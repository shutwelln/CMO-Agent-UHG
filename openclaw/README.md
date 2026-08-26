# OpenClaw Deployment — CMO Agent

Autonomous marketing agent powered by OpenClaw, backed by CMO Agent's 42-agent intelligence stack. Runs on the existing OpenClaw + n8n infrastructure on Hostinger VPS.

## Architecture

```
Layer 1: OPENCLAW (already running on VPS)
  ├── Slack (connected, Socket Mode)
  ├── Heartbeat (HEARTBEAT.md — 30-min cycles)
  ├── Cron (cron-jobs.json — daily briefing, EOD digest)
  ├── Skills (SKILL.md + scripts/ + references/)
  └── Workspace (AGENTS.md, SOUL.md, IDENTITY.md, USER.md, TOOLS.md)
         │
         │  HTTP calls to service layer
         ▼
Layer 2: CMO SERVICE LAYER (companion Docker container)
  ├── /api/proofread           → Proofreader (Haiku LLM)
  ├── /api/brand-voice/{ws}    → BrandVoiceLoader
  ├── /api/media/upload        → MediaStorage (Supabase CDN)
  ├── /api/n8n/execute/{id}    → N8NClient
  ├── /api/n8n/workflows       → N8NClient
  ├── /api/compositions/render → CompositionRenderer (Remotion)
  └── /api/outreach/append     → OutreachDashboard (Sheets)
         │
         ▼
Layer 3: N8N (already running on VPS)
  ├── Social publishing workflows
  ├── Email/newsletter sending
  └── Credential management for all external APIs
```

## Quick Start

```bash
# 1. Deploy service layer (joins OpenClaw's Docker network)
./deploy.sh start

# 2. Test endpoints
./deploy.sh test

# 3. Install skills + workspace config into OpenClaw
./deploy.sh install-skills

# 4. Restart OpenClaw to pick up new skills
docker restart openclaw-xmzf-openclaw-1
```

## Skills

### Tier 1 — Core Marketing Engine

| Skill | What It Does |
|-------|-------------|
| `content-writer` | Blog posts, social content, newsletters with brand voice + GEO optimization |
| `social-manager` | Content calendars, platform strategy, posting schedules |
| `analytics-reporter` | Measurement frameworks, UTM governance, event taxonomies |
| `daily-briefing` | Morning briefs with 4-dimension scored growth ideas |

### Tier 2 — Differentiation

| Skill | What It Does |
|-------|-------------|
| `compliance-reviewer` | Multi-regulation content review (FINRA, TCPA, CAN-SPAM, GDPR, CCPA) |
| `lifecycle-designer` | 8-stage lifecycle flows, trigger logic, message frameworks |
| `funnel-diagnostics` | Bottleneck analysis, A/B test design, 5-weighted prioritization |
| `gtm-strategist` | 3-phase launch plans, ICP definition, unit economics |

## File Structure

```
openclaw/
├── AGENTS.md              # Agent brain — session startup, decision framework, rules
├── SOUL.md                # Personality — principles, operating style, boundaries
├── IDENTITY.md            # Name, version, author metadata
├── HEARTBEAT.md           # Autonomous heartbeat cycle config
├── USER.md                # User profile and preferences
├── TOOLS.md               # Service endpoints and local setup
├── cron-jobs.json         # Scheduled tasks (daily brief, EOD digest)
├── docker-compose.yml     # Service layer deployment (companion to OpenClaw)
├── Dockerfile.service     # FastAPI service container
├── deploy.sh              # Deployment + skill installation script
├── services/
│   ├── __init__.py
│   └── api.py             # FastAPI service layer (wraps CMO Agent modules)
└── skills/
    ├── content-writer/
    │   ├── SKILL.md
    │   ├── scripts/
    │   │   └── writer.py
    │   └── references/
    │       └── geo-framework.md
    ├── social-manager/
    │   └── SKILL.md
    ├── analytics-reporter/
    │   └── SKILL.md
    ├── daily-briefing/
    │   └── SKILL.md
    ├── compliance-reviewer/
    │   ├── SKILL.md
    │   └── references/
    │       └── regulation-matrix.md
    ├── lifecycle-designer/
    │   ├── SKILL.md
    │   └── references/
    │       └── lifecycle-stages.md
    ├── funnel-diagnostics/
    │   ├── SKILL.md
    │   └── references/
    │       └── scoring-system.md
    └── gtm-strategist/
        ├── SKILL.md
        └── references/
            └── gtm-frameworks.md
```

## Credentials

Credentials are managed through OpenClaw's native system (`openclaw.json` + container environment variables). The service layer reads from the project's `.env` file (mounted read-only). n8n manages all external API credentials (social platforms, email providers, analytics).

## Key Differences from CMO Agent

| | CMO Agent | OpenClaw Deployment |
|---|---|---|
| **Purpose** | R&D lab + dev tool | Client-facing product |
| **Interface** | CLI + Web + Slack | Slack (via OpenClaw) |
| **Complexity** | 42 agents, full Python codebase | 8 focused skills, markdown config |
| **Intelligence** | Full agent code | Extracted frameworks + scoring systems |
| **Autonomy** | On-demand | Heartbeat + cron (autonomous) |
