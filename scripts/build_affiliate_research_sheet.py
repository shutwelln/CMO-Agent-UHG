"""Build Affiliate Research Sheet for Saverwell merchant pages.

Queries Supabase for all national published merchants (166+), creates a
Google Sheet with affiliate program research columns, and pre-populates
priority based on category revenue potential.

Run: python scripts/build_affiliate_research_sheet.py
"""

import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
}
OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'google-token.json'
)

client = httpx.Client(timeout=60)

# ── Category priority mapping ────────────────────────────────────────────────
# Based on typical affiliate commission rates by retail category.
# High = 5%+ commissions or high-AOV (electronics, health, insurance)
# Medium = 2-5% commissions (home, clothing, specialty)
# Low = 1-2% commissions (grocery, pharmacy, fast food)

CATEGORY_PRIORITY = {
    # High priority - higher commissions or high AOV
    'Health & Wellness': 'High',
    'Electronics': 'High',
    'Home Improvement': 'High',
    'Insurance': 'High',
    'Financial Services': 'High',
    'Telecom': 'High',
    # Medium priority
    'Clothing & Apparel': 'Medium',
    'Department Stores': 'Medium',
    'Home & Garden': 'Medium',
    'Specialty Retail': 'Medium',
    'Automotive': 'Medium',
    'Entertainment': 'Medium',
    'Travel': 'Medium',
    'Pet Supplies': 'Medium',
    # Low priority - thin margins
    'Grocery': 'Low',
    'Pharmacy': 'Low',
    'Restaurants': 'Low',
    'Fast Food': 'Low',
    'Convenience': 'Low',
    'Gas Stations': 'Low',
    'Dollar Stores': 'Low',
}


# ── Step 1: Fetch all national published merchants ────────────────────────────
print("Fetching national published merchants from Supabase...")

merchants = []
offset = 0
while True:
    r = client.get(f'{SUPABASE_URL}/rest/v1/merchants', headers=HEADERS, params={
        'select': 'id,name,website_url,category_id,is_national,page_slug,page_status',
        'is_national': 'eq.true',
        'page_status': 'eq.published',
        'page_slug': 'not.is.null',
        'limit': '500',
        'offset': str(offset),
        'order': 'name.asc',
    })
    r.raise_for_status()
    batch = r.json()
    if not batch:
        break
    merchants.extend(batch)
    offset += 500

print(f"  Found {len(merchants)} national published merchants")


# ── Step 2: Fetch category names ──────────────────────────────────────────────
print("Fetching merchant categories...")

r = client.get(f'{SUPABASE_URL}/rest/v1/merchant_categories', headers=HEADERS, params={
    'select': 'id,name',
    'limit': '100',
})
r.raise_for_status()
category_map = {c['id']: c['name'] for c in r.json()}
print(f"  Retrieved {len(category_map)} categories")


# ── Step 3: Build sheet rows ─────────────────────────────────────────────────
print("Building sheet rows...")

SHEET_HEADERS = [
    'merchant_id',
    'name',
    'category',
    'website_url',
    'priority',
    'affiliate_network',
    'commission_rate',
    'cookie_duration',
    'commission_type',
    'affiliate_program_url',
    'approval_status',
    'affiliate_url',
    'notes',
]

rows = []
for m in merchants:
    category_name = category_map.get(m.get('category_id'), 'Unknown')
    priority = CATEGORY_PRIORITY.get(category_name, 'Medium')

    rows.append([
        m['id'],
        m['name'],
        category_name,
        m.get('website_url') or '',
        priority,
        '',  # affiliate_network - to be researched
        '',  # commission_rate
        '',  # cookie_duration
        '',  # commission_type
        '',  # affiliate_program_url
        '',  # approval_status
        '',  # affiliate_url
        '',  # notes
    ])

# Sort: High priority first, then Medium, then Low, then alphabetical
priority_order = {'High': 0, 'Medium': 1, 'Low': 2}
rows.sort(key=lambda r: (priority_order.get(r[4], 1), r[1].lower()))

print(f"  Built {len(rows)} rows")

# Count by priority
high = sum(1 for r in rows if r[4] == 'High')
medium = sum(1 for r in rows if r[4] == 'Medium')
low = sum(1 for r in rows if r[4] == 'Low')


# ── Step 4: Create Google Sheet ───────────────────────────────────────────────
print("Creating Google Sheet...")

from cmo_agent.google_auth import get_google_credentials, share_file_restricted
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
drive_service = build('drive', 'v3', credentials=creds)

spreadsheet_body = {
    'properties': {'title': 'Saverwell Affiliate Research'},
    'sheets': [
        {'properties': {'title': 'Merchants', 'sheetId': 0}},
        {'properties': {'title': 'Instructions', 'sheetId': 1}},
    ],
}
spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet_body).execute()
spreadsheet_id = spreadsheet['spreadsheetId']
sheet_url = spreadsheet['spreadsheetUrl']
print(f"  Created spreadsheet: {spreadsheet_id}")

share_file_restricted(drive_service, spreadsheet_id)
print("  Shared with authorized users")


# ── Step 5: Write merchant data ───────────────────────────────────────────────
print("Writing merchant data to sheet...")

all_values = [SHEET_HEADERS] + rows
sheets_service.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id,
    range='Merchants!A1',
    valueInputOption='RAW',
    body={'values': all_values},
).execute()
print(f"  Wrote {len(rows)} rows + header")


# ── Step 6: Write instructions tab ───────────────────────────────────────────
print("Writing instructions tab...")

instructions = [
    ['Saverwell Affiliate Research - Instructions'],
    [],
    ['Column', 'Description'],
    ['merchant_id', 'Supabase merchant ID (do not edit)'],
    ['name', 'Merchant display name (do not edit)'],
    ['category', 'Merchant category (do not edit)'],
    ['website_url', 'Merchant website (do not edit)'],
    ['priority', 'High/Medium/Low based on typical commission rates for the category'],
    ['affiliate_network', 'Which network has this merchant (Impact, CJ, Rakuten, ShareASale, etc.)'],
    ['commission_rate', 'Commission rate (e.g., "5%", "$10 flat", "3-8%")'],
    ['cookie_duration', 'Cookie/attribution window (e.g., "30 days", "7 days")'],
    ['commission_type', 'CPC, CPA, CPS (cost per sale), revenue share, etc.'],
    ['affiliate_program_url', 'URL to the affiliate program signup/info page'],
    ['approval_status', 'not_applied, applied, approved, rejected, not_available'],
    ['affiliate_url', 'Your unique affiliate tracking URL after approval'],
    ['notes', 'Any notes about the program'],
    [],
    ['Workflow'],
    ['1. Sign up for Impact (primary network)'],
    ['2. Sign up for 1-2 gap-filler networks (CJ, Rakuten) for merchants not on Impact'],
    ['3. Work through High priority rows first, then Medium'],
    ['4. For each merchant: search "[merchant name] affiliate program"'],
    ['5. Fill in affiliate_network, commission_rate, cookie_duration, commission_type'],
    ['6. Apply to programs, set approval_status to "applied"'],
    ['7. When approved, paste your affiliate URL in the affiliate_url column'],
    ['8. Run populate_affiliate_urls.py to push approved URLs to Supabase'],
    [],
    ['Summary'],
    ['Total merchants', len(rows)],
    ['High priority', high],
    ['Medium priority', medium],
    ['Low priority', low],
]

sheets_service.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id,
    range='Instructions!A1',
    valueInputOption='RAW',
    body={'values': instructions},
).execute()


# ── Step 7: Format sheets ────────────────────────────────────────────────────
print("Formatting sheets...")

num_cols = len(SHEET_HEADERS)

requests = []

# --- Merchants sheet ---

# Bold + colored header row
requests.append({
    'repeatCell': {
        'range': {'sheetId': 0, 'startRowIndex': 0, 'endRowIndex': 1,
                  'startColumnIndex': 0, 'endColumnIndex': num_cols},
        'cell': {
            'userEnteredFormat': {
                'textFormat': {'bold': True, 'foregroundColorStyle': {
                    'rgbColor': {'red': 1, 'green': 1, 'blue': 1}
                }},
                'backgroundColor': {'red': 0.16, 'green': 0.22, 'blue': 0.43},
            }
        },
        'fields': 'userEnteredFormat(textFormat,backgroundColor)',
    }
})

# Freeze header row
requests.append({
    'updateSheetProperties': {
        'properties': {'sheetId': 0, 'gridProperties': {'frozenRowCount': 1}},
        'fields': 'gridProperties.frozenRowCount',
    }
})

# Color-code priority column (index 4)
priority_col = 4
for row_idx, row in enumerate(rows, start=1):
    priority = row[priority_col]
    if priority == 'High':
        bg = {'red': 0.85, 'green': 0.95, 'blue': 0.85}  # light green
    elif priority == 'Medium':
        bg = {'red': 1.0, 'green': 0.95, 'blue': 0.75}  # light yellow
    else:
        bg = {'red': 0.95, 'green': 0.90, 'blue': 0.90}  # light red
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': 0,
                'startRowIndex': row_idx,
                'endRowIndex': row_idx + 1,
                'startColumnIndex': priority_col,
                'endColumnIndex': priority_col + 1,
            },
            'cell': {
                'userEnteredFormat': {'backgroundColor': bg}
            },
            'fields': 'userEnteredFormat.backgroundColor',
        }
    })

# Auto-resize columns
requests.append({
    'autoResizeDimensions': {
        'dimensions': {
            'sheetId': 0,
            'dimension': 'COLUMNS',
            'startIndex': 0,
            'endIndex': num_cols,
        }
    }
})

# Data validation for approval_status column (index 10)
requests.append({
    'setDataValidation': {
        'range': {
            'sheetId': 0,
            'startRowIndex': 1,
            'endRowIndex': len(rows) + 1,
            'startColumnIndex': 10,
            'endColumnIndex': 11,
        },
        'rule': {
            'condition': {
                'type': 'ONE_OF_LIST',
                'values': [
                    {'userEnteredValue': 'not_applied'},
                    {'userEnteredValue': 'applied'},
                    {'userEnteredValue': 'approved'},
                    {'userEnteredValue': 'rejected'},
                    {'userEnteredValue': 'not_available'},
                ],
            },
            'showCustomUi': True,
            'strict': False,
        }
    }
})

# --- Instructions sheet ---

# Title row bold + larger
requests.append({
    'repeatCell': {
        'range': {'sheetId': 1, 'startRowIndex': 0, 'endRowIndex': 1,
                  'startColumnIndex': 0, 'endColumnIndex': 2},
        'cell': {
            'userEnteredFormat': {
                'textFormat': {'bold': True, 'fontSize': 14},
            }
        },
        'fields': 'userEnteredFormat.textFormat',
    }
})

# Bold column headers
requests.append({
    'repeatCell': {
        'range': {'sheetId': 1, 'startRowIndex': 2, 'endRowIndex': 3,
                  'startColumnIndex': 0, 'endColumnIndex': 2},
        'cell': {
            'userEnteredFormat': {
                'textFormat': {'bold': True},
                'backgroundColor': {'red': 0.16, 'green': 0.22, 'blue': 0.43},
            }
        },
        'fields': 'userEnteredFormat(textFormat,backgroundColor)',
    }
})

# Auto-resize instructions columns
requests.append({
    'autoResizeDimensions': {
        'dimensions': {
            'sheetId': 1,
            'dimension': 'COLUMNS',
            'startIndex': 0,
            'endIndex': 2,
        }
    }
})

sheets_service.spreadsheets().batchUpdate(
    spreadsheetId=spreadsheet_id,
    body={'requests': requests},
).execute()

print("  Formatting applied")


# ── Done ──────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"  Google Sheet URL: {sheet_url}")
print(f"{'=' * 60}")
print(f"\nSummary:")
print(f"  Total merchants: {len(rows)}")
print(f"  High priority: {high}")
print(f"  Medium priority: {medium}")
print(f"  Low priority: {low}")
print(f"\nNext steps:")
print(f"  1. Sign up for Impact Radius")
print(f"  2. Research affiliate coverage (search each merchant)")
print(f"  3. Apply to programs starting with High priority")
print(f"  4. Run populate_affiliate_urls.py after approvals")
