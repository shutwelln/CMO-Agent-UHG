#!/usr/bin/env python3
"""
Verify senior discount claims using Gemini with Google Search grounding.

For each "New" row in the Merchant Review sheet, queries Gemini to independently
verify whether the merchant actually offers a senior discount, captures verification
details, and updates the sheet with results.

Usage:
    python scripts/verify_discount_sheet.py --sheet-id "SHEET_ID"
    python scripts/verify_discount_sheet.py --sheet-id "SHEET_ID" --dry-run
    python scripts/verify_discount_sheet.py --sheet-id "SHEET_ID" --limit 10
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project setup
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from google import genai
from google.genai import types

from cmo_agent.google_auth import get_google_credentials
from googleapiclient.discovery import build as build_google

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"

OAUTH_TOKEN_PATH = str(_PROJECT_ROOT / "data" / "google-token.json")

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

# Column indices (0-based) in Merchant Review tab
COL_STATUS = 0        # A
COL_ACTION = 1        # B
COL_NAME = 2          # C
COL_SOURCE_URL = 3    # D
COL_CATEGORY = 4      # E
COL_DISCOUNT_VAL = 7  # H
COL_DISCOUNT_TXT = 8  # I
COL_REQUIREMENT = 9   # J
COL_DISCOUNT_TYPE = 10  # K
COL_CONDITIONS = 11   # L
COL_VERIF_URL = 12    # M
COL_VERIF_SOURCE = 13  # N
COL_CONFIDENCE = 14   # O
COL_NOTES = 20        # U
COL_SOURCES_COUNT = 21  # V (from consolidation script)
COL_STORE_LOCATOR = 22  # W: Store Locator Scrapeable?


def safe_get(row: List[str], idx: int) -> str:
    """Safely get a value from a row."""
    if idx < len(row):
        return row[idx]
    return ""


def safe_set(row: List[str], idx: int, value: str) -> None:
    """Safely set a value in a row, extending if needed."""
    while len(row) <= idx:
        row.append("")
    row[idx] = value


# ---------------------------------------------------------------------------
# Gemini verification
# ---------------------------------------------------------------------------
def find_verification_url(
    client: genai.Client,
    merchant_name: str,
) -> Dict[str, str]:
    """
    Use Gemini with search grounding to find the best direct URL verifying
    a merchant's senior discount. Prioritizes the merchant's own website.

    Returns dict with:
        url: direct URL to the page
        source_type: "merchant_site" | "aarp" | "publication" | "blog"
    """
    prompt = f"""I need to find a direct URL that proves {merchant_name} offers a senior citizen discount. Search the web for this.

FIRST: Search {merchant_name}'s own official website for any page mentioning senior discounts, senior pricing, senior menu, AARP partnership, special offers, deals page, or FAQ. Try paths like /deals, /offers, /faq, /senior, /aarp, /discounts, /savings, /promotions, /menu. Most companies have a page somewhere on their site that mentions this.

IF the company's own website has NO relevant page, THEN search for an AARP.org page (e.g. aarp.org/benefits-discounts/all/{merchant_name.lower().replace(' ', '-')}/).

IF neither exists, find the best article from a major publication or coupon site.

RULES:
- The URL MUST be a real, complete, direct URL to the specific page. NOT a redirect URL. NOT a homepage.
- The URL MUST start with https:// and be a normal website URL.
- Do NOT return any URL containing "vertexaisearch" or "google.com/grounding" - those are internal redirect URLs, not real pages.
- Do NOT return just a homepage - return the specific subpage.

Examples of CORRECT URLs:
- https://www.t-mobile.com/cell-phone-plans/senior-discount-plans
- https://www.aarp.org/benefits-discounts/all/hertz/
- https://www.choicehotels.com/deals/senior-rate
- https://www.dennys.com/menu/55-plus-menu
- https://www.thekrazycouponlady.com/tips/store-hacks/senior-discounts

Examples of WRONG URLs:
- https://www.t-mobile.com (homepage only)
- https://vertexaisearch.cloud.google.com/... (redirect URL)

Format your response ONLY as a JSON object (no markdown, no extra text):
{{"url": "the full direct URL to the specific page", "source_type": "merchant_site/aarp/publication/blog"}}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
            ),
        )

        raw = response.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)
        url = result.get("url", "").strip()
        source_type = result.get("source_type", "blog").strip().lower()

        # Validate it looks like a real URL (not a redirect stub)
        if (
            url
            and url.startswith("http")
            and "vertexaisearch" not in url
            and "grounding-api-redirect" not in url
        ):
            return {"url": url, "source_type": source_type}

        return {"url": "", "source_type": ""}

    except Exception as e:
        return {"url": "", "source_type": f"error: {e}"}


def check_store_locator(
    client: genai.Client,
    merchant_name: str,
) -> Dict[str, str]:
    """
    Use Gemini with search grounding to check if a merchant has a
    scrapeable store locator on their website.

    Returns dict with:
        has_locator: "Yes" | "No" | "Unknown"
        locator_url: direct URL to the store locator page
        locator_type: description of the locator format
    """
    prompt = f"""Does {merchant_name} have a store locator or location finder on their official website?

I need to know if they have a page where users can search for nearby store locations, typically at URLs like:
- /locations
- /store-locator
- /find-a-store
- /stores
- /restaurant-locator

Check {merchant_name}'s official website for this.

Also assess whether the store locator would be scrapeable (returns structured location data like addresses, city/state, zip codes):
- "Easy" = the locator returns a list of locations with addresses visible in the HTML or a public JSON/API endpoint
- "Medium" = the locator uses JavaScript rendering but locations are in the page source or a discoverable API
- "Hard" = the locator requires interactive input (e.g. must type a zip code first with no way to enumerate)
- "None" = no store locator exists (online-only, single location, or service-based business)

RULES:
- Do NOT return any URL containing "vertexaisearch" or "grounding-api-redirect"
- Return the FULL direct URL to the store locator page

Format your response ONLY as a JSON object (no markdown, no extra text):
{{"has_locator": "Yes/No", "locator_url": "full URL or empty", "scrape_difficulty": "Easy/Medium/Hard/None", "notes": "brief note about the locator format"}}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
            ),
        )

        raw = response.text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        result = json.loads(raw)

        has_locator = result.get("has_locator", "Unknown").strip().capitalize()
        if has_locator not in ("Yes", "No"):
            has_locator = "Unknown"

        locator_url = result.get("locator_url", "").strip()
        if locator_url and "vertexaisearch" in locator_url:
            locator_url = ""

        scrape_difficulty = result.get("scrape_difficulty", "Unknown").strip()
        notes = result.get("notes", "").strip()

        return {
            "has_locator": has_locator,
            "locator_url": locator_url,
            "scrape_difficulty": scrape_difficulty,
            "notes": notes,
        }

    except Exception as e:
        return {
            "has_locator": "Unknown",
            "locator_url": "",
            "scrape_difficulty": "Unknown",
            "notes": f"error: {e}",
        }


def verify_merchant(
    client: genai.Client,
    merchant_name: str,
    claimed_discount: str,
) -> Dict[str, str]:
    """
    Use Gemini with Google Search grounding to verify a merchant's senior discount.

    Returns dict with:
        verified: "Yes" | "No" | "Unknown"
        discount_value: verified discount amount
        age_requirement: verified age requirement
        conditions: verified conditions
        confidence: "High" | "Medium" | "Low"
        verification_url: best grounding source URL
        verification_source: domain of verification source
        notes: additional details or reason for rejection
    """
    prompt = f"""Does {merchant_name} offer a senior citizen discount in the United States?

I need to verify the following claim: "{claimed_discount}"

Please respond with a structured assessment:

1. VERIFIED: Answer Yes, No, or Unknown
   - Yes = the merchant offers a senior/age-based discount. Even if details vary by location or the exact percentage differs from the claim, answer Yes if the discount fundamentally exists. Franchise variation is normal and does NOT make it Partial.
   - No = the merchant does NOT offer a senior/age-based discount. Government assistance programs (Medicaid/SNAP/EBT) do NOT count as senior discounts. If the only "discount" is a government assistance program, answer No.
   - Unknown = insufficient information to confirm or deny

2. If Yes, provide the most commonly reported details:
   - DISCOUNT_VALUE: The most common discount amount (e.g. "10%", "15% off", "$2 off", "varies by location")
   - AGE_REQUIREMENT: The most common age requirement (e.g. "55+", "60+", "65+")
   - CONDITIONS: Any conditions (e.g. "Tuesdays only", "varies by location", "must ask")
   - DISCOUNT_TYPE: "In-store", "Online", "In-store and Online", or "Plan"

3. If No, explain briefly why (e.g. "No age-based discount; only offers government assistance discount")

Format your response ONLY as a JSON object (no markdown fences, no extra text):
{{"verified": "Yes/No/Unknown", "discount_value": "", "age_requirement": "", "conditions": "", "discount_type": "", "notes": ""}}"""

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())],
                temperature=0.0,
            ),
        )

        raw = response.text.strip()
        # Strip markdown fences if present
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)

        # Parse JSON response
        result = json.loads(raw)

        # Extract grounding source URL
        verification_url = ""
        verification_source = ""
        if (
            response.candidates
            and response.candidates[0].grounding_metadata
            and response.candidates[0].grounding_metadata.grounding_chunks
        ):
            for chunk in response.candidates[0].grounding_metadata.grounding_chunks:
                if chunk.web and chunk.web.uri:
                    # The grounding URLs are redirect URLs; extract the domain from title
                    verification_url = chunk.web.uri
                    if chunk.web.title:
                        verification_source = chunk.web.title
                    break

        # Normalize verified to title case (Gemini may return "YES"/"NO"/etc.)
        verified_raw = result.get("verified", "Unknown").strip()
        verified = verified_raw.capitalize()  # "YES" -> "Yes", "NO" -> "No"
        if verified not in ("Yes", "No", "Unknown"):
            verified = "Unknown"
        result["verified"] = verified

        # Map verified status to confidence
        if verified == "Yes":
            confidence = "High"
        elif verified == "No":
            confidence = "High"  # We're confident it doesn't exist
        else:
            confidence = "Low"

        return {
            "verified": verified,
            "discount_value": result.get("discount_value", ""),
            "age_requirement": result.get("age_requirement", ""),
            "conditions": result.get("conditions", ""),
            "discount_type": result.get("discount_type", ""),
            "confidence": confidence,
            "verification_url": verification_url,
            "verification_source": verification_source,
            "notes": result.get("notes", ""),
        }

    except json.JSONDecodeError as e:
        return {
            "verified": "Unknown",
            "discount_value": "",
            "age_requirement": "",
            "conditions": "",
            "discount_type": "",
            "confidence": "Low",
            "verification_url": "",
            "verification_source": "",
            "notes": f"JSON parse error: {e}",
        }
    except Exception as e:
        return {
            "verified": "Unknown",
            "discount_value": "",
            "age_requirement": "",
            "conditions": "",
            "discount_type": "",
            "confidence": "Low",
            "verification_url": "",
            "verification_source": "",
            "notes": f"Verification error: {e}",
        }


# ---------------------------------------------------------------------------
# Requirement normalization (reuse from discover script)
# ---------------------------------------------------------------------------
def normalize_requirement(raw: str) -> str:
    """Normalize age requirement to canonical form."""
    if not raw:
        return ""
    raw_lower = raw.lower().strip()
    if "aarp" in raw_lower:
        return "AARP membership required"
    age_match = re.search(r"(\d{2})", raw_lower)
    if age_match:
        age = int(age_match.group(1))
        return f"Ages {age} and up"
    return raw.strip()


# ---------------------------------------------------------------------------
# Google Sheets I/O
# ---------------------------------------------------------------------------
def read_all_rows(sheets_service: Any, sheet_id: str) -> Tuple[List[str], List[List[str]]]:
    """Read header and all data rows from Merchant Review tab."""
    result = (
        sheets_service.spreadsheets()
        .values()
        .get(
            spreadsheetId=sheet_id,
            range="Merchant Review!A:W",
        )
        .execute()
    )
    values = result.get("values", [])
    if not values:
        return [], []
    return values[0], values[1:]


def write_row_range(
    sheets_service: Any,
    sheet_id: str,
    row_idx: int,
    row_data: List[str],
) -> None:
    """Write a single row back to the sheet (row_idx is 0-based data row)."""
    # Ensure consistent column count
    max_cols = 23  # A through W
    padded = list(row_data)
    while len(padded) < max_cols:
        padded.append("")
    padded = padded[:max_cols]

    sheet_row = row_idx + 2  # +1 for header, +1 for 1-based
    range_str = f"Merchant Review!A{sheet_row}:W{sheet_row}"
    sheets_service.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=range_str,
        valueInputOption="RAW",
        body={"values": [padded]},
    ).execute()


def color_row(
    sheets_service: Any,
    sheet_id: str,
    row_idx: int,
    status: str,
    verified: str,
) -> None:
    """Color a row based on verification result."""
    # Red for rejected (No), keep existing color for verified
    if verified == "No":
        bg = {"red": 1.0, "green": 0.85, "blue": 0.85}  # Light red
    else:
        return  # Keep existing color for Yes/Unknown

    sheet_row = row_idx + 1  # +1 for 0-based to 1-based (header is row 0 in grid)
    request = {
        "repeatCell": {
            "range": {
                "sheetId": 0,
                "startRowIndex": sheet_row,
                "endRowIndex": sheet_row + 1,
                "startColumnIndex": 0,
                "endColumnIndex": 22,
            },
            "cell": {"userEnteredFormat": {"backgroundColor": bg}},
            "fields": "userEnteredFormat.backgroundColor",
        }
    }
    sheets_service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": [request]}
    ).execute()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(
        description="Verify senior discount claims via Gemini with search grounding"
    )
    parser.add_argument("--sheet-id", required=True, help="Google Sheet ID")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview verification results without updating the sheet",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Limit number of merchants to verify (0 = all)",
    )
    parser.add_argument(
        "--start-row",
        type=int,
        default=0,
        help="Start from this data row index (0-based, for resuming)",
    )
    parser.add_argument(
        "--urls-only",
        action="store_true",
        help="Only find verification URLs for already-verified rows (skip yes/no check)",
    )
    parser.add_argument(
        "--store-locator",
        action="store_true",
        help="Check if merchants have scrapeable store locators on their websites",
    )
    args = parser.parse_args()

    if not GEMINI_API_KEY:
        print("ERROR: GEMINI_API_KEY must be set in .env")
        sys.exit(1)

    if args.store_locator:
        mode_label = "Store Locator Check"
    elif args.urls_only:
        mode_label = "URL Lookup"
    else:
        mode_label = "Full Verification"
    print("=" * 70)
    print(f"  Senior Discount {mode_label} (Gemini + Search Grounding)")
    print("=" * 70)
    print(f"  Sheet ID:   {args.sheet_id}")
    print(f"  Model:      {GEMINI_MODEL}")
    print(f"  Mode:       {mode_label}")
    print(f"  Dry run:    {args.dry_run}")
    if args.limit:
        print(f"  Limit:      {args.limit}")
    if args.start_row:
        print(f"  Start row:  {args.start_row}")
    print()

    # Initialize services
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN_PATH,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    sheets_svc = build_google("sheets", "v4", credentials=creds)

    # Read all rows
    print("STEP 1: Reading sheet data ...")
    header, rows = read_all_rows(sheets_svc, args.sheet_id)
    if not rows:
        print("  No data rows found.")
        return
    print(f"  Found {len(rows)} data rows")

    if args.store_locator:
        # --- Store locator mode: check for scrapeable store locators ---
        to_process: List[Tuple[int, List[str]]] = []
        for i, row in enumerate(rows):
            if i < args.start_row:
                continue
            status = safe_get(row, COL_STATUS).strip()
            if status not in ("New", "Existing"):
                continue
            # Skip if already checked (col W has a value)
            existing_val = safe_get(row, COL_STORE_LOCATOR).strip()
            if existing_val:
                continue
            to_process.append((i, row))

        if args.limit:
            to_process = to_process[: args.limit]

        print(f"  Rows to check: {len(to_process)}")
        print()

        # Write Store Locator header
        if not args.dry_run:
            sheets_svc.spreadsheets().values().update(
                spreadsheetId=args.sheet_id,
                range="Merchant Review!W1",
                valueInputOption="RAW",
                body={"values": [["Store Locator"]]},
            ).execute()
            # Format header
            sheets_svc.spreadsheets().batchUpdate(
                spreadsheetId=args.sheet_id,
                body={
                    "requests": [
                        {
                            "repeatCell": {
                                "range": {
                                    "sheetId": 0,
                                    "startRowIndex": 0,
                                    "endRowIndex": 1,
                                    "startColumnIndex": COL_STORE_LOCATOR,
                                    "endColumnIndex": COL_STORE_LOCATOR + 1,
                                },
                                "cell": {
                                    "userEnteredFormat": {
                                        "textFormat": {
                                            "bold": True,
                                            "foregroundColorStyle": {
                                                "rgbColor": {
                                                    "red": 1,
                                                    "green": 1,
                                                    "blue": 1,
                                                }
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
                    ]
                },
            ).execute()

        print("STEP 2: Checking store locators via Gemini ...")
        easy_count = 0
        medium_count = 0
        hard_count = 0
        none_count = 0

        for idx, (row_idx, row) in enumerate(to_process):
            name = safe_get(row, COL_NAME).strip()
            print(f"  [{idx + 1}/{len(to_process)}] {name} ... ", end="", flush=True)

            result = check_store_locator(gemini_client, name)
            has_locator = result.get("has_locator", "Unknown")
            difficulty = result.get("scrape_difficulty", "Unknown")
            locator_url = result.get("locator_url", "")
            notes = result.get("notes", "")

            # Build cell value
            if has_locator == "Yes" and locator_url:
                cell_value = f"{difficulty}: {locator_url}"
            elif has_locator == "Yes":
                cell_value = f"{difficulty}: URL not found"
            else:
                cell_value = "None"

            if difficulty == "Easy":
                easy_count += 1
            elif difficulty == "Medium":
                medium_count += 1
            elif difficulty == "Hard":
                hard_count += 1
            else:
                none_count += 1

            print(f"{difficulty}" + (f" -> {locator_url[:60]}" if locator_url else ""))

            if not args.dry_run:
                safe_set(row, COL_STORE_LOCATOR, cell_value)
                write_row_range(sheets_svc, args.sheet_id, row_idx, row)

            time.sleep(4.5)

        # Summary
        print()
        print("=" * 70)
        print("  STORE LOCATOR CHECK COMPLETE")
        print("=" * 70)
        print(f"  Total checked:     {len(to_process)}")
        print(f"  Easy to scrape:    {easy_count}")
        print(f"  Medium difficulty:  {medium_count}")
        print(f"  Hard to scrape:    {hard_count}")
        print(f"  No locator:        {none_count}")
        if args.dry_run:
            print()
            print("  DRY RUN - No changes written to sheet.")

    elif args.urls_only:
        # --- URL-only mode: find direct verification URLs for verified rows ---
        to_process: List[Tuple[int, List[str]]] = []
        for i, row in enumerate(rows):
            if i < args.start_row:
                continue
            status = safe_get(row, COL_STATUS).strip()
            # Process New (verified Yes) and Existing rows
            if status not in ("New", "Existing"):
                continue
            to_process.append((i, row))

        if args.limit:
            to_process = to_process[: args.limit]

        print(f"  Rows to find URLs for: {len(to_process)}")
        print()

        print("STEP 2: Finding verification URLs via Gemini ...")
        found = 0
        merchant_site = 0
        aarp_site = 0
        other_site = 0

        for idx, (row_idx, row) in enumerate(to_process):
            name = safe_get(row, COL_NAME).strip()
            print(f"  [{idx + 1}/{len(to_process)}] {name} ... ", end="", flush=True)

            result = find_verification_url(gemini_client, name)
            url = result.get("url", "")
            source_type = result.get("source_type", "")

            if url:
                found += 1
                if source_type == "merchant_site":
                    merchant_site += 1
                elif source_type == "aarp":
                    aarp_site += 1
                else:
                    other_site += 1
                print(f"{source_type} -> {url[:80]}")

                if not args.dry_run:
                    safe_set(row, COL_VERIF_URL, url)
                    safe_set(row, COL_VERIF_SOURCE, source_type)
                    safe_set(row, COL_CONFIDENCE, "High")
                    write_row_range(sheets_svc, args.sheet_id, row_idx, row)
            else:
                print("no URL found")

            # Rate limit
            time.sleep(4.5)

        # Summary
        print()
        print("=" * 70)
        print("  URL LOOKUP COMPLETE")
        print("=" * 70)
        print(f"  Total processed:   {len(to_process)}")
        print(f"  URLs found:        {found}")
        print(f"    Merchant site:   {merchant_site}")
        print(f"    AARP:            {aarp_site}")
        print(f"    Other:           {other_site}")
        print(f"  No URL found:      {len(to_process) - found}")
        if args.dry_run:
            print()
            print("  DRY RUN - No changes written to sheet.")

    else:
        # --- Full verification mode ---
        to_verify: List[Tuple[int, List[str]]] = []
        for i, row in enumerate(rows):
            if i < args.start_row:
                continue
            status = safe_get(row, COL_STATUS).strip()
            if status != "New":
                continue
            to_verify.append((i, row))

        if args.limit:
            to_verify = to_verify[: args.limit]

        print(f"  Rows to verify: {len(to_verify)}")
        print()

        # Verify each merchant
        print("STEP 2: Verifying merchants via Gemini ...")
        results_summary = {"Yes": 0, "No": 0, "Unknown": 0}

        for idx, (row_idx, row) in enumerate(to_verify):
            name = safe_get(row, COL_NAME).strip()
            discount_val = safe_get(row, COL_DISCOUNT_VAL).strip()
            discount_txt = safe_get(row, COL_DISCOUNT_TXT).strip()

            # Build claim description
            claim = discount_txt or discount_val or "senior discount"

            print(f"  [{idx + 1}/{len(to_verify)}] {name} ... ", end="", flush=True)

            result = verify_merchant(gemini_client, name, claim)
            verified = result["verified"]
            results_summary[verified] = results_summary.get(verified, 0) + 1

            print(f"{verified} ({result['confidence']})")
            if result.get("notes"):
                print(f"    Notes: {result['notes']}")

            if not args.dry_run:
                # Update the row with verification results
                if verified == "No":
                    safe_set(row, COL_STATUS, "Rejected")
                    safe_set(row, COL_ACTION, "Skip")
                    notes = safe_get(row, COL_NOTES)
                    rejection_note = f"Gemini: NO discount. {result.get('notes', '')}"
                    if notes:
                        safe_set(row, COL_NOTES, f"{notes}; {rejection_note}")
                    else:
                        safe_set(row, COL_NOTES, rejection_note)
                elif verified == "Yes":
                    # Update with verified data if we got better info
                    if result.get("discount_value"):
                        safe_set(row, COL_DISCOUNT_VAL, result["discount_value"])
                    if result.get("age_requirement"):
                        requirement = normalize_requirement(result["age_requirement"])
                        safe_set(row, COL_REQUIREMENT, requirement)
                        # Rebuild discount text
                        dv = safe_get(row, COL_DISCOUNT_VAL)
                        if dv:
                            safe_set(
                                row, COL_DISCOUNT_TXT,
                                f"{dv} for seniors {result['age_requirement']}"
                            )
                    if result.get("conditions"):
                        safe_set(row, COL_CONDITIONS, result["conditions"])
                    if result.get("discount_type"):
                        safe_set(row, COL_DISCOUNT_TYPE, result["discount_type"])

                # Update verification fields
                if result.get("verification_url"):
                    safe_set(row, COL_VERIF_URL, result["verification_url"])
                if result.get("verification_source"):
                    safe_set(row, COL_VERIF_SOURCE, result["verification_source"])
                safe_set(row, COL_CONFIDENCE, result["confidence"])

                # Write row back to sheet
                write_row_range(sheets_svc, args.sheet_id, row_idx, row)

                # Color rejected rows red
                if verified == "No":
                    color_row(sheets_svc, args.sheet_id, row_idx, "New", verified)

            # Rate limit: Gemini free tier is 15 RPM for 2.5 Flash
            time.sleep(4.5)

        # Summary
        print()
        print("=" * 70)
        print("  VERIFICATION COMPLETE")
        print("=" * 70)
        print(f"  Total verified:    {len(to_verify)}")
        print(f"  Confirmed (Yes):   {results_summary.get('Yes', 0)}")
        print(f"  Rejected (No):     {results_summary.get('No', 0)}")
        print(f"  Unknown:           {results_summary.get('Unknown', 0)}")
        if args.dry_run:
            print()
            print("  DRY RUN - No changes written to sheet.")


if __name__ == "__main__":
    main()
