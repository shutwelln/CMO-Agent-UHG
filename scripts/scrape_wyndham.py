#!/usr/bin/env python3
"""Custom scraper for Wyndham Hotels (all brands) via sitemap + JSON-LD.

Wyndham owns ~15 hotel brands (Days Inn, La Quinta, Super 8, Ramada, etc.).
Property sitemaps are publicly listed in the sitemap index. Each property
overview page has JSON-LD with @type "Hotel" containing full address, coords,
and phone. No anti-bot protection - plain HTTP works fine.

Usage:
    python scripts/scrape_wyndham.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_wyndham.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
import xml.etree.ElementTree as ET
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

MERCHANT_NAME = "Wyndham / Days Inn / La Quinta"
SITEMAP_INDEX_URL = "https://www.wyndhamhotels.com/sitemap.xml"

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

# Wyndham brand codes found in property sitemaps
BRAND_CODES = {
    "se": "Super 8",
    "di": "Days Inn",
    "ra": "Ramada",
    "lq": "La Quinta",
    "bu": "Baymont",
    "tl": "Travelodge",
    "hj": "Howard Johnson",
    "mt": "Microtel",
    "tq": "Trademark Collection",
    "wg": "Wingate",
    "gn": "Wyndham Garden",
    "aa": "AmericInn",
    "hr": "Hawthorn",
    "vo": "Wyndham VO",
    "wt": "Wyndham",
    "gr": "Wyndham Grand",
}

# XML namespace used in sitemaps
SITEMAP_NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


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


def parse_sitemap_index(xml_text: str) -> List[str]:
    """Parse the sitemap index and return all property sub-sitemap URLs."""
    root = ET.fromstring(xml_text)
    urls: List[str] = []
    for sitemap_el in root.findall("sm:sitemap", SITEMAP_NS):
        loc_el = sitemap_el.find("sm:loc", SITEMAP_NS)
        if loc_el is not None and loc_el.text:
            url = loc_el.text.strip()
            if "_properties_" in url:
                urls.append(url)
    return urls


def parse_property_sitemap(xml_text: str) -> List[str]:
    """Parse a property sub-sitemap and return all overview page URLs."""
    root = ET.fromstring(xml_text)
    urls: List[str] = []
    for url_el in root.findall("sm:url", SITEMAP_NS):
        loc_el = url_el.find("sm:loc", SITEMAP_NS)
        if loc_el is not None and loc_el.text:
            url = loc_el.text.strip()
            if url.endswith("/overview"):
                urls.append(url)
    return urls


def clean_phone(phone: str) -> str:
    """Strip +1- prefix and normalize phone number."""
    if not phone:
        return ""
    phone = phone.strip()
    # Remove +1- or +1 prefix
    phone = re.sub(r"^\+1[-\s]?", "", phone)
    return phone


def parse_property_page(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract location data from a Wyndham property overview page.

    Primary: JSON-LD with @type "Hotel"
    Fallback: JavaScript variables (overview_propertyName, property_city_name, etc.)
    """
    loc: Dict[str, Any] = {"store_url": url}

    # --- Primary: JSON-LD ---
    jsonld_pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL,
    )
    for match in jsonld_pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") == "Hotel":
                    addr = item.get("address", {})
                    geo = item.get("geo", {})
                    country = (addr.get("addressCountry") or "").strip()
                    return {
                        "name": (item.get("name") or "").strip(),
                        "address": (addr.get("streetAddress") or "").strip(),
                        "city": (addr.get("addressLocality") or "").strip(),
                        "state": (addr.get("addressRegion") or "").strip(),
                        "zip": (addr.get("postalCode") or "").strip(),
                        "country": country,
                        "phone": clean_phone(item.get("telephone") or ""),
                        "latitude": str(geo.get("latitude") or ""),
                        "longitude": str(geo.get("longitude") or ""),
                        "store_url": url,
                    }
        except (json.JSONDecodeError, ValueError):
            continue

    # --- Fallback: JavaScript variables ---
    js_vars = {
        "name": r'overview_propertyName\s*=\s*"([^"]*)"',
        "latitude": r'overview_lat\s*=\s*"([^"]*)"',
        "longitude": r'overview_long\s*=\s*"([^"]*)"',
        "city": r'property_city_name\s*=\s*"([^"]*)"',
        "state": r'property_state_code\s*=\s*"([^"]*)"',
        "country_code": r'property_country_code\s*=\s*"([^"]*)"',
    }
    for field, pattern in js_vars.items():
        m = re.search(pattern, html)
        if m:
            loc[field] = m.group(1).strip()

    # Try to get address from the page if JS vars found a city
    if loc.get("city"):
        # Map country_code to country string for filtering
        cc = loc.pop("country_code", "")
        if cc == "US":
            loc["country"] = "United States"
        else:
            loc["country"] = cc

        # Try to extract address from visible content or meta tags
        addr_match = re.search(
            r'<span[^>]*class="[^"]*address[^"]*"[^>]*>([^<]+)</span>',
            html, re.IGNORECASE,
        )
        if addr_match:
            loc["address"] = addr_match.group(1).strip()

        # Try phone from tel: link
        phone_match = re.search(r'href="tel:([^"]+)"', html)
        if phone_match:
            loc["phone"] = clean_phone(phone_match.group(1))

        if loc.get("name"):
            return loc

    return None


def is_us_property(loc: Dict[str, Any]) -> bool:
    """Check if a location is in the United States."""
    country = (loc.get("country") or "").strip()
    state = (loc.get("state") or "").upper().strip()[:2]

    # Check country field
    if country and country.lower() in ("united states", "us", "usa"):
        return True

    # Check if state is a valid US state
    if state in VALID_STATES:
        return True

    return False


async def fetch_property_sitemaps(
    client: httpx.AsyncClient,
) -> List[str]:
    """Fetch sitemap index, then all property sub-sitemaps, return overview URLs."""
    # Step 1: Fetch the main sitemap index
    log.info("fetching_sitemap_index", url=SITEMAP_INDEX_URL)
    resp = await client.get(SITEMAP_INDEX_URL)
    if resp.status_code != 200:
        log.error("sitemap_index_failed", status=resp.status_code)
        return []

    property_sitemap_urls = parse_sitemap_index(resp.text)
    log.info("property_sitemaps_found", count=len(property_sitemap_urls))

    if not property_sitemap_urls:
        log.warning("no_property_sitemaps_found")
        return []

    # Step 2: Fetch each property sub-sitemap
    all_overview_urls: List[str] = []
    sem = asyncio.Semaphore(5)

    async def fetch_sub_sitemap(sitemap_url: str) -> List[str]:
        async with sem:
            try:
                r = await client.get(sitemap_url)
                if r.status_code == 200:
                    urls = parse_property_sitemap(r.text)
                    # Extract brand code for logging
                    brand_match = re.search(r"_([a-z]{2})_properties_", sitemap_url)
                    brand = brand_match.group(1) if brand_match else "??"
                    log.info(
                        "sub_sitemap_parsed",
                        brand=brand,
                        brand_name=BRAND_CODES.get(brand, "Unknown"),
                        overview_urls=len(urls),
                    )
                    return urls
                else:
                    log.warning(
                        "sub_sitemap_failed",
                        url=sitemap_url,
                        status=r.status_code,
                    )
            except Exception as e:
                log.warning(
                    "sub_sitemap_error",
                    url=sitemap_url,
                    error=str(e)[:100],
                )
            return []

    tasks = [fetch_sub_sitemap(u) for u in property_sitemap_urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for result in results:
        if isinstance(result, list):
            all_overview_urls.extend(result)

    log.info("total_overview_urls", count=len(all_overview_urls))
    return all_overview_urls


async def scrape_wyndham() -> List[Dict[str, Any]]:
    """Scrape all Wyndham Hotels locations from property overview pages."""
    locations: List[Dict[str, Any]] = []
    seen_keys: set = set()

    async with httpx.AsyncClient(
        timeout=30, headers=HEADERS, follow_redirects=True
    ) as client:
        # Step 1 & 2: Get all property overview URLs from sitemaps
        overview_urls = await fetch_property_sitemaps(client)

        if not overview_urls:
            log.warning("no_overview_urls_found")
            return locations

        # Step 3: Fetch each property overview page
        sem = asyncio.Semaphore(10)
        errors = 0

        async def fetch_property(url: str) -> Optional[Dict[str, Any]]:
            nonlocal errors
            async with sem:
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return parse_property_page(r.text, url)
                    else:
                        errors += 1
                except Exception as e:
                    errors += 1
                    log.warning(
                        "property_fetch_failed",
                        url=url[:80],
                        error=str(e)[:100],
                    )
                return None

        batch_size = 50
        for i in range(0, len(overview_urls), batch_size):
            batch_urls = overview_urls[i : i + batch_size]
            tasks = [fetch_property(u) for u in batch_urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for r in results:
                if isinstance(r, dict) and r.get("address") and r.get("city"):
                    # Filter to US-only
                    if not is_us_property(r):
                        continue

                    # Dedup by address+city+state
                    key = (
                        r.get("address", "").lower().strip(),
                        r.get("city", "").lower().strip(),
                        r.get("state", "").upper().strip(),
                    )
                    if key not in seen_keys:
                        seen_keys.add(key)
                        locations.append(r)

            if i + batch_size < len(overview_urls):
                await asyncio.sleep(0.3)

            log.info(
                "batch_done",
                batch_end=min(i + batch_size, len(overview_urls)),
                total=len(overview_urls),
                locations_so_far=len(locations),
                errors=errors,
            )

    return locations


def locations_to_rows(
    locations: List[Dict[str, Any]],
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema."""
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
            "v2_wyndham_custom",
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    locations = await scrape_wyndham()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 1))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Wyndham Custom Scraper")
    print(f"{'=' * 60}")
    print(f"  Locations scraped:  {len(locations)}")
    print(f"  Valid rows:         {len(rows)}")
    print(f"  Elapsed:            {round(elapsed, 1)}s")

    if args.dry_run:
        print(f"  (DRY RUN - nothing written)")
        for r in rows[:10]:
            print(f"    {r[2]:50s} {r[5]:20s} {r[6]:2s} {r[7]:5s}")
        if len(rows) > 10:
            print(f"    ... and {len(rows) - 10} more")
    else:
        sheets_svc = get_sheets_service()
        # Write in chunks of 5000 rows to avoid API limits
        chunk_size = 5000
        total_written = 0
        for ci in range(0, len(rows), chunk_size):
            chunk = rows[ci : ci + chunk_size]
            resp = (
                sheets_svc.spreadsheets()
                .values()
                .append(
                    spreadsheetId=args.sheet_id,
                    range=f"{SCRAPED_TAB}!A:Q",
                    valueInputOption="RAW",
                    insertDataOption="INSERT_ROWS",
                    body={"values": chunk},
                )
                .execute()
            )
            written = resp.get("updates", {}).get("updatedRows", len(chunk))
            total_written += written
            log.info("sheet_chunk_written", chunk=ci, written=written)
        print(f"  Written to sheet:   {total_written}")

    print()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Wyndham Hotels (all brands) from sitemaps + JSON-LD"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
