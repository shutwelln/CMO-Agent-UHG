"""Unified session interface for CMO Agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

from ..agents.factory import AgentFactory
from ..agents.orchestrator import CMOOrchestratorAgent
from ..agents.registry import AgentRegistry
from ..config import get_settings
from ..core.state import AgentContext, AgentState
from ..db.database import Database
from ..n8n.client import N8NClient
from ..workspace.manager import WorkspaceManager

logger = structlog.get_logger()


@dataclass
class CMOResponse:
    """Structured response from CMO Agent."""

    text: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "final"  # "final" | "in_progress" | "error"
    trace_id: str = field(default_factory=lambda: str(uuid4()))
    actions_taken: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary."""
        return {
            "text": self.text,
            "tool_calls": self.tool_calls,
            "artifacts": self.artifacts,
            "status": self.status,
            "trace_id": self.trace_id,
            "actions_taken": self.actions_taken,
        }


class CMOSession:
    """Manages a CMO Agent conversation session.

    Provides a stable programmatic API for all interaction surfaces
    (CLI, Web UI, Slack).

    Example:
        async with CMOSession() as session:
            response = await session.ask("List my workflows")
            print(response.text)
    """

    def __init__(self, session_id: Optional[str] = None):
        """Initialize session.

        Args:
            session_id: Optional session identifier. Auto-generated if not provided.
        """
        self.session_id = session_id or str(uuid4())
        self._agent_registry: Optional[AgentRegistry] = None
        self._orchestrator: Optional[CMOOrchestratorAgent] = None
        self._context: Optional[AgentContext] = None
        self._db: Optional[Database] = None
        self._n8n: Optional[N8NClient] = None
        self._workspace_mgr: Optional[WorkspaceManager] = None
        self._initialized = False

    async def initialize(self) -> None:
        """Initialize agent system, database, and n8n connection."""
        if self._initialized:
            return

        settings = get_settings()

        # Database
        self._db = Database(db_path=settings.db_path)
        await self._db.initialize()

        # n8n client
        self._n8n = N8NClient(
            base_url=settings.n8n_base_url,
            api_key=settings.n8n_api_key,
            timeout=settings.n8n_timeout,
        )
        await self._n8n.__aenter__()

        # Build all agents
        self._agent_registry = await AgentFactory.create_all(
            settings=settings,
            db=self._db,
            n8n_client=self._n8n,
            brand_voices_dir=Path(settings.brand_voices_dir),
        )

        self._orchestrator = self._agent_registry.get("cmo_orchestrator")  # type: ignore[assignment]
        self._context = AgentContext(conversation_id=self.session_id)

        # Workspace manager for resolving workspace from user input
        self._workspace_mgr = WorkspaceManager(self._db, Path(settings.brand_voices_dir))

        self._initialized = True
        logger.info("session_initialized", session_id=self.session_id)

    async def close(self) -> None:
        """Close session and cleanup resources."""
        if self._agent_registry and self._agent_registry.media_storage:
            await self._agent_registry.media_storage.close()
        if self._n8n and self._initialized:
            await self._n8n.__aexit__(None, None, None)
        if self._db:
            await self._db.close()
        self._initialized = False
        logger.info("session_closed", session_id=self.session_id)

    async def ask(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        history: Optional[List[Dict[str, str]]] = None,
        file_blocks: Optional[List[Dict[str, Any]]] = None,
        slack_channel: Optional[str] = None,
    ) -> CMOResponse:
        """Send a message to the agent and get a structured response.

        Args:
            message: User message text
            context: Optional additional context (reserved for future use)
            history: Optional prior conversation history as list of
                     {"role": "user"|"assistant", "text": "..."} dicts.
                     Injected before processing the current message.
            file_blocks: Optional list of content blocks from processed file
                         attachments (images, extracted text, etc.). These are
                         prepended to the user message as multimodal content.
            slack_channel: Optional Slack channel ID for workspace resolution.

        Returns:
            CMOResponse with text, tool_calls, actions_taken, etc.
        """
        if not self._initialized:
            await self.initialize()

        assert self._orchestrator is not None
        assert self._context is not None
        assert self._workspace_mgr is not None

        trace_id = str(uuid4())
        logger.info("session_ask", session_id=self.session_id, trace_id=trace_id)

        try:
            # Always start with a clean context to avoid stale tool_use blocks
            self._context.clear_messages()

            # Inject prior conversation history if provided
            if history:
                history = self._truncate_history_to_budget(history)
                self._context.inject_history(history)
                logger.debug(
                    "session_history_injected",
                    session_id=self.session_id,
                    history_count=len(history),
                )

            # Resolve workspace from user message (and Slack channel if available)
            ws = await self._workspace_mgr.resolve_workspace(message, slack_channel=slack_channel)
            workspace_id = ws.id

            # Build message content — multimodal if file attachments present
            if file_blocks:
                # Build list of content blocks: file blocks first, then text
                content_blocks: List[Dict[str, Any]] = list(file_blocks)
                content_blocks.append({"type": "text", "text": message})
                agent_message: Any = content_blocks
                logger.info(
                    "session_multimodal_message",
                    session_id=self.session_id,
                    file_block_count=len(file_blocks),
                )
            else:
                agent_message = message

            # Process via the orchestrator
            result = await self._orchestrator.process_message(
                agent_message,
                context=self._context,
                workspace_id=workspace_id,
            )

            # Build human-readable actions list + extract artifacts
            actions_taken = []
            artifacts: List[Dict[str, Any]] = []
            for tc in result.tool_calls:
                action_desc = self._format_action(tc)
                if action_desc:
                    actions_taken.append(action_desc)
                # Extract structured artifacts from tool results
                tc_result = tc.get("result", {})
                if isinstance(tc_result, dict):
                    self._extract_artifacts(tc_result, artifacts)

            status = "final"
            if result.status == "error" or result.status == "max_iterations":
                status = "error"

            return CMOResponse(
                text=result.text,
                tool_calls=result.tool_calls,
                artifacts=artifacts,
                status=status,
                trace_id=trace_id,
                actions_taken=actions_taken,
            )

        except Exception as e:
            logger.error("session_ask_failed", error=str(e), trace_id=trace_id)
            return CMOResponse(
                text=f"Error processing request: {e}",
                status="error",
                trace_id=trace_id,
            )

    @staticmethod
    def _extract_artifacts(tc_result: Dict[str, Any], artifacts: List[Dict[str, Any]]) -> None:
        """Extract structured media artifacts from a tool call result."""
        # Image from visual agent
        if tc_result.get("image_url") and tc_result.get("status") == "generated":
            artifacts.append(
                {
                    "type": "image",
                    "url": tc_result["image_url"],
                    "asset_id": tc_result.get("asset_id"),
                }
            )
        # Video from video agent
        if tc_result.get("video_url") and tc_result.get("status") == "generated":
            artifacts.append(
                {
                    "type": "video",
                    "url": tc_result["video_url"],
                    "asset_id": tc_result.get("asset_id"),
                }
            )
        # Composition from composition planner + renderer
        if tc_result.get("output_path") and tc_result.get("status") == "rendered":
            asset_type = tc_result.get("asset_type", "static")
            artifacts.append(
                {
                    "type": "composition",
                    "url": tc_result.get("cdn_url") or tc_result["output_path"],
                    "asset_id": tc_result.get("asset_id"),
                    "asset_type": asset_type,
                }
            )
        # Motion graphic from motion graphics agent
        if tc_result.get("video_url") and tc_result.get("status") == "rendered":
            artifacts.append(
                {
                    "type": "motion_graphic",
                    "url": tc_result["video_url"],
                    "asset_id": tc_result.get("asset_id"),
                    "composition_id": tc_result.get("composition_id"),
                }
            )
        # Google Docs link
        if tc_result.get("google_docs_url"):
            artifacts.append(
                {
                    "type": "doc",
                    "url": tc_result["google_docs_url"],
                    "google_docs_id": tc_result.get("google_docs_id"),
                }
            )
        # Google Sheets link
        if tc_result.get("google_sheets_url"):
            artifacts.append(
                {
                    "type": "sheet",
                    "url": tc_result["google_sheets_url"],
                    "google_sheets_id": tc_result.get("google_sheets_id"),
                }
            )
        # Deck — Google Slides link or CDN URL
        if tc_result.get("google_slides_url"):
            artifacts.append(
                {
                    "type": "deck",
                    "url": tc_result["google_slides_url"],
                    "google_slides_id": tc_result.get("google_slides_id"),
                }
            )
        elif tc_result.get("cdn_url") and tc_result.get("file_path"):
            artifacts.append(
                {
                    "type": "deck",
                    "url": tc_result["cdn_url"],
                    "asset_id": tc_result.get("asset_id"),
                }
            )
        # Nested results from composite tools (e.g. generate_social_graphic)
        if isinstance(tc_result.get("image"), dict):
            CMOSession._extract_artifacts(tc_result["image"], artifacts)
        # Dig into sub-agent delegation results (orchestrator -> sub-agent)
        # When the orchestrator delegates, the result is an AgentResult dict
        # which contains its own tool_calls with nested results.
        nested_tool_calls = tc_result.get("tool_calls", [])
        if isinstance(nested_tool_calls, list):
            for nested_tc in nested_tool_calls:
                if isinstance(nested_tc, dict) and isinstance(nested_tc.get("result"), dict):
                    CMOSession._extract_artifacts(nested_tc["result"], artifacts)

    def _format_action(self, tool_call: Dict[str, Any]) -> str:
        """Format a tool call as a human-readable action description."""
        name = tool_call.get("name", "")
        args = tool_call.get("arguments", {})

        action_map = {
            "list_workflows": "Listed available n8n workflows",
            "get_workflow": f"Retrieved workflow: {args.get('workflow_id', '')}",
            "execute_workflow": f"Executed workflow: {args.get('workflow_id', '')}",
            "activate_workflow": f"Activated workflow: {args.get('workflow_id', '')}",
            "deactivate_workflow": f"Deactivated workflow: {args.get('workflow_id', '')}",
            "create_workflow": f"Created workflow: {args.get('workflow_name', '')}",
            "list_opportunities": f"Listed opportunities for {args.get('workspace_id', '')}",
            "list_drafts": f"Listed drafts for {args.get('workspace_id', '')}",
            "approve_draft": f"Approved draft: {args.get('draft_id', '')}",
            "reject_draft": f"Rejected draft: {args.get('draft_id', '')}",
            "list_workspaces": "Listed workspaces",
            "health_check": "Ran health check",
            # Sub-agent delegations
            "research_agent": f"Delegated to Research Agent: {args.get('instruction', '')[:80]}",
            "reddit_ingest_agent": f"Delegated to Reddit Agent: {args.get('instruction', '')[:80]}",
            "google_alerts_agent": f"Delegated to Google Alerts Agent: {args.get('instruction', '')[:80]}",
            "writer_agent": f"Delegated to Writer Agent: {args.get('instruction', '')[:80]}",
            "create_visual": f"Creating visual: {args.get('description', '')[:80]}",
            "video_agent": f"Delegated to Video Agent: {args.get('instruction', '')[:80]}",
            "deck_agent": f"Delegated to Deck Agent: {args.get('instruction', '')[:80]}",
            "performance_marketer_agent": f"Delegated to Performance Marketer Agent: {args.get('instruction', '')[:80]}",
            "social_media_agent": f"Delegated to Social Media Manager Agent: {args.get('instruction', '')[:80]}",
            "workflow_healer_agent": f"Delegated to Workflow Healer Agent: {args.get('instruction', '')[:80]}",
            "workflow_builder_agent": f"Delegated to Workflow Builder Agent: {args.get('instruction', '')[:80]}",
            "docs_agent": f"Delegated to Docs Agent: {args.get('instruction', '')[:80]}",
            "sheets_agent": f"Delegated to Sheets Agent: {args.get('instruction', '')[:80]}",
            "lifecycle_marketing_agent": f"Delegated to Lifecycle Marketing Agent: {args.get('instruction', '')[:80]}",
            "growth_ideas_agent": f"Delegated to Growth Ideas Agent: {args.get('instruction', '')[:80]}",
            "marketing_analytics_agent": f"Delegated to Marketing Analytics Agent: {args.get('instruction', '')[:80]}",
            "motion_graphics_agent": f"Delegated to Motion Graphics Agent: {args.get('instruction', '')[:80]}",
            "acquisition_agent": f"Delegated to Acquisition Agent: {args.get('instruction', '')[:80]}",
            "compliance_agent": f"Delegated to Compliance Agent: {args.get('instruction', '')[:80]}",
            "legal_strategy_agent": f"Delegated to Legal Strategy Agent: {args.get('instruction', '')[:80]}",
            "telesales_agent": f"Delegated to Telesales Agent: {args.get('instruction', '')[:80]}",
            "sales_ops_agent": f"Delegated to Sales Ops Agent: {args.get('instruction', '')[:80]}",
            "linkedin_partnerships_agent": f"Delegated to LinkedIn Partnerships Agent: {args.get('instruction', '')[:80]}",
            "knowledge_base_agent": f"Delegated to Knowledge Base Agent: {args.get('instruction', '')[:80]}",
            "experiment_engineer_agent": f"Delegated to Experiment Engineer Agent: {args.get('instruction', '')[:80]}",
            "editorial_agent": f"Delegated to Editorial Agent: {args.get('instruction', '')[:80]}",
            "conversion_optimization_agent": f"Delegated to Conversion Optimization Agent: {args.get('instruction', '')[:80]}",
            "gtm_agent": f"Delegated to GTM Agent: {args.get('instruction', '')[:80]}",
            "seo_aeo_agent": f"Delegated to SEO/AEO Agent: {args.get('instruction', '')[:80]}",
            "ux_ui_design_agent": f"Delegated to UX/UI Design Agent: {args.get('instruction', '')[:80]}",
            # Media library
            "list_media": f"Listed media for {args.get('workspace_id', '')}",
            "get_draft_media": f"Retrieved media for draft: {args.get('draft_id', '')}",
            # Router
            "router": f"Routed request: {args.get('action', '')}",
        }

        return action_map.get(name, f"Called tool: {name}")

    @staticmethod
    def _truncate_history_to_budget(
        history: List[Dict[str, str]],
        max_history_tokens: int = 4000,
    ) -> List[Dict[str, str]]:
        """Drop oldest messages until estimated tokens fit under budget.

        Uses chars/4 as a rough token estimate. Preserves the most recent
        messages so the LLM always has the latest conversational context.
        """
        total_chars = sum(len(m.get("text", "")) for m in history)
        approx_tokens = total_chars // 4

        if approx_tokens <= max_history_tokens:
            return history

        # Drop oldest messages first until under budget
        trimmed = list(history)
        while trimmed and (sum(len(m.get("text", "")) for m in trimmed) // 4) > max_history_tokens:
            dropped = trimmed.pop(0)
            logger.debug(
                "history_budget_drop",
                role=dropped.get("role"),
                chars=len(dropped.get("text", "")),
            )

        return trimmed

    async def health_check(self) -> Dict[str, Any]:
        """Check agent health status."""
        if not self._initialized:
            await self.initialize()
        assert self._orchestrator is not None
        # Use the orchestrator's health check tool
        return {
            "session": "healthy",
            "agents": self._agent_registry.list_agents() if self._agent_registry else [],
        }

    def clear_history(self) -> None:
        """Clear conversation history."""
        if self._context:
            self._context.clear_messages()
            logger.info("session_history_cleared", session_id=self.session_id)

    async def __aenter__(self) -> "CMOSession":
        """Async context manager entry."""
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_val: Optional[BaseException],
        exc_tb: Optional[Any],
    ) -> None:
        """Async context manager exit."""
        await self.close()
