"""Saverwell reply generation with post-type awareness, pillar detection, and canned response templates."""

from __future__ import annotations

import re
import json
from typing import Any, Dict, List, Optional, Tuple

import structlog

from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_char_limit_hook, make_em_dash_hook

logger = structlog.get_logger()


# ---------------------------------------------------------------------------
# Quality criteria for Saverwell reply refinement
# ---------------------------------------------------------------------------

_SAVERWELL_CRITERIA = [
    QualityCriterion(
        name="authenticity",
        description="Sounds like a real person, not corporate marketing",
    ),
    QualityCriterion(
        name="brand_fit",
        description="Matches Saverwell's warm, empowering, practical tone",
    ),
    QualityCriterion(
        name="helpfulness",
        description="Provides genuinely useful information or links",
    ),
    QualityCriterion(
        name="no_overselling",
        description="Not pushy, not a hard sell, peer-like advice",
    ),
]


# ---------------------------------------------------------------------------
# Canned response templates
# ---------------------------------------------------------------------------

_CANNED_RESPONSES = [
    {
        "scenario": "discount_seeking_general",
        "template": "Hey! We actually verify senior discounts by area - you pop in your ZIP code and we show what is available near you. Give it a look at saverwell.com.",
    },
    {
        "scenario": "discount_seeking_specific",
        "template": "A lot of those discounts are real but they vary by location. We have a free tool where you enter your ZIP and we show verified discounts near you - no membership or sign-up needed.",
    },
    {
        "scenario": "fraud_alert",
        "template": "Sorry you are dealing with that. We put together a plain-language guide on common scams targeting seniors with step-by-step instructions on what to do next: saverwell.com/protection. We keep it updated as new ones pop up.",
    },
    {
        "scenario": "medicare_question",
        "template": "Medicare can be really confusing. We wrote some plain-language guides that break it down without all the jargon - might help sort out the options: saverwell.com/guides.",
    },
    {
        "scenario": "general_savings",
        "template": "We built a free tool that shows verified senior discounts by ZIP code. Not a membership thing, just a lookup. You might find some you did not know about: saverwell.com.",
    },
    {
        "scenario": "resource_request",
        "template": "We cover three things in one place: verified senior discounts by ZIP code, protection guides for common scams, and plain-language Medicare guides. All free, no sign-up needed: saverwell.com.",
    },
]


# ---------------------------------------------------------------------------
# Pillar detection keywords
# ---------------------------------------------------------------------------

_PILLAR_KEYWORDS = {
    "Protection": [
        "scam",
        "scams",
        "fraud",
        "phishing",
        "identity theft",
        "id theft",
        "robocall",
        "robocalls",
        "data breach",
        "protect",
        "security",
        "suspicious",
        "hacked",
        "stolen",
        "impersonation",
        "spoofing",
    ],
    "Guides": [
        "medicare",
        "medicaid",
        "enrollment",
        "part a",
        "part b",
        "part d",
        "medigap",
        "advantage plan",
        "supplement",
        "open enrollment",
        "coverage",
        "copay",
        "deductible",
        "premium",
        "insurance",
        "hearing aid",
        "hearing aids",
        "medical alert",
        "life alert",
    ],
    "Savings": [
        "discount",
        "discounts",
        "coupon",
        "coupons",
        "deal",
        "deals",
        "save money",
        "saving money",
        "savings",
        "senior discount",
        "frugal",
        "budget",
        "budgeting",
        "cheap",
        "affordable",
        "free",
        "promo",
        "sale",
        "price",
    ],
}


# ---------------------------------------------------------------------------
# Post type classification prompt
# ---------------------------------------------------------------------------

_CLASSIFY_PROMPT = """Classify this post into exactly ONE of these categories:
- discount_seeking: Asking about specific discounts or deals
- fraud_alert: Reporting or asking about scams targeting seniors
- medicare_question: Medicare enrollment, coverage, confusion
- insurance_question: Insurance comparison, costs, coverage
- general_savings: Savings tips, frugal living, budgeting
- resource_request: Looking for senior-focused tools or resources

Post title: {title}
Post content: {content}

Respond with ONLY the category name, nothing else."""


# ---------------------------------------------------------------------------
# Reply generation prompt
# ---------------------------------------------------------------------------

_REPLY_PROMPT = """You are drafting a Reddit reply that will be posted from the official Saverwell account (u/Saverwell). Saverwell is a free resource that helps seniors find verified discounts, protect against scams, and navigate Medicare.

IMPORTANT: You are writing as Saverwell, first-person. Use "we" language naturally:
- "We put together a guide on this" or "We cover this in our article on [topic]"
- "We built a free tool that..." or "We have a breakdown of..."
- NEVER write as a third party recommending Saverwell ("I heard about a site called...", "you might check out...", "there's a site called Saverwell...")
- You ARE Saverwell. Own it, but stay humble and helpful, not salesy.

ORIGINAL POST ({platform}):
Title: {title}
Content: {content}

POST TYPE: {post_type}

CANNED RESPONSE TEMPLATE (adapt to first-person Saverwell voice):
{canned_template}

SAVERWELL BRAND VOICE:
{brand_voice}

CONTENT PILLAR: {pillar}

{guide_links_section}

PLATFORM GUIDELINES ({platform}):
{platform_guidelines}

TONE AND STYLE:
- Warm, genuine, helpful. You are the Saverwell team member who created these resources and genuinely wants to help.
- Start with empathy or a direct answer to their question. Lead with value, not with "Hey, we're Saverwell."
- Mention Saverwell resources naturally in context: "We actually wrote a guide on exactly this" or "We break this down step by step here."
- Keep it conversational for Reddit. No corporate speak or marketing jargon.
- Match the tone and formality of the original post.
- Keep it brief and scannable.
- NEVER use em dashes (the long dash character). Use commas, periods, or " - " instead.
- This is a DRAFT for human review. A team member will personalize and post.

CRITICAL RULES:
- All links use saverwell.com (never other domains for Saverwell content)
- Never pushy or salesy. Offer the resource, don't push it.
- Never promise specific savings amounts or guarantees
- Do not make medical or financial advice claims
- Keep under 300 characters for Reddit, can be slightly longer for other platforms
- NEVER use em dashes

Write the reply draft. Lead with empathy or a direct answer, then naturally reference the relevant Saverwell resource.

After the reply, add a line with exactly "---REVIEWER NOTES---" and then any notes for the human reviewer: context flags, tone guidance, or things to verify before posting. Keep reviewer notes concise and actionable."""


# ---------------------------------------------------------------------------
# Platform guidelines
# ---------------------------------------------------------------------------

_SCORE_PROMPT = """Score this post for Saverwell outreach potential. Saverwell helps seniors (60+) and retirees save money, avoid scams, and navigate Medicare. Our audience is people already in retirement or approaching it, NOT younger adults.

Evaluate 5 dimensions, each 0-10:

1. **Pillar Match** - How well does this align with Saverwell's 3 pillars (Savings/Discounts, Protection/Fraud, Guides/Medicare)?
2. **Help-Seeking Intent** - Is the person actively asking for help, advice, or resources? Higher = more urgent/explicit need.
3. **Recency** - Is this post recent enough to still be relevant? (Consider: {hours_old} hours old)
4. **Engagement Potential** - Can Saverwell genuinely add value here? Is there a natural fit for a helpful reply?
5. **Audience Fit** (CRITICAL - this is a hard gate) - Is the poster likely a senior (60+), retiree, or caring for an aging parent?

{subreddit_context}

Audience Fit scoring rules:
- Score 8-10: Clear senior/retiree signals (mentions retirement, Social Security, Medicare, pension, fixed income, age 60+, grandchildren, downsizing, AARP, "my elderly parent")
- Score 6-7: Probable senior/retiree (context suggests older adult but no explicit age mention, discusses retirement planning in near-term, mentions adult children)
- Score 4-5: Ambiguous - could be any age, no clear demographic signals either way
- Score 0-3: Likely NOT a senior. Red flags: mentions student loans, first job, college, grad school, entry-level, internship, "just graduated", young ages (teens/20s/30s), starting career, babies/toddlers/young kids, "my first apartment", saving for a house at a young age, early career milestones

If audience_fit is 4 or below, the lead will be auto-skipped. Be rigorous - when in doubt on a general subreddit, score conservatively.

POST:
Platform: {platform}
Subreddit: {subreddit}
Title: {title}
Content: {content}

Also determine:
- pillar: Which Saverwell pillar fits best? One of: Savings, Protection, Guides, General
- post_type: One of: discount_seeking, fraud_alert, medicare_question, insurance_question, general_savings, resource_request
- monetization_signal: Brief note on any monetization relevance (e.g. "Asking about hearing aid costs - affiliate opportunity" or "General question - low monetization" or empty string)

Respond with ONLY valid JSON, no markdown fences:
{{"pillar_match": 7, "help_seeking": 8, "recency": 9, "engagement": 6, "audience_fit": 8, "total": 38, "pillar": "Savings", "post_type": "discount_seeking", "monetization_signal": "..."}}"""


_PLATFORM_GUIDELINES = {
    "reddit": "Conversational tone, no corporate-speak, match subreddit culture. Keep under 300 characters. Use markdown sparingly. Do not sound like an ad.",
    "facebook": "Friendly, warm, community tone. Can be slightly longer than Reddit. Encouraging and practical.",
    "nextdoor": "Neighborly, local-focused tone. Mention ZIP code tool naturally. Helpful without being salesy.",
}


# ---------------------------------------------------------------------------
# Helper: split reply and reviewer notes
# ---------------------------------------------------------------------------


def split_reply_and_notes(text: str) -> Tuple[str, str]:
    """Split a combined draft reply into (reply_text, reviewer_notes).

    Handles the explicit delimiter format and common LLM variations:
    - ---REVIEWER NOTES---
    - --- followed by note headers
    """
    if not text or not text.strip():
        return "", ""

    # Explicit delimiter (primary format from prompt)
    if "---REVIEWER NOTES---" in text:
        parts = text.split("---REVIEWER NOTES---", 1)
        return _strip_draft_boilerplate(parts[0].strip().rstrip("-").strip()), parts[1].strip()

    # Common note header patterns (case-insensitive)
    _headers = (
        r"(?:HUMAN\s+)?REVIEWER\s+NOTES?"
        r"|NOTES?\s+(?:TO|FOR)\s+(?:THE\s+)?(?:HUMAN\s+)?REVIEWER"
        r"|DRAFT\s+NOTES?\s+(?:(?:TO|FOR)\s+(?:THE\s+)?(?:HUMAN\s+)?REVIEWER)?"
        r"|DRAFT\s+NOTES?"
    )

    # Pattern: --- separator then any note header
    sep_pattern = re.compile(
        r"\n---[\s\n]*"
        r"(?:\*?~?\d+\s*characters?[^\n]*\*?\s*\n+)?"
        r"((?:>\s*)?[\*_]{0,2}[\[{(]?[\*_]{0,2}(?:" + _headers + r"))",
        re.IGNORECASE,
    )
    match = sep_pattern.search(text)
    if match:
        reply = text[: match.start()].strip()
        notes_raw = text[match.start() :].strip()
        notes_raw = re.sub(r"^---\s*\n*", "", notes_raw).strip()
        notes_raw = re.sub(r"^\*?~?\d+\s*characters?[^\n]*\*?\s*\n+", "", notes_raw).strip()
        notes_raw = re.sub(
            r"^(?:>\s*)?[\*_]{0,2}[\[{(]?[\*_]{0,2}"
            r"(?:" + _headers + r")[^:\n]*[:\]})]*[\*_]{0,2}\s*",
            "",
            notes_raw,
            flags=re.IGNORECASE,
        ).strip()
        return _strip_draft_boilerplate(reply), notes_raw

    return _strip_draft_boilerplate(text.strip()), ""


def _strip_draft_boilerplate(text: str) -> str:
    """Remove LLM-generated 'DRAFT' / 'human review' boilerplate from reply text.

    Handles common LLM artifacts so the Draft Reply cell is copy-paste ready.
    """
    cleaned = text

    # Strip **DRAFT REPLY:** / **REPLY DRAFT:** headers
    cleaned = re.sub(
        r"^\*{0,2}(?:DRAFT\s+REPLY|REPLY\s+DRAFT):?\*{0,2}\s*\n?",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Strip preamble mentioning "human review" or "DRAFT" before ---
    m = re.search(
        r"^(.*?(?:human review|DRAFT|draft|personalization before posting).*?)\n*---+\n*",
        cleaned,
        re.IGNORECASE | re.DOTALL,
    )
    if m and m.start() == 0 and m.end() < 400:
        cleaned = cleaned[m.end() :]

    # Strip residual markdown artifacts
    cleaned = cleaned.lstrip()
    while cleaned.startswith("---"):
        cleaned = cleaned[3:].lstrip()
    while cleaned.startswith("**\n") or cleaned.startswith("**\r"):
        cleaned = cleaned[2:].lstrip()

    # Brand voice: replace em/en dashes with " - " (single space each side)
    cleaned = cleaned.replace("\u2014", " - ")  # em dash
    cleaned = cleaned.replace("\u2013", " - ")  # en dash
    while "  - " in cleaned or " -  " in cleaned or "  -  " in cleaned:
        cleaned = cleaned.replace("  -  ", " - ").replace("  - ", " - ").replace(" -  ", " - ")

    return cleaned.strip()


# ---------------------------------------------------------------------------
# Main generator class
# ---------------------------------------------------------------------------


class SaverwellReplyGenerator:
    """Generates draft Saverwell replies with brand voice, post-type awareness, and pillar detection."""

    def __init__(
        self,
        llm: BaseLLM,
        classification_llm: Optional[BaseLLM] = None,
        scanning_llm: Optional[BaseLLM] = None,
    ) -> None:
        self._llm = llm
        self._classification_llm = classification_llm or llm
        self._scanning_llm = scanning_llm

    async def classify_post_type(self, title: str, content: str) -> str:
        """Classify a post into one of the 6 Saverwell post types."""
        prompt = _CLASSIFY_PROMPT.format(title=title, content=(content or "")[:1000])
        try:
            resp = await self._classification_llm.complete([Message(role="user", content=prompt)])
            response = resp.content
            post_type = response.strip().lower().replace(" ", "_")
            valid_types = {
                "discount_seeking",
                "fraud_alert",
                "medicare_question",
                "insurance_question",
                "general_savings",
                "resource_request",
            }
            if post_type in valid_types:
                return post_type
            # Try to match partial
            for vt in valid_types:
                if vt in post_type:
                    return vt
            return "general_savings"  # safe fallback
        except Exception as e:
            logger.warning("saverwell_post_type_classification_failed", error=str(e))
            return "general_savings"

    async def score_lead(
        self,
        title: str,
        content: str,
        platform: str = "reddit",
        hours_old: float = 0,
        subreddit: str = "",
    ) -> Dict[str, Any]:
        """Score a lead for outreach potential using scanning LLM (Haiku).

        Returns dict with: pillar_match, help_seeking, recency, engagement,
        audience_fit, total, pillar, post_type, monetization_signal.
        If audience_fit < 5, sets audience_mismatch=True for caller to handle.
        """
        llm = self._scanning_llm or self._classification_llm

        # Subreddits where demographics are self-selecting (seniors/retirees/caregivers)
        senior_subs = {
            "medicare", "socialsecurity", "seniorcitizens", "eldercare",
            "aging", "boomer", "overfifty", "agingparents", "caregiversupport",
            "caregivers", "elderlycare", "hospice", "parkinsons", "dementia",
            "alzheimers", "medicaid", "hearingaids", "veteransbenefits",
            "estateplanning",
        }
        sub_lower = subreddit.lower().replace("r/", "") if subreddit else ""
        if sub_lower in senior_subs:
            subreddit_context = (
                f"This post is from r/{subreddit}, a subreddit that self-selects for "
                f"seniors, retirees, or caregivers. Audience fit is likely high (7+) "
                f"unless there are explicit signals the poster is young."
            )
        elif sub_lower:
            subreddit_context = (
                f"This post is from r/{subreddit}, a GENERAL subreddit that attracts "
                f"all ages. You MUST find positive evidence the poster is a senior (60+), "
                f"retiree, or caring for an aging parent. Without clear demographic signals, "
                f"score audience_fit LOW (0-4). Do NOT assume someone is a senior just because "
                f"they are asking about budgeting, debt, or savings - younger people ask "
                f"these questions too."
            )
        else:
            subreddit_context = (
                "No subreddit info available. Look for explicit demographic signals. "
                "Without them, score audience_fit conservatively (4-5)."
            )

        prompt = _SCORE_PROMPT.format(
            platform=platform,
            subreddit=subreddit or "unknown",
            title=title,
            content=(content or "")[:3000],
            hours_old=round(hours_old, 1) if hours_old else "unknown",
            subreddit_context=subreddit_context,
        )
        defaults: Dict[str, Any] = {
            "pillar_match": 0,
            "help_seeking": 0,
            "recency": 0,
            "engagement": 0,
            "audience_fit": 0,
            "total": 0,
            "pillar": self.detect_pillar(title, content),
            "post_type": "general_savings",
            "monetization_signal": "",
        }
        try:
            resp = await llm.complete([Message(role="user", content=prompt)])
            text = resp.content.strip()
            # Strip markdown fences if present
            if text.startswith("```"):
                text = re.sub(r"^```(?:json)?\s*", "", text)
                text = re.sub(r"\s*```$", "", text)
            parsed = json.loads(text)
            # Validate and cap scores
            for key in ("pillar_match", "help_seeking", "recency", "engagement", "audience_fit"):
                val = parsed.get(key, 0)
                parsed[key] = max(0, min(10, int(val)))
            parsed["total"] = sum(
                parsed[k]
                for k in ("pillar_match", "help_seeking", "recency", "engagement", "audience_fit")
            )
            # Hard gate: audience_fit < 5 means audience mismatch
            parsed["audience_mismatch"] = parsed["audience_fit"] < 5
            return parsed
        except Exception as e:
            logger.warning("saverwell_score_lead_failed", error=str(e))
            return defaults

    @staticmethod
    def detect_pillar(title: str, content: str) -> str:
        """Detect which Saverwell content pillar is most relevant based on keywords.

        Returns one of: "Savings", "Protection", "Guides", or "General".
        """
        combined = (title + " " + (content or "")).lower()
        scores = {}
        for pillar, keywords in _PILLAR_KEYWORDS.items():
            count = 0
            for kw in keywords:
                pattern = re.compile(r"\b" + re.escape(kw) + r"\b")
                if pattern.search(combined):
                    count += 1
            scores[pillar] = count

        best_pillar = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best_pillar] == 0:
            return "General"
        return best_pillar

    async def generate_reply(
        self,
        title: str,
        content: str,
        post_type: str,
        platform: str,
        brand_voice: str,
        guide_slugs: Optional[List[str]] = None,
    ) -> Tuple[str, Optional[str], List[str]]:
        """Generate a draft reply for a Saverwell lead post.

        Args:
            title: Post title.
            content: Post body content.
            post_type: One of the 6 Saverwell post types.
            platform: Platform name (reddit, facebook, nextdoor).
            brand_voice: Saverwell brand voice text.
            guide_slugs: Optional list of relevant guide article slugs
                (e.g., ["medicare-part-b-guide", "senior-discounts-by-state"]).
                When provided, formatted as links for the LLM to reference.

        Returns:
            (reply_text, canned_response_scenario_used, warnings)
        """
        # Select best matching canned response
        canned_template, canned_name = self._select_canned_response(post_type)

        # Detect content pillar
        pillar = self.detect_pillar(title, content)

        platform_guidelines = _PLATFORM_GUIDELINES.get(platform, _PLATFORM_GUIDELINES["reddit"])

        # Build guide links section
        if guide_slugs:
            links = "\n".join(f"- saverwell.com/guides/{slug}" for slug in guide_slugs)
            guide_links_section = f"RELEVANT GUIDES (reference naturally if helpful):\n{links}"
        else:
            guide_links_section = ""

        prompt = _REPLY_PROMPT.format(
            platform=platform,
            title=title,
            content=(content or "")[:2000],
            post_type=post_type,
            canned_template=canned_template,
            brand_voice=brand_voice[:1000],
            pillar=pillar,
            guide_links_section=guide_links_section,
            platform_guidelines=platform_guidelines,
        )

        warnings: List[str] = []
        try:
            config = RefinementConfig(
                criteria=_SAVERWELL_CRITERIA,
                max_iterations=3,
                quality_threshold=8.0,
                log_prefix="saverwell_reply_refinement",
                extra_revision_instructions="Keep reply under 300 characters for Reddit. No corporate speak. Peer-like tone.",
            )
            hooks = build_hook_chain(
                make_em_dash_hook(),
                make_char_limit_hook(300) if platform == "reddit" else None,
            )
            loop = RefinementLoop(
                config=config,
                generation_llm=self._llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)
            reply_text = _strip_draft_boilerplate(result.content.strip())
        except Exception as e:
            logger.error("saverwell_reply_generation_failed", error=str(e))
            return f"[GENERATION FAILED: {e}]", None, [f"Generation error: {e}"]

        # Basic validation warnings
        if len(reply_text) > 300 and platform == "reddit":
            warnings.append(f"Reply is {len(reply_text)} chars, exceeds 300-char Reddit limit")
        if "saverwell.com" not in reply_text.lower():
            warnings.append("Reply does not mention saverwell.com - consider adding a link")

        return reply_text, canned_name, warnings

    @staticmethod
    def _select_canned_response(post_type: str) -> Tuple[str, Optional[str]]:
        """Select the best matching canned response for the post type.

        Returns: (template_text, scenario_name)
        """
        # Map post types to canned response scenarios
        type_to_scenario = {
            "discount_seeking": "discount_seeking_general",
            "fraud_alert": "fraud_alert",
            "medicare_question": "medicare_question",
            "insurance_question": "medicare_question",  # closest match
            "general_savings": "general_savings",
            "resource_request": "resource_request",
        }

        target_scenario = type_to_scenario.get(post_type, "general_savings")

        for canned in _CANNED_RESPONSES:
            if canned["scenario"] == target_scenario:
                return canned["template"], canned["scenario"]

        # Fallback: first response
        first = _CANNED_RESPONSES[0]
        return first["template"], first["scenario"]
