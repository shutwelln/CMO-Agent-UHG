#!/usr/bin/env python3
"""One-time backfill: Push all past growth ideas from SQLite drafts to the
Saverwell Product Ideas Google Sheet.

Safe to run multiple times - dedup is built into append_ideas().
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from cmo_agent.db.database import Database
from cmo_agent.db.repositories import DraftRepo
from cmo_agent.growth_ideas import ProductIdeasDashboard


def _extract_ideas_from_body(body: str) -> List[Dict[str, Any]]:
    """Extract the JSON ideas array from a growth ideas draft body.

    The body format is:
        # Daily Growth Ideas

        ## Ideas

        ```json
        [...]
        ```

        ## Recommended Priority
        ...
    """
    match = re.search(r"```json\s*\n(.*?)\n```", body, re.DOTALL)
    if not match:
        return []
    try:
        data = json.loads(match.group(1))
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return []


async def main():
    db_path = os.getenv("DB_PATH", str(ROOT / "data" / "cmo_agent.db"))
    sa_path = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        str(ROOT / "data" / "saverwell-google-credentials.json"),
    )
    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    sheet_id = os.getenv(
        "GROWTH_IDEAS_SPREADSHEET_ID",
        "13pe8PKVlkcUZJSd97j-GpfqbAcWRRw-bFcZPToVWpz4",
    )

    # Initialize DB
    db = Database(db_path=db_path)
    await db.initialize()

    drafts_repo = DraftRepo(db)

    # Query all growth_ideas drafts from the last 365 days
    drafts = await drafts_repo.list_recent(days=365, limit=1000, content_type="growth_ideas")
    print(f"Found {len(drafts)} growth ideas draft(s) in SQLite")

    # Extract all ideas from all drafts
    all_ideas: List[Dict[str, Any]] = []
    for draft in drafts:
        ideas = _extract_ideas_from_body(draft.body)
        all_ideas.extend(ideas)

    print(f"Extracted {len(all_ideas)} total ideas across all drafts")

    if not all_ideas:
        print("No ideas to backfill.")
        return

    # Initialize dashboard
    dashboard = ProductIdeasDashboard(
        google_credentials_path=sa_path,
        google_oauth_token_path=oauth_path,
        spreadsheet_id=sheet_id,
    )

    # Append with dedup
    appended = await dashboard.append_ideas(all_ideas, "Backfill")
    dupes = len(all_ideas) - appended
    print(f"\nBackfill complete: {appended} new ideas appended ({dupes} dupes skipped)")


if __name__ == "__main__":
    asyncio.run(main())
