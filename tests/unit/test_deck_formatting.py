"""Tests for Google Slides coordinate bounds in deck.py.

Verifies that all _gs_build_* textbox/image elements stay within
the 10" x 5.625" Google Slides canvas.
"""

from __future__ import annotations

from cmo_agent.agents.deck import (
    _EMU_INCH,
    _GS_H,
    _GS_W,
    _gs_build_content,
    _gs_build_cta,
    _gs_build_image,
    _gs_build_quote,
    _gs_build_section,
    _gs_build_stats,
    _gs_build_title,
    _gs_build_two_column,
)

# Page bounds in EMU
_MAX_X = _GS_W * _EMU_INCH
_MAX_Y = _GS_H * _EMU_INCH

# Shared dummy palette (float colors)
_PAL = {
    "primary": {"red": 0.1, "green": 0.4, "blue": 0.9},
    "secondary": {"red": 0.2, "green": 0.7, "blue": 0.3},
    "accent": {"red": 1.0, "green": 0.7, "blue": 0.0},
    "dark": {"red": 0.1, "green": 0.1, "blue": 0.2},
    "light": {"red": 0.97, "green": 0.97, "blue": 0.98},
    "text": {"red": 0.2, "green": 0.2, "blue": 0.2},
    "text_light": {"red": 1.0, "green": 1.0, "blue": 1.0},
    "muted": {"red": 0.42, "green": 0.46, "blue": 0.49},
}


def _extract_boxes(reqs: list) -> list:
    """Extract (left, top, width, height) tuples from createShape/createImage requests."""
    boxes = []
    for req in reqs:
        if "createShape" in req:
            props = req["createShape"]["elementProperties"]
            w = props["size"]["width"]["magnitude"]
            h = props["size"]["height"]["magnitude"]
            tx = props["transform"]["translateX"]
            ty = props["transform"]["translateY"]
            boxes.append((tx, ty, w, h))
        elif "createImage" in req:
            props = req["createImage"]["elementProperties"]
            w = props["size"]["width"]["magnitude"]
            h = props["size"]["height"]["magnitude"]
            tx = props["transform"]["translateX"]
            ty = props["transform"]["translateY"]
            boxes.append((tx, ty, w, h))
    return boxes


def _assert_in_bounds(boxes: list, label: str = "") -> None:
    for i, (left, top, width, height) in enumerate(boxes):
        right = left + width
        bottom = top + height
        prefix = f"{label} box[{i}]" if label else f"box[{i}]"
        assert right <= _MAX_X + 1, f"{prefix} right edge {right} exceeds page width {_MAX_X}"
        assert bottom <= _MAX_Y + 1, f"{prefix} bottom edge {bottom} exceeds page height {_MAX_Y}"
        assert left >= 0, f"{prefix} left {left} is negative"
        assert top >= 0, f"{prefix} top {top} is negative"


def test_title_slide_bounds():
    reqs = _gs_build_title("s1", {"title": "Hello", "subtitle": "World"}, _PAL, 0)
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 1
    _assert_in_bounds(boxes, "title")


def test_section_slide_bounds():
    reqs = _gs_build_section("s2", {"title": "Section", "subtitle": "Sub"}, _PAL, 1)
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 1
    _assert_in_bounds(boxes, "section")


def test_content_slide_bounds():
    reqs = _gs_build_content("s3", {"title": "Content", "bullets": ["A", "B", "C"]}, _PAL, 2)
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 2
    _assert_in_bounds(boxes, "content")


def test_two_column_slide_bounds():
    reqs = _gs_build_two_column(
        "s4",
        {
            "title": "Compare",
            "left_title": "Left",
            "left_column": ["A", "B"],
            "right_title": "Right",
            "right_column": ["C", "D"],
        },
        _PAL,
        3,
    )
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 3  # title + left + right
    _assert_in_bounds(boxes, "two_column")


def test_stats_slide_bounds():
    reqs = _gs_build_stats(
        "s5",
        {
            "title": "Metrics",
            "stats": [
                {"value": "85%", "label": "Growth"},
                {"value": "$1M", "label": "Revenue"},
                {"value": "500K", "label": "Users"},
            ],
        },
        _PAL,
        4,
    )
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 4  # title + 3 stats
    _assert_in_bounds(boxes, "stats")


def test_stats_slide_bounds_many_stats():
    """Even with 5 stats, all boxes should fit within page bounds."""
    reqs = _gs_build_stats(
        "s5b",
        {
            "title": "Many Metrics",
            "stats": [{"value": str(i), "label": f"Metric {i}"} for i in range(5)],
        },
        _PAL,
        4,
    )
    boxes = _extract_boxes(reqs)
    _assert_in_bounds(boxes, "stats_many")


def test_quote_slide_bounds():
    reqs = _gs_build_quote("s6", {"quote": "Something profound.", "attribution": "Author"}, _PAL, 5)
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 1
    _assert_in_bounds(boxes, "quote")


def test_image_slide_bounds_with_url():
    reqs = _gs_build_image(
        "s7",
        {"title": "Photo", "image_url": "https://example.com/img.png", "caption": "Cap"},
        _PAL,
        6,
    )
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 2  # title + image
    _assert_in_bounds(boxes, "image_url")


def test_image_slide_bounds_placeholder():
    reqs = _gs_build_image("s7b", {"title": "Photo", "caption": "Cap"}, _PAL, 6)
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 2  # title + placeholder
    _assert_in_bounds(boxes, "image_placeholder")


def test_cta_slide_bounds():
    reqs = _gs_build_cta("s8", {"title": "Get Started", "subtitle": "contact@example.com"}, _PAL, 7)
    boxes = _extract_boxes(reqs)
    assert len(boxes) >= 1
    _assert_in_bounds(boxes, "cta")


def test_alignment_requests_present_in_title():
    """Title slide should include alignment requests for centering."""
    reqs = _gs_build_title("s_align", {"title": "Hello"}, _PAL, 0)
    alignment_reqs = [
        r for r in reqs if "updateParagraphStyle" in r or "updateShapeProperties" in r
    ]
    assert len(alignment_reqs) >= 1, "Expected alignment requests in title slide"


def test_no_background_color_in_any_builder():
    """No _gs_build_* function should emit updatePageProperties (background color)."""
    builders_and_data = [
        (_gs_build_title, {"title": "T", "subtitle": "S"}),
        (_gs_build_section, {"title": "Sec"}),
        (_gs_build_content, {"title": "C", "bullets": ["A"]}),
        (_gs_build_two_column, {"title": "TC", "left_column": ["L"], "right_column": ["R"]}),
        (_gs_build_stats, {"title": "Stats", "stats": [{"value": "1", "label": "X"}]}),
        (_gs_build_quote, {"quote": "Q", "attribution": "A"}),
        (_gs_build_image, {"title": "Img", "caption": "C"}),
        (_gs_build_cta, {"title": "CTA", "subtitle": "D"}),
    ]
    for builder, data in builders_and_data:
        reqs = builder("slide_bg_test", data, _PAL, 0)
        bg_reqs = [r for r in reqs if "updatePageProperties" in r]
        assert bg_reqs == [], f"{builder.__name__} should not set background color"
