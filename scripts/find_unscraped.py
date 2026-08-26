"""Find all merchants with Status=New and Action=Insert in Merchant Review
that have NOT been scraped yet. Cross-reference against Scraped Locations tab.
Group by category."""

from googleapiclient.discovery import build
from cmo_agent.google_auth import get_google_credentials
from collections import defaultdict

SHEET_ID = '1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84'
OAUTH_PATH = 'data/google-token.json'
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

creds = get_google_credentials(oauth_token_path=OAUTH_PATH, scopes=SCOPES)
if not creds:
    raise RuntimeError("Failed to load Google credentials")

svc = build('sheets', 'v4', credentials=creds)

# Get Scraped Locations - merchant names
result = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID,
    range='Scraped Locations!A:A'
).execute()
scraped_rows = result.get('values', [])
scraped_merchants = set()
for row in scraped_rows[1:]:
    if row:
        scraped_merchants.add(row[0].strip().lower())

print(f"Scraped Locations tab has {len(scraped_merchants)} unique merchant names.\n")

# Get Merchant Review
result = svc.spreadsheets().values().get(
    spreadsheetId=SHEET_ID,
    range='Merchant Review!A:Z'
).execute()
review_rows = result.get('values', [])
header = review_rows[0]
data = review_rows[1:]

# Find column indices
col_map = {h: i for i, h in enumerate(header)}
status_idx = col_map['Status']
action_idx = col_map['Action']
name_idx = col_map['name']
cat_idx = col_map['category_id']
national_idx = col_map.get('is_national')
website_idx = col_map.get('website_url')
locator_idx = col_map.get('Store Locator')
cat_display_idx = col_map.get('Category (display)')
online_idx = col_map.get('is_online_only')


def safe_get(row, idx):
    if idx is not None and len(row) > idx:
        return row[idx]
    return ''


# Cross-reference
unscraped_by_cat = defaultdict(list)

for row in data:
    status = safe_get(row, status_idx)
    action = safe_get(row, action_idx)
    name = safe_get(row, name_idx)
    cat = safe_get(row, cat_idx)
    cat_display = safe_get(row, cat_display_idx)
    national = safe_get(row, national_idx)
    website = safe_get(row, website_idx)
    locator = safe_get(row, locator_idx)
    online = safe_get(row, online_idx)

    if status != 'New' or action != 'Insert':
        continue

    # Check if already scraped (fuzzy match)
    name_lower = name.strip().lower()
    found = False
    for sm in scraped_merchants:
        if name_lower == sm or name_lower in sm or sm in name_lower:
            found = True
            break

    if not found:
        unscraped_by_cat[cat_display or cat].append({
            'name': name,
            'national': national,
            'website': website,
            'locator': locator,
            'online': online,
        })

print('=== UNSCRAPED NEW MERCHANTS (by category) ===')
print()
for cat in sorted(unscraped_by_cat.keys()):
    merchants = unscraped_by_cat[cat]
    print(f'--- {cat} ({len(merchants)}) ---')
    for m in sorted(merchants, key=lambda x: x['name']):
        online_flag = ' [ONLINE-ONLY]' if m['online'] == 'TRUE' else ''
        nat_flag = 'National' if m['national'] == 'TRUE' else 'Regional'
        loc_flag = ' | Has Locator' if m['locator'] else ''
        print(f"  {m['name']:45s} | {nat_flag:10s}{online_flag}{loc_flag}")
    print()

print(f"TOTAL UNSCRAPED: {sum(len(v) for v in unscraped_by_cat.values())}")
