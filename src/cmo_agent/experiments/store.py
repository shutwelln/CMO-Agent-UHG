"""Append-only experiment registry with JSONL log and JSON snapshot."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()

_VALID_STATUSES = {"draft", "running", "paused", "completed", "cancelled"}
_VALID_TRANSITIONS: Dict[str, List[str]] = {
    "draft": ["running", "cancelled"],
    "running": ["paused", "completed", "cancelled"],
    "paused": ["running", "cancelled"],
    "completed": [],
    "cancelled": [],
}


class ExperimentSpec(BaseModel):
    """A single experiment definition."""

    experiment_id: str = Field(default_factory=lambda: str(uuid4()))
    workspace_id: str = "default"
    name: str = ""
    hypothesis: str = ""
    primary_metric: str = ""
    guardrail_metrics: List[str] = Field(default_factory=list)
    segments: List[str] = Field(default_factory=list)
    channels: List[str] = Field(default_factory=list)
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: str = "draft"
    results_summary: str = ""
    decision: str = ""  # ship, iterate, kill
    followups: List[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class ExperimentStore:
    """JSONL append log + JSON snapshot for experiment tracking.

    Reads from ``current.json`` (fast dict lookup).
    Writes append to both ``registry.jsonl`` and ``current.json``.
    """

    def __init__(self, base_dir: str = "./data/experiments") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._jsonl_path = self._base / "registry.jsonl"
        self._snapshot_path = self._base / "current.json"

    # ── Public API ────────────────────────────────────────────────────

    def create(self, spec: ExperimentSpec) -> ExperimentSpec:
        """Create a new experiment."""
        experiments = self._load_snapshot()
        experiments[spec.experiment_id] = spec
        self._append_jsonl(spec)
        self._save_snapshot(experiments)
        logger.debug("experiment_created", id=spec.experiment_id, name=spec.name)
        return spec

    def get(self, experiment_id: str) -> Optional[ExperimentSpec]:
        """Get an experiment by ID."""
        experiments = self._load_snapshot()
        return experiments.get(experiment_id)

    def list_all(
        self,
        workspace_id: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[ExperimentSpec]:
        """List experiments, optionally filtered by workspace and/or status."""
        experiments = self._load_snapshot()
        results = list(experiments.values())
        if workspace_id:
            results = [e for e in results if e.workspace_id == workspace_id]
        if status:
            results = [e for e in results if e.status == status]
        results.sort(key=lambda e: e.created_at, reverse=True)
        return results

    def update_status(self, experiment_id: str, new_status: str) -> Optional[ExperimentSpec]:
        """Transition an experiment to a new status (validates transitions)."""
        if new_status not in _VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}. Must be one of {_VALID_STATUSES}")

        experiments = self._load_snapshot()
        spec = experiments.get(experiment_id)
        if not spec:
            return None

        allowed = _VALID_TRANSITIONS.get(spec.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{spec.status}' to '{new_status}'. Allowed: {allowed}"
            )

        spec.status = new_status
        spec.updated_at = datetime.now(timezone.utc).isoformat()
        self._append_jsonl(spec)
        self._save_snapshot(experiments)
        return spec

    def record_readout(
        self,
        experiment_id: str,
        results_summary: str,
        decision: str = "",
        followups: Optional[List[str]] = None,
    ) -> Optional[ExperimentSpec]:
        """Record experiment results and decision."""
        experiments = self._load_snapshot()
        spec = experiments.get(experiment_id)
        if not spec:
            return None

        spec.results_summary = results_summary
        if decision:
            spec.decision = decision
        if followups:
            spec.followups = followups
        spec.updated_at = datetime.now(timezone.utc).isoformat()
        self._append_jsonl(spec)
        self._save_snapshot(experiments)
        return spec

    # ── Internal helpers ──────────────────────────────────────────────

    def _load_snapshot(self) -> Dict[str, ExperimentSpec]:
        """Load the current snapshot, rebuilding from JSONL if missing."""
        if self._snapshot_path.exists():
            try:
                data = json.loads(self._snapshot_path.read_text(encoding="utf-8"))
                return {k: ExperimentSpec.model_validate(v) for k, v in data.items()}
            except Exception:
                logger.warning("experiment_snapshot_corrupt_rebuilding")

        # Rebuild from JSONL
        return self._rebuild_from_jsonl()

    def _rebuild_from_jsonl(self) -> Dict[str, ExperimentSpec]:
        """Rebuild snapshot from the append-only JSONL log."""
        experiments: Dict[str, ExperimentSpec] = {}
        if not self._jsonl_path.exists():
            return experiments
        with open(self._jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    spec = ExperimentSpec.model_validate_json(line)
                    experiments[spec.experiment_id] = spec
                except Exception:
                    logger.warning("experiment_jsonl_parse_error", line=line[:80])
        self._save_snapshot(experiments)
        return experiments

    def _append_jsonl(self, spec: ExperimentSpec) -> None:
        """Append a single experiment record to the JSONL log."""
        with open(self._jsonl_path, "a", encoding="utf-8") as f:
            f.write(spec.model_dump_json() + "\n")

    def _save_snapshot(self, experiments: Dict[str, ExperimentSpec]) -> None:
        """Atomically write the current snapshot."""
        data = {k: v.model_dump(mode="json") for k, v in experiments.items()}
        tmp = self._snapshot_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(self._snapshot_path))
