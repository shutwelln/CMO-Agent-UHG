"""Create the 'Saverwell Content Queue' Google Sheet.

3 tabs:
1. Article Library - all 33 articles with priority, seasonal boost, email_ready
2. Seasonal Calendar - 5 seasonal windows
3. Send Log - empty with headers

Usage:
    python scripts/create_content_queue_sheet.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

# Article data: (slug, title, category, vertical, base_priority, send_day,
#                seasonal_boost_start, seasonal_boost_end, seasonal_boost_amount, notes)
PROTECTION_ARTICLES = [
    ("safe-online-shopping-tips", "Safe Online Shopping Tips for Seniors", "protection", "fraud", 9, "tuesday", "2026-11-01", "2026-12-31", "+2", "Holiday shopping boost"),
    ("password-safety-guide", "Password Safety: A Practical Guide for Older Adults", "protection", "fraud", 8, "tuesday", "", "", "", ""),
    ("bank-impostor-calls", "Bank Impostor Calls: When Scammers Pretend to Be Your Bank", "protection", "fraud", 8, "tuesday", "", "", "", ""),
    ("subscription-traps-unauthorized-charges", "Subscription Traps and Unauthorized Charges", "protection", "fraud", 7, "tuesday", "", "", "", ""),
    ("email-account-hacked", "What to Do If Your Email Account Is Hacked", "protection", "fraud", 7, "tuesday", "", "", "", ""),
    ("what-to-do-after-a-data-breach", "What to Do After a Data Breach", "protection", "fraud", 7, "tuesday", "", "", "", "Reactive boost for breach events"),
    ("two-factor-authentication-guide", "Two-Factor Authentication: An Extra Lock on Your Accounts", "protection", "fraud", 6, "tuesday", "", "", "", ""),
    ("tax-identity-theft", "Tax Identity Theft: Protecting Your Tax Refund", "protection", "fraud", 6, "tuesday", "2026-01-15", "2026-04-15", "+3", "Tax season boost"),
    ("how-to-spot-fake-websites", "How to Spot a Fake Website", "protection", "fraud", 7, "tuesday", "2026-11-01", "2026-12-31", "+2", "Holiday shopping boost"),
    ("peer-to-peer-payment-scams", "Peer-to-Peer Payment Scams: Staying Safe with Zelle, Venmo, and CashApp", "protection", "fraud", 6, "tuesday", "", "", "", ""),
    ("account-takeover-prevention", "Account Takeover: How to Protect Your Bank Login", "protection", "fraud", 6, "tuesday", "", "", "", ""),
    ("fake-check-overpayment-scams", "Fake Check and Overpayment Scams", "protection", "fraud", 5, "tuesday", "", "", "", ""),
    ("smartphone-security-for-seniors", "Smartphone Security for Seniors", "protection", "fraud", 6, "tuesday", "", "", "", ""),
    ("how-to-freeze-your-credit", "How to Freeze Your Credit: A Step-by-Step Guide", "protection", "fraud", 7, "tuesday", "", "", "", "Reactive boost for breach events"),
    ("wire-transfer-fraud", "Wire Transfer Fraud: Protecting Your Retirement Savings", "protection", "fraud", 5, "tuesday", "", "", "", ""),
    ("gift-card-scams", "Gift Card Scams: Why Scammers Want You to Pay with Gift Cards", "protection", "fraud", 5, "tuesday", "2026-11-01", "2026-12-31", "+2", "Holiday shopping boost"),
    ("protecting-your-social-security-number", "Protecting Your Social Security Number", "protection", "fraud", 6, "tuesday", "", "", "", ""),
    ("medicare-identity-theft", "Medicare Identity Theft: How to Protect Your Benefits", "protection", "medicare", 6, "tuesday", "2026-10-01", "2026-12-07", "+3", "AEP cross-over: protection angle on Medicare fraud"),
    ("reading-your-credit-report", "Reading Your Credit Report: How to Spot Identity Theft", "protection", "fraud", 5, "tuesday", "", "", "", "Reactive boost for breach events"),
    ("charity-scams", "Charity Scams: How to Spot Fake Charities", "protection", "fraud", 4, "tuesday", "2026-11-01", "2026-12-31", "+2", "Holiday giving season"),
    ("shared-verification-code-with-scammer", "I Shared a Verification Code with a Scammer: What to Do Now", "protection", "fraud", 5, "tuesday", "", "", "", ""),
]

GUIDE_ARTICLES = [
    ("medicare-explained-simple-guide", "Medicare Explained: A Simple Guide for Seniors", "guide", "medicare", 9, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP top priority"),
    ("medicare-parts-a-b-c-d-explained", "Medicare Parts A, B, C, and D: What Each One Covers", "guide", "medicare", 8, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP top priority"),
    ("save-money-medicare-premiums", "7 Ways to Save Money on Medicare Premiums", "guide", "medicare", 9, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP top priority - broker referral CTA"),
    ("medicare-enrollment-deadlines", "Medicare Enrollment Deadlines You Can't Afford to Miss", "guide", "medicare", 10, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP highest priority - deadline urgency"),
    ("medicare-advantage-vs-original", "Medicare Advantage vs. Original Medicare: Which Saves You More?", "guide", "medicare", 8, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP top priority - broker referral CTA"),
    ("does-medicare-cover-prescriptions", "Does Medicare Cover Prescriptions? Understanding Part D", "guide", "medicare", 7, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP boost"),
    ("medicare-vs-medicaid-difference", "Medicare vs. Medicaid: What's the Difference?", "guide", "medicare", 7, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP boost"),
    ("does-medicare-cover-dental", "Does Medicare Cover Dental? What Seniors Need to Know", "guide", "medicare", 6, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP boost"),
    ("does-medicare-cover-vision", "Does Medicare Cover Vision? Glasses, Exams, and Eye Care", "guide", "medicare", 6, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP boost"),
    ("does-medicare-cover-hearing-aids", "Does Medicare Cover Hearing Aids? Your Options Explained", "guide", "medicare", 6, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP boost"),
    ("irmaa-avoid-higher-medicare-premiums", "IRMAA: How to Avoid Higher Medicare Premiums", "guide", "medicare", 5, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP boost"),
    ("medicare-extra-help-prescription-savings", "Medicare Extra Help: Save on Prescription Drug Costs", "guide", "medicare", 5, "thursday", "2026-10-01", "2026-12-07", "+5", "AEP boost"),
]

SEASONAL_CALENDAR = [
    ("Medicare AEP", "2026-10-01", "2026-12-07", "medicare", "+5", "Biggest monetization window. Broker referral CTAs. Ramp-up starts Oct 1."),
    ("Medicare OEP", "2027-01-01", "2027-03-31", "medicare", "+3", "Medicare Advantage switching. Secondary monetization window."),
    ("Tax Season", "2027-01-15", "2027-04-15", "fraud, finance", "+3", "Tax identity theft, tax deduction guides."),
    ("Holiday Shopping", "2026-11-01", "2026-12-31", "fraud", "+2", "Online shopping scams, gift card fraud."),
    ("Data Breach (Reactive)", "", "", "fraud", "+4", "Manually set dates when major breaches announced."),
]


def main() -> None:
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
        share_file_restricted,
    )

    oauth_path = "/Users/nickshutwell/Desktop/CMO Agent/data/google-token.json"
    SCOPES = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    credentials = get_google_credentials(
        oauth_token_path=oauth_path, service_account_path="", scopes=SCOPES
    )
    if credentials is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    from googleapiclient.discovery import build

    sheets_service = build("sheets", "v4", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    print("Creating 'Saverwell Content Queue' Google Sheet...")

    # 1. Create spreadsheet with 3 tabs
    spreadsheet = sheets_service.spreadsheets().create(
        body={
            "properties": {"title": "Saverwell Content Queue"},
            "sheets": [
                {"properties": {"title": "Article Library", "index": 0}},
                {"properties": {"title": "Seasonal Calendar", "index": 1}},
                {"properties": {"title": "Send Log", "index": 2}},
            ],
        }
    ).execute()

    sheet_id = spreadsheet["spreadsheetId"]
    print(f"  Sheet created: {sheet_id}")

    # 2. Populate Article Library tab
    article_headers = [
        "slug", "title", "category", "vertical", "base_priority",
        "send_day", "seasonal_boost_start", "seasonal_boost_end",
        "seasonal_boost_amount", "email_ready", "total_sends", "notes",
    ]

    article_rows = []
    for a in PROTECTION_ARTICLES:
        article_rows.append([
            a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8],
            "TRUE", 0, a[9],
        ])
    for a in GUIDE_ARTICLES:
        article_rows.append([
            a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7], a[8],
            "TRUE", 0, a[9],
        ])

    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Article Library'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [article_headers] + article_rows},
    ).execute()
    print(f"  Article Library: {len(article_rows)} articles populated")

    # 3. Populate Seasonal Calendar tab
    seasonal_headers = [
        "season", "start_date", "end_date", "boost_verticals",
        "boost_amount", "notes",
    ]
    seasonal_rows = [list(s) for s in SEASONAL_CALENDAR]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Seasonal Calendar'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [seasonal_headers] + seasonal_rows},
    ).execute()
    print(f"  Seasonal Calendar: {len(seasonal_rows)} seasons populated")

    # 4. Populate Send Log tab (headers only)
    send_log_headers = [
        "send_date", "article_slug", "category", "segment_size",
        "send_type", "seasonal_context",
    ]

    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Send Log'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": [send_log_headers]},
    ).execute()
    print("  Send Log: headers written")

    # 5. Format: bold headers, freeze header row, auto-resize columns
    article_sheet_id = spreadsheet["sheets"][0]["properties"]["sheetId"]
    seasonal_sheet_id = spreadsheet["sheets"][1]["properties"]["sheetId"]
    send_log_sheet_id = spreadsheet["sheets"][2]["properties"]["sheetId"]

    format_requests = []
    for sid, cols in [
        (article_sheet_id, len(article_headers)),
        (seasonal_sheet_id, len(seasonal_headers)),
        (send_log_sheet_id, len(send_log_headers)),
    ]:
        # Bold header row
        format_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sid,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": {
                            "red": 0.9, "green": 0.9, "blue": 0.9,
                        },
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })
        # Freeze header row
        format_requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sid,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        })
        # Auto-resize columns
        format_requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": sid,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": cols,
                },
            }
        })

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": format_requests},
    ).execute()
    print("  Formatting applied (bold headers, frozen rows, auto-resize)")

    # 6. Share (restricted access)
    share_file_restricted(drive_service, sheet_id)

    # 7. Move to CMO Agent folder
    folder_id = ensure_drive_folder(drive_service)
    if folder_id:
        move_file_to_folder(drive_service, sheet_id, folder_id)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    print(f"\nGoogle Sheet created successfully!")
    print(f"URL: {sheet_url}")


if __name__ == "__main__":
    main()
