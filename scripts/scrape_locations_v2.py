#!/usr/bin/env python3
"""Second-pass store location scraper using Scrapling (DynamicFetcher / StealthyFetcher).

Targets high-value merchants that failed in the first pass (403s, SPAs that
did not render, Cloudflare-protected sites, etc.).

Three scraping strategies per merchant:
  A. API discovery   - Intercept XHR/fetch calls via page_action, replay with httpx
  B. DOM extraction  - Render the SPA, extract location cards / JSON-LD / __NEXT_DATA__
  C. Stealth fetch   - StealthyFetcher with Cloudflare bypass for blocked sites

Usage:
    # All merchants, auto strategy, 3 workers
    python scripts/scrape_locations_v2.py --sheet-id "SHEET_ID"

    # Single merchant
    python scripts/scrape_locations_v2.py --sheet-id "SHEET_ID" --merchant "CVS"

    # Force stealth strategy, 5 workers
    python scripts/scrape_locations_v2.py --sheet-id "SHEET_ID" \\
        --strategy stealth --workers 5

    # Dry run (preview only)
    python scripts/scrape_locations_v2.py --sheet-id "SHEET_ID" --dry-run

Requires: Python 3.10+, scrapling, httpx, structlog, google-api-python-client,
          google-auth, python-dotenv
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import httpx
import structlog
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")
ZCTA_PATH = _PROJECT_ROOT / "data" / "zcta_centroids.csv"

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

# Scraped Locations tab columns (must match the v1 script exactly)
SCRAPED_HEADER = [
    "merchant_name",   # A
    "merchant_id",     # B
    "store_name",      # C
    "address1",        # D
    "address2",        # E
    "city",            # F
    "state",           # G
    "zip",             # H
    "phone",           # I
    "store_hours",     # J
    "store_url",       # K
    "latitude",        # L
    "longitude",       # M
    "status",          # N
    "scraped_at",      # O
    "pushed_at",       # P
    "fetch_method",    # Q
]
SCRAPED_TAB = "Scraped Locations"

VALID_STATES: Set[str] = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

# Full state names (lowercased, hyphenated) for URL matching
STATE_NAMES: Set[str] = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new-hampshire", "new-jersey", "new-mexico", "new-york",
    "north-carolina", "north-dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode-island", "south-carolina", "south-dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west-virginia", "wisconsin", "wyoming", "district-of-columbia",
}

# ~50 ZIPs covering major US metro areas
US_SEARCH_GRID = [
    "10001", "90001", "60601", "77001", "85001", "19101", "78201",
    "92101", "75201", "95101", "78701", "32099", "46201", "94101",
    "43201", "28201", "76101", "48201", "79901", "98101", "80201",
    "20001", "02101", "37201", "73101", "89101", "97201", "38101",
    "40201", "21201", "53201", "87101", "85701", "93701", "95801",
    "64101", "30301", "68101", "33101", "55401", "74101", "33601",
    "80901", "27601", "96801", "23219", "29201", "83702", "84101",
    "70112",
]


# ---------------------------------------------------------------------------
# Hardcoded target merchants (failed in first pass)
# ---------------------------------------------------------------------------
@dataclass
class MerchantTarget:
    """A merchant to scrape in the second pass."""

    name: str
    locator_url: str
    category: str
    # Optional: known API pattern, CSS selectors, search param name
    search_param: str = "postalCode"
    search_input_selector: str = "input[type='text'], input[name*='zip'], input[name*='search'], input[name*='location'], input[placeholder*='ZIP'], input[placeholder*='zip'], input[placeholder*='city'], input[aria-label*='search']"
    result_selector: str = ".location-card, .store-result, .location-item, [data-location], .store-card, .restaurant-card, .result-item, .location-listing, .store-listing"
    notes: str = ""


MERCHANT_TARGETS: List[MerchantTarget] = [
    # ---- Restaurants ----
    MerchantTarget(
        name="Chick-Fil-A",
        locator_url="https://www.chick-fil-a.com/locations",
        category="restaurant",
        search_input_selector="input[aria-label*='Search'], input[placeholder*='address']",
        result_selector=".location-card, [data-testid*='location'], .locationCard",
    ),
    MerchantTarget(
        name="Wendy's",
        locator_url="https://locations.wendys.com/",
        category="restaurant",
        notes="yext_directory",
    ),
    MerchantTarget(
        name="Chili's",
        locator_url="https://www.chilis.com/locations",
        category="restaurant",
        search_input_selector="input[name*='search'], input[placeholder*='Enter']",
        result_selector=".location-card, .restaurant-card, [data-location]",
    ),
    MerchantTarget(
        name="Waffle House",
        locator_url="https://locations.wafflehouse.com/",
        category="restaurant",
        search_input_selector="input[type='text'], input[placeholder*='address'], input[placeholder*='zip']",
        result_selector=".location-card, .store-result, [data-location], .Directory-listLink",
    ),
    MerchantTarget(
        name="Steak 'n Shake",
        locator_url="https://www.steaknshake.com/locations",
        category="restaurant",
        search_input_selector="input[placeholder*='zip'], input[type='search']",
        result_selector=".location-card, .store-result, [data-location]",
    ),
    MerchantTarget(
        name="Long John Silver's",
        locator_url="https://www.ljsilvers.com/locations",
        category="restaurant",
        search_input_selector="input[placeholder*='zip'], input[type='text']",
        result_selector=".location-card, .store-result, .LocationCard",
    ),
    MerchantTarget(
        name="Moe's Southwest Grill",
        locator_url="https://locations.moes.com/",
        category="restaurant",
        notes="yext_directory",
    ),
    MerchantTarget(
        name="Papa John's",
        locator_url="https://locations.papajohns.com/",
        category="restaurant",
        notes="yext_directory",
    ),
    MerchantTarget(
        name="Zaxby's",
        locator_url="https://www.zaxbys.com/locations",
        category="restaurant",
        search_input_selector="input[placeholder*='zip'], input[type='text']",
        result_selector=".location-card, .store-result, [data-location]",
    ),
    MerchantTarget(
        name="CiCi's Pizza",
        locator_url="https://www.cicis.com/locations",
        category="restaurant",
        search_input_selector="input[type='text'], input[placeholder*='zip']",
        result_selector=".location-card, .store-result, [data-location]",
    ),
    MerchantTarget(
        name="Village Inn",
        locator_url="https://www.villageinn.com/locations",
        category="restaurant",
        search_input_selector="input[type='text'], input[placeholder*='zip']",
        result_selector=".location-card, .store-result, [data-location]",
    ),
    # ---- Retail ----
    MerchantTarget(
        name="Belk",
        locator_url="https://www.belk.com/stores/",
        category="retail",
        search_input_selector="input[name*='search'], input[placeholder*='zip']",
        result_selector=".store-card, .store-result, [data-store]",
    ),
    MerchantTarget(
        name="CVS",
        locator_url="https://www.cvs.com/store-locator/landing",
        category="retail",
        search_input_selector="input[name*='search'], input[placeholder*='city'], #searchInput",
        result_selector=".store-card, .store-list-item, [data-store]",
    ),
    MerchantTarget(
        name="Hy-Vee",
        locator_url="https://www.hy-vee.com/stores/",
        category="retail",
        search_input_selector="input[type='text'], input[placeholder*='zip']",
        result_selector=".store-card, .store-result, [data-store]",
    ),
    MerchantTarget(
        name="AT&T",
        locator_url="https://www.att.com/stores/",
        category="retail",
        search_input_selector="input[name*='search'], input[placeholder*='zip']",
        result_selector=".store-card, .location-card, [data-store]",
    ),
    MerchantTarget(
        name="Bealls Florida",
        locator_url="https://stores.beallsflorida.com/",
        category="retail",
        notes="yext_directory",
    ),
    # ---- Entertainment ----
    MerchantTarget(
        name="YMCA",
        locator_url="https://www.ymca.org/find-your-y",
        category="entertainment",
        search_input_selector="input[name*='search'], input[placeholder*='zip'], input[placeholder*='location']",
        result_selector=".location-card, .result-item, [data-location]",
    ),
    MerchantTarget(
        name="Cinemark",
        locator_url="https://www.cinemark.com/theatres",
        category="entertainment",
        search_input_selector="input[name*='search'], input[placeholder*='zip']",
        result_selector=".theatre-card, .location-card, [data-theatre]",
    ),
    MerchantTarget(
        name="Marcus Theatres",
        locator_url="https://www.marcustheatres.com/theatre-locations",
        category="entertainment",
        search_input_selector="input[type='text'], input[placeholder*='zip']",
        result_selector=".theatre-card, .location-card, [data-theatre]",
    ),
    # ---- Hotels ----
    MerchantTarget(
        name="Hilton",
        locator_url="https://www.hilton.com/en/locations/",
        category="hotel",
        search_input_selector="input[name*='query'], input[placeholder*='destination']",
        result_selector=".hotel-card, [data-hotel], .property-card",
        notes="Large chain, may need state-by-state",
    ),
    MerchantTarget(
        name="Marriott",
        locator_url="https://www.marriott.com/hotel-directory.mi",
        category="hotel",
        search_input_selector="input[name*='search'], input[placeholder*='destination']",
        result_selector=".hotel-card, [data-hotel], .property-card",
        notes="Directory page with state links",
    ),
    MerchantTarget(
        name="IHG / Holiday Inn",
        locator_url="https://www.ihg.com/hotels/us/en/find-hotels",
        category="hotel",
        search_input_selector="input[name*='query'], input[placeholder*='destination']",
        result_selector=".hotel-card, [data-hotel], .hotelResult",
    ),
    MerchantTarget(
        name="Wyndham / Days Inn / La Quinta",
        locator_url="https://www.wyndhamhotels.com/locations",
        category="hotel",
        search_input_selector="input[name*='search'], input[placeholder*='destination']",
        result_selector=".hotel-card, [data-hotel], .property-card",
    ),
    MerchantTarget(
        name="Best Western",
        locator_url="https://www.bestwestern.com/",
        category="hotel",
        search_input_selector="input[name*='search'], input[placeholder*='destination']",
        result_selector=".hotel-card, [data-hotel], .property-card",
    ),
    MerchantTarget(
        name="Hyatt",
        locator_url="https://www.hyatt.com/explore-hotels",
        category="hotel",
        search_input_selector="input[name*='search'], input[placeholder*='destination']",
        result_selector=".hotel-card, [data-hotel], .property-card",
    ),
    MerchantTarget(
        name="Motel 6",
        locator_url="https://www.motel6.com/en/motels.html",
        category="hotel",
        search_input_selector="input[name*='search'], input[placeholder*='destination']",
        result_selector=".hotel-card, [data-hotel], .property-card",
    ),
    MerchantTarget(
        name="Choice Hotels / Quality Inn / Comfort Suites / Econo Lodge / Rodeway Inn",
        locator_url="https://www.choicehotels.com/locations",
        category="hotel",
        search_input_selector="input[name*='search'], input[placeholder*='destination']",
        result_selector=".hotel-card, [data-hotel], .property-card",
    ),
]


# ---------------------------------------------------------------------------
# LocationDeduplicator (same as v1 script)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# ZCTA centroid loading (same as v1 script)
# ---------------------------------------------------------------------------
_zcta_cache: Optional[Dict[str, Tuple[float, float]]] = None


def load_zcta_centroids() -> Dict[str, Tuple[float, float]]:
    """Load ZIP -> (lat, lng) from ZCTA Gazetteer file."""
    global _zcta_cache
    if _zcta_cache is not None:
        return _zcta_cache

    centroids: Dict[str, Tuple[float, float]] = {}
    if not ZCTA_PATH.exists():
        log.warning("zcta_file_not_found", path=str(ZCTA_PATH))
        _zcta_cache = centroids
        return centroids

    with open(ZCTA_PATH, "r") as f:
        sample = f.read(2000)
        f.seek(0)
        delimiter = "\t" if "\t" in sample else ","
        reader = csv.DictReader(f, delimiter=delimiter)
        if reader.fieldnames:
            reader.fieldnames = [h.strip() for h in reader.fieldnames]
        for row in reader:
            zip_code = (
                row.get("GEOID") or row.get("ZCTA5") or row.get("GEOID20") or ""
            ).strip()
            lat_str = (row.get("INTPTLAT") or row.get("INTPTLAT20") or "").strip()
            lng_str = (row.get("INTPTLONG") or row.get("INTPTLONG20") or "").strip()
            if zip_code and lat_str and lng_str:
                try:
                    centroids[zip_code] = (float(lat_str), float(lng_str))
                except ValueError:
                    continue

    log.info("zcta_centroids_loaded", count=len(centroids))
    _zcta_cache = centroids
    return centroids


def build_dense_zip_grid(n: int = 500) -> List[str]:
    """Build an evenly-distributed set of ~n ZIP codes from ZCTA centroids."""
    centroids = load_zcta_centroids()
    if not centroids:
        log.warning("no_centroids_falling_back_to_sparse_grid")
        return list(US_SEARCH_GRID)

    us_zips: List[Tuple[str, float]] = []
    for zip_code, (lat, lng) in centroids.items():
        if (24.0 <= lat <= 72.0 and -180.0 <= lng <= -66.0) or (
            17.0 <= lat <= 19.0 and -68.0 <= lng <= -64.0
        ):
            us_zips.append((zip_code, lat))

    us_zips.sort(key=lambda x: x[1])
    step = max(1, len(us_zips) // n)
    selected = [z[0] for z in us_zips[::step]][:n]

    log.info("dense_zip_grid_built", count=len(selected), total_candidates=len(us_zips))
    return selected


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _resolve_store_url(raw_url: Optional[str], base_url: str) -> str:
    """Resolve a store URL, converting relative paths to full URLs."""
    if not raw_url:
        return ""
    url = raw_url.strip()
    if not url:
        return ""
    if url.startswith("http://") or url.startswith("https://"):
        return url
    return urljoin(base_url, url)


def _clean_text(text: Optional[str]) -> str:
    """Clean whitespace from extracted text."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def _extract_zip(text: str) -> str:
    """Extract a 5-digit ZIP code from a text string."""
    m = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
    return m.group(1) if m else ""


def _extract_state(text: str) -> str:
    """Extract a 2-letter state abbreviation from text."""
    m = re.search(r"\b([A-Z]{2})\b", text)
    if m and m.group(1) in VALID_STATES:
        return m.group(1)
    return ""


# ---------------------------------------------------------------------------
# Google Sheets functions (same as v1 script)
# ---------------------------------------------------------------------------
def get_sheets_service() -> Any:
    """Build and return Google Sheets API service."""
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


def ensure_scraped_tab(sheets_svc: Any, spreadsheet_id: str) -> None:
    """Create the Scraped Locations tab if it does not exist, write header."""
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

        sheets_svc.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": SCRAPED_TAB}}}]},
        ).execute()

        sheets_svc.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{SCRAPED_TAB}!A1",
            valueInputOption="RAW",
            body={"values": [SCRAPED_HEADER]},
        ).execute()
        log.info("scraped_tab_created")

    except Exception as e:
        log.warning("ensure_tab_failed", error=str(e)[:200])


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


# ---------------------------------------------------------------------------
# Supabase merchant ID lookup
# ---------------------------------------------------------------------------
def lookup_merchant_id(name: str) -> Optional[int]:
    """Look up a merchant ID from Supabase by name."""
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


# ---------------------------------------------------------------------------
# Location parsing helpers
# ---------------------------------------------------------------------------
def parse_json_ld_locations(html: str) -> List[Dict[str, Any]]:
    """Extract locations from Schema.org JSON-LD embedded in the page."""
    locations: List[Dict[str, Any]] = []
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
        except (json.JSONDecodeError, ValueError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            _extract_jsonld_item(item, locations)

    return locations


def _extract_jsonld_item(item: Any, locations: List[Dict[str, Any]]) -> None:
    """Recursively extract location info from a JSON-LD item."""
    if not isinstance(item, dict):
        return

    schema_type = item.get("@type", "")
    if isinstance(schema_type, list):
        schema_type = " ".join(schema_type)

    location_types = {
        "Restaurant", "Store", "LocalBusiness", "Hotel", "LodgingBusiness",
        "FoodEstablishment", "Place", "Organization", "MovingCompany",
        "HealthAndBeautyBusiness", "SportsActivityLocation", "MovieTheater",
        "Pharmacy", "ShoppingCenter", "DepartmentStore",
    }

    is_location = any(t in schema_type for t in location_types)
    address = item.get("address", {})
    if isinstance(address, str):
        # Some sites inline the address as a string
        return

    if is_location and isinstance(address, dict):
        loc: Dict[str, Any] = {
            "name": _clean_text(item.get("name")),
            "address": _clean_text(address.get("streetAddress")),
            "city": _clean_text(address.get("addressLocality")),
            "state": _clean_text(address.get("addressRegion", "")).upper()[:2],
            "zip": _extract_zip(address.get("postalCode", "")),
            "phone": _clean_text(item.get("telephone")),
            "store_url": item.get("url", ""),
        }
        geo = item.get("geo", {})
        if isinstance(geo, dict):
            loc["latitude"] = geo.get("latitude")
            loc["longitude"] = geo.get("longitude")

        hours = item.get("openingHoursSpecification")
        if hours:
            if isinstance(hours, list):
                parts = []
                for h in hours:
                    day = h.get("dayOfWeek", "")
                    if isinstance(day, list):
                        day = ", ".join(day)
                    opens = h.get("opens", "")
                    closes = h.get("closes", "")
                    if day and opens:
                        parts.append(f"{day}: {opens}-{closes}")
                loc["hours"] = "; ".join(parts)
            elif isinstance(hours, str):
                loc["hours"] = hours

        if loc["address"] and loc["city"]:
            locations.append(loc)

    # Recurse into nested structures
    if "department" in item:
        deps = item["department"]
        if isinstance(deps, list):
            for dep in deps:
                _extract_jsonld_item(dep, locations)
        elif isinstance(deps, dict):
            _extract_jsonld_item(deps, locations)

    if "containsPlace" in item:
        places = item["containsPlace"]
        if isinstance(places, list):
            for p in places:
                _extract_jsonld_item(p, locations)

    if "@graph" in item:
        for node in item["@graph"]:
            _extract_jsonld_item(node, locations)


def parse_next_data_locations(html: str) -> List[Dict[str, Any]]:
    """Extract locations from Next.js __NEXT_DATA__ script tag."""
    locations: List[Dict[str, Any]] = []
    pattern = re.compile(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        re.DOTALL,
    )
    match = pattern.search(html)
    if not match:
        return locations

    try:
        data = json.loads(match.group(1))
    except (json.JSONDecodeError, ValueError):
        return locations

    # Walk the entire structure looking for location-like objects
    _walk_for_locations(data, locations, depth=0)
    return locations


def parse_nuxt_data_locations(html: str) -> List[Dict[str, Any]]:
    """Extract locations from Nuxt.js state (window.__NUXT__ or __NUXT_DATA__).

    Nuxt 2 stores state in ``window.__NUXT__`` (a JS expression, not JSON).
    Nuxt 3 uses ``<script id="__NUXT_DATA__" type="application/json">``.
    We attempt the JSON variant first, then fall back to regex extraction.
    """
    locations: List[Dict[str, Any]] = []

    # Nuxt 3: JSON payload inside a script tag
    nuxt3_pattern = re.compile(
        r'<script[^>]+id=["\']__NUXT_DATA__["\'][^>]*>(.*?)</script>',
        re.DOTALL,
    )
    match = nuxt3_pattern.search(html)
    if match:
        try:
            data = json.loads(match.group(1))
            _walk_for_locations(data, locations, depth=0)
        except (json.JSONDecodeError, ValueError):
            pass

    # Nuxt 2: window.__NUXT__ assignment (try to extract the JSON-like part)
    nuxt2_pattern = re.compile(
        r"window\.__NUXT__\s*=\s*(\{.*?\})\s*;?\s*(?:</script>|$)",
        re.DOTALL,
    )
    match = nuxt2_pattern.search(html)
    if match:
        try:
            data = json.loads(match.group(1))
            _walk_for_locations(data, locations, depth=0)
        except (json.JSONDecodeError, ValueError):
            pass

    return locations


def _extract_nuxt_from_page(page: Any) -> str:
    """Extract Nuxt state directly from browser context via page.evaluate.

    Returns a JSON string of the __NUXT__ state, or empty string on failure.
    This is more reliable than regex since it evaluates the actual JS object.
    """
    try:
        result = page.evaluate(
            "typeof window.__NUXT__ !== 'undefined' "
            "? JSON.stringify(window.__NUXT__) : ''"
        )
        return result or ""
    except Exception:
        return ""


def _walk_for_locations(
    obj: Any, locations: List[Dict[str, Any]], depth: int
) -> None:
    """Recursively walk a data structure looking for location-like dicts."""
    if depth > 15:
        return

    if isinstance(obj, dict):
        # Check if this dict looks like a location
        has_address = any(
            k in obj for k in ("address", "streetAddress", "address1", "addr")
        )
        has_city = any(
            k in obj for k in ("city", "addressLocality", "locality")
        )
        has_state = any(
            k in obj for k in ("state", "addressRegion", "region", "stateCode")
        )

        if has_address and (has_city or has_state):
            loc = _dict_to_location(obj)
            if loc:
                locations.append(loc)
        else:
            for v in obj.values():
                _walk_for_locations(v, locations, depth + 1)

    elif isinstance(obj, list):
        for item in obj:
            _walk_for_locations(item, locations, depth + 1)


def _dict_to_location(d: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Convert a dict with address-like keys into a normalized location dict."""
    address = _clean_text(
        d.get("streetAddress")
        or d.get("address1")
        or d.get("address")
        or d.get("addr")
        or ""
    )
    if isinstance(address, dict):
        # address is itself a structured object
        address = _clean_text(address.get("streetAddress", ""))

    city = _clean_text(
        d.get("addressLocality")
        or d.get("city")
        or d.get("locality")
        or ""
    )
    state_raw = _clean_text(
        d.get("addressRegion")
        or d.get("state")
        or d.get("region")
        or d.get("stateCode")
        or ""
    )
    state = state_raw.upper()[:2] if state_raw else ""

    zip_raw = (
        d.get("postalCode")
        or d.get("zip")
        or d.get("zipCode")
        or d.get("postal")
        or ""
    )
    zip_code = _extract_zip(str(zip_raw))

    if not address or not city:
        return None

    loc: Dict[str, Any] = {
        "name": _clean_text(d.get("name") or d.get("storeName") or d.get("title") or ""),
        "address": address,
        "suite": _clean_text(d.get("address2") or d.get("suite") or ""),
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": _clean_text(d.get("telephone") or d.get("phone") or d.get("phoneNumber") or ""),
        "store_url": d.get("url") or d.get("storeUrl") or d.get("detailUrl") or "",
    }

    # Hours
    hours = d.get("hours") or d.get("storeHours") or d.get("openingHours") or ""
    if isinstance(hours, list):
        loc["hours"] = "; ".join(str(h) for h in hours)
    elif isinstance(hours, str):
        loc["hours"] = hours
    else:
        loc["hours"] = ""

    # Coordinates
    lat = d.get("latitude") or d.get("lat") or d.get("yext_lat")
    lng = d.get("longitude") or d.get("lng") or d.get("lon") or d.get("yext_lng")
    if lat and lng:
        try:
            loc["latitude"] = float(lat)
            loc["longitude"] = float(lng)
        except (ValueError, TypeError):
            pass

    return loc


def parse_api_json_locations(data: Any) -> List[Dict[str, Any]]:
    """Parse location data from a typical store locator API JSON response.

    Handles various common response shapes:
    - { "locations": [...] }
    - { "results": [...] }
    - { "stores": [...] }
    - { "data": { "locations": [...] } }
    - Direct list of location objects
    """
    locations: List[Dict[str, Any]] = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                loc = _dict_to_location(item)
                if loc:
                    locations.append(loc)
        return locations

    if not isinstance(data, dict):
        return locations

    # Try common top-level keys
    for key in ("locations", "results", "stores", "restaurants", "hotels",
                "properties", "items", "data", "response", "storeLocations",
                "searchResults", "nearbyStores", "features"):
        value = data.get(key)
        if isinstance(value, list) and len(value) > 0:
            for item in value:
                if isinstance(item, dict):
                    loc = _dict_to_location(item)
                    if loc:
                        locations.append(loc)
            if locations:
                return locations
        elif isinstance(value, dict):
            # Recurse one level
            sub_locations = parse_api_json_locations(value)
            if sub_locations:
                return sub_locations

    # If nothing found, walk the entire structure
    if not locations:
        _walk_for_locations(data, locations, depth=0)

    return locations


# ---------------------------------------------------------------------------
# Scraping strategies
# ---------------------------------------------------------------------------
@dataclass
class ScrapeResult:
    """Result from scraping a single merchant."""

    locations: List[Dict[str, Any]] = field(default_factory=list)
    method: str = "none"
    api_endpoint: str = ""
    errors: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Strategy Y: Yext directory crawl (pure httpx, no browser needed)
# ---------------------------------------------------------------------------
async def strategy_yext_directory(
    target: MerchantTarget,
    _zip_codes: List[str],
) -> ScrapeResult:
    """Strategy Y: Crawl a Yext-style location directory (locations.{brand}.com).

    Structure: country → state → city → individual location pages.
    Individual pages have microdata (itemprop) and geo.position meta tags.
    Pure httpx - no Playwright/Scrapling needed.
    """
    result = ScrapeResult(method="yext_directory")
    dedup = LocationDeduplicator()
    base = target.locator_url.rstrip("/")
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
    }

    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers=headers
    ) as client:
        # Step 1: Find the country page
        country_url = base
        if not base.endswith("/united-states"):
            country_url = f"{base}/united-states"

        try:
            r = await client.get(country_url)
            if r.status_code != 200:
                result.errors.append(f"Country page {r.status_code}: {country_url}")
                return result
        except Exception as e:
            result.errors.append(f"Country page fetch failed: {str(e)[:150]}")
            return result

        # Step 2: Extract state links
        state_pattern = re.compile(
            r'href="([^"]*united-states/[a-z]{2})"', re.IGNORECASE
        )
        state_links_raw = state_pattern.findall(r.text)
        # Normalize to full URLs
        state_urls: List[str] = []
        for link in state_links_raw:
            if link.startswith("http"):
                state_urls.append(link)
            elif link.startswith("/"):
                parsed = urlparse(base)
                state_urls.append(f"{parsed.scheme}://{parsed.netloc}{link}")
            else:
                state_urls.append(f"{base}/{link.lstrip('../').lstrip('./')}")
        # Deduplicate preserving order
        seen_states: Set[str] = set()
        unique_state_urls: List[str] = []
        for u in state_urls:
            if u not in seen_states:
                seen_states.add(u)
                unique_state_urls.append(u)
        state_urls = unique_state_urls

        if not state_urls:
            result.errors.append("No state links found on country page")
            return result

        log.info("yext_states_found", merchant=target.name, count=len(state_urls))

        # Step 3: Fetch all state pages and collect links
        all_page_links: List[str] = []
        sem = asyncio.Semaphore(10)

        async def fetch_state(state_url: str) -> List[str]:
            async with sem:
                try:
                    r2 = await client.get(state_url)
                    if r2.status_code != 200:
                        return []
                except Exception:
                    return []

                # Extract all directory links from the state page
                links = re.findall(r'href="([^"]*)"', r2.text)
                parsed_base = urlparse(state_url)
                base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
                result_links: List[str] = []
                for link in links:
                    # Resolve relative URLs
                    if link.startswith("../"):
                        full = urljoin(state_url, link)
                    elif link.startswith("/"):
                        full = f"{base_domain}{link}"
                    elif link.startswith("http"):
                        full = link
                    else:
                        full = f"{state_url}/{link}"

                    # Only keep links under united-states/{state}/
                    if "/united-states/" in full and full.count("/") > state_url.count("/"):
                        result_links.append(full)
                return result_links

        state_results = await asyncio.gather(
            *[fetch_state(u) for u in state_urls], return_exceptions=True
        )
        for sr in state_results:
            if isinstance(sr, list):
                all_page_links.extend(sr)

        # Deduplicate page links
        unique_links: List[str] = list(dict.fromkeys(all_page_links))
        log.info("yext_page_links_found", merchant=target.name, count=len(unique_links))

        # Step 4: Classify links - city pages vs individual location pages
        # Individual location pages have 5+ path segments:
        #   /united-states/al/albertville/7921-us-highway-431
        # City pages have 4 segments: /united-states/al/birmingham
        city_urls: List[str] = []
        location_urls: List[str] = []
        for link in unique_links:
            path = urlparse(link).path.rstrip("/")
            segments = [s for s in path.split("/") if s]
            if len(segments) >= 4:
                location_urls.append(link)
            elif len(segments) == 3:
                city_urls.append(link)

        log.info(
            "yext_link_classification",
            merchant=target.name,
            city_pages=len(city_urls),
            location_pages=len(location_urls),
        )

        # Step 5: Fetch city pages to get individual location links
        async def fetch_city(city_url: str) -> List[str]:
            async with sem:
                try:
                    r3 = await client.get(city_url)
                    if r3.status_code != 200:
                        return []
                except Exception:
                    return []
                links3 = re.findall(r'href="([^"]*)"', r3.text)
                parsed3 = urlparse(city_url)
                base3 = f"{parsed3.scheme}://{parsed3.netloc}"
                loc_links: List[str] = []
                for link in links3:
                    if link.startswith("../"):
                        full = urljoin(city_url, link)
                    elif link.startswith("/"):
                        full = f"{base3}{link}"
                    elif link.startswith("http"):
                        full = link
                    else:
                        full = f"{city_url}/{link}"
                    path = urlparse(full).path.rstrip("/")
                    segments = [s for s in path.split("/") if s]
                    if len(segments) >= 4 and "/united-states/" in full:
                        loc_links.append(full)
                return loc_links

        if city_urls:
            city_results = await asyncio.gather(
                *[fetch_city(u) for u in city_urls], return_exceptions=True
            )
            for cr in city_results:
                if isinstance(cr, list):
                    location_urls.extend(cr)

        # Deduplicate all location URLs
        location_urls = list(dict.fromkeys(location_urls))
        log.info(
            "yext_total_location_pages",
            merchant=target.name,
            count=len(location_urls),
        )

        # Step 6: Fetch individual location pages and extract data
        async def fetch_location_page(loc_url: str) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    r4 = await client.get(loc_url)
                    if r4.status_code != 200:
                        return None
                except Exception:
                    return None

                html = r4.text
                loc: Dict[str, Any] = {"store_url": str(r4.url)}

                # Extract geo.position meta tag (lat;lng)
                geo_match = re.search(
                    r'<meta[^>]+name="geo\.position"[^>]+content="([^"]+)"', html
                )
                if geo_match:
                    sep = ";" if ";" in geo_match.group(1) else ","
                    parts = geo_match.group(1).split(sep)
                    if len(parts) == 2:
                        try:
                            loc["latitude"] = float(parts[0])
                            loc["longitude"] = float(parts[1])
                        except ValueError:
                            pass

                # Extract itemprop fields
                itemprop_map = {
                    "streetAddress": "address",
                    "addressLocality": "city",
                    "addressRegion": "state",
                    "postalCode": "zip",
                    "telephone": "phone",
                }
                for prop, key in itemprop_map.items():
                    # Check for itemprop in <span>, <meta>, etc
                    m = re.search(
                        rf'itemprop="{prop}"[^>]*>([^<]*)<', html
                    )
                    if m and m.group(1).strip():
                        loc[key] = m.group(1).strip()
                    else:
                        # Try meta tag with content
                        m2 = re.search(
                            rf'itemprop="{prop}"[^>]+content="([^"]*)"', html
                        )
                        if m2:
                            loc[key] = m2.group(1).strip()

                # Fallback: extract address from Address-field classes
                if not loc.get("address"):
                    addr_fields = re.findall(
                        r'class="[^"]*Address-field[^"]*"[^>]*>(.*?)</(?:span|div)',
                        html,
                        re.DOTALL,
                    )
                    clean_fields = [
                        re.sub(r"<[^>]+>", "", f).strip() for f in addr_fields
                    ]
                    clean_fields = [f for f in clean_fields if f]
                    if clean_fields:
                        loc["address"] = clean_fields[0]

                # Extract store name from itemprop="name" that matches the merchant
                name_matches = re.findall(
                    r'itemprop="name"[^>]*>([^<]+)<', html
                )
                for nm in name_matches:
                    nm_clean = nm.strip()
                    if target.name.split("'")[0].lower() in nm_clean.lower():
                        loc["name"] = nm_clean
                        break

                # Normalize state to 2-letter
                if loc.get("state"):
                    loc["state"] = loc["state"].upper()[:2]
                # Normalize zip
                if loc.get("zip"):
                    loc["zip"] = _extract_zip(loc["zip"])

                # Validate minimum fields
                if loc.get("address") and loc.get("city"):
                    return loc
                return None

        # Process in batches
        batch_size = 50
        for i in range(0, len(location_urls), batch_size):
            batch = location_urls[i : i + batch_size]
            batch_results = await asyncio.gather(
                *[fetch_location_page(u) for u in batch],
                return_exceptions=True,
            )
            new_count = 0
            for br in batch_results:
                if isinstance(br, dict):
                    if dedup.add(br):
                        new_count += 1
            log.info(
                "yext_batch_done",
                merchant=target.name,
                batch=f"{i + len(batch)}/{len(location_urls)}",
                new=new_count,
                total=len(dedup),
            )

    result.locations = dedup.get_all()
    log.info(
        "yext_directory_done",
        merchant=target.name,
        total=len(result.locations),
    )
    return result


# ---------------------------------------------------------------------------
# Strategy S: Sitemap-based location extraction (pure httpx)
# ---------------------------------------------------------------------------
async def strategy_sitemap(
    target: MerchantTarget,
    _zip_codes: List[str],
) -> ScrapeResult:
    """Strategy S: Discover location pages via sitemap, fetch each, extract data.

    Works for any merchant whose sitemap lists individual location pages
    that have geo.position meta tags and/or itemprop structured data.
    """
    result = ScrapeResult(method="sitemap")
    dedup = LocationDeduplicator()
    parsed_base = urlparse(target.locator_url)
    base_domain = f"{parsed_base.scheme}://{parsed_base.netloc}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml",
    }

    async with httpx.AsyncClient(
        timeout=20, follow_redirects=True, headers=headers
    ) as client:
        # Step 1: Discover sitemaps
        sitemap_urls_to_check = [
            f"{base_domain}/sitemap.xml",
            f"{base_domain}/sitemap_index.xml",
        ]

        all_location_urls: List[str] = []
        checked_sitemaps: Set[str] = set()

        async def process_sitemap(sitemap_url: str) -> None:
            if sitemap_url in checked_sitemaps:
                return
            checked_sitemaps.add(sitemap_url)
            try:
                r = await client.get(sitemap_url)
                if r.status_code != 200:
                    return
            except Exception:
                return

            # Check for sub-sitemap references
            sub_sitemaps = re.findall(r"<loc>([^<]+\.xml[^<]*)</loc>", r.text)
            for sub in sub_sitemaps:
                if sub not in checked_sitemaps:
                    await process_sitemap(sub)

            # Extract location URLs (filter out non-location pages)
            all_urls = re.findall(r"<loc>([^<]+)</loc>", r.text)
            for url in all_urls:
                if url.endswith(".xml"):
                    continue
                # Skip non-location pages (menu, food-near-me, etc.)
                path = urlparse(url).path.lower()
                if any(
                    skip in path
                    for skip in [
                        "food-near-me",
                        "pizza-near-me",
                        "menu",
                        "/news",
                        "/blog",
                        "/about",
                        "/faq",
                        "/careers",
                        "/contact",
                    ]
                ):
                    continue
                # Must have address-like path (state/city/address or similar)
                segments = [s for s in path.strip("/").split("/") if s]
                if not segments:
                    continue

                # Pattern 1: hierarchical /state/city/address (3+ segments)
                has_state = any(
                    s.upper() in VALID_STATES
                    for s in segments
                    if len(s) == 2
                )
                if len(segments) >= 3 and has_state:
                    all_location_urls.append(url)
                    continue

                # Pattern 2: /locations/us/{state-name}/{city}/{addr}
                has_state_name = any(
                    s in STATE_NAMES for s in segments
                )
                if len(segments) >= 4 and has_state_name:
                    all_location_urls.append(url)
                    continue

                # Pattern 3: flat slug like "eastpoint-ga-7" (city-STATE-num)
                slug = segments[-1]
                flat_m = re.match(
                    r"^[a-z]+-([a-z]{2})-\d+$", slug, re.IGNORECASE
                )
                if flat_m and flat_m.group(1).upper() in VALID_STATES:
                    all_location_urls.append(url)
                    continue

                # Pattern 4: slug starts with state abbrev (e.g. tx-san-antonio)
                for seg in segments:
                    seg_m = re.match(
                        r"^([a-z]{2})-[a-z]", seg, re.IGNORECASE
                    )
                    if seg_m and seg_m.group(1).upper() in VALID_STATES:
                        all_location_urls.append(url)
                        break
                else:
                    # Pattern 5: store detail pages (/stores/detail.aspx?s=123)
                    if "store" in path and ("detail" in path or "?" in url):
                        all_location_urls.append(url)

        for sm_url in sitemap_urls_to_check:
            await process_sitemap(sm_url)

        # Deduplicate location URLs
        all_location_urls = list(dict.fromkeys(all_location_urls))

        if not all_location_urls:
            result.errors.append("No location URLs found in sitemap")
            return result

        # Sort: deeper paths first (location pages tend to have more segments
        # than city/state index pages, e.g. /us/va/richmond/1234-broad-st
        # vs /us/va/richmond).  This makes early-termination more effective.
        all_location_urls.sort(
            key=lambda u: len(urlparse(u).path.strip("/").split("/")),
            reverse=True,
        )

        log.info(
            "sitemap_location_urls_found",
            merchant=target.name,
            count=len(all_location_urls),
        )

        # Step 2: Fetch each location page and extract data
        sem = asyncio.Semaphore(15)

        async def fetch_location_page(loc_url: str) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    r4 = await client.get(loc_url)
                    if r4.status_code != 200:
                        return None
                except Exception:
                    return None

                html = r4.text
                loc: Dict[str, Any] = {"store_url": str(r4.url)}

                # --- JSON-LD (most reliable structured data) ---
                ld_matches = re.findall(
                    r'<script[^>]+type="application/ld\+json"[^>]*>'
                    r"(.*?)</script>",
                    html,
                    re.DOTALL,
                )
                for ld_raw in ld_matches:
                    try:
                        ld = json.loads(ld_raw)
                        if isinstance(ld, dict) and "@graph" in ld:
                            ld = ld["@graph"]
                        _LOC_TYPES = {
                            "Restaurant",
                            "Store",
                            "LocalBusiness",
                            "Place",
                            "Hotel",
                            "LodgingBusiness",
                            "GroceryStore",
                            "MovieTheater",
                            "MobilePhoneStore",
                            "ElectronicsStore",
                            "DepartmentStore",
                        }

                        def _normalize_type(t: str) -> str:
                            """Strip schema.org URL prefix if present."""
                            if t.startswith("https://schema.org/"):
                                return t[len("https://schema.org/"):]
                            if t.startswith("http://schema.org/"):
                                return t[len("http://schema.org/"):]
                            return t

                        def _is_location_type(item: dict) -> bool:
                            t = item.get("@type", "")
                            if isinstance(t, list):
                                return any(
                                    _normalize_type(x) in _LOC_TYPES
                                    for x in t
                                    if isinstance(x, str)
                                )
                            return _normalize_type(t) in _LOC_TYPES

                        if isinstance(ld, list):
                            ld = next(
                                (
                                    x
                                    for x in ld
                                    if isinstance(x, dict)
                                    and _is_location_type(x)
                                ),
                                None,
                            )
                        if isinstance(ld, dict) and not _is_location_type(ld):
                            ld = None
                        if not isinstance(ld, dict):
                            continue
                        addr = ld.get("address", {})
                        if isinstance(addr, list):
                            addr = addr[0] if addr else {}
                        if isinstance(addr, dict):
                            sa = addr.get("streetAddress", "")
                            if isinstance(sa, list):
                                sa = sa[0] if sa else ""
                            if sa:
                                loc["address"] = sa
                            if addr.get("addressLocality"):
                                loc["city"] = addr["addressLocality"]
                            if addr.get("addressRegion"):
                                loc["state"] = addr["addressRegion"]
                            if addr.get("postalCode"):
                                loc["zip"] = addr["postalCode"]
                        geo = ld.get("geo", {})
                        if isinstance(geo, dict):
                            if geo.get("latitude"):
                                loc["latitude"] = float(geo["latitude"])
                            if geo.get("longitude"):
                                loc["longitude"] = float(geo["longitude"])
                        if ld.get("telephone"):
                            loc["phone"] = ld["telephone"]
                        if ld.get("name"):
                            loc["name"] = ld["name"]
                        if loc.get("address") and loc.get("city"):
                            break
                    except (json.JSONDecodeError, ValueError, TypeError):
                        continue

                # --- geo.position meta tag ---
                geo_match = re.search(
                    r'<meta[^>]+name="geo\.position"[^>]+content="([^"]+)"',
                    html,
                )
                if geo_match and not loc.get("latitude"):
                    sep = ";" if ";" in geo_match.group(1) else ","
                    parts = geo_match.group(1).split(sep)
                    if len(parts) == 2:
                        try:
                            loc["latitude"] = float(parts[0])
                            loc["longitude"] = float(parts[1])
                        except ValueError:
                            pass

                # Extract geo.placename for city/state
                place_match = re.search(
                    r'<meta[^>]+name="geo\.placename"[^>]+content="([^"]+)"',
                    html,
                )
                if place_match:
                    place = place_match.group(1)
                    # Format: "City,State" or "City, State"
                    place_parts = [p.strip() for p in place.split(",")]
                    if len(place_parts) >= 2:
                        if not loc.get("city"):
                            loc["city"] = place_parts[0]
                        if not loc.get("state"):
                            state_raw = place_parts[-1].strip()
                            loc["state"] = _extract_state(
                                state_raw.upper()
                            ) or state_raw[:2].upper()

                # Extract geo.region for state fallback
                region_match = re.search(
                    r'<meta[^>]+name="geo\.region"[^>]+content="([^"]+)"',
                    html,
                )
                if region_match and not loc.get("state"):
                    region = region_match.group(1)
                    state_m = re.search(r"[A-Z]{2}", region)
                    if state_m and state_m.group(0) in VALID_STATES:
                        loc["state"] = state_m.group(0)

                # Extract itemprop fields
                itemprop_map = {
                    "streetAddress": "address",
                    "addressLocality": "city",
                    "addressRegion": "state",
                    "postalCode": "zip",
                    "telephone": "phone",
                }
                for prop, key in itemprop_map.items():
                    if loc.get(key):
                        continue
                    m = re.search(
                        rf'itemprop="{prop}"[^>]*>([^<]*)<', html
                    )
                    if m and m.group(1).strip():
                        loc[key] = m.group(1).strip()
                    else:
                        m2 = re.search(
                            rf'itemprop="{prop}"[^>]+content="([^"]*)"',
                            html,
                        )
                        if m2:
                            loc[key] = m2.group(1).strip()

                # Fallback: parse address from URL path
                url_path = urlparse(loc_url).path.strip("/")
                segments = url_path.split("/")
                if not loc.get("address") and len(segments) >= 3:
                    # Last segment is often the address slug
                    addr_slug = segments[-1]
                    # Un-slugify: replace hyphens with spaces, title case
                    addr = addr_slug.replace("-", " ").title()
                    loc["address"] = addr

                if not loc.get("city") and len(segments) >= 2:
                    city_slug = segments[-2]
                    loc["city"] = city_slug.replace("-", " ").title()

                # Extract ZIP from URL path (e.g., /va/24551/forest/...)
                if not loc.get("zip"):
                    for seg in segments:
                        if re.match(r"^\d{5}$", seg):
                            loc["zip"] = seg
                            break

                # Look for store name
                name_patterns = [
                    rf'itemprop="name"[^>]*>([^<]*{re.escape(target.name.split("'")[0])}[^<]*)<',
                    r'<title>([^<]+)</title>',
                ]
                for np in name_patterns:
                    nm = re.search(np, html, re.IGNORECASE)
                    if nm:
                        loc["name"] = nm.group(1).strip()
                        break

                # Normalize
                if loc.get("state"):
                    s = loc["state"].upper().strip()
                    loc["state"] = s[:2] if s[:2] in VALID_STATES else ""
                if loc.get("zip"):
                    loc["zip"] = _extract_zip(loc["zip"])

                if loc.get("address") and loc.get("city"):
                    return loc
                return None

        # Process in batches with early termination
        batch_size = 50
        consecutive_empty = 0
        max_empty_batches = 3  # Stop after 3 batches with 0 new locations
        for i in range(0, len(all_location_urls), batch_size):
            batch = all_location_urls[i : i + batch_size]
            batch_results = await asyncio.gather(
                *[fetch_location_page(u) for u in batch],
                return_exceptions=True,
            )
            new_count = 0
            for br in batch_results:
                if isinstance(br, dict):
                    if dedup.add(br):
                        new_count += 1
            log.info(
                "sitemap_batch_done",
                merchant=target.name,
                batch=f"{i + len(batch)}/{len(all_location_urls)}",
                new=new_count,
                total=len(dedup),
            )
            if new_count == 0:
                consecutive_empty += 1
                if consecutive_empty >= max_empty_batches:
                    log.info(
                        "sitemap_early_stop",
                        merchant=target.name,
                        reason=f"{max_empty_batches} consecutive empty batches",
                        total=len(dedup),
                        urls_remaining=len(all_location_urls) - i - len(batch),
                    )
                    break
            else:
                consecutive_empty = 0

    result.locations = dedup.get_all()
    log.info(
        "sitemap_done",
        merchant=target.name,
        total=len(result.locations),
    )
    return result


# ---------------------------------------------------------------------------
# Strategy A: API discovery via DynamicFetcher
# ---------------------------------------------------------------------------
async def strategy_api_discovery(
    target: MerchantTarget,
    zip_codes: List[str],
) -> ScrapeResult:
    """Strategy A: Intercept API calls via DynamicFetcher page_action.

    1. Load the locator page with a page_action callback that intercepts
       XHR/fetch responses.
    2. Fill the search input with a ZIP and submit.
    3. Capture the API endpoint and response.
    4. Replay the discovered API across all ZIP codes using httpx (no browser).
    """
    from scrapling.fetchers import DynamicFetcher

    result = ScrapeResult(method="api_discovery")
    dedup = LocationDeduplicator()

    # Phase 1: Discover the API endpoint by intercepting network calls
    captured_endpoints: List[Dict[str, Any]] = []
    pilot_zip = zip_codes[0] if zip_codes else "10001"

    def intercept_and_search(page: Any) -> None:
        """Page action callback: set up response interception and search."""
        import json as _json

        def handle_response(response: Any) -> None:
            try:
                url = response.url
                # Look for XHR/fetch JSON responses that look like location data
                content_type = response.headers.get("content-type", "")
                if "json" not in content_type and "javascript" not in content_type:
                    return
                if response.status != 200:
                    return

                # Filter for likely store locator API paths
                url_lower = url.lower()
                location_indicators = [
                    "location", "store", "search", "find", "nearby",
                    "restaurant", "theatre", "theater", "hotel",
                    "branch", "dealer", "place", "result", "locator",
                ]
                if not any(ind in url_lower for ind in location_indicators):
                    return

                try:
                    body = response.json()
                except Exception:
                    try:
                        body = _json.loads(response.text())
                    except Exception:
                        return

                captured_endpoints.append({
                    "url": url,
                    "body": body,
                    "method": response.request.method if hasattr(response, "request") else "GET",
                })
            except Exception:
                pass

        page.on("response", handle_response)

        # Wait for the page to fully load
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # Try to find and fill the search input
        selectors = target.search_input_selector.split(", ")
        filled = False
        for selector in selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    el.click()
                    el.fill(pilot_zip)
                    filled = True
                    break
            except Exception:
                continue

        if not filled:
            # Try a broader search for any visible text input
            try:
                inputs = page.query_selector_all("input[type='text'], input[type='search']")
                for inp in inputs:
                    try:
                        if inp.is_visible():
                            inp.click()
                            inp.fill(pilot_zip)
                            filled = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if filled:
            # Try pressing Enter or clicking a search button
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass

            # Also try clicking submit/search buttons
            for btn_selector in [
                "button[type='submit']",
                "button[aria-label*='search' i]",
                "button[aria-label*='find' i]",
                ".search-button",
                ".search-btn",
                "[data-testid*='search']",
            ]:
                try:
                    btn = page.query_selector(btn_selector)
                    if btn and btn.is_visible():
                        btn.click()
                        break
                except Exception:
                    continue

            # Wait for API responses
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            # Extra wait for late-arriving responses
            try:
                page.wait_for_timeout(3000)
            except Exception:
                pass

    try:
        log.info("api_discovery_start", merchant=target.name, pilot_zip=pilot_zip)
        await asyncio.to_thread(
            DynamicFetcher.fetch,
            target.locator_url,
            headless=True,
            network_idle=True,
            page_action=intercept_and_search,
            timeout=45000,
        )
    except Exception as e:
        result.errors.append(f"DynamicFetcher failed: {str(e)[:200]}")
        return result

    if not captured_endpoints:
        log.info("api_discovery_no_endpoints", merchant=target.name)
        return result

    # Phase 2: Parse the pilot response for initial locations
    best_endpoint: Optional[Dict[str, Any]] = None
    best_count = 0
    for ep in captured_endpoints:
        locs = parse_api_json_locations(ep["body"])
        if len(locs) > best_count:
            best_count = len(locs)
            best_endpoint = ep

    if not best_endpoint or best_count == 0:
        log.info("api_discovery_no_locations_in_responses", merchant=target.name,
                 endpoints_captured=len(captured_endpoints))
        return result

    result.api_endpoint = best_endpoint["url"]
    log.info("api_discovered", merchant=target.name,
             endpoint=result.api_endpoint[:120], pilot_count=best_count)

    # Add pilot locations
    for loc in parse_api_json_locations(best_endpoint["body"]):
        dedup.add(loc)

    # Phase 3: Replay the API across remaining ZIP codes using httpx
    parsed_url = urlparse(best_endpoint["url"])
    base_api = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"

    # Try to detect the ZIP/location parameter from the URL
    from urllib.parse import parse_qs

    query_params = parse_qs(parsed_url.query)
    zip_param_name: Optional[str] = None
    for param_name, values in query_params.items():
        for val in values:
            if val == pilot_zip or pilot_zip in val:
                zip_param_name = param_name
                break
        if zip_param_name:
            break

    if zip_param_name:
        log.info("api_replay_start", merchant=target.name,
                 param=zip_param_name, zip_count=len(zip_codes))

        async with httpx.AsyncClient(timeout=20) as client:
            sem = asyncio.Semaphore(10)

            async def fetch_zip(zc: str) -> List[Dict[str, Any]]:
                async with sem:
                    params = dict(query_params)
                    params[zip_param_name] = [zc]
                    flat_params = {k: v[0] if isinstance(v, list) and len(v) == 1 else v
                                   for k, v in params.items()}
                    try:
                        resp = await client.get(
                            base_api,
                            params=flat_params,
                            headers={
                                "Accept": "application/json",
                                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                                "Referer": target.locator_url,
                            },
                        )
                        if resp.status_code == 200:
                            try:
                                data = resp.json()
                                return parse_api_json_locations(data)
                            except Exception:
                                return []
                    except Exception:
                        return []
                    return []

            tasks = [fetch_zip(zc) for zc in zip_codes[1:]]  # skip pilot ZIP
            batch_size = 50
            for i in range(0, len(tasks), batch_size):
                batch = tasks[i : i + batch_size]
                results = await asyncio.gather(*batch, return_exceptions=True)
                for r in results:
                    if isinstance(r, list):
                        for loc in r:
                            dedup.add(loc)

                if i + batch_size < len(tasks):
                    await asyncio.sleep(0.5)

        log.info("api_replay_done", merchant=target.name, total=len(dedup))
    else:
        log.info("api_replay_skip_no_param", merchant=target.name,
                 url=result.api_endpoint[:120])

    result.locations = dedup.get_all()
    return result


async def strategy_dom_extraction(
    target: MerchantTarget,
    zip_codes: List[str],
) -> ScrapeResult:
    """Strategy B: Render the SPA and extract from DOM.

    1. Load the page with DynamicFetcher (network_idle).
    2. Search for locations using the pilot ZIP.
    3. Extract from:
       a. CSS selectors (location cards)
       b. JSON-LD <script> tags
       c. __NEXT_DATA__ script tag
    """
    from scrapling.fetchers import DynamicFetcher

    result = ScrapeResult(method="dom_extraction")
    dedup = LocationDeduplicator()
    pilot_zip = zip_codes[0] if zip_codes else "10001"
    rendered_html_container: List[str] = []
    nuxt_json_container: List[str] = []

    def search_and_wait(page: Any) -> None:
        """Fill search, wait for results, capture rendered HTML."""
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass

        # Try filling the search input
        selectors = target.search_input_selector.split(", ")
        filled = False
        for selector in selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    el.click()
                    el.fill(pilot_zip)
                    filled = True
                    break
            except Exception:
                continue

        if not filled:
            try:
                inputs = page.query_selector_all("input[type='text'], input[type='search']")
                for inp in inputs:
                    try:
                        if inp.is_visible():
                            inp.click()
                            inp.fill(pilot_zip)
                            filled = True
                            break
                    except Exception:
                        continue
            except Exception:
                pass

        if filled:
            try:
                page.keyboard.press("Enter")
            except Exception:
                pass
            for btn_selector in [
                "button[type='submit']",
                "button[aria-label*='search' i]",
                ".search-button",
                ".search-btn",
            ]:
                try:
                    btn = page.query_selector(btn_selector)
                    if btn and btn.is_visible():
                        btn.click()
                        break
                except Exception:
                    continue
            try:
                page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass
            try:
                page.wait_for_timeout(3000)
            except Exception:
                pass

        # Capture the fully rendered HTML
        try:
            rendered_html_container.append(page.content())
        except Exception:
            pass

        # Capture Nuxt.js state directly from browser context
        nuxt_raw = _extract_nuxt_from_page(page)
        if nuxt_raw:
            nuxt_json_container.append(nuxt_raw)

    try:
        log.info("dom_extraction_start", merchant=target.name, pilot_zip=pilot_zip)
        page = await asyncio.to_thread(
            DynamicFetcher.fetch,
            target.locator_url,
            headless=True,
            network_idle=True,
            page_action=search_and_wait,
            timeout=45000,
        )
    except Exception as e:
        result.errors.append(f"DynamicFetcher failed: {str(e)[:200]}")
        return result

    # Get the HTML - prefer the rendered version captured inside page_action
    html = rendered_html_container[0] if rendered_html_container else ""
    if not html:
        # Fall back to Scrapling's parsed body
        try:
            html = str(page.body) if hasattr(page, "body") else ""
        except Exception:
            pass
    if not html:
        try:
            html = page.html if hasattr(page, "html") else ""
        except Exception:
            pass

    if not html:
        result.errors.append("No HTML captured from page")
        return result

    log.info("dom_extraction_html_captured", merchant=target.name, length=len(html))

    # Try JSON-LD first (most structured)
    jsonld_locs = parse_json_ld_locations(html)
    if jsonld_locs:
        log.info("dom_extraction_jsonld", merchant=target.name, count=len(jsonld_locs))
        for loc in jsonld_locs:
            dedup.add(loc)

    # Try __NEXT_DATA__
    next_locs = parse_next_data_locations(html)
    if next_locs:
        log.info("dom_extraction_next_data", merchant=target.name, count=len(next_locs))
        for loc in next_locs:
            dedup.add(loc)

    # Try Nuxt.js state (__NUXT__ / __NUXT_DATA__)
    nuxt_locs = parse_nuxt_data_locations(html)
    if nuxt_locs:
        log.info("dom_extraction_nuxt_data", merchant=target.name, count=len(nuxt_locs))
        for loc in nuxt_locs:
            dedup.add(loc)

    # Also try browser-captured Nuxt state (more reliable than regex for Nuxt 2)
    if nuxt_json_container:
        try:
            nuxt_data = json.loads(nuxt_json_container[0])
            nuxt_browser_locs: List[Dict[str, Any]] = []
            _walk_for_locations(nuxt_data, nuxt_browser_locs, depth=0)
            if nuxt_browser_locs:
                log.info("dom_extraction_nuxt_browser", merchant=target.name,
                         count=len(nuxt_browser_locs))
                for loc in nuxt_browser_locs:
                    dedup.add(loc)
        except (json.JSONDecodeError, ValueError):
            pass

    # Try extracting inline JSON from script tags (common pattern: window.__STORE_DATA__)
    inline_json_patterns = [
        r"window\.__STORE_DATA__\s*=\s*(\{.*?\});",
        r"window\.__LOCATIONS__\s*=\s*(\[.*?\]);",
        r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});",
        r'var\s+storeData\s*=\s*(\{.*?\});',
        r'var\s+locations\s*=\s*(\[.*?\]);',
        r"window\.__NUXT__\s*=\s*(\{.*?\});",
        r"AEMdestinations\s*=\s*(\[.*?\]);",
    ]
    for pattern in inline_json_patterns:
        for match in re.finditer(pattern, html, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                inline_locs = parse_api_json_locations(data)
                if inline_locs:
                    log.info("dom_extraction_inline_json", merchant=target.name,
                             count=len(inline_locs))
                    for loc in inline_locs:
                        dedup.add(loc)
            except (json.JSONDecodeError, ValueError):
                continue

    # If still no results, try scraping multiple ZIPs with the session approach
    if len(dedup) == 0 and len(zip_codes) > 1:
        log.info("dom_extraction_multi_zip_start", merchant=target.name)
        sample_zips = zip_codes[:20]  # Only try 20 ZIPs with browser rendering

        for zc in sample_zips[1:]:
            rendered: List[str] = []

            def search_zip(page: Any, _zc: str = zc) -> None:
                try:
                    page.wait_for_load_state("networkidle", timeout=8000)
                except Exception:
                    pass

                selectors_list = target.search_input_selector.split(", ")
                for sel in selectors_list:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.triple_click()
                            el.fill(_zc)
                            try:
                                page.keyboard.press("Enter")
                            except Exception:
                                pass
                            try:
                                page.wait_for_load_state("networkidle", timeout=8000)
                            except Exception:
                                pass
                            try:
                                page.wait_for_timeout(2000)
                            except Exception:
                                pass
                            break
                    except Exception:
                        continue

                try:
                    rendered.append(page.content())
                except Exception:
                    pass

            try:
                await asyncio.to_thread(
                    DynamicFetcher.fetch,
                    target.locator_url,
                    headless=True,
                    network_idle=True,
                    page_action=search_zip,
                    timeout=30000,
                )
                if rendered:
                    for loc in parse_json_ld_locations(rendered[0]):
                        dedup.add(loc)
                    for loc in parse_next_data_locations(rendered[0]):
                        dedup.add(loc)
                    for loc in parse_nuxt_data_locations(rendered[0]):
                        dedup.add(loc)
            except Exception:
                continue

            await asyncio.sleep(0.3)

    result.locations = dedup.get_all()
    log.info("dom_extraction_done", merchant=target.name, total=len(result.locations))
    return result


def _stealth_capture_response(
    response: Any,
    endpoints: List[Dict[str, Any]],
    pilot_zip: str,
) -> None:
    """Capture JSON API responses during stealth browsing for cookie replay."""
    try:
        url = response.url
        content_type = response.headers.get("content-type", "")
        if response.status != 200:
            return
        if "application/json" not in content_type and "text/json" not in content_type:
            return
        # Skip static assets and tracking
        skip_patterns = ("/analytics", "/track", "/log", ".js", ".css", "/pixel")
        if any(s in url for s in skip_patterns):
            return
        body = response.json()
        if not body:
            return
        endpoints.append({"url": url, "body": body})
    except Exception:
        pass


async def strategy_stealth(
    target: MerchantTarget,
    zip_codes: List[str],
) -> ScrapeResult:
    """Strategy C: Use StealthyFetcher for Cloudflare-protected sites.

    Uses solve_cloudflare=True, hide_canvas=True, block_webrtc=True.
    """
    from scrapling.fetchers import StealthyFetcher

    result = ScrapeResult(method="stealth")
    dedup = LocationDeduplicator()
    pilot_zip = zip_codes[0] if zip_codes else "10001"
    captured_cookies: List[Dict[str, Any]] = []
    stealth_api_endpoints: List[Dict[str, Any]] = []

    def stealth_search(page: Any) -> None:
        """Fill search in stealth mode and capture cookies + API endpoints."""
        # Set up API interception before searching
        try:
            page.on(
                "response",
                lambda resp: _stealth_capture_response(resp, stealth_api_endpoints, pilot_zip),
            )
        except Exception:
            pass

        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass

        selectors = target.search_input_selector.split(", ")
        for selector in selectors:
            try:
                el = page.query_selector(selector)
                if el and el.is_visible():
                    el.click()
                    el.fill(pilot_zip)
                    try:
                        page.keyboard.press("Enter")
                    except Exception:
                        pass
                    try:
                        page.wait_for_load_state("networkidle", timeout=15000)
                    except Exception:
                        pass
                    try:
                        page.wait_for_timeout(5000)
                    except Exception:
                        pass
                    break
            except Exception:
                continue

        # Capture session cookies for replay
        try:
            cookies = page.context.cookies()
            captured_cookies.extend(cookies)
        except Exception:
            pass

    try:
        log.info("stealth_start", merchant=target.name, pilot_zip=pilot_zip)
        page = await asyncio.to_thread(
            StealthyFetcher.fetch,
            target.locator_url,
            headless=True,
            solve_cloudflare=True,
            hide_canvas=True,
            block_webrtc=True,
            page_action=stealth_search,
            network_idle=True,
            timeout=60000,
        )
    except Exception as e:
        result.errors.append(f"StealthyFetcher failed: {str(e)[:200]}")
        return result

    # Get HTML from the stealth-rendered page
    html = ""
    try:
        html = str(page.body) if hasattr(page, "body") else ""
    except Exception:
        pass
    if not html:
        try:
            html = page.html if hasattr(page, "html") else ""
        except Exception:
            pass

    if not html:
        result.errors.append("No HTML from StealthyFetcher")
        return result

    log.info("stealth_html_captured", merchant=target.name, length=len(html))

    # Parse all formats
    for loc in parse_json_ld_locations(html):
        dedup.add(loc)
    for loc in parse_next_data_locations(html):
        dedup.add(loc)
    for loc in parse_nuxt_data_locations(html):
        dedup.add(loc)

    # Try inline JSON
    inline_patterns = [
        r"window\.__STORE_DATA__\s*=\s*(\{.*?\});",
        r"window\.__LOCATIONS__\s*=\s*(\[.*?\]);",
        r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});",
        r"window\.__NUXT__\s*=\s*(\{.*?\});",
        r"AEMdestinations\s*=\s*(\[.*?\]);",
    ]
    for pattern in inline_patterns:
        for match in re.finditer(pattern, html, re.DOTALL):
            try:
                data = json.loads(match.group(1))
                for loc in parse_api_json_locations(data):
                    dedup.add(loc)
            except Exception:
                continue

    # --- Cookie replay: if stealth captured an API endpoint, replay with httpx ---
    cookie_replay_used = False
    if stealth_api_endpoints and captured_cookies and len(zip_codes) > 1:
        from urllib.parse import parse_qs

        # Find the best API endpoint (most locations)
        best_ep: Optional[Dict[str, Any]] = None
        best_ep_count = 0
        for ep in stealth_api_endpoints:
            ep_locs = parse_api_json_locations(ep["body"])
            if len(ep_locs) > best_ep_count:
                best_ep_count = len(ep_locs)
                best_ep = ep

        if best_ep and best_ep_count > 0:
            # Add pilot API locations
            for loc in parse_api_json_locations(best_ep["body"]):
                dedup.add(loc)

            parsed_ep = urlparse(best_ep["url"])
            base_api = f"{parsed_ep.scheme}://{parsed_ep.netloc}{parsed_ep.path}"
            query_params = parse_qs(parsed_ep.query)

            # Detect the ZIP parameter
            zip_param: Optional[str] = None
            for pname, pvals in query_params.items():
                for pv in pvals:
                    if pv == pilot_zip or pilot_zip in pv:
                        zip_param = pname
                        break
                if zip_param:
                    break

            if zip_param:
                # Build cookie header from captured cookies
                cookie_str = "; ".join(
                    f"{c['name']}={c['value']}" for c in captured_cookies if c.get("name")
                )
                log.info("stealth_cookie_replay_start", merchant=target.name,
                         endpoint=base_api[:100], zip_param=zip_param,
                         cookies=len(captured_cookies), zips=len(zip_codes) - 1)
                result.api_endpoint = best_ep["url"]
                cookie_replay_used = True

                async with httpx.AsyncClient(timeout=20) as client:
                    sem = asyncio.Semaphore(5)  # conservative for WAF sites

                    async def replay_zip(zc: str) -> List[Dict[str, Any]]:
                        async with sem:
                            params = dict(query_params)
                            params[zip_param] = [zc]
                            flat = {
                                k: v[0] if isinstance(v, list) and len(v) == 1 else v
                                for k, v in params.items()
                            }
                            try:
                                resp = await client.get(
                                    base_api,
                                    params=flat,
                                    headers={
                                        "Accept": "application/json",
                                        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                                        "Referer": target.locator_url,
                                        "Cookie": cookie_str,
                                    },
                                )
                                if resp.status_code == 200:
                                    try:
                                        return parse_api_json_locations(resp.json())
                                    except Exception:
                                        return []
                                elif resp.status_code in (403, 429):
                                    await asyncio.sleep(2.0)
                            except Exception:
                                pass
                            return []

                    replay_tasks = [replay_zip(zc) for zc in zip_codes[1:]]
                    batch_size = 25
                    for i in range(0, len(replay_tasks), batch_size):
                        batch = replay_tasks[i : i + batch_size]
                        results_batch = await asyncio.gather(*batch, return_exceptions=True)
                        for r in results_batch:
                            if isinstance(r, list):
                                for loc in r:
                                    dedup.add(loc)
                        if i + batch_size < len(replay_tasks):
                            await asyncio.sleep(1.0)

                log.info("stealth_cookie_replay_done", merchant=target.name,
                         total=len(dedup))

    # --- Fallback: multi-ZIP stealth browsing (if no cookie replay or no results) ---
    if not cookie_replay_used and len(dedup) > 0 and len(zip_codes) > 1:
        sample_zips = zip_codes[1:100]  # Expanded from 10 to 100 for better coverage
        log.info("stealth_multi_zip_start", merchant=target.name, zips=len(sample_zips))
        for zc in sample_zips:
            def search_another_zip(page: Any, _zc: str = zc) -> None:
                try:
                    page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    pass

                selectors_list = target.search_input_selector.split(", ")
                for sel in selectors_list:
                    try:
                        el = page.query_selector(sel)
                        if el and el.is_visible():
                            el.triple_click()
                            el.fill(_zc)
                            try:
                                page.keyboard.press("Enter")
                            except Exception:
                                pass
                            try:
                                page.wait_for_load_state("networkidle", timeout=10000)
                            except Exception:
                                pass
                            try:
                                page.wait_for_timeout(3000)
                            except Exception:
                                pass
                            break
                    except Exception:
                        continue

            try:
                page2 = await asyncio.to_thread(
                    StealthyFetcher.fetch,
                    target.locator_url,
                    headless=True,
                    solve_cloudflare=True,
                    hide_canvas=True,
                    block_webrtc=True,
                    page_action=search_another_zip,
                    network_idle=True,
                    timeout=45000,
                )
                html2 = ""
                try:
                    html2 = str(page2.body) if hasattr(page2, "body") else ""
                except Exception:
                    pass
                if html2:
                    for loc in parse_json_ld_locations(html2):
                        dedup.add(loc)
                    for loc in parse_next_data_locations(html2):
                        dedup.add(loc)
                    for loc in parse_nuxt_data_locations(html2):
                        dedup.add(loc)
            except Exception:
                continue

            await asyncio.sleep(1.0)  # 1s delay between stealth fetches

    result.locations = dedup.get_all()
    log.info("stealth_done", merchant=target.name, total=len(result.locations))
    return result


# ---------------------------------------------------------------------------
# Orchestration: run strategies for one merchant
# ---------------------------------------------------------------------------
async def scrape_merchant(
    target: MerchantTarget,
    strategy: str,
    zip_codes: List[str],
) -> ScrapeResult:
    """Scrape a single merchant using the selected strategy (or auto cascade)."""
    is_yext = "yext_directory" in (target.notes or "")

    if strategy == "yext":
        return await strategy_yext_directory(target, zip_codes)
    elif strategy == "sitemap":
        return await strategy_sitemap(target, zip_codes)
    elif strategy == "api":
        return await strategy_api_discovery(target, zip_codes)
    elif strategy == "dom":
        return await strategy_dom_extraction(target, zip_codes)
    elif strategy == "stealth":
        return await strategy_stealth(target, zip_codes)

    # Auto: try strategies in order, stop at first success
    log.info("auto_strategy_start", merchant=target.name)

    # Strategy Y: Yext directory (if flagged)
    if is_yext:
        result = await strategy_yext_directory(target, zip_codes)
        if result.locations:
            log.info("auto_strategy_success", merchant=target.name,
                     strategy="yext_directory", count=len(result.locations))
            return result

    # Strategy S: Sitemap-based extraction
    result = await strategy_sitemap(target, zip_codes)
    if result.locations:
        log.info("auto_strategy_success", merchant=target.name,
                 strategy="sitemap", count=len(result.locations))
        return result

    # Strategy A: API discovery
    result = await strategy_api_discovery(target, zip_codes)
    if result.locations:
        log.info("auto_strategy_success", merchant=target.name,
                 strategy="api_discovery", count=len(result.locations))
        return result

    # Strategy B: DOM extraction
    result = await strategy_dom_extraction(target, zip_codes)
    if result.locations:
        log.info("auto_strategy_success", merchant=target.name,
                 strategy="dom_extraction", count=len(result.locations))
        return result

    # Strategy C: Stealth
    result = await strategy_stealth(target, zip_codes)
    if result.locations:
        log.info("auto_strategy_success", merchant=target.name,
                 strategy="stealth", count=len(result.locations))
        return result

    # All strategies failed
    all_errors = result.errors or ["All strategies returned 0 locations"]
    log.warning("auto_strategy_all_failed", merchant=target.name)
    return ScrapeResult(method="none", errors=all_errors)


# ---------------------------------------------------------------------------
# Convert locations to sheet rows
# ---------------------------------------------------------------------------
def locations_to_sheet_rows(
    merchant_name: str,
    merchant_id: Optional[int],
    locator_url: str,
    locations: List[Dict[str, Any]],
    fetch_method: str,
    centroids: Dict[str, Tuple[float, float]],
) -> Tuple[List[List[str]], Dict[str, int]]:
    """Convert raw locations to Google Sheet rows, with validation.

    Returns (rows, stats) where stats has keys: valid, skipped, no_centroid.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parsed = urlparse(locator_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    rows: List[List[str]] = []
    stats = {"valid": 0, "skipped": 0, "no_centroid": 0}

    for loc in locations:
        address = (loc.get("address") or "").strip()
        city = (loc.get("city") or "").strip()
        state = (loc.get("state") or "").strip().upper()
        zip_code = (loc.get("zip") or "").strip()

        if not address or not city or not state or not zip_code:
            stats["skipped"] += 1
            continue

        zip_code = zip_code[:5]
        if not re.match(r"^\d{5}$", zip_code):
            stats["skipped"] += 1
            continue

        if state not in VALID_STATES:
            stats["skipped"] += 1
            continue

        # Get coordinates from location data or centroid lookup
        lat: Optional[float] = None
        lng: Optional[float] = None

        loc_lat = loc.get("latitude")
        loc_lng = loc.get("longitude")
        if loc_lat and loc_lng:
            try:
                lat = float(loc_lat)
                lng = float(loc_lng)
            except (ValueError, TypeError):
                pass

        if lat is None or lng is None:
            coords = centroids.get(zip_code)
            if coords:
                lat, lng = coords
            else:
                stats["no_centroid"] += 1
                stats["skipped"] += 1
                continue

        stats["valid"] += 1
        rows.append([
            merchant_name,                                         # A: Merchant Name
            str(merchant_id) if merchant_id else "",               # B: Merchant ID
            (loc.get("name") or "").strip(),                       # C: Store Name
            address,                                               # D: Address
            (loc.get("suite") or "").strip(),                      # E: Suite
            city,                                                  # F: City
            state,                                                 # G: State
            zip_code,                                              # H: ZIP
            (loc.get("phone") or "").strip(),                      # I: Phone
            (loc.get("hours") or "").strip(),                      # J: Hours
            _resolve_store_url(loc.get("store_url"), base_url),    # K: Store URL
            str(lat),                                              # L: Latitude
            str(lng),                                              # M: Longitude
            "Pending",                                             # N: Status
            now,                                                   # O: Scraped At
            "",                                                    # P: Pushed At
            f"v2_{fetch_method}",                                  # Q: Fetch Method
        ])

    return rows, stats


# ---------------------------------------------------------------------------
# Main async worker
# ---------------------------------------------------------------------------
async def process_merchant_worker(
    target: MerchantTarget,
    strategy: str,
    zip_codes: List[str],
    centroids: Dict[str, Tuple[float, float]],
    sheets_svc: Any,
    sheet_id: str,
    dry_run: bool,
    semaphore: asyncio.Semaphore,
) -> Dict[str, Any]:
    """Process a single merchant: scrape + write to sheet. Respects semaphore."""
    async with semaphore:
        merchant_id = lookup_merchant_id(target.name)
        mid_str = str(merchant_id) if merchant_id else "TBD"

        log.info(
            "merchant_start",
            merchant=target.name,
            merchant_id=mid_str,
            category=target.category,
            strategy=strategy,
        )

        t0 = time.monotonic()
        result = await scrape_merchant(target, strategy, zip_codes)
        elapsed = time.monotonic() - t0

        log.info(
            "merchant_scraped",
            merchant=target.name,
            locations_found=len(result.locations),
            method=result.method,
            elapsed_s=round(elapsed, 1),
        )

        # Convert to sheet rows
        sheet_rows, row_stats = locations_to_sheet_rows(
            merchant_name=target.name,
            merchant_id=merchant_id,
            locator_url=target.locator_url,
            locations=result.locations,
            fetch_method=result.method,
            centroids=centroids,
        )

        # Write to sheet
        if sheet_rows and not dry_run:
            try:
                appended = append_scraped_rows(sheets_svc, sheet_id, sheet_rows)
                log.info("sheet_rows_written", merchant=target.name, count=appended)
            except Exception as e:
                log.error("sheet_write_failed", merchant=target.name, error=str(e)[:200])
                result.errors.append(f"Sheet write error: {str(e)[:100]}")
        elif sheet_rows and dry_run:
            log.info("dry_run_would_write", merchant=target.name, count=len(sheet_rows))

        return {
            "merchant": target.name,
            "category": target.category,
            "found": len(result.locations),
            "valid": row_stats["valid"],
            "skipped": row_stats["skipped"],
            "no_centroid": row_stats["no_centroid"],
            "method": result.method,
            "api_endpoint": result.api_endpoint,
            "errors": result.errors,
            "elapsed_s": round(elapsed, 1),
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def async_main(args: argparse.Namespace) -> None:
    """Async entry point."""
    print()
    print("=" * 70)
    print("  Scrape Locations v2 (Scrapling)")
    print("=" * 70)
    print(f"  Sheet ID:    {args.sheet_id}")
    print(f"  Strategy:    {args.strategy}")
    print(f"  Workers:     {args.workers}")
    print(f"  Dry run:     {args.dry_run}")
    print()

    # Filter targets
    targets = list(MERCHANT_TARGETS)
    if args.merchant:
        targets = [
            t for t in targets
            if t.name.lower() == args.merchant.lower()
            or args.merchant.lower() in t.name.lower()
        ]
        if not targets:
            print(f"ERROR: No merchant matching '{args.merchant}' found in target list.")
            print("Available merchants:")
            for t in MERCHANT_TARGETS:
                print(f"  - {t.name}")
            sys.exit(1)

    print(f"  Merchants:   {len(targets)}")
    for t in targets:
        print(f"    - {t.name} ({t.category})")
    print()

    # Load centroids
    centroids = load_zcta_centroids()
    if not centroids:
        print("ERROR: No ZCTA centroids loaded. Cannot geocode.")
        sys.exit(1)

    # Build ZIP grid
    zip_codes = build_dense_zip_grid(500)

    # Google Sheets setup
    sheets_svc = get_sheets_service()
    if not args.dry_run:
        ensure_scraped_tab(sheets_svc, args.sheet_id)

    # Process merchants with concurrency control
    semaphore = asyncio.Semaphore(args.workers)
    tasks = [
        process_merchant_worker(
            target=t,
            strategy=args.strategy,
            zip_codes=zip_codes,
            centroids=centroids,
            sheets_svc=sheets_svc,
            sheet_id=args.sheet_id,
            dry_run=args.dry_run,
            semaphore=semaphore,
        )
        for t in targets
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Summary
    print()
    print("=" * 70)
    print("  SCRAPE v2 SUMMARY")
    print("=" * 70)

    total_found = 0
    total_valid = 0
    total_errors = 0
    method_counts: Dict[str, int] = {}

    stats_list: List[Dict[str, Any]] = []
    for r in results:
        if isinstance(r, Exception):
            total_errors += 1
            print(f"  ERROR (exception): {str(r)[:200]}")
            continue
        if isinstance(r, dict):
            stats_list.append(r)
            total_found += r["found"]
            total_valid += r["valid"]
            m = r.get("method", "none") or "none"
            method_counts[m] = method_counts.get(m, 0) + 1
            if r["errors"]:
                total_errors += len(r["errors"])

    print(f"  Merchants processed:   {len(stats_list)}")
    print(f"  Locations found:       {total_found}")
    print(f"  Valid (written):       {total_valid}")
    if args.dry_run:
        print("  (DRY RUN - nothing written)")

    if method_counts:
        parts = [f"{count} via {method}" for method, count in sorted(method_counts.items())]
        print(f"  Fetch methods:         {', '.join(parts)}")

    print()
    print("  Per merchant:")
    for s in stats_list:
        err = f" [{len(s['errors'])} errors]" if s["errors"] else ""
        api = f" api={s['api_endpoint'][:60]}..." if s.get("api_endpoint") else ""
        print(
            f"    {s['merchant']:45s}  found={s['found']:5d}  "
            f"valid={s['valid']:5d}  method={s['method']}{err}{api}"
        )
        if s["elapsed_s"]:
            print(f"      elapsed: {s['elapsed_s']}s")

    if total_errors > 0:
        print()
        print(f"  Total errors: {total_errors}")
        for s in stats_list:
            if s["errors"]:
                for e in s["errors"][:3]:
                    print(f"    [{s['merchant']}] {e}")

    if not args.dry_run and total_valid > 0:
        print()
        print("Next steps:")
        print(f"  1. Open the Google Sheet and review the '{SCRAPED_TAB}' tab")
        print("  2. Change Status column from 'Pending' to 'Approved' for good rows")
        print("  3. Change Status to 'Rejected' for bad rows")
        print(
            f"  4. Run: python scripts/scrape_store_locations.py "
            f'--sheet-id "{args.sheet_id}" --push'
        )

    print()
    print("Done.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Second-pass store location scraper using Scrapling "
            "(DynamicFetcher / StealthyFetcher) for merchants that "
            "failed in the first pass."
        ),
    )
    parser.add_argument(
        "--sheet-id",
        required=True,
        help="Google Sheet ID for output",
    )
    parser.add_argument(
        "--merchant",
        type=str,
        default=None,
        help="Process a single merchant by name (partial match supported)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview only, do not write to sheet",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=3,
        help="Number of concurrent merchant workers (default: 3)",
    )
    parser.add_argument(
        "--strategy",
        choices=["auto", "yext", "sitemap", "api", "dom", "stealth"],
        default="auto",
        help=(
            "Scraping strategy: auto (try api -> dom -> stealth), "
            "api (API interception + replay), "
            "dom (rendered DOM extraction), "
            "stealth (Cloudflare bypass). Default: auto"
        ),
    )
    args = parser.parse_args()

    # Validate dependencies
    try:
        from scrapling.fetchers import DynamicFetcher  # noqa: F401
    except ImportError:
        print("ERROR: scrapling is required. Install it in your venv:")
        print("  pip install scrapling")
        sys.exit(1)

    if args.strategy in ("stealth", "auto"):
        try:
            from scrapling.fetchers import StealthyFetcher  # noqa: F401
        except ImportError:
            if args.strategy == "stealth":
                print("ERROR: StealthyFetcher requires scrapling[stealth].")
                print("  pip install scrapling[stealth]")
                sys.exit(1)
            else:
                print(
                    "WARNING: StealthyFetcher not available. "
                    "Auto mode will skip the stealth strategy."
                )

    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
