"""Tests for the Experiment Engineer Agent, ExperimentStore, and EventSchemaStore."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cmo_agent.agents.experiment_engineer import ExperimentEngineerAgent
from cmo_agent.experiments.events import EventDefinition, EventSchemaStore
from cmo_agent.experiments.store import ExperimentSpec, ExperimentStore

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
    with patch.object(ExperimentEngineerAgent, "__init_subclass__", lambda **kw: None):
        a = ExperimentEngineerAgent(
            llm=mock_llm,
            db=mock_db,
            workspace_manager=mock_workspace_mgr,
            experiments_dir=str(tmp_path / "experiments"),
            analytics_dir=str(tmp_path / "analytics"),
        )
    return a


@pytest.fixture
def experiment_store(tmp_path):
    return ExperimentStore(base_dir=str(tmp_path / "experiments"))


@pytest.fixture
def event_store(tmp_path):
    return EventSchemaStore(base_dir=str(tmp_path / "analytics"))


# ── Agent Tests ───────────────────────────────────────────────────────


class TestExperimentEngineerAgent:
    def test_agent_id(self, agent):
        assert agent.agent_id == "experiment_engineer_agent"
        assert agent.agent_name == "Data & Experiment Engineer Agent"

    def test_tools_registered(self, agent):
        tools = agent.tool_registry.list_tools()
        expected = [
            "create_experiment",
            "list_experiments",
            "update_experiment_status",
            "record_experiment_readout",
            "define_event",
            "list_events",
            "import_events_from_markdown",
            "generate_experiment_readout",
        ]
        for tool_name in expected:
            assert tool_name in tools, f"Tool '{tool_name}' not registered"
        assert len(expected) == 8

    def test_system_prompt_is_tool_agnostic(self, agent):
        prompt = agent.get_system_prompt()
        assert "TOOL-AGNOSTIC" in prompt
        # Should not hardcode GA4 as the only platform
        assert "HYPOTHESIS-DRIVEN" in prompt
        assert "EXPERIMENT LIFECYCLE" in prompt


# ── ExperimentStore Tests ─────────────────────────────────────────────


class TestExperimentStore:
    def test_create_and_get(self, experiment_store):
        spec = ExperimentSpec(
            workspace_id="test",
            name="Homepage CTA test",
            hypothesis="Changing CTA color to green increases clicks by 10%",
            primary_metric="cta_click_rate",
        )
        created = experiment_store.create(spec)
        assert created.experiment_id == spec.experiment_id

        fetched = experiment_store.get(spec.experiment_id)
        assert fetched is not None
        assert fetched.name == "Homepage CTA test"

    def test_list_by_status(self, experiment_store):
        experiment_store.create(ExperimentSpec(name="Draft 1", status="draft", workspace_id="test"))
        experiment_store.create(
            ExperimentSpec(name="Running 1", status="draft", workspace_id="test")
        )
        # Transition second one to running
        specs = experiment_store.list_all(status="draft")
        experiment_store.update_status(specs[0].experiment_id, "running")

        draft_list = experiment_store.list_all(status="draft")
        running_list = experiment_store.list_all(status="running")
        assert len(draft_list) == 1
        assert len(running_list) == 1

    def test_status_transitions(self, experiment_store):
        spec = ExperimentSpec(name="Transition test", workspace_id="test")
        experiment_store.create(spec)

        # draft -> running (valid)
        result = experiment_store.update_status(spec.experiment_id, "running")
        assert result is not None
        assert result.status == "running"

        # running -> completed (valid)
        result = experiment_store.update_status(spec.experiment_id, "completed")
        assert result.status == "completed"

    def test_invalid_status_transition(self, experiment_store):
        spec = ExperimentSpec(name="Invalid test", workspace_id="test")
        experiment_store.create(spec)

        # draft -> completed (invalid — must go through running)
        with pytest.raises(ValueError, match="Cannot transition"):
            experiment_store.update_status(spec.experiment_id, "completed")

    def test_completed_cannot_transition(self, experiment_store):
        spec = ExperimentSpec(name="Completed test", workspace_id="test")
        experiment_store.create(spec)
        experiment_store.update_status(spec.experiment_id, "running")
        experiment_store.update_status(spec.experiment_id, "completed")

        with pytest.raises(ValueError, match="Cannot transition"):
            experiment_store.update_status(spec.experiment_id, "running")

    def test_record_readout(self, experiment_store):
        spec = ExperimentSpec(
            name="Readout test",
            workspace_id="test",
            hypothesis="Test hypothesis",
        )
        experiment_store.create(spec)

        result = experiment_store.record_readout(
            experiment_id=spec.experiment_id,
            results_summary="CTR increased 15%",
            decision="ship",
            followups=["Run follow-up with larger sample"],
        )
        assert result is not None
        assert result.results_summary == "CTR increased 15%"
        assert result.decision == "ship"
        assert len(result.followups) == 1

    def test_jsonl_append_verification(self, experiment_store, tmp_path):
        """Verify that JSONL log grows with each operation."""
        jsonl_path = tmp_path / "experiments" / "registry.jsonl"

        spec = ExperimentSpec(name="JSONL test", workspace_id="test")
        experiment_store.create(spec)
        lines_after_create = jsonl_path.read_text().strip().split("\n")
        assert len(lines_after_create) == 1

        experiment_store.update_status(spec.experiment_id, "running")
        lines_after_update = jsonl_path.read_text().strip().split("\n")
        assert len(lines_after_update) == 2

    def test_snapshot_rebuild(self, experiment_store, tmp_path):
        """Verify snapshot can be rebuilt from JSONL."""
        spec = ExperimentSpec(name="Rebuild test", workspace_id="test")
        experiment_store.create(spec)

        # Delete snapshot
        snapshot_path = tmp_path / "experiments" / "current.json"
        snapshot_path.unlink()

        # Should rebuild from JSONL
        fetched = experiment_store.get(spec.experiment_id)
        assert fetched is not None
        assert fetched.name == "Rebuild test"

    def test_get_nonexistent(self, experiment_store):
        assert experiment_store.get("nonexistent") is None

    def test_update_nonexistent(self, experiment_store):
        result = experiment_store.update_status("nonexistent", "running")
        assert result is None


# ── EventSchemaStore Tests ────────────────────────────────────────────


class TestEventSchemaStore:
    def test_define_and_list(self, event_store):
        event = EventDefinition(
            event_name="page_view",
            workspace_id="test",
            properties={"page": "string", "referrer": "string"},
            owner="Analytics team",
        )
        event_store.define(event)

        events = event_store.list_all(workspace_id="test")
        assert len(events) == 1
        assert events[0].event_name == "page_view"

    def test_search(self, event_store):
        event_store.define(EventDefinition(event_name="checkout_started", workspace_id="test"))
        event_store.define(EventDefinition(event_name="page_view", workspace_id="test"))

        results = event_store.search("checkout", workspace_id="test")
        assert len(results) == 1
        assert results[0].event_name == "checkout_started"

    def test_markdown_import(self, event_store):
        markdown = """# Event Definitions

## signup_completed
- **properties**: user_id (string), plan (string)
- **owner**: Growth team
- **where_fired**: signup page
- **notes**: Fires after email verification

## purchase_made
- **properties**: amount (number), product_id (string)
- **owner**: Revenue team
- **where_fired**: checkout page
- **notes**: Fires on payment confirmation
"""
        imported = event_store.import_from_markdown(markdown, workspace_id="test")
        assert imported == 2

        events = event_store.list_all(workspace_id="test")
        assert len(events) == 2

        signup = event_store.get("signup_completed", workspace_id="test")
        assert signup is not None
        assert "user_id" in signup.properties
        assert signup.owner == "Growth team"
        assert signup.where_fired == "signup page"

    def test_malformed_markdown_import(self, event_store):
        markdown = """This is not structured markdown at all.
Just some random text without any ## headings."""
        imported = event_store.import_from_markdown(markdown, workspace_id="test")
        assert imported == 0

    def test_get_nonexistent(self, event_store):
        assert event_store.get("nonexistent", workspace_id="test") is None
