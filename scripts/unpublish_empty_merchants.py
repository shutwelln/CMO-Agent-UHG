#!/usr/bin/env python3
"""
Unpublish merchant pages that have no content.

Approximately 1,733 merchants have page_slug set and page_status='published'
but zero content (page_hero_headline is NULL or empty). These were bulk-created
with slugs only. This script sets them back to page_status='draft' so they
don't appear in the sitemap or on the live site.

Usage:
    python scripts/unpublish_empty_merchants.py --dry-run   # preview
    python scripts/unpublish_empty_merchants.py              # apply
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def fetch_empty_published(client: httpx.Client) -> List[Dict[str, Any]]:
    """Fetch merchants that are published but have no page content."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000

    while True:
        resp = client.get(
            f"{SUPABASE_URL}/rest/v1/merchants",
            headers=HEADERS,
            params={
                "select": "id,name,page_slug,page_status,page_hero_headline",
                "page_status": "eq.published",
                "page_slug": "neq.",
                "or": "(page_hero_headline.is.null,page_hero_headline.eq.)",
                "limit": str(page_size),
                "offset": str(offset),
            },
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return rows


def unpublish_batch(
    client: httpx.Client, ids: List[int]
) -> int:
    """Set page_status='draft' for a batch of merchant IDs.

    Uses a single PATCH with in-filter for efficiency.
    Returns count of successfully updated rows.
    """
    # Supabase REST API supports in-filter: id=in.(1,2,3)
    batch_size = 100
    updated = 0

    for i in range(0, len(ids), batch_size):
        chunk = ids[i : i + batch_size]
        id_list = ",".join(str(mid) for mid in chunk)
        resp = client.patch(
            f"{SUPABASE_URL}/rest/v1/merchants",
            headers=HEADERS,
            params={"id": f"in.({id_list})"},
            json={"page_status": "draft"},
        )
        if resp.status_code in (200, 204):
            updated += len(chunk)
        else:
            print(f"  ERROR batch {i}-{i+len(chunk)}: HTTP {resp.status_code}")

    return updated


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Unpublish merchant pages with no content"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to DB",
    )
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    print("=" * 70)
    print("  Unpublish Empty Merchant Pages")
    print("=" * 70)
    print(f"  Dry run: {args.dry_run}")
    print()

    with httpx.Client(timeout=30) as client:
        print("Fetching published merchants with no content ...")
        empty_rows = fetch_empty_published(client)
        print(f"  Found {len(empty_rows)} empty published merchants")

        if not empty_rows:
            print("\nNo empty published merchants found. Nothing to do.")
            return

        # Show sample
        print("\n  Sample (first 10):")
        for row in empty_rows[:10]:
            name = row.get("name", "?")
            slug = row.get("page_slug", "?")
            print(f"    id={row['id']}  {name}  ({slug})")
        if len(empty_rows) > 10:
            print(f"    ... and {len(empty_rows) - 10} more")

        if args.dry_run:
            print(f"\n  [DRY RUN] Would set page_status='draft' for {len(empty_rows)} merchants")
        else:
            print(f"\n  Setting page_status='draft' for {len(empty_rows)} merchants ...")
            ids = [row["id"] for row in empty_rows]
            updated = unpublish_batch(client, ids)
            print(f"  Updated: {updated}")

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Empty published found: {len(empty_rows)}")
    if args.dry_run:
        print("  (DRY RUN - no changes written)")
    print()

    # Verification
    print("Verification query (run in Supabase SQL Editor):")
    print("  SELECT COUNT(*) FROM merchants")
    print("    WHERE page_status = 'published'")
    print("    AND (page_hero_headline IS NULL OR page_hero_headline = '');")
    print("  -- Expected: 0")
    print()
    print("  SELECT COUNT(*) FROM merchants")
    print("    WHERE page_status = 'published'")
    print("    AND page_hero_headline IS NOT NULL AND page_hero_headline != '';")
    print("  -- Expected: 66")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
