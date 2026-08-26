"""
Update 'Varies' discount rows in discounts_v2 and merchants tables.

1. Fetch active discounts_v2 rows where discount_value ilike '%varies%'
2. Update discount_value from "Varies" to "Discounts Vary"
3. Append contact-store language to details if not already present
4. Check corresponding merchants for default_discount_value/text containing "varies"
5. Print before/after summary
"""
from __future__ import annotations

import json
import os
import re
import sys

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

CONTACT_STORE_TEXT = "Discounts vary by location. Recommend contacting the store to confirm."

# Patterns that indicate the details already contain similar language
ALREADY_HAS_PATTERNS = [
    r"vary\s+by\s+location",
    r"varies\s+by\s+location",
    r"contact\s+(the\s+)?store",
    r"contacting\s+(the\s+)?store",
    r"check\s+with\s+(your\s+)?(local\s+)?store",
]


def details_already_has_language(details: str | None) -> bool:
    """Check if details already contain vary-by-location or contact-store language."""
    if not details:
        return False
    for pattern in ALREADY_HAS_PATTERNS:
        if re.search(pattern, details, re.IGNORECASE):
            return True
    return False


def main() -> None:
    client = httpx.Client(base_url=SUPABASE_URL, headers=HEADERS, timeout=30)

    # ── Step 1: Fetch discounts_v2 rows with "varies" ──
    print("=" * 70)
    print("STEP 1: Fetching discounts_v2 rows where discount_value ilike '%varies%'")
    print("=" * 70)

    resp = client.get(
        "/rest/v1/discounts_v2",
        params={
            "discount_value": "ilike.*varies*",
            "active": "eq.true",
            "select": "id,merchant_id,name,discount_value,details,requirement,discount_type",
        },
    )
    resp.raise_for_status()
    discounts = resp.json()

    print(f"Found {len(discounts)} rows.\n")

    if not discounts:
        print("No 'varies' discounts found. Exiting.")
        sys.exit(0)

    # ── Step 2 & 3: Update each discount row ──
    print("=" * 70)
    print("STEP 2: Updating discounts_v2 rows")
    print("=" * 70)

    merchant_ids = set()

    for row in discounts:
        row_id = row["id"]
        merchant_ids.add(row["merchant_id"])

        old_value = row["discount_value"]
        old_details = row["details"]

        new_value = "Discounts Vary"
        new_details = old_details

        if details_already_has_language(old_details):
            # Already has similar language, don't append
            pass
        else:
            if old_details and old_details.strip():
                new_details = old_details.rstrip() + " " + CONTACT_STORE_TEXT
            else:
                new_details = CONTACT_STORE_TEXT

        patch_body: dict = {"discount_value": new_value}
        if new_details != old_details:
            patch_body["details"] = new_details

        print(f"\n--- Discount ID: {row_id} | Merchant ID: {row['merchant_id']} ---")
        print(f"  Name:            {row['name']}")
        print(f"  discount_value:  '{old_value}' -> '{new_value}'")
        if new_details != old_details:
            print(f"  details BEFORE:  '{old_details}'")
            print(f"  details AFTER:   '{new_details}'")
        else:
            print(f"  details:         (unchanged) '{old_details}'")

        patch_resp = client.patch(
            "/rest/v1/discounts_v2",
            params={"id": f"eq.{row_id}"},
            content=json.dumps(patch_body),
        )
        patch_resp.raise_for_status()
        updated = patch_resp.json()
        print(f"  PATCHED OK -> returned: {json.dumps(updated, indent=2)}")

    # ── Step 4: Check merchants table ──
    print("\n" + "=" * 70)
    print("STEP 3: Checking merchants table for these merchant_ids")
    print("=" * 70)

    ids_csv = ",".join(str(mid) for mid in merchant_ids)
    resp = client.get(
        "/rest/v1/merchants",
        params={
            "id": f"in.({ids_csv})",
            "select": "id,name,default_discount_value,default_discount_text,default_discount_requirement",
        },
    )
    resp.raise_for_status()
    merchants = resp.json()

    print(f"Found {len(merchants)} merchants.\n")

    merchants_updated = 0
    for m in merchants:
        mid = m["id"]
        m_name = m["name"]
        old_ddv = m.get("default_discount_value")
        old_ddt = m.get("default_discount_text")

        patch_body = {}

        # Check default_discount_value
        if old_ddv and "varies" in old_ddv.lower():
            patch_body["default_discount_value"] = "Discounts Vary"

        # Check default_discount_text
        if old_ddt and "varies" in old_ddt.lower():
            if not details_already_has_language(old_ddt):
                if old_ddt.strip():
                    patch_body["default_discount_text"] = (
                        old_ddt.rstrip() + " " + CONTACT_STORE_TEXT
                    )
                else:
                    patch_body["default_discount_text"] = CONTACT_STORE_TEXT

        if patch_body:
            print(f"\n--- Merchant ID: {mid} | {m_name} ---")
            if "default_discount_value" in patch_body:
                print(
                    f"  default_discount_value: '{old_ddv}' -> '{patch_body['default_discount_value']}'"
                )
            if "default_discount_text" in patch_body:
                print(f"  default_discount_text BEFORE: '{old_ddt}'")
                print(
                    f"  default_discount_text AFTER:  '{patch_body['default_discount_text']}'"
                )

            patch_resp = client.patch(
                "/rest/v1/merchants",
                params={"id": f"eq.{mid}"},
                content=json.dumps(patch_body),
            )
            patch_resp.raise_for_status()
            updated = patch_resp.json()
            print(f"  PATCHED OK -> returned: {json.dumps(updated, indent=2)}")
            merchants_updated += 1
        else:
            print(f"  Merchant ID {mid} ({m_name}): no 'varies' in defaults, skipping.")

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Discounts updated:  {len(discounts)}")
    print(f"  Merchants updated:  {merchants_updated}")
    print("Done.")


if __name__ == "__main__":
    main()
