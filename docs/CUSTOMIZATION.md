# Customization Guide

CMO Agent is designed to be customized for your specific brand, industry, and workflows.

## Brand Voice Files

Each workspace uses a brand voice file that tells the Writer Agent (and other content-producing agents) how to write for your brand.

### Creating a Brand Voice

1. Copy the example template:
   ```bash
   cp data/brand_voices/_example.txt data/brand_voices/your_workspace.txt
   ```

2. Edit the file to define your brand's:
   - Tone and personality
   - Target audience
   - Preferred vocabulary
   - Formatting rules
   - Content guardrails

3. The filename must match your workspace ID (e.g., workspace `acme` uses `acme.txt`).

### Tips for Effective Brand Voices

- Be specific: "warm and conversational" is better than "friendly"
- Include examples of words to use and avoid
- Define formatting preferences (bullet styles, heading conventions)
- Set content guardrails (disclaimers, fact-checking rules)
- Update the file as your brand evolves

## Multiple Workspaces

CMO Agent supports multiple brands/projects simultaneously. Each workspace has its own:
- Brand voice file
- Monitoring sources (RSS feeds, subreddits)
- Configuration (keywords, score thresholds)
- Content drafts and opportunities

### Adding a Workspace

Ask the agent directly:
```
> Create a new workspace called "Acme Corp" with the ID "acme"
```

Or use the database directly:
```sql
INSERT INTO workspaces (id, name, type, brand_voice_path, is_default)
VALUES ('acme', 'Acme Corp', 'owned_brand', 'acme.txt', 0);
```

### Adding Monitoring Sources

Ask the agent to add sources:
```
> Add r/startups as a monitoring source for the acme workspace with keywords: SaaS, startup, growth
> Add the TechCrunch RSS feed for the acme workspace
```

## Custom Agents

You can create custom agents that extend CMO Agent's capabilities.

### Agent Architecture

Every agent inherits from `BaseAgent` which provides:
- A ReAct-style execution loop (think, act, observe, repeat)
- A `ToolRegistry` for registering callable tools
- Abstract methods: `get_system_prompt()` and `register_tools()`

### Creating a Custom Agent

1. Create `src/cmo_agent/agents/your_agent.py`:

```python
from __future__ import annotations
from typing import Any, Dict, Optional
from ..db.database import Database
from ..llm.base import BaseLLM
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

class YourAgent(BaseAgent):
    agent_id = "your_agent"
    agent_name = "Your Custom Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
    ) -> None:
        self._workspace_mgr = workspace_manager
        super().__init__(llm=llm, db=db)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return "You are a specialized agent that..."

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="your_tool",
            description="Does something useful.",
        )
        async def your_tool(input: str) -> Dict[str, Any]:
            # Your tool logic here
            return {"result": "success"}
```

2. Wire it into `factory.py` (import, instantiate, pass to orchestrator)
3. Add it to the orchestrator's constructor and tool registration
4. Add action formatting in `runtime/session.py`

## Configuration Reference

All settings are defined in `src/cmo_agent/config.py` and can be set via environment variables or `.env`:

| Category | Key Variables |
|----------|-------------|
| **LLM Models** | `LLM_MODEL`, `LLM_MODEL_SCANNING`, `LLM_MODEL_WRITING`, `LLM_MODEL_PREMIUM` |
| **Agent Toggling** | `DISABLED_AGENTS` (comma-separated agent IDs) |
| **Quality** | `REFINEMENT_ENABLED` (true/false), controls quality refinement loops |
| **Router** | `ROUTER_ENABLED` (true/false), `ROUTER_MODEL` |
| **Scheduler** | `SCHEDULER_ENABLED`, schedule hours/minutes/timezone for each scheduled task |
| **Paths** | `DB_PATH`, `BRAND_VOICES_DIR`, `VIDEO_OUTPUT_DIR`, `MOTION_OUTPUT_DIR` |
