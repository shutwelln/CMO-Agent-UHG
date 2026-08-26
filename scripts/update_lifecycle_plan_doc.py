#!/usr/bin/env python3
"""Update Saverwell Lifecycle Marketing Plan Google Doc with campaign details.

Reads the existing doc, converts to DOC_STRUCTURE, modifies specific sections,
adds new campaign sections (Protection Drip, Expert Guide Series, Medicare Guides),
and rebuilds via DocsAgent._update_google_doc().
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cmo_agent.agents.docs import DocsAgent  # noqa: E402
from cmo_agent.config import get_settings  # noqa: E402
from cmo_agent.db.database import Database  # noqa: E402
from cmo_agent.google_auth import get_google_credentials  # noqa: E402
from cmo_agent.llm.anthropic import AnthropicLLM  # noqa: E402
from cmo_agent.workspace.manager import WorkspaceManager  # noqa: E402

DOC_ID = "1C8yuO1FYQx92hFe-qV2W5evNgEi0-qBzDhkDFBhsKqs"


# ═══════════════════════════════════════════════════════════════════════════
# Google Docs JSON → DOC_STRUCTURE converter
# ═══════════════════════════════════════════════════════════════════════════


def _extract_text(para: dict) -> str:
    """Build paragraph text with **bold** markers."""
    parts: list[str] = []
    for elem in para.get("elements", []):
        run = elem.get("textRun", {})
        t = run.get("content", "").rstrip("\n")
        ts = run.get("textStyle", {})
        if ts.get("bold") and t.strip():
            parts.append(f"**{t.strip()}**")
        else:
            parts.append(t)
    return "".join(parts).strip()


def _extract_cell_text(cell: dict) -> str:
    """Extract plain text from a table cell."""
    parts: list[str] = []
    for ci in cell.get("content", []):
        if "paragraph" in ci:
            for elem in ci["paragraph"].get("elements", []):
                parts.append(elem.get("textRun", {}).get("content", "").strip())
    return " ".join(parts).strip()


def gdoc_to_structure(doc_json: dict) -> dict:
    """Convert a Google Docs API response to DOC_STRUCTURE format."""
    body = doc_json["body"]["content"]
    sections: list[dict] = []
    current_content: list[dict] = []
    pending_bullets: list[str] = []
    toc_text_seen = False

    def flush_bullets() -> None:
        nonlocal pending_bullets
        if pending_bullets:
            current_content.append({"type": "bullets", "items": pending_bullets[:]})
            pending_bullets = []

    for element in body:
        if "paragraph" in element:
            para = element["paragraph"]
            style = para.get("paragraphStyle", {}).get(
                "namedStyleType", "NORMAL_TEXT"
            )
            bullet = para.get("bullet")
            text = _extract_text(para)

            if not text:
                continue

            # Skip table of contents placeholder
            if text == "Table of Contents" and not toc_text_seen:
                toc_text_seen = True
                continue

            if "HEADING" in style:
                flush_bullets()
                level = int(style.replace("HEADING_", ""))
                new_section = {"heading": text, "level": level, "content": []}
                sections.append(new_section)
                current_content = new_section["content"]
            elif bullet:
                pending_bullets.append(text)
            else:
                flush_bullets()
                current_content.append({"type": "paragraph", "text": text})

        elif "table" in element:
            flush_bullets()
            table = element["table"]
            headers: list[str] = []
            rows: list[list[str]] = []
            for i, row in enumerate(table.get("tableRows", [])):
                row_data = [
                    _extract_cell_text(cell)
                    for cell in row.get("tableCells", [])
                ]
                if i == 0:
                    headers = row_data
                else:
                    rows.append(row_data)
            current_content.append(
                {"type": "table", "headers": headers, "rows": rows}
            )

    flush_bullets()
    return {
        "title": doc_json.get("title", ""),
        "include_toc": toc_text_seen,
        "sections": sections,
    }


# ═══════════════════════════════════════════════════════════════════════════
# New campaign sections to insert
# ═══════════════════════════════════════════════════════════════════════════

PROTECTION_DRIP_SECTIONS = [
    {
        "heading": "Protection Content Drip (8 Emails, Weekly Tuesdays)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Type: Segment-triggered campaign in Customer.io. Trigger segment: welcome_flow_started = true AND subscribed to Fraud Protection topic. Cadence: Weekly on Tuesdays. Exit: Person unsubscribes from Fraud Protection. Re-entry: Do not allow re-entry.",
            },
            {
                "type": "paragraph",
                "text": "This campaign starts immediately after the Welcome Flow completes (when welcome_flow_started is set to true). It sends one protection article per week, covering online safety, fraud prevention, account security, and identity theft.",
            },
            {
                "type": "table",
                "headers": ["#", "Week", "Subject", "Slug", "Topic"],
                "rows": [
                    ["1", "Tue 1", "Shop Online Safely: Protect Your Money", "safe-online-shopping-tips", "Fraud Protection"],
                    ["2", "Tue 2", "Password Safety: Your First Line of Defense", "password-safety-guide", "Fraud Protection"],
                    ["3", "Tue 3", "Bank Impostor Calls: How to Spot Them", "bank-impostor-calls", "Fraud Protection"],
                    ["4", "Tue 4", "Subscription Traps and Unauthorized Charges", "subscription-traps-unauthorized-charges", "Fraud Protection"],
                    ["5", "Tue 5", "What to Do If Your Email Gets Hacked", "email-account-hacked", "Fraud Protection"],
                    ["6", "Tue 6", "What to Do After a Data Breach", "what-to-do-after-a-data-breach", "Fraud Protection"],
                    ["7", "Tue 7", "Two-Factor Authentication Made Simple", "two-factor-authentication-guide", "Fraud Protection"],
                    ["8", "Tue 8", "Tax Identity Theft: How to Protect Yourself", "tax-identity-theft", "Fraud Protection"],
                ],
            },
        ],
    },
    {
        "heading": "Protection Drip - Journey End Actions",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Journey end action: Update Attribute - set protection_drip_completed = true. This attribute triggers the Expert Guide Series campaign to begin.",
            },
        ],
    },
    {
        "heading": "Protection Drip - Template Format",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": 'All 8 email templates are pre-built as body-only HTML (for the Saverwell Standard layout) in data/saverwell/email_templates/drip_protection_*.html. Each email has a headline, intro paragraph, "Read the full article" CTA button, and closing text. Templates are pasted into Customer.io campaign email steps via Code view.',
            },
        ],
    },
]

EXPERT_GUIDE_SECTIONS = [
    {
        "heading": "Expert Guide Series Campaign (13 Emails, Weekly Thursdays)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Type: Segment-triggered campaign in Customer.io. The Expert Guide Series is a year-round drip campaign covering insurance, medical alerts, phones, hearing aids, and finance topics. It runs on Thursdays after the Protection Drip completes.",
            },
            {
                "type": "paragraph",
                "text": 'Trigger segment: "Expert Guides Ready" - defined as welcome_flow_started = true AND protection_drip_completed = true AND subscribed to Educational Guides topic AND expert_guides_completed does not equal true. This ensures the campaign only starts after a subscriber has finished both the Welcome Flow and the Protection Drip.',
            },
            {
                "type": "paragraph",
                "text": "Cadence: Weekly on Thursdays. Exit: Person unsubscribes from Educational Guides topic. Re-entry: Do not allow re-entry. From: no-reply@saverwell.com.",
            },
            {
                "type": "paragraph",
                "text": "The sequence alternates topics for variety so subscribers do not receive several insurance or product review guides in a row.",
            },
            {
                "type": "table",
                "headers": ["#", "Week", "Subject", "Slug", "Category"],
                "rows": [
                    ["1", "Thu 1", "Medicare Vision: What's Covered & What's Not", "does-medicare-cover-vision", "insurance"],
                    ["2", "Thu 2", "Medicare Hearing Aid Coverage Explained", "does-medicare-cover-hearing-aids", "insurance"],
                    ["3", "Thu 3", "Cut Your Phone Bill by $40+ Per Month", "cell-phone-plans-seniors", "phones"],
                    ["4", "Thu 4", "Medical Alert Systems: What You Need to Know", "medical-alert-systems-guide", "medical-alerts"],
                    ["5", "Thu 5", "Dental Care After 65: Your Coverage Options", "dental-insurance-seniors", "insurance"],
                    ["6", "Thu 6", "When Should You Claim Social Security?", "when-to-claim-social-security", "finance"],
                    ["7", "Thu 7", "Auto & Home Insurance: Save After 55", "auto-home-insurance-seniors", "insurance"],
                    ["8", "Thu 8", "Save Thousands on Hearing Aids", "save-on-hearing-aids", "hearing-aids"],
                    ["9", "Thu 9", "Medical Alert Costs: Hidden Fees Revealed", "medical-alert-systems-cost", "medical-alerts"],
                    ["10", "Thu 10", "Vision Insurance: Worth It or Waste of Money?", "vision-insurance-seniors", "insurance"],
                    ["11", "Thu 11", "Cut Your Phone Bill in Half After 65", "cut-phone-bill-after-65", "phones"],
                    ["12", "Thu 12", "Life Insurance After 65: What You Need to Know", "life-insurance-seniors-over-65", "insurance"],
                    ["13", "Thu 13", "Tax Breaks You're Missing After 65", "tax-deductions-seniors-over-65", "finance"],
                ],
            },
        ],
    },
    {
        "heading": "Expert Guide Series - Journey End Actions",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Journey end action: Update Attribute - set expert_guides_completed = true. This attribute is available for future re-engagement campaigns.",
            },
        ],
    },
    {
        "heading": "Topic Mix and Ordering Rationale",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "The 13 guides span 5 verticals: Insurance (6), Medical Alerts (2), Phones (2), Hearing Aids (1), and Finance (2). The sequence alternates verticals to maintain engagement variety. The first two guides (vision and hearing aid coverage) bridge from Medicare content the subscriber already received in the Welcome Flow, creating a natural transition to broader topics.",
            },
            {
                "type": "paragraph",
                "text": "Title compliance: All titles avoid superlatives (Best, Cheapest) that could imply editorial endorsement. Neutral framing is used throughout: Compare Your Options, What to Know, Your Options Explained.",
            },
        ],
    },
    {
        "heading": "Expert Guide Series - Template Format",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": 'All 13 email templates are pre-built as body-only HTML in data/saverwell/email_templates/drip_guide_01_*.html through drip_guide_13_*.html. Each email has a headline, intro paragraph, "Read the full guide" CTA button linking to saverwell.com/guides/{category}/{slug}, and closing text. Emails 01-12 say "New expert guides every Thursday, covering insurance, medical alerts, hearing aids, phones, and more." Email 13 says "More expert guides are on the way. Keep an eye out for new topics every Thursday."',
            },
            {
                "type": "paragraph",
                "text": "Email treatment: Emails do NOT contain affiliate links. The CTA drives to the guide page on saverwell.com where affiliate content lives. This keeps emails clean and CAN-SPAM simple.",
            },
        ],
    },
]

MEDICARE_GUIDE_SECTIONS = [
    {
        "heading": "Medicare Guides Broadcast Series (11 Emails, Seasonal AEP)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Type: API-triggered broadcast series via n8n (not a Customer.io campaign journey). The Medicare Guides series is a seasonal deployment aligned to the Annual Enrollment Period (AEP). Unlike the evergreen campaigns (Welcome, Protection, Expert Guides), Medicare content is delivered as weekly broadcasts so that all eligible subscribers receive the same guide at the same time. AEP has a fixed deadline, so synchronized delivery is the right model.",
            },
            {
                "type": "paragraph",
                "text": "Sends on Wednesdays to avoid overlap with the Expert Guide Series (Thursdays). This eliminates the need to pause or resume any Customer.io journey during AEP. Subscribers in the Expert Guide Series continue receiving those emails on Thursdays without interruption.",
            },
            {
                "type": "paragraph",
                "text": 'Target segment: "Guide Content Eligible" - welcome_flow_started = true AND subscribed to Educational Guides topic. From: no-reply@saverwell.com.',
            },
            {
                "type": "paragraph",
                "text": "Timing strategy: AEP runs October 15 through December 7 each year. Launch the first email in early September so subscribers have time to read all 11 guides before AEP decisions need to be made. A September 3 launch (first Wednesday) puts the final email on November 12, giving subscribers 5 weeks of AEP with the full guide series complete.",
            },
            {
                "type": "table",
                "headers": ["#", "Week", "Subject", "Slug"],
                "rows": [
                    ["1", "Wed 1", "Medicare Made Simple: Your Complete Guide", "medicare-explained-simple-guide"],
                    ["2", "Wed 2", "Medicare Parts A, B, C, D: What's Covered?", "medicare-parts-a-b-c-d-explained"],
                    ["3", "Wed 3", "7 Ways to Cut Your Medicare Premiums", "save-money-medicare-premiums"],
                    ["4", "Wed 4", "Medicare Deadlines That Cost You Money", "medicare-enrollment-deadlines"],
                    ["5", "Wed 5", "Medicare Advantage vs Original: Which Saves?", "medicare-advantage-vs-original"],
                    ["6", "Wed 6", "Does Medicare Cover Your Prescriptions?", "does-medicare-cover-prescriptions"],
                    ["7", "Wed 7", "Medicare vs Medicaid: Know the Difference", "medicare-vs-medicaid-difference"],
                    ["8", "Wed 8", "Medicare Dental Gap: What You Need to Know", "does-medicare-cover-dental"],
                    ["9", "Wed 9", "Avoid $500+ Medicare IRMAA Surcharges", "irmaa-avoid-higher-medicare-premiums"],
                    ["10", "Wed 10", "Cut Prescription Costs to Under $5", "medicare-extra-help-prescription-savings"],
                    ["11", "Wed 11", "Medicare Supplement: What's Covered?", "medicare-supplement-plans-explained"],
                ],
            },
        ],
    },
    {
        "heading": "Medicare Guides - Broadcast Mechanics",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": 'n8n workflow: "Saverwell Medicare AEP Broadcast". Schedule trigger: every Wednesday at 8:00 AM CST during the AEP window (September through mid-November). The workflow checks the current date against the AEP start date to determine which email (1-11) to send, then triggers the Customer.io Broadcast API with the corresponding template content.',
            },
            {
                "type": "paragraph",
                "text": "After the final broadcast (week 11), the n8n workflow batch-updates all recipients via the Customer.io Batch API: set medicare_guides_completed = true. This attribute is available for future seasonal follow-up campaigns and prevents duplicate delivery the following year.",
            },
        ],
    },
    {
        "heading": "Medicare Guides - Why Broadcasts Instead of a Campaign Journey",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "No pause/resume problem. A Customer.io journey cannot be cleanly paused and resumed without emails queuing up or subscribers dropping out. Broadcasts avoid this entirely.",
                    "No day-of-week conflict. Expert Guide Series owns Thursdays. Medicare broadcasts own Wednesdays. Both run simultaneously without overlap.",
                    "Synchronized delivery. AEP has a fixed deadline. All eligible subscribers should receive the same guide at the same time, not on per-subscriber lifecycle timing.",
                    "Year-to-year flexibility. Adjusting the AEP start date or reordering guides only requires changing the n8n workflow schedule, not rebuilding a Customer.io journey.",
                    "Reusable pattern. The same broadcast approach works for future seasonal campaigns (Tax Season, OEP, Holiday Shopping) without creating new Customer.io journeys each time.",
                ],
            },
        ],
    },
    {
        "heading": "Medicare Guides - Template Format",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": 'All 11 email templates are pre-built as body-only HTML in data/saverwell/email_templates/medicare_guide_01_*.html through medicare_guide_11_*.html. Emails 01-10 say "New Medicare guides every week, covering enrollment, costs, coverage, and ways to save." Email 11 (the final email) says "That wraps up our Medicare guide series. Keep an eye out for more expert guides on insurance, savings, and staying protected."',
            },
        ],
    },
    {
        "heading": "Medicare Guides - Frequency Impact During AEP",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "During the 11-week AEP window, most subscribers receive 3 emails per week: Monday digest + Wednesday Medicare + Thursday Expert Guides. The Protection Drip (Tuesdays) will have completed for most subscribers by September, since it runs for 8 weeks and subscribers who joined before July will have finished. For the small cohort of late subscribers still in the Protection Drip when AEP starts, the temporary peak is 4 emails per week (Mon + Tue + Wed + Thu) for the remaining Protection Drip weeks. This is acceptable for a limited seasonal window with time-sensitive AEP content.",
            },
        ],
    },
]

REENGAGEMENT_SECTIONS = [
    {
        "heading": "Win-Back / Re-Engagement Campaign (3 Emails, 14 Days + 30-Day Wait)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Type: Segment-triggered campaign in Customer.io. Trigger segment: Inactive 30 Days (lifecycle_stage = active, no opens or clicks in 30 days). Cadence: Day 0, Day 7, Day 14 followed by a 30-day engagement wait. Exit: Person unsubscribes from all topics. Re-entry: Allow re-entry (subscriber can become inactive again after re-engaging).",
            },
            {
                "type": "paragraph",
                "text": "This campaign activates independently whenever a subscriber goes inactive at any point after the Welcome Flow. It runs alongside the other campaigns, not as a sequential step. The goal is to re-engage inactive subscribers with a value-first approach before sunsetting unresponsive profiles.",
            },
            {
                "type": "paragraph",
                "text": "Subscription topic: Product & Marketing (meta-campaign, not content-specific). From: no-reply@saverwell.com.",
            },
            {
                "type": "table",
                "headers": ["#", "Day", "Subject", "Content Approach", "Topic"],
                "rows": [
                    ["1", "Day 0", "Still Finding Savings Near You?", "Warm value reminder. Highlights new discounts, protection tips, and guides added since last engagement. CTA drives to discount map personalized by ZIP.", "Product & Marketing"],
                    ["2", "Day 7", "A Quick Fraud Protection Update", "Protection angle with emotional relevance. References latest protection content. Frames as making sure they saw important updates. CTA drives to protection hub.", "Fraud Protection"],
                    ["3", "Day 14", "Should We Keep Your Updates Coming?", "Respectful direct ask. Primary CTA to confirm continued interest. Secondary link to preference center. Mentions emails will be paused without response.", "Product & Marketing"],
                ],
            },
        ],
    },
    {
        "heading": "Re-Engagement - Journey End Actions",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "After Email 3, the journey waits 30 days for any email link click. The journey then branches:",
            },
            {
                "type": "bullets",
                "items": [
                    "If the subscriber clicked any link: Set re_engaged = true. The subscriber stays active and continues receiving content. They can re-enter the campaign if they go inactive again.",
                    "If no clicks after 30 days: Set lifecycle_stage = sunset and suppress the person. This removes them from all future sends. Total time from inactivity detection to sunset: 44 days (14-day email sequence + 30-day wait).",
                ],
            },
        ],
    },
    {
        "heading": "Re-Engagement - Template Format",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": 'All 3 email templates are pre-built as body-only HTML in data/saverwell/email_templates/reengagement_1_value_reminder.html, reengagement_2_protection_update.html, and reengagement_3_stay_or_go.html. Email 1 highlights new content and drives to the discount map. Email 2 leads with fraud protection relevance. Email 3 is a respectful opt-in confirmation with a secondary preference center link.',
            },
        ],
    },
]

SUDDEN_MONEY_SECTIONS = [
    {
        "heading": "Sudden Money After 55 Drip (5 Emails, Behavior-Triggered)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Type: Segment-triggered campaign in Customer.io. Trigger: User downloads lump-sum content, visits financial planning guides (permission-to-spend-in-retirement, dont-pay-it-back-yet-checklist), or is manually added to segment. Cadence: Day 0, Day 3, Day 7, Day 12, Day 17. Exit: Person unsubscribes from Educational Guides. Re-entry: Do not allow re-entry.",
            },
            {
                "type": "paragraph",
                "text": "This campaign targets seniors and retirees who received an unexpected lump sum (inheritance, home sale, pension buyout, life insurance payout). It provides a structured 90-day framework: pause and assess, organize into three pots, understand tax implications, find trustworthy advisors, and execute a checklist-based action plan. Educational framing throughout, no specific product recommendations.",
            },
            {
                "type": "table",
                "headers": ["#", "Day", "Subject", "Content Approach"],
                "rows": [
                    ["1", "Day 0", "You just got a big check. Here's the one thing to do first.", "Park the money, don't rush. CTA: permission-to-spend-in-retirement guide"],
                    ["2", "Day 3", "A simple way to organize your windfall", "Three Pots framework (safety net, debt clearance, growth). CTA: when-to-claim-social-security guide"],
                    ["3", "Day 7", "That lump sum might come with a tax bill", "Tax implications by source type: inheritance, pension buyout, home sale, life insurance. IRMAA warning. CTA: irmaa-avoid-higher-medicare-premiums guide"],
                    ["4", "Day 12", "3 questions to ask before you trust anyone with your money", "Fiduciary, fee structure, credentials. Red flags. CTA: how-to-spot-fake-financial-coach guide"],
                    ["5", "Day 17", "Your 90-day plan for that lump sum", "Printable checklist: Days 1-14 (secure), 15-30 (professional input), 31-60 (plan), 61-90 (execute). CTA: full guides library"],
                ],
            },
        ],
    },
    {
        "heading": "Sudden Money - Campaign Notes",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Content compliance: No specific product recommendations, no personalized financial advice, educational framing throughout. 'Talk to a professional' recommended at every decision point. Suppression: Suppress if user enters another active drip sequence. Key metrics: 35%+ open rate, 5%+ CTR, 60%+ sequence completion, flag if unsubscribe rate exceeds 1% on any email.",
            },
            {
                "type": "paragraph",
                "text": "Content location: data/saverwell/email_campaigns/sudden_money_after_55_drip.md. Status: Content drafted, pending Customer.io deployment.",
            },
        ],
    },
]

MEDICARE_MYTHS_SECTIONS = [
    {
        "heading": "What Medicare Actually Covers - Myth-Busting Series (4 Emails, Behavior-Triggered)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Type: Segment-triggered campaign in Customer.io. Trigger: User visits Medicare guide pages, downloads Medicare content, or is manually added to segment. Cadence: Day 0, Day 4, Day 8, Day 13. Exit: Person unsubscribes from Educational Guides. Re-entry: Do not allow re-entry.",
            },
            {
                "type": "paragraph",
                "text": "This campaign educates adults 60+ who are approaching Medicare eligibility or currently enrolled. It covers the five biggest Medicare coverage gaps, hidden costs (IRMAA, Part D donut hole, no out-of-pocket maximum), the Advantage vs Original tradeoff, and money-saving programs most people never apply for (Extra Help, Medicare Savings Programs, IRMAA appeals). Suppression: Suppress if user is already in the Expert Guide Series Medicare emails.",
            },
            {
                "type": "table",
                "headers": ["#", "Day", "Subject", "Content Approach"],
                "rows": [
                    ["1", "Day 0", "5 things Medicare doesn't cover (number 4 surprises everyone)", "Coverage gaps: dental, vision, hearing aids, long-term care, foreign travel. CTA: does-medicare-cover-dental guide"],
                    ["2", "Day 4", "Medicare isn't free. Here's what it actually costs.", "Part B premiums, IRMAA surcharge, Part D donut hole, no OOP maximum. CTA: irmaa-avoid-higher-medicare-premiums guide"],
                    ["3", "Day 8", "Medicare Advantage vs Original Medicare: which one is right?", "Network restrictions, prior authorization, geographic limits, switching difficulty. CTA: medicare-advantage-vs-original guide"],
                    ["4", "Day 13", "4 ways to pay less for Medicare", "Extra Help, Medicare Savings Programs, Supplement enrollment timing, IRMAA appeals. CTA: save-money-medicare-premiums guide"],
                ],
            },
        ],
    },
    {
        "heading": "Medicare Myths - Campaign Notes",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": 'Content compliance: No specific plan or carrier recommendations, no personalized advice. Educational framing: "factors to consider," "types available," "questions to ask." Medicare Supplement used throughout (never Medigap per brand voice). IRMAA spelled out on first use. Key metrics: 40%+ open rate, 6%+ CTR, 65%+ sequence completion, flag if unsubscribe rate exceeds 0.8%.',
            },
            {
                "type": "paragraph",
                "text": "Content location: data/saverwell/email_campaigns/medicare_myths_email_series.md. Status: Content drafted, pending Customer.io deployment.",
            },
        ],
    },
]

FRAUD_LEAD_MAGNET_SECTIONS = [
    {
        "heading": "Senior Fraud Protection Lead Magnet (3 Emails, Download-Triggered)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": 'Type: Segment-triggered campaign in Customer.io. Trigger: User downloads the "Senior Fraud Protection" PDF checklist. Cadence: Day 0, Day 3, Day 7. Exit: Person unsubscribes from Fraud Protection. Re-entry: Do not allow re-entry. Post-sequence: Move subscriber to general newsletter list.',
            },
            {
                "type": "paragraph",
                "text": "This campaign delivers the PDF lead magnet and follows up with two actionable protection emails. Email 1 delivers the download link plus 3 immediate action steps (save FTC number, check credit report, enable transaction alerts). Email 2 covers the number one fraud type targeting seniors (government impostor calls) with specific protection rules. Email 3 provides a 15-minute protection setup plan (credit freeze, fraud alert, free credit monitoring).",
            },
            {
                "type": "table",
                "headers": ["#", "Day", "Subject", "Content Approach"],
                "rows": [
                    ["1", "Day 0", "Your fraud protection checklist is ready - download it here", "PDF delivery + 3 immediate action steps. CTA: senior-scam-protection-complete-guide"],
                    ["2", "Day 3", "The number one financial threat targeting seniors right now", "Government impostor calls: how they work, protection rules. CTA: senior-scam-protection-complete-guide"],
                    ["3", "Day 7", "3 free fraud alerts you can set up today (takes 15 minutes)", "Credit freeze + fraud alert + free monitoring setup. CTA: finance guide hub"],
                ],
            },
        ],
    },
    {
        "heading": "Fraud Lead Magnet - Campaign Notes",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": 'Lead magnet PDF requirements: Title "The Saverwell Fraud Protection Checklist," 1-page printable format, checklist style, condensed version of senior-scam-protection-complete-guide article, Saverwell branding. Hosted on Supabase CDN or static assets.',
            },
            {
                "type": "paragraph",
                "text": "Content compliance: No specific product recommendations, no fearmongering, practical and actionable tone. Government resources cited with official URLs. Key metrics: 70%+ Email 1 open rate (just opted in), 45%+ Emails 2-3 open rate, 7%+ CTR, 70%+ sequence completion, 50%+ conversion to newsletter subscriber.",
            },
            {
                "type": "paragraph",
                "text": "Content location: data/saverwell/email_campaigns/senior_fraud_protection_lead_magnet.md. Status: Content drafted, pending Customer.io deployment.",
            },
        ],
    },
]

AHS_PARTNER_DRIP_SECTIONS = [
    {
        "heading": "AHS Home Warranty Partner Drip (3 Emails, Behavior-Triggered)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Type: Segment-triggered campaign in Customer.io. Trigger: User visits home warranty guides (home-warranty-explained, home-warranty-vs-home-insurance, best-home-warranty-seniors) or signs up via home warranty content gate. Cadence: Day 0, Day 4, Day 8. Exit: Person unsubscribes from Product & Marketing. Re-entry: Do not allow re-entry.",
            },
            {
                "type": "paragraph",
                "text": "Partner: American Home Shield (AHS). Monetization: Affiliate CTA in emails 2 and 3. Email 1 is education-only (no affiliate link) to establish trust. Emails 2 and 3 include a secondary partner CTA below the main guide CTA with affiliate disclosure. Audience: Homeowners aged 55+ concerned about unexpected repair costs on fixed income.",
            },
            {
                "type": "table",
                "headers": ["#", "Day", "Subject", "Content Approach", "Affiliate CTA"],
                "rows": [
                    ["1", "Day 0", "The home repair bill that catches retirees off guard", "Education: $5K-8K AC replacement, why fixed income makes repairs harder, what a home warranty covers. CTA: home-warranty-explained guide", "None"],
                    ["2", "Day 4", "Home warranty vs. home insurance: which one do you actually need?", "Comparison: insurance (disasters) vs warranty (breakdowns), no overlap, predictability value. CTA: best-home-warranty-seniors guide", "AHS: 50+ years, 23 systems/appliances"],
                    ["3", "Day 8", "Buying a home warranty? Ask these 5 questions first.", "Buying guide: service call fees, coverage details, contractor choice, claims process, cancellation. CTA: best-home-warranty-seniors guide", "AHS: three tiers, 30-day guarantee"],
                ],
            },
        ],
    },
    {
        "heading": "AHS Partner Drip - Campaign Notes",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Affiliate disclosure on emails 2 and 3: 'Saverwell may receive compensation if you purchase through our partner links. This doesn't affect our recommendations or the price you pay.' Partner CTA URLs use {AHS_AFFILIATE_URL} placeholder, to be replaced with live affiliate link after approval.",
            },
            {
                "type": "paragraph",
                "text": "Content location: data/saverwell/email_campaigns/ahs_home_warranty_drip.md. Status: Content drafted, pending Customer.io deployment and affiliate link activation.",
            },
        ],
    },
]

AARP_PARTNER_DRIP_SECTIONS = [
    {
        "heading": "AARP Membership Partner Drip (2 Emails, Behavior-Triggered)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Type: Segment-triggered campaign in Customer.io. Trigger: User visits AARP-related guides (is-aarp-membership-worth-it, aarp-discounts-complete-list) or signs up via AARP content gate. Cadence: Day 0, Day 4. Exit: Person unsubscribes from Product & Marketing. Re-entry: Do not allow re-entry.",
            },
            {
                "type": "paragraph",
                "text": "Partner: AARP. Monetization: Affiliate CTA in email 2 only. Email 1 is education-only analysis (no affiliate link). Email 2 reveals lesser-known discounts and includes a secondary partner CTA for joining AARP. Audience: Adults aged 50+ evaluating whether AARP membership is worth the cost.",
            },
            {
                "type": "table",
                "headers": ["#", "Day", "Subject", "Content Approach", "Affiliate CTA"],
                "rows": [
                    ["1", "Day 0", "Is AARP worth $16/year? We did the math.", "Value analysis: high-value discounts (travel, restaurants, cell plans, insurance) vs low-value ones (grocery, pharmacy, entertainment). Non-discount benefits (Tax-Aide, Medicare tools, fraud helpline). CTA: is-aarp-membership-worth-it guide", "None"],
                    ["2", "Day 4", "12 AARP discounts you're probably not using", "Lesser-known discounts across everyday (cell plans, hearing aids, vision, prescriptions), travel (rental cars, cruises), home/auto (security, Hartford insurance), and financial (Tax-Aide, planning tools). CTA: aarp-discounts-complete-list guide", "AARP: $16/yr or $12/yr for 5-year"],
                ],
            },
        ],
    },
    {
        "heading": "AARP Partner Drip - Campaign Notes",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Affiliate disclosure on email 2: 'Saverwell may receive compensation if you join through our partner link. This doesn't affect our recommendations or the price you pay.' Partner CTA URL uses {AARP_AFFILIATE_URL} placeholder, to be replaced with live affiliate link after approval.",
            },
            {
                "type": "paragraph",
                "text": "Content location: data/saverwell/email_campaigns/aarp_membership_drip.md. Status: Content drafted, pending Customer.io deployment and affiliate link activation.",
            },
        ],
    },
]

CAMPAIGN_SEQUENCING_SECTIONS = [
    {
        "heading": "Campaign Sequencing & Attribute Flow",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "The subscriber journey has three layers: a sequential campaign chain (Welcome, Protection, Expert Guides) that progresses via profile attributes; parallel elements (Medicare broadcasts, Re-Engagement) that run independently based on timing or inactivity; and behavior-triggered campaigns (Sudden Money, Medicare Myths, Fraud Lead Magnet, AHS Partner Drip, AARP Partner Drip) that activate based on content engagement or lead magnet downloads.",
            },
            {
                "type": "paragraph",
                "text": "Day 0: Subscriber enters. The Welcome Flow starts (5 emails over 14 days).",
            },
            {
                "type": "paragraph",
                "text": "Day 14: Welcome Flow completes. Sets lifecycle_stage = active and welcome_flow_started = true. Subscriber enters the Protection Content Eligible segment.",
            },
            {
                "type": "paragraph",
                "text": "Next Tuesday: Protection Drip starts (8 emails, weekly Tuesdays).",
            },
            {
                "type": "paragraph",
                "text": "~8 weeks later: Protection Drip completes. Sets protection_drip_completed = true. Subscriber enters the Expert Guides Ready segment.",
            },
            {
                "type": "paragraph",
                "text": "Next Thursday: Expert Guide Series starts (13 emails, weekly Thursdays).",
            },
            {
                "type": "paragraph",
                "text": "~13 weeks later: Expert Guide Series completes. Sets expert_guides_completed = true.",
            },
            {
                "type": "paragraph",
                "text": "September through mid-November (AEP window): Medicare Guides broadcast series (11 emails, weekly Wednesdays). Runs as n8n-triggered broadcasts in parallel with the Expert Guide Series. All eligible subscribers receive the same guide each week. No Customer.io journey, no pause/resume needed.",
            },
            {
                "type": "paragraph",
                "text": "At any point after Welcome Flow: If a subscriber has no opens or clicks for 30 days, they enter the Inactive 30 Days segment and the Re-Engagement Campaign starts (3 emails over 14 days). If no response after 30 more days, the subscriber is sunset and suppressed. If re-engaged, they stay active and can re-enter the campaign if they go inactive again.",
            },
            {
                "type": "paragraph",
                "text": "Total subscriber journey: Welcome (2 weeks) + Protection (8 weeks) + Expert Guides (13 weeks) = approximately 23 weeks of structured evergreen content. Medicare broadcasts layer on top during AEP (September-November) on Wednesdays, running in parallel without disrupting the Thursday Expert Guide Series. Re-engagement runs independently whenever a subscriber goes inactive.",
            },
            {
                "type": "paragraph",
                "text": "Behavior-triggered campaigns run independently of the sequential chain. Sudden Money After 55 (5 emails, 17 days) activates when a subscriber engages with lump-sum/financial planning content. Medicare Myths (4 emails, 13 days) activates on Medicare guide engagement. Fraud Protection Lead Magnet (3 emails, 7 days) activates on PDF download. AHS Home Warranty (3 emails, 8 days) and AARP Membership (2 emails, 4 days) are partner monetization drips triggered by relevant guide visits. These campaigns can run concurrently with the sequential chain since they target different content interests.",
            },
        ],
    },
    {
        "heading": "Key Attributes for Campaign Chaining",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Attribute", "Set By", "Used By"],
                "rows": [
                    ["welcome_flow_started", "Welcome Flow (after Email 5)", "Protection Drip + Expert Guide Series (entry trigger)"],
                    ["protection_drip_completed", "Protection Drip (after Email 8)", "Expert Guide Series (entry trigger via Expert Guides Ready segment)"],
                    ["expert_guides_completed", "Expert Guide Series (after Email 13)", "Re-engagement campaigns, future content targeting"],
                    ["medicare_guides_completed", "n8n Medicare AEP workflow (after broadcast 11, batch API)", "Future seasonal follow-ups, prevents duplicate AEP delivery"],
                    ["re_engaged", "Re-Engagement Campaign (if subscriber clicked)", "Analytics, future targeting, re-entry eligibility"],
                ],
            },
        ],
    },
    {
        "heading": "Required Segments for Campaign Chaining",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "In addition to the segments defined in the Unsubscribe Group Architecture section, one new segment is needed for the Expert Guide Series:",
            },
            {
                "type": "paragraph",
                "text": '**Segment: "Expert Guides Ready"** - Conditions: welcome_flow_started equals true AND protection_drip_completed equals true AND subscribed to topic Educational Guides AND expert_guides_completed does NOT equal true.',
            },
        ],
    },
]

DELIVERABLES_STATUS_SECTIONS = [
    {
        "heading": "Deliverables Completion Status",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["Deliverable", "Status", "Location"],
                "rows": [
                    ["Lifecycle Marketing Plan (this doc)", "COMPLETE", "This document"],
                    ["Customer.io Setup Guide", "COMPLETE", "data/saverwell/customerio_setup_guide.md"],
                    ["Welcome Campaign Templates (5)", "COMPLETE", "data/saverwell/email_templates/welcome_*.html"],
                    ["Protection Drip Templates (8)", "COMPLETE", "data/saverwell/email_templates/drip_protection_*.html"],
                    ["Expert Guide Series Templates (13)", "COMPLETE", "data/saverwell/email_templates/drip_guide_*.html"],
                    ["Medicare Guide Templates (11)", "COMPLETE", "data/saverwell/email_templates/medicare_guide_*.html"],
                    ["Re-Engagement Templates (3)", "COMPLETE", "data/saverwell/email_templates/reengagement_*.html"],
                    ["Saverwell Standard Layout + Snippets", "COMPLETE", "data/saverwell/email_templates/layout_*.html, snippet_*.html"],
                    ["Content Queue Google Sheet", "COMPLETE", "Google Sheet (linked)"],
                    ["Content Expansion Strategy", "COMPLETE", "data/saverwell/content_expansion_strategy.md"],
                    ["n8n Lifecycle Subscribe Workflow", "COMPLETE (inactive)", "n8n workflow hYsgc6mF8A5gQ0X5"],
                    ["Sudden Money After 55 Drip (5 emails)", "CONTENT DRAFTED", "data/saverwell/email_campaigns/sudden_money_after_55_drip.md"],
                    ["Medicare Myths Series (4 emails)", "CONTENT DRAFTED", "data/saverwell/email_campaigns/medicare_myths_email_series.md"],
                    ["Fraud Protection Lead Magnet (3 emails)", "CONTENT DRAFTED", "data/saverwell/email_campaigns/senior_fraud_protection_lead_magnet.md"],
                    ["AHS Home Warranty Partner Drip (3 emails)", "CONTENT DRAFTED", "data/saverwell/email_campaigns/ahs_home_warranty_drip.md"],
                    ["AARP Membership Partner Drip (2 emails)", "CONTENT DRAFTED", "data/saverwell/email_campaigns/aarp_membership_drip.md"],
                    ["Published Articles (53)", "COMPLETE", "8 protection + 11 Medicare + 13 expert + 21 expansion guides on saverwell.com"],
                    ["Customer.io Subscription Center + 5 Topics", "COMPLETE", "Created in Customer.io UI"],
                    ["Customer.io Segments (6)", "NOT STARTED", "Manual setup in Customer.io UI"],
                    ["Customer.io Welcome Campaign Journey", "COMPLETE", "Built in Customer.io UI (5-email journey)"],
                    ["Customer.io Protection Drip Journey", "COMPLETE", "Built in Customer.io UI (8-email journey)"],
                    ["Customer.io Expert Guide Series Journey", "NOT STARTED", "Manual setup in Customer.io UI (13-email journey)"],
                    ["Customer.io Re-Engagement Journey", "NOT STARTED", "Manual setup in Customer.io UI (3-email journey)"],
                    ["Customer.io Broadcast Templates (3)", "NOT STARTED", "Manual setup in Customer.io UI (Weekly Digest, Content Drip, Medicare AEP)"],
                    ["n8n Weekly Digest Builder Workflow", "NOT STARTED", "n8n workflow to build"],
                    ["n8n Medicare AEP Broadcast Workflow", "NOT STARTED", "n8n workflow to build (seasonal, Wednesdays Sept-Nov)"],
                    ["n8n Content Drip Engine Workflow", "NOT STARTED", "n8n workflow to build"],
                    ["Website Form Endpoint Switchover", "NOT STARTED", "Switch to lifecycle webhook"],
                ],
            },
            {
                "type": "paragraph",
                "text": "All content, templates, documentation, and automation scripts are complete. The Subscription Center, Welcome Campaign, and Protection Drip journeys are live in Customer.io. The remaining work is: 2 more core Customer.io campaign journeys (~2 hours manual), 5 behavior-triggered campaign journeys (~3 hours manual), 3 broadcast templates (~30 minutes manual), 6 segments (~30 minutes manual), n8n workflow activation and new workflow builds (~2.5 hours automated), and website form switchover (~15 minutes). Approximately 9 hours total remain.",
            },
        ],
    },
]

REVISED_ROADMAP_SECTIONS = [
    {
        "heading": "Implementation Roadmap (Revised)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "All content deliverables are complete: 57 email templates (40 core + 17 behavior-triggered/partner), setup guide, lifecycle plan, content queue, content expansion strategy, and 53 published articles. The n8n Lifecycle Subscribe workflow is built but inactive. The Subscription Center (5 topics), Welcome Campaign (5-email journey), and Protection Drip (8-email journey) are live in Customer.io. The remaining work covers 7 more campaign journeys (2 core + 5 behavior-triggered), broadcast templates, segments, n8n workflow activation, and go-live.",
            },
        ],
    },
    {
        "heading": "Completed Work",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "40 core email templates across 5 series (Welcome 5, Protection 8, Expert Guides 13, Medicare 11, Re-Engagement 3) plus layout and snippets, plus 17 behavior-triggered and partner drip emails (Sudden Money 5, Medicare Myths 4, Fraud Lead Magnet 3, AHS Partner 3, AARP Partner 2)",
                    "Customer.io setup guide with step-by-step instructions for 4 campaign journeys, 1 broadcast series, 6 segments, 5 subscription topics, and 3 broadcast templates",
                    "Customer.io Subscription Center with 5 topics (Savings & Discounts, Fraud Protection, Educational Guides, Weekly Digest, Product & Marketing) - live",
                    "Customer.io Welcome Campaign journey (5-email, 14-day sequence) - live",
                    "Customer.io Protection Drip journey (8-email, weekly Tuesdays) - live",
                    "Content Queue Google Sheet with Article Library, Seasonal Calendar, and Send Log tabs, populated with all 32 articles",
                    "n8n Lifecycle Subscribe workflow with Compute Lifecycle Attributes Code node, ZIP-to-state lookup, and Customer.io profile/event integration (inactive, ready to activate)",
                    "53 published articles on saverwell.com: 8 protection, 11 Medicare guides, 13 expert guides, 21 expansion guides across medical alerts, hearing aids, phones, home warranty, AARP, and financial planning",
                    "Content Expansion Strategy documenting 4-phase pipeline of 57 articles + 5 tools",
                ],
            },
        ],
    },
    {
        "heading": "Phase 1: Customer.io Foundation (~1 Hour Remaining)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Step", "Task", "Time", "Reference", "Status"],
                "rows": [
                    ["1", 'Enable Subscription Center. Create 5 topics: Savings & Discounts, Fraud Protection, Educational Guides, Weekly Digest, Product & Marketing. Set all to "Opted in by default."', "~15 min", "Setup Guide: Step 1", "COMPLETE"],
                    ["2", "Create 6 data-driven segments: New Subscribers, Active Subscribers, Protection Content Eligible, Guide Content Eligible, Expert Guides Ready, Inactive 30 Days.", "~30 min", "Setup Guide: Step 2", "NOT STARTED"],
                    ["3", "Activate the n8n Lifecycle Subscribe workflow. Test with a sample subscription to verify attributes flow into Customer.io.", "~15 min", "n8n workflow hYsgc6mF8A5gQ0X5", "NOT STARTED"],
                    ["4", "Send a test subscribe event and confirm: lifecycle_stage = new, welcome_flow_started = false, zip_code, state_resolved, content_interest all appear on the Customer.io profile.", "~15 min", "Setup Guide: Prerequisites", "NOT STARTED"],
                ],
            },
        ],
    },
    {
        "heading": "Phase 2: Campaign Journeys + Broadcast Templates (~2.5 Hours Remaining)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Step", "Task", "Time", "Reference", "Status"],
                "rows": [
                    ["1", "Create Welcome Campaign (5-email journey). Paste 5 HTML templates, configure 3-day/3-day/4-day/4-day delays, set journey end actions (lifecycle_stage = active, welcome_flow_started = true).", "~45 min", "Setup Guide: Step 3", "COMPLETE"],
                    ["2", "Create Protection Drip (8-email journey). Paste 8 templates, configure weekly Tuesday delays, set journey end action (protection_drip_completed = true).", "~45 min", "Setup Guide: Campaign 4", "COMPLETE"],
                    ["3", "Create Expert Guide Series (13-email journey). Paste 13 templates, configure weekly Thursday delays, set Expert Guides Ready trigger, set journey end action (expert_guides_completed = true).", "~1.5 hours", "Setup Guide: Campaign 2", "NOT STARTED"],
                    ["4", "Create Re-Engagement Campaign (3-email journey). Paste 3 templates, configure 7-day delays, set 30-day engagement wait, configure branch: re_engaged = true OR lifecycle_stage = sunset + suppress.", "~30 min", "Setup Guide: Campaign 5", "NOT STARTED"],
                    ["5", "Create 3 broadcast templates: Weekly Digest (Liquid variable slots for digest sections), Content Drip (Liquid variable slots for article content), and Medicare AEP (Liquid variable slots for Medicare guide content).", "~30 min", "Setup Guide: Post-Welcome Flow", "NOT STARTED"],
                ],
            },
        ],
    },
    {
        "heading": "Phase 3: Testing + Go-Live (~2 Hours)",
        "level": 2,
        "content": [
            {
                "type": "table",
                "headers": ["Step", "Task", "Time", "Method", "Status"],
                "rows": [
                    ["1", "Test all 4 campaign journeys: send test emails from each step, verify Liquid variables render (first_name, zip_code, unsubscribe), verify CTA links, check mobile rendering.", "~45 min", "Customer.io UI", "NOT STARTED"],
                    ["2", "Test with a real subscriber profile: create test profile with lifecycle_stage = new, welcome_flow_started = false. Verify segment entry, Email 1 sends, and subsequent emails arrive on schedule (use time travel).", "~30 min", "Customer.io UI", "NOT STARTED"],
                    ["3", "Build n8n Weekly Digest Builder workflow (Monday 6 AM schedule).", "~30 min", "n8n (automated)", "NOT STARTED"],
                    ["4", "Build n8n Medicare AEP Broadcast workflow (Wednesday schedule, Sept-Nov). Test with a single broadcast to a test segment.", "~30 min", "n8n (automated)", "NOT STARTED"],
                    ["5", "Switch website form endpoint from old subscribe workflow to Lifecycle Subscribe webhook. Deactivate old workflow (keep as backup).", "~15 min", "Website + n8n", "NOT STARTED"],
                    ["6", "Monitor first week of live sends. Track delivery rate (target >98%), open rate on Welcome Email 1 (target >30%), unsubscribe rate (target <0.5%).", "Ongoing", "Customer.io analytics", "NOT STARTED"],
                ],
            },
        ],
    },
    {
        "heading": "Future: Content Drip Engine (Post-Launch)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Once the 4 campaign journeys are live and subscribers are progressing through the journey, the Content Drip Engine n8n workflow can be built to handle future content beyond the initial 32 articles. This is not blocking launch. New articles are added to the Content Queue Google Sheet and the drip engine delivers them on schedule via Customer.io API-triggered broadcasts. Future seasonal campaigns (Tax Season, OEP, Holiday Shopping) follow the same broadcast pattern as the Medicare AEP series.",
            },
        ],
    },
    {
        "heading": "Total Remaining Effort",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "Approximately 9 hours of work remain: 1 hour for Customer.io foundation (segments, n8n workflow activation, testing), 2 hours for 2 remaining core campaign journeys, 3 hours for 5 behavior-triggered/partner campaign journeys, 30 minutes for 3 broadcast templates, and 2.5 hours for end-to-end testing, n8n workflow builds (digest + Medicare AEP broadcast), and go-live. The Subscription Center, Welcome Campaign, and Protection Drip are already live in Customer.io.",
            },
        ],
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# Modification functions
# ═══════════════════════════════════════════════════════════════════════════


def find_section_index(sections: list[dict], heading: str) -> int:
    """Find the index of a section by heading text."""
    for i, s in enumerate(sections):
        if s["heading"] == heading:
            return i
    return -1


def apply_modifications(structure: dict) -> dict:
    """Apply all modifications to the parsed structure."""
    sections = structure["sections"]

    # ── 1. Fix "Medigap" → "Medicare Supplement" globally ───────────
    for section in sections:
        if section["heading"]:
            section["heading"] = section["heading"].replace(
                "Medigap", "Medicare Supplement"
            )
        for item in section.get("content", []):
            if item.get("type") == "paragraph":
                item["text"] = item["text"].replace(
                    "Medigap", "Medicare Supplement"
                )
            elif item.get("type") == "table":
                for row in item.get("rows", []):
                    for j, cell in enumerate(row):
                        row[j] = cell.replace("Medigap", "Medicare Supplement")
                for j, h in enumerate(item.get("headers", [])):
                    item["headers"][j] = h.replace(
                        "Medigap", "Medicare Supplement"
                    )
            elif item.get("type") == "bullets":
                item["items"] = [
                    x.replace("Medigap", "Medicare Supplement")
                    for x in item["items"]
                ]

    # ── 2a. Remove sections that will be re-inserted (idempotent) ──
    removable_headings = [
        "Protection Content Drip",
        "Expert Guide Series Campaign",
        "Medicare Guides",
        "Win-Back / Re-Engagement Campaign",
        "Win-Back/Re-Engagement Campaign",
        "Sudden Money After 55",
        "What Medicare Actually Covers",
        "Senior Fraud Protection Lead Magnet",
        "AHS Home Warranty Partner Drip",
        "AARP Membership Partner Drip",
        "Campaign Sequencing & Attribute Flow",
        "Campaign Sequencing",
        # Deliverables + Roadmap sections (idempotent removal for re-runs)
        "Deliverables Completion Status",
        "Implementation Roadmap",
        # Safety net for orphaned phase subsections
        "Phase 1:",
        "Phase 2:",
        "Phase 3:",
        "Total Manual",
        "Completed Work",
        "Total Remaining Effort",
        "Future: Content Drip",
    ]
    for heading_pattern in removable_headings:
        while True:
            found = -1
            for i, s in enumerate(sections):
                if heading_pattern in s.get("heading", ""):
                    found = i
                    break
            if found < 0:
                break
            # Remove this H1 and its H2+ subsections
            end = found + 1
            while end < len(sections) and sections[end]["level"] > sections[found]["level"]:
                end += 1
            del sections[found:end]

    # ── 2c. Insert campaign sections after Welcome Campaign ──────────
    welcome_idx = find_section_index(
        sections, "Welcome/Onboarding Campaign (5 Emails, 14 Days)"
    )
    if welcome_idx == -1:
        print("WARNING: Could not find Welcome Campaign section")
        welcome_idx = 2  # fallback

    # Find the last H2 subsection of Welcome Campaign
    insert_at = welcome_idx + 1
    while insert_at < len(sections) and sections[insert_at]["level"] > 1:
        insert_at += 1

    # Insert in order: Protection Drip, Expert Guides, Medicare Guides,
    # Re-Engagement, Behavior-Triggered Campaigns, Partner Drips,
    # Campaign Sequencing
    new_sections = (
        PROTECTION_DRIP_SECTIONS
        + EXPERT_GUIDE_SECTIONS
        + MEDICARE_GUIDE_SECTIONS
        + REENGAGEMENT_SECTIONS
        + SUDDEN_MONEY_SECTIONS
        + MEDICARE_MYTHS_SECTIONS
        + FRAUD_LEAD_MAGNET_SECTIONS
        + AHS_PARTNER_DRIP_SECTIONS
        + AARP_PARTNER_DRIP_SECTIONS
        + CAMPAIGN_SEQUENCING_SECTIONS
    )
    for i, s in enumerate(new_sections):
        sections.insert(insert_at + i, s)

    # ── 3. Update article inventory table ───────────────────────────
    inv_idx = find_section_index(sections, "Current Article Inventory")
    if inv_idx >= 0:
        content = sections[inv_idx]["content"]
        for i, item in enumerate(content):
            if item.get("type") == "table":
                content[i] = {
                    "type": "table",
                    "headers": ["Category", "Count", "Status", "Verticals Covered"],
                    "rows": [
                        ["Protection Articles", "8", "Published (email variants ready)", "Online safety, fraud, identity theft, account security, scams"],
                        ["Medicare Guides", "11", "Published (email variants ready)", "Medicare Parts A-D, enrollment, costs, coverage, savings, Medicare Supplement"],
                        ["Expert Guides (non-Medicare)", "13", "Published (email variants ready)", "Insurance (vision, dental, life, auto/home), medical alerts, phones, hearing aids, finance (Social Security, tax deductions)"],
                        ["Expansion Guides (Phase 2)", "21", "Published", "Medical alerts (4: fall detection, watches, Medicare coverage, no-monthly-fee), hearing aids (2: OTC under $500, Medicare coverage), phones (2: free government, flip phones), home warranty (3), AARP (2), financial planning (8: conversations, tax, asset protection, crisis, permission, money management, Medicare brokers, Social Security, budgeting, scams)"],
                        ["Product Reviews (planned)", "12-18", "Pipeline", "Medical alerts (advanced), cell phone plans (advanced), hearing aids (advanced)"],
                        ["Finance & Retirement (planned)", "6-8", "Pipeline", "Social Security (advanced), reverse mortgages, property tax exemptions"],
                        ["Identity Theft & Digital Protection (planned)", "6-8", "Pipeline", "ID theft protection, credit freeze, password managers, home security"],
                        ["Tools/Calculators (planned)", "3-5", "Pipeline", "SS optimizer, retirement runway, savings finder"],
                    ],
                }
                break
        # Update the summary paragraph after the table
        for i, item in enumerate(content):
            if item.get("type") == "paragraph" and "33 current articles" in item.get("text", ""):
                content[i]["text"] = "All 53 published articles (8 protection + 11 Medicare + 13 expert guides + 21 expansion guides) have pre-built email variants (email_subject, email_preheader, email_intro_md, email_cta_label, email_cta_url) validated and ready for email delivery. All are published on saverwell.com with full SEO optimization including Article JSON-LD, FAQ schema, Twitter Cards, and internal cross-linking. Future articles will follow the same model."
                break

    # ── 4. Update "Content Queue" intro paragraph ───────────────────
    cq_idx = find_section_index(sections, "Content Queue & Evergreen Drip Engine")
    if cq_idx >= 0:
        content = sections[cq_idx]["content"]
        for i, item in enumerate(content):
            if item.get("type") == "paragraph" and "33 articles" in item.get("text", ""):
                content[i]["text"] = "The content library has 53 published articles (8 protection + 11 Medicare guides + 13 expert guides + 21 expansion guides across medical alerts, hearing aids, phones, home warranty, AARP, and financial planning), with additional articles planned across product reviews, advanced finance, and identity theft. Fixed-sequence drip campaigns handle the initial subscriber journey (Protection Drip, Expert Guide Series, Medicare Guides). Behavior-triggered campaigns (Sudden Money, Medicare Myths, Fraud Lead Magnet) and partner drips (AHS, AARP) activate based on content engagement. The Content Queue serves as the long-term editorial engine for ongoing and future content beyond the initial sequences."
                break

    # ── 5. Update second Content Queue intro paragraph ──────────────
    if cq_idx >= 0:
        content = sections[cq_idx]["content"]
        for i, item in enumerate(content):
            if item.get("type") == "paragraph" and "drip engine is driven by" in item.get("text", ""):
                content[i]["text"] = "For content beyond the fixed-sequence campaigns, the drip engine is driven by a Google Sheet content queue that acts as the single source of truth for article sequencing, priority, and seasonal boosts. n8n reads the sheet on schedule and sends via Customer.io API. This means anyone on the team can reorder articles, add seasonal boosts, or insert new content without touching any workflows or campaigns."
                break

    # ── 6. Update "Customer.io Campaigns (Created in UI)" ───────────
    cio_idx = find_section_index(sections, "Customer.io Campaigns (Created in UI)")
    if cio_idx >= 0:
        sections[cio_idx]["content"] = [
            {
                "type": "bullets",
                "items": [
                    "Welcome Campaign (5 emails, 14 days) [templates ready] - Segment-triggered journey on New Subscribers. Hardcoded sequence.",
                    "Protection Content Drip (8 emails, 8 weeks) [templates ready] - Segment-triggered journey on Protection Content Eligible. Weekly Tuesdays.",
                    "Expert Guide Series (13 emails, 13 weeks) [templates ready] - Segment-triggered journey on Expert Guides Ready. Weekly Thursdays. Year-round.",
                    "Re-Engagement Campaign (3 emails, 14 days) [templates ready] - Segment-triggered journey on Inactive 30 Days. Hardcoded sequence.",
                    "Weekly Digest Broadcast (1 template) [template ready] - API-triggered by n8n weekly digest workflow. Mondays.",
                    "Medicare AEP Broadcast (1 template) [template ready] - API-triggered by n8n Medicare AEP workflow. Wednesdays during AEP (Sept-Nov). 11 emails delivered as synchronized weekly broadcasts.",
                    "Content Drip Broadcast (1 template) [template ready] - API-triggered by n8n drip engine for future content beyond the fixed campaigns. Uses Liquid variables for article content.",
                    "Sudden Money After 55 (5-email drip) [content drafted] - Behavior-triggered on lump-sum content engagement. 17-day sequence.",
                    "What Medicare Actually Covers (4-email series) [content drafted] - Behavior-triggered on Medicare guide engagement. 13-day sequence.",
                    "Fraud Protection Lead Magnet (3-email sequence) [content drafted] - Download-triggered on PDF checklist request. 7-day sequence.",
                    "AHS Home Warranty Partner Drip (3-email series) [content drafted] - Behavior-triggered on home warranty guide visits. 8-day sequence. Affiliate CTA in emails 2-3.",
                    "AARP Membership Partner Drip (2-email series) [content drafted] - Behavior-triggered on AARP guide visits. 4-day sequence. Affiliate CTA in email 2.",
                ],
            },
        ]

    # ── 7. Update "What MUST Be Done in Customer.io UI" ────────────
    ui_idx = find_section_index(sections, "What MUST Be Done in Customer.io UI (No API Alternative)")
    if ui_idx >= 0:
        sections[ui_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "All HTML email templates and setup instructions referenced below are pre-built and documented in the Customer.io Setup Guide (data/saverwell/customerio_setup_guide.md). The manual work is building the campaign journeys in the UI and pasting the pre-built templates.",
            },
            {
                "type": "bullets",
                "items": [
                    "Create 4 core campaign journeys: Welcome (5-email), Protection Drip (8-email), Expert Guide Series (13-email), and Re-Engagement (3-email)",
                    "Create 5 behavior-triggered campaign journeys: Sudden Money (5-email), Medicare Myths (4-email), Fraud Lead Magnet (3-email), AHS Partner (3-email), AARP Partner (2-email)",
                    "Create 3 broadcast templates: Weekly Digest, Medicare AEP, and Content Drip (with Liquid variable slots)",
                    "Create 6 data-driven segments: New Subscribers, Active Subscribers, Protection Content Eligible, Expert Guides Ready, Guide Content Eligible, Inactive 30 Days",
                    "Enable Subscription Center + create 5 topics",
                    "Associate each campaign/broadcast with its relevant topic",
                    "Paste HTML email templates into all campaign journey steps (46 total email steps across 9 journeys)",
                ],
            },
        ]

    # ── 8. Insert Deliverables Status + Revised Roadmap ─────────────
    # Find KPIs section (insert before it) or fall back to end
    kpis_idx = find_section_index(sections, "KPIs and Success Metrics")
    if kpis_idx < 0:
        kpis_idx = len(sections)

    # Insert Revised Roadmap first (so it appears after Deliverables Status)
    for i, s in enumerate(REVISED_ROADMAP_SECTIONS):
        sections.insert(kpis_idx + i, s)

    # Insert Deliverables Status before the Revised Roadmap
    for i, s in enumerate(DELIVERABLES_STATUS_SECTIONS):
        sections.insert(kpis_idx + i, s)

    # ── 9. Update "Adding New Articles" subsection ──────────────────
    add_idx = find_section_index(sections, "Adding New Articles to the Queue")
    if add_idx >= 0:
        content = sections[add_idx]["content"]
        for i, item in enumerate(content):
            if item.get("type") == "paragraph" and "Medicare Supplement" in item.get("text", ""):
                # Already fixed by global Medigap replacement
                break
            if item.get("type") == "paragraph" and "new article is published" in item.get("text", ""):
                content[i]["text"] = "When a new article is published (e.g., a Medicare Supplement comparison guide), the process is:"
                break

    # ── 10. Add campaign chaining attributes to profile table ───────
    new_attrs_idx = find_section_index(sections, "New Computed Attributes (Added to Workflow Copy)")
    if new_attrs_idx >= 0:
        content = sections[new_attrs_idx]["content"]
        for i, item in enumerate(content):
            if item.get("type") == "table":
                item["rows"].extend([
                    ["protection_drip_completed", "Set to true by Protection Drip campaign journey end", "Triggers Expert Guide Series campaign entry"],
                    ["expert_guides_completed", "Set to true by Expert Guide Series campaign journey end", "Available for re-engagement campaigns"],
                    ["medicare_guides_completed", "Set to true by n8n Medicare AEP workflow (batch API after broadcast 11)", "Available for seasonal follow-ups, prevents duplicate AEP delivery"],
                    ["re_engaged", "Set to true by Re-Engagement Campaign (if subscriber clicked)", "Analytics, future targeting, re-entry eligibility"],
                ])
                break

    # ── 11. Update "How the Drip Engine Works" intro ────────────────
    drip_idx = find_section_index(sections, "How the Drip Engine Works")
    if drip_idx >= 0:
        content = sections[drip_idx]["content"]
        for i, item in enumerate(content):
            if item.get("type") == "paragraph" and "Instead of hardcoded" in item.get("text", ""):
                content[i]["text"] = "After subscribers complete the fixed-sequence campaigns (Protection Drip, Expert Guide Series), the Content Queue drip engine handles all future content delivery. The drip engine is a scheduled n8n workflow that determines what to send based on the Content Queue sheet. This approach scales to any number of articles and handles seasonal priority automatically."
                break

    # ── 12. Update Frequency Cap ──────────────────────────────────
    freq_idx = find_section_index(sections, "Frequency Cap")
    if freq_idx >= 0:
        sections[freq_idx]["content"] = [
            {
                "type": "paragraph",
                "text": "Standard cadence: Max 3 emails per week per subscriber. Monday digest + Tuesday protection + Thursday expert guide. This cadence prevents email fatigue while maintaining consistent touchpoints.",
            },
            {
                "type": "paragraph",
                "text": "During AEP (September through mid-November): Medicare broadcasts add a Wednesday send, bringing the maximum to 3 emails per week for most subscribers (Monday digest + Wednesday Medicare + Thursday expert guide). The Protection Drip (Tuesdays) will have completed for most subscribers by September. Subscribers still in the Protection Drip when AEP starts would temporarily receive 4 per week (Mon + Tue + Wed + Thu) until the Protection Drip completes, which is acceptable for a limited seasonal window with time-sensitive enrollment content.",
            },
        ]

    return structure


# ═══════════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════════


async def main() -> None:
    settings = get_settings()
    db = Database(db_path=settings.db_path)
    await db.initialize()

    workspace_mgr = WorkspaceManager(db, Path(settings.brand_voices_dir))
    writing_llm = AnthropicLLM(
        api_key=settings.get_llm_api_key(),
        model=settings.llm_model_writing,
    )

    docs_agent = DocsAgent(
        llm=writing_llm,
        db=db,
        workspace_manager=workspace_mgr,
        google_credentials_path=settings.google_credentials_path,
        google_oauth_token_path=settings.google_oauth_token_path,
    )

    # ── Step 1: Read existing doc ───────────────────────────────────
    print("Reading existing document...")
    from googleapiclient.discovery import build

    creds = get_google_credentials(
        service_account_path=settings.google_credentials_path,
        oauth_token_path=settings.google_oauth_token_path,
        scopes=[
            "https://www.googleapis.com/auth/documents",
            "https://www.googleapis.com/auth/drive.file",
        ],
    )
    service = build("docs", "v1", credentials=creds, cache_discovery=False)
    doc = service.documents().get(documentId=DOC_ID).execute()

    # ── Step 2: Convert to DOC_STRUCTURE ────────────────────────────
    print("Converting to DOC_STRUCTURE format...")
    structure = gdoc_to_structure(doc)
    print(f"  Parsed {len(structure['sections'])} sections")

    # ── Step 3: Apply modifications ─────────────────────────────────
    print("Applying modifications...")
    structure = apply_modifications(structure)
    print(f"  Final structure: {len(structure['sections'])} sections")

    # Print section list for verification
    for s in structure["sections"]:
        indent = "  " * (s["level"] - 1)
        print(f"  {indent}[H{s['level']}] {s['heading']}")

    # ── Step 4: Update the Google Doc ───────────────────────────────
    print("\nUpdating Google Doc...")
    result = docs_agent._update_google_doc(
        DOC_ID, structure, workspace_id="saverwell"
    )

    if result.get("status") == "updated":
        print("\nDocument updated successfully!")
        print(f"  URL: {result.get('google_docs_url')}")
        print(f"  Sections: {result.get('sections')}")
    else:
        print(f"\nUpdate failed: {result}")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
