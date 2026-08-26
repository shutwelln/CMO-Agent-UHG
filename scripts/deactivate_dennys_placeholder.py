"""Deactivate the placeholder discount row for Denny's in Supabase (id=9468)."""
import os
import sys

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# 1. PATCH the row to set active = false
patch_url = f"{SUPABASE_URL}/rest/v1/discounts_v2?id=eq.9468"
resp = requests.patch(patch_url, json={"active": False}, headers=HEADERS, timeout=15)

if resp.status_code not in (200, 204):
    print(f"PATCH failed ({resp.status_code}): {resp.text}")
    sys.exit(1)

patched = resp.json()
print(f"Patched {len(patched)} row(s):")
for row in patched:
    print(f"  id={row['id']}  merchant_id={row['merchant_id']}  active={row['active']}")

# 2. Verify: no active rows remain for merchant_id=1269
verify_url = f"{SUPABASE_URL}/rest/v1/discounts_v2?merchant_id=eq.1269&active=eq.true&select=id,merchant_id,active"
resp2 = requests.get(verify_url, headers=HEADERS, timeout=15)

if resp2.status_code != 200:
    print(f"Verify GET failed ({resp2.status_code}): {resp2.text}")
    sys.exit(1)

remaining = resp2.json()
print(f"\nActive rows remaining for merchant_id=1269: {len(remaining)}")
if remaining:
    for row in remaining:
        print(f"  id={row['id']}  merchant_id={row['merchant_id']}  active={row['active']}")
else:
    print("Confirmed: 0 active discount rows for Denny's (merchant_id=1269).")
