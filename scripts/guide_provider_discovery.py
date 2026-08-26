"""Focused affiliate discovery for guide comparison table providers.

Searches CJ (and optionally Impact.com) for the specific providers listed in
Saverwell's guide comparison tables. These are the highest-value affiliate
targets because they sit on dedicated comparison pages.

Reads provider names directly from Supabase guide_articles comparison_table
JSONB, then searches affiliate networks. Results are written to stdout and
optionally to a new 'Guide Providers' tab in the research sheet.

Requires:
  CJ_API_TOKEN + CJ_COMPANY_ID
  SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY

Optional:
  IMPACT_ACCOUNT_SID + IMPACT_AUTH_TOKEN
  AFFILIATE_RESEARCH_SHEET_ID (to write results tab)

Usage:
  python scripts/guide_provider_discovery.py [--write-sheet]
"""

import os
import re
import sys
import time
from pathlib import Path

import json

import httpx
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

CJ_API_TOKEN = os.environ.get('CJ_API_TOKEN', '')
CJ_COMPANY_ID = os.environ.get('CJ_COMPANY_ID', '')
IMPACT_SID = os.environ.get('IMPACT_ACCOUNT_SID', '')
IMPACT_TOKEN = os.environ.get('IMPACT_AUTH_TOKEN', '')
SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_SERVICE_ROLE_KEY']
SHEET_ID = os.environ.get('AFFILIATE_RESEARCH_SHEET_ID', '')
OAUTH_TOKEN_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'data', 'google-token.json'
)

WRITE_SHEET = '--write-sheet' in sys.argv

SUPABASE_HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
}

# Guide slugs and their match keys for comparison tables
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

CJ_RATE_DELAY = 2.5


# ── Helpers ─────────────────────────────────────────────────────────────────────

def normalize_name(name):
    """Normalize for fuzzy comparison."""
    name = name.lower().strip()
    name = re.sub(r'[^a-z0-9\s]', '', name)
    name = re.sub(r'\s+', ' ', name)
    for suffix in [' inc', ' llc', ' corp', ' co', ' company']:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()


# ── Step 1: Fetch guide comparison tables from Supabase ────────────────────────
print("Fetching guide comparison tables from Supabase...")

client = httpx.Client(timeout=30)

all_providers = {}  # {(guide_slug, provider_name): match_key}

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
        print(f"  {slug}: no comparison table found")
        continue

    table = rows[0]['comparison_table']
    if isinstance(table, str):
        table = json.loads(table)
    providers = []
    for row in table:
        name = row.get(match_key, '')
        if name:
            providers.append(name)
            all_providers[(slug, name)] = match_key

    print(f"  {slug}: {len(providers)} providers - {', '.join(providers[:5])}")

unique_providers = list(set(name for _, name in all_providers.keys()))
print(f"\nTotal unique providers to search: {len(unique_providers)}")


# ── Step 2: Search CJ for each provider ────────────────────────────────────────

cj_results = {}  # provider_name -> {found, advertiser_name, advertiser_id, ...}

if CJ_API_TOKEN and CJ_COMPANY_ID:
    import xml.etree.ElementTree as ET

    print(f"\nSearching CJ for {len(unique_providers)} providers...")

    cj_client = httpx.Client(
        timeout=30,
        headers={
            'Authorization': f'Bearer {CJ_API_TOKEN}',
            'Accept': 'application/xml',
        },
    )

    CJ_BASE = 'https://advertiser-lookup.api.cj.com/v2/advertiser-lookup'

    def _xml_text(elem, tag, default=''):
        child = elem.find(tag)
        return child.text.strip() if child is not None and child.text else default

    for i, provider in enumerate(unique_providers):
        print(f"  [{i + 1}/{len(unique_providers)}] {provider}", end='', flush=True)

        params = {
            'requestor-cid': CJ_COMPANY_ID,
            'advertiser-name': provider,
        }

        try:
            resp = cj_client.get(CJ_BASE, params=params)
            if resp.status_code == 200:
                root = ET.fromstring(resp.text)
                advs_elem = root.find('advertisers')
                advertisers = advs_elem.findall('advertiser') if advs_elem is not None else []

                # Find best match
                norm_provider = normalize_name(provider)
                match = None
                for adv in advertisers:
                    adv_name = _xml_text(adv, 'advertiser-name')
                    norm_adv = normalize_name(adv_name)
                    if norm_provider in norm_adv or norm_adv in norm_provider:
                        match = adv
                        break

                if match:
                    adv_name = _xml_text(match, 'advertiser-name')
                    adv_id = _xml_text(match, 'advertiser-id')
                    cj_results[provider] = {
                        'found': True,
                        'network': 'CJ',
                        'advertiser_name': adv_name,
                        'advertiser_id': adv_id,
                        'program_url': f"https://members.cj.com/publisher/{CJ_COMPANY_ID}/advertiser-detail/{adv_id}",
                    }
                    print(f" -> FOUND: {adv_name}")
                else:
                    cj_results[provider] = {'found': False}
                    print(" -> not found")
            else:
                cj_results[provider] = {'found': False}
                print(f" -> API error {resp.status_code}")
        except Exception as e:
            cj_results[provider] = {'found': False}
            print(f" -> error: {e}")

        time.sleep(CJ_RATE_DELAY)

    cj_client.close()
else:
    print("\nSkipping CJ search (no API credentials)")
    for p in unique_providers:
        cj_results[p] = {'found': False}


# ── Step 3: Search Impact.com ──────────────────────────────────────────────────

impact_results = {}  # provider_name -> {found, campaign_name, ...}

if IMPACT_SID and IMPACT_TOKEN:
    print(f"\nSearching Impact.com for {len(unique_providers)} providers...")

    impact_client = httpx.Client(
        timeout=30,
        auth=(IMPACT_SID, IMPACT_TOKEN),
    )

    # Fetch all campaigns once
    all_campaigns = []
    page = 1
    while True:
        resp = impact_client.get(
            f'https://api.impact.com/Mediapartners/{IMPACT_SID}/Campaigns',
            params={'PageSize': 100, 'Page': page},
            headers={'Accept': 'application/json'},
        )
        if resp.status_code != 200:
            print(f"  Impact API error: {resp.status_code}")
            break
        data = resp.json()
        campaigns = data.get('Campaigns', [])
        if not campaigns:
            break
        all_campaigns.extend(campaigns)
        total = data.get('@total', 0)
        if len(all_campaigns) >= total:
            break
        page += 1
        time.sleep(0.5)

    print(f"  Loaded {len(all_campaigns)} Impact campaigns")

    # Build name index
    campaign_index = {}
    for c in all_campaigns:
        norm = normalize_name(c.get('CampaignName', ''))
        campaign_index[norm] = c

    # Match providers
    for provider in unique_providers:
        norm_provider = normalize_name(provider)
        match = campaign_index.get(norm_provider)

        if not match:
            for c_name, c in campaign_index.items():
                if norm_provider in c_name or c_name in norm_provider:
                    match = c
                    break

        if match:
            impact_results[provider] = {
                'found': True,
                'network': 'Impact',
                'campaign_name': match.get('CampaignName', ''),
                'campaign_id': match.get('CampaignId', ''),
            }
        else:
            impact_results[provider] = {'found': False}

    impact_client.close()
else:
    print("\nSkipping Impact search (no API credentials)")
    for p in unique_providers:
        impact_results[p] = {'found': False}


# ── Step 4: Print results summary ──────────────────────────────────────────────

print(f"\n{'=' * 80}")
print(f"  GUIDE PROVIDER AFFILIATE DISCOVERY RESULTS")
print(f"{'=' * 80}\n")

# Group by guide
for slug, match_key in GUIDE_CONFIGS.items():
    providers_in_guide = [name for (s, name) in all_providers.keys() if s == slug]
    if not providers_in_guide:
        continue

    print(f"\n--- {slug} (match on: {match_key}) ---\n")

    for provider in providers_in_guide:
        cj = cj_results.get(provider, {})
        impact = impact_results.get(provider, {})

        cj_status = 'CJ' if cj.get('found') else ''
        impact_status = 'Impact' if impact.get('found') else ''

        networks = [n for n in [cj_status, impact_status] if n]

        if networks:
            network_str = ' + '.join(networks)
            details = []
            if cj.get('found'):
                details.append(f"CJ: {cj.get('advertiser_name', '')}")
            if impact.get('found'):
                details.append(f"Impact: {impact.get('campaign_name', '')}")
            print(f"  [FOUND] {provider} -> {network_str}")
            for d in details:
                print(f"          {d}")
        else:
            print(f"  [NONE]  {provider} -> Not on CJ or Impact")
            print(f"          Check: ShareASale, Rakuten, or direct affiliate program")

# Summary stats
found_on_any = sum(
    1 for p in unique_providers
    if cj_results.get(p, {}).get('found') or impact_results.get(p, {}).get('found')
)
found_cj_only = sum(
    1 for p in unique_providers
    if cj_results.get(p, {}).get('found') and not impact_results.get(p, {}).get('found')
)
found_impact_only = sum(
    1 for p in unique_providers
    if not cj_results.get(p, {}).get('found') and impact_results.get(p, {}).get('found')
)
found_both = sum(
    1 for p in unique_providers
    if cj_results.get(p, {}).get('found') and impact_results.get(p, {}).get('found')
)
found_neither = len(unique_providers) - found_on_any

print(f"\n{'=' * 80}")
print(f"  SUMMARY")
print(f"{'=' * 80}")
print(f"  Total providers:     {len(unique_providers)}")
print(f"  Found on CJ only:    {found_cj_only}")
print(f"  Found on Impact only: {found_impact_only}")
print(f"  Found on both:       {found_both}")
print(f"  Not found on either: {found_neither}")
print(f"{'=' * 80}")


# ── Step 5: Optionally write results to sheet ──────────────────────────────────

if WRITE_SHEET and SHEET_ID:
    print(f"\nWriting results to 'Guide Providers' tab in research sheet...")

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

    # Add new sheet tab
    try:
        sheets_service.spreadsheets().batchUpdate(
            spreadsheetId=SHEET_ID,
            body={'requests': [{'addSheet': {'properties': {'title': 'Guide Providers'}}}]},
        ).execute()
    except Exception:
        # Tab may already exist - clear it
        sheets_service.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID,
            range='Guide Providers!A:H',
        ).execute()

    # Build rows
    tab_headers = [
        'guide_slug', 'provider_name', 'match_key', 'on_cj', 'on_impact',
        'best_network', 'cj_program_url', 'notes',
    ]
    tab_rows = [tab_headers]

    for (slug, provider), match_key in sorted(all_providers.items()):
        cj = cj_results.get(provider, {})
        impact = impact_results.get(provider, {})

        on_cj = 'Yes' if cj.get('found') else 'No'
        on_impact = 'Yes' if impact.get('found') else 'No'

        if cj.get('found') and impact.get('found'):
            best = 'Both - compare rates'
        elif cj.get('found'):
            best = 'CJ'
        elif impact.get('found'):
            best = 'Impact'
        else:
            best = 'Manual search needed'

        notes_parts = []
        if cj.get('found'):
            notes_parts.append(f"CJ: {cj.get('advertiser_name', '')}")
        if impact.get('found'):
            notes_parts.append(f"Impact: {impact.get('campaign_name', '')}")
        if not cj.get('found') and not impact.get('found'):
            notes_parts.append('Check ShareASale, Rakuten, or direct program')

        tab_rows.append([
            slug,
            provider,
            match_key,
            on_cj,
            on_impact,
            best,
            cj.get('program_url', ''),
            '; '.join(notes_parts),
        ])

    sheets_service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range='Guide Providers!A1',
        valueInputOption='RAW',
        body={'values': tab_rows},
    ).execute()

    print(f"  Wrote {len(tab_rows) - 1} provider rows to 'Guide Providers' tab")

client.close()

print("\nDone!")
if found_neither > 0:
    print(f"\n{found_neither} providers not found on CJ or Impact.")
    print("For these, try:")
    print("  1. ShareASale (shareasale.com) - common for health/wellness brands")
    print("  2. Rakuten Advertising - some insurance/telecom brands")
    print("  3. Direct affiliate programs - google '[provider name] affiliate program'")
