#!/usr/bin/env python3
"""Custom scraper for Hallmark stores.

Hallmark has a store locator at stores.hallmark.com with embedded JSON on city pages.
Strategy:
1. Fetch sitemap index
2. Extract city-level pages (pattern: /xx/cityname/)
3. Fetch each city page and parse embedded JSON
4. Deduplicate by location ID (lid)

Usage:
    python scripts/scrape_hallmark.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_hallmark.py \
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
from typing import Any, Dict, List, Optional, Set

import httpx
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

MERCHANT_NAME = "Hallmark"

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

SITEMAP_INDEX = "https://stores.hallmark.com/sitemap.xml"
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


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


async def fetch_sitemap_index(client: httpx.AsyncClient) -> List[str]:
    """Fetch sitemap index and extract sub-sitemap URLs."""
    log.info("fetching_sitemap_index", url=SITEMAP_INDEX)
    try:
        resp = await client.get(SITEMAP_INDEX, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        text = resp.text

        # Extract all sitemap/loc URLs
        sitemap_urls = re.findall(r'<loc>(https://stores\.hallmark\.com/[^<]+)</loc>', text)
        log.info("sitemap_index_parsed", total_urls=len(sitemap_urls))
        return sitemap_urls
    except Exception as e:
        log.error("sitemap_index_fetch_failed", error=str(e))
        return []


async def fetch_city_urls_from_sitemap(
    client: httpx.AsyncClient, sitemap_url: str
) -> List[str]:
    """Fetch a sub-sitemap and extract city-level page URLs."""
    try:
        resp = await client.get(sitemap_url, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        text = resp.text

        # Extract city-level URLs (pattern: /xx/cityname/)
        # Avoid state-only pages (pattern: /xx/)
        city_pattern = r'<loc>(https://stores\.hallmark\.com/[a-z]{2}/[^/<]+/)</loc>'
        city_urls = re.findall(city_pattern, text)
        return city_urls
    except Exception as e:
        log.error("sitemap_fetch_failed", url=sitemap_url, error=str(e)[:100])
        return []


async def extract_locations_from_city_page(
    client: httpx.AsyncClient, url: str
) -> List[Dict[str, Any]]:
    """Fetch a city page and extract embedded JSON location data from $config.defaultListData."""
    import json as _json

    try:
        resp = await client.get(url, headers={"User-Agent": USER_AGENT})
        resp.raise_for_status()
        html = resp.text

        locations: List[Dict[str, Any]] = []

        # Hallmark stores embed data as: $config.defaultListData = '[{...}]'
        json_match = re.search(
            r"""\$config\.defaultListData\s*=\s*'(\[.*?\])'\s*;""",
            html,
            re.DOTALL,
        )

        if not json_match:
            # Fallback: double-quoted variant
            json_match = re.search(
                r"""\$config\.defaultListData\s*=\s*"(\[.*?\])"\s*;""",
                html,
                re.DOTALL,
            )

        if json_match:
            raw = json_match.group(1)
            # Data is stored as escaped JSON inside a single-quoted JS string:
            #   $config.defaultListData = '[{\"fid\":\"059588\",...}]';
            # Use regex to unescape one escape at a time (left-to-right).
            # Handles double-escaping correctly: \\" → \", \\/ → /
            raw = re.sub(r"\\(.)", lambda m: m.group(1), raw)
            try:
                locations = _json.loads(raw)
                log.debug("locations_extracted", url=url, count=len(locations))
            except _json.JSONDecodeError as e:
                log.error("json_parse_failed", url=url, error=str(e)[:100])
        else:
            log.debug("no_json_found", url=url)

        return locations
    except Exception as e:
        log.error("city_page_fetch_failed", url=url, error=str(e)[:100])
        return []


async def scrape_all_locations() -> List[Dict[str, Any]]:
    """Scrape all Hallmark locations from city pages."""
    async with httpx.AsyncClient(
        timeout=30, follow_redirects=True
    ) as client:
        # Step 1: Get sitemap URLs (may be sub-sitemaps or direct city pages)
        sitemap_urls = await fetch_sitemap_index(client)

        if not sitemap_urls:
            log.warning("no_sitemap_urls_found")
            return []

        # Separate sub-sitemaps (.xml) from direct city pages
        # City pages: /xx/cityname/ (exactly 2 path segments after domain)
        # Exclude: state pages (/xx/), store detail pages (/xx/city/store-slug.html)
        sub_sitemaps = [u for u in sitemap_urls if u.endswith(".xml")]
        city_re = re.compile(r'^https://stores\.hallmark\.com/[a-z]{2}/[a-z][^/]+/$')
        direct_city_urls = [u for u in sitemap_urls if city_re.match(u)]

        log.info("sitemap_breakdown", sub_sitemaps=len(sub_sitemaps), direct_cities=len(direct_city_urls))

        # If sub-sitemaps exist, fetch them for city URLs
        all_city_urls: Set[str] = set(direct_city_urls)
        if sub_sitemaps:
            tasks = [fetch_city_urls_from_sitemap(client, url) for url in sub_sitemaps]
            results = await asyncio.gather(*tasks)
            for city_urls_batch in results:
                all_city_urls.update(city_urls_batch)

        city_list = sorted(all_city_urls)
        log.info("city_urls_collected", total=len(city_list))

        if not city_list:
            log.warning("no_city_urls_found")
            return []

        # Step 2: Fetch city pages with concurrency limit
        semaphore = asyncio.Semaphore(8)

        async def fetch_with_limit(url: str) -> List[Dict[str, Any]]:
            async with semaphore:
                return await extract_locations_from_city_page(client, url)

        log.info("fetching_city_pages", total=len(city_list))
        tasks2 = [fetch_with_limit(url) for url in city_list]
        results = await asyncio.gather(*tasks2)

        # Flatten results
        all_locations: List[Dict[str, Any]] = []
        for locs in results:
            all_locations.extend(locs)

        log.info("locations_scraped", total=len(all_locations))

        # Deduplicate by lid (location ID) or by address+city+state
        seen_lids: Set[str] = set()
        seen_addresses: Set[str] = set()
        unique_locations: List[Dict[str, Any]] = []

        for loc in all_locations:
            lid = str(loc.get("lid", ""))
            address_key = (
                f"{loc.get('address_1', '')}|"
                f"{loc.get('city', '')}|"
                f"{loc.get('region', '')}"
            ).lower()

            if lid and lid in seen_lids:
                continue
            if not lid and address_key in seen_addresses:
                continue

            if lid:
                seen_lids.add(lid)
            seen_addresses.add(address_key)
            unique_locations.append(loc)

        log.info("deduplication_complete",
                 total=len(all_locations),
                 unique=len(unique_locations))

        return unique_locations


def locations_to_rows(
    locations: List[Dict[str, Any]],
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema (A:Q)."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []

    for loc in locations:
        state = (loc.get("region") or "").upper().strip()[:2]
        if state not in VALID_STATES:
            continue

        zip_code = (loc.get("post_code") or "").strip()
        if zip_code:
            zip_match = re.search(r"\b(\d{5})\b", zip_code)
            zip_code = zip_match.group(1) if zip_match else ""

        phone = normalize_phone(loc.get("local_phone") or loc.get("phone") or "")

        # Build store URL from individual store page or city page
        store_url = loc.get("url") or ""
        if store_url and not store_url.startswith("http"):
            store_url = f"https://stores.hallmark.com{store_url}"

        rows.append([
            MERCHANT_NAME,
            str(merchant_id) if merchant_id else "TBD",
            (loc.get("location_name") or "").strip(),
            (loc.get("address_1") or "").strip(),
            (loc.get("address_2") or "").strip(),
            (loc.get("city") or "").strip(),
            state,
            zip_code,
            phone,
            "",  # hours
            store_url,
            str(loc.get("lat") or loc.get("latitude") or ""),
            str(loc.get("lng") or loc.get("longitude") or ""),
            "Pending",
            now,
            "",  # pushed_at
            "v2_hallmark_custom",
        ])

    return rows


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Scrape Hallmark store locations from sitemap + city pages"
    )
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    t0 = time.monotonic()

    # Scrape locations
    locations = asyncio.run(scrape_all_locations())
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 3))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Custom Sitemap Scraper")
    print(f"{'=' * 60}")
    print(f"  Locations scraped:  {len(locations)}")
    print(f"  Valid rows:         {len(rows)}")
    print(f"  Elapsed:            {round(elapsed, 3)}s")

    if args.dry_run:
        print(f"  (DRY RUN - nothing written)")
        for r in rows[:10]:
            print(f"    {r[2]:50s} {r[5]:20s} {r[6]:2s} {r[7]:5s}")
        if len(rows) > 10:
            print(f"    ... and {len(rows) - 10} more")
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
