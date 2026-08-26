"""Deactivate all discounts_v2 rows for Kohl's (merchant_id 694)."""
from __future__ import annotations

import os
import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

BASE = f"{SUPABASE_URL}/rest/v1/discounts_v2"
MERCHANT_FILTER = "merchant_id=eq.694"


def main() -> None:
    with httpx.Client(timeout=30) as client:
        # 1. Count total rows for merchant_id 694
        resp_total = client.get(
            f"{BASE}?{MERCHANT_FILTER}&select=id,active",
            headers={**HEADERS, "Prefer": "return=representation"},
        )
        resp_total.raise_for_status()
        all_rows = resp_total.json()
        total = len(all_rows)
        active_before = sum(1 for r in all_rows if r.get("active") is True)
        inactive_before = sum(1 for r in all_rows if r.get("active") is False)

        print(f"Kohl's (merchant_id 694) - Before update:")
        print(f"  Total rows:    {total}")
        print(f"  Active:        {active_before}")
        print(f"  Inactive:      {inactive_before}")
        print()

        if active_before == 0:
            print("No active rows to deactivate. Done.")
            return

        # 2. PATCH all rows for merchant_id 694 -> active = false
        resp_patch = client.patch(
            f"{BASE}?{MERCHANT_FILTER}",
            headers={**HEADERS, "Prefer": "return=representation"},
            json={"active": False},
        )
        resp_patch.raise_for_status()
        patched = resp_patch.json()
        print(f"PATCH complete. Rows returned by PATCH: {len(patched)}")
        print()

        # 3. Verify: re-query active rows
        resp_verify = client.get(
            f"{BASE}?{MERCHANT_FILTER}&active=eq.true&select=id",
            headers={**HEADERS},
        )
        resp_verify.raise_for_status()
        still_active = resp_verify.json()

        print(f"Kohl's (merchant_id 694) - After update:")
        print(f"  Active remaining: {len(still_active)}")
        print()

        # 4. Summary
        print("=== Summary ===")
        print(f"  Rows deactivated:     {active_before}")
        print(f"  Already inactive:     {inactive_before}")
        print(f"  Total rows:           {total}")
        print(f"  Active remaining:     {len(still_active)}")

        if len(still_active) == 0:
            print("  Status: SUCCESS - all Kohl's discounts are now inactive.")
        else:
            print("  Status: WARNING - some rows are still active!")


if __name__ == "__main__":
    main()
