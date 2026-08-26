#!/usr/bin/env python3
"""
Investigate and resolve duplicate active merchant pairs in Supabase merchants table.

Duplicates: Albertsons, Bubba Gump Shrimp Co., Chart House

For each pair:
  1. Fetch full data for both rows
  2. Count store_locations and active discounts_v2 for each
  3. Compare all fields side by side
  4. Determine winner (keep) vs loser (deactivate)
  5. Handle store_locations: reassign unique ones, delete overlapping duplicates
  6. Handle discounts: reassign unique ones, deactivate overlapping duplicates
  7. Deactivate the loser merchant
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

SUPABASE_URL = os.environ["SUPABASE_URL"]
SERVICE_KEY = os.environ["SUPABASE_SERVICE_ROLE_KEY"]

HEADERS = {
    "apikey": SERVICE_KEY,
    "Authorization": f"Bearer {SERVICE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Duplicate search patterns (use spaces, not +)
DUPLICATE_QUERIES = [
    ("Albertsons", "*albertsons*"),
    ("Bubba Gump Shrimp Co.", "*bubba gump*"),
    ("Chart House", "*chart house*"),
]

# Fields that indicate page content is populated
PAGE_CONTENT_FIELDS = [
    "page_hero_headline",
    "page_hero_subhead",
    "page_seo_title",
    "page_seo_description",
    "page_about_md",
    "page_how_to_save_md",
    "page_tips_md",
    "page_faq_json",
    "page_faq_md",
    "page_direct_answer",
    "page_protection_note_md",
    "page_seo_keywords",
    "page_related_merchant_ids",
    "page_related_guide_slugs",
    "page_related_protection_slugs",
    "page_source",
    "page_review_notes",
    "page_slug",
]


def rest_url(table: str) -> str:
    return f"{SUPABASE_URL}/rest/v1/{table}"


# ---------------------------------------------------------------------------
# Fetchers
# ---------------------------------------------------------------------------
def fetch_merchants(client: httpx.Client, pattern: str) -> List[Dict[str, Any]]:
    """Fetch active merchants matching an ilike pattern."""
    resp = client.get(
        rest_url("merchants"),
        params={
            "is_active": "eq.true",
            "name": f"ilike.{pattern}",
            "select": "*",
        },
    )
    resp.raise_for_status()
    return resp.json()


def fetch_store_locations(
    client: httpx.Client, merchant_id: int
) -> List[Dict[str, Any]]:
    """Fetch all store_locations for a merchant (id and location_id)."""
    resp = client.get(
        rest_url("store_locations"),
        params={
            "merchant_id": f"eq.{merchant_id}",
            "select": "id,location_id",
        },
    )
    resp.raise_for_status()
    return resp.json()


def fetch_active_discounts(
    client: httpx.Client, merchant_id: int
) -> List[Dict[str, Any]]:
    """Fetch all active discounts for a merchant."""
    resp = client.get(
        rest_url("discounts_v2"),
        params={
            "merchant_id": f"eq.{merchant_id}",
            "active": "eq.true",
            "select": "id,name,details,discount_value,discount_type,requirement,store_location_id",
        },
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Page content scoring
# ---------------------------------------------------------------------------
def page_content_score(merchant: Dict[str, Any]) -> int:
    """Count how many page-content fields are populated (non-null, non-empty)."""
    score = 0
    for field in PAGE_CONTENT_FIELDS:
        val = merchant.get(field)
        if val is not None and val != "" and val != "null" and val != []:
            score += 1
    return score


# ---------------------------------------------------------------------------
# Decision logic
# ---------------------------------------------------------------------------
def pick_winner(
    a: Dict[str, Any],
    b: Dict[str, Any],
    a_stores: int,
    b_stores: int,
    a_discounts: int,
    b_discounts: int,
) -> Tuple[Dict[str, Any], Dict[str, Any], str]:
    """Return (winner, loser, reason)."""
    reasons = []

    a_page = page_content_score(a)
    b_page = page_content_score(b)

    a_score = 0
    b_score = 0

    if a_stores > b_stores:
        a_score += 2
        reasons.append("A has more store locations (%d vs %d)" % (a_stores, b_stores))
    elif b_stores > a_stores:
        b_score += 2
        reasons.append("B has more store locations (%d vs %d)" % (b_stores, a_stores))

    if a_discounts > b_discounts:
        a_score += 2
        reasons.append("A has more active discounts (%d vs %d)" % (a_discounts, b_discounts))
    elif b_discounts > a_discounts:
        b_score += 2
        reasons.append("B has more active discounts (%d vs %d)" % (b_discounts, a_discounts))

    if a_page > b_page:
        a_score += 3
        reasons.append("A has more page content (%d vs %d fields)" % (a_page, b_page))
    elif b_page > a_page:
        b_score += 3
        reasons.append("B has more page content (%d vs %d fields)" % (b_page, a_page))

    if a.get("is_national") and not b.get("is_national"):
        a_score += 1
        reasons.append("A is_national=true")
    elif b.get("is_national") and not a.get("is_national"):
        b_score += 1
        reasons.append("B is_national=true")

    # Tiebreaker: lower ID (older record)
    if a_score == b_score:
        if a["id"] < b["id"]:
            a_score += 1
            reasons.append("Tiebreaker: A has lower ID (%d vs %d)" % (a["id"], b["id"]))
        else:
            b_score += 1
            reasons.append("Tiebreaker: B has lower ID (%d vs %d)" % (b["id"], a["id"]))

    if a_score >= b_score:
        return a, b, " | ".join(reasons)
    else:
        return b, a, " | ".join(reasons)


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------
def handle_store_locations(
    client: httpx.Client,
    winner_id: int,
    loser_id: int,
) -> Tuple[int, int, int]:
    """
    Handle store_locations for a duplicate pair.

    Returns (reassigned_count, deleted_count, total_loser_count).
    - Reassign loser locations whose location_id is NOT in the winner
    - Delete loser locations whose location_id IS already in the winner (true dups)
    """
    winner_locs = fetch_store_locations(client, winner_id)
    loser_locs = fetch_store_locations(client, loser_id)

    if not loser_locs:
        return 0, 0, 0

    winner_location_ids: Set[Optional[int]] = {r["location_id"] for r in winner_locs}

    # Split loser locations into overlap vs unique
    overlap_ids: List[int] = []
    unique_ids: List[int] = []
    for r in loser_locs:
        if r["location_id"] in winner_location_ids:
            overlap_ids.append(r["id"])
        else:
            unique_ids.append(r["id"])

    reassigned = 0
    deleted = 0

    # Reassign unique locations to winner
    if unique_ids:
        for sl_id in unique_ids:
            resp = client.patch(
                rest_url("store_locations"),
                params={"id": f"eq.{sl_id}"},
                json={"merchant_id": winner_id},
            )
            resp.raise_for_status()
            reassigned += 1

    # Delete overlapping locations (they already exist under the winner)
    if overlap_ids:
        # Batch delete using IN filter
        id_list = ",".join(str(x) for x in overlap_ids)
        resp = client.delete(
            rest_url("store_locations"),
            params={"id": f"in.({id_list})"},
        )
        resp.raise_for_status()
        deleted = len(overlap_ids)

    return reassigned, deleted, len(loser_locs)


def handle_discounts(
    client: httpx.Client,
    winner_id: int,
    loser_id: int,
) -> Tuple[int, int, int]:
    """
    Handle discounts_v2 for a duplicate pair.

    Returns (reassigned_count, deactivated_count, total_loser_count).
    - Check if discount_value+discount_type overlap
    - Reassign unique discounts to winner
    - Deactivate overlapping loser discounts
    """
    winner_discs = fetch_active_discounts(client, winner_id)
    loser_discs = fetch_active_discounts(client, loser_id)

    if not loser_discs:
        return 0, 0, 0

    # Build a set of (discount_value, discount_type) for winner
    winner_keys: Set[Tuple[Optional[str], Optional[str]]] = set()
    for d in winner_discs:
        winner_keys.add((d.get("discount_value"), d.get("discount_type")))

    reassigned = 0
    deactivated = 0

    for d in loser_discs:
        key = (d.get("discount_value"), d.get("discount_type"))
        if key in winner_keys:
            # Duplicate discount - deactivate it
            resp = client.patch(
                rest_url("discounts_v2"),
                params={"id": "eq.%d" % d["id"]},
                json={"active": False},
            )
            resp.raise_for_status()
            deactivated += 1
        else:
            # Unique discount - reassign to winner
            resp = client.patch(
                rest_url("discounts_v2"),
                params={"id": "eq.%d" % d["id"]},
                json={"merchant_id": winner_id},
            )
            resp.raise_for_status()
            reassigned += 1

    return reassigned, deactivated, len(loser_discs)


def deactivate_merchant(client: httpx.Client, merchant_id: int) -> Dict[str, Any]:
    resp = client.patch(
        rest_url("merchants"),
        params={"id": "eq.%d" % merchant_id},
        json={"is_active": False},
    )
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def print_separator(char: str = "=", width: int = 110) -> None:
    print(char * width)


def print_comparison(
    label: str,
    a: Dict[str, Any],
    b: Dict[str, Any],
    a_stores: int,
    b_stores: int,
    a_discounts: int,
    b_discounts: int,
) -> None:
    print_separator()
    print("  DUPLICATE PAIR: %s" % label)
    print_separator()

    a_page = page_content_score(a)
    b_page = page_content_score(b)

    all_keys = sorted(set(list(a.keys()) + list(b.keys())))

    col_a = "ROW A (id=%d)" % a["id"]
    col_b = "ROW B (id=%d)" % b["id"]
    print()
    print("  %-35s %-40s %-40s" % ("FIELD", col_a, col_b))
    print("  %-35s %-40s %-40s" % ("-" * 35, "-" * 40, "-" * 40))

    for key in all_keys:
        val_a = a.get(key)
        val_b = b.get(key)
        str_a = _truncate(str(val_a), 38) if val_a is not None else "(null)"
        str_b = _truncate(str(val_b), 38) if val_b is not None else "(null)"
        marker = " <-- DIFF" if val_a != val_b else ""
        print("  %-35s %-40s %-40s%s" % (key, str_a, str_b, marker))

    print()
    print("  --- Relationship Counts ---")
    print("  %-35s %-40s %-40s" % ("Store Locations", a_stores, b_stores))
    print("  %-35s %-40s %-40s" % ("Active Discounts", a_discounts, b_discounts))
    print("  %-35s %-40s %-40s" % ("Page Content Score", a_page, b_page))
    print()


def _truncate(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    print()
    print_separator()
    print("  MERCHANT DUPLICATE RESOLUTION SCRIPT")
    print_separator()
    print("  Supabase: %s" % SUPABASE_URL)
    print()

    summary: List[str] = []

    with httpx.Client(headers=HEADERS, timeout=30) as client:
        for label, pattern in DUPLICATE_QUERIES:
            merchants = fetch_merchants(client, pattern)

            if len(merchants) < 2:
                msg = "[%s] Only %d active row(s) found - no duplicate to resolve." % (label, len(merchants))
                print("  %s" % msg)
                summary.append("%s: No duplicate found (%d active row(s))" % (label, len(merchants)))
                continue

            if len(merchants) > 2:
                print("  [%s] WARNING: %d active rows found (expected 2). Processing first 2." % (label, len(merchants)))

            a, b = merchants[0], merchants[1]

            # Fetch relationship counts
            a_store_locs = fetch_store_locations(client, a["id"])
            b_store_locs = fetch_store_locations(client, b["id"])
            a_stores = len(a_store_locs)
            b_stores = len(b_store_locs)

            a_disc_list = fetch_active_discounts(client, a["id"])
            b_disc_list = fetch_active_discounts(client, b["id"])
            a_discounts = len(a_disc_list)
            b_discounts = len(b_disc_list)

            # Check location overlap
            a_loc_ids = {r["location_id"] for r in a_store_locs}
            b_loc_ids = {r["location_id"] for r in b_store_locs}
            overlap_locs = a_loc_ids & b_loc_ids
            only_a_locs = a_loc_ids - b_loc_ids
            only_b_locs = b_loc_ids - a_loc_ids

            # Print comparison
            print_comparison(label, a, b, a_stores, b_stores, a_discounts, b_discounts)

            # Print location overlap analysis
            print("  --- Store Location Overlap Analysis ---")
            print("  Overlapping location_ids: %d" % len(overlap_locs))
            print("  Only in A (id=%d): %d" % (a["id"], len(only_a_locs)))
            print("  Only in B (id=%d): %d" % (b["id"], len(only_b_locs)))
            print()

            # Print discount analysis
            print("  --- Discount Analysis ---")
            for d in a_disc_list:
                print("    A (id=%d): discount_id=%d, value=%s, type=%s, name=%s" % (
                    a["id"], d["id"], d.get("discount_value", "?"), d.get("discount_type", "?"), d.get("name", "?")))
            for d in b_disc_list:
                print("    B (id=%d): discount_id=%d, value=%s, type=%s, name=%s" % (
                    b["id"], d["id"], d.get("discount_value", "?"), d.get("discount_type", "?"), d.get("name", "?")))
            print()

            # Pick winner
            winner, loser, reason = pick_winner(
                a, b, a_stores, b_stores, a_discounts, b_discounts
            )

            print("  DECISION: Keep id=%d (name=%s)" % (winner["id"], winner["name"]))
            print("            Deactivate id=%d (name=%s)" % (loser["id"], loser["name"]))
            print("  REASON:   %s" % reason)
            print()

            # Handle store_locations
            actions_taken = []

            sl_reassigned, sl_deleted, sl_total = handle_store_locations(
                client, winner["id"], loser["id"]
            )
            if sl_total > 0:
                msg = "Store locations (loser id=%d): %d total, %d reassigned to winner, %d deleted (duplicates)" % (
                    loser["id"], sl_total, sl_reassigned, sl_deleted
                )
                print("  ACTION: %s" % msg)
                actions_taken.append(msg)
            else:
                msg = "No store_locations on loser (id=%d)" % loser["id"]
                print("  ACTION: %s" % msg)
                actions_taken.append(msg)

            # Handle discounts
            d_reassigned, d_deactivated, d_total = handle_discounts(
                client, winner["id"], loser["id"]
            )
            if d_total > 0:
                msg = "Discounts (loser id=%d): %d total, %d reassigned to winner, %d deactivated (duplicates)" % (
                    loser["id"], d_total, d_reassigned, d_deactivated
                )
                print("  ACTION: %s" % msg)
                actions_taken.append(msg)
            else:
                msg = "No active discounts on loser (id=%d)" % loser["id"]
                print("  ACTION: %s" % msg)
                actions_taken.append(msg)

            # Deactivate loser
            result = deactivate_merchant(client, loser["id"])
            deactivated_name = result[0]["name"] if result else loser["name"]
            msg = "Deactivated merchant id=%d (name=%s)" % (loser["id"], deactivated_name)
            print("  ACTION: %s" % msg)
            actions_taken.append(msg)

            # Verify
            verify = fetch_merchants(client, pattern)
            active_count = len(verify)
            print()
            print("  VERIFY: %d active row(s) remaining for '%s'" % (active_count, label))
            if active_count == 1:
                print("  SUCCESS: Duplicate resolved. Surviving record: id=%d" % verify[0]["id"])
            else:
                print("  WARNING: Expected 1 active row, found %d" % active_count)

            summary.append(
                "%s: Kept id=%d, deactivated id=%d (%s)" % (
                    label, winner["id"], loser["id"], "; ".join(actions_taken)
                )
            )
            print()

    # Final summary
    print_separator()
    print("  FINAL SUMMARY")
    print_separator()
    for line in summary:
        print("  - %s" % line)
    print()


if __name__ == "__main__":
    main()
