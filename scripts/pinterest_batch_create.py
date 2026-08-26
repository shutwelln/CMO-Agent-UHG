#!/usr/bin/env python3
"""Batch create Pinterest pins from guide articles.

Reads published articles from Supabase and generates pin content
(copy + optional images) to data/pinterest/ready/.

Usage:
    python scripts/pinterest_batch_create.py                    # copy only
    python scripts/pinterest_batch_create.py --with-images      # copy + images
    python scripts/pinterest_batch_create.py --limit 10
    python scripts/pinterest_batch_create.py --slug medicare-explained-simple-guide
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx
import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402
from cmo_agent.pinterest.pin_generator import PinterestPinGenerator  # noqa: E402

logger = structlog.get_logger()

OUTPUT_DIR = _PROJECT_ROOT / "data" / "pinterest" / "ready"


async def fetch_articles(
    settings: Settings,
    slug: str = "",
    limit: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch published guide articles from Supabase."""
    params: Dict[str, str] = {
        "select": "slug,title,overview_md,key_takeaways_md,seo_keywords,tags,vertical",
        "publish_web": "eq.true",
        "order": "slug",
    }
    if slug:
        params["slug"] = f"eq.{slug}"
    if limit:
        params["limit"] = str(limit)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{settings.supabase_url}/rest/v1/guide_articles",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            params=params,
        )
        resp.raise_for_status()
        return resp.json()


# Vertical → category slug mapping (for board assignment)
_VERTICAL_TO_CATEGORY: Dict[str, str] = {
    "1A-medicare": "medicare",
    "1B-insurance": "insurance",
    "2A-medical-alerts": "senior-products",
    "2B-phones": "senior-products",
    "2C-hearing-aids": "senior-products",
    "3A-finance": "retirement-taxes",
    "5-protection": "protection",
    "6-discounts": "saving-money",
    "7-caregiving": "caregiving",
}


async def main() -> None:
    parser = argparse.ArgumentParser(description="Batch create Pinterest pins")
    parser.add_argument("--slug", type=str, default="", help="Single article slug")
    parser.add_argument("--limit", type=int, default=0, help="Max articles to process")
    parser.add_argument("--with-images", action="store_true", help="Also generate pin images")
    args = parser.parse_args()

    settings = Settings()

    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY required")
        sys.exit(1)

    # Fetch articles
    articles = await fetch_articles(settings, slug=args.slug, limit=args.limit)
    print(f"Found {len(articles)} articles")

    # Skip articles that already have pins
    to_process = []
    for art in articles:
        pin_dir = OUTPUT_DIR / art["slug"]
        if (pin_dir / "copy.json").exists():
            print(f"  Skipping {art['slug']} (already has pin)")
            continue
        to_process.append(art)

    print(f"Pins to create: {len(to_process)}")
    if not to_process:
        print("Nothing to do.")
        return

    generator = PinterestPinGenerator(
        anthropic_api_key=settings.anthropic_api_key,
        writing_model=settings.llm_model_writing,
    )

    created = 0
    failed = 0

    for i, art in enumerate(to_process, 1):
        slug = art["slug"]
        vertical = art.get("vertical", "6-discounts")
        category = _VERTICAL_TO_CATEGORY.get(vertical, "saving-money")

        print(f"\n[{i}/{len(to_process)}] {slug}")

        result = await generator.generate_and_save(
            article=art,
            category_slug=category,
            generate_image=args.with_images,
        )

        if result:
            created += 1
            print(f"  OK (image: {'yes' if result.get('image') else 'no'})")
        else:
            failed += 1
            print("  FAILED")

        if i < len(to_process):
            await asyncio.sleep(1.0)

    print(f"\nDone. Created: {created} | Failed: {failed}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
