"""Search Impact.com for Saverwell merchants.

If Impact.com API credentials are available (IMPACT_ACCOUNT_SID + IMPACT_AUTH_TOKEN),
uses the Campaigns API to list all available programs and fuzzy-match against
the research sheet merchants.

If API credentials are NOT available, falls back to generating a prioritized
checklist of merchants not yet found on CJ, formatted for quick manual search
in the Impact dashboard.

Requires:
  AFFILIATE_RESEARCH_SHEET_ID - Google Sheet ID

Optional:
  IMPACT_ACCOUNT_SID  - Impact.com Account SID
  IMPACT_AUTH_TOKEN    - Impact.com Auth Token

Usage:
  python scripts/impact_merchant_discovery.py [--dry-run]
"""

import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

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

if not SHEET_ID:
    print("ERROR: AFFILIATE_RESEARCH_SHEET_ID not set in .env")
    sys.exit(1)

HAS_API = bool(IMPACT_SID and IMPACT_TOKEN)
if HAS_API:
    print("Impact.com API credentials found - will use API discovery")
else:
    print("No Impact.com API credentials - will generate manual search checklist")


# ── Helpers ─────────────────────────────────────────────────────────────────────

def normalize_name(name):
    """Normalize merchant name for fuzzy comparison."""
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    for suffix in [' inc', ' llc', ' corp', ' co', ' company', ' stores', ' store']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


def domain_from_url(url):
    """Extract clean domain from URL."""
    if not url:
        return ''
    parsed = urlparse(url if '://' in url else f'https://{url}')
    domain = parsed.netloc or parsed.path.split('/')[0]
    return domain.replace('www.', '').lower()


# ── Step 1: Read Google Sheet ──────────────────────────────────────────────────
print(f"\nReading research sheet {SHEET_ID}...")

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
    print("No data rows found in sheet.")
    sys.exit(0)

headers = values[0]
data_rows = values[1:]
col_map = {h: i for i, h in enumerate(headers)}
print(f"  Read {len(data_rows)} merchants")


def get_cell(row, col_name):
    """Safely get cell value."""
    idx = col_map.get(col_name, -1)
    if idx < 0 or idx >= len(row):
        return ''
    return row[idx].strip()


# ── API Path: Search Impact.com Campaigns API ─────────────────────────────────
if HAS_API:
    print("\nFetching all available Impact.com campaigns...")

    impact_client = httpx.Client(
        timeout=30,
        auth=(IMPACT_SID, IMPACT_TOKEN),
    )

    # Fetch all campaigns (paginated)
    all_campaigns = []
    page = 1
    while True:
        resp = impact_client.get(
            f'https://api.impact.com/Mediapartners/{IMPACT_SID}/Campaigns',
            params={
                'PageSize': 100,
                'Page': page,
            },
            headers={'Accept': 'application/json'},
        )
        if resp.status_code != 200:
            print(f"  Impact API error {resp.status_code}: {resp.text[:300]}")
            if resp.status_code == 401:
                print("  Check IMPACT_ACCOUNT_SID and IMPACT_AUTH_TOKEN in .env")
            break

        data = resp.json()
        campaigns = data.get('Campaigns', [])
        if not campaigns:
            break
        all_campaigns.extend(campaigns)
        print(f"  Page {page}: {len(campaigns)} campaigns")

        # Check for more pages
        total = data.get('@total', 0)
        if len(all_campaigns) >= total:
            break
        page += 1
        time.sleep(0.5)

    print(f"  Total campaigns available: {len(all_campaigns)}")

    # Build lookup index
    campaign_by_name = {}
    campaign_by_domain = {}
    for c in all_campaigns:
        c_name = normalize_name(c.get('CampaignName', ''))
        c_url = c.get('CampaignUrl', '')
        c_domain = domain_from_url(c_url)
        if c_name:
            campaign_by_name[c_name] = c
        if c_domain:
            campaign_by_domain[c_domain] = c

    # Match merchants to campaigns
    found = 0
    not_found = 0
    already_set = 0
    updates = []

    for i, row in enumerate(data_rows):
        row_idx = i + 2
        name = get_cell(row, 'name')
        website = get_cell(row, 'website_url')
        existing_network = get_cell(row, 'affiliate_network')

        # Skip if already has non-CJ affiliate data (preserve CJ results for comparison)
        if existing_network and existing_network.lower() not in ('', 'cj', 'not_available'):
            already_set += 1
            continue

        norm_name = normalize_name(name)
        domain = domain_from_url(website)

        # Try exact name match, then domain match, then partial name
        match = campaign_by_name.get(norm_name)
        if not match and domain:
            match = campaign_by_domain.get(domain)
        if not match:
            # Partial name matching
            for c_name, c in campaign_by_name.items():
                if norm_name in c_name or c_name in norm_name:
                    match = c
                    break

        if match:
            found += 1
            c_name = match.get('CampaignName', '')
            c_id = match.get('CampaignId', '')
            c_url = match.get('CampaignUrl', '')
            c_status = match.get('ContractStatus', '')

            # Determine if this is better than existing CJ match
            is_cj = existing_network.upper() == 'CJ'
            network_value = 'Impact' if not is_cj else f"Impact (also on CJ)"

            row_updates = {
                'affiliate_network': network_value,
                'affiliate_program_url': c_url or '',
                'notes': f"Impact match: {c_name}" + (f" (status: {c_status})" if c_status else ''),
            }

            # Only overwrite commission data if we didn't already have CJ data
            if not is_cj:
                updates.append((row_idx, row_updates))
            else:
                # Just note it's on both, don't overwrite CJ data
                updates.append((row_idx, {
                    'notes': f"Also on Impact: {c_name} - compare rates",
                    'affiliate_network': f"CJ + Impact",
                }))

            print(f"  [{i + 1}/{len(data_rows)}] {name} -> FOUND: {c_name}")
        else:
            not_found += 1

    print(f"\nResults: {found} found on Impact, {not_found} not found, {already_set} skipped")

    if DRY_RUN:
        print("\n[DRY RUN] Would update:")
        for row_idx, upd in updates:
            print(f"  Row {row_idx}: {upd}")
    elif updates:
        print(f"Writing {len(updates)} updates to sheet...")
        batch_data = []
        for row_idx, upd in updates:
            for col_name, value in upd.items():
                if col_name in col_map:
                    col_letter = chr(ord('A') + col_map[col_name])
                    batch_data.append({
                        'range': f"Merchants!{col_letter}{row_idx}",
                        'values': [[value]],
                    })
        if batch_data:
            sheets_service.spreadsheets().values().batchUpdate(
                spreadsheetId=SHEET_ID,
                body={'valueInputOption': 'RAW', 'data': batch_data},
            ).execute()
            print(f"  Wrote {len(batch_data)} cell updates")

    impact_client.close()


# ── Fallback Path: Generate manual search checklist ────────────────────────────
else:
    print("\nGenerating prioritized manual search checklist for Impact.com...")

    # Find merchants NOT yet found on any affiliate network
    priority_order = {'High': 0, 'Medium': 1, 'Low': 2}
    checklist = []

    for i, row in enumerate(data_rows):
        name = get_cell(row, 'name')
        website = get_cell(row, 'website_url')
        priority = get_cell(row, 'priority')
        existing_network = get_cell(row, 'affiliate_network')
        notes = get_cell(row, 'notes')

        # Include merchants not found on CJ or with no network data
        needs_search = (
            not existing_network
            or existing_network.lower() in ('', 'not_available')
            or 'not found' in notes.lower()
        )

        if needs_search:
            checklist.append({
                'name': name,
                'website': website,
                'priority': priority or 'Medium',
                'sort_key': (priority_order.get(priority, 1), name.lower()),
            })

    checklist.sort(key=lambda x: x['sort_key'])

    print(f"\n{'=' * 70}")
    print(f"  Impact.com Manual Search Checklist")
    print(f"  {len(checklist)} merchants to search (sorted by priority)")
    print(f"{'=' * 70}\n")

    current_priority = None
    for item in checklist:
        if item['priority'] != current_priority:
            current_priority = item['priority']
            print(f"\n--- {current_priority} Priority ---\n")

        website_hint = f"  ({item['website']})" if item['website'] else ''
        print(f"  [ ] {item['name']}{website_hint}")

    print(f"\n{'=' * 70}")
    print(f"Total: {len(checklist)} merchants to search in Impact.com dashboard")
    high = sum(1 for c in checklist if c['priority'] == 'High')
    medium = sum(1 for c in checklist if c['priority'] == 'Medium')
    low = sum(1 for c in checklist if c['priority'] == 'Low')
    print(f"  High: {high} | Medium: {medium} | Low: {low}")
    print(f"\nTip: Start with High priority merchants for maximum revenue impact.")
    print(f"In Impact dashboard: Brands > Search > type merchant name")

print("\nDone!")
