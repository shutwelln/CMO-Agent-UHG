"""Catalog DSDN TikTok source assets from Google Drive with vision AI.

Lists all files in the shared Drive folder (including Images/ and Videos/
subfolders), downloads each uncataloged file temporarily, runs Claude vision
AI to generate descriptions, then saves catalog entries with drive_file_id
to the JSONL catalog.

Uses the service account for reading (it has access to the shared folder).

Usage:
    python scripts/catalog_drive_media.py [--limit 50]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from io import BytesIO
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import dotenv  # noqa: E402

dotenv.load_dotenv()

from googleapiclient.discovery import build  # noqa: E402
from googleapiclient.http import MediaIoBaseDownload  # noqa: E402

from cmo_agent.google_auth import get_google_credentials  # noqa: E402
from cmo_agent.llm.anthropic import AnthropicLLM  # noqa: E402
from cmo_agent.tiktok.media_catalog import MediaCatalog  # noqa: E402

DRIVE_FOLDER_ID = "1Rs3Cqq4QBxr8oI2UGbGXlyYlzeHza3p9"
SERVICE_ACCOUNT = "data/saverwell-google-credentials.json"
CATALOG_PATH = "data/dsdn/tiktok_media_catalog.jsonl"

MEDIA_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".webm", ".mkv",
    ".jpg", ".jpeg", ".png", ".webp", ".heic", ".gif",
}


def _get_drive_service():
    """Get Drive service using service account (can read shared folders)."""
    creds = get_google_credentials(
        oauth_token_path="",
        service_account_path=SERVICE_ACCOUNT,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
    )
    if creds is None:
        raise RuntimeError("No Google credentials available")
    return build("drive", "v3", credentials=creds)


def _list_all_media(service, folder_id: str) -> list:
    """List all media files in a folder and its subfolders (1 level deep)."""
    all_files = []

    # List items in root folder
    result = service.files().list(
        q=f"'{folder_id}' in parents and trashed = false",
        spaces="drive",
        fields="files(id, name, mimeType, size)",
        pageSize=200,
    ).execute()

    for item in result.get("files", []):
        if "folder" in item.get("mimeType", ""):
            # Scan subfolder
            sub_id = item["id"]
            sub_name = item["name"]
            if sub_name == "Produced":
                continue  # Skip Produced/ folder
            sub_result = service.files().list(
                q=f"'{sub_id}' in parents and trashed = false and mimeType != 'application/vnd.google-apps.folder'",
                spaces="drive",
                fields="files(id, name, mimeType, size)",
                pageSize=200,
            ).execute()
            sub_files = sub_result.get("files", [])
            # Filter to media extensions
            for sf in sub_files:
                if Path(sf["name"]).suffix.lower() in MEDIA_EXTENSIONS:
                    sf["_subfolder"] = sub_name
                    all_files.append(sf)
        else:
            # Root-level media file
            if Path(item["name"]).suffix.lower() in MEDIA_EXTENSIONS:
                item["_subfolder"] = ""
                all_files.append(item)

    return all_files


def _download_temp(service, file_id: str, filename: str, temp_dir: Path) -> str | None:
    """Download a single file to temp dir. Returns local path."""
    try:
        request = service.files().get_media(fileId=file_id)
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()

        local_path = temp_dir / filename
        local_path.write_bytes(fh.getvalue())
        return str(local_path)
    except Exception as e:
        print(f"download failed: {e}")
        return None


async def main():
    parser = argparse.ArgumentParser(description="Catalog DSDN Drive media assets")
    parser.add_argument("--limit", type=int, default=50, help="Max files to catalog per run")
    parser.add_argument("--retry-failed", action="store_true", help="Re-catalog entries with 0 tags")
    args = parser.parse_args()

    print("Initializing Drive service (service account)...")
    service = _get_drive_service()

    # List all files (including subfolders)
    print("Listing Drive files...")
    drive_files = _list_all_media(service, DRIVE_FOLDER_ID)
    print(f"  Found {len(drive_files)} media files")

    if not drive_files:
        print("No files to catalog.")
        return

    # Show breakdown by subfolder
    from collections import Counter
    by_folder = Counter(f.get("_subfolder", "root") for f in drive_files)
    for folder, count in sorted(by_folder.items()):
        print(f"    {folder or 'root'}: {count} files")

    # Load existing catalog
    catalog = MediaCatalog(catalog_path=CATALOG_PATH)
    catalog.load()
    print(f"  Existing catalog: {catalog.stats()}")

    if args.retry_failed:
        # Remove entries with 0 tags so they get re-processed
        failed_names = {e.filename for e in catalog.entries if len(e.tags) == 0}
        print(f"  Removing {len(failed_names)} entries with 0 tags for retry...")
        catalog._entries = [e for e in catalog._entries if len(e.tags) > 0]
        catalog.save()

    # Find uncataloged files
    uncataloged = catalog.get_uncataloged_drive(drive_files)
    print(f"  Uncataloged: {len(uncataloged)} files")

    if not uncataloged:
        print("All files already cataloged!")
        return

    # Limit batch size
    batch = uncataloged[: args.limit]
    print(f"  Cataloging {len(batch)} files (limit={args.limit})...")

    # Use Haiku for vision (cheaper, faster)
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        return
    llm = AnthropicLLM(api_key=api_key, model="claude-haiku-4-5-20251001")

    temp_dir = Path(tempfile.mkdtemp(prefix="dsdn_catalog_"))
    newly_cataloged = 0
    errors = 0

    for i, df in enumerate(batch, 1):
        file_id = df["id"]
        filename = df["name"]
        subfolder = df.get("_subfolder", "")
        label = f"{subfolder}/{filename}" if subfolder else filename
        temp_path = None

        try:
            print(f"  [{i}/{len(batch)}] {label}...", end=" ", flush=True)

            # Download temporarily
            temp_path = _download_temp(service, file_id, filename, temp_dir)
            if not temp_path:
                print("SKIP (download failed)")
                errors += 1
                continue

            # Run vision AI cataloging
            entry = await catalog.catalog_file(temp_path, llm, drive_file_id=file_id)
            newly_cataloged += 1
            print(f"OK ({len(entry.tags)} tags)")

        except Exception as e:
            errors += 1
            print(f"ERROR: {e}")
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except Exception:
                    pass

    # Save catalog
    catalog.save()
    print(f"\nDone! Cataloged {newly_cataloged} new files ({errors} errors)")
    print(f"  Catalog stats: {catalog.stats()}")
    print(f"  Catalog file: {CATALOG_PATH}")

    # Cleanup temp dir
    try:
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
