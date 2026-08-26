#!/usr/bin/env python3
"""
Consolidate duplicate merchants across multiple ingestion runs in the
Senior Discount Discovery Pipeline Google Sheet.

Reads all rows from the Merchant Review tab, runs fuzzy matching to find
near-duplicate merchants (e.g. "Denny's" vs "Dennys", "Rite-Aid" vs "Rite Aid"),
marks inferior duplicates, merges best data into the surviving row, and adds
a Sources Count column.

Usage:
    python scripts/consolidate_discount_sheet.py --sheet-id "SHEET_ID"
    python scripts/consolidate_discount_sheet.py --sheet-id "SHEET_ID" --dry-run
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials
from googleapiclient.discovery import build as build_google

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

# Header columns in Merchant Review tab (0-indexed)
COL_STATUS = 0        # A: Status
COL_ACTION = 1        # B: Action
COL_NAME = 2          # C: Merchant Name
COL_SOURCE_URL = 3    # D: Source URL
COL_CATEGORY = 4      # E: Category
COL_CATEGORY_ID = 5   # F: category_id
COL_IS_NATIONAL = 6   # G: is_national
COL_DISCOUNT_VAL = 7  # H: Discount Value
COL_DISCOUNT_TXT = 8  # I: Discount Text
COL_REQUIREMENT = 9   # J: Requirement
COL_DISCOUNT_TYPE = 10  # K: Discount Type
COL_CONDITIONS = 11   # L: Conditions
COL_VERIF_URL = 12    # M: Verification URL
COL_VERIF_SOURCE = 13  # N: Verification Source
COL_CONFIDENCE = 14   # O: Confidence
COL_PAGE_SLUG = 15    # P: page_slug
COL_DB_CUR_VAL = 16   # Q: DB Current Value
COL_DB_CUR_REQ = 17   # R: DB Current Requirement
COL_DIFF = 18         # S: Diff?
COL_EXISTING_ID = 19  # T: Existing Merchant ID
COL_NOTES = 20        # U: Notes
COL_SOURCES_COUNT = 21  # V: Sources Count (new column)

NUM_ORIGINAL_COLS = 21  # A through U

# Source authority ranking (lower = more authoritative)
SOURCE_AUTHORITY: Dict[str, int] = {
    "ncoa.org": 1,
    "seniorliving.org": 2,
    "theseniorlist.com": 3,
    "askchapter.org": 4,
    "caringseniorservice.com": 5,
}


# ---------------------------------------------------------------------------
# Helpers (reused from discover_senior_discounts.py)
# ---------------------------------------------------------------------------
def normalize_name(name: str) -> str:
    """Normalize merchant name for fuzzy matching."""
    s = name.lower().strip()
    for suffix in [
        " inc.", " inc", " llc", " corp.", " corp", " co.",
        " company", " stores", " store", "'s", "\u2019s",
    ]:
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    s = s.replace("'", "").replace("\u2019", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fuzzy_match(name1: str, name2: str) -> float:
    """Return 0-1 similarity between two merchant names."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if n1 == n2:
        return 1.0
    return SequenceMatcher(None, n1, n2).ratio()


def get_source_domain(url: str) -> str:
    """Extract domain from a source URL for authority ranking."""
    if not url:
        return ""
    # Strip protocol and www
    domain = url.lower()
    for prefix in ["https://", "http://", "www."]:
        if domain.startswith(prefix):
            domain = domain[len(prefix):]
    # Take just the domain part
    domain = domain.split("/")[0]
    return domain


def source_authority_score(url: str) -> int:
    """Return authority score for a source URL (lower = better)."""
    domain = get_source_domain(url)
    for key, score in SOURCE_AUTHORITY.items():
        if key in domain:
            return score
    return 99  # Unknown source


def row_completeness(row: List[str]) -> int:
    """Score how complete a row is (count of non-empty fields in key columns)."""
    key_cols = [
        COL_DISCOUNT_VAL, COL_DISCOUNT_TXT, COL_REQUIREMENT,
        COL_CONDITIONS, COL_DISCOUNT_TYPE, COL_VERIF_URL,
    ]
    score = 0
    for col in key_cols:
        if col < len(row) and row[col].strip():
            score += 1
    return score


def safe_get(row: List[str], idx: int) -> str:
    """Safely get a value from a row, returning empty string if out of bounds."""
    if idx < len(row):
        return row[idx]
    return ""


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------
def find_duplicate_groups(
    rows: List[List[str]],
    threshold: float = 0.85,
) -> List[List[int]]:
    """
    Find groups of rows with similar merchant names.
    Returns list of groups, each group is a list of row indices (0-based, data rows only).
    Skips rows already marked as Duplicate or Defunct.
    """
    # Build list of (index, name) for active rows
    active: List[Tuple[int, str]] = []
    for i, row in enumerate(rows):
        status = safe_get(row, COL_STATUS).strip()
        if status in ("Duplicate", "Defunct"):
            continue
        name = safe_get(row, COL_NAME).strip()
        if name:
            active.append((i, name))

    # Union-Find for grouping
    parent: Dict[int, int] = {idx: idx for idx, _ in active}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    # Compare all pairs (O(n^2) but n is small, ~200-300 rows max)
    for i in range(len(active)):
        for j in range(i + 1, len(active)):
            idx_i, name_i = active[i]
            idx_j, name_j = active[j]
            score = fuzzy_match(name_i, name_j)
            if score >= threshold:
                union(idx_i, idx_j)

    # Build groups
    groups_map: Dict[int, List[int]] = defaultdict(list)
    for idx, _ in active:
        root = find(idx)
        groups_map[root].append(idx)

    # Only return groups with 2+ members
    return [g for g in groups_map.values() if len(g) > 1]


def pick_winner(rows: List[List[str]], group: List[int]) -> int:
    """
    Pick the best row in a duplicate group.
    Priority: most complete data, then best source authority.
    Returns the winning row index.
    """
    scored = []
    for idx in group:
        row = rows[idx]
        completeness = row_completeness(row)
        authority = source_authority_score(safe_get(row, COL_SOURCE_URL))
        # Higher completeness is better, lower authority score is better
        # Use (completeness, -authority) so we can sort descending
        scored.append((completeness, -authority, idx))

    scored.sort(reverse=True)
    return scored[0][2]


def merge_data(winner_row: List[str], donor_row: List[str]) -> bool:
    """
    Merge missing data from donor_row into winner_row (in-place).
    Returns True if any data was merged.
    """
    changed = False
    # Fields that can be merged from donor if winner is empty
    mergeable_cols = [
        COL_DISCOUNT_VAL, COL_DISCOUNT_TXT, COL_REQUIREMENT,
        COL_CONDITIONS, COL_DISCOUNT_TYPE,
    ]
    for col in mergeable_cols:
        winner_val = safe_get(winner_row, col).strip()
        donor_val = safe_get(donor_row, col).strip()
        if not winner_val and donor_val:
            # Extend row if needed
            while len(winner_row) <= col:
                winner_row.append("")
            winner_row[col] = donor_val
            changed = True

    # Prefer higher-authority verification URL
    winner_authority = source_authority_score(safe_get(winner_row, COL_VERIF_URL))
    donor_authority = source_authority_score(safe_get(donor_row, COL_VERIF_URL))
    donor_verif = safe_get(donor_row, COL_VERIF_URL).strip()
    if donor_verif and donor_authority < winner_authority:
        while len(winner_row) <= COL_VERIF_URL:
            winner_row.append("")
        winner_row[COL_VERIF_URL] = donor_verif
        winner_row[COL_VERIF_SOURCE] = safe_get(donor_row, COL_VERIF_SOURCE)
        winner_row[COL_CONFIDENCE] = safe_get(donor_row, COL_CONFIDENCE)
        changed = True

    return changed


def consolidate(
    rows: List[List[str]],
    groups: List[List[int]],
) -> Tuple[int, int]:
    """
    Process duplicate groups: pick winners, merge data, mark duplicates.
    Modifies rows in-place.
    Returns (num_duplicates_marked, num_merges).
    """
    num_dupes = 0
    num_merges = 0

    for group in groups:
        winner_idx = pick_winner(rows, group)
        winner_row = rows[winner_idx]

        # Collect unique source URLs across the group
        source_urls = set()
        for idx in group:
            url = safe_get(rows[idx], COL_SOURCE_URL).strip()
            if url:
                source_urls.add(url)

        # Set Sources Count on winner
        while len(winner_row) <= COL_SOURCES_COUNT:
            winner_row.append("")
        winner_row[COL_SOURCES_COUNT] = str(len(source_urls))

        # Process duplicates (non-winners)
        for idx in group:
            if idx == winner_idx:
                continue

            donor_row = rows[idx]

            # Merge data from donor into winner
            if merge_data(winner_row, donor_row):
                num_merges += 1

            # Mark donor as Duplicate
            while len(donor_row) <= COL_SOURCES_COUNT:
                donor_row.append("")
            donor_row[COL_STATUS] = "Duplicate"
            # Note: row numbers in sheet are 1-indexed with header
            donor_row[COL_NOTES] = f"Duplicate of row {winner_idx + 2}"
            donor_row[COL_SOURCES_COUNT] = ""  # Only winner gets count
            num_dupes += 1

    # Set Sources Count = 1 for non-duplicate rows that aren't in any group
    grouped_indices = set()
    for group in groups:
        grouped_indices.update(group)

    for i, row in enumerate(rows):
        if i not in grouped_indices:
            status = safe_get(row, COL_STATUS).strip()
            if status not in ("Duplicate", "Defunct"):
                while len(row) <= COL_SOURCES_COUNT:
                    row.append("")
                if not row[COL_SOURCES_COUNT]:
                    row[COL_SOURCES_COUNT] = "1"

    return num_dupes, num_merges


# ---------------------------------------------------------------------------
# Google Sheets I/O
# ---------------------------------------------------------------------------
def read_all_rows(sheets_service: Any, sheet_id: str) -> List[List[str]]:
    """Read all data rows from Merchant Review tab (excluding header)."""
    result = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=sheet_id,
            range="Merchant Review!A:V",
        )
        .execute()
    )
    values = result.get("values", [])
    if len(values) <= 1:
        return []
    return values[1:]  # Skip header


def write_back_rows(
    sheets_service: Any,
    sheet_id: str,
    rows: List[List[str]],
) -> None:
    """Write all data rows back to the sheet (starting at row 2)."""
    # Ensure all rows have the same number of columns
    max_cols = COL_SOURCES_COUNT + 1
    padded = []
    for row in rows:
        padded_row = list(row)
        while len(padded_row) < max_cols:
            padded_row.append("")
        padded.append(padded_row[:max_cols])

    # Write the Sources Count header
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Merchant Review!V1",
        valueInputOption="RAW",
        body={"values": [["Sources Count"]]},
    ).execute()

    # Write all data rows
    range_str = f"Merchant Review!A2:V{len(padded) + 1}"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_str,
        valueInputOption="RAW",
        body={"values": padded},
    ).execute()


def color_duplicate_rows(
    sheets_service: Any,
    sheet_id: str,
    rows: List[List[str]],
) -> None:
    """Apply gray background to Duplicate rows."""
    requests = []
    gray_bg = {"red": 0.85, "green": 0.85, "blue": 0.85}
    num_cols = COL_SOURCES_COUNT + 1

    for idx, row in enumerate(rows):
        status = safe_get(row, COL_STATUS).strip()
        if status == "Duplicate":
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": idx + 1,  # +1 for header
                            "endRowIndex": idx + 2,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        },
                        "cell": {"userEnteredFormat": {"backgroundColor": gray_bg}},
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }
            )

    if requests:
        for i in range(0, len(requests), 500):
            batch = requests[i : i + 500]
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=sheet_id, body={"requests": batch}
            ).execute()


def format_sources_count_header(
    sheets_service: Any,
    sheet_id: str,
) -> None:
    """Format the Sources Count header to match the existing header style."""
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": COL_SOURCES_COUNT,
                    "endColumnIndex": COL_SOURCES_COUNT + 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColorStyle": {
                                "rgbColor": {"red": 1, "green": 1, "blue": 1}
                            },
                        },
                        "backgroundColor": {
                            "red": 0.16,
                            "green": 0.22,
                            "blue": 0.43,
                        },
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        }
    ]
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": requests}
    ).execute()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consolidate duplicate merchants across ingestion runs"
    )
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying the sheet",
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.85,
        help="Fuzzy match threshold (0-1, default: 0.85)",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("  Senior Discount Sheet Consolidation")
    print("=" * 70)
    print(f"  Sheet ID:   {args.sheet_id}")
    print(f"  Dry run:    {args.dry_run}")
    print(f"  Threshold:  {args.threshold}")
    print()

    # Initialize Google Sheets
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    sheets_svc = build_google("sheets", "v4", credentials=creds)

    # Step 1: Read all rows
    print("STEP 1: Reading all rows from Merchant Review tab ...")
    rows = read_all_rows(sheets_svc, args.sheet_id)
    if not rows:
        print("  No data rows found. Nothing to consolidate.")
        return
    print(f"  Found {len(rows)} data rows")

    # Count current statuses
    status_counts: Dict[str, int] = defaultdict(int)
    for row in rows:
        status_counts[safe_get(row, COL_STATUS).strip()] += 1
    for status, count in sorted(status_counts.items()):
        print(f"    {status}: {count}")

    # Step 2: Find duplicate groups
    print("\nSTEP 2: Finding duplicate groups (threshold={:.2f}) ...".format(args.threshold))
    groups = find_duplicate_groups(rows, threshold=args.threshold)
    if not groups:
        print("  No duplicates found. Sheet is clean.")
        # Still add Sources Count column with 1 for all rows
        if not args.dry_run:
            for row in rows:
                while len(row) <= COL_SOURCES_COUNT:
                    row.append("")
                if not row[COL_SOURCES_COUNT]:
                    row[COL_SOURCES_COUNT] = "1"
            write_back_rows(sheets_svc, args.sheet_id, rows)
            format_sources_count_header(sheets_svc, args.sheet_id)
            print("  Added Sources Count column (all rows = 1).")
        return

    print(f"  Found {len(groups)} duplicate groups:")
    for group in groups:
        names = [safe_get(rows[i], COL_NAME) for i in group]
        sources = [get_source_domain(safe_get(rows[i], COL_SOURCE_URL)) for i in group]
        print(f"    Group: {names}")
        print(f"      Sources: {sources}")

    # Step 3: Consolidate
    print(f"\nSTEP 3: Consolidating duplicates ...")
    num_dupes, num_merges = consolidate(rows, groups)
    print(f"  Duplicates marked: {num_dupes}")
    print(f"  Data merges: {num_merges}")

    # Step 4: Write back (or preview)
    if args.dry_run:
        print("\nDRY RUN - No changes written to sheet.")
        print("\nPreview of changes:")
        for group in groups:
            winner_idx = pick_winner(rows, group)
            winner_name = safe_get(rows[winner_idx], COL_NAME)
            sources_count = safe_get(rows[winner_idx], COL_SOURCES_COUNT)
            print(f"\n  Winner: {winner_name} (row {winner_idx + 2}, {sources_count} sources)")
            for idx in group:
                if idx != winner_idx:
                    dupe_name = safe_get(rows[idx], COL_NAME)
                    dupe_source = get_source_domain(safe_get(rows[idx], COL_SOURCE_URL))
                    print(f"    Duplicate: {dupe_name} (row {idx + 2}, from {dupe_source})")
    else:
        print("\nSTEP 4: Writing changes to sheet ...")
        write_back_rows(sheets_svc, args.sheet_id, rows)
        format_sources_count_header(sheets_svc, args.sheet_id)
        print("  Data written successfully.")

        print("\nSTEP 5: Applying color coding to duplicate rows ...")
        color_duplicate_rows(sheets_svc, args.sheet_id, rows)
        print("  Color coding applied.")

    # Summary
    print()
    print("=" * 70)
    print("  CONSOLIDATION COMPLETE")
    print("=" * 70)
    print(f"  Total rows:         {len(rows)}")
    print(f"  Duplicate groups:   {len(groups)}")
    print(f"  Rows marked dupe:   {num_dupes}")
    print(f"  Data merges:        {num_merges}")
    unique = len(rows) - num_dupes
    print(f"  Unique merchants:   {unique}")
    if args.dry_run:
        print()
        print("  Re-run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
