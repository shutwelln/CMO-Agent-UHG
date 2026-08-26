"""Pillow-based text overlay for crisp text on generated images."""

from __future__ import annotations

from io import BytesIO
from typing import Any, List, Optional, Tuple

import structlog

logger = structlog.get_logger()


class TextOverlayConfig:
    """Configuration for a single text overlay layer."""

    def __init__(
        self,
        text: str,
        position: str = "center",
        font_size: int = 56,
        font_color: str = "#FFFFFF",
        font_path: Optional[str] = None,
        stroke_color: Optional[str] = "#000000",
        stroke_width: int = 3,
        padding: int = 40,
        max_width_pct: float = 0.85,
        background_color: Optional[str] = None,
        background_opacity: int = 128,
        line_spacing: int = 8,
    ) -> None:
        self.text = text
        self.position = position
        self.font_size = font_size
        self.font_color = font_color
        self.font_path = font_path
        self.stroke_color = stroke_color
        self.stroke_width = stroke_width
        self.padding = padding
        self.max_width_pct = max_width_pct
        self.background_color = background_color
        self.background_opacity = background_opacity
        self.line_spacing = line_spacing


class TextOverlay:
    """Renders crisp text onto images using Pillow/PIL."""

    def __init__(self, default_font_path: str = "") -> None:
        self._default_font_path = default_font_path

    def render(
        self,
        image_bytes: bytes,
        overlays: List[TextOverlayConfig],
        output_format: str = "PNG",
    ) -> bytes:
        """Render text overlays onto an image.

        Args:
            image_bytes: The source image as bytes.
            overlays: List of TextOverlayConfig for each text layer.
            output_format: Output image format (PNG, JPEG, WEBP).

        Returns:
            The composited image as bytes.
        """
        from PIL import Image, ImageDraw, ImageFont

        img = Image.open(BytesIO(image_bytes)).convert("RGBA")
        img_width, img_height = img.size

        overlay_layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay_layer)

        for config in overlays:
            font_path = config.font_path or self._default_font_path
            try:
                font = ImageFont.truetype(font_path, config.font_size)
            except (IOError, OSError):
                logger.warning("font_load_failed_using_default", path=font_path)
                font = ImageFont.load_default()

            max_text_width = int(img_width * config.max_width_pct)
            wrapped_lines = _wrap_text(config.text, font, max_text_width, draw)

            line_heights: List[int] = []
            line_widths: List[int] = []
            for line in wrapped_lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_widths.append(bbox[2] - bbox[0])
                line_heights.append(bbox[3] - bbox[1])

            total_height = sum(line_heights) + config.line_spacing * max(len(wrapped_lines) - 1, 0)
            max_line_width = max(line_widths) if line_widths else 0

            x, y = _calculate_position(
                config.position,
                img_width,
                img_height,
                max_line_width,
                total_height,
                config.padding,
            )

            if config.background_color:
                bg_color = _hex_to_rgba(config.background_color, config.background_opacity)
                bg_rect = (
                    x - config.padding // 2,
                    y - config.padding // 2,
                    x + max_line_width + config.padding // 2,
                    y + total_height + config.padding // 2,
                )
                draw.rectangle(bg_rect, fill=bg_color)

            current_y = y
            text_color = _hex_to_rgba(config.font_color, 255)
            stroke_color = _hex_to_rgba(config.stroke_color, 255) if config.stroke_color else None

            for i, line in enumerate(wrapped_lines):
                line_bbox = draw.textbbox((0, 0), line, font=font)
                line_width = line_bbox[2] - line_bbox[0]
                line_x = x + (max_line_width - line_width) // 2

                draw.text(
                    (line_x, current_y),
                    line,
                    font=font,
                    fill=text_color,
                    stroke_width=config.stroke_width if stroke_color else 0,
                    stroke_fill=stroke_color,
                )
                current_y += line_heights[i] + config.line_spacing

        result = Image.alpha_composite(img, overlay_layer)

        output = BytesIO()
        if output_format.upper() in ("JPEG", "JPG"):
            result = result.convert("RGB")
        result.save(output, format=output_format.upper())
        return output.getvalue()


# ══════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════


def _wrap_text(text: str, font: Any, max_width: int, draw: Any) -> List[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: List[str] = []
    current_line: List[str] = []

    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))

    return lines or [text]


def _calculate_position(
    position: str,
    img_width: int,
    img_height: int,
    text_width: int,
    text_height: int,
    padding: int,
) -> Tuple[int, int]:
    """Calculate x, y coordinates for the text block."""
    cx = (img_width - text_width) // 2
    cy = (img_height - text_height) // 2

    positions = {
        "center": (cx, cy),
        "top": (cx, padding),
        "bottom": (cx, img_height - text_height - padding),
        "top-left": (padding, padding),
        "top-right": (img_width - text_width - padding, padding),
        "bottom-left": (padding, img_height - text_height - padding),
        "bottom-right": (img_width - text_width - padding, img_height - text_height - padding),
    }
    return positions.get(position, (cx, cy))


def _hex_to_rgba(hex_color: str, alpha: int = 255) -> Tuple[int, int, int, int]:
    """Convert hex color string to RGBA tuple."""
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 6:
        r = int(hex_color[0:2], 16)
        g = int(hex_color[2:4], 16)
        b = int(hex_color[4:6], 16)
        return (r, g, b, alpha)
    return (255, 255, 255, alpha)
