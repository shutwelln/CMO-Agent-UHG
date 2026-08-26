"""Editorial Lead & Publishing Ops Agent — content coordination without content creation."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..editorial.store import (
    BacklogItem,
    ContentBundle,
    EditorialCalendar,
    EditorialStore,
)
from ..llm.base import BaseLLM
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

_EDITORIAL_CRITERIA = [
    QualityCriterion(
        name="strategic_alignment",
        description="Calendar entries align with brand strategy, seasonal relevance, and content pillars",
    ),
    QualityCriterion(
        name="channel_variety",
        description="Calendar includes appropriate mix of channels and content types",
    ),
    QualityCriterion(
        name="production_feasibility",
        description="Scheduled content is realistic given production capacity and lead times",
    ),
    QualityCriterion(
        name="audience_targeting",
        description="Content topics and timing are appropriate for the target audience",
    ),
    QualityCriterion(
        name="completeness",
        description="All calendar days have substantive entries with clear topics and content types",
    ),
]


class EditorialLeadAgent(BaseAgent):
    """Coordinates editorial planning and content production — does NOT write content.

    Produces structured specs with ``assets_requested`` arrays so the orchestrator
    knows which agents to invoke next. This agent is a coordinator, not a creator.
    """

    agent_id = "editorial_agent"
    agent_name = "Editorial Lead & Publishing Ops Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        editorial_data_dir: str = "./data/editorial",
        max_iterations: int = 10,
    ) -> None:
        self._workspace_mgr = workspace_manager
        self._store = EditorialStore(base_dir=editorial_data_dir)
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Editorial Lead & Publishing Ops Agent.

You coordinate content production from idea through publishing. You are a
COORDINATOR — you do NOT write content yourself. You produce structured
specs and checklists that other agents execute.

WHAT YOU DO:
- Maintain the content backlog (ideas, priorities, channels)
- Create editorial calendars (weekly slots)
- Design content bundles (coordinated multi-asset packages)
- Track bundle status through the publishing pipeline
- Generate publish checklists

WHAT YOU DO NOT DO:
- Write blog posts, social copy, or any content (writer_agent does this)
- Generate images or videos (visual_agent, video_agent do this)
- Create documents or spreadsheets (docs_agent, sheets_agent do this)

CONTENT BUNDLE STATE MACHINE:
  draft → review → approved → scheduled → published
  (review can go back to draft, approved can go back to draft)

ASSETS_REQUESTED FORMAT:
When creating a content bundle, specify assets as:
```json
{"assets_requested": [
  {"agent": "writer_agent", "spec": "1200-word blog post about X"},
  {"agent": "visual_agent", "spec": "Hero image, infographic style"},
  {"agent": "social_media_agent", "spec": "3 social posts promoting the blog"}
]}
```
The orchestrator sees this output and can delegate to the specified agents.

PUBLISH CHECKLIST:
Always include a checklist for each bundle covering:
- Content review and approval
- SEO optimization
- Social media scheduling
- Email distribution
- Analytics tracking setup

SEO CONTENT COORDINATION:
- Search-targeted content requires a structured brief from seo_aeo_agent before
  being assigned to writer_agent.
- You may schedule SEO-briefed content into calendars but may NOT modify the SEO spec.
- For search content bundles, the production sequence is: seo_aeo_agent (brief) →
  writer_agent (content) → review → publish.
- When creating content bundles with search-targeted assets, populate the seo_keywords
  field from the SEO brief.

ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="create_editorial_plan",
            description="Create a weekly editorial calendar with content slots. Uses the LLM to generate a strategic plan based on workspace context.",
        )
        async def create_editorial_plan(
            workspace_id: str,
            week_start: str,
            focus_themes: Optional[List[str]] = None,
            channel_mix: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a weekly editorial calendar for {workspace_id}.

Week starting: {week_start}
Focus themes: {", ".join(focus_themes) if focus_themes else "general"}
Channel mix: {", ".join(channel_mix) if channel_mix else "blog, email, social"}

Brand voice context:
{brand_voice[:500] if brand_voice else "No brand voice configured"}

Return a JSON array of content slots. Each slot should have:
- day: Monday/Tuesday/etc
- channel: blog/email/social/etc
- topic: what the content is about
- content_type: article/newsletter/social_post/etc
- priority: high/medium/low
- notes: any special instructions

Return ONLY the JSON array, no other text."""

            config = RefinementConfig(
                criteria=_EDITORIAL_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="editorial_calendar_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            # Parse the LLM response as slots
            import json

            try:
                slots = json.loads(result.content)
            except json.JSONDecodeError:
                slots = [{"raw_plan": result.content}]

            calendar = EditorialCalendar(
                workspace_id=workspace_id,
                week_start=week_start,
                slots=slots,
            )
            saved = self._store.save_calendar(calendar)
            return {
                "workspace_id": workspace_id,
                "week_start": week_start,
                "slots_count": len(saved.slots),
                "slots": saved.slots,
            }

        @self.tool_registry.register(
            name="add_backlog_item",
            description="Add a content idea to the editorial backlog.",
        )
        async def add_backlog_item(
            workspace_id: str,
            idea: str,
            priority: str = "medium",
            channel: str = "",
        ) -> Dict[str, Any]:
            item = BacklogItem(
                workspace_id=workspace_id,
                idea=idea,
                priority=priority,
                channel=channel,
            )
            saved = self._store.add_backlog_item(item)
            return {
                "id": saved.id,
                "idea": saved.idea,
                "priority": saved.priority,
                "channel": saved.channel,
                "status": saved.status,
            }

        @self.tool_registry.register(
            name="list_backlog",
            description="List editorial backlog items, optionally filtered by workspace and/or status (open, planned, done, dismissed).",
        )
        async def list_backlog(
            workspace_id: Optional[str] = None,
            status: Optional[str] = None,
        ) -> Dict[str, Any]:
            items = self._store.list_backlog(workspace_id=workspace_id, status=status)
            return {
                "count": len(items),
                "items": [
                    {
                        "id": i.id,
                        "idea": i.idea[:100],
                        "priority": i.priority,
                        "channel": i.channel,
                        "status": i.status,
                        "created_at": i.created_at,
                    }
                    for i in items
                ],
            }

        @self.tool_registry.register(
            name="create_content_bundle",
            description="Create a coordinated content bundle — a multi-asset content package with target audience, channels, CTAs, and requested assets from other agents.",
        )
        async def create_content_bundle(
            workspace_id: str,
            title: str,
            target_audience: str = "",
            channels: Optional[List[str]] = None,
            primary_cta: str = "",
            key_messages: Optional[List[str]] = None,
            seo_keywords: Optional[List[str]] = None,
            assets_requested: Optional[List[Dict[str, str]]] = None,
        ) -> Dict[str, Any]:
            # Generate a publish checklist
            checklist = [
                "Content draft reviewed and approved",
                "SEO metadata set (title, description, keywords)",
                "Visual assets created and approved",
                "Social media posts drafted and scheduled",
                "Email distribution configured",
                "UTM parameters set for all links",
                "Analytics events verified",
                "Final proofread completed",
            ]

            bundle = ContentBundle(
                workspace_id=workspace_id,
                title=title,
                target_audience=target_audience,
                channels=channels or [],
                primary_cta=primary_cta,
                key_messages=key_messages or [],
                seo_keywords=seo_keywords or [],
                assets_requested=assets_requested or [],
                publish_checklist=checklist,
            )
            saved = self._store.create_bundle(bundle)
            return {
                "bundle_id": saved.id,
                "title": saved.title,
                "status": saved.status,
                "channels": saved.channels,
                "assets_requested": saved.assets_requested,
                "publish_checklist": saved.publish_checklist,
            }

        @self.tool_registry.register(
            name="update_bundle_status",
            description="Transition a content bundle to a new status. State machine: draft→review→approved→scheduled→published.",
        )
        async def update_bundle_status(
            bundle_id: str,
            new_status: str,
        ) -> Dict[str, Any]:
            try:
                bundle = self._store.update_bundle_status(bundle_id, new_status)
                if not bundle:
                    return {"error": f"Bundle {bundle_id} not found"}
                return {
                    "bundle_id": bundle.id,
                    "title": bundle.title,
                    "status": bundle.status,
                    "updated_at": bundle.updated_at,
                }
            except ValueError as e:
                return {"error": str(e)}

        @self.tool_registry.register(
            name="list_bundles",
            description="List content bundles, optionally filtered by workspace and/or status.",
        )
        async def list_bundles(
            workspace_id: Optional[str] = None,
            status: Optional[str] = None,
        ) -> Dict[str, Any]:
            bundles = self._store.list_bundles(workspace_id=workspace_id, status=status)
            return {
                "count": len(bundles),
                "bundles": [
                    {
                        "id": b.id,
                        "title": b.title,
                        "status": b.status,
                        "channels": b.channels,
                        "assets_count": len(b.assets_requested),
                        "created_at": b.created_at,
                    }
                    for b in bundles
                ],
            }

        @self.tool_registry.register(
            name="get_publish_checklist",
            description="Get the publish checklist and current status for a content bundle.",
        )
        async def get_publish_checklist(
            bundle_id: str,
        ) -> Dict[str, Any]:
            bundle = self._store.get_bundle(bundle_id)
            if not bundle:
                return {"error": f"Bundle {bundle_id} not found"}
            return {
                "bundle_id": bundle.id,
                "title": bundle.title,
                "status": bundle.status,
                "publish_checklist": bundle.publish_checklist,
                "assets_requested": bundle.assets_requested,
                "channels": bundle.channels,
                "primary_cta": bundle.primary_cta,
            }
