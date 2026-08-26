#!/usr/bin/env python3
"""Custom scraper for A&W Restaurants locations via Drupal JSON:API.

A&W exposes store data via https://backend.awrestaurants.com/jsonapi/node/store
with no auth required. Pagination is handled via ?page[limit]=50&page[offset]=0.

Usage:
    python scripts/scrape_aw.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_aw.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

MERCHANT_NAME = "A&W"

OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SCRAPED_TAB = "Scraped Locations"

SUPABASE_URL = __import__("os").environ.get("SUPABASE_URL", "")
SUPABASE_KEY = __import__("os").environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

VALID_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

BASE_URL = "https://backend.awrestaurants.com/jsonapi/node/store"
PAGE_SIZE = 50


def get_sheets_service() -> Any:
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        log.error("google_auth_failed")
        sys.exit(1)
    from googleapiclient.discovery import build as build_google
    return build_google("sheets", "v4", credentials=creds)


def lookup_merchant_id(name: str) -> Optional[int]:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{SUPABASE_URL}/rest/v1/merchants",
                headers=SUPABASE_HEADERS,
                params={"name": f"eq.{name}", "select": "id", "limit": "1"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    return data[0]["id"]
    except Exception:
        pass
    return None


def normalize_phone(raw: str) -> str:
    """Normalize phone to (XXX) XXX-XXXX format."""
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        return f"({digits[1:4]}) {digits[4:7]}-{digits[7:]}"
    return raw.strip()


def dedup_key(address: str, city: str, state: str) -> str:
    """Generate dedup key from address+city+state."""
    return f"{address.lower().strip()}|{city.lower().strip()}|{state.upper().strip()}"


def fetch_all_stores() -> List[Dict[str, Any]]:
    """Fetch all stores from A&W Drupal JSON:API with pagination."""
    stores: List[Dict[str, Any]] = []
    offset = 0
    seen_keys: Set[str] = set()

    with httpx.Client(timeout=30, follow_redirects=True) as client:
        while True:
            url = f"{BASE_URL}?page[limit]={PAGE_SIZE}&page[offset]={offset}"
            log.info("fetching_page", offset=offset, url=url)

            try:
                resp = client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                log.error("fetch_failed", offset=offset, error=str(e))
                break

            items = data.get("data", [])
            if not items:
                log.info("no_more_items", offset=offset)
                break

            for item in items:
                attrs = item.get("attributes", {})

                # Extract fields
                address = (attrs.get("title") or "").strip()
                city = (attrs.get("field_city") or "").strip()
                state = (attrs.get("field_state") or "").strip().upper()[:2]
                zip_code = (attrs.get("field_zip_code") or "").strip()
                phone = normalize_phone(attrs.get("field_store_phone_number") or "")
                store_url = (attrs.get("field_store_page_url") or "").strip()
                lat = attrs.get("field_latitude")
                lon = attrs.get("field_longitude")

                # Filter US-only
                if state not in VALID_STATES:
                    continue

                # Dedup
                key = dedup_key(address, city, state)
                if key in seen_keys:
                    continue
                seen_keys.add(key)

                # Normalize ZIP
                if zip_code:
                    zip_match = re.search(r"\b(\d{5})\b", zip_code)
                    zip_code = zip_match.group(1) if zip_match else ""

                stores.append({
                    "address": address,
                    "city": city,
                    "state": state,
                    "zip": zip_code,
                    "phone": phone,
                    "store_url": store_url,
                    "latitude": str(lat) if lat else "",
                    "longitude": str(lon) if lon else "",
                })

            log.info("page_complete", offset=offset, items=len(items), total_stores=len(stores))

            # Check if we have more pages
            links = data.get("links", {})
            if "next" not in links:
                log.info("no_next_link")
                break

            offset += PAGE_SIZE

    return stores


def locations_to_rows(
    locations: List[Dict[str, str]],
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema (A:Q)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []

    for loc in locations:
        rows.append([
            MERCHANT_NAME,
            str(merchant_id) if merchant_id else "TBD",
            "",  # name (A&W stores don't have individual names)
            loc.get("address", ""),
            "",  # address2
            loc.get("city", ""),
            loc.get("state", ""),
            loc.get("zip", ""),
            loc.get("phone", ""),
            "",  # hours
            loc.get("store_url", ""),
            loc.get("latitude", ""),
            loc.get("longitude", ""),
            "Pending",
            now,
            "",  # pushed_at
            "v2_aw_custom",
        ])

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape A&W Restaurants locations via Drupal JSON:API"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t0 = time.monotonic()

    # Fetch all stores from API
    locations = fetch_all_stores()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 3))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Drupal JSON:API Scraper")
    print(f"{'=' * 60}")
    print(f"  Locations fetched:  {len(locations)}")
    print(f"  Valid rows:         {len(rows)}")
    print(f"  Elapsed:            {round(elapsed, 3)}s")

    if args.dry_run:
        print(f"  (DRY RUN - nothing written)")
        for r in rows[:5]:
            print(f"    {r[3]:45s} {r[5]:20s} {r[6]:2s} {r[7]:5s}")
        if len(rows) > 5:
            print(f"    ... and {len(rows) - 5} more")
    else:
        sheets_svc = get_sheets_service()
        resp = (
            sheets_svc.spreadsheets()
            .values()
            .append(
                spreadsheetId=args.sheet_id,
                range=f"{SCRAPED_TAB}!A:Q",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            )
            .execute()
        )
        written = resp.get("updates", {}).get("updatedRows", len(rows))
        print(f"  Written to sheet:   {written}")

    print()


if __name__ == "__main__":
    main()
