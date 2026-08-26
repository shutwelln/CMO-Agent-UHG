#!/usr/bin/env python3
"""Fix Sheet: full post content, all dropdowns, auto-timestamp Apps Script.

Addresses:
1. Column C (Post Title/Summary): replace 200-char truncated text with full post
2. Column J (Status): restore dropdown — New, Claimed, Draft Generated, Responded, Skipped
3. Column L (Claimed By): add dropdown with team members
4. Column O (Outcome): restore dropdown — Connected, No Response, Declined, etc.
5. Install Apps Script: auto-populate column K (Claimed Date/Time) when L is changed
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


async def main():
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database

    settings = Settings()
    db = Database(db_path=settings.db_path)
    await db.initialize()

    # ── Google Sheets auth ──────────────────────────────────────────
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json")
    )
    creds = Credentials.from_authorized_user_file(
        oauth_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)
    spreadsheet_id = settings.outreach_spreadsheet_id

    # ── Get Sheet ID for Outreach Queue tab ─────────────────────────
    sheet_meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties"
    ).execute()
    queue_sheet_id = None
    for sheet in sheet_meta.get("sheets", []):
        if sheet["properties"]["title"] == "Outreach Queue":
            queue_sheet_id = sheet["properties"]["sheetId"]
            break

    if queue_sheet_id is None:
        print("ERROR: Could not find 'Outreach Queue' tab")
        return

    # ── Read existing Sheet rows ────────────────────────────────────
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="'Outreach Queue'!A2:P5000")
        .execute()
    )
    sheet_rows = result.get("values", [])
    print(f"Sheet rows: {len(sheet_rows)}")

    # Map opp_id (col P = index 15) → row number
    opp_id_to_row: Dict[str, int] = {}
    for i, row in enumerate(sheet_rows):
        if len(row) >= 16 and row[15]:
            opp_id_to_row[row[15]] = i + 2

    # ── Phase 1: Fix Post Title/Summary with full content ───────────
    print("\n=== Phase 1: Updating full post content ===")

    db_rows = await db.fetchall(
        "SELECT id, title, content FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND category = 'outreach'",
        (),
    )

    cell_updates: List[Dict[str, Any]] = []
    content_updated = 0
    for row in db_rows:
        opp_id = row["id"]
        if opp_id not in opp_id_to_row:
            continue

        title = row["title"] or ""
        content = row["content"] or ""
        full_post = (title + "\n\n" + content).strip() if content else title
        sheet_row = opp_id_to_row[opp_id]

        cell_updates.append({
            "range": f"'Outreach Queue'!C{sheet_row}",
            "values": [[full_post]],
        })
        content_updated += 1

    print(f"  Full post content prepared: {content_updated} rows")

    # ── Phase 2: Push all cell updates ──────────────────────────────
    if cell_updates:
        print(f"\n=== Phase 2: Pushing {len(cell_updates)} cell updates ===")
        for i in range(0, len(cell_updates), 100):
            chunk = cell_updates[i : i + 100]
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "RAW", "data": chunk},
            ).execute()
            print(f"  ...pushed {min(i + 100, len(cell_updates))}/{len(cell_updates)}")

    # ── Phase 3: Apply all dropdown validations ─────────────────────
    print("\n=== Phase 3: Applying dropdown validations ===")

    data_row_count = len(sheet_rows)
    end_row = max(data_row_count + 51, 200)  # Cover future rows

    from cmo_agent.outreach.dashboard import build_dropdown_validation_request

    dropdown_requests = [
        build_dropdown_validation_request(queue_sheet_id, 9, "Status", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 11, "Claimed By", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 14, "Outcome", end_row=end_row),
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": dropdown_requests},
    ).execute()
    print("  Dropdowns applied (ONE_OF_RANGE → Dropdowns tab): Status (J), Claimed By (L), Outcome (O)")

    await db.close()

    # ── Phase 4: Print Apps Script instructions ─────────────────────
    print("\n=== Phase 4: Apps Script for auto-timestamp ===")
    print(
        "To auto-populate 'Claimed Date/Time' (K) when 'Claimed By' (L) is selected,\n"
        "install this Apps Script in your Google Sheet:\n"
        "\n"
        "  1. Open the Sheet\n"
        "  2. Extensions > Apps Script\n"
        "  3. Replace Code.gs contents with:\n"
    )
    print(APPS_SCRIPT)
    print(
        "\n  4. Click Save (disk icon)\n"
        "  5. Close the Apps Script editor\n"
        "  6. The timestamp will auto-populate when you select a name in Claimed By\n"
    )

    print(f"\n{'='*60}")
    print("All fixes applied!")
    print(f"  Full post content updated: {content_updated} rows")
    print(f"  Dropdowns applied: Status, Claimed By, Outcome")
    print(f"  Apps Script: copy from above into Extensions > Apps Script")
    print(f"{'='*60}")


APPS_SCRIPT = '''\
/**
 * Auto-populate "Claimed Date/Time" (column K) when "Claimed By" (column L)
 * is selected on the Outreach Queue tab.
 *
 * This runs automatically on every edit via onEdit trigger.
 */
function onEdit(e) {
  var sheet = e.source.getActiveSheet();
  var range = e.range;

  // Only run on the "Outreach Queue" tab
  if (sheet.getName() !== "Outreach Queue") return;

  // Column L = 12 (Claimed By)
  if (range.getColumn() !== 12) return;

  // Skip header row
  if (range.getRow() <= 1) return;

  var claimedBy = range.getValue();
  var timestampCell = sheet.getRange(range.getRow(), 11); // Column K

  if (claimedBy && claimedBy.toString().trim() !== "") {
    // Only set timestamp if it's currently empty (don't overwrite)
    if (!timestampCell.getValue()) {
      timestampCell.setValue(new Date());
      timestampCell.setNumberFormat("yyyy-MM-dd HH:mm:ss");
    }
  }
}
'''


if __name__ == "__main__":
    asyncio.run(main())
