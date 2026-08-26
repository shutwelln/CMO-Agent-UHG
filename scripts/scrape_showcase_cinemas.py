#!/usr/bin/env python3
"""Custom scraper for Showcase Cinemas locations (hardcoded).

Showcase Cinemas has only 22 theaters across MA, NY, OH, and RI.
All location data is hardcoded from https://www.showcasecinemas.com/our-locations/
since the set is small and stable.

Usage:
    python scripts/scrape_showcase_cinemas.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_showcase_cinemas.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

MERCHANT_NAME = "Showcase Cinemas"

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

# ---------------------------------------------------------------------------
# Hardcoded theater data (22 locations)
# Source: https://www.showcasecinemas.com/our-locations/
# ---------------------------------------------------------------------------
SHOWCASE_LOCATIONS: List[Dict[str, str]] = [
    # MA (10)
    {
        "name": "Showcase SuperLux Chestnut Hill",
        "address": "55 Boylston Street",
        "city": "Chestnut Hill",
        "state": "MA",
        "zip": "02467",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Hanover Crossing",
        "address": "1775 Washington Street",
        "city": "Hanover",
        "state": "MA",
        "zip": "02339",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Legacy Place",
        "address": "670 Legacy Place",
        "city": "Dedham",
        "state": "MA",
        "zip": "02026",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Blackstone Valley 14 Cinema de Lux",
        "address": "70 Worcester/Prov. Tpke",
        "city": "Millbury",
        "state": "MA",
        "zip": "01527",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Lowell",
        "address": "32 Reiss Avenue",
        "city": "Lowell",
        "state": "MA",
        "zip": "01851",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Patriot Place",
        "address": "24 Patriot Place",
        "city": "Foxboro",
        "state": "MA",
        "zip": "02035",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux North Attleboro",
        "address": "640 South Washington St",
        "city": "North Attleboro",
        "state": "MA",
        "zip": "02760",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Randolph",
        "address": "73 Mazzeo Drive",
        "city": "Randolph",
        "state": "MA",
        "zip": "02368",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinemas Seekonk Route 6",
        "address": "100 Commerce Way",
        "city": "Seekonk",
        "state": "MA",
        "zip": "02771",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Woburn",
        "address": "25 Middlesex Canal Parkway",
        "city": "Woburn",
        "state": "MA",
        "zip": "01801",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    # NY (9)
    {
        "name": "Concourse Plaza Multiplex Cinemas",
        "address": "214 East 161st Street",
        "city": "Bronx",
        "state": "NY",
        "zip": "10451",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Linden Boulevard Multiplex Cinemas",
        "address": "2784 Linden Boulevard",
        "city": "Brooklyn",
        "state": "NY",
        "zip": "11208",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Farmingdale",
        "address": "1001 Broad Hollow Road",
        "city": "Farmingdale",
        "state": "NY",
        "zip": "11735",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Broadway",
        "address": "955 Broadway Commons",
        "city": "Hicksville",
        "state": "NY",
        "zip": "11801",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Island 16: Cinema de Lux",
        "address": "185 Morris Avenue",
        "city": "Holtsville",
        "state": "NY",
        "zip": "11742",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Jamaica Multiplex Cinemas",
        "address": "15902 Jamaica Avenue",
        "city": "Jamaica",
        "state": "NY",
        "zip": "11432",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "College Point Multiplex Cinemas",
        "address": "2855 Ulmer Street",
        "city": "Whitestone",
        "state": "NY",
        "zip": "11357",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Cross County",
        "address": "2 South Drive",
        "city": "Yonkers",
        "state": "NY",
        "zip": "10704",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Ridge Hill",
        "address": "59 Fitzgerald Street at Ridge Hill",
        "city": "Yonkers",
        "state": "NY",
        "zip": "10710",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    # OH (1)
    {
        "name": "Showcase Cinema de Lux Springdale",
        "address": "12064 Springfield Pike",
        "city": "Springdale",
        "state": "OH",
        "zip": "45246",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    # RI (2)
    {
        "name": "Providence Place Cinemas 16 and IMAX",
        "address": "10 Providence Place",
        "city": "Providence",
        "state": "RI",
        "zip": "02903",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
    {
        "name": "Showcase Cinema de Lux Warwick",
        "address": "1200 Quaker Lane",
        "city": "Warwick",
        "state": "RI",
        "zip": "02886",
        "store_url": "https://www.showcasecinemas.com/our-locations/",
    },
]


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


def get_locations() -> List[Dict[str, str]]:
    """Return the hardcoded list of Showcase Cinemas locations."""
    log.info("loading_hardcoded_locations", count=len(SHOWCASE_LOCATIONS))
    return SHOWCASE_LOCATIONS


def locations_to_rows(
    locations: List[Dict[str, str]],
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema (A:Q)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []

    for loc in locations:
        state = (loc.get("state") or "").upper().strip()[:2]
        if state not in VALID_STATES:
            continue

        zip_code = (loc.get("zip") or "").strip()
        if zip_code:
            zip_match = re.search(r"\b(\d{5})\b", zip_code)
            zip_code = zip_match.group(1) if zip_match else ""

        rows.append([
            MERCHANT_NAME,
            str(merchant_id) if merchant_id else "TBD",
            (loc.get("name") or "").strip(),
            (loc.get("address") or "").strip(),
            "",  # address2
            (loc.get("city") or "").strip(),
            state,
            zip_code,
            (loc.get("phone") or "").strip(),
            "",  # hours
            (loc.get("store_url") or "").strip(),
            str(loc.get("latitude") or ""),
            str(loc.get("longitude") or ""),
            "Pending",
            now,
            "",  # pushed_at
            "v2_showcase_custom",
        ])

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Showcase Cinemas locations (hardcoded)"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t0 = time.monotonic()

    # Load hardcoded locations
    locations = get_locations()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 3))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Hardcoded Custom Scraper")
    print(f"{'=' * 60}")
    print(f"  Locations loaded:   {len(locations)}")
    print(f"  Valid rows:         {len(rows)}")
    print(f"  Elapsed:            {round(elapsed, 3)}s")

    if args.dry_run:
        print(f"  (DRY RUN - nothing written)")
        for r in rows[:5]:
            print(f"    {r[2]:45s} {r[5]:20s} {r[6]:2s} {r[7]:5s}")
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
