"""Memory sanitizer — redacts secrets and PII before storage."""

from __future__ import annotations

import re
from typing import List, Tuple

# Patterns: (compiled regex, replacement label)
_PATTERNS: List[Tuple[re.Pattern[str], str]] = [
    # Anthropic / OpenAI / generic sk- keys
    (re.compile(r"sk-[A-Za-z0-9_\-]{20,}"), "[REDACTED_API_KEY]"),
    # Slack bot/app tokens
    (re.compile(r"xoxb-[A-Za-z0-9\-]{20,}"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"xoxp-[A-Za-z0-9\-]{20,}"), "[REDACTED_SLACK_TOKEN]"),
    (re.compile(r"xapp-[A-Za-z0-9\-]{20,}"), "[REDACTED_SLACK_TOKEN]"),
    # GitHub personal access tokens
    (re.compile(r"ghp_[A-Za-z0-9]{36,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"gho_[A-Za-z0-9]{36,}"), "[REDACTED_GITHUB_TOKEN]"),
    # Bearer tokens in headers
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}"), "Bearer [REDACTED_TOKEN]"),
    # AWS keys
    (re.compile(r"AKIA[A-Z0-9]{16}"), "[REDACTED_AWS_KEY]"),
    # Email addresses
    (re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+"), "[REDACTED_EMAIL]"),
    # US Social Security Numbers
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED_SSN]"),
]


class MemorySanitizer:
    """Redacts API keys, tokens, emails, and PII from text."""

    @staticmethod
    def sanitize(text: str) -> str:
        """Replace sensitive patterns with redaction labels."""
        for pattern, replacement in _PATTERNS:
            text = pattern.sub(replacement, text)
        return text
