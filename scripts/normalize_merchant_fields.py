"""
Normalize merchant_type and default_discount_type values in the Supabase merchants table.

Ensures consistent Title Case for merchant_type and standardized discount type values.
"""

import os
import json
from collections import Counter
from dotenv import load_dotenv
import httpx

# Load .env from project root
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BASE = f"{SUPABASE_URL}/rest/v1/merchants"

# Words that stay lowercase in title case (unless they are the first word)
LOWERCASE_WORDS = {"and", "or", "the", "a", "an", "in", "on", "at", "to", "for", "of", "with"}


def smart_title_case(s: str) -> str:
    """Title case that keeps conjunctions/prepositions lowercase (except first word)."""
    words = s.strip().split()
    result = []
    for i, word in enumerate(words):
        if i == 0:
            result.append(word.capitalize())
        elif word.lower() in LOWERCASE_WORDS:
            result.append(word.lower())
        else:
            result.append(word.capitalize())
    return " ".join(result)


def fetch_all_pages(client: httpx.Client, url: str, params: dict) -> list:
    """Fetch all rows using Range pagination (Supabase caps at 1000 per request)."""
    all_rows = []
    offset = 0
    page_size = 1000
    while True:
        headers = {**HEADERS, "Range": f"{offset}-{offset + page_size - 1}"}
        resp = client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return all_rows


def main():
    client = httpx.Client(timeout=30)
    changes_log = []

    # ── STEP 1: Audit merchant_type ──────────────────────────────────────
    print("=" * 70)
    print("STEP 1: Auditing merchant_type values for active merchants")
    print("=" * 70)

    rows = fetch_all_pages(
        client, BASE,
        {"is_active": "eq.true", "merchant_type": "not.is.null", "select": "id,merchant_type"},
    )
    mt_counter = Counter(r["merchant_type"] for r in rows)
    print(f"\nTotal active merchants with merchant_type: {len(rows)}")
    print(f"Unique values: {len(mt_counter)}")
    for val, count in mt_counter.most_common():
        print(f"  {val!r:30s} -> {count}")

    # ── STEP 2: Plan merchant_type normalization (Smart Title Case) ──────
    print("\n" + "=" * 70)
    print("STEP 2: Planning merchant_type normalization -> Smart Title Case")
    print("=" * 70)

    # Group by smart-title-case target
    target_map: dict[str, list[str]] = {}  # target -> [original values that differ]
    for val in mt_counter:
        target = smart_title_case(val)
        if val != target:
            target_map.setdefault(target, []).append(val)

    if not target_map:
        print("\nAll merchant_type values are already Title Case. Nothing to fix.")
    else:
        print("\nPlanned normalizations:")
        for target, originals in sorted(target_map.items()):
            for orig in originals:
                print(f"  {orig!r} ({mt_counter[orig]} rows) -> {target!r}")

    # ── STEP 3: Apply merchant_type patches ──────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 3: Applying merchant_type patches")
    print("=" * 70)

    for target, originals in sorted(target_map.items()):
        for orig in originals:
            count = mt_counter[orig]
            print(f"\n  Patching {orig!r} -> {target!r} ({count} rows)...")
            resp = client.patch(
                BASE,
                params={"is_active": "eq.true", "merchant_type": f"eq.{orig}"},
                headers=HEADERS,
                content=json.dumps({"merchant_type": target}),
            )
            resp.raise_for_status()
            patched = resp.json()
            print(f"    Updated {len(patched)} rows")
            changes_log.append({
                "field": "merchant_type",
                "from": orig,
                "to": target,
                "rows_updated": len(patched),
            })

    # ── STEP 4: Audit default_discount_type ──────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 4: Auditing default_discount_type values for active merchants")
    print("=" * 70)

    rows = fetch_all_pages(
        client, BASE,
        {
            "is_active": "eq.true",
            "default_discount_type": "not.is.null",
            "select": "id,default_discount_type",
        },
    )
    ddt_counter = Counter(r["default_discount_type"] for r in rows)
    print(f"\nTotal active merchants with default_discount_type: {len(rows)}")
    print(f"Unique values: {len(ddt_counter)}")
    for val, count in ddt_counter.most_common():
        print(f"  {val!r:30s} -> {count}")

    # ── STEP 5: Plan default_discount_type normalization ─────────────────
    print("\n" + "=" * 70)
    print("STEP 5: Planning default_discount_type normalization")
    print("=" * 70)

    STANDARD = "In-store"
    LEAVE_ALONE = {"percentage", "In-store and Online", STANDARD}

    ddt_fixes: dict[str, str] = {}
    for val in ddt_counter:
        if val in LEAVE_ALONE:
            reason = {
                STANDARD: "already the standard",
                "percentage": "honeypot rows (intentionally different)",
                "In-store and Online": "legitimate variant",
            }.get(val, "known exception")
            print(f"  SKIP {val!r} ({ddt_counter[val]} rows) - {reason}")
        else:
            ddt_fixes[val] = STANDARD
            print(f"  FIX  {val!r} ({ddt_counter[val]} rows) -> {STANDARD!r}")

    if not ddt_fixes:
        print("\n  No default_discount_type fixes needed.")

    # ── STEP 6: Apply default_discount_type patches ──────────────────────
    if ddt_fixes:
        print("\n" + "=" * 70)
        print("STEP 6: Applying default_discount_type patches")
        print("=" * 70)

        for orig, target in ddt_fixes.items():
            count = ddt_counter[orig]
            print(f"\n  Patching {orig!r} -> {target!r} ({count} rows)...")
            resp = client.patch(
                BASE,
                params={"is_active": "eq.true", "default_discount_type": f"eq.{orig}"},
                headers=HEADERS,
                content=json.dumps({"default_discount_type": target}),
            )
            resp.raise_for_status()
            patched = resp.json()
            print(f"    Updated {len(patched)} rows")
            changes_log.append({
                "field": "default_discount_type",
                "from": orig,
                "to": target,
                "rows_updated": len(patched),
            })

    # ── STEP 7: Verify final state ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 7: Verification - final unique values")
    print("=" * 70)

    print("\nmerchant_type (after normalization):")
    rows = fetch_all_pages(
        client, BASE,
        {"is_active": "eq.true", "merchant_type": "not.is.null", "select": "id,merchant_type"},
    )
    for val, count in Counter(r["merchant_type"] for r in rows).most_common():
        print(f"  {val!r:30s} -> {count}")

    print("\ndefault_discount_type (after normalization):")
    rows = fetch_all_pages(
        client, BASE,
        {
            "is_active": "eq.true",
            "default_discount_type": "not.is.null",
            "select": "id,default_discount_type",
        },
    )
    for val, count in Counter(r["default_discount_type"] for r in rows).most_common():
        print(f"  {val!r:30s} -> {count}")

    # ── STEP 8: Summary ─────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    if changes_log:
        print(f"\nTotal changes applied: {len(changes_log)}")
        total_rows = sum(c["rows_updated"] for c in changes_log)
        print(f"Total rows updated:    {total_rows}")
        print()
        for c in changes_log:
            print(f"  [{c['field']}] {c['from']!r} -> {c['to']!r} ({c['rows_updated']} rows)")
    else:
        print("\nNo changes were needed. All values already normalized.")

    print("\nLeft alone (by design):")
    print("  default_discount_type='percentage' - honeypot rows, intentionally different")
    print("  default_discount_type='In-store and Online' - legitimate variant")
    print("\nDone.")
    client.close()


if __name__ == "__main__":
    main()
