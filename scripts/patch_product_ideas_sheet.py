"""Patch the existing Product Ideas sheet: add Traffic Impact, Build Effort,
Competitive Moat columns to the main tab, then delete the Priority Matrix tab.
"""

import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'google-token.json'
)

SPREADSHEET_ID = "13pe8PKVlkcUZJSd97j-GpfqbAcWRRw-bFcZPToVWpz4"

# Traffic Impact, Build Effort, Competitive Moat for each of the 30 ideas (same order)
EXTRA_DATA = [
    ["Traffic Impact", "Build Effort", "Competitive Moat"],
    ["Low", "Low", "High"],              # 1. SMS Reminders
    ["Low", "Low", "Low"],               # 2. Affiliate Layer
    ["Medium", "Medium", "Medium"],      # 3. Savings Calculator
    ["Medium", "Medium", "High"],        # 4. Scam Alert Feed
    ["High", "Medium", "Medium"],        # 5. Medicare AEP Hub
    ["Medium", "Medium", "Medium"],      # 6. Personalized Newsletter
    ["Low", "Low (biz dev)", "Very High"],  # 7. Merchant Partnerships
    ["Low", "Medium", "Very High"],      # 8. Community Submissions
    ["Medium", "Low", "Medium"],         # 9. Widget
    ["Low", "Medium", "High"],           # 10. Savings Tracker
    ["Very High", "Low", "High"],        # 11. Merchant Page Expansion
    ["High", "Medium", "Very High"],     # 12. Senior Discount Day Calendar
    ["High", "Low", "Medium"],           # 13. Category Landing Pages
    ["High", "Medium", "Medium"],        # 14. Seasonal Savings Hubs
    ["High", "Medium", "High"],          # 15. Property Tax by State
    ["Low", "Medium", "High"],           # 16. Library Content Kit
    ["Medium", "Low", "High"],           # 17. Financial Advisor Hub
    ["Medium", "Low (biz dev)", "High"], # 18. Newspaper Syndication
    ["Medium", "Low", "Low"],            # 19. Share a Deal Cards
    ["High", "Medium", "High"],          # 20. Savings Map
    ["Low", "Low", "Medium"],            # 21. Print Savings Card
    ["Medium", "Medium", "High"],        # 22. Did It Work? Verification
    ["Medium", "Medium", "Very High"],   # 23. Local Champions
    ["High", "Medium", "Medium"],        # 24. Subscription Audit Tool
    ["High", "High", "Medium"],          # 25. Government Benefit Finder
    ["Very High", "Low", "Medium"],      # 26. ZIP Code Landing Pages
    ["Medium", "Medium", "Medium"],      # 27. Retirement Destination Guides
    ["Low", "Low", "Low"],               # 28. Forward to a Friend
    ["Low", "Low", "Medium"],            # 29. Savings Streak
    ["High", "Medium", "Medium"],        # 30. Tax Season Hub
]


from cmo_agent.google_auth import get_google_credentials
from googleapiclient.discovery import build

SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive.file',
]
creds = get_google_credentials(
    oauth_token_path=OAUTH_TOKEN_PATH, service_account_path="", scopes=SCOPES
)
if creds is None:
    print("ERROR: Could not load Google credentials.")
    sys.exit(1)

sheets_service = build('sheets', 'v4', credentials=creds)

# ── Step 1: Write the 3 new columns (E, F, G) ────────────────────────────────

print("Adding Traffic Impact, Build Effort, Competitive Moat columns...")

sheets_service.spreadsheets().values().update(
    spreadsheetId=SPREADSHEET_ID,
    range='Product Ideas!E1',
    valueInputOption='RAW',
    body={'values': EXTRA_DATA},
).execute()
print("  Wrote 3 new columns (E-G) with header + 30 rows")


# ── Step 2: Format the new header cells (E1:G1) ──────────────────────────────

print("Formatting new headers...")

NAVY = {'red': 0.16, 'green': 0.22, 'blue': 0.43}
WHITE = {'red': 1, 'green': 1, 'blue': 1}
LIGHT_GRAY = {'red': 0.95, 'green': 0.95, 'blue': 0.97}

requests = []

# Bold white-on-navy for new header cells E1:G1
requests.append({
    'repeatCell': {
        'range': {
            'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1,
            'startColumnIndex': 4, 'endColumnIndex': 7,
        },
        'cell': {
            'userEnteredFormat': {
                'textFormat': {'bold': True, 'foregroundColorStyle': {
                    'rgbColor': WHITE,
                }},
                'backgroundColor': NAVY,
            }
        },
        'fields': 'userEnteredFormat(textFormat,backgroundColor)',
    }
})

# Set column widths for E, F, G
for col_idx, width in [(4, 130), (5, 130), (6, 150)]:
    requests.append({
        'updateDimensionProperties': {
            'range': {
                'sheetId': 0,
                'dimension': 'COLUMNS',
                'startIndex': col_idx,
                'endIndex': col_idx + 1,
            },
            'properties': {'pixelSize': width},
            'fields': 'pixelSize',
        }
    })

# Alternating row colors on new columns (match existing pattern)
for row_idx in range(1, 31):
    if row_idx % 2 == 0:
        requests.append({
            'repeatCell': {
                'range': {
                    'sheetId': 0,
                    'startRowIndex': row_idx,
                    'endRowIndex': row_idx + 1,
                    'startColumnIndex': 4,
                    'endColumnIndex': 7,
                },
                'cell': {
                    'userEnteredFormat': {'backgroundColor': LIGHT_GRAY}
                },
                'fields': 'userEnteredFormat.backgroundColor',
            }
        })

# Delete the Priority Matrix tab (sheetId=1) since it's now redundant
requests.append({
    'deleteSheet': {'sheetId': 1}
})

sheets_service.spreadsheets().batchUpdate(
    spreadsheetId=SPREADSHEET_ID,
    body={'requests': requests},
).execute()

print("  Headers formatted, alternating rows applied, Priority Matrix tab deleted")
print("\nDone. All data is now in one tab.")
