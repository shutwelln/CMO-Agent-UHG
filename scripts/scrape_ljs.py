#!/usr/bin/env python3
"""Custom scraper for Long John Silver's via sitemap + __NUXT__ data.

ljsilvers.com has a sitemap with ~480 location URLs. Each location page embeds
structured data in a window.__NUXT__ payload (no JSON-LD). Fields are extracted
via regex from the raw HTML.

Usage:
    python scripts/scrape_ljs.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_ljs.py \
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

MERCHANT_NAME = "Long John Silver's"
SITEMAP_URL = "https://www.ljsilvers.com/sitemap.xml"

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


def extract_location_urls(sitemap_xml: str) -> List[str]:
    """Extract /locations/ URLs from the sitemap XML."""
    url_pattern = re.compile(r"<loc>(https?://www\.ljsilvers\.com/locations/[^<]+)</loc>")
    urls: List[str] = []
    for m in url_pattern.finditer(sitemap_xml):
        url = m.group(1).rstrip("/")
        # Filter to actual location pages (state/city/address pattern, at least 3 segments)
        path = url.replace("https://www.ljsilvers.com/locations", "").strip("/")
        segments = [s for s in path.split("/") if s]
        if len(segments) >= 3:
            urls.append(url)
    return urls


def format_phone(raw: str) -> str:
    """Format a 10-digit phone string as xxx-xxx-xxxx."""
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]}-{digits[3:6]}-{digits[6:]}"
    return raw


def parse_nuxt_location(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract location data from window.__NUXT__ payload via regex."""
    # Check that __NUXT__ data exists on the page
    if "window.__NUXT__" not in html and "__NUXT__" not in html:
        return None

    loc: Dict[str, Any] = {"store_url": url}

    # Extract fields from __NUXT__ data
    field_patterns = {
        "address": r'address:"([^"]*)"',
        "city": r'city:"([^"]*)"',
        "state": r'state:"([^"]*)"',
        "zip": r'zip:"([^"]*)"',
        "phone": r'phone:"([^"]*)"',
        "name": r'name:"([^"]*)"',
    }

    for field, pattern in field_patterns.items():
        m = re.search(pattern, html)
        if m:
            loc[field] = m.group(1)

    # lat/lng: take FIRST match only (second is default map center ~40.70/-74.01)
    lat_m = re.search(r"lat:([0-9.-]+)", html)
    lng_m = re.search(r"lng:(-?[0-9.]+)", html)
    if lat_m:
        loc["latitude"] = lat_m.group(1)
    if lng_m:
        loc["longitude"] = lng_m.group(1)

    # Format phone
    if loc.get("phone"):
        loc["phone"] = format_phone(loc["phone"])

    # Fallback name from <title> if not in __NUXT__
    if not loc.get("name"):
        title_m = re.search(r"<title>([^<]+)</title>", html)
        if title_m:
            loc["name"] = title_m.group(1).split("|")[0].split("-")[0].strip()

    # Must have at least address and city
    if loc.get("address") and loc.get("city"):
        return loc
    return None


async def scrape_ljs() -> List[Dict[str, Any]]:
    """Scrape all Long John Silver's locations from sitemap + __NUXT__ data."""
    locations: List[Dict[str, Any]] = []
    seen_keys: set = set()

    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        # Step 1: Fetch sitemap
        log.info("fetching_sitemap", url=SITEMAP_URL)
        resp = await client.get(SITEMAP_URL)
        if resp.status_code != 200:
            log.error("sitemap_fetch_failed", status=resp.status_code)
            return locations

        location_urls = extract_location_urls(resp.text)
        log.info("location_urls_found", count=len(location_urls))

        if not location_urls:
            log.warning("no_location_urls_found")
            return locations

        # Step 2: Fetch each location page
        sem = asyncio.Semaphore(5)

        async def fetch_location(url: str) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return parse_nuxt_location(r.text, url)
                except Exception as e:
                    log.warning("location_fetch_failed", url=url, error=str(e)[:100])
                return None

        tasks = [fetch_location(url) for url in location_urls]
        batch_size = 20
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
                await asyncio.sleep(0.5)

            log.info("batch_done", batch=i + len(batch), total=len(tasks),
                     locations_so_far=len(locations))

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
            "v2_ljs_custom",
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    locations = await scrape_ljs()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 1))

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
    parser = argparse.ArgumentParser(description="Scrape Long John Silver's from sitemap")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
