"""SQLite-based conversation memory storage."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

import structlog

logger = structlog.get_logger()

# Default database path
DEFAULT_DB_PATH = Path("./data/slack_memory.db")


@dataclass
class MemoryMessage:
    """A message stored in conversation memory."""

    role: str  # "user" or "assistant"
    text: str
    ts: str  # Slack timestamp or generated timestamp
    created_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "role": self.role,
            "text": self.text,
            "ts": self.ts,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class ConversationMemory:
    """SQLite-backed conversation memory storage.

    Stores conversation history per conversation_id with configurable limits.
    Thread-safe for concurrent access.
    """

    def __init__(
        self,
        db_path: Optional[Path] = None,
        max_messages: int = 6,
    ):
        """Initialize memory storage.

        Args:
            db_path: Path to SQLite database file. Defaults to ./data/slack_memory.db
            max_messages: Maximum messages to store per conversation (default 6)
        """
        self.db_path = db_path or DEFAULT_DB_PATH
        self.max_messages = max_messages
        self._local = threading.local()

        # Ensure data directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        # Initialize database schema
        self._init_db()

        logger.info(
            "memory_initialized",
            db_path=str(self.db_path),
            max_messages=max_messages,
        )

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, "connection") or self._local.connection is None:
            try:
                self._local.connection = sqlite3.connect(
                    str(self.db_path),
                    check_same_thread=False,
                )
                self._local.connection.row_factory = sqlite3.Row
            except sqlite3.OperationalError as e:
                if "readonly" in str(e).lower():
                    logger.error(
                        "memory_db_readonly",
                        path=str(self.db_path),
                        error=str(e),
                    )
                raise
        return self._local.connection

    @contextmanager
    def _cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        """Context manager for database cursor."""
        conn = self._get_connection()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            cursor.close()

    def _init_db(self) -> None:
        """Initialize database schema."""
        with self._cursor() as cursor:
            # Messages table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    conversation_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    ts TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_conversation
                ON messages(conversation_id, created_at DESC)
            """)

            # Conversation settings table (for memory on/off)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversation_settings (
                    conversation_id TEXT PRIMARY KEY,
                    memory_enabled INTEGER DEFAULT 1,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def add_message(
        self,
        conversation_id: str,
        role: str,
        text: str,
        ts: str,
    ) -> None:
        """Add a message to conversation history.

        Args:
            conversation_id: Unique conversation identifier
            role: Message role ("user" or "assistant")
            text: Message text content
            ts: Slack timestamp or generated timestamp
        """
        with self._cursor() as cursor:
            # Insert new message
            cursor.execute(
                """
                INSERT INTO messages (conversation_id, role, text, ts)
                VALUES (?, ?, ?, ?)
                """,
                (conversation_id, role, text, ts),
            )

            # Prune old messages to keep only max_messages
            cursor.execute(
                """
                DELETE FROM messages
                WHERE conversation_id = ?
                AND id NOT IN (
                    SELECT id FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                """,
                (conversation_id, conversation_id, self.max_messages),
            )

        logger.debug(
            "memory_message_added",
            conversation_id=conversation_id,
            role=role,
            ts=ts,
        )

    def get_messages(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
    ) -> List[MemoryMessage]:
        """Get conversation history.

        Args:
            conversation_id: Unique conversation identifier
            limit: Maximum messages to return (default: all up to max_messages)

        Returns:
            List of messages in chronological order (oldest first)
        """
        limit = limit or self.max_messages

        with self._cursor() as cursor:
            # Subquery to get most recent N messages, then order chronologically
            cursor.execute(
                """
                SELECT role, text, ts, created_at
                FROM (
                    SELECT role, text, ts, created_at, id
                    FROM messages
                    WHERE conversation_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                )
                ORDER BY id ASC
                """,
                (conversation_id, limit),
            )
            rows = cursor.fetchall()

        messages = [
            MemoryMessage(
                role=row["role"],
                text=row["text"],
                ts=row["ts"],
                created_at=datetime.fromisoformat(row["created_at"]) if row["created_at"] else None,
            )
            for row in rows
        ]

        logger.debug(
            "memory_messages_retrieved",
            conversation_id=conversation_id,
            count=len(messages),
        )

        return messages

    def clear_conversation(self, conversation_id: str) -> int:
        """Clear all messages for a conversation.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            Number of messages deleted
        """
        with self._cursor() as cursor:
            cursor.execute(
                "DELETE FROM messages WHERE conversation_id = ?",
                (conversation_id,),
            )
            deleted = cursor.rowcount

        logger.info(
            "memory_conversation_cleared",
            conversation_id=conversation_id,
            deleted=deleted,
        )

        return deleted

    def is_memory_enabled(self, conversation_id: str) -> bool:
        """Check if memory is enabled for a conversation.

        Args:
            conversation_id: Unique conversation identifier

        Returns:
            True if memory is enabled (default), False if disabled
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT memory_enabled
                FROM conversation_settings
                WHERE conversation_id = ?
                """,
                (conversation_id,),
            )
            row = cursor.fetchone()

        # Default to enabled if no setting exists
        return row["memory_enabled"] == 1 if row else True

    def set_memory_enabled(self, conversation_id: str, enabled: bool) -> None:
        """Enable or disable memory for a conversation.

        Args:
            conversation_id: Unique conversation identifier
            enabled: Whether memory should be enabled
        """
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO conversation_settings (conversation_id, memory_enabled, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(conversation_id)
                DO UPDATE SET memory_enabled = ?, updated_at = CURRENT_TIMESTAMP
                """,
                (conversation_id, 1 if enabled else 0, 1 if enabled else 0),
            )

        logger.info(
            "memory_setting_updated",
            conversation_id=conversation_id,
            enabled=enabled,
        )

    def get_stats(self) -> dict:
        """Get memory statistics.

        Returns:
            Dict with total conversations, total messages, database size
        """
        with self._cursor() as cursor:
            cursor.execute("SELECT COUNT(DISTINCT conversation_id) FROM messages")
            conversations = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM messages")
            messages = cursor.fetchone()[0]

        db_size = self.db_path.stat().st_size if self.db_path.exists() else 0

        return {
            "conversations": conversations,
            "messages": messages,
            "db_size_bytes": db_size,
            "db_path": str(self.db_path),
        }

    def close(self) -> None:
        """Close database connection."""
        if hasattr(self._local, "connection") and self._local.connection:
            self._local.connection.close()
            self._local.connection = None
