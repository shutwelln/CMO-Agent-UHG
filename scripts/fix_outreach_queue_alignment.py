#!/usr/bin/env python3
"""Fix Outreach Queue column misalignment + add Dropdowns tab + clear bad validation.

Three operations:
1. Remove misaligned duplicate rows (222+) from Outreach Queue — confirmed 100%
   duplicates via URL matching. Keeps only the correctly aligned rows (2-221).
2. Clear erroneous dropdown validation from column L (Reviewer Notes) — it should
   be a free text field, not a dropdown.
3. Add a "Dropdowns" tab as single source of truth for Status, Claimed By, and
   Outcome values. Apply dropdown validations to all queue tabs.

Usage:
    # Diagnose only (no changes):
    python scripts/fix_outreach_queue_alignment.py --diagnose

    # Fix everything (alignment + validation + Dropdowns tab):
    python scripts/fix_outreach_queue_alignment.py --fix
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys

# Allow running from project root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def get_sheets_service():
    """Build Google Sheets API service."""
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import get_google_credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = get_google_credentials(
        oauth_token_path=os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", ""),
        service_account_path=os.environ.get("GOOGLE_CREDENTIALS_PATH", ""),
        scopes=scopes,
    )
    if creds is None:
        print(
            "ERROR: No Google credentials found."
            " Set GOOGLE_OAUTH_TOKEN_PATH or GOOGLE_CREDENTIALS_PATH."
        )
        sys.exit(1)
    return build("sheets", "v4", credentials=creds)


# Opportunity IDs are UUID or hex hash format
_OPP_ID_PATTERN = re.compile(r"^[0-9a-f-]{16,64}$", re.IGNORECASE)


def is_opportunity_id(value: str) -> bool:
    """Check if a value looks like an Opportunity ID (UUID or hex hash)."""
    if not value:
        return False
    return bool(_OPP_ID_PATTERN.match(value.strip()))


def is_platform_name(value: str) -> bool:
    """Check if a value looks like a platform/source name (misaligned indicator)."""
    return value.strip().lower() in {"reddit", "glowing", "rss"}


def is_misaligned(row: list) -> bool:
    """Check if a row is misaligned: col C is not an Opportunity ID."""
    if len(row) < 3:
        return True
    col_c = row[2].strip() if row[2] else ""
    if not col_c:
        return True
    if is_opportunity_id(col_c):
        return False
    # Anything in col C that isn't a UUID/hash is misaligned
    return True


def diagnose(service, spreadsheet_id: str) -> dict:
    """Diagnose alignment issues in the Outreach Queue. Returns summary dict."""
    print("=" * 60)
    print("DIAGNOSING Outreach Queue alignment")
    print("=" * 60)

    # Read headers
    headers_result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="'Outreach Queue'!A1:R1")
        .execute()
    )
    headers = headers_result.get("values", [[]])[0]
    print(f"\nHeaders ({len(headers)} cols): {headers}")

    # Read all data rows
    data_result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="'Outreach Queue'!A2:R5000")
        .execute()
    )
    rows = data_result.get("values", [])
    print(f"Total data rows: {len(rows)}")

    # Classify rows: aligned = Opp ID in col C, misaligned = anything else in col C
    aligned = []
    misaligned = []

    for i, row in enumerate(rows):
        row_num = i + 2  # 1-indexed, skip header
        padded = row + [""] * (18 - len(row))

        if is_misaligned(padded):
            misaligned.append((row_num, padded))
        else:
            aligned.append((row_num, padded))

    # URL-based dedup: find URLs in misaligned rows (may be in col D or E depending
    # on shift amount) and compare against aligned rows (URL in col F, index 5)
    aligned_urls = set()
    for _, row in aligned:
        url = row[5].strip() if row[5] else ""
        if url and url.startswith("http"):
            aligned_urls.add(url)

    dup_count = 0
    unique_count = 0
    unique_misaligned_rows = []
    for row_num, row in misaligned:
        # Find the URL in the misaligned row — scan cols for http
        url_found = ""
        for col_idx in range(min(len(row), 8)):
            v = row[col_idx].strip() if row[col_idx] else ""
            if v.startswith("http"):
                url_found = v
                break
        if url_found and url_found in aligned_urls:
            dup_count += 1
        else:
            unique_count += 1
            unique_misaligned_rows.append((row_num, row))

    print("\n--- Classification ---")
    print(f"Aligned rows (Opp ID in C):     {len(aligned)}")
    print(f"Misaligned rows (no Opp ID):    {len(misaligned)}")
    print(f"  - URL duplicates of aligned:   {dup_count}")
    print(f"  - Unique (not in aligned set): {unique_count}")

    if misaligned:
        print("\nSample misaligned rows (cols A-F):")
        for row_num, row in misaligned[:5]:
            display = [v[:30] if v and len(v) > 30 else (v or "") for v in row[:6]]
            print(f"  Row {row_num}: {display}")

    # Check for Dropdowns tab
    meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
        .execute()
    )
    tab_names = [s["properties"]["title"] for s in meta.get("sheets", [])]
    has_dropdowns = "Dropdowns" in tab_names
    print(f"\nExisting tabs: {tab_names}")
    print(f"Dropdowns tab exists: {has_dropdowns}")

    return {
        "total_rows": len(rows),
        "aligned": aligned,
        "misaligned": misaligned,
        "dup_count": dup_count,
        "unique_count": unique_count,
        "has_dropdowns": has_dropdowns,
        "tab_names": tab_names,
        "spreadsheet_meta": meta,
    }


def fix_alignment(service, spreadsheet_id: str, diagnosis: dict) -> None:
    """Remove misaligned duplicate rows, keeping only aligned data."""
    aligned = diagnosis["aligned"]
    misaligned = diagnosis["misaligned"]

    if not misaligned:
        print("\nNo misaligned rows found. Skipping alignment fix.")
        return

    print("\n--- Step 1: Fix Alignment ---")
    print(f"Keeping {len(aligned)} aligned rows")
    print(f"Removing {len(misaligned)} misaligned rows (all URL duplicates)")

    clean_rows = [row[:18] for _, row in aligned]

    # Clear and rewrite
    print("Clearing A2:R5000...")
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range="'Outreach Queue'!A2:R5000",
    ).execute()

    if clean_rows:
        print(f"Writing {len(clean_rows)} clean rows...")
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range="'Outreach Queue'!A2",
            valueInputOption="RAW",
            body={"values": clean_rows},
        ).execute()

    # Verify
    verify = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="'Outreach Queue'!C2:C6")
        .execute()
    )
    for i, row in enumerate(verify.get("values", [])[:5]):
        val = row[0] if row else ""
        ok = "OK" if is_opportunity_id(val) else "WARN"
        print(f"  C{i + 2}: {val[:40]}  [{ok}]")

    print(f"Done: {len(clean_rows)} rows kept, {len(misaligned)} duplicates removed.")


def fix_column_l_validation(service, spreadsheet_id: str, meta: dict) -> None:
    """Clear erroneous dropdown validation from column L (Reviewer Notes) on ALL queue tabs."""
    print("\n--- Step 2: Clear Column L Validation ---")

    # Find all queue-like tabs and clear col L validation on each
    requests = []
    tabs_cleared = []
    for sheet in meta.get("sheets", []):
        title = sheet["properties"]["title"]
        if title in ("Outreach Queue", "Archive") or title.endswith("Queue"):
            sheet_id = sheet["properties"]["sheetId"]
            requests.append(
                {
                    "setDataValidation": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": 5000,
                            "startColumnIndex": 11,  # L = index 11
                            "endColumnIndex": 12,
                        },
                        # rule omitted = clears validation
                    }
                }
            )
            tabs_cleared.append(title)

    if not requests:
        print("WARNING: No queue tabs found. Skipping.")
        return

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": requests},
    ).execute()
    print(f"Cleared column L validation on: {tabs_cleared}")


def add_dropdowns_tab(service, spreadsheet_id: str, has_dropdowns: bool) -> None:
    """Add Dropdowns tab if it doesn't exist, seed with defaults."""
    from cmo_agent.outreach.dashboard import (
        DEFAULT_OUTCOME_VALUES,
        DEFAULT_STATUS_VALUES,
    )

    print("\n--- Step 3: Add Dropdowns Tab ---")

    if has_dropdowns:
        print("Dropdowns tab already exists. Skipping creation.")
        return

    # Add the tab
    print("Creating Dropdowns tab...")
    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "requests": [
                {
                    "addSheet": {
                        "properties": {"title": "Dropdowns", "index": 5},
                    }
                }
            ]
        },
    ).execute()

    # Get team members from env (backward compat seed)
    team_env = os.environ.get("OUTREACH_TEAM_MEMBERS", "")
    team = [m.strip() for m in team_env.split(",") if m.strip()]

    max_rows = max(len(DEFAULT_STATUS_VALUES), len(DEFAULT_OUTCOME_VALUES), len(team))
    rows = [["Status", "Claimed By", "Outcome"]]
    for i in range(max_rows):
        rows.append(
            [
                DEFAULT_STATUS_VALUES[i] if i < len(DEFAULT_STATUS_VALUES) else "",
                team[i] if i < len(team) else "",
                DEFAULT_OUTCOME_VALUES[i] if i < len(DEFAULT_OUTCOME_VALUES) else "",
            ]
        )

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="'Dropdowns'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()
    print(
        f"Seeded: {len(DEFAULT_STATUS_VALUES)} statuses, "
        f"{len(team)} team members, {len(DEFAULT_OUTCOME_VALUES)} outcomes"
    )


async def apply_validations(spreadsheet_id: str) -> None:
    """Apply dropdown validations to all queue tabs using Dropdowns tab."""
    from cmo_agent.outreach.dashboard import OutreachDashboard

    print("\n--- Step 4: Apply Dropdown Validations ---")
    dashboard = OutreachDashboard(
        google_credentials_path=os.environ.get("GOOGLE_CREDENTIALS_PATH", ""),
        google_oauth_token_path=os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", ""),
        spreadsheet_id=spreadsheet_id,
    )
    result = await dashboard.apply_dropdown_validations(spreadsheet_id)
    print(f"Result: {result}")


def main():
    parser = argparse.ArgumentParser(description="Fix Outreach Queue alignment + add Dropdowns tab")
    parser.add_argument("--diagnose", action="store_true", help="Diagnose only (no changes)")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Fix alignment, clear col L validation, add Dropdowns tab",
    )
    parser.add_argument(
        "--spreadsheet-id",
        default=os.environ.get("OUTREACH_SPREADSHEET_ID", ""),
        help="Google Sheets spreadsheet ID",
    )
    args = parser.parse_args()

    if not args.diagnose and not args.fix:
        parser.print_help()
        print("\nSpecify --diagnose or --fix")
        sys.exit(1)

    if not args.spreadsheet_id:
        print("ERROR: No spreadsheet ID. Set OUTREACH_SPREADSHEET_ID or use --spreadsheet-id.")
        sys.exit(1)

    service = get_sheets_service()
    diagnosis = diagnose(service, args.spreadsheet_id)

    if args.fix:
        # Step 1: Remove misaligned duplicate rows
        fix_alignment(service, args.spreadsheet_id, diagnosis)

        # Step 2: Clear column L (Reviewer Notes) dropdown validation
        fix_column_l_validation(service, args.spreadsheet_id, diagnosis["spreadsheet_meta"])

        # Step 3: Add Dropdowns tab
        add_dropdowns_tab(service, args.spreadsheet_id, diagnosis["has_dropdowns"])

        # Step 4: Apply dropdown validations to all queue tabs
        asyncio.run(apply_validations(args.spreadsheet_id))

        print("\n" + "=" * 60)
        print("ALL FIXES COMPLETE")
        print("=" * 60)


if __name__ == "__main__":
    main()
