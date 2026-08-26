"""JSONL-based workspace-scoped memory backend."""

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

from .sanitizer import MemorySanitizer

logger = structlog.get_logger()


class MemoryItem(BaseModel):
    """A single memory entry."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    workspace: str = "default"
    source_type: str = "manual"  # manual, slack, agent, system
    source_ref: str = ""  # e.g. conversation_id, agent_id
    tags: List[str] = Field(default_factory=list)
    summary: str = ""
    detail: str = ""
    confidence: float = 0.8  # 0.0–1.0
    expires_at: Optional[str] = None  # ISO datetime or None for permanent


class MemoryBackend:
    """Workspace-scoped JSONL memory store with keyword search.

    Storage layout: ``{base_dir}/{workspace}.jsonl`` — one JSON object per line.
    """

    def __init__(self, base_dir: str = "./data/memory") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)

    # ── Public API ────────────────────────────────────────────────────

    def store(self, item: MemoryItem) -> MemoryItem:
        """Append a memory item (sanitized) to the workspace JSONL file."""
        item.summary = MemorySanitizer.sanitize(item.summary)
        item.detail = MemorySanitizer.sanitize(item.detail)
        path = self._ws_path(item.workspace)
        line = item.model_dump_json() + "\n"
        with open(path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                f.write(line)
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        logger.debug("memory_stored", id=item.id, workspace=item.workspace)
        return item

    def search(
        self,
        query: str,
        workspace: str = "default",
        limit: int = 5,
    ) -> List[MemoryItem]:
        """Keyword search across summary + tags + detail. Returns top matches."""
        items = self._load_workspace(workspace)
        items = self._filter_expired(items)
        keywords = query.lower().split()
        if not keywords:
            return items[:limit]

        scored: List[tuple[float, MemoryItem]] = []
        for item in items:
            blob = f"{item.summary} {' '.join(item.tags)} {item.detail}".lower()
            score = sum(1 for kw in keywords if kw in blob)
            if score > 0:
                scored.append((score, item))

        scored.sort(key=lambda t: t[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def get_recent(
        self,
        workspace: str = "default",
        limit: int = 10,
        source_ref: Optional[str] = None,
    ) -> List[MemoryItem]:
        """Return the most recent memory items, optionally filtered by source_ref."""
        items = self._load_workspace(workspace)
        items = self._filter_expired(items)
        if source_ref:
            items = [i for i in items if i.source_ref == source_ref]
        return items[-limit:]

    def get_canonical(
        self,
        workspace: str = "default",
        min_confidence: float = 0.8,
    ) -> List[MemoryItem]:
        """Return high-confidence items (canonical facts / decisions)."""
        items = self._load_workspace(workspace)
        items = self._filter_expired(items)
        return [i for i in items if i.confidence >= min_confidence]

    def expire(self, item_id: str, workspace: str = "default") -> bool:
        """Mark a memory item as expired by setting expires_at to now."""
        items = self._load_workspace(workspace)
        found = False
        for item in items:
            if item.id == item_id:
                item.expires_at = datetime.now(timezone.utc).isoformat()
                found = True
                break
        if found:
            self._save_workspace(workspace, items)
        return found

    def stats(self, workspace: Optional[str] = None) -> Dict[str, Any]:
        """Return item counts and disk usage, optionally per workspace."""
        if workspace:
            items = self._load_workspace(workspace)
            active = self._filter_expired(items)
            path = self._ws_path(workspace)
            size = path.stat().st_size if path.exists() else 0
            return {
                "workspace": workspace,
                "total_items": len(items),
                "active_items": len(active),
                "expired_items": len(items) - len(active),
                "disk_bytes": size,
            }

        # All workspaces
        result: Dict[str, Any] = {"workspaces": {}, "total_items": 0, "total_bytes": 0}
        for path in sorted(self._base.glob("*.jsonl")):
            ws = path.stem
            items = self._load_workspace(ws)
            active = self._filter_expired(items)
            size = path.stat().st_size
            result["workspaces"][ws] = {
                "total_items": len(items),
                "active_items": len(active),
                "disk_bytes": size,
            }
            result["total_items"] += len(items)
            result["total_bytes"] += size
        return result

    # ── Internal helpers ──────────────────────────────────────────────

    def _ws_path(self, workspace: str) -> Path:
        """Sanitize workspace name and return its JSONL path."""
        safe = "".join(c for c in workspace if c.isalnum() or c in ("_", "-"))
        return self._base / f"{safe or 'default'}.jsonl"

    def _load_workspace(self, workspace: str) -> List[MemoryItem]:
        """Load all items from a workspace JSONL file."""
        path = self._ws_path(workspace)
        if not path.exists():
            return []
        items: List[MemoryItem] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(MemoryItem.model_validate_json(line))
                except Exception:
                    logger.warning("memory_parse_error", line=line[:80])
        return items

    def _save_workspace(self, workspace: str, items: List[MemoryItem]) -> None:
        """Rewrite the entire workspace JSONL (used after mutations like expire)."""
        path = self._ws_path(workspace)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                for item in items:
                    f.write(item.model_dump_json() + "\n")
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
        os.replace(str(tmp), str(path))

    @staticmethod
    def _filter_expired(items: List[MemoryItem]) -> List[MemoryItem]:
        """Remove items whose expires_at is in the past."""
        now = datetime.now(timezone.utc).isoformat()
        return [i for i in items if i.expires_at is None or i.expires_at > now]
