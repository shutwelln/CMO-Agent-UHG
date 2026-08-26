#!/usr/bin/env python3
"""One-time migration: add Dropdowns tab to existing DSDN Outreach Dashboard.

Idempotent — skips if tab already exists. Seeds default Status/Outcome values
and team members from OUTREACH_TEAM_MEMBERS env var. Then applies dropdown
validations to all queue tabs (Outreach Queue, Archive, and any dynamically
created queue tabs).

Usage:
    python scripts/add_dropdowns_tab.py
    python scripts/add_dropdowns_tab.py --spreadsheet-id <ID>
"""

from __future__ import annotations

import argparse
import asyncio
import os
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
            "ERROR: No Google credentials. Set GOOGLE_OAUTH_TOKEN_PATH or GOOGLE_CREDENTIALS_PATH."
        )
        sys.exit(1)
    return build("sheets", "v4", credentials=creds)


def tab_exists(service, spreadsheet_id: str, tab_name: str) -> bool:
    """Check if a tab already exists in the spreadsheet."""
    meta = (
        service.spreadsheets()
        .get(
            spreadsheetId=spreadsheet_id,
            fields="sheets.properties.title",
        )
        .execute()
    )
    for sheet in meta.get("sheets", []):
        if sheet.get("properties", {}).get("title") == tab_name:
            return True
    return False


def add_dropdowns_tab(service, spreadsheet_id: str) -> None:
    """Add the Dropdowns tab if it doesn't exist, seed with defaults."""
    from cmo_agent.outreach.dashboard import (
        DEFAULT_OUTCOME_VALUES,
        DEFAULT_STATUS_VALUES,
    )

    if tab_exists(service, spreadsheet_id, "Dropdowns"):
        print("Dropdowns tab already exists. Skipping creation.")
        return

    # Add the tab
    print("Adding Dropdowns tab...")
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

    # Get team members from env (backward compat)
    team_members_env = os.environ.get("OUTREACH_TEAM_MEMBERS", "")
    team_members = [m.strip() for m in team_members_env.split(",") if m.strip()]

    # Seed data
    max_rows = max(
        len(DEFAULT_STATUS_VALUES),
        len(DEFAULT_OUTCOME_VALUES),
        len(team_members),
    )
    rows = [["Status", "Claimed By", "Outcome"]]
    for i in range(max_rows):
        rows.append(
            [
                DEFAULT_STATUS_VALUES[i] if i < len(DEFAULT_STATUS_VALUES) else "",
                team_members[i] if i < len(team_members) else "",
                DEFAULT_OUTCOME_VALUES[i] if i < len(DEFAULT_OUTCOME_VALUES) else "",
            ]
        )

    print(
        f"Seeding {max_rows} rows: {len(DEFAULT_STATUS_VALUES)} statuses, "
        f"{len(team_members)} team members, {len(DEFAULT_OUTCOME_VALUES)} outcomes"
    )

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="'Dropdowns'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()
    print("Dropdowns tab created and seeded.")


async def apply_validations(spreadsheet_id: str) -> None:
    """Apply dropdown validations to all queue tabs."""
    from cmo_agent.outreach.dashboard import OutreachDashboard

    dashboard = OutreachDashboard(
        google_credentials_path=os.environ.get("GOOGLE_CREDENTIALS_PATH", ""),
        google_oauth_token_path=os.environ.get("GOOGLE_OAUTH_TOKEN_PATH", ""),
        spreadsheet_id=spreadsheet_id,
    )
    result = await dashboard.apply_dropdown_validations(spreadsheet_id)
    print(f"Dropdown validations: {result}")


def main():
    parser = argparse.ArgumentParser(description="Add Dropdowns tab to outreach dashboard")
    parser.add_argument(
        "--spreadsheet-id",
        default=os.environ.get("OUTREACH_SPREADSHEET_ID", ""),
        help="Google Sheets spreadsheet ID",
    )
    args = parser.parse_args()

    if not args.spreadsheet_id:
        print(
            "ERROR: No spreadsheet ID. Set OUTREACH_SPREADSHEET_ID env var or use --spreadsheet-id."
        )
        sys.exit(1)

    service = get_sheets_service()

    # Step 1: Add and seed the Dropdowns tab
    add_dropdowns_tab(service, args.spreadsheet_id)

    # Step 2: Apply dropdown validations to all queue tabs
    print("\nApplying dropdown validations to all queue tabs...")
    asyncio.run(apply_validations(args.spreadsheet_id))

    print("\nDone!")


if __name__ == "__main__":
    main()
