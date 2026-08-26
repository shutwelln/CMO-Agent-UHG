"""Batch-search CJ Affiliate for Saverwell merchants.

Reads the 'Saverwell Affiliate Research' Google Sheet, queries CJ's
Advertiser Lookup API for each merchant, and writes results (affiliate_network,
commission info, program URL) back to the sheet.

Requires:
  CJ_API_TOKEN       - Personal Access Token from developers.cj.com
  CJ_COMPANY_ID      - Your CJ publisher company ID (7 digits)
  AFFILIATE_RESEARCH_SHEET_ID - Google Sheet ID

Usage:
  python scripts/cj_merchant_discovery.py [--dry-run]
"""

import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

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
    print("Get yours at developers.cj.com > Authentication > Personal Access Tokens")
    sys.exit(1)

if not CJ_COMPANY_ID:
    print("ERROR: CJ_COMPANY_ID not set in .env")
    print("Find your 7-digit company ID in the CJ dashboard URL")
    sys.exit(1)

if not SHEET_ID:
    print("ERROR: AFFILIATE_RESEARCH_SHEET_ID not set in .env")
    sys.exit(1)


# ── CJ API client ──────────────────────────────────────────────────────────────

CJ_BASE = 'https://advertiser-lookup.api.cj.com/v2/advertiser-lookup'
CJ_HEADERS = {
    'Authorization': f'Bearer {CJ_API_TOKEN}',
    'Accept': 'application/xml',
}

# Rate limit: 25 calls/min. We pace at ~2.5s per call to stay safe.
RATE_LIMIT_DELAY = 2.5

cj_client = httpx.Client(timeout=30, headers=CJ_HEADERS)


def _xml_text(element, tag, default=''):
    """Get text content of a child XML element."""
    child = element.find(tag)
    return child.text.strip() if child is not None and child.text else default


def _parse_advertisers_xml(xml_text):
    """Parse CJ XML response into a list of advertiser dicts."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []

    advertisers_elem = root.find('advertisers')
    if advertisers_elem is None:
        return []

    results = []
    for adv in advertisers_elem.findall('advertiser'):
        # Extract commission info from actions
        commission_parts = []
        commission_type = 'CPS'
        actions_elem = adv.find('actions')
        if actions_elem is not None:
            for action in actions_elem.findall('action'):
                action_type = _xml_text(action, 'type')
                comm_elem = action.find('commission')
                if comm_elem is not None:
                    default_rate = _xml_text(comm_elem, 'default')
                    if default_rate:
                        commission_parts.append(default_rate)
                        if 'sale' in action_type.lower():
                            commission_type = 'CPS'
                        elif 'lead' in action_type.lower():
                            commission_type = 'CPL'
                        elif 'click' in action_type.lower():
                            commission_type = 'CPC'

        results.append({
            'advertiser-id': _xml_text(adv, 'advertiser-id'),
            'advertiser-name': _xml_text(adv, 'advertiser-name'),
            'program-url': _xml_text(adv, 'program-url'),
            'account-status': _xml_text(adv, 'account-status'),
            'relationship-status': _xml_text(adv, 'relationship-status'),
            'commission_rate': '; '.join(commission_parts),
            'commission_type': commission_type,
        })

    return results


def search_cj(search_term):
    """Search CJ for advertisers. Returns list of parsed dicts."""
    params = {
        'requestor-cid': CJ_COMPANY_ID,
        'advertiser-name': search_term,
    }
    try:
        resp = cj_client.get(CJ_BASE, params=params)
        if resp.status_code == 200:
            return _parse_advertisers_xml(resp.text)
        elif resp.status_code in (404, 406):
            return []
        else:
            print(f"    CJ API error {resp.status_code}: {resp.text[:200]}")
            return []
    except Exception as e:
        print(f"    CJ API exception: {e}")
        return []


def normalize_name(name):
    """Normalize merchant name for fuzzy comparison."""
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    for suffix in [' inc', ' llc', ' corp', ' co', ' company', ' stores', ' store']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


def find_best_match(merchant_name, website_url, advertisers):
    """Pick the best CJ advertiser match from search results."""
    if not advertisers:
        return None

    norm_merchant = normalize_name(merchant_name)
    domain = ''
    if website_url:
        domain = urlparse(website_url).netloc or ''
        domain = domain.replace('www.', '').lower()

    best = None
    best_score = 0

    for adv in advertisers:
        adv_name = adv.get('advertiser-name', '')
        adv_url = adv.get('program-url', '')
        norm_adv = normalize_name(adv_name)
        score = 0

        # Exact name match
        if norm_adv == norm_merchant:
            score = 100
        # Domain match (high confidence)
        elif domain and domain in adv_url.lower():
            score = 80
        # Name contains merchant name
        elif norm_merchant in norm_adv or norm_adv in norm_merchant:
            score = 70

        if score > best_score:
            best_score = score
            best = adv

    # Require at least a partial match (score >= 70)
    if best_score >= 70:
        return best
    return None


# ── Step 1: Read Google Sheet ──────────────────────────────────────────────────
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
    print("No data rows found in sheet.")
    sys.exit(0)

headers = values[0]
data_rows = values[1:]
col_map = {h: i for i, h in enumerate(headers)}

print(f"  Read {len(data_rows)} merchants")


# ── Step 2: Search CJ for each merchant ────────────────────────────────────────
print(f"\nSearching CJ for each merchant (pacing: {RATE_LIMIT_DELAY}s per call)...")
if DRY_RUN:
    print("  [DRY RUN - no sheet updates will be written]")

found = 0
not_found = 0
already_set = 0
updates = []  # (row_index, updates_dict) pairs

for i, row in enumerate(data_rows):
    row_idx = i + 2  # 1-indexed, +1 for header
    merchant_id = row[col_map['merchant_id']] if col_map['merchant_id'] < len(row) else ''
    name = row[col_map['name']] if col_map['name'] < len(row) else ''
    website = row[col_map['website_url']] if col_map['website_url'] < len(row) else ''
    existing_network = ''
    if col_map['affiliate_network'] < len(row):
        existing_network = row[col_map['affiliate_network']].strip()

    # Skip if already has affiliate data from any network
    if existing_network and existing_network.lower() not in ('', 'not_available'):
        already_set += 1
        continue

    print(f"  [{i + 1}/{len(data_rows)}] Searching: {name}", end='', flush=True)

    # Search by name first
    advertisers = search_cj(name)

    # If no results, try domain-based search
    if not advertisers and website:
        time.sleep(RATE_LIMIT_DELAY)
        domain = urlparse(website).netloc or website
        domain_name = domain.replace('www.', '').split('.')[0]
        advertisers = search_cj(domain_name)

    match = find_best_match(name, website, advertisers)

    if match:
        found += 1
        adv_name = match.get('advertiser-name', '')
        adv_id = match.get('advertiser-id', '')
        network_status = match.get('account-status', '')
        rel_status = match.get('relationship-status', '')

        row_updates = {
            'affiliate_network': 'CJ',
            'commission_rate': match.get('commission_rate', ''),
            'commission_type': match.get('commission_type', 'CPS'),
            'affiliate_program_url': f"https://members.cj.com/publisher/{CJ_COMPANY_ID}/advertiser-search?search={adv_name.replace(' ', '+')}" if adv_name else '',
            'notes': f"CJ match: {adv_name} ({rel_status})",
        }
        updates.append((row_idx, row_updates))
        print(f" -> FOUND: {adv_name} ({rel_status})")
    else:
        not_found += 1
        if not existing_network:
            updates.append((row_idx, {'notes': 'Not found on CJ'}))
        print(" -> not found")

    time.sleep(RATE_LIMIT_DELAY)


# ── Step 3: Write results back to sheet ─────────────────────────────────────────
print(f"\nResults: {found} found, {not_found} not found, {already_set} already had data")

if DRY_RUN:
    print("\n[DRY RUN] Would update the following rows:")
    for row_idx, upd in updates:
        print(f"  Row {row_idx}: {upd}")
    print("\nRe-run without --dry-run to write results.")
else:
    if updates:
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
                body={
                    'valueInputOption': 'RAW',
                    'data': batch_data,
                },
            ).execute()
            print(f"  Wrote {len(batch_data)} cell updates")
    else:
        print("No updates to write.")

cj_client.close()

print(f"\nDone!")
print(f"  Found on CJ: {found}")
print(f"  Not on CJ: {not_found}")
print(f"  Already had data: {already_set}")
print(f"\nNext steps:")
print(f"  1. Review results in the research sheet")
print(f"  2. Click 'Join Program' for desired CJ programs")
print(f"  3. Run impact_merchant_discovery.py for merchants not on CJ")
