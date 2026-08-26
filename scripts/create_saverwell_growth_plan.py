#!/usr/bin/env python3
"""Create Google Doc: Saverwell Revenue & Monetization Plan

Run:  python scripts/create_saverwell_growth_plan.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive",
]


def get_services():
    from googleapiclient.discovery import build
    from cmo_agent.google_auth import get_google_credentials

    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json")
    )
    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        raise RuntimeError("No Google credentials found.")

    docs = build("docs", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return docs, drive


# ── sanitize em/en dashes ──
def clean(text: str) -> str:
    return (
        text.replace("\u2014", " - ")
        .replace("\u2013", " - ")
        .replace("\u2014", " - ")
    )


# ── helpers ──
def insert_text(index: int, text: str) -> dict:
    return {"insertText": {"location": {"index": index}, "text": text}}


def style_range(start: int, end: int, style_name: str) -> dict:
    return {
        "updateParagraphStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "paragraphStyle": {"namedStyleType": style_name},
            "fields": "namedStyleType",
        }
    }


def bold_range(start: int, end: int) -> dict:
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"bold": True},
            "fields": "bold",
        }
    }


def bullet_range(start: int, end: int) -> dict:
    return {
        "createParagraphBullets": {
            "range": {"startIndex": start, "endIndex": end},
            "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
        }
    }


def numbered_range(start: int, end: int) -> dict:
    return {
        "createParagraphBullets": {
            "range": {"startIndex": start, "endIndex": end},
            "bulletPreset": "NUMBERED_DECIMAL_ALPHA_ROMAN",
        }
    }


def font_family_range(start: int, end: int, family: str) -> dict:
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"fontFamily": family},
            "fields": "fontFamily",
        }
    }


def font_size_range(start: int, end: int, size_pt: float) -> dict:
    return {
        "updateTextStyle": {
            "range": {"startIndex": start, "endIndex": end},
            "textStyle": {"fontSize": {"magnitude": size_pt, "unit": "PT"}},
            "fields": "fontSize",
        }
    }


def insert_table(index: int, rows: int, cols: int) -> dict:
    return {
        "insertTable": {
            "rows": rows,
            "columns": cols,
            "location": {"index": index},
        }
    }


# ── Segment accumulator ──

segments: list = []


def add_title(text: str) -> None:
    segments.append({"text": clean(text) + "\n", "style": "TITLE"})


def add_h1(text: str) -> None:
    segments.append({"text": clean(text) + "\n", "style": "HEADING_1"})


def add_h2(text: str) -> None:
    segments.append({"text": clean(text) + "\n", "style": "HEADING_2"})


def add_h3(text: str) -> None:
    segments.append({"text": clean(text) + "\n", "style": "HEADING_3"})


def add_para(text: str) -> None:
    segments.append({"text": clean(text) + "\n", "style": "NORMAL_TEXT"})


def add_bold_para(label: str, text: str) -> None:
    segments.append(
        {
            "text": clean(label + text) + "\n",
            "style": "NORMAL_TEXT",
            "bold_end": len(clean(label)),
        }
    )


def add_bullet(text: str) -> None:
    segments.append(
        {"text": clean(text) + "\n", "style": "NORMAL_TEXT", "bullet": True}
    )


def add_numbered(text: str) -> None:
    segments.append(
        {"text": clean(text) + "\n", "style": "NORMAL_TEXT", "numbered": True}
    )


def add_checkbox(text: str) -> None:
    segments.append(
        {
            "text": clean("[ ] " + text) + "\n",
            "style": "NORMAL_TEXT",
            "bullet": True,
        }
    )


def add_hr() -> None:
    segments.append({"text": "\n", "style": "NORMAL_TEXT"})


def add_table_as_text(headers: list, rows: list) -> None:
    header_line = " | ".join(headers)
    segments.append(
        {
            "text": clean(header_line) + "\n",
            "style": "NORMAL_TEXT",
            "bold_end": len(clean(header_line)),
        }
    )
    for row in rows:
        segments.append(
            {"text": clean(" | ".join(str(c) for c in row)) + "\n", "style": "NORMAL_TEXT"}
        )


def build_content() -> None:
    """Populate segments list with the entire document content."""
    add_title("Saverwell Revenue & Monetization Plan")

    # ── Context ──────────────────────────────────────────────────────
    add_h1("Context")
    add_para(
        "Saverwell has 2,007 indexed pages, 1,989 merchants across "
        "118,589 unique store locations, 29 live guides, "
        "28 protection articles, full GA4 tracking, Customer.io email, "
        "and an affiliate research pipeline. The frontend (saverwell-consumer) "
        "already renders affiliate disclosure banners, comparison table CTAs, "
        "and affiliate click tracking. But zero revenue is flowing because:"
    )
    add_numbered(
        "No partner contracts are signed yet (6 direct partnerships pending)"
    )
    add_numbered(
        "Only AT&T and Verizon affiliate applications submitted "
        "(156 merchant pages have zero affiliate links)"
    )
    add_numbered(
        "No admin-configurable partner promotion system exists "
        "(the Lovable admin has no partner_promotions table or UI)"
    )
    add_numbered(
        "Two key partners (AHS, AARP) have no guide content at all"
    )
    add_numbered(
        "Traffic is under 5K/month - the content and monetization "
        "need to launch together"
    )

    add_bold_para(
        "The goal: ",
        "Build a complete, launch-ready monetization system where activating "
        "any partner is a single admin toggle. When contracts close and "
        "traffic grows, revenue starts immediately with no additional "
        "engineering work.",
    )

    add_hr()

    # ── Part 1 ───────────────────────────────────────────────────────
    add_h1("Part 1: The Monetization System (Infrastructure)")
    add_para(
        "This is the most critical piece. Without this, every partner "
        "activation requires custom code changes. With it, any partner "
        "can go live in minutes."
    )

    add_h2("1A. Supabase partner_promotions Table")
    add_para("A new table that decouples partner offers from hardcoded content:")

    schema_fields = [
        "id (UUID, PK)",
        'partner_name (text) - "SelectQuote", "ADT", "Hear.com", etc.',
        'partner_slug (text, unique) - "selectquote", "adt", "hearcom"',
        'promotion_type (enum) - "cta_banner", "comparison_highlight", "click_to_call", "lead_gen_form"',
        'headline (text) - "Have Medicare Questions?"',
        'body_text (text) - "Talk to a licensed advisor at no cost."',
        'cta_text (text) - "Call Now" or "Get a Free Quote"',
        "cta_url (text, nullable) - empty until contract closes",
        "cta_phone (text, nullable) - for click-to-call partners like SelectQuote",
        'target_guide_categories (text[]) - ["medicare", "insurance", "medical-alerts"]',
        "target_guide_slugs (text[]) - optional override for specific guides",
        'target_page_types (text[]) - ["guide", "merchant", "protection", "dma"]',
        'position (enum) - "above_fold", "after_overview", "after_comparison", "end_of_article", "sidebar"',
        "display_order (int) - priority when multiple promotions match",
        "is_active (boolean, default false) - THE TOGGLE. False until contract closes.",
        "start_date (timestamp, nullable) - for time-boxed promos (e.g., Medicare AEP)",
        "end_date (timestamp, nullable)",
        'commission_type (text) - "cpl", "cpa", "cps", "recurring"',
        'estimated_commission (text) - "$50-200/lead", "$5-20/mo"',
        "created_at, updated_at (timestamps)",
    ]
    for field in schema_fields:
        add_bullet(field)

    add_bold_para(
        "How it works: ",
        "The consumer frontend queries this table for active promotions "
        "matching the current page's category/slug. When is_active = true "
        "and cta_url is populated, the promotion renders. Otherwise, nothing "
        "shows. The admin can:",
    )
    add_bullet("Seed all 6 partner records NOW (inactive, no URLs)")
    add_bullet("Fill in cta_url/cta_phone when a contract closes")
    add_bullet("Toggle is_active to go live instantly")
    add_bullet(
        "Set start_date/end_date for seasonal promos (Medicare AEP: Oct 15 - Dec 7)"
    )

    add_h2("1B. Admin Tool Extension (seniorsaveradmin)")
    add_bold_para("New admin page: ", "/admin/partner-promotions")

    add_table_as_text(
        ["Feature", "Description"],
        [
            [
                "List view",
                "All partner promotions with name, type, target categories, active status toggle",
            ],
            [
                "Edit view",
                "Edit headline, body, CTA text, CTA URL/phone, target categories/slugs, position, dates",
            ],
            [
                "Active toggle",
                "Inline switch to activate/deactivate any promotion instantly",
            ],
            [
                "Preview",
                "Show what the promotion looks like on a guide page before activating",
            ],
        ],
    )

    add_bold_para(
        "Modified page: ",
        '/admin/merchants/{id} - add "Partner Promotion" section',
    )
    add_bullet("Link to any partner_promotions records for this merchant")
    add_bullet("Quick-create promotion from merchant edit page")

    add_bold_para(
        "Spec deliverable: ",
        "Claude Code will produce a complete Lovable-ready spec document "
        "(Supabase table SQL, TypeScript interfaces, component structure, "
        "query patterns, wireframe descriptions) that the user can hand to "
        "Lovable for implementation.",
    )

    add_h2("1C. Consumer Frontend Rendering (saverwell-consumer)")
    add_bold_para("New component: ", "PartnerPromotion.tsx")
    add_bullet("Accepts guideCategory, guideSlug, pageType, position props")
    add_bullet(
        "Queries partner_promotions table for matching active promotions"
    )
    add_bullet("Renders based on promotion_type:")
    add_bullet(
        "  cta_banner: colored callout box with headline, body, CTA button"
    )
    add_bullet(
        '  click_to_call: phone icon + number + "Call Now" button (for SelectQuote)'
    )
    add_bullet(
        "  comparison_highlight: highlighted row in comparison table (for ADT, Hear.com)"
    )
    add_bullet(
        "  lead_gen_form: inline form or redirect CTA (for Insurify)"
    )
    add_bullet("Fires affiliateClick GA4 event on CTA interaction")
    add_bullet(
        "Appends UTM: utm_source=saverwell&utm_medium={pageType}"
        "&utm_content={slug}&utm_subid={partnerSlug}"
    )
    add_bullet(
        'Includes rel="sponsored nofollow noopener" on all partner links'
    )
    add_bullet(
        "Shows affiliate disclosure banner when any active promotion renders"
    )

    add_bold_para(
        "Integration points on guide pages ", "(GuideArticle.tsx):"
    )
    add_numbered('After overview section - position: "after_overview"')
    add_numbered('After comparison table - position: "after_comparison"')
    add_numbered(
        'End of article (before related guides) - position: "end_of_article"'
    )

    add_bold_para(
        "Integration points on merchant pages ", "(MerchantPage.tsx):"
    )
    add_bullet(
        "The existing affiliate CTA system already handles this via "
        "affiliate_url on the merchant record"
    )
    add_bullet("No changes needed for merchant-level affiliate links")

    add_h2("1D. Tracking & Attribution")

    add_bold_para("Already wired ", "(no changes needed):")
    add_bullet(
        "affiliateClick GA4 event on guide comparison CTAs and merchant CTAs"
    )
    add_bullet("UTM utility functions (utm-utils.ts)")
    add_bullet("swTrack global tracking object")

    add_bold_para("New tracking for partner promotions:", "")
    add_bullet(
        "partnerPromoView event: fires when a PartnerPromotion component "
        "renders (impression tracking)"
    )
    add_bullet(
        "partnerPromoClick event: fires on CTA click, includes partner_slug, "
        "promotion_type, guide_slug, position"
    )
    add_bullet("These map to the existing swTrack.customEvent() method")

    add_bold_para("Revenue dashboard ", "(Google Sheet via Sheets Agent):")
    add_bullet("Partner promotion impressions by guide (from GA4)")
    add_bullet("Partner promotion clicks by guide (from GA4)")
    add_bullet(
        "Click-through rate by partner, position, and guide category"
    )
    add_bullet(
        "Affiliate platform revenue (manual import from Impact/CJ until API integration)"
    )

    add_hr()

    # ── Part 2 ───────────────────────────────────────────────────────
    add_h1("Part 2: Content Architecture")

    add_h2("Partner-to-Content Map")
    add_para(
        "Each partner needs content that naturally leads users to the "
        "partner's offering. The CTA (Call to Action) should be the logical "
        "next step after consuming helpful content."
    )

    add_table_as_text(
        [
            "Partner",
            "Revenue Model",
            "Content That Exists",
            "Content to Create",
            "User Journey",
        ],
        [
            [
                "SelectQuote",
                "CPL (Cost Per Lead), click-to-call, $50-200/lead",
                "9 Medicare guides (live)",
                "None needed",
                'Read Medicare guide -> "Still have questions? Talk to a licensed advisor" -> click-to-call',
            ],
            [
                "ADT",
                "CPA (Cost Per Acquisition)/recurring, $5-20/mo",
                "2 medical alert guides (live)",
                "3-5 more guides (fall detection, wearable, GPS, no-monthly-fee, Medicare coverage)",
                'Read comparison guide -> see ADT in comparison table -> "Check Rates" CTA',
            ],
            [
                "Hear.com",
                "CPS (Cost Per Sale), $75-300/sale",
                "1 hearing aid guide (live)",
                "2-3 more (OTC under $500, Medicare coverage, price guide)",
                'Read savings guide -> "Save with our partner Hear.com" -> CTA',
            ],
            [
                "Insurify",
                "CPL, $20-150/lead",
                "1 auto+home insurance guide (live)",
                "0-1 more (bundling guide)",
                'Read insurance guide -> "Compare rates from top carriers" -> Insurify redirect',
            ],
            [
                "AHS",
                "CPA, $30-75/sale",
                "None",
                "3 new guides (home warranty explained, vs. insurance, choosing a plan)",
                'Read explainer -> "Get a free home warranty quote" -> AHS redirect',
            ],
            [
                "AARP",
                "CPA, $5-15/signup",
                "None",
                "2 new guides (membership value breakdown, discount list)",
                'Read AARP savings content -> "Join AARP and start saving" -> signup',
            ],
            [
                "AT&T",
                "CPA, $25-100/activation",
                "2 phone guides (live)",
                "2-4 more (free phones, flip phones, hearing loss, two-line plans)",
                'Read comparison guide -> see AT&T in table -> "Check Plans" CTA',
            ],
            [
                "Verizon",
                "CPA, $25-100/activation",
                "2 phone guides (live)",
                "2-4 more (same as AT&T)",
                "Same as AT&T",
            ],
        ],
    )

    add_h2("New Content Queue (Priority Order)")

    add_bold_para("Must-have ", "(partners with no content):")
    add_numbered(
        "home-warranty-explained - Home Warranty Plans: What They Cover, "
        "What They Cost, and What to Watch For"
    )
    add_numbered(
        "home-warranty-vs-home-insurance - Home Warranty vs. Home Insurance: "
        "What's the Difference?"
    )
    add_numbered(
        "best-home-warranty-seniors - Home Warranty for Seniors: How to "
        "Choose the Right Plan (affiliate tier)"
    )
    add_numbered(
        "is-aarp-membership-worth-it - Is an AARP Membership Worth It? "
        "A Savings Breakdown"
    )
    add_numbered(
        "aarp-discounts-complete-list - AARP Discounts: The Complete List for 2026"
    )

    add_bold_para("High-value expansion ", "(more surfaces for existing partners):")
    add_numbered(
        "medical-alert-fall-detection - Best Medical Alert Systems with Fall Detection"
    )
    add_numbered(
        "medical-alert-watches - Best Medical Alert Watches (Wearable)"
    )
    add_numbered(
        "medicare-medical-alert-coverage - Medical Alert Systems: Does Medicare Cover Them?"
    )
    add_numbered(
        "medical-alert-no-monthly-fee - Medical Alert Systems with No Monthly Fee"
    )
    add_numbered(
        "otc-hearing-aids-under-500 - Best OTC Hearing Aids Under $500"
    )
    add_numbered(
        "medicare-hearing-aids-coverage - Does Medicare Cover Hearing Aids? "
        "(And What Actually Helps)"
    )
    add_numbered(
        "free-phones-seniors - Free Cell Phones for Seniors (Government Programs)"
    )
    add_numbered(
        "best-flip-phones-seniors - Best Flip Phones for Seniors Who Want Simple"
    )

    add_bold_para("Total: ", "5 must-have + 8 expansion = 13 new guides")

    add_h2("Cross-Linking Strategy")
    add_para(
        "Every content type should funnel users toward monetized pages:"
    )

    add_bold_para("DMA Pages (361):", "")
    add_bullet("Link to merchant pages in that DMA (affiliate CTAs)")
    add_bullet('Link to relevant guides ("Read our Medicare Guide")')

    add_bold_para("Merchant Pages (156+):", "")
    add_bullet("Affiliate CTA (when affiliate_url is active)")
    add_bullet("Link to related guides (page_related_guide_slugs)")
    add_bullet("Link to protection articles (page_related_protection_slugs)")

    add_bold_para("Guide Articles (48 live + 13 new):", "")
    add_bullet("Partner promotions (from partner_promotions table)")
    add_bullet("Comparison table affiliate CTAs")
    add_bullet("Related guides (cross-pollination within guide network)")
    add_bullet("Link to relevant merchant pages")

    add_bold_para("Protection Articles (28 live):", "")
    add_bullet(
        'Cross-link to relevant guides ("Learn how to save on Medicare")'
    )
    add_bullet("Link to relevant merchant pages")

    add_bold_para("Email Drips (40+ templates):", "")
    add_bullet("CTA drives to guide pages (NOT direct affiliate links)")
    add_bullet("Guide pages have partner promotions")

    add_para(
        "This creates a content web where every page view has a path to "
        "monetization, but the user never feels sold to - they feel guided."
    )

    add_hr()

    # ── Part 3 ───────────────────────────────────────────────────────
    add_h1("Part 3: Affiliate Merchant Pipeline (156 Pages)")
    add_para(
        "Separate from the 6 direct partnerships, the 156 merchant pages "
        "represent a bulk affiliate opportunity."
    )

    add_h2("Current State")
    add_bullet(
        "Affiliate Research Sheet exists (1oOd2TzHn-DRAOPnGE9II2RG74HuPK_7k3fPnALOTRf4) "
        "with 166+ merchants"
    )
    add_bullet(
        "Only AT&T and Verizon applications submitted on Impact/CJ"
    )
    add_bullet(
        "Scripts ready: cj_merchant_discovery.py, impact_merchant_discovery.py, "
        "populate_affiliate_urls.py"
    )

    add_h2("Execution Plan")

    add_bold_para("Step 1: Populate the research sheet ", "(Claude Code)")
    add_bullet("Run impact_merchant_discovery.py against all 166+ merchants")
    add_bullet("Run cj_merchant_discovery.py against all merchants")
    add_bullet(
        "Sheet gets populated with: which network has each merchant, "
        "commission rates, application URLs"
    )

    add_bold_para(
        "Step 2: Generate prioritized application list ", "(Claude Code)"
    )
    add_bullet(
        "Sort by: High-priority category first (Telecom, Health, Electronics, "
        "Insurance), then by commission rate"
    )
    add_bullet("Generate application copy for each program")
    add_bullet(
        "Output: a checklist the user can work through to submit applications"
    )

    add_bold_para(
        "Step 3: Submit applications ", "(Human - requires W9/business entity)"
    )
    add_bullet("User works through the prioritized list")
    add_bullet(
        "Updates approval_status in the research sheet as applications go out"
    )

    add_bold_para("Step 4: Wire approved affiliate URLs ", "(Claude Code)")
    add_bullet(
        "Run populate_affiliate_urls.py to sync approved URLs from sheet to Supabase"
    )
    add_bullet(
        "Merchant pages automatically render affiliate CTAs "
        "(the consumer frontend already handles this)"
    )
    add_bullet("Run affiliate_link_monitor.py weekly for health checks")

    add_h2("Guide-Level Affiliate Links")
    add_para(
        "For guides with comparison tables (medical alerts, phones, hearing aids), "
        "the comparison table rows need affiliate URLs per provider:"
    )
    add_bold_para(
        "Step 1: ",
        "Run build_guide_affiliate_map.py to map guide comparison providers "
        "to affiliate merchants",
    )
    add_bold_para(
        "Step 2: ",
        "Run populate_guide_affiliate_links.py to inject affiliate URLs "
        "into comparison table JSONB",
    )
    add_bold_para(
        "Step 3: ",
        'Consumer frontend already renders "Check Rates" buttons for rows '
        "with affiliate_url",
    )

    add_hr()

    # ── Part 4 ───────────────────────────────────────────────────────
    add_h1("Part 4: Traffic Engine")
    add_para(
        "Under 5K/month means all the monetization infrastructure in the "
        "world won't matter without traffic. These are the traffic sources, "
        "ordered by speed-to-impact."
    )

    add_h2("4A. SEO (Primary, Long-Term)")
    add_para(
        "The 29 live guides + 13 new guides target high-volume keywords:"
    )
    add_bullet("Medicare keywords: 100K+ monthly searches")
    add_bullet("Medical alert comparisons: 20K+ monthly searches")
    add_bullet("Phone plans for seniors: 30K+ monthly searches")
    add_bullet("Hearing aid savings: 15K+ monthly searches")

    add_bold_para(
        "What Claude Code does: ",
        "Every new guide follows the existing GuideArticle content model "
        "with seo_title, seo_description, seo_keywords, structured FAQ "
        "(FAQ schema), and comparison tables (product schema). The "
        "Cloudflare Worker already renders JSON-LD for SEO bots.",
    )

    add_bold_para(
        "Cross-linking amplifies SEO: ",
        "Every guide links to related guides, merchant pages, and protection "
        "articles. This creates topical authority clusters that Google rewards.",
    )

    add_h2("4B. Email Drip Campaigns (Medium-Term)")
    add_para(
        "40+ Customer.io templates already exist. The drip sequences need "
        "to route subscribers to monetized guides:"
    )
    add_bullet(
        "Medicare series (11 templates) -> Medicare guide pages "
        "(SelectQuote click-to-call promotion when active)"
    )
    add_bullet(
        "Medical alert series -> medical alert guides (ADT promotion when active)"
    )
    add_bullet(
        "Phone plan series -> phone guides (AT&T/Verizon comparison table CTAs)"
    )
    add_bullet("New: AHS home warranty drip (3 templates for new guides)")
    add_bullet("New: AARP drip (2 templates for new guides)")

    add_bold_para(
        "Key principle: ",
        'Emails NEVER contain affiliate links. The CTA is always "Read the '
        'full guide" which drives to a web page where the partner promotion '
        "renders. This keeps emails clean and compliant.",
    )

    add_h2("4C. Charlie List Warm-Up (Medium-Term, High Volume)")
    add_para(
        "250K legacy contacts. Existing plan: 8-week phased warm-up via SendGrid."
    )
    add_bullet(
        "Funnel: SendGrid -> Saverwell subscribe form -> Customer.io -> "
        "guide drips -> monetized pages"
    )
    add_bullet(
        "Human prerequisites: SendGrid setup, updates.saverwell.com domain, "
        "legal consent review"
    )
    add_bullet(
        "Claude Code builds: the n8n workflow, email templates, batch "
        "segmentation logic"
    )

    add_h2("4D. Embeddable Widget (Distribution Play)")
    add_para(
        "Already built in cloudflare-worker/. Needs deployment + partner outreach."
    )
    add_bullet(
        "Widget shows local discounts on partner websites (financial advisors, "
        "Medicare brokers, senior centers)"
    )
    add_bullet(
        "Each interaction drives to merchant pages (with affiliate CTAs) "
        "and guide pages"
    )
    add_bullet("Generates backlinks (SEO boost) + qualified traffic")

    add_h2("4E. Internal Cross-Linking (Immediate, Free)")
    add_para(
        "Every page should link to every other relevant page. This keeps "
        "users on-site longer and exposes them to more monetization surfaces:"
    )
    add_bullet("DMA pages -> merchant pages + guides")
    add_bullet(
        "Merchant pages -> related guides + protection articles + other merchants"
    )
    add_bullet("Guides -> related guides + merchant pages")
    add_bullet("Protection articles -> relevant guides")
    add_bullet("Homepage -> featured merchants + guides")

    add_hr()

    # ── Part 5 ───────────────────────────────────────────────────────
    add_h1("Part 5: Partner Activation Playbooks")
    add_para(
        "When a contract closes, here's exactly what happens for each partner. "
        "The goal: activation in under 1 hour because all infrastructure "
        "is pre-built."
    )

    add_h2("SelectQuote (Medicare Click-to-Call)")
    add_numbered(
        "Admin fills in cta_phone field with SelectQuote's tracking phone number"
    )
    add_numbered("Admin sets cta_url if a web landing page is also needed")
    add_numbered("Admin toggles is_active = true")
    add_numbered(
        'All 9 Medicare guides immediately show: "Have Medicare questions? '
        'Talk to a licensed advisor" + phone button'
    )
    add_numbered(
        "Every call is tracked via partnerPromoClick event with "
        'partner_slug: "selectquote"'
    )

    add_h2("ADT (Medical Alert Devices)")
    add_numbered("Admin fills in cta_url with ADT's affiliate/partner URL")
    add_numbered("Admin toggles is_active = true")
    add_numbered(
        "Medical alert guides show ADT as highlighted partner in "
        "comparison tables + banner CTA"
    )
    add_numbered("Clicks tracked via affiliateClick event")

    add_h2("Hear.com (Hearing Aids)")
    add_numbered("Admin fills in cta_url with Hear.com's partner URL")
    add_numbered("Admin toggles is_active = true")
    add_numbered(
        'Hearing aid guides show "Save with our partner Hear.com" CTA'
    )
    add_numbered("Clicks tracked via affiliateClick event")

    add_h2("Insurify (Auto+Home Insurance)")
    add_numbered("Admin fills in cta_url with Insurify's quote page URL")
    add_numbered("Admin toggles is_active = true")
    add_numbered(
        'Insurance guides show "Compare Rates from Top Carriers" CTA'
    )
    add_numbered("Clicks tracked via affiliateClick event")

    add_h2("AHS (Home Warranty)")
    add_numbered("New home warranty guides must be published first (Part 2)")
    add_numbered("Admin fills in cta_url with AHS quote page URL")
    add_numbered("Admin toggles is_active = true")
    add_numbered(
        'Home warranty guides show "Get a Free Home Warranty Quote" CTA'
    )

    add_h2("AARP (Membership)")
    add_numbered("New AARP guides must be published first (Part 2)")
    add_numbered("Admin fills in cta_url with AARP join/signup URL")
    add_numbered("Admin toggles is_active = true")
    add_numbered('AARP guides show "Join AARP and Start Saving" CTA')
    add_numbered(
        "Cross-links from merchant pages where AARP discounts are referenced"
    )

    add_hr()

    # ── Part 6 ───────────────────────────────────────────────────────
    add_h1("Part 6: Execution Roadmap")
    add_para(
        "Everything Claude Code does, sequenced by dependency. Human "
        "actions are called out explicitly."
    )

    add_h2("Phase 1: Foundation Sprint (Weeks 1-2)")
    add_para(
        "Three parallel workstreams launch simultaneously. Each maps to "
        "an independent sub-agent."
    )

    add_bold_para("Agent A: Infrastructure ", "(SQL + Specs + Code)")
    add_bullet("Supabase migration SQL for partner_promotions")
    add_bullet("Seed 6 partner records")
    add_bullet("Lovable admin spec doc")
    add_bullet("PartnerPromotion.tsx React component")
    add_bullet("GuideArticle.tsx integration code")
    add_bullet("GA4 event definitions")
    add_bullet("Revenue dashboard (Google Sheet)")
    add_bullet("Google Doc version of this plan")

    add_bold_para("Agent B: Content ", "(Writer Agent)")
    add_bullet("3 AHS home warranty guides (must-have)")
    add_bullet("2 AARP guides (must-have)")
    add_bullet("3-5 medical alert expansion guides")
    add_bullet("2-3 hearing aid expansion guides")
    add_bullet("2-4 phone plan expansion guides")
    add_bullet("Email template variants for all new guides")
    add_bullet("Cross-link updates")

    add_bold_para("Agent C: Affiliates ", "(Discovery Scripts)")
    add_bullet("Run impact_merchant_discovery.py (166+ merchants)")
    add_bullet("Run cj_merchant_discovery.py")
    add_bullet("Populate research sheet with network data")
    add_bullet("Generate prioritized application checklist")
    add_bullet("Draft application copy per program")
    add_bullet("Build guide affiliate map")

    add_para(
        "No dependencies between these three - all run in parallel."
    )

    add_bold_para("Human actions ", "(while agents work):")
    add_checkbox("Run Supabase migration (when Agent A delivers SQL)")
    add_checkbox("Hand Lovable spec to Lovable for admin UI build")
    add_checkbox(
        "Submit affiliate applications from Agent C's prioritized list"
    )
    add_checkbox(
        "Review guide content from Agent B (or trust Writer Agent quality)"
    )

    add_h2("Phase 2: Integration (Weeks 3-4)")
    add_para("Two parallel workstreams. Depends on Phase 1 outputs.")

    add_bold_para("Agent D: Email + Drips", "")
    add_bullet("New Customer.io drips for AHS guides (3)")
    add_bullet("New Customer.io drips for AARP guides (2)")
    add_bullet(
        "Update existing drip sequences to route to monetized guides"
    )
    add_bullet(
        "All CTAs drive to web pages (no affiliate links in emails)"
    )

    add_bold_para("Agent E: Affiliate Sync", "")
    add_bullet(
        "Run populate_affiliate_urls.py as approvals arrive from Impact/CJ"
    )
    add_bullet(
        "Run populate_guide_affiliate_links.py to inject URLs into guide "
        "comparison tables"
    )
    add_bullet("Verify merchant pages render affiliate CTAs")
    add_bullet("Set up weekly link health monitoring")

    add_bold_para("Human actions:", "")
    add_checkbox(
        "Deploy updated consumer frontend (with PartnerPromotion component)"
    )
    add_checkbox("Deploy updated Cloudflare Worker")
    add_checkbox("Continue submitting affiliate applications")
    add_checkbox("Update approval_status in research sheet")

    add_h2("Phase 3: Traffic Activation (Weeks 4-8)")
    add_para("Two parallel workstreams for traffic generation.")

    add_bold_para("Agent F: Charlie List Campaign", "")
    add_bullet("Charlie list n8n workflow build")
    add_bullet("3-touch email templates")
    add_bullet("Batch segmentation logic")
    add_bullet("Deliverability monitoring n8n workflow")

    add_bold_para("Agent G: Widget + Cross-Linking", "")
    add_bullet("Widget deployment documentation")
    add_bullet(
        "Audit all cross-links (guides <-> merchants <-> DMA <-> protection)"
    )
    add_bullet("Fill cross-link gaps (page_related_guide_slugs, etc.)")
    add_bullet(
        "SEO audit: verify JSON-LD, meta tags, sitemaps for new guides"
    )

    add_bold_para("Human actions:", "")
    add_checkbox(
        "Set up SendGrid account + updates.saverwell.com domain"
    )
    add_checkbox("Legal consent review for Charlie list")
    add_checkbox("Deploy embeddable widget (npx wrangler deploy)")
    add_checkbox(
        "Identify initial widget distribution partners "
        "(financial advisors, Medicare brokers)"
    )

    add_h2("Phase 4: Optimization (Ongoing from Week 8)")
    add_checkbox(
        "A/B test partner CTA copy (create variant records in "
        "partner_promotions, toggle between them)"
    )
    add_checkbox(
        "Medicare AEP hub content (ready by September for Oct 15 - Dec 7 "
        "enrollment window)"
    )
    add_checkbox(
        "Interactive calculator specs (Social Security optimizer, "
        "phone bill savings)"
    )
    add_checkbox("Revenue dashboard updates with actual conversion data")
    add_checkbox(
        "Partner promotion performance analysis -> adjust headline, "
        "CTA text, position"
    )

    add_hr()

    # ── Part 7 ───────────────────────────────────────────────────────
    add_h1("Part 7: UX Principles for Monetization")
    add_para(
        "These principles ensure revenue integration doesn't degrade the "
        "user experience that builds trust."
    )

    add_numbered(
        "Monetization is a service, not an interruption. Every partner CTA "
        "is positioned as the natural next step after helpful content. "
        '"Have Medicare questions? Talk to a licensed advisor" feels like '
        "help, not an ad."
    )
    add_numbered(
        "Not every page is monetized. Protection articles remain purely "
        "informational (trust-building). Finance guides are informational. "
        "Only pages where commercial intent naturally exists get partner CTAs."
    )
    add_numbered(
        "Disclosure is clear and upfront. The teal affiliate disclosure "
        "banner appears at the top of any page with active partner "
        "promotions. Users trust transparency."
    )
    add_numbered(
        "One partner per guide section, max. No guide should feel like an "
        "ad gallery. One well-placed CTA per content section. The comparison "
        "table can have multiple providers (each with their own affiliate "
        "link), but banner CTAs are limited to one per position."
    )
    add_numbered(
        "Mobile-first. Most senior users browse on phones. Partner CTAs "
        "must be thumb-friendly, load fast, and not cause layout shift. "
        "The PartnerPromotion component renders responsively."
    )
    add_numbered(
        "Email stays clean. Emails drive to web content where monetization "
        "lives. No affiliate links in emails. This keeps deliverability "
        "high and compliant with CAN-SPAM."
    )

    add_hr()

    # ── Progress Tracking ────────────────────────────────────────────
    add_h1("Progress Tracking")
    add_para("After implementation begins, progress will be tracked in:")
    add_bullet(
        "Memory file: memory/saverwell_monetization_progress.md "
        "(persistent across Claude Code sessions)"
    )
    add_bullet("Google Sheet: Revenue tracking dashboard (built in Phase 1)")
    add_bullet("This plan file: checkboxes updated as phases complete")

    add_hr()

    # ── Key Files ────────────────────────────────────────────────────
    add_h1("Key Files")

    add_h2("CMO Agent (this repo)")
    add_table_as_text(
        ["File", "Role"],
        [
            [
                "data/saverwell/content_expansion_strategy.md",
                "Master content roadmap",
            ],
            [
                "data/saverwell/product_roadmap_ideas.md",
                "10 product ideas",
            ],
            [
                "data/saverwell/charlie_list_outbound_plan.md",
                "Charlie list warm-up plan",
            ],
            [
                "scripts/cj_merchant_discovery.py",
                "CJ affiliate batch discovery",
            ],
            [
                "scripts/impact_merchant_discovery.py",
                "Impact affiliate batch discovery",
            ],
            [
                "scripts/populate_affiliate_urls.py",
                "Sync affiliate URLs to Supabase",
            ],
            [
                "scripts/build_guide_affiliate_map.py",
                "Map guide providers to affiliates",
            ],
            [
                "scripts/populate_guide_affiliate_links.py",
                "Inject affiliate URLs into guides",
            ],
            [
                "scripts/affiliate_link_monitor.py",
                "Weekly link health checks",
            ],
            [
                "src/cmo_agent/content/guide.py",
                "GuideArticle content model",
            ],
        ],
    )

    add_h2("Consumer Frontend (saverwell-consumer)")
    add_table_as_text(
        ["File", "Role"],
        [
            [
                "src/pages/GuideArticle.tsx",
                "Guide page rendering + affiliate CTAs",
            ],
            [
                "src/pages/MerchantPage.tsx",
                "Merchant page rendering + affiliate CTAs",
            ],
            [
                "src/components/partner/PartnerWelcomeOverlay.tsx",
                "Partner landing overlay",
            ],
            [
                "src/lib/guide-queries.ts",
                "Guide Supabase queries",
            ],
            [
                "src/lib/merchant-page-queries.ts",
                "Merchant Supabase queries",
            ],
            [
                "src/lib/utm-utils.ts",
                "UTM parameter utilities",
            ],
            [
                "src/lib/partner-config.ts",
                "Partner registry",
            ],
        ],
    )

    add_h2("Admin Tool (seniorsaveradmin)")
    add_table_as_text(
        ["File", "Role"],
        [
            [
                "src/pages/MerchantDetail.tsx",
                "Merchant editing (has affiliate_url, affiliate_network)",
            ],
            [
                "src/pages/GuideArticleEdit.tsx",
                "Guide editing (needs Promotions tab addition)",
            ],
            [
                "src/types/database.ts",
                "TypeScript interfaces (needs partner_promotions)",
            ],
            [
                "src/lib/guideQueries.ts",
                "Guide CRUD queries",
            ],
        ],
    )

    add_bold_para(
        "Affiliate Research Sheet ID: ",
        "1oOd2TzHn-DRAOPnGE9II2RG74HuPK_7k3fPnALOTRf4",
    )

    add_hr()

    # ── Verification Plan ────────────────────────────────────────────
    add_h1("Verification Plan")
    add_table_as_text(
        ["What", "How to Verify"],
        [
            [
                "Partner promotions render",
                "Seed a test promotion with is_active=true, load a matching guide page, confirm CTA appears",
            ],
            [
                "Admin toggle works",
                "Toggle is_active in admin, refresh guide page, confirm CTA appears/disappears",
            ],
            [
                "GA4 tracking fires",
                "Open GA4 DebugView, click a partner CTA, confirm partnerPromoClick event with correct params",
            ],
            [
                "Affiliate links work",
                "Click a merchant page affiliate CTA, confirm redirect to affiliate URL with UTM params",
            ],
            [
                "Comparison table CTAs",
                'Load a guide with comparison_table affiliate URLs, click "Check Rates", confirm tracking + redirect',
            ],
            [
                "Email drips route correctly",
                "Send test email, click CTA, confirm landing on correct guide page with active promotion",
            ],
            [
                "Affiliate discovery scripts",
                "Run against 5 test merchants, verify research sheet gets populated",
            ],
            [
                "Affiliate URL sync",
                "Add a test URL in research sheet, run populate_affiliate_urls.py, verify Supabase merchant record updates",
            ],
            [
                "Cross-links work",
                "Load a guide page, verify related guides/merchants/protection articles link correctly",
            ],
            [
                "New guide content",
                "Load each new guide (AHS, AARP), verify all sections render, FAQ works, comparison table if applicable",
            ],
        ],
    )

    # ── First Session Deliverables ───────────────────────────────────
    add_h1("First Session Deliverables")
    add_para(
        "When implementation begins, the first session launches 3 parallel "
        "sub-agents immediately:"
    )

    add_bold_para("Agent A (Infrastructure):", "")
    add_numbered(
        "Create memory/saverwell_monetization_progress.md for persistent tracking"
    )
    add_numbered(
        "Write Supabase migration SQL for partner_promotions table + seed data"
    )
    add_numbered(
        "Write complete Lovable admin spec document (TypeScript interfaces, "
        "component wireframes, queries)"
    )
    add_numbered(
        "Write PartnerPromotion.tsx component for saverwell-consumer"
    )
    add_numbered("Write GuideArticle.tsx integration diff")
    add_numbered(
        "Create the Google Doc version of this plan via Docs Agent"
    )

    add_bold_para("Agent B (Content):", "")
    add_numbered("Draft home-warranty-explained guide via Writer Agent")
    add_numbered("Draft home-warranty-vs-home-insurance guide")
    add_numbered("Draft best-home-warranty-seniors guide")
    add_numbered("Draft is-aarp-membership-worth-it guide")
    add_numbered("Draft aarp-discounts-complete-list guide")
    add_numbered("Publish all 5 to Supabase with monetization fields")

    add_bold_para("Agent C (Affiliates):", "")
    add_numbered(
        "Run impact_merchant_discovery.py against all 166+ merchants"
    )
    add_numbered("Run cj_merchant_discovery.py against all merchants")
    add_numbered("Generate prioritized application checklist")
    add_numbered("Run build_guide_affiliate_map.py for existing guides")


def main() -> None:
    docs_service, drive_service = get_services()

    # Create blank doc
    doc = (
        docs_service.documents()
        .create(body={"title": "Saverwell Revenue & Monetization Plan"})
        .execute()
    )
    doc_id = doc["documentId"]
    print(f"Created doc: {doc_id}")

    # Build content
    build_content()

    # Insert all text then apply styles
    requests: List[dict] = []
    style_requests: List[dict] = []
    idx = 1  # Google Docs body starts at index 1

    for seg in segments:
        text = seg["text"]
        start = idx
        end = idx + len(text)

        requests.append(insert_text(idx, text))

        style_name = seg.get("style", "NORMAL_TEXT")
        style_requests.append(style_range(start, end, style_name))

        bold_end = seg.get("bold_end")
        if bold_end and bold_end > 0:
            style_requests.append(bold_range(start, start + bold_end))

        if seg.get("bullet"):
            style_requests.append(bullet_range(start, end))

        if seg.get("numbered"):
            style_requests.append(numbered_range(start, end))

        if seg.get("code"):
            style_requests.append(font_family_range(start, end - 1, "Courier New"))
            style_requests.append(font_size_range(start, end - 1, 9))

        idx = end

    # Send in batches
    BATCH_SIZE = 50
    for i in range(0, len(requests), BATCH_SIZE):
        batch = requests[i : i + BATCH_SIZE]
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": batch},
        ).execute()
        print(
            f"  Inserted text batch {i // BATCH_SIZE + 1}/"
            f"{(len(requests) + BATCH_SIZE - 1) // BATCH_SIZE}"
        )

    for i in range(0, len(style_requests), BATCH_SIZE):
        batch = style_requests[i : i + BATCH_SIZE]
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": batch},
        ).execute()
        print(
            f"  Applied style batch {i // BATCH_SIZE + 1}/"
            f"{(len(style_requests) + BATCH_SIZE - 1) // BATCH_SIZE}"
        )

    # Share with specific users + move to CMO Agent folder
    from cmo_agent.google_auth import (
        share_file_restricted,
        ensure_drive_folder,
        move_file_to_folder,
    )

    share_file_restricted(drive_service, doc_id)

    try:
        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)
    except Exception as e:
        print(f"Warning: could not move to folder: {e}")

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    print(f"\nDone! Document URL:\n{url}")


if __name__ == "__main__":
    main()
