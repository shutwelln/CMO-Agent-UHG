#!/usr/bin/env python3
"""Backfill: scan Reddit back to Jan 1 2026 for DSDN outreach posts.

Runs outside the scheduler — directly uses httpx + DB + dashboard.
Paginate Reddit's /new.json (up to 1000 posts per subreddit via `after` cursor).
Applies outreach search terms, scoring, risk assessment, and rebuilds Google Sheet.

Key features:
- Stores original Reddit post date as `posted_at` (separate from DB ingest time)
- Deduplicates by source_id and content_hash
- Updates posted_at on existing records that are missing it
- Rebuilds Sheet from scratch with new column layout (Post Date in col A)
"""
from __future__ import annotations

import asyncio
import calendar
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

logger = structlog.get_logger()

# ── Config ──────────────────────────────────────────────────────────────

# Go back to January 1, 2026 00:00 UTC
CUTOFF_DT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
CUTOFF_TS = CUTOFF_DT.timestamp()

# Outreach-relevant subreddits (wider net for backfill)
SUBREDDITS = [
    "downsyndrome",
    "BabyBumps",
    "NewParents",
    "NICUParents",
    "specialneedsparenting",
    "ScienceBasedParenting",
    "NIPT",
    "PregnancyAfterLoss",
    "pregnant",
    "beyondthebump",
]

REDDIT_USER_AGENT = "DSDN-Outreach-Backfill/1.0 (nonprofit; https://www.dsdiagnosisnetwork.org)"
REDDIT_DELAY = 2.0  # seconds between requests
MAX_PAGES_PER_SUB = 10  # up to 10 pages x 100 = 1000 posts per subreddit

WORKSPACE_ID = "dsdn"


# ── Helpers ─────────────────────────────────────────────────────────────


def compute_content_hash(title: str, content: str) -> str:
    normalized = title.strip().lower() + "|" + (content or "").strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def utc_ts_to_iso(ts: float) -> str:
    """Convert a Unix timestamp to an ISO 8601 datetime string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def score_outreach_post(title: str, content: str) -> Dict[str, int]:
    """Score using the same 4-dimension outreach scoring."""
    combined = (title + " " + (content or "")).lower()

    # Diagnosis relevance (0-10)
    relevance = 1
    high_rel = [
        "just found out", "got the results", "nipt came back", "nipt positive",
        "amnio results", "diagnosed", "prenatal diagnosis", "trisomy 21 positive",
        "t21 positive",
    ]
    mid_rel = [
        "diagnosis", "testing", "amniocentesis", "cvs results",
        "genetic counselor", "nipt", "trisomy 21",
    ]
    for t in high_rel:
        if t in combined:
            relevance = 10
            break
    if relevance < 10:
        for t in mid_rel:
            if t in combined:
                relevance = max(relevance, 7)
                break
    if "down syndrome" in combined and relevance < 4:
        relevance = 4

    # Recency (0-10)
    recency = 5

    # Urgency (0-10)
    urgency = 2
    high_urg = [
        "scared", "terrified", "don't know what to do", "feeling alone",
        "need help", "crying", "devastated", "heartbroken", "shocked",
        "overwhelmed", "lost",
    ]
    mid_urg = ["worried", "confused", "what should i expect", "any advice", "nervous", "anxious"]
    for t in high_urg:
        if t in combined:
            urgency = 9
            break
    if urgency < 9:
        for t in mid_urg:
            if t in combined:
                urgency = max(urgency, 6)
                break

    # DSDN fit (0-10)
    fit = 2
    high_fit = ["expecting", "pregnant", "prenatal", "newborn", "just born", "baby", "nicu", "born with"]
    mid_fit = ["toddler", "infant", "1 year", "2 year", "early intervention"]
    for t in high_fit:
        if t in combined:
            fit = 10
            break
    if fit < 10:
        for t in mid_fit:
            if t in combined:
                fit = max(fit, 7)
                break

    return {"diagnosis_relevance": relevance, "recency": recency, "urgency": urgency, "dsdn_fit": fit}


async def fetch_reddit_paginated(
    client: httpx.AsyncClient,
    subreddit: str,
    include_kw: List[str],
    exclude_kw: List[str],
) -> List[Dict[str, Any]]:
    """Fetch up to MAX_PAGES_PER_SUB pages from a subreddit, filtered by keywords and age."""
    from cmo_agent.outreach.search_terms import SearchTermsManager

    results = []
    after = None

    for page in range(MAX_PAGES_PER_SUB):
        params: Dict[str, Any] = {"limit": 100}
        if after:
            params["after"] = after

        url = f"https://www.reddit.com/r/{subreddit}/new.json"
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 429:
                logger.warning("reddit_rate_limited", subreddit=subreddit, page=page)
                await asyncio.sleep(10)
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("reddit_fetch_error", subreddit=subreddit, page=page, error=str(e))
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        after = data.get("data", {}).get("after")
        hit_cutoff = False

        for child in children:
            post = child.get("data", {})
            created_utc = post.get("created_utc", 0)

            # Stop if post is older than our lookback window (Jan 1, 2026)
            if created_utc < CUTOFF_TS:
                hit_cutoff = True
                break

            title = post.get("title", "")
            selftext = post.get("selftext", "")
            combined = title + " " + selftext

            # Apply outreach search terms
            if not SearchTermsManager.matches(combined, include_kw, exclude_kw):
                continue

            permalink = post.get("permalink", "")
            source_url = f"https://www.reddit.com{permalink}" if permalink else ""

            results.append({
                "title": title[:500],
                "content": selftext[:2000],
                "source_url": source_url,
                "source_id": f"reddit_{post.get('id', '')}",
                "subreddit": subreddit,
                "created_utc": created_utc,
                "posted_at": utc_ts_to_iso(created_utc),
                "score_reddit": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
                "author": post.get("author", ""),
            })

        if hit_cutoff or not after:
            break

        await asyncio.sleep(REDDIT_DELAY)

    return results


async def main():
    from cmo_agent.db.database import Database
    from cmo_agent.db.repositories import ConfigRepo, OpportunityRepo
    from cmo_agent.outreach.dashboard import (
        DEFAULT_EXCLUDE_TERMS,
        DEFAULT_INCLUDE_TERMS,
        OutreachDashboard,
    )
    from cmo_agent.outreach.search_terms import SearchTermsManager
    from cmo_agent.outreach.replies import OutreachReplyGenerator, split_reply_and_notes
    from cmo_agent.config import Settings

    settings = Settings()

    # Init DB
    db = Database(db_path=settings.db_path)
    await db.initialize()

    opp_repo = OpportunityRepo(db)
    config_repo = ConfigRepo(db)

    # Load search terms from DB (or defaults)
    include_kw, exclude_kw = await SearchTermsManager.get_keywords(config_repo, WORKSPACE_ID)
    if not include_kw:
        include_kw = DEFAULT_INCLUDE_TERMS
        exclude_kw = DEFAULT_EXCLUDE_TERMS

    print(f"Search terms loaded: {len(include_kw)} include, {len(exclude_kw)} exclude")
    print(f"Cutoff: Jan 1, 2026 ({datetime.fromtimestamp(CUTOFF_TS).isoformat()})")
    print(f"Subreddits: {', '.join(SUBREDDITS)}")
    print()

    # ── Phase 1: Scan Reddit ──────────────────────────────────────────
    all_posts: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        for sub in SUBREDDITS:
            print(f"Scanning r/{sub}...", end=" ", flush=True)
            posts = await fetch_reddit_paginated(client, sub, include_kw, exclude_kw)
            print(f"{len(posts)} matches")
            all_posts.extend(posts)
            await asyncio.sleep(REDDIT_DELAY)

    print(f"\nTotal Reddit matches: {len(all_posts)}")

    # ── Phase 2: Store in DB (with dedup + posted_at) ─────────────────
    stored = 0
    skipped_dedup = 0
    updated_posted_at = 0

    for post in all_posts:
        source_id = post["source_id"]
        posted_at_str = post["posted_at"]

        # Source-level dedup
        if await opp_repo.exists_by_source_id("reddit", source_id):
            # Existing record — backfill posted_at if missing
            await db.execute(
                "UPDATE opportunities SET posted_at = ? "
                "WHERE source = 'reddit' AND source_id = ? AND posted_at IS NULL",
                (posted_at_str, source_id),
            )
            updated_posted_at += 1
            skipped_dedup += 1
            continue

        # Cross-platform dedup
        content_hash = compute_content_hash(post["title"], post["content"])
        if await opp_repo.exists_by_content_hash(content_hash):
            skipped_dedup += 1
            continue

        # Score
        score_breakdown = score_outreach_post(post["title"], post["content"])
        total_score = sum(score_breakdown.values())

        # Store with posted_at
        await opp_repo.create(
            workspace_id=WORKSPACE_ID,
            source="reddit",
            title=post["title"],
            content=post["content"],
            source_url=post["source_url"],
            source_id=source_id,
            score=total_score,
            score_breakdown=score_breakdown,
            category="outreach",
            content_hash=content_hash,
            posted_at=posted_at_str,
        )

        # Set outreach_status for new posts
        row = await db.fetchone(
            "SELECT id FROM opportunities WHERE source = 'reddit' AND source_id = ?",
            (source_id,),
        )
        if row:
            await db.execute(
                "UPDATE opportunities SET outreach_status = 'new' WHERE id = ?",
                (row["id"],),
            )

        stored += 1

    print(f"Stored: {stored} new opportunities")
    print(f"Duplicates skipped: {skipped_dedup} ({updated_posted_at} had posted_at backfilled)")

    # ── Phase 3: Batch classify post types + assess risk ──────────────
    print("\nClassifying post types and assessing engagement risk...")

    from cmo_agent.llm.anthropic import AnthropicLLM

    llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model_writing,
        max_tokens=500,
        temperature=0.3,
    )
    reply_gen = OutreachReplyGenerator(llm)

    # Get unclassified posts
    rows = await db.fetchall(
        "SELECT id, title, content FROM opportunities "
        "WHERE workspace_id = ? AND category = 'outreach' "
        "AND (platform_post_type IS NULL OR engagement_risk IS NULL) "
        "ORDER BY created_at DESC LIMIT 200",
        (WORKSPACE_ID,),
    )

    classified = 0
    risk_assessed = 0
    for row in rows:
        opp_id = row["id"]
        title = row["title"] or ""
        content = row["content"] or ""

        # Classify post type
        post_type = await reply_gen.classify_post_type(title, content)
        await db.execute(
            "UPDATE opportunities SET platform_post_type = ? WHERE id = ? AND platform_post_type IS NULL",
            (post_type, opp_id),
        )
        classified += 1

        # Assess risk
        risk_level, reason = await reply_gen.assess_engagement_risk(title, content)
        risk_value = f"{risk_level}: {reason}" if risk_level != "none" else "none"
        await db.execute(
            "UPDATE opportunities SET engagement_risk = ? WHERE id = ? AND engagement_risk IS NULL",
            (risk_value, opp_id),
        )
        risk_assessed += 1

        if classified % 10 == 0:
            print(f"  ...{classified}/{len(rows)} classified")

    print(f"Classified: {classified} post types, {risk_assessed} risk assessments")

    # ── Phase 3b: Generate draft replies for posts missing them ───────
    print("\nGenerating draft replies for posts without one...")

    from cmo_agent.outreach.dashboard import CANNED_RESPONSES_SEED

    brand_voice_path = ROOT / "data" / "brand_voices" / "dsdn.txt"
    brand_voice = brand_voice_path.read_text() if brand_voice_path.exists() else ""

    no_reply_rows = await db.fetchall(
        "SELECT id, title, content, platform_post_type FROM opportunities "
        "WHERE workspace_id = ? AND category = 'outreach' "
        "AND (draft_reply IS NULL OR draft_reply = '') "
        "ORDER BY score DESC LIMIT 200",
        (WORKSPACE_ID,),
    )

    replies_generated = 0
    for row in no_reply_rows:
        opp_id = row["id"]
        title = row["title"] or ""
        content = row["content"] or ""
        post_type = row["platform_post_type"] or "seeking_community"

        reply_text, canned_used, warnings = await reply_gen.generate_reply(
            title=title,
            content=content,
            post_type=post_type,
            platform="reddit",
            canned_responses=CANNED_RESPONSES_SEED,
            brand_voice=brand_voice,
        )

        await db.execute(
            "UPDATE opportunities SET draft_reply = ?, canned_response_used = ?, "
            "outreach_status = CASE WHEN outreach_status = 'new' THEN 'draft_generated' ELSE outreach_status END "
            "WHERE id = ?",
            (reply_text, canned_used, opp_id),
        )
        replies_generated += 1

        if replies_generated % 10 == 0:
            print(f"  ...{replies_generated}/{len(no_reply_rows)} replies generated")

    print(f"Draft replies generated: {replies_generated}")

    # ── Phase 4: Rebuild Google Sheet ─────────────────────────────────
    print("\nRebuilding Google Sheet (new column layout with Post Date)...")

    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    spreadsheet_id = settings.outreach_spreadsheet_id

    creds = Credentials.from_authorized_user_file(
        oauth_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    service = build("sheets", "v4", credentials=creds)

    # Get Sheet ID for Outreach Queue tab
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

    # Clear existing data (preserve header row 1)
    service.spreadsheets().values().clear(
        spreadsheetId=spreadsheet_id,
        range="'Outreach Queue'!A1:R5000",
    ).execute()
    print("  Cleared existing Sheet data")

    # Write new headers (18 columns: A-R) — matches production layout in dashboard.py
    headers = [
        "Post Date",           # A (original post creation date)
        "Date Found",          # B (ingest timestamp)
        "Opportunity ID",      # C
        "Platform",            # D
        "Post Title/Summary",  # E
        "Post URL",            # F
        "Score",               # G
        "Post Type",           # H
        "Sensitivity?",        # I
        "Engagement Risk?",    # J
        "Draft Reply",         # K
        "Reviewer Notes",      # L
        "Status",              # M (dropdown)
        "Claimed Date/Time",   # N (auto-populated by Apps Script)
        "Claimed By",          # O (dropdown)
        "Response Notes",      # P
        "Response URL",        # Q
        "Outcome",             # R (dropdown)
    ]
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="'Outreach Queue'!A1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()
    print("  Wrote new headers (A-R)")

    # Load ALL outreach opportunities from DB and write to Sheet
    all_opps = await db.fetchall(
        "SELECT * FROM opportunities "
        "WHERE workspace_id = ? AND category = 'outreach' "
        "ORDER BY score DESC, created_at DESC",
        (WORKSPACE_ID,),
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
        opp_dict = dict(opp)
        sensitivity = "[SENSITIVE]" if _is_sensitive(
            opp_dict.get("platform_post_type"),
            opp_dict.get("score_breakdown"),
        ) else ""
        risk = opp_dict.get("engagement_risk", "none") or "none"
        risk_display = "None" if risk == "none" else risk
        title = opp_dict.get("title", "")
        content = opp_dict.get("content", "") or ""
        full_post = (title + "\n\n" + content).strip() if content else title
        status = opp_dict.get("outreach_status", "New") or "New"
        if status and status[0].islower():
            status = status.replace("_", " ").title()
        draft_raw = opp_dict.get("draft_reply", "") or ""
        reply_text, reviewer_notes = split_reply_and_notes(draft_raw)

        data_rows.append([
            opp_dict.get("posted_at", "") or "",           # A: Post Date
            opp_dict.get("created_at", "") or "",           # B: Date Found
            opp_dict.get("id", ""),                         # C: Opportunity ID
            opp_dict.get("source", ""),                     # D: Platform
            full_post,                                      # E: Post Title/Summary
            opp_dict.get("source_url", ""),                 # F: Post URL
            str(opp_dict.get("score", 0)),                  # G: Score
            opp_dict.get("platform_post_type", ""),         # H: Post Type
            sensitivity,                                    # I: Sensitivity?
            risk_display,                                   # J: Engagement Risk?
            reply_text,                                     # K: Draft Reply
            reviewer_notes,                                 # L: Reviewer Notes
            status,                                         # M: Status
            opp_dict.get("claimed_at", "") or "",           # N: Claimed Date/Time
            opp_dict.get("claimed_by", "") or "",           # O: Claimed By
            opp_dict.get("response_notes", "") or "",       # P: Response Notes
            opp_dict.get("response_url", "") or "",         # Q: Response URL
            opp_dict.get("outreach_outcome", "") or "",     # R: Outcome
        ])

    print(f"  Writing {len(data_rows)} rows to Sheet...")

    # Write in batches of 100
    for i in range(0, len(data_rows), 100):
        chunk = data_rows[i:i + 100]
        start_row = i + 2  # Row 1 is header
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'Outreach Queue'!A{start_row}",
            valueInputOption="RAW",
            body={"values": chunk},
        ).execute()
        print(f"  ...wrote rows {start_row}-{start_row + len(chunk) - 1}")

    # ── Phase 5: Apply dropdown validations ───────────────────────────
    print("\nApplying dropdown validations...")

    end_row = max(len(data_rows) + 51, 200)

    from cmo_agent.outreach.dashboard import build_dropdown_validation_request

    dropdown_requests = [
        build_dropdown_validation_request(queue_sheet_id, 12, "Status", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 14, "Claimed By", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 17, "Outcome", end_row=end_row),
    ]

    # Add Score column comment (column G, index 6)
    dropdown_requests.append({
        "updateCells": {
            "rows": [{
                "values": [{
                    "note": (
                        "Outreach Score (0-40)\n\n"
                        "Sum of 4 dimensions, each scored 0-10:\n"
                        "- Diagnosis Relevance: How specifically the post mentions a DS diagnosis\n"
                        "- Recency: How recently the post was made\n"
                        "- Urgency/Emotional Need: Signals of distress or isolation\n"
                        "- DSDN Fit: Is this person in DSDN's target demographic (diagnosis to age 3)?\n\n"
                        "Higher score = higher priority for outreach."
                    )
                }]
            }],
            "fields": "note",
            "range": {
                "sheetId": queue_sheet_id,
                "startRowIndex": 0,
                "endRowIndex": 1,
                "startColumnIndex": 6,   # G
                "endColumnIndex": 7,
            },
        }
    })

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": dropdown_requests},
    ).execute()
    print(f"  Dropdowns applied: Status (M), Claimed By (O), Outcome (R)")
    print(f"  Score note applied to column G header")

    await db.close()

    print(f"\n{'='*60}")
    print(f"Backfill complete!")
    print(f"  Reddit posts scanned: {len(all_posts)}")
    print(f"  New opportunities stored: {stored}")
    print(f"  Existing posted_at backfilled: {updated_posted_at}")
    print(f"  Duplicates skipped: {skipped_dedup}")
    print(f"  Post types classified: {classified}")
    print(f"  Draft replies generated: {replies_generated}")
    print(f"  Total rows written to Sheet: {len(data_rows)}")
    print(f"{'='*60}")

    # Remind about Apps Script update
    print(f"\nIMPORTANT: The Apps Script for auto-timestamp needs updating!")
    print(f"Column O (Claimed By) is now column 15 and column N (Claimed Date/Time) is column 14.")
    print(f"Update the Apps Script onEdit function:")
    print(f"  - Change range.getColumn() check to 15 (column O = Claimed By)")
    print(f"  - Change timestampCell column to 14 (column N = Claimed Date/Time)")


if __name__ == "__main__":
    asyncio.run(main())
