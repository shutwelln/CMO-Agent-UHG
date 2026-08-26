"""Tests for the Pillow-based text overlay."""

from __future__ import annotations

import pytest

from cmo_agent.text.overlay import (
    TextOverlay,
    TextOverlayConfig,
    _calculate_position,
    _hex_to_rgba,
    _wrap_text,
)


# ── TextOverlayConfig tests ──────────────────────────────────────────────


class TestTextOverlayConfig:
    def test_defaults(self) -> None:
        cfg = TextOverlayConfig(text="Hello")
        assert cfg.text == "Hello"
        assert cfg.position == "center"
        assert cfg.font_size == 56
        assert cfg.font_color == "#FFFFFF"
        assert cfg.stroke_width == 3
        assert cfg.background_color is None

    def test_custom_values(self) -> None:
        cfg = TextOverlayConfig(
            text="Test",
            position="bottom",
            font_size=24,
            font_color="#FF0000",
            background_color="#000000",
            background_opacity=200,
        )
        assert cfg.position == "bottom"
        assert cfg.font_size == 24
        assert cfg.background_opacity == 200


# ── Helper function tests ────────────────────────────────────────────────


class TestHexToRgba:
    def test_basic_hex(self) -> None:
        assert _hex_to_rgba("#FF0000") == (255, 0, 0, 255)

    def test_hex_without_hash(self) -> None:
        assert _hex_to_rgba("00FF00") == (0, 255, 0, 255)

    def test_custom_alpha(self) -> None:
        assert _hex_to_rgba("#0000FF", alpha=128) == (0, 0, 255, 128)

    def test_invalid_hex_returns_white(self) -> None:
        assert _hex_to_rgba("#ZZ") == (255, 255, 255, 255)

    def test_short_hex(self) -> None:
        # Non-6-char hex should fallback to white
        assert _hex_to_rgba("#FFF") == (255, 255, 255, 255)


class TestCalculatePosition:
    def test_center(self) -> None:
        x, y = _calculate_position("center", 1000, 1000, 200, 100, 40)
        assert x == 400  # (1000-200)//2
        assert y == 450  # (1000-100)//2

    def test_top(self) -> None:
        x, y = _calculate_position("top", 1000, 1000, 200, 100, 40)
        assert x == 400
        assert y == 40  # padding

    def test_bottom(self) -> None:
        x, y = _calculate_position("bottom", 1000, 1000, 200, 100, 40)
        assert x == 400
        assert y == 860  # 1000 - 100 - 40

    def test_top_left(self) -> None:
        x, y = _calculate_position("top-left", 1000, 1000, 200, 100, 40)
        assert x == 40
        assert y == 40

    def test_bottom_right(self) -> None:
        x, y = _calculate_position("bottom-right", 1000, 1000, 200, 100, 40)
        assert x == 760  # 1000 - 200 - 40
        assert y == 860  # 1000 - 100 - 40

    def test_unknown_position_defaults_to_center(self) -> None:
        x, y = _calculate_position("unknown", 1000, 1000, 200, 100, 40)
        assert x == 400
        assert y == 450


# ── TextOverlay render test ──────────────────────────────────────────────


class TestTextOverlayRender:
    def test_render_produces_bytes(self) -> None:
        """Render text onto a small test image and verify output is valid PNG bytes."""
        from PIL import Image
        from io import BytesIO

        # Create a small test image
        img = Image.new("RGB", (200, 200), color=(100, 100, 100))
        buf = BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        overlay = TextOverlay()
        config = TextOverlayConfig(text="Test", font_size=20, position="center")
        result = overlay.render(image_bytes, [config])

        assert isinstance(result, bytes)
        assert len(result) > 0
        # Verify it's a valid PNG (starts with PNG magic bytes)
        assert result[:4] == b"\x89PNG"

    def test_render_with_background(self) -> None:
        """Render text with a background bar."""
        from PIL import Image
        from io import BytesIO

        img = Image.new("RGB", (200, 200), color=(50, 50, 50))
        buf = BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        overlay = TextOverlay()
        config = TextOverlayConfig(
            text="With BG",
            font_size=16,
            position="bottom",
            background_color="#000000",
            background_opacity=160,
        )
        result = overlay.render(image_bytes, [config])

        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_render_jpeg_output(self) -> None:
        """Render as JPEG output format."""
        from PIL import Image
        from io import BytesIO

        img = Image.new("RGB", (200, 200), color=(200, 200, 200))
        buf = BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        overlay = TextOverlay()
        config = TextOverlayConfig(text="JPEG", font_size=16)
        result = overlay.render(image_bytes, [config], output_format="JPEG")

        assert isinstance(result, bytes)
        assert len(result) > 0
        # JPEG magic bytes
        assert result[:2] == b"\xff\xd8"

    def test_render_multiple_overlays(self) -> None:
        """Render multiple text overlays on the same image."""
        from PIL import Image
        from io import BytesIO

        img = Image.new("RGB", (400, 400), color=(0, 0, 0))
        buf = BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()

        overlay = TextOverlay()
        configs = [
            TextOverlayConfig(text="Top", font_size=16, position="top"),
            TextOverlayConfig(text="Bottom", font_size=16, position="bottom"),
        ]
        result = overlay.render(image_bytes, configs)
        assert isinstance(result, bytes)
        assert len(result) > 0
