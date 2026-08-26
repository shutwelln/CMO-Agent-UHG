#!/usr/bin/env python3
"""
Push approved merchants from the Google Sheet to Supabase.

Reads the "Merchant Review" tab from the discovery pipeline sheet and processes
rows where the Action column is "Insert" or "Update".

Usage:
    python scripts/push_approved_merchants.py --sheet-id "SHEET_ID"
    python scripts/push_approved_merchants.py --sheet-id "SHEET_ID" --dry-run
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

SERVICE_ACCOUNT_PATH = str(_PROJECT_ROOT / "data" / "saverwell-google-credentials.json")
OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Column indices in the Merchant Review tab (0-based)
COL_STATUS = 0
COL_ACTION = 1
COL_NAME = 2
COL_CATEGORY_ID = 3
COL_IS_NATIONAL = 4
COL_DISCOUNT_VALUE = 5
COL_DISCOUNT_TEXT = 6
COL_REQUIREMENT = 7
COL_DISCOUNT_TYPE = 8
COL_DETAILS = 9
COL_HYPERLINK = 10
COL_PAGE_SLUG = 11
COL_IS_ONLINE_ONLY = 12
COL_WEBSITE_URL = 13
COL_EXISTING_ID = 14


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def safe_get(row: List[str], idx: int) -> str:
    """Safely get a column value from a row."""
    if idx < len(row):
        return row[idx].strip()
    return ""


def parse_bool(val: str) -> bool:
    """Parse a string boolean value."""
    return val.lower() in ("true", "yes", "1")


def parse_int(val: str) -> Optional[int]:
    """Parse a string integer, return None if empty or invalid."""
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Supabase operations
# ---------------------------------------------------------------------------
def insert_merchant(
    client: httpx.Client,
    data: Dict[str, Any],
) -> Tuple[bool, Optional[int], str]:
    """Insert a new merchant. Returns (success, merchant_id, message)."""
    resp = client.post(
        f"{SUPABASE_URL}/rest/v1/merchants",
        headers=SUPABASE_HEADERS,
        json=data,
    )
    if resp.status_code in (200, 201):
        rows = resp.json()
        if rows and isinstance(rows, list):
            mid = rows[0].get("id")
            return True, mid, f"Inserted id={mid}"
        return True, None, "Inserted (no id returned)"
    return False, None, f"HTTP {resp.status_code}: {resp.text[:300]}"


def update_merchant(
    client: httpx.Client,
    merchant_id: int,
    data: Dict[str, Any],
) -> Tuple[bool, str]:
    """Update an existing merchant. Returns (success, message)."""
    resp = client.patch(
        f"{SUPABASE_URL}/rest/v1/merchants",
        headers=SUPABASE_HEADERS,
        params={"id": f"eq.{merchant_id}"},
        json=data,
    )
    if resp.status_code in (200, 204):
        return True, f"Updated id={merchant_id}"
    return False, f"HTTP {resp.status_code}: {resp.text[:300]}"


# ---------------------------------------------------------------------------
# Sheet operations
# ---------------------------------------------------------------------------
def read_merchant_review(
    sheets_service: Any, spreadsheet_id: str
) -> List[List[str]]:
    """Read all rows from the Merchant Review tab."""
    result = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Merchant Review!A:Z",
        )
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []
    # Skip header row
    return values[1:]


def mark_pushed(
    sheets_service: Any,
    spreadsheet_id: str,
    row_indices: List[int],
    timestamp: str,
) -> None:
    """Write a 'Pushed' timestamp next to processed rows.

    We use column AA (beyond the data columns) for the push timestamp.
    """
    # First, add header if not present
    try:
        header_check = (
            sheets_service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range="Merchant Review!AA1")
            .execute()
        )
        existing = header_check.get("values", [])
        if not existing or not existing[0]:
            sheets_service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range="Merchant Review!AA1",
                valueInputOption="RAW",
                body={"values": [["Pushed At"]]},
            ).execute()
    except Exception:
        pass

    # Write timestamp to each processed row
    data = []
    for row_idx in row_indices:
        # row_idx is 0-based data row, sheet row = row_idx + 2 (header + 1-indexed)
        sheet_row = row_idx + 2
        data.append(
            {
                "range": f"Merchant Review!AA{sheet_row}",
                "values": [[timestamp]],
            }
        )

    if data:
        sheets_service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": data},
        ).execute()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push approved merchants from Google Sheet to Supabase"
    )
    parser.add_argument(
        "--sheet-id", required=True, help="Google Sheet ID from discover script"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without writing to DB",
    )
    args = parser.parse_args()

    # Validate environment
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    print("=" * 70)
    print("  Push Approved Merchants to Supabase")
    print("=" * 70)
    print(f"  Sheet ID: {args.sheet_id}")
    print(f"  Dry run:  {args.dry_run}")
    print()

    # Load Google credentials
    # Use OAuth for Sheets (service account lacks Sheets API permission)
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    from googleapiclient.discovery import build as build_google

    sheets_svc = build_google("sheets", "v4", credentials=creds)

    # Read the sheet
    print("Reading Merchant Review tab ...")
    rows = read_merchant_review(sheets_svc, args.sheet_id)
    print(f"  Total rows: {len(rows)}")

    # Filter to actionable rows
    insert_rows: List[Tuple[int, List[str]]] = []
    update_rows: List[Tuple[int, List[str]]] = []

    for idx, row in enumerate(rows):
        action = safe_get(row, COL_ACTION).lower()
        if action == "insert":
            insert_rows.append((idx, row))
        elif action == "update":
            update_rows.append((idx, row))

    print(f"  Insert: {len(insert_rows)}  |  Update: {len(update_rows)}")
    print()

    if not insert_rows and not update_rows:
        print("No rows marked for Insert or Update. Nothing to do.")
        print("Fill in the Action column in the Google Sheet first.")
        return

    # Process
    inserted_ids: List[int] = []
    updated_ids: List[int] = []
    errors: List[str] = []
    processed_indices: List[int] = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with httpx.Client(timeout=30) as client:
        # ── Inserts ──────────────────────────────────────────────────────
        if insert_rows:
            print(f"Processing {len(insert_rows)} inserts ...")
            for idx, row in insert_rows:
                name = safe_get(row, COL_NAME)
                category_id = parse_int(safe_get(row, COL_CATEGORY_ID))
                is_national = parse_bool(safe_get(row, COL_IS_NATIONAL))
                discount_value = safe_get(row, COL_DISCOUNT_VALUE)
                discount_text = safe_get(row, COL_DISCOUNT_TEXT)
                requirement = safe_get(row, COL_REQUIREMENT)
                discount_type = safe_get(row, COL_DISCOUNT_TYPE) or "In-store"
                details = safe_get(row, COL_DETAILS)
                hyperlink = safe_get(row, COL_HYPERLINK)
                page_slug = safe_get(row, COL_PAGE_SLUG)
                is_online_only = parse_bool(safe_get(row, COL_IS_ONLINE_ONLY))
                website_url = safe_get(row, COL_WEBSITE_URL)

                # Build payload
                payload: Dict[str, Any] = {
                    "name": name,
                    "is_national": is_national,
                    "is_active": True,
                    "page_status": "published",
                    "default_discount_type": discount_type,
                    "is_online_only": is_online_only,
                }

                if category_id:
                    payload["category_id"] = category_id
                if discount_value:
                    payload["default_discount_value"] = discount_value
                if discount_text:
                    payload["default_discount_text"] = discount_text
                if requirement:
                    payload["default_discount_requirement"] = requirement
                if hyperlink:
                    payload["default_discount_details_hyperlink"] = hyperlink
                if page_slug:
                    payload["page_slug"] = page_slug
                if website_url:
                    payload["website_url"] = website_url
                if details:
                    payload["default_discount_details"] = details

                if args.dry_run:
                    print(f"  [DRY RUN] Would INSERT: {name}")
                    print(f"    Payload: {json.dumps(payload, indent=2)[:300]}")
                    processed_indices.append(idx)
                else:
                    ok, mid, msg = insert_merchant(client, payload)
                    if ok:
                        print(f"  INSERT OK: {name} -> {msg}")
                        if mid:
                            inserted_ids.append(mid)
                        processed_indices.append(idx)
                    else:
                        print(f"  INSERT FAIL: {name} -> {msg}")
                        errors.append(f"Insert {name}: {msg}")

        # ── Updates ──────────────────────────────────────────────────────
        if update_rows:
            print(f"\nProcessing {len(update_rows)} updates ...")
            for idx, row in update_rows:
                name = safe_get(row, COL_NAME)
                merchant_id = parse_int(safe_get(row, COL_EXISTING_ID))

                if not merchant_id:
                    msg = f"Update {name}: No Existing Merchant ID"
                    print(f"  SKIP: {msg}")
                    errors.append(msg)
                    continue

                # Build update payload with only changed fields
                update_data: Dict[str, Any] = {}

                discount_value = safe_get(row, COL_DISCOUNT_VALUE)
                discount_text = safe_get(row, COL_DISCOUNT_TEXT)
                requirement = safe_get(row, COL_REQUIREMENT)
                discount_type = safe_get(row, COL_DISCOUNT_TYPE)
                details = safe_get(row, COL_DETAILS)
                hyperlink = safe_get(row, COL_HYPERLINK)
                is_online_only_str = safe_get(row, COL_IS_ONLINE_ONLY)
                website_url = safe_get(row, COL_WEBSITE_URL)

                if discount_value:
                    update_data["default_discount_value"] = discount_value
                if discount_text:
                    update_data["default_discount_text"] = discount_text
                if requirement:
                    update_data["default_discount_requirement"] = requirement
                if discount_type:
                    update_data["default_discount_type"] = discount_type
                if hyperlink:
                    update_data["default_discount_details_hyperlink"] = hyperlink
                if details:
                    update_data["default_discount_details"] = details
                if is_online_only_str:
                    update_data["is_online_only"] = parse_bool(is_online_only_str)
                if website_url:
                    update_data["website_url"] = website_url

                if not update_data:
                    print(f"  SKIP: {name} - no fields to update")
                    continue

                if args.dry_run:
                    print(f"  [DRY RUN] Would UPDATE id={merchant_id}: {name}")
                    print(f"    Fields: {list(update_data.keys())}")
                    processed_indices.append(idx)
                else:
                    ok, msg = update_merchant(client, merchant_id, update_data)
                    if ok:
                        print(f"  UPDATE OK: {name} (id={merchant_id}) -> {msg}")
                        updated_ids.append(merchant_id)
                        processed_indices.append(idx)
                    else:
                        print(f"  UPDATE FAIL: {name} -> {msg}")
                        errors.append(f"Update {name} (id={merchant_id}): {msg}")

    # Mark processed rows in sheet
    if processed_indices and not args.dry_run:
        print("\nMarking processed rows in sheet ...")
        mark_pushed(sheets_svc, args.sheet_id, processed_indices, timestamp)

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Inserted:  {len(inserted_ids)}")
    print(f"  Updated:   {len(updated_ids)}")
    print(f"  Errors:    {len(errors)}")
    if args.dry_run:
        print(f"  (DRY RUN - no changes written to DB)")
    print()

    if inserted_ids:
        print(f"  Inserted IDs: {inserted_ids}")
    if updated_ids:
        print(f"  Updated IDs: {updated_ids}")
    if errors:
        print("\n  Errors:")
        for e in errors:
            print(f"    - {e}")

    print()
    print("Done.")


if __name__ == "__main__":
    main()
