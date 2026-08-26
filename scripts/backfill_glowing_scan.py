#!/usr/bin/env python3
"""Backfill Glowing.com outreach scan.

Scans active Glowing.com pregnancy groups for posts mentioning Down syndrome,
trisomy 21, NIPT results, and related topics. Runs the full outreach pipeline:
scoring, post-type classification, engagement risk assessment, and draft reply
generation. Results go to a "Glowing Queue" Google Sheet tab in the same A-Q
format as the Outreach Queue.

Groups scanned:
  - General Pregnancy (4.8M members, very active)
  - Pregnancy & Child Loss (TFMR / loss posts)
  - First Time Moms (3M members)

Read-only against the DB (dedup checks only, no writes).
Does NOT touch the existing Outreach Queue or DS Subreddit Queue tabs.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── Config ──────────────────────────────────────────────────────────────

GLOWING_USER_AGENT = "DSDN-Outreach/1.0 (nonprofit family support; https://www.dsdiagnosisnetwork.org)"
GLOWING_DELAY = 2.0
WORKSPACE_ID = "dsdn"

_CST = timezone(timedelta(hours=-6))

# Go back to January 1, 2026 00:00 UTC
CUTOFF_DT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
CUTOFF_TS = CUTOFF_DT.timestamp()

# Active groups to scan
GLOWING_GROUPS = [
    {
        "id": "72057594037927937",
        "slug": "general-pregnancy",
        "name": "General Pregnancy",
        "max_pages": 20,
    },
    {
        "id": "72057594037928001",
        "slug": "pregnancy-child-loss",
        "name": "Pregnancy & Child Loss",
        "max_pages": 5,
    },
    {
        "id": "72057594037928009",
        "slug": "first-time-moms",
        "name": "First Time Moms",
        "max_pages": 5,
    },
]


# ── Helpers ─────────────────────────────────────────────────────────────


def utc_ts_to_iso(ts: float) -> str:
    """Convert Unix timestamp to ISO datetime string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def strip_html(html_str: str) -> str:
    """Strip HTML tags and decode entities."""
    text = re.sub(r"<[^>]+>", " ", html_str)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def score_outreach_post(title: str, content: str) -> Dict[str, int]:
    """Score using the 4-dimension outreach scoring."""
    combined = (title + " " + (content or "")).lower()

    # Diagnosis relevance (0-10)
    relevance = 1
    high_rel = [
        "just found out", "got the results", "nipt came back",
        "nipt positive", "amnio results", "diagnosed",
        "prenatal diagnosis", "trisomy 21 positive", "t21 positive",
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
    mid_urg = ["worried", "confused", "what should i expect", "nervous", "anxious"]
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
    high_fit = [
        "expecting", "pregnant", "prenatal", "newborn",
        "just born", "baby", "nicu", "born with",
    ]
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

    return {
        "diagnosis_relevance": relevance,
        "recency": recency,
        "urgency": urgency,
        "dsdn_fit": fit,
    }


def is_sensitive(post_type: Optional[str], score_breakdown: Dict[str, int]) -> bool:
    """Check if a post is sensitive (loss or high urgency)."""
    if post_type == "loss":
        return True
    return score_breakdown.get("urgency", 0) >= 9


# ── Glowing.com Fetching ───────────────────────────────────────────────


def extract_topics_from_html(html: str) -> List[Dict[str, Any]]:
    """Extract topics JSON from Glowing.com page HTML."""
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)
    for s in scripts:
        if '"topics"' in s and len(s) > 1000:
            idx = s.find("{")
            if idx >= 0:
                bracket_count = 0
                for j in range(idx, len(s)):
                    if s[j] == "{":
                        bracket_count += 1
                    elif s[j] == "}":
                        bracket_count -= 1
                        if bracket_count == 0:
                            try:
                                data = json.loads(s[idx : j + 1])
                                return data.get("topics", [])
                            except json.JSONDecodeError:
                                continue
    return []


async def fetch_glowing_group(
    client: httpx.AsyncClient,
    group: Dict[str, Any],
    include_kw: List[str],
    exclude_kw: List[str],
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch posts from a Glowing.com group, applying keyword filter.

    Returns (matched_posts, total_scanned).
    """
    from cmo_agent.outreach.search_terms import SearchTermsManager

    group_id = group["id"]
    slug = group["slug"]
    name = group["name"]
    max_pages = group.get("max_pages", 10)

    matched: List[Dict[str, Any]] = []
    total_scanned = 0

    for page in range(1, max_pages + 1):
        url = f"https://glowing.com/community/group/{group_id}/{slug}?page={page}"

        try:
            resp = await client.get(url)
            if resp.status_code != 200:
                print(f"    Page {page}: HTTP {resp.status_code}, stopping")
                break
        except Exception as e:
            print(f"    Page {page}: ERROR {e}")
            break

        topics = extract_topics_from_html(resp.text)
        if not topics:
            break

        hit_cutoff = False
        for topic in topics:
            created_ts = topic.get("time_created", 0)
            if created_ts < CUTOFF_TS:
                hit_cutoff = True
                break

            total_scanned += 1
            title = topic.get("title", "")
            content_html = topic.get("content", "")
            content = strip_html(content_html)
            combined = title + " " + content

            if not SearchTermsManager.matches(combined, include_kw, exclude_kw):
                continue

            topic_url = topic.get("url", "")
            if topic_url and not topic_url.startswith("http"):
                topic_url = f"https://glowing.com{topic_url}"

            topic_id = topic.get("id", "")
            matched.append(
                {
                    "title": title[:500],
                    "content": content[:5000],
                    "source_url": topic_url,
                    "source_id": f"glowing_{topic_id}",
                    "group_name": name,
                    "created_utc": created_ts,
                    "posted_at": utc_ts_to_iso(created_ts),
                    "count_replies": topic.get("count_replies", 0),
                    "count_likes": topic.get("count_likes", 0),
                }
            )

        if hit_cutoff:
            break

        await asyncio.sleep(GLOWING_DELAY)

    return matched, total_scanned


# ── LLM Pipeline ───────────────────────────────────────────────────────


async def run_llm_pipeline(
    posts: List[Dict[str, Any]],
    settings: Any,
) -> None:
    """Classify, risk-assess, and draft replies for each post. Mutates in-place."""
    from cmo_agent.llm.anthropic import AnthropicLLM
    from cmo_agent.outreach.dashboard import CANNED_RESPONSES_SEED
    from cmo_agent.outreach.replies import OutreachReplyGenerator

    llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model_writing,
        max_tokens=500,
        temperature=0.3,
    )
    reply_gen = OutreachReplyGenerator(llm)

    brand_voice_path = ROOT / "data" / "brand_voices" / "dsdn.txt"
    brand_voice = brand_voice_path.read_text() if brand_voice_path.exists() else ""

    total = len(posts)
    print(f"\nRunning LLM pipeline on {total} posts...")

    for i, post in enumerate(posts):
        title = post["title"]
        content = post.get("content", "")

        # Score
        breakdown = score_outreach_post(title, content)
        total_score = sum(breakdown.values())
        post["score_breakdown"] = breakdown
        post["score"] = total_score

        # Classify post type
        post_type = await reply_gen.classify_post_type(title, content)
        post["post_type"] = post_type

        # Assess engagement risk
        risk_level, reason = await reply_gen.assess_engagement_risk(title, content)
        post["engagement_risk"] = f"{risk_level}: {reason}" if risk_level != "none" else "none"

        # Sensitivity
        post["sensitivity"] = is_sensitive(post_type, breakdown)

        # Generate draft reply (use "glowing" platform for tone)
        reply_text, canned_used, warnings = await reply_gen.generate_reply(
            title=title,
            content=content,
            post_type=post_type,
            platform="glowing",
            canned_responses=CANNED_RESPONSES_SEED,
            brand_voice=brand_voice,
        )
        post["draft_reply"] = reply_text

        if (i + 1) % 10 == 0 or (i + 1) == total:
            print(f"  ...{i + 1}/{total} processed")


# ── Google Sheet Writing ───────────────────────────────────────────────


def get_sheets_service():
    """Build authenticated Google Sheets service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    creds = Credentials.from_authorized_user_file(
        oauth_path,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        Path(oauth_path).write_text(creds.to_json())

    return build("sheets", "v4", credentials=creds)


def find_or_create_tab(service: Any, spreadsheet_id: str, tab_name: str) -> int:
    """Find existing tab or create a new one. Returns sheet ID."""
    sheet_meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
        .execute()
    )
    for sheet in sheet_meta.get("sheets", []):
        if sheet["properties"]["title"] == tab_name:
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab_name}'!A1:Z5000",
            ).execute()
            print(f"  Cleared existing '{tab_name}' tab")
            return sheet["properties"]["sheetId"]

    add_req = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
    resp = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=add_req).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"  Created new '{tab_name}' tab")
    return sheet_id


def write_queue_tab(
    service: Any,
    spreadsheet_id: str,
    posts: List[Dict[str, Any]],
    existing_ids: Set[str],
    settings: Any,
) -> None:
    """Write matched posts to 'Glowing Queue' in Outreach Queue format (A-Q)."""
    tab_name = "Glowing Queue"
    queue_sheet_id = find_or_create_tab(service, spreadsheet_id, tab_name)

    # Headers — EXACT same order as the Outreach Queue tab (A-Q)
    headers = [
        "Post Date",           # A
        "Date Found",          # B
        "Opportunity ID",      # C
        "Platform",            # D
        "Post Title/Summary",  # E
        "Post URL",            # F
        "Score",               # G
        "Post Type",           # H
        "Sensitivity?",        # I
        "Engagement Risk?",    # J
        "Draft Reply",         # K
        "Status",              # L
        "Claimed Date/Time",   # M
        "Claimed By",          # N
        "Response Notes",      # O
        "Response URL",        # P
        "Outcome",             # Q
    ]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()
    print(f"  Wrote headers (A-Q) to '{tab_name}'")

    now_str = utc_ts_to_iso(datetime.now(tz=timezone.utc).timestamp())
    sorted_posts = sorted(posts, key=lambda p: -p.get("score", 0))

    data_rows: List[List[str]] = []
    for post in sorted_posts:
        sensitivity = "[SENSITIVE]" if post.get("sensitivity") else ""
        risk = post.get("engagement_risk", "none") or "none"
        risk_display = "None" if risk == "none" else risk

        title = post["title"]
        content = post.get("content", "") or ""
        full_post = (title + "\n\n" + content).strip() if content else title

        in_db = post["source_id"] in existing_ids
        status = "Already in Outreach Queue" if in_db else "New"

        post_type = post.get("post_type", "")
        if post_type:
            post_type = post_type.replace("_", " ").title()

        data_rows.append(
            [
                post.get("posted_at", ""),      # A: Post Date
                now_str,                         # B: Date Found
                post.get("source_id", ""),       # C: Opportunity ID
                "glowing",                       # D: Platform
                full_post,                       # E: Post Title/Summary
                post.get("source_url", ""),      # F: Post URL
                str(post.get("score", 0)),       # G: Score
                post_type,                       # H: Post Type
                sensitivity,                     # I: Sensitivity?
                risk_display,                    # J: Engagement Risk?
                post.get("draft_reply", ""),     # K: Draft Reply
                status,                          # L: Status
                "",                              # M: Claimed Date/Time
                "",                              # N: Claimed By
                "",                              # O: Response Notes
                "",                              # P: Response URL
                "",                              # Q: Outcome
            ]
        )

    # Write in batches of 100
    print(f"  Writing {len(data_rows)} rows to '{tab_name}'...")
    for i in range(0, len(data_rows), 100):
        chunk = data_rows[i : i + 100]
        start_row = i + 2
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A{start_row}",
            valueInputOption="RAW",
            body={"values": chunk},
        ).execute()
        if len(data_rows) > 100:
            print(f"    ...wrote rows {start_row}-{start_row + len(chunk) - 1}")

    # Apply dropdown validations
    print("  Applying dropdowns...")
    end_row = max(len(data_rows) + 51, 200)

    from cmo_agent.outreach.dashboard import build_dropdown_validation_request

    dropdown_requests = [
        build_dropdown_validation_request(queue_sheet_id, 11, "Status", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 13, "Claimed By", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 16, "Outcome", end_row=end_row),
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": dropdown_requests},
    ).execute()
    print("  Dropdowns applied (ONE_OF_RANGE → Dropdowns tab): Status (L), Claimed By (N), Outcome (Q)")
    print(f"  Done — {len(data_rows)} rows in '{tab_name}'")


# ── Main ───────────────────────────────────────────────────────────────


async def main() -> None:
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database
    from cmo_agent.db.repositories import OpportunityRepo
    from cmo_agent.outreach.dashboard import DEFAULT_EXCLUDE_TERMS, DEFAULT_INCLUDE_TERMS

    settings = Settings()

    # Init DB (read-only — dedup checks only)
    db = Database(db_path=settings.db_path)
    await db.initialize()
    opp_repo = OpportunityRepo(db)

    # Use standard outreach keywords (designed for finding DS posts in general contexts)
    include_kw = list(DEFAULT_INCLUDE_TERMS)
    exclude_kw = list(DEFAULT_EXCLUDE_TERMS)

    print(f"Outreach include terms: {len(include_kw)}")
    print(f"Outreach exclude terms: {len(exclude_kw)}")
    print(f"Glowing groups: {len(GLOWING_GROUPS)}")
    print(f"Cutoff: {CUTOFF_DT.strftime('%b %d, %Y')}")
    print()

    # ── Phase 1: Scan Glowing groups ─────────────────────────────────────
    print("=" * 60)
    print("Phase 1: Scanning Glowing.com groups")
    print("=" * 60)
    print()

    all_posts: List[Dict[str, Any]] = []
    total_scanned = 0

    async with httpx.AsyncClient(
        headers={"User-Agent": GLOWING_USER_AGENT},
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        for group in GLOWING_GROUPS:
            print(f"  Scanning {group['name']}...", flush=True)
            posts, scanned = await fetch_glowing_group(
                client, group, include_kw, exclude_kw
            )
            print(f"    {scanned} posts scanned, {len(posts)} matched")
            all_posts.extend(posts)
            total_scanned += scanned
            await asyncio.sleep(GLOWING_DELAY)

    print(f"\nTotal: {total_scanned} posts scanned, {len(all_posts)} matched")

    if not all_posts:
        print("\nNo matching posts found. Nothing to write.")
        await db.close()
        return

    # ── Phase 2: Dedup check against DB ──────────────────────────────────
    print("\n" + "=" * 60)
    print("Phase 2: Dedup check against existing DB")
    print("=" * 60)
    print()

    existing_ids: Set[str] = set()
    for post in all_posts:
        if await opp_repo.exists_by_source_id("glowing", post["source_id"]):
            existing_ids.add(post["source_id"])

    new_count = len(all_posts) - len(existing_ids)
    print(f"  Already in DB: {len(existing_ids)}")
    print(f"  New: {new_count}")

    await db.close()

    # ── Phase 3: LLM pipeline ────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Phase 3: Scoring, classification, risk assessment, draft replies")
    print("=" * 60)

    await run_llm_pipeline(all_posts, settings)

    # ── Phase 4: Write to Google Sheet ───────────────────────────────────
    spreadsheet_id = settings.outreach_spreadsheet_id
    if not spreadsheet_id:
        print("\nERROR: OUTREACH_SPREADSHEET_ID not set in .env")
        return

    print("\n" + "=" * 60)
    print("Phase 4: Writing to Google Sheet")
    print("=" * 60)
    print()

    service = get_sheets_service()
    write_queue_tab(service, spreadsheet_id, all_posts, existing_ids, settings)

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()
    print("Platform:              Glowing.com")
    print(f"Groups scanned:        {len(GLOWING_GROUPS)}")
    print(f"Date range:            Jan 1, 2026 - present")
    print(f"Total posts scanned:   {total_scanned}")
    print(f"Matched keywords:      {len(all_posts)}")
    print(f"  Already in DB:       {len(existing_ids)}")
    print(f"  NEW for review:      {new_count}")
    print()

    for group in GLOWING_GROUPS:
        gname = group["name"]
        g_posts = [p for p in all_posts if p["group_name"] == gname]
        g_new = [p for p in g_posts if p["source_id"] not in existing_ids]
        print(f"  {gname}: {len(g_posts)} matched ({len(g_new)} new)")

    print()
    print("Google Sheet tab:")
    print('  - "Glowing Queue" — Outreach Queue format with draft replies')
    print()


if __name__ == "__main__":
    asyncio.run(main())
