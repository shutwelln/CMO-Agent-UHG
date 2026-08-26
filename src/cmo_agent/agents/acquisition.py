"""Acquisition Agent - funnel architecture, landing page strategy, friction analysis."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo, OpportunityRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# Acquisition quality criteria for RefinementLoop
_ACQUISITION_CRITERIA = [
    QualityCriterion(
        name="funnel_accuracy",
        description="Funnel stages, conversion points, and leakage analysis are specific and data-grounded",
    ),
    QualityCriterion(
        name="actionability",
        description="Recommendations include concrete next steps, not vague suggestions",
    ),
    QualityCriterion(
        name="metric_rigor",
        description="Metrics, benchmarks, and success criteria are precise and measurable",
    ),
    QualityCriterion(
        name="strategic_coherence",
        description="Audit findings, test roadmap, and experiment designs form a coherent optimization strategy",
    ),
    QualityCriterion(
        name="prioritization_clarity",
        description="Quick wins and high-impact items are clearly distinguished from longer-term initiatives",
    ),
]


class AcquisitionAgent(BaseAgent):
    """Handles acquisition funnel architecture, landing page strategy, and friction analysis.

    Identifies WHAT should be optimized and WHY.
    Does NOT design experiments or test plans — hands off to
    conversion_optimization_agent for experiment design and prioritization.
    """

    agent_id = "acquisition_agent"
    agent_name = "Acquisition Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._opportunities = OpportunityRepo(db)
        self._config = ConfigRepo(db)
        self._workspace_mgr = workspace_manager
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Acquisition Agent, a specialist in funnel architecture, landing page strategy, and friction analysis.

Your mission: Map, diagnose, and recommend improvements to the acquisition funnel from traffic to revenue.

You identify WHAT should be optimized and WHY.
You do NOT design experiments or test plans.
When your audit identifies an optimization opportunity, produce a structured recommendation and hand off to the conversion_optimization_agent for experiment design and prioritization.

Your expertise covers:
- Full funnel journey mapping (awareness → traffic → lead → customer → revenue)
- Bottleneck identification and friction point analysis
- Landing page strategy and offer framework design
- Lead generation optimization (forms, CTAs, page flow, exit intent)
- Cart/checkout abandonment recovery strategies
- Funnel metric calculation

KEY METRICS YOU WORK WITH:
- Conversion Rate (CVR) by funnel stage
- Visitor-to-Lead Rate (VTL)
- Lead-to-Customer Rate (LTC)
- Cost per Lead (CPL)
- Customer Acquisition Cost (CAC)
- LTV/CAC Ratio
- Bounce Rate and Exit Rate
- Form Completion Rate
- Time to Conversion
- Cart Abandonment Rate

IMPORTANT RULES:
- All specific benchmark claims MUST be flagged with [VERIFY] prefix
- All strategic plans are saved as drafts for human review
- Focus on post-traffic optimization (what happens after visitors arrive)
- Base recommendations on funnel data, user behavior, and CRO best practices
- Always consider the brand's target audience and value proposition
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels.

SCOPE BOUNDARIES:
- You handle: funnel architecture, funnel mapping, landing page strategy, friction analysis, conversion metric calculation
- GTM Agent defines macro funnel architecture for launches. You own micro funnel optimization — page-level friction analysis, step-by-step journey mapping, and drop-off diagnosis
- Conversion Optimization Agent handles: experiment design, experiment prioritization, A/B test planning, variant briefs, statistical validation, on-page element optimization
- Performance Marketer handles: paid ad channels, campaign architecture, ROAS, budget allocation, ad A/B testing
- Writer Agent handles: actual long-form content creation
- You provide strategic frameworks and recommendations; conversion_optimization_agent designs the experiments to test them

HANDOFF PROTOCOL:
When you identify an optimization opportunity, structure your recommendation as:
- Problem identified
- Recommended change
- Expected impact (directional)
- Suggested metric to test
Then note: "Hand off to conversion_optimization_agent for experiment design."
"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="run_funnel_audit",
            description="Conduct a comprehensive acquisition funnel audit with bottleneck analysis, optimization recommendations with structured handoff to Conversion Optimization Agent, and success criteria.",
        )
        async def run_funnel_audit(
            workspace_id: str,
            funnel_data: str,
            business_context: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Conduct a comprehensive acquisition funnel audit.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
BUSINESS CONTEXT: {business_context}
FUNNEL DATA: {funnel_data}

Structure the audit with these 5 sections:

## 1. Funnel Breakdown
- Map each stage: Awareness → Traffic → Lead → Customer → Revenue
- Current conversion rate at each stage transition
- Volume and velocity at each stage

## 2. Bottleneck Analysis
- Identify the top 3 drop-off points with severity (High/Medium/Low)
- Root cause analysis for each (UX, copy, offer, trust, technical)
- Data signals supporting each finding

## 3. Test Roadmap
- Prioritized list of 5-8 experiments ordered by potential impact
- Each with ICE score (Impact 1-10, Confidence 1-10, Ease 1-10)
- Timeline: quick wins (1-2 weeks) vs. strategic tests (1-3 months)

## 4. Experiment Designs
- Top 3 experiments with full design:
  - Hypothesis (If we [change], then [metric] will [improve] because [rationale])
  - Control vs. Variant description
  - Primary and secondary metrics
  - Sample size and duration estimate

## 5. Success Criteria and Metrics
- North star metric for the funnel
- Stage-specific KPIs with target values
- Measurement framework and tracking requirements

Flag all benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_ACQUISITION_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="acquisition_audit_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="funnel_audit",
                title=f"Funnel Audit: {workspace_id}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Funnel Audit: {workspace_id}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="map_acquisition_funnel",
            description="Create a comprehensive acquisition funnel map with stage breakdown, leakage analysis, and quick wins.",
        )
        async def map_acquisition_funnel(
            workspace_id: str,
            funnel_stages: Optional[List[str]] = None,
            current_metrics: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            stages_str = (
                ", ".join(funnel_stages)
                if funnel_stages
                else "awareness → traffic → lead → customer → revenue"
            )
            metrics_str = (
                current_metrics or "No baseline metrics provided — use industry benchmarks [VERIFY]"
            )

            prompt = f"""Create a comprehensive acquisition funnel map.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
FUNNEL STAGES: {stages_str}
CURRENT METRICS: {metrics_str}

Structure the funnel map as:
1. **Funnel Overview** — High-level journey from first touch to revenue
2. **Stage Breakdown** — For each stage: definition, key actions, current metrics, benchmarks [VERIFY]
3. **Critical Conversion Points** — Make-or-break moments
4. **Leakage Analysis** — Where prospects drop off and likely reasons
5. **Data Gaps** — What tracking/metrics are needed
6. **Quick Wins** — Immediate optimization opportunities"""

            config = RefinementConfig(
                criteria=_ACQUISITION_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="acquisition_funnel_map_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="acquisition_funnel_map",
                title=f"Acquisition Funnel Map: {workspace_id}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Acquisition Funnel Map: {workspace_id}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="identify_friction_points",
            description="Analyze funnel data to identify friction points causing drop-offs with severity and recommendations.",
        )
        async def identify_friction_points(
            workspace_id: str,
            funnel_data: str,
            stage_to_analyze: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Analyze the following funnel data and identify friction points causing drop-offs.

BRAND CONTEXT: {brand_voice[:300] if brand_voice else "No brand voice configured."}
FUNNEL DATA: {funnel_data}
STAGE TO ANALYZE: {stage_to_analyze or "all stages"}

For each friction point provide:
- Stage: Where in the funnel
- Issue: What's causing friction
- Severity: High/Medium/Low
- Evidence: Data signals
- Root Cause: UX, copy, offer, trust, or technical
- Recommendation: Specific fix

Return as JSON: {{"friction_points": [...], "most_critical": "...", "quick_wins": [...]}}"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.5,
            )

            try:
                result = json.loads(response.content)
            except json.JSONDecodeError:
                result = {
                    "friction_points": [],
                    "most_critical": response.content[:200],
                    "quick_wins": [],
                    "raw_analysis": response.content,
                }

            return result

        @self.tool_registry.register(
            name="recommend_landing_page_optimization",
            description="Recommend a landing page optimization framework with above-the-fold design, conversion elements, CTA strategy, and A/B test opportunities.",
        )
        async def recommend_landing_page_optimization(
            workspace_id: str,
            page_goal: str,
            target_audience: str,
            current_page_description: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Recommend a landing page optimization framework.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
PAGE GOAL: {page_goal}
TARGET AUDIENCE: {target_audience}
CURRENT PAGE: {current_page_description or "New page — no existing version"}

Structure:
1. Landing Page Strategy — approach for this goal/audience
2. Above-the-Fold Framework — headline formula, subhead, hero image/video, primary CTA
3. Page Structure — section-by-section flow
4. Conversion Elements — trust signals, social proof, guarantees, urgency
5. CTA Strategy — primary/secondary CTAs, copy formulas
6. Offer Framework — value prop positioning
7. Objection Handling — common objections addressed on-page
8. Mobile Optimization — responsive considerations
9. A/B Test Opportunities — highest-impact elements to test first"""

            config = RefinementConfig(
                criteria=_ACQUISITION_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="acquisition_landing_page_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Landing Page Plan: {page_goal}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="landing_page_plan",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="calculate_funnel_metrics",
            description="Calculate key funnel metrics from raw numbers. Pure math, no LLM needed.",
        )
        async def calculate_funnel_metrics(
            visitors: int,
            leads: int = 0,
            customers: int = 0,
            revenue: float = 0.0,
            spend: float = 0.0,
        ) -> Dict[str, Any]:
            metrics: Dict[str, Any] = {"visitors": visitors}

            if leads > 0:
                metrics["leads"] = leads
                metrics["visitor_to_lead_rate"] = round(leads / visitors * 100, 2)

            if customers > 0:
                metrics["customers"] = customers
                if leads > 0:
                    metrics["lead_to_customer_rate"] = round(customers / leads * 100, 2)
                metrics["overall_cvr"] = round(customers / visitors * 100, 2)

            if spend > 0:
                metrics["spend"] = spend
                if leads > 0:
                    metrics["cpl"] = round(spend / leads, 2)
                if customers > 0:
                    metrics["cac"] = round(spend / customers, 2)

            if revenue > 0:
                metrics["revenue"] = revenue
                metrics["revenue_per_visitor"] = round(revenue / visitors, 2)
                if customers > 0:
                    cac = spend / customers if spend > 0 and customers > 0 else 0
                    if cac > 0:
                        ltv = revenue / customers
                        metrics["ltv_cac_ratio"] = round(ltv / cac, 2)

            return metrics
