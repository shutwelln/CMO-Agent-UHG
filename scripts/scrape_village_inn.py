#!/usr/bin/env python3
"""Custom scraper for Village Inn via state listing pages + JSON-LD.

Village Inn's locator at villageinn.com/locations is JS-rendered with no
structured data the generic cascade can find. However:
  1. State listing pages at /Locations/List?country=usa&state={state} return
     individual store slugs (e.g., avondale-az).
  2. Individual pages at /{slug} embed JSON-LD (@type: Restaurant) with full
     address, phone, and hours. Hidden inputs provide lat/lng coords.

Usage:
    python scripts/scrape_village_inn.py \
        --sheet-id "SHEET_ID" --dry-run

    python scripts/scrape_village_inn.py \
        --sheet-id "SHEET_ID"
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

MERCHANT_NAME = "Village Inn"
BASE_URL = "https://www.villageinn.com"
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
}

VALID_STATES = {
    "AL", "AK", "AZ", "AR", "CA", "CO", "CT", "DE", "FL", "GA",
    "HI", "ID", "IL", "IN", "IA", "KS", "KY", "LA", "ME", "MD",
    "MA", "MI", "MN", "MS", "MO", "MT", "NE", "NV", "NH", "NJ",
    "NM", "NY", "NC", "ND", "OH", "OK", "OR", "PA", "RI", "SC",
    "SD", "TN", "TX", "UT", "VT", "VA", "WA", "WV", "WI", "WY",
    "DC",
}

# US states with full names for querying the listing endpoint
US_STATE_NAMES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming",
]


def get_sheets_service() -> Any:
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH, service_account_path="", scopes=SCOPES,
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


async def discover_store_slugs(client: httpx.AsyncClient) -> List[str]:
    """Discover all store slugs by querying each state listing page."""
    all_slugs: set = set()
    sem = asyncio.Semaphore(5)

    async def fetch_state(state_name: str) -> List[str]:
        async with sem:
            url = f"{BASE_URL}/Locations/List?country=usa&state={state_name}"
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return []
                # Extract store slugs from links like villageinn.com/{slug}
                slugs = re.findall(
                    r'villageinn\.com/([a-z0-9][a-z0-9-]+[a-z0-9])',
                    resp.text,
                )
                # Filter out non-location pages
                skip = {
                    "menu", "locations", "aboutus", "careers", "catering",
                    "community", "contact", "gift", "gift-cards", "rewards",
                    "privacy", "terms", "franchise", "account", "data-request",
                    "providers", "accessibility", "signout",
                }
                return [s for s in slugs if s not in skip and not s.startswith("Locations")]
            except Exception:
                return []

    tasks = [fetch_state(state) for state in US_STATE_NAMES]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, list):
            all_slugs.update(r)

    return sorted(all_slugs)


def parse_store_page(html: str, slug: str) -> Optional[Dict[str, Any]]:
    """Parse a Village Inn individual store page for location data."""
    loc: Dict[str, Any] = {"store_url": f"{BASE_URL}/{slug}"}

    # JSON-LD (@type: Restaurant)
    jsonld_match = re.search(
        r'<script\s+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL,
    )
    if jsonld_match:
        try:
            data = json.loads(jsonld_match.group(1), strict=False)
            loc["name"] = (data.get("name") or "").strip()
            addr = data.get("address", {})
            loc["address"] = (addr.get("streetAddress") or "").strip()
            loc["city"] = (addr.get("addressLocality") or "").strip()
            loc["state"] = (addr.get("addressRegion") or "").strip()
            loc["zip"] = (addr.get("postalCode") or "").strip()

            # Phone from contactPoint
            cp = data.get("contactPoint", {})
            phone_val = cp.get("telephone", "")
            if isinstance(phone_val, list):
                phone_val = phone_val[0] if phone_val else ""
            loc["phone"] = phone_val.strip()

            loc["hours"] = (data.get("openingHours") or "").strip()
        except (json.JSONDecodeError, ValueError):
            pass

    # Lat/lng from hidden inputs
    lat_match = re.search(r'selectedStore[._]Latitude["\s]+(?:type="hidden"\s+)?value="([^"]+)"', html)
    lng_match = re.search(r'selectedStore[._]Longitude["\s]+(?:type="hidden"\s+)?value="([^"]+)"', html)
    if lat_match:
        loc["latitude"] = lat_match.group(1)
    if lng_match:
        loc["longitude"] = lng_match.group(1)

    # Fallback phone from tel: link
    if not loc.get("phone"):
        tel_match = re.search(r'tel:(\([0-9]{3}\)[0-9-]+)', html)
        if tel_match:
            loc["phone"] = tel_match.group(1)

    if loc.get("address") and loc.get("city"):
        return loc
    return None


async def scrape_village_inn() -> List[Dict[str, Any]]:
    """Scrape all Village Inn locations."""
    locations: List[Dict[str, Any]] = []
    seen: set = set()

    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        # Step 1: Discover all store slugs
        log.info("discovering_store_slugs")
        slugs = await discover_store_slugs(client)
        log.info("store_slugs_found", count=len(slugs))

        if not slugs:
            return locations

        # Step 2: Fetch each store page
        sem = asyncio.Semaphore(5)

        async def fetch_store(slug: str) -> Optional[Dict[str, Any]]:
            async with sem:
                url = f"{BASE_URL}/{slug}"
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        return parse_store_page(resp.text, slug)
                except Exception:
                    pass
                return None

        tasks = [fetch_store(slug) for slug in slugs]
        batch_size = 20
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)
            for r in results:
                if isinstance(r, dict) and r.get("address"):
                    key = (
                        r.get("address", "").lower(),
                        r.get("city", "").lower(),
                        r.get("state", "").upper(),
                    )
                    if key not in seen:
                        seen.add(key)
                        locations.append(r)
            if i + batch_size < len(tasks):
                await asyncio.sleep(0.5)
            log.info("batch_done", batch=i + len(batch), total=len(tasks),
                     locations=len(locations))

    return locations


def locations_to_rows(
    locations: List[Dict[str, Any]], merchant_id: Optional[int],
) -> List[List[str]]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []
    for loc in locations:
        state = (loc.get("state") or "").upper().strip()[:2]
        if state not in VALID_STATES:
            continue
        zip_code = (loc.get("zip") or "").strip()
        if zip_code:
            m = re.search(r"\b(\d{5})\b", zip_code)
            zip_code = m.group(1) if m else ""
        rows.append([
            MERCHANT_NAME,
            str(merchant_id) if merchant_id else "TBD",
            (loc.get("name") or "").strip(),
            (loc.get("address") or "").strip(),
            "",
            (loc.get("city") or "").strip(),
            state,
            zip_code,
            (loc.get("phone") or "").strip(),
            (loc.get("hours") or "").strip(),
            (loc.get("store_url") or "").strip(),
            str(loc.get("latitude") or ""),
            str(loc.get("longitude") or ""),
            "Pending",
            now,
            "",
            "v2_villageinn_custom",
        ])
    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()
    locations = await scrape_village_inn()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 1))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Custom Scraper")
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
            sheets_svc.spreadsheets().values().append(
                spreadsheetId=args.sheet_id,
                range=f"{SCRAPED_TAB}!A:Q",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": rows},
            ).execute()
        )
        written = resp.get("updates", {}).get("updatedRows", len(rows))
        print(f"  Written to sheet:   {written}")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape Village Inn locations")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
