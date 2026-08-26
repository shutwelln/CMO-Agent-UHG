#!/usr/bin/env python3
"""One-off script: Creates the DSDN Outreach Google Sheet dashboard."""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cmo_agent.outreach.dashboard import OutreachDashboard


async def main():
    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

    dashboard = OutreachDashboard(
        google_credentials_path=sa_path,
        google_oauth_token_path=oauth_path,
    )

    team_members = ["Nick Shutwell"]

    print("Creating DSDN Outreach Dashboard...")
    result = await dashboard.create_dashboard(team_members)

    if result.get("status") == "created":
        print(f"\nDashboard created successfully!")
        print(f"URL: {result['spreadsheet_url']}")
        print(f"Spreadsheet ID: {result['spreadsheet_id']}")
        print(f"\nAdd this to your .env:")
        print(f'OUTREACH_SPREADSHEET_ID="{result["spreadsheet_id"]}"')
    else:
        print(f"Failed: {result}")


if __name__ == "__main__":
    asyncio.run(main())
