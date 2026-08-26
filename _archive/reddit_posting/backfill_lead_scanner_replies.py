#!/usr/bin/env python3
"""One-time backfill: score and generate draft replies for all leads from scratch.

Reads Full Content column for better scoring and reply quality.
Processes ALL leads with Status 'New', overwriting any previous scores/replies.

Usage:
    source .venv/bin/activate
    python scripts/backfill_lead_scanner_replies.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, List

# Ensure project root is on sys.path
project_root = str(Path(__file__).resolve().parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

import structlog

logger = structlog.get_logger()

SCORE_THRESHOLD = 20


async def backfill() -> None:
    from googleapiclient.discovery import build

    from src.cmo_agent.config import get_settings
    from src.cmo_agent.google_auth import get_google_credentials
    from src.cmo_agent.leads.dashboard import LeadScannerDashboard
    from src.cmo_agent.llm.anthropic import AnthropicLLM
    from src.cmo_agent.leads.dashboard import should_skip_lead
    from src.cmo_agent.saverwell.replies import (
        SaverwellReplyGenerator,
        split_reply_and_notes,
    )
    from src.cmo_agent.workspace.brand_voice import load_brand_voice

    settings = get_settings()
    sid = settings.lead_scanner_spreadsheet_id
    if not sid:
        print("ERROR: SAVERWELL_LEAD_SCANNER_SPREADSHEET_ID not set in .env")
        sys.exit(1)

    # Read all leads directly from the Sheet
    creds = get_google_credentials(
        service_account_path=settings.google_credentials_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    svc = build("sheets", "v4", credentials=creds)

    print(f"Reading leads from Sheet {sid}...")
    result = (
        svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=sid,
            range="'Lead Queue'!A1:S5000",
        )
        .execute()
    )
    all_rows = result.get("values", [])
    if len(all_rows) < 2:
        print("No leads in the Sheet.")
        return

    # Build header map
    header = all_rows[0]
    col: Dict[str, int] = {}
    for i, h in enumerate(header):
        col[h.strip()] = i

    print(f"Headers: {list(col.keys())}")

    def _cell(row: List[str], name: str) -> str:
        idx = col.get(name, -1)
        if idx < 0 or idx >= len(row):
            return ""
        return row[idx]

    # Collect leads that still need processing (empty Score column)
    all_leads: List[Dict[str, Any]] = []
    skipped_already_scored = 0

    for row_idx, row in enumerate(all_rows[1:], start=2):
        title = _cell(row, "Post Title/Summary")
        full_content = _cell(row, "Full Content")
        lead_id = _cell(row, "Lead ID")
        existing_score = _cell(row, "Score").strip()

        if not title and not full_content:
            continue

        # Skip leads that already have a score (already processed)
        if existing_score:
            skipped_already_scored += 1
            continue

        all_leads.append(
            {
                "row_number": row_idx,
                "lead_id": lead_id,
                "platform": _cell(row, "Platform"),
                "pillar": _cell(row, "Pillar"),
                "title": title,
                "full_content": full_content,
                "url": _cell(row, "Post URL"),
            }
        )

    total = len(all_leads)
    print(f"Found {total} leads to process ({skipped_already_scored} already scored, skipped)")

    if total == 0:
        print("Nothing to backfill.")
        return

    # Set up LLMs
    writing_llm = AnthropicLLM(
        api_key=settings.get_llm_api_key(),
        model=settings.llm_model_writing,
    )
    scanning_llm = AnthropicLLM(
        api_key=settings.get_llm_api_key(),
        model=settings.llm_model_scanning,
    )
    generator = SaverwellReplyGenerator(
        llm=writing_llm,
        classification_llm=scanning_llm,
        scanning_llm=scanning_llm,
    )

    brand_voice = load_brand_voice("saverwell.txt")
    guide_dir = Path("data/saverwell/guide_drafts")
    guide_slugs = [p.stem for p in guide_dir.glob("*.json")] if guide_dir.exists() else []

    # Dashboard for writing back
    dashboard = LeadScannerDashboard(
        google_credentials_path=settings.google_credentials_path,
        google_oauth_token_path=settings.google_oauth_token_path,
        spreadsheet_id=sid,
    )

    BATCH_SIZE = 25
    updates: List[Dict[str, Any]] = []
    generated = 0
    scored = 0
    count = 0
    total_written = 0

    async def flush_updates() -> None:
        nonlocal updates, total_written
        if not updates:
            return
        print(f"\n  >> Flushing {len(updates)} updates to Sheet...")
        written = await dashboard.update_lead_fields(updates)
        total_written += written
        print(f"  >> Written {written} rows (total so far: {total_written})")
        updates = []

    print(f"\n--- Scoring and generating replies for {total} leads ---")
    audience_mismatches = 0
    for lead in all_leads:
        count += 1
        title = lead["title"]
        content = lead.get("full_content", "") or ""
        platform = (lead.get("platform", "") or "reddit").lower()
        lead_id = lead.get("lead_id", "unknown")
        # Extract subreddit from URL
        url = lead.get("url", "") or ""
        subreddit = ""
        if "/r/" in url:
            parts = url.split("/r/", 1)[1].split("/", 1)
            subreddit = parts[0] if parts else ""

        try:
            score_result = await generator.score_lead(
                title=title,
                content=content,
                platform=platform,
                subreddit=subreddit,
            )
            total_score = score_result.get("total", 0)
            post_type = score_result.get("post_type", "general_savings")
            monetization = score_result.get("monetization_signal", "")
            audience_mismatch = score_result.get("audience_mismatch", False)
            audience_fit = score_result.get("audience_fit", 0)
            scored += 1

            draft_reply = ""
            reviewer_notes = ""

            if audience_mismatch:
                reviewer_notes = f"Flag: audience mismatch (audience_fit={audience_fit})"
                status_label = "NOFIT"
                audience_mismatches += 1
            elif total_score >= SCORE_THRESHOLD:
                reply_text, _canned, warnings = await generator.generate_reply(
                    title=title,
                    content=content,
                    post_type=post_type,
                    platform=platform,
                    brand_voice=brand_voice,
                    guide_slugs=guide_slugs[:5],
                )
                draft_reply, reviewer_notes = split_reply_and_notes(reply_text)
                generated += 1
                if warnings:
                    reviewer_notes = (
                        reviewer_notes + " | " + "; ".join(warnings)
                        if reviewer_notes
                        else "; ".join(warnings)
                    )
                status_label = "REPLY"
            else:
                reviewer_notes = "Score below threshold"
                status_label = "SKIP"

            status = "Skipped" if should_skip_lead(reviewer_notes) else "New"

            updates.append(
                {
                    "row_number": lead["row_number"],
                    "score": total_score,
                    "post_type": post_type,
                    "monetization_signal": monetization,
                    "draft_reply": draft_reply,
                    "reviewer_notes": reviewer_notes,
                    "status": status,
                }
            )
            has_content = "+" if content else "-"
            sub_tag = f"r/{subreddit}" if subreddit else platform
            print(
                f"  [{count}/{total}] {status_label} {has_content}C AF={audience_fit} | Score {total_score:>2} | {sub_tag[:16]} | {title[:50]}"
            )
        except Exception as e:
            print(f"  [{count}/{total}] ERROR | {lead_id[:16]} | {e}")

        if len(updates) >= BATCH_SIZE:
            await flush_updates()

    # Flush remaining
    await flush_updates()

    print(
        f"\nBackfill complete: {scored} scored, "
        f"{generated} replies generated, {audience_mismatches} audience mismatches, "
        f"{total_written} rows written out of {total} total leads."
    )


if __name__ == "__main__":
    asyncio.run(backfill())
