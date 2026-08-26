"""Lightweight Haiku router for token-efficient request classification."""

from __future__ import annotations

import json
from typing import List, Optional

import structlog
from pydantic import BaseModel, Field

from ..llm.base import BaseLLM, Message

logger = structlog.get_logger()


class RoutingDecision(BaseModel):
    """Result of the router's classification."""

    action: str  # "respond_directly" | "delegate_to_agent" | "use_management_tool"
    agent_id: Optional[str] = None
    tool_ids: List[str] = Field(default_factory=list)
    direct_response: Optional[str] = None
    reasoning: str = ""


class AgentRouter:
    """Lightweight router that classifies requests before the full orchestrator.

    Uses a compact system prompt (~450 tokens) sent to Haiku to decide whether
    to respond directly, delegate to a specific agent, or use a management tool.
    This avoids sending the full orchestrator prompt (~4,200 tokens) + all 45 tool
    schemas (~3,300 tokens) for simple requests.
    """

    def __init__(self, llm: BaseLLM, router_prompt: str) -> None:
        self._llm = llm
        self._router_prompt = router_prompt

    async def route(self, user_message: str, workspace_id: str) -> RoutingDecision:
        """Classify a user message into a routing decision.

        Args:
            user_message: The raw user message text.
            workspace_id: Current workspace scope.

        Returns:
            RoutingDecision indicating how to handle the request.
            On any error, returns a fallback that triggers the full orchestrator.
        """
        messages = [
            Message(role="system", content=self._router_prompt),
            Message(role="user", content=user_message),
        ]

        try:
            response = await self._llm.complete(
                messages=messages,
                tools=None,
                max_tokens=300,
                temperature=0.2,
            )

            raw = response.content.strip()
            # Strip markdown fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1]
                if raw.endswith("```"):
                    raw = raw[:-3]
                raw = raw.strip()

            decision = RoutingDecision(**json.loads(raw))

            logger.info(
                "router_decision",
                action=decision.action,
                agent_id=decision.agent_id,
                tool_ids=decision.tool_ids,
                reasoning=decision.reasoning,
                input_tokens=response.usage.input_tokens,
                output_tokens=response.usage.output_tokens,
            )

            return decision

        except (json.JSONDecodeError, TypeError, KeyError) as e:
            logger.warning(
                "router_parse_error",
                error=str(e),
                raw_response=response.content[:200] if response else "",
            )
            return self._fallback_decision("parse error")
        except Exception as e:
            logger.warning("router_error", error=str(e))
            return self._fallback_decision(str(e))

    @staticmethod
    def _fallback_decision(reason: str) -> RoutingDecision:
        """Return a fallback decision that triggers the full orchestrator."""
        return RoutingDecision(
            action="fallback",
            reasoning=f"Router fallback: {reason}",
        )
