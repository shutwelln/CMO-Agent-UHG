#!/usr/bin/env python3
"""
Skip rows in the Saverwell Lead Scanner Google Sheet where Reviewer Notes
indicate the lead should not be posted/responded to.

Updates column M (Status) to "Skipped" for matching rows.
Uses batchUpdate for efficiency (single API call).
"""

import re
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SHEET_ID = "1xnphzSpso_htOP1qX21B1zxx_R-Kvy99MrZ5Jfq2XAA"
TAB_NAME = "Lead Queue"
CREDENTIALS_PATH = "data/saverwell-google-credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column indices (0-based) in the data row
REVIEWER_NOTES_COL = 11  # Column L
STATUS_COL = 12           # Column M

# Negative signal patterns (case-insensitive substring match)
SKIP_PATTERNS = [
    "do not post",
    "not senior",
    "no saverwell",
    "mismatch",
    "off-topic",
    "recommend skip",
    "not relevant",
    "wrong audience",
    "consider skip",
    "not a good fit",
    "not a saverwell",
    "flag: post mismatch",
    "flag: audience mismatch",
    "flag - audience mismatch",
    "not appropriate",
    "skip",
    "no relevant",
    "doesn't align",
    "does not align",
    "no clear",
    "outside saverwell",
    "not aligned",
    "no monetization",
    "too niche",
    "not actionable",
    "generic",
    "low relevance",
    "no direct",
    "unlikely to convert",
    "promotional",
    "spam",
]

# Build a single compiled regex for efficiency
SKIP_REGEX = re.compile(
    "|".join(re.escape(p) for p in SKIP_PATTERNS),
    re.IGNORECASE,
)


def should_skip(reviewer_notes: str) -> bool:
    """Return True if the reviewer notes contain any negative signal pattern."""
    if not reviewer_notes or not reviewer_notes.strip():
        return False
    return bool(SKIP_REGEX.search(reviewer_notes))


def main():
    # Authenticate with service account
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    service = build("sheets", "v4", credentials=creds)
    sheets = service.spreadsheets()

    # Read all data from the Lead Queue tab
    result = sheets.values().get(
        spreadsheetId=SHEET_ID,
        range=f"'{TAB_NAME}'",
        valueRenderOption="UNFORMATTED_VALUE",
    ).execute()

    rows = result.get("values", [])
    if not rows:
        print("No data found in sheet.")
        return

    header = rows[0]
    print(f"Header row: {header}")
    print(f"Total rows (including header): {len(rows)}")
    print(f"Data rows: {len(rows) - 1}")

    # Verify column positions
    if len(header) > REVIEWER_NOTES_COL:
        print(f"Column L (index {REVIEWER_NOTES_COL}): {header[REVIEWER_NOTES_COL]}")
    if len(header) > STATUS_COL:
        print(f"Column M (index {STATUS_COL}): {header[STATUS_COL]}")
    print()

    # Identify rows to update
    updates = []
    skipped_examples = []
    already_skipped = 0

    for i, row in enumerate(rows[1:], start=2):  # start=2: row 1 is header, data starts at row 2
        # Get reviewer notes (column L, index 11)
        reviewer_notes = ""
        if len(row) > REVIEWER_NOTES_COL:
            reviewer_notes = str(row[REVIEWER_NOTES_COL]).strip()

        # Get current status (column M, index 12)
        current_status = ""
        if len(row) > STATUS_COL:
            current_status = str(row[STATUS_COL]).strip()

        if reviewer_notes and should_skip(reviewer_notes):
            # Only update if not already "Skipped"
            if current_status.lower() == "skipped":
                already_skipped += 1
                continue

            # Build the cell reference for column M (Status) in this row
            cell_range = f"'{TAB_NAME}'!M{i}"
            updates.append({
                "range": cell_range,
                "values": [["Skipped"]],
            })

            if len(skipped_examples) < 15:
                notes_display = (reviewer_notes[:80] + "...") if len(reviewer_notes) > 80 else reviewer_notes
                skipped_examples.append(
                    f"  Row {i}: Status '{current_status}' -> 'Skipped' | Notes: {notes_display}"
                )

    print(f"Rows matching skip patterns (need update): {len(updates)}")
    print(f"Rows already 'Skipped': {already_skipped}")

    if skipped_examples:
        print(f"\nFirst {len(skipped_examples)} examples:")
        for ex in skipped_examples:
            print(ex)

    if not updates:
        print("\nNo rows to update.")
        return

    # Execute batch update in a single API call
    body = {
        "valueInputOption": "RAW",
        "data": updates,
    }

    response = sheets.values().batchUpdate(
        spreadsheetId=SHEET_ID,
        body=body,
    ).execute()

    updated_cells = response.get("totalUpdatedCells", 0)
    print(f"\nBatch update complete.")
    print(f"Total rows updated: {len(updates)}")
    print(f"Total cells updated: {updated_cells}")


if __name__ == "__main__":
    main()
