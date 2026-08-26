"""Populate affiliate URLs in guide article comparison tables.

Updates the comparison_table JSONB in guide_articles, injecting affiliate_url
into each matching row. Non-destructive - preserves all existing data in
the comparison table objects.

Usage:
  python scripts/populate_guide_affiliate_links.py

Reads affiliate mappings from a JSON config file (data/saverwell/guide_affiliate_map.json).
The config maps guide slugs to provider-level affiliate URLs:

  {
    "cell-phone-plans-seniors": {
      "match_key": "carrier",
      "affiliates": {
        "Consumer Cellular": "https://consumercellu...?irclickid=...",
        "Cricket Wireless": "https://cricket...?irclickid=..."
      }
    },
    "medical-alert-systems-guide": {
      "match_key": "provider",
      "affiliates": {
        "Medical Guardian": "https://medicalguardian...?irclickid=..."
      }
    }
  }

Create this config file with your affiliate URLs before running.
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
HEADERS = {
    'apikey': SUPABASE_KEY,
    'Authorization': f'Bearer {SUPABASE_KEY}',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
}

CONFIG_PATH = project_root / 'data' / 'saverwell' / 'guide_affiliate_map.json'

client = httpx.Client(timeout=30)


# ── Step 1: Load affiliate mapping config ─────────────────────────────────────

if not CONFIG_PATH.exists():
    print(f"Config file not found: {CONFIG_PATH}")
    print("Create data/saverwell/guide_affiliate_map.json with your affiliate URL mappings.")
    print("See script docstring for format.")
    sys.exit(1)

with open(CONFIG_PATH) as f:
    affiliate_map = json.load(f)

print(f"Loaded affiliate mappings for {len(affiliate_map)} guides:")
for slug in affiliate_map:
    count = len(affiliate_map[slug].get('affiliates', {}))
    print(f"  {slug}: {count} providers")


# ── Step 2: Process each guide ────────────────────────────────────────────────
updated = 0
skipped = 0
failed = 0

for slug, config in affiliate_map.items():
    match_key = config.get('match_key', 'provider')
    affiliates = config.get('affiliates', {})

    if not affiliates:
        print(f"  {slug}: no affiliates configured, skipping")
        skipped += 1
        continue

    # Fetch current comparison_table
    resp = client.get(
        f'{SUPABASE_URL}/rest/v1/guide_articles',
        headers={
            'apikey': SUPABASE_KEY,
            'Authorization': f'Bearer {SUPABASE_KEY}',
        },
        params={
            'select': 'id,slug,comparison_table',
            'slug': f'eq.{slug}',
            'limit': '1',
        },
    )
    resp.raise_for_status()
    rows = resp.json()

    if not rows:
        print(f"  {slug}: guide not found in database, skipping")
        skipped += 1
        continue

    guide = rows[0]
    table = guide.get('comparison_table')

    if not table or not isinstance(table, list):
        print(f"  {slug}: no comparison_table data, skipping")
        skipped += 1
        continue

    # Inject affiliate_url into matching rows
    changes = 0
    for row in table:
        provider_name = row.get(match_key, '')
        if provider_name in affiliates:
            row['affiliate_url'] = affiliates[provider_name]
            changes += 1

    if changes == 0:
        print(f"  {slug}: no matching providers found, skipping")
        skipped += 1
        continue

    # Update Supabase
    resp = client.patch(
        f'{SUPABASE_URL}/rest/v1/guide_articles',
        headers=HEADERS,
        params={'slug': f'eq.{slug}'},
        json={'comparison_table': table},
    )

    if resp.status_code in (200, 204):
        updated += 1
        print(f"  {slug}: updated {changes} of {len(table)} rows with affiliate URLs")
    else:
        failed += 1
        print(f"  {slug}: FAILED - {resp.status_code} {resp.text}")

client.close()

print(f"\nDone: {updated} guides updated, {skipped} skipped, {failed} failed")
