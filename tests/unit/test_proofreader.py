"""Tests for the LLM-powered proofreader."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from cmo_agent.text.proofreader import Proofreader, ProofreadResult, _parse_proofread_response


# ── Fake LLM for testing ─────────────────────────────────────────────────


class _FakeLLMResponse:
    def __init__(self, content: str) -> None:
        self.content = content


class _FakeLLM:
    """Minimal LLM stub that returns a canned response."""

    def __init__(self, response_content: str = "") -> None:
        self._response = response_content

    async def complete(self, **kwargs: Any) -> _FakeLLMResponse:
        return _FakeLLMResponse(self._response)


# ── ProofreadResult tests ────────────────────────────────────────────────


class TestProofreadResult:
    def test_has_corrections_true(self) -> None:
        pr = ProofreadResult(
            corrected_text="hello",
            corrections=[{"original": "helo", "corrected": "hello", "reason": "spelling"}],
        )
        assert pr.has_corrections is True

    def test_has_corrections_false(self) -> None:
        pr = ProofreadResult(corrected_text="hello", corrections=[])
        assert pr.has_corrections is False


# ── Proofreader tests ────────────────────────────────────────────────────


class TestProofreader:
    @pytest.mark.asyncio
    async def test_proofread_returns_corrected_text(self) -> None:
        response = json.dumps(
            {
                "corrected_text": "The quick brown fox.",
                "corrections": [{"original": "quik", "corrected": "quick", "reason": "spelling"}],
            }
        )
        llm = _FakeLLM(response_content=response)
        proofreader = Proofreader(llm=llm)

        result = await proofreader.proofread("The quik brown fox.")
        assert result.corrected_text == "The quick brown fox."
        assert len(result.corrections) == 1
        assert result.corrections[0]["original"] == "quik"

    @pytest.mark.asyncio
    async def test_proofread_no_corrections(self) -> None:
        response = json.dumps({"corrected_text": "Perfect text.", "corrections": []})
        llm = _FakeLLM(response_content=response)
        proofreader = Proofreader(llm=llm)

        result = await proofreader.proofread("Perfect text.")
        assert result.corrected_text == "Perfect text."
        assert result.has_corrections is False

    @pytest.mark.asyncio
    async def test_proofread_empty_text(self) -> None:
        llm = _FakeLLM()
        proofreader = Proofreader(llm=llm)

        result = await proofreader.proofread("")
        assert result.corrected_text == ""
        assert result.corrections == []

    @pytest.mark.asyncio
    async def test_proofread_whitespace_only(self) -> None:
        llm = _FakeLLM()
        proofreader = Proofreader(llm=llm)

        result = await proofreader.proofread("   ")
        assert result.corrected_text == "   "
        assert result.corrections == []

    @pytest.mark.asyncio
    async def test_proofread_llm_failure_returns_original(self) -> None:
        """If the LLM raises an exception, the original text is returned."""
        llm = _FakeLLM()
        llm.complete = AsyncMock(side_effect=RuntimeError("LLM is down"))
        proofreader = Proofreader(llm=llm)

        result = await proofreader.proofread("some text")
        assert result.corrected_text == "some text"
        assert result.corrections == []

    @pytest.mark.asyncio
    async def test_proofread_dict_fields_basic(self) -> None:
        response = json.dumps(
            {
                "corrected_text": "Fixed title",
                "corrections": [
                    {"original": "Titl", "corrected": "Fixed title", "reason": "spelling"}
                ],
            }
        )
        llm = _FakeLLM(response_content=response)
        proofreader = Proofreader(llm=llm)

        data = {
            "title": "Titl",
            "number": 42,
            "sections": [{"heading": "Headin", "body": "some body"}],
        }
        corrected, corrections = await proofreader.proofread_dict_fields(
            data, fields=["title", "heading", "body"]
        )
        # Title should be corrected
        assert corrected["title"] == "Fixed title"
        # Number should be unchanged
        assert corrected["number"] == 42
        # Nested fields should also be proofread
        assert corrected["sections"][0]["heading"] == "Fixed title"
        assert corrected["sections"][0]["body"] == "Fixed title"

    @pytest.mark.asyncio
    async def test_proofread_dict_fields_with_list_of_strings(self) -> None:
        response = json.dumps({"corrected_text": "corrected", "corrections": []})
        llm = _FakeLLM(response_content=response)
        proofreader = Proofreader(llm=llm)

        data = {"bullets": ["first item", "second item"]}
        corrected, _ = await proofreader.proofread_dict_fields(data, fields=["bullets"])
        assert corrected["bullets"] == ["corrected", "corrected"]


# ── _parse_proofread_response tests ──────────────────────────────────────


class TestParseProofreadResponse:
    def test_parse_valid_json(self) -> None:
        raw = json.dumps({"corrected_text": "hello", "corrections": []})
        result = _parse_proofread_response(raw)
        assert result["corrected_text"] == "hello"

    def test_parse_json_in_code_block(self) -> None:
        raw = '```json\n{"corrected_text": "world", "corrections": []}\n```'
        result = _parse_proofread_response(raw)
        assert result["corrected_text"] == "world"

    def test_parse_fallback_returns_raw(self) -> None:
        raw = "This is not JSON at all."
        result = _parse_proofread_response(raw)
        assert result["corrected_text"] == raw
        assert result["corrections"] == []
