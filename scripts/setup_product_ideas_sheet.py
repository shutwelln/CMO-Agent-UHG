#!/usr/bin/env python3
"""One-time setup: Add Source column, Skipped status, and Archive tab to the
Saverwell Product Ideas Google Sheet.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cmo_agent.growth_ideas import ProductIdeasDashboard


async def main():
    sa_path = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        str(ROOT / "data" / "saverwell-google-credentials.json"),
    )
    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    sheet_id = os.getenv(
        "GROWTH_IDEAS_SPREADSHEET_ID",
        "13pe8PKVlkcUZJSd97j-GpfqbAcWRRw-bFcZPToVWpz4",
    )

    dashboard = ProductIdeasDashboard(
        google_credentials_path=sa_path,
        google_oauth_token_path=oauth_path,
        spreadsheet_id=sheet_id,
    )

    print("Setting up Product Ideas sheet...")
    result = await dashboard.setup_sheet()

    if result.get("status") == "ok":
        print("\nSetup complete!")
        for step in result.get("results", []):
            print(f"  - {step}")
    else:
        print(f"\nSetup failed: {result}")


if __name__ == "__main__":
    asyncio.run(main())
