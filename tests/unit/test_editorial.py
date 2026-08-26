"""Tests for the Editorial Lead Agent and EditorialStore."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cmo_agent.agents.editorial import EditorialLeadAgent
from cmo_agent.editorial.store import (
    BacklogItem,
    ContentBundle,
    EditorialCalendar,
    EditorialStore,
)

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
    with patch.object(EditorialLeadAgent, "__init_subclass__", lambda **kw: None):
        a = EditorialLeadAgent(
            llm=mock_llm,
            db=mock_db,
            workspace_manager=mock_workspace_mgr,
            editorial_data_dir=str(tmp_path / "editorial"),
        )
    return a


@pytest.fixture
def store(tmp_path):
    return EditorialStore(base_dir=str(tmp_path / "editorial"))


# ── Agent Tests ───────────────────────────────────────────────────────


class TestEditorialLeadAgent:
    def test_agent_id(self, agent):
        assert agent.agent_id == "editorial_agent"
        assert agent.agent_name == "Editorial Lead & Publishing Ops Agent"

    def test_tools_registered(self, agent):
        tools = agent.tool_registry.list_tools()
        expected = [
            "create_editorial_plan",
            "add_backlog_item",
            "list_backlog",
            "create_content_bundle",
            "update_bundle_status",
            "list_bundles",
            "get_publish_checklist",
        ]
        for tool_name in expected:
            assert tool_name in tools, f"Tool '{tool_name}' not registered"
        assert len(expected) == 7

    def test_system_prompt_mentions_state_machine(self, agent):
        prompt = agent.get_system_prompt()
        assert "draft" in prompt
        assert "review" in prompt
        assert "approved" in prompt
        assert "scheduled" in prompt
        assert "published" in prompt

    def test_system_prompt_says_no_content_creation(self, agent):
        prompt = agent.get_system_prompt()
        assert "does NOT write content" in prompt or "do NOT write content" in prompt


# ── EditorialStore Backlog Tests ──────────────────────────────────────


class TestEditorialStoreBacklog:
    def test_add_and_list(self, store):
        item = BacklogItem(
            workspace_id="test",
            idea="Write a blog post about AI trends",
            priority="high",
            channel="blog",
        )
        saved = store.add_backlog_item(item)
        assert saved.id == item.id

        items = store.list_backlog(workspace_id="test")
        assert len(items) == 1
        assert items[0].idea == "Write a blog post about AI trends"

    def test_filter_by_status(self, store):
        store.add_backlog_item(BacklogItem(workspace_id="test", idea="Open item", status="open"))
        store.add_backlog_item(
            BacklogItem(workspace_id="test", idea="Planned item", status="planned")
        )

        open_items = store.list_backlog(workspace_id="test", status="open")
        assert len(open_items) == 1
        assert open_items[0].idea == "Open item"

    def test_update_status(self, store):
        item = BacklogItem(workspace_id="test", idea="Test idea")
        store.add_backlog_item(item)

        updated = store.update_backlog_status(item.id, "planned")
        assert updated is not None
        assert updated.status == "planned"

    def test_invalid_backlog_status(self, store):
        item = BacklogItem(workspace_id="test", idea="Test idea")
        store.add_backlog_item(item)

        with pytest.raises(ValueError, match="Invalid backlog status"):
            store.update_backlog_status(item.id, "invalid_status")


# ── EditorialStore Calendar Tests ─────────────────────────────────────


class TestEditorialStoreCalendar:
    def test_save_and_get(self, store):
        calendar = EditorialCalendar(
            workspace_id="test",
            week_start="2025-06-02",
            slots=[
                {"day": "Monday", "channel": "blog", "topic": "AI Trends"},
                {"day": "Wednesday", "channel": "email", "topic": "Newsletter"},
            ],
        )
        saved = store.save_calendar(calendar)
        assert saved.workspace_id == "test"

        fetched = store.get_calendar("test", "2025-06-02")
        assert fetched is not None
        assert len(fetched.slots) == 2

    def test_get_nonexistent_calendar(self, store):
        assert store.get_calendar("test", "2099-01-01") is None


# ── EditorialStore Bundle Tests ───────────────────────────────────────


class TestEditorialStoreBundle:
    def test_create_and_get(self, store):
        bundle = ContentBundle(
            workspace_id="test",
            title="Q3 Campaign Launch",
            target_audience="Small business owners",
            channels=["blog", "email", "social"],
            primary_cta="Sign up for free trial",
            assets_requested=[
                {"agent": "writer_agent", "spec": "1200-word blog post"},
                {"agent": "visual_agent", "spec": "Hero image"},
            ],
        )
        saved = store.create_bundle(bundle)
        assert saved.id == bundle.id

        fetched = store.get_bundle(bundle.id)
        assert fetched is not None
        assert fetched.title == "Q3 Campaign Launch"
        assert len(fetched.assets_requested) == 2

    def test_status_transitions(self, store):
        bundle = ContentBundle(workspace_id="test", title="Test bundle")
        store.create_bundle(bundle)

        # draft -> review (valid)
        updated = store.update_bundle_status(bundle.id, "review")
        assert updated.status == "review"

        # review -> approved (valid)
        updated = store.update_bundle_status(bundle.id, "approved")
        assert updated.status == "approved"

        # approved -> scheduled (valid)
        updated = store.update_bundle_status(bundle.id, "scheduled")
        assert updated.status == "scheduled"

        # scheduled -> published (valid)
        updated = store.update_bundle_status(bundle.id, "published")
        assert updated.status == "published"

    def test_invalid_transition(self, store):
        bundle = ContentBundle(workspace_id="test", title="Test bundle")
        store.create_bundle(bundle)

        # draft -> published (invalid — must go through review/approved/scheduled)
        with pytest.raises(ValueError, match="Cannot transition"):
            store.update_bundle_status(bundle.id, "published")

    def test_published_cannot_transition(self, store):
        bundle = ContentBundle(workspace_id="test", title="Test bundle")
        store.create_bundle(bundle)
        store.update_bundle_status(bundle.id, "review")
        store.update_bundle_status(bundle.id, "approved")
        store.update_bundle_status(bundle.id, "scheduled")
        store.update_bundle_status(bundle.id, "published")

        with pytest.raises(ValueError, match="Cannot transition"):
            store.update_bundle_status(bundle.id, "draft")

    def test_filter_by_status(self, store):
        store.create_bundle(ContentBundle(workspace_id="test", title="Draft bundle"))
        b2 = ContentBundle(workspace_id="test", title="Review bundle")
        store.create_bundle(b2)
        store.update_bundle_status(b2.id, "review")

        draft_bundles = store.list_bundles(workspace_id="test", status="draft")
        assert len(draft_bundles) == 1
        assert draft_bundles[0].title == "Draft bundle"

        review_bundles = store.list_bundles(workspace_id="test", status="review")
        assert len(review_bundles) == 1
        assert review_bundles[0].title == "Review bundle"

    def test_get_nonexistent_bundle(self, store):
        assert store.get_bundle("nonexistent") is None
