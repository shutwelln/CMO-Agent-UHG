"""
Fix discounts_v2 data quality issues in Supabase:
1. 405 active rows with empty discount_type -> "In store"
2. 47 active rows with "In Store" (wrong caps) -> "In store"
3. 5 informal requirement values -> proper values or NULL
4. 2 bare number details ("10 off", "9 off") -> "$10 off", "$9 off"
"""
from __future__ import annotations

import json
import os
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

BASE = f"{SUPABASE_URL}/rest/v1/discounts_v2"

summary: list[dict] = []


def query(params: dict) -> list[dict]:
    """GET with query params, return JSON list."""
    resp = httpx.get(BASE, headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def patch(params: dict, body: dict) -> list[dict]:
    """PATCH matching rows, return updated rows."""
    resp = httpx.patch(BASE, headers=HEADERS, params=params, json=body, timeout=30)
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    print("=" * 70)
    print("discounts_v2 Data Quality Fix Script")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Fix empty discount_type -> "In store"
    # ------------------------------------------------------------------
    print("\n--- Step 1: Fix empty discount_type ---")
    params_empty_dt = {
        "active": "eq.true",
        "discount_type": "eq.",
        "select": "id,merchant_id,name,discount_value,discount_type",
    }
    before = query(params_empty_dt)
    print(f"  Found {len(before)} rows with empty discount_type")

    if before:
        updated = patch(
            {"active": "eq.true", "discount_type": "eq."},
            {"discount_type": "In store"},
        )
        print(f"  Updated {len(updated)} rows -> discount_type = 'In store'")
    else:
        updated = []
        print("  Nothing to fix.")

    summary.append({
        "issue": "Empty discount_type",
        "before": len(before),
        "fixed": len(updated),
    })

    # ------------------------------------------------------------------
    # 2. Fix "In Store" -> "In store" (capitalization)
    # ------------------------------------------------------------------
    print("\n--- Step 2: Fix 'In Store' capitalization ---")
    params_caps = {
        "active": "eq.true",
        "discount_type": "eq.In Store",
        "select": "id,merchant_id,name,discount_value,discount_type",
    }
    before = query(params_caps)
    print(f"  Found {len(before)} rows with 'In Store'")

    if before:
        updated = patch(
            {"active": "eq.true", "discount_type": "eq.In Store"},
            {"discount_type": "In store"},
        )
        print(f"  Updated {len(updated)} rows -> discount_type = 'In store'")
    else:
        updated = []
        print("  Nothing to fix.")

    summary.append({
        "issue": "'In Store' capitalization",
        "before": len(before),
        "fixed": len(updated),
    })

    # ------------------------------------------------------------------
    # 3. Fix informal requirement values
    # ------------------------------------------------------------------
    print("\n--- Step 3: Fix informal requirement values ---")

    requirement_fixes = [
        # (old_value, new_value_or_None)
        ("just the discount", None),
        ("show valid id", "Must show valid ID"),
        ("show VALID ID", "Must show valid ID"),
        ("just inform", None),
        ("valid id", "Must show valid ID"),
    ]

    total_req_before = 0
    total_req_fixed = 0

    for old_val, new_val in requirement_fixes:
        params_req = {
            "active": "eq.true",
            "requirement": f"eq.{old_val}",
            "select": "id,requirement",
        }
        rows = query(params_req)
        count = len(rows)
        total_req_before += count
        display_new = new_val if new_val else "NULL"
        print(f"  '{old_val}' -> '{display_new}': found {count} rows")

        if rows:
            body = {"requirement": new_val}  # None becomes JSON null
            patched = patch(
                {"active": "eq.true", "requirement": f"eq.{old_val}"},
                body,
            )
            total_req_fixed += len(patched)
            print(f"    Updated {len(patched)} rows")

    summary.append({
        "issue": "Informal requirement values",
        "before": total_req_before,
        "fixed": total_req_fixed,
    })

    # ------------------------------------------------------------------
    # 4. Fix bare number details
    # ------------------------------------------------------------------
    print("\n--- Step 4: Fix bare number details ---")

    detail_fixes = [
        ("10 off", "$10 off"),
        ("9 off", "$9 off"),
    ]

    total_det_before = 0
    total_det_fixed = 0

    for old_val, new_val in detail_fixes:
        params_det = {
            "active": "eq.true",
            "details": f"eq.{old_val}",
            "select": "id,details",
        }
        rows = query(params_det)
        count = len(rows)
        total_det_before += count
        print(f"  '{old_val}' -> '{new_val}': found {count} rows")

        if rows:
            patched = patch(
                {"active": "eq.true", "details": f"eq.{old_val}"},
                {"details": new_val},
            )
            total_det_fixed += len(patched)
            print(f"    Updated {len(patched)} rows")

    summary.append({
        "issue": "Bare number details",
        "before": total_det_before,
        "fixed": total_det_fixed,
    })

    # ------------------------------------------------------------------
    # 5. Verify all fixes
    # ------------------------------------------------------------------
    print("\n--- Step 5: Verification ---")

    # Verify empty discount_type
    remaining = query({
        "active": "eq.true",
        "discount_type": "eq.",
        "select": "id",
    })
    v1 = len(remaining)
    print(f"  Empty discount_type remaining: {v1}")

    # Verify "In Store" caps
    remaining = query({
        "active": "eq.true",
        "discount_type": "eq.In Store",
        "select": "id",
    })
    v2 = len(remaining)
    print(f"  'In Store' remaining: {v2}")

    # Verify informal requirements
    for old_val, _ in requirement_fixes:
        remaining = query({
            "active": "eq.true",
            "requirement": f"eq.{old_val}",
            "select": "id",
        })
        v = len(remaining)
        print(f"  requirement='{old_val}' remaining: {v}")

    # Verify bare details
    for old_val, _ in detail_fixes:
        remaining = query({
            "active": "eq.true",
            "details": f"eq.{old_val}",
            "select": "id",
        })
        v = len(remaining)
        print(f"  details='{old_val}' remaining: {v}")

    # ------------------------------------------------------------------
    # 6. Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'Issue':<35} {'Before':>8} {'Fixed':>8}")
    print("-" * 55)
    total_before = 0
    total_fixed = 0
    for s in summary:
        print(f"{s['issue']:<35} {s['before']:>8} {s['fixed']:>8}")
        total_before += s["before"]
        total_fixed += s["fixed"]
    print("-" * 55)
    print(f"{'TOTAL':<35} {total_before:>8} {total_fixed:>8}")
    print("=" * 70)


if __name__ == "__main__":
    main()
