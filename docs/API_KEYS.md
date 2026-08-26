# API Keys Guide

CMO Agent integrates with several external services. Only the Anthropic API key is required; everything else is optional.

## Required

### Anthropic API Key
- **Variable:** `ANTHROPIC_API_KEY`
- **Get it:** [console.anthropic.com/settings/keys](https://console.anthropic.com/settings/keys)
- **Used by:** All agents (LLM backbone)
- **Typical cost:** $50-200/mo depending on usage (Haiku for scanning, Sonnet for writing)

## Optional Integrations

### n8n (Workflow Automation)
- **Variables:** `N8N_BASE_URL`, `N8N_API_KEY`
- **Get it:** Self-host n8n or use [n8n.io cloud](https://n8n.io)
- **Used by:** Workflow Builder Agent, Workflow Healer Agent
- **Enables:** Building, deploying, and auto-healing n8n workflows from chat

### Google Workspace
- **Variables:** `GOOGLE_CREDENTIALS_PATH`, `GOOGLE_OAUTH_TOKEN_PATH`
- **Setup:** Create a Google Cloud service account or OAuth2 credentials
- **Used by:** Docs Agent, Sheets Agent, Deck Agent
- **Enables:** Creating Google Docs, Sheets, and Slides directly from chat

### Image Generation
Choose one or more providers:

| Provider | Variable | Quality | Cost |
|----------|----------|---------|------|
| **Gemini** (recommended) | `GEMINI_API_KEY` | Best | ~$0.04/image |
| **OpenAI DALL-E** | `OPENAI_API_KEY` | Good | ~$0.04/image |
| **SDXL (via fal.ai)** | `FAL_API_KEY` | Good | ~$0.01/image |

### Video Generation
- **Variable:** `FAL_API_KEY`
- **Used by:** Video Agent
- **Enables:** AI video generation via fal.ai (Kling, Runway)

### Supabase (Media Storage)
- **Variables:** `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_BUCKET`
- **Used by:** All visual/media agents
- **Enables:** CDN-hosted media with database tracking
- **Without it:** Media is stored locally in `data/` directories

### Slack Bot
- **Variables:** `SLACK_BOT_TOKEN`, `SLACK_APP_TOKEN`, `SLACK_SIGNING_SECRET`
- **Setup:** Create a Slack app with Socket Mode enabled
- **Used by:** Slack interaction surface, notifications, approval workflows

### Customer.io
- **Variable:** `CUSTOMERIO_APP_API_KEY`
- **Used by:** Lifecycle Marketing Agent
- **Enables:** Email/SMS/push campaign design with Customer.io integration

### GA4 Analytics
- **Variables:** `GA4_PROPERTY_ID`, `GA4_MEASUREMENT_ID`, `GA4_API_SECRET`, `GTM_CONTAINER_ID`
- **Used by:** Marketing Analytics Agent
- **Enables:** Measurement frameworks, tracking specifications, UTM governance

## Cost Estimation

Typical monthly costs by usage level:

| Usage Level | LLM Costs | Image Gen | Total |
|-------------|-----------|-----------|-------|
| Light (10-20 tasks/day) | $30-60 | $5-10 | $35-70 |
| Moderate (30-50 tasks/day) | $80-150 | $15-30 | $95-180 |
| Heavy (100+ tasks/day) | $200-400 | $30-60 | $230-460 |

LLM costs are dominated by Sonnet (writing) tasks. Scanning tasks use Haiku, which is ~20x cheaper per token.
