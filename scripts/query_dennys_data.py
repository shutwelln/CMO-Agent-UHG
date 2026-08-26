"""Query Supabase for all Denny's merchant and discount data."""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

PLACEHOLDER_PATTERN = re.compile(r"replace", re.IGNORECASE)

MERCHANT_FIELDS = (
    "id,name,default_discount_value,default_discount_text,"
    "default_discount_requirement,default_discount_type,"
    "is_national,is_active,category_id,page_slug,page_status"
)

DISCOUNT_FIELDS = (
    "id,merchant_id,name,discount_value,details,"
    "requirement,discount_type,store_location_id"
)


def check_placeholders(label: str, row: dict) -> list[str]:
    """Return list of flagged fields containing placeholder text."""
    flags = []
    for key, val in row.items():
        if isinstance(val, str) and PLACEHOLDER_PATTERN.search(val):
            flags.append(f"  *** PLACEHOLDER DETECTED in {label}.{key}: {val!r}")
    return flags


def main() -> None:
    all_flags: list[str] = []

    # --- 1. Query merchants ---
    merchant_url = (
        f"{SUPABASE_URL}/rest/v1/merchants"
        f"?name=ilike.*denny*&select={MERCHANT_FIELDS}"
    )
    resp = httpx.get(merchant_url, headers=HEADERS, timeout=15)
    if resp.status_code != 200:
        print(f"ERROR querying merchants: {resp.status_code} {resp.text}")
        sys.exit(1)

    merchants = resp.json()
    print(f"=== Merchants matching 'denny' ({len(merchants)} found) ===\n")

    if not merchants:
        print("No Denny's merchants found.")
        sys.exit(0)

    for m in merchants:
        print(f"--- Merchant: {m['name']} (id={m['id']}) ---")
        for key, val in m.items():
            print(f"  {key}: {val!r}")
        flags = check_placeholders(f"merchant[{m['id']}]", m)
        all_flags.extend(flags)
        for f in flags:
            print(f)
        print()

    # --- 2. Query active discounts for each merchant ---
    for m in merchants:
        mid = m["id"]
        discount_url = (
            f"{SUPABASE_URL}/rest/v1/discounts_v2"
            f"?merchant_id=eq.{mid}&active=eq.true&select={DISCOUNT_FIELDS}"
        )
        resp = httpx.get(discount_url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            print(f"ERROR querying discounts for merchant {mid}: {resp.status_code} {resp.text}")
            continue

        discounts = resp.json()
        print(f"=== Active Discounts for {m['name']} (id={mid}) - {len(discounts)} rows ===\n")

        if not discounts:
            print("  (no active discounts)\n")
            continue

        for i, d in enumerate(discounts, 1):
            print(f"  Discount #{i} (id={d['id']}):")
            for key, val in d.items():
                print(f"    {key}: {val!r}")
            flags = check_placeholders(f"discount[{d['id']}]", d)
            all_flags.extend(flags)
            for f in flags:
                print(f)
            print()

    # --- 3. Summary ---
    print("=" * 60)
    if all_flags:
        print(f"\n*** {len(all_flags)} PLACEHOLDER FLAG(S) FOUND ***\n")
        for f in all_flags:
            print(f)
    else:
        print("\nNo placeholder text detected.")


if __name__ == "__main__":
    main()
