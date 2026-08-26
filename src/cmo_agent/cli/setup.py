"""Interactive setup wizard for CMO Agent."""

from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

console = Console()

# Default agent profiles that pre-select disabled agents
AGENT_PROFILES = {
    "full": {
        "description": "All agents enabled (content, strategy, ops, compliance, workflows)",
        "disabled": [],
    },
    "marketing": {
        "description": "Content + strategy agents (no legal/compliance)",
        "disabled": [
            "compliance_agent",
            "legal_strategy_agent",
        ],
    },
    "content": {
        "description": "Content production only (writer, visual, video, docs, sheets, deck)",
        "disabled": [
            "compliance_agent",
            "legal_strategy_agent",
            "telesales_agent",
            "sales_ops_agent",
            "linkedin_partnerships_agent",
            "performance_marketer_agent",
            "marketing_analytics_agent",
            "acquisition_agent",
            "conversion_optimization_agent",
            "gtm_agent",
            "seo_aeo_agent",
            "workflow_builder_agent",
            "workflow_healer_agent",
        ],
    },
    "minimal": {
        "description": "Core only (writer, research, docs, sheets)",
        "disabled": [
            "compliance_agent",
            "legal_strategy_agent",
            "telesales_agent",
            "sales_ops_agent",
            "linkedin_partnerships_agent",
            "performance_marketer_agent",
            "marketing_analytics_agent",
            "acquisition_agent",
            "conversion_optimization_agent",
            "gtm_agent",
            "seo_aeo_agent",
            "workflow_builder_agent",
            "workflow_healer_agent",
            "create_visual",
            "video_agent",
            "deck_agent",
            "motion_graphics_agent",
            "social_media_agent",
            "lifecycle_marketing_agent",
            "growth_ideas_agent",
            "knowledge_base_agent",
            "experiment_engineer_agent",
            "editorial_agent",
            "composition_planner_agent",
        ],
    },
}


def _slugify(name: str) -> str:
    """Convert a brand name to a workspace slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "_", slug)
    slug = slug.strip("_")
    return slug


def run_setup() -> None:
    """Run the interactive setup wizard."""
    console.print(
        Panel.fit(
            "[bold blue]CMO Agent Setup Wizard[/bold blue]\n\n"
            "This wizard will configure your CMO Agent installation.\n"
            "It creates a .env file, initializes the database, and\n"
            "sets up your first workspace.",
            title="Welcome",
        )
    )
    console.print()

    project_root = Path(__file__).resolve().parents[3]
    env_path = project_root / ".env"
    template_path = project_root / ".env.template"

    # Check for existing .env
    if env_path.exists():
        overwrite = Confirm.ask(
            "[yellow]An .env file already exists. Overwrite it?[/yellow]",
            default=False,
        )
        if not overwrite:
            console.print("[dim]Setup cancelled. Your existing .env is unchanged.[/dim]")
            return

    # Start from template
    if template_path.exists():
        env_content = template_path.read_text()
    else:
        env_content = ""

    env_vars: dict[str, str] = {}

    # ── Step 1: API Key ──────────────────────────────────────
    console.print("\n[bold]Step 1: LLM API Key[/bold]")
    console.print("CMO Agent requires an Anthropic API key to function.")
    console.print("Get one at: https://console.anthropic.com/settings/keys\n")

    api_key = Prompt.ask("Anthropic API key", password=True)
    env_vars["ANTHROPIC_API_KEY"] = api_key

    # ── Step 2: First Workspace ──────────────────────────────
    console.print("\n[bold]Step 2: Your First Workspace[/bold]")
    console.print("A workspace represents a brand or project.\n")

    brand_name = Prompt.ask("Brand/project name", default="My Brand")
    workspace_id = _slugify(brand_name)
    console.print(f"  Workspace ID: [cyan]{workspace_id}[/cyan]")

    env_vars["DEFAULT_WORKSPACE"] = workspace_id

    # ── Step 3: Agent Profile ────────────────────────────────
    console.print("\n[bold]Step 3: Agent Profile[/bold]")
    console.print("Choose which agents to enable:\n")
    for key, profile in AGENT_PROFILES.items():
        marker = " (recommended)" if key == "full" else ""
        console.print(f"  [cyan]{key}[/cyan]{marker}: {profile['description']}")

    profile_choice = Prompt.ask(
        "\nProfile",
        choices=list(AGENT_PROFILES.keys()),
        default="full",
    )
    disabled = AGENT_PROFILES[profile_choice]["disabled"]
    if disabled:
        env_vars["DISABLED_AGENTS"] = ",".join(disabled)
    else:
        env_vars["DISABLED_AGENTS"] = ""

    # ── Step 4: Optional Integrations ────────────────────────
    console.print("\n[bold]Step 4: Optional Integrations[/bold]")

    # n8n
    if Confirm.ask("Connect to an n8n instance?", default=False):
        n8n_url = Prompt.ask("n8n URL", default="http://localhost:5678")
        n8n_key = Prompt.ask("n8n API key", password=True, default="")
        env_vars["N8N_BASE_URL"] = n8n_url
        if n8n_key:
            env_vars["N8N_API_KEY"] = n8n_key

    # Image generation
    if Confirm.ask("Enable image generation? (requires Gemini or OpenAI key)", default=False):
        gemini_key = Prompt.ask("Gemini API key (recommended)", password=True, default="")
        if gemini_key:
            env_vars["GEMINI_API_KEY"] = gemini_key

    # Slack
    if Confirm.ask("Enable Slack bot?", default=False):
        env_vars["SLACK_BOT_TOKEN"] = Prompt.ask("Slack Bot Token", password=True)
        env_vars["SLACK_APP_TOKEN"] = Prompt.ask("Slack App Token", password=True)

    # ── Write .env ───────────────────────────────────────────
    console.print("\n[bold]Writing configuration...[/bold]")

    # Update template content with provided values
    for key, value in env_vars.items():
        # Try to replace existing line in template
        pattern = rf"^{re.escape(key)}=.*$"
        replacement = f"{key}={value}"
        new_content, count = re.subn(pattern, replacement, env_content, flags=re.MULTILINE)
        if count > 0:
            env_content = new_content
        else:
            env_content += f"\n{key}={value}"

    env_path.write_text(env_content)
    console.print(f"  [green]OK[/green] .env written to {env_path}")

    # ── Create brand voice file ──────────────────────────────
    voices_dir = project_root / "data" / "brand_voices"
    voices_dir.mkdir(parents=True, exist_ok=True)
    voice_file = voices_dir / f"{workspace_id}.txt"
    example_file = voices_dir / "_example.txt"

    if not voice_file.exists():
        if example_file.exists():
            shutil.copy(example_file, voice_file)
            console.print(f"  [green]OK[/green] Brand voice template created at {voice_file}")
            console.print("       Edit this file to define your brand's tone and style.")
        else:
            voice_file.write_text(f"# Brand voice for {brand_name}\n")
            console.print(f"  [green]OK[/green] Brand voice file created at {voice_file}")

    # ── Initialize database ──────────────────────────────────
    console.print("\n[bold]Initializing database...[/bold]")
    asyncio.run(_init_db(project_root, workspace_id, brand_name))

    # ── Done ─────────────────────────────────────────────────
    console.print(
        Panel.fit(
            f"[bold green]Setup complete![/bold green]\n\n"
            f"Workspace: [cyan]{workspace_id}[/cyan] ({brand_name})\n"
            f"Profile: [cyan]{profile_choice}[/cyan]\n\n"
            f"Next steps:\n"
            f"  1. Edit your brand voice: [dim]{voice_file}[/dim]\n"
            f"  2. Start chatting: [green]cmo chat[/green]\n"
            f"  3. Start web UI: [green]cmo serve[/green]\n"
            f"  4. View status: [green]cmo status[/green]",
            title="Ready",
        )
    )


async def _init_db(project_root: Path, workspace_id: str, brand_name: str) -> None:
    """Initialize the database and create the first workspace."""
    from ..db.database import Database

    db_path = project_root / "data" / "cmo_agent.db"
    db = Database(db_path=str(db_path))
    try:
        await db.initialize()
        await db.seed_workspace(
            workspace_id=workspace_id,
            name=brand_name,
            brand_voice_path=f"{workspace_id}.txt",
        )
        console.print(f"  [green]OK[/green] Database initialized at {db_path}")
        console.print(f"  [green]OK[/green] Workspace '{workspace_id}' created")
    finally:
        await db.close()
