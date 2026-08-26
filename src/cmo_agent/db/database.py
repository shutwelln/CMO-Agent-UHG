"""Async SQLite database wrapper."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, List, Optional, Sequence

import aiosqlite
import structlog

from .schema import (
    MIGRATION_OUTREACH_INDEXES_SQL,
    MIGRATION_OUTREACH_SQL,
    SCHEMA_SQL,
    SEED_WORKSPACE_SQL,
)

logger = structlog.get_logger()

# Retry settings for database lock contention
_MAX_RETRIES = 3
_RETRY_BASE_DELAY = 0.2  # seconds


class Database:
    """Async SQLite database wrapper with schema management."""

    def __init__(self, db_path: str | Path = "./data/cmo_agent.db") -> None:
        self.db_path = Path(db_path)
        self._connection: Optional[aiosqlite.Connection] = None

    async def initialize(self) -> None:
        """Create tables, indexes, and seed data if needed."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = await self._get_connection()

        # Enable WAL mode for better concurrent read performance
        await conn.execute("PRAGMA journal_mode=WAL")
        await conn.execute("PRAGMA busy_timeout=5000")  # Wait up to 5s on lock
        await conn.execute("PRAGMA foreign_keys=ON")

        # Create all tables
        await conn.executescript(SCHEMA_SQL)

        # Auto-seed the default 'uhg' workspace if the workspaces table is empty.
        # Use `cmo setup` or admin operations to add additional workspaces.
        cursor = await conn.execute("SELECT COUNT(*) FROM workspaces")
        row = await cursor.fetchone()
        if row and row[0] == 0:
            await conn.execute(
                SEED_WORKSPACE_SQL,
                ("uhg", "UnitedHealth Group / Optum", "", "uhg.txt"),
            )
            await conn.commit()
            logger.info("workspace_auto_seeded", workspace_id="uhg")

        # Run outreach migration (ALTER TABLE is idempotent — skips if cols exist)
        for stmt in MIGRATION_OUTREACH_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    await conn.execute(stmt)
                except Exception as e:
                    if "duplicate column" in str(e).lower():
                        pass  # Column already exists — expected on subsequent runs
                    else:
                        logger.warning("migration_outreach_skip", stmt=stmt[:60], error=str(e))
        await conn.executescript(MIGRATION_OUTREACH_INDEXES_SQL)

        await conn.commit()
        logger.info("database_initialized", path=str(self.db_path))

    async def _get_connection(self) -> aiosqlite.Connection:
        """Get or create the database connection."""
        if self._connection is None:
            self._connection = await aiosqlite.connect(str(self.db_path))
            self._connection.row_factory = aiosqlite.Row
        return self._connection

    async def execute(self, sql: str, params: Sequence[Any] = ()) -> aiosqlite.Cursor:
        """Execute a SQL statement with retry on database lock."""
        conn = await self._get_connection()
        for attempt in range(_MAX_RETRIES):
            try:
                cursor = await conn.execute(sql, params)
                await conn.commit()
                return cursor
            except Exception as e:
                if "database is locked" in str(e) and attempt < _MAX_RETRIES - 1:
                    delay = _RETRY_BASE_DELAY * (2**attempt)
                    logger.warning(
                        "database_locked_retry",
                        attempt=attempt + 1,
                        delay=delay,
                        sql=sql[:80],
                    )
                    await asyncio.sleep(delay)
                else:
                    raise
        # Should not reach here, but satisfy type checker
        raise RuntimeError("execute exhausted retries")

    async def fetchone(self, sql: str, params: Sequence[Any] = ()) -> Optional[aiosqlite.Row]:
        """Execute and fetch a single row."""
        conn = await self._get_connection()
        cursor = await conn.execute(sql, params)
        return await cursor.fetchone()

    async def fetchall(self, sql: str, params: Sequence[Any] = ()) -> List[aiosqlite.Row]:
        """Execute and fetch all rows."""
        conn = await self._get_connection()
        cursor = await conn.execute(sql, params)
        return await cursor.fetchall()

    async def seed_workspace(
        self,
        workspace_id: str,
        name: str,
        slack_channel: str = "",
        brand_voice_path: str = "",
    ) -> None:
        """Create a workspace row if the workspaces table is empty."""
        conn = await self._get_connection()
        await conn.execute(
            SEED_WORKSPACE_SQL,
            (workspace_id, name, slack_channel, brand_voice_path),
        )
        await conn.commit()
        logger.info("workspace_seeded", workspace_id=workspace_id)

    async def close(self) -> None:
        """Close the database connection."""
        if self._connection:
            await self._connection.close()
            self._connection = None
            logger.info("database_closed")

    async def __aenter__(self) -> "Database":
        await self.initialize()
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.close()
