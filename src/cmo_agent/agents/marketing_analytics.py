"""Marketing Analytics Agent - measurement strategy, tracking architecture, attribution modeling."""

from __future__ import annotations

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

# Marketing Analytics quality criteria for RefinementLoop
_ANALYTICS_CRITERIA = [
    QualityCriterion(
        name="technical_precision",
        description="Event names, parameter definitions, and dataLayer specs follow platform naming conventions exactly",
    ),
    QualityCriterion(
        name="measurement_completeness",
        description="All key business actions, conversions, and engagement signals are captured in the framework",
    ),
    QualityCriterion(
        name="implementation_clarity",
        description="Technical specs are detailed enough for a developer to implement without ambiguity",
    ),
    QualityCriterion(
        name="standards_consistency",
        description="Naming conventions, UTM rules, and taxonomy are internally consistent across all specs",
    ),
    QualityCriterion(
        name="diagnostic_value",
        description="Dashboard layouts, alert thresholds, and attribution models enable actionable decision-making",
    ),
]


class MarketingAnalyticsAgent(BaseAgent):
    """Measurement frameworks, tracking specs, UTM governance, attribution, dashboards."""

    agent_id = "marketing_analytics_agent"
    agent_name = "Marketing Analytics Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._config = ConfigRepo(db)
        self._workspace_mgr = workspace_manager
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Marketing Analytics Agent, a specialist in marketing measurement, tracking architecture, and attribution modeling.

Your expertise covers:
- Google Analytics 4 (GA4): event taxonomy, custom dimensions/metrics, data streams, BigQuery export
- Attribution modeling: last-click, first-click, linear, time-decay, position-based, data-driven, MMM, MTA
- UTM governance: naming conventions, parameter standards, link management
- Event tracking architecture: dataLayer design, tag management (GTM), server-side tagging
- Conversion tracking: pixel implementation, offline conversion imports, enhanced conversions
- Marketing Mix Modeling (MMM) and Multi-Touch Attribution (MTA)
- Dashboard and reporting design: KPI hierarchies, data visualization, executive reporting

KEY FRAMEWORKS YOU WORK WITH:
- GA4 event model (automatically collected, enhanced measurement, recommended, custom)
- UTM parameter taxonomy (source, medium, campaign, content, term)
- KPI hierarchy (north star > primary > secondary > diagnostic metrics)
- Attribution model selection by channel maturity and data availability
- Measurement maturity model (foundational, intermediate, advanced, predictive)

SCOPE BOUNDARY: You handle measurement infrastructure and tracking architecture — what to track, how to name it, how to attribute it, and how to report on it. You do NOT analyze live campaign performance, optimize ad spend, or calculate ROAS from actual data. Those tasks belong to the Performance Marketer Agent.

IMPORTANT RULES:
- All specific benchmark claims MUST be flagged with [VERIFY] prefix
- All strategic deliverables are saved as drafts for human review
- Base recommendations on industry standards and GA4 documentation
- Always consider the brand's tech stack and data maturity level
- When providing SQL or tracking specs, use clear comments and standard formatting
- Always flag implementation complexity (low/medium/high) for each recommendation
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="create_measurement_framework",
            description="Create a comprehensive measurement framework mapping business goals to KPIs, metrics, data sources, and tracking requirements.",
        )
        async def create_measurement_framework(
            workspace_id: str,
            business_goals: List[str],
            channels: List[str],
            tech_stack: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a comprehensive measurement framework.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

BUSINESS GOALS: {", ".join(business_goals)}
CHANNELS: {", ".join(channels)}
TECH STACK: {tech_stack}

Structure the framework as:
1. **Business Goal → KPI Mapping** - Each goal mapped to primary and secondary metrics
2. **KPI Hierarchy** - North star metric, primary KPIs, secondary KPIs, diagnostic metrics
3. **Channel-Specific Metrics** - Per channel: key metrics, benchmarks, data source
4. **Data Source Mapping** - Analytics platform, ad platforms, CRM, backend events
5. **Tracking Requirements** - Events needed, parameters, implementation priority
6. **Measurement Maturity Assessment** - Current vs. target state
7. **Implementation Roadmap** - Phased rollout: foundational → intermediate → advanced

Flag any benchmark claims with [VERIFY]. Flag implementation complexity (low/medium/high) for each recommendation."""

            config = RefinementConfig(
                criteria=_ANALYTICS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="analytics_measurement_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="measurement_framework",
                title="Measurement Framework",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": "Measurement Framework",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="design_event_taxonomy",
            description="Define a GA4 event taxonomy with event names, parameters, custom dimensions, and dataLayer specifications.",
        )
        async def design_event_taxonomy(
            workspace_id: str,
            platform_type: str,
            key_user_actions: List[str],
            conversion_events: List[str],
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Define a GA4 event taxonomy.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

PLATFORM TYPE: {platform_type}
KEY USER ACTIONS: {", ".join(key_user_actions)}
CONVERSION EVENTS: {", ".join(conversion_events)}

Structure the taxonomy as:
1. **Event Naming Convention** - Casing rules, prefix patterns, naming examples
2. **Automatically Collected Events** - Relevant subset for this platform
3. **Enhanced Measurement Events** - Which to enable, configuration notes
4. **Recommended Events** - GA4 recommended events applicable to this business
5. **Custom Event Definitions** - Name, parameters, trigger conditions per event
6. **Custom Dimensions & Metrics** - Scope, name, description, parameter mapping
7. **dataLayer Specifications** - JSON push examples per event
8. **GTM Tag Configuration** - Tag/trigger/variable setup per event
9. **Testing & QA Checklist** - How to verify each event fires correctly

Flag any platform-specific details with [VERIFY] if they may change."""

            config = RefinementConfig(
                criteria=_ANALYTICS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="analytics_event_taxonomy_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="event_taxonomy",
                title=f"Event Taxonomy: {platform_type}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Event Taxonomy: {platform_type}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="design_utm_naming_standard",
            description="Design UTM naming conventions and governance rules with parameter definitions, naming patterns, validation rules, and example URLs.",
        )
        async def design_utm_naming_standard(
            workspace_id: str,
            channels: List[str],
            campaign_types: List[str],
            existing_conventions: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            existing = existing_conventions or "None specified"

            prompt = f"""Design UTM naming conventions and governance rules.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

CHANNELS: {", ".join(channels)}
CAMPAIGN TYPES: {", ".join(campaign_types)}
EXISTING CONVENTIONS: {existing}

Structure the standard as:
1. **UTM Parameter Definitions** - Source, medium, campaign, content, term — each with purpose and rules
2. **Naming Convention Rules** - Case, delimiters, allowed characters, max length
3. **Source/Medium Taxonomy** - Channel grouping alignment with GA4 default channel groups
4. **Campaign Naming Pattern** - Structure: {{brand}}_{{objective}}_{{audience}}_{{date}}
5. **Content & Term Usage Guidelines** - When to use, standard values
6. **Validation Rules & Regex Patterns** - Regex for each parameter
7. **Example URLs per Channel** - One complete tagged URL per channel
8. **Link Management Process** - Who creates, approval flow, central spreadsheet
9. **Common Mistakes to Avoid** - Top 5 governance failures

Flag any benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_ANALYTICS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="analytics_utm_standard_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="utm_standard",
                title="UTM Naming Standard",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": "UTM Naming Standard",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="recommend_attribution_model",
            description="Recommend attribution models by channel with rationale, data requirements, and implementation guidance for MMM and MTA.",
        )
        async def recommend_attribution_model(
            workspace_id: str,
            channels: List[str],
            data_maturity: str,
            primary_kpi: str,
            budget_range: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            budget = budget_range or "Not specified"

            prompt = f"""Recommend attribution models by channel.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

CHANNELS: {", ".join(channels)}
DATA MATURITY: {data_maturity}
PRIMARY KPI: {primary_kpi}
BUDGET RANGE: {budget}

Structure the recommendation as:
1. **Attribution Landscape Assessment** - Current state, gaps, opportunities
2. **Channel-by-Channel Model Recommendation** - Model type, rationale, data requirements per channel
3. **Cross-Channel Attribution Strategy** - How models interact across touchpoints
4. **MMM Feasibility Assessment** - Data requirements, cost, timeline, expected value
5. **MTA Implementation Requirements** - Tracking prerequisites, identity resolution, tooling
6. **GA4 Attribution Settings** - Recommended attribution model, lookback windows, conversion paths
7. **Attribution Window Recommendations** - Per channel: click window, view window, rationale
8. **Data Requirements & Gaps** - What data exists vs. what's needed
9. **Implementation Roadmap by Maturity Stage** - Foundational/intermediate/advanced actions

Flag any benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_ANALYTICS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="analytics_attribution_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="attribution_model",
                title=f"Attribution Model: {primary_kpi}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Attribution Model: {primary_kpi}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="audit_tracking_gaps",
            description="Audit current tracking setup to identify gaps, misconfigurations, and improvement opportunities. Returns analysis, not saved as draft.",
        )
        async def audit_tracking_gaps(
            workspace_id: str,
            current_tracking: str,
            desired_capabilities: List[str],
            platform: str = "GA4",
        ) -> Dict[str, Any]:
            prompt = f"""Audit the current tracking setup for gaps and improvements.

PLATFORM: {platform}
CURRENT TRACKING SETUP:
{current_tracking}

DESIRED CAPABILITIES: {", ".join(desired_capabilities)}

Provide your audit as:
1. **Tracking Health Summary** - Pass/fail/warning per category
2. **Coverage Assessment per Channel** - What's tracked vs. missing
3. **Gaps Identified** - Severity: critical/warning/info, with description
4. **Misconfiguration Risks** - Existing tracking that may produce bad data
5. **Data Quality Issues** - Duplicate events, missing parameters, sampling concerns
6. **Privacy & Consent Gaps** - Consent mode, cookie policy, GDPR/CCPA compliance
7. **Prioritized Fix List** - Each with complexity: low/medium/high
8. **Quick Wins vs. Long-Term Improvements** - Immediate actions vs. infrastructure changes

Flag any platform-specific details with [VERIFY] if they may change."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.5,
            )

            return {
                "audit": response.content,
                "platform": platform,
            }

        @self.tool_registry.register(
            name="create_dashboard_requirements",
            description="Define dashboard and reporting requirements with KPI layout, data sources, visualization types, filters, and refresh cadence.",
        )
        async def create_dashboard_requirements(
            workspace_id: str,
            dashboard_purpose: str,
            audience: str,
            kpis: List[str],
            data_sources: List[str],
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Define dashboard and reporting requirements.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

DASHBOARD PURPOSE: {dashboard_purpose}
AUDIENCE: {audience}
KPIs: {", ".join(kpis)}
DATA SOURCES: {", ".join(data_sources)}

Structure the requirements as:
1. **Dashboard Overview** - Purpose, audience, refresh frequency, access level
2. **KPI Card Layout** - Metric, visualization type, comparison period, target/threshold
3. **Chart Specifications** - Chart type, dimensions, measures, filters per chart
4. **Filter & Drill-Down Requirements** - Global filters, cross-filter behavior, drill-down paths
5. **Data Source Mapping** - Which data source feeds each widget, join keys
6. **SQL/Query Specifications** - Sample query for each key widget
7. **Alert & Threshold Rules** - Conditions that trigger notifications
8. **Access & Distribution Plan** - Who sees what, email cadence, export format

Flag any benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_ANALYTICS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="analytics_dashboard_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="dashboard_requirements",
                title=f"Dashboard Requirements: {dashboard_purpose}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Dashboard Requirements: {dashboard_purpose}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="generate_tracking_spec",
            description="Generate a technical tracking specification with SQL queries, GTM configurations, or dataLayer code for a specific tracking requirement.",
        )
        async def generate_tracking_spec(
            workspace_id: str,
            spec_type: str,
            requirement: str,
            target_platform: str = "GA4",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Generate a technical tracking specification.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

SPEC TYPE: {spec_type}
TARGET PLATFORM: {target_platform}
REQUIREMENT: {requirement}

Structure the specification as:
1. **Specification Overview** - What this spec implements, context
2. **Technical Implementation** - The actual code/config (SQL, JSON, JS depending on spec type)
3. **Dependencies & Prerequisites** - Libraries, permissions, existing tags required
4. **Testing Instructions** - How to verify the implementation works
5. **Validation Queries** - SQL or debug commands to confirm data flows correctly

Use clear comments in all code. Flag implementation complexity (low/medium/high)."""

            config = RefinementConfig(
                criteria=_ANALYTICS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="analytics_tracking_spec_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="tracking_spec",
                title=f"Tracking Spec: {spec_type} ({target_platform})",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Tracking Spec: {spec_type} ({target_platform})",
                "body_preview": result.content[:500],
                "spec_type": spec_type,
                "status": "pending",
            }
