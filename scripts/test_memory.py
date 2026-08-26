#!/usr/bin/env python3
"""Script to verify conversation memory store/retrieve works."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from cmo_agent.memory.store import ConversationMemory


def main():
    print("Testing Conversation Memory Storage")
    print("=" * 50)

    # Use test database
    db_path = Path("./data/test_memory.db")
    memory = ConversationMemory(db_path=db_path, max_messages=30)

    # Test conversation ID
    conversation_id = "test-conversation-123"

    # Clear any existing data
    memory.clear_conversation(conversation_id)

    print(f"\n1. Adding messages to conversation: {conversation_id}")
    memory.add_message(conversation_id, "user", "Hello! Can you list my workflows?", "ts1")
    memory.add_message(conversation_id, "assistant", "Sure! I found 5 workflows in your n8n instance.", "ts2")
    memory.add_message(conversation_id, "user", "Execute the first one", "ts3")
    memory.add_message(conversation_id, "assistant", "I've executed workflow 'Email Campaign'. Status: success.", "ts4")

    print("   Added 4 messages")

    print("\n2. Retrieving messages:")
    messages = memory.get_messages(conversation_id)
    for i, msg in enumerate(messages, 1):
        print(f"   [{i}] {msg.role}: {msg.text[:50]}...")

    print("\n3. Testing memory toggle:")
    print(f"   Memory enabled (default): {memory.is_memory_enabled(conversation_id)}")
    memory.set_memory_enabled(conversation_id, False)
    print(f"   After disabling: {memory.is_memory_enabled(conversation_id)}")
    memory.set_memory_enabled(conversation_id, True)
    print(f"   After re-enabling: {memory.is_memory_enabled(conversation_id)}")

    print("\n4. Statistics:")
    stats = memory.get_stats()
    print(f"   Total conversations: {stats['conversations']}")
    print(f"   Total messages: {stats['messages']}")
    print(f"   Database path: {stats['db_path']}")
    print(f"   Database size: {stats['db_size_bytes']} bytes")

    print("\n5. Testing limit parameter:")
    limited = memory.get_messages(conversation_id, limit=2)
    print(f"   Retrieved {len(limited)} of 4 messages (limit=2)")
    print(f"   First: {limited[0].text[:30]}...")
    print(f"   Last: {limited[-1].text[:30]}...")

    print("\n6. Clearing conversation:")
    deleted = memory.clear_conversation(conversation_id)
    print(f"   Deleted {deleted} messages")
    remaining = memory.get_messages(conversation_id)
    print(f"   Messages remaining: {len(remaining)}")

    # Cleanup
    memory.close()

    print("\n" + "=" * 50)
    print("All tests passed!")
    print("\nTo clear all memory:")
    print(f"  rm {db_path}")


if __name__ == "__main__":
    main()
