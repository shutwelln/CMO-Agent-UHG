"""Google Alerts Ingest Agent - scans Gmail for Google Alert emails via n8n."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, OpportunityRepo, ScanLogRepo, SourceRepo
from ..llm.base import BaseLLM
from ..n8n.client import N8NClient
from .base import BaseAgent

logger = structlog.get_logger()


class GoogleAlertsIngestAgent(BaseAgent):
    """Scans a Gmail inbox for Google Alert emails, extracts links, and scores them."""

    agent_id = "google_alerts_agent"
    agent_name = "Google Alerts Ingest Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        n8n_client: Optional[N8NClient] = None,
        max_iterations: int = 10,
    ) -> None:
        self._opportunities = OpportunityRepo(db)
        self._sources = SourceRepo(db)
        self._config = ConfigRepo(db)
        self._scan_log = ScanLogRepo(db)
        self._n8n = n8n_client
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        ws_label = workspace_id or "all workspaces"
        return f"""You are the Google Alerts Ingest Agent for {ws_label}.
You scan a dedicated Gmail inbox for Google Alert emails, extract the links
and summaries from each alert, score them for relevance, and save the best
ones as marketing opportunities.

Google Alert emails contain curated links from Google matching alert keywords.
Each email typically has multiple article links with short snippets.

For each article, score it on:
- Relevance (0-10): Match to workspace keywords
- Recency (0-10): How fresh
- Engagement potential (0-10): Estimated interest
- Actionability (0-10): Can we create content from this?

Total score >= 25 is high-priority."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="scan_google_alerts",
            description="Scan Google Alert emails for a workspace via n8n workflow. Returns new opportunities.",
        )
        async def scan_google_alerts(workspace_id: str) -> Dict[str, Any]:
            sources = await self._sources.list_by_workspace(workspace_id, "gmail_filter")
            if not sources:
                return {"message": "No Gmail alert sources configured", "found": 0}

            keywords_raw = await self._config.get(workspace_id, "keywords")
            keywords = json.loads(keywords_raw) if keywords_raw else []

            log_id = await self._scan_log.create(self.agent_id, workspace_id, "gmail_filter")

            total_scanned = 0
            total_found = 0
            errors: List[str] = []
            results: List[Dict[str, Any]] = []

            for source in sources:
                try:
                    alerts = await self._fetch_alerts_via_n8n(source.url or "", workspace_id)
                    total_scanned += len(alerts)

                    for alert in alerts:
                        link = alert.get("url", "")
                        if not link:
                            continue
                        if await self._opportunities.exists_by_source_id("gmail", link):
                            continue

                        title = alert.get("title", "")
                        snippet = alert.get("snippet", "")
                        combined = f"{title} {snippet}".lower()

                        if keywords and not any(kw.lower() in combined for kw in keywords):
                            continue

                        score = self._score_alert(title, snippet, keywords)
                        opp = await self._opportunities.create(
                            workspace_id=workspace_id,
                            source="gmail",
                            source_url=link,
                            source_id=link,
                            title=title,
                            content=snippet[:2000] if snippet else None,
                            score=score,
                            score_breakdown={
                                "relevance": self._kw_relevance(combined, keywords),
                                "recency": 8,  # Google Alerts are inherently recent
                                "engagement": 5,
                                "actionability": self._actionability(title, snippet),
                            },
                            category="news_announcement",
                        )
                        total_found += 1
                        results.append(
                            {
                                "id": opp.id,
                                "title": title[:100],
                                "url": link,
                                "score": score,
                            }
                        )

                    await self._sources.update_last_checked(source.id)

                except Exception as e:
                    err = f"{source.name}: {e}"
                    logger.error("google_alerts_scan_error", error=err)
                    errors.append(err)

            await self._scan_log.complete(log_id, total_scanned, total_found, errors or None)
            return {
                "workspace_id": workspace_id,
                "sources_scanned": len(sources),
                "alerts_scanned": total_scanned,
                "opportunities_found": total_found,
                "errors": errors,
                "results": results[:20],
            }

        @self.tool_registry.register(
            name="get_gmail_sources",
            description="List configured Gmail alert sources for a workspace.",
        )
        async def get_gmail_sources(workspace_id: str) -> Dict[str, Any]:
            sources = await self._sources.list_by_workspace(workspace_id, "gmail_filter")
            return {
                "workspace_id": workspace_id,
                "sources": [
                    {"name": s.name, "filter": s.url, "active": s.active, "id": s.id}
                    for s in sources
                ],
            }

        @self.tool_registry.register(
            name="add_gmail_source",
            description="Add a Gmail filter/label to monitor for Google Alerts.",
        )
        async def add_gmail_source(
            workspace_id: str,
            label_filter: str,
            name: str,
            keywords: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            source = await self._sources.create(
                workspace_id=workspace_id,
                source_type="gmail_filter",
                url=label_filter,
                name=name,
                keywords=keywords,
            )
            return {"created": True, "source_id": source.id}

    async def _fetch_alerts_via_n8n(
        self, label_filter: str, workspace_id: str
    ) -> List[Dict[str, Any]]:
        """Fetch Google Alert emails via an n8n workflow.

        The n8n workflow should:
        1. Connect to Gmail via OAuth
        2. Fetch emails matching the label/filter
        3. Parse out article links and snippets
        4. Return them as JSON array

        If n8n is not available, returns empty list.
        """
        if not self._n8n:
            logger.warning("google_alerts_no_n8n", workspace_id=workspace_id)
            return []

        try:
            # Look for a workflow named "Google Alerts - {workspace}"
            workflow = await self._n8n.get_workflow_by_name(f"Google Alerts - {workspace_id}")
            if not workflow:
                # Fall back to a generic alerts workflow
                workflow = await self._n8n.get_workflow_by_name("Google Alerts Scanner")

            if not workflow:
                logger.warning(
                    "google_alerts_no_workflow",
                    workspace_id=workspace_id,
                )
                return []

            execution = await self._n8n.execute_workflow(
                workflow.id,
                {"label_filter": label_filter, "workspace_id": workspace_id},
            )

            # The workflow execution should return alert items
            # For now, return empty if execution doesn't return data directly
            # (n8n executions are async; we'd poll or use webhook callback)
            logger.info(
                "google_alerts_workflow_triggered",
                execution_id=execution.id,
                workspace_id=workspace_id,
            )
            return []

        except Exception as e:
            logger.error("google_alerts_n8n_error", error=str(e))
            return []

    @staticmethod
    def _kw_relevance(text: str, keywords: List[str]) -> int:
        matches = sum(1 for kw in keywords if kw.lower() in text)
        if matches >= 4:
            return 10
        if matches >= 2:
            return 7
        if matches >= 1:
            return 4
        return 0

    @staticmethod
    def _actionability(title: str, snippet: str) -> int:
        text = f"{title} {snippet}".lower()
        signals = ["guide", "how to", "tips", "new", "update", "report", "study", "data"]
        hits = sum(1 for s in signals if s in text)
        if hits >= 3:
            return 9
        if hits >= 1:
            return 6
        return 3

    def _score_alert(self, title: str, snippet: str, keywords: List[str]) -> int:
        combined = f"{title} {snippet}".lower()
        return (
            self._kw_relevance(combined, keywords)
            + 8  # Recency: Google Alerts are fresh by nature
            + 5  # Engagement: no data
            + self._actionability(title, snippet)
        )
