"""Query the ~858 orphan batch rows from discounts_v2 (name IS NULL, active=true)
and create a formatted Google Sheet with merchant + store location details.

Orphan batch: rows created around 2025-12-29 with name=NULL in discounts_v2.
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
SHARE_EMAIL = 'nick@saverwell.com'

client = httpx.Client(timeout=60)


# ── Step 1: Fetch orphan batch rows (active=true, name IS NULL) ──────────────
print("Fetching orphan batch rows from discounts_v2...")
orphan_rows = []
offset = 0
while True:
    r = client.get(f'{SUPABASE_URL}/rest/v1/discounts_v2', headers=HEADERS, params={
        'select': 'id,merchant_id,name,discount_value,details,requirement,'
                  'discount_type,store_location_id,created_at',
        'active': 'eq.true',
        'name': 'is.null',
        'limit': '500',
        'offset': str(offset),
        'order': 'merchant_id.asc',
    })
    r.raise_for_status()
    batch = r.json()
    if not batch:
        break
    orphan_rows.extend(batch)
    offset += 500

print(f"  Found {len(orphan_rows)} orphan rows")


# ── Step 2: Fetch merchant details ───────────────────────────────────────────
merchant_ids = sorted(set(row['merchant_id'] for row in orphan_rows))
print(f"  {len(merchant_ids)} unique merchants")

print("Fetching merchant details...")
merchant_map = {}
for i in range(0, len(merchant_ids), 100):
    batch = merchant_ids[i:i + 100]
    ids_str = ','.join(str(x) for x in batch)
    r = client.get(f'{SUPABASE_URL}/rest/v1/merchants', headers=HEADERS, params={
        'select': 'id,name,default_discount_value,default_discount_text,'
                  'default_discount_requirement,default_discount_type,'
                  'is_national,is_active,page_slug,page_status',
        'id': f'in.({ids_str})',
        'limit': '500',
    })
    r.raise_for_status()
    for m in r.json():
        merchant_map[m['id']] = m

print(f"  Retrieved {len(merchant_map)} merchants")


# ── Step 3: Fetch store location details ─────────────────────────────────────
store_loc_ids = sorted(set(
    row['store_location_id'] for row in orphan_rows if row.get('store_location_id')
))
print(f"  {len(store_loc_ids)} unique store locations")

print("Fetching store location details...")
store_loc_map = {}
for i in range(0, len(store_loc_ids), 100):
    batch = store_loc_ids[i:i + 100]
    ids_str = ','.join(str(x) for x in batch)
    r = client.get(f'{SUPABASE_URL}/rest/v1/store_locations', headers=HEADERS, params={
        'select': 'id,merchant_id,location_id,store_name',
        'id': f'in.({ids_str})',
        'limit': '500',
    })
    r.raise_for_status()
    for loc in r.json():
        store_loc_map[loc['id']] = loc

# Fetch actual addresses from locations_v2 (store_locations references location_id)
location_ids = sorted(set(
    sl['location_id'] for sl in store_loc_map.values() if sl.get('location_id')
))
print(f"  Fetching {len(location_ids)} location addresses from locations_v2...")
address_map = {}
for i in range(0, len(location_ids), 100):
    batch = location_ids[i:i + 100]
    ids_str = ','.join(str(x) for x in batch)
    r = client.get(f'{SUPABASE_URL}/rest/v1/locations_v2', headers=HEADERS, params={
        'select': 'id,address1,city,state,zip',
        'id': f'in.({ids_str})',
        'limit': '500',
    })
    r.raise_for_status()
    for addr in r.json():
        address_map[addr['id']] = addr

print(f"  Retrieved {len(address_map)} addresses")


# ── Step 4: Build sheet rows ─────────────────────────────────────────────────
print("Building sheet rows...")

SHEET_HEADERS = [
    'Discount ID',
    'Merchant ID',
    'Merchant Name',
    'Is National',
    'discount_value',
    'details',
    'requirement',
    'discount_type',
    'store_location_id',
    'Store Name',
    'Store City',
    'Store State',
    'Merchant Default Value',
    'Merchant Default Text',
    'Merchant Default Requirement',
    'Merchant Default Type',
    'Has Valid Merchant Defaults',
    'Recommended Action',
    'Created At',
]

rows = []
for d in orphan_rows:
    mid = d['merchant_id']
    slid = d.get('store_location_id')
    merchant = merchant_map.get(mid, {})

    # Store location + address resolution
    store_loc = store_loc_map.get(slid, {}) if slid else {}
    loc_id = store_loc.get('location_id')
    address = address_map.get(loc_id, {}) if loc_id else {}

    store_name = store_loc.get('store_name', '')
    store_city = address.get('city', '')
    store_state = address.get('state', '')

    # Merchant defaults
    default_val = merchant.get('default_discount_value', '')
    default_text = merchant.get('default_discount_text', '')
    default_req = merchant.get('default_discount_requirement', '')
    default_type = merchant.get('default_discount_type', '')

    # Determine if merchant has valid defaults
    has_defaults = bool(default_val or default_text)
    has_defaults_str = 'YES' if has_defaults else 'NO'
    recommended_action = (
        'Deactivate - merchant defaults cover this' if has_defaults
        else 'Remap fields'
    )

    rows.append([
        d['id'],
        mid,
        merchant.get('name', ''),
        str(merchant.get('is_national', '')),
        str(d.get('discount_value')) if d.get('discount_value') is not None else 'None',
        str(d.get('details')) if d.get('details') is not None else 'None',
        str(d.get('requirement')) if d.get('requirement') is not None else 'None',
        str(d.get('discount_type')) if d.get('discount_type') is not None else 'None',
        str(slid) if slid else '',
        store_name or '',
        store_city or '',
        store_state or '',
        str(default_val) if default_val is not None else '',
        str(default_text) if default_text is not None else '',
        str(default_req) if default_req is not None else '',
        str(default_type) if default_type is not None else '',
        has_defaults_str,
        recommended_action,
        (d.get('created_at') or '')[:19].replace('T', ' '),
    ])

# Sort by Merchant Name, then Store State
rows.sort(key=lambda r: (r[2].lower() if r[2] else '', r[11].lower() if r[11] else ''))

print(f"  Built {len(rows)} rows")

# Summary stats
total = len(rows)
unique_merchants = len(merchant_ids)
can_deactivate = sum(1 for r in rows if r[17].startswith('Deactivate'))
need_remap = sum(1 for r in rows if r[17] == 'Remap fields')


# ── Step 5: Create Google Sheet ──────────────────────────────────────────────
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

# Create spreadsheet with two sheets
spreadsheet_body = {
    'properties': {'title': 'Discounts Orphan Batch Audit'},
    'sheets': [
        {'properties': {'title': 'Orphan Rows', 'sheetId': 0}},
        {'properties': {'title': 'Summary', 'sheetId': 1}},
    ],
}
spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet_body).execute()
spreadsheet_id = spreadsheet['spreadsheetId']
sheet_url = spreadsheet['spreadsheetUrl']
print(f"  Created spreadsheet: {spreadsheet_id}")

# Share with authorized users only (restricted access)
share_file_restricted(drive_service, spreadsheet_id)
print("  Shared with authorized users (restricted access)")


# ── Step 6: Write data to Orphan Rows sheet ──────────────────────────────────
print("Writing data to sheet...")

all_values = [SHEET_HEADERS] + rows
sheets_service.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id,
    range='Orphan Rows!A1',
    valueInputOption='RAW',
    body={'values': all_values},
).execute()
print(f"  Wrote {len(rows)} data rows + header")


# ── Step 7: Write Summary tab ────────────────────────────────────────────────
print("Writing summary tab...")

summary_values = [
    ['Discounts Orphan Batch Audit - Summary'],
    [],
    ['Metric', 'Value'],
    ['Total orphan rows', total],
    ['Unique merchants affected', unique_merchants],
    ['Can be deactivated (merchant defaults exist)', can_deactivate],
    ['Need field remapping (no merchant defaults)', need_remap],
    [],
    ['Breakdown by Recommended Action', ''],
    ['Deactivate - merchant defaults cover this', can_deactivate],
    ['Remap fields', need_remap],
]

sheets_service.spreadsheets().values().update(
    spreadsheetId=spreadsheet_id,
    range='Summary!A1',
    valueInputOption='RAW',
    body={'values': summary_values},
).execute()


# ── Step 8: Format both sheets ───────────────────────────────────────────────
print("Formatting sheets...")

num_cols = len(SHEET_HEADERS)
num_rows = len(rows) + 1  # +1 for header

# Find column index of "Recommended Action" (index 17, 0-based)
action_col_idx = 17

requests = []

# --- Orphan Rows sheet formatting ---

# Bold + freeze header row
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

requests.append({
    'updateSheetProperties': {
        'properties': {'sheetId': 0, 'gridProperties': {'frozenRowCount': 1}},
        'fields': 'gridProperties.frozenRowCount',
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

# Color-code "Recommended Action" column (col index 17)
# Green for "Deactivate", yellow for "Remap"
for row_idx, row in enumerate(rows, start=1):
    action = row[action_col_idx]
    if action.startswith('Deactivate'):
        bg = {'red': 0.85, 'green': 0.95, 'blue': 0.85}  # light green
    else:
        bg = {'red': 1.0, 'green': 0.95, 'blue': 0.75}  # light yellow
    requests.append({
        'repeatCell': {
            'range': {
                'sheetId': 0,
                'startRowIndex': row_idx,
                'endRowIndex': row_idx + 1,
                'startColumnIndex': action_col_idx,
                'endColumnIndex': action_col_idx + 1,
            },
            'cell': {
                'userEnteredFormat': {'backgroundColor': bg}
            },
            'fields': 'userEnteredFormat.backgroundColor',
        }
    })

# --- Summary sheet formatting ---

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

# Bold the "Metric" / "Value" header (row 2, 0-indexed)
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

# Bold "Breakdown" label (row 8, 0-indexed)
requests.append({
    'repeatCell': {
        'range': {'sheetId': 1, 'startRowIndex': 8, 'endRowIndex': 9,
                  'startColumnIndex': 0, 'endColumnIndex': 2},
        'cell': {
            'userEnteredFormat': {
                'textFormat': {'bold': True, 'fontSize': 11},
            }
        },
        'fields': 'userEnteredFormat.textFormat',
    }
})

# Auto-resize summary columns
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

# Execute all formatting
sheets_service.spreadsheets().batchUpdate(
    spreadsheetId=spreadsheet_id,
    body={'requests': requests},
).execute()

print("  Formatting applied")

# ── Done ─────────────────────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"  Google Sheet URL: {sheet_url}")
print(f"{'=' * 60}")
print(f"\nSummary:")
print(f"  Total orphan rows: {total}")
print(f"  Unique merchants: {unique_merchants}")
print(f"  Can deactivate (merchant defaults): {can_deactivate}")
print(f"  Need field remapping: {need_remap}")
