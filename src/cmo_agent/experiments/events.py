"""Event schema store for tracking plan definitions."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field

logger = structlog.get_logger()


class EventDefinition(BaseModel):
    """A tracked event definition."""

    event_name: str
    workspace_id: str = "default"
    properties: Dict[str, str] = Field(default_factory=dict)  # property_name -> type/description
    owner: str = ""  # team or person responsible
    where_fired: str = ""  # e.g. "checkout page", "mobile app"
    notes: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class EventSchemaStore:
    """JSON-based event schema registry."""

    def __init__(self, base_dir: str = "./data/analytics") -> None:
        self._base = Path(base_dir)
        self._base.mkdir(parents=True, exist_ok=True)
        self._path = self._base / "events.json"

    # ── Public API ────────────────────────────────────────────────────

    def define(self, event: EventDefinition) -> EventDefinition:
        """Add or update an event definition."""
        events = self._load()
        key = f"{event.workspace_id}:{event.event_name}"
        events[key] = event
        self._save(events)
        logger.debug("event_defined", name=event.event_name, workspace=event.workspace_id)
        return event

    def get(self, event_name: str, workspace_id: str = "default") -> Optional[EventDefinition]:
        """Get an event by name and workspace."""
        events = self._load()
        return events.get(f"{workspace_id}:{event_name}")

    def list_all(self, workspace_id: Optional[str] = None) -> List[EventDefinition]:
        """List all events, optionally filtered by workspace."""
        events = self._load()
        results = list(events.values())
        if workspace_id:
            results = [e for e in results if e.workspace_id == workspace_id]
        results.sort(key=lambda e: e.event_name)
        return results

    def search(self, query: str, workspace_id: Optional[str] = None) -> List[EventDefinition]:
        """Search events by keyword across name, properties, notes."""
        events = self.list_all(workspace_id)
        keywords = query.lower().split()
        if not keywords:
            return events

        results: List[EventDefinition] = []
        for event in events:
            blob = (
                f"{event.event_name} {' '.join(event.properties.keys())} "
                f"{event.where_fired} {event.notes} {event.owner}"
            ).lower()
            if any(kw in blob for kw in keywords):
                results.append(event)
        return results

    def import_from_markdown(self, markdown_text: str, workspace_id: str = "default") -> int:
        """Parse structured markdown event definitions and import them.

        Expected format per event::

            ## event_name
            - **properties**: prop1 (type), prop2 (type)
            - **owner**: Team Name
            - **where_fired**: Page or location
            - **notes**: Any notes

        Returns the number of events imported.
        """
        # Split by ## headings
        pattern = r"^##\s+(\S+)\s*$"
        sections = re.split(pattern, markdown_text, flags=re.MULTILINE)

        # sections[0] is text before first heading, then alternating name/body
        imported = 0
        i = 1
        while i < len(sections) - 1:
            event_name = sections[i].strip()
            body = sections[i + 1]
            i += 2

            if not event_name:
                continue

            properties: Dict[str, str] = {}
            owner = ""
            where_fired = ""
            notes = ""

            for line in body.strip().split("\n"):
                line = line.strip().lstrip("- ")
                lower_line = line.lower()

                if lower_line.startswith("**properties**:") or lower_line.startswith("properties:"):
                    prop_text = line.split(":", 1)[1].strip()
                    # Parse "prop1 (type), prop2 (type)"
                    for prop in prop_text.split(","):
                        prop = prop.strip()
                        m = re.match(r"(\w+)\s*\(([^)]+)\)", prop)
                        if m:
                            properties[m.group(1)] = m.group(2).strip()
                        elif prop:
                            properties[prop] = "string"
                elif lower_line.startswith("**owner**:") or lower_line.startswith("owner:"):
                    owner = line.split(":", 1)[1].strip()
                elif lower_line.startswith("**where_fired**:") or lower_line.startswith(
                    "where_fired:"
                ):
                    where_fired = line.split(":", 1)[1].strip()
                elif lower_line.startswith("**notes**:") or lower_line.startswith("notes:"):
                    notes = line.split(":", 1)[1].strip()

            event = EventDefinition(
                event_name=event_name,
                workspace_id=workspace_id,
                properties=properties,
                owner=owner,
                where_fired=where_fired,
                notes=notes,
            )
            self.define(event)
            imported += 1

        return imported

    # ── Internal helpers ──────────────────────────────────────────────

    def _load(self) -> Dict[str, EventDefinition]:
        """Load event definitions from JSON."""
        if not self._path.exists():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return {k: EventDefinition.model_validate(v) for k, v in data.items()}
        except Exception:
            logger.warning("events_json_parse_error")
            return {}

    def _save(self, events: Dict[str, EventDefinition]) -> None:
        """Atomically save event definitions to JSON."""
        data = {k: v.model_dump(mode="json") for k, v in events.items()}
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(self._path))
