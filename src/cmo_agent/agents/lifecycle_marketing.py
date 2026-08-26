"""Lifecycle Marketing Agent - customer lifecycle strategy, email/SMS/push flows, segmentation."""

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

# Lifecycle marketing quality criteria
_LIFECYCLE_CRITERIA = [
    QualityCriterion(
        name="engagement_hooks",
        description="Compelling hooks and attention-grabbing elements in messaging",
    ),
    QualityCriterion(
        name="compliance",
        description="Regulatory compliance considerations properly addressed (CAN-SPAM, TCPA, GDPR)",
    ),
    QualityCriterion(
        name="clarity", description="Clear, concise writing with logical flow and structure"
    ),
    QualityCriterion(
        name="personalization_quality",
        description="Effective use of personalization, dynamic content, and behavioral tokens",
    ),
    QualityCriterion(
        name="cta_effectiveness",
        description="Strong, clear calls-to-action with appropriate urgency levels",
    ),
]


class LifecycleMarketingAgent(BaseAgent):
    """Handles customer lifecycle strategy across email, SMS, push, and in-product messaging."""

    agent_id = "lifecycle_marketing_agent"
    agent_name = "Lifecycle Marketing Agent"

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
        return """You are the Lifecycle Marketing Agent, a specialist in customer lifecycle strategy and retention marketing.

Your expertise covers:
- Lifecycle flow design (welcome, onboarding, activation, engagement, upsell, cross-sell, win-back, churn prevention)
- Behavioral and lifecycle segmentation logic
- Trigger definitions and event tracking requirements
- High-converting message frameworks across email, SMS, push, and in-product channels
- A/B testing strategy for lifecycle messaging
- Compliance guidance (CAN-SPAM, TCPA, GDPR)

PLATFORMS YOU WORK WITH:
- Customer.io (event-driven lifecycle automation) - primary lifecycle platform
- Beehiiv (newsletter/email marketing)
- General email/SMS/push systems

CUSTOMER.IO INTEGRATION:
- The App API key is available in settings as CUSTOMERIO_APP_API_KEY (Bearer token)
- Use it to query profiles, segments, campaigns, and metrics via https://api.customer.io/v1/
- Track API writes (identify, events) are typically handled by an n8n workflow, not this agent

KEY METRICS YOU WORK WITH:
- LTV (Lifetime Value)
- Retention rate and churn rate
- Activation rate and time-to-value
- Email open rate, click rate, conversion rate
- SMS opt-in/opt-out rates
- Push notification engagement rates
- Revenue per subscriber
- NPS and engagement scores

IMPORTANT RULES:
- All specific performance claims MUST be flagged with [VERIFY] prefix
- All strategic plans are saved as drafts for human review
- Base recommendations on behavioral data and industry benchmarks
- Always consider the brand's target audience and voice
- Always flag compliance requirements for the relevant channels and regions
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="design_lifecycle_flow",
            description="Design a complete lifecycle flow (welcome, onboarding, activation, engagement, upsell, cross-sell, win-back, churn prevention) with triggers, conditions, message architecture, test plan, and KPIs.",
        )
        async def design_lifecycle_flow(
            workspace_id: str,
            flow_type: str,
            goal: str,
            channels: List[str],
            audience_description: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Design a complete lifecycle marketing flow.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

FLOW TYPE: {flow_type}
GOAL: {goal}
CHANNELS: {", ".join(channels)}
TARGET AUDIENCE: {audience_description}

Structure the plan as:
1. **Strategy Overview** - Goal, audience, expected impact
2. **Flow Map** - Step-by-step sequence with triggers, delays, and conditions
3. **Message Architecture** - Touchpoint summary per step (channel, purpose, timing)
4. **Trigger & Condition Logic** - Entry criteria, branching rules, exit conditions
5. **Personalization Strategy** - Dynamic content, merge tags, behavioral tokens
6. **Test Plan** - Key elements to A/B test within this flow
7. **KPIs & Success Metrics** - Primary and secondary metrics with target benchmarks
8. **Compliance Notes** - Channel-specific regulatory requirements

Flag any benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_LIFECYCLE_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="lifecycle_flow_refinement",
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
                content_type="lifecycle_flow",
                title=f"Lifecycle Flow: {flow_type}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Lifecycle Flow: {flow_type}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="create_segmentation_strategy",
            description="Create behavioral and lifecycle segmentation logic with segment definitions, entry/exit criteria, behavioral triggers, and data requirements.",
        )
        async def create_segmentation_strategy(
            workspace_id: str,
            business_model: str,
            available_data_points: List[str],
            goal: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a behavioral and lifecycle segmentation strategy.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

BUSINESS MODEL: {business_model}
AVAILABLE DATA POINTS: {", ".join(available_data_points)}
SEGMENTATION GOAL: {goal}

Structure the plan as:
1. **Segmentation Overview** - Approach and rationale
2. **Segment Definitions** - Name, description, and size estimate for each segment
3. **Entry Criteria** - Behavioral and demographic triggers for segment assignment
4. **Exit Criteria** - When and how users move between segments
5. **Behavioral Triggers** - Key events that indicate segment transitions
6. **Data Requirements** - Events, properties, and integrations needed
7. **Lifecycle Stage Mapping** - How segments map to lifecycle stages (new, active, at-risk, churned)
8. **Recommended Actions per Segment** - Messaging strategy and channel priority

Flag any benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="segmentation_strategy",
                title=f"Segmentation Strategy: {goal}",
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Segmentation Strategy: {goal}",
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="define_trigger_logic",
            description="Define trigger logic and event tracking requirements for a lifecycle flow, including event taxonomy, trigger conditions, delay logic, branching rules, and implementation instructions.",
        )
        async def define_trigger_logic(
            workspace_id: str,
            flow_name: str,
            platform: str = "general",
            events_available: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            events_str = ", ".join(events_available) if events_available else "Not specified"

            prompt = f"""Define trigger logic and event tracking requirements for a lifecycle flow.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

FLOW NAME: {flow_name}
PLATFORM: {platform}
AVAILABLE EVENTS: {events_str}

Structure the plan as:
1. **Event Taxonomy** - All events needed (name, description, properties)
2. **Trigger Conditions** - Entry triggers with exact logic (event + conditions)
3. **Delay Logic** - Wait steps, time-based triggers, optimal send times
4. **Branching Rules** - Conditional splits based on behavior or attributes
5. **Exit Conditions** - When to remove users from the flow (goal achieved, unsubscribed, etc.)
6. **Frequency Capping** - Rules to prevent message fatigue
7. **Platform Implementation** - {platform}-specific setup instructions
8. **Testing Checklist** - How to verify trigger logic before launch

Flag any platform-specific details with [VERIFY] if they may change."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="trigger_logic",
                title=f"Trigger Logic: {flow_name} ({platform})",
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Trigger Logic: {flow_name} ({platform})",
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="write_message_framework",
            description="Write high-converting message frameworks for lifecycle touchpoints with subject lines, preview text, body copy framework, CTA options, and personalization tokens.",
        )
        async def write_message_framework(
            workspace_id: str,
            channel: str,
            flow_stage: str,
            audience_segment: str,
            goal: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Write a high-converting message framework for a lifecycle touchpoint.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

CHANNEL: {channel}
FLOW STAGE: {flow_stage}
AUDIENCE SEGMENT: {audience_segment}
GOAL: {goal}

Structure the framework as:
1. **Message Overview** - Purpose, timing, expected outcome
2. **Subject Lines** (email) / **Hook** (SMS/push) - 3-5 options ranked by approach
3. **Preview Text** (email) / **Opening** - 2-3 options
4. **Body Copy Framework** - Structure with sections, key points, and tone guidance
5. **CTA Options** - 3 variants with different urgency levels
6. **Personalization Tokens** - Dynamic fields to include (name, behavior, preferences)
7. **Channel-Specific Best Practices** - Length, formatting, timing for {channel}
8. **Compliance Requirements** - Required elements (unsubscribe, physical address, opt-out for SMS)

Flag any benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_LIFECYCLE_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="lifecycle_message_refinement",
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
                content_type="message_framework",
                title=f"Message Framework: {channel} - {flow_stage}",
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Message Framework: {channel} - {flow_stage}",
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="create_lifecycle_test_plan",
            description="Recommend structured A/B tests for lifecycle messaging with variants, metrics, sample size, duration, and success criteria.",
        )
        async def create_lifecycle_test_plan(
            workspace_id: str,
            flow_name: str,
            element_to_test: str,
            hypothesis: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a structured A/B test plan for lifecycle messaging.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

FLOW NAME: {flow_name}
ELEMENT TO TEST: {element_to_test}
HYPOTHESIS: {hypothesis}

Structure the plan as:
1. **Test Name & Objective**
2. **Hypothesis** (formalized as: If we [change], then [metric] will [direction] because [rationale])
3. **Control (A)** - Current version description
4. **Variant (B)** - Proposed change description
5. **Primary Metric** - What defines success
6. **Secondary Metrics** - Supporting measurements
7. **Sample Size & Duration** - Statistical requirements for significance
8. **Audience Segmentation** - Who to include/exclude from the test
9. **Success Criteria** - Minimum detectable effect and confidence level
10. **Rollout Plan** - What happens if the variant wins, phased rollout steps

Flag any statistical benchmarks with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="lifecycle_test_plan",
                title=f"Lifecycle Test: {element_to_test} in {flow_name}",
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Lifecycle Test: {element_to_test} in {flow_name}",
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="audit_compliance",
            description="Check a message or flow against CAN-SPAM, TCPA, GDPR requirements. Returns compliance checklist, issues found, and remediation steps. Pure analysis, not saved as draft.",
        )
        async def audit_compliance(
            workspace_id: str,
            content: str,
            channel: str,
            target_regions: List[str],
        ) -> Dict[str, Any]:
            prompt = f"""Audit the following content for regulatory compliance.

CHANNEL: {channel}
TARGET REGIONS: {", ".join(target_regions)}

CONTENT TO AUDIT:
{content}

Check against ALL applicable regulations:
- **CAN-SPAM** (US email): sender identification, subject line accuracy, unsubscribe mechanism, physical address
- **TCPA** (US SMS/calls): prior express consent, opt-out mechanism, time restrictions, identification
- **GDPR** (EU/UK): lawful basis, data minimization, right to erasure, consent records, DPO requirements
- **CASL** (Canada): express/implied consent, identification, unsubscribe
- **CCPA/CPRA** (California): opt-out rights, data collection disclosure

Provide your audit as:
1. **Compliance Summary** - Overall status (pass/fail/needs review)
2. **Applicable Regulations** - Which laws apply based on channel and regions
3. **Checklist** - Line-by-line compliance check for each regulation
4. **Issues Found** - Specific violations or risks with severity (critical/warning/info)
5. **Remediation Steps** - Exactly what to fix, with example language where helpful
6. **Best Practices** - Additional recommendations beyond minimum compliance"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.5,
            )

            return {
                "audit": response.content,
                "channel": channel,
                "target_regions": target_regions,
            }
