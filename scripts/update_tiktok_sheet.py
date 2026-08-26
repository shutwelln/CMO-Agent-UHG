"""Update the existing DSDN TikTok Google Sheet with produced video Drive links.

Adds a 'Produced Video URL' column to the Content Packages tab and populates
it for the 3 videos we produced and uploaded.

Run:  python scripts/update_tiktok_sheet.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from googleapiclient.discovery import build
from cmo_agent.google_auth import get_google_credentials

SHEET_ID = "1jhQQ3YtWSPUZltD46h3Y5Izptx7JkZ-SO19P85aMN74"

# Our produced videos with Drive URLs
PRODUCED_VIDEOS = {
    # hook text -> drive URL (match by hook since that's unique)
    "A day in the life of a parent raising a child with Down syndrome": {
        "url": "https://drive.google.com/file/d/1YvJ0Jt5qN5I4FookIC_9spzWJsc5n-X0/view?usp=drivesdk",
        "note": "tiktok_swimming_01 - swimming footage with text overlay",
    },
    "Kids with Down syndrome are out here living their best lives": {
        "url": "https://drive.google.com/file/d/1C2uQEnjQpy5fCfBYgL9Iov0b-nFxLlzF/view?usp=drivesdk",
        "note": "tiktok_bestlife_02 - awareness facts with word-by-word text",
    },
    '"He may not be able to do the same things as other kids."': {
        "url": "https://drive.google.com/file/d/1sh0OC_46XYfdtfq2cznfwZuTPpXIitlN/view?usp=drivesdk",
        "note": "tiktok_hockey_03 - hockey myth buster with quote overlay",
    },
}


def main() -> None:
    creds = get_google_credentials(
        oauth_token_path="data/google-token.json",
        service_account_path="",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    if creds is None:
        print("ERROR: Could not load Google credentials")
        sys.exit(1)

    service = build("sheets", "v4", credentials=creds)

    # Read Content Packages headers
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="'Content Packages'!A1:Z1",
    ).execute()
    headers = result.get("values", [[]])[0]
    print(f"Current headers ({len(headers)} cols): {headers}")

    # Check if Produced Video URL column already exists
    if "Produced Video URL" in headers:
        video_col_idx = headers.index("Produced Video URL")
        print(f"'Produced Video URL' already exists at column {video_col_idx}")
    else:
        # Add it as the next column
        video_col_idx = len(headers)
        col_letter = chr(ord("A") + video_col_idx) if video_col_idx < 26 else "R"
        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"'Content Packages'!{col_letter}1",
            valueInputOption="RAW",
            body={"values": [["Produced Video URL"]]},
        ).execute()
        print(f"Added 'Produced Video URL' header at column {col_letter}")

    # Read all hooks (column D = index 3) to find matching rows
    result = service.spreadsheets().values().get(
        spreadsheetId=SHEET_ID,
        range="'Content Packages'!D1:D50",
    ).execute()
    hook_rows = result.get("values", [])
    print(f"\nFound {len(hook_rows) - 1} content packages")

    # Match hooks to our produced videos and build updates
    col_letter = chr(ord("A") + video_col_idx) if video_col_idx < 26 else "R"
    matches = 0

    for row_idx, row in enumerate(hook_rows):
        if row_idx == 0:
            continue  # skip header
        if not row:
            continue
        hook = row[0]

        # Check if this hook matches any produced video
        for produced_hook, video_info in PRODUCED_VIDEOS.items():
            # Match by substring since hooks in sheet may be slightly different
            if (produced_hook.lower() in hook.lower()
                    or hook.lower() in produced_hook.lower()):
                cell = f"'Content Packages'!{col_letter}{row_idx + 1}"
                service.spreadsheets().values().update(
                    spreadsheetId=SHEET_ID,
                    range=cell,
                    valueInputOption="RAW",
                    body={"values": [[video_info["url"]]]},
                ).execute()
                print(f"  Row {row_idx + 1}: Matched '{hook[:60]}...'")
                print(f"    -> {video_info['url']}")
                matches += 1
                break

    print(f"\nUpdated {matches} rows with video URLs")

    if matches < len(PRODUCED_VIDEOS):
        print(f"\nNote: {len(PRODUCED_VIDEOS) - matches} produced videos did not match any hook in the sheet.")
        print("The 3 produced videos used hooks from the test script, which may differ")
        print("from the content packages in the sheet. Let me add them as new rows.")

        # Read current data to find next empty row
        result = service.spreadsheets().values().get(
            spreadsheetId=SHEET_ID,
            range="'Content Packages'!A:A",
        ).execute()
        existing_rows = len(result.get("values", []))
        next_row = existing_rows + 1

        print(f"\nAppending unmatched videos starting at row {next_row}...")

        append_data = []
        for produced_hook, video_info in PRODUCED_VIDEOS.items():
            # Check if already matched
            already_matched = False
            for row_idx, row in enumerate(hook_rows):
                if row_idx == 0 or not row:
                    continue
                hook = row[0]
                if (produced_hook.lower() in hook.lower()
                        or hook.lower() in produced_hook.lower()):
                    already_matched = True
                    break

            if not already_matched:
                # Build a new row with the video data
                # Headers: Format, Content Type, Mission Area, Hook, Hook Formula, Caption,
                #          Hashtags, Sound, Duration, Difficulty, Mission Score, Trend Score,
                #          CTA, Sensitivity Notes, Script, Editing Instructions, Media Direction,
                #          Produced Video URL
                new_row = ["", "", "", produced_hook, "", "", "", "", "15s", "easy", "", "", "",
                           "", "", "", "", video_info["url"]]
                append_data.append(new_row)

        if append_data:
            service.spreadsheets().values().append(
                spreadsheetId=SHEET_ID,
                range="'Content Packages'!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": append_data},
            ).execute()
            print(f"Appended {len(append_data)} new rows with video URLs")

    print(f"\nDone! Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit#gid=1052744171")


if __name__ == "__main__":
    main()
