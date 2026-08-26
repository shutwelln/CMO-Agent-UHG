"""Batch-update category_id in local guide draft JSON files.

Run this AFTER migrate_guide_categories.py to sync local cache with DB.
Reads the final category IDs from Supabase and updates each JSON draft.

Usage:
  python scripts/update_draft_categories.py [--dry-run]
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

DRY_RUN = "--dry-run" in sys.argv
DRAFTS_DIR = project_root / "data" / "saverwell" / "guide_drafts"

client = httpx.Client(timeout=30)


def main() -> None:
    if DRY_RUN:
        print("=== DRY RUN MODE ===\n")

    # Fetch article slug -> category_id from DB (source of truth after migration)
    print("Fetching articles from Supabase...")
    resp = client.get(
        f"{SUPABASE_URL}/rest/v1/guide_articles",
        headers=HEADERS,
        params={"select": "slug,category_id", "limit": "500"},
    )
    resp.raise_for_status()
    articles = resp.json()
    slug_to_cat_id = {a["slug"]: a["category_id"] for a in articles}
    print(f"  Found {len(slug_to_cat_id)} articles in DB")

    # Also fetch category_id -> slug for category_slug updates
    resp = client.get(
        f"{SUPABASE_URL}/rest/v1/guide_categories",
        headers=HEADERS,
        params={"select": "id,slug"},
    )
    resp.raise_for_status()
    categories = resp.json()
    cat_id_to_slug = {c["id"]: c["slug"] for c in categories}

    # Process each JSON draft
    updated = 0
    skipped = 0
    json_files = sorted(DRAFTS_DIR.glob("*.json"))
    print(f"  Found {len(json_files)} JSON draft files\n")

    for json_path in json_files:
        slug = json_path.stem
        if slug not in slug_to_cat_id:
            skipped += 1
            continue

        data = json.loads(json_path.read_text())
        new_cat_id = slug_to_cat_id[slug]
        old_cat_id = data.get("category_id")
        changed = False

        if old_cat_id != new_cat_id:
            data["category_id"] = new_cat_id
            changed = True

        # Update category_slug if present
        new_cat_slug = cat_id_to_slug.get(new_cat_id)
        if new_cat_slug and data.get("category_slug") != new_cat_slug:
            data["category_slug"] = new_cat_slug
            changed = True

        # Update email_cta_url if category changed
        if changed and new_cat_slug:
            expected_url = f"/guides/{new_cat_slug}/{slug}"
            if data.get("email_cta_url") != expected_url:
                data["email_cta_url"] = expected_url

        if changed:
            if DRY_RUN:
                print(f"  [DRY] {slug}: category_id {old_cat_id} -> {new_cat_id}")
            else:
                json_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
                print(f"  UPDATED: {slug}: category_id {old_cat_id} -> {new_cat_id}")
            updated += 1

    print(f"\nUpdated: {updated}, Skipped (not in DB): {skipped}")
    print("Done!")


if __name__ == "__main__":
    main()
