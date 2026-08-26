#!/usr/bin/env python3
"""One-time backfill: fetch full post content for existing Lead Queue rows.

Adds the "Full Content" header (column T) if missing, then fetches full
Reddit post bodies via the JSON API and writes them back to the sheet.

Usage:
    python scripts/backfill_lead_full_content.py [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any, Dict, List, Tuple

import requests
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

SPREADSHEET_ID = "1xnphzSpso_htOP1qX21B1zxx_R-Kvy99MrZ5Jfq2XAA"
CREDENTIALS_PATH = "data/saverwell-google-credentials.json"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
LOG_FILE = "data/backfill_full_content.log"

USER_AGENT = "SaverwellLeadBackfill/1.0"
REDDIT_DELAY = 1.0


def log(msg: str) -> None:
    """Print and write to log file."""
    print(msg)
    with open(LOG_FILE, "a") as f:
        f.write(msg + "\n")


def get_sheets_service():
    creds = Credentials.from_service_account_file(CREDENTIALS_PATH, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds)


def ensure_full_content_header(service) -> int:
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range="'Lead Queue'!1:1")
        .execute()
    )
    headers = result.get("values", [[]])[0]

    for i, h in enumerate(headers):
        if h.strip() == "Full Content":
            log(f"'Full Content' header at column {chr(65 + i) if i < 26 else chr(64 + i // 26) + chr(65 + i % 26)}")
            return i

    col_idx = len(headers)
    col_letter = chr(65 + col_idx) if col_idx < 26 else chr(64 + col_idx // 26) + chr(65 + col_idx % 26)
    service.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range=f"'Lead Queue'!{col_letter}1",
        valueInputOption="RAW",
        body={"values": [["Full Content"]]},
    ).execute()
    log(f"Added 'Full Content' header at column {col_letter}")
    return col_idx


def fetch_reddit_content(url: str, session: requests.Session) -> str:
    if not url:
        return ""
    clean_url = url.rstrip("/").split("?")[0] + ".json"
    try:
        resp = session.get(clean_url, allow_redirects=True, timeout=15)
        if resp.status_code != 200:
            return ""
        data = resp.json()
        if isinstance(data, list) and len(data) > 0:
            children = data[0].get("data", {}).get("children", [])
            if children:
                selftext = children[0].get("data", {}).get("selftext", "")
                if selftext in ("[removed]", "[deleted]", ""):
                    return ""
                return selftext
        return ""
    except Exception as e:
        log(f"  Error: {url} -> {e}")
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Clear log
    with open(LOG_FILE, "w") as f:
        f.write(f"Backfill started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")

    service = get_sheets_service()

    fc_col_idx = ensure_full_content_header(service)
    fc_col_letter = chr(65 + fc_col_idx) if fc_col_idx < 26 else chr(64 + fc_col_idx // 26) + chr(65 + fc_col_idx % 26)

    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=SPREADSHEET_ID, range="'Lead Queue'!A1:T5100")
        .execute()
    )
    all_rows = result.get("values", [])
    headers, data_rows = all_rows[0], all_rows[1:]
    log(f"Total rows: {len(data_rows)}")

    col: Dict[str, int] = {}
    for i, h in enumerate(headers):
        col[h.strip()] = i

    url_idx = col.get("Post URL", -1)
    platform_idx = col.get("Platform", -1)
    fc_idx = col.get("Full Content", fc_col_idx)

    if url_idx < 0:
        log("ERROR: Post URL column not found")
        sys.exit(1)

    needs_backfill: List[Tuple[int, str]] = []
    already_filled = 0

    for i, row in enumerate(data_rows):
        row_num = i + 2
        existing_fc = row[fc_idx].strip() if fc_idx < len(row) else ""
        if existing_fc:
            already_filled += 1
            continue
        url = row[url_idx].strip() if url_idx < len(row) else ""
        if not url or "reddit.com" not in url:
            continue
        needs_backfill.append((row_num, url))

    log(f"Already filled: {already_filled}")
    log(f"Need backfill: {len(needs_backfill)}")

    if args.dry_run:
        log("[DRY RUN] Exiting.")
        return

    fetched = 0
    empty = 0
    batch: List[Dict[str, Any]] = []

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for idx, (row_num, url) in enumerate(needs_backfill):
        content = fetch_reddit_content(url, session)

        if content:
            batch.append({
                "range": f"'Lead Queue'!{fc_col_letter}{row_num}",
                "values": [[content]],
            })
            fetched += 1
        else:
            empty += 1

        # Log every 25 rows
        if (idx + 1) % 25 == 0:
            log(f"  [{idx + 1}/{len(needs_backfill)}] fetched={fetched} empty={empty}")

        # Write every 50 fetched rows
        if len(batch) >= 50:
            service.spreadsheets().values().batchUpdate(
                spreadsheetId=SPREADSHEET_ID,
                body={"valueInputOption": "RAW", "data": batch},
            ).execute()
            log(f"  >> Wrote {len(batch)} to sheet")
            batch = []

        time.sleep(REDDIT_DELAY)

    # Final batch
    if batch:
        service.spreadsheets().values().batchUpdate(
            spreadsheetId=SPREADSHEET_ID,
            body={"valueInputOption": "RAW", "data": batch},
        ).execute()
        log(f"  >> Wrote final {len(batch)} to sheet")

    log(f"\nDone! fetched={fetched} empty={empty} total={len(needs_backfill)}")


if __name__ == "__main__":
    main()
