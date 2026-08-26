#!/usr/bin/env python3
"""Replace the Complete Lovable Prompt section in the homepage redesign Google Doc.

Usage:  python scripts/update_lovable_prompt_section.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

DOC_ID = "18ddUK7r4uKMLb77gFAA0NY2y_3uYfbYdDi_FGYtKeuU"
SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

# ── CDN URLs ──────────────────────────────────────────────────────────
HERO_URL = "https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/cmo-agent/hero-options/hero_option_a.jpg"
ICON_FIND = "https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/cmo-agent/hero-options/icon_find_discounts.png"
ICON_PROTECT = "https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/cmo-agent/hero-options/icon_protect_savings.png"
ICON_GUIDES = "https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/cmo-agent/hero-options/icon_read_guides.png"
ICON_DIRECTORY = "https://lmtrgkmgfermqatopkfp.supabase.co/storage/v1/object/public/cmo-agent/hero-options/icon_store_directory.png"


LOVABLE_PROMPT = """Apply all of the following changes to the /homepage-redesign page in a single pass. Do not change anything not listed below. All text across the entire page must use the Manrope font family.

HEADER NAV
- Subscribe button text: "Subscribe for Free"
- Subscribe button style: background #F4B942 (brand gold), text #2A2F35 (charcoal)

HERO SECTION
- H1 "Save more. Stay protected.": remove whitespace-nowrap on mobile, keep md:whitespace-nowrap so it wraps naturally on small screens
- Mobile height: h-auto min-h-[320px] py-8. Desktop: md:h-[380px]
- Subheadline: insert <br> after "protection" so it reads "Senior discounts at 125,000+ locations. Fraud protection<br>alerts and free expert guides, built for adults 55+." This prevents the text from wrapping across the woman's face in the hero image.
- Stats bar: flex-col on mobile, md:flex-row on desktop. Hide dividers on mobile (hidden md:block). Change "Personalized savings tips in your inbox" to "Personalized savings tips".
- CTA button text: "Subscribe for Free". Background #F4B942 (brand gold), text #2A2F35 (charcoal). Must match header button exactly.
- Spacing below hero: reduce How It Works section top padding to py-6 md:py-8 so hero and How It Works feel like one connected above-the-fold unit.

CARD GRIDS (applies to ALL four sections: How It Works, Popular Senior Discounts, Stay Protected, Expert Guides)
- Layout: grid grid-cols-2 lg:grid-cols-4 gap-3 md:gap-6
- Card padding: p-3 on mobile, md:p-5 on desktop
- Card titles: text-sm on mobile, md:text-lg on desktop
- Category badges: remove ALL hover effects (no hover:opacity, hover:bg-*, or transitions). Badges must look identical on hover - currently they become unreadable when hovered.

HOW IT WORKS SECTION
- Section heading: keep centered, but use the same font-family and font-weight as the other section headings ("Popular Senior Discounts", "Stay Protected", "Expert Guides").
- Icons: add rounded-full CSS class to each icon <img> element. The PNG images have a white background outside the teal circle that shows on hover - rounded-full clips to a circle, hiding the white corners.
- Icon sizing: w-16 h-16 on mobile, md:w-[120px] md:h-[120px] on desktop.

POPULAR SENIOR DISCOUNTS SECTION
- No changes. This is the reference section for card styling.

STAY PROTECTED SECTION
- Category badges: background CORAL (#E76F51) with white text. Same shape/size/radius/padding as Popular Senior Discounts badges.
- Article selection: do NOT show 4 articles from the same category. Query protection_articles selecting one article per unique category_slug (e.g. one each from "scams", "fraud", "identity", "tech"), picking the most recent article in each category. This showcases the breadth of protection content.

EXPERT GUIDES SECTION
- Category badges: background brand GOLD #F4B942 with charcoal #2A2F35 text. Use exactly #F4B942 - NOT orange, NOT amber. Same shape/size/radius/padding as other section badges.

VIEW ALL LINKS (all sections)
- "View store directory", "View all articles", "View all guides": change to text-lg font-semibold. They are currently too small and must stand out as key navigation elements.

EMAIL SIGNUP SECTION
- No changes. Keep id="subscribe".

FOOTER
- No changes."""


def get_docs_service():
    """Return docs_service."""
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import get_google_credentials

    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json")
    )
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
    creds = get_google_credentials(
        oauth_token_path=oauth_path, service_account_path=sa_path, scopes=SCOPES
    )
    if creds is None:
        raise RuntimeError("No Google credentials found.")
    return build("docs", "v1", credentials=creds)


def find_section_range(
    doc: Dict[str, Any], start_heading: str, end_heading: str
) -> Optional[Tuple[int, int]]:
    """Find range between two named H1 headings.

    Returns (content_start_after_start_heading, start_of_end_heading).
    Searches by heading text content, not by style - handles cases where
    separators (---) get mis-styled as H1.
    """
    body = doc.get("body", {}).get("content", [])
    start_end_idx = None
    end_start_idx = None

    for elem in body:
        para = elem.get("paragraph", {})
        text = ""
        for el in para.get("elements", []):
            text += el.get("textRun", {}).get("content", "")
        text = text.strip()

        if start_end_idx is None:
            if start_heading in text:
                start_end_idx = elem.get("endIndex", 1)
        elif end_heading in text:
            end_start_idx = elem.get("startIndex", start_end_idx)
            break

    if start_end_idx is not None and end_start_idx is not None:
        return (start_end_idx, end_start_idx)

    # If end heading not found, delete to doc end
    if start_end_idx is not None:
        last_end = body[-1].get("endIndex", start_end_idx + 1) - 1
        return (start_end_idx, last_end)

    return None


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


def main() -> None:
    print("Initializing Google Docs API...")
    docs = get_docs_service()

    # Read the doc
    doc = docs.documents().get(documentId=DOC_ID).execute()

    # Find everything between "Complete Lovable Prompt" and "Verification Checklist"
    rng = find_section_range(doc, "Complete Lovable Prompt", "Verification Checklist")
    if rng is None:
        raise RuntimeError("Could not find 'Complete Lovable Prompt' heading in doc")

    content_start, section_end = rng
    print(f"Found section: content starts at {content_start}, next section at {section_end}")

    # Step 1: Delete the old content between the heading and the next section
    requests: List[Dict[str, Any]] = []
    if section_end > content_start:
        requests.append({
            "deleteContentRange": {
                "range": {
                    "startIndex": content_start,
                    "endIndex": section_end,
                }
            }
        })
        docs.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": requests}
        ).execute()
        print("Deleted old prompt content.")
        time.sleep(0.5)

    # Re-read doc for accurate cursor
    doc = docs.documents().get(documentId=DOC_ID).execute()

    # Find cursor: right after the "Complete Lovable Prompt" heading
    body = doc.get("body", {}).get("content", [])
    cursor = None
    for elem in body:
        para = elem.get("paragraph", {})
        style = para.get("paragraphStyle", {})
        named_style = style.get("namedStyleType", "")
        text = ""
        for el in para.get("elements", []):
            text += el.get("textRun", {}).get("content", "")
        if "Complete Lovable Prompt" in text.strip() and named_style == "HEADING_1":
            cursor = elem.get("endIndex", 1)
            break

    if cursor is None:
        raise RuntimeError("Could not find heading after deletion")

    print(f"Inserting new prompt at index {cursor}...")

    # Step 2: Set narrow page margins for the whole doc (0.5 inch = 36pt)
    margin_requests: List[Dict[str, Any]] = [{
        "updateDocumentStyle": {
            "documentStyle": {
                "marginTop": {"magnitude": 36, "unit": "PT"},
                "marginBottom": {"magnitude": 36, "unit": "PT"},
                "marginLeft": {"magnitude": 36, "unit": "PT"},
                "marginRight": {"magnitude": 36, "unit": "PT"},
            },
            "fields": "marginTop,marginBottom,marginLeft,marginRight",
        }
    }]
    docs.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": margin_requests}
    ).execute()
    time.sleep(0.3)

    # Step 3: Insert the prompt content
    requests = []

    # Track where all new content starts
    section_start = cursor

    # Intro paragraph
    intro = (
        "Copy everything below the line and paste it into Lovable. "
        "The prompt updates the /homepage-redesign prototype page.\n"
    )
    requests.append({"insertText": {"location": {"index": cursor}, "text": intro}})
    cursor += len(intro)

    # Separator + prompt + separator as one block
    sep = "---\n"
    prompt_text = sep + LOVABLE_PROMPT + "\n" + sep
    requests.append(
        {"insertText": {"location": {"index": cursor}, "text": prompt_text}}
    )
    cursor += len(prompt_text)

    # Apply compact styling to EVERYTHING (intro + prompt block)
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": section_start, "endIndex": cursor},
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT",
                "lineSpacing": 100,
                "spaceAbove": {"magnitude": 0, "unit": "PT"},
                "spaceBelow": {"magnitude": 0, "unit": "PT"},
            },
            "fields": "namedStyleType,lineSpacing,spaceAbove,spaceBelow",
        }
    })
    requests.append({
        "updateTextStyle": {
            "range": {"startIndex": section_start, "endIndex": cursor},
            "textStyle": {
                "fontSize": {"magnitude": 8, "unit": "PT"},
            },
            "fields": "fontSize",
        }
    })

    # Flush all content
    docs.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": requests}
    ).execute()

    # Step 4: Now bold section headers within the prompt (lines starting with numbers like "1.", "2.")
    # Re-read doc to find the prompt text range
    time.sleep(0.3)
    doc = docs.documents().get(documentId=DOC_ID).execute()
    body = doc.get("body", {}).get("content", [])

    bold_requests: List[Dict[str, Any]] = []
    section_headers = [
        "HEADER NAV",
        "HERO SECTION",
        "CARD GRIDS",
        "HOW IT WORKS SECTION",
        "POPULAR SENIOR DISCOUNTS SECTION",
        "STAY PROTECTED SECTION",
        "EXPERT GUIDES SECTION",
        "VIEW ALL LINKS",
        "EMAIL SIGNUP SECTION",
        "FOOTER",
    ]

    for elem in body:
        para = elem.get("paragraph", {})
        for el in para.get("elements", []):
            text_run = el.get("textRun", {})
            content = text_run.get("content", "")
            for header in section_headers:
                if header in content:
                    si = el.get("startIndex", 0)
                    ei = el.get("endIndex", 0)
                    if ei > si:
                        bold_requests.append({
                            "updateTextStyle": {
                                "range": {"startIndex": si, "endIndex": ei},
                                "textStyle": {
                                    "bold": True,
                                    "fontSize": {"magnitude": 9, "unit": "PT"},
                                },
                                "fields": "bold,fontSize",
                            }
                        })
                    break

    if bold_requests:
        docs.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": bold_requests}
        ).execute()

    print("\nDone! Updated the Lovable prompt section.")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    main()
