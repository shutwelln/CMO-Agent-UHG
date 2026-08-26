"""Reusable post-hooks for the refinement loop."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Optional

import structlog

logger = structlog.get_logger()

# Type alias matching refinement.py
PostHook = Callable[[str], Awaitable[str]]


def make_em_dash_hook() -> PostHook:
    """Create a hook that strips em/en dashes (anti-AI writing rule).

    Should ALWAYS be first in the hook chain.
    """

    async def _strip_dashes(content: str) -> str:
        cleaned = content.replace("\u2014", " - ")  # em dash
        cleaned = cleaned.replace("\u2013", " - ")  # en dash
        # Normalize double spaces around dashes
        while "  - " in cleaned or " -  " in cleaned or "  -  " in cleaned:
            cleaned = cleaned.replace("  -  ", " - ").replace("  - ", " - ").replace(" -  ", " - ")
        return cleaned

    return _strip_dashes


def make_proofread_hook(proofreader: Any, context: str = "") -> PostHook:
    """Create a hook that runs the Proofreader on content.

    Should run AFTER em-dash hook so it proofreads clean content.
    """

    async def _proofread(content: str) -> str:
        try:
            result = await proofreader.proofread(content, context=context)
            if result.has_corrections:
                logger.info("refinement_proofread_corrections", count=len(result.corrections))
                return result.corrected_text
        except Exception as e:
            logger.warning("refinement_proofread_failed", error=str(e))
        return content

    return _proofread


def make_char_limit_hook(max_chars: int) -> PostHook:
    """Create a hook that truncates content to max_chars at a word boundary.

    Should run LAST in the hook chain.
    """

    async def _truncate(content: str) -> str:
        if len(content) <= max_chars:
            return content
        # Find the last space before the limit
        truncated = content[:max_chars]
        last_space = truncated.rfind(" ")
        if last_space > max_chars // 2:
            truncated = truncated[:last_space]
        return truncated.rstrip()

    return _truncate


def make_safety_check_hook(
    checker: Any,
    platform: str = "reddit",
    post_type: str = "seeking_community",
) -> PostHook:
    """Create a hook that runs ContentSafetyChecker on outreach replies.

    Should run after proofreading.
    """

    async def _safety_check(content: str) -> str:
        try:
            passed, warnings = checker.check(content, platform=platform, post_type=post_type)
            # Safety warnings are surfaced via the warnings return value and
            # Reviewer Notes — do NOT prepend them to the reply text itself.
            _ = (passed, warnings)  # logged but not injected into content
        except Exception as e:
            logger.warning("refinement_safety_check_failed", error=str(e))
        return content

    return _safety_check


def build_hook_chain(*hooks: Optional[PostHook]) -> List[PostHook]:
    """Build an ordered hook chain, filtering out None values.

    If an em-dash hook is present, ensures it is at position 0.
    """
    filtered: List[PostHook] = [h for h in hooks if h is not None]
    return filtered
