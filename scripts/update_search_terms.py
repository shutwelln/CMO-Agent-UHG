#!/usr/bin/env python3
"""Replace Search Terms tab in the live outreach sheet with the full combination matrix."""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

SPREADSHEET_ID = "1-G_t2waz2JiOdNbhinpHgb2iemUwrcK3uztNeU-HJUY"


def main():
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import get_google_credentials
    from cmo_agent.outreach.dashboard import DEFAULT_EXCLUDE_TERMS, DEFAULT_INCLUDE_TERMS

    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path=sa_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    sheets = build("sheets", "v4", credentials=creds)

    today = datetime.now().strftime("%Y-%m-%d")

    # Build rows: headers + include terms + exclude terms
    headers = ["Term", "Type", "Platform", "Active", "Added By", "Date Added", "Notes"]
    rows = [headers]

    for term in DEFAULT_INCLUDE_TERMS:
        note = "AND combination" if "+" in term else "standalone"
        rows.append([term, "Include", "All", "Yes", "System", today, note])

    for term in DEFAULT_EXCLUDE_TERMS:
        rows.append([term, "Exclude", "All", "Yes", "System", today, "false positive filter"])

    # Clear existing data and write new
    sheets.spreadsheets().values().clear(
        spreadsheetId=SPREADSHEET_ID,
        range="'Search Terms'!A1:G500",
    ).execute()

    sheets.spreadsheets().values().update(
        spreadsheetId=SPREADSHEET_ID,
        range="'Search Terms'!A1",
        valueInputOption="RAW",
        body={"values": rows},
    ).execute()

    include_count = len(DEFAULT_INCLUDE_TERMS)
    exclude_count = len(DEFAULT_EXCLUDE_TERMS)
    combo_count = sum(1 for t in DEFAULT_INCLUDE_TERMS if "+" in t)
    standalone_count = include_count - combo_count

    print(f"Search Terms tab updated!")
    print(f"  Include terms: {include_count} ({standalone_count} standalone + {combo_count} AND combinations)")
    print(f"  Exclude terms: {exclude_count}")
    print(f"  Total rows: {include_count + exclude_count}")


if __name__ == "__main__":
    main()
