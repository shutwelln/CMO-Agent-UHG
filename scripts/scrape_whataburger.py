#!/usr/bin/env python3
"""Custom scraper for Whataburger store locations via Yext directory pages.

Whataburger uses Yext to power their store locator at locations.whataburger.com.
The directory is structured as:
    /directory.html       -> list of state links
    /{state}.html         -> list of city links within that state
    /{state}/{city}.html  -> individual location cards with embedded JSON-LD

Strategy:
1. Fetch /directory.html to discover state pages
2. For each state page, discover city pages
3. For each city page, extract location data from JSON-LD or HTML patterns
4. Deduplicate by address+city+state

Usage:
    python scripts/scrape_whataburger.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_whataburger.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import asyncio
import json
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

MERCHANT_NAME = "Whataburger"
BASE_SITE = "https://locations.whataburger.com"
DIRECTORY_URL = f"{BASE_SITE}/directory.html"

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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

VALID_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

# Two-letter state abbreviation to slug mapping for Yext directory URLs.
# Yext directories use lowercase full state names in the URL path (e.g., /tx.html).
# We need the reverse mapping too: given a slug from the page, resolve the state abbrev.
STATE_ABBREV = {
    "alabama": "AL", "alaska": "AK", "arizona": "AZ", "arkansas": "AR",
    "california": "CA", "colorado": "CO", "connecticut": "CT", "delaware": "DE",
    "florida": "FL", "georgia": "GA", "hawaii": "HI", "idaho": "ID",
    "illinois": "IL", "indiana": "IN", "iowa": "IA", "kansas": "KS",
    "kentucky": "KY", "louisiana": "LA", "maine": "ME", "maryland": "MD",
    "massachusetts": "MA", "michigan": "MI", "minnesota": "MN",
    "mississippi": "MS", "missouri": "MO", "montana": "MT", "nebraska": "NE",
    "nevada": "NV", "new-hampshire": "NH", "new-jersey": "NJ",
    "new-mexico": "NM", "new-york": "NY", "north-carolina": "NC",
    "north-dakota": "ND", "ohio": "OH", "oklahoma": "OK", "oregon": "OR",
    "pennsylvania": "PA", "rhode-island": "RI", "south-carolina": "SC",
    "south-dakota": "SD", "tennessee": "TN", "texas": "TX", "utah": "UT",
    "vermont": "VT", "virginia": "VA", "washington": "WA",
    "west-virginia": "WV", "wisconsin": "WI", "wyoming": "WY",
    "district-of-columbia": "DC",
    # Also handle two-letter slugs (Yext sometimes uses these)
    "al": "AL", "ak": "AK", "az": "AZ", "ar": "AR", "ca": "CA", "co": "CO",
    "ct": "CT", "de": "DE", "fl": "FL", "ga": "GA", "hi": "HI", "id": "ID",
    "il": "IL", "in": "IN", "ia": "IA", "ks": "KS", "ky": "KY", "la": "LA",
    "me": "ME", "md": "MD", "ma": "MA", "mi": "MI", "mn": "MN", "ms": "MS",
    "mo": "MO", "mt": "MT", "ne": "NE", "nv": "NV", "nh": "NH", "nj": "NJ",
    "nm": "NM", "ny": "NY", "nc": "NC", "nd": "ND", "oh": "OH", "ok": "OK",
    "or": "OR", "pa": "PA", "ri": "RI", "sc": "SC", "sd": "SD", "tn": "TN",
    "tx": "TX", "ut": "UT", "vt": "VT", "va": "VA", "wa": "WA", "wv": "WV",
    "wi": "WI", "wy": "WY", "dc": "DC",
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


def normalize_phone(raw: str) -> str:
    """Normalize phone to (XXX) XXX-XXXX format."""
    if not raw:
        return ""
    raw = re.sub(r"^\+1-?", "", raw.strip())
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw.strip()


def extract_state_links(html: str) -> List[str]:
    """Extract state page links from the directory.html page.

    Yext directory pages list states as links like:
        <a href="/al.html">Alabama</a>
        <a href="/tx.html">Texas</a>
    or sometimes relative paths within a directory listing container.
    """
    links: List[str] = []
    # Match href patterns pointing to state pages.
    # Links may be relative (al.html), root-relative (/al.html), or absolute.
    pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*?([a-z]{2})\.html)["\']',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        href = match.group(1).strip()
        slug = match.group(2).lower()

        # Only include if the slug maps to a valid US state
        if slug in STATE_ABBREV:
            # Skip city/store pages that have a path separator before the slug
            # (e.g., /tx/houston.html should not match as a state page)
            clean = href.split("?")[0].rstrip("/")
            # Count path segments - state pages have just one segment like "tx.html"
            path_part = clean.split("//")[-1]  # strip protocol
            if "/" in path_part:
                # Has path segments - check it's not a sub-path
                after_host = path_part.split("/", 1)[-1] if "." in path_part.split("/")[0] else path_part
                if "/" in after_host.replace(f"{slug}.html", "").rstrip("/"):
                    continue  # skip - this is a city or store page
            # Normalize to absolute URL
            if href.startswith("http"):
                pass
            elif href.startswith("/"):
                href = BASE_SITE + href
            else:
                href = BASE_SITE + "/" + href
            links.append(href)

    return sorted(set(links))


def extract_city_links(html: str, state_url: str) -> List[str]:
    """Extract city page links from a state page.

    State pages list cities as links like:
        <a href="/tx/houston.html">Houston</a>
    """
    links: List[str] = []
    # The state URL looks like https://locations.whataburger.com/tx.html
    # City pages are at /tx/houston.html (state-slug/city-slug.html)
    # Extract the state slug from the URL
    state_slug_match = re.search(r'/([a-z][a-z0-9-]+)\.html$', state_url, re.IGNORECASE)
    if not state_slug_match:
        return links
    state_slug = state_slug_match.group(1).lower()

    # Match links to city pages under this state.
    # Links may be relative (tx/houston.html), root-relative (/tx/houston.html), or absolute.
    pattern = re.compile(
        rf'<a[^>]+href=["\']([^"\']*?{re.escape(state_slug)}/[a-z0-9-]+\.html)["\']',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        href = match.group(1).strip()
        if href.startswith("http"):
            pass
        elif href.startswith("/"):
            href = BASE_SITE + href
        else:
            href = BASE_SITE + "/" + href
        links.append(href)

    # Also look for links that could be individual location pages directly
    # (some Yext directories skip the city level for small cities)
    return sorted(set(links))


def extract_location_links(html: str) -> List[str]:
    """Extract individual location page links from a city page.

    City pages may link to individual store pages like:
        /tx/houston/1234-main-street.html
    """
    links: List[str] = []
    # Match href patterns with 3+ path segments ending in .html
    pattern = re.compile(
        r'<a[^>]+href=["\']([^"\']*?/[a-z][a-z0-9-]*/[a-z0-9-]+/[a-z0-9-]+\.html)["\']',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        href = match.group(1).strip()
        if href.startswith("/"):
            href = BASE_SITE + href
        elif not href.startswith("http"):
            href = BASE_SITE + "/" + href
        links.append(href)

    return sorted(set(links))


def state_from_url(url: str) -> str:
    """Derive the two-letter state abbreviation from a Yext directory URL.

    e.g., /tx/houston.html -> TX
          /texas/houston.html -> TX
    """
    # Extract the first path segment after the domain
    match = re.search(r'locations\.whataburger\.com/([a-z][a-z0-9-]*)', url, re.IGNORECASE)
    if match:
        slug = match.group(1).lower()
        if slug in STATE_ABBREV:
            return STATE_ABBREV[slug]
    return ""


def parse_jsonld_locations(html: str, page_url: str) -> List[Dict[str, Any]]:
    """Extract location data from JSON-LD blocks in the page.

    Yext pages typically embed one or more LocalBusiness/Restaurant JSON-LD blocks.
    A city page may have multiple locations, each in its own JSON-LD script tag.
    """
    locations: List[Dict[str, Any]] = []
    pattern = re.compile(
        r'<script\s+type=["\']application/ld\+json["\']\s*>(.*?)</script>',
        re.DOTALL,
    )

    for match in pattern.finditer(html):
        raw = match.group(1).strip()
        try:
            data = json.loads(raw, strict=False)
        except (json.JSONDecodeError, ValueError):
            continue

        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue

            # Check @type
            item_type = item.get("@type", "")
            if isinstance(item_type, list):
                types = [t.lower() for t in item_type]
            else:
                types = [str(item_type).lower()]

            target_types = {
                "restaurant", "fastfoodrestaurant", "foodestablishment",
                "localbusiness", "store",
            }
            if not any(t in target_types for t in types):
                # Check @graph
                if "@graph" in item:
                    for graph_item in item["@graph"]:
                        if not isinstance(graph_item, dict):
                            continue
                        gt = graph_item.get("@type", "")
                        gt_list = [gt.lower()] if isinstance(gt, str) else [str(g).lower() for g in gt]
                        if any(t in target_types for t in gt_list):
                            loc = _extract_from_jsonld(graph_item, page_url)
                            if loc:
                                locations.append(loc)
                continue

            loc = _extract_from_jsonld(item, page_url)
            if loc:
                locations.append(loc)

    return locations


def _extract_from_jsonld(item: Dict[str, Any], page_url: str) -> Optional[Dict[str, Any]]:
    """Extract location fields from a single JSON-LD item."""
    addr = item.get("address", {})
    if isinstance(addr, str):
        return None
    if not isinstance(addr, dict):
        return None

    street = (addr.get("streetAddress") or "").strip()
    city = (addr.get("addressLocality") or "").strip()
    state = (addr.get("addressRegion") or "").strip()
    zip_code = (addr.get("postalCode") or "").strip()

    if not street or not city:
        return None

    # Geo coordinates
    geo = item.get("geo", {})
    lat = ""
    lon = ""
    if isinstance(geo, dict):
        lat = str(geo.get("latitude", "")).strip()
        lon = str(geo.get("longitude", "")).strip()

    # Phone
    phone = normalize_phone(item.get("telephone") or addr.get("telephone") or "")

    # Name
    name = (item.get("name") or "").strip()

    # Store URL: prefer the item's url field, fall back to page URL
    store_url = (item.get("url") or page_url).strip()

    return {
        "name": name,
        "address": street,
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "latitude": lat,
        "longitude": lon,
        "store_url": store_url,
    }


def parse_html_locations(html: str, page_url: str) -> List[Dict[str, Any]]:
    """Fallback: extract location data from HTML patterns when JSON-LD is missing.

    Yext pages often embed location data in structured HTML with data attributes,
    address blocks, and tel: links. This function uses multiple regex strategies.
    """
    locations: List[Dict[str, Any]] = []

    # Strategy 1: Look for Yext location cards with data attributes
    # Yext often uses data-lat/data-lng or data-latitude/data-longitude
    card_pattern = re.compile(
        r'data-lat(?:itude)?=["\']([0-9.\-]+)["\'][^>]*data-l(?:ng|on|ongitude)=["\']([0-9.\-]+)["\']',
        re.IGNORECASE,
    )
    for lat_match in card_pattern.finditer(html):
        lat = lat_match.group(1)
        lon = lat_match.group(2)
        # Try to find the nearest address block
        # Look backwards from this match for address info
        start_pos = max(0, lat_match.start() - 2000)
        block = html[start_pos:lat_match.end() + 500]
        loc = _parse_address_block(block, page_url, lat, lon)
        if loc:
            locations.append(loc)

    if locations:
        return locations

    # Strategy 2: Look for structured address elements (Yext listing format)
    # Pattern: street address, city, state, zip in nearby elements
    addr_blocks = re.findall(
        r'class=["\'][^"\']*(?:address|location|listing)[^"\']*["\'][^>]*>'
        r'(.*?)</(?:div|article|section|li)',
        html,
        re.DOTALL | re.IGNORECASE,
    )

    for block in addr_blocks:
        loc = _parse_address_block(block, page_url)
        if loc:
            locations.append(loc)

    if locations:
        return locations

    # Strategy 3: Look for full address patterns in the page body
    # "1234 Main Street, Houston, TX 77001"
    full_addr_pattern = re.compile(
        r'(\d+\s+[A-Za-z0-9\s.#]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Way|Ln|Lane|Ct|Court|Pkwy|Parkway|Hwy|Highway|Pl|Place|Cir|Circle|Loop|Trail|Trl|Fwy|Freeway)[.,]?)\s*'
        r'(?:<[^>]*>\s*)*'
        r'([A-Za-z\s]+),\s*'
        r'([A-Z]{2})\s+'
        r'(\d{5})',
        re.IGNORECASE,
    )
    seen_addrs: set = set()
    for addr_m in full_addr_pattern.finditer(html):
        street = addr_m.group(1).strip().rstrip(",.")
        city = addr_m.group(2).strip()
        state = addr_m.group(3).upper()
        zip_code = addr_m.group(4)

        key = f"{street.lower()}|{city.lower()}|{state}"
        if key in seen_addrs:
            continue
        seen_addrs.add(key)

        if state in VALID_STATES:
            # Try to find phone near this address
            phone = ""
            nearby = html[max(0, addr_m.start() - 500):addr_m.end() + 500]
            tel_m = re.search(r'href=["\']tel:([^"\']+)["\']', nearby)
            if tel_m:
                phone = normalize_phone(tel_m.group(1))

            locations.append({
                "name": "",
                "address": street,
                "city": city,
                "state": state,
                "zip": zip_code,
                "phone": phone,
                "latitude": "",
                "longitude": "",
                "store_url": page_url,
            })

    return locations


def _parse_address_block(
    block: str, page_url: str, lat: str = "", lon: str = ""
) -> Optional[Dict[str, Any]]:
    """Parse a chunk of HTML for address components."""
    loc: Dict[str, str] = {"store_url": page_url, "latitude": lat, "longitude": lon}

    # Street address
    street_m = re.search(
        r'(?:class=["\'][^"\']*(?:street|address-line|line1)[^"\']*["\'][^>]*>|'
        r'itemprop=["\']streetAddress["\'][^>]*>)\s*([^<]+)',
        block, re.IGNORECASE,
    )
    if street_m:
        loc["address"] = street_m.group(1).strip()

    # City
    city_m = re.search(
        r'(?:class=["\'][^"\']*(?:city|locality)[^"\']*["\'][^>]*>|'
        r'itemprop=["\']addressLocality["\'][^>]*>)\s*([^<]+)',
        block, re.IGNORECASE,
    )
    if city_m:
        loc["city"] = city_m.group(1).strip().rstrip(",")

    # State
    state_m = re.search(
        r'(?:class=["\'][^"\']*(?:state|region)[^"\']*["\'][^>]*>|'
        r'itemprop=["\']addressRegion["\'][^>]*>)\s*([^<]+)',
        block, re.IGNORECASE,
    )
    if state_m:
        loc["state"] = state_m.group(1).strip().rstrip(",")

    # ZIP
    zip_m = re.search(
        r'(?:class=["\'][^"\']*(?:zip|postal)[^"\']*["\'][^>]*>|'
        r'itemprop=["\']postalCode["\'][^>]*>)\s*([^<]+)',
        block, re.IGNORECASE,
    )
    if zip_m:
        loc["zip"] = zip_m.group(1).strip()

    # Phone
    phone_m = re.search(r'href=["\']tel:([^"\']+)["\']', block, re.IGNORECASE)
    if phone_m:
        loc["phone"] = normalize_phone(phone_m.group(1))

    # Name
    name_m = re.search(
        r'(?:class=["\'][^"\']*(?:location-name|listing-title|name)[^"\']*["\'][^>]*>)\s*([^<]+)',
        block, re.IGNORECASE,
    )
    if name_m:
        loc["name"] = name_m.group(1).strip()

    if loc.get("address") and loc.get("city"):
        return {
            "name": loc.get("name", ""),
            "address": loc.get("address", ""),
            "city": loc.get("city", ""),
            "state": loc.get("state", ""),
            "zip": loc.get("zip", ""),
            "phone": loc.get("phone", ""),
            "latitude": loc.get("latitude", ""),
            "longitude": loc.get("longitude", ""),
            "store_url": loc.get("store_url", page_url),
        }
    return None


def parse_yext_js_data(html: str, page_url: str) -> List[Dict[str, Any]]:
    """Extract location data from Yext-embedded JavaScript objects.

    Whataburger pages embed a JSON blob directly in a <script> tag:
        <script>{"response":{"entities": [...]}}</script>
    Also handles window.__INITIAL_STATE__ / window.__YEXT_DATA__ patterns.
    """
    locations: List[Dict[str, Any]] = []

    # Pattern 1: Raw JSON in script tags containing "entities" (Whataburger style)
    raw_json_pattern = re.compile(
        r'<script[^>]*>\s*(\{"response"\s*:\s*\{"entities"\s*:\s*\[.*?\]\s*\}\s*\})\s*</script>',
        re.DOTALL,
    )
    for match in raw_json_pattern.finditer(html):
        raw = match.group(1)
        try:
            data = json.loads(raw)
            found = _find_locations_in_obj(data, page_url)
            locations.extend(found)
        except (json.JSONDecodeError, ValueError):
            continue

    if locations:
        return locations

    # Pattern 2: window.__VAR__ = {...} style
    js_data_pattern = re.compile(
        r'(?:window\.__[A-Z_]+__|Yext\.[A-Za-z]+)\s*=\s*(\{.*?\});?\s*(?:</script>|$)',
        re.DOTALL,
    )
    for match in js_data_pattern.finditer(html):
        raw = match.group(1)
        try:
            data = json.loads(raw)
            found = _find_locations_in_obj(data, page_url)
            locations.extend(found)
        except (json.JSONDecodeError, ValueError):
            continue

    if locations:
        return locations

    # Pattern 3: Parse from <address> tags + embedded coordinates
    locations = _parse_from_address_tags(html, page_url)
    return locations


def _parse_from_address_tags(html: str, page_url: str) -> List[Dict[str, Any]]:
    """Parse locations from Yext <address> tags and coordinate data."""
    locations: List[Dict[str, Any]] = []

    # Extract all coordinate data from any script containing yextDisplayCoordinate
    coord_map: Dict[int, tuple] = {}  # index -> (lat, lon)
    coord_pattern = re.compile(
        r'"yextDisplayCoordinate"\s*:\s*\{\s*"lat"\s*:\s*([\d.-]+)\s*,\s*"long"\s*:\s*([\d.-]+)',
    )
    for i, m in enumerate(coord_pattern.finditer(html)):
        coord_map[i] = (m.group(1), m.group(2))

    # Extract store URLs
    url_pattern = re.compile(r'"url"\s*:\s*"(\.\./[^"]+\.html)"')
    urls = [m.group(1) for m in url_pattern.finditer(html)]

    # Extract address blocks
    addr_pattern = re.compile(r'<address[^>]*>(.*?)</address>', re.DOTALL)
    for i, addr_match in enumerate(addr_pattern.finditer(html)):
        block = addr_match.group(1)
        street = ""
        city = ""
        state = ""
        zip_code = ""

        sm = re.search(r'c-address-street-1["\s>]*>([^<]+)', block)
        if sm:
            street = sm.group(1).strip()
        cm = re.search(r'c-address-city["\s>]*>([^<]+)', block)
        if cm:
            city = cm.group(1).strip()
        stm = re.search(r'c-address-state["\s>]*>([^<]+)', block)
        if stm:
            state = stm.group(1).strip()
        zm = re.search(r'c-address-postal-code["\s>]*>([^<]+)', block)
        if zm:
            zip_code = zm.group(1).strip()

        if not street or not city:
            continue

        # Resolve state abbreviation
        state_lower = state.lower().replace(" ", "-")
        state_abbr = STATE_ABBREV.get(state_lower, state[:2].upper())

        lat, lon = coord_map.get(i, ("", ""))
        store_url = ""
        if i < len(urls):
            rel = urls[i]
            # Convert relative ../tx/houston/... to absolute
            base = page_url.rsplit("/", 1)[0]
            if rel.startswith("../"):
                base = base.rsplit("/", 1)[0]
                rel = rel[3:]
            store_url = base + "/" + rel

        # Extract phone from nearby tel: link
        # Look in a region around this address
        phone = ""
        pm = re.search(r'tel:\+?1?(\d{10})', block)
        if pm:
            d = pm.group(1)
            phone = f"({d[:3]}) {d[3:6]}-{d[6:]}"

        locations.append({
            "name": f"Whataburger",
            "address": street,
            "city": city,
            "state": state_abbr,
            "zip": zip_code,
            "phone": phone,
            "latitude": lat,
            "longitude": lon,
            "store_url": store_url if store_url.startswith("http") else page_url,
        })

    return locations


def _find_locations_in_obj(obj: Any, page_url: str) -> List[Dict[str, Any]]:
    """Recursively search a parsed JSON object for location data."""
    locations: List[Dict[str, Any]] = []

    if isinstance(obj, dict):
        # Check if this dict looks like a location
        has_addr = "address" in obj or "streetAddress" in obj or "line1" in obj
        has_coord = "latitude" in obj or "lat" in obj or "yextDisplayCoordinate" in obj
        if has_addr or has_coord:
            loc = _try_extract_location_from_dict(obj, page_url)
            if loc:
                locations.append(loc)
                return locations

        # Recurse into values
        for v in obj.values():
            locations.extend(_find_locations_in_obj(v, page_url))

    elif isinstance(obj, list):
        for item in obj:
            locations.extend(_find_locations_in_obj(item, page_url))

    return locations


def _try_extract_location_from_dict(d: Dict[str, Any], page_url: str) -> Optional[Dict[str, Any]]:
    """Try to extract a location from a dict that might contain address/geo data."""
    # Address fields - try multiple key patterns
    street = (
        d.get("streetAddress") or d.get("line1") or d.get("address1") or ""
    )
    if isinstance(d.get("address"), dict):
        addr = d["address"]
        street = street or addr.get("streetAddress") or addr.get("line1") or ""
        city = addr.get("addressLocality") or addr.get("city") or ""
        state = addr.get("addressRegion") or addr.get("region") or addr.get("state") or ""
        zip_code = addr.get("postalCode") or addr.get("zip") or ""
    else:
        city = d.get("city") or d.get("addressLocality") or ""
        state = d.get("state") or d.get("region") or d.get("addressRegion") or ""
        zip_code = d.get("zip") or d.get("postalCode") or ""

    if isinstance(street, str):
        street = street.strip()
    else:
        street = ""
    if isinstance(city, str):
        city = city.strip()
    else:
        city = ""

    if not street or not city:
        return None

    # Coordinates
    lat = ""
    lon = ""
    if "yextDisplayCoordinate" in d and isinstance(d["yextDisplayCoordinate"], dict):
        coord = d["yextDisplayCoordinate"]
        lat = str(coord.get("lat") or coord.get("latitude") or "")
        lon = str(coord.get("long") or coord.get("longitude") or "")
    elif "displayCoordinate" in d and isinstance(d["displayCoordinate"], dict):
        lat = str(d["displayCoordinate"].get("latitude", ""))
        lon = str(d["displayCoordinate"].get("longitude", ""))
    else:
        lat = str(d.get("latitude") or d.get("lat") or "")
        lon = str(d.get("longitude") or d.get("lng") or d.get("lon") or "")

    phone = normalize_phone(str(d.get("phone") or d.get("telephone") or d.get("mainPhone") or ""))
    name = str(d.get("name") or d.get("geomodifier") or d.get("locationName") or "").strip()
    store_url = str(d.get("url") or d.get("slug") or page_url).strip()

    if isinstance(state, str):
        state = state.strip()
    else:
        state = ""
    if isinstance(zip_code, str):
        zip_code = zip_code.strip()
    else:
        zip_code = ""

    return {
        "name": name,
        "address": street,
        "city": city,
        "state": state,
        "zip": zip_code,
        "phone": phone,
        "latitude": lat,
        "longitude": lon,
        "store_url": store_url if store_url.startswith("http") else page_url,
    }


def parse_page_locations(html: str, page_url: str) -> List[Dict[str, Any]]:
    """Extract all locations from a page using multiple strategies.

    Tries in order:
    1. JSON-LD structured data
    2. Yext JS embedded data
    3. HTML pattern matching
    """
    # Strategy 1: JSON-LD
    locations = parse_jsonld_locations(html, page_url)
    if locations:
        return locations

    # Strategy 2: Yext JS data objects
    locations = parse_yext_js_data(html, page_url)
    if locations:
        return locations

    # Strategy 3: HTML patterns
    locations = parse_html_locations(html, page_url)
    return locations


async def scrape_whataburger() -> List[Dict[str, Any]]:
    """Scrape all Whataburger locations via Yext directory crawl.

    Flow: directory.html -> state pages -> city pages -> location data
    """
    all_locations: List[Dict[str, Any]] = []
    seen_keys: set = set()
    sem = asyncio.Semaphore(5)

    async with httpx.AsyncClient(
        timeout=30, headers=HEADERS, follow_redirects=True
    ) as client:
        # ---- Step 1: Fetch directory page to get state links ----
        log.info("fetching_directory", url=DIRECTORY_URL)
        try:
            resp = await client.get(DIRECTORY_URL)
            if resp.status_code != 200:
                log.error("directory_failed", status=resp.status_code)
                return all_locations
        except Exception as e:
            log.error("directory_fetch_error", error=str(e)[:200])
            return all_locations

        state_urls = extract_state_links(resp.text)
        log.info("state_pages_found", count=len(state_urls))

        if not state_urls:
            # The directory page itself might contain locations directly
            locs = parse_page_locations(resp.text, DIRECTORY_URL)
            log.info("directory_page_locations", count=len(locs))
            for loc in locs:
                _add_location(loc, all_locations, seen_keys)
            return all_locations

        # ---- Step 2: Fetch each state page to get city links ----
        async def fetch_state(state_url: str) -> List[str]:
            """Return list of city page URLs from a state page."""
            async with sem:
                try:
                    r = await client.get(state_url)
                    if r.status_code != 200:
                        log.warning("state_page_failed", url=state_url, status=r.status_code)
                        return []
                    city_urls = extract_city_links(r.text, state_url)

                    # If city pages found, return them.
                    # Also check if the state page itself has locations
                    # (happens when a state has only one city)
                    if not city_urls:
                        locs = parse_page_locations(r.text, state_url)
                        if locs:
                            for loc in locs:
                                # Fill in state from URL if missing
                                if not loc.get("state"):
                                    loc["state"] = state_from_url(state_url)
                                _add_location(loc, all_locations, seen_keys)
                            log.info("state_page_locations", url=state_url, count=len(locs))

                    return city_urls
                except Exception as e:
                    log.warning("state_fetch_error", url=state_url, error=str(e)[:100])
                    return []

        # Batch fetch state pages
        state_tasks = [fetch_state(u) for u in state_urls]
        all_city_urls: List[str] = []

        batch_size = 10
        for i in range(0, len(state_tasks), batch_size):
            batch = state_tasks[i : i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    all_city_urls.extend(r)
                elif isinstance(r, Exception):
                    log.warning("state_batch_error", error=str(r)[:100])

            if i + batch_size < len(state_tasks):
                await asyncio.sleep(0.3)

            log.info(
                "state_batch_done",
                batch=i + len(batch),
                total=len(state_tasks),
                city_urls_so_far=len(all_city_urls),
            )

        all_city_urls = sorted(set(all_city_urls))
        log.info("city_pages_found", count=len(all_city_urls))

        # ---- Step 3: Fetch each city page for locations ----
        async def fetch_city(city_url: str) -> List[Dict[str, Any]]:
            """Fetch a city page and extract locations."""
            async with sem:
                try:
                    r = await client.get(city_url)
                    if r.status_code != 200:
                        log.warning("city_page_failed", url=city_url, status=r.status_code)
                        return []

                    # First check if this is a city listing page with individual location links
                    location_links = extract_location_links(r.text)

                    # Always try to parse locations from the city page itself
                    # (Yext city pages typically have all location data embedded)
                    locs = parse_page_locations(r.text, city_url)

                    # If we got locations from the page, use them
                    if locs:
                        # Fill in state from URL if missing
                        state = state_from_url(city_url)
                        for loc in locs:
                            if not loc.get("state") and state:
                                loc["state"] = state
                        return locs

                    # If no locations parsed but we have location links,
                    # fetch individual location pages
                    if location_links:
                        sub_locs: List[Dict[str, Any]] = []
                        for link in location_links:
                            try:
                                lr = await client.get(link)
                                if lr.status_code == 200:
                                    page_locs = parse_page_locations(lr.text, link)
                                    sub_locs.extend(page_locs)
                            except Exception:
                                pass
                        return sub_locs

                    return []
                except Exception as e:
                    log.warning("city_fetch_error", url=city_url, error=str(e)[:100])
                    return []

        # Batch fetch city pages
        city_tasks = [fetch_city(u) for u in all_city_urls]

        for i in range(0, len(city_tasks), batch_size):
            batch = city_tasks[i : i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    for loc in r:
                        _add_location(loc, all_locations, seen_keys)
                elif isinstance(r, Exception):
                    log.warning("city_batch_error", error=str(r)[:100])

            if i + batch_size < len(city_tasks):
                await asyncio.sleep(0.3)

            log.info(
                "city_batch_done",
                batch=min(i + batch_size, len(city_tasks)),
                total=len(city_tasks),
                locations_so_far=len(all_locations),
            )

    return all_locations


def _add_location(
    loc: Dict[str, Any],
    locations: List[Dict[str, Any]],
    seen_keys: set,
) -> None:
    """Add a location to the list if it passes dedup and validation."""
    address = (loc.get("address") or "").strip()
    city = (loc.get("city") or "").strip()
    state = (loc.get("state") or "").upper().strip()

    if not address or not city:
        return

    # Normalize state to 2-letter abbreviation
    if len(state) > 2:
        state = STATE_ABBREV.get(state.lower().replace(" ", "-"), state[:2].upper())
    loc["state"] = state

    key = f"{address.lower()}|{city.lower()}|{state}"
    if key in seen_keys:
        return
    seen_keys.add(key)

    locations.append(loc)


def locations_to_rows(
    locations: List[Dict[str, Any]],
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
            "v2_whataburger_yext",
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    locations = await scrape_whataburger()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 1))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Yext Directory Scraper")
    print(f"{'=' * 60}")
    print(f"  Locations scraped:  {len(locations)}")
    print(f"  Valid rows:         {len(rows)}")
    print(f"  Elapsed:            {round(elapsed, 1)}s")

    if args.dry_run:
        print(f"  (DRY RUN - nothing written)")
        for r in rows[:5]:
            print(f"    {r[2]:40s} {r[5]:20s} {r[6]:2s} {r[7]:5s}")
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
        description="Scrape Whataburger locations via Yext directory"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
