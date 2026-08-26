#!/usr/bin/env python3
"""Backfill default_discount_* fields for national merchants missing them.

Uses their active discounts_v2 rows to determine the most common values.
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BASE = f"{SUPABASE_URL}/rest/v1"


def main() -> None:
    client = httpx.Client(headers=HEADERS, timeout=30)

    # 1. Get all active national merchants missing default_discount_value
    print("Fetching active national merchants missing default_discount_value ...")
    resp = client.get(
        f"{BASE}/merchants",
        params={
            "is_active": "eq.true",
            "is_national": "eq.true",
            "default_discount_value": "is.null",
            "select": "id,name,default_discount_value,default_discount_text,"
                      "default_discount_requirement,default_discount_type",
        },
    )
    resp.raise_for_status()
    merchants = resp.json()
    print(f"Found {len(merchants)} merchants missing default_discount_value.\n")

    if not merchants:
        print("Nothing to backfill.")
        return

    updated: list[dict] = []
    skipped: list[dict] = []

    for m in merchants:
        mid = m["id"]
        name = m["name"]

        # 2. Get active discounts_v2 rows for this merchant
        resp = client.get(
            f"{BASE}/discounts_v2",
            params={
                "merchant_id": f"eq.{mid}",
                "active": "eq.true",
                "select": "id,discount_value,details,requirement,discount_type,store_location_id",
            },
        )
        resp.raise_for_status()
        discounts = resp.json()

        if not discounts:
            skipped.append({"id": mid, "name": name, "reason": "No active discounts_v2 rows"})
            continue

        # 3. Determine most common values
        values = [d["discount_value"] for d in discounts if d.get("discount_value")]
        requirements = [d["requirement"] for d in discounts if d.get("requirement")]
        types = [d["discount_type"] for d in discounts if d.get("discount_type")]
        details_list = [d["details"] for d in discounts if d.get("details")]

        if not values:
            skipped.append({
                "id": mid, "name": name,
                "reason": f"Has {len(discounts)} active discounts but none have discount_value",
            })
            continue

        best_value = Counter(values).most_common(1)[0][0]
        best_requirement = Counter(requirements).most_common(1)[0][0] if requirements else None
        best_type = Counter(types).most_common(1)[0][0] if types else None

        # For default_discount_text: use the most common details if available,
        # otherwise build from discount_value
        if details_list:
            best_text = Counter(details_list).most_common(1)[0][0]
        else:
            best_text = f"{best_value} off"

        patch_body = {
            "default_discount_value": best_value,
            "default_discount_text": best_text,
        }
        if best_requirement:
            patch_body["default_discount_requirement"] = best_requirement
        if best_type:
            patch_body["default_discount_type"] = best_type

        # 4. Update the merchant
        resp = client.patch(
            f"{BASE}/merchants",
            params={"id": f"eq.{mid}"},
            content=json.dumps(patch_body),
        )
        resp.raise_for_status()
        result = resp.json()

        updated.append({
            "id": mid,
            "name": name,
            "applied": patch_body,
            "discounts_count": len(discounts),
            "unique_values": len(set(values)),
        })

    # 5. Print summary
    print("=" * 80)
    print(f"BACKFILL COMPLETE: {len(updated)} updated, {len(skipped)} skipped")
    print("=" * 80)

    if updated:
        print(f"\n{'UPDATED MERCHANTS':=^80}")
        for i, u in enumerate(updated, 1):
            print(f"\n  {i}. {u['name']} (id: {u['id']})")
            print(f"     Discounts examined: {u['discounts_count']} active rows "
                  f"({u['unique_values']} unique values)")
            for k, v in u["applied"].items():
                print(f"     {k}: {v}")

    if skipped:
        print(f"\n{'SKIPPED MERCHANTS':=^80}")
        for i, s in enumerate(skipped, 1):
            print(f"  {i}. {s['name']} (id: {s['id']})")
            print(f"     Reason: {s['reason']}")

    print()


if __name__ == "__main__":
    main()
