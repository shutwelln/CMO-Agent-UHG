"""Tests for Video Agent AI video generation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import respx

from cmo_agent.agents.video import (
    VideoAgent,
    _call_fal_video,
    _call_sora_video,
    _download_video,
    _poll_for_completion,
)
from cmo_agent.db.database import Database
from cmo_agent.llm.base import LLMResponse
from cmo_agent.workspace.manager import WorkspaceManager

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def mock_db() -> AsyncMock:
    return AsyncMock(spec=Database)


@pytest.fixture
def mock_workspace_mgr() -> AsyncMock:
    mgr = AsyncMock(spec=WorkspaceManager)
    mgr.get_brand_voice.return_value = "Friendly, trustworthy brand voice."
    return mgr


@pytest.fixture
def mock_llm() -> AsyncMock:
    from cmo_agent.llm.base import BaseLLM

    llm = AsyncMock(spec=BaseLLM)
    llm.complete.return_value = LLMResponse(
        content="Optimized video prompt for testing",
        tool_calls=[],
    )
    return llm


def _make_agent(
    mock_llm: AsyncMock,
    mock_db: AsyncMock,
    mock_workspace_mgr: AsyncMock,
    fal_key: str = "",
    openai_key: str = "",
    video_output_dir: str = "/tmp/test_videos",
) -> VideoAgent:
    return VideoAgent(
        llm=mock_llm,
        db=mock_db,
        workspace_manager=mock_workspace_mgr,
        fal_api_key=fal_key,
        openai_api_key=openai_key,
        video_output_dir=video_output_dir,
    )


# ── TestVideoTierSelection ───────────────────────────────────────────────


class TestVideoTierSelection:
    """Tests for get_video_pricing tool."""

    async def test_get_video_pricing_all_configured(
        self, mock_llm: AsyncMock, mock_db: AsyncMock, mock_workspace_mgr: AsyncMock
    ) -> None:
        agent = _make_agent(
            mock_llm,
            mock_db,
            mock_workspace_mgr,
            fal_key="fal-key",
            openai_key="oai-key",
        )
        tool_fn = agent.tool_registry.get_tool("get_video_pricing")
        result = await tool_fn()

        assert len(result["tiers"]) == 3
        for tier in result["tiers"]:
            assert tier["available"] is True

    async def test_get_video_pricing_partial_keys(
        self, mock_llm: AsyncMock, mock_db: AsyncMock, mock_workspace_mgr: AsyncMock
    ) -> None:
        agent = _make_agent(
            mock_llm,
            mock_db,
            mock_workspace_mgr,
            fal_key="fal-key",  # low + medium tiers (both use fal.ai)
        )
        tool_fn = agent.tool_registry.get_tool("get_video_pricing")
        result = await tool_fn()

        tier_map = {t["tier"]: t["available"] for t in result["tiers"]}
        assert tier_map["low"] is True
        assert tier_map["medium"] is True
        assert tier_map["high"] is False

    async def test_get_video_pricing_no_keys(
        self, mock_llm: AsyncMock, mock_db: AsyncMock, mock_workspace_mgr: AsyncMock
    ) -> None:
        agent = _make_agent(mock_llm, mock_db, mock_workspace_mgr)
        tool_fn = agent.tool_registry.get_tool("get_video_pricing")
        result = await tool_fn()

        for tier in result["tiers"]:
            assert tier["available"] is False


# ── TestVideoGeneration ──────────────────────────────────────────────────


class TestVideoGeneration:
    """Tests for generate_video tool validation."""

    async def test_generate_video_invalid_tier(
        self, mock_llm: AsyncMock, mock_db: AsyncMock, mock_workspace_mgr: AsyncMock
    ) -> None:
        agent = _make_agent(mock_llm, mock_db, mock_workspace_mgr, fal_key="k")
        tool_fn = agent.tool_registry.get_tool("generate_video")
        result = await tool_fn(
            prompt="test",
            workspace_id="ws1",
            quality="ultra",
        )
        assert result["status"] == "failed"
        assert "Invalid quality tier" in result["error"]

    async def test_generate_video_missing_api_key(
        self, mock_llm: AsyncMock, mock_db: AsyncMock, mock_workspace_mgr: AsyncMock
    ) -> None:
        agent = _make_agent(mock_llm, mock_db, mock_workspace_mgr)
        tool_fn = agent.tool_registry.get_tool("generate_video")

        # Test each tier without keys
        for tier, key_name in [
            ("low", "FAL_API_KEY"),
            ("medium", "FAL_API_KEY"),
            ("high", "OPENAI_API_KEY"),
        ]:
            result = await tool_fn(
                prompt="test",
                workspace_id="ws1",
                quality=tier,
            )
            assert result["status"] == "not_configured"
            assert key_name in result["error"]

    @respx.mock
    async def test_generate_video_saves_draft(
        self,
        mock_llm: AsyncMock,
        mock_db: AsyncMock,
        mock_workspace_mgr: AsyncMock,
        tmp_path: Path,
    ) -> None:
        # Mock the draft repo create
        mock_draft = AsyncMock()
        mock_draft.id = "draft-123"

        agent = _make_agent(
            mock_llm,
            mock_db,
            mock_workspace_mgr,
            fal_key="test-fal-key",
            video_output_dir=str(tmp_path / "videos"),
        )
        agent._drafts = AsyncMock()
        agent._drafts.create.return_value = mock_draft

        # Mock fal.ai submit
        respx.post("https://queue.fal.run/fal-ai/kling-video/v1.5/standard").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status_url": "https://queue.fal.run/status/job-1",
                    "response_url": "https://queue.fal.run/result/job-1",
                },
            )
        )
        # Mock poll - already completed
        respx.get("https://queue.fal.run/status/job-1").mock(
            return_value=httpx.Response(200, json={"status": "COMPLETED"})
        )
        # Mock result fetch
        respx.get("https://queue.fal.run/result/job-1").mock(
            return_value=httpx.Response(
                200, json={"video": {"url": "https://cdn.fal.ai/video-1.mp4"}}
            )
        )
        # Mock video download
        respx.get("https://cdn.fal.ai/video-1.mp4").mock(
            return_value=httpx.Response(200, content=b"fake-video-bytes")
        )

        tool_fn = agent.tool_registry.get_tool("generate_video")
        result = await tool_fn(
            prompt="A happy senior walking in a park",
            workspace_id="uhg",
            quality="low",
        )

        assert result["status"] == "generated"
        assert result["video_url"] == "https://cdn.fal.ai/video-1.mp4"
        assert result["draft_id"] == "draft-123"
        assert result["provider"] == "fal.ai"

        # Verify draft was saved
        agent._drafts.create.assert_called_once()
        call_kwargs = agent._drafts.create.call_args[1]
        assert call_kwargs["content_type"] == "video"
        assert call_kwargs["workspace_id"] == "uhg"


# ── TestVideoProviderHelpers ─────────────────────────────────────────────


class TestVideoProviderHelpers:
    """Tests for provider-specific API helpers."""

    @respx.mock
    async def test_call_fal_video_success(self) -> None:
        respx.post("https://queue.fal.run/fal-ai/kling-video/v1.5/standard").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status_url": "https://queue.fal.run/status/j1",
                    "response_url": "https://queue.fal.run/result/j1",
                },
            )
        )
        respx.get("https://queue.fal.run/status/j1").mock(
            return_value=httpx.Response(200, json={"status": "COMPLETED"})
        )
        respx.get("https://queue.fal.run/result/j1").mock(
            return_value=httpx.Response(200, json={"video": {"url": "https://cdn.fal.ai/out.mp4"}})
        )

        result = await _call_fal_video(api_key="test-key", prompt="test prompt")
        assert result["url"] == "https://cdn.fal.ai/out.mp4"
        assert result["metadata"]["provider"] == "fal.ai"

    @respx.mock
    async def test_call_fal_image_to_video(self) -> None:
        route = respx.post("https://queue.fal.run/fal-ai/kling-video/v1.5/standard")
        route.mock(
            return_value=httpx.Response(
                200,
                json={
                    "status_url": "https://queue.fal.run/status/j2",
                    "response_url": "https://queue.fal.run/result/j2",
                },
            )
        )
        respx.get("https://queue.fal.run/status/j2").mock(
            return_value=httpx.Response(200, json={"status": "COMPLETED"})
        )
        respx.get("https://queue.fal.run/result/j2").mock(
            return_value=httpx.Response(200, json={"video": {"url": "https://cdn.fal.ai/i2v.mp4"}})
        )

        result = await _call_fal_video(
            api_key="test-key",
            prompt="animate this image",
            image_url="https://example.com/image.png",
        )
        assert result["url"] == "https://cdn.fal.ai/i2v.mp4"

        # Verify image_url was sent in the request
        request = route.calls[0].request
        body = json.loads(request.content)
        assert body["image_url"] == "https://example.com/image.png"

    @respx.mock
    async def test_call_sora_video_success(self) -> None:
        respx.post("https://api.openai.com/v1/video/generations").mock(
            return_value=httpx.Response(200, json={"id": "sora-job-1"})
        )
        respx.get("https://api.openai.com/v1/video/generations/sora-job-1").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "completed",
                    "data": [{"url": "https://cdn.openai.com/sora-out.mp4"}],
                },
            )
        )

        result = await _call_sora_video(api_key="oai-key", prompt="test prompt")
        assert result["url"] == "https://cdn.openai.com/sora-out.mp4"
        assert result["metadata"]["provider"] == "OpenAI Sora"

    @respx.mock
    async def test_poll_timeout(self) -> None:
        respx.get("https://example.com/status/j1").mock(
            return_value=httpx.Response(200, json={"status": "IN_PROGRESS"})
        )

        with patch("cmo_agent.agents.video._POLL_INTERVAL_SECONDS", 0):
            async with httpx.AsyncClient() as client:
                with pytest.raises(TimeoutError, match="timed out"):
                    await _poll_for_completion(
                        client=client,
                        url="https://example.com/status/j1",
                        headers={},
                        poll_timeout=0,
                    )

    @respx.mock
    async def test_poll_failure_status(self) -> None:
        respx.get("https://example.com/status/j2").mock(
            return_value=httpx.Response(
                200,
                json={
                    "status": "FAILED",
                    "error": "Content policy violation",
                },
            )
        )

        async with httpx.AsyncClient() as client:
            with pytest.raises(RuntimeError, match="Content policy violation"):
                await _poll_for_completion(
                    client=client,
                    url="https://example.com/status/j2",
                    headers={},
                    poll_timeout=60,
                )


# ── TestVideoDownload ────────────────────────────────────────────────────


class TestVideoDownload:
    """Tests for video download utility."""

    @respx.mock
    async def test_download_video_success(self, tmp_path: Path) -> None:
        video_bytes = b"\x00\x00\x00\x1cftypisom" + b"\x00" * 100
        respx.get("https://cdn.example.com/video.mp4").mock(
            return_value=httpx.Response(200, content=video_bytes)
        )

        output_dir = tmp_path / "videos"
        output_dir.mkdir()

        result = await _download_video(
            url="https://cdn.example.com/video.mp4",
            output_dir=str(output_dir),
        )

        assert result.exists()
        assert result.suffix == ".mp4"
        assert result.read_bytes() == video_bytes

    @respx.mock
    async def test_download_video_creates_directory(self, tmp_path: Path) -> None:
        respx.get("https://cdn.example.com/video2.mp4").mock(
            return_value=httpx.Response(200, content=b"fake-video")
        )

        output_dir = tmp_path / "new_dir" / "videos"
        assert not output_dir.exists()

        result = await _download_video(
            url="https://cdn.example.com/video2.mp4",
            output_dir=str(output_dir),
        )

        assert output_dir.exists()
        assert result.exists()
