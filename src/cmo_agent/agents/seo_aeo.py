"""SEO & AEO Growth Architect Agent - search architecture and AI answer optimization."""

from __future__ import annotations

import json
import re
from typing import Any, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo, WorkspaceRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# SEO/AEO quality criteria for RefinementLoop
_SEO_AEO_CRITERIA = [
    QualityCriterion(
        name="technical_accuracy",
        description="SEO/AEO specifications are technically correct and follow current search engine guidelines",
    ),
    QualityCriterion(
        name="architectural_coherence",
        description="Keyword clusters, page types, linking, and structured data form a consistent architecture",
    ),
    QualityCriterion(
        name="actionability",
        description="Specifications are detailed enough for a developer or content writer to implement directly",
    ),
    QualityCriterion(
        name="completeness",
        description="All required sections and fields are populated with substantive content, no placeholders",
    ),
    QualityCriterion(
        name="search_intent_alignment",
        description="Content briefs and page types match user search intent and funnel stage",
    ),
]

# ── Marketplace / multi-location optional directive ───────────────────

_MARKETPLACE_DIRECTIVE = """

MARKETPLACE / MULTI-LOCATION DIRECTIVE:
When the workspace operates a marketplace or geo-distributed product:
- Prioritize geographic clustering
- Sequence DMA buildouts intentionally
- Optimize for geo-modified and "near me" queries
- Prevent duplicate descriptions across locations
- Ensure differentiation beyond database fields
- Design compounding link loops between hub, item, and location pages
- Reinforce structured data
- Engineer search moats, not blog volume
"""

# ── GEO (Generative Engine Optimization) framework directive ─────────

_GEO_FRAMEWORK_DIRECTIVE = """

GEO (GENERATIVE ENGINE OPTIMIZATION) FRAMEWORK:

All SEO/AEO deliverables must integrate GEO principles. GEO extends AEO to
explicitly optimize for AI-powered answer engines (ChatGPT Search, Perplexity,
Google AI Overviews, Copilot, Claude) that cite, summarize, and extract content.

PRINCETON GEO CITATION FRAMEWORK — 9 methods ranked by AI citation impact:
1. Cite Sources (+40% visibility) — Reference authoritative studies, data sets, named institutions
2. Include Statistics (+30%) — Quantified claims with named sources beat qualitative assertions
3. Add Quotations (+25%) — Expert quotes with attribution increase extraction probability
4. Fluency Optimization (+15%) — Clear, jargon-appropriate writing improves summarization fidelity
5. Authoritative Tone (+12%) — Confident, expert-level language signals reliability to AI scoring
6. Technical Terminology (+10%) — Domain-specific vocabulary reinforces topical authority
7. Unique Perspective (+8%) — Novel angles reduce substitutability and increase citation preference
8. Easy-to-Understand (+5%) — Accessible structure (short paragraphs, lists) aids extraction
9. Keyword Stuffing (-10%) — Over-optimization degrades AI trust signals — AVOID

AI CRAWLER BOT REFERENCE:
| Bot              | Operator      | Index Source     | Key Signals                          |
|------------------|---------------|------------------|--------------------------------------|
| GPTBot           | OpenAI        | Web crawl        | Structured data, clear headings, FAQ |
| ChatGPT-User     | OpenAI        | Live browse      | Real-time freshness, direct answers  |
| ClaudeBot        | Anthropic     | Web crawl        | Long-form depth, citations, nuance   |
| PerplexityBot    | Perplexity    | Web crawl        | Source attribution, recency          |
| Google-Extended  | Google        | Search index     | E-E-A-T signals, schema, entities    |
| Bingbot          | Microsoft     | Bing index       | Schema, OpenGraph, freshness         |
| Applebot-Extended| Apple         | Safari/Siri      | Structured data, concise answers     |

ENGINE-SPECIFIC PLATFORM INTELLIGENCE:
- ChatGPT Search: Prefers structured data, FAQ sections, authoritative tone. Cites inline.
  Favors content with clear H2 structure and direct answer paragraphs.
- Perplexity: Source-heavy — cites 5-15 sources per answer. Prefers recency, statistics,
  and explicit citations within content. Indexes via PerplexityBot + Bing.
- Google AI Overviews: Extension of Knowledge Graph + featured snippets. E-E-A-T signals,
  schema alignment, and entity clarity dominate. SpeakableSpecification supports voice.
- Microsoft Copilot: Bing-indexed. Favors OpenGraph, schema, FAQ structure. Inline citations.
- Claude (web search): Prefers depth, nuanced analysis, cited statistics, and long-form
  authority. Less snippet-oriented, more synthesis-oriented.

GEO RULES:
- Every content brief MUST include geo_optimization_directives (citation targets, statistics,
  quotation opportunities, target engines, engine-specific notes)
- Every structured data spec MUST include ready-to-paste JSON-LD templates and
  SpeakableSpecification for voice/AI extraction
- Every measurement plan MUST include geo_metrics (AI citation tracking, engine-specific
  visibility, citation rate benchmarks, GEO optimization scoring)
- AI crawler directives (robots.txt, meta tags, HTTP headers) are a first-class deliverable
- Princeton GEO factors must inform all content architecture decisions
"""


def _strip_code_fence(text: str) -> str:
    """Remove markdown code fences from LLM JSON responses."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    return text


def _extract_verify_flags(text: str) -> list[str]:
    """Extract all [VERIFY] flagged claims from content."""
    pattern = r"\[VERIFY\]\s*(.+?)(?:\n|$)"
    matches = re.findall(pattern, text)
    return [m.strip() for m in matches]


class SEOAEOAgent(BaseAgent):
    """Designs, governs, and scales organic discovery systems across products.

    Covers both traditional search engines and AI-driven answer engines.
    Authority on SEO strategy, AEO strategy, information architecture,
    programmatic page design, internal linking systems, structured data,
    and organic performance diagnostics.

    Not a content writer. Not a paid media strategist. Does not define ICP
    or positioning. Operationalizes organic growth within the strategic
    direction defined by the GTM Orchestrator.

    Core capabilities:
    - Keyword and intent architecture
    - Page type governance and standards
    - Internal linking architecture
    - Structured data and entity strategy
    - AEO formatting and snippet optimization
    - Content brief generation for Writer Agent
    - Organic and AI answer performance measurement
    - Crawl integrity and technical SEO specifications
    - Cannibalization detection and prevention
    - SEO roadmap tracking per workspace

    CONVERSION OPTIMIZATION COORDINATION:
    - The Conversion Optimization Agent may optimize on-page conversion elements
      (CTAs, offers, social proof, headlines) on pages you govern.
    - Before accepting structural layout changes from Conversion Optimization,
      verify they don't break page taxonomy, schema integrity, or crawl architecture.
    - You do NOT design conversion experiments — the Conversion Optimization Agent does.
    """

    agent_id = "seo_aeo_agent"
    agent_name = "SEO & AEO Growth Architect"

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

    async def _get_existing_seo_drafts(
        self, workspace_id: str, content_type: str
    ) -> list[dict[str, Any]]:
        """Retrieve existing SEO drafts for context and deduplication."""
        drafts = await self._drafts.list_by_workspace(workspace_id, limit=20)
        return [
            {"id": d.id, "title": d.title, "content_type": d.content_type}
            for d in drafts
            if d.content_type == content_type
        ]

    # ── System prompt ────────────────────────────────────────────────────

    def get_system_prompt(self, workspace_id: str | None = None) -> str:
        ws_label = workspace_id or "all workspaces"

        base = f"""You are the SEO and AEO Growth Architect for the CMOCOROAI ecosystem.
Your scope: {ws_label}.

Your sole responsibility is to design, govern, and scale organic discovery systems across products.
Organic includes both traditional search engines and AI-driven answer engines.

You are the authority on:
- SEO strategy
- AEO strategy
- Information architecture
- Programmatic page design
- Internal linking systems
- Structured data and schema
- Organic and AI surface optimization
- Organic performance diagnostics

CORE PRINCIPLE:
Organic is a compounding asset.
AEO is not a separate channel — it is an extension of SEO architecture optimized for:
- Featured snippets
- AI-generated summaries
- Conversational queries
- Zero-click result surfaces
- Entity-based retrieval systems
All SEO systems must be designed with AEO compatibility from inception.

SCOPE BOUNDARY:
- You do NOT write content. Content creation belongs to Writer Agent. You produce structured briefs.
- You do NOT define ICP, positioning, or messaging pillars. Those belong to GTM Agent. You receive strategic direction and operationalize it into search architecture.
- You do NOT design paid media campaigns. Paid channel strategy belongs to Performance Marketer Agent.
- You do NOT design GA4 event taxonomies or UTM standards. Measurement infrastructure belongs to Marketing Analytics Agent. You define organic-specific KPIs and request dashboards from Analytics.
- You do NOT optimize on-page conversion elements (CTAs, forms, checkout flows). Post-traffic conversion belongs to Acquisition Agent. You design the page architecture; Acquisition optimizes the conversion within it.
- You do NOT manage editorial calendars or content production schedules. Production coordination belongs to Editorial Agent.
- If strategic direction is unclear, you MUST request clarification from the GTM Orchestrator before proceeding.

PRIMARY OBJECTIVES:
1. Translate GTM strategy into scalable search architecture
2. Design compounding organic traffic systems
3. Prevent duplication, cannibalization, and thin content
4. Optimize for both traditional ranking and AI answer extraction
5. Protect crawl integrity at scale
6. Establish measurable organic growth loops

COLLABORATION RULES:

WITH GTM ORCHESTRATOR:
- Receive ICP and geographic priorities
- Translate strategy into organic roadmap
- Validate organic feasibility
- Ensure messaging structure supports answer extraction
- Align organic buildout with phased launch

WITH WRITER AGENT:
All search-targeted content requires a structured brief including:
- Target keyword cluster
- Intent type
- Required headings
- Required direct answer block
- Required FAQ structure
- Schema instructions
- Internal linking requirements
- Word count range
- Snippet optimization rules
Writer does not independently choose strategic keyword targets.

WITH RESEARCH AGENT:
- Request competitive content monitoring via RSS feed scanning
- Request opportunity scoring for SEO-relevant signals
- You do NOT scan feeds directly — delegate to Research Agent

WITH MARKETING ANALYTICS AGENT:
- Define organic-specific KPIs
- Request dashboard specifications
- Define organic attribution logic

WITH EDITORIAL AGENT:
- Provide keyword targets for content bundles via seo_keywords field
- Search-targeted content requires your brief before Writer execution
- You do NOT manage production schedules

WITH EXPERIMENT ENGINEER:
- SEO experiments (title tag tests, schema additions, new page types) should be tracked as experiments
- You define WHAT to test; Experiment Engineer tracks the lifecycle

WITH WORKFLOW BUILDER AGENT:
- Request automated workflows for SEO monitoring (crawl checks, rank alerts, competitor detection)
- Provide workflow specifications; Workflow Builder handles implementation

WITH SHEETS AGENT:
- Provide keyword tracker and ranking dashboard specifications
- Sheets Agent creates the actual Google Sheets

CONFLICT RESOLUTION:
If any agent publishes pages outside approved taxonomy, alters URL structures, modifies schema standards, changes linking logic, or produces search content without mapped intent — you must flag and require alignment. You are the authority on organic and AI answer visibility systems.

WORKFLOW — For new organic buildouts, follow this sequence:
1. create_keyword_architecture() — define cluster targets
2. define_page_type_standards() — set page specs for each page type in scope
3. create_content_brief() — generate briefs per cluster/page combination
4. Hand briefs to orchestrator for Writer Agent execution

For diagnostics:
1. run_organic_audit() — identify issues
2. detect_cannibalization() — check for keyword overlap across existing content
3. Produce action plan with prioritized fixes

DECISION STANDARD:
Every recommendation must answer:
- Does this increase compounding organic visibility?
- Does this improve machine extractability?
- Does this protect crawl integrity?
- Does this reduce cannibalization?
- Does this strengthen entity clarity?
If not, it is not a priority.

IMPORTANT RULES:
- All specific benchmark claims, ranking projections, traffic estimates, and competitive assertions MUST be flagged with [VERIFY] prefix
- All strategic deliverables are saved as drafts for human review
- You provide architecture, not guarantees
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels.

You build durable, scalable organic and AI answer infrastructure.
You are systematic, technical, and decisive.

Current workspace: {ws_label}"""

        # GEO framework applies to all workspaces
        base += _GEO_FRAMEWORK_DIRECTIVE

        # Append marketplace / multi-location directive when applicable.
        # (Configured per-workspace via config key "seo_marketplace_mode"; falls back off.)
        # The current implementation keeps this directive available but does not auto-apply
        # — call sites should pass workspace context if they want it.

        return base

    # ── Tool registration ────────────────────────────────────────────────

    def register_tools(self) -> None:
        self._register_architecture_tools()
        self._register_brief_tools()
        self._register_diagnostic_tools()
        self._register_spec_tools()
        self._register_tracker_tools()

    def _register_architecture_tools(self) -> None:
        """Architecture tools — create governing artifacts, saved as drafts."""

        # ── create_keyword_architecture ──────────────────────────────
        @self.tool_registry.register(
            name="create_keyword_architecture",
            description=(
                "Create a keyword and intent architecture for a product or market. "
                "Clusters keywords by search intent, maps to page types, identifies "
                "AI conversational query variants. Aligns to GTM beachhead markets. "
                "Requires: workspace_id, product_description. Optional: geographic_focus, "
                "priority_page_types."
            ),
        )
        async def create_keyword_architecture(
            workspace_id: str,
            product_description: str,
            geographic_focus: str = "",
            priority_page_types: Optional[List[str]] = None,
        ) -> dict[str, Any]:
            return await self._create_keyword_architecture(
                workspace_id=workspace_id,
                product_description=product_description,
                geographic_focus=geographic_focus,
                priority_page_types=priority_page_types,
            )

        # ── define_page_type_standards ───────────────────────────────
        @self.tool_registry.register(
            name="define_page_type_standards",
            description=(
                "Define governance standards for a specific page type (e.g., dma, zip, "
                "merchant, location, discount_detail, faq_hub, comparison, guide). "
                "Returns required content sections, heading hierarchy, FAQ requirements, "
                "direct answer placement, schema requirements, linking rules, canonical "
                "logic, index/noindex rules, and AEO requirements."
            ),
        )
        async def define_page_type_standards(
            workspace_id: str,
            page_type: str,
            product_context: str = "",
        ) -> dict[str, Any]:
            return await self._define_page_type_standards(
                workspace_id=workspace_id,
                page_type=page_type,
                product_context=product_context,
            )

        # ── design_internal_linking_architecture ─────────────────────
        @self.tool_registry.register(
            name="design_internal_linking_architecture",
            description=(
                "Design internal linking rules and topology for a set of page types. "
                "Covers geographic clustering loops, merchant-to-location linking, "
                "DMA-to-location linking, anchor text standards, automated linking rules, "
                "and orphan page prevention. Reinforces both ranking authority and entity "
                "clarity for AI systems."
            ),
        )
        async def design_internal_linking_architecture(
            workspace_id: str,
            page_types: list[str],
            geographic_scope: str = "",
        ) -> dict[str, Any]:
            return await self._design_internal_linking(
                workspace_id=workspace_id,
                page_types=page_types,
                geographic_scope=geographic_scope,
            )

        # ── create_structured_data_spec ──────────────────────────────
        @self.tool_registry.register(
            name="create_structured_data_spec",
            description=(
                "Define structured data (schema.org) requirements for a page type. "
                "Covers required schema types, local business schema, offer schema, "
                "FAQ schema, breadcrumb schema, organization schema, entity "
                "reinforcement strategy, ready-to-paste JSON-LD templates, and "
                "SpeakableSpecification for voice/AI extraction. Ensures machine "
                "parsability."
            ),
        )
        async def create_structured_data_spec(
            workspace_id: str,
            page_type: str,
            entity_types: Optional[List[str]] = None,
        ) -> dict[str, Any]:
            return await self._create_structured_data_spec(
                workspace_id=workspace_id,
                page_type=page_type,
                entity_types=entity_types,
            )

        # ── create_organic_measurement_plan ──────────────────────────
        @self.tool_registry.register(
            name="create_organic_measurement_plan",
            description=(
                "Define organic, AEO, and GEO performance measurement plan. Covers "
                "page-type level reporting, cluster performance tracking, "
                "impression-to-click optimization, ranking velocity, cannibalization "
                "detection, AI answer visibility indicators, featured snippet capture "
                "rate, zero-click query trends, and GEO metrics (AI citation tracking, "
                "engine-specific visibility, citation rate benchmarks). Produces "
                "action-plan-oriented metrics, not just reports."
            ),
        )
        async def create_organic_measurement_plan(
            workspace_id: str,
            page_types: Optional[List[str]] = None,
            priority_clusters: Optional[List[str]] = None,
        ) -> dict[str, Any]:
            return await self._create_organic_measurement_plan(
                workspace_id=workspace_id,
                page_types=page_types,
                priority_clusters=priority_clusters,
            )

    def _register_brief_tools(self) -> None:
        """Brief generation — actionable output for Writer Agent."""

        # ── create_content_brief ─────────────────────────────────────
        @self.tool_registry.register(
            name="create_content_brief",
            description=(
                "Generate a structured SEO/AEO/GEO content brief for the Writer Agent. "
                "Includes target keyword cluster, intent type, required headings, "
                "direct answer block spec, FAQ structure, schema instructions, "
                "internal linking requirements, word count range, snippet "
                "optimization rules, and GEO optimization directives (citation "
                "targets, statistics, quotation opportunities, target AI engines). "
                "This is the handoff document to Writer Agent. "
                "Checks for existing briefs targeting the same cluster to prevent "
                "duplication."
            ),
        )
        async def create_content_brief(
            workspace_id: str,
            target_keyword_cluster: str,
            page_type: str,
            intent_type: str = "",
            geographic_target: str = "",
        ) -> dict[str, Any]:
            return await self._create_content_brief(
                workspace_id=workspace_id,
                target_keyword_cluster=target_keyword_cluster,
                page_type=page_type,
                intent_type=intent_type,
                geographic_target=geographic_target,
            )

    def _register_diagnostic_tools(self) -> None:
        """Diagnostic tools — analysis only, no artifact saved."""

        # ── run_organic_audit ────────────────────────────────────────
        @self.tool_registry.register(
            name="run_organic_audit",
            description=(
                "Run an organic audit for a workspace. Analyzes existing SEO artifacts "
                "(keyword architectures, page type specs, content briefs) and identifies "
                "issues: thin content risks, crawl integrity problems, schema gaps, "
                "missing linking rules, AEO compliance gaps. Returns prioritized findings "
                "with severity scoring and recommended fixes. Does NOT save a draft — "
                "returns analysis directly."
            ),
        )
        async def run_organic_audit(
            workspace_id: str,
            audit_scope: str = "full",
            focus_page_types: Optional[List[str]] = None,
        ) -> dict[str, Any]:
            return await self._run_organic_audit(
                workspace_id=workspace_id,
                audit_scope=audit_scope,
                focus_page_types=focus_page_types,
            )

        # ── detect_cannibalization ───────────────────────────────────
        @self.tool_registry.register(
            name="detect_cannibalization",
            description=(
                "Detect keyword cannibalization across existing content. Analyzes "
                "keyword architectures and content briefs for the workspace to find "
                "overlapping keyword targets, duplicate intent coverage, and competing "
                "pages. Returns analysis directly — does NOT save a draft."
            ),
        )
        async def detect_cannibalization(
            workspace_id: str,
            keyword_clusters: Optional[List[str]] = None,
        ) -> dict[str, Any]:
            return await self._detect_cannibalization(
                workspace_id=workspace_id,
                keyword_clusters=keyword_clusters,
            )

    def _register_spec_tools(self) -> None:
        """Spec tools — produce specifications for downstream agents."""

        # ── create_keyword_tracker_spec ──────────────────────────────
        @self.tool_registry.register(
            name="create_keyword_tracker_spec",
            description=(
                "Produce a structured specification for a keyword tracking spreadsheet. "
                "The orchestrator passes this to sheets_agent for Google Sheets creation. "
                "Includes columns, pre-populated rows from keyword architecture, formulas, "
                "and conditional formatting rules."
            ),
        )
        async def create_keyword_tracker_spec(
            workspace_id: str,
            tracker_type: str = "keyword_ranking",
            keyword_clusters: Optional[List[str]] = None,
        ) -> dict[str, Any]:
            return await self._create_keyword_tracker_spec(
                workspace_id=workspace_id,
                tracker_type=tracker_type,
                keyword_clusters=keyword_clusters,
            )

        # ── create_monitoring_workflow_spec ───────────────────────────
        @self.tool_registry.register(
            name="create_monitoring_workflow_spec",
            description=(
                "Produce a workflow specification for automated SEO monitoring. "
                "The orchestrator passes this to workflow_builder_agent for n8n "
                "workflow creation. Defines trigger type, schedule, data sources, "
                "alert conditions, and notification channels."
            ),
        )
        async def create_monitoring_workflow_spec(
            workspace_id: str,
            monitoring_type: str,
            alert_conditions: Optional[List[str]] = None,
        ) -> dict[str, Any]:
            return await self._create_monitoring_workflow_spec(
                workspace_id=workspace_id,
                monitoring_type=monitoring_type,
                alert_conditions=alert_conditions,
            )

        # ── sync_workspace_keywords ──────────────────────────────────
        @self.tool_registry.register(
            name="sync_workspace_keywords",
            description=(
                "Sync workspace keyword list from the most recent approved keyword "
                "architecture. Updates the workspace keywords that Research Agent uses "
                "for RSS scoring. Pure data operation — no LLM call."
            ),
        )
        async def sync_workspace_keywords(
            workspace_id: str,
        ) -> dict[str, Any]:
            return await self._sync_workspace_keywords(workspace_id=workspace_id)

        # ── create_ai_crawler_spec ───────────────────────────────────
        @self.tool_registry.register(
            name="create_ai_crawler_spec",
            description=(
                "Create AI crawler directive specification — robots.txt rules for "
                "GPTBot, ClaudeBot, PerplexityBot, Google-Extended, and other AI "
                "crawlers. Includes ready-to-paste robots.txt blocks, AI-specific "
                "meta tags, HTTP header recommendations, per-bot strategy with "
                "business rationale, and implementation checklist. "
                "Requires: workspace_id. Optional: site_url, crawl_strategy."
            ),
        )
        async def create_ai_crawler_spec(
            workspace_id: str,
            site_url: str = "",
            crawl_strategy: str = "selective_allow",
        ) -> dict[str, Any]:
            return await self._create_ai_crawler_spec(
                workspace_id=workspace_id,
                site_url=site_url,
                crawl_strategy=crawl_strategy,
            )

    def _register_tracker_tools(self) -> None:
        """Tracker tools — roadmap status via ConfigRepo, no LLM call."""

        # ── get_seo_roadmap_status ───────────────────────────────────
        @self.tool_registry.register(
            name="get_seo_roadmap_status",
            description=(
                "Get current SEO roadmap status for a workspace. Returns current "
                "phase, completed milestones, pending items, and phase history. "
                "No LLM call — reads from workspace config."
            ),
        )
        async def get_seo_roadmap_status(
            workspace_id: str,
        ) -> dict[str, Any]:
            return await self._get_seo_roadmap_status(workspace_id=workspace_id)

        # ── update_seo_roadmap ───────────────────────────────────────
        @self.tool_registry.register(
            name="update_seo_roadmap",
            description=(
                "Update SEO roadmap phase or milestones for a workspace. Records "
                "phase transitions and milestone completions. No LLM call — writes "
                "to workspace config."
            ),
        )
        async def update_seo_roadmap(
            workspace_id: str,
            phase: str,
            milestones_completed: list[str],
            milestones_pending: Optional[List[str]] = None,
            notes: str = "",
        ) -> dict[str, Any]:
            return await self._update_seo_roadmap(
                workspace_id=workspace_id,
                phase=phase,
                milestones_completed=milestones_completed,
                milestones_pending=milestones_pending,
                notes=notes,
            )

    # ── Tool implementations ────────────────────────────────────────────

    async def _create_keyword_architecture(
        self,
        workspace_id: str,
        product_description: str,
        geographic_focus: str = "",
        priority_page_types: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Generate a keyword and intent architecture."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        # Load existing workspace keywords as seed data
        existing_keywords = await self._workspace_mgr.get_keywords(workspace_id)
        kw_context = ""
        if existing_keywords:
            kw_context = f"\nEXISTING WORKSPACE KEYWORDS:\n{', '.join(existing_keywords[:50])}\n"

        # Check for existing keyword architectures to avoid duplication
        existing = await self._get_existing_seo_drafts(workspace_id, "seo_keyword_architecture")
        existing_context = ""
        if existing:
            existing_context = (
                "\nEXISTING KEYWORD ARCHITECTURES (avoid duplication):\n"
                + "\n".join(f"- {d['title']}" for d in existing[:5])
                + "\n"
            )

        page_types_text = ""
        if priority_page_types:
            page_types_text = f"\nPRIORITY PAGE TYPES: {', '.join(priority_page_types)}"

        geo_text = ""
        if geographic_focus:
            geo_text = f"\nGEOGRAPHIC FOCUS: {geographic_focus}"

        prompt = f"""Create a keyword and intent architecture for:

PRODUCT: {product_description}
{geo_text}
{page_types_text}
{kw_context}
{existing_context}
{context_section}

You MUST return structured JSON with key "clusters" containing an array.
Each cluster object MUST have these exact keys:

{{
  "cluster_name": "<descriptive name>",
  "intent_type": "commercial|informational|navigational|local",
  "primary_keyword": "<highest volume target>",
  "secondary_keywords": ["<list of supporting keywords>"],
  "conversational_query_variants": ["<how people ask AI assistants>"],
  "target_page_type": "<dma|zip|merchant|location|faq_hub|comparison|guide|discount_detail>",
  "priority_score": <1-10 integer>,
  "estimated_monthly_volume": "[VERIFY] <range estimate>",
  "competition_level": "low|medium|high"
}}

Also include a top-level key "architecture_summary" with:
- total_clusters: count
- intent_distribution: object with counts per intent type
- page_type_distribution: object with counts per page type
- geographic_relevance: how clusters map to geographic targets
- aeo_opportunity_score: 1-10 estimate of AI answer extraction potential

RULES:
- Cluster by search intent first, then by topic
- Distinguish commercial, informational, navigational, and local intent
- Include conversational query variants for every cluster (AEO readiness)
- Align priority clusters to GTM beachhead markets
- No content may be produced without mapped intent
- Flag all volume estimates with [VERIFY]
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_keyword_arch_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            architecture = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            architecture = {"raw_architecture": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_keyword_architecture",
            title=f"Keyword Architecture: {product_description[:80]}",
            body=json.dumps(architecture, indent=2) if isinstance(architecture, dict) else content,
            verify_flags=verify_flags,
        )

        cluster_count = 0
        if isinstance(architecture, dict) and "clusters" in architecture:
            cluster_count = len(architecture["clusters"])

        logger.info(
            "seo_keyword_architecture_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            cluster_count=cluster_count,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "architecture": architecture,
            "cluster_count": cluster_count,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
        }

    async def _define_page_type_standards(
        self,
        workspace_id: str,
        page_type: str,
        product_context: str = "",
    ) -> dict[str, Any]:
        """Define governance standards for a specific page type."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        prompt = f"""Define complete governance standards for this page type:

PAGE TYPE: {page_type}
{f"PRODUCT CONTEXT: {product_context}" if product_context else ""}

{context_section}

Return structured JSON with ALL of these sections:

{{
  "page_type": "{page_type}",
  "required_content_sections": ["<ordered list of required sections>"],
  "h1_structure_rules": "<exact H1 format pattern, e.g., '{{Discount Type}} in {{City}}, {{State}}'",
  "h2_hierarchy": ["<required H2s in order>"],
  "faq_requirements": {{
    "min_questions": <int>,
    "required_question_patterns": ["<question templates>"],
    "answer_format": "paragraph|list|mixed"
  }},
  "direct_answer_placement": {{
    "position": "after_h1|first_paragraph|dedicated_section",
    "max_words": <int>,
    "format": "paragraph|list|table"
  }},
  "minimum_depth_standards": {{
    "min_word_count": <int>,
    "min_sections": <int>,
    "min_internal_links": <int>,
    "min_faq_items": <int>
  }},
  "schema_requirements": ["<required schema types, e.g., LocalBusiness, FAQPage, Offer>"],
  "internal_linking_rules": {{
    "required_link_targets": ["<page types this must link to>"],
    "max_outbound_links": <int>,
    "anchor_text_rules": "<guidance>"
  }},
  "canonical_rules": "<self-referencing|parameter-stripped|parent-page>",
  "index_logic": "<conditions for index vs noindex>",
  "aeo_requirements": {{
    "extractable_answer_block": true,
    "faq_for_conversational_extraction": true,
    "entity_reinforcement": "<how to reinforce entity>",
    "schema_content_alignment": "<rule>",
    "short_paragraph_optimization": "<max words per paragraph for AI summarization>"
  }},
  "url_structure": "<pattern, e.g., '/{{state}}/{{city}}/{{page_type}}'>"
}}

RULES:
- Be specific to the page type, not generic
- H1 rules must include variable patterns where applicable
- Schema requirements must list specific schema.org types
- AEO requirements must ensure content is extractable by AI systems
- All standards must be enforceable by Writer Agent
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_page_type_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            standards = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            standards = {"raw_standards": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_page_type_spec",
            title=f"Page Type Standards: {page_type}",
            body=json.dumps(standards, indent=2) if isinstance(standards, dict) else content,
            verify_flags=verify_flags,
        )

        logger.info(
            "seo_page_type_standards_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            page_type=page_type,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "page_type": page_type,
            "standards": standards,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
        }

    async def _design_internal_linking(
        self,
        workspace_id: str,
        page_types: list[str],
        geographic_scope: str = "",
    ) -> dict[str, Any]:
        """Design internal linking architecture for a set of page types."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        prompt = f"""Design an internal linking architecture for these page types:

PAGE TYPES: {", ".join(page_types)}
{f"GEOGRAPHIC SCOPE: {geographic_scope}" if geographic_scope else ""}

{context_section}

Return structured JSON with:

{{
  "linking_topology": [
    {{
      "source_page_type": "<page type>",
      "target_page_type": "<page type>",
      "link_type": "geographic_cluster|thematic_cross_link|breadcrumb|related_entity|parent_child",
      "anchor_text_pattern": "<template, e.g., '{{Merchant Name}} in {{City}}'",
      "max_links_per_page": <int>,
      "bidirectional": <bool>
    }}
  ],
  "geographic_clustering_loops": {{
    "dma_to_location": "<rule>",
    "location_to_merchant": "<rule>",
    "merchant_to_dma": "<rule>",
    "cross_dma_linking": "<rule>"
  }},
  "anchor_text_standards": {{
    "max_exact_match_ratio": <float 0-1>,
    "variation_rules": "<guidance>",
    "prohibited_patterns": ["<patterns to avoid>"]
  }},
  "automated_linking_rules": [
    {{
      "rule_name": "<name>",
      "trigger": "<when to auto-link>",
      "target_selection": "<how to choose link target>",
      "max_auto_links": <int>
    }}
  ],
  "prevention_rules": {{
    "orphan_page_detection": "<how to detect and prevent>",
    "over_optimization_limits": "<thresholds>",
    "irrelevant_cross_linking": "<what to block>",
    "link_equity_dilution": "<max outbound links guidance>"
  }}
}}

RULES:
- Internal linking must reinforce both ranking authority and entity clarity for AI systems
- Prevent orphan pages, anchor text over-optimization, irrelevant cross-linking, and link equity dilution
- Geographic clustering loops are critical for marketplace products
- Every link must serve either topical relevance or geographic authority
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_linking_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            linking = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            linking = {"raw_linking": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_linking_architecture",
            title=f"Internal Linking Architecture: {', '.join(page_types[:3])}",
            body=json.dumps(linking, indent=2) if isinstance(linking, dict) else content,
            verify_flags=verify_flags,
        )

        logger.info(
            "seo_linking_architecture_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            page_types=page_types,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "linking_architecture": linking,
            "page_types": page_types,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
        }

    async def _create_structured_data_spec(
        self,
        workspace_id: str,
        page_type: str,
        entity_types: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Define structured data requirements for a page type."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        entity_text = ""
        if entity_types:
            entity_text = f"\nENTITY TYPES TO REINFORCE: {', '.join(entity_types)}"

        prompt = f"""Define structured data (schema.org) requirements for:

PAGE TYPE: {page_type}
{entity_text}

{context_section}

Return structured JSON with:

{{
  "page_type": "{page_type}",
  "required_schemas": [
    {{
      "schema_type": "<e.g., LocalBusiness, FAQPage, Offer, Article>",
      "required_properties": ["<list of required properties>"],
      "recommended_properties": ["<list of recommended properties>"],
      "example_json_ld": "<complete JSON-LD example>",
      "validation_rules": ["<rules for content-schema alignment>"]
    }}
  ],
  "entity_reinforcement_strategy": {{
    "primary_entity": "<main entity type>",
    "naming_consistency_rules": "<how to keep entity names consistent>",
    "geographic_signal_rules": "<how to reinforce geographic signals>",
    "attribute_machine_readability": "<rules for machine-parsable attributes>"
  }},
  "breadcrumb_schema": {{
    "structure": "<breadcrumb hierarchy pattern>",
    "example": "<JSON-LD example>"
  }},
  "organization_schema": {{
    "when_to_include": "<conditions>",
    "required_properties": ["<list>"]
  }},
  "ready_to_paste_templates": [
    {{
      "schema_type": "<e.g., FAQPage, Article, Organization, LocalBusiness, BreadcrumbList>",
      "json_ld": "<complete <script type=\\"application/ld+json\\">...</script> block ready to paste>",
      "notes": "<where to place and what to customize>"
    }}
  ],
  "combined_graph_template": "<complete <script type=\\"application/ld+json\\"> block using @graph to combine all schemas for this page type>",
  "speakable_specification": {{
    "css_selectors": ["<CSS selectors targeting direct-answer and FAQ sections>"],
    "json_ld": "<complete SpeakableSpecification JSON-LD block>",
    "purpose": "Enables voice assistants and AI engines to identify key extractable sections"
  }},
  "implementation_notes": [
    "<technical notes for engineering team>"
  ]
}}

RULES:
- Structured data MUST reflect visible content — no hidden markup
- Entity naming must be consistent across all page types
- Geographic signals must be reinforced in structured data
- Think in terms of machine parsability, not just human readability
- Discount and offer attributes must be machine-readable
- ready_to_paste_templates must contain complete <script type="application/ld+json"> blocks
- combined_graph_template must use @graph array to bundle all schemas
- speakable_specification must target direct answer blocks and FAQ sections
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_structured_data_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            spec = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            spec = {"raw_spec": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_structured_data",
            title=f"Structured Data Spec: {page_type}",
            body=json.dumps(spec, indent=2) if isinstance(spec, dict) else content,
            verify_flags=verify_flags,
        )

        logger.info(
            "seo_structured_data_spec_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            page_type=page_type,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "page_type": page_type,
            "structured_data_spec": spec,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
        }

    async def _create_organic_measurement_plan(
        self,
        workspace_id: str,
        page_types: Optional[List[str]] = None,
        priority_clusters: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Define organic and AEO performance measurement plan."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        page_text = ""
        if page_types:
            page_text = f"\nPAGE TYPES IN SCOPE: {', '.join(page_types)}"

        cluster_text = ""
        if priority_clusters:
            cluster_text = f"\nPRIORITY CLUSTERS: {', '.join(priority_clusters)}"

        prompt = f"""Define an organic and AEO performance measurement plan for workspace: {workspace_id}
{page_text}
{cluster_text}

{context_section}

Return structured JSON with:

{{
  "page_type_reporting": [
    {{
      "page_type": "<type>",
      "kpis": ["<list of KPIs>"],
      "targets": {{"<kpi>": "<target value>"}},
      "reporting_frequency": "daily|weekly|monthly"
    }}
  ],
  "cluster_performance_tracking": {{
    "tracking_dimensions": ["<keyword cluster, intent type, page type, geography>"],
    "metrics": ["<impressions, clicks, CTR, avg_position, conversions>"],
    "aggregation_rules": "<how to roll up cluster metrics>"
  }},
  "impression_to_click_optimization": {{
    "ctr_benchmarks_by_position": {{"1": "<target>", "2-3": "<target>", "4-10": "<target>"}},
    "optimization_triggers": ["<when to intervene>"],
    "action_playbook": ["<what to do when CTR is below target>"]
  }},
  "ranking_velocity_tracking": {{
    "measurement_cadence": "<frequency>",
    "velocity_thresholds": {{"improving": "<definition>", "stagnant": "<definition>", "declining": "<definition>"}},
    "escalation_rules": "<when to alert>"
  }},
  "cannibalization_detection": {{
    "detection_method": "<how to identify>",
    "monitoring_frequency": "<cadence>",
    "resolution_playbook": ["<steps to fix>"]
  }},
  "aeo_visibility_indicators": {{
    "featured_snippet_capture_rate": "<how to measure>",
    "ai_answer_inclusion_tracking": "<method>",
    "zero_click_query_trends": "<how to monitor>",
    "entity_recognition_signals": "<what to track>"
  }},
  "alert_thresholds": [
    {{
      "metric": "<name>",
      "condition": "<threshold>",
      "severity": "critical|warning|info",
      "action": "<what to do>"
    }}
  ],
  "geo_metrics": {{
    "ai_citation_tracking": {{
      "method": "<how to detect AI engine citations of your content>",
      "tools": ["<tools or techniques for citation monitoring>"],
      "frequency": "<monitoring cadence>"
    }},
    "engine_specific_visibility": [
      {{
        "engine": "<ChatGPT Search|Perplexity|Google AI Overview|Copilot|Claude>",
        "measurement_method": "<how to measure visibility on this engine>",
        "target_metric": "<what to track>",
        "baseline_methodology": "<how to establish baseline>"
      }}
    ],
    "citation_rate_benchmarks": {{
      "target_citation_rate": "[VERIFY] <target percentage of queries where content is cited>",
      "baseline_methodology": "<how to measure current citation rate>",
      "improvement_cadence": "<expected improvement timeline>"
    }},
    "geo_optimization_tracking": {{
      "princeton_factor_scoring": "<how to score content against Princeton GEO factors per page>",
      "ab_test_recommendations": ["<GEO-specific tests: e.g., with/without citations, with/without statistics>"]
    }}
  }}
}}

RULES:
- Provide action plans, not just reports
- Every metric must have a target and an escalation threshold
- AEO visibility must be measured alongside traditional SEO metrics
- GEO metrics must cover all 5 major AI engines
- [VERIFY] any specific benchmark numbers
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_measurement_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            plan = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            plan = {"raw_plan": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_measurement_plan",
            title=f"Organic Measurement Plan: {workspace_id}",
            body=json.dumps(plan, indent=2) if isinstance(plan, dict) else content,
            verify_flags=verify_flags,
        )

        logger.info(
            "seo_measurement_plan_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "measurement_plan": plan,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
        }

    # ── Content brief ────────────────────────────────────────────────────

    async def _create_content_brief(
        self,
        workspace_id: str,
        target_keyword_cluster: str,
        page_type: str,
        intent_type: str = "",
        geographic_target: str = "",
    ) -> dict[str, Any]:
        """Generate a structured content brief for Writer Agent."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        # Check for existing briefs targeting this cluster
        existing_briefs = await self._get_existing_seo_drafts(workspace_id, "seo_content_brief")
        dedup_context = ""
        if existing_briefs:
            dedup_context = (
                "\nEXISTING CONTENT BRIEFS (check for duplication):\n"
                + "\n".join(f"- {d['title']}" for d in existing_briefs[:10])
                + "\n\nDo NOT create a brief that duplicates an existing one. "
                "If this cluster is already covered, state so and suggest differentiation.\n"
            )

        prompt = f"""Generate a structured SEO/AEO content brief for the Writer Agent.

TARGET KEYWORD CLUSTER: {target_keyword_cluster}
PAGE TYPE: {page_type}
{f"INTENT TYPE: {intent_type}" if intent_type else ""}
{f"GEOGRAPHIC TARGET: {geographic_target}" if geographic_target else ""}
{dedup_context}
{context_section}

Return structured JSON with EXACTLY this schema — the Writer Agent parses this programmatically:

{{
  "brief_type": "seo_content_brief",
  "target_cluster": {{
    "name": "<cluster name>",
    "intent": "commercial|informational|navigational|local",
    "primary_keyword": "<main keyword target>",
    "secondary_keywords": ["<supporting keywords>"],
    "conversational_query_variants": ["<AI assistant query forms>"]
  }},
  "page_type": "{page_type}",
  "required_h1": "<exact H1 text or pattern with variables>",
  "required_h2_hierarchy": ["<ordered list of required H2 headings>"],
  "direct_answer_block": {{
    "target_query": "<the question this block answers>",
    "max_words": <int, typically 40-60>,
    "format": "paragraph|list|table",
    "placement": "first_paragraph|after_h1|dedicated_section"
  }},
  "faq_requirements": {{
    "min_questions": <int>,
    "required_questions": ["<specific questions that must be answered>"],
    "format": "conversational|formal",
    "schema_required": true
  }},
  "schema_instructions": [
    "<specific schema.org types to implement>",
    "<property requirements>"
  ],
  "internal_linking_requirements": [
    {{
      "anchor_text_pattern": "<suggested anchor text>",
      "target_page_type": "<where to link>",
      "context": "<where in content to place link>"
    }}
  ],
  "word_count_range": {{
    "min": <int>,
    "max": <int>
  }},
  "snippet_optimization_rules": [
    "<specific rules for featured snippet optimization>"
  ],
  "aeo_requirements": [
    "<specific rules for AI answer engine extractability>"
  ],
  "geo_optimization_directives": {{
    "citation_targets": ["<authoritative sources to cite — studies, institutions, data sets>"],
    "statistics_to_include": ["<quantified data points with named sources>"],
    "quotation_opportunities": ["<expert quotes to incorporate with attribution>"],
    "tone_profile": "authoritative|accessible|technical",
    "target_engines": ["chatgpt_search", "perplexity", "google_ai_overview"],
    "engine_specific_notes": ["<per-engine optimization tips for this content>"],
    "fluency_priority": "high|medium",
    "unique_angle": "<what makes this distinctively valuable vs competitors>"
  }},
  "content_differentiation_notes": "<what makes this content unique vs existing pages>"
}}

RULES:
- This brief must be specific enough that Writer Agent can follow it mechanically
- Include conversational query variants for AEO
- H2 hierarchy must support featured snippet extraction
- Direct answer block must be concise and extractable
- FAQ questions must match real search queries
- All schema instructions must reference specific schema.org types
- geo_optimization_directives must include at least 3 citation targets and 2 statistics
- target_engines must be selected based on audience intent and platform relevance
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_content_brief_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            brief = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            brief = {"raw_brief": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_content_brief",
            title=f"SEO Brief: {target_keyword_cluster} ({page_type})",
            body=json.dumps(brief, indent=2) if isinstance(brief, dict) else content,
            verify_flags=verify_flags,
        )

        logger.info(
            "seo_content_brief_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            cluster=target_keyword_cluster,
            page_type=page_type,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "brief": brief,
            "target_cluster": target_keyword_cluster,
            "page_type": page_type,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
        }

    # ── Diagnostic tools ─────────────────────────────────────────────────

    async def _run_organic_audit(
        self,
        workspace_id: str,
        audit_scope: str = "full",
        focus_page_types: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Run an organic audit against existing SEO artifacts."""
        # Gather existing SEO artifacts for context
        all_drafts = await self._drafts.list_by_workspace(workspace_id, limit=50)
        seo_drafts = [
            d
            for d in all_drafts
            if d.content_type
            in (
                "seo_keyword_architecture",
                "seo_page_type_spec",
                "seo_content_brief",
                "seo_linking_architecture",
                "seo_structured_data",
                "seo_measurement_plan",
                "seo_ai_crawler_spec",
            )
        ]

        artifact_summary = "NO EXISTING SEO ARTIFACTS FOUND."
        if seo_drafts:
            lines = []
            for d in seo_drafts:
                body_preview = (d.body or "")[:200]
                lines.append(f"- [{d.content_type}] {d.title}: {body_preview}")
            artifact_summary = "\n".join(lines)

        focus_text = ""
        if focus_page_types:
            focus_text = f"\nFOCUS PAGE TYPES: {', '.join(focus_page_types)}"

        prompt = f"""Run an organic SEO/AEO audit for workspace: {workspace_id}
AUDIT SCOPE: {audit_scope}
{focus_text}

EXISTING SEO ARTIFACTS:
{artifact_summary}

Analyze the existing SEO artifacts and identify issues across these categories:

1. CRAWL INTEGRITY — thin content risks, near-duplicate pages, over-templated content, parameter handling gaps
2. CANNIBALIZATION — overlapping keyword targets, duplicate intent coverage, competing pages
3. SCHEMA GAPS — missing structured data, misaligned schema-content, incomplete entity markup
4. LINKING GAPS — orphan pages, missing cross-links, anchor text issues, equity dilution
5. AEO COMPLIANCE — missing direct answer blocks, no FAQ sections, poor AI extractability
6. ARCHITECTURE GAPS — missing page type standards, undefined URL structures, no canonical rules

Return structured JSON with:
{{
  "audit_summary": {{
    "total_issues": <int>,
    "critical": <int>,
    "warning": <int>,
    "info": <int>,
    "overall_health_score": <1-10>
  }},
  "findings": [
    {{
      "category": "<category from list above>",
      "severity": "critical|warning|info",
      "title": "<short description>",
      "detail": "<explanation>",
      "recommended_fix": "<specific action>",
      "priority": <1-10>
    }}
  ],
  "action_plan": [
    {{
      "priority": <int>,
      "action": "<what to do>",
      "agent": "<which agent should handle>",
      "estimated_impact": "high|medium|low"
    }}
  ]
}}
"""

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.3,
            max_tokens=6144,
        )

        content = _strip_code_fence(response.content)

        try:
            audit = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            audit = {"raw_audit": content}

        logger.info(
            "seo_organic_audit_completed",
            workspace_id=workspace_id,
            scope=audit_scope,
            artifacts_analyzed=len(seo_drafts),
        )

        # Return analysis directly — no draft saved
        return {
            "status": "completed",
            "audit": audit,
            "artifacts_analyzed": len(seo_drafts),
            "workspace_id": workspace_id,
        }

    async def _detect_cannibalization(
        self,
        workspace_id: str,
        keyword_clusters: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Detect keyword cannibalization across existing content."""
        # Pull all keyword architectures and content briefs
        all_drafts = await self._drafts.list_by_workspace(workspace_id, limit=50)
        keyword_drafts = [
            d
            for d in all_drafts
            if d.content_type in ("seo_keyword_architecture", "seo_content_brief")
        ]

        if not keyword_drafts:
            return {
                "status": "no_data",
                "message": "No keyword architectures or content briefs found. "
                "Run create_keyword_architecture first.",
                "workspace_id": workspace_id,
            }

        # Build context from existing keyword data
        kw_context_lines = []
        for d in keyword_drafts:
            body_preview = (d.body or "")[:500]
            kw_context_lines.append(f"[{d.content_type}] {d.title}:\n{body_preview}")
        kw_context = "\n\n".join(kw_context_lines)

        cluster_filter = ""
        if keyword_clusters:
            cluster_filter = f"\nFOCUS ON THESE CLUSTERS: {', '.join(keyword_clusters)}"

        prompt = f"""Detect keyword cannibalization in the following SEO data:

{kw_context}
{cluster_filter}

Analyze for:
1. Multiple pages targeting the same primary keyword
2. Overlapping secondary keyword sets
3. Same-intent pages competing for the same queries
4. Content briefs that would create near-duplicate pages
5. Geographic keyword overlap (same keyword in overlapping regions)

Return structured JSON:
{{
  "cannibalization_found": <bool>,
  "risk_level": "none|low|medium|high|critical",
  "conflicts": [
    {{
      "keyword": "<overlapping keyword>",
      "competing_items": ["<draft titles or page types>"],
      "overlap_type": "exact_keyword|intent_overlap|geographic_overlap",
      "severity": "critical|warning|info",
      "recommended_resolution": "<specific fix>"
    }}
  ],
  "summary": "<overview of findings>",
  "prevention_recommendations": ["<rules to prevent future cannibalization>"]
}}
"""

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.3,
            max_tokens=4096,
        )

        content = _strip_code_fence(response.content)

        try:
            analysis = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            analysis = {"raw_analysis": content}

        logger.info(
            "seo_cannibalization_check_completed",
            workspace_id=workspace_id,
            drafts_analyzed=len(keyword_drafts),
        )

        # Return analysis directly — no draft saved
        return {
            "status": "completed",
            "analysis": analysis,
            "drafts_analyzed": len(keyword_drafts),
            "workspace_id": workspace_id,
        }

    # ── Spec tools ───────────────────────────────────────────────────────

    async def _create_keyword_tracker_spec(
        self,
        workspace_id: str,
        tracker_type: str = "keyword_ranking",
        keyword_clusters: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Produce a structured spec for a keyword tracking spreadsheet."""
        # Pull existing keyword architecture for pre-population
        all_drafts = await self._drafts.list_by_workspace(workspace_id, limit=20)
        kw_drafts = [d for d in all_drafts if d.content_type == "seo_keyword_architecture"]

        kw_data = ""
        if kw_drafts:
            latest = kw_drafts[0]
            kw_data = f"\nEXISTING KEYWORD ARCHITECTURE:\n{(latest.body or '')[:3000]}"

        cluster_text = ""
        if keyword_clusters:
            cluster_text = f"\nFOCUS CLUSTERS: {', '.join(keyword_clusters)}"

        prompt = f"""Create a spreadsheet specification for a {tracker_type} tracker.

WORKSPACE: {workspace_id}
{kw_data}
{cluster_text}

Return structured JSON with:

{{
  "sheet_type": "{tracker_type}",
  "sheet_title": "<title for the Google Sheet>",
  "columns": [
    {{
      "name": "<column header>",
      "width": <pixels>,
      "format": "text|number|percentage|date"
    }}
  ],
  "rows": [
    {{
      "data": ["<pre-populated values from keyword architecture>"]
    }}
  ],
  "formulas": {{
    "<column_name>": "<formula template using row references>"
  }},
  "conditional_formatting": [
    {{
      "column": "<name>",
      "rule": "<condition>",
      "format": "<color or style>"
    }}
  ],
  "frozen_rows": 1,
  "notes": "<instructions for the sheets agent>"
}}

Include columns appropriate for the tracker type:
- keyword_ranking: Keyword, Cluster, Intent, Volume, Target URL, Current Rank, Previous Rank, Change, Impressions, Clicks, CTR, Featured Snippet
- content_performance: URL, Title, Page Type, Target Keyword, Impressions, Clicks, CTR, Avg Position, Bounce Rate
- audit_tracker: URL, Status, Title Length, Meta Desc, H1, Schema, Internal Links, Canonical, Issues

Pre-populate rows from keyword architecture data when available.
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_tracker_spec_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, "", hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            spec = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            spec = {"raw_spec": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_tracker_spec",
            title=f"Keyword Tracker Spec: {tracker_type}",
            body=json.dumps(spec, indent=2) if isinstance(spec, dict) else content,
            verify_flags=verify_flags,
        )

        logger.info(
            "seo_tracker_spec_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            tracker_type=tracker_type,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "tracker_spec": spec,
            "tracker_type": tracker_type,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
            "note": "Pass this spec to sheets_agent for Google Sheets creation.",
        }

    async def _create_monitoring_workflow_spec(
        self,
        workspace_id: str,
        monitoring_type: str,
        alert_conditions: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Produce a workflow spec for automated SEO monitoring."""
        alert_text = ""
        if alert_conditions:
            alert_text = f"\nALERT CONDITIONS: {', '.join(alert_conditions)}"

        prompt = f"""Create an n8n workflow specification for SEO monitoring.

WORKSPACE: {workspace_id}
MONITORING TYPE: {monitoring_type}
{alert_text}

Return structured JSON with:

{{
  "workflow_name": "<descriptive name>",
  "monitoring_type": "{monitoring_type}",
  "trigger": {{
    "type": "schedule|webhook",
    "schedule": "<cron expression if scheduled>",
    "description": "<when this runs>"
  }},
  "data_sources": [
    {{
      "name": "<source name>",
      "type": "api|rss|webhook|database",
      "endpoint": "<URL or description>",
      "authentication": "<type needed>"
    }}
  ],
  "processing_steps": [
    {{
      "step": <int>,
      "action": "<what to do>",
      "node_type": "<suggested n8n node>",
      "configuration_notes": "<setup guidance>"
    }}
  ],
  "alert_conditions": [
    {{
      "condition": "<when to alert>",
      "severity": "critical|warning|info",
      "notification_channel": "slack|email|webhook",
      "message_template": "<alert message format>"
    }}
  ],
  "output": {{
    "format": "<json|csv|slack_message>",
    "destination": "<where results go>"
  }}
}}

Common monitoring types:
- rank_tracking: Daily keyword position checks
- crawl_health: Sitemap monitoring, error detection
- competitor_content: New competitor page detection
- indexing_verification: New page indexing confirmation
- traffic_anomaly: Sudden organic traffic drops
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_workflow_spec_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, "", hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            spec = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            spec = {"raw_spec": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_workflow_spec",
            title=f"SEO Monitoring Spec: {monitoring_type}",
            body=json.dumps(spec, indent=2) if isinstance(spec, dict) else content,
            verify_flags=verify_flags,
        )

        logger.info(
            "seo_workflow_spec_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            monitoring_type=monitoring_type,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "workflow_spec": spec,
            "monitoring_type": monitoring_type,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
            "note": "Pass this spec to workflow_builder_agent for n8n workflow creation.",
        }

    async def _sync_workspace_keywords(self, workspace_id: str) -> dict[str, Any]:
        """Sync workspace keyword list from latest keyword architecture. Pure data — no LLM."""
        # Find latest keyword architecture
        all_drafts = await self._drafts.list_by_workspace(workspace_id, limit=20)
        kw_drafts = [d for d in all_drafts if d.content_type == "seo_keyword_architecture"]

        if not kw_drafts:
            return {
                "status": "no_architecture",
                "message": "No keyword architecture found. Run create_keyword_architecture first.",
                "workspace_id": workspace_id,
            }

        latest = kw_drafts[0]
        try:
            architecture = json.loads(latest.body or "{}")
        except (json.JSONDecodeError, TypeError):
            return {
                "status": "parse_error",
                "message": "Could not parse keyword architecture.",
                "workspace_id": workspace_id,
            }

        # Extract primary keywords from clusters
        clusters = architecture.get("clusters", [])
        new_keywords = []
        for cluster in clusters:
            if isinstance(cluster, dict):
                pk = cluster.get("primary_keyword", "")
                if pk:
                    new_keywords.append(pk)

        if not new_keywords:
            return {
                "status": "no_keywords",
                "message": "No primary keywords found in architecture.",
                "workspace_id": workspace_id,
            }

        # Get existing keywords for diff
        existing = await self._workspace_mgr.get_keywords(workspace_id)
        existing_set = set(existing)
        new_set = set(new_keywords)

        added = new_set - existing_set
        merged = sorted(existing_set | new_set)

        # Update workspace keywords
        await self._workspace_mgr.set_keywords(workspace_id, merged)

        logger.info(
            "seo_workspace_keywords_synced",
            workspace_id=workspace_id,
            added=len(added),
            removed=0,  # We merge, not replace
            total=len(merged),
        )

        return {
            "status": "synced",
            "keywords_added": sorted(added),
            "total_keywords": len(merged),
            "workspace_id": workspace_id,
            "note": "Research Agent RSS scoring will now use these keywords.",
        }

    # ── AI crawler spec ──────────────────────────────────────────────────

    async def _create_ai_crawler_spec(
        self,
        workspace_id: str,
        site_url: str = "",
        crawl_strategy: str = "selective_allow",
    ) -> dict[str, Any]:
        """Generate AI crawler directive specification."""
        brand_voice, reference_docs = await self._get_workspace_context(workspace_id)
        context_section = self._format_context_section(brand_voice, reference_docs)

        site_text = ""
        if site_url:
            site_text = f"\nSITE URL: {site_url}"

        prompt = f"""Create an AI crawler directive specification for workspace: {workspace_id}
{site_text}
CRAWL STRATEGY: {crawl_strategy}
(allow_all = let all AI bots crawl freely, selective_allow = allow crawling but block training where possible, block_training_only = allow search indexing but block model training)

{context_section}

Return structured JSON with EXACTLY this schema:

{{
  "crawl_strategy": "{crawl_strategy}",
  "robots_txt_directives": {{
    "per_bot_rules": [
      {{
        "bot": "<user-agent name, e.g., GPTBot>",
        "operator": "<OpenAI|Anthropic|Perplexity|Google|Microsoft|Apple>",
        "action": "allow|block|conditional",
        "rules": ["<Disallow or Allow directives>"],
        "rationale": "<business reason for this decision>"
      }}
    ],
    "ready_to_paste_block": "<complete robots.txt block with all AI bot directives, ready to append to existing robots.txt>"
  }},
  "meta_tag_recommendations": [
    {{
      "tag": "<meta tag name>",
      "content": "<meta tag content value>",
      "purpose": "<what this controls>",
      "html_example": "<complete <meta> tag ready to paste into <head>>"
    }}
  ],
  "http_header_recommendations": [
    {{
      "header": "<HTTP header name, e.g., X-Robots-Tag>",
      "value": "<header value>",
      "purpose": "<what this controls>",
      "implementation_note": "<where to set this — server config, CDN, middleware>"
    }}
  ],
  "per_bot_strategy": [
    {{
      "bot": "<bot name>",
      "operator": "<company>",
      "crawl_allowed": <bool>,
      "training_allowed": <bool>,
      "search_indexing_allowed": <bool>,
      "rationale": "<business justification>"
    }}
  ],
  "implementation_checklist": [
    {{
      "step": <int>,
      "action": "<what to do>",
      "file_or_location": "<where to make the change>",
      "priority": "critical|high|medium",
      "notes": "<additional guidance>"
    }}
  ]
}}

RULES:
- robots_txt ready_to_paste_block must be a complete, valid robots.txt fragment
- Meta tag HTML examples must be complete tags ready for copy-paste
- Per-bot strategy must cover all 7 major AI bots (GPTBot, ChatGPT-User, ClaudeBot, PerplexityBot, Google-Extended, Bingbot, Applebot-Extended)
- Implementation checklist must be ordered by priority
- Rationale must explain the business trade-off for each bot decision
- Flag any uncertain recommendations with [VERIFY]
"""

        config = RefinementConfig(
            criteria=_SEO_AEO_CRITERIA,
            max_iterations=2,
            quality_threshold=7.0,
            log_prefix="seo_ai_crawler_refinement",
        )
        hooks = build_hook_chain(make_em_dash_hook())
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)

        content = _strip_code_fence(result.content)
        verify_flags = _extract_verify_flags(content)

        try:
            spec = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            spec = {"raw_spec": content}

        draft = await self._drafts.create(
            workspace_id=workspace_id,
            content_type="seo_ai_crawler_spec",
            title=f"AI Crawler Spec: {workspace_id} ({crawl_strategy})",
            body=json.dumps(spec, indent=2) if isinstance(spec, dict) else content,
            verify_flags=verify_flags,
        )

        logger.info(
            "seo_ai_crawler_spec_created",
            workspace_id=workspace_id,
            draft_id=draft.id,
            crawl_strategy=crawl_strategy,
        )

        return {
            "status": "created",
            "draft_id": draft.id,
            "ai_crawler_spec": spec,
            "crawl_strategy": crawl_strategy,
            "verify_flags": verify_flags,
            "workspace_id": workspace_id,
        }

    # ── Roadmap tracker ──────────────────────────────────────────────────

    async def _get_seo_roadmap_status(self, workspace_id: str) -> dict[str, Any]:
        """Get current SEO roadmap phase and milestones. No LLM call."""
        raw = await self._config.get(workspace_id, "seo_roadmap_status")
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
                "milestones_completed": [],
                "milestones_pending": [],
                "history": [],
                "note": (
                    "No SEO roadmap initiated. Use update_seo_roadmap to begin. "
                    "Typical phases: foundation → architecture → content_buildout → "
                    "optimization → scaling"
                ),
            }

        return {
            "current_phase": status.get("current_phase", "not_started"),
            "milestones_completed": status.get("milestones_completed", []),
            "milestones_pending": status.get("milestones_pending", []),
            "phase_started_at": status.get("phase_started_at", ""),
            "last_updated": status.get("last_updated", ""),
            "history": status.get("history", []),
            "workspace_id": workspace_id,
        }

    async def _update_seo_roadmap(
        self,
        workspace_id: str,
        phase: str,
        milestones_completed: list[str],
        milestones_pending: Optional[List[str]] = None,
        notes: str = "",
    ) -> dict[str, Any]:
        """Update SEO roadmap phase and milestones. No LLM call."""
        from datetime import datetime

        valid_phases = [
            "foundation",
            "architecture",
            "content_buildout",
            "optimization",
            "scaling",
        ]
        if phase not in valid_phases:
            return {
                "status": "error",
                "message": f"Invalid phase '{phase}'. Valid: {valid_phases}",
            }

        # Load existing status
        raw = await self._config.get(workspace_id, "seo_roadmap_status")
        if raw:
            try:
                status = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                status = {"history": []}
        else:
            status = {"history": []}

        old_phase = status.get("current_phase", "not_started")
        now = datetime.utcnow().isoformat()

        # Record transition
        if old_phase != phase:
            status.setdefault("history", []).append(
                {
                    "from_phase": old_phase,
                    "to_phase": phase,
                    "transitioned_at": now,
                    "milestones_completed": milestones_completed,
                    "notes": notes,
                }
            )

        status["current_phase"] = phase
        status["phase_started_at"] = now
        status["milestones_completed"] = milestones_completed
        status["milestones_pending"] = milestones_pending or []
        status["last_updated"] = now

        await self._config.set(workspace_id, "seo_roadmap_status", json.dumps(status))

        logger.info(
            "seo_roadmap_updated",
            workspace_id=workspace_id,
            old_phase=old_phase,
            new_phase=phase,
            milestones=len(milestones_completed),
        )

        result: dict[str, Any] = {
            "status": "updated",
            "previous_phase": old_phase,
            "current_phase": phase,
            "milestones_completed": milestones_completed,
            "milestones_pending": milestones_pending or [],
            "workspace_id": workspace_id,
        }
        if notes:
            result["notes"] = notes

        return result
