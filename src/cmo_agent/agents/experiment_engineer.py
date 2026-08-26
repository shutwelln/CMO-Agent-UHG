"""Data & Experiment Engineer Agent — structured experimentation system."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..experiments.events import EventDefinition, EventSchemaStore
from ..experiments.store import ExperimentSpec, ExperimentStore
from ..llm.base import BaseLLM
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()


class ExperimentEngineerAgent(BaseAgent):
    """Manages experiments, A/B tests, and event schema definitions.

    Tool-agnostic — does not assume GA4 or any specific analytics platform.
    """

    agent_id = "experiment_engineer_agent"
    agent_name = "Data & Experiment Engineer Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        experiments_dir: str = "./data/experiments",
        analytics_dir: str = "./data/analytics",
        max_iterations: int = 10,
    ) -> None:
        self._workspace_mgr = workspace_manager
        self._experiments = ExperimentStore(base_dir=experiments_dir)
        self._events = EventSchemaStore(base_dir=analytics_dir)
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Data & Experiment Engineer Agent.

You persist, track, and maintain structured experiments and event schemas.
You are TOOL-AGNOSTIC — you do not assume GA4, Mixpanel, or any specific platform.

SCOPE NOTE: You handle experiment lifecycle persistence (create, track status
transitions, record readouts) and event schema management. Experiment DESIGN
and PRIORITIZATION are owned by the Conversion Optimization Agent. You receive
structured experiment specs from the Conversion Optimization Agent and persist
them. You do not independently design experiments or set prioritization.

EXPERIMENT LIFECYCLE:
1. **Draft** — hypothesis, metrics, segments defined
2. **Running** — experiment is live, collecting data
3. **Paused** — temporarily stopped (optional)
4. **Completed** — data collected, readout needed
5. **Cancelled** — abandoned before completion

HYPOTHESIS-DRIVEN:
Every experiment MUST have:
- A clear hypothesis ("We believe X will cause Y")
- A primary metric (one number that determines success)
- Guardrail metrics (things that must NOT degrade)
- Defined segments and channels

READOUT STRUCTURE:
When recording results, include:
- What happened (data summary)
- Decision: ship / iterate / kill
- Follow-up experiments or actions

EVENT SCHEMA:
You also maintain a registry of tracked events (analytics events, conversion events, etc.).
Each event has: name, properties, owner, where_fired, notes.
Events can be imported from structured markdown."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="create_experiment",
            description="Create a new experiment with hypothesis, primary metric, guardrail metrics, segments, and channels.",
        )
        async def create_experiment(
            workspace_id: str,
            name: str,
            hypothesis: str,
            primary_metric: str,
            guardrail_metrics: Optional[List[str]] = None,
            segments: Optional[List[str]] = None,
            channels: Optional[List[str]] = None,
            start_date: Optional[str] = None,
            end_date: Optional[str] = None,
        ) -> Dict[str, Any]:
            spec = ExperimentSpec(
                workspace_id=workspace_id,
                name=name,
                hypothesis=hypothesis,
                primary_metric=primary_metric,
                guardrail_metrics=guardrail_metrics or [],
                segments=segments or [],
                channels=channels or [],
                start_date=start_date,
                end_date=end_date,
            )
            created = self._experiments.create(spec)
            return {
                "experiment_id": created.experiment_id,
                "name": created.name,
                "status": created.status,
                "hypothesis": created.hypothesis,
                "primary_metric": created.primary_metric,
            }

        @self.tool_registry.register(
            name="list_experiments",
            description="List experiments, optionally filtered by workspace and/or status (draft, running, paused, completed, cancelled).",
        )
        async def list_experiments(
            workspace_id: Optional[str] = None,
            status: Optional[str] = None,
        ) -> Dict[str, Any]:
            results = self._experiments.list_all(workspace_id=workspace_id, status=status)
            return {
                "count": len(results),
                "experiments": [
                    {
                        "experiment_id": e.experiment_id,
                        "name": e.name,
                        "status": e.status,
                        "hypothesis": e.hypothesis[:100],
                        "primary_metric": e.primary_metric,
                        "created_at": e.created_at,
                    }
                    for e in results
                ],
            }

        @self.tool_registry.register(
            name="update_experiment_status",
            description="Transition an experiment to a new status. Valid transitions: draft->running/cancelled, running->paused/completed/cancelled, paused->running/cancelled.",
        )
        async def update_experiment_status(
            experiment_id: str,
            new_status: str,
        ) -> Dict[str, Any]:
            try:
                spec = self._experiments.update_status(experiment_id, new_status)
                if not spec:
                    return {"error": f"Experiment {experiment_id} not found"}
                return {
                    "experiment_id": spec.experiment_id,
                    "name": spec.name,
                    "status": spec.status,
                    "updated_at": spec.updated_at,
                }
            except ValueError as e:
                return {"error": str(e)}

        @self.tool_registry.register(
            name="record_experiment_readout",
            description="Record the results and decision for an experiment. Decision should be: ship, iterate, or kill.",
        )
        async def record_experiment_readout(
            experiment_id: str,
            results_summary: str,
            decision: str = "",
            followups: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            spec = self._experiments.record_readout(
                experiment_id=experiment_id,
                results_summary=results_summary,
                decision=decision,
                followups=followups,
            )
            if not spec:
                return {"error": f"Experiment {experiment_id} not found"}
            return {
                "experiment_id": spec.experiment_id,
                "name": spec.name,
                "results_summary": spec.results_summary[:200],
                "decision": spec.decision,
                "followups": spec.followups,
            }

        @self.tool_registry.register(
            name="define_event",
            description="Define or update a tracked event in the event schema registry.",
        )
        async def define_event(
            event_name: str,
            workspace_id: str = "default",
            properties: Optional[Dict[str, str]] = None,
            owner: str = "",
            where_fired: str = "",
            notes: str = "",
        ) -> Dict[str, Any]:
            event = EventDefinition(
                event_name=event_name,
                workspace_id=workspace_id,
                properties=properties or {},
                owner=owner,
                where_fired=where_fired,
                notes=notes,
            )
            defined = self._events.define(event)
            return {
                "event_name": defined.event_name,
                "workspace": defined.workspace_id,
                "properties": defined.properties,
                "owner": defined.owner,
            }

        @self.tool_registry.register(
            name="list_events",
            description="List all tracked event definitions, optionally filtered by workspace.",
        )
        async def list_events(
            workspace_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            results = self._events.list_all(workspace_id=workspace_id)
            return {
                "count": len(results),
                "events": [
                    {
                        "event_name": e.event_name,
                        "workspace": e.workspace_id,
                        "properties": list(e.properties.keys()),
                        "owner": e.owner,
                        "where_fired": e.where_fired,
                    }
                    for e in results
                ],
            }

        @self.tool_registry.register(
            name="import_events_from_markdown",
            description="Import event definitions from structured markdown. Each event should be a ## heading with properties, owner, where_fired, and notes as bullet points.",
        )
        async def import_events_from_markdown(
            markdown_text: str,
            workspace_id: str = "default",
        ) -> Dict[str, Any]:
            count = self._events.import_from_markdown(markdown_text, workspace_id=workspace_id)
            return {
                "imported": count,
                "workspace": workspace_id,
            }

        @self.tool_registry.register(
            name="generate_experiment_readout",
            description="Generate a narrative readout for an experiment using the LLM. Requires experiment_id of a completed experiment.",
        )
        async def generate_experiment_readout(
            experiment_id: str,
        ) -> Dict[str, Any]:
            spec = self._experiments.get(experiment_id)
            if not spec:
                return {"error": f"Experiment {experiment_id} not found"}

            from ..llm.base import Message

            prompt = f"""Generate a structured experiment readout for:

Name: {spec.name}
Hypothesis: {spec.hypothesis}
Primary Metric: {spec.primary_metric}
Guardrail Metrics: {", ".join(spec.guardrail_metrics)}
Segments: {", ".join(spec.segments)}
Channels: {", ".join(spec.channels)}
Status: {spec.status}
Results Summary: {spec.results_summary or "Not yet recorded"}
Decision: {spec.decision or "Pending"}

Write a clear, concise readout with:
1. Executive Summary (2-3 sentences)
2. What We Tested
3. Results (what the data shows)
4. Recommendation (ship / iterate / kill, with reasoning)
5. Next Steps"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.5,
            )
            return {
                "experiment_id": spec.experiment_id,
                "name": spec.name,
                "readout": response.content,
            }
