#!/usr/bin/env python3
"""
Backfill email_hash on existing subscribers.

Computes SHA-256 hex hash of each subscriber's email (lowercased, trimmed)
and PATCHes the row. This matches the sw_user_id stored in localStorage
by the Cloudflare Worker DataLayer.

One-time script — safe to re-run (idempotent, skips already-hashed rows).

Usage:
  source .venv/bin/activate
  python scripts/backfill_subscriber_hashes.py
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import sys

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://lmtrgkmgfermqatopkfp.supabase.co")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")


def compute_hash(email: str) -> str:
    """SHA-256 hex hash of lowercased, trimmed email — matches DataLayer hashEmail()."""
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


async def main() -> None:
    import httpx

    if not SUPABASE_ANON_KEY:
        print("ERROR: SUPABASE_ANON_KEY not set in environment")
        sys.exit(1)

    headers = {
        "apikey": SUPABASE_ANON_KEY,
        "Authorization": f"Bearer {SUPABASE_ANON_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=30) as client:
        # Fetch subscribers without email_hash
        resp = await client.get(
            f"{SUPABASE_URL}/rest/v1/subscribers",
            params={"email_hash": "is.null", "select": "id,email"},
            headers=headers,
        )
        resp.raise_for_status()
        rows = resp.json()

        if not rows:
            print("All subscribers already have email_hash. Nothing to do.")
            return

        print(f"Found {len(rows)} subscribers without email_hash")

        for row in rows:
            email = row["email"]
            email_hash = compute_hash(email)

            patch_resp = await client.patch(
                f"{SUPABASE_URL}/rest/v1/subscribers",
                params={"id": f"eq.{row['id']}"},
                headers={**headers, "Prefer": "return=minimal"},
                json={"email_hash": email_hash},
            )
            patch_resp.raise_for_status()
            print(f"  {email} -> {email_hash[:16]}...")

    print(f"\nDone. Backfilled {len(rows)} subscriber(s).")


if __name__ == "__main__":
    asyncio.run(main())
