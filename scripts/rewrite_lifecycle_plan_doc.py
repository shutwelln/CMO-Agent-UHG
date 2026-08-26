#!/usr/bin/env python3
"""Rewrite the Saverwell Lifecycle Marketing Plan Google Doc.

Replaces the entire document with the new 3-Journey + Broadcast Engine
architecture. This is Deliverable A of the Lifecycle Marketing Overhaul.

Usage:
    python scripts/rewrite_lifecycle_plan_doc.py
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

DOC_ID = "1C8yuO1FYQx92hFe-qV2W5evNgEi0-qBzDhkDFBhsKqs"

# The DOC_STRUCTURE format expected by DocsAgent._update_google_doc()
DOC_STRUCTURE = {
    "title": "Saverwell Lifecycle Marketing Plan",
    "sections": [
        # --- HEADER ---
        {
            "heading": "Saverwell Lifecycle Marketing Plan",
            "heading_level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Strategic Architecture for Email Lifecycle Marketing",
                },
                {"type": "paragraph", "text": "Last updated: March 2026"},
                {"type": "paragraph", "text": "Status: Implementation in progress"},
            ],
        },
        # --- EXECUTIVE SUMMARY ---
        {
            "heading": "Executive Summary",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Saverwell's lifecycle marketing system converts website subscribers into engaged readers who return to the site regularly, where affiliate and partner conversions drive revenue. The system uses three Customer.io journeys and one n8n-powered broadcast engine to deliver ~100 articles across 9 content verticals.",
                },
                {
                    "type": "paragraph",
                    "text": "The architecture prioritizes engagement over monetization in the first 8 weeks, then transitions to personalized content delivery with light-touch partner recommendations on affiliate-enabled articles (22 of ~100).",
                },
                {
                    "type": "paragraph",
                    "text": "Key metrics: subscribers active after 90 days, email click-through rate, website return visits from email, and affiliate conversion rate on guide pages.",
                },
            ],
        },
        # --- SYSTEM ARCHITECTURE ---
        {
            "heading": "System Architecture",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "The lifecycle system has three sequential journeys and one ongoing broadcast engine:",
                },
                {
                    "type": "paragraph",
                    "text": "Journey 1: Welcome Flow - 5 emails over 14 days. Pure value delivery. Zero monetization. Introduces all three content pillars (savings, protection, guides) and the weekly digest format.",
                },
                {
                    "type": "paragraph",
                    "text": "Journey 2: Core Foundations - 6 emails over 6 weeks (Tuesdays). The best protection and guide content, hand-picked to showcase content breadth. Includes 2 affiliate-enabled articles (phones, medical alerts) as the first monetization-adjacent touchpoints after 5 weeks of pure value.",
                },
                {
                    "type": "paragraph",
                    "text": "Personalized Broadcast Engine - 2x/week (Tuesday + Thursday), ongoing. Selects from 80+ articles based on subscriber interests, engagement signals, seasonal windows, and articles already received. Light-touch partner recommendations appear only on the 22 affiliate-enabled articles.",
                },
                {
                    "type": "paragraph",
                    "text": "Weekly Digest - Monday. Curated roundup of the week's best content. One rotating partner spotlight per digest.",
                },
                {
                    "type": "paragraph",
                    "text": "Medicare Seasonal Overlay - September through December, Wednesday. 11 weeks of Annual Enrollment Period (AEP) content. Adds a third weekly email during this window.",
                },
                {
                    "type": "paragraph",
                    "text": "Journey 3: Re-engagement - Fires when a subscriber has not opened or clicked any email in 30 days. 3 emails over 14 days. If no response after an additional 30-day wait, the subscriber is sunset and suppressed. Total time from inactivity detection to sunset: 44 days.",
                },
            ],
        },
        # --- CONTENT INVENTORY ---
        {
            "heading": "Content Inventory",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "The system distributes approximately 100 unique articles across 9 content verticals. 22 articles are affiliate-enabled with partner recommendations.",
                },
                {
                    "type": "table",
                    "rows": [
                        ["Vertical", "Articles", "Affiliate-Enabled", "Email Templates"],
                        ["Fraud and Protection", "~28", "0", "8 built (drip_protection)"],
                        ["Medicare and Health", "17", "0", "11 built (medicare_guide)"],
                        ["Insurance", "9", "6", "0"],
                        ["Medical Alerts", "6", "5", "0"],
                        ["Phones and Telecom", "4", "3", "0"],
                        ["Hearing Aids", "3", "2", "0"],
                        ["Finance and Retirement", "~39", "3", "0"],
                        ["Family Caregiving", "4", "0", "0"],
                        ["Discounts and Shopping", "3", "3", "0"],
                        ["TOTAL", "~100+", "22", "19 built"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Content is tracked in the Content Queue Google Sheet with article-level metadata including vertical, priority, seasonal boost windows, monetization tier, affiliate disclosure status, and drip assignment.",
                },
            ],
        },
        # --- CORE FOUNDATIONS SEQUENCE ---
        {
            "heading": "Core Foundations: The 6-Email Sequence",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Core Foundations replaces the original 8-email Protection Drip. It combines the highest-impact protection content with the highest-engagement guide content so subscribers experience multiple verticals early.",
                },
                {
                    "type": "table",
                    "rows": [
                        ["Week", "Article", "Vertical", "Rationale"],
                        [
                            "1",
                            "Safe Online Shopping Tips",
                            "Protection",
                            "Highest-engagement protection article. Immediately practical.",
                        ],
                        [
                            "2",
                            "Password Safety Guide",
                            "Protection",
                            "Foundational security. Universal relevance.",
                        ],
                        [
                            "3",
                            "Senior Scam Protection Complete Guide",
                            "Protection",
                            "Capstone piece. Covers all scam types. Builds trust.",
                        ],
                        [
                            "4",
                            "Cell Phone Plans for Seniors",
                            "Phones (affiliate)",
                            "First guide vertical. High commercial intent. Introduces savings value prop.",
                        ],
                        [
                            "5",
                            "Medical Alert Systems Guide",
                            "Medical Alerts (affiliate)",
                            "Second guide vertical. High intent for 65+ audience.",
                        ],
                        [
                            "6",
                            "When to Claim Social Security",
                            "Finance",
                            "Universal relevance. Highest traffic article. Establishes financial education positioning.",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Why 6 instead of 8: Gets subscribers to the personalized broadcast engine 2 weeks earlier. The 3 protection articles (weeks 1-3) cover the most critical safety topics. The 3 guide articles (weeks 4-6) showcase content breadth and include 2 affiliate-enabled articles as the first monetization-adjacent touchpoints.",
                },
            ],
        },
        # --- PERSONALIZED BROADCAST ENGINE ---
        {
            "heading": "Personalized Broadcast Engine",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "After Core Foundations, subscribers enter the Personalized Broadcast Engine, which sends 2 emails per week (Tuesday + Thursday) from the full article pool of 80+ articles.",
                },
                {"type": "paragraph", "text": "Content selection logic (n8n workflow):"},
                {
                    "type": "paragraph",
                    "text": "1. Exclude articles already sent (tracked via articles_received_list attribute on the Customer.io profile).",
                },
                {
                    "type": "paragraph",
                    "text": "2. Apply seasonal boost to matching verticals (e.g., Medicare articles get +5 priority during AEP).",
                },
                {
                    "type": "paragraph",
                    "text": "3. Weight by content_interest attribute (derived from signup page URL).",
                },
                {
                    "type": "paragraph",
                    "text": "4. Weight by engagement signals from Customer.io (which articles the subscriber clicked, which guide pages they visited on the site). This is a Phase 3 enhancement that requires the Customer.io JavaScript snippet.",
                },
                {
                    "type": "paragraph",
                    "text": "5. Select the highest-priority article not yet sent to this subscriber.",
                },
                {
                    "type": "paragraph",
                    "text": "Tuesday broadcasts rotate across all verticals. Thursday broadcasts are weighted toward the subscriber's demonstrated interests. This ensures variety while respecting engagement patterns.",
                },
            ],
        },
        # --- MONETIZATION ---
        {
            "heading": "Monetization Strategy",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "The monetization approach is deliberately conservative. The business survives on referrals and on-site conversions, not email revenue. Emails exist to drive engaged readers to the website.",
                },
                {
                    "type": "paragraph",
                    "text": "Months 1-2 (Welcome + Core Foundations): ZERO monetization. Pure value delivery and trust building.",
                },
                {
                    "type": "paragraph",
                    "text": "Month 3+ (Broadcast Engine): When the engine sends one of the 22 affiliate-enabled articles, a 'Recommended by Saverwell' box appears below the main CTA. This is the only monetization element in content emails.",
                },
                {
                    "type": "paragraph",
                    "text": "Weekly Digest: A rotating 'This Week's Partner' section after the guide cards. One partner per digest. Same light-touch format.",
                },
                {
                    "type": "paragraph",
                    "text": "What does NOT go in emails: No affiliate links in email body text (CTAs drive to the website where affiliate links live). No monetization in Welcome or Core Foundations sequences. No more than 1 partner mention per email. No 'sponsored by' framing on content emails.",
                },
                {
                    "type": "table",
                    "rows": [
                        ["Partner", "Category", "Revenue Model", "Status"],
                        [
                            "SelectQuote",
                            "Medicare guides",
                            "$50-200/lead",
                            "Inactive (pending contract)",
                        ],
                        ["ADT", "Medical alerts", "$5-20/mo recurring", "Inactive"],
                        ["Hear.com", "Hearing aids", "$75-300/sale", "Inactive"],
                        ["Insurify", "Auto/home/life insurance", "$50-150/lead", "Inactive"],
                        ["AHS", "Home warranty", "$30-75/sale", "Inactive"],
                        ["AARP", "AARP/discounts", "$5-15/signup", "Inactive"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "The partner recommendation template is built and ready. Partners activate automatically when contracts close.",
                },
            ],
        },
        # --- SUBSCRIBER JOURNEY EXAMPLE ---
        {
            "heading": "Subscriber Journey Example",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Jane signs up via saverwell.com/guides/medicare on March 1. Her content_interest is set to 'guides' from the signup URL.",
                },
                {
                    "type": "paragraph",
                    "text": "Weeks 1-2 (Welcome Flow): 5 emails introducing savings, protection, guides, and the digest format. After email 5, lifecycle_stage becomes 'active'.",
                },
                {
                    "type": "paragraph",
                    "text": "Weeks 3-8 (Core Foundations): 6 emails on Tuesdays covering the essential protection and guide content. Monday digest starts in week 3. After email 6, core_foundations_completed becomes true.",
                },
                {
                    "type": "paragraph",
                    "text": "Weeks 9+ (Broadcast Engine): Tuesday and Thursday personalized content. Since Jane signed up via a Medicare page, Thursday broadcasts are weighted toward Medicare and health content. Tuesday broadcasts rotate other verticals. Monday digest continues.",
                },
                {
                    "type": "paragraph",
                    "text": "If Jane is active during AEP (Sep-Dec): A Wednesday Medicare broadcast is added, bringing total emails to 4 per week during the 11-week AEP window.",
                },
                {
                    "type": "paragraph",
                    "text": "If Jane goes inactive for 30 days: The Re-engagement journey fires with 3 emails over 14 days. If no response after an additional 30-day wait, Jane is sunset and suppressed.",
                },
                {
                    "type": "paragraph",
                    "text": "Total structured content before personalization: 11 emails across 8 weeks. Time from signup to first monetization-adjacent content: 5 weeks (Core Foundations email 4).",
                },
            ],
        },
        # --- EMAIL FREQUENCY ---
        {
            "heading": "Email Frequency by Lifecycle Stage",
            "heading_level": 2,
            "content": [
                {
                    "type": "table",
                    "rows": [
                        ["Stage", "Duration", "Emails/Week", "Total Emails"],
                        ["Welcome Flow", "2 weeks", "2-3", "5"],
                        ["Core Foundations", "6 weeks", "2 (Tue + Mon digest)", "12"],
                        ["Broadcast (normal)", "Ongoing", "3 (Tue + Thu + Mon digest)", "3/week"],
                        [
                            "Broadcast (AEP)",
                            "11 weeks (Sep-Dec)",
                            "4 (Tue + Wed + Thu + Mon)",
                            "4/week",
                        ],
                        ["Re-engagement", "2 weeks + 30 day wait", "~0.4", "3"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "Normal steady-state: 3 emails per week (Monday digest, Tuesday broadcast, Thursday broadcast). AEP peak: 4 emails per week for 11 weeks.",
                },
            ],
        },
        # --- UTM AND TRACKING ---
        {
            "heading": "UTM Standards and Tracking",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "All email CTA URLs include standardized UTM parameters:",
                },
                {
                    "type": "paragraph",
                    "text": "utm_source=saverwell, utm_medium=email, utm_campaign={journey_or_broadcast_type}, utm_content={article_slug}",
                },
                {
                    "type": "paragraph",
                    "text": "Campaign values: welcome, core_foundations, guide_broadcast, weekly_digest, medicare_seasonal, reengagement",
                },
                {
                    "type": "paragraph",
                    "text": "UTM bypass for email subscribers: When utm_medium=email is detected on the website, a session cookie (sw_email_subscriber=true) is set. The subscribe gate skips rendering for the rest of the browsing session. This prevents email subscribers from hitting the gate when clicking through from emails.",
                },
                {
                    "type": "paragraph",
                    "text": "Customer.io JavaScript snippet (Phase 3): Tracks page views and events on the website directly into Customer.io profiles. Enables engagement-based personalization in the broadcast engine. Installed via Google Tag Manager.",
                },
            ],
        },
        # --- CUSTOMER.IO CONFIGURATION ---
        {
            "heading": "Customer.io Configuration",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Journeys: 3 (Welcome Flow, Core Foundations, Re-engagement)",
                },
                {
                    "type": "paragraph",
                    "text": "Broadcast templates: 3 (Guide Broadcast, Weekly Digest, Medicare Seasonal)",
                },
                {
                    "type": "paragraph",
                    "text": "Subscription topics: 4 (Savings and Guides, Fraud Protection, Weekly Digest, Product and Marketing)",
                },
                {
                    "type": "paragraph",
                    "text": "Segments: 4 (New Subscribers, Core Foundations Ready, Broadcast Eligible, Inactive 30 Days)",
                },
                {
                    "type": "paragraph",
                    "text": "Full setup instructions are in the Customer.io Setup Guide (data/saverwell/customerio_setup_guide.md).",
                },
            ],
        },
        # --- KEY ATTRIBUTES ---
        {
            "heading": "Key Subscriber Attributes",
            "heading_level": 2,
            "content": [
                {
                    "type": "table",
                    "rows": [
                        ["Attribute", "Set By", "Used By"],
                        [
                            "lifecycle_stage",
                            "n8n Subscribe / Welcome / Re-engagement",
                            "Segment triggers",
                        ],
                        [
                            "welcome_flow_started",
                            "Welcome Flow (after Email 5)",
                            "Core Foundations trigger",
                        ],
                        [
                            "core_foundations_completed",
                            "Core Foundations (after Email 6)",
                            "Broadcast Engine eligibility",
                        ],
                        [
                            "content_interest",
                            "n8n Subscribe (from signup URL)",
                            "Broadcast personalization weighting",
                        ],
                        [
                            "articles_received_list",
                            "Core Foundations + n8n Broadcast",
                            "Dedup (never send same article twice)",
                        ],
                        ["re_engaged", "Re-engagement journey", "Analytics and targeting"],
                    ],
                },
            ],
        },
        # --- IMPLEMENTATION PHASES ---
        {
            "heading": "Implementation Phases",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "MVP (Launch Ready): Welcome flow rebuilt with fixes, Core Foundations journey built, Re-engagement journey built, Broadcast Engine n8n workflow operational. All emails have CAN-SPAM footer, UTM parameters, preheaders, and dark mode support.",
                },
                {
                    "type": "paragraph",
                    "text": "Phase 2 (Content + Digest): Full content library (100+ articles) populated in Content Queue. Subscriber Timeline tab added. Weekly Digest n8n workflow operational.",
                },
                {
                    "type": "paragraph",
                    "text": "Phase 3 (Engagement + Monetization): Customer.io JavaScript snippet installed via GTM. Broadcast engine updated to use engagement signals. UTM bypass implemented on saverwell.com. Documentation fully current.",
                },
                {
                    "type": "paragraph",
                    "text": "Phase 4 (Seasonal, September): Medicare AEP seasonal broadcast workflow built. 11-week Wednesday overlay activated. Medicare content boosted in Content Queue.",
                },
            ],
        },
        # --- WHAT WE ARE NOT DOING ---
        {
            "heading": "What This System Does NOT Include",
            "heading_level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "No behavior-triggered campaign journeys. The broadcast engine naturally adapts to engagement patterns without separate campaigns for each content vertical.",
                },
                {
                    "type": "paragraph",
                    "text": "No separate Expert Guide Series journey. Those 13 articles go into the broadcast pool. The engine delivers them based on priority and interest, not a rigid sequence.",
                },
                {
                    "type": "paragraph",
                    "text": "No affiliate links inside email body text. CTAs drive to the website where affiliate conversions happen. The partner recommendation box is the only monetization element in emails.",
                },
                {
                    "type": "paragraph",
                    "text": "No blocking launch on the Customer.io JavaScript snippet. The broadcast engine works without engagement signals (uses content_interest + articles_received_list + seasonal priority). Engagement signals are a Phase 3 enhancement.",
                },
            ],
        },
        # --- RELATED DELIVERABLES ---
        {
            "heading": "Related Deliverables",
            "heading_level": 2,
            "content": [
                {
                    "type": "table",
                    "rows": [
                        ["Deliverable", "Location"],
                        ["Customer.io Setup Guide", "data/saverwell/customerio_setup_guide.md"],
                        [
                            "Content Queue Google Sheet",
                            "https://docs.google.com/spreadsheets/d/1kSVQwjzXO1R9af55DPSTmhq86ZH12u1ra3fcoll1-xE/edit",
                        ],
                        ["Email Templates", "data/saverwell/email_templates/"],
                        ["Content Queue Population Script", "scripts/populate_content_queue.py"],
                        ["UTM Append Script", "scripts/add_utm_to_templates.py"],
                        [
                            "UTM Bypass Lovable Prompt",
                            "data/saverwell/lovable_ux_prompts/fix_utm_email_bypass_gate.md",
                        ],
                        [
                            "n8n Lifecycle Subscribe Workflow",
                            "https://automation.saverwell.com/workflow/hYsgc6mF8A5gQ0X5",
                        ],
                    ],
                },
            ],
        },
    ],
}


async def main() -> None:
    settings = get_settings()
    db = Database(settings.db_path)
    await db.initialize()

    llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model_writing,
    )
    workspace_mgr = WorkspaceManager(db)
    oauth_token = str(Path(__file__).resolve().parent.parent / "data" / "google-token.json")

    # Initialize DocsAgent with OAuth creds
    docs_agent = DocsAgent(
        llm=llm,
        db=db,
        workspace_manager=workspace_mgr,
        google_credentials_path=oauth_token,
        google_oauth_token_path=oauth_token,
    )

    # Manually init Google services with the correct scopes (bypass DocsAgent's
    # _init_google_services which uses drive.file scope, mismatching the token)
    from googleapiclient.discovery import build as gapi_build

    all_scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/presentations",
    ]
    creds = get_google_credentials(
        oauth_token_path=oauth_token,
        service_account_path="",
        scopes=all_scopes,
    )
    if creds is None:
        print("ERROR: Could not load Google OAuth credentials.")
        print("Run: python scripts/reauth_google_drive.py")
        await db.close()
        sys.exit(1)

    docs_agent._docs_service = gapi_build("docs", "v1", credentials=creds)
    docs_agent._drive_service = gapi_build("drive", "v3", credentials=creds)

    print(f"Rewriting Lifecycle Marketing Plan Google Doc: {DOC_ID}")
    result = docs_agent._update_google_doc(DOC_ID, DOC_STRUCTURE, "saverwell")
    print(f"Result: {result}")
    print(f"\nDoc URL: https://docs.google.com/document/d/{DOC_ID}/edit")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
