"""Investigate the 55% discount rows - are they merchants or locations at merchants?"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

url = os.environ['SUPABASE_URL']
key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
h = {'apikey': key, 'Authorization': f'Bearer {key}'}
client = httpx.Client(timeout=30)

# Get all merchant_ids with 55% discounts
all_55_ids = set()
offset = 0
while True:
    r = client.get(f'{url}/rest/v1/discounts_v2', headers=h, params={
        'select': 'merchant_id', 'discount_value': 'eq.55%', 'limit': '500', 'offset': str(offset),
    })
    batch = r.json()
    if not batch:
        break
    for d in batch:
        all_55_ids.add(d['merchant_id'])
    offset += 500

print(f'Merchants with 55% discount rows: {len(all_55_ids)}')

# For each merchant, check if they have OTHER discounts
only_55 = []
has_other = []
for mid in sorted(all_55_ids):
    r = client.get(f'{url}/rest/v1/discounts_v2', headers=h, params={
        'select': 'discount_value,active', 'merchant_id': f'eq.{mid}', 'limit': '20',
    })
    discounts = r.json()
    real_discounts = [d for d in discounts if d.get('discount_value') not in ('55%', None)]
    if real_discounts:
        has_other.append(mid)
    else:
        only_55.append(mid)

print(f'Merchants with ONLY 55% (no legit discount): {len(only_55)}')
print(f'Merchants with 55% AND other real discounts: {len(has_other)}')

# Batch check store_locations for the only-55% merchants
has_stores_list = []
no_stores_list = []
for i in range(0, len(only_55), 50):
    batch_ids = only_55[i:i + 50]
    ids_str = ','.join(str(x) for x in batch_ids)
    r = client.get(f'{url}/rest/v1/store_locations', headers=h, params={
        'select': 'merchant_id', 'merchant_id': f'in.({ids_str})', 'limit': '5000',
    })
    found_mids = set(row['merchant_id'] for row in r.json())
    for mid in batch_ids:
        if mid in found_mids:
            has_stores_list.append(mid)
        else:
            no_stores_list.append(mid)

print(f'\nOf the {len(only_55)} only-55% merchants:')
print(f'  With store locations: {len(has_stores_list)}')
print(f'  Without store locations (orphaned): {len(no_stores_list)}')


def get_name(mid):
    r = client.get(f'{url}/rest/v1/merchants', headers=h, params={
        'select': 'name', 'id': f'eq.{mid}', 'limit': '1',
    })
    return r.json()[0]['name'] if r.json() else '?'


print(f'\n--- Only-55% merchants WITH stores (showing 15) ---')
for mid in has_stores_list[:15]:
    print(f'  {get_name(mid)} (id={mid})')

print(f'\n--- Only-55% merchants WITHOUT stores (showing 15) ---')
for mid in no_stores_list[:15]:
    print(f'  {get_name(mid)} (id={mid})')

print(f'\n--- Merchants with 55% AND real discounts (showing 15) ---')
for mid in has_other[:15]:
    r = client.get(f'{url}/rest/v1/discounts_v2', headers=h, params={
        'select': 'discount_value,active', 'merchant_id': f'eq.{mid}', 'limit': '10',
    })
    vals = [f'{d["discount_value"]} (active={d["active"]})' for d in r.json()]
    print(f'  {get_name(mid)}: {" | ".join(vals)}')
