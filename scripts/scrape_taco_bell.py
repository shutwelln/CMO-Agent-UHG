#!/usr/bin/env python3
"""Custom scraper for Taco Bell store locations via their store locator API.

Taco Bell exposes nearby stores via:
    https://www.tacobell.com/tacobellwebservices/v4/tacobell/stores?latitude=...&longitude=...

We query a grid of ~1,475 lat/lon points covering the continental US, then
deduplicate by storeNumber.

Usage:
    python scripts/scrape_taco_bell.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_taco_bell.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

MERCHANT_NAME = "Taco Bell"

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

BASE_URL = "https://www.tacobell.com/tacobellwebservices/v4/tacobell/stores"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://www.tacobell.com/find-us",
}

# Grid covering continental US: lat 25-49, lon -125 to -67, step 1 degree
LAT_MIN, LAT_MAX, LAT_STEP = 25.0, 49.0, 1.0
LON_MIN, LON_MAX, LON_STEP = -125.0, -67.0, 1.0

SEMAPHORE_LIMIT = 5
REQUEST_DELAY = 0.5


def generate_grid() -> List[Tuple[float, float]]:
    """Generate lat/lon grid points covering the continental US."""
    points: List[Tuple[float, float]] = []
    lat = LAT_MIN
    while lat <= LAT_MAX:
        lon = LON_MIN
        while lon <= LON_MAX:
            points.append((lat, lon))
            lon += LON_STEP
        lat += LAT_STEP
    return points


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


async def fetch_stores_for_point(
    client: httpx.AsyncClient,
    sem: asyncio.Semaphore,
    lat: float,
    lon: float,
    seen_store_numbers: Set[str],
    stores: List[Dict[str, Any]],
    progress: Dict[str, int],
) -> None:
    """Fetch nearby stores for a single lat/lon grid point."""
    async with sem:
        progress["queried"] += 1
        try:
            resp = await client.get(
                BASE_URL,
                params={"latitude": str(lat), "longitude": str(lon)},
                headers=HEADERS,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log.warning("fetch_failed", lat=lat, lon=lon, error=str(e))
            await asyncio.sleep(REQUEST_DELAY)
            return

        nearby = data.get("nearByStores", [])
        new_count = 0

        for store in nearby:
            store_number = str(store.get("storeNumber", ""))
            if not store_number or store_number in seen_store_numbers:
                continue
            seen_store_numbers.add(store_number)

            addr = store.get("address", {})
            geo = store.get("geoPoint", {})

            street = (addr.get("line1") or "").strip()
            city = (addr.get("town") or "").strip()
            # Region is nested: {"isocode": "US-NY"}
            region = addr.get("region", {})
            state_iso = region.get("isocode", "") if isinstance(region, dict) else ""
            state = state_iso.replace("US-", "").strip().upper()[:2]
            zip_code = (addr.get("postalCode") or "").strip()
            phone = normalize_phone(store.get("phoneNumber") or "")
            lat_val = geo.get("latitude")
            lon_val = geo.get("longitude")

            # Filter US-only
            if state not in VALID_STATES:
                continue

            # Normalize ZIP to 5 digits
            if zip_code:
                zip_match = re.search(r"\b(\d{5})\b", zip_code)
                zip_code = zip_match.group(1) if zip_match else ""

            stores.append({
                "store_number": store_number,
                "address": street,
                "city": city,
                "state": state,
                "zip": zip_code,
                "phone": phone,
                "latitude": str(lat_val) if lat_val is not None else "",
                "longitude": str(lon_val) if lon_val is not None else "",
            })
            new_count += 1

        if new_count > 0:
            log.info(
                "point_fetched",
                lat=lat,
                lon=lon,
                nearby=len(nearby),
                new=new_count,
                total=len(stores),
                progress=f"{progress['queried']}/{progress['total']}",
            )

        await asyncio.sleep(REQUEST_DELAY)


async def fetch_all_stores() -> List[Dict[str, Any]]:
    """Fetch all Taco Bell stores by querying a US-covering lat/lon grid."""
    grid = generate_grid()
    log.info("grid_generated", points=len(grid))

    stores: List[Dict[str, Any]] = []
    seen_store_numbers: Set[str] = set()
    sem = asyncio.Semaphore(SEMAPHORE_LIMIT)
    progress: Dict[str, int] = {"queried": 0, "total": len(grid)}

    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        tasks = [
            fetch_stores_for_point(
                client, sem, lat, lon, seen_store_numbers, stores, progress
            )
            for lat, lon in grid
        ]
        await asyncio.gather(*tasks)

    log.info("fetch_complete", total_stores=len(stores), grid_points_queried=len(grid))
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
            "",  # name (individual store names not provided)
            loc.get("address", ""),
            "",  # address2
            loc.get("city", ""),
            loc.get("state", ""),
            loc.get("zip", ""),
            loc.get("phone", ""),
            "",  # hours
            "",  # store_url
            loc.get("latitude", ""),
            loc.get("longitude", ""),
            "Pending",
            now,
            "",  # pushed_at
            "v2_taco_bell_api",
        ])

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Taco Bell store locations via store locator API"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t0 = time.monotonic()

    # Fetch all stores via grid search
    locations = asyncio.run(fetch_all_stores())
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 3))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Store Locator API Scraper")
    print(f"{'=' * 60}")
    print(f"  Grid points queried: {25 * 59}")
    print(f"  Locations fetched:   {len(locations)}")
    print(f"  Valid rows:          {len(rows)}")
    print(f"  Elapsed:             {round(elapsed, 3)}s")

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
        print(f"  Written to sheet:    {written}")

    print()


if __name__ == "__main__":
    main()
