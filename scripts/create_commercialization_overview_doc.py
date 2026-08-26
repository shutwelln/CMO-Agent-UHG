#!/usr/bin/env python3
"""One-off script: Creates a Google Doc with the CMO Agent Commercialization Overview.

Covers product options, consumer interaction flows, pricing, agent profiles,
competitive positioning, and implementation roadmap.

Run:  python scripts/create_commercialization_overview_doc.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure project root is importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── Google Auth (reuse project helper) ─────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def get_services():
    """Return (docs_service, drive_service) using existing project credentials."""
    from googleapiclient.discovery import build
    from cmo_agent.google_auth import get_google_credentials

    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json")
    )
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path=sa_path,
        scopes=SCOPES,
    )
    if creds is None:
        raise RuntimeError(
            "No Google credentials found. "
            "Set GOOGLE_OAUTH_TOKEN_PATH or GOOGLE_CREDENTIALS_PATH."
        )

    docs = build("docs", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return docs, drive


# ── Inline formatting parser (from docs.py) ───────────────────────────
def parse_inline(text: str) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Parse **bold** and *italic* markers. Returns (plain_text, [(start,end,style),...])."""
    runs: List[Tuple[int, int, str]] = []
    chars: List[str] = []
    i, length = 0, len(text)
    while i < length:
        if i + 1 < length and text[i] == "*" and text[i + 1] == "*":
            end = text.find("**", i + 2)
            if end != -1:
                s = len(chars)
                inner = text[i + 2 : end]
                chars.extend(inner)
                runs.append((s, s + len(inner), "bold"))
                i = end + 2
                continue
        if text[i] == "*" and (i + 1 >= length or text[i + 1] != "*"):
            end = text.find("*", i + 1)
            if end != -1:
                s = len(chars)
                inner = text[i + 1 : end]
                chars.extend(inner)
                runs.append((s, s + len(inner), "italic"))
                i = end + 1
                continue
        chars.append(text[i])
        i += 1
    return "".join(chars), runs


# ── Document structure ─────────────────────────────────────────────────
TITLE = "CMO Agent - Commercialization Overview"

SECTIONS: List[Dict[str, Any]] = [
    # ── Executive Summary ──────────────────────────────────────────
    {
        "heading": "Executive Summary",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "CMO Agent is an AI-powered marketing automation system with 34 specialized "
                    "agents covering content production, marketing strategy, sales operations, "
                    "legal/compliance, nonprofit development, and workflow automation. Built on "
                    "Anthropic Claude with model-per-role assignment (Haiku for scanning, Sonnet "
                    "for writing), it provides a complete marketing department that runs on your "
                    "infrastructure using your API keys."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "The system has been battle-tested across three production brands (Saverwell, "
                    "DSDN, Agent Tunnel) with 53,000+ lines of Python, 500+ tests, and 27 phases "
                    "of agent development. This document outlines the commercialization strategy: "
                    "how the product is packaged, how consumers interact with it, pricing tiers, "
                    "competitive positioning, and implementation roadmap."
                ),
            },
        ],
    },

    # ── Positioning ──────────────────────────────────────────────
    {
        "heading": "Positioning",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    '"The marketing department you install, not subscribe to."'
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "No existing product combines all three of: (1) a multi-agent orchestrator "
                    "with 34+ specialized marketing agents, (2) self-hosted deployment with zero "
                    "data leaving the user's infrastructure, and (3) end-to-end coverage from "
                    "strategy to content to compliance to workflow automation."
                ),
            },
        ],
    },
    {
        "heading": "Key Differentiators",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Differentiator", "CMO Agent", "Closest Competitor", "Gap"],
                "rows": [
                    [
                        "Agent depth (34+ specialists)",
                        "Yes",
                        "Copy.ai (15 workflow agents)",
                        "2x breadth, deeper specialization",
                    ],
                    [
                        "Self-hosted / data sovereignty",
                        "Yes",
                        "Mautic (email only)",
                        "No competitor offers full AI marketing stack self-hosted",
                    ],
                    [
                        "n8n workflow integration",
                        "Native (build + heal workflows)",
                        "None",
                        "Unique capability",
                    ],
                    [
                        "Multi-brand / multi-tenant",
                        "Built-in",
                        "Enterprise platforms ($$$)",
                        "Available at 1/10th the cost",
                    ],
                    [
                        "Content + Strategy + Ops + Compliance",
                        "All four",
                        "Most do 1-2",
                        "Only complete stack",
                    ],
                    [
                        "Operating cost",
                        "~$100-500/mo (LLM API costs)",
                        "$3K-50K/mo (SaaS or agency)",
                        "10-100x cheaper",
                    ],
                ],
            },
        ],
    },

    # ── Competitive Landscape ─────────────────────────────────────
    {
        "heading": "Competitive Landscape",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["Tier", "Players", "Price Range", "What They Sell"],
                "rows": [
                    [
                        "Hyperscaler platforms",
                        "HubSpot Breeze, Salesforce Agentforce, Adobe Marketo",
                        "$450-3,600+/mo",
                        "AI bolted onto existing CRM/MAP. Lock-in via ecosystem.",
                    ],
                    [
                        "AI content platforms",
                        "Jasper ($49-69/seat), Copy.ai ($49-3K), Writer ($18/seat)",
                        "$18-500/mo",
                        "Content generation, some workflow automation. SaaS delivery.",
                    ],
                    [
                        "Agent-native startups",
                        "MarkeTeam.ai, 11x, Artisan, Unify",
                        "Custom/early",
                        "Purpose-built agent teams. Pre-revenue or early traction.",
                    ],
                    [
                        "Open-source / self-hosted",
                        "Mautic, CrewAI/LangGraph, n8n",
                        "Free + API costs",
                        "Components, not integrated marketing stacks.",
                    ],
                    [
                        "Agencies",
                        "Traditional + AI-augmented",
                        "$3K-50K/mo",
                        "Human-delivered, slow, expensive.",
                    ],
                ],
            },
        ],
    },

    # ── Product Form Factor ──────────────────────────────────────
    {
        "heading": "Product Form Factor",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "CMO Agent uses a hybrid distribution model: self-hosted as the primary "
                    "product, with managed deployment available as a premium service. This "
                    "lets technical users run their own instance while generating higher-margin "
                    "revenue from managed deployments."
                ),
            },
        ],
    },
    {
        "heading": "Distribution Options",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Option", "How It Works", "Best For"],
                "rows": [
                    [
                        "Private GitHub repo + pip install",
                        "Users clone the repo, run 'pip install -e .', then 'cmo setup' to configure. Source code access for transparency and customization.",
                        "Technical users who want full control and customization",
                    ],
                    [
                        "Docker Compose (one command)",
                        "Users run 'docker compose up -d' to start CMO Agent + n8n. No Python setup needed. Access web UI at localhost:8000.",
                        "Users who want easy deployment without managing Python environments",
                    ],
                    [
                        "Managed VPS deployment (Enterprise)",
                        "We deploy CMO Agent on a dedicated VPS (DigitalOcean/Hetzner). Includes setup call, ongoing maintenance, and priority support.",
                        "Companies who want hands-off deployment and don't want to manage infrastructure",
                    ],
                ],
            },
        ],
    },

    # ── Consumer Interaction Flows ───────────────────────────────
    {
        "heading": "Consumer Interaction Flows",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "From first install to daily use, here is how a consumer interacts with "
                    "CMO Agent at each stage."
                ),
            },
        ],
    },
    {
        "heading": "Step 1: Installation",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "**Option A: Local Install (developers, technical marketers)**",
            },
            {
                "type": "numbered_list",
                "items": [
                    "Clone the private GitHub repo",
                    "Create a Python virtual environment and install: pip install -e .",
                    "Run the setup wizard: cmo setup",
                    "Start chatting: cmo chat",
                ],
            },
            {
                "type": "paragraph",
                "text": "**Option B: Docker (non-technical users, teams)**",
            },
            {
                "type": "numbered_list",
                "items": [
                    "Copy .env.template to .env and add your Anthropic API key",
                    "Run: docker compose up -d",
                    "Access the web UI at http://localhost:8000",
                    "Access n8n at http://localhost:5678 (optional, for workflow automation)",
                ],
            },
        ],
    },
    {
        "heading": "Step 2: Setup Wizard (cmo setup)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The interactive setup wizard walks new users through initial configuration "
                    "in about 2 minutes. It handles everything needed to start using the system."
                ),
            },
            {
                "type": "numbered_list",
                "items": [
                    "Enter your Anthropic API key (the only required key)",
                    "Create your first workspace (brand name, auto-generates workspace ID)",
                    "Choose an agent profile (full, marketing, content, or minimal)",
                    "Configure optional integrations (n8n, image generation, Slack bot)",
                    "The wizard writes .env, initializes the database, creates a brand voice template, and confirms setup is complete",
                ],
            },
        ],
    },
    {
        "heading": "Step 3: Daily Interaction Surfaces",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "CMO Agent provides three interaction surfaces. All three converge on the "
                    "same agent pipeline, so switching between them is seamless."
                ),
            },
            {
                "type": "table",
                "headers": ["Surface", "Command", "Best For", "Description"],
                "rows": [
                    [
                        "CLI Chat",
                        "cmo chat",
                        "Quick tasks, power users",
                        "Terminal-based chat with the orchestrator. Fast, keyboard-driven. Supports all agent capabilities.",
                    ],
                    [
                        "Web UI",
                        "cmo serve",
                        "Browser users, media library",
                        "Browser-based chat at localhost:8000. Includes media library viewer for generated images and videos.",
                    ],
                    [
                        "Slack Bot",
                        "cmo slack",
                        "Team collaboration",
                        "Full-featured Slack bot with Socket Mode. Team members interact via DMs or channels. Supports interactive buttons for approvals.",
                    ],
                ],
            },
        ],
    },
    {
        "heading": "Step 4: Example Conversations",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Users interact with CMO Agent through natural language. The orchestrator "
                    "decides which specialized agent(s) to invoke based on the request. "
                    "Example prompts:"
                ),
            },
            {
                "type": "bullets",
                "items": [
                    '"Write a blog post about our new product launch" - Routes to Writer Agent',
                    '"Create a content calendar for next month" - Routes to Social Media Agent',
                    '"Build a Google Doc with a marketing brief" - Routes to Docs Agent',
                    '"Design a paid ad campaign for our Black Friday sale" - Routes to Performance Marketer Agent',
                    '"Draft an NDA for our new vendor partnership" - Routes to Legal Strategy Agent',
                    '"What are our SEO priorities?" - Routes to SEO/AEO Agent',
                    '"Create a lead scoring model for our CRM" - Routes to Sales Ops Agent',
                    '"Review this email for TCPA compliance" - Routes to Compliance Agent',
                    '"Build an n8n workflow that sends a Slack alert when a form is submitted" - Routes to Workflow Builder Agent',
                    '"Generate a hero image for our landing page" - Routes to Visual Agent',
                ],
            },
        ],
    },

    # ── Agent Profiles ───────────────────────────────────────────
    {
        "heading": "Agent Profiles",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Not every user needs all 34 agents. The setup wizard offers four pre-configured "
                    "profiles that toggle agents on or off. Users can also customize which agents are "
                    "enabled by editing the DISABLED_AGENTS setting in their .env file."
                ),
            },
            {
                "type": "table",
                "headers": ["Profile", "Agents Enabled", "Best For", "What's Included"],
                "rows": [
                    [
                        "Full",
                        "All 34",
                        "Power users who want every capability",
                        "Content, strategy, sales, legal/compliance, nonprofit, workflows, analytics",
                    ],
                    [
                        "Marketing",
                        "25",
                        "Marketing teams (no nonprofit/legal)",
                        "Content production + marketing strategy + sales + workflows. Excludes DSDN-specific, compliance, and legal agents.",
                    ],
                    [
                        "Content",
                        "14",
                        "Content production teams",
                        "Writer, Visual, Video, Deck, Docs, Sheets, Motion Graphics, Social Media, Editorial, Growth Ideas, Lifecycle, Knowledge Base, Experiment Engineer, Composition Planner",
                    ],
                    [
                        "Minimal",
                        "6",
                        "Lightweight setup, core features only",
                        "Writer, Research, Docs, Sheets, Reddit Ingest, Google Alerts. Just content creation and research.",
                    ],
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "Disabled agents are not constructed at startup and consume zero resources. "
                    "Users can change their profile at any time by updating DISABLED_AGENTS in .env "
                    "and restarting."
                ),
            },
        ],
    },

    # ── Agent Divisions ──────────────────────────────────────────
    {
        "heading": "Agent Divisions (All 34 Agents)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The 34 agents are organized into six divisions. Each agent is registered as "
                    "a tool on the orchestrator, which decides when to delegate based on the "
                    "user's request."
                ),
            },
        ],
    },
    {
        "heading": "Content Production (8 agents)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Agent", "What It Does"],
                "rows": [
                    ["Writer", "Blog posts, newsletters, social posts, Reddit replies. Quality refinement with proofreading."],
                    ["Visual", "AI image generation: photography, illustrations, abstract visuals (textless)."],
                    ["Video", "Video scripts, storyboards, shot lists. AI video generation via fal.ai/Kling/Sora."],
                    ["Deck", "Google Slides presentations and pitch decks."],
                    ["Docs", "Google Docs: reports, briefs, proposals, blog posts."],
                    ["Sheets", "Google Sheets: campaign trackers, budgets, analytics dashboards."],
                    ["Motion Graphics", "Programmatic animations via Remotion: text, data viz, branded intros."],
                    ["Composition Planner", "Text-on-visual pipeline: plan, validate, render compositions using parametric templates."],
                ],
            },
        ],
    },
    {
        "heading": "Marketing Strategy (9 agents)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Agent", "What It Does"],
                "rows": [
                    ["Performance Marketer", "Paid ad strategy, campaign architecture, A/B testing, budget allocation."],
                    ["Social Media", "Content calendars, platform strategy, hashtag research, engagement planning."],
                    ["Lifecycle Marketing", "Email/SMS/push/in-product flows, segmentation, trigger logic, compliance."],
                    ["Growth Ideas", "Daily growth ideas from recent activity, impact/effort scoring, Slack digest."],
                    ["Marketing Analytics", "GA4 measurement, UTM governance, attribution modeling, tracking specs."],
                    ["Acquisition", "Micro funnel optimization, landing pages, friction analysis, drop-off diagnosis."],
                    ["Conversion Optimization", "On-site experiments, A/B tests, variant briefs, statistical validation."],
                    ["GTM Strategy", "Go-to-market strategy, ICP definition, beachhead selection, channel strategy."],
                    ["SEO/AEO Architect", "SEO/AEO/GEO strategy, keyword architecture, structured data, organic briefs."],
                ],
            },
        ],
    },
    {
        "heading": "Sales & Revenue (3 agents)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Agent", "What It Does"],
                "rows": [
                    ["Telesales", "Call center design, call scripting, dialing strategy, voice AI evaluation, QA."],
                    ["Sales Operations", "CRM pipelines, sales automation, lead scoring, partner revenue workflows."],
                    ["LinkedIn Partnerships", "LinkedIn prospecting, outreach sequences, A/B testing, CRM tracking."],
                ],
            },
        ],
    },
    {
        "heading": "Legal & Compliance (2 agents)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Agent", "What It Does"],
                "rows": [
                    ["Compliance", "Regulatory review: FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA, insurance regs."],
                    ["Legal Strategy", "Contract drafting, NDAs, term sheets, risk flagging, negotiation strategy."],
                ],
            },
        ],
    },
    {
        "heading": "Nonprofit / DSDN (7 agents)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "These agents are purpose-built for the Down Syndrome Diagnosis Network (DSDN) "
                    "but can be adapted for other nonprofits. Disabled by default in Marketing, "
                    "Content, and Minimal profiles."
                ),
            },
            {
                "type": "table",
                "headers": ["Agent", "What It Does"],
                "rows": [
                    ["DSDN Ideas", "Mission-specific daily ideas with 4-dimension scoring."],
                    ["Grant Intelligence", "Grant discovery, eligibility assessment, win probability scoring."],
                    ["Grant Writing", "Grant proposal drafting: narratives, budget narratives, evaluation plans."],
                    ["Corporate Sponsorship", "Sponsor targeting, tier design, outreach, impact/ROI modeling."],
                    ["Ecosystem Intelligence", "Org landscape scanning, service gap analysis, partnership fit scoring."],
                    ["Outreach Scanner", "Reddit/forum scanning for families, draft replies, team workflow."],
                    ["DSDN TikTok", "TikTok trends, content packages, series, media catalog."],
                ],
            },
        ],
    },
    {
        "heading": "Operations & Intelligence (5 agents)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Agent", "What It Does"],
                "rows": [
                    ["Research", "RSS feeds, fraud monitoring, opportunity scoring."],
                    ["Knowledge Base", "Durable cross-session memory, keyword search, fact recall."],
                    ["Experiment Engineer", "Experiment lifecycle, hypothesis-driven design, event schemas."],
                    ["Editorial Lead", "Editorial calendars, content backlog, publish checklists."],
                    ["Workflow Builder", "Build new n8n workflows from natural language."],
                ],
            },
        ],
    },

    # ── Multi-Tenant Workspace System ────────────────────────────
    {
        "heading": "Multi-Tenant Workspace System",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "CMO Agent supports multiple brands and projects simultaneously. Each "
                    "workspace is isolated with its own brand voice, monitoring sources, "
                    "configuration, content drafts, and Slack channels. Adding a new brand "
                    "requires zero code changes."
                ),
            },
            {
                "type": "paragraph",
                "text": "**What each workspace gets:**",
            },
            {
                "type": "bullets",
                "items": [
                    "A brand voice file (text file defining tone, audience, vocabulary, and guardrails)",
                    "Monitoring sources (RSS feeds, subreddits, Google Alerts)",
                    "Per-workspace configuration (keywords, score thresholds, settings)",
                    "Isolated content drafts and opportunities",
                    "Dedicated Slack notification channels",
                    "Per-workspace knowledge base (durable memory)",
                ],
            },
            {
                "type": "paragraph",
                "text": "**How to add a workspace:**",
            },
            {
                "type": "numbered_list",
                "items": [
                    'Ask the agent: "Create a new workspace called Acme Corp with the ID acme"',
                    "Drop a brand voice file at data/brand_voices/acme.txt",
                    "The agent handles database creation, source setup, and configuration",
                ],
            },
        ],
    },

    # ── Brand Voice System ───────────────────────────────────────
    {
        "heading": "Brand Voice System",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Every workspace uses a brand voice file that tells the Writer Agent (and "
                    "other content-producing agents) how to write for that brand. This is how "
                    "CMO Agent maintains consistent brand voice across all content."
                ),
            },
            {
                "type": "paragraph",
                "text": "**What a brand voice file contains:**",
            },
            {
                "type": "bullets",
                "items": [
                    "Brand name, tagline, and mission statement",
                    "Tone and personality descriptors (e.g., 'warm and conversational' vs 'authoritative and technical')",
                    "Target audience description",
                    "Preferred vocabulary and words to avoid",
                    "Formatting preferences (bullet styles, heading conventions, emoji usage)",
                    "Content guardrails (disclaimers, legal requirements, fact-checking rules)",
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "A template brand voice file is included. Users edit it with their brand's "
                    "specifics during setup."
                ),
            },
        ],
    },

    # ── Pricing ──────────────────────────────────────────────────
    {
        "heading": "Pricing Tiers",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Three tiers designed around the solo-operator constraint: low support "
                    "overhead, high leverage, near-zero COGS (users bring their own API keys)."
                ),
            },
            {
                "type": "table",
                "headers": [" ", "Starter", "Team", "Enterprise"],
                "rows": [
                    ["Monthly price", "$149/mo", "$349/mo", "$799/mo"],
                    ["Annual price", "$1,490/yr (save 17%)", "$3,490/yr (save 17%)", "$7,990/yr (save 17%)"],
                    ["All 34 agents", "Yes", "Yes", "Yes"],
                    ["CLI + Web UI", "Yes", "Yes", "Yes"],
                    ["Workspaces", "1", "Unlimited", "Unlimited"],
                    ["Slack bot", "No", "Yes", "Yes"],
                    ["Multi-brand support", "No", "Yes", "Yes"],
                    ["Support", "Community (Discord/GitHub)", "Priority email (48h SLA)", "Dedicated Slack channel"],
                    ["Updates", "Monthly", "Weekly", "Same-day"],
                    ["Managed deployment", "No", "No", "Yes (VPS included)"],
                    ["Onboarding", "Self-serve docs", "Self-serve docs", "White-glove (2h setup call)"],
                    ["Custom agents", "No", "No", "2 per quarter"],
                ],
            },
        ],
    },
    {
        "heading": "Pricing Rationale",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "Starter at $149/mo is 3x Jasper Creator ($49), but delivers 34 agents vs. 1 content tool. Positioned as 'replace your AI content tool stack' (users typically pay $50-200/mo across 3-4 tools).",
                    "Team at $349/mo is below Copy.ai Scale ($3K/mo) and HubSpot Pro ($450/mo). Positioned as 'agency-quality output without the agency.'",
                    "Enterprise at $799/mo is a fraction of managed service alternatives ($3K-15K/mo agency). Capped at 10-15 Enterprise customers to manage support load.",
                    "Annual discount of ~17% (2 months free) incentivizes commitment and improves cash flow.",
                ],
            },
        ],
    },
    {
        "heading": "What Users Pay Beyond the Subscription",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "CMO Agent has near-zero COGS because users bring their own API keys. "
                    "The subscription covers software access and updates. Users separately pay:"
                ),
            },
            {
                "type": "table",
                "headers": ["Cost", "Typical Monthly Range", "Notes"],
                "rows": [
                    ["Anthropic API (required)", "$50-200", "Haiku for scanning (~$0.25/1M tokens), Sonnet for writing (~$3/1M tokens)"],
                    ["Image generation (optional)", "$5-30", "Gemini recommended (~$0.04/image). DALL-E, SDXL also supported."],
                    ["Video generation (optional)", "$10-50", "Via fal.ai. Only if using Video Agent."],
                    ["n8n (optional)", "Free-$24", "Self-hosted free. n8n Cloud from $24/mo."],
                    ["VPS hosting (if self-hosted)", "$12-48", "DigitalOcean droplet. Not needed for local/Docker."],
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "Typical all-in cost: $200-500/mo for a light-to-moderate user (subscription + API keys). "
                    "This replaces $3K-50K/mo in agency spend or $200-1,000/mo across multiple AI tools."
                ),
            },
        ],
    },

    # ── Revenue Projections ──────────────────────────────────────
    {
        "heading": "Revenue Projections (Year 1)",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["Scenario", "Starter", "Team", "Enterprise", "Monthly Revenue", "Annual Revenue"],
                "rows": [
                    ["Conservative", "15", "8", "3", "$5,422", "$65,060"],
                    ["Moderate", "25", "15", "5", "$12,970", "$155,640"],
                    ["Optimistic", "40", "25", "10", "$22,710", "$272,520"],
                ],
            },
        ],
    },
    {
        "heading": "Unit Economics",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Metric", "Value"],
                "rows": [
                    ["COGS per customer", "~$0 (users bring own API keys)"],
                    ["Gross margin", "~95%+"],
                    ["CAC target", "<$500"],
                    ["LTV (Starter, 12mo)", "$1,788"],
                    ["LTV (Team, 18mo)", "$6,282"],
                    ["LTV (Enterprise, 24mo)", "$19,176"],
                    ["LTV:CAC ratio", "3.5:1 to 38:1"],
                    ["Break-even", "~5 Starter + 2 Team customers"],
                ],
            },
        ],
    },

    # ── Additional Revenue Streams ───────────────────────────────
    {
        "heading": "Additional Revenue Streams",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Stream", "Description", "Pricing", "When"],
                "rows": [
                    ["Custom agent development", "Build bespoke agents for specific industries/workflows", "$2,000-5,000 per agent", "Post-launch"],
                    ["Onboarding consulting", "Setup + strategy session for non-Enterprise users", "$500 one-time", "Launch"],
                    ["Industry templates", "Pre-built workspace configs for SaaS, ecommerce, nonprofit, fintech", "$49-149 per template", "Post-launch"],
                    ["OpenClaw Lite", "Lightweight version (8 skills, no orchestrator)", "$49/mo", "Phase 2"],
                ],
            },
        ],
    },

    # ── Ideal Customer Profile ───────────────────────────────────
    {
        "heading": "Ideal Customer Profile (ICP)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Growth-stage startups (Series A-B, 10-50 employees) with 1-3 person "
                    "marketing teams who currently cobble together 4-6 AI tools and feel the "
                    "pain of context-switching, inconsistent brand voice, and no automation."
                ),
            },
            {
                "type": "table",
                "headers": ["Dimension", "Profile"],
                "rows": [
                    ["Company size", "10-100 employees"],
                    ["Revenue", "$1M-20M ARR"],
                    ["Marketing team", "1-3 people (overwhelmed, wearing many hats)"],
                    ["Current stack", "ChatGPT/Claude + Jasper/Copy.ai + Canva + HubSpot/Mailchimp + Google Sheets"],
                    ["Pain", "Context-switching between 5+ tools, inconsistent brand voice, no automation"],
                    ["Technical ability", "Can follow a README, comfortable with Docker (or willing to pay for managed)"],
                    ["Decision maker", "Head of Marketing, VP Marketing, or founder doing marketing"],
                    ["Budget", "Currently spending $200-1,000/mo on AI tools + $0-5K/mo on agency/freelance"],
                ],
            },
        ],
    },

    # ── Go-to-Market Strategy ────────────────────────────────────
    {
        "heading": "Go-to-Market Strategy",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Product-Led Growth (PLG) with high-touch for Enterprise tier. No paid ads "
                    "initially. The product should market itself, using CMO Agent to create the "
                    "content that sells CMO Agent."
                ),
            },
        ],
    },
    {
        "heading": "Sales Motion",
        "level": 2,
        "content": [
            {
                "type": "numbered_list",
                "items": [
                    "Discovery: Prospect finds CMO Agent via content, referral, or Product Hunt",
                    "Demo: Self-serve demo video + interactive sandbox (or 15-min Loom walkthrough)",
                    "Trial: 14-day free trial (full Team tier, requires Anthropic API key)",
                    "Conversion: Automated email sequence (built by CMO Agent's Lifecycle Marketing Agent)",
                    "Onboarding: Self-serve docs (Starter/Team) or 1:1 setup call (Enterprise)",
                    "Expansion: Starter to Team (add Slack), Team to Enterprise (add managed hosting)",
                ],
            },
        ],
    },
    {
        "heading": "Channel Strategy",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Channel", "Approach", "Expected Yield"],
                "rows": [
                    ["Agent Tunnel network", "Direct outreach to founders in warm network", "5-10 beta users"],
                    ["LinkedIn content", "Weekly posts showing specific agent workflows", "Brand awareness, inbound leads"],
                    ["Product Hunt launch", "Launch Core tier, emphasize self-hosted positioning", "Traffic spike, early adopters"],
                    ["YouTube/Loom demos", "Short videos of real agent workflows", "SEO + social proof"],
                    ["Reddit / HackerNews", "Show-don't-tell posts with real outputs", "Technical early adopters"],
                    ["SEO content", "Blog posts about AI marketing automation, written by the product", "Long-tail organic traffic"],
                ],
            },
        ],
    },

    # ── Launch Sequence ──────────────────────────────────────────
    {
        "heading": "Launch Sequence",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["Phase", "Timeline", "Action"],
                "rows": [
                    ["Alpha", "Week 1-4", "3-5 users from Agent Tunnel network, free, feedback-driven"],
                    ["Beta", "Week 5-8", "10-15 users, 50% discount, structured feedback forms"],
                    ["Product Hunt launch", "Week 9", "Public launch of Starter tier"],
                    ["General availability", "Week 10+", "Full pricing, all tiers live"],
                ],
            },
        ],
    },

    # ── Technical Architecture (Consumer View) ───────────────────
    {
        "heading": "Technical Architecture (Consumer View)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "From the consumer's perspective, CMO Agent is a single system they interact "
                    "with through natural language. Behind the scenes:"
                ),
            },
            {
                "type": "numbered_list",
                "items": [
                    "User sends a message via CLI, Web UI, or Slack",
                    "The CMO Session resolves the active workspace and loads brand voice",
                    "The Orchestrator Agent (Claude Sonnet) analyzes the request and decides which specialized agent(s) to invoke",
                    "The specialized agent executes with its own tools, system prompt, and LLM model assignment",
                    "Results flow back through the orchestrator to the user",
                    "All data stays local: SQLite database, local files, user's own API keys",
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "The system supports n8n workflow automation. The Workflow Builder Agent can "
                    "design, deploy, test, and activate n8n workflows from natural language. The "
                    "Workflow Healer Agent monitors workflows and automatically diagnoses and "
                    "repairs failures."
                ),
            },
        ],
    },

    # ── Quality & Safety ─────────────────────────────────────────
    {
        "heading": "Quality & Safety Systems",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Content quality is enforced through multiple layers, ensuring consistent "
                    "brand-safe output."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "Ralph Loops refinement system: Iterative self-critique with dual-LLM architecture (Sonnet for generation, Haiku for critique). Weighted per-dimension scoring with contrarian critique prompts. Integrated into all 16 content-producing agents.",
                    "Proofreading: LLM-powered proofreader (Haiku) checks spelling, grammar, and punctuation on all generated content.",
                    "Brand voice enforcement: Every content agent loads the workspace's brand voice file and follows its tone, vocabulary, and guardrails.",
                    "Content safety checks: Automated checks for domain validation, deficit language, person-first language, PII detection, and length limits (used extensively in outreach).",
                    "Compliance Agent: Regulatory review for financial services, insurance, healthcare content (FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA).",
                    "Visual quality: Post-generation vision AI evaluation scores images against specs across 6 dimensions (subject, lighting, composition, color, mood, text absence).",
                ],
            },
        ],
    },

    # ── Implementation Status ────────────────────────────────────
    {
        "heading": "Implementation Status",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The following commercialization work has been completed and what remains."
                ),
            },
        ],
    },
    {
        "heading": "Completed (Phase 1: Fork and Clean)",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "Decoupled personal data from seed SQL (removed 3 personal workspaces, 30+ sources, personal keywords)",
                    "Neutralized config defaults (n8n URL, workspace, Slack channels)",
                    "Added DISABLED_AGENTS environment variable for conditional agent loading",
                    "Conditional agent construction in factory.py (disabled agents not instantiated)",
                    "Dynamic router catalog (excludes disabled agents from classification)",
                    "Gated FraudWatch tools behind file existence check",
                    "Created .env.template with all fields documented",
                    "Created brand voice template file",
                    "Created setup wizard (cmo setup) with 4 agent profiles",
                    "Created standalone Dockerfile and docker-compose.yml (CMO Agent + n8n)",
                    "Created user-facing documentation (Getting Started, API Keys, Agent Reference, Customization Guide)",
                    "All 425 existing tests pass with zero new failures",
                ],
            },
        ],
    },
    {
        "heading": "Remaining Work",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Phase", "Work", "Effort"],
                "rows": [
                    [
                        "Phase 0: Validate",
                        "5 problem interviews, smoke test landing page, alpha deployment to 3-5 warm contacts",
                        "2 weeks",
                    ],
                    [
                        "Phase 2: Docker + Polish",
                        "Test fresh deploy on clean Ubuntu VPS, incorporate alpha feedback",
                        "2 weeks",
                    ],
                    [
                        "Phase 3: Admin Panel",
                        "Web-based admin panel (/admin routes for credentials, workspaces, agents, integrations), password auth",
                        "2 weeks",
                    ],
                    [
                        "Phase 4: Launch",
                        "Product Hunt launch, landing page, Stripe billing, onboarding docs per tier",
                        "2 weeks",
                    ],
                    [
                        "Phase 5: Post-Launch",
                        "OpenClaw Lite tier, industry templates, one-click deploy buttons, community Discord, sync script",
                        "Ongoing",
                    ],
                ],
            },
        ],
    },

    # ── Risk Assessment ──────────────────────────────────────────
    {
        "heading": "Risk Assessment",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["Risk", "Likelihood", "Impact", "Mitigation"],
                "rows": [
                    [
                        "No one buys",
                        "Medium",
                        "High",
                        "Validate with 5 free alpha users before building anything. If they don't use it for free, they won't pay.",
                    ],
                    [
                        "Support overwhelm",
                        "Medium",
                        "High",
                        "Self-serve docs, Discord community, Enterprise-only 1:1 support. Cap Enterprise at 10-15.",
                    ],
                    [
                        "Competitor builds similar",
                        "Low (12mo)",
                        "Medium",
                        "53K lines of domain logic is a moat. Frameworks enable building agents, not marketing intelligence.",
                    ],
                    [
                        "LLM API costs scare users",
                        "Medium",
                        "Medium",
                        "Include cost calculator in docs. Typical: $50-200/mo for Haiku-heavy workloads.",
                    ],
                    [
                        "Users can't set up Docker",
                        "Medium",
                        "Medium",
                        "Managed tier exists. Also: one-click deploy templates for DigitalOcean/Railway.",
                    ],
                ],
            },
        ],
    },

    # ── Validation Before Building ───────────────────────────────
    {
        "heading": "Validation Before Building (Next Steps)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Before building the full commercial product, validate demand with these "
                    "concrete steps:"
                ),
            },
            {
                "type": "numbered_list",
                "items": [
                    "Problem interviews (5 conversations): Talk to 5 people in the Agent Tunnel network who have small marketing teams. Ask about their current tools, pain points, and budget. Do NOT pitch CMO Agent. Listen.",
                    "Smoke test landing page: Build a simple page (Framer/Carrd, 1 day) describing the product with pricing. Drive warm contacts to it. Measure: do they click 'Get Started'?",
                    "Alpha deployment (3-5 users): Deploy CMO Agent for 3-5 warm contacts for free. Observe: do they actually use it? Which agents do they use most? What breaks?",
                    "Pricing validation: Show the 3-tier pricing to alpha users. Ask 'Would you pay this?' and 'Which tier?' If >60% say yes, proceed.",
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "Gate: Only proceed to Phase 2+ if validation shows genuine demand and "
                    "willingness to pay."
                ),
            },
        ],
    },
]


# ── Build Google Doc ───────────────────────────────────────────────
def heading_style(level: int) -> str:
    return f"HEADING_{min(level, 6)}"


def _batch_update(docs_service: Any, doc_id: str, requests: List[Dict[str, Any]]) -> None:
    """Execute batchUpdate with retry on rate-limit (429) errors."""
    from googleapiclient.errors import HttpError

    for attempt in range(5):
        try:
            docs_service.documents().batchUpdate(
                documentId=doc_id, body={"requests": requests}
            ).execute()
            return
        except HttpError as e:
            if e.resp.status == 429:
                wait = 15 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s (attempt {attempt + 1}/5)...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Rate limit exceeded after 5 retries")


def build_doc(docs_service: Any, drive_service: Any) -> str:
    """Create the Google Doc, populate it, share it. Returns the URL."""

    # 1. Create empty doc
    doc = docs_service.documents().create(body={"title": TITLE}).execute()
    doc_id = doc["documentId"]
    print(f"Created document: {doc_id}")

    # 2. Build requests
    requests: List[Dict[str, Any]] = []
    cursor = 1

    for section in SECTIONS:
        h = section.get("heading", "")
        lvl = section.get("level", 1)
        blocks = section.get("content", [])

        # Insert heading
        if h:
            htxt = h + "\n"
            requests.append(
                {"insertText": {"location": {"index": cursor}, "text": htxt}}
            )
            h_start, h_end = cursor, cursor + len(htxt)
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": h_start, "endIndex": h_end},
                        "paragraphStyle": {
                            "namedStyleType": heading_style(lvl),
                            "spaceAbove": {
                                "magnitude": 14 if lvl == 1 else 10,
                                "unit": "PT",
                            },
                            "spaceBelow": {"magnitude": 4, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow",
                    }
                }
            )
            cursor = h_end

        # Content blocks
        for block in blocks:
            btype = block.get("type", "paragraph")

            if btype == "paragraph":
                text = block["text"]
                para_text = text + "\n"
                plain, runs = parse_inline(para_text)
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": plain}}
                )
                p_start, p_end = cursor, cursor + len(plain)
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {"startIndex": p_start, "endIndex": p_end},
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "spaceBelow": {"magnitude": 6, "unit": "PT"},
                            },
                            "fields": "namedStyleType,spaceBelow",
                        }
                    }
                )
                for rs, re_, style in runs:
                    abs_s, abs_e = cursor + rs, cursor + re_
                    if style == "bold":
                        requests.append(
                            {
                                "updateTextStyle": {
                                    "range": {
                                        "startIndex": abs_s,
                                        "endIndex": abs_e,
                                    },
                                    "textStyle": {"bold": True},
                                    "fields": "bold",
                                }
                            }
                        )
                    elif style == "italic":
                        requests.append(
                            {
                                "updateTextStyle": {
                                    "range": {
                                        "startIndex": abs_s,
                                        "endIndex": abs_e,
                                    },
                                    "textStyle": {"italic": True},
                                    "fields": "italic",
                                }
                            }
                        )
                cursor = p_end

            elif btype == "bullets":
                items = block["items"]
                list_start = cursor
                for item in items:
                    itxt = str(item) + "\n"
                    plain_item, item_runs = parse_inline(itxt)
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": plain_item,
                            }
                        }
                    )
                    for rs, re_, style in item_runs:
                        abs_s, abs_e = cursor + rs, cursor + re_
                        if style == "bold":
                            requests.append(
                                {
                                    "updateTextStyle": {
                                        "range": {
                                            "startIndex": abs_s,
                                            "endIndex": abs_e,
                                        },
                                        "textStyle": {"bold": True},
                                        "fields": "bold",
                                    }
                                }
                            )
                        elif style == "italic":
                            requests.append(
                                {
                                    "updateTextStyle": {
                                        "range": {
                                            "startIndex": abs_s,
                                            "endIndex": abs_e,
                                        },
                                        "textStyle": {"italic": True},
                                        "fields": "italic",
                                    }
                                }
                            )
                    cursor += len(plain_item)
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": cursor,
                            },
                            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                        }
                    }
                )

            elif btype == "numbered_list":
                items = block["items"]
                list_start = cursor
                for item in items:
                    itxt = str(item) + "\n"
                    plain_item, item_runs = parse_inline(itxt)
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": plain_item,
                            }
                        }
                    )
                    for rs, re_, style in item_runs:
                        abs_s, abs_e = cursor + rs, cursor + re_
                        if style == "bold":
                            requests.append(
                                {
                                    "updateTextStyle": {
                                        "range": {
                                            "startIndex": abs_s,
                                            "endIndex": abs_e,
                                        },
                                        "textStyle": {"bold": True},
                                        "fields": "bold",
                                    }
                                }
                            )
                        elif style == "italic":
                            requests.append(
                                {
                                    "updateTextStyle": {
                                        "range": {
                                            "startIndex": abs_s,
                                            "endIndex": abs_e,
                                        },
                                        "textStyle": {"italic": True},
                                        "fields": "italic",
                                    }
                                }
                            )
                    cursor += len(plain_item)
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": cursor,
                            },
                            "bulletPreset": "NUMBERED_DECIMAL_NESTED",
                        }
                    }
                )

            elif btype == "table":
                # Flush pending requests BEFORE inserting table
                if requests:
                    _batch_update(docs_service, doc_id, requests)
                    requests = []
                    time.sleep(1.5)
                    # Re-read to get accurate cursor
                    _ds = docs_service.documents().get(documentId=doc_id).execute()
                    _bc = _ds.get("body", {}).get("content", [])
                    if _bc:
                        cursor = _bc[-1].get("endIndex", cursor + 1) - 1

                headers = block["headers"]
                rows = block["rows"]
                num_cols = len(headers)
                num_rows = 1 + len(rows)

                # Insert table
                requests.append(
                    {
                        "insertTable": {
                            "rows": num_rows,
                            "columns": num_cols,
                            "location": {"index": cursor},
                        }
                    }
                )

                # Batch execute to materialize the table
                _batch_update(docs_service, doc_id, requests)
                requests = []
                time.sleep(1.5)

                # Re-read to get table cell indices
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                table_elem = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_elem = elem  # take the last table (just inserted)

                if table_elem:
                    table = table_elem["table"]
                    all_rows = [headers] + rows
                    cell_inserts: List[Tuple[int, str]] = []
                    for ri, row_data in enumerate(all_rows):
                        if ri >= len(table.get("tableRows", [])):
                            break
                        table_row = table["tableRows"][ri]
                        for ci, cell_val in enumerate(row_data):
                            if ci >= len(table_row.get("tableCells", [])):
                                break
                            cell = table_row["tableCells"][ci]
                            cell_content = cell.get("content", [])
                            if cell_content:
                                cell_idx = cell_content[0].get("startIndex", 0)
                                cell_inserts.append((cell_idx, str(cell_val)))

                    # Sort descending (insert from end to avoid index shifts)
                    cell_inserts.sort(key=lambda x: x[0], reverse=True)
                    # Filter out empty text (API rejects empty inserts)
                    cell_inserts = [
                        (cidx, ctext)
                        for cidx, ctext in cell_inserts
                        if ctext.strip()
                    ]
                    for cidx, ctext in cell_inserts:
                        requests.append(
                            {
                                "insertText": {
                                    "location": {"index": cidx},
                                    "text": ctext,
                                }
                            }
                        )

                    if requests:
                        _batch_update(docs_service, doc_id, requests)
                        requests = []
                        time.sleep(1.5)

                    # Bold header row
                    doc_state2 = (
                        docs_service.documents().get(documentId=doc_id).execute()
                    )
                    bold_requests = []
                    for elem2 in doc_state2.get("body", {}).get("content", []):
                        if "table" in elem2:
                            t2 = elem2["table"]
                            if len(t2.get("tableRows", [])) > 0:
                                header_row = t2["tableRows"][0]
                                for hcell in header_row.get("tableCells", []):
                                    for para in hcell.get("content", []):
                                        for el in para.get("paragraph", {}).get(
                                            "elements", []
                                        ):
                                            si = el.get("startIndex", 0)
                                            ei = el.get("endIndex", 0)
                                            if ei > si:
                                                bold_requests.append(
                                                    {
                                                        "updateTextStyle": {
                                                            "range": {
                                                                "startIndex": si,
                                                                "endIndex": ei,
                                                            },
                                                            "textStyle": {
                                                                "bold": True
                                                            },
                                                            "fields": "bold",
                                                        }
                                                    }
                                                )
                    if bold_requests:
                        _batch_update(docs_service, doc_id, bold_requests)
                        time.sleep(1.5)

                # Update cursor
                doc_state3 = (
                    docs_service.documents().get(documentId=doc_id).execute()
                )
                body_content = doc_state3.get("body", {}).get("content", [])
                if body_content:
                    last = body_content[-1]
                    cursor = last.get("endIndex", cursor + 1) - 1

    # Final batch
    if requests:
        _batch_update(docs_service, doc_id, requests)

    # 3. Share (restricted access)
    from cmo_agent.google_auth import share_file_restricted

    share_file_restricted(drive_service, doc_id)

    # 4. Move to CMO Agent folder
    try:
        from cmo_agent.google_auth import ensure_drive_folder, move_file_to_folder

        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)
    except Exception as e:
        print(f"Warning: could not move to folder: {e}")

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return url


# ── Main ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Initializing Google services...")
    docs_svc, drive_svc = get_services()

    print("Building document...")
    doc_url = build_doc(docs_svc, drive_svc)

    print(f"\nDone! Document created:")
    print(doc_url)
