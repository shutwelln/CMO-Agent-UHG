#!/usr/bin/env python3
"""Generate hero image options and create a Google Doc with the full Saverwell homepage redesign spec.

Steps:
  1. Generate 3 hero images via Gemini 3.1 Flash Image API (16:9, 2K, textless)
  2. Upload to Supabase CDN at hero-options/
  3. Create a Google Doc with images inline, section specs, and a complete Lovable prompt

Usage:  python scripts/create_homepage_redesign_doc.py
"""
from __future__ import annotations

import base64
import io
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUTPUT_DIR = ROOT / "data" / "saverwell" / "hero_options"
GEMINI_MODEL = "gemini-3.1-flash-image-preview"

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

DOC_TITLE = "Saverwell Homepage Redesign - March 2026"

# ── Hero image prompts ────────────────────────────────────────────────

HERO_PROMPTS: List[Dict[str, str]] = [
    {
        "key": "hero_option_a",
        "label": "Option A - Couple reviewing finances at home",
        "prompt": (
            "Editorial lifestyle photograph. A couple in their mid-60s sitting at a "
            "bright kitchen table on a relaxed morning. Warm, golden morning light "
            "streams through a window behind them. A laptop or tablet is open on the "
            "table. Both are dressed casually but neatly, smiling naturally. "
            "The entire left third of the frame is clear negative space (soft "
            "out-of-focus wall or window) suitable for text overlay. "
            "Warm neutral tones, muted earth palette. Shot on a 50mm lens with "
            "shallow depth of field. No text, no logos, no watermarks, no overlays. "
            "Photorealistic, high resolution, editorial photography style."
        ),
    },
    {
        "key": "hero_option_b",
        "label": "Option B - Person shopping at a retail store",
        "prompt": (
            "Editorial lifestyle photograph. A woman in her early 60s browsing a "
            "well-lit retail store aisle with a small shopping basket. She has a "
            "natural, relaxed smile. The store is clean and modern with soft overhead "
            "lighting. The left third of the frame is clear negative space (blurred "
            "shelving or neutral wall) suitable for text overlay. "
            "Warm tones, moderate saturation, approachable and relatable mood. "
            "Shot on a 35mm lens, slight depth of field blur on background. "
            "No text, no logos, no watermarks, no overlays. "
            "Photorealistic, high resolution, editorial photography style."
        ),
    },
    {
        "key": "hero_option_c",
        "label": "Option C - Close-up, modern editorial feel",
        "prompt": (
            "Tight editorial close-up photograph. Hands of a person in their 60s "
            "holding a smartphone, reviewing something on the screen. A coffee cup "
            "sits slightly out of focus on the table nearby. Warm golden-hour side "
            "lighting with soft shadows. Strong negative space on the left side of "
            "the frame (blurred neutral background). "
            "Shallow depth of field, warm color temperature, modern editorial "
            "aesthetic. No text, no logos, no watermarks, no overlays. "
            "Photorealistic, high resolution."
        ),
    },
]

# ── Gemini image generation ───────────────────────────────────────────


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
    if img.mode == "RGBA":
        bg = PILImage.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90, optimize=True)
    result = buf.getvalue()
    print(f"  Compressed {len(image_bytes):,} -> {len(result):,} bytes (JPEG)")
    return result


# ── Supabase upload ───────────────────────────────────────────────────


def upload_to_supabase(image_bytes: bytes, filename: str) -> str:
    """Upload image bytes to Supabase Storage and return the public URL."""
    from cmo_agent.config import Settings

    settings = Settings()
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY")

    data = compress_png(image_bytes)
    content_type = "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/png"
    if content_type == "image/jpeg":
        filename = filename.rsplit(".", 1)[0] + ".jpg"

    bucket = "cmo-agent"
    path = f"hero-options/{filename}"

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
                print(f"  Upload error {resp.status_code}: {resp.text}")
                resp.raise_for_status()
            break
        except (httpx.WriteTimeout, httpx.ReadError) as e:
            if attempt < 2:
                print(f"  Upload attempt {attempt + 1} failed ({e}), retrying...")
                time.sleep(2)
            else:
                raise

    public_url = f"{settings.supabase_url}/storage/v1/object/public/{bucket}/{path}"
    print(f"  Uploaded: {public_url}")
    return public_url


# ── Google Auth ───────────────────────────────────────────────────────


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
    """Parse **bold** and *italic* markers. Returns (plain_text, [(start, end, style)])."""
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


# ── Document content ──────────────────────────────────────────────────
# IMAGE_URLS is populated at runtime after generation + upload.


def build_sections(image_urls: Dict[str, str]) -> List[Dict[str, Any]]:
    """Return the full document structure with image URLs injected."""
    return [
        # ── 1. Context ────────────────────────────────────────
        {
            "heading": "Context",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "This document contains the complete homepage redesign spec for "
                        "saverwell.com. It addresses six issues identified in a UX audit: "
                        "no hero CTA, poor text contrast on the hero image, inconsistent "
                        "How It Works icons, a stock photo that does not match the target "
                        "demographic, no content previews showcasing the depth of "
                        "Protection/Guide articles, and no social proof."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": (
                        "The site is built on Lovable (React/Tailwind/Supabase). All "
                        "changes are delivered as a Lovable prompt at the bottom of this "
                        "document. Hero images were generated via Gemini and uploaded to "
                        "the Supabase CDN."
                    ),
                },
            ],
        },
        # ── 2. Hero Image Options ─────────────────────────────
        {
            "heading": "Hero Image Options",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Three hero image options are shown below. All are 16:9, 2K "
                        "resolution, textless, with negative space on the left third for "
                        "headline overlay. Pick one and update the Lovable prompt with its URL."
                    ),
                },
            ],
        },
        {
            "heading": "Option A - Couple reviewing finances at home",
            "level": 2,
            "content": [
                {
                    "type": "image",
                    "url": image_urls.get("hero_option_a", ""),
                    "width_pt": 468,
                    "aspect": 9 / 16,
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Two people in their mid-60s at a kitchen table, warm morning "
                        "light, laptop visible. Editorial photography feel with warm neutrals."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": f"CDN URL: {image_urls.get('hero_option_a', 'N/A')}",
                },
            ],
        },
        {
            "heading": "Option B - Person shopping at a retail store",
            "level": 2,
            "content": [
                {
                    "type": "image",
                    "url": image_urls.get("hero_option_b", ""),
                    "width_pt": 468,
                    "aspect": 9 / 16,
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Person in their 60s browsing a retail aisle. Natural smile, warm "
                        "tones, relatable and approachable."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": f"CDN URL: {image_urls.get('hero_option_b', 'N/A')}",
                },
            ],
        },
        {
            "heading": "Option C - Close-up, modern editorial",
            "level": 2,
            "content": [
                {
                    "type": "image",
                    "url": image_urls.get("hero_option_c", ""),
                    "width_pt": 468,
                    "aspect": 9 / 16,
                },
                {
                    "type": "paragraph",
                    "text": (
                        "Tight crop of hands holding a smartphone. Shallow depth of "
                        "field, golden-hour lighting, modern editorial aesthetic."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": f"CDN URL: {image_urls.get('hero_option_c', 'N/A')}",
                },
            ],
        },
        # ── 3. Hero Section Spec ──────────────────────────────
        {
            "heading": "Hero Section Spec",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "The hero needs a dark gradient overlay for WCAG AA contrast, "
                        "an updated subheadline, a stats bar, and a CTA button."
                    ),
                },
            ],
        },
        {
            "heading": "Gradient Overlay",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "CSS: background: linear-gradient(to right, rgba(42,47,53,0.85) 0%, rgba(42,47,53,0.6) 50%, transparent 100%)",
                        "Base color: Charcoal #2A2F35",
                        "Left edge 85% opacity, fading to transparent on the right",
                        "Ensures white text passes WCAG AA on any hero photo",
                    ],
                },
            ],
        },
        {
            "heading": "Copy",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        'H1 (keep as-is): "Save more. Stay protected."',
                        'Subheadline (new): "166+ verified senior discounts, fraud protection alerts, and free expert guides. Built for adults 55 and up."',
                    ],
                },
            ],
        },
        {
            "heading": "Stats Bar",
            "level": 2,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "A horizontal row of three proof points below the subheadline, "
                        "separated by thin vertical dividers:"
                    ),
                },
                {
                    "type": "bullets",
                    "items": [
                        '"166+ verified stores" | "20+ free guides" | "100% free, forever"',
                        "Text: white, font-size 0.95rem, font-weight 500",
                        "Dividers: rgba(255,255,255,0.3), 1px wide, 20px tall",
                        "Margin: mt-4 below subheadline",
                    ],
                },
            ],
        },
        {
            "heading": "CTA Button",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        'Label: "Subscribe Free"',
                        "Background: Gold #F4B942, text: Charcoal #2A2F35, font-weight 700",
                        "Padding: px-8 py-3, rounded-lg",
                        "Hover: brightness 110%, subtle shadow",
                        'Behavior: smooth-scroll to id="subscribe" (the email signup section)',
                        "Margin: mt-6 below stats bar",
                        "Rationale: CTA is conversion (subscribe), not navigation. The four How It Works cards below handle navigation.",
                    ],
                },
            ],
        },
        # ── 4. Icon Redesign Spec ─────────────────────────────
        {
            "heading": "Icon Redesign Spec - How It Works",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Replace the current inconsistent icons with custom flat SVG "
                        "illustrations. All icons use the same visual language: 3 colors "
                        "max, consistent 2px stroke weight, set inside an 80x80px light "
                        "teal circle (#E6F5F3)."
                    ),
                },
            ],
        },
        {
            "heading": "Color Palette",
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "Primary stroke/fill: Teal #2A9D8F",
                        "Accent: Gold #F4B942",
                        "Background circle: Light Teal #E6F5F3",
                        "Warm Gray (subtle fills): #F5F6F7",
                    ],
                },
            ],
        },
        {
            "heading": "Icon Descriptions",
            "level": 2,
            "content": [
                {
                    "type": "numbered_list",
                    "items": [
                        'Find Discounts - Map pin with a "%" symbol inside. Teal pin outline, gold % symbol. Communicates "local savings near you."',
                        "Protect Your Savings - Shield with a checkmark inside. Teal shield outline and checkmark stroke. Communicates safety and trust.",
                        "Read Our Guides - Open book with a small lightbulb floating above. Teal book outline, gold lightbulb. Communicates knowledge and insight.",
                        "Browse Store Directory - Storefront icon with a small grid of dots (representing a directory). Teal storefront, gold dots. Communicates browsing a catalog.",
                    ],
                },
            ],
        },
        # ── 5. New Sections Spec ──────────────────────────────
        {
            "heading": "New Content Preview Sections",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Two new sections showcase the depth of Saverwell's content library. "
                        "Both pull live data from Supabase so they stay current automatically."
                    ),
                },
            ],
        },
        {
            "heading": '"Stay Protected" Section',
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        'Section heading: "Stay Protected"',
                        'Subheading: "Tips to keep your money and identity safe."',
                        "Layout: 4 cards in a horizontal row (responsive grid, 1 col on mobile)",
                        "Each card: article title, 2-line excerpt, category badge, link to full article",
                        "Data source: Supabase protection_articles table, ordered by published_at DESC, limit 4, status = published",
                        '"View All" link at bottom-right, links to /protection',
                        "Card style: match the existing Protection page card design (white bg, subtle shadow, rounded-lg)",
                        "GA4 event: fire sectionView with section=stay_protected via IntersectionObserver when section enters viewport",
                    ],
                },
            ],
        },
        {
            "heading": '"Expert Guides" Section',
            "level": 2,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        'Section heading: "Expert Guides"',
                        'Subheading: "Free, in-depth guides on Medicare, insurance, and more."',
                        "Layout: 4 cards in a horizontal row (responsive grid, 1 col on mobile)",
                        "Each card: guide title, 2-line excerpt, category badge, link to full guide",
                        "Data source: Supabase guide_articles table, ordered by published_at DESC, limit 4, status = published",
                        '"View All" link at bottom-right, links to /guides',
                        "Card style: match the existing Guides page card design",
                        "GA4 event: fire sectionView with section=expert_guides via IntersectionObserver when section enters viewport",
                    ],
                },
            ],
        },
        # ── 6. Updated Section Order ──────────────────────────
        {
            "heading": "Updated Section Order",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": "The final homepage layout from top to bottom:",
                },
                {
                    "type": "numbered_list",
                    "items": [
                        "Nav (unchanged)",
                        "Hero (updated: gradient overlay, new subheadline, stats bar, CTA button)",
                        "How It Works (updated: new custom SVG icons)",
                        "Popular Senior Discounts (unchanged)",
                        "Stay Protected (NEW - 4 latest protection articles)",
                        "Expert Guides (NEW - 4 latest guide articles)",
                        'Email Signup CTA (add id="subscribe" so hero CTA scrolls here)',
                        "Footer (unchanged)",
                    ],
                },
            ],
        },
        # ── 7. Complete Lovable Prompt ────────────────────────
        {
            "heading": "Complete Lovable Prompt",
            "level": 1,
            "content": [
                {
                    "type": "paragraph",
                    "text": (
                        "Copy everything below and paste it into the Lovable chat. "
                        "Replace CHOSEN_HERO_URL with the CDN URL of the hero image "
                        "you picked from the options above."
                    ),
                },
                {
                    "type": "paragraph",
                    "text": "---",
                },
                {
                    "type": "paragraph",
                    "text": _build_lovable_prompt(),
                },
                {
                    "type": "paragraph",
                    "text": "---",
                },
            ],
        },
        # ── 8. Verification Checklist ─────────────────────────
        {
            "heading": "Verification Checklist",
            "level": 1,
            "content": [
                {
                    "type": "bullets",
                    "items": [
                        "Hero: gradient overlay renders, white text is readable on all hero options",
                        "Hero: stats bar shows with dividers, responsive on mobile",
                        'Hero: "Subscribe Free" button scrolls to the email signup section',
                        "Icons: all 4 are visually consistent (same size, stroke, palette)",
                        "Stay Protected: 4 cards load from Supabase, link to correct articles",
                        "Expert Guides: 4 cards load from Supabase, link to correct guides",
                        "Section order matches the spec above",
                        "GA4: sectionView events fire for Stay Protected and Expert Guides",
                        "Mobile: all new sections stack properly on small screens",
                        "Lighthouse: no regression in performance score",
                    ],
                },
            ],
        },
    ]


def _build_lovable_prompt() -> str:
    """Return the full Lovable prompt as a single string."""
    return (
        "I need to make several updates to the Saverwell homepage. Here is the full spec.\n\n"
        "1. HERO SECTION UPDATES\n\n"
        "Replace the current hero background image with this URL: CHOSEN_HERO_URL\n\n"
        "Add a dark gradient overlay on top of the hero image using this CSS:\n"
        "background: linear-gradient(to right, rgba(42,47,53,0.85) 0%, rgba(42,47,53,0.6) 50%, transparent 100%)\n\n"
        'Keep the H1 text "Save more. Stay protected." in white.\n\n'
        "Replace the current subheadline with:\n"
        '"166+ verified senior discounts, fraud protection alerts, and free expert guides. '
        'Built for adults 55 and up."\n\n'
        "Below the subheadline, add a stats bar - a horizontal row of three items separated "
        "by thin vertical dividers:\n"
        '- "166+ verified stores"\n'
        '- "20+ free guides"\n'
        '- "100% free, forever"\n'
        "Style: white text, font-size 0.95rem, font-weight 500. Dividers are "
        "rgba(255,255,255,0.3), 1px wide, 20px tall. Add mt-4 margin above.\n\n"
        'Below the stats bar, add a CTA button labeled "Subscribe Free". '
        "Style: background #F4B942 (gold), text color #2A2F35 (charcoal), font-weight 700, "
        "px-8 py-3, rounded-lg. On hover: brightness 110% with a subtle shadow. "
        'The button should smooth-scroll to the element with id="subscribe". Add mt-6 margin above.\n\n'
        "2. HOW IT WORKS ICONS\n\n"
        "Replace the current How It Works icons with custom inline SVGs. Each icon sits inside "
        "an 80x80px circle with background #E6F5F3. All icons use 2px stroke weight.\n\n"
        'Icon 1 (Find Discounts): A map pin with a "%" symbol inside. Pin outline in #2A9D8F (teal), '
        "% symbol in #F4B942 (gold).\n"
        "Icon 2 (Protect Your Savings): A shield with a checkmark inside. Both in #2A9D8F (teal).\n"
        "Icon 3 (Read Our Guides): An open book with a small lightbulb floating above. "
        "Book outline in #2A9D8F (teal), lightbulb in #F4B942 (gold).\n"
        "Icon 4 (Browse Store Directory): A storefront icon with a small 2x2 grid of dots "
        "(representing a directory). Storefront in #2A9D8F (teal), dots in #F4B942 (gold).\n\n"
        "3. NEW SECTION: STAY PROTECTED\n\n"
        "Add a new section after Popular Senior Discounts. "
        'Section heading: "Stay Protected". '
        'Subheading: "Tips to keep your money and identity safe."\n\n'
        "Display 4 cards in a horizontal row (responsive: 2 cols on tablet, 1 col on mobile). "
        "Each card shows: article title, a 2-line text excerpt (truncated with ellipsis), "
        "a category badge, and a link to the full article.\n\n"
        "Data source: query the protection_articles table from Supabase, "
        "ordered by published_at DESC, limit 4, where status = 'published'. "
        "Card style: white background, subtle shadow (shadow-sm), rounded-lg, "
        "matching the card style on the /protection page.\n\n"
        'Add a "View All" link at the bottom-right that links to /protection.\n\n'
        "Add a GA4 event: when this section enters the viewport (via IntersectionObserver), "
        "fire: window.dataLayer.push({ event: 'sectionView', section: 'stay_protected' })\n\n"
        "4. NEW SECTION: EXPERT GUIDES\n\n"
        "Add a new section after Stay Protected. "
        'Section heading: "Expert Guides". '
        'Subheading: "Free, in-depth guides on Medicare, insurance, and more."\n\n'
        "Display 4 cards in a horizontal row (responsive: 2 cols on tablet, 1 col on mobile). "
        "Each card shows: guide title, a 2-line text excerpt, "
        "a category badge, and a link to the full guide.\n\n"
        "Data source: query the guide_articles table from Supabase, "
        "ordered by published_at DESC, limit 4, where status = 'published'. "
        "Card style: white background, subtle shadow, rounded-lg, "
        "matching the card style on the /guides page.\n\n"
        '"View All" link at the bottom-right, links to /guides.\n\n'
        "Add a GA4 event: when this section enters the viewport, "
        "fire: window.dataLayer.push({ event: 'sectionView', section: 'expert_guides' })\n\n"
        "5. EMAIL SIGNUP SECTION\n\n"
        'Add id="subscribe" to the existing email signup / CTA section so the hero button '
        "can smooth-scroll to it. Do not change anything else about this section.\n\n"
        "6. FINAL SECTION ORDER\n\n"
        "The homepage sections from top to bottom should be:\n"
        "1. Nav (unchanged)\n"
        "2. Hero (updated per above)\n"
        "3. How It Works (updated icons)\n"
        "4. Popular Senior Discounts (unchanged)\n"
        "5. Stay Protected (new)\n"
        "6. Expert Guides (new)\n"
        "7. Email Signup CTA (add id=\"subscribe\")\n"
        "8. Footer (unchanged)\n\n"
        "Make sure all new sections are responsive and look good on mobile. "
        "Do not change any other existing sections or components."
    )


# ── Doc builder ───────────────────────────────────────────────────────


def heading_style(level: int) -> str:
    return f"HEADING_{min(level, 6)}"


def build_doc(
    docs_service: Any,
    drive_service: Any,
    image_urls: Dict[str, str],
) -> str:
    """Create the Google Doc, populate it, share it. Returns the URL."""

    doc = docs_service.documents().create(body={"title": DOC_TITLE}).execute()
    doc_id = doc["documentId"]
    print(f"Created document: {doc_id}")

    sections = build_sections(image_urls)
    requests: List[Dict[str, Any]] = []
    cursor = 1

    for section in sections:
        h = section.get("heading", "")
        lvl = section.get("level", 1)
        blocks = section.get("content", [])

        # ── Section heading ───────────────────────────────────
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

            elif btype == "image":
                # Flush pending requests before inserting image
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []
                    time.sleep(0.5)

                # Re-read doc for accurate cursor
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                body_content = doc_state.get("body", {}).get("content", [])
                cursor = (
                    body_content[-1].get("endIndex", cursor + 1) - 1
                    if body_content
                    else cursor
                )

                url = block.get("url", "")
                if not url:
                    # Skip if no URL (image generation failed)
                    continue

                # Insert a newline for the image
                requests.append(
                    {"insertText": {"location": {"index": cursor}, "text": "\n"}}
                )
                cursor += 1

                width_pt = block.get("width_pt", 468)
                aspect = block.get("aspect", 9 / 16)
                height_pt = width_pt * aspect

                requests.append({
                    "insertInlineImage": {
                        "location": {"index": cursor - 1},
                        "uri": url,
                        "objectSize": {
                            "width": {"magnitude": width_pt, "unit": "PT"},
                            "height": {"magnitude": height_pt, "unit": "PT"},
                        },
                    }
                })

                # Flush image insert
                docs_service.documents().batchUpdate(
                    documentId=doc_id, body={"requests": requests}
                ).execute()
                requests = []
                time.sleep(0.5)

                # Re-read for accurate cursor after image
                doc_state = docs_service.documents().get(documentId=doc_id).execute()
                body_content = doc_state.get("body", {}).get("content", [])
                cursor = (
                    body_content[-1].get("endIndex", cursor + 1) - 1
                    if body_content
                    else cursor
                )

    # Flush remaining requests
    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()

    # Share + move to CMO Agent folder
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        move_file_to_folder,
        share_file_restricted,
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


# ── Main ──────────────────────────────────────────────────────────────


def main() -> None:
    from cmo_agent.config import Settings

    settings = Settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Using model: {GEMINI_MODEL}")
    print()

    # ── Step 1: Generate hero images ──────────────────────────
    image_urls: Dict[str, str] = {}

    for entry in HERO_PROMPTS:
        key = entry["key"]
        label = entry["label"]
        prompt = entry["prompt"]
        local_path = OUTPUT_DIR / f"{key}.png"

        print(f"[{label}]")

        if local_path.exists():
            print(f"  Using cached: {local_path}")
            img_bytes = local_path.read_bytes()
        else:
            print("  Generating image...")
            img_bytes = generate_image(api_key, prompt, aspect_ratio="16:9")
            local_path.write_bytes(img_bytes)
            print(f"  Saved locally: {local_path} ({len(img_bytes):,} bytes)")

        # ── Step 2: Upload to Supabase ────────────────────────
        print("  Uploading to Supabase...")
        cdn_url = upload_to_supabase(img_bytes, f"{key}.png")
        image_urls[key] = cdn_url
        print()

    # ── Step 3: Create Google Doc ─────────────────────────────
    print("Initializing Google services...")
    docs_svc, drive_svc = get_services()

    print("Building document...")
    doc_url = build_doc(docs_svc, drive_svc, image_urls)

    print("\nDone! Document created:")
    print(doc_url)


if __name__ == "__main__":
    main()
