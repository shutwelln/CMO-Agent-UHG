#!/usr/bin/env python3
"""Audit merchant pages for inconsistencies between default_discount_* fields
(source of truth) and the LLM-generated page content.

Flags:
  1. CONTRADICTION: Page says "no discount" / "does not offer" but merchants table
     has discount data in default_discount_text/default_discount_value.
  2. MISMATCH: Page mentions a different % or amount than default_discount_value.
  3. MISSING_DISCOUNT_DATA: Page exists but merchants table has no discount data at all.
  4. VALUE_VS_TEXT: default_discount_value and default_discount_text disagree on percentage.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

# Fields to fetch
SELECT = (
    "id,name,is_national,is_active,"
    "default_discount_value,default_discount_text,"
    "default_discount_requirement,default_discount_type,"
    "default_discount_details,"
    "page_slug,page_status,page_hero_headline,page_hero_subhead,"
    "page_direct_answer,page_about_md,"
    "page_how_to_save_md,page_tips_md"
)

# Phrases that indicate the LLM said "no discount"
NO_DISCOUNT_PHRASES = [
    "does not currently offer",
    "does not offer",
    "doesn't currently offer",
    "doesn't offer",
    "no standard senior discount",
    "no dedicated senior discount",
    "no specific senior discount",
    "no official senior discount",
    "no formal senior discount",
    "no traditional senior discount",
    "no set senior discount",
    "doesn't have a standard senior discount",
    "does not have a standard senior discount",
    "doesn't have a dedicated senior discount",
    "does not have a dedicated senior discount",
    "doesn't have an official senior discount",
    "does not have an official senior discount",
    "no longer offers a senior discount",
    "discontinued its senior discount",
    "no senior discount program",
    "no senior-specific discount",
]


def extract_percentages(text: str) -> list[str]:
    """Extract all percentage values from text (e.g., '15%', '20%')."""
    return re.findall(r"(\d+)%", text or "")


def has_no_discount_language(text: str) -> list[str]:
    """Check if text contains phrases indicating no discount exists."""
    if not text:
        return []
    text_lower = text.lower()
    return [phrase for phrase in NO_DISCOUNT_PHRASES if phrase in text_lower]


def main() -> None:
    # Fetch all merchants with page content
    url = f"{SUPABASE_URL}/rest/v1/merchants"
    params = {
        "select": SELECT,
        "is_active": "eq.true",
        "page_hero_headline": "not.is.null",
        "limit": "5000",
    }
    resp = httpx.get(url, headers=HEADERS, params=params, timeout=30)
    if resp.status_code != 200:
        print(f"ERROR: {resp.status_code} {resp.text}")
        sys.exit(1)

    merchants = resp.json()
    # Filter to rows that actually have page content
    merchants = [m for m in merchants if m.get("page_hero_headline")]
    print(f"Auditing {len(merchants)} merchants with page content...\n")

    issues: dict[str, list[dict]] = {
        "CONTRADICTION": [],
        "PERCENTAGE_MISMATCH": [],
        "VALUE_VS_TEXT_MISMATCH": [],
        "MISSING_DISCOUNT_DATA": [],
        "UNRESOLVED_PLACEHOLDER": [],
    }

    for m in merchants:
        mid = m["id"]
        name = m["name"]
        dv = m.get("default_discount_value") or ""
        dt = m.get("default_discount_text") or ""
        dr = m.get("default_discount_requirement") or ""
        da = m.get("page_direct_answer") or ""
        about = m.get("page_about_md") or ""
        subhead = m.get("page_hero_subhead") or ""

        has_discount_data = bool(dv.strip() or dt.strip())
        combined_page_text = f"{da} {about} {subhead}"

        # 1. CONTRADICTION: Merchant table has discount data but page says "no discount"
        if has_discount_data:
            no_disc_matches = has_no_discount_language(combined_page_text)
            if no_disc_matches:
                issues["CONTRADICTION"].append({
                    "id": mid,
                    "name": name,
                    "default_discount_value": dv,
                    "default_discount_text": dt,
                    "matched_phrases": no_disc_matches[:3],
                    "page_direct_answer": da[:200],
                })

        # 2. PERCENTAGE_MISMATCH: Discount percentages in page don't match merchants table
        if has_discount_data:
            table_pcts = set(extract_percentages(f"{dv} {dt}"))
            page_pcts = set(extract_percentages(combined_page_text))
            if table_pcts and page_pcts and not table_pcts.intersection(page_pcts):
                issues["PERCENTAGE_MISMATCH"].append({
                    "id": mid,
                    "name": name,
                    "table_percentages": sorted(table_pcts),
                    "page_percentages": sorted(page_pcts),
                    "default_discount_value": dv,
                    "default_discount_text": dt,
                    "page_direct_answer": da[:200],
                })

        # 3. VALUE_VS_TEXT_MISMATCH: default_discount_value and default_discount_text
        #    have different percentages
        if dv.strip() and dt.strip():
            val_pcts = set(extract_percentages(dv))
            txt_pcts = set(extract_percentages(dt))
            if val_pcts and txt_pcts and not val_pcts.intersection(txt_pcts):
                issues["VALUE_VS_TEXT_MISMATCH"].append({
                    "id": mid,
                    "name": name,
                    "default_discount_value": dv,
                    "default_discount_text": dt,
                    "value_pcts": sorted(val_pcts),
                    "text_pcts": sorted(txt_pcts),
                })

        # 4. MISSING_DISCOUNT_DATA: Page exists but no discount data in merchants table
        if not has_discount_data:
            issues["MISSING_DISCOUNT_DATA"].append({
                "id": mid,
                "name": name,
                "page_status": m.get("page_status"),
                "page_direct_answer": da[:200],
            })

        # 5. UNRESOLVED_PLACEHOLDER: {{DISCOUNT_*}} tokens still in page content
        placeholder_fields = {
            "page_about_md": m.get("page_about_md") or "",
            "page_how_to_save_md": m.get("page_how_to_save_md") or "",
            "page_tips_md": m.get("page_tips_md") or "",
        }
        unresolved = []
        for fld_name, fld_val in placeholder_fields.items():
            tokens = re.findall(r"\{\{DISCOUNT_\w+\}\}", fld_val)
            if tokens:
                unresolved.append({"field": fld_name, "tokens": tokens})
        if unresolved:
            issues["UNRESOLVED_PLACEHOLDER"].append({
                "id": mid,
                "name": name,
                "unresolved_fields": unresolved,
            })

    # ── Report ──────────────────────────────────────────────────────────────
    total_issues = sum(len(v) for v in issues.values())
    print("=" * 80)
    print(f"AUDIT RESULTS: {total_issues} issues found across {len(merchants)} merchant pages")
    print("=" * 80)

    for category, items in issues.items():
        print(f"\n{'─' * 70}")
        print(f"{category}: {len(items)} merchant(s)")
        print(f"{'─' * 70}")
        if not items:
            print("  (none)")
            continue
        for item in items:
            print(f"\n  [{item['id']}] {item['name']}")
            for k, v in item.items():
                if k in ("id", "name"):
                    continue
                print(f"    {k}: {v}")

    # Save full results to JSON
    out_path = Path(__file__).resolve().parent.parent / "data" / "saverwell" / "merchant_page_audit.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(issues, indent=2))
    print(f"\nFull results saved to: {out_path}")

    # Summary
    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}")
    print(f"  Total merchant pages audited:  {len(merchants)}")
    print(f"  CONTRADICTION (page says no discount, table has data):  {len(issues['CONTRADICTION'])}")
    print(f"  PERCENTAGE_MISMATCH (page % differs from table %):     {len(issues['PERCENTAGE_MISMATCH'])}")
    print(f"  VALUE_VS_TEXT_MISMATCH (value vs text fields differ):  {len(issues['VALUE_VS_TEXT_MISMATCH'])}")
    print(f"  MISSING_DISCOUNT_DATA (page exists, no table data):    {len(issues['MISSING_DISCOUNT_DATA'])}")
    print(f"  UNRESOLVED_PLACEHOLDER ({{{{DISCOUNT_*}}}} in content):   {len(issues['UNRESOLVED_PLACEHOLDER'])}")


if __name__ == "__main__":
    main()
