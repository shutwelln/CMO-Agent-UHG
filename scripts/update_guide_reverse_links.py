"""Add bidirectional internal links from existing articles to new SEO4 articles.

When we publish 25 new articles, existing articles should link BACK to them.
This script adds 1 new related_slug to each of 21 existing articles, capped
at 4 total related_slugs per article.

Usage:
  python scripts/update_guide_reverse_links.py [--dry-run]
"""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=minimal",
}

DRY_RUN = "--dry-run" in sys.argv
MAX_RELATED = 4  # cap related_slugs at 4 per article

client = httpx.Client(timeout=30)

# ── Reverse link mapping (existing article -> new SEO4 article to add) ───────

REVERSE_LINKS = {
    "retirement-finances-reset-guide": "12-month-retirement-countdown-checklist",
    "when-to-claim-social-security": "real-cost-of-delaying-retirement",
    "file-social-security-at-62-or-wait": "real-cost-of-delaying-retirement",
    "senior-scam-protection-complete-guide": "senior-fraud-protection-bundle",
    "how-to-spot-fake-financial-coach": "financial-advisor-red-flags",
    "monthly-subscription-audit-retirees": "hidden-monthly-drains-retirees",
    "why-retirees-quit-budgeting-apps": "free-budgeting-tools-retirees",
    "dont-pay-it-back-yet-checklist": "fixed-income-debt-payoff-guide",
    "helping-parent-financial-crisis": "sudden-loss-financial-checklist",
    "help-aging-parent-manage-money": "protecting-vulnerable-seniors-money",
    "asset-protection-before-nursing-home": "protecting-vulnerable-seniors-money",
    "medicare-advantage-vs-original": "medicare-advantage-red-flags-checklist",
    "medicare-enrollment-deadlines": "employer-to-medicare-transition-checklist",
    "medicare-extra-help-prescription-savings": "medicare-savings-program-comparison",
    "save-money-medicare-premiums": "medicare-savings-program-comparison",
    "auto-home-insurance-seniors": "vehicle-costs-after-retirement",
    "permission-to-spend-in-retirement": "safe-yield-investments-after-60",
    "tax-deductions-seniors-over-65": "backdoor-roth-after-55",
    "tax-season-savings-seniors": "backdoor-roth-after-55",
    "cut-phone-bill-after-65": "hidden-monthly-drains-retirees",
    "does-medicare-cover-prescriptions": "prescription-savings-comparison",
}


# ── Step 1: Fetch all guides ─────────────────────────────────────────────────
print("Fetching guide articles...")

resp = client.get(
    f"{SUPABASE_URL}/rest/v1/guide_articles",
    headers={
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
    },
    params={
        "select": "id,slug,related_slugs",
        "limit": "500",
    },
)
resp.raise_for_status()
guides = resp.json()

guide_map = {g["slug"]: g for g in guides}
existing_slugs = set(guide_map.keys())
print(f"  Found {len(guides)} guides in database")


# ── Step 2: Compute updates ──────────────────────────────────────────────────
print("Computing reverse link updates...")

updates = []
for source_slug, target_slug in REVERSE_LINKS.items():
    if source_slug not in guide_map:
        print(f"  SKIP {source_slug}: not in database")
        continue

    if target_slug not in existing_slugs:
        print(f"  SKIP {source_slug} -> {target_slug}: target not in database yet")
        continue

    guide = guide_map[source_slug]
    current_related = guide.get("related_slugs") or []
    if isinstance(current_related, str):
        try:
            current_related = json.loads(current_related)
        except (json.JSONDecodeError, TypeError):
            current_related = []

    # Skip if already linked
    if target_slug in current_related:
        print(f"  SKIP {source_slug}: already links to {target_slug}")
        continue

    # Cap at MAX_RELATED
    if len(current_related) >= MAX_RELATED:
        print(
            f"  SKIP {source_slug}: already has {len(current_related)} related slugs (max {MAX_RELATED})"
        )
        continue

    merged = current_related + [target_slug]
    updates.append(
        {
            "slug": source_slug,
            "related_slugs": merged,
            "added": target_slug,
        }
    )

print(f"  {len(updates)} guides need reverse link updates")


# ── Step 3: Apply updates ────────────────────────────────────────────────────
if DRY_RUN:
    print("\n[DRY RUN] Would update:")
    for u in updates:
        print(f"  {u['slug']}: +{u['added']}")
    print("\nRun without --dry-run to apply.")
    sys.exit(0)

print("Applying updates to Supabase...")

updated = 0
failed = 0

for u in updates:
    resp = client.patch(
        f"{SUPABASE_URL}/rest/v1/guide_articles",
        headers=HEADERS,
        params={"slug": f"eq.{u['slug']}"},
        json={"related_slugs": u["related_slugs"]},
    )

    if resp.status_code in (200, 204):
        updated += 1
        print(f"  {u['slug']}: added {u['added']}")
    else:
        failed += 1
        print(f"  {u['slug']}: FAILED - {resp.status_code} {resp.text}")

client.close()

print(f"\nDone: {updated} updated, {failed} failed")
