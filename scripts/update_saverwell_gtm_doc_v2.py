#!/usr/bin/env python3
"""Update Saverwell Go-To-Market Strategy Google Doc — April 2026 comprehensive refresh.

Reads the existing GTM doc, converts to DOC_STRUCTURE, applies modifications
reflecting all platform improvements (lifecycle marketing, content library,
partner infrastructure, Cloudflare Worker, Reddit scanner, Claude Code CLI,
analytics), and rebuilds via DocsAgent._update_google_doc().
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cmo_agent.agents.docs import DocsAgent  # noqa: E402
from cmo_agent.config import get_settings  # noqa: E402
from cmo_agent.db.database import Database  # noqa: E402
from cmo_agent.google_auth import get_google_credentials  # noqa: E402
from cmo_agent.llm.anthropic import AnthropicLLM  # noqa: E402
from cmo_agent.workspace.manager import WorkspaceManager  # noqa: E402

DOC_ID = "16jeXB5cK1C_ZSAax4HNbhBFGhHXE_oS7zT4w7iPI7Ro"


# ═══════════════════════════════════════════════════════════════════════════
# Google Docs JSON → DOC_STRUCTURE converter (same as lifecycle script)
# ═══════════════════════════════════════════════════════════════════════════


def _extract_text(para: dict) -> str:
    """Build paragraph text with **bold** markers."""
    parts: list[str] = []
    for elem in para.get("elements", []):
        run = elem.get("textRun", {})
        t = run.get("content", "").rstrip("\n")
        ts = run.get("textStyle", {})
        if ts.get("bold") and t.strip():
            parts.append(f"**{t.strip()}**")
        else:
            parts.append(t)
    return "".join(parts).strip()


def _extract_cell_text(cell: dict) -> str:
    """Extract plain text from a table cell."""
    parts: list[str] = []
    for ci in cell.get("content", []):
        if "paragraph" in ci:
            for elem in ci["paragraph"].get("elements", []):
                parts.append(elem.get("textRun", {}).get("content", "").strip())
    return " ".join(parts).strip()


def gdoc_to_structure(doc_json: dict) -> dict:
    """Convert a Google Docs API response to DOC_STRUCTURE format."""
    body = doc_json["body"]["content"]
    sections: list[dict] = []
    current_content: list[dict] = []
    pending_bullets: list[str] = []
    toc_text_seen = False

    def flush_bullets() -> None:
        nonlocal pending_bullets
        if pending_bullets:
            current_content.append({"type": "bullets", "items": pending_bullets[:]})
            pending_bullets = []

    for element in body:
        if "paragraph" in element:
            para = element["paragraph"]
            style = para.get("paragraphStyle", {}).get(
                "namedStyleType", "NORMAL_TEXT"
            )
            bullet = para.get("bullet")
            text = _extract_text(para)

            if not text:
                continue

            if text == "Table of Contents" and not toc_text_seen:
                toc_text_seen = True
                continue

            if "HEADING" in style:
                flush_bullets()
                level = int(style.replace("HEADING_", ""))
                new_section = {"heading": text, "level": level, "content": []}
                sections.append(new_section)
                current_content = new_section["content"]
            elif bullet:
                pending_bullets.append(text)
            else:
                flush_bullets()
                current_content.append({"type": "paragraph", "text": text})

        elif "table" in element:
            flush_bullets()
            table = element["table"]
            headers: list[str] = []
            rows: list[list[str]] = []
            for i, row in enumerate(table.get("tableRows", [])):
                row_data = [
                    _extract_cell_text(cell)
                    for cell in row.get("tableCells", [])
                ]
                if i == 0:
                    headers = row_data
                else:
                    rows.append(row_data)
            current_content.append(
                {"type": "table", "headers": headers, "rows": rows}
            )

    flush_bullets()
    return {
        "title": doc_json.get("title", ""),
        "include_toc": toc_text_seen,
        "sections": sections,
    }


# ═══════════════════════════════════════════════════════════════════════════
# New sections to insert
# ═══════════════════════════════════════════════════════════════════════════

CURRENT_EXECUTION_STATUS_SECTIONS = [
    {
        "heading": "Current Execution Status (April 2026)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "This section provides a snapshot of what has been built and deployed as of April 2026. The platform has moved well beyond the original pre-launch state described in earlier versions of this document. What follows is a comprehensive accounting of operational capabilities across content, lifecycle marketing, technical infrastructure, distribution channels, and monetization readiness.",
            },
        ],
    },
    {
        "heading": "Content Library",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Category", "Count", "Status"],
                "rows": [
                    ["Medicare Guides", "11", "Published with email variants, JSON-LD, FAQ schema"],
                    ["Insurance Guides", "6", "Published (vision, dental, life, auto/home, hearing aid coverage)"],
                    ["Medical Alert Guides", "4+", "Published (systems guide, cost breakdown, fall detection, watches, Medicare coverage, no-fee)"],
                    ["Phone Plan Guides", "2+", "Published (senior carriers, bill cutting, free government, flip phones)"],
                    ["Hearing Aid Guides", "2+", "Published (OTC options, savings, Medicare coverage)"],
                    ["Finance & Retirement Guides", "8+", "Published (Social Security, tax deductions, budgeting, caregiving, financial planning)"],
                    ["Fraud/Scam Guides", "6+", "Published (grandparent scam, tech support, IRS, romance, investment, AI voice cloning)"],
                    ["Discount Hub Pages", "3", "Published (restaurants, groceries, travel)"],
                    ["Protection Articles", "29+", "Published (scams, fraud recovery, identity protection, digital security, financial safety)"],
                    ["Guide Drafts (Pipeline)", "96 total", "Drafted in JSON format, ready for publishing"],
                ],
            },
            {
                "type": "paragraph",
                "text": "**53+ guide articles are published on saverwell.com** with full SEO optimization: Article JSON-LD structured data, Twitter Cards, FAQ rendering, internal cross-linking, and category landing pages. 96 total guide drafts exist in the pipeline across all 7 content verticals. All published articles have pre-built email variants (subject, preheader, intro, CTA) for newsletter distribution. 7 category landing pages are live with filterable guide indexes.",
            },
        ],
    },
    {
        "heading": "Lifecycle Marketing System",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "The lifecycle marketing system is fully operational with **3 active Customer.io campaign journeys** and **3 n8n-powered broadcast workflows** that replaced the original fixed-drip campaigns. The subscriber journey runs autonomously from signup through ongoing dynamic engagement.",
            },
            {
                "type": "paragraph",
                "text": "**Key architecture decision**: The original plan included fixed-drip Customer.io campaigns (Expert Guide Series 13-email, Protection Drip 8-email, Medicare Guides 11-email seasonal). These were retired and replaced with n8n-orchestrated broadcast workflows that dynamically select content from the Article Library Google Sheet, apply seasonal priority boosting, and track per-subscriber deduplication. This approach is more flexible (no manual template updates when articles change), scales automatically as new articles are added, and handles seasonal content priorities dynamically.",
            },
            {
                "type": "table",
                "headers": ["Component", "Status", "Details"],
                "rows": [
                    ["Welcome Flow (5 emails)", "LIVE in Customer.io", "14-day onboarding sequence. Sets lifecycle_stage=active, welcome_flow_started=true"],
                    ["Core Foundations (6 emails)", "LIVE in Customer.io", "Weekly Tuesdays after Welcome completes. Covers 3 protection + 3 guide topics. Sets core_foundations_completed=true. Appends article slugs to articles_received_list"],
                    ["Re-Engagement (3 emails)", "LIVE in Customer.io", "Triggers on 30-day inactivity. 3 emails over 14 days + 30-day wait. Re-engaged subscribers stay active; non-responsive are sunset + suppressed. Allows re-entry"],
                    ["Personalized Broadcast Engine", "LIVE via n8n", "Tue + Thu at 10am ET. Dynamically selects from 80+ article library. Seasonal priority boosting (Medicare Oct-Mar, Fraud/Finance Jan-Apr, Fraud Nov-Dec). Per-subscriber dedup via broadcast_send_log. REPLACED the old Expert Guide Series (13-email) and Protection Drip (8-email) fixed campaigns"],
                    ["Weekly Digest", "LIVE via n8n", "Mondays 9am ET. Curated 5-7 article cards from past week + partner spotlight. Fresh content each week, no dedup needed"],
                    ["Medicare Seasonal Broadcast", "LIVE via n8n", "Wed at 10am ET, Sep 1 - Dec 7 only. Selects from Medicare vertical articles. Phase tracking: pre-AEP (Sep-Oct 14) and active-AEP (Oct 15-Dec 7, 8 weeks). REPLACED the old Medicare Guides Broadcast (11-email fixed series)"],
                    ["Charlie Saver Migration (8 emails)", "BUILT, ready to deploy", "4-segment strategy for 250K-300K contacts. A/B subject lines. Progressive suppression via n8n real-time converted_to_saverwell event"],
                ],
            },
            {
                "type": "paragraph",
                "text": "**RETIRED campaigns** (replaced by broadcast engine): Expert Guide Series (13-email fixed drip on Thursdays), Protection Drip (8-email fixed drip on Tuesdays), Medicare Guides Broadcast (11-email fixed seasonal series). All of this content now flows through the dynamic broadcast engine and Medicare seasonal workflow, which read the Article Library sheet and apply real-time dedup + seasonal boosting.",
            },
            {
                "type": "paragraph",
                "text": "**Additional behavior-triggered campaigns drafted** (5 total): Sudden Money After 55 (5 emails), Medicare Myths (4 emails), Fraud Protection Lead Magnet (3 emails), AHS Home Warranty Partner Drip (3 emails), AARP Membership Partner Drip (2 emails). All content drafted and ready for Customer.io deployment.",
            },
            {
                "type": "paragraph",
                "text": "**Subscriber journey timeline**: Days 0-14 Welcome Flow (5 emails) → Weeks 2-8 Core Foundations (6 weekly on Tuesdays) → Week 9+ enters 'Broadcast Eligible' segment → Personalized Broadcasts (Tue + Thu via n8n) + Weekly Digest (Mon via n8n) + Medicare Seasonal (Wed via n8n, Sep-Dec only). Re-Engagement activates independently whenever a subscriber goes inactive for 30 days.",
            },
        ],
    },
    {
        "heading": "n8n Workflow Infrastructure",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Workflow", "Schedule", "Function"],
                "rows": [
                    ["Broadcast Engine", "Tue + Thu, 10am ET", "Dynamic article selection from 80+ library. Seasonal priority boosting (Medicare, Fraud, Finance). Per-subscriber dedup via broadcast_send_log. REPLACES old Expert Guide Series + Protection Drip fixed campaigns"],
                    ["Weekly Digest Builder", "Mon, 9am ET", "Curated 5-7 article cards from past week + partner spotlight. Fresh content each send"],
                    ["Medicare Seasonal", "Wed, 10am ET (Sep-Dec)", "Medicare vertical articles during AEP. Phase tracking: pre-AEP (Sep-Oct 14) + active-AEP (Oct 15-Dec 7). REPLACES old Medicare Guides 11-email fixed broadcast"],
                    ["Lead Scanner", "Every 4 hours", "Reddit/forum scanning for prospective subscribers"],
                    ["Subscribe Workflow", "Webhook-triggered", "Cloudflare → Supabase → Customer.io → GA4 pipeline"],
                    ["Web Read Tracker", "Webhook-triggered", "Article/guide view tracking for broadcast optimization"],
                    ["CIO Engagement Webhook", "Event-driven", "Bidirectional Customer.io event sync (opens, clicks)"],
                    ["Personalized Digest", "Weekly", "Subscriber-level digest personalization variant"],
                ],
            },
        ],
    },
    {
        "heading": "Technical Infrastructure",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "**Cloudflare Worker (2,389 lines)**: Production SEO dynamic rendering + embeddable partner widget. Intercepts all bot traffic (Googlebot, Bingbot, LinkedIn, Facebook, Twitter) and serves pre-rendered HTML with structured data. Covers /retailer/*, /dma/*, /protect/*, /guides/*, /state/*, /sitemap.xml. Includes embeddable widget API (/widget/v1/) with discount lookup, email signup, and partner branding. Cache strategy: 1h browser, 1d edge.",
            },
            {
                "type": "paragraph",
                "text": "**Supabase Edge Functions**: Dynamic sitemap generation with 6 sub-sitemaps (index, DMA, merchants, guides, protect, states). Database views power URL generation with lastmod dates.",
            },
            {
                "type": "paragraph",
                "text": "**Supabase Migrations (7+)**: broadcast_send_log, subscriber_sends, digest_v2, article_thumbnails, national_zoom_timeout fix, web_read_tracking, email_hash_trigger. Partner promotions table with GIN indexes on all array targeting columns.",
            },
            {
                "type": "paragraph",
                "text": "**Admin Panels (Lovable, COMPLETED)**: 4 content management interfaces for Partner Promotions (6 seeded partners, targeting, commission tracking), DMA Pages (200+ metros, all built), State Pages (51 pages, all built), and Merchant Pages (1,900+ merchants, all built). All use shared components (MarkdownEditor, FaqJsonEditor, SeoFieldsSection, StatusToggle).",
            },
            {
                "type": "paragraph",
                "text": "**Claude Code CLI Integration**: Direct codebase changes via GitHub. Plan-then-build workflows spawned from Slack idea approvals. Reduces dependency on Lovable for all non-UI changes. Backend logic, scripts, data processing, n8n workflow design, email templates, and content generation all execute via Claude Code without Lovable involvement.",
            },
        ],
    },
    {
        "heading": "Partner & Affiliate Readiness",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Metric", "Count", "Status"],
                "rows": [
                    ["Merchants researched for affiliate", "170", "Compiled"],
                    ["CJ Network matches identified", "21", "Ready to apply"],
                    ["Applications submitted", "2", "AT&T ($80 CPS), Verizon ($75 CPS)"],
                    ["Applications approved", "0", "Pending review"],
                    ["Partners seeded in system", "6", "SelectQuote, ADT, Hear.com, Insurify, AHS, AARP"],
                ],
            },
            {
                "type": "paragraph",
                "text": "**Partner Promotions Infrastructure (built)**: Supabase partner_promotions table with 4 promotion types (CTA banner, comparison highlight, click-to-call, lead gen form), 5 position slots (above_fold, after_overview, after_comparison, end_of_article, sidebar), page-type targeting (guide categories/slugs, merchant categories/slugs, protection categories/slugs), time-boxed scheduling (for Medicare AEP, seasonal promos), commission tracking (CPL, CPA, CPS, recurring), GA4 event tracking (partner_promo_view, partner_promo_click), and UTM automation. Consumer-side PartnerPromotion.tsx component renders dynamically. When no active promotions match, zero visual impact.",
            },
            {
                "type": "paragraph",
                "text": "**Embeddable Partner Widget (COMPLETED)**: Cloudflare Worker serves /widget/v1/embed.js (1,100+ lines). Partners can embed discount lookup + email signup on their own sites with custom branding, colors, logos, and disclosures. Fires GA4 events for partner attribution. Subscribe triggers n8n webhook for Customer.io profile creation.",
            },
        ],
    },
    {
        "heading": "Reddit & Community Channel",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Metric", "Value"],
                "rows": [
                    ["Leads backfilled to Google Sheet", "1,689"],
                    ["Draft replies generated", "30"],
                    ["Lead scanner frequency", "Every 4 hours"],
                    ["Reply generation frequency", "Every 6 hours (score >= 20)"],
                    ["Foundation posts queued", "8"],
                    ["Target subreddits", "r/retirement, r/personalfinance, r/frugal, r/Scams + 4 more planned"],
                ],
            },
            {
                "type": "paragraph",
                "text": "Reddit posting strategy: Weeks 1-2 text-only posts (build karma), Weeks 3-4 begin commenting with 1 link post every 2 weeks (90/10 helpful/promotional ratio), ongoing 2x/week original posts + 3-5x/week comments. UTM tracking: utm_source=reddit, utm_medium=social, utm_content={post_slug}.",
            },
        ],
    },
    {
        "heading": "SEO & Discoverability",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "All 58+ guides indexed in sitemap with 6 sub-sitemaps (DMA, merchants, guides, protect, states, pages)",
                    "7 category landing pages live with filterable guide indexes",
                    "Internal linking audit complete (42+ broken links fixed)",
                    "Article JSON-LD, Twitter Cards, FAQ schema deployed on all guide pages",
                    "Bot pre-rendering via Cloudflare Worker (Googlebot, Bingbot, social crawlers)",
                    "301 redirects for old category URLs (medical-alerts → senior-products, phones → senior-products, finance → guides)",
                    "OG meta tags with hero images and savings-focused messaging",
                    "Breadcrumb schema on all content pages",
                    "Dynamic FAQ generation from discount/guide metadata",
                ],
            },
        ],
    },
    {
        "heading": "Interactive Tools (Spec Complete, Awaiting Implementation)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Tool", "Purpose", "Backend Status"],
                "rows": [
                    ["Subscription Audit Tool", "Monthly cost optimization ('Am I Overpaying?')", "Supabase benchmarks table (30 subscriptions) ready"],
                    ["Government Benefit Finder", "Benefit eligibility assessment", "Spec complete"],
                    ["Scam Detection Quiz", "Fraud protection education", "Spec complete"],
                    ["Lump Sum Decision Engine", "Social Security/windfall analysis", "Spec complete"],
                    ["Financial Triage Quiz", "Financial health assessment", "Spec complete"],
                ],
            },
        ],
    },
    {
        "heading": "Analytics Capabilities",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "UTM attribution pipeline fully operational (12 parameters, 180-day cookies, Supabase → n8n → Customer.io)",
                    "GA4 fully configured (COMPLETED): property G-YFGSQ1WTQM, GTM container GTM-PZBKHZ6C with 28 variables, 15 triggers, 16 tags, 27 custom dimensions, 3 custom metrics, 14 events, dataLayer JS helper, Measurement Protocol integration. Remaining: paste GTM snippet into Lovable <head>",
                    "Web read tracking workflow deployed (article/guide engagement → broadcast optimization)",
                    "Customer.io engagement webhook active (bidirectional open/click event sync)",
                    "Broadcast send log tracking (dedup, per-subscriber article history)",
                    "Subscriber engagement tracking (articles_received_list for personalization)",
                ],
            },
        ],
    },
]

DEVELOPMENT_VELOCITY_SECTION = [
    {
        "heading": "Development Velocity & Capabilities",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "A critical evolution in the Saverwell platform is the shift from Lovable-only development to a hybrid model with Claude Code CLI for backend and infrastructure work. This change fundamentally accelerates execution speed and reduces bottlenecks.",
            },
            {
                "type": "table",
                "headers": ["Capability", "Before (Lovable Only)", "Now (Claude Code + Lovable)"],
                "rows": [
                    ["Email templates", "Manual HTML editing", "Claude generates 67 templates programmatically"],
                    ["n8n workflow design", "Manual node configuration", "Claude designs workflow JSON, deploys via API"],
                    ["Content generation", "Manual drafting", "Claude generates 96 guide articles from structured prompts with quality refinement"],
                    ["Database migrations", "Lovable SQL editor", "Claude writes migration SQL, deploys via Supabase CLI"],
                    ["Script automation", "Not possible", "Claude writes Python scripts for batch operations (backfills, analytics, content processing)"],
                    ["SEO optimization", "Manual per-page", "Claude audits and fixes cross-site (42+ broken links in one pass)"],
                    ["Partner integration", "Manual setup", "Claude builds full partner promotion infrastructure (table + component + admin spec)"],
                    ["Google Docs/Sheets", "Manual creation", "Claude creates and updates strategy docs programmatically via Google APIs"],
                ],
            },
            {
                "type": "paragraph",
                "text": "**Impact on GTM execution**: Tasks that previously required days of manual Lovable prompting now complete in hours. The CMO Agent system provides 30+ specialized agents (content, analytics, lifecycle, SEO, compliance, legal, and more) that can be orchestrated for complex multi-step operations. When a growth idea is approved in Slack, Claude Code spawns as a subprocess for plan-then-build workflows with interactive Slack thread conversations.",
            },
            {
                "type": "paragraph",
                "text": "**Lovable remains the right tool for**: UI component development, visual design iteration, React/Tailwind frontend work, and user-facing page templates. The hybrid model uses each tool where it excels.",
            },
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# Modification functions
# ═══════════════════════════════════════════════════════════════════════════


def find_section_index(sections: list[dict], heading: str) -> int:
    """Find the index of a section by heading text (exact match)."""
    for i, s in enumerate(sections):
        if s["heading"] == heading:
            return i
    return -1


def find_section_index_partial(sections: list[dict], pattern: str) -> int:
    """Find the index of a section by partial heading match."""
    for i, s in enumerate(sections):
        if pattern in s.get("heading", ""):
            return i
    return -1


def remove_section_and_children(sections: list[dict], idx: int) -> None:
    """Remove a section and all its H2+ children."""
    end = idx + 1
    while end < len(sections) and sections[end]["level"] > sections[idx]["level"]:
        end += 1
    del sections[idx:end]


def insert_sections_at(sections: list[dict], idx: int, new_sections: list[dict]) -> int:
    """Insert new sections at idx, return new idx after insertion."""
    for i, s in enumerate(new_sections):
        sections.insert(idx + i, s)
    return idx + len(new_sections)


def apply_modifications(structure: dict) -> dict:
    """Apply all April 2026 modifications to the parsed structure."""
    sections = structure["sections"]

    # ── 1. UPDATE EXECUTIVE SUMMARY ───────────────────────────────────
    exec_idx = find_section_index(sections, "Executive Summary")
    if exec_idx >= 0:
        sections[exec_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "Saverwell is a free platform for Americans aged 60+ that combines senior discount discovery, fraud protection, and expert educational guides. The platform helps seniors find every discount they have earned, protects them from financial threats, and gives them plain-language guidance on Medicare, insurance, and other complex financial topics. As of April 2026, the platform operates with **1,900+ merchants with verified discounts**, **125,000+ store locations** across **210 Designated Market Areas (DMAs)**, **51 state pages** and **200+ DMA pages** (all built), a **29+ article protection content library** covering scams, identity theft, payment fraud, and digital security, a **96-article educational guide library** (53 published across 7 categories: Medicare, insurance, medical alerts, phones, hearing aids, finance, and fraud/scam deep-dives), a **fully operational lifecycle marketing system** (3 active Customer.io journeys, n8n-powered personalized broadcast engine, weekly digest, and Medicare seasonal workflow with 67 pre-built email templates), a **Cloudflare Worker** for SEO dynamic rendering and embeddable partner widgets, and a **partner promotions infrastructure** with 6 seeded partners ready for activation.",
            },
            {
                "type": "paragraph",
                "text": "This is no longer a pre-launch platform. The merchant inventory (1,900+ merchants, 125,000+ locations), content library (53+ published guides), page infrastructure (200+ DMA pages, 51 state pages, 1,900+ merchant pages -- all built), lifecycle marketing system, and technical infrastructure are all operational. The site is live with dynamic bot rendering for search engines and automated email sequences running from signup through ongoing n8n-powered broadcasts. The challenge has shifted from building inventory to driving traffic, activating affiliate revenue, and scaling the subscriber base.",
            },
            {
                "type": "paragraph",
                "text": "This go-to-market strategy sequences four growth engines in priority order: **organic/Search Engine Optimization (SEO)** as the primary traffic engine (targeting 60% of Year 1 traffic), **email/lifecycle** as the retention engine (now fully operational), **community/earned media** as the trust engine (Reddit lead scanner active with 1,689 leads), and **paid acquisition** as the scale engine activated only after organic unit economics are proven.",
            },
            {
                "type": "paragraph",
                "text": "The three-pillar content model (savings, protection, and education) creates a powerful content flywheel. Discount discovery drives initial visits, protection content builds trust and engagement depth, educational guides capture high-intent search traffic (Medicare keywords alone drive 100K+ monthly searches) and open new monetization channels (insurance lead gen, affiliate commissions), and the combination creates a platform seniors return to because it serves every dimension of their financial wellbeing. This triple positioning differentiates Saverwell from pure coupon aggregators, generic fraud awareness sites, and insurance-industry Medicare content written for agents rather than consumers.",
            },
            {
                "type": "paragraph",
                "text": "The monetization model layers affiliate commissions (170 merchants researched, 21 CJ network matches, 2 applications pending), dynamic partner promotions (infrastructure built with targeting, commission tracking, and GA4 events), sponsored merchant placements, and premium newsletter sponsorships. All designed to be transparent and trust-preserving for a senior audience.",
            },
            {
                "type": "paragraph",
                "text": "**A critical capability shift**: the addition of Claude Code CLI for direct GitHub code changes has fundamentally accelerated execution velocity. Backend logic, scripts, data processing, n8n workflow design, email template generation, content production, and database migrations all execute via Claude Code without Lovable involvement. Tasks that previously required days of manual Lovable prompting now complete in hours. Lovable remains the right tool for UI/frontend work, while Claude Code handles everything else.",
            },
            {
                "type": "paragraph",
                "text": "**Year 1 targets**: 100,000-250,000 monthly active users, 25,000+ email subscribers, $7,500/month revenue, and 2,000+ verified merchant partners (currently at 1,900+). The strategy is designed for capital efficiency. The legacy Charlie Saver email list (250K-300K contacts) provides a significant subscriber acquisition opportunity via the 8-email migration campaign with 4-segment progressive suppression strategy.",
            },
        ]

    # ── 2. UPDATE CURRENT INFRASTRUCTURE STATUS TABLE ─────────────────
    infra_idx = find_section_index(sections, "Current Infrastructure Status")
    if infra_idx >= 0:
        sections[infra_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "The platform has significant infrastructure already operational. This section captures the current state as of April 2026.",
            },
            {
                "type": "table",
                "headers": ["Component", "Status", "Details"],
                "rows": [
                    [
                        "Supabase Database",
                        "Live",
                        "1,900+ merchants, 125,000+ store locations, 96 guide articles (53 published), 29+ protection articles, 7 guide categories, partner_promotions table, broadcast_send_log, subscriber_sends, web_read_tracking, email_hash_trigger. 7+ production migrations deployed.",
                    ],
                    [
                        "n8n Automation",
                        "Live (8 workflows)",
                        "Personalized Broadcast Engine (Tue+Thu 10am ET), Weekly Digest (Mon 9am ET), Medicare Seasonal (Wed 10am ET, Sep-Dec), Lead Scanner (every 4h), Subscribe Workflow (webhook), Web Read Tracker (webhook), CIO Engagement Webhook (event-driven), Personalized Digest (weekly). All n8n workflows replaced the old fixed-drip Customer.io campaigns (Expert Guide Series, Protection Drip, Medicare Guides) with dynamic, article-library-driven broadcasts.",
                    ],
                    [
                        "Customer.io",
                        "Fully Operational",
                        "3 active campaign journeys: Welcome (5-email, 14 days), Core Foundations (6-email, weekly Tuesdays), Re-Engagement (3-email, 30-day inactivity trigger). Subscription Center with 5 topics. Broadcast templates for n8n-triggered sends (Guide Broadcast, Weekly Digest, Medicare Seasonal). Old fixed-drip campaigns (Expert Guide 13-email, Protection Drip 8-email, Medicare Guides 11-email) retired and replaced by n8n broadcast engine.",
                    ],
                    [
                        "Cloudflare Worker",
                        "Live (Production)",
                        "2,389-line SEO dynamic rendering for all bot traffic (Googlebot, Bingbot, social crawlers). Embeddable partner widget API (/widget/v1/). Serves /retailer/*, /dma/*, /protect/*, /guides/*, /state/*. Cache: 1h browser, 1d edge.",
                    ],
                    [
                        "Sitemap Edge Function",
                        "Live",
                        "Dynamic sitemap generation with 6 sub-sitemaps (index, DMA, merchants, guides, protect, states). Database-driven with lastmod dates.",
                    ],
                    [
                        "Partner Promotions",
                        "Infrastructure Built",
                        "Supabase table + consumer component + admin spec. 6 partners seeded (SelectQuote, ADT, Hear.com, Insurify, AHS, AARP). 4 promo types, 5 positions, page-type targeting, GA4 tracking. Awaiting affiliate approvals for activation.",
                    ],
                    [
                        "GA4 / GTM",
                        "CONFIGURED (COMPLETED)",
                        "GA4 property created (G-YFGSQ1WTQM). GTM container built (GTM-PZBKHZ6C) with 28 variables, 15 triggers, 16 tags. 27 custom dimensions + 3 custom metrics registered. 14 events defined (13 client-side + 1 server-side). DataLayer helper JS implemented (331 lines). Cloudflare Worker serves dataLayer script + sends Measurement Protocol beacons. Key events: email_signup ($1.20 value), affiliate_click ($0.25 value). Remaining: paste GTM snippet into Lovable frontend <head>.",
                    ],
                    [
                        "UTM Attribution",
                        "Live",
                        "12-parameter system (5 standard UTM + 7 custom). 180-day cookie persistence, form pre-population, full payload to Supabase edge function → n8n webhook → Customer.io. Operational since launch.",
                    ],
                    [
                        "Site (Lovable + Cloudflare)",
                        "Live",
                        "53+ guides published with SEO optimization. 7 category landing pages. COMPLETED: 200+ DMA pages built, 51 state pages built, 1,900+ merchant pages built. Admin panels for DMA, State, Merchant, and Partner content management.",
                    ],
                    [
                        "Reddit Lead Scanner",
                        "Live (Active)",
                        "1,689 leads backfilled to Google Sheet. Scanning every 4 hours. Reply generation every 6 hours (score >= 20). 30 draft replies generated. 8 foundation posts queued.",
                    ],
                    [
                        "CMO Agent System",
                        "Live",
                        "30+ specialized agents for content, analytics, lifecycle, SEO, compliance, and more. Claude Code CLI integration for direct GitHub code changes. Slack-triggered plan-then-build workflows.",
                    ],
                    [
                        "Email (Charlie Saver List)",
                        "Migration Campaign Built",
                        "250K-300K contacts. 8-email migration sequence with 4-segment strategy (Fatigued Accounts, Other Accounts, Interest-Only, Saver+FraudWatch). A/B subject lines. Progressive suppression via n8n (real-time converted_to_saverwell event). Deploy window: ~4 weeks.",
                    ],
                    [
                        "Interactive Tools",
                        "Spec Complete",
                        "5 tools designed (Subscription Audit, Government Benefit Finder, Scam Quiz, Lump Sum Engine, Financial Triage). Supabase backend ready for Subscription Audit (30 benchmark records). Awaiting Lovable frontend implementation.",
                    ],
                ],
            },
        ]

    # ── 3. UPDATE POSITIONING - FOUR MESSAGING PILLARS ────────────────
    pillars_idx = find_section_index(sections, "Four Messaging Pillars")
    if pillars_idx < 0:
        pillars_idx = find_section_index_partial(sections, "Messaging Pillars")
    if pillars_idx >= 0:
        for item in sections[pillars_idx]["content"]:
            if item.get("type") == "table":
                item["rows"] = [
                    ["Verified & Current", '"We check so you don\'t have to"', "1,900+ merchants with automated monitoring via n8n workflows"],
                    ["Location-Aware", '"Discounts where you actually shop"', "125,000+ store locations mapped to your ZIP code across 210 DMAs. All DMA pages, state pages, and merchant pages built"],
                    ["Save & Stay Protected", '"Your financial wellbeing, covered"', "29+ protection articles with red flags, action steps, phone scripts, prevention checklists. Full lifecycle email system with n8n-powered broadcasts keeping subscribers informed"],
                    ["Expert Guides", '"Complex topics, simple answers"', "96 guides across 7 categories (53 published). Medicare, insurance, medical alerts, phones, hearing aids, finance, and fraud deep-dives. Written for seniors, not insurance agents. Dynamic broadcast engine delivers content based on seasonal priorities and per-subscriber dedup"],
                ]
                break

    # ── 4. UPDATE COMPETITIVE DIFFERENTIATION TABLE ───────────────────
    comp_idx = find_section_index(sections, "Competitive Differentiation")
    if comp_idx >= 0:
        for item in sections[comp_idx]["content"]:
            if item.get("type") == "table":
                # Update the Saverwell column values
                for row in item["rows"]:
                    if len(row) >= 2:
                        dim = row[0]
                        if "Fraud Protection" in dim or "fraud" in dim.lower():
                            row[1] = "29+ article library with actionable guides, phone scripts, checklists. Full email protection drip (8-email series)"
                        elif "Educational" in dim or "Guide" in dim:
                            row[1] = "96 guides across 7 categories (53 published), lifecycle email nurture with 67 templates, automated broadcast engine"
                        elif "Combined" in dim:
                            row[1] = "Savings + Protection + Guides in one platform with full lifecycle marketing (3 active journeys, 8 n8n workflows)"
                break

    # ── 5. UPDATE CHANNEL STRATEGY - EMAIL/LIFECYCLE ──────────────────
    email_idx = find_section_index_partial(sections, "Email/Lifecycle")
    if email_idx >= 0:
        sections[email_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "Email is the retention engine, and as of April 2026, it is **fully operational**. The lifecycle marketing system runs autonomously with 3 active Customer.io campaign journeys for onboarding and re-engagement, plus 3 n8n-powered broadcast workflows for ongoing content delivery. The old fixed-drip approach (Expert Guide 13-email, Protection Drip 8-email, Medicare Guides 11-email) was retired in favor of dynamic, article-library-driven broadcasts that automatically select content, apply seasonal boosting, and track per-subscriber dedup.",
            },
            {
                "type": "paragraph",
                "text": "**Deployed subscriber journey (COMPLETED)**: Welcome Flow (5 emails, 14 days) → Core Foundations (6 emails, weekly Tuesdays, covers 3 protection + 3 guide topics) → enters 'Broadcast Eligible' segment → Personalized Broadcasts via n8n (Tue + Thu, dynamic article selection with seasonal priority) + Weekly Digest via n8n (Mon, curated 5-7 article cards) + Medicare Seasonal via n8n (Wed, Sep-Dec AEP window only). Re-Engagement (3 emails) triggers independently on 30-day inactivity, with sunset and suppress for non-responsive subscribers.",
            },
            {
                "type": "paragraph",
                "text": "**Acquisition tactics (COMPLETED)**: Subscribe forms integrated into Cloudflare Worker pipeline. On signup: Supabase edge function → n8n webhook → Customer.io profile creation with full UTM attribution, ZIP code, state resolution, and lifecycle attributes. Partner widget (/widget/v1/) enables distributed email capture on partner sites with custom branding.",
            },
            {
                "type": "paragraph",
                "text": "**Charlie Saver migration campaign (BUILT, ready to deploy)**: 8-email sequence targeting 250K-300K contacts across 4 segments. Fatigued Account Holders (~20K, custom 2-email intro), Other Account Holders (~20K, standard 6-email), Interest-Only (~210K-260K, staggered 50K batches over Days 2-5), Saver+FraudWatch Subscribers (canary on Day 0). A/B subject line testing on every email. Progressive suppression via real-time converted_to_saverwell event through n8n. All links tracked with utm_source=charliesaver for partner overlay trigger.",
            },
            {
                "type": "paragraph",
                "text": "**Additional campaigns drafted and ready for deployment**: Sudden Money After 55 (5 emails, behavior-triggered on lump-sum content), Medicare Myths (4 emails, behavior-triggered on Medicare guide engagement), Fraud Protection Lead Magnet (3 emails, download-triggered), AHS Home Warranty Partner Drip (3 emails, affiliate CTA in emails 2-3), AARP Membership Partner Drip (2 emails, affiliate CTA in email 2).",
            },
        ]

    # ── 6. UPDATE CHANNEL STRATEGY - COMMUNITY/EARNED ─────────────────
    community_idx = find_section_index_partial(sections, "Community/Earned")
    if community_idx >= 0:
        sections[community_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "Community is the trust engine. Seniors trust peer recommendations over advertising. The Reddit monitoring system is fully operational with automated scanning and reply generation.",
            },
            {
                "type": "paragraph",
                "text": "**Reddit lead scanner (live)**: n8n workflow scans target subreddits every 4 hours. 1,689 leads backfilled to Google Sheet dashboard. AI-powered reply generation runs every 6 hours for leads scoring >= 20. 30 draft replies generated. 8 foundation posts queued across r/retirement, r/personalfinance, r/frugal, and r/Scams.",
            },
            {
                "type": "paragraph",
                "text": "**Reddit execution strategy**: Weeks 1-2 text-only posts (karma building, zero self-promotion), Weeks 3-4 begin commenting with 1 link post every 2 weeks (90/10 helpful/promotional ratio), ongoing 2x/week original posts + 3-5x/week helpful comments + 1 link post per 2 weeks. All links tracked with utm_source=reddit, utm_medium=social.",
            },
            {
                "type": "paragraph",
                "text": "**Senior organization partnerships**: AARP local chapters, Area Agencies on Aging, senior centers, libraries (poster/flyer program), church/community bulletin boards. Protection content is the strongest partnership lever. Financial institution partnerships for co-branded protection and educational content.",
            },
        ]

    # ── 7. UPDATE CHANNEL STRATEGY - PARTNERSHIPS ─────────────────────
    partner_idx = find_section_index_partial(sections, "Partnerships (Distribution Engine)")
    if partner_idx >= 0:
        sections[partner_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "The partnership distribution engine has evolved from planning to active infrastructure. The partner promotions system is built and ready for activation pending affiliate approvals.",
            },
            {
                "type": "bullets",
                "items": [
                    "**Affiliate recruitment (in progress)**: 170 merchants researched, 21 CJ Network matches identified, 2 applications submitted (AT&T $80 CPS, Verizon $75 CPS). Priority 1 CJ merchants ready to apply: Walgreens, LensCrafters, Valvoline, Best Western, Marriott, Hertz, Belk, O'Reilly Auto, Michaels, Ross. Revenue potential at 25K traffic: $1,225-3,075/month",
                    "**Partner promotions infrastructure (built)**: Dynamic CTAs on guide/merchant/protection articles via Supabase partner_promotions table. 4 promotion types, 5 position slots, page-type targeting, time-boxed scheduling, commission tracking, GA4 events. 6 partners seeded and ready for activation",
                    "**Embeddable partner widget (deployed)**: Cloudflare Worker serves /widget/v1/ with discount lookup, email signup, and partner branding. Partners can embed on their own sites with custom colors, logos, and disclosures",
                    "**Merchant partnerships**: Offer free 'Senior Discount' badge program for merchants to display on their websites and in-store. Builds inventory while creating backlinks",
                    "**Senior org distribution**: Co-branded discount and protection guides. Protection content is the strongest partnership lever",
                    "**Private label (Month 9+)**: White-label discount feeds, protection content, and guide content for financial advisors, Medicare brokers, senior living communities. Recurring B2B revenue stream via widget API",
                ],
            },
        ]

    # ── 8. INSERT CURRENT EXECUTION STATUS SECTION ────────────────────
    # Insert after the Channel Strategy sections, before Funnel Architecture
    funnel_idx = find_section_index_partial(sections, "Funnel Architecture")
    if funnel_idx < 0:
        funnel_idx = find_section_index_partial(sections, "Complete Funnel")
    if funnel_idx < 0:
        funnel_idx = len(sections)

    # Remove any existing "Current Execution Status" section
    existing_status = find_section_index_partial(sections, "Current Execution Status")
    if existing_status >= 0:
        remove_section_and_children(sections, existing_status)
        funnel_idx = find_section_index_partial(sections, "Funnel Architecture")
        if funnel_idx < 0:
            funnel_idx = len(sections)

    insert_sections_at(sections, funnel_idx, CURRENT_EXECUTION_STATUS_SECTIONS)

    # ── 9. INSERT DEVELOPMENT VELOCITY SECTION ────────────────────────
    # Remove any existing one first
    existing_dev = find_section_index_partial(sections, "Development Velocity")
    if existing_dev >= 0:
        remove_section_and_children(sections, existing_dev)

    # Insert after Current Execution Status
    dev_insert_idx = find_section_index_partial(sections, "Analytics Capabilities")
    if dev_insert_idx >= 0:
        # Find end of Analytics Capabilities children
        dev_insert_idx += 1
        while dev_insert_idx < len(sections) and sections[dev_insert_idx]["level"] > sections[dev_insert_idx - 1]["level"]:
            dev_insert_idx += 1
    else:
        dev_insert_idx = find_section_index_partial(sections, "Funnel Architecture")
        if dev_insert_idx < 0:
            dev_insert_idx = len(sections)

    insert_sections_at(sections, dev_insert_idx, DEVELOPMENT_VELOCITY_SECTION)

    # ── 10. UPDATE PHASED ROLLOUT SECTIONS ────────────────────────────
    phase1_idx = find_section_index_partial(sections, "Phase 1: Foundation")
    if phase1_idx >= 0:
        sections[phase1_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "**Status: LARGELY COMPLETE.** Original objective was to validate that organic search drives traffic and email capture converts. The infrastructure deliverables have been built and deployed.",
            },
            {
                "type": "paragraph",
                "text": "**Completed**: 53+ guide articles published with full SEO optimization (JSON-LD, Twitter Cards, FAQ schema, internal cross-links). 7 category landing pages live. 29+ protection articles published. All 1,900+ merchant pages built. All 200+ DMA pages built. All 51 state pages built. 125,000+ store location pages built. Cloudflare Worker providing bot pre-rendering for all content pages. 6 sub-sitemaps deployed. Customer.io fully configured with 3 active journeys. n8n-powered broadcast engine (Tue+Thu), weekly digest (Mon), and Medicare seasonal (Wed Sep-Dec) replacing old fixed-drip campaigns. 8 n8n workflows in production. Reddit lead scanner active with 1,689 leads. UTM attribution pipeline operational.",
            },
            {
                "type": "paragraph",
                "text": "**Remaining for Phase 1 completion**: GA4 property and GTM container are fully configured (property G-YFGSQ1WTQM, container GTM-PZBKHZ6C with 28 variables, 15 triggers, 16 tags, dataLayer JS helper implemented). Only remaining step: paste GTM snippet into Lovable frontend <head>. After that: first organic traffic measurement against exit criteria (500+ organic sessions/week, 2%+ email capture rate, 50%+ welcome flow completion rate). Charlie Saver migration campaign deployment (250K-300K contacts).",
            },
        ]

    phase2_idx = find_section_index_partial(sections, "Phase 2: Controlled Launch")
    if phase2_idx >= 0:
        sections[phase2_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "**Status: IN PROGRESS.** Objective is to prove email engagement and first affiliate revenue. The lifecycle marketing system is operational. Key focus is now affiliate activation and traffic growth.",
            },
            {
                "type": "paragraph",
                "text": "**Completed**: Full lifecycle marketing system deployed (Welcome → Core Foundations → Broadcasts → Re-Engagement). Personalized broadcast engine sending 2x/week from 80+ article library. Weekly digest running Mondays. Medicare seasonal broadcast ready for AEP. 5 additional behavior-triggered campaigns drafted. Partner promotions infrastructure built with 6 partners seeded.",
            },
            {
                "type": "paragraph",
                "text": "**Active work**: Affiliate program applications (AT&T, Verizon submitted, 10+ high-value CJ merchants ready to apply). Charlie Saver migration campaign deployment. Reddit posting schedule execution. Interactive tools frontend implementation via Lovable. GA4 deployment for traffic and conversion measurement.",
            },
            {
                "type": "paragraph",
                "text": "**Exit criteria**: 5,000+ organic sessions/week, 100+ email signups/week, first affiliate revenue ($50+/month), paid CAC below $3.",
            },
        ]

    # ── 11. UPDATE CONTENT STRATEGY - GUIDE CONTENT LIBRARY ───────────
    guide_lib_idx = find_section_index(sections, "Guide Content Library")
    if guide_lib_idx >= 0:
        sections[guide_lib_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "Saverwell maintains a structured educational guide library with **96 articles drafted and 53+ published** across 7 guide categories. Each article follows a standardized format designed for maximum clarity and actionability: Overview, Key Takeaways, Body (structured headings, savings focus), Savings Tips, Watch Out (warnings), FAQ (5 questions), and Comparison Table (where applicable).",
            },
            {
                "type": "table",
                "headers": ["Category", "Published", "Pipeline", "Monetization"],
                "rows": [
                    ["Medicare", "11", "11+", "Informational (traffic magnet, seasonal AEP broadcasts)"],
                    ["Insurance", "6", "12+", "Lead gen ($20-$200/lead) + affiliate"],
                    ["Medical Alerts", "4+", "12+", "Affiliate (recurring $5-$20/mo)"],
                    ["Phones", "2+", "10+", "Affiliate ($25-$100/activation)"],
                    ["Hearing Aids", "2+", "6+", "Affiliate ($75-$300/sale)"],
                    ["Finance & Retirement", "8+", "15+", "Informational (trust building)"],
                    ["Fraud/Scam Deep-Dives", "6+", "10+", "Protection credibility + email capture"],
                    ["Discounts", "3", "3+", "Merchant affiliate links"],
                    ["Interactive Tools", "0 (spec complete)", "5 tools", "Engagement + email capture"],
                ],
            },
            {
                "type": "paragraph",
                "text": "All published guide articles include pre-written email variants (subject, preheader, intro, CTA) for immediate newsletter distribution. Articles are stored in the guide_articles Supabase table with category taxonomy in guide_categories. URL pattern: /guides/{category_slug}/{article_slug}. Full Article JSON-LD, FAQ schema, Twitter Cards, and internal cross-linking deployed on all published guides.",
            },
            {
                "type": "paragraph",
                "text": "Content generation pipeline: Claude Code generates guide articles from structured prompts with quality refinement (Ralph Loops dual-LLM architecture). Articles pass through field validation (Pydantic models), SEO optimization (title, meta, FAQ, schema), and email variant generation before publishing. A single article from prompt to published takes approximately 15-20 minutes including all variants.",
            },
        ]

    # ── 12. UPDATE RISK ASSESSMENT ────────────────────────────────────
    risk_idx = find_section_index_partial(sections, "Risk Assessment")
    if risk_idx >= 0:
        for item in sections[risk_idx]["content"]:
            if item.get("type") == "table":
                # Update existing rows and add new ones
                updated_rows = [
                    ["SEO Dependency", "HIGH", "HIGH", "Diversify to email + paid by Month 4. Build direct/brand traffic. AEO optimization hedges against SERP changes. Newsletter builds owned audience. Lifecycle marketing system (3 active journeys, 8 workflows) ensures subscriber retention independent of Google. Cloudflare Worker bot rendering ensures content is indexed."],
                    ["Merchant Inventory", "LOW", "LOW", "Already at 1,900+ verified merchants with 125,000+ locations. All merchant, DMA, and state pages built. Automated n8n monitoring. User-submitted updates with verification workflow."],
                    ["Trust/Monetization Tension", "HIGH", "MEDIUM", "Clear 'Sponsored' labels on all affiliate content. Editorial independence. Partner promotions system returns null when no active promotions match (zero visual impact). Protection content has zero commercial motivation."],
                    ["Email Deliverability", "HIGH", "MEDIUM", "Charlie Saver migration uses 4-segment progressive strategy (never blast 250K). Dedicated sending domain with DKIM/SPF/DMARC. Re-engagement campaign sunsets non-responsive subscribers. n8n progressive suppression tracks real-time conversions."],
                    ["Protection Content Accuracy", "HIGH", "LOW", "All articles include official source links (FTC, CFPB, credit bureaus). Quarterly audits. No legal advice."],
                    ["Competitive Response", "LOW-MEDIUM", "LOW", "No competitor combines savings + protection + guides with lifecycle marketing. First-mover advantage with structured data + 96 articles + 67 email templates."],
                    ["Technical Platform", "LOW", "LOW", "Cloudflare Worker + Supabase proven at scale. 7+ migrations deployed. Admin panels operational. Risk significantly reduced from pre-launch assessment."],
                    ["Guide Content Accuracy", "HIGH", "LOW", "All guides include disclaimers, cite official sources, and undergo quarterly accuracy audits. No plan/provider recommendations without affiliate disclosure."],
                    ["Affiliate Activation Timing", "MEDIUM", "MEDIUM", "Partner promotions infrastructure is built but 0 affiliates approved. Revenue depends on application approvals. Mitigation: guide content drives organic traffic and email signups with standalone value even before monetization activates. Multiple affiliate networks being pursued (CJ, Impact.com, ShareASale)."],
                    ["Development Velocity", "LOW", "LOW", "Claude Code CLI integration enables hours-not-days execution for backend work. 30+ CMO Agent specialists available. Lovable handles UI. Risk: Lovable rate limits or API changes could slow frontend work."],
                ]
                item["rows"] = updated_rows
                break

    # ── 13. UPDATE FIRST 30 DAYS → NEXT 90 DAYS ──────────────────────
    first30_idx = find_section_index_partial(sections, "First 30 Days")
    if first30_idx >= 0:
        # Replace this section entirely
        sections[first30_idx]["heading"] = "Next 90 Days Execution Plan (April-June 2026)"
        sections[first30_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "With the platform infrastructure now operational, the execution focus shifts from building to activating and measuring. The principle remains: Claude does 99% of the work. The user only handles API connections, platform configurations, and actions requiring human account access.",
            },
        ]

        # Remove old Week 1-4 subsections
        week_patterns = ["Week 1:", "Week 2:", "Week 3:", "Week 4:"]
        for pattern in week_patterns:
            while True:
                idx = find_section_index_partial(sections, pattern)
                if idx < 0:
                    break
                remove_section_and_children(sections, idx)

    # Insert new execution plan subsections (only if not already present)
    next90_idx = find_section_index_partial(sections, "Next 90 Days")
    if next90_idx >= 0:
        # Check if subsections already exist
        already_has_weeks = find_section_index_partial(sections, "Weeks 1-2: Activate")
        if already_has_weeks >= 0:
            # Remove all existing week subsections to avoid duplicates
            week_patterns_new = [
                "Weeks 1-2: Activate",
                "Weeks 3-6: Scale",
                "Weeks 7-12: Monetize",
            ]
            for pattern in week_patterns_new:
                while True:
                    widx = find_section_index_partial(sections, pattern)
                    if widx < 0:
                        break
                    remove_section_and_children(sections, widx)

        # Re-find next90 after removals
        next90_idx = find_section_index_partial(sections, "Next 90 Days")
        insert_at = next90_idx + 1
        # Skip any remaining children
        while insert_at < len(sections) and sections[insert_at]["level"] > sections[next90_idx]["level"]:
            insert_at += 1

        execution_subsections = [
            {
                "heading": "Weeks 1-2: Activate & Measure (April 2026)",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Task", "Claude Produces", "User Does"],
                        "rows": [
                            ["GA4 activation (MOSTLY DONE)", "GA4 property (G-YFGSQ1WTQM), GTM container (GTM-PZBKHZ6C), 28 variables, 15 triggers, 16 tags, dataLayer JS -- all configured", "Paste GTM snippet into Lovable <head> tag (one-time, ~5 minutes)"],
                            ["Charlie Saver migration launch", "Campaign is built (8 emails, 4 segments, A/B subject lines, progressive suppression). Claude monitors n8n suppression workflow", "Deploy Segment A canary (20K fatigued accounts). Monitor deliverability. Green-light remaining segments"],
                            ["Affiliate applications", "Application talking points for 10 high-value CJ merchants (Walgreens, LensCrafters, Valvoline, Best Western, Marriott, Hertz, Belk, O'Reilly, Michaels, Ross)", "Submit applications via CJ dashboard"],
                            ["Reddit Week 1 posts", "8 foundation posts ready (profile intro, Medicare deadlines, phone bill tips, grandparent scam guide, IRMAA, tax deductions, AI scams, retirement finances)", "Review and post (or approve for posting)"],
                            ["First traffic baseline", "Analytics dashboard spec, GA4 configuration verification", "Review first week of organic session data"],
                        ],
                    },
                ],
            },
            {
                "heading": "Weeks 3-6: Scale Content & Conversions (April-May 2026)",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Task", "Claude Produces", "User Does"],
                        "rows": [
                            ["Remaining Customer.io journeys", "Step-by-step instructions for 2 remaining core journeys (Expert Guide Series 13-email, Protection Drip 8-email) + 5 behavior-triggered campaigns", "Build journeys in Customer.io UI, paste pre-built templates (~5 hours total)"],
                            ["Interactive tools frontend", "Detailed Lovable prompts for each tool (Subscription Audit first, highest engagement value)", "Paste prompts into Lovable, iterate on UI"],
                            ["Publish remaining guides", "Queue next 15-20 guide articles from 96-article pipeline for publishing", "Toggle publish flags in admin dashboard"],
                            ["Partner promotions activation", "Configure first 2-3 partner promotions via admin panel (using approved affiliates)", "Verify partner CTA rendering on guide pages"],
                            ["Email performance review", "Open rates, click rates, welcome flow completion, broadcast engagement analysis", "Review and approve optimization plan"],
                            ["Reddit ongoing engagement", "2x/week posts + 3-5x/week comments. Start link posts (90/10 ratio)", "Review high-visibility posts before publishing"],
                        ],
                    },
                ],
            },
            {
                "heading": "Weeks 7-12: Monetize & Optimize (May-June 2026)",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Task", "Claude Produces", "User Does"],
                        "rows": [
                            ["Affiliate revenue tracking", "Attribution dashboard linking partner_promo_click events to affiliate conversions", "Review first revenue reports"],
                            ["Impact.com publisher account", "Research on 50+ merchants not found on CJ. Application materials", "Set up Impact.com account, submit applications"],
                            ["Content velocity ramp", "10 new guide articles per week from pipeline", "Review and approve for publishing"],
                            ["Paid search pilot", "$500/month Google Search campaign spec for top 10 guide keywords + top 5 protection keywords", "Set up Google Ads account, launch campaigns"],
                            ["Facebook/Instagram pilot", "Ad creative briefs targeting 60+ demographic with savings + protection + guide content mix", "Launch campaigns"],
                            ["Phase 2 exit criteria check", "Assessment against targets: 5,000+ organic sessions/week, 100+ email signups/week, first affiliate revenue ($50+/month)", "Review results, approve Phase 3 plan"],
                        ],
                    },
                ],
            },
        ]
        insert_sections_at(sections, insert_at, execution_subsections)

    # ── 14. UPDATE SEO SECTION WITH DEPLOYED CAPABILITIES ─────────────
    seo_idx = find_section_index_partial(sections, "Organic/SEO")
    if seo_idx >= 0:
        # Add deployed infrastructure note at the beginning of the section
        content = sections[seo_idx]["content"]
        # Find first paragraph and prepend deployed status
        for i, item in enumerate(content):
            if item.get("type") == "paragraph" and "primary growth engine" in item.get("text", "").lower():
                content.insert(i + 1, {
                    "type": "paragraph",
                    "text": "**Deployed SEO infrastructure (as of April 2026)**: Cloudflare Worker (2,389 lines) intercepts all bot traffic and serves pre-rendered HTML with structured data. 6 sub-sitemaps covering DMA, merchants, guides, protection, states, and listing pages. Article JSON-LD, Twitter Cards, FAQ schema, and breadcrumb schema deployed on all content pages. 7 category landing pages live. 42+ broken internal links fixed. 301 redirects for old category URLs. OG meta tags with hero images. Dynamic FAQ generation from discount/guide metadata. 53+ guide pages indexed and ranking.",
                })
                break

    # ── 15. FIX MEDIGAP → MEDICARE SUPPLEMENT GLOBALLY ────────────────
    for section in sections:
        if section["heading"]:
            section["heading"] = section["heading"].replace("Medigap", "Medicare Supplement")
        for item in section.get("content", []):
            if item.get("type") == "paragraph":
                item["text"] = item["text"].replace("Medigap", "Medicare Supplement")
            elif item.get("type") == "table":
                for row in item.get("rows", []):
                    for j, cell in enumerate(row):
                        row[j] = cell.replace("Medigap", "Medicare Supplement")
                for j, h in enumerate(item.get("headers", [])):
                    item["headers"][j] = h.replace("Medigap", "Medicare Supplement")
            elif item.get("type") == "bullets":
                item["items"] = [
                    x.replace("Medigap", "Medicare Supplement")
                    for x in item["items"]
                ]

    # ── 16. FIX OLD COUNTS GLOBALLY ──────────────────────────────────
    count_replacements = [
        ("56,778 store locations", "125,000+ store locations"),
        ("56,778 locations", "125,000+ locations"),
        ("56,778 individual store", "125,000+ individual store"),
        ("1,418 merchants", "1,900+ merchants"),
        ("1,418 verified merchants", "1,900+ verified merchants"),
        ("2,000+ verified merchants in the database (expanding beyond current 1,418", "2,000+ verified merchants in the database (expanding beyond current 1,900+"),
        ("12-article Medicare guide library", "96-article educational guide library (53 published)"),
        ("12 Medicare guide articles", "96 guide articles (53 published across 7 categories)"),
        ("12 Medicare articles", "53+ published guides across 7 categories"),
        ("29-article protection content library (8 published, 21 in pipeline)", "29+ article protection content library"),
    ]
    for section in sections:
        for item in section.get("content", []):
            if item.get("type") == "paragraph":
                for old, new in count_replacements:
                    item["text"] = item["text"].replace(old, new)
            elif item.get("type") == "table":
                for row in item.get("rows", []):
                    for j, cell in enumerate(row):
                        for old, new in count_replacements:
                            row[j] = row[j].replace(old, new)
            elif item.get("type") == "bullets":
                for idx, bullet in enumerate(item["items"]):
                    for old, new in count_replacements:
                        item["items"][idx] = item["items"][idx].replace(old, new)

    # ── 17. MARK COMPLETED ITEMS IN PHASED ROLLOUT ───────────────────
    # Add completion markers to Phase 3 and Phase 4 for items already done
    phase3_idx = find_section_index_partial(sections, "Phase 3: Growth")
    if phase3_idx >= 0:
        for item in sections[phase3_idx].get("content", []):
            if item.get("type") == "paragraph":
                text = item["text"]
                if "All 1,418 merchants" in text or "All 1,900+" in text:
                    item["text"] = text.replace(
                        "All 1,900+ merchants surfaced with individual pages",
                        "COMPLETED: All 1,900+ merchants surfaced with individual pages"
                    )

    phase4_idx = find_section_index_partial(sections, "Phase 4: Scale")
    if phase4_idx >= 0:
        for item in sections[phase4_idx].get("content", []):
            if item.get("type") == "paragraph" or item.get("type") == "bullets":
                pass  # Will be caught by global count fixes

    # ── 18. MARK COMPLETED ITEMS IN KEY PAGES TABLE ──────────────────
    key_pages_idx = find_section_index_partial(sections, "Key Pages and Their Roles")
    if key_pages_idx >= 0:
        for item in sections[key_pages_idx].get("content", []):
            if item.get("type") == "table":
                for row in item.get("rows", []):
                    if len(row) >= 2:
                        page_type = row[0]
                        if "Merchant pages" in page_type:
                            row[0] = "Merchant pages (1,900+ BUILT)"
                        elif "DMA pages" in page_type:
                            row[0] = "DMA pages (200+ BUILT)"
                        elif "Store pages" in page_type:
                            row[0] = "Store pages (125,000+ BUILT)"
                        elif "Protection articles" in page_type:
                            row[0] = "Protection articles (29+ PUBLISHED)"
                        elif "Guide articles" in page_type:
                            row[0] = "Guide articles (53+ PUBLISHED, 96 total drafted)"

    # ── 19. MARK COMPLETED ITEMS IN SEO PAGE SEQUENCING ──────────────
    seo_idx = find_section_index_partial(sections, "Organic/SEO")
    if seo_idx >= 0:
        for item in sections[seo_idx].get("content", []):
            if item.get("type") == "paragraph":
                text = item["text"]
                # Mark page type sequencing phases as completed
                if "Phase 1: Top 50 merchant pages" in text:
                    item["text"] = text.replace(
                        "Phase 1: Top 50 merchant pages",
                        "COMPLETED - Phase 1: All 1,900+ merchant pages"
                    ).replace(
                        "Phase 2: Top 10 DMA landing pages",
                        "COMPLETED - Phase 2: All 200+ DMA landing pages"
                    ).replace(
                        "29 protection articles",
                        "29+ protection articles (PUBLISHED)"
                    )
                if "Phase 3: Top 50 city/ZIP pages" in text:
                    item["text"] = text.replace(
                        "Phase 3: Top 50 city/ZIP pages",
                        "Phase 3: City/ZIP pages"
                    )
                if "Phase 4: Programmatic store-level pages" in text:
                    item["text"] = text.replace(
                        "Phase 4: Programmatic store-level pages (56,778",
                        "COMPLETED - Phase 4: Store-level pages (125,000+"
                    )

    # ── 20. UPDATE COMPETITIVE DIFF TABLE - SAVERWELL COLUMN ─────────
    # Fix merchant count in competitive diff
    comp_idx2 = find_section_index(sections, "Competitive Differentiation")
    if comp_idx2 >= 0:
        for item in sections[comp_idx2].get("content", []):
            if item.get("type") == "table":
                for row in item.get("rows", []):
                    if len(row) >= 2:
                        dim = row[0]
                        if "Coverage" in dim:
                            row[1] = "All merchants (1,900+ and growing). 125,000+ store locations. 200+ DMA pages, 51 state pages (all built)"
                        elif "Location" in dim:
                            row[1] = "ZIP-level store mapping. 125,000+ locations across 210 DMAs. All DMA + state pages built"
                        elif "Verified" in dim:
                            row[1] = "Automated n8n monitoring. Cloudflare Worker bot rendering. All pages built and indexed"

    return structure


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


async def main() -> None:
    settings = get_settings()
    db = Database(db_path=settings.db_path)
    await db.initialize()

    workspace_mgr = WorkspaceManager(db, Path(settings.brand_voices_dir))
    writing_llm = AnthropicLLM(
        api_key=settings.get_llm_api_key(),
        model=settings.llm_model_writing,
    )

    docs_agent = DocsAgent(
        llm=writing_llm,
        db=db,
        workspace_manager=workspace_mgr,
        google_credentials_path=settings.google_credentials_path,
        google_oauth_token_path=settings.google_oauth_token_path,
    )

    # ── Step 1: Read existing doc ───────────────────────────────────
    print("Reading existing GTM document...")
    from googleapiclient.discovery import build

    creds = get_google_credentials(
        service_account_path=settings.google_credentials_path,
        oauth_token_path=settings.google_oauth_token_path,
        scopes=[
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    service = build("docs", "v1", credentials=creds, cache_discovery=False)
    doc = service.documents().get(documentId=DOC_ID).execute()

    # ── Step 2: Convert to DOC_STRUCTURE ────────────────────────────
    print("Converting to DOC_STRUCTURE format...")
    structure = gdoc_to_structure(doc)
    print(f"  Parsed {len(structure['sections'])} sections")

    # ── Step 3: Apply modifications ─────────────────────────────────
    print("Applying April 2026 modifications...")
    structure = apply_modifications(structure)
    print(f"  Final structure: {len(structure['sections'])} sections")

    # Print section list for verification
    for s in structure["sections"]:
        indent = "  " * (s["level"] - 1)
        print(f"  {indent}[H{s['level']}] {s['heading']}")

    # ── Step 4: Update the Google Doc ───────────────────────────────
    print("\nUpdating Google Doc...")
    result = docs_agent._update_google_doc(
        DOC_ID, structure, workspace_id="saverwell"
    )

    if result.get("status") == "updated":
        print("\nDocument updated successfully!")
        print(f"  URL: {result.get('google_docs_url')}")
        print(f"  Sections: {result.get('sections')}")
    else:
        print(f"\nUpdate failed: {result}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
