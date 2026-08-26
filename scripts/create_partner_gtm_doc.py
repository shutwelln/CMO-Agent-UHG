"""One-time script: Create the Saverwell Partner Business Model & GTM Plan Google Doc.

Uses the same Google Docs API pattern as the Docs Agent, but bypasses LLM
generation to ensure the full plan content is faithfully rendered.

Usage:
    source .venv/bin/activate
    python scripts/create_partner_gtm_doc.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add project to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")


# ── Document structure ─────────────────────────────────────────────────

def build_structure() -> Dict[str, Any]:
    """Return the full document structure dict."""
    return {
        "title": "Saverwell Partner Business Model & GTM Plan",
        "include_toc": True,
        "sections": [
            # ── Section 1 ──────────────────────────────────────────
            {
                "heading": "Recommended Business Model: Free Widget, Monetize the Backend",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Give the widget away free. Capture all affiliate/lead-gen revenue "
                            "on the backend. Introduce a paid Enterprise tier later (month 9+) "
                            "once unit economics are proven."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Saverwell is pre-revenue with no proven unit economics on the "
                            "partner channel. Charging creates friction at the exact point "
                            "where frictionless adoption is needed. The revenue engine is "
                            "affiliate commissions, not SaaS fees. The widget is a distribution "
                            "channel for the commission engine, not a product."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Free adoption creates a flywheel: more partners = more subscribers "
                            "= more affiliate revenue = better data to price premium tiers later. "
                            "Competitive dynamics favor free. \"Add a free tool to your site\" is "
                            "a 15-minute conversation. \"Buy my SaaS product\" is a procurement "
                            "cycle."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Can Saverwell still capture affiliate revenue if partners eventually "
                            "pay? Yes, always. A SaaS fee covers platform cost and customization. "
                            "Affiliate revenue persists regardless. They stack, not substitute."
                        ),
                    },
                ],
            },
            # ── Section 2 ──────────────────────────────────────────
            {
                "heading": "Partner Tier Structure",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Three tiers, two free, one paid.",
                    },
                ],
            },
            {
                "heading": "Community (Free)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Target partners: financial advisors, senior centers, nonprofits, "
                            "small agencies."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Standard widget with \"Powered by Saverwell\" footer",
                            "Self-serve onboarding (docs + embed code)",
                            "Full content library, no suppression",
                            "Basic monthly email report (impressions, clicks)",
                        ],
                    },
                ],
            },
            {
                "heading": "Growth (Free)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Target partners: Medicare brokers, regional insurance agencies, "
                            "newsletter operators."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Co-branded welcome overlay + lifecycle emails",
                            "Guided 30-min onboarding call",
                            "Vertical-level competitive suppression (e.g., suppress Medicare broker links)",
                            "Monthly partner report (subscribers, engagement, estimated value)",
                        ],
                    },
                ],
            },
            {
                "heading": "Enterprise (Paid, $199-$999/month)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Target partners: AARP-scale orgs, national brokers like SelectQuote."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "White-label option (remove Saverwell branding), custom CSS, API access",
                            "Full content routing rules + redirect-to-partner CTAs (Calls to Action)",
                            "Real-time analytics dashboard",
                            "Dedicated onboarding + ongoing account management",
                            "Optional rev-share model at high volumes (15% of partner-attributed affiliate revenue)",
                        ],
                    },
                ],
            },
            # ── Section 3 ──────────────────────────────────────────
            {
                "heading": "Channel Conflict Architecture",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This is the core technical challenge. The SelectQuote scenario: a "
                            "Medicare broker sends traffic to Saverwell, and Saverwell's Medicare "
                            "guide articles recommend competing brokers via affiliate links. The "
                            "system must prevent this."
                        ),
                    },
                ],
            },
            {
                "heading": "How It Works",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "A new partner_content_rules table in Supabase stores per-partner suppression and redirect rules as JSONB",
                            "When traffic arrives with utm_campaign={partner_id}, the system looks up that partner's rules",
                            "Suppression rules filter out affiliate links in competing verticals (e.g., hide Medicare broker affiliate links for SelectQuote's traffic)",
                            "Redirect rules replace generic affiliate CTAs with partner-specific CTAs (e.g., \"Get a Quote from SelectQuote\" instead of a generic Medicare comparison)",
                            "Rules execute in two places: the Cloudflare Worker (for bot/SEO-rendered pages) and the Lovable frontend (for SPA navigation via the existing usePartner hook)",
                            "The widget itself needs no changes - it already stamps all outbound links with utm_campaign={partner_name}",
                        ],
                    },
                ],
            },
            {
                "heading": "Suppression Rule Templates by Partner Type",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Partner Type", "Suppression Rules"],
                        "rows": [
                            ["Medicare broker", "Suppress insurance_leads affiliate links in guides. Remove competing broker rows from comparison tables. Optionally redirect Medicare CTAs to partner's quote page."],
                            ["Insurance agency (general)", "Suppress insurance_leads affiliate links. Keep medical alerts, phones, hearing aids (non-competing)."],
                            ["Financial advisor / senior center / nonprofit", "No suppression needed. No competitive conflicts."],
                            ["AARP-scale membership org", "Custom suppression based on their own partnership deals (e.g., AARP has a Consumer Cellular deal, so suppress competing carrier affiliates)."],
                        ],
                    },
                ],
            },
            {
                "heading": "Phased Implementation",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Phase 1 (MVP): Hard-code 2-3 partner rules as URL-parameter checks in the Cloudflare Worker. No database needed.",
                            "Phase 2 (month 3+): partner_content_rules table with configurable JSONB rules. Partner API endpoint for the frontend to fetch rules.",
                            "Phase 3 (month 6+): Redirect rules, real-time rule management, cross-content suppression beyond just guide articles.",
                        ],
                    },
                ],
            },
            # ── Section 4 ──────────────────────────────────────────
            {
                "heading": "Pricing Framework",
                "level": 1,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Partner Profile", "Tier", "Price", "Suppression"],
                        "rows": [
                            ["Local financial advisor (~50 impressions/mo)", "Community", "$0", "None needed"],
                            ["Regional Medicare agency (~500 impressions/mo)", "Growth", "$0", "Vertical-level suppression included"],
                            ["Senior center / nonprofit", "Community", "$0 (always free)", "None needed"],
                            ["National broker with suppression needs (5K-25K impressions/mo)", "Enterprise", "$299-$499/mo", "Full suppression + redirect rules"],
                            ["National membership org like AARP (100K+ impressions/mo)", "Enterprise", "$999/mo or rev-share", "Custom suppression + white-label"],
                        ],
                    },
                ],
            },
            {
                "heading": "Suppression Surcharge Rationale",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "When a Medicare broker asks Saverwell to suppress Medicare affiliate "
                            "links, Saverwell loses $20-$200/lead in affiliate revenue from those "
                            "clicks. The Enterprise fee compensates for that lost revenue. "
                            "Transparent pricing: \"We suppress competitor links to protect your "
                            "business, and the fee covers our forgone affiliate income.\""
                        ),
                    },
                ],
            },
            {
                "heading": "Rev-Share Alternative (Enterprise Only, 100K+ Impressions/Mo)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Saverwell keeps 85% of affiliate revenue from partner-attributed traffic",
                            "Partner receives 15% as a revenue share",
                            "No monthly fee",
                            "Both sides incentivized to drive volume",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Rev-share breakeven analysis: At $5,000/mo in partner-attributed "
                            "affiliate revenue, Saverwell keeps $4,250 under rev-share vs. "
                            "$4,501-$4,701 under flat fee ($499-$999 fee + $4,200 affiliate "
                            "after suppression cost). Rev-share becomes better for Saverwell "
                            "above ~$6,700/mo in affiliate revenue because it scales without "
                            "price renegotiation, while the flat fee caps out. For partners, "
                            "rev-share is attractive because there's no upfront commitment and "
                            "earnings grow with engagement."
                        ),
                    },
                ],
            },
            # ── Section 5 ──────────────────────────────────────────
            {
                "heading": "Partner Unit Economics",
                "level": 1,
                "content": [],
            },
            {
                "heading": "Per Community-Tier Partner (Moderate Scenario)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "1,000 monthly widget impressions, 8% CTR (Click-Through Rate) = 80 clicks to Saverwell",
                            "5% email signup conversion = 4 new subscribers/month",
                            "Subscribers enter lifecycle engine (welcome, drips, guides, Medicare AEP content)",
                            "Affiliate revenue compounds over subscriber lifetime",
                        ],
                    },
                ],
            },
            {
                "heading": "Cohort Model (100 Community-Tier Partners Over 12 Months)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "~350 new subscribers/month = ~4,200 by month 12",
                            "Year 1 affiliate revenue from partner channel: $8K-$30K",
                            "Cost to serve: near-zero (Cloudflare Worker is pennies, email is existing infrastructure)",
                        ],
                    },
                ],
            },
            {
                "heading": "Per Enterprise-Tier Partner (SelectQuote Scenario)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "$499/mo SaaS fee",
                            "25K widget impressions, 2K clicks, 100 new subscribers/month",
                            "Medicare affiliate links suppressed (cost: ~$200-$500/mo in forgone revenue)",
                            "Non-Medicare affiliate revenue from this traffic: $300-$800/mo",
                            "Net revenue per Enterprise partner: ~$599-$799/mo",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "The partner channel is a subscriber acquisition play. Individual "
                            "partners don't generate massive revenue. The economics compound as "
                            "the subscriber base grows and ages through the lifecycle content "
                            "(especially Medicare AEP (Annual Enrollment Period) season, where "
                            "insurance lead revenue spikes at $50-$200/lead)."
                        ),
                    },
                ],
            },
            # ── Section 6 ──────────────────────────────────────────
            {
                "heading": "Subscriber Data Ownership & Privacy",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Core principle: Saverwell owns the subscriber relationship. Partners "
                            "do not get access to individual subscriber data."
                        ),
                    },
                ],
            },
            {
                "heading": "What Partners Get",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Community: Monthly aggregate report (total impressions, clicks, signups attributed to their widget)",
                            "Growth: Monthly report with engagement metrics (open rates, click rates on co-branded emails, estimated subscriber value)",
                            "Enterprise: Real-time dashboard with aggregate metrics + exportable summary reports (never individual emails/PII)",
                        ],
                    },
                ],
            },
            {
                "heading": "What Partners Do NOT Get",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Individual subscriber emails or PII (Personally Identifiable Information)",
                            "Ability to export \"their\" subscriber list",
                            "Direct access to Customer.io segments or profiles",
                            "Ability to send their own emails to Saverwell subscribers",
                        ],
                    },
                ],
            },
            {
                "heading": "Why This Matters",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "If Enterprise partners could export subscriber lists, Saverwell becomes "
                            "a list-building service with no moat. The value is the ongoing "
                            "relationship (lifecycle emails, content, affiliate monetization), not "
                            "a one-time data transfer. This is also critical for CAN-SPAM compliance: "
                            "the subscriber consented to hear from Saverwell, not from the partner "
                            "directly."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Co-branded emails sent through Saverwell's Customer.io pipeline are "
                            "permissible because Saverwell controls the content and the subscriber "
                            "has opted in. The partner's brand appears in the header, but Saverwell "
                            "sends and manages the email."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Partner agreement language: The partner terms of service should explicitly "
                            "state: \"Subscribers acquired through the Saverwell widget are Saverwell "
                            "subscribers. Partner receives aggregate performance data. Individual "
                            "subscriber data is not shared, exported, or transferable.\""
                        ),
                    },
                ],
            },
            # ── Section 7 ──────────────────────────────────────────
            {
                "heading": "Modular Widget Configuration",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Currently, every partner gets the same modules (discounts + fraud "
                            "alert + email signup). This is limiting. The proposed module system "
                            "lets partners select which content modules their widget displays. "
                            "Each module is a toggleable component."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Module", "Default", "Description"],
                        "rows": [
                            ["discounts", "ON", "Local senior discount cards by ZIP"],
                            ["protection", "ON", "Latest fraud alert teaser"],
                            ["guides", "OFF", "Latest guide article teaser (e.g., Medicare enrollment reminder)"],
                            ["signup", "ON", "Email signup form"],
                        ],
                    },
                ],
            },
            {
                "heading": "Configuration via Data Attributes",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Partners configure their widget via data attributes on the embed script tag. "
                            "Example: data-partner=\"selectquote\" data-zip=\"85281\" "
                            "data-modules=\"discounts,guides,signup\" "
                            "data-guide-categories=\"medicare,insurance\"."
                        ),
                    },
                ],
            },
            {
                "heading": "Module Recommendations by Archetype",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Partner Archetype", "Recommended Modules", "Rationale"],
                        "rows": [
                            ["Medicare broker", "guides, protection, signup", "They want the Medicare content, not coupons"],
                            ["Financial advisor", "discounts, signup", "Clean, simple value-add for clients"],
                            ["Senior center", "discounts, protection, signup", "Full experience - discounts + safety"],
                            ["Newsletter operator", "discounts, protection, guides, signup", "Everything - they want engagement"],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Tier gating: Community tier gets default modules only. Growth/Enterprise "
                            "tiers unlock module customization and category filtering. This is a "
                            "natural upsell lever."
                        ),
                    },
                ],
            },
            # ── Section 8 ──────────────────────────────────────────
            {
                "heading": "The AARP Partnership Framework",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "AARP is fundamentally different from a local Medicare broker. They have "
                            "38M+ members, their own affiliate programs (Consumer Cellular, The "
                            "Hartford, UnitedHealthcare), their own content operation, and brand "
                            "requirements that demand control. The standard Enterprise tier doesn't fit."
                        ),
                    },
                ],
            },
            {
                "heading": "AARP-Class Partnership Model: White-Label Platform Deal",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Saverwell powers \"AARP Senior Discounts\" (or whatever AARP wants to call it) as a white-label content engine",
                            "AARP's branding is primary. Saverwell branding is removed or reduced to \"Powered by Saverwell\" in fine print",
                            "AARP controls which content categories appear (suppresses anything conflicting with their existing partnerships)",
                            "Revenue model: Rev-share on all affiliate revenue generated from AARP-attributed traffic. Suggested split: 70/30 (Saverwell/AARP) because Saverwell provides the content, data, and infrastructure",
                            "AARP provides: distribution (38M members, website traffic, email list placement)",
                            "Saverwell provides: discount database, fraud protection content, guide content, lifecycle email engine, widget infrastructure",
                        ],
                    },
                ],
            },
            {
                "heading": "Why This Works",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "For AARP: They already offer an \"AARP Discounts\" section on their "
                            "site. Saverwell's 1,418 merchants and 56,778 locations would massively "
                            "expand AARP's discount coverage without AARP building any infrastructure. "
                            "The content (fraud protection, guides) is additive value for their members."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "For Saverwell: Access to 38M members dwarfs any organic growth strategy. "
                            "Even at a 70/30 split, the volume makes it Saverwell's largest revenue "
                            "source. The AARP partnership also creates credibility for closing every "
                            "subsequent partner (\"We power AARP's senior discount experience\")."
                        ),
                    },
                ],
            },
            {
                "heading": "Custom Suppression for AARP",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Suppress Consumer Cellular competitors (AARP has an exclusive deal)",
                            "Suppress The Hartford competitors (AARP has an exclusive insurance deal)",
                            "Suppress UnitedHealthcare competitors (AARP has a Medicare Advantage deal)",
                            "Keep medical alerts, hearing aids, and other non-conflicting verticals",
                        ],
                    },
                ],
            },
            {
                "heading": "Approach Path",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "This is a 6-12 month sales cycle. Start by identifying the AARP "
                            "business development team. Lead with the data: \"We have 1,418 "
                            "verified merchants with senior discounts across 210 DMAs. Your "
                            "current AARP Discounts page has ~200 merchants. We can 7x your "
                            "discount coverage in 30 days.\" Do not lead with \"we want your "
                            "traffic.\""
                        ),
                    },
                ],
            },
            # ── Section 9 ──────────────────────────────────────────
            {
                "heading": "Partner Retention Strategy",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Acquisition without retention is a leaky bucket. Here's how to keep "
                            "partners engaged after the initial embed."
                        ),
                    },
                ],
            },
            {
                "heading": "Automated Value Signals (Monthly, All Tiers)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Partner email report: \"Your Saverwell widget was viewed X times this month. Y visitors found discounts near them. Z signed up for the weekly digest.\"",
                            "Benchmark against anonymized peer cohort: \"Your widget engagement is 15% above average for Medicare agencies.\"",
                            "Highlight seasonal opportunities: \"Medicare AEP starts Oct 15. Your widget will automatically feature Medicare enrollment guides.\"",
                        ],
                    },
                ],
            },
            {
                "heading": "Partner-Exclusive Content (Growth + Enterprise)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Co-branded seasonal campaigns that make the partner look good to their audience. Example: A Medicare broker gets a co-branded \"Medicare AEP Checklist\" email that Saverwell writes and sends to all subscribers attributed to that partner. The broker's brand is front and center, and they did zero work.",
                            "Early access to new content (e.g., new guide articles go to partner-attributed subscribers 48 hours before public launch)",
                            "Quarterly \"partner spotlight\" feature in the Saverwell digest that highlights the partner to all subscribers in their DMA (Designated Market Area)",
                        ],
                    },
                ],
            },
            {
                "heading": "Retention Metrics to Track",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Widget active rate: % of partners whose widget is still embedded and receiving impressions (target: >85% at 6 months)",
                            "Partner NPS (Net Promoter Score): Quarterly survey (target: >40)",
                            "Expansion rate: % of Community partners upgrading to Growth (target: 10% within 6 months)",
                        ],
                    },
                ],
            },
            {
                "heading": "Churn Signals & Intervention Playbook",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Signals to monitor:",
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Widget impressions drop to zero (partner removed the embed code)",
                            "Partner stops opening monthly reports",
                            "Partner's website goes down or changes platforms (may need re-integration support)",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Intervention playbook:",
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            "Impressions drop >50% month-over-month: Automated email + manual check-in",
                            "Zero impressions for 2 weeks: Personal outreach (\"Is the widget still working on your site? Let me help.\")",
                            "Partner requests removal: Exit interview (\"What would have made this more valuable?\"). Capture feedback for product roadmap.",
                        ],
                    },
                ],
            },
            # ── Section 10 ─────────────────────────────────────────
            {
                "heading": "Partner Program KPIs (Key Performance Indicators)",
                "level": 1,
                "content": [],
            },
            {
                "heading": "Acquisition Metrics",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Partners acquired per month (target: 5-10 in months 1-3, 10-20 in months 4-6)",
                            "Time from first contact to live widget (target: <7 days for Community, <14 days for Growth)",
                            "Activation rate: % of signed-up partners who actually embed the code (target: >70%)",
                        ],
                    },
                ],
            },
            {
                "heading": "Engagement Metrics",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Monthly Active Partners (MAP): Partners with >100 widget impressions in the last 30 days",
                            "Average widget impressions per partner per month",
                            "Click-through rate: widget impressions to Saverwell site visits",
                            "Subscriber conversion rate: widget clicks to email signups",
                        ],
                    },
                ],
            },
            {
                "heading": "Revenue Metrics",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Subscribers acquired via partner channel per month",
                            "Affiliate revenue attributed to partner-sourced subscribers",
                            "Revenue per partner-sourced subscriber (compare to organic subscriber revenue to validate channel quality)",
                            "Enterprise tier revenue (SaaS fees collected)",
                            "Blended partner channel CAC (Customer Acquisition Cost): Total partner program cost / subscribers acquired",
                        ],
                    },
                ],
            },
            {
                "heading": "Health Metrics",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "6-month partner retention rate (target: >85%)",
                            "Widget active rate (% of partners with non-zero impressions)",
                            "Partner NPS (Net Promoter Score)",
                        ],
                    },
                ],
            },
            # ── Section 11 ─────────────────────────────────────────
            {
                "heading": "Medicare Compliance Considerations",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Medicare marketing is regulated by CMS (Centers for Medicare & "
                            "Medicaid Services). Before onboarding Medicare brokers with redirect "
                            "rules, the following items should be flagged for legal review."
                        ),
                    },
                ],
            },
            {
                "heading": "CMS Marketing Guidelines (42 CFR 422.2274)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Medicare Advantage and Part D plans have strict rules about marketing materials, including digital content",
                            "If Saverwell's Medicare guides are being shown to traffic from a Medicare broker, and those guides contain plan comparisons or enrollment CTAs, the content may need to comply with CMS marketing rules",
                            "Saverwell's current Medicare guides are educational (\"What is Medicare?\", \"Medicare Parts Explained\") and do not recommend specific plans, which is generally compliant",
                            "If redirect rules point traffic to a broker's quote page, that's the broker's responsibility (their page, their compliance), but the referral pathway should be reviewed",
                        ],
                    },
                ],
            },
            {
                "heading": "TCPA Considerations",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "TCPA (Telephone Consumer Protection Act) considerations: Email signups "
                            "via the widget create a Saverwell subscriber, not a lead for the "
                            "partner. The partner should NOT receive individual subscriber data for "
                            "telemarketing purposes. If a partner wants Saverwell to pass leads "
                            "(not just subscribers), that's a separate lead-gen agreement with "
                            "explicit TCPA consent language on the signup form."
                        ),
                    },
                ],
            },
            {
                "heading": "Recommended Action",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Before launching the first Growth-tier Medicare broker partnership, "
                            "have a healthcare marketing attorney review: (1) Saverwell's Medicare "
                            "guide content for CMS compliance, (2) the redirect rule mechanism for "
                            "regulatory implications, and (3) the partner terms of service for "
                            "proper data separation language."
                        ),
                    },
                ],
            },
            # ── Section 12 ─────────────────────────────────────────
            {
                "heading": "Operational Scaling: Self-Service Partner Registry",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Current bottleneck: Each partner requires manual work in three systems: "
                            "(1) add config entry to partner-config.ts in the Lovable codebase "
                            "(requires a code deploy), (2) upload logo to Supabase storage, "
                            "(3) configure Customer.io co-branding templates (Liquid conditional "
                            "blocks). This works for 5 partners. It breaks at 20+."
                        ),
                    },
                ],
            },
            {
                "heading": "Target Architecture: Supabase-Backed Partner Registry",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Move partner configuration from hard-coded TypeScript to a "
                            "partner_registry Supabase table with the following schema:"
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Column", "Type", "Description"],
                        "rows": [
                            ["partner_id", "TEXT PRIMARY KEY", "Unique partner identifier"],
                            ["partner_name", "TEXT", "Display name"],
                            ["tier", "TEXT", "community / growth / enterprise"],
                            ["logo_url", "TEXT", "Logo URL in Supabase storage"],
                            ["industry_vertical", "TEXT", "Industry category"],
                            ["welcome_heading", "TEXT", "Custom welcome overlay heading"],
                            ["welcome_subhead", "TEXT", "Custom welcome overlay subheading"],
                            ["value_props", "JSONB", "Array of value propositions"],
                            ["cta_text", "TEXT", "Call-to-action button text"],
                            ["stats", "JSONB", "Stats displayed in widget"],
                            ["suppression_rules", "JSONB", "Content suppression configuration"],
                            ["modules_enabled", "TEXT[]", "discounts, protection, guides, signup"],
                            ["guide_categories", "TEXT[]", "Category filter for guide module"],
                            ["status", "TEXT", "active / paused / churned"],
                            ["created_at", "TIMESTAMPTZ", "Row creation timestamp"],
                        ],
                    },
                ],
            },
            {
                "heading": "Frontend Changes",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "getPartnerConfig() reads from Supabase via API instead of a static TypeScript object",
                            "Cache partner configs at the Cloudflare Worker edge (1-hour TTL) to avoid per-request DB calls",
                            "The usePartner hook logic stays the same - it just reads config from a different source",
                        ],
                    },
                ],
            },
            {
                "heading": "Customer.io Changes",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Instead of per-partner Liquid conditionals, use a generic template that reads customer.brand and dynamically fetches the partner logo and name from the registry",
                            "Template: \"Welcome to Saverwell, courtesy of {{ customer.brand_display_name }}\" with {{ customer.brand_logo_url }} for the header image",
                        ],
                    },
                ],
            },
            {
                "heading": "Self-Service Onboarding Flow",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Partner visits saverwell.com/partners",
                            "Fills out form: company name, website URL, ZIP code, industry vertical, logo upload",
                            "Supabase function creates partner_registry row, stores logo, generates partner_id",
                            "Page displays the embed code with their partner_id pre-filled",
                            "Partner pastes one line of code on their site. Widget goes live immediately.",
                            "For Growth tier (needs co-branding): human reviews and approves the partner entry, adds custom welcome copy",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Build this in Phase 3 (weeks 9-16). Until then, manual setup for "
                            "the first 10 partners is fine."
                        ),
                    },
                ],
            },
            # ── Section 13 ─────────────────────────────────────────
            {
                "heading": "Implementation Phases",
                "level": 1,
                "content": [],
            },
            {
                "heading": "Phase 1: Foundation (Weeks 1-4)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Deploy existing widget + subscribe webhook",
                            "Onboard Bright Path Medicare and Charlie Saver (both already configured)",
                            "Recruit 1-2 Community-tier partners from personal network",
                            "Build minimal partner landing page at saverwell.com/partners",
                            "Create partner_content_rules table in Supabase (minimal schema)",
                            "Define partner program KPIs and set up tracking",
                        ],
                    },
                ],
            },
            {
                "heading": "Phase 2: Channel Conflict + Modules (Weeks 5-8)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Implement URL-parameter-based content suppression in the Cloudflare Worker",
                            "Add data-modules and data-guide-categories support to embed.js",
                            "Add partner rules API endpoint to the Cloudflare Worker",
                            "Extend the Lovable usePartner hook to fetch and apply suppression rules",
                            "Onboard first Growth-tier Medicare broker with competitive suppression",
                            "Build partner attribution reporting (GA4 + monthly email summary)",
                            "Medicare compliance legal review (before first broker goes live)",
                        ],
                    },
                ],
            },
            {
                "heading": "Phase 3: Scale + Self-Service (Weeks 9-16)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Build Supabase-backed partner_registry (replace hard-coded TypeScript configs)",
                            "Partner self-service onboarding flow at saverwell.com/partners",
                            "Partner analytics dashboard (Google Sheet or lightweight web dashboard)",
                            "Introduce Enterprise tier and close first paid partner",
                            "Implement redirect rules for Enterprise partners",
                            "Launch outbound prospecting for Medicare brokers and insurance agencies",
                            "Partner retention automation (monthly value reports, seasonal co-branded campaigns)",
                        ],
                    },
                ],
            },
            {
                "heading": "Phase 4: Enterprise + AARP (Weeks 17+)",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Rev-share model for high-volume Enterprise partners",
                            "White-label widget (remove Saverwell branding, custom CSS)",
                            "API access for deep integrations",
                            "Begin AARP partnership outreach (6-12 month sales cycle)",
                            "Multi-partner suppression conflict resolution",
                            "Partner referral program",
                            "Partner NPS surveys and exit interviews",
                        ],
                    },
                ],
            },
            # ── GTM Playbook ───────────────────────────────────────
            {
                "heading": "Go-to-Market Playbook",
                "level": 1,
                "content": [],
            },
            {
                "heading": "First 10 Partners (Ordered by Ease of Closing)",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Bright Path Medicare - Already configured. Deploy and validate end-to-end.",
                            "Charlie Saver - Already configured. Execute 250K migration per existing setup guide.",
                            "1-2 local AZ financial advisors - Personal network. Community tier. Quick case study.",
                            "A local senior center (Phoenix) - Community tier. PR value.",
                            "A Medicare agent found via LinkedIn - First cold outreach. Tests the Growth-tier pitch.",
                            "A senior-focused newsletter (Substack/Beehiiv) - Content alignment. Widget is a natural fit.",
                            "A regional insurance agency - Tests competitive suppression with a real partner.",
                            "A retirement community website - New archetype. Residents are the exact audience.",
                            "9-10. Stretch targets based on what's working.",
                        ],
                    },
                ],
            },
            {
                "heading": "Sales Motion by Phase",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Partners 1-4 (weeks 1-4): Warm network, founder-led. \"I built a free tool that adds senior discount search to your website. One line of code. Want to try it?\"",
                            "Partners 5-7 (weeks 5-8): Cold outreach via LinkedIn. Lead with data from Partners 1-4.",
                            "Partners 8-10 (weeks 9-12): Inbound via partner landing page + case study content + referrals.",
                        ],
                    },
                ],
            },
            {
                "heading": "Proving ROI (Return on Investment) to Partners",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Financial advisor: \"28 of your clients found senior discounts near them. 6 signed up for the weekly digest. Your website now offers a free value-add that deepens client relationships.\"",
                            "Medicare broker: \"45 email signups this month from your widget. Those subscribers will receive Medicare enrollment reminders during AEP, keeping your brand top-of-mind.\"",
                            "Senior center: \"Your members used the discount finder 120 times. The most popular was Walgreens Senior Day.\"",
                        ],
                    },
                ],
            },
            # ── Key Files ──────────────────────────────────────────
            {
                "heading": "Key Files Reference",
                "level": 1,
                "content": [
                    {
                        "type": "table",
                        "headers": ["File", "Role"],
                        "rows": [
                            ["cloudflare-worker/src/index.ts", "Widget embed.js, discount API, subscribe API. Channel conflict suppression and module configuration will be added here."],
                            ["data/saverwell/lovable_prompt_bright_path_partner.md", "Partner config template. Every new partner follows this pattern."],
                            ["data/saverwell/ga4_datalayer.js", "GA4 tracking with first-touch/last-touch attribution. Partner analytics reporting reads from this."],
                            ["data/saverwell/saverwell_utm_tags.txt", "12-parameter UTM structure. Partner attribution flows through these params."],
                            ["data/saverwell/content_expansion_strategy.md", "Content roadmap. Affiliate monetization tiers determine which content gets suppressed per partner."],
                            ["data/saverwell/customerio_setup_guide.md", "Customer.io lifecycle setup. Co-branding uses brand={partner_name} attribute."],
                        ],
                    },
                ],
            },
        ],
    }


# ── Google Docs API helpers (mirrored from agents/docs.py) ─────────

def _heading_style(level: int) -> str:
    mapping = {1: "HEADING_1", 2: "HEADING_2", 3: "HEADING_3",
               4: "HEADING_4", 5: "HEADING_5", 6: "HEADING_6"}
    return mapping.get(level, "HEADING_1")


def _parse_inline_formatting(text: str) -> Tuple[str, List[tuple]]:
    runs: List[tuple] = []
    result_chars: List[str] = []
    i = 0
    length = len(text)
    while i < length:
        if i + 1 < length and text[i] == "*" and text[i + 1] == "*":
            end_marker = text.find("**", i + 2)
            if end_marker != -1:
                start_pos = len(result_chars)
                inner = text[i + 2 : end_marker]
                result_chars.extend(inner)
                runs.append((start_pos, start_pos + len(inner), "bold"))
                i = end_marker + 2
                continue
        if text[i] == "*" and (i + 1 >= length or text[i + 1] != "*"):
            end_marker = text.find("*", i + 1)
            if end_marker != -1 and (end_marker + 1 >= length or text[end_marker + 1] != "*"):
                start_pos = len(result_chars)
                inner = text[i + 1 : end_marker]
                result_chars.extend(inner)
                runs.append((start_pos, start_pos + len(inner), "italic"))
                i = end_marker + 1
                continue
        result_chars.append(text[i])
        i += 1
    return ("".join(result_chars), runs)


def _normalize_sections(structure: Dict[str, Any]) -> List[Dict[str, Any]]:
    sections = structure.get("sections", [])
    normalized: List[Dict[str, Any]] = []
    for section in sections:
        heading = section.get("heading", "").strip().lower()
        if heading == "table of contents":
            continue
        s = dict(section)
        if "content" not in s:
            body = s.pop("body", "")
            s["content"] = [{"type": "paragraph", "text": body}] if body else []
        normalized.append(s)
    return normalized


def build_google_doc(docs_service, drive_service, structure: Dict[str, Any]) -> Dict[str, Any]:
    """Create a Google Doc and return its URL."""

    title = structure.get("title", "Untitled Document")
    include_toc = structure.get("include_toc", False)
    sections = _normalize_sections(structure)

    # 1. Create empty document
    doc = docs_service.documents().create(body={"title": title}).execute()
    doc_id = doc["documentId"]
    print(f"  Created doc: {doc_id}")

    # 2. Build requests using a sequential cursor
    requests: List[Dict[str, Any]] = []
    cursor = 1

    for si, section in enumerate(sections):
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        # Insert heading
        if heading:
            heading_text = heading + "\n"
            requests.append(
                {"insertText": {"location": {"index": cursor}, "text": heading_text}}
            )
            h_start = cursor
            h_end = cursor + len(heading_text)
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {"startIndex": h_start, "endIndex": h_end},
                        "paragraphStyle": {
                            "namedStyleType": _heading_style(level),
                            "spaceAbove": {"magnitude": 12, "unit": "PT"},
                            "spaceBelow": {"magnitude": 4, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow",
                    }
                }
            )
            cursor = h_end

        # Insert each content block
        for block in content_blocks:
            block_type = block.get("type", "paragraph")

            if block_type == "paragraph":
                text = block.get("text", "")
                if not text:
                    continue
                para_text = text + "\n"
                plain, formatting_runs = _parse_inline_formatting(para_text)
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": plain}}
                )
                p_start = cursor
                p_end = cursor + len(plain)
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
                for run_start, run_end, style in formatting_runs:
                    abs_start = cursor + run_start
                    abs_end = cursor + run_end
                    if style == "bold":
                        requests.append(
                            {
                                "updateTextStyle": {
                                    "range": {"startIndex": abs_start, "endIndex": abs_end},
                                    "textStyle": {"bold": True},
                                    "fields": "bold",
                                }
                            }
                        )
                    elif style == "italic":
                        requests.append(
                            {
                                "updateTextStyle": {
                                    "range": {"startIndex": abs_start, "endIndex": abs_end},
                                    "textStyle": {"italic": True},
                                    "fields": "italic",
                                }
                            }
                        )
                cursor = p_end

            elif block_type in ("bullets", "numbered_list"):
                items = block.get("items", [])
                if not items:
                    continue
                list_start = cursor
                for item in items:
                    item_text = str(item) + "\n"
                    requests.append(
                        {"insertText": {"location": {"index": cursor}, "text": item_text}}
                    )
                    cursor += len(item_text)
                list_end = cursor
                preset = (
                    "BULLET_DISC_CIRCLE_SQUARE"
                    if block_type == "bullets"
                    else "NUMBERED_DECIMAL_NESTED"
                )
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {"startIndex": list_start, "endIndex": list_end},
                            "bulletPreset": preset,
                        }
                    }
                )

            elif block_type == "table":
                t_headers = block.get("headers", [])
                t_rows = block.get("rows", [])
                if not t_headers:
                    continue
                num_cols = len(t_headers)
                num_rows = 1 + len(t_rows)
                requests.append(
                    {
                        "insertTable": {
                            "rows": num_rows,
                            "columns": num_cols,
                            "location": {"index": cursor},
                        }
                    }
                )
                # Flush pending requests before table manipulation
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []

                # Re-read doc to find the table
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                # Find the LAST table (the one we just inserted)
                table_element = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_element = elem

                if table_element:
                    table = table_element["table"]
                    all_table_rows = [t_headers] + t_rows
                    cell_inserts: List[tuple] = []
                    for ri, row_data in enumerate(all_table_rows):
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
                                cell_text = str(cell_val)
                                if cell_text:
                                    cell_inserts.append((cell_idx, cell_text))
                    cell_inserts.sort(key=lambda x: x[0], reverse=True)
                    for cell_idx, cell_text in cell_inserts:
                        requests.append(
                            {"insertText": {"location": {"index": cell_idx}, "text": cell_text}}
                        )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []

                    # Bold header row
                    doc_state2 = docs_service.documents().get(documentId=doc_id).execute()
                    table_elem2 = None
                    for elem in doc_state2.get("body", {}).get("content", []):
                        if "table" in elem:
                            table_elem2 = elem
                    if table_elem2 and table_elem2["table"].get("tableRows"):
                        header_row = table_elem2["table"]["tableRows"][0]
                        for hcell in header_row.get("tableCells", []):
                            for para in hcell.get("content", []):
                                si_val = para.get("startIndex", 0)
                                ei_val = para.get("endIndex", si_val)
                                if ei_val > si_val:
                                    requests.append(
                                        {
                                            "updateTextStyle": {
                                                "range": {
                                                    "startIndex": si_val,
                                                    "endIndex": ei_val,
                                                },
                                                "textStyle": {"bold": True},
                                                "fields": "bold",
                                            }
                                        }
                                    )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []

                # Re-read to update cursor
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                body_content = doc_state.get("body", {}).get("content", [])
                if body_content:
                    last_elem = body_content[-1]
                    cursor = last_elem.get("endIndex", cursor) - 1
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": "\n"}}
                )
                cursor += 1

        print(f"  Section {si + 1}/{len(sections)}: {heading[:50]}...")

    # 3. Execute remaining batch requests
    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()

    # 4. Insert table of contents
    if include_toc:
        insert_toc(docs_service, doc_id)

    # 5. Share and organize
    from cmo_agent.google_auth import ensure_drive_folder, move_file_to_folder, share_file_restricted

    share_file_restricted(drive_service, doc_id)

    folder_id = ensure_drive_folder(drive_service)
    if folder_id:
        move_file_to_folder(drive_service, doc_id, folder_id)

    docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return {"status": "created", "google_docs_url": docs_url, "google_docs_id": doc_id}


def insert_toc(docs_service, doc_id: str) -> None:
    """Insert a linked table of contents at the beginning of the doc."""
    doc = docs_service.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])

    headings: List[Dict[str, Any]] = []
    for elem in body_content:
        if "paragraph" not in elem:
            continue
        para = elem["paragraph"]
        style = para.get("paragraphStyle", {})
        named_style = style.get("namedStyleType", "")
        heading_id = style.get("headingId", "")
        if not named_style.startswith("HEADING_") or not heading_id:
            continue
        level = int(named_style.replace("HEADING_", ""))
        if level > 3:
            continue
        text = ""
        for el in para.get("elements", []):
            text += el.get("textRun", {}).get("content", "")
        text = text.strip()
        if text:
            headings.append({"text": text, "level": level, "heading_id": heading_id})

    if not headings:
        return

    toc_title = "Table of Contents\n"
    toc_tip = (
        "For page numbers: select this TOC, delete it, then "
        "Insert > Table of contents > With page numbers.\n"
    )
    entry_lines = [h["text"] + "\n" for h in headings]
    separator = "\n"
    toc_text = toc_title + toc_tip + "".join(entry_lines) + separator

    requests: List[Dict[str, Any]] = [
        {"insertText": {"location": {"index": 1}, "text": toc_text}},
    ]

    # Style title
    title_start = 1
    title_end = title_start + len(toc_title)
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {"startIndex": title_start, "endIndex": title_end},
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "spaceBelow": {"magnitude": 4, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceBelow",
            }
        }
    )
    requests.append(
        {
            "updateTextStyle": {
                "range": {"startIndex": title_start, "endIndex": title_end - 1},
                "textStyle": {
                    "bold": True,
                    "fontSize": {"magnitude": 16, "unit": "PT"},
                },
                "fields": "bold,fontSize",
            }
        }
    )

    # Style tip line
    tip_start = title_end
    tip_end = tip_start + len(toc_tip)
    requests.append(
        {
            "updateParagraphStyle": {
                "range": {"startIndex": tip_start, "endIndex": tip_end},
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "spaceBelow": {"magnitude": 6, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceBelow",
            }
        }
    )
    requests.append(
        {
            "updateTextStyle": {
                "range": {"startIndex": tip_start, "endIndex": tip_end - 1},
                "textStyle": {
                    "italic": True,
                    "fontSize": {"magnitude": 9, "unit": "PT"},
                    "foregroundColor": {
                        "color": {"rgbColor": {"red": 0.6, "green": 0.6, "blue": 0.6}}
                    },
                },
                "fields": "italic,fontSize,foregroundColor",
            }
        }
    )

    # Style each entry
    entry_cursor = tip_end
    for h in headings:
        entry_text = h["text"] + "\n"
        entry_start = entry_cursor
        entry_end = entry_cursor + len(entry_text) - 1

        if entry_end > entry_start:
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": entry_start,
                            "endIndex": entry_start + len(entry_text),
                        },
                        "paragraphStyle": {
                            "namedStyleType": "NORMAL_TEXT",
                            "spaceAbove": {"magnitude": 2, "unit": "PT"},
                            "spaceBelow": {"magnitude": 2, "unit": "PT"},
                            "indentStart": {
                                "magnitude": 18 * (h["level"] - 1),
                                "unit": "PT",
                            },
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow,indentStart",
                    }
                }
            )

            style_fields = "fontSize,link"
            text_style: Dict[str, Any] = {
                "fontSize": {"magnitude": 11, "unit": "PT"},
                "link": {"headingId": h["heading_id"]},
            }
            if h["level"] == 1:
                text_style["bold"] = True
                style_fields += ",bold"

            requests.append(
                {
                    "updateTextStyle": {
                        "range": {"startIndex": entry_start, "endIndex": entry_end},
                        "textStyle": text_style,
                        "fields": style_fields,
                    }
                }
            )

        entry_cursor += len(entry_text)

    docs_service.documents().batchUpdate(
        documentId=doc_id, body={"requests": requests}
    ).execute()
    print(f"  TOC inserted with {len(headings)} entries")


# ── Main ───────────────────────────────────────────────────────────

def main() -> None:
    from googleapiclient.discovery import build

    # Use OAuth token directly (service account lacks Docs API permission)
    oauth_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", "")

    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive.file",
    ]

    if not oauth_path or not Path(oauth_path).exists():
        print("ERROR: GOOGLE_OAUTH_TOKEN_PATH not set or file not found.")
        sys.exit(1)

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    credentials = Credentials.from_authorized_user_file(oauth_path, SCOPES)
    if credentials.expired and credentials.refresh_token:
        print("Refreshing OAuth token...")
        credentials.refresh(Request())
        Path(oauth_path).write_text(credentials.to_json())
        print("Token refreshed.")

    if not credentials.valid:
        print("ERROR: OAuth token is invalid and cannot be refreshed.")
        sys.exit(1)

    docs_service = build("docs", "v1", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    print("Building document structure...")
    structure = build_structure()
    print(f"  {len(structure['sections'])} sections")

    print("Creating Google Doc...")
    result = build_google_doc(docs_service, drive_service, structure)

    if result["status"] == "created":
        print(f"\nGoogle Doc created successfully!")
        print(f"  URL: {result['google_docs_url']}")
    else:
        print(f"\nFailed: {result}")


if __name__ == "__main__":
    main()
