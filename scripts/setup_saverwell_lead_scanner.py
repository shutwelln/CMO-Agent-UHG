#!/usr/bin/env python3
"""One-off script: Creates the Saverwell Lead Scanner Google Sheet dashboard.

Creates a 6-tab Google Sheet (Lead Queue, Search Terms, Canned Responses,
Team Dashboard, Archive, Dropdowns) pre-populated with 130+ search terms
across 3 pillars (Savings, Protection, Guides), 6 canned response templates,
and dropdown validations.

Usage:
    python scripts/setup_saverwell_lead_scanner.py

Output:
    Prints the spreadsheet URL and ID. Add the ID to .env as:
    SAVERWELL_LEAD_SCANNER_SPREADSHEET_ID="<id>"
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cmo_agent.leads.dashboard import LeadScannerDashboard


async def main():
    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

    dashboard = LeadScannerDashboard(
        google_credentials_path=sa_path,
        google_oauth_token_path=oauth_path,
    )

    team_members = ["Nick Shutwell"]

    print("Creating Saverwell Lead Scanner Dashboard...")
    print(f"  - 6 tabs: Lead Queue, Search Terms, Canned Responses, Team Dashboard, Archive, Dropdowns")
    print(f"  - 130+ search terms across 3 pillars (Savings, Protection, Guides)")
    print(f"  - 6 canned response templates")
    print(f"  - Dropdown validations on Status, Claimed By, Outcome columns")
    print()

    result = await dashboard.create_dashboard(team_members)

    if result.get("status") == "created":
        print(f"Dashboard created successfully!")
        print(f"URL: {result['spreadsheet_url']}")
        print(f"Spreadsheet ID: {result['spreadsheet_id']}")
        print()
        print(f"Add this to your .env:")
        print(f'SAVERWELL_LEAD_SCANNER_SPREADSHEET_ID="{result["spreadsheet_id"]}"')
    else:
        print(f"Failed: {result}")


if __name__ == "__main__":
    asyncio.run(main())
