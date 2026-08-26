"""Async HTTP client for n8n API operations."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
import structlog

from .models import (
    Execution,
    ExecutionListResponse,
    Workflow,
    WorkflowListResponse,
)

logger = structlog.get_logger()


class N8NClientError(Exception):
    """Base exception for n8n client errors."""

    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class N8NClient:
    """Async client for n8n API operations.

    Provides methods for managing workflows, executions, and triggering
    workflow runs via the n8n REST API.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout: float = 30.0,
        max_retries: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "N8NClient":
        """Enter async context manager."""
        await self._ensure_client()
        return self

    async def __aexit__(self, *args: Any) -> None:
        """Exit async context manager."""
        await self.close()

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure HTTP client is initialized."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=f"{self.base_url}/api/v1",
                headers={
                    "X-N8N-API-KEY": self.api_key,
                    "Content-Type": "application/json",
                },
                timeout=self.timeout,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Make an HTTP request to the n8n API."""
        client = await self._ensure_client()

        # Debug log: print exact payload being sent
        if json is not None:
            logger.info(
                "n8n_request_payload",
                method=method,
                path=path,
                payload_keys=list(json.keys()),
                payload=json,
            )

        try:
            response = await client.request(
                method=method,
                url=path,
                params=params,
                json=json,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                "n8n_api_error",
                method=method,
                path=path,
                status_code=e.response.status_code,
                detail=e.response.text,
            )
            raise N8NClientError(
                f"n8n API error: {e.response.text}",
                status_code=e.response.status_code,
            ) from e
        except httpx.RequestError as e:
            logger.error("n8n_request_error", method=method, path=path, error=str(e))
            raise N8NClientError(f"Request failed: {e}") from e

    # ==================
    # Workflow Operations
    # ==================

    async def list_workflows(
        self,
        active: Optional[bool] = None,
        tags: Optional[List[str]] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> WorkflowListResponse:
        """List all workflows."""
        params: Dict[str, Any] = {"limit": limit}
        if active is not None:
            params["active"] = str(active).lower()
        if tags:
            params["tags"] = ",".join(tags)
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "/workflows", params=params)
        return WorkflowListResponse(**data)

    async def get_workflow(self, workflow_id: str) -> Workflow:
        """Get a specific workflow by ID."""
        data = await self._request("GET", f"/workflows/{workflow_id}")
        return Workflow(**data)

    async def create_workflow(self, workflow: Dict[str, Any]) -> Workflow:
        """Create a new workflow."""
        data = await self._request("POST", "/workflows", json=workflow)
        return Workflow(**data)

    async def update_workflow(self, workflow_id: str, workflow: Dict[str, Any]) -> Workflow:
        """Update an existing workflow."""
        data = await self._request("PUT", f"/workflows/{workflow_id}", json=workflow)
        return Workflow(**data)

    async def delete_workflow(self, workflow_id: str) -> None:
        """Delete a workflow."""
        await self._request("DELETE", f"/workflows/{workflow_id}")

    async def activate_workflow(self, workflow_id: str) -> Workflow:
        """Activate a workflow."""
        data = await self._request("POST", f"/workflows/{workflow_id}/activate")
        return Workflow(**data)

    async def deactivate_workflow(self, workflow_id: str) -> Workflow:
        """Deactivate a workflow."""
        data = await self._request("POST", f"/workflows/{workflow_id}/deactivate")
        return Workflow(**data)

    # =====================
    # Execution Operations
    # =====================

    async def execute_workflow(
        self,
        workflow_id: str,
        data: Optional[Dict[str, Any]] = None,
    ) -> Execution:
        """Execute a workflow manually."""
        result = await self._request(
            "POST",
            f"/workflows/{workflow_id}/run",
            json=data or {},
        )
        return Execution(**result)

    async def get_execution(self, execution_id: str) -> Execution:
        """Get a specific execution by ID."""
        data = await self._request("GET", f"/executions/{execution_id}")
        return Execution(**data)

    async def list_executions(
        self,
        workflow_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
        cursor: Optional[str] = None,
    ) -> ExecutionListResponse:
        """List workflow executions."""
        params: Dict[str, Any] = {"limit": limit}
        if workflow_id:
            params["workflowId"] = workflow_id
        if status:
            params["status"] = status
        if cursor:
            params["cursor"] = cursor

        data = await self._request("GET", "/executions", params=params)
        return ExecutionListResponse(**data)

    async def delete_execution(self, execution_id: str) -> None:
        """Delete an execution."""
        await self._request("DELETE", f"/executions/{execution_id}")

    # =================
    # Utility Methods
    # =================

    async def health_check(self) -> bool:
        """Check if the n8n API is reachable."""
        try:
            await self.list_workflows(limit=1)
            return True
        except N8NClientError:
            return False

    async def get_workflow_by_name(self, name: str) -> Optional[Workflow]:
        """Find a workflow by its name."""
        response = await self.list_workflows()
        for workflow in response.data:
            if workflow.name == name:
                return workflow
        return None
