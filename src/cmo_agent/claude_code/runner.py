"""Claude Code CLI subprocess runner for plan-then-build workflows."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import structlog

from ..config import get_settings

logger = structlog.get_logger()


class ClaudeCodePhase(str, Enum):
    """Phase of a Claude Code session."""

    PLANNING = "planning"
    BUILDING = "building"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class ClaudeCodeSession:
    """Tracks an active Claude Code CLI session."""

    conversation_id: str
    channel: str
    thread_ts: str
    idea_text: str
    idea_type: str  # "growth"
    workspace_id: str
    claude_session_id: Optional[str] = None
    phase: ClaudeCodePhase = ClaudeCodePhase.PLANNING
    dangerous_mode: bool = False
    turn_count: int = 0
    last_activity: float = field(default_factory=time.time)


@dataclass
class ClaudeCodeResult:
    """Parsed result from a Claude Code CLI invocation."""

    result_text: str
    session_id: Optional[str] = None
    is_error: bool = False
    cost_usd: Optional[float] = None
    duration_ms: Optional[int] = None
    num_turns: Optional[int] = None


class ClaudeCodeRunner:
    """Runs Claude Code CLI as a subprocess for plan-then-build workflows."""

    def __init__(self) -> None:
        settings = get_settings()
        self._cwd = settings.claude_code_cwd
        self._max_message_length = settings.claude_code_max_message_length
        self._plan_timeout_ms = settings.claude_code_plan_timeout_ms
        self._build_timeout_ms = settings.claude_code_build_timeout_ms
        self._binary = settings.claude_code_binary

    async def start_session(
        self,
        idea_text: str,
        idea_type: str,
        workspace_id: str,
    ) -> ClaudeCodeResult:
        """Start a new Claude Code planning session for an idea.

        Sends the initial planning prompt and returns the first response.
        """
        logger.info(
            "claude_code_start_session",
            max_message_length=self._max_message_length,
            binary=self._binary,
            cwd=self._cwd,
        )
        prompt = (
            f"I want to plan and then build a feature based on this {idea_type} idea "
            f"for workspace '{workspace_id}':\n\n"
            f"{idea_text}\n\n"
            f"IMPORTANT RULES:\n"
            f"- Keep ALL responses under {self._max_message_length} characters.\n"
            f"- Start by asking 2-3 focused questions about scope and priorities.\n"
            f"- Plan before building — do NOT write any code yet.\n"
            f"- Wait for my explicit approval before building anything."
        )

        args = [
            self._binary,
            "-p",
            prompt,
            "--output-format",
            "json",
        ]

        return await self._run_subprocess(args, timeout_ms=self._plan_timeout_ms)

    async def continue_session(
        self,
        session_id: str,
        user_message: str,
        dangerous_mode: bool = False,
    ) -> ClaudeCodeResult:
        """Continue an existing Claude Code session with a user reply."""
        args = [
            self._binary,
            "-p",
            user_message,
            "--output-format",
            "json",
            "--resume",
            session_id,
        ]

        if dangerous_mode:
            args.append("--dangerously-skip-permissions")

        return await self._run_subprocess(args, timeout_ms=self._plan_timeout_ms)

    async def start_build(
        self,
        session_id: str,
        dangerous_mode: bool = False,
    ) -> ClaudeCodeResult:
        """Transition a session to the build phase."""
        build_prompt = (
            "The user has approved the plan. Proceed to build it now. "
            "Implement the changes discussed. "
            f"Keep status updates under {self._max_message_length} characters."
        )

        args = [
            self._binary,
            "-p",
            build_prompt,
            "--output-format",
            "json",
            "--resume",
            session_id,
        ]

        if dangerous_mode:
            args.append("--dangerously-skip-permissions")

        return await self._run_subprocess(args, timeout_ms=self._build_timeout_ms)

    def truncate_for_slack(self, text: str, max_length: Optional[int] = None) -> str:
        """Truncate text at a word boundary for Slack display."""
        limit = max_length or self._max_message_length
        logger.info(
            "truncate_for_slack",
            text_length=len(text),
            limit=limit,
            will_truncate=len(text) > limit,
        )
        if len(text) <= limit:
            return text

        truncated = text[:limit]
        last_space = truncated.rfind(" ")
        if last_space > limit // 2:
            truncated = truncated[:last_space]

        return truncated.rstrip() + "..."

    async def _run_subprocess(
        self,
        args: List[str],
        timeout_ms: int,
    ) -> ClaudeCodeResult:
        """Execute Claude Code CLI as an async subprocess and parse JSON output."""
        timeout_seconds = timeout_ms / 1000.0

        logger.info(
            "claude_code_subprocess_start",
            binary=args[0],
            timeout_ms=timeout_ms,
        )

        start_time = time.monotonic()

        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self._cwd,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout_seconds
                )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                duration_ms = int((time.monotonic() - start_time) * 1000)
                logger.error("claude_code_timeout", timeout_ms=timeout_ms)
                return ClaudeCodeResult(
                    result_text=f"Claude Code timed out after {timeout_ms}ms.",
                    is_error=True,
                    duration_ms=duration_ms,
                )

            duration_ms = int((time.monotonic() - start_time) * 1000)
            stdout_text = stdout.decode("utf-8", errors="replace")
            stderr_text = stderr.decode("utf-8", errors="replace")

            # Debug: dump raw output to file for inspection
            try:
                from pathlib import Path

                jsonl_lines = [
                    ln for ln in stdout_text.splitlines() if ln.strip()
                ]
                debug_dir = Path("/Users/nickshutwell/Desktop/CMO Agent/data")
                debug_path = debug_dir / "claude_code_debug.txt"
                debug_path.write_text(
                    f"--- returncode: {process.returncode} ---\n"
                    f"--- stdout_length: {len(stdout_text)} ---\n"
                    f"--- stderr_length: {len(stderr_text)} ---\n"
                    f"--- jsonl_lines: {len(jsonl_lines)} ---\n"
                    f"--- args: {' '.join(args[:6])} ---\n"
                    f"--- STDOUT (first 10000 chars) ---\n{stdout_text[:10000]}\n"
                    f"--- STDERR ---\n{stderr_text[:2000]}\n",
                    encoding="utf-8",
                )
            except Exception:
                pass

            if process.returncode != 0:
                error_msg = stderr_text[:500] if stderr_text else f"Exit code {process.returncode}"
                logger.error(
                    "claude_code_subprocess_error",
                    returncode=process.returncode,
                    stderr=error_msg,
                )
                return ClaudeCodeResult(
                    result_text=f"Claude Code error: {error_msg}",
                    is_error=True,
                    duration_ms=duration_ms,
                )

            return self._parse_json_output(stdout_text, duration_ms)

        except FileNotFoundError:
            logger.error("claude_code_binary_not_found", binary=args[0])
            return ClaudeCodeResult(
                result_text=f"Claude Code binary not found: {args[0]}",
                is_error=True,
            )
        except Exception as e:
            logger.error("claude_code_unexpected_error", error=str(e))
            return ClaudeCodeResult(
                result_text=f"Unexpected error running Claude Code: {e}",
                is_error=True,
            )

    def _parse_json_output(self, stdout: str, duration_ms: int) -> ClaudeCodeResult:
        """Parse the JSON/JSONL output from Claude Code CLI.

        Claude Code with --output-format json emits JSONL (one JSON object per
        line).  The final object with type=result contains the response text and
        session_id.  We iterate lines in reverse to find it quickly.
        """
        # --- Try JSONL: find the last "result" object ---
        data: Optional[Dict[str, Any]] = None
        last_json: Optional[Dict[str, Any]] = None

        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if last_json is None:
                last_json = obj
            if isinstance(obj, dict) and obj.get("type") == "result":
                data = obj
                break

        # Fall back to the last parseable JSON object (any type)
        if data is None and last_json is not None and isinstance(last_json, dict):
            data = last_json

        # Final fallback: try parsing the whole stdout as a single JSON blob
        if data is None:
            try:
                blob = json.loads(stdout)
                if isinstance(blob, dict):
                    data = blob
            except json.JSONDecodeError:
                pass

        if data is None:
            # No JSON found at all — return raw text
            logger.warning(
                "claude_code_no_json_found",
                stdout_length=len(stdout),
                first_200=stdout[:200],
            )
            return ClaudeCodeResult(
                result_text=stdout.strip()[:3000]
                if stdout.strip()
                else "No output from Claude Code.",
                duration_ms=duration_ms,
            )

        result_text = data.get("result", "") or data.get("text", "") or ""
        session_id = data.get("session_id") or data.get("sessionId")
        is_error = data.get("is_error", False) or data.get("isError", False)
        cost_usd = data.get("cost_usd") or data.get("costUsd")
        num_turns = data.get("num_turns") or data.get("numTurns")

        if isinstance(cost_usd, (int, float)):
            cost_usd = float(cost_usd)
        else:
            cost_usd = None

        if isinstance(num_turns, int):
            pass
        else:
            num_turns = None

        logger.info(
            "claude_code_result_parsed",
            session_id=session_id,
            is_error=is_error,
            cost_usd=cost_usd,
            num_turns=num_turns,
            duration_ms=duration_ms,
            result_length=len(result_text),
        )

        return ClaudeCodeResult(
            result_text=result_text,
            session_id=session_id,
            is_error=is_error,
            cost_usd=cost_usd,
            duration_ms=duration_ms,
            num_turns=num_turns,
        )
