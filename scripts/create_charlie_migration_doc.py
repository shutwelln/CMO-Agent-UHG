#!/usr/bin/env python3
"""One-off script: Creates a Google Doc for the Charlie Saver to Saverwell Migration Campaign.

Run:  python scripts/create_charlie_migration_doc.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# -- Google Auth ---------------------------------------------------------------
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def get_services():
    """Return (docs_service, drive_service) using existing project credentials.

    Uses OAuth2 only - the Saverwell service account does not have
    Google Docs API permissions.  The service account works for Sheets
    but not for Docs/Drive document creation.
    """
    from googleapiclient.discovery import build
    from cmo_agent.google_auth import get_google_credentials

    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json")
    )

    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path="",
        scopes=SCOPES,
    )
    if creds is None:
        raise RuntimeError(
            "No Google credentials found. "
            "Set GOOGLE_OAUTH_TOKEN_PATH or GOOGLE_CREDENTIALS_PATH."
        )

    docs = build("docs", "v1", credentials=creds)
    drive = build("drive", "v3", credentials=creds)
    return docs, drive


# -- Inline formatting parser --------------------------------------------------
def parse_inline(text: str) -> Tuple[str, List[Tuple[int, int, str]]]:
    """Parse **bold** and *italic* markers."""
    runs: List[Tuple[int, int, str]] = []
    chars: List[str] = []
    i, length = 0, len(text)
    while i < length:
        if i + 1 < length and text[i] == "*" and text[i + 1] == "*":
            end = text.find("**", i + 2)
            if end != -1:
                s = len(chars)
                inner = text[i + 2 : end]
                chars.extend(inner)
                runs.append((s, s + len(inner), "bold"))
                i = end + 2
                continue
        if text[i] == "*" and (i + 1 >= length or text[i + 1] != "*"):
            end = text.find("*", i + 1)
            if end != -1:
                s = len(chars)
                inner = text[i + 1 : end]
                chars.extend(inner)
                runs.append((s, s + len(inner), "italic"))
                i = end + 1
                continue
        chars.append(text[i])
        i += 1
    return "".join(chars), runs


# -- Document structure --------------------------------------------------------
TITLE = "Charlie Saver to Saverwell Migration Campaign"

SECTIONS: List[Dict[str, Any]] = [
    # -- Context ---------------------------------------------------------------
    {
        "heading": "Context",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Charlie Saver (CharleSaver.com) was a senior discount and "
                    "fraud protection service that is winding down. Their "
                    "Customer.io instance with ~250K-300K email subscribers is "
                    "still active but expires mid-April 2026. This creates a "
                    "~4-week window to send emails FROM Charlie's platform, "
                    "leveraging their established sender reputation and subscriber "
                    "trust for much higher open rates than cold outbound would achieve."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "A separate charlie_list_outbound_plan.md already exists for "
                    "later SendGrid-based outbound from Saverwell's own domain. "
                    "This campaign runs FIRST from Charlie's side, and the two plans "
                    "are complementary - the SendGrid plan handles any contacts who "
                    "do not convert during this migration window."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "The Saverwell frontend already has a partner config system with "
                    "a co-branded partner page experience. The Charlie Saver logo is "
                    "in Supabase. Emails use Charlie Saver's actual brand colors "
                    "(dark purple #3B2D5E, green #3DAA68, cream #F5F0EB) so "
                    "subscribers recognize the look."
                ),
            },
        ],
    },
    # -- Narrative Framework ---------------------------------------------------
    {
        "heading": "Narrative Framework",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Every email walks a legal and emotional tightrope. "
                    "The sender is \"Charlie Saver\" (the discount and fraud "
                    "protection service). Never \"Charlie\" alone, never "
                    "\"Charlie Financial\", never \"the Charlie bank\". "
                    "Saverwell is a third party that Charlie Saver recommends, "
                    "not \"us\" or \"our new name\"."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "Charlie Saver was a service that helped members find senior "
                    "discounts and avoid fraud. Do NOT mention banking, account "
                    "closures, financial products, or corporate decisions. Tone "
                    "is warm, direct, brief - a real person closing a small shop "
                    "and telling regulars where to go next."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "No em dashes or en dashes. No mid-sentence bolding. Subject "
                    "lines: 6-8 words, sentence case. Preheader: 40-70 characters."
                ),
            },
        ],
    },
    # -- Deliverables ----------------------------------------------------------
    {
        "heading": "Deliverables",
        "level": 1,
        "content": [],
    },
    {
        "heading": "1. Charlie Migration Email Layout Template",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "**File:** data/saverwell/email_templates/layout_charlie_migration.html"
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "A full HTML email layout matching Charlie Saver's actual email "
                    "style. Table-based layout with MSO Outlook conditionals, 600px "
                    "fixed width, responsive with mobile breakpoint. Social icons "
                    "removed (acquisition TBD). Privacy link updated to charlesaver.com."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Charlie Saver Brand Identity:**",
            },
            {
                "type": "table",
                "headers": ["Element", "Value"],
                "rows": [
                    ["Logo", "\"Charlie\" in dark purple serif + green price-tag with \"Saver\" in white"],
                    ["Email background", "Warm cream/off-white (#F5F0EB)"],
                    ["Heading color", "Dark purple (#3B2D5E)"],
                    ["Body text", "Dark charcoal on cream, sans-serif, centered alignment"],
                    ["Accent / tag green", "Medium green (#3DAA68)"],
                    ["Headline font", "Serif (Georgia, Times New Roman fallback)"],
                    ["Body font", "Sans-serif system stack"],
                    ["Footer", "Charlie Financial Inc., 10250 Constellation Blvd Floor 23, Los Angeles CA 90067"],
                    ["Privacy link", "charlesaver.com/privacy"],
                    ["Social icons", "Removed"],
                    ["Tagline", "Your home for the best senior discounts."],
                ],
            },
        ],
    },
    {
        "heading": "2. Eight Migration Emails (Body-Only HTML)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Each email is a body-only HTML snippet that gets pasted into "
                    "the Charlie layout in Customer.io. Compressed cadence: 8 emails "
                    "(6 standard + 2 account holder custom) over 18 days."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Standard sequence (Segments B, C, D):**",
            },
            {
                "type": "table",
                "headers": ["#", "Day", "Subject (A/B)", "CTA Color"],
                "rows": [
                    [
                        "1", "0",
                        "\"Charlie Saver is moving to a new home\" / \"Where your savings features are going next\"",
                        "Charlie green",
                    ],
                    [
                        "2", "3",
                        "\"Savings near you we wanted you to see\" / \"Discounts you might be missing\"",
                        "Saverwell teal",
                    ],
                    [
                        "3", "6",
                        "\"One tip that could save you thousands\" / \"A financial warning we wish we sent sooner\"",
                        "Saverwell teal",
                    ],
                    [
                        "4", "9",
                        "\"Guides your wallet will thank you for\" / \"7 ways to cut your Medicare premiums\"",
                        "Saverwell teal",
                    ],
                    [
                        "5", "13",
                        "\"Your fellow Charlie Saver members already joined\" / \"Your neighbors are already saving\"",
                        "Saverwell teal",
                    ],
                    [
                        "6", "18",
                        "\"One last thing from Charlie Saver\" / \"Our final email, and a thank you\"",
                        "Charlie green",
                    ],
                ],
            },
            {
                "type": "paragraph",
                "text": "**Fatigued account holder sequence (Segment A):**",
            },
            {
                "type": "table",
                "headers": ["#", "Day", "Subject (A/B)", "CTA Color"],
                "rows": [
                    [
                        "1a", "0",
                        "\"This one is not about your account\" / \"Your discounts are not going away\"",
                        "Charlie green",
                    ],
                    [
                        "1b", "3",
                        "\"Senior discounts near [zip]\" / \"Your savings just got bigger\"",
                        "Saverwell teal",
                    ],
                    [
                        "-", "6+",
                        "Merges into standard Email 2 onward",
                        "-",
                    ],
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "**CTA strategy:** Emails 1, 1a, and 6 use Charlie green "
                    "(#3DAA68) CTA buttons (bookending the series in Charlie "
                    "Saver's identity). Emails 1b, 2-5 use Saverwell teal "
                    "(#2BBFB3) buttons (introducing Saverwell's visual identity). "
                    "All CTAs link to saverwell.com?utm_campaign=CharlieSaver "
                    "(triggers partner welcome overlay)."
                ),
            },
        ],
    },
    # -- Email 1a (Account Holder) ---------------------------------------------
    {
        "heading": "Email 1a: Account Holder Intro (Day 0, Segment A only)",
        "level": 3,
        "content": [
            {
                "type": "paragraph",
                "text": "**File:** charlie_migration_01a_account_holder.html",
            },
            {
                "type": "paragraph",
                "text": (
                    "Short email (~150 words) for fatigued account holders who "
                    "received 20+ closure comms in Dec/Jan. Opens by acknowledging "
                    "fatigue directly: \"We know you have heard from us more than "
                    "you wanted to lately. This is not about your account.\" Pivots "
                    "to discounts and protection features getting a new home through "
                    "Saverwell. No closing paragraphs - ends after CTA."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "CTA button: \"See your discounts on Saverwell\" (Charlie green #3DAA68)",
                    "Tone: Direct, empathetic, brief",
                    "Half the length of standard Email 1",
                ],
            },
        ],
    },
    # -- Email 1b (Account Holder Value) ---------------------------------------
    {
        "heading": "Email 1b: Account Holder Value (Day 3, Segment A only)",
        "level": 3,
        "content": [
            {
                "type": "paragraph",
                "text": "**File:** charlie_migration_01b_account_holder_value.html",
            },
            {
                "type": "paragraph",
                "text": (
                    "Value-forward email with no preamble. Jumps straight to "
                    "\"senior discounts near [zip code]\". Includes stat cards "
                    "(1,900+ Merchants, 125,000+ Locations, 75+ Guides). Mentions "
                    "fraud protection guides and Medicare resources. Brief sign-off: "
                    "\"More next week.\" After this email, Segment A merges into "
                    "the standard sequence at Email 2."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "CTA button: \"Find discounts near you\" (Saverwell teal #2BBFB3)",
                    "Zip code personalization in subject line and heading",
                    "Bridges fatigued segment into standard cadence",
                ],
            },
        ],
    },
    # -- Email 1 ---------------------------------------------------------------
    {
        "heading": "Email 1: Announcement (Day 0)",
        "level": 3,
        "content": [
            {
                "type": "paragraph",
                "text": "**File:** charlie_migration_01_announcement.html",
            },
            {
                "type": "paragraph",
                "text": (
                    "Note from the Charlie Saver team. Identifies sender as someone "
                    "who ran the discount and protection features. States simply that "
                    "Charlie Saver is winding down. Introduces Saverwell as where "
                    "these features continue: 1,900+ discounts, 75+ guides, free "
                    "weekly digest. No explanation of why - no banking references. "
                    "Closes with: \"We would not send you somewhere we did not trust.\""
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "CTA button: \"See what Saverwell offers\" (Charlie green #3DAA68)",
                    "Tone: Personal, direct, warm recommendation",
                    "No corporate language or urgency tactics",
                ],
            },
        ],
    },
    # -- Email 2 ---------------------------------------------------------------
    {
        "heading": "Email 2: Discounts (Day 3)",
        "level": 3,
        "content": [
            {
                "type": "paragraph",
                "text": "**File:** charlie_migration_02_discounts.html",
            },
            {
                "type": "paragraph",
                "text": (
                    "Value showcase email. Stat cards: 1,900+ merchants, 125,000+ "
                    "locations, 75+ guides. Lists specific brands (Goodwill, Kohl's, "
                    "Walgreens, Denny's, T-Mobile, Amtrak). Zip code personalization."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "CTA button: \"Find Discounts Near You\" (Saverwell teal #2BBFB3)",
                    "Stat cards: 3-column layout",
                    "Zip code personalization in CTA link",
                ],
            },
        ],
    },
    # -- Email 3 ---------------------------------------------------------------
    {
        "heading": "Email 3: Protection (Day 6)",
        "level": 3,
        "content": [
            {
                "type": "paragraph",
                "text": "**File:** charlie_migration_03_protection.html",
            },
            {
                "type": "paragraph",
                "text": (
                    "Fraud protection angle. $3.4 billion lost to fraud by "
                    "Americans over 60. 4 guide preview cards. 29 total guides."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "CTA button: \"Read the Protection Guides\" (Saverwell teal #2BBFB3)",
                    "4 guide preview cards with white background",
                ],
            },
        ],
    },
    # -- Email 4 ---------------------------------------------------------------
    {
        "heading": "Email 4: Guides (Day 9)",
        "level": 3,
        "content": [
            {
                "type": "paragraph",
                "text": "**File:** charlie_migration_04_guides.html",
            },
            {
                "type": "paragraph",
                "text": (
                    "Medicare and money-saving guides. 75+ total, all free. "
                    "Two sections with specific guide titles."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "CTA button: \"Browse the Guide Library\" (Saverwell teal #2BBFB3)",
                    "Two sub-sections with bullet lists of specific guide titles",
                ],
            },
        ],
    },
    # -- Email 5 ---------------------------------------------------------------
    {
        "heading": "Email 5: Social Proof (Day 13)",
        "level": 3,
        "content": [
            {
                "type": "paragraph",
                "text": "**File:** charlie_migration_05_social_proof.html",
            },
            {
                "type": "paragraph",
                "text": (
                    "Social proof. Thousands of Charlie Saver members have made "
                    "the move. Three testimonial quotes. Stat cards."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "CTA button: \"Join Your Fellow Members\" (Saverwell teal #2BBFB3)",
                    "3 testimonial cards with green left border",
                    "Update with real conversion numbers before sending if available",
                ],
            },
        ],
    },
    # -- Email 6 ---------------------------------------------------------------
    {
        "heading": "Email 6: Farewell (Day 18)",
        "level": 3,
        "content": [
            {
                "type": "paragraph",
                "text": "**File:** charlie_migration_06_farewell.html",
            },
            {
                "type": "paragraph",
                "text": (
                    "Emotional farewell. \"This is the last email you will receive "
                    "from Charlie Saver.\" Thanks the community. Final value prop "
                    "recap. Auto-unsubscribe notice."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "CTA button: \"Continue Your Savings Journey\" (Charlie green #3DAA68 - bookend)",
                    "Tone: Sincere, grateful, final",
                    "Auto-unsubscribe notice at bottom",
                ],
            },
        ],
    },
    # -- Deliverable 3: Partner Config -----------------------------------------
    {
        "heading": "3. Partner Config Entry for Charlie Saver",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "**File:** data/saverwell/lovable_prompt_charlie_saver_partner.md"
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "Adds a charliesaver entry to the PARTNERS registry in the "
                    "Saverwell frontend. Includes Lovable instructions comment "
                    "preventing brand deviations. Also documents 8 live page "
                    "fixes needed in the next Lovable deploy."
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "Welcome overlay: \"Welcome, Charlie Saver Member\" heading",
                    "Co-branded header (Saverwell + Charlie Saver logos side by side)",
                    "GA4 events: partner_welcome_view, partner_welcome_skip, partner_welcome_subscribe",
                    "Customer.io attribution: brand=charliesaver on subscriber profiles",
                    "4 value props: Discounts, Fraud Protection, Expert Guides, Weekly Digest",
                    "Stats: 1,900+ Merchants, 125,000+ Locations, 75+ Guides and Alerts",
                    "CTA: \"Get Started Free\" (not \"Continue to Saverwell\")",
                ],
            },
        ],
    },
    # -- Deliverable 4: Interstitial -------------------------------------------
    {
        "heading": "4. CharleSaver.com Interstitial Page (Domain Pending)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "**Status:** Nice-to-have. Domain is being acquired. "
                    "Build only if/when domain is confirmed."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "**Primary landing experience (no domain required):** All email "
                    "CTAs link to saverwell.com?utm_campaign=CharlieSaver, which "
                    "triggers the partner welcome overlay via the existing partner "
                    "config system. This works today with zero domain dependency."
                ),
            },
        ],
    },
    # -- Deliverable 5: Setup Guide --------------------------------------------
    {
        "heading": "5. Campaign Setup Guide",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "**File:** data/saverwell/charlie_migration_setup_guide.md"
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "Comprehensive setup guide covering:"
                ),
            },
            {
                "type": "bullets",
                "items": [
                    "Narrative framework and copy rules",
                    "DNS setup for email.charlesaver.com sending domain",
                    "Pre-exclusion filters (spam, bounces, opt-outs, dupes)",
                    "4-segment creation with day-by-day timing diagram",
                    "2 campaigns: account holder intro + standard sequence",
                    "Email configuration for all 8 emails with A/B subject lines",
                    "UTM specification (utm_source=charliesaver)",
                    "Testing checklist (rendering, Liquid, links, content quality, CTA colors)",
                    "Launch sequence with gate checks after Day 1",
                    "Deliverability monitoring (daily checks, pause thresholds)",
                    "Progressive suppression via n8n (real-time, 3 new nodes)",
                    "Unsubscribe policy (separate lists, no cross-honor with SendGrid)",
                    "Footer and sending identity (Charlie Saver from-name, Charlie Financial footer)",
                    "Post-campaign handoff to SendGrid outbound plan",
                ],
            },
        ],
    },
    # -- Segmentation Strategy -------------------------------------------------
    {
        "heading": "Segmentation Strategy (4 Segments)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "~250K-300K total contacts. ~40K had banking accounts (20K "
                    "heavily communicated in Dec/Jan, 20K were not). The rest "
                    "(~210K-260K) entered their email on charlie.com but never "
                    "opened an account."
                ),
            },
            {
                "type": "table",
                "headers": ["Segment", "Size", "Sequence", "Start"],
                "rows": [
                    [
                        "A: Fatigued Account Holders",
                        "~20K",
                        "Custom 1a + 1b, then standard from Email 2",
                        "Day 0 (canary)",
                    ],
                    [
                        "B: Other Account Holders",
                        "~20K",
                        "All 6 standard emails",
                        "Day 1",
                    ],
                    [
                        "C: Interest-Only (bulk)",
                        "~210K-260K",
                        "All 6 standard emails (50K batches)",
                        "Days 2-5",
                    ],
                    [
                        "D: Saver + FraudWatch Subs",
                        "Small",
                        "All 6 standard emails",
                        "Day 0 (canary)",
                    ],
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "Gate check after Day 1: if open rate < 10% or bounce rate > 5% "
                    "on A + D, pause and investigate before activating B and C."
                ),
            },
        ],
    },
    # -- UTM Tagging -----------------------------------------------------------
    {
        "heading": "UTM Tagging",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["Parameter", "Value"],
                "rows": [
                    ["utm_source", "charliesaver"],
                    ["utm_medium", "email"],
                    ["utm_campaign", "CharlieSaver (triggers partner overlay)"],
                    ["utm_content", "email_{N}_{angle} (e.g., email_1_intro, email_1a_account_holder)"],
                    ["utm_zip", "{customer.zip_code} (if available)"],
                ],
            },
        ],
    },
    # -- Progressive Suppression -----------------------------------------------
    {
        "heading": "Progressive Suppression (Real-Time via n8n)",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Real-time suppression via the existing n8n subscribe workflow. "
                    "After the existing Customer.io Identify node, an IF node checks "
                    "if brand == \"charliesaver\". If true, an HTTP Request node "
                    "pushes converted_to_saverwell=true to Charlie's Customer.io "
                    "instance. This creates a suppression segment in Charlie's "
                    "Customer.io that excludes converted subscribers from remaining "
                    "migration emails within minutes."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "Three new n8n nodes: IF (brand check) -> HTTP Request (Charlie "
                    "CIO attribute push) -> No Op (rejoin main flow). Continue on "
                    "fail = true so suppression failure never breaks the subscribe path."
                ),
            },
        ],
    },
    # -- Unsubscribe Policy ----------------------------------------------------
    {
        "heading": "Unsubscribe Policy",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Separate lists. Charlie Saver migration unsubscribes are NOT "
                    "cross-honored on SendGrid outbound. The downstream SendGrid "
                    "emails include partner-specific offers (Medicare, insurance "
                    "referrals) beyond Saverwell's core product. CAN-SPAM compliance "
                    "is maintained because Charlie Saver (via Customer.io) and "
                    "Saverwell (via SendGrid) are different sender identities with "
                    "different domains."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "Charlie Saver unsubscribers go into a \"soft hold\" list in "
                    "the SendGrid plan - they enter later batches, not the first "
                    "wave, reducing spam complaint risk."
                ),
            },
        ],
    },
    # -- Sending Identity ------------------------------------------------------
    {
        "heading": "Sending Identity and DNS",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "From name: \"Charlie Saver\". From address: "
                    "noreply@email.charlesaver.com (after DNS setup). Footer: "
                    "\"Charlie Financial Inc.\" (legal sender, CAN-SPAM requirement). "
                    "Privacy link: charlesaver.com/privacy. Social icons: removed."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "DNS requirements: SPF record on charlesaver.com, DKIM record "
                    "(Customer.io provides key), CNAME for email.charlesaver.com. "
                    "Must be set up before first send."
                ),
            },
        ],
    },
    # -- Conversion Flow -------------------------------------------------------
    {
        "heading": "Conversion Flow",
        "level": 1,
        "content": [
            {
                "type": "numbered_list",
                "items": [
                    "Charlie Customer.io sends email from Charlie Saver",
                    "Subscriber clicks CTA",
                    "Lands on saverwell.com?utm_campaign=CharlieSaver",
                    "Partner welcome overlay appears (charliesaver config)",
                    "Subscribes via overlay form",
                    "Cloudflare Worker -> n8n webhook -> Saverwell Customer.io",
                    "Profile created with brand=charliesaver + all UTM params",
                    "n8n pushes converted_to_saverwell=true to Charlie's Customer.io (real-time suppression)",
                    "Enters Saverwell Welcome Flow (5 emails, co-branded header)",
                    "Then Protection Drip -> Expert Guides -> Medicare Guides",
                ],
            },
        ],
    },
    # -- Timeline --------------------------------------------------------------
    {
        "heading": "Timeline",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["When", "What"],
                "rows": [
                    [
                        "Pre-launch (Week 0)",
                        "DNS setup for email.charlesaver.com. Deploy partner config + Lovable fixes. Create all templates. Load into Customer.io. Create segments. Configure n8n suppression nodes. Test everything.",
                    ],
                    [
                        "Day 0",
                        "Seg A gets Email 1a, Seg D gets Email 1. Monitor deliverability.",
                    ],
                    [
                        "Days 1-5",
                        "Seg B gets Email 1 (Day 1). Seg C enters in 50K batches (Days 2-5). Gate check after Day 1.",
                    ],
                    [
                        "Days 6-12",
                        "Seg A merges into standard at Email 2 (Day 6). Emails 2-4 per schedule.",
                    ],
                    [
                        "Days 13-18",
                        "Email 5 (social proof) with real numbers. Email 6 (farewell). Campaign wraps.",
                    ],
                    [
                        "Day 23",
                        "Last Seg C batch finishes Email 6. Final metrics report. SendGrid handoff.",
                    ],
                ],
            },
        ],
    },
    # -- Key Metrics -----------------------------------------------------------
    {
        "heading": "Key Metrics",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["Metric", "Target"],
                "rows": [
                    ["Delivery rate", "> 97% (warm sender)"],
                    ["Open rate (Seg D)", "> 25%"],
                    ["Open rate (all segments)", "> 15%"],
                    ["Click rate", "> 3%"],
                    ["Saverwell signups", "10K-25K subscribers"],
                    ["Overall conversion rate", "> 4%"],
                    ["Spam complaint rate", "< 0.05%"],
                ],
            },
        ],
    },
    # -- Files Created ---------------------------------------------------------
    {
        "heading": "Files Created",
        "level": 1,
        "content": [
            {
                "type": "table",
                "headers": ["#", "File", "Purpose"],
                "rows": [
                    ["1", "layout_charlie_migration.html", "Full HTML email layout (no social icons, charlesaver.com privacy)"],
                    ["2", "charlie_migration_01_announcement.html", "Email 1: announcement"],
                    ["3", "charlie_migration_01a_account_holder.html", "Email 1a: account holder intro (fatigued segment)"],
                    ["4", "charlie_migration_01b_account_holder_value.html", "Email 1b: account holder value (fatigued segment)"],
                    ["5", "charlie_migration_02_discounts.html", "Email 2: discounts showcase"],
                    ["6", "charlie_migration_03_protection.html", "Email 3: fraud protection"],
                    ["7", "charlie_migration_04_guides.html", "Email 4: expert guides"],
                    ["8", "charlie_migration_05_social_proof.html", "Email 5: social proof"],
                    ["9", "charlie_migration_06_farewell.html", "Email 6: farewell"],
                    ["10", "lovable_prompt_charlie_saver_partner.md", "Lovable partner config + live page fixes"],
                    ["11", "charlie_migration_setup_guide.md", "Customer.io setup guide"],
                ],
            },
        ],
    },
    # -- Verification ----------------------------------------------------------
    {
        "heading": "Verification Checklist",
        "level": 1,
        "content": [
            {
                "type": "numbered_list",
                "items": [
                    "Open each of the 8 email bodies in browser - verify rendering, CTA colors, responsive layout",
                    "All CTA links contain utm_source=charliesaver (not charlie_migration)",
                    "All links point to charlesaver.com (not charlie.com) where applicable",
                    "No bare \"Charlie\" brand references (always \"Charlie Saver\" or \"Charlie Financial\")",
                    "Zero em dashes, en dashes, and mid-sentence bolding across all files",
                    "saverwell.com?utm_campaign=CharlieSaver triggers the partner welcome overlay",
                    "Partner overlay shows \"Welcome, Charlie Saver Member\" (not \"Welcome, Charlie Member\")",
                    "Partner overlay CTA says \"Get Started Free\" (not \"Continue to Saverwell\")",
                    "No social icons in layout template",
                    "Account holder Email 1a is ~150 words (significantly shorter than standard)",
                    "Account holder Email 1b has zip code personalization in heading and subject",
                    "Setup guide contains day-by-day timing diagram, n8n node specs, DNS requirements, and unsubscribe policy",
                ],
            },
        ],
    },
]


# -- Build helpers -------------------------------------------------------------
def heading_style(level: int) -> str:
    return f"HEADING_{min(level, 6)}"


def build_doc(docs_service: Any, drive_service: Any) -> str:
    """Create the Google Doc, populate it, share it. Returns the URL."""

    doc = docs_service.documents().create(body={"title": TITLE}).execute()
    doc_id = doc["documentId"]
    print(f"Created document: {doc_id}")

    requests: List[Dict[str, Any]] = []
    cursor = 1

    for section in SECTIONS:
        h = section.get("heading", "")
        lvl = section.get("level", 1)
        blocks = section.get("content", [])

        if h:
            htxt = h + "\n"
            requests.append(
                {"insertText": {"location": {"index": cursor}, "text": htxt}}
            )
            h_start, h_end = cursor, cursor + len(htxt)
            requests.append({
                "updateParagraphStyle": {
                    "range": {"startIndex": h_start, "endIndex": h_end},
                    "paragraphStyle": {
                        "namedStyleType": heading_style(lvl),
                        "spaceAbove": {
                            "magnitude": 14 if lvl == 1 else 10,
                            "unit": "PT",
                        },
                        "spaceBelow": {"magnitude": 4, "unit": "PT"},
                    },
                    "fields": "namedStyleType,spaceAbove,spaceBelow",
                }
            })
            cursor = h_end

        for block in blocks:
            btype = block.get("type", "paragraph")

            if btype == "paragraph":
                text = block["text"]
                para_text = text + "\n"
                plain, runs = parse_inline(para_text)
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": plain}}
                )
                p_start, p_end = cursor, cursor + len(plain)
                requests.append({
                    "updateParagraphStyle": {
                        "range": {"startIndex": p_start, "endIndex": p_end},
                        "paragraphStyle": {
                            "namedStyleType": "NORMAL_TEXT",
                            "spaceBelow": {"magnitude": 6, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceBelow",
                    }
                })
                for rs, re_, style in runs:
                    abs_s, abs_e = cursor + rs, cursor + re_
                    if style == "bold":
                        requests.append({
                            "updateTextStyle": {
                                "range": {"startIndex": abs_s, "endIndex": abs_e},
                                "textStyle": {"bold": True},
                                "fields": "bold",
                            }
                        })
                    elif style == "italic":
                        requests.append({
                            "updateTextStyle": {
                                "range": {"startIndex": abs_s, "endIndex": abs_e},
                                "textStyle": {"italic": True},
                                "fields": "italic",
                            }
                        })
                cursor = p_end

            elif btype == "bullets":
                items = block["items"]
                list_start = cursor
                for item in items:
                    itxt = str(item) + "\n"
                    plain_item, item_runs = parse_inline(itxt)
                    requests.append({
                        "insertText": {
                            "location": {"index": cursor},
                            "text": plain_item,
                        }
                    })
                    for rs, re_, style in item_runs:
                        abs_s, abs_e = cursor + rs, cursor + re_
                        if style == "bold":
                            requests.append({
                                "updateTextStyle": {
                                    "range": {
                                        "startIndex": abs_s,
                                        "endIndex": abs_e,
                                    },
                                    "textStyle": {"bold": True},
                                    "fields": "bold",
                                }
                            })
                        elif style == "italic":
                            requests.append({
                                "updateTextStyle": {
                                    "range": {
                                        "startIndex": abs_s,
                                        "endIndex": abs_e,
                                    },
                                    "textStyle": {"italic": True},
                                    "fields": "italic",
                                }
                            })
                    cursor += len(plain_item)
                requests.append({
                    "createParagraphBullets": {
                        "range": {"startIndex": list_start, "endIndex": cursor},
                        "bulletPreset": "BULLET_DISC_CIRCLE_SQUARE",
                    }
                })

            elif btype == "numbered_list":
                items = block["items"]
                list_start = cursor
                for item in items:
                    itxt = str(item) + "\n"
                    plain_item, item_runs = parse_inline(itxt)
                    requests.append({
                        "insertText": {
                            "location": {"index": cursor},
                            "text": plain_item,
                        }
                    })
                    for rs, re_, style in item_runs:
                        abs_s, abs_e = cursor + rs, cursor + re_
                        if style == "bold":
                            requests.append({
                                "updateTextStyle": {
                                    "range": {
                                        "startIndex": abs_s,
                                        "endIndex": abs_e,
                                    },
                                    "textStyle": {"bold": True},
                                    "fields": "bold",
                                }
                            })
                        elif style == "italic":
                            requests.append({
                                "updateTextStyle": {
                                    "range": {
                                        "startIndex": abs_s,
                                        "endIndex": abs_e,
                                    },
                                    "textStyle": {"italic": True},
                                    "fields": "italic",
                                }
                            })
                    cursor += len(plain_item)
                requests.append({
                    "createParagraphBullets": {
                        "range": {"startIndex": list_start, "endIndex": cursor},
                        "bulletPreset": "NUMBERED_DECIMAL_NESTED",
                    }
                })

            elif btype == "table":
                # Flush pending requests before table insertion
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []
                    time.sleep(0.3)
                    _ds = (
                        docs_service.documents().get(documentId=doc_id).execute()
                    )
                    _bc = _ds.get("body", {}).get("content", [])
                    if _bc:
                        cursor = _bc[-1].get("endIndex", cursor + 1) - 1

                headers = block["headers"]
                rows = block["rows"]
                num_cols = len(headers)
                num_rows = 1 + len(rows)

                requests.append({
                    "insertTable": {
                        "rows": num_rows,
                        "columns": num_cols,
                        "location": {"index": cursor},
                    }
                })

                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []
                    time.sleep(0.5)

                doc_state = (
                    docs_service.documents().get(documentId=doc_id).execute()
                )
                table_elem = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_elem = elem

                if table_elem:
                    table = table_elem["table"]
                    all_rows = [headers] + rows
                    cell_inserts: List[Tuple[int, str]] = []
                    for ri, row_data in enumerate(all_rows):
                        if ri >= len(table.get("tableRows", [])):
                            break
                        table_row = table["tableRows"][ri]
                        for ci, cell_val in enumerate(row_data):
                            if ci >= len(table_row.get("tableCells", [])):
                                break
                            cell = table_row["tableCells"][ci]
                            cell_content = cell.get("content", [])
                            if cell_content:
                                cell_idx = cell_content[0].get("startIndex", 0)
                                cell_inserts.append((cell_idx, str(cell_val)))

                    cell_inserts.sort(key=lambda x: x[0], reverse=True)
                    for cidx, ctext in cell_inserts:
                        requests.append({
                            "insertText": {
                                "location": {"index": cidx},
                                "text": ctext,
                            }
                        })

                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": requests}
                        ).execute()
                        requests = []
                        time.sleep(0.5)

                    # Bold header row
                    doc_state2 = (
                        docs_service.documents().get(documentId=doc_id).execute()
                    )
                    bold_requests: List[Dict[str, Any]] = []
                    for elem2 in doc_state2.get("body", {}).get("content", []):
                        if "table" in elem2:
                            t2 = elem2["table"]
                            if len(t2.get("tableRows", [])) > 0:
                                header_row = t2["tableRows"][0]
                                for hcell in header_row.get("tableCells", []):
                                    for para in hcell.get("content", []):
                                        for el in para.get("paragraph", {}).get(
                                            "elements", []
                                        ):
                                            si = el.get("startIndex", 0)
                                            ei = el.get("endIndex", 0)
                                            if ei > si:
                                                bold_requests.append({
                                                    "updateTextStyle": {
                                                        "range": {
                                                            "startIndex": si,
                                                            "endIndex": ei,
                                                        },
                                                        "textStyle": {"bold": True},
                                                        "fields": "bold",
                                                    }
                                                })
                    if bold_requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id, body={"requests": bold_requests}
                        ).execute()
                        time.sleep(0.5)

                doc_state3 = (
                    docs_service.documents().get(documentId=doc_id).execute()
                )
                body_content = doc_state3.get("body", {}).get("content", [])
                if body_content:
                    last = body_content[-1]
                    cursor = last.get("endIndex", cursor + 1) - 1

    # Flush remaining requests
    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()

    # Share + move to CMO Agent folder
    from cmo_agent.google_auth import (
        share_file_restricted,
        ensure_drive_folder,
        move_file_to_folder,
    )

    share_file_restricted(drive_service, doc_id)

    try:
        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)
    except Exception as e:
        print(f"Warning: could not move to folder: {e}")

    url = f"https://docs.google.com/document/d/{doc_id}/edit"
    return url


if __name__ == "__main__":
    print("Initializing Google services...")
    docs_svc, drive_svc = get_services()

    print("Building document...")
    doc_url = build_doc(docs_svc, drive_svc)

    print(f"\nDone! Document created:")
    print(doc_url)
