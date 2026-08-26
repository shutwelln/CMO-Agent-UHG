# Getting Started with CMO Agent

CMO Agent is an AI-powered marketing automation system with 34 specialized agents. It runs on your infrastructure, uses your API keys, and keeps all data local.

## Prerequisites

- Python 3.9+
- An Anthropic API key ([get one here](https://console.anthropic.com/settings/keys))
- (Optional) Docker for containerized deployment
- (Optional) n8n for workflow automation

## Quick Start

### Option A: Local Install

```bash
# Clone the repository
git clone <your-repo-url> cmo-agent
cd cmo-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install
pip install -e .

# Run the setup wizard
cmo setup

# Start chatting
cmo chat
```

The setup wizard will walk you through:
1. Entering your Anthropic API key
2. Creating your first workspace (brand)
3. Choosing an agent profile
4. Configuring optional integrations (n8n, Slack, image generation)

### Option B: Docker

```bash
# Copy and edit the environment file
cp .env.template .env
# Edit .env with your API keys

# Start the full stack (CMO Agent + n8n)
docker compose up -d

# Access the web UI at http://localhost:8000
# Access n8n at http://localhost:5678
```

## Interaction Surfaces

CMO Agent provides three ways to interact:

| Surface | Command | Best For |
|---------|---------|----------|
| **CLI Chat** | `cmo chat` | Quick tasks, development, testing |
| **Web UI** | `cmo serve` | Browser-based access, media library |
| **Slack Bot** | `cmo slack` | Team collaboration, notifications |

## Your First Conversation

After setup, try these prompts:

```
> Write a blog post about [your topic] for [your brand]
> Create a content calendar for next week
> Draft a LinkedIn post about [your announcement]
> Build a Google Doc with a marketing brief for [your product]
> What agents are available?
```

## Agent Profiles

The setup wizard offers four profiles:

| Profile | Agents | Best For |
|---------|--------|----------|
| **full** | All 34 | Power users who want every capability |
| **marketing** | 25 | Marketing teams (no nonprofit/legal agents) |
| **content** | 14 | Content production focused |
| **minimal** | 6 | Lightweight setup, core features only |

You can change your profile later by editing `DISABLED_AGENTS` in `.env`.

## Next Steps

- [API Keys Guide](API_KEYS.md) - Configure optional integrations
- [Agent Reference](AGENT_REFERENCE.md) - Full list of all 34 agents
- [Customization Guide](CUSTOMIZATION.md) - Brand voices, custom agents, templates
