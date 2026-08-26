"""Workflow Builder Agent — designs, builds, validates, and deploys n8n workflows.

Takes natural language descriptions and produces fully configured, credential-
resolved n8n workflows.  Uses the shared N8NService layer for construction
helpers, credential resolution, and community search.

Approval flow:
  1. User describes what they want
  2. Agent asks clarifying questions if needed
  3. Agent builds the workflow and presents a summary for approval
  4. User approves → agent deploys to n8n (inactive) and returns a link
  5. User reviews in n8n → tells the agent to activate (move to production)
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import BuildLogRepo
from ..llm.base import BaseLLM
from ..n8n.client import N8NClientError
from ..n8n.service import N8NService
from .base import BaseAgent

logger = structlog.get_logger()


class WorkflowBuilderAgent(BaseAgent):
    """Designs and deploys n8n workflows from natural language descriptions."""

    agent_id = "workflow_builder_agent"
    agent_name = "Workflow Builder Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        n8n_service: N8NService,
        n8n_base_url: str = "",
        max_iterations: int = 15,
    ) -> None:
        self._service = n8n_service
        self._build_log = BuildLogRepo(db)
        self._n8n_base_url = n8n_base_url.rstrip("/")
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return f"""You are the Workflow Builder Agent, a specialist in designing and deploying n8n automation workflows.

You build workflows from natural language descriptions. You have deep knowledge of:
- 800+ n8n nodes (triggers, actions, transformations, AI/LangChain nodes)
- Workflow architecture patterns (webhook processing, scheduled tasks, data pipelines, AI agents)
- Node configuration (parameters, credentials, expressions)
- n8n expression syntax ({{{{ $json.field }}}}, {{{{ $node["Name"].json.field }}}})

YOUR WORKFLOW:
1. UNDERSTAND the request — ask clarifying questions if the user's intent is ambiguous
2. PLAN the workflow — decide which nodes are needed, what trigger to use, how data flows
3. BUILD the workflow — use build_workflow to construct it with proper node configs and connections
4. PRESENT the summary — show the user what you built and ask for approval
5. DEPLOY — after approval, deploy to n8n as inactive and provide a direct link
6. ACTIVATE — when the user confirms after review, activate the workflow

ARCHITECTURE GUIDELINES:
- Every workflow needs a trigger (Webhook, Schedule, Form, Manual, or Event trigger)
- Use the Set node to reshape/clean data between steps
- Use the IF node for conditional branching
- Use the Code node (JavaScript) for complex data transformations
- For error handling, add Error Trigger workflows or set continueOnFail on critical nodes
- Position nodes left-to-right with ~250px spacing
- Keep node names descriptive and unique

CREDENTIAL HANDLING:
- Always use resolve_credentials to find existing credentials in the n8n instance
- If a credential is missing, flag it clearly so the user can configure it in n8n
- Never ask the user for raw API keys — credentials are managed in n8n's UI

APPROVAL PROTOCOL:
- ALWAYS present a summary before deploying. Include: node list, flow diagram, credential status
- Wait for explicit user approval before calling deploy_workflow
- After deployment, tell the user to review in n8n and come back to activate
- Only call activate_workflow after the user explicitly confirms

GOOGLE SHEETS NODE RULES:
- ONLY use the 'append' operation for writing rows. NEVER use 'update' or 'appendOrUpdate'
  -- they fail when configured via the API (matchingColumns resolution bug in v4.5+).
- For append operations, use mappingMode: 'autoMapInputData' (NOT 'defineBelow').
  The 'defineBelow' mode requires a positional schema array that breaks if sheet columns
  are added, removed, or reordered after setup. autoMapInputData maps by column name and
  is resilient to sheet changes.
- Always use authentication: 'serviceAccount' with the CMO Agent Service Account credential.
- Reference sheets by mode: 'id' (not URL or name).
- For row updates (not appends), use an HTTP Request node calling the Sheets API directly
  (values.batchUpdate) instead of the Google Sheets node.
- Code nodes preceding a Google Sheets append should output ONLY the fields that match
  sheet column headers -- strip internal/temp fields (e.g., _original, _meta) before the
  append node.

n8n instance URL: {self._n8n_base_url}
"""

    def register_tools(self) -> None:
        """Register all workflow builder tools."""

        @self.tool_registry.register(
            name="list_existing_workflows",
            description="List all workflows currently in the n8n instance. Useful to avoid duplicates and understand what already exists.",
        )
        async def list_existing_workflows() -> Dict[str, Any]:
            try:
                workflows = await self._service.list_workflows()
                return {"count": len(workflows), "workflows": workflows}
            except N8NClientError as e:
                return {"error": str(e)}

        @self.tool_registry.register(
            name="get_workflow_details",
            description="Get full details of an existing workflow by ID. Useful for understanding existing patterns or modifying workflows.",
        )
        async def get_workflow_details(workflow_id: str) -> Dict[str, Any]:
            try:
                wf = await self._service.get_workflow(workflow_id)
                nodes = [
                    {
                        "name": n.name,
                        "type": n.type,
                        "parameters": n.parameters,
                        "credentials": n.credentials,
                    }
                    for n in wf.nodes
                ]
                return {
                    "id": wf.id,
                    "name": wf.name,
                    "active": wf.active,
                    "nodes": nodes,
                    "connections": wf.connections,
                    "settings": wf.settings,
                }
            except N8NClientError as e:
                return {"error": str(e)}

        @self.tool_registry.register(
            name="resolve_credentials",
            description="Look up existing credentials in the n8n instance for given node types. Pass a list of node type strings (e.g. ['n8n-nodes-base.slack', 'n8n-nodes-base.gmail']). Returns found credentials and warnings for missing ones.",
        )
        async def resolve_credentials(
            node_types: List[str],
        ) -> Dict[str, Any]:
            results: Dict[str, Any] = {}
            warnings: List[str] = []
            for ntype in node_types:
                cred_ref, warning = await self._service.resolve_credentials_for_node(ntype)
                if cred_ref:
                    results[ntype] = cred_ref
                if warning:
                    warnings.append(warning)
            return {"credentials": results, "warnings": warnings}

        @self.tool_registry.register(
            name="build_workflow",
            description=(
                "Build an n8n workflow from a structured specification. "
                "Pass: workflow_name (str), nodes (list of node dicts with keys: "
                "name, type, parameters, typeVersion), connections (list of "
                "[source_name, target_name] pairs for linear flow, or list of "
                "[source_name, target_name, source_output_idx, target_input_idx] "
                "for complex routing). Credentials are auto-resolved. "
                "Returns the workflow summary and validation result — does NOT deploy yet."
            ),
        )
        async def build_workflow(
            workflow_name: str,
            nodes: List[Dict[str, Any]],
            connections: List[List[Any]],
        ) -> Dict[str, Any]:
            # Generate IDs and position nodes
            built_nodes: List[Dict[str, Any]] = []
            for i, node_spec in enumerate(nodes):
                node = self._service.build_node(
                    node_id=self._service.generate_node_id(),
                    name=node_spec["name"],
                    node_type=node_spec["type"],
                    position=[250 + i * 250, 300],
                    parameters=node_spec.get("parameters", {}),
                    type_version=node_spec.get("typeVersion", 1.0),
                )
                built_nodes.append(node)

            # Resolve credentials
            built_nodes, cred_warnings = await self._service.resolve_all_credentials(built_nodes)

            # Build connections
            if connections and len(connections[0]) == 2:
                # Simple linear connections: [[A, B], [B, C]]
                node_chain = [connections[0][0]]
                for edge in connections:
                    if edge[1] not in node_chain:
                        node_chain.append(edge[1])
                built_connections = self._service.build_linear_connections(node_chain)
            elif connections and len(connections[0]) >= 4:
                # Complex connections: [[source, target, src_idx, tgt_idx]]
                edges = [(e[0], e[1], e[2], e[3]) for e in connections]
                built_connections = self._service.build_connections(edges)
            else:
                built_connections = {}

            # Validate
            errors = self._service.validate_workflow_structure(built_nodes, built_connections)

            # Generate summary
            summary = self._service.summarize_workflow(
                workflow_name, built_nodes, built_connections
            )

            # Store in context for deploy step
            result = {
                "status": "ready_for_approval" if not errors else "has_errors",
                "workflow_name": workflow_name,
                "node_count": len(built_nodes),
                "summary": summary,
                "validation_errors": errors,
                "credential_warnings": cred_warnings,
                "nodes": built_nodes,
                "connections": built_connections,
            }

            # Log the build attempt
            connections_desc = []
            for src, conn_data in built_connections.items():
                if isinstance(conn_data, dict):
                    for _, outputs in conn_data.items():
                        if isinstance(outputs, list):
                            for group in outputs:
                                if isinstance(group, list):
                                    for c in group:
                                        connections_desc.append(f"{src} → {c.get('node', '?')}")

            nodes_summary = [{"name": n["name"], "type": n["type"]} for n in built_nodes]

            await self._build_log.create(
                workflow_name=workflow_name,
                request=f"Build: {workflow_name}",
                status="ready_for_approval" if not errors else "validation_errors",
                node_count=len(built_nodes),
                nodes_summary=nodes_summary,
                connections_summary=connections_desc,
                credential_warnings=cred_warnings if cred_warnings else None,
            )

            return result

        @self.tool_registry.register(
            name="deploy_workflow",
            description=(
                "Deploy a built workflow to the n8n instance (created as INACTIVE). "
                "Pass the workflow_name, nodes, and connections exactly as returned by build_workflow. "
                "Returns the workflow ID and a direct link to view it in n8n. "
                "ONLY call this after the user has approved the workflow summary."
            ),
        )
        async def deploy_workflow(
            workflow_name: str,
            nodes: List[Dict[str, Any]],
            connections: Dict[str, Any],
        ) -> Dict[str, Any]:
            try:
                wf = await self._service.create_workflow(
                    name=workflow_name,
                    nodes=nodes,
                    connections=connections,
                )

                workflow_url = (
                    f"{self._n8n_base_url}/workflow/{wf.id}" if self._n8n_base_url else None
                )

                # Log successful deployment
                await self._build_log.create(
                    workflow_name=workflow_name,
                    request=f"Deploy: {workflow_name}",
                    status="deployed_inactive",
                    workflow_id=wf.id,
                    node_count=len(nodes),
                    workflow_url=workflow_url,
                )

                return {
                    "status": "deployed",
                    "workflow_id": wf.id,
                    "workflow_name": wf.name,
                    "active": wf.active,
                    "workflow_url": workflow_url,
                    "message": "Workflow deployed as INACTIVE. Review it in n8n and tell me when you're ready to activate.",
                }
            except N8NClientError as e:
                await self._build_log.create(
                    workflow_name=workflow_name,
                    request=f"Deploy: {workflow_name}",
                    status="deploy_failed",
                    node_count=len(nodes),
                    error_message=str(e),
                )
                return {"error": f"Failed to deploy: {e}"}

        @self.tool_registry.register(
            name="activate_workflow",
            description=(
                "Activate a workflow (move to production). "
                "ONLY call this after the user has reviewed the workflow in n8n and "
                "explicitly confirmed it should go live."
            ),
        )
        async def activate_workflow(workflow_id: str) -> Dict[str, Any]:
            try:
                wf = await self._service.activate_workflow(workflow_id)
                workflow_url = (
                    f"{self._n8n_base_url}/workflow/{wf.id}" if self._n8n_base_url else None
                )

                await self._build_log.create(
                    workflow_name=wf.name,
                    request=f"Activate: {wf.name}",
                    status="activated",
                    workflow_id=workflow_id,
                    workflow_url=workflow_url,
                )

                return {
                    "status": "activated",
                    "workflow_id": wf.id,
                    "workflow_name": wf.name,
                    "active": True,
                    "workflow_url": workflow_url,
                }
            except N8NClientError as e:
                return {"error": f"Failed to activate: {e}"}

        @self.tool_registry.register(
            name="deactivate_workflow",
            description="Deactivate (pause) a live workflow. It will stop processing triggers.",
        )
        async def deactivate_workflow(workflow_id: str) -> Dict[str, Any]:
            try:
                wf = await self._service.deactivate_workflow(workflow_id)
                return {
                    "status": "deactivated",
                    "workflow_id": wf.id,
                    "workflow_name": wf.name,
                    "active": False,
                }
            except N8NClientError as e:
                return {"error": f"Failed to deactivate: {e}"}

        @self.tool_registry.register(
            name="test_workflow",
            description=(
                "Test-execute a workflow by ID. Works for workflows with webhook, form, "
                "or manual triggers. Returns execution status and results."
            ),
        )
        async def test_workflow(
            workflow_id: str, test_data: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            return await self._service.test_workflow(workflow_id, test_data)

        @self.tool_registry.register(
            name="update_workflow",
            description=(
                "Update an existing workflow with new nodes and/or connections. "
                "Pass workflow_id and optionally: new_name, nodes (full replacement), "
                "connections (full replacement). Useful for iterating on a workflow "
                "after user feedback."
            ),
        )
        async def update_workflow(
            workflow_id: str,
            new_name: Optional[str] = None,
            nodes: Optional[List[Dict[str, Any]]] = None,
            connections: Optional[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            try:
                # Resolve credentials if nodes are being updated
                if nodes:
                    nodes, cred_warnings = await self._service.resolve_all_credentials(nodes)
                else:
                    cred_warnings = []

                wf = await self._service.update_workflow(
                    workflow_id=workflow_id,
                    name=new_name,
                    nodes=nodes,
                    connections=connections,
                )
                workflow_url = (
                    f"{self._n8n_base_url}/workflow/{wf.id}" if self._n8n_base_url else None
                )

                return {
                    "status": "updated",
                    "workflow_id": wf.id,
                    "workflow_name": wf.name,
                    "workflow_url": workflow_url,
                    "credential_warnings": cred_warnings,
                }
            except N8NClientError as e:
                return {"error": f"Failed to update: {e}"}

        @self.tool_registry.register(
            name="delete_workflow",
            description="Permanently delete a workflow. This cannot be undone.",
        )
        async def delete_workflow(workflow_id: str) -> Dict[str, Any]:
            try:
                await self._service.delete_workflow(workflow_id)
                return {"status": "deleted", "workflow_id": workflow_id}
            except N8NClientError as e:
                return {"error": f"Failed to delete: {e}"}

        @self.tool_registry.register(
            name="search_community",
            description=(
                "Search the n8n community forum for workflow patterns, solutions, "
                "and troubleshooting help. Pass a search query. "
                "Use this for inspiration or when you encounter a challenge."
            ),
        )
        async def search_community(query: str, limit: int = 5) -> Dict[str, Any]:
            results = await self._service.search_community(query, limit)
            return {"query": query, "results_count": len(results), "results": results}

        @self.tool_registry.register(
            name="get_build_history",
            description="View recent workflow build history. Shows what workflows have been built, their status, and any issues.",
        )
        async def get_build_history(limit: int = 10) -> Dict[str, Any]:
            entries = await self._build_log.get_recent(limit)
            return {
                "count": len(entries),
                "builds": [
                    {
                        "id": e.id,
                        "workflow_id": e.workflow_id,
                        "workflow_name": e.workflow_name,
                        "status": e.status,
                        "node_count": e.node_count,
                        "workflow_url": e.workflow_url,
                        "error": e.error_message,
                        "created_at": str(e.created_at) if e.created_at else None,
                    }
                    for e in entries
                ],
            }
