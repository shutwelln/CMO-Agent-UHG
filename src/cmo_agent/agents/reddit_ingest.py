"""Reddit Ingest Agent - monitors subreddits via public JSON feeds."""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, OpportunityRepo, ScanLogRepo, SourceRepo
from ..llm.base import BaseLLM
from .base import BaseAgent

logger = structlog.get_logger()

# Respect Reddit's public rate limits
_REDDIT_DELAY_SECONDS = 2.0
_REDDIT_USER_AGENT = "CMOAgent/0.2.0 (marketing research bot)"


class RedditIngestAgent(BaseAgent):
    """Scans Reddit subreddits via public JSON feeds for marketing opportunities."""

    agent_id = "reddit_ingest_agent"
    agent_name = "Reddit Ingest Agent"

    def __init__(self, llm: BaseLLM, db: Database, max_iterations: int = 10) -> None:
        self._opportunities = OpportunityRepo(db)
        self._sources = SourceRepo(db)
        self._config = ConfigRepo(db)
        self._scan_log = ScanLogRepo(db)
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        ws_label = workspace_id or "all workspaces"
        return f"""You are the Reddit Ingest Agent for {ws_label}.
You monitor Reddit subreddits via public JSON feeds to find marketing opportunities.

For each post, categorize it as:
- high_intent_lead: Someone asking for help or recommendations (highest priority)
- general_discussion: Good for engagement and community building
- news_announcement: Potential content source
- irrelevant: Does not match workspace keywords

Score relevant posts on four dimensions (0-10 each):
- Relevance: How well does this match the workspace's keywords and audience?
- Recency: How fresh is the content?
- Engagement potential: Comments, upvotes, social signals
- Actionability: Can we create content from this?

Total score >= 25 is considered high-priority.
Always return structured results with source URLs, scores, and categorization."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="scan_subreddits",
            description="Scan all monitored subreddits for a workspace. Returns new opportunities found.",
        )
        async def scan_subreddits(workspace_id: str) -> Dict[str, Any]:
            sources = await self._sources.list_by_workspace(workspace_id, "subreddit")
            if not sources:
                return {"message": "No subreddits configured for this workspace", "found": 0}

            keywords_raw = await self._config.get(workspace_id, "keywords")
            keywords: List[str] = json.loads(keywords_raw) if keywords_raw else []
            if not keywords:
                return {"message": "No keywords configured for this workspace", "found": 0}

            logger.info(
                "reddit_scan_keywords",
                workspace_id=workspace_id,
                source="config_keywords",
                include_count=len(keywords),
            )

            log_id = await self._scan_log.create(self.agent_id, workspace_id, "subreddit")

            total_scanned = 0
            total_found = 0
            errors: List[str] = []
            results: List[Dict[str, Any]] = []

            for source in sources:
                subreddit = source.url or ""
                try:
                    posts = await _fetch_subreddit(subreddit)
                    total_scanned += len(posts)

                    for post in posts:
                        post_id = post.get("id", "")
                        # Dedup — check both bare ID and reddit_-prefixed form
                        # (older records used "reddit_{id}" as source_id)
                        if await self._opportunities.exists_by_source_id(
                            "reddit", post_id
                        ) or await self._opportunities.exists_by_source_id(
                            "reddit", f"reddit_{post_id}"
                        ):
                            continue

                        title = post.get("title", "")
                        selftext = post.get("selftext", "")
                        combined = f"{title} {selftext}"

                        if not any(kw.lower() in combined.lower() for kw in keywords):
                            continue

                        score = _compute_score(post, keywords)
                        category = _quick_categorize(title, selftext)

                        # Convert Reddit epoch → ISO string for posted_at
                        created_utc = post.get("created_utc", 0)
                        posted_at_str = (
                            datetime.fromtimestamp(created_utc, tz=timezone.utc).isoformat()
                            if created_utc
                            else None
                        )

                        # Cross-platform dedup hash
                        norm = title.strip().lower() + "|" + (selftext or "").strip().lower()
                        content_hash = hashlib.sha256(norm.encode("utf-8")).hexdigest()

                        if await self._opportunities.exists_by_content_hash(content_hash):
                            continue

                        opp = await self._opportunities.create(
                            workspace_id=workspace_id,
                            source="reddit",
                            source_url=f"https://www.reddit.com{post.get('permalink', '')}",
                            source_id=post_id,
                            title=title,
                            content=selftext[:2000] if selftext else None,
                            score=score,
                            score_breakdown={
                                "relevance": _relevance_score(combined.lower(), keywords),
                                "recency": _recency_score(post.get("created_utc", 0)),
                                "engagement": _engagement_score(post),
                                "actionability": _actionability_score(title, selftext),
                            },
                            category=category,
                            subreddit=subreddit,
                            posted_at=posted_at_str,
                            content_hash=content_hash,
                        )

                        total_found += 1
                        results.append(
                            {
                                "id": opp.id,
                                "title": title[:100],
                                "subreddit": subreddit,
                                "score": score,
                                "category": category,
                            }
                        )

                    await self._sources.update_last_checked(source.id)
                    # Rate limit between subreddits
                    await asyncio.sleep(_REDDIT_DELAY_SECONDS)

                except Exception as e:
                    err_msg = f"r/{subreddit}: {e}"
                    logger.error("reddit_scan_error", error=err_msg)
                    errors.append(err_msg)

            await self._scan_log.complete(log_id, total_scanned, total_found, errors or None)

            return {
                "workspace_id": workspace_id,
                "subreddits_scanned": len(sources),
                "posts_scanned": total_scanned,
                "opportunities_found": total_found,
                "errors": errors,
                "results": results[:20],  # Cap for context window
            }

        @self.tool_registry.register(
            name="fetch_subreddit_feed",
            description="Fetch recent posts from a single subreddit. Returns raw post data.",
        )
        async def fetch_subreddit_feed(subreddit: str, limit: int = 50) -> Dict[str, Any]:
            posts = await _fetch_subreddit(subreddit, limit)
            return {
                "subreddit": subreddit,
                "post_count": len(posts),
                "posts": [
                    {
                        "id": p.get("id"),
                        "title": p.get("title"),
                        "score": p.get("score", 0),
                        "num_comments": p.get("num_comments", 0),
                        "url": f"https://www.reddit.com{p.get('permalink', '')}",
                    }
                    for p in posts[:20]
                ],
            }

        @self.tool_registry.register(
            name="get_monitored_subreddits",
            description="List all monitored subreddits for a workspace.",
        )
        async def get_monitored_subreddits(workspace_id: str) -> Dict[str, Any]:
            sources = await self._sources.list_by_workspace(workspace_id, "subreddit")
            return {
                "workspace_id": workspace_id,
                "subreddits": [
                    {"name": s.name, "url": s.url, "active": s.active, "id": s.id} for s in sources
                ],
            }

        @self.tool_registry.register(
            name="add_subreddit",
            description="Add a subreddit to monitor for a workspace.",
        )
        async def add_subreddit(
            workspace_id: str,
            subreddit: str,
            keywords: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            source = await self._sources.create(
                workspace_id=workspace_id,
                source_type="subreddit",
                url=subreddit.lstrip("r/"),
                name=f"r/{subreddit.lstrip('r/')}",
                keywords=keywords,
            )
            return {"created": True, "source_id": source.id, "subreddit": source.url}

        @self.tool_registry.register(
            name="remove_subreddit",
            description="Remove a subreddit from monitoring.",
        )
        async def remove_subreddit(source_id: str) -> Dict[str, Any]:
            await self._sources.delete(source_id)
            return {"deleted": True, "source_id": source_id}


# ── Helper functions ──────────────────────────────────────────────────────


async def _fetch_subreddit(subreddit: str, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch posts from Reddit's public JSON endpoint."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    headers = {"User-Agent": _REDDIT_USER_AGENT}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, params={"limit": limit}, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    children = data.get("data", {}).get("children", [])
    return [c.get("data", {}) for c in children]


def _relevance_score(text: str, keywords: List[str]) -> int:
    matches = sum(1 for kw in keywords if kw.lower() in text)
    if matches >= 4:
        return 10
    if matches >= 2:
        return 7
    if matches >= 1:
        return 4
    return 0


def _recency_score(created_utc: float) -> int:
    if created_utc == 0:
        return 5
    age_hours = (datetime.now(tz=timezone.utc).timestamp() - created_utc) / 3600
    if age_hours < 6:
        return 10
    if age_hours < 24:
        return 8
    if age_hours < 72:
        return 5
    if age_hours < 168:
        return 3
    return 1


def _engagement_score(post: Dict[str, Any]) -> int:
    ups = post.get("score", 0)
    comments = post.get("num_comments", 0)
    total = ups + comments * 2
    if total >= 100:
        return 10
    if total >= 50:
        return 8
    if total >= 20:
        return 6
    if total >= 5:
        return 4
    return 2


def _actionability_score(title: str, selftext: str) -> int:
    """Heuristic: questions and help-seeking posts are more actionable."""
    text = f"{title} {selftext}".lower()
    question_signals = [
        "?",
        "how do",
        "where can",
        "any advice",
        "recommend",
        "help me",
        "looking for",
        "anyone know",
        "suggestions",
    ]
    hits = sum(1 for s in question_signals if s in text)
    if hits >= 3:
        return 10
    if hits >= 2:
        return 8
    if hits >= 1:
        return 6
    return 3


def _compute_score(post: Dict[str, Any], keywords: List[str]) -> int:
    title = post.get("title", "")
    selftext = post.get("selftext", "")
    combined = f"{title} {selftext}".lower()
    return (
        _relevance_score(combined, keywords)
        + _recency_score(post.get("created_utc", 0))
        + _engagement_score(post)
        + _actionability_score(title, selftext)
    )


def _quick_categorize(title: str, selftext: str) -> str:
    """Fast heuristic categorization without LLM call."""
    text = f"{title} {selftext}".lower()
    question_signals = [
        "?",
        "how do",
        "where can",
        "any advice",
        "recommend",
        "help me",
        "looking for",
        "anyone know",
    ]
    if any(s in text for s in question_signals):
        return "high_intent_lead"
    news_signals = [
        "announce",
        "announcement",
        "update",
        "new law",
        "breaking",
        "report",
        "study",
        "research",
        "policy",
        "legislation",
        "federal",
        "bill",
        "foundation",
        "conference",
        "event",
        "initiative",
        "program launch",
        "advocacy",
    ]
    if any(s in text for s in news_signals):
        return "news_announcement"
    return "general_discussion"
