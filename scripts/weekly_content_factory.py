#!/usr/bin/env python3
"""Automated Content Factory — weekly orchestrator.

Chains together existing tools into an end-to-end pipeline:
  1. Topic gap detection (scanner data vs. article inventory)
  2. Auto-generate article briefs from gaps
  3. Content generation (LLM + refinement + proofread)
  4. Thumbnail generation (Gemini)
  5. Cross-linking update
  6. Content queue sheet update (Article Library)
  7. Google indexing request
  8. Slack summary

Designed to run every Sunday evening so new content is live before
Tuesday's broadcast email.

Usage:
    python scripts/weekly_content_factory.py                  # full run
    python scripts/weekly_content_factory.py --dry-run        # detect gaps, skip publish
    python scripts/weekly_content_factory.py --max-articles 3 # limit new articles
    python scripts/weekly_content_factory.py --skip-thumbnails
    python scripts/weekly_content_factory.py --skip-indexing
    python scripts/weekly_content_factory.py --include-revisions  # also revise existing articles
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

# Ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

from cmo_agent.config import Settings  # noqa: E402
from cmo_agent.content.topic_gap import GapBrief, TopicGapDetector  # noqa: E402

logger = structlog.get_logger()

# ── Constants ────────────────────────────────────────────────────────────────

LEAD_SCANNER_SHEET_ID = "1xnphzSpso_htOP1qX21B1zxx_R-Kvy99MrZ5Jfq2XAA"
CONTENT_QUEUE_SHEET_ID = "1kSVQwjzXO1R9af55DPSTmhq86ZH12u1ra3fcoll1-xE"
SLACK_CHANNEL = "#saverwell-opportunities"

# Category slug → category_id mapping (from Supabase guide_categories)
CATEGORY_IDS: Dict[str, int] = {
    "medicare": 1,
    "insurance": 2,
    "retirement-taxes": 8,
    "saving-money": 9,
    "caregiving": 10,
    "senior-products": 11,
    "protection": 12,
}


@dataclass
class FactoryResult:
    """Tracks the results of a content factory run."""

    gaps_detected: List[GapBrief] = field(default_factory=list)
    articles_generated: List[str] = field(default_factory=list)  # slugs
    articles_failed: List[str] = field(default_factory=list)
    thumbnails_generated: List[str] = field(default_factory=list)
    thumbnails_failed: List[str] = field(default_factory=list)
    cross_links_updated: int = 0
    articles_queued: int = 0
    indexing_submitted: List[str] = field(default_factory=list)
    revisions: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


# ── Google Sheets helper ─────────────────────────────────────────────────────


def _get_sheets_service() -> Any:
    """Build an authenticated Google Sheets service."""
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import get_google_credentials

    oauth_path = str(_PROJECT_ROOT / "data" / "google-token.json")
    sa_path = str(_PROJECT_ROOT / "data" / "saverwell-google-credentials.json")
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    credentials = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path=sa_path,
        scopes=scopes,
    )
    if credentials is None:
        raise RuntimeError("Could not load Google credentials")
    return build("sheets", "v4", credentials=credentials)


# ── Step 1: Topic Gap Detection ──────────────────────────────────────────────


async def step_1_detect_gaps(
    settings: Settings,
    max_gaps: int = 3,
    min_score: int = 7,
) -> List[GapBrief]:
    """Read scanner data, compare against inventory, detect gaps."""
    print("\n=== Step 1: Topic Gap Detection ===")

    detector = TopicGapDetector(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
        anthropic_api_key=settings.anthropic_api_key,
        scanning_model=settings.llm_model_scanning,
    )

    # Fetch article inventory from Supabase
    print("  Fetching article inventory from Supabase...")
    inventory = await detector.fetch_article_inventory()
    print(f"  Found {len(inventory)} published articles")

    # Read scanner leads from Google Sheet
    print("  Reading scanner leads from Google Sheet...")
    sheets_service = _get_sheets_service()
    leads = await detector.read_scanner_leads(
        sheets_service,
        LEAD_SCANNER_SHEET_ID,
        min_score=min_score,
    )
    print(f"  Found {len(leads)} leads scoring {min_score}+")

    if not leads:
        print("  No high-scoring leads found. Skipping gap detection.")
        return []

    # LLM gap analysis
    print(f"  Running LLM gap analysis (max {max_gaps} gaps)...")
    gaps = await detector.detect_gaps(leads, inventory, max_gaps=max_gaps)

    for i, gap in enumerate(gaps, 1):
        print(f"  Gap {i}: {gap.topic}")
        print(f"    Slug: {gap.slug}")
        print(f"    Category: {gap.category} | Vertical: {gap.vertical}")
        print(f"    Keywords: {', '.join(gap.keywords[:5])}")
        print(f"    Frequency: {gap.frequency} | Monetization: {gap.monetization_signal}")

    return gaps


# ── Step 2 & 3: Generate Articles ───────────────────────────────────────────


async def step_2_3_generate_articles(
    settings: Settings,
    gaps: List[GapBrief],
    dry_run: bool = False,
) -> tuple[List[str], List[str]]:
    """Convert gaps to briefs and generate articles."""
    print("\n=== Steps 2-3: Brief Generation + Content Generation ===")

    if not gaps:
        print("  No gaps to generate articles for.")
        return [], []

    # Import the generation function
    from generate_guide_content import generate_single_guide

    detector = TopicGapDetector(
        supabase_url=settings.supabase_url,
        supabase_key=settings.supabase_service_role_key,
        anthropic_api_key=settings.anthropic_api_key,
    )

    generated: List[str] = []
    failed: List[str] = []

    for i, gap in enumerate(gaps, 1):
        print(f"\n  [{i}/{len(gaps)}] Generating: {gap.slug}")

        # Convert gap to topic brief
        category_id = CATEGORY_IDS.get(gap.category, 5)
        brief = detector.gap_to_topic_brief(gap, category_id=category_id)

        t0 = time.time()
        try:
            payload = await generate_single_guide(
                topic_brief=brief,
                settings=settings,
                publish=not dry_run,
            )
            elapsed = time.time() - t0

            if payload:
                generated.append(gap.slug)
                score = payload.get("review_score", "?")
                print(f"    OK (score={score}, {elapsed:.1f}s)")
            else:
                failed.append(gap.slug)
                print(f"    FAILED ({elapsed:.1f}s)")
        except Exception as e:
            elapsed = time.time() - t0
            failed.append(gap.slug)
            print(f"    ERROR: {e} ({elapsed:.1f}s)")
            logger.error("content_factory_generation_error", slug=gap.slug, error=str(e))

        # Pause between articles
        if i < len(gaps):
            await asyncio.sleep(2.0)

    print(f"\n  Generated: {len(generated)} | Failed: {len(failed)}")
    return generated, failed


# ── Step 4: Thumbnail Generation ────────────────────────────────────────────


async def step_4_thumbnails(
    settings: Settings,
    slugs: List[str],
    provider: str = "gemini",
) -> tuple[List[str], List[str]]:
    """Generate thumbnails for new articles."""
    print("\n=== Step 4: Thumbnail Generation ===")

    if not slugs:
        print("  No articles to generate thumbnails for.")
        return [], []

    from generate_article_thumbnails import generate_for_slugs

    print(f"  Generating thumbnails for {len(slugs)} articles (provider: {provider})...")
    results = await generate_for_slugs(
        slugs=slugs,
        table="guide_articles",
        provider=provider,
        settings=settings,
    )

    generated = [s for s, ok in results.items() if ok]
    failed = [s for s, ok in results.items() if not ok]

    print(f"  Thumbnails: {len(generated)} OK, {len(failed)} failed")
    return generated, failed


# ── Step 5: Cross-Linking ────────────────────────────────────────────────────


async def step_5_cross_links(settings: Settings) -> int:
    """Update internal cross-links across all articles."""
    print("\n=== Step 5: Cross-Linking ===")

    import httpx

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    base = settings.supabase_url

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{base}/rest/v1/guide_articles",
            headers=headers,
            params={
                "select": "id,slug,title,category_id,related_slugs",
                "publish_web": "eq.true",
            },
        )
        resp.raise_for_status()
        guides = resp.json()

    all_slugs = {g["slug"] for g in guides}
    cat_to_slugs: Dict[int, List[str]] = {}
    for g in guides:
        cat_to_slugs.setdefault(g["category_id"], []).append(g["slug"])

    updates = []
    for g in guides:
        slug = g["slug"]
        raw_related = g.get("related_slugs") or []
        if isinstance(raw_related, str):
            raw_related = json.loads(raw_related)

        valid = [s for s in raw_related if s in all_slugs and s != slug]

        if len(valid) < 2:
            cat_id = g["category_id"]
            candidates = [
                s for s in cat_to_slugs.get(cat_id, []) if s != slug and s not in valid
            ]
            valid.extend(candidates[: 2 - len(valid)])

        if len(valid) < 2:
            all_others = [s for s in all_slugs if s != slug and s not in valid]
            valid.extend(all_others[: 2 - len(valid)])

        valid = valid[:3]

        if valid != raw_related:
            updates.append({"id": g["id"], "slug": slug, "related_slugs": valid})

    if not updates:
        print("  No cross-link updates needed.")
        return 0

    async with httpx.AsyncClient(timeout=30) as client:
        for u in updates:
            resp = await client.patch(
                f"{base}/rest/v1/guide_articles",
                headers=headers,
                params={"id": f"eq.{u['id']}"},
                json={"related_slugs": u["related_slugs"]},
            )
            resp.raise_for_status()

    # Update local JSON cache
    drafts_dir = _PROJECT_ROOT / "data" / "saverwell" / "guide_drafts"
    for u in updates:
        cache_path = drafts_dir / f"{u['slug']}.json"
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
            data["related_slugs"] = u["related_slugs"]
            cache_path.write_text(json.dumps(data, indent=2))

    print(f"  Updated cross-links for {len(updates)} articles")
    return len(updates)


# ── Step 6: Content Queue Update ─────────────────────────────────────────────


def step_6_content_queue(
    slugs: List[str],
    gap_briefs: List[GapBrief],
) -> int:
    """Add new articles to the Content Queue Article Library tab."""
    print("\n=== Step 6: Content Queue Update ===")

    if not slugs:
        print("  No new articles to add to content queue.")
        return 0

    from populate_content_queue import append_new_articles

    # Build article dicts for the content queue
    gap_map = {g.slug: g for g in gap_briefs}
    articles = []
    for slug in slugs:
        gap = gap_map.get(slug)
        articles.append(
            {
                "slug": slug,
                "title": gap.topic if gap else slug,
                "vertical": gap.vertical if gap else "6-discounts",
                "category_slug": gap.category if gap else "saving-money",
                "monetization_type": gap.monetization_signal if gap else "informational",
                "affiliate_disclosure": False,
                "base_priority": min(gap.frequency + 3, 10) if gap else 5,
            }
        )

    count = append_new_articles(articles, sheet_id=CONTENT_QUEUE_SHEET_ID)
    return count


# ── Step 7: Google Indexing ──────────────────────────────────────────────────


def step_7_indexing(slugs: List[str]) -> List[str]:
    """Request Google to crawl and index new article pages."""
    print("\n=== Step 7: Google Indexing ===")

    if not slugs:
        print("  No articles to submit for indexing.")
        return []

    from submit_url_inspection import get_credentials, SITE_URL, INSPECTION_DELAY

    try:
        creds = get_credentials(["https://www.googleapis.com/auth/webmasters"])
        from googleapiclient.discovery import build

        service = build("searchconsole", "v1", credentials=creds)
    except Exception as e:
        print(f"  WARNING: Could not initialize Search Console API: {e}")
        return []

    submitted: List[str] = []

    for slug in slugs:
        # Determine the article URL
        # Guide articles follow /guides/{category}/{slug} pattern
        url = f"https://saverwell.com/guides/{slug}"

        try:
            service.urlInspection().index().inspect(
                body={
                    "inspectionUrl": url,
                    "siteUrl": SITE_URL,
                }
            ).execute()
            submitted.append(slug)
            print(f"  Submitted: {url}")
        except Exception as e:
            err_str = str(e)[:200]
            print(f"  ERROR: {url} - {err_str}")
            if "quota" in err_str.lower() or "rate" in err_str.lower():
                print("  Rate limited. Stopping indexing submissions.")
                break

        import time

        time.sleep(INSPECTION_DELAY)

    print(f"  Submitted {len(submitted)} URLs for indexing")
    return submitted


# ── Step 8: Slack Summary ────────────────────────────────────────────────────


async def step_8_slack_summary(
    settings: Settings,
    result: FactoryResult,
) -> None:
    """Post a weekly content factory summary to Slack."""
    print("\n=== Step 8: Slack Summary ===")

    if not settings.slack_bot_token:
        print("  No Slack bot token configured. Skipping Slack summary.")
        return

    try:
        from slack_sdk.web.async_client import AsyncWebClient

        client = AsyncWebClient(token=settings.slack_bot_token)
    except ImportError:
        print("  slack_sdk not installed. Skipping Slack summary.")
        return

    # Build summary message
    lines = [":factory: *Weekly Content Factory Report*\n"]

    if result.gaps_detected:
        lines.append(f"*Topic Gaps Detected:* {len(result.gaps_detected)}")
        for gap in result.gaps_detected:
            lines.append(f"  - {gap.topic} (frequency: {gap.frequency})")
        lines.append("")

    if result.articles_generated:
        lines.append(f"*Articles Created:* {len(result.articles_generated)}")
        for slug in result.articles_generated:
            url = f"https://saverwell.com/guides/{slug}"
            lines.append(f"  - <{url}|{slug}>")
        lines.append("")

    if result.articles_failed:
        lines.append(f"*Articles Failed:* {len(result.articles_failed)}")
        for slug in result.articles_failed:
            lines.append(f"  - {slug}")
        lines.append("")

    if result.thumbnails_generated:
        lines.append(f"*Thumbnails:* {len(result.thumbnails_generated)} generated")

    if result.cross_links_updated:
        lines.append(f"*Cross-links Updated:* {result.cross_links_updated}")

    if result.articles_queued:
        lines.append(f"*Content Queue:* {result.articles_queued} articles added to email pipeline")

    if result.indexing_submitted:
        lines.append(f"*Indexing:* {len(result.indexing_submitted)} URLs submitted to Google")

    if result.revisions:
        lines.append(f"*Revisions:* {len(result.revisions)} articles updated")

    if result.errors:
        lines.append(f"\n:warning: *Errors:* {len(result.errors)}")
        for err in result.errors[:5]:
            lines.append(f"  - {err}")

    lines.append(f"\n_Elapsed: {result.elapsed_seconds:.0f}s_")

    text = "\n".join(lines)

    try:
        await client.chat_postMessage(
            channel=SLACK_CHANNEL,
            text=text,
            unfurl_links=False,
        )
        print("  Slack summary posted.")
    except Exception as e:
        print(f"  WARNING: Could not post Slack summary: {e}")


# ── Optional: Article Revision (Part 3) ─────────────────────────────────────


async def step_optional_revisions(
    settings: Settings,
    max_revisions: int = 2,
) -> List[str]:
    """Detect and apply article revisions based on scanner intelligence."""
    print("\n=== Optional: Article Revisions ===")

    try:
        from cmo_agent.content.article_reviser import ArticleReviser

        reviser = ArticleReviser(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_role_key,
            anthropic_api_key=settings.anthropic_api_key,
        )

        # Read scanner leads
        sheets_service = _get_sheets_service()
        from cmo_agent.content.topic_gap import TopicGapDetector

        detector = TopicGapDetector(
            supabase_url=settings.supabase_url,
            supabase_key=settings.supabase_service_role_key,
            anthropic_api_key=settings.anthropic_api_key,
        )
        leads = await detector.read_scanner_leads(
            sheets_service,
            LEAD_SCANNER_SHEET_ID,
            min_score=7,
        )

        # Get article inventory
        inventory = await detector.fetch_article_inventory()

        # Find mismatches
        mismatches = await reviser.find_mismatches(leads, inventory, max_revisions=max_revisions)

        revised: List[str] = []
        for mismatch in mismatches:
            slug = mismatch.get("slug", "")
            print(f"  Revising: {slug}")
            try:
                ok = await reviser.revise_article(mismatch, settings)
                if ok:
                    revised.append(slug)
                    print(f"    OK")
                else:
                    print(f"    FAILED")
            except Exception as e:
                print(f"    ERROR: {e}")

        return revised

    except ImportError:
        print("  ArticleReviser not available. Skipping revisions.")
        return []
    except Exception as e:
        print(f"  ERROR in revisions: {e}")
        return []


# ── Main Orchestrator ────────────────────────────────────────────────────────


async def run_content_factory(
    max_articles: int = 2,
    dry_run: bool = False,
    skip_thumbnails: bool = False,
    skip_indexing: bool = False,
    include_revisions: bool = False,
    thumbnail_provider: str = "gemini",
    min_score: int = 7,
) -> FactoryResult:
    """Run the full content factory pipeline."""
    t0 = time.time()
    result = FactoryResult()
    settings = Settings()

    # Validate configuration
    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        result.errors.append("Missing ANTHROPIC_API_KEY")
        return result

    if not dry_run and (not settings.supabase_url or not settings.supabase_service_role_key):
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required (or use --dry-run)")
        result.errors.append("Missing Supabase credentials")
        return result

    print("=" * 60)
    print("WEEKLY CONTENT FACTORY")
    print("=" * 60)
    print(f"Mode: {'DRY RUN' if dry_run else 'PRODUCTION'}")
    print(f"Max articles: {max_articles}")
    print(f"Thumbnail provider: {thumbnail_provider}")

    # Step 1: Detect topic gaps
    try:
        gaps = await step_1_detect_gaps(settings, max_gaps=max_articles, min_score=min_score)
        result.gaps_detected = gaps
    except Exception as e:
        print(f"  ERROR in gap detection: {e}")
        result.errors.append(f"Gap detection: {e}")
        gaps = []

    # Steps 2-3: Generate articles
    if gaps:
        try:
            generated, failed = await step_2_3_generate_articles(settings, gaps, dry_run=dry_run)
            result.articles_generated = generated
            result.articles_failed = failed
        except Exception as e:
            print(f"  ERROR in article generation: {e}")
            result.errors.append(f"Article generation: {e}")

    # Step 4: Thumbnails
    if result.articles_generated and not skip_thumbnails and not dry_run:
        try:
            thumb_ok, thumb_fail = await step_4_thumbnails(
                settings, result.articles_generated, provider=thumbnail_provider
            )
            result.thumbnails_generated = thumb_ok
            result.thumbnails_failed = thumb_fail
        except Exception as e:
            print(f"  ERROR in thumbnail generation: {e}")
            result.errors.append(f"Thumbnails: {e}")

    # Step 5: Cross-linking
    if result.articles_generated and not dry_run:
        try:
            result.cross_links_updated = await step_5_cross_links(settings)
        except Exception as e:
            print(f"  ERROR in cross-linking: {e}")
            result.errors.append(f"Cross-linking: {e}")

    # Step 6: Content queue
    if result.articles_generated and not dry_run:
        try:
            result.articles_queued = step_6_content_queue(
                result.articles_generated, result.gaps_detected
            )
        except Exception as e:
            print(f"  ERROR in content queue update: {e}")
            result.errors.append(f"Content queue: {e}")

    # Step 7: Indexing
    if result.articles_generated and not skip_indexing and not dry_run:
        try:
            result.indexing_submitted = step_7_indexing(result.articles_generated)
        except Exception as e:
            print(f"  ERROR in indexing: {e}")
            result.errors.append(f"Indexing: {e}")

    # Optional: Article revisions
    if include_revisions and not dry_run:
        try:
            result.revisions = await step_optional_revisions(settings)
        except Exception as e:
            print(f"  ERROR in revisions: {e}")
            result.errors.append(f"Revisions: {e}")

    # Step 8: Slack summary
    result.elapsed_seconds = time.time() - t0
    if not dry_run:
        try:
            await step_8_slack_summary(settings, result)
        except Exception as e:
            print(f"  ERROR in Slack summary: {e}")
            result.errors.append(f"Slack summary: {e}")

    # Final report
    print("\n" + "=" * 60)
    print("CONTENT FACTORY COMPLETE")
    print("=" * 60)
    print(f"Gaps detected:       {len(result.gaps_detected)}")
    print(f"Articles generated:  {len(result.articles_generated)}")
    print(f"Articles failed:     {len(result.articles_failed)}")
    print(f"Thumbnails:          {len(result.thumbnails_generated)}")
    print(f"Cross-links updated: {result.cross_links_updated}")
    print(f"Content queue adds:  {result.articles_queued}")
    print(f"Indexing submitted:  {len(result.indexing_submitted)}")
    print(f"Revisions:           {len(result.revisions)}")
    print(f"Errors:              {len(result.errors)}")
    print(f"Elapsed:             {result.elapsed_seconds:.0f}s")

    if result.errors:
        print("\nErrors:")
        for err in result.errors:
            print(f"  - {err}")

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Automated Content Factory — weekly orchestrator"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Detect gaps and generate content, but skip publishing/indexing",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=2,
        help="Maximum new articles to generate per run (default: 2)",
    )
    parser.add_argument(
        "--skip-thumbnails",
        action="store_true",
        help="Skip thumbnail generation step",
    )
    parser.add_argument(
        "--skip-indexing",
        action="store_true",
        help="Skip Google indexing submission step",
    )
    parser.add_argument(
        "--include-revisions",
        action="store_true",
        help="Also run the article revision pipeline",
    )
    parser.add_argument(
        "--thumbnail-provider",
        choices=["dalle", "gemini", "imagen4"],
        default="gemini",
        help="Image generation provider for thumbnails (default: gemini)",
    )
    parser.add_argument(
        "--min-score",
        type=int,
        default=7,
        help="Minimum scanner lead score to consider (default: 7)",
    )
    args = parser.parse_args()

    await run_content_factory(
        max_articles=args.max_articles,
        dry_run=args.dry_run,
        skip_thumbnails=args.skip_thumbnails,
        skip_indexing=args.skip_indexing,
        include_revisions=args.include_revisions,
        thumbnail_provider=args.thumbnail_provider,
        min_score=args.min_score,
    )


if __name__ == "__main__":
    asyncio.run(main())
