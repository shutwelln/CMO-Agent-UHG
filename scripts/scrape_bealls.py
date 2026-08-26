#!/usr/bin/env python3
"""Custom scraper for Bealls Outlet locations.

Bealls uses Yext with exposed API keys. This scraper tries:
1. Yext Content Delivery API (entities endpoint)
2. Yext Search API (vertical search endpoint)
3. Fallback: sitemap crawl + HTML parsing

API Discovery:
- Content Delivery API key: 6e7ebdc4d4e57c3e0d97e27960051f97
- Search API key: 94c39b95b0b1b36c4e686a543eba842b
- Sitemap: https://stores.bealls.com/sitemap1.xml (~800 locations)

Usage:
    python scripts/scrape_bealls.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_bealls.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from xml.etree import ElementTree as ET

import httpx
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

MERCHANT_NAME = "Bealls Outlet"
SHEET_NAME = "Bealls Outlet"

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

# Yext API keys
YEXT_CONTENT_API_KEY = "6e7ebdc4d4e57c3e0d97e27960051f97"
YEXT_SEARCH_API_KEY = "94c39b95b0b1b36c4e686a543eba842b"

# API endpoints
YEXT_ENTITIES_URL = "https://cdn.yextapis.com/v2/accounts/me/entities"
YEXT_SEARCH_URL = "https://cdn.yextapis.com/v2/accounts/me/search/vertical"
SITEMAP_URL = "https://stores.bealls.com/sitemap1.xml"


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


def normalize_phone(phone: str) -> str:
    """Normalize phone to (XXX) XXX-XXXX format."""
    digits = re.sub(r"\D", "", phone)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return phone


def make_dedup_key(address: str, city: str, state: str) -> str:
    """Generate dedup hash from address+city+state."""
    key = f"{address.lower().strip()}|{city.lower().strip()}|{state.upper().strip()}"
    return hashlib.md5(key.encode()).hexdigest()


def fetch_yext_entities() -> List[Dict[str, Any]]:
    """Fetch locations from Yext Content Delivery API (entities endpoint)."""
    log.info("fetching_yext_entities")
    locations: List[Dict[str, Any]] = []

    with httpx.Client(timeout=30) as client:
        offset = 0
        limit = 50

        while True:
            try:
                resp = client.get(
                    YEXT_ENTITIES_URL,
                    params={
                        "api_key": YEXT_CONTENT_API_KEY,
                        "v": "20230101",
                        "entityTypes": "location",
                        "limit": limit,
                        "offset": offset,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                entities = data.get("response", {}).get("entities", [])
                if not entities:
                    break

                for entity in entities:
                    loc = parse_yext_entity(entity)
                    if loc:
                        locations.append(loc)

                log.info("yext_entities_batch", offset=offset, count=len(entities))

                # Check if there are more results
                count = data.get("response", {}).get("count", 0)
                if offset + limit >= count:
                    break

                offset += limit
                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                log.error("yext_entities_error", offset=offset, error=str(e))
                break

    log.info("yext_entities_done", total=len(locations))
    return locations


def parse_yext_entity(entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse a Yext entity into our location format."""
    try:
        address_data = entity.get("address", {})
        name = entity.get("name", "")

        return {
            "name": name,
            "address": address_data.get("line1", ""),
            "address2": address_data.get("line2", ""),
            "city": address_data.get("city", ""),
            "state": address_data.get("region", ""),
            "zip": address_data.get("postalCode", ""),
            "phone": entity.get("mainPhone", ""),
            "store_url": entity.get("websiteUrl", {}).get("url", ""),
            "latitude": entity.get("yextDisplayCoordinate", {}).get("latitude"),
            "longitude": entity.get("yextDisplayCoordinate", {}).get("longitude"),
            "hours": "",  # Could parse from entity.get("hours", {})
        }
    except Exception as e:
        log.error("parse_entity_error", error=str(e), entity_id=entity.get("meta", {}).get("id"))
        return None


def fetch_yext_search() -> List[Dict[str, Any]]:
    """Fetch locations from Yext Search API (vertical search endpoint)."""
    log.info("fetching_yext_search")
    locations: List[Dict[str, Any]] = []

    with httpx.Client(timeout=30) as client:
        offset = 0
        limit = 50

        while True:
            try:
                resp = client.get(
                    YEXT_SEARCH_URL,
                    params={
                        "api_key": YEXT_SEARCH_API_KEY,
                        "v": "20230101",
                        "experienceKey": "bealls-locator",
                        "verticalKey": "locations",
                        "limit": limit,
                        "offset": offset,
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                results = data.get("response", {}).get("results", [])
                if not results:
                    break

                for result in results:
                    loc = parse_yext_search_result(result)
                    if loc:
                        locations.append(loc)

                log.info("yext_search_batch", offset=offset, count=len(results))

                # Check if there are more results
                total = data.get("response", {}).get("resultsCount", 0)
                if offset + limit >= total:
                    break

                offset += limit
                time.sleep(0.5)  # Rate limiting

            except Exception as e:
                log.error("yext_search_error", offset=offset, error=str(e))
                break

    log.info("yext_search_done", total=len(locations))
    return locations


def parse_yext_search_result(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Parse a Yext search result into our location format."""
    try:
        data = result.get("data", {})
        address_data = data.get("address", {})

        return {
            "name": data.get("name", ""),
            "address": address_data.get("line1", ""),
            "address2": address_data.get("line2", ""),
            "city": address_data.get("city", ""),
            "state": address_data.get("region", ""),
            "zip": address_data.get("postalCode", ""),
            "phone": data.get("mainPhone", ""),
            "store_url": data.get("landingPageUrl", ""),
            "latitude": data.get("yextDisplayCoordinate", {}).get("latitude"),
            "longitude": data.get("yextDisplayCoordinate", {}).get("longitude"),
            "hours": "",
        }
    except Exception as e:
        log.error("parse_search_result_error", error=str(e))
        return None


def fetch_sitemap_urls() -> List[str]:
    """Fetch store page URLs from sitemap."""
    log.info("fetching_sitemap", url=SITEMAP_URL)
    urls: List[str] = []

    try:
        with httpx.Client(timeout=30) as client:
            resp = client.get(SITEMAP_URL)
            resp.raise_for_status()

            root = ET.fromstring(resp.content)
            ns = {"ns": "http://www.sitemaps.org/schemas/sitemap/0.9"}

            for url_elem in root.findall(".//ns:url", ns):
                loc = url_elem.find("ns:loc", ns)
                if loc is not None and loc.text:
                    # Filter for store pages (skip root/category pages)
                    if loc.text.count("/") >= 4:  # e.g., stores.bealls.com/fl/orlando/123
                        urls.append(loc.text)

            log.info("sitemap_parsed", urls=len(urls))
    except Exception as e:
        log.error("sitemap_error", error=str(e))

    return urls


def scrape_store_page(url: str, client: httpx.Client) -> Optional[Dict[str, Any]]:
    """Scrape a single store page for location data."""
    try:
        resp = client.get(url, timeout=15)
        resp.raise_for_status()
        html = resp.text

        # Basic regex patterns (adjust based on actual HTML structure)
        name_match = re.search(r'<h1[^>]*>([^<]+)</h1>', html)
        address_match = re.search(
            r'<span[^>]*itemprop="streetAddress"[^>]*>([^<]+)</span>', html
        )
        city_match = re.search(r'<span[^>]*itemprop="addressLocality"[^>]*>([^<]+)</span>', html)
        state_match = re.search(r'<span[^>]*itemprop="addressRegion"[^>]*>([^<]+)</span>', html)
        zip_match = re.search(r'<span[^>]*itemprop="postalCode"[^>]*>([^<]+)</span>', html)
        phone_match = re.search(r'<a[^>]*href="tel:([^"]+)"[^>]*>', html)
        lat_match = re.search(r'"latitude"\s*:\s*([0-9.-]+)', html)
        lon_match = re.search(r'"longitude"\s*:\s*([0-9.-]+)', html)

        return {
            "name": name_match.group(1).strip() if name_match else "",
            "address": address_match.group(1).strip() if address_match else "",
            "address2": "",
            "city": city_match.group(1).strip() if city_match else "",
            "state": state_match.group(1).strip() if state_match else "",
            "zip": zip_match.group(1).strip() if zip_match else "",
            "phone": phone_match.group(1).strip() if phone_match else "",
            "store_url": url,
            "latitude": float(lat_match.group(1)) if lat_match else None,
            "longitude": float(lon_match.group(1)) if lon_match else None,
            "hours": "",
        }
    except Exception as e:
        log.error("scrape_page_error", url=url, error=str(e))
        return None


def fetch_from_sitemap() -> List[Dict[str, Any]]:
    """Fallback: crawl sitemap and scrape store pages."""
    log.info("falling_back_to_sitemap")
    urls = fetch_sitemap_urls()

    if not urls:
        return []

    locations: List[Dict[str, Any]] = []

    with httpx.Client(timeout=30) as client:
        for i, url in enumerate(urls):
            loc = scrape_store_page(url, client)
            if loc and loc.get("name"):
                locations.append(loc)

            if (i + 1) % 50 == 0:
                log.info("sitemap_scrape_progress", scraped=i + 1, total=len(urls))
                time.sleep(1)  # Rate limiting
            else:
                time.sleep(0.2)

    log.info("sitemap_scrape_done", total=len(locations))
    return locations


def get_locations() -> List[Dict[str, Any]]:
    """Fetch locations using the best available method."""
    # Try Yext entities API first
    locations = fetch_yext_entities()
    if locations:
        log.info("using_yext_entities", count=len(locations))
        return locations

    # Try Yext search API
    locations = fetch_yext_search()
    if locations:
        log.info("using_yext_search", count=len(locations))
        return locations

    # Fallback to sitemap crawl
    locations = fetch_from_sitemap()
    log.info("using_sitemap_fallback", count=len(locations))
    return locations


def locations_to_rows(
    locations: List[Dict[str, Any]],
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema (A:Q).

    Filters to US-only, normalizes phones, and deduplicates by address+city+state.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []
    seen_keys: Set[str] = set()

    for loc in locations:
        state = (loc.get("state") or "").upper().strip()[:2]
        if state not in VALID_STATES:
            continue

        address = (loc.get("address") or "").strip()
        city = (loc.get("city") or "").strip()

        # Dedup check
        dedup_key = make_dedup_key(address, city, state)
        if dedup_key in seen_keys:
            continue
        seen_keys.add(dedup_key)

        # Normalize zip code
        zip_code = (loc.get("zip") or "").strip()
        if zip_code:
            zip_match = re.search(r"\b(\d{5})\b", zip_code)
            zip_code = zip_match.group(1) if zip_match else ""

        # Normalize phone
        phone = normalize_phone(loc.get("phone") or "")

        rows.append([
            MERCHANT_NAME,
            str(merchant_id) if merchant_id else "TBD",
            (loc.get("name") or "").strip(),
            address,
            (loc.get("address2") or "").strip(),
            city,
            state,
            zip_code,
            phone,
            (loc.get("hours") or "").strip(),
            (loc.get("store_url") or "").strip(),
            str(loc.get("latitude") or ""),
            str(loc.get("longitude") or ""),
            "Pending",
            now,
            "",  # pushed_at
            "v2_bealls_yext",
        ])

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description=f"Scrape {MERCHANT_NAME} locations via Yext API or sitemap"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t0 = time.monotonic()

    # Fetch locations
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
    print(f"  {MERCHANT_NAME} - Yext API Scraper")
    print(f"{'=' * 60}")
    print(f"  Locations fetched:  {len(locations)}")
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
