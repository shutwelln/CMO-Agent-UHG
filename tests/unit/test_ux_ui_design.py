"""Tests for the UX/UI Design Agent."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cmo_agent.agents.ux_ui_design import UxUiDesignAgent
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
    """Create a UxUiDesignAgent with mocks."""
    with patch.object(UxUiDesignAgent, "__init_subclass__", lambda **kw: None):
        a = UxUiDesignAgent(llm=mock_llm, db=mock_db, workspace_manager=mock_workspace_mgr)
    return a


class TestUxUiDesignAgent:
    """Tests for UxUiDesignAgent."""

    def test_agent_id(self, agent):
        """Test agent identity."""
        assert agent.agent_id == "ux_ui_design_agent"
        assert agent.agent_name == "UX/UI Design Agent"

    def test_system_prompt_contains_wcag(self, agent):
        """Test system prompt includes accessibility standards."""
        prompt = agent.get_system_prompt()
        assert "WCAG 2.1 AA" in prompt
        assert "4.5:1" in prompt
        assert "44px" in prompt
        assert "ARIA" in prompt

    def test_tools_registered(self, agent):
        """Test all 5 tools are registered."""
        tools = agent.tool_registry.list_tools()
        expected = [
            "run_ux_audit",
            "design_spec",
            "navigation_design",
            "interaction_design",
            "screenshot_ux_audit",
        ]
        for tool_name in expected:
            assert tool_name in tools, f"Tool '{tool_name}' not registered"

    def test_system_prompt_anti_ai_writing(self, agent):
        """Test system prompt includes anti-AI writing rules."""
        prompt = agent.get_system_prompt()
        assert "em dash" in prompt.lower() or "NEVER use em dashes" in prompt

    def test_system_prompt_scope_boundaries(self, agent):
        """Test system prompt defines scope boundaries."""
        prompt = agent.get_system_prompt()
        assert "Acquisition Agent" in prompt
        assert "CRO Agent" in prompt
        assert "SEO/AEO Agent" in prompt

    @pytest.mark.asyncio
    async def test_run_ux_audit(self, agent, mock_llm):
        """Test run_ux_audit creates a draft."""
        mock_llm.complete.return_value = LLMResponse(
            content="## 1. Heuristic Evaluation\nFindings here...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-ux-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)
        agent._config.get = AsyncMock(return_value="")

        result = await agent.tool_registry.execute(
            "run_ux_audit",
            {
                "workspace_id": "uhg",
                "page_description": "Homepage with hero, discount map, and guides section",
                "page_type": "homepage",
            },
        )

        assert result["draft_id"] == "draft-ux-001"
        assert result["status"] == "pending"
        agent._drafts.create.assert_called_once()
        call_kwargs = agent._drafts.create.call_args
        assert call_kwargs.kwargs["content_type"] == "ux_audit"

    @pytest.mark.asyncio
    async def test_design_spec(self, agent, mock_llm):
        """Test design_spec creates a draft and persists context for design_system type."""
        mock_llm.complete.return_value = LLMResponse(
            content="## Typography Scale\nManrope, weights 300-700...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-ds-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)
        agent._config.get = AsyncMock(return_value="")
        agent._config.set = AsyncMock()

        result = await agent.tool_registry.execute(
            "design_spec",
            {
                "workspace_id": "uhg",
                "spec_type": "design_system",
                "subject": "UHG consumer site design system",
            },
        )

        assert result["draft_id"] == "draft-ds-001"
        assert result["status"] == "pending"
        # design_system spec should persist context
        agent._config.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_design_spec_component(self, agent, mock_llm):
        """Test design_spec component type does not persist context."""
        mock_llm.complete.return_value = LLMResponse(
            content="## Component Overview\nButton component...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-comp-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)
        agent._config.get = AsyncMock(return_value="")
        agent._config.set = AsyncMock()

        result = await agent.tool_registry.execute(
            "design_spec",
            {
                "workspace_id": "uhg",
                "spec_type": "component",
                "subject": "CTA Button",
                "requirements": "Primary and secondary variants, 3 sizes",
            },
        )

        assert result["draft_id"] == "draft-comp-001"
        # component spec should NOT persist design context
        agent._config.set.assert_not_called()

    @pytest.mark.asyncio
    async def test_navigation_design(self, agent, mock_llm):
        """Test navigation_design creates a draft."""
        mock_llm.complete.return_value = LLMResponse(
            content="## 1. Desktop Navigation\nHeader layout...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-nav-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)
        agent._config.get = AsyncMock(return_value="")

        result = await agent.tool_registry.execute(
            "navigation_design",
            {
                "workspace_id": "uhg",
                "site_structure": (
                    "5 top-level pages: Home, Discounts, Protection, Guides, Directory"
                ),
            },
        )

        assert result["draft_id"] == "draft-nav-001"
        assert result["status"] == "pending"
        call_kwargs = agent._drafts.create.call_args
        assert call_kwargs.kwargs["content_type"] == "navigation_design"

    @pytest.mark.asyncio
    async def test_interaction_design(self, agent, mock_llm):
        """Test interaction_design creates a draft."""
        mock_llm.complete.return_value = LLMResponse(
            content="## 1. State Definitions\nButton states...",
            model="test",
            usage={"input_tokens": 10, "output_tokens": 50},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-ix-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)
        agent._config.get = AsyncMock(return_value="")

        result = await agent.tool_registry.execute(
            "interaction_design",
            {
                "workspace_id": "uhg",
                "interaction_context": "Search and filter interactions for store directory",
                "interaction_type": "search_filter",
                "component_or_page": "Store Directory page",
            },
        )

        assert result["draft_id"] == "draft-ix-001"
        assert result["status"] == "pending"
        call_kwargs = agent._drafts.create.call_args
        assert call_kwargs.kwargs["content_type"] == "interaction_design"

    @pytest.mark.asyncio
    async def test_screenshot_ux_audit_missing_file(self, agent):
        """Test screenshot_ux_audit handles missing file gracefully."""
        agent._config.get = AsyncMock(return_value="")

        result = await agent.tool_registry.execute(
            "screenshot_ux_audit",
            {
                "workspace_id": "uhg",
                "screenshot_path": "/nonexistent/screenshot.png",
            },
        )

        assert "error" in result
        assert "not found" in result["error"]

    @pytest.mark.asyncio
    async def test_screenshot_ux_audit_with_image(self, agent, mock_llm, tmp_path):
        """Test screenshot_ux_audit processes image and creates draft."""
        # Create a small test image file
        img_path = tmp_path / "test_screenshot.png"
        img_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        audit_json = {
            "scores": {
                "visual_hierarchy": 7,
                "typography": 8,
                "color_usage": 6,
                "spacing": 7,
                "accessibility": 5,
                "navigation_clarity": 8,
                "content_density": 7,
                "mobile_readiness": 6,
            },
            "overall_score": 6.75,
            "findings": ["Good typography hierarchy", "Low contrast on CTA button"],
            "priority_fixes": [
                {
                    "what": "CTA button contrast",
                    "where": "Hero section, center",
                    "why": "WCAG contrast ratio below 4.5:1",
                    "fix": "Change bg to brand-teal-700 text-white",
                    "impact": "Improved accessibility and click-through",
                }
            ],
        }

        mock_llm.complete.return_value = LLMResponse(
            content=json.dumps(audit_json),
            model="test",
            usage={"input_tokens": 100, "output_tokens": 200},
        )
        mock_draft = MagicMock()
        mock_draft.id = "draft-ss-001"
        agent._drafts.create = AsyncMock(return_value=mock_draft)
        agent._config.get = AsyncMock(return_value="")

        result = await agent.tool_registry.execute(
            "screenshot_ux_audit",
            {
                "workspace_id": "uhg",
                "screenshot_path": str(img_path),
                "page_type": "homepage",
            },
        )

        assert result["draft_id"] == "draft-ss-001"
        assert result["overall_score"] == 6.75
        assert result["priority_fixes_count"] == 1
        assert result["scores"]["typography"] == 8
        # Verify multimodal message was sent
        call_args = mock_llm.complete.call_args
        msg = call_args.kwargs["messages"][0]
        assert isinstance(msg.content, list)
        assert msg.content[0]["type"] == "image"
