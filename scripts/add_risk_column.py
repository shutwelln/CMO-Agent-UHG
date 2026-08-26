#!/usr/bin/env python3
"""Add 'Engagement Risk' column to the live outreach sheet and fix column references."""
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

    # --- Get sheet IDs ---
    spreadsheet = sheets.spreadsheets().get(spreadsheetId=SPREADSHEET_ID).execute()
    sheet_ids = {}
    for s in spreadsheet["sheets"]:
        title = s["properties"]["title"]
        sheet_ids[title] = s["properties"]["sheetId"]

    queue_id = sheet_ids["Outreach Queue"]
    archive_id = sheet_ids.get("Archive")

    # --- Step 1: Insert column H (index 7) on Outreach Queue ---
    # This shifts all columns after G (Sensitivity) right by one
    requests = [
        {
            "insertDimension": {
                "range": {
                    "sheetId": queue_id,
                    "dimension": "COLUMNS",
                    "startIndex": 7,  # insert before column H (0-indexed)
                    "endIndex": 8,
                },
                "inheritFromBefore": False,
            }
        },
    ]

    # Do the same for Archive tab if it exists
    if archive_id is not None:
        requests.append(
            {
                "insertDimension": {
                    "range": {
                        "sheetId": archive_id,
                        "dimension": "COLUMNS",
                        "startIndex": 7,
                        "endIndex": 8,
                    },
                    "inheritFromBefore": False,
                }
            }
        )

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests},
    ).execute()
    print("Inserted new column H on Outreach Queue (and Archive)")

    # --- Step 2: Write the header ---
    sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Outreach Queue'!H1",
        valueInputOption="RAW",
        body={"values": [["Engagement Risk"]]},
    ).execute()

    if archive_id is not None:
        sheets.spreadsheets().values().update(
            spreadsheetId=SPREADSHEET_ID,
            range="'Archive'!H1",
            valueInputOption="RAW",
            body={"values": [["Engagement Risk"]]},
        ).execute()

    print("Added 'Engagement Risk' header")

    # --- Step 3: Fix dropdowns (ONE_OF_RANGE → Dropdowns tab, shifted columns) ---
    # Status: was I (8) → now J (9)
    # Claimed By: was J (9) → now K (10)
    # Outcome: was N (13) → now O (14)
    from cmo_agent.outreach.dashboard import build_dropdown_validation_request

    dropdown_requests = [
        build_dropdown_validation_request(queue_id, 9, "Status", end_row=1000),
        build_dropdown_validation_request(queue_id, 10, "Claimed By", end_row=1000),
        build_dropdown_validation_request(queue_id, 14, "Outcome", end_row=1000),
    ]

    sheets.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": dropdown_requests},
    ).execute()
    print("Fixed dropdown validations (ONE_OF_RANGE → Dropdowns tab) for new column positions")

    # --- Step 4: Fix Team Dashboard formulas ---
    # Columns shifted: Claimed By is now K, Status is now J, Outcome is now O, Claimed At is now L
    result = sheets.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID,
        range="'Team Dashboard'!A2:A50",
    ).execute()
    members = [row[0] for row in result.get("values", []) if row]

    formula_rows = []
    for i in range(20):
        row_num = i + 2
        formula_rows.append([
            members[i] if i < len(members) else "",
            f'=IF(A{row_num}="","",COUNTIF(\'Outreach Queue\'!K:K,A{row_num}))',
            f'=IF(A{row_num}="","",COUNTIFS(\'Outreach Queue\'!K:K,A{row_num},\'Outreach Queue\'!J:J,"Responded"))',
            "—",
            f'=IF(A{row_num}="","",IFERROR(COUNTIFS(\'Outreach Queue\'!K:K,A{row_num},\'Outreach Queue\'!O:O,"Connected")/COUNTIFS(\'Outreach Queue\'!K:K,A{row_num},\'Outreach Queue\'!J:J,"Responded"),"N/A"))',
            f'=IF(A{row_num}="","",COUNTIFS(\'Outreach Queue\'!K:K,A{row_num},\'Outreach Queue\'!L:L,">="&TEXT(TODAY()-7,"yyyy-mm-dd")))',
            f'=IF(A{row_num}="","",COUNTIFS(\'Outreach Queue\'!K:K,A{row_num},\'Outreach Queue\'!L:L,">="&TEXT(TODAY()-30,"yyyy-mm-dd")))',
            f'=IF(A{row_num}="","",COUNTIFS(\'Outreach Queue\'!K:K,A{row_num},\'Outreach Queue\'!J:J,"Claimed"))',
        ])

    sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'Team Dashboard'!A2:H21",
        valueInputOption="USER_ENTERED",
        body={"values": formula_rows},
    ).execute()
    print(f"Fixed Team Dashboard formulas for new column positions")

    print("\nDone! Engagement Risk column added and all references updated.")


if __name__ == "__main__":
    main()
