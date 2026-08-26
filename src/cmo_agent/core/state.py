"""Agent state management."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..llm.base import Message


class AgentState(str, Enum):
    """Current state of the agent."""

    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING_FOR_USER = "waiting_for_user"
    ERROR = "error"


class ConversationTurn(BaseModel):
    """A single turn in the conversation."""

    user_message: str
    assistant_message: str
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AgentContext(BaseModel):
    """Context for agent operations.

    Maintains conversation history, active state, and metadata
    for the current agent session.
    """

    # Session identification
    conversation_id: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Conversation state
    messages: List[Message] = Field(default_factory=list)
    turns: List[ConversationTurn] = Field(default_factory=list)

    # Active context
    current_campaign_id: Optional[str] = None
    active_workflows: List[str] = Field(default_factory=list)

    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def add_user_message(self, content: Any) -> None:
        """Add a user message to the conversation.

        Content can be a string (text-only) or a list of content blocks
        for multimodal messages (text + images/files).
        """
        self.messages.append(Message(role="user", content=content))

    def add_assistant_message(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Add an assistant message to the conversation."""
        from ..llm.base import ToolCall

        parsed_tool_calls = None
        if tool_calls:
            parsed_tool_calls = [ToolCall(**tc) for tc in tool_calls]

        self.messages.append(
            Message(role="assistant", content=content, tool_calls=parsed_tool_calls)
        )

    def add_tool_result(self, tool_call_id: str, result: str) -> None:
        """Add a tool result to the conversation."""
        self.messages.append(Message(role="tool", content=result, tool_call_id=tool_call_id))

    def record_turn(
        self,
        user_message: str,
        assistant_message: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Record a complete conversation turn."""
        self.turns.append(
            ConversationTurn(
                user_message=user_message,
                assistant_message=assistant_message,
                tool_calls=tool_calls or [],
            )
        )

    def get_system_prompt(self) -> str:
        """Get the system prompt for the agent."""
        return """You are a CMO (Chief Marketing Officer) Agent with expertise in:
- Marketing campaign planning and execution
- Content creation and optimization
- Multi-channel marketing orchestration (email, social media, ads)
- Marketing analytics and performance reporting

You have access to tools that allow you to:
- Create and manage marketing campaigns
- Generate marketing content using AI
- Execute n8n workflows for automation
- Retrieve and analyze marketing metrics

When users ask for marketing help, analyze their needs and use the appropriate tools
to accomplish their goals. Always explain your reasoning and provide actionable insights.

Be proactive in suggesting improvements and optimizations based on best practices."""

    def to_messages_for_llm(self) -> List[Message]:
        """Convert context to messages for LLM completion."""
        system_message = Message(role="system", content=self.get_system_prompt())
        return [system_message] + self.messages

    def clear_messages(self) -> None:
        """Clear conversation messages while preserving other state."""
        self.messages.clear()

    def inject_history(self, history: List[Dict[str, str]]) -> None:
        """Inject prior conversation history.

        Args:
            history: List of dicts with 'role' and 'text' keys.
                     Role should be 'user' or 'assistant'.
        """
        for msg in history:
            role = msg.get("role", "user")
            text = msg.get("text", "")
            if role == "user":
                self.messages.append(Message(role="user", content=text))
            elif role == "assistant":
                self.messages.append(Message(role="assistant", content=text))

    def summary(self) -> Dict[str, Any]:
        """Get a summary of the current context."""
        return {
            "conversation_id": self.conversation_id,
            "message_count": len(self.messages),
            "turn_count": len(self.turns),
            "current_campaign_id": self.current_campaign_id,
            "active_workflows": self.active_workflows,
        }
