#!/usr/bin/env python3
"""Generate 21 Saverwell Protection draft articles and upsert to Supabase.

Usage:
    python scripts/generate_protection_content.py              # full run
    python scripts/generate_protection_content.py --dry-run    # generate + validate, skip upsert
    python scripts/generate_protection_content.py --resume     # load cached JSONs, skip regen
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
import structlog

# ── Project imports ──────────────────────────────────────────────────────────
# Ensure the project root is on sys.path so that cmo_agent is importable.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402, I001
from cmo_agent.content.protection import (  # noqa: E402
    PROOFREAD_FIELDS,
    ProtectionArticle,
    _JSON_SCHEMA,
    parse_article_json,
)

logger = structlog.get_logger()

# ── Paths ────────────────────────────────────────────────────────────────────
BRAND_VOICE_PATH = _PROJECT_ROOT / "data" / "brand_voices" / "saverwell.txt"
ARCHIVE_PATH = _PROJECT_ROOT / "data" / "saverwell" / "protection_article_archive.txt"
DRAFTS_DIR = _PROJECT_ROOT / "data" / "saverwell" / "protection_drafts"

# ── LLM settings ────────────────────────────────────────────────────────────
GENERATION_MODEL = "claude-sonnet-4-20250514"
SCANNING_MODEL = "claude-haiku-4-5-20251001"
GENERATION_TEMPERATURE = 0.4
GENERATION_MAX_TOKENS = 8192
MAX_RETRIES = 3
INTER_ARTICLE_PAUSE = 2.0  # seconds between articles

# ── Refinement settings ────────────────────────────────────────────────────
MAX_REFINEMENT_ITERATIONS = 2
QUALITY_THRESHOLD = 7  # out of 10

# ── Senior-lens keywords ────────────────────────────────────────────────────
SENIOR_KEYWORDS = {
    "medicare", "social security", "retirement", "grandchild", "fixed income",
    "pharmacy", "landline", "retiree", "senior", "older adult", "pension",
    "caregiver", "assisted living", "nursing home", "aarp",
}

ASK_FOR_HELP_KEYWORDS = {
    "family member", "caregiver", "bank branch", "official number",
    "someone you trust", "trusted friend", "trusted person",
}

# Trusted .gov domains for citation enforcement
GOV_CITATION_DOMAINS = {
    "ftc.gov", "ic3.gov", "ssa.gov", "irs.gov", "cms.gov",
    "consumerfinance.gov", "cisa.gov", "fbi.gov", "hhs.gov",
    "medicare.gov", "treasury.gov", "fdic.gov", "nist.gov",
}

MIN_CITATIONS = 2
MIN_GOV_CITATIONS = 1


# ── Topic Briefs ─────────────────────────────────────────────────────────────

@dataclass
class TopicBrief:
    """Defines a single article topic."""

    slug: str
    title: str
    category_slug: str
    category_id: int
    description: str
    senior_examples: List[str]
    source_urls: List[Dict[str, str]]  # [{label, url}]
    scam_type_tags: List[str]
    channel_tags: List[str]
    suggested_tags: List[str]


TOPIC_BRIEFS: List[TopicBrief] = [
    # ── Identity (6) ─────────────────────────────────────────────────────────
    TopicBrief(
        slug="protecting-your-social-security-number",
        title="Protecting Your Social Security Number",
        category_slug="identity",
        category_id=3,
        description="How to keep your SSN safe from identity thieves. Covers when you should and should not share it, how scammers steal SSNs, and step-by-step protection for retirees.",
        senior_examples=[
            "A retiree receives a call claiming to be from the Social Security Administration saying their number has been 'suspended' due to suspicious activity",
            "A senior gets a letter asking them to 'verify' their SSN to continue receiving benefits",
            "A grandparent's SSN is stolen from a medical form and used to open credit cards",
        ],
        source_urls=[
            {"label": "SSA Office of Inspector General", "url": "https://oig.ssa.gov/scam-awareness/"},
            {"label": "FTC Identity Theft", "url": "https://consumer.ftc.gov/features/identity-theft"},
            {"label": "IdentityTheft.gov", "url": "https://www.identitytheft.gov/"},
        ],
        scam_type_tags=["impersonation", "identity-theft", "government-impersonation"],
        channel_tags=["phone", "mail", "in-person"],
        suggested_tags=["social-security", "identity-theft", "ssn-protection", "government-impersonation", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="how-to-freeze-your-credit",
        title="How to Freeze Your Credit: A Step-by-Step Guide",
        category_slug="identity",
        category_id=3,
        description="Complete walkthrough for placing, lifting, and managing credit freezes at all three bureaus. Explains the difference between freezes and fraud alerts in plain language.",
        senior_examples=[
            "A retiree wants to freeze their credit after hearing about a data breach at their health insurance company",
            "A senior is confused about whether a credit freeze will stop them from using their existing credit cards",
            "A widow needs to freeze credit after discovering her late spouse's identity was being used fraudulently",
        ],
        source_urls=[
            {"label": "FTC Credit Freeze FAQ", "url": "https://consumer.ftc.gov/articles/what-know-about-credit-freezes-fraud-alerts"},
            {"label": "CFPB Credit Freeze Guide", "url": "https://www.consumerfinance.gov/ask-cfpb/what-do-i-do-if-i-think-i-have-been-a-victim-of-identity-theft-en-31/"},
            {"label": "AnnualCreditReport.com", "url": "https://www.annualcreditreport.com/"},
        ],
        scam_type_tags=["identity-theft"],
        channel_tags=["online", "phone"],
        suggested_tags=["credit-freeze", "credit-bureau", "identity-protection", "fraud-alert", "equifax", "experian", "transunion", "seniors"],
    ),
    TopicBrief(
        slug="medicare-identity-theft",
        title="Medicare Identity Theft: How to Protect Your Benefits",
        category_slug="identity",
        category_id=3,
        description="How scammers steal and misuse Medicare numbers, how to spot unauthorized claims, and step-by-step recovery. Covers Medicare Summary Notices and reporting to HHS OIG.",
        senior_examples=[
            "A retiree receives a Medicare Summary Notice for a medical device they never ordered",
            "A senior gets a call from someone claiming to be from Medicare asking them to 'confirm' their Medicare number for a new card",
            "A caregiver notices charges on a parent's Medicare account for a doctor visit in another state",
        ],
        source_urls=[
            {"label": "Medicare.gov Fraud Prevention", "url": "https://www.medicare.gov/basics/reporting-medicare-fraud-and-abuse"},
            {"label": "HHS OIG Fraud Reporting", "url": "https://oig.hhs.gov/fraud/report-fraud/"},
            {"label": "FTC Medicare Scams", "url": "https://consumer.ftc.gov/articles/medicare-scams"},
        ],
        scam_type_tags=["impersonation", "identity-theft", "healthcare-fraud"],
        channel_tags=["phone", "mail"],
        suggested_tags=["medicare", "healthcare-fraud", "identity-theft", "government-impersonation", "seniors", "benefits-fraud"],
    ),
    TopicBrief(
        slug="what-to-do-after-a-data-breach",
        title="What to Do After a Data Breach",
        category_slug="identity",
        category_id=3,
        description="Step-by-step response plan when you learn your information was exposed in a data breach. Covers notification letters, credit monitoring, and long-term protection.",
        senior_examples=[
            "A retiree receives a letter from their health insurance company saying their data was exposed in a breach",
            "A senior learns their pharmacy chain was hacked and names, addresses, and prescription history were stolen",
            "A grandparent's email provider was breached and their login credentials were exposed",
        ],
        source_urls=[
            {"label": "FTC Data Breach Response", "url": "https://consumer.ftc.gov/articles/what-do-if-youre-victim-data-breach"},
            {"label": "IdentityTheft.gov", "url": "https://www.identitytheft.gov/"},
            {"label": "FBI IC3", "url": "https://www.ic3.gov/"},
        ],
        scam_type_tags=["identity-theft", "data-breach"],
        channel_tags=["online", "mail"],
        suggested_tags=["data-breach", "identity-theft", "credit-monitoring", "fraud-prevention", "breach-response", "seniors"],
    ),
    TopicBrief(
        slug="tax-identity-theft",
        title="Tax Identity Theft: Protecting Your Tax Refund",
        category_slug="identity",
        category_id=3,
        description="How scammers file fake tax returns using stolen SSNs, IRS impersonation tactics, and step-by-step recovery. Covers IRS Identity Protection PINs.",
        senior_examples=[
            "A retiree files their tax return only to learn someone already filed using their Social Security number",
            "A senior receives a threatening phone call from someone claiming to be the IRS demanding immediate payment",
            "A widow's tax refund is stolen by someone who filed a fraudulent return in their spouse's name",
        ],
        source_urls=[
            {"label": "IRS Identity Theft Central", "url": "https://www.irs.gov/identity-theft-central"},
            {"label": "FTC Tax Identity Theft", "url": "https://consumer.ftc.gov/articles/what-know-about-tax-identity-theft"},
            {"label": "TIGTA Report Fraud", "url": "https://www.treasury.gov/tigta/"},
        ],
        scam_type_tags=["impersonation", "identity-theft", "government-impersonation"],
        channel_tags=["phone", "mail", "online"],
        suggested_tags=["tax-fraud", "irs-scam", "identity-theft", "tax-refund", "government-impersonation", "seniors"],
    ),
    TopicBrief(
        slug="reading-your-credit-report",
        title="Reading Your Credit Report: How to Spot Identity Theft",
        category_slug="identity",
        category_id=3,
        description="Plain-language guide to understanding your credit report, spotting accounts you did not open, and disputing errors. Covers free annual reports from all three bureaus.",
        senior_examples=[
            "A retiree checks their credit report for the first time and finds a credit card they never applied for",
            "A senior notices an address they have never lived at listed on their credit report",
            "A grandparent sees hard inquiries from companies they have never contacted",
        ],
        source_urls=[
            {"label": "CFPB Credit Reports", "url": "https://www.consumerfinance.gov/consumer-tools/credit-reports-and-scores/"},
            {"label": "AnnualCreditReport.com", "url": "https://www.annualcreditreport.com/"},
            {"label": "FTC Free Credit Reports", "url": "https://consumer.ftc.gov/articles/free-credit-reports"},
        ],
        scam_type_tags=["identity-theft"],
        channel_tags=["online", "mail"],
        suggested_tags=["credit-report", "identity-theft", "credit-bureau", "fraud-detection", "credit-monitoring", "seniors"],
    ),

    # ── Payments (6) ─────────────────────────────────────────────────────────
    TopicBrief(
        slug="gift-card-scams",
        title="Gift Card Scams: Why Scammers Want You to Pay with Gift Cards",
        category_slug="payments",
        category_id=4,
        description="Why scammers demand gift card payments, how the schemes work, and how to recognize the warning signs. Covers common scenarios targeting seniors.",
        senior_examples=[
            "A retiree receives a call from someone claiming to be from the IRS saying they owe back taxes and must pay with iTunes gift cards immediately",
            "A grandparent gets a call from a fake 'grandchild' begging them to buy gift cards for bail money",
            "A senior is told by a fake tech support agent that they need to pay a computer repair fee with Google Play gift cards",
        ],
        source_urls=[
            {"label": "FTC Gift Card Scams", "url": "https://consumer.ftc.gov/articles/gift-card-scams"},
            {"label": "AARP Gift Card Warning", "url": "https://www.aarp.org/money/scams-fraud/"},
        ],
        scam_type_tags=["impersonation", "gift-card-fraud", "government-impersonation"],
        channel_tags=["phone", "email", "in-person"],
        suggested_tags=["gift-cards", "payment-fraud", "phone-scams", "fraud-prevention", "seniors", "impersonation"],
    ),
    TopicBrief(
        slug="wire-transfer-fraud",
        title="Wire Transfer Fraud: Protecting Your Retirement Savings",
        category_slug="payments",
        category_id=4,
        description="How scammers trick seniors into wiring money from retirement accounts, why wire transfers are nearly impossible to reverse, and how to verify legitimate requests.",
        senior_examples=[
            "A retiree is convinced by a romance scammer to wire $15,000 from their savings to an overseas account",
            "A senior receives a call from someone posing as their bank saying they need to wire money to a 'safe' account due to suspected fraud",
            "A grandparent wires money to a fake attorney who claims their grandchild has been arrested",
        ],
        source_urls=[
            {"label": "FTC Wire Transfer Scams", "url": "https://consumer.ftc.gov/articles/sending-money"},
            {"label": "FBI IC3", "url": "https://www.ic3.gov/"},
            {"label": "CFPB Wire Transfer Info", "url": "https://www.consumerfinance.gov/"},
        ],
        scam_type_tags=["wire-fraud", "impersonation", "romance"],
        channel_tags=["phone", "online"],
        suggested_tags=["wire-transfer", "payment-fraud", "retirement-savings", "bank-fraud", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="charity-scams",
        title="Charity Scams: How to Spot Fake Charities",
        category_slug="payments",
        category_id=4,
        description="How to verify legitimate charities, recognize fake donation requests, and protect yourself from charity fraud. Covers disaster relief scams and look-alike organizations.",
        senior_examples=[
            "A retiree receives a phone call after a hurricane from a charity with a name similar to the Red Cross asking for a credit card donation",
            "A senior gets a door-to-door visitor asking for cash donations to a veterans charity they cannot verify",
            "A grandparent donates online to what looks like a real charity website but the URL is slightly misspelled",
        ],
        source_urls=[
            {"label": "FTC Charity Scams", "url": "https://consumer.ftc.gov/articles/before-giving-to-charity"},
            {"label": "BBB Wise Giving Alliance", "url": "https://www.give.org/"},
        ],
        scam_type_tags=["impersonation", "charity-fraud"],
        channel_tags=["phone", "online", "in-person", "mail"],
        suggested_tags=["charity-scams", "donation-fraud", "disaster-relief", "nonprofit-fraud", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="peer-to-peer-payment-scams",
        title="Peer-to-Peer Payment Scams: Staying Safe with Zelle, Venmo, and CashApp",
        category_slug="payments",
        category_id=4,
        description="Risks of peer-to-peer payment apps for seniors, common scam tactics, and how to use these tools safely. Covers the difference between fraud and authorized transfers.",
        senior_examples=[
            "A retiree sends money via Zelle to a Facebook Marketplace seller for furniture that never arrives",
            "A senior receives a text that looks like it is from their bank asking them to send a Zelle payment to 'verify' their account",
            "A grandparent sends money via Venmo to someone claiming to be a grandchild in need, but the request was from a scammer",
        ],
        source_urls=[
            {"label": "FTC P2P Payment Scams", "url": "https://consumer.ftc.gov/articles/using-peer-peer-payment-apps-and-services"},
            {"label": "CFPB Payment Apps", "url": "https://www.consumerfinance.gov/"},
            {"label": "Zelle Safety Tips", "url": "https://www.zellepay.com/pay-it-safe"},
        ],
        scam_type_tags=["payment-fraud", "impersonation", "phishing"],
        channel_tags=["online", "text", "phone"],
        suggested_tags=["zelle", "venmo", "cashapp", "p2p-payments", "payment-fraud", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="fake-check-overpayment-scams",
        title="Fake Check and Overpayment Scams",
        category_slug="payments",
        category_id=4,
        description="How overpayment scams work, why fake checks clear before bouncing, and how to protect yourself from losing money. Covers selling items online and work-from-home schemes.",
        senior_examples=[
            "A retiree sells furniture on Craigslist and receives a check for more than the asking price, with a request to wire the difference back",
            "A senior gets a check for a 'mystery shopper' job and is told to deposit it and wire part of the money to evaluate a wire transfer service",
            "A grandparent receives a check claiming to be sweepstakes winnings but is told to send money for taxes before the check clears",
        ],
        source_urls=[
            {"label": "FTC Fake Check Scams", "url": "https://consumer.ftc.gov/articles/how-spot-avoid-and-report-fake-check-scams"},
            {"label": "BBB Fake Check Warning", "url": "https://www.bbb.org/"},
            {"label": "FDIC Consumer Resources", "url": "https://www.fdic.gov/resources/consumers/"},
        ],
        scam_type_tags=["fake-check", "overpayment", "wire-fraud"],
        channel_tags=["mail", "online", "phone"],
        suggested_tags=["fake-checks", "overpayment", "payment-fraud", "wire-fraud", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="subscription-traps-unauthorized-charges",
        title="Subscription Traps and Unauthorized Charges",
        category_slug="payments",
        category_id=4,
        description="How free trial traps work, how to spot unauthorized recurring charges, and how to dispute charges with your bank or credit card company.",
        senior_examples=[
            "A retiree signs up for a 'free trial' of a supplement and is charged $89 per month without clear notice",
            "A senior notices a small recurring charge on their credit card statement from a company they do not recognize",
            "A grandparent clicks on an online ad for a free product sample and unknowingly agrees to monthly shipments and charges",
        ],
        source_urls=[
            {"label": "FTC Free Trial Offers", "url": "https://consumer.ftc.gov/articles/free-trial-offers"},
            {"label": "CFPB Billing Disputes", "url": "https://www.consumerfinance.gov/ask-cfpb/what-should-i-do-if-theres-an-unauthorized-charge-on-my-credit-card-en-35/"},
        ],
        scam_type_tags=["subscription-trap", "unauthorized-charge"],
        channel_tags=["online", "phone", "mail"],
        suggested_tags=["subscription-traps", "free-trial", "unauthorized-charges", "billing-dispute", "fraud-prevention", "seniors"],
    ),

    # ── Tech (6) ─────────────────────────────────────────────────────────────
    TopicBrief(
        slug="smartphone-security-for-seniors",
        title="Smartphone Security for Seniors",
        category_slug="tech",
        category_id=5,
        description="Essential phone security settings for older adults, including screen lock, app permissions, automatic updates, and recognizing suspicious text messages.",
        senior_examples=[
            "A retiree does not have a screen lock on their phone and it gets stolen at a doctor's office, giving the thief access to email and banking apps",
            "A senior accidentally installs a malicious app that sends premium text messages from their phone",
            "A grandparent clicks a link in a text message that installs spyware tracking their keystrokes and passwords",
        ],
        source_urls=[
            {"label": "FTC Mobile Phone Security", "url": "https://consumer.ftc.gov/articles/how-protect-your-phone"},
            {"label": "CISA Mobile Security Tips", "url": "https://www.cisa.gov/news-events/news/putting-mobile-device-security-your-everyday-routine"},
        ],
        scam_type_tags=["phishing", "malware", "smishing"],
        channel_tags=["text", "online"],
        suggested_tags=["smartphone-security", "mobile-safety", "app-permissions", "screen-lock", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="password-safety-guide",
        title="Password Safety: A Practical Guide for Older Adults",
        category_slug="tech",
        category_id=5,
        description="How to create strong passwords, why each account needs a unique password, and how password managers work in plain language.",
        senior_examples=[
            "A retiree uses the same password for their email, bank, and shopping accounts, and a data breach exposes all of them",
            "A senior writes their passwords on a sticky note attached to their computer monitor",
            "A grandparent cannot log in to their bank because they forgot which password they used",
        ],
        source_urls=[
            {"label": "CISA Password Tips", "url": "https://www.cisa.gov/secure-our-world/use-strong-passwords"},
            {"label": "FTC Password Security", "url": "https://consumer.ftc.gov/articles/creating-strong-passwords-and-other-ways-protect-your-accounts"},
            {"label": "NIST Password Guidelines", "url": "https://pages.nist.gov/800-63-4/sp800-63b.html"},
        ],
        scam_type_tags=["identity-theft", "data-breach"],
        channel_tags=["online"],
        suggested_tags=["passwords", "password-manager", "online-safety", "account-security", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="how-to-spot-fake-websites",
        title="How to Spot a Fake Website",
        category_slug="tech",
        category_id=5,
        description="Visual cues and URL tricks that reveal fake shopping, banking, and government websites. Covers HTTPS, domain spelling, and too-good-to-be-true deals.",
        senior_examples=[
            "A retiree searches for their bank online and clicks on a sponsored search result that leads to a look-alike phishing site",
            "A senior finds an unbelievable deal on a popular medication on a website that looks legitimate but has a slightly different URL",
            "A grandparent enters their credit card on a fake online store they found through a social media ad",
        ],
        source_urls=[
            {"label": "FTC Online Shopping Scams", "url": "https://consumer.ftc.gov/articles/online-shopping"},
            {"label": "FBI IC3 Spoofing", "url": "https://www.ic3.gov/"},
            {"label": "BBB Scam Tracker", "url": "https://www.bbb.org/scamtracker"},
        ],
        scam_type_tags=["phishing", "fake-website", "shopping-fraud"],
        channel_tags=["online"],
        suggested_tags=["fake-websites", "phishing", "url-spoofing", "online-safety", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="safe-online-shopping-tips",
        title="Safe Online Shopping Tips for Seniors",
        category_slug="tech",
        category_id=5,
        description="How to shop safely online, recognize legitimate retailers, use credit cards (not debit), and protect personal information during checkout.",
        senior_examples=[
            "A retiree buys holiday gifts from a social media ad and receives counterfeit products (or nothing at all)",
            "A senior uses their debit card for an online purchase and the card number is stolen, draining their checking account",
            "A grandparent enters their credit card on an unsecured website (no lock icon) and their information is intercepted",
        ],
        source_urls=[
            {"label": "FTC Online Shopping Safety", "url": "https://consumer.ftc.gov/articles/online-shopping"},
            {"label": "CFPB Debit vs Credit", "url": "https://www.consumerfinance.gov/"},
            {"label": "BBB Online Shopping", "url": "https://www.bbb.org/"},
        ],
        scam_type_tags=["shopping-fraud", "phishing"],
        channel_tags=["online"],
        suggested_tags=["online-shopping", "credit-card-safety", "debit-card-risk", "secure-checkout", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="two-factor-authentication-guide",
        title="Two-Factor Authentication: An Extra Lock on Your Accounts",
        category_slug="tech",
        category_id=5,
        description="Plain-language explanation of two-factor authentication (2FA), how to set it up on common accounts, and why it makes your accounts much harder to hack.",
        senior_examples=[
            "A retiree's email is hacked because they only had a password and no second verification step",
            "A senior does not understand what the 6-digit code texted to their phone is for when logging in to their bank",
            "A grandparent is nervous about 2FA because they worry about getting locked out of their accounts",
        ],
        source_urls=[
            {"label": "CISA Multi-Factor Auth", "url": "https://www.cisa.gov/secure-our-world/turn-on-multifactor-authentication"},
            {"label": "FTC Account Security", "url": "https://consumer.ftc.gov/articles/creating-strong-passwords-and-other-ways-protect-your-accounts"},
            {"label": "NIST Authentication Guide", "url": "https://pages.nist.gov/800-63-4/sp800-63b.html"},
        ],
        scam_type_tags=["identity-theft", "phishing"],
        channel_tags=["online"],
        suggested_tags=["two-factor-authentication", "2fa", "account-security", "online-safety", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="email-account-hacked",
        title="What to Do If Your Email Account Is Hacked",
        category_slug="tech",
        category_id=5,
        description="Step-by-step recovery when your email account is compromised. Covers password changes, account recovery, checking connected accounts, and preventing future hacks.",
        senior_examples=[
            "A retiree's email starts sending spam to everyone in their contacts list",
            "A senior cannot log in to their email because the password has been changed by someone else",
            "A grandparent's email is hacked and the scammer uses it to send money requests to their friends and family",
        ],
        source_urls=[
            {"label": "FTC Hacked Email", "url": "https://consumer.ftc.gov/articles/what-do-if-your-email-hacked"},
            {"label": "IdentityTheft.gov", "url": "https://www.identitytheft.gov/"},
            {"label": "CISA Account Security", "url": "https://www.cisa.gov/secure-our-world"},
        ],
        scam_type_tags=["identity-theft", "phishing", "account-takeover"],
        channel_tags=["online", "email"],
        suggested_tags=["email-hacked", "account-recovery", "password-security", "identity-theft", "fraud-prevention", "seniors"],
    ),

    # ── Fraud (3) ────────────────────────────────────────────────────────────
    TopicBrief(
        slug="account-takeover-prevention",
        title="Account Takeover: How to Protect Your Bank Login",
        category_slug="fraud",
        category_id=2,
        description="How criminals gain access to online banking accounts, warning signs of account takeover, and step-by-step protection for retirees.",
        senior_examples=[
            "A retiree receives a text alert for a login to their bank account from a device they do not recognize",
            "A senior's checking account is drained overnight after a phishing email captured their banking credentials",
            "A grandparent discovers unauthorized bill payments made through their online banking portal",
        ],
        source_urls=[
            {"label": "FTC Account Security", "url": "https://consumer.ftc.gov/articles/creating-strong-passwords-and-other-ways-protect-your-accounts"},
            {"label": "CFPB Banking Security", "url": "https://www.consumerfinance.gov/"},
            {"label": "FBI IC3", "url": "https://www.ic3.gov/"},
            {"label": "FDIC Consumer Protection", "url": "https://www.fdic.gov/resources/consumers/"},
        ],
        scam_type_tags=["account-takeover", "phishing", "identity-theft"],
        channel_tags=["online", "phone", "email"],
        suggested_tags=["account-takeover", "bank-fraud", "online-banking", "password-security", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="bank-impostor-calls",
        title="Bank Impostor Calls: When Scammers Pretend to Be Your Bank",
        category_slug="fraud",
        category_id=2,
        description="How caller ID spoofing makes fake bank calls look real, what your real bank will and will not ask, and what to do if you receive a suspicious call.",
        senior_examples=[
            "A retiree answers a call that shows their bank's real name on caller ID, but the caller asks them to 'confirm' their account number and PIN",
            "A senior is told their account has been compromised and they need to transfer money to a 'safe' temporary account",
            "A grandparent receives a call claiming to be the bank's fraud department asking them to read back a verification code that was just texted to them",
        ],
        source_urls=[
            {"label": "FTC Impersonation Scams", "url": "https://consumer.ftc.gov/articles/impersonator-scams"},
            {"label": "CFPB Avoiding Scams", "url": "https://www.consumerfinance.gov/"},
            {"label": "BBB Impersonation Scams", "url": "https://www.bbb.org/"},
            {"label": "FDIC Consumer Resources", "url": "https://www.fdic.gov/resources/consumers/"},
        ],
        scam_type_tags=["impersonation", "caller-id-spoofing", "bank-fraud"],
        channel_tags=["phone"],
        suggested_tags=["bank-impostor", "caller-id-spoofing", "phone-scams", "impersonation", "fraud-prevention", "seniors"],
    ),
    TopicBrief(
        slug="shared-verification-code-with-scammer",
        title="I Shared a Verification Code with a Scammer: What to Do Now",
        category_slug="fraud",
        category_id=2,
        description="Immediate recovery steps after sharing a 2FA or verification code with a scammer. Covers account lockdown, password changes, and monitoring for further compromise.",
        senior_examples=[
            "A retiree received a call from someone claiming to be their bank and read back the 6-digit code that was just texted to them",
            "A senior shared a Google verification code with a scammer who then gained access to their email and contacts",
            "A grandparent gave a code to someone claiming to be from Apple Support, who then locked them out of their own phone",
        ],
        source_urls=[
            {"label": "FTC Account Security", "url": "https://consumer.ftc.gov/articles/creating-strong-passwords-and-other-ways-protect-your-accounts"},
            {"label": "CISA Account Recovery", "url": "https://www.cisa.gov/secure-our-world"},
            {"label": "IdentityTheft.gov", "url": "https://www.identitytheft.gov/"},
        ],
        scam_type_tags=["phishing", "account-takeover", "impersonation"],
        channel_tags=["phone", "text"],
        suggested_tags=["verification-code", "2fa-scam", "account-recovery", "phone-scams", "fraud-prevention", "seniors"],
    ),
]


# ── System Prompt ────────────────────────────────────────────────────────────

def build_system_prompt(brand_voice: str, few_shot_examples: str) -> str:
    """Build the shared system prompt for article generation."""
    parts = [
        "You are a senior-safety content writer for Saverwell Protection.",
        "Your audience is adults aged 65+ who may have limited tech experience.",
        "",
        "BRAND VOICE:",
        brand_voice,
        "",
        "WRITING RULES:",
        "1. Write in a warm, supportive tone. Never be alarmist or patronizing.",
        "2. Use short sentences and simple vocabulary. Explain technical terms when used.",
        "3. Use 'seniors', 'retirees', or 'older adults'. NEVER use 'elderly' or 'old folks'.",
        "4. Avoid 'fraudsters' in body copy (reserve for headlines where tone earns it).",
        "5. Short paragraphs (2-3 sentences max). Bullet points for lists.",
        "6. No excessive emojis. No m-dashes. No bolding in the middle of sentences.",
        "",
        "ARTICLE FORMAT RULES:",
        "1. prevention_md MUST start with 'Before you act:' followed by at least 3 checklist items in format '- [ ] Step description'.",
        "2. Weave at least 2 senior-relevant examples into body_md (medicare, social security, retirement, grandchild, fixed income, etc.).",
        "3. Include one 'Ask for help' suggestion (family member, caregiver, bank branch, official number, or 'someone you trust').",
        "4. phone_script_md: Write word-for-word scripts an older adult could read aloud. Assume phone/in-person preference.",
        "5. resources_md MUST include reportfraud.ftc.gov AND IdentityTheft.gov as bullet items.",
        "6. Use ONLY the source URLs provided in the topic brief. Do NOT invent or hallucinate URLs.",
        "7. Reference sources inline in body_md where claiming a statistic or fact.",
        "8. email_subject must be <= 45 characters. email_preheader must be <= 90 characters.",
        "9. email_cta_url MUST be '/protection/article/<slug>' where <slug> matches the slug field.",
        "10. email_cta_label MUST be exactly 'Read full guide'.",
        "11. intent_tags MUST include at least one of: awareness, prevention, urgent_help.",
        "12. tags must have 3-8 lowercase items.",
        "13. slug must be lowercase-hyphenated (a-z, 0-9, hyphens only).",
        "14. reading_minutes should be 4-7 depending on article depth.",
        "",
        f"OUTPUT FORMAT: Return ONLY a JSON object matching this schema:\n{_JSON_SCHEMA}",
        "",
        "Return bare JSON only. No markdown code blocks. No extra text before or after.",
    ]

    if few_shot_examples:
        parts.append(
            f"\nPAST PROTECTION ARTICLES (match this structure and tone):\n{few_shot_examples}"
        )

    return "\n".join(parts)


def build_user_prompt(topic: TopicBrief) -> str:
    """Build the per-topic user prompt."""
    source_list = "\n".join(
        f"- {s['label']}: {s['url']}" for s in topic.source_urls
    )
    examples_list = "\n".join(f"- {ex}" for ex in topic.senior_examples)

    return f"""Write a Saverwell Protection article for the following topic:

TITLE: {topic.title}
SLUG: {topic.slug}
CATEGORY: {topic.category_slug}
DESCRIPTION: {topic.description}

SENIOR-RELEVANT EXAMPLES (weave at least 2 into the article):
{examples_list}

AUTHORITATIVE SOURCES (use ONLY these URLs — do not invent others):
{source_list}

SCAM TYPE TAGS to include: {', '.join(topic.scam_type_tags)}
CHANNEL TAGS to include: {', '.join(topic.channel_tags)}
SUGGESTED TAGS: {', '.join(topic.suggested_tags)}

Remember:
- prevention_md starts with "Before you act:" and has at least 3 "- [ ]" checklist items
- Include one "Ask for help" suggestion
- resources_md must include reportfraud.ftc.gov and IdentityTheft.gov
- email_cta_url must be "/protection/article/{topic.slug}"
- Return bare JSON only"""


# ── Validation ───────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    """Result of senior-lens validation."""

    passed: bool
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)


def validate_senior_lens(article: ProtectionArticle, topic: TopicBrief) -> ValidationResult:
    """Custom senior-lens validation beyond Pydantic."""
    warnings: List[str] = []
    errors: List[str] = []

    # Check "Before you act" in prevention_md
    if "before you act" not in article.prevention_md.lower():
        errors.append("prevention_md missing 'Before you act:' heading")

    # Check at least 3 checkboxes in prevention_md
    checkbox_count = article.prevention_md.count("- [")
    if checkbox_count < 3:
        errors.append(f"prevention_md has {checkbox_count} checkboxes, need at least 3")

    # Check senior-relevant keywords in body
    body_lower = article.body_md.lower()
    found_keywords = [kw for kw in SENIOR_KEYWORDS if kw in body_lower]
    if len(found_keywords) < 2:
        errors.append(f"body_md has {len(found_keywords)} senior keywords, need at least 2")

    # Check "ask for help" suggestion
    full_text = (
        article.body_md + article.what_to_do_md + article.prevention_md + article.phone_script_md
    ).lower()
    has_help = any(kw in full_text for kw in ASK_FOR_HELP_KEYWORDS)
    if not has_help:
        warnings.append("Missing 'ask for help' suggestion (family member, caregiver, etc.)")

    # Check required resources
    resources_lower = article.resources_md.lower()
    if "reportfraud.ftc.gov" not in resources_lower:
        errors.append("resources_md missing reportfraud.ftc.gov")
    if "identitytheft.gov" not in resources_lower:
        errors.append("resources_md missing IdentityTheft.gov")

    # Check no legal advice language
    legal_phrases = ["not legal advice", "consult an attorney", "this is not legal"]
    for phrase in legal_phrases:
        if phrase in full_text:
            warnings.append(f"Contains legal advice caveat: '{phrase}'")

    # Check slug matches topic
    if article.slug != topic.slug:
        errors.append(f"Slug mismatch: got '{article.slug}', expected '{topic.slug}'")

    # Check category matches topic
    if article.category_slug != topic.category_slug:
        errors.append(
            f"Category mismatch: got '{article.category_slug}', expected '{topic.category_slug}'"
        )

    # Citation enforcement: at least MIN_CITATIONS sources, at least MIN_GOV_CITATIONS .gov
    source_urls = [s["url"] for s in topic.source_urls]
    if len(source_urls) < MIN_CITATIONS:
        errors.append(
            f"Topic has {len(source_urls)} citations, need at least {MIN_CITATIONS}"
        )
    gov_count = sum(
        1 for url in source_urls
        if any(domain in url for domain in GOV_CITATION_DOMAINS)
    )
    if gov_count < MIN_GOV_CITATIONS:
        errors.append(
            f"Topic has {gov_count} .gov citations, need at least {MIN_GOV_CITATIONS}"
        )

    passed = len(errors) == 0
    return ValidationResult(passed=passed, warnings=warnings, errors=errors)


# ── Refinement ───────────────────────────────────────────────────────────────

async def refine_article(
    client: "anthropic.AsyncAnthropic",
    article: ProtectionArticle,
    brand_voice: str,
) -> Tuple[ProtectionArticle, int]:
    """Quality refinement loop. Returns (article, refinement_score)."""
    import anthropic as _anthropic  # avoid top-level import collision

    last_score = 10  # assume good until proven otherwise

    for i in range(MAX_REFINEMENT_ITERATIONS):
        article_json = article.model_dump_json(indent=2)
        critique_prompt = f"""Rate this Saverwell Protection article on a scale of 1-10.

BRAND VOICE TO MATCH:
{brand_voice[:500]}

ARTICLE JSON:
{article_json[:4000]}

Score each criterion (1-10):
1. Brand voice alignment (calm, supportive tone for seniors)
2. Clarity and readability for older adults (65+)
3. Completeness of all sections (overview, red flags, what to do, prevention, phone script, resources)
4. Senior-lens compliance (senior examples woven in, help suggestions present, no patronizing language)
5. Sources referenced in body text (inline citations where claiming facts)

Return ONLY a JSON object: {{"brand_voice": N, "clarity": N, "completeness": N, "senior_lens": N, "sources": N, "overall": N, "feedback": "..."}}"""

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
            revise_prompt = f"""Revise this Protection article based on the critique.

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

            revised = parse_article_json(revise_resp.content[0].text)
            if isinstance(revised, ProtectionArticle):
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
    article: ProtectionArticle,
    settings: Settings,
) -> Tuple[ProtectionArticle, int]:
    """Proofread article fields via Haiku. Returns (article, correction_count)."""
    from cmo_agent.llm.anthropic import AnthropicLLM
    from cmo_agent.text.proofreader import Proofreader

    scanning_llm = AnthropicLLM(
        api_key=settings.anthropic_api_key,
        model=SCANNING_MODEL,
        max_tokens=4096,
        temperature=0.1,
    )
    proofreader = Proofreader(scanning_llm)

    article_dict = article.model_dump()
    corrected, corrections = await proofreader.proofread_dict_fields(
        article_dict,
        PROOFREAD_FIELDS,
        preserve_terms=[
            "Saverwell", "FTC", "IdentityTheft.gov", "Medicare",
            "Social Security", "CFPB", "AARP", "Equifax", "Experian",
            "TransUnion", "FDIC", "CISA", "FBI", "IC3", "IRS",
            "Zelle", "Venmo", "CashApp", "AnnualCreditReport.com",
        ],
    )
    if corrections:
        try:
            article = ProtectionArticle(**corrected)
            logger.info("proofread_corrections", count=len(corrections))
        except Exception as e:
            # Proofreader may expand text beyond length limits (e.g. email_subject > 45 chars).
            # Fall back to the pre-proofread article rather than crashing.
            logger.warning(
                "proofread_validation_failed_using_original",
                error=str(e),
                corrections_attempted=len(corrections),
            )
            corrections = []  # report 0 since we discarded them

    return article, len(corrections)


# ── Source URL verification ──────────────────────────────────────────────────

async def verify_source_urls(topics: List[TopicBrief]) -> Dict[str, str]:
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

def append_to_archive(article: ProtectionArticle) -> None:
    """Append a completed article to the protection archive file."""
    ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not ARCHIVE_PATH.exists():
        ARCHIVE_PATH.write_text(
            "# Saverwell Protection Article Archive\n"
            "# Converted from FraudWatch newsletters. Used as few-shot examples.\n"
        )
    entry = (
        f"\n---\n\n### {article.slug}\n"
        f"Status: Completed\n"
        f"Title: {article.title}\n"
        f"Category: {article.category_slug}\n"
        f"Tags: {', '.join(article.tags)}\n\n"
        f"## Overview\n{article.overview_md}\n\n"
        f"## Red Flags\n{article.red_flags_md}\n\n"
        f"## What to Do\n{article.what_to_do_md}\n\n"
        f"## Prevention Checklist\n{article.prevention_md}\n\n"
        f"## Phone Script\n{article.phone_script_md}\n\n"
        f"## Resources\n{article.resources_md}\n"
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
    if (
        validation.passed
        and not validation.warnings
        and refinement_score >= 8
    ):
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
    topic: TopicBrief,
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
    """Fetch existing article slugs from Supabase."""
    async with httpx.AsyncClient(timeout=10.0) as http:
        resp = await http.get(
            f"{settings.supabase_url}/rest/v1/protection_articles?select=slug",
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
    """Upsert a single article to Supabase. Returns True on success."""
    async with httpx.AsyncClient(timeout=15.0) as http:
        resp = await http.post(
            f"{settings.supabase_url}/rest/v1/protection_articles",
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
    article: ProtectionArticle,
    topic: TopicBrief,
    review_score: int,
    review_notes: str,
) -> Dict[str, Any]:
    """Build the Supabase row payload from an article and topic brief."""
    data = article.model_dump()

    # Map to Supabase columns
    payload: Dict[str, Any] = {
        "slug": data["slug"],
        "title": data["title"],
        "subtitle": data["subtitle"],
        # NOTE: category_slug column does NOT exist in Supabase table — omitted
        "category_id": topic.category_id,
        "tags": data["tags"],
        "channel_tags": data["channel_tags"],
        "scam_type_tags": data["scam_type_tags"],
        "intent_tags": data["intent_tags"],
        "reading_minutes": data["reading_minutes"],
        "overview_md": data["overview_md"],
        "red_flags_md": data["red_flags_md"],
        "what_to_do_md": data["what_to_do_md"],
        "prevention_md": data["prevention_md"],
        "phone_script_md": data["phone_script_md"],
        "resources_md": data["resources_md"],
        "body_md": data["body_md"],
        "email_subject": data["email_subject"],
        "email_preheader": data["email_preheader"],
        "email_intro_md": data["email_intro_md"],
        "email_cta_label": data["email_cta_label"],
        "email_cta_url": data["email_cta_url"],
        # Metadata
        "status": "draft",
        "publish_web": False,
        "publish_email": False,
        "source": "scanner_seed",
        "source_name": "generate_protection_content.py",
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
    topic: TopicBrief,
    system_prompt: str,
    settings: Settings,
    url_results: Dict[str, str],
) -> Optional[Dict[str, Any]]:
    """Generate, validate, refine, proofread, and return a Supabase payload."""
    user_prompt = build_user_prompt(topic)

    article: Optional[ProtectionArticle] = None
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
            parsed = parse_article_json(raw_text)

            if isinstance(parsed, dict) and "error" in parsed:
                logger.warning(
                    "parse_failed", slug=topic.slug, attempt=attempt, error=parsed["error"]
                )
                continue

            article = parsed  # type: ignore[assignment]

            # Senior-lens validation
            last_validation = validate_senior_lens(article, topic)
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
                await asyncio.sleep(2 ** attempt)
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
        last_validation = validate_senior_lens(article, topic)

    review_score = compute_review_score(
        last_validation, refinement_score, proofread_count, attempt
    )
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

async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Saverwell Protection articles")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate and validate, but skip Supabase upsert",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Load cached JSONs from data/saverwell/protection_drafts/ instead of regenerating",
    )
    args = parser.parse_args()

    settings = Settings()

    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)

    if not args.dry_run and (not settings.supabase_url or not settings.supabase_service_role_key):
        print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY required (or use --dry-run)")
        sys.exit(1)

    # Load brand voice and few-shot examples
    brand_voice = BRAND_VOICE_PATH.read_text()
    few_shot = load_few_shot_examples(max_articles=2)
    system_prompt = build_system_prompt(brand_voice, few_shot)

    # Fetch existing slugs from Supabase (unless dry-run with no Supabase)
    existing_slugs: set = set()
    if not args.dry_run:
        try:
            existing_slugs = await fetch_existing_slugs(settings)
            print(f"Found {len(existing_slugs)} existing articles in Supabase")
        except Exception as e:
            print(f"WARNING: Could not fetch existing slugs: {e}")

    # Determine which topics need generation
    topics_to_generate: List[TopicBrief] = []
    topics_to_skip: List[str] = []
    cached_payloads: Dict[str, Dict[str, Any]] = {}

    for topic in TOPIC_BRIEFS:
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
    url_results = await verify_source_urls(TOPIC_BRIEFS)
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
        print(f"\nUpserting {len(all_payloads)} articles to Supabase...")
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
    cat_counts: Dict[str, Dict[str, int]] = {
        "identity": {"inserted": 0, "existing": 0},
        "payments": {"inserted": 0, "existing": 0},
        "tech": {"inserted": 0, "existing": 0},
        "fraud": {"inserted": 0, "existing": 0},
        "scams": {"inserted": 0, "existing": 0},
    }

    # Count existing by category (from topic briefs for skipped)
    topic_map = {t.slug: t for t in TOPIC_BRIEFS}
    for slug in topics_to_skip:
        topic = topic_map.get(slug)
        if topic:
            cat_counts[topic.category_slug]["existing"] += 1

    for slug, _ in inserted_slugs:
        topic = topic_map.get(slug)
        if topic:
            cat_counts[topic.category_slug]["inserted"] += 1

    # Base existing counts (from the plan)
    base_existing = {"scams": 7, "fraud": 1, "identity": 0, "payments": 0, "tech": 0}

    print("\n" + "=" * 50)
    print("COMPLETION REPORT")
    print("=" * 50)
    print(f"Generated:  {len(generated_payloads)}")
    print(f"From cache: {len(cached_payloads)}")
    total_inserted = len(inserted_slugs)
    print(f"Inserted:   {total_inserted}" + (" (dry-run)" if args.dry_run else ""))
    print(f"Failed:     {len(failed_slugs) + len(upsert_failed)}")
    print(f"Skipped:    {len(topics_to_skip)} (already existed)")

    print("\nPer category:")
    for cat in ["identity", "payments", "tech", "fraud", "scams"]:
        ins = cat_counts[cat]["inserted"]
        base = base_existing.get(cat, 0) + cat_counts[cat]["existing"]
        total = base + ins
        print(f"  {cat:10s}: {ins} inserted ({total} total)")

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


if __name__ == "__main__":
    asyncio.run(main())
