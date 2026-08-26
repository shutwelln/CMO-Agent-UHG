#!/usr/bin/env python3
"""Generate high-res widget visuals via Gemini 3.1 Flash Image and insert into Google Doc.

Creates two images:
  1. Widget mockup - what the widget looks like embedded on a partner's website
  2. Flow diagram - how data flows from partner site through Saverwell infrastructure

Uploads to Supabase, then appends to the existing Widget Google Doc.

Usage:  python scripts/create_widget_visuals_gemini.py
"""
from __future__ import annotations

import base64
import io
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUTPUT_DIR = ROOT / "data" / "saverwell"
DOC_ID = "1EA2Sq4RznL725RuU1oOVjPp8oxvpM_xgbTEu_UkP7NY"
GEMINI_MODEL = "gemini-3.1-flash-image-preview"


def generate_image(api_key: str, prompt: str, aspect_ratio: str = "16:9") -> bytes:
    """Call Gemini 3.1 Flash Image to generate a high-res image."""
    resp = httpx.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"Content-Type": "application/json"},
        params={"key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseModalities": ["IMAGE", "TEXT"],
                "imageConfig": {
                    "aspectRatio": aspect_ratio,
                    "imageSize": "2K",
                },
            },
        },
        timeout=120.0,
    )
    resp.raise_for_status()
    data = resp.json()

    candidates = data.get("candidates", [])
    for candidate in candidates:
        parts = candidate.get("content", {}).get("parts", [])
        for part in parts:
            inline_data = part.get("inlineData")
            if inline_data and inline_data.get("mimeType", "").startswith("image/"):
                return base64.b64decode(inline_data["data"])

    raise ValueError(f"Gemini did not return an image. Response: {data}")


def compress_png(image_bytes: bytes, max_bytes: int = 2_000_000) -> bytes:
    """Compress a PNG image by converting to optimized JPEG if too large."""
    if len(image_bytes) <= max_bytes:
        return image_bytes
    from PIL import Image as PILImage

    img = PILImage.open(io.BytesIO(image_bytes))
    # Convert to RGB if RGBA (JPEG doesn't support alpha)
    if img.mode == "RGBA":
        bg = PILImage.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    result = buf.getvalue()
    print(f"Compressed {len(image_bytes):,} -> {len(result):,} bytes (JPEG)")
    return result


def upload_to_supabase(image_bytes: bytes, filename: str) -> str:
    """Upload image bytes to Supabase Storage and return the public URL."""
    from cmo_agent.config import Settings

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    # Compress large images to avoid upload timeouts
    data = compress_png(image_bytes)
    content_type = "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png"
    if content_type == "image/jpeg":
        filename = filename.rsplit(".", 1)[0] + ".jpg"

    bucket = "cmo-agent"
    path = f"widget-docs/{filename}"

    upload_url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{path}"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": content_type,
        "x-upsert": "true",
    }

    timeout = httpx.Timeout(connect=30.0, read=60.0, write=120.0, pool=30.0)
    for attempt in range(3):
        try:
            resp = httpx.post(upload_url, headers=headers, content=data, timeout=timeout)
            if resp.status_code >= 400:
                print(f"Upload error {resp.status_code}: {resp.text}")
                resp.raise_for_status()
            break
        except (httpx.WriteTimeout, httpx.ReadError) as e:
            if attempt < 2:
                print(f"Upload attempt {attempt + 1} failed ({e}), retrying...")
                import time
                time.sleep(2)
            else:
                raise

    public_url = f"{settings.supabase_url}/storage/v1/object/public/{bucket}/{path}"
    print(f"Uploaded: {public_url}")
    return public_url


def insert_images_into_doc(image_urls: List[Dict[str, Any]]) -> None:
    """Append images with captions to the existing Google Doc."""
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import get_google_credentials

    oauth_path = os.getenv(
        "GOOGLE_OAUTH_TOKEN_PATH", str(ROOT / "data" / "google-token.json")
    )
    sa_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive.file",
    ]

    creds = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path=sa_path,
        scopes=scopes,
    )
    docs = build("docs", "v1", credentials=creds)

    # Get current doc end index
    doc = docs.documents().get(documentId=DOC_ID).execute()
    body_content = doc.get("body", {}).get("content", [])
    cursor = body_content[-1].get("endIndex", 1) - 1 if body_content else 1

    requests: List[Dict[str, Any]] = []

    # Section heading
    heading_text = "Visual Overview (High-Res)\n"
    requests.append({"insertText": {"location": {"index": cursor}, "text": heading_text}})
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": cursor, "endIndex": cursor + len(heading_text)},
            "paragraphStyle": {
                "namedStyleType": "HEADING_1",
                "spaceAbove": {"magnitude": 14, "unit": "PT"},
                "spaceBelow": {"magnitude": 4, "unit": "PT"},
            },
            "fields": "namedStyleType,spaceAbove,spaceBelow",
        }
    })
    cursor += len(heading_text)

    # Flush heading first
    docs.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": requests}
    ).execute()
    requests = []

    for entry in image_urls:
        # Re-read doc for accurate cursor
        time.sleep(0.5)
        doc = docs.documents().get(documentId=DOC_ID).execute()
        body_content = doc.get("body", {}).get("content", [])
        cursor = body_content[-1].get("endIndex", 1) - 1 if body_content else 1

        # Caption
        caption = entry["caption"] + "\n"
        requests.append({"insertText": {"location": {"index": cursor}, "text": caption}})
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": cursor, "endIndex": cursor + len(caption)},
                "paragraphStyle": {
                    "namedStyleType": "HEADING_2",
                    "spaceAbove": {"magnitude": 10, "unit": "PT"},
                    "spaceBelow": {"magnitude": 4, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceAbove,spaceBelow",
            }
        })
        cursor += len(caption)

        # Newline for image
        requests.append({"insertText": {"location": {"index": cursor}, "text": "\n"}})
        cursor += 1

        # Insert image (16:9 aspect -> width 468pt, height ~263pt)
        width_pt = 468
        height_pt = width_pt * entry["aspect"]
        requests.append({
            "insertInlineImage": {
                "location": {"index": cursor - 1},
                "uri": entry["url"],
                "objectSize": {
                    "width": {"magnitude": width_pt, "unit": "PT"},
                    "height": {"magnitude": height_pt, "unit": "PT"},
                },
            }
        })

        docs.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": requests}
        ).execute()
        requests = []
        print(f"Inserted: {entry['caption']}")

    print("Done inserting images.")


# ── Prompts ──────────────────────────────────────────────────────────────

MOCKUP_PROMPT = """\
Create a photorealistic UI screenshot of a Medicare insurance agency website \
that has a TWO-COLUMN LAYOUT: the main website content on the LEFT and a \
separate discount widget on the RIGHT. The two columns must NOT overlap. \
Every single word of text must be real, legible English - no placeholder \
text, no lorem ipsum, no gibberish, no blurry or garbled letters.

LEFT COLUMN - THE MAIN WEBSITE (~68% of width):
- Full-width top navigation bar spanning the entire image width. On the far \
left of the nav bar is the Bright Path Medicare logo: a teal compass/path \
icon (circular teal icon depicting a stylized path or compass rose) followed \
by the text "Bright Path Medicare" ALL ON ONE SINGLE LINE in dark navy bold \
sans-serif font. Do NOT stack the name on two lines - it must read \
"Bright Path Medicare" horizontally on one line next to the icon. To the \
right of the logo are nav links: "Plans" "Enrollment" "Resources" "Contact"
- Hero section with the heading: "Find the Right Medicare Plan for You"
- Subheading: "We help Arizona seniors navigate Medicare options, compare \
plans, and enroll with confidence."
- A teal call-to-action button reading "Schedule a Free Consultation"
- Below, a section heading: "Why Choose Bright Path?"
- Three small feature cards in a row that fit ENTIRELY within the left column \
and do NOT extend under or behind the widget:
  Card 1: "Licensed Agents" - "Our team is certified in all 50 states"
  Card 2: "No Cost to You" - "Our services are always free for you"
  Card 3: "Local Experts" - "We know the Arizona Medicare landscape"

RIGHT COLUMN - THE SAVERWELL WIDGET (~28% of width, clearly separated):
This widget sits in its own column to the RIGHT of the main content. There \
must be visible whitespace or a clear gutter between the main content and \
the widget. The widget must NOT overlap or cover any part of the main site.
- Card with subtle shadow and rounded corners
- Widget header in teal (#2A9D8F) background with white text: \
"Senior Discounts Near Phoenix, AZ"
- Three discount rows, each with a small colored circle, bold store name, \
and one-line discount description:
  Row 1: "Kroger" - "10% off every Tuesday for ages 60+"
  Row 2: "Ross" - "10% off every Wednesday for ages 55+"
  Row 3: "Walgreens" - "20% off Seniors Day, first Tuesday monthly"
- A teal link reading "See all 147 discounts near you"
- A compact email signup: text input with placeholder "Enter your email" \
and a teal button reading "Get Savings"
- Footer text in small gray: "Powered by Saverwell"

CRITICAL LAYOUT RULE: The left column content and right column widget must \
be side by side with clear separation. The widget must not cover or overlap \
any cards, text, or buttons from the main website. Think of it like a \
classic blog layout with a main content area and a sidebar.

STYLE: Clean, modern, professional. White and light gray background. Teal \
(#2A9D8F) accents. Sans-serif font. Subtle shadows on cards. Must look like \
a real screenshot of a live website. Crisp, sharp text rendering.
"""

FLOW_PROMPT = """\
Create a clean, professional infographic showing a data flow architecture \
diagram for an embeddable widget system. The diagram should show these steps \
flowing left to right:

1. "Partner Website" (shown as a browser window icon) with an embedded widget card
2. An arrow pointing to "Cloudflare Worker" (shown as a cloud/edge server icon)
3. The Worker connects to "Supabase Database" (shown as a database icon) \
labeled "1,400+ merchants, 8,700+ discounts, 210 DMAs"
4. A separate flow from the widget showing "Email Signup" going through the \
Worker to "Customer.io" (shown as an email/automation icon) labeled \
"Co-branded lifecycle emails"
5. Another arrow from the widget to "GA4 Analytics" (shown as a chart icon) \
labeled "UTM attribution tracking"

Use a clean, modern style with teal (#2A9D8F) as the primary accent color \
on a white/light gray background. Each node should be a rounded rectangle \
or icon with a label. Arrows should be clean with optional labels. \
The overall look should be like a professional SaaS architecture diagram \
you would see in product documentation. Minimal, clear, no clutter.
"""


COBRAND_SITE_PROMPT = """\
Create a photorealistic UI screenshot of the Saverwell website homepage \
co-branded with a partner called "Bright Path Medicare". Every single word \
of text must be real, legible English. No gibberish, no placeholder text, \
no blurry letters.

THE HEADER BAR (white background, full width):
- Far left: The Saverwell logo (a teal shield icon with a checkmark and \
location pin, followed by the word "Saverwell" in dark navy text). \
Immediately to the right of the Saverwell logo, separated by a thin \
vertical gray divider line, show a second logo: a simple teal compass/path \
icon followed by the text "Bright Path Medicare" in dark navy. Both logos \
sit side by side in the header.
- Center-right: Navigation links in gray text: "Discounts" "Protection" \
"Guides" "Store Directory"
- Far right: A search icon, then a teal "Subscribe" button with white text

THE HERO SECTION (full-width photo background showing the inside of a \
pharmacy/drugstore with a friendly pharmacist, slightly darkened overlay):
- Large white bold heading: "Save more. Stay protected."
- Smaller white subheading below: "Discounts, fraud protection, and expert \
guides built for people who want to make the most of their money."

HOW IT WORKS SECTION (white background below the hero):
- Section heading in black: "How It Works"
- Four cards in a row, each with a small colorful icon above, a bold title, \
and gray description text:
  Card 1: "Find Discounts Near You" - "Search locally or browse nationwide."
  Card 2: "Protect Your Savings" - "Know the warning signs before they cost you."
  Card 3: "Read Our Guides" - "Medicare, insurance, fraud protection, and more. All free."
  Card 4: "Browse Store Directory" - "Stores, services, and malls across the country."

Below that, a section heading: "Popular Senior Discounts"
With subtext: "Explore top-rated stores & services offering discounts for seniors"
And a link on the right: "View All Stores" with an arrow

STYLE: Clean, modern, professional. White background with teal (#2A9D8F) \
accents. Sans-serif typography. This must look like a real screenshot of a \
live website. Crisp text, proper spacing, professional layout.
"""

COBRAND_EMAIL_PROMPT = """\
Create a photorealistic screenshot of a marketing welcome email, shown as it \
would appear in an email client. Every single word of text must be real, \
legible English. No gibberish, no placeholder text, no blurry letters.

The email has a clean white background with centered content, max width \
around 560 pixels. Here is the exact layout from top to bottom:

HEADER AREA (centered):
- The Saverwell logo (a teal shield icon with a checkmark and location pin) \
followed by the word "Saverwell" in dark navy text. Immediately to the right, \
separated by a small vertical divider or "x" symbol, show a second logo: a \
simple teal compass/path icon followed by "Bright Path Medicare" in dark navy. \
Both logos sit side by side, centered.
- Below the logos, centered gray tagline text: "Save more. Stay protected."
- A thin horizontal gray line separator

EMAIL BODY (left-aligned text):
- Bold heading: "Welcome to Saverwell"
- Body paragraph: "Welcome to Saverwell. We help seniors save money, stay \
protected from fraud, and navigate Medicare with confidence."
- Body text: "Here is what you will get from us:"
- Bullet list with four items:
  - "Senior discounts near you, updated weekly"
  - "Fraud protection tips to keep your money safe"
  - "Medicare guides that save you hundreds"
  - "A weekly digest with the best finds"
- A large teal (#2A9D8F) rounded button, centered, with white text: \
"Explore Senior Discounts"
- Body paragraph below the button: "Over the next two weeks, we will send \
you our best savings tips, protection guides, and Medicare resources."

FOOTER (centered):
- A thin horizontal gray line separator
- The Saverwell logo (smaller, just the shield icon and "Saverwell" text)
- Below: two small gray underlined links: "Manage your email preferences" \
then a pipe separator then "Unsubscribe from all"
- Below: small gray text: "Saverwell Holdings, LLC"

STYLE: Clean, minimal email design. White background. Teal (#2A9D8F) for \
the button and logo accents. Dark navy (#1F2937) for heading text. Gray \
(#6B7280) for body text. This should look like a real email screenshot, \
not a wireframe. Professional, polished, proper typography and spacing.
"""


def main() -> None:
    from cmo_agent.config import Settings

    settings = Settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")

    print(f"Using model: {GEMINI_MODEL}")
    print()

    mockup_path = OUTPUT_DIR / "widget_mockup_hires.png"

    # Regenerate the widget mockup with updated Bright Path Medicare logo
    if mockup_path.exists():
        print(f"Using cached: {mockup_path}")
        mockup_bytes = mockup_path.read_bytes()
    else:
        print("Generating widget mockup (Medicare agency + matching logo)...")
        mockup_bytes = generate_image(api_key, MOCKUP_PROMPT, aspect_ratio="16:9")
        mockup_path.write_bytes(mockup_bytes)
        print(f"Saved locally: {mockup_path} ({len(mockup_bytes):,} bytes)")

    # Upload to Supabase (overwrite previous)
    print("\nUploading to Supabase...")
    mockup_url = upload_to_supabase(mockup_bytes, "widget-mockup-hires.png")

    # Insert into Google Doc
    print("\nInserting into Google Doc...")
    insert_images_into_doc([
        {
            "url": mockup_url,
            "caption": "Widget on a Medicare Agency Website",
            "aspect": 9 / 16,  # 16:9 -> H/W
        },
    ])

    print(f"\nDone! View the updated doc:")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    main()
