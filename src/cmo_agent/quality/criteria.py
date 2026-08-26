"""Quality criteria models for the refinement loop."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class QualityCriterion(BaseModel):
    """A single dimension for quality scoring."""

    name: str
    description: str
    weight: float = 1.0


class RefinementConfig(BaseModel):
    """Configuration for a RefinementLoop instance."""

    criteria: List[QualityCriterion]
    max_iterations: int = 3
    quality_threshold: float = 7.0
    critique_temperature: float = 0.3
    revision_temperature: float = 0.6
    generation_temperature: float = 0.7
    critique_prompt_template: Optional[str] = None
    revision_prompt_template: Optional[str] = None
    extra_revision_instructions: str = ""
    log_prefix: str = "refinement"
    enabled: bool = True


class ScoreRecord(BaseModel):
    """Scores from a single critique iteration."""

    iteration: int
    dimension_scores: Dict[str, float]
    overall: float
    feedback: str = ""
    passed: bool = False


class RefinementResult(BaseModel):
    """Final result from a refinement loop run."""

    content: str
    score_history: List[ScoreRecord] = Field(default_factory=list)
    iterations_used: int = 0
    final_score: float = 0.0
    passed_threshold: bool = False
    best_content: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
