#!/usr/bin/env python3
"""Classify merchants with NULL category_id using Claude Haiku batch classification.

Reads the merchant_categories table from Supabase, fetches all merchants where
category_id IS NULL, batches merchant names to Claude Haiku for classification,
and PATCHes each merchant's category_id.

Prerequisites:
    1. Run scripts/sql/create_merchant_categories.sql in Supabase SQL Editor first
    2. Ensure ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY in .env

Usage:
    python scripts/migrate_merchant_categories.py              # full run
    python scripts/migrate_merchant_categories.py --dry-run    # preview only
    python scripts/migrate_merchant_categories.py --batch-size 30  # smaller batches
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

try:
    import anthropic
except ImportError:
    print("Run: pip install anthropic httpx")
    sys.exit(1)

import structlog
from dotenv import load_dotenv

# ── Project imports ──────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(_PROJECT_ROOT / ".env")
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402

logger = structlog.get_logger()

# ── LLM settings ────────────────────────────────────────────────────────────
CLASSIFICATION_MODEL = "claude-haiku-4-5-20251001"
CLASSIFICATION_MAX_TOKENS = 4096
CLASSIFICATION_TEMPERATURE = 0.0
BATCH_SIZE = 50
INTER_BATCH_PAUSE = 1.0  # seconds between batches
MAX_RETRIES = 2


# ── Supabase helpers ─────────────────────────────────────────────────────────


def _headers(settings: Settings) -> Dict[str, str]:
    return {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


async def fetch_all(
    http: httpx.AsyncClient,
    settings: Settings,
    table: str,
    params: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Paginated fetch from Supabase REST API."""
    all_rows: List[Dict[str, Any]] = []
    offset = 0
    batch = 1000
    while True:
        p = dict(params or {})
        p["limit"] = str(batch)
        p["offset"] = str(offset)
        resp = await http.get(
            f"{settings.supabase_url}/rest/v1/{table}",
            headers=_headers(settings),
            params=p,
        )
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data)
        if len(data) < batch:
            break
        offset += batch
    return all_rows


async def patch_merchant(
    http: httpx.AsyncClient,
    settings: Settings,
    merchant_id: int,
    category_id: int,
) -> bool:
    """PATCH a single merchant's category_id."""
    resp = await http.patch(
        f"{settings.supabase_url}/rest/v1/merchants?id=eq.{merchant_id}",
        headers=_headers(settings),
        json={"category_id": category_id},
    )
    if resp.status_code in (200, 204):
        return True
    logger.error(
        "patch_failed",
        merchant_id=merchant_id,
        status=resp.status_code,
        body=resp.text[:300],
    )
    return False


# ── LLM classification ──────────────────────────────────────────────────────


def build_classification_prompt(
    categories: List[Dict[str, Any]],
    merchants: List[Dict[str, Any]],
) -> str:
    """Build the user prompt for batch classification."""
    cat_lines = []
    for c in categories:
        cat_lines.append(f"- {c['slug']}: {c['display_name']} - {c['description']}")
    cat_block = "\n".join(cat_lines)

    merchant_lines = []
    for m in merchants:
        merchant_lines.append(f"- id={m['id']}: {m['name']}")
    merchant_block = "\n".join(merchant_lines)

    return f"""Classify each merchant into exactly one category. Use the merchant name to determine the best-fit category.

CATEGORIES:
{cat_block}

MERCHANTS TO CLASSIFY:
{merchant_block}

Return a JSON array where each element is {{"id": <merchant_id>, "slug": "<category_slug>"}}.
Return ONLY the JSON array. No markdown fences, no extra text."""


SYSTEM_PROMPT = """You are a data classification assistant. You classify merchant/business names into standardized categories based on what the business sells or provides.

Rules:
- Every merchant MUST be assigned exactly one category
- Use the merchant name to infer the business type
- Grocery stores, supermarkets, food markets -> grocery
- Pharmacies, drugstores (CVS, Walgreens, Rite Aid) -> pharmacy
- Restaurants, fast food, pizza, cafes, bars, coffee shops -> restaurant
- Clothing, department stores, general retail, specialty shops -> retail
- Home improvement, hardware, lumber, flooring, carpet -> home-improvement
- Auto parts, tires, oil change, car repair, vehicle dealers -> auto
- Pet stores, pet food, pet grooming -> pets
- Movie theaters, museums, amusement parks, bowling, arcades -> entertainment
- Cell phone, internet, cable, telecom providers -> telecom
- Transit, bus, taxi, ride services -> transportation
- Hotels, motels, inns, lodging -> hotels-lodging
- Airlines, air travel -> airlines
- Cruise lines, travel agencies -> cruises-travel
- Thrift stores, consignment, Goodwill, Salvation Army -> thrift-secondhand
- Barber shops, hair salons, beauty supply, spas, nail salons -> beauty-personal-care
- Cannabis dispensaries -> retail
- If truly ambiguous, default to retail"""


async def classify_batch(
    client: anthropic.AsyncAnthropic,
    categories: List[Dict[str, Any]],
    merchants: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    """Classify a batch of merchants via Claude Haiku. Returns list of {id, slug}."""
    user_prompt = build_classification_prompt(categories, merchants)

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.messages.create(
                model=CLASSIFICATION_MODEL,
                max_tokens=CLASSIFICATION_MAX_TOKENS,
                temperature=CLASSIFICATION_TEMPERATURE,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = resp.content[0].text.strip()
            # Strip markdown fences
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

            results = json.loads(raw)
            if not isinstance(results, list):
                raise ValueError(f"Expected list, got {type(results)}")
            return results

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                "classification_parse_error",
                attempt=attempt,
                error=str(e)[:200],
                batch_size=len(merchants),
            )
        except Exception as e:
            logger.error(
                "classification_error",
                attempt=attempt,
                error=str(e)[:200],
            )

        if attempt < MAX_RETRIES:
            await asyncio.sleep(2)

    return []


# ── Main pipeline ────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Classify NULL-category merchants via LLM")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, skip DB writes")
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE, help="Merchants per LLM call")
    parser.add_argument("--limit", type=int, default=0, help="Max merchants to process (0=all)")
    args = parser.parse_args()

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    async with httpx.AsyncClient(timeout=60.0) as http:
        # 1. Fetch categories
        categories = await fetch_all(http, settings, "merchant_categories", {"select": "*"})
        if not categories:
            logger.error("No merchant_categories found. Run create_merchant_categories.sql first.")
            sys.exit(1)
        slug_to_id = {c["slug"]: c["id"] for c in categories}
        logger.info("loaded_categories", count=len(categories))

        # 2. Fetch merchants with NULL category_id
        merchants = await fetch_all(
            http, settings, "merchants",
            {"select": "id,name,merchant_type,category_id", "category_id": "is.null", "is_active": "eq.true"},
        )
        logger.info("merchants_to_classify", count=len(merchants))

        if not merchants:
            logger.info("All merchants already have category_id. Nothing to do.")
            return

        if args.limit:
            merchants = merchants[:args.limit]
            logger.info("limited_to", count=len(merchants))

    # 3. Batch classify
    ai_client = anthropic.AsyncAnthropic()
    batches = [merchants[i:i + args.batch_size] for i in range(0, len(merchants), args.batch_size)]
    logger.info("classification_batches", count=len(batches), batch_size=args.batch_size)

    all_assignments: List[Tuple[int, int]] = []  # (merchant_id, category_id)
    unmatched: List[Dict[str, Any]] = []

    for batch_idx, batch in enumerate(batches):
        logger.info("classifying_batch", batch=f"{batch_idx + 1}/{len(batches)}", size=len(batch))

        results = await classify_batch(ai_client, categories, batch)

        for r in results:
            mid = r.get("id")
            slug = r.get("slug", "")
            cat_id = slug_to_id.get(slug)
            if mid and cat_id:
                all_assignments.append((mid, cat_id))
            else:
                unmatched.append(r)

        if batch_idx < len(batches) - 1:
            await asyncio.sleep(INTER_BATCH_PAUSE)

    logger.info(
        "classification_complete",
        assigned=len(all_assignments),
        unmatched=len(unmatched),
    )

    if unmatched:
        logger.warning("unmatched_merchants", items=unmatched[:10])

    # 4. Apply to Supabase
    if args.dry_run:
        # Print summary by category
        from collections import Counter
        cat_counts: Counter = Counter()
        for _, cat_id in all_assignments:
            cat_counts[cat_id] += 1
        id_to_slug = {v: k for k, v in slug_to_id.items()}
        logger.info("dry_run_summary")
        for cat_id, count in cat_counts.most_common():
            print(f"  {id_to_slug.get(cat_id, '?'):25s} -> {count:4d} merchants")
        print(f"\n  Total: {len(all_assignments)} would be updated")
        print(f"  Unmatched: {len(unmatched)}")
        return

    # Write assignments
    success = 0
    failed = 0
    async with httpx.AsyncClient(timeout=30.0) as http:
        for mid, cat_id in all_assignments:
            ok = await patch_merchant(http, settings, mid, cat_id)
            if ok:
                success += 1
            else:
                failed += 1

    logger.info("migration_complete", success=success, failed=failed, total=len(all_assignments))


if __name__ == "__main__":
    asyncio.run(main())
