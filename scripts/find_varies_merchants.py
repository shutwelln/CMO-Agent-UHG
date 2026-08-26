#!/usr/bin/env python3
"""Find all merchants and discounts_v2 rows where discount value contains 'varies'."""

import os
import sys
import requests
from dotenv import load_dotenv

load_dotenv("/Users/nickshutwell/Desktop/CMO Agent/.env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}


def query_merchants():
    """Query merchants where default_discount_value contains 'varies'."""
    url = (
        f"{SUPABASE_URL}/rest/v1/merchants"
        "?default_discount_value=ilike.*varies*"
        "&select=id,name,default_discount_value,default_discount_text,"
        "default_discount_requirement,default_discount_type,is_national,"
        "is_active,category_id,page_slug,page_status"
        "&order=name.asc"
    )
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def query_discounts_v2():
    """Query discounts_v2 where discount_value contains 'varies' and active=true."""
    url = (
        f"{SUPABASE_URL}/rest/v1/discounts_v2"
        "?discount_value=ilike.*varies*"
        "&active=eq.true"
        "&select=id,merchant_id,name,discount_value,details,requirement,"
        "discount_type,store_location_id"
        "&order=name.asc"
    )
    resp = requests.get(url, headers=HEADERS)
    resp.raise_for_status()
    return resp.json()


def print_merchants_table(merchants):
    """Print a formatted table of merchants."""
    if not merchants:
        print("No merchants found with 'Varies' in default_discount_value.")
        return

    # Column widths
    id_w = max(len("ID"), max(len(str(m["id"])) for m in merchants))
    name_w = max(len("Name"), max(len(str(m["name"] or "")) for m in merchants))
    name_w = min(name_w, 45)  # cap width
    val_w = max(len("Discount Value"), max(len(str(m["default_discount_value"] or "")) for m in merchants))
    text_w = max(len("Discount Text"), max(len(str(m["default_discount_text"] or "")[:50]) for m in merchants))
    text_w = min(text_w, 50)
    type_w = max(len("Type"), max(len(str(m["default_discount_type"] or "")) for m in merchants))
    req_w = max(len("Requirement"), max(len(str(m["default_discount_requirement"] or "")[:40]) for m in merchants))
    req_w = min(req_w, 40)

    header = (
        f"{'ID':<{id_w}}  "
        f"{'Name':<{name_w}}  "
        f"{'Discount Value':<{val_w}}  "
        f"{'Discount Text':<{text_w}}  "
        f"{'Type':<{type_w}}  "
        f"{'Requirement':<{req_w}}  "
        f"{'National':>8}  "
        f"{'Active':>6}  "
        f"{'Page Status':<12}  "
        f"{'Page Slug'}"
    )
    print(header)
    print("-" * len(header))

    for m in merchants:
        name_display = str(m["name"] or "")[:name_w]
        text_display = str(m["default_discount_text"] or "")[:text_w]
        req_display = str(m["default_discount_requirement"] or "")[:req_w]
        print(
            f"{str(m['id']):<{id_w}}  "
            f"{name_display:<{name_w}}  "
            f"{str(m['default_discount_value'] or ''):<{val_w}}  "
            f"{text_display:<{text_w}}  "
            f"{str(m['default_discount_type'] or ''):<{type_w}}  "
            f"{req_display:<{req_w}}  "
            f"{str(m['is_national']):>8}  "
            f"{str(m['is_active']):>6}  "
            f"{str(m.get('page_status') or ''):<12}  "
            f"{str(m.get('page_slug') or '')}"
        )


def print_discounts_table(discounts):
    """Print a formatted table of discounts_v2 rows."""
    if not discounts:
        print("\nNo active discounts_v2 rows found with 'Varies' in discount_value.")
        return

    print(f"\n{'='*80}")
    print(f"DISCOUNTS_V2 ROWS WITH 'VARIES' (active=true)")
    print(f"{'='*80}\n")

    id_w = max(len("ID"), max(len(str(d["id"])) for d in discounts))
    mid_w = max(len("Merchant ID"), max(len(str(d["merchant_id"])) for d in discounts))
    name_w = max(len("Name"), max(len(str(d["name"] or "")) for d in discounts))
    name_w = min(name_w, 40)
    val_w = max(len("Value"), max(len(str(d["discount_value"] or "")) for d in discounts))
    det_w = max(len("Details"), max(len(str(d["details"] or "")[:50]) for d in discounts))
    det_w = min(det_w, 50)
    type_w = max(len("Type"), max(len(str(d["discount_type"] or "")) for d in discounts))

    header = (
        f"{'ID':<{id_w}}  "
        f"{'Merchant ID':<{mid_w}}  "
        f"{'Name':<{name_w}}  "
        f"{'Value':<{val_w}}  "
        f"{'Details':<{det_w}}  "
        f"{'Type':<{type_w}}  "
        f"{'Requirement'}"
    )
    print(header)
    print("-" * len(header))

    for d in discounts:
        name_display = str(d["name"] or "")[:name_w]
        det_display = str(d["details"] or "")[:det_w]
        print(
            f"{str(d['id']):<{id_w}}  "
            f"{str(d['merchant_id']):<{mid_w}}  "
            f"{name_display:<{name_w}}  "
            f"{str(d['discount_value'] or ''):<{val_w}}  "
            f"{det_display:<{det_w}}  "
            f"{str(d['discount_type'] or ''):<{type_w}}  "
            f"{str(d.get('requirement') or '')}"
        )

    print(f"\nTotal discounts_v2 rows: {len(discounts)}")


def main():
    print(f"{'='*80}")
    print(f"MERCHANTS WITH 'VARIES' IN default_discount_value")
    print(f"{'='*80}\n")

    merchants = query_merchants()
    print_merchants_table(merchants)
    print(f"\nTotal merchants: {len(merchants)}")

    discounts = query_discounts_v2()
    print_discounts_table(discounts)


if __name__ == "__main__":
    main()
