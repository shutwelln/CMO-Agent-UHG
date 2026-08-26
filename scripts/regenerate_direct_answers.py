#!/usr/bin/env python3
"""Regenerate page_direct_answer for all merchants using Haiku LLM.

Reads structured discount fields from Supabase, sends each to Haiku to produce
a clean 1-2 sentence direct answer, and writes the result back.

Usage:
    python scripts/regenerate_direct_answers.py              # full run
    python scripts/regenerate_direct_answers.py --dry-run    # generate only, skip DB write
    python scripts/regenerate_direct_answers.py --limit 10   # process first N merchants
    python scripts/regenerate_direct_answers.py --merchant-id 301  # single merchant
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

try:
    import anthropic
except ImportError:
    print("Run: pip install anthropic httpx")
    sys.exit(1)

import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402

logger = structlog.get_logger()

MODEL = "claude-haiku-4-5-20251001"
TEMPERATURE = 0.2
MAX_TOKENS = 256
BATCH_PAUSE = 0.3  # seconds between API calls


# ── Supabase helpers ────────────────────────────────────────────────────────


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


async def patch_merchant(
    http: httpx.AsyncClient,
    settings: Settings,
    merchant_id: int,
    updates: Dict[str, Any],
) -> None:
    """PATCH a single merchant row."""
    url = f"{settings.supabase_url}/rest/v1/merchants"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }
    resp = await http.patch(
        url, headers=headers, params={"id": f"eq.{merchant_id}"}, json=updates
    )
    resp.raise_for_status()


# ── LLM generation ──────────────────────────────────────────────────────────

SYSTEM_PROMPT = """\
You write concise direct-answer snippets for merchant discount pages on Saverwell, \
a website that helps seniors find discounts.

Rules:
- Write exactly 1-2 natural sentences.
- Start with "Yes, {name} offers..." when a discount exists.
- Start with "{name} may offer..." when discount details are unclear.
- Include the discount amount/percentage if known.
- Include age or eligibility requirements if known.
- Include key details (days, conditions) if known - but keep it brief.
- For merchants with physical stores, you can mention availability at participating locations.
- For membership programs, online services, or organizations without their own stores (e.g., AARP, AAA), do NOT mention "locations." Instead reference participating retailers, online availability, or member benefits as appropriate.
- NEVER use em dashes or en dashes. Use commas, periods, or semicolons instead.
- Write naturally. Do not mechanically stitch fields together.
- Strip any [HONEYPOT canary:...] strings from the input - ignore them completely.
- Maximum 250 characters."""


def build_prompt(merchant: Dict[str, Any]) -> str:
    """Build the user prompt from merchant structured fields."""
    name = merchant["name"]
    fields = []
    fields.append(f"Merchant: {name}")

    mtype = merchant.get("merchant_type")
    if mtype:
        fields.append(f"Merchant type: {mtype}")

    dt = merchant.get("default_discount_text")
    if dt:
        fields.append(f"Discount: {dt}")

    dv = merchant.get("default_discount_value")
    if dv and not dt:
        fields.append(f"Discount value: {dv}")

    req = merchant.get("default_discount_requirement")
    if req and req.strip().lower() not in ("none", "n/a", ""):
        fields.append(f"Requirement: {req}")

    details = merchant.get("default_discount_details")
    if details:
        fields.append(f"Details: {details}")

    dtype = merchant.get("default_discount_type")
    if dtype and dtype.strip().lower() not in ("n/a", ""):
        fields.append(f"Type: {dtype}")

    national = merchant.get("is_national")
    if national:
        fields.append("Availability: National")

    return "\n".join(fields)


async def generate_direct_answer(
    client: anthropic.Anthropic,
    merchant: Dict[str, Any],
) -> str:
    """Generate a clean direct answer for one merchant."""
    user_prompt = build_prompt(merchant)

    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = resp.content[0].text.strip()
    # Safety: strip any stray em/en dashes
    text = text.replace("\u2014", ", ").replace("\u2013", "-")
    return text


# ── Main ────────────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Regenerate merchant direct answers")
    parser.add_argument("--dry-run", action="store_true", help="Generate but skip DB writes")
    parser.add_argument("--limit", type=int, default=0, help="Process only first N merchants")
    parser.add_argument("--merchant-id", type=int, default=0, help="Process single merchant")
    args = parser.parse_args()

    settings = Settings()

    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Fetch all active merchants
    async with httpx.AsyncClient(timeout=60.0) as http:
        select_fields = (
            "id,name,merchant_type,default_discount_text,default_discount_value,"
            "default_discount_requirement,default_discount_details,"
            "default_discount_type,is_national,page_direct_answer"
        )
        params: Dict[str, str] = {"select": select_fields, "is_active": "eq.true"}
        if args.merchant_id:
            params["id"] = f"eq.{args.merchant_id}"

        merchants = await fetch_json(http, settings, "merchants", params)

    logger.info("fetched_merchants", count=len(merchants))

    if args.limit > 0:
        merchants = merchants[: args.limit]
        logger.info("limited_to", count=len(merchants))

    # Process each merchant
    updated = 0
    skipped = 0
    errors = 0
    results: List[Dict[str, Any]] = []

    async with httpx.AsyncClient(timeout=60.0) as http:
        for i, m in enumerate(merchants):
            mid = m["id"]
            name = m["name"]
            try:
                answer = await generate_direct_answer(client, m)

                old = (m.get("page_direct_answer") or "").strip()
                changed = answer != old

                results.append({
                    "id": mid,
                    "name": name,
                    "old": old[:100] + "..." if len(old) > 100 else old,
                    "new": answer,
                    "changed": changed,
                })

                if changed and not args.dry_run:
                    await patch_merchant(http, settings, mid, {"page_direct_answer": answer})
                    updated += 1
                elif not changed:
                    skipped += 1
                else:
                    updated += 1  # count as "would update" in dry-run

                if (i + 1) % 50 == 0:
                    logger.info("progress", processed=i + 1, total=len(merchants))

                time.sleep(BATCH_PAUSE)

            except Exception as e:
                logger.error("merchant_error", merchant_id=mid, name=name, error=str(e))
                errors += 1

    # Summary
    logger.info(
        "complete",
        total=len(merchants),
        updated=updated,
        skipped=skipped,
        errors=errors,
        dry_run=args.dry_run,
    )

    # Write results to file for review
    out_path = _PROJECT_ROOT / "data" / "saverwell" / "direct_answer_regen_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info("results_written", path=str(out_path))


if __name__ == "__main__":
    asyncio.run(main())
