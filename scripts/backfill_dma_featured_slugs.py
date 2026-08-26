#!/usr/bin/env python3
"""Backfill DMA featured_guide_slugs with diverse guide selection.

Currently every DMA has the same 2 guide slugs. This script expands each
DMA to 4-5 guides via round-robin rotation through popular published guides,
creating more unique cross-link patterns for crawl signals.

Usage:
    python scripts/backfill_dma_featured_slugs.py              # full run
    python scripts/backfill_dma_featured_slugs.py --dry-run    # preview changes
    python scripts/backfill_dma_featured_slugs.py --limit 10   # first N DMAs
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402

# Popular guides to rotate through (must be published with publish_web=true)
GUIDE_ROTATION_POOL = [
    "medicare-explained-simple-guide",
    "save-money-medicare-premiums",
    "medicare-parts-a-b-c-d-explained",
    "dental-insurance-seniors",
    "medical-alert-systems-guide",
    "when-to-claim-social-security",
    "cell-phone-plans-seniors",
    "tax-deductions-seniors-over-65",
    "auto-home-insurance-seniors",
    "life-insurance-seniors-over-65",
    "medicare-enrollment-deadlines",
    "does-medicare-cover-hearing-aids",
]

GUIDES_PER_DMA = 5


async def fetch_dmas(settings: Settings) -> List[Dict[str, Any]]:
    """Fetch all published DMAs."""
    async with httpx.AsyncClient(timeout=30.0) as http:
        resp = await http.get(
            f"{settings.supabase_url}/rest/v1/dma_page_content",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            params={
                "select": "id,slug,display_name,featured_guide_slugs",
                "status": "eq.published",
                "order": "slug.asc",
                "limit": "500",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_published_guide_slugs(settings: Settings) -> set[str]:
    """Fetch slugs of all published guides to validate rotation pool."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.get(
            f"{settings.supabase_url}/rest/v1/guide_articles",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            params={
                "select": "slug",
                "publish_web": "eq.true",
                "limit": "500",
            },
        )
        resp.raise_for_status()
        return {r["slug"] for r in resp.json()}


async def update_featured_slugs(
    settings: Settings, dma_id: int, slugs: List[str]
) -> bool:
    """Update featured_guide_slugs for a DMA."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.patch(
            f"{settings.supabase_url}/rest/v1/dma_page_content",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=minimal",
            },
            params={"id": f"eq.{dma_id}"},
            json={"featured_guide_slugs": slugs},
        )
        return resp.status_code in (200, 204)


async def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill DMA featured guide slugs")
    parser.add_argument("--dry-run", action="store_true", help="Preview without updating")
    parser.add_argument("--limit", type=int, default=0, help="Limit DMAs to process")
    args = parser.parse_args()

    settings = Settings()
    print("Fetching published guides...")
    published = await fetch_published_guide_slugs(settings)

    # Filter rotation pool to only published guides
    valid_pool = [s for s in GUIDE_ROTATION_POOL if s in published]
    print(f"Valid guide pool: {len(valid_pool)}/{len(GUIDE_ROTATION_POOL)} guides published")
    if len(valid_pool) < 3:
        print("ERROR: Need at least 3 published guides in rotation pool")
        sys.exit(1)

    print("Fetching DMAs...")
    dmas = await fetch_dmas(settings)
    if args.limit:
        dmas = dmas[: args.limit]
    print(f"Processing {len(dmas)} DMAs")

    updated = 0
    skipped = 0
    errors = 0

    for i, dma in enumerate(dmas):
        # Round-robin: offset into the pool by DMA index
        start = (i * GUIDES_PER_DMA) % len(valid_pool)
        slugs = []
        for j in range(GUIDES_PER_DMA):
            idx = (start + j) % len(valid_pool)
            slugs.append(valid_pool[idx])
        # Deduplicate while preserving order
        seen: set[str] = set()
        unique_slugs = []
        for s in slugs:
            if s not in seen:
                seen.add(s)
                unique_slugs.append(s)

        current = dma.get("featured_guide_slugs") or []
        if isinstance(current, str):
            try:
                current = json.loads(current)
            except (json.JSONDecodeError, TypeError):
                current = []

        if set(current) == set(unique_slugs):
            skipped += 1
            continue

        if args.dry_run:
            print(f"  [DRY RUN] {dma['slug']}: {current} -> {unique_slugs}")
            updated += 1
            continue

        ok = await update_featured_slugs(settings, dma["id"], unique_slugs)
        if ok:
            updated += 1
            if updated % 20 == 0:
                print(f"  Updated {updated} DMAs...")
        else:
            errors += 1
            print(f"  ERROR updating {dma['slug']}")

    print(f"\nDone: {updated} updated, {skipped} skipped (already correct), {errors} errors")


if __name__ == "__main__":
    asyncio.run(main())
