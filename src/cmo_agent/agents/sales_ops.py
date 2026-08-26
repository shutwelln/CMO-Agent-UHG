"""Sales Operations Agent - revenue process design, CRM architecture, and sales automation."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

_SALES_OPS_CRITERIA = [
    QualityCriterion(
        name="process_completeness",
        description="All pipeline stages, entry/exit criteria, and automation rules are fully specified",
    ),
    QualityCriterion(
        name="implementation_readiness",
        description="Specs are detailed enough for CRM configuration or n8n workflow implementation",
    ),
    QualityCriterion(
        name="metric_alignment",
        description="KPIs, SLAs, and velocity metrics are appropriate for the sales motion and team size",
    ),
    QualityCriterion(
        name="automation_feasibility",
        description="Automation sequences and n8n recommendations are technically achievable",
    ),
    QualityCriterion(
        name="handoff_clarity",
        description="Marketing-to-sales handoff criteria, lead scoring, and routing rules are unambiguous",
    ),
]


class SalesOpsAgent(BaseAgent):
    """Designs scalable sales processes, CRM pipelines, automation sequences, and partner revenue workflows."""

    agent_id = "sales_ops_agent"
    agent_name = "Sales Operations Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._workspace_mgr = workspace_manager
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Sales Operations Agent, a specialist in designing scalable revenue process infrastructure for lean teams.

Your mission: Design sales processes, CRM architecture, automation sequences, and partner revenue workflows that are immediately implementable — not theoretical frameworks.

Your expertise covers:

SALES PROCESS DESIGN:
- Inbound and outbound sales process architecture
- PLG (product-led growth) sales motions and hybrid models
- Sales stage definitions with clear entry/exit criteria
- Velocity metrics and pipeline math
- Deal qualification frameworks (BANT, MEDDIC, SPICED)
- Sales methodology selection and implementation

CRM PIPELINE ARCHITECTURE:
- Pipeline design for HubSpot, Salesforce, Pipedrive, Close, and other CRMs
- Custom properties, deal stages, and lifecycle stages
- Required vs optional fields per stage
- Automation rules (stage progression, assignment, notifications)
- Data hygiene and deduplication strategies
- Reporting views and dashboard design

SALES AUTOMATION:
- Lead routing and round-robin assignment
- Outbound sequence design (email, LinkedIn, phone cadences)
- Follow-up automation and task creation
- Deal stage-triggered actions
- Meeting scheduling and handoff workflows
- Re-engagement and recycling sequences

MQL/SQL HANDOFF:
- Marketing-qualified lead (MQL) definition and criteria
- Sales-qualified lead (SQL) acceptance criteria
- Handoff SLA design (response time, required info)
- Feedback loops (accepted/rejected with reasons)
- Lead routing rules at handoff point
- Re-engagement rules for rejected leads
- Joint reporting metrics (handoff volume, acceptance rate)

LEAD SCORING:
- Fit scoring (firmographic/demographic signals)
- Engagement scoring (behavioral signals)
- Scoring thresholds for MQL/SQL transitions
- Score decay rules for inactive leads
- Negative scoring signals
- Model calibration guidance

PARTNER REVENUE:
- Affiliate program architecture
- Referral program design and incentive structures
- Channel partner onboarding and enablement
- Co-selling and deal registration workflows
- Revenue share and commission models
- Partner performance tracking

COMPENSATION & QUOTA:
- Sales compensation plan design (base/variable split, accelerators)
- Quota setting methodology
- Territory planning
- SPIFs and contest design
- Ramp plans for new hires

n8n AWARENESS:
This system operates on an n8n-powered automation platform. When designing automation:
- Recommend specific n8n workflow patterns (webhook triggers, CRM nodes, conditional routing, scheduled checks)
- Reference n8n node types where applicable (HTTP Request, IF, Switch, Slack, Email Send)
- Design automations that can be directly implemented as n8n workflows
- Consider error handling and retry logic in workflow design

SCOPE BOUNDARIES:
- YOU handle: Sales process infrastructure, CRM pipelines, lead routing/scoring, MQL/SQL handoff, sales automation logic, partner programs, compensation models, pipeline metrics
- Performance Marketer handles: Paid ad campaigns, ROAS, ad spend optimization
- Lifecycle Marketing handles: Email/SMS/push messaging content and flows
- Acquisition handles: Landing page CRO, post-traffic funnel experiments
- Marketing Analytics handles: GA4 events, UTM governance, attribution modeling

When your designs overlap with other agents' domains, note the collaboration point. For example: "The outbound sequence structure is defined here — delegate actual email copy to the Writer Agent or messaging flow design to the Lifecycle Marketing Agent."

IMPORTANT RULES:
- Design for LEAN TEAMS — assume no dedicated sales ops headcount
- All process designs should be immediately implementable, not aspirational
- Include specific CRM field names, automation trigger conditions, and metric formulas
- When recommending automation, include n8n workflow patterns where relevant
- Always consider the full lifecycle: what triggers this, what happens next, what if it fails
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="design_sales_process",
            description="Design a complete sales process for a specific go-to-market motion. Covers stages, qualification, velocity metrics, and team structure. Saves as draft.",
        )
        async def design_sales_process(
            workspace_id: str,
            go_to_market_motion: str,
            team_size: int,
            current_tools: Optional[str] = None,
            avg_deal_size: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Design a complete sales process for the following context.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
GO-TO-MARKET MOTION: {go_to_market_motion}
TEAM SIZE: {team_size} people
CURRENT TOOLS: {current_tools or "Not specified"}
AVERAGE DEAL SIZE: {avg_deal_size or "Not specified"}

Structure the sales process design:

## 1. Sales Motion Overview
- Motion type and rationale
- Buyer journey stages mapped to sales stages
- Expected cycle length and velocity targets

## 2. Pipeline Stages
For each stage:
- **Stage name**
- **Entry criteria**: What must be true to enter this stage
- **Exit criteria**: What must be true to advance
- **Required actions**: What the rep must do in this stage
- **Required data**: Fields that must be populated
- **Max time in stage**: SLA before escalation/recycling
- **Conversion target**: Expected stage-to-stage conversion rate

## 3. Qualification Framework
- Recommended framework (BANT/MEDDIC/SPICED) with rationale
- Qualification questions per stage
- Disqualification criteria and recycling rules

## 4. Velocity Metrics & Pipeline Math
- Pipeline coverage ratio target
- Stage conversion benchmarks
- Average time-in-stage targets
- Revenue forecasting formula
- Leading indicators to monitor

## 5. Team Structure & Roles
- Role definitions for a team of {team_size}
- Handoff points between roles
- Capacity planning guidelines

## 6. Automation Opportunities
- Which stages/actions can be automated
- Recommended automation triggers and actions
Note: This system uses n8n for workflow automation. Where relevant, mention how stages/rules could be automated via n8n workflows.

## 7. Implementation Roadmap
- Week 1-2: Quick wins
- Week 3-4: Core process
- Month 2: Optimization"""

            config = RefinementConfig(
                criteria=_SALES_OPS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="sales_process_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Sales Process: {go_to_market_motion} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="sales_process_map",
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
            name="define_crm_pipeline",
            description="Define a CRM pipeline architecture with stages, properties, automation rules, and reporting views for a specific CRM platform. Saves as draft.",
        )
        async def define_crm_pipeline(
            workspace_id: str,
            crm_platform: str,
            pipeline_type: str,
            deal_stages: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            stages_str = ", ".join(deal_stages) if deal_stages else "Recommend optimal stages"

            prompt = f"""Define a complete CRM pipeline architecture for the following context.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
CRM PLATFORM: {crm_platform}
PIPELINE TYPE: {pipeline_type}
DEAL STAGES: {stages_str}

Structure the CRM pipeline definition:

## 1. Pipeline Overview
- Pipeline name and purpose
- Expected deal flow and volume
- Key metrics this pipeline tracks

## 2. Deal Stages
For each stage:
- **Stage name** (CRM-formatted: no spaces, lowercase for API)
- **Display name**
- **Win probability %**
- **Stage description** (for rep guidance)
- **Required properties** before advancing
- **Automation triggers** on entry/exit

## 3. Custom Properties
For each property:
- **Property name** (API name)
- **Display label**
- **Field type** (text, number, dropdown, date, etc.)
- **Options** (if dropdown)
- **Required at stage**: Which stage requires this
- **Description**: What reps should enter

## 4. Lifecycle Stage Mapping
- How deal stages map to contact/company lifecycle stages
- When lifecycle stages should auto-update

## 5. Automation Rules
For each rule:
- **Trigger**: What event fires this
- **Action**: What happens
- **Conditions**: Any filters/guards
Note: This system uses n8n for workflow automation. Where relevant, mention how rules could be implemented as n8n workflows.

## 6. Views & Reports
- Default pipeline view configuration
- Key reports to create
- Dashboard widgets recommended

## 7. {crm_platform}-Specific Implementation Notes
- Platform-specific settings and configurations
- Known limitations and workarounds
- API considerations for integration"""

            crm_config = RefinementConfig(
                criteria=_SALES_OPS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="sales_crm_pipeline_refinement",
            )
            crm_hooks = build_hook_chain(make_em_dash_hook())
            crm_loop = RefinementLoop(
                config=crm_config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            crm_result = await crm_loop.generate_and_refine(prompt, brand_voice, crm_hooks)

            title = f"CRM Pipeline: {crm_platform} {pipeline_type} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="crm_pipeline",
                title=title,
                body=crm_result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": crm_result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="build_automation_sequences",
            description="Design sales automation sequences with triggers, steps, timing, and n8n workflow recommendations. Saves as draft.",
        )
        async def build_automation_sequences(
            workspace_id: str,
            sequence_type: str,
            target_segment: str,
            channels: List[str],
            goal: str,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            channels_str = ", ".join(channels)

            prompt = f"""Design a sales automation sequence for the following context.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
SEQUENCE TYPE: {sequence_type}
TARGET SEGMENT: {target_segment}
CHANNELS: {channels_str}
GOAL: {goal}

Structure the automation sequence:

## 1. Sequence Overview
- Sequence name and purpose
- Target audience definition
- Entry trigger(s)
- Exit conditions (goal met, unsubscribe, max touches)
- Expected duration and touch count

## 2. Sequence Steps
For each step:
- **Step #**: Sequential number
- **Day/Timing**: When this fires (Day 0, Day 2, etc.)
- **Channel**: {channels_str}
- **Action type**: Email, task, notification, field update, etc.
- **Content brief**: What this touchpoint communicates (2-3 sentences)
- **Subject line / message hook** (if applicable)
- **Personalization tokens**: What data to merge
- **Branch condition**: If/then logic after this step

## 3. Branching Logic
- Decision points and branches
- How replies/engagement change the path
- Fallback paths for non-responders

## 4. Performance Metrics
- Key metrics to track per step
- Sequence-level success metrics
- Benchmarks to target

## 5. A/B Testing Opportunities
- Which steps to test first
- What variables to test
- Minimum sample size guidance

## n8n Implementation
Recommend specific n8n workflow patterns to implement this automation:
- Trigger type (webhook, schedule, CRM event)
- Key nodes (IF, Switch, HTTP Request, CRM nodes, Slack, Email)
- Branching logic implementation
- Error handling approach
- Timing/delay implementation
This system runs on n8n — make recommendations concrete and implementable.

## 6. Implementation Checklist
- Prerequisites (data, integrations, content)
- Setup steps in order
- Testing plan before activation"""

            auto_config = RefinementConfig(
                criteria=_SALES_OPS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="sales_automation_refinement",
            )
            auto_hooks = build_hook_chain(make_em_dash_hook())
            auto_loop = RefinementLoop(
                config=auto_config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            auto_result = await auto_loop.generate_and_refine(prompt, brand_voice, auto_hooks)

            title = f"Sales Automation: {sequence_type} - {target_segment}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="sales_automation",
                title=title,
                body=auto_result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": auto_result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="plan_partner_revenue",
            description="Design a partner/affiliate/referral revenue program with structure, incentives, workflows, and tracking. Saves as draft.",
        )
        async def plan_partner_revenue(
            workspace_id: str,
            partner_type: str,
            revenue_model: str,
            current_state: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Design a partner revenue program for the following context.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
PARTNER TYPE: {partner_type}
REVENUE MODEL: {revenue_model}
CURRENT STATE: {current_state or "Starting from scratch"}

Structure the partner revenue plan:

## 1. Program Overview
- Program name and positioning
- Value proposition for partners
- Target partner profile
- Revenue model details ({revenue_model})

## 2. Program Structure
- Partner tiers (if applicable) with requirements and benefits
- Commission/revenue share rates per tier
- Payment terms and schedule
- Minimum thresholds and clawback rules

## 3. Partner Onboarding
- Application and vetting process
- Onboarding checklist (steps, timeline)
- Training and enablement materials needed
- Technical setup (tracking, portal access)

## 4. Deal Flow & Attribution
- How deals are registered/attributed
- Deal registration rules and protection windows
- Conflict resolution for overlapping deals
- Attribution tracking mechanism

## 5. Partner Enablement
- Sales materials and co-branded assets
- Product training requirements
- Communication cadence (newsletters, updates)
- Support escalation path

## 6. Incentive Design
- Base commission structure
- Accelerators and bonuses
- SPIFs for strategic priorities
- Non-monetary incentives (certification, co-marketing)

## 7. Tracking & Reporting
- KPIs to track per partner
- Partner scorecard metrics
- Reporting cadence and format
- Dashboard requirements
Note: This system uses n8n for workflow automation. Where relevant, mention how tracking/notifications could be automated via n8n workflows.

## 8. Legal & Compliance
- Key agreement terms to include
- Revenue recognition considerations
- Regulatory requirements (if applicable)

## 9. Launch Plan
- Phase 1: Pilot (timeline, target partners)
- Phase 2: Scale (expansion criteria)
- Phase 3: Optimize (data-driven improvements)"""

            partner_config = RefinementConfig(
                criteria=_SALES_OPS_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="sales_partner_revenue_refinement",
            )
            partner_hooks = build_hook_chain(make_em_dash_hook())
            partner_loop = RefinementLoop(
                config=partner_config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            partner_result = await partner_loop.generate_and_refine(
                prompt, brand_voice, partner_hooks
            )

            title = f"Partner Revenue: {partner_type} - {revenue_model}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="partner_revenue_plan",
                title=title,
                body=partner_result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": partner_result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="create_sales_metrics_framework",
            description="Create a sales metrics and reporting framework with KPIs, formulas, benchmarks, and dashboard specs. Saves as draft.",
        )
        async def create_sales_metrics_framework(
            workspace_id: str,
            sales_motion: str,
            team_structure: str,
            reporting_audience: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a sales metrics and reporting framework for the following context.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
SALES MOTION: {sales_motion}
TEAM STRUCTURE: {team_structure}
REPORTING AUDIENCE: {reporting_audience or "Sales leadership and executive team"}

Structure the metrics framework:

## 1. Metrics Hierarchy
- North star metric and formula
- Primary KPIs (3-5) with formulas and targets
- Secondary metrics grouped by category
- Leading vs lagging indicator classification

## 2. Pipeline Metrics
For each metric:
- **Name**
- **Formula**: Exact calculation
- **Benchmark**: Industry target range
- **Frequency**: How often to measure
- **Data source**: Where this comes from
Include: pipeline coverage, velocity, conversion rates, ASP, cycle time, win rate

## 3. Activity Metrics
- Rep activity benchmarks (calls, emails, meetings)
- Activity-to-outcome ratios
- Efficiency metrics (time allocation)

## 4. Revenue Metrics
- Bookings vs revenue recognition
- Expansion/contraction/churn tracking
- Forecast accuracy measurement
- Quota attainment distribution

## 5. Funnel Metrics
- Stage-to-stage conversion rates
- Drop-off analysis framework
- Time-in-stage benchmarks
- Bottleneck identification method

## 6. Team Performance
- Individual rep scorecards
- Ramp tracking for new hires
- Coaching signal metrics
- Territory performance comparison

## 7. Reporting Cadence
| Report | Audience | Frequency | Key Metrics |
|--------|----------|-----------|-------------|
(Fill in recommended reports)

## 8. Dashboard Specifications
- Executive dashboard (what to show)
- Manager dashboard (what to show)
- Rep dashboard (what to show)
- Data refresh requirements
Note: This system uses n8n for workflow automation. Where relevant, mention how data pipelines and alerts could be automated via n8n workflows."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.5,
            )

            title = f"Sales Metrics: {sales_motion} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="sales_metrics_framework",
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
            name="align_marketing_sales_handoff",
            description="Design the marketing-to-sales handoff process including MQL/SQL definitions, SLA, feedback loops, routing rules, and n8n workflow patterns. Saves as draft.",
        )
        async def align_marketing_sales_handoff(
            workspace_id: str,
            marketing_channels: List[str],
            sales_team_size: int,
            current_mql_definition: Optional[str] = None,
            current_sql_definition: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            channels_str = ", ".join(marketing_channels)

            prompt = f"""Design the marketing-to-sales handoff process for the following context.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
MARKETING CHANNELS: {channels_str}
SALES TEAM SIZE: {sales_team_size}
CURRENT MQL DEFINITION: {current_mql_definition or "Not yet defined"}
CURRENT SQL DEFINITION: {current_sql_definition or "Not yet defined"}

Structure the handoff alignment:

## 1. MQL Definition
- Qualification criteria (fit + engagement thresholds)
- Channel-specific MQL rules for: {channels_str}
- MQL scoring threshold (reference lead scoring model)
- Data requirements at MQL (what fields must be populated)

## 2. SQL Acceptance Criteria
- What sales accepts as qualified
- Required validation steps before SQL status
- Rejection reasons taxonomy (standardized list)
- Minimum information requirements

## 3. Handoff SLA
- Marketing → Sales response time SLA
- Required information package at handoff
- Handoff format (notification, CRM assignment, meeting)
- Escalation rules for SLA breaches

## 4. Lead Routing Rules
- Assignment logic (round-robin, territory, expertise, capacity)
- Routing for {sales_team_size}-person team
- Overflow and backup rules
- Priority routing for high-score leads

## 5. Feedback Loop Design
- How sales reports back on lead quality (accept/reject with reason)
- Feedback cadence and format
- How marketing uses feedback to improve
- Closed-loop reporting (MQL → SQL → Opportunity → Revenue)

## 6. Re-engagement Rules
- What happens with rejected leads
- Recycling criteria and cool-down periods
- Nurture sequence triggers for recycled leads
- Re-MQL criteria

## 7. Joint Reporting Metrics
- Handoff volume and trends
- Acceptance rate by channel/campaign
- Time-to-follow-up tracking
- MQL-to-SQL conversion rate
- SQL-to-Opportunity conversion rate
- Marketing-sourced pipeline and revenue

## 8. Alignment Meeting Cadence
- Weekly/monthly review agenda
- Shared dashboard requirements
- Dispute resolution process

## n8n Implementation
Recommend specific n8n workflow patterns to implement this handoff:
- Trigger type: webhook on MQL threshold reached
- CRM deal/contact creation on handoff
- Slack notification to assigned rep
- SLA timer workflow (check response time, escalate if breached)
- Feedback capture workflow
- Reporting data pipeline
This system runs on n8n — make recommendations concrete and implementable."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.5,
            )

            title = f"Marketing-Sales Handoff: {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="marketing_sales_handoff",
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
            name="build_lead_scoring_model",
            description="Build a lead scoring model with fit/engagement criteria, thresholds, decay rules, and negative signals. Returns structured JSON (not saved as draft).",
        )
        async def build_lead_scoring_model(
            workspace_id: str,
            scoring_type: str,
            industry: Optional[str] = None,
            deal_complexity: Optional[str] = None,
        ) -> Dict[str, Any]:
            prompt = f"""Build a lead scoring model for the following context.

SCORING TYPE: {scoring_type}
INDUSTRY: {industry or "General B2B"}
DEAL COMPLEXITY: {deal_complexity or "Medium"}

Return a JSON object with this exact structure:
{{
    "scoring_model": {{
        "name": "Descriptive model name",
        "scoring_type": "{scoring_type}",
        "fit_criteria": [
            {{"signal": "Description of the signal", "points": 10, "category": "firmographic", "data_source": "Where this data comes from"}},
            {{"signal": "Another signal", "points": 15, "category": "demographic", "data_source": "Source"}}
        ],
        "engagement_criteria": [
            {{"signal": "Behavioral signal", "points": 5, "category": "behavioral", "data_source": "Source"}},
            {{"signal": "Another engagement signal", "points": 8, "category": "content", "data_source": "Source"}}
        ],
        "negative_signals": [
            {{"signal": "Negative indicator", "points": -10, "category": "disqualifying", "reason": "Why this reduces score"}},
            {{"signal": "Another negative", "points": -5, "category": "behavioral", "reason": "Reason"}}
        ],
        "mql_threshold": 50,
        "sql_threshold": 80,
        "decay_rules": {{
            "inactive_days": 30,
            "decay_points_per_period": -5,
            "decay_period_days": 7,
            "minimum_score": 0,
            "decay_exempt_stages": ["opportunity", "customer"]
        }},
        "recency_boost": {{
            "days_window": 7,
            "multiplier": 1.5,
            "applicable_signals": ["content", "behavioral"]
        }}
    }},
    "implementation_notes": "Practical notes on implementing this scoring model in a CRM. Include n8n automation recommendations for score calculation and threshold triggers.",
    "calibration_guidance": "How to validate and tune thresholds with real data over 30-60 days.",
    "disclaimer": "Scoring thresholds are starting points and should be calibrated with 30-60 days of real conversion data. Monitor MQL-to-SQL acceptance rate to tune."
}}

Include 8-12 fit criteria, 8-12 engagement criteria, and 4-6 negative signals.
Make points values realistic and differentiated.
Return ONLY valid JSON."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.3,
            )

            try:
                result = json.loads(response.content)
            except json.JSONDecodeError:
                result = {
                    "scoring_model": {
                        "name": f"Lead Scoring Model - {scoring_type}",
                        "scoring_type": scoring_type,
                        "fit_criteria": [],
                        "engagement_criteria": [],
                        "negative_signals": [],
                        "mql_threshold": 50,
                        "sql_threshold": 80,
                        "decay_rules": {
                            "inactive_days": 30,
                            "decay_points_per_period": -5,
                        },
                    },
                    "raw_analysis": response.content,
                    "implementation_notes": "See raw_analysis for full model details.",
                    "disclaimer": "Thresholds should be calibrated with 30-60 days of real data.",
                }

            return result
