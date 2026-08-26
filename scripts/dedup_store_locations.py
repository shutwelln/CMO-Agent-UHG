"""
Deduplicate store_locations rows where the same (merchant_id, location_id)
combo appears more than once.

For each duplicate group:
  - Keep the row with the lowest id (oldest record).
  - Reassign any discounts_v2 rows that reference a duplicate's
    store_location_id to the keeper's id.
  - Delete the duplicate rows.
"""
from __future__ import annotations

import os
import sys
from collections import defaultdict

import httpx
from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# PostgREST returns at most 1000 rows per request by default.
PAGE_SIZE = 1000


def fetch_all_store_locations(client: httpx.Client) -> list[dict]:
    """Paginate through all store_locations rows."""
    rows: list[dict] = []
    offset = 0
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/store_locations"
            f"?select=id,merchant_id,location_id,is_active,created_at"
            f"&order=merchant_id,location_id,id"
            f"&limit={PAGE_SIZE}&offset={offset}"
        )
        resp = client.get(url, headers=HEADERS)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        print(f"  fetched {len(rows)} rows so far ...", flush=True)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return rows


def find_duplicates(rows: list[dict]) -> dict[tuple, list[dict]]:
    """Group by (merchant_id, location_id) and return groups with >1 row."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        key = (r["merchant_id"], r["location_id"])
        groups[key].append(r)
    return {k: v for k, v in groups.items() if len(v) > 1}


def find_discounts_for_store_location(
    client: httpx.Client, store_location_id: int
) -> list[dict]:
    """Return discounts_v2 rows referencing a given store_location_id."""
    url = (
        f"{SUPABASE_URL}/rest/v1/discounts_v2"
        f"?select=id,store_location_id"
        f"&store_location_id=eq.{store_location_id}"
    )
    resp = client.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def reassign_discounts(
    client: httpx.Client,
    discount_ids: list[int],
    new_store_location_id: int,
) -> int:
    """Point discounts_v2 rows to the keeper store_location_id."""
    count = 0
    for did in discount_ids:
        url = f"{SUPABASE_URL}/rest/v1/discounts_v2?id=eq.{did}"
        resp = client.patch(
            url,
            headers=HEADERS,
            json={"store_location_id": new_store_location_id},
        )
        resp.raise_for_status()
        count += 1
    return count


def delete_store_location(client: httpx.Client, row_id: int) -> None:
    url = f"{SUPABASE_URL}/rest/v1/store_locations?id=eq.{row_id}"
    resp = client.delete(url, headers=HEADERS)
    resp.raise_for_status()


def main() -> None:
    print("=== Store Locations Deduplication ===\n")

    with httpx.Client(timeout=60) as client:
        # 1. Fetch all store_locations
        print("1. Fetching all store_locations ...")
        rows = fetch_all_store_locations(client)
        print(f"   Total rows: {len(rows)}\n")

        # 2. Find duplicates
        print("2. Finding duplicate (merchant_id, location_id) groups ...")
        dups = find_duplicates(rows)
        print(f"   Duplicate groups: {len(dups)}\n")

        if not dups:
            print("No duplicates found. Nothing to do.")
            return

        # 3. Process each group
        total_deleted = 0
        total_reassigned = 0
        affected_merchants: set[int] = set()
        reassignment_details: list[str] = []

        print("3. Processing duplicate groups ...\n")
        for idx, ((merchant_id, location_id), group) in enumerate(
            sorted(dups.items()), 1
        ):
            # Sort by id; keep the lowest
            group.sort(key=lambda r: r["id"])
            keeper = group[0]
            duplicates = group[1:]

            affected_merchants.add(merchant_id)

            print(
                f"   Group {idx}: merchant_id={merchant_id}, "
                f"location_id={location_id} "
                f"({len(group)} rows, keeping id={keeper['id']})"
            )

            for dup in duplicates:
                # Check for discounts referencing this duplicate
                discounts = find_discounts_for_store_location(client, dup["id"])
                if discounts:
                    discount_ids = [d["id"] for d in discounts]
                    reassigned = reassign_discounts(
                        client, discount_ids, keeper["id"]
                    )
                    total_reassigned += reassigned
                    detail = (
                        f"     Reassigned {reassigned} discount(s) from "
                        f"store_location {dup['id']} -> {keeper['id']}"
                    )
                    print(detail)
                    reassignment_details.append(detail)

                # Delete the duplicate row
                delete_store_location(client, dup["id"])
                total_deleted += 1
                print(f"     Deleted store_location id={dup['id']}")

        # 4. Summary
        print("\n=== SUMMARY ===")
        print(f"Duplicate groups found:     {len(dups)}")
        print(f"Rows deleted:               {total_deleted}")
        print(f"Discounts reassigned:       {total_reassigned}")
        print(f"Affected merchant_ids ({len(affected_merchants)}):")
        for mid in sorted(affected_merchants):
            print(f"  - {mid}")

        if reassignment_details:
            print("\nReassignment details:")
            for d in reassignment_details:
                print(d)

        print("\nDone.")


if __name__ == "__main__":
    main()
