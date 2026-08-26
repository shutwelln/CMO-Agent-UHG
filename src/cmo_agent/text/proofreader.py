"""LLM-powered proofreader for correcting spelling, grammar, and punctuation."""

from __future__ import annotations

import json
import re as _re
from typing import Any, Dict, List, Optional

import structlog

from ..llm.base import BaseLLM, Message

logger = structlog.get_logger()


class ProofreadResult:
    """Result from a proofreading pass."""

    def __init__(self, corrected_text: str, corrections: List[Dict[str, str]]) -> None:
        self.corrected_text = corrected_text
        self.corrections = corrections

    @property
    def has_corrections(self) -> bool:
        return len(self.corrections) > 0


class Proofreader:
    """Shared proofreading utility using a fast scanning LLM.

    Corrects spelling, grammar, and punctuation while preserving:
    - Brand names and trademarks
    - Marketing jargon and intentional stylistic choices
    - [VERIFY] flags and markdown formatting
    - Hashtags, @mentions, URLs
    """

    def __init__(self, llm: BaseLLM) -> None:
        self._llm = llm

    async def proofread(
        self,
        text: str,
        preserve_terms: Optional[List[str]] = None,
        context: str = "",
    ) -> ProofreadResult:
        """Proofread text and return corrected version with list of changes.

        Args:
            text: The text to proofread.
            preserve_terms: Brand names or terms that must not be altered.
            context: Optional context (e.g., "social media post", "newsletter").

        Returns:
            ProofreadResult with corrected text and corrections list.
        """
        if not text or not text.strip():
            return ProofreadResult(corrected_text=text, corrections=[])

        preserve_section = ""
        if preserve_terms:
            terms_str = ", ".join(preserve_terms)
            preserve_section = (
                f"\nPRESERVE THESE TERMS EXACTLY (do not alter spelling or casing): {terms_str}"
            )

        context_section = ""
        if context:
            context_section = f"\nCONTENT TYPE: {context}"

        prompt = f"""Proofread the following text. Fix ONLY:
- Spelling errors
- Grammar mistakes
- Punctuation errors
- Obvious typos

DO NOT change:
- Brand names, product names, or company names
- Marketing jargon or industry terminology
- Intentional stylistic choices (sentence fragments for emphasis, etc.)
- [VERIFY] flags or markdown formatting
- Hashtags, @mentions, or URLs
- The overall tone, voice, or meaning{preserve_section}{context_section}

TEXT TO PROOFREAD:
{text}

Return a JSON object:
{{"corrected_text": "the full corrected text", "corrections": [{{"original": "misspelled word", "corrected": "correct version", "reason": "spelling/grammar/punctuation"}}]}}

If no corrections are needed, return the original text with an empty corrections array.
Return ONLY the JSON object, nothing else."""

        try:
            response = await self._llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.1,
            )

            result = _parse_proofread_response(response.content)
            corrected = result.get("corrected_text", text)
            # Guard: if the "corrected" text looks like raw JSON or fenced
            # JSON, the LLM response was truncated or mis-parsed — keep the
            # original text to avoid corrupting the field.
            if _is_corrupted_output(corrected):
                logger.warning(
                    "proofreader_corruption_guard",
                    preview=corrected[:120],
                )
                return ProofreadResult(corrected_text=text, corrections=[])
            return ProofreadResult(
                corrected_text=corrected,
                corrections=result.get("corrections", []),
            )
        except Exception as e:
            logger.warning("proofreader_error", error=str(e))
            return ProofreadResult(corrected_text=text, corrections=[])

    async def proofread_dict_fields(
        self,
        data: Dict[str, Any],
        fields: List[str],
        preserve_terms: Optional[List[str]] = None,
    ) -> tuple:
        """Proofread specific string fields in a dictionary.

        Recursively walks nested dicts and lists, proofreading any string
        values found at the specified field names.

        Args:
            data: The dictionary to proofread.
            fields: Field names to proofread (e.g., ["title", "bullets"]).
            preserve_terms: Brand terms to preserve.

        Returns:
            Tuple of (corrected dict, all corrections).
        """
        all_corrections: List[Dict[str, str]] = []
        corrected = await self._proofread_recursive(data, fields, preserve_terms, all_corrections)
        return corrected, all_corrections

    async def _proofread_recursive(
        self,
        obj: Any,
        fields: List[str],
        preserve_terms: Optional[List[str]],
        corrections: List[Dict[str, str]],
    ) -> Any:
        if isinstance(obj, dict):
            result: Dict[str, Any] = {}
            for key, value in obj.items():
                if key in fields and isinstance(value, str) and value.strip():
                    pr = await self.proofread(value, preserve_terms)
                    result[key] = pr.corrected_text
                    corrections.extend(pr.corrections)
                elif key in fields and isinstance(value, list):
                    new_list = []
                    for item in value:
                        if isinstance(item, str) and item.strip():
                            pr = await self.proofread(item, preserve_terms)
                            new_list.append(pr.corrected_text)
                            corrections.extend(pr.corrections)
                        else:
                            new_list.append(
                                await self._proofread_recursive(
                                    item, fields, preserve_terms, corrections
                                )
                            )
                    result[key] = new_list
                else:
                    result[key] = await self._proofread_recursive(
                        value, fields, preserve_terms, corrections
                    )
            return result
        elif isinstance(obj, list):
            return [
                await self._proofread_recursive(item, fields, preserve_terms, corrections)
                for item in obj
            ]
        return obj


def _is_corrupted_output(text: str) -> bool:
    """Detect if proofreader output contains raw JSON instead of clean text."""
    stripped = text.strip()
    if stripped.startswith("```"):
        return True
    if stripped.startswith("{") and '"corrected_text"' in stripped[:200]:
        return True
    if '"corrections"' in stripped[:200] and stripped.startswith("{"):
        return True
    return False


def _parse_proofread_response(raw: str) -> Dict[str, Any]:
    """Parse the LLM proofreading response as JSON."""

    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        pass

    match = _re.search(r"```(?:json)?\s*\n?(.*?)\n?```", raw, _re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except (json.JSONDecodeError, TypeError):
            pass

    # Last resort: try to extract corrected_text from a truncated JSON response
    ct_match = _re.search(r'"corrected_text"\s*:\s*"(.*)', raw, _re.DOTALL)
    if ct_match:
        # The response was truncated mid-JSON — don't use it
        logger.warning("proofreader_truncated_json", raw_length=len(raw))
        return {"corrected_text": raw, "corrections": []}

    logger.warning("proofreader_parse_fallback", raw_length=len(raw))
    return {"corrected_text": raw, "corrections": []}
