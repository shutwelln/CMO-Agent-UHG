"""Populate merchant affiliate URLs from the research Google Sheet to Supabase.

Reads the 'Saverwell Affiliate Research' sheet, finds rows with
approval_status='approved' and a non-empty affiliate_url, then updates
the corresponding merchant in Supabase.

Idempotent - safe to re-run as new approvals come in.

Usage:
  python scripts/populate_affiliate_urls.py <SHEET_ID>

  SHEET_ID: The Google Sheet ID from build_affiliate_research_sheet.py
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
SUPABASE_HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
}
OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'google-token.json'
)

# ── Parse args ────────────────────────────────────────────────────────────────
if len(sys.argv) < 2:
    print("Usage: python scripts/populate_affiliate_urls.py <SHEET_ID>")
    print("  SHEET_ID: Google Sheet ID from build_affiliate_research_sheet.py")
    sys.exit(1)

SHEET_ID = sys.argv[1]


# ── Step 1: Read research sheet ───────────────────────────────────────────────
print(f"Reading research sheet {SHEET_ID}...")

from cmo_agent.google_auth import get_google_credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
creds = get_google_credentials(
    oauth_token_path=OAUTH_TOKEN_PATH, service_account_path="", scopes=SCOPES
)
if creds is None:
    print("ERROR: Could not load Google credentials.")
    sys.exit(1)

sheets_service = build('sheets', 'v4', credentials=creds)

result = sheets_service.spreadsheets().values().get(
    spreadsheetId=SHEET_ID,
    range='Merchants!A1:M',
).execute()

values = result.get('values', [])
if len(values) < 2:
    print("No data rows found in sheet.")
    sys.exit(0)

headers = values[0]
data_rows = values[1:]
print(f"  Read {len(data_rows)} rows")

# Build column index map
col_map = {h: i for i, h in enumerate(headers)}
required_cols = ['merchant_id', 'approval_status', 'affiliate_url',
                 'affiliate_network', 'commission_type', 'commission_rate']
for col in required_cols:
    if col not in col_map:
        print(f"ERROR: Missing required column '{col}' in sheet.")
        sys.exit(1)


# ── Step 2: Filter approved rows ──────────────────────────────────────────────

def get_cell(row, col_name):
    """Safely get a cell value from a row by column name."""
    idx = col_map[col_name]
    return row[idx].strip() if idx < len(row) and row[idx] else ''


approved = []
for row in data_rows:
    status = get_cell(row, 'approval_status')
    url = get_cell(row, 'affiliate_url')
    merchant_id = get_cell(row, 'merchant_id')

    if status == 'approved' and url and merchant_id:
        approved.append({
            'merchant_id': int(merchant_id),
            'affiliate_url': url,
            'affiliate_network': get_cell(row, 'affiliate_network'),
            'commission_type': get_cell(row, 'commission_type'),
            'commission_rate': get_cell(row, 'commission_rate'),
        })

print(f"  Found {len(approved)} approved merchants with affiliate URLs")

if not approved:
    print("No approved merchants to update. Done.")
    sys.exit(0)


# ── Step 3: Update Supabase ───────────────────────────────────────────────────
print("Updating Supabase merchants...")

client = httpx.Client(timeout=30)
updated = 0
failed = 0

for item in approved:
    mid = item['merchant_id']
    payload = {
        'affiliate_url': item['affiliate_url'],
        'affiliate_network': item['affiliate_network'],
        'commission_type': item['commission_type'],
        'commission_rate': item['commission_rate'],
        'affiliate_status': 'active',
    }

    resp = client.patch(
        f'{SUPABASE_URL}/rest/v1/merchants',
        headers=SUPABASE_HEADERS,
        params={'id': f'eq.{mid}'},
        json=payload,
    )

    if resp.status_code in (200, 204):
        updated += 1
        print(f"  Updated merchant {mid}")
    else:
        failed += 1
        print(f"  FAILED merchant {mid}: {resp.status_code} {resp.text}")

client.close()

print(f"\nDone: {updated} updated, {failed} failed out of {len(approved)} approved")
