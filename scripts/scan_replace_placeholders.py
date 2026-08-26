"""Scan Supabase discounts_v2 and merchants tables for REPLACE_ placeholder text."""
from __future__ import annotations

import os
import httpx
import sys

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lmtrgkmgfermqatopkfp.supabase.co")
SUPABASE_KEY = os.environ.get(
    "SUPABASE_SERVICE_ROLE_KEY",
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxtdHJna21nZmVybXFhdG9wa2ZwIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTk3NzA1NCwiZXhwIjoyMDgxNTUzMDU0fQ.R2zvCHiUgfwnp2Q096UPYNurTlPgMHcbAOyBGIS-ozQ",
)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "count=exact",
}

SELECT_DISCOUNTS = "id,merchant_id,name,discount_value,details,requirement,discount_type,active,store_location_id"
SELECT_MERCHANTS = "id,name,default_discount_value,default_discount_text,default_discount_requirement,default_discount_type,is_national"


def query(client: httpx.Client, table: str, params: dict) -> list[dict]:
    """Query Supabase REST API with pagination (1000 rows per page)."""
    all_rows = []
    offset = 0
    page_size = 1000
    while True:
        p = {**params, "offset": str(offset), "limit": str(page_size)}
        resp = client.get(f"{SUPABASE_URL}/rest/v1/{table}", params=p, headers=HEADERS)
        resp.raise_for_status()
        rows = resp.json()
        all_rows.extend(rows)
        if len(rows) < page_size:
            break
        offset += page_size
    return all_rows


def main() -> None:
    client = httpx.Client(timeout=30)

    # ── 1. Scan discounts_v2 for REPLACE_ ───────────────────────────────
    print("=" * 100)
    print("SCANNING discounts_v2 FOR REPLACE_ PLACEHOLDERS")
    print("=" * 100)

    fields_to_check = ["discount_value", "details", "requirement"]
    all_discount_rows: dict[int, dict] = {}

    for field in fields_to_check:
        params = {
            "select": SELECT_DISCOUNTS,
            field: "ilike.*REPLACE*",
        }
        rows = query(client, "discounts_v2", params)
        for row in rows:
            all_discount_rows[row["id"]] = row
        print(f"  {field}: {len(rows)} rows with REPLACE_")

    print(f"\n  Total unique discount rows with REPLACE_: {len(all_discount_rows)}")

    if all_discount_rows:
        # Gather unique merchant IDs
        merchant_ids = set(r["merchant_id"] for r in all_discount_rows.values() if r.get("merchant_id"))
        merchant_map: dict[int, dict] = {}

        for mid in merchant_ids:
            params = {"select": SELECT_MERCHANTS, "id": f"eq.{mid}"}
            merchants = query(client, "merchants", params)
            if merchants:
                merchant_map[mid] = merchants[0]

        # Print table
        print()
        print("-" * 100)
        print(
            f"{'Disc ID':>8}  {'Merchant':30s}  {'Active':>6}  {'Loc ID':>6}  "
            f"{'Placeholder Fields'}"
        )
        print("-" * 100)

        active_count = 0
        inactive_count = 0

        for disc_id in sorted(all_discount_rows.keys()):
            row = all_discount_rows[disc_id]
            mid = row.get("merchant_id")
            merchant = merchant_map.get(mid, {})
            merchant_name = merchant.get("name", f"(merchant {mid})")[:30]
            active = row.get("active", False)
            loc_id = row.get("store_location_id") or "-"

            if active:
                active_count += 1
            else:
                inactive_count += 1

            # Which fields have REPLACE_?
            placeholder_fields = []
            for f in fields_to_check:
                val = row.get(f) or ""
                if "REPLACE" in val.upper():
                    placeholder_fields.append(f"{f}={val!r}")

            print(
                f"{disc_id:>8}  {merchant_name:30s}  {str(active):>6}  {str(loc_id):>6}  "
                f"{'; '.join(placeholder_fields)}"
            )

        print("-" * 100)
        print(f"\nTotal: {len(all_discount_rows)} discount rows with REPLACE_ placeholders")
        print(f"  Active:   {active_count}")
        print(f"  Inactive: {inactive_count}")

        # Print merchant defaults
        print()
        print("=" * 100)
        print("MERCHANT-LEVEL DEFAULTS FOR AFFECTED MERCHANTS")
        print("=" * 100)
        print()
        print(
            f"{'Merch ID':>8}  {'Merchant':30s}  {'National':>8}  "
            f"{'Def Value':20s}  {'Def Text':30s}  {'Def Requirement':30s}  {'Has Defaults?'}"
        )
        print("-" * 160)

        for mid in sorted(merchant_map.keys()):
            m = merchant_map[mid]
            def_val = m.get("default_discount_value") or ""
            def_txt = m.get("default_discount_text") or ""
            def_req = m.get("default_discount_requirement") or ""
            is_national = m.get("is_national", False)

            has_defaults = bool(def_val and "REPLACE" not in def_val.upper())

            print(
                f"{mid:>8}  {m.get('name', '')[:30]:30s}  {str(is_national):>8}  "
                f"{def_val[:20]:20s}  {def_txt[:30]:30s}  {def_req[:30]:30s}  "
                f"{'YES' if has_defaults else 'NO'}"
            )

    else:
        print("\n  No REPLACE_ placeholders found in discounts_v2!")

    # ── 2. Scan merchants for REPLACE_ ──────────────────────────────────
    print()
    print("=" * 100)
    print("SCANNING merchants FOR REPLACE_ PLACEHOLDERS")
    print("=" * 100)

    merchant_fields = [
        ("default_discount_value", "id,name,default_discount_value,default_discount_text"),
        ("default_discount_text", "id,name,default_discount_value,default_discount_text"),
        ("default_discount_requirement", "id,name,default_discount_value,default_discount_requirement"),
    ]

    all_merchant_rows: dict[int, dict] = {}
    for field, select in merchant_fields:
        params = {"select": select, field: "ilike.*REPLACE*"}
        rows = query(client, "merchants", params)
        for row in rows:
            # Merge fields since different selects
            if row["id"] in all_merchant_rows:
                all_merchant_rows[row["id"]].update(row)
            else:
                all_merchant_rows[row["id"]] = row
        print(f"  {field}: {len(rows)} merchants with REPLACE_")

    print(f"\n  Total unique merchants with REPLACE_: {len(all_merchant_rows)}")

    if all_merchant_rows:
        print()
        print("-" * 120)
        print(
            f"{'Merch ID':>8}  {'Merchant':30s}  {'Placeholder Fields'}"
        )
        print("-" * 120)

        for mid in sorted(all_merchant_rows.keys()):
            m = all_merchant_rows[mid]
            placeholder_fields = []
            for field, _ in merchant_fields:
                val = m.get(field) or ""
                if "REPLACE" in val.upper():
                    placeholder_fields.append(f"{field}={val!r}")

            print(
                f"{mid:>8}  {m.get('name', '')[:30]:30s}  {'; '.join(placeholder_fields)}"
            )

        print("-" * 120)
        print(f"\nTotal: {len(all_merchant_rows)} merchants with REPLACE_ placeholders")
    else:
        print("\n  No REPLACE_ placeholders found in merchants table!")

    print()
    print("=" * 100)
    print("SCAN COMPLETE")
    print("=" * 100)

    client.close()


if __name__ == "__main__":
    main()
