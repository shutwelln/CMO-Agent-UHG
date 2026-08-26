# Agent Reference

CMO Agent includes 34 specialized sub-agents organized into six divisions. Each agent is registered as a tool on the orchestrator, which decides when to delegate based on your request.

## Content Production

| Agent | ID | What It Does |
|-------|-----|-------------|
| **Writer** | `writer_agent` | Content generation in brand voice: blog posts, newsletters, social posts, Reddit replies. Quality refinement loop with proofreading. |
| **Visual** | `create_visual` | AI image generation: photography, illustrations, abstract visuals (textless). Supports Gemini, DALL-E, SDXL. |
| **Video** | `video_agent` | Video scripts, storyboards, shot lists. AI video generation via fal.ai/Kling/Sora. |
| **Deck** | `deck_agent` | Google Slides presentations and pitch decks. |
| **Docs** | `docs_agent` | Google Docs creation: reports, briefs, proposals, blog posts. |
| **Sheets** | `sheets_agent` | Google Sheets creation: campaign trackers, budgets, analytics dashboards. |
| **Motion Graphics** | `motion_graphics_agent` | Programmatic animations via Remotion: text animations, data visualizations, branded intros. |
| **Composition Planner** | `composition_planner_agent` | Text-on-visual pipeline: plan, validate, render compositions using parametric templates. |

## Marketing Strategy

| Agent | ID | What It Does |
|-------|-----|-------------|
| **Performance Marketer** | `performance_marketer_agent` | Paid ad strategy, campaign architecture, A/B testing, budget allocation. |
| **Social Media** | `social_media_agent` | Content calendars, platform strategy, hashtag research, engagement planning. |
| **Lifecycle Marketing** | `lifecycle_marketing_agent` | Email/SMS/push/in-product flows, segmentation, trigger logic, compliance. |
| **Growth Ideas** | `growth_ideas_agent` | Daily growth ideas from recent activity, impact/effort scoring, Slack digest. |
| **Marketing Analytics** | `marketing_analytics_agent` | GA4 measurement, UTM governance, attribution modeling, tracking specs. |
| **Acquisition** | `acquisition_agent` | Micro funnel optimization, landing pages, friction analysis, drop-off diagnosis. |
| **Conversion Optimization** | `conversion_optimization_agent` | On-site experiments, A/B tests, variant briefs, statistical validation. |
| **GTM Strategy** | `gtm_agent` | Go-to-market strategy, ICP definition, beachhead selection, channel strategy. |
| **SEO/AEO Architect** | `seo_aeo_agent` | SEO/AEO/GEO strategy, keyword architecture, structured data, organic briefs. |

## Sales & Revenue

| Agent | ID | What It Does |
|-------|-----|-------------|
| **Telesales** | `telesales_agent` | Call center design, call scripting, dialing strategy, voice AI evaluation, QA. |
| **Sales Operations** | `sales_ops_agent` | CRM pipelines, sales automation, lead scoring, partner revenue workflows. |
| **LinkedIn Partnerships** | `linkedin_partnerships_agent` | LinkedIn prospecting, outreach sequences, A/B testing, CRM tracking. |

## Legal & Compliance

| Agent | ID | What It Does |
|-------|-----|-------------|
| **Compliance** | `compliance_agent` | Regulatory review: FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA, insurance regs. |
| **Legal Strategy** | `legal_strategy_agent` | Contract drafting, NDAs, term sheets, risk flagging, negotiation strategy. |

## Nonprofit / DSDN

These agents are purpose-built for the Down Syndrome Diagnosis Network (DSDN) but can be adapted for other nonprofits:

| Agent | ID | What It Does |
|-------|-----|-------------|
| **DSDN Ideas** | `dsdn_ideas_agent` | Mission-specific daily ideas with 4-dimension scoring. |
| **Grant Intelligence** | `grant_intelligence_agent` | Grant discovery, eligibility assessment, win probability scoring. |
| **Grant Writing** | `grant_writing_agent` | Grant proposal drafting: narratives, budget narratives, evaluation plans. |
| **Corporate Sponsorship** | `corporate_sponsorship_agent` | Sponsor targeting, tier design, outreach, impact/ROI modeling. |
| **Ecosystem Intelligence** | `ecosystem_intelligence_agent` | Org landscape scanning, service gap analysis, partnership fit scoring. |
| **Outreach Scanner** | `outreach_scanner_agent` | Reddit/forum scanning for families, draft replies, team workflow. |
| **DSDN TikTok** | `dsdn_tiktok_agent` | TikTok trends, content packages, series, media catalog. |

## Operations & Intelligence

| Agent | ID | What It Does |
|-------|-----|-------------|
| **Research** | `research_agent` | RSS feeds, fraud monitoring, opportunity scoring. |
| **Reddit Ingest** | `reddit_ingest_agent` | Reddit subreddit monitoring via public JSON feeds. |
| **Google Alerts** | `google_alerts_agent` | Gmail scanning for Google Alert emails. |
| **Knowledge Base** | `knowledge_base_agent` | Durable cross-session memory, keyword search, fact recall. |
| **Experiment Engineer** | `experiment_engineer_agent` | Experiment lifecycle, hypothesis-driven design, event schemas. |
| **Editorial Lead** | `editorial_agent` | Editorial calendars, content backlog, publish checklists. |
| **Workflow Builder** | `workflow_builder_agent` | Build new n8n workflows from natural language. |
| **Workflow Healer** | `workflow_healer_agent` | Diagnose, repair, and rollback broken n8n workflows. |

## Disabling Agents

To disable specific agents, add their IDs to `DISABLED_AGENTS` in your `.env` file:

```
DISABLED_AGENTS=dsdn_ideas_agent,dsdn_tiktok_agent,outreach_scanner_agent,grant_intelligence_agent,grant_writing_agent,corporate_sponsorship_agent,ecosystem_intelligence_agent
```

Disabled agents are not constructed at startup and consume zero resources.
