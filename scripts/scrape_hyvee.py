#!/usr/bin/env python3
"""Custom scraper for Hy-Vee grocery stores.

Hy-Vee publishes a location sitemap at
https://www.hy-vee.com/sitemap-locations.xml listing ~300 store detail pages.
Each store page contains structured data (JSON-LD, microdata, or meta tags)
with address, phone, and coordinates.

Hy-Vee operates in 8 states: IA, IL, KS, MN, MO, NE, SD, WI.

Usage:
    python scripts/scrape_hyvee.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_hyvee.py \
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

MERCHANT_NAME = "Hy-Vee"
SITEMAP_URL = "https://www.hy-vee.com/sitemap-locations.xml"

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

# Hy-Vee operates in these 8 states
HYVEE_STATES = {"IA", "IL", "KS", "MN", "MO", "NE", "SD", "WI"}


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


def extract_sitemap_urls(xml_text: str) -> List[str]:
    """Extract store detail URLs from the sitemap XML.

    Looks for <loc> entries matching /stores/detail.aspx?s=...
    Also handles any /stores/ paths that look like individual store pages.
    """
    urls: List[str] = []
    loc_pattern = re.compile(r"<loc>\s*(https?://[^<]+)\s*</loc>", re.IGNORECASE)
    for match in loc_pattern.finditer(xml_text):
        url = match.group(1).strip()
        # Accept store detail pages (detail.aspx?s=...) and also
        # modern /stores/<slug> paths if the sitemap uses them
        if "/stores/detail.aspx" in url.lower() or re.search(r"/stores/[a-z0-9-]+/?$", url, re.IGNORECASE):
            urls.append(url)
    return urls


def parse_store_page(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract store location data from an individual Hy-Vee store page.

    Tries multiple extraction strategies in order:
    1. JSON-LD structured data
    2. Schema.org microdata attributes
    3. Meta tags (og:title, etc.)
    4. Regex fallback (h1, address patterns, tel: links, hidden inputs)
    """
    loc = _try_jsonld(html, url)
    if loc:
        return loc

    loc = _try_microdata(html, url)
    if loc:
        return loc

    loc = _try_meta_tags(html, url)
    if loc:
        return loc

    loc = _try_regex_fallback(html, url)
    if loc:
        return loc

    return None


def _try_jsonld(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract location from JSON-LD (application/ld+json) blocks."""
    jsonld_pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL,
    )
    for match in jsonld_pattern.finditer(html):
        try:
            data = json.loads(match.group(1))
            items = data if isinstance(data, list) else [data]
            for item in items:
                # Check top-level @type
                item_type = item.get("@type", "")
                if isinstance(item_type, list):
                    types = item_type
                else:
                    types = [item_type]

                target_types = {
                    "LocalBusiness", "Store", "GroceryStore",
                    "Supermarket", "FoodEstablishment",
                }
                if not any(t in target_types for t in types):
                    # Also check @graph entries
                    if "@graph" in item:
                        for graph_item in item["@graph"]:
                            gt = graph_item.get("@type", "")
                            gt_list = gt if isinstance(gt, list) else [gt]
                            if any(t in target_types for t in gt_list):
                                result = _extract_from_jsonld_item(graph_item, url)
                                if result:
                                    return result
                    continue

                result = _extract_from_jsonld_item(item, url)
                if result:
                    return result
        except (json.JSONDecodeError, ValueError, TypeError):
            continue
    return None


def _extract_from_jsonld_item(item: Dict[str, Any], url: str) -> Optional[Dict[str, Any]]:
    """Extract location fields from a single JSON-LD item."""
    addr = item.get("address", {})
    if isinstance(addr, str):
        return None
    geo = item.get("geo", {})

    street = addr.get("streetAddress", "")
    city = addr.get("addressLocality", "")
    state = addr.get("addressRegion", "")

    if not street or not city:
        return None

    lat = ""
    lng = ""
    if isinstance(geo, dict):
        lat = str(geo.get("latitude", ""))
        lng = str(geo.get("longitude", ""))

    return {
        "name": item.get("name", ""),
        "address": street,
        "city": city,
        "state": state,
        "zip": addr.get("postalCode", ""),
        "phone": item.get("telephone", ""),
        "latitude": lat,
        "longitude": lng,
        "store_url": url,
    }


def _try_microdata(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract location from schema.org microdata attributes (itemprop)."""
    loc: Dict[str, str] = {}

    microdata_fields = {
        "name": r'itemprop=["\']name["\'][^>]*>([^<]+)<',
        "streetAddress": r'itemprop=["\']streetAddress["\'][^>]*>([^<]+)<',
        "addressLocality": r'itemprop=["\']addressLocality["\'][^>]*>([^<]+)<',
        "addressRegion": r'itemprop=["\']addressRegion["\'][^>]*>([^<]+)<',
        "postalCode": r'itemprop=["\']postalCode["\'][^>]*>([^<]+)<',
        "telephone": r'itemprop=["\']telephone["\'][^>]*>([^<]+)<',
    }

    for field, pattern in microdata_fields.items():
        m = re.search(pattern, html, re.IGNORECASE)
        if m:
            loc[field] = m.group(1).strip()

    # Also try content= attribute variant
    for field in microdata_fields:
        if field not in loc:
            m = re.search(
                rf'itemprop=["\']{ field }["\'][^>]*content=["\']([^"\']+)["\']',
                html, re.IGNORECASE,
            )
            if m:
                loc[field] = m.group(1).strip()

    if not loc.get("streetAddress") or not loc.get("addressLocality"):
        return None

    # Try geo microdata
    lat = ""
    lng = ""
    lat_m = re.search(r'itemprop=["\']latitude["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    lng_m = re.search(r'itemprop=["\']longitude["\'][^>]*content=["\']([^"\']+)["\']', html, re.IGNORECASE)
    if lat_m:
        lat = lat_m.group(1).strip()
    if lng_m:
        lng = lng_m.group(1).strip()

    return {
        "name": loc.get("name", ""),
        "address": loc.get("streetAddress", ""),
        "city": loc.get("addressLocality", ""),
        "state": loc.get("addressRegion", ""),
        "zip": loc.get("postalCode", ""),
        "phone": loc.get("telephone", ""),
        "latitude": lat,
        "longitude": lng,
        "store_url": url,
    }


def _try_meta_tags(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Extract location from meta tags (og: and business: properties)."""
    loc: Dict[str, str] = {"store_url": url}

    # og:title for name
    title_m = re.search(
        r'<meta\s+(?:property|name)=["\']og:title["\']\s+content=["\']([^"\']*)["\']',
        html, re.IGNORECASE,
    )
    if title_m:
        loc["name"] = title_m.group(1).strip()

    # business:contact_data meta tags
    meta_map = {
        "business:contact_data:street_address": "address",
        "business:contact_data:locality": "city",
        "business:contact_data:region": "state",
        "business:contact_data:postal_code": "zip",
        "business:contact_data:phone_number": "phone",
    }
    for meta_name, field in meta_map.items():
        m = re.search(
            rf'<meta\s+(?:property|name)=["\']{ re.escape(meta_name) }["\']\s+content=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        if m:
            loc[field] = m.group(1).strip()

    # Geo from meta
    for meta_name, field in [
        ("place:location:latitude", "latitude"),
        ("place:location:longitude", "longitude"),
        ("geo.position", None),  # format: lat;lng
    ]:
        m = re.search(
            rf'<meta\s+(?:property|name)=["\']{ re.escape(meta_name) }["\']\s+content=["\']([^"\']*)["\']',
            html, re.IGNORECASE,
        )
        if m:
            if field:
                loc[field] = m.group(1).strip()
            else:
                # geo.position is "lat;lng"
                parts = m.group(1).split(";")
                if len(parts) == 2:
                    loc["latitude"] = parts[0].strip()
                    loc["longitude"] = parts[1].strip()

    if not loc.get("address") or not loc.get("city"):
        return None

    return {
        "name": loc.get("name", ""),
        "address": loc.get("address", ""),
        "city": loc.get("city", ""),
        "state": loc.get("state", ""),
        "zip": loc.get("zip", ""),
        "phone": loc.get("phone", ""),
        "latitude": loc.get("latitude", ""),
        "longitude": loc.get("longitude", ""),
        "store_url": url,
    }


def _try_regex_fallback(html: str, url: str) -> Optional[Dict[str, Any]]:
    """Last-resort regex extraction from visible HTML elements."""
    loc: Dict[str, str] = {"store_url": url}

    # Store name from <h1>
    h1_m = re.search(r"<h1[^>]*>([^<]+)</h1>", html, re.IGNORECASE)
    if h1_m:
        loc["name"] = h1_m.group(1).strip()
    else:
        title_m = re.search(r"<title>([^<]+)</title>", html, re.IGNORECASE)
        if title_m:
            loc["name"] = title_m.group(1).split("|")[0].split("-")[0].strip()

    # Phone from tel: links
    tel_m = re.search(r'href=["\']tel:([^"\']+)["\']', html, re.IGNORECASE)
    if tel_m:
        loc["phone"] = tel_m.group(1).strip()

    # Address pattern: look for common address structures
    # Try a block that has street, city, state ZIP on consecutive lines or in a container
    addr_pattern = re.compile(
        r'(\d+\s+[A-Za-z0-9\s.]+(?:St|Street|Ave|Avenue|Blvd|Boulevard|Rd|Road|Dr|Drive|Way|Ln|Lane|Ct|Court|Pkwy|Parkway|Hwy|Highway|Pl|Place|Cir|Circle)[.,]?)\s*'
        r'(?:<[^>]*>\s*)*'
        r'([A-Za-z\s]+),\s*'
        r'([A-Z]{2})\s+'
        r'(\d{5})',
        re.IGNORECASE,
    )
    addr_m = addr_pattern.search(html)
    if addr_m:
        loc["address"] = addr_m.group(1).strip().rstrip(",.")
        loc["city"] = addr_m.group(2).strip()
        loc["state"] = addr_m.group(3).upper()
        loc["zip"] = addr_m.group(4)

    # Lat/lng from hidden inputs (common in store locator pages)
    lat_m = re.search(
        r'<input[^>]+(?:id|name)=["\'][^"\']*lat(?:itude)?["\'][^>]*value=["\']([0-9.\-]+)["\']',
        html, re.IGNORECASE,
    )
    if not lat_m:
        lat_m = re.search(
            r'<input[^>]+value=["\']([0-9.\-]+)["\'][^>]*(?:id|name)=["\'][^"\']*lat(?:itude)?["\']',
            html, re.IGNORECASE,
        )
    lng_m = re.search(
        r'<input[^>]+(?:id|name)=["\'][^"\']*(?:lng|lon|longitude)["\'][^>]*value=["\']([0-9.\-]+)["\']',
        html, re.IGNORECASE,
    )
    if not lng_m:
        lng_m = re.search(
            r'<input[^>]+value=["\']([0-9.\-]+)["\'][^>]*(?:id|name)=["\'][^"\']*(?:lng|lon|longitude)["\']',
            html, re.IGNORECASE,
        )

    if lat_m:
        loc["latitude"] = lat_m.group(1)
    if lng_m:
        loc["longitude"] = lng_m.group(1)

    # Also try data attributes or JS variables for coords
    if "latitude" not in loc:
        js_lat = re.search(r'["\']?latitude["\']?\s*[:=]\s*["\']?([0-9.\-]+)', html)
        if js_lat:
            loc["latitude"] = js_lat.group(1)
    if "longitude" not in loc:
        js_lng = re.search(r'["\']?longitude["\']?\s*[:=]\s*["\']?([0-9.\-]+)', html)
        if js_lng:
            loc["longitude"] = js_lng.group(1)

    if not loc.get("address") or not loc.get("city"):
        return None

    return {
        "name": loc.get("name", ""),
        "address": loc.get("address", ""),
        "city": loc.get("city", ""),
        "state": loc.get("state", ""),
        "zip": loc.get("zip", ""),
        "phone": loc.get("phone", ""),
        "latitude": loc.get("latitude", ""),
        "longitude": loc.get("longitude", ""),
        "store_url": url,
    }


async def scrape_hyvee() -> List[Dict[str, Any]]:
    """Scrape all Hy-Vee store locations from sitemap + individual pages."""
    locations: List[Dict[str, Any]] = []
    seen_keys: set = set()

    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        # Step 1: Fetch the sitemap
        log.info("fetching_sitemap", url=SITEMAP_URL)
        resp = await client.get(SITEMAP_URL)
        if resp.status_code != 200:
            log.error("sitemap_fetch_failed", status=resp.status_code)
            return locations

        store_urls = extract_sitemap_urls(resp.text)
        log.info("store_urls_found", count=len(store_urls))

        if not store_urls:
            log.warning("no_store_urls_found")
            return locations

        # Step 2: Fetch each store page
        sem = asyncio.Semaphore(5)

        async def fetch_store(store_url: str) -> Optional[Dict[str, Any]]:
            async with sem:
                try:
                    r = await client.get(store_url)
                    if r.status_code == 200:
                        return parse_store_page(r.text, store_url)
                    else:
                        log.warning("store_page_status", url=store_url, status=r.status_code)
                except Exception as e:
                    log.warning("store_fetch_failed", url=store_url, error=str(e)[:100])
                return None

        tasks = [fetch_store(u) for u in store_urls]
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
            "v2_hyvee_custom",
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    locations = await scrape_hyvee()
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
    parser = argparse.ArgumentParser(description="Scrape Hy-Vee stores from sitemap")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
