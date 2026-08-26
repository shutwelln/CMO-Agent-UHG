"""Growth Ideas Agent - generates daily growth ideas from recent project activity."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import (
    ApprovedIdeaRepo,
    DraftRepo,
    MediaAssetRepo,
    OpportunityRepo,
    ScanLogRepo,
    SkippedIdeaRepo,
    WorkspaceRepo,
)
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

_ACTIVITY_WINDOW_DAYS = 14

_GROWTH_IDEAS_CRITERIA = [
    QualityCriterion(
        name="actionability",
        description="Each idea includes specific, concrete next steps that could be executed this week",
    ),
    QualityCriterion(
        name="impact_justification",
        description="Impact and effort scores are justified with reasoning, not arbitrary",
    ),
    QualityCriterion(
        name="cross_workspace_insight",
        description="Ideas draw connections across workspaces and recent project activity",
    ),
    QualityCriterion(
        name="novelty",
        description="Ideas are fresh and differentiated from previously generated ideas",
    ),
    QualityCriterion(
        name="execution_clarity",
        description="The recommended pick's execution outline has clear, sequenced steps",
    ),
]


class GrowthIdeasAgent(BaseAgent):
    """Generates scored growth ideas based on recent project activity across workspaces."""

    agent_id = "growth_ideas_agent"
    agent_name = "Daily Growth Ideas Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._workspace_mgr = workspace_manager
        self._workspaces = WorkspaceRepo(db)
        self._drafts = DraftRepo(db)
        self._opportunities = OpportunityRepo(db)
        self._media_assets = MediaAssetRepo(db)
        self._scan_log = ScanLogRepo(db)
        self._skipped_ideas = SkippedIdeaRepo(db)
        self._approved_ideas = ApprovedIdeaRepo(db)
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Daily Growth Ideas Agent, a strategic marketing advisor.

You review recent project activity across the workspace and generate actionable growth ideas.

IMPORTANT RULES:
- Every idea MUST reference specific recent projects by name
- Ideas must be actionable within 1-2 weeks
- Mix of quick wins (effort 1-3) and bigger bets (effort 5-8)
- At least 2 ideas should leverage existing content (repurposing/amplification)
- Flag performance claims with [VERIFY]
- NEVER re-suggest previous ideas. Every idea must be genuinely new — fresh angles, different approaches, or untapped opportunities. The system tracks all past ideas and will reject duplicates.
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels.

WORKFLOW — you MUST call all three tools in this order:
1. Call gather_recent_activity()
2. Call get_previous_ideas() — for context (not strict dedup — re-suggesting is OK)
3. Call generate_growth_ideas(activity_summary=<the JSON activity data from step 1>) — this generates and stores the ideas
"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="gather_recent_activity",
            description="Query the last 14 days of drafts, opportunities, media assets, and scans. Pass workspace_id for a single workspace, or omit for all workspaces.",
        )
        async def gather_recent_activity(
            workspace_id: Optional[str] = None,
            exclude_workspaces: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            return await self._gather_recent_activity(workspace_id, exclude_workspaces)

        @self.tool_registry.register(
            name="generate_growth_ideas",
            description="Generate scored growth ideas from the activity summary. Pass the full activity summary text. The number of ideas to generate will be specified in the user message. Stores result as a draft.",
        )
        async def generate_growth_ideas(
            activity_summary: str,
            workspace_id: Optional[str] = None,
            num_ideas: Optional[str] = None,
        ) -> Dict[str, Any]:
            return await self._generate_growth_ideas(activity_summary, workspace_id, num_ideas)

        @self.tool_registry.register(
            name="get_previous_ideas",
            description="Retrieve the most recent growth ideas draft for dedup context or user review.",
        )
        async def get_previous_ideas(
            workspace_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return await self._get_previous_ideas(workspace_id)

    # ── Tool implementations ─────────────────────────────────────────────

    async def _gather_recent_activity(
        self,
        workspace_id: Optional[str] = None,
        exclude_workspaces: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Gather recent activity across one or all workspaces."""
        _exclude: set[str] = set()
        if exclude_workspaces:
            if isinstance(exclude_workspaces, str):
                cleaned = exclude_workspaces.strip("[]'\" ")
                parsed = [w.strip().strip("'\"") for w in cleaned.split(",") if w.strip()]
                _exclude.update(parsed)
            else:
                _exclude.update(exclude_workspaces)

        if workspace_id:
            if workspace_id in _exclude:
                return {"error": f"Workspace '{workspace_id}' is in the exclude list"}
            workspaces = [await self._workspaces.get(workspace_id)]
            workspaces = [ws for ws in workspaces if ws is not None]
        else:
            workspaces = await self._workspaces.list_all()
            workspaces = [ws for ws in workspaces if ws.id not in _exclude]

        if not workspaces:
            return {"error": "No workspaces found"}

        summaries: Dict[str, Any] = {}
        active_workspace_count = 0

        for ws in workspaces:
            drafts = await self._drafts.list_recent(ws.id, days=_ACTIVITY_WINDOW_DAYS)
            opps = await self._opportunities.list_recent(ws.id, days=_ACTIVITY_WINDOW_DAYS)
            media = await self._media_assets.list_recent(ws.id, days=_ACTIVITY_WINDOW_DAYS)
            scans = await self._scan_log.get_latest(ws.id, limit=20)

            # Skip empty workspaces
            if not drafts and not opps and not media:
                summaries[ws.id] = {"note": "No activity in the last 14 days", "skipped": True}
                continue

            active_workspace_count += 1

            # Group drafts by content_type
            drafts_by_type: Dict[str, List[Dict[str, str]]] = defaultdict(list)
            for d in drafts:
                drafts_by_type[d.content_type].append(
                    {"title": d.title or "(untitled)", "status": d.status.value, "id": d.id}
                )

            # Group opportunities by source
            opps_by_source: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
            for o in opps:
                opps_by_source[o.source].append(
                    {"title": o.title[:100], "score": o.score, "category": o.category}
                )

            # Media counts by type
            media_counts: Dict[str, int] = defaultdict(int)
            for m in media:
                media_counts[m.media_type] += 1

            # Brand voice snippet
            brand_voice = ""
            try:
                bv = await self._workspace_mgr.get_brand_voice(ws.id)
                brand_voice = bv[:200] if bv else ""
            except Exception:
                pass

            summaries[ws.id] = {
                "name": ws.name,
                "drafts_by_type": dict(drafts_by_type),
                "drafts_total": len(drafts),
                "opportunities_by_source": dict(opps_by_source),
                "opportunities_total": len(opps),
                "media_counts": dict(media_counts),
                "media_total": len(media),
                "recent_scans": len(scans),
                "brand_voice_snippet": brand_voice,
            }

        return {
            "window_days": _ACTIVITY_WINDOW_DAYS,
            "total_workspaces": len(workspaces),
            "active_workspaces": active_workspace_count,
            "workspace_summaries": summaries,
        }

    async def _generate_growth_ideas(
        self,
        activity_summary: str,
        workspace_id: Optional[str] = None,
        num_ideas: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate scored growth ideas via two LLM calls."""
        # Determine idea count range
        ideas_range = num_ideas if num_ideas else "5-10"

        # Get previous ideas for context (not strict dedup)
        prev = await self._get_previous_ideas(workspace_id)
        dedup_section = ""
        if prev.get("ideas_titles"):
            titles = "\n".join(f"- {t}" for t in prev["ideas_titles"])
            dedup_section = f"""
PREVIOUS IDEAS — do NOT generate ideas matching or closely resembling any of these {len(prev["ideas_titles"])} titles. They have already been suggested. Generate completely NEW ideas with fresh angles:
{titles}
"""

        # Get skipped ideas — these must NOT be re-suggested
        skipped_titles = await self._skipped_ideas.list_titles("growth")
        skipped_section = ""
        if skipped_titles:
            skipped_list = "\n".join(f"- {t}" for t in skipped_titles)
            skipped_section = f"""
SKIPPED IDEAS — do NOT generate ideas matching or closely resembling any of these titles. They were explicitly rejected by the user:
{skipped_list}
"""

        # Get approved ideas — these are already being built, do NOT re-suggest
        approved_titles = await self._approved_ideas.list_titles("growth")
        approved_section = ""
        if approved_titles:
            approved_list = "\n".join(f"- {t}" for t in approved_titles)
            approved_section = f"""
APPROVED IDEAS (already being built) — do NOT generate ideas matching or closely resembling these titles:
{approved_list}
"""

        # LLM Call 1: Generate ideas as JSON
        ideas_prompt = f"""Based on the following recent project activity, generate {ideas_range} actionable growth ideas.

ACTIVITY SUMMARY:
{activity_summary}
{dedup_section}{skipped_section}{approved_section}
REQUIREMENTS:
- Every idea MUST reference specific recent projects by name
- Ideas must be actionable within 1-2 weeks
- Mix of quick wins (effort 1-3) and bigger bets (effort 5-8)
- At least 2 ideas should leverage existing content (repurposing/amplification)
- Flag any performance claims with [VERIFY]

Output ONLY a JSON array. No markdown, no explanation. Each element:
{{"title": "Short punchy title", "description": "2-3 sentence description", "workspaces": ["ws_id1"], "related_projects": ["Project Name 1"], "impact_score": 8, "effort_score": 3, "category": "content_amplification|new_channel|optimization|partnership|conversion|retention"}}"""

        config = RefinementConfig(
            criteria=_GROWTH_IDEAS_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="growth_ideas_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(ideas_prompt, "", hooks)

        # Parse JSON from response
        ideas = _parse_json_array(result.content)
        if not ideas:
            return {"error": "Failed to generate ideas — could not parse LLM JSON output"}

        # LLM Call 2: Recommended pick with execution outline
        ideas_text = json.dumps(ideas, indent=2)
        pick_prompt = f"""Given these growth ideas:

{ideas_text}

Select the ONE idea with the best impact-to-effort ratio.
Produce a response with:
1. Which idea you recommend and why (1-2 sentences)
2. A 5-step execution outline:
   - Step (action to take)
   - Owner (which agent or team)
   - Timeline (e.g., "Day 1-2")
   - Expected outcome
   - Key risk

Keep it concise and actionable."""

        pick_resp = await self.llm.complete(
            messages=[Message(role="user", content=pick_prompt)],
            temperature=0.5,
        )

        recommended_pick = pick_resp.content

        # Store as a draft — use explicit workspace or first workspace from ideas
        store_ws = workspace_id
        if not store_ws:
            # Try to pick a workspace from the generated ideas
            for idea in ideas:
                ws_list = idea.get("workspaces", [])
                if ws_list and isinstance(ws_list, list):
                    store_ws = ws_list[0]
                    break
        store_ws = store_ws or "uhg"
        body = f"# Daily Growth Ideas\n\n## Ideas\n\n```json\n{ideas_text}\n```\n\n## Recommended Priority\n\n{recommended_pick}"
        draft = await self._drafts.create(
            workspace_id=store_ws,
            content_type="growth_ideas",
            title=f"Growth Ideas — {len(ideas)} ideas",
            body=body,
        )

        return {
            "draft_id": draft.id,
            "ideas_count": len(ideas),
            "ideas": ideas,
            "recommended_pick": recommended_pick,
            "dedup_applied": bool(prev.get("ideas_titles")),
        }

    async def _get_previous_ideas(self, workspace_id: Optional[str] = None) -> Dict[str, Any]:
        """Retrieve ALL previous growth ideas drafts for hard dedup."""
        all_titles: List[str] = []
        seen: set = set()

        ws_ids: List[str] = []
        if workspace_id:
            ws_ids.append(workspace_id)
        ws_ids.append("cross_workspace")
        # Include every registered workspace
        for ws in await self._workspaces.list_all():
            if ws.id not in ws_ids:
                ws_ids.append(ws.id)

        for ws_id in ws_ids:
            drafts = await self._drafts.list_recent(ws_id, days=90, limit=100)
            for d in drafts:
                if d.content_type == "growth_ideas":
                    titles = _extract_idea_titles(d.body)
                    for t in titles:
                        t_lower = t.strip().lower()
                        if t_lower and t_lower not in seen:
                            seen.add(t_lower)
                            all_titles.append(t.strip())

        if all_titles:
            return {
                "found": True,
                "ideas_titles": all_titles,
                "total_previous": len(all_titles),
            }

        return {"found": False, "ideas_titles": []}


def _parse_json_array(text: str) -> List[Dict[str, Any]]:
    """Extract a JSON array from LLM output, tolerating markdown fences."""
    # Strip markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*", "", text).strip()
    cleaned = re.sub(r"```\s*$", "", cleaned).strip()

    # Try direct parse
    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, list):
            return parsed
    except json.JSONDecodeError:
        pass

    # Try to find a JSON array in the text
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if match:
        try:
            parsed = json.loads(match.group())
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

    return []


def _extract_idea_titles(body: str) -> List[str]:
    """Extract idea titles from a growth ideas draft body."""
    titles: List[str] = []

    # Try to parse JSON from the body
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", body)
    if match:
        try:
            ideas = json.loads(match.group(1))
            if isinstance(ideas, list):
                for idea in ideas:
                    if isinstance(idea, dict) and idea.get("title"):
                        titles.append(idea["title"])
        except json.JSONDecodeError:
            pass

    return titles
