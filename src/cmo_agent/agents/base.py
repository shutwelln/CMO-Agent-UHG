"""Base agent with ReAct loop, shared by all specialized agents."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Literal, Optional

import structlog
from pydantic import BaseModel, Field

from ..core.state import AgentContext, AgentState
from ..core.tools import ToolRegistry
from ..db.database import Database
from ..llm.base import BaseLLM

logger = structlog.get_logger()


class AgentResult(BaseModel):
    """Structured result from an agent invocation."""

    text: str = ""
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    agent_id: str = ""
    status: Literal["success", "error", "max_iterations"] = "success"
    metadata: Dict[str, Any] = Field(default_factory=dict)


class BaseAgent(ABC):
    """Abstract base agent with a ReAct-style execution loop.

    Subclasses must implement get_system_prompt() and register_tools().
    The ReAct loop (process_message) is inherited unchanged.
    """

    agent_id: str = "base"
    agent_name: str = "Base Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        max_iterations: int = 10,
    ) -> None:
        self.llm = llm
        self.db = db
        self.max_iterations = max_iterations
        self.state = AgentState.IDLE
        self.tool_registry = ToolRegistry()
        self.register_tools()

    @abstractmethod
    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        """Return the system prompt for this agent."""
        ...

    @abstractmethod
    def register_tools(self) -> None:
        """Register tools on self.tool_registry."""
        ...

    def _get_tool_definitions(self) -> Optional[list]:
        """Get tool definitions for LLM call. Subclasses can override for selective loading."""
        return self.tool_registry.get_all_definitions() or None

    async def process_message(
        self,
        message: Any,  # str or List[Dict] for multimodal content
        context: Optional[AgentContext] = None,
        workspace_id: Optional[str] = None,
    ) -> AgentResult:
        """Run the ReAct loop: think -> act -> observe -> repeat.

        Args:
            message: The instruction or user message. Can be a string for
                     text-only, or a list of content blocks for multimodal
                     messages (text + images/files).
            context: Optional existing context. A fresh one is created if None.
            workspace_id: Workspace scope for this invocation.

        Returns:
            AgentResult with text, tool calls, and metadata.
        """
        if context is None:
            from uuid import uuid4

            context = AgentContext(conversation_id=str(uuid4()))

        if workspace_id:
            context.metadata["workspace_id"] = workspace_id

        # Inject system prompt
        system_prompt = self.get_system_prompt(workspace_id)
        from ..llm.base import Message

        context.messages = [msg for msg in context.messages if msg.role != "system"]
        context.messages.insert(0, Message(role="system", content=system_prompt))

        # Add user message
        context.add_user_message(message)

        self.state = AgentState.THINKING
        iteration = 0
        all_tool_calls: List[Dict[str, Any]] = []
        metadata: Dict[str, Any] = {}

        while iteration < self.max_iterations:
            iteration += 1
            logger.info(
                "agent_iteration",
                agent=self.agent_id,
                iteration=iteration,
            )

            response = await self.llm.complete(
                messages=context.messages,
                tools=self._get_tool_definitions(),
            )

            # No tool calls means we have a final answer
            if not response.tool_calls:
                self.state = AgentState.IDLE
                context.add_assistant_message(response.content)
                return AgentResult(
                    text=response.content,
                    tool_calls=all_tool_calls,
                    agent_id=self.agent_id,
                    status="success",
                    metadata=metadata,
                )

            # Execute tool calls
            self.state = AgentState.EXECUTING
            context.add_assistant_message(
                response.content,
                [tc.model_dump() for tc in response.tool_calls],
            )

            for tool_call in response.tool_calls:
                logger.info(
                    "executing_tool",
                    agent=self.agent_id,
                    tool=tool_call.name,
                    arguments=tool_call.arguments,
                )
                tool_record: Dict[str, Any] = {
                    "name": tool_call.name,
                    "arguments": tool_call.arguments,
                }

                try:
                    result = await self.tool_registry.execute(
                        tool_name=tool_call.name,
                        arguments=tool_call.arguments,
                    )
                    result_str = str(result)
                    # Cap tool result size to avoid blowing up context window
                    if len(result_str) > 50_000:
                        logger.warning(
                            "tool_result_truncated",
                            agent=self.agent_id,
                            tool=tool_call.name,
                            original_len=len(result_str),
                        )
                        result_str = result_str[:50_000] + "\n... (truncated)"
                    # Preserve structured result for artifact extraction
                    if isinstance(result, dict):
                        tool_record["result"] = result
                except Exception as e:
                    logger.error(
                        "tool_execution_failed",
                        agent=self.agent_id,
                        tool=tool_call.name,
                        error=str(e),
                    )
                    result_str = f"Error: {e}"

                all_tool_calls.append(tool_record)
                context.add_tool_result(tool_call.id, result_str)

            self.state = AgentState.THINKING

        # Max iterations reached
        self.state = AgentState.ERROR
        return AgentResult(
            text="Max iterations reached. The task could not be completed.",
            tool_calls=all_tool_calls,
            agent_id=self.agent_id,
            status="max_iterations",
            metadata=metadata,
        )

    def list_available_tools(self) -> List[str]:
        return self.tool_registry.list_tools()
