#!/usr/bin/env python3
"""One-time scan & repair for proofreader-corrupted fields in Supabase.

The proofreader bug stored raw JSON (```json fences or {"corrected_text":...})
into article fields instead of clean markdown. This script:
  1. Fetches ALL articles from Supabase guide_articles
  2. Checks all 12 proofread fields for corruption patterns
  3. Attempts to extract clean text from the corrupted JSON
  4. Falls back to the local JSON cache if available
  5. Upserts fixed fields back to Supabase
  6. Reports all fixes and any needing manual review

Usage:
    python scripts/fix_corrupted_articles.py                # scan + fix
    python scripts/fix_corrupted_articles.py --dry-run      # scan only, no writes
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402

logger = structlog.get_logger()

GUIDE_DRAFTS_DIR = _PROJECT_ROOT / "data" / "saverwell" / "guide_drafts"

PROOFREAD_FIELDS = [
    "title",
    "subtitle",
    "overview_md",
    "key_takeaways_md",
    "body_md",
    "savings_tips_md",
    "watch_out_md",
    "faq_md",
    "email_subject",
    "email_preheader",
    "email_intro_md",
    "thumbnail_alt",
]


def is_corrupted(value: str) -> bool:
    """Check if a field value contains raw proofreader JSON."""
    if not value or not value.strip():
        return False
    stripped = value.strip()
    # Fenced JSON block
    if stripped.startswith("```"):
        return True
    # Raw JSON object with proofreader keys
    if stripped.startswith("{") and (
        '"corrected_text"' in stripped[:300] or '"corrections"' in stripped[:300]
    ):
        return True
    return False


def extract_clean_text(corrupted: str) -> Optional[str]:
    """Try to extract the corrected_text from corrupted JSON."""
    stripped = corrupted.strip()

    # Remove fences if present
    defenced = stripped
    if defenced.startswith("```"):
        # Remove opening fence
        defenced = re.sub(r"^```(?:json)?\s*\n?", "", defenced)
        # Remove closing fence if present
        defenced = re.sub(r"\n?```\s*$", "", defenced)

    # Try parsing as JSON
    try:
        parsed = json.loads(defenced)
        if isinstance(parsed, dict) and "corrected_text" in parsed:
            return parsed["corrected_text"]
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting corrected_text value with regex (handles truncated JSON)
    match = re.search(r'"corrected_text"\s*:\s*"((?:[^"\\]|\\.)*)"', defenced, re.DOTALL)
    if match:
        try:
            # Unescape JSON string
            return json.loads(f'"{match.group(1)}"')
        except (json.JSONDecodeError, TypeError):
            return match.group(1)

    return None


def load_local_field(slug: str, field: str) -> Optional[str]:
    """Load a field value from the local JSON cache."""
    local_path = GUIDE_DRAFTS_DIR / f"{slug}.json"
    if not local_path.exists():
        return None
    try:
        data = json.loads(local_path.read_text())
        value = data.get(field)
        if value and isinstance(value, str) and not is_corrupted(value):
            return value
    except (json.JSONDecodeError, KeyError):
        pass
    return None


async def fetch_all_articles(settings: Settings) -> List[Dict[str, Any]]:
    """Fetch all articles with proofread fields from Supabase."""
    select_fields = ",".join(["slug"] + PROOFREAD_FIELDS)
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            f"{settings.supabase_url}/rest/v1/guide_articles",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            params={
                "select": select_fields,
                "order": "slug",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def upsert_fixes(
    settings: Settings,
    slug: str,
    fixes: Dict[str, str],
) -> bool:
    """Upsert fixed fields back to Supabase."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.patch(
            f"{settings.supabase_url}/rest/v1/guide_articles",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={"slug": f"eq.{slug}"},
            json=fixes,
        )
        return resp.status_code < 300


def fix_local_cache(slug: str, fixes: Dict[str, str]) -> bool:
    """Fix the local JSON cache file."""
    local_path = GUIDE_DRAFTS_DIR / f"{slug}.json"
    if not local_path.exists():
        return False
    try:
        data = json.loads(local_path.read_text())
        data.update(fixes)
        local_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return True
    except Exception:
        return False


async def main() -> None:
    parser = argparse.ArgumentParser(description="Scan & repair corrupted article fields")
    parser.add_argument("--dry-run", action="store_true", help="Scan only, no writes")
    args = parser.parse_args()

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
        sys.exit(1)

    print("Fetching all articles from Supabase...")
    articles = await fetch_all_articles(settings)
    print(f"Found {len(articles)} articles\n")

    total_corrupted = 0
    total_fixed = 0
    manual_review: List[Tuple[str, str]] = []
    fixed_slugs: List[Tuple[str, List[str]]] = []

    for art in articles:
        slug = art.get("slug", "unknown")
        fixes: Dict[str, str] = {}

        for field in PROOFREAD_FIELDS:
            value = art.get(field)
            if not value or not isinstance(value, str):
                continue

            if not is_corrupted(value):
                continue

            total_corrupted += 1
            print(f"  CORRUPTED: {slug}.{field} ({len(value)} chars)")
            print(f"    Preview: {value[:100]}...")

            # Try to extract clean text from the JSON
            clean = extract_clean_text(value)
            if clean and not is_corrupted(clean):
                fixes[field] = clean
                print(f"    -> Extracted clean text ({len(clean)} chars)")
                continue

            # Fall back to local cache
            local_val = load_local_field(slug, field)
            if local_val:
                fixes[field] = local_val
                print(f"    -> Using local cache ({len(local_val)} chars)")
                continue

            # Can't fix automatically
            manual_review.append((slug, field))
            print("    -> NEEDS MANUAL REVIEW")

        if fixes:
            fixed_fields = list(fixes.keys())
            if args.dry_run:
                print(f"  [DRY RUN] Would fix {len(fixes)} fields for {slug}")
            else:
                ok = await upsert_fixes(settings, slug, fixes)
                if ok:
                    total_fixed += len(fixes)
                    print(f"  Fixed {len(fixes)} fields in Supabase")
                else:
                    print(f"  ERROR: Supabase upsert failed for {slug}")
                    manual_review.extend((slug, f) for f in fixed_fields)
                    continue

                # Also fix local cache
                fix_local_cache(slug, fixes)

            fixed_slugs.append((slug, fixed_fields))

    # Summary
    print("\n" + "=" * 60)
    print("CORRUPTION SCAN RESULTS")
    print("=" * 60)
    print(f"Articles scanned:  {len(articles)}")
    print(f"Corrupted fields:  {total_corrupted}")
    print(f"Fixed fields:      {total_fixed}")
    print(f"Manual review:     {len(manual_review)}")

    if fixed_slugs:
        print("\nFixed articles:")
        for slug, fields in fixed_slugs:
            print(f"  {slug}: {', '.join(fields)}")

    if manual_review:
        print("\nNeeding manual review:")
        for slug, field in manual_review:
            print(f"  {slug}.{field}")

    if args.dry_run:
        print("\n[DRY RUN] No changes were made. Run without --dry-run to apply fixes.")


if __name__ == "__main__":
    asyncio.run(main())
