#!/usr/bin/env python3
"""Generate Saverwell state-level hub page content and upsert to Supabase.

Builds 51 state pages (50 states + DC) that serve as parent hubs linking
down to DMA metro-area sub-pages. Captures queries like "senior discounts
in [State]", "[State] senior savings programs".

Re-runnable: only states without a row in state_page_content get processed
(unless --force-regen is passed).

Usage:
    python scripts/generate_state_page_content.py              # full run
    python scripts/generate_state_page_content.py --dry-run    # generate + validate, skip upsert
    python scripts/generate_state_page_content.py --limit 3    # process only first N states
    python scripts/generate_state_page_content.py --state TX   # single state
    python scripts/generate_state_page_content.py --force-regen # overwrite existing rows
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import httpx

try:
    import anthropic
except ImportError:
    print("Run: pip install anthropic httpx")
    sys.exit(1)

import structlog

# -- Project imports -----------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402

logger = structlog.get_logger()

# -- Paths ---------------------------------------------------------------------
BRAND_VOICE_PATH = _PROJECT_ROOT / "data" / "brand_voices" / "saverwell.txt"
DRAFTS_DIR = _PROJECT_ROOT / "data" / "saverwell" / "state_page_drafts"

# -- LLM settings (mirror DMA script) -----------------------------------------
GENERATION_MODEL = "claude-haiku-4-5-20251001"
GENERATION_TEMPERATURE = 0.4
GENERATION_MAX_TOKENS = 4096
MAX_RETRIES = 2
INTER_STATE_PAUSE = 1.0  # seconds between states

# -- Cross-link inventory (shared with DMA script) ----------------------------
UNIVERSAL_PROTECTION_SLUGS = [
    "5-common-scams-seniors-should-know",
    "how-to-freeze-your-credit",
    "protecting-your-social-security-number",
    "phishing-scams-what-retirees-need-to-know",
    "gift-card-scams",
    "password-safety-guide",
    "how-to-spot-fake-websites",
    "what-to-do-if-you-suspect-youve-been-scammed",
    "safe-online-shopping-tips",
    "smartphone-security-for-seniors",
]

UNIVERSAL_GUIDE_SLUGS = [
    "medicare-explained-simple-guide",
    "save-money-medicare-premiums",
]

# -- State-to-region mapping ---------------------------------------------------
STATE_REGIONS = {
    "AL": "Southeast", "AK": "Alaska", "AZ": "Southwest", "AR": "South",
    "CA": "West Coast", "CO": "Mountain West", "CT": "New England",
    "DE": "Mid-Atlantic", "FL": "Southeast", "GA": "Southeast",
    "HI": "Hawaii", "ID": "Pacific Northwest", "IL": "Midwest",
    "IN": "Midwest", "IA": "Midwest", "KS": "Great Plains",
    "KY": "South", "LA": "South", "ME": "New England", "MD": "Mid-Atlantic",
    "MA": "New England", "MI": "Midwest", "MN": "Midwest",
    "MS": "South", "MO": "Midwest", "MT": "Mountain West",
    "NE": "Great Plains", "NV": "Southwest", "NH": "New England",
    "NJ": "Mid-Atlantic", "NM": "Southwest", "NY": "Mid-Atlantic",
    "NC": "Southeast", "ND": "Great Plains", "OH": "Midwest",
    "OK": "South", "OR": "Pacific Northwest", "PA": "Mid-Atlantic",
    "RI": "New England", "SC": "Southeast", "SD": "Great Plains",
    "TN": "South", "TX": "South", "UT": "Mountain West",
    "VT": "New England", "VA": "Mid-Atlantic", "WA": "Pacific Northwest",
    "WV": "South", "WI": "Midwest", "WY": "Mountain West", "DC": "Mid-Atlantic",
}

# -- State names ---------------------------------------------------------------
STATE_NAMES: Dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut",
    "DE": "Delaware", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois",
    "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota",
    "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire",
    "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio",
    "OK": "Oklahoma", "OR": "Oregon", "PA": "Pennsylvania",
    "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming",
    "DC": "District of Columbia",
}

# -- State slugs ---------------------------------------------------------------
STATE_SLUGS: Dict[str, str] = {
    "AL": "alabama", "AK": "alaska", "AZ": "arizona", "AR": "arkansas",
    "CA": "california", "CO": "colorado", "CT": "connecticut",
    "DE": "delaware", "FL": "florida", "GA": "georgia",
    "HI": "hawaii", "ID": "idaho", "IL": "illinois",
    "IN": "indiana", "IA": "iowa", "KS": "kansas",
    "KY": "kentucky", "LA": "louisiana", "ME": "maine", "MD": "maryland",
    "MA": "massachusetts", "MI": "michigan", "MN": "minnesota",
    "MS": "mississippi", "MO": "missouri", "MT": "montana",
    "NE": "nebraska", "NV": "nevada", "NH": "new-hampshire",
    "NJ": "new-jersey", "NM": "new-mexico", "NY": "new-york",
    "NC": "north-carolina", "ND": "north-dakota", "OH": "ohio",
    "OK": "oklahoma", "OR": "oregon", "PA": "pennsylvania",
    "RI": "rhode-island", "SC": "south-carolina", "SD": "south-dakota",
    "TN": "tennessee", "TX": "texas", "UT": "utah",
    "VT": "vermont", "VA": "virginia", "WA": "washington",
    "WV": "west-virginia", "WI": "wisconsin", "WY": "wyoming",
    "DC": "district-of-columbia",
}

# -- State Attorney General offices -------------------------------------------
STATE_AG_OFFICES: Dict[str, Dict[str, str]] = {
    "AL": {"name": "Alabama Attorney General Consumer Protection Division", "phone": "1-800-392-5658"},
    "AK": {"name": "Alaska Attorney General Consumer Protection Unit", "phone": "1-907-269-5100"},
    "AZ": {"name": "Arizona Attorney General Consumer Protection Division", "phone": "1-602-542-5763"},
    "AR": {"name": "Arkansas Attorney General Consumer Protection Division", "phone": "1-800-482-8982"},
    "CA": {"name": "California Department of Justice Consumer Protection", "phone": "1-800-952-5225"},
    "CO": {"name": "Colorado Attorney General Consumer Protection Section", "phone": "1-800-222-4444"},
    "CT": {"name": "Connecticut Attorney General Consumer Protection", "phone": "1-860-808-5318"},
    "DE": {"name": "Delaware Department of Justice Consumer Protection Unit", "phone": "1-800-220-5424"},
    "FL": {"name": "Florida Attorney General Consumer Protection Division", "phone": "1-866-966-7226"},
    "GA": {"name": "Georgia Attorney General Consumer Protection Division", "phone": "1-404-651-8600"},
    "HI": {"name": "Hawaii Office of Consumer Protection", "phone": "1-808-586-2630"},
    "ID": {"name": "Idaho Attorney General Consumer Protection Division", "phone": "1-800-432-3545"},
    "IL": {"name": "Illinois Attorney General Consumer Protection Division", "phone": "1-800-243-0618"},
    "IN": {"name": "Indiana Attorney General Consumer Protection Division", "phone": "1-800-382-5516"},
    "IA": {"name": "Iowa Attorney General Consumer Protection Division", "phone": "1-515-281-5926"},
    "KS": {"name": "Kansas Attorney General Consumer Protection Division", "phone": "1-800-432-2310"},
    "KY": {"name": "Kentucky Attorney General Consumer Protection Division", "phone": "1-888-432-9257"},
    "LA": {"name": "Louisiana Attorney General Consumer Protection Section", "phone": "1-800-351-4889"},
    "ME": {"name": "Maine Attorney General Consumer Protection Division", "phone": "1-207-626-8849"},
    "MD": {"name": "Maryland Attorney General Consumer Protection Division", "phone": "1-410-528-8662"},
    "MA": {"name": "Massachusetts Attorney General Consumer Protection Division", "phone": "1-617-727-8400"},
    "MI": {"name": "Michigan Attorney General Consumer Protection Division", "phone": "1-877-765-8388"},
    "MN": {"name": "Minnesota Attorney General Consumer Protection Division", "phone": "1-651-296-3353"},
    "MS": {"name": "Mississippi Attorney General Consumer Protection Division", "phone": "1-601-359-4230"},
    "MO": {"name": "Missouri Attorney General Consumer Protection Division", "phone": "1-800-392-8222"},
    "MT": {"name": "Montana Attorney General Consumer Protection Office", "phone": "1-406-444-4500"},
    "NE": {"name": "Nebraska Attorney General Consumer Protection Division", "phone": "1-800-727-6432"},
    "NV": {"name": "Nevada Attorney General Consumer Protection Bureau", "phone": "1-702-486-3132"},
    "NH": {"name": "New Hampshire Attorney General Consumer Protection Bureau", "phone": "1-603-271-3641"},
    "NJ": {"name": "New Jersey Division of Consumer Affairs", "phone": "1-800-242-5846"},
    "NM": {"name": "New Mexico Attorney General Consumer Protection Division", "phone": "1-844-255-9210"},
    "NY": {"name": "New York Attorney General Consumer Protection Bureau", "phone": "1-800-771-7755"},
    "NC": {"name": "North Carolina Attorney General Consumer Protection Division", "phone": "1-877-566-7226"},
    "ND": {"name": "North Dakota Attorney General Consumer Protection Division", "phone": "1-800-472-2600"},
    "OH": {"name": "Ohio Attorney General Consumer Protection Section", "phone": "1-800-282-0515"},
    "OK": {"name": "Oklahoma Attorney General Consumer Protection Unit", "phone": "1-405-521-2029"},
    "OR": {"name": "Oregon Department of Justice Consumer Protection", "phone": "1-877-877-9392"},
    "PA": {"name": "Pennsylvania Attorney General Consumer Protection Bureau", "phone": "1-800-441-2555"},
    "RI": {"name": "Rhode Island Attorney General Consumer Protection Unit", "phone": "1-401-274-4400"},
    "SC": {"name": "South Carolina Department of Consumer Affairs", "phone": "1-800-922-1594"},
    "SD": {"name": "South Dakota Attorney General Consumer Protection Division", "phone": "1-800-300-1986"},
    "TN": {"name": "Tennessee Attorney General Consumer Protection Division", "phone": "1-615-741-4737"},
    "TX": {"name": "Texas Attorney General Consumer Protection Division", "phone": "1-800-621-0508"},
    "UT": {"name": "Utah Division of Consumer Protection", "phone": "1-801-530-6601"},
    "VT": {"name": "Vermont Attorney General Consumer Protection Division", "phone": "1-800-649-2424"},
    "VA": {"name": "Virginia Attorney General Consumer Protection Section", "phone": "1-800-552-9963"},
    "WA": {"name": "Washington Attorney General Consumer Protection Division", "phone": "1-800-551-4636"},
    "WV": {"name": "West Virginia Attorney General Consumer Protection Division", "phone": "1-800-368-8808"},
    "WI": {"name": "Wisconsin Department of Agriculture Consumer Protection", "phone": "1-800-422-7128"},
    "WY": {"name": "Wyoming Attorney General Consumer Protection Unit", "phone": "1-307-777-7841"},
    "DC": {"name": "DC Attorney General Office of Consumer Protection", "phone": "1-202-442-9828"},
}

# -- State senior programs ----------------------------------------------------
STATE_SENIOR_PROGRAMS: Dict[str, List[str]] = {
    "AL": ["Alabama Medicaid Agency", "SHIP (State Health Insurance Assistance Program)"],
    "AK": ["Alaska Commission on Aging", "Senior Benefits Program"],
    "AZ": ["Arizona Department of Economic Security Aging Services", "SHIP Medicare Counseling"],
    "AR": ["Arkansas Division of Aging and Adult Services", "SHIP Medicare Counseling"],
    "CA": ["California Department of Aging", "HICAP (Medicare counseling)", "Cal MediConnect"],
    "CO": ["Colorado Division of Aging and Adult Services", "SHIP Medicare Counseling", "Old Age Pension"],
    "CT": ["Connecticut Department on Aging", "CHOICES (Medicare counseling)", "CT Energy Assistance"],
    "DE": ["Delaware Division of Services for Aging", "ELDERinfo (Medicare counseling)"],
    "FL": ["Florida SHINE (Medicare counseling)", "Florida Silver Alert", "Florida Department of Elder Affairs"],
    "GA": ["Georgia Division of Aging Services", "GeorgiaCares (Medicare counseling)"],
    "HI": ["Hawaii Executive Office on Aging", "SHIP Medicare Counseling", "Kupuna Care"],
    "ID": ["Idaho Commission on Aging", "SHIBA (Medicare counseling)"],
    "IL": ["Illinois Department on Aging", "SHIP Medicare Counseling", "Illinois Circuit Breaker Tax Relief"],
    "IN": ["Indiana Division of Aging", "SHIP Medicare Counseling"],
    "IA": ["Iowa Department on Aging", "SHIIP (Medicare counseling)"],
    "KS": ["Kansas Department for Aging and Disability Services", "SHICK (Medicare counseling)"],
    "KY": ["Kentucky Department for Aging and Independent Living", "SHIP Medicare Counseling"],
    "LA": ["Louisiana Governor's Office of Elderly Affairs", "SHIP Medicare Counseling"],
    "ME": ["Maine Office of Aging and Disability Services", "SHIP Medicare Counseling"],
    "MD": ["Maryland Department of Aging", "SHIP Medicare Counseling", "Senior Prescription Drug Program"],
    "MA": ["Massachusetts Executive Office of Elder Affairs", "SHINE (Medicare counseling)", "Prescription Advantage"],
    "MI": ["Michigan Aging and Adult Services Agency", "MMAP (Medicare counseling)"],
    "MN": ["Minnesota Board on Aging", "Senior LinkAge Line (Medicare counseling)", "Minnesota Senior Rx"],
    "MS": ["Mississippi Division of Aging and Adult Services", "SHIP Medicare Counseling"],
    "MO": ["Missouri Division of Senior and Disability Services", "CLAIM (Medicare counseling)"],
    "MT": ["Montana Aging Services Bureau", "SHIP Medicare Counseling"],
    "NE": ["Nebraska State Unit on Aging", "SHIIP (Medicare counseling)"],
    "NV": ["Nevada Aging and Disability Services Division", "SHIP Medicare Counseling"],
    "NH": ["New Hampshire Bureau of Elderly and Adult Services", "ServiceLink (Medicare counseling)"],
    "NJ": ["New Jersey Division of Aging Services", "SHIP Medicare Counseling", "Pharmaceutical Assistance to the Aged"],
    "NM": ["New Mexico Aging and Long-Term Services Department", "Benefits Counseling Program"],
    "NY": ["NY EPIC (prescription discount)", "NY HIICAP (Medicare counseling)", "NY Office for the Aging"],
    "NC": ["North Carolina Division of Aging and Adult Services", "SHIIP (Medicare counseling)"],
    "ND": ["North Dakota Aging Services Division", "SHIC (Medicare counseling)"],
    "OH": ["Ohio Department of Aging", "OSHIIP (Medicare counseling)", "Ohio Golden Buckeye Card"],
    "OK": ["Oklahoma Aging Services Division", "SHIP Medicare Counseling"],
    "OR": ["Oregon Department of Human Services Aging Division", "SHIBA (Medicare counseling)"],
    "PA": ["Pennsylvania Department of Aging", "APPRISE (Medicare counseling)", "PACE Pharmacy Program"],
    "RI": ["Rhode Island Division of Elderly Affairs", "SHIP Medicare Counseling"],
    "SC": ["South Carolina Lieutenant Governor's Office on Aging", "I-CARE (Medicare counseling)"],
    "SD": ["South Dakota Department of Human Services Adult Services", "SHINE (Medicare counseling)"],
    "TN": ["Tennessee Commission on Aging and Disability", "SHIP Medicare Counseling"],
    "TX": ["Texas Health and Human Services Senior Benefits", "HICAP (Medicare counseling)", "Texas PACE Program"],
    "UT": ["Utah Division of Aging and Adult Services", "SHIP Medicare Counseling"],
    "VT": ["Vermont Department of Disabilities, Aging, and Independent Living", "SHIP Medicare Counseling"],
    "VA": ["Virginia Department for Aging and Rehabilitative Services", "VICAP (Medicare counseling)"],
    "WA": ["Washington Aging and Long-Term Support Administration", "SHIBA (Medicare counseling)"],
    "WV": ["West Virginia Bureau of Senior Services", "SHIP Medicare Counseling"],
    "WI": ["Wisconsin Bureau of Aging and Disability Resources", "SHIP Medicare Counseling", "SeniorCare Rx"],
    "WY": ["Wyoming Aging Division", "SHIP Medicare Counseling"],
    "DC": ["DC Office on Aging", "SHIP Medicare Counseling", "DC Senior Citizen Tax Relief"],
}

# -- State senior demographics (60+ population, 2020 Census / ACS estimates) ---
STATE_SENIOR_DEMOGRAPHICS: Dict[str, Dict[str, str]] = {
    "AL": {"pop_60_plus": "1.2 million", "pct_60_plus": "24.5%"},
    "AK": {"pop_60_plus": "140,000", "pct_60_plus": "19.0%"},
    "AZ": {"pop_60_plus": "1.8 million", "pct_60_plus": "24.7%"},
    "AR": {"pop_60_plus": "750,000", "pct_60_plus": "24.9%"},
    "CA": {"pop_60_plus": "8.8 million", "pct_60_plus": "22.1%"},
    "CO": {"pop_60_plus": "1.3 million", "pct_60_plus": "22.0%"},
    "CT": {"pop_60_plus": "930,000", "pct_60_plus": "25.6%"},
    "DE": {"pop_60_plus": "260,000", "pct_60_plus": "26.1%"},
    "FL": {"pop_60_plus": "5.9 million", "pct_60_plus": "27.0%"},
    "GA": {"pop_60_plus": "2.4 million", "pct_60_plus": "22.0%"},
    "HI": {"pop_60_plus": "370,000", "pct_60_plus": "25.7%"},
    "ID": {"pop_60_plus": "420,000", "pct_60_plus": "22.0%"},
    "IL": {"pop_60_plus": "3.0 million", "pct_60_plus": "23.3%"},
    "IN": {"pop_60_plus": "1.6 million", "pct_60_plus": "23.3%"},
    "IA": {"pop_60_plus": "780,000", "pct_60_plus": "24.6%"},
    "KS": {"pop_60_plus": "690,000", "pct_60_plus": "23.5%"},
    "KY": {"pop_60_plus": "1.1 million", "pct_60_plus": "24.5%"},
    "LA": {"pop_60_plus": "1.1 million", "pct_60_plus": "23.0%"},
    "ME": {"pop_60_plus": "400,000", "pct_60_plus": "29.0%"},
    "MD": {"pop_60_plus": "1.5 million", "pct_60_plus": "24.0%"},
    "MA": {"pop_60_plus": "1.8 million", "pct_60_plus": "25.3%"},
    "MI": {"pop_60_plus": "2.5 million", "pct_60_plus": "25.0%"},
    "MN": {"pop_60_plus": "1.3 million", "pct_60_plus": "23.0%"},
    "MS": {"pop_60_plus": "720,000", "pct_60_plus": "24.0%"},
    "MO": {"pop_60_plus": "1.5 million", "pct_60_plus": "24.3%"},
    "MT": {"pop_60_plus": "280,000", "pct_60_plus": "25.3%"},
    "NE": {"pop_60_plus": "450,000", "pct_60_plus": "23.0%"},
    "NV": {"pop_60_plus": "730,000", "pct_60_plus": "23.0%"},
    "NH": {"pop_60_plus": "370,000", "pct_60_plus": "26.9%"},
    "NJ": {"pop_60_plus": "2.3 million", "pct_60_plus": "25.0%"},
    "NM": {"pop_60_plus": "540,000", "pct_60_plus": "25.4%"},
    "NY": {"pop_60_plus": "4.8 million", "pct_60_plus": "24.3%"},
    "NC": {"pop_60_plus": "2.6 million", "pct_60_plus": "24.5%"},
    "ND": {"pop_60_plus": "180,000", "pct_60_plus": "23.0%"},
    "OH": {"pop_60_plus": "2.9 million", "pct_60_plus": "24.8%"},
    "OK": {"pop_60_plus": "950,000", "pct_60_plus": "23.6%"},
    "OR": {"pop_60_plus": "1.1 million", "pct_60_plus": "25.5%"},
    "PA": {"pop_60_plus": "3.3 million", "pct_60_plus": "25.7%"},
    "RI": {"pop_60_plus": "280,000", "pct_60_plus": "25.7%"},
    "SC": {"pop_60_plus": "1.3 million", "pct_60_plus": "25.0%"},
    "SD": {"pop_60_plus": "210,000", "pct_60_plus": "23.5%"},
    "TN": {"pop_60_plus": "1.7 million", "pct_60_plus": "24.0%"},
    "TX": {"pop_60_plus": "5.8 million", "pct_60_plus": "19.4%"},
    "UT": {"pop_60_plus": "580,000", "pct_60_plus": "17.5%"},
    "VT": {"pop_60_plus": "190,000", "pct_60_plus": "29.5%"},
    "VA": {"pop_60_plus": "2.0 million", "pct_60_plus": "23.1%"},
    "WA": {"pop_60_plus": "1.8 million", "pct_60_plus": "23.2%"},
    "WV": {"pop_60_plus": "500,000", "pct_60_plus": "27.8%"},
    "WI": {"pop_60_plus": "1.5 million", "pct_60_plus": "25.0%"},
    "WY": {"pop_60_plus": "140,000", "pct_60_plus": "24.0%"},
    "DC": {"pop_60_plus": "140,000", "pct_60_plus": "20.0%"},
}


# -- Data models ---------------------------------------------------------------


@dataclass
class StateContext:
    """All data needed to generate a state page."""

    state_code: str
    state_name: str
    slug: str
    region: str
    zip_count: int
    county_count: int
    dma_count: int
    location_count: int
    merchant_count: int
    coverage_tier: str  # full, emerging
    top_merchants: List[Dict[str, Any]]  # name, location_count, discount_value
    dma_pages: List[Dict[str, Any]]  # slug, display_name, merchant_count, location_count
    ag_office: Dict[str, str]  # name, phone
    senior_programs: List[str]
    demographics: Dict[str, str]  # pop_60_plus, pct_60_plus
    protection_slugs: List[str]
    guide_slugs: List[str]


# -- Supabase helpers ----------------------------------------------------------


async def fetch_json(
    http: httpx.AsyncClient,
    settings: Settings,
    path: str,
    params: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Fetch from Supabase REST API with pagination."""
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    batch = 5000
    base_url = f"{settings.supabase_url}/rest/v1/{path}"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    while True:
        p = dict(params or {})
        p["limit"] = str(batch)
        p["offset"] = str(offset)
        resp = await http.get(base_url, headers=headers, params=p)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data)
        if len(data) < batch:
            break
        offset += batch
    return all_rows


async def gather_state_contexts(
    settings: Settings,
    state_filter: Optional[str] = None,
    force_regen: bool = False,
) -> List[StateContext]:
    """Query Supabase and build StateContext for each state."""

    async with httpx.AsyncClient(timeout=120.0) as http:
        # 1. Fetch Zip_County_DMA mapping
        logger.info("fetching_zip_county_dma")
        zips_raw = await fetch_json(
            http, settings, "Zip_County_DMA",
            {"select": "zip,county_name,state_code,DMA_description"},
        )

        # Build state -> zips/counties/DMAs
        state_zips: Dict[str, Set[str]] = defaultdict(set)
        state_counties: Dict[str, Set[str]] = defaultdict(set)
        state_dmas: Dict[str, Set[str]] = defaultdict(set)
        zip_to_state: Dict[str, str] = {}

        for r in zips_raw:
            sc = r.get("state_code")
            if not sc:
                continue
            z = str(r["zip"])
            state_zips[sc].add(z)
            zip_to_state[z] = sc
            if r.get("county_name"):
                state_counties[sc].add(r["county_name"])
            if r.get("DMA_description"):
                state_dmas[sc].add(r["DMA_description"])

        logger.info("states_found", count=len(state_zips))

        # 2. Fetch merchant defaults (source of truth for discount values)
        logger.info("fetching_merchant_defaults")
        merchants_raw = await fetch_json(
            http, settings, "merchants",
            {"select": "id,name,default_discount_value,default_discount_text"},
        )
        merchant_defaults: Dict[str, Dict[str, Any]] = {}
        for m in merchants_raw:
            merchant_defaults[m["name"]] = {
                "default_discount_value": m.get("default_discount_value", ""),
                "default_discount_text": m.get("default_discount_text", ""),
            }

        # 3. Fetch store locations for location counts per state
        logger.info("fetching_store_locations")
        enriched = await fetch_json(
            http, settings, "store_locations_with_effective_discount_enriched",
            {"select": "merchant_id,merchant_name,zip"},
        )

        # Map locations to states
        state_locations: Dict[str, List[Dict]] = defaultdict(list)
        for loc in enriched:
            z = loc.get("zip", "")
            z_short = z.split("-")[0] if z else ""
            sc = zip_to_state.get(z) or zip_to_state.get(z_short)
            if sc:
                state_locations[sc].append(loc)

        # 4. Fetch published DMA page content for sub-page directory
        logger.info("fetching_dma_pages")
        dma_pages_raw = await fetch_json(
            http, settings, "dma_page_content",
            {
                "select": "slug,display_name,merchant_count,location_count,state_codes,status",
                "status": "eq.published",
            },
        )

        # Build state -> DMA pages
        state_dma_pages: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
        for dma in dma_pages_raw:
            dma_states = dma.get("state_codes", [])
            if isinstance(dma_states, str):
                try:
                    dma_states = json.loads(dma_states)
                except (json.JSONDecodeError, TypeError):
                    dma_states = []
            for sc in dma_states:
                state_dma_pages[sc].append({
                    "slug": dma["slug"],
                    "display_name": dma["display_name"],
                    "merchant_count": dma.get("merchant_count", 0) or 0,
                    "location_count": dma.get("location_count", 0) or 0,
                })

        # 5. Check which states already have content
        existing_states: Set[str] = set()
        if not force_regen:
            logger.info("checking_existing_content")
            existing_raw = await fetch_json(
                http, settings, "state_page_content",
                {"select": "state_code"},
            )
            existing_states = {r["state_code"] for r in existing_raw}

        # 6. Build contexts for all 51 states
        contexts = []
        for sc, name in sorted(STATE_NAMES.items()):
            if state_filter and sc != state_filter:
                continue
            if sc in existing_states:
                logger.info("skipping_has_content", state=sc)
                continue

            locs = state_locations.get(sc, [])
            location_count = len(locs)

            # Count locations per merchant
            merch_counter: Counter = Counter()
            for loc in locs:
                mid = loc.get("merchant_name", "Unknown")
                merch_counter[mid] += 1

            # Build top merchants using defaults from merchants table
            top_merchants = []
            for mname, cnt in merch_counter.most_common(10):
                defaults = merchant_defaults.get(mname, {})
                # Prefer default_discount_text, fall back to default_discount_value
                discount_display = (
                    defaults.get("default_discount_text", "")
                    or defaults.get("default_discount_value", "")
                )
                top_merchants.append({
                    "name": mname,
                    "location_count": cnt,
                    "discount_value": discount_display,
                })

            coverage_tier = "full" if location_count >= 50 else "emerging"

            # Pick protection slugs (rotate)
            idx = hash(sc) % (len(UNIVERSAL_PROTECTION_SLUGS) - 2)
            protection_slugs = UNIVERSAL_PROTECTION_SLUGS[idx:idx + 3]

            # Sort DMA pages by location count descending
            dma_pages = sorted(
                state_dma_pages.get(sc, []),
                key=lambda d: -(d.get("location_count") or 0),
            )

            ctx = StateContext(
                state_code=sc,
                state_name=name,
                slug=STATE_SLUGS[sc],
                region=STATE_REGIONS.get(sc, "United States"),
                zip_count=len(state_zips.get(sc, set())),
                county_count=len(state_counties.get(sc, set())),
                dma_count=len(state_dmas.get(sc, set())),
                location_count=location_count,
                merchant_count=len(merch_counter),
                coverage_tier=coverage_tier,
                top_merchants=top_merchants,
                dma_pages=dma_pages,
                ag_office=STATE_AG_OFFICES.get(sc, {"name": "", "phone": ""}),
                senior_programs=STATE_SENIOR_PROGRAMS.get(sc, []),
                demographics=STATE_SENIOR_DEMOGRAPHICS.get(sc, {}),
                protection_slugs=protection_slugs,
                guide_slugs=UNIVERSAL_GUIDE_SLUGS[:2],
            )
            contexts.append(ctx)

    # Sort by location count descending (process biggest states first)
    contexts.sort(key=lambda c: -c.location_count)
    return contexts


# -- Prompt building -----------------------------------------------------------


def build_system_prompt() -> str:
    """Build the system prompt with brand voice."""
    brand_voice = BRAND_VOICE_PATH.read_text() if BRAND_VOICE_PATH.exists() else ""

    return f"""You are a senior content writer for Saverwell, a free platform helping Americans aged 60+ find verified senior discounts, stay protected from financial threats, and access expert guides on topics like Medicare and insurance.

{brand_voice}

YOUR TASK: Generate structured page content for a STATE-LEVEL hub page on Saverwell.com. This page is a PARENT page that links to metro-area (DMA) sub-pages. It captures queries like "senior discounts in [State]", "[State] senior discount stores", "[State] senior savings programs".

STATE PAGE vs DMA PAGE DIFFERENCES:
- State pages provide a BROAD OVERVIEW, not local detail
- DO NOT list individual store addresses or specific discount days/times
- DO reference specific metro areas by name and link readers to explore them
- DO reference state-level programs, state AG consumer protection, state demographics
- DO position Saverwell as a statewide resource connecting seniors to local deals
- The explore_areas_md section should read as a helpful directory of metro areas

CRITICAL SEO RULES:
- The hero_headline MUST include the state name and "Senior Discounts" (e.g., "Senior Discounts in Texas")
- The seo_title MUST follow: "Senior Discounts in [State] 2026 - [Count] Stores Across [N] Metro Areas | Saverwell"
- The seo_description MUST be 150-160 characters and mention the state, store count, and that discounts are free/verified
- FAQ questions MUST match real state-level search queries (People Also Ask format)
- seo_keywords MUST include "[state] senior discounts", "[state] senior savings programs" (not city names)
- Use natural language, not keyword stuffing

GEO (GENERATIVE ENGINE OPTIMIZATION) DIRECTIVES:
- Cite authoritative sources by name (e.g., "According to the U.S. Census Bureau, [State] has over X million residents aged 60+")
- Include at least one statistic with a named source per major content section
- Reference known organizations: AARP, state Department of Aging, U.S. Census Bureau, state AG office
- Use authoritative, factual tone

DIRECT ANSWER REQUIREMENT:
- Produce a "direct_answer" field: 40-60 words directly answering "Where can seniors get discounts in [State]?"
- Focus on statewide scope: number of metro areas, total merchants, and 2-3 top merchants available statewide
- This block is extracted by featured snippets and AI answer engines

UNIQUE FIELD - explore_areas_md:
- A prose section introducing the state's metro areas
- Mention each DMA area by display name with merchant/location counts
- Group areas by region if the state has many (e.g., "North Texas" vs "Gulf Coast")
- Format as a natural narrative with a bulleted area list, NOT a dry table
- This section MUST NOT duplicate detail that belongs on DMA pages

CONTENT RULES:
- Short paragraphs (2-3 sentences max)
- Bullet points for lists
- NEVER use em dashes or en dashes. Use commas, periods, semicolons, or " - " (spaced hyphen) instead
- NEVER bold words mid-sentence. Bolding is only for section headers or standalone labels
- Use "seniors", "retirees" - NEVER "elderly" or "old folks"
- Reference real merchant names from the provided data
- If location/merchant count is low, keep content proportional - don't oversell thin coverage
- Every section must reference at least one named data source (Census, AARP, local org, etc.)

OUTPUT: Return valid JSON matching the schema exactly. No markdown fences, no extra text."""


def build_user_prompt(ctx: StateContext) -> str:
    """Build the user prompt with state-specific data."""

    merchants_text = ""
    for m in ctx.top_merchants[:8]:
        disc = f" ({m['discount_value']})" if m.get("discount_value") else ""
        merchants_text += f"\n  - {m['name']}: {m['location_count']} locations{disc}"

    dma_text = ""
    for d in ctx.dma_pages:
        dma_text += f"\n  - {d['display_name']}: {d.get('merchant_count', 0)} merchants, {d.get('location_count', 0)} locations"
    if not dma_text:
        dma_text = "\n  (No published DMA pages yet)"

    programs_text = ", ".join(ctx.senior_programs) if ctx.senior_programs else "General SHIP Medicare counseling"

    demo = ctx.demographics
    demo_text = ""
    if demo:
        demo_text = f"\n- Senior Population (60+): {demo.get('pop_60_plus', 'N/A')} ({demo.get('pct_60_plus', 'N/A')} of state population)"

    ag = ctx.ag_office
    ag_text = ""
    if ag.get("name"):
        ag_text = f"\n- Attorney General: {ag['name']}, Consumer Fraud Hotline: {ag.get('phone', 'N/A')}"

    return f"""Generate STATE-LEVEL hub page content for: {ctx.state_name}

STATE DATA:
- State: {ctx.state_name} ({ctx.state_code})
- Region: {ctx.region}
- ZIP codes covered: {ctx.zip_count:,}
- Counties: {ctx.county_count}
- Metro areas (DMAs): {ctx.dma_count}
- Total store locations: {ctx.location_count:,}
- Distinct merchants: {ctx.merchant_count}
- Coverage tier: {ctx.coverage_tier}{demo_text}

STATE-SPECIFIC RESOURCES:{ag_text}
- State Senior Programs: {programs_text}

TOP MERCHANTS IN THIS STATE:{merchants_text}

DMA AREAS IN THIS STATE ({len(ctx.dma_pages)} published pages):{dma_text}

Return a JSON object with these exact keys:

{{
  "direct_answer": "40-60 words answering: Where can seniors get discounts in {ctx.state_name}? Focus on statewide scope - number of metro areas, total merchants, and 2-3 top merchants available statewide.",
  "hero_headline": "{ctx.state_name} Senior Discounts (max 60 chars)",
  "hero_subhead": "One sentence about statewide savings (max 140 chars)",
  "intro_md": "2-3 paragraphs. Reference state senior population (from provided demographics), number of metro areas covered, and why Saverwell is useful statewide. Cite Census data. Markdown.",
  "savings_spotlight_md": "1-2 paragraphs on top statewide merchants. Name merchants available across multiple metro areas. Include discount values where available. Markdown with ## heading.",
  "explore_areas_md": "Section introducing the state's metro areas. Mention each DMA by display name with merchant/location counts. Group by region if 5+ DMAs. Markdown with ## heading.",
  "local_tips_md": "3-5 bullet points. Reference state senior programs (from provided data), state-specific savings culture, regional tips. Markdown with ## heading.",
  "protection_callout_md": "1-2 paragraphs. Reference the state Attorney General by official name (from provided data) and fraud hotline number. Mention state-specific scam trends if known. Markdown with ## heading.",
  "faq_md": "3-5 state-level FAQs in this format:\\n\\n**Q: Question?**\\nAnswer.\\n\\nQuestions should match real state-level searches: What states have the most senior discounts? Does {ctx.state_name} have senior discount programs? How many stores offer senior discounts in {ctx.state_name}?",
  "faq_json": [
    {{"question": "Where can seniors get discounts in {ctx.state_name}?", "answer": "Answer text..."}},
    {{"question": "Does {ctx.state_name} have senior discount programs?", "answer": "Answer text..."}},
    {{"question": "How many stores offer senior discounts in {ctx.state_name}?", "answer": "Answer text..."}}
  ],
  "seo_title": "Senior Discounts in {ctx.state_name} 2026 - [Count] Stores Across [N] Metro Areas | Saverwell",
  "seo_description": "150-160 char meta description with state name, merchant count, and free/verified positioning",
  "seo_keywords": ["{ctx.state_name.lower()} senior discounts", "{ctx.state_name.lower()} senior savings programs", "senior discounts {ctx.state_code}", ...]
}}

IMPORTANT: The faq_json array must contain the same questions and answers as faq_md, but in structured JSON format for FAQPage schema markup. Each object needs "question" and "answer" string fields.

Return ONLY the JSON object. No markdown fences."""


# -- Quality validation --------------------------------------------------------


def validate_content(data: Dict[str, Any], label: str) -> List[str]:
    """Validate generated content and return a list of warnings."""
    warnings: List[str] = []

    # Em dash / en dash check across all text fields
    text_fields = [
        "intro_md", "savings_spotlight_md", "explore_areas_md",
        "local_tips_md", "protection_callout_md", "faq_md",
        "hero_headline", "hero_subhead", "direct_answer",
    ]
    for fld in text_fields:
        val = data.get(fld, "")
        if "\u2014" in val or "\u2013" in val:
            warnings.append(f"[{label}] {fld} contains em/en dash")

    # Direct answer word count (target 40-60)
    da = data.get("direct_answer", "")
    da_words = len(da.split()) if da else 0
    if da_words < 30:
        warnings.append(f"[{label}] direct_answer too short ({da_words} words, target 40-60)")
    elif da_words > 80:
        warnings.append(f"[{label}] direct_answer too long ({da_words} words, target 40-60)")

    # SEO description length (target 150-160 chars)
    seo_desc = data.get("seo_description", "")
    if len(seo_desc) < 120:
        warnings.append(f"[{label}] seo_description short ({len(seo_desc)} chars, target 150-160)")
    elif len(seo_desc) > 170:
        warnings.append(f"[{label}] seo_description long ({len(seo_desc)} chars, target 150-160)")

    # SEO title length (max ~70 chars)
    seo_title = data.get("seo_title", "")
    if len(seo_title) > 80:
        warnings.append(f"[{label}] seo_title long ({len(seo_title)} chars, max ~70)")

    # Intro minimum word count
    intro = data.get("intro_md", "")
    if len(intro.split()) < 50:
        warnings.append(f"[{label}] intro_md short ({len(intro.split())} words, min 50)")

    # explore_areas_md should exist for state pages
    explore = data.get("explore_areas_md", "")
    if len(explore.split()) < 20:
        warnings.append(f"[{label}] explore_areas_md too short ({len(explore.split())} words)")

    # FAQ count
    faq_json = data.get("faq_json", [])
    if isinstance(faq_json, list) and len(faq_json) < 3:
        warnings.append(f"[{label}] faq_json has {len(faq_json)} items (min 3)")

    return warnings


# -- LLM generation ------------------------------------------------------------


async def generate_state_content(
    client: anthropic.AsyncAnthropic,
    ctx: StateContext,
    system_prompt: str,
) -> Optional[Dict[str, Any]]:
    """Generate content for a single state."""
    user_prompt = build_user_prompt(ctx)

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("generating", state=ctx.state_code, attempt=attempt)
        try:
            resp = await client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=GENERATION_MAX_TOKENS,
                temperature=GENERATION_TEMPERATURE,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = resp.content[0].text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

            data = json.loads(raw)

            required = [
                "direct_answer", "hero_headline", "hero_subhead", "intro_md",
                "savings_spotlight_md", "explore_areas_md", "local_tips_md",
                "protection_callout_md", "faq_md", "faq_json",
                "seo_title", "seo_description", "seo_keywords",
            ]
            missing = [k for k in required if k not in data or not data[k]]
            if missing:
                logger.warning("missing_keys", state=ctx.state_code, missing=missing)
                if attempt < MAX_RETRIES:
                    continue
                for k in missing:
                    if k == "seo_keywords":
                        data[k] = [f"{ctx.state_name.lower()} senior discounts"]
                    elif k == "faq_json":
                        data[k] = []
                    else:
                        data[k] = ""

            return data

        except json.JSONDecodeError as e:
            logger.error("json_parse_error", state=ctx.state_code, error=str(e)[:200])
        except Exception as e:
            logger.error("generation_error", state=ctx.state_code, error=str(e)[:200])

        if attempt < MAX_RETRIES:
            await asyncio.sleep(2)

    return None


# -- Supabase write ------------------------------------------------------------


async def upsert_state(
    settings: Settings,
    payload: Dict[str, Any],
) -> bool:
    """Upsert a state page row via Supabase REST API."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            f"{settings.supabase_url}/rest/v1/state_page_content?on_conflict=state_code",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation,resolution=merge-duplicates",
            },
            json=payload,
        )
        if resp.status_code in (200, 201):
            return True
        logger.error(
            "supabase_upsert_failed",
            state=payload.get("state_code"),
            status=resp.status_code,
            body=resp.text[:500],
        )
        return False


# -- Cache ---------------------------------------------------------------------


def save_draft(slug: str, payload: Dict[str, Any]) -> None:
    """Cache generated content locally."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFTS_DIR / f"{slug}.json"
    path.write_text(json.dumps(payload, indent=2))
    logger.info("draft_cached", slug=slug, path=str(path))


# -- Main pipeline -------------------------------------------------------------


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate state page content")
    parser.add_argument("--dry-run", action="store_true", help="Skip Supabase writes")
    parser.add_argument("--limit", type=int, default=0, help="Max states to process")
    parser.add_argument("--state", type=str, help="Process single state by code (e.g., TX)")
    parser.add_argument(
        "--force-regen", action="store_true",
        help="Overwrite existing state rows",
    )
    args = parser.parse_args()

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    # Gather state data
    logger.info("gathering_state_data")
    contexts = await gather_state_contexts(
        settings,
        state_filter=args.state.upper() if args.state else None,
        force_regen=args.force_regen,
    )
    logger.info("states_to_process", count=len(contexts))

    if not contexts:
        logger.info("no_states_to_process")
        return

    if args.limit:
        contexts = contexts[:args.limit]
        logger.info("limited_to", count=len(contexts))

    # Build prompts
    system_prompt = build_system_prompt()
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    # Generate content
    success = 0
    failed = 0
    all_warnings: List[str] = []
    for i, ctx in enumerate(contexts):
        logger.info(
            "processing",
            index=f"{i+1}/{len(contexts)}",
            state=ctx.state_code,
            locations=ctx.location_count,
            merchants=ctx.merchant_count,
            dma_pages=len(ctx.dma_pages),
        )

        data = await generate_state_content(client, ctx, system_prompt)
        if not data:
            logger.error("generation_failed", state=ctx.state_code)
            failed += 1
            continue

        # Quality validation
        content_warnings = validate_content(data, ctx.state_code)
        all_warnings.extend(content_warnings)
        for w in content_warnings:
            logger.warning("quality_check", warning=w)

        # Build payload
        faq_json = data.get("faq_json", [])
        if not isinstance(faq_json, list):
            faq_json = []

        payload = {
            "state_code": ctx.state_code,
            "state_name": ctx.state_name,
            "slug": ctx.slug,
            "region": ctx.region,
            "zip_count": ctx.zip_count,
            "county_count": ctx.county_count,
            "dma_count": ctx.dma_count,
            "location_count": ctx.location_count,
            "merchant_count": ctx.merchant_count,
            "coverage_tier": ctx.coverage_tier,
            "dma_pages": ctx.dma_pages,
            "direct_answer": data.get("direct_answer", ""),
            "hero_headline": data["hero_headline"],
            "hero_subhead": data["hero_subhead"],
            "intro_md": data["intro_md"],
            "savings_spotlight_md": data["savings_spotlight_md"],
            "explore_areas_md": data["explore_areas_md"],
            "local_tips_md": data["local_tips_md"],
            "protection_callout_md": data["protection_callout_md"],
            "faq_md": data["faq_md"],
            "faq_json": faq_json,
            "featured_protection_slugs": ctx.protection_slugs,
            "featured_guide_slugs": ctx.guide_slugs,
            "seo_title": data["seo_title"],
            "seo_description": data["seo_description"],
            "seo_keywords": data["seo_keywords"],
            "status": "draft",
            "source": "generate_state_page_content",
            "author": "Saverwell AI",
            "review_notes": f"Generated by {GENERATION_MODEL}",
        }

        # Cache locally
        save_draft(ctx.slug, payload)

        # Write to Supabase
        if args.dry_run:
            logger.info("dry_run_skip_write", state=ctx.state_code, slug=ctx.slug)
        else:
            ok = await upsert_state(settings, payload)
            if ok:
                logger.info("upserted", state=ctx.state_code, slug=ctx.slug)
                success += 1
            else:
                failed += 1

        if i < len(contexts) - 1:
            await asyncio.sleep(INTER_STATE_PAUSE)

    logger.info(
        "complete",
        success=success,
        failed=failed,
        total=len(contexts),
        quality_warnings=len(all_warnings),
    )
    if all_warnings:
        logger.info("quality_summary", warnings=all_warnings)


if __name__ == "__main__":
    asyncio.run(main())
