#!/usr/bin/env python3
"""One-time backfill: scan WhatToExpect forums from Jan 1, 2026 to today.

Deep-paginates all configured WTE forums, applies search term filtering,
scoring, risk assessment, post-type classification, gender inference, and
draft reply generation. Results go to the Review Queue tab on the outreach
Google Sheet (outreach_status='review').

Uses the full agent stack so all pipeline logic matches the regular cron.

Usage:
    python scripts/backfill_wte.py
    python scripts/backfill_wte.py --max-pages 50   # limit pages per forum
    python scripts/backfill_wte.py --dry-run         # scan only, no Sheet sync
"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── Logging ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("backfill_wte")

WORKSPACE_ID = "dsdn"
CUTOFF_DATE = "2026-01-01"
DEFAULT_MAX_PAGES = 100  # pages per forum, ~20 topics per page


async def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Backfill WhatToExpect outreach scan")
    parser.add_argument(
        "--max-pages", type=int, default=DEFAULT_MAX_PAGES,
        help=f"Max listing pages to scan per forum (default {DEFAULT_MAX_PAGES})",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Scan and store to DB but skip Google Sheet sync",
    )
    args = parser.parse_args()

    from cmo_agent.agents.factory import AgentFactory
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database
    from cmo_agent.n8n.client import N8NClient

    settings = Settings()
    if not settings.outreach_enabled:
        logger.info("OUTREACH_ENABLED=false, exiting")
        return

    # ── Boot agent stack ───────────────────────────────────────────
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

        scanner = registry.get("outreach_scanner_agent")
        if not scanner:
            logger.error("outreach_scanner_agent not found in registry")
            return

        # ── Step 1: Sync search terms ─────────────────────────────
        logger.info("Step 1: Syncing search terms from Google Sheet...")
        sync_result = await scanner.process_message(
            "Sync search terms from the Google Sheet to the database.",
            workspace_id=WORKSPACE_ID,
        )
        logger.info("Search terms synced: %s", sync_result.status)

        # ── Step 2: Deep-paginate WTE forums ──────────────────────
        logger.info(
            "Step 2: Scanning WTE (max_pages=%d, cutoff=%s)...",
            args.max_pages, CUTOFF_DATE,
        )
        wte_result = await scanner._scan_whattoexpect(
            WORKSPACE_ID,
            max_pages=args.max_pages,
            cutoff_date=CUTOFF_DATE,
            route_to_review=True,
        )
        logger.info(
            "WTE scan complete: scanned=%d new=%d errors=%s",
            wte_result.get("scanned", 0),
            wte_result.get("new", 0),
            wte_result.get("errors", []),
        )

        if wte_result.get("new", 0) == 0:
            logger.info("No new posts found. Checking if there are unprocessed review items...")

        # ── Step 3: Risk assessment for all unrated items ─────────
        logger.info("Step 3: Batch risk assessment...")
        risk_count = await scanner._batch_assess_risk(WORKSPACE_ID)
        logger.info("Risk assessments completed: %d", risk_count)

        # ── Step 4: Classify + draft + gender inference ───────────
        logger.info("Step 4: Classify post types, infer gender, generate draft replies...")
        subgroup_keywords = await scanner._dashboard.read_subgroup_keywords()
        classified = await scanner._batch_classify_and_draft(
            WORKSPACE_ID, subgroup_keywords=subgroup_keywords,
        )
        logger.info("Classified and drafted: %d items", classified)

        # ── Step 5: Sync Review Queue to Google Sheet ─────────────
        if not args.dry_run:
            logger.info("Step 5: Syncing Review Queue to Google Sheet...")
            review_result = await scanner._sync_review_queue(
                WORKSPACE_ID, subgroup_keywords,
            )
            logger.info("Review Queue sync: %s", review_result)
        else:
            logger.info("Step 5: SKIPPED (--dry-run)")
            review_result = {"status": "dry_run"}

        # ── Summary ───────────────────────────────────────────────
        from cmo_agent.agents.outreach_scanner import _WTE_FORUM_SLUGS

        print(f"\n{'='*60}")
        print("WhatToExpect Backfill Complete!")
        print(f"  Forums scanned: {len(_WTE_FORUM_SLUGS)}")
        print(f"  Pages per forum: up to {args.max_pages}")
        print(f"  Cutoff date: {CUTOFF_DATE}")
        print(f"  Threads scanned: {wte_result.get('scanned', 0)}")
        print(f"  New posts found: {wte_result.get('new', 0)}")
        print(f"  Risk assessments: {risk_count}")
        print(f"  Classified/drafted: {classified}")
        print(f"  Review Queue sync: {review_result.get('status', 'n/a')}")
        if review_result.get("review_queue_synced"):
            print(f"  Rows added to Review Queue: {review_result['review_queue_synced']}")
        if wte_result.get("errors"):
            print(f"  Errors: {wte_result['errors']}")
        print(f"{'='*60}")

    finally:
        await n8n_client.__aexit__(None, None, None)
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
