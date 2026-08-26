"""Push manually corrected merchant page JSON files to Supabase."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

DRAFTS_DIR = Path(__file__).resolve().parent.parent / "data" / "saverwell" / "merchant_page_drafts"

# Page content fields to push (excludes non-DB fields like merchant_id, name)
PAGE_FIELDS = [
    "page_slug", "page_direct_answer", "page_hero_headline", "page_hero_subhead",
    "page_about_md", "page_how_to_save_md", "page_tips_md",
    "page_faq_md", "page_faq_json", "page_protection_note_md",
    "page_related_protection_slugs", "page_related_guide_slugs",
    "page_related_merchant_ids", "page_seo_title", "page_seo_description",
    "page_seo_keywords", "page_status", "page_source", "page_author",
    "page_review_score", "page_review_notes", "page_updated_at",
]

# Files to push: (slug, merchant_id)
CORRECTIONS = [
    ("adidas-senior-discount", 3761),
    ("firestone-complete-auto-care-senior-discount", 876),
    ("bp-senior-discount", 3802),
]


def main() -> None:
    for slug, mid in CORRECTIONS:
        path = DRAFTS_DIR / f"{slug}.json"
        if not path.exists():
            print(f"SKIP: {path} not found")
            continue

        data = json.loads(path.read_text())
        payload = {k: data[k] for k in PAGE_FIELDS if k in data}

        resp = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/merchants?id=eq.{mid}",
            headers=HEADERS,
            json=payload,
            timeout=15,
        )
        if resp.status_code not in (200, 204):
            print(f"FAILED [{mid}] {slug}: {resp.status_code} {resp.text[:200]}")
            continue

        print(f"Pushed [{mid}] {slug}")

    print("Done.")


if __name__ == "__main__":
    main()
