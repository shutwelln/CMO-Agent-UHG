"""Tests for WorkflowHealerAgent: diagnosis, repair, cooldown, rollback, repo CRUD."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest

from cmo_agent.agents.workflow_healer import (
    CREDENTIAL_REQUIRING_TYPES,
    MODEL_DEPRECATION_MAP,
    NODE_TYPE_MIGRATION_MAP,
    REPAIR_COOLDOWN_SECONDS,
    WorkflowHealerAgent,
)
from cmo_agent.db.models import HealLogEntry
from cmo_agent.n8n.client import N8NClientError
from cmo_agent.n8n.models import (
    Execution,
    ExecutionListResponse,
    ExecutionStatus,
    Workflow,
    WorkflowListResponse,
    WorkflowNode,
)


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_workflow(
    workflow_id: str = "wf-1",
    name: str = "Test Workflow",
    nodes: Optional[List[Dict[str, Any]]] = None,
    connections: Optional[Dict[str, Any]] = None,
) -> Workflow:
    """Build a Workflow model from simple dicts."""
    node_objs = []
    for n in nodes or []:
        node_objs.append(WorkflowNode(**n))
    return Workflow(
        id=workflow_id,
        name=name,
        active=True,
        nodes=node_objs,
        connections=connections or {},
    )


def _make_agent(
    n8n_mock: Optional[AsyncMock] = None,
    db_mock: Optional[MagicMock] = None,
) -> WorkflowHealerAgent:
    """Create a WorkflowHealerAgent with mocked deps."""
    llm = MagicMock()
    db = db_mock or MagicMock()
    n8n = n8n_mock or AsyncMock()
    return WorkflowHealerAgent(llm=llm, db=db, n8n_client=n8n)


# ── Diagnosis tests ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diagnose_deprecated_model():
    """Nodes with deprecated model IDs are flagged."""
    n8n = AsyncMock()
    n8n.get_workflow.return_value = _make_workflow(
        nodes=[
            {
                "name": "OpenAI Chat",
                "type": "n8n-nodes-base.openAi",
                "parameters": {"model": "gpt-4-0613"},
            }
        ]
    )

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    model_issues = [i for i in result["issues"] if i["type"] == "deprecated_model"]
    assert len(model_issues) == 1
    assert model_issues[0]["current_value"] == "gpt-4-0613"
    assert model_issues[0]["replacement"] == MODEL_DEPRECATION_MAP["gpt-4-0613"]


@pytest.mark.asyncio
async def test_diagnose_deprecated_node_type():
    """Deprecated node types like function -> code are flagged."""
    n8n = AsyncMock()
    n8n.get_workflow.return_value = _make_workflow(
        nodes=[
            {
                "name": "My Function",
                "type": "n8n-nodes-base.function",
                "parameters": {},
            }
        ]
    )

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    has_node_type_issue = any(i["type"] == "deprecated_node_type" for i in result["issues"])
    assert has_node_type_issue


@pytest.mark.asyncio
async def test_diagnose_dangling_connection_source():
    """Connections referencing non-existent source nodes are flagged."""
    n8n = AsyncMock()
    n8n.get_workflow.return_value = _make_workflow(
        nodes=[{"name": "Start", "type": "n8n-nodes-base.start", "parameters": {}}],
        connections={"Deleted Node": {"main": [[{"node": "Start", "type": "main", "index": 0}]]}},
    )

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    assert any(i["type"] == "dangling_connection_source" for i in result["issues"])


@pytest.mark.asyncio
async def test_diagnose_dangling_connection_target():
    """Connections referencing non-existent target nodes are flagged."""
    n8n = AsyncMock()
    n8n.get_workflow.return_value = _make_workflow(
        nodes=[{"name": "Start", "type": "n8n-nodes-base.start", "parameters": {}}],
        connections={"Start": {"main": [[{"node": "Ghost Node", "type": "main", "index": 0}]]}},
    )

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    assert any(i["type"] == "dangling_connection_target" for i in result["issues"])


@pytest.mark.asyncio
async def test_diagnose_duplicate_node_names():
    """Duplicate node names are flagged."""
    n8n = AsyncMock()
    n8n.get_workflow.return_value = _make_workflow(
        nodes=[
            {"name": "HTTP Request", "type": "n8n-nodes-base.httpRequest", "parameters": {}},
            {"name": "HTTP Request", "type": "n8n-nodes-base.httpRequest", "parameters": {}},
        ]
    )

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    dup_issues = [i for i in result["issues"] if i["type"] == "duplicate_node_name"]
    assert len(dup_issues) == 1
    assert dup_issues[0]["count"] == 2


@pytest.mark.asyncio
async def test_diagnose_no_issues():
    """Clean workflow has zero issues."""
    n8n = AsyncMock()
    n8n.get_workflow.return_value = _make_workflow(
        nodes=[
            {"name": "Start", "type": "n8n-nodes-base.start", "parameters": {}},
            {"name": "End", "type": "n8n-nodes-base.noOp", "parameters": {}},
        ]
    )

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    assert result["issues_count"] == 0


@pytest.mark.asyncio
async def test_diagnose_api_error():
    """Diagnosis returns error when n8n API fails."""
    n8n = AsyncMock()
    n8n.get_workflow.side_effect = N8NClientError("Connection refused")

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    assert "error" in result


# ── Credential check tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diagnose_missing_credentials():
    """Nodes that require credentials but have none are flagged as warnings."""
    n8n = AsyncMock()
    n8n.get_workflow.return_value = _make_workflow(
        nodes=[
            {
                "name": "Slack",
                "type": "n8n-nodes-base.slack",
                "parameters": {"channel": "#test"},
                "credentials": None,
            }
        ]
    )

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    cred_issues = [i for i in result["issues"] if i["type"] == "missing_credentials"]
    assert len(cred_issues) == 1
    assert cred_issues[0]["severity"] == "warning"


@pytest.mark.asyncio
async def test_diagnose_empty_credential_ref():
    """Empty credential references are flagged as errors."""
    n8n = AsyncMock()
    n8n.get_workflow.return_value = _make_workflow(
        nodes=[
            {
                "name": "Slack",
                "type": "n8n-nodes-base.slack",
                "parameters": {},
                "credentials": {"slackApi": {}},
            }
        ]
    )

    agent = _make_agent(n8n_mock=n8n)
    result = await agent._diagnose_workflow_internal("wf-1")

    empty_issues = [i for i in result["issues"] if i["type"] == "empty_credential_ref"]
    assert len(empty_issues) == 1
    assert empty_issues[0]["severity"] == "error"


# ── Fix application tests ────────────────────────────────────────────────────


def test_apply_fix_model_replacement():
    """_apply_fix replaces deprecated model values."""
    agent = _make_agent()
    nodes = [{"name": "AI", "type": "openai", "parameters": {"model": "gpt-4-0613"}}]
    connections: Dict[str, Any] = {}

    fix = agent._apply_fix(
        {
            "type": "deprecated_model",
            "node_name": "AI",
            "param_key": "model",
            "current_value": "gpt-4-0613",
            "replacement": "gpt-4",
        },
        nodes,
        connections,
    )

    assert fix is not None
    assert fix["type"] == "model_replaced"
    assert nodes[0]["parameters"]["model"] == "gpt-4"


def test_apply_fix_node_type_migration():
    """_apply_fix migrates deprecated node types."""
    agent = _make_agent()
    nodes = [{"name": "Func", "type": "n8n-nodes-base.function", "parameters": {}}]
    connections: Dict[str, Any] = {}

    fix = agent._apply_fix(
        {
            "type": "deprecated_node_type",
            "node_name": "Func",
            "current_type": "n8n-nodes-base.function",
            "replacement_type": "n8n-nodes-base.code",
        },
        nodes,
        connections,
    )

    assert fix is not None
    assert fix["type"] == "node_type_migrated"
    assert nodes[0]["type"] == "n8n-nodes-base.code"


def test_apply_fix_dangling_source_removal():
    """_apply_fix removes dangling source connections."""
    agent = _make_agent()
    nodes: List[Dict[str, Any]] = []
    connections = {"Ghost": {"main": [[]]}}

    fix = agent._apply_fix(
        {"type": "dangling_connection_source", "source_name": "Ghost"},
        nodes,
        connections,
    )

    assert fix is not None
    assert "Ghost" not in connections


def test_apply_fix_dangling_target_removal():
    """_apply_fix removes dangling target connections."""
    agent = _make_agent()
    nodes: List[Dict[str, Any]] = []
    connections = {
        "Start": {
            "main": [
                [
                    {"node": "Ghost", "type": "main", "index": 0},
                    {"node": "Valid", "type": "main", "index": 0},
                ]
            ]
        }
    }

    fix = agent._apply_fix(
        {
            "type": "dangling_connection_target",
            "source_name": "Start",
            "target_name": "Ghost",
        },
        nodes,
        connections,
    )

    assert fix is not None
    remaining = connections["Start"]["main"][0]
    assert len(remaining) == 1
    assert remaining[0]["node"] == "Valid"


def test_apply_fix_credential_issues_return_none():
    """Credential issues are not auto-fixable."""
    agent = _make_agent()
    nodes: List[Dict[str, Any]] = []
    connections: Dict[str, Any] = {}

    fix = agent._apply_fix(
        {"type": "missing_credentials", "node_name": "Slack"},
        nodes,
        connections,
    )
    assert fix is None

    fix2 = agent._apply_fix(
        {"type": "empty_credential_ref", "node_name": "Slack"},
        nodes,
        connections,
    )
    assert fix2 is None


# ── Validation tests ─────────────────────────────────────────────────────────


def test_validate_structure_valid():
    """Valid structure returns no errors."""
    agent = _make_agent()
    nodes = [
        {"name": "Start", "type": "n8n-nodes-base.start"},
        {"name": "End", "type": "n8n-nodes-base.noOp"},
    ]
    connections = {"Start": {"main": [[{"node": "End"}]]}}

    errors = agent._validate_structure(nodes, connections)
    assert errors == []


def test_validate_structure_empty():
    """Empty node list is an error."""
    agent = _make_agent()
    errors = agent._validate_structure([], {})
    assert len(errors) == 1
    assert "no nodes" in errors[0].lower()


def test_validate_structure_duplicate_names():
    """Duplicate node names are caught."""
    agent = _make_agent()
    nodes = [
        {"name": "Node", "type": "a"},
        {"name": "Node", "type": "b"},
    ]
    errors = agent._validate_structure(nodes, {})
    assert any("Duplicate" in e for e in errors)


def test_validate_structure_missing_fields():
    """Nodes missing name or type are caught."""
    agent = _make_agent()
    nodes = [{"name": "", "type": ""}, {"type": "x"}]
    errors = agent._validate_structure(nodes, {})
    assert len(errors) >= 2


def test_validate_structure_dangling_connection():
    """Connections to non-existent source nodes are caught."""
    agent = _make_agent()
    nodes = [{"name": "Start", "type": "x"}]
    connections = {"Ghost": {"main": []}}
    errors = agent._validate_structure(nodes, connections)
    assert any("Ghost" in e for e in errors)


# ── Cooldown tests ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_cooldown_recent_repair():
    """Cooldown returns True when recent repair exists."""
    agent = _make_agent()
    recent_entry = HealLogEntry(
        id=1,
        workflow_id="wf-1",
        action="repair",
        status="success",
        created_at=datetime.utcnow() - timedelta(seconds=60),
    )
    agent._heal_log = AsyncMock()
    agent._heal_log.get_latest = AsyncMock(return_value=[recent_entry])

    assert await agent._check_cooldown("wf-1") is True


@pytest.mark.asyncio
async def test_cooldown_old_repair():
    """Cooldown returns False when last repair is old."""
    agent = _make_agent()
    old_entry = HealLogEntry(
        id=1,
        workflow_id="wf-1",
        action="repair",
        status="success",
        created_at=datetime.utcnow() - timedelta(seconds=REPAIR_COOLDOWN_SECONDS + 60),
    )
    agent._heal_log = AsyncMock()
    agent._heal_log.get_latest = AsyncMock(return_value=[old_entry])

    assert await agent._check_cooldown("wf-1") is False


@pytest.mark.asyncio
async def test_cooldown_no_history():
    """Cooldown returns False when no repair history exists."""
    agent = _make_agent()
    agent._heal_log = AsyncMock()
    agent._heal_log.get_latest = AsyncMock(return_value=[])

    assert await agent._check_cooldown("wf-1") is False


# ── Repair tests ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_repair_skips_on_cooldown():
    """repair_workflow_internal returns skipped when on cooldown."""
    n8n = AsyncMock()
    agent = _make_agent(n8n_mock=n8n)
    agent._heal_log = AsyncMock()

    # Mock cooldown as active
    agent._check_cooldown = AsyncMock(return_value=True)

    result = await agent._repair_workflow_internal("wf-1", [{"type": "deprecated_model"}])
    assert result["status"] == "skipped"
    assert result["reason"] == "cooldown"


@pytest.mark.asyncio
async def test_repair_applies_fixes_and_updates():
    """Successful repair applies fixes and calls update_workflow."""
    n8n = AsyncMock()
    wf = _make_workflow(
        nodes=[{"name": "AI", "type": "openai", "parameters": {"model": "gpt-4-0613"}}]
    )
    n8n.get_workflow.return_value = wf
    n8n.update_workflow.return_value = wf

    agent = _make_agent(n8n_mock=n8n)
    agent._heal_log = AsyncMock()
    agent._heal_log.create = AsyncMock(return_value=1)
    agent._check_cooldown = AsyncMock(return_value=False)

    issues = [
        {
            "type": "deprecated_model",
            "node_name": "AI",
            "param_key": "model",
            "current_value": "gpt-4-0613",
            "replacement": "gpt-4",
        }
    ]

    result = await agent._repair_workflow_internal("wf-1", issues)

    assert result["status"] == "repaired"
    assert result["fixes_count"] == 1
    n8n.update_workflow.assert_called_once()


@pytest.mark.asyncio
async def test_repair_rollback_on_api_failure():
    """Repair attempts rollback when update_workflow fails."""
    n8n = AsyncMock()
    wf = _make_workflow(
        nodes=[{"name": "AI", "type": "openai", "parameters": {"model": "gpt-4-0613"}}]
    )
    n8n.get_workflow.return_value = wf
    n8n.update_workflow.side_effect = [
        N8NClientError("Server error"),
        wf,  # Rollback succeeds
    ]

    agent = _make_agent(n8n_mock=n8n)
    agent._heal_log = AsyncMock()
    agent._heal_log.create = AsyncMock(return_value=1)
    agent._check_cooldown = AsyncMock(return_value=False)

    issues = [
        {
            "type": "deprecated_model",
            "node_name": "AI",
            "param_key": "model",
            "current_value": "gpt-4-0613",
            "replacement": "gpt-4",
        }
    ]

    result = await agent._repair_workflow_internal("wf-1", issues)

    assert result["status"] == "failed"
    assert result["rollback"] == "rolled_back"
    assert n8n.update_workflow.call_count == 2


@pytest.mark.asyncio
async def test_repair_no_fixable_issues():
    """Repair with only credential issues (not fixable) returns no_fixable_issues."""
    n8n = AsyncMock()
    wf = _make_workflow(nodes=[{"name": "Slack", "type": "n8n-nodes-base.slack", "parameters": {}}])
    n8n.get_workflow.return_value = wf

    agent = _make_agent(n8n_mock=n8n)
    agent._heal_log = AsyncMock()
    agent._heal_log.create = AsyncMock(return_value=1)
    agent._check_cooldown = AsyncMock(return_value=False)

    issues = [
        {
            "type": "missing_credentials",
            "severity": "warning",
            "node_name": "Slack",
        }
    ]

    result = await agent._repair_workflow_internal("wf-1", issues)
    assert result["status"] == "no_fixable_issues"


# ── Execution health tests ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_execution_health_healthy():
    """Healthy classification when error rate < 20%."""
    n8n = AsyncMock()
    executions = [
        Execution(
            id=str(i),
            workflowId="wf-1",
            status=ExecutionStatus.ERROR if i == 0 else ExecutionStatus.SUCCESS,
            startedAt=datetime.utcnow(),
        )
        for i in range(10)
    ]
    n8n.list_executions.return_value = ExecutionListResponse(data=executions)

    agent = _make_agent(n8n_mock=n8n)
    # Call the tool's underlying logic via the agent's registered tools
    result = await agent.tool_registry.execute(
        "check_execution_health", {"workflow_id": "wf-1", "limit": 10}
    )

    assert result["health"] == "healthy"
    assert result["error_rate"] == 0.1


@pytest.mark.asyncio
async def test_execution_health_unhealthy():
    """Unhealthy classification when error rate >= 50%."""
    n8n = AsyncMock()
    executions = [
        Execution(
            id=str(i),
            workflowId="wf-1",
            status=ExecutionStatus.ERROR if i < 6 else ExecutionStatus.SUCCESS,
            startedAt=datetime.utcnow(),
        )
        for i in range(10)
    ]
    n8n.list_executions.return_value = ExecutionListResponse(data=executions)

    agent = _make_agent(n8n_mock=n8n)
    result = await agent.tool_registry.execute("check_execution_health", {"workflow_id": "wf-1"})

    assert result["health"] == "unhealthy"


@pytest.mark.asyncio
async def test_execution_health_degraded():
    """Degraded classification when 20% <= error rate < 50%."""
    n8n = AsyncMock()
    executions = [
        Execution(
            id=str(i),
            workflowId="wf-1",
            status=ExecutionStatus.ERROR if i < 3 else ExecutionStatus.SUCCESS,
            startedAt=datetime.utcnow(),
        )
        for i in range(10)
    ]
    n8n.list_executions.return_value = ExecutionListResponse(data=executions)

    agent = _make_agent(n8n_mock=n8n)
    result = await agent.tool_registry.execute("check_execution_health", {"workflow_id": "wf-1"})

    assert result["health"] == "degraded"


@pytest.mark.asyncio
async def test_execution_health_no_executions():
    """Unknown health when no executions exist."""
    n8n = AsyncMock()
    n8n.list_executions.return_value = ExecutionListResponse(data=[])

    agent = _make_agent(n8n_mock=n8n)
    result = await agent.tool_registry.execute("check_execution_health", {"workflow_id": "wf-1"})

    assert result["health"] == "unknown"


# ── HealLogRepo CRUD (in-memory SQLite) ──────────────────────────────────────


@pytest.mark.asyncio
async def test_heal_log_repo_crud():
    """Create, get, get_latest with in-memory SQLite."""
    from cmo_agent.db.database import Database
    from cmo_agent.db.repositories import HealLogRepo

    db = Database(db_path=":memory:")
    await db.initialize()

    repo = HealLogRepo(db)

    # Create
    log_id = await repo.create(
        workflow_id="wf-123",
        action="repair",
        status="success",
        workflow_name="Test WF",
        issues_found=[{"type": "deprecated_model"}],
        fixes_applied=[{"type": "model_replaced"}],
    )
    assert log_id > 0

    # Get
    entry = await repo.get(log_id)
    assert entry is not None
    assert entry.workflow_id == "wf-123"
    assert entry.action == "repair"
    assert entry.status == "success"
    assert entry.issues_found == [{"type": "deprecated_model"}]
    assert entry.fixes_applied == [{"type": "model_replaced"}]

    # Get latest
    entries = await repo.get_latest("wf-123", action="repair")
    assert len(entries) == 1

    # Get recent all
    all_entries = await repo.get_recent_all(limit=10)
    assert len(all_entries) == 1

    await db.close()


# ── Session action formatting ────────────────────────────────────────────────


def test_session_format_action_workflow_healer():
    """Session formats workflow_healer_agent delegations correctly."""
    from cmo_agent.runtime.session import CMOSession

    session = CMOSession()
    action = session._format_action(
        {
            "name": "workflow_healer_agent",
            "arguments": {"instruction": "Diagnose all my workflows for issues"},
        }
    )
    assert "Workflow Healer Agent" in action
    assert "Diagnose all my workflows" in action


# ── Diagnose all workflows ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diagnose_all_workflows():
    """diagnose_all_workflows iterates all workflows."""
    n8n = AsyncMock()
    n8n.list_workflows.return_value = WorkflowListResponse(
        data=[
            _make_workflow(
                workflow_id="1",
                name="WF1",
                nodes=[{"name": "AI", "type": "openai", "parameters": {"model": "gpt-4-0613"}}],
            ),
            _make_workflow(
                workflow_id="2",
                name="WF2",
                nodes=[{"name": "Start", "type": "n8n-nodes-base.start", "parameters": {}}],
            ),
        ]
    )
    # Mock get_workflow for individual diagnosis calls
    n8n.get_workflow.side_effect = [
        _make_workflow(
            workflow_id="1",
            name="WF1",
            nodes=[{"name": "AI", "type": "openai", "parameters": {"model": "gpt-4-0613"}}],
        ),
        _make_workflow(
            workflow_id="2",
            name="WF2",
            nodes=[{"name": "Start", "type": "n8n-nodes-base.start", "parameters": {}}],
        ),
    ]

    agent = _make_agent(n8n_mock=n8n)
    result = await agent.tool_registry.execute("diagnose_all_workflows", {})

    assert result["workflows_checked"] == 2
    assert result["total_issues"] == 1  # Only WF1 has a deprecated model
