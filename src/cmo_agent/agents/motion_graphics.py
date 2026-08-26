"""Motion Graphics Agent - programmatic animation using Remotion."""

from __future__ import annotations

import asyncio
import json
import re
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog

from ..db.database import Database
from ..db.repositories import DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality.visual_spec import MotionSpec, VisualSpecRefiner
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# ── Complexity tier configuration ────────────────────────────────────────

_COMPLEXITY_TIERS: Dict[str, Dict[str, Any]] = {
    "simple": {
        "description": "Basic text animation, logo reveal, or simple lower third. 3-15 seconds duration.",
        "estimated_render_seconds": "7-15",
        "cost": "Free (local CPU rendering)",
        "examples": "Animated title card, text fade-in, logo spin",
        "max_duration_seconds": 15,
    },
    "standard": {
        "description": "Multi-element animation with transitions, animated data points, or branded intro/outro. 5-30 seconds.",
        "estimated_render_seconds": "15-40",
        "cost": "Free (local CPU rendering)",
        "examples": "Animated bar chart, social media counter, multi-slide text sequence",
        "max_duration_seconds": 30,
    },
    "complex": {
        "description": "Full motion graphic with multiple scenes, animated data visualization, or complex particle/shape effects. 10-60 seconds.",
        "estimated_render_seconds": "30-90",
        "cost": "Free (local CPU rendering)",
        "examples": "Animated infographic, full brand video intro, multi-chart data story",
        "max_duration_seconds": 60,
    },
}

# ── Audio track presets ─────────────────────────────────────────────────

_AUDIO_TRACKS: Dict[str, Dict[str, str]] = {
    "corporate": {
        "file": "audio/corporate-ambient.wav",
        "label": "Corporate Ambient",
        "description": "Piano arpeggios over warm pad chords (C-Am-F-G) with soft kick/hi-hat groove at 90 BPM — professional tone for reports, presentations, and branded content",
    },
    "calm": {
        "file": "audio/calm-inspirational.wav",
        "label": "Calm & Inspirational",
        "description": "Flowing piano arpeggios with lush string pads and gentle bass (Cmaj7-Fmaj7-Dm7-G7) at 72 BPM — warm and uplifting for non-profit, community, and storytelling content",
    },
    "energetic": {
        "file": "audio/energetic-upbeat.wav",
        "label": "Energetic & Upbeat",
        "description": "Driving synth chords with lead melody, punchy kick/snare, octave bass line, and hi-hats at 120 BPM — high-energy for product launches, social media, and ads",
    },
    "none": {
        "file": "",
        "label": "No Audio",
        "description": "Silent — visual only",
    },
}

# ── Audio visualization styles ──────────────────────────────────────────

_AUDIO_VIZ_STYLES: Dict[str, str] = {
    "none": "No audio visualization overlay",
    "bars": "Equalizer-style frequency bars at the bottom of the frame",
    "waveform": "Horizontal waveform line across the bottom of the frame",
    "pulse": "Subtle background pulse/glow that reacts to the audio beat",
}


class MotionGraphicsAgent(BaseAgent):
    """Creates programmatic motion graphics using Remotion (React video framework).

    Produces:
    - Animated text sequences and title cards
    - Animated data visualizations (bar charts, line graphs, counters, pie charts)
    - Branded motion graphic intros, outros, and transitions
    - Social media animated content
    - Infographic animations

    All rendering is local and free (CPU time only). Requires Node.js 18+ and
    the Remotion project scaffold at the configured project directory. Falls back
    to code-only output when Node.js or Remotion is not installed.
    """

    agent_id = "motion_graphics_agent"
    agent_name = "Motion Graphics Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        remotion_project_dir: str = "./data/remotion",
        motion_output_dir: str = "./data/motion_graphics",
        media_storage: Optional[Any] = None,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._workspace_mgr = workspace_manager
        self._remotion_project_dir = remotion_project_dir
        self._motion_output_dir = motion_output_dir
        self._media_storage = media_storage
        self._scanning_llm = scanning_llm
        self._spec_refiner = VisualSpecRefiner(generation_llm=llm, critique_llm=scanning_llm)
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def _remotion_available(self) -> bool:
        """Check if Node.js and npx are available on the system."""
        return shutil.which("npx") is not None

    def _project_initialized(self) -> bool:
        """Check if the Remotion project directory exists with a package.json."""
        project = Path(self._remotion_project_dir)
        return project.exists() and (project / "package.json").exists()

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        ws_label = workspace_id or "all workspaces"
        remotion_status = (
            "AVAILABLE"
            if self._remotion_available() and self._project_initialized()
            else "not configured"
        )

        tier_lines = []
        for tier_name, tier_cfg in _COMPLEXITY_TIERS.items():
            tier_lines.append(
                f"  - {tier_name.upper()}: {tier_cfg['description']} "
                f"(render: ~{tier_cfg['estimated_render_seconds']}s)"
            )
        tiers_text = "\n".join(tier_lines)

        return f"""You are the Motion Graphics Agent for {ws_label}.
You create programmatic motion graphics using Remotion (React video framework).

This is DIFFERENT from the Video Agent:
- Motion Graphics Agent = programmatic animations (text, data viz, branded graphics, counters, charts)
- Video Agent = AI-generated video from prompts (fal.ai, Sora)

This is also DIFFERENT from composed visuals (diagrams, dashboards, ecosystem maps, process flows).
The Composition Pipeline handles structured text-on-visual layouts using parametric Remotion templates.
You handle FREEFORM programmatic animations: logo reveals, animated counters, custom data
visualizations, kinetic typography, and bespoke motion design that doesn't fit a standard template.

Remotion rendering: {remotion_status}
All rendering is FREE (local CPU time only).

Complexity tiers:
{tiers_text}

IMPORTANT: When asked to create a motion graphic, ALWAYS call get_motion_pricing first
to show the user available options and estimated render times.

You can:
- Generate React/TypeScript Remotion compositions for any animation type
- Create animated text sequences, title cards, and lower thirds
- Build animated data visualizations (bar charts, line graphs, counters, pie charts)
- Produce branded intros, outros, and transitions
- Suggest motion graphic concepts for marketing content

When creating motion graphics:
- Match the brand voice and colors
- Keep animations smooth and professional (30fps default)
- Use easing functions for natural motion (spring, interpolate with Easing)
- Optimize for the target platform (aspect ratio, duration)

Standard formats:
- Social media square: 1080x1080, 5-15s
- Instagram Reel / TikTok: 1080x1920 (9:16), 5-30s
- YouTube / LinkedIn: 1920x1080 (16:9), 5-60s
- Story: 1080x1920 (9:16), 5-15s segments

Audio options:
- Background music: corporate, calm, energetic, or none (default: none)
- Audio visualization: none, bars (equalizer), waveform, or pulse (default: none)
When a user requests audio, set audio_track and/or audio_viz on create_motion_graphic.

Current workspace: {ws_label}"""

    def register_tools(self) -> None:  # noqa: C901
        @self.tool_registry.register(
            name="get_motion_pricing",
            description=(
                "Show motion graphics rendering options, complexity tiers, and estimated "
                "render times. All local rendering is FREE. Call this BEFORE "
                "create_motion_graphic so the user can choose a complexity tier. "
                "No external API call is made."
            ),
        )
        async def get_motion_pricing() -> Dict[str, Any]:
            tiers = []
            for tier_name, cfg in _COMPLEXITY_TIERS.items():
                tiers.append(
                    {
                        "tier": tier_name,
                        "description": cfg["description"],
                        "estimated_render_time": cfg["estimated_render_seconds"],
                        "cost": cfg["cost"],
                        "examples": cfg["examples"],
                        "max_duration_seconds": cfg["max_duration_seconds"],
                    }
                )
            audio_options = {
                "tracks": {
                    k: v["label"] + " — " + v["description"] for k, v in _AUDIO_TRACKS.items()
                },
                "visualization_styles": _AUDIO_VIZ_STYLES,
            }
            return {
                "tiers": tiers,
                "audio": audio_options,
                "remotion_available": self._remotion_available(),
                "project_initialized": self._project_initialized(),
                "note": "All local rendering is FREE. Audio and visualization are optional add-ons at no cost.",
                "instructions": "Present these options to the user and ask them to choose a complexity tier (and optionally audio settings) before calling create_motion_graphic.",
            }

        @self.tool_registry.register(
            name="suggest_motion_concepts",
            description=(
                "Brainstorm motion graphic ideas for a marketing topic or campaign. "
                "Returns concepts with animation type, complexity, and platform recommendations."
            ),
        )
        async def suggest_motion_concepts(
            content: str,
            workspace_id: str,
            count: int = 3,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Suggest {count} motion graphic concepts for this marketing content.

CONTENT:
{content[:1000]}

BRAND CONTEXT:
{brand_voice[:300] if brand_voice else "No brand voice specified."}

Motion graphics are programmatic animations (NOT AI-generated video). Think:
- Animated text sequences and title cards
- Animated data visualizations (bar charts, counters, pie charts)
- Logo reveals and branded intros
- Animated infographics
- Social media animated content

For each suggestion provide:
1. Title
2. Brief description of the animation
3. Animation type (text_animation, data_viz, branded_intro, infographic, social_content)
4. Recommended platform (instagram_reel, youtube, linkedin, tiktok, story)
5. Recommended duration in seconds
6. Complexity tier (simple, standard, complex)
7. Why this concept works for the brand

Return as a JSON array of objects with keys: title, description, animation_type, platform, duration, complexity, rationale"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.8,
            )

            try:
                concepts = json.loads(response.content)
            except (json.JSONDecodeError, TypeError):
                concepts = [{"title": "Parse error", "description": response.content}]

            return {"concepts": concepts, "count": len(concepts)}

        @self.tool_registry.register(
            name="create_motion_graphic",
            description=(
                "Generate a Remotion composition and render it to MP4. Requires: "
                "a description of the animation, workspace_id, and complexity tier "
                "(simple/standard/complex). Optionally add background music "
                "(audio_track: corporate/calm/energetic/none) and audio visualization "
                "(audio_viz: none/bars/waveform/pulse). Call get_motion_pricing first "
                "to show the user available options."
            ),
        )
        async def create_motion_graphic(
            description: str,
            workspace_id: str,
            complexity: str = "simple",
            duration_seconds: int = 10,
            width: int = 1080,
            height: int = 1080,
            fps: int = 30,
            animation_type: str = "general",
            audio_track: str = "none",
            audio_viz: str = "none",
        ) -> Dict[str, Any]:
            return await self._create_motion_graphic_internal(
                description=description,
                workspace_id=workspace_id,
                complexity=complexity,
                duration_seconds=duration_seconds,
                width=width,
                height=height,
                fps=fps,
                animation_type=animation_type,
                audio_track=audio_track,
                audio_viz=audio_viz,
            )

        @self.tool_registry.register(
            name="create_animated_text",
            description=(
                "Quick text animation: animated title card, quote reveal, or text sequence. "
                "Lower barrier to entry than create_motion_graphic. Generates and renders automatically."
            ),
        )
        async def create_animated_text(
            text: str,
            workspace_id: str,
            style: str = "fade_in",
            duration_seconds: int = 5,
            width: int = 1080,
            height: int = 1080,
            background_color: str = "#1a1a2e",
            text_color: str = "#ffffff",
            audio_track: str = "none",
            audio_viz: str = "none",
        ) -> Dict[str, Any]:
            description = (
                f"Animated text: '{text}'. Style: {style}. "
                f"Background: {background_color}, text color: {text_color}. "
                f"This should be a clean, professional text animation."
            )
            return await self._create_motion_graphic_internal(
                description=description,
                workspace_id=workspace_id,
                complexity="simple",
                duration_seconds=duration_seconds,
                width=width,
                height=height,
                animation_type="text_animation",
                audio_track=audio_track,
                audio_viz=audio_viz,
            )

        @self.tool_registry.register(
            name="create_data_visualization",
            description=(
                "Create an animated data visualization: bar chart, line graph, counter, "
                "or pie chart. Provide the data points and chart type."
            ),
        )
        async def create_data_visualization(
            title: str,
            data_points: str,
            workspace_id: str,
            chart_type: str = "bar_chart",
            duration_seconds: int = 10,
            width: int = 1920,
            height: int = 1080,
            audio_track: str = "none",
            audio_viz: str = "none",
        ) -> Dict[str, Any]:
            description = (
                f"Animated {chart_type} visualization. Title: '{title}'. "
                f"Data: {data_points}. "
                f"Animate the data appearing progressively with smooth easing. "
                f"Use brand colors. Professional and clean style."
            )
            return await self._create_motion_graphic_internal(
                description=description,
                workspace_id=workspace_id,
                complexity="standard",
                duration_seconds=duration_seconds,
                width=width,
                height=height,
                animation_type="data_viz",
                audio_track=audio_track,
                audio_viz=audio_viz,
            )

    # ── Internal implementation ──────────────────────────────────────────

    async def _optimize_motion_prompt(
        self,
        description: str,
        brand_voice: str,
    ) -> str:
        """Refine user description into a structured brief using MotionSpec."""
        try:
            spec_dict = await self._spec_refiner.generate_spec(
                user_description=description,
                brand_voice=brand_voice,
                spec_type="motion",
            )
            if spec_dict:
                spec_dict = await self._spec_refiner.refine_spec(
                    spec=spec_dict,
                    brand_voice=brand_voice,
                )
                # Convert spec to structured brief format
                try:
                    motion_spec = MotionSpec(**spec_dict)
                except Exception:
                    motion_spec = None

                if motion_spec:
                    brief_parts = [
                        f"VISUAL STRUCTURE: {motion_spec.visual_structure}",
                        f"ANIMATION FLOW: entrance={motion_spec.animation_flow.entrance}, exit={motion_spec.animation_flow.exit}, timing={motion_spec.animation_flow.timing}, easing={motion_spec.animation_flow.easing}",
                    ]
                    if motion_spec.text_content:
                        text_items = ", ".join(
                            f"{k}: {v}" for k, v in motion_spec.text_content.items()
                        )
                        brief_parts.append(f"TEXT CONTENT: {text_items}")
                    cs = motion_spec.color_scheme
                    brief_parts.append(
                        f"COLORS: bg={cs.background}, primary={cs.primary}, accent={cs.accent}, text={cs.text}"
                    )
                    brief_parts.append(f"LAYOUT: {motion_spec.layout_grid}")
                    refined = "\n".join(brief_parts)
                    logger.info(
                        "motion_prompt_optimized",
                        original_len=len(description),
                        refined_len=len(refined),
                    )
                    return refined
        except Exception as e:
            logger.warning("motion_spec_generation_failed", error=str(e))

        # Fallback to legacy prompt optimization
        prompt = f"""Refine this motion graphic description into a structured brief for a React developer.

USER DESCRIPTION: {description}

BRAND CONTEXT:
{brand_voice[:300] if brand_voice else "No brand voice specified."}

Produce a structured brief with:
- VISUAL STRUCTURE: What elements appear, their positions, groupings
- ANIMATION FLOW: Sequence of animations, timing, movement direction
- TEXT CONTENT: All labels, headings, numbers that should appear on screen
- COLOR GUIDANCE: Primary, secondary, accent colors from brand context

Keep the brief under 800 characters. Be specific and concrete.
Return ONLY the structured brief, nothing else."""

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.5,
            max_tokens=1024,
        )
        refined = response.content.strip()
        logger.info(
            "motion_prompt_optimized", original_len=len(description), refined_len=len(refined)
        )
        return refined

    async def _create_motion_graphic_internal(
        self,
        description: str,
        workspace_id: str,
        complexity: str = "simple",
        duration_seconds: int = 10,
        width: int = 1080,
        height: int = 1080,
        fps: int = 30,
        animation_type: str = "general",
        audio_track: str = "none",
        audio_viz: str = "none",
    ) -> Dict[str, Any]:
        """Core pipeline: generate composition code, render, upload, save draft."""
        complexity = complexity.lower()
        if complexity not in _COMPLEXITY_TIERS:
            return {
                "error": f"Invalid complexity tier '{complexity}'. Choose from: simple, standard, complex.",
                "status": "failed",
            }

        tier_cfg = _COMPLEXITY_TIERS[complexity]
        max_dur = tier_cfg["max_duration_seconds"]
        if duration_seconds > max_dur:
            return {
                "error": f"Duration {duration_seconds}s exceeds max {max_dur}s for {complexity} tier.",
                "status": "failed",
            }

        # Validate audio settings
        audio_track = audio_track.lower() if audio_track else "none"
        audio_viz = audio_viz.lower() if audio_viz else "none"
        if audio_track not in _AUDIO_TRACKS:
            audio_track = "none"
        if audio_viz not in _AUDIO_VIZ_STYLES:
            audio_viz = "none"

        audio_file = _AUDIO_TRACKS[audio_track]["file"] if audio_track != "none" else ""

        brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
        reference_docs = await self._workspace_mgr.get_reference_docs(workspace_id)

        # Step 0: Optimize the description into a structured brief
        description = await self._optimize_motion_prompt(description, brand_voice)

        # Step 1: Generate Remotion composition code via LLM
        composition_code = await self._generate_composition_code(
            description=description,
            brand_voice=brand_voice,
            reference_docs=reference_docs,
            duration_seconds=duration_seconds,
            width=width,
            height=height,
            fps=fps,
            animation_type=animation_type,
            complexity=complexity,
            audio_file=audio_file,
            audio_viz=audio_viz,
        )

        composition_id = f"MotionGraphic{uuid4().hex[:8]}"

        # Step 2: If Remotion is available, write + render (with 1 repair attempt)
        if self._remotion_available() and self._project_initialized():
            rendered = None
            last_error = None
            for attempt in range(2):  # attempt 0 = original, attempt 1 = repaired
                try:
                    rendered = await self._write_and_render(
                        composition_id=composition_id,
                        composition_code=composition_code,
                        duration_seconds=duration_seconds,
                        width=width,
                        height=height,
                        fps=fps,
                    )
                    break  # Success — exit retry loop
                except Exception as e:
                    last_error = str(e)
                    if attempt == 0:
                        logger.warning(
                            "motion_render_attempt_failed",
                            attempt=attempt,
                            error=last_error,
                        )
                        # Attempt LLM repair
                        try:
                            composition_code = await self._repair_code(
                                code=composition_code,
                                error=last_error,
                                width=width,
                            )
                        except Exception as repair_err:
                            logger.error("motion_repair_failed", error=str(repair_err))
                            break  # Can't repair — give up
                    else:
                        logger.error("motion_render_repair_failed", error=last_error)

            if rendered is None:
                return {
                    "status": "code_only",
                    "composition_code": composition_code,
                    "composition_id": composition_id,
                    "render_error": last_error,
                    "message": "Rendering failed after repair attempt. The composition code is provided for manual use.",
                }

            # Step 3: Upload to Supabase if available
            local_path = rendered["output_path"]
            cdn_url = None
            asset_id = None
            if self._media_storage:
                try:
                    asset = await self._media_storage.upload_from_file(
                        file_path=local_path,
                        workspace_id=workspace_id,
                        media_type="motion_graphic",
                        source_agent=self.agent_id,
                        prompt=description,
                        metadata={
                            "complexity": complexity,
                            "duration": duration_seconds,
                            "width": width,
                            "height": height,
                            "fps": fps,
                            "animation_type": animation_type,
                        },
                    )
                    cdn_url = asset.cdn_url
                    asset_id = asset.id
                except Exception as e:
                    logger.warning("motion_media_upload_failed", error=str(e))

            # Step 4: Save as draft
            body = json.dumps(
                {
                    "video_url": cdn_url or local_path,
                    "local_path": local_path,
                    "composition_code": composition_code,
                    "composition_id": composition_id,
                    "complexity": complexity,
                    "duration_seconds": duration_seconds,
                    "dimensions": f"{width}x{height}",
                    "fps": fps,
                    "render_time_seconds": rendered.get("render_time_seconds"),
                }
            )
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="motion_graphic",
                title=f"Motion Graphic: {description[:60]}",
                body=body,
            )

            if asset_id and self._media_storage:
                try:
                    await self._media_storage.link_to_draft(asset_id, draft.id)
                except Exception as e:
                    logger.warning("motion_media_link_failed", error=str(e))

            logger.info(
                "motion_graphic_created",
                composition_id=composition_id,
                complexity=complexity,
                render_time=rendered.get("render_time_seconds"),
                local_path=local_path,
                draft_id=draft.id,
            )

            return {
                "status": "rendered",
                "video_url": cdn_url or local_path,
                "local_path": local_path,
                "draft_id": draft.id,
                "composition_id": composition_id,
                "composition_code": composition_code,
                "render_time_seconds": rendered.get("render_time_seconds"),
                "cost": "Free (local rendering)",
                "asset_id": asset_id,
            }
        else:
            # Code-only output when Remotion not available
            return {
                "status": "code_only",
                "composition_code": composition_code,
                "composition_id": composition_id,
                "message": (
                    "Remotion is not installed or project not initialized. "
                    "The composition code is provided. To render: "
                    "1) Install Node.js 18+, "
                    "2) Run 'npx create-video@latest' in the remotion project dir, "
                    "3) Add this composition and run 'npx remotion render'."
                ),
                "cost": "Free (local rendering)",
            }

    async def _generate_composition_code(
        self,
        description: str,
        brand_voice: str,
        reference_docs: str = "",
        duration_seconds: int = 10,
        width: int = 1080,
        height: int = 1080,
        fps: int = 30,
        animation_type: str = "general",
        complexity: str = "simple",
        audio_file: str = "",
        audio_viz: str = "none",
    ) -> str:
        """Use the LLM to generate Remotion React/TypeScript composition code."""
        total_frames = duration_seconds * fps

        ref_docs_section = ""
        if reference_docs:
            ref_docs_section = f"""
REFERENCE DOCUMENTS (use real data, metrics, and facts from these):
{reference_docs[:15000]}
"""

        # Build audio instructions
        audio_section = ""
        if audio_file or audio_viz != "none":
            audio_section = "\nAUDIO REQUIREMENTS:\n"
            if audio_file:
                audio_section += f"""- Add background music: import {{ Audio }} from "remotion"; and {{ staticFile }} from "remotion";
- Use: <Audio src={{staticFile("{audio_file}")}} volume={{(f) => interpolate(f, [0, {fps}], [0, 0.6], {{extrapolateRight: "clamp"}})}} />
- Place the <Audio> tag inside the <AbsoluteFill> alongside the visual content.
- The audio should fade in over the first second and play at 0.6 volume.
"""
            if audio_viz == "bars":
                audio_section += f"""- Add equalizer visualization: import {{ useAudioData, visualizeAudio }} from "@remotion/media-utils";
- Load audio data: const audioData = useAudioData(staticFile("{audio_file}"));
- Get frequency bars: const viz = audioData ? visualizeAudio({{ fps, frame, audioData, numberOfSamples: 16 }}) : [];
- Render bars in a row at the BOTTOM of the frame (position: absolute, bottom: 0).
- Each bar: width ~40px, height = viz[i] * 100, with brand accent color and slight opacity.
- If audioData is null (loading), render nothing for the bars.
"""
            elif audio_viz == "waveform":
                audio_section += f"""- Add waveform visualization: import {{ useAudioData, visualizeAudioWaveform }} from "@remotion/media-utils";
- Load audio data: const audioData = useAudioData(staticFile("{audio_file}"));
- Get waveform: const waveform = audioData ? visualizeAudioWaveform({{ audioData, frame, fps, numberOfSamples: 128, windowInSeconds: 1 }}) : [];
- Render as an SVG polyline path at the BOTTOM of the frame (position: absolute, bottom: 20).
- Use brand accent color with 0.5 opacity. Height range ~50px.
"""
            elif audio_viz == "pulse":
                audio_section += f"""- Add pulse visualization: import {{ useAudioData, visualizeAudio }} from "@remotion/media-utils";
- Load audio data: const audioData = useAudioData(staticFile("{audio_file}"));
- Get amplitude: const viz = audioData ? visualizeAudio({{ fps, frame, audioData, numberOfSamples: 4 }}) : [0];
- const amplitude = viz.reduce((a, b) => a + b, 0) / viz.length;
- Apply a subtle background glow/scale effect using the amplitude value (e.g., background opacity pulses between 0.02 and 0.08).
"""

        # Compute concrete minimum font sizes for this specific render dimensions
        heading_min = max(96, int(width * 0.089))  # ~96px at 1080, ~170px at 1920
        subtitle_min = max(48, int(width * 0.044))  # ~48px at 1080, ~84px at 1920
        body_min = max(32, int(width * 0.030))  # ~32px at 1080, ~58px at 1920
        metric_min = max(110, int(width * 0.102))  # ~110px at 1080, ~196px at 1920
        absolute_min = max(28, int(width * 0.026))  # ~28px at 1080, ~50px at 1920

        prompt = f"""Generate a Remotion React/TypeScript composition for this motion graphic.

╔══════════════════════════════════════════════════════════════════════════╗
║  TYPOGRAPHY IS THE #1 PRIORITY. TEXT MUST BE LARGE AND BOLD.           ║
║  If text is too small, the entire motion graphic is unusable.          ║
║  These are MINIMUM sizes for this {width}x{height} render:              ║
║                                                                        ║
║  HEADINGS / HERO TITLES:    fontSize: {heading_min}  fontWeight: 800     ║
║  SUBTITLES / SECTION HEADS: fontSize: {subtitle_min}  fontWeight: 700     ║
║  BODY TEXT / LABELS:         fontSize: {body_min}  fontWeight: 500        ║
║  METRIC VALUES / BIG NUMBERS: fontSize: {metric_min}  fontWeight: 900    ║
║  ABSOLUTE MINIMUM ANY TEXT:  fontSize: {absolute_min}                     ║
║                                                                        ║
║  Headings must DOMINATE the frame — fill 60-80% of width.             ║
║  NEVER use fontSize below {absolute_min}. It is unreadable in video.    ║
╚══════════════════════════════════════════════════════════════════════════╝

DESCRIPTION: {description}
ANIMATION TYPE: {animation_type}
COMPLEXITY: {complexity}
DIMENSIONS: {width}x{height}
DURATION: {duration_seconds}s ({total_frames} frames at {fps}fps)

BRAND CONTEXT:
{brand_voice[:400] if brand_voice else "No brand voice specified. Use a clean, professional style."}
{ref_docs_section}
{audio_section}
REQUIREMENTS:
- Use React with TypeScript
- Import from 'remotion': useCurrentFrame, useVideoConfig, interpolate, spring, Sequence, AbsoluteFill
- Export a default React component
- Use interpolate() and spring() for smooth animations
- Use Easing from 'remotion' for custom easing curves
- Total frames = {total_frames}
- Component should be self-contained (no external assets unless using web fonts via @import in style tags)
- Use inline styles (React CSSProperties)
- Colors should match brand if provided, otherwise use a professional palette
- Keep the code CONCISE — use arrays/maps for repeated metric items instead of duplicating JSX blocks
- Aim for under 300 lines of code total. Refactor repeated patterns into small inline helpers
- CRITICAL: You MUST complete the entire component including the final `export default` statement

RETURN FORMAT:
Return ONLY the TypeScript/React code for the composition component. No markdown fences, no explanation.
Start with the import statement and end with the export default.

Example structure (note the LARGE font sizes — this is the standard):
import {{ useCurrentFrame, useVideoConfig, interpolate, spring, AbsoluteFill }} from "remotion";

const MyComposition: React.FC = () => {{
  const frame = useCurrentFrame();
  const {{ fps }} = useVideoConfig();
  // ... animation logic using interpolate/spring
  return (
    <AbsoluteFill style={{{{ backgroundColor: "#1a1a2e" }}}}>
      <div style={{{{ fontSize: {heading_min}, fontWeight: 800, color: "#ffffff" }}}}>
        {{/* Heading text — MUST be {heading_min}px or larger */}}
      </div>
      <div style={{{{ fontSize: {subtitle_min}, fontWeight: 700, color: "#cccccc" }}}}>
        {{/* Subtitle — MUST be {subtitle_min}px or larger */}}
      </div>
    </AbsoluteFill>
  );
}};

export default MyComposition;"""

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.4,
            max_tokens=8192,
        )

        code = response.content.strip()
        # Strip markdown code fences if present
        if code.startswith("```"):
            code = re.sub(r"^```(?:tsx?|typescript|javascript)?\s*\n?", "", code)
            code = re.sub(r"\n?```\s*$", "", code)

        # Repair truncated output: ensure the code has a valid export default
        if "export default" not in code:
            # Try to detect the component name from the code
            comp_match = re.search(r"const\s+(\w+)\s*:\s*React\.FC", code)
            comp_name = comp_match.group(1) if comp_match else "Composition"

            # Count unmatched braces/parens and close them
            open_braces = code.count("{") - code.count("}")
            open_parens = code.count("(") - code.count(")")
            open_angles = code.count("<") - code.count(">")

            # Close JSX tags, parens, braces in order
            for _ in range(max(0, open_angles)):
                code += "\n/>"
            for _ in range(max(0, open_parens)):
                code += "\n)"
            code += "\n);\n};\n" if open_braces > 0 else "\n"
            code += f"\nexport default {comp_name};"
            logger.warning("motion_code_repaired", component=comp_name, added_braces=open_braces)

        # ── Post-generation font size enforcement ────────────────────────
        # Scan the generated code for fontSize values and enforce minimums.
        # The LLM often ignores sizing instructions, so we fix it here.
        absolute_min = max(28, int(width * 0.026))

        def _bump_font_size(match: re.Match) -> str:
            """Replace fontSize values below the absolute minimum."""
            prefix = match.group(1)  # e.g. 'fontSize: ' or 'fontSize:'
            value = int(match.group(2))
            if value < absolute_min:
                logger.warning(
                    "motion_font_size_bumped",
                    original=value,
                    bumped_to=absolute_min,
                )
                return f"{prefix}{absolute_min}"
            return match.group(0)

        code = re.sub(r"(fontSize:\s*)(\d+)", _bump_font_size, code)

        return code

    async def _validate_syntax(self, filepath: str) -> Optional[str]:
        """Fast syntax check via esbuild (<10ms). Returns error message or None."""
        project_dir = Path(self._remotion_project_dir).resolve()
        cmd = [
            "npx",
            "esbuild",
            filepath,
            "--outfile=/dev/null",
            "--bundle",
            "--external:remotion",
            "--external:react",
            "--external:@remotion/*",
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(project_dir),
            )
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
        except asyncio.TimeoutError:
            logger.warning("esbuild_timeout", filepath=filepath)
            return None  # Don't block on esbuild timeout — let render try
        except Exception as e:
            logger.warning("esbuild_error", error=str(e))
            return None  # esbuild not available — skip validation

        if process.returncode == 0:
            logger.info("motion_syntax_valid", filepath=filepath)
            return None

        error_text = stderr.decode("utf-8", errors="replace")[:2000]
        # Extract the most useful esbuild error line
        for line in error_text.split("\n"):
            if "ERROR" in line.upper():
                return line.strip()
        return error_text.strip()

    async def _repair_code(self, code: str, error: str, width: int) -> str:
        """Feed error + code back to LLM for a targeted fix."""
        prompt = f"""The following Remotion React/TypeScript composition has a syntax or render error.
Fix ONLY the error. Do not rewrite from scratch. Preserve all animation logic, styles, and structure.

ERROR:
{error[:1500]}

CODE:
{code}

Return ONLY the fixed TypeScript/React code. No markdown fences, no explanation.
Start with the import statement and end with the export default."""

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.2,
            max_tokens=8192,
        )

        fixed = response.content.strip()
        # Strip markdown code fences if present
        if fixed.startswith("```"):
            fixed = re.sub(r"^```(?:tsx?|typescript|javascript)?\s*\n?", "", fixed)
            fixed = re.sub(r"\n?```\s*$", "", fixed)

        # Apply same font-size enforcement
        absolute_min = max(28, int(width * 0.026))

        def _bump_font_size(match: re.Match) -> str:
            prefix = match.group(1)
            value = int(match.group(2))
            if value < absolute_min:
                return f"{prefix}{absolute_min}"
            return match.group(0)

        fixed = re.sub(r"(fontSize:\s*)(\d+)", _bump_font_size, fixed)

        logger.info("motion_code_repaired", original_len=len(code), fixed_len=len(fixed))
        return fixed

    async def _write_and_render(
        self,
        composition_id: str,
        composition_code: str,
        duration_seconds: int,
        width: int,
        height: int,
        fps: int,
    ) -> Dict[str, Any]:
        """Write composition to project, render with npx remotion render, return output path."""
        project_dir = Path(self._remotion_project_dir)
        compositions_dir = project_dir / "src" / "compositions"
        compositions_dir.mkdir(parents=True, exist_ok=True)

        # Write the composition file
        comp_filename = f"{composition_id}.tsx"
        comp_path = compositions_dir / comp_filename
        comp_path.write_text(composition_code, encoding="utf-8")

        # Fast syntax validation via esbuild before expensive render
        syntax_error = await self._validate_syntax(str(comp_path))
        if syntax_error:
            logger.warning("motion_syntax_invalid", error=syntax_error)
            raise RuntimeError(f"Syntax validation failed: {syntax_error}")

        # Write/update the Root.tsx to register this composition
        total_frames = duration_seconds * fps
        root_path = project_dir / "src" / "Root.tsx"
        root_content = f'''import {{ Composition }} from "remotion";
import {composition_id} from "./compositions/{composition_id}";

export const RemotionRoot: React.FC = () => {{
  return (
    <>
      <Composition
        id="{composition_id}"
        component={{{composition_id}}}
        durationInFrames={{{total_frames}}}
        fps={{{fps}}}
        width={{{width}}}
        height={{{height}}}
      />
    </>
  );
}};
'''
        root_path.write_text(root_content, encoding="utf-8")

        # Prepare output path
        output_dir = Path(self._motion_output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_filename = f"{composition_id}.mp4"
        output_path = output_dir / output_filename

        # Render via npx remotion render (paths relative to project_dir cwd)
        abs_project_dir = project_dir.resolve()
        abs_output_path = output_path.resolve()
        cmd = [
            "npx",
            "remotion",
            "render",
            "src/index.ts",
            composition_id,
            str(abs_output_path),
        ]

        logger.info(
            "motion_render_started",
            composition_id=composition_id,
            command=" ".join(cmd),
        )

        start_time = time.monotonic()

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(abs_project_dir),
        )

        # Timeout: max 180 seconds for complex renders
        render_timeout = 180
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=render_timeout)
        except asyncio.TimeoutError:
            process.kill()
            raise TimeoutError(f"Remotion render timed out after {render_timeout}s")

        render_time = round(time.monotonic() - start_time, 1)

        if process.returncode != 0:
            error_text = stderr.decode("utf-8", errors="replace")[:2000]
            # Extract the most useful error line
            error_msg = error_text
            for line in error_text.split("\n"):
                if "Error:" in line or "ERROR" in line.upper():
                    error_msg = line.strip()
                    break
            raise RuntimeError(
                f"Remotion render failed (exit code {process.returncode}): {error_msg}"
            )

        if not abs_output_path.exists():
            raise RuntimeError(f"Render completed but output file not found: {abs_output_path}")

        logger.info(
            "motion_render_completed",
            composition_id=composition_id,
            render_time_seconds=render_time,
            output_size_kb=round(abs_output_path.stat().st_size / 1024, 1),
        )

        return {
            "output_path": str(abs_output_path),
            "render_time_seconds": render_time,
        }
