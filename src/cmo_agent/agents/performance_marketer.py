"""Performance Marketer Agent - paid advertising, conversion optimization, ROI analysis."""

from __future__ import annotations

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

# Performance marketer quality criteria
_PERF_CRITERIA = [
    QualityCriterion(
        name="specificity",
        description="Specific, detailed recommendations rather than generic advice",
    ),
    QualityCriterion(
        name="actionability",
        description="Immediately actionable steps with clear implementation guidance",
    ),
    QualityCriterion(
        name="metric_rigor",
        description="Metrics properly defined, benchmarks cited, KPIs measurable",
    ),
    QualityCriterion(
        name="platform_alignment",
        description="Recommendations aligned with platform capabilities and best practices",
    ),
    QualityCriterion(
        name="budget_justification",
        description="Budget decisions justified with rationale and expected ROI",
    ),
]


class PerformanceMarketerAgent(BaseAgent):
    """Handles paid advertising strategy, campaign architecture, and performance analysis."""

    agent_id = "performance_marketer_agent"
    agent_name = "Performance Marketer Agent"

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
        return """You are the Performance Marketer Agent, a specialist in paid advertising and conversion optimization.

Your expertise covers:
- Paid advertising across platforms (Google Ads, Meta Ads, LinkedIn Ads, TikTok Ads)
- Conversion rate optimization (CRO) and funnel analysis
- ROI analysis and attribution modeling
- A/B testing strategy and statistical significance
- Budget allocation and bid strategy optimization
- Campaign architecture and audience segmentation

KEY METRICS YOU WORK WITH:
- ROAS (Return on Ad Spend)
- CPA (Cost per Acquisition)
- CTR (Click-Through Rate)
- CVR (Conversion Rate)
- LTV (Lifetime Value)
- CAC (Customer Acquisition Cost)
- CPM (Cost per Mille)

SCOPE BOUNDARY (CONVERSION OPTIMIZATION):
- On-site conversion testing (headlines, CTAs, layouts, offers, page elements)
  is owned by the Conversion Optimization Agent.
- You own A/B testing for paid ad campaigns (creative, audiences, bid strategies,
  ad copy, landing page selection within campaign context).
- If a request is about on-page conversion mechanics or experiment design for
  on-site elements, it should be routed to conversion_optimization_agent.

IMPORTANT RULES:
- All specific performance claims MUST be flagged with [VERIFY] prefix
- All strategic plans are saved as drafts for human review
- Base recommendations on data and industry benchmarks
- Always consider the brand's target audience and voice
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="analyze_campaign_performance",
            description="Analyze campaign performance data and provide optimization recommendations.",
        )
        async def analyze_campaign_performance(
            workspace_id: str,
            campaign_data: str,
            platform: str = "general",
            goal: str = "conversions",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Analyze the following campaign performance data and provide actionable recommendations.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

PLATFORM: {platform}
CAMPAIGN GOAL: {goal}

CAMPAIGN DATA:
{campaign_data}

Provide your analysis in these sections:
1. **Performance Summary** — Key metrics and how they compare to benchmarks
2. **What's Working** — Strengths to double down on
3. **What Needs Improvement** — Underperforming areas with specific fixes
4. **Optimization Recommendations** — Prioritized action items
5. **Budget Reallocation Suggestions** — Where to shift spend

Flag any specific benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            return {
                "analysis": response.content,
                "platform": platform,
                "goal": goal,
            }

        @self.tool_registry.register(
            name="create_ab_test_plan",
            description="Create a structured A/B test plan with hypothesis, variants, and success criteria.",
        )
        async def create_ab_test_plan(
            workspace_id: str,
            test_subject: str,
            element_to_test: str,
            hypothesis: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a detailed A/B test plan.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

TEST SUBJECT: {test_subject}
ELEMENT TO TEST: {element_to_test}
HYPOTHESIS: {hypothesis}

Structure the plan as:
1. **Test Name & Objective**
2. **Hypothesis** (formalized as: If we [change], then [metric] will [direction] because [rationale])
3. **Control (A)** — Current version description
4. **Variant (B)** — Proposed change description
5. **Primary Metric** — What defines success
6. **Secondary Metrics** — Supporting measurements
7. **Sample Size & Duration** — Statistical requirements
8. **Audience Segmentation** — Who to include/exclude
9. **Success Criteria** — Minimum detectable effect
10. **Rollout Plan** — What happens if the variant wins

Flag any statistical benchmarks with [VERIFY]."""

            config = RefinementConfig(
                criteria=_PERF_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="perf_ab_test_refinement",
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
                content_type="ab_test_plan",
                title=f"A/B Test: {test_subject}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"A/B Test: {test_subject}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="create_budget_allocation",
            description="Create a budget allocation plan across platforms and campaigns.",
        )
        async def create_budget_allocation(
            workspace_id: str,
            total_budget: str,
            platforms: List[str],
            goals: str,
            timeframe: str = "monthly",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a performance marketing budget allocation plan.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

TOTAL BUDGET: {total_budget}
PLATFORMS: {", ".join(platforms)}
CAMPAIGN GOALS: {goals}
TIMEFRAME: {timeframe}

Structure the plan as:
1. **Budget Overview** — Total spend and timeframe
2. **Platform Allocation** — % and dollar amount per platform with rationale
3. **Campaign Type Split** — Prospecting vs. retargeting vs. brand awareness
4. **Funnel Stage Budget** — Top/Mid/Bottom of funnel allocation
5. **Testing Budget** — Amount reserved for experimentation (recommend 10-20%)
6. **Scaling Triggers** — KPIs that signal when to increase/decrease spend
7. **Monthly Pacing** — How to distribute spend across the period
8. **Risk Mitigation** — Contingency plans for underperformance

Flag any industry benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="budget_plan",
                title=f"Budget Allocation: {total_budget} ({timeframe})",
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Budget Allocation: {total_budget} ({timeframe})",
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="design_campaign_structure",
            description="Design a campaign structure with ad groups, targeting, and creative strategy.",
        )
        async def design_campaign_structure(
            workspace_id: str,
            platform: str,
            objective: str,
            target_audience: str,
            budget: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Design a complete campaign structure for paid advertising.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

PLATFORM: {platform}
OBJECTIVE: {objective}
TARGET AUDIENCE: {target_audience}
BUDGET: {budget}

Structure the plan as:
1. **Campaign Overview** — Name, objective, platform settings
2. **Campaign Architecture** — Campaign > Ad Set/Group > Ad hierarchy
3. **Audience Strategy** — Targeting layers (demographics, interests, behaviors, custom/lookalike)
4. **Ad Creative Strategy** — Format recommendations, messaging angles, CTA variants
5. **Bidding Strategy** — Bid type, cap recommendations, optimization events
6. **Landing Page Requirements** — Key elements for conversion
7. **Tracking & Attribution** — Pixels, UTMs, conversion events to set up
8. **Launch Checklist** — Pre-launch verification steps
9. **Optimization Schedule** — When and what to check post-launch

Flag any platform-specific recommendations with [VERIFY] if they may change."""

            config = RefinementConfig(
                criteria=_PERF_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="perf_campaign_refinement",
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
                content_type="campaign_plan",
                title=f"Campaign: {objective} on {platform}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Campaign: {objective} on {platform}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="calculate_marketing_metrics",
            description="Calculate key marketing metrics from raw numbers. Pure math, no LLM needed.",
        )
        async def calculate_marketing_metrics(
            spend: float,
            revenue: float = 0.0,
            impressions: int = 0,
            clicks: int = 0,
            conversions: int = 0,
        ) -> Dict[str, Any]:
            metrics: Dict[str, Any] = {"spend": spend}

            if revenue > 0:
                metrics["revenue"] = revenue
                metrics["roas"] = round(revenue / spend, 2) if spend > 0 else 0
                metrics["profit"] = round(revenue - spend, 2)

            if impressions > 0:
                metrics["impressions"] = impressions
                metrics["cpm"] = round((spend / impressions) * 1000, 2) if spend > 0 else 0

            if clicks > 0:
                metrics["clicks"] = clicks
                metrics["cpc"] = round(spend / clicks, 2) if spend > 0 else 0
                if impressions > 0:
                    metrics["ctr"] = round((clicks / impressions) * 100, 2)

            if conversions > 0:
                metrics["conversions"] = conversions
                metrics["cpa"] = round(spend / conversions, 2) if spend > 0 else 0
                if clicks > 0:
                    metrics["cvr"] = round((conversions / clicks) * 100, 2)

            return metrics
