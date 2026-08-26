"""Migrate guide categories: 7 -> 6 balanced categories.

Splits Finance (39 articles) into Retirement & Taxes, Saving Money, and Caregiving.
Merges Medical Alerts + Phones + Hearing Aids into Senior Products.
Moves does-medicare-cover-hearing-aids from Medicare to Senior Products.

Usage:
  python scripts/migrate_guide_categories.py [--dry-run]
"""

import json
import os
import re
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
    "Prefer": "return=representation",
}

DRY_RUN = "--dry-run" in sys.argv
ROLLBACK_PATH = project_root / "data" / "saverwell" / "category_migration_rollback.json"

client = httpx.Client(timeout=30)

# ── New category definitions ─────────────────────────────────────────────────

NEW_CATEGORIES = [
    {
        "slug": "retirement-taxes",
        "name": "Retirement & Taxes",
        "description": "Social Security, pensions, tax strategy, and retirement planning",
        "sort_order": 3,
    },
    {
        "slug": "saving-money",
        "name": "Saving Money",
        "description": "Budgeting, debt management, discounts, and everyday savings",
        "sort_order": 4,
    },
    {
        "slug": "caregiving",
        "name": "Caregiving",
        "description": "Supporting aging parents with finances, legal, and end-of-life planning",
        "sort_order": 5,
    },
    {
        "slug": "senior-products",
        "name": "Senior Products",
        "description": "Medical alerts, phones, and hearing aid reviews and comparisons",
        "sort_order": 6,
    },
]

# Sort order updates for kept categories
KEPT_CATEGORY_SORT = {
    "medicare": 1,
    "insurance": 2,
}

# ── Article -> new category slug mapping ─────────────────────────────────────

# Retirement & Taxes
RETIREMENT_TAXES_SLUGS = {
    "when-to-claim-social-security",
    "file-social-security-at-62-or-wait",
    "retirement-finances-reset-guide",
    "12-month-retirement-countdown-checklist",
    "real-cost-of-delaying-retirement",
    "forgotten-pension-recovery-guide",
    "public-employee-retirement-guide",
    "late-career-income-pivot",
    "backdoor-roth-after-55",
    "tax-deductions-seniors-over-65",
    "tax-season-savings-seniors",
    "permission-to-spend-in-retirement",
    "safe-yield-investments-after-60",
    "late-life-marriage-benefits-guide",
    "social-security-emergency-checklist",
    "government-knock-at-your-door-guide",
    "financial-advisor-red-flags",
}

# Saving Money
SAVING_MONEY_SLUGS = {
    "monthly-subscription-audit-retirees",
    "hidden-monthly-drains-retirees",
    "what-seniors-actually-cut-first",
    "why-retirees-quit-budgeting-apps",
    "free-budgeting-tools-retirees",
    "beginner-saver-guide-retirees",
    "dont-pay-it-back-yet-checklist",
    "fixed-income-debt-payoff-guide",
    "auto-debt-after-60",
    "unexpected-cost-survival-playbook",
    "vehicle-costs-after-retirement",
    "senior-scam-protection-complete-guide",
    "how-to-spot-fake-financial-coach",
    "senior-fraud-protection-bundle",
    "aarp-discounts-complete-list",
    "is-aarp-membership-worth-it",
    # Protection articles (scam guides) -> Saving Money
    "ai-voice-cloning-scams",
    "grandparent-scam-how-to-protect",
    "tech-support-scams-seniors",
    "irs-tax-phone-scams",
    "romance-scams-targeting-seniors",
    "investment-scams-targeting-seniors",
    # Discounts articles -> Saving Money
    "restaurant-senior-discounts",
    "grocery-store-senior-discounts",
    "senior-travel-discounts",
}

# Caregiving
CAREGIVING_SLUGS = {
    "difficult-conversations-aging-parents-finances",
    "help-aging-parent-manage-money",
    "helping-parent-financial-crisis",
    "protecting-vulnerable-seniors-money",
    "sudden-loss-financial-checklist",
    "asset-protection-before-nursing-home",
    # From existing caregiving category (ID 10)
    "protect-aging-parents-from-scams",
    "signs-parent-getting-scammed",
    "rep-payee-guide",
    "underwater-car-loan-retirement",
}

# Senior Products (medical-alerts + phones + hearing-aids + 1 from medicare)
SENIOR_PRODUCTS_SLUGS = {
    # Medical Alerts
    "medical-alert-systems-guide",
    "medical-alert-systems-cost",
    "medical-alert-fall-detection",
    "medical-alert-no-monthly-fee",
    "medical-alert-watches",
    "medicare-medical-alert-coverage",
    # Phones
    "cell-phone-plans-seniors",
    "best-flip-phones-seniors",
    "free-phones-seniors",
    "cut-phone-bill-after-65",
    # Hearing Aids
    "save-on-hearing-aids",
    "otc-hearing-aids-under-500",
    "medicare-hearing-aids-coverage",
    # From Medicare
    "does-medicare-cover-hearing-aids",
}

# Old category slugs that will be deleted
OLD_CATEGORY_SLUGS = {
    "medical-alerts",
    "phones",
    "hearing-aids",
    "finance",
    "tools",
    "protection",
    "discounts",
}

# Old category slugs for inline link rewriting
OLD_TO_NEW_CATEGORY = {
    "medical-alerts": "senior-products",
    "phones": "senior-products",
    "hearing-aids": "senior-products",
    "tools": "saving-money",  # fallback
}
# finance articles need per-slug lookup (split 3 ways)
# protection -> saving-money, discounts -> saving-money, caregiving stays

# Text fields to scan for inline links
TEXT_FIELDS = [
    "body_md",
    "email_intro_md",
    "savings_tips_md",
    "watch_out_md",
    "faq_md",
]


def get_new_category_for_slug(slug: str) -> str:
    """Return the new category slug for a given article slug."""
    if slug in RETIREMENT_TAXES_SLUGS:
        return "retirement-taxes"
    if slug in SAVING_MONEY_SLUGS:
        return "saving-money"
    if slug in CAREGIVING_SLUGS:
        return "caregiving"
    if slug in SENIOR_PRODUCTS_SLUGS:
        return "senior-products"
    return ""  # empty means keep current category


def supabase_get(table: str, params: dict) -> list:
    """GET from Supabase REST API."""
    resp = client.get(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS,
        params=params,
    )
    resp.raise_for_status()
    return resp.json()


def supabase_post(table: str, data: dict) -> dict:
    """POST to Supabase REST API."""
    resp = client.post(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS,
        json=data,
    )
    resp.raise_for_status()
    result = resp.json()
    return result[0] if isinstance(result, list) else result


def supabase_patch(table: str, match: dict, data: dict) -> None:
    """PATCH Supabase REST API."""
    resp = client.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers={**HEADERS, "Prefer": "return=minimal"},
        params={k: f"eq.{v}" for k, v in match.items()},
        json=data,
    )
    resp.raise_for_status()


def supabase_delete(table: str, match: dict) -> None:
    """DELETE from Supabase REST API."""
    resp = client.delete(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS,
        params={k: f"eq.{v}" for k, v in match.items()},
    )
    resp.raise_for_status()


def fix_inline_links(text: str, slug_to_new_cat: dict) -> str:
    """Rewrite /guides/{old_cat}/{slug} links to use new category slug."""

    def replacer(m: re.Match) -> str:
        old_cat = m.group(1)
        article_slug = m.group(2)
        # Look up article's new category
        new_cat = slug_to_new_cat.get(article_slug)
        if new_cat:
            return f"/guides/{new_cat}/{article_slug}"
        # If article not in our mapping, try category-level redirect
        fallback = OLD_TO_NEW_CATEGORY.get(old_cat, old_cat)
        return f"/guides/{fallback}/{article_slug}"

    return re.sub(r"/guides/([a-z][a-z0-9-]+)/([a-z0-9-]+)", replacer, text)


def main() -> None:
    if DRY_RUN:
        print("=== DRY RUN MODE (no changes will be made) ===\n")

    # ── Step 1: Fetch current categories ─────────────────────────────────
    print("Step 1: Fetching current categories...")
    categories = supabase_get("guide_categories", {"select": "*", "order": "id"})
    cat_by_slug = {c["slug"]: c for c in categories}
    cat_by_id = {c["id"]: c for c in categories}

    print(f"  Found {len(categories)} categories:")
    for c in categories:
        print(f"    ID {c['id']}: {c['slug']} ({c['name']})")

    # ── Step 2: Insert new categories (skip if slug exists) ──────────────
    print("\nStep 2: Creating new categories...")
    for new_cat in NEW_CATEGORIES:
        if new_cat["slug"] in cat_by_slug:
            print(
                f"  SKIP: '{new_cat['slug']}' already exists (ID {cat_by_slug[new_cat['slug']]['id']})"
            )
            continue
        if DRY_RUN:
            print(f"  [DRY] Would create: {new_cat['slug']} ({new_cat['name']})")
        else:
            result = supabase_post("guide_categories", new_cat)
            print(f"  CREATED: {new_cat['slug']} (ID {result['id']})")
            cat_by_slug[new_cat["slug"]] = result
            cat_by_id[result["id"]] = result

    # ── Step 3: Refresh categories to get final IDs ──────────────────────
    if not DRY_RUN:
        categories = supabase_get("guide_categories", {"select": "*", "order": "id"})
        cat_by_slug = {c["slug"]: c for c in categories}
        cat_by_id = {c["id"]: c for c in categories}

    # ── Step 4: Fetch all articles ───────────────────────────────────────
    print("\nStep 3: Fetching all articles...")
    fields = ["id", "slug", "category_id", "email_cta_url"] + TEXT_FIELDS
    articles = supabase_get(
        "guide_articles",
        {
            "select": ",".join(fields),
            "order": "id",
            "limit": "500",
        },
    )
    print(f"  Found {len(articles)} articles")

    # ── Step 5: Save rollback snapshot ───────────────────────────────────
    print("\nStep 4: Saving rollback snapshot...")
    rollback = {a["slug"]: a["category_id"] for a in articles}
    if DRY_RUN:
        print(f"  [DRY] Would save rollback to {ROLLBACK_PATH}")
    else:
        ROLLBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
        ROLLBACK_PATH.write_text(json.dumps(rollback, indent=2))
        print(f"  Saved {len(rollback)} entries to {ROLLBACK_PATH}")

    # Build slug -> new category slug map (for inline link rewriting)
    slug_to_new_cat: dict[str, str] = {}
    for a in articles:
        new_cat_slug = get_new_category_for_slug(a["slug"])
        if new_cat_slug:
            slug_to_new_cat[a["slug"]] = new_cat_slug
        else:
            # Keep current category slug
            old_cat = cat_by_id.get(a["category_id"])
            if old_cat:
                slug_to_new_cat[a["slug"]] = old_cat["slug"]

    # ── Step 6: Reassign articles ────────────────────────────────────────
    print("\nStep 5: Reassigning articles to new categories...")
    updated = 0
    link_fixes = 0

    for a in articles:
        new_cat_slug = get_new_category_for_slug(a["slug"])
        if not new_cat_slug:
            continue  # stays in current category

        if new_cat_slug not in cat_by_slug:
            print(f"  ERROR: Category '{new_cat_slug}' not found for article '{a['slug']}'")
            continue

        new_cat_id = cat_by_slug[new_cat_slug]["id"]
        old_cat = cat_by_id.get(a["category_id"], {})
        old_cat_slug = old_cat.get("slug", "unknown")

        if a["category_id"] == new_cat_id:
            continue  # already in correct category

        new_cta_url = f"/guides/{new_cat_slug}/{a['slug']}"
        patch_data: dict = {
            "category_id": new_cat_id,
            "email_cta_url": new_cta_url,
        }

        # Fix inline links in text fields
        for field in TEXT_FIELDS:
            text = a.get(field)
            if text and "/guides/" in text:
                fixed = fix_inline_links(text, slug_to_new_cat)
                if fixed != text:
                    patch_data[field] = fixed
                    link_fixes += 1

        if DRY_RUN:
            print(f"  [DRY] {a['slug']}: {old_cat_slug} -> {new_cat_slug}")
        else:
            supabase_patch("guide_articles", {"id": a["id"]}, patch_data)
            print(f"  MOVED: {a['slug']}: {old_cat_slug} -> {new_cat_slug}")
        updated += 1

    print(f"\n  Total reassigned: {updated}")
    print(f"  Inline link fixes: {link_fixes}")

    # ── Step 7: Fix inline links in articles that stay ───────────────────
    print("\nStep 6: Fixing inline links in non-moved articles...")
    stay_fixes = 0
    for a in articles:
        new_cat_slug = get_new_category_for_slug(a["slug"])
        if new_cat_slug:
            continue  # already handled above

        patch_data = {}
        for field in TEXT_FIELDS:
            text = a.get(field)
            if text and "/guides/" in text:
                fixed = fix_inline_links(text, slug_to_new_cat)
                if fixed != text:
                    patch_data[field] = fixed

        if patch_data:
            if DRY_RUN:
                print(f"  [DRY] Fix links in: {a['slug']} ({len(patch_data)} fields)")
            else:
                supabase_patch("guide_articles", {"id": a["id"]}, patch_data)
                print(f"  FIXED links in: {a['slug']} ({len(patch_data)} fields)")
            stay_fixes += 1

    print(f"  Fixed links in {stay_fixes} non-moved articles")

    # ── Step 8: Update sort_order on kept categories ─────────────────────
    print("\nStep 7: Updating sort_order on categories...")
    for slug, sort_order in KEPT_CATEGORY_SORT.items():
        if slug in cat_by_slug:
            if DRY_RUN:
                print(f"  [DRY] {slug}: sort_order -> {sort_order}")
            else:
                supabase_patch(
                    "guide_categories", {"id": cat_by_slug[slug]["id"]}, {"sort_order": sort_order}
                )
                print(f"  UPDATED: {slug}: sort_order -> {sort_order}")

    # ── Step 9: Delete old categories ────────────────────────────────────
    print("\nStep 8: Deleting old categories...")
    for slug in OLD_CATEGORY_SLUGS:
        cat = cat_by_slug.get(slug)
        if not cat:
            print(f"  SKIP: '{slug}' not found")
            continue

        # Safety check: ensure no articles still reference this category
        remaining = supabase_get(
            "guide_articles",
            {
                "select": "id,slug",
                "category_id": f"eq.{cat['id']}",
                "limit": "5",
            },
        )
        if remaining:
            slugs = [r["slug"] for r in remaining]
            print(
                f"  WARNING: '{slug}' (ID {cat['id']}) still has {len(remaining)} articles: {slugs}"
            )
            print(f"  SKIPPING DELETE to avoid orphans")
            continue

        if DRY_RUN:
            print(f"  [DRY] Would delete: {slug} (ID {cat['id']})")
        else:
            supabase_delete("guide_categories", {"id": cat["id"]})
            print(f"  DELETED: {slug} (ID {cat['id']})")

    # ── Step 10: Final verification ──────────────────────────────────────
    print("\nStep 9: Verification...")
    if not DRY_RUN:
        final_cats = supabase_get("guide_categories", {"select": "*", "order": "sort_order"})
        print(f"  Final categories ({len(final_cats)}):")
        for c in final_cats:
            count_resp = supabase_get(
                "guide_articles",
                {
                    "select": "id",
                    "category_id": f"eq.{c['id']}",
                },
            )
            print(f"    {c['sort_order']}. {c['slug']} ({c['name']}): {len(count_resp)} articles")

        # Check for orphans
        all_cat_ids = {c["id"] for c in final_cats}
        all_articles = supabase_get(
            "guide_articles", {"select": "id,slug,category_id", "limit": "500"}
        )
        orphans = [a for a in all_articles if a["category_id"] not in all_cat_ids]
        if orphans:
            print(f"\n  WARNING: {len(orphans)} orphaned articles!")
            for o in orphans:
                print(f"    {o['slug']} (category_id={o['category_id']})")
        else:
            print(f"\n  No orphaned articles. Migration complete!")
    else:
        print("  [DRY] Skipping verification in dry-run mode")

    print("\nDone!")


if __name__ == "__main__":
    main()
