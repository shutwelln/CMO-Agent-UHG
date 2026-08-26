"""Slack-based approval workflow for content drafts."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.models import DraftStatus
from ..db.repositories import DraftRepo, WorkspaceRepo

logger = structlog.get_logger()


class ApprovalWorkflow:
    """Manages the approve/edit/reject flow for drafts via Slack interactive messages."""

    def __init__(self, db: Database, slack_client: Any = None) -> None:
        self.db = db
        self.slack = slack_client
        self._drafts = DraftRepo(db)
        self._workspaces = WorkspaceRepo(db)

    async def send_for_approval(self, draft_id: str) -> Optional[str]:
        """Send a draft to Slack for approval. Returns the message timestamp."""
        draft = await self._drafts.get(draft_id)
        if not draft:
            logger.error("approval_draft_not_found", draft_id=draft_id)
            return None

        ws = await self._workspaces.get(draft.workspace_id)
        channel = ws.slack_channel if ws else None
        if not channel or not self.slack:
            logger.warning(
                "approval_no_channel",
                draft_id=draft_id,
                workspace_id=draft.workspace_id,
            )
            return None

        blocks = self._build_approval_blocks(draft_id, draft)
        try:
            result = await self.slack.chat_postMessage(
                channel=channel,
                text=f"New {draft.content_type} draft for review: {draft.title or 'Untitled'}",
                blocks=blocks,
            )
            message_ts = result["ts"]
            thread_ts = result.get("thread_ts", message_ts)

            await self._drafts.set_slack_refs(draft_id, thread_ts, message_ts)
            logger.info(
                "approval_sent",
                draft_id=draft_id,
                channel=channel,
                message_ts=message_ts,
            )
            return message_ts

        except Exception as e:
            logger.error("approval_send_failed", draft_id=draft_id, error=str(e))
            return None

    async def handle_approve(self, draft_id: str, user_id: str) -> None:
        """Mark a draft as approved."""
        await self._drafts.update_status(draft_id, DraftStatus.APPROVED)
        logger.info("draft_approved", draft_id=draft_id, user_id=user_id)

        if self.slack:
            draft = await self._drafts.get(draft_id)
            if draft and draft.slack_message_ts:
                ws = await self._workspaces.get(draft.workspace_id)
                channel = ws.slack_channel if ws else None
                if channel:
                    await self.slack.chat_update(
                        channel=channel,
                        ts=draft.slack_message_ts,
                        text=f"Approved by <@{user_id}>: {draft.title or 'Untitled'}",
                        blocks=[],  # Clear interactive buttons
                    )

    async def handle_request_edit(self, draft_id: str, user_id: str) -> None:
        """Request edits on a draft (user provides feedback in thread)."""
        logger.info("draft_edit_requested", draft_id=draft_id, user_id=user_id)

        if self.slack:
            draft = await self._drafts.get(draft_id)
            if draft and draft.slack_thread_ts:
                ws = await self._workspaces.get(draft.workspace_id)
                channel = ws.slack_channel if ws else None
                if channel:
                    await self.slack.chat_postMessage(
                        channel=channel,
                        thread_ts=draft.slack_thread_ts,
                        text=f"<@{user_id}> requested edits. Please reply in this thread with your feedback, and I'll revise the draft.",
                    )

    async def handle_reject(
        self, draft_id: str, user_id: str, reason: Optional[str] = None
    ) -> None:
        """Reject a draft."""
        await self._drafts.update_status(draft_id, DraftStatus.REJECTED, reason)
        logger.info("draft_rejected", draft_id=draft_id, user_id=user_id, reason=reason)

        if self.slack:
            draft = await self._drafts.get(draft_id)
            if draft and draft.slack_message_ts:
                ws = await self._workspaces.get(draft.workspace_id)
                channel = ws.slack_channel if ws else None
                if channel:
                    reason_text = f" Reason: {reason}" if reason else ""
                    await self.slack.chat_update(
                        channel=channel,
                        ts=draft.slack_message_ts,
                        text=f"Rejected by <@{user_id}>: {draft.title or 'Untitled'}.{reason_text}",
                        blocks=[],
                    )

    async def check_expiring_drafts(self) -> List[str]:
        """Find pending drafts linked to expiring opportunities. Returns draft IDs."""
        # This would query drafts with pending status whose linked opportunities
        # have expires_at within 24 hours. Simplified for now.
        rows = await self.db.fetchall(
            """SELECT d.id FROM drafts d
            JOIN opportunities o ON d.opportunity_ids LIKE '%' || o.id || '%'
            WHERE d.status = 'pending'
            AND o.expires_at IS NOT NULL
            AND o.expires_at <= datetime('now', '+24 hours')""",
        )
        return [r[0] for r in rows]

    def _build_approval_blocks(self, draft_id: str, draft: Any) -> List[Dict[str, Any]]:
        """Build Slack Block Kit blocks for an approval message."""
        body_preview = (draft.body or "")[:1500]
        verify_section = ""
        if draft.verify_flags:
            flags = "\n".join(f"  - {f}" for f in draft.verify_flags[:10])
            verify_section = f"\n\n*Claims to verify:*\n{flags}"

        return [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"New {draft.content_type}: {draft.title or 'Untitled'}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Workspace:* {draft.workspace_id}\n*Type:* {draft.content_type}{verify_section}",
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": body_preview,
                },
            },
            {"type": "divider"},
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Approve"},
                        "style": "primary",
                        "action_id": "approve_draft",
                        "value": draft_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Request Edit"},
                        "action_id": "edit_draft",
                        "value": draft_id,
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Reject"},
                        "style": "danger",
                        "action_id": "reject_draft",
                        "value": draft_id,
                    },
                ],
            },
        ]
