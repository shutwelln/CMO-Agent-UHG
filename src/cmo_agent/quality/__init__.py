"""Quality refinement package - reusable Ralph Loop infrastructure."""

from .criteria import QualityCriterion, RefinementConfig, RefinementResult, ScoreRecord
from .refinement import RefinementLoop

__all__ = [
    "QualityCriterion",
    "RefinementConfig",
    "RefinementResult",
    "RefinementLoop",
    "ScoreRecord",
]
