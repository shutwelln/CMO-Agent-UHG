"""JSON-based editorial calendar, backlog, and content bundle storage."""

from __future__ import annotations

import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

# ── Status machines ──────────────────────────────────────────────────

_BACKLOG_STATUSES = {"open", "planned", "done", "dismissed"}

_BUNDLE_STATUSES = {"draft", "review", "approved", "scheduled", "published"}
_BUNDLE_TRANSITIONS: Dict[str, List[str]] = {
    "draft": ["review", "approved"],
    "review": ["draft", "approved"],
    "approved": ["scheduled", "published", "draft"],
    "scheduled": ["published", "approved"],
    "published": [],
}


# ── Models ───────────────────────────────────────────────────────────


class BacklogItem(BaseModel):
    """A content idea in the editorial backlog."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str = "default"
    idea: str = ""
    priority: str = "medium"  # low, medium, high, urgent
    channel: str = ""  # blog, email, social, etc.
    status: str = "open"  # open, planned, done, dismissed
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ContentBundle(BaseModel):
    """A coordinated content package with multiple assets."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str = "default"
    title: str = ""
    target_audience: str = ""
    channels: List[str] = Field(default_factory=list)
    primary_cta: str = ""
    key_messages: List[str] = Field(default_factory=list)
    seo_keywords: List[str] = Field(default_factory=list)
    assets_requested: List[Dict[str, str]] = Field(default_factory=list)
    publish_checklist: List[str] = Field(default_factory=list)
    copy_variants: Dict[str, str] = Field(default_factory=dict)  # short/medium/long
    utms: Dict[str, str] = Field(default_factory=dict)
    status: str = "draft"  # draft, review, approved, scheduled, published
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EditorialCalendar(BaseModel):
    """A weekly editorial calendar."""

    workspace_id: str = "default"
    week_start: str = ""  # YYYY-MM-DD
    slots: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Store ────────────────────────────────────────────────────────────


class EditorialStore:
    """JSON file storage for editorial calendar, backlog, and bundles."""

    def __init__(self, base_dir: str = "./data/editorial") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._backlog_path = self._base / "backlog.json"
        self._bundles_path = self._base / "bundles.json"
        self._calendar_path = self._base / "calendar.json"

    # ── Backlog ───────────────────────────────────────────────────────

    def add_backlog_item(self, item: BacklogItem) -> BacklogItem:
        """Add a new item to the backlog."""
        items = self._load_backlog()
        items[item.id] = item
        self._save_json(
            self._backlog_path, {k: v.model_dump(mode="json") for k, v in items.items()}
        )
        return item

    def list_backlog(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[BacklogItem]:
        """List backlog items, optionally filtered."""
        items = self._load_backlog()
        results = list(items.values())
        if workspace_id:
            results = [i for i in results if i.workspace_id == workspace_id]
        if status:
            results = [i for i in results if i.status == status]
        results.sort(key=lambda i: i.created_at, reverse=True)
        return results

    def update_backlog_status(self, item_id: str, new_status: str) -> Optional[BacklogItem]:
        """Update a backlog item's status."""
        if new_status not in _BACKLOG_STATUSES:
            raise ValueError(f"Invalid backlog status: {new_status}")
        items = self._load_backlog()
        item = items.get(item_id)
        if not item:
            return None
        item.status = new_status
        item.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_json(
            self._backlog_path, {k: v.model_dump(mode="json") for k, v in items.items()}
        )
        return item

    # ── Content Bundles ───────────────────────────────────────────────

    def create_bundle(self, bundle: ContentBundle) -> ContentBundle:
        """Create a new content bundle."""
        bundles = self._load_bundles()
        bundles[bundle.id] = bundle
        self._save_json(
            self._bundles_path, {k: v.model_dump(mode="json") for k, v in bundles.items()}
        )
        return bundle

    def get_bundle(self, bundle_id: str) -> Optional[ContentBundle]:
        """Get a bundle by ID."""
        bundles = self._load_bundles()
        return bundles.get(bundle_id)

    def list_bundles(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[ContentBundle]:
        """List bundles, optionally filtered."""
        bundles = self._load_bundles()
        results = list(bundles.values())
        if workspace_id:
            results = [b for b in results if b.workspace_id == workspace_id]
        if status:
            results = [b for b in results if b.status == status]
        results.sort(key=lambda b: b.created_at, reverse=True)
        return results

    def update_bundle_status(self, bundle_id: str, new_status: str) -> Optional[ContentBundle]:
        """Transition a bundle to a new status (validates state machine)."""
        if new_status not in _BUNDLE_STATUSES:
            raise ValueError(f"Invalid bundle status: {new_status}")
        bundles = self._load_bundles()
        bundle = bundles.get(bundle_id)
        if not bundle:
            return None

        allowed = _BUNDLE_TRANSITIONS.get(bundle.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{bundle.status}' to '{new_status}'. Allowed: {allowed}"
            )

        bundle.status = new_status
        bundle.updated_at = datetime.now(timezone.utc).isoformat()
        self._save_json(
            self._bundles_path, {k: v.model_dump(mode="json") for k, v in bundles.items()}
        )
        return bundle

    # ── Calendar ──────────────────────────────────────────────────────

    def save_calendar(self, calendar: EditorialCalendar) -> EditorialCalendar:
        """Save an editorial calendar (keyed by workspace + week_start)."""
        calendars = self._load_calendars()
        key = f"{calendar.workspace_id}:{calendar.week_start}"
        calendars[key] = calendar
        self._save_json(
            self._calendar_path, {k: v.model_dump(mode="json") for k, v in calendars.items()}
        )
        return calendar

    def get_calendar(self, workspace_id: str, week_start: str) -> Optional[EditorialCalendar]:
        """Get a calendar by workspace and week start."""
        calendars = self._load_calendars()
        return calendars.get(f"{workspace_id}:{week_start}")

    # ── Internal helpers ──────────────────────────────────────────────

    def _load_backlog(self) -> Dict[str, BacklogItem]:
        return self._load_typed(self._backlog_path, BacklogItem)

    def _load_bundles(self) -> Dict[str, ContentBundle]:
        return self._load_typed(self._bundles_path, ContentBundle)

    def _load_calendars(self) -> Dict[str, EditorialCalendar]:
        return self._load_typed(self._calendar_path, EditorialCalendar)

    @staticmethod
    def _load_typed(path: Path, model_cls: type) -> Dict[str, Any]:
        """Load a JSON file and validate each value against the model."""
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {k: model_cls.model_validate(v) for k, v in data.items()}
        except Exception:
            logger.warning("editorial_json_parse_error", path=str(path))
            return {}

    @staticmethod
    def _save_json(path: Path, data: Dict[str, Any]) -> None:
        """Atomically save JSON data with file locking."""
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                json.dump(data, f, indent=2)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(str(tmp), str(path))
