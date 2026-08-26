"""Upload produced TikTok videos to Google Drive and create a production sheet.

1. Upload the 3 produced MP4s to DSDN TikTok > Produced/ on Drive
2. Share with the user's email
3. Create a Google Sheet with production details + Drive links

Run:  python scripts/upload_tiktok_to_drive.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

from cmo_agent.google_auth import get_google_credentials, share_file_restricted

# ── Config ──────────────────────────────────────────────────────────

CREDENTIALS_PATH = (
    "/Users/nickshutwell/Desktop/CMO Agent/data/saverwell-google-credentials.json"
)
OAUTH_PATH = (
    "/Users/nickshutwell/Desktop/CMO Agent/data/google-token.json"
)
DRIVE_FOLDER_ID = "1Rs3Cqq4QBxr8oI2UGbGXlyYlzeHza3p9"
PRODUCED_DIR = Path(__file__).resolve().parent.parent / "data" / "dsdn" / "tiktok_produced"

# Map rendered filenames to content metadata
VIDEO_META = {
    "TikTokOverlay-27f948a6.mp4": {
        "id": "tiktok_swimming_01",
        "hook": "Watch this little swimmer go",
        "format": "day_in_the_life",
        "type": "celebration",
        "caption": "Just keep swimming. This is what joy looks like. #DownSyndrome #SwimLife #DSDN #Inclusion #JoyfulKids",
        "source_file": "18f4cf74173242a9bec87906147c6e12.mov",
        "duration": "15s",
    },
    "TikTokOverlay-5e7767cb.mp4": {
        "id": "tiktok_bestlife_02",
        "hook": "Kids with Down syndrome are out here living their best lives",
        "format": "awareness_facts",
        "type": "awareness",
        "caption": "No limits. Just love, laughter, and living their best lives. #DownSyndrome #LivingTheirBestLife #DSDN #Awareness #Inclusion #DisabilityJoy",
        "source_file": "5509016ace294d389cbed9821534a7ea.mov",
        "duration": "15s",
    },
    "TikTokOverlay-de31c2c4.mp4": {
        "id": "tiktok_hockey_03",
        "hook": '"He may not be able to do the same things as other kids."',
        "format": "community_story",
        "type": "community",
        "caption": "They said he might not keep up. He is out here playing hockey. Every child deserves the chance to prove the world wrong. #DownSyndrome #HockeyKids #DSDN #MythBuster #Inclusion",
        "source_file": "7209cc48d44a49b2b2803c2dceb2cf66.mov",
        "duration": "15s",
    },
}


def main() -> None:
    # ── 1. Get credentials + services ──────────────────────────────────
    # Use OAuth (not service account) because service accounts have no
    # Drive storage quota and cannot upload files.
    scopes = [
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/spreadsheets",
    ]
    creds = get_google_credentials(
        oauth_token_path=OAUTH_PATH,
        service_account_path="",  # Skip service account - no storage quota
        scopes=scopes,
    )
    if creds is None:
        print("ERROR: Could not load Google credentials")
        sys.exit(1)

    drive_service = build("drive", "v3", credentials=creds)
    sheets_service = build("sheets", "v4", credentials=creds)
    print("Google services initialized")

    # ── 2. Find or create Produced/ subfolder ───────────────────────────
    query = (
        f"'{DRIVE_FOLDER_ID}' in parents "
        "and name = 'Produced' "
        "and mimeType = 'application/vnd.google-apps.folder' "
        "and trashed = false"
    )
    result = drive_service.files().list(
        q=query, spaces="drive", fields="files(id, name)", pageSize=1
    ).execute()
    existing = result.get("files", [])

    if existing:
        produced_folder_id = existing[0]["id"]
        print(f"Found existing Produced/ folder: {produced_folder_id}")
    else:
        folder_meta = {
            "name": "Produced",
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [DRIVE_FOLDER_ID],
        }
        folder = drive_service.files().create(body=folder_meta, fields="id").execute()
        produced_folder_id = folder["id"]
        print(f"Created Produced/ folder: {produced_folder_id}")

    # ── 3. Upload each video ────────────────────────────────────────────
    upload_results = []

    for filename, meta in VIDEO_META.items():
        local_path = PRODUCED_DIR / filename
        if not local_path.exists():
            print(f"SKIP {filename}: not found at {local_path}")
            continue

        size_mb = local_path.stat().st_size / (1024 * 1024)
        print(f"\nUploading {filename} ({size_mb:.1f} MB)...")

        # Use a descriptive name on Drive
        drive_name = f"{meta['id']}_{meta['format']}.mp4"

        file_metadata = {
            "name": drive_name,
            "parents": [produced_folder_id],
        }
        media = MediaFileUpload(str(local_path), mimetype="video/mp4", resumable=True)
        uploaded = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
        ).execute()

        file_id = uploaded["id"]
        drive_url = uploaded.get("webViewLink", "")

        # Share with user
        share_file_restricted(drive_service, file_id)

        print(f"  Uploaded: {drive_name}")
        print(f"  Drive ID: {file_id}")
        print(f"  URL: {drive_url}")

        upload_results.append({
            "filename": drive_name,
            "file_id": file_id,
            "drive_url": drive_url,
            **meta,
        })

    if not upload_results:
        print("\nNo videos uploaded. Exiting.")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"Uploaded {len(upload_results)} videos to Drive")
    print(f"{'='*60}")

    # ── 4. Create Google Sheet with production data ─────────────────────
    print("\nCreating production Google Sheet...")

    sheet_body = {
        "properties": {
            "title": "DSDN TikTok Production Dashboard",
        },
        "sheets": [
            {
                "properties": {
                    "title": "Content Calendar",
                    "gridProperties": {"frozenRowCount": 1},
                }
            },
            {
                "properties": {
                    "title": "Production Log",
                    "gridProperties": {"frozenRowCount": 1},
                }
            },
        ],
    }

    spreadsheet = sheets_service.spreadsheets().create(
        body=sheet_body, fields="spreadsheetId"
    ).execute()
    sheet_id = spreadsheet["spreadsheetId"]
    sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"
    print(f"Sheet created: {sheet_url}")

    # Share sheet with user
    share_file_restricted(drive_service, sheet_id)

    # ── 5. Populate Content Calendar tab ────────────────────────────────
    calendar_headers = [
        "Package ID",
        "Date",
        "Format",
        "Content Type",
        "Hook",
        "Caption",
        "Duration",
        "Source Video",
        "Status",
        "Produced Video URL",
        "Notes",
    ]

    calendar_rows = []
    for r in upload_results:
        calendar_rows.append([
            r["id"],
            "2026-03-12",
            r["format"],
            r["type"],
            r["hook"],
            r["caption"],
            r["duration"],
            r["source_file"],
            "Produced",
            r["drive_url"],
            "",
        ])

    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Content Calendar!A1",
        valueInputOption="RAW",
        body={"values": [calendar_headers] + calendar_rows},
    ).execute()
    print("Content Calendar tab populated")

    # ── 6. Populate Production Log tab ──────────────────────────────────
    log_headers = [
        "Package ID",
        "Template",
        "Rendered Filename",
        "Drive Filename",
        "File Size (MB)",
        "Status",
        "Drive URL",
        "Drive File ID",
    ]

    log_rows = []
    for r in upload_results:
        # Find original filename from VIDEO_META
        original = [k for k, v in VIDEO_META.items() if v["id"] == r["id"]][0]
        size_mb = (PRODUCED_DIR / original).stat().st_size / (1024 * 1024)
        log_rows.append([
            r["id"],
            "TikTokOverlay-Portrait-Motion",
            original,
            r["filename"],
            f"{size_mb:.1f}",
            "Uploaded",
            r["drive_url"],
            r["file_id"],
        ])

    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="Production Log!A1",
        valueInputOption="RAW",
        body={"values": [log_headers] + log_rows},
    ).execute()
    print("Production Log tab populated")

    # ── 7. Format header rows (bold + color) ────────────────────────────
    # Get sheet IDs for formatting
    sheet_metadata = sheets_service.spreadsheets().get(
        spreadsheetId=sheet_id
    ).execute()
    tab_ids = {
        s["properties"]["title"]: s["properties"]["sheetId"]
        for s in sheet_metadata["sheets"]
    }

    format_requests = []
    for tab_name, tab_id in tab_ids.items():
        # Bold header row
        format_requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": tab_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True},
                        "backgroundColor": {
                            "red": 0.2,
                            "green": 0.4,
                            "blue": 0.8,
                            "alpha": 1.0,
                        },
                        "textFormat": {
                            "bold": True,
                            "foregroundColor": {
                                "red": 1.0,
                                "green": 1.0,
                                "blue": 1.0,
                            },
                        },
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        })

        # Auto-resize columns
        format_requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId": tab_id,
                    "dimension": "COLUMNS",
                    "startIndex": 0,
                    "endIndex": 12,
                },
            }
        })

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": format_requests},
    ).execute()
    print("Sheet formatted")

    # ── Summary ─────────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print("COMPLETE")
    print(f"{'='*60}")
    print(f"Videos uploaded to Drive: {len(upload_results)}")
    print(f"Production Sheet: {sheet_url}")
    print()
    for r in upload_results:
        print(f"  {r['id']}: {r['drive_url']}")


if __name__ == "__main__":
    main()
