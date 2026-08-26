"""Backfill page_slug for all active merchants with NULL page_slug.

Generates slugs using: name -> lowercase -> strip apostrophes -> replace non-alnum
with hyphens -> collapse multiple hyphens -> strip leading/trailing hyphens ->
append "-senior-discount". Detects duplicates and appends -{id} to resolve.
"""
from __future__ import annotations

import os
import re
import sys

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}


def slugify(name: str) -> str:
    """Convert merchant name to URL slug, e.g. "McDonald's" -> "mcdonalds-senior-discount"."""
    s = name.lower()
    s = s.replace("'", "").replace("\u2019", "")  # strip apostrophes
    s = re.sub(r"[^a-z0-9]+", "-", s)  # non-alnum -> hyphen
    s = re.sub(r"-{2,}", "-", s)  # collapse multiple hyphens
    s = s.strip("-")
    return f"{s}-senior-discount"


def main() -> None:
    client = httpx.Client(timeout=30)

    # 1. Fetch all active merchants with NULL page_slug
    #    Supabase REST uses "is.null" filter for NULL columns
    url = f"{SUPABASE_URL}/rest/v1/merchants"
    params = {
        "select": "id,name",
        "page_slug": "is.null",
        "is_active": "eq.true",
        "order": "id.asc",
        "limit": "5000",
    }
    resp = client.get(url, headers=HEADERS, params=params)
    resp.raise_for_status()
    merchants = resp.json()
    print(f"Found {len(merchants)} merchants with NULL page_slug")

    if not merchants:
        print("Nothing to do.")
        return

    # 2. Also fetch existing slugs to detect collisions
    existing_resp = client.get(
        url,
        headers=HEADERS,
        params={
            "select": "id,page_slug",
            "page_slug": "not.is.null",
            "limit": "5000",
        },
    )
    existing_resp.raise_for_status()
    existing_slugs: set[str] = {
        row["page_slug"] for row in existing_resp.json() if row.get("page_slug")
    }
    print(f"Existing slugs in DB: {len(existing_slugs)}")

    # 3. Generate slugs, detect duplicates within this batch + existing
    slug_map: dict[str, list[dict]] = {}  # slug -> [merchant rows]
    for m in merchants:
        slug = slugify(m["name"])
        slug_map.setdefault(slug, []).append(m)

    updates: list[tuple[int, str]] = []
    for slug, rows in slug_map.items():
        if len(rows) == 1 and slug not in existing_slugs:
            updates.append((rows[0]["id"], slug))
        else:
            # Duplicate slug - append -id to all
            for row in rows:
                deduped = f"{slug}-{row['id']}"
                updates.append((row["id"], deduped))

    print(f"Will update {len(updates)} merchants")

    # 4. PATCH each merchant
    success = 0
    errors = 0
    for merchant_id, slug in updates:
        patch_url = f"{SUPABASE_URL}/rest/v1/merchants?id=eq.{merchant_id}"
        patch_resp = client.patch(patch_url, headers=HEADERS, json={"page_slug": slug})
        if patch_resp.status_code in (200, 204):
            success += 1
        else:
            print(f"  ERROR patching id={merchant_id} slug={slug}: {patch_resp.status_code} {patch_resp.text}")
            errors += 1

    print(f"Done: {success} updated, {errors} errors")


if __name__ == "__main__":
    main()
