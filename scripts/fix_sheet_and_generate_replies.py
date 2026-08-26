#!/usr/bin/env python3
"""Fix Sheet columns and generate draft replies for backfilled posts.

Fixes three issues:
1. Generate draft replies (column I) for all posts using canned responses + LLM
2. Update Engagement Risk (column H) to show "None" instead of blank for safe posts
3. Re-apply dropdown validations on Status (J), Outcome (O) columns
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


async def main():
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database
    from cmo_agent.llm.anthropic import AnthropicLLM
    from cmo_agent.llm.base import Message
    from cmo_agent.outreach.dashboard import CANNED_RESPONSES_SEED
    from cmo_agent.outreach.replies import OutreachReplyGenerator

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

    # ── Get Sheet ID for Outreach Queue tab ─────────────────────────
    sheet_meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties"
    ).execute()
    queue_sheet_id = None
    for sheet in sheet_meta.get("sheets", []):
        if sheet["properties"]["title"] == "Outreach Queue":
            queue_sheet_id = sheet["properties"]["sheetId"]
            break

    if queue_sheet_id is None:
        print("ERROR: Could not find 'Outreach Queue' tab")
        return

    # ── Read existing Sheet rows to map Opp IDs to row numbers ──────
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range="'Outreach Queue'!A2:P5000")
        .execute()
    )
    sheet_rows = result.get("values", [])
    print(f"Sheet rows: {len(sheet_rows)}")

    opp_id_to_row: Dict[str, int] = {}
    for i, row in enumerate(sheet_rows):
        if len(row) >= 16 and row[15]:
            opp_id_to_row[row[15]] = i + 2  # 1-indexed + header

    # ── Load brand voice ────────────────────────────────────────────
    brand_voice_path = ROOT / "data" / "brand_voices" / "dsdn.txt"
    brand_voice = ""
    if brand_voice_path.exists():
        brand_voice = brand_voice_path.read_text()[:1000]
    print(f"Brand voice loaded: {len(brand_voice)} chars")

    # ── Init LLM + reply generator ──────────────────────────────────
    llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model_writing,
        max_tokens=600,
        temperature=0.5,
    )
    reply_gen = OutreachReplyGenerator(llm)

    # ── Phase 1: Generate draft replies ─────────────────────────────
    print("\n=== Phase 1: Generating draft replies ===")

    db_rows = await db.fetchall(
        "SELECT id, title, content, platform_post_type, source, draft_reply "
        "FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND category = 'outreach' "
        "AND platform_post_type IS NOT NULL "
        "ORDER BY score DESC",
        (),
    )

    replies_generated = 0
    cell_updates: List[Dict[str, Any]] = []

    for row in db_rows:
        opp_id = row["id"]
        title = row["title"] or ""
        content = row["content"] or ""
        post_type = row["platform_post_type"] or "seeking_community"
        platform = row["source"] or "reddit"

        # Skip if already has a draft
        if row["draft_reply"]:
            # Still push existing draft to Sheet if row exists
            if opp_id in opp_id_to_row:
                sheet_row = opp_id_to_row[opp_id]
                cell_updates.append({
                    "range": f"'Outreach Queue'!I{sheet_row}",
                    "values": [[row["draft_reply"][:2000]]],
                })
            continue

        print(f"  Generating reply for [{post_type}]: {title[:60]}...", flush=True)

        reply_text, canned_used, warnings = await reply_gen.generate_reply(
            title=title,
            content=content,
            post_type=post_type,
            platform=platform,
            canned_responses=CANNED_RESPONSES_SEED,
            brand_voice=brand_voice,
        )

        # Store in DB
        await db.execute(
            "UPDATE opportunities SET draft_reply = ?, canned_response_used = ? "
            "WHERE id = ?",
            (reply_text, canned_used, opp_id),
        )

        # Queue Sheet update
        if opp_id in opp_id_to_row:
            sheet_row = opp_id_to_row[opp_id]
            cell_updates.append({
                "range": f"'Outreach Queue'!I{sheet_row}",
                "values": [[reply_text[:2000]]],
            })

        replies_generated += 1
        if replies_generated % 10 == 0:
            print(f"    ...{replies_generated} replies generated")

        if warnings:
            for w in warnings:
                print(f"    WARNING: {w}")

    print(f"  Draft replies generated: {replies_generated}")

    # ── Phase 2: Fix Engagement Risk display ────────────────────────
    print("\n=== Phase 2: Fixing Engagement Risk display ===")

    risk_rows = await db.fetchall(
        "SELECT id, engagement_risk FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND category = 'outreach'",
        (),
    )

    risk_updates = 0
    for row in risk_rows:
        opp_id = row["id"]
        if opp_id not in opp_id_to_row:
            continue

        risk = row["engagement_risk"] or "none"
        risk_display = "None" if risk == "none" else risk
        sheet_row = opp_id_to_row[opp_id]
        cell_updates.append({
            "range": f"'Outreach Queue'!H{sheet_row}",
            "values": [[risk_display]],
        })
        risk_updates += 1

    print(f"  Engagement Risk cells to update: {risk_updates}")

    # ── Phase 3: Batch push all cell updates ────────────────────────
    print(f"\n=== Phase 3: Pushing {len(cell_updates)} cell updates to Sheet ===")

    for i in range(0, len(cell_updates), 100):
        chunk = cell_updates[i : i + 100]
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": chunk},
        ).execute()
        print(f"  ...pushed {min(i + 100, len(cell_updates))}/{len(cell_updates)}")

    # ── Phase 4: Fix Status column — set "New" via USER_ENTERED + apply dropdowns ──
    print("\n=== Phase 4: Restoring dropdowns ===")

    data_row_count = len(sheet_rows)
    last_data_row = data_row_count + 1  # 1-indexed, +1 for header

    # Set Status values to "New" for rows that have it as "new" (case fix)
    status_updates = []
    for i, row in enumerate(sheet_rows):
        sheet_row_num = i + 2
        # Column J (index 9) is Status
        current_status = row[9] if len(row) > 9 else ""
        if current_status.lower() == "new" or current_status == "":
            status_updates.append({
                "range": f"'Outreach Queue'!J{sheet_row_num}",
                "values": [["New"]],
            })

    if status_updates:
        for i in range(0, len(status_updates), 100):
            chunk = status_updates[i : i + 100]
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"valueInputOption": "RAW", "data": chunk},
            ).execute()
        print(f"  Status values set: {len(status_updates)}")

    # Apply dropdown validations via ONE_OF_RANGE (dynamic from Dropdowns tab)
    from cmo_agent.outreach.dashboard import build_dropdown_validation_request

    end_row = max(last_data_row + 50, 200)
    dropdown_requests = [
        build_dropdown_validation_request(queue_sheet_id, 9, "Status", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 14, "Outcome", end_row=end_row),
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": dropdown_requests},
    ).execute()
    print("  Dropdowns applied (ONE_OF_RANGE → Dropdowns tab): Status (J), Outcome (O)")

    await db.close()

    print(f"\n{'='*60}")
    print("All fixes applied!")
    print(f"  Draft replies generated: {replies_generated}")
    print(f"  Engagement Risk cells updated: {risk_updates}")
    print(f"  Status dropdown rows: {max(last_data_row + 50, 200) - 1}")
    print(f"  Total Sheet cell updates: {len(cell_updates) + len(status_updates)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
