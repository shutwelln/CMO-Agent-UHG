#!/usr/bin/env python3
"""Merge Revenue Dashboard tabs into the existing Affiliate Research Sheet.

Adds 3 new tabs (Partner Promotions, Guide Performance, Monthly Summary) to the
existing Affiliate Research Sheet. Idempotent - skips any tab that already exists.
Does NOT touch the existing Affiliate Research tab.

Sheet ID: 1oOd2TzHn-DRAOPnGE9II2RG74HuPK_7k3fPnALOTRf4

Usage:
    python scripts/merge_revenue_tabs.py
    python scripts/merge_revenue_tabs.py --spreadsheet-id <ID>
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

DEFAULT_SHEET_ID = "1oOd2TzHn-DRAOPnGE9II2RG74HuPK_7k3fPnALOTRf4"


def get_sheets_service():
    """Build Google Sheets API service using OAuth (sheet owned by personal account)."""
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import get_google_credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = get_google_credentials(
        oauth_token_path=os.environ.get(
            "GOOGLE_OAUTH_TOKEN_PATH", "data/google-token.json"
        ),
        service_account_path="",  # Force OAuth - sheet is owned by personal account
        scopes=scopes,
    )
    if creds is None:
        print(
            "ERROR: No Google credentials. "
            "Run scripts/reauth_google_drive.py first."
        )
        sys.exit(1)
    return build("sheets", "v4", credentials=creds)


def get_existing_tabs(service, spreadsheet_id: str) -> dict:
    """Return {tab_name: sheet_id} for all existing tabs."""
    meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
        .execute()
    )
    tabs = {}
    for sheet in meta.get("sheets", []):
        props = sheet.get("properties", {})
        tabs[props["title"]] = props["sheetId"]
    return tabs


def add_tab(service, spreadsheet_id: str, title: str, index: int) -> int:
    """Add a new tab and return its sheetId."""
    result = (
        service.spreadsheets()
        .batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "requests": [
                    {"addSheet": {"properties": {"title": title, "index": index}}}
                ]
            },
        )
        .execute()
    )
    return result["replies"][0]["addSheet"]["properties"]["sheetId"]


def main():
    parser = argparse.ArgumentParser(
        description="Add revenue tracking tabs to Affiliate Research Sheet"
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=os.environ.get("AFFILIATE_RESEARCH_SHEET_ID", DEFAULT_SHEET_ID),
        help="Google Sheets spreadsheet ID",
    )
    args = parser.parse_args()
    spreadsheet_id = args.spreadsheet_id

    service = get_sheets_service()

    # ── Check existing tabs ──────────────────────────────────────────
    existing = get_existing_tabs(service, spreadsheet_id)
    print(f"Existing tabs: {list(existing.keys())}")

    # Next index after existing tabs
    next_index = len(existing)

    # ── Tab definitions ──────────────────────────────────────────────
    tabs_to_add = {
        "Partner Promotions": {
            "headers": [
                "Partner Name",
                "Partner Slug",
                "Promotion Type",
                "Headline",
                "CTA Text",
                "Target Categories",
                "Position",
                "Status",
                "Commission Type",
                "Est. Commission",
                "Impressions (MTD)",
                "Clicks (MTD)",
                "CTR",
                "Revenue (MTD)",
            ],
            "rows": [
                [
                    "SelectQuote",
                    "selectquote",
                    "click_to_call",
                    "Have Medicare Questions?",
                    "Call Now",
                    "medicare",
                    "after_overview",
                    "Inactive",
                    "CPL",
                    "$50-200/lead",
                    "0",
                    "0",
                    "",
                    "$0.00",
                ],
                [
                    "ADT",
                    "adt",
                    "cta_banner",
                    "Get 24/7 Medical Alert Protection",
                    "Check Rates",
                    "medical-alerts",
                    "after_comparison",
                    "Inactive",
                    "CPA",
                    "$5-20/mo recurring",
                    "0",
                    "0",
                    "",
                    "$0.00",
                ],
                [
                    "Hear.com",
                    "hearcom",
                    "cta_banner",
                    "Save on Premium Hearing Aids",
                    "Get a Free Consultation",
                    "hearing-aids",
                    "after_comparison",
                    "Inactive",
                    "CPS",
                    "$75-300/sale",
                    "0",
                    "0",
                    "",
                    "$0.00",
                ],
                [
                    "Insurify",
                    "insurify",
                    "lead_gen_form",
                    "Compare Insurance Rates in Minutes",
                    "Compare Rates Free",
                    "insurance",
                    "after_overview",
                    "Inactive",
                    "CPL",
                    "$20-150/lead",
                    "0",
                    "0",
                    "",
                    "$0.00",
                ],
                [
                    "American Home Shield",
                    "ahs",
                    "cta_banner",
                    "Get a Free Home Warranty Quote",
                    "Get Your Free Quote",
                    "insurance",
                    "end_of_article",
                    "Inactive",
                    "CPA",
                    "$30-75/sale",
                    "0",
                    "0",
                    "",
                    "$0.00",
                ],
                [
                    "AARP",
                    "aarp",
                    "cta_banner",
                    "Join AARP and Start Saving",
                    "Join AARP Today",
                    "finance",
                    "after_overview",
                    "Inactive",
                    "CPA",
                    "$5-15/signup",
                    "0",
                    "0",
                    "",
                    "$0.00",
                ],
                [
                    "Chime",
                    "chime",
                    "cta_banner",
                    "Bank Smarter with Chime",
                    "Open Your Account",
                    "finance",
                    "after_overview",
                    "Inactive",
                    "CPA",
                    "TBD - contract pending",
                    "0",
                    "0",
                    "",
                    "$0.00",
                ],
            ],
        },
        "Guide Performance": {
            "headers": [
                "Guide Slug",
                "Guide Title",
                "Category",
                "Has Partner Promo",
                "Has Affiliate Links",
                "Pageviews (MTD)",
                "Affiliate Clicks (MTD)",
                "Partner Promo Clicks (MTD)",
                "Estimated Revenue (MTD)",
            ],
            "rows": [
                [
                    "home-warranty-explained",
                    "Home Warranty Plans: What They Cover, What They Cost, and What to Watch For",
                    "insurance",
                    "Yes",
                    "No",
                    "0",
                    "0",
                    "0",
                    "$0.00",
                ],
                [
                    "home-warranty-vs-home-insurance",
                    "Home Warranty vs. Home Insurance: What's the Difference?",
                    "insurance",
                    "Yes",
                    "No",
                    "0",
                    "0",
                    "0",
                    "$0.00",
                ],
                [
                    "best-home-warranty-seniors",
                    "Home Warranty for Seniors: How to Choose the Right Plan",
                    "insurance",
                    "Yes",
                    "Yes",
                    "0",
                    "0",
                    "0",
                    "$0.00",
                ],
                [
                    "is-aarp-membership-worth-it",
                    "Is an AARP Membership Worth It? A Savings Breakdown",
                    "finance",
                    "Yes",
                    "Yes",
                    "0",
                    "0",
                    "0",
                    "$0.00",
                ],
                [
                    "aarp-discounts-complete-list",
                    "AARP Discounts: The Complete List for 2026",
                    "finance",
                    "Yes",
                    "Yes",
                    "0",
                    "0",
                    "0",
                    "$0.00",
                ],
            ],
        },
        "Monthly Summary": {
            "headers": [
                "Month",
                "Partner Revenue",
                "Affiliate Revenue",
                "Guide Revenue",
                "Total Revenue",
                "Total Pageviews",
                "Revenue Per Pageview",
            ],
            "rows": [
                ["2026-03", "$0.00", "$0.00", "$0.00", "$0.00", "0", "$0.00"],
            ],
        },
    }

    # ── Create tabs + populate ───────────────────────────────────────
    new_sheet_ids = {}

    for tab_name, tab_data in tabs_to_add.items():
        if tab_name in existing:
            print(f"  Tab '{tab_name}' already exists. Skipping.")
            new_sheet_ids[tab_name] = existing[tab_name]
            continue

        print(f"  Adding tab: {tab_name}")
        sheet_id = add_tab(service, spreadsheet_id, tab_name, next_index)
        new_sheet_ids[tab_name] = sheet_id
        next_index += 1

        # Populate headers + seed rows
        values = [tab_data["headers"]] + tab_data["rows"]
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A1",
            valueInputOption="RAW",
            body={"values": values},
        ).execute()
        print(f"    Populated {len(tab_data['rows'])} rows")

    # ── Format all new tabs ──────────────────────────────────────────
    format_requests = []

    for tab_name, tab_data in tabs_to_add.items():
        sid = new_sheet_ids.get(tab_name)
        if sid is None:
            continue

        num_cols = len(tab_data["headers"])

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

        # Auto-resize columns
        format_requests.append(
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sid,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": num_cols,
                    }
                }
            }
        )

    if format_requests:
        service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": format_requests},
        ).execute()
        print("  Formatting applied (bold headers, frozen rows, auto-resize)")

    print(
        f"\nDone! Affiliate Research + Revenue Dashboard: "
        f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    )


if __name__ == "__main__":
    main()
