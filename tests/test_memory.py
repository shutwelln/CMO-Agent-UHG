"""Tests for conversation memory storage."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from cmo_agent.memory.store import ConversationMemory, MemoryMessage


@pytest.fixture
def temp_db():
    """Create a temporary database file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "test_memory.db"


@pytest.fixture
def memory(temp_db):
    """Create a memory store with temporary database."""
    store = ConversationMemory(db_path=temp_db, max_messages=10)
    yield store
    store.close()


class TestConversationMemory:
    """Tests for ConversationMemory class."""

    def test_add_and_get_messages(self, memory):
        """Test adding and retrieving messages."""
        conversation_id = "test-convo-1"

        # Add messages
        memory.add_message(conversation_id, "user", "Hello", "ts1")
        memory.add_message(conversation_id, "assistant", "Hi there!", "ts2")
        memory.add_message(conversation_id, "user", "How are you?", "ts3")

        # Retrieve messages
        messages = memory.get_messages(conversation_id)

        assert len(messages) == 3
        assert messages[0].role == "user"
        assert messages[0].text == "Hello"
        assert messages[1].role == "assistant"
        assert messages[1].text == "Hi there!"
        assert messages[2].role == "user"
        assert messages[2].text == "How are you?"

    def test_message_limit(self, temp_db):
        """Test that messages are pruned to max_messages."""
        memory = ConversationMemory(db_path=temp_db, max_messages=5)
        conversation_id = "test-convo-2"

        # Add 10 messages
        for i in range(10):
            memory.add_message(conversation_id, "user", f"Message {i}", f"ts{i}")

        # Should only have last 5
        messages = memory.get_messages(conversation_id)
        assert len(messages) == 5
        assert messages[0].text == "Message 5"
        assert messages[-1].text == "Message 9"

        memory.close()

    def test_get_messages_with_limit(self, memory):
        """Test retrieving limited messages."""
        conversation_id = "test-convo-3"

        for i in range(8):
            memory.add_message(conversation_id, "user", f"Message {i}", f"ts{i}")

        # Get only 3 most recent
        messages = memory.get_messages(conversation_id, limit=3)
        assert len(messages) == 3
        assert messages[0].text == "Message 5"
        assert messages[-1].text == "Message 7"

    def test_clear_conversation(self, memory):
        """Test clearing a conversation."""
        conversation_id = "test-convo-4"

        memory.add_message(conversation_id, "user", "Hello", "ts1")
        memory.add_message(conversation_id, "assistant", "Hi!", "ts2")

        deleted = memory.clear_conversation(conversation_id)
        assert deleted == 2

        messages = memory.get_messages(conversation_id)
        assert len(messages) == 0

    def test_separate_conversations(self, memory):
        """Test that conversations are isolated."""
        memory.add_message("convo-a", "user", "Message A", "ts1")
        memory.add_message("convo-b", "user", "Message B", "ts2")

        messages_a = memory.get_messages("convo-a")
        messages_b = memory.get_messages("convo-b")

        assert len(messages_a) == 1
        assert len(messages_b) == 1
        assert messages_a[0].text == "Message A"
        assert messages_b[0].text == "Message B"

    def test_memory_enabled_default(self, memory):
        """Test memory is enabled by default."""
        assert memory.is_memory_enabled("new-conversation") is True

    def test_memory_toggle(self, memory):
        """Test enabling/disabling memory."""
        conversation_id = "test-toggle"

        # Disable
        memory.set_memory_enabled(conversation_id, False)
        assert memory.is_memory_enabled(conversation_id) is False

        # Enable
        memory.set_memory_enabled(conversation_id, True)
        assert memory.is_memory_enabled(conversation_id) is True

    def test_get_stats(self, memory):
        """Test getting statistics."""
        memory.add_message("convo-1", "user", "Hello", "ts1")
        memory.add_message("convo-1", "assistant", "Hi", "ts2")
        memory.add_message("convo-2", "user", "Bye", "ts3")

        stats = memory.get_stats()
        assert stats["conversations"] == 2
        assert stats["messages"] == 3
        assert "db_path" in stats

    def test_persistence(self, temp_db):
        """Test that data persists across instances."""
        conversation_id = "persist-test"

        # Write with first instance
        memory1 = ConversationMemory(db_path=temp_db)
        memory1.add_message(conversation_id, "user", "Persisted message", "ts1")
        memory1.close()

        # Read with second instance
        memory2 = ConversationMemory(db_path=temp_db)
        messages = memory2.get_messages(conversation_id)
        assert len(messages) == 1
        assert messages[0].text == "Persisted message"
        memory2.close()

    def test_message_to_dict(self):
        """Test MemoryMessage.to_dict()."""
        msg = MemoryMessage(role="user", text="Hello", ts="123.456")
        d = msg.to_dict()

        assert d["role"] == "user"
        assert d["text"] == "Hello"
        assert d["ts"] == "123.456"


class TestConversationIdComputation:
    """Tests for conversation ID computation logic."""

    def test_dm_conversation_id(self):
        """Test DM uses channel as conversation_id."""
        from cmo_agent.slack.bot import get_conversation_id

        event = {
            "channel": "D12345",
            "channel_type": "im",
            "ts": "1234567890.123456",
        }
        assert get_conversation_id(event) == "D12345"

    def test_thread_conversation_id(self):
        """Test thread uses channel:thread_ts."""
        from cmo_agent.slack.bot import get_conversation_id

        event = {
            "channel": "C12345",
            "channel_type": "channel",
            "thread_ts": "1111111111.111111",
            "ts": "1234567890.123456",
        }
        assert get_conversation_id(event) == "C12345:1111111111.111111"

    def test_new_message_conversation_id(self):
        """Test new message uses channel:event_ts."""
        from cmo_agent.slack.bot import get_conversation_id

        event = {
            "channel": "C12345",
            "channel_type": "channel",
            "ts": "1234567890.123456",
        }
        assert get_conversation_id(event) == "C12345:1234567890.123456"
