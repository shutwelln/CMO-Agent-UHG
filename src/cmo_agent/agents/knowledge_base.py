"""Knowledge Base & Memory Curator Agent — durable cross-session memory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..llm.base import BaseLLM
from ..memory.backend import MemoryBackend, MemoryItem
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()


class KnowledgeBaseAgent(BaseAgent):
    """Stores, retrieves, and manages durable workspace-scoped memory.

    Two-layer model:
    - **Conversation memory** (ephemeral): handled by existing ConversationMemory
    - **Knowledge base** (durable): this agent's JSONL store, survives across sessions
    """

    agent_id = "knowledge_base_agent"
    agent_name = "Knowledge Base & Memory Curator Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        memory_store_path: str = "./data/memory",
        max_iterations: int = 10,
    ) -> None:
        self._workspace_mgr = workspace_manager
        self._backend = MemoryBackend(base_dir=memory_store_path)
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Knowledge Base & Memory Curator Agent.

You manage durable, workspace-scoped memory that persists across conversations.
Your job is to store decisions, facts, preferences, and context so the team
never has to re-explain things.

TWO-LAYER MEMORY MODEL:
1. Conversation memory (ephemeral) — handled by the Slack bot, short-term
2. Knowledge base (durable) — YOUR domain, long-term facts and decisions

CONFIDENCE SCORING:
- 1.0: Explicit user instruction ("always use blue branding")
- 0.8: Clear decision from conversation ("we decided to target millennials")
- 0.6: Inferred from context, reasonable but not explicit
- 0.4: Speculative, needs verification

REDACTION RULES:
- API keys, tokens, passwords are auto-redacted before storage
- Email addresses and SSNs are auto-redacted
- Do NOT store raw credentials even if the user provides them

WHEN TO STORE:
- Brand decisions, style preferences, strategic directions
- Key metrics, benchmarks, targets
- Tool configurations, workflow preferences
- Important dates, deadlines, milestones
- Lessons learned, post-mortem insights

WHEN NOT TO STORE:
- Temporary task status (use editorial backlog instead)
- Raw data dumps (summarize first)
- Speculative ideas without context (use growth ideas instead)"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="memory_store",
            description="Store a memory item in the workspace knowledge base. Provide a concise summary, optional detail, tags, source_type, and confidence score.",
        )
        async def memory_store(
            workspace_id: str,
            summary: str,
            detail: str = "",
            tags: Optional[List[str]] = None,
            source_type: str = "manual",
            source_ref: str = "",
            confidence: float = 0.8,
        ) -> Dict[str, Any]:
            item = MemoryItem(
                workspace=workspace_id,
                summary=summary,
                detail=detail,
                tags=tags or [],
                source_type=source_type,
                source_ref=source_ref,
                confidence=confidence,
            )
            stored = self._backend.store(item)
            return {
                "stored": True,
                "id": stored.id,
                "summary": stored.summary,
                "confidence": stored.confidence,
            }

        @self.tool_registry.register(
            name="memory_search",
            description="Search the workspace knowledge base by keywords. Returns the most relevant memory items.",
        )
        async def memory_search(
            query: str,
            workspace_id: str = "default",
            limit: int = 5,
        ) -> Dict[str, Any]:
            results = self._backend.search(query, workspace=workspace_id, limit=limit)
            return {
                "query": query,
                "workspace": workspace_id,
                "count": len(results),
                "results": [
                    {
                        "id": r.id,
                        "summary": r.summary,
                        "tags": r.tags,
                        "confidence": r.confidence,
                        "source_type": r.source_type,
                        "created_at": r.created_at,
                    }
                    for r in results
                ],
            }

        @self.tool_registry.register(
            name="memory_get_recent",
            description="Get the most recent memory items for a workspace, optionally filtered by source_ref (e.g. conversation ID).",
        )
        async def memory_get_recent(
            workspace_id: str = "default",
            limit: int = 10,
            source_ref: Optional[str] = None,
        ) -> Dict[str, Any]:
            results = self._backend.get_recent(
                workspace=workspace_id, limit=limit, source_ref=source_ref
            )
            return {
                "workspace": workspace_id,
                "count": len(results),
                "items": [
                    {
                        "id": r.id,
                        "summary": r.summary,
                        "detail": r.detail[:200],
                        "tags": r.tags,
                        "confidence": r.confidence,
                        "created_at": r.created_at,
                    }
                    for r in results
                ],
            }

        @self.tool_registry.register(
            name="memory_get_canonical",
            description="Get high-confidence (canonical) memory items — established facts, decisions, and preferences.",
        )
        async def memory_get_canonical(
            workspace_id: str = "default",
            min_confidence: float = 0.8,
        ) -> Dict[str, Any]:
            results = self._backend.get_canonical(
                workspace=workspace_id, min_confidence=min_confidence
            )
            return {
                "workspace": workspace_id,
                "min_confidence": min_confidence,
                "count": len(results),
                "items": [
                    {
                        "id": r.id,
                        "summary": r.summary,
                        "tags": r.tags,
                        "confidence": r.confidence,
                        "created_at": r.created_at,
                    }
                    for r in results
                ],
            }

        @self.tool_registry.register(
            name="memory_status",
            description="Get memory store statistics — item counts, disk usage, per workspace or overall.",
        )
        async def memory_status(
            workspace_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            return self._backend.stats(workspace=workspace_id)

        @self.tool_registry.register(
            name="memory_expire",
            description="Expire (soft-delete) a memory item by ID. The item remains in storage but is excluded from searches.",
        )
        async def memory_expire(
            item_id: str,
            workspace_id: str = "default",
        ) -> Dict[str, Any]:
            success = self._backend.expire(item_id, workspace=workspace_id)
            return {
                "expired": success,
                "item_id": item_id,
            }
