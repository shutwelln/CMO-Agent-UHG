#!/usr/bin/env python3
"""Scrape store locations from merchant store locator pages.

Two-phase workflow:
  1. SCRAPE: Fetch locator pages, extract via Haiku, geocode, write to Google Sheet
     for human review.
  2. PUSH:   Read approved rows from the Google Sheet and insert into Supabase
     (locations_v2 + store_locations tables).

Strategies (--strategy):
  auto     - Comprehensive: tries sitemap -> API replay -> ZIP search -> state pages
  sitemap  - Sitemap XML discovery only
  api      - Playwright + API interception with 200-point coordinate grid
  zip      - Dense ZIP search with 500 ZIP codes and early termination
  state    - State directory page scraping (/locations/{state})
  legacy   - Old tiered fetch pipeline (uses --fetch-mode)

Usage:
    # Comprehensive scrape (recommended)
    python scripts/scrape_store_locations.py --sheet-id "SHEET_ID" --strategy auto
    python scripts/scrape_store_locations.py --sheet-id "SHEET_ID" --merchant "Hardee's"
    python scripts/scrape_store_locations.py --sheet-id "SHEET_ID" --dry-run

    # Force a specific strategy
    python scripts/scrape_store_locations.py --sheet-id "SHEET_ID" \
        --merchant "Golden Corral" --strategy sitemap
    python scripts/scrape_store_locations.py --sheet-id "SHEET_ID" \
        --merchant "Hardee's" --strategy api

    # Legacy mode (old behavior)
    python scripts/scrape_store_locations.py --sheet-id "SHEET_ID" \
        --strategy legacy --fetch-mode auto

    # Push approved rows from sheet to Supabase
    python scripts/scrape_store_locations.py --sheet-id "SHEET_ID" --push
    python scripts/scrape_store_locations.py --sheet-id "SHEET_ID" --push --dry-run
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote_plus, urlencode, urljoin, urlparse

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")
ZCTA_PATH = _PROJECT_ROOT / "data" / "zcta_centroids.csv"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Merchant Review tab column indices (0-based)
COL_STATUS = 0
COL_NAME = 2
COL_EXISTING_ID = 14
COL_STORE_LOCATOR = 25  # col Z: "Easy - https://..." or "Medium - https://..."

# Scraped Locations tab columns (named to match Supabase field names)
SCRAPED_HEADER = [
    "merchant_name",  # A  (lookup reference, not a DB field)
    "merchant_id",  # B  -> store_locations.merchant_id
    "store_name",  # C  -> store_locations.store_name
    "address1",  # D  -> locations_v2.address1
    "address2",  # E  -> locations_v2.address2
    "city",  # F  -> locations_v2.city
    "state",  # G  -> locations_v2.state
    "zip",  # H  -> locations_v2.zip
    "phone",  # I  -> locations_v2.phone
    "store_hours",  # J  -> store_locations.store_hours
    "store_url",  # K  -> store_locations.store_url
    "latitude",  # L  -> locations_v2.latitude
    "longitude",  # M  -> locations_v2.longitude
    "status",  # N  (Pending / Approved / Rejected - sheet only)
    "scraped_at",  # O  -> store_locations.scraped_at
    "pushed_at",  # P  (sheet only)
    "fetch_method",  # Q  (debugging: which tier produced the data)
]
SCRAPED_TAB = "Scraped Locations"
# Column indices for reading back from the Scraped Locations tab
SC_MERCHANT_NAME = 0
SC_MERCHANT_ID = 1
SC_STORE_NAME = 2
SC_ADDRESS = 3
SC_SUITE = 4
SC_CITY = 5
SC_STATE = 6
SC_ZIP = 7
SC_PHONE = 8
SC_HOURS = 9
SC_STORE_URL = 10
SC_LATITUDE = 11
SC_LONGITUDE = 12
SC_STATUS = 13
SC_SCRAPED_AT = 14
SC_PUSHED_AT = 15

HAIKU_MODEL = "claude-haiku-4-5-20251001"
MAX_HTML_CHARS = 80_000
THROTTLE_SECONDS = 0.5
PILOT_COUNT = 4

# ---------------------------------------------------------------------------
# Tiered fetch config
# ---------------------------------------------------------------------------
SCRAPING_SERVICE_API_KEY = os.environ.get("SCRAPING_SERVICE_API_KEY", "")
SCRAPING_SERVICE_URL = os.environ.get("SCRAPING_SERVICE_URL", "https://api.scraperapi.com")
PLAYWRIGHT_TIMEOUT_MS = 30_000
PLAYWRIGHT_WAIT_MS = 5_000

# ~50 ZIPs covering major US metro areas (one per state cluster)
US_SEARCH_GRID = [
    "10001",  # New York, NY
    "90001",  # Los Angeles, CA
    "60601",  # Chicago, IL
    "77001",  # Houston, TX
    "85001",  # Phoenix, AZ
    "19101",  # Philadelphia, PA
    "78201",  # San Antonio, TX
    "92101",  # San Diego, CA
    "75201",  # Dallas, TX
    "95101",  # San Jose, CA
    "78701",  # Austin, TX
    "32099",  # Jacksonville, FL
    "46201",  # Indianapolis, IN
    "94101",  # San Francisco, CA
    "43201",  # Columbus, OH
    "28201",  # Charlotte, NC
    "76101",  # Fort Worth, TX
    "48201",  # Detroit, MI
    "79901",  # El Paso, TX
    "98101",  # Seattle, WA
    "80201",  # Denver, CO
    "20001",  # Washington, DC
    "02101",  # Boston, MA
    "37201",  # Nashville, TN
    "73101",  # Oklahoma City, OK
    "89101",  # Las Vegas, NV
    "97201",  # Portland, OR
    "38101",  # Memphis, TN
    "40201",  # Louisville, KY
    "21201",  # Baltimore, MD
    "53201",  # Milwaukee, WI
    "87101",  # Albuquerque, NM
    "85701",  # Tucson, AZ
    "93701",  # Fresno, CA
    "95801",  # Sacramento, CA
    "64101",  # Kansas City, MO
    "30301",  # Atlanta, GA
    "68101",  # Omaha, NE
    "33101",  # Miami, FL
    "55401",  # Minneapolis, MN
    "74101",  # Tulsa, OK
    "33601",  # Tampa, FL
    "80901",  # Colorado Springs, CO
    "27601",  # Raleigh, NC
    "96801",  # Honolulu, HI
    "23219",  # Richmond, VA
    "29201",  # Columbia, SC
    "83702",  # Boise, ID
    "84101",  # Salt Lake City, UT
    "70112",  # New Orleans, LA
]


@dataclass
class FetchResult:
    """Result from a tiered fetch attempt."""

    html: str
    method: str  # static, service, playwright, playwright_api, playwright_search
    status_code: int = 200
    api_endpoints: List[str] = field(default_factory=list)


VALID_STATES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
}

US_STATES: Dict[str, str] = {
    "AL": "alabama",
    "AK": "alaska",
    "AZ": "arizona",
    "AR": "arkansas",
    "CA": "california",
    "CO": "colorado",
    "CT": "connecticut",
    "DE": "delaware",
    "FL": "florida",
    "GA": "georgia",
    "HI": "hawaii",
    "ID": "idaho",
    "IL": "illinois",
    "IN": "indiana",
    "IA": "iowa",
    "KS": "kansas",
    "KY": "kentucky",
    "LA": "louisiana",
    "ME": "maine",
    "MD": "maryland",
    "MA": "massachusetts",
    "MI": "michigan",
    "MN": "minnesota",
    "MS": "mississippi",
    "MO": "missouri",
    "MT": "montana",
    "NE": "nebraska",
    "NV": "nevada",
    "NH": "new-hampshire",
    "NJ": "new-jersey",
    "NM": "new-mexico",
    "NY": "new-york",
    "NC": "north-carolina",
    "ND": "north-dakota",
    "OH": "ohio",
    "OK": "oklahoma",
    "OR": "oregon",
    "PA": "pennsylvania",
    "RI": "rhode-island",
    "SC": "south-carolina",
    "SD": "south-dakota",
    "TN": "tennessee",
    "TX": "texas",
    "UT": "utah",
    "VT": "vermont",
    "VA": "virginia",
    "WA": "washington",
    "WV": "west-virginia",
    "WI": "wisconsin",
    "WY": "wyoming",
    "DC": "district-of-columbia",
}

# Reverse lookup: full state name -> 2-letter abbreviation.
# Handles both "ohio" and "new-york" (hyphenated slug) formats.
_STATE_NAME_TO_ABBR: Dict[str, str] = {}
for _abbr, _slug in US_STATES.items():
    # e.g. "ohio" -> "OH", "new-york" -> "NY"
    _STATE_NAME_TO_ABBR[_slug] = _abbr
    # Also store space-separated form: "new york" -> "NY"
    _STATE_NAME_TO_ABBR[_slug.replace("-", " ")] = _abbr


def _normalize_state(raw: str) -> str:
    """Convert a state value to a 2-letter code.

    Handles: "OH", "Ohio", "OHIO", "oh", "new york", "New York".
    Returns uppercase 2-letter code or empty string if unrecognized.
    """
    s = raw.strip()
    if not s:
        return ""
    upper = s.upper()
    # Already a valid 2-letter code
    if len(upper) == 2 and upper in VALID_STATES:
        return upper
    # Try full-name lookup (case-insensitive)
    abbr = _STATE_NAME_TO_ABBR.get(s.lower())
    if abbr:
        return abbr
    return ""


def _normalize_zip(raw: Any) -> str:
    """Normalize a ZIP code value to 5 digits.

    Handles: "43215", "43215-1234", 43215 (int), "043215".
    Returns 5-digit string or empty string if invalid.
    """
    s = str(raw).strip().split("-")[0].split(" ")[0]
    s = re.sub(r"[^0-9]", "", s)
    s = s[:5]
    if re.match(r"^\d{5}$", s):
        return s
    return ""


class LocationDeduplicator:
    """Deduplicate locations by (address, city, state, zip) tuple."""

    def __init__(self) -> None:
        self._seen: set = set()
        self._locations: List[Dict[str, Any]] = []

    def _make_key(self, loc: Dict[str, Any]) -> Tuple[str, str, str, str]:
        return (
            (loc.get("address") or "").lower().strip(),
            (loc.get("city") or "").lower().strip(),
            (loc.get("state") or "").upper().strip(),
            (loc.get("zip") or "").strip(),
        )

    def add(self, loc: Dict[str, Any]) -> bool:
        """Add a location. Returns True if new (not a duplicate)."""
        key = self._make_key(loc)
        if not key[0] or not key[1] or not key[2] or not key[3]:
            return False
        if key in self._seen:
            return False
        self._seen.add(key)
        self._locations.append(loc)
        return True

    def get_all(self) -> List[Dict[str, Any]]:
        """Return all unique locations."""
        return list(self._locations)

    def __len__(self) -> int:
        return len(self._locations)


# Cache for dense grids (computed once per run)
_dense_coord_grid_cache: Optional[List[Tuple[float, float]]] = None
_dense_zip_grid_cache: Optional[List[str]] = None


def build_dense_coord_grid(n: int = 200) -> List[Tuple[float, float]]:
    """Build an evenly-spaced coordinate grid covering the US.

    Divides the US bounding box (lat 24-49, lng -125 to -66) into a grid,
    producing ~n points with even geographic coverage.
    """
    global _dense_coord_grid_cache
    if _dense_coord_grid_cache is not None:
        return _dense_coord_grid_cache

    lat_min, lat_max = 24.0, 49.0
    lng_min, lng_max = -125.0, -66.0

    bands = int(math.sqrt(n))
    lat_step = (lat_max - lat_min) / bands
    lng_step = (lng_max - lng_min) / bands

    grid: List[Tuple[float, float]] = []
    for i in range(bands):
        lat = lat_min + lat_step * (i + 0.5)
        for j in range(bands):
            lng = lng_min + lng_step * (j + 0.5)
            grid.append((round(lat, 4), round(lng, 4)))

    # Add Hawaii and Alaska
    grid.append((21.3069, -157.8583))  # Honolulu
    grid.append((64.2008, -152.4937))  # Fairbanks
    grid.append((61.2181, -149.9003))  # Anchorage

    _dense_coord_grid_cache = grid
    print(f"  Built dense coordinate grid: {len(grid)} points")
    return grid


def build_dense_zip_grid(n: int = 500) -> List[str]:
    """Build an evenly-distributed set of ~n ZIP codes from ZCTA centroids.

    Sorts all ZCTAs by latitude and takes every Nth one for even
    geographic distribution.
    """
    global _dense_zip_grid_cache
    if _dense_zip_grid_cache is not None:
        return _dense_zip_grid_cache

    centroids = load_zcta_centroids(ZCTA_PATH)
    if not centroids:
        print("  WARNING: No centroids loaded, falling back to sparse grid")
        _dense_zip_grid_cache = list(US_SEARCH_GRID)
        return _dense_zip_grid_cache

    # Filter to US mainland + Hawaii + Alaska
    us_zips: List[Tuple[str, float]] = []
    for zip_code, (lat, lng) in centroids.items():
        if (24.0 <= lat <= 72.0 and -180.0 <= lng <= -66.0) or (
            17.0 <= lat <= 19.0 and -68.0 <= lng <= -64.0
        ):
            us_zips.append((zip_code, lat))

    # Sort by latitude for even geographic spread
    us_zips.sort(key=lambda x: x[1])

    step = max(1, len(us_zips) // n)
    selected = [z[0] for z in us_zips[::step]][:n]

    _dense_zip_grid_cache = selected
    print(f"  Built dense ZIP grid: {len(selected)} ZIPs from {len(us_zips)} candidates")
    return selected


# ---------------------------------------------------------------------------
# ZCTA centroid loading
# ---------------------------------------------------------------------------
def load_zcta_centroids(path: Path) -> Dict[str, Tuple[float, float]]:
    """Load ZIP -> (lat, lng) from ZCTA Gazetteer file."""
    centroids: Dict[str, Tuple[float, float]] = {}
    if not path.exists():
        print(f"WARNING: ZCTA centroids file not found at {path}")
        return centroids

    with open(path, "r") as f:
        sample = f.read(2000)
        f.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        if reader.fieldnames:
            reader.fieldnames = [h.strip() for h in reader.fieldnames]
        for row in reader:
            zip_code = (row.get("GEOID") or row.get("ZCTA5") or row.get("GEOID20") or "").strip()
            lat_str = (row.get("INTPTLAT") or row.get("INTPTLAT20") or "").strip()
            lng_str = (row.get("INTPTLONG") or row.get("INTPTLONG20") or "").strip()
            if zip_code and lat_str and lng_str:
                try:
                    centroids[zip_code] = (float(lat_str), float(lng_str))
                except ValueError:
                    continue

    print(f"  Loaded {len(centroids):,} ZCTA centroids")
    return centroids


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def safe_get(row: List[str], idx: int) -> str:
    if idx < len(row):
        return row[idx].strip()
    return ""


def parse_int(val: str) -> Optional[int]:
    if not val:
        return None
    try:
        return int(val)
    except ValueError:
        return None


def _resolve_store_url(raw_url: Optional[str], base_url: str) -> str:
    """Resolve a store URL, converting relative paths to full URLs.

    Examples:
      "/concord" + "https://www.fuddruckers.com" -> "https://www.fuddruckers.com/concord"
      "https://example.com/store" -> "https://example.com/store" (unchanged)
      "" -> ""
    """
    if not raw_url:
        return ""
    url = raw_url.strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    # Relative path - resolve against the locator's base domain
    return urljoin(base_url, url)


def parse_store_locator_column(value: str) -> Tuple[str, str]:
    """Parse the store locator column into (difficulty, url).

    Expected formats:
      "Easy - https://example.com/locations"
      "Medium - https://example.com/store-finder"
      "Hard - https://..."
      "None"
    """
    value = value.strip()
    if not value or value.lower() == "none":
        return ("None", "")
    match = re.match(r"^(Easy|Medium|Hard)\s*[-:]\s*(.*)", value, re.IGNORECASE)
    if match:
        return (match.group(1).title(), match.group(2).strip())
    if value.startswith("http"):
        return ("Easy", value)
    return ("None", "")


# ---------------------------------------------------------------------------
# Content heuristic
# ---------------------------------------------------------------------------
def _content_has_locations(html: str) -> bool:
    """Heuristic: does this HTML contain actual location data?

    Looks for multiple ZIP codes, phone numbers, and street address patterns.
    Returns True if 2+ indicators present AND content > 2000 chars.
    """
    if len(html) < 2000:
        return False

    indicators = 0
    # Multiple 5-digit ZIP codes
    zips = re.findall(r"\b\d{5}\b", html)
    if len(zips) >= 3:
        indicators += 1
    # Phone numbers (xxx-xxx-xxxx or (xxx) xxx-xxxx)
    phones = re.findall(r"\(?\d{3}\)?[-.\s]\d{3}[-.\s]\d{4}", html)
    if len(phones) >= 2:
        indicators += 1
    # Street address patterns (123 Main St)
    streets = re.findall(
        r"\b\d+\s+[A-Z][a-zA-Z]+\s+(?:St|Ave|Blvd|Dr|Rd|Ln|Way|Ct|Pl|Pkwy|Hwy)\b",
        html,
    )
    if len(streets) >= 2:
        indicators += 1
    # Address/location keywords in structured data
    kw_count = sum(
        1
        for kw in ["address", "location", "store_name", "storeNumber", "postalCode"]
        if kw.lower() in html.lower()
    )
    if kw_count >= 2:
        indicators += 1

    return indicators >= 2


def _preprocess_html_for_extraction(html: str) -> str:
    """Extract useful location data from HTML, stripping JS/CSS noise.

    Many SPAs (Next.js, React) embed location data in script tags:
    - <script id="__NEXT_DATA__"> contains page props as JSON
    - <script type="application/ld+json"> contains structured data
    These are invisible to Haiku when buried in 80K chars of framework code.

    Strategy:
    1. Extract __NEXT_DATA__ JSON and check for location arrays
    2. Extract JSON-LD structured data
    3. Strip <script> and <style> tags to reduce noise
    4. Return the most useful content within MAX_HTML_CHARS
    """
    extracted_parts: List[str] = []

    # 1. Extract __NEXT_DATA__ (Next.js page data)
    next_data_match = re.search(
        r'<script\s+id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    if next_data_match:
        next_json = next_data_match.group(1).strip()
        try:
            data = json.loads(next_json)
            if _looks_like_location_json(data):
                extracted_parts.append(f"__NEXT_DATA__ (location data):\n{next_json}")
            else:
                # Check nested props for location data
                props = data.get("props", {}).get("pageProps", {})
                for key, val in props.items():
                    if isinstance(val, (list, dict)):
                        if _looks_like_location_json(val):
                            chunk = json.dumps(val)
                            extracted_parts.append(f"__NEXT_DATA__.props.pageProps.{key}:\n{chunk}")
        except (json.JSONDecodeError, AttributeError):
            pass

    # 2. Extract JSON-LD structured data
    ld_matches = re.findall(
        r'<script\s+type="application/ld\+json"[^>]*>(.*?)</script>',
        html,
        re.DOTALL,
    )
    for ld_json in ld_matches:
        try:
            data = json.loads(ld_json.strip())
            # Look for LocalBusiness, Restaurant, Store schema types
            schema_type = ""
            schema_types: set = set()
            if isinstance(data, dict):
                raw_type = data.get("@type", "")
                schema_type = raw_type if isinstance(raw_type, str) else ""
                schema_types = set(raw_type) if isinstance(raw_type, list) else {schema_type}
            elif isinstance(data, list) and data:
                raw_type = data[0].get("@type", "") if isinstance(data[0], dict) else ""
                schema_type = raw_type if isinstance(raw_type, str) else ""
                schema_types = set(raw_type) if isinstance(raw_type, list) else {schema_type}
            location_types = {
                "LocalBusiness",
                "Restaurant",
                "FoodEstablishment",
                "Store",
                "Organization",
                "Place",
            }
            if schema_types & location_types or _looks_like_location_json(data):
                extracted_parts.append(f"JSON-LD ({schema_type}):\n{ld_json.strip()}")
        except json.JSONDecodeError:
            pass

    # 3. If we found embedded data, prioritize it
    if extracted_parts:
        embedded = "\n\n---\n\n".join(extracted_parts)
        if len(embedded) > 2000:
            return embedded[:MAX_HTML_CHARS]

    # 4. Strip <script> and <style> tags to reduce noise in page HTML
    cleaned = re.sub(r"<script\b[^>]*>.*?</script>", "", html, flags=re.DOTALL)
    cleaned = re.sub(r"<style\b[^>]*>.*?</style>", "", cleaned, flags=re.DOTALL)
    # Collapse whitespace
    cleaned = re.sub(r"\s{3,}", "\n", cleaned)
    cleaned = cleaned.strip()

    # If cleaned HTML is much smaller but still has location indicators, use it
    if cleaned and len(cleaned) > 500:
        return cleaned[:MAX_HTML_CHARS]

    # Fallback to original
    return html[:MAX_HTML_CHARS]


# ---------------------------------------------------------------------------
# Fetch store locator page
# ---------------------------------------------------------------------------
def fetch_locator_page(url: str, client: httpx.Client) -> Optional[str]:
    """Fetch a store locator page, return HTML/text content."""
    try:
        resp = client.get(
            url,
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "application/json;q=0.8,*/*;q=0.7"
                ),
            },
        )
        if resp.status_code != 200:
            print(f"    HTTP {resp.status_code} for {url}")
            return None
        return resp.text[:MAX_HTML_CHARS]
    except Exception as e:
        print(f"    Fetch error: {str(e)[:200]}")
        return None


# ---------------------------------------------------------------------------
# Tier 1: Scraping service with JS rendering
# ---------------------------------------------------------------------------
def fetch_via_service(url: str, client: httpx.Client) -> Optional[FetchResult]:
    """Fetch via ScraperAPI (or compatible) with JS rendering enabled."""
    if not SCRAPING_SERVICE_API_KEY:
        return None
    try:
        service_url = (
            f"{SCRAPING_SERVICE_URL}"
            f"?api_key={SCRAPING_SERVICE_API_KEY}"
            f"&render=true"
            f"&url={quote_plus(url)}"
        )
        resp = client.get(service_url, timeout=60)
        if resp.status_code != 200:
            print(f"    Scraping service HTTP {resp.status_code}")
            return None
        html = resp.text[:MAX_HTML_CHARS]
        return FetchResult(html=html, method="service", status_code=resp.status_code)
    except Exception as e:
        print(f"    Scraping service error: {str(e)[:200]}")
        return None


# ---------------------------------------------------------------------------
# Tier 2: Playwright with API interception
# ---------------------------------------------------------------------------
def _looks_like_location_json(data: Any) -> bool:
    """Check if a parsed JSON response looks like location data.

    Searches up to 3 levels deep for address-like field names to handle
    APIs that nest address info under contactDetails, geoDetails, etc.
    """
    items: List[Any] = []
    if isinstance(data, list):
        items = data[:5]
    elif isinstance(data, dict):
        # Common wrapper patterns: {results: [...]}, {data: [...]}, {stores: [...]}
        for key in ("results", "data", "stores", "locations", "items", "response"):
            val = data.get(key)
            if isinstance(val, list) and val:
                items = val[:5]
                break
        if not items and any(
            k in data for k in ("address", "city", "state", "lat", "lng", "latitude")
        ):
            items = [data]

    if not items:
        return False

    # Check if items have address-like keys (search up to 3 levels deep)
    address_keys = {
        "address",
        "city",
        "state",
        "zip",
        "lat",
        "lng",
        "latitude",
        "longitude",
        "postalcode",
        "stateprovince",
        "streetaddress",
        "address1",
        "postal_code",
        "store_name",
        "storename",
        "line1",
        "cityname",
        "stateprovinceCode",
        "countrycode",
        "geodetails",
        "contactdetails",
    }

    def _has_address_keys(obj: Any, depth: int = 0) -> bool:
        if not isinstance(obj, dict) or depth > 2:
            return False
        overlap = set(k.lower() for k in obj.keys()) & address_keys
        if len(overlap) >= 2:
            return True
        # Recurse into nested dicts
        for v in obj.values():
            if isinstance(v, dict) and _has_address_keys(v, depth + 1):
                return True
        return False

    for item in items:
        if _has_address_keys(item):
            return True
    return False


def _extract_items_from_json(data: Any) -> List[Dict[str, Any]]:
    """Extract location item dicts from various JSON response structures."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if isinstance(data, dict):
        # Check for maplist pattern: JSON blocks embedded in an HTML string
        # Used by RioSEO-powered store locators (Applebee's, etc.)
        maplist = data.get("maplist")
        if isinstance(maplist, str) and len(maplist) > 100:
            items = _extract_items_from_maplist(maplist)
            if items:
                return items

        # Try common wrapper keys
        for key in (
            "results",
            "data",
            "stores",
            "locations",
            "items",
            "response",
            "restaurants",
            "storeList",
            "Features",
            "features",
            "markers",
            "searchResults",
            "nearbyStores",
            "poiList",
        ):
            val = data.get(key)
            if isinstance(val, list) and val:
                return [item for item in val if isinstance(item, dict)]

        # Two-level nesting: {data: {stores: [...]}}
        for outer_key in ("data", "response", "result", "payload"):
            outer = data.get(outer_key)
            if isinstance(outer, dict):
                for inner_key in ("results", "stores", "locations", "items"):
                    val = outer.get(inner_key)
                    if isinstance(val, list) and val:
                        return [item for item in val if isinstance(item, dict)]

        # Single location object
        if any(k.lower() in ("address", "city", "state", "latitude", "lat") for k in data.keys()):
            return [data]

    return []


def _extract_items_from_maplist(maplist_html: str) -> List[Dict[str, Any]]:
    """Extract JSON location objects embedded in RioSEO maplist HTML strings.

    RioSEO store locators return a 'maplist' field containing an HTML string
    with comma-separated JSON objects inside a <div> tag, like:
      <div class="tlsmap_list">{"fid":"1","city":"NYC",...},{"fid":"2",...},</div>

    Strategy: strip HTML tags, wrap in [], parse as JSON array.
    """
    # Strip HTML tags
    clean = re.sub(r"<[^>]+>", "", maplist_html).strip()
    if not clean:
        return []

    # Remove trailing comma(s) and whitespace
    clean = clean.rstrip().rstrip(",")

    # Wrap in array brackets and parse
    try:
        arr = json.loads("[" + clean + "]")
        if isinstance(arr, list):
            return [item for item in arr if isinstance(item, dict) and "city" in item]
    except json.JSONDecodeError:
        pass

    return []


def _map_location_fields(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Map API-specific field names to our standard format."""
    # Build a case-insensitive lookup by flattening all nested dicts
    # This handles APIs that nest address data deeply, e.g.:
    #   contactDetails.address.line1, geoDetails.latitude
    ci: Dict[str, Any] = {}

    def _flatten(obj: Dict[str, Any], depth: int = 0) -> None:
        for k, v in obj.items():
            kl = k.lower()
            # Don't overwrite existing keys (prefer top-level values)
            if kl not in ci:
                ci[kl] = v
            # Recurse into nested dicts (up to 3 levels)
            if isinstance(v, dict) and depth < 3:
                _flatten(v, depth + 1)

    _flatten(item)

    # Map address field
    address = ""
    for key in (
        "address_1",
        "address1",
        "street",
        "streetaddress",
        "street_address",
        "addr1",
        "line1",
        "address_line_1",
        "addressline1",
    ):
        if ci.get(key):
            address = str(ci[key]).strip()
            break
    if not address:
        raw_addr = ci.get("address", "")
        if isinstance(raw_addr, str) and raw_addr:
            address = raw_addr.strip()

    # Map city
    city = ""
    for key in ("city", "locality", "town", "cityname", "city_name"):
        if ci.get(key):
            city = str(ci[key]).strip()
            break

    # Map state (normalize full names like "Ohio" -> "OH")
    state = ""
    for key in (
        "state",
        "region",
        "stateprovince",
        "state_province",
        "statecode",
        "province",
        "stateabbreviation",
        "stateprovincecode",
        "state_code",
    ):
        if ci.get(key):
            state = _normalize_state(str(ci[key]))
            break

    # Map ZIP (normalize integers, +4 extensions, non-numeric chars)
    zip_code = ""
    for key in ("zip", "postalcode", "postal_code", "zipcode", "zip_code", "post_code"):
        if ci.get(key):
            zip_code = _normalize_zip(ci[key])
            break

    if not address or not city or not state or not zip_code:
        return None

    # Map optional fields
    phone = ""
    for key in ("phone", "phonenumber", "telephone", "phone_number", "local_phone"):
        if ci.get(key):
            phone = str(ci[key]).strip()
            break

    name = ""
    for key in (
        "name",
        "storename",
        "store_name",
        "title",
        "locationname",
        "displayname",
        "publicname",
        "location_name",
        "location_display_name",
    ):
        if ci.get(key):
            name = str(ci[key]).strip()
            break

    store_url = ""
    for key in ("url", "store_url", "storeurl", "link", "page_url", "pageurl"):
        if ci.get(key):
            store_url = str(ci[key]).strip()
            break

    hours = ""
    for key in ("hours", "storehours", "store_hours", "operatinghours"):
        val = ci.get(key)
        if val:
            if isinstance(val, list):
                hours = "; ".join(str(h) for h in val)
            else:
                hours = str(val).strip()
            break

    suite_raw = (
        ci.get("suite") or ci.get("address2") or ci.get("address_2")
        or ci.get("unit") or ci.get("line2") or ""
    )
    suite = str(suite_raw).strip() if suite_raw else ""

    return {
        "name": name,
        "address": address,
        "suite": suite,
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "hours": hours,
        "store_url": store_url,
    }


def _is_pre_parsed_location(item: Dict[str, Any]) -> bool:
    """Check if a dict is already in our standard location format."""
    return isinstance(item, dict) and "address" in item and "city" in item and "state" in item


def extract_locations_from_json(
    json_str: str,
    merchant_name: str,
) -> List[Dict[str, Any]]:
    """Parse location data directly from JSON API responses.

    Handles common wrapper formats and field naming conventions
    without needing Haiku LLM calls. Supports concatenated responses
    separated by '---'. Also handles pre-parsed location arrays
    (from incremental parsing in replay/search).
    """
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # Try splitting on separator (concatenated API responses)
        parts = json_str.split("\n---\n")
        all_locations: List[Dict[str, Any]] = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            try:
                chunk_data = json.loads(part)
                items = _extract_items_from_json(chunk_data)
                for item in items:
                    loc = _map_location_fields(item)
                    if loc:
                        all_locations.append(loc)
            except json.JSONDecodeError:
                continue
        return all_locations

    # Check if this is already a pre-parsed list of standard locations
    # (from incremental parsing in _try_replay_api_in_browser or
    # fetch_via_playwright_search)
    if isinstance(data, list) and data and _is_pre_parsed_location(data[0]):
        return data

    items = _extract_items_from_json(data)
    return [loc for loc in (_map_location_fields(item) for item in items) if loc]


def fetch_via_playwright(url: str) -> Optional[FetchResult]:
    """Fetch with headless Playwright, intercept API responses for location data."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "    Playwright not installed. Run: pip install -e '.[scraping]' "
            "&& playwright install chromium"
        )
        return None

    captured_apis: List[Dict[str, Any]] = []
    api_endpoints: List[str] = []

    def on_response(response: Any) -> None:
        try:
            content_type = response.headers.get("content-type", "")
            if "application/json" not in content_type:
                return
            body = response.text()
            if len(body) < 1000:
                return
            data = json.loads(body)
            if _looks_like_location_json(data):
                # Capture original request headers for replay
                req_headers: Dict[str, str] = {}
                try:
                    req_headers = dict(response.request.headers)
                except Exception:
                    pass
                captured_apis.append(
                    {
                        "url": response.url,
                        "data": data,
                        "body": body,
                        "request_headers": req_headers,
                    }
                )
                api_endpoints.append(response.url)
        except Exception:
            pass

    pw = None
    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        # Register listener BEFORE navigation
        page.on("response", on_response)

        try:
            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)
        except Exception:
            # networkidle can timeout on pages with persistent connections;
            # retry with domcontentloaded which is more lenient
            print("    networkidle timeout, retrying with domcontentloaded ...")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT_MS)
            except Exception as retry_err:
                print(f"    domcontentloaded also failed: {str(retry_err)[:150]}")
                # Still try to get whatever content is available
        # Extra wait for SPA hydration
        page.wait_for_timeout(PLAYWRIGHT_WAIT_MS)

        # If we captured a good API response, try dense replay
        if captured_apis:
            best = max(captured_apis, key=lambda c: len(c["body"]))
            print(f"    Intercepted API: {best['url'][:100]}")

            # Always try dense coordinate grid replay first - even a large
            # initial response may only contain nearby locations (e.g. Applebee's
            # returns 20K chars but only ~20 locations near the default center).
            print(
                f"    Trying dense API replay "
                f"(initial response: {len(best['body']):,} chars) ..."
            )
            for api_ep in list(dict.fromkeys(api_endpoints)):  # deduplicate
                # Find matching captured API to get its original request headers
                matching = next((c for c in captured_apis if c["url"] == api_ep), None)
                req_headers = matching.get("request_headers") if matching else None
                replayed = _try_replay_api_in_browser(api_ep, page, req_headers)
                if replayed:
                    return FetchResult(
                        html=replayed,
                        method="api_replay",
                        api_endpoints=api_endpoints,
                    )

            # Dense replay failed (no lat/lng params, auth failure, etc.)
            # Return the initial API response - it may still have useful data
            print("    API replay failed, returning initial API response ...")
            return FetchResult(
                html=best["body"],
                method="playwright_api",
                api_endpoints=api_endpoints,
            )

        # Fall back to full page HTML
        content = page.content()
        return FetchResult(
            html=content[:MAX_HTML_CHARS],
            method="playwright",
            api_endpoints=api_endpoints,
        )
    except Exception as e:
        print(f"    Playwright error: {str(e)[:200]}")
        return None
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()


# ---------------------------------------------------------------------------
# Tier 3a: Direct API replay with coordinate grid
# ---------------------------------------------------------------------------
# Common location API param patterns for lat/lng/radius/limit
_COORD_PARAM_NAMES = {
    "lat": ["lat", "latitude", "originLat"],
    "lng": ["lng", "longitude", "lon", "originLng"],
    "radius": ["radius", "distance", "maxDistance", "miles"],
    "limit": ["limit", "count", "maxResults", "pageSize", "rows"],
}

# ~12 coordinates covering US regions (fewer than ZIP grid, wider radius)
US_COORD_GRID = [
    (40.7128, -74.0060),  # NYC / Northeast
    (34.0522, -118.2437),  # LA / Southwest
    (41.8781, -87.6298),  # Chicago / Midwest
    (29.7604, -95.3698),  # Houston / South Central
    (33.4484, -112.0740),  # Phoenix / Desert Southwest
    (47.6062, -122.3321),  # Seattle / Pacific NW
    (39.7392, -104.9903),  # Denver / Mountain
    (25.7617, -80.1918),  # Miami / Southeast
    (42.3601, -71.0589),  # Boston / New England
    (35.2271, -80.8431),  # Charlotte / Mid-Atlantic
    (36.1627, -86.7816),  # Nashville / Upper South
    (44.9778, -93.2650),  # Minneapolis / Upper Midwest
]


def _try_replay_api_in_browser(
    api_url: str,
    page: Any,
    original_headers: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Replay a discovered location API from within Playwright's browser session.

    Uses page.evaluate(fetch()) to call the API with the browser's cookies/session
    and the original request headers (auth tokens, API keys, etc.), sweeping across
    US coordinates with higher limit and wider radius.

    Parses each response individually and deduplicates by address to avoid
    truncation issues with large concatenated responses.
    """
    parsed = urlparse(api_url)
    params = parse_qs(parsed.query, keep_blank_values=True)
    flat_params = {k: v[0] if len(v) == 1 else v for k, v in params.items()}

    # Detect lat/lng/radius/limit param names
    lat_key = lng_key = limit_key = radius_key = None
    for k in flat_params:
        kl = k.lower()
        if kl in [n.lower() for n in _COORD_PARAM_NAMES["lat"]]:
            lat_key = k
        elif kl in [n.lower() for n in _COORD_PARAM_NAMES["lng"]]:
            lng_key = k
        elif kl in [n.lower() for n in _COORD_PARAM_NAMES["limit"]]:
            limit_key = k
        elif kl in [n.lower() for n in _COORD_PARAM_NAMES["radius"]]:
            radius_key = k

    if not lat_key or not lng_key:
        print(f"    API replay: no lat/lng params found in {api_url[:80]}")
        return None

    print(f"    API replay: lat={lat_key}, lng={lng_key}, limit={limit_key}, radius={radius_key}")

    # Build headers for replay, forwarding original auth headers
    # Filter out hop-by-hop and request-specific headers that shouldn't be replayed
    skip_headers = {
        "host",
        "content-length",
        "connection",
        "accept-encoding",
        "transfer-encoding",
        "te",
        "trailer",
        "upgrade",
    }
    replay_headers: Dict[str, str] = {"accept": "application/json"}
    if original_headers:
        for k, v in original_headers.items():
            if k.lower() not in skip_headers:
                replay_headers[k.lower()] = v
        # Ensure we keep auth headers
        auth_keys = [
            k
            for k in original_headers
            if k.lower()
            in (
                "authorization",
                "x-api-key",
                "api-key",
                "apikey",
                "x-access-token",
                "token",
            )
        ]
        if auth_keys:
            print(f"    API replay: forwarding auth headers: {auth_keys}")

    base_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    dedup = LocationDeduplicator()
    response_count = 0

    # Use Playwright's APIRequestContext to bypass CORS while keeping cookies/auth
    api_request = page.context.request

    coord_grid = build_dense_coord_grid()
    for i, (lat, lng) in enumerate(coord_grid):
        new_params = dict(flat_params)
        new_params[lat_key] = str(lat)
        new_params[lng_key] = str(lng)
        if limit_key:
            new_params[limit_key] = "200"
        if radius_key:
            new_params[radius_key] = "500"

        call_url = f"{base_url}?{urlencode(new_params)}"
        try:
            resp = api_request.get(call_url, headers=replay_headers, timeout=10_000)
            status = resp.status
            if status != 200:
                if i == 0:
                    print(f"    API replay: first call returned HTTP {status}")
                    if status in (401, 403):
                        print("    API replay: auth failure, aborting")
                        return None
                continue
            body = resp.text()
            if len(body) > 100:
                response_count += 1
                # Parse each response immediately instead of concatenating
                try:
                    chunk_data = json.loads(body)
                    items = _extract_items_from_json(chunk_data)
                    for item in items:
                        loc = _map_location_fields(item)
                        if loc:
                            dedup.add(loc)
                except json.JSONDecodeError:
                    pass
        except Exception as e:
            if i == 0:
                print(f"    API replay error ({lat},{lng}): {str(e)[:80]}")
                if "timeout" in str(e).lower():
                    print("    API replay: timeout on first call, aborting")
                    return None
            continue
        time.sleep(0.5)

    if len(dedup) > 0:
        print(
            f"    API replay: {len(dedup)} unique locations from "
            f"{response_count} responses across {len(coord_grid)} coordinates"
        )
        # Return as JSON array string so callers can parse with extract_locations_from_json
        return json.dumps(dedup.get_all())
    print("    API replay: no valid responses from any coordinate")
    return None


# ---------------------------------------------------------------------------
# Tier 3b: Playwright with search interaction (ZIP grid) - fallback
# ---------------------------------------------------------------------------
_SEARCH_INPUT_SELECTORS = [
    "input[name*='zip' i]",
    "input[name*='postal' i]",
    "input[name*='search' i]",
    "input[name*='location' i]",
    "input[placeholder*='zip' i]",
    "input[placeholder*='city' i]",
    "input[placeholder*='enter' i]",
    "input[placeholder*='search' i]",
    "input[id*='zip' i]",
    "input[id*='search' i]",
    "input[id*='location' i]",
    "#storeLocatorInput",
    ".store-locator input[type='text']",
    ".search-input",
    "input[type='search']",
    "input[type='text']",  # last resort
]

_SUBMIT_SELECTORS = [
    "button[type='submit']",
    "input[type='submit']",
    "button[aria-label*='search' i]",
    "button[class*='search' i]",
    ".store-locator button",
    "button:has-text('Search')",
    "button:has-text('Find')",
    "button:has-text('Go')",
]


def fetch_via_playwright_search(
    url: str,
    merchant_name: str,
) -> Optional[FetchResult]:
    """Search-based locator scraping: type ZIP codes, capture results.

    Parses each API response incrementally during the search loop to avoid
    truncation issues when hundreds of responses are captured.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("    Playwright not installed.")
        return None

    all_api_bodies: List[str] = []
    all_html_snippets: List[str] = []
    api_endpoints: List[str] = []
    seen_addresses: set = set()
    # Incremental location parsing: parse each API response as it arrives
    incremental_dedup = LocationDeduplicator()

    pw = None
    browser = None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )

        # Capture API responses across all searches
        captured_per_search: List[Dict[str, Any]] = []

        def on_response(response: Any) -> None:
            try:
                content_type = response.headers.get("content-type", "")
                if "application/json" not in content_type:
                    return
                body = response.text()
                if len(body) < 1000:
                    return
                data = json.loads(body)
                if _looks_like_location_json(data):
                    captured_per_search.append({"url": response.url, "body": body})
                    if response.url not in api_endpoints:
                        api_endpoints.append(response.url)
            except Exception:
                pass

        page.on("response", on_response)

        # Navigate to locator page
        try:
            page.goto(url, wait_until="networkidle", timeout=PLAYWRIGHT_TIMEOUT_MS)
        except Exception:
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=PLAYWRIGHT_TIMEOUT_MS)
            except Exception:
                pass
        page.wait_for_timeout(3000)

        # Find the search input
        search_input = None
        for selector in _SEARCH_INPUT_SELECTORS:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    search_input = el
                    break
            except Exception:
                continue

        if not search_input:
            print(f"    No search input found on {url}")
            content = page.content()
            return FetchResult(
                html=content[:MAX_HTML_CHARS],
                method="playwright",
                api_endpoints=api_endpoints,
            )

        # Find submit button selector (store as selector, not element ref)
        submit_selector = None
        for selector in _SUBMIT_SELECTORS:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    submit_selector = selector
                    break
            except Exception:
                continue

        # Store which search selector worked (re-query each iteration)
        search_selector = None
        for selector in _SEARCH_INPUT_SELECTORS:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    search_selector = selector
                    break
            except Exception:
                continue

        zip_grid = build_dense_zip_grid()
        print(f"    Searching {len(zip_grid)} ZIP codes ...")
        searched = 0
        consecutive_errors = 0
        consecutive_no_new_locs = 0
        for zip_code in zip_grid:
            captured_per_search.clear()
            try:
                # Use page-level fill (forces value even with overlays)
                if search_selector:
                    page.fill(search_selector, "", timeout=5000)
                    page.fill(search_selector, zip_code, timeout=5000)
                else:
                    consecutive_errors += 1
                    if consecutive_errors >= 3:
                        print("    3 consecutive failures, stopping")
                        break
                    continue

                # Submit via button or Enter
                if submit_selector:
                    try:
                        page.click(submit_selector, timeout=5000)
                    except Exception:
                        page.press(search_selector, "Enter", timeout=5000)
                else:
                    page.press(search_selector, "Enter", timeout=5000)

                consecutive_errors = 0

                # Wait for results
                page.wait_for_timeout(3000)

                # Collect and parse API responses from this search immediately
                new_this_zip = 0
                for cap in captured_per_search:
                    dedup_key = cap["body"][:200]
                    if dedup_key not in seen_addresses:
                        seen_addresses.add(dedup_key)
                        all_api_bodies.append(cap["body"])
                        # Parse each response immediately instead of batching
                        try:
                            chunk_data = json.loads(cap["body"])
                            items = _extract_items_from_json(chunk_data)
                            for item in items:
                                loc = _map_location_fields(item)
                                if loc and incremental_dedup.add(loc):
                                    new_this_zip += 1
                        except json.JSONDecodeError:
                            new_this_zip += 1  # count raw body as new

                # If no API captured, grab rendered HTML
                if not captured_per_search:
                    snippet = page.content()
                    snippet_key = snippet[:200]
                    if snippet_key not in seen_addresses:
                        seen_addresses.add(snippet_key)
                        all_html_snippets.append(snippet)

                searched += 1

                # Progress logging every 50 ZIPs
                if searched % 50 == 0:
                    print(
                        f"    Progress: {searched}/{len(zip_grid)} ZIPs, "
                        f"{len(incremental_dedup)} locations, "
                        f"{len(all_api_bodies)} API responses"
                    )

                # Early termination: only count as "no new" when we got
                # API responses AND parsed them but found no new locations.
                # This avoids false early stops when JSON parsing fails.
                if new_this_zip > 0:
                    consecutive_no_new_locs = 0
                elif captured_per_search and len(incremental_dedup) > 0:
                    # Only count as empty if we've already found some locations
                    # (proves parsing works) but this ZIP added nothing new
                    consecutive_no_new_locs += 1

                if consecutive_no_new_locs >= 50 and len(incremental_dedup) >= 10:
                    print(
                        f"    Early stop: no new locations for 50 "
                        f"consecutive ZIPs ({len(incremental_dedup)} total locations)"
                    )
                    break
                if searched >= 100 and not all_api_bodies and not all_html_snippets:
                    print(f"    Aborting: {searched} ZIPs searched, 0 results")
                    break

            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors >= 3:
                    print(f"    ZIP {zip_code}: {str(e)[:80]}")
                    print("    3 consecutive failures interacting with search, stopping")
                    break
                continue

            # Rate limit between searches
            time.sleep(2)

        print(
            f"    Searched {searched}/{len(zip_grid)} ZIPs, "
            f"captured {len(all_api_bodies)} API responses, "
            f"{len(all_html_snippets)} HTML snippets, "
            f"{len(incremental_dedup)} unique locations parsed"
        )

        # Return incrementally parsed locations as JSON if we have them
        if len(incremental_dedup) > 0:
            return FetchResult(
                html=json.dumps(incremental_dedup.get_all()),
                method="playwright_search",
                api_endpoints=api_endpoints,
            )
        # Fall back to raw API bodies for Haiku extraction (truncated)
        elif all_api_bodies:
            combined = "\n---\n".join(all_api_bodies)
            return FetchResult(
                html=combined[:MAX_HTML_CHARS],
                method="playwright_search",
                api_endpoints=api_endpoints,
            )
        elif all_html_snippets:
            combined = "\n---\n".join(all_html_snippets)
            return FetchResult(
                html=combined[:MAX_HTML_CHARS],
                method="playwright_search",
                api_endpoints=api_endpoints,
            )
        else:
            return FetchResult(
                html=page.content()[:MAX_HTML_CHARS],
                method="playwright_search",
                api_endpoints=api_endpoints,
            )

    except Exception as e:
        print(f"    Playwright search error: {str(e)[:200]}")
        return None
    finally:
        if browser:
            browser.close()
        if pw:
            pw.stop()


# ---------------------------------------------------------------------------
# Tiered fetch orchestrator
# ---------------------------------------------------------------------------
def fetch_page_tiered(
    url: str,
    client: httpx.Client,
    fetch_mode: str,
    merchant_name: str,
) -> Optional[FetchResult]:
    """Orchestrate fetch tiers based on --fetch-mode.

    Modes:
      static     - httpx only (original behavior)
      service    - ScraperAPI only
      playwright - Playwright only (with API interception)
      auto       - Smart cascade: service -> playwright -> playwright_search
    """
    if fetch_mode == "static":
        html = fetch_locator_page(url, client)
        if html:
            return FetchResult(html=html, method="static")
        return None

    if fetch_mode == "service":
        return fetch_via_service(url, client)

    if fetch_mode == "playwright":
        return fetch_via_playwright(url)

    # Auto mode: cascade with smart escalation
    if fetch_mode == "auto":
        # Step 1: Try scraping service (fastest JS-rendered fetch)
        if SCRAPING_SERVICE_API_KEY:
            print("    Tier 1: scraping service ...")
            result = fetch_via_service(url, client)
            if result and _content_has_locations(result.html):
                print(f"    Tier 1 success ({len(result.html):,} chars)")
                return result
            if result:
                print("    Tier 1 fetched but no locations detected, escalating ...")
        else:
            print("    Tier 1: skipped (no SCRAPING_SERVICE_API_KEY)")

        # Step 2: Playwright with API interception + auto replay
        # (handles large API responses, small geo-limited APIs with coord replay,
        #  and falls back to page HTML)
        print("    Tier 2: Playwright + API interception ...")
        result = fetch_via_playwright(url)
        if result and result.method in ("playwright_api", "api_replay"):
            print(f"    Tier 2 success: {result.method} ({len(result.html):,} chars)")
            return result
        if result and _content_has_locations(result.html):
            print(f"    Tier 2 success: page content ({len(result.html):,} chars)")
            return result
        if result:
            print("    Tier 2 fetched but no locations detected, escalating ...")

        # Step 3: Try Playwright with ZIP grid search (last resort)
        print("    Tier 3: Playwright search (ZIP grid) ...")
        result = fetch_via_playwright_search(url, merchant_name)
        if result:
            print(f"    Tier 3 complete ({len(result.html):,} chars)")
            return result

        print("    All tiers exhausted, no content retrieved")
        return None

    print(f"    Unknown fetch mode: {fetch_mode}")
    return None


# ---------------------------------------------------------------------------
# Claude Haiku extraction
# ---------------------------------------------------------------------------
def _repair_truncated_json(raw: str) -> Optional[List[Dict[str, Any]]]:
    """Try to salvage locations from truncated JSON output.

    When Haiku hits max_tokens, the JSON array gets cut off mid-object.
    Strategy: find the last complete object (ending with '}') and close the array.
    """
    # Find the last complete object in the array
    last_close = raw.rfind("}")
    if last_close < 0:
        return None
    # Find the matching array start
    arr_start = raw.find("[")
    if arr_start < 0:
        return None
    # Truncate to last complete object and close the array
    candidate = raw[arr_start : last_close + 1] + "]"
    try:
        data = json.loads(candidate)
        if isinstance(data, list):
            return data
    except json.JSONDecodeError:
        # Try with fewer objects - maybe the last one was incomplete too
        # Walk backwards to find a clean cut point
        pos = last_close
        for _ in range(5):
            pos = raw.rfind("}", 0, pos)
            if pos < 0:
                break
            candidate = raw[arr_start : pos + 1] + "]"
            try:
                data = json.loads(candidate)
                if isinstance(data, list):
                    return data
            except json.JSONDecodeError:
                continue
    return None


def extract_locations_with_haiku(
    html_content: str,
    merchant_name: str,
    locator_url: str,
) -> List[Dict[str, Any]]:
    """Send page content to Claude Haiku for structured location extraction."""
    import anthropic

    # Truncate to prevent oversized LLM calls
    html_content = html_content[:MAX_HTML_CHARS]

    # Preprocess HTML to extract embedded data and strip noise
    # (skip for raw JSON from API interception - already clean)
    if "<html" in html_content[:500].lower() or "<script" in html_content[:2000].lower():
        processed = _preprocess_html_for_extraction(html_content)
        if len(processed) < len(html_content):
            print(f"    Preprocessed: {len(html_content):,} -> {len(processed):,} chars")
        html_content = processed

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = (
        "You are a data extraction specialist. Extract store location data "
        "from the provided HTML/text content of a store locator page.\n\n"
        "Return a JSON array of location objects. Each object should have:\n"
        '- "name": Store/location name (string, optional)\n'
        '- "address": Street address (string, required)\n'
        '- "suite": Suite/unit number (string, optional)\n'
        '- "city": City name (string, required)\n'
        '- "state": 2-letter state code (string, required, e.g. "CA")\n'
        '- "zip": 5-digit ZIP code (string, required)\n'
        '- "phone": Phone number (string, optional)\n'
        '- "hours": Store hours as a single string (string, optional)\n'
        '- "store_url": Individual store page URL (string, optional)\n\n'
        "RULES:\n"
        "- Only include US locations\n"
        "- ZIP must be exactly 5 digits (strip any +4 extension)\n"
        "- State must be a valid 2-letter US state code\n"
        "- If you can't determine address components, skip that location\n"
        "- If the page contains no parseable locations, return an empty array []\n"
        "- Return ONLY the JSON array, no markdown fences or extra text"
    )

    user_prompt = (
        f'Extract all store locations for "{merchant_name}" '
        f"from this store locator page ({locator_url}).\n\n"
        f"PAGE CONTENT:\n{html_content}\n\n"
        "Return the JSON array of locations."
    )

    try:
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=16384,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        locations = json.loads(raw)
        if isinstance(locations, list):
            return locations
        return []
    except json.JSONDecodeError as e:
        # Handle "Extra data" - Haiku sometimes returns [] followed by explanation
        if "Extra data" in str(e):
            try:
                decoder = json.JSONDecoder()
                locations, _ = decoder.raw_decode(raw)
                if isinstance(locations, list):
                    return locations
            except (json.JSONDecodeError, ValueError):
                pass
        # Handle truncated JSON (Unterminated string, etc.) - output hit max_tokens
        if "Unterminated" in str(e) or "Expecting" in str(e):
            repaired = _repair_truncated_json(raw)
            if repaired:
                print(f"    Haiku output truncated, recovered {len(repaired)} locations")
                return repaired
        print(f"    Haiku JSON parse error: {str(e)[:200]}")
        return []
    except Exception as e:
        print(f"    Haiku extraction error: {str(e)[:200]}")
        return []


def extract_locations_chunked(
    content: str,
    merchant_name: str,
    locator_url: str,
    chunk_size: int = 60_000,
) -> List[Dict[str, Any]]:
    """Split large content and extract locations via Haiku in chunks.

    Handles content that exceeds Haiku's effective processing limit
    by splitting into smaller chunks and deduplicating results.
    """
    if len(content) <= MAX_HTML_CHARS:
        return extract_locations_with_haiku(content, merchant_name, locator_url)

    # Split on separator if present (concatenated API responses)
    if "\n---\n" in content:
        parts = content.split("\n---\n")
    else:
        # Split by character count
        parts = [content[i : i + chunk_size] for i in range(0, len(content), chunk_size)]

    all_locations: List[Dict[str, Any]] = []
    seen_keys: set = set()

    # Process in batches
    batch: List[str] = []
    batch_chars = 0

    for part in parts:
        part = part.strip()
        if not part:
            continue
        batch.append(part)
        batch_chars += len(part)

        if batch_chars >= chunk_size:
            combined = "\n---\n".join(batch)
            locs = extract_locations_with_haiku(
                combined[:MAX_HTML_CHARS], merchant_name, locator_url
            )
            for loc in locs:
                key = (
                    (loc.get("address") or "").lower().strip(),
                    (loc.get("city") or "").lower().strip(),
                    (loc.get("state") or "").upper().strip(),
                    (loc.get("zip") or "").strip(),
                )
                if key not in seen_keys:
                    seen_keys.add(key)
                    all_locations.append(loc)
            batch = []
            batch_chars = 0

    # Process remaining batch
    if batch:
        combined = "\n---\n".join(batch)
        locs = extract_locations_with_haiku(combined[:MAX_HTML_CHARS], merchant_name, locator_url)
        for loc in locs:
            key = (
                (loc.get("address") or "").lower().strip(),
                (loc.get("city") or "").lower().strip(),
                (loc.get("state") or "").upper().strip(),
                (loc.get("zip") or "").strip(),
            )
            if key not in seen_keys:
                seen_keys.add(key)
                all_locations.append(loc)

    return all_locations


# ---------------------------------------------------------------------------
# Sitemap discovery strategy
# ---------------------------------------------------------------------------
def discover_locations_via_sitemap(
    base_url: str,
    merchant_name: str,
    http_client: httpx.Client,
) -> List[Dict[str, Any]]:
    """Try to find store locations via sitemap XML.

    Strategy:
    1. Check robots.txt for Sitemap: directives
    2. Try common sitemap URLs
    3. Parse sitemap XML for location URLs
    4. Fetch location pages in batches and extract addresses
    """
    sitemap_urls: List[str] = []

    # Check robots.txt
    try:
        resp = http_client.get(
            f"{base_url}/robots.txt",
            follow_redirects=True,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        if resp.status_code == 200:
            for line in resp.text.splitlines():
                if line.strip().lower().startswith("sitemap:"):
                    url = line.split(":", 1)[1].strip()
                    # Handle "Sitemap: https://..." where split on first : gets "//..."
                    if not url.startswith("http"):
                        url = "https:" + url if url.startswith("//") else url
                    if url.startswith("http"):
                        sitemap_urls.append(url)
    except Exception:
        pass

    # Try common sitemap URLs
    for path in (
        "/sitemap.xml",
        "/sitemap_index.xml",
        "/sitemap-locations.xml",
        "/locations-sitemap.xml",
        "/store-sitemap.xml",
    ):
        sitemap_urls.append(f"{base_url}{path}")

    # Deduplicate
    sitemap_urls = list(dict.fromkeys(sitemap_urls))

    # Parse sitemaps to find location URLs
    location_urls: List[str] = []
    location_patterns = re.compile(
        r"/(?:locations?|stores?|restaurants?|find-a-store|storelocator)/",
        re.IGNORECASE,
    )

    ns = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}

    for sitemap_url in sitemap_urls:
        try:
            resp = http_client.get(
                sitemap_url,
                follow_redirects=True,
                timeout=15,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code != 200:
                continue

            root = ET.fromstring(resp.text)

            # Check if this is a sitemap index
            sub_sitemaps = root.findall(".//sm:sitemap/sm:loc", ns)
            if sub_sitemaps:
                for loc_el in sub_sitemaps:
                    sub_url = (loc_el.text or "").strip()
                    if location_patterns.search(sub_url):
                        try:
                            sub_resp = http_client.get(
                                sub_url,
                                follow_redirects=True,
                                timeout=15,
                                headers={"User-Agent": "Mozilla/5.0"},
                            )
                            if sub_resp.status_code == 200:
                                sub_root = ET.fromstring(sub_resp.text)
                                for url_el in sub_root.findall(".//sm:url/sm:loc", ns):
                                    page_url = (url_el.text or "").strip()
                                    if page_url:
                                        location_urls.append(page_url)
                        except Exception:
                            continue
                        time.sleep(0.5)

            # Check for direct URL entries
            for url_el in root.findall(".//sm:url/sm:loc", ns):
                page_url = (url_el.text or "").strip()
                if page_url and location_patterns.search(page_url):
                    location_urls.append(page_url)

        except ET.ParseError:
            continue
        except Exception:
            continue

    # Deduplicate
    location_urls = list(dict.fromkeys(location_urls))

    if not location_urls:
        print("    Sitemap: no location URLs found")
        return []

    # Filter to individual location pages (3+ path segments)
    individual_urls = []
    for url in location_urls:
        path = urlparse(url).path.rstrip("/")
        segments = [s for s in path.split("/") if s]
        if len(segments) >= 3:
            individual_urls.append(url)

    if not individual_urls:
        individual_urls = location_urls

    print(f"    Sitemap: found {len(individual_urls)} potential location URLs")

    # Cap at 5000
    individual_urls = individual_urls[:5000]

    # Fetch pages in batches and extract with Haiku
    all_locations: List[Dict[str, Any]] = []
    batch_size = 20

    for batch_start in range(0, len(individual_urls), batch_size):
        batch = individual_urls[batch_start : batch_start + batch_size]
        batch_html_parts: List[str] = []

        for page_url in batch:
            try:
                resp = http_client.get(
                    page_url,
                    follow_redirects=True,
                    timeout=10,
                    headers={"User-Agent": "Mozilla/5.0"},
                )
                if resp.status_code == 200:
                    processed = _preprocess_html_for_extraction(resp.text[:30_000])
                    batch_html_parts.append(f"--- PAGE: {page_url} ---\n{processed[:5000]}")
            except Exception:
                continue
            time.sleep(0.3)

        if batch_html_parts:
            combined = "\n\n".join(batch_html_parts)
            locs = extract_locations_with_haiku(combined, merchant_name, f"{base_url}/sitemap")
            all_locations.extend(locs)

        progress = min(batch_start + batch_size, len(individual_urls))
        print(
            f"    Sitemap progress: {progress}/{len(individual_urls)} pages, "
            f"{len(all_locations)} locations extracted"
        )

    return all_locations


# ---------------------------------------------------------------------------
# State directory strategy
# ---------------------------------------------------------------------------
def discover_locations_via_state_pages(
    base_url: str,
    merchant_name: str,
    http_client: httpx.Client,
) -> List[Dict[str, Any]]:
    """Try to find locations via state directory pages.

    Many chain restaurants/stores have /locations/{state} pages listing
    all locations in that state.
    """
    patterns = [
        "{base}/locations/{state_name}",
        "{base}/locations/{state_code}",
        "{base}/stores/{state_name}",
        "{base}/restaurants/{state_name}",
    ]

    # Test with Alabama first
    test_state = "alabama"
    test_code = "al"
    working_pattern = None

    for pattern in patterns:
        test_url = pattern.format(base=base_url, state_name=test_state, state_code=test_code)
        try:
            resp = http_client.get(
                test_url,
                follow_redirects=True,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200 and len(resp.text) > 2000:
                if _content_has_locations(resp.text):
                    working_pattern = pattern
                    print(f"    State pages: pattern works: {pattern}")
                    break
        except Exception:
            continue

    if not working_pattern:
        print("    State pages: no working URL pattern found")
        return []

    # Fetch all state pages
    all_locations: List[Dict[str, Any]] = []

    for state_code, state_name in sorted(US_STATES.items()):
        state_url = working_pattern.format(
            base=base_url,
            state_name=state_name,
            state_code=state_code.lower(),
        )
        try:
            resp = http_client.get(
                state_url,
                follow_redirects=True,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            if resp.status_code == 200 and len(resp.text) > 1000:
                processed = _preprocess_html_for_extraction(resp.text[:MAX_HTML_CHARS])
                locs = extract_locations_with_haiku(processed, merchant_name, state_url)
                all_locations.extend(locs)
                if locs:
                    print(f"    {state_code}: {len(locs)} locations")
        except Exception as e:
            print(f"    {state_code}: error - {str(e)[:80]}")
            continue

        time.sleep(0.5)

    return all_locations


# ---------------------------------------------------------------------------
# Comprehensive scraping orchestrator
# ---------------------------------------------------------------------------
def scrape_merchant_comprehensive(
    merchant_name: str,
    locator_url: str,
    http_client: httpx.Client,
    strategy: str = "auto",
) -> Tuple[List[Dict[str, Any]], str]:
    """Comprehensive scraping with multiple strategies.

    Tries strategies in priority order, stopping when comprehensive
    results are found. Returns (locations, method) where locations are
    dicts with name/address/city/state/zip/phone/hours/store_url fields.
    """
    dedup = LocationDeduplicator()
    parsed = urlparse(locator_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Strategy 1: Sitemap discovery
    if strategy in ("auto", "sitemap"):
        print("  Strategy 1: Sitemap discovery ...")
        try:
            locs = discover_locations_via_sitemap(base_url, merchant_name, http_client)
            for loc in locs:
                dedup.add(loc)
            if len(dedup) >= 10:
                print(f"  Sitemap found {len(dedup)} unique locations")
                return dedup.get_all(), "sitemap"
            elif len(dedup) > 0:
                print(f"  Sitemap found {len(dedup)} locations (continuing to find more)")
        except Exception as e:
            print(f"  Sitemap error: {str(e)[:100]}")

    # Strategy 2: Playwright + API interception + dense replay
    if strategy in ("auto", "api"):
        print("  Strategy 2: Playwright + API interception ...")
        try:
            result = fetch_via_playwright(locator_url)
            if result and result.method in ("playwright_api", "api_replay"):
                # Parse JSON responses directly (no Haiku needed)
                locs = extract_locations_from_json(result.html, merchant_name)
                if not locs:
                    # Direct JSON parsing failed, try Haiku as fallback
                    locs = extract_locations_chunked(result.html, merchant_name, locator_url)
                for loc in locs:
                    dedup.add(loc)
                print(
                    f"  API ({result.method}) found {len(dedup)} unique locations"
                )
                # Only return early if we found a substantial number (100+)
                # Otherwise continue to ZIP search for more coverage
                if len(dedup) >= 100:
                    return dedup.get_all(), result.method
            elif result and _content_has_locations(result.html):
                # Page HTML has locations, extract with Haiku
                locs = extract_locations_with_haiku(result.html, merchant_name, locator_url)
                for loc in locs:
                    dedup.add(loc)
        except Exception as e:
            print(f"  API interception error: {str(e)[:100]}")

    # Strategy 3: Dense ZIP search
    if strategy in ("auto", "zip"):
        # Skip ZIP search if API already found 100+ locations
        if len(dedup) >= 100:
            print(f"  Skipping ZIP search (already have {len(dedup)} locations)")
        else:
            print("  Strategy 3: Dense ZIP search ...")
            try:
                result = fetch_via_playwright_search(locator_url, merchant_name)
                if result and result.html:
                    # Try direct JSON parsing first
                    locs = extract_locations_from_json(result.html, merchant_name)
                    if not locs:
                        # Fall back to Haiku (chunked for large content)
                        locs = extract_locations_chunked(
                            result.html, merchant_name, locator_url
                        )
                    for loc in locs:
                        dedup.add(loc)
                    if len(dedup) >= 10:
                        print(f"  ZIP search found {len(dedup)} unique locations")
            except Exception as e:
                print(f"  ZIP search error: {str(e)[:100]}")

    # If we already have good coverage from strategies 2+3, return
    if len(dedup) >= 100:
        method = "api_and_zip" if len(dedup) > 0 else "combined"
        print(f"  Total: {len(dedup)} unique locations (skipping state pages)")
        return dedup.get_all(), method

    # Strategy 4: State directory pages (only if we still need more)
    if strategy in ("auto", "state"):
        print("  Strategy 4: State directory pages ...")
        try:
            locs = discover_locations_via_state_pages(base_url, merchant_name, http_client)
            for loc in locs:
                dedup.add(loc)
            if locs:
                print(f"  State pages added {len(locs)} locations (total: {len(dedup)})")
        except Exception as e:
            print(f"  State pages error: {str(e)[:100]}")

    # Return whatever we have
    if len(dedup) > 0:
        print(f"  Combined: {len(dedup)} unique locations across all strategies")
        return dedup.get_all(), "combined"

    print("  No locations found via any strategy")
    return [], "none"


# ---------------------------------------------------------------------------
# Google Sheet operations
# ---------------------------------------------------------------------------
def ensure_scraped_tab(sheets_svc: Any, spreadsheet_id: str) -> None:
    """Create the Scraped Locations tab if it doesn't exist, write header."""
    try:
        meta = (
            sheets_svc.spreadsheets()
            .get(
                spreadsheetId=spreadsheet_id,
                fields="sheets.properties.title",
            )
            .execute()
        )
        titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if SCRAPED_TAB in titles:
            return

        # Create tab
        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": SCRAPED_TAB}}}]},
        ).execute()

        # Write header
        sheets_svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{SCRAPED_TAB}!A1",
            valueInputOption="RAW",
            body={"values": [SCRAPED_HEADER]},
        ).execute()
        print(f"  Created '{SCRAPED_TAB}' tab with header row")

    except Exception as e:
        print(f"  Warning: could not ensure tab: {str(e)[:200]}")


def append_scraped_rows(
    sheets_svc: Any,
    spreadsheet_id: str,
    rows: List[List[str]],
) -> int:
    """Append rows to the Scraped Locations tab. Returns count appended."""
    if not rows:
        return 0
    resp = (
        sheets_svc.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=f"{SCRAPED_TAB}!A:Q",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        )
        .execute()
    )
    updated = resp.get("updates", {}).get("updatedRows", len(rows))
    return updated


def read_scraped_tab(sheets_svc: Any, spreadsheet_id: str) -> List[List[str]]:
    """Read all rows from the Scraped Locations tab (skipping header)."""
    result = (
        sheets_svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range=f"{SCRAPED_TAB}!A:Q",
        )
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []
    return values[1:]  # skip header


def mark_pushed_scraped(
    sheets_svc: Any,
    spreadsheet_id: str,
    row_indices: List[int],
    timestamp: str,
) -> None:
    """Write push timestamp to column P of processed rows."""
    data = []
    for row_idx in row_indices:
        sheet_row = row_idx + 2  # 0-based data -> 1-based sheet + header
        data.append(
            {
                "range": f"{SCRAPED_TAB}!P{sheet_row}",
                "values": [[timestamp]],
            }
        )
    if data:
        sheets_svc.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"valueInputOption": "RAW", "data": data},
        ).execute()


def read_merchant_review(sheets_svc: Any, spreadsheet_id: str) -> List[List[str]]:
    """Read all rows from the Merchant Review tab."""
    result = (
        sheets_svc.spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id,
            range="Merchant Review!A:AA",
        )
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return []
    return values[1:]


# ---------------------------------------------------------------------------
# Supabase operations (used only in --push mode)
# ---------------------------------------------------------------------------
def upsert_location_v2(
    client: httpx.Client,
    data: Dict[str, Any],
) -> Optional[int]:
    """Upsert into locations_v2, matching on address1+city+state+zip."""
    params = {
        "address1": f"eq.{data['address1']}",
        "city": f"eq.{data['city']}",
        "state": f"eq.{data['state']}",
        "zip": f"eq.{data['zip']}",
        "select": "id",
        "limit": "1",
    }
    resp = client.get(
        f"{SUPABASE_URL}/rest/v1/locations_v2",
        headers=SUPABASE_HEADERS,
        params=params,
    )
    if resp.status_code == 200:
        rows = resp.json()
        if rows:
            return rows[0]["id"]

    resp = client.post(
        f"{SUPABASE_URL}/rest/v1/locations_v2",
        headers=SUPABASE_HEADERS,
        json=data,
    )
    if resp.status_code in (200, 201):
        rows = resp.json()
        if rows and isinstance(rows, list):
            return rows[0].get("id")
    else:
        print(f"    locations_v2 insert failed: HTTP {resp.status_code}: {resp.text[:200]}")
    return None


def insert_store_location(
    client: httpx.Client,
    data: Dict[str, Any],
) -> Optional[int]:
    """Insert into store_locations, dedup on merchant_id+location_id."""
    params = {
        "merchant_id": f"eq.{data['merchant_id']}",
        "location_id": f"eq.{data['location_id']}",
        "select": "id",
        "limit": "1",
    }
    resp = client.get(
        f"{SUPABASE_URL}/rest/v1/store_locations",
        headers=SUPABASE_HEADERS,
        params=params,
    )
    if resp.status_code == 200:
        rows = resp.json()
        if rows:
            return rows[0]["id"]

    resp = client.post(
        f"{SUPABASE_URL}/rest/v1/store_locations",
        headers=SUPABASE_HEADERS,
        json=data,
    )
    if resp.status_code in (200, 201):
        rows = resp.json()
        if rows and isinstance(rows, list):
            return rows[0].get("id")
    else:
        print(f"    store_locations insert failed: HTTP {resp.status_code}: {resp.text[:200]}")
    return None


# ---------------------------------------------------------------------------
# Scrape pipeline (Phase 1: scrape -> sheet)
# ---------------------------------------------------------------------------
def process_merchant_to_rows(
    merchant_name: str,
    merchant_id: Optional[int],
    locator_url: str,
    http_client: httpx.Client,
    centroids: Dict[str, Tuple[float, float]],
    fetch_mode: str = "static",
    strategy: str = "auto",
) -> Tuple[List[List[str]], Dict[str, Any]]:
    """Scrape one merchant, return (sheet_rows, stats).

    When strategy is 'legacy', uses the old tiered fetch pipeline.
    Otherwise, uses comprehensive multi-strategy scraping.
    """
    stats: Dict[str, Any] = {
        "merchant": merchant_name,
        "found": 0,
        "valid": 0,
        "skipped": 0,
        "fetch_method": "",
        "errors": [],
    }

    fetch_method = ""

    if strategy == "legacy":
        # Original tiered fetch pipeline
        print(f"  Fetching: {locator_url}")
        result = fetch_page_tiered(locator_url, http_client, fetch_mode, merchant_name)
        if not result:
            stats["errors"].append("Failed to fetch locator page (all tiers)")
            return [], stats

        html = result.html
        fetch_method = result.method
        print(f"  Fetched {len(html):,} chars via {result.method}, sending to Haiku ...")
        locations = extract_locations_with_haiku(html, merchant_name, locator_url)
        stats["found"] = len(locations)
        print(f"  Extracted {len(locations)} locations")

        # Auto mode retry
        if (
            not locations
            and fetch_mode == "auto"
            and result.method not in ("playwright_search", "api_replay")
        ):
            print("  Auto retry: escalating to Playwright ZIP search ...")
            retry = fetch_via_playwright_search(locator_url, merchant_name)
            if retry and retry.html:
                fetch_method = retry.method
                locations = extract_locations_with_haiku(retry.html, merchant_name, locator_url)
                stats["found"] = len(locations)
                print(f"  Retry extracted {len(locations)} locations")
    else:
        # Comprehensive multi-strategy scraping
        print(f"  Comprehensive scrape: {locator_url}")
        locations, fetch_method = scrape_merchant_comprehensive(
            merchant_name, locator_url, http_client, strategy
        )
        stats["found"] = len(locations)
        print(f"  Total: {len(locations)} locations via {fetch_method}")

    stats["fetch_method"] = fetch_method

    if not locations:
        return [], stats

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    sheet_rows: List[List[str]] = []

    # Build base URL for resolving relative store_url paths
    parsed = urlparse(locator_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    for loc in locations:
        address = (loc.get("address") or "").strip()
        city = (loc.get("city") or "").strip()
        state = _normalize_state(str(loc.get("state") or ""))
        zip_code = _normalize_zip(loc.get("zip") or "")

        if not address or not city or not state or not zip_code:
            stats["skipped"] += 1
            continue

        coords = centroids.get(zip_code)
        if not coords:
            stats["skipped"] += 1
            stats["errors"].append(f"No centroid for zip {zip_code}")
            continue

        lat, lng = coords
        stats["valid"] += 1

        sheet_rows.append(
            [
                merchant_name,  # A: Merchant Name
                str(merchant_id) if merchant_id else "",  # B: Merchant ID
                (loc.get("name") or "").strip(),  # C: Store Name
                address,  # D: Address
                (loc.get("suite") or "").strip(),  # E: Suite
                city,  # F: City
                state,  # G: State
                zip_code,  # H: ZIP
                (loc.get("phone") or "").strip(),  # I: Phone
                (loc.get("hours") or "").strip(),  # J: Hours
                _resolve_store_url(loc.get("store_url"), base_url),  # K: Store URL
                str(lat),  # L: Latitude
                str(lng),  # M: Longitude
                "Pending",  # N: Status
                now,  # O: Scraped At
                "",  # P: Pushed At
                fetch_method,  # Q: Fetch Method
            ]
        )

    return sheet_rows, stats


def run_scrape(args: argparse.Namespace, sheets_svc: Any) -> None:
    """Scrape store locations and write to Google Sheet for review."""
    # Load ZCTA centroids
    print("Loading ZCTA centroids ...")
    centroids = load_zcta_centroids(ZCTA_PATH)
    if not centroids:
        print("ERROR: No ZCTA centroids loaded. Cannot geocode.")
        sys.exit(1)

    # Read Merchant Review tab
    print("Reading Merchant Review tab ...")
    rows = read_merchant_review(sheets_svc, args.sheet_id)
    print(f"  Total rows: {len(rows)}")

    # Build list of merchants to process (only Status = New)
    merchants: List[Dict[str, Any]] = []
    for row in rows:
        status = safe_get(row, COL_STATUS).lower()
        if status != "new":
            continue

        name = safe_get(row, COL_NAME)
        merchant_id = parse_int(safe_get(row, COL_EXISTING_ID))
        store_locator_raw = safe_get(row, COL_STORE_LOCATOR)

        if not name or not store_locator_raw:
            continue

        difficulty, url = parse_store_locator_column(store_locator_raw)
        if not url or difficulty == "None":
            continue

        if args.merchant and name.lower() != args.merchant.lower():
            continue
        if args.difficulty and difficulty.lower() != args.difficulty.lower():
            continue
        # In static mode, skip Hard merchants unless explicitly requested
        fetch_mode = getattr(args, "fetch_mode", "static")
        if (
            not args.difficulty
            and not args.merchant
            and difficulty == "Hard"
            and fetch_mode == "static"
        ):
            continue

        merchants.append(
            {
                "name": name,
                "merchant_id": merchant_id,
                "difficulty": difficulty,
                "url": url,
            }
        )

    print(f"  Merchants with store locators: {len(merchants)}")

    # Apply pilot/skip/limit
    if args.pilot:
        easy = [m for m in merchants if m["difficulty"] == "Easy"]
        merchants = easy[:PILOT_COUNT]
        print(f"  Pilot mode: {len(merchants)} Easy merchants")
    else:
        if args.skip:
            merchants = merchants[args.skip :]
            print(f"  Skipped first {args.skip}, {len(merchants)} remaining")
        if args.limit:
            merchants = merchants[: args.limit]
            print(f"  Limited to {len(merchants)}")

    if not merchants:
        print("\nNo merchants to process. Check your filters.")
        return

    # Try to look up merchant IDs from Supabase for rows missing them
    needs_id = [m for m in merchants if not m["merchant_id"]]
    if needs_id:
        print(f"\nLooking up {len(needs_id)} merchant IDs from Supabase ...")
        with httpx.Client(timeout=30) as sb:
            for m in needs_id:
                resp = sb.get(
                    f"{SUPABASE_URL}/rest/v1/merchants",
                    headers=SUPABASE_HEADERS,
                    params={"name": f"eq.{m['name']}", "select": "id", "limit": "1"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    if data:
                        m["merchant_id"] = data[0]["id"]
                        print(f"  {m['name']} -> id={m['merchant_id']}")
                    else:
                        print(
                            f"  {m['name']} -> not in DB yet (will scrape, ID needed at push time)"
                        )

    if not merchants:
        print("No merchants to process.")
        return

    # Ensure sheet tab exists
    if not args.dry_run:
        ensure_scraped_tab(sheets_svc, args.sheet_id)

    # Process each merchant
    all_rows: List[List[str]] = []
    all_stats: List[Dict[str, Any]] = []
    total_found = 0
    total_valid = 0

    with httpx.Client(timeout=30) as http_client:
        for i, m in enumerate(merchants):
            mid_str = m["merchant_id"] or "TBD"
            print(f"\n[{i + 1}/{len(merchants)}] {m['name']} (id={mid_str}, {m['difficulty']})")

            sheet_rows, stats = process_merchant_to_rows(
                merchant_name=m["name"],
                merchant_id=m["merchant_id"],
                locator_url=m["url"],
                http_client=http_client,
                centroids=centroids,
                fetch_mode=getattr(args, "fetch_mode", "static"),
                strategy=getattr(args, "strategy", "auto"),
            )
            all_rows.extend(sheet_rows)
            all_stats.append(stats)
            total_found += stats["found"]
            total_valid += stats["valid"]

            print(
                f"  Result: {stats['found']} found, {stats['valid']} valid, "
                f"{stats['skipped']} skipped"
            )
            if stats["errors"]:
                for err in stats["errors"][:3]:
                    print(f"    Error: {err}")

            # Write this merchant's rows immediately (safe for parallel workers)
            if sheet_rows and not args.dry_run:
                try:
                    appended = append_scraped_rows(sheets_svc, args.sheet_id, sheet_rows)
                    print(f"  Written {appended} rows to sheet")
                except Exception as e:
                    print(f"  Sheet write error: {str(e)[:100]}")
            elif sheet_rows and args.dry_run:
                print(f"  [DRY RUN] Would write {len(sheet_rows)} rows")

            if i < len(merchants) - 1:
                time.sleep(THROTTLE_SECONDS)

    # Summary
    print()
    print("=" * 70)
    print("  SCRAPE SUMMARY")
    print("=" * 70)
    print(f"  Merchants processed:   {len(all_stats)}")
    print(f"  Locations found:       {total_found}")
    print(f"  Valid (written):       {total_valid}")
    if args.dry_run:
        print("  (DRY RUN - nothing written)")

    # Method breakdown
    method_counts: Dict[str, int] = {}
    for s in all_stats:
        m = s.get("fetch_method", "unknown") or "failed"
        method_counts[m] = method_counts.get(m, 0) + 1
    if method_counts:
        parts = [f"{count} via {method}" for method, count in sorted(method_counts.items())]
        print(f"  Fetch methods:         {', '.join(parts)}")

    print()
    print("  Per merchant:")
    for s in all_stats:
        err = f" [{len(s['errors'])} errors]" if s["errors"] else ""
        method = s.get("fetch_method", "") or "n/a"
        print(
            f"    {s['merchant']:30s}  found={s['found']:4d}  "
            f"valid={s['valid']:4d}  method={method}{err}"
        )

    if not args.dry_run and all_rows:
        print("\nNext steps:")
        print(f"  1. Open the Google Sheet and review the '{SCRAPED_TAB}' tab")
        print("  2. Change Status column from 'Pending' to 'Approved' for good rows")
        print("  3. Change Status to 'Rejected' for bad rows")
        print(
            f"  4. Run: python scripts/scrape_store_locations.py "
            f'--sheet-id "{args.sheet_id}" --push'
        )


# ---------------------------------------------------------------------------
# Push pipeline (Phase 2: sheet -> Supabase)
# ---------------------------------------------------------------------------
def run_push(args: argparse.Namespace, sheets_svc: Any) -> None:
    """Read approved rows from the Scraped Locations tab and push to Supabase."""
    print("Reading Scraped Locations tab ...")
    rows = read_scraped_tab(sheets_svc, args.sheet_id)
    print(f"  Total rows: {len(rows)}")

    # Filter to Approved + not yet pushed
    approved: List[Tuple[int, List[str]]] = []
    for idx, row in enumerate(rows):
        status = safe_get(row, SC_STATUS).lower()
        pushed = safe_get(row, SC_PUSHED_AT)
        if status == "approved" and not pushed:
            approved.append((idx, row))

    print(f"  Approved & not pushed: {len(approved)}")
    if not approved:
        print("No approved rows to push. Mark rows as 'Approved' first.")
        return

    inserted = 0
    skipped = 0
    errors: List[str] = []
    processed_indices: List[int] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    with httpx.Client(timeout=30) as client:
        for idx, row in approved:
            merchant_name = safe_get(row, SC_MERCHANT_NAME)
            merchant_id = parse_int(safe_get(row, SC_MERCHANT_ID))
            address = safe_get(row, SC_ADDRESS)
            city = safe_get(row, SC_CITY)
            state = safe_get(row, SC_STATE)
            zip_code = safe_get(row, SC_ZIP)

            if not merchant_id or not address or not city or not state or not zip_code:
                skipped += 1
                continue

            lat_str = safe_get(row, SC_LATITUDE)
            lng_str = safe_get(row, SC_LONGITUDE)
            try:
                lat = float(lat_str) if lat_str else 0.0
                lng = float(lng_str) if lng_str else 0.0
            except ValueError:
                lat, lng = 0.0, 0.0

            if args.dry_run:
                print(
                    f"  [DRY RUN] Would push: {merchant_name} - "
                    f"{address}, {city}, {state} {zip_code}"
                )
                inserted += 1
                processed_indices.append(idx)
                continue

            # Upsert location
            loc_data = {
                "address1": address,
                "address2": safe_get(row, SC_SUITE) or None,
                "city": city,
                "state": state,
                "zip": zip_code,
                "phone": safe_get(row, SC_PHONE) or None,
                "website_url": safe_get(row, SC_STORE_URL) or None,
                "latitude": lat,
                "longitude": lng,
                "geocode_source": "zipcode",
                "geocoded_at": now_iso,
            }
            location_id = upsert_location_v2(client, loc_data)
            if not location_id:
                errors.append(f"Location upsert failed: {address}, {city}")
                continue

            # Insert store_location
            sl_data = {
                "merchant_id": merchant_id,
                "location_id": location_id,
                "store_name": safe_get(row, SC_STORE_NAME) or None,
                "store_phone": safe_get(row, SC_PHONE) or None,
                "store_url": safe_get(row, SC_STORE_URL) or None,
                "store_hours": safe_get(row, SC_HOURS) or None,
                "is_active": True,
                "source": "store_locator_scrape",
                "scraped_at": now_iso,
            }
            sl_id = insert_store_location(client, sl_data)
            if sl_id:
                inserted += 1
                processed_indices.append(idx)
            else:
                errors.append(f"store_location insert failed: {merchant_name} loc={location_id}")

    # Mark pushed rows
    if processed_indices and not args.dry_run:
        print(f"\nMarking {len(processed_indices)} rows as pushed ...")
        mark_pushed_scraped(sheets_svc, args.sheet_id, processed_indices, timestamp)

    # Summary
    print()
    print("=" * 70)
    print("  PUSH SUMMARY")
    print("=" * 70)
    print(f"  Approved rows:     {len(approved)}")
    print(f"  Inserted:          {inserted}")
    print(f"  Skipped:           {skipped}")
    print(f"  Errors:            {len(errors)}")
    if args.dry_run:
        print("  (DRY RUN - nothing written to DB)")
    if errors:
        print("\n  Errors:")
        for e in errors[:10]:
            print(f"    - {e}")
    print()
    print("Done.")
    if not args.dry_run and inserted > 0:
        print("\nRecommended: run `python scripts/dedup_store_locations.py` to clean up dupes.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape store locations and write to sheet, or push to Supabase"
    )
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument(
        "--push",
        action="store_true",
        help="Push approved rows from sheet to Supabase (Phase 2 - after review)",
    )
    parser.add_argument(
        "--pilot", action="store_true", help=f"Scrape only first {PILOT_COUNT} Easy merchants"
    )
    parser.add_argument(
        "--difficulty", type=str, default=None, help="Filter by difficulty (Easy, Medium, Hard)"
    )
    parser.add_argument(
        "--merchant", type=str, default=None, help="Process a single merchant by name"
    )
    parser.add_argument("--limit", type=int, default=0, help="Max merchants to process")
    parser.add_argument("--skip", type=int, default=0, help="Skip first N merchants")
    parser.add_argument(
        "--fetch-mode",
        choices=["static", "service", "playwright", "auto"],
        default="static",
        dest="fetch_mode",
        help="Fetch strategy (legacy mode only): static (httpx), service (ScraperAPI), "
        "playwright (headless browser + API interception), "
        "auto (smart cascade). Default: static",
    )
    parser.add_argument(
        "--strategy",
        choices=["auto", "sitemap", "api", "zip", "state", "legacy"],
        default="auto",
        help="Scraping strategy: auto (comprehensive, tries all strategies in order), "
        "sitemap/api/zip/state (force a specific strategy), "
        "legacy (old tiered fetch pipeline, uses --fetch-mode). Default: auto",
    )
    args = parser.parse_args()

    # Validate env
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_SERVICE_ROLE_KEY")
    if not args.push and not ANTHROPIC_API_KEY:
        missing.append("ANTHROPIC_API_KEY")
    if missing:
        print(f"ERROR: Missing env vars: {', '.join(missing)}")
        sys.exit(1)

    # Validate fetch mode dependencies
    if args.strategy == "legacy":
        if args.fetch_mode == "service" and not SCRAPING_SERVICE_API_KEY:
            print("ERROR: --fetch-mode=service requires SCRAPING_SERVICE_API_KEY env var.")
            print("  Get a free key at https://www.scraperapi.com/ and add to .env")
            sys.exit(1)

        if args.fetch_mode in ("playwright", "auto"):
            try:
                from playwright.sync_api import sync_playwright  # noqa: F401
            except ImportError:
                if args.fetch_mode == "playwright":
                    print("ERROR: --fetch-mode=playwright requires playwright.")
                    print("  Install: pip install -e '.[scraping]' && playwright install chromium")
                    sys.exit(1)
                else:
                    print("WARNING: playwright not installed. Auto mode will skip Tiers 2-3.")
                    print("  Install: pip install -e '.[scraping]' && playwright install chromium")

        if args.fetch_mode == "auto" and not SCRAPING_SERVICE_API_KEY:
            print(
                "NOTE: No SCRAPING_SERVICE_API_KEY set. "
                "Auto mode will skip Tier 1 (scraping service)."
            )
    else:
        # Comprehensive strategies: api and zip need Playwright
        needs_pw = args.strategy in ("auto", "api", "zip")
        if needs_pw:
            try:
                from playwright.sync_api import sync_playwright  # noqa: F401
            except ImportError:
                if args.strategy in ("api", "zip"):
                    print(f"ERROR: --strategy={args.strategy} requires playwright.")
                    print("  Install: pip install -e '.[scraping]' && playwright install chromium")
                    sys.exit(1)
                else:
                    print(
                        "WARNING: playwright not installed. "
                        "Strategies 2 (api) and 3 (zip) will be skipped."
                    )
                    print("  Install: pip install -e '.[scraping]' && playwright install chromium")

    print("=" * 70)
    if args.push:
        print("  Push Scraped Locations -> Supabase")
    else:
        print("  Scrape Store Locations -> Google Sheet")
    print("=" * 70)
    print(f"  Sheet ID:    {args.sheet_id}")
    print(f"  Strategy:    {args.strategy}")
    if args.strategy == "legacy":
        print(f"  Fetch mode:  {args.fetch_mode}")
    print(f"  Dry run:     {args.dry_run}")
    print()

    # Google auth (read+write for both modes)
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    from googleapiclient.discovery import build as build_google

    sheets_svc = build_google("sheets", "v4", credentials=creds)

    if args.push:
        run_push(args, sheets_svc)
    else:
        run_scrape(args, sheets_svc)


if __name__ == "__main__":
    main()
