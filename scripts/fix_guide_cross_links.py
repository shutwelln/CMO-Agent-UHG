#!/usr/bin/env python3
"""Fix guide_articles related_slugs to only reference existing guides.

For each guide, filters out non-existent slugs from related_slugs,
then backfills from same-category guides to ensure 2-3 cross-links.
Updates both local JSON cache and Supabase.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cmo_agent.config import Settings


async def main() -> None:
    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required")
        sys.exit(1)

    import httpx

    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    base = settings.supabase_url

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch all published guides
        resp = await client.get(
            f"{base}/rest/v1/guide_articles",
            headers=headers,
            params={"select": "id,slug,title,category_id,related_slugs", "publish_web": "eq.true"},
        )
        resp.raise_for_status()
        guides = resp.json()

    all_slugs = {g["slug"] for g in guides}
    slug_to_guide = {g["slug"]: g for g in guides}
    cat_to_slugs: dict[int, list[str]] = {}
    for g in guides:
        cat_to_slugs.setdefault(g["category_id"], []).append(g["slug"])

    print(f"Found {len(guides)} published guides across {len(cat_to_slugs)} categories")
    print(f"Categories: {', '.join(f'{cid}: {len(slugs)} guides' for cid, slugs in sorted(cat_to_slugs.items()))}")

    updates = []
    for g in guides:
        slug = g["slug"]
        raw_related = g.get("related_slugs") or []
        if isinstance(raw_related, str):
            raw_related = json.loads(raw_related)

        # Filter to only existing slugs (exclude self)
        valid = [s for s in raw_related if s in all_slugs and s != slug]

        # Backfill from same category if < 2
        if len(valid) < 2:
            cat_id = g["category_id"]
            candidates = [s for s in cat_to_slugs.get(cat_id, []) if s != slug and s not in valid]
            needed = 2 - len(valid)
            valid.extend(candidates[:needed])

        # Still short? Pull from any category
        if len(valid) < 2:
            all_others = [s for s in all_slugs if s != slug and s not in valid]
            needed = 2 - len(valid)
            valid.extend(all_others[:needed])

        # Cap at 3
        valid = valid[:3]

        if valid != raw_related:
            removed = set(raw_related) - set(valid) - {slug}
            added = set(valid) - set(raw_related)
            print(f"\n{slug}:")
            if removed:
                print(f"  removed: {', '.join(sorted(removed))}")
            if added:
                print(f"  added:   {', '.join(sorted(added))}")
            print(f"  result:  {valid}")
            updates.append({"id": g["id"], "slug": slug, "related_slugs": valid})

    if not updates:
        print("\nNo updates needed!")
        return

    print(f"\n--- Updating {len(updates)} guides in Supabase ---")

    async with httpx.AsyncClient(timeout=30) as client:
        for u in updates:
            resp = await client.patch(
                f"{base}/rest/v1/guide_articles",
                headers=headers,
                params={"id": f"eq.{u['id']}"},
                json={"related_slugs": u["related_slugs"]},
            )
            resp.raise_for_status()
            print(f"  updated: {u['slug']}")

    # Also update local JSON cache
    drafts_dir = Path("data/saverwell/guide_drafts")
    for u in updates:
        cache_path = drafts_dir / f"{u['slug']}.json"
        if cache_path.exists():
            data = json.loads(cache_path.read_text())
            data["related_slugs"] = u["related_slugs"]
            cache_path.write_text(json.dumps(data, indent=2))

    print(f"\nDone! Updated {len(updates)} guides.")


if __name__ == "__main__":
    asyncio.run(main())
