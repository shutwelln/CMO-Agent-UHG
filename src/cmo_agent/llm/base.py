"""Abstract LLM interface and response models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """A tool call requested by the LLM."""

    id: str
    name: str
    arguments: Dict[str, Any]


class TokenUsage(BaseModel):
    """Token usage statistics."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class LLMResponse(BaseModel):
    """Response from an LLM completion."""

    content: str = ""
    tool_calls: List[ToolCall] = Field(default_factory=list)
    usage: TokenUsage = Field(default_factory=TokenUsage)
    stop_reason: Optional[str] = None


class ToolDefinition(BaseModel):
    """Definition of a tool that the LLM can call."""

    name: str
    description: str
    parameters: Dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    """A conversation message.

    Content can be:
    - A plain string (text-only messages)
    - A list of content blocks for multimodal messages (images, text, etc.)
      Each block is a dict matching Anthropic's content block format:
      {"type": "text", "text": "..."} or
      {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": "..."}}
    """

    role: str  # "user", "assistant", "tool"
    content: Any  # str or List[Dict[str, Any]] for multimodal
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None

    @property
    def text_content(self) -> str:
        """Get the text content regardless of content format."""
        if isinstance(self.content, str):
            return self.content
        if isinstance(self.content, list):
            parts = []
            for block in self.content:
                if isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block.get("text", ""))
            return "\n".join(parts)
        return str(self.content)


class BaseLLM(ABC):
    """Abstract base class for LLM providers.

    Implementations should provide async methods for:
    - complete: Generate a single completion
    - stream: Stream a completion response
    """

    @abstractmethod
    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """Generate a completion from messages.

        Args:
            messages: Conversation history
            tools: Optional list of tools the LLM can call
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Returns:
            LLMResponse with content and/or tool calls
        """
        pass

    @abstractmethod
    async def stream(
        self,
        messages: List[Message],
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> AsyncIterator[str]:
        """Stream a completion response.

        Args:
            messages: Conversation history
            max_tokens: Maximum tokens in response
            temperature: Sampling temperature

        Yields:
            Text chunks as they're generated
        """
        pass

    def _convert_tools_to_provider_format(
        self, tools: List[ToolDefinition]
    ) -> List[Dict[str, Any]]:
        """Convert tool definitions to provider-specific format.

        Override in subclasses for provider-specific formatting.
        """
        return [tool.model_dump() for tool in tools]
