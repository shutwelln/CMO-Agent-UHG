#!/usr/bin/env python3
"""
Repair double-serialized JSONB fields in Supabase.

The generate_merchant_page_content.py and generate_dma_page_content.py scripts
wrapped Python lists in json.dumps() before passing to httpx's json= parameter.
httpx serializes again, storing a JSON string literal (e.g. '"[...]"') in what
should be a native JSONB array column.

This script reads affected rows, detects string-typed JSONB values, deserializes
them once, and PATCHes the corrected value back.

Usage:
    python scripts/repair_jsonb_fields.py --dry-run   # preview changes
    python scripts/repair_jsonb_fields.py              # apply fixes
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# ---------------------------------------------------------------------------
# Field definitions
# ---------------------------------------------------------------------------

# Merchant JSONB fields that were double-serialized
MERCHANT_JSONB_FIELDS = [
    "page_faq_json",
    "page_related_protection_slugs",
    "page_related_guide_slugs",
    "page_related_merchant_ids",
    "page_seo_keywords",
]

# DMA JSONB fields that were double-serialized
DMA_JSONB_FIELDS = [
    "faq_json",
    "featured_protection_slugs",
    "featured_guide_slugs",
    "seo_keywords",
    "state_codes",
    "county_names",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def try_deserialize(val: Any) -> Tuple[bool, Any]:
    """Try to deserialize a string-wrapped JSON value.

    Returns (needs_fix, corrected_value).
    """
    if not isinstance(val, str):
        return False, val
    try:
        parsed = json.loads(val)
        if isinstance(parsed, (list, dict)):
            return True, parsed
        return False, val
    except (json.JSONDecodeError, TypeError):
        return False, val


def fetch_all(
    client: httpx.Client,
    table: str,
    select: str,
    filters: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Fetch all rows from a Supabase table with pagination."""
    rows: List[Dict[str, Any]] = []
    offset = 0
    page_size = 1000

    while True:
        params: Dict[str, str] = {
            "select": select,
            "limit": str(page_size),
            "offset": str(offset),
        }
        if filters:
            params.update(filters)

        resp = client.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=HEADERS,
            params=params,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        rows.extend(batch)
        if len(batch) < page_size:
            break
        offset += page_size

    return rows


def patch_row(
    client: httpx.Client,
    table: str,
    row_id: Any,
    updates: Dict[str, Any],
    id_col: str = "id",
) -> bool:
    """PATCH a single row in Supabase."""
    resp = client.patch(
        f"{SUPABASE_URL}/rest/v1/{table}",
        headers=HEADERS,
        params={id_col: f"eq.{row_id}"},
        json=updates,
    )
    return resp.status_code in (200, 204)


# ---------------------------------------------------------------------------
# Repair logic
# ---------------------------------------------------------------------------
def repair_table(
    client: httpx.Client,
    table: str,
    id_col: str,
    label_col: str,
    jsonb_fields: List[str],
    filters: Optional[Dict[str, str]],
    dry_run: bool,
) -> Tuple[int, int, int]:
    """Repair double-serialized JSONB fields in a table.

    Returns (rows_checked, rows_fixed, errors).
    """
    select_cols = ",".join([id_col, label_col] + jsonb_fields)
    rows = fetch_all(client, table, select_cols, filters)
    print(f"  Fetched {len(rows)} rows from {table}")

    fixed = 0
    errors = 0

    for row in rows:
        row_id = row[id_col]
        label = row.get(label_col, row_id)
        updates: Dict[str, Any] = {}

        for field in jsonb_fields:
            val = row.get(field)
            if val is None:
                continue
            needs_fix, corrected = try_deserialize(val)
            if needs_fix:
                updates[field] = corrected

        if not updates:
            continue

        field_names = list(updates.keys())
        if dry_run:
            print(f"  [DRY RUN] Would fix {label}: {field_names}")
            for f in field_names:
                original = row.get(f, "")
                preview = str(original)[:80]
                print(f"    {f}: {preview} -> (deserialized)")
            fixed += 1
        else:
            ok = patch_row(client, table, row_id, updates, id_col)
            if ok:
                print(f"  FIXED {label}: {field_names}")
                fixed += 1
            else:
                print(f"  ERROR fixing {label}")
                errors += 1

    return len(rows), fixed, errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Repair double-serialized JSONB fields in Supabase"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without writing to DB",
    )
    args = parser.parse_args()

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)

    print("=" * 70)
    print("  Repair Double-Serialized JSONB Fields")
    print("=" * 70)
    print(f"  Dry run: {args.dry_run}")
    print()

    with httpx.Client(timeout=30) as client:
        # ── Merchant pages ────────────────────────────────────────────────
        print("Repairing merchant JSONB fields ...")
        print("  (filtering to rows with page content)")
        m_checked, m_fixed, m_errors = repair_table(
            client=client,
            table="merchants",
            id_col="id",
            label_col="name",
            jsonb_fields=MERCHANT_JSONB_FIELDS,
            filters={
                "page_hero_headline": "neq.",
            },
            dry_run=args.dry_run,
        )

        print()

        # ── DMA pages ─────────────────────────────────────────────────────
        print("Repairing DMA JSONB fields ...")
        d_checked, d_fixed, d_errors = repair_table(
            client=client,
            table="dma_page_content",
            id_col="id",
            label_col="display_name",
            jsonb_fields=DMA_JSONB_FIELDS,
            filters=None,
            dry_run=args.dry_run,
        )

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    print(f"  Merchants: {m_checked} checked, {m_fixed} fixed, {m_errors} errors")
    print(f"  DMA pages: {d_checked} checked, {d_fixed} fixed, {d_errors} errors")
    total_fixed = m_fixed + d_fixed
    total_errors = m_errors + d_errors
    print(f"  Total:     {total_fixed} fixed, {total_errors} errors")
    if args.dry_run:
        print("  (DRY RUN - no changes written to DB)")
    print()

    # Verification queries
    print("Verification queries (run in Supabase SQL Editor):")
    print("  SELECT jsonb_typeof(faq_json) FROM dma_page_content LIMIT 3;")
    print("  -- Expected: 'array'")
    print()
    print("  SELECT jsonb_typeof(page_faq_json) FROM merchants")
    print("    WHERE page_hero_headline IS NOT NULL AND page_hero_headline != '' LIMIT 3;")
    print("  -- Expected: 'array'")
    print()
    print("Done.")


if __name__ == "__main__":
    main()
