#!/usr/bin/env python3
"""Generate Saverwell merchant page content and update the merchants table.

Targets merchants with 50+ active store locations that don't yet have
page content populated. Re-runnable: add new merchants, run again, and
only rows with empty page_hero_headline get processed.

Usage:
    python scripts/generate_merchant_page_content.py              # full run
    python scripts/generate_merchant_page_content.py --dry-run    # generate + validate, skip DB write
    python scripts/generate_merchant_page_content.py --limit 5    # process only first N merchants
    python scripts/generate_merchant_page_content.py --merchant-id 301  # single merchant by ID
    python scripts/generate_merchant_page_content.py --min-locations 100 # override location threshold
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
DRAFTS_DIR = _PROJECT_ROOT / "data" / "saverwell" / "merchant_page_drafts"

# ── LLM settings ────────────────────────────────────────────────────────────
GENERATION_MODEL = "claude-haiku-4-5-20251001"
GENERATION_TEMPERATURE = 0.4
GENERATION_MAX_TOKENS = 4096
MAX_RETRIES = 2
INTER_MERCHANT_PAUSE = 1.0  # seconds between merchants
MIN_LOCATIONS = 50

# ── Cross-link inventory ────────────────────────────────────────────────────
# Protection articles available for cross-linking, grouped by relevance
PROTECTION_ARTICLES = {
    "scams": [
        "5-common-scams-seniors-should-know",
        "phishing-scams-what-retirees-need-to-know",
        "tech-support-scams-what-you-need-to-know",
        "grandparent-scam-what-you-need-to-know",
        "romance-scams-what-you-need-to-know",
        "facebook-lottery-scam",
    ],
    "fraud": [
        "account-takeover-prevention",
        "bank-impostor-calls",
        "shared-verification-code-with-scammer",
        "what-to-do-if-you-suspect-youve-been-scammed",
    ],
    "identity": [
        "how-to-freeze-your-credit",
        "protecting-your-social-security-number",
        "what-to-do-after-a-data-breach",
        "medicare-identity-theft",
        "tax-identity-theft",
        "reading-your-credit-report",
    ],
    "payments": [
        "gift-card-scams",
        "charity-scams",
        "peer-to-peer-payment-scams",
        "fake-check-overpayment-scams",
        "subscription-traps-unauthorized-charges",
        "wire-transfer-fraud",
    ],
    "tech": [
        "smartphone-security-for-seniors",
        "email-account-hacked",
        "password-safety-guide",
        "how-to-spot-fake-websites",
        "two-factor-authentication-guide",
        "safe-online-shopping-tips",
    ],
}

GUIDE_ARTICLES = [
    "medicare-explained-simple-guide",
    "medicare-parts-a-b-c-d-explained",
    "save-money-medicare-premiums",
    "medicare-advantage-vs-original",
    "does-medicare-cover-dental",
    "does-medicare-cover-vision",
    "does-medicare-cover-hearing-aids",
    "does-medicare-cover-prescriptions",
    "medicare-enrollment-deadlines",
    "medicare-extra-help-prescription-savings",
    "irmaa-avoid-higher-medicare-premiums",
    "medicare-vs-medicaid-difference",
]

# Map category slugs to relevant protection article categories
CATEGORY_SLUG_PROTECTION_MAP = {
    "grocery": ["payments", "scams"],
    "pharmacy": ["identity", "scams"],
    "restaurant": ["payments", "scams"],
    "retail": ["payments", "tech"],
    "home-improvement": ["scams", "payments"],
    "auto": ["scams", "payments"],
    "pets": ["payments", "scams"],
    "entertainment": ["scams", "payments"],
    "telecom": ["tech", "identity"],
    "transportation": ["payments", "scams"],
    "hotels-lodging": ["scams", "identity"],
    "airlines": ["scams", "identity"],
    "cruises-travel": ["scams", "identity"],
    "thrift-secondhand": ["payments", "scams"],
    "beauty-personal-care": ["payments", "scams"],
}

# Default categories for merchants without a type
DEFAULT_PROTECTION_CATEGORIES = ["scams", "payments"]


# ── Data models ──────────────────────────────────────────────────────────────


@dataclass
class MerchantContext:
    """All data needed to generate a merchant page."""

    merchant_id: int
    name: str
    merchant_type: Optional[str]
    category_slug: Optional[str]
    category_id: Optional[int]
    website_url: Optional[str]
    is_national: bool
    logo_url: Optional[str]
    # Default discount data (merchants table — source of truth)
    default_discount_value: Optional[str]
    default_discount_text: Optional[str]
    default_discount_requirement: Optional[str]
    default_discount_type: Optional[str]
    default_discount_details: Optional[str]
    # Supplementary discount rows (discounts_v2)
    discounts: List[Dict[str, Any]]
    # Stats
    location_count: int
    state_count: int
    top_states: List[str]
    # Cross-links
    protection_slugs: List[str]
    guide_slugs: List[str]
    related_merchant_ids: List[int]


def slugify(name: str) -> str:
    """Convert merchant name to URL slug."""
    s = name.lower().strip()
    s = re.sub(r"[''`]", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return f"{s}-senior-discount"


def pick_protection_slugs(category_slug: Optional[str], count: int = 2) -> List[str]:
    """Pick relevant protection article slugs for a merchant category."""
    categories = CATEGORY_SLUG_PROTECTION_MAP.get(
        category_slug or "", DEFAULT_PROTECTION_CATEGORIES
    )
    slugs = []
    for cat in categories:
        for slug in PROTECTION_ARTICLES.get(cat, []):
            if slug not in slugs:
                slugs.append(slug)
            if len(slugs) >= count:
                return slugs
    return slugs[:count]


def pick_guide_slugs(category_slug: Optional[str]) -> List[str]:
    """Pick relevant guide slugs. Pharmacy/telecom -> Medicare guides."""
    if category_slug in ("pharmacy", "telecom"):
        return ["medicare-explained-simple-guide", "save-money-medicare-premiums"]
    if category_slug == "grocery":
        return ["medicare-extra-help-prescription-savings"]
    return []


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
        url = base_url
        p = dict(params or {})
        p["limit"] = str(batch)
        p["offset"] = str(offset)
        resp = await http.get(url, headers=headers, params=p)
        resp.raise_for_status()
        data = resp.json()
        all_rows.extend(data)
        if len(data) < batch:
            break
        offset += batch
    return all_rows


async def gather_merchant_contexts(
    settings: Settings,
    min_locations: int = MIN_LOCATIONS,
    merchant_id: Optional[int] = None,
    force: bool = False,
) -> List[MerchantContext]:
    """Query Supabase and build MerchantContext for each eligible merchant."""

    async with httpx.AsyncClient(timeout=60.0) as http:
        # 1. Fetch all active merchants (include category_id)
        merchants_raw = await fetch_json(
            http,
            settings,
            "merchants",
            {
                "select": "id,name,merchant_type,category_id,website_url,is_national,logo_url,page_hero_headline,default_discount_value,default_discount_text,default_discount_requirement,default_discount_type,default_discount_details",
                "is_active": "eq.true",
            },
        )
        merch_by_id = {m["id"]: m for m in merchants_raw}

        # 1b. Fetch category lookup
        cats_raw = await fetch_json(http, settings, "merchant_categories", {"select": "id,slug"})
        cat_id_to_slug = {c["id"]: c["slug"] for c in cats_raw}

        # 2. Fetch store locations for counts
        locs_raw = await fetch_json(
            http,
            settings,
            "store_locations",
            {"select": "merchant_id,location_id", "is_active": "eq.true"},
        )
        from collections import Counter

        loc_counts = Counter(r["merchant_id"] for r in locs_raw)

        # 3. Fetch locations_v2 for state info
        locations_v2 = await fetch_json(
            http,
            settings,
            "locations_v2",
            {"select": "id,state"},
        )
        loc_state = {r["id"]: r["state"] for r in locations_v2}

        # Build merchant→states mapping
        from collections import defaultdict

        merch_states: Dict[int, Counter] = defaultdict(Counter)
        for r in locs_raw:
            state = loc_state.get(r["location_id"])
            if state:
                merch_states[r["merchant_id"]][state] += 1

        # 4. Fetch all active discounts
        discs_raw = await fetch_json(
            http,
            settings,
            "discounts_v2",
            {
                "select": "merchant_id,name,details,discount_type,discount_value,requirement",
                "active": "eq.true",
            },
        )
        from collections import defaultdict as dd

        merch_discounts: Dict[int, List[Dict]] = dd(list)
        for d in discs_raw:
            merch_discounts[d["merchant_id"]].append(d)

        # 5. Filter to eligible merchants
        eligible_ids = set()
        if merchant_id:
            eligible_ids = {merchant_id}
        elif min_locations == 0:
            eligible_ids = set(merch_by_id.keys())
        else:
            for mid, cnt in loc_counts.items():
                if cnt >= min_locations:
                    eligible_ids.add(mid)

        # 6. Filter out merchants that already have page content
        contexts = []
        for mid in sorted(eligible_ids):
            m = merch_by_id.get(mid)
            if not m:
                continue
            # Skip if already has content (re-runnable check) unless --force
            if not force and m.get("page_hero_headline") and m["page_hero_headline"].strip():
                logger.info("skipping_has_content", merchant_id=mid, name=m["name"])
                continue

            state_counter = merch_states.get(mid, Counter())
            top_states = [s for s, _ in state_counter.most_common(5)]

            # Find related merchants (same category, 50+ locations, not self)
            related = []
            for oid, ocnt in loc_counts.most_common(200):
                if oid == mid or ocnt < min_locations:
                    continue
                om = merch_by_id.get(oid)
                if not om:
                    continue
                if (
                    m.get("category_id")
                    and om.get("category_id")
                    and m["category_id"] == om["category_id"]
                ):
                    related.append(oid)
                    if len(related) >= 3:
                        break
            # If no type match, just pick top 3 by location count
            if len(related) < 3:
                for oid, _ in loc_counts.most_common(200):
                    if oid == mid and oid not in related and loc_counts[oid] >= min_locations:
                        continue
                    if oid not in related and oid != mid and loc_counts[oid] >= min_locations:
                        related.append(oid)
                        if len(related) >= 3:
                            break

            cat_slug = cat_id_to_slug.get(m.get("category_id"))

            ctx = MerchantContext(
                merchant_id=mid,
                name=m["name"],
                merchant_type=m.get("merchant_type"),
                category_slug=cat_slug,
                category_id=m.get("category_id"),
                website_url=m.get("website_url"),
                is_national=bool(m.get("is_national")),
                logo_url=m.get("logo_url"),
                default_discount_value=str(m["default_discount_value"])
                if m.get("default_discount_value")
                else None,
                default_discount_text=m.get("default_discount_text"),
                default_discount_requirement=m.get("default_discount_requirement"),
                default_discount_type=m.get("default_discount_type"),
                default_discount_details=m.get("default_discount_details"),
                discounts=merch_discounts.get(mid, []),
                location_count=loc_counts.get(mid, 0),
                state_count=len(state_counter),
                top_states=top_states,
                protection_slugs=pick_protection_slugs(cat_slug),
                guide_slugs=pick_guide_slugs(cat_slug),
                related_merchant_ids=related[:3],
            )
            contexts.append(ctx)

    return contexts


# ── Prompt building ──────────────────────────────────────────────────────────


def build_system_prompt() -> str:
    """Build the system prompt with brand voice."""
    brand_voice = BRAND_VOICE_PATH.read_text() if BRAND_VOICE_PATH.exists() else ""

    return f"""You are a senior content writer for Saverwell, a free platform helping Americans aged 60+ find verified senior discounts, stay protected from financial threats, and access expert guides on topics like Medicare and insurance.

{brand_voice}

YOUR TASK: Generate structured page content for a merchant's senior discount page on Saverwell.com. This page will rank in search for queries like "[Merchant] senior discount", "[Merchant] senior discount age", "does [Merchant] have a senior discount".

CRITICAL SEO RULES:
- The hero_headline MUST contain the merchant name and "Senior Discount" (e.g., "Walgreens Senior Discount")
- The seo_title MUST follow this format: "[Merchant] Senior Discount 2026 - Age, Amount & Locations | Saverwell"
- Use natural language, not keyword stuffing

GEO (GENERATIVE ENGINE OPTIMIZATION) DIRECTIVES:
- Cite the merchant's official discount policy where possible (e.g., "According to Walgreens' senior savings program...")
- Reference AARP or senior organization partnerships if applicable
- Include verifiable statistics: number of locations, states served
- Use authoritative, factual tone - AI engines prioritize content with named sources and verifiable data
- If the merchant partners with AARP, Medicare, or other senior programs, name those partnerships explicitly

DISCOUNT NUMBERS IN CONTENT:
- You may reference discount amounts naturally if you know them from general knowledge.
- Our system will automatically verify and correct any percentages post-generation.
- Focus on writing helpful narrative content about the merchant and how seniors benefit.

CONTENT RULES:
- Short paragraphs (2-3 sentences max)
- Bullet points for lists
- NEVER use em dashes or en dashes. Use commas, periods, semicolons, or " - " (spaced hyphen) instead
- NEVER bold words mid-sentence. Bolding is only for section headers or standalone labels
- Use "seniors", "retirees" - NEVER "elderly" or "old folks"
- If the merchant is described as having no known discount, focus on general savings tips

OUTPUT: Return valid JSON matching the schema exactly. No markdown fences, no extra text."""


def build_user_prompt(ctx: MerchantContext) -> str:
    """Build the user prompt with merchant-specific data.

    The LLM no longer sees discount numbers. It writes narrative content using
    placeholder tokens that get resolved from verified DB fields post-generation.
    """
    has_discount = bool(ctx.default_discount_text or ctx.default_discount_value)

    states_text = ", ".join(ctx.top_states) if ctx.top_states else "nationwide"

    if ctx.location_count > 0:
        location_line = f"- Active store locations: {ctx.location_count:,}"
        states_line = f"- States: {ctx.state_count} states (top: {states_text})"
    else:
        location_line = (
            "- Active store locations: Online or limited locations (no physical stores tracked yet)"
        )
        states_line = "- States: Available online or at select locations"

    discount_context = (
        "This merchant offers a verified senior discount. Write about the merchant "
        "and how seniors can take advantage of savings."
        if has_discount
        else "No specific discount data is available for this merchant. "
        "Write general savings content and tips for shopping here as a senior."
    )

    return f"""Generate merchant page content for: {ctx.name}

MERCHANT DATA:
- Name: {ctx.name}
- Category: {ctx.category_slug or ctx.merchant_type or "General retail"}
- National chain: {ctx.is_national}
{location_line}
{states_line}
- Website: {ctx.website_url or "N/A"}

DISCOUNT CONTEXT: {discount_context}

Return a JSON object with these exact keys:

{{
  "page_hero_headline": "Short headline, must include merchant name + Senior Discount (max 60 chars)",
  "page_about_md": "2-3 paragraphs about this merchant's senior discount program. Do NOT repeat specific discount percentages, age requirements, or discount details - those are displayed elsewhere on the page. Focus on the merchant story, shopping experience, and why seniors benefit. Cite the merchant's official policy or known partnerships (AARP, etc.) by name. Markdown format.",
  "page_how_to_save_md": "Numbered step-by-step instructions for claiming the discount at this merchant. 3-5 steps. Markdown format with ## heading.",
  "page_tips_md": "3-5 specific savings tips for this merchant. Bullet points. Include at least one tip referencing a verifiable fact (number of locations, states, etc.). Markdown format with ## heading.",
  "page_protection_note_md": "1-2 paragraph fraud awareness note relevant to shopping at this type of merchant. Reference FTC or BBB data on common scams for this category. Markdown format.",
  "page_seo_title": "{ctx.name} Senior Discount 2026 - Age, Amount & Locations | Saverwell",
  "page_seo_keywords": ["keyword1", "keyword2", "keyword3", "keyword4", "keyword5"]
}}

Return ONLY the JSON object. No markdown fences."""


# ── Quality validation ────────────────────────────────────────────────────────


def validate_content(data: Dict[str, Any], label: str) -> List[str]:
    """Validate generated content and return a list of warnings."""
    warnings: List[str] = []

    # Em dash / en dash check across LLM-generated text fields
    text_fields = [
        "page_about_md",
        "page_how_to_save_md",
        "page_tips_md",
        "page_protection_note_md",
        "page_hero_headline",
    ]
    for fld in text_fields:
        val = data.get(fld, "")
        if "\u2014" in val or "\u2013" in val:
            warnings.append(f"[{label}] {fld} contains em/en dash")

    # SEO title length (max ~70 chars)
    seo_title = data.get("page_seo_title", "")
    if len(seo_title) > 80:
        warnings.append(f"[{label}] page_seo_title long ({len(seo_title)} chars, max ~70)")

    # About minimum word count
    about = data.get("page_about_md", "")
    if len(about.split()) < 50:
        warnings.append(f"[{label}] page_about_md short ({len(about.split())} words, min 50)")

    return warnings


def _format_requirement_clause(req: Optional[str]) -> str:
    """Format a discount requirement as a natural sentence clause.

    Returns a complete clause ready to insert after "offers {discount}":
    - Age-style ("55+") -> "for customers aged 55+"
    - Instruction-style ("Must show valid ID") -> ". Customers must show valid ID"
    - Named group ("AARP members") -> "for AARP members"
    - "Ages 65 and up" -> "for customers ages 65 and up"

    Returns empty string if no requirement.
    """
    if not req:
        return ""
    r = req.strip()
    lower = r.lower()
    # Age-style: "55+", "60+ years"
    if re.match(r"^\d{2}\+", r):
        return f" for customers aged {r}"
    # "Ages 65 and up" style
    if lower.startswith("ages ") or lower.startswith("age "):
        return f" for customers {lower}"
    # Instruction-style: "Must show...", "Requires...", "Need..."
    if lower.startswith(("must ", "requires ", "need ", "show ")):
        return f". {r[0].upper()}{r[1:]}"
    # Named group: "AARP members", "veterans", etc.
    return f" for {r}"


def _short_discount_summary(text: Optional[str], threshold: int = 80) -> Optional[str]:
    """Extract a concise discount summary from potentially long text.

    If `text` is short (<=threshold chars), return it as-is.
    If long, extract the first sentence. Returns None if text is empty.
    """
    if not text or not text.strip():
        return None
    t = text.strip()
    if len(t) <= threshold:
        return t
    # Extract first sentence (split on ". " or "." at end)
    m = re.match(r"^(.+?\.)\s", t)
    if m:
        return m.group(1)
    # Fallback: if no sentence boundary, truncate at threshold word boundary
    truncated = t[:threshold].rsplit(" ", 1)[0]
    return truncated + "..."


def build_direct_answer(ctx: MerchantContext) -> str:
    """Build the direct-answer snippet from structured discount data."""
    name = ctx.name
    if not ctx.default_discount_text and not ctx.default_discount_value:
        return (
            f"{name} may offer savings opportunities for seniors. "
            f"Visit your local {name} or check their website for current "
            f"senior discount availability and requirements."
        )
    summary = _short_discount_summary(ctx.default_discount_text)
    discount = summary or f"{ctx.default_discount_value} off"
    req = _format_requirement_clause(ctx.default_discount_requirement)
    details = f" {ctx.default_discount_details}" if ctx.default_discount_details else ""
    dtype = ctx.default_discount_type or ""
    where = f" {dtype.lower()}" if dtype and dtype.lower() not in ("n/a", "") else ""
    return (
        f"Yes, {name} offers {discount}{req}.{details} "
        f"The discount is available{where} at participating locations."
    ).strip()


def build_hero_subhead(ctx: MerchantContext) -> str:
    """Build the hero subhead from structured discount data.

    Uses first sentence only when default_discount_text is long (>80 chars)
    to keep the subtitle as a short one-liner.
    """
    if ctx.default_discount_text:
        summary = _short_discount_summary(ctx.default_discount_text)
        if summary:
            return f"{summary} at {ctx.name}."
    if ctx.default_discount_value:
        return f"Save {ctx.default_discount_value} at {ctx.name} with their senior discount."
    return f"Find senior savings at {ctx.name}."


def build_seo_description(ctx: MerchantContext) -> str:
    """Build a 150-160 char meta description from structured data.

    Uses first sentence of discount text when long to produce clean
    descriptions instead of truncating mid-sentence.
    """
    name = ctx.name
    if ctx.default_discount_text:
        summary = _short_discount_summary(ctx.default_discount_text)
        base = f"{name} offers {summary}"
    elif ctx.default_discount_value:
        base = f"{name} offers {ctx.default_discount_value} off for seniors"
    else:
        base = f"Find senior discount details for {name}"
    req = f" ({ctx.default_discount_requirement})" if ctx.default_discount_requirement else ""
    suffix = ". See eligibility, how to save, and locations on Saverwell."
    desc = f"{base}{req}{suffix}"
    # Trim to ~160 chars at a word boundary
    if len(desc) > 160:
        desc = desc[:157].rsplit(" ", 1)[0] + "..."
    return desc


def build_faq_json(ctx: MerchantContext) -> List[Dict[str, str]]:
    """Build structured FAQ entries from discount data."""
    name = ctx.name
    faqs: List[Dict[str, str]] = []

    # Q1: Age requirement
    if ctx.default_discount_requirement:
        req_clause = _format_requirement_clause(ctx.default_discount_requirement)
        faqs.append(
            {
                "question": f"What age do you need for {name} senior discount?",
                "answer": f"{name}'s senior discount is available{req_clause}.",
            }
        )
    else:
        faqs.append(
            {
                "question": f"What age do you need for {name} senior discount?",
                "answer": (
                    f"Age requirements for {name}'s senior discount may vary by location. "
                    f"Check with your local store for specific eligibility details."
                ),
            }
        )

    # Q2: How much
    discount_summary = _short_discount_summary(ctx.default_discount_text) or (
        f"{ctx.default_discount_value} off" if ctx.default_discount_value else None
    )
    if discount_summary:
        faqs.append(
            {
                "question": f"How much is {name} senior discount?",
                "answer": f"{name} offers {discount_summary} for eligible seniors.",
            }
        )

    # Q3: Availability / type
    if ctx.default_discount_type:
        faqs.append(
            {
                "question": f"How do I get the {name} senior discount?",
                "answer": (
                    f"The {name} senior discount is available {ctx.default_discount_type.lower()}. "
                    f"Ask a team member at checkout or check their website for details."
                ),
            }
        )

    # Q4: Special days / details
    if ctx.default_discount_details:
        faqs.append(
            {
                "question": f"When is the {name} senior discount available?",
                "answer": f"{ctx.default_discount_details}",
            }
        )

    return faqs


def build_faq_md(faqs: List[Dict[str, str]]) -> str:
    """Convert FAQ JSON list to markdown format."""
    parts: List[str] = []
    for faq in faqs:
        parts.append(f"**Q: {faq['question']}**\n{faq['answer']}")
    return "\n\n".join(parts)


def resolve_placeholders(text: str, ctx: MerchantContext) -> str:
    """Replace placeholder tokens with verified discount data.

    Also corrects hallucinated percentages: if the LLM wrote a specific
    percentage that differs from the source, swap it to the correct value.
    """
    # 1. Replace any placeholder tokens the LLM actually used
    replacements = {
        "{{DISCOUNT_SUMMARY}}": ctx.default_discount_text or "senior discount",
        "{{DISCOUNT_VALUE}}": ctx.default_discount_value or "discount",
        "{{DISCOUNT_REQUIREMENT}}": ctx.default_discount_requirement or "eligible seniors",
        "{{DISCOUNT_TYPE}}": ctx.default_discount_type or "in-store",
    }
    for token, value in replacements.items():
        text = text.replace(token, value)

    # 2. Fix hallucinated percentages - the LLM may write numbers from
    #    general knowledge that differ from the DB source of truth.
    source_text = f"{ctx.default_discount_value or ''} {ctx.default_discount_text or ''}"
    source_pcts = set(re.findall(r"(\d+)%", source_text))
    if source_pcts:
        page_pcts = set(re.findall(r"(\d+)%", text))
        wrong_pcts = page_pcts - source_pcts
        if wrong_pcts and len(source_pcts) == 1:
            correct = source_pcts.pop()
            for bad in wrong_pcts:
                text = text.replace(f"{bad}%", f"{correct}%")

    return text


# ── LLM generation ───────────────────────────────────────────────────────────


async def generate_merchant_content(
    client: anthropic.AsyncAnthropic,
    ctx: MerchantContext,
    system_prompt: str,
) -> Optional[Dict[str, Any]]:
    """Generate content for a single merchant."""
    user_prompt = build_user_prompt(ctx)

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("generating", merchant=ctx.name, attempt=attempt)
        try:
            resp = await client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=GENERATION_MAX_TOKENS,
                temperature=GENERATION_TEMPERATURE,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            raw = resp.content[0].text.strip()
            # Strip markdown fences if model wraps them
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)

            data = json.loads(raw)

            # Validate required keys (reduced - SEO fields built from templates)
            required = [
                "page_hero_headline",
                "page_about_md",
                "page_how_to_save_md",
                "page_tips_md",
                "page_protection_note_md",
                "page_seo_title",
                "page_seo_keywords",
            ]
            missing = [k for k in required if k not in data or not data[k]]
            if missing:
                logger.warning("missing_keys", merchant=ctx.name, missing=missing)
                if attempt < MAX_RETRIES:
                    continue
                # On last attempt, fill gaps
                for k in missing:
                    if k == "page_seo_keywords":
                        data[k] = [f"{ctx.name} senior discount"]
                    elif k == "page_faq_json":
                        data[k] = []
                    else:
                        data[k] = ""

            return data

        except json.JSONDecodeError as e:
            logger.error("json_parse_error", merchant=ctx.name, error=str(e)[:200])
        except Exception as e:
            logger.error("generation_error", merchant=ctx.name, error=str(e)[:200])

        if attempt < MAX_RETRIES:
            await asyncio.sleep(2)

    return None


# ── Supabase write ───────────────────────────────────────────────────────────


async def update_merchant(
    settings: Settings,
    merchant_id: int,
    payload: Dict[str, Any],
) -> bool:
    """PATCH the merchants row with page content."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.patch(
            f"{settings.supabase_url}/rest/v1/merchants?id=eq.{merchant_id}",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
                "Content-Type": "application/json",
                "Prefer": "return=representation",
            },
            json=payload,
        )
        if resp.status_code in (200, 204):
            return True
        logger.error(
            "supabase_update_failed",
            merchant_id=merchant_id,
            status=resp.status_code,
            body=resp.text[:500],
        )
        return False


# ── Cache ────────────────────────────────────────────────────────────────────


def save_draft(merchant_id: int, slug: str, payload: Dict[str, Any]) -> None:
    """Cache generated content locally."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFTS_DIR / f"{slug}.json"
    path.write_text(json.dumps(payload, indent=2))
    logger.info("draft_cached", merchant_id=merchant_id, path=str(path))


# ── Main pipeline ────────────────────────────────────────────────────────────


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate merchant page content")
    parser.add_argument("--dry-run", action="store_true", help="Skip Supabase writes")
    parser.add_argument("--limit", type=int, default=0, help="Max merchants to process")
    parser.add_argument("--merchant-id", type=int, help="Process single merchant by ID")
    parser.add_argument(
        "--min-locations",
        type=int,
        default=MIN_LOCATIONS,
        help=f"Minimum store locations (default: {MIN_LOCATIONS})",
    )
    parser.add_argument(
        "--min-id", type=int, default=0, help="Only process merchants with id >= this value"
    )
    parser.add_argument(
        "--force", action="store_true", help="Regenerate even if content already exists"
    )
    args = parser.parse_args()

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        logger.error("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in .env")
        sys.exit(1)

    # Gather merchant data
    logger.info("gathering_merchant_data", min_locations=args.min_locations)
    contexts = await gather_merchant_contexts(
        settings,
        min_locations=args.min_locations,
        merchant_id=args.merchant_id,
        force=args.force,
    )
    logger.info("merchants_to_process", count=len(contexts))

    if args.min_id:
        contexts = [c for c in contexts if c.merchant_id >= args.min_id]
        logger.info("filtered_by_min_id", min_id=args.min_id, count=len(contexts))

    if not contexts:
        logger.info("no_merchants_to_process")
        return

    if args.limit:
        contexts = contexts[: args.limit]
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
            index=f"{i + 1}/{len(contexts)}",
            merchant=ctx.name,
            locations=ctx.location_count,
        )

        data = await generate_merchant_content(client, ctx, system_prompt)
        if not data:
            logger.error("generation_failed", merchant=ctx.name)
            failed += 1
            continue

        # Quality validation
        content_warnings = validate_content(data, ctx.name)
        all_warnings.extend(content_warnings)
        for w in content_warnings:
            logger.warning("quality_check", warning=w)

        # Build payload - template-generated fields (no LLM) + LLM fields with placeholders resolved
        slug = slugify(ctx.name)
        faq_json = build_faq_json(ctx)

        payload = {
            "page_slug": slug,
            # Template-generated (no LLM)
            "page_direct_answer": build_direct_answer(ctx),
            "page_hero_subhead": build_hero_subhead(ctx),
            "page_faq_json": faq_json,
            "page_faq_md": build_faq_md(faq_json),
            "page_seo_description": build_seo_description(ctx),
            # LLM-generated with placeholders resolved
            "page_hero_headline": data["page_hero_headline"],
            "page_about_md": resolve_placeholders(data["page_about_md"], ctx),
            "page_how_to_save_md": resolve_placeholders(data["page_how_to_save_md"], ctx),
            "page_tips_md": resolve_placeholders(data["page_tips_md"], ctx),
            # LLM-generated, no discount data needed
            "page_protection_note_md": data["page_protection_note_md"],
            "page_seo_title": data.get(
                "page_seo_title",
                f"{ctx.name} Senior Discount 2026 - Age, Amount & Locations | Saverwell",
            ),
            "page_seo_keywords": data.get("page_seo_keywords", [f"{ctx.name} senior discount"]),
            # Cross-links + metadata
            "page_related_protection_slugs": ctx.protection_slugs,
            "page_related_guide_slugs": ctx.guide_slugs,
            "page_related_merchant_ids": ctx.related_merchant_ids,
            "page_status": "published",
            "page_source": "generate_merchant_page_content",
            "page_author": "Saverwell AI",
            "page_review_score": None,
            "page_review_notes": f"Generated by {GENERATION_MODEL}",
            "page_updated_at": "now()",
        }

        # Cache locally
        save_draft(
            ctx.merchant_id, slug, {**payload, "merchant_id": ctx.merchant_id, "name": ctx.name}
        )

        # Write to Supabase
        if args.dry_run:
            logger.info("dry_run_skip_write", merchant=ctx.name, slug=slug)
        else:
            ok = await update_merchant(settings, ctx.merchant_id, payload)
            if ok:
                logger.info("updated", merchant=ctx.name, slug=slug)
                success += 1
            else:
                failed += 1

        if i < len(contexts) - 1:
            await asyncio.sleep(INTER_MERCHANT_PAUSE)

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
