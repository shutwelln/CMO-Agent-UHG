"""Upload locally-produced TikTok videos to Google Drive and update the sheet.

Run this after reauth_google_drive.py to upload videos that were rendered locally
because the OAuth token didn't have drive scope at production time.

Scans the output directory for .mp4 files and matches them to Content Packages
rows where Status = "Produced" but Produced Video URL is a local path (not a
Drive link).

Usage:
    python scripts/upload_produced_to_drive.py
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import dotenv  # noqa: E402

dotenv.load_dotenv()

from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.http import MediaFileUpload  # noqa: E402

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

SHEET_ID = "1jhQQ3YtWSPUZltD46h3Y5Izptx7JkZ-SO19P85aMN74"
PRODUCED_FOLDER_ID = "12v0yO3hegF5P-PyI5rgjgkUfIJe0xP4i"
OAUTH_TOKEN = "data/google-token.json"
PACKAGES_TAB = "Content Packages"
OUTPUT_DIR = Path("data/dsdn/tiktok_produced")
COL_VIDEO_URL = "R"


def main():
    parser = argparse.ArgumentParser(description="Upload produced TikTok videos to Drive")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be uploaded")
    args = parser.parse_args()

    # Check OAuth has drive scope
    import json
    token_data = json.loads(Path(OAUTH_TOKEN).read_text())
    if "https://www.googleapis.com/auth/drive" not in token_data.get("scopes", []):
        print("ERROR: OAuth token missing drive scope.")
        print("Run: python scripts/reauth_google_drive.py")
        return

    # Get services
    drive_creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN,
        service_account_path="",
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    sheets_creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN,
        service_account_path="",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    drive_svc = build("drive", "v3", credentials=drive_creds)
    sheets_svc = build("sheets", "v4", credentials=sheets_creds)

    # Read sheet to find rows with local paths
    result = (
        sheets_svc.spreadsheets()
        .values()
        .get(spreadsheetId=SHEET_ID, range=f"'{PACKAGES_TAB}'!A1:R5000")
        .execute()
    )
    all_rows = result.get("values", [])
    if not all_rows:
        print("No data in sheet.")
        return

    headers = all_rows[0]
    status_idx = headers.index("Status") if "Status" in headers else -1
    url_idx = headers.index("Produced Video URL") if "Produced Video URL" in headers else -1

    if status_idx < 0 or url_idx < 0:
        print("ERROR: Missing Status or Produced Video URL columns")
        return

    uploaded = 0
    for i, row in enumerate(all_rows[1:], start=2):
        while len(row) <= url_idx:
            row.append("")

        status = row[status_idx]
        video_url = row[url_idx]

        # Only process rows that are "Produced" with a local path (not a Drive link)
        if status != "Produced":
            continue
        if not video_url or video_url.startswith("http"):
            continue

        local_path = Path(video_url)
        if not local_path.exists():
            print(f"  Row {i}: SKIP - local file missing: {video_url}")
            continue

        filename = local_path.name
        print(f"  Row {i}: {filename}", end="")

        if args.dry_run:
            print(" (dry run - would upload)")
            continue

        # Upload to Drive
        try:
            file_metadata = {"name": filename, "parents": [PRODUCED_FOLDER_ID]}
            media = MediaFileUpload(str(local_path), mimetype="video/mp4", resumable=True)
            uploaded_file = (
                drive_svc.files()
                .create(body=file_metadata, media_body=media, fields="id, webViewLink")
                .execute()
            )
            drive_url = uploaded_file.get("webViewLink", "")

            # Update sheet
            sheets_svc.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=f"'{PACKAGES_TAB}'!{COL_VIDEO_URL}{i}",
                valueInputOption="RAW",
                body={"values": [[drive_url]]},
            ).execute()

            uploaded += 1
            print(f" -> {drive_url}")
        except Exception as e:
            print(f" FAILED: {e}")

    print(f"\nDone! Uploaded {uploaded} videos to Drive.")


if __name__ == "__main__":
    main()
