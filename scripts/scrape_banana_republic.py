#!/usr/bin/env python3
"""Custom scraper for Banana Republic locations via sitemap.

bananarepublic.gap.com publishes a stores sitemap at /stores/sitemap.xml with ~430
individual store URLs following the pattern:
    https://bananarepublic.gap.com/stores/{state}/{city}/{slug}.html

Each location page has JSON-LD structured data (@type: ClothingStore) BUT the JSON-LD
uses HQ address (unreliable). Parse HTML instead for:
    - Store name
    - Street address, city, state, zip
    - Phone number
    - Coordinates

There are also state-level pages (/stores/al/) and city-level pages (/stores/al/hoover/).
We filter to individual .html store pages only.

Usage:
    python scripts/scrape_banana_republic.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_banana_republic.py \
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

MERCHANT_NAME = "Banana Republic"
SITEMAP_URL = "https://bananarepublic.gap.com/stores/sitemap.xml"

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

# URL pattern: /stores/{state}/{city}/{slug}.html
# Exclude state-level (/stores/al/) and city-level (/stores/al/hoover/) pages
LOCATION_URL_RE = re.compile(
    r"^https://bananarepublic\.gap\.com/stores/[a-z]{2}/[^/]+/.+\.html$"
)


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
    """Filter sitemap URLs to only individual store .html pages."""
    location_urls: List[str] = []
    for url in urls:
        # Must end with .html and match the 3-segment pattern: /stores/{state}/{city}/{slug}.html
        if not LOCATION_URL_RE.match(url):
            continue
        location_urls.append(url)
    return location_urls


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


def parse_banana_republic_city_page(html: str, page_url: str) -> List[Dict[str, Any]]:
    """Extract all store locations from a Banana Republic city page.

    City pages list multiple stores as plain-text blocks:
        <strong>Store Name</strong>
        123 Street Address
        City, ST 12345
        (xxx) xxx-xxxx
    """
    locations: List[Dict[str, Any]] = []

    # Pattern: <strong>STORE NAME</strong> followed by address lines
    # Each store block ends at the next <strong> or end of section
    blocks = re.split(r'<strong>', html)

    for block in blocks[1:]:  # skip first (before any <strong>)
        # Extract store name
        name_match = re.match(r'([^<]+)</strong>', block)
        if not name_match:
            continue
        name = name_match.group(1).strip()

        # Skip navigation/non-store entries
        if len(name) < 3 or name.upper() in ("STORE", "STORES", "NEARBY"):
            continue

        # Get the text after </strong> up to the next major HTML tag
        after_name = block[name_match.end():]
        # Strip HTML tags and get plain text lines
        text = re.sub(r'<[^>]+>', '\n', after_name)
        lines = [ln.strip() for ln in text.split('\n') if ln.strip()]

        if not lines:
            continue

        loc: Dict[str, Any] = {"name": name, "store_url": page_url}

        # First non-empty line is usually the street address
        loc["address"] = lines[0]

        # Look for "City, ST ZIP" pattern in remaining lines
        for line in lines[1:6]:
            city_state_match = re.match(
                r'^([A-Za-z\s.]+),\s*([A-Z]{2})\s+(\d{5})',
                line,
            )
            if city_state_match:
                loc["city"] = city_state_match.group(1).strip()
                loc["state"] = city_state_match.group(2).strip()
                loc["zip"] = city_state_match.group(3).strip()
                break

        # Look for phone number
        for line in lines[1:8]:
            phone_match = re.search(r'\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}', line)
            if phone_match:
                loc["phone"] = normalize_phone(phone_match.group(0))
                break

        # Also check for tel: links in the raw block
        if not loc.get("phone"):
            tel_match = re.search(r'href="tel:([^"]+)"', block)
            if tel_match:
                loc["phone"] = normalize_phone(tel_match.group(1))

        # If we have address + city, it's valid
        if loc.get("address") and loc.get("city"):
            locations.append(loc)

    return locations


async def scrape_banana_republic_locations() -> List[Dict[str, Any]]:
    """Scrape all Banana Republic locations via sitemap -> city pages."""
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

        # Step 2: Get city-level pages (/stores/{state}/{city}/) instead of .html
        # Individual .html pages redirect to city pages anyway
        city_url_re = re.compile(
            r"^https://bananarepublic\.gap\.com/stores/[a-z]{2}/[^/]+/$"
        )
        city_urls = sorted(set(u for u in all_urls if city_url_re.match(u)))
        # Also include .html pages - they may contain individual store data
        html_urls = sorted(set(u for u in all_urls if LOCATION_URL_RE.match(u)))

        all_page_urls = sorted(set(city_urls + html_urls))
        log.info("page_urls", city=len(city_urls), html=len(html_urls), total=len(all_page_urls))

        if not all_page_urls:
            log.warning("no_page_urls_found")
            return locations

        # Step 3: Fetch each page and parse for stores
        sem = asyncio.Semaphore(8)

        async def fetch_page(url: str) -> List[Dict[str, Any]]:
            async with sem:
                try:
                    r = await client.get(url)
                    if r.status_code == 200:
                        return parse_banana_republic_city_page(r.text, url)
                    else:
                        log.warning("page_http_error", url=url, status=r.status_code)
                except Exception as e:
                    log.warning("page_fetch_failed", url=url, error=str(e)[:100])
                return []

        tasks = [fetch_page(url) for url in all_page_urls]
        batch_size = 50
        for i in range(0, len(tasks), batch_size):
            batch = tasks[i : i + batch_size]
            results = await asyncio.gather(*batch, return_exceptions=True)
            for r in results:
                if isinstance(r, list):
                    for store in r:
                        if store.get("address") and store.get("city"):
                            key = (
                                store.get("address", "").lower().strip(),
                                store.get("city", "").lower().strip(),
                                store.get("state", "").upper().strip(),
                            )
                            if key not in seen_keys:
                                seen_keys.add(key)
                                locations.append(store)

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
            "v2_banana_republic_custom",
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    locations = await scrape_banana_republic_locations()
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
    parser = argparse.ArgumentParser(description="Scrape Banana Republic locations via sitemap")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
