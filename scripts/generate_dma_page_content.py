#!/usr/bin/env python3
"""Generate Saverwell DMA landing page content and upsert to Supabase.

Processes all 210 DMAs from the Zip_County_DMA table. Re-runnable:
only DMAs without a row in dma_page_content get processed.

Usage:
    python scripts/generate_dma_page_content.py              # full run
    python scripts/generate_dma_page_content.py --dry-run    # generate + validate, skip upsert
    python scripts/generate_dma_page_content.py --limit 5    # process only first N DMAs
    python scripts/generate_dma_page_content.py --dma "PHOENIX (PRESCOTT)"  # single DMA
    python scripts/generate_dma_page_content.py --top-only   # only DMAs with 100+ locations
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx

try:
    import anthropic
except ImportError:
    print("Run: pip install anthropic httpx")
    sys.exit(1)

import structlog

# ── Project imports ──────────────────────────────────────────────────────────
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402

logger = structlog.get_logger()

# ── Paths ────────────────────────────────────────────────────────────────────
BRAND_VOICE_PATH = _PROJECT_ROOT / "data" / "brand_voices" / "saverwell.txt"
DRAFTS_DIR = _PROJECT_ROOT / "data" / "saverwell" / "dma_page_drafts"

# ── LLM settings ────────────────────────────────────────────────────────────
GENERATION_MODEL = "claude-haiku-4-5-20251001"
GENERATION_TEMPERATURE = 0.4
GENERATION_MAX_TOKENS = 4096
MAX_RETRIES = 2
INTER_DMA_PAUSE = 1.0  # seconds between DMAs

# ── Cross-link inventory ────────────────────────────────────────────────────
# Universally relevant protection articles (applicable to any geography)
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

# ── State-to-region mapping for content flavor ──────────────────────────────
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


# ── Data models ──────────────────────────────────────────────────────────────


@dataclass
class DMAContext:
    """All data needed to generate a DMA page."""
    dma_description: str
    display_name: str
    slug: str
    state_codes: List[str]
    county_names: List[str]
    zip_count: int
    location_count: int
    merchant_count: int
    discount_location_count: int
    top_merchants: List[Dict[str, Any]]  # name, location_count, discount_value
    coverage_tier: str  # full, emerging
    region: str
    protection_slugs: List[str]
    guide_slugs: List[str]


def slugify_dma(dma_desc: str) -> str:
    """Convert DMA description to URL slug.

    Matches the frontend ``createSlug()`` in external-supabase.ts so that
    ``/dma/:slug`` routes resolve correctly.
    """
    s = dma_desc.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s


def format_dma_display_name(dma_desc: str, states: List[str]) -> str:
    """Create human-readable DMA name."""
    # Clean up raw DMA description
    name = dma_desc.title()
    # Fix common patterns
    name = re.sub(r"\s*\(\s*", " (", name)
    name = re.sub(r"\s*\)\s*", ") ", name).strip()
    # Replace hyphens with &
    name = re.sub(r"\s*-\s*", " & ", name)
    # Remove double spaces
    name = re.sub(r"\s+", " ", name).strip()
    # Clean up parenthetical abbreviations
    name = re.sub(r"\s*\(([^)]+)\)", lambda m: f" ({m.group(1).title()})", name)

    if states:
        state_str = ", ".join(states[:2])
        if len(states) > 2:
            state_str += f" + {len(states) - 2} more"
        return f"{name}, {state_str}"
    return name


# ── Supabase helpers ─────────────────────────────────────────────────────────


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


async def gather_dma_contexts(
    settings: Settings,
    dma_filter: Optional[str] = None,
    top_only: bool = False,
    force: bool = False,
) -> List[DMAContext]:
    """Query Supabase and build DMAContext for each DMA."""

    async with httpx.AsyncClient(timeout=120.0) as http:
        # 1. Fetch Zip_County_DMA mapping
        logger.info("fetching_zip_county_dma")
        zips_raw = await fetch_json(
            http, settings, "Zip_County_DMA",
            {"select": "zip,county_name,state_code,DMA_description"},
        )

        # Build DMA → zips/counties/states
        from collections import defaultdict, Counter
        dma_zips: Dict[str, Set[str]] = defaultdict(set)
        dma_counties: Dict[str, Set[str]] = defaultdict(set)
        dma_states: Dict[str, Counter] = defaultdict(Counter)
        zip_to_dma: Dict[str, str] = {}

        for r in zips_raw:
            dma = r.get("DMA_description")
            if not dma:
                continue
            z = str(r["zip"])  # normalize to string (DMA table stores int)
            dma_zips[dma].add(z)
            zip_to_dma[z] = dma
            if r.get("county_name"):
                dma_counties[dma].add(r["county_name"])
            if r.get("state_code"):
                dma_states[dma][r["state_code"]] += 1

        all_dmas = sorted(dma_zips.keys())
        logger.info("dmas_found", count=len(all_dmas))

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

        # 3. Fetch store locations for location counts per DMA
        logger.info("fetching_store_locations")
        enriched = await fetch_json(
            http, settings, "store_locations_with_effective_discount_enriched",
            {"select": "merchant_id,merchant_name,zip"},
        )

        # Map locations to DMAs
        dma_locations: Dict[str, List[Dict]] = defaultdict(list)
        for loc in enriched:
            z = loc.get("zip", "")
            # Handle zip+4 format
            z_short = z.split("-")[0] if z else ""
            dma = zip_to_dma.get(z) or zip_to_dma.get(z_short)
            if dma:
                dma_locations[dma].append(loc)

        # 4. Check which DMAs already have content
        logger.info("checking_existing_content")
        existing_raw = await fetch_json(
            http, settings, "dma_page_content",
            {"select": "dma_description"},
        )
        existing_dmas = {r["dma_description"] for r in existing_raw}

        # 5. Build contexts
        contexts = []
        for dma in all_dmas:
            if dma_filter and dma != dma_filter:
                continue
            if not force and dma in existing_dmas:
                logger.info("skipping_has_content", dma=dma)
                continue

            locs = dma_locations.get(dma, [])
            location_count = len(locs)

            if top_only and location_count < 100:
                continue

            # Count locations per merchant
            merch_counter: Counter = Counter()
            discount_count = 0
            for loc in locs:
                mid = loc.get("merchant_name", "Unknown")
                merch_counter[mid] += 1
                # Count merchants that have a default discount
                defaults = merchant_defaults.get(mid, {})
                if defaults.get("default_discount_value") or defaults.get("default_discount_text"):
                    discount_count += 1

            # Top merchants using defaults from merchants table
            top_merchants = []
            for mname, cnt in merch_counter.most_common(10):
                defaults = merchant_defaults.get(mname, {})
                discount_display = (
                    defaults.get("default_discount_text", "")
                    or defaults.get("default_discount_value", "")
                )
                top_merchants.append({
                    "name": mname,
                    "location_count": cnt,
                    "discount_value": discount_display,
                })

            states = [s for s, _ in dma_states[dma].most_common()]
            counties = sorted(dma_counties[dma])[:20]  # cap for very large DMAs
            region = STATE_REGIONS.get(states[0], "United States") if states else "United States"

            coverage_tier = "full" if location_count >= 10 else "emerging"

            # Pick protection slugs (rotate through the universal list)
            idx = hash(dma) % (len(UNIVERSAL_PROTECTION_SLUGS) - 2)
            protection_slugs = UNIVERSAL_PROTECTION_SLUGS[idx:idx + 3]

            ctx = DMAContext(
                dma_description=dma,
                display_name=format_dma_display_name(dma, states),
                slug=slugify_dma(dma),
                state_codes=states,
                county_names=counties,
                zip_count=len(dma_zips[dma]),
                location_count=location_count,
                merchant_count=len(merch_counter),
                discount_location_count=discount_count,
                top_merchants=top_merchants,
                coverage_tier=coverage_tier,
                region=region,
                protection_slugs=protection_slugs,
                guide_slugs=UNIVERSAL_GUIDE_SLUGS[:2],
            )
            contexts.append(ctx)

    # Sort by location count descending (process biggest DMAs first)
    contexts.sort(key=lambda c: -c.location_count)
    return contexts


# ── Prompt building ──────────────────────────────────────────────────────────


def build_system_prompt() -> str:
    """Build the system prompt with brand voice."""
    brand_voice = BRAND_VOICE_PATH.read_text() if BRAND_VOICE_PATH.exists() else ""

    return f"""You are a senior content writer for Saverwell, a free platform helping Americans aged 60+ find verified senior discounts, stay protected from financial threats, and access expert guides on topics like Medicare and insurance.

{brand_voice}

YOUR TASK: Generate structured page content for a DMA (Designated Market Area) landing page on Saverwell.com. This page will rank in search for queries like "senior discounts in [City]", "senior discounts near [City]", "[City] senior discount stores".

CRITICAL SEO RULES:
- The hero_headline MUST include the area name and "Senior Discounts" (e.g., "Senior Discounts in Phoenix & Prescott")
- The seo_title MUST follow: "Senior Discounts in [Area] [State] 2026 - [Count] Stores with Verified Discounts | Saverwell"
- The seo_description MUST be 150-160 characters and mention the area, store count, and that discounts are free/verified
- FAQ questions MUST match real local search queries (People Also Ask format)
- Use natural language, not keyword stuffing

GEO (GENERATIVE ENGINE OPTIMIZATION) DIRECTIVES:
- Cite authoritative local sources by name (e.g., "According to the U.S. Census Bureau, the Phoenix metro has over 1.2 million residents aged 60+")
- Include at least one statistic with a named source per major content section (intro, savings spotlight, local tips)
- Reference known organizations: AARP, Area Agency on Aging, local Chamber of Commerce, state Department of Aging, U.S. Census Bureau
- Use authoritative, factual tone - AI engines prioritize content that cites sources and includes verifiable data
- Statistics increase AI engine citation rates by ~30% and source citations by ~40% (Princeton GEO research)

DIRECT ANSWER REQUIREMENT:
- Produce a "direct_answer" field: a concise 40-60 word paragraph that directly answers "Where can seniors get discounts in [Area]?"
- This block is extracted by featured snippets and AI answer engines - it must stand alone as a complete answer
- Include the area name, approximate number of stores, and 2-3 top merchant names

CONTENT RULES:
- Short paragraphs (2-3 sentences max)
- Bullet points for lists
- NEVER use em dashes or en dashes. Use commas, periods, semicolons, or " - " (spaced hyphen) instead
- NEVER bold words mid-sentence. Bolding is only for section headers or standalone labels
- Use "seniors", "retirees" - NEVER "elderly" or "old folks"
- Reference real merchant names from the provided data
- Make local_tips feel genuinely local - reference the region, climate, culture
- protection_callout should feel relevant to the area, not generic
- If location/merchant count is low, keep content proportional - don't oversell thin coverage
- Every section must reference at least one named data source (Census, AARP, local org, etc.)

OUTPUT: Return valid JSON matching the schema exactly. No markdown fences, no extra text."""


def build_user_prompt(ctx: DMAContext) -> str:
    """Build the user prompt with DMA-specific data."""

    merchants_text = ""
    for m in ctx.top_merchants[:8]:
        disc = f" ({m['discount_value']})" if m.get("discount_value") else ""
        merchants_text += f"\n  - {m['name']}: {m['location_count']} locations{disc}"

    counties_text = ", ".join(ctx.county_names[:10])
    if len(ctx.county_names) > 10:
        counties_text += f" + {len(ctx.county_names) - 10} more"

    return f"""Generate DMA landing page content for: {ctx.display_name}

DMA DATA:
- DMA: {ctx.dma_description}
- Display name: {ctx.display_name}
- Region: {ctx.region}
- States: {', '.join(ctx.state_codes)}
- Counties: {counties_text}
- ZIP codes: {ctx.zip_count:,}
- Total store locations: {ctx.location_count:,}
- Distinct merchants: {ctx.merchant_count}
- Locations with verified discounts: {ctx.discount_location_count:,}
- Coverage tier: {ctx.coverage_tier}

TOP MERCHANTS IN THIS DMA:{merchants_text}

Return a JSON object with these exact keys:

{{
  "direct_answer": "A concise 40-60 word paragraph that directly answers: Where can seniors get discounts in {ctx.display_name}? Must include the area name, approximate store count, and 2-3 top merchant names. This is extracted by featured snippets and AI engines.",
  "hero_headline": "Short headline with area name + Senior Discounts (max 60 chars)",
  "hero_subhead": "One sentence about finding discounts in this area (max 140 chars)",
  "intro_md": "2-3 paragraphs introducing this market. Mention the area, the number of merchants, and why Saverwell is useful here. Reference specific merchants. Cite at least one authoritative source (e.g., U.S. Census Bureau population data, AARP). Markdown format.",
  "savings_spotlight_md": "1-2 paragraphs highlighting the top savings opportunities in this area. Name specific merchants and their discounts. Include a statistic with source. Markdown format with ## heading.",
  "local_tips_md": "3-5 bullet points with local savings tips. Reference the region, climate, or local shopping culture. Should feel like a local wrote it. Reference a local organization or resource. Markdown with ## heading.",
  "protection_callout_md": "1-2 paragraphs about staying safe from scams in this area. Reference FTC or state-specific scam data if applicable. Markdown format with ## heading.",
  "faq_md": "3-5 FAQs in this exact format:\\n\\n**Q: Question here?**\\nAnswer here.\\n\\n**Q: Next question?**\\nAnswer here.\\n\\nQuestions should match real search queries like: Where can seniors get discounts in [City]? What stores offer senior discounts in [State]? What age do you need for senior discounts in [Area]?",
  "faq_json": [
    {{"question": "Where can seniors get discounts in [Area]?", "answer": "Answer text..."}},
    {{"question": "What stores offer senior discounts in [Area]?", "answer": "Answer text..."}},
    {{"question": "What age qualifies for senior discounts in [Area]?", "answer": "Answer text..."}}
  ],
  "seo_title": "Senior Discounts in [Area] [State] 2026 - [Count] Stores with Verified Discounts | Saverwell",
  "seo_description": "150-160 char meta description with area name, merchant count, and free/verified positioning",
  "seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}}

IMPORTANT: The faq_json array must contain the same questions and answers as faq_md, but in structured JSON format for FAQPage schema markup. Each object needs "question" and "answer" string fields.

Return ONLY the JSON object. No markdown fences."""


# ── Quality validation ────────────────────────────────────────────────────────


def validate_content(data: Dict[str, Any], label: str) -> List[str]:
    """Validate generated content and return a list of warnings."""
    warnings: List[str] = []

    # Em dash / en dash check across all text fields
    text_fields = [
        "intro_md", "savings_spotlight_md", "local_tips_md",
        "protection_callout_md", "faq_md", "hero_headline", "hero_subhead",
        "direct_answer",
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

    # FAQ count
    faq_json = data.get("faq_json", [])
    if isinstance(faq_json, list) and len(faq_json) < 3:
        warnings.append(f"[{label}] faq_json has {len(faq_json)} items (min 3)")

    return warnings


# ── LLM generation ───────────────────────────────────────────────────────────


async def generate_dma_content(
    client: anthropic.AsyncAnthropic,
    ctx: DMAContext,
    system_prompt: str,
) -> Optional[Dict[str, Any]]:
    """Generate content for a single DMA."""
    user_prompt = build_user_prompt(ctx)

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("generating", dma=ctx.dma_description, attempt=attempt)
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
                "savings_spotlight_md", "local_tips_md", "protection_callout_md",
                "faq_md", "faq_json", "seo_title", "seo_description", "seo_keywords",
            ]
            missing = [k for k in required if k not in data or not data[k]]
            if missing:
                logger.warning("missing_keys", dma=ctx.dma_description, missing=missing)
                if attempt < MAX_RETRIES:
                    continue
                for k in missing:
                    if k == "seo_keywords":
                        data[k] = [f"senior discounts {ctx.display_name}"]
                    elif k == "faq_json":
                        data[k] = []
                    else:
                        data[k] = ""

            return data

        except json.JSONDecodeError as e:
            logger.error("json_parse_error", dma=ctx.dma_description, error=str(e)[:200])
        except Exception as e:
            logger.error("generation_error", dma=ctx.dma_description, error=str(e)[:200])

        if attempt < MAX_RETRIES:
            await asyncio.sleep(2)

    return None


# ── Supabase write ───────────────────────────────────────────────────────────


async def upsert_dma(
    settings: Settings,
    payload: Dict[str, Any],
) -> bool:
    """Upsert a DMA page row via Supabase REST API."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            f"{settings.supabase_url}/rest/v1/dma_page_content?on_conflict=dma_description",
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
            dma=payload.get("dma_description"),
            status=resp.status_code,
            body=resp.text[:500],
        )
        return False


# ── Cache ────────────────────────────────────────────────────────────────────


def save_draft(slug: str, payload: Dict[str, Any]) -> None:
    """Cache generated content locally."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFTS_DIR / f"{slug}.json"
    path.write_text(json.dumps(payload, indent=2))
    logger.info("draft_cached", slug=slug, path=str(path))


# ── Main pipeline ────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate DMA page content")
    parser.add_argument("--dry-run", action="store_true", help="Skip Supabase writes")
    parser.add_argument("--limit", type=int, default=0, help="Max DMAs to process")
    parser.add_argument("--dma", type=str, help="Process single DMA by description")
    parser.add_argument("--top-only", action="store_true", help="Only DMAs with 100+ locations")
    parser.add_argument("--force", action="store_true",
                        help="Regenerate DMAs that already have content (upsert)")
    args = parser.parse_args()

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    # Gather DMA data
    logger.info("gathering_dma_data")
    contexts = await gather_dma_contexts(
        settings,
        dma_filter=args.dma,
        top_only=args.top_only,
        force=args.force,
    )
    logger.info("dmas_to_process", count=len(contexts))

    if not contexts:
        logger.info("no_dmas_to_process")
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
            dma=ctx.dma_description,
            locations=ctx.location_count,
            merchants=ctx.merchant_count,
        )

        data = await generate_dma_content(client, ctx, system_prompt)
        if not data:
            logger.error("generation_failed", dma=ctx.dma_description)
            failed += 1
            continue

        # Quality validation
        content_warnings = validate_content(data, ctx.dma_description)
        all_warnings.extend(content_warnings)
        for w in content_warnings:
            logger.warning("quality_check", warning=w)

        # Build payload
        faq_json = data.get("faq_json", [])
        if not isinstance(faq_json, list):
            faq_json = []

        payload = {
            "dma_description": ctx.dma_description,
            "slug": ctx.slug,
            "display_name": ctx.display_name,
            "state_codes": ctx.state_codes,
            "county_names": ctx.county_names,
            "zip_count": ctx.zip_count,
            "location_count": ctx.location_count,
            "merchant_count": ctx.merchant_count,
            "coverage_tier": ctx.coverage_tier,
            "direct_answer": data.get("direct_answer", ""),
            "hero_headline": data["hero_headline"],
            "hero_subhead": data["hero_subhead"],
            "intro_md": data["intro_md"],
            "savings_spotlight_md": data["savings_spotlight_md"],
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
            "source": "generate_dma_page_content",
            "author": "Saverwell AI",
            "review_notes": f"Generated by {GENERATION_MODEL}",
        }

        # Cache locally
        save_draft(ctx.slug, payload)

        # Write to Supabase
        if args.dry_run:
            logger.info("dry_run_skip_write", dma=ctx.dma_description, slug=ctx.slug)
        else:
            ok = await upsert_dma(settings, payload)
            if ok:
                logger.info("upserted", dma=ctx.dma_description, slug=ctx.slug)
                success += 1
            else:
                failed += 1

        if i < len(contexts) - 1:
            await asyncio.sleep(INTER_DMA_PAUSE)

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
