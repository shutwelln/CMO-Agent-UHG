"""Generate CJ affiliate tracking links for approved programs.

For each merchant in the research sheet with affiliate_network='CJ' and
approval_status='approved', generates a deep-link tracking URL via the
CJ Link Creation API and writes it back to the affiliate_url column.

Requires:
  CJ_API_TOKEN
  CJ_COMPANY_ID
  AFFILIATE_RESEARCH_SHEET_ID

Usage:
  python scripts/cj_generate_links.py [--dry-run]
"""

import os
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

CJ_API_TOKEN = os.environ.get('CJ_API_TOKEN', '')
CJ_COMPANY_ID = os.environ.get('CJ_COMPANY_ID', '')
SHEET_ID = os.environ.get('AFFILIATE_RESEARCH_SHEET_ID', '')
OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'google-token.json'
)

DRY_RUN = '--dry-run' in sys.argv

if not CJ_API_TOKEN:
    print("ERROR: CJ_API_TOKEN not set in .env")
    sys.exit(1)
if not CJ_COMPANY_ID:
    print("ERROR: CJ_COMPANY_ID not set in .env")
    sys.exit(1)
if not SHEET_ID:
    print("ERROR: AFFILIATE_RESEARCH_SHEET_ID not set in .env")
    sys.exit(1)

# CJ deep link creation endpoint
CJ_LINK_BASE = 'https://link-search.api.cj.com/v2/link-search'

cj_client = httpx.Client(
    timeout=30,
    headers={
        'Authorization': f'Bearer {CJ_API_TOKEN}',
        'Accept': 'application/xml',
    },
)


def generate_cj_link(advertiser_id, website_url, merchant_name):
    """Generate a CJ tracking link for a merchant.

    Strategy:
    1. Try to find an existing deep link for the merchant's homepage
    2. If found, use it directly
    3. If not, construct a CJ deep link URL pattern
    """
    import xml.etree.ElementTree as ET

    # Search for existing links from this advertiser
    params = {
        'requestor-cid': CJ_COMPANY_ID,
        'advertiser-ids': advertiser_id,
        'link-type': 'Text Link',
        'page-number': '1',
        'records-per-page': '10',
    }

    try:
        resp = cj_client.get(CJ_LINK_BASE, params=params)
        if resp.status_code == 200:
            root = ET.fromstring(resp.text)
            links_elem = root.find('links')
            if links_elem is not None:
                for link in links_elem.findall('link'):
                    click_url_elem = link.find('clickUrl')
                    if click_url_elem is not None and click_url_elem.text:
                        return click_url_elem.text.strip()

        # Fallback: construct a standard CJ deep link
        if website_url:
            return f"https://www.anrdoezrs.net/click-{CJ_COMPANY_ID}-{advertiser_id}"

    except Exception as e:
        print(f"    Link generation error: {e}")

    return ''


# ── Step 1: Read sheet ──────────────────────────────────────────────────────────
print(f"Reading research sheet {SHEET_ID}...")

from cmo_agent.google_auth import get_google_credentials
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
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
    print("No data rows found.")
    sys.exit(0)

headers = values[0]
data_rows = values[1:]
col_map = {h: i for i, h in enumerate(headers)}
print(f"  Read {len(data_rows)} merchants")


def get_cell(row, col_name):
    idx = col_map.get(col_name, -1)
    if idx < 0 or idx >= len(row):
        return ''
    return row[idx].strip()


# ── Step 2: Find approved CJ programs needing links ────────────────────────────
print("\nFinding approved CJ programs that need tracking links...")

needs_links = []
for i, row in enumerate(data_rows):
    row_idx = i + 2
    network = get_cell(row, 'affiliate_network')
    status = get_cell(row, 'approval_status')
    existing_url = get_cell(row, 'affiliate_url')
    name = get_cell(row, 'name')
    website = get_cell(row, 'website_url')
    notes = get_cell(row, 'notes')

    # Need link: CJ network, approved, no affiliate_url yet
    if 'cj' in network.lower() and status == 'approved' and not existing_url:
        # Extract advertiser ID from notes or program URL
        adv_id = ''
        program_url = get_cell(row, 'affiliate_program_url')
        if 'advertiser-detail/' in program_url:
            adv_id = program_url.split('advertiser-detail/')[-1].split('/')[0].split('?')[0]
        elif 'CJ match:' in notes:
            # Try to extract from notes if stored there
            pass

        needs_links.append({
            'row_idx': row_idx,
            'name': name,
            'website': website,
            'advertiser_id': adv_id,
        })

print(f"  Found {len(needs_links)} approved CJ programs needing tracking links")

if not needs_links:
    print("\nNo CJ programs need link generation.")
    print("Make sure approved programs have approval_status='approved' in the sheet.")
    sys.exit(0)


# ── Step 3: Generate links ─────────────────────────────────────────────────────
print(f"\nGenerating tracking links...")
if DRY_RUN:
    print("  [DRY RUN - no sheet updates]")

generated = 0
failed = 0
updates = []

for item in needs_links:
    name = item['name']
    adv_id = item['advertiser_id']
    website = item['website']
    row_idx = item['row_idx']

    print(f"  {name}", end='', flush=True)

    if not adv_id:
        print(" -> SKIP (no advertiser ID)")
        failed += 1
        continue

    link = generate_cj_link(adv_id, website, name)

    if link:
        generated += 1
        updates.append((row_idx, link))
        print(f" -> {link[:60]}...")
    else:
        failed += 1
        print(" -> FAILED (no link generated)")

    time.sleep(2.5)


# ── Step 4: Write links to sheet ────────────────────────────────────────────────
print(f"\nResults: {generated} links generated, {failed} failed")

if DRY_RUN:
    print("\n[DRY RUN] Would write:")
    for row_idx, link in updates:
        print(f"  Row {row_idx}: {link}")
elif updates:
    print(f"Writing {len(updates)} links to sheet...")

    affiliate_url_col = col_map.get('affiliate_url')
    if affiliate_url_col is None:
        print("ERROR: 'affiliate_url' column not found in sheet")
        sys.exit(1)

    col_letter = chr(ord('A') + affiliate_url_col)
    batch_data = []
    for row_idx, link in updates:
        batch_data.append({
            'range': f"Merchants!{col_letter}{row_idx}",
            'values': [[link]],
        })

    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={'valueInputOption': 'RAW', 'data': batch_data},
    ).execute()
    print(f"  Wrote {len(batch_data)} links")

cj_client.close()

print(f"\nDone! Generated {generated} CJ tracking links.")
print(f"\nNext steps:")
print(f"  1. Verify links work by clicking a few in the sheet")
print(f"  2. Run populate_affiliate_urls.py to push to Supabase")
print(f"  3. Run build_guide_affiliate_map.py to update guide comparison tables")
