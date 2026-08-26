# CMO Agent

AI-Powered Marketing Automation Agent with n8n workflow integration.

## Features

- **Interactive CLI Chat** - Conversational interface for marketing tasks
- **Web UI** - Browser-based chat interface
- **Slack Integration** - Bot that responds to DMs and @mentions
- **n8n Workflow Control** - List, execute, activate/deactivate workflows
- **Content Generation** - AI-powered marketing content creation

## Quick Start

### Prerequisites

- Python 3.9+
- n8n instance with API access
- Anthropic API key

### Installation

```bash
# Clone and enter directory
cd cmo-agent

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package
pip install -e .
```

### Configuration

Create a `.env` file and fill in your values (see `config.py` for all available settings):

Required settings:
- `N8N_BASE_URL` - Your n8n instance URL
- `N8N_API_KEY` - n8n API key
- `ANTHROPIC_API_KEY` - Anthropic API key

For Slack integration (optional):
- `SLACK_BOT_TOKEN` - Bot token (xoxb-...)
- `SLACK_APP_TOKEN` - App-level token (xapp-...)

## Usage

### CLI Chat

```bash
cmo chat
```

Interactive commands:
- `exit` / `quit` - End session
- `clear` - Clear conversation history
- `status` - Check agent health

### Web UI

```bash
cmo serve
```

Opens at http://127.0.0.1:8000

Options:
- `--host` / `-h` - Host to bind (default: 127.0.0.1)
- `--port` / `-p` - Port to bind (default: 8000)
- `--reload` / `-r` - Enable auto-reload for development

### Slack Bot

```bash
cmo slack
```

Requires `SLACK_BOT_TOKEN` and `SLACK_APP_TOKEN` in `.env`.

### Other Commands

```bash
cmo status      # Show system status and test connections
cmo workflows   # List n8n workflows
cmo execute ID  # Execute a workflow by ID
cmo tools       # List available agent tools
cmo version     # Show version
```

## Slack App Setup

1. **Create App**: Go to https://api.slack.com/apps and create a new app

2. **Enable Socket Mode**:
   - Settings → Socket Mode → Enable
   - Generate App-Level Token with `connections:write` scope
   - Save as `SLACK_APP_TOKEN` in `.env`

3. **Add Bot Scopes** (OAuth & Permissions → Bot Token Scopes):
   - `app_mentions:read`
   - `chat:write`
   - `im:history`
   - `im:read`

4. **Enable Events** (Event Subscriptions):
   - Enable Events
   - Subscribe to: `app_mention`, `message.im`

5. **Install to Workspace**:
   - Install App
   - Save Bot Token as `SLACK_BOT_TOKEN` in `.env`

6. **Start Bot**:
   ```bash
   cmo slack
   ```

## Project Structure

```
src/cmo_agent/
├── cli/           # CLI interface (Typer)
├── core/          # Agent orchestrator, tools, state
├── llm/           # LLM providers (Anthropic)
├── n8n/           # n8n API client
├── runtime/       # Session management (CMOSession)
├── slack/         # Slack bot (Socket Mode)
├── web/           # FastAPI web UI
└── marketing/     # Marketing domain logic
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run with auto-reload (web)
cmo serve --reload
```

## License

MIT
