#!/usr/bin/env python3
"""One-time script: clean up duplicate outreach items and backfill content hashes."""
from __future__ import annotations

import asyncio
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))


async def cleanup() -> None:
    from cmo_agent.config import Settings
    from cmo_agent.db.database import Database

    settings = Settings()
    db = Database(db_path=settings.db_path)
    await db.initialize()

    # 1. Backfill missing content_hashes
    rows = await db.fetchall(
        "SELECT id, title, content FROM opportunities "
        "WHERE workspace_id = 'dsdn' "
        "AND (content_hash IS NULL OR content_hash = '')",
        (),
    )
    print(f"Backfilling content_hash for {len(rows)} items...")
    for r in rows:
        title = (r["title"] or "").strip().lower()
        content = (r["content"] or "").strip().lower()
        norm = title + "|" + content
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        await db.execute(
            "UPDATE opportunities SET content_hash = ? WHERE id = ?",
            (h, r["id"]),
        )
    print(f"  Done: {len(rows)} hashes backfilled")

    # 2. Remove title+source duplicates (keep the oldest per combo)
    dupes = await db.fetchall(
        "SELECT title, source, GROUP_CONCAT(id) as ids, COUNT(*) as cnt "
        "FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND outreach_status IS NOT NULL "
        "GROUP BY title, source "
        "HAVING cnt > 1 "
        "ORDER BY cnt DESC",
        (),
    )

    total_deleted = 0
    for r in dupes:
        ids = r["ids"].split(",")
        # Keep the first (oldest), delete the rest
        to_delete = ids[1:]
        for del_id in to_delete:
            await db.execute("DELETE FROM opportunities WHERE id = ?", (del_id,))
            total_deleted += 1
    print(f"Deleted {total_deleted} same-source duplicate rows")

    # 3. Remove cross-platform dupes (same content_hash, different source)
    cross_dupes = await db.fetchall(
        "SELECT content_hash, GROUP_CONCAT(id) as ids, COUNT(*) as cnt "
        "FROM opportunities "
        "WHERE workspace_id = 'dsdn' "
        "AND content_hash IS NOT NULL AND content_hash != '' "
        "GROUP BY content_hash "
        "HAVING cnt > 1",
        (),
    )
    cross_deleted = 0
    for r in cross_dupes:
        ids = r["ids"].split(",")
        to_delete = ids[1:]
        for del_id in to_delete:
            await db.execute("DELETE FROM opportunities WHERE id = ?", (del_id,))
            cross_deleted += 1
    print(f"Deleted {cross_deleted} cross-platform duplicate rows")

    # Final stats
    total = await db.fetchone(
        "SELECT COUNT(*) as cnt FROM opportunities "
        "WHERE workspace_id = 'dsdn' AND outreach_status IS NOT NULL",
        (),
    )
    print(f"\nRemaining outreach items: {total['cnt']}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(cleanup())
