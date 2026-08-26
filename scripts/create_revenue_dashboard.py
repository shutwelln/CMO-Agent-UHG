"""Create Saverwell Revenue Dashboard Google Sheet.

Uses the project's google_auth module and service account credentials.
"""

import os
import sys

# Add src to path so we can import cmo_agent
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from googleapiclient.discovery import build
from cmo_agent.google_auth import get_google_credentials, share_file_restricted


def main():
    # ── Authenticate ───────────────────────────────────────────────────
    # Force OAuth (service_account_path="") — service accounts can't create
    # spreadsheets owned by a personal account.
    creds = get_google_credentials(
        oauth_token_path="data/google-token.json",
        service_account_path="",
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    if creds is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    sheets_service = build("sheets", "v4", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    # ── Define tabs ────────────────────────────────────────────────────
    tab_names = [
        "Partner Promotions",
        "Affiliate Merchants",
        "Guide Performance",
        "Monthly Summary",
    ]

    spreadsheet_body = {
        "properties": {"title": "Saverwell Revenue Dashboard"},
        "sheets": [
            {"properties": {"title": name, "index": i}}
            for i, name in enumerate(tab_names)
        ],
    }

    # ── Create spreadsheet ─────────────────────────────────────────────
    result = (
        sheets_service.spreadsheets()
        .create(body=spreadsheet_body, fields="spreadsheetId,spreadsheetUrl,sheets")
        .execute()
    )

    spreadsheet_id = result["spreadsheetId"]
    spreadsheet_url = result["spreadsheetUrl"]
    created_sheets = result["sheets"]

    # Build sheet_id lookup
    sheet_ids = {}
    for sheet in created_sheets:
        props = sheet["properties"]
        sheet_ids[props["title"]] = props["sheetId"]

    print(f"Created spreadsheet: {spreadsheet_id}")

    # ── Tab 1: Partner Promotions ──────────────────────────────────────
    partner_headers = [
        "Partner Name",
        "Promotion Type",
        "Target Categories",
        "Position",
        "Status",
        "Impressions (MTD)",
        "Clicks (MTD)",
        "CTR",
        "Revenue (MTD)",
        "Notes",
    ]
    partner_rows = [
        ["SelectQuote", "", "", "", "", "0", "0", "0%", "$0.00", ""],
        ["ADT", "", "", "", "", "0", "0", "0%", "$0.00", ""],
        ["Hear.com", "", "", "", "", "0", "0", "0%", "$0.00", ""],
        ["Insurify", "", "", "", "", "0", "0", "0%", "$0.00", ""],
        ["AHS", "", "", "", "", "0", "0", "0%", "$0.00", ""],
        ["AARP", "", "", "", "", "0", "0", "0%", "$0.00", ""],
    ]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="'Partner Promotions'!A1",
        valueInputOption="RAW",
        body={"values": [partner_headers] + partner_rows},
    ).execute()

    # ── Tab 2: Affiliate Merchants ─────────────────────────────────────
    affiliate_headers = [
        "Merchant",
        "Category",
        "Network",
        "Commission Rate",
        "Approval Status",
        "Monthly Clicks",
        "Monthly Revenue",
        "Affiliate URL",
    ]
    affiliate_rows = [
        ["AT&T", "", "", "", "", "0", "$0.00", ""],
        ["Verizon", "", "", "", "", "0", "$0.00", ""],
        ["Walgreens", "", "", "", "", "0", "$0.00", ""],
        ["LensCrafters", "", "", "", "", "0", "$0.00", ""],
        ["Valvoline", "", "", "", "", "0", "$0.00", ""],
        ["Best Western", "", "", "", "", "0", "$0.00", ""],
        ["Marriott", "", "", "", "", "0", "$0.00", ""],
        ["Hertz", "", "", "", "", "0", "$0.00", ""],
    ]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="'Affiliate Merchants'!A1",
        valueInputOption="RAW",
        body={"values": [affiliate_headers] + affiliate_rows},
    ).execute()

    # ── Tab 3: Guide Performance ───────────────────────────────────────
    guide_headers = [
        "Guide Slug",
        "Category",
        "Page Views (MTD)",
        "Partner Promo Clicks",
        "Affiliate Clicks",
        "Revenue",
        "Top Partner",
    ]
    guide_rows = [
        ["home-warranty-explained", "", "0", "0", "0", "$0.00", ""],
        ["home-warranty-vs-home-insurance", "", "0", "0", "0", "$0.00", ""],
        ["best-home-warranty-seniors", "", "0", "0", "0", "$0.00", ""],
        ["is-aarp-membership-worth-it", "", "0", "0", "0", "$0.00", ""],
        ["aarp-discounts-complete-list", "", "0", "0", "0", "$0.00", ""],
    ]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="'Guide Performance'!A1",
        valueInputOption="RAW",
        body={"values": [guide_headers] + guide_rows},
    ).execute()

    # ── Tab 4: Monthly Summary ─────────────────────────────────────────
    summary_headers = [
        "Month",
        "Total Page Views",
        "Partner Promo Impressions",
        "Partner Promo Clicks",
        "Affiliate Clicks",
        "Total Revenue",
        "Top Partner",
        "Top Guide",
    ]
    summary_rows = [
        ["March 2026", "0", "0", "0", "0", "$0.00", "", ""],
    ]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="'Monthly Summary'!A1",
        valueInputOption="RAW",
        body={"values": [summary_headers] + summary_rows},
    ).execute()

    # ── Apply formatting: bold headers + freeze rows ───────────────────
    format_requests = []

    tab_col_counts = {
        "Partner Promotions": len(partner_headers),
        "Affiliate Merchants": len(affiliate_headers),
        "Guide Performance": len(guide_headers),
        "Monthly Summary": len(summary_headers),
    }

    for tab_name, num_cols in tab_col_counts.items():
        sid = sheet_ids[tab_name]

        # Bold header row with light gray background
        format_requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": num_cols,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {
                                "red": 0.9,
                                "green": 0.9,
                                "blue": 0.9,
                            },
                            "horizontalAlignment": "CENTER",
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment)",
                }
            }
        )

        # Freeze header row
        format_requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sid,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        )

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": format_requests},
    ).execute()

    # ── Share with authorized users ────────────────────────────────────
    share_file_restricted(drive_service, spreadsheet_id)

    print(f"\nSaverwell Revenue Dashboard created successfully!")
    print(f"URL: {spreadsheet_url}")


if __name__ == "__main__":
    main()
