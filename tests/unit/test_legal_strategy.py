"""Tests for the Legal Strategy Agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cmo_agent.agents.legal_strategy import LegalStrategyAgent
from cmo_agent.llm.base import LLMResponse


@pytest.fixture
def mock_db():
    """Create a mock database."""
    return MagicMock()


@pytest.fixture
def mock_workspace_mgr():
    """Create a mock workspace manager."""
    mgr = MagicMock()
    mgr.get_brand_voice = AsyncMock(return_value="Test brand voice content.")
    return mgr


@pytest.fixture
def mock_llm():
    """Create a mock LLM."""
    llm = MagicMock()
    llm.complete = AsyncMock()
    return llm


@pytest.fixture
def agent(mock_llm, mock_db, mock_workspace_mgr):
    """Create a LegalStrategyAgent with mocks."""
    with patch.object(LegalStrategyAgent, "__init_subclass__", lambda **kw: None):
        a = LegalStrategyAgent(llm=mock_llm, db=mock_db, workspace_manager=mock_workspace_mgr)
    return a


class TestLegalStrategyAgent:
    """Tests for LegalStrategyAgent tools."""

    def test_agent_id(self, agent):
        """Test agent identity."""
        assert agent.agent_id == "legal_strategy_agent"
        assert agent.agent_name == "Legal Strategy Agent"

    def test_system_prompt_contains_disclaimer(self, agent):
        """Test system prompt includes legal disclaimer guidance."""
        prompt = agent.get_system_prompt()
        assert (
            "not constitute legal advice" in prompt.lower() or "NOT a licensed attorney" in prompt
        )

    def test_tools_registered(self, agent):
        """Test all 7 tools are registered."""
        tools = agent.tool_registry.list_tools()
        expected = [
            "draft_nda",
            "draft_partnership_agreement",
            "outline_term_sheet",
            "flag_risk_areas",
            "suggest_negotiation_strategy",
            "explain_clause",
            "analyze_contract",
        ]
        for tool_name in expected:
            assert tool_name in tools, f"Tool '{tool_name}' not registered"

    @pytest.mark.asyncio
    async def test_draft_nda(self, agent, mock_llm):
        """Test draft_nda creates a draft with content_type nda_draft."""
        mock_llm.complete.return_value = LLMResponse(
            content="## 1. Draft Document\nNDA content here...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-nda-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)

        result = await agent.tool_registry.execute(
            "draft_nda",
            {
                "workspace_id": "ws1",
                "parties": "Acme Corp and Beta Inc",
                "purpose": "Marketing partnership",
            },
        )

        assert result["draft_id"] == "draft-nda-001"
        assert result["status"] == "pending"
        agent._drafts.create.assert_called_once()
        call_kwargs = agent._drafts.create.call_args
        assert call_kwargs.kwargs["content_type"] == "nda_draft"

    @pytest.mark.asyncio
    async def test_draft_partnership_agreement(self, agent, mock_llm):
        """Test draft_partnership_agreement creates a draft."""
        mock_llm.complete.return_value = LLMResponse(
            content="## 1. Draft Document\nPartnership content...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-pa-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)

        result = await agent.tool_registry.execute(
            "draft_partnership_agreement",
            {
                "workspace_id": "ws1",
                "partner_name": "Acme Corp",
                "partnership_type": "co-marketing",
                "scope": "Joint content creation",
            },
        )

        assert result["draft_id"] == "draft-pa-001"
        assert result["status"] == "pending"
        call_kwargs = agent._drafts.create.call_args
        assert call_kwargs.kwargs["content_type"] == "partnership_agreement"

    @pytest.mark.asyncio
    async def test_outline_term_sheet(self, agent, mock_llm):
        """Test outline_term_sheet creates a draft."""
        mock_llm.complete.return_value = LLMResponse(
            content="## 1. Draft Document\nTerm sheet content...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-ts-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)

        result = await agent.tool_registry.execute(
            "outline_term_sheet",
            {
                "workspace_id": "ws1",
                "deal_type": "SaaS licensing",
                "parties": "Us and Vendor Co",
                "key_terms": "12-month commitment, volume discount",
            },
        )

        assert result["draft_id"] == "draft-ts-001"
        assert result["status"] == "pending"
        call_kwargs = agent._drafts.create.call_args
        assert call_kwargs.kwargs["content_type"] == "term_sheet"

    @pytest.mark.asyncio
    async def test_flag_risk_areas_json(self, agent, mock_llm):
        """Test flag_risk_areas returns parsed JSON structure."""
        risk_json = {
            "risks": [
                {
                    "clause": "Section 5.2",
                    "severity": "High",
                    "issue": "Unlimited liability",
                    "recommendation": "Cap liability",
                }
            ],
            "overall_risk_level": "High",
            "top_priority": "Unlimited liability clause",
        }
        mock_llm.complete.return_value = LLMResponse(
            content=json.dumps(risk_json),
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )

        result = await agent.tool_registry.execute(
            "flag_risk_areas",
            {
                "workspace_id": "ws1",
                "agreement_text": "Sample agreement text with problematic clauses.",
            },
        )

        assert "risks" in result
        assert len(result["risks"]) == 1
        assert result["risks"][0]["severity"] == "High"
        assert result["overall_risk_level"] == "High"

    @pytest.mark.asyncio
    async def test_flag_risk_areas_fallback(self, agent, mock_llm):
        """Test flag_risk_areas handles non-JSON LLM response gracefully."""
        mock_llm.complete.return_value = LLMResponse(
            content="This is not valid JSON but a text analysis.",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )

        result = await agent.tool_registry.execute(
            "flag_risk_areas",
            {
                "workspace_id": "ws1",
                "agreement_text": "Some agreement text.",
            },
        )

        assert "raw_analysis" in result
        assert result["overall_risk_level"] == "Unknown"

    @pytest.mark.asyncio
    async def test_suggest_negotiation_strategy(self, agent, mock_llm):
        """Test suggest_negotiation_strategy creates a draft."""
        mock_llm.complete.return_value = LLMResponse(
            content="## 1. Draft Document\nNegotiation strategy...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-neg-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)

        result = await agent.tool_registry.execute(
            "suggest_negotiation_strategy",
            {
                "workspace_id": "ws1",
                "deal_context": "Renewing SaaS contract",
                "our_position": "Want 20% discount",
            },
        )

        assert result["draft_id"] == "draft-neg-001"
        assert result["status"] == "pending"
        call_kwargs = agent._drafts.create.call_args
        assert call_kwargs.kwargs["content_type"] == "negotiation_strategy"

    @pytest.mark.asyncio
    async def test_explain_clause_json(self, agent, mock_llm):
        """Test explain_clause returns parsed dict (no workspace_id needed)."""
        clause_json = {
            "plain_english": "This means you can't sue them.",
            "implications": "You waive your right to legal action.",
            "common_modifications": "Add carve-out for gross negligence.",
            "watch_out_for": "Overly broad waiver language.",
        }
        mock_llm.complete.return_value = LLMResponse(
            content=json.dumps(clause_json),
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )

        result = await agent.tool_registry.execute(
            "explain_clause",
            {"clause_text": "Party A hereby waives all claims..."},
        )

        assert "plain_english" in result
        assert "implications" in result
        assert "common_modifications" in result
        assert "watch_out_for" in result

    @pytest.mark.asyncio
    async def test_explain_clause_fallback(self, agent, mock_llm):
        """Test explain_clause handles non-JSON gracefully."""
        mock_llm.complete.return_value = LLMResponse(
            content="This clause means you agree to not disclose information.",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )

        result = await agent.tool_registry.execute(
            "explain_clause",
            {"clause_text": "Confidentiality clause text here."},
        )

        assert result["plain_english"] != ""
        assert result["implications"] == ""

    @pytest.mark.asyncio
    async def test_analyze_contract(self, agent, mock_llm):
        """Test analyze_contract creates a draft with content_type contract_analysis."""
        mock_llm.complete.return_value = LLMResponse(
            content="## 1. Draft Document\nContract analysis...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-ca-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)

        result = await agent.tool_registry.execute(
            "analyze_contract",
            {
                "workspace_id": "ws1",
                "contract_text": "Full contract text goes here...",
                "our_role": "service provider",
            },
        )

        assert result["draft_id"] == "draft-ca-001"
        assert result["status"] == "pending"
        call_kwargs = agent._drafts.create.call_args
        assert call_kwargs.kwargs["content_type"] == "contract_analysis"
