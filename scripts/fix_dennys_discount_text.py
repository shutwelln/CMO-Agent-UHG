"""Fix Denny's default_discount_text from 20% to 15% to match default_discount_value."""
from __future__ import annotations

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

MERCHANT_ID = 1269  # Denny's

resp = httpx.patch(
    f"{SUPABASE_URL}/rest/v1/merchants?id=eq.{MERCHANT_ID}",
    headers=HEADERS,
    json={"default_discount_text": "15% off for seniors 55+"},
    timeout=15,
)

if resp.status_code not in (200, 204):
    print(f"PATCH failed ({resp.status_code}): {resp.text}")
    sys.exit(1)

rows = resp.json()
for r in rows:
    print(f"Updated merchant {r['id']} ({r['name']}):")
    print(f"  default_discount_value: {r.get('default_discount_value')}")
    print(f"  default_discount_text:  {r.get('default_discount_text')}")
print("Done.")
