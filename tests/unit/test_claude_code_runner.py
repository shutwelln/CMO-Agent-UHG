"""Tests for ClaudeCodeRunner subprocess wrapper."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cmo_agent.claude_code.runner import (
    ClaudeCodePhase,
    ClaudeCodeRunner,
    ClaudeCodeSession,
)


@pytest.fixture
def mock_settings():
    """Patch get_settings so ClaudeCodeRunner can be constructed."""
    with patch("cmo_agent.claude_code.runner.get_settings") as mock:
        s = MagicMock()
        s.claude_code_cwd = "/tmp/test"
        s.claude_code_max_message_length = 100
        s.claude_code_plan_timeout_ms = 5000
        s.claude_code_build_timeout_ms = 10000
        s.claude_code_binary = "claude"
        mock.return_value = s
        yield s


def _make_process(stdout: str = "", stderr: str = "", returncode: int = 0):
    """Create a mock asyncio subprocess."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout.encode(), stderr.encode()))
    proc.returncode = returncode
    proc.kill = MagicMock()
    proc.wait = AsyncMock()
    return proc


class TestClaudeCodeRunner:
    """Tests for ClaudeCodeRunner."""

    @pytest.mark.asyncio
    async def test_start_session_success(self, mock_settings):
        """start_session sends initial prompt and parses JSON result."""
        payload = json.dumps(
            {
                "result": "What is the target audience?",
                "session_id": "sess-abc",
                "is_error": False,
                "cost_usd": 0.005,
                "num_turns": 1,
            }
        )
        proc = _make_process(stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = ClaudeCodeRunner()
            result = await runner.start_session("test idea", "growth", "uhg")

        assert result.result_text == "What is the target audience?"
        assert result.session_id == "sess-abc"
        assert result.is_error is False
        assert result.cost_usd == 0.005
        assert result.num_turns == 1

    @pytest.mark.asyncio
    async def test_start_session_args(self, mock_settings):
        """start_session passes correct CLI args."""
        payload = json.dumps({"result": "ok", "session_id": "s1"})
        proc = _make_process(stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            runner = ClaudeCodeRunner()
            await runner.start_session("idea text", "uhg2", "uhg2")

        args = mock_exec.call_args[0]
        assert args[0] == "claude"
        assert "-p" in args
        assert "--output-format" in args
        assert "json" in args
        # Should NOT have --continue, --resume, or --session-id on first call
        assert "--continue" not in args
        assert "--resume" not in args
        assert "--session-id" not in args

    @pytest.mark.asyncio
    async def test_continue_session_args(self, mock_settings):
        """continue_session adds --resume with session id."""
        payload = json.dumps({"result": "noted", "session_id": "s1"})
        proc = _make_process(stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            runner = ClaudeCodeRunner()
            await runner.continue_session("s1", "focus on email", dangerous_mode=False)

        args = mock_exec.call_args[0]
        assert "--resume" in args
        assert "s1" in args
        # --continue and --session-id should NOT be used (causes CLI error)
        assert "--continue" not in args
        assert "--session-id" not in args
        assert "--dangerously-skip-permissions" not in args

    @pytest.mark.asyncio
    async def test_continue_session_dangerous(self, mock_settings):
        """continue_session adds --dangerously-skip-permissions when dangerous_mode=True."""
        payload = json.dumps({"result": "ok", "session_id": "s1"})
        proc = _make_process(stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            runner = ClaudeCodeRunner()
            await runner.continue_session("s1", "go", dangerous_mode=True)

        args = mock_exec.call_args[0]
        assert "--dangerously-skip-permissions" in args

    @pytest.mark.asyncio
    async def test_start_build_args(self, mock_settings):
        """start_build uses --resume with session id for build prompt."""
        payload = json.dumps({"result": "built", "session_id": "s1", "cost_usd": 0.1})
        proc = _make_process(stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            runner = ClaudeCodeRunner()
            result = await runner.start_build("s1", dangerous_mode=False)

        args = mock_exec.call_args[0]
        assert "--resume" in args
        assert "s1" in args
        # --continue and --session-id should NOT be used (causes CLI error)
        assert "--continue" not in args
        assert "--session-id" not in args
        assert "--dangerously-skip-permissions" not in args
        assert result.result_text == "built"

    @pytest.mark.asyncio
    async def test_start_build_dangerous(self, mock_settings):
        """start_build adds --dangerously-skip-permissions."""
        payload = json.dumps({"result": "done", "session_id": "s1"})
        proc = _make_process(stdout=payload)

        with patch("asyncio.create_subprocess_exec", return_value=proc) as mock_exec:
            runner = ClaudeCodeRunner()
            await runner.start_build("s1", dangerous_mode=True)

        args = mock_exec.call_args[0]
        assert "--dangerously-skip-permissions" in args

    @pytest.mark.asyncio
    async def test_subprocess_timeout(self, mock_settings):
        """Timeout returns an error result."""

        async def hang(*_a, **_kw):
            raise asyncio.TimeoutError()

        proc = _make_process()
        proc.communicate = hang

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = ClaudeCodeRunner()
            result = await runner.start_session("test", "growth", "ws")

        assert result.is_error is True
        assert "timed out" in result.result_text

    @pytest.mark.asyncio
    async def test_subprocess_nonzero_exit(self, mock_settings):
        """Non-zero exit code returns an error result."""
        proc = _make_process(stderr="something broke", returncode=1)

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = ClaudeCodeRunner()
            result = await runner.start_session("test", "growth", "ws")

        assert result.is_error is True
        assert "something broke" in result.result_text

    @pytest.mark.asyncio
    async def test_binary_not_found(self, mock_settings):
        """FileNotFoundError returns an error result."""

        async def raise_fnf(*_a, **_kw):
            raise FileNotFoundError("claude not found")

        with patch("asyncio.create_subprocess_exec", side_effect=raise_fnf):
            runner = ClaudeCodeRunner()
            result = await runner.start_session("test", "growth", "ws")

        assert result.is_error is True
        assert "not found" in result.result_text

    @pytest.mark.asyncio
    async def test_non_json_stdout(self, mock_settings):
        """Non-JSON stdout falls back to plain text."""
        proc = _make_process(stdout="plain text response")

        with patch("asyncio.create_subprocess_exec", return_value=proc):
            runner = ClaudeCodeRunner()
            result = await runner.start_session("test", "growth", "ws")

        assert result.result_text == "plain text response"
        assert result.is_error is False


class TestTruncateForSlack:
    """Tests for truncate_for_slack."""

    def test_short_text_unchanged(self, mock_settings):
        runner = ClaudeCodeRunner()
        assert runner.truncate_for_slack("hello") == "hello"

    def test_long_text_truncated_at_word(self, mock_settings):
        runner = ClaudeCodeRunner()
        text = "word " * 30  # 150 chars, limit is 100
        result = runner.truncate_for_slack(text)
        assert len(result) <= 104  # 100 + "..."
        assert result.endswith("...")

    def test_custom_max_length(self, mock_settings):
        runner = ClaudeCodeRunner()
        result = runner.truncate_for_slack("a " * 50, max_length=20)
        assert len(result) <= 23
        assert result.endswith("...")

    def test_exact_length_unchanged(self, mock_settings):
        runner = ClaudeCodeRunner()
        text = "x" * 100
        assert runner.truncate_for_slack(text) == text


class TestClaudeCodeSession:
    """Tests for ClaudeCodeSession dataclass."""

    def test_defaults(self):
        session = ClaudeCodeSession(
            conversation_id="c1",
            channel="C123",
            thread_ts="123.456",
            idea_text="test idea",
            idea_type="growth",
            workspace_id="ws",
        )
        assert session.phase == ClaudeCodePhase.PLANNING
        assert session.dangerous_mode is False
        assert session.turn_count == 0
        assert session.claude_session_id is None
