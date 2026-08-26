#!/usr/bin/env python3
"""One-off script: Creates a Google Doc for the Saverwell Embeddable Widget.

Covers how the widget works, technical architecture, partner installation
instructions, configuration options, UTM attribution, and email signup flow.

Run:  python scripts/create_widget_doc.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ── Google Auth ───────────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def get_services():
    """Return (docs_service, drive_service) using existing project credentials."""
    from googleapiclient.discovery import build
    from cmo_agent.google_auth import get_google_credentials

    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json")
    )
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")

    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path=sa_path,
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


# ── Inline formatting parser ─────────────────────────────────────────
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


# ── Document structure ────────────────────────────────────────────────
TITLE = "Saverwell Embeddable Discount Widget - Product & Partner Guide"

SECTIONS: List[Dict[str, Any]] = [
    # ── Overview ──────────────────────────────────────────────────
    {
        "heading": "Overview",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The Saverwell Embeddable Widget is a lightweight JavaScript snippet that "
                    "partners install on their website with a single line of code. It renders "
                    "a branded card showing local senior discounts from the Saverwell database, "
                    "includes an inline email signup form, and optionally surfaces a fraud "
                    "protection alert. Every interaction is tracked with UTM parameters that "
                    "flow into the existing Saverwell partner attribution pipeline."
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    "The widget is served from saverwell.com/widget/v1/ via a Cloudflare "
                    "Worker at the edge, so it loads fast from anywhere in the world. It uses "
                    "Shadow DOM for complete CSS isolation, meaning it will not conflict with "
                    "any styling on the host website."
                ),
            },
        ],
    },
    {
        "heading": "What Partners See",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "When a partner adds the widget to their website, their visitors see a "
                    "clean, compact card with the following sections:"
                ),
            },
            {
                "type": "numbered_list",
                "items": [
                    'Header: "Senior Discounts Near [Metro Area]" with a tag icon',
                    "Merchant cards: Each card shows the merchant name, discount details (e.g., "
                    '"10% off every Tuesday, 55+"), and a logo or first-letter fallback',
                    '"See all X discounts near you" call-to-action linking to the full Saverwell DMA page',
                    'Email signup: "Get weekly savings alerts" input with a Subscribe button',
                    "Fraud alert teaser: The latest Saverwell protection article headline (optional, on by default)",
                    '"Powered by Saverwell" footer',
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "The widget supports light and dark themes. Light is the default (white "
                    "background, teal accents matching the Saverwell brand). Dark theme uses a "
                    "dark gray background with light text, suitable for partner sites with "
                    "dark color schemes."
                ),
            },
        ],
    },

    # ── How It Works ──────────────────────────────────────────────
    {
        "heading": "How It Works",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The widget consists of three components, all served from a single "
                    "Cloudflare Worker deployment:"
                ),
            },
        ],
    },
    {
        "heading": "embed.js (the script partners install)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "A ~8 KB vanilla JavaScript file with zero external dependencies. When it "
                    "loads, it reads configuration from data-* attributes on the script tag, "
                    "creates a Shadow DOM container (for CSS isolation), shows a loading "
                    "spinner, fetches discount data from the Saverwell API, and renders the "
                    "widget. All outbound links are automatically stamped with UTM parameters "
                    "for partner attribution."
                ),
            },
        ],
    },
    {
        "heading": "Discounts API",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "GET saverwell.com/widget/v1/api/discounts accepts a zip parameter "
                    "(required, 5-digit US ZIP code), plus optional categories and limit "
                    "parameters. It looks up the DMA (Designated Market Area) for the given "
                    "ZIP, queries published merchant pages from the Saverwell database, and "
                    "fetches the latest protection article for the fraud alert teaser. "
                    "Responses are cached at the Cloudflare edge for 4 hours and in the "
                    "browser for 1 hour."
                ),
            },
            {
                "type": "paragraph",
                "text": "The API returns a JSON response with this structure:",
            },
            {
                "type": "bullets",
                "items": [
                    "dma: The metro area info (slug, display name, merchant count) for the "
                    "given ZIP code",
                    "merchants: An array of merchant objects (name, page slug, logo URL, "
                    "discount text, discount value, website URL)",
                    "alert: The latest protection article (title and slug) for the fraud "
                    "alert teaser",
                ],
            },
        ],
    },
    {
        "heading": "Subscribe API",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "POST saverwell.com/widget/v1/api/subscribe accepts a JSON body with "
                    "email, zip, and partner fields. The endpoint injects UTM fields "
                    "(utm_source=partner, utm_campaign={partner name}, utm_medium=widget) and "
                    "forwards the signup to the Saverwell lifecycle pipeline. Subscribers "
                    "enter the same co-branded email flow as any other partner-referred user, "
                    "meaning their welcome emails include both the partner's branding and "
                    "Saverwell's branding."
                ),
            },
        ],
    },

    # ── UTM Attribution ───────────────────────────────────────────
    {
        "heading": "UTM Attribution & Analytics",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "The widget uses the same UTM convention as all Saverwell partner "
                    "traffic. This means widget clicks automatically trigger the existing "
                    "co-branding pipeline in Customer.io with no additional configuration."
                ),
            },
            {
                "type": "table",
                "headers": ["UTM Parameter", "Value", "Purpose"],
                "rows": [
                    [
                        "utm_source",
                        "partner",
                        "Identifies this as partner traffic (triggers co-brand logic)",
                    ],
                    [
                        "utm_campaign",
                        "{partner name}",
                        "Identifies which partner, triggers co-branded emails",
                    ],
                    [
                        "utm_medium",
                        "widget",
                        "Distinguishes widget clicks from other partner channels",
                    ],
                    [
                        "utm_content",
                        "{element type}",
                        "What was clicked: discount_card, see_all, protection_alert, "
                        "powered_by",
                    ],
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "In GA4, you can segment widget traffic by filtering on "
                    "utm_medium = widget. To see all traffic from a specific partner "
                    "(widget plus any other channel), filter on utm_campaign = {partner name}."
                ),
            },
        ],
    },

    # ── Email Signup Flow ─────────────────────────────────────────
    {
        "heading": "Email Signup Flow",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "When a visitor signs up via the widget, they never leave the partner's "
                    "website. The signup is handled entirely within the widget:"
                ),
            },
            {
                "type": "numbered_list",
                "items": [
                    "Visitor enters their email in the widget and clicks Subscribe",
                    "Widget validates the email format client-side",
                    "Widget POSTs to saverwell.com/widget/v1/api/subscribe with the email, "
                    "ZIP code, and partner name",
                    "Cloudflare Worker injects UTM fields and forwards to the Saverwell "
                    "lifecycle pipeline",
                    "Customer.io profile is created with brand = {partner name}",
                    "Welcome flow triggers with co-branded emails showing both the "
                    "partner's logo and Saverwell's logo",
                    'Widget shows "Check your inbox for your first savings digest!"',
                ],
            },
            {
                "type": "paragraph",
                "text": (
                    "From that point forward, the subscriber is in the Saverwell ecosystem "
                    "receiving co-branded weekly savings digests, protection alerts, and "
                    "guide recommendations, all personalized to their ZIP code."
                ),
            },
        ],
    },

    # ── Partner Requirements ──────────────────────────────────────
    {
        "heading": "Partner Requirements",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Adding the Saverwell widget requires minimal technical effort. There is "
                    "nothing to download, no API keys to manage, and no server-side "
                    "integration needed."
                ),
            },
        ],
    },
    {
        "heading": "What you need",
        "level": 2,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "A website where you can add a script tag (any CMS, static site, or "
                    "custom-built site works)",
                    "Your assigned partner name (provided by Saverwell during onboarding)",
                    "The primary ZIP code to show discounts for (usually your office location "
                    "or your client base's primary area)",
                ],
            },
        ],
    },
    {
        "heading": "Installation (2 minutes)",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "Copy and paste the following line into your website's HTML, wherever you "
                    "want the widget to appear. Replace YOUR-PARTNER-NAME with the partner "
                    "name Saverwell provides, and YOUR-ZIP with a 5-digit ZIP code:"
                ),
            },
            {
                "type": "paragraph",
                "text": (
                    '<script src="https://saverwell.com/widget/v1/embed.js" '
                    'data-partner="YOUR-PARTNER-NAME" data-zip="YOUR-ZIP"></script>'
                ),
            },
            {
                "type": "paragraph",
                "text": "That's it. The widget will render automatically when the page loads.",
            },
        ],
    },
    {
        "heading": "Configuration Options",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "All configuration is done through data-* attributes on the script tag. "
                    "Only data-partner and data-zip are required. Everything else is optional."
                ),
            },
            {
                "type": "table",
                "headers": ["Attribute", "Required", "Default", "Description"],
                "rows": [
                    [
                        "data-partner",
                        "Yes",
                        "-",
                        "Your partner name (provided by Saverwell). Used for attribution "
                        "and co-branded emails.",
                    ],
                    [
                        "data-zip",
                        "Yes",
                        "-",
                        "5-digit US ZIP code. Determines which metro area's discounts to "
                        "show.",
                    ],
                    [
                        "data-count",
                        "No",
                        "5",
                        "Number of merchant discounts to display (1 to 10).",
                    ],
                    [
                        "data-categories",
                        "No",
                        "all",
                        "Comma-separated category IDs to filter by (e.g., grocery, pharmacy).",
                    ],
                    [
                        "data-theme",
                        "No",
                        "light",
                        'Set to "dark" for dark backgrounds. Light theme has white background '
                        "with teal accents.",
                    ],
                    [
                        "data-show-protection",
                        "No",
                        "true",
                        'Set to "false" to hide the fraud alert teaser at the bottom of '
                        "the widget.",
                    ],
                ],
            },
        ],
    },
    {
        "heading": "Examples",
        "level": 2,
        "content": [
            {
                "type": "paragraph",
                "text": "**Basic install** (shows 5 discounts near ZIP 85281, light theme):",
            },
            {
                "type": "paragraph",
                "text": (
                    '<script src="https://saverwell.com/widget/v1/embed.js" '
                    'data-partner="jones-financial" data-zip="85281"></script>'
                ),
            },
            {
                "type": "paragraph",
                "text": "**Dark theme, 3 discounts, no fraud alert:**",
            },
            {
                "type": "paragraph",
                "text": (
                    '<script src="https://saverwell.com/widget/v1/embed.js" '
                    'data-partner="jones-financial" data-zip="85281" '
                    'data-theme="dark" data-count="3" '
                    'data-show-protection="false"></script>'
                ),
            },
            {
                "type": "paragraph",
                "text": "**Sidebar placement** (works in narrow containers down to ~280px):",
            },
            {
                "type": "paragraph",
                "text": (
                    "The widget's max width is 400px and it adapts to smaller containers. "
                    "It works well in sidebars, footer areas, or embedded within article content."
                ),
            },
        ],
    },

    # ── Compatibility ─────────────────────────────────────────────
    {
        "heading": "Technical Compatibility",
        "level": 1,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "Works on any website that supports script tags (WordPress, Squarespace, "
                    "Wix, Webflow, custom HTML, etc.)",
                    "No external dependencies or libraries required",
                    "Uses Shadow DOM for CSS isolation, so it will not affect or be affected by "
                    "the host site's styles",
                    "Loads asynchronously and does not block page rendering",
                    "Total size: ~8 KB (serves from Cloudflare's edge CDN for fast loading)",
                    "CORS-enabled: works when embedded on any domain",
                    "Supports all modern browsers (Chrome, Firefox, Safari, Edge)",
                ],
            },
        ],
    },

    # ── What Partners Get ─────────────────────────────────────────
    {
        "heading": "What Partners Get",
        "level": 1,
        "content": [
            {
                "type": "bullets",
                "items": [
                    "A free, useful tool for your website visitors (no cost to you or them)",
                    "Increased website engagement and stickiness",
                    "Co-branded Saverwell emails for any visitors who subscribe through "
                    "your widget, featuring your logo alongside Saverwell's",
                    "Full attribution: Saverwell tracks every click and signup from your "
                    "widget, so you can see the impact",
                    "Automatic updates: when Saverwell adds new merchants or discounts, "
                    "your widget reflects them automatically with no action needed",
                ],
            },
        ],
    },

    # ── FAQ ────────────────────────────────────────────────────────
    {
        "heading": "Frequently Asked Questions",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "**Does the widget slow down my website?**",
            },
            {
                "type": "paragraph",
                "text": (
                    "No. The script is ~8 KB and loads asynchronously from Cloudflare's "
                    "global edge network. It does not block page rendering."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Will it conflict with my website's design?**",
            },
            {
                "type": "paragraph",
                "text": (
                    "No. The widget uses Shadow DOM, which creates a fully isolated CSS "
                    "scope. Your styles will not leak in, and the widget's styles will not "
                    "leak out."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Can I customize the appearance?**",
            },
            {
                "type": "paragraph",
                "text": (
                    "You can choose light or dark theme, control how many discounts to show "
                    "(1 to 10), filter by merchant category, and hide the fraud alert section. "
                    "The widget's max width is 400px and it adapts to its container."
                ),
            },
            {
                "type": "paragraph",
                "text": "**What happens when someone subscribes through my widget?**",
            },
            {
                "type": "paragraph",
                "text": (
                    "They enter the Saverwell email lifecycle with your partner branding. "
                    "Their welcome emails and ongoing digests show both your logo and "
                    "Saverwell's logo. You get full credit for the referral."
                ),
            },
            {
                "type": "paragraph",
                "text": "**Can I place it on multiple pages?**",
            },
            {
                "type": "paragraph",
                "text": (
                    "Yes. You can add the script tag to as many pages as you like. Each "
                    "instance can use a different ZIP code if needed (e.g., a financial "
                    "advisor with offices in multiple cities)."
                ),
            },
            {
                "type": "paragraph",
                "text": "**How do I get my partner name?**",
            },
            {
                "type": "paragraph",
                "text": (
                    "Saverwell assigns your partner name during onboarding. It is typically "
                    "a lowercase, hyphenated version of your business name (e.g., "
                    '"jones-financial", "tampa-senior-center").'
                ),
            },
        ],
    },

    # ── Support ───────────────────────────────────────────────────
    {
        "heading": "Support",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": (
                    "If you have questions about installing or configuring the widget, "
                    "contact the Saverwell team at the email or Slack channel provided "
                    "during your onboarding."
                ),
            },
        ],
    },
]


# ── Doc builder ───────────────────────────────────────────────────────
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
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []
                    time.sleep(0.3)
                    _ds = docs_service.documents().get(documentId=doc_id).execute()
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

                doc_state = docs_service.documents().get(documentId=doc_id).execute()
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
                    bold_requests = []
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
