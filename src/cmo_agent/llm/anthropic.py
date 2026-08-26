"""Anthropic Claude LLM integration."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import anthropic
import structlog
import time
from structlog.contextvars import get_contextvars

from .base import (
    BaseLLM,
    LLMResponse,
    Message,
    TokenUsage,
    ToolCall,
    ToolDefinition,
)

logger = structlog.get_logger()


class AnthropicLLM(BaseLLM):
    """Anthropic Claude LLM provider.

    Implements the BaseLLM interface for Anthropic's Claude models.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ):
        self.api_key = api_key
        self.model = model
        self.default_max_tokens = max_tokens
        self.default_temperature = temperature
        self._client: Optional[anthropic.AsyncAnthropic] = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        """Get or create the Anthropic client."""
        if self._client is None:
            self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
        return self._client

    def _convert_messages(
        self, messages: List[Message]
    ) -> Tuple[Optional[str], List[Dict[str, Any]]]:
        """Convert messages to Anthropic format.

        Merges consecutive tool_result messages into a single user message
        so the API sees all results for a multi-tool-call turn together.
        Also merges any consecutive same-role messages to satisfy the
        Anthropic alternating-roles requirement.

        After conversion, validates that every tool_use block has a matching
        tool_result block. Strips orphaned tool_use blocks to prevent
        400 errors from the Anthropic API.

        Returns:
            Tuple of (system_prompt, messages)
        """
        system_prompt: Optional[str] = None
        anthropic_messages: List[Dict[str, Any]] = []

        for msg in messages:
            if msg.role == "system":
                system_prompt = msg.content
                continue

            if msg.role == "tool":
                # Tool results become user-role messages in Anthropic format.
                # Merge with the previous message if it is also a tool_result
                # user message (happens when the LLM makes multiple tool calls
                # in a single turn).
                tool_result_block = {
                    "type": "tool_result",
                    "tool_use_id": msg.tool_call_id,
                    "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                }
                if (
                    anthropic_messages
                    and anthropic_messages[-1]["role"] == "user"
                    and isinstance(anthropic_messages[-1]["content"], list)
                    and anthropic_messages[-1]["content"]
                    and anthropic_messages[-1]["content"][0].get("type") == "tool_result"
                ):
                    # Append to existing tool_result user message
                    anthropic_messages[-1]["content"].append(tool_result_block)
                else:
                    anthropic_messages.append(
                        {
                            "role": "user",
                            "content": [tool_result_block],
                        }
                    )
            elif msg.role == "assistant" and msg.tool_calls:
                # Assistant message with tool calls
                content: List[Dict[str, Any]] = []
                if msg.content:
                    content.append({"type": "text", "text": msg.content})
                for tool_call in msg.tool_calls:
                    content.append(
                        {
                            "type": "tool_use",
                            "id": tool_call.id,
                            "name": tool_call.name,
                            "input": tool_call.arguments,
                        }
                    )
                anthropic_messages.append({"role": "assistant", "content": content})
            else:
                # Plain user or assistant message — may be str or list of content blocks.
                msg_content = msg.content

                # If content is already a list of blocks (multimodal), pass through
                if isinstance(msg_content, list):
                    # Multimodal content blocks — merge with previous same-role if possible
                    if (
                        anthropic_messages
                        and anthropic_messages[-1]["role"] == msg.role
                        and isinstance(anthropic_messages[-1]["content"], list)
                    ):
                        anthropic_messages[-1]["content"].extend(msg_content)
                    else:
                        anthropic_messages.append({"role": msg.role, "content": msg_content})
                else:
                    # String content — merge consecutive same-role messages
                    if (
                        anthropic_messages
                        and anthropic_messages[-1]["role"] == msg.role
                        and isinstance(anthropic_messages[-1]["content"], str)
                    ):
                        anthropic_messages[-1]["content"] += "\n\n" + msg_content
                    else:
                        anthropic_messages.append({"role": msg.role, "content": msg_content})

        # Validate and fix tool_use / tool_result pairing
        anthropic_messages = self._fix_orphaned_tool_use(anthropic_messages)

        return system_prompt, anthropic_messages

    @staticmethod
    def _fix_orphaned_tool_use(
        messages: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Ensure every tool_use block has a matching tool_result.

        Anthropic requires that every tool_use id has a corresponding
        tool_result in the *immediately following* user message. If any
        tool_use blocks are orphaned (missing their result in the next
        message), we strip them to prevent a 400 error. If an assistant
        message has no remaining content after stripping, it is replaced
        with a text placeholder so the conversation flow stays valid.
        """
        fixed: List[Dict[str, Any]] = []

        for i, msg in enumerate(messages):
            if msg["role"] == "assistant" and isinstance(msg.get("content"), list):
                # Collect tool_result ids from the immediately following user message
                next_result_ids: set[str] = set()
                if i + 1 < len(messages):
                    next_msg = messages[i + 1]
                    if next_msg["role"] == "user" and isinstance(next_msg.get("content"), list):
                        for block in next_msg["content"]:
                            if isinstance(block, dict) and block.get("type") == "tool_result":
                                next_result_ids.add(block.get("tool_use_id", ""))

                new_content: List[Dict[str, Any]] = []
                stripped = False
                for block in msg["content"]:
                    if isinstance(block, dict) and block.get("type") == "tool_use":
                        tool_id = block.get("id", "")
                        if tool_id not in next_result_ids:
                            # Orphaned tool_use — no matching result in next message
                            logger.warning(
                                "stripping_orphaned_tool_use",
                                tool_use_id=tool_id,
                                tool_name=block.get("name", "unknown"),
                            )
                            stripped = True
                            continue
                    new_content.append(block)

                if stripped and not new_content:
                    # All content was tool_use blocks that got stripped;
                    # replace with a text placeholder to maintain flow
                    new_content = [
                        {"type": "text", "text": "(tool calls removed — results unavailable)"}
                    ]

                fixed.append(
                    {"role": "assistant", "content": new_content if stripped else msg["content"]}
                )
            else:
                fixed.append(msg)

        return fixed

    def _convert_tools_to_provider_format(
        self, tools: List[ToolDefinition]
    ) -> List[Dict[str, Any]]:
        """Convert tool definitions to Anthropic format."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": {
                    "type": "object",
                    "properties": tool.parameters.get("properties", {}),
                    "required": tool.parameters.get("required", []),
                },
            }
            for tool in tools
        ]

    async def complete(
        self,
        messages: List[Message],
        tools: Optional[List[ToolDefinition]] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> LLMResponse:
        """Generate a completion using Claude."""
        client = self._get_client()
        system_prompt, anthropic_messages = self._convert_messages(messages)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "temperature": temperature or self.default_temperature,
        }

        if system_prompt:
            kwargs["system"] = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]

        if tools:
            provider_tools = self._convert_tools_to_provider_format(tools)
            if provider_tools:
                provider_tools[-1]["cache_control"] = {"type": "ephemeral"}
            kwargs["tools"] = provider_tools

        try:
            # Per-component payload breakdown (behind feature flag)
            from ..routing.instrumentation import (
                compute_payload_breakdown,
                estimate_user_message_chars,
            )
            from ..config import get_settings

            _settings = get_settings()
            if _settings.token_instrumentation:
                breakdown = compute_payload_breakdown(
                    system_prompt=kwargs.get("system"),
                    messages=kwargs.get("messages", []),
                    tools=kwargs.get("tools"),
                )
                logger.info("anthropic_payload_breakdown", **breakdown)
                # Token budget guardrail
                if breakdown["total_tokens_approx"] > _settings.token_budget_warn:
                    user_chars = estimate_user_message_chars(kwargs.get("messages", []))
                    if user_chars < 200:
                        logger.warning(
                            "token_budget_exceeded",
                            total_approx=breakdown["total_tokens_approx"],
                            budget=_settings.token_budget_warn,
                            user_msg_chars=user_chars,
                        )

            ctx = get_contextvars()
            t0 = time.time()

            logger.info(
                "anthropic_call_start",
                request_id=ctx.get("request_id"),
                conversation_id=ctx.get("conversation_id"),
                model=kwargs.get("model"),
                payload_chars=len(str(kwargs)),
            )

            response = await client.messages.create(**kwargs)

            usage = getattr(response, "usage", None)
            input_tokens = getattr(usage, "input_tokens", None) if usage else None
            output_tokens = getattr(usage, "output_tokens", None) if usage else None
            cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0

            logger.info(
                "anthropic_call_end",
                request_id=ctx.get("request_id"),
                conversation_id=ctx.get("conversation_id"),
                model=kwargs.get("model"),
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=(input_tokens or 0) + (output_tokens or 0),
                cache_creation_input_tokens=cache_creation,
                cache_read_input_tokens=cache_read,
                duration_ms=int((time.time() - t0) * 1000),
            )

            # Extract content and tool calls
            content = ""
            tool_calls: List[ToolCall] = []

            for block in response.content:
                if block.type == "text":
                    content += block.text
                elif block.type == "tool_use":
                    tool_calls.append(
                        ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input,
                        )
                    )

            return LLMResponse(
                content=content,
                tool_calls=tool_calls,
                usage=TokenUsage(
                    input_tokens=response.usage.input_tokens,
                    output_tokens=response.usage.output_tokens,
                    cache_creation_input_tokens=cache_creation,
                    cache_read_input_tokens=cache_read,
                ),
                stop_reason=response.stop_reason,
            )

        except anthropic.APIError as e:
            logger.error("anthropic_api_error", error=str(e))
            raise

    async def stream(
        self,
        messages: List[Message],
        max_tokens: Optional[int] = None,
        temperature: Optional[int] = None,
    ) -> AsyncIterator[str]:
        """Stream a completion response from Claude."""
        client = self._get_client()
        system_prompt, anthropic_messages = self._convert_messages(messages)

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": anthropic_messages,
            "max_tokens": max_tokens or self.default_max_tokens,
            "temperature": temperature or self.default_temperature,
        }

        if system_prompt:
            kwargs["system"] = system_prompt

        try:
            async with client.messages.stream(**kwargs) as stream:
                async for text in stream.text_stream:
                    yield text

        except anthropic.APIError as e:
            logger.error("anthropic_stream_error", error=str(e))
            raise
