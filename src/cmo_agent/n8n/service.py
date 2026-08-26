"""Shared n8n service layer — high-level operations used by Builder and Healer agents.

Wraps the low-level N8NClient REST API with domain-aware helpers for
workflow construction, credential resolution, node configuration, and
community knowledge retrieval.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import httpx
import structlog

from .client import N8NClient, N8NClientError
from .models import Workflow

logger = structlog.get_logger()

# ── Well-known node types and their typical credential types ────────────────

CREDENTIAL_MAP: Dict[str, str] = {
    "n8n-nodes-base.slack": "slackApi",
    "n8n-nodes-base.gmail": "gmailOAuth2Api",
    "n8n-nodes-base.googleSheets": "googleSheetsOAuth2Api",
    "n8n-nodes-base.googleDrive": "googleDriveOAuth2Api",
    "n8n-nodes-base.googleCalendar": "googleCalendarOAuth2Api",
    "n8n-nodes-base.notion": "notionApi",
    "n8n-nodes-base.airtable": "airtableTokenApi",
    "n8n-nodes-base.hubspot": "hubspotApi",
    "n8n-nodes-base.telegram": "telegramApi",
    "n8n-nodes-base.stripe": "stripeApi",
    "n8n-nodes-base.openAi": "openAiApi",
    "@n8n/n8n-nodes-langchain.lmChatOpenAi": "openAiApi",
    "@n8n/n8n-nodes-langchain.lmChatAnthropic": "anthropicApi",
    "n8n-nodes-base.httpRequest": "httpHeaderAuth",
    "n8n-nodes-base.postgres": "postgres",
    "n8n-nodes-base.mysql": "mySql",
    "n8n-nodes-base.microsoftOutlook": "microsoftOutlookOAuth2Api",
    "n8n-nodes-base.discord": "discordBotApi",
    "n8n-nodes-base.github": "githubApi",
    "n8n-nodes-base.jira": "jiraSoftwareCloudApi",
    "n8n-nodes-base.twilio": "twilioApi",
    "n8n-nodes-base.sendGrid": "sendGridApi",
    "n8n-nodes-base.mailchimp": "mailchimpApi",
}

# Nodes that never need credentials
NO_CREDENTIAL_NODES = {
    "n8n-nodes-base.set",
    "n8n-nodes-base.code",
    "n8n-nodes-base.if",
    "n8n-nodes-base.switch",
    "n8n-nodes-base.merge",
    "n8n-nodes-base.splitInBatches",
    "n8n-nodes-base.noOp",
    "n8n-nodes-base.stickyNote",
    "n8n-nodes-base.manualTrigger",
    "n8n-nodes-base.scheduleTrigger",
    "n8n-nodes-base.webhook",
    "n8n-nodes-base.respondToWebhook",
    "n8n-nodes-base.formTrigger",
    "n8n-nodes-base.dateTime",
    "n8n-nodes-base.crypto",
    "n8n-nodes-base.xml",
    "n8n-nodes-base.html",
    "n8n-nodes-base.markdown",
    "n8n-nodes-base.convertToFile",
    "n8n-nodes-base.extractFromFile",
    "n8n-nodes-base.wait",
    "n8n-nodes-base.executeWorkflow",
    "n8n-nodes-base.errorTrigger",
    "n8n-nodes-base.start",
}


class N8NService:
    """High-level n8n operations shared by Workflow Builder and Healer agents.

    Provides:
    - Credential discovery and resolution
    - Workflow construction helpers (positioning, connection building)
    - Workflow validation and testing
    - Community / template search via web scraping
    """

    def __init__(self, n8n_client: N8NClient) -> None:
        self._client = n8n_client
        self._credentials_cache: Optional[List[Dict[str, Any]]] = None

    # ── Credential Management ─────────────────────────────────────────────

    async def list_credentials(self) -> List[Dict[str, Any]]:
        """List all credentials configured in the n8n instance."""
        if self._credentials_cache is not None:
            return self._credentials_cache

        try:
            client = await self._client._ensure_client()
            response = await client.request("GET", "/credentials")
            response.raise_for_status()
            data = response.json()
            self._credentials_cache = data.get("data", data) if isinstance(data, dict) else data
            return self._credentials_cache
        except Exception as e:
            logger.warning("credentials_list_failed", error=str(e))
            return []

    async def find_credential(self, credential_type: str) -> Optional[Dict[str, Any]]:
        """Find an existing credential by type name.

        Returns the first matching credential dict or None.
        """
        creds = await self.list_credentials()
        for cred in creds:
            cred_type = cred.get("type", "")
            if cred_type == credential_type:
                return cred
        return None

    async def resolve_credentials_for_node(
        self, node_type: str
    ) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """Resolve credentials for a node type.

        Returns:
            (credential_ref, warning_message)
            - credential_ref: dict like {"slackApi": {"id": "123", "name": "My Slack"}} or None
            - warning_message: human-readable warning if cred not found, else None
        """
        if node_type in NO_CREDENTIAL_NODES:
            return None, None

        expected_type = CREDENTIAL_MAP.get(node_type)
        if not expected_type:
            return None, None

        cred = await self.find_credential(expected_type)
        if cred:
            return {
                expected_type: {"id": str(cred["id"]), "name": cred.get("name", expected_type)}
            }, None

        return (
            None,
            f"No '{expected_type}' credential found in n8n for node type '{node_type}'. You'll need to configure this in the n8n UI.",
        )

    async def resolve_all_credentials(
        self, nodes: List[Dict[str, Any]]
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """Resolve credentials for all nodes in a workflow.

        Mutates node dicts in place to add credential references.
        Returns (updated_nodes, warnings).
        """
        warnings: List[str] = []
        for node in nodes:
            node_type = node.get("type", "")
            cred_ref, warning = await self.resolve_credentials_for_node(node_type)
            if cred_ref:
                node["credentials"] = cred_ref
            if warning:
                warnings.append(warning)
        return nodes, warnings

    def invalidate_credential_cache(self) -> None:
        """Clear the credential cache to force re-fetch."""
        self._credentials_cache = None

    # ── Workflow Construction Helpers ──────────────────────────────────────

    @staticmethod
    def build_node(
        node_id: str,
        name: str,
        node_type: str,
        position: List[int],
        parameters: Optional[Dict[str, Any]] = None,
        type_version: float = 1.0,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build a properly structured n8n node dict."""
        node: Dict[str, Any] = {
            "id": node_id,
            "name": name,
            "type": node_type,
            "typeVersion": type_version,
            "position": position,
            "parameters": parameters or {},
        }
        if credentials:
            node["credentials"] = credentials
        return node

    @staticmethod
    def auto_position_nodes(
        nodes: List[Dict[str, Any]], start_x: int = 250, start_y: int = 300, spacing_x: int = 250
    ) -> List[Dict[str, Any]]:
        """Auto-position nodes in a left-to-right flow."""
        for i, node in enumerate(nodes):
            node["position"] = [start_x + i * spacing_x, start_y]
        return nodes

    @staticmethod
    def build_linear_connections(node_names: List[str]) -> Dict[str, Any]:
        """Build connections for a linear chain of nodes (A → B → C → ...)."""
        connections: Dict[str, Any] = {}
        for i in range(len(node_names) - 1):
            connections[node_names[i]] = {
                "main": [[{"node": node_names[i + 1], "type": "main", "index": 0}]]
            }
        return connections

    @staticmethod
    def build_connections(edges: List[Tuple[str, str, int, int]]) -> Dict[str, Any]:
        """Build connections from a list of edges.

        Each edge is (source_name, target_name, source_output_index, target_input_index).
        """
        connections: Dict[str, Any] = {}
        for source, target, source_idx, target_idx in edges:
            if source not in connections:
                connections[source] = {"main": []}
            main = connections[source]["main"]
            # Ensure enough output slots
            while len(main) <= source_idx:
                main.append([])
            main[source_idx].append(
                {
                    "node": target,
                    "type": "main",
                    "index": target_idx,
                }
            )
        return connections

    @staticmethod
    def generate_node_id() -> str:
        """Generate a UUID-style node ID matching n8n's format."""
        from uuid import uuid4

        return str(uuid4())

    # ── Workflow CRUD (delegation to client) ──────────────────────────────

    async def create_workflow(
        self,
        name: str,
        nodes: List[Dict[str, Any]],
        connections: Dict[str, Any],
        settings: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """Create a workflow in n8n. Returns the created Workflow."""
        payload: Dict[str, Any] = {
            "name": name,
            "nodes": nodes,
            "connections": connections,
            "settings": settings or {"executionOrder": "v1"},
        }
        return await self._client.create_workflow(payload)

    async def update_workflow(
        self,
        workflow_id: str,
        name: Optional[str] = None,
        nodes: Optional[List[Dict[str, Any]]] = None,
        connections: Optional[Dict[str, Any]] = None,
        settings: Optional[Dict[str, Any]] = None,
    ) -> Workflow:
        """Update an existing workflow."""
        wf = await self._client.get_workflow(workflow_id)
        payload: Dict[str, Any] = {
            "name": name or wf.name,
            "nodes": nodes or [n.model_dump(by_alias=True) for n in wf.nodes],
            "connections": connections if connections is not None else wf.connections,
            "settings": settings or wf.settings,
        }
        return await self._client.update_workflow(workflow_id, payload)

    async def activate_workflow(self, workflow_id: str) -> Workflow:
        """Activate a workflow (move to production)."""
        return await self._client.activate_workflow(workflow_id)

    async def deactivate_workflow(self, workflow_id: str) -> Workflow:
        """Deactivate a workflow."""
        return await self._client.deactivate_workflow(workflow_id)

    async def get_workflow(self, workflow_id: str) -> Workflow:
        """Get a workflow by ID."""
        return await self._client.get_workflow(workflow_id)

    async def list_workflows(self) -> List[Dict[str, Any]]:
        """List all workflows as simple dicts."""
        response = await self._client.list_workflows()
        return [{"id": w.id, "name": w.name, "active": w.active} for w in response.data]

    async def delete_workflow(self, workflow_id: str) -> None:
        """Delete a workflow."""
        await self._client.delete_workflow(workflow_id)

    # ── Execution & Testing ───────────────────────────────────────────────

    async def test_workflow(
        self, workflow_id: str, data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Execute a workflow and return the result."""
        try:
            execution = await self._client.execute_workflow(workflow_id, data)
            return {
                "execution_id": execution.id,
                "status": execution.status.value,
                "finished": execution.finished,
            }
        except N8NClientError as e:
            return {"error": str(e), "status": "failed"}

    async def get_execution_details(self, execution_id: str) -> Dict[str, Any]:
        """Get details for a specific execution."""
        try:
            execution = await self._client.get_execution(execution_id)
            return {
                "id": execution.id,
                "status": execution.status.value,
                "finished": execution.finished,
                "mode": execution.mode,
            }
        except N8NClientError as e:
            return {"error": str(e)}

    async def check_execution_health(self, workflow_id: str, limit: int = 20) -> Dict[str, Any]:
        """Analyze recent executions for error rate patterns."""
        try:
            exec_resp = await self._client.list_executions(workflow_id=workflow_id, limit=limit)
        except N8NClientError as e:
            return {"error": f"Failed to list executions: {e}"}

        executions = exec_resp.data
        if not executions:
            return {
                "workflow_id": workflow_id,
                "health": "unknown",
                "message": "No recent executions found.",
            }

        total = len(executions)
        errors = sum(1 for ex in executions if ex.status.value == "error")
        error_rate = errors / total if total > 0 else 0.0

        if error_rate >= 0.5:
            health = "unhealthy"
        elif error_rate >= 0.2:
            health = "degraded"
        else:
            health = "healthy"

        return {
            "workflow_id": workflow_id,
            "health": health,
            "total_executions": total,
            "error_count": errors,
            "error_rate": round(error_rate, 2),
        }

    # ── Community Search ──────────────────────────────────────────────────

    async def search_community(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """Search the n8n community forum for solutions and patterns.

        Scrapes community.n8n.io search results.
        Returns list of {title, url, excerpt} dicts.
        """
        results: List[Dict[str, Any]] = []
        try:
            async with httpx.AsyncClient(timeout=15.0) as http:
                response = await http.get(
                    "https://community.n8n.io/search.json",
                    params={"q": query, "order": "relevance"},
                )
                response.raise_for_status()
                data = response.json()

                topics = data.get("topics", [])
                for topic in topics[:limit]:
                    results.append(
                        {
                            "title": topic.get("title", ""),
                            "url": f"https://community.n8n.io/t/{topic.get('slug', '')}/{topic.get('id', '')}",
                            "excerpt": topic.get("excerpt", topic.get("blurb", ""))[:200],
                            "views": topic.get("views", 0),
                            "reply_count": topic.get("reply_count", 0),
                            "like_count": topic.get("like_count", 0),
                        }
                    )
        except Exception as e:
            logger.warning("community_search_failed", query=query, error=str(e))

        return results

    # ── Workflow Validation Helpers ────────────────────────────────────────

    @staticmethod
    def validate_workflow_structure(
        nodes: List[Dict[str, Any]],
        connections: Dict[str, Any],
    ) -> List[str]:
        """Validate workflow structure. Returns list of error strings."""
        errors: List[str] = []

        if not nodes:
            errors.append("Workflow has no nodes.")
            return errors

        node_names = set()
        has_trigger = False
        for node in nodes:
            name = node.get("name")
            if not name:
                errors.append("Node missing 'name' field.")
            elif name in node_names:
                errors.append(f"Duplicate node name: '{name}'.")
            else:
                node_names.add(name)

            ntype = node.get("type", "")
            if not ntype:
                errors.append(f"Node '{name}' missing 'type' field.")
            if "trigger" in ntype.lower() or "webhook" in ntype.lower():
                has_trigger = True

        if not has_trigger:
            errors.append("Workflow has no trigger node. It won't start automatically.")

        # Validate connections reference real nodes
        for source_name, conn_data in connections.items():
            if source_name not in node_names:
                errors.append(f"Connection references non-existent source: '{source_name}'.")
            if isinstance(conn_data, dict):
                for output_key, outputs in conn_data.items():
                    if isinstance(outputs, list):
                        for output_group in outputs:
                            if isinstance(output_group, list):
                                for conn in output_group:
                                    target = conn.get("node")
                                    if target and target not in node_names:
                                        errors.append(
                                            f"Connection from '{source_name}' targets non-existent node: '{target}'."
                                        )

        return errors

    @staticmethod
    def summarize_workflow(
        name: str,
        nodes: List[Dict[str, Any]],
        connections: Dict[str, Any],
    ) -> str:
        """Generate a human-readable summary of a workflow for approval."""
        lines = [f"**Workflow: {name}**", f"**Nodes ({len(nodes)}):**"]
        for i, node in enumerate(nodes, 1):
            ntype = (
                node.get("type", "unknown")
                .replace("n8n-nodes-base.", "")
                .replace("@n8n/n8n-nodes-langchain.", "")
            )
            lines.append(f"  {i}. {node.get('name', 'unnamed')} ({ntype})")

        lines.append(f"\n**Flow:**")
        # Build flow description
        if connections:
            for source, conn_data in connections.items():
                if isinstance(conn_data, dict):
                    for output_key, outputs in conn_data.items():
                        if isinstance(outputs, list):
                            for output_group in outputs:
                                if isinstance(output_group, list):
                                    for conn in output_group:
                                        target = conn.get("node", "?")
                                        lines.append(f"  {source} → {target}")
        else:
            lines.append("  (no connections)")

        return "\n".join(lines)
