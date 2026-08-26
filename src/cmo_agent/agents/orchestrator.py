"""CMO Orchestrator Agent - delegates to sub-agents and manages workflows."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from ..core.state import AgentContext
from ..db.database import Database
from ..db.repositories import (
    DraftRepo,
    OpportunityRepo,
    SourceRepo,
    WorkspaceRepo,
)
from ..llm.base import BaseLLM
from ..n8n.client import N8NClient
from ..routing.catalog import AGENT_TOOL_GROUPS
from ..workspace.manager import WorkspaceManager
from .base import AgentResult, BaseAgent

logger = structlog.get_logger()

# ── Visual routing: deterministic Python routing (no LLM decision) ──────

_COMPOSITION_TYPES = frozenset(
    {
        "diagram",
        "infographic",
        "dashboard",
        "flow",
        "flowchart",
        "timeline",
        "comparison",
        "ecosystem",
        "hero_banner",
        "quote",
        "process",
        "grid",
        "scorecard",
        "map",
        "chart",
    }
)

_COMPOSITION_KEYWORDS = frozenset(
    {
        "diagram",
        "infographic",
        "flow",
        "ecosystem",
        "dashboard",
        "process",
        "comparison",
        "timeline",
        "chart",
        "funnel",
        "architecture",
        "hierarchy",
        "kpi",
        "metrics",
        "scorecard",
    }
)


def _needs_composition(visual_type: str, description: str) -> bool:
    """Deterministic check: should this visual go through the composition pipeline?"""
    if visual_type.lower() in _COMPOSITION_TYPES:
        return True
    lower = description.lower()
    return any(kw in lower for kw in _COMPOSITION_KEYWORDS)


class CMOOrchestratorAgent(BaseAgent):
    """Top-level orchestrator that delegates to specialized sub-agents.

    Registers each sub-agent as a tool so the LLM can decide when to delegate.
    Also carries forward the existing n8n workflow tools.
    """

    agent_id = "cmo_orchestrator"
    agent_name = "CMO Orchestrator Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        n8n_client: N8NClient,
        workspace_manager: WorkspaceManager,
        research_agent: Optional[BaseAgent] = None,
        reddit_agent: Optional[BaseAgent] = None,
        google_alerts_agent: Optional[BaseAgent] = None,
        writer_agent: Optional[BaseAgent] = None,
        visual_agent: Optional[BaseAgent] = None,
        video_agent: Optional[BaseAgent] = None,
        deck_agent: Optional[BaseAgent] = None,
        performance_marketer_agent: Optional[BaseAgent] = None,
        social_media_agent: Optional[BaseAgent] = None,
        workflow_healer_agent: Optional[BaseAgent] = None,
        workflow_builder_agent: Optional[BaseAgent] = None,
        docs_agent: Optional[BaseAgent] = None,
        sheets_agent: Optional[BaseAgent] = None,
        motion_graphics_agent: Optional[BaseAgent] = None,
        lifecycle_marketing_agent: Optional[BaseAgent] = None,
        growth_ideas_agent: Optional[BaseAgent] = None,
        marketing_analytics_agent: Optional[BaseAgent] = None,
        acquisition_agent: Optional[BaseAgent] = None,
        conversion_optimization_agent: Optional[BaseAgent] = None,
        compliance_agent: Optional[BaseAgent] = None,
        legal_strategy_agent: Optional[BaseAgent] = None,
        telesales_agent: Optional[BaseAgent] = None,
        sales_ops_agent: Optional[BaseAgent] = None,
        linkedin_partnerships_agent: Optional[BaseAgent] = None,
        knowledge_base_agent: Optional[BaseAgent] = None,
        experiment_engineer_agent: Optional[BaseAgent] = None,
        editorial_agent: Optional[BaseAgent] = None,
        gtm_agent: Optional[BaseAgent] = None,
        seo_aeo_agent: Optional[BaseAgent] = None,
        composition_planner_agent: Optional[BaseAgent] = None,
        ux_ui_design_agent: Optional[BaseAgent] = None,
        media_storage: Optional[Any] = None,
        router: Optional[Any] = None,  # Optional[AgentRouter]
        max_iterations: int = 10,
    ) -> None:
        self._n8n = n8n_client
        self._workspace_mgr = workspace_manager
        self._research = research_agent
        self._reddit = reddit_agent
        self._google_alerts = google_alerts_agent
        self._writer = writer_agent
        self._visual = visual_agent
        self._video = video_agent
        self._deck = deck_agent
        self._performance_marketer = performance_marketer_agent
        self._social_media = social_media_agent
        self._workflow_healer = workflow_healer_agent
        self._workflow_builder = workflow_builder_agent
        self._docs = docs_agent
        self._sheets = sheets_agent
        self._motion_graphics = motion_graphics_agent
        self._lifecycle_marketing = lifecycle_marketing_agent
        self._growth_ideas = growth_ideas_agent
        self._marketing_analytics = marketing_analytics_agent
        self._acquisition = acquisition_agent
        self._conversion_optimization = conversion_optimization_agent
        self._compliance = compliance_agent
        self._legal_strategy = legal_strategy_agent
        self._telesales = telesales_agent
        self._sales_ops = sales_ops_agent
        self._linkedin_partnerships = linkedin_partnerships_agent
        self._knowledge_base = knowledge_base_agent
        self._experiment_engineer = experiment_engineer_agent
        self._editorial = editorial_agent
        self._gtm = gtm_agent
        self._seo_aeo = seo_aeo_agent
        self._composition_planner = composition_planner_agent
        self._ux_ui_design = ux_ui_design_agent
        self._media_storage = media_storage
        self._router = router
        self._selected_tool_names: Optional[List[str]] = None
        self._workspaces = WorkspaceRepo(db)
        self._opportunities = OpportunityRepo(db)
        self._drafts = DraftRepo(db)
        self._sources = SourceRepo(db)
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        ws_label = workspace_id or "default workspace"
        # Use slim prompt when router has pre-selected tools
        if self._router is not None and self._selected_tool_names is not None:
            return self._get_slim_system_prompt(ws_label)
        return self._get_full_system_prompt(ws_label)

    def _get_slim_system_prompt(self, ws_label: str) -> str:
        """Compact system prompt used when the router has already selected tools."""
        return f"""You are the CMO Agent — an AI-powered Chief Marketing Officer running a full marketing and revenue organization for {ws_label}.
You lead specialized agents across content production, marketing strategy, sales & revenue, legal & compliance, and operations/intelligence.
You have been given the specific tool(s) needed for this request. Delegate to the tool provided.

CRITICAL RULES:
- NEVER explain what you cannot do. Delegate to the tool immediately.
- NEVER generate document/spreadsheet/presentation content yourself — use the agent tool.
- When you receive a result, extract and display any URLs prominently.
- For visuals: follow the 4-step flow: (1) Ask what the visual should show, (2) Present plan with cost info, (3) Wait for approval, (4) Call the visual tool. For SINGLE images: use create_visual. For MULTIPLE VARIANTS of the same content: use create_visual_variants (generates N stylistically different AI images — corporate, vibrant, minimal, dark-tech). Default tier is "high" (Gemini) for best quality. If create_visual fails, report the error — do NOT fall back to deck_agent or other agents. CRITICAL: The description parameter must contain the FULL ACCUMULATED brief — the user's original request VERBATIM plus ALL follow-up answers, clarifications, and additional context. Include EVERYTHING: structure, phases, groupings, counts, emphasis areas, titles, format preferences.
- For video and motion graphics: use video_agent (AI-generated clips via fal.ai Kling, OpenAI Sora). Follow the 4-step flow with tier/cost options.
- ANIMATED INFOGRAPHIC CHAINING: For "animated infographic/diagram/dashboard" requests, first generate the static image via create_visual (Gemini), then animate it via video_agent's generate_video with image_url set to the generated image URL. Best quality: Gemini design + AI video animation.
- Always tell the user what you're doing and present results clearly.
- NEVER ask the user for brand guidelines, colors, metrics, or report data if reference documents are available (see below). The sub-agents will use the reference documents automatically.
- ABBREVIATIONS: Always spell out abbreviations/acronyms on first use with the abbreviation in parentheses — e.g., "Total Addressable Market (TAM)". After the first occurrence, use the abbreviation only. Include this instruction when delegating to any content-producing agent.
- ANTI-AI WRITING RULES (MANDATORY — apply to ALL content from every agent):
  • NEVER use em dashes (—) or en dashes (–). Use commas, periods, semicolons, or " - " (spaced hyphen) instead.
  • NEVER bold words in the middle of a sentence. Bolding is only acceptable for section headers or standalone labels.
  These are telltale signs of AI-generated text. Enforce these rules when delegating to any content-producing agent.
{self._get_ref_docs_note()}
Current workspace: {ws_label}"""

    def _get_full_system_prompt(self, ws_label: str) -> str:
        """Full system prompt with all agent descriptions and delegation guidelines."""
        return f"""You are the CMO Agent — an AI-powered Chief Marketing Officer running a full marketing and revenue organization for {ws_label}.

You lead a multi-agent team spanning five divisions:
• CONTENT PRODUCTION — writing, images, video, motion graphics, presentations, documents, spreadsheets
• MARKETING STRATEGY — performance marketing, lifecycle (email/SMS/push), social media, analytics, acquisition/CRO, growth ideas, GTM launches
• SALES & REVENUE — telesales/voice AI, sales operations/CRM, LinkedIn partnerships
• LEGAL & COMPLIANCE — regulatory review (FINRA/SEC/TCPA/GDPR/CCPA), contract drafting, risk mitigation
• OPERATIONS & INTELLIGENCE — editorial production, experimentation, knowledge base/memory, workflow building & healing, research & monitoring

You don't just answer marketing questions — you produce real deliverables: Google Docs, Google Sheets, Google Slides, images, videos, motion graphics, n8n automations, contracts, call scripts, CRM blueprints, and more.

You have access to specialized sub-agents:
- research_agent: For RSS feed scanning, fraud/scam monitoring, opportunity scoring, web browsing (fetch_webpage can visit any URL and extract text, links, and site structure), reading spreadsheets (read_spreadsheet reads XLSX/CSV files from the data/ directory), brand color extraction from websites (extract_brand_colors), manual brand color setting (set_brand_colors), and general web research
- reddit_ingest_agent: For Reddit subreddit monitoring, post categorization, and lead discovery
- google_alerts_agent: For scanning Google Alert emails for news and opportunities
- writer_agent: For creating content in brand voice (newsletters, blog posts, Reddit replies, social media)
- create_visual: For ALL image requests — infographics, diagrams, ecosystem maps, photos, illustrations, dashboards, process flows, etc. Generates images directly via AI (Gemini). Default tier is "high" (Gemini, ~$0.05-$0.10) for best quality. Use create_visual_variants for multiple stylistically different versions of the same visual. Returns ONE finished image per call
- video_agent: For ALL video and animation content — video scripts, storyboards, AI-generated video clips, motion graphics, animated infographics (fal.ai Kling, OpenAI Sora)
- deck_agent: For creating Google Slides presentations, pitch decks, and marketing slide decks (outputs native Google Slides links by default)
- performance_marketer_agent: For paid advertising strategy, campaign architecture, A/B testing, budget allocation, ROI analysis, and marketing metrics
- social_media_agent: For social media strategy, content calendars, platform strategy, hashtag research, engagement planning, and content ideas
- workflow_healer_agent: For diagnosing and repairing broken n8n workflows, checking execution health, rolling back failed repairs, and viewing healing history
- workflow_builder_agent: For building new n8n workflows from natural language descriptions. Handles the full lifecycle: design, build, validate, deploy (inactive), test, and activate (production). Presents workflow summaries for user approval before deploying
- docs_agent: For creating Google Docs — reports, briefs, proposals, blog posts, newsletters as live editable documents (returns a direct Google Docs link)
- sheets_agent: For creating Google Sheets — campaign trackers, budget sheets, content calendars, analytics dashboards (returns a direct Google Sheets link). Can also read existing XLSX/CSV files from the data/ directory
- motion_graphics_agent: DEPRECATED — for animations and motion graphics, use video_agent instead (AI-generated video via fal.ai Kling, OpenAI Sora produces superior results)
- lifecycle_marketing_agent: For customer lifecycle strategy — email/SMS/push/in-product flows, segmentation, trigger logic, message frameworks, A/B tests, compliance audits (Customer.io, Beehiiv)
- growth_ideas_agent: For generating daily growth ideas based on recent project activity across the workspace, with impact/effort scoring and execution outlines
- marketing_analytics_agent: For marketing measurement strategy, GA4 event taxonomy, UTM naming standards, attribution modeling (MMM/MTA), tracking gap audits, dashboard/reporting requirements, and technical tracking specs (SQL, GTM, dataLayer)
- acquisition_agent: For acquisition funnel architecture, funnel mapping, landing page strategy, friction point analysis, and conversion metric calculation. Identifies WHAT should be optimized and WHY. Does NOT design experiments — hands off to conversion_optimization_agent for experiment design and prioritization
- conversion_optimization_agent: For on-site conversion rate optimization and experimentation governance. VERTICAL-AGNOSTIC: on first engagement with a workspace, run discover_conversion_architecture to learn the site's page types, revenue mechanics, and testable elements — all tools auto-calibrate from that point forward. Designs A/B and multivariate tests, prioritizes experiment backlogs, creates variant briefs for Writer Agent, defines tracking requirements, analyzes experiment results, and validates statistical significance. The experimentation authority for the entire ecosystem — no other agent designs experiments without this agent's oversight
- compliance_agent: For regulatory compliance review in financial services and insurance — FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA, state insurance regulations. Reviews messaging for compliance risks, provides disclosures, flags prohibited claims, advises on consent, generates channel checklists
- legal_strategy_agent: For contract drafting and risk mitigation — NDAs, partnership agreements, term sheets, risk flagging, negotiation strategy, plain-English clause explanations, and full contract review
- telesales_agent: For telesales program design, call scripting, dialing strategy, voice AI evaluation frameworks, CRM integration blueprints, QA frameworks, and KPI dashboards. Handles call center operations — NOT regulatory compliance (defers to compliance agent)
- sales_ops_agent: For revenue process design, CRM pipeline architecture, sales automation sequences, marketing-to-sales handoff alignment, lead scoring models, partner/affiliate/referral revenue workflows, and compensation models. Designs for lean teams. n8n-aware — recommends implementable workflow patterns
- linkedin_partnerships_agent: For LinkedIn partnership lead generation — ICP/partner profiling, LinkedIn prospecting strategy, outreach sequences with A/B variants, follow-up cadences, partnership CRM tracking, and n8n automation recommendations
- knowledge_base_agent: For storing and retrieving durable memory across sessions — decisions, preferences, brand facts, strategic context, benchmarks. Persists across conversations so context never needs re-explaining. Workspace-scoped with confidence scoring and auto-redaction of secrets
- experiment_engineer_agent: For structured experimentation — create experiments with hypotheses, track status through lifecycle (draft→running→completed), record readouts, define event schemas, import events from markdown. Tool-agnostic (not tied to GA4 or any specific platform)
- editorial_agent: For editorial production coordination — content backlog management, weekly editorial calendars, content bundles (multi-asset packages), publish checklists, bundle status tracking (draft→review→approved→scheduled→published). Does NOT write content — produces specs that other agents execute
- gtm_agent: For go-to-market strategy and launch execution — GTM plans, ICP definition, beachhead selection, channel strategy, funnel architecture, phased rollout planning, unit economics, risk assessment, and sub-agent execution briefs. The architect and quarterback of product launch — designs, sequences, and drives GTM execution from zero to scalable traction
- seo_aeo_agent: For SEO, AEO (Answer Engine Optimization), and GEO (Generative Engine Optimization) strategy — keyword architecture, intent clustering, page type governance, URL structures, structured data/schema standards with ready-to-paste JSON-LD, internal linking architecture, AEO formatting, GEO strategy (Princeton citation framework, AI crawler directives, engine-specific optimization), snippet optimization, AI answer visibility, AI crawler specs (robots.txt for GPTBot/ClaudeBot/PerplexityBot), organic content brief generation for Writer Agent, programmatic page design, crawl integrity diagnostics, cannibalization detection, organic and GEO measurement systems, keyword tracker specs, and SEO monitoring workflow specs. The authority on search architecture, AI answer optimization, and generative engine optimization. Does NOT write content — produces structured briefs that writer_agent executes. Does NOT define ICP or positioning (GTM owns that). Operationalizes organic growth within GTM strategic direction
- ux_ui_design_agent: For website UX/UI design - UX audits (heuristic evaluation, accessibility, visual hierarchy), design system specs (typography, colors, spacing, component standards), page layout specs, navigation architecture (mega-menus, mobile nav, dropdowns), interaction design (transitions, loading states, form UX), and screenshot-based UX analysis. Produces implementation-ready specs for React/Tailwind/shadcn developers. Does NOT design experiments (CRO), own funnel strategy (Acquisition), or define page taxonomy (SEO/AEO)

You also have direct tools for:
- n8n workflow management (list, execute, create, update, delete workflows)
- Opportunity and draft management (list, approve, reject)
- Workspace configuration (sources, keywords, settings)
- Media library (list, search generated images/videos/decks)

CRITICAL RULES:
- NEVER explain what you cannot do. ALWAYS delegate to the appropriate sub-agent and let it handle the request.
- NEVER describe system limitations or suggest future enhancements. Just do the task.
- If a user asks for something a sub-agent can handle, delegate IMMEDIATELY without commentary about capabilities.
- NEVER generate document, spreadsheet, or presentation content yourself. You MUST delegate to the appropriate agent (docs_agent, sheets_agent, deck_agent). These agents create real Google Workspace files and return live links.
- When you receive a result from a document-creation agent, extract and prominently display any URLs (google_docs_url, google_sheets_url, google_slides_url) in your response.
- ABBREVIATIONS: Always spell out abbreviations/acronyms on first use with the abbreviation in parentheses — e.g., "Total Addressable Market (TAM)". After the first occurrence, use the abbreviation only. Include this instruction when delegating to any content-producing agent.
- ANTI-AI WRITING RULES (MANDATORY — apply to ALL content from every agent):
  • NEVER use em dashes (—) or en dashes (–). Use commas, periods, semicolons, or " - " (spaced hyphen) instead.
  • NEVER bold words in the middle of a sentence. Bolding is only acceptable for section headers or standalone labels.
  These are telltale signs of AI-generated text. Enforce these rules when delegating to any content-producing agent.

DELEGATION GUIDELINES:
- When asked to find/research/scan content, delegate to the appropriate ingest agent
- When asked to write/draft/create content, delegate to the writer agent
- MEDIA CREATION FLOW (images, videos, motion graphics): All three media agents follow the same 4-step approval flow. NEVER skip steps or combine them. Each step requires waiting for the user's response before proceeding.

  STEP 1 — CLARIFY: Ask clarifying questions to understand what the user wants.
  STEP 2 — PLAN: Based on their answers, present a production plan with ALL tier/cost options. The plan should describe WHAT you will create, HOW, and the cost at each tier. Do NOT call the production tool yet.
  STEP 3 — APPROVE: Wait for the user to approve the plan AND select their preferred tier/options. Do not proceed until the user explicitly confirms.
  STEP 4 — PRODUCE: Only after approval, call the agent tool to produce the content. Return the output with a direct link.

VISUAL CONTENT CREATION:
Use create_visual for ALL image requests — photos, infographics, diagrams, ecosystem visuals, dashboards, illustrations, etc.
The tool generates images directly via AI (Gemini) — it produces rich, professional visuals.
Default pricing tier is "high" (Gemini, ~$0.05-$0.10/image) for best quality.
Set output_format to match the use case:
- "landscape" for LinkedIn posts, presentations, blog headers
- "square" for social media, thumbnails
- "portrait" for stories, mobile-first content

FOR MULTIPLE VARIANTS: Use create_visual_variants to generate N stylistically different versions of the same visual (corporate, vibrant, minimal, dark-tech).

CRITICAL — DESCRIPTION = FULL ACCUMULATED BRIEF:
The description parameter is the COMPLETE BRIEF that the AI image generator uses. It must contain EVERYTHING the user has said about this visual across ALL messages in the conversation — the initial request PLUS all follow-up clarifications, answers to your questions, and additional context.

You MUST:
1. Start with the user's original request (verbatim — do NOT summarize or paraphrase)
2. APPEND any follow-up context the user provided in subsequent messages (answers to your clarifying questions, additional details, corrections)
3. Include ALL of these when present:
   - Structure and layout (e.g. "4 phases: request → clarify → orchestrate → deliver")
   - Specific data (groupings, counts, names, labels the user specified)
   - Emphasis areas (e.g. "emphasis should be on step 3")
   - Format preferences (e.g. "LinkedIn post format", "vertical", "landscape")
   - Title preferences (e.g. "call it the CMO/CRO AI Ecosystem")
   - Any corrections or refinements from follow-up messages

Do NOT summarize, paraphrase, or abbreviate. The AI image generator reads ONLY this description. If context is lost here, it is lost forever. Err on the side of including TOO MUCH context rather than too little.

Follow the 4-step approval flow:
STEP 1 — Ask what the visual should show, style, format.
STEP 2 — Present plan with cost info. Images cost ~$0.01-$0.10 depending on tier (low=SDXL ~$0.01, medium=DALL-E ~$0.04, high=Gemini ~$0.05-$0.10).
STEP 3 — Wait for approval.
STEP 4 — For ONE visual: call create_visual. For MULTIPLE VARIANTS: call create_visual_variants ONCE.

IMPORTANT: If create_visual returns an error, report the error to the user and ask how to proceed. Do NOT fall back to deck_agent, docs_agent, or any other agent as a substitute for image generation. Slides and documents are NOT images.

For ANIMATIONS and VIDEO:
- Use video_agent for ALL video and animation content (AI-generated clips, motion graphics, animated infographics)
- Follow the 4-step approval flow with tier/cost options

ANIMATED INFOGRAPHIC CHAINING:
For requests like "animated infographic", "animated ecosystem diagram", or "animated dashboard":
1. First generate the static infographic via create_visual (Gemini produces excellent infographic images)
2. Then animate it via video_agent's generate_video with the image_url parameter set to the generated image URL
This produces the best quality: Gemini's visual design + AI video animation.

- When asked to create presentations, decks, slides, Google Slides, or PowerPoints, you MUST delegate to the deck agent. NEVER write slide content yourself. The deck agent creates the actual Google Slides file and returns a URL. Include that URL in your response.
- When asked about paid ads, campaigns, A/B tests, budgets, ROAS, CPA, or ad performance, delegate to the performance marketer agent
- When asked about social media strategy, content calendars, hashtags, engagement, or posting schedules, delegate to the social media agent
- When asked to diagnose, repair, heal, fix, or check health of existing workflows, delegate to the workflow healer agent
- When asked to build, create, design, or set up a NEW n8n workflow or automation, delegate to the workflow builder agent. The builder will present a summary for approval, deploy as inactive, and activate after user review. For complex requests that may need multiple workflows, the builder handles multi-workflow architectures
- When asked to activate or move a workflow to production, delegate to the workflow builder agent
- When asked to create documents, reports, briefs, proposals, or Google Docs, you MUST delegate to the docs agent. NEVER write document content yourself. The docs agent creates the actual Google Doc and returns a URL. Include that URL in your response.
- When asked to create spreadsheets, trackers, budget sheets, Google Sheets, or tabular data, you MUST delegate to the sheets agent. NEVER write table/spreadsheet content yourself. The sheets agent creates the actual Google Sheet and returns a URL. Include that URL in your response.
- When asked about lifecycle marketing, email/SMS/push flows, customer journeys, onboarding sequences, win-back campaigns, segmentation, trigger logic, message frameworks, or compliance audits, delegate to the lifecycle marketing agent
- When asked for growth ideas, growth suggestions, what to work on next, growth opportunities, or daily priorities, delegate to the growth ideas agent
- When asked about measurement frameworks, event tracking, UTM conventions, attribution models, tracking audits, GA4 setup, dashboard requirements, KPI hierarchies, or tracking specifications, delegate to the marketing analytics agent
- BOUNDARY: Performance Marketer Agent handles live campaign analysis, ad spend optimization, and ROAS calculations from actual data. Marketing Analytics Agent handles measurement infrastructure — what to track, how to name it, how to attribute it, and how to report on it. When in doubt: if the request is about designing tracking/measurement systems, use marketing analytics; if it's about analyzing campaign results, use performance marketer
- When asked about funnel architecture, funnel mapping, landing page strategy, friction point analysis, lead generation strategy, or funnel metric calculation, delegate to the acquisition agent
- When asked about experiment design, A/B test design, multivariate tests, experiment prioritization, experiment backlog, on-page conversion optimization, CTA optimization, headline testing, offer positioning, email capture optimization, affiliate click-through optimization, variant briefs, statistical validation, or experiment results analysis, delegate to the conversion_optimization_agent
- BOUNDARY: Acquisition Agent identifies optimization opportunities (what to fix and why). Conversion Optimization Agent designs the experiments to test them (how to test and when to ship). Experiment Engineer persists and tracks experiment lifecycle. Performance Marketer owns ad campaign A/B tests. Marketing Analytics owns measurement infrastructure
- CHAINING: For "audit and optimize our DMA pages", delegate funnel audit to acquisition_agent → optimization recommendations to conversion_optimization_agent → experiment design to conversion_optimization_agent → variant copy to writer_agent → lifecycle tracking to experiment_engineer_agent
- CHAINING: For "run a headline test", delegate experiment design to conversion_optimization_agent → variant brief to conversion_optimization_agent → copy variants to writer_agent → experiment creation to experiment_engineer_agent → tracking requirements to sales_ops_agent
- When asked about compliance review, regulatory compliance, disclosures, disclaimers, consent requirements, FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA, or state insurance regulations, delegate to the compliance agent
- When asked about contracts, NDAs, agreements, term sheets, legal risk, negotiation strategy, clause explanations, or contract review, delegate to the legal strategy agent
- When asked about telesales, call scripts, dialing strategy, voice AI, cold calling, call center design, objection handling, CRM integration for sales teams, or QA scorecards, delegate to the telesales agent. If the request involves regulatory compliance (TCPA, DNC, disclosures), also delegate to the compliance agent for review
- When asked about sales process design, CRM pipelines, sales automation, lead routing, MQL/SQL handoff, partner revenue programs, sales compensation, quota setting, pipeline velocity, or sales metrics frameworks, delegate to the sales ops agent
- When asked about LinkedIn outreach, partnership prospecting, connection request templates, partner ICP, LinkedIn lead generation, outreach sequences, or partnership pipeline tracking, delegate to the linkedin partnerships agent
- BOUNDARY: LinkedIn Partnerships handles partnership prospecting and LinkedIn outbound. Sales Ops handles CRM pipeline infrastructure. Lifecycle Marketing handles email/SMS flows. Legal Strategy handles partnership agreements. Compliance handles regulatory review of outreach messaging
- BOUNDARY: Sales Ops handles revenue process infrastructure. Performance Marketer handles paid ad campaigns. Lifecycle Marketing handles email/SMS/push messaging flows. Acquisition handles funnel architecture and friction analysis. Conversion Optimization handles experiment design and on-page optimization. Marketing Analytics handles measurement infrastructure
- CHAINING: For requests like "design a sales process with nurture emails", delegate process design to Sales Ops first, then messaging content to Lifecycle Marketing. For "build a lead scoring model with tracking", delegate scoring to Sales Ops, then tracking specs to Marketing Analytics
- When asked to remember something, store a fact, recall a decision, look up prior context, or manage institutional memory, delegate to the knowledge base agent
- When asked to create, track, or manage experiments, A/B tests, define events, import event schemas, or generate experiment readouts, delegate to the experiment engineer agent
- BOUNDARY: Conversion Optimization Agent designs and prioritizes experiments. Experiment Engineer handles experiment lifecycle persistence and event schemas. Marketing Analytics handles measurement infrastructure and tracking specs. Performance Marketer handles live campaign analysis and ad campaign A/B tests
- When asked to create editorial calendars, manage the content backlog, create content bundles, track publishing status, or coordinate multi-asset content packages, delegate to the editorial agent
- BOUNDARY: Editorial Agent coordinates production and creates specs. Writer Agent, Visual Agent, and other content agents create the actual content. Editorial Agent does NOT write content itself — it produces assets_requested specs for the orchestrator to delegate
- When asked about go-to-market strategy, GTM plans, product launches, market entry, ICP definition, beachhead selection, launch sequencing, channel strategy for new products, unit economics for a launch, or sub-agent execution briefs for a launch, delegate to the gtm_agent
- BOUNDARY: GTM Agent designs the strategy and produces the plan. Other agents (writer, visual, performance_marketer, etc.) execute the individual deliverables. GTM Agent produces structured briefs that the orchestrator can use to coordinate execution across agents
- When asked about SEO strategy, keyword research, keyword architecture, intent mapping, search optimization, page taxonomy, URL structures, canonical rules, structured data, schema markup, JSON-LD, internal linking, AEO strategy, answer engine optimization, featured snippets, AI answer visibility, GEO strategy, generative engine optimization, AI crawler directives, robots.txt for AI bots, AI citation optimization, organic measurement, GEO metrics, crawl health, cannibalization detection, programmatic pages, organic content briefs, or keyword trackers, delegate to the seo_aeo_agent
- BOUNDARY: SEO/AEO Agent owns search architecture, page design standards, and organic measurement. Writer Agent writes the content following SEO briefs. Marketing Analytics Agent owns measurement infrastructure (GA4, UTM). Acquisition Agent owns funnel architecture and friction analysis. Conversion Optimization Agent owns on-page conversion optimization and experiment design. GTM Agent owns strategic channel prioritization and ICP. Editorial Agent coordinates production schedules
- CHAINING: For "create SEO content for DMA pages", delegate page architecture to SEO/AEO Agent first, then content brief creation to SEO/AEO Agent, then content writing to Writer Agent following the brief. For "build organic measurement dashboards", delegate KPI definitions to SEO/AEO Agent, then dashboard specs to Marketing Analytics Agent
- CHAINING: For "create a keyword tracker", delegate keyword architecture to SEO/AEO Agent → delegate tracker spec to SEO/AEO Agent → delegate sheet creation to Sheets Agent
- CHAINING: When SEO/AEO Agent produces an approved keyword architecture or page standard, delegate storage to Knowledge Base Agent with tags ["seo", "keyword_architecture"] or ["seo", "page_type_standard"]
- CHAINING: For SEO experiments (title tag tests, schema additions, new page types), delegate experiment creation to Experiment Engineer Agent with hypothesis and metrics from SEO/AEO Agent
- CHAINING: For "launch organic for new market", delegate market priorities to GTM Agent → keyword architecture to SEO/AEO Agent → content briefs to SEO/AEO Agent → content to Writer Agent
- When asked about UX audits, design systems, component specs, page layouts, navigation design, interaction design, accessibility audits, responsive design specs, or screenshot analysis, delegate to the ux_ui_design_agent
- BOUNDARY: UX/UI Design Agent owns visual design layer, interaction design, accessibility, and design-to-dev handoff. Acquisition Agent identifies funnel friction (what to fix). CRO Agent designs experiments to test changes. SEO/AEO Agent owns page taxonomy and information architecture. Writer Agent handles content copy
- CHAINING: For "audit and redesign the homepage", delegate UX audit to ux_ui_design_agent, then design specs to ux_ui_design_agent, then experiment design to conversion_optimization_agent, then copy to writer_agent

- When asked about status, configuration, or workflows, handle directly
- Always tell the user what you're doing and present results clearly
- NEVER ask the user for brand guidelines, colors, metrics, annual report data, or other background information if reference documents are available (see below). The sub-agents will use the reference documents automatically.
{self._get_ref_docs_note()}
Current workspace: {ws_label}"""

    def _get_ref_docs_note(self) -> str:
        """Return a reference documents note for the system prompt, if any are loaded."""
        ref_docs = getattr(self, "_ref_docs_context", "")
        if not ref_docs:
            return ""
        return f"""
WORKSPACE REFERENCE DOCUMENTS AVAILABLE:
The following reference data has been loaded from the workspace and will be automatically passed to sub-agents. You do NOT need to ask the user for brand guidelines, annual report data, or other background information — the sub-agents already have it.

Summary of available documents:
{ref_docs[:2000]}
[... full documents will be passed to the sub-agent automatically]
"""

    # ── Router-aware overrides ─────────────────────────────────────────

    def _get_tool_definitions(self) -> Optional[list]:
        """Return selective tool definitions when router has pre-selected tools."""
        if self._selected_tool_names is not None:
            defs = self.tool_registry.get_definitions_by_names(self._selected_tool_names)
            return defs or None
        return super()._get_tool_definitions()

    async def process_message(
        self,
        message: Any,
        context: Optional[AgentContext] = None,
        workspace_id: Optional[str] = None,
    ) -> AgentResult:
        """Route via lightweight Haiku classifier when router is enabled.

        Also injects reference document context into the system prompt
        so the orchestrator knows what workspace data is available.
        """
        # Load reference docs for this workspace and stash for system prompt
        if workspace_id and self._workspace_mgr:
            try:
                ref_docs = await self._workspace_mgr.get_reference_docs(workspace_id)
                if ref_docs:
                    self._ref_docs_context = ref_docs
                else:
                    self._ref_docs_context = ""
            except Exception:
                self._ref_docs_context = ""
        else:
            self._ref_docs_context = ""

        if self._router is not None:
            return await self._process_with_router(message, context, workspace_id)
        return await super().process_message(message, context, workspace_id)

    async def _process_with_router(
        self,
        message: Any,
        context: Optional[AgentContext] = None,
        workspace_id: Optional[str] = None,
    ) -> AgentResult:
        """Use the router to classify the request, then dispatch efficiently."""
        # Extract text from message (may be str or list of content blocks)
        if isinstance(message, str):
            message_text = message
        elif isinstance(message, list):
            parts = []
            for block in message:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            message_text = " ".join(parts)
        else:
            message_text = str(message)

        ws_id = workspace_id or "default"

        try:
            decision = await self._router.route(message_text, ws_id)
        except Exception as e:
            logger.warning("router_failed_fallback", error=str(e))
            self._selected_tool_names = None
            return await super().process_message(message, context, workspace_id)

        # ── respond_directly: no orchestrator call at all ────────────
        if decision.action == "respond_directly" and decision.direct_response:
            logger.info("router_direct_response", response=decision.direct_response[:80])
            return AgentResult(
                text=decision.direct_response,
                agent_id=self.agent_id,
                status="success",
                metadata={"routed": "direct"},
            )

        # ── delegate_to_agent: load only the target agent + its tools ─
        if decision.action == "delegate_to_agent" and decision.agent_id:
            agent_id = decision.agent_id
            extra_tools = AGENT_TOOL_GROUPS.get(agent_id, [])
            self._selected_tool_names = [agent_id] + extra_tools
            logger.info(
                "router_delegate",
                agent_id=agent_id,
                tool_count=len(self._selected_tool_names),
            )
            try:
                result = await super().process_message(message, context, workspace_id)
            finally:
                self._selected_tool_names = None
            return result

        # ── use_management_tool: load only the requested tools ────────
        if decision.action == "use_management_tool" and decision.tool_ids:
            self._selected_tool_names = list(decision.tool_ids)
            logger.info(
                "router_management_tool",
                tool_ids=decision.tool_ids,
            )
            try:
                result = await super().process_message(message, context, workspace_id)
            finally:
                self._selected_tool_names = None
            return result

        # ── fallback: full orchestrator ───────────────────────────────
        logger.info("router_fallback", action=decision.action)
        self._selected_tool_names = None
        return await super().process_message(message, context, workspace_id)

    # ── Tool registration ────────────────────────────────────────────

    def register_tools(self) -> None:
        self._register_sub_agent_tools()
        self._register_n8n_tools()
        self._register_management_tools()

    def _register_sub_agent_tools(self) -> None:
        """Register each sub-agent as a callable tool."""

        @self.tool_registry.register(
            name="research_agent",
            description="Delegate a research task: RSS feed scanning, fraud monitoring, opportunity scoring, general web research, reading spreadsheets (XLSX/CSV from data/ directory), brand color extraction from websites, manual brand color setting. Pass a clear instruction.",
        )
        async def call_research_agent(
            instruction: str, workspace_id: Optional[str] = None
        ) -> Dict[str, Any]:
            result = await self._research.process_message(instruction, workspace_id=workspace_id)
            return result.model_dump()

        @self.tool_registry.register(
            name="reddit_ingest_agent",
            description="Delegate a Reddit monitoring task: scan subreddits, categorize posts, find leads. Pass a clear instruction.",
        )
        async def call_reddit_agent(
            instruction: str, workspace_id: Optional[str] = None
        ) -> Dict[str, Any]:
            result = await self._reddit.process_message(instruction, workspace_id=workspace_id)
            return result.model_dump()

        @self.tool_registry.register(
            name="google_alerts_agent",
            description="Delegate a Google Alerts scan: check Gmail for alert emails, extract and score articles. Pass a clear instruction.",
        )
        async def call_google_alerts_agent(
            instruction: str, workspace_id: Optional[str] = None
        ) -> Dict[str, Any]:
            result = await self._google_alerts.process_message(
                instruction, workspace_id=workspace_id
            )
            return result.model_dump()

        @self.tool_registry.register(
            name="writer_agent",
            description="Delegate a writing task: newsletter, blog post, Reddit reply, social media post, or other brand-voiced copy. Pass a clear instruction with the topic and content type.",
        )
        async def call_writer_agent(
            instruction: str, workspace_id: Optional[str] = None
        ) -> Dict[str, Any]:
            result = await self._writer.process_message(instruction, workspace_id=workspace_id)
            return result.model_dump()

        if self._video:

            @self.tool_registry.register(
                name="video_agent",
                description=(
                    "Delegate a video task to the Video Agent. "
                    "IMPORTANT: You MUST collect all required parameters from the user BEFORE calling this tool. "
                    "Ask the user for: (1) what the video should show/convey, "
                    "(2) which pricing tier (Budget ~$0.10-$0.20 Kling 1.5 Standard / Standard ~$0.35-$0.50 Kling 1.5 Pro / Premium ~$2-$5 OpenAI Sora), "
                    "(3) style, duration, and aspect ratio preferences. "
                    "Do NOT call this tool until you have explicit user answers."
                ),
            )
            async def call_video_agent(
                instruction: str,
                video_description: str,
                pricing_tier: str,
                style_and_preferences: str,
                user_approved_cost: bool,
                workspace_id: Optional[str] = None,
            ) -> Dict[str, Any]:
                full_instruction = (
                    f"{instruction}\n\n"
                    f"Video description: {video_description}\n"
                    f"Pricing tier: {pricing_tier}\n"
                    f"Style/preferences: {style_and_preferences}"
                )
                result = await self._video.process_message(
                    full_instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._deck:

            @self.tool_registry.register(
                name="deck_agent",
                description="Delegate a presentation/deck task: creates native Google Slides presentations, pitch decks, marketing slide decks, or converts content into slides. Returns a google_slides_url link that opens directly in Google Slides. Always share that link with the user. Pass a clear instruction with the topic and purpose.",
            )
            async def call_deck_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._deck.process_message(instruction, workspace_id=workspace_id)
                return result.model_dump()

        if self._performance_marketer:

            @self.tool_registry.register(
                name="performance_marketer_agent",
                description="Delegate a performance marketing task: paid ad strategy, campaign architecture, A/B test plans, budget allocation, ROI analysis, or marketing metrics calculation. Pass a clear instruction.",
            )
            async def call_performance_marketer_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._performance_marketer.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._social_media:

            @self.tool_registry.register(
                name="social_media_agent",
                description="Delegate a social media task: content calendar creation, platform strategy, hashtag research, engagement planning, or content idea generation. Pass a clear instruction.",
            )
            async def call_social_media_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._social_media.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._workflow_healer:

            @self.tool_registry.register(
                name="workflow_healer_agent",
                description="Delegate a workflow healing task: diagnose broken workflows, repair deprecated models or broken connections, check execution health, rollback failed repairs, or view healing history. Pass a clear instruction.",
            )
            async def call_workflow_healer_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._workflow_healer.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._workflow_builder:

            @self.tool_registry.register(
                name="workflow_builder_agent",
                description=(
                    "Delegate a workflow building task: design and deploy new n8n workflows "
                    "from natural language descriptions. The builder handles the full lifecycle: "
                    "architecture design, node selection, credential resolution, validation, "
                    "deployment (inactive), testing, and activation (production). "
                    "It will present a summary for user approval before deploying. "
                    "Pass a clear instruction describing what the workflow should do."
                ),
            )
            async def call_workflow_builder_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._workflow_builder.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._docs:

            @self.tool_registry.register(
                name="docs_agent",
                description="Delegate a document task: creates native Google Docs — reports, briefs, proposals, newsletters, blog posts. Returns a google_docs_url link. Always share that link with the user. Pass a clear instruction.",
            )
            async def call_docs_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._docs.process_message(instruction, workspace_id=workspace_id)
                return result.model_dump()

        if self._sheets:

            @self.tool_registry.register(
                name="sheets_agent",
                description="Delegate a spreadsheet task: creates native Google Sheets — campaign trackers, budget sheets, content calendars, analytics dashboards. Can also read existing XLSX/CSV files from the data/ directory. Returns a google_sheets_url link. Always share that link with the user. Pass a clear instruction.",
            )
            async def call_sheets_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._sheets.process_message(instruction, workspace_id=workspace_id)
                return result.model_dump()

        if self._motion_graphics:

            @self.tool_registry.register(
                name="motion_graphics_agent",
                description=(
                    "Delegate a motion graphics task to the Motion Graphics Agent (Remotion). "
                    "Creates programmatic animations: animated text, data visualizations, "
                    "branded intros, infographic animations. All rendering is FREE (local CPU). "
                    "IMPORTANT: You MUST collect all required parameters from the user BEFORE calling this tool. "
                    "Ask the user for: (1) what the motion graphic should show, (2) complexity tier "
                    "(Simple/Standard/Complex), (3) format preferences (dimensions, duration). "
                    "Do NOT call this tool until you have explicit user answers."
                ),
            )
            async def call_motion_graphics_agent(
                instruction: str,
                animation_description: str,
                complexity_tier: str,
                format_preferences: str,
                user_confirmed: bool,
                workspace_id: Optional[str] = None,
            ) -> Dict[str, Any]:
                full_instruction = (
                    f"{instruction}\n\n"
                    f"Animation description: {animation_description}\n"
                    f"Complexity tier: {complexity_tier}\n"
                    f"Format preferences: {format_preferences}"
                )
                result = await self._motion_graphics.process_message(
                    full_instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._lifecycle_marketing:

            @self.tool_registry.register(
                name="lifecycle_marketing_agent",
                description="Delegate a lifecycle marketing task: email/SMS/push/in-product flow design, segmentation strategy, trigger logic, message frameworks, A/B test plans, or compliance audits. Covers Customer.io, Beehiiv, and general lifecycle platforms. Pass a clear instruction.",
            )
            async def call_lifecycle_marketing_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._lifecycle_marketing.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._growth_ideas:

            @self.tool_registry.register(
                name="growth_ideas_agent",
                description="Delegate a growth ideas task: generate daily growth ideas based on recent project activity across all workspaces, with impact/effort scoring and execution outlines. Pass a clear instruction.",
            )
            async def call_growth_ideas_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._growth_ideas.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._marketing_analytics:

            @self.tool_registry.register(
                name="marketing_analytics_agent",
                description="Delegate a marketing analytics task: measurement frameworks, GA4 event taxonomy, UTM naming standards, attribution modeling (MMM/MTA), tracking gap audits, dashboard requirements, KPI hierarchies, or technical tracking specs (SQL, GTM, dataLayer). Pass a clear instruction.",
            )
            async def call_marketing_analytics_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._marketing_analytics.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._acquisition:

            @self.tool_registry.register(
                name="acquisition_agent",
                description="Delegate an acquisition funnel task: funnel architecture, funnel mapping, landing page strategy, friction point analysis, or funnel metric calculation. Identifies what to optimize and why. Does NOT design experiments — hand off to conversion_optimization_agent for that. Pass a clear instruction.",
            )
            async def call_acquisition_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._acquisition.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._conversion_optimization:

            @self.tool_registry.register(
                name="conversion_optimization_agent",
                description=(
                    "Delegate an on-site conversion optimization or experimentation task: "
                    "conversion architecture discovery (run first for new sites), "
                    "experiment design, experiment prioritization, A/B test planning, "
                    "on-page element optimization, variant briefs for Writer Agent, "
                    "tracking requirements, experiment results analysis, or statistical "
                    "requirement calculations. Vertical-agnostic — auto-calibrates to "
                    "any site's business model via discover_conversion_architecture. "
                    "This agent is the experimentation authority — no other agent designs "
                    "experiments without its oversight. Pass a clear instruction."
                ),
            )
            async def call_conversion_optimization_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._conversion_optimization.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._compliance:

            @self.tool_registry.register(
                name="compliance_agent",
                description="Delegate a compliance review task to the Marketing Compliance Agent. Use for regulatory compliance in financial services and insurance (FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA, state insurance). Pass a clear instruction.",
            )
            async def call_compliance_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._compliance.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._legal_strategy:

            @self.tool_registry.register(
                name="legal_strategy_agent",
                description="Delegate a legal strategy task: draft NDAs, partnership agreements, term sheets, analyze contracts, flag risks, suggest negotiation strategies, or explain clauses in plain English. Pass a clear instruction.",
            )
            async def call_legal_strategy_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._legal_strategy.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._telesales:

            @self.tool_registry.register(
                name="telesales_agent",
                description="Delegate a telesales task: call center program design, call scripting, objection trees, dialing strategy, CRM integration blueprints, voice AI evaluation frameworks, QA frameworks, or KPI dashboards. Pass a clear instruction.",
            )
            async def call_telesales_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._telesales.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._sales_ops:

            @self.tool_registry.register(
                name="sales_ops_agent",
                description="Delegate a sales operations task: sales process design, CRM pipeline architecture, sales automation sequences, marketing-to-sales handoff alignment, lead scoring models, partner/affiliate/referral revenue workflows, compensation models, or sales metrics frameworks. n8n-aware — recommends implementable workflow patterns. Pass a clear instruction.",
            )
            async def call_sales_ops_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._sales_ops.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._linkedin_partnerships:

            @self.tool_registry.register(
                name="linkedin_partnerships_agent",
                description="Delegate a LinkedIn partnership lead generation task: partner ICP definition, LinkedIn prospecting strategy, outreach sequences with A/B testing, follow-up cadences, partnership CRM tracking, or full lead gen strategy. Pass a clear instruction.",
            )
            async def call_linkedin_partnerships_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._linkedin_partnerships.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._knowledge_base:

            @self.tool_registry.register(
                name="knowledge_base_agent",
                description="Delegate a memory/knowledge task: store decisions, recall context, search institutional memory, manage canonical facts. Pass a clear instruction.",
            )
            async def call_knowledge_base_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._knowledge_base.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._experiment_engineer:

            @self.tool_registry.register(
                name="experiment_engineer_agent",
                description="Delegate an experiment/testing task: create experiments with hypotheses, track lifecycle, record readouts, define event schemas, import events. Tool-agnostic (not tied to GA4). Pass a clear instruction.",
            )
            async def call_experiment_engineer_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._experiment_engineer.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._editorial:

            @self.tool_registry.register(
                name="editorial_agent",
                description="Delegate an editorial coordination task: editorial calendars, content backlog, content bundles, publish checklists, production tracking. Does NOT write content — produces specs for other agents. Pass a clear instruction.",
            )
            async def call_editorial_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._editorial.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        if self._gtm:

            @self.tool_registry.register(
                name="gtm_agent",
                description=(
                    "Delegate a go-to-market strategy task: GTM plans, ICP definition, "
                    "channel strategy, launch phasing, unit economics, risk assessment, "
                    "and agent execution briefs. This agent is the architect of product "
                    "launch — it designs, sequences, and drives GTM execution from zero "
                    "to scalable traction. Pass a clear instruction with product context."
                ),
            )
            async def call_gtm_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._gtm.process_message(instruction, workspace_id=workspace_id)
                return result.model_dump()

        if self._seo_aeo:

            @self.tool_registry.register(
                name="seo_aeo_agent",
                description=(
                    "Delegate an SEO/AEO/GEO task: keyword architecture, intent clustering, "
                    "page type governance, structured data standards, ready-to-paste JSON-LD, "
                    "internal linking design, AEO formatting, GEO strategy, AI crawler "
                    "directives (robots.txt for GPTBot/ClaudeBot/PerplexityBot), organic "
                    "content briefs for Writer Agent, snippet optimization, AI answer "
                    "visibility, GEO metrics, organic audits, cannibalization detection, "
                    "keyword tracker specs, monitoring workflow specs, or organic measurement "
                    "systems. This agent is the authority on search architecture, AI answer "
                    "optimization, and generative engine optimization. Pass a clear instruction."
                ),
            )
            async def call_seo_aeo_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._seo_aeo.process_message(instruction, workspace_id=workspace_id)
                return result.model_dump()

        if self._ux_ui_design:

            @self.tool_registry.register(
                name="ux_ui_design_agent",
                description=(
                    "Delegate a UX/UI design task: website UX audits "
                    "(heuristic evaluation, accessibility, visual hierarchy), "
                    "design specs (typography, colors, spacing, component standards, "
                    "page layouts), navigation architecture (mega-menus, mobile nav, "
                    "dropdowns), interaction design (transitions, loading states, "
                    "form UX), and screenshot-based UX analysis. Produces "
                    "implementation-ready specs for React/Tailwind/shadcn developers. "
                    "Does NOT design experiments (CRO), own funnel strategy "
                    "(Acquisition), or define page taxonomy (SEO/AEO)."
                ),
            )
            async def call_ux_ui_design_agent(
                instruction: str, workspace_id: Optional[str] = None
            ) -> Dict[str, Any]:
                result = await self._ux_ui_design.process_message(
                    instruction, workspace_id=workspace_id
                )
                return result.model_dump()

        # ── Unified visual tool: single gateway for ALL static images ──
        if self._visual or self._composition_planner:

            @self.tool_registry.register(
                name="create_visual",
                description=(
                    "Generate a visual image using AI (Gemini/DALL-E). "
                    "Handles ALL visual types: infographics, diagrams, ecosystem maps, "
                    "photos, illustrations, dashboards, process flows, etc. "
                    "The AI generates the full image directly — rich, professional output. "
                    "Default tier is 'high' (Gemini) for best quality. "
                    "Use 'medium' (DALL-E) or 'low' (SDXL) for cost savings. "
                    "CRITICAL: description must be the COMPLETE ACCUMULATED BRIEF."
                ),
            )
            async def create_visual(
                description: str,
                visual_type: str,
                output_format: str = "landscape",
                pricing_tier: str = "high",
                workspace_id: Optional[str] = None,
            ) -> Dict[str, Any]:
                """Generate a visual image via direct AI generation (Gemini/DALL-E/SDXL).

                Args:
                    description: COMPLETE ACCUMULATED BRIEF — the user's original request
                        VERBATIM plus ALL follow-up answers, clarifications, and additional
                        context from the conversation. Include structure, phases, groupings,
                        counts, emphasis areas, titles, format preferences.
                    visual_type: Type of visual (diagram, infographic, photo, etc.).
                    output_format: landscape, square, or portrait.
                    pricing_tier: low (SDXL ~$0.01), medium (DALL-E ~$0.04), or
                        high (Gemini ~$0.05-$0.10). Default high for best quality.
                    workspace_id: Workspace context.
                """
                return await self._generate_photo(
                    prompt=description,
                    tier=pricing_tier,
                    output_format=output_format,
                    workspace_id=workspace_id,
                )

            @self.tool_registry.register(
                name="create_visual_variants",
                description=(
                    "Generate multiple stylistically different versions of the same visual. "
                    "Each variant uses a different visual style (corporate, vibrant, minimal, dark-tech). "
                    "Produces truly distinct visuals from the same brief. "
                    "Better than calling create_visual multiple times. "
                    "CRITICAL: description must be the FULL ACCUMULATED BRIEF."
                ),
            )
            async def create_visual_variants(
                description: str,
                visual_type: str,
                styles: List[str] = None,
                count: int = 4,
                output_format: str = "landscape",
                pricing_tier: str = "high",
                workspace_id: Optional[str] = None,
            ) -> Dict[str, Any]:
                """Generate multiple AI images with different style modifiers.

                Args:
                    description: COMPLETE ACCUMULATED BRIEF for the visual.
                    visual_type: Type of visual (diagram, infographic, photo, etc.).
                    styles: List of style keys (corporate, vibrant, minimal, dark-tech).
                        Defaults to all 4.
                    count: Number of variants (ignored if styles specified).
                    output_format: landscape, square, or portrait.
                    pricing_tier: low, medium, or high. Default high (Gemini).
                    workspace_id: Workspace context.
                """
                _STYLE_MODIFIERS: Dict[str, str] = {
                    "corporate": (
                        "Corporate professional style with deep blue/navy palette, "
                        "clean lines, subtle gradients"
                    ),
                    "vibrant": (
                        "Vibrant energetic style with bold orange/pink/teal colors, "
                        "glowing accents, dynamic composition"
                    ),
                    "minimal": (
                        "Minimalist style with white/light background, muted colors, "
                        "generous whitespace, clean typography"
                    ),
                    "dark-tech": (
                        "Dark futuristic style with dark background, cyan/green neon "
                        "accents, tech-forward aesthetic"
                    ),
                }

                style_keys = styles or list(_STYLE_MODIFIERS.keys())[:count]
                results: List[Dict[str, Any]] = []

                for style_key in style_keys:
                    modifier = _STYLE_MODIFIERS.get(style_key, style_key)
                    styled_desc = f"{description}\n\nVisual style: {modifier}"
                    result = await self._generate_photo(
                        prompt=styled_desc,
                        tier=pricing_tier,
                        output_format=output_format,
                        workspace_id=workspace_id,
                    )
                    if result.get("status") == "generated":
                        results.append({**result, "style": style_key})
                    else:
                        results.append(
                            {
                                "style": style_key,
                                "status": result.get("status", "failed"),
                                "error": result.get("error", "Unknown error"),
                            }
                        )

                return {
                    "status": "generated",
                    "variant_count": len(results),
                    "variants": results,
                }

    # ── Visual routing ───────────────────────────────────────────────

    async def _plan_composition_once(
        self,
        description: str,
        workspace_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        """Run the composition planner once and extract the spec."""
        if not self._composition_planner:
            return None

        planner_result = await self._composition_planner.process_message(
            description, workspace_id=workspace_id
        )
        logger.info(
            "composition_planner_result_single",
            status=planner_result.status,
            tool_call_count=len(planner_result.tool_calls),
        )
        spec = self._extract_composition_spec(planner_result)
        if spec is None:
            spec = self._extract_spec_from_text(planner_result.text)
        return spec

    async def _run_composition_pipeline(
        self,
        description: str,
        output_format: str,
        asset_type: str,
        background_style: str,
        workspace_id: Optional[str],
        style_hint: str = "",
    ) -> Dict[str, Any]:
        """Composition pipeline: plan → validate → render → upload."""
        import shutil

        _PHOTO_BG_TEMPLATES = {"HeroOverlay", "QuoteCard", "CalloutOverlay"}

        if not self._composition_planner:
            return {
                "status": "error",
                "error": "Composition Planner not configured.",
            }

        # ── Pre-flight: verify Remotion is available ──
        if not shutil.which("npx"):
            return {
                "status": "error",
                "error": "Remotion rendering unavailable: npx not found on PATH",
            }

        # ── Step 1: Get structured spec from Composition Planner ──
        # Inject style_hint into the planner message so it picks a different theme
        planner_message = description
        if style_hint:
            planner_message = f"{description}\n\n[Style hint: Use theme: {style_hint}]"
        planner_result = await self._composition_planner.process_message(
            planner_message, workspace_id=workspace_id
        )
        logger.info(
            "composition_planner_result",
            status=planner_result.status,
            tool_call_count=len(planner_result.tool_calls),
            tool_names=[tc.get("name") for tc in planner_result.tool_calls],
            text_len=len(planner_result.text),
        )
        spec = self._extract_composition_spec(planner_result)
        if spec is None:
            # Fallback: attempt JSON extraction from planner text
            spec = self._extract_spec_from_text(planner_result.text)
        if spec is None:
            logger.warning(
                "composition_spec_extraction_failed",
                planner_text=planner_result.text[:500],
                tool_calls=[
                    {"name": tc.get("name"), "result_status": tc.get("result", {}).get("status")}
                    for tc in planner_result.tool_calls
                ],
            )
            return {
                "status": "error",
                "error": "Composition Planner did not produce a valid spec. "
                "Raw output: " + planner_result.text[:500],
            }

        # ── Step 1b: Enforce theme from style_hint (safety net) ──
        if style_hint and spec.get("template_props"):
            current_theme = spec["template_props"].get("theme", "")
            if current_theme != style_hint:
                spec["template_props"]["theme"] = style_hint
                logger.info(
                    "composition_theme_enforced",
                    requested=style_hint,
                    was=current_theme,
                )

        # ── Step 2: Prop reasonableness checks (Level 2 QA) ──
        qa_errors = self._validate_composition_props(spec)
        if qa_errors:
            return {
                "status": "error",
                "error": "Composition spec failed quality checks: " + "; ".join(qa_errors),
            }

        # ── Step 3: Generate background if photo requested ──
        bg_path = None
        needs_photo_bg = background_style == "photo" or (
            background_style == "auto" and spec["template_id"] in _PHOTO_BG_TEMPLATES
        )
        if needs_photo_bg and spec.get("background_prompt"):
            bg_path = await self._generate_textless_background(
                spec["background_prompt"], output_format, workspace_id
            )

        # ── Step 4: Render via Remotion (with retry) ──
        from pathlib import Path as _Path

        from ..text.composition_renderer import CompositionRenderer

        renderer = CompositionRenderer()

        async def _try_render(
            render_spec: Dict[str, Any],
        ) -> Optional[str]:
            """Attempt a render, return output path or None on failure."""
            try:
                if asset_type in ("motion", "video_overlay"):
                    path = await renderer.render_motion(
                        template_id=render_spec["template_id"],
                        props=render_spec["template_props"],
                        output_format=output_format,
                    )
                else:
                    path = await renderer.render_static(
                        template_id=render_spec["template_id"],
                        props=render_spec["template_props"],
                        output_format=output_format,
                        background_path=bg_path,
                    )
                out_path = _Path(path)
                if not out_path.exists() or out_path.stat().st_size == 0:
                    return None
                # Post-render sanity check: reject suspiciously small files
                if out_path.stat().st_size < 15000:
                    logger.warning(
                        "composition_suspiciously_small",
                        size=out_path.stat().st_size,
                        template=render_spec["template_id"],
                    )
                # Verify dimensions match expected canvas
                try:
                    from PIL import Image as _PILImage

                    img = _PILImage.open(out_path)
                    w, h = img.size
                    img.close()
                    expected = {
                        "landscape": (1920, 1080),
                        "square": (1080, 1080),
                    }
                    exp_w, exp_h = expected.get(output_format, (1920, 1080))
                    if w != exp_w or h != exp_h:
                        logger.warning(
                            "composition_dimension_mismatch",
                            expected=(exp_w, exp_h),
                            got=(w, h),
                            template=render_spec["template_id"],
                        )
                except Exception:
                    pass  # Non-fatal — don't block on dimension check
                return path
            except Exception as e:
                logger.warning(
                    "composition_render_attempt_failed",
                    template=render_spec["template_id"],
                    error=str(e),
                )
                return None

        # First attempt
        output_path = await _try_render(spec)
        if output_path is None:
            # Retry with simplified spec
            simplified_spec = self._simplify_spec(spec)
            logger.info("composition_retry_with_simplified_spec")
            output_path = await _try_render(simplified_spec)
        if output_path is None:
            return {
                "status": "error",
                "error": f"Render failed for {spec['template_id']} after retry with simplified spec",
            }

        # ── Step 5: Verify output ──
        out = _Path(output_path)
        if not out.exists() or out.stat().st_size == 0:
            return {
                "status": "error",
                "error": f"Render produced no output for {spec['template_id']}",
            }

        # ── Step 6: Upload to CDN ──
        result: Dict[str, Any] = {
            "status": "rendered",
            "asset_type": asset_type,
            "template_id": spec["template_id"],
            "output_path": output_path,
        }
        if self._media_storage and self._media_storage.is_configured:
            try:
                media_type = "video" if asset_type == "motion" else "image"
                asset = await self._media_storage.upload(
                    data=out.read_bytes(),
                    workspace_id=workspace_id or "default",
                    media_type=media_type,
                    extension=out.suffix,
                    source_agent="composition_planner",
                    prompt=f"Template: {spec['template_id']}",
                )
                if asset and asset.cdn_url:
                    result["cdn_url"] = asset.cdn_url
                    result["asset_id"] = asset.id
            except Exception as upload_err:
                logger.warning("composition_upload_failed", error=str(upload_err))
        return result

    # Signals that a request is for an infographic / diagram (text expected)
    _INFOGRAPHIC_SIGNALS = frozenset(
        {
            "infographic",
            "diagram",
            "ecosystem",
            "dashboard",
            "flow",
            "architecture",
            "process",
            "timeline",
            "comparison",
            "chart",
            "visual showing",
            "visual representation",
            "visual that",
            "agent groupings",
            "phases",
            "interconnect",
            "funnel",
            "hierarchy",
            "kpi",
            "metrics",
            "scorecard",
            "map",
        }
    )

    async def _optimize_image_prompt(self, description: str, workspace_id: Optional[str]) -> str:
        """Optimize a raw image description into a detailed, brand-aware image prompt.

        Detects whether the request is for an infographic/diagram (text expected)
        vs a photograph (no text) and uses different optimization rules.
        """
        if not self._visual or not self._workspace_mgr:
            return description

        from ..llm.base import Message

        # Detect infographic-style requests
        lower_desc = description.lower()
        is_infographic = any(kw in lower_desc for kw in self._INFOGRAPHIC_SIGNALS)

        try:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id or "default")

            if is_infographic:
                rules = """RULES:
1. Create a detailed visual design description for generating a professional infographic image.
2. Describe the LAYOUT: where elements go, relative sizes, visual hierarchy.
3. Describe the STYLE: color palette, background, typography feel, icon style.
4. Include ALL text labels, headings, and data from the brief — text IS required and expected.
5. Specify visual elements: icons, connecting lines, containers, groupings.
6. Make it look like a polished LinkedIn/presentation graphic, not a basic diagram.
7. No watermarks or stock photo artifacts."""
            else:
                rules = """RULES (in priority order):
1. ABSOLUTELY NO TEXT in the image. No letters, words, numbers, typography, signage, labels, watermarks, or any written content. The generated prompt MUST include the phrase "no text" or "without any text".
2. Describe the scene concretely — subjects, setting, lighting, camera angle, depth of field.
3. Be specific about colors, composition, and mood.
4. Keep it professional and brand-appropriate."""

            gen_prompt = f"""Create a detailed image generation prompt for:
Description: {description}

Brand context:
{brand_voice[:500] if brand_voice else "No brand voice specified."}

{rules}

Return ONLY the image prompt, nothing else."""
            response = await self._visual.llm.complete(
                messages=[Message(role="user", content=gen_prompt)],
                temperature=0.5,
            )
            optimized = response.content.strip()
            if optimized:
                logger.info(
                    "image_prompt_optimized",
                    original_len=len(description),
                    optimized_len=len(optimized),
                    is_infographic=is_infographic,
                )
                return optimized
        except Exception as e:
            logger.warning("image_prompt_optimization_failed", error=str(e))
        return description

    async def _generate_photo(
        self,
        prompt: str,
        tier: str,
        output_format: str,
        workspace_id: Optional[str],
    ) -> Dict[str, Any]:
        """Direct image API call — no Visual Agent ReAct loop."""
        from .visual import IMAGE_TIERS, _call_dalle, _call_gemini, _call_sdxl

        if not self._visual:
            return {"status": "error", "error": "Visual Agent not configured."}

        # Detect infographic-style request BEFORE prompt optimization
        # (optimization may rewrite the prompt, so check the original)
        lower_prompt = prompt.lower()
        is_infographic = any(kw in lower_prompt for kw in self._INFOGRAPHIC_SIGNALS)

        # Optimize prompt with brand voice and concrete details
        prompt = await self._optimize_image_prompt(prompt, workspace_id)

        size_map = {
            "landscape": "1792x1024",
            "square": "1024x1024",
            "portrait": "1024x1792",
        }
        size = size_map.get(output_format, "1024x1024")

        tier = tier.lower()
        tier_info = IMAGE_TIERS.get(tier, IMAGE_TIERS["medium"])
        platform = tier_info["platform"]

        try:
            if platform == "sdxl":
                if not self._visual._fal_api_key:
                    return {"status": "skipped", "error": "FAL API key not configured."}
                result = await _call_sdxl(
                    api_key=self._visual._fal_api_key,
                    model=self._visual._sdxl_model,
                    prompt=prompt,
                    size=size,
                )
            elif platform == "gemini":
                if not self._visual._gemini_api_key:
                    return {"status": "skipped", "error": "Gemini API key not configured."}
                # For infographics: skip the "no text" prefix — text IS needed
                result = await _call_gemini(
                    api_key=self._visual._gemini_api_key,
                    model=self._visual._gemini_image_model,
                    prompt=prompt,
                    size=size,
                    no_text_prefix=not is_infographic,
                )
            else:
                # Default: DALL-E 3
                if not self._visual._openai_api_key:
                    return {"status": "skipped", "error": "OpenAI API key not configured."}
                result = await _call_dalle(
                    api_key=self._visual._openai_api_key,
                    prompt=prompt,
                    size=size,
                    quality="standard",
                    style="natural",
                )

            # CDN upload
            cdn_url = result["url"]
            asset_id = None
            if self._media_storage and workspace_id:
                try:
                    media_metadata = {
                        "size": size,
                        "tier": tier,
                        "model": tier_info["model_name"],
                    }
                    if result["url"].startswith("file://"):
                        local_path = result["url"].removeprefix("file://")
                        asset = await self._media_storage.upload_from_file(
                            file_path=local_path,
                            workspace_id=workspace_id,
                            media_type="image",
                            source_agent="create_visual",
                            prompt=prompt,
                            metadata=media_metadata,
                        )
                    else:
                        asset = await self._media_storage.upload_from_url(
                            url=result["url"],
                            workspace_id=workspace_id,
                            media_type="image",
                            extension=".png",
                            source_agent="create_visual",
                            prompt=prompt,
                            metadata=media_metadata,
                        )
                    cdn_url = asset.cdn_url or result["url"]
                    asset_id = asset.id
                except Exception as e:
                    logger.warning("photo_upload_failed", error=str(e))

            return {
                "image_url": cdn_url,
                "revised_prompt": result.get("revised_prompt", prompt),
                "size": size,
                "tier": tier,
                "model": tier_info["model_name"],
                "status": "generated",
                "asset_id": asset_id,
            }
        except Exception as e:
            logger.error("photo_generation_failed", tier=tier, error=str(e))
            return {"error": str(e), "prompt": prompt, "tier": tier, "status": "failed"}

    # ── Composition pipeline helpers ─────────────────────────────────

    # Per-template element caps (safety net — planner should respect these too)
    _TEMPLATE_CAPS: Dict[str, Dict[str, int]] = {
        "EcosystemMap": {"clusters": 8},
        "DataDashboard": {"metrics": 8},
        "ProcessFlow": {"steps": 6},
        "ComparisonGrid": {"items": 4},
        "TimelineSequence": {"events": 8},
        "StaticLayout": {"nodes": 12},
        "CalloutOverlay": {"callouts": 6},
    }
    _PLACEHOLDERS = {"tbd", "xxx", "lorem", "example", "placeholder"}

    def _validate_composition_props(self, spec: Dict[str, Any]) -> List[str]:
        """Level 2 QA: deterministic prop reasonableness checks (free, instant).

        Auto-heals where possible (truncation, cap enforcement) instead of erroring.
        Only returns hard errors that cannot be auto-fixed.
        """
        errors: List[str] = []
        props = spec.get("template_props", {})
        template_id = spec.get("template_id", "")

        # Check title/hub label is non-empty
        if "title" in props and not str(props["title"]).strip():
            errors.append("Title is empty")
        if "hub" in props:
            hub = props["hub"]
            if isinstance(hub, dict) and not str(hub.get("label", "")).strip():
                errors.append("Hub label is empty")

        # Check list items for empty labels, duplicates, placeholders
        for key in ("clusters", "metrics", "steps", "items", "callouts", "events", "nodes"):
            items = props.get(key, [])
            if not isinstance(items, list):
                continue

            # Per-template cap: auto-truncate instead of erroring
            caps = self._TEMPLATE_CAPS.get(template_id, {})
            cap = caps.get(key)
            if cap and len(items) > cap:
                logger.warning(
                    "composition_auto_truncated",
                    template=template_id,
                    prop=key,
                    original=len(items),
                    capped=cap,
                )
                props[key] = items[:cap]
                items = props[key]

            labels: List[str] = []
            for i, item in enumerate(items):
                if isinstance(item, dict):
                    label = item.get("label") or item.get("heading") or item.get("title") or ""
                    if not str(label).strip():
                        errors.append(f"{key}[{i}] has empty label")
                    # Auto-truncate long labels
                    if isinstance(label, str) and len(label) > 30:
                        truncated = label[:27] + "..."
                        logger.warning(
                            "composition_label_truncated",
                            key=key,
                            index=i,
                            original=label,
                            truncated=truncated,
                        )
                        for field in ("label", "heading", "title"):
                            if field in item:
                                item[field] = truncated
                                break
                    labels.append(str(label).strip().lower())

                    # Placeholder detection
                    for field in ("label", "heading", "title", "description", "value"):
                        val = item.get(field, "")
                        if isinstance(val, str) and val.strip().lower() in self._PLACEHOLDERS:
                            errors.append(f"{key}[{i}].{field} contains placeholder text: '{val}'")

            # Check for duplicate labels
            seen: set = set()
            for label in labels:
                if label and label in seen:
                    errors.append(f"Duplicate label in {key}: '{label}'")
                seen.add(label)

        return errors

    @staticmethod
    def _simplify_spec(spec: Dict[str, Any]) -> Dict[str, Any]:
        """Produce a simplified spec for retry: fewer items, no descriptions/edges."""
        import copy

        simplified = copy.deepcopy(spec)
        props = simplified.get("template_props", {})

        # Remove descriptions from list items
        for key in ("clusters", "metrics", "steps", "items", "callouts", "events", "nodes"):
            items = props.get(key, [])
            if not isinstance(items, list):
                continue
            # Truncate to 75% of current length
            cap = max(2, int(len(items) * 0.75))
            props[key] = items[:cap]
            for item in props[key]:
                if isinstance(item, dict):
                    item.pop("description", None)

        # Remove connections and edges (keep core elements)
        props.pop("connections", None)
        props.pop("edges", None)
        props.pop("groups", None)

        return simplified

    def _extract_composition_spec(self, planner_result: "AgentResult") -> Optional[Dict[str, Any]]:
        """Extract structured spec from planner's tool calls."""
        for tc in planner_result.tool_calls:
            if tc.get("name") in ("emit_composition_spec", "plan_composition"):
                tc_result = tc.get("result", {})
                if isinstance(tc_result, dict) and tc_result.get("status") == "spec_ready":
                    return tc_result
        return None

    def _extract_spec_from_text(self, text: str) -> Optional[Dict[str, Any]]:
        """Fallback: extract a spec from planner free-text output (handles nested JSON)."""
        import json as _json

        # Strategy: find every '{' that could start a JSON object containing
        # template_id, then try json.loads from that position.
        if "template_id" not in text or "template_props" not in text:
            return None
        for i, ch in enumerate(text):
            if ch != "{":
                continue
            # Try to parse a JSON object starting here
            try:
                data = _json.loads(text[i:])
            except _json.JSONDecodeError:
                # Try to find the matching closing brace
                depth = 0
                for j in range(i, len(text)):
                    if text[j] == "{":
                        depth += 1
                    elif text[j] == "}":
                        depth -= 1
                    if depth == 0:
                        try:
                            data = _json.loads(text[i : j + 1])
                        except _json.JSONDecodeError:
                            continue
                        break
                else:
                    continue
            if isinstance(data, dict) and "template_id" in data and "template_props" in data:
                return {
                    "status": "spec_ready",
                    "template_id": data["template_id"],
                    "template_props": data["template_props"],
                    "background_prompt": data.get("background_prompt", ""),
                }
        return None

    async def _generate_textless_background(
        self, prompt: str, output_format: str, workspace_id: Optional[str]
    ) -> Optional[str]:
        """Generate a textless background via direct DALL-E API call, return local path.

        Resizes the output to match the exact Remotion canvas dimensions
        (e.g. 1920x1080 for landscape) to eliminate resolution mismatch.
        """
        if not self._visual:
            return None

        from .visual import _call_dalle

        size_map = {
            "landscape": "1792x1024",
            "square": "1024x1024",
            "portrait": "1024x1792",
        }
        size = size_map.get(output_format, "1024x1024")

        # Target dimensions for Remotion canvas
        target_map = {
            "landscape": (1920, 1080),
            "square": (1080, 1080),
            "portrait": (1080, 1920),
        }
        target_size = target_map.get(output_format, (1920, 1080))

        if not self._visual._openai_api_key:
            logger.warning("bg_gen_skipped_no_api_key")
            return None

        try:
            result = await _call_dalle(
                api_key=self._visual._openai_api_key,
                prompt=prompt,
                size=size,
                quality="standard",
                style="natural",
            )
            # Download to local temp file
            import io
            import tempfile

            import httpx

            url = result["url"]
            if url.startswith("file://"):
                local_path = url.removeprefix("file://")
                # Still resize local files
                try:
                    from PIL import Image

                    img = Image.open(local_path)
                    if img.size != target_size:
                        img = img.resize(target_size, Image.LANCZOS)
                        img.save(local_path, format="PNG")
                except Exception:
                    pass  # Proceed with original if resize fails
                return local_path
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    # Resize to match Remotion canvas
                    image_bytes = resp.content
                    try:
                        from PIL import Image

                        img = Image.open(io.BytesIO(image_bytes))
                        if img.size != target_size:
                            img = img.resize(target_size, Image.LANCZOS)
                            buf = io.BytesIO()
                            img.save(buf, format="PNG")
                            image_bytes = buf.getvalue()
                    except Exception:
                        pass  # Proceed with original if resize fails

                    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
                    tmp.write(image_bytes)
                    tmp.close()
                    return tmp.name
        except Exception as bg_err:
            logger.warning("bg_generation_failed", error=str(bg_err))
        return None

    def _register_n8n_tools(self) -> None:
        """Carry forward n8n workflow tools from the original CMOAgent."""
        from ..core.agent import (
            _normalize_connections,
            _normalize_nodes,
            _normalize_settings,
        )

        @self.tool_registry.register(
            name="list_workflows",
            description="List all n8n workflows.",
        )
        async def list_workflows() -> Dict[str, Any]:
            response = await self._n8n.list_workflows()
            return {
                "workflows": [
                    {"id": w.id, "name": w.name, "active": w.active} for w in response.data
                ]
            }

        @self.tool_registry.register(
            name="get_workflow",
            description="Get details of a specific n8n workflow by ID.",
        )
        async def get_workflow(workflow_id: str) -> Dict[str, Any]:
            w = await self._n8n.get_workflow(workflow_id)
            return {
                "id": w.id,
                "name": w.name,
                "active": w.active,
                "nodes": [n.name for n in w.nodes],
            }

        @self.tool_registry.register(
            name="execute_workflow",
            description="Execute an n8n workflow by ID.",
        )
        async def execute_workflow(
            workflow_id: str, data: Optional[Dict[str, Any]] = None
        ) -> Dict[str, Any]:
            execution = await self._n8n.execute_workflow(workflow_id, data)
            result: Dict[str, Any] = {
                "execution_id": execution.id,
                "status": execution.status.value,
            }
            # Auto-diagnose on execution error
            if execution.status.value == "error" and self._workflow_healer:
                try:
                    from .workflow_healer import WorkflowHealerAgent

                    healer: WorkflowHealerAgent = self._workflow_healer  # type: ignore[assignment]
                    diagnosis = await healer._diagnose_workflow_internal(workflow_id)
                    if diagnosis.get("issues"):
                        result["diagnosis"] = diagnosis
                except Exception as diag_err:
                    logger.warning(
                        "auto_diagnosis_failed",
                        workflow_id=workflow_id,
                        error=str(diag_err),
                    )
            return result

        @self.tool_registry.register(
            name="activate_workflow",
            description="Activate an n8n workflow.",
        )
        async def activate_workflow(workflow_id: str) -> Dict[str, Any]:
            w = await self._n8n.activate_workflow(workflow_id)
            return {"id": w.id, "name": w.name, "active": w.active}

        @self.tool_registry.register(
            name="deactivate_workflow",
            description="Deactivate an n8n workflow.",
        )
        async def deactivate_workflow(workflow_id: str) -> Dict[str, Any]:
            w = await self._n8n.deactivate_workflow(workflow_id)
            return {"id": w.id, "name": w.name, "active": w.active}

        @self.tool_registry.register(
            name="create_workflow",
            description="Create a new n8n workflow. Pass nodes as objects, not JSON strings.",
        )
        async def create_workflow(
            workflow_name: str,
            nodes: Any,
            connections: Any,
            settings: Optional[Any] = None,
        ) -> Dict[str, Any]:
            workflow_data = {
                "name": workflow_name,
                "nodes": _normalize_nodes(nodes),
                "connections": _normalize_connections(connections),
                "settings": _normalize_settings(settings),
            }
            w = await self._n8n.create_workflow(workflow_data)
            return {"id": w.id, "name": w.name, "active": w.active}

    def _register_management_tools(self) -> None:
        """Register tools for opportunity, draft, source, and workspace management."""

        @self.tool_registry.register(
            name="list_opportunities",
            description="List marketing opportunities for a workspace. Filter by status or source.",
        )
        async def list_opportunities(
            workspace_id: str,
            status: Optional[str] = None,
            source: Optional[str] = None,
            limit: int = 20,
        ) -> Dict[str, Any]:
            opps = await self._opportunities.list_by_workspace(
                workspace_id, status=status, source=source, limit=limit
            )
            return {
                "workspace_id": workspace_id,
                "count": len(opps),
                "opportunities": [
                    {
                        "id": o.id,
                        "title": o.title[:100],
                        "source": o.source,
                        "score": o.score,
                        "category": o.category,
                        "status": o.status.value,
                        "created_at": str(o.created_at) if o.created_at else None,
                    }
                    for o in opps
                ],
            }

        @self.tool_registry.register(
            name="list_drafts",
            description="List content drafts for a workspace. Filter by status.",
        )
        async def list_drafts(
            workspace_id: str,
            status: Optional[str] = None,
            limit: int = 20,
        ) -> Dict[str, Any]:
            drafts = await self._drafts.list_by_workspace(workspace_id, status=status, limit=limit)
            return {
                "workspace_id": workspace_id,
                "count": len(drafts),
                "drafts": [
                    {
                        "id": d.id,
                        "title": d.title,
                        "content_type": d.content_type,
                        "status": d.status.value,
                        "verify_flags_count": len(d.verify_flags),
                        "created_at": str(d.created_at) if d.created_at else None,
                    }
                    for d in drafts
                ],
            }

        @self.tool_registry.register(
            name="approve_draft",
            description="Approve a content draft.",
        )
        async def approve_draft(draft_id: str) -> Dict[str, Any]:
            from ..db.models import DraftStatus

            await self._drafts.update_status(draft_id, DraftStatus.APPROVED)
            return {"draft_id": draft_id, "status": "approved"}

        @self.tool_registry.register(
            name="reject_draft",
            description="Reject a content draft with an optional reason.",
        )
        async def reject_draft(draft_id: str, reason: Optional[str] = None) -> Dict[str, Any]:
            from ..db.models import DraftStatus

            await self._drafts.update_status(draft_id, DraftStatus.REJECTED, reason)
            return {"draft_id": draft_id, "status": "rejected", "reason": reason}

        @self.tool_registry.register(
            name="list_workspaces",
            description="List all configured workspaces/brands.",
        )
        async def list_workspaces() -> Dict[str, Any]:
            wss = await self._workspaces.list_all()
            return {
                "workspaces": [
                    {
                        "id": ws.id,
                        "name": ws.name,
                        "type": ws.type,
                        "slack_channel": ws.slack_channel,
                        "is_default": ws.is_default,
                    }
                    for ws in wss
                ]
            }

        @self.tool_registry.register(
            name="get_workspace_config",
            description="Show configuration for a workspace including sources and keywords.",
        )
        async def get_workspace_config(workspace_id: str) -> Dict[str, Any]:
            ws = await self._workspaces.get(workspace_id)
            if not ws:
                return {"error": f"Workspace '{workspace_id}' not found"}

            sources = await self._sources.list_by_workspace(workspace_id)
            keywords = await self._workspace_mgr.get_keywords(workspace_id)

            return {
                "workspace": ws.model_dump(mode="json"),
                "keywords": keywords,
                "sources": [
                    {"id": s.id, "type": s.type, "name": s.name, "url": s.url, "active": s.active}
                    for s in sources
                ],
            }

        @self.tool_registry.register(
            name="add_source",
            description="Add a monitoring source (subreddit, rss, gmail_filter, fraud_rss) to a workspace.",
        )
        async def add_source(
            workspace_id: str,
            source_type: str,
            url: str,
            name: Optional[str] = None,
            keywords: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            source = await self._sources.create(
                workspace_id=workspace_id,
                source_type=source_type,
                url=url,
                name=name or url,
                keywords=keywords,
            )
            return {"created": True, "source_id": source.id, "type": source_type}

        @self.tool_registry.register(
            name="remove_source",
            description="Remove a monitoring source by ID.",
        )
        async def remove_source(source_id: str) -> Dict[str, Any]:
            await self._sources.delete(source_id)
            return {"deleted": True, "source_id": source_id}

        # ── Media library tools ───────────────────────────────────────────

        if self._media_storage:

            @self.tool_registry.register(
                name="list_media",
                description="Browse the media library for a workspace. Optionally filter by media_type (image, video, deck) or search by keyword.",
            )
            async def list_media(
                workspace_id: str,
                media_type: Optional[str] = None,
                search: Optional[str] = None,
                limit: int = 20,
            ) -> Dict[str, Any]:
                if search:
                    assets = await self._media_storage.search_assets(workspace_id, search, limit)
                else:
                    assets = await self._media_storage.list_assets(workspace_id, media_type, limit)
                return {
                    "workspace_id": workspace_id,
                    "count": len(assets),
                    "assets": [
                        {
                            "id": a.id,
                            "media_type": a.media_type,
                            "filename": a.filename,
                            "cdn_url": a.cdn_url,
                            "local_path": a.local_path,
                            "source_agent": a.source_agent,
                            "prompt": (a.prompt or "")[:100],
                            "created_at": str(a.created_at) if a.created_at else None,
                        }
                        for a in assets
                    ],
                }

            @self.tool_registry.register(
                name="get_draft_media",
                description="Get all media assets attached to a specific draft.",
            )
            async def get_draft_media(draft_id: str) -> Dict[str, Any]:
                assets = await self._media_storage.get_draft_assets(draft_id)
                return {
                    "draft_id": draft_id,
                    "count": len(assets),
                    "assets": [
                        {
                            "id": a.id,
                            "media_type": a.media_type,
                            "cdn_url": a.cdn_url,
                            "filename": a.filename,
                        }
                        for a in assets
                    ],
                }

        @self.tool_registry.register(
            name="health_check",
            description="Check system health including all agents and n8n connection.",
        )
        async def health_check() -> Dict[str, Any]:
            n8n_healthy = await self._n8n.health_check()
            agents = {
                "research": self._research.agent_id,
                "reddit": self._reddit.agent_id,
                "google_alerts": self._google_alerts.agent_id,
                "writer": self._writer.agent_id,
            }
            if self._visual:
                agents["visual"] = self._visual.agent_id
            if self._video:
                agents["video"] = self._video.agent_id
            if self._deck:
                agents["deck"] = self._deck.agent_id
            if self._performance_marketer:
                agents["performance_marketer"] = self._performance_marketer.agent_id
            if self._social_media:
                agents["social_media"] = self._social_media.agent_id
            if self._workflow_healer:
                agents["workflow_healer"] = self._workflow_healer.agent_id
            if self._workflow_builder:
                agents["workflow_builder"] = self._workflow_builder.agent_id
            if self._docs:
                agents["docs"] = self._docs.agent_id
            if self._sheets:
                agents["sheets"] = self._sheets.agent_id
            if self._motion_graphics:
                agents["motion_graphics"] = self._motion_graphics.agent_id
            if self._lifecycle_marketing:
                agents["lifecycle_marketing"] = self._lifecycle_marketing.agent_id
            if self._growth_ideas:
                agents["growth_ideas"] = self._growth_ideas.agent_id
            if self._marketing_analytics:
                agents["marketing_analytics"] = self._marketing_analytics.agent_id
            if self._acquisition:
                agents["acquisition"] = self._acquisition.agent_id
            if self._conversion_optimization:
                agents["conversion_optimization"] = self._conversion_optimization.agent_id
            if self._compliance:
                agents["compliance"] = self._compliance.agent_id
            if self._legal_strategy:
                agents["legal_strategy"] = self._legal_strategy.agent_id
            if self._telesales:
                agents["telesales"] = self._telesales.agent_id
            if self._sales_ops:
                agents["sales_ops"] = self._sales_ops.agent_id
            if self._linkedin_partnerships:
                agents["linkedin_partnerships"] = self._linkedin_partnerships.agent_id
            if self._knowledge_base:
                agents["knowledge_base"] = self._knowledge_base.agent_id
            if self._experiment_engineer:
                agents["experiment_engineer"] = self._experiment_engineer.agent_id
            if self._editorial:
                agents["editorial"] = self._editorial.agent_id
            if self._gtm:
                agents["gtm"] = self._gtm.agent_id
            if self._seo_aeo:
                agents["seo_aeo"] = self._seo_aeo.agent_id
            if self._composition_planner:
                agents["composition_planner"] = self._composition_planner.agent_id
            result: Dict[str, Any] = {
                "orchestrator": "healthy",
                "n8n": "healthy" if n8n_healthy else "unhealthy",
                "agents": agents,
                "tools_registered": len(self.tool_registry.list_tools()),
            }
            if self._media_storage:
                result["media_storage"] = (
                    "configured" if self._media_storage.is_configured else "local_only"
                )
            return result
