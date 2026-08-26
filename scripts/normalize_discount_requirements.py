"""
Normalize inconsistent default_discount_requirement values in the Supabase
merchants table and requirement values in the discounts_v2 table.
"""
from __future__ import annotations

import os
import sys
import httpx
from dotenv import load_dotenv

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

# Normalizations: (old_value, new_value)
# new_value=None means set the DB column to JSON null
NORMALIZATIONS: list[tuple[str, str | None]] = [
    ("Show ID", "Must show valid ID"),
    ("show VALID ID", "Must show valid ID"),
    ("show valid id", "Must show valid ID"),
    ("valid id", "Must show valid ID"),
    ("just the discount", None),
    ("just inform", None),
    ("age_55_plus", "Ages 55 and up"),
    ("age_58_plus", "Ages 58 and up"),
    ("age_60_plus", "Ages 60 and up"),
    ("age_62_plus", "Ages 62 and up"),
    ("age_65_plus", "Ages 65 and up"),
]


def url_encode_value(val: str) -> str:
    """Encode a value for use in Supabase query params (spaces -> +)."""
    return val.replace(" ", "+")


def patch_table(
    client: httpx.Client,
    table: str,
    column: str,
    old_value: str,
    new_value: str | None,
    active_column: str = "is_active",
) -> int:
    """
    PATCH rows in `table` where `column` == `old_value`, setting column to new_value.
    Only patches active rows (using active_column for the filter).
    Returns the number of rows updated.
    """
    encoded = url_encode_value(old_value)
    url = f"{SUPABASE_URL}/rest/v1/{table}?{active_column}=eq.true&{column}=eq.{encoded}"
    body = {column: new_value}
    resp = client.patch(url, json=body, headers=HEADERS)
    if resp.status_code not in (200, 201):
        print(f"  WARNING: PATCH {table} [{old_value}] returned {resp.status_code}: {resp.text}")
        return 0
    rows = resp.json()
    return len(rows) if isinstance(rows, list) else 0


def main() -> None:
    print("=" * 70)
    print("Normalizing discount requirement values")
    print("=" * 70)

    merchants_summary: list[tuple[str, str | None, int]] = []
    discounts_summary: list[tuple[str, str | None, int]] = []

    with httpx.Client(timeout=30) as client:
        # ---------------------------------------------------------------
        # 1. merchants.default_discount_requirement (is_active column)
        # ---------------------------------------------------------------
        print("\n--- merchants.default_discount_requirement ---")
        for old_val, new_val in NORMALIZATIONS:
            count = patch_table(
                client, "merchants", "default_discount_requirement", old_val, new_val,
                active_column="is_active",
            )
            new_display = new_val if new_val is not None else "NULL"
            if count:
                print(f"  {old_val!r:30s} -> {new_display!r:30s}  ({count} rows)")
            else:
                print(f"  {old_val!r:30s} -> {new_display!r:30s}  (0 rows - no matches)")
            merchants_summary.append((old_val, new_val, count))

        # ---------------------------------------------------------------
        # 2. discounts_v2.requirement (active column, not is_active)
        # ---------------------------------------------------------------
        print("\n--- discounts_v2.requirement ---")
        for old_val, new_val in NORMALIZATIONS:
            count = patch_table(
                client, "discounts_v2", "requirement", old_val, new_val,
                active_column="active",
            )
            new_display = new_val if new_val is not None else "NULL"
            if count:
                print(f"  {old_val!r:30s} -> {new_display!r:30s}  ({count} rows)")
            else:
                print(f"  {old_val!r:30s} -> {new_display!r:30s}  (0 rows - no matches)")
            discounts_summary.append((old_val, new_val, count))

    # ---------------------------------------------------------------
    # Summary
    # ---------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)

    total_merchants = sum(r[2] for r in merchants_summary)
    total_discounts = sum(r[2] for r in discounts_summary)

    print(f"\nmerchants table: {total_merchants} total rows updated")
    for old_val, new_val, count in merchants_summary:
        if count > 0:
            new_display = new_val if new_val is not None else "NULL"
            print(f"  {old_val!r} -> {new_display!r}: {count} rows")

    print(f"\ndiscounts_v2 table: {total_discounts} total rows updated")
    for old_val, new_val, count in discounts_summary:
        if count > 0:
            new_display = new_val if new_val is not None else "NULL"
            print(f"  {old_val!r} -> {new_display!r}: {count} rows")

    if total_merchants == 0 and total_discounts == 0:
        print("\nNo rows needed normalization - all values are already consistent.")

    print("\nDone.")


if __name__ == "__main__":
    main()
