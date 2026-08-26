#!/usr/bin/env python3
"""Generate widget visuals (Pillow) and insert them into the existing Google Doc.

Creates two images:
  1. Widget mockup - what the widget looks like on a partner's site
  2. Flow diagram - data flow from partner site to Customer.io

Uploads to Supabase storage, then appends to the Google Doc.

Usage:  python scripts/create_widget_visuals.py
"""
from __future__ import annotations

import io
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

FONT_DIR = ROOT / "data" / "fonts"
OUTPUT_DIR = ROOT / "data" / "saverwell"

# Colors
TEAL = (42, 157, 143)
WHITE = (255, 255, 255)
DARK_BG = (31, 41, 55)
LIGHT_GRAY = (243, 244, 246)
MED_GRAY = (156, 163, 175)
DARK_TEXT = (31, 41, 55)
BORDER = (229, 231, 235)
RED_BG = (254, 242, 242)
RED_TEXT = (153, 27, 27)
GREEN_TEXT = (5, 150, 105)
BLUE = (59, 130, 246)
ORANGE = (249, 115, 22)

DOC_ID = "1EA2Sq4RznL725RuU1oOVjPp8oxvpM_xgbTEu_UkP7NY"


def load_font(bold: bool = False, size: int = 14) -> ImageFont.FreeTypeFont:
    # Try bundled Inter fonts first
    name = "Inter-Bold.otf" if bold else "Inter-Regular.otf"
    path = FONT_DIR / name
    try:
        return ImageFont.truetype(str(path), size)
    except (OSError, IOError):
        pass
    # Fallback to system Helvetica (macOS) or Arial
    for fallback in [
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]:
        try:
            # For .ttc files, index 1 is bold
            idx = 1 if bold and fallback.endswith(".ttc") else 0
            return ImageFont.truetype(fallback, size, index=idx)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def rounded_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple,
    radius: int,
    fill=None,
    outline=None,
    width: int = 1,
):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)


def create_widget_mockup() -> Image.Image:
    """Create a visual mockup of the widget on a partner's website."""
    W, H = 900, 680
    img = Image.new("RGB", (W, H), (248, 250, 252))
    draw = ImageDraw.Draw(img)

    font_sm = load_font(size=11)
    font_md = load_font(size=13)
    font_lg = load_font(size=16)
    font_xl = load_font(bold=True, size=18)
    font_title = load_font(bold=True, size=14)
    font_tiny = load_font(size=10)

    # -- Partner website chrome --
    # Browser bar
    draw.rectangle([0, 0, W, 44], fill=(241, 245, 249))
    draw.rectangle([0, 44, W, 45], fill=BORDER)
    # Dots
    for i, c in enumerate([(239, 68, 68), (250, 204, 21), (34, 197, 94)]):
        draw.ellipse([16 + i * 22, 14, 30 + i * 22, 28], fill=c)
    # URL bar
    rounded_rect(draw, (100, 10, 700, 34), radius=6, fill=WHITE, outline=BORDER)
    draw.text((115, 14), "partnersfinancial.com/resources", fill=MED_GRAY, font=font_sm)

    # Partner site header
    draw.rectangle([0, 45, W, 95], fill=WHITE)
    draw.rectangle([0, 95, W, 96], fill=BORDER)
    draw.text((30, 58), "Partners Financial Group", fill=DARK_TEXT, font=font_xl)
    for i, tab in enumerate(["Home", "Services", "Resources", "Contact"]):
        draw.text((500 + i * 90, 63), tab, fill=MED_GRAY, font=font_md)

    # Partner content area
    draw.text((30, 115), "Resources for Our Clients", fill=DARK_TEXT, font=font_xl)
    draw.text(
        (30, 145),
        "We provide tools and resources to help you save money in retirement.",
        fill=MED_GRAY,
        font=font_md,
    )

    # -- Widget card --
    wx, wy = 30, 185
    ww, wh = 420, 460
    rounded_rect(draw, (wx, wy, wx + ww, wy + wh), radius=12, fill=WHITE, outline=BORDER, width=2)

    # Annotation arrow + label
    draw.text((480, 200), "Partners add one line:", fill=DARK_TEXT, font=font_title)
    # Code snippet background
    rounded_rect(draw, (480, 225, 870, 285), radius=8, fill=DARK_BG)
    draw.text(
        (495, 233),
        '<script src="...embed.js"',
        fill=(167, 243, 208),
        font=load_font(size=12),
    )
    draw.text(
        (495, 251),
        '  data-partner="partners-financial"',
        fill=(167, 243, 208),
        font=load_font(size=12),
    )
    draw.text(
        (495, 269),
        '  data-zip="85281"></script>',
        fill=(167, 243, 208),
        font=load_font(size=12),
    )

    # Arrow from code to widget
    draw.line([(475, 260), (455, 350)], fill=TEAL, width=2)
    draw.polygon([(455, 350), (450, 340), (460, 340)], fill=TEAL)

    # Widget header
    hx, hy = wx + 16, wy + 16
    # Tag icon (simple)
    draw.rectangle([hx, hy + 2, hx + 16, hy + 16], fill=TEAL)
    draw.text((hx + 24, hy - 2), "Senior Discounts Near Phoenix, AZ", fill=DARK_TEXT, font=font_title)

    # Merchant rows
    merchants = [
        ("K", "Kroger", "5% off every Wednesday, 60+", (34, 197, 94)),
        ("C", "CVS", "20% off first Tuesday of month", (59, 130, 246)),
        ("R", "Ross", "10% off every Tuesday, 55+", (168, 85, 247)),
        ("G", "Goodwill", "25% off every Wednesday, 55+", (249, 115, 22)),
        ("D", "Denny's", "15% off daily, 55+", (239, 68, 68)),
    ]

    my = hy + 30
    for initial, name, discount, color in merchants:
        # Logo circle
        draw.ellipse([hx, my, hx + 36, my + 36], fill=color)
        iw = draw.textlength(initial, font=load_font(bold=True, size=16))
        draw.text((hx + 18 - iw / 2, my + 6), initial, fill=WHITE, font=load_font(bold=True, size=16))
        # Name + discount
        draw.text((hx + 46, my + 2), name, fill=DARK_TEXT, font=font_title)
        draw.text((hx + 46, my + 20), discount, fill=TEAL, font=font_sm)
        # Separator
        if name != "Denny's":
            draw.line([(hx, my + 42), (wx + ww - 16, my + 42)], fill=LIGHT_GRAY, width=1)
        my += 48

    # See all CTA
    cta_y = my + 8
    draw.line([(wx, cta_y), (wx + ww, cta_y)], fill=LIGHT_GRAY, width=1)
    cta_text = "See all 47 discounts near you  \u2192"
    tw = draw.textlength(cta_text, font=load_font(bold=True, size=13))
    draw.text(
        (wx + ww / 2 - tw / 2, cta_y + 10),
        cta_text,
        fill=TEAL,
        font=load_font(bold=True, size=13),
    )

    # Email signup
    form_y = cta_y + 38
    draw.line([(wx, form_y), (wx + ww, form_y)], fill=LIGHT_GRAY, width=1)
    form_y += 12
    # Input
    rounded_rect(
        draw, (hx, form_y, hx + 250, form_y + 32), radius=6, fill=WHITE, outline=BORDER
    )
    draw.text((hx + 10, form_y + 7), "Get weekly savings alerts", fill=MED_GRAY, font=font_sm)
    # Button
    rounded_rect(
        draw, (hx + 258, form_y, hx + 378, form_y + 32), radius=6, fill=TEAL
    )
    tw2 = draw.textlength("Subscribe", font=load_font(bold=True, size=12))
    draw.text(
        (hx + 258 + 60 - tw2 / 2, form_y + 8),
        "Subscribe",
        fill=WHITE,
        font=load_font(bold=True, size=12),
    )

    # Protection alert
    alert_y = form_y + 44
    draw.line([(wx, alert_y), (wx + ww, alert_y)], fill=LIGHT_GRAY, width=1)
    rounded_rect(
        draw, (wx + 1, alert_y + 1, wx + ww - 1, alert_y + 32), radius=0, fill=RED_BG
    )
    draw.text(
        (hx, alert_y + 8),
        "\u26A0  New Medicare impostor calls targeting AZ seniors",
        fill=RED_TEXT,
        font=font_sm,
    )

    # Footer
    footer_y = alert_y + 34
    draw.line([(wx, footer_y), (wx + ww, footer_y)], fill=LIGHT_GRAY, width=1)
    pw = draw.textlength("Powered by Saverwell", font=font_tiny)
    draw.text(
        (wx + ww / 2 - pw / 2, footer_y + 8),
        "Powered by Saverwell",
        fill=MED_GRAY,
        font=font_tiny,
    )

    # Annotation: Shadow DOM
    draw.text((480, 320), "Shadow DOM", fill=DARK_TEXT, font=font_title)
    draw.text((480, 340), "CSS fully isolated from", fill=MED_GRAY, font=font_md)
    draw.text((480, 358), "partner's site styles", fill=MED_GRAY, font=font_md)

    # Annotation: UTM
    draw.text((480, 400), "All links stamped with:", fill=DARK_TEXT, font=font_title)
    rounded_rect(draw, (480, 422, 870, 500), radius=8, fill=DARK_BG)
    draw.text((495, 430), "utm_source=partner", fill=(167, 243, 208), font=load_font(size=12))
    draw.text((495, 448), "utm_campaign=partners-financial", fill=(167, 243, 208), font=load_font(size=12))
    draw.text((495, 466), "utm_medium=widget", fill=(167, 243, 208), font=load_font(size=12))
    draw.text((495, 484), "utm_content=discount_card", fill=(167, 243, 208), font=load_font(size=12))

    # Annotation: Themes
    draw.text((480, 520), "Light + Dark themes", fill=DARK_TEXT, font=font_title)
    draw.text((480, 540), "Responsive (works in sidebars)", fill=MED_GRAY, font=font_md)
    draw.text((480, 558), "~8 KB, zero dependencies", fill=MED_GRAY, font=font_md)

    return img


def create_flow_diagram() -> Image.Image:
    """Create a data flow diagram showing widget -> Saverwell -> Customer.io."""
    W, H = 900, 500
    img = Image.new("RGB", (W, H), WHITE)
    draw = ImageDraw.Draw(img)

    font_sm = load_font(size=11)
    font_md = load_font(size=13)
    font_title = load_font(bold=True, size=14)
    font_lg = load_font(bold=True, size=16)
    font_section = load_font(bold=True, size=12)

    # Title
    draw.text((30, 20), "Widget Data Flow", fill=DARK_TEXT, font=load_font(bold=True, size=22))
    draw.text((30, 48), "From partner install to co-branded email delivery", fill=MED_GRAY, font=font_md)

    # Boxes
    boxes = [
        (30, 90, 200, 200, "Partner's\nWebsite", (241, 245, 249), DARK_TEXT),
        (240, 90, 410, 200, "embed.js\n(Shadow DOM)", (236, 253, 245), TEAL),
        (450, 90, 620, 200, "Cloudflare\nWorker", (255, 247, 237), ORANGE),
        (660, 90, 870, 200, "Supabase\nDatabase", (239, 246, 255), BLUE),
    ]

    for x0, y0, x1, y1, label, bg, fg in boxes:
        rounded_rect(draw, (x0, y0, x1, y1), radius=10, fill=bg, outline=fg, width=2)
        lines = label.split("\n")
        for i, line in enumerate(lines):
            lw = draw.textlength(line, font=font_title)
            draw.text(
                ((x0 + x1) / 2 - lw / 2, y0 + 35 + i * 22),
                line,
                fill=fg,
                font=font_title,
            )

    # Arrows between boxes (top row)
    for x in [200, 410, 620]:
        draw.line([(x, 145), (x + 40, 145)], fill=MED_GRAY, width=2)
        draw.polygon([(x + 40, 145), (x + 32, 140), (x + 32, 150)], fill=MED_GRAY)

    # Sub-labels on arrows
    draw.text((205, 120), "loads script", fill=MED_GRAY, font=font_sm)
    draw.text((415, 120), "API calls", fill=MED_GRAY, font=font_sm)
    draw.text((625, 120), "queries", fill=MED_GRAY, font=font_sm)

    # Bottom row: subscribe flow
    bot_y = 280
    subscribe_boxes = [
        (30, bot_y, 200, bot_y + 110, "Visitor\nSubscribes", (241, 245, 249), DARK_TEXT),
        (240, bot_y, 410, bot_y + 110, "POST\n/api/subscribe", (236, 253, 245), TEAL),
        (450, bot_y, 620, bot_y + 110, "n8n Lifecycle\nWorkflow", (255, 247, 237), ORANGE),
        (660, bot_y, 870, bot_y + 110, "Customer.io\nCo-branded Email", (239, 246, 255), BLUE),
    ]

    for x0, y0, x1, y1, label, bg, fg in subscribe_boxes:
        rounded_rect(draw, (x0, y0, x1, y1), radius=10, fill=bg, outline=fg, width=2)
        lines = label.split("\n")
        for i, line in enumerate(lines):
            lw = draw.textlength(line, font=font_title)
            draw.text(
                ((x0 + x1) / 2 - lw / 2, y0 + 30 + i * 22),
                line,
                fill=fg,
                font=font_title,
            )

    # Arrows (bottom row)
    for x in [200, 410, 620]:
        draw.line([(x, bot_y + 55), (x + 40, bot_y + 55)], fill=MED_GRAY, width=2)
        draw.polygon(
            [(x + 40, bot_y + 55), (x + 32, bot_y + 50), (x + 32, bot_y + 60)],
            fill=MED_GRAY,
        )

    # Sub-labels on bottom arrows
    draw.text((205, bot_y + 30), "email + zip +", fill=MED_GRAY, font=font_sm)
    draw.text((205, bot_y + 43), "partner name", fill=MED_GRAY, font=font_sm)
    draw.text((415, bot_y + 30), "+ UTM fields", fill=MED_GRAY, font=font_sm)
    draw.text((415, bot_y + 43), "+ brand attr", fill=MED_GRAY, font=font_sm)
    draw.text((625, bot_y + 30), "brand =", fill=MED_GRAY, font=font_sm)
    draw.text((625, bot_y + 43), "partner name", fill=MED_GRAY, font=font_sm)

    # Section labels
    draw.text((30, 70), "DISCOUNT DISPLAY", fill=TEAL, font=font_section)
    draw.text((30, bot_y - 20), "EMAIL SIGNUP", fill=TEAL, font=font_section)

    # Vertical connector
    draw.line([(115, 200), (115, bot_y)], fill=BORDER, width=1)

    # Key takeaway at bottom
    ky = bot_y + 135
    rounded_rect(draw, (30, ky, 870, ky + 55), radius=8, fill=(236, 253, 245), outline=TEAL, width=1)
    draw.text(
        (50, ky + 8),
        "Key: The partner gets full attribution credit. Subscribers receive co-branded emails",
        fill=DARK_TEXT,
        font=font_title,
    )
    draw.text(
        (50, ky + 28),
        "showing both the partner's logo and Saverwell's logo. All powered by existing UTM pipeline.",
        fill=DARK_TEXT,
        font=font_md,
    )

    return img


def upload_to_supabase(img: Image.Image, filename: str) -> str:
    """Upload PIL image to Supabase storage and return public URL."""
    import httpx

    from cmo_agent.config import Settings

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    buf.seek(0)
    data = buf.read()

    bucket = "cmo-agent"
    path = f"widget-docs/{filename}"

    upload_url = f"{settings.supabase_url}/storage/v1/object/{bucket}/{path}"
    headers = {
        "apikey": settings.supabase_service_role_key,
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
        "Content-Type": "image/png",
        "x-upsert": "true",
    }

    resp = httpx.post(upload_url, headers=headers, content=data, timeout=30.0)
    if resp.status_code >= 400:
        print(f"Upload error {resp.status_code}: {resp.text}")
        resp.raise_for_status()

    public_url = f"{settings.supabase_url}/storage/v1/object/public/{bucket}/{path}"
    print(f"Uploaded: {public_url}")
    return public_url


def insert_images_into_doc(image_urls: List[Dict[str, str]]) -> None:
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
    heading_text = "Visual Overview\n"
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

    # Flush heading first (images need accurate cursor)
    docs.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": requests}
    ).execute()
    requests = []

    import time

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

        # Add a newline for the image
        requests.append({"insertText": {"location": {"index": cursor}, "text": "\n"}})
        cursor += 1

        # Insert image
        requests.append({
            "insertInlineImage": {
                "location": {"index": cursor - 1},
                "uri": entry["url"],
                "objectSize": {
                    "width": {"magnitude": 468, "unit": "PT"},
                    "height": {"magnitude": 468 * entry["aspect"], "unit": "PT"},
                },
            }
        })

        docs.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": requests}
        ).execute()
        requests = []
        print(f"Inserted: {entry['caption']}")

    print("Done inserting images.")


def main() -> None:
    print("Creating widget mockup...")
    mockup = create_widget_mockup()
    mockup_path = OUTPUT_DIR / "widget_mockup.png"
    mockup.save(str(mockup_path), "PNG")
    print(f"Saved locally: {mockup_path}")

    print("Creating flow diagram...")
    flow = create_flow_diagram()
    flow_path = OUTPUT_DIR / "widget_flow.png"
    flow.save(str(flow_path), "PNG")
    print(f"Saved locally: {flow_path}")

    print("\nUploading to Supabase...")
    mockup_url = upload_to_supabase(mockup, "widget-mockup.png")
    flow_url = upload_to_supabase(flow, "widget-flow.png")

    print("\nInserting into Google Doc...")
    insert_images_into_doc([
        {
            "url": flow_url,
            "caption": "How the Widget Works",
            "aspect": 500 / 900,  # H/W ratio
        },
        {
            "url": mockup_url,
            "caption": "Widget on a Partner's Website",
            "aspect": 680 / 900,  # H/W ratio
        },
    ])

    print(f"\nDone! View the updated doc:")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    main()
