#!/usr/bin/env python3
"""Cross-Reddit keyword search test — what posts are we missing?

Two experiments in one script:
  1. Search ALL of Reddit for 10 high-signal phrases, categorize results by
     subreddit (existing vs new), and check DB dedup status.
  2. Fetch ALL posts from r/downsyndrome (no keyword filter) for the last
     5 days. Compare total vs keyword-matched to find gaps.

Results go to a new "Cross-Reddit Test" tab in the outreach Google Sheet.
The script is read-only against the DB (dedup checks only, no writes).
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── Config ──────────────────────────────────────────────────────────────

REDDIT_USER_AGENT = "DSDN-Outreach-Test/1.0 (nonprofit; https://www.dsdiagnosisnetwork.org)"
REDDIT_DELAY = 2.0  # seconds between requests
WORKSPACE_ID = "dsdn"

# CST = UTC-6 (fixed offset, matches dashboard.py convention)
_CST = timezone(timedelta(hours=-6))

# Last 7 days for cross-Reddit search (Reddit search uses t=week)
# Last 5 days for r/downsyndrome unfiltered scan
UNFILTERED_DAYS = 5
UNFILTERED_CUTOFF = datetime.now(tz=timezone.utc) - timedelta(days=UNFILTERED_DAYS)

# The 10 existing subreddits we already scan
EXISTING_SUBREDDITS: Set[str] = {
    "downsyndrome",
    "babybumps",
    "newparents",
    "nicuparents",
    "specialneedsparenting",
    "sciencebasedparenting",
    "nipt",
    "pregnancyafterloss",
    "pregnant",
    "beyondthebump",
}

# 10 high-signal search terms for cross-Reddit search
SEARCH_TERMS = [
    "down syndrome diagnosis",
    "trisomy 21",
    "NIPT positive",
    "down syndrome baby",
    "T21 diagnosis",
    "just found out down syndrome",
    "prenatal diagnosis down syndrome",
    "amniocentesis down syndrome",
    "down syndrome support",
    "down syndrome newborn",
]

# ── DS-Context Keywords (life-stage filter for DS-specific subreddits) ──
# In r/downsyndrome or r/NIPT, the topic is already Down syndrome.
# We just need to detect: is this a new/expectant parent in the 0-3 window?

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
    """Convert Unix timestamp to CST display string (M/D/YYYY h:MM AM/PM)."""
    dt = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(_CST)
    return dt.strftime("%-m/%-d/%Y %-I:%M %p")


def utc_ts_to_iso(ts: float) -> str:
    """Convert Unix timestamp to ISO datetime string."""
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def truncate(text: str, length: int = 100) -> str:
    """Truncate text to length, adding ellipsis if needed."""
    if not text:
        return ""
    text = text.replace("\n", " ").strip()
    if len(text) <= length:
        return text
    return text[: length - 3] + "..."


# ── Phase 1: Cross-Reddit Keyword Search ────────────────────────────────


async def search_reddit(
    client: httpx.AsyncClient,
    query: str,
) -> List[Dict[str, Any]]:
    """Search all of Reddit for a phrase. Returns parsed post dicts."""
    url = "https://www.reddit.com/search.json"
    params = {
        "q": f'"{query}"',  # exact phrase match
        "sort": "new",
        "t": "week",
        "limit": 100,
    }

    posts: List[Dict[str, Any]] = []

    try:
        resp = await client.get(url, params=params)
        if resp.status_code == 429:
            print(f"    Rate limited on '{query}', waiting 10s...")
            await asyncio.sleep(10)
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    ERROR searching '{query}': {e}")
        return posts

    children = data.get("data", {}).get("children", [])

    for child in children:
        post = child.get("data", {})
        if post.get("is_self") is False and not post.get("selftext"):
            # Link posts with no selftext — still include, title may be relevant
            pass

        subreddit = post.get("subreddit", "")
        title = post.get("title", "")
        selftext = post.get("selftext", "")
        permalink = post.get("permalink", "")
        created_utc = post.get("created_utc", 0)

        posts.append(
            {
                "reddit_id": post.get("id", ""),
                "source_id": f"reddit_{post.get('id', '')}",
                "subreddit": subreddit,
                "subreddit_lower": subreddit.lower(),
                "title": title[:500],
                "selftext": selftext[:2000],
                "source_url": f"https://www.reddit.com{permalink}" if permalink else "",
                "created_utc": created_utc,
                "score": post.get("score", 0),
                "num_comments": post.get("num_comments", 0),
            }
        )

    return posts


async def run_cross_reddit_search(
    client: httpx.AsyncClient,
    opp_repo: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, Dict[str, Any]], Dict[str, List[str]]]:
    """Run cross-Reddit search for all 10 terms.

    Returns:
        new_sub_posts: posts from subreddits NOT in our existing list
        term_stats: per-term result counts
        sub_posts_map: subreddit -> list of search terms that found posts there
    """
    # Dedup across search terms (same post may match multiple terms)
    seen_ids: Set[str] = set()

    # Posts from NEW subreddits (the main finding)
    new_sub_posts: List[Dict[str, Any]] = []

    # Per-term stats
    term_stats: Dict[str, Dict[str, Any]] = {}

    # Per new-subreddit: which terms found posts there
    sub_terms_map: Dict[str, List[str]] = defaultdict(list)

    # Aggregate counters
    total_results = 0
    total_in_db = 0
    total_existing_sub = 0
    total_new_sub = 0

    for term in SEARCH_TERMS:
        print(f'  Searching: "{term}"...', end=" ", flush=True)
        posts = await search_reddit(client, term)
        print(f"{len(posts)} results")

        term_in_db = 0
        term_existing = 0
        term_new = 0

        for post in posts:
            rid = post["reddit_id"]
            if rid in seen_ids:
                continue
            seen_ids.add(rid)
            total_results += 1

            # Check if already in our DB
            in_db = await opp_repo.exists_by_source_id("reddit", post["source_id"])
            if in_db:
                total_in_db += 1
                term_in_db += 1
                continue

            # Check if from an existing subreddit
            if post["subreddit_lower"] in EXISTING_SUBREDDITS:
                total_existing_sub += 1
                term_existing += 1
            else:
                total_new_sub += 1
                term_new += 1
                post["search_term"] = term
                new_sub_posts.append(post)
                sub_terms_map[post["subreddit"]].append(term)

        term_stats[term] = {
            "total": len(posts),
            "unique": term_in_db + term_existing + term_new,
            "in_db": term_in_db,
            "existing_sub": term_existing,
            "new_sub": term_new,
        }

        await asyncio.sleep(REDDIT_DELAY)

    # Store aggregates on term_stats for summary
    term_stats["__totals__"] = {
        "total_results": total_results,
        "in_db": total_in_db,
        "existing_sub": total_existing_sub,
        "new_sub": total_new_sub,
    }

    return new_sub_posts, term_stats, dict(sub_terms_map)


# ── Phase 2: r/downsyndrome Unfiltered Scan ─────────────────────────────


async def fetch_subreddit_all(
    client: httpx.AsyncClient,
    subreddit: str,
    cutoff_ts: float,
    max_pages: int = 10,
) -> List[Dict[str, Any]]:
    """Fetch ALL posts from a subreddit back to cutoff date (no keyword filter)."""
    url = f"https://www.reddit.com/r/{subreddit}/new.json"
    after: Optional[str] = None
    posts: List[Dict[str, Any]] = []

    for page in range(max_pages):
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
        after = data.get("data", {}).get("after")
        hit_cutoff = False

        for child in children:
            post = child.get("data", {})
            created_utc = post.get("created_utc", 0)

            if created_utc < cutoff_ts:
                hit_cutoff = True
                break

            title = post.get("title", "")
            selftext = post.get("selftext", "")
            permalink = post.get("permalink", "")

            posts.append(
                {
                    "reddit_id": post.get("id", ""),
                    "title": title[:500],
                    "selftext": selftext[:2000],
                    "source_url": f"https://www.reddit.com{permalink}" if permalink else "",
                    "created_utc": created_utc,
                    "score": post.get("score", 0),
                }
            )

        if hit_cutoff or not after:
            break

        await asyncio.sleep(REDDIT_DELAY)

    return posts


def check_keyword_match(
    posts: List[Dict[str, Any]],
    include_kw: List[str],
    exclude_kw: List[str],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Split posts into matched vs unmatched against our keywords."""
    from cmo_agent.outreach.search_terms import SearchTermsManager

    matched = []
    unmatched = []

    for post in posts:
        combined = post["title"] + " " + (post["selftext"] or "")
        if SearchTermsManager.matches(combined, include_kw, exclude_kw):
            post["matched_keywords"] = True
            matched.append(post)
        else:
            post["matched_keywords"] = False
            unmatched.append(post)

    return matched, unmatched


# ── Phase 3: Write to Google Sheet ──────────────────────────────────────


def write_to_sheet(
    spreadsheet_id: str,
    new_sub_posts: List[Dict[str, Any]],
    ds_all: List[Dict[str, Any]],
    ds_matched: List[Dict[str, Any]],
    ds_unmatched: List[Dict[str, Any]],
    ds_ctx_all: Optional[List[Dict[str, Any]]] = None,
    ds_ctx_matched: Optional[List[Dict[str, Any]]] = None,
    ds_ctx_unmatched: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """Create/overwrite 'Cross-Reddit Test' tab with results."""
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

    service = build("sheets", "v4", credentials=creds)
    tab_name = "Cross-Reddit Test"

    # ── Find or create the tab ──────────────────────────────────────────
    sheet_meta = (
        service.spreadsheets()
        .get(spreadsheetId=spreadsheet_id, fields="sheets.properties")
        .execute()
    )
    tab_sheet_id = None
    for sheet in sheet_meta.get("sheets", []):
        if sheet["properties"]["title"] == tab_name:
            tab_sheet_id = sheet["properties"]["sheetId"]
            break

    if tab_sheet_id is not None:
        # Clear existing data
        service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=f"'{tab_name}'!A1:Z5000",
        ).execute()
        print(f"  Cleared existing '{tab_name}' tab")
    else:
        # Add new tab
        add_req = {
            "requests": [
                {
                    "addSheet": {
                        "properties": {"title": tab_name},
                    }
                }
            ]
        }
        resp = (
            service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=add_req).execute()
        )
        tab_sheet_id = resp["replies"][0]["addSheet"]["properties"]["sheetId"]
        print(f"  Created new '{tab_name}' tab")

    # ── Section A: Posts from new subreddits ─────────────────────────────
    rows: List[List[str]] = []

    # Title row
    rows.append(
        [
            "=== SECTION A: Posts from NEW Subreddits (not in our scan list) ===",
            "",
            "",
            "",
            "",
            "",
            "",
        ]
    )
    rows.append([])  # blank row

    # Headers
    rows.append(
        [
            "Post Date (CST)",
            "Subreddit",
            "Post Title",
            "Post URL",
            "Score",
            "Search Term Matched",
            "Full Content",
        ]
    )

    # Sort by subreddit then date
    sorted_posts = sorted(
        new_sub_posts,
        key=lambda p: (p["subreddit"].lower(), -p["created_utc"]),
    )

    for post in sorted_posts:
        rows.append(
            [
                utc_ts_to_cst(post["created_utc"]),
                f"r/{post['subreddit']}",
                post["title"],
                post["source_url"],
                str(post["score"]),
                post.get("search_term", ""),
                post.get("selftext", ""),
            ]
        )

    if not sorted_posts:
        rows.append(["(No posts found from new subreddits)", "", "", "", "", "", ""])

    # ── Section B: r/downsyndrome unfiltered ─────────────────────────────
    rows.append([])  # blank separator
    rows.append([])
    rows.append(
        [
            f"=== SECTION B: r/downsyndrome Unfiltered (last {UNFILTERED_DAYS} days) ===",
            "",
            "",
            "",
            "",
        ]
    )
    rows.append(
        [
            f"Total posts: {len(ds_all)}  |  "
            f"Matched keywords: {len(ds_matched)} ({_pct(len(ds_matched), len(ds_all))})  |  "
            f"Did NOT match: {len(ds_unmatched)} ({_pct(len(ds_unmatched), len(ds_all))})",
            "",
            "",
            "",
            "",
        ]
    )
    rows.append([])

    rows.append(
        [
            "Post Date (CST)",
            "Post Title",
            "Post URL",
            "Matched Keywords?",
            "Score",
            "Full Content",
        ]
    )

    # Show ALL posts, unmatched first (those are the interesting ones)
    all_ds_sorted = sorted(ds_unmatched, key=lambda p: -p["created_utc"]) + sorted(
        ds_matched, key=lambda p: -p["created_utc"]
    )

    for post in all_ds_sorted:
        rows.append(
            [
                utc_ts_to_cst(post["created_utc"]),
                post["title"],
                post["source_url"],
                "Yes" if post.get("matched_keywords") else "NO",
                str(post["score"]),
                post.get("selftext", ""),
            ]
        )

    # ── Section C: DS-context life-stage filter results ──────────────────
    if ds_ctx_all is not None:
        ds_ctx_matched = ds_ctx_matched or []
        ds_ctx_unmatched = ds_ctx_unmatched or []

        rows.append([])  # blank separator
        rows.append([])
        rows.append(
            [
                f"=== SECTION C: DS-Context Life-Stage Filter (last {UNFILTERED_DAYS} days) ===",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        rows.append(
            [
                f"Total posts: {len(ds_ctx_all)}  |  "
                f"Matched DS-context: {len(ds_ctx_matched)} ({_pct(len(ds_ctx_matched), len(ds_ctx_all))})  |  "
                f"Not matched (likely outside 0-3): {len(ds_ctx_unmatched)} ({_pct(len(ds_ctx_unmatched), len(ds_ctx_all))})",
                "",
                "",
                "",
                "",
                "",
                "",
            ]
        )
        rows.append([])

        rows.append(
            [
                "Post Date (CST)",
                "Post Title",
                "Post URL",
                "DS-Context Match?",
                "Score",
                "DS-Context Terms Hit",
                "Full Content",
            ]
        )

        # Show unmatched first (the ones filtered OUT — should be older-kid/off-topic)
        ctx_sorted = sorted(ds_ctx_unmatched, key=lambda p: -p["created_utc"]) + sorted(
            ds_ctx_matched, key=lambda p: -p["created_utc"]
        )

        for post in ctx_sorted:
            terms_hit = ", ".join(post.get("ds_context_terms_matched", [])[:8])
            rows.append(
                [
                    utc_ts_to_cst(post["created_utc"]),
                    post["title"],
                    post["source_url"],
                    "YES — 0-3 scope" if post.get("matched_keywords") else "NO — filtered out",
                    str(post["score"]),
                    terms_hit,
                    post.get("selftext", ""),
                ]
            )

    # ── Write all rows ──────────────────────────────────────────────────
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()
    print(f"  Wrote {len(rows)} rows to '{tab_name}' tab")


def _pct(part: int, total: int) -> str:
    """Format a percentage string, handling zero total."""
    if total == 0:
        return "0%"
    return f"{part * 100 // total}%"


# ── Phase 4: Print Summary ──────────────────────────────────────────────


def print_summary(
    term_stats: Dict[str, Dict[str, Any]],
    sub_terms_map: Dict[str, List[str]],
    ds_all: List[Dict[str, Any]],
    ds_matched: List[Dict[str, Any]],
    ds_unmatched: List[Dict[str, Any]],
) -> None:
    """Print human-readable summary to console."""
    totals = term_stats.get("__totals__", {})

    print("\n" + "=" * 60)
    print("CROSS-REDDIT SEARCH RESULTS (last 7 days)")
    print("=" * 60)
    print()
    print(f"Search queries run:          {len(SEARCH_TERMS)}")
    print(f"Total unique results:        {totals.get('total_results', 0)}")
    print(f"  Already in DB:             {totals.get('in_db', 0)}  (we have these)")
    print(
        f"  From existing subreddits:  {totals.get('existing_sub', 0)}"
        f"  (would catch via current approach)"
    )
    new_count = totals.get("new_sub", 0)
    print(f"  From NEW subreddits:       {new_count}  <-- THIS IS THE NUMBER THAT MATTERS")
    print()

    # New subreddits discovered
    if sub_terms_map:
        print("New subreddits discovered:")
        # Sort by post count descending
        sorted_subs = sorted(sub_terms_map.items(), key=lambda x: -len(x[1]))
        for sub, terms in sorted_subs:
            unique_terms = list(dict.fromkeys(terms))  # preserve order, dedup
            print(
                f"  r/{sub:<25s} {len(terms)} post(s)  "
                f"(terms: {', '.join(repr(t) for t in unique_terms[:3])})"
            )
        print()

    # Search term effectiveness
    print("Search term effectiveness:")
    sorted_terms = sorted(
        [(t, s) for t, s in term_stats.items() if t != "__totals__"],
        key=lambda x: -x[1]["total"],
    )
    for term, stats in sorted_terms:
        print(
            f'  "{term}"'
            f"{' ' * max(1, 42 - len(term))}"
            f"-> {stats['total']} results"
            f"  (new subs: {stats['new_sub']},"
            f" existing: {stats['existing_sub']},"
            f" in DB: {stats['in_db']})"
        )

    print()
    print()
    print("=" * 60)
    print(f"r/downsyndrome UNFILTERED (last {UNFILTERED_DAYS} days)")
    print("=" * 60)
    print()
    total = len(ds_all)
    matched = len(ds_matched)
    unmatched = len(ds_unmatched)
    print(f"Total posts:              {total}")
    print(f"Matched our keywords:     {matched} ({_pct(matched, total)})")
    print(
        f"Did NOT match keywords:   {unmatched} ({_pct(unmatched, total)})"
        f"  <-- posts we'd gain by full-scanning this sub"
    )
    print()

    if ds_unmatched:
        print("Non-keyword-matching post titles (review for relevance):")
        for post in sorted(ds_unmatched, key=lambda p: -p["created_utc"]):
            print(f"  - {post['title'][:90]}")
        print()

    # Caveats
    print("NOTE: Reddit search is known to be incomplete. Results are a lower")
    print("bound — actual missed posts could be higher due to indexing gaps.")
    print()


# ── Main ────────────────────────────────────────────────────────────────


async def main() -> None:
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database
    from cmo_agent.db.repositories import ConfigRepo, OpportunityRepo
    from cmo_agent.outreach.dashboard import DEFAULT_EXCLUDE_TERMS, DEFAULT_INCLUDE_TERMS
    from cmo_agent.outreach.search_terms import SearchTermsManager

    settings = Settings()

    # Init DB (read-only — we only check dedup, never write)
    db = Database(db_path=settings.db_path)
    await db.initialize()
    opp_repo = OpportunityRepo(db)
    config_repo = ConfigRepo(db)

    # Load search terms for keyword matching
    include_kw, exclude_kw = await SearchTermsManager.get_keywords(config_repo, WORKSPACE_ID)
    if not include_kw:
        include_kw = DEFAULT_INCLUDE_TERMS
        exclude_kw = DEFAULT_EXCLUDE_TERMS
    print(f"Loaded {len(include_kw)} include terms, {len(exclude_kw)} exclude terms")
    print(f"Existing subreddits: {', '.join(sorted(EXISTING_SUBREDDITS))}")
    print()

    async with httpx.AsyncClient(
        headers={"User-Agent": REDDIT_USER_AGENT},
        timeout=15.0,
        follow_redirects=True,
    ) as client:
        # ── Experiment 1: Cross-Reddit keyword search ───────────────────
        print("=" * 60)
        print("EXPERIMENT 1: Cross-Reddit Keyword Search")
        print("=" * 60)
        print()

        new_sub_posts, term_stats, sub_terms_map = await run_cross_reddit_search(client, opp_repo)

        # ── Experiment 2: r/downsyndrome unfiltered ─────────────────────
        print()
        print("=" * 60)
        print("EXPERIMENT 2: r/downsyndrome Unfiltered Scan")
        print("=" * 60)
        print()

        cutoff_ts = UNFILTERED_CUTOFF.timestamp()
        print(
            f"  Fetching ALL posts from r/downsyndrome (last {UNFILTERED_DAYS} days)...",
            end=" ",
            flush=True,
        )
        ds_all = await fetch_subreddit_all(client, "downsyndrome", cutoff_ts)
        print(f"{len(ds_all)} posts")

        ds_matched, ds_unmatched = check_keyword_match(ds_all, include_kw, exclude_kw)

    await db.close()

    # ── Experiment 3: DS-context keyword filter ───────────────────────
    print()
    print("=" * 60)
    print("EXPERIMENT 3: DS-Context Life-Stage Filter")
    print("=" * 60)
    print()
    print(f"  DS-context include terms: {len(DS_CONTEXT_INCLUDE_TERMS)}")
    print(f"  DS-context exclude terms: {len(DS_CONTEXT_EXCLUDE_TERMS)}")
    print()

    # Re-classify all r/downsyndrome posts with the DS-context filter
    # Make fresh copies so we don't mutate the Experiment 2 flags
    import copy

    ds_all_copy = copy.deepcopy(ds_all)
    ds_ctx_matched, ds_ctx_unmatched = check_keyword_match(
        ds_all_copy, DS_CONTEXT_INCLUDE_TERMS, DS_CONTEXT_EXCLUDE_TERMS
    )

    # Also tag each post with which DS-context terms matched
    from cmo_agent.outreach.search_terms import SearchTermsManager

    for post in ds_all_copy:
        combined = post["title"] + " " + (post.get("selftext") or "")
        hits = []
        for term in DS_CONTEXT_INCLUDE_TERMS:
            if "+" in term:
                parts = [p.strip() for p in term.split("+") if p.strip()]
                if parts and all(SearchTermsManager._term_present(p, combined.lower()) for p in parts):
                    hits.append(term)
            else:
                if SearchTermsManager._term_present(term, combined.lower()):
                    hits.append(term)
        post["ds_context_terms_matched"] = hits

    ctx_total = len(ds_all_copy)
    ctx_matched = len(ds_ctx_matched)
    ctx_unmatched = len(ds_ctx_unmatched)

    print(f"  Total r/downsyndrome posts:      {ctx_total}")
    print(f"  Matched DS-context keywords:      {ctx_matched} ({_pct(ctx_matched, ctx_total)})")
    print(f"  Did NOT match DS-context:          {ctx_unmatched} ({_pct(ctx_unmatched, ctx_total)})")
    print()

    if ds_ctx_matched:
        print("  CAUGHT by DS-context filter:")
        for post in sorted(ds_ctx_matched, key=lambda p: -p["created_utc"]):
            terms = ", ".join(post.get("ds_context_terms_matched", [])[:5])
            print(f"    + {post['title'][:70]}  [{terms}]")
        print()

    if ds_ctx_unmatched:
        print("  MISSED by DS-context filter (review — likely outside 0-3 scope):")
        for post in sorted(ds_ctx_unmatched, key=lambda p: -p["created_utc"]):
            print(f"    - {post['title'][:90]}")
        print()

    # ── Write to Google Sheet ───────────────────────────────────────────
    spreadsheet_id = settings.outreach_spreadsheet_id
    if spreadsheet_id:
        print()
        print("Writing results to Google Sheet...")
        write_to_sheet(
            spreadsheet_id,
            new_sub_posts,
            ds_all,
            ds_matched,
            ds_unmatched,
            ds_all_copy,
            ds_ctx_matched,
            ds_ctx_unmatched,
        )
    else:
        print()
        print("WARNING: OUTREACH_SPREADSHEET_ID not set — skipping Sheet write.")
        print("Set it in .env to enable Google Sheet output.")

    # ── Print summary ───────────────────────────────────────────────────
    print_summary(term_stats, sub_terms_map, ds_all, ds_matched, ds_unmatched)


if __name__ == "__main__":
    asyncio.run(main())
