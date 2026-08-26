#!/usr/bin/env python3
"""Seed subscriber_sends table with historical send data.

One-time script to backfill:
1. Core Foundations slugs for all broadcast-eligible subscribers (send_type='core_foundations')
2. Broadcast send log entries for all broadcast-eligible subscribers (send_type='broadcast')

Reads subscriber emails from Customer.io segment membership API (segment 16),
then reads broadcast_send_log from Supabase for previously-sent article slugs.

Usage:
    python scripts/seed_subscriber_sends.py
    python scripts/seed_subscriber_sends.py --dry-run
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any, Dict, List

import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))


# ── Constants ────────────────────────────────────────────────────────────

CORE_FOUNDATIONS_SLUGS = [
    "safe-online-shopping-tips",
    "password-safety-guide",
    "senior-scam-protection-complete-guide",
    "cell-phone-plans-seniors",
    "medical-alert-systems-guide",
    "when-to-claim-social-security",
]

CIO_APP_API_BASE = "https://api.customer.io/v1"
CIO_SEGMENT_ID = 16  # Broadcast Eligible segment


# ── Helpers ──────────────────────────────────────────────────────────────

def _ok(msg: str) -> None:
    print(f"  [OK] {msg}")


def _info(msg: str) -> None:
    print(f"  [INFO] {msg}")


def _err(msg: str) -> None:
    print(f"  [ERR] {msg}")


def fetch_cio_segment_members(api_key: str) -> List[str]:
    """Fetch all subscriber emails from a CIO segment, handling pagination."""
    emails: List[str] = []
    url = f"{CIO_APP_API_BASE}/segments/{CIO_SEGMENT_ID}/membership"
    headers = {"Authorization": f"Bearer {api_key}"}

    page = 0
    while url:
        page += 1
        _info(f"Fetching CIO segment page {page}...")
        resp = httpx.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # CIO returns {"identifiers": [...], "next": "cursor_url"}
        identifiers = data.get("identifiers", [])
        for ident in identifiers:
            email = ident.get("email", "")
            if email:
                emails.append(email.lower().strip())

        next_url = data.get("next", "")
        if next_url:
            url = next_url
            time.sleep(0.5)  # respect rate limits
        else:
            url = ""

    return emails


def fetch_broadcast_send_log(
    supabase_url: str, supabase_key: str
) -> List[str]:
    """Fetch all broadcast-sent article slugs from Supabase."""
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
    }
    resp = httpx.get(
        f"{supabase_url}/rest/v1/broadcast_send_log",
        params={
            "select": "article_slug",
            "send_type": "neq.seed",
        },
        headers=headers,
        timeout=30,
    )
    resp.raise_for_status()
    rows = resp.json()
    # Deduplicate slugs
    return list({r["article_slug"] for r in rows if r.get("article_slug")})


def batch_insert_subscriber_sends(
    supabase_url: str,
    supabase_key: str,
    rows: List[Dict[str, Any]],
    batch_size: int = 500,
    dry_run: bool = False,
) -> int:
    """Insert rows into subscriber_sends in batches, ignoring duplicates."""
    if dry_run:
        _info(f"DRY RUN: Would insert {len(rows)} rows")
        return len(rows)

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=ignore-duplicates,return=minimal",
    }

    total_inserted = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        resp = httpx.post(
            f"{supabase_url}/rest/v1/subscriber_sends",
            json=batch,
            headers=headers,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            total_inserted += len(batch)
            _ok(f"Batch {i // batch_size + 1}: {len(batch)} rows inserted")
        elif resp.status_code == 409:
            _info(f"Batch {i // batch_size + 1}: duplicates ignored")
            total_inserted += len(batch)
        else:
            _err(f"Batch {i // batch_size + 1} failed: {resp.status_code} {resp.text}")

        time.sleep(0.2)

    return total_inserted


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Seed subscriber_sends table")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted")
    args = parser.parse_args()

    # Load credentials
    cio_app_key = os.environ.get("CUSTOMERIO_APP_API_KEY", "")
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not cio_app_key:
        _err("CUSTOMERIO_APP_API_KEY not set")
        sys.exit(1)
    if not supabase_url or not supabase_key:
        _err("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    # Step 1: Get all subscriber emails from CIO segment
    print("\n=== Step 1: Fetch CIO Segment Members ===")
    emails = fetch_cio_segment_members(cio_app_key)
    _ok(f"Found {len(emails)} subscribers in segment {CIO_SEGMENT_ID}")

    if not emails:
        _err("No subscribers found. Aborting.")
        sys.exit(1)

    # Step 2: Build Core Foundations rows
    print("\n=== Step 2: Build Core Foundations Seed Data ===")
    cf_rows: List[Dict[str, Any]] = []
    for email in emails:
        for slug in CORE_FOUNDATIONS_SLUGS:
            cf_rows.append({
                "subscriber_email": email,
                "article_slug": slug,
                "send_type": "core_foundations",
            })
    _info(f"Core Foundations: {len(cf_rows)} rows ({len(emails)} subs x {len(CORE_FOUNDATIONS_SLUGS)} slugs)")

    # Step 3: Get broadcast send log for previously-sent articles
    print("\n=== Step 3: Fetch Broadcast Send Log ===")
    broadcast_slugs = fetch_broadcast_send_log(supabase_url, supabase_key)
    _ok(f"Found {len(broadcast_slugs)} previously broadcast articles")

    # Step 4: Build broadcast seed rows (every subscriber saw every broadcast article)
    print("\n=== Step 4: Build Broadcast Seed Data ===")
    bc_rows: List[Dict[str, Any]] = []
    for email in emails:
        for slug in broadcast_slugs:
            bc_rows.append({
                "subscriber_email": email,
                "article_slug": slug,
                "send_type": "broadcast",
            })
    _info(f"Broadcast: {len(bc_rows)} rows ({len(emails)} subs x {len(broadcast_slugs)} slugs)")

    # Step 5: Insert all rows
    all_rows = cf_rows + bc_rows
    print(f"\n=== Step 5: Insert {len(all_rows)} Total Rows ===")
    inserted = batch_insert_subscriber_sends(
        supabase_url, supabase_key, all_rows, dry_run=args.dry_run
    )
    _ok(f"Done. {inserted} rows processed.")


if __name__ == "__main__":
    main()
