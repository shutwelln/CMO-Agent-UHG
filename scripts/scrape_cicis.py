#!/usr/bin/env python3
"""Custom scraper for CiCi's Pizza via order.cicis.com.

The main site (www.cicis.com) is behind Cloudflare JS Challenge. The ordering
subdomain order.cicis.com runs on Netlify with NO bot protection and lists all
~276 locations in a single window.__NUXT__ blob on the /locations/ page.

The __NUXT__ data is a minified self-invoking JS function with variable
substitution. We evaluate it with a Node.js subprocess to get clean JSON,
then walk the structure to extract location objects.

Usage:
    python scripts/scrape_cicis.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84" --dry-run

    python scripts/scrape_cicis.py \
        --sheet-id "1KAoWnXNdz6Ay5TTLeDC2g-o1S_5bcYAH-QF_TLTAV84"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
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

MERCHANT_NAME = "CiCi's Pizza"
LOCATIONS_URL = "https://order.cicis.com/locations/"

OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
SCRAPED_TAB = "Scraped Locations"

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
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

# ── Location fields to look for when walking the __NUXT__ data ──────────────
LOCATION_REQUIRED_FIELDS = {"address", "city", "state", "zip"}
LOCATION_ALL_FIELDS = {
    "address", "city", "state", "zip", "phone", "lat", "lng",
    "latitude", "longitude", "name", "storeName", "store_name",
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


# ── __NUXT__ evaluation via Node.js ─────────────────────────────────────────

def evaluate_nuxt_with_node(js_code: str) -> Optional[Any]:
    """Evaluate the __NUXT__ JS expression using Node.js subprocess.

    The __NUXT__ blob is a self-invoking function like:
        (function(a,b,c,...){ return { data: [...] } }("val_a","val_b",...))
    Node evaluates the variable substitution and returns clean JSON.
    """
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            suffix=".js", mode="w", delete=False, encoding="utf-8",
        ) as f:
            # Evaluate the expression and print as JSON
            f.write(f"const d = {js_code};\nconsole.log(JSON.stringify(d));")
            tmp_path = f.name

        result = subprocess.run(
            ["node", tmp_path],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            log.warning(
                "node_eval_failed",
                returncode=result.returncode,
                stderr=result.stderr[:500] if result.stderr else "",
            )
            return None

        return json.loads(result.stdout)

    except FileNotFoundError:
        log.warning("node_not_found", hint="Node.js not installed, falling back to regex")
        return None
    except subprocess.TimeoutExpired:
        log.warning("node_timeout")
        return None
    except json.JSONDecodeError as e:
        log.warning("node_json_parse_failed", error=str(e)[:200])
        return None
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


def walk_for_locations(obj: Any, depth: int = 0) -> List[Dict[str, Any]]:
    """Recursively walk a JSON structure to find objects with location fields.

    Looks for dicts that have at least the required fields (address, city,
    state, zip). Returns all matching objects.
    """
    if depth > 20:
        return []

    results: List[Dict[str, Any]] = []

    if isinstance(obj, dict):
        # Check if this dict itself looks like a location
        keys = set(obj.keys())
        if LOCATION_REQUIRED_FIELDS.issubset(keys):
            results.append(obj)
        else:
            # Recurse into values
            for v in obj.values():
                results.extend(walk_for_locations(v, depth + 1))

    elif isinstance(obj, list):
        for item in obj:
            results.extend(walk_for_locations(item, depth + 1))

    return results


# ── Regex fallback ──────────────────────────────────────────────────────────

def extract_locations_regex(js_code: str) -> List[Dict[str, Any]]:
    """Fallback: extract location data from raw minified JS using regex.

    The minified JS has repeating patterns for each location with fields like:
        address:"1234 Main St",city:"Austin",state:"TX",zip:"78701"
    We find each address field and grab the surrounding fields.
    """
    locations: List[Dict[str, Any]] = []

    # Find all address occurrences and extract a window around each
    address_pattern = re.compile(r'address\s*:\s*"([^"]+)"')
    for m in address_pattern.finditer(js_code):
        # Grab a window of ~500 chars around this match to find sibling fields
        start = max(0, m.start() - 100)
        end = min(len(js_code), m.end() + 400)
        window = js_code[start:end]

        loc: Dict[str, Any] = {"address": m.group(1)}

        # Extract sibling fields from the window
        field_patterns = {
            "city": r'city\s*:\s*"([^"]+)"',
            "state": r'state\s*:\s*"([^"]+)"',
            "zip": r'zip\s*:\s*"([^"]+)"',
            "phone": r'phone\s*:\s*"([^"]+)"',
            "name": r'(?:name|storeName|store_name)\s*:\s*"([^"]+)"',
        }
        for field, pattern in field_patterns.items():
            fm = re.search(pattern, window)
            if fm:
                loc[field] = fm.group(1)

        # Lat/lng can be numeric (unquoted)
        lat_m = re.search(r'lat(?:itude)?\s*:\s*(-?\d+\.?\d*)', window)
        lng_m = re.search(r'lng|longitude\s*:\s*(-?\d+\.?\d*)', window)
        if lat_m:
            loc["lat"] = lat_m.group(1)
        if lng_m:
            loc["lng"] = lng_m.group(1)

        # Only keep if we have the required fields
        if loc.get("city") and loc.get("state"):
            locations.append(loc)

    return locations


# ── Main scrape logic ───────────────────────────────────────────────────────

async def scrape_cicis() -> List[Dict[str, Any]]:
    """Scrape all CiCi's Pizza locations from order.cicis.com."""
    locations: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=30, headers=HEADERS, follow_redirects=True) as client:
        log.info("fetching_locations_page", url=LOCATIONS_URL)
        resp = await client.get(LOCATIONS_URL)
        if resp.status_code != 200:
            log.error("locations_page_failed", status=resp.status_code)
            return locations

        html = resp.text
        log.info("page_fetched", length=len(html))

        # Extract the __NUXT__ blob
        nuxt_match = re.search(
            r'window\.__NUXT__\s*=\s*(.*?)\s*;?\s*</script>',
            html,
            re.DOTALL,
        )
        if not nuxt_match:
            log.error("nuxt_blob_not_found")
            return locations

        js_code = nuxt_match.group(1).strip()
        log.info("nuxt_blob_extracted", length=len(js_code))

        # Primary: evaluate with Node.js
        nuxt_data = evaluate_nuxt_with_node(js_code)
        if nuxt_data is not None:
            log.info("node_eval_success")
            locations = walk_for_locations(nuxt_data)
            log.info("locations_from_node", count=len(locations))
        else:
            # Fallback: regex extraction
            log.info("falling_back_to_regex")
            locations = extract_locations_regex(js_code)
            log.info("locations_from_regex", count=len(locations))

    return locations


def normalize_location(loc: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize field names across different data shapes."""
    return {
        "name": (
            loc.get("name")
            or loc.get("storeName")
            or loc.get("store_name")
            or ""
        ),
        "address": loc.get("address", ""),
        "city": loc.get("city", ""),
        "state": loc.get("state", ""),
        "zip": loc.get("zip", ""),
        "phone": loc.get("phone", ""),
        "latitude": str(loc.get("lat") or loc.get("latitude") or ""),
        "longitude": str(loc.get("lng") or loc.get("longitude") or ""),
        "store_url": loc.get("url") or loc.get("store_url") or "",
    }


def deduplicate_locations(
    locations: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Deduplicate locations by address+city+state."""
    seen: set = set()
    unique: List[Dict[str, Any]] = []
    for loc in locations:
        key = (
            loc.get("address", "").lower().strip(),
            loc.get("city", "").lower().strip(),
            loc.get("state", "").upper().strip(),
        )
        if key not in seen:
            seen.add(key)
            unique.append(loc)
    return unique


def locations_to_rows(
    locations: List[Dict[str, Any]],
    merchant_id: Optional[int],
) -> List[List[str]]:
    """Convert locations to sheet rows matching the Scraped Locations schema."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    rows: List[List[str]] = []

    for raw_loc in locations:
        loc = normalize_location(raw_loc)
        state = (loc.get("state") or "").upper().strip()[:2]
        if state not in VALID_STATES:
            continue

        zip_code = (loc.get("zip") or "").strip()
        if zip_code:
            zip_match = re.search(r"\b(\d{5})\b", zip_code)
            zip_code = zip_match.group(1) if zip_match else ""

        phone = (loc.get("phone") or "").strip()
        # Normalize phone: strip non-digits, then format
        phone_digits = re.sub(r"\D", "", phone)
        if len(phone_digits) == 10:
            phone = f"({phone_digits[:3]}) {phone_digits[3:6]}-{phone_digits[6:]}"
        elif len(phone_digits) == 11 and phone_digits[0] == "1":
            phone = f"({phone_digits[1:4]}) {phone_digits[4:7]}-{phone_digits[7:]}"

        # Build location name if not present
        name = (loc.get("name") or "").strip()
        if not name:
            city = (loc.get("city") or "").strip()
            name = f"CiCi's Pizza - {city}" if city else "CiCi's Pizza"

        rows.append([
            MERCHANT_NAME,                              # A: merchant_name
            str(merchant_id) if merchant_id else "TBD", # B: merchant_id
            name,                                       # C: location_name
            (loc.get("address") or "").strip(),          # D: address
            "",                                          # E: address2
            (loc.get("city") or "").strip(),              # F: city
            state,                                       # G: state
            zip_code,                                    # H: zip
            phone,                                       # I: phone
            "",                                          # J: hours
            (loc.get("store_url") or "").strip(),         # K: store_url
            str(loc.get("latitude") or ""),               # L: latitude
            str(loc.get("longitude") or ""),              # M: longitude
            "Pending",                                   # N: status
            now,                                         # O: scraped_at
            "",                                          # P: pushed_at
            "v2_cicis_custom",                           # Q: fetch_method
        ])

    return rows


async def async_main(args: argparse.Namespace) -> None:
    t0 = time.monotonic()

    # Scrape
    raw_locations = await scrape_cicis()
    elapsed = time.monotonic() - t0

    log.info("scrape_done", raw_locations=len(raw_locations), elapsed_s=round(elapsed, 1))

    if not raw_locations:
        print(f"\nNo locations found for {MERCHANT_NAME}")
        return

    # Normalize and deduplicate
    normalized = [normalize_location(loc) for loc in raw_locations]
    locations = deduplicate_locations(normalized)

    log.info("dedup_done", before=len(raw_locations), after=len(locations))

    # Build rows
    merchant_id = lookup_merchant_id(MERCHANT_NAME)
    rows = locations_to_rows(locations, merchant_id)

    print(f"\n{'=' * 60}")
    print(f"  {MERCHANT_NAME} - order.cicis.com Custom Scraper")
    print(f"{'=' * 60}")
    print(f"  Raw locations:      {len(raw_locations)}")
    print(f"  After dedup:        {len(locations)}")
    print(f"  Valid rows:         {len(rows)}")
    print(f"  Elapsed:            {round(elapsed, 1)}s")

    if args.dry_run:
        print(f"  (DRY RUN - nothing written)")
        for r in rows[:10]:
            print(f"    {r[2]:40s} {r[5]:20s} {r[6]:2s} {r[7]:5s}")
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Scrape CiCi's Pizza from order.cicis.com")
    parser.add_argument("--sheet-id", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    asyncio.run(async_main(args))


if __name__ == "__main__":
    main()
