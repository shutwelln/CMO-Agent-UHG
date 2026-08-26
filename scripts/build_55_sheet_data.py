"""Build dataset for the 55% discount investigation Google Sheet."""
import os
import json
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

url = os.environ['SUPABASE_URL']
key = os.environ['SUPABASE_SERVICE_ROLE_KEY']
h = {'apikey': key, 'Authorization': f'Bearer {key}'}
client = httpx.Client(timeout=30)

# 1. Fetch ALL 55% discount rows
print("Fetching 55% discount rows...")
all_55 = []
offset = 0
while True:
    r = client.get(f'{url}/rest/v1/discounts_v2', headers=h, params={
        'select': 'id,created_at,merchant_id,store_location_id,name,details,details_hyperlink,'
                  'discount_type,discount_value,requirement,active',
        'discount_value': 'eq.55%',
        'limit': '500',
        'offset': str(offset),
        'order': 'merchant_id.asc',
    })
    batch = r.json()
    if not batch:
        break
    all_55.extend(batch)
    offset += 500
print(f"  Found {len(all_55)} rows")

# 2. Collect unique merchant_ids and store_location_ids
merchant_ids = sorted(set(d['merchant_id'] for d in all_55))
store_loc_ids = sorted(set(d['store_location_id'] for d in all_55 if d.get('store_location_id')))
print(f"  {len(merchant_ids)} unique merchants, {len(store_loc_ids)} unique store locations")

# 3. Batch-fetch merchant info
print("Fetching merchant details...")
merchant_map = {}
for i in range(0, len(merchant_ids), 100):
    batch = merchant_ids[i:i + 100]
    ids_str = ','.join(str(x) for x in batch)
    r = client.get(f'{url}/rest/v1/merchants', headers=h, params={
        'select': 'id,name,merchant_type,website_url,is_active,category_id',
        'id': f'in.({ids_str})',
        'limit': '200',
    })
    for m in r.json():
        merchant_map[m['id']] = m

# 4. Batch-fetch store location info (store_locations -> locations_v2 for address)
print("Fetching store location details...")
store_loc_map = {}  # store_location_id -> {location_id, store_name, ...}
for i in range(0, len(store_loc_ids), 100):
    batch = store_loc_ids[i:i + 100]
    ids_str = ','.join(str(x) for x in batch)
    r = client.get(f'{url}/rest/v1/store_locations', headers=h, params={
        'select': 'id,merchant_id,location_id,store_name',
        'id': f'in.({ids_str})',
        'limit': '500',
    })
    for loc in r.json():
        store_loc_map[loc['id']] = loc

# 4b. Batch-fetch actual addresses from locations_v2
location_ids = sorted(set(
    sl['location_id'] for sl in store_loc_map.values() if sl.get('location_id')
))
print(f"  Fetching {len(location_ids)} location addresses...")
address_map = {}  # location_id -> {address1, city, state, zip, ...}
for i in range(0, len(location_ids), 100):
    batch = location_ids[i:i + 100]
    ids_str = ','.join(str(x) for x in batch)
    r = client.get(f'{url}/rest/v1/locations_v2', headers=h, params={
        'select': 'id,address1,address2,city,state,zip,phone',
        'id': f'in.({ids_str})',
        'limit': '500',
    })
    for addr in r.json():
        address_map[addr['id']] = addr

# 5. For each merchant, check if they have OTHER (non-55%) discounts
print("Checking for other discounts per merchant...")
other_discounts_map = {}  # merchant_id -> list of other discount values
for i in range(0, len(merchant_ids), 50):
    batch = merchant_ids[i:i + 50]
    ids_str = ','.join(str(x) for x in batch)
    r = client.get(f'{url}/rest/v1/discounts_v2', headers=h, params={
        'select': 'merchant_id,discount_value,active,store_location_id',
        'merchant_id': f'in.({ids_str})',
        'discount_value': 'neq.55%',
        'limit': '2000',
    })
    for d in r.json():
        mid = d['merchant_id']
        if mid not in other_discounts_map:
            other_discounts_map[mid] = []
        loc_label = f" (loc {d['store_location_id']})" if d.get('store_location_id') else " (merchant-level)"
        other_discounts_map[mid].append(
            f"{d['discount_value']} active={d['active']}{loc_label}"
        )

# 6. Build rows for the sheet
print("Building sheet data...")
rows = []
for d in all_55:
    mid = d['merchant_id']
    slid = d.get('store_location_id')
    merchant = merchant_map.get(mid, {})
    store_loc = store_loc_map.get(slid, {}) if slid else {}
    loc_id = store_loc.get('location_id')
    location = address_map.get(loc_id, {}) if loc_id else {}

    addr_parts = [location.get('address1', '')]
    if location.get('address2'):
        addr_parts.append(location['address2'])
    address = ', '.join(p for p in addr_parts if p)

    city_state_zip = ', '.join(filter(None, [
        location.get('city', ''),
        location.get('state', ''),
        location.get('zip', ''),
    ]))

    other = other_discounts_map.get(mid, [])
    other_str = '; '.join(other[:5])
    if len(other) > 5:
        other_str += f'; ... +{len(other) - 5} more'

    rows.append({
        'discount_id': d['id'],
        'merchant_id': mid,
        'merchant_name': merchant.get('name', d.get('name', '')),
        'merchant_type': merchant.get('merchant_type', ''),
        'merchant_active': merchant.get('is_active', ''),
        'store_location_id': slid or '',
        'address': address,
        'city_state_zip': city_state_zip,
        'discount_value': d['discount_value'],
        'discount_active': d['active'],
        'discount_type': d.get('discount_type', ''),
        'requirement': d.get('requirement', ''),
        'details': d.get('details', ''),
        'details_hyperlink': d.get('details_hyperlink', ''),
        'created_at': (d.get('created_at') or '')[:19].replace('T', ' '),
        'has_other_discounts': 'Yes' if other else 'No',
        'other_discounts': other_str,
    })

# Sort by merchant name then store location
rows.sort(key=lambda r: (r['merchant_name'].lower(), r['store_location_id']))

# Save as JSON for the Sheets agent
output_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'saverwell', '55_pct_investigation.json')
with open(output_path, 'w') as f:
    json.dump(rows, f, indent=2)

print(f"Saved {len(rows)} rows to {output_path}")
print(f"\nSummary:")
print(f"  Total 55% discount rows: {len(rows)}")
print(f"  Unique merchants: {len(merchant_ids)}")
print(f"  Unique store locations: {len(store_loc_ids)}")
print(f"  With other discounts: {sum(1 for r in rows if r['has_other_discounts'] == 'Yes')}")
print(f"  Without other discounts: {sum(1 for r in rows if r['has_other_discounts'] == 'No')}")
print(f"  Location-level (has store_location_id): {sum(1 for r in rows if r['store_location_id'])}")
print(f"  Merchant-level (no store_location_id): {sum(1 for r in rows if not r['store_location_id'])}")
