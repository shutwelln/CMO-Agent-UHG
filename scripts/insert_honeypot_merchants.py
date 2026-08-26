"""
Insert honeypot (canary) merchants into the Saverwell Supabase database.

These are verifiably fake merchants with tracking URLs (saverwell.ai/r/*)
used to detect scraping of our merchant/discount data. Each merchant gets
a matching discounts_v2 record. A honeypot_hits table schema is printed
for manual creation.

Usage:
    python scripts/insert_honeypot_merchants.py
"""
from __future__ import annotations

import json
import os
import sys

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

if not SUPABASE_URL or not SERVICE_ROLE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
    sys.exit(1)

HEADERS = {
    "Authorization": f"Bearer {SERVICE_ROLE_KEY}",
    "apikey": SERVICE_ROLE_KEY,
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# ---------------------------------------------------------------------------
# Honeypot merchant definitions
#
# Mapped to actual merchants table columns:
#   name, merchant_type, website_url, default_discount_type,
#   default_discount_value, default_discount_text,
#   default_discount_details, default_discount_requirement,
#   is_national, is_active
#
# The "notes" field does not exist on the table, so the honeypot marker
# is embedded in default_discount_details as a suffix.
# ---------------------------------------------------------------------------

# Map honeypot merchant_type to merchant_categories slug for category_id resolution
HONEYPOT_CATEGORY_SLUGS = {
    "Grocery": "grocery",
    "Home Improvement": "home-improvement",
    "Pharmacy": "pharmacy",
    "Hardware": "home-improvement",
}

HONEYPOT_MERCHANTS = [
    {
        "name": "GreenLeaf Market",
        "merchant_type": "Grocery",
        "default_discount_type": "percentage",
        "default_discount_value": 15,
        "default_discount_text": "15% off every Thursday for seniors",
        "default_discount_details": "15% off every Thursday for seniors. [HONEYPOT canary:glm]",
        "default_discount_requirement": "age_62_plus",
        "is_national": True,
        "is_active": True,
        "website_url": "https://saverwell.ai/r/glm",
        "affiliate_priority_score": 0,
    },
    {
        "name": "Patriot Home Supply",
        "merchant_type": "Home Improvement",
        "default_discount_type": "percentage",
        "default_discount_value": 12,
        "default_discount_text": "12% off every Monday for seniors",
        "default_discount_details": "12% off every Monday for seniors. [HONEYPOT canary:phs]",
        "default_discount_requirement": "age_58_plus",
        "is_national": True,
        "is_active": True,
        "website_url": "https://saverwell.ai/r/phs",
        "affiliate_priority_score": 0,
    },
    {
        "name": "SilverBridge Pharmacy",
        "merchant_type": "Pharmacy",
        "default_discount_type": "percentage",
        "default_discount_value": 20,
        "default_discount_text": "20% off every Wednesday, AARP membership required",
        "default_discount_details": "20% off every Wednesday, AARP membership required. [HONEYPOT canary:sbp]",
        "default_discount_requirement": "age_65_plus",
        "is_national": True,
        "is_active": True,
        "website_url": "https://saverwell.ai/r/sbp",
        "affiliate_priority_score": 0,
    },
    {
        "name": "Cornerstone Grocers",
        "merchant_type": "Grocery",
        "default_discount_type": "percentage",
        "default_discount_value": 8,
        "default_discount_text": "8% off daily for seniors",
        "default_discount_details": "8% off daily for seniors. [HONEYPOT canary:cg]",
        "default_discount_requirement": "age_60_plus",
        "is_national": True,
        "is_active": True,
        "website_url": "https://saverwell.ai/r/cg",
        "affiliate_priority_score": 0,
    },
    {
        "name": "BrightPath Hardware",
        "merchant_type": "Hardware",
        "default_discount_type": "percentage",
        "default_discount_value": 10,
        "default_discount_text": "10% off every Friday for seniors",
        "default_discount_details": "10% off every Friday for seniors. [HONEYPOT canary:bph]",
        "default_discount_requirement": "age_55_plus",
        "is_national": True,
        "is_active": True,
        "website_url": "https://saverwell.ai/r/bph",
        "affiliate_priority_score": 0,
    },
]

# Canary code lookup by merchant name (for summary output)
CANARY_CODES = {
    "GreenLeaf Market": "glm",
    "Patriot Home Supply": "phs",
    "SilverBridge Pharmacy": "sbp",
    "Cornerstone Grocers": "cg",
    "BrightPath Hardware": "bph",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def pp(label: str, data: object) -> None:
    """Pretty-print a labelled JSON blob."""
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    print(json.dumps(data, indent=2, default=str))


# ---------------------------------------------------------------------------
# Step 1 - Insert merchants
# ---------------------------------------------------------------------------


def fetch_category_slug_to_id(client: httpx.Client) -> dict[str, int]:
    """Fetch merchant_categories and return slug->id map."""
    url = f"{SUPABASE_URL}/rest/v1/merchant_categories?select=id,slug"
    resp = client.get(url)
    if resp.status_code != 200:
        print(f"WARNING: Could not fetch merchant_categories ({resp.status_code}). Skipping category_id.")
        return {}
    return {row["slug"]: row["id"] for row in resp.json()}


def insert_merchants(client: httpx.Client) -> list[dict]:
    """Insert honeypot merchants and return the created rows (with IDs)."""
    # Resolve category_id from merchant_categories table
    slug_to_id = fetch_category_slug_to_id(client)

    merchants_with_category = []
    for m in HONEYPOT_MERCHANTS:
        row = dict(m)
        cat_slug = HONEYPOT_CATEGORY_SLUGS.get(m["merchant_type"])
        if cat_slug and cat_slug in slug_to_id:
            row["category_id"] = slug_to_id[cat_slug]
        merchants_with_category.append(row)

    url = f"{SUPABASE_URL}/rest/v1/merchants"
    resp = client.post(url, json=merchants_with_category)

    if resp.status_code not in (200, 201):
        print(f"ERROR inserting merchants: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    rows = resp.json()
    pp("Step 1: Inserted merchants", rows)
    return rows


# ---------------------------------------------------------------------------
# Step 2 - Insert discounts_v2 records
# ---------------------------------------------------------------------------


def insert_discounts(client: httpx.Client, merchant_rows: list[dict]) -> list[dict]:
    """Insert a discounts_v2 row for each honeypot merchant."""
    discounts = []
    for m in merchant_rows:
        discounts.append(
            {
                "merchant_id": m["id"],
                "store_location_id": None,
                "name": f"{m['name']} Senior Discount",
                "discount_type": m["default_discount_type"],
                "discount_value": m["default_discount_value"],
                "details": m["default_discount_details"],
                "requirement": m["default_discount_requirement"],
                "active": True,
            }
        )

    url = f"{SUPABASE_URL}/rest/v1/discounts_v2"
    resp = client.post(url, json=discounts)

    if resp.status_code not in (200, 201):
        print(f"ERROR inserting discounts: {resp.status_code}")
        print(resp.text)
        sys.exit(1)

    rows = resp.json()
    pp("Step 2: Inserted discounts_v2", rows)
    return rows


# ---------------------------------------------------------------------------
# Step 3 - honeypot_hits table
# ---------------------------------------------------------------------------

HONEYPOT_HITS_SQL = """\
-- Run this in the Supabase SQL Editor (or via psql) to create the honeypot_hits table.

CREATE TABLE IF NOT EXISTS honeypot_hits (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    created_at      timestamptz NOT NULL DEFAULT now(),
    canary_code     text NOT NULL,           -- e.g. "glm", "phs", "sbp", "cg", "bph"
    hit_type        text NOT NULL,           -- "redirect" or "beacon"
    referrer        text,
    ip_address      text,
    user_agent      text,
    merchant_slug   text
);

-- Index for quick lookups by canary code
CREATE INDEX IF NOT EXISTS idx_honeypot_hits_canary_code ON honeypot_hits (canary_code);

-- Enable RLS (service role bypasses; anon should not read)
ALTER TABLE honeypot_hits ENABLE ROW LEVEL SECURITY;
"""


def print_honeypot_hits_sql() -> None:
    """Print the CREATE TABLE SQL for honeypot_hits."""
    print(f"\n{'='*60}")
    print("  Step 3: honeypot_hits table SQL (run manually)")
    print(f"{'='*60}")
    print(HONEYPOT_HITS_SQL)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Saverwell Honeypot Merchant Insertion")
    print(f"Target: {SUPABASE_URL}")

    with httpx.Client(headers=HEADERS, timeout=30) as client:
        # Step 1
        merchant_rows = insert_merchants(client)
        print(f"\n  -> {len(merchant_rows)} merchants inserted.")

        # Step 2
        discount_rows = insert_discounts(client, merchant_rows)
        print(f"\n  -> {len(discount_rows)} discounts inserted.")

    # Step 3
    print_honeypot_hits_sql()

    # Summary
    print(f"\n{'='*60}")
    print("  Summary")
    print(f"{'='*60}")
    for m in merchant_rows:
        code = CANARY_CODES.get(m["name"], "?")
        print(
            f"  merchant_id={m['id']}  canary={code}  "
            f"name={m['name']}  website={m['website_url']}"
        )
    print("\nDone. Honeypot merchants are live.")
    print("IMPORTANT: Run the Step 3 SQL in the Supabase SQL Editor to create honeypot_hits.")


if __name__ == "__main__":
    main()
