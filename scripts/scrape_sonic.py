#!/usr/bin/env python3
"""Custom scraper for Sonic Drive-In store locations via Inspire Brands API.

Sonic's website (sonicdrivein.com) is a Next.js app that renders location data
entirely client-side. The sitemap at /locations.xml contains only city-level
template pages (no individual stores), and those pages load store data via
JavaScript API calls after render, making traditional HTML scraping impossible.

Strategy (2-phase: grid seed + breadcrumb expansion):
  Phase 1 - GRID SEED: Sweep a dense US grid (0.5-degree spacing, ~35 miles)
    querying the Sonic fulfillment API at each point. Each grid point is
    reverse-geocoded offline (via reverse_geocoder) to get city/state context
    required by the API. Each API call returns the single nearest delivery-
    enabled store.
  Phase 2 - BREADCRUMB EXPANSION: For each discovered store, query 8
    surrounding points offset by ~0.07 degrees (~5 miles) to find adjacent
    stores. Repeat expansion rounds until no new stores are found (max 10
    rounds). This "snowball" approach efficiently discovers clustered urban
    stores.
  Dedup: All stores keyed by store ID; duplicates automatically eliminated.

The Sonic API endpoint (Inspire Brands fulfillment service):
  POST https://api-idp.sonicdrivein.com/snc/digital-exp-api/v1/fulfillment/locations
  Headers: X-Channel: WEBOA, X-Session-Id: <any-uuid>
  Body: {time: null, locationDetails: {coordinates: {lat, lon}, address: {line1, cityName, stateProvinceCode, ...}}}
  Returns: {pickupLocations: [{id, contactDetails, geoDetails, restaurantInfo, locationHours, ...}]}

Note: The API requires a non-empty address.line1 AND matching city/state for
the given coordinates. We reverse-geocode each query point to satisfy this.
The API returns only delivery-enabled stores, covering ~95%+ of all locations.

Usage:
    python scripts/scrape_sonic.py \\
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_sonic.py \\
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx
import reverse_geocoder as rg
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

MERCHANT_NAME = "Sonic"

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

# Full state name -> abbreviation (reverse_geocoder returns full names)
STATE_NAME_TO_ABBR: Dict[str, str] = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new hampshire": "NH", "new jersey": "NJ",
    "new mexico": "NM", "new york": "NY", "north carolina": "NC",
    "north dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode island": "RI", "south carolina": "SC",
    "south dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district of columbia": "DC",
}

SITEMAP_URL = "https://www.sonicdrivein.com/locations.xml"

SONIC_API_URL = (
    "https://api-idp.sonicdrivein.com/snc/digital-exp-api/v1/fulfillment/locations"
)

API_HEADERS = {
    "Content-Type": "application/json",
    "X-Channel": "WEBOA",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
}

# Expansion offsets: 8 compass directions at ~5 miles (~0.07 degrees)
EXPAND_OFFSETS: List[Tuple[float, float]] = [
    (0.07, 0.0),    # N
    (-0.07, 0.0),   # S
    (0.0, 0.07),    # E
    (0.0, -0.07),   # W
    (0.07, 0.07),   # NE
    (0.07, -0.07),  # NW
    (-0.07, 0.07),  # SE
    (-0.07, -0.07), # SW
]

MAX_EXPAND_ROUNDS = 10


def _build_grid_points() -> List[Tuple[float, float]]:
    """Build a dense US grid at 0.5-degree spacing (~35 miles)."""
    points: List[Tuple[float, float]] = []
    # Continental US: lat 25.0-49.5, lon -125.0 to -66.5
    for lat_10 in range(250, 500, 5):  # step 0.5
        lat = lat_10 / 10.0
        for lon_10 in range(-1250, -660, 5):  # step 0.5
            lon = lon_10 / 10.0
            points.append((lat, lon))
    # Alaska and Hawaii
    points.extend([
        (61.2, -149.9), (64.8, -147.7),  # AK
        (21.3, -157.8), (19.7, -155.1),  # HI
    ])
    return points


US_GRID_POINTS = _build_grid_points()


# ---------------------------------------------------------------------------
# Shared boilerplate (matches scrape_aw.py pattern)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Sitemap parsing (for reference logging)
# ---------------------------------------------------------------------------

def parse_sitemap_urls(xml_text: str) -> List[str]:
    """Extract <url><loc>...</loc></url> entries from sitemap XML."""
    pattern = re.compile(r"<url>\s*<loc>([^<]+)</loc>", re.DOTALL)
    return [m.group(1).strip() for m in pattern.finditer(xml_text)]


# ---------------------------------------------------------------------------
# Reverse geocoding
# ---------------------------------------------------------------------------

def reverse_geocode_points(
    points: List[Tuple[float, float]],
) -> Dict[Tuple[float, float], Tuple[str, str]]:
    """Batch reverse-geocode (lat, lon) points to (city_name, state_abbr).

    Uses the offline reverse_geocoder library (no network calls).
    Only returns US points with valid state abbreviations.
    """
    if not points:
        return {}

    log.info("reverse_geocoding", count=len(points))
    results = rg.search(points)

    mapping: Dict[Tuple[float, float], Tuple[str, str]] = {}
    for pt, r in zip(points, results):
        if r.get("cc") != "US":
            continue
        city = r.get("name", "")
        state_full = (r.get("admin1") or "").lower()
        state_abbr = STATE_NAME_TO_ABBR.get(state_full, "")
        if city and state_abbr:
            mapping[pt] = (city, state_abbr)

    log.info("reverse_geocoding_done", us_points=len(mapping))
    return mapping


# ---------------------------------------------------------------------------
# API response parsing
# ---------------------------------------------------------------------------

def format_hours(location_hours: List[Dict[str, Any]]) -> str:
    """Format locationHours array into a compact hours string."""
    if not location_hours:
        return ""
    day_abbr = {
        "MONDAY": "Mon", "TUESDAY": "Tue", "WEDNESDAY": "Wed",
        "THURSDAY": "Thu", "FRIDAY": "Fri", "SATURDAY": "Sat", "SUNDAY": "Sun",
    }
    parts: List[str] = []
    for entry in location_hours:
        day = day_abbr.get(entry.get("dayOfWeek", ""), "")
        start = entry.get("startTime", "")
        end = entry.get("endTime", "")
        if entry.get("isTwentyFourHourService"):
            parts.append(f"{day}: 24hrs")
        elif start and end:
            parts.append(f"{day}: {start}-{end}")
    unique_hours = set(p.split(": ", 1)[1] for p in parts if ": " in p)
    if len(unique_hours) == 1:
        return f"Daily: {unique_hours.pop()}"
    return "; ".join(parts)


def parse_store_from_api(loc: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse a single pickupLocation entry from the Sonic API response."""
    store_id = loc.get("id", "")
    if not store_id:
        return None

    contact = loc.get("contactDetails") or {}
    addr = contact.get("address") or {}
    geo = loc.get("geoDetails") or {}
    restaurant = loc.get("restaurantInfo") or {}

    line1 = (addr.get("line1") or "").strip()
    city = (addr.get("cityName") or "").strip()
    state = (addr.get("stateProvinceCode") or "").strip().upper()
    zip_code = (addr.get("postalCode") or "").strip()
    phone = normalize_phone(contact.get("phone") or "")

    if state not in VALID_STATES:
        return None
    if not line1:
        return None

    # Normalize ZIP to 5 digits
    if zip_code:
        zip_match = re.search(r"\b(\d{5})\b", zip_code)
        zip_code = zip_match.group(1) if zip_match else ""

    # Build store URL
    city_slug = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-")
    addr_slug = re.sub(r"[^a-z0-9]+", "-", line1.lower()).strip("-")
    store_url = (
        f"https://www.sonicdrivein.com/locations/us/{state.lower()}"
        f"/{city_slug}/{addr_slug}/store-{store_id}/"
    )

    hours = format_hours(loc.get("locationHours") or [])

    return {
        "store_id": store_id,
        "name": (restaurant.get("publicName") or line1).strip(),
        "address": line1,
        "address2": (addr.get("line2") or "").strip(),
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "hours": hours,
        "store_url": store_url,
        "latitude": str(geo.get("latitude", "")),
        "longitude": str(geo.get("longitude", "")),
    }


# ---------------------------------------------------------------------------
# API querying
# ---------------------------------------------------------------------------

async def query_sonic_api(
    client: httpx.AsyncClient,
    lat: float,
    lon: float,
    city_name: str,
    state_code: str,
    sem: asyncio.Semaphore,
    session_id: str,
) -> List[Dict[str, Any]]:
    """Query the Sonic fulfillment API for the nearest store at (lat, lon).

    Requires matching city/state context for the coordinates.
    """
    body = {
        "time": None,
        "locationDetails": {
            "coordinates": {"lat": lat, "lon": lon},
            "address": {
                "line1": "100 Main St",
                "cityName": city_name,
                "stateProvinceCode": state_code,
                "postalCode": "",
                "countryCode": "US",
                "countryName": "United States",
            },
        },
    }

    async with sem:
        try:
            resp = await client.post(
                SONIC_API_URL,
                json=body,
                headers={**API_HEADERS, "X-Session-Id": session_id},
            )
            if resp.status_code in (200, 201):
                data = resp.json()
                return data.get("pickupLocations", [])
            elif resp.status_code == 429:
                log.warning("rate_limited", lat=round(lat, 3), lon=round(lon, 3))
                await asyncio.sleep(5)
        except Exception as e:
            log.warning(
                "api_request_failed",
                lat=round(lat, 3), lon=round(lon, 3),
                error=str(e)[:100],
            )
    return []


async def _query_batch_with_geo(
    client: httpx.AsyncClient,
    points_with_geo: List[Tuple[float, float, str, str]],
    sem: asyncio.Semaphore,
    session_id: str,
    stores: Dict[str, Dict[str, Any]],
    batch_size: int = 50,
    label: str = "batch",
) -> int:
    """Query the API for a list of (lat, lon, city, state) tuples.

    Returns count of newly discovered stores.
    """
    new_count = 0
    for i in range(0, len(points_with_geo), batch_size):
        batch = points_with_geo[i : i + batch_size]
        tasks = [
            query_sonic_api(client, lat, lon, city, state, sem, session_id)
            for lat, lon, city, state in batch
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        batch_new = 0
        for r in results:
            if isinstance(r, list):
                for raw_loc in r:
                    parsed = parse_store_from_api(raw_loc)
                    if parsed and parsed["store_id"] not in stores:
                        stores[parsed["store_id"]] = parsed
                        batch_new += 1
        new_count += batch_new

        if i + batch_size < len(points_with_geo):
            await asyncio.sleep(0.3)

        log.info(
            f"{label}_progress",
            batch=i + len(batch),
            total=len(points_with_geo),
            new_stores=batch_new,
            unique_stores=len(stores),
        )
    return new_count


# ---------------------------------------------------------------------------
# Main scrape orchestration
# ---------------------------------------------------------------------------

async def scrape_sonic_locations() -> List[Dict[str, Any]]:
    """Scrape all Sonic locations via grid sweep + breadcrumb expansion."""
    stores: Dict[str, Dict[str, Any]] = {}  # keyed by store_id
    session_id = str(uuid.uuid4())
    sem = asyncio.Semaphore(8)

    # ---- Reverse-geocode all grid points (offline, fast) ----
    geo_map = reverse_geocode_points(US_GRID_POINTS)

    # Build query list: only US points with valid city/state
    grid_queries: List[Tuple[float, float, str, str]] = []
    for pt in US_GRID_POINTS:
        geo_info = geo_map.get(pt)
        if geo_info:
            city, state = geo_info
            grid_queries.append((pt[0], pt[1], city, state))

    log.info(
        "grid_queries_prepared",
        total_grid=len(US_GRID_POINTS),
        us_queries=len(grid_queries),
    )

    async with httpx.AsyncClient(
        timeout=30, follow_redirects=True, http2=False
    ) as client:

        # ---- Log sitemap info (reference only) ----
        try:
            resp = await client.get(SITEMAP_URL, headers={
                "User-Agent": API_HEADERS["User-Agent"],
            })
            if resp.status_code == 200:
                sitemap_urls = parse_sitemap_urls(resp.text)
                city_re = re.compile(
                    r"https://www\.sonicdrivein\.com/locations/us/[a-z]{2}/[a-z0-9-]+$"
                )
                city_count = sum(1 for u in sitemap_urls if city_re.match(u))
                log.info("sitemap_reference", urls=len(sitemap_urls), cities=city_count)
        except Exception:
            pass

        # ---- Phase 1: Dense US grid sweep ----
        log.info("phase_1_grid_sweep", queries=len(grid_queries))
        grid_new = await _query_batch_with_geo(
            client, grid_queries, sem, session_id, stores,
            batch_size=50, label="grid",
        )
        log.info("phase_1_complete", stores_from_grid=grid_new, total=len(stores))

        # ---- Phase 2: Breadcrumb expansion ----
        queried_coords: Set[Tuple[float, float]] = set()
        for pt in US_GRID_POINTS:
            queried_coords.add((round(pt[0], 4), round(pt[1], 4)))

        for _round in range(1, MAX_EXPAND_ROUNDS + 1):
            # Collect expansion points around all known stores
            expand_raw: List[Tuple[float, float]] = []
            for store in list(stores.values()):
                try:
                    slat = float(store["latitude"])
                    slon = float(store["longitude"])
                except (ValueError, KeyError):
                    continue
                for dlat, dlon in EXPAND_OFFSETS:
                    pt = (round(slat + dlat, 4), round(slon + dlon, 4))
                    if pt not in queried_coords:
                        queried_coords.add(pt)
                        expand_raw.append(pt)

            if not expand_raw:
                log.info("expansion_no_new_points", round=_round)
                break

            # Reverse-geocode expansion points
            expand_geo = reverse_geocode_points(expand_raw)
            expand_queries: List[Tuple[float, float, str, str]] = []
            for pt in expand_raw:
                geo_info = expand_geo.get(pt)
                if geo_info:
                    city, state = geo_info
                    expand_queries.append((pt[0], pt[1], city, state))

            if not expand_queries:
                log.info("expansion_no_us_points", round=_round)
                break

            log.info(
                "phase_2_expand",
                round=_round,
                raw_points=len(expand_raw),
                us_queries=len(expand_queries),
                stores_before=len(stores),
            )

            new_count = await _query_batch_with_geo(
                client, expand_queries, sem, session_id, stores,
                batch_size=50, label=f"expand_r{_round}",
            )

            log.info(
                "phase_2_round_done",
                round=_round,
                new_stores=new_count,
                total=len(stores),
            )

            if new_count == 0:
                log.info("expansion_converged", round=_round)
                break

    return list(stores.values())


# ---------------------------------------------------------------------------
# Sheet output (A:Q schema)
# ---------------------------------------------------------------------------

def locations_to_rows(
    locations: List[Dict[str, Any]],
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema (A:Q)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []

    for loc in locations:
        rows.append([
            MERCHANT_NAME,                              # A: merchant_name
            str(merchant_id) if merchant_id else "TBD", # B: merchant_id
            loc.get("name", ""),                         # C: name
            loc.get("address", ""),                      # D: address
            loc.get("address2", ""),                     # E: address2
            loc.get("city", ""),                         # F: city
            loc.get("state", ""),                        # G: state
            loc.get("zip", ""),                          # H: zip
            loc.get("phone", ""),                        # I: phone
            loc.get("hours", ""),                        # J: hours
            loc.get("store_url", ""),                    # K: store_url
            loc.get("latitude", ""),                     # L: lat
            loc.get("longitude", ""),                    # M: lon
            "Pending",                                   # N: status
            now,                                         # O: scraped_at
            "",                                          # P: pushed_at
            "v2_sonic_sitemap",                          # Q: fetch_method
        ])

    return rows


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    locations = await scrape_sonic_locations()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 1))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Sitemap + API Scraper")
    print(f"{'=' * 60}")
    print(f"  Locations scraped:  {len(locations)}")
    print(f"  Valid rows:         {len(rows)}")
    print(f"  Elapsed:            {round(elapsed, 1)}s")

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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Sonic Drive-In locations via sitemap + Inspire Brands API"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
