"""
Cleanup discount text across merchants and discounts_v2 tables.

1. All "varies"/"vary" variants -> "View"
2. Previous "Ask" entries -> "View"
3. Remove " off" suffix from percentage values (e.g., "10% off" -> "10%")
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


def main() -> None:
    client = httpx.Client(base_url=SUPABASE_URL, headers=HEADERS, timeout=30)

    counts = {
        "discounts_varies": 0,
        "merchants_varies": 0,
        "discounts_ask": 0,
        "merchants_ask": 0,
        "discounts_off": 0,
        "merchants_off": 0,
    }

    # ── Step 1: "varies"/"vary" -> "View" in discounts_v2 ──
    print("=" * 70)
    print("STEP 1: discounts_v2 - varies/vary variants -> View")
    print("=" * 70)

    resp = client.get(
        "/rest/v1/discounts_v2",
        params={
            "discount_value": "ilike.*var*",
            "active": "eq.true",
            "select": "id,merchant_id,name,discount_value",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    print(f"Found {len(rows)} rows.\n")

    for row in rows:
        old_val = row["discount_value"]
        print(f"  Discount ID {row['id']} (merchant {row['merchant_id']}): "
              f"'{old_val}' -> 'View'")
        patch_resp = client.patch(
            "/rest/v1/discounts_v2",
            params={"id": f"eq.{row['id']}"},
            content=json.dumps({"discount_value": "View"}),
        )
        patch_resp.raise_for_status()
        counts["discounts_varies"] += 1

    # ── Step 2: "varies"/"vary" -> "View" in merchants ──
    print("\n" + "=" * 70)
    print("STEP 2: merchants - varies/vary variants -> View")
    print("=" * 70)

    resp = client.get(
        "/rest/v1/merchants",
        params={
            "default_discount_value": "ilike.*var*",
            "select": "id,name,default_discount_value,default_discount_text",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    print(f"Found {len(rows)} rows.\n")

    for row in rows:
        old_val = row["default_discount_value"]
        old_text = row.get("default_discount_text")
        patch_body: dict = {"default_discount_value": "View"}
        # Also fix default_discount_text if it contains varies/vary
        if old_text and "var" in old_text.lower():
            patch_body["default_discount_text"] = "View"

        print(f"  Merchant ID {row['id']} ({row['name']}): "
              f"default_discount_value '{old_val}' -> 'View'")
        if "default_discount_text" in patch_body:
            print(f"    default_discount_text '{old_text}' -> 'View'")

        patch_resp = client.patch(
            "/rest/v1/merchants",
            params={"id": f"eq.{row['id']}"},
            content=json.dumps(patch_body),
        )
        patch_resp.raise_for_status()
        counts["merchants_varies"] += 1

    # Also check default_discount_text independently for varies/vary
    resp = client.get(
        "/rest/v1/merchants",
        params={
            "default_discount_text": "ilike.*var*",
            "select": "id,name,default_discount_value,default_discount_text",
        },
    )
    resp.raise_for_status()
    text_rows = resp.json()
    # Filter out any already updated above
    already_updated = {r["id"] for r in rows}
    text_rows = [r for r in text_rows if r["id"] not in already_updated]

    if text_rows:
        print(f"\n  Found {len(text_rows)} additional merchants with varies in default_discount_text.\n")
        for row in text_rows:
            old_text = row.get("default_discount_text")
            print(f"  Merchant ID {row['id']} ({row['name']}): "
                  f"default_discount_text '{old_text}' -> 'View'")
            patch_resp = client.patch(
                "/rest/v1/merchants",
                params={"id": f"eq.{row['id']}"},
                content=json.dumps({"default_discount_text": "View"}),
            )
            patch_resp.raise_for_status()
            counts["merchants_varies"] += 1

    # ── Step 3: "Ask" -> "View" in discounts_v2 ──
    print("\n" + "=" * 70)
    print("STEP 3: discounts_v2 - Ask -> View")
    print("=" * 70)

    resp = client.get(
        "/rest/v1/discounts_v2",
        params={
            "discount_value": "eq.Ask",
            "active": "eq.true",
            "select": "id,merchant_id,name,discount_value",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    print(f"Found {len(rows)} rows.\n")

    for row in rows:
        print(f"  Discount ID {row['id']} (merchant {row['merchant_id']}): "
              f"'Ask' -> 'View'")
        patch_resp = client.patch(
            "/rest/v1/discounts_v2",
            params={"id": f"eq.{row['id']}"},
            content=json.dumps({"discount_value": "View"}),
        )
        patch_resp.raise_for_status()
        counts["discounts_ask"] += 1

    # ── Step 4: "Ask" -> "View" in merchants ──
    print("\n" + "=" * 70)
    print("STEP 4: merchants - Ask -> View")
    print("=" * 70)

    resp = client.get(
        "/rest/v1/merchants",
        params={
            "default_discount_value": "eq.Ask",
            "select": "id,name,default_discount_value,default_discount_text",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    print(f"Found {len(rows)} rows.\n")

    for row in rows:
        old_text = row.get("default_discount_text")
        patch_body = {"default_discount_value": "View"}
        if old_text == "Ask":
            patch_body["default_discount_text"] = "View"

        print(f"  Merchant ID {row['id']} ({row['name']}): "
              f"default_discount_value 'Ask' -> 'View'")
        if "default_discount_text" in patch_body:
            print(f"    default_discount_text 'Ask' -> 'View'")

        patch_resp = client.patch(
            "/rest/v1/merchants",
            params={"id": f"eq.{row['id']}"},
            content=json.dumps(patch_body),
        )
        patch_resp.raise_for_status()
        counts["merchants_ask"] += 1

    # Also check default_discount_text = "Ask" independently
    resp = client.get(
        "/rest/v1/merchants",
        params={
            "default_discount_text": "eq.Ask",
            "select": "id,name,default_discount_value,default_discount_text",
        },
    )
    resp.raise_for_status()
    text_rows = resp.json()
    already_updated = {r["id"] for r in rows}
    text_rows = [r for r in text_rows if r["id"] not in already_updated]

    if text_rows:
        print(f"\n  Found {len(text_rows)} additional merchants with Ask in default_discount_text.\n")
        for row in text_rows:
            print(f"  Merchant ID {row['id']} ({row['name']}): "
                  f"default_discount_text 'Ask' -> 'View'")
            patch_resp = client.patch(
                "/rest/v1/merchants",
                params={"id": f"eq.{row['id']}"},
                content=json.dumps({"default_discount_text": "View"}),
            )
            patch_resp.raise_for_status()
            counts["merchants_ask"] += 1

    # ── Step 5: "% off" -> "%" in discounts_v2 ──
    print("\n" + "=" * 70)
    print("STEP 5: discounts_v2 - remove ' off' from percentage values")
    print("=" * 70)

    resp = client.get(
        "/rest/v1/discounts_v2",
        params={
            "discount_value": "ilike.*% off*",
            "active": "eq.true",
            "select": "id,merchant_id,name,discount_value",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    print(f"Found {len(rows)} rows.\n")

    for row in rows:
        old_val = row["discount_value"]
        new_val = old_val.replace(" off", "").replace(" Off", "").replace(" OFF", "")
        print(f"  Discount ID {row['id']} (merchant {row['merchant_id']}): "
              f"'{old_val}' -> '{new_val}'")
        patch_resp = client.patch(
            "/rest/v1/discounts_v2",
            params={"id": f"eq.{row['id']}"},
            content=json.dumps({"discount_value": new_val}),
        )
        patch_resp.raise_for_status()
        counts["discounts_off"] += 1

    # ── Step 6: "% off" -> "%" in merchants ──
    print("\n" + "=" * 70)
    print("STEP 6: merchants - remove ' off' from percentage values")
    print("=" * 70)

    resp = client.get(
        "/rest/v1/merchants",
        params={
            "default_discount_value": "ilike.*% off*",
            "select": "id,name,default_discount_value",
        },
    )
    resp.raise_for_status()
    rows = resp.json()
    print(f"Found {len(rows)} rows.\n")

    for row in rows:
        old_val = row["default_discount_value"]
        new_val = old_val.replace(" off", "").replace(" Off", "").replace(" OFF", "")
        print(f"  Merchant ID {row['id']} ({row['name']}): "
              f"'{old_val}' -> '{new_val}'")
        patch_resp = client.patch(
            "/rest/v1/merchants",
            params={"id": f"eq.{row['id']}"},
            content=json.dumps({"default_discount_value": new_val}),
        )
        patch_resp.raise_for_status()
        counts["merchants_off"] += 1

    # ── Summary ──
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  discounts_v2 varies/vary -> View:  {counts['discounts_varies']}")
    print(f"  merchants varies/vary -> View:     {counts['merchants_varies']}")
    print(f"  discounts_v2 Ask -> View:          {counts['discounts_ask']}")
    print(f"  merchants Ask -> View:             {counts['merchants_ask']}")
    print(f"  discounts_v2 '% off' -> '%':       {counts['discounts_off']}")
    print(f"  merchants '% off' -> '%':          {counts['merchants_off']}")
    total = sum(counts.values())
    print(f"  TOTAL rows updated:                {total}")
    print("Done.")


if __name__ == "__main__":
    main()
