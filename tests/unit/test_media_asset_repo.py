"""Tests for MediaAssetRepo database operations."""

from __future__ import annotations

import pytest

from cmo_agent.db.database import Database
from cmo_agent.db.models import MediaAsset
from cmo_agent.db.repositories import MediaAssetRepo


@pytest.fixture
async def db(tmp_path):
    """Real SQLite DB in a temp directory."""
    db = Database(db_path=tmp_path / "test.db")
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
def repo(db) -> MediaAssetRepo:
    return MediaAssetRepo(db)


class TestMediaAssetRepo:
    async def test_create_and_get(self, repo):
        """Roundtrip: create then get by ID."""
        asset = await repo.create(
            asset_id="abc123",
            workspace_id="uhg",
            media_type="image",
            filename="abc123.png",
            storage_path="uhg/image/2026-02/abc123.png",
            cdn_url="https://cdn.example.com/abc123.png",
            source_agent="visual_agent",
            prompt="a happy sunset",
            metadata={"size": "1024x1024"},
            file_size_bytes=12345,
            content_type="image/png",
        )

        assert isinstance(asset, MediaAsset)
        assert asset.id == "abc123"
        assert asset.workspace_id == "uhg"
        assert asset.cdn_url == "https://cdn.example.com/abc123.png"
        assert asset.metadata == {"size": "1024x1024"}

        fetched = await repo.get("abc123")
        assert fetched is not None
        assert fetched.id == "abc123"
        assert fetched.prompt == "a happy sunset"

    async def test_get_returns_none(self, repo):
        result = await repo.get("nonexistent")
        assert result is None

    async def test_list_by_workspace(self, repo):
        """List with and without type filter."""
        await repo.create(
            asset_id="a1",
            workspace_id="uhg",
            media_type="image",
            filename="a1.png",
            storage_path="uhg/image/a1.png",
            source_agent="visual_agent",
        )
        await repo.create(
            asset_id="a2",
            workspace_id="uhg",
            media_type="video",
            filename="a2.mp4",
            storage_path="uhg/video/a2.mp4",
            source_agent="video_agent",
        )
        await repo.create(
            asset_id="a3",
            workspace_id="uhg2",
            media_type="image",
            filename="a3.png",
            storage_path="uhg2/image/a3.png",
            source_agent="visual_agent",
        )

        # All for uhg
        ss_all = await repo.list_by_workspace("uhg")
        assert len(ss_all) == 2

        # Only images for uhg
        ss_images = await repo.list_by_workspace("uhg", media_type="image")
        assert len(ss_images) == 1
        assert ss_images[0].media_type == "image"

        # uhg2 has 1
        uhg2_all = await repo.list_by_workspace("uhg2")
        assert len(uhg2_all) == 1

    async def test_set_draft_id(self, repo):
        """Update draft_id on an existing asset."""
        await repo.create(
            asset_id="d1",
            workspace_id="uhg",
            media_type="image",
            filename="d1.png",
            storage_path="uhg/image/d1.png",
            source_agent="visual_agent",
        )

        await repo.set_draft_id("d1", "draft-xyz")

        asset = await repo.get("d1")
        assert asset is not None
        assert asset.draft_id == "draft-xyz"

    async def test_list_by_draft(self, repo):
        await repo.create(
            asset_id="e1",
            workspace_id="uhg",
            media_type="image",
            filename="e1.png",
            storage_path="uhg/image/e1.png",
            source_agent="visual_agent",
            draft_id="draft-1",
        )
        await repo.create(
            asset_id="e2",
            workspace_id="uhg",
            media_type="video",
            filename="e2.mp4",
            storage_path="uhg/video/e2.mp4",
            source_agent="video_agent",
            draft_id="draft-1",
        )

        assets = await repo.list_by_draft("draft-1")
        assert len(assets) == 2

    async def test_metadata_json_parsing(self, repo):
        """metadata stored as JSON string is parsed back to dict."""
        await repo.create(
            asset_id="m1",
            workspace_id="uhg",
            media_type="image",
            filename="m1.png",
            storage_path="uhg/image/m1.png",
            source_agent="visual_agent",
            metadata={"quality": "hd", "style": "vivid"},
        )

        asset = await repo.get("m1")
        assert asset is not None
        assert asset.metadata == {"quality": "hd", "style": "vivid"}

    async def test_search(self, repo):
        await repo.create(
            asset_id="s1",
            workspace_id="uhg",
            media_type="image",
            filename="s1.png",
            storage_path="uhg/image/s1.png",
            source_agent="visual_agent",
            prompt="beautiful mountain landscape",
        )
        await repo.create(
            asset_id="s2",
            workspace_id="uhg",
            media_type="image",
            filename="s2.png",
            storage_path="uhg/image/s2.png",
            source_agent="visual_agent",
            prompt="urban city night",
        )

        results = await repo.search("uhg", "mountain")
        assert len(results) == 1
        assert results[0].id == "s1"

        # Search by source_agent
        results = await repo.search("uhg", "visual")
        assert len(results) == 2

    async def test_delete(self, repo):
        await repo.create(
            asset_id="del1",
            workspace_id="uhg",
            media_type="image",
            filename="del1.png",
            storage_path="uhg/image/del1.png",
            source_agent="visual_agent",
        )

        await repo.delete("del1")
        assert await repo.get("del1") is None
