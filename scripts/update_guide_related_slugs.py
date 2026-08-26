"""Update guide article related_slugs to cross-link informational content to affiliate guides.

Adds high-commission affiliate guide slugs to the related_slugs array of
informational guides in the same vertical. This funnels readers from
informational content (Medicare explainers, etc.) to monetized guides
(hearing aids, medical alerts, phone plans).

Usage:
  python scripts/update_guide_related_slugs.py [--dry-run]
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

DRY_RUN = '--dry-run' in sys.argv

client = httpx.Client(timeout=30)

# ── Cross-linking rules ──────────────────────────────────────────────────────
# Maps informational guide slugs to affiliate guide slugs they should link to.
# Each informational guide gets 1-3 relevant affiliate guides in related_slugs.

CROSS_LINKS = {
    # Medicare guides -> hearing aids, insurance, medical alerts
    'medicare-explained-simple-guide': [
        'save-on-hearing-aids',
        'medical-alert-systems-guide',
        'medicare-supplement-plans-explained',
    ],
    'medicare-parts-a-b-c-d-explained': [
        'save-on-hearing-aids',
        'does-medicare-cover-dental',
        'medicare-supplement-plans-explained',
    ],
    'save-money-medicare-premiums': [
        'medicare-supplement-plans-explained',
        'save-on-hearing-aids',
        'dental-insurance-seniors',
    ],
    'medicare-enrollment-deadlines': [
        'medicare-supplement-plans-explained',
        'medicare-advantage-vs-original',
    ],
    'medicare-advantage-vs-original': [
        'medicare-supplement-plans-explained',
        'save-money-medicare-premiums',
    ],
    'does-medicare-cover-prescriptions': [
        'medicare-extra-help-prescription-savings',
        'save-money-medicare-premiums',
    ],
    'medicare-vs-medicaid-difference': [
        'medicare-supplement-plans-explained',
        'save-money-medicare-premiums',
    ],
    'does-medicare-cover-dental': [
        'dental-insurance-seniors',
        'medicare-supplement-plans-explained',
    ],
    'irmaa-avoid-higher-medicare-premiums': [
        'save-money-medicare-premiums',
        'medicare-supplement-plans-explained',
    ],
    'medicare-extra-help-prescription-savings': [
        'save-money-medicare-premiums',
        'medicare-supplement-plans-explained',
    ],
    'medicare-supplement-plans-explained': [
        'save-money-medicare-premiums',
        'medicare-advantage-vs-original',
    ],
    # Hearing aid informational -> hearing aid affiliate
    'does-medicare-cover-hearing-aids': [
        'save-on-hearing-aids',
    ],
    # Vision -> vision insurance
    'does-medicare-cover-vision': [
        'vision-insurance-seniors',
    ],
    # Phone informational -> phone plan affiliate
    'cut-phone-bill-after-65': [
        'cell-phone-plans-seniors',
    ],
    # Finance guides -> insurance/financial affiliate content
    'when-to-claim-social-security': [
        'life-insurance-seniors-over-65',
        'tax-deductions-seniors-over-65',
    ],
    'tax-deductions-seniors-over-65': [
        'when-to-claim-social-security',
        'auto-home-insurance-seniors',
    ],
    # Insurance informational -> insurance affiliate
    'auto-home-insurance-seniors': [
        'life-insurance-seniors-over-65',
    ],
    'dental-insurance-seniors': [
        'does-medicare-cover-dental',
        'vision-insurance-seniors',
    ],
    'vision-insurance-seniors': [
        'does-medicare-cover-vision',
        'dental-insurance-seniors',
    ],
    'life-insurance-seniors-over-65': [
        'auto-home-insurance-seniors',
        'when-to-claim-social-security',
    ],
    # Medical alert guides -> each other
    'medical-alert-systems-guide': [
        'medical-alert-systems-cost',
    ],
    'medical-alert-systems-cost': [
        'medical-alert-systems-guide',
    ],
    # Protection -> identity theft affiliate (future)
    'safe-online-shopping-tips': [
        'password-safety-guide',
    ],
    'password-safety-guide': [
        'safe-online-shopping-tips',
    ],
}


# ── Step 1: Fetch all guides ─────────────────────────────────────────────────
print("Fetching guide articles...")

resp = client.get(
    f'{SUPABASE_URL}/rest/v1/guide_articles',
    headers={
        'apikey': SUPABASE_KEY,
        'Authorization': f'Bearer {SUPABASE_KEY}',
    },
    params={
        'select': 'id,slug,related_slugs',
        'limit': '500',
    },
)
resp.raise_for_status()
guides = resp.json()

# Build lookup
guide_map = {g['slug']: g for g in guides}
existing_slugs = set(guide_map.keys())
print(f"  Found {len(guides)} guides in database")


# ── Step 2: Compute updates ──────────────────────────────────────────────────
print("Computing cross-link updates...")

updates = []
for source_slug, target_slugs in CROSS_LINKS.items():
    if source_slug not in guide_map:
        print(f"  SKIP {source_slug}: not in database")
        continue

    guide = guide_map[source_slug]
    current_related = guide.get('related_slugs') or []
    if isinstance(current_related, str):
        try:
            current_related = json.loads(current_related)
        except (json.JSONDecodeError, TypeError):
            current_related = []

    # Only add slugs that exist in the database and aren't already linked
    new_slugs = []
    for target in target_slugs:
        if target in existing_slugs and target not in current_related:
            new_slugs.append(target)

    if not new_slugs:
        continue

    merged = current_related + new_slugs
    updates.append({
        'slug': source_slug,
        'related_slugs': merged,
        'added': new_slugs,
    })

print(f"  {len(updates)} guides need cross-link updates")


# ── Step 3: Apply updates ────────────────────────────────────────────────────
if DRY_RUN:
    print("\n[DRY RUN] Would update:")
    for u in updates:
        print(f"  {u['slug']}: +{len(u['added'])} links -> {u['added']}")
    print("\nRun without --dry-run to apply.")
    sys.exit(0)

print("Applying updates to Supabase...")

updated = 0
failed = 0

for u in updates:
    resp = client.patch(
        f'{SUPABASE_URL}/rest/v1/guide_articles',
        headers=HEADERS,
        params={'slug': f'eq.{u["slug"]}'},
        json={'related_slugs': u['related_slugs']},
    )

    if resp.status_code in (200, 204):
        updated += 1
        print(f"  {u['slug']}: added {u['added']}")
    else:
        failed += 1
        print(f"  {u['slug']}: FAILED - {resp.status_code} {resp.text}")

client.close()

print(f"\nDone: {updated} updated, {failed} failed")
