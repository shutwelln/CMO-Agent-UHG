"""Integration tests for n8n connection.

These tests require a valid .env file with n8n credentials.
Run with: pytest tests/integration -v
"""

import pytest
from cmo_agent.config import get_settings
from cmo_agent.n8n.client import N8NClient


@pytest.fixture
def n8n_client() -> N8NClient:
    """Create n8n client from environment settings."""
    settings = get_settings()
    return N8NClient(
        base_url=settings.n8n_base_url,
        api_key=settings.n8n_api_key,
    )


@pytest.mark.asyncio
async def test_n8n_health_check(n8n_client: N8NClient):
    """Test that we can connect to n8n."""
    async with n8n_client:
        is_healthy = await n8n_client.health_check()
        assert is_healthy, "n8n connection failed - check your API key and URL"


@pytest.mark.asyncio
async def test_list_workflows(n8n_client: N8NClient):
    """Test listing workflows from n8n."""
    async with n8n_client:
        response = await n8n_client.list_workflows(limit=10)
        assert response is not None
        assert hasattr(response, "data")
        print(f"Found {len(response.data)} workflows")
        for workflow in response.data[:5]:
            print(f"  - {workflow.name} (ID: {workflow.id}, Active: {workflow.active})")


@pytest.mark.asyncio
async def test_list_executions(n8n_client: N8NClient):
    """Test listing executions from n8n."""
    async with n8n_client:
        response = await n8n_client.list_executions(limit=5)
        assert response is not None
        assert hasattr(response, "data")
        print(f"Found {len(response.data)} recent executions")
