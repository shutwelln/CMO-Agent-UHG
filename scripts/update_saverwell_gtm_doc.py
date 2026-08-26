#!/usr/bin/env python3
"""Update Saverwell Go-To-Market Strategy Google Doc with full refresh."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cmo_agent.agents.docs import DocsAgent  # noqa: E402
from cmo_agent.config import get_settings  # noqa: E402
from cmo_agent.db.database import Database  # noqa: E402
from cmo_agent.llm.anthropic import AnthropicLLM  # noqa: E402
from cmo_agent.workspace.manager import WorkspaceManager  # noqa: E402

DOC_ID = "16jeXB5cK1C_ZSAax4HNbhBFGhHXE_oS7zT4w7iPI7Ro"

# Abbreviation tracking — first occurrence spelled out, then abbreviation only.
# Order of first use in this document:
#  1. DMA (Designated Market Area) — Exec Summary
#  2. SEO (Search Engine Optimization) — Exec Summary
#  3. ICP (Ideal Customer Profile) — Section 2 heading
#  4. UX (User Experience) — Alternatives table
#  5. CFPB (Consumer Financial Protection Bureau) — Alternatives table
#  6. CPI (Consumer Price Index) — Why Now
#  7. SGE (Search Generative Experience) — Why Now
#  8. TAM (Total Addressable Market) — Market Sizing
#  9. SAM (Serviceable Addressable Market) — Market Sizing
# 10. SOM (Serviceable Obtainable Market) — Market Sizing
# 11. MAU (Monthly Active Users) — Market Sizing
# 12. AEO (Answer Engine Optimization) — SEO section
# 13. FAQ (Frequently Asked Questions) — SEO section
# 14. CTA (Call to Action) — Funnel table
# 15. GA4 (Google Analytics 4) — Funnel table
# 16. CAC (Customer Acquisition Cost) — Paid section
# 17. ROAS (Return on Ad Spend) — Paid section
# 18. B2B (Business-to-Business) — Partnerships
# 19. LTV (Lifetime Value) — Metrics section heading
# 20. FTC (Federal Trade Commission) — Protection Content Library
# 21. UTM (Urchin Tracking Module) — Analytics section
# 22. CPA (Cost Per Acquisition) — Dashboards
# 23. SERP (Search Engine Results Page) — Risk table
# 24. DKIM/SPF/DMARC — Risk table

DOC_STRUCTURE = {
    "title": "Saverwell Go-To-Market Strategy",
    "include_toc": True,
    "sections": [
        # ═══════════════════════════════════════════════════════════════════
        # 1. EXECUTIVE SUMMARY
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Executive Summary",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Saverwell is a free platform for Americans aged 60+ that combines senior discount discovery, fraud protection, and expert educational guides. The platform helps seniors find every discount they have earned, protects them from financial threats, and gives them plain-language guidance on Medicare, insurance, and other complex financial topics. It launches with **1,418 merchants with verified discounts** (8,762 discount records), **56,778 store locations** across **210 Designated Market Areas (DMAs)**, a **29-article protection content library** (8 published, 21 in pipeline) covering scams, identity theft, payment fraud, and digital security, a **12-article Medicare guide library** (first of 7 planned guide categories covering Medicare, insurance, medical alerts, phones, hearing aids, finance, and interactive tools — 54–78 total articles planned), and a Supabase-powered database with n8n automation infrastructure.",
                },
                {
                    "type": "paragraph",
                    "text": "This is not a cold start. The merchant inventory is already built at scale — 1,418 merchants and 56,778 locations are in the database, ready to be surfaced on the site. The educational guide library already has 12 Medicare articles with full SEO optimization, email variants, and structured data. The Phase 1 challenge is indexing and presenting this existing content, not building it from scratch.",
                },
                {
                    "type": "paragraph",
                    "text": "This go-to-market strategy sequences four growth engines in priority order: **organic/Search Engine Optimization (SEO)** as the primary traffic engine (targeting 60% of Year 1 traffic), **email/lifecycle** as the retention engine, **community/earned media** as the trust engine, and **paid acquisition** as the scale engine activated only after organic unit economics are proven.",
                },
                {
                    "type": "paragraph",
                    "text": "The three-pillar content model — savings, protection, and education — creates a powerful content flywheel. Discount discovery drives initial visits, protection content builds trust and engagement depth, educational guides capture high-intent search traffic (Medicare keywords alone drive 100K+ monthly searches) and open new monetization channels (insurance lead gen, affiliate commissions), and the combination creates a platform seniors return to because it serves every dimension of their financial wellbeing. This triple positioning differentiates Saverwell from pure coupon aggregators, generic fraud awareness sites, and insurance-industry Medicare content written for agents rather than consumers.",
                },
                {
                    "type": "paragraph",
                    "text": "The monetization model layers affiliate commissions, sponsored merchant placements, and premium newsletter sponsorships — all designed to be transparent and trust-preserving for a senior audience that is rightfully skeptical of hidden commercial intent.",
                },
                {
                    "type": "paragraph",
                    "text": "**Year 1 targets**: 100,000–250,000 monthly active users, 25,000+ email subscribers, $7,500/month revenue, and 2,000+ verified merchant partners. The strategy is designed for capital efficiency — Phase 1 operates at $0 paid spend, with paid channels activated only after conversion funnels are validated.",
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 1B. CURRENT INFRASTRUCTURE STATUS
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Current Infrastructure Status",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "The platform has significant infrastructure already operational. This section captures what is live, what is connected but unconfigured, and what is not yet set up.",
                },
                {
                    "type": "table",
                    "headers": ["Component", "Status", "Details"],
                    "rows": [
                        [
                            "Supabase Database",
                            "Live",
                            "1,418 merchants, 8,762 discount records, 56,778 store locations, 29 protection articles, 12 Medicare guide articles, guide_categories (7 verticals), guide_articles table, signups table with UTM fields",
                        ],
                        [
                            "n8n Automation",
                            "Live",
                            "Reddit monitoring (7 subreddits, 518+ opportunities), webhook processing, workflow automation",
                        ],
                        [
                            "Customer.io",
                            "Connected",
                            "Profiles auto-created via n8n webhook on signup. No campaigns or events configured yet",
                        ],
                        ["Beehiiv", "Not set up", "Planned for newsletter publishing"],
                        [
                            "GA4",
                            "Not set up",
                            "Tracking specs ready (Marketing Analytics Agent can generate full implementation guide)",
                        ],
                        [
                            "UTM Attribution",
                            "Live",
                            "12-parameter system (5 standard UTM + 7 custom: state, market, zip_code, leadid, subid, email, zip). 180-day cookie persistence, form pre-population, full payload to Supabase edge function → n8n webhook → Customer.io",
                        ],
                        [
                            "Site (Lovable)",
                            "Pre-launch",
                            "Built with Lovable, not yet live to public",
                        ],
                        [
                            "CMO Agent System",
                            "Live",
                            "30+ specialized agents available for content, analytics, lifecycle, SEO, compliance, and more",
                        ],
                        [
                            "Email (250K Legacy List)",
                            "Available",
                            "Needs warm-up protocol before use",
                        ],
                    ],
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 2. MARKET DEFINITION & ICP
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Market Definition & Ideal Customer Profile (ICP)",
            "level": 1,
            "content": [],
        },
        {
            "heading": "Beachhead Segment: The Digital-Comfortable Retiree",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Our beachhead customer is the **Digital-Comfortable Retiree** — aged 60–72, household income $30K–$65K, suburban, smartphone-proficient, shops in-store 3–5 times weekly, and actively seeks savings. They are not technology-averse; they use Google, email, and Facebook daily. They are price-conscious but not extreme couponers.",
                },
                {
                    "type": "paragraph",
                    "text": "Their defining behaviors span three frustrations:",
                },
                {
                    "type": "paragraph",
                    "text": '**Savings frustration**: They Google "senior discounts at [store]" and get frustrated by outdated blog posts, paywalled AARP lists, and scattered Reddit threads. They know discounts exist but cannot find a reliable, current, organized source.',
                },
                {
                    "type": "paragraph",
                    "text": "**Protection frustration**: They receive suspicious calls, emails, and texts with increasing frequency. They worry about scams but do not know where to find trustworthy, plain-language guidance. Mainstream fraud resources are either too generic, too technical, or buried in government websites designed for younger audiences.",
                },
                {
                    "type": "paragraph",
                    "text": "**Information frustration**: They face complex financial decisions — Medicare enrollment windows, Part D coverage gaps, IRMAA (Income-Related Monthly Adjustment Amount) surcharges, Medigap plan selection, insurance comparisons — and the available information is either written for insurance agents (not consumers), designed to sell them a plan (not educate them), or buried in government PDFs that assume expert-level knowledge. They need plain-language, savings-focused guidance from a source that is not trying to sell them something.",
                },
                {
                    "type": "paragraph",
                    "text": "This triple frustration is our opening. Saverwell addresses all three in one place.",
                },
                {
                    "type": "bullets",
                    "items": [
                        "Age: 60–72 (recently retired or near-retirement)",
                        "Household income: $30K–$65K (fixed income, Social Security + modest savings)",
                        "Geography: Suburban, concentrated in retirement metros (Phoenix, Tampa, Miami, Orlando, Las Vegas)",
                        "Digital comfort: Smartphone-proficient, uses Google, email, and Facebook daily",
                        "Shopping behavior: In-store 3–5x/week at national chains (Walmart, Costco, Publix, CVS)",
                        'Motivation: Wants to stretch retirement dollars without feeling "cheap" or working too hard for it',
                        "Protection awareness: Concerned about scams and fraud but uncertain where to get reliable, actionable guidance",
                    ],
                },
            ],
        },
        {
            "heading": "The Urgent Problem",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": 'Senior discounts are **fragmented across hundreds of merchants** with inconsistent and confusing rules. Age thresholds vary from 50 to 65 depending on the merchant. Some require AARP membership, some are day-specific ("Tuesdays only"), some are location-specific (franchise vs. corporate). No single source of truth exists.',
                },
                {
                    "type": "paragraph",
                    "text": "At the same time, financial fraud targeting seniors is accelerating. In 2022 alone, people over 60 lost an estimated **$28.3 billion** to scammers. Common scams — phishing, tech support fraud, grandparent scams, identity theft, gift card schemes, wire transfer fraud — are growing more sophisticated. Seniors are disproportionately targeted because they are more likely to answer phone calls, trust authority figures, and have accumulated savings.",
                },
                {
                    "type": "paragraph",
                    "text": "The result on the savings side: seniors waste time calling stores, visit on wrong days, miss discounts entirely, or assume they don't qualify when they do. A typical senior leaves **$50–$150/month** in unclaimed discounts on the table — not because the discounts don't exist, but because discovering them is unreasonably difficult.",
                },
                {
                    "type": "paragraph",
                    "text": "The result on the protection side: seniors either fall victim to scams they could have recognized, or they become so fearful of fraud that they avoid beneficial financial activities altogether. Neither outcome is acceptable.",
                },
            ],
        },
        {
            "heading": "Current Alternatives & Why They Fall Short",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Alternative", "What It Does", "Why It Falls Short"],
                    "rows": [
                        [
                            "AARP",
                            "$16/yr membership, partner discount program, fraud watch hotline",
                            "Paywall, limited to AARP partners, no location awareness, skews toward insurance/travel not everyday retail. Fraud resources exist but are secondary to membership benefits",
                        ],
                        [
                            "RetailMeNot",
                            "Coupon aggregator with user-submitted deals",
                            "Not senior-specific, no age-based filtering, cluttered user experience (UX), no location awareness, coupon codes often expired, zero fraud protection content",
                        ],
                        [
                            "Blog Listicles",
                            '"50 Senior Discounts You Didn\'t Know About" articles',
                            "Outdated within months, no verification, generic national lists, no location specificity, SEO-optimized clickbait",
                        ],
                        [
                            "Reddit r/frugal",
                            "Community-sourced tips and scattered discount mentions",
                            "No organization, requires active searching, buried in threads, no verification, intimidating UX for seniors",
                        ],
                        [
                            "Government Fraud Sites",
                            "FTC, FBI IC3, Consumer Financial Protection Bureau (CFPB) resources",
                            "Authoritative but generic, not senior-focused, difficult to navigate, no integration with savings or everyday financial life",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "No existing platform combines verified discount discovery, actionable fraud protection, and plain-language educational guides in a single, senior-friendly experience.",
                },
            ],
        },
        {
            "heading": "Why Now",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "**Demographic wave**: 10,000 Americans turn 65 every single day — the largest retirement cohort in history",
                        "**Inflation squeeze**: Consumer Price Index (CPI) up 20%+ since 2020, hitting fixed-income retirees hardest — every dollar of savings matters more",
                        "**Fraud epidemic**: Elder fraud losses reached $28.3 billion in 2022 and continue rising — seniors need protection resources that meet them where they are",
                        "**Digital adoption**: Smartphone ownership among 65+ hit 75%, with 70%+ using search engines weekly",
                        "**AI answer engines**: Google Search Generative Experience (SGE), Perplexity, and ChatGPT are creating new discovery surfaces that reward structured, verified data — exactly what Saverwell provides",
                        '**No incumbent**: No venture-backed or well-funded competitor owns the combined "senior discount discovery + fraud protection + educational guides" category — the space is fragmented across outdated blogs, membership programs, insurance-agent-focused content, and government sites',
                    ],
                },
            ],
        },
        {
            "heading": "Market Sizing",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Metric", "Size", "Notes"],
                    "rows": [
                        [
                            "Total Addressable Market (TAM)",
                            "58M Americans aged 60+",
                            "$3.4 trillion annual spending power",
                        ],
                        [
                            "Serviceable Addressable Market (SAM)",
                            "28M digitally-active seniors who shop in-store",
                            "75% smartphone ownership x in-store shopping frequency",
                        ],
                        [
                            "Serviceable Obtainable Market (SOM) Year 1",
                            "100K–250K Monthly Active Users (MAU)",
                            "0.4–0.9% of SAM — achievable with organic/SEO primary channel",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "The fraud protection vertical expands the addressable audience beyond deal-seekers to include any senior (or their family members) searching for scam prevention guidance — a rapidly growing search category. The educational guides vertical (starting with Medicare) expands it further to the massive population of seniors navigating healthcare enrollment, insurance decisions, and financial planning — 100K+ monthly searches for Medicare topics alone.",
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 3. POSITIONING & NARRATIVE
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Positioning & Narrative",
            "level": 1,
            "content": [],
        },
        {
            "heading": "Core Value Proposition",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": '**"Save more. Stay protected. Stay informed."**',
                },
                {
                    "type": "paragraph",
                    "text": "The savings are out there. So are the fraudsters. And so are the confusing Medicare forms. We help you stay ahead of all of it. Saverwell is the single platform where seniors find verified discounts organized by where they actually shop, get plain-language fraud protection guides, and access expert educational content on Medicare, insurance, and financial decisions — all written for real people, not insurance agents. No membership required. No hidden fees. No paywalls.",
                },
            ],
        },
        {
            "heading": "Four Messaging Pillars",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Pillar", "Message", "Proof Point"],
                    "rows": [
                        [
                            "Verified & Current",
                            '"We check so you don\'t have to"',
                            "1,418 merchants with automated monitoring via n8n workflows",
                        ],
                        [
                            "Location-Aware",
                            '"Discounts where you actually shop"',
                            "56,778 store locations mapped to your ZIP code across 210 DMAs",
                        ],
                        [
                            "Save & Stay Protected",
                            '"Your financial wellbeing, covered"',
                            "29 protection articles with red flags, action steps, phone scripts, and prevention checklists — plus verified discounts, all free",
                        ],
                        [
                            "Expert Guides",
                            '"Complex topics, simple answers"',
                            "12 Medicare guides (and growing across 7 categories) written in plain language for seniors, not insurance agents — with savings tips, warnings, and FAQs in every article",
                        ],
                    ],
                },
            ],
        },
        {
            "heading": "Competitive Differentiation",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": [
                        "Dimension",
                        "Saverwell",
                        "AARP",
                        "RetailMeNot",
                        "Blog Listicles",
                        "Gov Fraud Sites",
                        "SeniorLiving.org",
                    ],
                    "rows": [
                        ["Price", "Free", "$16/yr", "Free", "Free", "Free", "Free"],
                        [
                            "Senior-Specific",
                            "Yes — built for seniors only",
                            "Partial — broad member benefits",
                            "No — general coupons",
                            "Partial — one-off articles",
                            "Partial — general consumer focus",
                            "Yes — but lead-gen focused",
                        ],
                        [
                            "Location-Aware",
                            "ZIP-level store mapping",
                            "No location awareness",
                            "Limited geo-targeting",
                            "No location specificity",
                            "No",
                            "Facility directories",
                        ],
                        [
                            "Verified/Current",
                            "Automated monitoring",
                            "Partner-only verification",
                            "User-submitted (often expired)",
                            "Static (outdated in months)",
                            "Updated periodically",
                            "Varies",
                        ],
                        [
                            "Coverage",
                            "All merchants (1,418 and growing)",
                            "AARP partners only",
                            "Coupon codes only",
                            "Top 10–20 lists",
                            "N/A",
                            "N/A",
                        ],
                        [
                            "Fraud Protection",
                            "29-article library with actionable guides, phone scripts, checklists",
                            "Fraud Watch hotline (members only)",
                            "None",
                            "Occasional articles",
                            "Comprehensive but hard to navigate",
                            "Minimal",
                        ],
                        [
                            "Educational Guides",
                            "12+ Medicare guides, 7 categories planned (54–78 articles) — savings-first, plain language",
                            "Generic articles",
                            "None",
                            "Scattered listicles",
                            "Government PDFs",
                            "22 Medicare pages — written for insurance agents, designed to sell plans",
                        ],
                        [
                            "Combined Platform",
                            "Savings + Protection + Guides in one place",
                            "Separate programs",
                            "Coupons only",
                            "Single-topic articles",
                            "Fraud only",
                            "Lead-gen only",
                        ],
                    ],
                },
            ],
        },
        {
            "heading": "Trust-Building Mechanisms",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Trust is the **single most important asset** for a senior-facing platform. Seniors have been burned by scams, dark patterns, and bait-and-switch offers. Every design and content decision must prioritize trust over conversion optimization.",
                },
                {
                    "type": "bullets",
                    "items": [
                        "**No dark patterns**: No misleading countdown timers, no fake urgency, no manipulative copy",
                        '**Clear sponsor labels**: Every affiliate link clearly marked as "Sponsored" or "We may earn a commission"',
                        "**Fraud protection integration**: Scam warnings, red flag guides, and phone scripts demonstrate that Saverwell puts user safety first — commercial interests never compromise editorial integrity",
                        "**Accessible design**: Large readable fonts (16px minimum), simple navigation, high contrast, mobile-friendly",
                        "**Phone number visible**: Real contact information builds institutional trust",
                        "**Privacy-first**: No selling personal data, no invasive tracking, clear privacy policy in plain English",
                        "**Editorial independence**: Non-affiliate merchants recommended equally — commercial relationships never compromise editorial integrity",
                        "**Protection-first credibility**: The fraud protection content has zero commercial motivation — it exists purely to serve users, which strengthens trust across the entire platform including the savings side",
                    ],
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 4. CHANNEL STRATEGY
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Channel Strategy",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Channels are prioritized by phase, with organic/SEO as the foundation and each subsequent channel layered on as the previous one proves out. This sequencing minimizes burn rate while building sustainable traffic sources.",
                },
            ],
        },
        {
            "heading": "Organic/SEO (Primary Growth Engine — 60% of Year 1 Traffic)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": 'SEO is the primary growth engine because our target audience\'s discovery behavior is search-first. "Senior discounts at Walmart," "Costco senior discount," and "senior discounts near me" are high-intent, moderate-volume queries with weak competition (dominated by outdated blog posts). The fraud protection vertical opens an entirely new set of high-intent keywords ("how to spot a scam call," "what to do if you gave a scammer your information," "senior fraud protection") with even weaker competition. The educational guides vertical — starting with Medicare — opens massive search volume: "Medicare explained," "Medicare Parts A B C D," "does Medicare cover dental," and "Medicare enrollment deadlines" collectively drive 100K+ monthly searches, and the existing content is overwhelmingly written for insurance agents rather than consumers.',
                },
                {
                    "type": "paragraph",
                    "text": "The key advantage: we already have 1,418 merchants, 56,778 locations, and 12 Medicare guide articles in the database. The challenge is not building inventory — it is surfacing and indexing what we already have. Phase 1 focuses on creating the page templates and publishing the highest-value pages first, while the full database powers programmatic expansion in later phases.",
                },
                {
                    "type": "paragraph",
                    "text": "**Page type sequencing** — pages are rolled out in order of SEO authority and content complexity:",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "Phase 1: Top 50 merchant pages by location count (from 1,418 in database) + 29 protection articles — highest search volume, easiest to rank",
                        "Phase 2: Top 10 DMA landing pages (Phoenix, Tampa, Miami, Orlando, Las Vegas, Tucson, Sarasota, Fort Myers, Scottsdale, Jacksonville) — retirement metro concentration",
                        'Phase 3: Top 50 city/ZIP pages ("Senior Discounts in Phoenix AZ 85001") — hyper-local intent',
                        "Phase 4: Programmatic store-level pages (56,778 individual store pages with directions, hours, and specific discount details)",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Keyword tiers**:",
                },
                {
                    "type": "bullets",
                    "items": [
                        'Tier 1 (Head terms): "senior discounts at Walmart", "Costco senior discount", "does Target have senior discounts" — 1K–10K monthly searches, moderate competition',
                        'Tier 2 (Location terms): "senior discounts in Phoenix AZ", "senior discounts near me" — 500–5K monthly searches, low competition',
                        'Tier 3 (Long-tail): "does Publix give senior discounts on Wednesdays", "what age do you need for Kohl\'s senior discount" — 100–500 monthly searches, near-zero competition',
                        'Tier 4 (Protection/fraud terms): "how to freeze your credit", "Medicare identity theft", "gift card scam what to do", "how to spot fake websites" — 500–10K monthly searches, moderate competition but weak senior-specific results',
                        'Tier 5 (Educational guide terms): "Medicare explained", "Medicare Parts A B C D", "does Medicare cover dental", "Medicare enrollment deadlines", "save money on Medicare premiums", "IRMAA surcharges" — 1K–50K monthly searches per keyword, high volume but dominated by insurance-agent-focused content. Saverwell\'s savings-first, consumer-friendly angle is a differentiated entry point',
                        'Tier 6 (Guide expansion terms): "best Medigap plans", "cheapest cell phone plans for seniors", "best medical alert systems", "OTC hearing aids", "senior dental insurance" — 500–20K monthly searches, high commercial intent, affiliate/lead-gen monetization',
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Content velocity targets**: 20 pages/week in Phase 1 (including protection articles and guide articles), 50/week in Phase 2, 100+/week in Phase 3 (programmatic generation from database). **Answer Engine Optimization (AEO)**: Frequently Asked Questions (FAQ) schema, LocalBusiness structured data, Offer schema on every merchant page, HowTo schema on protection guides, Article schema on educational guides — formatted for Google SGE, Perplexity, and AI answer engines.",
                },
            ],
        },
        {
            "heading": "Email/Lifecycle (Retention Engine — 30% of Engaged Users)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Email is the retention engine. Anonymous visitors return sporadically; email subscribers return 2–3x more frequently. The email strategy has four components: acquisition, welcome flow, weekly newsletter, and legacy list integration.",
                },
                {
                    "type": "paragraph",
                    "text": "**Acquisition tactics**:",
                },
                {
                    "type": "bullets",
                    "items": [
                        'Exit-intent popup: "Get your personalized discount guide — enter your ZIP code" (target: 3–5% conversion rate)',
                        'Content upgrade on merchant pages: "Download the complete Walmart senior discount guide" (PDF in exchange for email)',
                        'Protection content upgrade on fraud articles: "Get the complete fraud protection checklist" (PDF in exchange for email)',
                        'Guide content upgrade on educational articles: "Get the free Medicare savings cheat sheet" (PDF in exchange for email)',
                        "ZIP code capture: personalized weekly digest based on their location",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Welcome flow** (5 emails over 14 days via Customer.io/Beehiiv):",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        'Email 1 (Day 0): Personalized discount map for their ZIP — "Here are 8 senior discounts within 10 miles of you"',
                        "Email 2 (Day 3): Top 3 discounts they're probably missing — \"Most seniors don't know about these\"",
                        'Email 3 (Day 6): Protection spotlight — "How to spot the 3 most common scams targeting seniors" (trust-building, links to protection articles)',
                        'Email 4 (Day 10): Community story/testimonial — "How Margaret saves $200/month"',
                        "Email 5 (Day 14): Weekly digest preview + frequency preference setting",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Legacy 250K email list warm-up protocol**: Start with the most engaged 5K contacts (previous openers/clickers). Add 10K/week over 8 weeks. Monitor deliverability at each batch (target: >95% delivery, <0.1% complaint rate). Sunset non-openers after 3 consecutive sends. Never blast 250K on day 1 — that kills deliverability permanently.",
                },
            ],
        },
        {
            "heading": "Community/Earned (Trust Engine)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Community is the trust engine. Seniors trust peer recommendations over advertising. Our Reddit monitoring system is already active, tracking 7 subreddits with **518 discovered opportunities** for engagement.",
                },
                {
                    "type": "paragraph",
                    "text": "**Reddit execution** (monitoring: r/frugal, r/personalfinance, r/retirement, r/senior, r/aging, r/SeniorCitizens, r/FinancialPlanning):",
                },
                {
                    "type": "bullets",
                    "items": [
                        "Respond helpfully to discount questions with Saverwell links (no spam — value-first)",
                        "Respond to fraud and scam questions with relevant protection article links",
                        "Respond to Medicare, insurance, and financial questions with relevant guide article links",
                        'Post original research: "We analyzed 1,418 merchant senior discount policies — here\'s what we found"',
                        'Post protection content: "Step-by-step guide if you think you\'ve been scammed" (linking to protection articles)',
                        "Build karma and community trust before any self-promotion",
                        "Target: 10–20 helpful responses/week, 1 original post/month",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Senior organization partnerships**: AARP local chapters, Area Agencies on Aging, senior centers, libraries (poster/flyer program), church/community bulletin boards. These are high-trust distribution channels with zero cost. Protection content is particularly valuable for these partnerships — senior centers and libraries actively seek fraud prevention resources to share with their communities.",
                },
            ],
        },
        {
            "heading": "Paid (Scale Engine — Phase 2+)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Paid acquisition is activated **only after organic unit economics are proven**. Trigger conditions: organic Customer Acquisition Cost (CAC) below $0.50, conversion funnel validated with 500+ email signups, and welcome flow completion rate above 50%.",
                },
                {
                    "type": "table",
                    "headers": ["Platform", "Budget Allocation", "Rationale"],
                    "rows": [
                        [
                            "Google Search",
                            "60%",
                            "Highest intent — users actively searching for senior discounts and fraud protection",
                        ],
                        [
                            "Facebook/Instagram",
                            "30%",
                            "Best demographic targeting for 60+ age group, lower intent but high reach. Protection content performs well as social share content",
                        ],
                        [
                            "YouTube",
                            "10%",
                            'How-to content ("How to find senior discounts", "How to spot a scam call"), brand awareness for later retargeting',
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Budget ramp**: $500/month pilot (Month 4), $2K/month (Month 6), $5K/month (Month 9) — scaled only if Return on Ad Spend (ROAS) exceeds 3x. Kill any channel that can't achieve <$3 CAC within 30 days of testing.",
                },
            ],
        },
        {
            "heading": "Partnerships (Distribution Engine)",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "**Affiliate recruitment**: Apply to merchant affiliate programs — Amazon Associates, Walmart Affiliate, Target Partners, Costco via Rakuten/ShareASale/CJ Affiliate. Target: 5 active programs by Month 6",
                        '**Merchant partnerships**: Offer free "Senior Discount" badge program for merchants to display on their websites and in-store. Builds merchant inventory while creating backlinks',
                        "**Senior org distribution**: Co-branded discount and protection guides with AARP chapters, senior centers, and Area Agencies on Aging. Protection content is a strong partnership lever — these organizations actively need fraud prevention resources",
                        "**Financial institution partnerships**: Banks and credit unions seeking fraud education content for their senior customers — co-branded protection guides with Saverwell attribution",
                        "**Private label (Month 9+)**: White-label discount feeds and protection content for financial advisors, Medicare brokers, senior living communities. Recurring business-to-business (B2B) revenue stream",
                    ],
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 5. FUNNEL ARCHITECTURE
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Funnel Architecture",
            "level": 1,
            "content": [],
        },
        {
            "heading": "Complete Funnel Map",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": [
                        "Stage",
                        "Page/Action",
                        "Google Analytics 4 (GA4) Event",
                        "Target Rate",
                    ],
                    "rows": [
                        ["Awareness", "SEO/social impression", "page_view", "—"],
                        [
                            "Landing",
                            "Merchant/DMA/city/protection/guide page",
                            "page_view + scroll_depth",
                            "40% scroll to Call to Action (CTA)",
                        ],
                        ["Email Capture", "Popup/inline form", "email_signup", "3–5% of visitors"],
                        [
                            "Activation",
                            "First discount click, protection article read, or guide read",
                            "discount_click, protection_read, guide_read",
                            "60% of signups within 7 days",
                        ],
                        [
                            "Engagement",
                            "3+ discount clicks or 2+ protection reads in 30 days",
                            "user_engaged",
                            "40% of activated",
                        ],
                        [
                            "Monetization",
                            "Affiliate link click",
                            "affiliate_click",
                            "15% of engaged",
                        ],
                        ["Referral", "Share with friend", "share_content", "5% of engaged"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "The three-pillar content model (savings + protection + guides) strengthens activation and engagement. A user who arrives for discounts discovers protection content and educational guides — three reasons to return. A user who arrives via a Medicare search discovers the discount database and fraud protection — three reasons to subscribe. Each content pillar feeds the others: guide readers become discount users, discount users read protection articles, protection readers explore guides.",
                },
            ],
        },
        {
            "heading": "Key Pages and Their Roles",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Page Type", "Primary Role", "Key Metrics"],
                    "rows": [
                        [
                            "Homepage",
                            "Trust + ZIP code entry point + dual mission positioning",
                            "Bounce rate, ZIP submissions",
                        ],
                        [
                            "Merchant pages (1,418 in database; top 50 live in Phase 1)",
                            "SEO + discount details + affiliate CTA",
                            "Organic traffic, affiliate clicks",
                        ],
                        [
                            "DMA pages (210 total)",
                            "Geo landing + local merchant aggregation",
                            "Organic traffic, email capture",
                        ],
                        [
                            "City/ZIP pages",
                            "Hyper-local + store-level results",
                            "Long-tail organic, high engagement",
                        ],
                        [
                            "Store pages (56,778)",
                            "Directions + hours + specific discount",
                            "Affiliate clicks, map interactions",
                        ],
                        [
                            "Protection articles (29+)",
                            "Fraud education + trust building + email capture",
                            "Organic traffic, protection_read events, email capture rate, time on page",
                        ],
                        [
                            "Guide articles (12+ Medicare, 7 categories planned)",
                            "Educational content + high-intent search capture + monetization (affiliate/lead-gen)",
                            "Organic traffic, guide_read events, email capture rate, affiliate/lead-gen clicks",
                        ],
                        [
                            "Newsletter archive",
                            "SEO + trust building",
                            "Organic traffic, subscriber conversion",
                        ],
                    ],
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 6. PHASED ROLLOUT
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Phased Rollout with Exit Criteria",
            "level": 1,
            "content": [],
        },
        {
            "heading": "Phase 1: Foundation & Validation (Weeks 1–4)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**Objective**: Validate that organic search drives traffic and email capture converts. Zero paid spend. The focus is surfacing and indexing existing content (1,418 merchants, 29 protection articles, 12 Medicare guides), not building from scratch.",
                },
                {
                    "type": "paragraph",
                    "text": "**Deliverables**:",
                },
                {
                    "type": "bullets",
                    "items": [
                        "Top 50 merchant pages live (from 1,418 in database) with full discount details and FAQ schema",
                        "29 protection articles live with red flags, action steps, phone scripts, prevention checklists, and HowTo schema (8 published, 21 in pipeline)",
                        "Guides tab live with 12 Medicare articles — each with overview, key takeaways, savings tips, watch-out warnings, FAQ, and Article JSON-LD schema",
                        "10 DMA landing pages for top retirement metros",
                        "GA4 fully instrumented with all custom events (including protection_read, protection_share, guide_read, guide_share)",
                        "Email capture forms on every page (exit-intent + inline), including protection-specific and guide-specific lead magnets",
                        "5-email welcome flow active in Customer.io (with protection content in Email 3 and guide highlight in Email 4)",
                        "Reddit monitoring confirmed active (7 subreddits, 518 opportunities)",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Exit criteria** (must hit all 3 to advance): 500+ organic sessions/week, 2%+ email capture rate, 50%+ welcome flow completion rate. **Budget**: $0 (organic only + existing tools).",
                },
            ],
        },
        {
            "heading": "Phase 2: Controlled Launch (Weeks 5–12)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**Objective**: Prove email engagement and first affiliate revenue. Begin legacy list warm-up. Expand guide content into insurance vertical.",
                },
                {
                    "type": "paragraph",
                    "text": "**Deliverables**:",
                },
                {
                    "type": "bullets",
                    "items": [
                        "Legacy 250K list warm-up begins (5K to 50K over 8 weeks with deliverability monitoring)",
                        "30 DMA pages live (expanding beyond top 10 retirement metros)",
                        "50 city-level pages for highest-population retirement cities",
                        "200+ additional merchant pages surfaced from database (expanding beyond top 50)",
                        "Protection content expanded: 10+ additional articles covering emerging scam types, seasonal fraud patterns",
                        "Insurance guide vertical launched: 8–12 articles (Medigap, dental, vision, life, long-term care, auto, travel insurance) — high monetization potential via lead gen and affiliate",
                        "First affiliate links live on merchant pages (top 5 merchants) and guide articles (insurance lead-gen forms)",
                        "Paid search pilot: $500/month on Google Search for top 10 merchant keywords + top 5 protection keywords",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Exit criteria**: 5,000+ organic sessions/week, 100+ email signups/week, first affiliate revenue ($50+/month), paid CAC below $3. **Budget**: $500/month paid + tools.",
                },
            ],
        },
        {
            "heading": "Phase 3: Growth & Monetization (Weeks 13–24)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**Objective**: Scale content programmatically from the database, diversify monetization, activate Facebook ads. Launch product review guide verticals.",
                },
                {
                    "type": "paragraph",
                    "text": "**Deliverables**:",
                },
                {
                    "type": "bullets",
                    "items": [
                        "Programmatic city/ZIP pages (500+ pages generated from database)",
                        "All 1,418 merchants surfaced with individual pages",
                        "Product review guide verticals launched: medical alert systems (8–12 articles), cell phone plans for seniors (7–10 articles), hearing aid savings guides (4–6 articles) — high affiliate commission verticals",
                        "5+ active affiliate programs with revenue attribution (merchants + guide product reviews)",
                        "Facebook/Instagram ad campaigns targeting 60+ demographic (savings, protection, and guide content mix)",
                        "Advanced email segmentation (by geography, merchant preference, engagement level, content interest: savings/protection/guides)",
                        "Sponsored merchant placement program launched",
                        'Protection content newsletter series: monthly "Fraud Alert" digest driving engagement and trust',
                        'Guide content newsletter series: monthly "Money-Saving Guide" digest featuring new guide articles',
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Exit criteria**: 25,000+ organic sessions/week, $500+/month affiliate revenue, 3%+ email-to-click rate, 10K+ email list size. **Budget**: $2K/month.",
                },
            ],
        },
        {
            "heading": "Phase 4: Scale (Weeks 25–52)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**Objective**: Achieve 100K+ MAU, $5K+/month revenue, and establish category leadership across all three content pillars.",
                },
                {
                    "type": "paragraph",
                    "text": "**Deliverables**:",
                },
                {
                    "type": "bullets",
                    "items": [
                        "All 210 DMAs covered with dedicated landing pages",
                        "2,000+ verified merchants in the database (expanding beyond current 1,418 through automated discovery)",
                        "50+ protection articles covering the full fraud landscape",
                        "Finance and retirement guide vertical launched: Social Security guides, tax deductions, retirement budgeting (8–10 articles) — trust foundation content",
                        "Interactive tools launched: Social Security optimizer, retirement runway calculator, phone bill savings calculator (3–5 tools)",
                        "Identity theft and digital protection guides (6–8 articles) — natural extension of protection content",
                        "Full guide library reaching 54–78 articles across all 7 categories",
                        "Private label API for partners (financial advisors, Medicare brokers, senior living communities) — includes discount feeds, protection content, and guide content",
                        "Community features: user-submitted discounts with verification workflow, user-reported scam alerts",
                        "Mobile app evaluation and potential development",
                        "3+ distribution partnerships generating referral traffic",
                        "Financial institution partnerships for co-branded protection and educational content",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Exit criteria**: 100K+ MAU, $5K+/month revenue, 3+ active distribution partnerships, 25K+ email list. **Budget**: $5K/month.",
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 7. METRICS & UNIT ECONOMICS
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Metrics & Unit Economics",
            "level": 1,
            "content": [],
        },
        {
            "heading": "Customer Acquisition Cost by Channel",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Channel", "CAC Range", "Notes"],
                    "rows": [
                        [
                            "Organic/SEO",
                            "$0.10–$0.30",
                            "Content creation cost amortized over traffic volume; lowest CAC, highest volume. Protection content adds a second organic traffic stream",
                        ],
                        [
                            "Legacy Email List",
                            "$0.02–$0.05",
                            "Near-zero marginal cost — list already owned, just need warm-up infrastructure",
                        ],
                        [
                            "Google Ads",
                            "$1.50–$4.00",
                            'High intent but competitive for "senior discounts" keywords. Protection keywords may be less competitive',
                        ],
                        [
                            "Facebook Ads",
                            "$1.00–$3.00",
                            "Strong demographic targeting for 60+, lower intent than search. Protection content drives higher engagement as share-worthy content",
                        ],
                        [
                            "Reddit/Community",
                            "$0.05–$0.15",
                            "Time investment, high trust signal, low direct cost. Protection responses generate strong goodwill",
                        ],
                        [
                            "Partnerships",
                            "$0.20–$0.50",
                            "Co-marketing costs shared with senior orgs and merchant partners. Protection content is a strong partnership lever",
                        ],
                    ],
                },
            ],
        },
        {
            "heading": "Lifetime Value (LTV) Modeling",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": [
                        "Scenario",
                        "Monthly Visits",
                        "Affiliate Click Rate",
                        "Avg Commission",
                        "Monthly LTV",
                        "12-Month LTV",
                    ],
                    "rows": [
                        ["Conservative", "2 visits/mo", "5%", "$0.15", "$0.015", "$0.18"],
                        ["Base", "4 visits/mo", "10%", "$0.25", "$0.10", "$1.20"],
                        ["Optimistic", "6 visits/mo", "15%", "$0.40", "$0.36", "$4.32"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Email subscribers have 2–3x higher LTV than anonymous visitors due to repeat engagement and newsletter-driven traffic. At the Base scenario, a blended CAC of $0.20 (organic-heavy) yields a 12-month LTV/CAC ratio of 6:1 — well above the 3:1 threshold for sustainable growth.",
                },
                {
                    "type": "paragraph",
                    "text": "The three-pillar content model (savings + protection + guides) is expected to increase visit frequency by 30–50% over a savings-only platform. Users who engage with multiple content types visit more often and retain longer, as each content stream provides an independent reason to return. Guide readers show particularly strong retention — Medicare enrollment windows and insurance decisions create natural return triggers throughout the year.",
                },
            ],
        },
        {
            "heading": "Retention Benchmarks",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Metric", "Target", "Notes"],
                    "rows": [
                        [
                            "D1 (return next day)",
                            "30%",
                            "Driven by welcome email sending personalized discount map",
                        ],
                        [
                            "D7 (return within week)",
                            "20%",
                            "Weekly newsletter + email 2 of welcome flow",
                        ],
                        [
                            "D30 (monthly active)",
                            "12%",
                            "Newsletter subscribers + direct/bookmark traffic",
                        ],
                        [
                            "D90 (quarterly retained)",
                            "8%",
                            "Core loyal users — high affiliate value",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Email subscribers retain at 2–3x the rate of anonymous visitors. Converting a visitor to an email subscriber is the single highest-leverage action in the funnel. Protection content readers show higher engagement depth (longer time on page, more pages per session) which correlates with stronger retention. Guide readers have the highest content engagement — the average Medicare guide is 1,200+ words with FAQs and savings tips that drive extended session times and cross-content discovery.",
                },
            ],
        },
        {
            "heading": "Revenue Projections",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": [
                        "Month",
                        "MAU",
                        "Email List",
                        "Affiliate Revenue",
                        "Sponsored Revenue",
                        "Guide Lead-Gen Revenue",
                        "Total Revenue",
                    ],
                    "rows": [
                        ["Month 3", "3,000", "700", "$50", "$25", "$25", "$100"],
                        ["Month 6", "15,000", "4,500", "$500", "$400", "$300", "$1,200"],
                        ["Month 9", "40,000", "12,000", "$1,800", "$1,200", "$800", "$3,800"],
                        ["Month 12", "120,000", "30,000", "$3,500", "$2,500", "$1,500", "$7,500"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Guide lead-gen revenue includes insurance lead generation ($20–$200/lead from Medicare, Medigap, dental, vision, life insurance guide pages) and affiliate commissions from product review guides (medical alerts $5–$20/month recurring, phones $25–$100/activation, hearing aids $75–$300/sale). This revenue stream activates in Phase 2 when insurance guide content launches and scales significantly in Phase 3 with product review verticals.",
                },
                {
                    "type": "paragraph",
                    "text": "**Break-even point**: Month 4 (covering ~$200/month in hosting + tools). Revenue accelerates in Months 6–12 as affiliate programs mature, guide monetization activates, sponsored placements launch, and the email list compounds. Year 1 total revenue projection: approximately $35,000–$50,000.",
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 8. CONTENT & EDITORIAL STRATEGY
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Content & Editorial Strategy",
            "level": 1,
            "content": [],
        },
        {
            "heading": "Six Content Pillars",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Pillar", "Share of Content", "Examples"],
                    "rows": [
                        [
                            "Discount Discovery",
                            "40%",
                            'Merchant pages, DMA pages, city guides, store-level pages, "new discount" alerts',
                        ],
                        [
                            "Educational Guides",
                            "20%",
                            "Medicare guides, insurance comparisons, medical alert reviews, phone plan comparisons, hearing aid savings guides, Social Security guides, interactive calculators and tools",
                        ],
                        [
                            "Fraud Protection & Prevention",
                            "20%",
                            "Protection articles (red flags, action steps, phone scripts, prevention checklists), emerging scam alerts, seasonal fraud warnings",
                        ],
                        [
                            "Smart Money",
                            "10%",
                            '"How to stack senior discounts with coupons", "5 discounts every Costco senior should know", budgeting tips',
                        ],
                        [
                            "Scam Recovery & Response",
                            "5%",
                            '"What to do if you gave a scammer your information", credit freeze guides, bank fraud response, identity theft recovery',
                        ],
                        [
                            "Community Stories",
                            "5%",
                            '"How Margaret saves $200/month using senior discounts", user tips, success stories, scam survival stories',
                        ],
                    ],
                },
            ],
        },
        {
            "heading": "Guide Content Library",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Saverwell maintains a structured educational guide library, currently containing **12 Medicare articles** with **7 guide categories planned**. Each article follows a standardized format designed for maximum clarity and actionability:",
                },
                {
                    "type": "table",
                    "headers": ["Section", "Purpose"],
                    "rows": [
                        ["Overview", "Plain-language explanation of the topic"],
                        [
                            "Key Takeaways",
                            "5 bullet points summarizing what the reader needs to know",
                        ],
                        ["Body", "Full article with structured headings, savings focus"],
                        [
                            "Savings Tips",
                            "Specific, actionable ways to save money on this topic",
                        ],
                        [
                            "Watch Out",
                            "Warnings about common mistakes, hidden costs, or scam risks",
                        ],
                        ["FAQ", "5 frequently asked questions with clear answers"],
                        [
                            "Comparison Table",
                            "Side-by-side product or plan comparisons (where applicable)",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Current guide categories and content status:",
                },
                {
                    "type": "table",
                    "headers": ["Category", "Articles", "Status", "Monetization"],
                    "rows": [
                        ["Medicare", "12", "Draft (ready to publish)", "Informational (traffic magnet)"],
                        ["Insurance", "0 (8–12 planned)", "Phase 2", "Lead gen ($20–$200/lead)"],
                        ["Medical Alerts", "0 (8–12 planned)", "Phase 3", "Affiliate (recurring $5–$20/mo)"],
                        ["Phones", "0 (7–10 planned)", "Phase 3", "Affiliate ($25–$100/activation)"],
                        ["Hearing Aids", "0 (4–6 planned)", "Phase 3", "Affiliate ($75–$300/sale)"],
                        ["Finance", "0 (8–10 planned)", "Phase 4", "Informational (trust building)"],
                        ["Tools", "0 (3–5 planned)", "Phase 4", "Engagement + email capture"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Each guide article also includes pre-written email variants (subject line, preheader, intro, Call to Action (CTA)) for immediate newsletter distribution. Guide articles are stored in the guide_articles Supabase table, separate from protection articles, with category taxonomy in guide_categories. URL pattern: /guides/{category_slug}/{article_slug}.",
                },
                {
                    "type": "paragraph",
                    "text": "The guide content strategy is informed by competitive analysis of SeniorLiving.org (~500K–1.5M monthly visits, ~1,850 pages). Their highest-traffic pages are informational (Medicare, directories), but their highest per-visitor revenue comes from product review pages (hearing aids, medical alerts). Saverwell's approach: build traffic with informational guides (Medicare, finance), monetize with product review guides (medical alerts, phones, hearing aids, insurance).",
                },
            ],
        },
        {
            "heading": "Protection Content Library",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Saverwell maintains a structured protection article library, currently containing **29 articles** (8 published, 21 in pipeline) across five categories. Each article follows a standardized format designed for maximum actionability:",
                },
                {
                    "type": "table",
                    "headers": ["Section", "Purpose"],
                    "rows": [
                        ["Overview", "Plain-language explanation of the threat"],
                        ["Red Flags", "Specific warning signs to watch for"],
                        ["What to Do", "Step-by-step response if affected"],
                        [
                            "Prevention Checklist",
                            "Actionable items to protect yourself proactively",
                        ],
                        [
                            "Phone Scripts",
                            "Word-for-word scripts for calling banks, reporting to the Federal Trade Commission (FTC), and telling family members",
                        ],
                        [
                            "Resources",
                            "Links to official reporting channels and help organizations",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Current article categories and coverage:",
                },
                {
                    "type": "table",
                    "headers": ["Category", "Articles", "Examples"],
                    "rows": [
                        [
                            "Scams",
                            "10",
                            "5 common scams, gift card scams, fake check overpayment, charity scams, peer-to-peer payment scams, romance/sweetheart scams, investment/crypto scams, Medicare scams",
                        ],
                        [
                            "Fraud Recovery",
                            "4",
                            "What to do if scammed, what to do after a data breach, shared verification code with scammer, identity theft recovery steps",
                        ],
                        [
                            "Identity Protection",
                            "5",
                            "Protecting your Social Security number, credit freeze guide, reading your credit report, Medicare identity theft, protecting a deceased family member's identity",
                        ],
                        [
                            "Digital Security",
                            "7",
                            "Password safety, two-factor authentication, smartphone security, spotting fake websites, email account hacked, AI deepfake voice scams, QR code phishing",
                        ],
                        [
                            "Financial Safety",
                            "3",
                            "Wire transfer fraud, subscription traps and unauthorized charges, tax refund fraud",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "New articles are generated through a structured pipeline that converts fraud intelligence (sourced from FraudWatch newsletters and emerging threat monitoring) into the standardized protection article format, complete with Supabase publishing.",
                },
            ],
        },
        {
            "heading": "Content Cadence",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        '**Weekly**: 1 newsletter ("Your Weekly Senior Savings, Protection & Guide Update"), 2–3 new merchant/location pages, 1 Smart Money article, 1 guide article (rotating across categories)',
                        "**Biweekly**: 1 new or updated protection article based on emerging fraud trends",
                        "**Monthly**: 1 fraud alert digest (compilation of month's top threats), 1 Community Story, DMA expansion batch (5–10 new DMA pages), 1 guide category expansion batch (3–5 articles in the current focus vertical)",
                        "**Quarterly**: Comprehensive discount guide update (re-verify all merchants), merchant verification sweep, seasonal discount roundup, protection library audit (update statistics, add new scam types), guide library audit (update pricing data, policy changes, dead links in comparison tables)",
                    ],
                },
            ],
        },
        {
            "heading": "Content Repurposing Workflow",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "One piece of research feeds 5+ distribution touchpoints. Every merchant verification, discount discovery, or fraud alert follows this repurposing chain:",
                },
                {
                    "type": "paragraph",
                    "text": "**Savings content chain:**",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "Source page on Saverwell (SEO-optimized, evergreen)",
                        "Email excerpt in weekly newsletter (driving traffic back to site)",
                        "Social snippet for Facebook group post (shareable format)",
                        "Reddit comment when relevant questions arise (helpful, not promotional)",
                        "Newsletter feature in monthly roundup (compilation format)",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Protection content chain:**",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "Full protection article on Saverwell (SEO-optimized, structured for AEO)",
                        "Protection spotlight in weekly newsletter (trust-building + traffic)",
                        "Social share card for Facebook (shareable fraud alert format)",
                        "Reddit response to scam/fraud questions (link to full article)",
                        "Partner distribution to senior centers and libraries (co-branded PDF)",
                        "Email drip content for protection-interested segment",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Guide content chain:**",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "Full guide article on Saverwell (SEO-optimized, Article schema, savings tips, FAQ)",
                        "Guide highlight in weekly newsletter (using pre-written email variants)",
                        'Social snippet for Facebook (shareable savings tip or "did you know" fact)',
                        "Reddit response to Medicare/insurance/finance questions (link to full guide)",
                        "Email drip content for guide-interested segment (triggered by guide_read events)",
                        "Cross-link to related merchant discounts (e.g., Medicare hearing aid guide to hearing aid merchants with senior discounts)",
                    ],
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 9. ANALYTICS & MEASUREMENT FRAMEWORK
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Analytics & Measurement Framework",
            "level": 1,
            "content": [],
        },
        {
            "heading": "GA4 Custom Event Taxonomy",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Event Name", "Trigger", "Key Parameters"],
                    "rows": [
                        [
                            "page_view",
                            "Any page load",
                            "page_type, merchant_id, dma_id, content_category",
                        ],
                        [
                            "email_signup",
                            "Form submission",
                            "signup_source, zip_code, content_interest (savings/protection/guides/all)",
                        ],
                        [
                            "discount_click",
                            "Click on discount detail",
                            "merchant_id, discount_type, location",
                        ],
                        [
                            "affiliate_click",
                            "Click on affiliate link",
                            "merchant_id, commission_type, page_type",
                        ],
                        [
                            "protection_read",
                            "Protection article scroll >75%",
                            "article_slug, category_slug, reading_minutes",
                        ],
                        [
                            "protection_share",
                            "Share a protection article",
                            "article_slug, share_method",
                        ],
                        [
                            "guide_read",
                            "Guide article scroll >75%",
                            "article_slug, category_slug, reading_minutes, guide_vertical",
                        ],
                        [
                            "guide_share",
                            "Share a guide article",
                            "article_slug, share_method",
                        ],
                        ["share_content", "Share button click", "share_method, content_type"],
                        ["search_query", "Site search", "search_term, results_count"],
                        ["zip_lookup", "ZIP code entry", "zip_code, dma_id"],
                        ["scroll_depth", "25/50/75/100% scroll", "page_type, depth_percent"],
                        ["store_directions", "Click for directions", "merchant_id, store_id"],
                        ["scam_alert_view", "Scam alert displayed", "alert_type, merchant"],
                        ["newsletter_open", "Email opened", "campaign_id, segment"],
                        [
                            "newsletter_click",
                            "Email link clicked",
                            "campaign_id, link_type, content_category",
                        ],
                    ],
                },
            ],
        },
        {
            "heading": "Urchin Tracking Module (UTM) Attribution System (Live)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Saverwell has a fully operational UTM attribution pipeline already built into the frontend. The system accepts 12 URL parameters — 5 standard UTM tags plus 7 custom parameters for geographic targeting, partner tracking, and form pre-population:",
                },
                {
                    "type": "table",
                    "headers": ["Parameter", "Purpose", "Example"],
                    "rows": [
                        ["utm_source", "Traffic source", "google, newsletter, partner"],
                        ["utm_campaign", "Campaign name", "spring2026, medicare-guide-launch"],
                        ["utm_medium", "Marketing medium", "email, cpc, social"],
                        ["utm_content", "Ad/content variant for A/B testing", "banner_a, sidebar_cta"],
                        ["utm_referrer", "Referring site (auto-set from document.referrer if absent)", "blog.example.com"],
                        ["utm_state", "Target state for geo-targeted campaigns", "FL, AZ"],
                        ["utm_market", "Target DMA/market for local campaigns", "tampa, phoenix"],
                        ["utm_zip_code", "Target ZIP for hyper-local marketing context", "33601"],
                        ["utm_leadid", "External lead ID for partner attribution", "abc123"],
                        ["utm_subid", "Sub-affiliate/partner ID for multi-tier tracking", "aff456"],
                        ["utm_email", "Pre-known email (pre-fills subscribe form)", "user@example.com"],
                        ["utm_zip", "Pre-known ZIP (pre-fills subscribe form)", "90210"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Data pipeline (fully operational)**: (1) Cookie persistence — all 12 parameters saved to 180-day cookies on page load, surviving cross-page navigation. (2) Form pre-population — utm_email and utm_zip auto-fill the subscribe form. (3) Supabase edge function — on subscribe, full payload (email, ZIP, brand, consent, form source, URL, referrer, honeypot, timestamp, + all 12 UTM fields) sent to edge function. (4) n8n webhook — edge function forwards entire payload with server-derived ip_address and timestamp. (5) Customer.io — n8n maps payload into profile attributes for segmented lifecycle messaging.",
                },
                {
                    "type": "paragraph",
                    "text": "**UTM naming conventions**: utm_source: google, facebook, reddit, email, partner, direct, beehiiv. utm_medium: organic, cpc, social, email, referral, newsletter. utm_campaign: {channel}_{content-type}_{date} (e.g., email_weekly-digest_2026-03-15, email_medicare-guide_2026-03-20). utm_content: {variant}_{position} for A/B testing.",
                },
                {
                    "type": "paragraph",
                    "text": "This system enables attribution-aware lifecycle marketing from day one — every signup carries full context about how they discovered Saverwell, which campaign brought them, and which geographic market they are in.",
                },
            ],
        },
        {
            "heading": "Attribution Approach by Phase",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "**Phase 1–2**: Last-touch attribution (simple, sufficient at low volume, easy to implement)",
                        "**Phase 3+**: First-touch for acquisition channels (which channel brought them in), last-touch for conversion channels (what drove the purchase)",
                        "**Phase 4**: Evaluate multi-touch data-driven attribution when volume supports statistical significance",
                    ],
                },
            ],
        },
        {
            "heading": "Dashboard Requirements",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Nine dashboards covering every critical business function:",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "**Executive Summary**: MAU, revenue, CAC, LTV, channel mix, month-over-month growth",
                        "**SEO Performance**: Organic sessions, keyword rankings (savings + protection + guide keywords tracked separately), page indexation rate, Core Web Vitals",
                        "**Email Health**: List size, open rate, click rate, deliverability, unsubscribe rate, welcome flow completion",
                        "**Affiliate Revenue**: Clicks, conversions, commission by merchant, top-performing pages, trending merchants, guide lead-gen revenue",
                        "**Content Velocity**: Pages published per week (savings, protection, and guides tracked separately), content gaps identified, update frequency, broken links",
                        "**Protection Content**: Protection article reads, shares, time on page, most-read articles, search queries driving protection traffic, conversion to email signup",
                        "**Guide Content**: Guide article reads, shares, time on page, most-read guides by category, search queries driving guide traffic, guide-to-email conversion, affiliate/lead-gen clicks from guide pages, guide category performance comparison",
                        "**Funnel Conversion**: Stage-by-stage drop-off rates, A/B test results, conversion rate by page type (savings vs. protection vs. guide entry points)",
                        "**Paid Media**: Spend by platform, Cost Per Acquisition (CPA) by campaign, ROAS, budget pacing, keyword performance",
                    ],
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 10. RISK ASSESSMENT & MITIGATION
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Risk Assessment & Mitigation",
            "level": 1,
            "content": [
                {
                    "type": "table",
                    "headers": ["Risk", "Severity", "Likelihood", "Mitigation Strategy"],
                    "rows": [
                        [
                            "SEO Dependency",
                            "HIGH",
                            "HIGH",
                            "Diversify to email + paid by Month 4. Build direct/brand traffic. AEO optimization hedges against Search Engine Results Page (SERP) changes. Newsletter builds owned audience independent of Google. Protection content doubles organic keyword surface area.",
                        ],
                        [
                            "Merchant Inventory",
                            "LOW",
                            "LOW",
                            "Already at 1,418 verified merchants with 56,778 locations in database. Automated n8n monitoring for discount policy changes. User-submitted updates with verification workflow. Focus is surfacing existing inventory, not building it.",
                        ],
                        [
                            "Trust/Monetization Tension",
                            "HIGH",
                            "MEDIUM",
                            'Clear "Sponsored" labels on all affiliate content. Editorial independence — recommend non-affiliate merchants equally. Protection content has zero commercial motivation, which strengthens platform-wide trust.',
                        ],
                        [
                            "Email Deliverability",
                            "HIGH",
                            "HIGH",
                            "Legacy list warm-up protocol (never blast 250K). Dedicated sending domain with DomainKeys Identified Mail (DKIM), Sender Policy Framework (SPF), and Domain-based Message Authentication, Reporting & Conformance (DMARC). Aggressive sunset of non-openers. Monitor complaint rates at every batch.",
                        ],
                        [
                            "Protection Content Accuracy",
                            "HIGH",
                            "LOW",
                            "All protection articles include links to official sources (FTC, CFPB, credit bureaus). Articles follow a structured format with verified phone numbers and URLs. Regular quarterly audits to update statistics and remove outdated information. No legal advice — always recommend consulting professionals for specific situations.",
                        ],
                        [
                            "Competitive Response",
                            "LOW-MEDIUM",
                            "LOW",
                            "AARP unlikely to build location-aware discount search (not their business model). RetailMeNot unlikely to go senior-specific. No competitor combines savings + protection in one platform. First-mover advantage in structured senior discount data + protection content.",
                        ],
                        [
                            "Technical Platform",
                            "MEDIUM",
                            "LOW",
                            "Lovable prototype sufficient for validation. Plan migration to Next.js + Vercel if >50K MAU. Supabase scales well for current data volume (56,778 locations).",
                        ],
                        [
                            "Fraud Landscape Evolution",
                            "MEDIUM",
                            "HIGH",
                            "Protection content pipeline can rapidly convert emerging fraud intelligence into new articles. Automated monitoring for new scam types. Quarterly content audit ensures coverage stays current.",
                        ],
                        [
                            "Guide Content Accuracy",
                            "HIGH",
                            "LOW",
                            'Guide articles cover regulated topics (Medicare, insurance) where inaccurate information could harm readers. Mitigation: all guides include disclaimers ("This is educational content, not professional advice"), link to official sources (Medicare.gov, state insurance departments), cite specific policy numbers and dates, and undergo quarterly accuracy audits to reflect policy changes (e.g., IRMAA thresholds update annually). No guide recommends a specific plan or provider without transparent affiliate disclosure.',
                        ],
                        [
                            "Guide Monetization Timing",
                            "LOW",
                            "MEDIUM",
                            "Insurance lead-gen and affiliate revenue from guides requires Phase 2–3 partner integrations. If partnerships take longer to close, guide content still drives organic traffic and email signups — the traffic has standalone value even before monetization activates.",
                        ],
                    ],
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # 11. FIRST 30 DAYS EXECUTION CHECKLIST
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "First 30 Days Execution Checklist",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**Principle**: Claude does 99% of the work. The user only handles API connections, platform configurations, and actions requiring human account access.",
                },
            ],
        },
        {
            "heading": "Week 1: Infrastructure",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Task", "Claude Produces", "User Does"],
                    "rows": [
                        [
                            "GA4 setup",
                            "Full event taxonomy spec, implementation guide with dataLayer.push() code snippets for all 14 custom events",
                            "Create GA4 property, paste measurement ID into Lovable settings",
                        ],
                        [
                            "Customer.io welcome flow",
                            "5-email sequence: subject lines, body copy, trigger logic, delay specs, segment definitions",
                            "Create campaign in Customer.io UI, paste content, set triggers",
                        ],
                        [
                            "UTM governance",
                            "UTM attribution system is already live (12 parameters, 180-day cookies, full Supabase → n8n → Customer.io pipeline). Claude produces: naming convention cheat sheet with example URLs for all channels + campaigns, n8n validation workflow spec",
                            "Review cheat sheet, bookmark for campaign launches",
                        ],
                        [
                            "Email capture forms",
                            "Lovable prompt for exit-intent popup + inline form components (see Appendix A)",
                            "Paste prompt into Lovable",
                        ],
                        [
                            "Reddit monitoring",
                            "Confirm active via CMO Agent status check",
                            "None — already running",
                        ],
                        [
                            "Brand voice review",
                            "Audit brand voice file for triple-mission consistency (savings + protection + guides)",
                            "Review and approve",
                        ],
                        [
                            "Protection articles audit",
                            "Review all 29 articles for accuracy, formatting, SEO optimization",
                            "None — Claude handles",
                        ],
                        [
                            "Guide articles publish",
                            "Set all 12 Medicare guide articles to publish_web=true in Supabase, verify Article JSON-LD schema, confirm Guides tab rendering",
                            "Toggle publish flags in admin dashboard",
                        ],
                    ],
                },
            ],
        },
        {
            "heading": "Week 2: Content Foundation",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Task", "Claude Produces", "User Does"],
                    "rows": [
                        [
                            "Top 50 merchant pages",
                            "SEO-optimized content briefs + full page copy for top 50 merchants by location count (from 1,418 in database)",
                            "Paste Lovable prompt to create merchant page template (see Appendix A)",
                        ],
                        [
                            "Protection articles publish",
                            "Publishing-ready content for all 29 articles with HowTo schema, red flags, phone scripts, prevention checklists",
                            "Paste Lovable prompt to create protection article template (see Appendix A)",
                        ],
                        [
                            "DMA landing pages",
                            "Content for top 10 retirement metro pages (Phoenix, Tampa, Miami, Orlando, Las Vegas, Tucson, Sarasota, Fort Myers, Scottsdale, Jacksonville)",
                            "Paste Lovable prompt to create DMA page template (see Appendix A)",
                        ],
                        [
                            "Schema markup",
                            "Ready-to-paste JSON-LD for FAQ, HowTo, LocalBusiness, Offer, Article on all page types",
                            "Paste into Lovable page templates",
                        ],
                        [
                            "Internal linking",
                            "Complete linking map: merchant to DMA to city to protection to guide cross-links (e.g., Medicare hearing aid guide to hearing aid merchants with senior discounts)",
                            "None — built into page templates",
                        ],
                        [
                            "First Smart Money article",
                            'Full article: "The Complete Guide to Senior Discounts in 2026"',
                            "None — published via template",
                        ],
                        [
                            "Guide content SEO audit",
                            "Verify all 12 Medicare guides have optimized titles, meta descriptions, internal links, FAQ schema, and related_slugs cross-referencing",
                            "None — Claude handles",
                        ],
                    ],
                },
            ],
        },
        {
            "heading": "Week 3: Distribution",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Task", "Claude Produces", "User Does"],
                    "rows": [
                        [
                            "Reddit engagement",
                            "10 drafted responses to discount, fraud, and Medicare/insurance questions with Saverwell links",
                            "Review and post (or approve for auto-posting)",
                        ],
                        [
                            "First newsletter",
                            'Complete newsletter draft: "Welcome to Saverwell — Save More, Stay Protected, Stay Informed" — includes guide highlight section',
                            "Set up Beehiiv publication, paste content",
                        ],
                        [
                            "Guide email campaign",
                            "3-email Medicare guide drip sequence using pre-written email variants from guide articles (subject, preheader, intro, CTA already in Supabase)",
                            "Create campaign in Customer.io",
                        ],
                        [
                            "Affiliate applications",
                            "List of affiliate programs + application talking points for top 5 merchants",
                            "Submit applications",
                        ],
                        [
                            "Partner outreach",
                            "Email templates for senior centers, libraries, AARP chapters — leading with protection content",
                            "Send emails",
                        ],
                        [
                            "Protection content PDFs",
                            "Co-branded fraud protection PDF resources for 5 senior centers/libraries",
                            "Print/distribute",
                        ],
                        [
                            "Legacy list assessment",
                            "Segment analysis: identify most-engaged 5K contacts from 250K list",
                            "None — Claude analyzes",
                        ],
                    ],
                },
            ],
        },
        {
            "heading": "Week 4: Measurement & Iteration",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Task", "Claude Produces", "User Does"],
                    "rows": [
                        [
                            "Analytics review",
                            "Dashboard specs, key metrics to check, savings vs. protection performance comparison",
                            "Review GA4 data",
                        ],
                        [
                            "Conversion audit",
                            "Funnel analysis with recommendations, comparison of savings vs. protection entry point conversion",
                            "None — Claude analyzes",
                        ],
                        [
                            "Content gap analysis",
                            "Priority list of next 200 merchant pages + 5 protection articles + next guide vertical (insurance, 8–12 articles)",
                            "Review priorities",
                        ],
                        [
                            "Email performance review",
                            "A/B test plan for subject lines, CTAs, send times",
                            "Approve test plan",
                        ],
                        [
                            "Protection content review",
                            "Top-performing articles, search queries driving protection traffic, engagement metrics",
                            "None — Claude analyzes",
                        ],
                        [
                            "Guide content review",
                            "Medicare guide performance: reads, time on page, email conversion, search queries, category comparison",
                            "None — Claude analyzes",
                        ],
                        [
                            "Phase 1 exit criteria check",
                            "Assessment against 500 sessions/week, 2% email capture, 50% welcome completion",
                            "Review results",
                        ],
                        [
                            "Month 2 plan",
                            "Detailed roadmap for weeks 5–8 with specific deliverables",
                            "Approve",
                        ],
                    ],
                },
            ],
        },
        # ═══════════════════════════════════════════════════════════════════
        # APPENDIX A: LOVABLE IMPLEMENTATION PROMPTS
        # ═══════════════════════════════════════════════════════════════════
        {
            "heading": "Appendix A: Lovable Implementation Prompts",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Ready-to-paste prompts for each frontend component needed in Phase 1. Each prompt is self-contained for Lovable.",
                },
            ],
        },
        {
            "heading": "A1. Merchant Page Template",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Create a dynamic merchant page template that pulls discount data from our Supabase database. The page should have:",
                },
                {
                    "type": "paragraph",
                    "text": '**Header**: Merchant name (h1), merchant logo (if available from discounts_v2.logo_url), and a subtitle: "Senior Discount at [Merchant Name] — Verified [Month Year]".',
                },
                {
                    "type": "paragraph",
                    "text": "**Discount Details Section**: Pull from discounts_v2 table filtered by merchant_name. Display: discount percentage/description, age requirement, eligible days (if day-specific), whether AARP/membership is required, any restrictions. Format as a clean card layout with large readable text (16px minimum body, 24px headings).",
                },
                {
                    "type": "paragraph",
                    "text": '**Store Locator Section**: "Find [Merchant Name] Near You" with a ZIP code input field. On submit, query store_locations table filtered by merchant and sorted by distance from entered ZIP. Display top 10 results with store address, phone number, and "Get Directions" link (Google Maps).',
                },
                {
                    "type": "paragraph",
                    "text": '**FAQ Section**: Auto-generate 4–5 FAQ items from the discount data: "What age do you need for [Merchant]\'s senior discount?", "What days does [Merchant] offer senior discounts?", etc. Add FAQ JSON-LD schema markup in the page head.',
                },
                {
                    "type": "paragraph",
                    "text": '**Email Capture**: Inline form below the FAQ: "Get weekly discount updates for your area — enter your ZIP code and email." On submit, POST to the Customer.io webhook endpoint with email, zip_code, and signup_source="merchant_page".',
                },
                {
                    "type": "paragraph",
                    "text": '**Affiliate CTA**: If merchant has an affiliate link, show a prominent button: "Shop [Merchant Name] Online" with clear "We may earn a commission" disclosure text. Add rel="sponsored nofollow" to the link.',
                },
                {
                    "type": "paragraph",
                    "text": '**Related Protection Articles**: Show 2 related protection articles from the protection_articles table below the main content. Use a "Stay Protected" header.',
                },
            ],
        },
        {
            "heading": "A2. Protection Article Template",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Create a protection article page template that pulls content from our Supabase protection_articles table. Layout includes:",
                },
                {
                    "type": "paragraph",
                    "text": '**Header**: Article title (h1), category badge (e.g., "Scams", "Digital Security"), publish date, estimated reading time. **Alert Banner**: Yellow/amber banner: "If you are currently being scammed, call your bank immediately, then call the FTC at 1-877-FTC-HELP."',
                },
                {
                    "type": "paragraph",
                    "text": "**Article Body**: Structured sections — Overview (plain-language threat explanation), Red Flags (bulleted list with warning icons), What to Do (numbered steps), Prevention Checklist (checkbox-style with green checkmarks), Phone Scripts (blockquote-styled with copy buttons), Resources (official links card grid).",
                },
                {
                    "type": "paragraph",
                    "text": '**HowTo Schema**: JSON-LD from "What to Do" steps. **Social Sharing**: Facebook, email, Copy Link buttons above and below article. **Email Capture**: "Get weekly fraud alerts" form, POST to Customer.io. **Related Content**: 3 same-category articles + 2 merchant discount pages. **Typography**: 18px body, 1.6 line height, 680px max width.',
                },
            ],
        },
        {
            "heading": "A3. DMA Landing Page Template",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Create a DMA (metro area) landing page aggregating merchants and locations for a geographic area. Data from Supabase store_locations joined with discounts_v2.",
                },
                {
                    "type": "paragraph",
                    "text": '**Header**: "Senior Discounts in [City/Metro] — [Count] Merchants, [Count] Locations". **ZIP Quick Search**: Prominent input that auto-filters results. **Merchant Grid**: Cards with name, logo, discount summary, location count, link to merchant page.',
                },
                {
                    "type": "paragraph",
                    "text": '**Map View**: Embedded map with store location pins from Supabase lat/lng. **Protection Section**: 3 relevant protection articles. **Email Capture**: ZIP + email form, POST to Customer.io with signup_source="dma_page". **LocalBusiness Schema**: JSON-LD for top merchants.',
                },
            ],
        },
        {
            "heading": "A4. Email Capture Popup",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Exit-intent email capture popup. **Trigger**: cursor toward address bar (desktop) or 30-second delay (mobile). Skip if dismissed in last 7 days (localStorage). **Design**: Centered modal, white card, 440px max-width.",
                },
                {
                    "type": "paragraph",
                    "text": '**Content**: "Don\'t Miss Your Discounts" headline. "Enter your ZIP code and we\'ll send you a personalized guide" subheadline. ZIP + Email fields. "Get My Free Guide" button (yellow/gold). "No thanks" dismiss link. Trust line: "Free forever. No spam. Unsubscribe anytime."',
                },
                {
                    "type": "paragraph",
                    "text": '**On Submit**: POST to Customer.io webhook with email, zip_code, signup_source="exit_popup", content_interest="both". Success message + dataLayer.push for tracking.',
                },
            ],
        },
        {
            "heading": "A5. Homepage Protection Section",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": '"Stay Protected" section below main hero, above footer. Header + subtitle: "Free fraud protection guides written in plain language for seniors." Grid of 4 most-read protection articles as cards. Statistics bar: "29 Protection Guides | 10 Scam Categories". CTA: "View All Protection Guides" linking to /protection. Light gray/blue background for visual separation.',
                },
            ],
        },
        {
            "heading": "A6. GA4 dataLayer Events",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Add GA4 tracking using dataLayer pattern. Install base tag (user provides measurement ID), then add custom event pushes for all 14 events: page_view (with page_type, merchant_id, dma_id, content_category), email_signup, discount_click, affiliate_click, protection_read (scroll >75%), protection_share, share_content, zip_lookup, store_directions, scroll_depth (25/50/75/100% via Intersection Observer). See GA4 Custom Event Taxonomy section for full parameter specs.",
                },
            ],
        },
        {
            "heading": "A7. Social Share Buttons",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": 'Share buttons on all content pages — below title and at bottom of content. Three buttons: Facebook (share dialog), Email (mailto with subject/body), Copy Link (clipboard API, shows "Copied!" for 2 seconds). Pill-shaped, 40px height, 8px gap. Mobile: full-width stacked. Fire dataLayer.push on each share.',
                },
            ],
        },
        {
            "heading": "A8. Newsletter Signup Inline Form",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": 'Inline newsletter form on all article pages, between main content and Related Content. Light yellow/amber card. "Weekly Savings & Protection Updates" headline. "Get personalized discount alerts plus fraud protection tips — delivered every Tuesday." Email + ZIP fields + "Subscribe — It\'s Free" button. Trust text below. POST to Customer.io webhook on submit. Hide via localStorage if already subscribed.',
                },
            ],
        },
    ],
}


async def main() -> None:
    print(f"Updating Saverwell GTM Strategy Google Doc (ID: {DOC_ID})...")
    print("Full refresh: updated numbers, protection content, Lovable prompts...\n")

    settings = get_settings()

    db = Database(db_path=settings.db_path)
    await db.initialize()

    workspace_mgr = WorkspaceManager(db, Path(settings.brand_voices_dir))

    writing_llm = AnthropicLLM(
        api_key=settings.get_llm_api_key(),
        model=settings.llm_model_writing,
        max_tokens=settings.llm_max_tokens,
        temperature=0.7,
    )

    docs_agent = DocsAgent(
        llm=writing_llm,
        db=db,
        workspace_manager=workspace_mgr,
        google_credentials_path=settings.google_credentials_path,
        google_oauth_token_path=settings.google_oauth_token_path,
    )

    # Update the existing doc with the refreshed structure
    result = docs_agent._update_google_doc(DOC_ID, DOC_STRUCTURE, workspace_id="saverwell")

    print("\n" + "=" * 60)
    print("RESULT:")
    print("=" * 60)

    if result.get("status") == "updated":
        print("Google Doc updated successfully!")
        print(f"URL: {result['google_docs_url']}")
    elif result.get("status") == "not_configured":
        print(f"Google credentials not configured: {result.get('message')}")
    else:
        print(f"Error: {result.get('message', result)}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
