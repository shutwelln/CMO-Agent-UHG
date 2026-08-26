"""Centralized media storage with Supabase CDN + local DB tracking."""

from __future__ import annotations

import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
import structlog

from ..db.database import Database
from ..db.models import MediaAsset
from ..db.repositories import MediaAssetRepo

logger = structlog.get_logger()

# Extension -> content type fallback
_CONTENT_TYPES: Dict[str, str] = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".pdf": "application/pdf",
}


class MediaStorage:
    """Upload media to Supabase Storage and track in DB.

    Gracefully degrades when Supabase is not configured — DB records
    are always created, but cdn_url will be None.
    """

    def __init__(
        self,
        db: Database,
        supabase_url: str = "",
        supabase_service_role_key: str = "",
        supabase_bucket: str = "cmo-media",
    ) -> None:
        self._db = db
        self._supabase_url = supabase_url.rstrip("/") if supabase_url else ""
        self._service_role_key = supabase_service_role_key
        self._bucket = supabase_bucket
        self._repo = MediaAssetRepo(db)
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def is_configured(self) -> bool:
        """True when Supabase URL and key are both set."""
        return bool(self._supabase_url and self._service_role_key)

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    # ── Upload methods ────────────────────────────────────────────────────

    async def upload(
        self,
        data: bytes,
        workspace_id: str,
        media_type: str,
        extension: str,
        source_agent: str,
        prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        local_path: Optional[str] = None,
        draft_id: Optional[str] = None,
    ) -> MediaAsset:
        """Upload raw bytes to Supabase (if configured) and record in DB."""
        asset_id = uuid4().hex[:12]
        filename = f"{asset_id}{extension}"
        storage_path = self._build_storage_path(workspace_id, media_type, filename)
        content_type = _resolve_content_type(extension)

        cdn_url: Optional[str] = None
        if self.is_configured:
            try:
                cdn_url = await self._upload_to_supabase(data, storage_path, content_type)
            except Exception as e:
                logger.error("supabase_upload_failed", error=str(e), path=storage_path)

        asset = await self._repo.create(
            asset_id=asset_id,
            workspace_id=workspace_id,
            media_type=media_type,
            filename=filename,
            storage_path=storage_path,
            cdn_url=cdn_url,
            local_path=local_path,
            source_agent=source_agent,
            prompt=prompt,
            metadata=metadata,
            file_size_bytes=len(data),
            content_type=content_type,
            draft_id=draft_id,
        )

        logger.info(
            "media_asset_created",
            asset_id=asset_id,
            media_type=media_type,
            cdn_url=cdn_url is not None,
            workspace=workspace_id,
        )
        return asset

    async def upload_from_url(
        self,
        url: str,
        workspace_id: str,
        media_type: str,
        extension: str,
        source_agent: str,
        prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        draft_id: Optional[str] = None,
    ) -> MediaAsset:
        """Download from URL then upload to Supabase."""
        client = await self._ensure_client()
        resp = await client.get(url)
        resp.raise_for_status()
        return await self.upload(
            data=resp.content,
            workspace_id=workspace_id,
            media_type=media_type,
            extension=extension,
            source_agent=source_agent,
            prompt=prompt,
            metadata=metadata,
            draft_id=draft_id,
        )

    async def upload_from_file(
        self,
        file_path: str,
        workspace_id: str,
        media_type: str,
        source_agent: str,
        prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        draft_id: Optional[str] = None,
    ) -> MediaAsset:
        """Read a local file then upload to Supabase."""
        path = Path(file_path)
        data = path.read_bytes()
        extension = path.suffix or ".bin"
        return await self.upload(
            data=data,
            workspace_id=workspace_id,
            media_type=media_type,
            extension=extension,
            source_agent=source_agent,
            prompt=prompt,
            metadata=metadata,
            local_path=file_path,
            draft_id=draft_id,
        )

    # ── Query methods ─────────────────────────────────────────────────────

    async def list_assets(
        self,
        workspace_id: str,
        media_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[MediaAsset]:
        return await self._repo.list_by_workspace(workspace_id, media_type, limit)

    async def get_asset(self, asset_id: str) -> Optional[MediaAsset]:
        return await self._repo.get(asset_id)

    async def get_draft_assets(self, draft_id: str) -> List[MediaAsset]:
        return await self._repo.list_by_draft(draft_id)

    async def search_assets(
        self,
        workspace_id: str,
        query: str,
        limit: int = 50,
    ) -> List[MediaAsset]:
        return await self._repo.search(workspace_id, query, limit)

    async def link_to_draft(self, asset_id: str, draft_id: str) -> None:
        await self._repo.set_draft_id(asset_id, draft_id)

    # ── Internal ──────────────────────────────────────────────────────────

    async def _upload_to_supabase(self, data: bytes, storage_path: str, content_type: str) -> str:
        """POST to Supabase Storage and return the public CDN URL."""
        client = await self._ensure_client()
        resp = await client.post(
            f"{self._supabase_url}/storage/v1/object/{self._bucket}/{storage_path}",
            content=data,
            headers={
                "Authorization": f"Bearer {self._service_role_key}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
        )
        resp.raise_for_status()
        return f"{self._supabase_url}/storage/v1/object/public/{self._bucket}/{storage_path}"

    @staticmethod
    def _build_storage_path(workspace_id: str, media_type: str, filename: str) -> str:
        """Build: {workspace}/{type}/{YYYY-MM}/{filename}"""
        month = datetime.utcnow().strftime("%Y-%m")
        return f"{workspace_id}/{media_type}/{month}/{filename}"


def _resolve_content_type(extension: str) -> str:
    """Resolve MIME type from extension."""
    ext = extension.lower()
    ct = _CONTENT_TYPES.get(ext)
    if ct:
        return ct
    guessed, _ = mimetypes.guess_type(f"file{ext}")
    return guessed or "application/octet-stream"
