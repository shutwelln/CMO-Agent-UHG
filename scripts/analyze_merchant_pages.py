"""Analyze merchant page content coverage in Supabase.

Fetches all active merchants and reports:
- Content completeness distribution (0/8 through 8/8 fields filled)
- National vs local breakdown
- Category coverage
- Field-level fill rates
- High-priority merchants (have discount but no content)
"""
from __future__ import annotations

import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "count=exact",
}

SELECT_FIELDS = (
    "id,name,is_national,category_id,"
    "page_status,page_slug,"
    "page_hero_headline,page_hero_subhead,"
    "page_about_md,page_how_to_save_md,page_tips_md,"
    "page_faq_md,page_faq_json,"
    "page_seo_title,page_seo_description,"
    "page_direct_answer,"
    "page_related_protection_slugs,page_related_guide_slugs,page_related_merchant_ids,"
    "default_discount_value,default_discount_text"
)

CORE_FIELDS = [
    "page_hero_headline",
    "page_hero_subhead",
    "page_about_md",
    "page_how_to_save_md",
    "page_tips_md",
    "page_faq",       # special: faq_md OR faq_json
    "page_seo_title",
    "page_seo_description",
]

BONUS_FIELDS = [
    "page_direct_answer",
    "page_related_protection_slugs",
    "page_related_guide_slugs",
    "page_related_merchant_ids",
]


def is_filled(value) -> bool:
    """Check if a field value is non-null and non-empty."""
    if value is None:
        return False
    if isinstance(value, str) and value.strip() == "":
        return False
    if isinstance(value, list) and len(value) == 0:
        return False
    if isinstance(value, dict) and len(value) == 0:
        return False
    return True


def count_core_fields(m: dict) -> int:
    """Count how many of the 8 core content fields are populated."""
    count = 0
    for f in ["page_hero_headline", "page_hero_subhead", "page_about_md",
              "page_how_to_save_md", "page_tips_md",
              "page_seo_title", "page_seo_description"]:
        if is_filled(m.get(f)):
            count += 1
    # FAQ: either page_faq_md or page_faq_json counts
    if is_filled(m.get("page_faq_md")) or is_filled(m.get("page_faq_json")):
        count += 1
    return count


def field_filled(m: dict, field: str) -> bool:
    """Check if a specific core field is filled."""
    if field == "page_faq":
        return is_filled(m.get("page_faq_md")) or is_filled(m.get("page_faq_json"))
    return is_filled(m.get(field))


def fetch_all_merchants() -> list[dict]:
    """Fetch all active merchants with pagination (1000 per page)."""
    merchants = []
    offset = 0
    limit = 1000

    with httpx.Client(timeout=30) as client:
        while True:
            url = (
                f"{SUPABASE_URL}/rest/v1/merchants"
                f"?is_active=eq.true"
                f"&select={SELECT_FIELDS}"
                f"&order=id"
                f"&offset={offset}"
                f"&limit={limit}"
            )
            resp = client.get(url, headers=HEADERS)
            resp.raise_for_status()

            batch = resp.json()
            if not batch:
                break
            merchants.extend(batch)

            # Check Content-Range header for total
            content_range = resp.headers.get("content-range", "")
            if content_range:
                # Format: "0-999/3456"
                parts = content_range.split("/")
                if len(parts) == 2 and parts[1] != "*":
                    total = int(parts[1])
                    if offset + limit >= total:
                        break

            if len(batch) < limit:
                break
            offset += limit

    return merchants


def fetch_categories() -> dict[int, str]:
    """Fetch category id->name mapping."""
    with httpx.Client(timeout=30) as client:
        url = f"{SUPABASE_URL}/rest/v1/merchant_categories?select=id,name&order=id"
        resp = client.get(url, headers=HEADERS)
        resp.raise_for_status()
        return {c["id"]: c["name"] for c in resp.json()}


def main():
    print("=" * 80)
    print("SAVERWELL MERCHANT PAGE CONTENT ANALYSIS")
    print("=" * 80)
    print()

    # Fetch data
    print("Fetching active merchants from Supabase...")
    merchants = fetch_all_merchants()
    print(f"  Total active merchants: {len(merchants)}")

    print("Fetching categories...")
    categories = fetch_categories()
    print(f"  Categories found: {len(categories)}")
    print()

    # ---------------------------------------------------------------
    # 1. Content completeness distribution
    # ---------------------------------------------------------------
    tier_merchants = defaultdict(list)  # score -> [merchant_names]
    for m in merchants:
        score = count_core_fields(m)
        tier_merchants[score].append(m)

    print("-" * 80)
    print("1. CONTENT COMPLETENESS DISTRIBUTION (0-8 core fields filled)")
    print("-" * 80)
    for score in range(9):
        group = tier_merchants[score]
        pct = len(group) / len(merchants) * 100 if merchants else 0
        bar = "#" * int(pct / 2)
        print(f"  {score}/8: {len(group):>5} merchants ({pct:5.1f}%)  {bar}")
        if group:
            examples = sorted(group, key=lambda x: x["name"])[:5]
            names = ", ".join(e["name"] for e in examples)
            print(f"        Examples: {names}")
    print()

    # Summary buckets
    zero = len(tier_merchants[0])
    partial = sum(len(tier_merchants[s]) for s in range(1, 8))
    full = len(tier_merchants[8])
    print(f"  Summary:")
    print(f"    Zero content (0/8):    {zero:>5} ({zero/len(merchants)*100:.1f}%)")
    print(f"    Partial (1-7/8):       {partial:>5} ({partial/len(merchants)*100:.1f}%)")
    print(f"    Full content (8/8):    {full:>5} ({full/len(merchants)*100:.1f}%)")
    print()

    # ---------------------------------------------------------------
    # 2. National vs Local breakdown
    # ---------------------------------------------------------------
    print("-" * 80)
    print("2. NATIONAL vs LOCAL MERCHANTS")
    print("-" * 80)
    national = [m for m in merchants if m.get("is_national")]
    local = [m for m in merchants if not m.get("is_national")]

    for label, group in [("National", national), ("Local", local)]:
        scores = [count_core_fields(m) for m in group]
        full_c = sum(1 for s in scores if s == 8)
        partial_c = sum(1 for s in scores if 1 <= s <= 7)
        zero_c = sum(1 for s in scores if s == 0)
        print(f"  {label}: {len(group)} merchants")
        print(f"    Full (8/8):    {full_c:>5} ({full_c/len(group)*100:.1f}%)" if group else "")
        print(f"    Partial (1-7): {partial_c:>5} ({partial_c/len(group)*100:.1f}%)" if group else "")
        print(f"    Zero (0/8):    {zero_c:>5} ({zero_c/len(group)*100:.1f}%)" if group else "")
        if group:
            avg = sum(scores) / len(scores)
            print(f"    Average score: {avg:.1f}/8")
        print()

    # National merchants with zero content
    national_zero = [m for m in national if count_core_fields(m) == 0]
    if national_zero:
        print(f"  National merchants with ZERO content ({len(national_zero)}):")
        for m in sorted(national_zero, key=lambda x: x["name"])[:20]:
            disc = m.get("default_discount_value") or "no discount"
            print(f"    - {m['name']} (discount: {disc})")
        if len(national_zero) > 20:
            print(f"    ... and {len(national_zero) - 20} more")
    print()

    # ---------------------------------------------------------------
    # 3. Category coverage
    # ---------------------------------------------------------------
    print("-" * 80)
    print("3. CATEGORY COVERAGE")
    print("-" * 80)
    cat_stats = defaultdict(lambda: {"total": 0, "full": 0, "partial": 0, "zero": 0, "avg": 0.0, "scores": []})
    for m in merchants:
        cid = m.get("category_id")
        score = count_core_fields(m)
        cat_stats[cid]["total"] += 1
        cat_stats[cid]["scores"].append(score)
        if score == 8:
            cat_stats[cid]["full"] += 1
        elif score >= 1:
            cat_stats[cid]["partial"] += 1
        else:
            cat_stats[cid]["zero"] += 1

    # Sort by total merchants descending
    sorted_cats = sorted(cat_stats.items(), key=lambda x: x[1]["total"], reverse=True)

    print(f"  {'Category':<35} {'Total':>6} {'Full':>6} {'Partial':>8} {'Zero':>6} {'Avg':>5}")
    print(f"  {'-'*35} {'-'*6} {'-'*6} {'-'*8} {'-'*6} {'-'*5}")
    for cid, stats in sorted_cats:
        cat_name = categories.get(cid, f"Unknown ({cid})") if cid else "No category"
        avg = sum(stats["scores"]) / len(stats["scores"]) if stats["scores"] else 0
        print(
            f"  {cat_name:<35} {stats['total']:>6} {stats['full']:>6} "
            f"{stats['partial']:>8} {stats['zero']:>6} {avg:>5.1f}"
        )
    print()

    # ---------------------------------------------------------------
    # 4. Field-level fill rates
    # ---------------------------------------------------------------
    print("-" * 80)
    print("4. FIELD-LEVEL FILL RATES")
    print("-" * 80)
    total = len(merchants)
    field_labels = [
        ("page_hero_headline", "Hero Headline"),
        ("page_hero_subhead", "Hero Subhead"),
        ("page_about_md", "About (Markdown)"),
        ("page_how_to_save_md", "How to Save (Markdown)"),
        ("page_tips_md", "Tips (Markdown)"),
        ("page_faq", "FAQ (md or json)"),
        ("page_seo_title", "SEO Title"),
        ("page_seo_description", "SEO Description"),
    ]
    print(f"\n  Core fields (count toward 8/8 score):")
    for field, label in field_labels:
        filled = sum(1 for m in merchants if field_filled(m, field))
        pct = filled / total * 100 if total else 0
        bar = "#" * int(pct / 2)
        print(f"    {label:<30} {filled:>5}/{total} ({pct:5.1f}%)  {bar}")

    print(f"\n  Bonus fields (not in 8/8 score):")
    for field in BONUS_FIELDS:
        filled = sum(1 for m in merchants if is_filled(m.get(field)))
        pct = filled / total * 100 if total else 0
        bar = "#" * int(pct / 2)
        label = field.replace("page_", "").replace("_", " ").title()
        print(f"    {label:<30} {filled:>5}/{total} ({pct:5.1f}%)  {bar}")

    # Also check page_slug and page_status
    print(f"\n  Infrastructure fields:")
    for field, label in [("page_slug", "Page Slug"), ("page_status", "Page Status")]:
        filled = sum(1 for m in merchants if is_filled(m.get(field)))
        pct = filled / total * 100 if total else 0
        print(f"    {label:<30} {filled:>5}/{total} ({pct:5.1f}%)")

    # page_status distribution
    status_counts = Counter(m.get("page_status") for m in merchants)
    print(f"\n  Page status distribution:")
    for status, count in status_counts.most_common():
        print(f"    {str(status):<20} {count:>5} ({count/total*100:.1f}%)")
    print()

    # ---------------------------------------------------------------
    # 5. Discount set but no content (highest priority)
    # ---------------------------------------------------------------
    print("-" * 80)
    print("5. HIGH PRIORITY: Merchants WITH discount but WITHOUT content")
    print("-" * 80)
    has_discount_no_content = [
        m for m in merchants
        if is_filled(m.get("default_discount_value"))
        and count_core_fields(m) == 0
    ]
    has_discount_partial = [
        m for m in merchants
        if is_filled(m.get("default_discount_value"))
        and 1 <= count_core_fields(m) <= 7
    ]
    has_discount_full = [
        m for m in merchants
        if is_filled(m.get("default_discount_value"))
        and count_core_fields(m) == 8
    ]
    no_discount = [
        m for m in merchants
        if not is_filled(m.get("default_discount_value"))
    ]

    total_with_discount = sum(1 for m in merchants if is_filled(m.get("default_discount_value")))
    print(f"  Total merchants with discount set:    {total_with_discount}")
    print(f"  Total merchants without discount:     {len(no_discount)}")
    print()
    print(f"  WITH discount + full content (8/8):   {len(has_discount_full)}")
    print(f"  WITH discount + partial (1-7/8):      {len(has_discount_partial)}")
    print(f"  WITH discount + ZERO content (0/8):   {len(has_discount_no_content)}  <-- PRIORITY")
    print()

    # Break down discount-no-content by national/local
    nat_disc_zero = [m for m in has_discount_no_content if m.get("is_national")]
    loc_disc_zero = [m for m in has_discount_no_content if not m.get("is_national")]
    print(f"  Of the {len(has_discount_no_content)} discount+zero-content merchants:")
    print(f"    National: {len(nat_disc_zero)}")
    print(f"    Local:    {len(loc_disc_zero)}")
    print()

    if nat_disc_zero:
        print(f"  NATIONAL merchants with discount + zero content ({len(nat_disc_zero)}):")
        for m in sorted(nat_disc_zero, key=lambda x: x["name"])[:30]:
            disc_val = m.get("default_discount_value", "?")
            disc_txt = m.get("default_discount_text", "")
            cat_name = categories.get(m.get("category_id"), "?")
            print(f"    - {m['name']:<40} discount: {disc_val}  ({disc_txt})  cat: {cat_name}")
        if len(nat_disc_zero) > 30:
            print(f"    ... and {len(nat_disc_zero) - 30} more")
    print()

    # ---------------------------------------------------------------
    # 6. Content generation priority tiers
    # ---------------------------------------------------------------
    print("-" * 80)
    print("6. RECOMMENDED PRIORITY TIERS FOR CONTENT GENERATION")
    print("-" * 80)

    # Tier 1: National + discount + zero content
    t1 = [m for m in merchants if m.get("is_national") and is_filled(m.get("default_discount_value")) and count_core_fields(m) == 0]
    # Tier 2: National + discount + partial content
    t2 = [m for m in merchants if m.get("is_national") and is_filled(m.get("default_discount_value")) and 1 <= count_core_fields(m) <= 7]
    # Tier 3: National + no discount + zero content
    t3 = [m for m in merchants if m.get("is_national") and not is_filled(m.get("default_discount_value")) and count_core_fields(m) == 0]
    # Tier 4: Local + discount + zero content
    t4 = [m for m in merchants if not m.get("is_national") and is_filled(m.get("default_discount_value")) and count_core_fields(m) == 0]
    # Tier 5: Local + discount + partial content
    t5 = [m for m in merchants if not m.get("is_national") and is_filled(m.get("default_discount_value")) and 1 <= count_core_fields(m) <= 7]
    # Tier 6: National + no discount + partial
    t6 = [m for m in merchants if m.get("is_national") and not is_filled(m.get("default_discount_value")) and 1 <= count_core_fields(m) <= 7]
    # Tier 7: Local + no discount + zero
    t7 = [m for m in merchants if not m.get("is_national") and not is_filled(m.get("default_discount_value")) and count_core_fields(m) == 0]

    tiers = [
        ("P1", "National + discount + zero content", t1),
        ("P2", "National + discount + partial content (1-7/8)", t2),
        ("P3", "National + no discount + zero content", t3),
        ("P4", "Local + discount + zero content", t4),
        ("P5", "Local + discount + partial content (1-7/8)", t5),
        ("P6", "National + no discount + partial content", t6),
        ("P7", "Local + no discount + zero content", t7),
    ]

    total_needing_work = 0
    for code, desc, group in tiers:
        total_needing_work += len(group)
        print(f"\n  {code}: {desc}")
        print(f"       Count: {len(group)}")
        if group:
            examples = sorted(group, key=lambda x: x["name"])[:5]
            names = ", ".join(e["name"] for e in examples)
            print(f"       Examples: {names}")

    print(f"\n  Already complete (8/8): {full}")
    print(f"  Total needing work:    {total_needing_work}")
    print()

    # ---------------------------------------------------------------
    # 7. Quick-win analysis: merchants close to completion
    # ---------------------------------------------------------------
    print("-" * 80)
    print("7. QUICK WINS: Merchants at 7/8 (need just 1 more field)")
    print("-" * 80)
    nearly_done = tier_merchants[7]
    if nearly_done:
        # Which field is missing for each?
        missing_field_counts = Counter()
        for m in nearly_done:
            for field, label in field_labels:
                if not field_filled(m, field):
                    missing_field_counts[label] += 1

        print(f"  {len(nearly_done)} merchants are at 7/8. Missing field breakdown:")
        for field_name, count in missing_field_counts.most_common():
            print(f"    {field_name:<30} missing in {count} merchants")
        print()
        print(f"  Sample 7/8 merchants:")
        for m in sorted(nearly_done, key=lambda x: x["name"])[:10]:
            missing = []
            for field, label in field_labels:
                if not field_filled(m, field):
                    missing.append(label)
            print(f"    - {m['name']:<35} missing: {', '.join(missing)}")
    else:
        print("  None at 7/8.")
    print()

    # ---------------------------------------------------------------
    # 8. Merchants at 6/8 (need 2 more fields)
    # ---------------------------------------------------------------
    print("-" * 80)
    print("8. NEAR WINS: Merchants at 6/8 (need 2 more fields)")
    print("-" * 80)
    almost_done = tier_merchants[6]
    if almost_done:
        missing_field_counts = Counter()
        for m in almost_done:
            for field, label in field_labels:
                if not field_filled(m, field):
                    missing_field_counts[label] += 1

        print(f"  {len(almost_done)} merchants are at 6/8. Missing field breakdown:")
        for field_name, count in missing_field_counts.most_common():
            print(f"    {field_name:<30} missing in {count} merchants")
        print()
        print(f"  Sample 6/8 merchants:")
        for m in sorted(almost_done, key=lambda x: x["name"])[:10]:
            missing = []
            for field, label in field_labels:
                if not field_filled(m, field):
                    missing.append(label)
            nat = "NATIONAL" if m.get("is_national") else "local"
            print(f"    - {m['name']:<35} [{nat}] missing: {', '.join(missing)}")
    else:
        print("  None at 6/8.")
    print()

    # ---------------------------------------------------------------
    # 9. Default discount text patterns
    # ---------------------------------------------------------------
    print("-" * 80)
    print("9. DISCOUNT VALUE DISTRIBUTION (merchants with discount set)")
    print("-" * 80)
    discount_vals = Counter()
    for m in merchants:
        dv = m.get("default_discount_value")
        if is_filled(dv):
            discount_vals[dv] += 1
    print(f"  Top 20 discount values:")
    for val, count in discount_vals.most_common(20):
        print(f"    {str(val):<20} {count:>5} merchants")
    print()

    print("=" * 80)
    print("END OF ANALYSIS")
    print("=" * 80)


if __name__ == "__main__":
    main()
