"""Per-component payload breakdown logging for LLM calls."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


def compute_payload_breakdown(
    system_prompt: Optional[str],
    messages: Optional[List[Dict[str, Any]]],
    tools: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """Compute a per-component breakdown of an LLM request payload.

    Returns approximate token counts (chars // 4) for each component
    so we can identify where the overhead lives.
    """
    system_chars = len(system_prompt) if system_prompt else 0
    messages_chars = len(json.dumps(messages, default=str)) if messages else 0
    tools_json = json.dumps(tools, default=str) if tools else ""
    tools_chars = len(tools_json)
    tool_count = len(tools) if tools else 0

    # Count how many tools are agent delegations (name ends with _agent)
    agent_tools_count = 0
    if tools:
        agent_tools_count = sum(
            1 for t in tools if isinstance(t, dict) and t.get("name", "").endswith("_agent")
        )

    total_chars = system_chars + messages_chars + tools_chars

    return {
        "system_prompt_chars": system_chars,
        "system_prompt_tokens_approx": system_chars // 4,
        "messages_chars": messages_chars,
        "messages_tokens_approx": messages_chars // 4,
        "tools_json_chars": tools_chars,
        "tools_json_tokens_approx": tools_chars // 4,
        "tool_count": tool_count,
        "agent_tools_count": agent_tools_count,
        "total_chars": total_chars,
        "total_tokens_approx": total_chars // 4,
    }


def estimate_user_message_chars(messages: Optional[List[Dict[str, Any]]]) -> int:
    """Estimate the character count of just the latest user message.

    Useful as a guardrail: if the user message is tiny but total payload
    is huge, we know the overhead is all fixed cost.
    """
    if not messages:
        return 0

    # Walk backwards to find the last user message
    for msg in reversed(messages):
        if msg.get("role") != "user":
            continue
        content = msg.get("content", "")
        if isinstance(content, str):
            return len(content)
        if isinstance(content, list):
            # Sum text blocks in multimodal content
            total = 0
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        total += len(block.get("text", ""))
                    elif block.get("type") == "tool_result":
                        total += len(str(block.get("content", "")))
            return total
    return 0
