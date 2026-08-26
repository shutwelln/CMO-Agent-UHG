"""Data access layer for all database entities."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import structlog

from .database import Database
from .models import (
    BuildLogEntry,
    ConfigEntry,
    Draft,
    DraftStatus,
    HealLogEntry,
    MediaAsset,
    Opportunity,
    OpportunityStatus,
    OutreachStatus,
    ScanLogEntry,
    Source,
    Workspace,
)

logger = structlog.get_logger()


class WorkspaceRepo:
    """Repository for workspace operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, workspace_id: str) -> Optional[Workspace]:
        row = await self.db.fetchone("SELECT * FROM workspaces WHERE id = ?", (workspace_id,))
        return Workspace(**dict(row)) if row else None

    async def get_default(self) -> Optional[Workspace]:
        row = await self.db.fetchone("SELECT * FROM workspaces WHERE is_default = 1 LIMIT 1")
        return Workspace(**dict(row)) if row else None

    async def list_all(self) -> List[Workspace]:
        rows = await self.db.fetchall("SELECT * FROM workspaces ORDER BY name")
        return [Workspace(**dict(r)) for r in rows]

    async def create(
        self,
        workspace_id: str,
        name: str,
        workspace_type: str = "owned_brand",
        slack_channel: Optional[str] = None,
        brand_voice_path: Optional[str] = None,
        is_default: bool = False,
    ) -> Workspace:
        await self.db.execute(
            """INSERT INTO workspaces (id, name, type, slack_channel, brand_voice_path, is_default)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (
                workspace_id,
                name,
                workspace_type,
                slack_channel,
                brand_voice_path,
                1 if is_default else 0,
            ),
        )
        ws = await self.get(workspace_id)
        assert ws is not None
        return ws

    async def update(self, workspace_id: str, **kwargs: Any) -> Optional[Workspace]:
        sets = []
        params: list[Any] = []
        for key, val in kwargs.items():
            if key == "is_default":
                val = 1 if val else 0
            sets.append(f"{key} = ?")
            params.append(val)
        sets.append("updated_at = datetime('now')")
        params.append(workspace_id)
        await self.db.execute(
            f"UPDATE workspaces SET {', '.join(sets)} WHERE id = ?", tuple(params)
        )
        return await self.get(workspace_id)


class OpportunityRepo:
    """Repository for opportunity operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        workspace_id: str,
        source: str,
        title: str,
        content: Optional[str] = None,
        source_url: Optional[str] = None,
        source_id: Optional[str] = None,
        score: int = 0,
        score_breakdown: Optional[Dict[str, Any]] = None,
        category: Optional[str] = None,
        subreddit: Optional[str] = None,
        expires_at: Optional[str] = None,
        content_hash: Optional[str] = None,
        platform_post_type: Optional[str] = None,
        posted_at: Optional[str] = None,
    ) -> Opportunity:
        opp_id = str(uuid4())
        await self.db.execute(
            """INSERT INTO opportunities
            (id, workspace_id, source, source_url, source_id, title, content,
             score, score_breakdown, category, subreddit, expires_at,
             content_hash, platform_post_type, posted_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                opp_id,
                workspace_id,
                source,
                source_url,
                source_id,
                title,
                content,
                score,
                json.dumps(score_breakdown) if score_breakdown else None,
                category,
                subreddit,
                expires_at,
                content_hash,
                platform_post_type,
                posted_at,
            ),
        )
        opp = await self.get(opp_id)
        assert opp is not None
        return opp

    async def get(self, opportunity_id: str) -> Optional[Opportunity]:
        row = await self.db.fetchone("SELECT * FROM opportunities WHERE id = ?", (opportunity_id,))
        return Opportunity(**dict(row)) if row else None

    async def list_by_workspace(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 50,
    ) -> List[Opportunity]:
        sql = "SELECT * FROM opportunities WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        if source:
            sql += " AND source = ?"
            params.append(source)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetchall(sql, tuple(params))
        return [Opportunity(**dict(r)) for r in rows]

    async def list_recent(
        self,
        workspace_id: Optional[str] = None,
        days: int = 14,
        limit: int = 50,
    ) -> List[Opportunity]:
        """List opportunities created within the last N days."""
        if workspace_id:
            sql = (
                "SELECT * FROM opportunities WHERE workspace_id = ?"
                " AND created_at >= datetime('now', ?)"
                " ORDER BY created_at DESC LIMIT ?"
            )
            params: tuple[Any, ...] = (workspace_id, f"-{days} days", limit)
        else:
            sql = (
                "SELECT * FROM opportunities"
                " WHERE created_at >= datetime('now', ?)"
                " ORDER BY created_at DESC LIMIT ?"
            )
            params = (f"-{days} days", limit)
        rows = await self.db.fetchall(sql, params)
        return [Opportunity(**dict(r)) for r in rows]

    async def update_status(self, opportunity_id: str, status: OpportunityStatus) -> None:
        await self.db.execute(
            "UPDATE opportunities SET status = ? WHERE id = ?",
            (status.value, opportunity_id),
        )

    async def exists_by_source_id(self, source: str, source_id: str) -> bool:
        row = await self.db.fetchone(
            "SELECT 1 FROM opportunities WHERE source = ? AND source_id = ?",
            (source, source_id),
        )
        return row is not None

    # ── Outreach workflow methods ─────────────────────────────────────

    async def exists_by_content_hash(self, content_hash: str) -> bool:
        """Check cross-platform dedup by content hash."""
        row = await self.db.fetchone(
            "SELECT 1 FROM opportunities WHERE content_hash = ?",
            (content_hash,),
        )
        return row is not None

    async def claim(self, opportunity_id: str, claimed_by: str) -> None:
        """Claim a post for outreach response."""
        await self.db.execute(
            """UPDATE opportunities
            SET claimed_by = ?, claimed_at = datetime('now'),
                outreach_status = ?
            WHERE id = ?""",
            (claimed_by, OutreachStatus.CLAIMED.value, opportunity_id),
        )

    async def set_draft_reply(
        self,
        opportunity_id: str,
        draft_reply: str,
        canned_response_used: Optional[str] = None,
    ) -> None:
        """Store a generated draft reply. Does NOT change outreach_status (stays 'new')."""
        await self.db.execute(
            """UPDATE opportunities
            SET draft_reply = ?, canned_response_used = ?
            WHERE id = ?""",
            (
                draft_reply,
                canned_response_used,
                opportunity_id,
            ),
        )

    async def mark_responded(
        self,
        opportunity_id: str,
        response_url: Optional[str] = None,
        response_notes: Optional[str] = None,
    ) -> None:
        """Mark a post as responded to."""
        await self.db.execute(
            """UPDATE opportunities
            SET response_url = ?, response_notes = ?,
                outreach_status = ?
            WHERE id = ?""",
            (response_url, response_notes, OutreachStatus.RESPONDED.value, opportunity_id),
        )

    async def record_outcome(self, opportunity_id: str, outcome: str) -> None:
        """Record the outcome after outreach response."""
        await self.db.execute(
            "UPDATE opportunities SET outreach_outcome = ? WHERE id = ?",
            (outcome, opportunity_id),
        )

    async def skip_outreach(self, opportunity_id: str) -> None:
        """Mark a post as skipped."""
        await self.db.execute(
            "UPDATE opportunities SET outreach_status = ? WHERE id = ?",
            (OutreachStatus.SKIPPED.value, opportunity_id),
        )

    async def list_outreach_queue(
        self,
        workspace_id: str,
        outreach_status: Optional[str] = None,
        limit: int = 100,
    ) -> List[Opportunity]:
        """List outreach queue items, optionally filtered by status."""
        sql = "SELECT * FROM opportunities WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if outreach_status:
            sql += " AND outreach_status = ?"
            params.append(outreach_status)
        else:
            # Default: only outreach-relevant items (not null status)
            sql += " AND outreach_status IS NOT NULL"
        sql += " ORDER BY score DESC, created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetchall(sql, tuple(params))
        return [Opportunity(**dict(r)) for r in rows]

    async def get_outreach_stats(self, workspace_id: str) -> Dict[str, Any]:
        """Aggregate outreach stats per team member."""
        rows = await self.db.fetchall(
            """SELECT
                claimed_by,
                COUNT(*) as total,
                SUM(CASE WHEN outreach_status = 'responded' THEN 1 ELSE 0 END) as responded,
                SUM(CASE WHEN outreach_outcome = 'connected' THEN 1 ELSE 0 END) as connected,
                SUM(CASE WHEN outreach_outcome = 'no_response' THEN 1 ELSE 0 END) as no_response,
                SUM(CASE WHEN outreach_outcome = 'declined' THEN 1 ELSE 0 END) as declined
            FROM opportunities
            WHERE workspace_id = ? AND claimed_by IS NOT NULL
            GROUP BY claimed_by""",
            (workspace_id,),
        )
        stats: Dict[str, Any] = {}
        for row in rows:
            d = dict(row)
            member = d.pop("claimed_by", "unknown")
            stats[member] = d
        return stats

    async def archive_old_outreach(
        self,
        workspace_id: str,
        responded_days: int = 30,
    ) -> int:
        """Move old responded items to dismissed status. Returns count archived.

        Responded items archive after 30 days. Skipped items are archived
        immediately via the Google Sheet archive_skipped_rows() flow.
        """
        cursor = await self.db.execute(
            """UPDATE opportunities SET status = ?
            WHERE workspace_id = ? AND outreach_status = ?
              AND created_at < datetime('now', ?)""",
            (
                OpportunityStatus.DISMISSED.value,
                workspace_id,
                OutreachStatus.RESPONDED.value,
                f"-{responded_days} days",
            ),
        )
        return cursor.rowcount or 0


class DraftRepo:
    """Repository for draft operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        workspace_id: str,
        content_type: str,
        body: str,
        title: Optional[str] = None,
        verify_flags: Optional[List[str]] = None,
        opportunity_ids: Optional[List[str]] = None,
    ) -> Draft:
        draft_id = str(uuid4())
        await self.db.execute(
            """INSERT INTO drafts
            (id, workspace_id, content_type, title, body, verify_flags, opportunity_ids)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                draft_id,
                workspace_id,
                content_type,
                title,
                body,
                json.dumps(verify_flags or []),
                json.dumps(opportunity_ids or []),
            ),
        )
        draft = await self.get(draft_id)
        assert draft is not None
        return draft

    async def get(self, draft_id: str) -> Optional[Draft]:
        row = await self.db.fetchone("SELECT * FROM drafts WHERE id = ?", (draft_id,))
        return Draft(**dict(row)) if row else None

    async def list_by_workspace(
        self,
        workspace_id: str,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Draft]:
        sql = "SELECT * FROM drafts WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if status:
            sql += " AND status = ?"
            params.append(status)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetchall(sql, tuple(params))
        return [Draft(**dict(r)) for r in rows]

    async def update_status(
        self,
        draft_id: str,
        status: DraftStatus,
        rejection_reason: Optional[str] = None,
    ) -> None:
        if status == DraftStatus.APPROVED:
            await self.db.execute(
                "UPDATE drafts SET status = ?, approved_at = datetime('now') WHERE id = ?",
                (status.value, draft_id),
            )
        elif status == DraftStatus.REJECTED:
            await self.db.execute(
                "UPDATE drafts SET status = ?, rejection_reason = ? WHERE id = ?",
                (status.value, rejection_reason, draft_id),
            )
        else:
            await self.db.execute(
                "UPDATE drafts SET status = ? WHERE id = ?",
                (status.value, draft_id),
            )

    async def update_body(
        self, draft_id: str, body: str, verify_flags: Optional[List[str]] = None
    ) -> None:
        await self.db.execute(
            "UPDATE drafts SET body = ?, verify_flags = ?, revised_at = datetime('now'), status = ? WHERE id = ?",
            (body, json.dumps(verify_flags or []), DraftStatus.REVISED.value, draft_id),
        )

    async def list_recent(
        self,
        workspace_id: Optional[str] = None,
        days: int = 14,
        limit: int = 50,
        content_type: Optional[str] = None,
    ) -> List[Draft]:
        """List drafts created within the last N days.

        Args:
            workspace_id: Filter by workspace (optional).
            days: How many days back to look.
            limit: Max rows to return.
            content_type: Filter by content_type (e.g. "blog").
        """
        conditions = ["created_at >= datetime('now', ?)"]
        params_list: list[Any] = [f"-{days} days"]
        if workspace_id:
            conditions.insert(0, "workspace_id = ?")
            params_list.insert(0, workspace_id)
        if content_type:
            conditions.append("content_type = ?")
            params_list.append(content_type)
        where = " AND ".join(conditions)
        sql = f"SELECT * FROM drafts WHERE {where} ORDER BY created_at DESC LIMIT ?"
        params_list.append(limit)
        rows = await self.db.fetchall(sql, tuple(params_list))
        return [Draft(**dict(r)) for r in rows]

    async def set_slack_refs(self, draft_id: str, thread_ts: str, message_ts: str) -> None:
        await self.db.execute(
            "UPDATE drafts SET slack_thread_ts = ?, slack_message_ts = ? WHERE id = ?",
            (thread_ts, message_ts, draft_id),
        )


class SourceRepo:
    """Repository for monitoring source operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        workspace_id: str,
        source_type: str,
        url: Optional[str] = None,
        name: Optional[str] = None,
        keywords: Optional[List[str]] = None,
    ) -> Source:
        source_id = str(uuid4())
        await self.db.execute(
            """INSERT INTO sources (id, workspace_id, type, url, name, keywords)
            VALUES (?, ?, ?, ?, ?, ?)""",
            (source_id, workspace_id, source_type, url, name, json.dumps(keywords or [])),
        )
        src = await self.get(source_id)
        assert src is not None
        return src

    async def get(self, source_id: str) -> Optional[Source]:
        row = await self.db.fetchone("SELECT * FROM sources WHERE id = ?", (source_id,))
        return Source(**dict(row)) if row else None

    async def list_by_workspace(
        self,
        workspace_id: str,
        source_type: Optional[str] = None,
        active_only: bool = True,
    ) -> List[Source]:
        sql = "SELECT * FROM sources WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if source_type:
            sql += " AND type = ?"
            params.append(source_type)
        if active_only:
            sql += " AND active = 1"
        sql += " ORDER BY name"
        rows = await self.db.fetchall(sql, tuple(params))
        return [Source(**dict(r)) for r in rows]

    async def update_last_checked(self, source_id: str, last_item_at: Optional[str] = None) -> None:
        if last_item_at:
            await self.db.execute(
                "UPDATE sources SET last_checked_at = datetime('now'), last_item_at = ? WHERE id = ?",
                (last_item_at, source_id),
            )
        else:
            await self.db.execute(
                "UPDATE sources SET last_checked_at = datetime('now') WHERE id = ?",
                (source_id,),
            )

    async def delete(self, source_id: str) -> None:
        await self.db.execute("DELETE FROM sources WHERE id = ?", (source_id,))

    async def set_active(self, source_id: str, active: bool) -> None:
        await self.db.execute(
            "UPDATE sources SET active = ? WHERE id = ?",
            (1 if active else 0, source_id),
        )


class ConfigRepo:
    """Repository for per-workspace configuration."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def get(self, workspace_id: str, key: str) -> Optional[str]:
        row = await self.db.fetchone(
            "SELECT value FROM config WHERE workspace_id = ? AND key = ?",
            (workspace_id, key),
        )
        return row[0] if row else None

    async def set(self, workspace_id: str, key: str, value: str) -> None:
        await self.db.execute(
            """INSERT INTO config (workspace_id, key, value)
            VALUES (?, ?, ?)
            ON CONFLICT(workspace_id, key)
            DO UPDATE SET value = ?, updated_at = datetime('now')""",
            (workspace_id, key, value, value),
        )

    async def get_all(self, workspace_id: str) -> List[ConfigEntry]:
        rows = await self.db.fetchall(
            "SELECT * FROM config WHERE workspace_id = ? ORDER BY key",
            (workspace_id,),
        )
        return [ConfigEntry(**dict(r)) for r in rows]

    async def delete(self, workspace_id: str, key: str) -> None:
        await self.db.execute(
            "DELETE FROM config WHERE workspace_id = ? AND key = ?",
            (workspace_id, key),
        )


class ScanLogRepo:
    """Repository for scan history."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        agent_id: str,
        workspace_id: str,
        source_type: str,
        started_at: Optional[str] = None,
    ) -> int:
        started = started_at or datetime.utcnow().isoformat()
        cursor = await self.db.execute(
            """INSERT INTO scan_log (agent_id, workspace_id, source_type, started_at)
            VALUES (?, ?, ?, ?)""",
            (agent_id, workspace_id, source_type, started),
        )
        return cursor.lastrowid or 0

    async def complete(
        self,
        log_id: int,
        items_scanned: int,
        items_found: int,
        errors: Optional[List[str]] = None,
    ) -> None:
        await self.db.execute(
            """UPDATE scan_log
            SET items_scanned = ?, items_found = ?, errors = ?,
                completed_at = datetime('now')
            WHERE id = ?""",
            (items_scanned, items_found, json.dumps(errors) if errors else None, log_id),
        )

    async def get_latest(
        self, workspace_id: str, source_type: Optional[str] = None, limit: int = 10
    ) -> List[ScanLogEntry]:
        sql = "SELECT * FROM scan_log WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if source_type:
            sql += " AND source_type = ?"
            params.append(source_type)
        sql += " ORDER BY started_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetchall(sql, tuple(params))
        return [ScanLogEntry(**dict(r)) for r in rows]


class MediaAssetRepo:
    """Repository for media asset operations."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        asset_id: str,
        workspace_id: str,
        media_type: str,
        filename: str,
        storage_path: str,
        source_agent: str,
        cdn_url: Optional[str] = None,
        local_path: Optional[str] = None,
        prompt: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        file_size_bytes: Optional[int] = None,
        content_type: Optional[str] = None,
        draft_id: Optional[str] = None,
    ) -> MediaAsset:
        await self.db.execute(
            """INSERT INTO media_assets
            (id, workspace_id, media_type, filename, storage_path, cdn_url,
             local_path, source_agent, prompt, metadata, file_size_bytes,
             content_type, draft_id)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                asset_id,
                workspace_id,
                media_type,
                filename,
                storage_path,
                cdn_url,
                local_path,
                source_agent,
                prompt,
                json.dumps(metadata) if metadata else None,
                file_size_bytes,
                content_type,
                draft_id,
            ),
        )
        asset = await self.get(asset_id)
        assert asset is not None
        return asset

    async def get(self, asset_id: str) -> Optional[MediaAsset]:
        row = await self.db.fetchone("SELECT * FROM media_assets WHERE id = ?", (asset_id,))
        return MediaAsset(**dict(row)) if row else None

    async def list_by_workspace(
        self,
        workspace_id: str,
        media_type: Optional[str] = None,
        limit: int = 50,
    ) -> List[MediaAsset]:
        sql = "SELECT * FROM media_assets WHERE workspace_id = ?"
        params: list[Any] = [workspace_id]
        if media_type:
            sql += " AND media_type = ?"
            params.append(media_type)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetchall(sql, tuple(params))
        return [MediaAsset(**dict(r)) for r in rows]

    async def list_recent(
        self,
        workspace_id: Optional[str] = None,
        days: int = 14,
        limit: int = 50,
    ) -> List[MediaAsset]:
        """List media assets created within the last N days."""
        if workspace_id:
            sql = (
                "SELECT * FROM media_assets WHERE workspace_id = ?"
                " AND created_at >= datetime('now', ?)"
                " ORDER BY created_at DESC LIMIT ?"
            )
            params: tuple[Any, ...] = (workspace_id, f"-{days} days", limit)
        else:
            sql = (
                "SELECT * FROM media_assets"
                " WHERE created_at >= datetime('now', ?)"
                " ORDER BY created_at DESC LIMIT ?"
            )
            params = (f"-{days} days", limit)
        rows = await self.db.fetchall(sql, params)
        return [MediaAsset(**dict(r)) for r in rows]

    async def list_by_draft(self, draft_id: str) -> List[MediaAsset]:
        rows = await self.db.fetchall(
            "SELECT * FROM media_assets WHERE draft_id = ? ORDER BY created_at DESC",
            (draft_id,),
        )
        return [MediaAsset(**dict(r)) for r in rows]

    async def search(
        self,
        workspace_id: str,
        query: str,
        limit: int = 50,
    ) -> List[MediaAsset]:
        pattern = f"%{query}%"
        rows = await self.db.fetchall(
            """SELECT * FROM media_assets
            WHERE workspace_id = ?
              AND (prompt LIKE ? OR source_agent LIKE ? OR filename LIKE ?)
            ORDER BY created_at DESC LIMIT ?""",
            (workspace_id, pattern, pattern, pattern, limit),
        )
        return [MediaAsset(**dict(r)) for r in rows]

    async def set_draft_id(self, asset_id: str, draft_id: str) -> None:
        await self.db.execute(
            "UPDATE media_assets SET draft_id = ? WHERE id = ?",
            (draft_id, asset_id),
        )

    async def delete(self, asset_id: str) -> None:
        await self.db.execute("DELETE FROM media_assets WHERE id = ?", (asset_id,))


class HealLogRepo:
    """Repository for workflow healing history."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        workflow_id: str,
        action: str,
        status: str,
        workflow_name: Optional[str] = None,
        issues_found: Optional[List[Dict[str, Any]]] = None,
        fixes_applied: Optional[List[Dict[str, Any]]] = None,
        snapshot_before: Optional[Dict[str, Any]] = None,
        snapshot_after: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
    ) -> int:
        cursor = await self.db.execute(
            """INSERT INTO heal_log
            (workflow_id, workflow_name, action, status, issues_found,
             fixes_applied, snapshot_before, snapshot_after, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow_id,
                workflow_name,
                action,
                status,
                json.dumps(issues_found) if issues_found else None,
                json.dumps(fixes_applied) if fixes_applied else None,
                json.dumps(snapshot_before) if snapshot_before else None,
                json.dumps(snapshot_after) if snapshot_after else None,
                error_message,
            ),
        )
        return cursor.lastrowid or 0

    async def get(self, log_id: int) -> Optional[HealLogEntry]:
        row = await self.db.fetchone("SELECT * FROM heal_log WHERE id = ?", (log_id,))
        return HealLogEntry(**dict(row)) if row else None

    async def get_latest(
        self,
        workflow_id: str,
        action: Optional[str] = None,
        limit: int = 10,
    ) -> List[HealLogEntry]:
        sql = "SELECT * FROM heal_log WHERE workflow_id = ?"
        params: list[Any] = [workflow_id]
        if action:
            sql += " AND action = ?"
            params.append(action)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = await self.db.fetchall(sql, tuple(params))
        return [HealLogEntry(**dict(r)) for r in rows]

    async def get_recent_all(self, limit: int = 50) -> List[HealLogEntry]:
        rows = await self.db.fetchall(
            "SELECT * FROM heal_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [HealLogEntry(**dict(r)) for r in rows]


class SkippedIdeaRepo:
    """Repository for skipped ideas (excluded from future generation)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(
        self,
        idea_title: str,
        idea_type: str,
        workspace_id: Optional[str] = None,
        skipped_by: Optional[str] = None,
    ) -> int:
        cursor = await self.db.execute(
            """INSERT INTO skipped_ideas (idea_title, idea_type, workspace_id, skipped_by)
            VALUES (?, ?, ?, ?)""",
            (idea_title, idea_type, workspace_id, skipped_by),
        )
        return cursor.lastrowid or 0

    async def list_titles(self, idea_type: str) -> List[str]:
        """Return all skipped idea titles for a given type (e.g. "growth")."""
        rows = await self.db.fetchall(
            "SELECT idea_title FROM skipped_ideas WHERE idea_type = ? ORDER BY created_at DESC",
            (idea_type,),
        )
        return [row[0] for row in rows]


class ApprovedIdeaRepo:
    """Repository for approved ideas (excluded from future generation, tracked for launch)."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def add(
        self,
        idea_title: str,
        idea_type: str,
        workspace_id: Optional[str] = None,
        approved_by: Optional[str] = None,
    ) -> int:
        cursor = await self.db.execute(
            """INSERT INTO approved_ideas (idea_title, idea_type, workspace_id, approved_by)
            VALUES (?, ?, ?, ?)""",
            (idea_title, idea_type, workspace_id, approved_by),
        )
        return cursor.lastrowid or 0

    async def list_titles(self, idea_type: str) -> List[str]:
        """Return all approved idea titles for a given type (e.g. "growth")."""
        rows = await self.db.fetchall(
            "SELECT idea_title FROM approved_ideas WHERE idea_type = ? ORDER BY created_at DESC",
            (idea_type,),
        )
        return [row[0] for row in rows]

    async def list_stale(self, idea_type: str, stale_days: int = 7) -> List[Dict[str, Any]]:
        """Return approved-but-not-launched ideas older than N days."""
        rows = await self.db.fetchall(
            """SELECT id, idea_title, idea_type, workspace_id, approved_by, created_at
            FROM approved_ideas
            WHERE idea_type = ? AND status = 'approved'
              AND created_at <= datetime('now', ?)
            ORDER BY created_at ASC""",
            (idea_type, f"-{stale_days} days"),
        )
        return [dict(row) for row in rows]

    async def mark_launched(self, idea_id: int) -> None:
        """Set status to 'launched' and record launched_at timestamp."""
        await self.db.execute(
            "UPDATE approved_ideas SET status = 'launched', launched_at = datetime('now') WHERE id = ?",
            (idea_id,),
        )


class BuildLogRepo:
    """Repository for workflow build history."""

    def __init__(self, db: Database) -> None:
        self.db = db

    async def create(
        self,
        workflow_name: str,
        request: str,
        status: str,
        workflow_id: Optional[str] = None,
        node_count: int = 0,
        nodes_summary: Optional[List[Dict[str, Any]]] = None,
        connections_summary: Optional[List[str]] = None,
        credential_warnings: Optional[List[str]] = None,
        workflow_url: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> int:
        cursor = await self.db.execute(
            """INSERT INTO build_log
            (workflow_id, workflow_name, request, status, node_count,
             nodes_summary, connections_summary, credential_warnings,
             workflow_url, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                workflow_id,
                workflow_name,
                request,
                status,
                node_count,
                json.dumps(nodes_summary) if nodes_summary else None,
                json.dumps(connections_summary) if connections_summary else None,
                json.dumps(credential_warnings) if credential_warnings else None,
                workflow_url,
                error_message,
            ),
        )
        return cursor.lastrowid or 0

    async def get(self, log_id: int) -> Optional[BuildLogEntry]:
        row = await self.db.fetchone("SELECT * FROM build_log WHERE id = ?", (log_id,))
        return BuildLogEntry(**dict(row)) if row else None

    async def get_recent(self, limit: int = 20) -> List[BuildLogEntry]:
        rows = await self.db.fetchall(
            "SELECT * FROM build_log ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return [BuildLogEntry(**dict(r)) for r in rows]
