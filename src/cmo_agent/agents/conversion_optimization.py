"""Conversion Rate Optimization & Experimentation Architect Agent."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# CRO quality criteria for RefinementLoop
_CRO_CRITERIA = [
    QualityCriterion(
        name="hypothesis_rigor",
        description="Hypotheses are specific, measurable, and falsifiable with clear causal reasoning",
    ),
    QualityCriterion(
        name="statistical_validity",
        description="Sample sizes, confidence levels, and MDE are appropriate for the test context",
    ),
    QualityCriterion(
        name="variant_clarity",
        description="Control and variant descriptions are specific enough for a designer or developer to implement",
    ),
    QualityCriterion(
        name="risk_assessment",
        description="Risk levels, guardrails, and rollback plans are thorough and realistic",
    ),
    QualityCriterion(
        name="decision_framework",
        description="Ship/iterate/kill decisions are grounded in data with clear criteria",
    ),
]

# ── Default optimization areas (universal across verticals) ──────────
# These are the baseline. The agent discovers site-specific areas via
# discover_conversion_architecture and stores them per workspace.

_UNIVERSAL_OPTIMIZATION_AREAS = [
    "Headline framing",
    "Value proposition clarity",
    "CTA copy",
    "CTA placement",
    "Button color and prominence",
    "Social proof placement",
    "Page length and scannability",
    "Trust signals",
    "FAQ placement impact",
    "Email / lead capture timing",
]


class ConversionOptimizationAgent(BaseAgent):
    """Systematically increases conversion efficiency, revenue per visitor,
    and user activation across products.

    This agent is the experimentation authority for the entire CMO ecosystem.
    No other agent designs experiments without this agent's oversight.

    VERTICAL-AGNOSTIC: This agent does not assume any specific business model.
    On first engagement with a workspace, it discovers the site's conversion
    architecture (page types, revenue mechanics, conversion events, on-page
    elements) and calibrates its optimization areas accordingly. All context
    is persisted per workspace via the config store.

    Owns:
    - On-page conversion mechanics
    - Experiment design (hypothesis, variants, success criteria, rollout)
    - Experiment prioritization and backlog management
    - Statistical validation standards
    - CTA architecture and offer presentation logic
    - Variant brief creation for Writer Agent
    - Tracking requirements definition for Experiment Engineer / Sales Ops
    - Cross-agent experimentation governance

    Does NOT own:
    - ICP definition or positioning (GTM Orchestrator)
    - Traffic acquisition (GTM Orchestrator / Performance Marketer)
    - Funnel architecture and mapping (Acquisition Agent)
    - Page taxonomy or URL structure (SEO/AEO Agent)
    - Experiment lifecycle persistence (Experiment Engineer Agent)
    - Measurement infrastructure (Marketing Analytics Agent)
    - Content writing (Writer Agent)
    - Ad campaign A/B tests (Performance Marketer Agent)
    """

    agent_id = "conversion_optimization_agent"
    agent_name = "Conversion Rate Optimization & Experimentation Architect"

    # Config key for persisted conversion context per workspace
    _CONVERSION_CONTEXT_KEY = "conversion_optimization_context"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 12,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._config = ConfigRepo(db)
        self._workspace_mgr = workspace_manager
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    # ── Context helpers ──────────────────────────────────────────────────

    async def _get_conversion_context(self, workspace_id: str) -> Optional[Dict[str, Any]]:
        """Load persisted conversion context for this workspace."""
        raw = await self._config.get(workspace_id, self._CONVERSION_CONTEXT_KEY)
        if raw:
            try:
                return json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    async def _save_conversion_context(self, workspace_id: str, context: Dict[str, Any]) -> None:
        """Persist conversion context for this workspace."""
        await self._config.set(workspace_id, self._CONVERSION_CONTEXT_KEY, json.dumps(context))

    def _format_conversion_context(self, ctx: Optional[Dict[str, Any]]) -> str:
        """Format discovered conversion context for injection into prompts."""
        if not ctx:
            return (
                "NO CONVERSION CONTEXT DISCOVERED YET.\n"
                "Using universal optimization areas. Run discover_conversion_architecture "
                "to calibrate for this specific site/product."
            )

        sections = []
        if ctx.get("vertical"):
            sections.append(f"VERTICAL: {ctx['vertical']}")
        if ctx.get("business_model"):
            sections.append(f"BUSINESS MODEL: {ctx['business_model']}")
        if ctx.get("revenue_mechanics"):
            sections.append(f"REVENUE MECHANICS: {', '.join(ctx['revenue_mechanics'])}")
        if ctx.get("page_types"):
            sections.append(f"PAGE TYPES: {', '.join(ctx['page_types'])}")
        if ctx.get("conversion_events"):
            sections.append(f"CONVERSION EVENTS: {', '.join(ctx['conversion_events'])}")
        if ctx.get("optimization_areas"):
            numbered = [f"  {i + 1}. {a}" for i, a in enumerate(ctx["optimization_areas"])]
            sections.append(f"OPTIMIZATION AREAS:\n" + "\n".join(numbered))
        if ctx.get("key_metrics"):
            sections.append(f"KEY METRICS: {', '.join(ctx['key_metrics'])}")
        if ctx.get("tech_stack"):
            sections.append(f"TECH STACK: {ctx['tech_stack']}")
        if ctx.get("notes"):
            sections.append(f"NOTES: {ctx['notes']}")

        return "\n".join(sections)

    async def _get_full_context(self, workspace_id: str) -> tuple[str, str, str]:
        """Return brand voice, reference docs summary, and conversion context."""
        brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
        conversion_ctx = await self._get_conversion_context(workspace_id)
        ctx_text = self._format_conversion_context(conversion_ctx)

        # Also load reference docs if available for additional context
        try:
            ref_docs = await self._workspace_mgr.get_reference_docs(workspace_id)
        except Exception:
            ref_docs = ""

        return brand_voice or "", ref_docs or "", ctx_text

    def _get_optimization_areas(self, ctx: Optional[Dict[str, Any]]) -> List[str]:
        """Return optimization areas — discovered if available, universal otherwise."""
        if ctx and ctx.get("optimization_areas"):
            return ctx["optimization_areas"]
        return list(_UNIVERSAL_OPTIMIZATION_AREAS)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Conversion Rate Optimization and Experimentation Architect for the CMO Agent ecosystem.

Your sole responsibility is to systematically increase conversion efficiency, revenue per visitor, and user activation across products.

You do not define ICP.
You do not define positioning.
You do not own traffic acquisition.
You optimize what happens after traffic arrives.

You operate under strategic direction from the GTM Orchestrator.
You collaborate with SEO/AEO, Writer, Sales Ops, Analytics, and Engineering.

--------------------------------------------------
VERTICAL-AGNOSTIC OPERATION
--------------------------------------------------

You do NOT assume any specific business model, vertical, or site structure.

When you first engage with a workspace, use discover_conversion_architecture
to learn:
- What the site/product does
- What page types exist
- How revenue is generated
- What conversion events matter
- What on-page elements are testable

This discovery is persisted per workspace. All subsequent tools automatically
use the discovered context. If no context exists, you operate on universal
optimization principles and flag that discovery should be run.

You learn from what you are given. You adapt to the vertical.

--------------------------------------------------
ROLE BOUNDARIES
--------------------------------------------------

GTM Orchestrator owns:
- ICP
- Positioning
- Channel mix
- Economic targets

SEO and AEO Architect owns:
- Search architecture
- Page structure standards
- Schema and entity clarity

Acquisition Agent owns:
- Funnel architecture and mapping
- Landing page conversion strategy
- Page-level conversion audits
- Friction identification
- Conversion metric calculation

Experiment Engineer Agent owns:
- Experiment lifecycle persistence (create, track, record readouts)
- Event schema management

Performance Marketer Agent owns:
- Ad campaign A/B tests (creative, audiences, bid strategies)

Marketing Analytics Agent owns:
- Measurement infrastructure (GA4, UTM, attribution)

You own:
- On-page conversion mechanics
- CTA architecture
- Offer presentation logic
- Placement testing
- A/B and multivariate test design for on-site elements
- Experiment prioritization
- Statistical validation standards
- Cross-agent experimentation governance

No other agent designs experiments without your oversight.

--------------------------------------------------
PRIMARY OBJECTIVES
--------------------------------------------------

1. Increase conversion rate by page type
2. Increase revenue per session
3. Increase primary lead capture rate
4. Increase monetization event rate (clicks, sign-ups, purchases — varies by vertical)
5. Improve activation to repeat visit rate
6. Design scalable experimentation systems

--------------------------------------------------
EXPERIMENTATION FRAMEWORK
--------------------------------------------------

For every experiment you must define:

- Hypothesis
- Target page type
- Primary metric
- Secondary metrics
- Expected impact
- Risk level
- Required traffic threshold
- Success criteria
- Rollout plan

No experiment may launch without defined success metrics.

--------------------------------------------------
TEST PRIORITIZATION MODEL
--------------------------------------------------

You score experiments using:

- Impact potential (1-10)
- Confidence level (1-10)
- Traffic volume available
- Implementation complexity (1-10, inverted as ease)
- Revenue upside estimate

You maintain an experimentation backlog ranked by expected ROI.

--------------------------------------------------
ECOSYSTEM INTEGRATION
--------------------------------------------------

You replace no existing agent. You are additive.

HANDOFF PROTOCOLS:
- When designing an experiment, produce the full spec, then hand off to
  experiment_engineer_agent for lifecycle tracking (create_experiment tool).
- When needing copy variants, produce a structured variant brief, then
  hand off to writer_agent for execution.
- When needing new tracking events, produce event definitions, then
  hand off to experiment_engineer_agent (define_event tool).
- When results need statistical validation, request from
  marketing_analytics_agent.
- When conversion audit data is needed, request from acquisition_agent.
- When tracking events need implementation, coordinate with sales_ops_agent
  (revenue ops) for attribution integrity.

--------------------------------------------------
COLLABORATION RULES
--------------------------------------------------

With GTM Orchestrator:
- Align experiments to defined economic targets
- Ensure experiments support strategic goals

With SEO and AEO Architect:
- Do not alter core page taxonomy
- Do not break schema integrity
- Coordinate before structural layout changes

With Acquisition Agent:
- Receive conversion audits and friction analysis as input
- Do not duplicate funnel mapping or metric calculation
- Your experiments address issues the acquisition agent identifies

With Writer:
- Issue structured variant briefs
- Require benefit-driven copy
- Define tone adjustments tied to hypothesis

With Sales Ops (Revenue Ops):
- Define tracking events
- Validate attribution integrity
- Ensure experiment tagging standards

With Marketing Analytics:
- Validate statistical significance
- Monitor experiment contamination
- Track long-term lift, not just short-term spikes

With Experiment Engineer:
- Hand off experiment specs for lifecycle persistence
- Hand off event definitions for schema registry
- Do not persist experiments directly

--------------------------------------------------
DECISION STANDARD
--------------------------------------------------

Every recommendation must answer:

- Does this increase revenue per visitor?
- Does this improve activation quality?
- Does this reduce friction?
- Is the lift statistically defensible?
- Does this scale across page types?

If not, it is not prioritized.

IMPORTANT RULES:
- All specific benchmark claims MUST be flagged with [VERIFY] prefix
- All strategic deliverables are saved as drafts for human review
- You are systematic, evidence-driven, and economically disciplined
- You optimize systems, not opinions
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels."""

    def register_tools(self) -> None:
        # ── discover_conversion_architecture ──────────────────────────
        @self.tool_registry.register(
            name="discover_conversion_architecture",
            description=(
                "Discover and persist the conversion architecture for a workspace. "
                "Given a site description, URL context, or product description, this tool "
                "identifies page types, revenue mechanics, conversion events, testable "
                "on-page elements, and key metrics. Stores the result per workspace so "
                "all other tools automatically calibrate. Run this first for any new site."
            ),
        )
        async def discover_conversion_architecture(
            workspace_id: str,
            site_description: str,
            url: Optional[str] = None,
            known_page_types: Optional[List[str]] = None,
            known_revenue_model: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            # Load reference docs — they often contain the best context
            try:
                ref_docs = await self._workspace_mgr.get_reference_docs(workspace_id)
            except Exception:
                ref_docs = ""

            known_pages_text = ", ".join(known_page_types) if known_page_types else "Not provided"
            known_rev_text = known_revenue_model or "Not provided"

            prompt = f"""Analyze this site/product and map its complete conversion architecture.

SITE DESCRIPTION: {site_description}
{f"URL: {url}" if url else ""}
KNOWN PAGE TYPES: {known_pages_text}
KNOWN REVENUE MODEL: {known_rev_text}

{f"BRAND CONTEXT:{chr(10)}{brand_voice[:500]}" if brand_voice else ""}
{f"REFERENCE DOCUMENTS:{chr(10)}{ref_docs[:6000]}" if ref_docs else ""}

Based on everything provided, produce a structured analysis. You must INFER what
you are not told based on the site description, brand context, and reference
documents. Be specific — do not give generic answers.

Return STRICT JSON with these keys:

{{
  "vertical": "<industry vertical: e.g., marketplace, SaaS, ecommerce, B2B services, media/publishing, fintech, healthcare, education, nonprofit, etc.>",
  "business_model": "<how the business makes money: e.g., affiliate commissions, subscriptions, one-time purchases, lead gen fees, advertising, donations, etc.>",
  "revenue_mechanics": ["<specific revenue event 1>", "<specific revenue event 2>", ...],
  "page_types": ["<page type 1>", "<page type 2>", ...],
  "conversion_events": ["<primary conversion>", "<secondary conversion>", ...],
  "optimization_areas": [
    "<site-specific area 1: e.g., 'Product card layout' or 'Merchant card layout' or 'Pricing table clarity'>",
    "<site-specific area 2>",
    "... (10-18 areas total, mix of universal and site-specific)"
  ],
  "key_metrics": ["<metric 1>", "<metric 2>", ...],
  "tech_stack": "<inferred or stated tech stack>",
  "primary_cta_types": ["<CTA type 1: e.g., 'Get Quote', 'Add to Cart', 'Start Free Trial'>", ...],
  "monetization_elements": ["<element 1: e.g., 'affiliate links', 'checkout flow', 'subscription gate'>", ...],
  "personalization_dimensions": ["<dimension 1: e.g., 'geographic', 'user segment', 'device type'>", ...],
  "notes": "<any important context for future experiments>"
}}

RULES:
- optimization_areas MUST include universal areas (headline, CTA, social proof, trust signals, scannability) PLUS site-specific areas derived from the business model
- Do NOT use generic placeholders. Every value must be specific to THIS site.
- If the site is a marketplace, include areas like card layout, offer comparison, geographic filtering
- If SaaS, include pricing table, feature comparison, onboarding flow, trial-to-paid conversion
- If ecommerce, include product imagery, cart flow, shipping messaging, review placement
- If B2B, include demo request flow, case study placement, ROI calculator
- If media/publishing, include paywall placement, newsletter capture, content gate
- Infer what you can. Flag uncertainty with [INFERRED] prefix."""

            config = RefinementConfig(
                criteria=_CRO_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="cro_discovery_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)

            # Parse and persist
            content = result.content.strip()
            if content.startswith("```"):
                import re

                content = re.sub(r"^```(?:json)?\s*\n?", "", content)
                content = re.sub(r"\n?```\s*$", "", content)

            try:
                ctx = json.loads(content)
            except (json.JSONDecodeError, TypeError):
                ctx = {
                    "raw_discovery": content,
                    "optimization_areas": list(_UNIVERSAL_OPTIMIZATION_AREAS),
                }

            await self._save_conversion_context(workspace_id, ctx)

            logger.info(
                "conversion_context_discovered",
                workspace_id=workspace_id,
                vertical=ctx.get("vertical"),
                page_types=ctx.get("page_types"),
                optimization_area_count=len(ctx.get("optimization_areas", [])),
            )

            return {
                "status": "discovered",
                "workspace_id": workspace_id,
                "conversion_context": ctx,
                "optimization_area_count": len(ctx.get("optimization_areas", [])),
                "note": "Context persisted. All tools will now use this context automatically.",
            }

        # ── design_experiment ────────────────────────────────────────
        @self.tool_registry.register(
            name="design_experiment",
            description=(
                "Design a complete on-site conversion experiment with all 9 required fields: "
                "hypothesis, target page type, primary metric, secondary metrics, expected impact, "
                "risk level, required traffic threshold, success criteria, and rollout plan. "
                "Automatically uses discovered conversion context for the workspace."
            ),
        )
        async def design_experiment(
            workspace_id: str,
            hypothesis: str,
            target_page_type: str,
            primary_metric: str,
            optimization_area: str,
            current_performance: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice, ref_docs, ctx_text = await self._get_full_context(workspace_id)

            prompt = f"""Design a complete on-site conversion experiment.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

CONVERSION CONTEXT:
{ctx_text}

HYPOTHESIS: {hypothesis}
TARGET PAGE TYPE: {target_page_type}
PRIMARY METRIC: {primary_metric}
OPTIMIZATION AREA: {optimization_area}
CURRENT PERFORMANCE: {current_performance or "No baseline provided"}

You MUST structure the experiment with ALL of these sections:

1. **Experiment Name** — descriptive, following pattern: [page_type]_[element]_[variant_description]
2. **Hypothesis** — formalized: "If we [change], then [metric] will [direction] because [rationale]"
3. **Target Page Type** — which pages this applies to and estimated traffic volume
4. **Primary Metric** — the single metric that determines success
5. **Secondary Metrics** — 2-4 supporting metrics to monitor
6. **Expected Impact** — estimated lift range with confidence interval
7. **Risk Level** — low/medium/high with explanation of what could go wrong
8. **Required Traffic Threshold** — minimum sample size per variant for statistical significance (95% confidence, 80% power)
9. **Success Criteria** — minimum detectable effect, confidence level, duration
10. **Rollout Plan** — what happens if variant wins (partial rollout, full rollout, iteration)
11. **Control Description** — current state
12. **Variant Description** — proposed change with rationale
13. **Guardrail Metrics** — metrics that must NOT degrade
14. **Implementation Notes** — technical requirements for clean experiment isolation

Return as structured JSON with keys matching the section names (snake_case).
Flag any benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_CRO_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="cro_experiment_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Experiment: {target_page_type} — {optimization_area}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="conversion_experiment",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
                "next_step": "Hand off to experiment_engineer_agent for lifecycle tracking",
            }

        # ── prioritize_experiment_backlog ─────────────────────────────
        @self.tool_registry.register(
            name="prioritize_experiment_backlog",
            description=(
                "Score and rank an experiment backlog using impact potential, confidence, "
                "traffic volume, implementation complexity, and revenue upside. "
                "Returns a prioritized list with reasoning."
            ),
        )
        async def prioritize_experiment_backlog(
            workspace_id: str,
            experiments: List[Dict[str, Any]],
        ) -> Dict[str, Any]:
            scored: List[Dict[str, Any]] = []

            for exp in experiments:
                name = exp.get("name", "Unnamed")
                impact = exp.get("impact_potential", 5)
                confidence = exp.get("confidence", 5)
                traffic = exp.get("traffic_volume", 5)
                complexity = exp.get("implementation_complexity", 5)
                revenue_upside = exp.get("revenue_upside", 5)

                ease = 11 - complexity  # invert: low complexity = high ease
                score = round(
                    (
                        impact * 0.30
                        + confidence * 0.20
                        + traffic * 0.15
                        + ease * 0.15
                        + revenue_upside * 0.20
                    ),
                    2,
                )

                scored.append(
                    {
                        "name": name,
                        "score": score,
                        "impact_potential": impact,
                        "confidence": confidence,
                        "traffic_volume": traffic,
                        "implementation_complexity": complexity,
                        "revenue_upside": revenue_upside,
                    }
                )

            scored.sort(key=lambda x: x["score"], reverse=True)
            for i, item in enumerate(scored):
                item["rank"] = i + 1

            # LLM reasoning for top 3
            reasoning_prompt = f"""Given these top prioritized experiments (weighted scoring: impact 30%, confidence 20%, traffic 15%, ease 15%, revenue upside 20%):
{json.dumps(scored[:3], indent=2)}

Provide 1-2 sentence reasoning for each ranking. Return as JSON: {{"top_reasoning": [{{"name": "...", "reasoning": "..."}}]}}"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=reasoning_prompt)],
                temperature=0.3,
            )

            try:
                reasoning = json.loads(response.content)
                top_reasoning = reasoning.get("top_reasoning", [])
            except json.JSONDecodeError:
                top_reasoning = [
                    {"name": s["name"], "reasoning": "See scores."} for s in scored[:3]
                ]

            return {
                "prioritized_backlog": scored,
                "scoring_weights": {
                    "impact_potential": 0.30,
                    "confidence": 0.20,
                    "traffic_volume": 0.15,
                    "ease": 0.15,
                    "revenue_upside": 0.20,
                },
                "top_reasoning": top_reasoning,
            }

        # ── optimize_page_element ────────────────────────────────────
        @self.tool_registry.register(
            name="optimize_page_element",
            description=(
                "Analyze and recommend optimization for a specific on-page element. "
                "Uses discovered conversion context to tailor recommendations to this "
                "specific site's vertical, business model, and page types."
            ),
        )
        async def optimize_page_element(
            workspace_id: str,
            element_type: str,
            current_state: str,
            page_type: str,
            target_metric: str,
        ) -> Dict[str, Any]:
            brand_voice, ref_docs, ctx_text = await self._get_full_context(workspace_id)

            prompt = f"""Analyze and recommend optimization for an on-page conversion element.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

CONVERSION CONTEXT:
{ctx_text}

ELEMENT TYPE: {element_type}
CURRENT STATE: {current_state}
PAGE TYPE: {page_type}
TARGET METRIC: {target_metric}

Structure your analysis as:

1. **Current State Assessment** — what's working and what's not, with evidence-based reasoning
2. **Optimization Hypothesis** — formalized: "If we [change], then [metric] will [direction] because [rationale]"
3. **Recommended Variants** — 2-3 specific alternatives, each with:
   - The exact change
   - Why it should convert better (psychological principle or data pattern)
   - Expected impact (directional: low/medium/high)
4. **Experiment Design** — how to test the recommended variants:
   - Test type (A/B or multivariate)
   - Primary metric
   - Minimum sample size estimate
   - Duration estimate
5. **Implementation Priority** — where this ranks against other potential optimizations on this page type
6. **Cross-Page-Type Scalability** — can this optimization be applied to other page types?

Flag any benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_CRO_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="cro_page_element_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Page Element Optimization: {element_type} on {page_type}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="page_element_optimization",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        # ── create_variant_brief ─────────────────────────────────────
        @self.tool_registry.register(
            name="create_variant_brief",
            description=(
                "Create a structured copy variant brief for the Writer Agent. "
                "Ties tone adjustments to the experiment hypothesis and defines "
                "exact deliverables expected from the Writer."
            ),
        )
        async def create_variant_brief(
            workspace_id: str,
            experiment_hypothesis: str,
            element_type: str,
            variant_count: int,
            current_copy: str,
            tone_direction: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice, ref_docs, ctx_text = await self._get_full_context(workspace_id)

            prompt = f"""Create a structured copy variant brief for the Writer Agent.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

CONVERSION CONTEXT:
{ctx_text}

EXPERIMENT HYPOTHESIS: {experiment_hypothesis}
ELEMENT TYPE: {element_type}
NUMBER OF VARIANTS NEEDED: {variant_count}
CURRENT COPY: {current_copy}
TONE DIRECTION: {tone_direction or "Maintain brand voice; adjust as hypothesis requires"}

Structure the brief as:

1. **Brief Context** — what experiment this supports and why
2. **Current Copy** — the control version
3. **Variant Requirements** — for each variant:
   - Variant label (B, C, D...)
   - Direction: what to change and why (tied to hypothesis)
   - Tone adjustment: specific tonal shift from current
   - Length constraint: character/word limit
   - Must include: required elements (benefit, CTA verb, urgency, etc.)
   - Must avoid: prohibited elements
4. **Quality Criteria** — what makes a good variant for this test
5. **Deliverable Format** — exact format the Writer should return

This brief will be handed to the Writer Agent. Make it machine-readable and unambiguous.

Return as structured JSON."""

            config = RefinementConfig(
                criteria=_CRO_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="cro_variant_brief_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Variant Brief: {element_type} — {variant_count} variants"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="variant_brief",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
                "next_step": "Hand off to writer_agent for copy variant execution",
            }

        # ── define_tracking_requirements ──────────────────────────────
        @self.tool_registry.register(
            name="define_tracking_requirements",
            description=(
                "Define tracking event requirements for an experiment. "
                "Produces event specs to hand off to Experiment Engineer (event schema) "
                "and Sales Ops / Marketing Analytics (implementation)."
            ),
        )
        async def define_tracking_requirements(
            workspace_id: str,
            experiment_name: str,
            variants: List[str],
            primary_metric: str,
            secondary_metrics: List[str],
        ) -> Dict[str, Any]:
            _, _, ctx_text = await self._get_full_context(workspace_id)

            prompt = f"""Define tracking event requirements for a conversion experiment.

CONVERSION CONTEXT:
{ctx_text}

EXPERIMENT: {experiment_name}
VARIANTS: {", ".join(variants)}
PRIMARY METRIC: {primary_metric}
SECONDARY METRICS: {", ".join(secondary_metrics)}

Structure the requirements as:

1. **Events Required** — for each event:
   - event_name (snake_case, follows naming convention: experiment_[name]_[action])
   - properties: key-value pairs to capture (variant_id, page_type, user_segment, etc.)
   - where_fired: page/component where this event triggers
   - trigger_condition: what user action fires the event
2. **Experiment Tagging Standard** — how to tag all events with experiment_id and variant_id
3. **Attribution Requirements** — how to attribute conversions to specific variants
4. **Data Validation Rules** — how to verify events are firing correctly
5. **Contamination Prevention** — how to ensure users stay in their assigned variant

Return as structured JSON with key "events" containing the array and key "tagging_standard" with the rules.
This output will be handed to experiment_engineer_agent (event schema) and sales_ops_agent (implementation)."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.4,
            )

            return {
                "tracking_requirements": response.content,
                "experiment_name": experiment_name,
                "variant_count": len(variants),
                "next_steps": [
                    "Hand off event definitions to experiment_engineer_agent (define_event tool)",
                    "Hand off implementation spec to sales_ops_agent / marketing_analytics_agent",
                ],
            }

        # ── run_conversion_audit ─────────────────────────────────────
        @self.tool_registry.register(
            name="run_conversion_audit",
            description=(
                "Run a comprehensive conversion audit for a specific page type. "
                "Uses discovered optimization areas for this workspace — if none "
                "discovered, uses universal areas and recommends running discovery first."
            ),
        )
        async def run_conversion_audit(
            workspace_id: str,
            page_type: str,
            current_metrics: str,
            page_description: str,
        ) -> Dict[str, Any]:
            brand_voice, ref_docs, ctx_text = await self._get_full_context(workspace_id)
            conversion_ctx = await self._get_conversion_context(workspace_id)
            opt_areas = self._get_optimization_areas(conversion_ctx)
            numbered_areas = "\n".join(f"{i + 1}. {a}" for i, a in enumerate(opt_areas))

            prompt = f"""Run a comprehensive conversion audit for a specific page type.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

CONVERSION CONTEXT:
{ctx_text}

PAGE TYPE: {page_type}
CURRENT METRICS: {current_metrics}
PAGE DESCRIPTION: {page_description}

Evaluate ALL of the following optimization areas and score each (1-10 for current effectiveness):

{numbered_areas}

For each area provide:
- Current score (1-10)
- Evidence/reasoning for score
- Optimization opportunity (high/medium/low)
- Recommended experiment if opportunity is medium or high

Then produce a PRIORITIZED EXPERIMENT ROADMAP:
- Rank experiments by expected revenue impact
- Include quick wins (1 week) vs. strategic tests (1 month)
- Estimate cumulative conversion lift if all experiments succeed

Flag any benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_CRO_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="cro_conversion_audit_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            refinement_result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Conversion Audit: {page_type}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="conversion_audit",
                title=title,
                body=refinement_result.content,
            )

            result: Dict[str, Any] = {
                "draft_id": draft.id,
                "title": title,
                "body_preview": refinement_result.content[:500],
                "status": "pending",
                "optimization_areas_used": len(opt_areas),
            }

            if not conversion_ctx:
                result["warning"] = (
                    "No conversion context discovered for this workspace. "
                    "Audit used universal optimization areas. Run "
                    "discover_conversion_architecture for calibrated results."
                )

            return result

        # ── analyze_experiment_results ────────────────────────────────
        @self.tool_registry.register(
            name="analyze_experiment_results",
            description=(
                "Analyze experiment results and produce a recommendation: "
                "ship, iterate, or kill. Validates statistical significance "
                "and checks for long-term lift vs. short-term spikes."
            ),
        )
        async def analyze_experiment_results(
            workspace_id: str,
            experiment_name: str,
            control_data: str,
            variant_data: str,
            duration_days: int,
            sample_size_per_variant: int,
        ) -> Dict[str, Any]:
            _, _, ctx_text = await self._get_full_context(workspace_id)

            prompt = f"""Analyze experiment results and produce a recommendation.

CONVERSION CONTEXT:
{ctx_text}

EXPERIMENT: {experiment_name}
DURATION: {duration_days} days
SAMPLE SIZE PER VARIANT: {sample_size_per_variant}

CONTROL DATA:
{control_data}

VARIANT DATA:
{variant_data}

Structure your analysis as:

1. **Executive Summary** — 2-3 sentence verdict
2. **Statistical Validation**
   - Was the sample size sufficient for 95% confidence / 80% power?
   - Is the result statistically significant? Show reasoning.
   - Is there risk of a false positive (p-hacking, peeking)?
   - Were guardrail metrics preserved?
3. **Result Breakdown**
   - Primary metric: control vs. variant (absolute and relative change)
   - Secondary metrics: control vs. variant for each
   - Segment analysis: did the lift hold across key segments?
4. **Durability Assessment**
   - Is this a novelty effect that may fade?
   - Were there temporal patterns (weekday vs. weekend, time of day)?
   - Recommendation for holdback group to monitor long-term
5. **Decision: Ship / Iterate / Kill**
   - Clear recommendation with reasoning
   - If ship: rollout plan (partial first? which segments?)
   - If iterate: what to change in the next variant
   - If kill: what to test instead
6. **Follow-Up Experiments** — what to test next based on learnings

Flag any statistical claims with confidence levels."""

            config = RefinementConfig(
                criteria=_CRO_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="cro_results_analysis_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, "", hooks)

            title = f"Experiment Results: {experiment_name}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="experiment_results",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
                "next_step": "Hand off decision to experiment_engineer_agent (record_experiment_readout)",
            }

        # ── calculate_experiment_requirements ─────────────────────────
        @self.tool_registry.register(
            name="calculate_experiment_requirements",
            description=(
                "Calculate statistical requirements for an experiment. "
                "Pure math: minimum sample size, duration estimate, and "
                "minimum detectable effect. No LLM call."
            ),
        )
        async def calculate_experiment_requirements(
            baseline_conversion_rate: float,
            minimum_detectable_effect: float,
            daily_traffic: int,
            traffic_split: float = 0.5,
            confidence_level: float = 0.95,
            power: float = 0.80,
            num_variants: int = 2,
        ) -> Dict[str, Any]:
            import math

            # Z-scores
            z_alpha = {0.90: 1.645, 0.95: 1.960, 0.99: 2.576}.get(confidence_level, 1.960)
            z_beta = {0.80: 0.842, 0.90: 1.282}.get(power, 0.842)

            # Minimum sample size per variant (two-proportion z-test)
            p1 = baseline_conversion_rate
            p2 = baseline_conversion_rate * (1 + minimum_detectable_effect)
            p_bar = (p1 + p2) / 2

            if p1 <= 0 or p1 >= 1 or p2 <= 0 or p2 >= 1:
                return {"error": "Conversion rates must be between 0 and 1 (exclusive)"}

            numerator = (
                z_alpha * math.sqrt(2 * p_bar * (1 - p_bar))
                + z_beta * math.sqrt(p1 * (1 - p1) + p2 * (1 - p2))
            ) ** 2
            denominator = (p2 - p1) ** 2
            sample_per_variant = math.ceil(numerator / denominator)

            total_sample = sample_per_variant * num_variants
            traffic_per_variant_per_day = daily_traffic * traffic_split / num_variants
            duration_days = math.ceil(sample_per_variant / max(traffic_per_variant_per_day, 1))

            return {
                "baseline_conversion_rate": round(p1, 4),
                "expected_variant_rate": round(p2, 4),
                "minimum_detectable_effect": round(minimum_detectable_effect, 4),
                "confidence_level": confidence_level,
                "power": power,
                "sample_per_variant": sample_per_variant,
                "total_sample_needed": total_sample,
                "num_variants": num_variants,
                "daily_traffic": daily_traffic,
                "traffic_split": traffic_split,
                "traffic_per_variant_per_day": round(traffic_per_variant_per_day, 1),
                "estimated_duration_days": duration_days,
                "estimated_duration_weeks": round(duration_days / 7, 1),
                "recommendation": (
                    "Sufficient traffic"
                    if duration_days <= 28
                    else f"Consider increasing traffic or MDE. Current estimate: {duration_days} days"
                ),
            }

        # ── get_conversion_context ───────────────────────────────────
        @self.tool_registry.register(
            name="get_conversion_context",
            description=(
                "Retrieve the current discovered conversion context for a workspace. "
                "Shows what the agent has learned about this site's vertical, page types, "
                "revenue mechanics, optimization areas, and key metrics."
            ),
        )
        async def get_conversion_context(
            workspace_id: str,
        ) -> Dict[str, Any]:
            ctx = await self._get_conversion_context(workspace_id)
            if ctx:
                return {
                    "status": "discovered",
                    "workspace_id": workspace_id,
                    "conversion_context": ctx,
                }
            return {
                "status": "not_discovered",
                "workspace_id": workspace_id,
                "message": (
                    "No conversion context found for this workspace. "
                    "Run discover_conversion_architecture to calibrate."
                ),
                "default_optimization_areas": list(_UNIVERSAL_OPTIMIZATION_AREAS),
            }
