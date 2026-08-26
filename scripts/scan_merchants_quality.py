#!/usr/bin/env python3
"""
Comprehensive data quality scan of the Supabase merchants table.

Checks for placeholder text, missing fields, inconsistencies, duplicates,
and published pages with no content. Outputs a severity-organized report.
"""
from __future__ import annotations

import os
import sys
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

PAGE_SIZE = 1000

# Fields to scan for placeholder patterns
SCAN_FIELDS = [
    "name",
    "default_discount_value",
    "default_discount_text",
    "default_discount_requirement",
    "default_discount_type",
    "page_slug",
    "page_hero_headline",
    "page_hero_subhead",
    "page_about_md",
    "page_how_to_save_md",
    "page_tips_md",
    "page_seo_title",
    "page_seo_description",
]

# Patterns that indicate placeholder / dummy data
PLACEHOLDER_PATTERNS = [
    "REPLACE",
    "TODO",
    "TBD",
    "placeholder",
    "dummy",
    "test",
    "sample",
    "example",
    "lorem",
    "XXX",
    "???",
    "coming soon",
    "insert",
    "fill in",
    "update this",
    "pending",
]

# Page content fields that should be populated for published pages
PAGE_CONTENT_FIELDS = [
    "page_hero_headline",
    "page_hero_subhead",
    "page_about_md",
    "page_how_to_save_md",
    "page_tips_md",
    "page_seo_title",
    "page_seo_description",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def paginated_get(
    client: httpx.Client,
    table: str,
    select: str = "*",
    filters: str = "",
    order: str = "",
) -> List[Dict[str, Any]]:
    """Fetch all rows from a Supabase table, paginating at PAGE_SIZE."""
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{SUPABASE_URL}/rest/v1/{table}?select={select}"
        if filters:
            url += f"&{filters}"
        if order:
            url += f"&order={order}"
        url += f"&limit={PAGE_SIZE}&offset={offset}"
        resp = client.get(url, headers=HEADERS)
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return all_rows


def count_rows(client: httpx.Client, table: str, filters: str = "") -> int:
    """Use Prefer: count=exact HEAD-style request to get row count."""
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=id"
    if filters:
        url += f"&{filters}"
    url += "&limit=0"
    h = {**HEADERS, "Prefer": "count=exact"}
    resp = client.get(url, headers=h)
    resp.raise_for_status()
    cr = resp.headers.get("content-range", "")
    # format: "0-0/1234" or "*/1234"
    if "/" in cr:
        return int(cr.split("/")[1])
    return 0


def is_empty(val: Any) -> bool:
    return val is None or (isinstance(val, str) and val.strip() == "")


def contains_pattern(val: Any, pattern: str) -> bool:
    if val is None:
        return False
    return pattern.lower() in str(val).lower()


def section(title: str) -> None:
    print(f"\n{'=' * 80}")
    print(f"  {title}")
    print(f"{'=' * 80}")


def subsection(title: str) -> None:
    print(f"\n  --- {title} ---")


def severity(level: str, msg: str, count: int = 0, examples: Optional[List[str]] = None) -> None:
    icons = {"HIGH": "[HIGH]", "MEDIUM": "[MED]", "LOW": "[LOW]", "INFO": "[INFO]"}
    icon = icons.get(level, "[???]")
    line = f"  {icon} {msg}"
    if count > 0:
        line += f" -- count: {count}"
    print(line)
    if examples:
        for ex in examples[:10]:
            print(f"         -> {ex}")
        if len(examples) > 10:
            print(f"         ... and {len(examples) - 10} more")


# ---------------------------------------------------------------------------
# Main scan
# ---------------------------------------------------------------------------
def main() -> None:
    print("=" * 80)
    print("  MERCHANTS TABLE - COMPREHENSIVE DATA QUALITY SCAN")
    print("=" * 80)

    client = httpx.Client(timeout=60)

    # ------------------------------------------------------------------
    # 1. Total counts
    # ------------------------------------------------------------------
    section("1. ROW COUNTS")
    total_count = count_rows(client, "merchants")
    active_count = count_rows(client, "merchants", "is_active=eq.true")
    inactive_count = total_count - active_count
    print(f"  Total merchants:    {total_count}")
    print(f"  Active merchants:   {active_count}")
    print(f"  Inactive merchants: {inactive_count}")

    # ------------------------------------------------------------------
    # Fetch all active merchants (the main dataset for scanning)
    # ------------------------------------------------------------------
    print("\n  Fetching all active merchants...")
    active_merchants = paginated_get(
        client,
        "merchants",
        select=",".join([
            "id", "name", "is_active", "is_national",
            "default_discount_value", "default_discount_text",
            "default_discount_requirement", "default_discount_type",
            "page_slug", "page_status",
            "page_hero_headline", "page_hero_subhead",
            "page_about_md", "page_how_to_save_md", "page_tips_md",
            "page_seo_title", "page_seo_description",
            "category_id", "merchant_type",
            "website_url", "logo_url", "featured",
        ]),
        filters="is_active=eq.true",
        order="name.asc",
    )
    print(f"  Fetched {len(active_merchants)} active merchant rows.")

    # ------------------------------------------------------------------
    # 2. Placeholder / dummy text scan
    # ------------------------------------------------------------------
    section("2. PLACEHOLDER / DUMMY TEXT SCAN (active merchants)")

    placeholder_hits: Dict[str, Dict[str, List[str]]] = {}  # pattern -> field -> [merchant names]
    for pattern in PLACEHOLDER_PATTERNS:
        for field in SCAN_FIELDS:
            hits = [
                m["name"] or f"(id={m['id']})"
                for m in active_merchants
                if contains_pattern(m.get(field), pattern)
            ]
            if hits:
                placeholder_hits.setdefault(pattern, {})[field] = hits

    if placeholder_hits:
        for pat, fields in sorted(placeholder_hits.items()):
            total_hits = sum(len(v) for v in fields.values())
            sev = "HIGH" if total_hits >= 10 else "MEDIUM"
            for fld, names in fields.items():
                severity(sev, f"Pattern '{pat}' in field '{fld}'", len(names), names[:5])
    else:
        severity("INFO", "No placeholder/dummy text found in any scanned fields.", 0)

    # ------------------------------------------------------------------
    # 3. NULL and empty default_discount_* fields
    # ------------------------------------------------------------------
    section("3. NULL / EMPTY DEFAULT DISCOUNT FIELDS (active merchants)")

    discount_fields = [
        "default_discount_value",
        "default_discount_text",
        "default_discount_requirement",
        "default_discount_type",
    ]

    for fld in discount_fields:
        null_count = sum(1 for m in active_merchants if m.get(fld) is None)
        empty_count = sum(1 for m in active_merchants if isinstance(m.get(fld), str) and m[fld].strip() == "")
        null_names = [m["name"] for m in active_merchants if m.get(fld) is None][:5]
        empty_names = [m["name"] for m in active_merchants if isinstance(m.get(fld), str) and m[fld].strip() == ""][:5]

        if null_count > 0:
            sev = "HIGH" if fld == "default_discount_value" and null_count > 20 else "MEDIUM"
            severity(sev, f"NULL {fld}", null_count, null_names)
        if empty_count > 0:
            severity("MEDIUM", f"Empty string {fld}", empty_count, empty_names)

    # Cross-reference: merchants with NO default discount data at all
    subsection("Merchants with ALL four default_discount fields null/empty")
    no_discount_merchants = [
        m for m in active_merchants
        if all(is_empty(m.get(fld)) for fld in discount_fields)
    ]
    severity(
        "HIGH" if len(no_discount_merchants) > 10 else "MEDIUM",
        "Active merchants with zero default discount data",
        len(no_discount_merchants),
        [m["name"] for m in no_discount_merchants[:10]],
    )

    # Now check which of those also have no active discounts_v2 rows
    subsection("Of those, merchants with NO active discounts_v2 rows either")
    no_discount_ids = [m["id"] for m in no_discount_merchants]
    orphan_merchants: List[str] = []
    # Check in batches of 50 to avoid URL length issues
    for i in range(0, len(no_discount_ids), 50):
        batch_ids = no_discount_ids[i : i + 50]
        id_list = ",".join(str(x) for x in batch_ids)
        discounts = paginated_get(
            client,
            "discounts_v2",
            select="merchant_id",
            filters=f"merchant_id=in.({id_list})&active=eq.true",
        )
        merchants_with_discounts = {d["merchant_id"] for d in discounts}
        for mid in batch_ids:
            if mid not in merchants_with_discounts:
                name = next((m["name"] for m in no_discount_merchants if m["id"] == mid), f"id={mid}")
                orphan_merchants.append(name)

    severity(
        "HIGH",
        "Active merchants with ZERO discount info anywhere (no defaults, no discounts_v2)",
        len(orphan_merchants),
        orphan_merchants[:15],
    )

    # ------------------------------------------------------------------
    # 4. Unique default_discount_value distribution
    # ------------------------------------------------------------------
    section("4. DEFAULT_DISCOUNT_VALUE DISTRIBUTION (active merchants)")

    dv_values = [m.get("default_discount_value") for m in active_merchants]
    dv_counter = Counter(dv_values)
    print(f"  Unique values: {len(dv_counter)}")
    print(f"  Top 30 by frequency:")
    for val, cnt in dv_counter.most_common(30):
        display = repr(val) if val is not None else "NULL"
        print(f"    {display:50s} {cnt:>5}")

    # ------------------------------------------------------------------
    # 5. Unique default_discount_type distribution
    # ------------------------------------------------------------------
    section("5. DEFAULT_DISCOUNT_TYPE DISTRIBUTION (active merchants)")

    dt_values = [m.get("default_discount_type") for m in active_merchants]
    dt_counter = Counter(dt_values)
    print(f"  Unique values: {len(dt_counter)}")
    for val, cnt in dt_counter.most_common(50):
        display = repr(val) if val is not None else "NULL"
        print(f"    {display:50s} {cnt:>5}")

    # ------------------------------------------------------------------
    # 6. Unique default_discount_requirement distribution
    # ------------------------------------------------------------------
    section("6. DEFAULT_DISCOUNT_REQUIREMENT DISTRIBUTION (active merchants)")

    dr_values = [m.get("default_discount_requirement") for m in active_merchants]
    dr_counter = Counter(dr_values)
    print(f"  Unique values: {len(dr_counter)}")
    for val, cnt in dr_counter.most_common(50):
        display = repr(val) if val is not None else "NULL"
        print(f"    {display:50s} {cnt:>5}")

    # ------------------------------------------------------------------
    # 7. Capitalization inconsistencies in default_discount_type
    # ------------------------------------------------------------------
    section("7. CAPITALIZATION INCONSISTENCIES IN DEFAULT_DISCOUNT_TYPE")

    # Group by lowercased value
    case_groups: Dict[str, List[str]] = {}
    for m in active_merchants:
        val = m.get("default_discount_type")
        if val and isinstance(val, str) and val.strip():
            key = val.strip().lower()
            case_groups.setdefault(key, []).append(val.strip())

    inconsistencies_found = False
    for key, variants in sorted(case_groups.items()):
        unique_forms = set(variants)
        if len(unique_forms) > 1:
            inconsistencies_found = True
            form_counts = Counter(variants)
            desc = ", ".join(f"'{f}' x{c}" for f, c in form_counts.most_common())
            severity("MEDIUM", f"Inconsistent capitalization for '{key}': {desc}")

    if not inconsistencies_found:
        severity("INFO", "No capitalization inconsistencies found in default_discount_type.")

    # ------------------------------------------------------------------
    # 8. page_status distribution
    # ------------------------------------------------------------------
    section("8. PAGE_STATUS DISTRIBUTION (active merchants)")

    ps_values = [m.get("page_status") for m in active_merchants]
    ps_counter = Counter(ps_values)
    for val, cnt in ps_counter.most_common():
        display = repr(val) if val is not None else "NULL"
        print(f"    {display:50s} {cnt:>5}")

    # ------------------------------------------------------------------
    # 9. National merchants missing key fields
    # ------------------------------------------------------------------
    section("9. NATIONAL MERCHANTS (is_national=true) MISSING KEY FIELDS")

    national = [m for m in active_merchants if m.get("is_national")]
    print(f"  Total active national merchants: {len(national)}")

    key_fields_for_national = [
        "default_discount_value",
        "page_slug",
        "page_hero_headline",
        "page_seo_title",
    ]
    for fld in key_fields_for_national:
        missing = [m["name"] for m in national if is_empty(m.get(fld))]
        if missing:
            severity("HIGH", f"National merchants missing '{fld}'", len(missing), missing[:10])

    # ------------------------------------------------------------------
    # 10. Duplicate merchant names
    # ------------------------------------------------------------------
    section("10. DUPLICATE ACTIVE MERCHANT NAMES")

    name_counter = Counter(m["name"] for m in active_merchants if m.get("name"))
    dupes = {name: cnt for name, cnt in name_counter.items() if cnt > 1}
    if dupes:
        for name, cnt in sorted(dupes.items(), key=lambda x: -x[1]):
            severity("HIGH", f"Duplicate name: '{name}'", cnt)
    else:
        severity("INFO", "No duplicate active merchant names found.")

    # ------------------------------------------------------------------
    # 11. Vague default_discount_value ("Varies", etc.)
    # ------------------------------------------------------------------
    section("11. VAGUE DEFAULT_DISCOUNT_VALUE")

    vague_patterns = ["varies", "various", "call for", "ask", "see store", "check", "contact"]
    vague_hits: List[Tuple[str, str]] = []
    for m in active_merchants:
        val = m.get("default_discount_value")
        if val and isinstance(val, str):
            for vp in vague_patterns:
                if vp in val.lower():
                    vague_hits.append((m["name"], val))
                    break

    if vague_hits:
        severity(
            "LOW",
            "Merchants with vague discount values",
            len(vague_hits),
            [f"{name}: '{val}'" for name, val in vague_hits[:10]],
        )
    else:
        severity("INFO", "No vague discount values found.")

    # ------------------------------------------------------------------
    # 12. String "None" values (literal, not SQL NULL)
    # ------------------------------------------------------------------
    section("12. STRING LITERAL 'None' VALUES (not SQL NULL)")

    none_fields = discount_fields
    for fld in none_fields:
        hits = [
            m["name"]
            for m in active_merchants
            if isinstance(m.get(fld), str) and m[fld].strip().lower() == "none"
        ]
        if hits:
            severity("MEDIUM", f"String 'None' in {fld}", len(hits), hits[:10])

    # Also check for "null" string
    for fld in none_fields:
        hits = [
            m["name"]
            for m in active_merchants
            if isinstance(m.get(fld), str) and m[fld].strip().lower() == "null"
        ]
        if hits:
            severity("MEDIUM", f"String 'null' in {fld}", len(hits), hits[:10])

    # ------------------------------------------------------------------
    # 13. Published pages with empty content
    # ------------------------------------------------------------------
    section("13. PUBLISHED PAGES WITH EMPTY/NULL CONTENT FIELDS")

    published = [m for m in active_merchants if m.get("page_status") == "published"]
    print(f"  Total published merchants: {len(published)}")

    for fld in PAGE_CONTENT_FIELDS:
        empty_published = [m["name"] for m in published if is_empty(m.get(fld))]
        if empty_published:
            severity("HIGH", f"Published but missing '{fld}'", len(empty_published), empty_published[:10])

    # Completely empty published pages (all content fields null/empty)
    shell_pages = [
        m["name"]
        for m in published
        if all(is_empty(m.get(fld)) for fld in PAGE_CONTENT_FIELDS)
    ]
    if shell_pages:
        severity("HIGH", "Published SHELL pages (all content fields empty)", len(shell_pages), shell_pages[:15])
    else:
        severity("INFO", "No completely empty published pages found.")

    # ------------------------------------------------------------------
    # 14. Additional checks
    # ------------------------------------------------------------------
    section("14. ADDITIONAL CHECKS")

    # Check for merchants with page_slug but no page_status
    slug_no_status = [
        m["name"]
        for m in active_merchants
        if not is_empty(m.get("page_slug")) and is_empty(m.get("page_status"))
    ]
    if slug_no_status:
        severity("MEDIUM", "Has page_slug but NULL/empty page_status", len(slug_no_status), slug_no_status[:10])

    # Check for merchants with page_status but no page_slug
    status_no_slug = [
        m["name"]
        for m in active_merchants
        if not is_empty(m.get("page_status")) and is_empty(m.get("page_slug"))
    ]
    if status_no_slug:
        severity("MEDIUM", "Has page_status but NULL/empty page_slug", len(status_no_slug), status_no_slug[:10])

    # Check for default_discount_value that look like percentages but are stored inconsistently
    pct_formats: Dict[str, int] = {}
    for m in active_merchants:
        val = m.get("default_discount_value")
        if val and isinstance(val, str) and "%" in val:
            # Categorize format: "10%", "10% off", "Up to 10%", etc.
            stripped = val.strip()
            # Rough categorization
            if stripped.endswith("% off"):
                pct_formats.setdefault("X% off", 0)
                pct_formats["X% off"] += 1
            elif stripped.endswith("%"):
                pct_formats.setdefault("X%", 0)
                pct_formats["X%"] += 1
            elif "up to" in stripped.lower():
                pct_formats.setdefault("Up to X%", 0)
                pct_formats["Up to X%"] += 1
            else:
                pct_formats.setdefault("other % format", 0)
                pct_formats["other % format"] += 1

    if len(pct_formats) > 1:
        desc = ", ".join(f"'{k}': {v}" for k, v in sorted(pct_formats.items(), key=lambda x: -x[1]))
        severity("LOW", f"Inconsistent percentage formats in default_discount_value: {desc}")

    # Check for very long field values (potential data dumps)
    for fld in SCAN_FIELDS:
        long_vals = [
            (m["name"], len(str(m.get(fld, ""))))
            for m in active_merchants
            if m.get(fld) and len(str(m[fld])) > 5000
        ]
        if long_vals:
            severity(
                "LOW",
                f"Unusually long values in '{fld}' (>5000 chars)",
                len(long_vals),
                [f"{name}: {length} chars" for name, length in long_vals[:5]],
            )

    # Check for leading/trailing whitespace in name
    whitespace_names = [
        f"'{m['name']}'"
        for m in active_merchants
        if m.get("name") and m["name"] != m["name"].strip()
    ]
    if whitespace_names:
        severity("LOW", "Merchant names with leading/trailing whitespace", len(whitespace_names), whitespace_names[:10])

    # Check for category_id distribution
    subsection("Category ID distribution (active merchants)")
    cat_values = [m.get("category_id") for m in active_merchants]
    cat_counter = Counter(cat_values)
    for val, cnt in cat_counter.most_common(30):
        display = repr(val) if val is not None else "NULL"
        print(f"    {display:50s} {cnt:>5}")

    # Check for merchant_type distribution
    subsection("Merchant type distribution (active merchants)")
    mt_values = [m.get("merchant_type") for m in active_merchants]
    mt_counter = Counter(mt_values)
    for val, cnt in mt_counter.most_common(30):
        display = repr(val) if val is not None else "NULL"
        print(f"    {display:50s} {cnt:>5}")

    # Check for featured merchants without key data
    featured = [m for m in active_merchants if m.get("featured")]
    if featured:
        subsection(f"Featured merchants check ({len(featured)} featured)")
        for fld in ["default_discount_value", "page_slug", "page_hero_headline", "logo_url"]:
            missing = [m["name"] for m in featured if is_empty(m.get(fld))]
            if missing:
                severity("HIGH", f"Featured merchants missing '{fld}'", len(missing), missing[:10])

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    section("SCAN COMPLETE")
    print(f"  Scanned {len(active_merchants)} active merchants across {len(SCAN_FIELDS)} fields")
    print(f"  Checked {len(PLACEHOLDER_PATTERNS)} placeholder patterns")
    print(f"  Total merchants in table: {total_count}")
    print()


if __name__ == "__main__":
    main()
