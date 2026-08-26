"""Slack bot using Socket Mode for CMO Agent with conversation memory."""

from __future__ import annotations

import asyncio
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog
from slack_bolt.adapter.socket_mode.async_handler import AsyncSocketModeHandler
from slack_bolt.async_app import AsyncApp

from ..claude_code import ClaudeCodePhase, ClaudeCodeRunner, ClaudeCodeSession
from ..config import get_settings
from ..files.processor import process_slack_files
from ..memory.store import ConversationMemory, MemoryMessage
from ..runtime.session import CMOSession

logger = structlog.get_logger()

# Session per conversation (conversation_id -> session)
conversation_sessions: Dict[str, CMOSession] = {}

# Claude Code sessions (conversation_id -> ClaudeCodeSession)
claude_code_sessions: Dict[str, ClaudeCodeSession] = {}

# Global memory store
memory_store: Optional[ConversationMemory] = None

# Global approval workflow (initialized when bot starts)
_approval_workflow: Optional[Any] = None

# Global scheduler (initialized when bot starts)
_scheduler: Optional[Any] = None

# Global skipped-idea repo (initialized when bot starts)
_skipped_idea_repo: Optional[Any] = None

# Global approved-idea repo (initialized when bot starts)
_approved_idea_repo: Optional[Any] = None

# Socket handler reference (for graceful restart)
_socket_handler: Optional[AsyncSocketModeHandler] = None

# Restart flag (set by admin command, checked by main())
_restart_requested: bool = False

# Product Ideas dashboard (initialized at startup if spreadsheet ID is configured)
_product_ideas_dashboard: Optional[Any] = None


def get_conversation_id(event: Dict[str, Any]) -> str:
    """Compute conversation_id from Slack event.

    Rules:
    - DM with thread: conversation_id = channel_id:thread_ts
    - DM without thread: conversation_id = channel_id:event_ts (fresh per message)
    - Channel with thread: conversation_id = channel_id:thread_ts
    - Channel without thread: conversation_id = channel_id:event_ts
    """
    channel = event.get("channel", "")
    thread_ts = event.get("thread_ts")
    event_ts = event.get("ts", "")

    # Threaded messages (DM or channel) share their thread's context
    if thread_ts:
        return f"{channel}:{thread_ts}"

    # Channel messages without a thread (start of new thread)
    return f"{channel}:{event_ts}"


def init_memory_store() -> ConversationMemory:
    """Initialize the memory store."""
    global memory_store
    if memory_store is None:
        settings = get_settings()
        memory_store = ConversationMemory(
            db_path=Path(settings.memory_db_path),
            max_messages=settings.memory_max_stored,
        )
    return memory_store


def create_slack_app() -> AsyncApp:
    """Create and configure the Slack app."""
    settings = get_settings()

    app = AsyncApp(
        token=settings.slack_bot_token,
        signing_secret=settings.slack_signing_secret if settings.slack_signing_secret else None,
    )

    # Initialize memory store
    memory = init_memory_store()

    async def handle_message(
        event: Dict[str, Any],
        say: Any,
        client: Any,
        memory: ConversationMemory,
        settings: Any,
    ) -> None:
        """Process incoming message and respond."""
        user_id = event.get("user")
        text = event.get("text", "").strip()
        channel = event.get("channel")
        thread_ts = event.get("thread_ts") or event.get("ts")
        event_ts = event.get("ts", "")
        files = event.get("files", [])

        # Remove bot mention from text
        text = re.sub(r"<@[A-Z0-9]+>\s*", "", text).strip()

        if not text and not files:
            return

        conversation_id = get_conversation_id(event)

        # Bind request_id into structlog context
        import uuid

        from structlog.contextvars import bind_contextvars, clear_contextvars

        request_id = f"slack-{conversation_id}-{uuid.uuid4().hex[:8]}"

        clear_contextvars()
        bind_contextvars(
            request_id=request_id,
            conversation_id=conversation_id,
            slack_user_id=user_id,
            slack_channel=channel,
            slack_thread_ts=thread_ts,
        )

        logger.info(
            "slack_message_received",
            user_id=user_id,
            channel=channel,
            conversation_id=conversation_id,
            text_length=len(text),
        )

        # Handle admin commands
        admin_response = await handle_admin_command(
            text, conversation_id, memory, say, thread_ts, user_id, channel
        )
        if admin_response:
            return

        # Check if memory is enabled for this conversation
        memory_enabled = settings.memory_enabled and memory.is_memory_enabled(conversation_id)

        # Get or create session for this conversation
        if conversation_id not in conversation_sessions:
            conversation_sessions[conversation_id] = CMOSession(
                session_id=f"slack-{conversation_id}"
            )
            logger.info("slack_session_created", conversation_id=conversation_id)

        session = conversation_sessions[conversation_id]

        # Load conversation history if memory is enabled
        history: Optional[List[Dict[str, str]]] = None
        if memory_enabled:
            prior_messages: List[MemoryMessage] = memory.get_messages(
                conversation_id,
                limit=settings.memory_max_turns,
            )
            if prior_messages:
                history = [{"role": m.role, "text": m.text} for m in prior_messages]
                logger.debug(
                    "slack_history_loaded",
                    conversation_id=conversation_id,
                    message_count=len(history),
                )

        # Process file attachments if present
        file_blocks: Optional[List[Dict[str, Any]]] = None
        if files:
            try:
                attachments = await process_slack_files(files, settings.slack_bot_token)
                if attachments:
                    file_blocks = []
                    file_descriptions = []
                    for att in attachments:
                        file_blocks.extend(att.content_blocks)
                        file_descriptions.append(att.summary)
                    logger.info(
                        "slack_files_processed",
                        count=len(attachments),
                        descriptions=file_descriptions,
                    )
                    if not text:
                        text = "I've uploaded the attached file(s). Please review and analyze them."
            except Exception as file_err:
                logger.error("slack_file_processing_error", error=str(file_err))

        # Send acknowledgment for potentially long operations
        await say(text="Working on it...", thread_ts=thread_ts)

        try:
            # Process message with history and file attachments
            response = await session.ask(
                text, history=history, file_blocks=file_blocks, slack_channel=channel
            )

            # Store user message and response in memory (skip errors)
            if memory_enabled and response.status != "error":
                memory.add_message(
                    conversation_id=conversation_id,
                    role="user",
                    text=text,
                    ts=event_ts,
                )
                memory.add_message(
                    conversation_id=conversation_id,
                    role="assistant",
                    text=_truncate_for_memory(response.text),
                    ts=event_ts + "_response",
                )

            # Check if the response contains structured ideas from sub-agents
            ideas_blocks = _extract_ideas_blocks_from_response(response)

            if ideas_blocks:
                # Post interactive idea blocks (with Approve buttons)
                for msg_blocks in ideas_blocks:
                    await say(
                        text="Here are the ideas I generated:",
                        blocks=msg_blocks,
                        thread_ts=thread_ts,
                    )
            else:
                # Standard text response, split if long
                text_chunks = _split_text_for_slack(response.text, max_chars=2900)

                for chunk_idx, chunk in enumerate(text_chunks):
                    blocks: List[Dict[str, Any]] = []
                    blocks.append(
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": chunk},
                        }
                    )

                    # On the last chunk, append actions taken and artifacts
                    if chunk_idx == len(text_chunks) - 1:
                        if response.actions_taken:
                            actions_text = "\n".join(f"- {a}" for a in response.actions_taken)
                            blocks.append({"type": "divider"})
                            blocks.append(
                                {
                                    "type": "context",
                                    "elements": [
                                        {
                                            "type": "mrkdwn",
                                            "text": f"Actions taken:\n{actions_text[:2900]}",
                                        }
                                    ],
                                }
                            )

                        # Render artifacts as Slack blocks
                        for artifact in response.artifacts:
                            art_type = artifact.get("type")
                            art_url = artifact.get("url")
                            if not art_url:
                                continue

                            if art_type == "image":
                                blocks.append(
                                    {
                                        "type": "image",
                                        "image_url": art_url,
                                        "alt_text": "Generated marketing image",
                                    }
                                )
                            elif art_type == "deck":
                                blocks.append(
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f":bar_chart: <{art_url}|Open presentation>",
                                        },
                                    }
                                )
                            elif art_type == "video":
                                blocks.append(
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f":movie_camera: <{art_url}|View video>",
                                        },
                                    }
                                )
                            elif art_type == "motion_graphic":
                                blocks.append(
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f":art: <{art_url}|View motion graphic>",
                                        },
                                    }
                                )
                            elif art_type == "doc":
                                blocks.append(
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f":page_facing_up: <{art_url}|Open Google Doc>",
                                        },
                                    }
                                )
                            elif art_type == "sheet":
                                blocks.append(
                                    {
                                        "type": "section",
                                        "text": {
                                            "type": "mrkdwn",
                                            "text": f":bar_chart: <{art_url}|Open Google Sheet>",
                                        },
                                    }
                                )

                    await say(
                        text=chunk[:3000],
                        blocks=blocks,
                        thread_ts=thread_ts,
                    )

            logger.info(
                "slack_response_sent",
                user_id=user_id,
                conversation_id=conversation_id,
                status=response.status,
                actions_count=len(response.actions_taken),
                memory_enabled=memory_enabled,
            )

        except Exception as e:
            logger.error("slack_error", error=str(e), user_id=user_id)
            await say(
                text=f"Sorry, I encountered an error: {e}",
                thread_ts=thread_ts,
            )

    @app.event("app_mention")
    async def handle_mention(event: Dict[str, Any], say: Any, client: Any) -> None:
        """Handle @mentions in channels."""
        # Check if this mention is in a Claude Code thread
        thread_ts = event.get("thread_ts")
        if thread_ts:
            channel = event.get("channel", "")
            conv_id = f"{channel}:{thread_ts}"
            if conv_id in claude_code_sessions:
                await handle_claude_code_reply(event, client)
                return

        await handle_message(event, say, client, memory, settings)

    @app.event("message")
    async def handle_dm(event: Dict[str, Any], say: Any, client: Any) -> None:
        """Handle direct messages and channel thread replies with active sessions."""
        # Ignore bot messages and most subtypes, but allow file_share
        if event.get("bot_id"):
            return
        subtype = event.get("subtype")
        if subtype and subtype != "file_share":
            return

        channel_type = event.get("channel_type", "")
        thread_ts = event.get("thread_ts")

        # Debug: log channel messages with thread_ts to diagnose routing
        if thread_ts and channel_type != "im":
            channel = event.get("channel", "")
            conv_id = f"{channel}:{thread_ts}"
            cc_match = conv_id in claude_code_sessions
            logger.info(
                "channel_thread_reply_received",
                channel=channel,
                thread_ts=thread_ts,
                conv_id=conv_id,
                cc_session_match=cc_match,
                cc_session_keys=list(claude_code_sessions.keys())[:5],
                channel_type=channel_type,
            )

        # Always handle DMs
        if channel_type == "im":
            await handle_message(event, say, client, memory, settings)
            return

        # For channel messages: only handle thread replies where we have an active session
        if thread_ts:
            channel = event.get("channel", "")
            conv_id = f"{channel}:{thread_ts}"
            # Claude Code sessions take priority over CMO sessions
            if conv_id in claude_code_sessions:
                await handle_claude_code_reply(event, client)
                return
            if conv_id in conversation_sessions:
                await handle_message(event, say, client, memory, settings)


    # Approval workflow interactive handlers

    @app.action("approve_draft")
    async def handle_approve_action(ack: Any, body: Any, client: Any) -> None:
        """Handle the Approve button click on a draft."""
        await ack()
        draft_id = body["actions"][0]["value"]
        user_id = body["user"]["id"]
        logger.info("slack_approve_draft", draft_id=draft_id, user_id=user_id)

        if _approval_workflow:
            await _approval_workflow.handle_approve(draft_id, user_id)
        else:
            channel = body["channel"]["id"]
            await client.chat_postMessage(
                channel=channel,
                text=f"Draft {draft_id} approved by <@{user_id}>.",
            )

    @app.action("edit_draft")
    async def handle_edit_action(ack: Any, body: Any, client: Any) -> None:
        """Handle the Request Edit button click on a draft."""
        await ack()
        draft_id = body["actions"][0]["value"]
        user_id = body["user"]["id"]
        logger.info("slack_edit_draft", draft_id=draft_id, user_id=user_id)

        if _approval_workflow:
            await _approval_workflow.handle_request_edit(draft_id, user_id)
        else:
            channel = body["channel"]["id"]
            message_ts = body["message"]["ts"]
            await client.chat_postMessage(
                channel=channel,
                thread_ts=message_ts,
                text=f"<@{user_id}> requested edits. Reply in this thread with feedback.",
            )

    @app.action("reject_draft")
    async def handle_reject_action(ack: Any, body: Any, client: Any) -> None:
        """Handle the Reject button click on a draft."""
        await ack()
        draft_id = body["actions"][0]["value"]
        user_id = body["user"]["id"]
        logger.info("slack_reject_draft", draft_id=draft_id, user_id=user_id)

        if _approval_workflow:
            await _approval_workflow.handle_reject(draft_id, user_id)
        else:
            channel = body["channel"]["id"]
            await client.chat_postMessage(
                channel=channel,
                text=f"Draft {draft_id} rejected by <@{user_id}>.",
            )

    # Growth Ideas interactive handlers

    @app.action("execute_growth_idea")
    async def handle_execute_growth_idea(ack: Any, body: Any, client: Any) -> None:
        """Handle the Approve button click on a growth idea.

        Creates a planning thread, presents a plan for user review before building.
        The user can reply in the thread to refine the plan, then confirm to build.
        """
        await ack()
        value = body["actions"][0]["value"]  # "draft_id:idea_index:ws_ids"
        user_id = body["user"]["id"]
        channel = body["channel"]["id"]
        logger.info("slack_approve_growth_idea", value=value, user_id=user_id)

        parts = value.split(":", 2)
        if len(parts) < 3:
            await client.chat_postEphemeral(
                channel=channel, user=user_id, text="Invalid idea reference."
            )
            return

        draft_id, idea_idx_str, ws_ids_str = parts
        idea_num = int(idea_idx_str) + 1

        # Extract the idea text from the original message blocks
        idea_text = ""
        target_block_id = f"idea_{value}"
        for block in body["message"].get("blocks", []):
            if block.get("block_id") == target_block_id:
                idea_text = block.get("text", {}).get("text", "")
                break

        # Parse the title from the idea text (format: "*N. Title*\nDescription...")
        idea_title = f"Growth Idea #{idea_num}"
        if idea_text:
            first_line = idea_text.split("\n")[0]
            clean_title = first_line.replace("*", "").strip()
            if clean_title:
                idea_title = clean_title

        # Record approval so this idea is excluded from future generation
        if _approved_idea_repo and idea_title:
            try:
                await _approved_idea_repo.add(
                    idea_title=idea_title,
                    idea_type="growth",
                    workspace_id=ws_ids_str if ws_ids_str != "cross_workspace" else None,
                    approved_by=user_id,
                )
            except Exception as e:
                logger.warning("approved_idea_record_failed", error=str(e))

        # Sync status to Product Ideas Google Sheet (graceful)
        if _product_ideas_dashboard and idea_title:
            try:
                # Strip leading number prefix (e.g. "3. Build a widget" -> "Build a widget")
                clean = idea_title
                if clean and clean[0].isdigit():
                    dot_pos = clean.find(". ")
                    if dot_pos != -1 and dot_pos < 5:
                        clean = clean[dot_pos + 2 :]
                await _product_ideas_dashboard.update_idea_status(clean, "In Progress")
            except Exception as e:
                logger.warning("growth_idea_sheet_status_update_failed", error=str(e))

        try:
            starter = await client.chat_postMessage(
                channel=channel,
                text=f"Planning: {idea_title}",
                blocks=[
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"Planning: {idea_title}"},
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": idea_text or f"Planning growth idea #{idea_num}...",
                        },
                    },
                    {
                        "type": "context",
                        "elements": [
                            {
                                "type": "mrkdwn",
                                "text": (
                                    f"Selected by <@{user_id}> | "
                                    f"Draft: `{draft_id}` | "
                                    f"Workspaces: {ws_ids_str}"
                                ),
                            }
                        ],
                    },
                ],
            )
            thread_ts = starter["ts"]
        except Exception as e:
            logger.error("growth_idea_starter_post_failed", error=str(e))
            await client.chat_postEphemeral(
                channel=channel,
                user=user_id,
                text=f"Failed to create planning thread: {e}",
            )
            return

        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="Starting Claude Code planning session...",
        )

        ws_label = ws_ids_str if ws_ids_str != "cross_workspace" else "all workspaces"
        conv_id = f"{channel}:{thread_ts}"

        runner = ClaudeCodeRunner()
        try:
            result = await runner.start_session(
                idea_text=idea_text or f"Growth idea #{idea_num} for {ws_label}",
                idea_type="growth",
                workspace_id=ws_label,
            )

            cc_session = ClaudeCodeSession(
                conversation_id=conv_id,
                channel=channel,
                thread_ts=thread_ts,
                idea_text=idea_text,
                idea_type="growth",
                workspace_id=ws_label,
                claude_session_id=result.session_id,
                phase=ClaudeCodePhase.ERROR if result.is_error else ClaudeCodePhase.PLANNING,
                turn_count=1,
            )
            claude_code_sessions[conv_id] = cc_session

            await _post_cc_response(client, channel, thread_ts, result.result_text)

            if not result.is_error:
                await _post_planning_hint(client, channel, thread_ts)

        except Exception as e:
            logger.error("growth_idea_planning_error", error=str(e))
            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"Error starting Claude Code: {e}",
            )

        # Update the original digest button to show approval
        try:
            message_ts = body["message"]["ts"]
            original_blocks = body["message"].get("blocks", [])
            updated_blocks = _disable_idea_button(original_blocks, value)
            if updated_blocks:
                await client.chat_update(
                    channel=channel,
                    ts=message_ts,
                    blocks=updated_blocks,
                    text="Daily Growth Ideas (updated)",
                )
        except Exception as e:
            logger.warning("growth_idea_button_update_failed", error=str(e))

    @app.action("noop_approved")
    async def handle_noop_approved(ack: Any, body: Any, client: Any) -> None:
        """No-op handler for the disabled Approved button."""
        await ack()

    @app.action("dismiss_growth_idea")
    async def handle_dismiss_growth_idea(ack: Any, body: Any, client: Any) -> None:
        """Handle the Dismiss button click on a growth idea."""
        await ack()
        value = body["actions"][0]["value"]
        user_id = body["user"]["id"]
        logger.info("slack_dismiss_growth_idea", value=value, user_id=user_id)

        channel = body["channel"]["id"]
        await client.chat_postEphemeral(
            channel=channel, user=user_id, text="Growth idea dismissed."
        )

    @app.action("skip_growth_idea")
    async def handle_skip_growth_idea(ack: Any, body: Any, client: Any) -> None:
        """Handle the Skip button click on a growth idea — excludes it from future generation."""
        await ack()
        value = body["actions"][0]["value"]
        user_id = body["user"]["id"]
        channel = body["channel"]["id"]
        logger.info("slack_skip_growth_idea", value=value, user_id=user_id)

        # Extract the idea title from the message blocks
        idea_title = _extract_idea_title_from_blocks(body["message"].get("blocks", []), value)

        if _skipped_idea_repo and idea_title:
            parts = value.split(":", 2)
            ws_id = parts[2] if len(parts) >= 3 else None
            await _skipped_idea_repo.add(
                idea_title=idea_title,
                idea_type="growth",
                workspace_id=ws_id,
                skipped_by=user_id,
            )

        # Sync status to Product Ideas Google Sheet (auto-archives)
        if _product_ideas_dashboard and idea_title:
            try:
                await _product_ideas_dashboard.update_idea_status(idea_title, "Skipped")
            except Exception as e:
                logger.warning("skip_growth_idea_sheet_update_failed", error=str(e))

        # Update the button to show it was skipped
        try:
            message_ts = body["message"]["ts"]
            original_blocks = body["message"].get("blocks", [])
            updated_blocks = _disable_idea_to_skipped(original_blocks, value, "execute_growth_idea")
            if updated_blocks:
                await client.chat_update(
                    channel=channel,
                    ts=message_ts,
                    blocks=updated_blocks,
                    text="Daily Growth Ideas (updated)",
                )
        except Exception as e:
            logger.warning("skip_growth_idea_button_update_failed", error=str(e))

        await client.chat_postEphemeral(
            channel=channel,
            user=user_id,
            text=f"Skipped: _{idea_title or 'idea'}_. It won't appear in future runs.",
        )

    @app.action("mark_idea_launched")
    async def handle_mark_idea_launched(ack: Any, body: Any, client: Any) -> None:
        """Handle the 'Mark as Launched' button on stale idea reminders."""
        await ack()
        value = body["actions"][0]["value"]  # "idea_id:idea_type"
        user_id = body["user"]["id"]
        channel = body["channel"]["id"]
        logger.info("slack_mark_idea_launched", value=value, user_id=user_id)

        parts = value.split(":", 1)
        if len(parts) < 2 or not _approved_idea_repo:
            await client.chat_postEphemeral(
                channel=channel, user=user_id, text="Could not process launch."
            )
            return

        idea_id = int(parts[0])
        await _approved_idea_repo.mark_launched(idea_id)

        # Update the button to show it was launched
        try:
            import copy

            message_ts = body["message"]["ts"]
            original_blocks = body["message"].get("blocks", [])
            updated = copy.deepcopy(original_blocks)
            for block in updated:
                acc = block.get("accessory", {})
                if acc.get("action_id") == "mark_idea_launched" and acc.get("value") == value:
                    block["accessory"] = {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Launched"},
                        "action_id": "noop_approved",
                        "value": value,
                    }
                    break
            await client.chat_update(
                channel=channel,
                ts=message_ts,
                blocks=updated,
                text="Stale ideas reminder (updated)",
            )
        except Exception as e:
            logger.warning("mark_launched_button_update_failed", error=str(e))

        await client.chat_postEphemeral(
            channel=channel,
            user=user_id,
            text="Idea marked as launched.",
        )



    # Claude Code interactive handlers

    async def handle_claude_code_reply(event: Dict[str, Any], client: Any) -> None:
        """Route a thread reply to an active Claude Code session."""
        channel = event.get("channel", "")
        thread_ts = event.get("thread_ts", "")
        conv_id = f"{channel}:{thread_ts}"
        user_text = event.get("text", "").strip()
        user_text = re.sub(r"<@[A-Z0-9]+>\s*", "", user_text).strip()

        if not user_text:
            return

        cc_session = claude_code_sessions.get(conv_id)
        if not cc_session or not cc_session.claude_session_id:
            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="No active Claude Code session found for this thread.",
            )
            return

        # Handle "done" to end the session
        if user_text.lower().strip() in ("done", "end", "close"):
            claude_code_sessions.pop(conv_id, None)
            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Session ended. Start a new one by clicking Build It on an idea.",
            )
            return

        logger.info(
            "claude_code_reply",
            conv_id=conv_id,
            session_id=cc_session.claude_session_id,
            phase=cc_session.phase.value,
        )

        runner = ClaudeCodeRunner()
        try:
            result = await runner.continue_session(
                session_id=cc_session.claude_session_id,
                user_message=user_text,
                dangerous_mode=cc_session.dangerous_mode,
            )

            cc_session.turn_count += 1
            cc_session.last_activity = __import__("time").time()
            if result.session_id:
                cc_session.claude_session_id = result.session_id

            await _post_cc_response(client, channel, thread_ts, result.result_text)

            # Show build buttons only during initial planning (first few turns)
            if (
                not result.is_error
                and cc_session.phase == ClaudeCodePhase.PLANNING
                and cc_session.turn_count <= 5
            ):
                await _post_claude_code_actions(client, channel, thread_ts)

        except Exception as e:
            logger.error("claude_code_reply_error", error=str(e))
            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"Error from Claude Code: {e}",
            )

    @app.action("claude_code_build")
    async def handle_claude_code_build(ack: Any, body: Any, client: Any) -> None:
        """Handle 'Build It' button — start build without dangerous mode."""
        await ack()
        channel = body["channel"]["id"]
        thread_ts = body["message"].get("thread_ts") or body["message"]["ts"]
        conv_id = f"{channel}:{thread_ts}"
        user_id = body["user"]["id"]

        cc_session = claude_code_sessions.get(conv_id)
        if not cc_session or not cc_session.claude_session_id:
            await client.chat_postEphemeral(
                channel=channel, user=user_id, text="No active Claude Code session."
            )
            return

        cc_session.phase = ClaudeCodePhase.BUILDING
        cc_session.dangerous_mode = False
        logger.info("claude_code_build_start", conv_id=conv_id, dangerous=False)

        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="Building... this may take a few minutes.",
        )

        runner = ClaudeCodeRunner()
        try:
            result = await runner.start_build(
                session_id=cc_session.claude_session_id,
                dangerous_mode=False,
            )
            cc_session.phase = ClaudeCodePhase.COMPLETE
            await _post_build_summary(result, runner, client, channel, thread_ts, conv_id)
        except Exception as e:
            cc_session.phase = ClaudeCodePhase.ERROR
            logger.error("claude_code_build_error", error=str(e))
            await client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=f"Build error: {e}"
            )

    @app.action("claude_code_build_dangerous")
    async def handle_claude_code_build_dangerous(ack: Any, body: Any, client: Any) -> None:
        """Handle 'Build It (Skip Permissions)' button — build with dangerous mode."""
        await ack()
        channel = body["channel"]["id"]
        thread_ts = body["message"].get("thread_ts") or body["message"]["ts"]
        conv_id = f"{channel}:{thread_ts}"
        user_id = body["user"]["id"]

        cc_session = claude_code_sessions.get(conv_id)
        if not cc_session or not cc_session.claude_session_id:
            await client.chat_postEphemeral(
                channel=channel, user=user_id, text="No active Claude Code session."
            )
            return

        cc_session.phase = ClaudeCodePhase.BUILDING
        cc_session.dangerous_mode = True
        logger.info("claude_code_build_start", conv_id=conv_id, dangerous=True)

        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="Building (skip permissions)... this may take a few minutes.",
        )

        runner = ClaudeCodeRunner()
        try:
            result = await runner.start_build(
                session_id=cc_session.claude_session_id,
                dangerous_mode=True,
            )
            cc_session.phase = ClaudeCodePhase.COMPLETE
            await _post_build_summary(result, runner, client, channel, thread_ts, conv_id)
        except Exception as e:
            cc_session.phase = ClaudeCodePhase.ERROR
            logger.error("claude_code_build_error", error=str(e))
            await client.chat_postMessage(
                channel=channel, thread_ts=thread_ts, text=f"Build error: {e}"
            )

    @app.action("claude_code_cancel")
    async def handle_claude_code_cancel(ack: Any, body: Any, client: Any) -> None:
        """Handle 'Cancel' button — tear down Claude Code session."""
        await ack()
        channel = body["channel"]["id"]
        thread_ts = body["message"].get("thread_ts") or body["message"]["ts"]
        conv_id = f"{channel}:{thread_ts}"
        user_id = body["user"]["id"]

        removed = claude_code_sessions.pop(conv_id, None)
        if removed:
            logger.info("claude_code_cancelled", conv_id=conv_id, user_id=user_id)
            await client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Claude Code session cancelled.",
            )
        else:
            await client.chat_postEphemeral(
                channel=channel, user=user_id, text="No active session to cancel."
            )

    return app


async def handle_admin_command(
    text: str,
    conversation_id: str,
    memory: ConversationMemory,
    say: Any,
    thread_ts: str,
    user_id: Optional[str] = None,
    channel: Optional[str] = None,
) -> bool:
    """Handle admin commands. Returns True if command was handled."""
    text_lower = text.lower().strip()

    if text_lower == "memory off":
        memory.set_memory_enabled(conversation_id, False)
        await say(
            text="Memory disabled for this conversation. I won't remember our chat history.",
            thread_ts=thread_ts,
        )
        logger.info("slack_memory_disabled", conversation_id=conversation_id)
        return True

    if text_lower == "memory on":
        memory.set_memory_enabled(conversation_id, True)
        await say(
            text="Memory enabled for this conversation. I'll remember our chat history.",
            thread_ts=thread_ts,
        )
        logger.info("slack_memory_enabled", conversation_id=conversation_id)
        return True

    if text_lower == "memory clear":
        deleted = memory.clear_conversation(conversation_id)
        await say(
            text=f"Cleared {deleted} messages from memory for this conversation.",
            thread_ts=thread_ts,
        )
        logger.info("slack_memory_cleared", conversation_id=conversation_id, deleted=deleted)
        return True

    if text_lower == "memory status":
        enabled = memory.is_memory_enabled(conversation_id)
        messages = memory.get_messages(conversation_id)
        stats = memory.get_stats()
        status_text = (
            "Memory Status\n"
            f"- Enabled for this conversation: {'Yes' if enabled else 'No'}\n"
            f"- Messages in this conversation: {len(messages)}\n"
            f"- Total conversations: {stats['conversations']}\n"
            f"- Total messages stored: {stats['messages']}"
        )
        await say(text=status_text, thread_ts=thread_ts)
        return True

    if text_lower == "restart":
        settings = get_settings()
        admin_ids = [u.strip() for u in settings.slack_admin_users.split(",") if u.strip()]
        if not admin_ids or user_id not in admin_ids:
            await say(text="Sorry, only admin users can restart the bot.", thread_ts=thread_ts)
            return True
        await say(text="Restarting bot... back in a moment.", thread_ts=thread_ts)
        # Save restart context so we can confirm in the same thread after restart
        _save_restart_context(channel, thread_ts)
        logger.info("slack_restart_requested", user_id=user_id)
        asyncio.get_event_loop().call_later(1.0, _trigger_restart)
        return True

    return False


def _trigger_restart() -> None:
    """Initiate graceful shutdown for restart (exit code 42)."""
    global _restart_requested
    _restart_requested = True

    async def _do_shutdown() -> None:
        if _socket_handler:
            try:
                await asyncio.wait_for(_socket_handler.close_async(), timeout=5.0)
            except Exception:
                pass
            # Give the handler a moment to finish its loop
            await asyncio.sleep(0.5)

        # If close_async didn't cause start_async to return, force exit.
        # os._exit skips finally blocks but the CLI restart loop will relaunch.
        import os

        logger.warning("restart_force_exit")
        os._exit(42)

    asyncio.ensure_future(_do_shutdown())


_RESTART_CONTEXT_FILE = Path("data/.restart_context.json")


def _save_restart_context(channel: str, thread_ts: Optional[str]) -> None:
    """Persist restart origin so we can confirm in the same thread after restart."""
    import json as _json

    try:
        _RESTART_CONTEXT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _RESTART_CONTEXT_FILE.write_text(_json.dumps({"channel": channel, "thread_ts": thread_ts}))
    except Exception as e:
        logger.warning("restart_context_save_failed", error=str(e))


def _load_and_clear_restart_context() -> Optional[Dict[str, Any]]:
    """Load restart context if it exists, then delete the file."""
    import json as _json

    if not _RESTART_CONTEXT_FILE.exists():
        return None
    try:
        ctx = _json.loads(_RESTART_CONTEXT_FILE.read_text())
        _RESTART_CONTEXT_FILE.unlink()
        return ctx
    except Exception as e:
        logger.warning("restart_context_load_failed", error=str(e))
        return None


async def run_slack_bot() -> None:
    """Run the Slack bot with Socket Mode."""
    global \
        _approval_workflow, \
        _scheduler, \
        _socket_handler, \
        _skipped_idea_repo, \
        _approved_idea_repo, \
        _product_ideas_dashboard

    settings = get_settings()

    if not settings.slack_bot_token:
        raise ValueError("SLACK_BOT_TOKEN is required")
    if not settings.slack_app_token:
        raise ValueError("SLACK_APP_TOKEN is required")

    app = create_slack_app()
    handler = AsyncSocketModeHandler(app, settings.slack_app_token)
    _socket_handler = handler

    # Initialize Phase 2 components (approval workflow + scheduler)
    db = None
    agent_registry = None
    try:
        from slack_sdk.web.async_client import AsyncWebClient

        from ..agents.factory import AgentFactory
        from ..approval.workflow import ApprovalWorkflow
        from ..db.database import Database
        from ..n8n.client import N8NClient

        db = Database(db_path=settings.db_path)
        await db.initialize()

        slack_client = AsyncWebClient(token=settings.slack_bot_token)
        _approval_workflow = ApprovalWorkflow(db=db, slack_client=slack_client)
        logger.info("approval_workflow_initialized")

        from ..db.repositories import ApprovedIdeaRepo, SkippedIdeaRepo

        _skipped_idea_repo = SkippedIdeaRepo(db)
        _approved_idea_repo = ApprovedIdeaRepo(db)
        logger.info("idea_repos_initialized")

        # Initialize Product Ideas dashboard if spreadsheet ID is configured
        if settings.growth_ideas_spreadsheet_id:
            from ..growth_ideas import ProductIdeasDashboard

            _product_ideas_dashboard = ProductIdeasDashboard(
                google_credentials_path=settings.google_credentials_path,
                google_oauth_token_path=settings.google_oauth_token_path,
                spreadsheet_id=settings.growth_ideas_spreadsheet_id,
            )
            logger.info(
                "product_ideas_dashboard_initialized",
                spreadsheet_id=settings.growth_ideas_spreadsheet_id,
            )

        # Build agents for scheduler
        if settings.scheduler_enabled:
            n8n_client = N8NClient(
                base_url=settings.n8n_base_url,
                api_key=settings.n8n_api_key,
                timeout=settings.n8n_timeout,
            )
            await n8n_client.__aenter__()

            agent_registry = await AgentFactory.create_all(
                settings=settings,
                db=db,
                n8n_client=n8n_client,
            )

            from ..scheduler.scheduler import AgentScheduler
            from ..scheduler.tasks import (
                make_daily_growth_ideas,
                make_health_summary,
                make_scan_fraud,
                make_scan_google_alerts,
                make_scan_reddit,
                make_scan_rss,
                make_stale_growth_ideas_reminder,
            )

            _scheduler = AgentScheduler()
            _scheduler.register_task(
                "scan_reddit",
                make_scan_reddit(agent_registry, db, slack_client),
                interval_seconds=24 * 3600,
                daily_at=(6, 0),
                tz_offset_hours=-6.0,
                run_immediately=False,
            )
            _scheduler.register_task(
                "scan_rss",
                make_scan_rss(agent_registry, db, slack_client),
                interval_seconds=24 * 3600,
                daily_at=(6, 0),
                tz_offset_hours=-6.0,
                run_immediately=False,
            )
            _scheduler.register_task(
                "scan_google_alerts",
                make_scan_google_alerts(agent_registry, db, slack_client),
                interval_seconds=24 * 3600,
                daily_at=(6, 0),
                tz_offset_hours=-6.0,
                run_immediately=False,
            )
            _scheduler.register_task(
                "scan_fraud",
                make_scan_fraud(agent_registry, db, slack_client),
                interval_seconds=7 * 24 * 3600,
            )
            _scheduler.register_task(
                "health_summary",
                make_health_summary(agent_registry, db, slack_client),
                interval_seconds=24 * 3600,
                daily_at=(6, 0),
                tz_offset_hours=-6.0,
                run_immediately=False,
            )
            growth_channel = (
                settings.slack_growth_ideas_channel or settings.slack_notification_channel
            )
            _scheduler.register_task(
                "daily_growth_ideas",
                make_daily_growth_ideas(
                    agent_registry,
                    db,
                    slack_client,
                    growth_channel,
                    ideas_count_min=settings.growth_ideas_count_min,
                    ideas_count_max=settings.growth_ideas_count_max,
                    product_ideas_dashboard=_product_ideas_dashboard,
                ),
                interval_seconds=24 * 3600,
                daily_at=(
                    settings.growth_ideas_schedule_hour,
                    settings.growth_ideas_schedule_minute,
                ),
                tz_offset_hours=settings.growth_ideas_tz_offset,
                run_immediately=False,
                every_n_days=settings.growth_ideas_frequency_days,
            )
            # --- Stale approved growth ideas reminder ---
            _scheduler.register_task(
                "stale_growth_ideas_reminder",
                make_stale_growth_ideas_reminder(db, slack_client, growth_channel, stale_days=7),
                interval_seconds=24 * 3600,
                daily_at=(
                    settings.growth_ideas_schedule_hour,
                    settings.growth_ideas_schedule_minute,
                ),
                tz_offset_hours=settings.growth_ideas_tz_offset,
                run_immediately=False,
            )

            _scheduler.start()
            logger.info("scheduler_started_with_bot")

    except Exception as e:
        logger.warning("phase2_init_partial", error=str(e))

    logger.info("slack_bot_starting", memory_enabled=settings.memory_enabled)
    print("CMO Agent Slack bot is running. Press Ctrl+C to stop.")
    print(f"Memory: {'enabled' if settings.memory_enabled else 'disabled'}")
    print(f"Scheduler: {'enabled' if settings.scheduler_enabled else 'disabled'}")

    # If restarting, send confirmation in the same thread where restart was requested
    restart_ctx = _load_and_clear_restart_context()
    if restart_ctx:

        async def _send_restart_confirmation() -> None:
            await asyncio.sleep(3)  # Wait for socket connection to stabilize
            try:
                from slack_sdk.web.async_client import AsyncWebClient

                client = AsyncWebClient(token=settings.slack_bot_token)
                await client.chat_postMessage(
                    channel=restart_ctx["channel"],
                    text="CMO Agent is back online and ready.",
                    thread_ts=restart_ctx.get("thread_ts"),
                )
                logger.info(
                    "restart_confirmation_sent",
                    channel=restart_ctx["channel"],
                    thread_ts=restart_ctx.get("thread_ts"),
                )
            except Exception as e:
                logger.warning("restart_confirmation_failed", error=str(e))

        asyncio.ensure_future(_send_restart_confirmation())

    try:
        await handler.start_async()
    finally:
        if _scheduler:
            _scheduler.stop()

        for session_id, session in conversation_sessions.items():
            try:
                await session.close()
            except Exception as e:
                logger.error("slack_session_close_error", session_id=session_id, error=str(e))
        conversation_sessions.clear()
        claude_code_sessions.clear()

        if memory_store:
            memory_store.close()

        if db:
            await db.close()


def _extract_ideas_blocks_from_response(
    response: Any,
) -> Optional[List[List[Dict[str, Any]]]]:
    """Extract structured ideas from a CMOResponse and build interactive Slack blocks."""
    ideas: List[Dict[str, Any]] = []
    draft_id = ""
    recommended_pick = ""

    for tc in response.tool_calls:
        tool_name = tc.get("name", "")
        tc_result = tc.get("result", {})
        if not isinstance(tc_result, dict):
            continue

        if tool_name == "growth_ideas_agent":
            sub_tool_calls = tc_result.get("tool_calls", [])
            for sub_tc in sub_tool_calls:
                sub_result = sub_tc.get("result", {})
                if not isinstance(sub_result, dict):
                    continue
                if sub_result.get("ideas") and isinstance(sub_result["ideas"], list):
                    ideas = sub_result["ideas"]
                    draft_id = sub_result.get("draft_id", "")
                    recommended_pick = sub_result.get("recommended_pick", "")
                    break
            if ideas:
                break

        if tc_result.get("ideas") and isinstance(tc_result["ideas"], list):
            ideas = tc_result["ideas"]
            draft_id = tc_result.get("draft_id", "")
            recommended_pick = tc_result.get("recommended_pick", "")
            break

    if not ideas:
        return None

    _MAX_PER_MSG = 8
    header_title = "Growth Ideas"
    header_context = f"Growth ideas | {len(ideas)} generated"
    action_id = "execute_growth_idea"
    footer_label = "Growth Ideas Agent"

    header_blocks: List[Dict[str, Any]] = [
        {"type": "header", "text": {"type": "plain_text", "text": header_title}},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": header_context}],
        },
        {"type": "divider"},
    ]

    idea_sections: List[Dict[str, Any]] = []
    for i, idea in enumerate(ideas, 1):
        title = idea.get("title", "Untitled")
        desc = idea.get("description", "")
        impact = idea.get("impact_score", "?")
        effort = idea.get("effort_score", "?")
        category = idea.get("category", "")
        cat_display = category.replace("_", " ") if category else ""
        scores_line = f"Impact: {impact}/10 | Effort: {effort}/10 | Category: {cat_display}"
        workspaces = idea.get("workspaces", [])
        ws_value = ",".join(workspaces) if workspaces else "cross_workspace"

        text_parts = [f"{i}. {title}", desc, scores_line]
        button_value = f"{draft_id}:{i - 1}:{ws_value}"

        section: Dict[str, Any] = {
            "type": "section",
            "block_id": f"idea_{button_value}",
            "text": {"type": "mrkdwn", "text": "\n".join(text_parts)[:2900]},
        }

        actions_block: Dict[str, Any] = {
            "type": "actions",
            "block_id": f"actions_{button_value}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔥 Build It 🔥"},
                    "action_id": action_id,
                    "value": button_value,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Skip"},
                    "action_id": "skip_growth_idea",
                    "value": button_value,
                },
            ],
        }

        idea_sections.append(section)
        idea_sections.append(actions_block)

    footer_blocks: List[Dict[str, Any]] = [{"type": "divider"}]
    if recommended_pick:
        footer_blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"Recommended priority\n\n{recommended_pick[:2900]}",
                },
            }
        )
    footer_blocks.append(
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Draft ID: `{draft_id}` | Generated by {footer_label}"}
            ],
        }
    )

    messages: List[List[Dict[str, Any]]] = []
    for batch_start in range(0, len(idea_sections), _MAX_PER_MSG):
        batch = idea_sections[batch_start : batch_start + _MAX_PER_MSG]
        msg_blocks: List[Dict[str, Any]] = []

        if batch_start == 0:
            msg_blocks.extend(header_blocks)

        msg_blocks.extend(batch)

        if batch_start + _MAX_PER_MSG >= len(idea_sections):
            msg_blocks.extend(footer_blocks)

        messages.append(msg_blocks)

    return messages if messages else None


def _truncate_for_memory(text: str, max_chars: int = 800) -> str:
    """Truncate assistant response for memory storage.

    The full response is already shown in Slack — memory only needs enough
    for the LLM to understand what was previously discussed.
    """
    if len(text) <= max_chars:
        return text

    # Try to cut at a paragraph boundary
    cut_at = text.rfind("\n\n", 0, max_chars)
    if cut_at == -1 or cut_at < max_chars // 3:
        # Try sentence boundary
        cut_at = text.rfind(". ", 0, max_chars)
        if cut_at != -1:
            cut_at += 1  # include the period
    if cut_at == -1 or cut_at < max_chars // 3:
        cut_at = max_chars

    return text[:cut_at].rstrip() + "\n\n[...truncated]"


def _split_text_for_slack(text: str, max_chars: int = 2900) -> List[str]:
    """Split long text into Slack-safe chunks, breaking at paragraph/line boundaries."""
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    remaining = text

    while remaining:
        if len(remaining) <= max_chars:
            chunks.append(remaining)
            break

        cut_at = remaining.rfind("\n\n", 0, max_chars)
        if cut_at == -1 or cut_at < max_chars // 3:
            cut_at = remaining.rfind("\n", 0, max_chars)
        if cut_at == -1 or cut_at < max_chars // 3:
            cut_at = remaining.rfind(" ", 0, max_chars)
        if cut_at == -1:
            cut_at = max_chars

        chunks.append(remaining[:cut_at].rstrip())
        remaining = remaining[cut_at:].lstrip()

    return chunks


def _disable_idea_button(
    blocks: List[Dict[str, Any]], button_value: str
) -> Optional[List[Dict[str, Any]]]:
    """Replace the actions block with an 'Approved' indicator for the given growth idea."""
    import copy

    target_actions_id = f"actions_{button_value}"
    updated = copy.deepcopy(blocks)
    for block in updated:
        if block.get("block_id") == target_actions_id:
            noop_id = "noop_approved"
            block["elements"] = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Building..."},
                    "action_id": noop_id,
                    "value": button_value,
                    "style": "primary",
                }
            ]
            return updated
    return None




def _disable_idea_to_skipped(
    blocks: List[Dict[str, Any]], button_value: str, execute_action_id: str
) -> Optional[List[Dict[str, Any]]]:
    """Replace the actions block with a 'Skipped' indicator."""
    import copy

    target_actions_id = f"actions_{button_value}"
    noop_id = "noop_approved"
    updated = copy.deepcopy(blocks)
    for block in updated:
        if block.get("block_id") == target_actions_id:
            block["elements"] = [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Skipped"},
                    "action_id": noop_id,
                    "value": button_value,
                }
            ]
            return updated
    return None


def _extract_idea_title_from_blocks(blocks: List[Dict[str, Any]], button_value: str) -> str:
    """Extract the idea title from the section block associated with the given button value."""
    target_block_id = f"idea_{button_value}"
    for block in blocks:
        if block.get("block_id") == target_block_id:
            text = block.get("text", {}).get("text", "")
            if text:
                first_line = text.split("\n")[0]
                # Strip leading number and markdown bold markers
                clean = re.sub(r"^\d+\.\s*", "", first_line).replace("*", "").strip()
                return clean
    return ""


async def _post_planning_hint(client: Any, channel: str, thread_ts: str) -> None:
    """Post a hint telling the user to @mention the bot in the thread to continue."""
    # Resolve the bot's own user ID for a proper @mention
    bot_mention = "me"
    try:
        auth = await client.auth_test()
        bot_uid = auth.get("user_id")
        if bot_uid:
            bot_mention = f"<@{bot_uid}>"
    except Exception:
        pass

    await client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=f"To reply, tag {bot_mention} at the start of your message. Example: {bot_mention} here are my answers...",
        blocks=[
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        f":point_right: *To continue, tag {bot_mention} "
                        f"at the start of your reply.*\n"
                        f"Example: `{bot_mention} here are my answers...`"
                    ),
                },
            },
        ],
    )


async def _post_claude_code_actions(client: Any, channel: str, thread_ts: str) -> None:
    """Post the Build / Build (Skip Permissions) / Cancel buttons to a thread."""
    await client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text="Reply in this thread to answer the questions above and refine the plan. When ready, click a build button.",
        blocks=[
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": "Reply in this thread to answer the questions and refine the plan. When the plan is ready, choose a build option below.",
                    }
                ],
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Build (Step-by-Step)"},
                        "action_id": "claude_code_build",
                        "value": "build",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Build (Auto-Approve)"},
                        "action_id": "claude_code_build_dangerous",
                        "value": "build_dangerous",
                        "style": "danger",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Cancel"},
                        "action_id": "claude_code_cancel",
                        "value": "cancel",
                    },
                ],
            },
        ],
    )


async def _post_cc_response(
    client: Any,
    channel: str,
    thread_ts: str,
    text: str,
) -> None:
    """Post a Claude Code response using mrkdwn blocks for better rendering.

    Slack section blocks have a 3000-char text limit, so we split if needed.
    """
    MAX_SECTION = 2900  # leave margin for safety
    if not text:
        text = "(no response)"

    # Split into chunks at paragraph or sentence boundaries
    chunks: List[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= MAX_SECTION:
            chunks.append(remaining)
            break
        # Find a good break point
        cut = remaining[:MAX_SECTION].rfind("\n\n")
        if cut < MAX_SECTION // 2:
            cut = remaining[:MAX_SECTION].rfind("\n")
        if cut < MAX_SECTION // 2:
            cut = remaining[:MAX_SECTION].rfind(". ")
            if cut > 0:
                cut += 1  # include the period
        if cut < MAX_SECTION // 2:
            cut = MAX_SECTION
        chunks.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()

    blocks: List[Dict[str, Any]] = []
    for chunk in chunks:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": chunk}})

    await client.chat_postMessage(
        channel=channel,
        thread_ts=thread_ts,
        text=text[:3000],  # plain-text fallback
        blocks=blocks,
    )


async def _post_build_summary(
    result: Any,
    runner: Any,
    client: Any,
    channel: str,
    thread_ts: str,
    conv_id: str,
) -> None:
    """Post build results and keep session alive for continued iteration."""
    meta_parts: List[str] = []
    if result.cost_usd is not None:
        meta_parts.append(f"Cost: ${result.cost_usd:.4f}")
    if result.duration_ms is not None:
        meta_parts.append(f"Duration: {result.duration_ms / 1000:.1f}s")
    if result.num_turns is not None:
        meta_parts.append(f"Turns: {result.num_turns}")

    full_text = f"*Build complete*\n{result.result_text}"
    if meta_parts:
        full_text += "\n\n_" + " | ".join(meta_parts) + "_"

    await _post_cc_response(client, channel, thread_ts, full_text)

    # Keep session alive — transition back to PLANNING so user can keep iterating
    cc_session = claude_code_sessions.get(conv_id)
    if cc_session:
        cc_session.phase = ClaudeCodePhase.PLANNING
        await client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            text="Reply in this thread to keep iterating, or type 'done' to end the session.",
            blocks=[
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": (
                                "Reply in this thread to keep iterating on this idea. "
                                "Type `done` to end the session."
                            ),
                        }
                    ],
                },
            ],
        )


def main() -> None:
    """Entry point for Slack bot."""
    global _restart_requested
    _restart_requested = False
    asyncio.run(run_slack_bot())
    if _restart_requested:
        sys.exit(42)


if __name__ == "__main__":
    main()
