"""CMO Agent CLI interface."""

from __future__ import annotations

import asyncio
from typing import Dict, Optional
from uuid import uuid4

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt
from rich.markdown import Markdown

from ..config import get_settings
from ..core.agent import CMOAgent
from ..core.state import AgentContext
from ..llm.anthropic import AnthropicLLM
from ..n8n.client import N8NClient
from ..runtime.session import CMOSession

app = typer.Typer(
    name="cmo",
    help="CMO Agent - AI-Powered Marketing Automation",
    no_args_is_help=True,
)
console = Console()


def get_agent() -> CMOAgent:
    """Create and return a configured CMO Agent."""
    settings = get_settings()

    llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=settings.llm_model,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )

    n8n_client = N8NClient(
        base_url=settings.n8n_base_url,
        api_key=settings.n8n_api_key,
        timeout=settings.n8n_timeout,
    )

    return CMOAgent(llm=llm, n8n_client=n8n_client)


@app.command()
def chat():
    """Start an interactive chat session with the CMO Agent."""
    console.print(
        Panel.fit(
            "[bold blue]CMO Agent Interactive Mode[/bold blue]\n"
            "Your AI-powered marketing assistant\n\n"
            "Type [green]'exit'[/green] or [green]'quit'[/green] to end the session.\n"
            "Type [green]'clear'[/green] to clear conversation history.\n"
            "Type [green]'status'[/green] to check agent health.",
            title="Welcome",
        )
    )

    asyncio.run(_chat_loop())


async def _chat_loop():
    """Run the interactive chat loop using CMOSession."""
    async with CMOSession() as session:
        while True:
            try:
                console.print()
                user_input = Prompt.ask("[bold green]You[/bold green]")

                if not user_input.strip():
                    continue

                if user_input.lower() in ("exit", "quit"):
                    console.print("[yellow]Goodbye![/yellow]")
                    break

                if user_input.lower() == "clear":
                    session.clear_history()
                    console.print("[dim]Conversation cleared.[/dim]")
                    continue

                if user_input.lower() == "status":
                    health = await session.health_check()
                    console.print(f"[dim]Status: {health}[/dim]")
                    continue

                with console.status("[bold blue]Thinking...[/bold blue]"):
                    response = await session.ask(user_input)

                console.print()
                console.print("[bold blue]CMO Agent[/bold blue]:")
                console.print(Markdown(response.text))

                # Show actions taken if any
                if response.actions_taken:
                    console.print()
                    console.print("[dim]Actions taken:[/dim]")
                    for action in response.actions_taken:
                        console.print(f"  [dim]• {action}[/dim]")

            except KeyboardInterrupt:
                console.print("\n[yellow]Session interrupted.[/yellow]")
                break
            except Exception as e:
                console.print(f"[bold red]Error:[/bold red] {e}")


@app.command()
def status():
    """Show current system status and configuration."""
    settings = get_settings()

    table = Table(title="CMO Agent Status")
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Details", style="white")

    table.add_row("Environment", "Active", settings.environment)
    table.add_row("n8n", "Configured", settings.n8n_base_url)
    table.add_row(
        "LLM Provider",
        "Ready" if settings.anthropic_api_key else "Not Configured",
        f"{settings.llm_provider}/{settings.llm_model}",
    )
    table.add_row(
        "Slack",
        "Ready" if settings.slack_bot_token and settings.slack_app_token else "Not Configured",
        "Socket Mode",
    )

    console.print(table)

    # Test connections
    console.print("\n[bold]Testing connections...[/bold]")
    asyncio.run(_test_connections())


async def _test_connections():
    """Test n8n and LLM connections."""
    settings = get_settings()

    # Test n8n
    n8n_client = N8NClient(
        base_url=settings.n8n_base_url,
        api_key=settings.n8n_api_key,
    )

    async with n8n_client:
        n8n_ok = await n8n_client.health_check()
        if n8n_ok:
            console.print("[green]✓[/green] n8n connection successful")
            # List workflows
            response = await n8n_client.list_workflows(limit=5)
            console.print(f"  Found {len(response.data)} workflows")
        else:
            console.print("[red]✗[/red] n8n connection failed")


@app.command()
def workflows():
    """List all n8n workflows."""
    asyncio.run(_list_workflows())


async def _list_workflows():
    """List workflows from n8n."""
    settings = get_settings()

    n8n_client = N8NClient(
        base_url=settings.n8n_base_url,
        api_key=settings.n8n_api_key,
    )

    async with n8n_client:
        try:
            response = await n8n_client.list_workflows()

            if not response.data:
                console.print("[yellow]No workflows found.[/yellow]")
                return

            table = Table(title="n8n Workflows")
            table.add_column("ID", style="cyan")
            table.add_column("Name", style="white")
            table.add_column("Status", style="green")

            for workflow in response.data:
                wf_status = "[green]Active[/green]" if workflow.active else "[dim]Inactive[/dim]"
                table.add_row(workflow.id or "N/A", workflow.name, wf_status)

            console.print(table)

        except Exception as e:
            console.print(f"[red]Error listing workflows:[/red] {e}")


@app.command()
def execute(
    workflow_id: str = typer.Argument(..., help="Workflow ID to execute"),
    data: Optional[str] = typer.Option(None, "--data", "-d", help="JSON data to pass to workflow"),
):
    """Execute an n8n workflow."""
    import json

    parsed_data = None
    if data:
        try:
            parsed_data = json.loads(data)
        except json.JSONDecodeError:
            console.print("[red]Invalid JSON data[/red]")
            raise typer.Exit(1)

    asyncio.run(_execute_workflow(workflow_id, parsed_data))


async def _execute_workflow(workflow_id: str, data: Optional[Dict] = None):
    """Execute a workflow."""
    settings = get_settings()

    n8n_client = N8NClient(
        base_url=settings.n8n_base_url,
        api_key=settings.n8n_api_key,
    )

    async with n8n_client:
        try:
            with console.status("[bold blue]Executing workflow...[/bold blue]"):
                execution = await n8n_client.execute_workflow(workflow_id, data)

            console.print("[green]✓[/green] Workflow executed successfully")
            console.print(f"  Execution ID: {execution.id}")
            console.print(f"  Status: {execution.status.value}")

        except Exception as e:
            console.print(f"[red]Error executing workflow:[/red] {e}")


@app.command()
def tools():
    """List available agent tools."""
    agent = get_agent()

    table = Table(title="Available Tools")
    table.add_column("Tool Name", style="cyan")
    table.add_column("Description", style="white")

    for definition in agent.tool_registry.get_all_definitions():
        table.add_row(definition.name, definition.description)

    console.print(table)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host", "-h", help="Host to bind"),
    port: int = typer.Option(8000, "--port", "-p", help="Port to bind"),
    reload: bool = typer.Option(False, "--reload", "-r", help="Enable auto-reload for development"),
):
    """Start the web UI server."""
    import uvicorn

    console.print(
        Panel.fit(
            f"[bold blue]CMO Agent Web UI[/bold blue]\n\n"
            f"Starting server at [green]http://{host}:{port}[/green]\n"
            f"Press [yellow]Ctrl+C[/yellow] to stop.",
            title="Web Server",
        )
    )

    uvicorn.run(
        "cmo_agent.web.app:app",
        host=host,
        port=port,
        reload=reload,
    )


@app.command()
def slack():
    """Start the Slack bot (Socket Mode)."""
    settings = get_settings()

    if not settings.slack_bot_token:
        console.print("[red]Error: SLACK_BOT_TOKEN is required[/red]")
        console.print("Add it to your .env file")
        raise typer.Exit(1)

    if not settings.slack_app_token:
        console.print("[red]Error: SLACK_APP_TOKEN is required[/red]")
        console.print("Add it to your .env file")
        raise typer.Exit(1)

    console.print(
        Panel.fit(
            "[bold blue]CMO Agent Slack Bot[/bold blue]\n\n"
            "Starting in Socket Mode...\n"
            "Press [yellow]Ctrl+C[/yellow] to stop.",
            title="Slack Bot",
        )
    )

    import subprocess
    import sys

    while True:
        result = subprocess.run(
            [sys.executable, "-m", "cmo_agent.slack.bot"],
        )
        if result.returncode == 42:
            console.print("[yellow]Restarting Slack bot...[/yellow]")
            continue
        if result.returncode != 0:
            raise typer.Exit(result.returncode)
        break


@app.command()
def setup():
    """Run the interactive setup wizard to configure CMO Agent."""
    from .setup import run_setup

    run_setup()


@app.command()
def version():
    """Show version information."""
    from .. import __version__

    console.print(f"CMO Agent v{__version__}")


def main():
    """CLI entry point."""
    app()


if __name__ == "__main__":
    main()
