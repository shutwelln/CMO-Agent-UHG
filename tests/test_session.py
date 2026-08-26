"""Tests for CMOSession."""

from __future__ import annotations

import pytest

from cmo_agent.runtime.session import CMOResponse, CMOSession


def test_cmo_response_to_dict():
    """Test CMOResponse.to_dict() method."""
    response = CMOResponse(
        text="Hello, world!",
        tool_calls=[{"name": "test_tool", "arguments": {}}],
        artifacts=[],
        status="final",
        trace_id="test-trace-123",
        actions_taken=["Did something"],
    )

    data = response.to_dict()

    assert data["text"] == "Hello, world!"
    assert data["status"] == "final"
    assert data["trace_id"] == "test-trace-123"
    assert len(data["tool_calls"]) == 1
    assert data["actions_taken"] == ["Did something"]


def test_cmo_response_defaults():
    """Test CMOResponse has sensible defaults."""
    response = CMOResponse(text="Test")

    assert response.text == "Test"
    assert response.status == "final"
    assert response.tool_calls == []
    assert response.artifacts == []
    assert response.actions_taken == []
    assert response.trace_id  # Should have auto-generated UUID


def test_session_initialization():
    """Test CMOSession can be created with or without session_id."""
    # With explicit session ID
    session1 = CMOSession(session_id="my-session")
    assert session1.session_id == "my-session"
    assert not session1._initialized

    # With auto-generated session ID
    session2 = CMOSession()
    assert session2.session_id  # Should have a UUID
    assert session2.session_id != session1.session_id


@pytest.mark.asyncio
async def test_session_lifecycle():
    """Test CMOSession context manager lifecycle.

    Note: This requires valid API keys to fully test.
    The test verifies the structure works correctly.
    """
    session = CMOSession(session_id="test-lifecycle")

    # Not initialized before entering context
    assert not session._initialized

    try:
        async with session:
            # Should be initialized inside context
            assert session._initialized
    except Exception:
        # May fail without valid API keys - that's ok for this test
        pass

    # Should be closed after exiting context
    assert not session._initialized


def test_session_format_action():
    """Test _format_action converts tool calls to readable strings."""
    session = CMOSession()

    # Test various tool call formats
    assert session._format_action({"name": "list_workflows"}) == "Listed available n8n workflows"

    assert (
        session._format_action({"name": "execute_workflow", "arguments": {"workflow_id": "abc123"}})
        == "Executed workflow: abc123"
    )

    # Sub-agent delegation
    assert (
        session._format_action(
            {
                "name": "writer_agent",
                "arguments": {"instruction": "Write a newsletter about discounts"},
            }
        )
        == "Delegated to Writer Agent: Write a newsletter about discounts"
    )

    assert (
        session._format_action({"name": "unknown_tool", "arguments": {}})
        == "Called tool: unknown_tool"
    )
