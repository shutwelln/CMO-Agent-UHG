"""Deactivate merchants whose only discounts are the bogus 55% rows.

These 58 merchants have:
  - At least one row in discounts_v2 with discount_value = '55%'
  - is_active = true in the merchants table
  - NO other active discounts (no rows where discount_value != '55%' AND active = true)

They offer no real savings to users and should be hidden from the marketplace.

Set DRY_RUN = False to execute the actual deactivation.
"""

import os
import sys
import httpx
from dotenv import load_dotenv

# ──────────────────────────────────────────────────────────────────────
DRY_RUN = False  # Set to False to actually deactivate merchants
# ──────────────────────────────────────────────────────────────────────

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

url = os.environ['SUPABASE_URL']
key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
headers = {
    'apikey': key,
    'Authorization': f'Bearer {key}',
    'Content-Type': 'application/json',
    'Prefer': 'return=minimal',
}
client = httpx.Client(timeout=30)


def get_55_merchant_ids() -> set:
    """Return all merchant_ids that have at least one 55% discount row."""
    ids = set()
    offset = 0
    while True:
        r = client.get(f'{url}/rest/v1/discounts_v2', headers=headers, params={
            'select': 'merchant_id',
            'discount_value': 'eq.55%',
            'limit': '500',
            'offset': str(offset),
        })
        r.raise_for_status()
        batch = r.json()
        if not batch:
            break
        for row in batch:
            ids.add(row['merchant_id'])
        offset += 500
    return ids


def filter_active_merchants(merchant_ids: set) -> list:
    """Return (id, name) tuples for merchants where is_active = true."""
    active = []
    sorted_ids = sorted(merchant_ids)
    for i in range(0, len(sorted_ids), 50):
        batch = sorted_ids[i:i + 50]
        ids_str = ','.join(str(x) for x in batch)
        r = client.get(f'{url}/rest/v1/merchants', headers=headers, params={
            'select': 'id,name',
            'id': f'in.({ids_str})',
            'is_active': 'eq.true',
            'limit': '500',
        })
        r.raise_for_status()
        for m in r.json():
            active.append((m['id'], m['name']))
    return active


def filter_only_55(active_merchants: list) -> list:
    """Return merchants that have NO other active discounts besides 55%."""
    orphans = []
    for mid, mname in active_merchants:
        r = client.get(f'{url}/rest/v1/discounts_v2', headers=headers, params={
            'select': 'discount_value,active',
            'merchant_id': f'eq.{mid}',
            'discount_value': 'neq.55%',
            'active': 'eq.true',
            'limit': '10',
        })
        r.raise_for_status()
        other_active = r.json()
        if not other_active:
            orphans.append((mid, mname))
    return sorted(orphans, key=lambda x: x[1])


def deactivate_merchant(merchant_id: int) -> bool:
    """Set is_active = false for a single merchant. Returns True on success."""
    r = client.patch(
        f'{url}/rest/v1/merchants',
        headers=headers,
        params={'id': f'eq.{merchant_id}'},
        json={'is_active': False},
    )
    return r.status_code in (200, 204)


def main():
    mode = 'DRY RUN' if DRY_RUN else 'LIVE'
    print(f'=== Deactivate 55%-Only Orphan Merchants ({mode}) ===\n')

    # Step 1: Find all merchant_ids with 55% discount rows
    all_55_ids = get_55_merchant_ids()
    print(f'[1/3] Merchants with 55% discount rows: {len(all_55_ids)}')

    # Step 2: Filter to active merchants only
    active_merchants = filter_active_merchants(all_55_ids)
    print(f'[2/3] Of those, currently active: {len(active_merchants)}')

    # Step 3: Filter to those with no other active discounts
    orphans = filter_only_55(active_merchants)
    print(f'[3/3] With ONLY 55% (no real discounts): {len(orphans)}')

    if not orphans:
        print('\nNo orphan merchants found. Nothing to do.')
        return

    print(f'\n{"#":<4} {"ID":<8} {"Status":<14} Name')
    print('-' * 70)

    success = 0
    failed = 0

    for i, (mid, mname) in enumerate(orphans, 1):
        if DRY_RUN:
            status = 'WOULD DEACT'
            print(f'{i:<4} {mid:<8} {status:<14} {mname}')
            success += 1
        else:
            ok = deactivate_merchant(mid)
            if ok:
                status = 'DEACTIVATED'
                success += 1
            else:
                status = 'FAILED'
                failed += 1
            print(f'{i:<4} {mid:<8} {status:<14} {mname}')

    print('-' * 70)
    print(f'\nSummary ({mode}):')
    print(f'  Total orphans found: {len(orphans)}')
    if DRY_RUN:
        print(f'  Would deactivate: {success}')
        print(f'\n  >>> Set DRY_RUN = False at the top of this script to execute. <<<')
    else:
        print(f'  Successfully deactivated: {success}')
        if failed:
            print(f'  Failed: {failed}')


if __name__ == '__main__':
    main()
