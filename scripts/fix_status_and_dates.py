#!/usr/bin/env python3
"""Fix: dates to CST format, remove Draft Generated status, default all to New."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

CST = timezone(timedelta(hours=-6))


def to_cst_display(dt_str: Optional[str]) -> str:
    """Convert a UTC datetime string to CST display format (MM/DD/YYYY h:MM AM/PM)."""
    if not dt_str:
        return ""
    try:
        # Handle various formats from SQLite / our scripts
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S%z", "%Y-%m-%dT%H:%M:%S",
                     "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                dt = datetime.strptime(dt_str.strip(), fmt)
                break
            except ValueError:
                continue
        else:
            # Try just date
            try:
                dt = datetime.strptime(dt_str.strip()[:10], "%Y-%m-%d")
            except ValueError:
                return dt_str  # Return as-is if unparseable

        # If naive (no tz), assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        # Convert to CST
        dt_cst = dt.astimezone(CST)
        return dt_cst.strftime("%-m/%-d/%Y %-I:%M %p")
    except Exception:
        return dt_str


async def main():
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database

    settings = Settings()
    db = Database(db_path=settings.db_path)
    await db.initialize()

    # ── Phase 1: Fix status in DB ─────────────────────────────────────
    print("=== Phase 1: Fixing outreach_status in DB ===")

    cursor = await db.execute(
        "UPDATE opportunities SET outreach_status = 'new' "
        "WHERE workspace_id = 'dsdn' AND category = 'outreach' "
        "AND outreach_status = 'draft_generated'",
        (),
    )
    fixed_status = cursor.rowcount or 0
    print(f"  Changed {fixed_status} rows from 'draft_generated' to 'new'")

    # ── Phase 2: Rebuild Sheet with CST dates + fixed statuses ────────
    print("\n=== Phase 2: Rebuilding Sheet data with CST dates ===")

    import json
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

    # Get Sheet ID
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
        await db.close()
        return

    # Clear data rows (keep header)
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range="'Outreach Queue'!A2:Q5000",
    ).execute()

    # Load all outreach records from DB
    all_opps = await db.fetchall(
        "SELECT * FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND category = 'outreach' "
        "ORDER BY score DESC, created_at DESC",
        (),
    )

    def _is_sensitive(post_type: Optional[str], score_breakdown_str: Optional[str]) -> bool:
        if post_type == "loss":
            return True
        if score_breakdown_str:
            try:
                bd = json.loads(score_breakdown_str) if isinstance(score_breakdown_str, str) else score_breakdown_str
                return bd.get("urgency", 0) >= 9
            except (json.JSONDecodeError, AttributeError):
                pass
        return False

    data_rows = []
    for opp in all_opps:
        d = dict(opp)
        sensitivity = "[SENSITIVE]" if _is_sensitive(
            d.get("platform_post_type"), d.get("score_breakdown"),
        ) else ""
        risk = d.get("engagement_risk", "none") or "none"
        risk_display = "None" if risk == "none" else risk
        title = d.get("title", "")
        content = d.get("content", "") or ""
        full_post = (title + "\n\n" + content).strip() if content else title

        # Status: always "New" now (we fixed DB above)
        status = d.get("outreach_status", "new") or "new"
        if status and status[0].islower():
            status = status.replace("_", " ").title()

        data_rows.append([
            to_cst_display(d.get("posted_at", "")),      # A: Post Date (CST)
            to_cst_display(d.get("created_at", "")),      # B: Date Found (CST)
            d.get("source", ""),                           # C: Platform
            full_post,                                     # D: Post Title/Summary
            d.get("source_url", ""),                       # E: Post URL
            str(d.get("score", 0)),                        # F: Score
            d.get("platform_post_type", ""),               # G: Post Type
            sensitivity,                                   # H: Sensitivity?
            risk_display,                                  # I: Engagement Risk?
            d.get("draft_reply", "") or "",                # J: Draft Reply
            status,                                        # K: Status
            d.get("claimed_at", "") or "",                 # L: Claimed Date/Time
            d.get("claimed_by", "") or "",                 # M: Claimed By
            d.get("response_notes", "") or "",             # N: Response Notes
            d.get("response_url", "") or "",               # O: Response URL
            d.get("outreach_outcome", "") or "",           # P: Outcome
            d.get("id", ""),                               # Q: Opportunity ID
        ])

    print(f"  Writing {len(data_rows)} rows with CST dates...")

    for i in range(0, len(data_rows), 100):
        chunk = data_rows[i:i + 100]
        start_row = i + 2
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'Outreach Queue'!A{start_row}",
            valueInputOption="RAW",
            body={"values": chunk},
        ).execute()
        print(f"  ...wrote rows {start_row}-{start_row + len(chunk) - 1}")

    # ── Phase 3: Fix dropdown (remove Draft Generated) ────────────────
    print("\n=== Phase 3: Updating dropdown validations ===")

    end_row = max(len(data_rows) + 51, 200)

    from cmo_agent.outreach.dashboard import build_dropdown_validation_request

    dropdown_requests = [
        build_dropdown_validation_request(queue_sheet_id, 10, "Status", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 12, "Claimed By", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 15, "Outcome", end_row=end_row),
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": dropdown_requests},
    ).execute()
    print("  Dropdowns applied (ONE_OF_RANGE → Dropdowns tab): Status (K), Claimed By (M), Outcome (P)")

    await db.close()

    print(f"\n{'='*60}")
    print("All fixes applied!")
    print(f"  Status fixed: {fixed_status} rows changed to 'New'")
    print(f"  Dates reformatted to CST (US Central)")
    print(f"  'Draft Generated' removed from status dropdown")
    print(f"  Total rows: {len(data_rows)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
