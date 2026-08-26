#!/usr/bin/env python3
"""Custom scraper for Applebee's locations via sitemap.

restaurants.applebees.com publishes a sitemap at /sitemap.xml with ~1,500
individual restaurant URLs following the pattern:
    https://restaurants.applebees.com/en-us/{state}/{city}/{address-code}

Each location page embeds JSON-LD structured data (@type: Restaurant) with
address, phone, geo coordinates, and hours.

Usage:
    python scripts/scrape_applebees.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_applebees.py \
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

MERCHANT_NAME = "Applebee's"
SITEMAP_URL = "https://restaurants.applebees.com/sitemap.xml"

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

# URL pattern: /en-us/{state}/{city}/{address-code}
# Exclude sub-pages like /burgers, /careers, /catering, /delivery, /happy-hour, /specials, /takeout
LOCATION_URL_RE = re.compile(
    r"^https://restaurants\.applebees\.com/en-us/[a-z]{2}/[^/]+/[^/]+$"
)

# Known sub-page suffixes to exclude (in case the regex alone isn't enough)
EXCLUDED_SUFFIXES = {
    "burgers", "careers", "catering", "delivery", "happy-hour",
    "specials", "takeout", "menu", "reviews", "order",
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


def parse_sitemap_urls(xml_text: str) -> List[str]:
    """Extract <url><loc>...</loc></url> entries from sitemap XML."""
    pattern = re.compile(r"<url>\s*<loc>([^<]+)</loc>", re.DOTALL)
    return [m.group(1).strip() for m in pattern.finditer(xml_text)]


def filter_location_urls(urls: List[str]) -> List[str]:
    """Filter sitemap URLs to only individual restaurant location pages."""
    location_urls: List[str] = []
    for url in urls:
        # Must match the 4-segment pattern: /en-us/{state}/{city}/{address-code}
        if not LOCATION_URL_RE.match(url):
            continue
        # Double-check: exclude known sub-page suffixes
        last_segment = url.rstrip("/").rsplit("/", 1)[-1].lower()
        if last_segment in EXCLUDED_SUFFIXES:
            continue
        location_urls.append(url)
    return location_urls


def parse_jsonld(html: str) -> Optional[Dict[str, Any]]:
    """Extract JSON-LD @type Restaurant data from HTML."""
    # Find all JSON-LD script blocks
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

        # Handle single object or array
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and item.get("@type") == "Restaurant":
                    return item
        elif isinstance(data, dict):
            if data.get("@type") == "Restaurant":
                return data
    return None


def normalize_phone(raw: str) -> str:
    """Normalize a phone string to (XXX) XXX-XXXX format."""
    raw = re.sub(r"^\+1-?", "", raw.strip())
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    elif len(digits) == 11 and digits[0] == "1":
        digits = digits[1:]
        return f"({digits[:3]}) {digits[3:6]}-{digits[6:]}"
    return raw.strip()


def parse_applebees_location_page(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract location data from an Applebee's restaurant page.

    Primary: JSON-LD structured data (@type: Restaurant)
    Fallback: HTML regex parsing
    """
    loc: Dict[str, Any] = {"store_url": url}

    # --- Try JSON-LD first ---
    jsonld = parse_jsonld(html)
    if jsonld:
        loc["name"] = (jsonld.get("name") or "").strip()

        addr = jsonld.get("address") or {}
        if isinstance(addr, dict):
            loc["address"] = (addr.get("streetAddress") or "").strip()
            loc["city"] = (addr.get("addressLocality") or "").strip()
            loc["state"] = (addr.get("addressRegion") or "").strip()
            loc["zip"] = (addr.get("postalCode") or "").strip()
            # Phone is nested under address in Applebee's JSON-LD
            phone_raw = (addr.get("telephone") or "").strip()
            if phone_raw:
                loc["phone"] = normalize_phone(phone_raw)

        geo = jsonld.get("geo") or {}
        if isinstance(geo, dict):
            lat = geo.get("latitude")
            lon = geo.get("longitude")
            if lat:
                loc["latitude"] = str(lat).strip()
            if lon:
                loc["longitude"] = str(lon).strip()

        # If phone wasn't in address, check top-level
        if not loc.get("phone"):
            phone_raw = (jsonld.get("telephone") or "").strip()
            if phone_raw:
                loc["phone"] = normalize_phone(phone_raw)

        # Require at minimum address + city
        if loc.get("address") and loc.get("city"):
            return loc

    # --- Fallback: HTML parsing ---

    # Address line from the Google Maps link text
    maps_match = re.search(
        r'<a[^>]*href="https://www\.google\.com/maps[^"]*"[^>]*>([^<]+)</a>',
        html,
    )
    if maps_match:
        full_addr = maps_match.group(1).strip()
        # Typical format: "1331 Hwy. 72 East, Athens, AL 35611"
        parts = [p.strip() for p in full_addr.split(",")]
        if len(parts) >= 3:
            loc["address"] = parts[0]
            loc["city"] = parts[1]
            # Last part: "AL 35611"
            state_zip = parts[-1].strip().split()
            if len(state_zip) >= 1:
                loc["state"] = state_zip[0]
            if len(state_zip) >= 2:
                loc["zip"] = state_zip[1]

    # Phone from tel: link
    phone_match = re.search(r'<a\s+href="tel:([^"]+)"', html)
    if phone_match and not loc.get("phone"):
        loc["phone"] = normalize_phone(phone_match.group(1))

    # Name from <title> or <h1>
    if not loc.get("name"):
        h1_match = re.search(r"<h1[^>]*>([^<]+)</h1>", html)
        if h1_match:
            loc["name"] = h1_match.group(1).strip()
        else:
            title_match = re.search(r"<title>([^<]+)</title>", html)
            if title_match:
                loc["name"] = title_match.group(1).split("|")[0].strip()

    # Latitude/Longitude from data attributes or meta tags
    if not loc.get("latitude"):
        lat_match = re.search(r'data-lat(?:itude)?="([^"]+)"', html)
        if lat_match:
            loc["latitude"] = lat_match.group(1).strip()
    if not loc.get("longitude"):
        lng_match = re.search(r'data-l(?:ng|on|ongitude)="([^"]+)"', html)
        if lng_match:
            loc["longitude"] = lng_match.group(1).strip()

    # Require at minimum address + city
    if loc.get("address") and loc.get("city"):
        return loc
    return None


async def scrape_applebees_locations() -> List[Dict[str, Any]]:
    """Scrape all Applebee's locations via sitemap -> location pages."""
    locations: List[Dict[str, Any]] = []
    seen_keys: set = set()

    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        # Step 1: Fetch sitemap
        log.info("fetching_sitemap", url=SITEMAP_URL)
        resp = await client.get(SITEMAP_URL)
        if resp.status_code != 200:
            log.error("sitemap_failed", status=resp.status_code)
            return locations

        all_urls = parse_sitemap_urls(resp.text)
        log.info("sitemap_urls_found", count=len(all_urls))

        # Step 2: Filter to individual restaurant location pages only
        all_location_urls = filter_location_urls(all_urls)
        all_location_urls = sorted(set(all_location_urls))
        log.info("location_urls_filtered", count=len(all_location_urls))

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
                        return parse_applebees_location_page(r.text, url)
                    else:
                        log.warning("location_http_error", url=url, status=r.status_code)
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
            "v2_applebees_custom",
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    locations = await scrape_applebees_locations()
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
    parser = argparse.ArgumentParser(description="Scrape Applebee's locations via sitemap")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
