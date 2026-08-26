#!/usr/bin/env python3
"""One-time setup: Create the DSDN Automated Grant Scanner Google Sheet."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cmo_agent.grants.dashboard import GrantScannerDashboard


async def main():
    sa_path = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        str(ROOT / "data" / "saverwell-google-credentials.json"),
    )
    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))

    dashboard = GrantScannerDashboard(
        google_credentials_path=sa_path,
        google_oauth_token_path=oauth_path,
    )

    team_members = ["Melissa Shutwell"]

    print("Creating DSDN Automated Grant Scanner dashboard...")
    result = await dashboard.create_dashboard(team_members)

    if result.get("status") == "created":
        print("\nDashboard created successfully!")
        print(f"URL: {result['spreadsheet_url']}")
        print(f"Spreadsheet ID: {result['spreadsheet_id']}")
        print("\nAdd this to your .env:")
        print(f'GRANT_SCANNER_SPREADSHEET_ID="{result["spreadsheet_id"]}"')
    else:
        print(f"Failed: {result}")


if __name__ == "__main__":
    asyncio.run(main())
