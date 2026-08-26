#!/usr/bin/env python3
"""
Comprehensive Supabase data quality scan.
Checks referential integrity, content quality, and overall statistics
for all tables EXCEPT merchants and discounts_v2 (already cleaned).

Uses correct column names from OpenAPI schema introspection.
"""

import json
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = "https://lmtrgkmgfermqatopkfp.supabase.co"
SUPABASE_KEY = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImxtdHJna21nZmVybXFhdG9wa2ZwIiwi"
    "cm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTc2NTk3NzA1NCwiZXhwIjoyMDgx"
    "NTUzMDU0fQ.R2zvCHiUgfwnp2Q096UPYNurTlPgMHcbAOyBGIS-ozQ"
)

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

PAGE_SIZE = 1000
REQUEST_DELAY = 0.05  # seconds between requests

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

findings: List[Dict[str, Any]] = []


def add_finding(severity: str, category: str, title: str, detail: str,
                count: Optional[int] = None, samples: Optional[List] = None):
    f = {"severity": severity, "category": category, "title": title, "detail": detail}
    if count is not None:
        f["count"] = count
    if samples:
        f["samples"] = samples[:5]
    findings.append(f)


def paginated_get(client: httpx.Client, table: str, select: str = "*",
                  filters: str = "", order: str = "") -> List[Dict]:
    """Fetch all rows from a table with Range-header pagination."""
    all_rows: List[Dict] = []
    offset = 0
    while True:
        url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
        if filters:
            url += f"&{filters}"
        if order:
            url += f"&order={order}"
        h = {**HEADERS, "Range": f"{offset}-{offset + PAGE_SIZE - 1}", "Prefer": "count=exact"}
        resp = client.get(url, headers=h)
        if resp.status_code not in (200, 206):
            print(f"  WARNING: {table} fetch failed at offset {offset}: "
                  f"{resp.status_code} {resp.text[:200]}")
            break
        rows = resp.json()
        if not rows:
            break
        all_rows.extend(rows)
        # Parse content-range to see if there are more
        cr = resp.headers.get("content-range", "")
        # e.g. "0-999/5432"
        if "/" in cr:
            try:
                total = int(cr.split("/")[1].strip())
                if offset + len(rows) >= total:
                    break
            except (ValueError, IndexError):
                pass
        if len(rows) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
        time.sleep(REQUEST_DELAY)
    return all_rows


def get_exact_count(client: httpx.Client, table: str, filters: str = "") -> int:
    """Get exact row count using HEAD with count=exact."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=id"
    if filters:
        url += f"&{filters}"
    h = {**HEADERS, "Prefer": "count=exact", "Range": "0-0"}
    resp = client.head(url, headers=h)
    cr = resp.headers.get("content-range", "")
    if "/" in cr:
        try:
            return int(cr.split("/")[1].strip())
        except (ValueError, IndexError):
            pass
    # Fallback with GET
    h2 = {**HEADERS, "Prefer": "count=exact", "Range": "0-0"}
    resp2 = client.get(url, headers=h2)
    cr2 = resp2.headers.get("content-range", "")
    if "/" in cr2:
        try:
            return int(cr2.split("/")[1].strip())
        except (ValueError, IndexError):
            pass
    return -1


def is_empty(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip() == "":
        return True
    return False


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------

def main():
    print("=" * 80)
    print("SUPABASE DATA QUALITY SCAN")
    print("=" * 80)
    print(f"Target: {SUPABASE_URL}")
    print(f"Scope: All tables (merchants/discounts_v2 included for referential checks)")
    print()

    client = httpx.Client(timeout=60)

    # ------------------------------------------------------------------
    # 0. BASELINE DATA
    # ------------------------------------------------------------------
    print("[0] Loading baseline data...")

    # Active merchant IDs
    print("  Fetching active merchants (id only)...")
    active_merchants_raw = paginated_get(client, "merchants", select="id",
                                          filters="is_active=eq.true")
    active_merchant_ids: Set[int] = {r["id"] for r in active_merchants_raw}
    print(f"    Active merchants: {len(active_merchant_ids)}")

    # ALL merchant IDs
    print("  Fetching all merchants (id only)...")
    all_merchants_raw = paginated_get(client, "merchants", select="id")
    all_merchant_ids: Set[int] = {r["id"] for r in all_merchants_raw}
    print(f"    All merchants: {len(all_merchant_ids)}")

    # All locations_v2 IDs (store_locations.location_id -> locations_v2.id)
    print("  Fetching all locations_v2 (id only)...")
    all_locs_v2 = paginated_get(client, "locations_v2", select="id")
    all_loc_v2_ids: Set[int] = {r["id"] for r in all_locs_v2}
    print(f"    locations_v2: {len(all_loc_v2_ids)}")

    # ------------------------------------------------------------------
    # 1. STORE LOCATIONS: referential integrity + data quality
    # ------------------------------------------------------------------
    print("\n[1] Store locations...")

    print("  Fetching store_locations...")
    store_locs = paginated_get(
        client, "store_locations",
        select="id,merchant_id,location_id,mall_id,store_name,is_active,source,external_store_id"
    )
    print(f"    Total store_locations: {len(store_locs)}")

    # 1a. store_locations -> merchants
    sl_no_merchant = [r for r in store_locs if r.get("merchant_id") is None]
    sl_nonexistent_merchant = [r for r in store_locs
                                if r.get("merchant_id") is not None
                                and r["merchant_id"] not in all_merchant_ids]
    sl_inactive_merchant = [r for r in store_locs
                             if r.get("merchant_id") is not None
                             and r["merchant_id"] in all_merchant_ids
                             and r["merchant_id"] not in active_merchant_ids]

    if sl_no_merchant:
        add_finding("HIGH", "Referential Integrity",
                    "Store locations with NULL merchant_id",
                    f"{len(sl_no_merchant)} store_locations have no merchant_id",
                    count=len(sl_no_merchant),
                    samples=[{"id": r["id"], "store_name": r.get("store_name")} for r in sl_no_merchant])

    if sl_nonexistent_merchant:
        bad_ids = {r["merchant_id"] for r in sl_nonexistent_merchant}
        add_finding("HIGH", "Referential Integrity",
                    "Store locations -> nonexistent merchants",
                    f"{len(sl_nonexistent_merchant)} store_locations reference {len(bad_ids)} merchant IDs not in merchants table",
                    count=len(sl_nonexistent_merchant),
                    samples=[{"id": r["id"], "merchant_id": r["merchant_id"]} for r in sl_nonexistent_merchant])

    if sl_inactive_merchant:
        add_finding("MEDIUM", "Referential Integrity",
                    "Store locations -> inactive merchants",
                    f"{len(sl_inactive_merchant)} store_locations reference merchants with is_active=false",
                    count=len(sl_inactive_merchant),
                    samples=[{"id": r["id"], "merchant_id": r["merchant_id"], "store_name": r.get("store_name")} for r in sl_inactive_merchant])

    if not sl_no_merchant and not sl_nonexistent_merchant:
        add_finding("INFO", "Referential Integrity",
                    "store_locations -> merchants: no broken FK",
                    "All store_locations point to existing merchants.")

    # 1b. store_locations -> locations_v2
    sl_no_location = [r for r in store_locs if r.get("location_id") is None]
    sl_bad_location = [r for r in store_locs
                        if r.get("location_id") is not None
                        and r["location_id"] not in all_loc_v2_ids]

    if sl_no_location:
        add_finding("MEDIUM", "Referential Integrity",
                    "Store locations with NULL location_id",
                    f"{len(sl_no_location)} store_locations have no location_id (no address data linked)",
                    count=len(sl_no_location),
                    samples=[{"id": r["id"], "merchant_id": r.get("merchant_id"), "store_name": r.get("store_name")} for r in sl_no_location])

    if sl_bad_location:
        add_finding("HIGH", "Referential Integrity",
                    "Store locations -> nonexistent locations_v2",
                    f"{len(sl_bad_location)} store_locations reference location_ids not in locations_v2",
                    count=len(sl_bad_location),
                    samples=[{"id": r["id"], "location_id": r["location_id"], "merchant_id": r.get("merchant_id")} for r in sl_bad_location])

    if not sl_no_location and not sl_bad_location:
        add_finding("INFO", "Referential Integrity",
                    "store_locations -> locations_v2: ALL CLEAN",
                    "All store_locations have valid location_id references.")

    # 1c. Duplicate store_locations (same merchant_id + location_id)
    loc_counter = Counter()
    for r in store_locs:
        if r.get("merchant_id") and r.get("location_id"):
            key = (r["merchant_id"], r["location_id"])
            loc_counter[key] += 1
    dupes = {k: v for k, v in loc_counter.items() if v > 1}
    if dupes:
        total_dup_rows = sum(v for v in dupes.values())
        add_finding("MEDIUM", "Store Locations",
                    "Duplicate store_locations (same merchant_id + location_id)",
                    f"{len(dupes)} merchant+location combos appear multiple times ({total_dup_rows} total rows)",
                    count=len(dupes),
                    samples=[{"merchant_id": k[0], "location_id": k[1], "occurrences": v} for k, v in list(dupes.items())[:5]])
    else:
        add_finding("INFO", "Store Locations",
                    "No duplicate store_locations (merchant_id + location_id)",
                    "All merchant+location pairs are unique.")

    # Active vs inactive store_locations
    sl_active = [r for r in store_locs if r.get("is_active")]
    sl_inactive = [r for r in store_locs if not r.get("is_active")]
    add_finding("INFO", "Store Locations",
                "Store locations breakdown",
                f"Total: {len(store_locs)}, Active: {len(sl_active)}, "
                f"Inactive: {len(sl_inactive)}, "
                f"Ratio: {len(sl_active)/max(len(store_locs),1)*100:.1f}% active")

    # ------------------------------------------------------------------
    # 2. LOCATIONS_V2 DATA QUALITY
    # ------------------------------------------------------------------
    print("\n[2] Locations_v2 data quality...")

    print("  Fetching locations_v2 (full data)...")
    locs_v2 = paginated_get(
        client, "locations_v2",
        select="id,name,address1,address2,city,state,zip,latitude,longitude,geocode_source"
    )
    print(f"    Total locations_v2: {len(locs_v2)}")

    lv2_no_city = [r for r in locs_v2 if is_empty(r.get("city"))]
    lv2_no_state = [r for r in locs_v2 if is_empty(r.get("state"))]
    lv2_no_zip = [r for r in locs_v2 if is_empty(r.get("zip"))]
    lv2_no_address = [r for r in locs_v2 if is_empty(r.get("address1"))]
    lv2_no_coords = [r for r in locs_v2
                      if r.get("latitude") is None or r.get("longitude") is None]

    if lv2_no_city:
        add_finding("MEDIUM", "Locations_v2",
                    "Locations with NULL/empty city",
                    f"{len(lv2_no_city)} of {len(locs_v2)} locations_v2 have no city",
                    count=len(lv2_no_city),
                    samples=[{"id": r["id"], "address1": r.get("address1"), "state": r.get("state")} for r in lv2_no_city])

    if lv2_no_state:
        add_finding("MEDIUM", "Locations_v2",
                    "Locations with NULL/empty state",
                    f"{len(lv2_no_state)} locations_v2 have no state",
                    count=len(lv2_no_state),
                    samples=[{"id": r["id"], "city": r.get("city")} for r in lv2_no_state])

    if lv2_no_zip:
        add_finding("LOW", "Locations_v2",
                    "Locations with NULL/empty zip",
                    f"{len(lv2_no_zip)} locations_v2 have no zip",
                    count=len(lv2_no_zip))

    if lv2_no_address:
        add_finding("LOW", "Locations_v2",
                    "Locations with NULL/empty address1",
                    f"{len(lv2_no_address)} locations_v2 have no address1",
                    count=len(lv2_no_address))

    if lv2_no_coords:
        pct = len(lv2_no_coords) / max(len(locs_v2), 1) * 100
        sev = "MEDIUM" if pct > 10 else "LOW"
        add_finding(sev, "Locations_v2",
                    "Locations with NULL coordinates",
                    f"{len(lv2_no_coords)} ({pct:.1f}%) locations_v2 have no lat/lng",
                    count=len(lv2_no_coords))

    # Duplicate locations (same address1 + city + state + zip)
    addr_counter = Counter()
    for r in locs_v2:
        a = (r.get("address1") or "").strip().lower()
        c = (r.get("city") or "").strip().lower()
        s = (r.get("state") or "").strip().lower()
        z = (r.get("zip") or "").strip()
        if a and c and s:
            key = (a, c, s, z)
            addr_counter[key] += 1
    loc_dupes = {k: v for k, v in addr_counter.items() if v > 1}
    if loc_dupes:
        total_dup = sum(v for v in loc_dupes.values())
        add_finding("MEDIUM", "Locations_v2",
                    "Duplicate addresses in locations_v2",
                    f"{len(loc_dupes)} unique addresses appear multiple times ({total_dup} total rows)",
                    count=len(loc_dupes),
                    samples=[{"address": k[0], "city": k[1], "state": k[2], "zip": k[3], "count": v} for k, v in list(loc_dupes.items())[:5]])

    # Orphan locations_v2 (not referenced by any store_location)
    referenced_loc_ids = {r["location_id"] for r in store_locs if r.get("location_id") is not None}
    orphan_locs = [r for r in locs_v2 if r["id"] not in referenced_loc_ids]
    if orphan_locs:
        pct = len(orphan_locs) / max(len(locs_v2), 1) * 100
        sev = "MEDIUM" if pct > 20 else "LOW"
        add_finding(sev, "Locations_v2",
                    "Orphan locations_v2 (not referenced by any store_location)",
                    f"{len(orphan_locs)} ({pct:.1f}%) locations_v2 have no store_location pointing to them",
                    count=len(orphan_locs),
                    samples=[{"id": r["id"], "address1": r.get("address1"), "city": r.get("city"), "state": r.get("state")} for r in orphan_locs])

    if not lv2_no_city and not lv2_no_state and not lv2_no_address:
        add_finding("INFO", "Locations_v2",
                    "Locations_v2 core fields: ALL POPULATED",
                    "All locations have city, state, and address1.")

    # ------------------------------------------------------------------
    # 3. DISCOUNTS_V2: referential integrity (active -> merchants, -> store_locations)
    # ------------------------------------------------------------------
    print("\n[3] Active discounts_v2 referential integrity...")

    active_discounts = paginated_get(
        client, "discounts_v2",
        select="id,merchant_id,store_location_id,name,discount_type,discount_value,active",
        filters="active=eq.true"
    )
    print(f"    Active discounts_v2: {len(active_discounts)}")

    all_disc_count = get_exact_count(client, "discounts_v2")
    print(f"    Total discounts_v2: {all_disc_count}")

    # Active discounts -> inactive/nonexistent merchants
    disc_bad_merchant = [d for d in active_discounts
                          if d.get("merchant_id") is not None
                          and d["merchant_id"] not in all_merchant_ids]
    disc_inactive_merchant = [d for d in active_discounts
                               if d.get("merchant_id") is not None
                               and d["merchant_id"] in all_merchant_ids
                               and d["merchant_id"] not in active_merchant_ids]

    if disc_bad_merchant:
        add_finding("HIGH", "Referential Integrity",
                    "Active discounts -> nonexistent merchants",
                    f"{len(disc_bad_merchant)} active discounts reference merchants not in the merchants table",
                    count=len(disc_bad_merchant),
                    samples=[{"id": d["id"], "merchant_id": d["merchant_id"], "name": d.get("name")} for d in disc_bad_merchant])

    if disc_inactive_merchant:
        add_finding("MEDIUM", "Referential Integrity",
                    "Active discounts -> inactive merchants",
                    f"{len(disc_inactive_merchant)} active discounts reference merchants with is_active=false",
                    count=len(disc_inactive_merchant),
                    samples=[{"id": d["id"], "merchant_id": d["merchant_id"], "name": d.get("name")} for d in disc_inactive_merchant])

    if not disc_bad_merchant and not disc_inactive_merchant:
        add_finding("INFO", "Referential Integrity",
                    "Active discounts_v2 -> merchants: ALL CLEAN",
                    "All active discounts point to active, existing merchants.")

    # Active discounts -> store_locations
    all_sl_ids: Set[int] = {r["id"] for r in store_locs}
    disc_with_sl = [d for d in active_discounts if d.get("store_location_id") is not None]
    disc_bad_sl = [d for d in disc_with_sl if d["store_location_id"] not in all_sl_ids]

    if disc_bad_sl:
        add_finding("HIGH", "Referential Integrity",
                    "Active discounts -> nonexistent store_locations",
                    f"{len(disc_bad_sl)} active discounts reference store_location_ids not in store_locations",
                    count=len(disc_bad_sl),
                    samples=[{"id": d["id"], "store_location_id": d["store_location_id"]} for d in disc_bad_sl])
    else:
        if disc_with_sl:
            add_finding("INFO", "Referential Integrity",
                        "Active discounts -> store_locations: ALL CLEAN",
                        f"All {len(disc_with_sl)} discounts with store_location_id reference valid rows.")
        else:
            add_finding("INFO", "Referential Integrity",
                        "Active discounts -> store_locations: none linked",
                        "No active discounts have a store_location_id set.")

    # Discounts with no merchant_id
    disc_no_merchant = [d for d in active_discounts if d.get("merchant_id") is None]
    if disc_no_merchant:
        add_finding("HIGH", "Referential Integrity",
                    "Active discounts with NULL merchant_id",
                    f"{len(disc_no_merchant)} active discounts have no merchant_id",
                    count=len(disc_no_merchant),
                    samples=[{"id": d["id"], "name": d.get("name")} for d in disc_no_merchant])

    # ------------------------------------------------------------------
    # 4. GUIDE ARTICLES
    # ------------------------------------------------------------------
    print("\n[4] Guide articles...")

    guide_articles = paginated_get(
        client, "guide_articles",
        select="id,slug,title,category_id,status,publish_web,overview_md,body_md,vertical"
    )
    print(f"    Total guide_articles: {len(guide_articles)}")

    if guide_articles:
        ga_published = [a for a in guide_articles if a.get("publish_web") is True]
        ga_status_published = [a for a in guide_articles if a.get("status") == "published"]
        ga_draft = [a for a in guide_articles if a.get("status") == "draft"]

        pub_set = ga_published if ga_published else ga_status_published

        # Empty content on published articles
        ga_pub_empty_body = [a for a in pub_set if is_empty(a.get("body_md"))]
        ga_pub_empty_overview = [a for a in pub_set if is_empty(a.get("overview_md"))]
        ga_pub_empty_title = [a for a in pub_set if is_empty(a.get("title"))]

        if ga_pub_empty_body:
            add_finding("HIGH", "Guide Articles",
                        "Published guide articles with empty body_md",
                        f"{len(ga_pub_empty_body)} published guide articles have no body content",
                        count=len(ga_pub_empty_body),
                        samples=[{"id": a["id"], "slug": a.get("slug"), "title": a.get("title")} for a in ga_pub_empty_body])

        if ga_pub_empty_overview:
            add_finding("MEDIUM", "Guide Articles",
                        "Published guide articles with empty overview_md",
                        f"{len(ga_pub_empty_overview)} published guide articles have no overview",
                        count=len(ga_pub_empty_overview),
                        samples=[{"id": a["id"], "slug": a.get("slug")} for a in ga_pub_empty_overview])

        if ga_pub_empty_title:
            add_finding("HIGH", "Guide Articles",
                        "Published guide articles with empty title",
                        f"{len(ga_pub_empty_title)} published guide articles have no title",
                        count=len(ga_pub_empty_title))

        # Duplicate slugs
        slug_counter = Counter(a.get("slug") for a in guide_articles if not is_empty(a.get("slug")))
        dup_slugs = {k: v for k, v in slug_counter.items() if v > 1}
        if dup_slugs:
            add_finding("HIGH", "Guide Articles",
                        "Duplicate guide article slugs",
                        f"{len(dup_slugs)} slugs appear more than once",
                        count=len(dup_slugs),
                        samples=[{"slug": k, "count": v} for k, v in list(dup_slugs.items())[:5]])

        # NULL slug
        ga_no_slug = [a for a in guide_articles if is_empty(a.get("slug"))]
        if ga_no_slug:
            add_finding("MEDIUM", "Guide Articles",
                        "Guide articles with NULL/empty slug",
                        f"{len(ga_no_slug)} guide articles have no slug",
                        count=len(ga_no_slug),
                        samples=[{"id": a["id"], "title": a.get("title")} for a in ga_no_slug])

        # Category check
        guide_cats = paginated_get(client, "guide_categories", select="id,name,slug")
        guide_cat_ids = {c["id"] for c in guide_cats}
        ga_no_cat = [a for a in guide_articles if a.get("category_id") is None]
        ga_bad_cat = [a for a in guide_articles
                       if a.get("category_id") is not None and a["category_id"] not in guide_cat_ids]

        if ga_no_cat:
            add_finding("LOW", "Guide Articles",
                        "Guide articles with NULL category_id",
                        f"{len(ga_no_cat)} guide articles have no category_id",
                        count=len(ga_no_cat),
                        samples=[{"id": a["id"], "slug": a.get("slug")} for a in ga_no_cat])

        if ga_bad_cat:
            add_finding("MEDIUM", "Guide Articles",
                        "Guide articles with invalid category_id",
                        f"{len(ga_bad_cat)} guide articles reference category_ids not in guide_categories",
                        count=len(ga_bad_cat),
                        samples=[{"id": a["id"], "slug": a.get("slug"), "category_id": a["category_id"]} for a in ga_bad_cat])

        if (not ga_pub_empty_body and not ga_pub_empty_overview and not ga_pub_empty_title
                and not dup_slugs and not ga_bad_cat):
            add_finding("INFO", "Guide Articles",
                        "Guide articles content: ALL CLEAN",
                        "No quality issues found on published guides.")

        add_finding("INFO", "Guide Articles",
                    "Guide articles counts",
                    f"Total: {len(guide_articles)}, publish_web=true: {len(ga_published)}, "
                    f"status=published: {len(ga_status_published)}, Draft: {len(ga_draft)}")

        # Category utilization
        used_guide_cats = {a["category_id"] for a in guide_articles if a.get("category_id")}
        orphan_guide_cats = [c for c in guide_cats if c["id"] not in used_guide_cats]
        if orphan_guide_cats:
            add_finding("LOW", "Guide Articles",
                        "Unused guide_categories",
                        f"{len(orphan_guide_cats)} guide_categories have no articles",
                        count=len(orphan_guide_cats),
                        samples=[{"id": c["id"], "name": c.get("name"), "slug": c.get("slug")} for c in orphan_guide_cats])

        add_finding("INFO", "Guide Articles",
                    "Guide categories",
                    f"Total: {len(guide_cats)}, Used: {len(used_guide_cats)}, Unused: {len(orphan_guide_cats)}")
    else:
        add_finding("INFO", "Guide Articles", "guide_articles table: EMPTY", "No guide articles found.")

    # ------------------------------------------------------------------
    # 5. PROTECTION ARTICLES
    # ------------------------------------------------------------------
    print("\n[5] Protection articles...")

    prot_articles = paginated_get(
        client, "protection_articles",
        select="id,slug,title,category_id,status,publish_web,overview_md,body_md,featured"
    )
    print(f"    Total protection_articles: {len(prot_articles)}")

    if prot_articles:
        pa_published = [a for a in prot_articles if a.get("publish_web") is True]
        pa_status_published = [a for a in prot_articles if a.get("status") == "published"]
        pa_draft = [a for a in prot_articles if a.get("status") == "draft"]
        pub_pa = pa_published if pa_published else pa_status_published

        pa_pub_empty_body = [a for a in pub_pa if is_empty(a.get("body_md"))]
        pa_pub_empty_overview = [a for a in pub_pa if is_empty(a.get("overview_md"))]
        pa_pub_empty_title = [a for a in pub_pa if is_empty(a.get("title"))]

        if pa_pub_empty_body:
            add_finding("HIGH", "Protection Articles",
                        "Published protection articles with empty body_md",
                        f"{len(pa_pub_empty_body)} published protection articles have no body",
                        count=len(pa_pub_empty_body),
                        samples=[{"id": a["id"], "slug": a.get("slug"), "title": a.get("title")} for a in pa_pub_empty_body])

        if pa_pub_empty_overview:
            add_finding("MEDIUM", "Protection Articles",
                        "Published protection articles with empty overview_md",
                        f"{len(pa_pub_empty_overview)} published protection articles have no overview",
                        count=len(pa_pub_empty_overview),
                        samples=[{"id": a["id"], "slug": a.get("slug")} for a in pa_pub_empty_overview])

        if pa_pub_empty_title:
            add_finding("HIGH", "Protection Articles",
                        "Published protection articles with empty title",
                        f"{len(pa_pub_empty_title)} published protection articles have no title",
                        count=len(pa_pub_empty_title))

        # Duplicate slugs
        pa_slug_counter = Counter(a.get("slug") for a in prot_articles if not is_empty(a.get("slug")))
        pa_dup_slugs = {k: v for k, v in pa_slug_counter.items() if v > 1}
        if pa_dup_slugs:
            add_finding("HIGH", "Protection Articles",
                        "Duplicate protection article slugs",
                        f"{len(pa_dup_slugs)} slugs appear more than once",
                        count=len(pa_dup_slugs),
                        samples=[{"slug": k, "count": v} for k, v in list(pa_dup_slugs.items())[:5]])

        # Category check
        prot_cats = paginated_get(client, "protection_categories", select="id,name,slug")
        prot_cat_ids = {c["id"] for c in prot_cats}
        pa_no_cat = [a for a in prot_articles if a.get("category_id") is None]
        pa_bad_cat = [a for a in prot_articles
                       if a.get("category_id") is not None and a["category_id"] not in prot_cat_ids]

        if pa_no_cat:
            add_finding("LOW", "Protection Articles",
                        "Protection articles with NULL category_id",
                        f"{len(pa_no_cat)} protection articles have no category_id",
                        count=len(pa_no_cat),
                        samples=[{"id": a["id"], "slug": a.get("slug")} for a in pa_no_cat])

        if pa_bad_cat:
            add_finding("MEDIUM", "Protection Articles",
                        "Protection articles with invalid category_id",
                        f"{len(pa_bad_cat)} protection articles reference category_ids not in protection_categories",
                        count=len(pa_bad_cat),
                        samples=[{"id": a["id"], "slug": a.get("slug"), "category_id": a["category_id"]} for a in pa_bad_cat])

        if (not pa_pub_empty_body and not pa_pub_empty_overview and not pa_pub_empty_title
                and not pa_dup_slugs and not pa_bad_cat):
            add_finding("INFO", "Protection Articles",
                        "Protection articles content: ALL CLEAN",
                        "No quality issues found.")

        add_finding("INFO", "Protection Articles",
                    "Protection articles counts",
                    f"Total: {len(prot_articles)}, publish_web=true: {len(pa_published)}, "
                    f"status=published: {len(pa_status_published)}, Draft: {len(pa_draft)}")

        used_prot_cats = {a["category_id"] for a in prot_articles if a.get("category_id")}
        orphan_prot_cats = [c for c in prot_cats if c["id"] not in used_prot_cats]
        add_finding("INFO", "Protection Articles",
                    "Protection categories",
                    f"Total: {len(prot_cats)}, Used: {len(used_prot_cats)}, Unused: {len(orphan_prot_cats)}")
    else:
        add_finding("INFO", "Protection Articles", "protection_articles: EMPTY", "")

    # ------------------------------------------------------------------
    # 6. DMA PAGE CONTENT
    # ------------------------------------------------------------------
    print("\n[6] DMA page content...")

    dma_pages = paginated_get(
        client, "dma_page_content",
        select="id,slug,display_name,dma_description,status,hero_headline,hero_subhead,intro_md,"
               "savings_spotlight_md,local_tips_md,faq_md,merchant_count,location_count,coverage_tier"
    )
    print(f"    Total dma_page_content: {len(dma_pages)}")

    if dma_pages:
        dma_published = [d for d in dma_pages if d.get("status") == "published"]
        dma_draft = [d for d in dma_pages if d.get("status") == "draft"]

        dma_pub_empty_headline = [d for d in dma_published if is_empty(d.get("hero_headline"))]
        dma_pub_empty_intro = [d for d in dma_published if is_empty(d.get("intro_md"))]

        if dma_pub_empty_headline:
            add_finding("HIGH", "DMA Pages",
                        "Published DMA pages with empty hero_headline",
                        f"{len(dma_pub_empty_headline)} published DMA pages have no headline",
                        count=len(dma_pub_empty_headline),
                        samples=[{"id": d["id"], "slug": d.get("slug"), "display_name": d.get("display_name")} for d in dma_pub_empty_headline])

        if dma_pub_empty_intro:
            add_finding("MEDIUM", "DMA Pages",
                        "Published DMA pages with empty intro_md",
                        f"{len(dma_pub_empty_intro)} published DMA pages have no intro content",
                        count=len(dma_pub_empty_intro),
                        samples=[{"id": d["id"], "slug": d.get("slug"), "display_name": d.get("display_name")} for d in dma_pub_empty_intro])

        # Duplicate DMA slugs
        dma_slug_counter = Counter(d.get("slug") for d in dma_pages if not is_empty(d.get("slug")))
        dma_dup_slugs = {k: v for k, v in dma_slug_counter.items() if v > 1}
        if dma_dup_slugs:
            add_finding("HIGH", "DMA Pages",
                        "Duplicate DMA page slugs",
                        f"{len(dma_dup_slugs)} slugs appear more than once",
                        count=len(dma_dup_slugs),
                        samples=[{"slug": k, "count": v} for k, v in list(dma_dup_slugs.items())[:5]])

        # merchant_count = 0 or NULL on published
        dma_zero = [d for d in dma_published
                     if d.get("merchant_count") is None or d.get("merchant_count") == 0]
        if dma_zero:
            add_finding("MEDIUM", "DMA Pages",
                        "Published DMA pages with 0/NULL merchant_count",
                        f"{len(dma_zero)} published pages show zero merchants",
                        count=len(dma_zero),
                        samples=[{"id": d["id"], "slug": d.get("slug"), "display_name": d.get("display_name"),
                                  "merchant_count": d.get("merchant_count")} for d in dma_zero])

        # Published with ALL main content fields empty (shell pages)
        content_fields = ["hero_headline", "hero_subhead", "intro_md", "savings_spotlight_md", "local_tips_md"]
        dma_shells = [d for d in dma_published if all(is_empty(d.get(f)) for f in content_fields)]
        if dma_shells:
            add_finding("HIGH", "DMA Pages",
                        "DMA shell pages (published, all content empty)",
                        f"{len(dma_shells)} published DMA pages have zero content in all fields",
                        count=len(dma_shells),
                        samples=[{"id": d["id"], "slug": d.get("slug"), "display_name": d.get("display_name")} for d in dma_shells])

        if not dma_pub_empty_headline and not dma_pub_empty_intro and not dma_dup_slugs and not dma_shells:
            add_finding("INFO", "DMA Pages",
                        "DMA page content: ALL CLEAN",
                        "No content quality issues found.")

        add_finding("INFO", "DMA Pages",
                    "DMA page counts",
                    f"Total: {len(dma_pages)}, Published: {len(dma_published)}, Draft: {len(dma_draft)}")
    else:
        add_finding("INFO", "DMA Pages", "dma_page_content: EMPTY", "No DMA pages found.")

    # ------------------------------------------------------------------
    # 7. MERCHANT PAGE CONTENT (columns on merchants table)
    # ------------------------------------------------------------------
    print("\n[7] Merchant page content consistency...")

    print("  Fetching merchant page metadata...")
    merchant_page_data = paginated_get(
        client, "merchants",
        select="id,name,is_active,page_slug,page_status,page_hero_headline,page_hero_subhead,"
               "page_about_md,page_how_to_save_md,page_tips_md,page_faq_json,page_faq_md,"
               "page_protection_note_md"
    )
    print(f"    Total merchants: {len(merchant_page_data)}")

    page_content_fields = [
        "page_hero_headline", "page_hero_subhead", "page_about_md",
        "page_how_to_save_md", "page_tips_md", "page_faq_json", "page_faq_md",
        "page_protection_note_md"
    ]

    m_published_pages = [m for m in merchant_page_data if m.get("page_status") == "published"]
    m_with_slug = [m for m in merchant_page_data if not is_empty(m.get("page_slug"))]

    # Shell pages: published + ALL content fields empty
    m_shell = []
    for m in m_published_pages:
        if all(is_empty(m.get(f)) for f in page_content_fields):
            m_shell.append(m)

    active_shells = [m for m in m_shell if m.get("is_active")]
    inactive_shells = [m for m in m_shell if not m.get("is_active")]

    if m_shell:
        add_finding("HIGH", "Merchant Pages",
                    "Shell pages: published with ALL content fields empty",
                    f"{len(m_shell)} merchants have page_status='published' but zero content "
                    f"({len(active_shells)} active, {len(inactive_shells)} inactive merchants)",
                    count=len(m_shell),
                    samples=[{"id": m["id"], "name": m.get("name"), "page_slug": m.get("page_slug"),
                              "is_active": m.get("is_active")} for m in m_shell])

    # Partial content (some fields filled, some empty) on published pages
    m_partial = []
    for m in m_published_pages:
        filled = sum(1 for f in page_content_fields if not is_empty(m.get(f)))
        if 0 < filled < len(page_content_fields):
            m_partial.append({"id": m["id"], "name": m.get("name"),
                              "filled": filled, "total": len(page_content_fields),
                              "page_slug": m.get("page_slug")})
    if m_partial:
        add_finding("MEDIUM", "Merchant Pages",
                    "Published merchant pages with partial content",
                    f"{len(m_partial)} published merchant pages have some content fields filled but not all",
                    count=len(m_partial),
                    samples=m_partial)

    # Slug but no content and not published
    m_slug_no_content = []
    for m in m_with_slug:
        if m.get("page_status") != "published":
            if all(is_empty(m.get(f)) for f in page_content_fields):
                m_slug_no_content.append(m)
    if m_slug_no_content:
        add_finding("LOW", "Merchant Pages",
                    "Merchants with page_slug but no content (non-published)",
                    f"{len(m_slug_no_content)} merchants have a page_slug set but zero content and are not published",
                    count=len(m_slug_no_content))

    # Duplicate page_slugs
    slug_counter = Counter(m.get("page_slug") for m in merchant_page_data if not is_empty(m.get("page_slug")))
    dup_slugs = {k: v for k, v in slug_counter.items() if v > 1}
    if dup_slugs:
        add_finding("HIGH", "Merchant Pages",
                    "Duplicate merchant page_slugs",
                    f"{len(dup_slugs)} page_slugs appear more than once",
                    count=len(dup_slugs),
                    samples=[{"page_slug": k, "count": v} for k, v in list(dup_slugs.items())[:5]])
    else:
        if m_with_slug:
            add_finding("INFO", "Merchant Pages",
                        "No duplicate merchant page_slugs",
                        f"All {len(m_with_slug)} page_slugs are unique.")

    m_full_content = [m for m in m_published_pages
                      if all(not is_empty(m.get(f)) for f in page_content_fields)]

    add_finding("INFO", "Merchant Pages",
                "Merchant page content summary",
                f"Total merchants: {len(merchant_page_data)}, "
                f"With page_slug: {len(m_with_slug)}, "
                f"page_status=published: {len(m_published_pages)}, "
                f"Full content: {len(m_full_content)}, "
                f"Shell (zero content): {len(m_shell)}, "
                f"Partial content: {len(m_partial)}")

    # ------------------------------------------------------------------
    # 8. MALLS
    # ------------------------------------------------------------------
    print("\n[8] Malls...")

    malls = paginated_get(client, "Malls", select="id,location_id,location_v2_id,phone,photo_url")
    print(f"    Total Malls: {len(malls)}")

    if malls:
        # Malls -> locations_v2
        mall_no_loc = [m for m in malls if m.get("location_v2_id") is None]
        mall_bad_loc = [m for m in malls
                         if m.get("location_v2_id") is not None
                         and m["location_v2_id"] not in all_loc_v2_ids]

        if mall_no_loc:
            add_finding("LOW", "Malls",
                        "Malls with NULL location_v2_id",
                        f"{len(mall_no_loc)} malls have no location_v2_id",
                        count=len(mall_no_loc))

        if mall_bad_loc:
            add_finding("MEDIUM", "Malls",
                        "Malls -> nonexistent locations_v2",
                        f"{len(mall_bad_loc)} malls reference location_v2_ids not in locations_v2",
                        count=len(mall_bad_loc))

        # Malls referenced by store_locations
        mall_ids_in_sl = {r["mall_id"] for r in store_locs if r.get("mall_id") is not None}
        all_mall_ids = {m["id"] for m in malls}
        sl_bad_mall = {r["mall_id"] for r in store_locs
                        if r.get("mall_id") is not None and r["mall_id"] not in all_mall_ids}
        if sl_bad_mall:
            count_bad = len([r for r in store_locs if r.get("mall_id") in sl_bad_mall])
            add_finding("MEDIUM", "Malls",
                        "Store locations -> nonexistent Malls",
                        f"{count_bad} store_locations reference {len(sl_bad_mall)} mall_ids not in Malls table",
                        count=count_bad)

        add_finding("INFO", "Malls",
                    "Malls count",
                    f"Total: {len(malls)}, Referenced by store_locations: {len(mall_ids_in_sl)}")

    # ------------------------------------------------------------------
    # 9. OFFERS & ARTICLE_OFFERS
    # ------------------------------------------------------------------
    print("\n[9] Offers & article_offers...")

    offers = paginated_get(client, "offers", select="id,slug,name,is_active,offer_type,partner_name,cta_url")
    print(f"    Total offers: {len(offers)}")

    if offers:
        offers_active = [o for o in offers if o.get("is_active")]
        offers_no_slug = [o for o in offers if is_empty(o.get("slug"))]
        offers_no_cta = [o for o in offers_active if is_empty(o.get("cta_url"))]

        if offers_no_cta:
            add_finding("MEDIUM", "Offers",
                        "Active offers with no cta_url",
                        f"{len(offers_no_cta)} active offers have no CTA URL",
                        count=len(offers_no_cta),
                        samples=[{"id": o["id"], "name": o.get("name")} for o in offers_no_cta])

        add_finding("INFO", "Offers",
                    "Offers counts",
                    f"Total: {len(offers)}, Active: {len(offers_active)}, "
                    f"No slug: {len(offers_no_slug)}")

    article_offers = paginated_get(client, "article_offers", select="article_id,offer_id,placement_key")
    print(f"    Total article_offers: {len(article_offers)}")

    if article_offers:
        offer_ids = {o["id"] for o in offers}
        ao_bad_offer = [ao for ao in article_offers if ao.get("offer_id") not in offer_ids]
        if ao_bad_offer:
            add_finding("MEDIUM", "Offers",
                        "article_offers -> nonexistent offers",
                        f"{len(ao_bad_offer)} article_offers reference offer_ids not in offers table",
                        count=len(ao_bad_offer))

    # ------------------------------------------------------------------
    # 10. SIGNUPS
    # ------------------------------------------------------------------
    print("\n[10] Signups...")

    signups_count = get_exact_count(client, "signups")
    print(f"    Total signups: {signups_count}")

    # Get a sample to check quality
    signup_sample = paginated_get(
        client, "signups",
        select="id,email,signup_type,brand,created_at,zip,source,site",
    )
    if signup_sample:
        su_no_email = [s for s in signup_sample if is_empty(s.get("email"))]
        if su_no_email:
            add_finding("MEDIUM", "Signups",
                        "Signups with NULL/empty email",
                        f"{len(su_no_email)} signups have no email address",
                        count=len(su_no_email))

        # Brand distribution
        brand_dist = Counter(s.get("brand") or "(null)" for s in signup_sample)
        add_finding("INFO", "Signups",
                    "Signups breakdown",
                    f"Total: {len(signup_sample)}. By brand: {dict(brand_dist)}")

        # Signup type distribution
        type_dist = Counter(s.get("signup_type") or "(null)" for s in signup_sample)
        add_finding("INFO", "Signups",
                    "Signups by type",
                    f"{dict(type_dist)}")

    # ------------------------------------------------------------------
    # 11. HONEYPOT HITS
    # ------------------------------------------------------------------
    print("\n[11] Honeypot hits...")

    honeypot_count = get_exact_count(client, "honeypot_hits")
    print(f"    Total honeypot_hits: {honeypot_count}")
    add_finding("INFO", "Honeypot",
                "Honeypot hits count",
                f"Total: {honeypot_count}")

    # ------------------------------------------------------------------
    # 12. PROTECTION PIPELINE: sources, incoming, tags
    # ------------------------------------------------------------------
    print("\n[12] Protection pipeline tables...")

    prot_sources = paginated_get(client, "protection_sources", select="id,slug,name,source_type,is_active")
    prot_incoming = paginated_get(client, "protection_incoming_items",
                                   select="id,source_id,status,dedupe_hash,url,title")

    print(f"    protection_sources: {len(prot_sources)}")
    print(f"    protection_incoming_items: {len(prot_incoming)}")

    if prot_sources:
        ps_active = [s for s in prot_sources if s.get("is_active")]
        add_finding("INFO", "Protection Pipeline",
                    "Protection sources",
                    f"Total: {len(prot_sources)}, Active: {len(ps_active)}")

    if prot_incoming:
        pi_status_dist = Counter(i.get("status") or "(null)" for i in prot_incoming)
        add_finding("INFO", "Protection Pipeline",
                    "Protection incoming items by status",
                    f"Total: {len(prot_incoming)}. {dict(pi_status_dist)}")

        # Check for duplicate dedupe_hash
        hash_counter = Counter(i.get("dedupe_hash") for i in prot_incoming if i.get("dedupe_hash"))
        dup_hashes = {k: v for k, v in hash_counter.items() if v > 1}
        if dup_hashes:
            add_finding("MEDIUM", "Protection Pipeline",
                        "Duplicate dedupe_hash in protection_incoming_items",
                        f"{len(dup_hashes)} hashes appear more than once",
                        count=len(dup_hashes))

    prot_tags = paginated_get(client, "protection_tags", select="id,name,tag_type")
    if prot_tags:
        tag_type_dist = Counter(t.get("tag_type") or "(null)" for t in prot_tags)
        add_finding("INFO", "Protection Pipeline",
                    "Protection tags",
                    f"Total: {len(prot_tags)}, By type: {dict(tag_type_dist)}")

    # ------------------------------------------------------------------
    # 13. MERCHANT CATEGORIES
    # ------------------------------------------------------------------
    print("\n[13] Merchant categories...")

    merch_cats = paginated_get(client, "merchant_categories", select="id,slug,name,display_name,is_active")
    print(f"    Total merchant_categories: {len(merch_cats)}")

    if merch_cats:
        mc_active = [c for c in merch_cats if c.get("is_active")]
        # Check if merchants reference them via category_id
        merch_cat_ids = {c["id"] for c in merch_cats}

        # Fetch merchant category_ids
        merch_cats_used = paginated_get(client, "merchants", select="id,category_id",
                                         filters="category_id=not.is.null")
        used_mc_ids = {m["category_id"] for m in merch_cats_used}
        bad_mc = used_mc_ids - merch_cat_ids
        if bad_mc:
            count_bad = len([m for m in merch_cats_used if m["category_id"] in bad_mc])
            add_finding("MEDIUM", "Merchant Categories",
                        "Merchants with invalid category_id",
                        f"{count_bad} merchants reference {len(bad_mc)} category_ids not in merchant_categories",
                        count=count_bad)

        unused_mc = [c for c in merch_cats if c["id"] not in used_mc_ids]
        if unused_mc:
            add_finding("LOW", "Merchant Categories",
                        "Unused merchant_categories",
                        f"{len(unused_mc)} merchant_categories are not referenced by any merchant",
                        count=len(unused_mc),
                        samples=[{"id": c["id"], "name": c.get("name"), "slug": c.get("slug")} for c in unused_mc])

        add_finding("INFO", "Merchant Categories",
                    "Merchant categories",
                    f"Total: {len(merch_cats)}, Active: {len(mc_active)}, "
                    f"Used by merchants: {len(used_mc_ids)}, Unused: {len(unused_mc)}")

    # ------------------------------------------------------------------
    # 14. STAGING / IMPORT TABLES
    # ------------------------------------------------------------------
    print("\n[14] Staging & import tables...")

    for tbl in ["stg_store_locations_upload", "stg_store_locations_clean",
                "import_ace_store_staging", "ace_stage_deduped", "ace_stage_matches"]:
        cnt = get_exact_count(client, tbl)
        if cnt < 0:
            # Try fetching with a different select since some don't have 'id'
            rows = paginated_get(client, tbl, select="*", filters="limit=1")
            cnt = len(rows) if rows else 0
        print(f"    {tbl}: {cnt}")
        add_finding("INFO", "Staging Tables",
                    f"{tbl}",
                    f"Row count: {cnt}")

    # Location import jobs
    import_jobs = paginated_get(client, "location_import_jobs",
                                 select="id,status,batch_size,processed_count,success_count,fail_count,source_name")
    if import_jobs:
        job_status = Counter(j.get("status") for j in import_jobs)
        total_fails = sum(j.get("fail_count") or 0 for j in import_jobs)
        add_finding("INFO", "Staging Tables",
                    "Location import jobs",
                    f"Total: {len(import_jobs)}, By status: {dict(job_status)}, Total fail_count: {total_fails}")
        if total_fails > 0:
            failed_jobs = [j for j in import_jobs if (j.get("fail_count") or 0) > 0]
            add_finding("LOW", "Staging Tables",
                        "Import jobs with failures",
                        f"{len(failed_jobs)} jobs had failures (total {total_fails} failed rows)",
                        count=total_fails,
                        samples=[{"id": j["id"], "source": j.get("source_name"),
                                  "failed": j.get("fail_count"), "status": j.get("status")} for j in failed_jobs])

    # ------------------------------------------------------------------
    # 15. BACKUP TABLES
    # ------------------------------------------------------------------
    print("\n[15] Backup tables...")

    for tbl in ["merchants_backup_2026_01_27", "discounts_v2_backup_2026_01_27",
                "store_locations_backup_2026_01_27"]:
        cnt = get_exact_count(client, tbl)
        print(f"    {tbl}: {cnt}")
        add_finding("INFO", "Backup Tables",
                    f"{tbl}",
                    f"Row count: {cnt} (consider dropping if cleanup is confirmed stable)")

    # ------------------------------------------------------------------
    # 16. MISC TABLES
    # ------------------------------------------------------------------
    print("\n[16] Misc tables...")

    # Zip_County_DMA
    zcd_count = get_exact_count(client, "Zip_County_DMA")
    print(f"    Zip_County_DMA: {zcd_count}")
    add_finding("INFO", "Misc Tables", "Zip_County_DMA", f"Row count: {zcd_count}")

    # map_points (view or materialized)
    mp_count = get_exact_count(client, "map_points")
    print(f"    map_points: {mp_count}")
    add_finding("INFO", "Misc Tables", "map_points", f"Row count: {mp_count}")

    # processed_zip_codes
    pzc_count = get_exact_count(client, "processed_zip_codes")
    print(f"    processed_zip_codes: {pzc_count}")
    add_finding("INFO", "Misc Tables", "processed_zip_codes", f"Row count: {pzc_count}")

    # zip_code_locks
    zcl = paginated_get(client, "zip_code_locks", select="zip_code,locked_by,locked_at,expires_at")
    print(f"    zip_code_locks: {len(zcl)}")
    if zcl:
        add_finding("LOW", "Misc Tables",
                    "zip_code_locks still active",
                    f"{len(zcl)} zip_code_locks exist (may be stale)",
                    count=len(zcl))

    # offer_placements
    op = paginated_get(client, "offer_placements", select="id,placement_key,description")
    print(f"    offer_placements: {len(op)}")
    add_finding("INFO", "Misc Tables", "offer_placements", f"Row count: {len(op)}")

    # ------------------------------------------------------------------
    # 17. OVERALL STATISTICS
    # ------------------------------------------------------------------
    print("\n[17] Overall statistics...")

    m_active = [m for m in merchant_page_data if m.get("is_active")]
    m_inactive = [m for m in merchant_page_data if not m.get("is_active")]

    add_finding("INFO", "Overall Statistics",
                "Merchants",
                f"Total: {len(merchant_page_data)}, Active: {len(m_active)}, Inactive: {len(m_inactive)}, "
                f"Ratio: {len(m_active)/max(len(merchant_page_data),1)*100:.1f}% active")

    add_finding("INFO", "Overall Statistics",
                "Store Locations",
                f"Total: {len(store_locs)}, Active: {len(sl_active)}, Inactive: {len(sl_inactive)}")

    add_finding("INFO", "Overall Statistics",
                "Locations_v2",
                f"Total: {len(locs_v2)}, Referenced: {len(referenced_loc_ids)}, "
                f"Orphan: {len(orphan_locs)}")

    add_finding("INFO", "Overall Statistics",
                "Discounts_v2",
                f"Total: {all_disc_count}, Active: {len(active_discounts)}")

    # ------------------------------------------------------------------
    # REPORT
    # ------------------------------------------------------------------
    print("\n")
    print("=" * 80)
    print("                    DATA QUALITY REPORT")
    print("=" * 80)

    severity_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "INFO": 3}
    findings_sorted = sorted(findings, key=lambda f: (severity_order.get(f["severity"], 99), f["category"], f["title"]))

    severity_counts = Counter(f["severity"] for f in findings)

    print(f"\n  SUMMARY: {severity_counts.get('HIGH', 0)} HIGH | "
          f"{severity_counts.get('MEDIUM', 0)} MEDIUM | "
          f"{severity_counts.get('LOW', 0)} LOW | "
          f"{severity_counts.get('INFO', 0)} INFO")

    current_severity = None
    for f in findings_sorted:
        if f["severity"] != current_severity:
            current_severity = f["severity"]
            marker = {"HIGH": "!!!", "MEDIUM": "!!", "LOW": "!", "INFO": "---"}.get(current_severity, "")
            print(f"\n{'='*70}")
            print(f"  {marker} {current_severity} FINDINGS {marker}")
            print(f"{'='*70}")

        count_str = f" [{f['count']}]" if "count" in f else ""
        print(f"\n  [{f['severity']}] {f['category']} / {f['title']}{count_str}")
        print(f"    {f['detail']}")
        if f.get("samples"):
            print(f"    Samples:")
            for s in f["samples"]:
                print(f"      {json.dumps(s, default=str)}")

    print(f"\n{'='*80}")
    print("  SCAN COMPLETE")
    print(f"{'='*80}")

    client.close()


if __name__ == "__main__":
    main()
