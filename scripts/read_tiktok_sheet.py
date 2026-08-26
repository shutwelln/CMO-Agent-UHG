"""Read the existing DSDN TikTok Google Sheet to understand its structure."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from googleapiclient.discovery import build
from cmo_agent.google_auth import get_google_credentials

SHEET_ID = "1jhQQ3YtWSPUZltD46h3Y5Izptx7JkZ-SO19P85aMN74"

creds = get_google_credentials(
    oauth_token_path="data/google-token.json",
    service_account_path="",
    scopes=["https://www.googleapis.com/auth/spreadsheets"],
)
service = build("sheets", "v4", credentials=creds)

# Read all tabs
for tab_name in ["Trends", "Content Packages", "Weekly Calendar", "Hook Formulas"]:
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range=f"'{tab_name}'!A1:Z5",
        ).execute()
        rows = result.get("values", [])
        print(f"\n=== {tab_name} ===")
        for i, row in enumerate(rows):
            print(f"  Row {i}: {row}")
    except Exception as e:
        print(f"\n=== {tab_name} === ERROR: {e}")
