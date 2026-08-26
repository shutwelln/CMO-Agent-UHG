#!/usr/bin/env python3
"""Update the DSDN Outreach Sheet: add dropdown validation + Team Dashboard formulas."""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SPREADSHEET_ID = "1-G_t2waz2JiOdNbhinpHgb2iemUwrcK3uztNeU-HJUY"


def main():
    from googleapiclient.discovery import build
    from cmo_agent.google_auth import get_google_credentials

    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path=sa_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    sheets = build("sheets", "v4", credentials=creds)

    # --- Step 1: Get sheet IDs ---
    spreadsheet = sheets.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_ids = {}
    for s in spreadsheet["sheets"]:
        title = s["properties"]["title"]
        sheet_ids[title] = s["properties"]["sheetId"]

    queue_id = sheet_ids["Outreach Queue"]
    team_id = sheet_ids["Team Dashboard"]

    print(f"Outreach Queue sheet ID: {queue_id}")
    print(f"Team Dashboard sheet ID: {team_id}")

    # --- Step 2: Add data validation dropdowns (ONE_OF_RANGE → Dropdowns tab) ---
    from cmo_agent.outreach.dashboard import build_dropdown_validation_request

    requests = [
        build_dropdown_validation_request(queue_id, 8, "Status", end_row=1000),
        build_dropdown_validation_request(queue_id, 9, "Claimed By", end_row=1000),
        build_dropdown_validation_request(queue_id, 13, "Outcome", end_row=1000),
    ]

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests},
    ).execute()
    print("Added dropdowns (ONE_OF_RANGE → Dropdowns tab): Status, Claimed By, Outcome")

    # --- Step 3: Replace Team Dashboard with live formulas ---
    # Row 1 = headers (already there), Row 2+ = team members with formulas
    # Read current team members from A2:A50
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Team Dashboard'!A2:A50",
    ).execute()
    members = [row[0] for row in result.get("values", []) if row]

    if not members:
        print("No team members found in Team Dashboard. Skipping formulas.")
        return

    formula_rows = []
    for i, member in enumerate(members):
        row_num = i + 2  # row 2, 3, etc.
        # A = Team Member name (keep as-is)
        # B = Posts Claimed: count where Claimed By (col J) matches this member
        # C = Posts Responded: count where Claimed By matches AND Status = "Responded"
        # D = Avg Response Time: placeholder (would need timestamps)
        # E = Connected Rate: Connected outcomes / Posts Responded
        # F = This Week: Claimed in last 7 days
        # G = This Month: Claimed in last 30 days
        # H = Pending Claims: Claimed by this member AND Status = "Claimed" (not yet responded)
        formula_rows.append([
            member,
            f'=COUNTIF(\'Outreach Queue\'!J:J,A{row_num})',
            f'=COUNTIFS(\'Outreach Queue\'!J:J,A{row_num},\'Outreach Queue\'!I:I,"Responded")',
            "—",  # Avg response time placeholder
            f'=IFERROR(COUNTIFS(\'Outreach Queue\'!J:J,A{row_num},\'Outreach Queue\'!N:N,"Connected")/COUNTIFS(\'Outreach Queue\'!J:J,A{row_num},\'Outreach Queue\'!I:I,"Responded"),"N/A")',
            f'=COUNTIFS(\'Outreach Queue\'!J:J,A{row_num},\'Outreach Queue\'!K:K,">="&TEXT(TODAY()-7,"yyyy-mm-dd"))',
            f'=COUNTIFS(\'Outreach Queue\'!J:J,A{row_num},\'Outreach Queue\'!K:K,">="&TEXT(TODAY()-30,"yyyy-mm-dd"))',
            f'=COUNTIFS(\'Outreach Queue\'!J:J,A{row_num},\'Outreach Queue\'!I:I,"Claimed")',
        ])

    sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'Team Dashboard'!A2:H{1 + len(formula_rows)}",
        valueInputOption="USER_ENTERED",  # important: interprets formulas
        body={"values": formula_rows},
    ).execute()
    print(f"Added live formulas for {len(members)} team member(s)")

    print("\nDone! Spreadsheet updated.")


if __name__ == "__main__":
    main()
