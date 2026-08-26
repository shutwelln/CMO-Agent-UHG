"""Workflow Healer Agent - diagnoses, repairs, and rolls back broken n8n workflows."""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import HealLogRepo
from ..llm.base import BaseLLM
from ..n8n.client import N8NClient, N8NClientError
from ..n8n.service import N8NService
from .base import BaseAgent

logger = structlog.get_logger()

# ── Deprecation / migration maps ──────────────────────────────────────────────

MODEL_DEPRECATION_MAP: Dict[str, str] = {
    # OpenAI
    "gpt-4-0613": "gpt-4",
    "gpt-4-0314": "gpt-4",
    "gpt-4-32k-0613": "gpt-4",
    "gpt-4-32k-0314": "gpt-4",
    "gpt-4-turbo": "gpt-4o-mini",
    "gpt-4-turbo-preview": "gpt-4o-mini",
    "gpt-4-1106-preview": "gpt-4o-mini",
    "gpt-4-0125-preview": "gpt-4o-mini",
    "gpt-3.5-turbo-0613": "gpt-3.5-turbo",
    "gpt-3.5-turbo-0301": "gpt-3.5-turbo",
    "gpt-3.5-turbo-1106": "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k-0613": "gpt-3.5-turbo",
    "gpt-3.5-turbo-16k": "gpt-3.5-turbo",
    "text-davinci-003": "gpt-3.5-turbo",
    "text-davinci-002": "gpt-3.5-turbo",
    # Anthropic
    "claude-2": "claude-sonnet-4-20250514",
    "claude-2.0": "claude-sonnet-4-20250514",
    "claude-2.1": "claude-sonnet-4-20250514",
    "claude-instant-1": "claude-haiku-4-5-20251001",
    "claude-instant-1.2": "claude-haiku-4-5-20251001",
    "claude-3-haiku-20240307": "claude-haiku-4-5-20251001",
    "claude-3-5-haiku-20241022": "claude-haiku-4-5-20251001",
    "claude-3-sonnet-20240229": "claude-sonnet-4-20250514",
    "claude-3-opus-20240229": "claude-sonnet-4-20250514",
}

NODE_TYPE_MIGRATION_MAP: Dict[str, str] = {
    "n8n-nodes-base.function": "n8n-nodes-base.code",
    "n8n-nodes-base.functionItem": "n8n-nodes-base.code",
    "n8n-nodes-base.merge": "n8n-nodes-base.merge",
}

MODEL_PARAM_KEYS = {"model", "modelId", "chatModel", "modelName", "engine"}

# Node types that typically require credentials
CREDENTIAL_REQUIRING_TYPES = {
    "n8n-nodes-base.httpRequest",
    "n8n-nodes-base.slack",
    "n8n-nodes-base.gmail",
    "n8n-nodes-base.googleSheets",
    "n8n-nodes-base.openAi",
    "@n8n/n8n-nodes-langchain.lmChatOpenAi",
    "@n8n/n8n-nodes-langchain.lmChatAnthropic",
    "n8n-nodes-base.telegram",
    "n8n-nodes-base.airtable",
    "n8n-nodes-base.notion",
    "n8n-nodes-base.hubspot",
    "n8n-nodes-base.stripe",
}

REPAIR_COOLDOWN_SECONDS: int = 300


class WorkflowHealerAgent(BaseAgent):
    """Diagnoses and repairs broken n8n workflows automatically."""

    agent_id = "workflow_healer_agent"
    agent_name = "Workflow Healer Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        n8n_client: N8NClient,
        n8n_service: Optional[N8NService] = None,
        max_iterations: int = 10,
    ) -> None:
        self._n8n = n8n_client
        self._service = n8n_service or N8NService(n8n_client)
        self._heal_log = HealLogRepo(db)
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Workflow Healer Agent, a specialist in diagnosing, repairing, and maintaining n8n workflows.

You can:
- Diagnose workflows for deprecated models, broken connections, credential issues, and structural problems
- Repair workflows by applying fixes (model upgrades, node migrations, connection cleanup)
- Roll back workflows to previous snapshots if a repair fails
- Check execution health to identify error-prone workflows
- Review healing history for any workflow
- Validate workflow structure with detailed error reporting
- Resolve and verify credentials for workflow nodes
- Search the n8n community forum for solutions to uncommon issues
- Test workflows after repairs to verify fixes work

GUIDELINES:
- Always diagnose before repairing
- Repairs are non-destructive: snapshots are taken before and after
- After repairing, test the workflow if it has a testable trigger
- Credential issues: check if the credential exists in n8n first using resolve_credentials
- Respect cooldown periods between repairs to prevent loops
- Search the community when you encounter an issue you haven't seen before
- Present findings clearly with issue type, severity, and recommended action"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="diagnose_workflow",
            description="Diagnose a single workflow for issues: deprecated models, broken connections, duplicate node names, missing credentials. Returns structured issues list.",
        )
        async def diagnose_workflow(workflow_id: str) -> Dict[str, Any]:
            return await self._diagnose_workflow_internal(workflow_id)

        @self.tool_registry.register(
            name="diagnose_all_workflows",
            description="List all workflows and diagnose each one. Returns summary with counts per workflow.",
        )
        async def diagnose_all_workflows() -> Dict[str, Any]:
            try:
                response = await self._n8n.list_workflows()
            except N8NClientError as e:
                return {"error": f"Failed to list workflows: {e}"}

            results = []
            total_issues = 0
            for wf in response.data:
                diag = await self._diagnose_workflow_internal(str(wf.id))
                issue_count = len(diag.get("issues", []))
                total_issues += issue_count
                results.append(
                    {
                        "workflow_id": wf.id,
                        "workflow_name": wf.name,
                        "issues_count": issue_count,
                        "issues": diag.get("issues", []),
                    }
                )

            return {
                "workflows_checked": len(results),
                "total_issues": total_issues,
                "results": results,
            }

        @self.tool_registry.register(
            name="repair_workflow",
            description="Repair a workflow: snapshot, apply fixes, validate, update via API. Auto-rollback on failure. Respects cooldown.",
        )
        async def repair_workflow(workflow_id: str) -> Dict[str, Any]:
            # Diagnose first
            diagnosis = await self._diagnose_workflow_internal(workflow_id)
            issues = diagnosis.get("issues", [])
            if not issues:
                return {
                    "status": "no_issues",
                    "workflow_id": workflow_id,
                    "message": "No issues found.",
                }

            return await self._repair_workflow_internal(workflow_id, issues)

        @self.tool_registry.register(
            name="validate_workflow",
            description="Structural validation of a workflow: check node types, connections, required fields, duplicates.",
        )
        async def validate_workflow(workflow_id: str) -> Dict[str, Any]:
            try:
                wf = await self._n8n.get_workflow(workflow_id)
            except N8NClientError as e:
                return {"error": f"Failed to fetch workflow: {e}"}

            nodes_data = [n.model_dump(by_alias=True) for n in wf.nodes]
            errors = self._validate_structure(nodes_data, wf.connections)
            return {
                "workflow_id": workflow_id,
                "workflow_name": wf.name,
                "valid": len(errors) == 0,
                "errors": errors,
            }

        @self.tool_registry.register(
            name="rollback_workflow",
            description="Restore a workflow to a previous snapshot from heal_log. Optionally specify a heal_log_id.",
        )
        async def rollback_workflow(
            workflow_id: str, heal_log_id: Optional[int] = None
        ) -> Dict[str, Any]:
            if heal_log_id:
                entry = await self._heal_log.get(heal_log_id)
                if not entry or entry.workflow_id != workflow_id:
                    return {"error": "Heal log entry not found for this workflow."}
            else:
                entries = await self._heal_log.get_latest(workflow_id, action="repair", limit=1)
                if not entries:
                    return {"error": "No repair history found for this workflow."}
                entry = entries[0]

            if not entry.snapshot_before:
                return {"error": "No snapshot_before available for rollback."}

            try:
                await self._n8n.update_workflow(workflow_id, entry.snapshot_before)
                await self._heal_log.create(
                    workflow_id=workflow_id,
                    workflow_name=entry.workflow_name,
                    action="rollback",
                    status="success",
                    snapshot_before=None,
                    snapshot_after=entry.snapshot_before,
                )
                return {
                    "status": "rolled_back",
                    "workflow_id": workflow_id,
                    "restored_from": entry.id,
                }
            except N8NClientError as e:
                await self._heal_log.create(
                    workflow_id=workflow_id,
                    workflow_name=entry.workflow_name,
                    action="rollback",
                    status="failed",
                    error_message=str(e),
                )
                return {"error": f"Rollback failed: {e}"}

        @self.tool_registry.register(
            name="get_heal_history",
            description="Query healing history for a workflow.",
        )
        async def get_heal_history(workflow_id: str, limit: int = 10) -> Dict[str, Any]:
            entries = await self._heal_log.get_latest(workflow_id, limit=limit)
            return {
                "workflow_id": workflow_id,
                "count": len(entries),
                "history": [
                    {
                        "id": e.id,
                        "action": e.action,
                        "status": e.status,
                        "issues_count": len(e.issues_found) if e.issues_found else 0,
                        "fixes_count": len(e.fixes_applied) if e.fixes_applied else 0,
                        "error_message": e.error_message,
                        "created_at": str(e.created_at) if e.created_at else None,
                    }
                    for e in entries
                ],
            }

        @self.tool_registry.register(
            name="check_execution_health",
            description="Analyze recent executions for error rate patterns. Returns health status: healthy/degraded/unhealthy.",
        )
        async def check_execution_health(workflow_id: str, limit: int = 20) -> Dict[str, Any]:
            return await self._service.check_execution_health(workflow_id, limit)

        # ── Enhanced tools via shared N8NService ──────────────────────────

        @self.tool_registry.register(
            name="resolve_credentials",
            description=(
                "Check if required credentials exist in the n8n instance for a list of node types. "
                "Pass node_types like ['n8n-nodes-base.slack', 'n8n-nodes-base.gmail']. "
                "Returns found credentials and warnings for missing ones. "
                "Use this to determine if credential issues are due to missing credentials vs misconfigured ones."
            ),
        )
        async def resolve_credentials(node_types: List[str]) -> Dict[str, Any]:
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
            name="search_community",
            description=(
                "Search the n8n community forum for solutions to workflow issues. "
                "Pass a search query describing the problem. "
                "Use this when you encounter an issue you haven't seen before or "
                "need to find workarounds for known n8n bugs."
            ),
        )
        async def search_community(query: str, limit: int = 5) -> Dict[str, Any]:
            results = await self._service.search_community(query, limit)
            return {"query": query, "results_count": len(results), "results": results}

        @self.tool_registry.register(
            name="test_workflow",
            description=(
                "Test-execute a workflow after repair. Works for workflows with "
                "webhook, form, or manual triggers. Returns execution status."
            ),
        )
        async def test_workflow(
            workflow_id: str, test_data: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            return await self._service.test_workflow(workflow_id, test_data)

        @self.tool_registry.register(
            name="list_all_workflows",
            description="List all workflows in the n8n instance with their active status. Useful for scanning across all workflows.",
        )
        async def list_all_workflows() -> Dict[str, Any]:
            try:
                workflows = await self._service.list_workflows()
                return {"count": len(workflows), "workflows": workflows}
            except N8NClientError as e:
                return {"error": str(e)}

    # ── Internal methods (called directly by scheduler, no LLM cost) ──────

    async def _diagnose_workflow_internal(self, workflow_id: str) -> Dict[str, Any]:
        """Core diagnosis logic — returns structured issues list."""
        try:
            wf = await self._n8n.get_workflow(workflow_id)
        except N8NClientError as e:
            return {"error": f"Failed to fetch workflow {workflow_id}: {e}"}

        issues: List[Dict[str, Any]] = []

        node_names: List[str] = []
        for node in wf.nodes:
            # Check deprecated models
            for key in MODEL_PARAM_KEYS:
                model_val = node.parameters.get(key)
                if isinstance(model_val, str) and model_val in MODEL_DEPRECATION_MAP:
                    issues.append(
                        {
                            "type": "deprecated_model",
                            "severity": "error",
                            "node_name": node.name,
                            "param_key": key,
                            "current_value": model_val,
                            "replacement": MODEL_DEPRECATION_MAP[model_val],
                        }
                    )

            # Check deprecated node types
            if node.type in NODE_TYPE_MIGRATION_MAP:
                replacement = NODE_TYPE_MIGRATION_MAP[node.type]
                if replacement != node.type:
                    issues.append(
                        {
                            "type": "deprecated_node_type",
                            "severity": "warning",
                            "node_name": node.name,
                            "current_type": node.type,
                            "replacement_type": replacement,
                        }
                    )

            # Check credentials
            cred_issues = self._check_credentials(node.name, node.type, node.credentials)
            issues.extend(cred_issues)

            # Track names for duplicate check
            node_names.append(node.name)

        # Duplicate node names
        seen: Dict[str, int] = {}
        for name in node_names:
            seen[name] = seen.get(name, 0) + 1
        for name, count in seen.items():
            if count > 1:
                issues.append(
                    {
                        "type": "duplicate_node_name",
                        "severity": "warning",
                        "node_name": name,
                        "count": count,
                    }
                )

        # Dangling connections
        valid_names = set(node_names)
        for source_name, conn_data in wf.connections.items():
            if source_name not in valid_names:
                issues.append(
                    {
                        "type": "dangling_connection_source",
                        "severity": "error",
                        "source_name": source_name,
                    }
                )
            # Check target nodes in connection outputs
            if isinstance(conn_data, dict):
                for output_key, outputs in conn_data.items():
                    if isinstance(outputs, list):
                        for output_group in outputs:
                            if isinstance(output_group, list):
                                for conn in output_group:
                                    target = conn.get("node")
                                    if target and target not in valid_names:
                                        issues.append(
                                            {
                                                "type": "dangling_connection_target",
                                                "severity": "error",
                                                "source_name": source_name,
                                                "target_name": target,
                                            }
                                        )

        return {
            "workflow_id": workflow_id,
            "workflow_name": wf.name,
            "issues_count": len(issues),
            "issues": issues,
        }

    async def _repair_workflow_internal(
        self, workflow_id: str, issues: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Core repair logic — snapshot, fix, validate, update, log."""
        # Check cooldown
        if await self._check_cooldown(workflow_id):
            return {
                "status": "skipped",
                "reason": "cooldown",
                "workflow_id": workflow_id,
            }

        try:
            wf = await self._n8n.get_workflow(workflow_id)
        except N8NClientError as e:
            return {"error": f"Failed to fetch workflow: {e}"}

        snapshot_before = wf.model_dump(by_alias=True)
        nodes = [n.model_dump(by_alias=True) for n in wf.nodes]
        connections = dict(wf.connections)

        fixes_applied: List[Dict[str, Any]] = []
        for issue in issues:
            fix = self._apply_fix(issue, nodes, connections)
            if fix:
                fixes_applied.append(fix)

        if not fixes_applied:
            await self._heal_log.create(
                workflow_id=workflow_id,
                workflow_name=wf.name,
                action="repair",
                status="no_fixable_issues",
                issues_found=issues,
            )
            return {
                "status": "no_fixable_issues",
                "workflow_id": workflow_id,
                "issues": issues,
            }

        # Validate structure after fixes
        validation_errors = self._validate_structure(nodes, connections)
        if validation_errors:
            await self._heal_log.create(
                workflow_id=workflow_id,
                workflow_name=wf.name,
                action="repair",
                status="validation_failed",
                issues_found=issues,
                fixes_applied=fixes_applied,
                error_message="; ".join(validation_errors),
            )
            return {
                "status": "validation_failed",
                "workflow_id": workflow_id,
                "validation_errors": validation_errors,
            }

        # Build updated workflow payload
        update_payload: Dict[str, Any] = {
            "name": wf.name,
            "nodes": nodes,
            "connections": connections,
            "settings": wf.settings,
        }

        try:
            updated = await self._n8n.update_workflow(workflow_id, update_payload)
            snapshot_after = updated.model_dump(by_alias=True)

            await self._heal_log.create(
                workflow_id=workflow_id,
                workflow_name=wf.name,
                action="repair",
                status="success",
                issues_found=issues,
                fixes_applied=fixes_applied,
                snapshot_before=snapshot_before,
                snapshot_after=snapshot_after,
            )

            return {
                "status": "repaired",
                "workflow_id": workflow_id,
                "fixes_applied": fixes_applied,
                "issues_found": len(issues),
                "fixes_count": len(fixes_applied),
            }

        except N8NClientError as e:
            # Attempt rollback
            logger.error("repair_failed_attempting_rollback", workflow_id=workflow_id, error=str(e))
            try:
                await self._n8n.update_workflow(workflow_id, snapshot_before)
                rollback_status = "rolled_back"
            except N8NClientError:
                rollback_status = "rollback_failed"

            await self._heal_log.create(
                workflow_id=workflow_id,
                workflow_name=wf.name,
                action="repair",
                status=f"failed_{rollback_status}",
                issues_found=issues,
                fixes_applied=fixes_applied,
                snapshot_before=snapshot_before,
                error_message=str(e),
            )

            return {
                "status": "failed",
                "workflow_id": workflow_id,
                "error": str(e),
                "rollback": rollback_status,
            }

    def _apply_fix(
        self,
        issue: Dict[str, Any],
        nodes: List[Dict[str, Any]],
        connections: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Apply a single fix based on issue type. Returns fix dict or None."""
        issue_type = issue.get("type")

        if issue_type == "deprecated_model":
            node_name = issue["node_name"]
            param_key = issue["param_key"]
            replacement = issue["replacement"]
            for node in nodes:
                if node.get("name") == node_name:
                    old_val = node.get("parameters", {}).get(param_key)
                    if old_val == issue["current_value"]:
                        node["parameters"][param_key] = replacement
                        return {
                            "type": "model_replaced",
                            "node_name": node_name,
                            "param_key": param_key,
                            "old_value": old_val,
                            "new_value": replacement,
                        }
            return None

        if issue_type == "deprecated_node_type":
            node_name = issue["node_name"]
            replacement_type = issue["replacement_type"]
            for node in nodes:
                if node.get("name") == node_name:
                    old_type = node["type"]
                    node["type"] = replacement_type
                    return {
                        "type": "node_type_migrated",
                        "node_name": node_name,
                        "old_type": old_type,
                        "new_type": replacement_type,
                    }
            return None

        if issue_type == "dangling_connection_source":
            source_name = issue["source_name"]
            if source_name in connections:
                del connections[source_name]
                return {
                    "type": "dangling_source_removed",
                    "source_name": source_name,
                }
            return None

        if issue_type == "dangling_connection_target":
            source_name = issue["source_name"]
            target_name = issue["target_name"]
            if source_name in connections:
                conn_data = connections[source_name]
                if isinstance(conn_data, dict):
                    for output_key, outputs in conn_data.items():
                        if isinstance(outputs, list):
                            for i, output_group in enumerate(outputs):
                                if isinstance(output_group, list):
                                    outputs[i] = [
                                        c for c in output_group if c.get("node") != target_name
                                    ]
                return {
                    "type": "dangling_target_removed",
                    "source_name": source_name,
                    "target_name": target_name,
                }

        # Credential issues and duplicate names are not auto-fixable
        return None

    def _validate_structure(
        self,
        nodes: List[Dict[str, Any]],
        connections: Dict[str, Any],
    ) -> List[str]:
        """Validate workflow structure, return list of error strings."""
        errors: List[str] = []

        if not nodes:
            errors.append("Workflow has no nodes.")
            return errors

        node_names = set()
        for node in nodes:
            name = node.get("name")
            if not name:
                errors.append("Node missing 'name' field.")
            elif name in node_names:
                errors.append(f"Duplicate node name: '{name}'.")
            else:
                node_names.add(name)

            if not node.get("type"):
                errors.append(f"Node '{name}' missing 'type' field.")

        # Validate connection references
        for source_name in connections:
            if source_name not in node_names:
                errors.append(f"Connection references non-existent source node: '{source_name}'.")

        return errors

    async def _check_cooldown(self, workflow_id: str) -> bool:
        """Return True if workflow was repaired within REPAIR_COOLDOWN_SECONDS."""
        entries = await self._heal_log.get_latest(workflow_id, action="repair", limit=1)
        if not entries:
            return False

        last_repair = entries[0]
        if last_repair.created_at is None:
            return False

        cooldown_threshold = datetime.utcnow() - timedelta(seconds=REPAIR_COOLDOWN_SECONDS)
        return last_repair.created_at > cooldown_threshold

    def _check_credentials(
        self,
        node_name: str,
        node_type: str,
        credentials: Optional[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Check node credentials for missing or empty entries."""
        issues: List[Dict[str, Any]] = []

        if node_type in CREDENTIAL_REQUIRING_TYPES and credentials is None:
            issues.append(
                {
                    "type": "missing_credentials",
                    "severity": "warning",
                    "node_name": node_name,
                    "node_type": node_type,
                    "message": "Node type typically requires credentials but none are set.",
                }
            )
        elif credentials:
            for cred_type, cred_ref in credentials.items():
                if cred_ref is None or cred_ref == "" or cred_ref == {}:
                    issues.append(
                        {
                            "type": "empty_credential_ref",
                            "severity": "error",
                            "node_name": node_name,
                            "credential_type": cred_type,
                            "message": "Credential reference is empty.",
                        }
                    )

        return issues
