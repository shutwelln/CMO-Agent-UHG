"""Structured visual spec models and spec-to-prompt conversion."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

import structlog
from pydantic import BaseModel, Field

from ..llm.base import BaseLLM, Message
from .criteria import QualityCriterion, RefinementConfig, ScoreRecord
from .refinement import RefinementLoop, _clamp, _compute_weighted_overall, _strip_markdown_fences

logger = structlog.get_logger()


# ── Image Spec ────────────────────────────────────────────────────────


class SubjectSpec(BaseModel):
    description: str = ""
    count: int = 1
    expression: str = ""


class SettingSpec(BaseModel):
    location: str = ""
    time_of_day: str = "midday"
    environment: str = "indoor"


class LightingSpec(BaseModel):
    type: str = "natural"
    direction: str = "front"
    quality: str = "soft"
    warmth: str = "warm"
    detail: str = ""


class CameraSpec(BaseModel):
    angle: str = "eye_level"
    distance: str = "medium_shot"
    depth_of_field: str = "shallow"
    lens_style: str = "standard"
    detail: str = ""


class CompositionSpec(BaseModel):
    rule: str = "rule_of_thirds"
    focal_point: str = "center"
    negative_space: str = "none"
    detail: str = ""


class ColorSpec(BaseModel):
    palette: str = "warm_neutrals"
    saturation: str = "moderate"
    contrast: str = "medium"
    detail: str = ""


class ImageSpec(BaseModel):
    subject: SubjectSpec = Field(default_factory=SubjectSpec)
    setting: SettingSpec = Field(default_factory=SettingSpec)
    lighting: LightingSpec = Field(default_factory=LightingSpec)
    camera: CameraSpec = Field(default_factory=CameraSpec)
    composition: CompositionSpec = Field(default_factory=CompositionSpec)
    color: ColorSpec = Field(default_factory=ColorSpec)
    mood: str = "professional"
    style: str = "lifestyle"
    exclusions: List[str] = Field(default_factory=lambda: ["text", "logos", "watermarks"])


# ── Video Spec ────────────────────────────────────────────────────────


class VideoSpec(BaseModel):
    scene_description: str = ""
    camera_movement: str = "static"
    lighting: str = "natural"
    color_grade: str = "neutral"
    pacing: str = "moderate"
    audio_mood: str = "calm"
    duration: int = 5
    aspect_ratio: str = "16:9"
    text_overlays: List[str] = Field(default_factory=list)
    transitions: str = "cut"


# ── Motion Spec ───────────────────────────────────────────────────────


class AnimationFlow(BaseModel):
    entrance: str = "fade_in"
    exit: str = "fade_out"
    timing: str = "sequential"
    easing: str = "ease_in_out"


class ColorScheme(BaseModel):
    background: str = "#FFFFFF"
    primary: str = "#000000"
    accent: str = "#0066CC"
    text: str = "#333333"


class MotionSpec(BaseModel):
    visual_structure: str = ""
    animation_flow: AnimationFlow = Field(default_factory=AnimationFlow)
    text_content: Dict[str, str] = Field(default_factory=dict)
    color_scheme: ColorScheme = Field(default_factory=ColorScheme)
    layout_grid: str = "centered"


# ── Spec Taxonomy (included in generation prompts) ────────────────────

_IMAGE_SPEC_TAXONOMY = """IMAGE SPEC FIELDS (pick from these values):

subject: {description, count, expression}
setting: {location, time_of_day: morning|golden_hour|midday|dusk|night|studio, environment: indoor|outdoor|studio}
lighting: {type: natural|studio|dramatic|rim|rembrandt|split|butterfly|ambient|backlit|overcast, direction: front|left|right|above|behind|below|diffused, quality: soft|hard|diffused|dappled|even, warmth: warm|cool|neutral|golden|blue, detail: optional free-text}
camera: {angle: eye_level|low_angle|high_angle|birds_eye|worms_eye|dutch_angle|over_shoulder, distance: extreme_close_up|close_up|medium_close_up|medium_shot|medium_long|long_shot|extreme_long, depth_of_field: shallow|medium|deep, lens_style: standard|wide_angle|telephoto|macro|tilt_shift, detail: optional free-text}
composition: {rule: rule_of_thirds|centered|golden_ratio|leading_lines|framing|symmetry|diagonal|fill_frame, focal_point: left_third|right_third|center|upper_third|lower_third, negative_space: left|right|top|bottom|none, detail: optional free-text}
color: {palette: warm_neutrals|cool_blues|earth_tones|monochrome|complementary|analogous|muted_pastels|high_contrast, saturation: vibrant|moderate|muted|desaturated, contrast: high|medium|low, detail: optional free-text}
mood: hopeful|trustworthy|energetic|calm|professional|playful|serious|warm|clinical|luxurious
style: editorial_photography|lifestyle|documentary|commercial|fine_art|minimalist|flat_illustration|3d_render|watercolor|abstract
exclusions: list of things to avoid (always include "text", "logos")"""

_VIDEO_SPEC_TAXONOMY = """VIDEO SPEC FIELDS:

scene_description: detailed description of what happens
camera_movement: static|pan_left|pan_right|tilt_up|tilt_down|dolly_in|dolly_out|tracking|orbit|crane|handheld
lighting: natural|studio|dramatic|rim|ambient|backlit|overcast
color_grade: warm|cool|neutral|cinematic|vintage|high_key|low_key
pacing: slow|moderate|fast|building|decelerating
audio_mood: uplifting|calm|energetic|dramatic|ambient|silent
duration: seconds (integer)
aspect_ratio: 16:9|9:16|1:1|4:5
text_overlays: list of text if applicable (empty for most)
transitions: cut|dissolve|fade|wipe|zoom"""

_MOTION_SPEC_TAXONOMY = """MOTION SPEC FIELDS:

visual_structure: description of layout/composition
animation_flow: {entrance: fade_in|slide_left|slide_up|scale_up|typewriter|none, exit: fade_out|slide_right|scale_down|none, timing: sequential|staggered|simultaneous, easing: ease_in_out|ease_in|ease_out|linear|spring|bounce}
text_content: {label_name: "text value"} for all text on screen
color_scheme: {background: hex, primary: hex, accent: hex, text: hex}
layout_grid: centered|split_horizontal|split_vertical|grid_2x2|freeform"""


# ── Spec Critique Criteria ────────────────────────────────────────────

_SPEC_CRITERIA = [
    QualityCriterion(
        name="completeness",
        description="All required fields populated, no empty strings",
        weight=1.5,
    ),
    QualityCriterion(
        name="consistency",
        description="Lighting + mood + color + style are coherent (e.g. warm lighting with cool_blues is contradictory)",
        weight=1.5,
    ),
    QualityCriterion(
        name="specificity",
        description="No vague terms like 'nice', 'good', 'interesting'",
        weight=1.0,
    ),
    QualityCriterion(
        name="brand_fit", description="Spec aligns with brand voice context", weight=1.0
    ),
]


# ── Provider-Specific Prompt Conversion ───────────────────────────────


def spec_to_prompt(spec: ImageSpec, provider: str = "dalle") -> str:
    """Convert a refined ImageSpec into a provider-optimized prompt string."""
    provider = provider.lower()

    if provider in ("dalle", "dall-e", "openai"):
        return _spec_to_dalle_prompt(spec)
    elif provider in ("sdxl", "fal", "fal.ai"):
        return _spec_to_sdxl_prompt(spec)
    elif provider in ("gemini",):
        return _spec_to_gemini_prompt(spec)
    else:
        return _spec_to_dalle_prompt(spec)  # default


def _spec_to_dalle_prompt(spec: ImageSpec) -> str:
    """DALL-E 3: Natural language, <400 chars. Include 'no text' prefix."""
    parts = ["No text, no words, no letters."]

    # Style and subject
    style_label = spec.style.replace("_", " ")
    parts.append(f"{style_label.capitalize()} of {spec.subject.description}")
    if spec.subject.expression:
        parts.append(f"with {spec.subject.expression} expression")

    # Setting
    if spec.setting.location:
        parts.append(f"in {spec.setting.location}")

    # Lighting
    light_desc = (
        f"{spec.lighting.quality} {spec.lighting.type} lighting from the {spec.lighting.direction}"
    )
    if spec.lighting.warmth != "neutral":
        light_desc += f", {spec.lighting.warmth} tones"
    parts.append(light_desc)
    if spec.lighting.detail:
        parts.append(spec.lighting.detail)

    # Camera
    angle = spec.camera.angle.replace("_", " ")
    distance = spec.camera.distance.replace("_", " ")
    parts.append(f"{angle} {distance}")
    if spec.camera.depth_of_field == "shallow":
        parts.append("shallow depth of field blurring background")
    if spec.camera.detail:
        parts.append(spec.camera.detail)

    # Composition
    comp_rule = spec.composition.rule.replace("_", " ")
    parts.append(f"{comp_rule} composition")
    if spec.composition.negative_space != "none":
        parts.append(f"negative space on {spec.composition.negative_space}")
    if spec.composition.detail:
        parts.append(spec.composition.detail)

    # Color
    palette = spec.color.palette.replace("_", " ")
    parts.append(f"{palette} palette, {spec.color.saturation} saturation")
    if spec.color.detail:
        parts.append(spec.color.detail)

    # Mood
    parts.append(f"{spec.mood} mood")

    prompt = ", ".join(parts) + "."

    # Truncate if needed (DALL-E works best under 400 chars)
    if len(prompt) > 400:
        prompt = prompt[:397] + "..."

    return prompt


def _spec_to_sdxl_prompt(spec: ImageSpec) -> str:
    """SDXL via fal.ai: comma-separated tag style."""
    tags = [
        spec.style.replace("_", " "),
        spec.subject.description,
        f"{spec.subject.expression} expression" if spec.subject.expression else "",
        spec.setting.location,
        f"{spec.lighting.type} lighting",
        f"{spec.lighting.warmth} tones" if spec.lighting.warmth != "neutral" else "",
        spec.camera.angle.replace("_", " "),
        spec.camera.distance.replace("_", " "),
        f"{spec.camera.depth_of_field} depth of field",
        spec.composition.rule.replace("_", " "),
        f"{spec.color.palette.replace('_', ' ')} palette",
        spec.mood,
        "no text",
        "no watermark",
    ]
    # Filter empty strings
    tags = [t for t in tags if t]
    return ", ".join(tags)


def _spec_to_gemini_prompt(spec: ImageSpec) -> str:
    """Gemini: Descriptive sentences, up to 1000 chars."""
    parts = [
        f"Create a {spec.style.replace('_', ' ')} image.",
        f"Subject: {spec.subject.description}.",
    ]
    if spec.subject.expression:
        parts.append(f"Expression: {spec.subject.expression}.")
    parts.append(f"Setting: {spec.setting.location}, {spec.setting.time_of_day}.")
    parts.append(
        f"Lighting: {spec.lighting.type}, {spec.lighting.direction}, "
        f"{spec.lighting.quality}, {spec.lighting.warmth} tones."
    )
    if spec.lighting.detail:
        parts.append(spec.lighting.detail)
    parts.append(
        f"Camera: {spec.camera.angle.replace('_', ' ')}, "
        f"{spec.camera.distance.replace('_', ' ')}, "
        f"{spec.camera.depth_of_field} depth of field."
    )
    if spec.camera.detail:
        parts.append(spec.camera.detail)
    parts.append(
        f"Composition: {spec.composition.rule.replace('_', ' ')}, "
        f"focal point at {spec.composition.focal_point.replace('_', ' ')}."
    )
    parts.append(
        f"Colors: {spec.color.palette.replace('_', ' ')}, "
        f"{spec.color.saturation} saturation, {spec.color.contrast} contrast."
    )
    parts.append(f"Mood: {spec.mood}.")
    parts.append("No text, no letters, no words, no logos.")
    return " ".join(parts)


def validate_spec_coverage(spec: ImageSpec, prompt: str) -> List[str]:
    """Check that key spec terms appear in the converted prompt.

    Returns list of missing terms as warnings (not blocking).
    """
    warnings = []
    prompt_lower = prompt.lower()

    checks = {
        "subject": spec.subject.description.split()[0].lower() if spec.subject.description else "",
        "lighting_type": spec.lighting.type.lower(),
        "composition": spec.composition.rule.replace("_", " ").lower(),
        "mood": spec.mood.lower(),
        "style": spec.style.replace("_", " ").lower(),
    }

    for field, term in checks.items():
        if term and term not in prompt_lower:
            warnings.append(f"Missing {field} term: '{term}'")

    return warnings


# ── VisualSpecRefiner ─────────────────────────────────────────────────


class VisualSpecRefiner:
    """Generates and refines structured visual specs before prompt conversion."""

    def __init__(
        self,
        generation_llm: BaseLLM,
        critique_llm: Optional[BaseLLM] = None,
    ) -> None:
        self._gen_llm = generation_llm
        self._crit_llm = critique_llm or generation_llm

    async def generate_spec(
        self,
        user_description: str,
        brand_voice: str = "",
        spec_type: str = "image",
    ) -> Dict[str, Any]:
        """Generate a structured spec from a user description."""
        if spec_type == "video":
            taxonomy = _VIDEO_SPEC_TAXONOMY
            model_name = "VideoSpec"
        elif spec_type == "motion":
            taxonomy = _MOTION_SPEC_TAXONOMY
            model_name = "MotionSpec"
        else:
            taxonomy = _IMAGE_SPEC_TAXONOMY
            model_name = "ImageSpec"

        prompt = f"""Generate a structured {model_name} JSON from this description.

USER DESCRIPTION: {user_description}

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice specified."}

{taxonomy}

Generate a complete JSON spec. Pick specific values from the vocabulary above.
Be concrete and specific - no vague descriptions.
Return ONLY the JSON object, nothing else."""

        response = await self._gen_llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.5,
        )

        try:
            raw = _strip_markdown_fences(response.content)
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("visual_spec_parse_failed", spec_type=spec_type)
            return {}

    async def refine_spec(
        self,
        spec: Dict[str, Any],
        brand_voice: str = "",
        max_iterations: int = 2,
        threshold: float = 7.0,
    ) -> Dict[str, Any]:
        """Run a pre-generation Ralph Loop on the spec (text-only, cheap)."""
        config = RefinementConfig(
            criteria=_SPEC_CRITERIA,
            max_iterations=max_iterations,
            quality_threshold=threshold,
            log_prefix="visual_spec",
        )
        loop = RefinementLoop(
            config=config,
            generation_llm=self._gen_llm,
            critique_llm=self._crit_llm,
        )

        spec_text = json.dumps(spec, indent=2)
        result = await loop.refine(spec_text, brand_voice)

        # Try to parse the refined spec back to dict
        try:
            raw = _strip_markdown_fences(result.content)
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Return original spec if refinement output is not valid JSON
            return spec
