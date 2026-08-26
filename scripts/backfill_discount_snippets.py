#!/usr/bin/env python3
"""
Backfill short discount snippets for the Store Directory tiles.

Two fixes:
1. Merchants with NULL default_discount_text: derive snippet from discounts_v2.discount_value
2. Merchants with verbose default_discount_text (>30 chars): shorten to a clean snippet

The snippet is the short text shown on each tile (e.g., "10% off", "$5 off", "Discounts vary").
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional

import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

DRY_RUN = "--dry-run" in sys.argv


def make_snippet(value: Optional[str]) -> Optional[str]:
    """Convert a discount_value into a short display snippet for tiles."""
    if not value or not value.strip():
        return None

    v = value.strip()

    # Already a good snippet
    if v.lower() in ("discounts vary", "varies"):
        return "Discounts vary"

    # "10% off", "$5 off" - already contains "off"
    if "off" in v.lower():
        return v

    # Range with % - "10-20%" or "5-10%"
    range_pct = re.match(r"^(\d+[\-–]\d+)\s*%$", v)
    if range_pct:
        return f"{range_pct.group(1)}% off"

    # Bare percentage - "10%" or "Up to 15%"
    if v.endswith("%"):
        return f"{v} off"
    if re.match(r"^Up to \d+%$", v, re.IGNORECASE):
        return f"{v} off"

    # Dollar amount - "$5", "$10"
    if v.startswith("$") and re.match(r"^\$[\d.]+$", v):
        return f"{v} off"

    # Dollar range - "$1-4"
    if re.match(r"^\$\d+[\-–]\d+", v):
        return f"{v} off"

    # Bare number - assume percentage
    if re.match(r"^\d+$", v):
        return f"{v}% off"

    # Special text values - keep as-is if short enough
    if len(v) <= 25:
        return v

    # Truncate anything else
    return v[:25].rstrip() + "..."


def fetch_all(endpoint: str, params: Dict[str, str]) -> List[Dict[str, Any]]:
    """Paginated fetch from Supabase REST API."""
    results: List[Dict[str, Any]] = []
    offset = 0
    while True:
        p = {**params, "limit": "1000", "offset": str(offset)}
        r = httpx.get(f"{SUPABASE_URL}/rest/v1/{endpoint}", headers=HEADERS, params=p)
        r.raise_for_status()
        batch = r.json()
        results.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    return results


def patch_merchant(merchant_id: int, updates: Dict[str, Any]) -> None:
    """PATCH a single merchant row."""
    r = httpx.patch(
        f"{SUPABASE_URL}/rest/v1/merchants?id=eq.{merchant_id}",
        headers=HEADERS,
        json=updates,
    )
    r.raise_for_status()


def main() -> None:
    print("Fetching active merchants...")
    merchants = fetch_all(
        "merchants",
        {
            "select": "id,name,default_discount_value,default_discount_text",
            "is_active": "eq.true",
            "order": "name.asc",
        },
    )
    print(f"  Total active merchants: {len(merchants)}")

    # ---------------------------------------------------------------
    # 1. Merchants with NULL default_discount_text
    # ---------------------------------------------------------------
    missing_text = [m for m in merchants if not m.get("default_discount_text")]
    print(f"\nMerchants missing default_discount_text: {len(missing_text)}")

    # For those with a default_discount_value already on the merchant row, use it directly
    fix_from_merchant = []
    need_lookup = []
    for m in missing_text:
        snippet = make_snippet(m.get("default_discount_value"))
        if snippet:
            fix_from_merchant.append((m, snippet))
        else:
            need_lookup.append(m)

    print(f"  Can fix from merchant.default_discount_value: {len(fix_from_merchant)}")
    print(f"  Need discounts_v2 lookup: {len(need_lookup)}")

    # Lookup discounts_v2 for those without a merchant-level value
    fix_from_v2 = []
    still_missing = []
    if need_lookup:
        lookup_ids = [m["id"] for m in need_lookup]
        for i in range(0, len(lookup_ids), 50):
            batch_ids = lookup_ids[i : i + 50]
            ids_str = ",".join(str(x) for x in batch_ids)
            discounts = fetch_all(
                "discounts_v2",
                {
                    "select": "merchant_id,discount_value",
                    "merchant_id": f"in.({ids_str})",
                    "active": "eq.true",
                },
            )
            by_merchant: Dict[int, str] = {}
            for d in discounts:
                mid = d["merchant_id"]
                if mid not in by_merchant and d.get("discount_value"):
                    by_merchant[mid] = d["discount_value"]

            for mid in batch_ids:
                m = next(x for x in need_lookup if x["id"] == mid)
                if mid in by_merchant:
                    snippet = make_snippet(by_merchant[mid])
                    if snippet:
                        fix_from_v2.append((m, snippet, by_merchant[mid]))
                    else:
                        still_missing.append(m)
                else:
                    still_missing.append(m)

    print(f"  Can fix from discounts_v2: {len(fix_from_v2)}")
    print(f"  Still missing (no data anywhere): {len(still_missing)}")

    # ---------------------------------------------------------------
    # 2. Merchants with verbose default_discount_text (>30 chars)
    # ---------------------------------------------------------------
    verbose = [
        m
        for m in merchants
        if m.get("default_discount_text") and len(m["default_discount_text"]) > 30
    ]
    print(f"\nVerbose default_discount_text (>30 chars): {len(verbose)}")

    fix_verbose = []
    for m in verbose:
        # Try to derive from default_discount_value first
        snippet = make_snippet(m.get("default_discount_value"))
        if snippet and len(snippet) <= 30:
            fix_verbose.append((m, snippet))
        else:
            # For "Varies by location for seniors 55+" etc., shorten
            text = m["default_discount_text"]
            if "varies by location" in text.lower():
                fix_verbose.append((m, "Varies by location"))
            elif snippet:
                fix_verbose.append((m, snippet))
            else:
                # Last resort: take first meaningful chunk
                fix_verbose.append((m, "Discounts vary"))

    print(f"  Will shorten: {len(fix_verbose)}")

    # ---------------------------------------------------------------
    # Preview
    # ---------------------------------------------------------------
    all_fixes = []
    for m, snippet in fix_from_merchant:
        all_fixes.append((m, snippet, "from merchant value"))
    for m, snippet, raw in fix_from_v2:
        all_fixes.append((m, snippet, f"from discounts_v2 ({raw})"))
    for m, snippet in fix_verbose:
        all_fixes.append((m, snippet, f"shortened from: {m['default_discount_text'][:60]}..."))

    print(f"\n{'='*70}")
    print(f"TOTAL FIXES: {len(all_fixes)}")
    print(f"{'='*70}")

    # Show samples
    print("\n--- Sample fixes (first 30) ---")
    for m, snippet, source in all_fixes[:30]:
        print(f"  {m['name']}: \"{snippet}\"  ({source})")

    if still_missing:
        print(f"\n--- Merchants with NO discount data anywhere ({len(still_missing)}) ---")
        for m in still_missing:
            print(f"  {m['name']}")

    if DRY_RUN:
        print(f"\n[DRY RUN] Would update {len(all_fixes)} merchants. Pass without --dry-run to apply.")
        return

    # ---------------------------------------------------------------
    # Apply
    # ---------------------------------------------------------------
    print(f"\nApplying {len(all_fixes)} updates...")
    success = 0
    errors = 0
    for m, snippet, source in all_fixes:
        updates: Dict[str, Any] = {"default_discount_text": snippet}
        # Also backfill default_discount_value if missing
        if not m.get("default_discount_value"):
            # Extract raw value from snippet
            if "% off" in snippet:
                raw = snippet.replace("% off", "%").replace(" off", "")
                updates["default_discount_value"] = raw
        try:
            patch_merchant(m["id"], updates)
            success += 1
        except Exception as e:
            print(f"  ERROR updating {m['name']}: {e}")
            errors += 1

    print(f"\nDone! Updated: {success}, Errors: {errors}")


if __name__ == "__main__":
    main()
