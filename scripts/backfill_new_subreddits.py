#!/usr/bin/env python3
"""One-time backfill of posts from new subreddits since Feb 1, 2026.

Fetches historical posts from 23 new subreddits (13 New Opportunities +
10 Caregiving), scores them via Anthropic Haiku, and appends to the
corresponding Google Sheet tabs. No draft replies are generated.

Usage:
    source .venv/bin/activate
    python scripts/backfill_new_subreddits.py
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

# Ensure project root on path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

SPREADSHEET_ID = "1xnphzSpso_htOP1qX21B1zxx_R-Kvy99MrZ5Jfq2XAA"
BACKFILL_CUTOFF = datetime(2026, 2, 1, tzinfo=timezone.utc)
MAX_POSTS_PER_SUB = 1000  # Reddit API caps pagination around this
REDDIT_DELAY_SECS = 1.0
LLM_DELAY_SECS = 0.5
SCORE_THRESHOLD = 0  # Write all scored posts (team evaluates)

LOG_FILE = Path(project_root) / "data" / "backfill_new_subreddits.log"

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
SCORING_MODEL = "claude-haiku-4-5-20251001"

# ---------------------------------------------------------------------------
# Subreddit definitions
# ---------------------------------------------------------------------------


@dataclass
class SubredditConfig:
    name: str
    tab: str
    scan_all: bool = False
    limit: int = 100  # per-page limit for Reddit API


NEW_OPPORTUNITIES: List[SubredditConfig] = [
    SubredditConfig("AskOldPeople", "New Opportunities"),
    SubredditConfig("RedditForGrownups", "New Opportunities"),
    SubredditConfig("povertyfinance", "New Opportunities"),
    SubredditConfig("HearingAids", "New Opportunities", scan_all=True),
    SubredditConfig("tax", "New Opportunities"),
    SubredditConfig("HealthInsurance", "New Opportunities"),
    SubredditConfig("leanfire", "New Opportunities"),
    SubredditConfig("financialindependence", "New Opportunities"),
    SubredditConfig("VeteransBenefits", "New Opportunities"),
    SubredditConfig("EatCheapAndHealthy", "New Opportunities"),
    SubredditConfig("OverFifty", "New Opportunities", scan_all=True),
    SubredditConfig("homeowners", "New Opportunities"),
    SubredditConfig("legaladvice", "New Opportunities"),
    # Tier 1 health/benefits subs (condition self-selects for 55+)
    SubredditConfig("SleepApnea", "New Opportunities"),
    SubredditConfig("CPAP", "New Opportunities"),
    SubredditConfig("widowers", "New Opportunities"),
    SubredditConfig("tinnitus", "New Opportunities"),
    SubredditConfig("AFIB", "New Opportunities", scan_all=True),
    SubredditConfig("ProstateCancer", "New Opportunities", scan_all=True),
    SubredditConfig("diabetes_t2", "New Opportunities"),
    SubredditConfig("SSDI", "New Opportunities", scan_all=True),
    SubredditConfig("hardofhearing", "New Opportunities", scan_all=True),
    SubredditConfig("dentures", "New Opportunities", scan_all=True),
    SubredditConfig("COPD", "New Opportunities", scan_all=True),
]

CAREGIVING: List[SubredditConfig] = [
    SubredditConfig("AgingParents", "Caregiving Queue", scan_all=True),
    SubredditConfig("CaregiverSupport", "Caregiving Queue", scan_all=True),
    SubredditConfig("caregivers", "Caregiving Queue", scan_all=True),
    SubredditConfig("elderlycare", "Caregiving Queue", scan_all=True),
    SubredditConfig("hospice", "Caregiving Queue", scan_all=True),
    SubredditConfig("Parkinsons", "Caregiving Queue", scan_all=True),
    SubredditConfig("dementia", "Caregiving Queue", scan_all=True),
    SubredditConfig("Alzheimers", "Caregiving Queue", scan_all=True),
    SubredditConfig("Medicaid", "Caregiving Queue", scan_all=True),
    SubredditConfig("estateplanning", "Caregiving Queue", scan_all=True),
]

ALL_SUBS = NEW_OPPORTUNITIES + CAREGIVING

# ---------------------------------------------------------------------------
# Search terms (imported from dashboard.py at runtime)
# ---------------------------------------------------------------------------


def _load_terms():
    """Load include/exclude terms from the dashboard module."""
    from src.cmo_agent.leads.dashboard import (
        CAREGIVING_EXCLUDE_TERMS,
        DEFAULT_EXCLUDE_TERMS,
        DEFAULT_INCLUDE_TERMS,
    )

    return DEFAULT_INCLUDE_TERMS, DEFAULT_EXCLUDE_TERMS, CAREGIVING_EXCLUDE_TERMS


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger("backfill")

# ---------------------------------------------------------------------------
# Reddit fetching
# ---------------------------------------------------------------------------

REDDIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; SaverwellBackfill/1.0)",
}


def simple_hash(text: str) -> str:
    """Deterministic 12-char hex hash matching the n8n lead_id logic."""
    h = 0
    for ch in text:
        code = ord(ch)
        h = ((h << 5) - h) + code
        h &= 0xFFFFFFFF  # keep as 32-bit
    if h >= 0x80000000:
        h -= 0x100000000
    return format(abs(h), "x")[:12]


def fetch_subreddit_posts(
    sub: SubredditConfig,
    include_terms: List[Dict[str, str]],
    exclude_terms: List[str],
) -> List[Dict[str, Any]]:
    """Paginate r/{sub}/new.json back to BACKFILL_CUTOFF.

    Returns list of matched post dicts.
    """
    matched: List[Dict[str, Any]] = []
    after: Optional[str] = None
    total_fetched = 0
    cutoff_ts = BACKFILL_CUTOFF.timestamp()

    while total_fetched < MAX_POSTS_PER_SUB:
        url = f"https://www.reddit.com/r/{sub.name}/new.json?limit={sub.limit}"
        if after:
            url += f"&after={after}"

        try:
            resp = httpx.get(url, headers=REDDIT_HEADERS, timeout=15)
            if resp.status_code == 429:
                log.warning("Rate limited on r/%s, waiting 10s", sub.name)
                time.sleep(10)
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.error("Failed fetching r/%s page: %s", sub.name, e)
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        after = data.get("data", {}).get("after")
        total_fetched += len(children)
        reached_cutoff = False

        for child in children:
            post = child.get("data", {})
            if not post:
                continue

            created_utc = post.get("created_utc", 0)
            if created_utc < cutoff_ts:
                reached_cutoff = True
                break

            title = post.get("title", "")
            selftext = post.get("selftext", "")
            combined = (title + " " + selftext).lower()

            # Exclude check
            if any(ex in combined for ex in exclude_terms):
                continue

            # Age gate: skip posts from obviously young users
            import re as _re

            _young_patterns = [
                r"\bi['\s]?m\s+(1[4-9]|2[0-9])\b",
                r"\b(1[4-9]|2[0-5])\s*[mf]\b",
                r"\bi\s*\((1[4-9]|2[0-9])[mf]?\)",
                r"\bjust turned (1[4-9]|2[0-1])\b",
                r"\b(teenager|high school|college student|college kid|in college)\b",
                r"\b(dorm room|undergraduate|freshman|sophomore)\b",
            ]
            if any(_re.search(p, combined, _re.IGNORECASE) for p in _young_patterns):
                continue

            # Include check (or scan_all)
            pillar = "General"
            matched_term_strs: List[str] = []
            if sub.scan_all:
                matched_term_strs = ["scan_all"]
            else:
                for term_obj in include_terms:
                    if term_obj["term"].lower() in combined:
                        matched_term_strs.append(term_obj["term"])
                        if pillar == "General":
                            pillar = term_obj.get("pillar", "General")
                if not matched_term_strs:
                    continue

            permalink = post.get("permalink", "")
            post_url = f"https://www.reddit.com{permalink}" if permalink else ""
            hash_input = title.lower() + "|||" + post_url.lower()

            matched.append(
                {
                    "platform": "reddit",
                    "subreddit": post.get("subreddit", sub.name),
                    "title": title,
                    "content": selftext,
                    "url": post_url,
                    "author": post.get("author", ""),
                    "post_score": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "created_utc": created_utc,
                    "matched_terms": matched_term_strs,
                    "pillar": pillar,
                    "lead_id": simple_hash(hash_input),
                    "tab": sub.tab,
                    "source_subreddit": f"r/{sub.name}",
                }
            )

        if reached_cutoff or not after:
            break

        time.sleep(REDDIT_DELAY_SECS)

    log.info(
        "r/%s: fetched %d posts, %d matched",
        sub.name,
        total_fetched,
        len(matched),
    )
    return matched


# ---------------------------------------------------------------------------
# LLM scoring via Anthropic Haiku
# ---------------------------------------------------------------------------

SCORING_PROMPT = """You are a lead scoring agent for Saverwell, a free platform helping Americans aged 60+ find senior discounts, protect themselves from fraud, and understand Medicare costs.

Score this post on 5 dimensions (0-10 each):
1. Pillar Match: How strongly does this match savings, protection, guides, or caregiving content?
2. Help-Seeking Intent: Is this person actively seeking information or help? 10=direct question with urgency, 5=discussion, 1=news
3. Recency: Based on post age. 10=<6h, 8=<24h, 5=<72h, 3=<7d, 1=>7d
4. Engagement Potential: Can Saverwell add genuine value? 10=unanswered question we directly solve, 5=active discussion, 2=low engagement
5. Audience Fit: Is this person likely 55+ or caring for someone 55+? 10=explicitly senior/retired, 7=likely older adult, 5=age-ambiguous, 3=likely younger, 1=definitely young

Also classify:
- pillar: "Savings" | "Protection" | "Guides" | "Caregiving" | "Multi"
- post_type: "discount_seeking" | "fraud_alert" | "medicare_question" | "general_savings" | "resource_request" | "caregiving_advice" | "community_discussion"
- monetization_signal: "affiliate_potential" | "lead_gen" | "awareness" | "none"

Return ONLY valid JSON (no markdown, no explanation):
{"pillar_match":N,"help_intent":N,"recency":N,"engagement":N,"audience_fit":N,"total_score":N,"pillar":"...","post_type":"...","monetization_signal":"...","reviewer_notes":"..."}"""


def score_post(post: Dict[str, Any], client: httpx.Client) -> Dict[str, Any]:
    """Score a single post via Anthropic Haiku. Returns score dict."""
    hours_ago = (time.time() - post["created_utc"]) / 3600

    user_message = (
        f"Platform: {post['platform']}\n"
        f"Subreddit: r/{post['subreddit']}\n"
        f"Title: {post['title']}\n"
        f"Content: {post['content'][:1000]}\n"
        f"Hours ago: {hours_ago:.0f}\n"
        f"Matched terms: {', '.join(post['matched_terms'])}"
    )

    try:
        resp = client.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": SCORING_MODEL,
                "max_tokens": 300,
                "system": SCORING_PROMPT,
                "messages": [{"role": "user", "content": user_message}],
            },
            timeout=30,
        )
        resp.raise_for_status()
        result = resp.json()
        text = result["content"][0]["text"].strip()
        # Try direct parse first
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        # Strip markdown code blocks
        if "```" in text:
            import re as _re

            block = _re.search(r"```(?:json)?\s*\n?(.*?)```", text, _re.DOTALL)
            if block:
                try:
                    return json.loads(block.group(1).strip())
                except json.JSONDecodeError:
                    pass
        # Last resort: find first { to last }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise ValueError(f"No JSON found in: {text[:100]}")
    except Exception as e:
        log.warning("Scoring failed for %s: %s", post["lead_id"], e)
        return {
            "pillar_match": 0,
            "help_intent": 0,
            "recency": 0,
            "engagement": 0,
            "audience_fit": 0,
            "total_score": 0,
            "pillar": post["pillar"],
            "post_type": "unknown",
            "monetization_signal": "none",
            "reviewer_notes": f"Scoring error: {e}",
        }


# ---------------------------------------------------------------------------
# Google Sheets writing
# ---------------------------------------------------------------------------


def get_sheets_service():
    """Build Google Sheets API service using service account."""
    from google.oauth2 import service_account
    from googleapiclient.discovery import build

    creds_path = Path(project_root) / "data" / "saverwell-google-credentials.json"
    creds = service_account.Credentials.from_service_account_file(
        str(creds_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def get_existing_ids(sheets_service) -> set:
    """Read Lead IDs from all tabs to prevent duplicates."""
    ids: set = set()
    for tab in ["Lead Queue", "New Opportunities", "Caregiving Queue", "Archive"]:
        try:
            result = (
                sheets_service.spreadsheets()
                .values()
                .get(spreadsheetId=SPREADSHEET_ID, range=f"'{tab}'!C2:C5000")
                .execute()
            )
            for row in result.get("values", []):
                if row and row[0]:
                    ids.add(row[0])
        except Exception:
            continue
    return ids


def format_cst(unix_ts: float) -> str:
    """Format unix timestamp to CST display string."""
    from datetime import timedelta

    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    cst = timezone(timedelta(hours=-6))
    dt_cst = dt.astimezone(cst)
    return dt_cst.strftime("%-m/%-d/%Y %-I:%M %p")


def append_to_sheet(
    sheets_service,
    tab_name: str,
    posts: List[Dict[str, Any]],
) -> int:
    """Append scored posts to the specified tab. Returns count appended."""
    if not posts:
        return 0

    rows = []
    for p in posts:
        score_data = p.get("score_data", {})
        content = p.get("content", "") or ""
        title = p.get("title", "")
        summary = (title + " - " + content[:200]).strip() if content else title

        rows.append(
            [
                format_cst(time.time()),  # A: Date Found
                format_cst(p.get("created_utc", 0)),  # B: Post Date
                p.get("lead_id", ""),  # C: Lead ID
                p.get("platform", ""),  # D: Platform
                score_data.get("pillar", p.get("pillar", "")),  # E: Pillar
                summary,  # F: Post Title/Summary
                content,  # G: Full Content
                p.get("url", ""),  # H: Post URL
                str(score_data.get("total_score", 0)),  # I: Score
                score_data.get("post_type", ""),  # J: Post Type
                score_data.get("monetization_signal", ""),  # K: Monetization Signal
                "",  # L: Draft Reply (no replies for evaluation)
                score_data.get("reviewer_notes", ""),  # M: Reviewer Notes
                "New",  # N: Status
                "",  # O: Claimed Date/Time
                "",  # P: Claimed By
                "",  # Q: Response Notes
                "",  # R: Response URL
                "",  # S: Outcome
                p.get("source_subreddit", ""),  # T: Source Subreddit
            ]
        )

    try:
        sheets_service.spreadsheets().values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=f"'{tab_name}'!A2",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
        return len(rows)
    except Exception as e:
        log.error("Sheet append failed for %s: %s", tab_name, e)
        return 0


# ---------------------------------------------------------------------------
# Summary report
# ---------------------------------------------------------------------------


@dataclass
class SubStats:
    name: str
    tab: str
    total_fetched: int = 0
    matched: int = 0
    scores: List[int] = field(default_factory=list)
    pillars: Dict[str, int] = field(default_factory=dict)

    @property
    def avg_score(self) -> float:
        return sum(self.scores) / len(self.scores) if self.scores else 0

    @property
    def pct_above_25(self) -> float:
        if not self.scores:
            return 0
        return len([s for s in self.scores if s >= 25]) / len(self.scores) * 100

    @property
    def top_pillar(self) -> str:
        if not self.pillars:
            return "-"
        return max(self.pillars, key=self.pillars.get)


def print_summary(stats_list: List[SubStats]) -> None:
    """Print a formatted summary table."""
    header = f"{'Subreddit':<25} | {'Posts':>5} | {'Matched':>7} | {'Avg Score':>9} | {'% >= 25':>7} | {'Top Pillar':<12}"
    sep = "-" * len(header)
    print(f"\n{sep}")
    print("BACKFILL SUMMARY REPORT")
    print(sep)
    print(header)
    print(sep)

    total_posts = 0
    total_matched = 0
    for s in stats_list:
        total_posts += s.total_fetched
        total_matched += s.matched
        print(
            f"r/{s.name:<23} | {s.total_fetched:>5} | {s.matched:>7} | "
            f"{s.avg_score:>9.1f} | {s.pct_above_25:>6.0f}% | {s.top_pillar:<12}"
        )

    print(sep)
    print(f"{'TOTAL':<25} | {total_posts:>5} | {total_matched:>7}")
    print(sep)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    log.info("Starting backfill from %s", BACKFILL_CUTOFF.isoformat())

    # Load search terms
    include_terms, default_excludes, caregiving_excludes = _load_terms()

    # Initialize Google Sheets
    sheets_service = get_sheets_service()

    # Get existing IDs for dedup
    existing_ids = get_existing_ids(sheets_service)
    log.info("Found %d existing lead IDs across all tabs", len(existing_ids))

    # Initialize HTTP client for Anthropic
    anthropic_client = httpx.Client(timeout=30)

    all_stats: List[SubStats] = []

    for sub in ALL_SUBS:
        stats = SubStats(name=sub.name, tab=sub.tab)
        log.info("Processing r/%s (tab: %s, scan_all: %s)", sub.name, sub.tab, sub.scan_all)

        # Choose exclude list based on tab
        excludes = caregiving_excludes if sub.tab == "Caregiving Queue" else default_excludes

        # Fetch posts
        posts = fetch_subreddit_posts(sub, include_terms, excludes)
        stats.total_fetched = len(posts)  # Note: this is matched count from fetch

        # Dedup against existing
        new_posts = [p for p in posts if p["lead_id"] not in existing_ids]
        log.info(
            "r/%s: %d matched, %d new (after dedup)",
            sub.name,
            len(posts),
            len(new_posts),
        )

        if not new_posts:
            all_stats.append(stats)
            continue

        # Score each post via Haiku
        scored_posts: List[Dict[str, Any]] = []
        skipped_young = 0
        for i, post in enumerate(new_posts):
            score_data = score_post(post, anthropic_client)
            post["score_data"] = score_data

            total = score_data.get("total_score", 0)
            audience_fit = score_data.get("audience_fit", 0)
            stats.scores.append(total)

            p = score_data.get("pillar", "Unknown")
            stats.pillars[p] = stats.pillars.get(p, 0) + 1

            # Gate: only write posts with audience_fit >= 4
            # (likely 55+ or caring for someone 55+)
            if audience_fit >= 4:
                scored_posts.append(post)
            else:
                skipped_young += 1

            # Add to existing_ids to prevent re-processing regardless
            existing_ids.add(post["lead_id"])

            if (i + 1) % 10 == 0:
                log.info("  Scored %d/%d posts for r/%s", i + 1, len(new_posts), sub.name)

            time.sleep(LLM_DELAY_SECS)

        stats.matched = len(scored_posts)
        if skipped_young:
            log.info(
                "r/%s: skipped %d posts with audience_fit < 4",
                sub.name,
                skipped_young,
            )

        # Write to sheet in batches of 50
        written = 0
        for batch_start in range(0, len(scored_posts), 50):
            batch = scored_posts[batch_start : batch_start + 50]
            written += append_to_sheet(sheets_service, sub.tab, batch)

        log.info("r/%s: wrote %d rows to %s", sub.name, written, sub.tab)
        all_stats.append(stats)

    anthropic_client.close()

    # Print summary
    print_summary(all_stats)
    log.info("Backfill complete")


if __name__ == "__main__":
    main()
