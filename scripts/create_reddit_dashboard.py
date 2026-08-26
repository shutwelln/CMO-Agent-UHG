#!/usr/bin/env python3
"""
Add Reddit posting tabs to the existing Saverwell Content Queue Google Sheet.

Adds two tabs:
  1. Reddit Calendar   - schedule, status tracking, and result metrics
  2. Reddit Posts      - full post titles and bodies for easy copy-paste

Usage:
    python scripts/create_reddit_dashboard.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

QUEUE_PATH = ROOT / "data" / "saverwell" / "reddit_post_queue.json"
SPREADSHEET_ID = "1kSVQwjzXO1R9af55DPSTmhq86ZH12u1ra3fcoll1-xE"


# ---------------------------------------------------------------------------
# Google auth
# ---------------------------------------------------------------------------


def get_sheets_service():
    """Build Sheets API service using service account."""
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import get_google_credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]

    sa_path = os.getenv(
        "GOOGLE_CREDENTIALS_PATH",
        str(ROOT / "data" / "saverwell-google-credentials.json"),
    )
    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH",
        str(ROOT / "data" / "google-token.json"),
    )

    creds = get_google_credentials(
        service_account_path=sa_path,
        oauth_token_path=oauth_path,
        scopes=scopes,
    )
    if creds is None:
        print("Error: No valid Google credentials found.")
        sys.exit(1)

    return build("sheets", "v4", credentials=creds)


# ---------------------------------------------------------------------------
# Queue + post content loaders
# ---------------------------------------------------------------------------


def load_queue() -> list[dict]:
    with open(QUEUE_PATH) as f:
        return json.load(f)


def read_post_body(post: dict) -> str:
    """Extract the body text from a post markdown file."""
    post_file = ROOT / post["post_file"]
    if not post_file.exists():
        return "(post file not found)"

    content = post_file.read_text()
    marker = "**Body:**"
    if marker in content:
        return content.split(marker, 1)[1].strip()

    parts = content.split("---")
    if len(parts) >= 2:
        return parts[-1].strip()
    return content.strip()


def clean_formatting(text: str) -> str:
    """Strip AI-style bold/header formatting from post body."""
    lines = text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        line = line.replace("\u2014", " - ").replace("\u2013", " - ")
        if re.match(r"^\*\*.*\*\*$", stripped):
            line = line.replace("**", "")
        elif "**" in line:
            line = re.sub(r"\*\*(.+?)\*\*", r"\1", line)
        cleaned.append(line)
    return "\n".join(cleaned)


# ---------------------------------------------------------------------------
# Check existing tabs
# ---------------------------------------------------------------------------


def get_existing_tabs(sheets_svc) -> dict[str, int]:
    """Return map of tab title -> sheetId."""
    meta = (
        sheets_svc.spreadsheets()
        .get(spreadsheetId=SPREADSHEET_ID, fields="sheets.properties")
        .execute()
    )
    return {s["properties"]["title"]: s["properties"]["sheetId"] for s in meta.get("sheets", [])}


# ---------------------------------------------------------------------------
# Add tabs
# ---------------------------------------------------------------------------


def add_tabs(sheets_svc, existing_tabs: dict) -> dict[str, int]:
    """Add Reddit Calendar and Reddit Posts tabs if they don't exist."""
    tabs_to_add = []
    for title in ["Reddit Calendar", "Reddit Posts"]:
        if title not in existing_tabs:
            tabs_to_add.append(title)

    if not tabs_to_add:
        print("  Both tabs already exist, skipping creation.")
        return existing_tabs

    requests = []
    for title in tabs_to_add:
        requests.append({"addSheet": {"properties": {"title": title}}})

    result = (
        sheets_svc.spreadsheets()
        .batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"requests": requests},
        )
        .execute()
    )

    # Collect new sheet IDs
    for reply in result.get("replies", []):
        props = reply.get("addSheet", {}).get("properties", {})
        if props:
            existing_tabs[props["title"]] = props["sheetId"]

    print(f"  Added tabs: {', '.join(tabs_to_add)}")
    return existing_tabs


# ---------------------------------------------------------------------------
# Tab 1: Reddit Calendar
# ---------------------------------------------------------------------------


def seed_calendar(sheets_svc, queue: list[dict]) -> None:
    """Populate the Reddit Calendar tab with headers and data."""
    headers = [
        "post_num",
        "week",
        "day",
        "subreddit",
        "title",
        "type",
        "status",
        "posted_date",
        "reddit_url",
        "upvotes_24h",
        "comments",
        "link_included",
        "notes",
    ]

    rows = [headers]
    for i, p in enumerate(queue):
        row_num = i + 2  # header is row 1, data starts at row 2
        post_type = "reddit_only" if p.get("source_guide") is None else "guide_adapted"
        # Status column uses a formula that pulls from the Reddit Posts tab
        status_formula = (
            f"=IFERROR(INDEX('Reddit Posts'!F:F,MATCH(A{row_num},'Reddit Posts'!A:A,0)),\"\")"
        )
        rows.append(
            [
                p["id"],
                f"week_{p['week']}",
                p.get("scheduled_day", "").lower(),
                f"r/{p['subreddit']}",
                p["title"],
                post_type,
                status_formula,
                p.get("posted_at") or "",
                p.get("reddit_url") or "",
                "",
                "",
                "no" if not p.get("includes_saverwell_link") else "yes",
                p.get("notes", ""),
            ]
        )

    # Use USER_ENTERED so formulas in column G are interpreted
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Reddit Calendar'!A1",
        valueInputOption="USER_ENTERED",
        body={"values": rows},
    ).execute()


# ---------------------------------------------------------------------------
# Tab 2: Reddit Posts (for copy-paste)
# ---------------------------------------------------------------------------


def seed_posts(sheets_svc, queue: list[dict]) -> None:
    """Populate the Reddit Posts tab with full text for easy copying."""
    headers = [
        "post_num",
        "subreddit",
        "title",
        "body",
        "word_count",
        "status",
    ]

    rows = [headers]
    for p in queue:
        body = clean_formatting(read_post_body(p))
        word_count = len(body.split())
        rows.append(
            [
                p["id"],
                f"r/{p['subreddit']}",
                p["title"],
                body,
                word_count,
                p["status"],
            ]
        )

    sheets_svc.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Reddit Posts'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def apply_formatting(sheets_svc, tab_ids: dict) -> None:
    """Apply header formatting, column widths, dropdowns, freezes, and text wrap."""
    cal_id = tab_ids.get("Reddit Calendar")
    posts_id = tab_ids.get("Reddit Posts")

    if cal_id is None or posts_id is None:
        print("  Warning: Could not find tab IDs for formatting.")
        return

    requests = []

    # -- Freeze header row on both tabs --
    for sheet_id in [cal_id, posts_id]:
        requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        )

    # -- Bold + green background on header rows --
    for sheet_id in [cal_id, posts_id]:
        requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sheet_id,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": {"red": 0.15, "green": 0.5, "blue": 0.25},
                            "textFormat": {
                                "bold": True,
                                "foregroundColor": {"red": 1, "green": 1, "blue": 1},
                            },
                        }
                    },
                    "fields": "userEnteredFormat(backgroundColor,textFormat)",
                }
            }
        )

    # -- Column widths for Reddit Calendar --
    cal_widths = {
        0: 70,  # post_num
        1: 80,  # week
        2: 100,  # day
        3: 150,  # subreddit
        4: 420,  # title
        5: 120,  # type
        6: 90,  # status
        7: 130,  # posted_date
        8: 300,  # reddit_url
        9: 100,  # upvotes_24h
        10: 90,  # comments
        11: 110,  # link_included
        12: 300,  # notes
    }
    for col, width in cal_widths.items():
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": cal_id,
                        "dimension": "COLUMNS",
                        "startIndex": col,
                        "endIndex": col + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )

    # -- Column widths for Reddit Posts --
    posts_widths = {
        0: 70,  # post_num
        1: 150,  # subreddit
        2: 420,  # title
        3: 800,  # body
        4: 90,  # word_count
        5: 90,  # status
    }
    for col, width in posts_widths.items():
        requests.append(
            {
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": posts_id,
                        "dimension": "COLUMNS",
                        "startIndex": col,
                        "endIndex": col + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            }
        )

    # -- Wrap text in body column (D) of Reddit Posts --
    requests.append(
        {
            "repeatCell": {
                "range": {
                    "sheetId": posts_id,
                    "startRowIndex": 1,
                    "endRowIndex": 50,
                    "startColumnIndex": 3,
                    "endColumnIndex": 4,
                },
                "cell": {
                    "userEnteredFormat": {"wrapStrategy": "WRAP"},
                },
                "fields": "userEnteredFormat.wrapStrategy",
            }
        }
    )

    # -- Status dropdown on Reddit Calendar (column G, index 6) --
    requests.append(
        {
            "setDataValidation": {
                "range": {
                    "sheetId": cal_id,
                    "startRowIndex": 1,
                    "endRowIndex": 50,
                    "startColumnIndex": 6,
                    "endColumnIndex": 7,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": "queued"},
                            {"userEnteredValue": "posted"},
                            {"userEnteredValue": "skipped"},
                            {"userEnteredValue": "failed"},
                        ],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        }
    )

    # -- link_included dropdown on Reddit Calendar (column L, index 11) --
    requests.append(
        {
            "setDataValidation": {
                "range": {
                    "sheetId": cal_id,
                    "startRowIndex": 1,
                    "endRowIndex": 50,
                    "startColumnIndex": 11,
                    "endColumnIndex": 12,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [
                            {"userEnteredValue": "no"},
                            {"userEnteredValue": "yes"},
                        ],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        }
    )

    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=SPREADSHEET_ID,
        body={"requests": requests},
    ).execute()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Loading post queue...")
    queue = load_queue()
    print(f"  {len(queue)} posts in queue")

    print("Authenticating with Google...")
    sheets_svc = get_sheets_service()

    print("Checking existing tabs...")
    existing_tabs = get_existing_tabs(sheets_svc)
    print(f"  Found: {', '.join(existing_tabs.keys())}")

    print("Adding Reddit tabs...")
    tab_ids = add_tabs(sheets_svc, existing_tabs)

    print("Populating Reddit Calendar...")
    seed_calendar(sheets_svc, queue)

    print("Populating Reddit Posts...")
    seed_posts(sheets_svc, queue)

    print("Applying formatting...")
    apply_formatting(sheets_svc, tab_ids)

    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}"
    print("\nDone! Reddit tabs added to your Content Queue sheet.")
    print(f"URL: {url}")
    print("\nHow to post:")
    print("  1. Open the 'Reddit Posts' tab")
    print("  2. Copy the title (column C) into Reddit's title field")
    print("  3. Copy the body (column D) into Reddit's post body")
    print("  4. Update status to 'posted' on the 'Reddit Calendar' tab")
    print("  5. Fill in reddit_url, upvotes_24h, and comments for tracking")


if __name__ == "__main__":
    main()
