"""Add column header notes to the existing Saverwell Content Queue Google Sheet.

Adds hover-over notes to every header cell across all 3 tabs so that
anyone editing the sheet understands what each column means.

Usage:
    python scripts/add_content_queue_notes.py
"""

from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

SHEET_ID = "1kSVQwjzXO1R9af55DPSTmhq86ZH12u1ra3fcoll1-xE"

# ───────────────────────────────────────────────────────────────────
# Column descriptions for each tab
# ───────────────────────────────────────────────────────────────────

ARTICLE_LIBRARY_NOTES = [
    (
        "slug",
        "Unique URL-friendly identifier for this article. "
        "Used by the system to look up article content and track sends. "
        "Do not change.",
    ),
    (
        "title",
        "Full display title of the article as it appears on the "
        "website and in email subject lines.",
    ),
    (
        "category",
        'Content type: "protection" (fraud/safety articles sent on '
        'Tuesdays) or "guide" (educational Medicare/insurance articles '
        "sent on Thursdays).",
    ),
    (
        "vertical",
        'Topic area this article belongs to (e.g., "fraud", "medicare"). '
        "Used for seasonal boosting - when a seasonal window targets a "
        "vertical, all articles in that vertical get the boost.",
    ),
    (
        "base_priority",
        "Year-round importance score from 1 to 10. Higher number = "
        "sent sooner to new subscribers.\n\n"
        "10 = send first (e.g., Medicare enrollment deadlines)\n"
        "7-9 = high priority, broad appeal\n"
        "4-6 = standard priority\n"
        "1-3 = niche or lower urgency\n\n"
        "Effective priority = base_priority + seasonal_boost_amount "
        "(during boost window). You can edit this to reprioritize articles.",
    ),
    (
        "send_day",
        "Day of the week this article type is emailed. Protection "
        'articles = "tuesday", guide articles = "thursday". '
        "This keeps a predictable cadence for subscribers.",
    ),
    (
        "seasonal_boost_start",
        "Date when this article's seasonal priority boost begins. "
        "Format: YYYY-MM-DD. Leave blank if no seasonal boost applies.\n\n"
        "Example: 2026-10-01 for Medicare AEP ramp-up.",
    ),
    (
        "seasonal_boost_end",
        "Date when this article's seasonal priority boost ends. "
        "Format: YYYY-MM-DD. Leave blank if no seasonal boost applies.\n\n"
        "Example: 2026-12-07 for Medicare AEP close.",
    ),
    (
        "seasonal_boost_amount",
        "How much to add to base_priority during the seasonal window. "
        'Format: "+N" (e.g., "+5").\n\n'
        "During the boost period, effective priority = base_priority + "
        "this number. A base_priority of 8 with a +5 boost = 13 effective "
        "priority, making it the top article to send.\n\n"
        "Leave blank if no seasonal boost.",
    ),
    (
        "email_ready",
        "Whether this article has a complete email variant (subject line, "
        "preheader, intro text, CTA) and is approved for sending.\n\n"
        "TRUE = ready to send in email campaigns\n"
        "FALSE = still in draft, will be skipped by the send workflow\n\n"
        "Set to FALSE to temporarily pause an article from being sent.",
    ),
    (
        "total_sends",
        "How many times this article has been sent across all subscribers. "
        "Updated automatically by the n8n send workflow after each batch.\n\n"
        "Do not edit manually. Used to track which articles are being "
        "used and to avoid over-sending the same content.",
    ),
    (
        "notes",
        "Free-text field for context about this article. Use for:\n"
        "- Seasonal strategy (e.g., 'Holiday shopping boost')\n"
        "- Reactive triggers (e.g., 'Boost after major breach events')\n"
        "- Special considerations or CTA notes\n\n"
        "Editable by anyone on the team.",
    ),
]

SEASONAL_CALENDAR_NOTES = [
    (
        "season",
        "Name of the seasonal marketing window. These windows "
        "automatically boost the priority of matching articles "
        "during their active dates.",
    ),
    (
        "start_date",
        "When this seasonal window begins. Format: YYYY-MM-DD.\n\n"
        "Leave blank for reactive windows (e.g., data breaches) "
        "where you manually set dates when events occur.",
    ),
    (
        "end_date",
        "When this seasonal window ends. Format: YYYY-MM-DD.\n\n"
        "Leave blank for reactive windows. The send workflow only "
        "applies the boost between start and end dates.",
    ),
    (
        "boost_verticals",
        "Which article verticals get boosted during this window. "
        'Comma-separated if multiple (e.g., "fraud, finance").\n\n'
        "Must match the vertical column values in the Article "
        'Library tab (e.g., "fraud", "medicare").',
    ),
    (
        "boost_amount",
        "How much to add to base_priority for matching articles "
        'during this window. Format: "+N".\n\n'
        "+5 = major event (Medicare AEP)\n"
        "+3 = significant window (Tax Season, OEP)\n"
        "+2 = moderate boost (Holiday Shopping)\n"
        "+4 = reactive/urgent (Data Breach)",
    ),
    (
        "notes",
        "Strategy notes for this seasonal window. Include:\n"
        "- What content to prioritize\n"
        "- Monetization opportunities (e.g., broker referrals)\n"
        "- Ramp-up timing and special considerations",
    ),
]

SEND_LOG_NOTES = [
    (
        "send_date",
        "Date this email batch was sent. Format: YYYY-MM-DD.\n\n"
        "Populated automatically by the n8n send workflow.",
    ),
    (
        "article_slug",
        "The slug of the article that was sent. Matches the slug "
        "column in the Article Library tab.\n\n"
        "Populated automatically.",
    ),
    (
        "category",
        'Content type that was sent: "protection" or "guide".\n\n'
        "Populated automatically.",
    ),
    (
        "segment_size",
        "How many subscribers received this email in this batch.\n\n"
        "Populated automatically by the send workflow.",
    ),
    (
        "send_type",
        'How this send was triggered:\n\n'
        '"drip" = automated content sequence (new subscriber getting '
        "next article in priority order)\n"
        '"broadcast" = manual or scheduled send to a segment\n'
        '"seasonal" = triggered by a seasonal campaign overlay',
    ),
    (
        "seasonal_context",
        "Which seasonal window was active when this was sent, if any.\n\n"
        'Example: "Medicare AEP", "Holiday Shopping"\n'
        "Blank if no seasonal window was active.\n\n"
        "Useful for analyzing whether seasonal content performs "
        "better than evergreen sends.",
    ),
]


def main() -> None:
    from cmo_agent.google_auth import get_google_credentials
    from googleapiclient.discovery import build

    oauth_path = "/Users/nickshutwell/Desktop/CMO Agent/data/google-token.json"
    credentials = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path="",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    if credentials is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    sheets_service = build("sheets", "v4", credentials=credentials)

    # Get sheet metadata to find tab IDs
    meta = (
        sheets_service.spreadsheets()
        .get(spreadsheetId=SHEET_ID, fields="sheets.properties")
        .execute()
    )
    tab_ids = {}
    for sheet in meta["sheets"]:
        props = sheet["properties"]
        tab_ids[props["title"]] = props["sheetId"]

    print(f"Found tabs: {list(tab_ids.keys())}")

    # Build note requests
    requests = []

    tab_notes = [
        ("Article Library", ARTICLE_LIBRARY_NOTES),
        ("Seasonal Calendar", SEASONAL_CALENDAR_NOTES),
        ("Send Log", SEND_LOG_NOTES),
    ]

    for tab_name, notes in tab_notes:
        if tab_name not in tab_ids:
            print(f"  Warning: tab '{tab_name}' not found, skipping")
            continue

        sid = tab_ids[tab_name]
        cell_values = []
        for _, note_text in notes:
            cell_values.append({"note": note_text})

        requests.append(
            {
                "updateCells": {
                    "rows": [{"values": cell_values}],
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                        "startColumnIndex": 0,
                        "endColumnIndex": len(notes),
                    },
                    "fields": "note",
                }
            }
        )

    # Execute
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=SHEET_ID,
        body={"requests": requests},
    ).execute()

    print(f"\nNotes added to {len(tab_notes)} tabs:")
    for tab_name, notes in tab_notes:
        print(f"  {tab_name}: {len(notes)} column notes")

    print(
        f"\nSheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit"
    )
    print(
        "Hover over any header cell to see its description."
    )


if __name__ == "__main__":
    main()
