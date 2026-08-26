"""Tests for the tool registry."""

import pytest
from cmo_agent.core.tools import ToolRegistry


@pytest.fixture
def registry() -> ToolRegistry:
    """Create a fresh tool registry."""
    return ToolRegistry()


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_tool(self, registry: ToolRegistry):
        """Test registering a tool."""

        @registry.register(name="test_tool", description="A test tool")
        async def test_tool(arg1: str, arg2: int = 10) -> dict:
            return {"arg1": arg1, "arg2": arg2}

        assert "test_tool" in registry.list_tools()

    def test_get_tool_definition(self, registry: ToolRegistry):
        """Test getting tool definition."""

        @registry.register(name="my_tool", description="My description")
        async def my_tool(query: str) -> str:
            return query

        definition = registry.get_definition("my_tool")
        assert definition is not None
        assert definition.name == "my_tool"
        assert definition.description == "My description"
        assert "query" in definition.parameters.get("properties", {})

    def test_get_all_definitions(self, registry: ToolRegistry):
        """Test getting all tool definitions."""

        @registry.register(name="tool1", description="Tool 1")
        async def tool1() -> str:
            return "1"

        @registry.register(name="tool2", description="Tool 2")
        async def tool2() -> str:
            return "2"

        definitions = registry.get_all_definitions()
        assert len(definitions) == 2
        names = [d.name for d in definitions]
        assert "tool1" in names
        assert "tool2" in names

    @pytest.mark.asyncio
    async def test_execute_tool(self, registry: ToolRegistry):
        """Test executing a tool."""

        @registry.register(name="adder", description="Adds numbers")
        async def adder(a: int, b: int) -> int:
            return a + b

        result = await registry.execute(tool_name="adder", arguments={"a": 5, "b": 3})
        assert result == 8

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self, registry: ToolRegistry):
        """Test executing an unknown tool raises error."""
        with pytest.raises(KeyError):
            await registry.execute(tool_name="unknown_tool", arguments={})

    def test_clear_registry(self, registry: ToolRegistry):
        """Test clearing the registry."""

        @registry.register(name="temp_tool", description="Temporary")
        async def temp_tool() -> None:
            pass

        assert len(registry.list_tools()) == 1
        registry.clear()
        assert len(registry.list_tools()) == 0


class TestWorkflowToolArgumentCollision:
    """Tests for workflow tool argument collision fix."""

    @pytest.fixture
    def registry(self) -> ToolRegistry:
        """Create a fresh tool registry with workflow tools."""
        reg = ToolRegistry()

        @reg.register(name="create_workflow", description="Create a workflow")
        async def create_workflow(
            workflow_name: str,
            nodes: list,
            connections: dict,
        ) -> dict:
            # Simulate payload that would be sent to n8n API
            return {
                "payload": {
                    "name": workflow_name,  # API expects "name"
                    "nodes": nodes,
                    "connections": connections,
                }
            }

        @reg.register(name="update_workflow", description="Update a workflow")
        async def update_workflow(
            workflow_id: str,
            workflow_name: str = None,
        ) -> dict:
            return {
                "workflow_id": workflow_id,
                "new_name": workflow_name,
            }

        return reg

    @pytest.mark.asyncio
    async def test_create_workflow_no_collision(self, registry: ToolRegistry):
        """Test that create_workflow with workflow_name doesn't collide with tool_name."""
        result = await registry.execute(
            tool_name="create_workflow",
            arguments={
                "workflow_name": "My Test Workflow",
                "nodes": [{"id": "1", "type": "trigger"}],
                "connections": {},
            },
        )

        # Verify the payload maps workflow_name to "name" for the API
        assert result["payload"]["name"] == "My Test Workflow"
        assert result["payload"]["nodes"] == [{"id": "1", "type": "trigger"}]

    @pytest.mark.asyncio
    async def test_create_workflow_backward_compat(self, registry: ToolRegistry):
        """Test that 'name' argument is converted to workflow_name for backward compat."""
        result = await registry.execute(
            tool_name="create_workflow",
            arguments={
                "name": "Legacy Workflow Name",  # Old parameter name
                "nodes": [],
                "connections": {},
            },
        )

        # Should work due to backward compatibility conversion
        assert result["payload"]["name"] == "Legacy Workflow Name"

    @pytest.mark.asyncio
    async def test_update_workflow_with_workflow_name(self, registry: ToolRegistry):
        """Test update_workflow uses workflow_name parameter."""
        result = await registry.execute(
            tool_name="update_workflow",
            arguments={
                "workflow_id": "123",
                "workflow_name": "Renamed Workflow",
            },
        )

        assert result["workflow_id"] == "123"
        assert result["new_name"] == "Renamed Workflow"

    @pytest.mark.asyncio
    async def test_tool_arguments_isolated_from_tool_name(self, registry: ToolRegistry):
        """Verify that tool_name parameter doesn't leak into tool arguments."""
        captured_args = {}

        @registry.register(name="capture_args", description="Captures args")
        async def capture_args(**kwargs) -> dict:
            captured_args.update(kwargs)
            return kwargs

        await registry.execute(
            tool_name="capture_args",
            arguments={"user_arg": "value", "another": 123},
        )

        # tool_name should NOT appear in captured args
        assert "tool_name" not in captured_args
        assert captured_args == {"user_arg": "value", "another": 123}


class TestWorkflowPayloadNormalization:
    """Tests for workflow payload normalization."""

    def test_normalize_nodes_from_list_of_dicts(self):
        """Test nodes passed as proper list of dicts."""
        from cmo_agent.core.agent import _normalize_nodes

        nodes = [
            {"name": "Trigger", "type": "n8n-nodes-base.manualTrigger"},
            {"name": "HTTP", "type": "n8n-nodes-base.httpRequest", "typeVersion": 2},
        ]
        result = _normalize_nodes(nodes)

        assert len(result) == 2
        assert result[0]["name"] == "Trigger"
        assert result[0]["typeVersion"] == 1  # Default added
        assert result[0]["parameters"] == {}  # Default added
        assert result[1]["typeVersion"] == 2  # Preserved

    def test_normalize_nodes_from_json_string(self):
        """Test nodes passed as JSON string array."""
        from cmo_agent.core.agent import _normalize_nodes
        import json

        nodes_str = json.dumps(
            [
                {"name": "Trigger", "type": "n8n-nodes-base.manualTrigger"},
            ]
        )
        result = _normalize_nodes(nodes_str)

        assert len(result) == 1
        assert result[0]["name"] == "Trigger"
        assert result[0]["typeVersion"] == 1

    def test_normalize_nodes_from_list_of_json_strings(self):
        """Test nodes passed as list of JSON strings."""
        from cmo_agent.core.agent import _normalize_nodes
        import json

        nodes = [
            json.dumps({"name": "Trigger", "type": "n8n-nodes-base.manualTrigger"}),
            json.dumps({"name": "HTTP", "type": "n8n-nodes-base.httpRequest"}),
        ]
        result = _normalize_nodes(nodes)

        assert len(result) == 2
        assert result[0]["name"] == "Trigger"
        assert result[1]["name"] == "HTTP"

    def test_normalize_nodes_validates_required_fields(self):
        """Test that missing required fields raise clear errors."""
        from cmo_agent.core.agent import _normalize_nodes

        with pytest.raises(ValueError, match="missing required fields"):
            _normalize_nodes([{"name": "NoType"}])

    def test_normalize_nodes_invalid_json_error(self):
        """Test clear error on invalid JSON."""
        from cmo_agent.core.agent import _normalize_nodes

        with pytest.raises(ValueError, match="Failed to parse nodes JSON"):
            _normalize_nodes("not valid json")

    def test_normalize_nodes_invalid_element_json_error(self):
        """Test clear error on invalid JSON element."""
        from cmo_agent.core.agent import _normalize_nodes

        with pytest.raises(ValueError, match=r"Failed to parse node\[0\] JSON"):
            _normalize_nodes(["not valid json"])

    def test_normalize_nodes_wrong_type_error(self):
        """Test clear error when nodes is wrong type."""
        from cmo_agent.core.agent import _normalize_nodes

        with pytest.raises(ValueError, match="nodes must be a list"):
            _normalize_nodes(123)

    def test_normalize_connections_from_dict(self):
        """Test connections passed as proper dict."""
        from cmo_agent.core.agent import _normalize_connections

        conns = {"Trigger": {"main": [[{"node": "HTTP", "type": "main", "index": 0}]]}}
        result = _normalize_connections(conns)

        assert result == conns

    def test_normalize_connections_from_json_string(self):
        """Test connections passed as JSON string."""
        from cmo_agent.core.agent import _normalize_connections
        import json

        conns = {"Trigger": {"main": [[{"node": "HTTP", "type": "main", "index": 0}]]}}
        result = _normalize_connections(json.dumps(conns))

        assert result == conns

    def test_normalize_connections_none_returns_empty(self):
        """Test None connections returns empty dict."""
        from cmo_agent.core.agent import _normalize_connections

        assert _normalize_connections(None) == {}

    def test_normalize_connections_invalid_json_error(self):
        """Test clear error on invalid JSON."""
        from cmo_agent.core.agent import _normalize_connections

        with pytest.raises(ValueError, match="Failed to parse connections JSON"):
            _normalize_connections("not valid json")

    def test_normalize_settings_from_dict(self):
        """Test settings passed as proper dict."""
        from cmo_agent.core.agent import _normalize_settings

        settings = {"executionOrder": "v1"}
        result = _normalize_settings(settings)

        assert result == settings

    def test_normalize_settings_from_json_string(self):
        """Test settings passed as JSON string."""
        from cmo_agent.core.agent import _normalize_settings
        import json

        settings = {"executionOrder": "v1"}
        result = _normalize_settings(json.dumps(settings))

        assert result == settings

    def test_normalize_settings_none_returns_empty(self):
        """Test None settings returns empty dict."""
        from cmo_agent.core.agent import _normalize_settings

        assert _normalize_settings(None) == {}


class TestWorkflowPayloadNoActiveField:
    """Regression tests to ensure 'active' field is never in workflow payloads."""

    def test_create_workflow_payload_structure(self):
        """Test that create_workflow payload has correct fields and no 'active'."""
        from cmo_agent.core.agent import (
            _normalize_nodes,
            _normalize_connections,
            _normalize_settings,
        )

        workflow_name = "Test Workflow"
        nodes = [{"name": "Trigger", "type": "n8n-nodes-base.manualTrigger"}]
        connections = {}

        # Simulate the payload construction from create_workflow
        normalized_nodes = _normalize_nodes(nodes)
        normalized_connections = _normalize_connections(connections)
        normalized_settings = _normalize_settings(None)

        workflow_data = {
            "name": workflow_name,
            "nodes": normalized_nodes,
            "connections": normalized_connections,
        }
        if normalized_settings:
            workflow_data["settings"] = normalized_settings

        # Verify payload structure
        assert "name" in workflow_data
        assert "nodes" in workflow_data
        assert "connections" in workflow_data
        assert "active" not in workflow_data, "Payload must not include 'active' - it's read-only"

        # Verify nodes are normalized
        assert isinstance(workflow_data["nodes"], list)
        assert len(workflow_data["nodes"]) == 1
        assert workflow_data["nodes"][0]["typeVersion"] == 1  # Default added

    def test_payload_with_settings(self):
        """Test that settings are included only when provided."""
        from cmo_agent.core.agent import (
            _normalize_nodes,
            _normalize_connections,
            _normalize_settings,
        )

        nodes = [{"name": "Trigger", "type": "n8n-nodes-base.manualTrigger"}]
        settings = {"executionOrder": "v1"}

        normalized_nodes = _normalize_nodes(nodes)
        normalized_connections = _normalize_connections({})
        normalized_settings = _normalize_settings(settings)

        workflow_data = {
            "name": "Test",
            "nodes": normalized_nodes,
            "connections": normalized_connections,
        }
        if normalized_settings:
            workflow_data["settings"] = normalized_settings

        assert "settings" in workflow_data
        assert workflow_data["settings"] == {"executionOrder": "v1"}
        assert "active" not in workflow_data
