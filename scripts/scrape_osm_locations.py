#!/usr/bin/env python3
"""Scrape merchant locations from OpenStreetMap via the Overpass API.

For merchants behind aggressive bot protection (Akamai, DataDome, Cloudflare),
OSM crowdsourced data provides ~60-80% coverage as an alternative to direct
website scraping.

Supports hotel chains (tourism=hotel), pharmacies (amenity=pharmacy),
department stores (shop=department_store), and other retail.

Usage:
    # Dry-run a single merchant
    python scripts/scrape_osm_locations.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" \
        --merchant "Hilton" --dry-run

    # Dry-run all remaining merchants
    python scripts/scrape_osm_locations.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" \
        --merchant all --dry-run

    # Production run (writes to sheet)
    python scripts/scrape_osm_locations.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" \
        --merchant "Hilton"
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx
import reverse_geocoder as rg
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

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

OVERPASS_URL = "https://overpass-api.de/api/interpreter"

# US continental bounding box (south, west, north, east)
US_BBOX = "24.5,-125.0,49.5,-66.5"

VALID_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

# State abbreviation lookup for full names sometimes found in OSM
STATE_NAME_TO_ABBR = {
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


# ---------------------------------------------------------------------------
# Merchant brand definitions
# ---------------------------------------------------------------------------
# Each entry: (sheet_merchant_name, osm_category, brand_regex_patterns)
# osm_category determines the Overpass tag filter:
#   "hotel"      -> tourism=hotel
#   "motel"      -> tourism=motel OR tourism=hotel
#   "pharmacy"   -> amenity=pharmacy
#   "department" -> shop=department_store

MerchantDef = Tuple[str, str, List[str]]

MERCHANT_DEFS: Dict[str, MerchantDef] = {
    "Motel 6": (
        "Motel 6",
        "motel",
        ["Motel 6", "Studio 6"],
    ),
    "Hyatt": (
        "Hyatt",
        "hotel",
        [
            "Hyatt", "Hyatt Place", "Hyatt House", "Hyatt Regency",
            "Grand Hyatt", "Park Hyatt", "Andaz", "Thompson Hotels",
            "Hyatt Centric",
        ],
    ),
    "Best Western": (
        "Best Western",
        "hotel",
        ["Best Western", "Best Western Plus", "Best Western Premier"],
    ),
    "Wyndham": (
        "Wyndham / Days Inn / La Quinta",
        "hotel",
        [
            "Wyndham", "Days Inn", "La Quinta", "Super 8", "Ramada",
            "Howard Johnson", "Baymont", "Microtel", "Wingate",
            "AmericInn", "Travelodge", "Knights Inn", "Hawthorn Suites",
        ],
    ),
    "IHG": (
        "IHG / Holiday Inn",
        "hotel",
        [
            "Holiday Inn", "Holiday Inn Express", "InterContinental",
            "Crowne Plaza", "Staybridge Suites", "Candlewood Suites",
            "Hotel Indigo", "Kimpton", "IHG", "Even Hotels", "Avid Hotels",
        ],
    ),
    "Choice Hotels": (
        "Choice Hotels / Quality Inn / Comfort Suites / Econo Lodge / Rodeway Inn",
        "hotel",
        [
            "Comfort Inn", "Comfort Suites", "Quality Inn", "Sleep Inn",
            "Clarion", "Econo Lodge", "Rodeway Inn", "MainStay Suites",
            "Suburban Extended Stay", "WoodSpring Suites", "Choice Hotels",
            "Ascend Collection",
        ],
    ),
    "Hilton": (
        "Hilton",
        "hotel",
        [
            "Hilton", "DoubleTree", "Hampton Inn", "Hampton by Hilton",
            "Homewood Suites", "Embassy Suites", "Hilton Garden Inn",
            "Conrad", "Waldorf Astoria", "Curio", "Tru by Hilton",
            "Tapestry", "Home2 Suites", "Motto by Hilton", "Spark by Hilton",
        ],
    ),
    "Marriott": (
        "Marriott",
        "hotel",
        [
            "Marriott", "Courtyard", "Residence Inn", "SpringHill Suites",
            "Fairfield", "TownePlace Suites", "Sheraton", "Westin",
            "W Hotels", "Ritz-Carlton", "AC Hotels", "Aloft", "Element",
            "Moxy", "Le Meridien", "St. Regis", "JW Marriott",
            "Renaissance Hotels", "Protea Hotels", "Four Points",
            "Delta Hotels",
        ],
    ),
    "Belk": (
        "Belk",
        "department",
        ["Belk"],
    ),
    "CVS": (
        "CVS",
        "pharmacy",
        ["CVS", "CVS Pharmacy", "CVS Health"],
    ),
    # --- Batch 2: Retail + Restaurants + Thrift ---
    "Applebees": (
        "Applebee's",
        "restaurant",
        ["Applebee's", "Applebees"],
    ),
    "A&W": (
        "A&W",
        "fast_food",
        ["A&W", "A & W"],
    ),
    "TJ Maxx": (
        "TJ Maxx",
        "clothing",
        ["TJ Maxx", "T.J. Maxx", "TJX"],
    ),
    "Joann": (
        "Joann",
        "craft",
        ["Joann", "Jo-Ann", "JOANN"],
    ),
    "Hallmark": (
        "Hallmark",
        "gift",
        ["Hallmark"],
    ),
    "Banana Republic": (
        "Banana Republic",
        "clothing",
        ["Banana Republic"],
    ),
    "Salvation Army": (
        "The Salvation Army Thrift Stores",
        "thrift",
        ["Salvation Army"],
    ),
    "Bealls Outlet": (
        "Bealls Outlet",
        "department",
        ["Bealls", "Beall's"],
    ),
    "Clarks": (
        "Clarks",
        "shoes",
        ["Clarks"],
    ),
    "Cost Cutters": (
        "Cost Cutters",
        "salon",
        ["Cost Cutters"],
    ),
    "Showcase Cinemas": (
        "Showcase Cinemas",
        "cinema",
        ["Showcase Cinemas", "Showcase Cinema"],
    ),
    # --- Batch 3: Restaurants ---
    "Back Yard Burgers": (
        "Back Yard Burgers",
        "fast_food",
        ["Back Yard Burgers"],
    ),
    "Ben & Jerry's": (
        "Ben & Jerry's",
        "fast_food",
        ["Ben & Jerry's", "Ben and Jerry's", "Ben & Jerrys"],
    ),
    "Bob's Big Boy": (
        "Bob's Big Boy",
        "restaurant",
        ["Bob's Big Boy", "Bobs Big Boy", "Big Boy"],
    ),
    "Bob Evans": (
        "Bob Evans",
        "restaurant",
        ["Bob Evans"],
    ),
    "Boston Market": (
        "Boston Market",
        "fast_food",
        ["Boston Market"],
    ),
    "Bruster's": (
        "Bruster's",
        "fast_food",
        ["Bruster's", "Brusters"],
    ),
    "Captain D's": (
        "Captain D's Seafood",
        "fast_food",
        ["Captain D's", "Captain Ds"],
    ),
    "Golden Corral": (
        "Golden Corral",
        "restaurant",
        ["Golden Corral"],
    ),
    "Landry's": (
        "Landry's Inc. Restaurants",
        "restaurant",
        ["Landry's", "Landrys"],
    ),
    "Mr. Gatti's": (
        "Mr. Gatti's Pizza",
        "restaurant",
        ["Mr. Gatti's", "Mr Gattis", "Gatti's Pizza"],
    ),
    "Mrs. Fields": (
        "Mrs. Fields",
        "fast_food",
        ["Mrs. Fields", "Mrs Fields"],
    ),
    "Old Spaghetti Factory": (
        "The Old Spaghetti Factory",
        "restaurant",
        ["Old Spaghetti Factory", "The Old Spaghetti Factory"],
    ),
    "Sonic": (
        "Sonic",
        "fast_food",
        ["Sonic", "Sonic Drive-In"],
    ),
    "Taco Bell": (
        "Taco Bell",
        "fast_food",
        ["Taco Bell"],
    ),
    "TCBY": (
        "TCBY",
        "fast_food",
        ["TCBY"],
    ),
    "Tea Room Cafe": (
        "Tea Room Cafe",
        "restaurant",
        ["Tea Room Cafe", "Tea Room"],
    ),
    "Whataburger": (
        "Whataburger",
        "fast_food",
        ["Whataburger"],
    ),
    # --- Batch 3: Grocery ---
    "Compare Foods": (
        "Compare Foods Supermarket",
        "grocery",
        ["Compare Foods"],
    ),
    "Great Valu": (
        "Great Valu Food Store",
        "grocery",
        ["Great Valu"],
    ),
    "Gristedes": (
        "Gristedes Supermarket",
        "grocery",
        ["Gristedes", "Gristede's"],
    ),
    "Morton Williams": (
        "Morton Williams Supermarket",
        "grocery",
        ["Morton Williams"],
    ),
    "Piggly Wiggly": (
        "Piggly Wiggly",
        "grocery",
        ["Piggly Wiggly"],
    ),
    "Rogers Marketplace": (
        "Rogers Marketplace",
        "grocery",
        ["Rogers Marketplace", "Rogers"],
    ),
    "Uncle Giuseppe's": (
        "Uncle Giuseppe's Marketplace",
        "grocery",
        ["Uncle Giuseppe's", "Uncle Giuseppes"],
    ),
    # --- Batch 3: Auto Service ---
    "Valvoline": (
        "Valvoline",
        "car_service",
        ["Valvoline", "Valvoline Instant Oil Change"],
    ),
}


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


def build_overpass_query(category: str, brand_patterns: List[str]) -> str:
    """Build an Overpass QL query for the given category and brand patterns."""
    # Build brand regex: case-insensitive match on brand OR name tag
    # Escape regex special chars in brand names, join with |
    escaped = [re.escape(b) for b in brand_patterns]
    brand_regex = "|".join(escaped)

    # Determine the primary tag filter based on category
    if category == "motel":
        # Motel 6 might be tagged as tourism=motel or tourism=hotel
        tag_filters = [
            f'nwr["tourism"="motel"]["brand"~"{brand_regex}",i]',
            f'nwr["tourism"="hotel"]["brand"~"{brand_regex}",i]',
            f'nwr["tourism"="motel"]["name"~"{brand_regex}",i]',
            f'nwr["tourism"="hotel"]["name"~"{brand_regex}",i]',
        ]
    elif category == "hotel":
        tag_filters = [
            f'nwr["tourism"="hotel"]["brand"~"{brand_regex}",i]',
            f'nwr["tourism"="hotel"]["name"~"{brand_regex}",i]',
            # Some might be tagged as tourism=motel
            f'nwr["tourism"="motel"]["brand"~"{brand_regex}",i]',
        ]
    elif category == "pharmacy":
        tag_filters = [
            f'nwr["amenity"="pharmacy"]["brand"~"{brand_regex}",i]',
            f'nwr["amenity"="pharmacy"]["name"~"{brand_regex}",i]',
            f'nwr["shop"="chemist"]["brand"~"{brand_regex}",i]',
        ]
    elif category == "department":
        tag_filters = [
            f'nwr["shop"="department_store"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="department_store"]["name"~"{brand_regex}",i]',
            f'nwr["shop"="clothes"]["brand"~"{brand_regex}",i]',
        ]
    elif category == "restaurant":
        tag_filters = [
            f'nwr["amenity"="restaurant"]["brand"~"{brand_regex}",i]',
            f'nwr["amenity"="restaurant"]["name"~"{brand_regex}",i]',
            f'nwr["amenity"="fast_food"]["brand"~"{brand_regex}",i]',
            f'nwr["amenity"="fast_food"]["name"~"{brand_regex}",i]',
        ]
    elif category == "fast_food":
        tag_filters = [
            f'nwr["amenity"="fast_food"]["brand"~"{brand_regex}",i]',
            f'nwr["amenity"="fast_food"]["name"~"{brand_regex}",i]',
            f'nwr["amenity"="restaurant"]["brand"~"{brand_regex}",i]',
            f'nwr["amenity"="restaurant"]["name"~"{brand_regex}",i]',
        ]
    elif category == "clothing":
        tag_filters = [
            f'nwr["shop"="clothes"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="clothes"]["name"~"{brand_regex}",i]',
            f'nwr["shop"="department_store"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="fashion"]["brand"~"{brand_regex}",i]',
        ]
    elif category == "craft":
        tag_filters = [
            f'nwr["shop"="craft"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="craft"]["name"~"{brand_regex}",i]',
            f'nwr["shop"="fabric"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="fabric"]["name"~"{brand_regex}",i]',
        ]
    elif category == "gift":
        tag_filters = [
            f'nwr["shop"="gift"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="gift"]["name"~"{brand_regex}",i]',
            f'nwr["shop"="stationery"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="stationery"]["name"~"{brand_regex}",i]',
        ]
    elif category == "thrift":
        tag_filters = [
            f'nwr["shop"="charity"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="charity"]["name"~"{brand_regex}",i]',
            f'nwr["shop"="second_hand"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="second_hand"]["name"~"{brand_regex}",i]',
            f'nwr["amenity"="social_facility"]["name"~"{brand_regex}",i]',
        ]
    elif category == "shoes":
        tag_filters = [
            f'nwr["shop"="shoes"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="shoes"]["name"~"{brand_regex}",i]',
        ]
    elif category == "salon":
        tag_filters = [
            f'nwr["shop"="hairdresser"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="hairdresser"]["name"~"{brand_regex}",i]',
            f'nwr["amenity"="hairdresser"]["brand"~"{brand_regex}",i]',
            f'nwr["amenity"="hairdresser"]["name"~"{brand_regex}",i]',
        ]
    elif category == "cinema":
        tag_filters = [
            f'nwr["amenity"="cinema"]["brand"~"{brand_regex}",i]',
            f'nwr["amenity"="cinema"]["name"~"{brand_regex}",i]',
        ]
    elif category == "grocery":
        tag_filters = [
            f'nwr["shop"="supermarket"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="supermarket"]["name"~"{brand_regex}",i]',
            f'nwr["shop"="convenience"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="greengrocer"]["name"~"{brand_regex}",i]',
        ]
    elif category == "car_service":
        tag_filters = [
            f'nwr["shop"="car_repair"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="car_repair"]["name"~"{brand_regex}",i]',
            f'nwr["amenity"="car_wash"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="car"]["brand"~"{brand_regex}",i]',
            f'nwr["shop"="car_parts"]["brand"~"{brand_regex}",i]',
        ]
    else:
        tag_filters = [
            f'nwr["brand"~"{brand_regex}",i]',
            f'nwr["name"~"{brand_regex}",i]',
        ]

    # Build union query
    union_body = "\n  ".join(f"{tf}({US_BBOX});" for tf in tag_filters)

    query = f"""[out:json][timeout:300];
(
  {union_body}
);
out center body;"""

    return query


def normalize_state(state_raw: str) -> str:
    """Normalize state to 2-letter abbreviation."""
    s = state_raw.strip()
    if len(s) == 2:
        return s.upper()
    # Try full name lookup
    lower = s.lower()
    if lower in STATE_NAME_TO_ABBR:
        return STATE_NAME_TO_ABBR[lower]
    return s.upper()[:2]


def normalize_phone(raw: str) -> str:
    """Normalize phone to (XXX) XXX-XXXX format."""
    # Strip leading +1 or +1-
    clean = re.sub(r"^\+1[\s-]?", "", raw.strip())
    digits = re.sub(r"\D", "", clean)
    if len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw.strip()


def enrich_with_reverse_geocoding(
    locations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Fill in missing city/state using offline reverse geocoding. Filters out non-US."""
    if not locations:
        return locations

    # Collect coordinates for batch reverse geocoding
    coords = [(float(loc["latitude"]), float(loc["longitude"])) for loc in locations]

    # Batch reverse geocode (very fast - thousands per second)
    results = rg.search(coords, verbose=False)

    enriched: List[Dict[str, Any]] = []
    for loc, geo in zip(locations, results):
        cc = geo.get("cc", "")

        # Filter out non-US locations
        if cc != "US":
            continue

        # Fill in missing city
        if not loc.get("city"):
            loc["city"] = geo.get("name", "")

        # Fill in missing state from admin1 code (e.g., "US.CA" -> "CA")
        if not loc.get("state"):
            admin1 = geo.get("admin1", "")
            # admin1 is the full state name in reverse_geocoder
            state_abbr = STATE_NAME_TO_ABBR.get(admin1.lower(), "")
            if state_abbr:
                loc["state"] = state_abbr

        enriched.append(loc)

    return enriched


def parse_osm_elements(
    data: Dict[str, Any],
    brand_patterns: List[str],
) -> List[Dict[str, Any]]:
    """Parse Overpass API JSON response into location dicts."""
    locations: List[Dict[str, Any]] = []
    seen_keys: set = set()

    # Build a set of lowercase brand patterns for validation
    brand_lower = {b.lower() for b in brand_patterns}

    elements = data.get("elements", [])
    for el in elements:
        tags = el.get("tags", {})

        # Get coordinates (nodes have lat/lon directly, ways/relations use center)
        lat = el.get("lat") or (el.get("center", {}) or {}).get("lat")
        lon = el.get("lon") or (el.get("center", {}) or {}).get("lon")

        if not lat or not lon:
            continue

        # Extract address components
        address = tags.get("addr:street", "").strip()
        housenumber = tags.get("addr:housenumber", "").strip()
        city = tags.get("addr:city", "").strip()
        state_raw = tags.get("addr:state", "").strip()
        zipcode = tags.get("addr:postcode", "").strip()

        # Build full street address
        if housenumber and address:
            full_address = f"{housenumber} {address}"
        elif address:
            full_address = address
        elif housenumber:
            full_address = housenumber
        else:
            full_address = ""

        # Get name and brand
        name = tags.get("name", "").strip()
        brand = tags.get("brand", "").strip()

        # Validate that this actually matches our brand
        # (OSM regex matching can be loose)
        name_lower = name.lower()
        brand_lower_val = brand.lower()
        matched = False
        for bp in brand_lower:
            if bp in name_lower or bp in brand_lower_val:
                matched = True
                break
        if not matched:
            continue

        # Normalize state
        state = normalize_state(state_raw) if state_raw else ""

        # Normalize ZIP
        if zipcode:
            zip_match = re.search(r"\b(\d{5})\b", zipcode)
            zipcode = zip_match.group(1) if zip_match else ""

        # Phone
        phone = tags.get("phone", "") or tags.get("contact:phone", "")
        if phone:
            phone = normalize_phone(phone)

        # Website
        website = tags.get("website", "") or tags.get("contact:website", "")

        # Dedup by lat/lon rounded to 4 decimal places (approx 11m precision)
        dedup_key = (round(float(lat), 4), round(float(lon), 4))
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        locations.append({
            "name": name or brand,
            "address": full_address,
            "city": city,
            "state": state,
            "zip": zipcode,
            "phone": phone,
            "latitude": str(lat),
            "longitude": str(lon),
            "store_url": website,
        })

    return locations


def fetch_osm_locations(
    category: str,
    brand_patterns: List[str],
    merchant_key: str,
) -> List[Dict[str, Any]]:
    """Fetch locations from the Overpass API."""
    query = build_overpass_query(category, brand_patterns)

    log.info(
        "overpass_query",
        merchant=merchant_key,
        category=category,
        brands=len(brand_patterns),
        query_len=len(query),
    )

    with httpx.Client(timeout=httpx.Timeout(connect=30, read=360, write=30, pool=30)) as client:
        resp = client.post(
            OVERPASS_URL,
            data={"data": query},
            headers={"Accept": "application/json"},
        )
        if resp.status_code == 429:
            log.warning("overpass_rate_limited", merchant=merchant_key)
            # Wait and retry once
            time.sleep(30)
            resp = client.post(
                OVERPASS_URL,
                data={"data": query},
                headers={"Accept": "application/json"},
            )

        if resp.status_code != 200:
            log.error(
                "overpass_failed",
                merchant=merchant_key,
                status=resp.status_code,
                body=resp.text[:200],
            )
            return []

        data = resp.json()
        raw_count = len(data.get("elements", []))
        log.info("overpass_response", merchant=merchant_key, raw_elements=raw_count)

        locations = parse_osm_elements(data, brand_patterns)

        # Enrich with reverse geocoding and filter to US-only
        before = len(locations)
        locations = enrich_with_reverse_geocoding(locations)
        log.info(
            "reverse_geocoded",
            merchant=merchant_key,
            before=before,
            after=len(locations),
            non_us_removed=before - len(locations),
        )

        return locations


def locations_to_rows(
    locations: List[Dict[str, Any]],
    merchant_name: str,
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema (A:Q)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []

    for loc in locations:
        state = (loc.get("state") or "").upper().strip()[:2]
        if state and state not in VALID_STATES:
            continue

        zip_code = (loc.get("zip") or "").strip()
        if zip_code:
            zip_match = re.search(r"\b(\d{5})\b", zip_code)
            zip_code = zip_match.group(1) if zip_match else ""

        rows.append([
            merchant_name,
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
            "v2_osm_overpass",
        ])

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape merchant locations from OpenStreetMap Overpass API"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument(
        "--merchant",
        required=True,
        help="Merchant key (e.g. 'Hilton', 'CVS') or 'all' for all defined merchants",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    # Determine which merchants to process
    if args.merchant.lower() == "all":
        merchants_to_run = list(MERCHANT_DEFS.keys())
    else:
        # Find matching merchant (case-insensitive partial match)
        matched = None
        for key in MERCHANT_DEFS:
            if key.lower() == args.merchant.lower():
                matched = key
                break
        if not matched:
            # Try partial match
            for key in MERCHANT_DEFS:
                if args.merchant.lower() in key.lower():
                    matched = key
                    break
        if not matched:
            print(f"Unknown merchant: {args.merchant}")
            print(f"Available: {', '.join(MERCHANT_DEFS.keys())}")
            sys.exit(1)
        merchants_to_run = [matched]

    # Prepare sheets service (only if not dry-run)
    sheets_svc = None
    if not args.dry_run:
        sheets_svc = get_sheets_service()

    grand_total_locations = 0
    grand_total_rows = 0

    for merchant_key in merchants_to_run:
        sheet_name, category, brand_patterns = MERCHANT_DEFS[merchant_key]
        t0 = time.monotonic()

        print(f"\n{'=' * 70}")
        print(f"  {merchant_key} (sheet name: {sheet_name})")
        print(f"  Category: {category} | Brands: {', '.join(brand_patterns[:5])}{'...' if len(brand_patterns) > 5 else ''}")
        print(f"{'=' * 70}")

        # Fetch from OSM
        try:
            locations = fetch_osm_locations(category, brand_patterns, merchant_key)
        except Exception as e:
            elapsed = time.monotonic() - t0
            print(f"  ERROR: {e} ({round(elapsed, 1)}s)")
            if len(merchants_to_run) > 1:
                time.sleep(15)
            continue
        elapsed = time.monotonic() - t0

        if not locations:
            print(f"  No locations found ({round(elapsed, 1)}s)")
            # Small delay between merchants to avoid rate limiting
            if len(merchants_to_run) > 1:
                time.sleep(5)
            continue

        # Build rows
        merchant_id = lookup_merchant_id(sheet_name)
        rows = locations_to_rows(locations, sheet_name, merchant_id)

        grand_total_locations += len(locations)
        grand_total_rows += len(rows)

        print(f"  OSM elements parsed: {len(locations)}")
        print(f"  Valid rows:          {len(rows)}")
        print(f"  Elapsed:             {round(elapsed, 1)}s")

        if args.dry_run:
            print(f"  (DRY RUN - nothing written)")
            # Show breakdown by state
            state_counts: Dict[str, int] = {}
            no_state = 0
            for r in rows:
                st = r[6]
                if st:
                    state_counts[st] = state_counts.get(st, 0) + 1
                else:
                    no_state += 1
            print(f"  States represented:  {len(state_counts)}")
            if no_state:
                print(f"  No state (lat/lon only): {no_state}")
            # Show sample
            for r in rows[:5]:
                print(f"    {r[2]:45s} {r[5]:20s} {r[6]:2s} {r[7]:5s}")
            if len(rows) > 5:
                print(f"    ... and {len(rows) - 5} more")
        else:
            if rows:
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

        # Delay between merchants
        if len(merchants_to_run) > 1:
            time.sleep(10)

    # Grand summary
    if len(merchants_to_run) > 1:
        print(f"\n{'=' * 70}")
        print(f"  GRAND TOTAL")
        print(f"{'=' * 70}")
        print(f"  Merchants processed: {len(merchants_to_run)}")
        print(f"  Total locations:     {grand_total_locations}")
        print(f"  Total valid rows:    {grand_total_rows}")
        if args.dry_run:
            print(f"  (DRY RUN - nothing written)")
    print()


if __name__ == "__main__":
    main()
