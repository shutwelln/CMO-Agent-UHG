#!/usr/bin/env python3
"""Backfill missing fields on existing outreach rows.

Scans the DB for outreach opportunities missing:
- posted_at (Post Date)
- platform_post_type (Post Type)
- draft_reply (Draft Reply)
- engagement_risk (Engagement Risk)

Then updates the DB and patches only the affected cells in the Google Sheet,
preserving all user-entered data (Status, Claimed By, Notes, etc.).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import structlog

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

logger = structlog.get_logger()

WORKSPACE_ID = "dsdn"
_CST = timezone(timedelta(hours=-6))


def _to_cst_display(dt_str: str) -> str:
    """Convert a UTC datetime string to CST display format."""
    if not dt_str:
        return ""
    try:
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S%z",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%S%z",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S+00:00",
        ):
            try:
                dt = datetime.strptime(str(dt_str).strip(), fmt)
                break
            except ValueError:
                continue
        else:
            try:
                dt = datetime.strptime(str(dt_str).strip()[:10], "%Y-%m-%d")
            except ValueError:
                return str(dt_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt_cst = dt.astimezone(_CST)
        return dt_cst.strftime("%-m/%-d/%Y %-I:%M %p")
    except Exception:
        return str(dt_str)


async def main():
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database
    from cmo_agent.db.repositories import OpportunityRepo
    from cmo_agent.outreach.dashboard import CANNED_RESPONSES_SEED
    from cmo_agent.outreach.replies import OutreachReplyGenerator, split_reply_and_notes
    from cmo_agent.agents.dsdn_constants import DSDN_ORG_PROFILE

    settings = Settings()

    # Init DB
    db = Database(db_path=settings.db_path)
    await db.initialize()
    opp_repo = OpportunityRepo(db)

    print("=" * 60)
    print("Backfill Missing Fields on Existing Outreach Rows")
    print("=" * 60)

    # ── Phase 1: Find opportunities missing fields ──────────────────
    print("\nPhase 1: Finding opportunities with missing fields...")

    missing_rows = await db.fetchall(
        "SELECT id, title, content, source, posted_at, platform_post_type, "
        "draft_reply, engagement_risk, source_id "
        "FROM opportunities "
        "WHERE workspace_id = ? AND outreach_status IS NOT NULL "
        "AND (posted_at IS NULL OR platform_post_type IS NULL "
        "     OR draft_reply IS NULL OR draft_reply = '' "
        "     OR engagement_risk IS NULL) "
        "ORDER BY score DESC, created_at DESC",
        (WORKSPACE_ID,),
    )

    print(f"  Found {len(missing_rows)} opportunities with missing fields")

    if not missing_rows:
        print("  Nothing to backfill!")
        await db.close()
        return

    # Count what's missing
    missing_posted = sum(1 for r in missing_rows if not r["posted_at"])
    missing_type = sum(1 for r in missing_rows if not r["platform_post_type"])
    missing_reply = sum(1 for r in missing_rows if not r["draft_reply"])
    missing_risk = sum(1 for r in missing_rows if not r["engagement_risk"])

    print(f"  Missing posted_at: {missing_posted}")
    print(f"  Missing platform_post_type: {missing_type}")
    print(f"  Missing draft_reply: {missing_reply}")
    print(f"  Missing engagement_risk: {missing_risk}")

    # ── Phase 1b: Backfill posted_at from Reddit API for Reddit posts ──
    if missing_posted > 0:
        reddit_missing = [r for r in missing_rows if r["source"] == "reddit" and not r["posted_at"]]
        if reddit_missing:
            print(f"\n  Attempting to backfill posted_at for {len(reddit_missing)} Reddit posts...")
            import httpx

            async with httpx.AsyncClient(
                headers={"User-Agent": "DSDN-Backfill/1.0"},
                timeout=15.0,
                follow_redirects=True,
            ) as client:
                filled = 0
                for row in reddit_missing:
                    source_id = row["source_id"] or ""
                    # source_id format: "reddit_{post_id}" or just the post_id
                    post_id = source_id.replace("reddit_", "") if source_id.startswith("reddit_") else source_id
                    if not post_id:
                        continue

                    try:
                        url = f"https://www.reddit.com/api/info.json?id=t3_{post_id}"
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            data = resp.json()
                            children = data.get("data", {}).get("children", [])
                            if children:
                                created_utc = children[0].get("data", {}).get("created_utc", 0)
                                if created_utc:
                                    posted_str = datetime.fromtimestamp(
                                        created_utc, tz=timezone.utc
                                    ).strftime("%Y-%m-%d %H:%M:%S")
                                    await db.execute(
                                        "UPDATE opportunities SET posted_at = ? WHERE id = ?",
                                        (posted_str, row["id"]),
                                    )
                                    filled += 1
                        await asyncio.sleep(2.0)
                    except Exception as e:
                        logger.warning("reddit_posted_at_fetch_error", post_id=post_id, error=str(e))

                print(f"  Backfilled posted_at for {filled}/{len(reddit_missing)} Reddit posts")

    # ── Phase 2: Classify post types + assess risk via LLM ──────────
    needs_llm = [r for r in missing_rows if not r["platform_post_type"] or not r["engagement_risk"]]

    if needs_llm:
        print(f"\nPhase 2: Classifying post types + assessing risk for {len(needs_llm)} items...")

        from cmo_agent.llm.anthropic import AnthropicLLM

        llm = AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model_writing,
            max_tokens=500,
            temperature=0.3,
        )
        reply_gen = OutreachReplyGenerator(llm)

        classified = 0
        risk_assessed = 0

        for row in needs_llm:
            opp_id = row["id"]
            title = row["title"] or ""
            content = row["content"] or ""

            try:
                # Classify post type if missing
                if not row["platform_post_type"]:
                    post_type = await reply_gen.classify_post_type(title, content)
                    await db.execute(
                        "UPDATE opportunities SET platform_post_type = ? "
                        "WHERE id = ? AND platform_post_type IS NULL",
                        (post_type, opp_id),
                    )
                    classified += 1

                # Assess engagement risk if missing
                if not row["engagement_risk"]:
                    risk_level, reason = await reply_gen.assess_engagement_risk(title, content)
                    risk_value = f"{risk_level}: {reason}" if risk_level != "none" else "none"
                    await db.execute(
                        "UPDATE opportunities SET engagement_risk = ? "
                        "WHERE id = ? AND engagement_risk IS NULL",
                        (risk_value, opp_id),
                    )
                    risk_assessed += 1

                if (classified + risk_assessed) % 10 == 0:
                    print(f"  ...processed {classified + risk_assessed} items")
            except Exception as e:
                logger.warning("classify_error", opp_id=opp_id[:12], error=str(e))

        print(f"  Classified {classified} post types, assessed {risk_assessed} risks")
    else:
        print("\nPhase 2: No items need classification/risk assessment")
        # Still need LLM for draft replies
        from cmo_agent.llm.anthropic import AnthropicLLM

        llm = AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.llm_model_writing,
            max_tokens=500,
            temperature=0.3,
        )
        reply_gen = OutreachReplyGenerator(llm)

    # ── Phase 3: Generate draft replies ──────────────────────────────
    needs_reply = [r for r in missing_rows if not r["draft_reply"]]

    if needs_reply:
        print(f"\nPhase 3: Generating draft replies for {len(needs_reply)} items...")

        # Re-read from DB to get updated platform_post_type values
        needs_reply_ids = [r["id"] for r in needs_reply]
        placeholders = ",".join("?" for _ in needs_reply_ids)
        updated_rows = await db.fetchall(
            f"SELECT id, title, content, source, platform_post_type "
            f"FROM opportunities WHERE id IN ({placeholders})",
            tuple(needs_reply_ids),
        )
        updated_map = {r["id"]: dict(r) for r in updated_rows}

        generated = 0
        for row in needs_reply:
            opp_id = row["id"]
            updated = updated_map.get(opp_id, {})
            title = updated.get("title") or row["title"] or ""
            content = updated.get("content") or row["content"] or ""
            post_type = updated.get("platform_post_type") or "seeking_community"
            platform = updated.get("source") or row["source"] or "reddit"

            try:
                reply_text, canned_used, warnings = await reply_gen.generate_reply(
                    title=title,
                    content=content,
                    post_type=post_type,
                    platform=platform,
                    canned_responses=CANNED_RESPONSES_SEED,
                    brand_voice=DSDN_ORG_PROFILE,
                )

                await db.execute(
                    "UPDATE opportunities SET draft_reply = ?, canned_response_used = ? "
                    "WHERE id = ? AND (draft_reply IS NULL OR draft_reply = '')",
                    (reply_text, canned_used, opp_id),
                )
                generated += 1

                if generated % 10 == 0:
                    print(f"  ...generated {generated}/{len(needs_reply)} replies")
            except Exception as e:
                logger.warning("reply_gen_error", opp_id=opp_id[:12], error=str(e))

        print(f"  Generated {generated} draft replies")
    else:
        print("\nPhase 3: All items already have draft replies")

    # ── Phase 4: Update Google Sheet (patch affected cells only) ─────
    print("\nPhase 4: Patching Google Sheet with updated data...")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    spreadsheet_id = settings.outreach_spreadsheet_id

    if not spreadsheet_id:
        print("  ERROR: No spreadsheet_id configured. Skipping sheet update.")
        await db.close()
        return

    creds = Credentials.from_authorized_user_file(
        oauth_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)

    # Read all tabs that have outreach data
    sheet_meta = service.spreadsheets().get(
        spreadsheetId=spreadsheet_id, fields="sheets.properties"
    ).execute()
    queue_tabs = []
    for sheet in sheet_meta.get("sheets", []):
        title = sheet["properties"]["title"]
        if title in ("Outreach Queue", "Archive") or title.endswith("Queue"):
            queue_tabs.append(title)

    print(f"  Tabs to update: {', '.join(queue_tabs)}")

    total_updated = 0

    for tab_name in queue_tabs:
        # Read current sheet data: columns A-L (system columns) + C (Opp ID for lookup)
        try:
            result = service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab_name}'!A1:R5000",
            ).execute()
            rows = result.get("values", [])
        except Exception as e:
            print(f"  WARNING: Could not read tab '{tab_name}': {e}")
            continue

        if len(rows) < 2:
            continue

        headers = rows[0]
        # Find column indices by header name
        col_map = {h.strip(): i for i, h in enumerate(headers)}

        opp_id_col = col_map.get("Opportunity ID")
        post_date_col = col_map.get("Post Date")
        date_found_col = col_map.get("Date Found")
        post_type_col = col_map.get("Post Type")
        draft_reply_col = col_map.get("Draft Reply")
        reviewer_notes_col = col_map.get("Reviewer Notes")
        risk_col = col_map.get("Engagement Risk?")
        sensitivity_col = col_map.get("Sensitivity?")
        score_col = col_map.get("Score")

        if opp_id_col is None:
            print(f"  WARNING: Tab '{tab_name}' has no 'Opportunity ID' column, skipping")
            continue

        # Collect opportunity IDs from the sheet
        sheet_opp_ids = []
        for i, row in enumerate(rows[1:], start=2):  # row numbers are 1-indexed, skip header
            if len(row) > opp_id_col and row[opp_id_col]:
                sheet_opp_ids.append((i, row[opp_id_col], row))

        if not sheet_opp_ids:
            continue

        # Batch-read all those opportunities from DB
        all_ids = [sid for _, sid, _ in sheet_opp_ids]
        placeholders = ",".join("?" for _ in all_ids)
        db_rows = await db.fetchall(
            f"SELECT * FROM opportunities WHERE id IN ({placeholders})",
            tuple(all_ids),
        )
        db_map = {r["id"]: dict(r) for r in db_rows}

        # Build batch update requests
        updates: List[Dict[str, Any]] = []

        for row_num, opp_id, sheet_row in sheet_opp_ids:
            opp = db_map.get(opp_id)
            if not opp:
                continue

            def _get_cell(col_idx):
                if col_idx is not None and col_idx < len(sheet_row):
                    return sheet_row[col_idx].strip()
                return ""

            # Check each field and queue updates for missing ones
            # Post Date (A)
            if post_date_col is not None and not _get_cell(post_date_col) and opp.get("posted_at"):
                col_letter = chr(65 + post_date_col) if post_date_col < 26 else "A"
                updates.append({
                    "range": f"'{tab_name}'!{col_letter}{row_num}",
                    "values": [[_to_cst_display(str(opp["posted_at"]))]],
                })

            # Date Found (B)
            if date_found_col is not None and not _get_cell(date_found_col) and opp.get("created_at"):
                col_letter = chr(65 + date_found_col)
                updates.append({
                    "range": f"'{tab_name}'!{col_letter}{row_num}",
                    "values": [[_to_cst_display(str(opp["created_at"]))]],
                })

            # Post Type (H)
            if post_type_col is not None and not _get_cell(post_type_col) and opp.get("platform_post_type"):
                col_letter = chr(65 + post_type_col)
                updates.append({
                    "range": f"'{tab_name}'!{col_letter}{row_num}",
                    "values": [[opp["platform_post_type"]]],
                })

            # Sensitivity (I) — recalculate
            if sensitivity_col is not None and not _get_cell(sensitivity_col):
                is_sens = False
                if opp.get("platform_post_type") == "loss":
                    is_sens = True
                sb = opp.get("score_breakdown")
                if sb:
                    try:
                        bd = json.loads(sb) if isinstance(sb, str) else sb
                        if bd.get("urgency", 0) >= 9:
                            is_sens = True
                    except (json.JSONDecodeError, TypeError):
                        pass
                if is_sens:
                    col_letter = chr(65 + sensitivity_col)
                    updates.append({
                        "range": f"'{tab_name}'!{col_letter}{row_num}",
                        "values": [["[SENSITIVE]"]],
                    })

            # Engagement Risk (J)
            if risk_col is not None and not _get_cell(risk_col) and opp.get("engagement_risk"):
                risk = opp["engagement_risk"]
                risk_display = "None" if risk == "none" else risk
                col_letter = chr(65 + risk_col)
                updates.append({
                    "range": f"'{tab_name}'!{col_letter}{row_num}",
                    "values": [[risk_display]],
                })

            # Draft Reply (K)
            if draft_reply_col is not None and not _get_cell(draft_reply_col) and opp.get("draft_reply"):
                draft_raw = opp["draft_reply"]
                reply_text, reviewer_notes = split_reply_and_notes(draft_raw)
                col_letter = chr(65 + draft_reply_col)
                updates.append({
                    "range": f"'{tab_name}'!{col_letter}{row_num}",
                    "values": [[reply_text]],
                })
                # Reviewer Notes (L)
                if reviewer_notes_col is not None and reviewer_notes and not _get_cell(reviewer_notes_col):
                    col_letter = chr(65 + reviewer_notes_col)
                    updates.append({
                        "range": f"'{tab_name}'!{col_letter}{row_num}",
                        "values": [[reviewer_notes]],
                    })

            # Score (G) — fill if empty
            if score_col is not None and not _get_cell(score_col) and opp.get("score"):
                col_letter = chr(65 + score_col)
                updates.append({
                    "range": f"'{tab_name}'!{col_letter}{row_num}",
                    "values": [[str(opp["score"])]],
                })

        if updates:
            # Batch update in chunks of 50
            for i in range(0, len(updates), 50):
                chunk = updates[i:i + 50]
                service.spreadsheets().values().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={
                        "valueInputOption": "RAW",
                        "data": chunk,
                    },
                ).execute()

            total_updated += len(updates)
            print(f"  Tab '{tab_name}': patched {len(updates)} cells")
        else:
            print(f"  Tab '{tab_name}': no cells needed patching")

    await db.close()

    print(f"\n{'=' * 60}")
    print("Backfill complete!")
    print(f"  Total cells patched in Google Sheet: {total_updated}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    asyncio.run(main())
