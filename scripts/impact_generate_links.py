"""Generate Impact.com affiliate tracking links for approved programs.

For each merchant in the research sheet with affiliate_network containing
'Impact' and approval_status='approved', generates a tracking URL via the
Impact.com Tracking Links API and writes it back to the affiliate_url column.

Requires:
  IMPACT_ACCOUNT_SID
  IMPACT_AUTH_TOKEN
  AFFILIATE_RESEARCH_SHEET_ID

Usage:
  python scripts/impact_generate_links.py [--dry-run]
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

IMPACT_SID = os.environ.get('IMPACT_ACCOUNT_SID', '')
IMPACT_TOKEN = os.environ.get('IMPACT_AUTH_TOKEN', '')
SHEET_ID = os.environ.get('AFFILIATE_RESEARCH_SHEET_ID', '')
OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'google-token.json'
)

DRY_RUN = '--dry-run' in sys.argv

if not IMPACT_SID or not IMPACT_TOKEN:
    print("ERROR: IMPACT_ACCOUNT_SID and IMPACT_AUTH_TOKEN must be set in .env")
    print("Get your token from Impact.com Personal Access Tokens page")
    sys.exit(1)

if not SHEET_ID:
    print("ERROR: AFFILIATE_RESEARCH_SHEET_ID not set in .env")
    sys.exit(1)

impact_client = httpx.Client(
    timeout=30,
    auth=(IMPACT_SID, IMPACT_TOKEN),
)


def get_campaign_id_for_merchant(merchant_name, website_url):
    """Look up the Impact campaign ID for a merchant."""
    import re

    def normalize(name):
        name = name.lower().strip()
        name = re.sub(r'[^a-z0-9\s]', '', name)
        return re.sub(r'\s+', ' ', name).strip()

    # Search campaigns by name
    resp = impact_client.get(
        f'https://api.impact.com/Mediapartners/{IMPACT_SID}/Campaigns',
        params={'PageSize': 100, 'Name': merchant_name},
        headers={'Accept': 'application/json'},
    )

    if resp.status_code != 200:
        return None

    data = resp.json()
    campaigns = data.get('Campaigns', [])

    norm_name = normalize(merchant_name)
    for c in campaigns:
        c_name = normalize(c.get('CampaignName', ''))
        if norm_name in c_name or c_name in norm_name:
            return c.get('CampaignId')

    return None


def generate_impact_link(campaign_id, destination_url):
    """Generate an Impact.com tracking link via the API."""
    # Impact.com Tracking Links API
    resp = impact_client.post(
        f'https://api.impact.com/Mediapartners/{IMPACT_SID}/Campaigns/{campaign_id}/TrackingLinks',
        headers={
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        },
        json={
            'Url': destination_url,
            'SubId1': 'saverwell',
        },
    )

    if resp.status_code in (200, 201):
        data = resp.json()
        return data.get('TrackingLink', '') or data.get('Url', '')

    # Fallback: try the unique link endpoint
    resp2 = impact_client.get(
        f'https://api.impact.com/Mediapartners/{IMPACT_SID}/Campaigns/{campaign_id}/UniqueUrls',
        headers={'Accept': 'application/json'},
        params={'PageSize': 1},
    )

    if resp2.status_code == 200:
        data = resp2.json()
        urls = data.get('UniqueUrls', [])
        if urls:
            return urls[0].get('UniqueLinkUrl', '')

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


# ── Step 2: Find approved Impact programs needing links ─────────────────────────
print("\nFinding approved Impact programs that need tracking links...")

needs_links = []
for i, row in enumerate(data_rows):
    row_idx = i + 2
    network = get_cell(row, 'affiliate_network')
    status = get_cell(row, 'approval_status')
    existing_url = get_cell(row, 'affiliate_url')
    name = get_cell(row, 'name')
    website = get_cell(row, 'website_url')

    # Need link: Impact network, approved, no affiliate_url yet
    if 'impact' in network.lower() and status == 'approved' and not existing_url:
        needs_links.append({
            'row_idx': row_idx,
            'name': name,
            'website': website,
        })

print(f"  Found {len(needs_links)} approved Impact programs needing tracking links")

if not needs_links:
    print("\nNo Impact programs need link generation.")
    print("Ensure approved programs have approval_status='approved' in the sheet.")
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
    website = item['website']
    row_idx = item['row_idx']

    print(f"  {name}", end='', flush=True)

    # Find campaign ID
    campaign_id = get_campaign_id_for_merchant(name, website)
    if not campaign_id:
        print(" -> SKIP (campaign not found)")
        failed += 1
        time.sleep(1)
        continue

    # Generate tracking link
    destination = website if website else f"https://www.{name.lower().replace(' ', '')}.com"
    link = generate_impact_link(campaign_id, destination)

    if link:
        generated += 1
        updates.append((row_idx, link))
        print(f" -> {link[:60]}...")
    else:
        failed += 1
        print(" -> FAILED (no link generated)")

    time.sleep(1)


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
        print("ERROR: 'affiliate_url' column not found")
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

impact_client.close()

print(f"\nDone! Generated {generated} Impact tracking links.")
print(f"\nNext steps:")
print(f"  1. Verify links work by clicking a few in the sheet")
print(f"  2. Run populate_affiliate_urls.py to push to Supabase")
print(f"  3. Run build_guide_affiliate_map.py to update guide comparison tables")
