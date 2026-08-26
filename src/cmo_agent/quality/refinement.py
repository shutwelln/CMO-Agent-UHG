"""Reusable quality refinement loop with dual-LLM support."""

from __future__ import annotations

import json
import re
from typing import Any, Awaitable, Callable, Dict, List, Optional

import structlog

from ..config import get_settings
from ..llm.base import BaseLLM, Message
from .criteria import QualityCriterion, RefinementConfig, RefinementResult, ScoreRecord

logger = structlog.get_logger()

# Type alias for post-hooks: async callables that transform content
PostHook = Callable[[str], Awaitable[str]]

# Contrarian critique system prompt
_CRITIQUE_SYSTEM = (
    "You are a tough, skeptical quality reviewer. Your job is to identify weaknesses, "
    "not confirm quality. Be specific about what is wrong. Do not give inflated scores. "
    "A score of 7 means 'good enough to publish'. Anything below 7 needs revision. "
    "A 10 is nearly impossible."
)


def _strip_markdown_fences(text: str) -> str:
    """Remove markdown code fences (```json ... ```) from LLM output."""
    text = text.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = re.sub(r"^```\w*\s*\n?", "", text)
    if text.endswith("```"):
        text = text[:-3].rstrip()
    return text.strip()


def _clamp(value: float, low: float = 1.0, high: float = 10.0) -> float:
    """Clamp a score to the valid range."""
    return max(low, min(high, value))


def _compute_weighted_overall(
    dimension_scores: Dict[str, float],
    criteria: List[QualityCriterion],
) -> float:
    """Compute weighted average from dimension scores and criteria weights."""
    total_weight = 0.0
    weighted_sum = 0.0
    criteria_map = {c.name: c.weight for c in criteria}

    for name, score in dimension_scores.items():
        weight = criteria_map.get(name, 1.0)
        weighted_sum += score * weight
        total_weight += weight

    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 2)


def _build_critique_prompt(
    content: str,
    brand_voice: str,
    criteria: List[QualityCriterion],
    custom_template: Optional[str] = None,
) -> str:
    """Build the critique prompt from criteria."""
    if custom_template:
        return custom_template.format(content=content, brand_voice=brand_voice)

    criteria_lines = "\n".join(
        f"{i + 1}. {c.name}: {c.description}" for i, c in enumerate(criteria)
    )
    score_keys = ", ".join(f'"{c.name}": N' for c in criteria)

    return f"""Rate the following content on a scale of 1-10 for quality.

BRAND VOICE TO MATCH:
{brand_voice[:500]}

CONTENT:
{content[:3000]}

Score each criterion (1-10):
{criteria_lines}

Return ONLY a JSON object: {{{score_keys}, "feedback": "specific issues to fix"}}"""


def _build_revision_prompt(
    content: str,
    brand_voice: str,
    feedback: str,
    overall_score: float,
    extra_instructions: str = "",
    custom_template: Optional[str] = None,
) -> str:
    """Build the revision prompt from critique feedback."""
    if custom_template:
        return custom_template.format(
            content=content,
            brand_voice=brand_voice,
            feedback=feedback,
            score=overall_score,
        )

    extra = f"\n\nADDITIONAL INSTRUCTIONS:\n{extra_instructions}" if extra_instructions else ""

    return f"""Revise this content based on the critique.

BRAND VOICE:
{brand_voice[:500]}

CURRENT CONTENT:
{content[:3000]}

CRITIQUE (score {overall_score}/10):
{feedback}

Produce the improved version. Address every specific issue raised in the critique.{extra}"""


class RefinementLoop:
    """Iterative quality refinement with dual-LLM support.

    Uses a generation LLM (Sonnet) for content creation/revision and a
    separate critique LLM (Haiku) for scoring, following the project's
    model-per-role pattern.
    """

    def __init__(
        self,
        config: RefinementConfig,
        generation_llm: BaseLLM,
        critique_llm: Optional[BaseLLM] = None,
    ) -> None:
        self.config = config
        self._gen_llm = generation_llm
        self._crit_llm = critique_llm or generation_llm

        # Check per-category override (settings can only disable, not force-enable)
        try:
            settings = get_settings()
            if self.config.log_prefix.startswith("visual_spec"):
                if not settings.refinement_enabled_visual:
                    self.config.enabled = False
            else:
                if not settings.refinement_enabled:
                    self.config.enabled = False
        except Exception:
            pass  # Settings not available (e.g. in tests)

    async def generate_and_refine(
        self,
        generation_prompt: str,
        brand_voice: str = "",
        post_hooks: Optional[List[PostHook]] = None,
    ) -> RefinementResult:
        """Generate content from a prompt, then refine it.

        This is the convenience method for agents that want generation + refinement
        in one call.
        """
        if not self.config.enabled:
            # Bypass mode: single generation, no critique/revision/hooks
            response = await self._gen_llm.complete(
                messages=[Message(role="user", content=generation_prompt)],
                temperature=self.config.generation_temperature,
            )
            return RefinementResult(
                content=response.content,
                best_content=response.content,
                passed_threshold=True,
                iterations_used=0,
                final_score=0.0,
            )

        # Generate initial content
        response = await self._gen_llm.complete(
            messages=[Message(role="user", content=generation_prompt)],
            temperature=self.config.generation_temperature,
        )
        initial_content = response.content

        return await self.refine(initial_content, brand_voice, post_hooks)

    async def refine(
        self,
        initial_content: str,
        brand_voice: str = "",
        post_hooks: Optional[List[PostHook]] = None,
    ) -> RefinementResult:
        """Critique and revise existing content until quality threshold is met.

        Tracks the best-scoring version across iterations. If the loop exhausts
        all iterations without passing threshold, returns the best version with
        passed_threshold=False.
        """
        if not self.config.enabled:
            return RefinementResult(
                content=initial_content,
                best_content=initial_content,
                passed_threshold=True,
                iterations_used=0,
                final_score=0.0,
            )

        body = initial_content
        score_history: List[ScoreRecord] = []
        best_content = body
        best_score = 0.0
        prefix = self.config.log_prefix

        for i in range(self.config.max_iterations):
            # Critique
            critique_prompt = _build_critique_prompt(
                content=body,
                brand_voice=brand_voice,
                criteria=self.config.criteria,
                custom_template=self.config.critique_prompt_template,
            )

            try:
                critique_resp = await self._crit_llm.complete(
                    messages=[
                        Message(role="system", content=_CRITIQUE_SYSTEM),
                        Message(role="user", content=critique_prompt),
                    ],
                    temperature=self.config.critique_temperature,
                )
            except Exception as e:
                logger.warning(f"{prefix}_critique_call_failed", error=str(e), iteration=i + 1)
                break

            # Parse critique JSON
            try:
                raw = _strip_markdown_fences(critique_resp.content)
                critique = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"{prefix}_critique_parse_failed", iteration=i + 1)
                break

            # Extract dimension scores and compute weighted overall
            dimension_scores: Dict[str, float] = {}
            for criterion in self.config.criteria:
                raw_score = critique.get(criterion.name, 5)
                try:
                    dimension_scores[criterion.name] = _clamp(float(raw_score))
                except (ValueError, TypeError):
                    dimension_scores[criterion.name] = 5.0

            overall = _compute_weighted_overall(dimension_scores, self.config.criteria)
            feedback = critique.get("feedback", "Improve quality")
            passed = overall >= self.config.quality_threshold

            record = ScoreRecord(
                iteration=i + 1,
                dimension_scores=dimension_scores,
                overall=overall,
                feedback=str(feedback),
                passed=passed,
            )
            score_history.append(record)

            # Track best version
            if overall > best_score:
                best_score = overall
                best_content = body

            if passed:
                logger.info(
                    f"{prefix}_passed",
                    iteration=i + 1,
                    score=overall,
                    dimensions=dimension_scores,
                )
                break

            # Revise
            revise_prompt = _build_revision_prompt(
                content=body,
                brand_voice=brand_voice,
                feedback=str(feedback),
                overall_score=overall,
                extra_instructions=self.config.extra_revision_instructions,
                custom_template=self.config.revision_prompt_template,
            )

            try:
                revise_resp = await self._gen_llm.complete(
                    messages=[Message(role="user", content=revise_prompt)],
                    temperature=self.config.revision_temperature,
                )
                body = revise_resp.content
            except Exception as e:
                logger.warning(f"{prefix}_revision_failed", error=str(e), iteration=i + 1)
                break

            logger.info(
                f"{prefix}_iteration",
                iteration=i + 1,
                score=overall,
                dimensions=dimension_scores,
            )

        else:
            # Loop exhausted without break (threshold never met)
            if best_score > 0:
                logger.warning(
                    f"{prefix}_threshold_not_met",
                    best_score=best_score,
                    threshold=self.config.quality_threshold,
                    iterations_used=len(score_history),
                )

        # Use best content if we exhausted iterations
        final_passed = any(s.passed for s in score_history)
        if final_passed:
            # Find the version that passed (it's the current body at break time)
            final_content = body
        else:
            final_content = best_content

        # Apply post-hooks in order
        if post_hooks:
            for hook in post_hooks:
                try:
                    final_content = await hook(final_content)
                except Exception as e:
                    logger.warning(f"{prefix}_post_hook_failed", error=str(e))

        final_score = score_history[-1].overall if score_history else 0.0

        return RefinementResult(
            content=final_content,
            score_history=score_history,
            iterations_used=len(score_history),
            final_score=final_score,
            passed_threshold=final_passed,
            best_content=best_content,
        )
