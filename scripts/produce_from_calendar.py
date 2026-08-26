"""Produce TikTok videos from the Content Packages sheet.

For each package row in the sheet:
1. Searches media catalog for matching source by hook keywords
2. Downloads matched Drive file on-demand (via service account)
3. Renders via Remotion (TikTokOverlay, 8-10s, 1080x1920)
4. Uploads produced video to Drive Produced/ subfolder (if OAuth has drive scope)
5. Writes Drive link (or local path) to Produced Video URL column in sheet
6. Updates Status to "Produced"

Usage:
    python scripts/produce_from_calendar.py [--status Draft] [--limit 5]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import dotenv  # noqa: E402

dotenv.load_dotenv()

from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload  # noqa: E402

from cmo_agent.google_auth import get_google_credentials  # noqa: E402
from cmo_agent.text.composition_renderer import CompositionRenderer  # noqa: E402
from cmo_agent.tiktok.media_catalog import MediaCatalog  # noqa: E402
from cmo_agent.tiktok.models import CatalogEntry  # noqa: E402

SHEET_ID = "1jhQQ3YtWSPUZltD46h3Y5Izptx7JkZ-SO19P85aMN74"
DRIVE_FOLDER_ID = "1Rs3Cqq4QBxr8oI2UGbGXlyYlzeHza3p9"
PRODUCED_FOLDER_ID = "12v0yO3hegF5P-PyI5rgjgkUfIJe0xP4i"
OAUTH_TOKEN = "data/google-token.json"
SERVICE_ACCOUNT = "data/saverwell-google-credentials.json"
CATALOG_PATH = "data/dsdn/tiktok_media_catalog.jsonl"
PACKAGES_TAB = "Content Packages"
OUTPUT_DIR = Path("data/dsdn/tiktok_produced")

# Column positions (0-indexed): N=Status(13), R=Produced Video URL(17)
COL_STATUS = "N"
COL_VIDEO_URL = "R"

# Duration string to seconds
DURATION_MAP = {"8s": 8, "10s": 10, "15s": 15, "30s": 30, "60s": 60}

# Format to animation style
FORMAT_ANIMATION = {
    "educational_overlay": "word-by-word",
    "awareness_facts": "word-by-word",
}


def _get_sheets_service():
    """Sheets service via OAuth (spreadsheets scope)."""
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN,
        service_account_path="",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def _get_drive_service_for_download():
    """Drive service via service account (can read shared folders)."""
    creds = get_google_credentials(
        oauth_token_path="",
        service_account_path=SERVICE_ACCOUNT,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    if creds is None:
        raise RuntimeError("No service account credentials for Drive downloads")
    return build("drive", "v3", credentials=creds)


def _get_drive_service_for_upload():
    """Drive service via OAuth (needs drive scope for uploads). Returns None if unavailable."""
    token_path = Path(OAUTH_TOKEN)
    if not token_path.exists():
        return None

    token_data = json.loads(token_path.read_text())
    scopes = token_data.get("scopes", [])
    if "https://www.googleapis.com/auth/drive" not in scopes:
        return None

    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN,
        service_account_path="",
        scopes=["https://www.googleapis.com/auth/drive"],
    )
    if creds is None:
        return None
    return build("drive", "v3", credentials=creds)


def _read_packages(service, status_filter: str = "Draft") -> list:
    """Read content package rows from the sheet."""
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(
                spreadsheetId=SHEET_ID,
                range=f"'{PACKAGES_TAB}'!A1:R5000",
            )
            .execute()
        )
        all_rows = result.get("values", [])
    except Exception as e:
        print(f"ERROR reading sheet: {e}")
        return []

    if not all_rows:
        return []

    headers = all_rows[0]
    entries = []
    for i, row in enumerate(all_rows[1:], start=2):
        while len(row) < len(headers):
            row.append("")

        row_dict = dict(zip(headers, row))
        row_dict["_row_number"] = i

        if status_filter and row_dict.get("Status", "").lower() != status_filter.lower():
            continue

        entries.append(row_dict)

    return entries


def _update_sheet_cell(service, col: str, row: int, value: str) -> None:
    """Update a single cell in the sheet."""
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"'{PACKAGES_TAB}'!{col}{row}",
        valueInputOption="RAW",
        body={"values": [[value]]},
    ).execute()


def _download_source(drive_service, file_id: str, filename: str, temp_dir: Path) -> Optional[str]:
    """Download a single file from Drive via service account."""
    try:
        request = drive_service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        local_path = temp_dir / filename
        local_path.write_bytes(fh.getvalue())
        size_mb = len(fh.getvalue()) / 1024 / 1024
        print(f"    Downloaded: {filename} ({size_mb:.1f}MB)")
        return str(local_path)
    except Exception as e:
        print(f"    Download failed: {e}")
        return None


def _upload_to_drive(drive_service, local_path: str, filename: str) -> Optional[str]:
    """Upload a video to the Produced/ folder. Returns Drive web link or None."""
    try:
        file_metadata = {
            "name": filename,
            "parents": [PRODUCED_FOLDER_ID],
        }
        media = MediaFileUpload(local_path, mimetype="video/mp4", resumable=True)
        uploaded = (
            drive_service.files()
            .create(body=file_metadata, media_body=media, fields="id, webViewLink")
            .execute()
        )
        return uploaded.get("webViewLink", "")
    except Exception as e:
        print(f"    Drive upload failed: {e}")
        return None


def _search_catalog(catalog: MediaCatalog, hook: str) -> Optional[CatalogEntry]:
    """Search catalog for a photo matching the hook keywords."""
    # Try the full hook
    results = catalog.search(hook, media_type="photo", limit=1)
    if results:
        return results[0]

    # Try individual words (skip common words)
    skip_words = {"the", "a", "an", "is", "are", "was", "were", "of", "in", "to", "and", "or",
                  "for", "on", "at", "by", "it", "its", "this", "that", "not", "no", "your",
                  "you", "we", "they", "what", "why", "how", "when", "don't", "didn't", "won't"}
    words = [w.lower().strip(".,!?\"'") for w in hook.split() if w.lower() not in skip_words]
    for word in words:
        if len(word) < 3:
            continue
        results = catalog.search(word, media_type="photo", limit=1)
        if results:
            return results[0]

    # Try broader terms related to DSDN content
    for term in ["baby", "child", "family", "smile", "portrait", "down syndrome"]:
        results = catalog.search(term, media_type="photo", limit=1)
        if results:
            return results[0]

    return None


def _build_props(hook: str, fmt: str, bg_image: Optional[str] = None) -> Dict[str, Any]:
    """Build TikTokOverlay template props from package data."""
    animation = FORMAT_ANIMATION.get(fmt, "fade-up")

    props: Dict[str, Any] = {
        "text": hook,
        "subtext": "",
        "textPosition": "bottom-center",
        "textColor": "#FFFFFF",
        "textStyle": "bold",
        "bgDim": 0.15,
        "textShadow": True,
        "animation": animation,
        "mode": "animated",
    }

    if bg_image:
        props["bgImage"] = bg_image

    return props


async def main():
    parser = argparse.ArgumentParser(description="Produce TikTok videos from sheet")
    parser.add_argument("--status", default="Draft", help="Filter rows by status")
    parser.add_argument("--limit", type=int, default=10, help="Max videos to produce")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load media catalog
    print("Loading media catalog...")
    catalog = MediaCatalog(catalog_path=CATALOG_PATH)
    catalog.load()
    stats = catalog.stats()
    print(f"  Catalog: {stats['total']} entries ({stats['photos']} photos, {stats['videos']} videos)")

    if stats["total"] == 0:
        print("WARNING: Media catalog is empty. Run catalog_drive_media.py first.")
        print("Videos will render with solid color backgrounds.")

    # Initialize services
    print("Initializing services...")
    sheets_service = _get_sheets_service()
    drive_download = _get_drive_service_for_download()
    drive_upload = _get_drive_service_for_upload()

    if drive_upload:
        print("  Drive upload: ENABLED (OAuth has drive scope)")
    else:
        print("  Drive upload: DISABLED (OAuth missing drive scope)")
        print("  Videos will be saved locally. Run reauth_google_drive.py to enable uploads.")

    renderer = CompositionRenderer(remotion_project_dir="data/remotion")

    # Read packages from sheet
    print(f"Reading sheet (status={args.status})...")
    rows = _read_packages(sheets_service, status_filter=args.status)
    print(f"  Found {len(rows)} rows")

    if not rows:
        print("No rows to produce.")
        return

    batch = rows[: args.limit]
    print(f"Producing {len(batch)} videos...\n")

    temp_dir = Path(tempfile.mkdtemp(prefix="dsdn_produce_"))
    produced = 0
    failed = 0
    local_paths: List[Tuple[str, str]] = []  # (pkg_id, local_path)

    for i, row in enumerate(batch, 1):
        pkg_id = row.get("ID", f"unknown_{i}")
        hook = row.get("Hook", "")
        fmt = row.get("Format", "educational_overlay")
        duration_str = row.get("Duration", "10s")
        row_num = row["_row_number"]
        duration_secs = DURATION_MAP.get(duration_str, 10)

        print(f"  [{i}/{len(batch)}] {pkg_id}: \"{hook}\" ({duration_str})")

        # Mark as producing
        _update_sheet_cell(sheets_service, COL_STATUS, row_num, "Producing")

        # 1. Search catalog for matching source image
        bg_image_path = None
        catalog_entry = _search_catalog(catalog, hook)
        if catalog_entry and catalog_entry.drive_file_id:
            print(f"    Matched: {catalog_entry.filename}")
            bg_image_path = _download_source(
                drive_download, catalog_entry.drive_file_id, catalog_entry.filename, temp_dir
            )
        elif catalog_entry and catalog_entry.file_path and Path(catalog_entry.file_path).exists():
            bg_image_path = catalog_entry.file_path
            print(f"    Matched (local): {catalog_entry.filename}")
        else:
            print("    No matching source - using solid background")

        # 2. Build props (use filename only for bgImage - Remotion needs --public-dir)
        props = _build_props(hook, fmt)

        # 3. Render via Remotion
        try:
            # If we have a background image, copy to Remotion public/ and use filename
            remotion_public = Path("data/remotion/public")
            temp_public_img = None
            if bg_image_path and Path(bg_image_path).exists():
                import shutil as _sh
                temp_public_img = remotion_public / Path(bg_image_path).name
                _sh.copy2(bg_image_path, str(temp_public_img))
                props["bgImage"] = Path(bg_image_path).name

            video_path = await renderer.render_motion(
                template_id="TikTokOverlay",
                props=props,
                duration_seconds=duration_secs,
                fps=30,
                output_format="portrait",
            )

            # Copy to our output dir with a meaningful name
            from datetime import datetime, timezone
            ts = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            out_name = f"{ts}_{fmt}_{pkg_id}.mp4"
            final_path = OUTPUT_DIR / out_name
            import shutil
            shutil.copy2(video_path, str(final_path))

            print(f"    Rendered: {final_path}")
            local_paths.append((pkg_id, str(final_path)))

        except Exception as e:
            print(f"    RENDER FAILED: {e}")
            _update_sheet_cell(sheets_service, COL_STATUS, row_num, "Failed")
            failed += 1
            # Clean up downloaded source
            if bg_image_path and Path(bg_image_path).exists():
                Path(bg_image_path).unlink(missing_ok=True)
            continue

        # 4. Upload to Drive (if OAuth has drive scope)
        video_url = str(final_path)  # default to local path
        if drive_upload:
            drive_url = _upload_to_drive(drive_upload, str(final_path), out_name)
            if drive_url:
                video_url = drive_url
                print(f"    Uploaded: {drive_url}")

        # 5. Update sheet
        _update_sheet_cell(sheets_service, COL_STATUS, row_num, "Produced")
        _update_sheet_cell(sheets_service, COL_VIDEO_URL, row_num, video_url)
        produced += 1

        # Clean up downloaded source image (keep public copy until batch end)
        if bg_image_path and Path(bg_image_path).exists():
            Path(bg_image_path).unlink(missing_ok=True)

    # Clean up all temp images from Remotion public/ at batch end
    remotion_public = Path("data/remotion/public")
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        for f in remotion_public.glob(f"*{ext}"):
            try:
                f.unlink(missing_ok=True)
            except Exception:
                pass

    # Cleanup temp dir
    try:
        import shutil as _shutil
        _shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass

    print(f"\n{'='*60}")
    print(f"Done! Produced: {produced}, Failed: {failed}")
    print(f"Output dir: {OUTPUT_DIR}")
    if not drive_upload and produced > 0:
        print(f"\nTo upload to Drive, run:")
        print(f"  1. python scripts/reauth_google_drive.py  (adds drive scope)")
        print(f"  2. python scripts/upload_produced_to_drive.py  (uploads + updates sheet)")
    print(f"Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}")


if __name__ == "__main__":
    asyncio.run(main())
