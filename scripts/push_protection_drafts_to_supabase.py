"""Push local SQLite protection_article drafts to Supabase.

Reads drafts with content_type='protection_article' from the local DB,
maps category_slug → category_id via Supabase protection_categories,
and upserts into Supabase public.protection_articles.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

import httpx

# Ensure project root is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ── Category lookup ──────────────────────────────────────────────────────

def fetch_category_map(base_url: str, headers: dict) -> dict[str, int]:
    """Fetch protection_categories from Supabase and return {slug: id}."""
    resp = httpx.get(
        f"{base_url}/rest/v1/protection_categories?select=id,slug",
        headers=headers,
    )
    resp.raise_for_status()
    return {row["slug"]: row["id"] for row in resp.json()}


# ── Main ─────────────────────────────────────────────────────────────────

async def main() -> None:
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database

    settings = Settings()

    # Validate Supabase credentials
    supabase_url = settings.supabase_url.rstrip("/")
    supabase_key = settings.supabase_service_role_key
    if not supabase_url or not supabase_key:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
        sys.exit(1)

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }

    # 1. Fetch category map from Supabase
    cat_map = fetch_category_map(supabase_url, headers)
    print(f"Category map: {cat_map}")

    # 2. Read protection_article drafts from local SQLite
    db = Database(settings.db_path)
    await db.initialize()

    rows = await db.fetchall(
        "SELECT id, body FROM drafts "
        "WHERE content_type = 'protection_article' "
        "ORDER BY created_at ASC"
    )
    await db.close()

    if not rows:
        print("No protection_article drafts found in local DB.")
        sys.exit(0)

    print(f"Found {len(rows)} protection_article drafts in SQLite.\n")

    # 3. Build Supabase payloads
    payloads = []
    for row in rows:
        draft_id = row["id"]
        body_json = json.loads(row["body"])

        category_slug = body_json.get("category_slug", "scams")
        category_id = cat_map.get(category_slug)
        if category_id is None:
            print(f"  WARNING: Unknown category_slug '{category_slug}' for draft {draft_id}, defaulting to 'scams'")
            category_id = cat_map["scams"]

        payload = {
            "slug": body_json["slug"],
            "title": body_json["title"],
            "subtitle": body_json.get("subtitle", ""),
            "category_id": category_id,
            "status": "draft",
            "publish_web": False,
            "publish_email": False,
            "source": "fraudwatch_pdf",
            "source_ref": f"sqlite_draft:{draft_id}",
            "tags": body_json.get("tags", []),
            "channel_tags": body_json.get("channel_tags", []),
            "scam_type_tags": body_json.get("scam_type_tags", []),
            "intent_tags": body_json.get("intent_tags", []),
            "reading_minutes": body_json.get("reading_minutes", 5),
            "overview_md": body_json.get("overview_md", ""),
            "red_flags_md": body_json.get("red_flags_md", ""),
            "what_to_do_md": body_json.get("what_to_do_md", ""),
            "prevention_md": body_json.get("prevention_md", ""),
            "phone_script_md": body_json.get("phone_script_md", ""),
            "resources_md": body_json.get("resources_md", ""),
            "body_md": body_json.get("body_md", ""),
            "email_subject": body_json.get("email_subject", ""),
            "email_preheader": body_json.get("email_preheader", ""),
            "email_intro_md": body_json.get("email_intro_md", ""),
            "email_cta_label": body_json.get("email_cta_label", "Read full guide"),
            "email_cta_url": body_json.get("email_cta_url", ""),
        }
        payloads.append(payload)
        print(f"  Prepared: {payload['slug']}  (category_id={category_id}, source_ref=sqlite_draft:{draft_id[:12]}...)")

    # 4. Upsert to Supabase (batch POST with on_conflict=slug)
    print(f"\nUpserting {len(payloads)} rows to Supabase protection_articles...")
    upsert_headers = {
        **headers,
        "Prefer": "return=representation,resolution=merge-duplicates",
    }

    resp = httpx.post(
        f"{supabase_url}/rest/v1/protection_articles?on_conflict=slug",
        headers=upsert_headers,
        json=payloads,
        timeout=30.0,
    )

    if resp.status_code not in (200, 201):
        print(f"\nERROR: Supabase upsert failed (HTTP {resp.status_code})")
        print(resp.text)
        sys.exit(1)

    upserted = resp.json()
    print(f"Upserted {len(upserted)} rows successfully.\n")

    # 5. Verify: count and list
    print("=" * 70)
    print("VERIFICATION")
    print("=" * 70)

    count_resp = httpx.get(
        f"{supabase_url}/rest/v1/protection_articles?source=eq.fraudwatch_pdf&select=id",
        headers={**headers, "Prefer": "count=exact"},
    )
    count_resp.raise_for_status()
    total = count_resp.headers.get("content-range", "")
    print(f"\nTotal protection_articles where source='fraudwatch_pdf': {total}")

    verify_resp = httpx.get(
        f"{supabase_url}/rest/v1/protection_articles"
        "?source=eq.fraudwatch_pdf"
        "&select=slug,status,publish_web,publish_email,source,source_ref"
        "&order=slug.asc",
        headers=headers,
    )
    verify_resp.raise_for_status()
    for art in verify_resp.json():
        print(f"  slug={art['slug']:<50s} status={art['status']}  web={art['publish_web']}  email={art['publish_email']}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
