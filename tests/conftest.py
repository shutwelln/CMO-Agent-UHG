"""Pytest configuration and fixtures."""

import pytest
from unittest.mock import AsyncMock

from cmo_agent.config import Settings
from cmo_agent.n8n.client import N8NClient
from cmo_agent.llm.base import BaseLLM, LLMResponse, Message


@pytest.fixture
def mock_settings() -> Settings:
    """Create test settings."""
    return Settings(
        environment="development",
        anthropic_api_key="test-key",
        n8n_base_url="https://test.n8n.io",
        n8n_api_key="test-n8n-key",
        llm_provider="anthropic",
        llm_model="claude-sonnet-4-20250514",
    )


@pytest.fixture
def mock_n8n_client() -> N8NClient:
    """Create a mock n8n client."""
    client = N8NClient(
        base_url="https://test.n8n.io",
        api_key="test-key",
    )
    return client


@pytest.fixture
def mock_llm() -> BaseLLM:
    """Create a mock LLM."""
    llm = AsyncMock(spec=BaseLLM)
    llm.complete.return_value = LLMResponse(
        content="Test response",
        tool_calls=[],
    )
    return llm
