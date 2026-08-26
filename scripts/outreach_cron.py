#!/usr/bin/env python3
"""Standalone DSDN outreach cron job.

Runs the full outreach pipeline without requiring the Slack bot:
1. Search term sync from Google Sheet (first, so manual edits are picked up)
2. Reddit ingest for DSDN workspace
3. Outreach scan (Glowing + WTE + Mumsnet + BabyandBump + classify/draft + Sheet sync)
4. Slack notifications for ALL new fully-processed items above threshold
4.5. Archive skipped items from Outreach Queue to Archive tab
5. Daily digest (timestamp-gated, once per 24h) + write last-run timestamp

Designed for macOS launchd (4-hour interval). Safe to run concurrently
with the Slack bot - dedup prevents double-writes.

Usage:
    python scripts/outreach_cron.py
    python scripts/outreach_cron.py --dry-run   # skip Slack notifications
"""

from __future__ import annotations

import asyncio
import fcntl
import logging
import sys
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Dict, List

# Ensure src/ is on sys.path when run as a standalone script
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── Logging ────────────────────────────────────────────────────────────

LOG_DIR = ROOT / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOG_FILE = LOG_DIR / "outreach_cron.log"
LOCK_FILE = LOG_DIR / "outreach_cron.lock"
LAST_RUN_FILE = LOG_DIR / "outreach_cron_last_run.txt"
DIGEST_LAST_RUN_FILE = LOG_DIR / "outreach_digest_last_run.txt"

# Digest runs at most once every 23 hours
_DIGEST_INTERVAL_HOURS = 23

# Rotating file handler: 5 MB max, 3 backups
file_handler = RotatingFileHandler(str(LOG_FILE), maxBytes=5 * 1024 * 1024, backupCount=3)
file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

logger = logging.getLogger("outreach_cron")
logger.setLevel(logging.INFO)
logger.addHandler(file_handler)
logger.addHandler(console_handler)

WORKSPACE_ID = "dsdn"


# ── File Lock ──────────────────────────────────────────────────────────


class CronLock:
    """File-based lock to prevent concurrent runs."""

    def __init__(self, lock_path: Path):
        self._path = lock_path
        self._fp: Any = None

    def acquire(self) -> bool:
        """Try to acquire the lock. Returns False if another instance holds it."""
        self._fp = open(self._path, "w")
        try:
            fcntl.flock(self._fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._fp.write(str(time.time()))
            self._fp.flush()
            return True
        except OSError:
            self._fp.close()
            self._fp = None
            return False

    def release(self) -> None:
        if self._fp:
            fcntl.flock(self._fp, fcntl.LOCK_UN)
            self._fp.close()
            self._fp = None


# ── Slack Notifications ────────────────────────────────────────────────


def _score_emoji(score: int) -> str:
    """Color-coded emoji for outreach score (0-40 scale)."""
    if score >= 30:
        return "\U0001f7e2"  # green circle
    elif score >= 20:
        return "\U0001f7e0"  # orange circle
    return "\U0001f534"  # red circle


def _build_notification_blocks(opp: Any) -> List[Dict[str, Any]]:
    """Build Slack Block Kit blocks for an outreach candidate.

    Mirrors _build_outreach_notification_blocks in tasks.py but adds
    the score emoji to the header line.
    """
    sensitivity = ""
    if getattr(opp, "platform_post_type", None) in ("loss",):
        sensitivity = " [SENSITIVE]"
    score_breakdown = getattr(opp, "score_breakdown", None) or {}
    if isinstance(score_breakdown, str):
        import json as _json

        try:
            score_breakdown = _json.loads(score_breakdown)
        except Exception:
            score_breakdown = {}
    if score_breakdown.get("urgency", 0) >= 9:
        sensitivity = " [SENSITIVE]"

    score = getattr(opp, "score", 0) or 0
    emoji = _score_emoji(score)
    snippet = (getattr(opp, "content", "") or "")[:200]
    if len(getattr(opp, "content", "") or "") > 200:
        snippet += "..."

    post_type_display = (getattr(opp, "platform_post_type", "") or "unknown").replace("_", " ")
    title = (getattr(opp, "title", "") or "")[:200]

    blocks: List[Dict[str, Any]] = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji} *New Outreach Candidate (Score: {score}/40)*{sensitivity}\n\n"
                    f"*{title}*\n"
                    f"Platform: `{getattr(opp, 'source', '')}` | "
                    f"Type: _{post_type_display}_\n"
                    f"_{snippet}_"
                ),
            },
        },
    ]

    source_url = getattr(opp, "source_url", "")
    if source_url:
        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"<{source_url}|View original post>"},
                ],
            }
        )

    opp_id = getattr(opp, "id", "")
    blocks.append(
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Claim"},
                    "action_id": "claim_outreach_post",
                    "value": opp_id,
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Generate Reply"},
                    "action_id": "generate_outreach_reply",
                    "value": opp_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Skip"},
                    "action_id": "skip_outreach_post",
                    "value": opp_id,
                },
            ],
        }
    )

    created_at = getattr(opp, "created_at", "")
    blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"ID: `{opp_id[:12]}...` | Found: {created_at}"},
            ],
        }
    )

    return blocks


async def _send_slack_notifications(
    opps: list,
    channel: str,
    bot_token: str,
    dry_run: bool = False,
) -> int:
    """Post Slack notifications for outreach candidates.

    Returns count of messages sent. Falls back to text-only if Block Kit
    fails for some reason.
    """
    if dry_run or not bot_token or not channel:
        logger.info(
            "Slack notifications skipped (dry_run=%s, token=%s, channel=%s)",
            dry_run,
            bool(bot_token),
            channel,
        )
        return 0

    try:
        from slack_sdk.web.async_client import AsyncWebClient
    except ImportError:
        logger.warning("slack_sdk not installed, skipping notifications")
        return 0

    client = AsyncWebClient(token=bot_token)

    # Best-effort channel join
    try:
        await client.conversations_join(channel=channel)
    except Exception:
        pass  # Already in channel, or channel is a DM

    sent = 0
    for opp in opps:
        try:
            blocks = _build_notification_blocks(opp)
            score = getattr(opp, "score", 0) or 0
            emoji = _score_emoji(score)
            title = (getattr(opp, "title", "") or "")[:80]
            fallback = f"{emoji} New outreach candidate (Score: {score}/40): {title}"

            await client.chat_postMessage(
                channel=channel,
                text=fallback,
                blocks=blocks,
            )
            sent += 1
            logger.info(
                "Slack notification sent: opp_id=%s score=%s", getattr(opp, "id", ""), score
            )
        except Exception as e:
            logger.error("Slack notification error: opp_id=%s error=%s", getattr(opp, "id", ""), e)

    return sent


async def _send_failure_alert(channel: str, bot_token: str, error_msg: str) -> None:
    """Post a failure alert to Slack."""
    if not bot_token or not channel:
        return
    try:
        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=bot_token)
        await client.chat_postMessage(
            channel=channel,
            text=f"\U0001f6a8 Outreach cron failed: {error_msg[:500]}",
        )
    except Exception:
        pass  # Best-effort


# ── Digest Helpers ─────────────────────────────────────────────────────


def _should_run_digest() -> bool:
    """Check if enough time has passed since the last digest."""
    if not DIGEST_LAST_RUN_FILE.exists():
        return True
    try:
        last_ts = DIGEST_LAST_RUN_FILE.read_text().strip()
        last_dt = datetime.fromisoformat(last_ts)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        elapsed = datetime.now(timezone.utc) - last_dt
        return elapsed.total_seconds() >= _DIGEST_INTERVAL_HOURS * 3600
    except Exception:
        return True


async def _get_digest_stats(db: Any) -> Dict[str, Any]:
    """Query DB for daily digest statistics."""
    stats: Dict[str, Any] = {}

    # New items in last 24h by source
    rows = await db.fetchall(
        """SELECT source, COUNT(*) as cnt FROM opportunities
        WHERE workspace_id = 'dsdn'
          AND outreach_status IS NOT NULL
          AND created_at >= datetime('now', '-1 day')
        GROUP BY source""",
        (),
    )
    by_source: Dict[str, int] = {}
    total_new = 0
    for r in rows:
        by_source[r["source"]] = r["cnt"]
        total_new += r["cnt"]
    stats["new_24h"] = total_new
    stats["new_by_source"] = by_source

    # Pending items (unclaimed) by score tier
    rows = await db.fetchall(
        """SELECT score FROM opportunities
        WHERE workspace_id = 'dsdn'
          AND outreach_status IN ('new', 'draft_generated', 'notified')
          AND status != 'dismissed'""",
        (),
    )
    high = sum(1 for r in rows if (r["score"] or 0) >= 30)
    medium = sum(1 for r in rows if 20 <= (r["score"] or 0) < 30)
    low = sum(1 for r in rows if (r["score"] or 0) < 20)
    stats["pending_total"] = len(rows)
    stats["pending_high"] = high
    stats["pending_medium"] = medium
    stats["pending_low"] = low

    # Items by post type
    rows = await db.fetchall(
        """SELECT platform_post_type, COUNT(*) as cnt FROM opportunities
        WHERE workspace_id = 'dsdn'
          AND outreach_status IS NOT NULL
          AND created_at >= datetime('now', '-1 day')
          AND platform_post_type IS NOT NULL
        GROUP BY platform_post_type""",
        (),
    )
    stats["by_post_type"] = {r["platform_post_type"]: r["cnt"] for r in rows}

    # Team activity
    rows = await db.fetchall(
        """SELECT
            SUM(CASE WHEN outreach_status = 'claimed' THEN 1 ELSE 0 END) as claimed,
            SUM(CASE WHEN outreach_status = 'responded' THEN 1 ELSE 0 END) as responded,
            SUM(CASE WHEN outreach_outcome = 'connected' THEN 1 ELSE 0 END) as connected
        FROM opportunities
        WHERE workspace_id = 'dsdn'
          AND outreach_status IS NOT NULL
          AND created_at >= datetime('now', '-7 days')""",
        (),
    )
    if rows:
        r = rows[0]
        stats["team_claimed"] = r["claimed"] or 0
        stats["team_responded"] = r["responded"] or 0
        stats["team_connected"] = r["connected"] or 0
    else:
        stats["team_claimed"] = 0
        stats["team_responded"] = 0
        stats["team_connected"] = 0

    return stats


def _format_digest_blocks(stats: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Build Slack Block Kit blocks for the daily digest."""
    by_source = stats.get("new_by_source", {})
    source_parts = []
    for src in ["reddit", "whattoexpect", "mumsnet", "babyandbump", "glowing"]:
        cnt = by_source.get(src, 0)
        if cnt > 0:
            label = {
                "reddit": "Reddit",
                "whattoexpect": "WTE",
                "mumsnet": "Mumsnet",
                "babyandbump": "BabyandBump",
                "glowing": "Glowing",
            }.get(src, src)
            source_parts.append(f"{label}: {cnt}")
    source_line = " | ".join(source_parts) if source_parts else "None"

    blocks: List[Dict[str, Any]] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": "DSDN Outreach Daily Digest"},
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*New posts found (last 24h):* {stats.get('new_24h', 0)}\n"
                    f"  {source_line}\n\n"
                    f"*Pending queue:* {stats.get('pending_total', 0)} items\n"
                    f"  High priority (30+): {stats.get('pending_high', 0)}\n"
                    f"  Medium priority (20-29): {stats.get('pending_medium', 0)}\n"
                    f"  Lower priority (<20): {stats.get('pending_low', 0)}\n\n"
                    f"*Team activity (last 7 days):*\n"
                    f"  Claimed: {stats.get('team_claimed', 0)} | "
                    f"Responded: {stats.get('team_responded', 0)} | "
                    f"Connected: {stats.get('team_connected', 0)}"
                ),
            },
        },
    ]
    return blocks


async def _send_daily_digest(
    stats: Dict[str, Any],
    channel: str,
    bot_token: str,
    dry_run: bool = False,
) -> bool:
    """Post the daily digest to Slack. Returns True if sent."""
    if dry_run or not bot_token or not channel:
        logger.info("Digest skipped (dry_run=%s)", dry_run)
        return False

    try:
        from slack_sdk.web.async_client import AsyncWebClient
    except ImportError:
        logger.warning("slack_sdk not installed, skipping digest")
        return False

    client = AsyncWebClient(token=bot_token)
    try:
        await client.conversations_join(channel=channel)
    except Exception:
        pass

    blocks = _format_digest_blocks(stats)
    try:
        await client.chat_postMessage(
            channel=channel,
            text="DSDN Outreach Daily Digest",
            blocks=blocks,
        )
        return True
    except Exception as e:
        logger.error("Digest send failed: %s", e)
        return False


async def _archive_skipped_items(db: Any, dashboard: Any) -> Dict[str, Any]:
    """Archive skipped items: move from Sheet Queue to Archive, update DB."""
    archived_ids = await dashboard.archive_skipped_rows()

    db_updated = 0
    for opp_id in archived_ids:
        try:
            await db.execute(
                "UPDATE opportunities SET outreach_status = 'dismissed' "
                "WHERE id = ? AND outreach_status = 'skipped'",
                (opp_id,),
            )
            db_updated += 1
        except Exception as e:
            logger.warning("Failed to update skipped opp %s in DB: %s", opp_id, e)

    return {"sheet_archived": len(archived_ids), "db_updated": db_updated}


# ── Main Pipeline ──────────────────────────────────────────────────────


async def run_pipeline(dry_run: bool = False) -> Dict[str, Any]:
    """Execute the full outreach pipeline."""
    from cmo_agent.agents.factory import AgentFactory
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database
    from cmo_agent.db.repositories import OpportunityRepo
    from cmo_agent.n8n.client import N8NClient

    settings = Settings()
    stats: Dict[str, Any] = {"started_at": datetime.now(timezone.utc).isoformat()}

    if not settings.outreach_enabled:
        logger.info("OUTREACH_ENABLED=false, exiting")
        stats["skipped"] = "OUTREACH_ENABLED=false"
        return stats

    channel = settings.slack_outreach_channel
    bot_token = settings.slack_bot_token
    score_threshold = settings.outreach_score_threshold

    # ── Boot minimal stack ─────────────────────────────────────────
    logger.info("Booting agent stack...")
    db = Database(db_path=settings.db_path)
    await db.initialize()

    n8n_client = N8NClient(
        base_url=settings.n8n_base_url,
        api_key=settings.n8n_api_key,
        timeout=settings.n8n_timeout,
    )
    await n8n_client.__aenter__()

    try:
        registry = await AgentFactory.create_all(
            settings=settings,
            db=db,
            n8n_client=n8n_client,
            brand_voices_dir=Path(settings.brand_voices_dir),
        )

        # ── Step 1: Search term sync (BEFORE scans) ────────────────
        # Sync first so any manual edits to the Search Terms tab are
        # picked up by the scanners in this same run.
        logger.info("Step 1: Search term sync from Google Sheet")
        outreach_agent = registry.get("outreach_scanner_agent")
        if outreach_agent:
            result = await outreach_agent.process_message(
                "Sync search terms from the Google Sheet to the database.",
                workspace_id=WORKSPACE_ID,
            )
            stats["search_term_sync"] = result.status
            logger.info("Search term sync done: status=%s", result.status)

        # ── Step 2: Reddit ingest for DSDN ─────────────────────────
        logger.info("Step 2: Reddit ingest for DSDN")
        reddit_agent = registry.get("reddit_ingest_agent")
        if reddit_agent:
            result = await reddit_agent.process_message(
                "Scan all monitored subreddits for workspace dsdn",
                workspace_id=WORKSPACE_ID,
            )
            stats["reddit_ingest"] = result.status
            logger.info("Reddit ingest done: status=%s", result.status)
        else:
            stats["reddit_ingest"] = "agent_not_found"
            logger.warning("reddit_ingest_agent not found in registry")

        # ── Step 3: Full outreach scan ─────────────────────────────
        logger.info(
            "Step 3: Full outreach scan (Glowing + WTE + Mumsnet + BabyandBump + classify + draft + Sheet)"
        )
        if not outreach_agent:
            outreach_agent = registry.get("outreach_scanner_agent")
        if outreach_agent:
            result = await outreach_agent.process_message(
                "Scan all outreach sources for DSDN workspace.",
                workspace_id=WORKSPACE_ID,
            )
            stats["outreach_scan"] = result.status
            logger.info("Outreach scan done: status=%s", result.status)
        else:
            stats["outreach_scan"] = "agent_not_found"
            logger.warning("outreach_scanner_agent not found in registry")

        # ── Step 4: Slack notifications for ALL new items ──────────
        logger.info("Step 4: Slack notifications")
        opp_repo = OpportunityRepo(db)
        new_opps = await opp_repo.list_outreach_queue(WORKSPACE_ID, outreach_status="new", limit=50)
        # Also include draft_generated items (classify/draft just ran)
        draft_opps = await opp_repo.list_outreach_queue(
            WORKSPACE_ID, outreach_status="draft_generated", limit=50
        )
        all_new = new_opps + draft_opps
        # Filter by score threshold and deduplicate
        seen_ids: set = set()
        notify_opps = []
        for opp in all_new:
            if opp.id not in seen_ids and opp.score >= score_threshold:
                notify_opps.append(opp)
                seen_ids.add(opp.id)

        stats["candidates_above_threshold"] = len(notify_opps)
        logger.info(
            "Notification candidates: new=%d draft=%d above_threshold=%d",
            len(new_opps),
            len(draft_opps),
            len(notify_opps),
        )

        sent = await _send_slack_notifications(notify_opps, channel, bot_token, dry_run=dry_run)
        stats["slack_notifications_sent"] = sent

        # Mark notified items so they don't get re-notified
        for opp in notify_opps:
            try:
                await db.execute(
                    "UPDATE opportunities SET outreach_status = 'notified' "
                    "WHERE id = ? AND outreach_status IN ('new', 'draft_generated')",
                    (opp.id,),
                )
            except Exception as e:
                logger.warning("Failed to mark opp %s as notified: %s", opp.id, e)

        # ── Step 4.5: Archive skipped items ─────────────────────────
        logger.info("Step 4.5: Archive skipped items from Outreach Queue")
        if outreach_agent:
            dashboard = outreach_agent._dashboard
            archive_result = await _archive_skipped_items(db, dashboard)
            stats["archive_skipped"] = archive_result
            logger.info("Archive skipped done: %s", archive_result)

        # ── Step 5: Daily digest (timestamp-gated) ──────────────────
        if _should_run_digest():
            logger.info("Step 5: Daily digest")
            digest_stats = await _get_digest_stats(db)
            digest_sent = await _send_daily_digest(
                digest_stats, channel, bot_token, dry_run=dry_run
            )
            stats["digest"] = {
                "sent": digest_sent,
                "stats": digest_stats,
            }
            if digest_sent or dry_run:
                DIGEST_LAST_RUN_FILE.write_text(datetime.now(timezone.utc).isoformat())
            logger.info("Daily digest done: sent=%s", digest_sent)
        else:
            stats["digest"] = {"skipped": "too_recent"}
            logger.info("Step 5: Daily digest skipped (too recent)")

    finally:
        await n8n_client.__aexit__(None, None, None)
        await db.close()

    stats["completed_at"] = datetime.now(timezone.utc).isoformat()
    return stats


async def main() -> None:
    dry_run = "--dry-run" in sys.argv

    # Acquire file lock
    lock = CronLock(LOCK_FILE)
    if not lock.acquire():
        logger.warning("Another instance is running, exiting")
        sys.exit(0)

    try:
        logger.info("Outreach cron started (dry_run=%s)", dry_run)
        stats = await run_pipeline(dry_run=dry_run)
        logger.info("Outreach cron completed: %s", stats)

        # Write last-run timestamp
        LAST_RUN_FILE.write_text(datetime.now(timezone.utc).isoformat())

    except Exception as e:
        logger.exception("Outreach cron failed: %s", e)

        # Best-effort Slack failure alert
        from cmo_agent.config import Settings

        settings = Settings()
        await _send_failure_alert(
            settings.slack_outreach_channel,
            settings.slack_bot_token,
            str(e),
        )
        sys.exit(1)

    finally:
        lock.release()


if __name__ == "__main__":
    asyncio.run(main())
