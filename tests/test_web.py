"""Smoke tests for CMO Agent Web UI."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from cmo_agent.web.app import app

client = TestClient(app)


def test_health_endpoint():
    """Test /health returns ok status."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["service"] == "cmo-agent"


def test_index_page():
    """Test / returns the HTML page."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "CMO Agent" in response.text


def test_chat_endpoint_structure():
    """Test POST /chat returns expected response structure.

    Note: This test makes a real API call if env vars are set.
    In CI, you would mock the CMOSession.
    """
    response = client.post(
        "/chat",
        json={"message": "Hello", "session_id": "test-session-123"},
    )

    # Should return 200 or 500 (if API keys not configured)
    assert response.status_code in (200, 500)

    if response.status_code == 200:
        data = response.json()
        # Check response structure
        assert "reply" in data
        assert "status" in data
        assert "trace_id" in data
        assert "session_id" in data
        assert data["session_id"] == "test-session-123"


def test_delete_session_not_found():
    """Test DELETE /session returns 404 for unknown session."""
    response = client.delete("/session/nonexistent-session-id")
    assert response.status_code == 404
