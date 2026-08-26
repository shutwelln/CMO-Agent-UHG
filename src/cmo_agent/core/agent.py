"""Main CMO Agent orchestrator."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Union

import structlog

from ..llm.base import BaseLLM, ToolCall
from ..n8n.client import N8NClient
from .state import AgentContext, AgentState
from .tools import ToolRegistry

logger = structlog.get_logger()


def _normalize_nodes(nodes: Any) -> List[Dict[str, Any]]:
    """Normalize nodes input to list of dicts.

    Accepts:
      - list[dict]: Pass through with validation
      - list[str]: Parse each string as JSON
      - str: Parse as JSON array

    Returns: List of validated node dicts
    Raises: ValueError with clear error message
    """
    # Case: JSON string array
    if isinstance(nodes, str):
        try:
            nodes = json.loads(nodes)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse nodes JSON string: {e}")

    if not isinstance(nodes, list):
        raise ValueError(f"nodes must be a list, got {type(nodes).__name__}")

    result = []
    for i, node in enumerate(nodes):
        # Case: JSON string element
        if isinstance(node, str):
            try:
                node = json.loads(node)
            except json.JSONDecodeError as e:
                raise ValueError(f"Failed to parse node[{i}] JSON string: {e}")

        if not isinstance(node, dict):
            raise ValueError(f"node[{i}] must be an object, got {type(node).__name__}")

        # Validate required fields
        required = ["name", "type"]
        missing = [f for f in required if f not in node]
        if missing:
            raise ValueError(f"node[{i}] missing required fields: {missing}")

        # Set defaults for optional fields
        if "typeVersion" not in node:
            node["typeVersion"] = 1
        if "position" not in node:
            node["position"] = [250 + i * 200, 300]
        if "parameters" not in node:
            node["parameters"] = {}

        result.append(node)

    return result


def _normalize_connections(connections: Any) -> Dict[str, Any]:
    """Normalize connections input to dict.

    Accepts:
      - dict: Pass through
      - str: Parse as JSON object
      - None: Return empty dict

    Returns: Connections dict
    Raises: ValueError with clear error message
    """
    if connections is None:
        return {}

    if isinstance(connections, str):
        try:
            connections = json.loads(connections)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse connections JSON string: {e}")

    if not isinstance(connections, dict):
        raise ValueError(f"connections must be an object, got {type(connections).__name__}")

    return connections


def _normalize_settings(settings: Any) -> Dict[str, Any]:
    """Normalize settings input to dict.

    Accepts:
      - dict: Pass through
      - str: Parse as JSON object
      - None: Return empty dict

    Returns: Settings dict
    Raises: ValueError with clear error message
    """
    if settings is None:
        return {}

    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse settings JSON string: {e}")

    if not isinstance(settings, dict):
        raise ValueError(f"settings must be an object, got {type(settings).__name__}")

    return settings


class CMOAgent:
    """Main CMO Agent orchestrator.

    Coordinates between LLM, n8n workflows, and marketing services
    to execute marketing automation tasks using a ReAct-style loop.
    """

    def __init__(
        self,
        llm: BaseLLM,
        n8n_client: N8NClient,
        max_iterations: int = 10,
    ):
        self.llm = llm
        self.n8n = n8n_client
        self.max_iterations = max_iterations
        self.state = AgentState.IDLE
        self.tool_registry = ToolRegistry()
        self._register_default_tools()

    def _register_default_tools(self) -> None:
        """Register default tools available to the agent."""

        @self.tool_registry.register(
            name="list_workflows",
            description="List all n8n workflows. Use this to see available automation workflows.",
        )
        async def list_workflows() -> Dict[str, Any]:
            response = await self.n8n.list_workflows()
            return {
                "workflows": [
                    {
                        "id": w.id,
                        "name": w.name,
                        "active": w.active,
                    }
                    for w in response.data
                ]
            }

        @self.tool_registry.register(
            name="get_workflow",
            description="Get details of a specific n8n workflow by its ID.",
        )
        async def get_workflow(workflow_id: str) -> Dict[str, Any]:
            workflow = await self.n8n.get_workflow(workflow_id)
            return {
                "id": workflow.id,
                "name": workflow.name,
                "active": workflow.active,
                "nodes": [n.name for n in workflow.nodes],
            }

        @self.tool_registry.register(
            name="execute_workflow",
            description="Execute an n8n workflow by its ID. Optionally pass data to the workflow.",
        )
        async def execute_workflow(
            workflow_id: str,
            data: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            execution = await self.n8n.execute_workflow(workflow_id, data)
            return {
                "execution_id": execution.id,
                "status": execution.status.value,
                "started_at": str(execution.started_at),
            }

        @self.tool_registry.register(
            name="activate_workflow",
            description="Activate an n8n workflow so it can be triggered automatically.",
        )
        async def activate_workflow(workflow_id: str) -> Dict[str, Any]:
            workflow = await self.n8n.activate_workflow(workflow_id)
            return {
                "id": workflow.id,
                "name": workflow.name,
                "active": workflow.active,
            }

        @self.tool_registry.register(
            name="deactivate_workflow",
            description="Deactivate an n8n workflow to stop automatic triggers.",
        )
        async def deactivate_workflow(workflow_id: str) -> Dict[str, Any]:
            workflow = await self.n8n.deactivate_workflow(workflow_id)
            return {
                "id": workflow.id,
                "name": workflow.name,
                "active": workflow.active,
            }

        @self.tool_registry.register(
            name="list_executions",
            description="List recent workflow executions. Optionally filter by workflow ID or status.",
        )
        async def list_executions(
            workflow_id: Optional[str] = None,
            status: Optional[str] = None,
            limit: int = 10,
        ) -> Dict[str, Any]:
            response = await self.n8n.list_executions(
                workflow_id=workflow_id,
                status=status,
                limit=limit,
            )
            return {
                "executions": [
                    {
                        "id": e.id,
                        "workflow_id": e.workflow_id,
                        "status": e.status.value,
                        "started_at": str(e.started_at),
                        "finished": e.finished,
                    }
                    for e in response.data
                ]
            }

        @self.tool_registry.register(
            name="create_workflow",
            description="""Create a new n8n workflow.

IMPORTANT: Pass nodes and connections as proper objects, NOT as JSON strings.

Parameters:
- workflow_name (string, required): Display name for the workflow
- nodes (array of objects, required): List of node objects. Each node must have:
  - name (string): Node display name
  - type (string): Node type, e.g. 'n8n-nodes-base.manualTrigger'
  - typeVersion (number, optional): Usually 1, defaults to 1
  - position (array, optional): [x, y] coordinates, auto-assigned if omitted
  - parameters (object, optional): Node-specific parameters
- connections (object, required): Maps source node names to outputs.
  Format: {"NodeName": {"main": [[{"node": "TargetNode", "type": "main", "index": 0}]]}}
- settings (object, optional): Workflow settings

Common node types:
- n8n-nodes-base.manualTrigger: Manual trigger (start node)
- n8n-nodes-base.webhook: Webhook trigger
- n8n-nodes-base.scheduleTrigger: Schedule/cron trigger
- n8n-nodes-base.httpRequest: Make HTTP requests
- n8n-nodes-base.code: Run JavaScript/Python code
- n8n-nodes-base.set: Set/transform data
- n8n-nodes-base.slack: Slack integration""",
        )
        async def create_workflow(
            workflow_name: str,
            nodes: Any,  # Accept Any for normalization
            connections: Any,  # Accept Any for normalization
            settings: Optional[Any] = None,
        ) -> Dict[str, Any]:
            # Normalize inputs to handle JSON strings from LLM
            normalized_nodes = _normalize_nodes(nodes)
            normalized_connections = _normalize_connections(connections)
            normalized_settings = _normalize_settings(settings)

            # Build payload - strict whitelist of allowed fields
            # n8n requires: name, nodes, connections, settings
            # Do NOT include "active" as it's read-only in POST /workflows
            workflow_data = {
                "name": workflow_name,
                "nodes": normalized_nodes,
                "connections": normalized_connections,
                "settings": normalized_settings,  # Required by n8n, even if empty {}
            }

            # Validate payload doesn't have read-only fields
            assert "active" not in workflow_data, "Payload must not include 'active' field"

            logger.debug("create_workflow_payload", payload=workflow_data)

            workflow = await self.n8n.create_workflow(workflow_data)
            return {
                "id": workflow.id,
                "name": workflow.name,
                "active": workflow.active,
                "message": f"Workflow '{workflow_name}' created successfully with ID {workflow.id}",
            }

        @self.tool_registry.register(
            name="update_workflow",
            description="""Update an existing n8n workflow.

IMPORTANT: Pass nodes and connections as proper objects, NOT as JSON strings.

Parameters:
- workflow_id (string, required): ID of workflow to update
- workflow_name (string, optional): New display name
- nodes (array of objects, optional): New node list (replaces all nodes)
- connections (object, optional): New connections (replaces all connections)
- settings (object, optional): New settings""",
        )
        async def update_workflow(
            workflow_id: str,
            workflow_name: Optional[str] = None,
            nodes: Optional[Any] = None,  # Accept Any for normalization
            connections: Optional[Any] = None,  # Accept Any for normalization
            settings: Optional[Any] = None,
        ) -> Dict[str, Any]:
            # Get current workflow first
            current = await self.n8n.get_workflow(workflow_id)

            # Build update payload with normalization
            workflow_data: Dict[str, Any] = {
                "name": workflow_name if workflow_name is not None else current.name,
            }

            if nodes is not None:
                workflow_data["nodes"] = _normalize_nodes(nodes)
            else:
                workflow_data["nodes"] = [n.model_dump(by_alias=True) for n in current.nodes]

            if connections is not None:
                workflow_data["connections"] = _normalize_connections(connections)
            else:
                workflow_data["connections"] = current.connections

            if settings is not None:
                workflow_data["settings"] = _normalize_settings(settings)
            else:
                workflow_data["settings"] = current.settings

            # Validate payload doesn't have read-only fields
            # Use activate_workflow/deactivate_workflow to change active state
            assert "active" not in workflow_data, "Payload must not include 'active' field"

            logger.debug("update_workflow_payload", workflow_id=workflow_id, payload=workflow_data)

            workflow = await self.n8n.update_workflow(workflow_id, workflow_data)
            return {
                "id": workflow.id,
                "name": workflow.name,
                "active": workflow.active,
                "message": f"Workflow '{workflow.name}' updated successfully",
            }

        @self.tool_registry.register(
            name="delete_workflow",
            description="Delete an n8n workflow by its ID. This action is irreversible.",
        )
        async def delete_workflow(workflow_id: str) -> Dict[str, Any]:
            # Get workflow name before deletion for confirmation
            workflow = await self.n8n.get_workflow(workflow_id)
            workflow_name = workflow.name

            await self.n8n.delete_workflow(workflow_id)
            return {
                "deleted": True,
                "workflow_id": workflow_id,
                "workflow_name": workflow_name,
                "message": f"Workflow '{workflow_name}' (ID: {workflow_id}) deleted successfully",
            }

        @self.tool_registry.register(
            name="get_workflow_json",
            description="Get the full JSON definition of a workflow including all nodes and connections. Useful for understanding workflow structure or creating similar workflows.",
        )
        async def get_workflow_json(workflow_id: str) -> Dict[str, Any]:
            workflow = await self.n8n.get_workflow(workflow_id)
            return {
                "id": workflow.id,
                "name": workflow.name,
                "active": workflow.active,
                "nodes": [n.model_dump(by_alias=True) for n in workflow.nodes],
                "connections": workflow.connections,
                "settings": workflow.settings,
            }

        @self.tool_registry.register(
            name="generate_content",
            description="Generate marketing content. Specify the type (email, social_post, ad_copy), topic, and tone.",
        )
        async def generate_content(
            content_type: str,
            topic: str,
            tone: str = "professional",
            channel: Optional[str] = None,
        ) -> Dict[str, Any]:
            # Use the LLM to generate content
            from ..llm.base import Message

            prompt = f"""Generate {content_type} content about: {topic}

Tone: {tone}
{"Channel: " + channel if channel else ""}

Provide the content in a format ready to use. Include:
1. A compelling headline/subject line
2. The main body content
3. A call to action

Be concise and engaging."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.8,
            )

            return {
                "content_type": content_type,
                "topic": topic,
                "generated_content": response.content,
            }

    async def process_message(
        self,
        message: str,
        context: AgentContext,
    ) -> str:
        """Process a user message and return a response.

        Implements a ReAct-style loop:
        1. Think about the task
        2. Decide on actions (tool calls)
        3. Execute actions
        4. Observe results
        5. Continue or respond
        """
        self.state = AgentState.THINKING

        # Add user message to context
        context.add_user_message(message)

        iteration = 0
        all_tool_calls: List[Dict[str, Any]] = []

        while iteration < self.max_iterations:
            iteration += 1
            logger.info("agent_iteration", iteration=iteration)

            # Get LLM response with available tools
            response = await self.llm.complete(
                messages=context.to_messages_for_llm(),
                tools=self.tool_registry.get_all_definitions(),
            )

            # If no tool calls, we have a final response
            if not response.tool_calls:
                self.state = AgentState.IDLE
                context.add_assistant_message(response.content)
                context.record_turn(message, response.content, all_tool_calls)
                return response.content

            # Execute tool calls
            self.state = AgentState.EXECUTING

            # Add assistant message with tool calls
            context.add_assistant_message(
                response.content,
                [tc.model_dump() for tc in response.tool_calls],
            )

            for tool_call in response.tool_calls:
                logger.info(
                    "executing_tool",
                    tool=tool_call.name,
                    arguments=tool_call.arguments,
                )

                all_tool_calls.append(
                    {
                        "name": tool_call.name,
                        "arguments": tool_call.arguments,
                    }
                )

                try:
                    result = await self.tool_registry.execute(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                    )
                    result_str = str(result)
                except Exception as e:
                    logger.error("tool_execution_failed", error=str(e))
                    result_str = f"Error: {e}"

                # Add tool result to context
                context.add_tool_result(tool_call.id, result_str)

            self.state = AgentState.THINKING

        # Max iterations reached
        self.state = AgentState.ERROR
        final_message = "I apologize, but I was unable to complete the task within the allowed iterations. Please try breaking down your request into smaller steps."
        context.add_assistant_message(final_message)
        return final_message

    async def health_check(self) -> Dict[str, Any]:
        """Check the health of agent dependencies."""
        n8n_healthy = await self.n8n.health_check()

        return {
            "agent": "healthy",
            "n8n": "healthy" if n8n_healthy else "unhealthy",
            "tools_registered": len(self.tool_registry.list_tools()),
        }

    def get_state(self) -> AgentState:
        """Get the current agent state."""
        return self.state

    def list_available_tools(self) -> List[str]:
        """List all tools available to the agent."""
        return self.tool_registry.list_tools()
