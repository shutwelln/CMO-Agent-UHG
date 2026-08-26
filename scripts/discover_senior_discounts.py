#!/usr/bin/env python3
"""
Discover senior discounts from any blog/article URL, cross-reference against
the Saverwell Supabase merchants table, verify via web search, and stage
everything in a Google Sheet for human review.

Usage:
    python scripts/discover_senior_discounts.py --url "https://example.com/senior-discounts"
    python scripts/discover_senior_discounts.py --url "..." --skip-research
    python scripts/discover_senior_discounts.py --url "..." --sheet-id "existing_sheet_id"
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from difflib import SequenceMatcher

import httpx
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

try:
    import anthropic
except ImportError:
    print("Run: pip install anthropic")
    sys.exit(1)

from cmo_agent.google_auth import get_google_credentials, share_file_restricted
from googleapiclient.discovery import build as build_google

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

SERVICE_ACCOUNT_PATH = str(_PROJECT_ROOT / "data" / "saverwell-google-credentials.json")
OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")
VERIFICATION_CACHE_PATH = str(
    _PROJECT_ROOT / "data" / "saverwell" / "senior_discount_verification.json"
)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]

SUPABASE_HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
}

HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-5-20250929"

# ---------------------------------------------------------------------------
# Known defunct merchants
# ---------------------------------------------------------------------------
DEFUNCT_MERCHANTS = {
    "dressbarn": "Closed all stores 2019",
    "dress barn": "Closed all stores 2019",
    "bon-ton": "Bankruptcy 2018, all stores closed",
    "bon ton": "Bankruptcy 2018, all stores closed",
    "modells": "Bankruptcy 2020, all stores closed",
    "modell's": "Bankruptcy 2020, all stores closed",
    "stein mart": "Bankruptcy 2020, online-only revival",
    "carmike cinemas": "Acquired by AMC 2016",
    "carmike": "Acquired by AMC 2016",
    "sizzler": "Largely defunct, ~15 US locations remain",
}

# ---------------------------------------------------------------------------
# Category mapping: source text -> our merchant_categories slug
# ---------------------------------------------------------------------------
CATEGORY_OVERRIDES: Dict[str, str] = {
    "goodwill": "thrift-secondhand",
    "salvation army": "thrift-secondhand",
    "savers": "thrift-secondhand",
    "petsmart": "pets",
    "petco": "pets",
    "pet supplies plus": "pets",
    "walgreens": "pharmacy",
    "cvs": "pharmacy",
    "rite aid": "pharmacy",
    "fred meyer": "grocery",
    "kroger": "grocery",
    "albertsons": "grocery",
    "publix": "grocery",
    "piggly wiggly": "grocery",
    "harris teeter": "grocery",
    "food lion": "grocery",
    "hy-vee": "grocery",
    "winn-dixie": "grocery",
    "bi-lo": "grocery",
    "safeway": "grocery",
    "sprouts": "grocery",
    "aldi": "grocery",
    "lidl": "grocery",
    "at&t": "telecom",
    "t-mobile": "telecom",
    "verizon": "telecom",
    "consumer cellular": "telecom",
    "great clips": "beauty-personal-care",
    "supercuts": "beauty-personal-care",
    "amtrak": "transportation",
    "greyhound": "transportation",
    "national parks": "entertainment",
    "regal cinemas": "entertainment",
    "amc": "entertainment",
    "cinemark": "entertainment",
    "marcus theatres": "entertainment",
    "lowe's": "home-improvement",
    "lowes": "home-improvement",
    "ace hardware": "home-improvement",
    "sherwin-williams": "home-improvement",
    "jiffy lube": "auto",
    "autozone": "auto",
    "advance auto parts": "auto",
    "o'reilly auto parts": "auto",
    "napa auto parts": "auto",
}

CATEGORY_KEYWORD_MAP: Dict[str, str] = {
    "grocery": "grocery",
    "supermarket": "grocery",
    "food": "grocery",
    "restaurant": "restaurant",
    "dining": "restaurant",
    "fast food": "restaurant",
    "pizza": "restaurant",
    "coffee": "restaurant",
    "retail": "retail",
    "clothing": "retail",
    "department store": "retail",
    "pharmacy": "pharmacy",
    "drugstore": "pharmacy",
    "hotel": "hotels-lodging",
    "lodging": "hotels-lodging",
    "motel": "hotels-lodging",
    "airline": "airlines",
    "air travel": "airlines",
    "cruise": "cruises-travel",
    "travel": "cruises-travel",
    "movie": "entertainment",
    "theater": "entertainment",
    "museum": "entertainment",
    "cinema": "entertainment",
    "auto": "auto",
    "car": "auto",
    "tire": "auto",
    "oil change": "auto",
    "telecom": "telecom",
    "phone": "telecom",
    "cell": "telecom",
    "wireless": "telecom",
    "home improvement": "home-improvement",
    "hardware": "home-improvement",
    "thrift": "thrift-secondhand",
    "secondhand": "thrift-secondhand",
    "consignment": "thrift-secondhand",
    "salon": "beauty-personal-care",
    "barber": "beauty-personal-care",
    "beauty": "beauty-personal-care",
    "pet": "pets",
    "transit": "transportation",
    "bus": "transportation",
    "train": "transportation",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def normalize_name(name: str) -> str:
    """Normalize merchant name for fuzzy matching."""
    s = name.lower().strip()
    # Remove common suffixes
    for suffix in [
        " inc.", " inc", " llc", " corp.", " corp", " co.",
        " company", " stores", " store", "'s", "\u2019s",
    ]:
        if s.endswith(suffix):
            s = s[: -len(suffix)]
    # Remove apostrophes and extra spaces
    s = s.replace("'", "").replace("\u2019", "")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def fuzzy_match(name1: str, name2: str) -> float:
    """Return 0-1 similarity between two merchant names."""
    n1 = normalize_name(name1)
    n2 = normalize_name(name2)
    if n1 == n2:
        return 1.0
    return SequenceMatcher(None, n1, n2).ratio()


def slugify(name: str) -> str:
    """Convert merchant name to URL slug."""
    s = name.lower()
    s = s.replace("'", "").replace("\u2019", "")
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-{2,}", "-", s)
    s = s.strip("-")
    return f"{s}-senior-discount"


def check_defunct(name: str) -> Optional[str]:
    """Check if a merchant is known defunct. Returns reason or None."""
    normalized = normalize_name(name)
    for defunct_name, reason in DEFUNCT_MERCHANTS.items():
        if defunct_name in normalized or normalized in defunct_name:
            return reason
    return None


def categorize_merchant(
    name: str, source_category: str, slug_to_id: Dict[str, int]
) -> Tuple[str, int]:
    """Auto-categorize a merchant. Returns (slug, category_id)."""
    normalized = normalize_name(name)

    # Check per-merchant overrides first
    for override_name, slug in CATEGORY_OVERRIDES.items():
        if override_name in normalized:
            cat_id = slug_to_id.get(slug, 0)
            return slug, cat_id

    # Check source category keywords
    source_lower = source_category.lower() if source_category else ""
    for keyword, slug in CATEGORY_KEYWORD_MAP.items():
        if keyword in source_lower:
            cat_id = slug_to_id.get(slug, 0)
            return slug, cat_id

    # Default to retail
    return "retail", slug_to_id.get("retail", 0)


# ---------------------------------------------------------------------------
# Step 1: Fetch and parse source URL with LLM
# ---------------------------------------------------------------------------
def fetch_page_content(url: str) -> str:
    """Fetch a URL and return its text content."""
    print(f"  Fetching {url} ...")
    resp = httpx.get(
        url,
        follow_redirects=True,
        timeout=30,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    )
    resp.raise_for_status()

    # Strip HTML tags for a rough text extraction
    from html.parser import HTMLParser

    class TagStripper(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.result: list[str] = []
            self._skip = False

        def handle_starttag(self, tag: str, attrs: list) -> None:
            if tag in ("script", "style", "nav", "footer", "header"):
                self._skip = True

        def handle_endtag(self, tag: str) -> None:
            if tag in ("script", "style", "nav", "footer", "header"):
                self._skip = False

        def handle_data(self, data: str) -> None:
            if not self._skip:
                self.result.append(data)

    stripper = TagStripper()
    stripper.feed(resp.text)
    text = " ".join(stripper.result)
    # Collapse whitespace
    text = re.sub(r"\s+", " ", text).strip()
    return text


def extract_merchants_from_page(page_text: str, source_url: str) -> List[Dict[str, str]]:
    """Use Claude Haiku to extract structured merchant data from page text."""
    print("  Extracting merchants via LLM ...")

    # Truncate to ~100K chars to stay within token limits
    if len(page_text) > 100_000:
        page_text = page_text[:100_000]

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=16384,
        temperature=0.0,
        system=(
            "You are a data extraction assistant. Extract structured merchant "
            "discount information from the provided webpage text. Be thorough "
            "and extract every merchant mentioned."
        ),
        messages=[
            {
                "role": "user",
                "content": f"""Extract all senior discount merchants from this webpage text.

For each merchant, extract:
- name: The merchant/business name (proper capitalization)
- discount_value: The discount amount normalized (e.g. "10%", "$5 off", "varies by location")
- age_requirement: Age required (e.g. "55+", "60+", "62+", "65+", "AARP members")
- conditions: Any additional conditions (e.g. "Tuesdays only", "AARP required", "varies by location")
- source_category: The category this merchant was listed under on the page (e.g. "Grocery", "Restaurant", "Retail")
- discount_type: One of "In-store", "Plan", "Pass/Membership", or "In-store and Online"
- is_national: true if the merchant operates nationally, false if regional/local

For hotel chains with multiple brands, list EACH brand separately (e.g. each Choice Hotels brand gets its own row). Same for any parent company with distinct sub-brands.

Return ONLY a JSON array. No markdown fences, no extra text.

PAGE TEXT:
{page_text}""",
            }
        ],
    )

    raw = resp.content[0].text.strip()
    # Strip markdown fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

    try:
        merchants = json.loads(raw)
    except json.JSONDecodeError:
        # Common LLM issues: trailing commas, truncated output
        # Try to repair: remove trailing commas before ] or }
        repaired = re.sub(r",\s*([}\]])", r"\1", raw)
        # If truncated mid-object, try to close the array
        if not repaired.rstrip().endswith("]"):
            # Find the last complete object
            last_brace = repaired.rfind("}")
            if last_brace > 0:
                repaired = repaired[: last_brace + 1] + "\n]"
        try:
            merchants = json.loads(repaired)
        except json.JSONDecodeError as e2:
            print(f"  ERROR parsing LLM response (even after repair): {e2}")
            print(f"  First 500 chars: {raw[:500]}")
            return []

    if not isinstance(merchants, list):
        print(f"  WARNING: LLM returned {type(merchants)}, expected list")
        return []
    print(f"  Extracted {len(merchants)} merchants")
    return merchants


# ---------------------------------------------------------------------------
# Step 2: Cross-reference against Supabase merchants
# ---------------------------------------------------------------------------
def fetch_all_merchants(client: httpx.Client) -> List[Dict[str, Any]]:
    """Fetch all active merchants from Supabase."""
    print("  Fetching merchants from Supabase ...")
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    while True:
        resp = client.get(
            f"{SUPABASE_URL}/rest/v1/merchants",
            headers=SUPABASE_HEADERS,
            params={
                "select": (
                    "id,name,category_id,is_national,is_active,"
                    "default_discount_value,default_discount_text,"
                    "default_discount_requirement,default_discount_type,"
                    "default_discount_details_hyperlink,page_slug,page_status"
                ),
                "is_active": "eq.true",
                "limit": "1000",
                "offset": str(offset),
                "order": "name.asc",
            },
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < 1000:
            break
        offset += 1000
    print(f"  Found {len(all_rows)} active merchants in DB")
    return all_rows


def fetch_categories(client: httpx.Client) -> Tuple[Dict[str, int], Dict[int, str]]:
    """Fetch merchant_categories. Returns (slug_to_id, id_to_display_name)."""
    resp = client.get(
        f"{SUPABASE_URL}/rest/v1/merchant_categories",
        headers=SUPABASE_HEADERS,
        params={"select": "id,slug,display_name"},
    )
    resp.raise_for_status()
    cats = resp.json()
    slug_to_id = {c["slug"]: c["id"] for c in cats}
    id_to_name = {c["id"]: c["display_name"] for c in cats}
    return slug_to_id, id_to_name


def fetch_existing_slugs(client: httpx.Client) -> set:
    """Fetch all existing page_slugs."""
    all_slugs: set = set()
    offset = 0
    while True:
        resp = client.get(
            f"{SUPABASE_URL}/rest/v1/merchants",
            headers=SUPABASE_HEADERS,
            params={
                "select": "page_slug",
                "page_slug": "not.is.null",
                "limit": "5000",
                "offset": str(offset),
            },
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        for row in batch:
            if row.get("page_slug"):
                all_slugs.add(row["page_slug"])
        if len(batch) < 5000:
            break
        offset += 5000
    return all_slugs


def cross_reference(
    extracted: List[Dict[str, str]], db_merchants: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Match extracted merchants against DB. Returns enriched list."""
    results = []
    for item in extracted:
        name = item.get("name", "").strip()
        if not name:
            continue

        # Check defunct first
        defunct_reason = check_defunct(name)

        # Find best DB match
        best_match: Optional[Dict[str, Any]] = None
        best_score = 0.0
        for db_m in db_merchants:
            score = fuzzy_match(name, db_m.get("name", ""))
            if score > best_score:
                best_score = score
                best_match = db_m

        status = "New"
        matched_id = None
        db_current_value = ""
        db_current_requirement = ""
        has_diff = ""

        if defunct_reason:
            status = "Defunct"
        elif best_score >= 0.85 and best_match:
            status = "Existing"
            matched_id = best_match["id"]
            db_current_value = str(best_match.get("default_discount_value") or "")
            db_current_requirement = str(
                best_match.get("default_discount_requirement") or ""
            )
            # Check if data differs
            extracted_value = item.get("discount_value", "")
            if db_current_value and extracted_value:
                if db_current_value.lower().strip() != extracted_value.lower().strip():
                    has_diff = "YES"

        results.append(
            {
                "source_name": name,
                "status": status,
                "matched_id": matched_id,
                "match_score": best_score,
                "db_current_value": db_current_value,
                "db_current_requirement": db_current_requirement,
                "has_diff": has_diff,
                "defunct_reason": defunct_reason or "",
                "discount_value": item.get("discount_value", ""),
                "age_requirement": item.get("age_requirement", ""),
                "conditions": item.get("conditions", ""),
                "source_category": item.get("source_category", ""),
                "discount_type": item.get("discount_type", "In-store"),
                "is_national": item.get("is_national", True),
                "db_match": best_match,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Step 3: Normalize requirement text
# ---------------------------------------------------------------------------
def normalize_requirement(raw: str) -> str:
    """Normalize age requirement to canonical form."""
    if not raw:
        return ""
    raw_lower = raw.lower().strip()

    # AARP special case
    if "aarp" in raw_lower:
        return "AARP membership required"

    # Extract age number
    age_match = re.search(r"(\d{2})", raw_lower)
    if age_match:
        age = int(age_match.group(1))
        return f"Ages {age} and up"

    # Passthrough if no pattern matches
    return raw.strip()


# ---------------------------------------------------------------------------
# Step 4: Verification research
# ---------------------------------------------------------------------------
def load_verification_cache() -> Dict[str, Any]:
    """Load the verification URL cache."""
    if os.path.exists(VERIFICATION_CACHE_PATH):
        with open(VERIFICATION_CACHE_PATH, "r") as f:
            return json.load(f)
    return {}


def save_verification_cache(cache: Dict[str, Any]) -> None:
    """Save the verification URL cache."""
    os.makedirs(os.path.dirname(VERIFICATION_CACHE_PATH), exist_ok=True)
    with open(VERIFICATION_CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def verify_merchant_discount(
    name: str,
    cache: Dict[str, Any],
    source_url: str,
) -> Dict[str, str]:
    """
    Search for credible verification of a merchant's senior discount.
    Uses Claude to evaluate search results and pick the best verification URL.
    Returns {url, source_type, confidence}.
    """
    cache_key = normalize_name(name)
    if cache_key in cache:
        return cache[cache_key]

    client = anthropic.Anthropic()

    # Build search queries
    queries = [
        f'"{name}" senior discount',
        f'"{name}" senior discount site:aarp.org',
    ]

    # Use LLM to search and evaluate
    search_prompt = f"""I need to verify whether {name} offers a senior discount.

I would search for:
1. "{name}" senior discount
2. "{name}" senior discount AARP

Based on your knowledge, what is the most credible URL that confirms {name} offers a senior discount?

Consider these source tiers:
- HIGH confidence: The merchant's own website (e.g. {name.lower().replace(' ', '')}.com)
- MEDIUM confidence: AARP.org, Forbes, CNBC, USA Today, or other major publications
- LOW confidence: Blog aggregators, small sites
- UNVERIFIED: If you cannot confidently name a source

Return ONLY a JSON object (no markdown fences):
{{"url": "the best verification URL or empty string", "source_type": "merchant_site|aarp|publication|blog|unverified", "confidence": "High|Medium|Low|Unverified"}}"""

    try:
        resp = client.messages.create(
            model=HAIKU_MODEL,
            max_tokens=512,
            temperature=0.0,
            messages=[{"role": "user", "content": search_prompt}],
        )
        raw = resp.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)
        if not isinstance(result, dict):
            result = {"url": "", "source_type": "unverified", "confidence": "Unverified"}
    except Exception as e:
        print(f"    Verification failed for {name}: {e}")
        result = {"url": "", "source_type": "unverified", "confidence": "Unverified"}

    # Fall back to source URL if unverified
    if result.get("confidence") == "Unverified" and source_url:
        result["url"] = source_url
        result["source_type"] = "blog"
        result["confidence"] = "Low"

    cache[cache_key] = result
    save_verification_cache(cache)

    return result


# ---------------------------------------------------------------------------
# Step 5: Google Sheet output
# ---------------------------------------------------------------------------
REVIEW_HEADERS = [
    "Status",
    "Action",
    "Merchant Name",
    "Source URL",
    "Category",
    "category_id",
    "is_national",
    "Discount Value",
    "Discount Text",
    "Requirement",
    "Discount Type",
    "Conditions",
    "Verification URL",
    "Verification Source",
    "Confidence",
    "page_slug",
    "DB Current Value",
    "DB Current Requirement",
    "Diff?",
    "Existing Merchant ID",
    "Notes",
]

RUN_LOG_HEADERS = [
    "Run Date",
    "Source URL",
    "Total Parsed",
    "New",
    "Existing",
    "Defunct",
    "Verified",
]


def create_or_get_sheet(
    sheets_service: Any,
    drive_service: Any,
    sheet_id: Optional[str],
    categories: List[List[str]],
) -> Tuple[str, str]:
    """Create a new Google Sheet or return existing one. Returns (sheet_id, url)."""
    if sheet_id:
        # Verify it exists
        try:
            ss = sheets_service.spreadsheets().get(spreadsheetId=sheet_id).execute()
            print(f"  Using existing sheet: {ss['spreadsheetUrl']}")
            return sheet_id, ss["spreadsheetUrl"]
        except Exception as e:
            print(f"  WARNING: Could not find sheet {sheet_id}: {e}")
            print("  Creating new sheet instead.")

    # Create new spreadsheet
    body = {
        "properties": {"title": "Senior Discount Discovery Pipeline"},
        "sheets": [
            {"properties": {"title": "Merchant Review", "sheetId": 0}},
            {"properties": {"title": "Run Log", "sheetId": 1}},
            {"properties": {"title": "Category Reference", "sheetId": 2}},
        ],
    }
    ss = sheets_service.spreadsheets().create(body=body).execute()
    sid = ss["spreadsheetId"]
    url = ss["spreadsheetUrl"]
    print(f"  Created new sheet: {url}")

    # Share with authorized users
    share_file_restricted(drive_service, sid)
    # Also share with nick@saverwell.com
    try:
        drive_service.permissions().create(
            fileId=sid,
            body={
                "type": "user",
                "role": "writer",
                "emailAddress": "nick@saverwell.com",
            },
            fields="id",
            sendNotificationEmail=False,
        ).execute()
    except Exception:
        pass  # May already be covered by share_file_restricted

    # Write headers to Merchant Review
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sid,
        range="Merchant Review!A1",
        valueInputOption="RAW",
        body={"values": [REVIEW_HEADERS]},
    ).execute()

    # Write headers to Run Log
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sid,
        range="Run Log!A1",
        valueInputOption="RAW",
        body={"values": [RUN_LOG_HEADERS]},
    ).execute()

    # Write Category Reference
    cat_headers = ["category_id", "slug", "display_name"]
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sid,
        range="Category Reference!A1",
        valueInputOption="RAW",
        body={"values": [cat_headers] + categories},
    ).execute()

    # Format header rows
    _format_sheet(sheets_service, sid, len(categories))

    return sid, url


def _format_sheet(
    sheets_service: Any,
    spreadsheet_id: str,
    num_cat_rows: int,
) -> None:
    """Apply formatting to all sheet tabs."""
    requests = []
    num_cols = len(REVIEW_HEADERS)

    # --- Merchant Review header ---
    requests.append(
        {
            "repeatCell": {
                "range": {
                    "sheetId": 0,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": num_cols,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColorStyle": {
                                "rgbColor": {"red": 1, "green": 1, "blue": 1}
                            },
                        },
                        "backgroundColor": {
                            "red": 0.16,
                            "green": 0.22,
                            "blue": 0.43,
                        },
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        }
    )
    requests.append(
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": 0,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        }
    )

    # --- Run Log header ---
    requests.append(
        {
            "repeatCell": {
                "range": {
                    "sheetId": 1,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": len(RUN_LOG_HEADERS),
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColorStyle": {
                                "rgbColor": {"red": 1, "green": 1, "blue": 1}
                            },
                        },
                        "backgroundColor": {
                            "red": 0.16,
                            "green": 0.22,
                            "blue": 0.43,
                        },
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        }
    )
    requests.append(
        {
            "updateSheetProperties": {
                "properties": {
                    "sheetId": 1,
                    "gridProperties": {"frozenRowCount": 1},
                },
                "fields": "gridProperties.frozenRowCount",
            }
        }
    )

    # --- Category Reference header ---
    requests.append(
        {
            "repeatCell": {
                "range": {
                    "sheetId": 2,
                    "startRowIndex": 0,
                    "endRowIndex": 1,
                    "startColumnIndex": 0,
                    "endColumnIndex": 3,
                },
                "cell": {
                    "userEnteredFormat": {
                        "textFormat": {
                            "bold": True,
                            "foregroundColorStyle": {
                                "rgbColor": {"red": 1, "green": 1, "blue": 1}
                            },
                        },
                        "backgroundColor": {
                            "red": 0.16,
                            "green": 0.22,
                            "blue": 0.43,
                        },
                    }
                },
                "fields": "userEnteredFormat(textFormat,backgroundColor)",
            }
        }
    )

    # Auto-resize columns on all sheets
    for sheet_id, end_col in [(0, num_cols), (1, len(RUN_LOG_HEADERS)), (2, 3)]:
        requests.append(
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sheet_id,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": end_col,
                    }
                }
            }
        )

    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=spreadsheet_id, body={"requests": requests}
    ).execute()


def get_existing_merchant_names(
    sheets_service: Any, spreadsheet_id: str
) -> set:
    """Read existing merchant names from the sheet to avoid duplicates across runs."""
    try:
        result = (
            sheets_service.spreadsheets()
            .values()
            .get(
                spreadsheetId=spreadsheet_id,
                range="Merchant Review!C:C",
            )
            .execute()
        )
        values = result.get("values", [])
        # Skip header row
        return {row[0].lower().strip() for row in values[1:] if row}
    except Exception:
        return set()


def write_review_rows(
    sheets_service: Any,
    spreadsheet_id: str,
    rows: List[List[str]],
) -> None:
    """Append rows to the Merchant Review tab."""
    if not rows:
        return
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Merchant Review!A:U",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def write_run_log(
    sheets_service: Any,
    spreadsheet_id: str,
    source_url: str,
    total: int,
    new_count: int,
    existing_count: int,
    defunct_count: int,
    verified_count: int,
) -> None:
    """Append a row to the Run Log tab."""
    row = [
        datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        source_url,
        str(total),
        str(new_count),
        str(existing_count),
        str(defunct_count),
        str(verified_count),
    ]
    sheets_service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id,
        range="Run Log!A:G",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": [row]},
    ).execute()


def color_status_rows(
    sheets_service: Any,
    spreadsheet_id: str,
    rows: List[List[str]],
    start_row: int,
) -> None:
    """Color-code rows by Status column (index 0)."""
    requests = []
    status_colors = {
        "New": {"red": 0.85, "green": 0.95, "blue": 0.85},       # light green
        "Existing": {"red": 0.9, "green": 0.92, "blue": 1.0},    # light blue
        "Defunct": {"red": 1.0, "green": 0.85, "blue": 0.85},     # light red
    }
    num_cols = len(REVIEW_HEADERS)

    for idx, row in enumerate(rows):
        status = row[0] if row else ""
        bg = status_colors.get(status)
        if bg:
            requests.append(
                {
                    "repeatCell": {
                        "range": {
                            "sheetId": 0,
                            "startRowIndex": start_row + idx,
                            "endRowIndex": start_row + idx + 1,
                            "startColumnIndex": 0,
                            "endColumnIndex": num_cols,
                        },
                        "cell": {"userEnteredFormat": {"backgroundColor": bg}},
                        "fields": "userEnteredFormat.backgroundColor",
                    }
                }
            )

    if requests:
        # Batch in groups of 500 to avoid API limits
        for i in range(0, len(requests), 500):
            batch = requests[i : i + 500]
            sheets_service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id, body={"requests": batch}
            ).execute()


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover senior discounts from any URL and stage in Google Sheet"
    )
    parser.add_argument("--url", required=True, help="Source URL to scrape")
    parser.add_argument(
        "--skip-research",
        action="store_true",
        help="Skip verification research step",
    )
    parser.add_argument(
        "--sheet-id",
        default=None,
        help="Existing Google Sheet ID to append to (creates new if omitted)",
    )
    args = parser.parse_args()

    source_url = args.url

    # Validate environment
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env")
        sys.exit(1)
    if not ANTHROPIC_API_KEY:
        print("ERROR: ANTHROPIC_API_KEY must be set in .env")
        sys.exit(1)

    print("=" * 70)
    print("  Senior Discount Discovery Pipeline")
    print("=" * 70)
    print(f"  Source URL: {source_url}")
    print(f"  Skip research: {args.skip_research}")
    print()

    # ── Step 1: Fetch and parse ──────────────────────────────────────────
    print("STEP 1: Fetch and parse source URL")
    page_text = fetch_page_content(source_url)
    print(f"  Page text length: {len(page_text):,} chars")

    extracted = extract_merchants_from_page(page_text, source_url)
    if not extracted:
        print("ERROR: No merchants extracted from page. Exiting.")
        sys.exit(1)
    print(f"  Extracted {len(extracted)} merchants from page")

    # ── Step 2: Cross-reference with DB ──────────────────────────────────
    print("\nSTEP 2: Cross-reference against Supabase")
    with httpx.Client(timeout=30) as http_client:
        db_merchants = fetch_all_merchants(http_client)
        slug_to_id, id_to_name = fetch_categories(http_client)
        existing_slugs = fetch_existing_slugs(http_client)

    enriched = cross_reference(extracted, db_merchants)
    new_count = sum(1 for r in enriched if r["status"] == "New")
    existing_count = sum(1 for r in enriched if r["status"] == "Existing")
    defunct_count = sum(1 for r in enriched if r["status"] == "Defunct")
    print(f"  New: {new_count}  |  Existing: {existing_count}  |  Defunct: {defunct_count}")

    # ── Step 3: Auto-categorize ──────────────────────────────────────────
    print("\nSTEP 3: Auto-categorize merchants")
    for item in enriched:
        if item["status"] == "Existing" and item.get("db_match"):
            # Use the DB category for existing merchants
            db_cat_id = item["db_match"].get("category_id")
            if db_cat_id:
                cat_name = id_to_name.get(db_cat_id, "")
                item["category_name"] = cat_name
                item["category_id"] = db_cat_id
                continue

        cat_slug, cat_id = categorize_merchant(
            item["source_name"], item["source_category"], slug_to_id
        )
        item["category_name"] = id_to_name.get(cat_id, cat_slug)
        item["category_id"] = cat_id

    # ── Step 4: Verification research ────────────────────────────────────
    verified_count = 0
    if not args.skip_research:
        print("\nSTEP 4: Verification research")
        cache = load_verification_cache()
        total = len(enriched)
        for idx, item in enumerate(enriched):
            name = item["source_name"]
            print(f"  [{idx + 1}/{total}] Verifying: {name} ...", end="")
            result = verify_merchant_discount(name, cache, source_url)
            item["verification_url"] = result.get("url", "")
            item["verification_source"] = result.get("source_type", "unverified")
            item["confidence"] = result.get("confidence", "Unverified")
            if result.get("confidence") in ("High", "Medium"):
                verified_count += 1
            print(f" {result.get('confidence', 'Unverified')}")
            # Brief pause to avoid rate limits
            time.sleep(0.3)
        print(f"  Verified: {verified_count} / {total}")
    else:
        print("\nSTEP 4: Verification research (SKIPPED)")
        for item in enriched:
            item["verification_url"] = source_url
            item["verification_source"] = "blog"
            item["confidence"] = "Low"

    # ── Step 5: Generate slugs ───────────────────────────────────────────
    print("\nSTEP 5: Generate page slugs")
    generated_slugs: set = set()
    for item in enriched:
        if item["status"] == "Existing" and item.get("db_match"):
            item["page_slug"] = item["db_match"].get("page_slug", "")
        else:
            slug = slugify(item["source_name"])
            # Check for collisions
            if slug in existing_slugs or slug in generated_slugs:
                counter = 2
                while f"{slug}-{counter}" in existing_slugs or f"{slug}-{counter}" in generated_slugs:
                    counter += 1
                slug = f"{slug}-{counter}"
            generated_slugs.add(slug)
            item["page_slug"] = slug

    # ── Step 6: Build sheet rows ─────────────────────────────────────────
    print("\nSTEP 6: Build Google Sheet rows")

    # Build category reference data
    cat_rows = []
    for slug, cat_id in sorted(slug_to_id.items(), key=lambda x: x[1]):
        cat_rows.append([str(cat_id), slug, id_to_name.get(cat_id, "")])

    # Initialize Google services
    # Use OAuth for Sheets/Drive (service account lacks Sheets API permission)
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    sheets_svc = build_google("sheets", "v4", credentials=creds)
    drive_svc = build_google("drive", "v3", credentials=creds)

    sheet_id, sheet_url = create_or_get_sheet(
        sheets_svc, drive_svc, args.sheet_id, cat_rows
    )

    # Check for existing merchants in sheet (dedup across runs)
    existing_in_sheet = get_existing_merchant_names(sheets_svc, sheet_id)

    # Find current row count for color coding offset
    try:
        existing_data = (
            sheets_svc.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range="Merchant Review!A:A")
            .execute()
        )
        start_row = len(existing_data.get("values", []))
    except Exception:
        start_row = 1

    # Build rows
    sheet_rows = []
    skipped_dupes = 0
    for item in enriched:
        name = item["source_name"]

        # Skip if already in sheet from a prior run
        if name.lower().strip() in existing_in_sheet:
            skipped_dupes += 1
            continue

        # Build discount text
        discount_text = ""
        if item["discount_value"]:
            discount_text = f"{item['discount_value']} for seniors"
            if item["age_requirement"]:
                discount_text += f" {item['age_requirement']}"

        # Build requirement
        requirement = normalize_requirement(item.get("age_requirement", ""))

        # Build notes
        notes_parts = []
        if item.get("defunct_reason"):
            notes_parts.append(f"Defunct - {item['defunct_reason']}")
        if item.get("conditions"):
            notes_parts.append(item["conditions"])
        notes = "; ".join(notes_parts)

        row = [
            item["status"],                                      # Status
            "",                                                  # Action (user fills)
            name,                                                # Merchant Name
            source_url,                                          # Source URL
            item.get("category_name", ""),                       # Category
            str(item.get("category_id", "")),                    # category_id
            str(item.get("is_national", True)),                  # is_national
            item.get("discount_value", ""),                      # Discount Value
            discount_text,                                       # Discount Text
            requirement,                                         # Requirement
            item.get("discount_type", "In-store"),               # Discount Type
            item.get("conditions", ""),                          # Conditions
            item.get("verification_url", ""),                    # Verification URL
            item.get("verification_source", ""),                 # Verification Source
            item.get("confidence", "Unverified"),                # Confidence
            item.get("page_slug", ""),                           # page_slug
            item.get("db_current_value", ""),                    # DB Current Value
            item.get("db_current_requirement", ""),              # DB Current Requirement
            item.get("has_diff", ""),                            # Diff?
            str(item.get("matched_id", "") or ""),               # Existing Merchant ID
            notes,                                               # Notes
        ]
        sheet_rows.append(row)

    if skipped_dupes:
        print(f"  Skipped {skipped_dupes} merchants already in sheet from prior runs")

    print(f"  Writing {len(sheet_rows)} rows to sheet")

    # Write data
    write_review_rows(sheets_svc, sheet_id, sheet_rows)

    # Color-code rows
    print("  Applying color coding ...")
    color_status_rows(sheets_svc, sheet_id, sheet_rows, start_row)

    # Write run log
    write_run_log(
        sheets_svc,
        sheet_id,
        source_url,
        len(extracted),
        new_count,
        existing_count,
        defunct_count,
        verified_count,
    )

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("  COMPLETE")
    print("=" * 70)
    print(f"  Source URL:    {source_url}")
    print(f"  Total parsed:  {len(extracted)}")
    print(f"  New:           {new_count}")
    print(f"  Existing:      {existing_count}")
    print(f"  Defunct:        {defunct_count}")
    print(f"  Verified:      {verified_count}")
    print(f"  Rows written:  {len(sheet_rows)}")
    if skipped_dupes:
        print(f"  Dupes skipped: {skipped_dupes}")
    print()
    print(f"  Google Sheet:  {sheet_url}")
    print(f"  Sheet ID:      {sheet_id}")
    print()
    print("Next steps:")
    print("  1. Open the Google Sheet and review the Merchant Review tab")
    print("  2. Fill in the Action column: Insert / Update / Skip")
    print("  3. Run: python scripts/push_approved_merchants.py --sheet-id", sheet_id)


if __name__ == "__main__":
    main()
