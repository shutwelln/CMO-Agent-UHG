"""Tests for MediaStorage upload and query methods."""

from __future__ import annotations

import pytest
import respx

from cmo_agent.db.database import Database
from cmo_agent.db.models import MediaAsset
from cmo_agent.media.storage import MediaStorage, _resolve_content_type

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
async def db(tmp_path):
    """Real SQLite DB in a temp directory."""
    db = Database(db_path=tmp_path / "test.db")
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
def configured_storage(db) -> MediaStorage:
    """MediaStorage with Supabase configured."""
    return MediaStorage(
        db=db,
        supabase_url="https://test.supabase.co",
        supabase_service_role_key="test-key",
        supabase_bucket="cmo-media",
    )


@pytest.fixture
def unconfigured_storage(db) -> MediaStorage:
    """MediaStorage without Supabase (local-only)."""
    return MediaStorage(db=db)


# ── Config tests ──────────────────────────────────────────────────────────


class TestMediaStorageConfig:
    def test_is_configured_true(self, configured_storage):
        assert configured_storage.is_configured is True

    def test_is_configured_false_no_url(self, db):
        s = MediaStorage(db=db, supabase_service_role_key="key")
        assert s.is_configured is False

    def test_is_configured_false_no_key(self, db):
        s = MediaStorage(db=db, supabase_url="https://x.supabase.co")
        assert s.is_configured is False

    def test_is_configured_false_empty(self, unconfigured_storage):
        assert unconfigured_storage.is_configured is False


# ── Upload tests ──────────────────────────────────────────────────────────


class TestMediaStorageUpload:
    @respx.mock
    async def test_upload_success(self, configured_storage):
        """Supabase upload succeeds — CDN URL returned."""
        respx.post(url__startswith="https://test.supabase.co/storage/v1/object/cmo-media/").respond(
            200
        )

        asset = await configured_storage.upload(
            data=b"fake-png-data",
            workspace_id="uhg",
            media_type="image",
            extension=".png",
            source_agent="visual_agent",
            prompt="a sunset photo",
            metadata={"size": "1024x1024"},
        )

        assert isinstance(asset, MediaAsset)
        assert asset.cdn_url is not None
        assert "supabase.co" in asset.cdn_url
        assert asset.workspace_id == "uhg"
        assert asset.media_type == "image"
        assert asset.source_agent == "visual_agent"
        assert asset.prompt == "a sunset photo"
        assert asset.file_size_bytes == len(b"fake-png-data")
        assert asset.content_type == "image/png"

    async def test_upload_graceful_degradation_no_config(self, unconfigured_storage):
        """Without Supabase config, DB record created with cdn_url=None."""
        asset = await unconfigured_storage.upload(
            data=b"fake-data",
            workspace_id="uhg",
            media_type="image",
            extension=".png",
            source_agent="visual_agent",
        )

        assert isinstance(asset, MediaAsset)
        assert asset.cdn_url is None
        assert asset.workspace_id == "uhg"
        assert asset.file_size_bytes == len(b"fake-data")

    @respx.mock
    async def test_upload_graceful_degradation_on_error(self, configured_storage):
        """Supabase 500 — DB record still created, cdn_url=None."""
        respx.post(url__startswith="https://test.supabase.co/storage/v1/object/cmo-media/").respond(
            500
        )

        asset = await configured_storage.upload(
            data=b"data",
            workspace_id="uhg",
            media_type="image",
            extension=".png",
            source_agent="visual_agent",
        )

        assert isinstance(asset, MediaAsset)
        assert asset.cdn_url is None  # Failed upload
        assert asset.workspace_id == "uhg"

    @respx.mock
    async def test_upload_from_url(self, configured_storage):
        """Download from URL then upload to Supabase."""
        # Mock the URL download
        respx.get("https://temp.openai.com/image.png").respond(200, content=b"image-bytes")
        # Mock Supabase upload
        respx.post(url__startswith="https://test.supabase.co/storage/v1/object/cmo-media/").respond(
            200
        )

        asset = await configured_storage.upload_from_url(
            url="https://temp.openai.com/image.png",
            workspace_id="uhg",
            media_type="image",
            extension=".png",
            source_agent="visual_agent",
            prompt="dall-e image",
        )

        assert isinstance(asset, MediaAsset)
        assert asset.cdn_url is not None
        assert asset.file_size_bytes == len(b"image-bytes")

    @respx.mock
    async def test_upload_from_file(self, configured_storage, tmp_path):
        """Read local file then upload to Supabase."""
        test_file = tmp_path / "test.mp4"
        test_file.write_bytes(b"video-data-here")

        respx.post(url__startswith="https://test.supabase.co/storage/v1/object/cmo-media/").respond(
            200
        )

        asset = await configured_storage.upload_from_file(
            file_path=str(test_file),
            workspace_id="uhg",
            media_type="video",
            source_agent="video_agent",
        )

        assert isinstance(asset, MediaAsset)
        assert asset.cdn_url is not None
        assert asset.local_path == str(test_file)
        assert asset.content_type == "video/mp4"


# ── Path tests ────────────────────────────────────────────────────────────


class TestMediaStoragePaths:
    def test_build_storage_path(self):
        path = MediaStorage._build_storage_path("ws", "image", "abc.png")
        parts = path.split("/")
        assert parts[0] == "ws"
        assert parts[1] == "image"
        # parts[2] = YYYY-MM
        assert len(parts[2]) == 7 and "-" in parts[2]
        assert parts[3] == "abc.png"

    def test_resolve_content_type_known(self):
        assert _resolve_content_type(".png") == "image/png"
        assert _resolve_content_type(".mp4") == "video/mp4"
        assert _resolve_content_type(".pptx") == (
            "application/vnd.openxmlformats-officedocument.presentationml.presentation"
        )

    def test_resolve_content_type_unknown(self):
        ct = _resolve_content_type(".xyz")
        assert ct  # Should return something, not empty


# ── Listing tests ─────────────────────────────────────────────────────────


class TestMediaStorageListing:
    async def test_list_assets(self, unconfigured_storage):
        """Upload two assets, list returns both."""
        await unconfigured_storage.upload(
            data=b"a",
            workspace_id="uhg",
            media_type="image",
            extension=".png",
            source_agent="visual_agent",
        )
        await unconfigured_storage.upload(
            data=b"b",
            workspace_id="uhg",
            media_type="video",
            extension=".mp4",
            source_agent="video_agent",
        )

        all_assets = await unconfigured_storage.list_assets("uhg")
        assert len(all_assets) == 2

        images = await unconfigured_storage.list_assets("uhg", media_type="image")
        assert len(images) == 1
        assert images[0].media_type == "image"

    async def test_get_draft_assets(self, unconfigured_storage):
        """Link asset to draft, then retrieve by draft_id."""
        asset = await unconfigured_storage.upload(
            data=b"x",
            workspace_id="uhg",
            media_type="image",
            extension=".png",
            source_agent="visual_agent",
        )
        await unconfigured_storage.link_to_draft(asset.id, "draft-123")

        draft_assets = await unconfigured_storage.get_draft_assets("draft-123")
        assert len(draft_assets) == 1
        assert draft_assets[0].id == asset.id

    async def test_search_assets(self, unconfigured_storage):
        """Search by prompt text."""
        await unconfigured_storage.upload(
            data=b"a",
            workspace_id="uhg",
            media_type="image",
            extension=".png",
            source_agent="visual_agent",
            prompt="sunset over the ocean",
        )
        await unconfigured_storage.upload(
            data=b"b",
            workspace_id="uhg",
            media_type="image",
            extension=".png",
            source_agent="visual_agent",
            prompt="city skyline at night",
        )

        results = await unconfigured_storage.search_assets("uhg", "sunset")
        assert len(results) == 1
        assert "sunset" in results[0].prompt
