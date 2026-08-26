"""Pydantic models for n8n API entities."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    """Workflow activation status."""

    ACTIVE = "active"
    INACTIVE = "inactive"


class ExecutionStatus(str, Enum):
    """Workflow execution status."""

    NEW = "new"
    RUNNING = "running"
    SUCCESS = "success"
    ERROR = "error"
    CANCELED = "canceled"
    WAITING = "waiting"


class WorkflowNode(BaseModel):
    """A node in an n8n workflow."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    id: Optional[str] = None
    name: str
    type: str
    type_version: float = Field(default=1.0, alias="typeVersion")
    position: List[int] = Field(default_factory=lambda: [0, 0])
    parameters: Dict[str, Any] = Field(default_factory=dict)
    credentials: Optional[Dict[str, Any]] = None


class Workflow(BaseModel):
    """n8n workflow definition."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    id: Optional[str] = None
    name: str
    active: bool = False
    nodes: List[WorkflowNode] = Field(default_factory=list)
    # Use Any for connections since n8n can have complex/nullable structures
    connections: Dict[str, Any] = Field(default_factory=dict)
    settings: Dict[str, Any] = Field(default_factory=dict)
    static_data: Optional[Dict[str, Any]] = Field(default=None, alias="staticData")
    tags: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: Optional[datetime] = Field(default=None, alias="createdAt")
    updated_at: Optional[datetime] = Field(default=None, alias="updatedAt")


class ExecutionData(BaseModel):
    """Data from a workflow execution."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    result_data: Optional[Dict[str, Any]] = Field(default=None, alias="resultData")
    execution_data: Optional[Dict[str, Any]] = Field(default=None, alias="executionData")


class Execution(BaseModel):
    """n8n workflow execution record."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    id: str
    workflow_id: str = Field(alias="workflowId")
    finished: bool = False
    mode: str = "manual"
    status: ExecutionStatus = ExecutionStatus.NEW
    started_at: datetime = Field(alias="startedAt")
    stopped_at: Optional[datetime] = Field(default=None, alias="stoppedAt")
    data: Optional[ExecutionData] = None


class WorkflowListResponse(BaseModel):
    """Response from listing workflows."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    data: List[Workflow]
    next_cursor: Optional[str] = Field(default=None, alias="nextCursor")


class ExecutionListResponse(BaseModel):
    """Response from listing executions."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    data: List[Execution]
    next_cursor: Optional[str] = Field(default=None, alias="nextCursor")


class WebhookTriggerResponse(BaseModel):
    """Response from triggering a workflow via webhook."""

    model_config = {"extra": "ignore", "populate_by_name": True}

    execution_id: Optional[str] = Field(default=None, alias="executionId")
    data: Optional[Dict[str, Any]] = None
