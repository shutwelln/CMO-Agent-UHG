#!/usr/bin/env python3
"""Fix double-spaced dashes in existing draft replies (DB + Google Sheet).

Replaces "  -  ", "  - ", " -  " with " - " (single space each side)
in all draft_reply values in the DB, then pushes cleaned text to the Sheet.
"""
from __future__ import annotations

import asyncio
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


def normalize_dashes(text: str) -> str:
    """Replace em/en dashes and normalize spacing around hyphens."""
    cleaned = text
    # Replace em/en dashes
    cleaned = cleaned.replace("\u2014", " - ")
    cleaned = cleaned.replace("\u2013", " - ")
    # Normalize double-spaced dashes to single-spaced
    while "  - " in cleaned or " -  " in cleaned or "  -  " in cleaned:
        cleaned = (
            cleaned.replace("  -  ", " - ")
            .replace("  - ", " - ")
            .replace(" -  ", " - ")
        )
    return cleaned


async def main():
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database

    settings = Settings()
    db = Database(db_path=settings.db_path)
    await db.initialize()

    # ── Phase 1: Fix draft replies in DB ──────────────────────────────
    print("=== Phase 1: Fixing dash spacing in DB draft replies ===")

    rows = await db.fetchall(
        "SELECT id, draft_reply FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND category = 'outreach' "
        "AND draft_reply IS NOT NULL AND draft_reply != ''",
        (),
    )
    print(f"  Found {len(rows)} draft replies in DB")

    db_fixed = 0
    for row in rows:
        opp_id = row["id"]
        original = row["draft_reply"]
        cleaned = normalize_dashes(original)
        if cleaned != original:
            await db.execute(
                "UPDATE opportunities SET draft_reply = ? WHERE id = ?",
                (cleaned, opp_id),
            )
            db_fixed += 1

    print(f"  Fixed dash spacing in {db_fixed} DB rows")

    # ── Phase 2: Push cleaned drafts to Google Sheet ──────────────────
    print("\n=== Phase 2: Pushing cleaned drafts to Google Sheet ===")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json")
    )
    creds = Credentials.from_authorized_user_file(
        oauth_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)
    spreadsheet_id = settings.outreach_spreadsheet_id

    # Read Sheet to map Opportunity ID (col P, index 15) → row number
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="'Outreach Queue'!A2:P5000")
        .execute()
    )
    sheet_rows = result.get("values", [])
    print(f"  Sheet rows: {len(sheet_rows)}")

    opp_id_to_row: Dict[str, int] = {}
    for i, row in enumerate(sheet_rows):
        if len(row) >= 16 and row[15]:
            opp_id_to_row[row[15]] = i + 2  # +2 for 1-indexed + header

    # Read cleaned drafts from DB
    cleaned_rows = await db.fetchall(
        "SELECT id, draft_reply FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND category = 'outreach' "
        "AND draft_reply IS NOT NULL AND draft_reply != ''",
        (),
    )

    cell_updates: List[Dict[str, Any]] = []
    for row in cleaned_rows:
        opp_id = row["id"]
        if opp_id not in opp_id_to_row:
            continue
        sheet_row = opp_id_to_row[opp_id]
        cell_updates.append({
            "range": f"'Outreach Queue'!I{sheet_row}",
            "values": [[row["draft_reply"]]],
        })

    print(f"  Pushing {len(cell_updates)} cleaned drafts to Sheet")

    if cell_updates:
        for i in range(0, len(cell_updates), 100):
            chunk = cell_updates[i : i + 100]
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "RAW", "data": chunk},
            ).execute()
            print(
                f"  ...pushed {min(i + 100, len(cell_updates))}/{len(cell_updates)}"
            )

    await db.close()

    print(f"\n{'='*60}")
    print(f"Done! Fixed {db_fixed} drafts in DB, pushed {len(cell_updates)} to Sheet.")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
