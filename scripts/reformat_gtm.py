#!/usr/bin/env python3
"""Re-create Agent Tunnel GTM Google Doc and Slides with improved formatting.

Run:  source .venv/bin/activate && python scripts/reformat_gtm.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cmo_agent.agents.deck import DeckAgent, _get_palette  # noqa: E402
from cmo_agent.agents.docs import DocsAgent  # noqa: E402
from cmo_agent.config import Settings  # noqa: E402
from cmo_agent.db.database import Database  # noqa: E402
from cmo_agent.llm.anthropic import AnthropicLLM  # noqa: E402
from cmo_agent.workspace.manager import WorkspaceManager  # noqa: E402

# ── GTM Document structure (rich format) ────────────────────────────────

GTM_DOC_STRUCTURE = {
    "title": "Agent Tunnel — Go-to-Market Strategy",
    "include_toc": True,
    "sections": [
        # ── Executive Summary ──────────────────────────────────────────
        {
            "heading": "Executive Summary",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Agent Tunnel puts **Claude Code in your pocket** through a secure Mac desktop app with mobile access. The site is **already live at agenttunnel.app** with Stripe payments operational. Our 90-day mission: prove mobile-first developer tools can change how professionals work.",
                },
                {
                    "type": "table",
                    "headers": ["Metric", "Target"],
                    "rows": [
                        ["Paid users", "500"],
                        ["LTV:CAC ratio", "3:1"],
                        ["Monthly recurring revenue", "$7,500"],
                        ["Setup completion rate", "85%+"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Budget:** $500-2,000/month across all channels. **Key Bet:** Mobile productivity beats desktop-bound workflows. Security and simplicity drive adoption over feature complexity.",
                },
                {
                    "type": "paragraph",
                    "text": "**Current Status:** agenttunnel.app is live with Stripe integration (Justin). Codebase is in GitHub for joint development. Lifecycle marketing (Customer.io) and retargeting pixels (GTM) must be operational before any launch traffic is driven — every early visitor is high-value and must be captured.",
                },
            ],
        },
        # ── Product Overview ───────────────────────────────────────────
        {
            "heading": "Product Overview & Competitive Landscape",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Mac desktop app enabling secure smartphone control of Claude Code via **Cloudflare tunnel**. No SSH, no VPN, no exposed ports. Site live at **agenttunnel.app** with Stripe payments. Codebase in GitHub — Nick and Justin developing jointly.",
                },
            ],
        },
        {
            "heading": "Key Differentiators",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "Biometric authentication (Face ID / Touch ID)",
                        "Sub-5-minute setup — install, scan QR, control",
                        "Native mobile experience, not screen sharing",
                        "Enterprise-grade security with zero configuration",
                    ],
                },
            ],
        },
        {
            "heading": "Competitive Analysis",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Competitor", "Pain Point", "Agent Tunnel Advantage"],
                    "rows": [
                        ["SSH Tunnels", "Complex setup, key management, port forwarding", "No terminal config, no key management, no port forwarding"],
                        ["Screen Sharing", "Laggy, desktop-optimized interfaces on mobile", "Native mobile experience, not a laggy remote desktop"],
                        ["Status Quo", "Missing opportunities, inflexible schedules", "Your AI assistant goes where you go"],
                    ],
                },
            ],
        },
        # ── Target Market ──────────────────────────────────────────────
        {
            "heading": "Target Market & ICP",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**Primary ICP:** Busy Claude Code Power Users — professionals aged 28-50, income $75k-200k+, roles including senior developers, tech leads, consultants, and freelancers.",
                },
            ],
        },
        {
            "heading": "Psychographics & Behavioral Indicators",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "Values time over money — willing to pay for convenience",
                        "Security-conscious but not paranoid",
                        "500+ Claude Code sessions in past 90 days",
                        "Active on developer Twitter/Reddit",
                        "Uses productivity tools (Notion, Linear, etc.)",
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
                    "headers": ["Segment", "Estimate", "Notes"],
                    "rows": [
                        ["TAM", "50,000+", "Regular Claude Code users"],
                        ["SAM", "15,000", "Power users (500+ sessions)"],
                        ["SOM", "2,500", "Mobile-productivity-focused professionals"],
                    ],
                },
            ],
        },
        # ── Positioning ────────────────────────────────────────────────
        {
            "heading": "Positioning & Messaging Framework",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**Primary Position:** *Claude Code in your pocket — secure, simple, mobile-first.*",
                },
            ],
        },
        {
            "heading": "Three Value Pillars",
            "level": 2,
            "content": [
                {
                    "type": "numbered_list",
                    "items": [
                        "Security — Cloudflare tunnel encryption, biometric auth, no exposed ports, compliance-friendly",
                        "Simplicity — Install, scan QR, control. Three steps, under 5 minutes. No SSH keys, no VPN.",
                        "Mobility — Work from the couch, coffee shop, kid's soccer game. Full Claude Code access anywhere.",
                    ],
                },
            ],
        },
        {
            "heading": "Messaging by Audience",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**For Busy Professionals:** \"You're at your kid's basketball game. A Slack message pings — there's a bug in production. Open Agent Tunnel, ask Claude to investigate, push the fix. Back to the game before halftime.\"",
                },
                {
                    "type": "paragraph",
                    "text": '**For Security-Conscious Users:** "Cloudflare tunnel means your machine is never directly exposed to the internet. Face ID means only you get in. Enterprise-grade security, zero configuration."',
                },
                {
                    "type": "paragraph",
                    "text": '**For Simplicity Seekers:** "Three steps: Install the app, scan the QR code, start coding from your phone. Setup takes less time than making coffee."',
                },
            ],
        },
        # ── Pricing ────────────────────────────────────────────────────
        {
            "heading": "Pricing Strategy",
            "level": 1,
            "content": [
                {
                    "type": "table",
                    "headers": ["Tier", "Price", "Target", "Positioning"],
                    "rows": [
                        ["Free Trial", "14 days", "All users", "Full access, no credit card"],
                        ["Monthly", "$15/month", "Flexibility seekers", "Cost of two coffee shop visits"],
                        ["Annual", "$150/year", "Committed users", "Less than $3/week"],
                        ["Early Adopter", "$10/month", "First 100 customers", "Locked rate for 12 months"],
                        ["Lifetime", "$500 one-time", "First 50 customers", "Builds committed base"],
                    ],
                },
            ],
        },
        # ── Channel Strategy Summary ───────────────────────────────────
        {
            "heading": "Channel Strategy",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Our channel strategy is organized into **P0 (primary)** and **P1 (secondary)** priorities, optimizing for a $500-2,000/month budget.",
                },
            ],
        },
        {
            "heading": "P0 Channels (Primary Focus)",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Channel", "Budget", "Goal", "Timeline"],
                    "rows": [
                        ["Organic SEO", "$200/month", "20+ high-intent keywords", "3-6 months to ranking"],
                        ["Reddit Organic", "$0 (time)", "4 target subreddits", "Ongoing"],
                        ["Product Hunt", "$300 (one-time)", "Top 5 product of day", "Month 2"],
                        ["Hacker News", "$0", "Front page story", "Month 2-3"],
                    ],
                },
            ],
        },
        {
            "heading": "P1 Channels (Secondary)",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "Twitter/X Organic ($100/month) — 40% educational, 30% product, 20% engagement, 10% promo",
                        "LinkedIn Content ($50/month) — Professional use cases and productivity wins",
                        "Developer Community Engagement ($0) — Discord servers, Slack groups, indie hacker forums",
                    ],
                },
            ],
        },
        # ── 90-Day Execution Plan ──────────────────────────────────────
        {
            "heading": "90-Day Execution Plan",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "The following sections break the channel strategy into **four execution phases** with specific deliverables, agent assignments, automation workflows, and human actions required. Every tactic maps to a CMO Agent capability — every strategy below can be executed through the system.",
                },
                {
                    "type": "paragraph",
                    "text": "**Product:** Agent Tunnel — Mac desktop app for secure mobile access to Claude Code via Cloudflare tunnel. **Site:** agenttunnel.app (live, Stripe operational). **Codebase:** GitHub (joint Nick + Justin). **Budget:** $500-2,000/month. **Target:** 500 paid users, $7,500 MRR. **Timeline:** 90 days.",
                },
                {
                    "type": "paragraph",
                    "text": "**Critical constraint:** Lifecycle marketing (Customer.io) and retargeting pixels (GTM) must be fully operational before driving any launch traffic. Every early visitor is high-value — we cannot afford to lose them to missing capture infrastructure.",
                },
            ],
        },
        # ── Phase 0: Foundation & Launch Readiness ─────────────────────
        {
            "heading": "Phase 0: Foundation & Launch Readiness (Days 1-10)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Everything depends on this phase. No channel is activated until analytics, lifecycle emails, and retargeting pixels are fully operational. The site is already live — this phase focuses on instrumenting it for capture and conversion.",
                },
            ],
        },
        {
            "heading": "0A. Workspace & Brand Configuration",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Register **agent_tunnel** as a workspace in the CMO Agent database with proper sources, keywords, and Slack channel.",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "Create workspace agent_tunnel named 'Agent Tunnel' with type owned_brand and Slack channel #agent-tunnel",
                        "Set keywords: Claude Code, mobile coding, remote development, Cloudflare tunnel, AI coding assistant, mobile IDE, SSH alternative, Claude mobile, code from phone, developer tools",
                        "Store in knowledge base: Product is a Mac desktop app at $15/mo. Three value pillars: Security (Cloudflare tunnel), Simplicity (3-step setup), Mobility (phone access to Claude Code). Primary ICP: busy professionals 28-50 who use Claude Code.",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Agent mapping:** Orchestrator direct tools (add_source, workspace config), Knowledge Base Agent (memory_store). **Dependencies:** None — this is step zero.",
                },
            ],
        },
        {
            "heading": "0B. Measurement & Analytics Foundation",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Design the entire tracking architecture. The site is live — this must be deployed to agenttunnel.app before any traffic is driven.",
                },
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent", "Description"],
                    "rows": [
                        ["Measurement framework", "Marketing Analytics", "Business goals: trial signups, paid conversions, retention, referrals. Tech stack: GA4, Customer.io, Beehiiv, Stripe"],
                        ["Event taxonomy", "Marketing Analytics", "GA4 events: page_view, sign_up_start, sign_up_complete, trial_start, qr_code_scanned, first_session, upgrade_to_paid, referral_sent, referral_converted, churn"],
                        ["UTM governance", "Marketing Analytics", "Sources: reddit, twitter, linkedin, google, beehiiv, producthunt, hackernews, email. Mediums: organic, social, cpc, retargeting, newsletter, community"],
                        ["KPI dashboard", "Marketing Analytics + Sheets", "Daily/weekly signups, trial-to-paid rate, MRR, churn rate, CAC by channel, LTV, referral rate — as a Google Sheet"],
                        ["Tracking implementation spec", "Marketing Analytics", "dataLayer push events, GA4 config, enhanced conversions for Stripe, cross-domain tracking"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 1-3. **Dependencies:** 0A must complete first.",
                },
            ],
        },
        {
            "heading": "0C. Google Tag Manager & Retargeting Pixels",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**This is launch-critical.** GTM container and all retargeting pixels must be live on agenttunnel.app before any traffic is driven. Every early visitor must be capturable for retargeting.",
                },
                {
                    "type": "table",
                    "headers": ["Deliverable", "Owner", "Description"],
                    "rows": [
                        ["GTM container setup", "Justin/Nick", "Create GTM account, install GTM snippet on agenttunnel.app (in GitHub codebase)"],
                        ["GA4 tag in GTM", "Justin/Nick", "Configure GA4 measurement ID, page_view tracking, enhanced measurement"],
                        ["Meta Pixel in GTM", "Nick", "Install Meta Pixel via GTM. Events: PageView, Lead (signup), StartTrial, Purchase (paid conversion)"],
                        ["Google Ads remarketing tag", "Nick", "Install Google Ads tag via GTM for display retargeting audiences"],
                        ["LinkedIn Insight Tag", "Nick", "Install via GTM for LinkedIn retargeting (professional audience)"],
                        ["Customer.io site tracking", "Nick", "Install Customer.io JavaScript snippet via GTM for on-site behavioral tracking"],
                        ["Conversion event mapping", "Marketing Analytics Agent", "Map GTM dataLayer events to each pixel: signup -> Lead/StartTrial across all platforms"],
                        ["GTM preview/debug verification", "Justin/Nick", "Use GTM preview mode to verify all tags fire correctly on signup/trial/purchase flows"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 2-5. **Dependencies:** 0B (event taxonomy defines what to track). **Gate:** No channel activation until GTM is verified firing on all conversion events.",
                },
            ],
        },
        {
            "heading": "0D. Customer.io Integration via n8n",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**This is launch-critical.** Customer.io must be receiving user data and triggering lifecycle emails before any traffic is driven. We already have a starting n8n workflow that integrates with Customer.io via API — build everything from there.",
                },
                {
                    "type": "table",
                    "headers": ["n8n Workflow", "Description"],
                    "rows": [
                        ["Signup -> Customer.io", "Webhook receives new_signup from agenttunnel.app -> Customer.io Track API: identify person with email, UTM source/medium/campaign, signup_date, plan=trial"],
                        ["Trial activation event", "Webhook receives first_mobile_session -> Customer.io Track API: track event 'first_session_completed' with device_type, session_duration"],
                        ["Stripe -> Customer.io (paid)", "Stripe webhook: checkout.session.completed -> Customer.io Track API: update person paid=true, plan=monthly/annual, track event 'upgraded_to_paid'"],
                        ["Stripe -> Customer.io (churn)", "Stripe webhook: customer.subscription.deleted -> Customer.io Track API: update person paid=false, track event 'churned', trigger win-back segment"],
                        ["Daily metrics -> Slack", "Cron 8am -> Customer.io Reporting API: fetch signup/conversion counts -> format summary -> post to #agent-tunnel Slack"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Nick** — Create Customer.io account, generate API credentials (Track API key + App API key), add to n8n credentials store. **Justin** — Add signup webhook to agenttunnel.app codebase (POST to n8n webhook URL on new user creation with email + UTM params).",
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 3-7. **Dependencies:** 0B (event taxonomy), 0C (site tracking). **Gate:** Must be fully operational before Phase 1 channels drive traffic.",
                },
            ],
        },
        {
            "heading": "0E. Email Lifecycle System (Launch-Ready)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "**This is launch-critical.** All lifecycle email flows must be built in Customer.io and ready to fire before any channel drives traffic. Every trial user must immediately enter the onboarding sequence.",
                },
                {
                    "type": "paragraph",
                    "text": "**Lifecycle flows to design (Lifecycle Marketing Agent):**",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "Trial onboarding (5-email sequence: welcome, setup guide, first win, social proof, upgrade nudge)",
                        "Trial-to-paid conversion (4 emails: Day 5/10/13/14 triggers)",
                        "Win-back (3 emails: 7/30/60 days post-churn)",
                        "Engagement/retention (2 emails: no_session_7d, low_usage triggers)",
                        "Segmentation: trial_active, trial_inactive, trial_expiring, paid_active, paid_at_risk, churned",
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Email copy (all via Writer Agent):** 5 onboarding + 4 conversion + 3 win-back + 2 engagement = **14 emails total**.",
                },
                {
                    "type": "paragraph",
                    "text": "**Nick** — Build campaign flows in Customer.io UI (segments, triggers, delays). Agent produces all email copy and subject lines; human configures the actual campaigns in Customer.io.",
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 5-10. **Dependencies:** 0D (Customer.io integration). **Gate:** Onboarding sequence must fire correctly for a test user before any channel activation.",
                },
            ],
        },
        {
            "heading": "0F. Landing Page CRO (Site Already Live)",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": "The site is **already live at agenttunnel.app** with Stripe payments operational (Justin). This phase focuses on optimizing conversion, not building from scratch. The codebase is in GitHub for joint development.",
                },
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["Funnel architecture audit (current site -> optimization opportunities)", "Acquisition Agent"],
                        ["CRO copy recommendations (Hero, How It Works, Security, Use Cases, FAQ, CTA)", "Writer Agent"],
                        ["Hero image (developer on phone with code visible, 1792x1024)", "Visual Agent"],
                        ["Product demo motion graphic (3-step setup flow, 15 seconds)", "Motion Graphics Agent"],
                        ["A/B headline test design (benefit-led vs. pain-led vs. curiosity-led)", "Acquisition Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Justin/Nick** — Implement copy and design changes to agenttunnel.app via GitHub. Agent produces the content; humans merge PRs.",
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 3-8. **Dependencies:** 0B, 0C (tracking must be in place to measure CRO impact).",
                },
            ],
        },
        # ── Phase 1: Content & Organic Engines ─────────────────────────
        {
            "heading": "Phase 1: Content & Organic Engines (Days 5-21)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Four organic channels running in parallel — SEO for long-term compounding, Reddit for community trust, Twitter/X for brand awareness, LinkedIn for professional credibility. These channels only activate after Phase 0 gates are met (GTM verified, Customer.io lifecycle emails operational).",
                },
            ],
        },
        {
            "heading": "1A. SEO & Content Marketing",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["Keyword architecture (5 clusters)", "SEO & AEO Agent"],
                        ["Page type governance (5 page types)", "SEO & AEO Agent"],
                        ["8 SEO content briefs", "SEO & AEO Agent"],
                        ["AEO optimization spec", "SEO & AEO Agent"],
                        ["Keyword ranking tracker (Google Sheet)", "SEO & AEO + Sheets Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Ongoing content production:** Blog posts 2/week via Writer Agent (following SEO briefs), blog images 1 per post via Visual Agent, 3 comparison pages (vs. SSH, vs. VPN, vs. screen sharing) via Writer Agent.",
                },
                {
                    "type": "paragraph",
                    "text": "**Automation:** Blog publish notification workflow (Slack + social queue + RSS trigger). **Timeline:** Days 5-21, then ongoing through Day 90. **Justin/Nick** — Publish blog posts to website CMS (or build blog into agenttunnel.app via GitHub).",
                },
            ],
        },
        {
            "heading": "1B. Reddit Organic",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["Reddit engagement strategy (9 subreddits)", "Social Media Manager"],
                        ["5 Reddit reply templates", "Writer Agent"],
                        ["Show r/ClaudeAI launch post", "Writer Agent"],
                        ["Weekly value posts (ongoing)", "Writer Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Automation:** Add r/ClaudeAI, r/ChatGPTPro, r/MacApps, r/webdev, r/programming, r/sideproject as monitoring sources. Build n8n workflow scanning for \"Claude Code mobile/phone/remote\" every 4 hours -> Slack alert.",
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 5-14 setup, then ongoing. **Nick/Justin** — Must post to Reddit personally (automated posting violates TOS). Agent drafts all content.",
                },
            ],
        },
        {
            "heading": "1C. Twitter/X Organic",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["Twitter/X content strategy", "Social Media Manager"],
                        ["30-day content calendar", "Social Media Manager"],
                        ["Daily tweets (5-7/week)", "Writer Agent"],
                        ["Weekly threads", "Writer Agent"],
                        ["Social images (2/week)", "Visual Agent"],
                        ["Short demo clips (2/month)", "Motion Graphics Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 5-14 setup, ongoing. **Nick/Justin** — Create @AgentTunnel account, post all content manually. Agent drafts everything.",
                },
            ],
        },
        {
            "heading": "1D. LinkedIn",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["LinkedIn strategy", "Social Media Manager"],
                        ["LinkedIn posts (3-4/week)", "Writer Agent"],
                        ["LinkedIn article (1/month)", "Writer + Docs Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 7-14 setup, ongoing. **Nick/Justin** — Post from personal LinkedIn profiles.",
                },
            ],
        },
        # ── Phase 2: Launch Events ─────────────────────────────────────
        {
            "heading": "Phase 2: Launch Events (Days 14-35)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Newsletter launch alongside two high-impact launch events — Product Hunt and Hacker News — timed for maximum overlap. Lifecycle emails and retargeting are already operational from Phase 0, so every visitor from these launches is captured.",
                },
            ],
        },
        {
            "heading": "2A. Newsletter / Beehiiv",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["Newsletter strategy", "Lifecycle Marketing"],
                        ["Beehiiv setup spec (Google Doc)", "Docs Agent"],
                        ["Weekly newsletter (ongoing)", "Writer Agent"],
                        ["Welcome email", "Writer Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Automation:** Blog-to-newsletter workflow + Beehiiv subscriber -> Customer.io sync. **Timeline:** Days 14-21. **Nick** — Create Beehiiv account, configure publication settings, connect to Customer.io via n8n.",
                },
            ],
        },
        {
            "heading": "2B. Product Hunt Launch",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["PH launch strategy (hour-by-hour playbook)", "Social Media Manager"],
                        ["PH listing copy (tagline, description, maker comment)", "Writer Agent"],
                        ["5 PH gallery images (1270x760)", "Visual Agent"],
                        ["10 launch day tweets", "Writer Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Automation:** PH launch day Slack reminders every 2 hours + Beehiiv blast trigger. **Timeline:** Day 25-30 (prep starts Day 14). **Nick/Justin** — Submit PH listing, engage with comments all day, coordinate personal network for upvotes, respond to every comment.",
                },
            ],
        },
        {
            "heading": "2C. Hacker News",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["HN strategy", "Social Media Manager"],
                        ["Show HN post draft (500 words, technical)", "Writer Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Day 28-32 (2-3 days after Product Hunt). **Nick/Justin** — Post to HN from personal account (needs karma). Engage with all technical comments.",
                },
            ],
        },
        # ── Phase 3: Referral & Scale ──────────────────────────────────
        {
            "heading": "Phase 3: Paid Retargeting Campaigns & Referral (Days 28-60)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Retargeting pixels have been collecting data since Day 1 (Phase 0C). Now we activate paid campaigns against those audiences. Referral program launches once the paid user base is large enough to seed it.",
                },
            ],
        },
        {
            "heading": "3A. Paid Retargeting Campaign Activation",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["Retargeting campaign architecture (3 funnel stages)", "Performance Marketer"],
                        ["6 ad copy variants (2 per funnel stage)", "Writer Agent"],
                        ["4 retargeting ad images", "Visual Agent"],
                        ["A/B test plan", "Performance Marketer"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Budget:** Meta retargeting $200-300/mo + Google Display $100-200/mo = $300-500/mo. Pixels have been collecting audience data since Day 1.",
                },
                {
                    "type": "paragraph",
                    "text": "**Nick** — Create Meta Business Manager + Google Ads accounts (if not already), upload ad creatives, set budgets, launch campaigns. Sync Customer.io segments as custom audiences for suppression (don't retarget paid users). **Automation:** Weekly ad spend report -> Slack.",
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 28-35 setup, ongoing.",
                },
            ],
        },
        {
            "heading": "3B. Referral Program",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["Referral program design (Beehiiv + paid-user tiers)", "Lifecycle Marketing"],
                        ["3 referral emails", "Writer Agent"],
                        ["Referral landing page copy", "Writer Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Tiers:** 3 referrals = tips PDF, 5 = sticker pack, 10 = 1 month free. Paid users: refer-a-friend = both get 1 month free.",
                },
                {
                    "type": "paragraph",
                    "text": "**Justin** — Implement referral tracking in agenttunnel.app codebase (unique referral links, credit tracking). **Automation:** Referral conversion notification + monthly referral digest. **Timeline:** Days 35-42.",
                },
            ],
        },
        # ── Phase 4: Community & Scale ─────────────────────────────────
        {
            "heading": "Phase 4: Community & Scale (Days 45-90)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Community building and editorial coordination scale the content engine and build long-term moats.",
                },
            ],
        },
        {
            "heading": "4A. Developer Community",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["Community engagement strategy", "Social Media Manager"],
                        ["Tutorial blog series (2/month)", "Writer Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Monitoring:** Add RSS sources (Anthropic blog, Cloudflare blog), Google Alerts for competitor mentions. **Nick/Justin** — Join and participate in Discord servers, Slack groups, indie hacker forums.",
                },
            ],
        },
        {
            "heading": "4B. Editorial Coordination",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Deliverable", "Agent"],
                    "rows": [
                        ["12-week master editorial calendar", "Editorial Lead"],
                        ["30-item content backlog (prioritized)", "Editorial Lead"],
                        ["4 weekly content bundles", "Editorial Lead"],
                        ["Content production tracker (Google Sheet)", "Sheets Agent"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Timeline:** Days 7-14 (parallel with Phase 1).",
                },
            ],
        },
        # ── Ongoing Operations ─────────────────────────────────────────
        {
            "heading": "Ongoing Operations",
            "level": 1,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "**Daily (automated):** Reddit monitoring (4h), RSS scanning (6h), Google Alerts (12h), Growth Ideas (daily), KPI Slack digest (8am)",
                        "**Weekly:** Content review (Editorial Lead), Retargeting performance review (Performance Marketer), SEO ranking check (SEO Agent)",
                        "**Weekly (Nick/Justin):** Review and post social content drafted by agents, review Customer.io email performance, check ad spend vs. budget",
                        "**Monthly:** Strategy review, content audit, experiment readouts, competitive intel, knowledge base update",
                        "**Monthly (Nick/Justin):** Review MRR vs. targets, adjust paid budget allocation, 1:1 founder outreach to churned users",
                    ],
                },
            ],
        },
        # ── Budget Allocation ──────────────────────────────────────────
        {
            "heading": "Budget Allocation (Monthly)",
            "level": 1,
            "content": [
                {
                    "type": "table",
                    "headers": ["Category", "Min ($500/mo)", "Max ($2,000/mo)"],
                    "rows": [
                        ["Meta retargeting", "$150", "$500"],
                        ["Google Display retargeting", "$100", "$300"],
                        ["Image generation (DALL-E)", "$10", "$40"],
                        ["Video generation (fal.ai)", "$5", "$25"],
                        ["LLM costs (Anthropic API)", "$50", "$150"],
                        ["Beehiiv", "$0", "$49"],
                        ["Customer.io", "$0", "$100"],
                        ["Reserve for experiments", "$185", "$836"],
                        ["Total", "$500", "$2,000"],
                    ],
                },
            ],
        },
        # ── Build Order ────────────────────────────────────────────────
        {
            "heading": "Build Order (Critical Path)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Phase 0 is a hard gate — no traffic is driven until GTM, Customer.io, and lifecycle emails are verified operational. The site is already live, so Phase 0 focuses on instrumentation, not deployment.",
                },
                {
                    "type": "table",
                    "headers": ["Timeline", "Phase", "Work", "Gate?"],
                    "rows": [
                        ["Day 1", "0A", "Workspace setup in CMO Agent", ""],
                        ["Day 1-3", "0B", "Analytics framework + event taxonomy", ""],
                        ["Day 2-5", "0C", "GTM container + all retargeting pixels on agenttunnel.app", "GATE"],
                        ["Day 3-7", "0D", "Customer.io integration via n8n (5 workflows)", "GATE"],
                        ["Day 5-10", "0E", "Lifecycle email flows built in Customer.io (14 emails)", "GATE"],
                        ["Day 3-8", "0F", "Landing page CRO (optimize existing site)", ""],
                        ["Day 5-7", "4B", "Editorial calendar (parallel)", ""],
                        ["Day 5-21", "1A-1D", "SEO engine + Reddit + Twitter + LinkedIn (only after gates pass)", ""],
                        ["Day 14-21", "2A", "Newsletter / Beehiiv", ""],
                        ["Day 25-30", "2B", "Product Hunt launch", ""],
                        ["Day 28-35", "2C + 3A", "Hacker News + Paid retargeting campaign activation", ""],
                        ["Day 35-42", "3B", "Referral program", ""],
                        ["Day 45-90", "4A", "Community scaling", ""],
                        ["Day 90", "Review", "500 users / $7,500 MRR checkpoint", ""],
                    ],
                },
            ],
        },
        # ── Funnel Math ────────────────────────────────────────────────
        {
            "heading": "Funnel Math",
            "level": 1,
            "content": [
                {
                    "type": "table",
                    "headers": ["Stage", "Conversion Rate", "Volume Needed"],
                    "rows": [
                        ["Paid users (target)", "—", "500"],
                        ["Trial users needed", "15% trial-to-paid", "~3,333"],
                        ["Signups needed", "40% signup-to-trial", "~8,333"],
                        ["Visitors needed", "8% visitor-to-signup", "~104,000"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Top traffic sources (estimated share):** PH launch (20%), Hacker News (15%), SEO (10%), Reddit (8%), Twitter (8%), Paid retargeting (8%).",
                },
                {
                    "type": "paragraph",
                    "text": "**Note:** 104K visitors is aggressive for 90 days. Product Hunt + Hacker News launches are the biggest levers. If those underperform, extend to 120 days or increase paid budget.",
                },
            ],
        },
        # ── n8n Workflows ──────────────────────────────────────────────
        {
            "heading": "n8n Automation Workflows to Build",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Consolidated list of all automation workflows. We already have a starting n8n workflow with Customer.io API integration — build from there. Workflows marked (Phase 0) are launch-critical.",
                },
                {
                    "type": "table",
                    "headers": ["Workflow", "Trigger", "Action", "Priority"],
                    "rows": [
                        ["Signup -> Customer.io", "Webhook: new_signup from agenttunnel.app", "Customer.io Track API: identify person + UTM attributes", "Phase 0 (CRITICAL)"],
                        ["Trial activation", "Webhook: first_mobile_session", "Customer.io Track API: event 'first_session_completed'", "Phase 0 (CRITICAL)"],
                        ["Stripe -> Customer.io (paid)", "Stripe: checkout.session.completed", "Customer.io: update paid=true, track 'upgraded_to_paid'", "Phase 0 (CRITICAL)"],
                        ["Stripe -> Customer.io (churn)", "Stripe: customer.subscription.deleted", "Customer.io: update paid=false, trigger win-back", "Phase 0 (CRITICAL)"],
                        ["New signup notification", "Webhook: new_signup event", "Post to #agent-tunnel Slack with email, UTM, timestamp", "Phase 0"],
                        ["Daily metrics digest", "Cron: 8am daily", "Fetch signup/conversion data -> Slack summary", "Phase 0"],
                        ["Blog publish notification", "RSS: blog feed", "Slack + social queue notification", "Phase 1"],
                        ["Reddit keyword alert", "Cron: every 4h", "Scan subreddits for keywords -> Slack alert", "Phase 1"],
                        ["Blog-to-newsletter sync", "RSS: blog feed", "Auto-draft Beehiiv newsletter from new posts", "Phase 2"],
                        ["Beehiiv -> Customer.io sync", "Webhook: new subscriber", "Sync subscriber to Customer.io", "Phase 2"],
                        ["PH launch day reminders", "Cron: every 2h on launch day", "Slack reminders + Beehiiv blast", "Phase 2"],
                        ["Weekly ad spend report", "Cron: weekly", "Fetch Meta/Google ad data -> Slack summary", "Phase 3"],
                        ["Referral conversion", "Webhook: referral_converted", "Notification + monthly digest", "Phase 3"],
                    ],
                },
            ],
        },
        # ── First 10 Commands ──────────────────────────────────────────
        {
            "heading": "First 10 Commands to Execute",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "After reviewing this plan with Justin, these are the first 10 commands to run in the CMO Agent system to kick off execution:",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "\"Create workspace agent_tunnel named 'Agent Tunnel' with type owned_brand and Slack channel #agent-tunnel\"",
                        "\"Set keywords for agent_tunnel: Claude Code, mobile coding, remote development, Cloudflare tunnel, AI coding assistant, mobile IDE, SSH alternative\"",
                        "\"Store in knowledge base for agent_tunnel: Agent Tunnel is a Mac desktop app at $15/month. Site live at agenttunnel.app with Stripe. Three value pillars: Security, Simplicity, Mobility. ICP: busy professionals 28-50.\"",
                        "\"Create a measurement framework for agent_tunnel with business goals: trial signups, paid conversions, retention, referrals. Tech stack: GA4, Customer.io, Beehiiv, Stripe\"",
                        "\"Create UTM naming standards for agent_tunnel with sources: reddit, twitter, linkedin, google, beehiiv, producthunt, hackernews, email\"",
                        "\"Design GA4 event taxonomy for agent_tunnel covering: page_view, sign_up_start, sign_up_complete, trial_start, qr_code_scanned, first_session, upgrade_to_paid\"",
                        "\"Design lifecycle email flows for agent_tunnel: trial onboarding (5 emails), trial-to-paid conversion (4 emails), win-back (3 emails), engagement (2 emails)\"",
                        "\"Write the 14 lifecycle emails for agent_tunnel trial onboarding, conversion, win-back, and engagement sequences\"",
                        "\"Create a 12-week editorial calendar for agent_tunnel covering all channels\"",
                        "\"Build keyword architecture for agent_tunnel with 5 topic clusters\"",
                    ],
                },
            ],
        },
        # ── Human Actions Required ─────────────────────────────────────
        {
            "heading": "Human Actions Required (Consolidated)",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "Everything below requires a human to take action. The CMO Agent system produces all strategy, copy, creative, and automation specs — but these items cannot be automated and must be done by Nick or Justin.",
                },
                {
                    "type": "table",
                    "headers": ["Phase", "Action", "Owner", "Blocking?"],
                    "rows": [
                        ["0C", "Create GTM account + install GTM snippet on agenttunnel.app (GitHub PR)", "Justin", "YES — blocks all channels"],
                        ["0C", "Install Meta Pixel, Google Ads tag, LinkedIn Insight Tag, Customer.io snippet in GTM", "Nick", "YES — blocks retargeting"],
                        ["0C", "Verify all GTM tags fire correctly via GTM preview mode", "Justin/Nick", "YES — blocks all channels"],
                        ["0D", "Create Customer.io account + generate API keys + add to n8n", "Nick", "YES — blocks lifecycle emails"],
                        ["0D", "Add signup webhook to agenttunnel.app (POST to n8n on new user creation)", "Justin", "YES — blocks lifecycle emails"],
                        ["0E", "Build campaign flows in Customer.io UI (segments, triggers, email campaigns)", "Nick", "YES — blocks all channels"],
                        ["0E", "Test lifecycle email flow end-to-end with a test signup", "Nick", "YES — final gate"],
                        ["0F", "Implement CRO copy/design changes to agenttunnel.app (merge GitHub PRs)", "Justin/Nick", "No"],
                        ["1A", "Publish blog posts to website CMS (or build blog into site)", "Justin/Nick", "No"],
                        ["1B", "Post all Reddit content personally (TOS requirement)", "Nick/Justin", "No"],
                        ["1C", "Create @AgentTunnel Twitter account + post all drafted content", "Nick/Justin", "No"],
                        ["1D", "Post LinkedIn content from personal profiles", "Nick/Justin", "No"],
                        ["2A", "Create Beehiiv account + configure publication", "Nick", "No"],
                        ["2B", "Submit Product Hunt listing + engage with comments on launch day", "Nick/Justin", "No"],
                        ["2C", "Post Show HN from personal account (needs karma)", "Nick/Justin", "No"],
                        ["3A", "Create Meta Business Manager + Google Ads accounts, upload ad creatives, set budgets", "Nick", "No"],
                        ["3B", "Implement referral tracking in agenttunnel.app codebase", "Justin", "No"],
                        ["4A", "Join and participate in developer Discord/Slack communities", "Nick/Justin", "No"],
                        ["Ongoing", "Weekly: review and post social content, review email performance, check ad spend", "Nick/Justin", "No"],
                        ["Ongoing", "Monthly: review MRR targets, adjust budgets, founder outreach to churned users", "Nick/Justin", "No"],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**7 blocking items** must be completed before any traffic is driven. All are in Phase 0. Target: complete all blocking items by Day 10.",
                },
            ],
        },
        {
            "heading": "Full-Funnel Architecture",
            "level": 1,
            "content": [
                {
                    "type": "table",
                    "headers": ["Stage", "Conversion Target", "Key Tactics"],
                    "rows": [
                        [
                            "Awareness → Interest",
                            "10K monthly visitors",
                            "SEO, Reddit, Product Hunt, HN",
                        ],
                        [
                            "Interest → Consideration",
                            "8-12% to email",
                            "Lead magnets, exit-intent popups",
                        ],
                        [
                            "Consideration → Trial",
                            "60%+ email to trial",
                            "5-email nurture, social proof",
                        ],
                        ["Trial → Paid", "15-25% conversion", "First session in 24hrs, 3+ uses"],
                        ["Retention", "90%+ monthly", "Lifecycle emails, usage reports"],
                    ],
                },
            ],
        },
        {
            "heading": "Lifecycle Marketing & Email Sequence",
            "level": 1,
            "content": [
                {
                    "type": "table",
                    "headers": ["Day", "Subject Line", "Content Focus"],
                    "rows": [
                        [
                            "Day 0",
                            "Your Agent Tunnel download is ready",
                            "Download link + quick start guide",
                        ],
                        [
                            "Day 1",
                            "Did Claude Code respond from your phone yet?",
                            "Troubleshooting + demo video",
                        ],
                        [
                            "Day 3",
                            "3 ways to use Agent Tunnel this week",
                            "Use cases: commute, coffee shop, couch",
                        ],
                        [
                            "Day 7",
                            "Your first week with mobile Claude Code",
                            "Usage stats + advanced tips",
                        ],
                        [
                            "Day 14",
                            "Halfway through your trial — how's it going?",
                            "Founder check-in + 1:1 offer",
                        ],
                        [
                            "Day 18",
                            "6 days left — secure your early adopter rate",
                            "Discount reminder + social proof",
                        ],
                        ["Day 21", "Your Agent Tunnel trial ends today", "Final conversion push"],
                    ],
                },
            ],
        },
        {
            "heading": "Launch Timeline",
            "level": 1,
            "content": [
                {
                    "type": "numbered_list",
                    "items": [
                        "Phase 1: Foundation (Weeks 1-4) — Finalize pricing, launch SEO, soft launch to 50 beta users, expand to 200",
                        "Phase 2: Public Launch (Weeks 5-8) — Product Hunt launch, Hacker News, influencer outreach, paid retargeting",
                        "Phase 3: Growth (Weeks 9-12) — A/B test pricing, expand channels, launch referral program, plan enterprise features",
                    ],
                },
            ],
        },
        {
            "heading": "Unit Economics & Financial Model",
            "level": 1,
            "content": [
                {
                    "type": "table",
                    "headers": ["Metric", "Value"],
                    "rows": [
                        ["Target CAC", "$50/customer"],
                        ["Blended LTV", "$240"],
                        ["LTV:CAC Ratio", "4.8:1"],
                        ["Month 3 Revenue", "$7,500 (500 × $15 avg)"],
                        ["Month 3 Costs", "$3,500"],
                        ["Month 3 Margin", "53%"],
                        ["Break-even", "233 customers (Month 2 target)"],
                    ],
                },
            ],
        },
        {
            "heading": "CAC by Channel",
            "level": 2,
            "content": [
                {
                    "type": "table",
                    "headers": ["Channel", "CAC", "Notes"],
                    "rows": [
                        ["Organic SEO", "$20", "Content + tools"],
                        ["Reddit/HN", "$10", "Time investment only"],
                        ["Product Hunt", "$30", "Assets + outreach"],
                        ["Paid Retargeting", "$80", "Highest cost, high intent"],
                    ],
                },
            ],
        },
        {
            "heading": "Risk Assessment",
            "level": 1,
            "content": [
                {
                    "type": "table",
                    "headers": ["Category", "Risk", "Mitigation"],
                    "rows": [
                        [
                            "Technical",
                            "Cloudflare tunnel reliability",
                            "SLA monitoring, backup providers",
                        ],
                        [
                            "Technical",
                            "Mac app security vulnerabilities",
                            "Security audits, responsible disclosure",
                        ],
                        [
                            "Market",
                            "Claude Code breaking changes",
                            "Direct Anthropic relationship, API monitoring",
                        ],
                        [
                            "Market",
                            "Well-funded competitor enters",
                            "Superior UX, strong community",
                        ],
                        [
                            "Business",
                            "Low trial-to-paid conversion",
                            "Onboarding optimization, success metrics",
                        ],
                        [
                            "Business",
                            "High churn rate",
                            "Proactive customer success, usage campaigns",
                        ],
                    ],
                },
                {
                    "type": "paragraph",
                    "text": "**Mitigation Budget:** $5,000 emergency fund, $2,000 legal/IP, $3,000 additional development.",
                },
            ],
        },
    ],
}


# ── GTM Pitch Deck structure ────────────────────────────────────────────

GTM_DECK_STRUCTURE = {
    "title": "Agent Tunnel — Go-to-Market Strategy",
    "subtitle": "Claude Code in Your Pocket",
    "slides": [
        {
            "type": "title",
            "title": "Agent Tunnel",
            "subtitle": "Claude Code in Your Pocket — Secure, Simple, Mobile-First",
        },
        {
            "type": "content",
            "title": "The Problem",
            "bullets": [
                "Claude Code users are desk-bound — can't code on the go",
                "SSH tunnels are complex: key management, port forwarding, config",
                "Screen sharing is laggy and unusable on mobile",
                "Missed opportunities when you're away from your desk",
            ],
        },
        {
            "type": "content",
            "title": "The Solution",
            "bullets": [
                "Mac desktop app with secure mobile access via Cloudflare tunnel",
                "Three steps: Install → Scan QR → Control Claude Code from phone",
                "Native mobile experience, not a remote desktop",
                "Enterprise-grade security with zero configuration",
            ],
        },
        {
            "type": "stats",
            "title": "90-Day Targets",
            "stats": [
                {"value": "500", "label": "Paid Users"},
                {"value": "3:1", "label": "LTV:CAC"},
                {"value": "$7.5K", "label": "Monthly Revenue"},
                {"value": "85%", "label": "Setup Completion"},
            ],
        },
        {
            "type": "section",
            "title": "Three Value Pillars",
        },
        {
            "type": "two_column",
            "title": "Security & Simplicity",
            "left_title": "Security",
            "left_column": [
                "Cloudflare tunnel encryption",
                "Biometric auth (Face ID/Touch ID)",
                "No exposed ports",
                "Compliance-friendly",
            ],
            "right_title": "Simplicity",
            "right_column": [
                "Install, scan QR, control",
                "Under 5 minutes to setup",
                "No SSH keys or VPN config",
                "Just works out of the box",
            ],
        },
        {
            "type": "content",
            "title": "Target Market",
            "bullets": [
                "Primary: Busy professionals aged 28-50 using Claude Code",
                "TAM: 50,000+ regular Claude Code users",
                "SAM: 15,000 power users (500+ sessions)",
                "SOM: 2,500 mobile-productivity-focused professionals",
                "Psychographic: Values time, security-conscious, pays for convenience",
            ],
        },
        {
            "type": "two_column",
            "title": "Pricing Strategy",
            "left_title": "Consumer Tiers",
            "left_column": [
                "Free: 14-day trial, full access",
                "Monthly: $15/month",
                "Annual: $150/year (17% discount)",
            ],
            "right_title": "Launch Specials",
            "right_column": [
                "Early Adopter: $10/month (first 100)",
                "Lifetime: $500 one-time (first 50)",
                "Builds immediate cash flow + loyalty",
            ],
        },
        {
            "type": "content",
            "title": "Channel Strategy",
            "bullets": [
                "P0: Organic SEO ($200/mo), Reddit, Product Hunt, Hacker News",
                "P1: Twitter/X ($100/mo), LinkedIn ($50/mo), Dev communities",
                "Total budget: $500-2,000/month across all channels",
                "Focus on organic channels with high trust signals",
            ],
        },
        {
            "type": "stats",
            "title": "Unit Economics",
            "stats": [
                {"value": "$50", "label": "Target CAC"},
                {"value": "$240", "label": "Blended LTV"},
                {"value": "4.8:1", "label": "LTV:CAC Ratio"},
                {"value": "53%", "label": "Month 3 Margin"},
            ],
        },
        {
            "type": "content",
            "title": "Full-Funnel Conversion Targets",
            "bullets": [
                "Awareness → Interest: 10,000 monthly visitors by Month 3",
                "Interest → Consideration: 8-12% visitor to email signup",
                "Consideration → Trial: 60%+ email to trial conversion",
                "Trial → Paid: 15-25% trial to paid conversion",
                "Retention: 90%+ monthly retention rate",
            ],
        },
        {
            "type": "content",
            "title": "Launch Timeline",
            "bullets": [
                "Weeks 1-4: Foundation — beta users, SEO, email sequences",
                "Weeks 5-8: Public Launch — Product Hunt, HN, press outreach",
                "Weeks 9-12: Growth — A/B testing, referral program, enterprise",
            ],
        },
        {
            "type": "quote",
            "quote": "You're at your kid's basketball game. A Slack message pings — there's a bug in production. Open Agent Tunnel, ask Claude to investigate, push the fix. Back to the game before halftime.",
            "attribution": "Agent Tunnel Use Case",
        },
        {
            "type": "cta",
            "title": "Let's Build the Future of Mobile Development",
            "subtitle": "agenttunnel.app  |  hello@agenttunnel.app",
        },
    ],
}


# ── Existing document IDs to update ────────────────────────────────────
EXISTING_DOC_ID = "1zegIuI3M98H2ZkqAHI5E8O9hZGrXHiOBqnUUQvH1NyA"
EXISTING_DECK_ID = "1luVXI8TfqouTvOLiWq_XVB8ehCr4uY4RWB6hAVWbdgs"

# Highlight colours (light pastels so text remains readable)
# RGB values 0.0-1.0
COLOR_NICK = {"red": 1.0, "green": 0.9, "blue": 0.6}       # warm yellow
COLOR_JUSTIN = {"red": 0.7, "green": 0.88, "blue": 1.0}    # light blue
COLOR_BOTH = {"red": 0.8, "green": 0.95, "blue": 0.75}     # light green


def highlight_owner_mentions(docs_agent: DocsAgent, doc_id: str) -> int:
    """Read a Google Doc and highlight Nick / Justin mentions.

    Returns the total number of highlights applied.
    """
    import re as _re
    import time

    svc = docs_agent._docs_service
    doc = svc.documents().get(documentId=doc_id).execute()
    body_content = doc.get("body", {}).get("content", [])

    # Collect full document plain text with index mapping
    # Each text run has a startIndex in the doc — we scan for patterns there
    matches: list = []

    # Highlight each name individually with its own colour
    nick_pat = _re.compile(r"\bNick\b")
    justin_pat = _re.compile(r"\bJustin\b")

    def _scan_elements(elements: list) -> None:
        """Scan paragraph elements for Nick/Justin and record matches."""
        for el in elements:
            tr = el.get("textRun")
            if not tr:
                continue
            content = tr.get("content", "")
            start_idx = el.get("startIndex", 0)
            for m in nick_pat.finditer(content):
                matches.append((start_idx + m.start(), start_idx + m.end(), COLOR_NICK))
            for m in justin_pat.finditer(content):
                matches.append((start_idx + m.start(), start_idx + m.end(), COLOR_JUSTIN))

    for elem in body_content:
        if "paragraph" in elem:
            _scan_elements(elem["paragraph"].get("elements", []))
        elif "table" in elem:
            for row in elem["table"].get("tableRows", []):
                for cell in row.get("tableCells", []):
                    for cell_elem in cell.get("content", []):
                        if "paragraph" not in cell_elem:
                            continue
                        _scan_elements(cell_elem["paragraph"].get("elements", []))

    if not matches:
        print("  No Nick/Justin mentions found to highlight.")
        return 0

    # Build highlight requests
    requests = []
    for start, end, color in matches:
        requests.append(
            {
                "updateTextStyle": {
                    "range": {"startIndex": start, "endIndex": end},
                    "textStyle": {
                        "backgroundColor": {"color": {"rgbColor": color}},
                    },
                    "fields": "backgroundColor",
                }
            }
        )

    # Execute in batches of 50 to stay within rate limits
    _write_ts: list = []
    total = len(requests)
    for i in range(0, total, 50):
        batch = requests[i : i + 50]
        now = time.time()
        while _write_ts and now - _write_ts[0] > 60:
            _write_ts.pop(0)
        if len(_write_ts) >= 55:
            sleep_time = 61 - (now - _write_ts[0])
            if sleep_time > 0:
                print(f"  Rate limit pause: {sleep_time:.1f}s")
                time.sleep(sleep_time)
        svc.documents().batchUpdate(
            documentId=doc_id, body={"requests": batch}
        ).execute()
        _write_ts.append(time.time())
        print(f"  Highlighted {min(i + 50, total)}/{total} mentions")

    return total


async def main() -> None:
    settings = Settings()

    # Initialize database
    db = Database(settings.db_path)
    await db.initialize()

    # Initialize workspace manager
    workspace_mgr = WorkspaceManager(db)

    # Initialize LLM (needed for agent constructors but we won't call LLM)
    llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model_writing,
    )

    workspace_id = "agent_tunnel"

    # ── Update existing Google Doc ───────────────────────────────────
    print(f"\n=== Updating GTM Google Doc ({EXISTING_DOC_ID}) ===")
    docs_agent = DocsAgent(
        llm=llm,
        db=db,
        workspace_manager=workspace_mgr,
        google_credentials_path=settings.google_credentials_path,
        google_oauth_token_path=getattr(settings, "google_oauth_token_path", ""),
    )

    doc_result = docs_agent._update_google_doc(EXISTING_DOC_ID, GTM_DOC_STRUCTURE, workspace_id)
    print(f"Doc result: {doc_result}")

    # ── Highlight Nick / Justin mentions ──────────────────────
    if doc_result.get("status") in ("updated", "created"):
        print("\n=== Highlighting owner mentions ===")
        count = highlight_owner_mentions(docs_agent, EXISTING_DOC_ID)
        print(f"  Applied {count} highlights (yellow=Nick, blue=Justin, green=both)")

    # ── Summary ──────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("RESULTS:")
    if doc_result.get("google_docs_url"):
        print(f"  Google Doc:    {doc_result['google_docs_url']}")
    else:
        print(f"  Google Doc:    FAILED — {doc_result.get('message', doc_result)}")
    print("=" * 60)

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
