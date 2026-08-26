#!/usr/bin/env python3
"""Backfill subscribers table from Customer.io.

Fetches all emails from CIO segment 16 (Broadcast Eligible),
reads each subscriber's content_interest attribute from CIO,
and upserts to the Supabase subscribers table.

Usage:
    python scripts/backfill_subscribers_table.py
    python scripts/backfill_subscribers_table.py --dry-run
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

        identifiers = data.get("identifiers", [])
        for ident in identifiers:
            email = ident.get("email", "")
            if email:
                emails.append(email.lower().strip())

        next_url = data.get("next", "")
        if next_url:
            url = next_url
            time.sleep(0.5)
        else:
            url = ""

    return emails


def fetch_cio_subscriber_interest(
    api_key: str, email: str
) -> str:
    """Fetch a single subscriber's content_interest from CIO."""
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = httpx.get(
            f"{CIO_APP_API_BASE}/customers/{email}/attributes",
            headers=headers,
            timeout=15,
        )
        if resp.status_code == 404:
            return "all"
        resp.raise_for_status()
        data = resp.json()
        attrs = data.get("customer", {})
        return attrs.get("content_interest", "all")
    except Exception as e:
        _err(f"Failed to fetch interest for {email}: {e}")
        return "all"


def batch_upsert_subscribers(
    supabase_url: str,
    supabase_key: str,
    rows: List[Dict[str, Any]],
    batch_size: int = 500,
    dry_run: bool = False,
) -> int:
    """Upsert rows into subscribers table in batches."""
    if dry_run:
        _info(f"DRY RUN: Would upsert {len(rows)} rows")
        return len(rows)

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates,return=minimal",
    }

    total = 0
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        resp = httpx.post(
            f"{supabase_url}/rest/v1/subscribers?on_conflict=email",
            json=batch,
            headers=headers,
            timeout=30,
        )
        if resp.status_code in (200, 201):
            total += len(batch)
            _ok(f"Batch {i // batch_size + 1}: {len(batch)} rows upserted")
        else:
            _err(f"Batch {i // batch_size + 1} failed: {resp.status_code} {resp.text}")

        time.sleep(0.2)

    return total


# ── Main ─────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill subscribers table from CIO")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be inserted")
    args = parser.parse_args()

    cio_app_key = os.environ.get("CUSTOMERIO_APP_API_KEY", "")
    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    if not cio_app_key:
        _err("CUSTOMERIO_APP_API_KEY not set")
        sys.exit(1)
    if not supabase_url or not supabase_key:
        _err("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    # Step 1: Fetch all subscriber emails
    print("\n=== Step 1: Fetch CIO Segment Members ===")
    emails = fetch_cio_segment_members(cio_app_key)
    _ok(f"Found {len(emails)} subscribers in segment {CIO_SEGMENT_ID}")

    if not emails:
        _err("No subscribers found. Aborting.")
        sys.exit(1)

    # Step 2: Fetch content_interest for each subscriber
    print(f"\n=== Step 2: Fetch Content Interest for {len(emails)} Subscribers ===")
    rows: List[Dict[str, Any]] = []
    interest_counts: Dict[str, int] = {}

    for i, email in enumerate(emails):
        interest = fetch_cio_subscriber_interest(cio_app_key, email)
        rows.append({
            "email": email,
            "content_interest": interest,
            "brand": "saverwell",
        })
        interest_counts[interest] = interest_counts.get(interest, 0) + 1

        if (i + 1) % 50 == 0:
            _info(f"Processed {i + 1}/{len(emails)} subscribers...")
        time.sleep(0.15)  # ~7 req/s rate limit

    # Step 3: Print distribution
    print("\n=== Step 3: Content Interest Distribution ===")
    for interest, count in sorted(interest_counts.items(), key=lambda x: -x[1]):
        pct = count / len(rows) * 100
        _info(f"  {interest}: {count} ({pct:.1f}%)")

    # Step 4: Upsert to Supabase
    print(f"\n=== Step 4: Upsert {len(rows)} Subscribers ===")
    total = batch_upsert_subscribers(
        supabase_url, supabase_key, rows, dry_run=args.dry_run
    )
    _ok(f"Done. {total} rows processed.")


if __name__ == "__main__":
    main()
