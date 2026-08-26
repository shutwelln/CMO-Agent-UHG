"""Tests for the visual spec system and post-generation evaluator."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from cmo_agent.llm.base import BaseLLM, LLMResponse
from cmo_agent.quality.visual_evaluator import PostGenerationEvaluator
from cmo_agent.quality.visual_spec import (
    ImageSpec,
    VisualSpecRefiner,
    spec_to_prompt,
    validate_spec_coverage,
)


def _make_llm(responses: list[str]) -> AsyncMock:
    """Create a mock LLM that returns responses in sequence."""
    llm = AsyncMock(spec=BaseLLM)
    llm.complete.side_effect = [LLMResponse(content=r, tool_calls=[]) for r in responses]
    return llm


_VALID_IMAGE_SPEC = {
    "subject": {"description": "woman at pharmacy counter", "count": 1, "expression": "relieved"},
    "setting": {"location": "modern pharmacy", "time_of_day": "midday", "environment": "indoor"},
    "lighting": {"type": "natural", "direction": "left", "quality": "soft", "warmth": "warm"},
    "camera": {
        "angle": "eye_level",
        "distance": "medium_shot",
        "depth_of_field": "shallow",
        "lens_style": "standard",
    },
    "composition": {
        "rule": "rule_of_thirds",
        "focal_point": "left_third",
        "negative_space": "right",
    },
    "color": {"palette": "warm_neutrals", "saturation": "moderate", "contrast": "medium"},
    "mood": "hopeful",
    "style": "lifestyle",
    "exclusions": ["text", "logos", "watermarks"],
}


@pytest.mark.asyncio
async def test_generate_image_spec():
    """Mock LLM returns valid ImageSpec JSON, all fields populated."""
    llm = _make_llm([json.dumps(_VALID_IMAGE_SPEC)])
    refiner = VisualSpecRefiner(generation_llm=llm)

    spec = await refiner.generate_spec("A woman picking up prescriptions", "brand voice")

    assert spec["subject"]["description"] == "woman at pharmacy counter"
    assert spec["lighting"]["type"] == "natural"
    assert spec["mood"] == "hopeful"


@pytest.mark.asyncio
async def test_refine_spec_passes():
    """When critique scores spec above threshold, spec is returned."""
    scores = json.dumps(
        {
            "completeness": 9,
            "consistency": 8,
            "specificity": 8,
            "brand_fit": 9,
            "feedback": "Good spec",
        }
    )
    gen_llm = _make_llm([])  # Not used for refine
    crit_llm = _make_llm([scores])

    refiner = VisualSpecRefiner(generation_llm=gen_llm, critique_llm=crit_llm)
    result = await refiner.refine_spec(_VALID_IMAGE_SPEC.copy(), "brand voice")

    # Should return the original spec (serialized and deserialized)
    assert result["mood"] == "hopeful"


@pytest.mark.asyncio
async def test_refine_spec_applies_improvements():
    """When critique suggests improvements, refined version is used."""
    # First critique: below threshold
    scores_low = json.dumps(
        {
            "completeness": 5,
            "consistency": 5,
            "specificity": 4,
            "brand_fit": 5,
            "feedback": "Too vague",
        }
    )
    # After revision: above threshold
    scores_high = json.dumps(
        {
            "completeness": 9,
            "consistency": 9,
            "specificity": 9,
            "brand_fit": 9,
            "feedback": "Great",
        }
    )
    improved_spec = _VALID_IMAGE_SPEC.copy()
    improved_spec["mood"] = "trustworthy"

    gen_llm = _make_llm([json.dumps(improved_spec)])  # Revision
    crit_llm = _make_llm([scores_low, scores_high])

    refiner = VisualSpecRefiner(generation_llm=gen_llm, critique_llm=crit_llm)
    result = await refiner.refine_spec(_VALID_IMAGE_SPEC.copy(), "brand voice")

    assert result["mood"] == "trustworthy"


@pytest.mark.asyncio
async def test_spec_to_prompt_dalle():
    """DALL-E prompt is < 400 chars, includes key terms, includes 'no text'."""
    spec = ImageSpec(**_VALID_IMAGE_SPEC)
    prompt = spec_to_prompt(spec, "dalle")

    assert len(prompt) <= 400
    assert "no text" in prompt.lower()
    assert "natural" in prompt.lower()  # lighting type
    assert "hopeful" in prompt.lower()  # mood


@pytest.mark.asyncio
async def test_spec_to_prompt_sdxl():
    """SDXL prompt uses comma-separated tag style."""
    spec = ImageSpec(**_VALID_IMAGE_SPEC)
    prompt = spec_to_prompt(spec, "sdxl")

    # Should be comma-separated
    assert ", " in prompt
    assert "no text" in prompt.lower()
    assert "lifestyle" in prompt.lower()  # style


@pytest.mark.asyncio
async def test_validate_spec_coverage():
    """Validates that key spec terms appear in the prompt."""
    spec = ImageSpec(**_VALID_IMAGE_SPEC)
    prompt = spec_to_prompt(spec, "dalle")

    # Full prompt should have no warnings
    warnings = validate_spec_coverage(spec, prompt)
    # Most terms should be present
    assert len(warnings) <= 1  # At most one minor miss

    # Artificially broken prompt missing key terms
    bad_prompt = "A photo of something"
    warnings = validate_spec_coverage(spec, bad_prompt)
    assert len(warnings) >= 3  # Should flag multiple missing terms


@pytest.mark.asyncio
async def test_evaluate_image_multimodal():
    """Evaluator sends multimodal message with image block + text block."""
    scores = json.dumps(
        {
            "subject_accuracy": 8,
            "lighting_match": 7,
            "composition_quality": 9,
            "color_accuracy": 8,
            "mood_alignment": 8,
            "text_absence": 10,
            "feedback": "Good image",
        }
    )
    llm = _make_llm([scores])

    evaluator = PostGenerationEvaluator(llm=llm)
    spec = ImageSpec(**_VALID_IMAGE_SPEC)
    result = await evaluator.evaluate_image(b"\x89PNG\r\n", spec)

    # Verify it was called with multimodal content
    call_args = llm.complete.call_args
    messages = call_args[0][0] if call_args[0] else call_args[1]["messages"]
    user_msg = messages[0]
    assert isinstance(user_msg.content, list)
    assert user_msg.content[0]["type"] == "image"
    assert user_msg.content[1]["type"] == "text"

    # Check scores
    assert result.overall > 0
    assert result.passed is True  # Default threshold is 6.0
    assert "subject_accuracy" in result.dimension_scores


@pytest.mark.asyncio
async def test_evaluate_image_below_threshold():
    """Image scoring below threshold returns passed=False."""
    scores = json.dumps(
        {
            "subject_accuracy": 3,
            "lighting_match": 4,
            "composition_quality": 3,
            "color_accuracy": 4,
            "mood_alignment": 3,
            "text_absence": 5,
            "feedback": "Poor match",
        }
    )
    llm = _make_llm([scores])

    evaluator = PostGenerationEvaluator(llm=llm)
    spec = ImageSpec(**_VALID_IMAGE_SPEC)
    result = await evaluator.evaluate_image(b"\x89PNG\r\n", spec, threshold=6.0)

    assert result.passed is False
    assert result.overall < 6.0


@pytest.mark.asyncio
async def test_detail_fields_in_prompt():
    """Spec with lighting.detail includes detail text in converted prompt."""
    spec_dict = _VALID_IMAGE_SPEC.copy()
    spec_dict["lighting"] = {
        "type": "natural",
        "direction": "left",
        "quality": "dappled",
        "warmth": "golden",
        "detail": "dappled sunlight through oak leaves",
    }
    spec = ImageSpec(**spec_dict)
    prompt = spec_to_prompt(spec, "dalle")

    assert "dappled sunlight through oak leaves" in prompt
