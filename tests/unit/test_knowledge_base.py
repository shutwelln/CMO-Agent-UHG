"""Tests for the Knowledge Base Agent, MemoryBackend, and MemorySanitizer."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cmo_agent.agents.knowledge_base import KnowledgeBaseAgent
from cmo_agent.memory.backend import MemoryBackend, MemoryItem
from cmo_agent.memory.sanitizer import MemorySanitizer

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.fixture
def mock_workspace_mgr():
    mgr = MagicMock()
    mgr.get_brand_voice = AsyncMock(return_value="Test brand voice.")
    return mgr


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    llm.complete = AsyncMock()
    return llm


@pytest.fixture
def agent(mock_llm, mock_db, mock_workspace_mgr, tmp_path):
    with patch.object(KnowledgeBaseAgent, "__init_subclass__", lambda **kw: None):
        a = KnowledgeBaseAgent(
            llm=mock_llm,
            db=mock_db,
            workspace_manager=mock_workspace_mgr,
            memory_store_path=str(tmp_path / "memory"),
        )
    return a


@pytest.fixture
def backend(tmp_path):
    return MemoryBackend(base_dir=str(tmp_path / "memory"))


# ── Agent Tests ───────────────────────────────────────────────────────


class TestKnowledgeBaseAgent:
    def test_agent_id(self, agent):
        assert agent.agent_id == "knowledge_base_agent"
        assert agent.agent_name == "Knowledge Base & Memory Curator Agent"

    def test_tools_registered(self, agent):
        tools = agent.tool_registry.list_tools()
        expected = [
            "memory_store",
            "memory_search",
            "memory_get_recent",
            "memory_get_canonical",
            "memory_status",
            "memory_expire",
        ]
        for tool_name in expected:
            assert tool_name in tools, f"Tool '{tool_name}' not registered"
        assert len(expected) == 6

    def test_system_prompt_content(self, agent):
        prompt = agent.get_system_prompt()
        assert "Knowledge Base" in prompt
        assert "CONFIDENCE SCORING" in prompt
        assert "REDACTION" in prompt
        assert "TWO-LAYER MEMORY MODEL" in prompt


# ── MemoryBackend Tests ───────────────────────────────────────────────


class TestMemoryBackend:
    def test_store_and_search(self, backend):
        item = MemoryItem(
            workspace="test",
            summary="We decided to use blue branding",
            tags=["branding", "color"],
            confidence=0.9,
        )
        stored = backend.store(item)
        assert stored.id == item.id

        results = backend.search("blue branding", workspace="test")
        assert len(results) == 1
        assert results[0].summary == "We decided to use blue branding"

    def test_search_no_results(self, backend):
        backend.store(MemoryItem(workspace="test", summary="Red is the primary color"))
        results = backend.search("purple elephants", workspace="test")
        assert len(results) == 0

    def test_workspace_filtering(self, backend):
        backend.store(MemoryItem(workspace="ws1", summary="Item for ws1"))
        backend.store(MemoryItem(workspace="ws2", summary="Item for ws2"))

        results = backend.search("Item", workspace="ws1")
        assert len(results) == 1
        assert results[0].workspace == "ws1"

    def test_get_recent(self, backend):
        for i in range(5):
            backend.store(MemoryItem(workspace="test", summary=f"Item {i}"))
        results = backend.get_recent(workspace="test", limit=3)
        assert len(results) == 3
        assert results[-1].summary == "Item 4"

    def test_get_recent_with_source_ref(self, backend):
        backend.store(MemoryItem(workspace="test", summary="Conv A item", source_ref="conv-a"))
        backend.store(MemoryItem(workspace="test", summary="Conv B item", source_ref="conv-b"))
        results = backend.get_recent(workspace="test", source_ref="conv-a")
        assert len(results) == 1
        assert results[0].source_ref == "conv-a"

    def test_get_canonical(self, backend):
        backend.store(MemoryItem(workspace="test", summary="High confidence", confidence=0.95))
        backend.store(MemoryItem(workspace="test", summary="Low confidence", confidence=0.3))
        results = backend.get_canonical(workspace="test", min_confidence=0.8)
        assert len(results) == 1
        assert results[0].summary == "High confidence"

    def test_expire(self, backend):
        item = MemoryItem(workspace="test", summary="Will be expired")
        backend.store(item)

        success = backend.expire(item.id, workspace="test")
        assert success is True

        results = backend.search("expired", workspace="test")
        assert len(results) == 0

    def test_expire_nonexistent(self, backend):
        success = backend.expire("nonexistent-id", workspace="test")
        assert success is False

    def test_stats(self, backend):
        backend.store(MemoryItem(workspace="ws1", summary="Item 1"))
        backend.store(MemoryItem(workspace="ws1", summary="Item 2"))
        backend.store(MemoryItem(workspace="ws2", summary="Item 3"))

        # Per-workspace stats
        ws1_stats = backend.stats(workspace="ws1")
        assert ws1_stats["total_items"] == 2
        assert ws1_stats["active_items"] == 2

        # Overall stats
        all_stats = backend.stats()
        assert all_stats["total_items"] == 3
        assert "ws1" in all_stats["workspaces"]
        assert "ws2" in all_stats["workspaces"]

    def test_sanitization_on_store(self, backend):
        item = MemoryItem(
            workspace="test",
            summary="API key is sk-1234567890abcdef1234567890abcdef",
            detail="Token: xoxb-EXAMPLE-NOT-A-REAL-SLACK-TOKEN",
        )
        stored = backend.store(item)
        assert "sk-" not in stored.summary
        assert "[REDACTED_API_KEY]" in stored.summary
        assert "xoxb-" not in stored.detail
        assert "[REDACTED_SLACK_TOKEN]" in stored.detail


# ── MemorySanitizer Tests ─────────────────────────────────────────────


class TestMemorySanitizer:
    def test_redacts_api_key(self):
        text = "My key is sk-1234567890abcdefghijklmnopqr"
        result = MemorySanitizer.sanitize(text)
        assert "[REDACTED_API_KEY]" in result
        assert "sk-" not in result

    def test_redacts_slack_token(self):
        text = "Bot token: xoxb-EXAMPLE-NOT-A-REAL-SLACK-TOKEN"
        result = MemorySanitizer.sanitize(text)
        assert "[REDACTED_SLACK_TOKEN]" in result
        assert "xoxb-" not in result

    def test_redacts_github_token(self):
        text = "Token: ghp_abcdefghijklmnopqrstuvwxyz1234567890"
        result = MemorySanitizer.sanitize(text)
        assert "[REDACTED_GITHUB_TOKEN]" in result
        assert "ghp_" not in result

    def test_redacts_email(self):
        text = "Contact user@example.com for details"
        result = MemorySanitizer.sanitize(text)
        assert "[REDACTED_EMAIL]" in result
        assert "user@example.com" not in result

    def test_redacts_ssn(self):
        text = "SSN: 123-45-6789"
        result = MemorySanitizer.sanitize(text)
        assert "[REDACTED_SSN]" in result
        assert "123-45-6789" not in result

    def test_preserves_normal_text(self):
        text = "We decided to use blue branding for the campaign."
        result = MemorySanitizer.sanitize(text)
        assert result == text

    def test_redacts_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = MemorySanitizer.sanitize(text)
        assert "Bearer [REDACTED_TOKEN]" in result

    def test_redacts_aws_key(self):
        text = "AWS key: AKIAIOSFODNN7EXAMPLE"
        result = MemorySanitizer.sanitize(text)
        assert "[REDACTED_AWS_KEY]" in result
