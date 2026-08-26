"""LinkedIn Partnerships Lead Generation Agent - ICP profiling, prospecting, outreach sequences."""

from __future__ import annotations

from typing import Any, Dict, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_char_limit_hook, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# Quality criteria for LinkedIn outreach sequence refinement
_LINKEDIN_OUTREACH_CRITERIA = [
    QualityCriterion(
        name="conciseness",
        description="Messages are tight, no filler words, every sentence earns its place",
    ),
    QualityCriterion(
        name="value_hook",
        description="Opens with a compelling value proposition or insight, not a generic intro",
    ),
    QualityCriterion(
        name="personalization",
        description="Content feels tailored to the specific partner type, not generic boilerplate",
    ),
    QualityCriterion(
        name="professional_tone",
        description="Consultative, peer-to-peer tone without being stiff or overly formal",
    ),
    QualityCriterion(
        name="character_limit_compliance",
        description="Connection requests under 300 chars, InMail under 1900 chars, limits shown in output",
    ),
]


class LinkedInPartnershipsAgent(BaseAgent):
    """Handles LinkedIn partnership lead generation: ICP profiling, prospecting, outreach, tracking."""

    agent_id = "linkedin_partnerships_agent"
    agent_name = "LinkedIn Partnerships Lead Generation Agent"

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
        return """You are the LinkedIn Partnerships Lead Generation Agent, a specialist in B2B partnership prospecting via LinkedIn.

Your mission: Generate qualified partnership leads through systematic ICP definition, LinkedIn prospecting strategy, personalized outreach sequences, follow-up cadences, and CRM tracking frameworks.

Your expertise covers:
- ICP/partner profiling: firmographic (revenue, headcount, industry, geography), technographic (tech stack, tools, platforms), and behavioral (content engagement, hiring signals, funding events) criteria
- LinkedIn Sales Navigator prospecting with Boolean search syntax (AND, OR, NOT, quotes, parentheses)
- Outreach messaging with LinkedIn platform constraints
- Follow-up cadence design with multi-channel branching (LinkedIn → email → phone)
- CRM tracking and partnership pipeline stage design
- n8n automation awareness — recommends concrete workflow patterns (webhook triggers, CRM updates, Slack notifications)

LINKEDIN HARD CONSTRAINTS (enforce in all outreach outputs):
- Connection requests: MUST be under 300 characters (LinkedIn enforces this limit)
- InMail messages: MUST be under 1900 characters
- Weekly connection request limit: ~100 (LinkedIn enforces, pace accordingly)
- Profile view warming: View target's profile 2-3 days before sending connection request
- No mass scraping or automated connection requests (LinkedIn ToS violation)
- No misleading profile activity or fake engagement

KEY METRICS (all specific benchmarks flagged [VERIFY]):
- Connection request acceptance rate: [VERIFY] 25-40% with personalization
- InMail response rate: [VERIFY] 10-25% depending on targeting quality
- Reply-to-meeting conversion: [VERIFY] 15-30% for warm outreach
- Average touches to partnership meeting: [VERIFY] 5-8 across channels
- Pipeline velocity: [VERIFY] 30-90 days from first touch to signed partnership

IMPORTANT RULES:
- All specific benchmark claims MUST be flagged with [VERIFY] prefix
- All strategic plans are saved as drafts for human review
- Enforce LinkedIn character limits in all message templates
- Include A/B testing frameworks in outreach sequences
- Recommend n8n workflow patterns where automation adds value
- Always include suggested_next_steps referencing specific sister agents
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels.

SCOPE BOUNDARIES:
- You handle: partner ICP definition, LinkedIn prospecting strategy, outreach sequences, follow-up cadences, partnership pipeline tracking
- Compliance Agent handles: regulatory review of outreach copy (TCPA, CAN-SPAM, GDPR)
- Legal Strategy Agent handles: partnership agreements, NDAs, term sheets
- Lifecycle Marketing Agent handles: email/SMS nurture flows beyond LinkedIn
- Sales Ops Agent handles: CRM pipeline infrastructure and automation implementation
- Performance Marketer Agent handles: paid LinkedIn ad campaigns (Sponsored Content, InMail ads)

COLLABORATION: When your output overlaps another agent's domain, include a suggested_next_steps recommendation naming the specific agent and what to ask them."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="define_partner_icp",
            description="Define an Ideal Customer Profile for partnership prospecting with firmographic, technographic, and behavioral criteria, scoring rubric, and LinkedIn search filters.",
        )
        async def define_partner_icp(
            workspace_id: str,
            partnership_goal: str,
            industry_focus: Optional[str] = None,
            company_size_range: Optional[str] = None,
            geographic_focus: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Define an Ideal Customer Profile (ICP) for partnership prospecting.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
PARTNERSHIP GOAL: {partnership_goal}
INDUSTRY FOCUS: {industry_focus or "Not specified — recommend based on partnership goal"}
COMPANY SIZE: {company_size_range or "Not specified — recommend based on partnership goal"}
GEOGRAPHIC FOCUS: {geographic_focus or "Not specified — recommend based on partnership goal"}

Structure the ICP with these sections:

## 1. Firmographic Criteria
- Industry / sub-industry targets
- Company size (revenue range, employee count)
- Geography / HQ location
- Business model (B2B, B2C, marketplace, SaaS, etc.)
- Growth stage (startup, scale-up, enterprise)

## 2. Technographic Criteria
- Tech stack signals (tools, platforms, languages)
- Current vendor/partner landscape
- Technology adoption indicators
- Integration compatibility signals

## 3. Behavioral Criteria
- LinkedIn engagement signals (posting frequency, topic alignment, engagement type)
- Hiring signals (roles being hired indicate priorities)
- Funding / growth events (raises, acquisitions, expansions)
- Content consumption patterns
- Conference / event attendance

## 4. Partner Scoring Rubric
- Scoring dimensions (1-10 scale): Strategic Fit, Revenue Potential, Ease of Activation, Brand Alignment, Market Reach
- Tier definitions: Tier 1 (score 40-50), Tier 2 (score 25-39), Tier 3 (score 15-24)
- Disqualification criteria (automatic no-go signals)

## 5. LinkedIn Search Filters
- LinkedIn Sales Navigator Boolean search strings (exact syntax)
- Saved search recommendations
- Lead list segmentation strategy
- Profile keyword patterns to target

## 6. Negative Criteria (Anti-ICP)
- Company characteristics to exclude
- Red flag signals
- Competitive conflicts

Flag all benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.5,
            )

            title = f"Partner ICP: {partnership_goal[:60]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="partner_icp",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
                "suggested_next_steps": [
                    "Use ICP criteria to build prospecting framework (build_prospecting_framework tool)",
                    "Send outreach copy to Compliance Agent for regulatory review",
                    "Ask Performance Marketer Agent for paid LinkedIn ad targeting using these ICP criteria",
                ],
            }

        @self.tool_registry.register(
            name="build_prospecting_framework",
            description="Build a LinkedIn prospecting framework with search strategies, warming sequences, signal-based targeting, weekly cadence, and n8n workflow recommendations.",
        )
        async def build_prospecting_framework(
            workspace_id: str,
            target_partner_type: str,
            prospecting_volume: Optional[str] = None,
            linkedin_tools_available: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Build a comprehensive LinkedIn prospecting framework.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
TARGET PARTNER TYPE: {target_partner_type}
PROSPECTING VOLUME: {prospecting_volume or "Not specified — recommend sustainable weekly volume"}
LINKEDIN TOOLS AVAILABLE: {linkedin_tools_available or "Assume LinkedIn Sales Navigator + basic LinkedIn"}

Structure the framework with these sections:

## 1. Search Strategy
- LinkedIn Sales Navigator saved searches (exact Boolean syntax)
- Keyword combinations and filters
- Industry and function targeting
- Second/third-degree connection leveraging
- Alumni and group-based searches

## 2. Profile Warming Sequence
- Day 1-2: View target's profile (triggers notification)
- Day 2-3: Engage with their content (like, thoughtful comment)
- Day 3-5: Follow their company page
- Day 5-7: Send connection request
- Warming signals to watch for (profile views back, content engagement)

## 3. Signal-Based Targeting
- Trigger events that indicate partnership readiness:
  - Job postings (roles that align with partnership needs)
  - Funding announcements
  - Product launches or pivots
  - Leadership changes
  - Conference speaking / attendance
- How to monitor each signal on LinkedIn

## 4. Weekly Prospecting Cadence
- Daily/weekly activity targets (connections, InMails, profile views)
- Time blocking recommendations
- LinkedIn activity limits to respect (~100 connections/week)
- Pipeline stage movement criteria

## 5. Lead Qualification Process
- Initial qualification criteria (before outreach)
- Discovery call qualification framework (BANT/MEDDIC adapted for partnerships)
- Handoff criteria to partnership development

## 6. n8n Workflow Recommendations
For each workflow, provide: workflow name, trigger type, key nodes, and example flow.
- New Lead Identified: LinkedIn signal → n8n Webhook → Create CRM Contact → Post to Slack #partnerships
- Lead Scoring Update: Schedule trigger → Pull CRM data → Score leads → Update CRM → Alert for Tier 1
- Follow-up Reminder: Schedule trigger → Check CRM last-touch dates → Send Slack reminders for stale leads
- Partnership Meeting Booked: Webhook → Update CRM stage → Create calendar event → Notify team

Flag all benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            title = f"Prospecting Framework: {target_partner_type[:60]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="prospecting_framework",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
                "suggested_next_steps": [
                    "Create outreach sequences for this target type (create_outreach_sequences tool)",
                    "Ask Workflow Builder Agent to implement the n8n automation workflows",
                    "Ask Sales Ops Agent to set up CRM pipeline stages",
                ],
            }

        @self.tool_registry.register(
            name="create_outreach_sequences",
            description="Create LinkedIn outreach sequences with connection requests (< 300 chars enforced), first messages, follow-up cadence with A/B variants, pitch messaging, and re-engagement templates.",
        )
        async def create_outreach_sequences(
            workspace_id: str,
            partner_type: str,
            value_proposition: str,
            outreach_tone: Optional[str] = None,
            sequence_length: int = 5,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create LinkedIn outreach sequences for partnership prospecting.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
PARTNER TYPE: {partner_type}
VALUE PROPOSITION: {value_proposition}
OUTREACH TONE: {outreach_tone or "Professional, consultative, peer-to-peer"}
SEQUENCE LENGTH: {sequence_length} touches

CRITICAL LINKEDIN CONSTRAINTS — ENFORCE STRICTLY:
- Connection request messages: MUST be under 300 characters. Count characters carefully. If over 300, rewrite shorter.
- InMail messages: MUST be under 1900 characters.
- Daily connection request pacing: LinkedIn allows ~100 connection requests/week. Pace accordingly.
- Profile view warming: View profile 2-3 days before sending connection request.

Structure the sequences with these sections:

## 1. Connection Request Templates (A/B Test)
For EACH template: MUST be under 300 characters. Show character count in [brackets].

**Variant A: [Name — e.g., "Direct Ask"]**
- Template text (under 300 chars)
- Character count: [X/300]
- Hypothesis: What we're testing (e.g., direct CTA vs. value-first)
- Best for: Which prospect segment

**Variant B: [Name — e.g., "Value-First"]**
- Template text (under 300 chars)
- Character count: [X/300]
- Hypothesis: What we're testing
- Best for: Which prospect segment

**A/B Test Protocol:**
- Minimum sample: Send each variant to 50 prospects before evaluating
- Success metric: Connection acceptance rate
- Decision criteria: If Variant A acceptance rate > Variant B by 5%+ after 100 total sends, scale the winner

## 2. First Message After Connection (A/B Test)
Two variants with:
- Message text (conversational, value-focused)
- Hypothesis and success metric (reply rate)
- Minimum sample size: 30 conversations per variant
- Decision criteria for winner selection

## 3. Follow-Up Sequence ({sequence_length} touches)
For each touch point:
- Timing (days after previous touch)
- Channel (LinkedIn message, LinkedIn voice note, email, phone)
- Message template
- Purpose (value add, social proof, soft ask, direct ask)
- Branching logic (if replied → X, if no reply → Y)

## 4. Partnership Pitch Message
- Detailed value proposition message for interested prospects
- Partnership model overview
- Next steps / CTA
- Under 1900 characters for InMail delivery

## 5. Re-engagement Templates
- For prospects who went cold after initial interest
- For prospects who declined but circumstances may have changed
- Seasonal/event-triggered re-engagement

## 6. A/B Testing Framework Summary
| Message Type | Variants | Sample Size | Success Metric | Decision Threshold |
|---|---|---|---|---|
| Connection Request | A vs B | 50 each | Acceptance Rate | 5%+ difference |
| First Message | A vs B | 30 each | Reply Rate | 5%+ difference |
| Follow-up Sequence | Timing variants | 25 each | Meeting Booked Rate | Directional signal |

Flag all benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_LINKEDIN_OUTREACH_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="linkedin_outreach_refinement",
            )
            hooks = build_hook_chain(
                make_em_dash_hook(),
                make_char_limit_hook(300),
            )
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Outreach Sequences: {partner_type[:60]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="outreach_sequences",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
                "suggested_next_steps": [
                    "Send outreach sequences to Compliance Agent for regulatory review (TCPA, CAN-SPAM, GDPR)",
                    "Send partnership pitch to Legal Strategy Agent for contract template / NDA",
                    "Ask Lifecycle Marketing Agent to design email/SMS nurture for prospects who move off LinkedIn",
                ],
            }

        @self.tool_registry.register(
            name="design_partnership_tracking",
            description="Design a partnership CRM pipeline with stages, custom properties, KPIs, dashboards, and n8n automation workflow specs.",
        )
        async def design_partnership_tracking(
            workspace_id: str,
            crm_platform: Optional[str] = None,
            partnership_types: Optional[str] = None,
            team_size: int = 1,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Design a partnership CRM tracking system.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
CRM PLATFORM: {crm_platform or "Platform-agnostic (applicable to HubSpot, Salesforce, Pipedrive, or spreadsheet)"}
PARTNERSHIP TYPES: {partnership_types or "General partnerships — co-marketing, referral, integration, reseller"}
TEAM SIZE: {team_size} person(s) managing partnerships

Structure the tracking system with these sections:

## 1. Pipeline Stages
For each stage: name, definition, entry criteria, exit criteria, expected duration [VERIFY], key activities
- Identified → Researching → Outreach → Engaged → Discovery Call → Proposal → Negotiation → Signed → Onboarding → Active

## 2. Custom Properties / Fields
- Contact-level: partner type, ICP tier, LinkedIn URL, engagement score, last touch date, assigned owner
- Company-level: partner category, tech stack, annual revenue, employee count, integration compatibility
- Deal-level: partnership model, revenue share %, contract value, term length, launch date

## 3. KPI Dashboard
- Pipeline metrics: deals by stage, conversion rates, pipeline velocity, average deal cycle
- Activity metrics: outreach volume, response rates, meetings booked, proposals sent
- Revenue metrics: partner-sourced revenue, partner-influenced revenue, LTV of partner leads
- Health metrics: partner NPS, churn rate, time-to-first-value

## 4. Reporting Templates
- Weekly partnership activity report
- Monthly pipeline review
- Quarterly partner performance review

## 5. n8n Automation Workflow Specs
For each workflow, provide: workflow name, trigger type (webhook/schedule/manual), key nodes (node type + purpose), and example flow description.

**Workflow 1: New Partner Lead Capture**
- Trigger: Webhook (from form or manual entry)
- Nodes: Webhook → IF (check for duplicates) → CRM Create Contact → Set Stage to "Identified" → Slack notification to #partnerships
- Purpose: Standardize lead entry and notify team

**Workflow 2: Stale Lead Alert**
- Trigger: Schedule (daily at 9 AM)
- Nodes: Schedule → CRM Query (last touch > 7 days, stage < Signed) → Filter (exclude paused) → Slack message with lead list
- Purpose: Prevent leads from going cold

**Workflow 3: Stage Progression Tracker**
- Trigger: Webhook (CRM stage change event)
- Nodes: Webhook → Switch (by new stage) → Update metrics sheet → IF (stage = Signed) → Celebrate in Slack + Create onboarding task
- Purpose: Track pipeline movement and trigger onboarding

**Workflow 4: Partner Activity Digest**
- Trigger: Schedule (weekly, Friday 4 PM)
- Nodes: Schedule → CRM Query (this week's activities) → Aggregate stats → Format report → Send to Slack / email
- Purpose: Weekly visibility into partnership progress

## 6. Team Workflow (for {team_size}-person team)
- Daily prospecting routine
- Weekly pipeline review cadence
- Monthly partner check-in schedule
- Escalation triggers

Flag all benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.5,
            )

            title = f"Partnership Tracking: {crm_platform or 'CRM Pipeline'}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="partnership_tracking",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
                "suggested_next_steps": [
                    "Ask Sales Ops Agent to build CRM pipeline infrastructure and automation sequences",
                    "Ask Workflow Builder Agent to implement the n8n automation workflows",
                    "Ask Marketing Analytics Agent to design attribution tracking for partner-sourced leads",
                ],
            }

        @self.tool_registry.register(
            name="generate_full_lead_gen_strategy",
            description="Generate an end-to-end LinkedIn partnership lead generation strategy combining ICP, prospecting, outreach, tracking, and a 90-day implementation roadmap with inter-agent handoff recommendations.",
        )
        async def generate_full_lead_gen_strategy(
            workspace_id: str,
            business_context: str,
            partnership_goal: str,
            target_partners: str,
            timeline: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Generate a comprehensive LinkedIn partnership lead generation strategy.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
BUSINESS CONTEXT: {business_context}
PARTNERSHIP GOAL: {partnership_goal}
TARGET PARTNERS: {target_partners}
TIMELINE: {timeline or "90 days"}

LINKEDIN CONSTRAINTS TO RESPECT:
- Connection requests: under 300 characters
- InMail: under 1900 characters
- ~100 connection requests/week maximum
- Profile warming before cold outreach
- No automated scraping or connection tools (LinkedIn ToS)

Structure the strategy covering all 5 pillars:

## Pillar 1: Partner ICP Definition
- Firmographic criteria (industry, size, geography, business model)
- Technographic signals (tech stack, platforms, integrations)
- Behavioral indicators (LinkedIn activity, hiring, funding)
- Scoring rubric with tier definitions
- Anti-ICP (who to exclude)

## Pillar 2: Prospecting Framework
- LinkedIn Sales Navigator search strategies (Boolean syntax)
- Profile warming sequence (view → engage → connect)
- Signal-based targeting (trigger events)
- Weekly activity cadence with LinkedIn limits
- Lead qualification criteria

## Pillar 3: Outreach Sequences
- Connection request templates with A/B variants (under 300 chars each, show char count)
- First message after connection (A/B variants)
- {timeline or "90-day"} follow-up cadence with multi-channel branching
- Partnership pitch message (under 1900 chars for InMail)
- Re-engagement templates
- A/B testing protocol: sample sizes, success metrics, decision criteria

## Pillar 4: Partnership Tracking
- CRM pipeline stages with entry/exit criteria
- Custom properties and fields
- KPI dashboard metrics
- n8n workflow specs (workflow name, trigger, key nodes, purpose)

## Pillar 5: 90-Day Implementation Roadmap

**Phase 1: Foundation (Days 1-30)**
- Week 1-2: Define ICP, set up CRM pipeline, create templates
- Week 3-4: Begin prospecting, launch first outreach sequences

**Phase 2: Scale (Days 31-60)**
- Week 5-6: Evaluate A/B test results, optimize winning sequences
- Week 7-8: Scale outreach volume, add follow-up channels (email, phone)

**Phase 3: Optimize (Days 61-90)**
- Week 9-10: Review pipeline velocity, adjust scoring, refine ICP
- Week 11-12: Document playbook, set up recurring automation, plan for scale

## Inter-Agent Handoff Recommendations
- **Compliance Agent**: Review all outreach copy for regulatory compliance (TCPA, CAN-SPAM, GDPR)
- **Legal Strategy Agent**: Draft partnership agreement templates, NDAs for qualified prospects
- **Lifecycle Marketing Agent**: Design email/SMS nurture for prospects who engage beyond LinkedIn
- **Sales Ops Agent**: Build CRM pipeline infrastructure and implement automation sequences
- **Performance Marketer Agent**: Launch paid LinkedIn campaigns to complement organic outreach
- **Marketing Analytics Agent**: Set up attribution tracking for partner-sourced leads
- **Workflow Builder Agent**: Implement n8n workflows from the tracking specs

Flag all benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.65,
            )

            title = f"LinkedIn Lead Gen Strategy: {partnership_goal[:50]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="linkedin_lead_gen_strategy",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
                "suggested_next_steps": [
                    "Send outreach copy to Compliance Agent for regulatory review",
                    "Ask Legal Strategy Agent to draft partnership agreement / NDA templates",
                    "Ask Lifecycle Marketing Agent to design multi-channel nurture beyond LinkedIn",
                    "Ask Sales Ops Agent to build CRM pipeline and automation infrastructure",
                    "Ask Workflow Builder Agent to implement n8n workflows from tracking specs",
                    "Ask Performance Marketer Agent to plan paid LinkedIn ad campaigns",
                ],
            }
