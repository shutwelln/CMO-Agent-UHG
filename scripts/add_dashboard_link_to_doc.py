#!/usr/bin/env python3
"""Add the outreach dashboard link to the existing Google Doc write-up."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DOC_ID = "1csMuYaWIipABUnDI8XBsUEYqo2sCP71tr2opKx3erKQ"
SHEET_URL = "https://docs.google.com/spreadsheets/d/1-G_t2waz2JiOdNbhinpHgb2iemUwrcK3uztNeU-HJUY/edit"


def main():
    from googleapiclient.discovery import build
    from cmo_agent.google_auth import get_google_credentials

    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json"))
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path=sa_path,
        scopes=[
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    docs = build("docs", "v1", credentials=creds)

    # Read the doc to find the insertion point — right after the "Executive Summary" heading
    doc = docs.documents().get(documentId=DOC_ID).execute()
    body = doc.get("body", {}).get("content", [])

    # Find the end of the Executive Summary heading paragraph
    insert_after = None
    for elem in body:
        if "paragraph" not in elem:
            continue
        para = elem["paragraph"]
        style = para.get("paragraphStyle", {})
        named_style = style.get("namedStyleType", "")
        if named_style == "HEADING_1":
            text = ""
            for el in para.get("elements", []):
                text += el.get("textRun", {}).get("content", "")
            if "Executive Summary" in text:
                insert_after = elem.get("endIndex")
                break

    if not insert_after:
        print("Could not find 'Executive Summary' heading.")
        return

    # Build the block: a "Quick Links" sub-heading + the dashboard link line
    link_label = "Outreach Dashboard (Google Sheet)"
    line1 = "Quick Links\n"
    line2 = f"{link_label}\n"
    line3 = "\n"  # spacer

    full_text = line1 + line2 + line3
    cursor = insert_after

    requests = [
        # Insert all text
        {"insertText": {"location": {"index": cursor}, "text": full_text}},

        # Style "Quick Links" as HEADING_2
        {
            "updateParagraphStyle": {
                "range": {"startIndex": cursor, "endIndex": cursor + len(line1)},
                "paragraphStyle": {
                    "namedStyleType": "HEADING_2",
                    "spaceAbove": {"magnitude": 10, "unit": "PT"},
                    "spaceBelow": {"magnitude": 4, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceAbove,spaceBelow",
            }
        },

        # Style the link line as normal text
        {
            "updateParagraphStyle": {
                "range": {
                    "startIndex": cursor + len(line1),
                    "endIndex": cursor + len(line1) + len(line2),
                },
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "spaceBelow": {"magnitude": 6, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceBelow",
            }
        },

        # Make the link label a hyperlink
        {
            "updateTextStyle": {
                "range": {
                    "startIndex": cursor + len(line1),
                    "endIndex": cursor + len(line1) + len(link_label),
                },
                "textStyle": {
                    "link": {"url": SHEET_URL},
                    "foregroundColor": {
                        "color": {"rgbColor": {"red": 0.067, "green": 0.333, "blue": 0.8}}
                    },
                    "underline": True,
                    "bold": True,
                },
                "fields": "link,foregroundColor,underline,bold",
            }
        },
    ]

    docs.documents().batchUpdate(documentId=DOC_ID, body={"requests": requests}).execute()
    print("Done! Added 'Quick Links' section with dashboard link after Executive Summary heading.")


if __name__ == "__main__":
    main()
