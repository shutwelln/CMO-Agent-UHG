#!/usr/bin/env python3
"""Backfill DS-specific subreddits using life-stage keyword filter.

Scans r/downsyndrome and r/NIPT back to Jan 1, 2026 using DS-context keywords
(life-stage signals for the 0-3 / prenatal window). Runs the full outreach
pipeline: scoring, post-type classification, engagement risk assessment, and
draft reply generation. Results go to two new Google Sheet tabs:

  - "DS Subreddit Terms"  — editable include/exclude keyword list
  - "DS Subreddit Queue"  — matched posts in Outreach Queue format (A-Q)

Read-only against the DB (dedup checks only, no writes).
Does NOT touch the existing Outreach Queue, Search Terms, or other tabs.
"""

from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── Config ──────────────────────────────────────────────────────────────

REDDIT_USER_AGENT = "DSDN-Outreach-DSScan/1.0 (nonprofit; https://www.dsdiagnosisnetwork.org)"
REDDIT_DELAY = 2.0
MAX_PAGES_PER_SUB = 10  # up to 10 pages x 100 = 1000 posts per subreddit
WORKSPACE_ID = "dsdn"

_CST = timezone(timedelta(hours=-6))

# Go back to January 1, 2026 00:00 UTC
CUTOFF_DT = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
CUTOFF_TS = CUTOFF_DT.timestamp()

# DS-specific subreddits — topic is already Down syndrome
DS_SUBREDDITS = [
    "downsyndrome",
    "NIPT",
]

# ── DS-Context Keywords ─────────────────────────────────────────────────
# Life-stage filter for 0-3 / prenatal window.
# These are written to the "DS Subreddit Terms" tab so the team can edit them.

DS_CONTEXT_INCLUDE_TERMS = [
    # Prenatal / expecting
    "pregnant",
    "expecting",
    "due date",
    "ultrasound",
    "anatomy scan",
    "prenatal",
    "trimester",
    "first trimester",
    "second trimester",
    "weeks pregnant",
    "weeks along",
    "maternity",
    "OB",
    "midwife",
    # Diagnosis / screening
    "just found out",
    "diagnosed",
    "diagnosis",
    "results came back",
    "positive result",
    "screening",
    "NIPT",
    "NIPT positive",
    "amniocentesis",
    "amnio",
    "CVS",
    "chorionic villus",
    "genetic counselor",
    "karyotype",
    "soft markers",
    "nuchal translucency",
    "quad screen",
    "trisomy 21",
    "T21",
    "extra chromosome",
    # Newborn / baby (0-12 months)
    "baby",
    "newborn",
    "just born",
    "born with",
    "weeks old",
    "months old",
    "days old",
    "NICU",
    "delivery",
    "labor",
    "birth",
    "gave birth",
    "c-section",
    "breastfeeding",
    "feeding",
    "latch",
    "formula",
    "pediatrician",
    "heart defect",
    "AV canal",
    "duodenal atresia",
    "Hirschsprung",
    # Toddler / early childhood (1-3 years)
    "toddler",
    "infant",
    "early intervention",
    "EI",
    "therapy",
    "speech therapy",
    "physical therapy",
    "occupational therapy",
    "milestone",
    "milestones",
    "crawling",
    "walking",
    "first steps",
    "first words",
    # Emotional / new parent signals
    "scared",
    "terrified",
    "overwhelmed",
    "grieving",
    "support",
    "support group",
    "connect with other parents",
    "what to expect",
    "resources",
    "new to this",
    "new here",
    "just joined",
    "our journey",
]

DS_CONTEXT_EXCLUDE_TERMS = [
    # Older child / adult signals (outside 0-3 window)
    "teenager",
    "teen",
    "high school",
    "middle school",
    "elementary school",
    "college",
    "university",
    "adult child",
    "group home",
    "independent living",
    "retirement",
    "aging parent",
    # Off-topic
    "down syndrome cat",
    "stock market down",
    "Nintendo DS",
    "DS game",
    "sundown syndrome",
]


# ── Helpers ─────────────────────────────────────────────────────────────


def utc_ts_to_cst(ts: float) -> str:
    """Convert Unix timestamp to CST display string."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(_CST)
    return dt.strftime("%-m/%-d/%Y %-I:%M %p")


def utc_ts_to_iso(ts: float) -> str:
    """Convert Unix timestamp to ISO datetime string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def score_outreach_post(title: str, content: str) -> Dict[str, int]:
    """Score using the 4-dimension outreach scoring (same as backfill script)."""
    combined = (title + " " + (content or "")).lower()

    # Diagnosis relevance (0-10)
    relevance = 1
    high_rel = [
        "just found out",
        "got the results",
        "nipt came back",
        "nipt positive",
        "amnio results",
        "diagnosed",
        "prenatal diagnosis",
        "trisomy 21 positive",
        "t21 positive",
    ]
    mid_rel = [
        "diagnosis",
        "testing",
        "amniocentesis",
        "cvs results",
        "genetic counselor",
        "nipt",
        "trisomy 21",
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
        "scared",
        "terrified",
        "don't know what to do",
        "feeling alone",
        "need help",
        "crying",
        "devastated",
        "heartbroken",
        "shocked",
        "overwhelmed",
        "lost",
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
    high_fit = [
        "expecting",
        "pregnant",
        "prenatal",
        "newborn",
        "just born",
        "baby",
        "nicu",
        "born with",
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


# ── Reddit Fetching ─────────────────────────────────────────────────────


async def fetch_subreddit_filtered(
    client: httpx.AsyncClient,
    subreddit: str,
    include_kw: List[str],
    exclude_kw: List[str],
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch posts from a subreddit back to CUTOFF, applying keyword filter.

    Returns (matched_posts, total_scanned).
    """
    from cmo_agent.outreach.search_terms import SearchTermsManager

    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    after: Optional[str] = None
    matched: List[Dict[str, Any]] = []
    total_scanned = 0

    for page in range(MAX_PAGES_PER_SUB):
        params: Dict[str, Any] = {"limit": 100}
        if after:
            params["after"] = after

        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 429:
                print(f"    Rate limited on r/{subreddit} page {page + 1}, waiting 10s...")
                await asyncio.sleep(10)
                resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"    ERROR fetching r/{subreddit} page {page + 1}: {e}")
            break

        children = data.get("data", {}).get("children", [])
        if not children:
            break

        after = data.get("data", {}).get("after")
        hit_cutoff = False

        for child in children:
            post = child.get("data", {})
            created_utc = post.get("created_utc", 0)

            if created_utc < CUTOFF_TS:
                hit_cutoff = True
                break

            total_scanned += 1
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            combined = title + " " + selftext

            if not SearchTermsManager.matches(combined, include_kw, exclude_kw):
                continue

            permalink = post.get("permalink", "")
            source_url = f"https://www.reddit.com{permalink}" if permalink else ""

            matched.append(
                {
                    "title": title[:500],
                    "content": selftext[:5000],
                    "source_url": source_url,
                    "source_id": f"reddit_{post.get('id', '')}",
                    "subreddit": subreddit,
                    "created_utc": created_utc,
                    "posted_at": utc_ts_to_iso(created_utc),
                    "score_reddit": post.get("score", 0),
                    "num_comments": post.get("num_comments", 0),
                    "author": post.get("author", ""),
                }
            )

        if hit_cutoff or not after:
            break

        await asyncio.sleep(REDDIT_DELAY)

    return matched, total_scanned


# ── LLM Pipeline (classify, risk, reply) ────────────────────────────────


async def run_llm_pipeline(
    posts: List[Dict[str, Any]],
    settings: Any,
) -> None:
    """Run post-type classification, risk assessment, and reply generation.

    Mutates each post dict in-place with: post_type, engagement_risk,
    draft_reply, score, score_breakdown, sensitivity.
    """
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
        if risk_level != "none":
            post["engagement_risk"] = f"{risk_level}: {reason}"
        else:
            post["engagement_risk"] = "none"

        # Sensitivity
        post["sensitivity"] = is_sensitive(post_type, breakdown)

        # Generate draft reply
        reply_text, canned_used, warnings = await reply_gen.generate_reply(
            title=title,
            content=content,
            post_type=post_type,
            platform="reddit",
            canned_responses=CANNED_RESPONSES_SEED,
            brand_voice=brand_voice,
        )
        post["draft_reply"] = reply_text

        if (i + 1) % 10 == 0 or (i + 1) == total:
            print(f"  ...{i + 1}/{total} processed")


# ── Google Sheet Writing ────────────────────────────────────────────────


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
            # Clear existing data
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"'{tab_name}'!A1:Z5000",
            ).execute()
            print(f"  Cleared existing '{tab_name}' tab")
            return sheet["properties"]["sheetId"]

    # Create new tab
    add_req = {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]}
    resp = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=add_req).execute()
    sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
    print(f"  Created new '{tab_name}' tab")
    return sheet_id


def write_terms_tab(service: Any, spreadsheet_id: str) -> None:
    """Write DS-context keywords to the 'DS Subreddit Terms' tab."""
    tab_name = "DS Subreddit Terms"
    find_or_create_tab(service, spreadsheet_id, tab_name)

    rows: List[List[str]] = []

    # Header
    rows.append(["Include Terms", "", "Exclude Terms"])
    rows.append(
        [
            f"({len(DS_CONTEXT_INCLUDE_TERMS)} terms — "
            "life-stage signals for 0-3 / prenatal window)",
            "",
            f"({len(DS_CONTEXT_EXCLUDE_TERMS)} terms — older child / off-topic filters)",
        ]
    )
    rows.append([])  # blank row

    # Category headers
    rows.append(["Category", "Term", "Exclude Term"])

    # Build include terms with categories
    include_categorized: List[Tuple[str, str]] = []
    cat = "Prenatal / expecting"
    for term in DS_CONTEXT_INCLUDE_TERMS:
        if term == "just found out":
            cat = "Diagnosis / screening"
        elif term == "baby":
            cat = "Newborn / baby (0-12 months)"
        elif term == "toddler":
            cat = "Toddler / early childhood (1-3)"
        elif term == "scared":
            cat = "Emotional / new parent signals"
        include_categorized.append((cat, term))

    # Merge include and exclude into rows
    max_rows = max(len(include_categorized), len(DS_CONTEXT_EXCLUDE_TERMS))
    for i in range(max_rows):
        row: List[str] = []
        if i < len(include_categorized):
            row.append(include_categorized[i][0])
            row.append(include_categorized[i][1])
        else:
            row.append("")
            row.append("")
        if i < len(DS_CONTEXT_EXCLUDE_TERMS):
            row.append(DS_CONTEXT_EXCLUDE_TERMS[i])
        else:
            row.append("")
        rows.append(row)

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()
    print(f"  Wrote {len(rows)} rows to '{tab_name}' tab")


def write_queue_tab(
    service: Any,
    spreadsheet_id: str,
    posts: List[Dict[str, Any]],
    existing_ids: Set[str],
    settings: Any,
) -> None:
    """Write matched posts to 'DS Subreddit Queue' in Outreach Queue format (A-R)."""
    tab_name = "DS Subreddit Queue"
    queue_sheet_id = find_or_create_tab(service, spreadsheet_id, tab_name)

    # Headers — EXACT same order as the Outreach Queue tab (A-R)
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
        "Claimed Date/Time",   # N
        "Claimed By",          # O (dropdown)
        "Response Notes",      # P
        "Response URL",        # Q
        "Outcome",             # R (dropdown)
    ]

    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()
    print(f"  Wrote headers (A-R) to '{tab_name}'")

    # Build data rows — sort by score descending (highest priority first)
    now_str = utc_ts_to_iso(datetime.now(tz=timezone.utc).timestamp())

    sorted_posts = sorted(posts, key=lambda p: -p.get("score", 0))

    from cmo_agent.outreach.replies import split_reply_and_notes

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

        draft_raw = post.get("draft_reply", "")
        reply_text, reviewer_notes = split_reply_and_notes(draft_raw)

        data_rows.append(
            [
                post.get("posted_at", ""),      # A: Post Date
                now_str,                         # B: Date Found
                post.get("source_id", ""),       # C: Opportunity ID
                "reddit",                        # D: Platform
                full_post,                       # E: Post Title/Summary
                post.get("source_url", ""),      # F: Post URL
                str(post.get("score", 0)),       # G: Score
                post_type,                       # H: Post Type
                sensitivity,                     # I: Sensitivity?
                risk_display,                    # J: Engagement Risk?
                reply_text,                      # K: Draft Reply
                reviewer_notes,                  # L: Reviewer Notes
                status,                          # M: Status
                "",                              # N: Claimed Date/Time
                "",                              # O: Claimed By
                "",                              # P: Response Notes
                "",                              # Q: Response URL
                "",                              # R: Outcome
            ]
        )

    # Write in batches of 100
    print(f"  Writing {len(data_rows)} rows to '{tab_name}'...")
    for i in range(0, len(data_rows), 100):
        chunk = data_rows[i : i + 100]
        start_row = i + 2  # Row 1 is header
        service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A{start_row}",
            valueInputOption="RAW",
            body={"values": chunk},
        ).execute()
        if len(data_rows) > 100:
            print(f"    ...wrote rows {start_row}-{start_row + len(chunk) - 1}")

    # ── Apply dropdown validations (same as Outreach Queue) ─────────────
    print("  Applying dropdowns...")

    end_row = max(len(data_rows) + 51, 200)

    from cmo_agent.outreach.dashboard import build_dropdown_validation_request

    dropdown_requests = [
        build_dropdown_validation_request(queue_sheet_id, 12, "Status", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 14, "Claimed By", end_row=end_row),
        build_dropdown_validation_request(queue_sheet_id, 17, "Outcome", end_row=end_row),
        # Score column note (column G, index 6)
        {
            "updateCells": {
                "rows": [
                    {
                        "values": [
                            {
                                "note": (
                                    "Outreach Score (0-40)\n\n"
                                    "Sum of 4 dimensions, each scored 0-10:\n"
                                    "- Diagnosis Relevance\n"
                                    "- Recency\n"
                                    "- Urgency/Emotional Need\n"
                                    "- DSDN Fit (diagnosis to age 3)\n\n"
                                    "Higher score = higher priority."
                                )
                            }
                        ]
                    }
                ],
                "fields": "note",
                "range": {
                    "sheetId": queue_sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 6,
                    "endColumnIndex": 7,
                },
            }
        },
    ]

    service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": dropdown_requests},
    ).execute()
    print("  Dropdowns applied: Status (M), Claimed By (O), Outcome (R)")

    print(f"  Done — {len(data_rows)} rows in '{tab_name}'")


# ── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database
    from cmo_agent.db.repositories import OpportunityRepo

    settings = Settings()

    # Init DB (read-only — dedup checks only)
    db = Database(db_path=settings.db_path)
    await db.initialize()
    opp_repo = OpportunityRepo(db)

    print(f"DS-context include terms: {len(DS_CONTEXT_INCLUDE_TERMS)}")
    print(f"DS-context exclude terms: {len(DS_CONTEXT_EXCLUDE_TERMS)}")
    print(f"Subreddits: {', '.join('r/' + s for s in DS_SUBREDDITS)}")
    print(f"Cutoff: {CUTOFF_DT.strftime('%b %d, %Y')}")
    print()

    # ── Phase 1: Scan DS subreddits ─────────────────────────────────────
    print("=" * 60)
    print("Phase 1: Scanning DS subreddits with life-stage filter")
    print("=" * 60)
    print()

    all_posts: List[Dict[str, Any]] = []
    total_scanned = 0

    async with httpx.AsyncClient(
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        for sub in DS_SUBREDDITS:
            print(f"  Scanning r/{sub}...", end=" ", flush=True)
            posts, scanned = await fetch_subreddit_filtered(
                client, sub, DS_CONTEXT_INCLUDE_TERMS, DS_CONTEXT_EXCLUDE_TERMS
            )
            print(f"{scanned} posts scanned, {len(posts)} matched")
            all_posts.extend(posts)
            total_scanned += scanned
            await asyncio.sleep(REDDIT_DELAY)

    print(f"\nTotal: {total_scanned} posts scanned, {len(all_posts)} matched")

    # ── Phase 2: Dedup check against DB ─────────────────────────────────
    print("\n" + "=" * 60)
    print("Phase 2: Dedup check against existing DB")
    print("=" * 60)
    print()

    existing_ids: Set[str] = set()
    for post in all_posts:
        if await opp_repo.exists_by_source_id("reddit", post["source_id"]):
            existing_ids.add(post["source_id"])

    new_count = len(all_posts) - len(existing_ids)
    print(f"  Already in DB: {len(existing_ids)}")
    print(f"  New (not in Outreach Queue): {new_count}")

    await db.close()

    # ── Phase 3: LLM pipeline (classify, risk, reply) ───────────────────
    print("\n" + "=" * 60)
    print("Phase 3: Scoring, classification, risk assessment, draft replies")
    print("=" * 60)

    await run_llm_pipeline(all_posts, settings)

    # ── Phase 4: Write to Google Sheet ──────────────────────────────────
    spreadsheet_id = settings.outreach_spreadsheet_id
    if not spreadsheet_id:
        print("\nERROR: OUTREACH_SPREADSHEET_ID not set in .env")
        return

    print("\n" + "=" * 60)
    print("Phase 4: Writing to Google Sheet")
    print("=" * 60)
    print()

    service = get_sheets_service()

    # Write the editable terms tab
    write_terms_tab(service, spreadsheet_id)

    # Write the queue tab (Outreach Queue format)
    write_queue_tab(service, spreadsheet_id, all_posts, existing_ids, settings)

    # ── Summary ─────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print()
    print(f"Subreddits scanned:    {', '.join('r/' + s for s in DS_SUBREDDITS)}")
    print("Date range:            Jan 1, 2026 - present")
    print(f"Total posts scanned:   {total_scanned}")
    print(f"Matched DS-context:    {len(all_posts)}")
    print(f"  Already in DB:       {len(existing_ids)}")
    print(f"  NEW for review:      {new_count}")
    print()

    for sub in DS_SUBREDDITS:
        sub_posts = [p for p in all_posts if p["subreddit"] == sub]
        sub_new = [p for p in sub_posts if p["source_id"] not in existing_ids]
        print(f"  r/{sub}: {len(sub_posts)} matched ({len(sub_new)} new)")

    print()
    print("Google Sheet tabs:")
    print('  - "DS Subreddit Terms" — editable keyword list')
    print('  - "DS Subreddit Queue" — full Outreach Queue format with draft replies')
    print()


if __name__ == "__main__":
    asyncio.run(main())
