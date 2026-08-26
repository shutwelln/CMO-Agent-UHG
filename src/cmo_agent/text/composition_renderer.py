"""Composition renderer — renders Remotion templates as static PNG or animated MP4."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any, Dict, Optional
from uuid import uuid4

import structlog

logger = structlog.get_logger()

# Templates registered in TemplateRoot.tsx
AVAILABLE_TEMPLATES = [
    "HeroOverlay",
    "TikTokOverlay",
    "LowerThird",
    "DataDashboard",
    "ProcessFlow",
    "EcosystemMap",
    "ComparisonGrid",
    "CalloutOverlay",
    "TimelineSequence",
    "QuoteCard",
    "StaticLayout",
]


class CompositionRenderer:
    """Renders compositions via Remotion templates — both static (still) and motion (video).

    Uses ``npx remotion still`` for single-frame PNG output and
    ``npx remotion render`` for animated MP4 output.  Both operate on
    the template entry point (``src/templateIndex.ts``), which is separate
    from the freeform motion graphics pipeline.
    """

    def __init__(
        self,
        remotion_project_dir: str = "./data/remotion",
        output_dir: str = "./data/compositions",
    ) -> None:
        self._project_dir = Path(remotion_project_dir).resolve()
        self._output_dir = Path(output_dir).resolve()
        self._output_dir.mkdir(parents=True, exist_ok=True)

    async def render_static(
        self,
        template_id: str,
        props: Dict[str, Any],
        output_format: str = "landscape",
        background_path: Optional[str] = None,
    ) -> str:
        """Render a template as a single-frame PNG via ``npx remotion still``.

        Args:
            template_id: Template name (e.g. "DataDashboard", "HeroOverlay").
            props: Structured props matching the template's interface.
            output_format: "landscape" (1920x1080), "square" (1080x1080), "portrait" (1080x1920).
            background_path: Optional path to a background image to include.

        Returns:
            Absolute path to the rendered PNG file.
        """
        self._validate_template(template_id)

        # Force static mode
        props = {**props, "mode": "static"}

        # Include background image path if provided
        if background_path:
            props["bgImage"] = background_path

        # Select composition ID based on format
        comp_id = self._resolve_composition_id(template_id, "static", output_format)

        # Write props to temp file
        render_id = uuid4().hex[:8]
        props_file = self._project_dir / f"props-{render_id}.json"
        output_file = self._output_dir / f"{template_id}-{render_id}.png"

        props_file.write_text(json.dumps(props, indent=2))

        try:
            result = await self._run_remotion(
                "still",
                comp_id,
                str(output_file),
                str(props_file),
            )

            if not output_file.exists():
                raise RuntimeError(
                    f"Remotion still did not produce output: {result.get('stderr', '')}"
                )

            logger.info(
                "composition_rendered_static",
                template=template_id,
                output=str(output_file),
            )
            return str(output_file)

        finally:
            # Clean up props file
            if props_file.exists():
                props_file.unlink()

    async def render_motion(
        self,
        template_id: str,
        props: Dict[str, Any],
        duration_seconds: int = 10,
        fps: int = 30,
        output_format: str = "landscape",
        background_video_path: Optional[str] = None,
    ) -> str:
        """Render a template as an animated MP4 via ``npx remotion render``.

        Args:
            template_id: Template name (e.g. "DataDashboard-Motion").
            props: Structured props matching the template's interface.
            duration_seconds: Video duration in seconds.
            fps: Frames per second.
            output_format: "landscape", "square", or "portrait".
            background_video_path: Optional path to a background video.

        Returns:
            Absolute path to the rendered MP4 file.
        """
        base_template = template_id.replace("-Motion", "")
        self._validate_template(base_template)

        # Force animated mode
        props = {**props, "mode": "animated"}

        # If a background video is provided, pass just the filename in props
        # and tell Remotion to serve the parent directory as public/ via
        # --public-dir so the template can resolve it with staticFile().
        public_dir_override: Optional[str] = None
        if background_video_path:
            bg_source = Path(background_video_path)
            if bg_source.exists():
                public_dir_override = str(bg_source.parent.resolve())
                props["bgVideo"] = bg_source.name  # filename only
            else:
                props["bgVideo"] = background_video_path

        # Use motion composition ID
        comp_id = self._resolve_composition_id(base_template, "animated", output_format)

        render_id = uuid4().hex[:8]
        props_file = self._project_dir / f"props-{render_id}.json"
        output_file = self._output_dir / f"{base_template}-{render_id}.mp4"

        props_file.write_text(json.dumps(props, indent=2))

        try:
            result = await self._run_remotion(
                "render",
                comp_id,
                str(output_file),
                str(props_file),
                public_dir=public_dir_override,
            )

            if not output_file.exists():
                raise RuntimeError(
                    f"Remotion render did not produce output: {result.get('stderr', '')}"
                )

            logger.info(
                "composition_rendered_motion",
                template=base_template,
                duration=duration_seconds,
                output=str(output_file),
            )
            return str(output_file)

        finally:
            if props_file.exists():
                props_file.unlink()

    def _validate_template(self, template_id: str) -> None:
        """Validate that the template exists."""
        if template_id not in AVAILABLE_TEMPLATES:
            raise ValueError(
                f"Unknown template '{template_id}'. Available: {', '.join(AVAILABLE_TEMPLATES)}"
            )

    def _resolve_composition_id(self, template_id: str, mode: str, output_format: str) -> str:
        """Resolve the Remotion composition ID from template + mode + format."""
        if output_format == "portrait":
            if mode == "animated":
                return f"{template_id}-Portrait-Motion"
            return f"{template_id}-Portrait"
        if mode == "animated":
            return f"{template_id}-Motion"
        if output_format == "square":
            return f"{template_id}-Square"
        return template_id

    async def _run_remotion(
        self,
        command: str,  # "still" or "render"
        composition_id: str,
        output_path: str,
        props_path: str,
        public_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a Remotion CLI command."""
        npx = shutil.which("npx")
        if not npx:
            raise RuntimeError("npx not found on PATH — Node.js is required")

        cmd = [
            npx,
            "remotion",
            command,
            "src/templateIndex.ts",
            composition_id,
            output_path,
            f"--props={props_path}",
            "--log=error",
        ]

        # Override public directory so Remotion can serve external assets
        if public_dir:
            cmd.append(f"--public-dir={public_dir}")

        logger.info(
            "remotion_command",
            command=command,
            composition=composition_id,
            cwd=str(self._project_dir),
        )

        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(self._project_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=300,  # 5 minute timeout
        )

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        if process.returncode != 0:
            logger.error(
                "remotion_command_failed",
                command=command,
                composition=composition_id,
                returncode=process.returncode,
                stderr=stderr_str[:2000],
            )
            raise RuntimeError(
                f"Remotion {command} failed (exit {process.returncode}): {stderr_str[:500]}"
            )

        return {"stdout": stdout_str, "stderr": stderr_str, "returncode": process.returncode}

    def list_templates(self) -> list:
        """Return the list of available template IDs."""
        return list(AVAILABLE_TEMPLATES)
