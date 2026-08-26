"""GTM (Go-To-Market) Agent - launch strategy and execution orchestration."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo, WorkspaceRepo
from ..llm.base import BaseLLM
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# GTM quality criteria for RefinementLoop
_GTM_CRITERIA = [
    QualityCriterion(
        name="market_specificity",
        description="Market definition, TAM/SAM/SOM, and beachhead selection use specific data, not generic estimates",
    ),
    QualityCriterion(
        name="positioning_clarity",
        description="Value proposition and positioning are differentiated, specific, and defensible",
    ),
    QualityCriterion(
        name="channel_justification",
        description="Channel recommendations include rationale, expected CAC ranges, and prioritization logic",
    ),
    QualityCriterion(
        name="economic_validity",
        description="Unit economics, payback periods, and growth assumptions are internally consistent",
    ),
    QualityCriterion(
        name="risk_completeness",
        description="Risk assessment covers execution, market, regulatory, and competitive dimensions",
    ),
]

# ── GTM launch phases ───────────────────────────────────────────────────

_LAUNCH_PHASES = {
    "validation": {
        "label": "Phase 1 — Validation",
        "goal": "Prove message-market fit with a tight beachhead segment",
        "typical_duration": "2-4 weeks",
        "exit_criteria": [
            "ICP validated with real conversations or signals",
            "Landing page live with conversion tracking",
            "First 50-100 signups or waitlist entries",
            "Core value prop tested in 2-3 channel experiments",
        ],
    },
    "controlled_launch": {
        "label": "Phase 2 — Controlled Launch",
        "goal": "Scale initial traction with repeatable acquisition loops",
        "typical_duration": "4-8 weeks",
        "exit_criteria": [
            "CAC within 2x target",
            "Activation rate above minimum threshold",
            "At least 1 channel producing consistent volume",
            "Retention signals validated (D7/D30 cohorts)",
        ],
    },
    "scaled_expansion": {
        "label": "Phase 3 — Scaled Expansion",
        "goal": "Expand to adjacent segments and optimize unit economics",
        "typical_duration": "8-16 weeks",
        "exit_criteria": [
            "CAC at or below target across 2+ channels",
            "LTV:CAC ratio > 3:1",
            "Second segment validated",
            "Revenue or monetization events tracking to plan",
        ],
    },
}


# ── Helpers ─────────────────────────────────────────────────────────────


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences from LLM JSON responses."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text


class GTMAgent(BaseAgent):
    """Designs and drives go-to-market execution for new growth products.

    Not a content creator or performance operator — this agent is the
    architect and quarterback of product launch. It produces structured
    GTM plans, sequences phased rollouts, assigns briefs to sub-agents,
    and enforces commercial discipline.

    Core capabilities:
    - ICP definition and beachhead selection
    - Differentiated value proposition development
    - Channel strategy and funnel architecture
    - Phased rollout planning (validation → launch → scale)
    - Unit economics calculator (pure math)
    - Launch phase tracking with exit criteria
    - Risk assessment and constraint identification
    - Sub-agent brief generation for execution handoff
    """

    agent_id = "gtm_agent"
    agent_name = "GTM Strategy Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 15,
    ) -> None:
        self._workspace_mgr = workspace_manager
        self._workspaces = WorkspaceRepo(db)
        self._drafts = DraftRepo(db)
        self._config = ConfigRepo(db)
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    # ── Context helpers ──────────────────────────────────────────────────

    async def _get_workspace_context(self, workspace_id: str) -> tuple[str, str]:
        """Load brand voice and reference docs for a workspace."""
        brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
        reference_docs = await self._workspace_mgr.get_reference_docs(workspace_id)
        return brand_voice or "", reference_docs or ""

    def _format_context_section(self, brand_voice: str, reference_docs: str) -> str:
        """Format brand voice and reference docs for LLM prompt injection."""
        sections = []
        if brand_voice:
            sections.append(f"BRAND CONTEXT:\n{brand_voice[:500]}")
        if reference_docs:
            sections.append(f"REFERENCE DOCUMENTS:\n{reference_docs[:12000]}")
        return "\n\n".join(sections) if sections else ""

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        ws_label = workspace_id or "all workspaces"

        phase_lines = []
        for phase_key, phase in _LAUNCH_PHASES.items():
            phase_lines.append(
                f"  - {phase['label']}: {phase['goal']} ({phase['typical_duration']})"
            )
        phases_text = "\n".join(phase_lines)

        return f"""You are the Growth Go-To-Market Orchestrator for {ws_label}.

Your sole responsibility is to design, sequence, and drive full go-to-market execution
for new growth products from zero to scalable traction.

You are NOT a content creator. You are NOT a performance operator.
You are the architect and quarterback of launch.

You define the macro funnel architecture (traffic sources, conversion events, monetization model) as part
of GTM strategy. Acquisition Agent owns the micro funnel (page-level friction analysis, journey mapping,
drop-off diagnosis). Do not produce page-level funnel audits.

You operate with commercial urgency, capital efficiency, and measurable accountability.

OPERATING PRINCIPLES:
1. Beachhead First — select one segment and dominate it before expanding
2. Capital Efficient Growth — bias toward durable acquisition loops, not vanity reach
3. Instrument Before Spend — analytics, attribution, and funnel tracking before traffic scales
4. Message-Market Fit Before Channel Scale — validated positioning before aggressive paid expansion
5. Revenue Clarity — monetization mechanics defined before growth acceleration
6. Language Standard — clear, benefit-driven language; specific, measurable, outcome-oriented claims

REQUIRED LAUNCH FRAMEWORK:
When producing a GTM plan, you MUST include ALL of these sections:
1. Market Definition: ICP, urgent problem, current alternatives, why now
2. Positioning & Narrative: core value prop, 3 messaging pillars, proof mechanisms, competitive differentiation
3. Channel Strategy: owned, earned, paid, partnerships, direct outreach (with funnel role and success metrics for each)
4. Funnel Architecture: traffic sources, landing experience, conversion events, activation events, retention triggers, monetization events
5. Phased Rollout: validation → controlled launch → scaled expansion (with clear exit criteria per phase)
6. Metrics & Economics: CAC target, LTV assumptions, conversion benchmarks, retention benchmarks, break-even timeline
7. Risk Assessment: execution risks, channel dependency risks, regulatory risks, operational constraints

LAUNCH PHASES:
{phases_text}

AGENT COORDINATION RULES:
When your plan requires output from another agent in the ecosystem, you must:
1. State the agent name explicitly
2. Provide a structured brief with clear deliverables
3. Define output format expected
4. Define sequence order (what must happen first)
5. Define success criteria

If an execution agent produces output that conflicts with the defined ICP, positioning,
or economic constraints, you must reject and revise the brief.

SEO/AEO COORDINATION:
- SEO/AEO Agent owns search architecture and organic execution. When your GTM plan
  includes organic/SEO as a channel, produce a strategic brief for the SEO/AEO Agent
  specifying geographic priorities, product context, priority page types, and timeline.
- Do NOT specify keyword targets, page structures, or linking rules — the SEO/AEO Agent
  designs those based on your strategic direction.
- The SEO/AEO Agent translates your ICP and beachhead priorities into scalable search
  architecture.

MARKETPLACE / MULTI-LOCATION RULES:
- Prioritize geographic clustering strategy when relevant
- Delegate SEO and location page architecture to seo_aeo_agent — do not design search architecture yourself
- Design monetization placements intentionally
- Incorporate email lifecycle early
- Define partnership acquisition channels
- Think in terms of compounding distribution assets, not one-time campaigns

TOOLS:
- Use calculate_unit_economics for all math (CAC, LTV, payback). Never estimate these in prose.
- Use get_launch_status to check current phase before recommending next actions.
- Use update_launch_phase to advance phases only when exit criteria are met.
- All strategic outputs (ICP, channel strategy, risk assessment, briefs) are saved as drafts automatically.

You are decisive. You choose. You sequence. You enforce alignment.

ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels.

Current workspace: {ws_label}"""

    def register_tools(self) -> None:
        # ── create_gtm_plan ──────────────────────────────────────────
        @self.tool_registry.register(
            name="create_gtm_plan",
            description=(
                "Create a comprehensive go-to-market plan for a new product or initiative. "
                "Produces a board-ready GTM plan with ICP, positioning, channel strategy, "
                "funnel architecture, phased rollout, unit economics, and risk assessment. "
                "Requires: product_description, workspace_id. Optional: target_market, "
                "budget_constraints, timeline_constraints."
            ),
        )
        async def create_gtm_plan(
            product_description: str,
            workspace_id: str,
            target_market: str = "",
            budget_constraints: str = "",
            timeline_constraints: str = "",
            competitive_context: str = "",
        ) -> Dict[str, Any]:
            return await self._create_gtm_plan(
                product_description=product_description,
                workspace_id=workspace_id,
                target_market=target_market,
                budget_constraints=budget_constraints,
                timeline_constraints=timeline_constraints,
                competitive_context=competitive_context,
            )

        # ── define_icp ───────────────────────────────────────────────
        @self.tool_registry.register(
            name="define_icp",
            description=(
                "Define the Ideal Customer Profile and beachhead segment for a product. "
                "Returns a structured ICP with demographics, psychographics, urgent problem, "
                "current alternatives, and why-now thesis. Saved as a draft."
            ),
        )
        async def define_icp(
            product_description: str,
            workspace_id: str,
            market_context: str = "",
        ) -> Dict[str, Any]:
            return await self._define_icp(
                product_description=product_description,
                workspace_id=workspace_id,
                market_context=market_context,
            )

        # ── create_channel_strategy ──────────────────────────────────
        @self.tool_registry.register(
            name="create_channel_strategy",
            description=(
                "Design a channel strategy with owned, earned, paid, partnership, and "
                "direct outreach channels. Each channel includes funnel role, estimated "
                "CAC, and success metrics. Saved as a draft."
            ),
        )
        async def create_channel_strategy(
            product_description: str,
            workspace_id: str,
            icp_summary: str = "",
            budget_range: str = "",
        ) -> Dict[str, Any]:
            return await self._create_channel_strategy(
                product_description=product_description,
                workspace_id=workspace_id,
                icp_summary=icp_summary,
                budget_range=budget_range,
            )

        # ── create_agent_briefs ──────────────────────────────────────
        @self.tool_registry.register(
            name="create_agent_briefs",
            description=(
                "Generate structured, machine-readable execution briefs for downstream "
                "agents based on an approved GTM plan. Each brief maps to an orchestrator "
                "tool call with agent_name, deliverable, sequence_order, and dependencies."
            ),
        )
        async def create_agent_briefs(
            gtm_plan_summary: str,
            workspace_id: str,
            phase: str = "validation",
        ) -> Dict[str, Any]:
            return await self._create_agent_briefs(
                gtm_plan_summary=gtm_plan_summary,
                workspace_id=workspace_id,
                phase=phase,
            )

        # ── get_launch_phases ────────────────────────────────────────
        @self.tool_registry.register(
            name="get_launch_phases",
            description=(
                "Return the standard launch phase framework with goals, durations, "
                "and exit criteria for each phase. No API call — returns local config."
            ),
        )
        async def get_launch_phases() -> Dict[str, Any]:
            return {
                "phases": _LAUNCH_PHASES,
                "note": (
                    "Each phase has clear exit criteria. Do not advance to the next "
                    "phase until all exit criteria are met."
                ),
            }

        # ── assess_gtm_risks ────────────────────────────────────────
        @self.tool_registry.register(
            name="assess_gtm_risks",
            description=(
                "Identify and score execution risks, channel dependency risks, "
                "regulatory risks, and operational constraints for a GTM plan. "
                "Saved as a draft."
            ),
        )
        async def assess_gtm_risks(
            gtm_plan_summary: str,
            workspace_id: str,
        ) -> Dict[str, Any]:
            return await self._assess_risks(
                gtm_plan_summary=gtm_plan_summary,
                workspace_id=workspace_id,
            )

        # ── calculate_unit_economics (pure math) ─────────────────────
        @self.tool_registry.register(
            name="calculate_unit_economics",
            description=(
                "Calculate unit economics from raw numbers. Pure math, no LLM call. "
                "Returns CAC, LTV, LTV:CAC ratio, payback period, break-even, and "
                "monthly projections. Requires spend and customers_acquired at minimum."
            ),
        )
        async def calculate_unit_economics(
            spend: float,
            customers_acquired: int,
            avg_revenue_per_customer: float = 0.0,
            avg_monthly_revenue_per_customer: float = 0.0,
            avg_customer_lifetime_months: float = 0.0,
            monthly_churn_rate: float = 0.0,
            gross_margin: float = 1.0,
        ) -> Dict[str, Any]:
            return self._calculate_unit_economics(
                spend=spend,
                customers_acquired=customers_acquired,
                avg_revenue_per_customer=avg_revenue_per_customer,
                avg_monthly_revenue_per_customer=avg_monthly_revenue_per_customer,
                avg_customer_lifetime_months=avg_customer_lifetime_months,
                monthly_churn_rate=monthly_churn_rate,
                gross_margin=gross_margin,
            )

        # ── get_launch_status ────────────────────────────────────────
        @self.tool_registry.register(
            name="get_launch_status",
            description=(
                "Get current launch phase status for a workspace, including current "
                "phase, exit criteria checklist, and phase history."
            ),
        )
        async def get_launch_status(
            workspace_id: str,
        ) -> Dict[str, Any]:
            return await self._get_launch_status(workspace_id=workspace_id)

        # ── update_launch_phase ──────────────────────────────────────
        @self.tool_registry.register(
            name="update_launch_phase",
            description=(
                "Advance or update the launch phase for a workspace. Records exit "
                "criteria status and phase transition notes. Will warn if exit "
                "criteria are not met."
            ),
        )
        async def update_launch_phase(
            workspace_id: str,
            new_phase: str,
            exit_criteria_met: List[str],
            exit_criteria_unmet: List[str] = [],
            notes: str = "",
        ) -> Dict[str, Any]:
            return await self._update_launch_phase(
                workspace_id=workspace_id,
                new_phase=new_phase,
                exit_criteria_met=exit_criteria_met,
                exit_criteria_unmet=exit_criteria_unmet,
                notes=notes,
            )

    # ── Tool implementations ────────────────────────────────────────────

    async def _create_gtm_plan(
        self,
        product_description: str,
        workspace_id: str,
        target_market: str = "",
        budget_constraints: str = "",
        timeline_constraints: str = "",
        competitive_context: str = "",
    ) -> Dict[str, Any]:
        """Generate a comprehensive GTM plan."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        constraints = []
        if target_market:
            constraints.append(f"Target market: {target_market}")
        if budget_constraints:
            constraints.append(f"Budget constraints: {budget_constraints}")
        if timeline_constraints:
            constraints.append(f"Timeline constraints: {timeline_constraints}")
        if competitive_context:
            constraints.append(f"Competitive context: {competitive_context}")
        constraints_text = (
            "\n".join(constraints) if constraints else "No specific constraints provided."
        )

        prompt = f"""Create a comprehensive go-to-market plan for the following product:

PRODUCT: {product_description}

{context_section}

CONSTRAINTS:
{constraints_text}

You MUST produce a structured plan with ALL seven sections:

1. MARKET DEFINITION
   - ICP description (demographics, psychographics, behavior)
   - Urgent problem they face
   - Current alternatives and why they fall short
   - Why now (market timing thesis)

2. POSITIONING & NARRATIVE
   - Core value proposition (one sentence)
   - 3 messaging pillars with supporting proof points
   - Proof mechanisms (data, testimonials, demos, case studies)
   - Competitive differentiation matrix

3. CHANNEL STRATEGY
   For each channel (owned, earned, paid, partnerships, direct outreach):
   - Specific tactics
   - Role in funnel (awareness / consideration / conversion / retention)
   - Estimated CAC range
   - Success metrics
   - Priority order

4. FUNNEL ARCHITECTURE
   - Traffic sources → Landing experience → Conversion events → Activation events → Retention triggers → Monetization events
   - Each stage with specific metrics and targets

5. PHASED ROLLOUT
   Phase 1 - Validation (2-4 weeks): specific actions and exit criteria
   Phase 2 - Controlled Launch (4-8 weeks): specific actions and exit criteria
   Phase 3 - Scaled Expansion (8-16 weeks): specific actions and exit criteria

6. METRICS & ECONOMICS
   - CAC target (by channel)
   - LTV assumptions (with methodology)
   - Conversion benchmarks at each funnel stage
   - Retention benchmarks (D7, D30, D90)
   - Break-even timeline
   - Monthly burn rate projection

7. RISK ASSESSMENT
   - Top 3 execution risks with mitigation
   - Channel dependency risks
   - Regulatory risks
   - Operational constraints and resource gaps

FORMAT: Return as structured JSON with section keys: market_definition, positioning, channel_strategy, funnel_architecture, phased_rollout, metrics_economics, risk_assessment. Each section should contain structured sub-objects, not raw text.
"""

        config = RefinementConfig(
            criteria=_GTM_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="gtm_plan_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)

        try:
            plan = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            plan = {"raw_plan": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="gtm_plan",
            title=f"GTM Plan: {product_description[:80]}",
            body=json.dumps(plan, indent=2) if isinstance(plan, dict) else content,
        )

        logger.info(
            "gtm_plan_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            sections=list(plan.keys()) if isinstance(plan, dict) else ["raw"],
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "plan": plan,
            "product": product_description[:200],
            "workspace_id": workspace_id,
        }

    async def _define_icp(
        self,
        product_description: str,
        workspace_id: str,
        market_context: str = "",
    ) -> Dict[str, Any]:
        """Define ICP and beachhead segment."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        prompt = f"""Define the Ideal Customer Profile and beachhead segment for:

PRODUCT: {product_description}
{f"MARKET CONTEXT: {market_context}" if market_context else ""}

{context_section}

Return structured JSON with:
- beachhead_segment: the single most promising initial segment to dominate first
- demographics: age, income, location, household
- psychographics: values, motivations, fears, aspirations
- behavior: online behavior, purchase patterns, information sources
- urgent_problem: the specific pain point this product solves
- current_alternatives: what they do today and why it falls short
- why_now: market timing thesis for this segment
- segment_size_estimate: rough TAM/SAM/SOM for the beachhead
- acquisition_signals: how to find and reach this person
"""

        config = RefinementConfig(
            criteria=_GTM_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="gtm_icp_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)

        try:
            icp = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            icp = {"raw_icp": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="gtm_icp",
            title=f"ICP: {product_description[:80]}",
            body=json.dumps(icp, indent=2) if isinstance(icp, dict) else content,
        )

        logger.info("gtm_icp_created", workspace_id=workspace_id, draft_id=draft.id)

        return {
            "status": "defined",
            "draft_id": draft.id,
            "icp": icp,
            "workspace_id": workspace_id,
        }

    async def _create_channel_strategy(
        self,
        product_description: str,
        workspace_id: str,
        icp_summary: str = "",
        budget_range: str = "",
    ) -> Dict[str, Any]:
        """Design multi-channel acquisition strategy."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        prompt = f"""Design a channel strategy for:

PRODUCT: {product_description}
{f"ICP: {icp_summary}" if icp_summary else ""}
{f"BUDGET: {budget_range}" if budget_range else ""}

{context_section}

For EACH of these five channel categories, provide specific tactics:

1. OWNED (blog, SEO, email, app, social profiles)
2. EARNED (PR, word of mouth, reviews, community, UGC)
3. PAID (search ads, social ads, display, retargeting)
4. PARTNERSHIPS (affiliates, co-marketing, integrations, distribution deals)
5. DIRECT OUTREACH (sales, LinkedIn, cold email, events)

For each tactic, specify:
- funnel_role: awareness | consideration | conversion | retention
- estimated_cac_range: dollar range per acquisition
- success_metric: specific measurable outcome
- priority: 1 (do first) through 5 (do later)
- rationale: why this channel for this product/ICP

Return as structured JSON with keys: owned, earned, paid, partnerships, direct_outreach.
Each containing an array of tactic objects.
"""

        config = RefinementConfig(
            criteria=_GTM_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="gtm_channel_strategy_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)

        try:
            strategy = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            strategy = {"raw_strategy": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="gtm_channel_strategy",
            title=f"Channel Strategy: {product_description[:60]}",
            body=json.dumps(strategy, indent=2) if isinstance(strategy, dict) else content,
        )

        logger.info("gtm_channel_strategy_created", workspace_id=workspace_id, draft_id=draft.id)

        return {
            "status": "created",
            "draft_id": draft.id,
            "channel_strategy": strategy,
            "workspace_id": workspace_id,
        }

    async def _create_agent_briefs(
        self,
        gtm_plan_summary: str,
        workspace_id: str,
        phase: str = "validation",
    ) -> Dict[str, Any]:
        """Generate structured, machine-readable briefs for downstream agents."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        prompt = f"""Based on this GTM plan, generate execution briefs for downstream agents.

GTM PLAN:
{gtm_plan_summary[:6000]}

CURRENT PHASE: {phase}

{context_section}

Available agents in the ecosystem:
- research_agent: Web research, competitive intelligence, market data
- writer_agent: Content creation, copywriting, messaging
- visual_agent: Image generation (SDXL, DALL-E 3, Gemini)
- video_agent: AI video generation (Kling, Sora)
- motion_graphics_agent: Programmatic animation (Remotion)
- docs_agent: Google Docs creation (reports, briefs, proposals)
- sheets_agent: Google Sheets creation (trackers, models)
- deck_agent: Google Slides presentations
- performance_marketer_agent: Paid ads, campaign optimization
- social_media_agent: Social content, posting strategy
- lifecycle_marketing_agent: Email/SMS flows, customer journeys
- marketing_analytics_agent: Tracking setup, attribution, dashboards
- acquisition_agent: Funnel architecture, landing page strategy, friction analysis
- conversion_optimization_agent: On-site conversion optimization, experiment design, CTA architecture, offer positioning, revenue per visitor optimization. Requires: page_types, conversion_goals, current_metrics, economic_targets
- compliance_agent: Regulatory review, disclosures
- linkedin_partnerships_agent: LinkedIn outreach, partnership prospecting
- editorial_agent: Content production coordination
- seo_aeo_agent: SEO/AEO architecture — keyword clustering, page taxonomy, content briefs, internal linking, structured data, organic measurement. Requires: geographic_focus, product_context, priority_page_types, timeline

For the current phase, generate briefs ONLY for agents needed NOW.

CRITICAL: Each brief MUST be a JSON object with EXACTLY these keys (the orchestrator
will parse these programmatically to auto-delegate):

{{
  "agent_id": "<exact agent_id from list above, e.g. writer_agent>",
  "tool_name": "<the orchestrator tool to call, same as agent_id>",
  "instruction": "<the exact instruction string to pass to the agent>",
  "deliverable": "<specific output expected>",
  "output_format": "<what the output should look like>",
  "sequence_order": <integer, 1 = do first>,
  "depends_on": ["<agent_id that must complete first>"],
  "success_criteria": "<how to evaluate the output>",
  "estimated_tokens": <approximate output token budget>
}}

Return as a JSON object with key "briefs" containing the array, and key "execution_summary"
with a short paragraph describing the overall execution sequence.
"""

        config = RefinementConfig(
            criteria=_GTM_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="gtm_agent_briefs_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)

        try:
            parsed = json.loads(content)
            if isinstance(parsed, list):
                parsed = {"briefs": parsed, "execution_summary": ""}
            briefs = parsed.get("briefs", parsed)
        except (json.JSONDecodeError, TypeError):
            parsed = {"briefs": [{"raw_briefs": content}], "execution_summary": ""}
            briefs = parsed["briefs"]

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="gtm_agent_briefs",
            title=f"GTM Agent Briefs — {phase.replace('_', ' ').title()}",
            body=json.dumps(parsed, indent=2),
        )

        logger.info(
            "gtm_briefs_created",
            workspace_id=workspace_id,
            phase=phase,
            brief_count=len(briefs) if isinstance(briefs, list) else 1,
            draft_id=draft.id,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "phase": phase,
            "briefs": briefs,
            "execution_summary": parsed.get("execution_summary", ""),
            "brief_count": len(briefs) if isinstance(briefs, list) else 1,
            "workspace_id": workspace_id,
        }

    async def _assess_risks(
        self,
        gtm_plan_summary: str,
        workspace_id: str,
    ) -> Dict[str, Any]:
        """Identify and score GTM risks."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        prompt = f"""Assess the risks for this go-to-market plan:

{gtm_plan_summary[:6000]}

{context_section}

Return structured JSON with:

1. execution_risks: array of objects with risk, likelihood (high/medium/low), impact (high/medium/low), mitigation
2. channel_dependency_risks: array — risks from over-reliance on specific channels
3. regulatory_risks: array — compliance, legal, or regulatory concerns
4. operational_constraints: array — resource gaps, capability gaps, timing constraints

For each risk, include a specific mitigation strategy.

Also include a scored readiness assessment:
- readiness_score: float 0.0 to 1.0
- readiness_by_dimension: object with scores (0.0-1.0) for:
  - product_market_fit
  - positioning_clarity
  - channel_readiness
  - team_capability
  - financial_runway
  - measurement_setup
- readiness_label: "ready" | "conditionally_ready" | "not_ready"
- readiness_rationale: explanation of the score
- blockers: array of items that must be resolved before launch
"""

        config = RefinementConfig(
            criteria=_GTM_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="gtm_risk_assessment_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)

        try:
            risks = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            risks = {"raw_risks": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="gtm_risk_assessment",
            title=f"GTM Risk Assessment",
            body=json.dumps(risks, indent=2) if isinstance(risks, dict) else content,
        )

        logger.info("gtm_risk_assessment_created", workspace_id=workspace_id, draft_id=draft.id)

        return {
            "status": "assessed",
            "draft_id": draft.id,
            "risk_assessment": risks,
            "workspace_id": workspace_id,
        }

    # ── Unit economics calculator (pure math) ───────────────────────────

    def _calculate_unit_economics(
        self,
        spend: float,
        customers_acquired: int,
        avg_revenue_per_customer: float = 0.0,
        avg_monthly_revenue_per_customer: float = 0.0,
        avg_customer_lifetime_months: float = 0.0,
        monthly_churn_rate: float = 0.0,
        gross_margin: float = 1.0,
    ) -> Dict[str, Any]:
        """Pure math unit economics — no LLM call."""
        metrics: Dict[str, Any] = {
            "spend": round(spend, 2),
            "customers_acquired": customers_acquired,
        }

        # CAC
        if customers_acquired > 0:
            cac = spend / customers_acquired
            metrics["cac"] = round(cac, 2)
        else:
            cac = 0.0
            metrics["cac"] = 0.0
            metrics["warning"] = "No customers acquired — CAC undefined"

        # LTV calculation
        ltv = 0.0

        # Method 1: direct total revenue per customer
        if avg_revenue_per_customer > 0:
            ltv = avg_revenue_per_customer * gross_margin
            metrics["ltv_method"] = "direct_revenue"

        # Method 2: monthly revenue * lifetime
        elif avg_monthly_revenue_per_customer > 0 and avg_customer_lifetime_months > 0:
            ltv = avg_monthly_revenue_per_customer * avg_customer_lifetime_months * gross_margin
            metrics["ltv_method"] = "monthly_x_lifetime"

        # Method 3: monthly revenue / churn
        elif avg_monthly_revenue_per_customer > 0 and monthly_churn_rate > 0:
            avg_customer_lifetime_months = 1.0 / monthly_churn_rate
            ltv = avg_monthly_revenue_per_customer * avg_customer_lifetime_months * gross_margin
            metrics["ltv_method"] = "revenue_over_churn"
            metrics["implied_lifetime_months"] = round(avg_customer_lifetime_months, 1)

        if ltv > 0:
            metrics["ltv"] = round(ltv, 2)
            metrics["gross_margin"] = round(gross_margin, 2)

            if cac > 0:
                metrics["ltv_cac_ratio"] = round(ltv / cac, 2)

                # Payback period (months)
                if avg_monthly_revenue_per_customer > 0:
                    monthly_gross = avg_monthly_revenue_per_customer * gross_margin
                    if monthly_gross > 0:
                        metrics["payback_months"] = round(cac / monthly_gross, 1)

                # Health assessment
                ratio = ltv / cac
                if ratio >= 3.0:
                    metrics["health"] = "healthy"
                elif ratio >= 1.5:
                    metrics["health"] = "marginal"
                else:
                    metrics["health"] = "unsustainable"

        # Monthly projections (if we have monthly revenue)
        if avg_monthly_revenue_per_customer > 0 and customers_acquired > 0:
            monthly_revenue = avg_monthly_revenue_per_customer * customers_acquired
            monthly_gross_profit = monthly_revenue * gross_margin
            metrics["monthly_revenue"] = round(monthly_revenue, 2)
            metrics["monthly_gross_profit"] = round(monthly_gross_profit, 2)
            metrics["monthly_net_of_acquisition"] = round(monthly_gross_profit - spend, 2)

        if monthly_churn_rate > 0:
            metrics["monthly_churn_rate"] = round(monthly_churn_rate, 4)
            metrics["annual_churn_rate"] = round(1.0 - (1.0 - monthly_churn_rate) ** 12, 4)

        return metrics

    # ── Launch phase tracker ────────────────────────────────────────────

    async def _get_launch_status(self, workspace_id: str) -> Dict[str, Any]:
        """Get current launch phase and exit criteria status from config."""
        raw = await self._config.get(workspace_id, "gtm_launch_status")
        if raw:
            try:
                status = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                status = None
        else:
            status = None

        if not status:
            return {
                "current_phase": "not_started",
                "workspace_id": workspace_id,
                "phases": _LAUNCH_PHASES,
                "history": [],
                "note": "No launch has been initiated for this workspace. Use update_launch_phase to begin.",
            }

        current = status.get("current_phase", "not_started")
        phase_config = _LAUNCH_PHASES.get(current, {})

        return {
            "current_phase": current,
            "phase_label": phase_config.get("label", current),
            "phase_goal": phase_config.get("goal", ""),
            "exit_criteria": phase_config.get("exit_criteria", []),
            "exit_criteria_met": status.get("exit_criteria_met", []),
            "exit_criteria_unmet": status.get("exit_criteria_unmet", []),
            "phase_started_at": status.get("phase_started_at", ""),
            "history": status.get("history", []),
            "workspace_id": workspace_id,
        }

    async def _update_launch_phase(
        self,
        workspace_id: str,
        new_phase: str,
        exit_criteria_met: List[str],
        exit_criteria_unmet: List[str] = [],
        notes: str = "",
    ) -> Dict[str, Any]:
        """Update launch phase with exit criteria tracking."""
        from datetime import datetime

        valid_phases = list(_LAUNCH_PHASES.keys())
        if new_phase not in valid_phases:
            return {
                "status": "error",
                "message": f"Invalid phase '{new_phase}'. Valid: {valid_phases}",
            }

        # Load existing status
        raw = await self._config.get(workspace_id, "gtm_launch_status")
        if raw:
            try:
                status = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                status = {"history": []}
        else:
            status = {"history": []}

        old_phase = status.get("current_phase", "not_started")
        now = datetime.utcnow().isoformat()

        # Check if advancing without meeting all exit criteria
        warnings = []
        if exit_criteria_unmet:
            warnings.append(
                f"Advancing to {new_phase} with {len(exit_criteria_unmet)} unmet exit criteria: "
                f"{', '.join(exit_criteria_unmet[:3])}"
            )

        # Record transition in history
        if old_phase != new_phase:
            status.setdefault("history", []).append(
                {
                    "from_phase": old_phase,
                    "to_phase": new_phase,
                    "transitioned_at": now,
                    "exit_criteria_met": exit_criteria_met,
                    "exit_criteria_unmet": exit_criteria_unmet,
                    "notes": notes,
                }
            )

        # Update current state
        status["current_phase"] = new_phase
        status["phase_started_at"] = now
        status["exit_criteria_met"] = exit_criteria_met
        status["exit_criteria_unmet"] = exit_criteria_unmet
        status["last_updated"] = now

        await self._config.set(workspace_id, "gtm_launch_status", json.dumps(status))

        logger.info(
            "gtm_phase_updated",
            workspace_id=workspace_id,
            old_phase=old_phase,
            new_phase=new_phase,
            criteria_met=len(exit_criteria_met),
            criteria_unmet=len(exit_criteria_unmet),
        )

        result: Dict[str, Any] = {
            "status": "updated",
            "previous_phase": old_phase,
            "current_phase": new_phase,
            "exit_criteria_met": exit_criteria_met,
            "exit_criteria_unmet": exit_criteria_unmet,
            "workspace_id": workspace_id,
        }
        if warnings:
            result["warnings"] = warnings
        if notes:
            result["notes"] = notes

        return result
