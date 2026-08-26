#!/usr/bin/env python3
"""Create a detailed Agent Tunnel GTM Work Plan in Google Sheets.

Builds a multi-tab spreadsheet from the GTM strategy with every task,
n8n workflow, human action, milestone, and budget line item.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Add src to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SPREADSHEET_TITLE = "Agent Tunnel — GTM Work Plan"


# ── Task Data ────────────────────────────────────────────────────────────

def _work_plan_rows() -> List[List[str]]:
    """Return every task row for the Work Plan tab."""
    # fmt: off
    return [
        # Phase 0A — Workspace & Brand Configuration
        ["0A-1", "0", "0A", "Register agent_tunnel workspace", "Create workspace agent_tunnel in CMO Agent DB with type=owned_brand, Slack #agent-tunnel", "Setup", "Orchestrator", "Agent", "Critical", "No", "1", "1", "1", "—", "Not Started"],
        ["0A-2", "0", "0A", "Set workspace keywords", "Set keywords: Claude Code, mobile coding, remote development, Cloudflare tunnel, AI coding assistant, mobile IDE, SSH alternative, Claude mobile, code from phone, developer tools", "Setup", "Orchestrator", "Agent", "Critical", "No", "1", "1", "1", "0A-1", "Not Started"],
        ["0A-3", "0", "0A", "Store product knowledge in KB", "Store in knowledge base: Mac desktop app at $15/mo. Three pillars: Security, Simplicity, Mobility. ICP: busy professionals 28-50", "Setup", "Knowledge Base", "Agent", "High", "No", "1", "1", "1", "0A-1", "Not Started"],

        # Phase 0B — Measurement & Analytics Foundation
        ["0B-1", "0", "0B", "Create measurement framework", "Business goals: trial signups, paid conversions, retention, referrals. Tech stack: GA4, Customer.io, Beehiiv, Stripe", "Strategy", "Marketing Analytics", "Agent", "Critical", "No", "1", "3", "3", "0A-1", "Not Started"],
        ["0B-2", "0", "0B", "Design GA4 event taxonomy", "Events: page_view, sign_up_start, sign_up_complete, trial_start, qr_code_scanned, first_session, upgrade_to_paid, referral_sent, referral_converted, churn", "Strategy", "Marketing Analytics", "Agent", "Critical", "No", "1", "3", "3", "0A-1", "Not Started"],
        ["0B-3", "0", "0B", "Create UTM governance standards", "Sources: reddit, twitter, linkedin, google, beehiiv, producthunt, hackernews, email. Mediums: organic, social, cpc, retargeting, newsletter, community", "Strategy", "Marketing Analytics", "Agent", "Critical", "No", "2", "3", "2", "0B-1", "Not Started"],
        ["0B-4", "0", "0B", "Build KPI dashboard (Google Sheet)", "Daily/weekly signups, trial-to-paid rate, MRR, churn rate, CAC by channel, LTV, referral rate", "Dashboard", "Marketing Analytics + Sheets", "Agent", "High", "No", "2", "4", "3", "0B-1", "Not Started"],
        ["0B-5", "0", "0B", "Write tracking implementation spec", "dataLayer push events, GA4 config, enhanced conversions for Stripe, cross-domain tracking", "Spec", "Marketing Analytics", "Agent", "Critical", "No", "2", "3", "2", "0B-2", "Not Started"],

        # Phase 0C — GTM & Retargeting Pixels
        ["0C-1", "0", "0C", "Create GTM account", "Create Google Tag Manager account for agenttunnel.app", "Setup", "—", "Justin", "Critical", "YES", "2", "3", "2", "—", "Not Started"],
        ["0C-2", "0", "0C", "Install GTM snippet on site", "Add GTM container snippet to agenttunnel.app via GitHub PR", "Code", "—", "Justin", "Critical", "YES", "2", "4", "3", "0C-1", "Not Started"],
        ["0C-3", "0", "0C", "Configure GA4 tag in GTM", "Set up GA4 measurement ID, page_view tracking, enhanced measurement in GTM", "Setup", "—", "Justin / Nick", "Critical", "YES", "3", "5", "3", "0C-2, 0B-2", "Not Started"],
        ["0C-4", "0", "0C", "Install Meta Pixel in GTM", "Add Meta Pixel via GTM. Events: PageView, Lead (signup), StartTrial, Purchase", "Setup", "—", "Nick", "Critical", "YES", "3", "5", "3", "0C-2", "Not Started"],
        ["0C-5", "0", "0C", "Install Google Ads remarketing tag", "Install Google Ads tag via GTM for display retargeting audiences", "Setup", "—", "Nick", "Critical", "YES", "3", "5", "3", "0C-2", "Not Started"],
        ["0C-6", "0", "0C", "Install LinkedIn Insight Tag", "Install via GTM for LinkedIn retargeting (professional audience)", "Setup", "—", "Nick", "High", "No", "3", "5", "3", "0C-2", "Not Started"],
        ["0C-7", "0", "0C", "Install Customer.io site tracking", "Install Customer.io JavaScript snippet via GTM for on-site behavioral tracking", "Setup", "—", "Nick", "Critical", "YES", "3", "5", "3", "0C-2", "Not Started"],
        ["0C-8", "0", "0C", "Map conversion events across pixels", "Map GTM dataLayer events to each pixel: signup → Lead/StartTrial across all platforms", "Strategy", "Marketing Analytics", "Agent", "Critical", "No", "3", "5", "3", "0B-2, 0C-2", "Not Started"],
        ["0C-9", "0", "0C", "GTM preview/debug verification", "Use GTM preview mode to verify all tags fire correctly on signup/trial/purchase flows", "QA", "—", "Justin / Nick", "Critical", "YES", "4", "5", "2", "0C-3 thru 0C-8", "Not Started"],

        # Phase 0D — Customer.io Integration via n8n
        ["0D-1", "0", "0D", "Create Customer.io account", "Create account, generate Track API key + App API key", "Setup", "—", "Nick", "Critical", "YES", "3", "4", "2", "—", "Not Started"],
        ["0D-2", "0", "0D", "Add Customer.io creds to n8n", "Add Track API key + App API key to n8n credentials store", "Setup", "—", "Nick", "Critical", "YES", "3", "4", "2", "0D-1", "Not Started"],
        ["0D-3", "0", "0D", "Build n8n: Signup → Customer.io", "Webhook receives new_signup → Customer.io Track API: identify person with email, UTM, signup_date, plan=trial", "Automation", "n8n", "Agent", "Critical", "YES", "4", "6", "3", "0D-2, 0B-2", "Not Started"],
        ["0D-4", "0", "0D", "Build n8n: Trial activation event", "Webhook receives first_mobile_session → Customer.io Track API: event 'first_session_completed'", "Automation", "n8n", "Agent", "Critical", "YES", "4", "6", "3", "0D-2", "Not Started"],
        ["0D-5", "0", "0D", "Build n8n: Stripe → Customer.io (paid)", "Stripe webhook checkout.session.completed → Customer.io: update paid=true, track 'upgraded_to_paid'", "Automation", "n8n", "Agent", "Critical", "YES", "4", "7", "4", "0D-2", "Not Started"],
        ["0D-6", "0", "0D", "Build n8n: Stripe → Customer.io (churn)", "Stripe webhook customer.subscription.deleted → Customer.io: update paid=false, trigger win-back", "Automation", "n8n", "Agent", "Critical", "YES", "5", "7", "3", "0D-2", "Not Started"],
        ["0D-7", "0", "0D", "Build n8n: Daily metrics → Slack", "Cron 8am → Customer.io Reporting API: fetch signup/conversion counts → Slack #agent-tunnel", "Automation", "n8n", "Agent", "High", "No", "5", "7", "3", "0D-2", "Not Started"],
        ["0D-8", "0", "0D", "Add signup webhook to site", "Add POST to n8n webhook URL on new user creation with email + UTM params in agenttunnel.app codebase", "Code", "—", "Justin", "Critical", "YES", "4", "6", "3", "0D-3", "Not Started"],

        # Phase 0E — Email Lifecycle System
        ["0E-1", "0", "0E", "Design lifecycle email flows", "Trial onboarding (5), conversion (4), win-back (3), engagement (2). Segments: trial_active, trial_inactive, trial_expiring, paid_active, paid_at_risk, churned", "Strategy", "Lifecycle Marketing", "Agent", "Critical", "No", "5", "7", "3", "0D-3", "Not Started"],
        ["0E-2", "0", "0E", "Write 5 trial onboarding emails", "Welcome, setup guide, first win, social proof, upgrade nudge", "Copy", "Writer", "Agent", "Critical", "No", "6", "8", "3", "0E-1", "Not Started"],
        ["0E-3", "0", "0E", "Write 4 trial-to-paid conversion emails", "Day 5/10/13/14 triggers — urgency progression", "Copy", "Writer", "Agent", "Critical", "No", "6", "8", "3", "0E-1", "Not Started"],
        ["0E-4", "0", "0E", "Write 3 win-back emails", "7/30/60 days post-churn — re-engagement sequence", "Copy", "Writer", "Agent", "High", "No", "7", "9", "3", "0E-1", "Not Started"],
        ["0E-5", "0", "0E", "Write 2 engagement/retention emails", "no_session_7d and low_usage triggers", "Copy", "Writer", "Agent", "High", "No", "7", "9", "3", "0E-1", "Not Started"],
        ["0E-6", "0", "0E", "Build campaign flows in Customer.io", "Configure segments, triggers, delays, and email campaigns in Customer.io UI", "Setup", "—", "Nick", "Critical", "YES", "7", "10", "4", "0E-2 thru 0E-5, 0D-3", "Not Started"],
        ["0E-7", "0", "0E", "Create segments in Customer.io", "trial_active, trial_inactive, trial_expiring, paid_active, paid_at_risk, churned", "Setup", "—", "Nick", "Critical", "No", "7", "9", "3", "0D-3", "Not Started"],
        ["0E-8", "0", "0E", "Test lifecycle email flow E2E", "Run test signup through entire lifecycle flow — verify all emails fire", "QA", "—", "Nick", "Critical", "YES", "9", "10", "2", "0E-6", "Not Started"],

        # Phase 0F — Landing Page CRO
        ["0F-1", "0", "0F", "Funnel architecture audit", "Audit current agenttunnel.app for conversion optimization opportunities", "Strategy", "Acquisition", "Agent", "High", "No", "3", "5", "3", "0B-1", "Not Started"],
        ["0F-2", "0", "0F", "CRO copy recommendations", "Hero, How It Works, Security, Use Cases, FAQ, CTA copy", "Copy", "Writer", "Agent", "High", "No", "4", "6", "3", "0F-1", "Not Started"],
        ["0F-3", "0", "0F", "Hero image creation", "Developer on phone with code visible, 1792x1024", "Creative", "Visual", "Agent", "Medium", "No", "4", "6", "3", "—", "Not Started"],
        ["0F-4", "0", "0F", "Product demo motion graphic", "3-step setup flow animation, 15 seconds", "Creative", "Motion Graphics", "Agent", "Medium", "No", "5", "8", "4", "—", "Not Started"],
        ["0F-5", "0", "0F", "A/B headline test design", "Benefit-led vs. pain-led vs. curiosity-led headline variants", "Strategy", "Acquisition", "Agent", "Medium", "No", "5", "7", "3", "0F-1", "Not Started"],
        ["0F-6", "0", "0F", "Implement CRO changes on site", "Merge copy/design GitHub PRs to agenttunnel.app", "Code", "—", "Justin / Nick", "High", "No", "6", "8", "3", "0F-2, 0F-3", "Not Started"],

        # Phase 1A — SEO & Content Marketing
        ["1A-1", "1", "1A", "Build keyword architecture (5 clusters)", "5 topic clusters around Claude Code mobile, SSH alternatives, remote dev tools, AI coding, mobile IDE", "Strategy", "SEO & AEO", "Agent", "High", "No", "5", "8", "4", "0A-2", "Not Started"],
        ["1A-2", "1", "1A", "Define page type governance (5 types)", "Blog post, comparison page, landing page, tutorial, use case — with templates", "Strategy", "SEO & AEO", "Agent", "High", "No", "5", "8", "4", "1A-1", "Not Started"],
        ["1A-3", "1", "1A", "Create 8 SEO content briefs", "One brief per target keyword cluster — title, outline, word count, target keyword, internal links", "Strategy", "SEO & AEO", "Agent", "High", "No", "7", "10", "4", "1A-1", "Not Started"],
        ["1A-4", "1", "1A", "Create AEO optimization spec", "Featured snippet formatting, AI summary optimization, zero-click answer positioning", "Strategy", "SEO & AEO", "Agent", "Medium", "No", "8", "11", "4", "1A-1", "Not Started"],
        ["1A-5", "1", "1A", "Build keyword ranking tracker sheet", "Google Sheet tracking keyword positions, search volume, SERP features", "Dashboard", "SEO & AEO + Sheets", "Agent", "Medium", "No", "8", "10", "3", "1A-1", "Not Started"],
        ["1A-6", "1", "1A", "Write first 4 blog posts", "From SEO briefs — 2/week cadence starting week 2", "Copy", "Writer", "Agent", "High", "No", "10", "21", "12", "1A-3", "Not Started"],
        ["1A-7", "1", "1A", "Create blog images (1 per post)", "Custom header images for each blog post", "Creative", "Visual", "Agent", "Medium", "No", "10", "21", "12", "1A-6", "Not Started"],
        ["1A-8", "1", "1A", "Write 3 comparison pages", "vs. SSH tunnels, vs. VPN, vs. screen sharing — each 1500+ words", "Copy", "Writer", "Agent", "High", "No", "10", "16", "7", "1A-1", "Not Started"],
        ["1A-9", "1", "1A", "Build n8n blog publish workflow", "RSS: blog feed → Slack + social queue notification", "Automation", "n8n", "Agent", "Medium", "No", "10", "12", "3", "—", "Not Started"],
        ["1A-10", "1", "1A", "Publish blog posts to website", "Deploy blog posts to agenttunnel.app CMS or build blog section", "Code", "—", "Justin / Nick", "High", "No", "12", "21", "10", "1A-6", "Not Started"],

        # Phase 1B — Reddit Organic
        ["1B-1", "1", "1B", "Create Reddit engagement strategy", "Target 9 subreddits: r/ClaudeAI, r/ChatGPTPro, r/MacApps, r/webdev, r/programming, r/sideproject, etc.", "Strategy", "Social Media", "Agent", "High", "No", "5", "8", "4", "0A-2", "Not Started"],
        ["1B-2", "1", "1B", "Write 5 Reddit reply templates", "Helpful, non-promotional responses for different question types", "Copy", "Writer", "Agent", "High", "No", "6", "9", "4", "1B-1", "Not Started"],
        ["1B-3", "1", "1B", "Write Show r/ClaudeAI launch post", "Launch announcement post for r/ClaudeAI — authentic developer tone", "Copy", "Writer", "Agent", "High", "No", "8", "10", "3", "1B-1", "Not Started"],
        ["1B-4", "1", "1B", "Add Reddit monitoring sources", "Add subreddits as monitoring sources in CMO Agent", "Setup", "Orchestrator", "Agent", "Medium", "No", "5", "6", "2", "0A-1", "Not Started"],
        ["1B-5", "1", "1B", "Build n8n Reddit keyword alert", "Scan subreddits for 'Claude Code mobile/phone/remote' every 4h → Slack alert", "Automation", "n8n", "Agent", "Medium", "No", "7", "10", "4", "1B-4", "Not Started"],
        ["1B-6", "1", "1B", "Write weekly value posts (ongoing)", "Weekly Reddit posts with genuine value — tips, insights, discussions", "Copy", "Writer", "Agent", "Medium", "No", "10", "90", "80", "1B-1", "Not Started"],
        ["1B-7", "1", "1B", "Post Reddit content personally", "All Reddit posting must be done by humans (TOS requirement)", "Posting", "—", "Nick / Justin", "High", "No", "10", "90", "80", "1B-2", "Not Started"],

        # Phase 1C — Twitter/X Organic
        ["1C-1", "1", "1C", "Create Twitter/X content strategy", "Platform strategy: 40% educational, 30% product, 20% engagement, 10% promo", "Strategy", "Social Media", "Agent", "High", "No", "5", "8", "4", "0A-2", "Not Started"],
        ["1C-2", "1", "1C", "Build 30-day content calendar", "Daily tweet schedule with content types and themes", "Strategy", "Social Media", "Agent", "High", "No", "6", "10", "5", "1C-1", "Not Started"],
        ["1C-3", "1", "1C", "Write daily tweets (5-7/week)", "Educational, product, engagement tweets — ongoing", "Copy", "Writer", "Agent", "Medium", "No", "10", "90", "80", "1C-2", "Not Started"],
        ["1C-4", "1", "1C", "Write weekly threads", "Deep-dive threads on mobile development, Claude Code tips, productivity", "Copy", "Writer", "Agent", "Medium", "No", "10", "90", "80", "1C-2", "Not Started"],
        ["1C-5", "1", "1C", "Create social images (2/week)", "Branded images for tweets — tips, stats, quotes", "Creative", "Visual", "Agent", "Medium", "No", "10", "90", "80", "1C-1", "Not Started"],
        ["1C-6", "1", "1C", "Create short demo clips (2/month)", "15-30 second animated demos of Agent Tunnel features", "Creative", "Motion Graphics", "Agent", "Medium", "No", "14", "90", "76", "1C-1", "Not Started"],
        ["1C-7", "1", "1C", "Create @AgentTunnel account", "Set up Twitter/X account with branding", "Setup", "—", "Nick / Justin", "High", "No", "5", "7", "3", "—", "Not Started"],
        ["1C-8", "1", "1C", "Post Twitter content manually", "All Twitter posting done by humans", "Posting", "—", "Nick / Justin", "High", "No", "10", "90", "80", "1C-7, 1C-3", "Not Started"],

        # Phase 1D — LinkedIn
        ["1D-1", "1", "1D", "Create LinkedIn strategy", "Professional use cases and productivity wins positioning", "Strategy", "Social Media", "Agent", "Medium", "No", "7", "10", "4", "0A-2", "Not Started"],
        ["1D-2", "1", "1D", "Write LinkedIn posts (3-4/week)", "Professional audience content — ongoing", "Copy", "Writer", "Agent", "Medium", "No", "10", "90", "80", "1D-1", "Not Started"],
        ["1D-3", "1", "1D", "Write LinkedIn article (1/month)", "Long-form thought leadership — mobile-first development, AI coding future", "Copy", "Writer + Docs", "Agent", "Low", "No", "14", "90", "76", "1D-1", "Not Started"],
        ["1D-4", "1", "1D", "Post from personal LinkedIn profiles", "All LinkedIn posting from Nick/Justin personal profiles", "Posting", "—", "Nick / Justin", "Medium", "No", "10", "90", "80", "1D-2", "Not Started"],

        # Phase 2A — Newsletter / Beehiiv
        ["2A-1", "2", "2A", "Design newsletter strategy", "Frequency, content mix, growth tactics, subscriber journey", "Strategy", "Lifecycle Marketing", "Agent", "High", "No", "14", "17", "4", "0E-1", "Not Started"],
        ["2A-2", "2", "2A", "Create Beehiiv setup spec (Google Doc)", "Full Beehiiv configuration spec — publication settings, design, integrations", "Spec", "Docs", "Agent", "Medium", "No", "14", "17", "4", "2A-1", "Not Started"],
        ["2A-3", "2", "2A", "Write welcome email", "Beehiiv welcome email for new newsletter subscribers", "Copy", "Writer", "Agent", "High", "No", "15", "17", "3", "2A-1", "Not Started"],
        ["2A-4", "2", "2A", "Write first weekly newsletter", "First edition of weekly newsletter", "Copy", "Writer", "Agent", "High", "No", "17", "19", "3", "2A-1", "Not Started"],
        ["2A-5", "2", "2A", "Build n8n blog-to-newsletter sync", "RSS: blog feed → auto-draft Beehiiv newsletter from new posts", "Automation", "n8n", "Agent", "Medium", "No", "17", "20", "4", "1A-9, 2A-7", "Not Started"],
        ["2A-6", "2", "2A", "Build n8n Beehiiv → Customer.io sync", "Webhook: new subscriber → sync to Customer.io", "Automation", "n8n", "Agent", "High", "No", "17", "20", "4", "2A-7, 0D-2", "Not Started"],
        ["2A-7", "2", "2A", "Create Beehiiv account + configure", "Set up Beehiiv publication, design, connect domain", "Setup", "—", "Nick", "High", "No", "14", "16", "3", "—", "Not Started"],

        # Phase 2B — Product Hunt Launch
        ["2B-1", "2", "2B", "Create PH launch strategy", "Hour-by-hour playbook for launch day, pre-launch outreach plan", "Strategy", "Social Media", "Agent", "High", "No", "14", "18", "5", "—", "Not Started"],
        ["2B-2", "2", "2B", "Write PH listing copy", "Tagline, description, first comment/maker comment", "Copy", "Writer", "Agent", "High", "No", "16", "20", "5", "2B-1", "Not Started"],
        ["2B-3", "2", "2B", "Create 5 PH gallery images", "1270x760 gallery images showcasing product", "Creative", "Visual", "Agent", "High", "No", "18", "24", "7", "2B-1", "Not Started"],
        ["2B-4", "2", "2B", "Write 10 launch day tweets", "Pre-written tweets for launch day cadence", "Copy", "Writer", "Agent", "Medium", "No", "20", "24", "5", "2B-1", "Not Started"],
        ["2B-5", "2", "2B", "Build n8n PH launch day reminders", "Cron every 2h on launch day → Slack reminders + Beehiiv blast trigger", "Automation", "n8n", "Agent", "Medium", "No", "20", "24", "5", "—", "Not Started"],
        ["2B-6", "2", "2B", "Submit PH listing + engage", "Submit listing, engage with all comments on launch day, coordinate network", "Launch", "—", "Nick / Justin", "High", "No", "25", "30", "6", "2B-2, 2B-3", "Not Started"],

        # Phase 2C — Hacker News
        ["2C-1", "2", "2C", "Create HN strategy", "Technical positioning, comment engagement plan, timing strategy", "Strategy", "Social Media", "Agent", "Medium", "No", "20", "24", "5", "—", "Not Started"],
        ["2C-2", "2", "2C", "Write Show HN post draft", "500-word technical post — authentic, engineering-focused", "Copy", "Writer", "Agent", "High", "No", "24", "27", "4", "2C-1", "Not Started"],
        ["2C-3", "2", "2C", "Post to HN from personal account", "Post Show HN, engage with all technical comments", "Launch", "—", "Nick / Justin", "High", "No", "28", "32", "5", "2C-2", "Not Started"],

        # Phase 3A — Paid Retargeting
        ["3A-1", "3", "3A", "Design retargeting campaign architecture", "3 funnel stages: awareness, consideration, conversion — audience definitions", "Strategy", "Performance Marketer", "Agent", "High", "No", "25", "30", "6", "0C-9", "Not Started"],
        ["3A-2", "3", "3A", "Write 6 ad copy variants", "2 variants per funnel stage — benefit-led and pain-led", "Copy", "Writer", "Agent", "High", "No", "27", "32", "6", "3A-1", "Not Started"],
        ["3A-3", "3", "3A", "Create 4 retargeting ad images", "Ad creatives for Meta and Google Display — multiple sizes", "Creative", "Visual", "Agent", "High", "No", "27", "32", "6", "3A-1", "Not Started"],
        ["3A-4", "3", "3A", "Design A/B test plan", "Test matrix: creative × copy × audience for retargeting", "Strategy", "Performance Marketer", "Agent", "Medium", "No", "28", "32", "5", "3A-1", "Not Started"],
        ["3A-5", "3", "3A", "Create ad platform accounts", "Create Meta Business Manager + Google Ads accounts (if needed)", "Setup", "—", "Nick", "High", "No", "28", "30", "3", "—", "Not Started"],
        ["3A-6", "3", "3A", "Upload creatives + launch campaigns", "Upload ad creatives, set budgets ($300-500/mo), launch campaigns", "Setup", "—", "Nick", "High", "No", "30", "35", "6", "3A-2, 3A-3, 3A-5", "Not Started"],
        ["3A-7", "3", "3A", "Build n8n weekly ad spend report", "Cron weekly → fetch Meta/Google ad data → Slack summary", "Automation", "n8n", "Agent", "Medium", "No", "32", "35", "4", "3A-6", "Not Started"],
        ["3A-8", "3", "3A", "Sync Customer.io segments as audiences", "Upload Customer.io segments as custom audiences for suppression (don't retarget paid users)", "Setup", "—", "Nick", "Medium", "No", "30", "35", "6", "0E-7, 3A-5", "Not Started"],

        # Phase 3B — Referral Program
        ["3B-1", "3", "3B", "Design referral program", "Tiers: 3 refs=tips PDF, 5=stickers, 10=1mo free. Paid: refer-a-friend both get 1mo free", "Strategy", "Lifecycle Marketing", "Agent", "High", "No", "30", "34", "5", "0E-1", "Not Started"],
        ["3B-2", "3", "3B", "Write 3 referral emails", "Referral invitation, reminder, reward notification", "Copy", "Writer", "Agent", "Medium", "No", "32", "36", "5", "3B-1", "Not Started"],
        ["3B-3", "3", "3B", "Write referral landing page copy", "Dedicated landing page for referral program", "Copy", "Writer", "Agent", "Medium", "No", "33", "37", "5", "3B-1", "Not Started"],
        ["3B-4", "3", "3B", "Implement referral tracking in codebase", "Unique referral links, credit tracking in agenttunnel.app", "Code", "—", "Justin", "High", "No", "35", "42", "8", "3B-1", "Not Started"],
        ["3B-5", "3", "3B", "Build n8n referral conversion workflow", "Webhook referral_converted → notification + monthly digest", "Automation", "n8n", "Agent", "Medium", "No", "38", "42", "5", "3B-4", "Not Started"],

        # Phase 4A — Developer Community
        ["4A-1", "4", "4A", "Create community engagement strategy", "Target Discord servers, Slack groups, indie hacker forums — engagement plan", "Strategy", "Social Media", "Agent", "Medium", "No", "40", "45", "6", "—", "Not Started"],
        ["4A-2", "4", "4A", "Write tutorial blog series (2/month)", "Deep-dive tutorials on Agent Tunnel use cases — ongoing", "Copy", "Writer", "Agent", "Medium", "No", "45", "90", "45", "4A-1, 1A-1", "Not Started"],
        ["4A-3", "4", "4A", "Add RSS monitoring sources", "Anthropic blog, Cloudflare blog as monitoring sources", "Setup", "Orchestrator", "Agent", "Low", "No", "45", "47", "3", "0A-1", "Not Started"],
        ["4A-4", "4", "4A", "Set up Google Alerts", "Competitor mentions, 'Claude Code mobile', 'AI coding mobile'", "Setup", "—", "Nick", "Low", "No", "45", "47", "3", "—", "Not Started"],
        ["4A-5", "4", "4A", "Join Discord/Slack communities", "Active participation in developer communities", "Community", "—", "Nick / Justin", "Medium", "No", "45", "90", "45", "4A-1", "Not Started"],

        # Phase 4B — Editorial Coordination
        ["4B-1", "4", "4B", "Create 12-week editorial calendar", "Master content calendar across all channels — blog, social, email, newsletter", "Strategy", "Editorial Lead", "Agent", "High", "No", "7", "10", "4", "1A-1, 1C-1, 1D-1", "Not Started"],
        ["4B-2", "4", "4B", "Build 30-item content backlog", "Prioritized content ideas with effort/impact scoring", "Strategy", "Editorial Lead", "Agent", "High", "No", "8", "12", "5", "4B-1", "Not Started"],
        ["4B-3", "4", "4B", "Create 4 weekly content bundles", "Multi-asset content packages (blog + social + email per topic)", "Strategy", "Editorial Lead", "Agent", "Medium", "No", "10", "14", "5", "4B-2", "Not Started"],
        ["4B-4", "4", "4B", "Build content production tracker sheet", "Google Sheet tracking content pipeline status", "Dashboard", "Sheets", "Agent", "Medium", "No", "10", "12", "3", "4B-1", "Not Started"],
    ]
    # fmt: on


def _n8n_workflows_rows() -> List[List[str]]:
    """n8n Workflows tab data."""
    return [
        ["W-01", "Signup → Customer.io", "Webhook: new_signup from agenttunnel.app", "Customer.io Track API: identify person + UTM attributes", "0D", "Phase 0 (CRITICAL)", "Not Started"],
        ["W-02", "Trial activation", "Webhook: first_mobile_session", "Customer.io Track API: event 'first_session_completed'", "0D", "Phase 0 (CRITICAL)", "Not Started"],
        ["W-03", "Stripe → Customer.io (paid)", "Stripe: checkout.session.completed", "Customer.io: update paid=true, track 'upgraded_to_paid'", "0D", "Phase 0 (CRITICAL)", "Not Started"],
        ["W-04", "Stripe → Customer.io (churn)", "Stripe: customer.subscription.deleted", "Customer.io: update paid=false, trigger win-back", "0D", "Phase 0 (CRITICAL)", "Not Started"],
        ["W-05", "New signup notification", "Webhook: new_signup event", "Post to #agent-tunnel Slack with email, UTM, timestamp", "0D", "Phase 0", "Not Started"],
        ["W-06", "Daily metrics digest", "Cron: 8am daily", "Fetch signup/conversion data → Slack summary", "0D", "Phase 0", "Not Started"],
        ["W-07", "Blog publish notification", "RSS: blog feed", "Slack + social queue notification", "1A", "Phase 1", "Not Started"],
        ["W-08", "Reddit keyword alert", "Cron: every 4h", "Scan subreddits for keywords → Slack alert", "1B", "Phase 1", "Not Started"],
        ["W-09", "Blog-to-newsletter sync", "RSS: blog feed", "Auto-draft Beehiiv newsletter from new posts", "2A", "Phase 2", "Not Started"],
        ["W-10", "Beehiiv → Customer.io sync", "Webhook: new subscriber", "Sync subscriber to Customer.io", "2A", "Phase 2", "Not Started"],
        ["W-11", "PH launch day reminders", "Cron: every 2h on launch day", "Slack reminders + Beehiiv blast trigger", "2B", "Phase 2", "Not Started"],
        ["W-12", "Weekly ad spend report", "Cron: weekly", "Fetch Meta/Google ad data → Slack summary", "3A", "Phase 3", "Not Started"],
        ["W-13", "Referral conversion", "Webhook: referral_converted", "Notification + monthly digest", "3B", "Phase 3", "Not Started"],
    ]


def _human_actions_rows() -> List[List[str]]:
    """Human Actions tab data."""
    return [
        ["H-01", "0C", "Create GTM account + install GTM snippet on agenttunnel.app (GitHub PR)", "Justin", "YES", "—", "Not Started"],
        ["H-02", "0C", "Install Meta Pixel, Google Ads tag, LinkedIn Insight Tag, Customer.io snippet in GTM", "Nick", "YES", "H-01", "Not Started"],
        ["H-03", "0C", "Verify all GTM tags fire correctly via GTM preview mode", "Justin / Nick", "YES", "H-01, H-02", "Not Started"],
        ["H-04", "0D", "Create Customer.io account + generate API keys + add to n8n", "Nick", "YES", "—", "Not Started"],
        ["H-05", "0D", "Add signup webhook to agenttunnel.app (POST to n8n on new user)", "Justin", "YES", "H-04", "Not Started"],
        ["H-06", "0E", "Build campaign flows in Customer.io UI (segments, triggers, email campaigns)", "Nick", "YES", "H-04", "Not Started"],
        ["H-07", "0E", "Test lifecycle email flow end-to-end with a test signup", "Nick", "YES", "H-06", "Not Started"],
        ["H-08", "0F", "Implement CRO copy/design changes to agenttunnel.app (merge GitHub PRs)", "Justin / Nick", "No", "—", "Not Started"],
        ["H-09", "1A", "Publish blog posts to website CMS (or build blog section)", "Justin / Nick", "No", "—", "Not Started"],
        ["H-10", "1B", "Post all Reddit content personally (TOS requirement)", "Nick / Justin", "No", "—", "Not Started"],
        ["H-11", "1C", "Create @AgentTunnel Twitter account + post all drafted content", "Nick / Justin", "No", "—", "Not Started"],
        ["H-12", "1D", "Post LinkedIn content from personal profiles", "Nick / Justin", "No", "—", "Not Started"],
        ["H-13", "2A", "Create Beehiiv account + configure publication settings", "Nick", "No", "—", "Not Started"],
        ["H-14", "2B", "Submit Product Hunt listing + engage with comments on launch day", "Nick / Justin", "No", "—", "Not Started"],
        ["H-15", "2C", "Post Show HN from personal account (needs karma)", "Nick / Justin", "No", "—", "Not Started"],
        ["H-16", "3A", "Create Meta Business Manager + Google Ads accounts, upload creatives, set budgets", "Nick", "No", "—", "Not Started"],
        ["H-17", "3B", "Implement referral tracking in agenttunnel.app codebase", "Justin", "No", "—", "Not Started"],
        ["H-18", "4A", "Join and participate in developer Discord/Slack communities", "Nick / Justin", "No", "—", "Not Started"],
        ["H-19", "Ongoing", "Weekly: review and post social content, review email performance, check ad spend", "Nick / Justin", "No", "—", "Not Started"],
        ["H-20", "Ongoing", "Monthly: review MRR targets, adjust budgets, founder outreach to churned users", "Nick / Justin", "No", "—", "Not Started"],
    ]


def _milestones_rows() -> List[List[str]]:
    """Milestones & Gates tab data."""
    return [
        ["M-01", "1", "Workspace registered in CMO Agent", "0A complete", "No", "—"],
        ["M-02", "3", "Analytics framework complete", "0B complete — measurement, events, UTMs defined", "No", "M-01"],
        ["M-03", "5", "GATE: GTM verified on agenttunnel.app", "All GTM tags fire correctly — retargeting pixels live", "YES", "M-02"],
        ["M-04", "7", "GATE: Customer.io integration live", "All 5 n8n workflows operational — signup/trial/paid/churn/metrics", "YES", "M-03"],
        ["M-05", "10", "GATE: Lifecycle emails operational", "14 emails built in Customer.io — E2E test passed", "YES", "M-04"],
        ["M-06", "10", "Phase 0 complete — launch infrastructure ready", "Analytics + GTM + Customer.io + lifecycle emails + CRO = all operational", "YES", "M-03, M-04, M-05"],
        ["M-07", "14", "Editorial calendar published", "12-week content plan across all channels", "No", "M-06"],
        ["M-08", "14", "SEO engine running", "Keyword clusters defined, first blog posts in production", "No", "M-06"],
        ["M-09", "21", "Organic channels active", "Reddit, Twitter/X, LinkedIn all posting — 2+ weeks of content", "No", "M-06"],
        ["M-10", "21", "Newsletter launched", "Beehiiv live, welcome email active, first newsletter sent", "No", "M-09"],
        ["M-11", "30", "Product Hunt launch", "PH listing live, top-5 target, launch day executed", "No", "M-09, M-10"],
        ["M-12", "32", "Hacker News launch", "Show HN posted, 2-3 days after PH for momentum", "No", "M-11"],
        ["M-13", "35", "Paid retargeting live", "Meta + Google retargeting campaigns launched ($300-500/mo)", "No", "M-03"],
        ["M-14", "42", "Referral program launched", "Referral tracking live, referral emails active, tiers configured", "No", "M-13"],
        ["M-15", "60", "Mid-point review", "Assess: users, MRR, CAC, channel performance — adjust strategy", "No", "—"],
        ["M-16", "90", "90-day checkpoint", "Target: 500 paid users, $7,500 MRR, 3:1 LTV:CAC", "No", "—"],
    ]


def _budget_rows() -> List[List[str]]:
    """Budget tab data."""
    return [
        ["Meta retargeting", "$150", "$500", "Phase 3+", "Retargeting site visitors and trial dropoffs"],
        ["Google Display retargeting", "$100", "$300", "Phase 3+", "Display network retargeting"],
        ["Image generation (DALL-E)", "$10", "$40", "All phases", "Blog images, social images, ad creatives"],
        ["Video generation (fal.ai)", "$5", "$25", "Phase 0+", "Demo videos, motion graphics"],
        ["LLM costs (Anthropic API)", "$50", "$150", "All phases", "Content generation, strategy, analysis"],
        ["Beehiiv", "$0", "$49", "Phase 2+", "Newsletter platform"],
        ["Customer.io", "$0", "$100", "Phase 0+", "Lifecycle marketing platform"],
        ["Reserve for experiments", "$185", "$836", "All phases", "Unallocated budget for testing new channels"],
        ["TOTAL", "$500", "$2,000", "—", "—"],
    ]


# ── Google Sheet Builder ─────────────────────────────────────────────────

def build_sheet(sheets_service: Any, drive_service: Any) -> str:
    """Create the Google Sheet and return its URL."""

    # ── 1. Define sheets ──────────────────────────────────────────────
    sheet_defs = [
        {"properties": {"sheetId": 0, "title": "Work Plan", "index": 0}},
        {"properties": {"sheetId": 1, "title": "n8n Workflows", "index": 1}},
        {"properties": {"sheetId": 2, "title": "Human Actions", "index": 2}},
        {"properties": {"sheetId": 3, "title": "Milestones & Gates", "index": 3}},
        {"properties": {"sheetId": 4, "title": "Budget", "index": 4}},
    ]

    print("  Creating spreadsheet...")
    result = sheets_service.spreadsheets().create(
        body={
            "properties": {"title": SPREADSHEET_TITLE},
            "sheets": sheet_defs,
        }
    ).execute()
    spreadsheet_id = result["spreadsheetId"]
    print(f"  Spreadsheet ID: {spreadsheet_id}")

    # ── 2. Populate data ─────────────────────────────────────────────
    tabs: List[Tuple[str, List[str], List[List[str]]]] = [
        (
            "Work Plan",
            ["Task ID", "Phase", "Sub-Phase", "Task Name", "Description", "Deliverable Type", "Agent / Tool", "Owner", "Priority", "Blocking?", "Day Start", "Day End", "Duration", "Dependencies", "Status"],
            _work_plan_rows(),
        ),
        (
            "n8n Workflows",
            ["Workflow ID", "Workflow Name", "Trigger", "Action", "Sub-Phase", "Priority", "Status"],
            _n8n_workflows_rows(),
        ),
        (
            "Human Actions",
            ["Action ID", "Phase", "Action", "Owner", "Blocking?", "Dependencies", "Status"],
            _human_actions_rows(),
        ),
        (
            "Milestones & Gates",
            ["Milestone ID", "Day", "Milestone", "Description", "Gate?", "Dependencies"],
            _milestones_rows(),
        ),
        (
            "Budget",
            ["Category", "Min ($500/mo)", "Max ($2,000/mo)", "Phase", "Notes"],
            _budget_rows(),
        ),
    ]

    value_ranges = []
    for sheet_name, headers, rows in tabs:
        all_rows = [headers] + rows
        value_ranges.append({
            "range": f"'{sheet_name}'!A1",
            "values": all_rows,
        })

    print("  Populating data...")
    sheets_service.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={
            "valueInputOption": "USER_ENTERED",
            "data": value_ranges,
        },
    ).execute()

    # ── 3. Apply formatting ──────────────────────────────────────────
    print("  Applying formatting...")
    format_requests = _build_format_requests(tabs)
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id,
        body={"requests": format_requests},
    ).execute()

    # ── 4. Share (restricted access) ─────────────────────────────────
    print("  Sharing spreadsheet...")
    share_file_restricted(drive_service, spreadsheet_id)

    # ── 5. Move to CMO Agent folder ──────────────────────────────────
    _move_to_folder(drive_service, spreadsheet_id)

    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
    return url


def _build_format_requests(
    tabs: List[Tuple[str, List[str], List[List[str]]]],
) -> List[Dict[str, Any]]:
    """Build formatting requests for all tabs."""
    requests: List[Dict[str, Any]] = []

    # Tab-specific column widths
    col_widths_map = {
        "Work Plan": [70, 50, 70, 200, 350, 100, 140, 90, 70, 70, 60, 60, 60, 120, 90],
        "n8n Workflows": [80, 200, 250, 300, 70, 120, 90],
        "Human Actions": [70, 70, 400, 90, 70, 100, 90],
        "Milestones & Gates": [80, 50, 200, 350, 50, 120],
        "Budget": [200, 100, 120, 80, 300],
    }

    # Color scheme
    header_bg = {"red": 0.18, "green": 0.20, "blue": 0.30}  # Dark navy
    header_fg = {"red": 1.0, "green": 1.0, "blue": 1.0}  # White text
    band_1 = {"red": 1.0, "green": 1.0, "blue": 1.0}  # White
    band_2 = {"red": 0.93, "green": 0.95, "blue": 0.98}  # Light blue-gray
    border_color = {"red": 0.78, "green": 0.80, "blue": 0.84}

    for tab_idx, (sheet_name, headers, rows) in enumerate(tabs):
        sheet_id = tab_idx
        num_cols = len(headers)
        num_rows = 1 + len(rows)
        col_widths = col_widths_map.get(sheet_name, [])

        # Bold header row with dark background and white text
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {"bold": True, "foregroundColorStyle": {"rgbColor": header_fg}},
                        "backgroundColor": header_bg,
                        "horizontalAlignment": "CENTER",
                        "verticalAlignment": "MIDDLE",
                        "wrapStrategy": "WRAP",
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor,horizontalAlignment,verticalAlignment,wrapStrategy)",
            }
        })

        # Freeze header row
        requests.append({
            "updateSheetProperties": {
                "properties": {
                    "sheetId": sheet_id,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        })

        # Alternating row banding
        if num_rows > 1:
            requests.append({
                "addBanding": {
                    "bandedRange": {
                        "range": {
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": num_rows,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        },
                        "rowProperties": {
                            "firstBandColor": band_1,
                            "secondBandColor": band_2,
                        },
                    }
                }
            })

        # Borders
        requests.append({
            "updateBorders": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 0,
                    "endRowIndex": num_rows,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols,
                },
                "top": {"style": "SOLID", "width": 1, "color": border_color},
                "bottom": {"style": "SOLID", "width": 1, "color": border_color},
                "left": {"style": "SOLID", "width": 1, "color": border_color},
                "right": {"style": "SOLID", "width": 1, "color": border_color},
                "innerHorizontal": {"style": "SOLID", "width": 1, "color": border_color},
                "innerVertical": {"style": "SOLID", "width": 1, "color": border_color},
            }
        })

        # Column widths
        for j, width in enumerate(col_widths):
            if j >= num_cols:
                break
            requests.append({
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": j,
                        "endIndex": j + 1,
                    },
                    "properties": {"pixelSize": width},
                    "fields": "pixelSize",
                }
            })

        # Wrap text in data rows
        requests.append({
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": num_rows,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "wrapStrategy": "WRAP",
                        "verticalAlignment": "TOP",
                    }
                },
                "fields": "userEnteredFormat(wrapStrategy,verticalAlignment)",
            }
        })

    # ── Work Plan tab: Conditional formatting for Status column ─────
    # Status is column O (index 14) in Work Plan (sheet 0)
    wp_rows = _work_plan_rows()
    wp_num_rows = 1 + len(wp_rows)

    # "Not Started" → light red background
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": 0,
                    "startRowIndex": 1,
                    "endRowIndex": wp_num_rows,
                    "startColumnIndex": 14,
                    "endColumnIndex": 15,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Not Started"}]},
                    "format": {"backgroundColor": {"red": 0.96, "green": 0.88, "blue": 0.88}},
                },
            },
            "index": 0,
        }
    })

    # "In Progress" → light yellow
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": 0,
                    "startRowIndex": 1,
                    "endRowIndex": wp_num_rows,
                    "startColumnIndex": 14,
                    "endColumnIndex": 15,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "In Progress"}]},
                    "format": {"backgroundColor": {"red": 1.0, "green": 0.95, "blue": 0.75}},
                },
            },
            "index": 1,
        }
    })

    # "Complete" → light green
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": 0,
                    "startRowIndex": 1,
                    "endRowIndex": wp_num_rows,
                    "startColumnIndex": 14,
                    "endColumnIndex": 15,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Complete"}]},
                    "format": {"backgroundColor": {"red": 0.82, "green": 0.94, "blue": 0.82}},
                },
            },
            "index": 2,
        }
    })

    # Blocking? = "YES" → bold red text in Work Plan
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": 0,
                    "startRowIndex": 1,
                    "endRowIndex": wp_num_rows,
                    "startColumnIndex": 9,
                    "endColumnIndex": 10,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "YES"}]},
                    "format": {
                        "textFormat": {"bold": True, "foregroundColor": {"red": 0.8, "green": 0.1, "blue": 0.1}},
                        "backgroundColor": {"red": 1.0, "green": 0.9, "blue": 0.9},
                    },
                },
            },
            "index": 3,
        }
    })

    # Priority = "Critical" → bold in Work Plan
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": 0,
                    "startRowIndex": 1,
                    "endRowIndex": wp_num_rows,
                    "startColumnIndex": 8,
                    "endColumnIndex": 9,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Critical"}]},
                    "format": {
                        "textFormat": {"bold": True, "foregroundColor": {"red": 0.7, "green": 0.0, "blue": 0.0}},
                    },
                },
            },
            "index": 4,
        }
    })

    # ── Human Actions tab: Blocking? = "YES" conditional formatting ─
    ha_rows = _human_actions_rows()
    ha_num_rows = 1 + len(ha_rows)
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": 2,
                    "startRowIndex": 1,
                    "endRowIndex": ha_num_rows,
                    "startColumnIndex": 4,
                    "endColumnIndex": 5,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "YES"}]},
                    "format": {
                        "textFormat": {"bold": True, "foregroundColor": {"red": 0.8, "green": 0.1, "blue": 0.1}},
                        "backgroundColor": {"red": 1.0, "green": 0.9, "blue": 0.9},
                    },
                },
            },
            "index": 5,
        }
    })

    # ── Milestones tab: Gate? = "YES" conditional formatting ─────
    ms_rows = _milestones_rows()
    ms_num_rows = 1 + len(ms_rows)
    requests.append({
        "addConditionalFormatRule": {
            "rule": {
                "ranges": [{
                    "sheetId": 3,
                    "startRowIndex": 1,
                    "endRowIndex": ms_num_rows,
                    "startColumnIndex": 4,
                    "endColumnIndex": 5,
                }],
                "booleanRule": {
                    "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "YES"}]},
                    "format": {
                        "textFormat": {"bold": True, "foregroundColor": {"red": 0.8, "green": 0.1, "blue": 0.1}},
                        "backgroundColor": {"red": 1.0, "green": 0.9, "blue": 0.9},
                    },
                },
            },
            "index": 6,
        }
    })

    # ── Status columns conditional formatting for other tabs ────
    for sheet_id, status_col, total_rows in [
        (1, 6, 1 + len(_n8n_workflows_rows())),   # n8n Workflows
        (2, 6, ha_num_rows),                        # Human Actions
    ]:
        for rule_idx, (value, bg) in enumerate([
            ("Not Started", {"red": 0.96, "green": 0.88, "blue": 0.88}),
            ("In Progress", {"red": 1.0, "green": 0.95, "blue": 0.75}),
            ("Complete", {"red": 0.82, "green": 0.94, "blue": 0.82}),
        ]):
            requests.append({
                "addConditionalFormatRule": {
                    "rule": {
                        "ranges": [{
                            "sheetId": sheet_id,
                            "startRowIndex": 1,
                            "endRowIndex": total_rows,
                            "startColumnIndex": status_col,
                            "endColumnIndex": status_col + 1,
                        }],
                        "booleanRule": {
                            "condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": value}]},
                            "format": {"backgroundColor": bg},
                        },
                    },
                    "index": 7 + sheet_id * 3 + rule_idx,
                }
            })

    # ── Data validation: Status dropdown ──────────────────────────
    status_values = ["Not Started", "In Progress", "Complete", "Blocked", "Skipped"]
    for sheet_id, status_col, total_rows in [
        (0, 14, wp_num_rows),
        (1, 6, 1 + len(_n8n_workflows_rows())),
        (2, 6, ha_num_rows),
    ]:
        requests.append({
            "setDataValidation": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": 1,
                    "endRowIndex": total_rows,
                    "startColumnIndex": status_col,
                    "endColumnIndex": status_col + 1,
                },
                "rule": {
                    "condition": {
                        "type": "ONE_OF_LIST",
                        "values": [{"userEnteredValue": v} for v in status_values],
                    },
                    "showCustomUi": True,
                    "strict": False,
                },
            }
        })

    # ── Data validation: Priority dropdown in Work Plan ───────────
    priority_values = ["Critical", "High", "Medium", "Low"]
    requests.append({
        "setDataValidation": {
            "range": {
                "sheetId": 0,
                "startRowIndex": 1,
                "endRowIndex": wp_num_rows,
                "startColumnIndex": 8,
                "endColumnIndex": 9,
            },
            "rule": {
                "condition": {
                    "type": "ONE_OF_LIST",
                    "values": [{"userEnteredValue": v} for v in priority_values],
                },
                "showCustomUi": True,
                "strict": False,
            },
        }
    })

    return requests


def _move_to_folder(drive_service: Any, file_id: str) -> None:
    """Move spreadsheet to the CMO Agent folder in Google Drive."""
    # Find or create CMO Agent folder
    results = drive_service.files().list(
        q="name='CMO Agent' and mimeType='application/vnd.google-apps.folder' and trashed=false",
        spaces="drive",
        fields="files(id)",
    ).execute()
    folders = results.get("files", [])

    if folders:
        folder_id = folders[0]["id"]
    else:
        folder = drive_service.files().create(
            body={
                "name": "CMO Agent",
                "mimeType": "application/vnd.google-apps.folder",
            },
            fields="id",
        ).execute()
        folder_id = folder["id"]

    # Move file to folder
    file_meta = drive_service.files().get(
        fileId=file_id, fields="parents"
    ).execute()
    prev_parents = ",".join(file_meta.get("parents", []))
    drive_service.files().update(
        fileId=file_id,
        addParents=folder_id,
        removeParents=prev_parents,
        fields="id, parents",
    ).execute()
    print(f"  Moved to CMO Agent folder ({folder_id})")


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

    from googleapiclient.discovery import build

    from cmo_agent.config import Settings
    from cmo_agent.google_auth import get_google_credentials, share_file_restricted

    settings = Settings()
    creds = get_google_credentials(
        oauth_token_path=settings.google_oauth_token_path,
        service_account_path=settings.google_credentials_path,
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    if not creds:
        print("ERROR: No Google credentials available. Check .env settings.")
        sys.exit(1)

    sheets_service = build("sheets", "v4", credentials=creds)
    drive_service = build("drive", "v3", credentials=creds)

    print(f"Creating '{SPREADSHEET_TITLE}'...")
    url = build_sheet(sheets_service, drive_service)
    print(f"\nDone! View at: {url}")


if __name__ == "__main__":
    main()
