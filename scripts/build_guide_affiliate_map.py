"""Auto-generate guide_affiliate_map.json from approved affiliate URLs.

Reads the research sheet and the 'Guide Providers' tab (if present) to build
the affiliate mapping config used by populate_guide_affiliate_links.py.

Matches providers in guide comparison tables to approved affiliate URLs from
either the Guide Providers tab or the main Merchants tab.

Requires:
  AFFILIATE_RESEARCH_SHEET_ID
  SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY

Usage:
  python scripts/build_guide_affiliate_map.py [--dry-run]
"""

import json
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
SHEET_ID = os.environ.get('AFFILIATE_RESEARCH_SHEET_ID', '')
OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'google-token.json'
)
OUTPUT_PATH = project_root / 'data' / 'saverwell' / 'guide_affiliate_map.json'

DRY_RUN = '--dry-run' in sys.argv

SUPABASE_HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
}

# Guide configs: slug -> match_key for comparison table
GUIDE_CONFIGS = {
    'cell-phone-plans-seniors': 'carrier',
    'medical-alert-systems-guide': 'provider',
    'medical-alert-systems-cost': 'provider',
    'save-on-hearing-aids': 'brand',
    'dental-insurance-seniors': 'provider',
    'vision-insurance-seniors': 'provider',
    'life-insurance-seniors-over-65': 'provider',
    'auto-home-insurance-seniors': 'provider',
    'medicare-supplement-plans-explained': 'provider',
}

client = httpx.Client(timeout=30)


# ── Step 1: Fetch provider names from Supabase guide comparison tables ─────────
print("Fetching guide comparison tables from Supabase...")

guide_providers = {}  # slug -> {match_key, providers: [name1, name2, ...]}

for slug, match_key in GUIDE_CONFIGS.items():
    resp = client.get(
        f'{SUPABASE_URL}/rest/v1/guide_articles',
        headers=SUPABASE_HEADERS,
        params={
            'select': 'slug,comparison_table',
            'slug': f'eq.{slug}',
            'limit': '1',
        },
    )
    resp.raise_for_status()
    rows = resp.json()

    if not rows or not rows[0].get('comparison_table'):
        print(f"  {slug}: no comparison table")
        continue

    table = rows[0]['comparison_table']

    # Handle both formats: list-of-dicts (draft JSON) and headers/rows (Supabase JSONB)
    if isinstance(table, dict) and 'headers' in table and 'rows' in table:
        headers = table['headers']
        key_idx = None
        for i, h in enumerate(headers):
            if h.lower().replace(' ', '_') == match_key or h.lower() == match_key:
                key_idx = i
                break
        if key_idx is None:
            print(f"  {slug}: match_key '{match_key}' not found in headers {headers}")
            continue
        providers = [row[key_idx] for row in table['rows'] if len(row) > key_idx and row[key_idx]]
    elif isinstance(table, list):
        providers = [row.get(match_key, '') for row in table if isinstance(row, dict) and row.get(match_key)]
    else:
        print(f"  {slug}: unexpected comparison_table format: {type(table)}")
        continue
    guide_providers[slug] = {
        'match_key': match_key,
        'providers': providers,
    }
    print(f"  {slug}: {len(providers)} providers")


# ── Step 2: Build provider-to-URL mapping from approved merchants ──────────────
print("\nBuilding provider-to-URL mapping...")

# Source 1: Main Merchants tab (for national merchants that are also guide providers)
merchant_urls = {}  # normalized name -> affiliate_url

if SHEET_ID:
    from cmo_agent.google_auth import get_google_credentials
    from googleapiclient.discovery import build

    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH, service_account_path="", scopes=SCOPES
    )

    if creds:
        sheets_service = build('sheets', 'v4', credentials=creds)

        # Read main merchants tab
        result = sheets_service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range='Merchants!A1:M',
        ).execute()
        values = result.get('values', [])

        if len(values) >= 2:
            headers = values[0]
            col_map = {h: i for i, h in enumerate(headers)}

            for row in values[1:]:
                def get(col):
                    idx = col_map.get(col, -1)
                    return row[idx].strip() if 0 <= idx < len(row) else ''

                name = get('name')
                url = get('affiliate_url')
                status = get('approval_status')

                if name and url and status == 'approved':
                    merchant_urls[name.lower().strip()] = url

            print(f"  Merchants tab: {len(merchant_urls)} approved URLs")

        # Try reading Guide Providers tab (created by guide_provider_discovery.py)
        try:
            result2 = sheets_service.spreadsheets().values().get(
                spreadsheetId=SHEET_ID,
                range='Guide Providers!A1:H',
            ).execute()
            gp_values = result2.get('values', [])

            if len(gp_values) >= 2:
                gp_headers = gp_values[0]
                gp_col_map = {h: i for i, h in enumerate(gp_headers)}

                # Guide Providers tab may have direct URLs
                for row in gp_values[1:]:
                    def gp_get(col):
                        idx = gp_col_map.get(col, -1)
                        return row[idx].strip() if 0 <= idx < len(row) else ''

                    provider_name = gp_get('provider_name')
                    # Check if there's a URL in the notes or program URL
                    program_url = gp_get('cj_program_url')
                    if provider_name and program_url:
                        # Store program URL as fallback reference
                        key = provider_name.lower().strip()
                        if key not in merchant_urls:
                            merchant_urls[key] = ''  # Placeholder - needs actual tracking URL

                print(f"  Guide Providers tab: loaded provider references")
        except Exception:
            print(f"  Guide Providers tab: not found (run guide_provider_discovery.py first)")

else:
    print("  No SHEET_ID - using Supabase merchants with active affiliate status")

    # Fallback: read directly from Supabase
    resp = client.get(
        f'{SUPABASE_URL}/rest/v1/merchants',
        headers=SUPABASE_HEADERS,
        params={
            'select': 'name,affiliate_url',
            'affiliate_status': 'eq.active',
            'affiliate_url': 'not.is.null',
        },
    )
    resp.raise_for_status()
    for m in resp.json():
        if m.get('name') and m.get('affiliate_url'):
            merchant_urls[m['name'].lower().strip()] = m['affiliate_url']
    print(f"  Supabase: {len(merchant_urls)} active affiliate URLs")


# ── Step 3: Match providers to URLs and build map ──────────────────────────────
print("\nMatching guide providers to affiliate URLs...")

affiliate_map = {}
matched_total = 0
unmatched_total = 0

for slug, config in guide_providers.items():
    match_key = config['match_key']
    providers = config['providers']
    affiliates = {}

    for provider in providers:
        provider_lower = provider.lower().strip()

        # Try exact match
        url = merchant_urls.get(provider_lower, '')

        # Try partial match if no exact
        if not url:
            for merch_name, merch_url in merchant_urls.items():
                if provider_lower in merch_name or merch_name in provider_lower:
                    url = merch_url
                    break

        if url:
            affiliates[provider] = url
            matched_total += 1
        else:
            unmatched_total += 1

    affiliate_map[slug] = {
        'match_key': match_key,
        'affiliates': affiliates,
    }

    matched = len(affiliates)
    total = len(providers)
    print(f"  {slug}: {matched}/{total} providers matched")


# ── Step 4: Write output ───────────────────────────────────────────────────────
print(f"\nTotal: {matched_total} matched, {unmatched_total} unmatched")

if DRY_RUN:
    print(f"\n[DRY RUN] Would write to {OUTPUT_PATH}:")
    print(json.dumps(affiliate_map, indent=2))
else:
    with open(OUTPUT_PATH, 'w') as f:
        json.dump(affiliate_map, f, indent=2)
        f.write('\n')
    print(f"\nWrote {OUTPUT_PATH}")

    # Count non-empty affiliate maps
    active_guides = sum(1 for v in affiliate_map.values() if v['affiliates'])
    print(f"  {active_guides} guides have affiliate URLs")

client.close()

print(f"\nDone!")
if matched_total > 0:
    print(f"\nNext step: run populate_guide_affiliate_links.py to inject URLs into Supabase")
if unmatched_total > 0:
    print(f"\n{unmatched_total} providers still need affiliate URLs.")
    print("These may be on networks other than CJ/Impact, or may need manual research.")
