#!/usr/bin/env python3
"""Query Supabase for all Kohl's data - merchant record + discounts + page content.

Searches for any field containing 'Replace _Kohls_Value' or similar placeholder text.
"""
import json
import os
import sys

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

url = os.environ["SUPABASE_URL"]
key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
headers = {"apikey": key, "Authorization": f"Bearer {key}"}
client = httpx.Client(timeout=30)

# ── Step 1: Get Kohl's merchant record(s) ────────────────────────────────────
print("=" * 80)
print("STEP 1: Merchant record(s) matching 'kohl'")
print("=" * 80)

r = client.get(
    f"{url}/rest/v1/merchants",
    headers=headers,
    params={"select": "*", "name": "ilike.*kohl*"},
)
r.raise_for_status()
merchants = r.json()

if not merchants:
    print("No merchants found matching 'kohl'")
    sys.exit(0)

for m in merchants:
    print(f"\n--- Merchant ID: {m['id']} ---")
    for k, v in sorted(m.items()):
        print(f"  {k}: {v}")

merchant_ids = [m["id"] for m in merchants]

# ── Step 2: Get all discounts for those merchant IDs ─────────────────────────
print("\n" + "=" * 80)
print("STEP 2: Discounts (discounts_v2) for Kohl's merchant(s)")
print("=" * 80)

for mid in merchant_ids:
    r = client.get(
        f"{url}/rest/v1/discounts_v2",
        headers=headers,
        params={"select": "*", "merchant_id": f"eq.{mid}"},
    )
    r.raise_for_status()
    discounts = r.json()
    print(f"\nMerchant ID {mid}: {len(discounts)} discount(s)")
    for d in discounts:
        print(f"\n  --- Discount ID: {d.get('id', 'N/A')} ---")
        for k, v in sorted(d.items()):
            print(f"    {k}: {v}")

# ── Step 3: Scan ALL text fields for placeholder patterns ────────────────────
print("\n" + "=" * 80)
print("STEP 3: Scanning ALL fields for placeholder patterns")
print("=" * 80)

placeholders_found = []
search_patterns = ["Replace", "REPLACE", "_Value", "_VALUE", "placeholder", "PLACEHOLDER"]

for m in merchants:
    for k, v in m.items():
        if v is None:
            continue
        v_str = str(v)
        for pat in search_patterns:
            if pat in v_str:
                placeholders_found.append(f"  merchants.{k} contains '{pat}': {v_str[:200]}")

for mid in merchant_ids:
    r = client.get(
        f"{url}/rest/v1/discounts_v2",
        headers=headers,
        params={"select": "*", "merchant_id": f"eq.{mid}"},
    )
    for d in r.json():
        for k, v in d.items():
            if v is None:
                continue
            v_str = str(v)
            for pat in search_patterns:
                if pat in v_str:
                    placeholders_found.append(
                        f"  discounts_v2.{k} (discount {d.get('id','?')}): '{pat}' found: {v_str[:200]}"
                    )

if placeholders_found:
    print("FOUND placeholder-like text:")
    for p in placeholders_found:
        print(p)
else:
    print("No placeholder patterns found in any Kohl's data fields.")

# ── Step 4: Also check store_locations count ─────────────────────────────────
print("\n" + "=" * 80)
print("STEP 4: Store location count for Kohl's")
print("=" * 80)

for mid in merchant_ids:
    r = client.get(
        f"{url}/rest/v1/store_locations",
        headers=headers,
        params={
            "select": "merchant_id",
            "merchant_id": f"eq.{mid}",
            "is_active": "eq.true",
        },
    )
    r.raise_for_status()
    locs = r.json()
    print(f"Merchant ID {mid}: {len(locs)} active store locations")

print("\n" + "=" * 80)
print("DONE")
print("=" * 80)
