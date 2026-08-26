# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CMO Agent for UnitedHealth Group / Optum is an AI-powered marketing automation system with a multi-agent architecture. It is the UHG-focused descendant of a brand-agnostic CMO Agent platform: same orchestration core, same agent ecosystem, but scoped to UHG / Optum / Optum Financial / Optum Bank.

The system integrates with n8n workflows and exposes three interaction surfaces: a CLI chat, a FastAPI web UI, and a Slack bot (Socket Mode). It uses Anthropic Claude as its LLM with model-per-role assignment (Haiku for scanning, Sonnet for writing, Opus available for premium reasoning).

The default workspace is `uhg` (auto-seeded on first DB init). The multi-tenant workspace infrastructure remains in place — sub-brand workspaces (`optum`, `optum_financial`, `optum_bank`) can be added later without code changes by adding a workspaces row plus a brand voice file under `data/brand_voices/`.

## Build & Run Commands

```bash
# Install (editable, into .venv)
source .venv/bin/activate
pip install -e .          # production deps
pip install -e ".[dev]"   # + pytest, ruff, mypy, respx

# Run tests
pytest                            # all tests
pytest tests/unit/test_tools.py   # single test file
pytest -k "test_normalize_nodes"  # single test by name

# Lint & type check
ruff check src/ tests/
ruff format src/ tests/
mypy src/

# Run the app
cmo chat                  # interactive CLI
cmo serve --reload        # web UI at localhost:8000 (includes /api/media endpoint)
cmo slack                 # Slack bot (requires SLACK_BOT_TOKEN + SLACK_APP_TOKEN)
cmo status                # health check + connection test
cmo workflows             # list n8n workflows
cmo execute <ID>          # run a workflow
```

## Architecture

### Multi-Agent System

```
CMO Orchestrator Agent (Sonnet)
├── Research Agent (Haiku)                — RSS feeds, fraud monitoring, opportunity scoring
├── Reddit Ingest Agent (Haiku)           — Reddit subreddit monitoring via public JSON feeds
├── Google Alerts Ingest Agent (Haiku)    — Gmail scanning for Google Alert emails via n8n
├── Writer Agent (Sonnet)                 — Content generation in brand voice, Ralph-style refinement, proofreading
├── Visual Agent (Sonnet)                 — Image generation: photography, illustrations, abstract visuals (textless only)
├── Video Agent (Sonnet)                  — Video scripts, storyboards, shot lists, AI video generation (fal.ai/Runway/Sora)
├── Deck Agent (Sonnet)                   — PowerPoint presentations and Google Slides decks
├── Docs Agent (Sonnet)                   — Google Docs creation: reports, briefs, proposals, newsletters
├── Sheets Agent (Sonnet)                 — Google Sheets creation: trackers, budgets, analytics dashboards
├── Performance Marketer Agent (Sonnet)   — Paid ads, campaign architecture, A/B testing, budget allocation
├── Lifecycle Marketing Agent (Sonnet)    — Email/SMS/push/in-product flows, segmentation, triggers, compliance (Customer.io, Beehiiv)
├── Motion Graphics Agent (Sonnet)        — Programmatic animations via Remotion: text, data viz, branded intros
├── Marketing Analytics Agent (Sonnet)    — GA4 measurement, UTM governance, attribution modeling, tracking specs, dashboards
├── Growth Ideas Agent (Sonnet)           — Daily growth ideas from recent activity, impact/effort scoring, Slack digest
├── Acquisition Agent (Sonnet)            — Micro funnel optimization, landing pages, friction analysis, drop-off diagnosis
├── Conversion Optimization Agent (Sonnet) — On-site experiments, A/B tests, experiment governance, variant briefs, statistical validation
├── GTM Agent (Sonnet)                    — Go-to-market strategy, ICP, beachhead selection, channel strategy, launch phasing
├── Compliance Agent (Sonnet)             — Regulatory compliance: FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA, state insurance regs
├── Legal Strategy Agent (Sonnet)         — Contract drafting, NDAs, term sheets, risk flagging, negotiation strategy
├── Telesales Agent (Sonnet)              — Call center design, scripting, voice AI evaluation, CRM integration, QA frameworks
├── Sales Operations Agent (Sonnet)       — Revenue process design, CRM pipelines, sales automation, lead scoring, comp models (n8n-aware)
├── LinkedIn Partnerships Agent (Sonnet)  — LinkedIn lead gen: ICP profiling, prospecting, outreach sequences, CRM tracking
├── Knowledge Base Agent (Sonnet)         — Durable cross-session memory: store, search, recall facts; confidence scoring, auto-redaction
├── Experiment Engineer Agent (Sonnet)    — Structured experiments: lifecycle tracking, hypothesis-driven, readouts, event schemas
├── Editorial Lead Agent (Sonnet)         — Editorial coordination: calendars, backlog, bundles, publish checklists (does NOT write content)
├── Social Media Manager Agent (Sonnet)   — Content calendars, platform strategy, hashtag research, engagement planning
├── SEO & AEO Growth Architect (Sonnet)   — SEO/AEO/GEO strategy, keyword architecture, schema, AI crawler optimization
├── Composition Planner Agent (Sonnet)    — Atomic text-on-visual pipeline via create_composed_visual: plan → validate → render → upload
├── UX/UI Design Agent (Sonnet)           — UX audits, design systems, component specs, navigation, accessibility, interaction design
├── Workflow Builder Agent (Sonnet)       — Build new n8n workflows from natural language: design, deploy, test, activate
└── Workflow Healer Agent (Haiku)         — Self-healing: diagnose, repair, rollback broken n8n workflows
```

### Request Flow

All three surfaces (CLI, Web, Slack) converge on the same pipeline:

```
CLI / Web / Slack
      |
  CMOSession  (runtime/session.py — unified async session, context manager)
      |
  AgentFactory  (agents/factory.py — constructs all agents with proper LLM models)
      |
  CMOOrchestratorAgent  (agents/orchestrator.py — delegates to sub-agents as tools)
      |
  ┌───┴───────────────┐
  Sub-agents             Direct tools         Shared services
  (research, reddit,     (n8n workflows,      (MediaStorage —
   google_alerts,         workspace config,     Supabase CDN +
   writer, visual,        draft management,     media_assets DB)
   video, deck, docs,     media library)
   sheets, motion_graphics,
   performance_marketer,
   lifecycle_marketing,
   marketing_analytics,
   growth_ideas,
   acquisition,
   conversion_optimization,
   gtm, compliance, legal_strategy,
   telesales, sales_ops,
   linkedin_partnerships,
   knowledge_base, experiment_engineer,
   editorial, social_media,
   seo_aeo, composition_planner,
   ux_ui_design,
   workflow_builder, workflow_healer)
```

`CMOSession.ask()` resolves the workspace from user input (defaulting to `uhg`), then routes through the orchestrator. The orchestrator's LLM decides which sub-agents to invoke based on tool descriptions.

### Agent Design Pattern

Each agent inherits from `BaseAgent` (agents/base.py) which provides:
- A ReAct-style execution loop (think → act → observe → repeat, max 10 iterations)
- A `ToolRegistry` for registering tools
- Abstract methods: `get_system_prompt()` and `register_tools()`

Sub-agents are registered as **tools** on the orchestrator's ToolRegistry. Each sub-agent gets a fresh `AgentContext` per invocation — it does not see the full user conversation.

### Multi-Tenant Workspace System

The system supports multiple workspaces. Today there is one: `uhg`. Every operation carries a `workspace_id`:
- **sources** table: monitoring sources (subreddits, RSS, Gmail filters) per workspace
- **opportunities** table: discovered content tagged per workspace
- **drafts** table: generated content per workspace
- **config** table: per-workspace keywords, settings
- **brand voice files**: per-workspace in `data/brand_voices/`
- **Slack channels**: per-workspace notification channels

Adding sub-brand workspaces (e.g., `optum_financial`, `optum_bank`) requires zero code changes — just a DB row plus a brand voice file. The auto-seed at `Database.initialize()` creates the default `uhg` row on first launch.

### Key Modules

- **`agents/base.py`** — `BaseAgent` abstract class with ReAct loop, `AgentResult` model
- **`agents/orchestrator.py`** — CMO Orchestrator that registers sub-agents as tools + n8n tools
- **`agents/factory.py`** — `AgentFactory` constructs all agents with model assignments
- **`agents/registry.py`** — `AgentRegistry` maps agent IDs to instances
- **`agents/research.py`** — RSS feeds, fraud monitoring, opportunity scoring (Haiku)
- **`agents/reddit_ingest.py`** — Reddit subreddit monitoring (Haiku)
- **`agents/google_alerts.py`** — Gmail/Google Alerts scanning via n8n (Haiku)
- **`agents/writer.py`** — Content generation with brand voice, quality refinement, proofreading (Sonnet)
- **`agents/visual.py`** — Image generation: photography, illustrations, abstract visuals — textless only (Sonnet)
- **`agents/video.py`** — Video scripts, storyboards, shot lists, AI video generation (Sonnet)
- **`agents/deck.py`** — PowerPoint and Google Slides decks (Sonnet)
- **`agents/docs.py`** — Google Docs creation (Sonnet)
- **`agents/sheets.py`** — Google Sheets creation (Sonnet)
- **`agents/lifecycle_marketing.py`** — Email/SMS/push/in-product flows (Sonnet)
- **`agents/performance_marketer.py`** — Paid ad strategy, campaigns, A/B testing (Sonnet)
- **`agents/social_media.py`** — Content calendars, platform strategy (Sonnet)
- **`agents/motion_graphics.py`** — Programmatic motion graphics via Remotion (Sonnet)
- **`agents/marketing_analytics.py`** — GA4, UTM, attribution, tracking specs (Sonnet)
- **`agents/growth_ideas.py`** — Daily growth ideas, scoring, Slack digest (Sonnet)
- **`agents/acquisition.py`** — Funnel architecture, friction analysis (Sonnet)
- **`agents/conversion_optimization.py`** — On-site experiments, A/B test design (Sonnet)
- **`agents/gtm.py`** — GTM strategy, ICP, channel strategy, launch phasing (Sonnet)
- **`agents/compliance.py`** — Regulatory review: FINRA, SEC, TCPA, CAN-SPAM, GDPR, CCPA, state insurance regs (Sonnet)
- **`agents/legal_strategy.py`** — Contract drafting, NDAs, risk flagging (Sonnet)
- **`agents/telesales.py`** — Call center design, scripting, voice AI (Sonnet)
- **`agents/sales_ops.py`** — CRM pipelines, sales automation, lead scoring (Sonnet)
- **`agents/linkedin_partnerships.py`** — LinkedIn lead gen, outreach sequences (Sonnet)
- **`agents/knowledge_base.py`** — Durable JSONL memory, workspace-scoped (Sonnet)
- **`agents/experiment_engineer.py`** — Experiment lifecycle, event schemas (Sonnet)
- **`agents/editorial.py`** — Editorial calendars, backlog, bundles (Sonnet)
- **`agents/seo_aeo.py`** — SEO/AEO/GEO strategy, schema, organic briefs (Sonnet)
- **`agents/composition_planner.py`** — Atomic text-on-visual pipeline (Sonnet)
- **`agents/ux_ui_design.py`** — UX audits, design systems, component specs (Sonnet)
- **`agents/workflow_builder.py`** — Build new n8n workflows from natural language (Sonnet)
- **`agents/workflow_healer.py`** — Self-healing workflow diagnosis and repair (Haiku)
- **`quality/`** — Ralph-style refinement loops (RefinementLoop, post-hooks, criteria, visual specs)
- **`text/proofreader.py`** — LLM-powered proofreader (Haiku)
- **`text/overlay.py`** — Pillow text overlay for images
- **`text/composition_renderer.py`** — `CompositionRenderer` for Remotion still/motion rendering
- **`media/storage.py`** — `MediaStorage`: Supabase CDN + DB tracking
- **`db/database.py`** — Async SQLite wrapper with auto-seed of `uhg` workspace
- **`db/schema.py`** — DDL and seed SQL
- **`db/repositories.py`** — CRUD repos for all entities
- **`workspace/manager.py`** — `WorkspaceManager` with multi-tenant routing
- **`workspace/brand_voice.py`** — Loads brand voice files from `data/brand_voices/`
- **`approval/workflow.py`** — Slack-based approve/edit/reject flow
- **`scheduler/scheduler.py`** — In-process async scheduler
- **`scheduler/tasks.py`** — Predefined tasks: scans, daily growth ideas, health summary, workflow healing
- **`config.py`** — Pydantic Settings (single workspace defaults, LLM, Supabase, etc.)
- **`runtime/session.py`** — `CMOSession` for CLI/Web/Slack unification
- **`core/tools.py`** — `ToolRegistry` with auto JSON Schema from type hints
- **`core/state.py`** — `AgentContext`, `AgentState` enum
- **`n8n/client.py`** — Async httpx client for n8n REST API
- **`memory/store.py`** — SQLite conversation memory for Slack persistence
- **`memory/backend.py`** — Durable workspace-scoped JSONL memory
- **`routing/router.py`** + **`routing/catalog.py`** — Lightweight Haiku router for token-optimization
- **`claude_code/runner.py`** — Claude Code CLI subprocess runner for idea→build flows

### Data

- `data/cmo_agent.db` — Phase 2 SQLite (workspaces, opportunities, drafts, sources, config, scan_log, heal_log, media_assets); auto-seeded with `uhg` on first init
- `data/slack_memory.db` — Slack conversation memory
- `data/brand_voices/` — Brand voice text files per workspace (`uhg.txt` is the default)
- `data/uhg/` — UHG workspace content directory (reference docs, investor materials, notes, research)
- `data/videos/` — Downloaded AI-generated videos
- `data/decks/` — Generated .pptx presentations
- `data/remotion/` — Remotion project scaffold (React/TS compositions)
- `data/motion_graphics/` — Rendered motion graphic MP4s
- `data/fonts/` — Bundled fonts (Inter) for Pillow text overlay
- `data/memory/` — Durable Knowledge Base JSONL per workspace
- `data/experiments/` — Experiment registry
- `data/analytics/` — Event schema definitions
- `data/editorial/` — Editorial backlog, bundles, calendar
- `data/compositions/` — Rendered composition output (PNG stills, MP4 motions)
- `.env` — Configuration (API keys, model settings, Supabase, Slack tokens)

## Code Conventions

- Python 3.9+ (`from __future__ import annotations` used throughout)
- Ruff: line-length 100, rules E/F/I/N/W/UP
- mypy: strict mode
- pytest-asyncio with `asyncio_mode = "auto"`
- Pydantic v2 for all models and settings
- structlog for logging
- All async code; DB, n8n, LLM, and session management are async
- Agents-as-tools pattern: sub-agents registered on orchestrator's ToolRegistry

## Provenance

This repository was forked from a brand-agnostic CMO Agent codebase that previously supported Saverwell (Medicare lead-gen), DSDN (Down Syndrome Diagnosis Network nonprofit), and Agent Tunnel (AI consulting). All brand-specific code paths for those projects have been removed; the multi-tenant infrastructure remains. Pre-existing files under `data/` (saverwell/, dsdn/, agent_tunnel_*) are left untouched as reference artifacts owned by the original project.
