"""Telesales & Voice AI Strategy Agent - call center design, scripting, dialing, voice AI."""

from __future__ import annotations

from typing import Any, Dict, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# Quality criteria for telesales content
_TELESALES_CRITERIA = [
    QualityCriterion(
        name="natural_flow",
        description="Script reads naturally and conversationally, not robotic or forced",
    ),
    QualityCriterion(
        name="objection_handling",
        description="Objection responses are empathetic, specific, and move toward resolution",
    ),
    QualityCriterion(
        name="compliance",
        description="Compliance-sensitive areas are properly flagged for review, no unauthorized legal advice",
    ),
    QualityCriterion(
        name="empathy",
        description="Tone demonstrates genuine care and understanding of the prospect's situation",
    ),
    QualityCriterion(
        name="closing_effectiveness",
        description="Close techniques are clear, non-pushy, and provide a logical next step",
    ),
]


class TelesalesAgent(BaseAgent):
    """Handles telesales program design, call scripting, dialing strategy, and voice AI evaluation."""

    agent_id = "telesales_agent"
    agent_name = "Telesales & Voice AI Strategy Agent"

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
        return """You are the Telesales & Voice AI Strategy Agent, a specialist in designing scalable inbound and outbound telesales programs using human agents or voice AI.

Your mission: Design high-performing phone-based sales and service programs that drive revenue through optimized call operations.

Your expertise covers:
- Call center program design (staffing models, routing logic, scheduling, escalation paths, tech stack)
- Campaign scripting (cold call, warm lead, inbound, retention, win-back, upsell/cross-sell)
- Objection handling decision trees with branching logic
- Dialing strategy and cadence optimization (predictive, progressive, power, preview dialers)
- CRM integration architecture (data flow, disposition codes, lead scoring, automation triggers)
- Voice AI platform evaluation frameworks (scoring criteria, capability checklists, cost models)
- Quality assurance frameworks (scorecards, call monitoring, coaching plans)
- KPI design and performance dashboards (conversion rates, handle time, cost per acquisition)

VOICE AI SCOPE:
- You provide vendor-agnostic evaluation frameworks — scoring matrices, decision templates, capability checklists, cost model structures
- You do NOT recommend specific vendors or hardcode vendor names
- Users fill in specific vendors to evaluate using your framework

IMPORTANT RULES:
- All specific benchmark claims MUST be flagged with [VERIFY] prefix
- All strategic plans are saved as drafts for human review
- Focus on operational strategy and creative scripting — NOT regulatory compliance
- When compliance is relevant (disclosures, TCPA windows, DNC rules, consent requirements), flag with [COMPLIANCE REVIEW NEEDED] and recommend running output through the Compliance Agent
- NEVER render compliance opinions, write disclosure language, or advise on regulatory requirements
- Base recommendations on proven telesales methodology and best practices
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels.

SCOPE BOUNDARIES:
- You handle: call center operations, call scripts, dialing strategy, voice AI evaluation, CRM integration, QA frameworks, telesales KPIs
- Compliance Agent handles: ALL regulatory matters (TCPA, TSR, DNC, state telemarketing regs, disclosure language, consent requirements)
- Lifecycle Marketing Agent handles: non-voice channels (email, SMS, push, in-product messaging)
- Performance Marketer Agent handles: paid advertising, campaign architecture, ad spend optimization
- Acquisition Agent handles: web funnels, landing pages, on-site CRO"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="design_call_center_program",
            description="Design a full call center program: staffing model, routing logic, scheduling, escalation paths, tech stack recommendations, and training framework. Flags [COMPLIANCE REVIEW NEEDED] for regulatory items.",
        )
        async def design_call_center_program(
            workspace_id: str,
            program_type: str,
            business_context: str,
            team_size: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Design a comprehensive call center program.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
PROGRAM TYPE: {program_type}  (e.g. outbound sales, inbound support, blended, retention)
BUSINESS CONTEXT: {business_context}
TEAM SIZE: {team_size or "Not specified — recommend optimal staffing"}

Structure the program with these sections:

## 1. Program Overview
- Mission and objectives
- Target audience and ideal customer profile
- Expected call volume and capacity planning

## 2. Staffing Model
- Role breakdown (agents, team leads, QA, trainers)
- Staffing ratios and shift scheduling
- Ramp plan for new hires
- Skills matrix and specialization tracks

## 3. Call Routing & IVR Design
- Routing logic (skills-based, round-robin, priority-based)
- IVR menu structure (keep simple — max 3 levels)
- Escalation paths and warm transfer procedures
- After-hours and overflow handling

## 4. Technology Stack
- Dialer type recommendation (predictive, progressive, power, preview)
- CRM integration requirements
- Call recording and analytics platform
- Workforce management tools

## 5. Training Framework
- Onboarding program structure (timeline, milestones)
- Ongoing coaching cadence
- Call monitoring and feedback loops

## 6. Escalation Matrix
- Tier 1/2/3 escalation criteria
- Manager escalation triggers
- Customer recovery procedures

## 7. Key Metrics & Targets
- Primary KPIs with target ranges [VERIFY specific benchmarks]
- Reporting cadence and dashboard requirements

## 8. Compliance Considerations
[COMPLIANCE REVIEW NEEDED] Flag all areas requiring regulatory review:
- Call recording consent requirements
- Do-not-call list management
- Calling window restrictions
- Required disclosures
- State-specific telemarketing rules
Recommend running this section through the Compliance Agent for full regulatory review.

Flag all benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="call_center_program",
                title=f"Call Center Program: {program_type} - {workspace_id}",
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Call Center Program: {program_type} - {workspace_id}",
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="write_call_script",
            description="Write a call script with opening, pitch, objection handling, and close. Supports human agent and voice AI formats. Flags where disclosures are needed but does not write them.",
        )
        async def write_call_script(
            workspace_id: str,
            campaign_type: str,
            product_or_offer: str,
            target_audience: str,
            voice_ai_format: bool = False,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            format_note = ""
            if voice_ai_format:
                format_note = """
FORMAT: Voice AI compatible
- Use clear decision nodes with branching paths
- Mark each response with intent classification tags
- Include silence/timeout handling (3s, 6s, 10s thresholds)
- Add DTMF fallback options where appropriate
- Keep each speech segment under 30 words for natural delivery"""

            prompt = f"""Write a complete call script for a telesales campaign.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
CAMPAIGN TYPE: {campaign_type}  (e.g. cold call, warm lead follow-up, inbound inquiry, retention, win-back, upsell)
PRODUCT/OFFER: {product_or_offer}
TARGET AUDIENCE: {target_audience}
{format_note}

Structure the script with these sections:

## 1. Pre-Call Prep
- Lead qualification checklist
- CRM data to review before dialing
- Personalization hooks to look for

## 2. Opening (first 15 seconds)
- Greeting and introduction
- Permission-based opening ("Did I catch you at a good time?")
- Pattern interrupt or hook statement
- [COMPLIANCE REVIEW NEEDED] Mark where mandatory disclosures may be required

## 3. Discovery / Qualification
- 3-5 open-ended qualifying questions
- Active listening prompts
- Pain point identification framework

## 4. Value Proposition / Pitch
- Core pitch (30-second version)
- Extended pitch with supporting points
- Social proof and credibility statements [VERIFY any specific claims]
- Benefit-focused language (not feature-focused)

## 5. Objection Handling
- Top 5 expected objections with responses
- "Not interested" recovery path
- Price objection handling
- Competitor comparison responses
- Stall tactics ("send me info" / "call me later")

## 6. Close
- Trial close questions
- Primary close technique
- Alternative close if primary fails
- Next steps and follow-up scheduling
- [COMPLIANCE REVIEW NEEDED] Mark where consent confirmation may be required

## 7. Post-Call Actions
- Disposition code guide
- CRM update requirements
- Follow-up task creation rules

Flag all benchmark claims with [VERIFY].
Flag all compliance-sensitive areas with [COMPLIANCE REVIEW NEEDED]."""

            config = RefinementConfig(
                criteria=_TELESALES_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="telesales_call_script",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)
            body = result.content

            format_label = "Voice AI" if voice_ai_format else "Human Agent"
            title = f"Call Script ({format_label}): {campaign_type} - {product_or_offer[:50]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="call_script",
                title=title,
                body=body,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": body[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="build_objection_tree",
            description="Build a categorized objection handling decision tree with responses, escalation triggers, and optional voice AI branching paths.",
        )
        async def build_objection_tree(
            workspace_id: str,
            product_or_offer: str,
            objection_categories: Optional[str] = None,
            include_voice_ai_branching: bool = False,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            categories = (
                objection_categories or "price, timing, need, trust, competitor, authority, inertia"
            )
            voice_ai_note = ""
            if include_voice_ai_branching:
                voice_ai_note = """
VOICE AI BRANCHING:
- Add intent classification labels to each objection node
- Include confidence threshold triggers (high/medium/low intent match)
- Add human handoff triggers for low-confidence or complex objections
- Include silence/non-response handling at each decision point"""

            prompt = f"""Build a comprehensive objection handling decision tree.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
PRODUCT/OFFER: {product_or_offer}
OBJECTION CATEGORIES: {categories}
{voice_ai_note}

Structure the decision tree:

## Objection Tree Overview
- Total categories and expected frequency distribution [VERIFY]
- Escalation philosophy (handle vs. escalate criteria)

## For EACH objection category, provide:

### [Category Name]
**Trigger phrases**: Common ways prospects express this objection
**Root cause**: Why prospects actually object (surface vs. real reason)
**Response framework**:
  - Acknowledge: Validate the concern
  - Probe: Ask a follow-up to understand specifics
  - Reframe: Shift perspective
  - Evidence: Provide proof point [VERIFY specific claims]
  - Close: Bridge back to next step

**Escalation trigger**: When to escalate to supervisor/closer
**If response fails**: Secondary approach
**Example dialogue**: 2-3 exchange example

## Escalation Matrix
- When to escalate vs. when to gracefully close
- Manager talk-off scripts for escalated objections
- Customer retention save offers (if applicable)

## Training Notes
- Role-play scenarios for each category
- Common mistakes to avoid
- Tone and pace guidance

Flag all benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_TELESALES_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="telesales_objection_tree",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)
            body = result.content

            title = f"Objection Tree: {product_or_offer[:60]}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="objection_tree",
                title=title,
                body=body,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": body[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="recommend_dialing_strategy",
            description="Recommend a dialing strategy: dialer type, cadence rules, time-of-day optimization, attempt limits. Flags compliance-sensitive areas for Compliance Agent review.",
        )
        async def recommend_dialing_strategy(
            workspace_id: str,
            campaign_type: str,
            lead_volume: str,
            team_size: str,
            lead_source: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Recommend a dialing strategy for a telesales campaign.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
CAMPAIGN TYPE: {campaign_type}
LEAD VOLUME: {lead_volume}
TEAM SIZE: {team_size}
LEAD SOURCE: {lead_source or "Mixed sources — optimize for general use"}

Structure the recommendation:

## 1. Dialer Type Recommendation
- Recommended dialer: predictive / progressive / power / preview
- Rationale (based on team size, lead quality, campaign type)
- Configuration parameters (dial ratio, abandon rate threshold [VERIFY])
- When to switch dialer types

## 2. Cadence Design
- Multi-touch cadence (calls, voicemails, follow-ups)
- Day-by-day contact attempt schedule
- Maximum attempts per lead before recycling
- Cool-down periods between attempts

## 3. Time-of-Day Optimization
- Optimal calling windows by day of week [VERIFY]
- Time zone management strategy
- [COMPLIANCE REVIEW NEEDED] Calling hour restrictions (TCPA, state-specific rules — defer to Compliance Agent)
- Power hour scheduling for peak performance

## 4. List Management
- Lead prioritization logic (hot/warm/cold scoring)
- List segmentation strategy
- Recycling rules and re-engagement timing
- DNC list management process
- [COMPLIANCE REVIEW NEEDED] Consent verification procedures — defer to Compliance Agent

## 5. Voicemail Strategy
- When to leave voicemails vs. silent drop
- Voicemail script (under 30 seconds)
- Ringless voicemail considerations
- [COMPLIANCE REVIEW NEEDED] Voicemail compliance requirements — defer to Compliance Agent

## 6. Performance Optimization
- Connect rate targets by dialer type [VERIFY]
- Conversion benchmarks by campaign type [VERIFY]
- A/B testing framework for cadence optimization
- Underperforming lead disposition strategy

Flag all benchmark claims with [VERIFY].
Flag all compliance areas with [COMPLIANCE REVIEW NEEDED]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            title = f"Dialing Strategy: {campaign_type} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="dialing_strategy",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="design_crm_integration",
            description="Design a CRM integration blueprint: data flow, disposition codes, lead scoring, automation triggers, and reporting requirements.",
        )
        async def design_crm_integration(
            workspace_id: str,
            crm_platform: str,
            integration_goals: str,
            current_setup: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Design a CRM integration blueprint for a telesales operation.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
CRM PLATFORM: {crm_platform}  (e.g. Salesforce, HubSpot, Close, custom)
INTEGRATION GOALS: {integration_goals}
CURRENT SETUP: {current_setup or "Greenfield — no existing integration"}

Structure the blueprint:

## 1. Data Architecture
- Lead/contact data model (required fields, custom fields)
- Data flow diagram: Lead source -> CRM -> Dialer -> CRM (round-trip)
- Real-time sync vs. batch sync decisions
- Data hygiene and deduplication rules

## 2. Disposition Code Framework
- Primary disposition codes (Connected, No Answer, Voicemail, Wrong Number, DNC, etc.)
- Sub-disposition codes for each primary
- Auto-actions triggered by each disposition
- Reporting implications of each code

## 3. Lead Scoring Model
- Scoring dimensions (demographic, behavioral, engagement)
- Score ranges and thresholds (hot/warm/cold)
- Score decay rules (time-based depreciation)
- Auto-routing rules based on score

## 4. Automation Triggers
- Post-call automation (email follow-up, task creation, pipeline updates)
- Inbound lead routing rules
- Re-engagement triggers (cold leads, stalled deals)
- Alert triggers (high-value lead, VIP customer)

## 5. Pipeline Management
- Sales stages and stage definitions
- Stage exit criteria
- Pipeline velocity metrics
- Stale deal handling rules

## 6. Reporting & Dashboards
- Agent performance dashboard fields
- Campaign performance metrics
- Pipeline health indicators
- Data export and BI integration requirements

## 7. Implementation Roadmap
- Phase 1: Core integration (must-have)
- Phase 2: Automation layer
- Phase 3: Advanced analytics
- Technical requirements and API considerations"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            title = f"CRM Integration: {crm_platform} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="crm_integration",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="evaluate_voice_ai_vendors",
            description="Generate a vendor-agnostic voice AI evaluation framework: scoring criteria matrix, decision template, capability checklist, and cost model structure. Users fill in specific vendors.",
        )
        async def evaluate_voice_ai_vendors(
            workspace_id: str,
            use_case: str,
            call_volume: str,
            key_requirements: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a vendor-agnostic voice AI evaluation framework.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
USE CASE: {use_case}  (e.g. outbound sales, inbound routing, appointment setting, lead qualification, customer service)
EXPECTED CALL VOLUME: {call_volume}
KEY REQUIREMENTS: {key_requirements or "General evaluation — cover all major capability areas"}

IMPORTANT: This is a vendor-agnostic framework. Do NOT name specific vendors. Create blank evaluation templates that the user fills in with their shortlisted vendors.

Structure the framework:

## 1. Evaluation Criteria Matrix
Create a weighted scoring matrix with these categories:
- Voice Quality & Naturalness (weight: __)
- Conversation Intelligence (intent detection, context handling)
- Integration Capabilities (CRM, dialer, telephony)
- Customization & Training (prompt engineering, fine-tuning)
- Scalability & Reliability (uptime SLA, concurrent call capacity)
- Analytics & Reporting
- Compliance & Security
- Pricing Model & Total Cost of Ownership
For each category: scoring criteria (1-5), weight, and evaluation method

## 2. Capability Checklist
Must-have capabilities vs. nice-to-have for this use case:
- Speech recognition accuracy
- Multi-language support
- Latency (response time)
- Interruption handling
- Sentiment detection
- Human handoff triggers and execution
- Call recording and transcription
- Custom voice/persona
- A/B testing capability

## 3. Decision Template
Blank comparison template:
| Criteria | Weight | Vendor A | Vendor B | Vendor C |
Format for side-by-side vendor comparison

## 4. Cost Model Structure
- Per-minute vs. per-call vs. per-seat pricing comparison framework
- Hidden cost checklist (setup, training, overage, API calls, telephony)
- TCO calculation template (Year 1, Year 2, Year 3)
- Break-even analysis vs. human agents framework

## 5. POC Test Plan
- Test scenario design (10-15 test calls per vendor)
- Evaluation rubric for POC results
- Success criteria and go/no-go thresholds
- Timeline template for POC execution

## 6. Risk Assessment Template
- Vendor lock-in risk factors to evaluate
- Data ownership and portability questions
- Business continuity considerations
- Regulatory compliance questions to ask [COMPLIANCE REVIEW NEEDED]

Flag compliance areas with [COMPLIANCE REVIEW NEEDED]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            title = f"Voice AI Evaluation Framework: {use_case}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="voice_ai_evaluation",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="design_qa_framework",
            description="Design a QA framework: scorecard, call monitoring cadence, coaching plans, and performance improvement processes. Flags compliance audit items for Compliance Agent.",
        )
        async def design_qa_framework(
            workspace_id: str,
            team_type: str,
            focus_areas: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Design a comprehensive QA framework for a telesales team.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
TEAM TYPE: {team_type}  (e.g. outbound sales, inbound support, blended, retention)
FOCUS AREAS: {focus_areas or "Full QA coverage — all dimensions"}

Structure the framework:

## 1. QA Scorecard
Design a 100-point scorecard with weighted categories:
- Opening / Greeting (__ points)
- Discovery / Needs Analysis (__ points)
- Product Knowledge / Pitch (__ points)
- Objection Handling (__ points)
- Closing Technique (__ points)
- Compliance Adherence (__ points) [COMPLIANCE REVIEW NEEDED — specific compliance criteria should be defined by Compliance Agent]
- Professionalism / Soft Skills (__ points)
- CRM Documentation (__ points)
For each category: specific evaluation criteria, scoring rubric (1-5), and examples of excellent/poor performance

## 2. Call Monitoring Program
- Monitoring cadence (calls per agent per week/month)
- Random vs. targeted monitoring balance
- Live monitoring vs. recorded review ratio
- Side-by-side coaching sessions frequency
- Calibration sessions (QA team alignment)

## 3. Coaching Framework
- 1:1 coaching cadence and structure
- Call review session format (listen together, self-assessment first)
- Performance improvement plan (PIP) template and triggers
- Peer coaching and buddy system design
- Recognition and incentive program

## 4. Performance Tiers
- Define performance tiers: Top Performer / Meeting Expectations / Needs Improvement / PIP
- Tier criteria (QA score ranges, conversion rates, handle time)
- Tier-specific coaching intensity
- Promotion and advancement criteria

## 5. Reporting & Analytics
- QA score trending (individual and team)
- Category-level performance breakdown
- Coaching effectiveness tracking
- Correlation analysis: QA scores vs. conversion rates

## 6. Compliance QA
[COMPLIANCE REVIEW NEEDED] The following areas need Compliance Agent review:
- Required disclosure verification
- Consent capture verification
- DNC compliance monitoring
- Call recording notification compliance
- Script adherence for regulated content
Recommend running compliance-specific scorecard items through the Compliance Agent.

Flag all benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            title = f"QA Framework: {team_type} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="qa_framework",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="generate_kpi_dashboard",
            description="Generate a KPI hierarchy, targets, benchmarks, reporting cadence, alert thresholds, and ROI framework for telesales operations.",
        )
        async def generate_kpi_dashboard(
            workspace_id: str,
            operation_type: str,
            current_metrics: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Generate a comprehensive KPI dashboard framework for telesales operations.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
OPERATION TYPE: {operation_type}  (e.g. outbound sales, inbound support, blended, appointment setting)
CURRENT METRICS: {current_metrics or "No baseline — use industry benchmarks [VERIFY]"}

Structure the dashboard:

## 1. KPI Hierarchy
Organize metrics in a pyramid:

### North Star Metric
- The single metric that best represents success for this operation

### Primary KPIs (4-6 metrics)
For each: definition, formula, target range [VERIFY], measurement frequency

### Secondary KPIs (6-10 metrics)
For each: definition, formula, target range [VERIFY], measurement frequency

### Operational Metrics (8-12 metrics)
For each: definition, formula, healthy range [VERIFY], measurement frequency

## 2. Metric Definitions & Formulas
For every metric:
- Clear definition (what it measures, what it excludes)
- Calculation formula
- Data source
- Reporting granularity (real-time / daily / weekly / monthly)

## 3. Target Setting Framework
- Industry benchmark ranges [VERIFY]
- How to set targets (percentile-based, improvement-based, or absolute)
- Ramp period targets for new teams/agents
- Seasonal adjustment considerations

## 4. Alert Thresholds
For key metrics define:
- Green zone (on track)
- Yellow zone (needs attention — trigger coaching)
- Red zone (critical — trigger management review)
- Alert delivery method and escalation

## 5. Reporting Cadence
- Real-time wallboard metrics
- Daily performance summary
- Weekly team review metrics
- Monthly business review package
- Quarterly strategic review

## 6. ROI Framework
- Revenue attribution model
- Cost per acquisition (CPA) calculation
- Agent-level ROI tracking
- Campaign-level ROI comparison
- Break-even analysis template
- LTV:CAC impact tracking

## 7. Dashboard Layout
- Executive view (5 key metrics)
- Manager view (team + individual drill-down)
- Agent view (personal scorecard)
- Campaign view (campaign-level comparison)

Flag all benchmark claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            title = f"KPI Dashboard: {operation_type} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="kpi_dashboard",
                title=title,
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": response.content[:500],
                "status": "pending",
            }
