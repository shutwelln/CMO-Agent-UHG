# TOOLS.md - Service Endpoints & Local Setup

## Service Layer (FastAPI on same VPS)

Base URL: `http://cmo-service:8100` (Docker internal) or `http://localhost:8100` (from host)

### Available Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Service health check |
| `/api/proofread` | POST | LLM-powered proofreading (Haiku). Preserves brand terms. |
| `/api/brand-voice/{workspace_id}` | GET | Load brand voice for a workspace |
| `/api/brand-voice` | GET | List all available brand voices |
| `/api/media/upload` | POST | Upload media to Supabase CDN + DB tracking |
| `/api/n8n/execute/{workflow_id}` | POST | Trigger an n8n workflow |
| `/api/n8n/workflows` | GET | List available n8n workflows |
| `/api/compositions/render` | POST | Render Remotion compositions (PNG/MP4) |
| `/api/outreach/append` | POST | Append row to outreach Google Sheet |

### Proofread Request

```json
{
  "text": "Content to proofread",
  "preserve_terms": ["Saverwell", "Charlie"],
  "context": "Brand: saverwell, Type: blog_post"
}
```

### Brand Voice Response

```json
{
  "workspace_id": "saverwell",
  "brand_voice": "BRAND: Saverwell\n...",
  "exists": true
}
```

## n8n (Automation Engine)

- URL: `https://automation.saverwell.com`
- Manages all external API credentials (social publishing, email, analytics)
- Use n8n workflows for any action that leaves the workspace (publishing, emailing, external API calls)
- Never call external APIs directly — always through n8n

## Supabase (Media CDN)

- Media uploads go through `/api/media/upload`
- Returns CDN URL for sharing
- Tracks assets in `media_assets` table

## Google Workspace

- Service account at `data/saverwell-google-credentials.json`
- Used for Sheets (outreach dashboard) and Docs
- Outreach dashboard: 6-tab Google Sheet per workspace

## Local Resources

- Brand voice files: `data/brand_voices/{workspace_id}.txt`
- Database: `data/cmo_agent.db` (SQLite)
- Fonts: `data/fonts/` (Inter family for text overlay)
- Remotion templates: `data/remotion/src/templates/` (10 parametric templates)
