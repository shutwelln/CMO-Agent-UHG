#!/usr/bin/env python3
"""Analyze the gap between merchants WITH page content vs those WITHOUT.

Compares the 62 merchants with full page content to the ~495 with discounts
but no content, and the remainder with no discount and no content.

Usage:
    python scripts/analyze_merchant_content_gap.py
"""

from __future__ import annotations

import asyncio
import os
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

# ── Load .env ────────────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
}


# ── Supabase helpers ─────────────────────────────────────────────────────────


async def fetch_all(
    http: httpx.AsyncClient,
    table: str,
    params: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Paginated GET from Supabase REST API."""
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    batch = 5000
    while True:
        p = dict(params or {})
        p["limit"] = str(batch)
        p["offset"] = str(offset)
        resp = await http.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            params=p,
        )
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data)
        if len(data) < batch:
            break
        offset += batch
    return all_rows


# ── Analysis ─────────────────────────────────────────────────────────────────


async def main() -> None:
    async with httpx.AsyncClient(timeout=60.0) as http:

        # ── 1. Fetch all active merchants ───────────────────────────────────
        print("Fetching merchants...")
        merchants_raw = await fetch_all(
            http,
            "merchants",
            {
                "select": "id,name,is_national,category_id,default_discount_value,"
                          "default_discount_text,page_slug,page_seo_title,"
                          "page_hero_headline,created_at",
                "is_active": "eq.true",
            },
        )
        print(f"  Total active merchants: {len(merchants_raw)}")

        # ── 2. Fetch category lookup ────────────────────────────────────────
        print("Fetching categories...")
        cats_raw = await fetch_all(http, "merchant_categories", {"select": "id,name,slug"})
        cat_by_id = {c["id"]: c for c in cats_raw}

        # ── 3. Fetch ALL store_locations (active) ───────────────────────────
        print("Fetching store locations...")
        locs_raw = await fetch_all(
            http,
            "store_locations",
            {"select": "merchant_id,location_id", "is_active": "eq.true"},
        )
        loc_counts: Counter = Counter(r["merchant_id"] for r in locs_raw)
        print(f"  Total active store_locations: {len(locs_raw)}")

        # ── 4. Fetch locations_v2 for state info ────────────────────────────
        print("Fetching locations_v2 for state data...")
        locations_v2 = await fetch_all(http, "locations_v2", {"select": "id,state,city"})
        loc_meta = {r["id"]: r for r in locations_v2}

        # Build merchant -> state counter
        merch_states: Dict[int, Counter] = defaultdict(Counter)
        merch_cities: Dict[int, Counter] = defaultdict(Counter)
        for r in locs_raw:
            meta = loc_meta.get(r["location_id"], {})
            state = meta.get("state")
            city = meta.get("city")
            if state:
                merch_states[r["merchant_id"]][state] += 1
            if city:
                merch_cities[r["merchant_id"]][city] += 1

    # ── Classify merchants into 3 groups ────────────────────────────────────
    with_content = []
    with_discount_no_content = []
    no_discount_no_content = []

    for m in merchants_raw:
        has_content = bool(
            m.get("page_hero_headline") and m["page_hero_headline"].strip()
        )
        has_discount = bool(
            m.get("default_discount_value") and str(m["default_discount_value"]).strip()
        )

        m["_loc_count"] = loc_counts.get(m["id"], 0)
        m["_cat_name"] = cat_by_id.get(m.get("category_id"), {}).get("name", "Unknown")
        m["_cat_slug"] = cat_by_id.get(m.get("category_id"), {}).get("slug", "unknown")
        m["_states"] = merch_states.get(m["id"], Counter())
        m["_state_count"] = len(m["_states"])
        m["_top_states"] = [s for s, _ in m["_states"].most_common(3)]

        if has_content:
            with_content.append(m)
        elif has_discount:
            with_discount_no_content.append(m)
        else:
            no_discount_no_content.append(m)

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 1: The 62 with full page content
    # ═══════════════════════════════════════════════════════════════════════
    with_content.sort(key=lambda x: x["_loc_count"], reverse=True)

    print("\n" + "=" * 100)
    print(f"GROUP 1: MERCHANTS WITH FULL PAGE CONTENT ({len(with_content)} merchants)")
    print("=" * 100)
    print(
        f"{'#':<4} {'Name':<35} {'National?':<10} {'Category':<22} "
        f"{'Discount':<15} {'Locations':<10} {'States':<8}"
    )
    print("-" * 100)
    for i, m in enumerate(with_content, 1):
        discount_display = str(m.get("default_discount_value", ""))[:13]
        print(
            f"{i:<4} {m['name'][:34]:<35} "
            f"{'Yes' if m.get('is_national') else 'No':<10} "
            f"{m['_cat_name'][:21]:<22} "
            f"{discount_display:<15} "
            f"{m['_loc_count']:<10} "
            f"{m['_state_count']:<8}"
        )

    # Analysis of Group 1
    g1_national = sum(1 for m in with_content if m.get("is_national"))
    g1_local = len(with_content) - g1_national
    g1_locs = [m["_loc_count"] for m in with_content]
    g1_cats = Counter(m["_cat_name"] for m in with_content)

    print(f"\n--- Group 1 Analysis ---")
    print(f"  National: {g1_national} ({g1_national/len(with_content)*100:.1f}%)")
    print(f"  Local:    {g1_local} ({g1_local/len(with_content)*100:.1f}%)")
    print(f"\n  Store location counts:")
    print(f"    Total:   {sum(g1_locs):,}")
    print(f"    Mean:    {statistics.mean(g1_locs):,.1f}")
    print(f"    Median:  {statistics.median(g1_locs):,.1f}")
    print(f"    Min:     {min(g1_locs):,}")
    print(f"    Max:     {max(g1_locs):,}")
    print(f"\n  Categories:")
    for cat, cnt in g1_cats.most_common():
        print(f"    {cat:<25} {cnt:>3}")

    g1_discounts = [
        m.get("default_discount_value", "")
        for m in with_content
        if m.get("default_discount_value")
    ]
    disc_counter = Counter(g1_discounts)
    print(f"\n  Discount value distribution:")
    for dv, cnt in disc_counter.most_common(15):
        print(f"    {str(dv):<20} {cnt:>3}")

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 2: Merchants with discounts but NO content
    # ═══════════════════════════════════════════════════════════════════════
    with_discount_no_content.sort(key=lambda x: x["_loc_count"], reverse=True)

    print("\n" + "=" * 100)
    print(
        f"GROUP 2: MERCHANTS WITH DISCOUNTS BUT NO CONTENT "
        f"({len(with_discount_no_content)} merchants)"
    )
    print("=" * 100)

    g2_national = sum(1 for m in with_discount_no_content if m.get("is_national"))
    g2_local = len(with_discount_no_content) - g2_national
    g2_locs = [m["_loc_count"] for m in with_discount_no_content]
    g2_cats = Counter(m["_cat_name"] for m in with_discount_no_content)

    print(f"\n--- Group 2 Analysis ---")
    print(f"  National: {g2_national} ({g2_national/len(with_discount_no_content)*100:.1f}%)")
    print(f"  Local:    {g2_local} ({g2_local/len(with_discount_no_content)*100:.1f}%)")

    if g2_locs:
        print(f"\n  Store location counts:")
        print(f"    Total:   {sum(g2_locs):,}")
        print(f"    Mean:    {statistics.mean(g2_locs):,.1f}")
        print(f"    Median:  {statistics.median(g2_locs):,.1f}")
        print(f"    Min:     {min(g2_locs):,}")
        print(f"    Max:     {max(g2_locs):,}")

    # Location distribution buckets
    print(f"\n  Location distribution:")
    buckets = [
        (">100 locations", lambda x: x > 100),
        ("51-100 locations", lambda x: 51 <= x <= 100),
        ("11-50 locations", lambda x: 11 <= x <= 50),
        ("6-10 locations", lambda x: 6 <= x <= 10),
        ("2-5 locations", lambda x: 2 <= x <= 5),
        ("1 location", lambda x: x == 1),
        ("0 locations", lambda x: x == 0),
    ]
    for label, fn in buckets:
        cnt = sum(1 for lc in g2_locs if fn(lc))
        total_locs_in_bucket = sum(lc for lc in g2_locs if fn(lc))
        print(f"    {label:<20} {cnt:>4} merchants   ({total_locs_in_bucket:>7,} locations)")

    print(f"\n  Categories:")
    for cat, cnt in g2_cats.most_common():
        print(f"    {cat:<25} {cnt:>3}")

    g2_discounts = [
        m.get("default_discount_value", "")
        for m in with_discount_no_content
        if m.get("default_discount_value")
    ]
    g2_disc_counter = Counter(g2_discounts)
    print(f"\n  Discount value distribution:")
    for dv, cnt in g2_disc_counter.most_common(20):
        print(f"    {str(dv):<20} {cnt:>3}")

    # Top 20 by store location count (highest impact opportunities)
    print(f"\n  --- TOP 20 BY STORE LOCATIONS (Highest Impact) ---")
    print(
        f"  {'#':<4} {'Name':<35} {'National?':<10} {'Category':<22} "
        f"{'Discount':<15} {'Locations':<10} {'States':<8}"
    )
    print("  " + "-" * 98)
    for i, m in enumerate(with_discount_no_content[:20], 1):
        discount_display = str(m.get("default_discount_value", ""))[:13]
        print(
            f"  {i:<4} {m['name'][:34]:<35} "
            f"{'Yes' if m.get('is_national') else 'No':<10} "
            f"{m['_cat_name'][:21]:<22} "
            f"{discount_display:<15} "
            f"{m['_loc_count']:<10} "
            f"{m['_state_count']:<8}"
        )

    # ── Las Vegas / Nevada analysis ─────────────────────────────────────
    print(f"\n  --- LAS VEGAS / NEVADA LOCAL MERCHANTS ---")
    lv_merchants = []
    for m in with_discount_no_content:
        states = m["_states"]
        if not states:
            continue
        # All locations in Nevada?
        total_locs_for_m = sum(states.values())
        nv_locs = states.get("NV", 0) + states.get("Nevada", 0)
        if total_locs_for_m > 0 and nv_locs / total_locs_for_m >= 0.8:
            lv_merchants.append(m)

    print(f"  Merchants with 80%+ locations in Nevada: {len(lv_merchants)}")
    if lv_merchants:
        lv_merchants.sort(key=lambda x: x["_loc_count"], reverse=True)
        for m in lv_merchants[:30]:
            print(
                f"    {m['name'][:35]:<36} "
                f"locs={m['_loc_count']:<5} "
                f"NV={m['_states'].get('NV', 0) + m['_states'].get('Nevada', 0)}"
            )

    # ═══════════════════════════════════════════════════════════════════════
    # GROUP 3: No discount AND no content
    # ═══════════════════════════════════════════════════════════════════════
    no_discount_no_content.sort(key=lambda x: x["_loc_count"], reverse=True)

    print("\n" + "=" * 100)
    print(
        f"GROUP 3: NO DISCOUNT AND NO CONTENT "
        f"({len(no_discount_no_content)} merchants)"
    )
    print("=" * 100)

    g3_national = sum(1 for m in no_discount_no_content if m.get("is_national"))
    g3_local = len(no_discount_no_content) - g3_national
    g3_locs = [m["_loc_count"] for m in no_discount_no_content]

    print(f"\n--- Group 3 Analysis ---")
    print(f"  National: {g3_national} ({g3_national/len(no_discount_no_content)*100:.1f}% )")
    print(f"  Local:    {g3_local} ({g3_local/len(no_discount_no_content)*100:.1f}%)")

    if g3_locs:
        print(f"\n  Store location counts:")
        print(f"    Total:   {sum(g3_locs):,}")
        print(f"    Mean:    {statistics.mean(g3_locs):,.1f}")
        print(f"    Median:  {statistics.median(g3_locs):,.1f}")
        if g3_locs:
            print(f"    Min:     {min(g3_locs):,}")
            print(f"    Max:     {max(g3_locs):,}")

    print(f"\n  Location distribution:")
    for label, fn in buckets:
        cnt = sum(1 for lc in g3_locs if fn(lc))
        total_locs_in_bucket = sum(lc for lc in g3_locs if fn(lc))
        print(f"    {label:<20} {cnt:>4} merchants   ({total_locs_in_bucket:>7,} locations)")

    # ═══════════════════════════════════════════════════════════════════════
    # SEO / TRAFFIC POTENTIAL SUMMARY
    # ═══════════════════════════════════════════════════════════════════════
    total_g1_locs = sum(g1_locs)
    total_g2_locs = sum(g2_locs) if g2_locs else 0
    total_g3_locs = sum(g3_locs) if g3_locs else 0

    print("\n" + "=" * 100)
    print("SEO / TRAFFIC POTENTIAL SUMMARY")
    print("=" * 100)
    print(f"""
  Current state:
    Group 1 (has content):         {len(with_content):>5} merchants   {total_g1_locs:>8,} store locations covered
    Group 2 (discount, no content):{len(with_discount_no_content):>5} merchants   {total_g2_locs:>8,} store locations uncovered
    Group 3 (no discount/content): {len(no_discount_no_content):>5} merchants   {total_g3_locs:>8,} store locations uncovered

  If we generate content for Group 2:
    Incremental merchants:         +{len(with_discount_no_content)} pages
    Incremental store locations:   +{total_g2_locs:,} location pages addressable
    Total with content:            {len(with_content) + len(with_discount_no_content)} merchants ({total_g1_locs + total_g2_locs:,} locations)
    Coverage increase:             {(len(with_content)+len(with_discount_no_content))/(len(with_content))*100 - 100:.0f}% more merchant pages
    """)

    # ── Prioritized tiers for Group 2 ──────────────────────────────────
    print("  RECOMMENDED CONTENT GENERATION TIERS (Group 2):")
    print()

    tier1 = [m for m in with_discount_no_content if m["_loc_count"] >= 100]
    tier2 = [m for m in with_discount_no_content if 50 <= m["_loc_count"] < 100]
    tier3 = [m for m in with_discount_no_content if 10 <= m["_loc_count"] < 50]
    tier4 = [m for m in with_discount_no_content if 1 <= m["_loc_count"] < 10]
    tier5 = [m for m in with_discount_no_content if m["_loc_count"] == 0]

    tiers = [
        ("Tier 1: 100+ locations (immediate)", tier1),
        ("Tier 2: 50-99 locations (high value)", tier2),
        ("Tier 3: 10-49 locations (medium value)", tier3),
        ("Tier 4: 1-9 locations (low value / local)", tier4),
        ("Tier 5: 0 locations (data quality issue)", tier5),
    ]

    for label, tier in tiers:
        tier_locs = sum(m["_loc_count"] for m in tier)
        national_in_tier = sum(1 for m in tier if m.get("is_national"))
        print(
            f"    {label:<45} "
            f"{len(tier):>4} merchants   "
            f"{tier_locs:>7,} locations   "
            f"({national_in_tier} national)"
        )

    # ── Quick cost estimate ─────────────────────────────────────────────
    print(f"""
  Cost estimate (Claude Haiku at ~$0.002/page):
    Tier 1 ({len(tier1)} merchants):      ~${len(tier1) * 0.002:.2f}
    Tier 2 ({len(tier2)} merchants):      ~${len(tier2) * 0.002:.2f}
    Tier 3 ({len(tier3)} merchants):     ~${len(tier3) * 0.002:.2f}
    Tier 4 ({len(tier4)} merchants):     ~${len(tier4) * 0.002:.2f}
    All Group 2 ({len(with_discount_no_content)} merchants): ~${len(with_discount_no_content) * 0.002:.2f}
    """)

    # ── Tier 1 detail ──────────────────────────────────────────────────
    if tier1:
        print(f"\n  --- TIER 1 DETAIL: 100+ Locations ({len(tier1)} merchants) ---")
        print(
            f"  {'#':<4} {'Name':<35} {'National?':<10} {'Category':<22} "
            f"{'Discount':<15} {'Locations':<10} {'States':<8}"
        )
        print("  " + "-" * 98)
        for i, m in enumerate(tier1, 1):
            discount_display = str(m.get("default_discount_value", ""))[:13]
            print(
                f"  {i:<4} {m['name'][:34]:<35} "
                f"{'Yes' if m.get('is_national') else 'No':<10} "
                f"{m['_cat_name'][:21]:<22} "
                f"{discount_display:<15} "
                f"{m['_loc_count']:<10} "
                f"{m['_state_count']:<8}"
            )

    # ── Tier 2 detail ──────────────────────────────────────────────────
    if tier2:
        print(f"\n  --- TIER 2 DETAIL: 50-99 Locations ({len(tier2)} merchants) ---")
        print(
            f"  {'#':<4} {'Name':<35} {'National?':<10} {'Category':<22} "
            f"{'Discount':<15} {'Locations':<10} {'States':<8}"
        )
        print("  " + "-" * 98)
        for i, m in enumerate(tier2, 1):
            discount_display = str(m.get("default_discount_value", ""))[:13]
            print(
                f"  {i:<4} {m['name'][:34]:<35} "
                f"{'Yes' if m.get('is_national') else 'No':<10} "
                f"{m['_cat_name'][:21]:<22} "
                f"{discount_display:<15} "
                f"{m['_loc_count']:<10} "
                f"{m['_state_count']:<8}"
            )


if __name__ == "__main__":
    asyncio.run(main())
