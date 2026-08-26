"""Tests for Google Docs formatting helpers in docs.py."""

from __future__ import annotations

from cmo_agent.agents.docs import (
    _normalize_sections,
    _parse_doc_structure,
    _parse_inline_formatting,
)

# ── _parse_inline_formatting ─────────────────────────────────────────────


class TestParseInlineFormatting:
    def test_no_formatting(self):
        plain, runs = _parse_inline_formatting("Hello world")
        assert plain == "Hello world"
        assert runs == []

    def test_bold(self):
        plain, runs = _parse_inline_formatting("Use **bold** text")
        assert plain == "Use bold text"
        assert len(runs) == 1
        start, end, style = runs[0]
        assert style == "bold"
        assert plain[start:end] == "bold"

    def test_italic(self):
        plain, runs = _parse_inline_formatting("Use *italic* text")
        assert plain == "Use italic text"
        assert len(runs) == 1
        start, end, style = runs[0]
        assert style == "italic"
        assert plain[start:end] == "italic"

    def test_mixed_bold_and_italic(self):
        plain, runs = _parse_inline_formatting("A **bold** and *italic* mix")
        assert plain == "A bold and italic mix"
        assert len(runs) == 2
        assert runs[0][2] == "bold"
        assert runs[1][2] == "italic"

    def test_unclosed_bold_treated_as_literal(self):
        plain, runs = _parse_inline_formatting("Unclosed **bold text")
        # ** without closing should remain literal
        assert "**" in plain
        assert runs == []

    def test_unclosed_italic_treated_as_literal(self):
        plain, runs = _parse_inline_formatting("Unclosed *italic text")
        assert "*" in plain
        assert runs == []

    def test_empty_string(self):
        plain, runs = _parse_inline_formatting("")
        assert plain == ""
        assert runs == []

    def test_adjacent_markers(self):
        plain, runs = _parse_inline_formatting("**A** **B**")
        assert plain == "A B"
        assert len(runs) == 2


# ── _normalize_sections ──────────────────────────────────────────────────


class TestNormalizeSections:
    def test_old_body_format(self):
        structure = {
            "title": "Doc",
            "sections": [{"heading": "Intro", "body": "Some text", "level": 1}],
        }
        result = _normalize_sections(structure)
        assert len(result) == 1
        assert "content" in result[0]
        assert result[0]["content"][0]["type"] == "paragraph"
        assert result[0]["content"][0]["text"] == "Some text"
        # Original body key should be removed
        assert "body" not in result[0]

    def test_new_content_format_untouched(self):
        structure = {
            "title": "Doc",
            "sections": [
                {
                    "heading": "Intro",
                    "level": 1,
                    "content": [
                        {"type": "paragraph", "text": "Hello"},
                        {"type": "bullets", "items": ["A", "B"]},
                    ],
                }
            ],
        }
        result = _normalize_sections(structure)
        assert len(result[0]["content"]) == 2
        assert result[0]["content"][0]["type"] == "paragraph"
        assert result[0]["content"][1]["type"] == "bullets"

    def test_empty_body(self):
        structure = {
            "title": "Doc",
            "sections": [{"heading": "Empty", "body": "", "level": 1}],
        }
        result = _normalize_sections(structure)
        assert result[0]["content"] == []

    def test_no_body_or_content(self):
        structure = {
            "title": "Doc",
            "sections": [{"heading": "Bare", "level": 1}],
        }
        result = _normalize_sections(structure)
        assert result[0]["content"] == []


# ── _parse_doc_structure ─────────────────────────────────────────────────


class TestParseDocStructure:
    def test_valid_json(self):
        raw = '{"title": "Test", "sections": [{"heading": "H", "body": "B", "level": 1}]}'
        result = _parse_doc_structure(raw)
        assert result["title"] == "Test"

    def test_json_in_code_block(self):
        raw = '```json\n{"title": "CB", "sections": []}\n```'
        result = _parse_doc_structure(raw)
        assert result["title"] == "CB"

    def test_json_with_prefix_text(self):
        raw = 'Here is the document structure:\n{"title": "Prefixed", "sections": []}'
        result = _parse_doc_structure(raw)
        assert result["title"] == "Prefixed"

    def test_fallback_skips_json_fragments(self):
        raw = '{\n  "title": "Broken\n}\nActual Title\nSome body text'
        result = _parse_doc_structure(raw)
        # The fallback should use "Actual Title" not "{"
        title = result.get("title", "")
        assert "{" not in title
        assert "}" not in title

    def test_fallback_plain_text(self):
        raw = "My Document Title\nFirst paragraph content\nSecond paragraph"
        result = _parse_doc_structure(raw)
        assert result["title"] == "My Document Title"
        assert len(result["sections"]) >= 1
