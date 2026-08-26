"""Compact agent catalog for the lightweight router."""

from __future__ import annotations

from typing import Dict, List, Optional, Set

# One-line agent descriptions for the router prompt (~40 chars each).
# Keep these SHORT — the router only needs enough to classify intent.
AGENT_CATALOG: Dict[str, str] = {
    "research_agent": "RSS feeds, fraud monitoring, web research",
    "reddit_ingest_agent": "Reddit subreddit monitoring, leads",
    "google_alerts_agent": "Gmail Google Alert email scanning",
    "writer_agent": "Content writing, brand voice",
    "create_visual": "Any static visual — diagrams, photos, infographics, illustrations",
    "video_agent": "Video scripts, AI video generation",
    "deck_agent": "Google Slides presentations, decks",
    "docs_agent": "Google Docs reports, briefs, proposals",
    "sheets_agent": "Google Sheets trackers, budgets",
    "motion_graphics_agent": "Remotion animations, data viz",
    "performance_marketer_agent": "Paid ads, A/B tests, budgets",
    "social_media_agent": "Content calendars, platform strategy",
    "lifecycle_marketing_agent": "Email/SMS/push flows, segments",
    "growth_ideas_agent": "Daily growth ideas, scoring",
    "marketing_analytics_agent": "GA4, UTM, attribution, tracking",
    "acquisition_agent": "Funnel architecture, landing pages, friction",
    "conversion_optimization_agent": "On-site experiments, A/B tests, CRO",
    "compliance_agent": "FINRA/SEC/TCPA/GDPR compliance review",
    "legal_strategy_agent": "Contracts, NDAs, risk flagging",
    "telesales_agent": "Call scripts, dialing, voice AI, QA",
    "sales_ops_agent": "CRM pipelines, lead scoring, automation",
    "linkedin_partnerships_agent": "LinkedIn prospecting, outreach",
    "workflow_healer_agent": "Diagnose/repair broken n8n workflows",
    "workflow_builder_agent": "Build new n8n workflows from scratch",
    "knowledge_base_agent": "Memory storage, fact recall, decisions",
    "editorial_agent": "Editorial calendars, content backlog, bundles",
    "experiment_engineer_agent": "Experiments, A/B tests, event schemas",
    "gtm_agent": "GTM strategy, product launch, ICP, channel strategy",
    "seo_aeo_agent": "SEO, AEO, keywords, schema, linking, organic",
    "ux_ui_design_agent": "UX audits, design systems, component specs, accessibility",
}

# Management tools that don't require agent delegation
MANAGEMENT_TOOLS: List[str] = [
    "list_workflows",
    "get_workflow",
    "execute_workflow",
    "activate_workflow",
    "deactivate_workflow",
    "create_workflow",
    "list_opportunities",
    "list_drafts",
    "approve_draft",
    "reject_draft",
    "list_workspaces",
    "get_workspace_config",
    "add_source",
    "remove_source",
    "list_media",
    "get_draft_media",
    "health_check",
]

# Which management tools each agent might need alongside its delegation
AGENT_TOOL_GROUPS: Dict[str, List[str]] = {
    "workflow_builder_agent": [
        "list_workflows",
        "get_workflow",
        "create_workflow",
        "activate_workflow",
        "execute_workflow",
    ],
    "workflow_healer_agent": [
        "list_workflows",
        "get_workflow",
        "execute_workflow",
        "activate_workflow",
        "deactivate_workflow",
    ],
    "research_agent": ["list_opportunities"],
    "reddit_ingest_agent": ["list_opportunities"],
    "google_alerts_agent": ["list_opportunities"],
    "writer_agent": ["list_drafts"],
    "create_visual": ["list_media"],
    "video_agent": ["list_media"],
    "deck_agent": ["list_media"],
    "docs_agent": ["list_media"],
    "sheets_agent": ["list_media"],
    "motion_graphics_agent": ["list_media"],
    "seo_aeo_agent": ["list_drafts"],
    "conversion_optimization_agent": ["list_drafts"],
    "ux_ui_design_agent": ["list_drafts"],
}


def build_router_prompt(disabled_agents: Optional[Set[str]] = None) -> str:
    """Build the compact classification prompt for the Haiku router.

    This prompt is ~1,800 chars / ~450 tokens — much smaller than
    the full orchestrator system prompt (~16,900 chars / ~4,200 tokens).

    Agents in ``disabled_agents`` are excluded from the catalog so the
    router will never attempt to delegate to them.
    """
    excluded = disabled_agents or set()
    catalog = {k: v for k, v in AGENT_CATALOG.items() if k not in excluded}
    agent_lines = "\n".join(f"  {aid}: {desc}" for aid, desc in catalog.items())
    mgmt_lines = ", ".join(MANAGEMENT_TOOLS)

    return f"""You are a request router for the CMO Agent — an AI-powered Chief Marketing Officer running a multi-agent marketing and revenue organization.
The system spans content production, marketing strategy, sales & revenue ops, legal & compliance, and business intelligence.
Classify the user message into ONE of three actions.

AGENTS:
{agent_lines}

MANAGEMENT TOOLS: {mgmt_lines}

RULES:
1. Greetings, small talk, thanks, "ok", "hi", single words with no task intent → respond_directly
2. Requests matching an agent's domain → delegate_to_agent (pick the best agent_id)
3. Requests about workflows, opportunities, drafts, workspaces, health → use_management_tool
4. When unsure, prefer delegate_to_agent over respond_directly
5. For "what can you do?" / "help" / capability questions → respond_directly with a summary covering all five divisions: content production (writing, images, video, motion graphics, decks, docs, sheets), marketing strategy (paid ads, lifecycle email/SMS, social, analytics, CRO, growth ideas, GTM), sales & revenue (telesales, sales ops, LinkedIn partnerships), legal & compliance (regulatory review, contracts), and operations (editorial, experiments, knowledge base, n8n workflows). Never describe this as just a "marketing tool" — it is a full marketing and revenue organization.

OUTPUT FORMAT (JSON only, no other text):
{{"action": "respond_directly"|"delegate_to_agent"|"use_management_tool", "agent_id": "agent_id_or_null", "tool_ids": ["tool_name"] or [], "direct_response": "short friendly reply or null", "reasoning": "1 sentence"}}"""
