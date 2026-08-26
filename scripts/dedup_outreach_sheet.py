#!/usr/bin/env python3
"""One-time script: remove duplicate rows from Outreach Queue Google Sheet.

Keeps the first occurrence of each Opportunity ID, deletes all subsequent
duplicates. Processes deletions in reverse row order to avoid index shifting.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


async def dedup_sheet() -> None:
    from cmo_agent.config import Settings
    from cmo_agent.outreach.dashboard import OutreachDashboard

    settings = Settings()
    dashboard = OutreachDashboard(
        google_credentials_path="data/saverwell-google-credentials.json",
        google_oauth_token_path="data/google-token.json",
        spreadsheet_id=settings.outreach_spreadsheet_id,
    )
    if not dashboard._get_google_services():
        print("ERROR: Could not initialize Google services")
        return

    sid = settings.outreach_spreadsheet_id

    # Get sheet ID for Outreach Queue
    tabs = await dashboard._get_sheet_tabs_metadata(sid)
    queue_sheet_id = None
    for t in tabs:
        if t["title"] == "Outreach Queue":
            queue_sheet_id = t["sheetId"]
            break

    if queue_sheet_id is None:
        print("ERROR: Outreach Queue tab not found")
        return

    # Read Opportunity ID column (C) to find duplicates
    result = (
        dashboard._sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=sid, range="'Outreach Queue'!C2:C5000")
        .execute()
    )
    rows = result.get("values", [])
    ids = [r[0] if r else "" for r in rows]

    print(f"Total rows: {len(ids)}")

    # Find duplicate row indices (0-based into the rows list)
    seen: set = set()
    dupe_indices: list = []
    for i, oid in enumerate(ids):
        if not oid:
            continue
        if oid in seen:
            dupe_indices.append(i)
        else:
            seen.add(oid)

    print(f"Unique IDs: {len(seen)}")
    print(f"Duplicate rows to delete: {len(dupe_indices)}")

    if not dupe_indices:
        print("No duplicates found!")
        return

    # Delete in batches (Sheets API has a limit on request size)
    # Process in reverse order to avoid index shifting
    dupe_indices.sort(reverse=True)

    batch_size = 100
    total_deleted = 0

    for batch_start in range(0, len(dupe_indices), batch_size):
        batch = dupe_indices[batch_start : batch_start + batch_size]
        delete_requests = []
        for idx in batch:
            # +1 because row 0 in values = sheet row 2 (after header row 1)
            sheet_row = idx + 1
            delete_requests.append(
                {
                    "deleteDimension": {
                        "range": {
                            "sheetId": queue_sheet_id,
                            "dimension": "ROWS",
                            "startIndex": sheet_row,
                            "endIndex": sheet_row + 1,
                        }
                    }
                }
            )

        dashboard._sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=sid,
            body={"requests": delete_requests},
        ).execute()
        total_deleted += len(batch)
        print(f"  Deleted batch: {len(batch)} rows (total: {total_deleted})")

    # Verify
    result = (
        dashboard._sheets_service.spreadsheets()
        .values()
        .get(spreadsheetId=sid, range="'Outreach Queue'!C2:C5000")
        .execute()
    )
    remaining = result.get("values", [])
    remaining_ids = [r[0] for r in remaining if r and r[0]]
    print(f"\nAfter cleanup: {len(remaining_ids)} rows, {len(set(remaining_ids))} unique")
    if len(remaining_ids) != len(set(remaining_ids)):
        print("WARNING: Some duplicates remain!")


if __name__ == "__main__":
    asyncio.run(dedup_sheet())
