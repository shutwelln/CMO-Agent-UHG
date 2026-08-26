"""Shared Google API credential loading — service account preferred, OAuth2 fallback."""

from __future__ import annotations

from pathlib import Path
from typing import Any, List, Optional

import structlog

logger = structlog.get_logger()


def get_google_credentials(
    oauth_token_path: str = "",
    service_account_path: str = "",
    scopes: Optional[List[str]] = None,
) -> Optional[Any]:
    """Load Google credentials, preferring service account over OAuth2.

    Service accounts never expire — no manual re-auth needed.
    All Python callers (Sheets, Docs, Drive, Slides) work with service
    accounts.  OAuth2 is kept as a fallback for any future caller that
    needs user-context credentials (e.g. consumer Gmail).

    1. Try service account JSON — never expires, no refresh needed.
    2. Fall back to OAuth2 token file — auto-refreshes expired tokens.
    3. Return ``None`` if neither is available.
    """
    scopes = scopes or []

    # ── Try service account first (never expires) ─────────────────────
    if service_account_path and Path(service_account_path).exists():
        try:
            from google.oauth2 import service_account

            creds = service_account.Credentials.from_service_account_file(
                service_account_path, scopes=scopes
            )
            logger.info("google_auth_using_service_account")
            return creds
        except Exception as e:
            logger.warning("google_service_account_load_failed", error=str(e))

    # ── Fall back to OAuth2 token ─────────────────────────────────────
    if oauth_token_path and Path(oauth_token_path).exists():
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials

            creds = Credentials.from_authorized_user_file(oauth_token_path, scopes)

            if creds.expired and creds.refresh_token:
                logger.info("google_oauth_token_refreshing")
                creds.refresh(Request())
                # Persist the refreshed token
                Path(oauth_token_path).write_text(creds.to_json())
                logger.info("google_oauth_token_refreshed")

            if creds.valid:
                logger.info("google_auth_using_oauth")
                return creds

            logger.warning("google_oauth_token_invalid")
        except Exception as e:
            logger.warning("google_oauth_load_failed", error=str(e))

    return None


# ── Drive folder helpers ──────────────────────────────────────────────

DEFAULT_DRIVE_FOLDER = "CMO Agent"


def ensure_drive_folder(
    drive_service: Any,
    folder_name: str = DEFAULT_DRIVE_FOLDER,
) -> Optional[str]:
    """Find or create a Google Drive folder by name. Returns folder ID or None."""
    try:
        # Search for existing folder
        query = (
            f"name = '{folder_name}' "
            "and mimeType = 'application/vnd.google-apps.folder' "
            "and trashed = false"
        )
        results = (
            drive_service.files()
            .list(q=query, spaces="drive", fields="files(id, name)", pageSize=1)
            .execute()
        )
        files = results.get("files", [])
        if files:
            logger.info("drive_folder_found", folder_id=files[0]["id"], name=folder_name)
            return files[0]["id"]

        # Create folder
        folder_metadata = {
            "name": folder_name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        folder = drive_service.files().create(body=folder_metadata, fields="id").execute()
        logger.info("drive_folder_created", folder_id=folder["id"], name=folder_name)
        return folder["id"]
    except Exception as e:
        logger.warning("drive_folder_ensure_failed", error=str(e))
        return None


def move_file_to_folder(
    drive_service: Any,
    file_id: str,
    folder_id: str,
) -> None:
    """Move a Drive file into a folder (removes from root)."""
    try:
        # Get current parents so we can remove them
        file = drive_service.files().get(fileId=file_id, fields="parents").execute()
        previous_parents = ",".join(file.get("parents", []))
        drive_service.files().update(
            fileId=file_id,
            addParents=folder_id,
            removeParents=previous_parents,
            fields="id, parents",
        ).execute()
        logger.info("drive_file_moved", file_id=file_id, folder_id=folder_id)
    except Exception as e:
        logger.warning("drive_file_move_failed", file_id=file_id, error=str(e))


# ── Restricted sharing ─────────────────────────────────────────────

SHARE_EMAILS = ["shutwelln@gmail.com"]


def share_file_restricted(
    drive_service: Any,
    file_id: str,
    emails: Optional[List[str]] = None,
    role: str = "writer",
) -> None:
    """Share a Drive file with specific users only (restricted access).

    Does NOT create an ``anyone`` permission, so the file stays restricted
    to the listed email addresses.
    """
    for email in (emails or SHARE_EMAILS):
        try:
            drive_service.permissions().create(
                fileId=file_id,
                body={"type": "user", "role": role, "emailAddress": email},
                fields="id",
                sendNotificationEmail=False,
            ).execute()
        except Exception as e:
            logger.warning(
                "drive_share_failed", file_id=file_id, email=email, error=str(e)
            )
