"""Pydantic models for database entities."""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class OpportunityStatus(str, Enum):
    NEW = "new"
    REVIEWED = "reviewed"
    USED = "used"
    DISMISSED = "dismissed"


class OutreachStatus(str, Enum):
    NEW = "new"
    CLAIMED = "claimed"
    RESPONDED = "responded"
    SKIPPED = "skipped"


class OutreachOutcome(str, Enum):
    CONNECTED = "connected"
    NO_RESPONSE = "no_response"
    DECLINED = "declined"
    ALREADY_CONNECTED = "already_connected"
    REFERRED_ELSEWHERE = "referred_elsewhere"


class DraftStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISED = "revised"


class Workspace(BaseModel):
    """A brand workspace."""

    id: str
    name: str
    type: str = "owned_brand"
    slack_channel: Optional[str] = None
    brand_voice_path: Optional[str] = None
    is_default: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class Opportunity(BaseModel):
    """A discovered content opportunity."""

    id: str
    workspace_id: str
    source: str
    source_url: Optional[str] = None
    source_id: Optional[str] = None
    title: str
    content: Optional[str] = None
    score: int = 0
    score_breakdown: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    status: OpportunityStatus = OpportunityStatus.NEW
    subreddit: Optional[str] = None
    expires_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # Outreach workflow fields
    claimed_by: Optional[str] = None
    claimed_at: Optional[datetime] = None
    response_url: Optional[str] = None
    response_notes: Optional[str] = None
    draft_reply: Optional[str] = None
    platform_post_type: Optional[str] = None
    outreach_status: Optional[str] = None
    outreach_outcome: Optional[str] = None
    content_hash: Optional[str] = None
    canned_response_used: Optional[str] = None
    engagement_risk: Optional[str] = None
    posted_at: Optional[datetime] = None
    poster_gender: Optional[str] = None

    model_config = {"from_attributes": True}

    @field_validator("score_breakdown", mode="before")
    @classmethod
    def parse_score_breakdown(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            return json.loads(v)
        return v


class Draft(BaseModel):
    """A content draft."""

    id: str
    workspace_id: str
    content_type: str
    title: Optional[str] = None
    body: str
    verify_flags: List[str] = Field(default_factory=list)
    status: DraftStatus = DraftStatus.PENDING
    rejection_reason: Optional[str] = None
    opportunity_ids: List[str] = Field(default_factory=list)
    slack_thread_ts: Optional[str] = None
    slack_message_ts: Optional[str] = None
    created_at: Optional[datetime] = None
    approved_at: Optional[datetime] = None
    revised_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("verify_flags", mode="before")
    @classmethod
    def parse_verify_flags(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return json.loads(v)
        if v is None:
            return []
        return v

    @field_validator("opportunity_ids", mode="before")
    @classmethod
    def parse_opportunity_ids(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return json.loads(v)
        if v is None:
            return []
        return v


class Source(BaseModel):
    """A monitoring source."""

    id: str
    workspace_id: str
    type: str
    url: Optional[str] = None
    name: Optional[str] = None
    keywords: List[str] = Field(default_factory=list)
    active: bool = True
    last_checked_at: Optional[datetime] = None
    last_item_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("keywords", mode="before")
    @classmethod
    def parse_keywords(cls, v: Any) -> List[str]:
        if isinstance(v, str):
            return json.loads(v)
        if v is None:
            return []
        return v

    @field_validator("active", mode="before")
    @classmethod
    def parse_active(cls, v: Any) -> bool:
        if isinstance(v, int):
            return v == 1
        return bool(v)


class ConfigEntry(BaseModel):
    """A configuration entry."""

    workspace_id: str
    key: str
    value: str
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class MediaAsset(BaseModel):
    """A media asset stored in Supabase/locally."""

    id: str
    workspace_id: str
    media_type: str
    filename: str
    storage_path: str
    cdn_url: Optional[str] = None
    local_path: Optional[str] = None
    source_agent: str
    prompt: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    file_size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    draft_id: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("metadata", mode="before")
    @classmethod
    def parse_metadata(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            return json.loads(v)
        return v


class ScanLogEntry(BaseModel):
    """A scan log entry."""

    id: Optional[int] = None
    agent_id: str
    workspace_id: str
    source_type: str
    items_scanned: int = 0
    items_found: int = 0
    errors: Optional[List[str]] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("errors", mode="before")
    @classmethod
    def parse_errors(cls, v: Any) -> Optional[List[str]]:
        if isinstance(v, str):
            return json.loads(v)
        return v


class HealLogEntry(BaseModel):
    """A workflow healing log entry."""

    id: Optional[int] = None
    workflow_id: str
    workflow_name: Optional[str] = None
    action: str
    status: str
    issues_found: Optional[List[Dict[str, Any]]] = None
    fixes_applied: Optional[List[Dict[str, Any]]] = None
    snapshot_before: Optional[Dict[str, Any]] = None
    snapshot_after: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("issues_found", mode="before")
    @classmethod
    def parse_issues_found(cls, v: Any) -> Optional[List[Dict[str, Any]]]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("fixes_applied", mode="before")
    @classmethod
    def parse_fixes_applied(cls, v: Any) -> Optional[List[Dict[str, Any]]]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("snapshot_before", "snapshot_after", mode="before")
    @classmethod
    def parse_snapshot(cls, v: Any) -> Optional[Dict[str, Any]]:
        if isinstance(v, str):
            return json.loads(v)
        return v


class BuildLogEntry(BaseModel):
    """A workflow build log entry."""

    id: Optional[int] = None
    workflow_id: Optional[str] = None
    workflow_name: str
    request: str
    status: str
    node_count: int = 0
    nodes_summary: Optional[List[Dict[str, Any]]] = None
    connections_summary: Optional[List[str]] = None
    credential_warnings: Optional[List[str]] = None
    workflow_url: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[datetime] = None

    model_config = {"from_attributes": True}

    @field_validator("nodes_summary", mode="before")
    @classmethod
    def parse_nodes_summary(cls, v: Any) -> Optional[List[Dict[str, Any]]]:
        if isinstance(v, str):
            return json.loads(v)
        return v

    @field_validator("connections_summary", "credential_warnings", mode="before")
    @classmethod
    def parse_string_lists(cls, v: Any) -> Optional[List[str]]:
        if isinstance(v, str):
            return json.loads(v)
        return v
