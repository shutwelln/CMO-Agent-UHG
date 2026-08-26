"""Tests for the visual routing guard (_needs_composition) and direct photo pipeline."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cmo_agent.agents.orchestrator import _needs_composition


class TestNeedsComposition:
    """Tests for the deterministic visual routing function."""

    def test_diagram_type(self):
        assert _needs_composition("diagram", "anything") is True

    def test_infographic_type(self):
        assert _needs_composition("infographic", "some metrics") is True

    def test_dashboard_type(self):
        assert _needs_composition("dashboard", "KPI overview") is True

    def test_flow_type(self):
        assert _needs_composition("flow", "process steps") is True

    def test_flowchart_type(self):
        assert _needs_composition("flowchart", "workflow") is True

    def test_timeline_type(self):
        assert _needs_composition("timeline", "project milestones") is True

    def test_comparison_type(self):
        assert _needs_composition("comparison", "features side by side") is True

    def test_ecosystem_type(self):
        assert _needs_composition("ecosystem", "org relationships") is True

    def test_hero_banner_type(self):
        assert _needs_composition("hero_banner", "landing page") is True

    def test_quote_type(self):
        assert _needs_composition("quote", "customer testimonial") is True

    def test_photo_type_no_keywords(self):
        assert _needs_composition("photo", "a sunset over the ocean") is False

    def test_illustration_type_no_keywords(self):
        assert _needs_composition("illustration", "a friendly dog") is False

    def test_abstract_type_no_keywords(self):
        assert _needs_composition("abstract", "geometric shapes") is False

    def test_background_type_no_keywords(self):
        assert _needs_composition("background", "soft gradient") is False

    def test_case_insensitive_type(self):
        assert _needs_composition("DIAGRAM", "something") is True
        assert _needs_composition("Photo", "a cat") is False

    def test_keyword_override_in_description(self):
        """Even if visual_type is photo, composition keywords in description override."""
        assert _needs_composition("photo", "an ecosystem map of our agents") is True
        assert _needs_composition("photo", "a dashboard showing KPIs") is True
        assert _needs_composition("illustration", "a process flow diagram") is True

    def test_no_false_positive_on_common_words(self):
        """Common words shouldn't trigger composition routing."""
        assert _needs_composition("photo", "a beautiful mountain landscape") is False
        assert _needs_composition("photo", "product photography on white background") is False

    def test_keyword_funnel(self):
        assert _needs_composition("photo", "our marketing funnel stages") is True

    def test_keyword_hierarchy(self):
        assert _needs_composition("illustration", "the company hierarchy") is True

    def test_keyword_scorecard(self):
        assert _needs_composition("photo", "balanced scorecard visual") is True


class TestGeneratePhoto:
    """Tests for the direct photo generation pipeline (no ReAct loop)."""

    @pytest.mark.asyncio
    async def test_generate_photo_calls_dalle_directly(self):
        """Verify _generate_photo calls _call_dalle without using the Visual Agent ReAct loop."""
        mock_dalle_result = {
            "url": "https://example.com/image.png",
            "revised_prompt": "a sunset",
        }

        # Create a minimal orchestrator-like object with _generate_photo
        from cmo_agent.agents.orchestrator import CMOOrchestratorAgent

        orch = object.__new__(CMOOrchestratorAgent)
        # Mock Visual Agent (only for API key access)
        orch._visual = MagicMock()
        orch._visual._openai_api_key = "test-key"
        orch._visual._fal_api_key = ""
        orch._visual._gemini_api_key = ""
        orch._visual._sdxl_model = "fal-ai/fast-sdxl"
        orch._media_storage = None
        orch._workspace_mgr = None  # No workspace manager in test

        with (
            patch(
                "cmo_agent.agents.visual._call_dalle",
                new_callable=AsyncMock,
                return_value=mock_dalle_result,
            ) as mock_dalle,
            patch.object(
                orch,
                "_optimize_image_prompt",
                new_callable=AsyncMock,
                side_effect=lambda desc, ws: desc,
            ),
        ):
            result = await orch._generate_photo(
                prompt="a sunset over mountains",
                tier="medium",
                output_format="landscape",
                workspace_id="test",
            )

        # Verify DALL-E was called directly
        mock_dalle.assert_called_once()
        call_kwargs = mock_dalle.call_args
        assert call_kwargs[1]["api_key"] == "test-key"
        assert call_kwargs[1]["size"] == "1792x1024"

        # Verify result
        assert result["status"] == "generated"
        assert result["image_url"] == "https://example.com/image.png"
        assert result["tier"] == "medium"

    @pytest.mark.asyncio
    async def test_generate_photo_no_react_loop(self):
        """Verify that process_message is NOT called (no ReAct loop)."""
        mock_dalle_result = {
            "url": "https://example.com/image.png",
            "revised_prompt": "test",
        }

        from cmo_agent.agents.orchestrator import CMOOrchestratorAgent

        orch = object.__new__(CMOOrchestratorAgent)
        orch._visual = MagicMock()
        orch._visual._openai_api_key = "test-key"
        orch._visual._fal_api_key = ""
        orch._visual._gemini_api_key = ""
        orch._visual._sdxl_model = "fal-ai/fast-sdxl"
        orch._visual.process_message = AsyncMock()
        orch._media_storage = None
        orch._workspace_mgr = None

        with (
            patch(
                "cmo_agent.agents.visual._call_dalle",
                new_callable=AsyncMock,
                return_value=mock_dalle_result,
            ),
            patch.object(
                orch,
                "_optimize_image_prompt",
                new_callable=AsyncMock,
                side_effect=lambda desc, ws: desc,
            ),
        ):
            await orch._generate_photo(
                prompt="test image",
                tier="medium",
                output_format="square",
                workspace_id="test",
            )

        # process_message should NOT have been called
        orch._visual.process_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_generate_photo_size_mapping(self):
        """Verify output_format maps to correct DALL-E sizes."""
        mock_dalle_result = {"url": "https://example.com/img.png", "revised_prompt": "x"}

        from cmo_agent.agents.orchestrator import CMOOrchestratorAgent

        orch = object.__new__(CMOOrchestratorAgent)
        orch._visual = MagicMock()
        orch._visual._openai_api_key = "key"
        orch._visual._fal_api_key = ""
        orch._visual._gemini_api_key = ""
        orch._visual._sdxl_model = "fal-ai/fast-sdxl"
        orch._media_storage = None
        orch._workspace_mgr = None

        for fmt, expected_size in [
            ("landscape", "1792x1024"),
            ("square", "1024x1024"),
            ("portrait", "1024x1792"),
        ]:
            with (
                patch(
                    "cmo_agent.agents.visual._call_dalle",
                    new_callable=AsyncMock,
                    return_value=mock_dalle_result,
                ) as mock_dalle,
                patch.object(
                    orch,
                    "_optimize_image_prompt",
                    new_callable=AsyncMock,
                    side_effect=lambda desc, ws: desc,
                ),
            ):
                await orch._generate_photo(
                    prompt="test", tier="medium", output_format=fmt, workspace_id="test"
                )
                assert mock_dalle.call_args[1]["size"] == expected_size
