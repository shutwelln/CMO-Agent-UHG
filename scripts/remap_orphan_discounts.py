"""
Remap 858 orphan discount rows from discounts_v2 to merchant-level defaults,
then deactivate the orphan rows.

Orphan rows = active=true, name=null in discounts_v2.
"""
from __future__ import annotations

import os
import sys
import time
from collections import Counter
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv()
SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
BASE = f"{SUPABASE_URL}/rest/v1"
HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}
BATCH_SIZE = 25  # merchants per batch for PATCH calls


def get(client: httpx.Client, path: str) -> List[Dict[str, Any]]:
    """GET with automatic pagination (Supabase default limit is 1000)."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    limit = 1000
    while True:
        url = f"{BASE}/{path}"
        sep = "&" if "?" in path else "?"
        resp = client.get(
            f"{url}{sep}limit={limit}&offset={offset}",
            headers=HEADERS,
        )
        resp.raise_for_status()
        batch = resp.json()
        rows.extend(batch)
        if len(batch) < limit:
            break
        offset += limit
    return rows


def patch(client: httpx.Client, path: str, body: Dict[str, Any]) -> List[Dict[str, Any]]:
    resp = client.patch(f"{BASE}/{path}", headers=HEADERS, json=body)
    resp.raise_for_status()
    return resp.json()


def most_common(values: List[str]) -> Optional[str]:
    """Return the most common non-null, non-'None' value, or None."""
    filtered = [v for v in values if v is not None and v != "None"]
    if not filtered:
        return None
    return Counter(filtered).most_common(1)[0][0]


def main() -> None:
    errors: List[str] = []

    with httpx.Client(timeout=60) as client:

        # ------------------------------------------------------------------
        # Step 1: Fetch orphan rows
        # ------------------------------------------------------------------
        print("Fetching orphan discount rows (active=true, name=null)...")
        orphans = get(
            client,
            "discounts_v2?active=eq.true&name=is.null"
            "&select=id,merchant_id,discount_value,details,requirement,discount_type,store_location_id",
        )
        print(f"  Found {len(orphans)} orphan rows.")

        if not orphans:
            print("No orphan rows found. Nothing to do.")
            return

        # ------------------------------------------------------------------
        # Step 2: Collect unique merchant IDs and fetch merchant data
        # ------------------------------------------------------------------
        merchant_ids = list({r["merchant_id"] for r in orphans if r.get("merchant_id")})
        print(f"  Spanning {len(merchant_ids)} unique merchants.")

        # Supabase URL length limit - fetch in batches of 200 IDs
        merchants_map: Dict[int, Dict[str, Any]] = {}
        for i in range(0, len(merchant_ids), 200):
            batch_ids = merchant_ids[i : i + 200]
            ids_csv = ",".join(str(mid) for mid in batch_ids)
            merchant_rows = get(
                client,
                f"merchants?id=in.({ids_csv})"
                "&select=id,name,default_discount_value,default_discount_text,"
                "default_discount_requirement,default_discount_type,is_national",
            )
            for m in merchant_rows:
                merchants_map[m["id"]] = m

        print(f"  Fetched data for {len(merchants_map)} merchants.")

        # ------------------------------------------------------------------
        # Step 3: Group orphans by merchant and compute defaults
        # ------------------------------------------------------------------
        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for row in orphans:
            mid = row.get("merchant_id")
            if mid:
                grouped.setdefault(mid, []).append(row)

        updates: List[Dict[str, Any]] = []  # (merchant_id, patch_body)
        skipped_existing = 0
        skipped_missing = 0

        for mid, rows in grouped.items():
            merchant = merchants_map.get(mid)
            if not merchant:
                skipped_missing += 1
                continue

            # Skip merchants that already have default_discount_value set
            if merchant.get("default_discount_value"):
                skipped_existing += 1
                continue

            # Most common `details` value -> default_discount_value
            details_values = [r.get("details") for r in rows]
            best_details = most_common(details_values)
            if not best_details:
                # Fallback to discount_value field if details is all null
                dv_values = [r.get("discount_value") for r in rows]
                best_details = most_common(dv_values)
            if not best_details:
                errors.append(f"Merchant {mid}: no usable discount value found, skipping.")
                continue

            # Most common non-null, non-"None" requirement
            req_values = [r.get("requirement") for r in rows]
            best_req = most_common(req_values)  # None if all null/"None"

            body: Dict[str, Any] = {
                "default_discount_value": best_details,
                "default_discount_text": best_details,
                "default_discount_type": "In-store",
            }
            if best_req is not None:
                body["default_discount_requirement"] = best_req
            else:
                body["default_discount_requirement"] = None

            updates.append({"merchant_id": mid, "body": body})

        print(f"\n  Merchants to update: {len(updates)}")
        print(f"  Merchants skipped (already have defaults): {skipped_existing}")
        print(f"  Merchants skipped (not found in merchants table): {skipped_missing}")

        # ------------------------------------------------------------------
        # Step 4: Batch PATCH merchants
        # ------------------------------------------------------------------
        print(f"\nUpdating merchants in batches of {BATCH_SIZE}...")
        updated_count = 0
        discount_value_counts: Counter = Counter()

        for i in range(0, len(updates), BATCH_SIZE):
            batch = updates[i : i + BATCH_SIZE]
            for item in batch:
                mid = item["merchant_id"]
                body = item["body"]
                try:
                    result = patch(client, f"merchants?id=eq.{mid}", body)
                    if result:
                        updated_count += 1
                        discount_value_counts[body["default_discount_value"]] += 1
                    else:
                        errors.append(f"Merchant {mid}: PATCH returned empty response.")
                except httpx.HTTPStatusError as e:
                    errors.append(f"Merchant {mid}: HTTP {e.response.status_code} - {e.response.text}")
                except Exception as e:
                    errors.append(f"Merchant {mid}: {e}")

            done = min(i + BATCH_SIZE, len(updates))
            print(f"  Processed {done}/{len(updates)} merchants...")
            if i + BATCH_SIZE < len(updates):
                time.sleep(0.5)  # small delay between batches

        print(f"\n  Successfully updated {updated_count} merchants.")

        # ------------------------------------------------------------------
        # Step 5: Deactivate ALL orphan rows
        # ------------------------------------------------------------------
        print("\nDeactivating all orphan discount rows...")
        deactivated = patch(
            client,
            "discounts_v2?active=eq.true&name=is.null",
            {"active": False},
        )
        deactivated_count = len(deactivated) if isinstance(deactivated, list) else 0
        print(f"  Deactivated {deactivated_count} orphan rows.")

        # ------------------------------------------------------------------
        # Step 6: Verify
        # ------------------------------------------------------------------
        print("\nVerifying...")

        # Check remaining orphans
        remaining = get(
            client,
            "discounts_v2?active=eq.true&name=is.null&select=id",
        )
        print(f"  Remaining active orphan rows: {len(remaining)}")

        # Spot-check a few updated merchants
        if updates:
            sample_ids = [u["merchant_id"] for u in updates[:5]]
            ids_csv = ",".join(str(mid) for mid in sample_ids)
            verified = get(
                client,
                f"merchants?id=in.({ids_csv})"
                "&select=id,name,default_discount_value,default_discount_text,"
                "default_discount_requirement,default_discount_type",
            )
            print(f"\n  Spot-check (first 5 updated merchants):")
            for m in verified:
                print(
                    f"    {m['id']} ({m.get('name', 'N/A')}): "
                    f"value={m.get('default_discount_value')}, "
                    f"text={m.get('default_discount_text')}, "
                    f"req={m.get('default_discount_requirement')}, "
                    f"type={m.get('default_discount_type')}"
                )

        # ------------------------------------------------------------------
        # Step 7: Summary
        # ------------------------------------------------------------------
        print("\n" + "=" * 70)
        print("MIGRATION SUMMARY")
        print("=" * 70)
        print(f"  Total orphan rows found:           {len(orphans)}")
        print(f"  Unique merchants with orphans:      {len(merchant_ids)}")
        print(f"  Merchants updated with defaults:    {updated_count}")
        print(f"  Merchants skipped (had defaults):   {skipped_existing}")
        print(f"  Merchants skipped (not in table):   {skipped_missing}")
        print(f"  Orphan rows deactivated:            {deactivated_count}")
        print(f"  Remaining active orphan rows:       {len(remaining)}")
        print(f"  Errors encountered:                 {len(errors)}")

        print(f"\n  Discount value breakdown (applied to merchants):")
        for val, cnt in discount_value_counts.most_common():
            print(f"    {val!r:40s} -> {cnt} merchants")

        if errors:
            print(f"\n  ERRORS ({len(errors)}):")
            for e in errors:
                print(f"    - {e}")

        print("=" * 70)
        print("Done.")


if __name__ == "__main__":
    main()
