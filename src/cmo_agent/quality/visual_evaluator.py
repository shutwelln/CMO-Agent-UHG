"""Post-generation visual evaluation using Claude vision."""

from __future__ import annotations

import base64
from typing import Any, Dict, Optional

import structlog

from ..llm.base import BaseLLM, Message
from .criteria import ScoreRecord
from .refinement import _clamp, _compute_weighted_overall, _strip_markdown_fences
from .visual_spec import ImageSpec

logger = structlog.get_logger()

# Evaluation dimensions for post-generation image review
_IMAGE_EVAL_CRITERIA = [
    {
        "name": "subject_accuracy",
        "description": "Does the image depict the specified subject?",
        "weight": 1.5,
    },
    {
        "name": "lighting_match",
        "description": "Does the lighting match type/direction/quality/warmth in the spec?",
        "weight": 1.0,
    },
    {
        "name": "composition_quality",
        "description": "Does the composition follow the specified rule, with focal point and negative space as requested?",
        "weight": 1.0,
    },
    {
        "name": "color_accuracy",
        "description": "Does the color palette, saturation, and contrast match the spec?",
        "weight": 1.0,
    },
    {
        "name": "mood_alignment",
        "description": "Does the overall mood and atmosphere match the spec?",
        "weight": 1.0,
    },
    {
        "name": "text_absence",
        "description": "Is the image free of unwanted text, logos, or watermarks?",
        "weight": 2.0,
    },
]


class PostGenerationEvaluator:
    """Evaluates generated images against their specs using Claude vision."""

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def evaluate_image(
        self,
        image_bytes: bytes,
        spec: ImageSpec,
        media_type: str = "image/png",
        threshold: float = 6.0,
    ) -> ScoreRecord:
        """Send image + spec to Claude vision for evaluation.

        Returns a ScoreRecord with dimension scores, overall, and feedback.
        """
        import json

        spec_text = spec.model_dump_json(indent=2)

        criteria_lines = "\n".join(
            f"- {c['name']}: {c['description']}" for c in _IMAGE_EVAL_CRITERIA
        )
        score_keys = ", ".join(f'"{c["name"]}": N' for c in _IMAGE_EVAL_CRITERIA)

        eval_prompt = f"""Evaluate this generated image against the spec below.

IMAGE SPEC:
{spec_text}

Score each dimension (1-10):
{criteria_lines}

Return ONLY a JSON object: {{{score_keys}, "feedback": "specific observations"}}"""

        # Build multimodal message with image + text
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        content_blocks = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": media_type,
                    "data": image_b64,
                },
            },
            {
                "type": "text",
                "text": eval_prompt,
            },
        ]

        try:
            response = await self._llm.complete(
                messages=[Message(role="user", content=content_blocks)],
                temperature=0.3,
            )
        except Exception as e:
            logger.warning("image_evaluation_failed", error=str(e))
            return ScoreRecord(
                iteration=0,
                dimension_scores={},
                overall=0.0,
                feedback=f"Evaluation failed: {e}",
                passed=False,
            )

        # Parse scores
        try:
            raw = _strip_markdown_fences(response.content)
            scores = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("image_evaluation_parse_failed")
            return ScoreRecord(
                iteration=0,
                dimension_scores={},
                overall=0.0,
                feedback="Failed to parse evaluation response",
                passed=False,
            )

        # Extract and clamp dimension scores
        dimension_scores: Dict[str, float] = {}
        from .criteria import QualityCriterion

        criteria_models = []
        for c in _IMAGE_EVAL_CRITERIA:
            raw_score = scores.get(c["name"], 5)
            try:
                dimension_scores[c["name"]] = _clamp(float(raw_score))
            except (ValueError, TypeError):
                dimension_scores[c["name"]] = 5.0
            criteria_models.append(
                QualityCriterion(name=c["name"], description=c["description"], weight=c["weight"])
            )

        overall = _compute_weighted_overall(dimension_scores, criteria_models)
        feedback = scores.get("feedback", "")
        passed = overall >= threshold

        logger.info(
            "image_evaluation_complete",
            overall=overall,
            passed=passed,
            dimensions=dimension_scores,
        )

        return ScoreRecord(
            iteration=0,
            dimension_scores=dimension_scores,
            overall=overall,
            feedback=str(feedback),
            passed=passed,
        )
