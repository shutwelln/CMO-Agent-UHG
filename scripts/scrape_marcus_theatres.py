#!/usr/bin/env python3
"""Custom scraper for Marcus Theatres via Fandango.

marcustheatres.com is behind Incapsula + Distil bot protection, so the generic
v2 cascade returns 0. Fandango lists all Marcus + Movie Tavern locations with
structured data (JSON-LD) on individual theatre pages.

Usage:
    python scripts/scrape_marcus_theatres.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_marcus_theatres.py \
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

MERCHANT_NAME = "Marcus Theatres"
FANDANGO_LIST_URL = "https://www.fandango.com/movie-theaters/marcus-theatres"
FANDANGO_BASE = "https://www.fandango.com"

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


def extract_theatre_links(html: str) -> List[str]:
    """Extract individual theatre page URLs from Fandango's Marcus Theatres list.

    Fandango uses links like /{slug}-{id}/theater-page, e.g.:
        /marcus-cedar-rapids-cinema-aatlq/theater-page
        /movie-tavern-little-rock-aaxfp/theater-page
    """
    pattern = re.compile(
        r'href="(/(marcus-[^"]+|movie-tavern-[^"]+)/theater-page)"',
        re.IGNORECASE,
    )
    links = set()
    for m in pattern.finditer(html):
        links.add(m.group(1))
    return sorted(links)


def parse_fandango_theatre_page(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract location data from an individual Fandango theatre page.

    Fandango embeds JSON-LD with MovieTheater schema on each page.
    """
    # Try JSON-LD first
    jsonld_pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL,
    )
    for match in jsonld_pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("@type") in ("MovieTheater", "LocalBusiness", "Place"):
                    addr = item.get("address", {})
                    geo = item.get("geo", {})
                    return {
                        "name": item.get("name", ""),
                        "address": addr.get("streetAddress", ""),
                        "city": addr.get("addressLocality", ""),
                        "state": addr.get("addressRegion", ""),
                        "zip": addr.get("postalCode", ""),
                        "phone": item.get("telephone", ""),
                        "latitude": str(geo.get("latitude", "")),
                        "longitude": str(geo.get("longitude", "")),
                        "store_url": url,
                    }
        except (json.JSONDecodeError, ValueError):
            continue

    # Fallback: extract from meta tags and visible content
    loc: Dict[str, Any] = {"store_url": url}

    # Title for name
    title_match = re.search(r"<title>([^<]+)</title>", html)
    if title_match:
        loc["name"] = title_match.group(1).split("|")[0].strip()

    # Address from og:street-address or visible elements
    for meta_name, field in [
        ("business:contact_data:street_address", "address"),
        ("business:contact_data:locality", "city"),
        ("business:contact_data:region", "state"),
        ("business:contact_data:postal_code", "zip"),
        ("business:contact_data:phone_number", "phone"),
    ]:
        m = re.search(
            rf'<meta\s+(?:property|name)="{meta_name}"\s+content="([^"]*)"',
            html, re.IGNORECASE,
        )
        if m:
            loc[field] = m.group(1).strip()

    # Geo coords
    for meta_name, field in [
        ("place:location:latitude", "latitude"),
        ("place:location:longitude", "longitude"),
    ]:
        m = re.search(
            rf'<meta\s+(?:property|name)="{meta_name}"\s+content="([^"]*)"',
            html, re.IGNORECASE,
        )
        if m:
            loc[field] = m.group(1).strip()

    if loc.get("address") and loc.get("city"):
        return loc
    return None


async def scrape_marcus_theatres() -> List[Dict[str, Any]]:
    """Scrape all Marcus Theatres locations from Fandango."""
    locations: List[Dict[str, Any]] = []
    seen_keys: set = set()

    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        # Step 1: Get the list page
        log.info("fetching_list_page", url=FANDANGO_LIST_URL)
        resp = await client.get(FANDANGO_LIST_URL)
        if resp.status_code != 200:
            log.error("list_page_failed", status=resp.status_code)
            return locations

        theatre_links = extract_theatre_links(resp.text)
        log.info("theatre_links_found", count=len(theatre_links))

        if not theatre_links:
            log.warning("no_theatre_links_found")
            return locations

        # Step 2: Fetch each theatre page
        sem = asyncio.Semaphore(5)

        async def fetch_theatre(path: str) -> Optional[Dict[str, Any]]:
            async with sem:
                url = f"{FANDANGO_BASE}{path}"
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return parse_fandango_theatre_page(r.text, url)
                except Exception as e:
                    log.warning("theatre_fetch_failed", url=url, error=str(e)[:100])
                return None

        tasks = [fetch_theatre(link) for link in theatre_links]
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
            "v2_fandango_custom",
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    locations = await scrape_marcus_theatres()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", locations=len(locations), elapsed_s=round(elapsed, 1))

    if not locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - Fandango Custom Scraper")
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
    parser = argparse.ArgumentParser(description="Scrape Marcus Theatres from Fandango")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
