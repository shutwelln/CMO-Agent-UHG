"""Generate Saverwell Welcome Campaign assets for Customer.io.

Produces:
1. 5 responsive HTML email templates with Liquid variables
2. Customer.io setup guide (segments, campaign journey, configuration)

Customer.io campaigns/segments cannot be created via API - they require UI work.
These templates are designed to be pasted into Customer.io's email editor (Code view).

Usage:
    python scripts/create_welcome_campaign.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

TEMPLATE_DIR = project_root / "data" / "saverwell" / "email_templates"
GUIDE_PATH = project_root / "data" / "saverwell" / "customerio_setup_guide.md"

# Brand colors (Saverwell brand guide)
TEAL = "#2A9D8F"  # Primary: CTAs, links, emphasis
TEAL_DARK = "#228176"  # CTA button border
SLATE = "#3D4F5F"  # Text, headings
SLATE_LIGHT = "#6B7B8D"  # Secondary text (tagline, captions)
SLATE_LIGHTER = "#8A96A3"  # Footer text
BG_WARM = "#ffffff"  # White background (logo is not transparent)
BG_WHITE = "#ffffff"  # Card/content areas
BORDER = "#E8EAEC"  # Warm border

# Legacy aliases used in template strings
GREEN = TEAL
GREEN_DARK = TEAL_DARK
BG_LIGHT = BG_WARM
TEXT_DARK = SLATE
TEXT_MED = SLATE_LIGHT
TEXT_LIGHT = SLATE_LIGHTER

LOGO_URL = "https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/Saverwell/saverwell-logo.png"

# ───────────────────────────────────────────────────────────────────
# Base email wrapper (inline CSS for email clients)
# ───────────────────────────────────────────────────────────────────


def wrap_email(preheader: str, body_html: str, subject_comment: str = "") -> str:
    """Wrap body content in the Saverwell responsive email base template."""
    comment = f"<!-- Subject: {subject_comment} -->\n" if subject_comment else ""
    return f"""{comment}<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <title>Saverwell</title>
  <!--[if mso]>
  <style type="text/css">
    table {{border-collapse: collapse; border: 0; border-spacing: 0; margin: 0;}}
    div, td {{padding: 0;}}
    div {{margin: 0 !important;}}
  </style>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <![endif]-->
  <style type="text/css">
    body {{ margin: 0; padding: 0; -webkit-text-size-adjust: 100%; -ms-text-size-adjust: 100%; }}
    table {{ border-collapse: collapse; mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
    img {{ border: 0; line-height: 100%; outline: none; text-decoration: none; -ms-interpolation-mode: bicubic; }}
    a {{ color: {GREEN}; text-decoration: underline; }}
    @media only screen and (max-width: 620px) {{
      .email-container {{ width: 100% !important; max-width: 100% !important; }}
      .fluid {{ max-width: 100% !important; height: auto !important; }}
      .stack-column {{ display: block !important; width: 100% !important; max-width: 100% !important; }}
      .mobile-pad {{ padding-left: 20px !important; padding-right: 20px !important; }}
    }}
  </style>
</head>
<body style="margin: 0; padding: 0; background-color: {BG_LIGHT}; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif;">
  <!-- Preheader (hidden preview text) -->
  <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">
    {preheader}
  </div>
  <!-- Prevent Gmail from using preheader as snippet -->
  <div style="display: none; max-height: 0; overflow: hidden; mso-hide: all;">
    &nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;&nbsp;&zwnj;
  </div>

  <center style="width: 100%; background-color: {BG_LIGHT};">
    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" align="center" class="email-container" style="margin: auto; background-color: {BG_WHITE};">

      <!-- LOGO HEADER -->
      <tr>
        <td style="padding: 32px 40px 16px; text-align: center;" class="mobile-pad">
          <img src="{LOGO_URL}" alt="Saverwell" width="180" style="display: block; margin: 0 auto; max-width: 180px; height: auto;">
          <br>
          <span style="font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 13px; color: {TEXT_MED};">Save more. Stay protected.</span>
        </td>
      </tr>

      <!-- DIVIDER -->
      <tr>
        <td style="padding: 0 40px;" class="mobile-pad">
          <hr style="border: none; border-top: 2px solid {GREEN}; margin: 0;">
        </td>
      </tr>

      <!-- BODY CONTENT -->
      <tr>
        <td style="padding: 24px 40px 32px; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 16px; line-height: 1.65; color: {TEXT_DARK};" class="mobile-pad">
{body_html}
        </td>
      </tr>

      <!-- FOOTER -->
      <tr>
        <td style="padding: 24px 40px; background-color: #f9f9f9; border-top: 1px solid {BORDER}; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 13px; color: {TEXT_LIGHT}; text-align: center;" class="mobile-pad">
          <p style="margin: 0 0 8px;">Saverwell - Save more. Stay protected.</p>
          <p style="margin: 0 0 8px;">
            <a href="{{{{ unsubscribe_url }}}}" style="color: {TEXT_MED}; text-decoration: underline;">Manage your email preferences</a>
            &nbsp;|&nbsp;
            <a href="{{{{ unsubscribe_url }}}}" style="color: {TEXT_MED}; text-decoration: underline;">Unsubscribe from all</a>
          </p>
          <p style="margin: 0;">Saverwell Holdings, LLC</p>
        </td>
      </tr>

    </table>
  </center>
</body>
</html>"""


def make_cta_button(label: str, url: str) -> str:
    """Generate an email-safe CTA button (table-based for Outlook compat)."""
    return f"""
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" align="center" style="margin: 0 auto;">
            <tr>
              <td style="border-radius: 6px; background-color: {GREEN};">
                <a href="{url}" target="_blank" style="display: inline-block; background-color: {GREEN}; color: #ffffff; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 16px; font-weight: bold; padding: 14px 32px; text-decoration: none; border-radius: 6px; border: 1px solid {GREEN_DARK};">
                  {label}
                </a>
              </td>
            </tr>
          </table>"""


def make_bullet_list(items: list) -> str:
    """Generate a styled bullet list for emails."""
    rows = ""
    for item in items:
        rows += f"""
            <tr>
              <td valign="top" style="padding: 0 8px 8px 0; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 16px; color: {GREEN}; line-height: 1.65;">&bull;</td>
              <td valign="top" style="padding: 0 0 8px; font-family: 'Manrope', system-ui, -apple-system, 'Segoe UI', sans-serif; font-size: 16px; color: {TEXT_DARK}; line-height: 1.65;">{item}</td>
            </tr>"""
    return f"""
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%">
            {rows}
          </table>"""


# ───────────────────────────────────────────────────────────────────
# Email 1: Day 0 - Welcome + Discounts
# ───────────────────────────────────────────────────────────────────

WELCOME_1_SUBJECT = "Welcome to Saverwell - Savings and Protection for Seniors"
WELCOME_1_PREHEADER = "Discounts near you, fraud protection tips, and Medicare guides - all free."


def build_welcome_1() -> str:
    body = f"""
          <p style="margin: 0 0 16px; font-size: 20px; font-weight: bold; color: {GREEN};">
            Welcome to Saverwell{{% if customer.first_name %}}, {{{{ customer.first_name }}}}{{% endif %}}
          </p>

          <p style="margin: 0 0 16px;">
            You just joined thousands of seniors who are saving more and staying protected from financial threats. Here is what you can expect from us:
          </p>

{
        make_bullet_list(
            [
                "Discounts and deals near your zip code, updated regularly",
                "Fraud protection tips to keep your money safe",
                "Medicare guides to help you make smarter decisions about your coverage",
                "A weekly digest with the best finds, delivered to your inbox",
            ]
        )
    }

          <p style="margin: 16px 0 24px;">
            Start by exploring the discounts available{{% if customer.zip_code %}} near {{{{ customer.zip_code }}}}{{% endif %}}. You have earned these savings.
          </p>

{
        make_cta_button(
            "Explore Discounts Near You",
            "https://saverwell.com/discounts{% if customer.zip_code %}?zip={{ customer.zip_code }}{% endif %}",
        )
    }

          <p style="margin: 24px 0 0; font-size: 14px; color: {TEXT_MED};">
            Reply to this email anytime if you have questions. We read every message.
          </p>"""

    return wrap_email(WELCOME_1_PREHEADER, body, WELCOME_1_SUBJECT)


# ───────────────────────────────────────────────────────────────────
# Email 2: Day 3 - Hidden Discounts
# ───────────────────────────────────────────────────────────────────

WELCOME_2_SUBJECT = "3 Discounts Most Seniors Don't Know About"
WELCOME_2_PREHEADER = "These under-the-radar savings are hiding in plain sight."


def build_welcome_2() -> str:
    body = f"""
          <p style="margin: 0 0 16px; font-size: 20px; font-weight: bold; color: {GREEN};">
            Savings hiding in plain sight
          </p>

          <p style="margin: 0 0 16px;">
            Did you know that many retailers, restaurants, and service providers offer senior discounts, but they rarely advertise them? You usually have to ask. Here are three that surprise people the most:
          </p>

          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 0 0 16px;">
            <tr>
              <td style="padding: 16px; background-color: #f0f7f1; border-radius: 6px; border-left: 4px solid {GREEN};">
                <p style="margin: 0 0 4px; font-weight: bold; color: {GREEN}; font-size: 16px;">1. Grocery store discount days</p>
                <p style="margin: 0; font-size: 15px; color: {TEXT_DARK};">Many grocery chains offer 5-10% off on specific weekdays for customers 60 and older. Check with your local store for their senior discount schedule.</p>
              </td>
            </tr>
          </table>

          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 0 0 16px;">
            <tr>
              <td style="padding: 16px; background-color: #f0f7f1; border-radius: 6px; border-left: 4px solid {GREEN};">
                <p style="margin: 0 0 4px; font-weight: bold; color: {GREEN}; font-size: 16px;">2. Cell phone carrier plans</p>
                <p style="margin: 0; font-size: 15px; color: {TEXT_DARK};">T-Mobile, AT&T, and other carriers have plans specifically for 55+ customers. These plans can save $20-40 per month compared to standard rates.</p>
              </td>
            </tr>
          </table>

          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 0 0 16px;">
            <tr>
              <td style="padding: 16px; background-color: #f0f7f1; border-radius: 6px; border-left: 4px solid {GREEN};">
                <p style="margin: 0 0 4px; font-weight: bold; color: {GREEN}; font-size: 16px;">3. Property tax exemptions</p>
                <p style="margin: 0; font-size: 15px; color: {TEXT_DARK};">Most states offer property tax reductions for seniors. Some freeze your rate so it never goes up. Contact your county assessor's office to see what you qualify for.</p>
              </td>
            </tr>
          </table>

          <p style="margin: 0 0 24px;">
            We track hundreds of senior discounts across the country. Browse the full list to see what is available near you.
          </p>

{make_cta_button("Browse All Discounts", "https://saverwell.com/discounts")}"""

    return wrap_email(WELCOME_2_PREHEADER, body, WELCOME_2_SUBJECT)


# ───────────────────────────────────────────────────────────────────
# Email 3: Day 6 - Protection Spotlight
# ───────────────────────────────────────────────────────────────────

WELCOME_3_SUBJECT = "Shop Online Safely: Protect Your Money"
WELCOME_3_PREHEADER = (
    "Credit cards vs. debit cards, spotting fake sites, and keeping your info secure."
)


def build_welcome_3(protection_article: dict) -> str:
    intro = protection_article.get(
        "email_intro_md",
        "Online shopping offers great convenience, but scammers create fake websites to "
        "steal your money and personal information. The good news? You can shop safely "
        "online when you know what to watch for.",
    )
    cta_url = "https://saverwell.com" + protection_article.get(
        "email_cta_url", "/protection/article/safe-online-shopping-tips"
    )
    cta_label = protection_article.get("email_cta_label", "Read full guide")

    body = f"""
          <p style="margin: 0 0 16px; font-size: 20px; font-weight: bold; color: {GREEN};">
            Protect yourself when shopping online
          </p>

          <p style="margin: 0 0 16px;">
            {intro}
          </p>

          <p style="margin: 0 0 4px; font-weight: bold; color: {
        TEXT_DARK
    };">Quick tips to stay safe:</p>

{
        make_bullet_list(
            [
                "Always use a credit card, never a debit card, for online purchases",
                "Look for the lock icon and 'https' in the website address",
                "If a deal looks too good to be true, it probably is",
                "Never shop online using public Wi-Fi",
            ]
        )
    }

          <p style="margin: 16px 0 24px;">
            This is one of our most popular protection guides. It walks you through everything you need to shop online with confidence.
          </p>

{make_cta_button(cta_label, cta_url)}

          <p style="margin: 24px 0 0; font-size: 14px; color: {TEXT_MED};">
            Every Tuesday, we send a new protection tip to help you stay ahead of financial threats. This is just the start.
          </p>"""

    return wrap_email(WELCOME_3_PREHEADER, body, WELCOME_3_SUBJECT)


# ───────────────────────────────────────────────────────────────────
# Email 4: Day 10 - Guide Teaser
# ───────────────────────────────────────────────────────────────────

WELCOME_4_SUBJECT = "7 Ways to Cut Your Medicare Premiums"
WELCOME_4_PREHEADER = (
    "Smart strategies to reduce Medicare costs without sacrificing coverage quality."
)


def build_welcome_4(guide_article: dict) -> str:
    intro = guide_article.get(
        "email_intro_md",
        "Medicare premiums keep rising, but you have more control over your costs "
        "than you might think. These seven proven strategies can help you keep more "
        "money in your pocket while maintaining quality healthcare coverage.",
    )
    cta_url = "https://saverwell.com" + guide_article.get(
        "email_cta_url", "/guides/medicare/save-money-medicare-premiums"
    )
    cta_label = guide_article.get("email_cta_label", "Read the full guide")

    body = f"""
          <p style="margin: 0 0 16px; font-size: 20px; font-weight: bold; color: {GREEN};">
            Are you paying more than you should for Medicare?
          </p>

          <p style="margin: 0 0 16px;">
            {intro}
          </p>

          <p style="margin: 0 0 4px; font-weight: bold; color: {
        TEXT_DARK
    };">Here is a preview of what you will learn:</p>

{
        make_bullet_list(
            [
                "Why comparing plans every year could save you thousands",
                "The Extra Help program that most eligible seniors never apply for",
                "How to appeal IRMAA surcharges when your income drops",
                "The credit card vs. debit card rule for online shopping",
            ]
        )
    }

          <p style="margin: 16px 0 24px;">
            Read the full guide to see all seven strategies, with real examples and step-by-step instructions.
          </p>

{make_cta_button(cta_label, cta_url)}

          <p style="margin: 24px 0 0; font-size: 14px; color: {TEXT_MED};">
            Every Thursday, we share a new guide on Medicare, insurance, and financial topics that matter to seniors. More coming soon.
          </p>"""

    return wrap_email(WELCOME_4_PREHEADER, body, WELCOME_4_SUBJECT)


# ───────────────────────────────────────────────────────────────────
# Email 5: Day 14 - Digest Preview + Preference Center
# ───────────────────────────────────────────────────────────────────

WELCOME_5_SUBJECT = "Your First Weekly Digest Is Ready"
WELCOME_5_PREHEADER = "Discounts, protection tips, and guides - all in one email, every Monday."


def build_welcome_5() -> str:
    body = f"""
          <p style="margin: 0 0 16px; font-size: 20px; font-weight: bold; color: {GREEN};">
            Here is what your weekly digest looks like
          </p>

          <p style="margin: 0 0 16px;">
            Every Monday, you will get a single email with the best finds from the past week. No clutter, no spam, just the savings and tips that matter most to you. Here is a preview of what to expect:
          </p>

          <!-- Digest preview card -->
          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 0 0 8px; border: 1px solid {BORDER}; border-radius: 6px;">
            <tr>
              <td style="padding: 16px 16px 12px; background-color: #f0f7f1; border-radius: 6px 6px 0 0;">
                <p style="margin: 0; font-weight: bold; color: {GREEN}; font-size: 15px;">Discounts Near You</p>
              </td>
            </tr>
            <tr>
              <td style="padding: 12px 16px; font-size: 15px; color: {TEXT_DARK};">
                New senior discounts found this week based on your location. Grocery deals, pharmacy savings, and more.
              </td>
            </tr>
          </table>

          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 0 0 8px; border: 1px solid {BORDER}; border-radius: 6px;">
            <tr>
              <td style="padding: 16px 16px 12px; background-color: #fff8f0; border-radius: 6px 6px 0 0;">
                <p style="margin: 0; font-weight: bold; color: #c65d00; font-size: 15px;">This Week's Protection Tip</p>
              </td>
            </tr>
            <tr>
              <td style="padding: 12px 16px; font-size: 15px; color: {TEXT_DARK};">
                A timely fraud alert or safety guide, chosen based on what is trending. Quick to read, easy to share with family.
              </td>
            </tr>
          </table>

          <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="margin: 0 0 16px; border: 1px solid {BORDER}; border-radius: 6px;">
            <tr>
              <td style="padding: 16px 16px 12px; background-color: #f0f0f7; border-radius: 6px 6px 0 0;">
                <p style="margin: 0; font-weight: bold; color: #3d3d8f; font-size: 15px;">Featured Guide</p>
              </td>
            </tr>
            <tr>
              <td style="padding: 12px 16px; font-size: 15px; color: {TEXT_DARK};">
                A deep dive on Medicare, insurance, or financial topics. This week: making the most of your Medicare enrollment options.
              </td>
            </tr>
          </table>

          <p style="margin: 0 0 16px;">
            Your first digest will arrive next Monday. In the meantime, you can customize what you receive. Choose the topics that matter most to you, and we will tailor your emails accordingly.
          </p>

{make_cta_button("Customize Your Preferences", "{{ unsubscribe_url }}")}

          <p style="margin: 24px 0 0; font-size: 14px; color: {TEXT_MED};">
            Thank you for being part of Saverwell. We are glad you are here.
          </p>"""

    return wrap_email(WELCOME_5_PREHEADER, body, WELCOME_5_SUBJECT)


# ───────────────────────────────────────────────────────────────────
# Customer.io Setup Guide
# ───────────────────────────────────────────────────────────────────


def build_setup_guide() -> str:
    return """# Customer.io Welcome Campaign - Setup Guide

**Last updated:** 2026-02-27
**Campaign type:** Segment-triggered (5 emails, 14 days)
**Templates:** `data/saverwell/email_templates/welcome_*.html`

---

## Prerequisites

Before setting up the Welcome Campaign, ensure:

1. The "Saverwell Lifecycle Subscribe" n8n workflow is active and pushing these attributes to Customer.io profiles:
   - `lifecycle_stage` = "new"
   - `welcome_flow_started` = false
   - `content_interest` (derived from signup page)
   - `zip_code` (from form)
   - `state_resolved` (computed from ZIP)
   - `articles_received` = 0

2. Customer.io workspace has the Track API credentials configured in the n8n workflow.

---

## Step 1: Create Subscription Topics (one-time, ~5 minutes)

Go to **Settings > Subscription Center** in Customer.io.

1. Enable the Subscription Center
2. Create these 5 topics:

| Topic Name | Description (shown to subscribers) |
|---|---|
| Savings & Discounts | Weekly discount alerts and personalized merchant content |
| Fraud Protection | Protection articles, fraud alerts, and safety tips |
| Educational Guides | Medicare guides, insurance guides, and financial education |
| Weekly Digest | Your weekly compilation of the best finds |
| Product & Marketing | Product announcements, partnerships, and promotions |

3. Set all topics to "Opted in by default"
4. Save

---

## Step 2: Create Segments (~10 minutes)

Go to **Segments** in Customer.io. Create these data-driven segments:

### Segment: "New Subscribers"

**Conditions:**
- `lifecycle_stage` equals `new`
- AND `welcome_flow_started` equals `false`

This is the trigger segment for the Welcome Campaign.

### Segment: "Active Subscribers"

**Conditions:**
- `lifecycle_stage` equals `active`

### Segment: "Protection Content Eligible"

**Conditions:**
- `welcome_flow_started` equals `true`
- AND subscribed to topic "Fraud Protection"

### Segment: "Guide Content Eligible"

**Conditions:**
- `welcome_flow_started` equals `true`
- AND subscribed to topic "Educational Guides"

### Segment: "Inactive 30 Days"

**Conditions:**
- `lifecycle_stage` equals `active`
- AND did NOT open any email in the last 30 days
- AND did NOT click any email in the last 30 days

---

## Step 3: Create the Welcome Campaign (~30 minutes)

Go to **Campaigns > New Campaign**.

### Campaign Settings

- **Name:** Saverwell Welcome Flow
- **Trigger type:** Segment-triggered
- **Trigger segment:** "New Subscribers"
- **Goal:** Person clicks any email link
- **Goal deadline:** 14 days
- **Exit conditions:** Person unsubscribes from all topics
- **Re-entry:** Do not allow re-entry (a person should only get the welcome flow once)
- **Associate with topic:** Product & Marketing (the welcome flow is a meta-campaign)

### Journey Flow

Build the following journey in the visual workflow builder:

```
[Entry: Enters "New Subscribers" segment]
    |
    v
[Email 1: Welcome + Discounts]  (Day 0)
    |
    v
[Delay: 3 days]
    |
    v
[Email 2: Hidden Discounts]  (Day 3)
    |
    v
[Delay: 3 days]
    |
    v
[Email 3: Protection Spotlight]  (Day 6)
    |
    v
[Delay: 4 days]
    |
    v
[Email 4: Guide Teaser]  (Day 10)
    |
    v
[Delay: 4 days]
    |
    v
[Email 5: Digest Preview + Preferences]  (Day 14)
    |
    v
[Update Attribute: lifecycle_stage = "active"]
    |
    v
[Update Attribute: welcome_flow_started = true]
    |
    v
[End]
```

### Email Configuration (for each email step)

For each email in the journey, configure these fields:

#### Email 1 (Day 0)

- **Subject:** Welcome to Saverwell - Savings and Protection for Seniors
- **Preheader:** Discounts near you, fraud protection tips, and Medicare guides - all free.
- **Body:** Switch to Code view, paste contents of `welcome_1_discounts.html`
- **Topic:** Savings & Discounts

#### Email 2 (Day 3)

- **Subject:** 3 Discounts Most Seniors Don't Know About
- **Preheader:** These under-the-radar savings are hiding in plain sight.
- **Body:** Switch to Code view, paste contents of `welcome_2_hidden_deals.html`
- **Topic:** Savings & Discounts

#### Email 3 (Day 6)

- **Subject:** Shop Online Safely: Protect Your Money
- **Preheader:** Credit cards vs. debit cards, spotting fake sites, and keeping your info secure.
- **Body:** Switch to Code view, paste contents of `welcome_3_protection.html`
- **Topic:** Fraud Protection

#### Email 4 (Day 10)

- **Subject:** 7 Ways to Cut Your Medicare Premiums
- **Preheader:** Smart strategies to reduce Medicare costs without sacrificing coverage quality.
- **Body:** Switch to Code view, paste contents of `welcome_4_guide.html`
- **Topic:** Educational Guides

#### Email 5 (Day 14)

- **Subject:** Your First Weekly Digest Is Ready
- **Preheader:** Discounts, protection tips, and guides - all in one email, every Monday.
- **Body:** Switch to Code view, paste contents of `welcome_5_digest_preview.html`
- **Topic:** Weekly Digest

---

## Step 4: Test the Campaign (~15 minutes)

1. **Send test emails:** Use Customer.io's "Send test" button on each email step. Verify:
   - Saverwell logo/header renders correctly
   - CTA buttons are clickable and go to the right URLs
   - Preheader text appears in email client previews
   - Unsubscribe/preferences links work
   - Footer displays correctly
   - No em dashes or mid-sentence bolding (brand voice compliance)

2. **Test with a real subscriber:** Create a test profile with `lifecycle_stage = "new"` and `welcome_flow_started = false`. Verify:
   - The profile enters the "New Subscribers" segment
   - Email 1 is sent immediately
   - Subsequent emails arrive on schedule (use Customer.io's time travel for testing)
   - After Email 5, `lifecycle_stage` updates to "active" and `welcome_flow_started` updates to true

3. **Test personalization:** Verify Liquid variables render:
   - `{{ customer.first_name }}` shows name (or gracefully hides greeting if missing)
   - `{{ customer.zip_code }}` shows ZIP in discount URL (or omits if missing)
   - `{{ unsubscribe_url }}` generates valid Customer.io Subscription Center links

---

## Step 5: Activate the Campaign

1. Review the journey one final time
2. Click "Start" to activate the campaign
3. Monitor the first 24 hours for:
   - Delivery rate (target: >98%)
   - Open rate on Email 1 (target: >30%)
   - Unsubscribe rate (target: <0.5%)

---

## Liquid Variables Used in Templates

| Variable | Source | Fallback |
|---|---|---|
| `{{ customer.first_name }}` | n8n webhook (if form collects name) | Conditionally hidden |
| `{{ customer.zip_code }}` | Subscriber form ZIP field | Conditionally hidden |
| `{{ unsubscribe_url }}` | Auto-generated by Customer.io | Always present |

---

## Post-Welcome Flow

After a subscriber completes the welcome flow (lifecycle_stage = "active"):

- **Tuesdays:** Protection content drip (from Content Queue sheet, highest priority article not yet sent)
- **Thursdays:** Guide content drip (from Content Queue sheet, highest priority guide not yet sent)
- **Mondays:** Weekly digest (API-triggered broadcast via n8n)

These are separate Customer.io campaigns that trigger on the "Protection Content Eligible" and "Guide Content Eligible" segments respectively.

---

## Relationship to Other Deliverables

| Deliverable | Status | Link |
|---|---|---|
| Lifecycle Marketing Plan (Google Doc) | Complete | [Google Doc](https://docs.google.com/document/d/1C8yuO1FYQx92hFe-qV2W5evNgEi0-qBzDhkDFBhsKqs/edit) |
| Content Queue (Google Sheet) | Complete | [Google Sheet](https://docs.google.com/spreadsheets/d/1kSVQwjzXO1R9af55DPSTmhq86ZH12u1ra3fcoll1-xE/edit) |
| n8n Lifecycle Subscribe Workflow | Complete (inactive) | [n8n Workflow](https://automation.saverwell.com/workflow/hYsgc6mF8A5gQ0X5) |
| Welcome Campaign Templates | Complete | `data/saverwell/email_templates/welcome_*.html` |
| This Setup Guide | Complete | `data/saverwell/customerio_setup_guide.md` |
"""


# ───────────────────────────────────────────────────────────────────
# Main
# ───────────────────────────────────────────────────────────────────


def main() -> None:
    TEMPLATE_DIR.mkdir(parents=True, exist_ok=True)

    # Load article data for emails 3 and 4
    protection_path = (
        project_root / "data" / "saverwell" / "protection_drafts" / "safe-online-shopping-tips.json"
    )
    guide_path = (
        project_root / "data" / "saverwell" / "guide_drafts" / "save-money-medicare-premiums.json"
    )

    protection_article = {}
    if protection_path.exists():
        with open(protection_path) as f:
            protection_article = json.load(f)
        print(f"  Loaded protection article: {protection_article.get('title')}")
    else:
        print("  Warning: protection article not found, using defaults")

    guide_article = {}
    if guide_path.exists():
        with open(guide_path) as f:
            guide_article = json.load(f)
        print(f"  Loaded guide article: {guide_article.get('title')}")
    else:
        print("  Warning: guide article not found, using defaults")

    # Generate templates
    templates = [
        ("welcome_1_discounts.html", build_welcome_1()),
        ("welcome_2_hidden_deals.html", build_welcome_2()),
        ("welcome_3_protection.html", build_welcome_3(protection_article)),
        ("welcome_4_guide.html", build_welcome_4(guide_article)),
        ("welcome_5_digest_preview.html", build_welcome_5()),
    ]

    print("\nGenerating Welcome Campaign email templates...")
    for filename, html in templates:
        filepath = TEMPLATE_DIR / filename
        with open(filepath, "w") as f:
            f.write(html)
        print(f"  Created: {filepath.relative_to(project_root)}")

    # Generate setup guide
    print("\nGenerating Customer.io setup guide...")
    guide_content = build_setup_guide()
    with open(GUIDE_PATH, "w") as f:
        f.write(guide_content)
    print(f"  Created: {GUIDE_PATH.relative_to(project_root)}")

    # Summary
    print("\n" + "=" * 60)
    print("Welcome Campaign assets generated successfully!")
    print("=" * 60)
    print(f"\nTemplates ({len(templates)} files):")
    for filename, _ in templates:
        print(f"  data/saverwell/email_templates/{filename}")
    print("\nSetup Guide:")
    print("  data/saverwell/customerio_setup_guide.md")
    print("\nNext steps:")
    print("  1. Open Customer.io and follow the setup guide")
    print("  2. Create 5 subscription topics")
    print("  3. Create 5 data-driven segments")
    print("  4. Create the Welcome Campaign with the journey flow")
    print("  5. Paste each HTML template into the corresponding email step")
    print("  6. Send test emails, then activate")
    print("\nEstimated UI time: ~1 hour")


if __name__ == "__main__":
    main()
