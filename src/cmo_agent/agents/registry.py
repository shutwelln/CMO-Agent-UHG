"""Agent registry for looking up agents by ID."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .base import BaseAgent


class AgentRegistry:
    """Registry mapping agent IDs to agent instances."""

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}
        self.media_storage: Optional[Any] = None

    def register(self, agent: BaseAgent) -> None:
        self._agents[agent.agent_id] = agent

    def get(self, agent_id: str) -> Optional[BaseAgent]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[str]:
        return list(self._agents.keys())

    def all(self) -> Dict[str, BaseAgent]:
        return dict(self._agents)
