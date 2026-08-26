#!/usr/bin/env python3
"""Custom scraper for YMCA locations via sitemap.

ymca.org publishes a sitemap index at /sitemap.xml with sub-sitemaps containing
~2,706 location URLs. Each location page uses CSS-class-based HTML (Drupal) with
address spans, data-lat/data-lng attributes, and tel: links.

Usage:
    python scripts/scrape_ymca.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_ymca.py \
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
from typing import Any, Dict, List, Optional

import httpx
import structlog
from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.google_auth import get_google_credentials  # noqa: E402

log = structlog.get_logger()

MERCHANT_NAME = "YMCA"
SITEMAP_INDEX_URL = "https://ymca.org/sitemap.xml"

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
    """Extract sub-sitemap URLs from a sitemap index XML."""
    # Match <sitemap><loc>...</loc></sitemap> entries
    pattern = re.compile(r"<sitemap>\s*<loc>([^<]+)</loc>", re.DOTALL)
    return [m.group(1).strip() for m in pattern.finditer(xml_text)]


def parse_sitemap_urls(xml_text: str) -> List[str]:
    """Extract <url><loc>...</loc></url> entries from a sub-sitemap."""
    pattern = re.compile(r"<url>\s*<loc>([^<]+)</loc>", re.DOTALL)
    return [m.group(1).strip() for m in pattern.finditer(xml_text)]


def parse_ymca_location_page(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract location data from a YMCA location page using CSS-class-based HTML."""
    loc: Dict[str, Any] = {"store_url": url}

    # Name: <h1> tag
    h1_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
    if h1_match:
        loc["name"] = h1_match.group(1).strip()
    else:
        # Fallback: <title>
        title_match = re.search(r"<title>([^<]+)</title>", html)
        if title_match:
            loc["name"] = title_match.group(1).split("|")[0].strip()

    # Street: <span class="address-line1">...</span>
    street_match = re.search(
        r'<span\s+class="address-line1">([^<]+)</span>', html
    )
    if street_match:
        loc["address"] = street_match.group(1).strip()

    # City: <span class="locality">...</span>
    city_match = re.search(
        r'<span\s+class="locality">([^<]+)</span>', html
    )
    if city_match:
        loc["city"] = city_match.group(1).strip()

    # State: <span class="administrative-area">...</span>
    state_match = re.search(
        r'<span\s+class="administrative-area">([^<]+)</span>', html
    )
    if state_match:
        loc["state"] = state_match.group(1).strip()

    # Zip: <span class="postal-code">...</span>
    zip_match = re.search(
        r'<span\s+class="postal-code">([^<]+)</span>', html
    )
    if zip_match:
        loc["zip"] = zip_match.group(1).strip()

    # Latitude: data-lat="..."
    lat_match = re.search(r'data-lat="([^"]+)"', html)
    if lat_match:
        loc["latitude"] = lat_match.group(1).strip()

    # Longitude: data-lng="..."
    lng_match = re.search(r'data-lng="([^"]+)"', html)
    if lng_match:
        loc["longitude"] = lng_match.group(1).strip()

    # Phone: <a href="tel:+1-201-487-6600"> - strip +1- prefix, normalize
    phone_match = re.search(r'<a\s+href="tel:([^"]+)"', html)
    if phone_match:
        raw_phone = phone_match.group(1).strip()
        # Strip leading +1- or +1
        raw_phone = re.sub(r"^\+1-?", "", raw_phone)
        # Normalize: remove non-digit, then format as (XXX) XXX-XXXX
        digits = re.sub(r"\D", "", raw_phone)
        if len(digits) == 10:
            loc["phone"] = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        elif len(digits) == 11 and digits[0] == "1":
            digits = digits[1:]
            loc["phone"] = f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
        else:
            loc["phone"] = raw_phone

    # Require at minimum address + city to count as a valid location
    if loc.get("address") and loc.get("city"):
        return loc
    return None


async def scrape_ymca_locations() -> List[Dict[str, Any]]:
    """Scrape all YMCA locations via sitemap index -> sub-sitemaps -> location pages."""
    locations: List[Dict[str, Any]] = []
    seen_keys: set = set()

    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        # Step 1: Fetch sitemap index
        log.info("fetching_sitemap_index", url=SITEMAP_INDEX_URL)
        resp = await client.get(SITEMAP_INDEX_URL)
        if resp.status_code != 200:
            log.error("sitemap_index_failed", status=resp.status_code)
            return locations

        sub_sitemaps = parse_sitemap_index(resp.text)
        log.info("sub_sitemaps_found", count=len(sub_sitemaps))

        if not sub_sitemaps:
            log.warning("no_sub_sitemaps_found")
            return locations

        # Step 2: Fetch each sub-sitemap and collect /locations/ URLs
        all_location_urls: List[str] = []
        for sitemap_url in sub_sitemaps:
            log.info("fetching_sub_sitemap", url=sitemap_url)
            try:
                r = await client.get(sitemap_url)
                if r.status_code == 200:
                    urls = parse_sitemap_urls(r.text)
                    location_urls = [u for u in urls if "/locations/" in u]
                    all_location_urls.extend(location_urls)
                    log.info(
                        "sub_sitemap_parsed",
                        url=sitemap_url,
                        total_urls=len(urls),
                        location_urls=len(location_urls),
                    )
                else:
                    log.warning("sub_sitemap_failed", url=sitemap_url, status=r.status_code)
            except Exception as e:
                log.warning("sub_sitemap_error", url=sitemap_url, error=str(e)[:100])

        # Deduplicate URLs
        all_location_urls = sorted(set(all_location_urls))
        log.info("total_location_urls", count=len(all_location_urls))

        if not all_location_urls:
            log.warning("no_location_urls_found")
            return locations

        # Step 3: Fetch each location page
        sem = asyncio.Semaphore(8)

        async def fetch_location(url: str) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return parse_ymca_location_page(r.text, url)
                except Exception as e:
                    log.warning("location_fetch_failed", url=url, error=str(e)[:100])
                return None

        tasks = [fetch_location(url) for url in all_location_urls]
        batch_size = 50
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)
            for r in results:
                if isinstance(r, dict) and r.get("address") and r.get("city"):
                    # Dedup by address+city+state
                    key = (
                        r.get("address", "").lower().strip(),
                        r.get("city", "").lower().strip(),
                        r.get("state", "").upper().strip(),
                    )
                    if key not in seen_keys:
                        seen_keys.add(key)
                        locations.append(r)

            if i + batch_size < len(tasks):
                await asyncio.sleep(0.3)

            log.info(
                "batch_done",
                batch=i + len(batch),
                total=len(tasks),
                locations_so_far=len(locations),
            )

    return locations


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
            "v2_ymca_custom",
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    locations = await scrape_ymca_locations()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 1))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Sitemap Custom Scraper")
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
    parser = argparse.ArgumentParser(description="Scrape YMCA locations via sitemap")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
