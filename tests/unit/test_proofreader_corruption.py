"""Regression tests for proofreader corruption guard.

Verifies that the proofreader:
1. Detects corrupted output (raw JSON, fenced JSON) and keeps the original text
2. Correctly parses valid proofreader JSON responses
3. Handles truncated JSON responses gracefully
"""

from __future__ import annotations

import pytest

from cmo_agent.text.proofreader import (
    _is_corrupted_output,
    _parse_proofread_response,
)


# ── _is_corrupted_output ─────────────────────────────────────────────────────


class TestIsCorruptedOutput:
    def test_fenced_json(self):
        text = '```json\n{"corrected_text": "Hello world", "corrections": []}\n```'
        assert _is_corrupted_output(text) is True

    def test_fenced_no_lang(self):
        text = '```\n{"corrected_text": "Hello world"}\n```'
        assert _is_corrupted_output(text) is True

    def test_raw_json_with_corrected_text(self):
        text = '{"corrected_text": "Hello world", "corrections": []}'
        assert _is_corrupted_output(text) is True

    def test_raw_json_with_corrections(self):
        text = '{"corrections": [{"original": "teh", "corrected": "the"}], "corrected_text": "the"}'
        assert _is_corrupted_output(text) is True

    def test_clean_markdown(self):
        text = "## What Is Medicare?\n\nMedicare is the federal health insurance..."
        assert _is_corrupted_output(text) is False

    def test_clean_plain_text(self):
        text = "This is a normal article about saving money on insurance."
        assert _is_corrupted_output(text) is False

    def test_empty_string(self):
        assert _is_corrupted_output("") is False

    def test_whitespace(self):
        assert _is_corrupted_output("   ") is False

    def test_markdown_code_block_not_json(self):
        """Code blocks in articles that aren't proofreader output should pass."""
        text = "Here's an example:\n\n```python\nprint('hello')\n```\n\nThat's it."
        # This starts with normal text, not ``` — so it's fine
        assert _is_corrupted_output(text) is False

    def test_truncated_fenced_json(self):
        """Truncated fenced JSON (no closing ```) still detected."""
        text = '```json\n{"corrected_text": "## What Is Medicare?\\n\\nMedicare is'
        assert _is_corrupted_output(text) is True


# ── _parse_proofread_response ────────────────────────────────────────────────


class TestParseProofreadResponse:
    def test_valid_json(self):
        raw = '{"corrected_text": "Hello world", "corrections": []}'
        result = _parse_proofread_response(raw)
        assert result["corrected_text"] == "Hello world"
        assert result["corrections"] == []

    def test_fenced_json(self):
        raw = '```json\n{"corrected_text": "Fixed text", "corrections": [{"original": "teh", "corrected": "the", "reason": "spelling"}]}\n```'
        result = _parse_proofread_response(raw)
        assert result["corrected_text"] == "Fixed text"
        assert len(result["corrections"]) == 1

    def test_truncated_json_returns_raw(self):
        """Truncated JSON should return raw (which the corruption guard will catch)."""
        raw = '```json\n{"corrected_text": "## Medicare\\n\\nMedicare is the feder'
        result = _parse_proofread_response(raw)
        # The result will have the raw text as corrected_text (fallback)
        assert "corrected_text" in result

    def test_plain_text_fallback(self):
        """When the LLM returns plain text instead of JSON."""
        raw = "The corrected text is: Hello world."
        result = _parse_proofread_response(raw)
        assert result["corrected_text"] == raw


# ── Integration-style test ───────────────────────────────────────────────────


class TestCorruptionGuardIntegration:
    """Verify that the corruption guard + parser work together."""

    def test_long_article_truncation_scenario(self):
        """Simulate the exact bug: LLM returns truncated fenced JSON for body_md."""
        body_md = "## Understanding Dementia Care\n\n" + "Long article content. " * 200

        # Simulate what the LLM returns when max_tokens is too low
        truncated_response = (
            '```json\n{"corrected_text": "## Understanding Dementia Care\\n\\n'
            + "Long article content. " * 50
            # Truncated here — no closing quote, no closing brace, no closing fence
        )

        result = _parse_proofread_response(truncated_response)
        corrected = result.get("corrected_text", body_md)

        # The corruption guard should catch this
        assert _is_corrupted_output(corrected) is True

    def test_clean_output_passes_guard(self):
        """Normal proofreader output should pass the guard."""
        clean_response = '{"corrected_text": "## Medicare Explained\\n\\nMedicare is the federal health insurance program.", "corrections": [{"original": "helath", "corrected": "health", "reason": "spelling"}]}'

        result = _parse_proofread_response(clean_response)
        corrected = result["corrected_text"]

        # Clean markdown should NOT be flagged
        assert _is_corrupted_output(corrected) is False
        assert corrected.startswith("## Medicare Explained")
