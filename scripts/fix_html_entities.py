"""
Fix HTML entities (&amp; &lt; &gt; &#39; &quot; etc.) in Supabase merchants
and discounts_v2 tables.

Dry-run scan first, then apply with confirmation.
"""

import html
import json
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

MERCHANTS_URL = f"{SUPABASE_URL}/rest/v1/merchants"
DISCOUNTS_URL = f"{SUPABASE_URL}/rest/v1/discounts_v2"

# Fields to check in each table
MERCHANT_TEXT_FIELDS = [
    "name",
    "default_discount_text",
    "default_discount_details",
    "page_hero_headline",
    "page_hero_subhead",
    "page_about_md",
]

DISCOUNT_TEXT_FIELDS = [
    "name",
    "details",
]

# Regex to detect any HTML entity
HTML_ENTITY_RE = re.compile(r"&(?:#\d+|#x[0-9a-fA-F]+|[a-zA-Z]+);")


def slugify(name: str) -> str:
    """Convert merchant name to URL slug (matches backfill_page_slugs.py)."""
    s = name.lower()
    s = s.replace("'", "").replace("\u2019", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return f"{s}-senior-discount"


def fetch_all(client: httpx.Client, url: str, params: dict) -> list:
    """Fetch all rows with Range pagination."""
    all_rows = []
    offset = 0
    page_size = 1000
    while True:
        hdrs = {**HEADERS, "Range": f"{offset}-{offset + page_size - 1}"}
        resp = client.get(url, params=params, headers=hdrs)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return all_rows


def has_html_entity(value: str) -> bool:
    """Check if a string contains any HTML entity."""
    return bool(HTML_ENTITY_RE.search(value))


def scan_table(client, url, fields, id_field="id"):
    """Scan a table for HTML entities in specified fields. Returns list of fixes."""
    select = f"{id_field},{','.join(fields)}"
    rows = fetch_all(client, url, {"select": select})
    fixes = []
    for row in rows:
        row_fixes = {}
        for field in fields:
            val = row.get(field)
            if val and isinstance(val, str) and has_html_entity(val):
                cleaned = html.unescape(val)
                if cleaned != val:
                    row_fixes[field] = {"old": val, "new": cleaned}
        if row_fixes:
            fixes.append({"id": row[id_field], "fields": row_fixes})
    return fixes


def main():
    client = httpx.Client(timeout=30)

    # ── STEP 1: Scan merchants ────────────────────────────────────────────
    print("=" * 70)
    print("STEP 1: Scanning merchants table for HTML entities")
    print("=" * 70)

    # Also fetch page_slug so we can recalculate if name changes
    select = f"id,page_slug,{','.join(MERCHANT_TEXT_FIELDS)}"
    merchant_rows = fetch_all(client, MERCHANTS_URL, {"select": select})
    merchant_fixes = []
    for row in merchant_rows:
        row_fixes = {}
        for field in MERCHANT_TEXT_FIELDS:
            val = row.get(field)
            if val and isinstance(val, str) and has_html_entity(val):
                cleaned = html.unescape(val)
                if cleaned != val:
                    row_fixes[field] = {"old": val, "new": cleaned}
        if row_fixes:
            # If name changed, recalculate slug
            slug_fix = None
            if "name" in row_fixes:
                old_slug = row.get("page_slug")
                new_slug = slugify(row_fixes["name"]["new"])
                if old_slug and old_slug != new_slug:
                    slug_fix = {"old": old_slug, "new": new_slug}
            merchant_fixes.append({
                "id": row["id"],
                "fields": row_fixes,
                "slug_fix": slug_fix,
            })

    if not merchant_fixes:
        print("\n  No HTML entities found in merchants table.")
    else:
        print(f"\n  Found {len(merchant_fixes)} merchants with HTML entities:\n")
        for fix in merchant_fixes:
            print(f"  Merchant ID {fix['id']}:")
            for field, change in fix["fields"].items():
                old_preview = change["old"][:80]
                new_preview = change["new"][:80]
                print(f"    {field}: {old_preview!r}")
                print(f"        -> {new_preview!r}")
            if fix.get("slug_fix"):
                print(f"    page_slug: {fix['slug_fix']['old']!r}")
                print(f"           -> {fix['slug_fix']['new']!r}")

    # ── STEP 2: Scan discounts_v2 ─────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 2: Scanning discounts_v2 table for HTML entities")
    print("=" * 70)

    discount_fixes = scan_table(client, DISCOUNTS_URL, DISCOUNT_TEXT_FIELDS)

    if not discount_fixes:
        print("\n  No HTML entities found in discounts_v2 table.")
    else:
        print(f"\n  Found {len(discount_fixes)} discounts with HTML entities:\n")
        for fix in discount_fixes:
            print(f"  Discount ID {fix['id']}:")
            for field, change in fix["fields"].items():
                print(f"    {field}: {change['old'][:80]!r}")
                print(f"        -> {change['new'][:80]!r}")

    # ── STEP 3: Confirm and apply ──────────────────────────────────────────
    total = len(merchant_fixes) + len(discount_fixes)
    if total == 0:
        print("\nNothing to fix. Done.")
        client.close()
        return

    print("\n" + "=" * 70)
    print(f"READY TO FIX: {len(merchant_fixes)} merchants + {len(discount_fixes)} discounts")
    print("=" * 70)
    answer = input("\nApply fixes? (yes/no): ").strip().lower()
    if answer != "yes":
        print("Aborted.")
        client.close()
        return

    # ── Apply merchant fixes ───────────────────────────────────────────────
    m_ok, m_fail = 0, 0
    for fix in merchant_fixes:
        payload = {field: change["new"] for field, change in fix["fields"].items()}
        if fix.get("slug_fix"):
            payload["page_slug"] = fix["slug_fix"]["new"]
        resp = client.patch(
            MERCHANTS_URL,
            params={"id": f"eq.{fix['id']}"},
            headers=HEADERS,
            content=json.dumps(payload),
        )
        if resp.status_code in (200, 204):
            m_ok += 1
            print(f"  [OK] Merchant {fix['id']}: {list(payload.keys())}")
        else:
            m_fail += 1
            print(f"  [FAIL] Merchant {fix['id']}: HTTP {resp.status_code} {resp.text[:200]}")

    # ── Apply discount fixes ───────────────────────────────────────────────
    d_ok, d_fail = 0, 0
    for fix in discount_fixes:
        payload = {field: change["new"] for field, change in fix["fields"].items()}
        resp = client.patch(
            DISCOUNTS_URL,
            params={"id": f"eq.{fix['id']}"},
            headers=HEADERS,
            content=json.dumps(payload),
        )
        if resp.status_code in (200, 204):
            d_ok += 1
            print(f"  [OK] Discount {fix['id']}: {list(payload.keys())}")
        else:
            d_fail += 1
            print(f"  [FAIL] Discount {fix['id']}: HTTP {resp.status_code} {resp.text[:200]}")

    # ── Summary ────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Merchants: {m_ok} fixed, {m_fail} failed")
    print(f"  Discounts: {d_ok} fixed, {d_fail} failed")
    print("Done.")
    client.close()


if __name__ == "__main__":
    main()
