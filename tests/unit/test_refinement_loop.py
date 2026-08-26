"""Tests for the RefinementLoop quality refinement system."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from cmo_agent.llm.base import BaseLLM, LLMResponse
from cmo_agent.quality import QualityCriterion, RefinementConfig, RefinementLoop
from cmo_agent.quality.hooks import build_hook_chain, make_char_limit_hook, make_em_dash_hook


@pytest.fixture(autouse=True)
def _default_refinement_settings(monkeypatch):
    """Isolate tests from .env refinement settings."""
    from cmo_agent.config import Settings

    fake = Settings(REFINEMENT_ENABLED=True, REFINEMENT_ENABLED_VISUAL=True)
    monkeypatch.setattr("cmo_agent.quality.refinement.get_settings", lambda: fake)


def _make_llm(responses: list[str]) -> AsyncMock:
    """Create a mock LLM that returns responses in sequence."""
    llm = AsyncMock(spec=BaseLLM)
    llm.complete.side_effect = [LLMResponse(content=r, tool_calls=[]) for r in responses]
    return llm


def _default_criteria() -> list[QualityCriterion]:
    return [
        QualityCriterion(name="clarity", description="Clear writing"),
        QualityCriterion(name="tone", description="Correct tone"),
    ]


def _score_json(clarity: float, tone: float, feedback: str = "Good") -> str:
    return json.dumps({"clarity": clarity, "tone": tone, "feedback": feedback})


@pytest.mark.asyncio
async def test_passes_on_first_critique():
    """When critique scores above threshold, no revision is needed."""
    gen_llm = _make_llm(["Initial draft content"])
    crit_llm = _make_llm([_score_json(8, 9)])

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=3,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Write something", "brand voice")

    assert result.passed_threshold is True
    assert result.iterations_used == 1
    assert "Initial draft content" in result.content
    # Generation (1) call on gen_llm, critique (1) on crit_llm
    assert gen_llm.complete.call_count == 1
    assert crit_llm.complete.call_count == 1


@pytest.mark.asyncio
async def test_revises_below_threshold():
    """When critique is below threshold, revision occurs and passes on retry."""
    gen_llm = _make_llm(["Initial draft", "Revised draft"])
    crit_llm = _make_llm(
        [
            _score_json(4, 5, "Needs work"),
            _score_json(8, 9, "Much better"),
        ]
    )

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=3,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Write something", "brand voice")

    assert result.passed_threshold is True
    assert result.iterations_used == 2
    assert "Revised draft" in result.content
    # Generation (1) + revision (1) = 2 gen_llm calls
    assert gen_llm.complete.call_count == 2


@pytest.mark.asyncio
async def test_exhausts_iterations_returns_best():
    """When loop exhausts iterations, returns best-scoring version."""
    gen_llm = _make_llm(["Initial", "Revision 1", "Revision 2"])
    crit_llm = _make_llm(
        [
            _score_json(3, 3),  # iter 1: avg 3
            _score_json(6, 6),  # iter 2: avg 6 (best)
            _score_json(5, 5),  # iter 3: avg 5
        ]
    )

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=3,
        quality_threshold=9.0,  # Impossibly high
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Write something", "brand voice")

    assert result.passed_threshold is False
    assert result.iterations_used == 3
    # Best content is the version that was critiqued when the highest score was recorded.
    # Iteration 2 critiques "Revision 1" and scores it 6.0 (the best).
    assert result.best_content == "Revision 1"  # scored 6 (best)


@pytest.mark.asyncio
async def test_json_parse_failure_breaks_gracefully():
    """When critique returns invalid JSON, loop breaks and returns current content."""
    gen_llm = _make_llm(["Draft content"])
    crit_llm = _make_llm(["This is not JSON at all"])

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=3,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Write something", "brand voice")

    # Should have broken out of loop after parse failure
    assert result.iterations_used == 0  # No successful iterations recorded
    assert "Draft content" in result.content


@pytest.mark.asyncio
async def test_post_hooks_applied_in_order():
    """Post-hooks run in the order specified."""
    gen_llm = _make_llm(["Content with \u2014 em dashes"])
    crit_llm = _make_llm([_score_json(8, 8)])

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=1,
        quality_threshold=7.0,
    )

    call_order = []

    async def hook_a(content: str) -> str:
        call_order.append("a")
        return content.replace("\u2014", " - ")

    async def hook_b(content: str) -> str:
        call_order.append("b")
        return content

    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Write", "", [hook_a, hook_b])

    assert call_order == ["a", "b"]
    assert "\u2014" not in result.content
    assert " - " in result.content


@pytest.mark.asyncio
async def test_bypass_when_disabled():
    """When config.enabled is False, single generation with no critique."""
    gen_llm = _make_llm(["Fast draft"])
    crit_llm = _make_llm([])  # Should never be called

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=3,
        quality_threshold=7.0,
        enabled=False,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Write something", "brand voice")

    assert result.passed_threshold is True
    assert result.iterations_used == 0
    assert result.content == "Fast draft"
    assert gen_llm.complete.call_count == 1
    assert crit_llm.complete.call_count == 0


@pytest.mark.asyncio
async def test_generate_and_refine_convenience():
    """generate_and_refine calls generation then refinement."""
    gen_llm = _make_llm(["Generated content"])
    crit_llm = _make_llm([_score_json(9, 9)])

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=2,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Generate this", "brand")

    assert "Generated content" in result.content
    assert result.passed_threshold is True
    assert gen_llm.complete.call_count == 1  # One generation call


@pytest.mark.asyncio
async def test_custom_criteria_used_in_prompt():
    """Custom criterion names appear in the critique prompt."""
    gen_llm = _make_llm(["Draft"])
    crit_llm = _make_llm([json.dumps({"my_custom_dim": 9, "another_dim": 8, "feedback": "good"})])

    criteria = [
        QualityCriterion(name="my_custom_dim", description="A custom dimension"),
        QualityCriterion(name="another_dim", description="Another dimension"),
    ]
    config = RefinementConfig(
        criteria=criteria,
        max_iterations=1,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    await loop.generate_and_refine("Write", "brand")

    # Verify the critique was called and the prompt contains our dimension names
    crit_call_args = crit_llm.complete.call_args
    messages = crit_call_args[0][0] if crit_call_args[0] else crit_call_args[1]["messages"]
    # Find the user message
    user_msg = [m for m in messages if m.role == "user"][0]
    assert "my_custom_dim" in user_msg.content
    assert "another_dim" in user_msg.content


@pytest.mark.asyncio
async def test_em_dash_hook_strips_dashes():
    """Em dash hook replaces em/en dashes with ' - '."""
    hook = make_em_dash_hook()
    result = await hook("Hello \u2014 world \u2013 test")
    assert "\u2014" not in result
    assert "\u2013" not in result
    assert " - " in result


@pytest.mark.asyncio
async def test_weighted_scoring_computed_not_llm():
    """Overall score is computed from weighted dimensions, not LLM's self-report."""
    gen_llm = _make_llm(["Content"])
    # LLM returns scores but we compute the weighted overall ourselves
    crit_llm = _make_llm([json.dumps({"important": 4, "minor": 10, "feedback": "ok"})])

    criteria = [
        QualityCriterion(name="important", description="High weight", weight=2.0),
        QualityCriterion(name="minor", description="Low weight", weight=1.0),
    ]
    config = RefinementConfig(
        criteria=criteria,
        max_iterations=1,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Write", "brand")

    # Weighted: (4*2.0 + 10*1.0) / (2.0+1.0) = 18/3 = 6.0
    assert result.score_history[0].overall == 6.0
    assert result.passed_threshold is False  # 6.0 < 7.0


@pytest.mark.asyncio
async def test_score_clamping():
    """Scores outside 1-10 are clamped."""
    gen_llm = _make_llm(["Content"])
    crit_llm = _make_llm([json.dumps({"clarity": 15, "tone": -2, "feedback": "extreme"})])

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=1,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    result = await loop.generate_and_refine("Write", "brand")

    scores = result.score_history[0].dimension_scores
    assert scores["clarity"] == 10.0  # Clamped from 15
    assert scores["tone"] == 1.0  # Clamped from -2


@pytest.mark.asyncio
async def test_separate_critique_llm():
    """Generation uses gen_llm, critique uses crit_llm."""
    gen_llm = _make_llm(["Generated by Sonnet"])
    crit_llm = _make_llm([_score_json(9, 9)])

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=1,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    await loop.generate_and_refine("Write", "brand")

    assert gen_llm.complete.call_count == 1  # Generation
    assert crit_llm.complete.call_count == 1  # Critique


@pytest.mark.asyncio
async def test_contrarian_system_prompt():
    """Critique prompt contains skepticism instruction."""
    gen_llm = _make_llm(["Content"])
    crit_llm = _make_llm([_score_json(9, 9)])

    config = RefinementConfig(
        criteria=_default_criteria(),
        max_iterations=1,
        quality_threshold=7.0,
    )
    loop = RefinementLoop(config=config, generation_llm=gen_llm, critique_llm=crit_llm)
    await loop.generate_and_refine("Write", "brand")

    # Check the system message in the critique call
    crit_call_args = crit_llm.complete.call_args
    messages = crit_call_args[0][0] if crit_call_args[0] else crit_call_args[1]["messages"]
    system_msg = [m for m in messages if m.role == "system"][0]
    assert "skeptical" in system_msg.content.lower()
    assert "weaknesses" in system_msg.content.lower()


@pytest.mark.asyncio
async def test_visual_enabled_when_global_off(monkeypatch):
    """Visual spec loops stay enabled even when global refinement is off."""
    from cmo_agent.config import Settings

    fake = Settings(REFINEMENT_ENABLED=False, REFINEMENT_ENABLED_VISUAL=True)
    monkeypatch.setattr("cmo_agent.quality.refinement.get_settings", lambda: fake)

    config = RefinementConfig(
        criteria=_default_criteria(),
        log_prefix="visual_spec_image",
    )
    gen_llm = _make_llm([])
    loop = RefinementLoop(config=config, generation_llm=gen_llm)
    assert loop.config.enabled is True


@pytest.mark.asyncio
async def test_text_disabled_when_global_off(monkeypatch):
    """Text agent loops are disabled when global refinement is off."""
    from cmo_agent.config import Settings

    fake = Settings(REFINEMENT_ENABLED=False, REFINEMENT_ENABLED_VISUAL=True)
    monkeypatch.setattr("cmo_agent.quality.refinement.get_settings", lambda: fake)

    config = RefinementConfig(
        criteria=_default_criteria(),
        log_prefix="writer_refinement",
    )
    gen_llm = _make_llm([])
    loop = RefinementLoop(config=config, generation_llm=gen_llm)
    assert loop.config.enabled is False


@pytest.mark.asyncio
async def test_both_enabled_when_global_on(monkeypatch):
    """When global refinement is on, both text and visual loops are enabled."""
    from cmo_agent.config import Settings

    fake = Settings(REFINEMENT_ENABLED=True, REFINEMENT_ENABLED_VISUAL=True)
    monkeypatch.setattr("cmo_agent.quality.refinement.get_settings", lambda: fake)

    text_config = RefinementConfig(
        criteria=_default_criteria(),
        log_prefix="writer_refinement",
    )
    visual_config = RefinementConfig(
        criteria=_default_criteria(),
        log_prefix="visual_spec_video",
    )
    gen_llm = _make_llm([])
    text_loop = RefinementLoop(config=text_config, generation_llm=gen_llm)
    visual_loop = RefinementLoop(config=visual_config, generation_llm=gen_llm)
    assert text_loop.config.enabled is True
    assert visual_loop.config.enabled is True


@pytest.mark.asyncio
async def test_build_hook_chain_filters_none():
    """build_hook_chain filters out None values."""
    em_dash = make_em_dash_hook()
    chain = build_hook_chain(em_dash, None, make_char_limit_hook(100))
    assert len(chain) == 2
    assert chain[0] is em_dash
