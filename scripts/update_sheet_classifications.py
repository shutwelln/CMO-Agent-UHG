#!/usr/bin/env python3
"""Update existing Sheet rows with post type + engagement risk from DB.

The backfill stored classifications in the DB but the Sheet rows already
existed, so append_opportunities skipped them. This script reads the
Sheet's Opportunity IDs (column P), looks up classifications in the DB,
and batch-updates columns F (Post Type) and H (Engagement Risk).
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


async def main():
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database

    settings = Settings()
    db = Database(db_path=settings.db_path)
    await db.initialize()

    # ── Google Sheets auth ──────────────────────────────────────────
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

    # ── Read existing rows: columns F (Post Type), H (Risk), P (Opp ID) ──
    result = (
        service.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="'Outreach Queue'!A2:P5000",
        )
        .execute()
    )
    rows = result.get("values", [])
    print(f"Sheet rows: {len(rows)}")

    # Build map: opp_id → row_index (0-based from row 2)
    opp_id_to_row = {}
    for i, row in enumerate(rows):
        if len(row) >= 16 and row[15]:  # column P = index 15
            opp_id_to_row[row[15]] = i + 2  # +2 because Sheet is 1-indexed + header

    print(f"Mapped {len(opp_id_to_row)} opportunity IDs")

    # ── Read classifications from DB ──────────────────────────────
    db_rows = await db.fetchall(
        "SELECT id, platform_post_type, engagement_risk FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND category = 'outreach' "
        "AND platform_post_type IS NOT NULL",
        (),
    )
    print(f"DB rows with classifications: {len(db_rows)}")

    # ── Batch update Sheet ────────────────────────────────────────
    updates = []
    for row in db_rows:
        opp_id = row["id"]
        if opp_id not in opp_id_to_row:
            continue

        sheet_row = opp_id_to_row[opp_id]
        post_type = row["platform_post_type"] or ""
        risk = row["engagement_risk"] or ""
        risk_display = "" if risk == "none" else f"[RISK: {risk}]"

        # Column F = Post Type (index 5, so F{row})
        updates.append({
            "range": f"'Outreach Queue'!F{sheet_row}",
            "values": [[post_type]],
        })
        # Column H = Engagement Risk (index 7, so H{row})
        updates.append({
            "range": f"'Outreach Queue'!H{sheet_row}",
            "values": [[risk_display]],
        })

    if not updates:
        print("No updates needed.")
        await db.close()
        return

    print(f"Pushing {len(updates)} cell updates...")

    # Batch update in chunks of 100 (API limit)
    for i in range(0, len(updates), 100):
        chunk = updates[i : i + 100]
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={
                "valueInputOption": "RAW",
                "data": chunk,
            },
        ).execute()
        print(f"  ...updated {min(i + 100, len(updates))}/{len(updates)}")

    print("Done! Post types and engagement risk updated in Sheet.")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
