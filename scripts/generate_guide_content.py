#!/usr/bin/env python3
"""Generate Saverwell Guide articles and upsert to Supabase.

Usage:
    python scripts/generate_guide_content.py                     # full run (1A-medicare)
    python scripts/generate_guide_content.py --dry-run           # generate + validate, skip upsert
    python scripts/generate_guide_content.py --resume            # load cached JSONs, upsert
    python scripts/generate_guide_content.py --phase 1A          # explicit phase (default)
    python scripts/generate_guide_content.py --refresh-data      # update articles with 2026 data
    python scripts/generate_guide_content.py --refresh-data --dry-run  # refresh + validate only
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
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import httpx

if TYPE_CHECKING:
    import anthropic
import structlog

# ── Project imports ──────────────────────────────────────────────────────────
# Ensure the project root is on sys.path so that cmo_agent is importable.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402, I001
from cmo_agent.content.guide import (  # noqa: E402
    PROOFREAD_FIELDS,
    GuideArticle,
    _JSON_SCHEMA,
    parse_guide_json,
)

logger = structlog.get_logger()

# ── Paths ────────────────────────────────────────────────────────────────────
BRAND_VOICE_PATH = _PROJECT_ROOT / "data" / "brand_voices" / "saverwell.txt"
ARCHIVE_PATH = _PROJECT_ROOT / "data" / "saverwell" / "guide_article_archive.txt"
DRAFTS_DIR = _PROJECT_ROOT / "data" / "saverwell" / "guide_drafts"

# ── LLM settings ────────────────────────────────────────────────────────────
GENERATION_MODEL = "claude-sonnet-4-20250514"
SCANNING_MODEL = "claude-haiku-4-5-20251001"
GENERATION_TEMPERATURE = 0.4
GENERATION_MAX_TOKENS = 16384
MAX_RETRIES = 3
INTER_ARTICLE_PAUSE = 2.0  # seconds between articles

# ── Refinement settings ────────────────────────────────────────────────────
MAX_REFINEMENT_ITERATIONS = 2
QUALITY_THRESHOLD = 7  # out of 10

# ── Senior-lens keywords (Guide-specific) ──────────────────────────────────
SENIOR_KEYWORDS = {
    "medicare",
    "social security",
    "retirement",
    "retiree",
    "senior",
    "older adult",
    "fixed income",
    "pension",
    "caregiver",
    "65",
    "enrollment",
    "premium",
    "coverage",
    "benefits",
    "savings",
}

SAVINGS_KEYWORDS = {
    "save",
    "saving",
    "savings",
    "discount",
    "free",
    "reduce",
    "lower",
    "affordable",
    "budget",
    "cost",
    "cheaper",
    "cut",
}


# ── 2026 Medicare Data Reference ─────────────────────────────────────────────

MEDICARE_2026_DATA = """
## 2026 MEDICARE DATA REFERENCE (Official CMS Figures)

### Part A (Hospital Insurance)
- Inpatient hospital deductible: $1,736 per benefit period
- Coinsurance days 61-90: $434/day
- Lifetime reserve days (91-150): $868/day
- SNF coinsurance days 21-100: $217.00/day
- Part A premium (full, <30 quarters): $565/month
- Part A premium (reduced, 30+ quarters): $311/month

### Part B (Medical Insurance)
- Standard monthly premium: $202.90
- Annual deductible: $283
- Coinsurance: 20% of Medicare-approved amounts (unchanged)

### Part D (Prescription Drug Coverage — reflects IRA changes)
- Maximum deductible: $615
- Annual out-of-pocket maximum: $2,100 (up from $2,000 in 2025)
- Coverage gap/donut hole: ELIMINATED (since 2025 under the Inflation Reduction Act)
- Catastrophic coverage: $0 cost-sharing after hitting $2,100 OOP cap
- First 10 negotiated drug prices take effect January 1, 2026
- National base beneficiary premium: ~$36.78/month (used for late penalty calc)

### IRMAA (2026, based on 2024 tax returns)

Single filers:
| Modified AGI | Part B Total Premium | Part D Surcharge |
|---|---|---|
| <= $109,000 | $202.90 | $0 |
| $109,001 - $137,000 | $284.10 | $14.50 |
| $137,001 - $171,000 | $405.80 | $37.50 |
| $171,001 - $205,000 | $527.50 | $60.40 |
| $205,001 - $499,999 | $649.20 | $83.30 |
| >= $500,000 | $689.90 | $91.00 |

Married filing jointly:
| Modified AGI | Part B Total Premium | Part D Surcharge |
|---|---|---|
| <= $218,000 | $202.90 | $0 |
| $218,001 - $274,000 | $284.10 | $14.50 |
| $274,001 - $342,000 | $405.80 | $37.50 |
| $342,001 - $410,000 | $527.50 | $60.40 |
| $410,001 - $749,999 | $649.20 | $83.30 |
| >= $750,000 | $689.90 | $91.00 |

### Extra Help / Low Income Subsidy (LIS)
- Income limit: $23,475 individual / $31,725 couple (150% FPL)
- Resource limit: $16,100 individual / $32,130 couple
- Full Extra Help copays: $1.60-$4.90 generic, $4.80-$12.15 brand (by benefit level)
- Partial subsidy eliminated since 2024; all qualifying individuals get full benefits
- Annual OOP cap applies: $0 after $2,100

### Enrollment Periods (unchanged)
- Initial Enrollment Period (IEP): 7-month window around 65th birthday
- Open Enrollment Period (OEP/AEP): October 15 - December 7
- General Enrollment Period (GEP): January 1 - March 31
- Medicare Advantage Open Enrollment Period (MA OEP): January 1 - March 31

### Penalties
- Part B late enrollment penalty: 10% per 12-month period delayed (permanent)
  - 2026 penalty per year delayed: 10% x $202.90 = $20.29/month
  - 2-year delay: $40.58/month added permanently
- Part D late enrollment penalty: 1% of national base premium per uncovered month (permanent)

### Other Constants
- RMD starting age: 73 (unchanged)
- Qualified Roth distribution age: 59.5 (unchanged)
- IRMAA lookback: 2026 premiums are based on 2024 tax returns (MAGI)
""".strip()


# ── Topic Briefs ─────────────────────────────────────────────────────────────


@dataclass
class GuideTopicBrief:
    """Defines a single guide article topic."""

    slug: str
    title: str
    category_slug: str  # "medicare", "insurance", etc.
    # TODO: category_id values are stale after the category restructuring migration.
    # After running the Supabase migration that creates the new categories
    # (senior-products, saving-money, retirement-taxes, caregiving), update these
    # IDs to match the new guide_categories.id values from the DB.
    category_id: int  # FK to guide_categories.id
    vertical: str  # "1A-medicare", "1B-insurance", etc.
    description: str  # Full topic description for LLM
    senior_examples: List[str]  # 3 relatable examples
    source_urls: List[Dict[str, str]]  # [{label, url}]
    seo_keywords: List[str]  # Target SEO keywords
    suggested_tags: List[str]  # 3-8 tags
    intent_tags: List[str]  # learn, compare, save, decide
    monetization_type: str = "informational"  # informational, affiliate, lead_gen


# ── Phase 1A: Medicare Topic Briefs (12 articles) ────────────────────────────

PHASE_1A_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="medicare-explained-simple-guide",
        title="Medicare Explained: A Simple Guide for Seniors",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Pillar page. What Medicare is, who qualifies, the 4 parts overview, and how to get started. Written for someone who has never dealt with Medicare before.",
        senior_examples=[
            "A 64-year-old approaching retirement who has always had employer insurance and doesn't know where to start with Medicare",
            "A retiree helping their spouse understand Medicare enrollment after turning 65",
            "A grandparent who has been on Medicare for years but still doesn't understand the difference between parts",
        ],
        source_urls=[
            {
                "label": "Medicare.gov What Is Medicare",
                "url": "https://www.medicare.gov/what-medicare-covers",
            },
            {"label": "CMS.gov Medicare Basics", "url": "https://www.cms.gov/Medicare/Medicare"},
            {"label": "SSA.gov Medicare", "url": "https://www.ssa.gov/benefits/medicare/"},
        ],
        seo_keywords=[
            "medicare explained",
            "what is medicare",
            "medicare for beginners",
            "medicare guide for seniors",
        ],
        suggested_tags=["medicare", "health-insurance", "enrollment", "seniors", "retirement"],
        intent_tags=["learn"],
    ),
    GuideTopicBrief(
        slug="medicare-parts-a-b-c-d-explained",
        title="Medicare Parts A, B, C, and D: What Each One Covers",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Breakdown of all 4 Medicare parts — hospital (A), medical (B), Advantage (C), prescriptions (D). Coverage, costs, and what's NOT covered in each.",
        senior_examples=[
            "A retiree who thought Medicare Part A covered everything and got a surprise bill for an outpatient procedure",
            "A senior confused about whether they need Part D if they already have Part C (Medicare Advantage)",
            "A caregiver trying to figure out which parts their parent needs for upcoming knee surgery",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Parts Overview",
                "url": "https://www.medicare.gov/basics/get-started-with-medicare",
            },
            {"label": "CMS.gov Medicare Parts", "url": "https://www.cms.gov/Medicare/Medicare"},
            {
                "label": "Medicare.gov Part D",
                "url": "https://www.medicare.gov/drug-coverage-part-d",
            },
        ],
        seo_keywords=[
            "medicare parts explained",
            "medicare part a vs b",
            "medicare part c",
            "medicare part d",
            "what does medicare cover",
        ],
        suggested_tags=["medicare", "part-a", "part-b", "part-c", "part-d", "coverage"],
        intent_tags=["learn", "compare"],
    ),
    GuideTopicBrief(
        slug="medicare-vs-medicaid-difference",
        title="Medicare vs. Medicaid: What's the Difference?",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Clear comparison of Medicare (age-based) vs. Medicaid (income-based). Who qualifies for each, dual eligibility, and how they work together.",
        senior_examples=[
            "A retiree with limited income who doesn't know they might qualify for both Medicare AND Medicaid",
            "A senior who confuses the two programs and tries to apply for the wrong one",
            "A caregiver whose parent needs long-term care and doesn't realize Medicaid — not Medicare — covers nursing homes",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Medicare vs Medicaid",
                "url": "https://www.medicare.gov/basics",
            },
            {"label": "Medicaid.gov", "url": "https://www.medicaid.gov/"},
            {
                "label": "CMS.gov Dual Eligibility",
                "url": "https://www.medicare.gov/basics",
            },
        ],
        seo_keywords=[
            "medicare vs medicaid",
            "difference between medicare and medicaid",
            "dual eligible medicare medicaid",
        ],
        suggested_tags=["medicare", "medicaid", "dual-eligible", "health-insurance", "low-income"],
        intent_tags=["learn", "compare"],
    ),
    GuideTopicBrief(
        slug="medicare-enrollment-deadlines",
        title="Medicare Enrollment Deadlines You Can't Afford to Miss",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="All enrollment windows — Initial Enrollment Period (IEP), General Enrollment Period (GEP), Annual Enrollment Period (AEP), Special Enrollment Periods (SEP). Late enrollment penalties explained.",
        senior_examples=[
            "A retiree who missed their Initial Enrollment Period because they didn't know it started 3 months before their 65th birthday",
            "A senior paying a permanent 10% Part B penalty because they delayed enrollment when they retired",
            "A retiree who wants to switch Medicare Advantage plans but doesn't know when open enrollment is",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Enrollment Periods",
                "url": "https://www.medicare.gov/basics/get-started-with-medicare/sign-up/when-does-medicare-coverage-start",
            },
            {"label": "CMS.gov Open Enrollment", "url": "https://www.cms.gov/Medicare/Medicare"},
            {
                "label": "SSA.gov Apply for Medicare",
                "url": "https://www.ssa.gov/benefits/medicare/",
            },
        ],
        seo_keywords=[
            "medicare enrollment deadlines",
            "when to sign up for medicare",
            "medicare open enrollment",
            "medicare late enrollment penalty",
        ],
        suggested_tags=["medicare", "enrollment", "deadlines", "penalties", "open-enrollment"],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="save-money-medicare-premiums",
        title="7 Ways to Save Money on Medicare Premiums",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Core Saverwell savings angle. Actionable strategies to reduce Medicare costs — comparing plans annually, Extra Help, IRMAA appeals, Medicare Supplement timing, Part D optimization.",
        senior_examples=[
            "A retiree paying $300/month more than necessary because they never compared Medicare Advantage plans after their initial enrollment",
            "A senior on a fixed income who qualifies for Extra Help but doesn't know the program exists",
            "A retiree hit with IRMAA surcharges after selling their home, unaware they could appeal",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Save Money",
                "url": "https://www.medicare.gov/basics/costs/medicare-costs/get-help-paying-costs",
            },
            {
                "label": "SSA.gov IRMAA",
                "url": "https://www.ssa.gov/benefits/medicare/medicare-premiums.html",
            },
            {
                "label": "CMS.gov Extra Help",
                "url": "https://www.cms.gov/medicare/coverage/prescription-drug-coverage/LimitedIncomeandResources",
            },
        ],
        seo_keywords=[
            "save money medicare",
            "reduce medicare premiums",
            "medicare cost savings",
            "lower medicare costs",
        ],
        suggested_tags=["medicare", "savings", "premiums", "cost-reduction", "fixed-income"],
        intent_tags=["save", "learn"],
    ),
    GuideTopicBrief(
        slug="medicare-advantage-vs-original",
        title="Medicare Advantage vs. Original Medicare: Which Saves You More?",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Side-by-side cost comparison. Premiums, out-of-pocket maximums, network restrictions, extra benefits, and when each option makes more financial sense.",
        senior_examples=[
            "A retiree debating whether to switch from Original Medicare to an Advantage plan that advertises $0 premiums",
            "A senior who chose Medicare Advantage but discovered their preferred doctor is out-of-network",
            "A retiree who saved $2,400/year by switching back to Original Medicare plus a Medicare Supplement plan",
        ],
        source_urls=[
            {"label": "Medicare.gov Plan Compare", "url": "https://www.medicare.gov/plan-compare/"},
            {
                "label": "CMS.gov Medicare Advantage",
                "url": "https://www.cms.gov/medicare/enrollment-renewal/health-plans",
            },
            {
                "label": "Medicare.gov Original vs Advantage",
                "url": "https://www.medicare.gov/health-drug-plans/health-plans",
            },
        ],
        seo_keywords=[
            "medicare advantage vs original medicare",
            "is medicare advantage worth it",
            "original medicare cost",
            "medicare advantage pros cons",
        ],
        suggested_tags=[
            "medicare",
            "medicare-advantage",
            "original-medicare",
            "medicare-supplement",
            "cost-comparison",
        ],
        intent_tags=["compare", "decide", "save"],
    ),
    GuideTopicBrief(
        slug="does-medicare-cover-dental",
        title="Does Medicare Cover Dental? What Seniors Need to Know",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Coverage gap explained. What Original Medicare does NOT cover, Advantage plans with dental, standalone dental plans, discount options, and free/low-cost clinics.",
        senior_examples=[
            "A retiree who needs a root canal and is shocked to learn Original Medicare doesn't cover dental",
            "A senior paying $3,000 out of pocket for dentures because they assumed Medicare covered it",
            "A retiree who found a Medicare Advantage plan with $0 preventive dental but $50 copays for major work",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Dental Coverage",
                "url": "https://www.medicare.gov/coverage/dental-services",
            },
            {"label": "CMS.gov Coverage Gap", "url": "https://www.cms.gov/Medicare/Medicare"},
            {"label": "HRSA Health Centers", "url": "https://findahealthcenter.hrsa.gov/"},
        ],
        seo_keywords=[
            "does medicare cover dental",
            "medicare dental coverage",
            "dental insurance for seniors",
            "senior dental plans",
        ],
        suggested_tags=["medicare", "dental", "coverage-gap", "dental-insurance", "cost-savings"],
        intent_tags=["learn", "save"],
    ),
    GuideTopicBrief(
        slug="does-medicare-cover-hearing-aids",
        title="Does Medicare Cover Hearing Aids? Your Options Explained",
        category_slug="senior-products",
        category_id=1,
        vertical="1A-medicare",
        description="Coverage gap and new OTC hearing aid options. What Medicare covers (diagnostic tests) vs. doesn't (hearing aids), Advantage plans with hearing benefits, OTC options under $300.",
        senior_examples=[
            "A retiree told they need hearing aids costing $4,000 but Medicare won't cover them",
            "A senior who found $299 OTC hearing aids at Walgreens after the FDA rule change and wants to know if they work",
            "A retiree whose Medicare Advantage plan covers $500/year toward hearing aids but they didn't know",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Hearing Aid Coverage",
                "url": "https://www.medicare.gov/coverage/hearing-aids",
            },
            {
                "label": "FDA OTC Hearing Aids",
                "url": "https://www.fda.gov/medical-devices/consumer-products/hearing-aids",
            },
            {"label": "CMS.gov Medicare Hearing", "url": "https://www.cms.gov/Medicare/Medicare"},
        ],
        seo_keywords=[
            "does medicare cover hearing aids",
            "OTC hearing aids seniors",
            "hearing aid cost seniors",
            "cheap hearing aids",
        ],
        suggested_tags=["medicare", "hearing-aids", "otc", "coverage-gap", "cost-savings"],
        intent_tags=["learn", "save", "compare"],
    ),
    GuideTopicBrief(
        slug="does-medicare-cover-vision",
        title="Does Medicare Cover Vision? Glasses, Exams, and Eye Care",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="What Medicare covers (cataract surgery, glaucoma tests, diabetic eye exams) vs. what it doesn't (routine eye exams, glasses, contacts). Affordable alternatives.",
        senior_examples=[
            "A retiree who needs new glasses and is surprised to learn Medicare doesn't cover routine eye exams",
            "A senior with diabetes who doesn't realize Medicare DOES cover their annual diabetic eye exam",
            "A retiree paying $600 for glasses out of pocket when their Advantage plan included a $200 vision allowance",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Eye Exams",
                "url": "https://www.medicare.gov/coverage",
            },
            {
                "label": "Medicare.gov Glaucoma Tests",
                "url": "https://www.medicare.gov/coverage",
            },
            {"label": "CMS.gov Vision Coverage", "url": "https://www.cms.gov/Medicare/Medicare"},
        ],
        seo_keywords=[
            "does medicare cover vision",
            "medicare eye exam coverage",
            "vision insurance seniors",
            "medicare glasses coverage",
        ],
        suggested_tags=["medicare", "vision", "eye-care", "coverage-gap", "glasses"],
        intent_tags=["learn", "save"],
    ),
    GuideTopicBrief(
        slug="does-medicare-cover-prescriptions",
        title="Does Medicare Cover Prescriptions? Understanding Part D",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Part D explained — formularies, tiers, donut hole, coverage gap, how to compare plans, generic vs. brand savings, and Extra Help for low-income seniors.",
        senior_examples=[
            "A retiree paying $400/month for a brand-name medication who doesn't know a $15 generic alternative exists on their plan",
            "A senior who hit the Part D donut hole (coverage gap) and suddenly has to pay 25% of drug costs",
            "A retiree whose pharmacy stopped carrying their medication and they need to switch Part D plans mid-year",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Part D",
                "url": "https://www.medicare.gov/drug-coverage-part-d",
            },
            {
                "label": "CMS.gov Part D",
                "url": "https://www.cms.gov/medicare/coverage/prescription-drug-coverage",
            },
            {"label": "Medicare.gov Plan Finder", "url": "https://www.medicare.gov/plan-compare/"},
        ],
        seo_keywords=[
            "does medicare cover prescriptions",
            "medicare part d explained",
            "medicare drug coverage",
            "part d donut hole",
        ],
        suggested_tags=["medicare", "part-d", "prescriptions", "drug-coverage", "formulary"],
        intent_tags=["learn", "save"],
    ),
    GuideTopicBrief(
        slug="irmaa-avoid-higher-medicare-premiums",
        title="IRMAA: How to Avoid Higher Medicare Premiums",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Income-Related Monthly Adjustment Amount explained. Who gets hit, current thresholds, how to appeal (life-changing event), strategies to reduce MAGI.",
        senior_examples=[
            "A retiree who sold a rental property and got hit with $500+/month IRMAA surcharges the following year",
            "A senior who retired mid-year and didn't know they could appeal IRMAA based on their reduced income",
            "A retiree whose financial advisor helped them manage Roth conversions to stay below IRMAA thresholds",
        ],
        source_urls=[
            {
                "label": "SSA.gov IRMAA",
                "url": "https://www.ssa.gov/benefits/medicare/medicare-premiums.html",
            },
            {
                "label": "Medicare.gov Costs",
                "url": "https://www.medicare.gov/basics/costs/medicare-costs",
            },
            {"label": "CMS.gov Part B Premiums", "url": "https://www.cms.gov/Medicare/Medicare"},
        ],
        seo_keywords=[
            "IRMAA medicare",
            "avoid higher medicare premiums",
            "medicare income surcharge",
            "IRMAA appeal",
        ],
        suggested_tags=["medicare", "irmaa", "premiums", "income-surcharge", "tax-planning"],
        intent_tags=["save", "learn"],
    ),
    GuideTopicBrief(
        slug="medicare-extra-help-prescription-savings",
        title="Medicare Extra Help: Save on Prescription Drug Costs",
        category_slug="medicare",
        category_id=1,
        vertical="1A-medicare",
        description="Low Income Subsidy (Extra Help) program. Eligibility, how to apply, what it covers, income/asset limits, auto-enrollment for dual-eligible beneficiaries.",
        senior_examples=[
            "A retiree spending $200/month on prescriptions who qualifies for Extra Help but has never heard of the program",
            "A senior whose spouse recently passed away and whose reduced income now qualifies them for the subsidy",
            "A grandparent helping their elderly parent apply for Extra Help through SSA.gov",
        ],
        source_urls=[
            {
                "label": "SSA.gov Extra Help",
                "url": "https://www.ssa.gov/benefits/medicare/prescriptionhelp/",
            },
            {
                "label": "Medicare.gov Extra Help",
                "url": "https://www.medicare.gov/basics/costs/medicare-costs/get-help-paying-costs/lower-prescription-costs",
            },
            {
                "label": "CMS.gov LIS",
                "url": "https://www.cms.gov/medicare/coverage/prescription-drug-coverage/LimitedIncomeandResources",
            },
        ],
        seo_keywords=[
            "medicare extra help",
            "low income subsidy medicare",
            "prescription drug savings seniors",
            "medicare prescription help",
        ],
        suggested_tags=["medicare", "extra-help", "low-income", "prescriptions", "subsidy"],
        intent_tags=["save", "learn"],
    ),
]

# ── Phase 1B: Insurance Topic Briefs (3 articles) ────────────────────────────

PHASE_1B_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="medicare-supplement-plans-explained",
        title="Medicare Supplement Insurance: What It Covers and How It Works",
        category_slug="insurance",
        category_id=2,
        vertical="1B-insurance",
        description="Comprehensive guide to Medicare Supplement (Med Supp) insurance. What it covers, the standardized plan letters (A through N), how to compare plans from different insurers, enrollment timing, and cost factors. Educational framing only - no specific company recommendations.",
        senior_examples=[
            "A retiree confused about the difference between Medicare Advantage and Medicare Supplement plans",
            "A 65-year-old who missed their Medicare Supplement open enrollment window and now faces medical underwriting",
            "A senior paying $400/month for a Plan F equivalent when a Plan G from a different insurer costs $200 less",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Supplement Insurance",
                "url": "https://www.medicare.gov/health-drug-plans/medigap",
            },
            {
                "label": "CMS.gov Medicare Supplement",
                "url": "https://www.cms.gov/Medicare/Medicare",
            },
            {
                "label": "NAIC Shopper's Guide",
                "url": "https://www.naic.org/documents/prod_serv_consumer_guide_medicare_supplement.pdf",
            },
        ],
        seo_keywords=[
            "medicare supplement insurance",
            "med supp plans",
            "medicare supplement vs medicare advantage",
            "medicare supplement plan g",
        ],
        suggested_tags=[
            "insurance",
            "medicare-supplement",
            "med-supp",
            "coverage",
            "plan-comparison",
        ],
        intent_tags=["learn", "compare"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="auto-home-insurance-seniors",
        title="Auto and Home Insurance: How to Save After 55",
        category_slug="insurance",
        category_id=2,
        vertical="1B-insurance",
        description="Practical guide to reducing auto and home insurance costs after 55. Discounts available for retirees, defensive driving courses, bundling strategies, coverage adjustments for fixed incomes, and questions to ask your agent. Educational and affiliate-friendly.",
        senior_examples=[
            "A retiree who hasn't shopped auto insurance in 10 years and is paying 40% more than comparable quotes",
            "A senior who took a defensive driving course and saved $300/year on auto insurance",
            "A couple who downsized and didn't realize they could reduce their home insurance by $800/year",
        ],
        source_urls=[
            {
                "label": "NAIC Consumer Auto Insurance",
                "url": "https://www.consumerfinance.gov/consumer-tools/auto-loans/",
            },
            {
                "label": "III.org Senior Auto Discounts",
                "url": "https://www.iii.org/article/how-get-best-deal-auto-insurance",
            },
            {
                "label": "FEMA.gov Homeowners Insurance",
                "url": "https://www.fema.gov/flood-insurance",
            },
        ],
        seo_keywords=[
            "auto insurance seniors",
            "home insurance savings over 55",
            "senior auto insurance discounts",
            "save on car insurance retiree",
        ],
        suggested_tags=[
            "insurance",
            "auto-insurance",
            "home-insurance",
            "savings",
            "discounts",
            "seniors",
        ],
        intent_tags=["save", "learn"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="dental-insurance-seniors",
        title="Dental Insurance for Seniors: Your Options Explained",
        category_slug="insurance",
        category_id=2,
        vertical="1B-insurance",
        description="Guide to dental insurance options for seniors not covered by Original Medicare. Standalone dental plans, Medicare Advantage dental benefits, discount dental programs, and community health centers. Cost ranges and coverage tiers explained.",
        senior_examples=[
            "A retiree who needs a root canal and is shocked to learn Original Medicare doesn't cover dental",
            "A senior comparing standalone dental plans and discovering annual maximums are only $1,000-$1,500",
            "A grandparent who found a community health center offering sliding-scale dental care",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Dental Coverage",
                "url": "https://www.medicare.gov/coverage/dental-services",
            },
            {"label": "HRSA Health Centers", "url": "https://findahealthcenter.hrsa.gov/"},
            {"label": "NADP Consumer Guide", "url": "https://www.medicare.gov/coverage"},
        ],
        seo_keywords=[
            "dental insurance seniors",
            "dental plans for retirees",
            "senior dental coverage",
            "dental insurance after 65",
        ],
        suggested_tags=["insurance", "dental", "seniors", "coverage-gap", "dental-plans"],
        intent_tags=["learn", "compare", "save"],
        monetization_type="affiliate",
    ),
]

# ── Phase 2A: Medical Alerts Topic Briefs (2 articles) ──────────────────────

PHASE_2A_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="medical-alert-systems-guide",
        title="Medical Alert Systems: Features, Costs, and What to Know",
        category_slug="senior-products",
        category_id=3,
        vertical="2A-medical-alerts",
        description="Comprehensive guide to medical alert systems for seniors. Types (in-home, mobile GPS, smartwatch), key features (fall detection, GPS, two-way voice), cost structures (equipment, monthly monitoring, cancellation fees), and factors to consider when choosing. No specific brand recommendations.",
        senior_examples=[
            "A daughter researching medical alert systems for her 78-year-old mother who lives alone",
            "A retiree who signed up for a medical alert system only to discover hidden cancellation fees",
            "A senior couple comparing in-home systems vs. mobile GPS options for their active lifestyle",
        ],
        source_urls=[
            {
                "label": "FTC.gov Medical Alert Systems",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "NIA.gov Aging in Place",
                "url": "https://www.cdc.gov/falls/",
            },
            {
                "label": "Medicare.gov Home Health",
                "url": "https://www.medicare.gov/coverage/home-health-services",
            },
        ],
        seo_keywords=[
            "medical alert systems",
            "medical alert systems for seniors",
            "personal emergency response system",
            "medical alert features",
        ],
        suggested_tags=["medical-alerts", "safety", "seniors", "fall-detection", "aging-in-place"],
        intent_tags=["learn", "compare"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="medical-alert-systems-cost",
        title="How Much Do Medical Alert Systems Cost?",
        category_slug="senior-products",
        category_id=3,
        vertical="2A-medical-alerts",
        description="Transparent cost breakdown of medical alert systems. Monthly monitoring fees, equipment costs, activation fees, cancellation penalties, and total cost of ownership. Comparison of pricing tiers (basic, mid-range, premium). Hidden costs to watch for.",
        senior_examples=[
            "A senior comparing a $20/month basic system vs. a $50/month premium system and wondering what the extra cost gets them",
            "A family who signed a 3-year contract and discovered a $350 early cancellation fee",
            "A retiree who found a no-contract medical alert option and saved over $200 vs. the contract alternative",
        ],
        source_urls=[
            {
                "label": "FTC.gov Medical Alert Systems",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "NIA.gov Aging in Place",
                "url": "https://www.cdc.gov/falls/",
            },
            {
                "label": "AARP Medical Alerts Guide",
                "url": "https://www.aarp.org/caregiving/home-care/",
            },
        ],
        seo_keywords=[
            "medical alert system cost",
            "how much do medical alert systems cost",
            "medical alert monthly fee",
            "cheapest medical alert system",
        ],
        suggested_tags=["medical-alerts", "cost", "pricing", "comparison", "hidden-fees"],
        intent_tags=["compare", "save"],
        monetization_type="affiliate",
    ),
]

# ── Phase 2B: Phones Topic Briefs (2 articles) ─────────────────────────────

PHASE_2B_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="cell-phone-plans-seniors",
        title="Cell Phone Plans for Seniors: Compare Your Options (2026)",
        category_slug="senior-products",
        category_id=4,
        vertical="2B-phones",
        description="Guide to affordable cell phone plans for seniors. Major carriers, MVNOs (Mint, Consumer Cellular, etc.), government Lifeline program, data needs assessment, and cost comparison by usage tier. Savings-first framing.",
        senior_examples=[
            "A retiree paying $85/month for a plan with unlimited data when they only use 2GB",
            "A senior who switched to an MVNO and cut their phone bill from $70 to $25/month",
            "A couple who didn't know about the Lifeline program that provides free or discounted phone service",
        ],
        source_urls=[
            {"label": "FCC Lifeline Program", "url": "https://www.fcc.gov/lifeline-consumers"},
            {"label": "FCC Consumer Guides", "url": "https://www.fcc.gov/consumers/guides"},
            {
                "label": "AARP Cell Phone Guide",
                "url": "https://www.aarp.org/home-family/personal-technology/",
            },
        ],
        seo_keywords=[
            "cell phone plans for seniors",
            "senior cell phone plans",
            "cheapest phone plans seniors",
            "phone plans for older adults",
        ],
        suggested_tags=["phones", "cell-plans", "seniors", "savings", "comparison", "mvno"],
        intent_tags=["compare", "save"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="cut-phone-bill-after-65",
        title="How to Cut Your Phone Bill in Half After 65",
        category_slug="senior-products",
        category_id=4,
        vertical="2B-phones",
        description="Actionable strategies to reduce phone costs. Audit your current usage, downgrade data plans, switch to MVNOs, use Wi-Fi calling, government assistance programs, and senior-specific discounts. Savings-first framing with specific dollar examples.",
        senior_examples=[
            "A retiree who audited their phone usage and realized they were paying for 10GB when they used less than 1GB",
            "A senior who switched to Wi-Fi calling at home and downgraded to a $15/month plan",
            "A couple who combined their plans and saved $40/month by switching carriers",
        ],
        source_urls=[
            {"label": "FCC Lifeline Program", "url": "https://www.fcc.gov/lifeline-consumers"},
            {"label": "FCC Consumer Guides", "url": "https://www.fcc.gov/consumers/guides"},
            {"label": "USAGov Phone Assistance", "url": "https://www.usa.gov/"},
        ],
        seo_keywords=[
            "cut phone bill senior",
            "lower phone bill after 65",
            "save money cell phone retiree",
            "reduce phone costs",
        ],
        suggested_tags=["phones", "savings", "tips", "seniors", "budget"],
        intent_tags=["save", "learn"],
        monetization_type="affiliate",
    ),
]

# ── Phase 2C: Hearing Aids Topic Briefs (1 article) ────────────────────────

PHASE_2C_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="save-on-hearing-aids",
        title="How to Save Thousands on Hearing Aids",
        category_slug="senior-products",
        category_id=5,
        vertical="2C-hearing-aids",
        description="Savings-first guide to hearing aids. OTC vs. prescription comparison, price ranges by type, insurance and Medicare Advantage benefits, VA programs, state assistance, financing options, and hidden costs to watch for. Own the savings angle competitors ignore.",
        senior_examples=[
            "A retiree quoted $6,000 for prescription hearing aids who found comparable OTC models for $600",
            "A veteran who discovered the VA provides hearing aids at no cost",
            "A senior who saved $2,000 by purchasing hearing aids through a warehouse club audiologist instead of a private practice",
        ],
        source_urls=[
            {
                "label": "FDA OTC Hearing Aids",
                "url": "https://www.fda.gov/medical-devices/consumer-products/hearing-aids",
            },
            {
                "label": "Medicare.gov Hearing Aid Coverage",
                "url": "https://www.medicare.gov/coverage/hearing-aids",
            },
            {
                "label": "VA.gov Hearing Aids",
                "url": "https://www.va.gov/health-care/about-va-health-benefits/",
            },
        ],
        seo_keywords=[
            "save money hearing aids",
            "cheap hearing aids",
            "affordable hearing aids seniors",
            "OTC hearing aids cost",
        ],
        suggested_tags=["hearing-aids", "savings", "otc", "cost-comparison", "seniors"],
        intent_tags=["save", "compare"],
        monetization_type="affiliate",
    ),
]

# ── Phase EXPAND: Monetization Expansion Topics (8 articles) ────────────────

PHASE_EXPAND_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="medical-alert-fall-detection",
        title="Best Medical Alert Systems with Fall Detection",
        category_slug="senior-products",
        category_id=3,
        vertical="2A-medical-alerts",
        description="Comparison guide to medical alert systems with automatic fall detection. How fall detection technology works (accelerometers, AI algorithms), accuracy rates, false alarm handling, cost differences vs. non-fall-detection systems, and which situations benefit most from fall detection. No specific brand rankings, but compare feature tiers.",
        senior_examples=[
            "A 76-year-old who lives alone and had a fall in the bathroom but couldn't reach the help button",
            "A daughter evaluating fall detection systems for her mother after a hip replacement",
            "A senior couple comparing fall detection add-on costs across different medical alert providers",
        ],
        source_urls=[
            {
                "label": "NIA.gov Falls Prevention",
                "url": "https://www.cdc.gov/falls/",
            },
            {"label": "CDC Falls Prevention", "url": "https://www.cdc.gov/falls/"},
            {
                "label": "FTC.gov PERS",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
        ],
        seo_keywords=[
            "medical alert fall detection",
            "fall detection systems seniors",
            "automatic fall detection medical alert",
            "best fall detection device",
        ],
        suggested_tags=["medical-alerts", "fall-detection", "safety", "seniors", "aging-in-place"],
        intent_tags=["compare", "decide"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="medical-alert-watches",
        title="Best Medical Alert Watches and Wearables for Seniors",
        category_slug="senior-products",
        category_id=3,
        vertical="2A-medical-alerts",
        description="Guide to wearable medical alert devices: smartwatch-style systems, wrist-based panic buttons, and GPS-enabled wearables. Compare form factors (watch vs. pendant vs. clip), battery life, water resistance, cellular connectivity, and which wearables work without a smartphone. Focus on lifestyle fit for active seniors.",
        senior_examples=[
            "A 70-year-old who walks daily and wants a medical alert that looks like a regular watch",
            "A senior who rejected a pendant-style alert because it felt stigmatizing but would wear a smartwatch",
            "A retiree comparing Apple Watch fall detection vs. dedicated medical alert watches",
        ],
        source_urls=[
            {
                "label": "FTC.gov PERS",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "NIA.gov Aging in Place",
                "url": "https://www.cdc.gov/falls/",
            },
            {
                "label": "AARP Medical Alerts",
                "url": "https://www.aarp.org/caregiving/home-care/",
            },
        ],
        seo_keywords=[
            "medical alert watch",
            "medical alert smartwatch seniors",
            "wearable medical alert",
            "medical alert bracelet",
        ],
        suggested_tags=["medical-alerts", "wearable", "smartwatch", "seniors", "active-lifestyle"],
        intent_tags=["compare", "decide"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="medicare-medical-alert-coverage",
        title="Medical Alert Systems: Does Medicare Cover Them?",
        category_slug="senior-products",
        category_id=3,
        vertical="2A-medical-alerts",
        description="Clear answer to whether Medicare covers medical alert systems. Original Medicare limitations, Medicare Advantage plans that include PERS benefits, Medicaid waivers by state, VA benefits for veterans, and other assistance programs. Includes how to find out if your specific plan covers a medical alert.",
        senior_examples=[
            "A senior who assumed Medicare covered their medical alert system and received a $300 bill",
            "A retiree who switched to a Medicare Advantage plan partly because it included a free medical alert system",
            "A veteran who discovered the VA provides medical alert devices at no cost through their home health program",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Home Health",
                "url": "https://www.medicare.gov/coverage/home-health-services",
            },
            {
                "label": "Medicare.gov DME",
                "url": "https://www.medicare.gov/coverage",
            },
            {
                "label": "VA.gov Health Benefits",
                "url": "https://www.va.gov/health-care/about-va-health-benefits/",
            },
        ],
        seo_keywords=[
            "does medicare cover medical alert systems",
            "medicare medical alert",
            "medicare advantage medical alert",
            "medicaid medical alert coverage",
        ],
        suggested_tags=["medical-alerts", "medicare", "coverage", "insurance", "medicaid"],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="medical-alert-no-monthly-fee",
        title="Medical Alert Systems with No Monthly Fee: What to Know",
        category_slug="senior-products",
        category_id=3,
        vertical="2A-medical-alerts",
        description="Honest guide to medical alert systems without monthly monitoring fees. One-time purchase options, smartphone-based solutions, Apple Watch and Samsung Galaxy Watch emergency features, family-monitored alternatives, and the trade-offs vs. professionally monitored systems. Help seniors understand what they gain and lose without 24/7 monitoring.",
        senior_examples=[
            "A retiree on a fixed income who can't afford $30-50/month for monitoring but wants emergency help",
            "A senior who set up their iPhone with Emergency SOS and Medical ID as a free alternative",
            "A family who bought a one-time-purchase medical alert and connected it to their own response plan",
        ],
        source_urls=[
            {
                "label": "FTC.gov PERS",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {"label": "Apple Emergency SOS", "url": "https://support.apple.com/en-us/108896"},
            {
                "label": "NIA.gov Aging in Place",
                "url": "https://www.cdc.gov/falls/",
            },
        ],
        seo_keywords=[
            "medical alert no monthly fee",
            "medical alert one time purchase",
            "free medical alert seniors",
            "medical alert without subscription",
        ],
        suggested_tags=["medical-alerts", "no-monthly-fee", "budget", "seniors", "alternatives"],
        intent_tags=["save", "compare"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="otc-hearing-aids-under-500",
        title="Best OTC Hearing Aids Under $500",
        category_slug="senior-products",
        category_id=5,
        vertical="2C-hearing-aids",
        description="Comparison guide to over-the-counter hearing aids priced under $500. What changed with the 2022 FDA rule, OTC vs. prescription hearing aids, what to expect at different price points ($100, $300, $500), key features to look for (Bluetooth, rechargeable, app control), and honest limitations. Savings-focused framing.",
        senior_examples=[
            "A retiree who was quoted $4,500 for prescription hearing aids and wants to try OTC first",
            "A senior who bought $50 hearing amplifiers online and was disappointed, now looking for legitimate OTC options",
            "A couple where both partners need hearing aids and are looking at the total cost savings of OTC",
        ],
        source_urls=[
            {
                "label": "FDA OTC Hearing Aids",
                "url": "https://www.fda.gov/medical-devices/consumer-products/hearing-aids",
            },
            {"label": "NIDCD Hearing Aids", "url": "https://www.nidcd.nih.gov/health/hearing-aids"},
            {
                "label": "AARP OTC Hearing Aids",
                "url": "https://www.fda.gov/medical-devices/consumer-products/hearing-aids",
            },
        ],
        seo_keywords=[
            "OTC hearing aids under 500",
            "best over the counter hearing aids",
            "cheap hearing aids that work",
            "affordable hearing aids seniors",
        ],
        suggested_tags=["hearing-aids", "otc", "budget", "cost-comparison", "seniors"],
        intent_tags=["compare", "save", "decide"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="medicare-hearing-aids-coverage",
        title="Does Medicare Cover Hearing Aids? What Actually Helps",
        category_slug="senior-products",
        category_id=5,
        vertical="2C-hearing-aids",
        description="Clear guide to Medicare and hearing aid coverage. Original Medicare limitations (doesn't cover hearing aids), Medicare Advantage plans with hearing benefits, Medicaid hearing aid coverage by state, VA hearing aid programs, nonprofit assistance programs, and the OTC alternative. Actionable steps to find coverage.",
        senior_examples=[
            "A senior who needs hearing aids and is frustrated to learn Original Medicare doesn't cover them",
            "A retiree who switched to a Medicare Advantage plan and got $2,500 in hearing aid coverage",
            "A veteran who received premium hearing aids through the VA at no cost",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Hearing Aids",
                "url": "https://www.medicare.gov/coverage/hearing-aids",
            },
            {"label": "NIDCD Hearing Aids", "url": "https://www.nidcd.nih.gov/health/hearing-aids"},
            {
                "label": "VA.gov Audiology",
                "url": "https://www.va.gov/health-care/about-va-health-benefits/",
            },
        ],
        seo_keywords=[
            "does medicare cover hearing aids",
            "medicare hearing aid coverage",
            "medicare advantage hearing aids",
            "free hearing aids seniors",
        ],
        suggested_tags=["hearing-aids", "medicare", "coverage", "insurance", "seniors"],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="free-phones-seniors",
        title="Free Cell Phones for Seniors: Government Programs and How to Qualify",
        category_slug="senior-products",
        category_id=4,
        vertical="2B-phones",
        description="Guide to government-subsidized cell phone programs for low-income seniors. Lifeline program, Affordable Connectivity Program status, state-level programs, how to apply, what phones and plans are provided, income eligibility requirements, and how to avoid scams claiming to offer free phones.",
        senior_examples=[
            "A senior on Social Security living on $1,200/month who qualifies for a free phone through Lifeline",
            "A retiree who was paying $80/month for a plan when they qualified for a free or deeply discounted phone",
            "A grandparent who fell for a 'free government phone' scam website and needs to know the legitimate programs",
        ],
        source_urls=[
            {"label": "FCC Lifeline Program", "url": "https://www.fcc.gov/lifeline-consumers"},
            {"label": "USAC Lifeline", "url": "https://www.usac.org/lifeline/"},
            {"label": "FCC ACP Info", "url": "https://www.fcc.gov/acp"},
        ],
        seo_keywords=[
            "free cell phones seniors",
            "free government phone seniors",
            "Lifeline phone program",
            "free phone low income senior",
        ],
        suggested_tags=[
            "phones",
            "free-phone",
            "government-program",
            "Lifeline",
            "low-income",
            "seniors",
        ],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="best-flip-phones-seniors",
        title="Best Flip Phones for Seniors Who Want Simple",
        category_slug="senior-products",
        category_id=4,
        vertical="2B-phones",
        description="Guide to modern flip phones and simple phones for seniors who don't want a smartphone. Feature comparison (big buttons, loud speakers, SOS buttons, hearing aid compatibility), carrier options, cost comparison vs. smartphones, and the best flip phones available in 2026. Practical focus on ease of use.",
        senior_examples=[
            "An 82-year-old who just wants to make calls and send texts without touchscreen confusion",
            "A daughter looking for a simple phone for her father who keeps accidentally deleting apps on his smartphone",
            "A senior who switched from a $90/month smartphone plan to a $15/month flip phone plan and saved $900/year",
        ],
        source_urls=[
            {
                "label": "AARP Tech for Seniors",
                "url": "https://www.aarp.org/home-family/personal-technology/",
            },
            {
                "label": "FCC Hearing Aid Compatibility",
                "url": "https://www.fcc.gov/hearing-aid-compatibility-and-volume-control",
            },
            {
                "label": "Consumer Reports Phones",
                "url": "https://www.aarp.org/home-family/personal-technology/",
            },
        ],
        seo_keywords=[
            "best flip phones seniors",
            "simple phones for elderly",
            "flip phone for older adults",
            "easy cell phone seniors",
        ],
        suggested_tags=["phones", "flip-phone", "simple", "seniors", "ease-of-use", "cost-savings"],
        intent_tags=["compare", "decide", "save"],
        monetization_type="affiliate",
    ),
]

# ── Phase 3A-Insurance: Additional Insurance Topic Briefs (2 articles) ──────

PHASE_3A_INSURANCE_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="vision-insurance-seniors",
        title="Vision Insurance for Seniors: Your Options Explained",
        category_slug="insurance",
        category_id=2,
        vertical="1B-insurance",
        description="Guide to vision insurance options for seniors. Standalone vision plans, Medicare Advantage vision benefits, discount programs, online eyewear retailers, and when vision insurance is vs. isn't worth the premium. Cost comparison approach.",
        senior_examples=[
            "A retiree paying $600/year for glasses who discovered online retailers offering comparable quality for $100",
            "A senior whose Medicare Advantage plan included a $250 annual vision allowance they never used",
            "A couple comparing standalone vision insurance premiums vs. simply paying out of pocket for annual exams",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Eye Exams",
                "url": "https://www.medicare.gov/coverage",
            },
            {"label": "AAO Eye Health for Seniors", "url": "https://www.aao.org/eye-health"},
            {
                "label": "NEI Eye Health Information",
                "url": "https://www.nei.nih.gov/learn-about-eye-health",
            },
        ],
        seo_keywords=[
            "vision insurance seniors",
            "vision plans for retirees",
            "senior eye care options",
            "vision insurance worth it",
        ],
        suggested_tags=["insurance", "vision", "eye-care", "seniors", "cost-comparison"],
        intent_tags=["learn", "compare", "save"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="life-insurance-seniors-over-65",
        title="Life Insurance for Seniors Over 65: What to Know",
        category_slug="insurance",
        category_id=2,
        vertical="1B-insurance",
        description="Educational guide to life insurance options for seniors over 65. Term vs. whole life, guaranteed acceptance policies, final expense insurance, coverage amounts, factors affecting premiums, and questions to ask before purchasing. No specific company recommendations.",
        senior_examples=[
            "A 68-year-old widower wanting life insurance to cover funeral costs and leave something for grandchildren",
            "A retiree confused by guaranteed acceptance life insurance ads on TV and wondering about the fine print",
            "A couple reviewing their existing life insurance policy and discovering it may no longer be needed",
        ],
        source_urls=[
            {
                "label": "NAIC Life Insurance Guide",
                "url": "https://www.consumerfinance.gov/consumer-tools/",
            },
            {
                "label": "FTC.gov Insurance Tips",
                "url": "https://www.consumerfinance.gov/housing/housing-insure/",
            },
            {
                "label": "SSA.gov Survivors Benefits",
                "url": "https://www.ssa.gov/benefits/survivors/",
            },
        ],
        seo_keywords=[
            "life insurance seniors over 65",
            "life insurance for retirees",
            "senior life insurance options",
            "final expense insurance",
        ],
        suggested_tags=["insurance", "life-insurance", "seniors", "final-expense", "coverage"],
        intent_tags=["learn", "decide"],
        monetization_type="affiliate",
    ),
]

# ── Phase 3A-Finance: Finance Topic Briefs (2 articles) ─────────────────────

PHASE_3A_FINANCE_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="when-to-claim-social-security",
        title="When to Claim Social Security: A Plain-Language Guide",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="3A-finance",
        description="Plain-language guide to Social Security claiming strategy. Early (62) vs. full retirement age vs. delayed (70) benefits, spousal benefits, survivor benefits, working while claiming, and tax implications. Educational framing with real-dollar examples.",
        senior_examples=[
            "A 62-year-old debating whether to claim Social Security early or wait until 67 for full benefits",
            "A widow who didn't know she could claim survivor benefits while letting her own benefit grow until 70",
            "A couple strategizing when each spouse should claim to maximize their combined lifetime benefits",
        ],
        source_urls=[
            {
                "label": "SSA.gov Benefits Planner",
                "url": "https://www.ssa.gov/benefits/retirement/planner/claiming.html",
            },
            {
                "label": "SSA.gov Spousal Benefits",
                "url": "https://www.ssa.gov/benefits/retirement/planner/applying7.html",
            },
            {
                "label": "SSA.gov Calculator",
                "url": "https://www.ssa.gov/benefits/retirement/estimator.html",
            },
        ],
        seo_keywords=[
            "when to claim social security",
            "social security claiming strategy",
            "best age to claim social security",
            "social security benefits guide",
        ],
        suggested_tags=[
            "finance",
            "social-security",
            "retirement",
            "claiming-strategy",
            "benefits",
        ],
        intent_tags=["learn", "decide"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="tax-deductions-seniors-over-65",
        title="Tax Deductions Every Senior Over 65 Should Know",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="3A-finance",
        description="Guide to tax deductions and credits available to seniors over 65. Higher standard deduction, medical expense deduction, property tax exemptions, Social Security taxation thresholds, charitable giving strategies, and state-specific benefits. Educational framing - no personalized tax advice.",
        senior_examples=[
            "A retiree who didn't know seniors over 65 get a higher standard deduction and overpaid taxes for years",
            "A senior spending $8,000/year on medical expenses who didn't realize they could deduct amounts over 7.5% of AGI",
            "A homeowner who missed their state's senior property tax exemption worth $1,200/year",
        ],
        source_urls=[
            {
                "label": "IRS.gov Seniors Tax Guide",
                "url": "https://www.irs.gov/individuals/seniors-retirees",
            },
            {"label": "IRS.gov Standard Deduction", "url": "https://www.irs.gov/taxtopics/tc551"},
            {"label": "IRS.gov Medical Expenses", "url": "https://www.irs.gov/taxtopics/tc502"},
        ],
        seo_keywords=[
            "tax deductions seniors over 65",
            "senior tax breaks",
            "tax credits for retirees",
            "senior standard deduction",
        ],
        suggested_tags=["finance", "taxes", "deductions", "seniors", "retirement", "savings"],
        intent_tags=["save", "learn"],
        monetization_type="informational",
    ),
]

# ── SEO Phase: Community-Research-Driven Articles (10 articles) ───────────────

SEO_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="difficult-conversations-aging-parents-finances",
        title="How to Have Difficult Conversations With Aging Parents About Finances",
        category_slug="caregiving",
        category_id=6,
        vertical="SEO-finance",
        description="Comprehensive guide for adult children navigating sensitive financial conversations with aging parents. Covers when to start the conversation, how to approach it without being patronizing, what documents to ask about, how to handle resistance, and when to involve professionals. Focuses on maintaining dignity and trust. Emphasizes the savings angle: early conversations prevent costly emergencies (missed bills, fraud losses, unnecessary fees).",
        senior_examples=[
            "A daughter who noticed her 78-year-old father was paying the same utility bill twice each month but did not know how to bring it up without hurting his pride",
            "A son whose mother refused to discuss her finances until a phone scam cost her $8,000, and the family had to scramble to secure her accounts",
            "An adult child who discovered their parent had been paying $340/month for subscriptions they no longer used, but felt uncomfortable suggesting changes",
        ],
        source_urls=[
            {
                "label": "CFPB Managing Someone Else's Money",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "NIA Aging in Place",
                "url": "https://www.cdc.gov/falls/",
            },
            {
                "label": "FTC Elder Financial Exploitation",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
        ],
        seo_keywords=[
            "talking to aging parents about money",
            "difficult conversations aging parents finances",
            "how to discuss finances with elderly parents",
            "managing aging parents finances",
        ],
        suggested_tags=["finance", "family", "caregiving", "seniors", "communication", "planning"],
        intent_tags=["learn", "decide"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="tax-season-savings-seniors",
        title="Tax Season Savings for Seniors: Deductions and Credits You Might Be Missing",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO-finance",
        description="Hub-style article covering every tax deduction and credit available to seniors and retirees. Includes the extra standard deduction for 65+, medical expense deductions, property tax breaks, retirement income exclusions by state, charitable giving strategies (QCDs), and common mistakes that cost seniors money at tax time. Updated for the current tax year.",
        senior_examples=[
            "A retiree who did not know about the extra standard deduction for people 65 and older and overpaid by $1,850 for three years",
            "A senior who paid $4,200 in medical expenses last year and did not realize they could deduct amounts exceeding 7.5% of their income",
            "A couple who donated $3,000 from their IRA directly to charity using a Qualified Charitable Distribution and avoided paying income tax on the distribution",
        ],
        source_urls=[
            {
                "label": "IRS Tax Guide for Seniors (Pub 554)",
                "url": "https://www.irs.gov/publications/p554",
            },
            {
                "label": "IRS Standard Deduction",
                "url": "https://www.irs.gov/taxtopics/tc551",
            },
            {
                "label": "AARP Tax-Aide",
                "url": "https://www.aarp.org/money/taxes/aarp_taxaide/",
            },
        ],
        seo_keywords=[
            "senior tax deductions",
            "tax credits for retirees",
            "tax breaks for seniors over 65",
            "tax season savings retirees",
        ],
        suggested_tags=["finance", "taxes", "deductions", "seniors", "retirement", "savings"],
        intent_tags=["save", "learn"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="asset-protection-before-nursing-home",
        title="Asset Protection Before a Nursing Home: What Families Need to Know",
        category_slug="caregiving",
        category_id=6,
        vertical="SEO-finance",
        description="Authority article covering how families can protect assets before a loved one needs nursing home care. Explains Medicaid spend-down rules, the 5-year look-back period, exempt vs. countable assets, spousal protections (Community Spouse Resource Allowance), irrevocable trusts, and common planning mistakes. Focuses on what to do BEFORE a crisis, not during one. Emphasizes consulting an elder law attorney. No personalized financial advice.",
        senior_examples=[
            "A family that lost their parent's entire savings of $180,000 to nursing home costs because they did not understand Medicaid planning until it was too late",
            "A spouse who kept the family home because they learned about the Medicaid homestead exemption, while the other spouse received nursing home care",
            "A daughter who helped her parents set up an irrevocable trust 6 years before care was needed, protecting $250,000 in assets",
        ],
        source_urls=[
            {
                "label": "Medicaid.gov Eligibility",
                "url": "https://www.medicaid.gov/medicaid/eligibility/index.html",
            },
            {
                "label": "CFPB Managing Someone Else's Money",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "Medicare.gov Long-Term Care",
                "url": "https://www.medicare.gov/what-medicare-covers/what-part-a-covers/how-can-i-pay-for-nursing-home-care",
            },
        ],
        seo_keywords=[
            "asset protection nursing home",
            "Medicaid spend down rules",
            "protect assets from nursing home costs",
            "Medicaid planning for seniors",
        ],
        suggested_tags=[
            "finance",
            "medicaid",
            "nursing-home",
            "asset-protection",
            "seniors",
            "planning",
        ],
        intent_tags=["learn", "decide"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="helping-parent-financial-crisis",
        title="Helping a Parent in Financial Crisis: A Step-by-Step Guide for Adult Children",
        category_slug="caregiving",
        category_id=6,
        vertical="SEO-finance",
        description="Practical guide for adult children who discover a parent is in financial trouble (debt, missed bills, scam losses, or dwindling savings). Step-by-step approach: assess the situation, prioritize debts, find free resources, set up bill-pay systems, explore benefit programs, and protect against further losses. Addresses the emotional dimensions (guilt, role reversal, sibling disagreements) without being preachy. Email gate for a downloadable 'Emergency Financial Checklist for Aging Parents' PDF.",
        senior_examples=[
            "A son who discovered his mother had $12,000 in credit card debt she was hiding because she was embarrassed to ask for help",
            "A daughter whose father stopped paying his property taxes after his wife died and nearly lost the family home",
            "An adult child who found 47 unopened medical bills in their parent's desk drawer, totaling over $9,000",
        ],
        source_urls=[
            {
                "label": "CFPB Helping Older Adults",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "BenefitsCheckUp.org",
                "url": "https://www.benefitscheckup.org/",
            },
            {
                "label": "FTC Dealing with Debt",
                "url": "https://www.consumerfinance.gov/consumer-tools/debt-collection/",
            },
        ],
        seo_keywords=[
            "helping aging parent with finances",
            "parent in financial trouble",
            "senior parent debt help",
            "helping elderly parent manage money",
        ],
        suggested_tags=["finance", "debt", "caregiving", "seniors", "family", "crisis"],
        intent_tags=["learn", "decide"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="permission-to-spend-in-retirement",
        title="Permission to Spend in Retirement: Why It Is Okay to Enjoy Your Savings",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO-finance",
        description="Emotional SEO article addressing a common but rarely discussed problem: retirees who saved diligently their entire lives but feel paralyzed about spending any of it. Covers the psychology of the 'retirement spending gap,' why frugality can become unhealthy, how to create a 'spending plan' (not a budget), the concept of a 'fun fund,' and practical frameworks for deciding when spending is smart. Warm, permission-giving tone. Not financial advice, just emotional support and practical frameworks.",
        senior_examples=[
            "A retired teacher with $400,000 in savings who felt guilty buying a $200 pair of shoes even though she could afford it",
            "A couple who skipped a 50th anniversary trip because spending $5,000 felt irresponsible, then regretted it when one partner's health declined",
            "A retiree who kept driving a 15-year-old car despite having the savings for a reliable replacement, because 'what if I need that money later'",
        ],
        source_urls=[
            {
                "label": "SSA Retirement Benefits",
                "url": "https://www.ssa.gov/benefits/retirement/",
            },
            {
                "label": "NIA Healthy Aging",
                "url": "https://www.cdc.gov/falls/",
            },
            {
                "label": "CFPB Retirement Planning",
                "url": "https://www.consumerfinance.gov/consumer-tools/retirement/",
            },
        ],
        seo_keywords=[
            "permission to spend in retirement",
            "afraid to spend money in retirement",
            "retirement spending guilt",
            "how much can I spend in retirement",
        ],
        suggested_tags=["finance", "retirement", "spending", "psychology", "seniors", "wellness"],
        intent_tags=["learn", "decide"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="help-aging-parent-manage-money",
        title="How to Help an Aging Parent Manage Money Without Taking Over",
        category_slug="caregiving",
        category_id=6,
        vertical="SEO-finance",
        description="Authority article for adult children who need to help a parent manage finances while preserving their independence and dignity. Covers levels of involvement (monitoring vs. managing vs. power of attorney), tools and systems (autopay, simplified accounts, prepaid cards for discretionary spending), warning signs that more help is needed, legal documents to have in place, and how to involve siblings. Practical, respectful tone. Addresses the specific challenge of prepaid cards for spending control without infantilizing the parent.",
        senior_examples=[
            "A daughter who set up automatic bill pay for her mother's six recurring bills, eliminating late fees that were costing $45/month",
            "A son who gave his father a prepaid card loaded with $500/month for discretionary spending, which helped his dad feel independent while preventing overspending",
            "A family that used a shared checking account with view-only access so adult children could monitor transactions without controlling them",
        ],
        source_urls=[
            {
                "label": "CFPB Managing Someone Else's Money",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "NIA Getting Your Affairs in Order",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "FTC Signs of a Scam",
                "url": "https://reportfraud.ftc.gov/",
            },
        ],
        seo_keywords=[
            "help aging parent manage money",
            "managing elderly parents finances",
            "prepaid cards for elderly parents",
            "financial help for aging parents",
        ],
        suggested_tags=[
            "finance",
            "caregiving",
            "seniors",
            "money-management",
            "family",
            "independence",
        ],
        intent_tags=["learn", "decide"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="what-medicare-broker-does",
        title="What a Medicare Broker Actually Does for You",
        category_slug="medicare",
        category_id=1,
        vertical="SEO-medicare",
        description="Plain-language explainer of what Medicare brokers do, how they get paid (commissions from insurers, not you), the difference between brokers and agents, questions to ask before working with one, red flags to watch for, and when using a broker makes sense vs. going direct. Addresses common confusion about whether brokers are free, whether they are biased, and whether you need one at all. Practical, no-jargon tone.",
        senior_examples=[
            "A retiree who thought Medicare brokers charged a fee and avoided them, then spent 3 weeks confused by plan options before learning brokers are free to the consumer",
            "A senior who used a broker and got great help, but then received calls from 5 other brokers trying to switch their plan during Open Enrollment",
            "A couple who did not realize their 'independent broker' only sold plans from 3 carriers and missed a better option from another insurer",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Plan Finder",
                "url": "https://www.medicare.gov/plan-compare/",
            },
            {
                "label": "CMS Medicare & You Handbook",
                "url": "https://www.medicare.gov/publications/10050-medicare-and-you.pdf",
            },
            {
                "label": "NAIC Insurance Consumer Resources",
                "url": "https://content.naic.org/consumer",
            },
        ],
        seo_keywords=[
            "what does a Medicare broker do",
            "Medicare broker vs agent",
            "are Medicare brokers free",
            "do I need a Medicare broker",
        ],
        suggested_tags=["medicare", "brokers", "insurance", "seniors", "enrollment", "advice"],
        intent_tags=["learn", "decide"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="file-social-security-at-62-or-wait",
        title="File at 62 or Wait? How to Decide When to Claim Social Security",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO-finance",
        description="Comparison-style decision guide helping seniors decide when to claim Social Security. Covers the basics of early (62), full retirement age (66-67), and delayed (70) claiming. Includes break-even analysis, spousal strategies, the earnings test for those still working, tax implications, and how health and life expectancy factor in. Uses concrete dollar examples showing the difference between claiming at 62 vs. 67 vs. 70. Not personalized financial advice. Email gate for a 'Social Security Decision Worksheet' PDF.",
        senior_examples=[
            "A 61-year-old still working part-time who was told to file at 62 by a friend but did not understand the earnings test would reduce benefits",
            "A widow who did not know she could claim survivor benefits at 60 while letting her own benefit grow until 70",
            "A retiree who filed at 62 and receives $1,200/month, while a neighbor who waited until 70 gets $2,100/month for the same earnings history",
        ],
        source_urls=[
            {
                "label": "SSA When to Start Receiving Benefits",
                "url": "https://www.ssa.gov/benefits/retirement/planner/agereduction.html",
            },
            {
                "label": "SSA Earnings Test Calculator",
                "url": "https://www.ssa.gov/benefits/retirement/planner/whileworking.html",
            },
            {
                "label": "SSA Benefit Calculators",
                "url": "https://www.ssa.gov/benefits/retirement/estimator.html",
            },
        ],
        seo_keywords=[
            "file Social Security at 62 or wait",
            "when to claim Social Security",
            "Social Security claiming strategy",
            "Social Security break even age",
        ],
        suggested_tags=[
            "finance",
            "social-security",
            "retirement",
            "seniors",
            "claiming-strategy",
            "benefits",
        ],
        intent_tags=["decide", "compare", "learn"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="why-retirees-quit-budgeting-apps",
        title="Why Retirees Quit Budgeting Apps (And What Actually Works Instead)",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO-finance",
        description="Opinion-style article addressing why most budgeting apps fail for retirees. Covers the mismatch between app design (built for earners with variable income) and retiree needs (fixed income, irregular medical expenses, RMDs). Reviews why popular apps frustrate seniors: complex setup, subscription fatigue, privacy concerns with bank linking, and feature overload. Offers practical alternatives: envelope method, simple spreadsheet templates, Saverwell's ZIP-code discount finder, and the 'three accounts' system. Warm, validating tone that does not blame the user.",
        senior_examples=[
            "A retiree who tried 4 different budgeting apps and quit each one within a month because they required linking bank accounts, which felt like a security risk",
            "A senior who found that every budgeting app categorized his Social Security income incorrectly and required manual fixes every month",
            "A couple who realized they spent more time managing their budgeting app than they saved by using it",
        ],
        source_urls=[
            {
                "label": "CFPB Retirement Planning Tools",
                "url": "https://www.consumerfinance.gov/consumer-tools/retirement/",
            },
            {
                "label": "FTC Online Privacy",
                "url": "https://www.identitytheft.gov/",
            },
            {
                "label": "SSA Understanding Benefits",
                "url": "https://www.ssa.gov/benefits/retirement/",
            },
        ],
        seo_keywords=[
            "budgeting apps for retirees",
            "best budget app for seniors",
            "retirement budgeting tools",
            "simple budgeting for retirees",
        ],
        suggested_tags=["finance", "budgeting", "apps", "seniors", "retirement", "tools"],
        intent_tags=["learn", "compare"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="senior-scam-protection-complete-guide",
        title="The Complete Guide to Protecting Seniors from Scams",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO-finance",
        description="Comprehensive scam protection bundle covering the most common scams targeting seniors: phone scams (IRS, Social Security, grandparent scam), email phishing, romance scams, Medicare fraud, tech support scams, and investment scams. For each scam type: how it works, real warning signs, what to do if targeted, and how to report it. Includes a 'Scam Red Flags Checklist' section. Designed as the definitive resource families can bookmark and share. Email gate for a downloadable 'Senior Scam Protection PDF Guide' lead magnet.",
        senior_examples=[
            "A grandmother who received a frantic call from someone pretending to be her grandson asking for $5,000 bail money and nearly wired it before her daughter intervened",
            "A retiree who clicked a 'Medicare enrollment' email link that looked official and entered his Social Security number on a fake website",
            "A senior who lost $15,000 to a romance scam over 6 months and was too embarrassed to tell her family",
        ],
        source_urls=[
            {
                "label": "FTC Scam Alerts",
                "url": "https://reportfraud.ftc.gov/",
            },
            {
                "label": "FBI Elder Fraud",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
            {
                "label": "SSA Scam Awareness",
                "url": "https://www.ssa.gov/scam/",
            },
        ],
        seo_keywords=[
            "senior scam protection",
            "common scams targeting seniors",
            "how to protect elderly from scams",
            "senior fraud prevention guide",
        ],
        suggested_tags=[
            "finance",
            "scams",
            "fraud",
            "protection",
            "seniors",
            "safety",
            "identity-theft",
        ],
        intent_tags=["learn", "save"],
        monetization_type="lead_gen",
    ),
]

# ── SEO2 Phase: Workstream 4 SEO Articles (4 articles) ───────────────────────

SEO2_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="late-life-marriage-benefits-guide",
        title="Late-Life Marriage and Your Benefits: What Changes When You Say 'I Do' After 60",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO2-finance",
        description="SEO decision guide for seniors considering marriage later in life. Covers how marriage affects Social Security benefits (spousal benefits, survivor benefits, the 9-month and 10-year rules), Medicare premiums (IRMAA recalculation), pension survivor benefits, property and estate implications, Medicaid eligibility changes, and tax filing status. Includes a decision framework for couples weighing the financial pros and cons of remarriage vs. staying unmarried. Not legal or financial advice.",
        senior_examples=[
            "A 67-year-old widow receiving $2,400/month in survivor benefits who learned she would lose them if she remarried before age 60",
            "A couple in their 70s who married and discovered that combining incomes pushed them into a higher IRMAA bracket, increasing Medicare premiums by $400/month",
            "Two retirees who chose not to marry so one partner could keep Medicaid eligibility for long-term care",
        ],
        source_urls=[
            {
                "label": "SSA Marriage and Benefits",
                "url": "https://www.ssa.gov/benefits/retirement/planner/applying7.html",
            },
            {
                "label": "SSA Survivors Benefits",
                "url": "https://www.ssa.gov/benefits/survivors/",
            },
            {
                "label": "Medicare.gov Costs",
                "url": "https://www.medicare.gov/basics/costs/medicare-costs",
            },
        ],
        seo_keywords=[
            "marriage after 60 benefits",
            "late life marriage Social Security",
            "remarriage and Medicare",
            "getting married after retirement benefits",
        ],
        suggested_tags=[
            "finance",
            "marriage",
            "social-security",
            "medicare",
            "seniors",
            "retirement",
        ],
        intent_tags=["decide", "learn"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="how-to-spot-fake-financial-coach",
        title="How to Spot a Fake Financial Coach Targeting Seniors",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO2-finance",
        description="Authority article about predatory financial coaching and advisory scams targeting retirees. Covers red flags to watch for (guaranteed returns, high-pressure sales, upfront fees for 'free' seminars, unlicensed advisors), the difference between fiduciary and non-fiduciary advisors, how to verify credentials (FINRA BrokerCheck, SEC IAPD, CFP Board), questions to ask before hiring anyone, and what to do if you have been scammed. Bridges to the broader Saverwell scam protection content.",
        senior_examples=[
            "A retiree who paid $3,500 for a 'financial coaching package' from someone who turned out to have no credentials and gave advice that cost her thousands more",
            "A senior who attended a free dinner seminar about 'safe retirement strategies' and was pressured into buying a high-fee annuity he did not need",
            "A couple who discovered their 'financial advisor' was not registered with FINRA or the SEC after losing $25,000 in an unsuitable investment",
        ],
        source_urls=[
            {
                "label": "FINRA BrokerCheck",
                "url": "https://brokercheck.finra.org/",
            },
            {
                "label": "SEC Investment Adviser Search",
                "url": "https://adviserinfo.sec.gov/",
            },
            {
                "label": "FTC Financial Scams",
                "url": "https://reportfraud.ftc.gov/",
            },
        ],
        seo_keywords=[
            "fake financial coach scam",
            "spot a financial advisor scam",
            "financial advisor red flags seniors",
            "how to verify financial advisor",
        ],
        suggested_tags=["finance", "scams", "fraud", "advisors", "seniors", "protection"],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="why-are-glasses-expensive-after-60",
        title="Why Are Glasses So Expensive After 60? How Seniors Can Save on Eyewear",
        category_slug="insurance",
        category_id=2,
        vertical="SEO2-insurance",
        description="SEO article addressing the frustration of expensive eyewear for seniors. Covers why glasses cost more as you age (progressive lenses, coatings, stronger prescriptions), how vision insurance works (and when it is not worth it), Medicare's limited vision coverage, affordable alternatives (online retailers, warehouse clubs, nonprofit programs), and programs like AARP Vision Discounts, Lions Club, and EyeCare America. Practical savings focus with email gate for a 'Vision Savings Checklist' PDF.",
        senior_examples=[
            "A retiree who was quoted $800 for progressive lenses at a retail chain and found the same prescription online for $180",
            "A senior paying $15/month for vision insurance but only using it for a $75 annual exam, spending more on premiums than she saved",
            "A veteran who did not know the VA covers eye exams and glasses for qualifying conditions",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Eye Exams",
                "url": "https://www.medicare.gov/coverage",
            },
            {
                "label": "NEI Eye Health for Seniors",
                "url": "https://www.nei.nih.gov/learn-about-eye-health",
            },
            {
                "label": "AAO Eye Health",
                "url": "https://www.aao.org/eye-health",
            },
        ],
        seo_keywords=[
            "expensive glasses after 60",
            "save money on glasses seniors",
            "cheap glasses for seniors",
            "vision insurance worth it seniors",
        ],
        suggested_tags=["insurance", "vision", "glasses", "savings", "seniors", "eyewear"],
        intent_tags=["save", "learn", "compare"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="monthly-subscription-audit-retirees",
        title="Monthly Subscription Audit for Retirees: Find and Cancel What You Don't Need",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO2-finance",
        description="SEO landing page about subscription creep for retirees. Covers the average senior's hidden subscription spend ($200-400/month in common cases), a step-by-step audit process (bank statement review, app store subscriptions, annual-billing traps), the most common forgotten subscriptions for seniors (protection plans, streaming bundles, magazine renewals, gym memberships, unused insurance riders), negotiation tips for lower rates, and a printable audit worksheet. Positions Saverwell's ZIP code discount finder as a free alternative to paid discount subscription services.",
        senior_examples=[
            "A retiree who found 7 recurring charges totaling $142/month for services he forgot he signed up for, including a $9.99 'identity protection' plan and a $14.99 roadside assistance he already had through his auto insurance",
            "A senior who was paying $34/month for a streaming bundle but only watched one of the three services included",
            "A couple who saved $280/month after doing a full subscription audit and canceling duplicates and unused services",
        ],
        source_urls=[
            {
                "label": "CFPB Managing Your Money",
                "url": "https://www.consumerfinance.gov/consumer-tools/retirement/",
            },
            {
                "label": "FTC Negative Option Marketing",
                "url": "https://reportfraud.ftc.gov/",
            },
            {
                "label": "AARP Money Tips",
                "url": "https://www.aarp.org/money/budgeting-saving/",
            },
        ],
        seo_keywords=[
            "subscription audit retirees",
            "cancel subscriptions seniors",
            "hidden subscriptions costing money",
            "subscription management for retirees",
        ],
        suggested_tags=["finance", "subscriptions", "budgeting", "savings", "seniors", "audit"],
        intent_tags=["save", "learn"],
        monetization_type="informational",
    ),
]

# ── Phase SEO3: WS5 Finance Lead Magnets ────────────────────────────────────

SEO3_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="retirement-finances-reset-guide",
        title="Retirement Finances Reset: A Step-by-Step Guide to Getting Back on Track",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO3-finance",
        description="A step-by-step guide for retirees who feel their finances are off track, covering budget reassessment, expense reduction, benefit optimization, and creating a sustainable plan. Addresses the emotional weight of feeling behind, provides concrete action steps (not generic advice), and shows how small changes compound into meaningful savings over 12 months. Includes a printable reset worksheet.",
        senior_examples=[
            "A retired couple who realized their savings were depleting faster than expected and needed to restructure their monthly spending plan",
            "A 72-year-old widow who had never managed the household finances and felt overwhelmed after her husband passed, unsure where to start",
            "A retiree who took a lump-sum pension distribution that was supposed to last 20 years but was running low after 8 due to unchecked lifestyle inflation",
        ],
        source_urls=[
            {
                "label": "CFPB Retirement Planning Tools",
                "url": "https://www.consumerfinance.gov/consumer-tools/retirement/",
            },
            {
                "label": "SSA Retirement Benefits",
                "url": "https://www.ssa.gov/benefits/retirement/",
            },
        ],
        seo_keywords=[
            "retirement financial reset",
            "get finances on track retirement",
            "retirement budget reset guide",
            "fix finances in retirement",
        ],
        suggested_tags=["finance", "retirement", "budgeting", "planning"],
        intent_tags=["learn", "decide"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="dont-pay-it-back-yet-checklist",
        title="Don't Pay It Back Yet: What to Check Before Repaying Debt in Retirement",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO3-finance",
        description="A checklist for retirees considering accelerated debt repayment, covering when to pay off debt vs preserve liquidity, mortgage payoff analysis, and debt prioritization. Challenges the assumption that all debt is bad in retirement, explains when keeping a low-rate mortgage makes sense, addresses credit card vs medical debt vs mortgage tradeoffs, and provides a decision framework based on interest rates, tax implications, and emergency fund adequacy.",
        senior_examples=[
            "A retiree wondering whether to use $40,000 in savings to pay off their remaining mortgage balance or keep the cash for emergencies and healthcare costs",
            "A couple who paid off their house early and then faced an unexpected $18,000 home repair with no liquid savings left to cover it",
            "A senior carrying $6,000 in credit card debt at 22% interest while sitting on a $200,000 retirement account, unsure whether to take a distribution to pay it off",
        ],
        source_urls=[
            {
                "label": "CFPB Debt Collection Tools",
                "url": "https://www.consumerfinance.gov/consumer-tools/debt-collection/",
            },
            {
                "label": "AARP Money and Debt",
                "url": "https://www.aarp.org/money/",
            },
        ],
        seo_keywords=[
            "paying off debt in retirement",
            "should retirees pay off mortgage",
            "debt repayment retirement checklist",
            "retire with debt or pay it off",
        ],
        suggested_tags=["finance", "debt", "retirement", "checklist"],
        intent_tags=["decide", "learn"],
        monetization_type="lead_gen",
    ),
]

# ── Phase SEO4A: P1 Quick Wins (7 articles) ─────────────────────────────────

SEO4A_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="hidden-monthly-drains-retirees",
        title="The Hidden Monthly Drains Retirees Overlook",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Exposes monthly expenses retirees overpay for beyond subscriptions: "
            "insurance riders nobody uses, utility rate plans never optimized, "
            "grocery brand loyalty costing hundreds, unused bank maintenance fees, "
            "oversized data plans, and cheaper alternatives for everyday purchases. "
            "Framed as '$500/month you can reclaim' with specific dollar amounts per "
            "category. Goes broader than the existing subscription audit article. "
            "Related articles to link to: monthly-subscription-audit-retirees, "
            "retirement-finances-reset-guide, cut-phone-bill-after-65."
        ),
        senior_examples=[
            "A 68-year-old paying $45/month for a landline she never uses because she forgot to cancel it after getting a cell phone",
            "A retired couple discovering their auto insurance still includes commuter rates from when they drove to work daily",
            "A 72-year-old paying $15/month for a bank account that would be free if he switched to a senior checking account",
        ],
        source_urls=[
            {
                "label": "CFPB Money Management Tools",
                "url": "https://www.consumerfinance.gov/consumer-tools/money-as-you-grow/",
            },
            {
                "label": "FTC Consumer Information",
                "url": "https://www.consumerfinance.gov/consumer-tools/",
            },
            {
                "label": "BLS Consumer Expenditure Survey",
                "url": "https://www.bls.gov/cex/",
            },
        ],
        seo_keywords=[
            "hidden costs retirees ignore",
            "monthly spending drains retirement",
            "save 500 month retirement",
            "where retirees waste money",
        ],
        suggested_tags=["finance", "spending", "savings", "budget", "hidden-costs", "audit"],
        intent_tags=["save", "learn"],
    ),
    GuideTopicBrief(
        slug="medicare-savings-program-comparison",
        title="QMB vs. SLMB vs. QI-1: Medicare Savings Programs Compared",
        category_slug="medicare",
        category_id=1,
        vertical="SEO4-medicare",
        description=(
            "Comparison of the three Medicare Savings Programs that help low-income "
            "seniors pay Medicare premiums, deductibles, and coinsurance. Distinct "
            "from Extra Help (which covers Part D drugs). Covers income limits for "
            "each program, what each covers, how to apply through your state Medicaid "
            "office, and how to check eligibility. "
            "COMPLIANCE: Frame all insurance topics as educational. Never recommend "
            "specific plans. Always reference SHIP (1-877-839-2675) for free "
            "counseling. Include disclaimer: not insurance advice. "
            "Related articles to link to: medicare-extra-help-prescription-savings, "
            "save-money-medicare-premiums, medicare-explained-simple-guide."
        ),
        senior_examples=[
            "A 70-year-old on $1,200/month Social Security who qualifies for QMB but has never heard of it, paying $202/month in Part B premiums she cannot afford",
            "A couple earning $1,800/month combined who qualify for SLMB but assumed 'Medicaid' meant they were not eligible",
            "A 66-year-old just above the SLMB income limit who qualifies for QI-1 and could save $202/month on Part B premiums",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Savings Programs",
                "url": "https://www.medicare.gov/basics/costs/help/drug-costs",
            },
            {
                "label": "Benefits.gov QMB",
                "url": "https://www.benefits.gov/benefit/4412",
            },
            {
                "label": "Medicaid.gov",
                "url": "https://www.medicaid.gov/medicaid/eligibility/index.html",
            },
        ],
        seo_keywords=[
            "QMB vs SLMB vs QI",
            "medicare savings program eligibility",
            "medicare premium assistance low income",
            "medicare savings program comparison",
        ],
        suggested_tags=[
            "medicare",
            "savings-programs",
            "QMB",
            "SLMB",
            "QI-1",
            "low-income",
        ],
        intent_tags=["save", "compare"],
    ),
    GuideTopicBrief(
        slug="vehicle-costs-after-retirement",
        title="Managing Vehicle Costs on a Fixed Retirement Income",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Comprehensive guide to car costs in retirement. Covers whether to keep "
            "a car vs. go car-free, buying used vs. leasing, insurance optimization "
            "for low-mileage retirees, maintenance schedules that prevent costly "
            "repairs, fuel savings strategies, and total cost of ownership. Addresses "
            "the emotional difficulty of giving up driving and practical alternatives "
            "(rideshare credits, senior transit programs). "
            "Related articles to link to: auto-home-insurance-seniors, "
            "monthly-subscription-audit-retirees, retirement-finances-reset-guide."
        ),
        senior_examples=[
            "A retired teacher who cut her auto insurance by $800/year by switching to a low-mileage policy after she stopped commuting",
            "A 74-year-old weighing whether to replace his 15-year-old car or start using senior transit and Lyft",
            "A couple who sold their second car after retirement and save $6,000/year between payments, insurance, and maintenance",
        ],
        source_urls=[
            {
                "label": "CFPB Auto Finance Resources",
                "url": "https://www.consumerfinance.gov/consumer-tools/auto-loans/",
            },
            {
                "label": "FuelEconomy.gov",
                "url": "https://fueleconomy.gov/",
            },
            {
                "label": "Eldercare Locator Transportation",
                "url": "https://eldercare.acl.gov/Public/Index.aspx",
            },
        ],
        seo_keywords=[
            "car costs in retirement",
            "vehicle expenses fixed income",
            "should retirees keep a car",
            "auto costs after 65",
        ],
        suggested_tags=[
            "finance",
            "vehicle",
            "car",
            "insurance",
            "transportation",
            "savings",
        ],
        intent_tags=["save", "learn"],
    ),
    GuideTopicBrief(
        slug="protecting-vulnerable-seniors-money",
        title="How to Protect a Vulnerable Senior's Finances from Exploitation",
        category_slug="caregiving",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Covers financial exploitation by family members and caretakers (not "
            "external scams). Representative payee programs, power of attorney "
            "structures, guardianship basics, bank account safeguards (joint accounts "
            "vs. authorized signer), elder financial abuse warning signs, and "
            "reporting to adult protective services. Written for adult children and "
            "caregivers. "
            "COMPLIANCE: Frame all legal topics as educational. Never suggest "
            "specific legal actions. Always deflect to 'consult an elder law "
            "attorney in your state.' Include disclaimer: not legal advice. "
            "Related articles to link to: senior-scam-protection-complete-guide, "
            "help-aging-parent-manage-money, asset-protection-before-nursing-home."
        ),
        senior_examples=[
            "A daughter who discovered her brother had been withdrawing $500/month from their mother's bank account using a power of attorney meant for emergencies",
            "A 78-year-old whose hired caregiver gradually gained access to credit cards and ran up $12,000 in charges",
            "A son trying to set up a representative payee arrangement for his father with dementia, unsure of the legal steps",
        ],
        source_urls=[
            {
                "label": "CFPB Managing Someone Else's Money",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {
                "label": "Eldercare Locator",
                "url": "https://eldercare.acl.gov/Public/Index.aspx",
            },
            {
                "label": "SSA Representative Payee",
                "url": "https://www.ssa.gov/payee/",
            },
        ],
        seo_keywords=[
            "protect elderly parent money",
            "representative payee social security",
            "elder financial abuse signs",
            "protect senior from financial exploitation",
        ],
        suggested_tags=[
            "finance",
            "elder-abuse",
            "protection",
            "caregiver",
            "power-of-attorney",
            "guardianship",
        ],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="late-career-income-pivot",
        title="Late-Career Income Disruption: A Survival Guide for Workers 50+",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "For workers 50+ facing layoffs, industry changes, or health issues. "
            "Covers severance negotiation basics, bridging health insurance to "
            "Medicare, early Social Security considerations, skills-based pivot "
            "strategies, gig economy options for experienced professionals, and "
            "protecting retirement savings during the gap. Addresses the emotional "
            "weight of career disruption near retirement. "
            "Related articles to link to: retirement-finances-reset-guide, "
            "when-to-claim-social-security, file-social-security-at-62-or-wait."
        ),
        senior_examples=[
            "A 57-year-old IT manager laid off after 22 years who needs to bridge 8 years of health insurance before Medicare eligibility",
            "A 62-year-old retail worker whose store closed, weighing whether to claim Social Security early or find new work",
            "A 54-year-old nurse forced to stop working due to a back injury, navigating disability benefits and career alternatives",
        ],
        source_urls=[
            {
                "label": "DOL Career Resources for Older Workers",
                "url": "https://www.dol.gov/agencies/eta",
            },
            {
                "label": "SSA Retirement Planner",
                "url": "https://www.ssa.gov/benefits/retirement/planner/agereduction.html",
            },
            {
                "label": "CareerOneStop",
                "url": "https://www.careeronestop.org/",
            },
        ],
        seo_keywords=[
            "career change after 50",
            "late career layoff survival",
            "income disruption before retirement",
            "job loss at 55 what to do",
        ],
        suggested_tags=["finance", "career", "layoff", "income", "job-loss", "over-50"],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="medicare-advantage-red-flags-checklist",
        title="Medicare Advantage Red Flags: When Your MA Plan Is Working Against You",
        category_slug="medicare",
        category_id=1,
        vertical="SEO4-medicare",
        description=(
            "Checklist for frustrated MA enrollees. Covers shrinking provider "
            "networks, prior authorization delays, surprise balance billing, phantom "
            "benefits (dental/vision allowances with catches), misleading star "
            "ratings, and when switching back to Original Medicare makes sense. "
            "Includes AEP decision checklist. "
            "COMPLIANCE: Frame all insurance topics as educational. Never recommend "
            "specific plans. Always reference SHIP (1-877-839-2675) for free "
            "counseling. Include disclaimer: not insurance advice. "
            "Related articles to link to: medicare-advantage-vs-original, "
            "medicare-explained-simple-guide, medicare-enrollment-deadlines."
        ),
        senior_examples=[
            "A 72-year-old whose cardiologist left her MA network mid-year, leaving her scrambling for a new provider",
            "A retired couple whose MA plan advertised $2,000/year in dental benefits but the fine print limited coverage to a single cleaning and one filling",
            "A 69-year-old waiting 6 weeks for prior authorization on an MRI his doctor ordered urgently",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Plan Compare",
                "url": "https://www.medicare.gov/plan-compare/",
            },
            {
                "label": "CMS Medicare Advantage Info",
                "url": "https://www.cms.gov/medicare/enrollment-renewal/health-plans/MedicareAdvtgSpecRateStats",
            },
            {
                "label": "SHIP Helpline",
                "url": "https://www.shiphelp.org/",
            },
        ],
        seo_keywords=[
            "medicare advantage problems",
            "bad medicare advantage plan signs",
            "medicare advantage red flags",
            "switch from medicare advantage to original",
        ],
        suggested_tags=[
            "medicare",
            "advantage",
            "red-flags",
            "enrollment",
            "network",
            "prior-auth",
        ],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="what-seniors-actually-cut-first",
        title="What Retirees Actually Cut from Their Budget First (and What They Refuse To)",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Data-driven viral list based on community research about what retirees "
            "cut first when money gets tight. Covers the spending hierarchy and the "
            "categories seniors refuse to cut (healthcare, grandchildren, pet care). "
            "Includes counterintuitive frugality tactics that work long-term vs. "
            "ones that backfire. Designed for social sharing. "
            "Related articles to link to: monthly-subscription-audit-retirees, "
            "retirement-finances-reset-guide, why-retirees-quit-budgeting-apps."
        ),
        senior_examples=[
            "A retired firefighter who canceled premium cable ($180/month) but refused to give up his $15/month gym membership because it kept him healthy",
            "A 70-year-old grandmother who stopped buying brand-name groceries and saves $200/month but will not reduce spending on birthday gifts for her grandchildren",
            "A widower who switched from dining out 3x/week to cooking at home and saved $400/month, but kept his $50/month wine subscription because it is his one indulgence",
        ],
        source_urls=[
            {
                "label": "CFPB Money Management",
                "url": "https://www.consumerfinance.gov/consumer-tools/money-as-you-grow/",
            },
            {
                "label": "BLS Consumer Expenditure Survey",
                "url": "https://www.bls.gov/cex/",
            },
            {
                "label": "USA.gov Benefits",
                "url": "https://www.usa.gov/benefits",
            },
        ],
        seo_keywords=[
            "what retirees cut from budget first",
            "frugal living seniors",
            "retirement budget cuts",
            "what to cut when money is tight retirement",
        ],
        suggested_tags=["finance", "frugal", "budget", "spending", "retirement", "viral"],
        intent_tags=["learn", "save"],
    ),
]

# ── Phase SEO4B: P1 Lead Magnets + Trust Builders (5 articles) ──────────────

SEO4B_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="social-security-emergency-checklist",
        title="Social Security Emergency Checklist: What to Do When You Get a Scary SSA Notice",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Emergency response for overpayment demands, CDR reviews, and benefits "
            "reduction letters. Covers how to verify legitimacy vs. scam, appeal "
            "rights and deadlines, the waiver request process, repayment plans, and "
            "free legal help resources. "
            "COMPLIANCE: Frame all legal topics as educational. Never suggest "
            "specific legal actions. Always deflect to 'consult a legal aid "
            "attorney.' Include disclaimer: not legal advice. "
            "Related articles to link to: when-to-claim-social-security, "
            "senior-scam-protection-complete-guide, file-social-security-at-62-or-wait."
        ),
        senior_examples=[
            "A 68-year-old who received a $14,000 overpayment notice from SSA and panicked, not knowing she had 60 days to appeal",
            "A disabled veteran whose CDR notice felt like a threat to cut his benefits, though it turned out to be a routine review",
            "A widow whose late husband's overpayment was transferred to her, and she did not know she could request a waiver",
        ],
        source_urls=[
            {
                "label": "SSA Overpayment Recovery",
                "url": "https://www.ssa.gov/pubs/EN-05-10098.pdf",
            },
            {
                "label": "SSA Appeals Process",
                "url": "https://www.ssa.gov/appeals/",
            },
            {
                "label": "CFPB Financial Protection for Older Americans",
                "url": "https://www.consumerfinance.gov/consumer-tools/educator-tools/resources-for-older-adults/",
            },
        ],
        seo_keywords=[
            "social security overpayment notice",
            "social security overpayment waiver",
            "SSA overpayment appeal",
            "social security benefits reduced what to do",
        ],
        suggested_tags=[
            "finance",
            "social-security",
            "emergency",
            "overpayment",
            "appeal",
            "SSA",
        ],
        intent_tags=["learn", "decide"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="senior-fraud-protection-bundle",
        title="The Senior Fraud Survival Kit: Your Complete Protection Checklist",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Hub article bundling Saverwell's existing fraud protection content into "
            "a single gateway. Overviews the most common scam types targeting seniors "
            "with brief summaries and deep links to full dedicated articles. Gated as "
            "downloadable checklist for email capture. Positions Saverwell as the "
            "comprehensive authority on senior fraud protection. "
            "Related articles to link to: senior-scam-protection-complete-guide, "
            "how-to-spot-fake-financial-coach, protecting-vulnerable-seniors-money."
        ),
        senior_examples=[
            "A family who printed the checklist and taped it next to their 80-year-old mother's phone after she nearly fell for a grandparent scam call",
            "A retired postal worker who shared the kit with his entire neighborhood watch group",
            "A 65-year-old who used the checklist to identify a phishing email pretending to be from Medicare",
        ],
        source_urls=[
            {
                "label": "FTC Scam Alerts",
                "url": "https://reportfraud.ftc.gov/",
            },
            {
                "label": "FBI Elder Fraud",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
            {
                "label": "SSA Scam Awareness",
                "url": "https://www.ssa.gov/scam/",
            },
        ],
        seo_keywords=[
            "senior fraud protection guide",
            "senior scam checklist",
            "protect seniors from fraud",
            "senior fraud survival kit",
        ],
        suggested_tags=[
            "finance",
            "fraud",
            "scam",
            "protection",
            "checklist",
            "bundle",
        ],
        intent_tags=["learn", "save"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="auto-debt-after-60",
        title="Auto Debt After 60: Options When You Owe More Than Your Car Is Worth",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Guide for seniors carrying auto debt on fixed income. Covers when "
            "voluntary repossession makes financial sense vs. when it creates worse "
            "problems, negotiating with lenders for lower payments, being 'upside "
            "down' on a car loan, refinancing options, and credit score impacts. "
            "Non-judgmental tone. "
            "COMPLIANCE: Frame all financial topics as educational. Never recommend "
            "specific products or strategies. Use 'some retirees explore' not 'you "
            "should.' Include disclaimer: not financial advice, consult a licensed "
            "financial professional. "
            "Related articles to link to: dont-pay-it-back-yet-checklist, "
            "vehicle-costs-after-retirement, retirement-finances-reset-guide."
        ),
        senior_examples=[
            "A 63-year-old who owes $18,000 on a car worth $11,000 and is terrified of voluntary repossession destroying her credit before retirement",
            "A retired truck driver paying $450/month on a car loan that eats 30% of his Social Security check",
            "A 70-year-old who refinanced her auto loan from 9% to 4% and saved $150/month by calling her credit union",
        ],
        source_urls=[
            {
                "label": "CFPB Auto Loan Resources",
                "url": "https://www.consumerfinance.gov/consumer-tools/auto-loans/",
            },
            {
                "label": "FTC Dealing with Debt",
                "url": "https://www.consumerfinance.gov/consumer-tools/debt-collection/",
            },
            {
                "label": "USA.gov Consumer Complaints",
                "url": "https://www.usa.gov/consumer-complaints",
            },
        ],
        seo_keywords=[
            "car debt in retirement",
            "upside down car loan senior",
            "voluntary repossession consequences",
            "auto loan help retirees",
        ],
        suggested_tags=[
            "finance",
            "auto-debt",
            "car-loan",
            "refinance",
            "repossession",
            "fixed-income",
        ],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="financial-advisor-red-flags",
        title="Red Flags Your Financial Advisor May Not Be Acting in Your Best Interest",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "About legitimate but potentially harmful advisors (different from the "
            "existing fake-coach/scam article). Fee structure red flags (high-load "
            "funds, 12b-1 fees, wrap fees above 1.5%), suitability violations "
            "(aggressive portfolios for retirees), the fiduciary vs. suitability "
            "standard, how to check FINRA BrokerCheck and SEC IAPD, and when it may "
            "be time to seek a second opinion. "
            "COMPLIANCE: Frame all financial topics as educational. Never recommend "
            "specific advisors or firms. Use 'factors to consider' not 'you should "
            "switch.' Include disclaimer: not financial advice. "
            "Related articles to link to: how-to-spot-fake-financial-coach, "
            "senior-scam-protection-complete-guide, retirement-finances-reset-guide."
        ),
        senior_examples=[
            "A 71-year-old retiree whose advisor put 60% of her portfolio in aggressive growth funds despite her telling him she needed income stability",
            "A retired teacher who discovered her advisor was earning 5% commissions on every annuity he sold her, totaling $8,000 in fees she never knew about",
            "A 68-year-old who checked FINRA BrokerCheck and found his advisor had two customer disputes and a regulatory action she was never told about",
        ],
        source_urls=[
            {
                "label": "FINRA BrokerCheck",
                "url": "https://brokercheck.finra.org/",
            },
            {
                "label": "SEC Investment Adviser Search",
                "url": "https://www.investor.gov/",
            },
            {
                "label": "CFPB Financial Advisor Guide",
                "url": "https://www.consumerfinance.gov/consumer-tools/educator-tools/resources-for-older-adults/",
            },
        ],
        seo_keywords=[
            "financial advisor red flags",
            "is my financial advisor trustworthy",
            "bad financial advisor signs",
            "financial advisor complaints",
        ],
        suggested_tags=[
            "finance",
            "advisor",
            "red-flags",
            "fiduciary",
            "fees",
            "FINRA",
        ],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="sudden-loss-financial-checklist",
        title="Financial Steps After Losing a Spouse or Parent: A Checklist for the First 6 Months",
        category_slug="caregiving",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Step-by-step for the aftermath of a death. First 72 hours (securing "
            "accounts, notifying SSA, contacting insurance). First 30 days (probate "
            "basics, beneficiary claims, COBRA/Medicare transitions). First 6 months "
            "(retitling accounts, tax filing, survivor benefits). Written with deep "
            "empathy. "
            "COMPLIANCE: Frame all legal topics as educational. Never suggest "
            "specific legal actions. Always deflect to 'consult a probate or estate "
            "attorney in your state.' Include disclaimer: not legal advice. "
            "Related articles to link to: helping-parent-financial-crisis, "
            "asset-protection-before-nursing-home, when-to-claim-social-security."
        ),
        senior_examples=[
            "A 72-year-old widow who did not know she had only 2 years to apply for Social Security survivor benefits and nearly missed the window",
            "An adult daughter overwhelmed by her father's finances after his sudden death, discovering accounts and insurance policies she never knew existed",
            "A 65-year-old widower whose wife handled all the finances, now learning how to pay bills and manage accounts for the first time",
        ],
        source_urls=[
            {
                "label": "SSA Survivor Benefits",
                "url": "https://www.ssa.gov/benefits/survivors/",
            },
            {
                "label": "IRS Filing After Death",
                "url": "https://www.irs.gov/newsroom/tax-scams-consumer-alerts",
            },
            {
                "label": "CFPB Resources for Older Adults",
                "url": "https://www.consumerfinance.gov/consumer-tools/educator-tools/resources-for-older-adults/",
            },
        ],
        seo_keywords=[
            "financial checklist after death of spouse",
            "what to do financially when spouse dies",
            "financial steps after parent death",
            "survivor benefits checklist",
        ],
        suggested_tags=[
            "finance",
            "survivor",
            "death",
            "checklist",
            "probate",
            "benefits",
        ],
        intent_tags=["learn", "decide"],
    ),
]

# ── Phase SEO4C: P2 Retirement Planning Cluster (7 articles) ────────────────

SEO4C_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="government-knock-at-your-door-guide",
        title="What to Do If the Government Contacts You About Your Benefits",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Emergency guide for OIG visits, CDR second notices, SSA/IRS letters. "
            "How to verify legitimacy (badge checks, callback procedures), what a "
            "CDR actually means, your rights during OIG interviews, responding to "
            "benefit clawback notices, and when to immediately contact a lawyer. "
            "COMPLIANCE: Frame all legal topics as educational. Never suggest "
            "specific legal actions. Always deflect to 'consult a legal aid "
            "attorney.' Include disclaimer: not legal advice. "
            "Related articles to link to: senior-scam-protection-complete-guide, "
            "social-security-emergency-checklist, how-to-spot-fake-financial-coach."
        ),
        senior_examples=[
            "A 66-year-old on SSDI who received a CDR letter and assumed it meant his benefits were being cut, when it was actually a routine review",
            "A widow who got a letter from the SSA OIG requesting an interview about her late husband's benefits and did not know she could have an attorney present",
            "A 70-year-old who received what looked like an IRS audit notice but turned out to be a scam letter",
        ],
        source_urls=[
            {
                "label": "SSA OIG",
                "url": "https://oig.ssa.gov/",
            },
            {
                "label": "SSA CDR Information",
                "url": "https://www.ssa.gov/pubs/EN-05-10199.pdf",
            },
            {
                "label": "CFPB Older Adults",
                "url": "https://www.consumerfinance.gov/consumer-tools/educator-tools/resources-for-older-adults/",
            },
        ],
        seo_keywords=[
            "OIG visit what to do",
            "government knock at door senior",
            "social security review notice",
            "CDR second notice",
        ],
        suggested_tags=[
            "finance",
            "government",
            "OIG",
            "CDR",
            "benefits",
            "emergency",
        ],
        intent_tags=["learn", "decide"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="12-month-retirement-countdown-checklist",
        title="The 12-Month Retirement Countdown: A Month-by-Month Checklist",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "For people 6-18 months from retirement. Month-by-month action items: "
            "Social Security timing decisions, Medicare enrollment windows, employer "
            "benefits runoff, 401(k) rollover timing, health insurance bridge "
            "strategies, pension elections, and emergency fund targets. Each month "
            "has 3-5 specific items. Designed as interactive checklist with "
            "downloadable PDF version. "
            "Related articles to link to: when-to-claim-social-security, "
            "medicare-enrollment-deadlines, file-social-security-at-62-or-wait."
        ),
        senior_examples=[
            "A 64-year-old teacher planning to retire next June who has no idea when to sign up for Medicare or whether to take her pension as a lump sum",
            "A 63-year-old factory worker who wants to retire at 65 but has not yet checked whether his employer offers retiree health benefits",
            "A 61-year-old who just realized she needs to notify Social Security separately from her employer's HR department",
        ],
        source_urls=[
            {
                "label": "SSA Retirement Planner",
                "url": "https://www.ssa.gov/benefits/retirement/",
            },
            {
                "label": "Medicare.gov Getting Started",
                "url": "https://www.medicare.gov/basics/get-started-with-medicare",
            },
            {
                "label": "IRS Retirement Plans",
                "url": "https://www.irs.gov/retirement-plans",
            },
        ],
        seo_keywords=[
            "retirement countdown checklist",
            "12 month retirement plan",
            "preparing to retire checklist",
            "retirement planning timeline",
        ],
        suggested_tags=[
            "finance",
            "retirement",
            "checklist",
            "planning",
            "countdown",
            "pre-retirement",
        ],
        intent_tags=["learn", "decide"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="real-cost-of-delaying-retirement",
        title="The Real Cost of Delaying Retirement: Is Working Longer Worth It?",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Addresses whether waiting to retire truly pays off. Hidden costs of "
            "delaying (health deterioration, lost years), the financial math of "
            "working extra years (higher SS, more savings, shorter drawdown), "
            "breakeven analysis at different income levels, and non-financial factors "
            "people underweight. Different from 'when to claim SS' articles: this is "
            "about when to stop working. "
            "COMPLIANCE: Frame all financial topics as educational. Never recommend "
            "specific strategies. Use 'factors to consider' not 'you should.' "
            "Include disclaimer: not financial advice, consult a licensed financial "
            "professional. "
            "Related articles to link to: when-to-claim-social-security, "
            "file-social-security-at-62-or-wait, retirement-finances-reset-guide."
        ),
        senior_examples=[
            "A 64-year-old office manager debating whether working 3 more years is worth the larger Social Security check or if she is sacrificing her healthy years",
            "A 67-year-old who worked until 70 for the maximum SS benefit but now regrets missing time with grandchildren",
            "A 62-year-old weighing an early retirement offer against the pension increase from staying 3 more years",
        ],
        source_urls=[
            {
                "label": "SSA Retirement Planner Age Calculator",
                "url": "https://www.ssa.gov/benefits/retirement/planner/agereduction.html",
            },
            {
                "label": "SSA Quick Calculator",
                "url": "https://www.ssa.gov/OACT/quickcalc/",
            },
            {
                "label": "CFPB Planning for Retirement",
                "url": "https://www.consumerfinance.gov/consumer-tools/retirement/",
            },
        ],
        seo_keywords=[
            "cost of delaying retirement",
            "should I work longer before retiring",
            "is working until 70 worth it",
            "early retirement vs late retirement financially",
        ],
        suggested_tags=[
            "finance",
            "retirement",
            "delay",
            "working-longer",
            "breakeven",
            "social-security",
        ],
        intent_tags=["decide", "learn"],
    ),
    GuideTopicBrief(
        slug="forgotten-pension-recovery-guide",
        title="How to Find and Claim Forgotten Pension Benefits",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "For retirees who lost track of old pensions from previous employers. "
            "How to locate forgotten pensions (PBGC search, former employer HR, "
            "state unclaimed property databases), how pension activation works, what "
            "to do if your former employer merged or went bankrupt, lump sum vs. "
            "annuity election considerations, and rolling pension payouts into an "
            "IRA. "
            "COMPLIANCE: Frame all financial topics as educational. No specific "
            "investment recommendations for pension rollovers. Use 'options to "
            "explore' language. Include disclaimer: not financial advice, consult a "
            "licensed financial professional. "
            "Related articles to link to: when-to-claim-social-security, "
            "retirement-finances-reset-guide, 12-month-retirement-countdown-checklist."
        ),
        senior_examples=[
            "A 68-year-old who worked at a manufacturing company for 12 years in the 1990s and forgot he was vested in a pension until his former colleague mentioned receiving payments",
            "A 73-year-old whose former employer was acquired twice, and she has no idea which company now holds her pension",
            "A retired nurse who found $340/month in unclaimed pension benefits through the PBGC search tool after her daughter helped her look",
        ],
        source_urls=[
            {
                "label": "PBGC Find Pension Plan",
                "url": "https://www.pbgc.gov/search-plan",
            },
            {
                "label": "DOL Employee Benefits Security",
                "url": "https://www.dol.gov/agencies/ebsa",
            },
            {
                "label": "NAUPA Unclaimed Property",
                "url": "https://unclaimed.org/",
            },
        ],
        seo_keywords=[
            "find old pension from previous employer",
            "forgotten pension benefits",
            "PBGC unclaimed pension",
            "how to claim pension backpay",
        ],
        suggested_tags=[
            "finance",
            "pension",
            "unclaimed",
            "PBGC",
            "retirement",
            "benefits",
        ],
        intent_tags=["learn", "save"],
        monetization_type="lead_gen",
    ),
    GuideTopicBrief(
        slug="employer-to-medicare-transition-checklist",
        title="From Employer Insurance to Medicare: A Transition Checklist",
        category_slug="medicare",
        category_id=1,
        vertical="SEO4-medicare",
        description=(
            "For the 3-6 month window around retirement. Coordinating last day of "
            "employer coverage with Part B start date, COBRA bridge options and "
            "costs, Special Enrollment Period rules, avoiding Part B late enrollment "
            "penalty, prescription coverage gaps during transition, and retiree "
            "health benefits interaction with Medicare. "
            "COMPLIANCE: Frame all insurance topics as educational. Never recommend "
            "specific plans. Always reference SHIP (1-877-839-2675) for free "
            "counseling. Include disclaimer: not insurance advice. "
            "Related articles to link to: medicare-enrollment-deadlines, "
            "medicare-explained-simple-guide, when-to-claim-social-security."
        ),
        senior_examples=[
            "A 65-year-old who retired in March but did not realize she had to actively enroll in Part B within 8 months of losing employer coverage or face a permanent penalty",
            "A 66-year-old paying $750/month for COBRA who did not know Medicare Part B at $202/month was a cheaper option he should have switched to immediately",
            "A retired postal worker confused about whether his Federal Employee Health Benefits plan counts as creditable prescription coverage for Part D",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Getting Started",
                "url": "https://www.medicare.gov/basics/get-started-with-medicare",
            },
            {
                "label": "CMS Special Enrollment Period",
                "url": "https://www.cms.gov/medicare/enrollment-renewal/original-part-a-b",
            },
            {
                "label": "DOL COBRA Guide",
                "url": "https://www.dol.gov/agencies/ebsa/laws-and-regulations/laws/cobra",
            },
        ],
        seo_keywords=[
            "employer insurance to medicare transition",
            "retiring and starting medicare",
            "COBRA vs medicare",
            "medicare when you stop working",
        ],
        suggested_tags=[
            "medicare",
            "employer",
            "transition",
            "COBRA",
            "enrollment",
            "penalty",
        ],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="backdoor-roth-after-55",
        title="Backdoor Roth Conversions After 55: What Retirees Need to Know",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Educational explainer for workers/retirees over 55 considering backdoor "
            "Roth. The step-by-step conversion process, the pro-rata rule and its "
            "impact on people with existing traditional IRA balances, tax "
            "implications before and after retirement, the 5-year rule for "
            "distributions, and at what age/income levels conversion tends to be "
            "more or less favorable. "
            "COMPLIANCE: Frame all financial topics as educational. No personalized "
            "tax calculations. Use 'some retirees explore' not 'you should convert.' "
            "Include disclaimer: not financial or tax advice, consult a CPA or "
            "licensed financial advisor. "
            "Related articles to link to: tax-deductions-seniors-over-65, "
            "tax-season-savings-seniors, retirement-finances-reset-guide."
        ),
        senior_examples=[
            "A 58-year-old earning $160,000 who cannot contribute to a Roth IRA directly and wants to understand the backdoor option before she retires",
            "A 62-year-old with $200,000 in a traditional IRA who wants to convert but is worried about the tax bill in a single year",
            "A 67-year-old retiree in a low tax bracket considering converting $30,000/year to take advantage of lower marginal rates before RMDs start at 73",
        ],
        source_urls=[
            {
                "label": "IRS Roth IRAs",
                "url": "https://www.irs.gov/retirement-plans/roth-iras",
            },
            {
                "label": "IRS Rollovers of Retirement Distributions",
                "url": "https://www.irs.gov/retirement-plans/plan-participant-employee/rollovers-of-retirement-plan-and-ira-distributions",
            },
            {
                "label": "Investor.gov",
                "url": "https://www.investor.gov/",
            },
        ],
        seo_keywords=[
            "backdoor roth after 55",
            "roth conversion before retirement",
            "backdoor roth IRA older workers",
            "roth conversion tax implications retirement",
        ],
        suggested_tags=["finance", "roth", "conversion", "tax", "IRA", "retirement"],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="public-employee-retirement-guide",
        title="Public Employee Retirement: Pensions, Social Security, and the WEP Trap",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "For teachers, state workers, municipal employees. CalSTRS/CalPERS-style "
            "systems, the Windfall Elimination Provision (WEP) and Government "
            "Pension Offset (GPO) that reduce Social Security for public employees, "
            "pension vs. 457(b) withdrawal strategies, health benefits in retirement, "
            "and defined benefit vs. defined contribution. "
            "COMPLIANCE: Frame all financial topics as educational. No specific "
            "withdrawal strategy recommendations. Use 'factors to consider' "
            "language. Include disclaimer: not financial advice, consult a licensed "
            "financial professional. "
            "Related articles to link to: forgotten-pension-recovery-guide, "
            "when-to-claim-social-security, 12-month-retirement-countdown-checklist."
        ),
        senior_examples=[
            "A retired California teacher shocked to learn WEP reduced her Social Security check from $1,200 to $600 because of her CalSTRS pension",
            "A 62-year-old firefighter trying to understand whether to take his pension at 55 with a reduced benefit or wait until 60 for the full amount",
            "A municipal worker's spouse who discovered GPO will reduce her spousal Social Security benefit because of her husband's government pension",
        ],
        source_urls=[
            {
                "label": "SSA WEP Information",
                "url": "https://www.ssa.gov/benefits/retirement/planner/wep.html",
            },
            {
                "label": "SSA GPO Fact Sheet",
                "url": "https://www.ssa.gov/pubs/EN-05-10007.pdf",
            },
            {
                "label": "OPM Retirement Services",
                "url": "https://www.opm.gov/retirement-services/",
            },
        ],
        seo_keywords=[
            "public employee retirement guide",
            "CalSTRS retirement planning",
            "government pension and social security",
            "WEP GPO explained",
        ],
        suggested_tags=[
            "finance",
            "public-employee",
            "pension",
            "WEP",
            "GPO",
            "CalSTRS",
        ],
        intent_tags=["learn", "decide"],
    ),
]

# ── Phase SEO4D: P2 Tools, Comparison & Beginner (6 articles) ───────────────

SEO4D_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="free-budgeting-tools-retirees",
        title="The Best Free Budgeting Tools and Methods for Retirees",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Comparison of apps, spreadsheet templates, the envelope method, and "
            "pen-and-paper systems. Evaluates ease of use, fixed-income "
            "compatibility, security, and cost. Includes a 'which approach is right "
            "for you' decision matrix based on tech comfort level. Complements "
            "why-retirees-quit-budgeting-apps (which explains why apps fail; this "
            "shows what works instead). "
            "Related articles to link to: why-retirees-quit-budgeting-apps, "
            "monthly-subscription-audit-retirees, retirement-finances-reset-guide."
        ),
        senior_examples=[
            "A 72-year-old who tried Mint and YNAB but found them overwhelming, then switched to a simple paper envelope system that finally worked",
            "A retired accountant who built a simple Google Sheets template that tracks his fixed income against 6 spending categories",
            "A 65-year-old couple who use a shared notes app on their phones to log every purchase and review spending each Sunday morning over coffee",
        ],
        source_urls=[
            {
                "label": "CFPB Money Management",
                "url": "https://www.consumerfinance.gov/consumer-tools/money-as-you-grow/",
            },
            {
                "label": "MyMoney.gov",
                "url": "https://www.mymoney.gov/",
            },
            {
                "label": "USA.gov Managing Money",
                "url": "https://www.usa.gov/money",
            },
        ],
        seo_keywords=[
            "best free budgeting tools retirees",
            "budgeting app for fixed income",
            "free budget planner seniors",
            "retirement budget spreadsheet",
        ],
        suggested_tags=[
            "finance",
            "budgeting",
            "tools",
            "apps",
            "spreadsheet",
            "comparison",
        ],
        intent_tags=["compare", "learn"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="safe-yield-investments-after-60",
        title="Where to Put Your Money After 60: Lower-Risk Yield Options Explained",
        category_slug="retirement-taxes",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Educational guide to conservative yield strategies. Treasury bills and "
            "T-bill laddering, high-yield savings accounts, CDs, I Bonds, money "
            "market funds, and fixed annuities (with critical warnings about "
            "surrender charges and fees). Explains risk levels, tax implications, "
            "and realistic yield expectations for each. NOT investment advice. "
            "Addresses inflation risk of being too conservative. "
            "COMPLIANCE: Frame all financial topics as educational. Never recommend "
            "specific products or securities. Use 'some retirees explore' language. "
            "Include disclaimer: not investment advice, consult a licensed financial "
            "advisor. "
            "Related articles to link to: retirement-finances-reset-guide, "
            "permission-to-spend-in-retirement, dont-pay-it-back-yet-checklist."
        ),
        senior_examples=[
            "A 67-year-old with $150,000 in a savings account earning 0.5% who wants better returns but is terrified of losing money in the stock market",
            "A retired couple who built a simple 3-month T-bill ladder and earn 4%+ while keeping their money accessible",
            "A 71-year-old who bought a fixed annuity based on a seminar pitch and now regrets the 7-year surrender period locking up her money",
        ],
        source_urls=[
            {
                "label": "TreasuryDirect",
                "url": "https://www.treasurydirect.gov/",
            },
            {
                "label": "Investor.gov",
                "url": "https://www.investor.gov/",
            },
            {
                "label": "CFPB Retirement Planning",
                "url": "https://www.consumerfinance.gov/consumer-tools/retirement/",
            },
        ],
        seo_keywords=[
            "safe investments for retirees",
            "T-bill ladder retirement",
            "conservative yield after 60",
            "safe returns on retirement savings",
        ],
        suggested_tags=[
            "finance",
            "investing",
            "T-bills",
            "savings",
            "yield",
            "conservative",
        ],
        intent_tags=["learn", "compare"],
    ),
    GuideTopicBrief(
        slug="unexpected-cost-survival-playbook",
        title="The Unexpected Cost Survival Playbook for Retirees",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Emergency response for ER bills, home repairs, car breakdowns, or "
            "family crises. The first 48 hours (what NOT to do, who to call), "
            "hospital bill negotiation approaches, medical payment plan options, "
            "emergency home repair resources, tapping retirement accounts as a last "
            "resort (72(t) distributions, hardship withdrawals and their tax "
            "consequences), and nonprofit/community assistance resources. "
            "COMPLIANCE: Frame all financial topics as educational. No specific "
            "financial product recommendations. Use 'options to explore' language. "
            "Include disclaimer: not financial advice, consult a licensed financial "
            "professional. "
            "Related articles to link to: retirement-finances-reset-guide, "
            "helping-parent-financial-crisis, dont-pay-it-back-yet-checklist."
        ),
        senior_examples=[
            "A 69-year-old who got a $23,000 ER bill and did not know most hospitals have financial assistance programs for people on fixed income",
            "A retired widow whose furnace broke in January and needed $4,500 she did not have, not knowing her county had a senior home repair grant program",
            "A 73-year-old who withdrew $10,000 from his IRA for an emergency roof repair, not realizing the tax and potential penalty implications",
        ],
        source_urls=[
            {
                "label": "CFPB Medical Debt Resources",
                "url": "https://www.consumerfinance.gov/consumer-tools/debt-collection/",
            },
            {
                "label": "CMS No Surprises Act",
                "url": "https://www.cms.gov/nosurprises",
            },
            {
                "label": "HHS Health Resources",
                "url": "https://www.hhs.gov/programs/index.html",
            },
        ],
        seo_keywords=[
            "unexpected medical bill retirement",
            "emergency expenses on fixed income",
            "hospital bill help seniors",
            "emergency costs in retirement",
        ],
        suggested_tags=[
            "finance",
            "emergency",
            "medical-bill",
            "unexpected-costs",
            "survival",
            "fixed-income",
        ],
        intent_tags=["learn", "decide"],
    ),
    GuideTopicBrief(
        slug="fixed-income-debt-payoff-guide",
        title="7 Real Strategies for Paying Off Debt on a Fixed Retirement Income",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "Practical strategies adapted for retirees. Avalanche vs. snowball "
            "methods on fixed income, negotiating with creditors (medical debt, "
            "credit cards), debt consolidation options and risks, when bankruptcy "
            "may be a legitimate option to explore, debt collection rules after 65 "
            "(Social Security garnishment protections), and community resources for "
            "free debt counseling. Different from dont-pay-it-back-yet-checklist "
            "(which is about whether to pay; this is about how). "
            "COMPLIANCE: Frame all financial topics as educational. Never recommend "
            "bankruptcy or specific financial actions. Use 'some people explore' "
            "language. Include disclaimer: not financial or legal advice, consult a "
            "licensed professional. "
            "Related articles to link to: dont-pay-it-back-yet-checklist, "
            "retirement-finances-reset-guide, auto-debt-after-60."
        ),
        senior_examples=[
            "A 68-year-old who negotiated $14,000 in medical debt down to $4,200 by asking the hospital's financial assistance office for a hardship review",
            "A retired couple who called each credit card company and got interest rates reduced from 24% to 12% simply by explaining their fixed income situation",
            "A 71-year-old who was terrified of debt collectors calling until she learned that Social Security benefits cannot be garnished for most consumer debts",
        ],
        source_urls=[
            {
                "label": "CFPB Debt Collection",
                "url": "https://www.consumerfinance.gov/consumer-tools/debt-collection/",
            },
            {
                "label": "FTC Dealing with Debt",
                "url": "https://www.consumerfinance.gov/consumer-tools/debt-collection/",
            },
            {
                "label": "SSA Garnishment Protections",
                "url": "https://www.ssa.gov/pubs/EN-05-10153.pdf",
            },
        ],
        seo_keywords=[
            "paying off debt on fixed income",
            "debt payoff strategies retirees",
            "debt help for seniors",
            "get out of debt in retirement",
        ],
        suggested_tags=[
            "finance",
            "debt",
            "payoff",
            "negotiation",
            "collection",
            "fixed-income",
        ],
        intent_tags=["learn", "save"],
    ),
    GuideTopicBrief(
        slug="prescription-savings-comparison",
        title="Beyond Medicare Part D: Prescription Savings Programs Compared",
        category_slug="medicare",
        category_id=1,
        vertical="SEO4-medicare",
        description=(
            "Comparison of savings options beyond Part D. Programs like GoodRx and "
            "RxSaver, Mark Cuban's Cost Plus Drugs model, manufacturer patient "
            "assistance programs, 340B pharmacy programs, state pharmaceutical "
            "assistance programs (SPAPs), pill splitting strategies, and warehouse "
            "pharmacy options. Side-by-side cost comparisons for common senior "
            "medications. Positioned as a complement to, not replacement for, Part D. "
            "COMPLIANCE: Frame all financial topics as educational. Never recommend "
            "specific programs over Part D. Use 'options to explore' language. "
            "Include disclaimer: not medical or insurance advice, talk to your "
            "pharmacist and doctor. "
            "Related articles to link to: medicare-extra-help-prescription-savings, "
            "does-medicare-cover-prescriptions, save-money-medicare-premiums."
        ),
        senior_examples=[
            "A 70-year-old who saves $80/month on her cholesterol medication by using a discount program her pharmacist recommended after her Part D copay increased",
            "A retired veteran paying $300/month for a brand-name drug who found the same medication for $40/month through a manufacturer's patient assistance program",
            "A 66-year-old who did not know Costco pharmacy does not require a membership for prescriptions and saves $45/month on two medications",
        ],
        source_urls=[
            {
                "label": "Medicare.gov Drug Coverage",
                "url": "https://www.medicare.gov/drug-coverage-part-d",
            },
            {
                "label": "CFPB Prescription Costs",
                "url": "https://www.consumerfinance.gov/consumer-tools/educator-tools/resources-for-older-adults/",
            },
            {
                "label": "FDA Generic Drugs",
                "url": "https://www.fda.gov/drugs/generic-drugs",
            },
        ],
        seo_keywords=[
            "prescription savings programs seniors",
            "GoodRx alternatives seniors",
            "cheapest way to get prescriptions retired",
            "prescription drug discount comparison",
        ],
        suggested_tags=[
            "medicare",
            "prescriptions",
            "savings",
            "GoodRx",
            "pharmacy",
            "comparison",
        ],
        intent_tags=["compare", "save"],
        monetization_type="affiliate",
    ),
    GuideTopicBrief(
        slug="beginner-saver-guide-retirees",
        title="Starting from Scratch: A Beginner's Guide to Managing Money After 60",
        category_slug="saving-money",
        category_id=6,
        vertical="SEO4-finance",
        description=(
            "For retirees who never learned money management (surviving spouse who "
            "never handled finances, recent immigrant senior, lifelong "
            "paycheck-to-paycheck earner). Absolute basics: how to read a bank "
            "statement, setting up automatic bill pay, checking vs. savings accounts, "
            "building a first $500 emergency fund, and the one-page budget approach. "
            "Zero assumed knowledge. Zero judgment. Warm, encouraging tone. "
            "Related articles to link to: retirement-finances-reset-guide, "
            "monthly-subscription-audit-retirees, why-retirees-quit-budgeting-apps."
        ),
        senior_examples=[
            "A 71-year-old widow whose husband handled every bill for 48 years, now learning what a bank statement means for the first time",
            "A 65-year-old immigrant grandmother whose family handles her finances but who wants to understand where her Social Security check goes each month",
            "A 60-year-old who lived paycheck-to-paycheck his entire career and is now on a fixed Social Security income with no savings, wanting to start",
        ],
        source_urls=[
            {
                "label": "MyMoney.gov",
                "url": "https://www.mymoney.gov/",
            },
            {
                "label": "CFPB Money Management",
                "url": "https://www.consumerfinance.gov/consumer-tools/money-as-you-grow/",
            },
            {
                "label": "USA.gov Managing Money",
                "url": "https://www.usa.gov/money",
            },
        ],
        seo_keywords=[
            "financial literacy for seniors",
            "beginner budgeting retirees",
            "learning to manage money after 60",
            "basic money management seniors",
        ],
        suggested_tags=[
            "finance",
            "beginner",
            "literacy",
            "budget",
            "basics",
            "money-management",
        ],
        intent_tags=["learn"],
    ),
]

# ── Phase 5: Fraud Deep-Dives (6 articles) ──────────────────────────────────

PHASE_5_PROTECTION_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="ai-voice-cloning-scams",
        title="AI Voice Cloning and Deepfake Scams: How to Protect Yourself",
        category_slug="saving-money",
        category_id=8,
        vertical="5-protection",
        description="Deep-dive guide on AI voice cloning and deepfake scams targeting seniors. Covers how voice cloning technology works (as little as 3 seconds of audio), how fraudsters use deepfakes to impersonate family members and authority figures, real examples of AI-powered grandparent scams, how to verify callers using family code words, and what to do if you suspect a deepfake call. Surging search volume as AI scam reports increase 300%+ in 2025-2026.",
        senior_examples=[
            "A grandmother who received a call from what sounded exactly like her grandson crying, asking for $3,000 for bail - it was an AI clone of his voice scraped from a TikTok video",
            "A retiree who got a voicemail from what appeared to be their bank's fraud department, using a cloned voice of the actual branch manager they knew",
            "A couple who almost wired $10,000 after receiving a video call showing what looked like their daughter-in-law in a hospital - it was a deepfake",
        ],
        source_urls=[
            {
                "label": "FTC AI Scam Warnings",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
            {
                "label": "FBI IC3 Elder Fraud Report",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
            {"label": "AARP AI Scam Guide", "url": "https://www.aarp.org/money/scams-fraud/"},
        ],
        seo_keywords=[
            "AI voice cloning scam",
            "deepfake scam seniors",
            "voice cloning fraud",
            "AI phone scam protection",
            "deepfake grandparent scam",
        ],
        suggested_tags=["protection", "ai-scams", "voice-cloning", "deepfake", "fraud", "seniors"],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="grandparent-scam-how-to-protect",
        title="The Grandparent Scam: How It Works and How to Stop It",
        category_slug="saving-money",
        category_id=8,
        vertical="5-protection",
        description="Comprehensive guide to the grandparent scam - one of the most emotionally manipulative frauds targeting seniors. Covers how the scam works (urgent calls pretending to be grandchildren in trouble), the psychology behind why it works, real dollar losses (FBI reports seniors lost $1.3B to impersonation scams in 2023), family code word strategy, what to do during a suspicious call, how to report it, and how the scam has evolved with AI voice cloning. Written to empower without inducing fear.",
        senior_examples=[
            "A 78-year-old grandfather who wired $5,000 to bail out his 'grandson' - only to discover his real grandson was safe at college",
            "A grandmother who caught the scam because her family had established a code word system after reading about it",
            "A retiree who received three grandparent scam calls in one month, each time with a different 'grandchild' name",
        ],
        source_urls=[
            {
                "label": "FTC Imposter Scams",
                "url": "https://reportfraud.ftc.gov/",
            },
            {
                "label": "FBI Elder Fraud Report",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
            {
                "label": "AARP Grandparent Scam",
                "url": "https://www.aarp.org/money/scams-fraud/info-2019/grandparent.html",
            },
        ],
        seo_keywords=[
            "grandparent scam",
            "grandparent phone scam",
            "grandchild emergency scam",
            "how to stop grandparent scam",
            "family impersonation scam",
        ],
        suggested_tags=[
            "protection",
            "grandparent-scam",
            "impersonation",
            "phone-scam",
            "fraud",
            "family",
        ],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="tech-support-scams-seniors",
        title="Tech Support Scams: What Seniors Need to Know",
        category_slug="saving-money",
        category_id=8,
        vertical="5-protection",
        description="Deep-dive guide on tech support scams - the #1 fraud type targeting seniors by call volume. Covers pop-up warnings, fake virus alerts, remote access tricks, refund scams (a newer variant where scammers claim to have overcharged you), how they gain access to bank accounts through screen sharing, the Microsoft/Apple impersonation playbook, and how to safely handle real computer problems. Includes a clear action plan for what to do if you already gave remote access.",
        senior_examples=[
            "A retiree who called a number from a browser pop-up claiming their computer had a virus, and the 'technician' installed software that captured their banking passwords",
            "A senior who let a tech support scammer access their computer for a $299 'repair' - then the scammer returned months later claiming a refund was owed, and stole $8,000 through a fake refund process",
            "A 75-year-old who received a call from 'Microsoft' saying their Windows license was expiring and needed to be renewed for $199",
        ],
        source_urls=[
            {
                "label": "FTC Tech Support Scams",
                "url": "https://support.microsoft.com/en-us/windows/protect-yourself-from-online-scams-and-attacks",
            },
            {
                "label": "FBI IC3 Tech Support Fraud",
                "url": "https://www.ic3.gov/",
            },
            {
                "label": "Microsoft Scam Protection",
                "url": "https://support.microsoft.com/en-us/windows/protect-yourself-from-online-scams-and-attacks",
            },
        ],
        seo_keywords=[
            "tech support scam",
            "tech support scam seniors",
            "fake virus warning scam",
            "computer scam elderly",
            "Microsoft tech support scam",
        ],
        suggested_tags=[
            "protection",
            "tech-support",
            "computer-scam",
            "remote-access",
            "fraud",
            "seniors",
        ],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="irs-tax-phone-scams",
        title="IRS and Tax Phone Scams: How to Spot Them Instantly",
        category_slug="saving-money",
        category_id=8,
        vertical="5-protection",
        description="Definitive guide to IRS impersonation and tax-related phone scams. Covers how the IRS actually contacts you (always by mail first), common scripts fraudsters use, seasonal spikes (January-April and October-November), gift card payment demands, spoofed caller ID showing IRS numbers, the 'tax lien' threat, identity theft tax refund fraud, and state tax agency impersonation. Includes exact phrases the real IRS will never say. Timed for pre-tax-season publishing to capture January search spike.",
        senior_examples=[
            "A retiree who received a call threatening arrest for unpaid taxes and was told to buy $2,000 in iTunes gift cards as payment - the caller ID showed a Washington, D.C. number",
            "A senior who received an official-looking letter with a fake IRS letterhead demanding immediate payment to a P.O. box - they called the real IRS and confirmed it was fake",
            "A couple whose tax refund was stolen by an identity thief who filed a fraudulent return using their Social Security numbers before they filed",
        ],
        source_urls=[
            {
                "label": "IRS.gov Scam Alerts",
                "url": "https://www.irs.gov/newsroom/tax-scams-consumer-alerts",
            },
            {
                "label": "FTC IRS Impersonation",
                "url": "https://reportfraud.ftc.gov/",
            },
            {"label": "TIGTA Report Scams", "url": "https://www.treasury.gov/tigta/"},
        ],
        seo_keywords=[
            "IRS phone scam",
            "IRS scam call",
            "tax scam seniors",
            "fake IRS call",
            "IRS impersonation scam",
        ],
        suggested_tags=[
            "protection",
            "irs-scam",
            "tax-fraud",
            "phone-scam",
            "impersonation",
            "seniors",
        ],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="romance-scams-targeting-seniors",
        title="Romance Scams Targeting Seniors: Warning Signs and How to Stay Safe",
        category_slug="saving-money",
        category_id=8,
        vertical="5-protection",
        description="Sensitive, empathetic guide to romance scams targeting older adults. Covers how romance scams work (the long con - weeks or months of emotional grooming), why seniors are especially vulnerable (loneliness after losing a spouse, isolation), red flags to watch for, the financial progression (small requests escalating to large), cryptocurrency and investment romance hybrids ('pig butchering'), how to verify someone's identity, and where to get help. Written with zero shame or blame - romance scams are sophisticated fraud, not a character flaw.",
        senior_examples=[
            "A 70-year-old widow who met a 'retired military officer' on Facebook who spent 4 months building a relationship before asking for $20,000 for a 'medical emergency' overseas",
            "A retiree who lost $85,000 to a romance scammer who convinced him to invest in cryptocurrency through a fake trading platform",
            "A senior who was too embarrassed to tell her family she had been sending money to someone she met online for over a year - she only came forward after the total reached $40,000",
        ],
        source_urls=[
            {
                "label": "FTC Romance Scams",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
            {
                "label": "FBI Romance Fraud",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
            {
                "label": "AARP Romance Scams",
                "url": "https://www.aarp.org/money/scams-fraud/info-2019/romance.html",
            },
        ],
        seo_keywords=[
            "romance scam seniors",
            "online dating scam elderly",
            "romance fraud older adults",
            "catfishing seniors",
            "love scam warning signs",
        ],
        suggested_tags=[
            "protection",
            "romance-scam",
            "online-dating",
            "fraud",
            "emotional-manipulation",
            "seniors",
        ],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="investment-scams-targeting-seniors",
        title="Investment Scams Targeting Seniors: What to Watch For",
        category_slug="saving-money",
        category_id=8,
        vertical="5-protection",
        description="Authority guide to investment scams targeting seniors and retirees. Covers Ponzi schemes, pump-and-dump stock schemes, cryptocurrency fraud, precious metals scams, unregistered securities, seminar-based high-pressure selling, affinity fraud (targeting through churches and community groups), and the growing 'pig butchering' investment scam trend. Includes how to verify investment advisors through FINRA BrokerCheck and SEC EDGAR, and the difference between legitimate and fraudulent investment opportunities. Educational framing - no personalized investment advice.",
        senior_examples=[
            "A retired teacher who invested $50,000 in a 'guaranteed 12% return' CD offered by someone at a church-sponsored financial seminar - it was an unregistered security",
            "A senior couple who were convinced by a friend to invest in a cryptocurrency platform promising 20% monthly returns - it was a Ponzi scheme that collapsed after 6 months",
            "A retiree who lost $30,000 in gold coins purchased from a TV ad promising 'safe haven' returns, only to discover the coins were marked up 300% over spot price",
        ],
        source_urls=[
            {"label": "SEC Investor Alerts", "url": "https://www.sec.gov/investor/alerts"},
            {"label": "FINRA BrokerCheck", "url": "https://brokercheck.finra.org/"},
            {
                "label": "FBI Investment Fraud",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
        ],
        seo_keywords=[
            "investment scam seniors",
            "senior investment fraud",
            "financial scam elderly",
            "Ponzi scheme seniors",
            "cryptocurrency scam retirees",
        ],
        suggested_tags=[
            "protection",
            "investment-scam",
            "financial-fraud",
            "ponzi-scheme",
            "crypto",
            "seniors",
        ],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
]

# ── Phase 6: Discount Hub Pages (3 articles) ──────────────────────────────────

PHASE_6_DISCOUNTS_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="restaurant-senior-discounts",
        title="Restaurant Senior Discounts: The Complete List",
        category_slug="saving-money",
        category_id=9,
        vertical="6-discounts",
        description="Comprehensive hub page listing every major restaurant chain offering senior discounts. Organized by category (fast food, casual dining, coffee shops). Each entry includes: discount details (percentage or dollar amount), age requirement, whether it's every day or specific days, how to claim it (ask at register, show ID, app-based). Built from existing Saverwell merchant data. Includes tips for maximizing restaurant savings and a printable quick-reference card.",
        senior_examples=[
            "A retiree who eats out 3 times a week and didn't know most restaurants offer 10-15% senior discounts just by asking",
            "A couple who saved $600/year by consistently asking for senior discounts at restaurants they already frequented",
            "A senior who was embarrassed to ask for the discount until she learned most cashiers expect it and some restaurants give it automatically",
        ],
        source_urls=[
            {
                "label": "AARP Dining Discounts",
                "url": "https://www.aarp.org/benefits-discounts/",
            },
            {"label": "Saverwell Discounts", "url": "https://www.saverwell.com/discounts"},
            {
                "label": "SeniorLiving.org Discounts",
                "url": "https://www.aarp.org/benefits-discounts/",
            },
        ],
        seo_keywords=[
            "restaurant senior discounts",
            "senior discounts restaurants",
            "fast food senior discounts",
            "restaurant discounts over 55",
            "senior meal deals",
        ],
        suggested_tags=["discounts", "restaurants", "dining", "fast-food", "seniors", "savings"],
        intent_tags=["save", "learn"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="grocery-store-senior-discounts",
        title="Grocery Store Senior Discounts: Where to Save on Groceries",
        category_slug="saving-money",
        category_id=9,
        vertical="6-discounts",
        description="Comprehensive hub page listing every major grocery chain offering senior discounts. Organized by chain with specific details: discount percentage, qualifying age, which day(s) of the week, whether it requires a loyalty card, and any exclusions. Built from existing Saverwell merchant data. Includes grocery savings tips beyond discounts (shopping timing, store brands, clearance sections, SNAP benefits for eligible seniors).",
        senior_examples=[
            "A senior who switched her weekly grocery shopping to Tuesdays and saved 10% at her local store's senior discount day",
            "A retiree on a fixed income who combined senior discount day with digital coupons and store brand substitutions to cut his grocery bill by 30%",
            "A couple who didn't realize their grocery store offered a 5% senior discount every day on store-brand products",
        ],
        source_urls=[
            {
                "label": "USDA SNAP for Seniors",
                "url": "https://www.fns.usda.gov/snap/supplemental-nutrition-assistance-program",
            },
            {"label": "Saverwell Discounts", "url": "https://www.saverwell.com/discounts"},
            {
                "label": "AARP Grocery Savings",
                "url": "https://www.aarp.org/money/budgeting-saving/",
            },
        ],
        seo_keywords=[
            "grocery store senior discounts",
            "senior discount grocery day",
            "grocery discounts for seniors",
            "save on groceries seniors",
            "senior grocery savings",
        ],
        suggested_tags=[
            "discounts",
            "grocery",
            "food-savings",
            "seniors",
            "weekly-deals",
            "savings",
        ],
        intent_tags=["save", "learn"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="senior-travel-discounts",
        title="Senior Travel Discounts: Airlines, Hotels, and More",
        category_slug="saving-money",
        category_id=9,
        vertical="6-discounts",
        description="Hub page covering senior travel discounts across all major categories: airlines (which ones still offer senior fares), hotels (AARP, AAA, and chain-specific programs), car rentals, Amtrak (15% discount for 65+), national parks (lifetime pass for $80 at 62+), cruises, and tour operators. Includes honest assessment of which 'senior discounts' are actually good deals vs. marketing gimmicks. Tips for booking strategies, best times to travel for savings, and travel insurance considerations.",
        senior_examples=[
            "A retiree who bought an America the Beautiful Senior Pass for $80 and saved over $300 in national park entry fees in one year",
            "A couple who saved $400 on Amtrak by using the 15% senior discount for their cross-country trip",
            "A senior who compared a hotel's 'senior rate' to online prices and discovered the online rate was actually $20/night cheaper",
        ],
        source_urls=[
            {"label": "NPS Senior Pass", "url": "https://www.nps.gov/planyourvisit/passes.htm"},
            {"label": "Amtrak Senior Discount", "url": "https://www.amtrak.com/deals-discounts"},
            {"label": "AARP Travel Benefits", "url": "https://www.aarp.org/travel/"},
        ],
        seo_keywords=[
            "senior travel discounts",
            "travel discounts for seniors",
            "airline senior discounts",
            "hotel senior discounts",
            "senior travel deals",
        ],
        suggested_tags=["discounts", "travel", "airlines", "hotels", "national-parks", "seniors"],
        intent_tags=["save", "learn", "compare"],
        monetization_type="affiliate",
    ),
]

# ── Phase 7: Caregiving Resources (4 articles) ─────────────────────────────────

PHASE_7_CAREGIVING_TOPICS: List[GuideTopicBrief] = [
    GuideTopicBrief(
        slug="protect-aging-parents-from-scams",
        title="How to Protect Your Aging Parents from Scams",
        category_slug="caregiving",
        category_id=10,
        vertical="7-caregiving",
        description="Anchor guide for the caregiving section. Written for adult children who want to protect their aging parents from financial fraud. Covers the most common scams targeting seniors (summary with links to deep-dive guides), warning signs that a parent may be targeted, practical protective steps (call blocking, credit freezes, bank alerts, power of attorney), how to have the conversation without being patronizing, technology tools for monitoring, and what to do if fraud has already occurred. Bridges the protection and caregiving missions.",
        senior_examples=[
            "A daughter who set up call blocking and credit freezes for her 80-year-old mother after a neighbor was scammed for $15,000",
            "An adult child who noticed their father was receiving 20+ scam calls per day but didn't know how to help without seeming controlling",
            "A family that established a 'two-person rule' where their mother agreed to check with a family member before any financial decision over $500",
        ],
        source_urls=[
            {
                "label": "CFPB Protecting Older Adults",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
            {"label": "FTC Scam Resources", "url": "https://reportfraud.ftc.gov/"},
            {
                "label": "FBI Elder Fraud",
                "url": "https://www.ic3.gov/AnnualReport/Reports/2024_IC3ElderFraudReport.pdf",
            },
        ],
        seo_keywords=[
            "protect aging parents from scams",
            "how to protect elderly parent from fraud",
            "senior parent scam protection",
            "prevent elder financial abuse",
            "help parent avoid scams",
        ],
        suggested_tags=[
            "caregiving",
            "scam-protection",
            "family",
            "elder-fraud",
            "prevention",
            "seniors",
        ],
        intent_tags=["learn", "save"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="signs-parent-getting-scammed",
        title="Signs Your Parent May Be Getting Scammed",
        category_slug="caregiving",
        category_id=10,
        vertical="7-caregiving",
        description="Practical checklist-style guide helping adult children recognize when an aging parent may be the target or victim of a scam. Covers behavioral warning signs (secrecy, new 'friend' they won't discuss, unusual purchases, confusion about finances), financial red flags (unexpected withdrawals, new accounts, gift card purchases, wire transfers), mail and phone indicators (stacks of sweepstakes mail, frequent unfamiliar calls), and emotional signs (anxiety, shame, defensiveness about money). Includes how to approach the conversation with empathy and what immediate steps to take if you confirm fraud.",
        senior_examples=[
            "A son who noticed his mother was buying large quantities of gift cards and discovered she was being coached by a scammer to send the card numbers",
            "A daughter who found a pile of sweepstakes 'winner' letters in her father's desk, each requesting a 'processing fee' - he had already sent $3,000 in checks",
            "An adult child whose parent suddenly became secretive about phone calls and money, which turned out to be a romance scammer extracting funds over months",
        ],
        source_urls=[
            {
                "label": "AARP Warning Signs",
                "url": "https://www.aarp.org/money/scams-fraud/",
            },
            {
                "label": "NCOA Elder Financial Abuse",
                "url": "https://www.ncoa.org/article/get-the-facts-on-elder-abuse",
            },
            {
                "label": "FTC Reporting Fraud",
                "url": "https://reportfraud.ftc.gov/",
            },
        ],
        seo_keywords=[
            "signs parent being scammed",
            "signs elderly parent being taken advantage of",
            "elder financial abuse warning signs",
            "how to tell if parent is scam victim",
            "senior scam warning signs family",
        ],
        suggested_tags=[
            "caregiving",
            "warning-signs",
            "elder-fraud",
            "family",
            "detection",
            "seniors",
        ],
        intent_tags=["learn", "decide"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="rep-payee-guide",
        title="How to Become a Rep Payee Without Making Costly Mistakes",
        category_slug="caregiving",
        category_id=10,
        vertical="7-caregiving",
        description="Authoritative guide for adult children who need to become a Representative Payee for a parent receiving Social Security benefits. Covers what a Rep Payee is (vs. power of attorney - different systems), who qualifies, the SSA application process, legal responsibilities, record-keeping requirements, common mistakes that trigger SSA audits, how to handle the money properly (dedicated account, no commingling), annual accounting requirements, and when a Rep Payee arrangement is appropriate vs. other options. Includes real cost examples of mistakes. Unparked from Product Ideas Row 34.",
        senior_examples=[
            "A daughter who became Rep Payee for her father with dementia but didn't know she needed to keep a separate bank account and got flagged in an SSA audit",
            "A son who spent 6 months navigating the SSA application process to become Rep Payee for his mother, only to discover he needed to file annual accounting reports",
            "An adult child who assumed power of attorney covered Social Security benefits and was surprised to learn Rep Payee is a completely separate SSA designation",
        ],
        source_urls=[
            {"label": "SSA Representative Payee", "url": "https://www.ssa.gov/payee/"},
            {
                "label": "SSA Guide for Rep Payees",
                "url": "https://www.ssa.gov/pubs/EN-05-10076.pdf",
            },
            {
                "label": "CFPB Managing Someone Else's Money",
                "url": "https://www.consumerfinance.gov/consumer-tools/managing-someone-elses-money/",
            },
        ],
        seo_keywords=[
            "representative payee",
            "how to become rep payee",
            "Social Security representative payee",
            "rep payee responsibilities",
            "rep payee vs power of attorney",
        ],
        suggested_tags=["caregiving", "rep-payee", "social-security", "legal", "family", "finance"],
        intent_tags=["learn", "decide"],
        monetization_type="informational",
    ),
    GuideTopicBrief(
        slug="underwater-car-loan-retirement",
        title="Underwater Car Loan in Retirement: What to Do When a Parent Is Stuck",
        category_slug="caregiving",
        category_id=10,
        vertical="7-caregiving",
        description="Practical guide for adult children helping a retired parent who is underwater on a car loan (owing more than the car is worth). Covers how seniors end up underwater (long loan terms, rolled-over negative equity, dealership upselling), the real cost of carrying negative equity on a fixed income, options for getting out (refinancing, negotiating with lender, voluntary surrender vs. repossession, trading down, paying the gap), how to avoid it next time, and the emotional dimension (shame, pride, fear of losing independence). Includes a decision tree for the best path based on the parent's situation. Unparked from Product Ideas Row 47.",
        senior_examples=[
            "A retiree on Social Security who owes $18,000 on a car worth $11,000 after a dealership rolled $4,000 of negative equity from a previous trade-in",
            "An adult child who discovered their 75-year-old father was paying $550/month on a 7-year car loan that was eating 25% of his Social Security income",
            "A daughter who helped her mother refinance an underwater car loan from 9% to 4.5%, saving $120/month, then set up automatic payments from her checking account",
        ],
        source_urls=[
            {
                "label": "CFPB Auto Loans",
                "url": "https://www.consumerfinance.gov/consumer-tools/auto-loans/",
            },
            {
                "label": "FTC Buying a Car",
                "url": "https://www.consumerfinance.gov/consumer-tools/auto-loans/",
            },
            {"label": "NFCC Debt Help", "url": "https://www.nfcc.org/"},
        ],
        seo_keywords=[
            "underwater car loan retirement",
            "upside down car loan senior",
            "car loan negative equity retiree",
            "help parent underwater car loan",
            "car loan on fixed income",
        ],
        suggested_tags=["caregiving", "car-loan", "debt", "retirement", "family", "finance"],
        intent_tags=["learn", "decide", "save"],
        monetization_type="informational",
    ),
]

# Phase registry — future phases add more as needed
PHASE_TOPICS: Dict[str, List[GuideTopicBrief]] = {
    "1A": PHASE_1A_TOPICS,
    "1B": PHASE_1B_TOPICS,
    "2A": PHASE_2A_TOPICS,
    "2B": PHASE_2B_TOPICS,
    "2C": PHASE_2C_TOPICS,
    "NON-MEDICARE": (
        PHASE_1B_TOPICS
        + PHASE_2A_TOPICS
        + PHASE_2B_TOPICS
        + PHASE_2C_TOPICS
        + PHASE_3A_INSURANCE_TOPICS
        + PHASE_3A_FINANCE_TOPICS
    ),
    "SEO": SEO_TOPICS,
    "SEO2": SEO2_TOPICS,
    "SEO3": SEO3_TOPICS,
    "SEO4A": SEO4A_TOPICS,
    "SEO4B": SEO4B_TOPICS,
    "SEO4C": SEO4C_TOPICS,
    "SEO4D": SEO4D_TOPICS,
    "EXPAND": PHASE_EXPAND_TOPICS,
    "5-PROTECTION": PHASE_5_PROTECTION_TOPICS,
    "6-DISCOUNTS": PHASE_6_DISCOUNTS_TOPICS,
    "7-CAREGIVING": PHASE_7_CAREGIVING_TOPICS,
    "WAVE1": [
        PHASE_5_PROTECTION_TOPICS[0],  # AI voice cloning
        PHASE_5_PROTECTION_TOPICS[1],  # Grandparent scam
        PHASE_6_DISCOUNTS_TOPICS[0],  # Restaurant discounts
        PHASE_6_DISCOUNTS_TOPICS[1],  # Grocery discounts
    ],
    "WAVE2": [
        PHASE_5_PROTECTION_TOPICS[2],  # Tech support scams
        PHASE_5_PROTECTION_TOPICS[3],  # IRS scams
        PHASE_7_CAREGIVING_TOPICS[0],  # Protect parents
        PHASE_7_CAREGIVING_TOPICS[1],  # Signs parent scammed
    ],
    "WAVE3": [
        PHASE_5_PROTECTION_TOPICS[4],  # Romance scams
        PHASE_5_PROTECTION_TOPICS[5],  # Investment scams
        PHASE_6_DISCOUNTS_TOPICS[2],  # Travel discounts
    ],
    "WAVE4": [
        PHASE_7_CAREGIVING_TOPICS[2],  # Rep payee
        PHASE_7_CAREGIVING_TOPICS[3],  # Underwater car loan
    ],
}


# ── System Prompt ────────────────────────────────────────────────────────────


def build_system_prompt(brand_voice: str, few_shot_examples: str) -> str:
    """Build the shared system prompt for guide article generation."""
    parts = [
        "You are a senior financial education writer for Saverwell Guides.",
        "Your audience is adults aged 65+ who may have limited experience",
        "navigating Medicare, insurance, and retirement finances.",
        "",
        "BRAND VOICE:",
        brand_voice,
        "",
        "WRITING RULES:",
        "1. Write in a warm, confident tone. Never be alarmist or patronizing.",
        "2. Use short sentences and simple vocabulary. Spell out abbreviations",
        '   on first use (e.g., "Income-Related Monthly Adjustment Amount (IRMAA)").',
        "3. Use 'seniors', 'retirees', or 'experienced savers'. NEVER use",
        "   'elderly' or 'old folks'.",
        '4. Lead with the SAVINGS angle — "here\'s how to save money" not',
        '   "here\'s what to buy."',
        "5. Short paragraphs (2-3 sentences max). Bullet points for lists.",
        "6. No excessive emojis. No em dashes. No bolding in the middle of",
        "   sentences.",
        "",
        "ARTICLE FORMAT RULES:",
        "1. overview_md: 2-3 sentence overview.",
        '2. key_takeaways_md: 3-5 bullets starting with "- ".',
        "3. body_md: Full article with ## headings. MINIMUM 1,000 words (aim for 1,500+). This is a LONG-FORM guide.",
        "4. savings_tips_md: Specific, actionable ways to save money.",
        "5. watch_out_md: Hidden costs, common mistakes, fraud risks.",
        '6. faq_md: At least 3 questions using "**Q: Question?**" format.',
        "7. email_subject <= 45 characters. email_preheader <= 90 characters.",
        "8. email_cta_url MUST be '/guides/<category_slug>/<slug>'.",
        "9. email_cta_label MUST be exactly 'Read the full guide'.",
        "10. intent_tags MUST include at least one of: learn, compare, save, decide.",
        "11. tags must have 3-8 lowercase items. seo_keywords at least 1.",
        "12. slug must be lowercase-hyphenated (a-z, 0-9, hyphens only).",
        "13. Weave at least 2 senior-relevant examples into body_md.",
        "14. Reference source URLs inline where claiming facts or statistics.",
        "15. Use ONLY the source URLs provided. Do NOT invent or hallucinate URLs.",
        "16. If the article reviews or compares products, include comparison_table.",
        "17. reading_minutes should be 5-10 depending on depth.",
        "",
        "COMPLIANCE-SAFE LANGUAGE (use these patterns):",
        '- "Factors to consider when choosing..."',
        '- "Types of coverage available include..."',
        '- "Many seniors find that..."',
        '- "Questions to ask your insurance agent..."',
        '- "Costs typically range from $X to $Y depending on..."',
        "",
        "PROHIBITED LANGUAGE (never use):",
        '- "We recommend..." / "Our top pick..."',
        '- "You should choose..." / "You need..."',
        '- "This plan/product is best for..."',
        '- "Guaranteed to save..." / "Risk-free..."',
        '- "Medigap" (always use "Medicare Supplement" or "Med Supp")',
        "- Specific policy terms/benefits for named insurers",
        '- Personalized advice ("based on your situation...")',
        "",
        f"OUTPUT FORMAT: Return ONLY a JSON object matching this schema:\n{_JSON_SCHEMA}",
        "",
        "Return bare JSON only. No markdown code blocks. No extra text.",
    ]

    if few_shot_examples:
        parts.append(f"\nPAST GUIDE ARTICLES (match this structure and tone):\n{few_shot_examples}")

    return "\n".join(parts)


def build_user_prompt(topic: GuideTopicBrief) -> str:
    """Build the per-topic user prompt."""
    source_list = "\n".join(f"- {s['label']}: {s['url']}" for s in topic.source_urls)
    examples_list = "\n".join(f"- {ex}" for ex in topic.senior_examples)

    return f"""Write a Saverwell Guide article for the following topic:

SLUG: {topic.slug}
TITLE: {topic.title}
CATEGORY: {topic.category_slug}
VERTICAL: {topic.vertical}
DESCRIPTION: {topic.description}

SENIOR-RELEVANT EXAMPLES (weave at least 2 into the article):
{examples_list}

AUTHORITATIVE SOURCES (use ONLY these URLs — do not invent others):
{source_list}

TARGET SEO KEYWORDS: {", ".join(topic.seo_keywords)}
SUGGESTED TAGS: {", ".join(topic.suggested_tags)}
INTENT TAGS: {", ".join(topic.intent_tags)}
MONETIZATION TYPE: {topic.monetization_type}

email_cta_url must be "/guides/{topic.category_slug}/{topic.slug}"
IMPORTANT: body_md must be a comprehensive long-form article with at least 1,000 words. Cover the topic thoroughly with multiple ## sections. If no product comparison is needed, set comparison_table to null (not an empty array).
Return bare JSON only."""


# ── Validation ───────────────────────────────────────────────────────────────


@dataclass
class ValidationResult:
    """Result of guide-lens validation."""

    passed: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def validate_guide_lens(article: GuideArticle, topic: GuideTopicBrief) -> ValidationResult:
    """Custom guide-lens validation beyond Pydantic."""
    warnings: List[str] = []
    errors: List[str] = []

    # 1. Key takeaways count
    if article.key_takeaways_md.count("- ") < 3:
        errors.append(
            f"key_takeaways_md has {article.key_takeaways_md.count('- ')} bullets, need at least 3"
        )

    # 2. FAQ bold question count
    if article.faq_md.count("**Q:") < 3:
        errors.append(f"faq_md has {article.faq_md.count('**Q:')} bold questions, need at least 3")

    # 3. Savings tips non-empty
    if len(article.savings_tips_md.strip()) < 50:
        errors.append("savings_tips_md is too short (< 50 chars)")

    # 4. Watch out non-empty
    if len(article.watch_out_md.strip()) < 50:
        errors.append("watch_out_md is too short (< 50 chars)")

    # 5. SEO keywords in body
    body_lower = article.body_md.lower()
    missing_kw = [kw for kw in topic.seo_keywords if kw.lower() not in body_lower]
    if len(missing_kw) > len(topic.seo_keywords) * 0.5:
        errors.append(f"body_md missing > 50% of SEO keywords: {missing_kw}")

    # 6. Word count range
    word_count = len(article.body_md.split())
    if word_count < 1000:
        errors.append(f"body_md word count {word_count} < 1000 minimum")
    elif word_count > 2500:
        warnings.append(f"body_md word count {word_count} > 2500 maximum")

    # 7. Senior keywords in body
    found_senior = [kw for kw in SENIOR_KEYWORDS if kw in body_lower]
    if len(found_senior) < 2:
        errors.append(f"body_md has {len(found_senior)} senior keywords, need at least 2")

    # 8. Savings keywords anywhere
    full_text = (
        article.body_md
        + article.savings_tips_md
        + article.watch_out_md
        + article.overview_md
        + article.key_takeaways_md
        + article.faq_md
    ).lower()
    found_savings = [kw for kw in SAVINGS_KEYWORDS if kw in full_text]
    if len(found_savings) < 1:
        errors.append("No savings keywords found in article text")

    # 9. Slug match
    if article.slug != topic.slug:
        errors.append(f"Slug mismatch: got '{article.slug}', expected '{topic.slug}'")

    # 10. Category match
    if article.category_slug != topic.category_slug:
        errors.append(
            f"Category mismatch: got '{article.category_slug}', expected '{topic.category_slug}'"
        )

    # 11. Vertical match
    if article.vertical != topic.vertical:
        errors.append(f"Vertical mismatch: got '{article.vertical}', expected '{topic.vertical}'")

    # 12. CTA URL match
    expected_cta = f"/guides/{topic.category_slug}/{topic.slug}"
    if article.email_cta_url != expected_cta:
        errors.append(
            f"email_cta_url mismatch: got '{article.email_cta_url}', expected '{expected_cta}'"
        )

    # 13. Citation count
    if len(topic.source_urls) < 2:
        errors.append(f"Topic has {len(topic.source_urls)} citations, need at least 2")

    # 14. .gov citation count
    gov_count = sum(1 for s in topic.source_urls if ".gov" in s["url"])
    if gov_count < 1:
        errors.append(f"Topic has {gov_count} .gov citations, need at least 1")

    # 15. Source URLs referenced in body
    source_domains = []
    for s in topic.source_urls:
        # Extract domain from URL
        match = re.search(r"https?://(?:www\.)?([^/]+)", s["url"])
        if match:
            source_domains.append(match.group(1).lower())
    referenced = sum(1 for d in source_domains if d in body_lower)
    if referenced < 1:
        warnings.append("No source URL domains referenced in body_md")

    passed = len(errors) == 0
    return ValidationResult(passed=passed, warnings=warnings, errors=errors)


# ── Refinement ───────────────────────────────────────────────────────────────


async def refine_article(
    client: "anthropic.AsyncAnthropic",
    article: GuideArticle,
    brand_voice: str,
) -> Tuple[GuideArticle, int]:
    """Quality refinement loop. Returns (article, refinement_score)."""
    import anthropic as _anthropic  # avoid top-level import collision

    last_score = 10  # assume good until proven otherwise

    for i in range(MAX_REFINEMENT_ITERATIONS):
        article_json = article.model_dump_json(indent=2)
        critique_prompt = f"""Rate this Saverwell Guide article on a scale of 1-10.

BRAND VOICE TO MATCH:
{brand_voice[:500]}

ARTICLE JSON:
{article_json[:4000]}

Score each criterion (1-10):
1. Brand voice alignment — calm, confident Saverwell tone for seniors
2. Clarity and readability — short sentences, plain language for 65+
3. Completeness — all sections filled (overview, key takeaways, body, savings tips, watch out, FAQ)
4. Savings angle strength — does the article lead with savings/cost-reduction?
5. SEO coverage — are target keywords naturally woven into headings and body?
6. Source attribution — are sources referenced inline where facts are claimed?

Return ONLY a JSON object: {{"brand_voice": N, "clarity": N, "completeness": N, "savings_angle": N, "seo_coverage": N, "sources": N, "overall": N, "feedback": "..."}}"""

        try:
            resp = await client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=1024,
                temperature=0.3,
                messages=[{"role": "user", "content": critique_prompt}],
            )

            raw = resp.content[0].text
            # Strip markdown code blocks if present
            match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
            if match:
                raw = match.group(1).strip()

            critique = json.loads(raw)
            overall = critique.get("overall", 10)
            last_score = overall

            if overall >= QUALITY_THRESHOLD:
                logger.info("refinement_passed", iteration=i + 1, score=overall)
                break

            feedback = critique.get("feedback", "Improve quality")
            revise_prompt = f"""Revise this Saverwell Guide article based on the critique.

BRAND VOICE:
{brand_voice[:500]}

CURRENT ARTICLE JSON:
{article_json[:4000]}

CRITIQUE (score {overall}/10):
{feedback}

Return ONLY the revised JSON object (same schema, all fields required). No markdown wrapping."""

            revise_resp = await client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=GENERATION_MAX_TOKENS,
                temperature=0.5,
                messages=[{"role": "user", "content": revise_prompt}],
            )

            revised = parse_guide_json(revise_resp.content[0].text)
            if isinstance(revised, GuideArticle):
                article = revised
                logger.info("refinement_iteration", iteration=i + 1, score=overall)
            else:
                logger.warning(
                    "refinement_parse_failed",
                    iteration=i + 1,
                    error=revised.get("error"),
                )
                break
        except (json.JSONDecodeError, TypeError) as e:
            logger.warning("critique_parse_failed", iteration=i + 1, error=str(e))
            break
        except _anthropic.APIError as e:
            logger.warning("refinement_api_error", iteration=i + 1, error=str(e))
            break

    return article, last_score


# ── Proofreading ─────────────────────────────────────────────────────────────


async def proofread_article(
    article: GuideArticle,
    settings: Settings,
) -> Tuple[GuideArticle, int]:
    """Proofread article fields via Haiku. Returns (article, correction_count)."""
    from cmo_agent.llm.anthropic import AnthropicLLM
    from cmo_agent.text.proofreader import Proofreader

    scanning_llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=SCANNING_MODEL,
        max_tokens=16384,
        temperature=0.1,
    )
    proofreader = Proofreader(scanning_llm)

    article_dict = article.model_dump()
    corrected, corrections = await proofreader.proofread_dict_fields(
        article_dict,
        PROOFREAD_FIELDS,
        preserve_terms=[
            "Saverwell",
            "Medicare",
            "Medicaid",
            "Medicare Supplement",
            "IRMAA",
            "Part A",
            "Part B",
            "Part C",
            "Part D",
            "Social Security",
            "SSA",
            "CMS",
            "AARP",
            "AEP",
            "IEP",
            "GEP",
            "SEP",
            "MAGI",
            "LIS",
            "Extra Help",
            "HRSA",
            "FDA",
            "OTC",
        ],
    )
    if corrections:
        try:
            article = GuideArticle(**corrected)
            logger.info("proofread_corrections", count=len(corrections))
        except Exception as e:
            logger.warning(
                "proofread_validation_failed_using_original",
                error=str(e),
                corrections_attempted=len(corrections),
            )
            corrections = []  # report 0 since we discarded them

    return article, len(corrections)


# ── Data refresh ────────────────────────────────────────────────────────────


REFRESH_SYSTEM_PROMPT = """\
You are a Medicare content editor for Saverwell. Your job is to update
an existing guide article with current 2026 Medicare data.

RULES:
1. Replace ALL dollar amounts, income thresholds, and year references
   with the 2026 figures provided in the data reference.
2. Change every "in 2024" or "for 2024" reference to "in 2026" or
   "for 2026" as appropriate. Also update "2025" references where
   the data has changed for 2026.
3. Update IRMAA lookback references: 2026 premiums are based on 2024
   tax returns (not 2022).
4. For Part D: the donut hole/coverage gap was eliminated in 2025
   under the Inflation Reduction Act. Replace any donut hole
   references with the new $2,100 annual out-of-pocket cap. Mention
   the first 10 negotiated drug prices taking effect in 2026 where
   relevant.
5. Keep ALL other content unchanged: narrative structure, anecdotes,
   tone, formatting, section headings, markdown structure.
6. Anecdotal dollar amounts in scenarios (e.g. Sarah's $1,200 root
   canal, Robert's $3,400 out-of-network bill) should stay as-is —
   these are story elements, not regulatory data.
7. Recalculate any derived amounts. For example, a Part B late
   enrollment penalty of 10% should be recalculated from
   10% x $202.90 = $20.29/month per year delayed.
8. Preserve all source URL references. Do not change URLs.
9. Return the FULL article as a JSON object matching the exact same
   schema. Do not omit any fields.
10. For Extra Help / LIS: use 2025 figures (2026 not yet published
    for LIS-specific limits). Make income/resource limits consistent
    across all sections that reference them.
"""


async def refresh_article(
    client: "anthropic.AsyncAnthropic",
    article_data: Dict[str, Any],
    data_reference: str,
) -> Optional[GuideArticle]:
    """Refresh an article's data figures using the 2026 reference sheet.

    Sends the full article JSON + data reference to Sonnet and parses
    the result through the GuideArticle Pydantic model.
    """
    user_prompt = f"""Here is the article to update:
{json.dumps(article_data, indent=2)}

2026 MEDICARE DATA REFERENCE:
{data_reference}

Return the updated article as a JSON object. Change ONLY data figures,
dollar amounts, income thresholds, year references, and IRMAA brackets.
Keep everything else identical — same narrative structure, same tone,
same anecdotes, same formatting, same URLs.

Return bare JSON only. No markdown code blocks. No extra text."""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=GENERATION_MAX_TOKENS,
                temperature=0.2,  # low temp for factual updates
                system=REFRESH_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )

            parsed = parse_guide_json(resp.content[0].text)
            if isinstance(parsed, GuideArticle):
                return parsed

            error = parsed.get("error", "Unknown")
            logger.warning(
                "refresh_parse_failed",
                slug=article_data.get("slug"),
                attempt=attempt,
                error=error,
            )
        except Exception as e:
            logger.error(
                "refresh_api_error",
                slug=article_data.get("slug"),
                attempt=attempt,
                error=str(e),
            )
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2**attempt)

    return None


# ── Source URL verification ──────────────────────────────────────────────────


async def verify_source_urls(topics: List[GuideTopicBrief]) -> Dict[str, str]:
    """HEAD-check all source URLs. Returns {url: status} map."""
    results: Dict[str, str] = {}
    all_urls = set()
    for topic in topics:
        for source in topic.source_urls:
            all_urls.add(source["url"])

    async with httpx.AsyncClient(timeout=5.0, follow_redirects=True) as http:
        for url in sorted(all_urls):
            try:
                resp = await http.head(url)
                results[url] = f"{resp.status_code}"
                if resp.status_code != 200:
                    logger.warning("source_url_non_200", url=url, status=resp.status_code)
            except Exception as e:
                results[url] = f"error: {e}"
                logger.warning("source_url_unreachable", url=url, error=str(e))

    return results


# ── Archive helper ───────────────────────────────────────────────────────────


def append_to_archive(article: GuideArticle) -> None:
    """Append a completed article to the guide archive file."""
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ARCHIVE_PATH.exists():
        ARCHIVE_PATH.write_text(
            "# Saverwell Guide Article Archive\n"
            "# Generated guide articles. Used as few-shot examples.\n"
        )
    entry = (
        f"\n---\n\n### {article.slug}\n"
        f"Status: Completed\n"
        f"Title: {article.title}\n"
        f"Category: {article.category_slug}\n"
        f"Vertical: {article.vertical}\n"
        f"Tags: {', '.join(article.tags)}\n\n"
        f"## Overview\n{article.overview_md}\n\n"
        f"## Key Takeaways\n{article.key_takeaways_md}\n\n"
        f"## Savings Tips\n{article.savings_tips_md}\n\n"
        f"## Watch Out\n{article.watch_out_md}\n\n"
        f"## FAQ\n{article.faq_md}\n"
    )
    with open(ARCHIVE_PATH, "a") as f:
        f.write(entry)
    logger.info("article_archived", slug=article.slug)


# ── Review score computation ────────────────────────────────────────────────


def compute_review_score(
    validation: ValidationResult,
    refinement_score: int,
    proofread_corrections: int,
    attempt: int,
) -> int:
    """Compute a 2-5 review score based on validation and refinement."""
    if validation.passed and not validation.warnings and refinement_score >= 8:
        return 5
    if validation.passed and refinement_score >= 7:
        return 4
    if validation.passed and refinement_score >= 5:
        return 3
    return 2


def build_review_notes(
    validation: ValidationResult,
    refinement_score: int,
    proofread_corrections: int,
    url_results: Dict[str, str],
    topic: GuideTopicBrief,
    attempt: int,
) -> str:
    """Build human-readable review notes."""
    parts = [f"Refinement score: {refinement_score}/10"]
    parts.append(f"Generation attempt: {attempt}/{MAX_RETRIES}")
    parts.append(f"Proofread corrections: {proofread_corrections}")

    if validation.warnings:
        parts.append(f"Warnings: {'; '.join(validation.warnings)}")
    if validation.errors:
        parts.append(f"Errors: {'; '.join(validation.errors)}")

    # Source URL status for this topic
    for source in topic.source_urls:
        url = source["url"]
        status = url_results.get(url, "not checked")
        if status != "200":
            parts.append(f"Source URL {url}: {status}")

    return " | ".join(parts)


# ── Supabase helpers ─────────────────────────────────────────────────────────


async def fetch_existing_slugs(settings: Settings) -> set:
    """Fetch existing guide article slugs from Supabase."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.get(
            f"{settings.supabase_url}/rest/v1/guide_articles?select=slug",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        return {row["slug"] for row in rows}


async def upsert_article(
    settings: Settings,
    payload: Dict[str, Any],
) -> bool:
    """Upsert a single guide article to Supabase. Returns True on success."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            f"{settings.supabase_url}/rest/v1/guide_articles?on_conflict=slug",
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
            slug=payload.get("slug"),
            status=resp.status_code,
            body=resp.text[:500],
        )
        return False


def build_supabase_payload(
    article: GuideArticle,
    topic: GuideTopicBrief,
    review_score: int,
    review_notes: str,
) -> Dict[str, Any]:
    """Build the Supabase row payload from an article and topic brief."""
    data = article.model_dump()

    payload: Dict[str, Any] = {
        "slug": data["slug"],
        "title": data["title"],
        "subtitle": data["subtitle"],
        "category_id": topic.category_id,
        "vertical": topic.vertical,
        "tags": data["tags"],
        "intent_tags": data["intent_tags"],
        "seo_keywords": data["seo_keywords"],
        "reading_minutes": data["reading_minutes"],
        "overview_md": data["overview_md"],
        "key_takeaways_md": data["key_takeaways_md"],
        "body_md": data["body_md"],
        "savings_tips_md": data["savings_tips_md"],
        "watch_out_md": data["watch_out_md"],
        "faq_md": data["faq_md"],
        "comparison_table": json.dumps(data["comparison_table"])
        if data["comparison_table"]
        else None,
        "related_slugs": data["related_slugs"],
        "email_subject": data["email_subject"],
        "email_preheader": data["email_preheader"],
        "email_intro_md": data["email_intro_md"],
        "email_cta_label": data["email_cta_label"],
        "email_cta_url": data["email_cta_url"],
        "monetization_type": data["monetization_type"],
        "affiliate_disclosure": data["affiliate_disclosure"],
        # Metadata
        "status": "draft",
        "publish_web": False,
        "publish_email": False,
        "source": "generate_guide_content",
        "source_name": "generate_guide_content.py",
        "author": "Saverwell AI",
        "review_score": review_score,
        "review_notes": review_notes,
        "citations": json.dumps(topic.source_urls),
    }

    return payload


# ── Local cache helpers ──────────────────────────────────────────────────────


def save_draft_cache(slug: str, payload: Dict[str, Any]) -> None:
    """Save a Supabase payload to local JSON cache."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAFTS_DIR / f"{slug}.json"
    path.write_text(json.dumps(payload, indent=2))
    logger.info("draft_cached", slug=slug, path=str(path))


def load_draft_cache(slug: str) -> Optional[Dict[str, Any]]:
    """Load a cached draft payload. Returns None if not found."""
    path = DRAFTS_DIR / f"{slug}.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


# ── Few-shot loading ─────────────────────────────────────────────────────────


def load_few_shot_examples(max_articles: int = 2) -> str:
    """Load the first N completed articles from the archive as few-shot examples."""
    if not ARCHIVE_PATH.exists():
        return ""
    content = ARCHIVE_PATH.read_text()
    entries = content.split("\n---\n")
    completed = [e for e in entries if "Status: Completed" in e]
    selected = completed[:max_articles] if len(completed) > max_articles else completed
    return "\n---\n".join(selected)


# ── Main generation pipeline ────────────────────────────────────────────────


async def generate_article(
    client: "anthropic.AsyncAnthropic",
    topic: GuideTopicBrief,
    system_prompt: str,
    settings: Settings,
    url_results: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Generate, validate, refine, proofread, and return a Supabase payload."""
    user_prompt = build_user_prompt(topic)

    article: Optional[GuideArticle] = None
    last_validation: Optional[ValidationResult] = None
    attempt = 0

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info("generating_article", slug=topic.slug, attempt=attempt)

        try:
            resp = await client.messages.create(
                model=GENERATION_MODEL,
                max_tokens=GENERATION_MAX_TOKENS,
                temperature=GENERATION_TEMPERATURE,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )

            raw_text = resp.content[0].text
            parsed = parse_guide_json(raw_text)

            if isinstance(parsed, dict) and "error" in parsed:
                logger.warning(
                    "parse_failed", slug=topic.slug, attempt=attempt, error=parsed["error"]
                )
                continue

            article = parsed  # type: ignore[assignment]

            # Guide-lens validation
            last_validation = validate_guide_lens(article, topic)
            if last_validation.passed:
                break
            else:
                logger.warning(
                    "validation_failed",
                    slug=topic.slug,
                    attempt=attempt,
                    errors=last_validation.errors,
                )
                if attempt == MAX_RETRIES:
                    # Accept with warnings on final attempt
                    logger.warning("accepting_with_errors", slug=topic.slug)
                    break

        except Exception as e:
            logger.error("generation_error", slug=topic.slug, attempt=attempt, error=str(e))
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2**attempt)
                continue
            return None

    if article is None:
        logger.error("all_attempts_failed", slug=topic.slug)
        return None

    # Refinement
    article, refinement_score = await refine_article(client, article, BRAND_VOICE_PATH.read_text())

    # Proofreading
    article, proofread_count = await proofread_article(article, settings)

    # Compute review score and notes
    if last_validation is None:
        last_validation = validate_guide_lens(article, topic)

    review_score = compute_review_score(last_validation, refinement_score, proofread_count, attempt)
    review_notes = build_review_notes(
        last_validation, refinement_score, proofread_count, url_results, topic, attempt
    )

    # Build payload
    payload = build_supabase_payload(article, topic, review_score, review_notes)

    # Save to local cache
    save_draft_cache(topic.slug, payload)

    # Append to archive
    try:
        append_to_archive(article)
    except Exception as e:
        logger.warning("archive_append_failed", slug=topic.slug, error=str(e))

    return payload


# ── Main ─────────────────────────────────────────────────────────────────────


async def run_refresh(
    args: argparse.Namespace,
    settings: Settings,
    all_topics: List[GuideTopicBrief],
    phase_key: str,
) -> None:
    """Refresh cached articles with 2026 Medicare data."""
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    topic_map = {t.slug: t for t in all_topics}

    # Load all cached JSONs
    cached_files = sorted(DRAFTS_DIR.glob("*.json"))
    if not cached_files:
        print("ERROR: No cached articles found in data/saverwell/guide_drafts/")
        print("Run without --refresh-data first to generate articles.")
        sys.exit(1)

    # Filter to phase topics only
    phase_slugs = {t.slug for t in all_topics}
    to_refresh = [f for f in cached_files if f.stem in phase_slugs]
    print(f"\nFound {len(to_refresh)} cached articles to refresh with 2026 data")

    refreshed_payloads: Dict[str, Dict[str, Any]] = {}
    failed_slugs: List[str] = []

    for i, path in enumerate(to_refresh):
        slug = path.stem
        print(f"\n[{i + 1}/{len(to_refresh)}] Refreshing: {slug}")
        t0 = time.time()

        # Load cached article data (Supabase payload format)
        article_data = json.loads(path.read_text())

        # Cached payloads use category_id (int) but GuideArticle needs
        # category_slug (str). Inject it from the topic brief so the LLM
        # returns a valid GuideArticle-compatible JSON.
        topic = topic_map.get(slug)
        if topic is None:
            logger.warning("topic_not_found_for_slug", slug=slug)
            failed_slugs.append(slug)
            print("  SKIPPED (no topic brief for slug)")
            continue
        # Preserve original metadata before stripping for LLM
        orig_review_score = article_data.get("review_score", 4)
        orig_review_notes = article_data.get("review_notes", "")

        # Build a GuideArticle-compatible dict for the LLM by adding
        # category_slug and stripping Supabase-only metadata fields.
        article_data["category_slug"] = topic.category_slug
        supabase_only = [
            "category_id",
            "status",
            "publish_web",
            "publish_email",
            "source",
            "source_name",
            "author",
            "review_score",
            "review_notes",
            "citations",
        ]
        for key in supabase_only:
            article_data.pop(key, None)

        # Refresh via LLM
        refreshed = await refresh_article(client, article_data, MEDICARE_2026_DATA)
        if refreshed is None:
            failed_slugs.append(slug)
            print(f"  FAILED (refresh) ({time.time() - t0:.1f}s)")
            continue

        # Proofread
        refreshed, proofread_count = await proofread_article(refreshed, settings)

        # Validate
        validation = validate_guide_lens(refreshed, topic)
        if not validation.passed:
            logger.warning(
                "refresh_validation_warnings",
                slug=slug,
                errors=validation.errors,
            )

        # Build review notes — append refresh marker
        refresh_note = f"Data refreshed to 2026 | Proofread corrections: {proofread_count}"
        if validation.errors:
            refresh_note += f" | Validation: {'; '.join(validation.errors)}"
        new_notes = f"{orig_review_notes} | {refresh_note}" if orig_review_notes else refresh_note

        payload = build_supabase_payload(
            refreshed,
            topic,
            orig_review_score,
            new_notes,
        )

        # Save updated JSON to cache
        save_draft_cache(slug, payload)
        refreshed_payloads[slug] = payload

        elapsed = time.time() - t0
        print(f"  OK (proofread={proofread_count}, {elapsed:.1f}s)")

        # Pause between articles
        if i < len(to_refresh) - 1:
            await asyncio.sleep(INTER_ARTICLE_PAUSE)

    # Upsert to Supabase
    upserted: List[str] = []
    upsert_failed: List[str] = []

    if not args.dry_run and refreshed_payloads:
        print(f"\nUpserting {len(refreshed_payloads)} refreshed articles to Supabase...")
        for slug, payload in refreshed_payloads.items():
            success = await upsert_article(settings, payload)
            if success:
                upserted.append(slug)
            else:
                upsert_failed.append(slug)
    elif args.dry_run:
        print("\n--dry-run: skipping Supabase upsert")
        upserted = list(refreshed_payloads.keys())

    # Completion report
    print("\n" + "=" * 50)
    print("DATA REFRESH REPORT")
    print("=" * 50)
    print(f"Phase:      {phase_key}")
    print(f"Refreshed:  {len(refreshed_payloads)}")
    print(f"Upserted:   {len(upserted)}" + (" (dry-run)" if args.dry_run else ""))
    print(f"Failed:     {len(failed_slugs) + len(upsert_failed)}")

    if upserted:
        print("\nRefreshed slugs:")
        for slug in upserted:
            print(f"  OK  {slug}")

    if failed_slugs or upsert_failed:
        print("\nFailed:")
        for slug in failed_slugs:
            print(f"  FAIL (refresh)  {slug}")
        for slug in upsert_failed:
            print(f"  FAIL (upsert)   {slug}")

    if not failed_slugs and not upsert_failed:
        print("\nAll articles refreshed successfully.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Saverwell Guide articles")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate, but skip Supabase upsert",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load cached JSONs from data/saverwell/guide_drafts/ instead of regenerating",
    )
    parser.add_argument(
        "--refresh-data",
        action="store_true",
        help="Update cached articles with current-year Medicare data (2026)",
    )
    parser.add_argument(
        "--phase",
        default="1A",
        help="Phase to generate (default: 1A). Options: 1A, 1B, 2A, 2B, 2C, NON-MEDICARE, SEO, SEO2, SEO3, SEO4A-D, EXPAND, 5-PROTECTION, 6-DISCOUNTS, 7-CAREGIVING, WAVE1-4",
    )
    args = parser.parse_args()

    settings = Settings()

    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    if not args.dry_run and (not settings.supabase_url or not settings.supabase_service_role_key):
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required (or use --dry-run)")
        sys.exit(1)

    # Resolve phase topics
    phase_key = args.phase.upper()
    if phase_key not in PHASE_TOPICS:
        print(f"ERROR: Unknown phase '{args.phase}'. Available: {', '.join(PHASE_TOPICS.keys())}")
        sys.exit(1)

    all_topics = PHASE_TOPICS[phase_key]
    print(f"Phase {phase_key}: {len(all_topics)} topics")

    # ── Refresh mode ──────────────────────────────────────────────────────
    if args.refresh_data:
        await run_refresh(args, settings, all_topics, phase_key)
        return

    # ── Normal generation mode ────────────────────────────────────────────

    # Load brand voice and few-shot examples
    brand_voice = BRAND_VOICE_PATH.read_text()
    few_shot = load_few_shot_examples(max_articles=2)
    system_prompt = build_system_prompt(brand_voice, few_shot)

    # Fetch existing slugs from Supabase (unless dry-run with no Supabase)
    existing_slugs: set = set()
    if not args.dry_run:
        try:
            existing_slugs = await fetch_existing_slugs(settings)
            print(f"Found {len(existing_slugs)} existing guide articles in Supabase")
        except Exception as e:
            print(f"WARNING: Could not fetch existing slugs: {e}")

    # Determine which topics need generation
    topics_to_generate: List[GuideTopicBrief] = []
    topics_to_skip: List[str] = []
    cached_payloads: Dict[str, Dict[str, Any]] = {}

    for topic in all_topics:
        if topic.slug in existing_slugs:
            topics_to_skip.append(topic.slug)
            continue

        if args.resume:
            cached = load_draft_cache(topic.slug)
            if cached:
                cached_payloads[topic.slug] = cached
                continue

        topics_to_generate.append(topic)

    print(f"\nTopics to generate: {len(topics_to_generate)}")
    print(f"Topics from cache:  {len(cached_payloads)}")
    print(f"Topics to skip:     {len(topics_to_skip)}")

    if not topics_to_generate and not cached_payloads:
        print("\nAll articles already exist. Nothing to do.")
        return

    # Verify source URLs
    print("\nVerifying source URLs...")
    url_results = await verify_source_urls(all_topics)
    ok_count = sum(1 for v in url_results.values() if v == "200")
    print(f"Source URLs: {ok_count}/{len(url_results)} returned 200")

    # Generate articles
    import anthropic

    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    generated_payloads: Dict[str, Dict[str, Any]] = {}
    failed_slugs: List[str] = []

    for i, topic in enumerate(topics_to_generate):
        print(f"\n[{i + 1}/{len(topics_to_generate)}] Generating: {topic.slug}")
        t0 = time.time()

        payload = await generate_article(client, topic, system_prompt, settings, url_results)

        elapsed = time.time() - t0
        if payload:
            generated_payloads[topic.slug] = payload
            score = payload.get("review_score", "?")
            print(f"  OK (score={score}, {elapsed:.1f}s)")
        else:
            failed_slugs.append(topic.slug)
            print(f"  FAILED ({elapsed:.1f}s)")

        # Pause between articles
        if i < len(topics_to_generate) - 1:
            await asyncio.sleep(INTER_ARTICLE_PAUSE)

    # Merge generated and cached payloads
    all_payloads = {**cached_payloads, **generated_payloads}

    # Upsert to Supabase
    inserted_slugs: List[Tuple[str, int]] = []
    upsert_failed: List[str] = []

    if not args.dry_run and all_payloads:
        print(f"\nUpserting {len(all_payloads)} guide articles to Supabase...")
        for slug, payload in all_payloads.items():
            success = await upsert_article(settings, payload)
            if success:
                inserted_slugs.append((slug, payload.get("review_score", 0)))
            else:
                upsert_failed.append(slug)
    elif args.dry_run:
        print("\n--dry-run: skipping Supabase upsert")
        for slug, payload in all_payloads.items():
            inserted_slugs.append((slug, payload.get("review_score", 0)))

    # ── Completion report ────────────────────────────────────────────────────

    # Category counts
    cat_counts: Dict[str, int] = {}
    topic_map = {t.slug: t for t in all_topics}

    for slug, _ in inserted_slugs:
        topic = topic_map.get(slug)
        if topic:
            cat_counts[topic.category_slug] = cat_counts.get(topic.category_slug, 0) + 1

    print("\n" + "=" * 50)
    print("COMPLETION REPORT")
    print("=" * 50)
    print(f"Phase:      {phase_key}")
    print(f"Generated:  {len(generated_payloads)}")
    print(f"From cache: {len(cached_payloads)}")
    total_inserted = len(inserted_slugs)
    print(f"Inserted:   {total_inserted}" + (" (dry-run)" if args.dry_run else ""))
    print(f"Failed:     {len(failed_slugs) + len(upsert_failed)}")
    print(f"Skipped:    {len(topics_to_skip)} (already existed)")

    if cat_counts:
        print("\nPer category:")
        for cat, count in sorted(cat_counts.items()):
            print(f"  {cat:15s}: {count} inserted")

    if inserted_slugs:
        print("\nInserted slugs:")
        for slug, score in inserted_slugs:
            print(f"  OK  {slug:50s} (score={score})")

    if failed_slugs or upsert_failed:
        print("\nFailed:")
        for slug in failed_slugs:
            print(f"  FAIL (generation) {slug}")
        for slug in upsert_failed:
            print(f"  FAIL (upsert)     {slug}")

    if not failed_slugs and not upsert_failed:
        print("\nAll articles processed successfully.")


# ── Importable API for weekly_content_factory ────────────────────────────────


async def generate_single_guide(
    topic_brief: Dict[str, Any],
    settings: Optional["Settings"] = None,
    publish: bool = True,
) -> Optional[Dict[str, Any]]:
    """Generate a single guide article from a topic brief dict.

    This is the importable entry point used by ``weekly_content_factory.py``.
    Handles LLM generation, validation, refinement, proofreading, caching,
    and optionally upserts to Supabase.

    Args:
        topic_brief: Dict matching GuideTopicBrief fields (slug, title,
            category_slug, category_id, vertical, description,
            senior_examples, source_urls, seo_keywords, suggested_tags,
            intent_tags, monetization_type).
        settings: CMO Agent settings. Loaded from .env if None.
        publish: If True, upsert to Supabase with status='published'
            and publish_web=True. If False, save to cache only.

    Returns:
        Supabase payload dict on success, None on failure.
    """
    import anthropic

    if settings is None:
        settings = Settings()

    if not settings.anthropic_api_key:
        logger.error("generate_single_guide_no_api_key")
        return None

    # Build topic brief dataclass
    topic = GuideTopicBrief(
        slug=topic_brief["slug"],
        title=topic_brief["title"],
        category_slug=topic_brief.get("category_slug", "saving-money"),
        category_id=topic_brief.get("category_id", 1),
        vertical=topic_brief.get("vertical", "6-discounts"),
        description=topic_brief.get("description", topic_brief["title"]),
        senior_examples=topic_brief.get("senior_examples", []),
        source_urls=topic_brief.get("source_urls", []),
        seo_keywords=topic_brief.get("seo_keywords", []),
        suggested_tags=topic_brief.get("suggested_tags", []),
        intent_tags=topic_brief.get("intent_tags", ["learn"]),
        monetization_type=topic_brief.get("monetization_type", "informational"),
    )

    # Build system prompt
    brand_voice = BRAND_VOICE_PATH.read_text() if BRAND_VOICE_PATH.exists() else ""
    few_shot = load_few_shot_examples(max_articles=2)
    system_prompt = build_system_prompt(brand_voice, few_shot)

    # Verify source URLs
    url_results = await verify_source_urls([topic])

    # Generate article
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    payload = await generate_article(client, topic, system_prompt, settings, url_results)

    if payload is None:
        logger.error("generate_single_guide_failed", slug=topic.slug)
        return None

    # Override status for auto-published content
    if publish:
        payload["status"] = "published"
        payload["publish_web"] = True
        payload["publish_email"] = True
        payload["source"] = "weekly_content_factory"
        payload["source_name"] = "weekly_content_factory.py"

        if settings.supabase_url and settings.supabase_service_role_key:
            success = await upsert_article(settings, payload)
            if not success:
                logger.error("generate_single_guide_upsert_failed", slug=topic.slug)
                return None
            logger.info("generate_single_guide_published", slug=topic.slug)
        else:
            logger.warning("generate_single_guide_no_supabase", slug=topic.slug)

    return payload


if __name__ == "__main__":
    asyncio.run(main())
