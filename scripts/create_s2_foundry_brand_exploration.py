"""Create the S2 Foundry Brand Exploration Google Doc.

Presents color palette options, logo concepts, typography pairings,
and tagline candidates for Nick and Justin to review and select.
Generates palette swatch mockups and logo concepts via Gemini,
uploads to Supabase CDN, and embeds in the Google Doc.

Usage:
    python scripts/create_s2_foundry_brand_exploration.py
    python scripts/create_s2_foundry_brand_exploration.py --update DOC_ID
    python scripts/create_s2_foundry_brand_exploration.py --skip-images  # text only, no Gemini
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root / "src"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(project_root / ".env")


# ── Color palette definitions ─────────────────────────────────────────────

PALETTES = {
    "A": {
        "name": "Warm Forge",
        "vibe": (
            "Molten metal, premium craft, foundry metaphor. "
            "Amber and gold tones against dark stone, evoking the heat "
            "and precision of a forge. Feels premium, warm, intentional."
        ),
        "tokens": {
            "Primary": ("#F59E0B", "Amber - main brand color, CTAs, links"),
            "Accent": ("#EAB308", "Yellow - hover states, highlights, secondary CTAs"),
            "Background": ("#0C0A09", "Stone-950 - page background, deep dark base"),
            "Card": ("#1C1917", "Stone-900 - card surfaces, elevated containers"),
            "Text": ("#FAFAF9", "Stone-50 - primary text, headings"),
            "Muted": ("#A8A29E", "Stone-400 - secondary text, captions"),
            "Border": ("#292524", "Stone-800 - card borders, dividers"),
            "Glow": ("#F59E0B33", "Amber at 20% opacity - card hover glow, accent shadows"),
        },
    },
    "B": {
        "name": "Electric Emerald",
        "vibe": (
            "Growth, innovation, clean tech. Emerald and lime tones "
            "against cool zinc, evoking forward motion and fresh "
            "thinking. Feels modern, energetic, tech-forward."
        ),
        "tokens": {
            "Primary": ("#10B981", "Emerald - main brand color, CTAs, links"),
            "Accent": ("#84CC16", "Lime - hover states, highlights, secondary CTAs"),
            "Background": ("#09090B", "Zinc-950 - page background, deep dark base"),
            "Card": ("#18181B", "Zinc-900 - card surfaces, elevated containers"),
            "Text": ("#FAFAFA", "Zinc-50 - primary text, headings"),
            "Muted": ("#A1A1AA", "Zinc-400 - secondary text, captions"),
            "Border": ("#27272A", "Zinc-800 - card borders, dividers"),
            "Glow": ("#10B98133", "Emerald at 20% opacity - card hover glow, accent shadows"),
        },
    },
    "C": {
        "name": "Arctic Steel",
        "vibe": (
            "Precision, engineering, cold-forged. Indigo and sky blue "
            "against deep slate, evoking precision engineering and "
            "clarity. Feels sharp, technical, confident."
        ),
        "tokens": {
            "Primary": ("#6366F1", "Indigo - main brand color, CTAs, links"),
            "Accent": ("#38BDF8", "Sky blue - hover states, highlights, secondary CTAs"),
            "Background": ("#020617", "Slate-950 - page background, deep dark base"),
            "Card": ("#0F172A", "Slate-900 - card surfaces, elevated containers"),
            "Text": ("#F8FAFC", "Slate-50 - primary text, headings"),
            "Muted": ("#94A3B8", "Slate-400 - secondary text, captions"),
            "Border": ("#1E293B", "Slate-800 - card borders, dividers"),
            "Glow": ("#6366F133", "Indigo at 20% opacity - card hover glow, accent shadows"),
        },
    },
}

LOGO_DIRECTIONS = [
    {
        "id": 1,
        "name": "Geometric Monogram",
        "description": (
            '"S2" as interlocking geometric shapes. Minimal, modern, works '
            "at any size. Think: Stripe's \"S\", Square's tilted square. "
            "Clean lines, mathematical precision."
        ),
    },
    {
        "id": 2,
        "name": "Forge Mark",
        "description": (
            '"S2" incorporated into an anvil, hammer, or spark silhouette. '
            "Leans into the foundry metaphor literally. Industrial, bold, "
            "memorable."
        ),
    },
    {
        "id": 3,
        "name": "Circuit Letterform",
        "description": (
            '"S2" with circuit-board traces or node connections built into '
            "the letterforms. Technical, AI-forward, detailed but clean."
        ),
    },
    {
        "id": 4,
        "name": "Negative Space",
        "description": (
            '"S2" created through negative space or cutouts in a solid shape. '
            "Clever, memorable, premium. The mark rewards a second look."
        ),
    },
    {
        "id": 5,
        "name": "Type-Only Wordmark",
        "description": (
            '"S2 FOUNDRY" as a custom wordmark with distinctive letter '
            "treatment (no icon). Clean, confident, lets the name speak. "
            "Works everywhere without needing a separate icon."
        ),
    },
]

TYPOGRAPHY_OPTIONS = [
    {
        "option": "A",
        "headings": "Inter",
        "body": "Inter",
        "description": (
            "Geometric, clean, widely loved in tech. One font family "
            "for everything, relying on weight contrast (Bold headings, "
            "Regular body) for hierarchy. Simple to implement, always readable."
        ),
    },
    {
        "option": "B",
        "headings": "Space Grotesk",
        "body": "Inter",
        "description": (
            "More distinctive headings with a tech-forward feel. Space Grotesk "
            "has slightly more character than Inter while staying geometric. "
            "Good contrast between heading and body."
        ),
    },
    {
        "option": "C",
        "headings": "Outfit",
        "body": "Inter",
        "description": (
            "Modern, slightly rounded, friendly-tech vibe. Outfit adds warmth "
            "to headings without losing professionalism. Approachable but still "
            "technical."
        ),
    },
]

TAGLINES = [
    (
        "We build what's next.",
        "Broad, forward-looking, ambitious. Works across products and services.",
    ),
    (
        "AI products, forged to ship.",
        "Leans into the foundry metaphor. Emphasizes shipping over theorizing.",
    ),
    (
        "From idea to product. Fast.",
        "Direct, action-oriented. Communicates speed and full-stack capability.",
    ),
    (
        "Build. Automate. Launch.",
        "Three words, three pillars. Punchy, scannable, maps to the service offering.",
    ),
    (
        "Your AI product team.",
        "Positions S2 Foundry as an extension of the client's team. Relationship-focused.",
    ),
]


# ── Document structure builder ─────────────────────────────────────────────

def build_document_structure(image_urls: dict | None = None) -> dict:
    """Build the Brand Exploration document structure.

    image_urls is a dict with keys like:
        palette_A, palette_B, palette_C
        logo_1a, logo_1b, logo_2a, logo_2b, etc.
    """
    if image_urls is None:
        image_urls = {}

    sections = []

    # ── Header ────────────────────────────────────────────────────────────
    sections.append({
        "heading": "",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "S2 Foundry - Brand Exploration",
            },
            {
                "type": "paragraph",
                "text": (
                    "This document presents brand identity options for S2 Foundry, LLC. "
                    "Review each section and note your selections. Once selections are "
                    "confirmed, we proceed to website build and brand guidelines."
                ),
            },
        ],
    })

    # ── Section 1: Brand Positioning ──────────────────────────────────────
    sections.append({
        "heading": "1. Brand Positioning",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "What S2 Foundry Is",
            },
            {
                "type": "paragraph",
                "text": (
                    "S2 Foundry is a B2B AI product studio and consultancy. "
                    "We build AI-powered products end-to-end, automate business "
                    "workflows with AI agents, and execute go-to-market for "
                    "product launches."
                ),
            },
            {
                "type": "paragraph",
                "text": "Who We Serve",
            },
            {
                "type": "bullets",
                "items": [
                    "Companies that need AI products built "
                    "(startups, scale-ups, enterprise innovation teams)",
                    "Businesses with manual workflows ripe for AI automation",
                    "Founders who need GTM execution alongside product development",
                ],
            },
            {
                "type": "paragraph",
                "text": "How We're Different",
            },
            {
                "type": "bullets",
                "items": [
                    "Builds AND strategizes. Most agencies do one or the other.",
                    "Founder-led, AI-native. We use AI to build AI products.",
                    "Ships fast. Strategy without code is a deck. We do both.",
                ],
            },
            {
                "type": "paragraph",
                "text": "Relationship to Agent Tunnel",
            },
            {
                "type": "paragraph",
                "text": (
                    "Agent Tunnel is S2 Foundry's first product, not its only product. "
                    "It demonstrates our process and capabilities. Future products will "
                    "be built under the S2 Foundry umbrella with the same approach."
                ),
            },
        ],
    })

    # ── Section 2: Color Palettes ─────────────────────────────────────────
    palette_content = [
        {
            "type": "paragraph",
            "text": (
                "Three color palette options, each designed for a dark-theme website. "
                "Each includes primary, accent, background, card, text, muted, border, "
                "and glow tokens. Select one palette to carry through the entire brand."
            ),
        },
    ]

    for key, palette in PALETTES.items():
        palette_content.append({
            "type": "paragraph",
            "text": f"Option {key}: {palette['name']}",
        })
        palette_content.append({
            "type": "paragraph",
            "text": palette["vibe"],
        })
        palette_content.append({
            "type": "table",
            "headers": ["Token", "Hex", "Usage"],
            "rows": [
                [token, hex_val, usage]
                for token, (hex_val, usage) in palette["tokens"].items()
            ],
        })

        img_key = f"palette_{key}"
        if img_key in image_urls:
            palette_content.append({
                "type": "image",
                "url": image_urls[img_key],
                "width": 500,
                "height": 300,
            })

        palette_content.append({
            "type": "paragraph",
            "text": "",
        })

    sections.append({
        "heading": "2. Color Palette Options",
        "level": 1,
        "content": palette_content,
    })

    # ── Section 3: Logo Concepts ──────────────────────────────────────────
    logo_content = [
        {
            "type": "paragraph",
            "text": (
                "Five distinct creative directions for the S2 Foundry logo. "
                "Each direction has 2-3 generated variants. Select one direction, "
                "then we refine the chosen concept into final logo files."
            ),
        },
    ]

    for direction in LOGO_DIRECTIONS:
        logo_content.append({
            "type": "paragraph",
            "text": f"Direction {direction['id']}: {direction['name']}",
        })
        logo_content.append({
            "type": "paragraph",
            "text": direction["description"],
        })

        # Add any generated logo images for this direction
        for variant in ["a", "b", "c"]:
            img_key = f"logo_{direction['id']}{variant}"
            if img_key in image_urls:
                logo_content.append({
                    "type": "image",
                    "url": image_urls[img_key],
                    "width": 400,
                    "height": 400,
                })

        logo_content.append({
            "type": "paragraph",
            "text": "",
        })

    sections.append({
        "heading": "3. Logo Concepts",
        "level": 1,
        "content": logo_content,
    })

    # ── Section 4: Typography ─────────────────────────────────────────────
    typo_content = [
        {
            "type": "paragraph",
            "text": (
                "Three font pairing options. All use Google Fonts for easy "
                "web implementation. Select one pairing for headings and body text."
            ),
        },
    ]

    for opt in TYPOGRAPHY_OPTIONS:
        typo_content.append({
            "type": "paragraph",
            "text": f"Option {opt['option']}: {opt['headings']} + {opt['body']}",
        })
        typo_content.append({
            "type": "table",
            "headers": ["Role", "Font", "Weight"],
            "rows": [
                ["Headings", opt["headings"], "600-700 (Semi-Bold to Bold)"],
                ["Body", opt["body"], "400 (Regular)"],
                ["Captions/Labels", opt["body"], "500 (Medium)"],
            ],
        })
        typo_content.append({
            "type": "paragraph",
            "text": opt["description"],
        })

    sections.append({
        "heading": "4. Typography Options",
        "level": 1,
        "content": typo_content,
    })

    # ── Section 5: Tagline Options ────────────────────────────────────────
    tagline_content = [
        {
            "type": "paragraph",
            "text": (
                "Five tagline candidates for the hero section and brand usage. "
                "Select one (or propose a modification)."
            ),
        },
        {
            "type": "table",
            "headers": ["#", "Tagline", "Notes"],
            "rows": [
                [str(i + 1), tagline, notes]
                for i, (tagline, notes) in enumerate(TAGLINES)
            ],
        },
    ]

    sections.append({
        "heading": "5. Tagline Options",
        "level": 1,
        "content": tagline_content,
    })

    # ── Section 6: Next Steps ─────────────────────────────────────────────
    sections.append({
        "heading": "6. Your Selections",
        "level": 1,
        "content": [
            {
                "type": "paragraph",
                "text": "Fill in your selections below:",
            },
            {
                "type": "bullets",
                "items": [
                    "Color Palette: _____ (A / B / C)",
                    "Logo Direction: _____ (1 / 2 / 3 / 4 / 5)",
                    "Typography: _____ (A / B / C)",
                    "Tagline: _____ (1 / 2 / 3 / 4 / 5 / custom)",
                ],
            },
            {
                "type": "paragraph",
                "text": "Once selections are confirmed, next steps:",
            },
            {
                "type": "numbered_list",
                "items": [
                    "Refine selected logo into final variants "
                    "(icon, wordmark, horizontal, vertical)",
                    "Generate service icons, OG image, favicon in selected palette",
                    "Build the s2foundry.com static website with selected brand identity",
                    "Wire up contact form to n8n workflow (Google Sheet + Slack notification)",
                    "Deploy to Hostinger and enable SSL",
                    "Create brand guidelines Google Doc",
                ],
            },
        ],
    })

    return {
        "title": "S2 Foundry - Brand Exploration",
        "sections": sections,
    }


# ── Image generation via Gemini generateContent API ───────────────────────

GEMINI_MODEL = "gemini-2.0-flash-exp-image-generation"


async def _call_gemini_image(prompt: str) -> bytes | None:
    """Call Gemini generateContent API for image generation.

    Uses the same REST API pattern as the visual agent.
    """
    import base64

    import httpx

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("  WARN: No GEMINI_API_KEY set")
        return None

    url = (
        f"https://generativelanguage.googleapis.com/v1beta"
        f"/models/{GEMINI_MODEL}:generateContent"
    )

    max_retries = 3
    for attempt in range(max_retries):
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                params={"key": api_key},
                json={
                    "contents": [
                        {"parts": [{"text": prompt}]},
                    ],
                    "generationConfig": {
                        "responseModalities": ["IMAGE", "TEXT"],
                    },
                },
            )
            if resp.status_code == 429:
                wait = 15 * (attempt + 1)
                print(f"  Rate limited, waiting {wait}s...")
                await asyncio.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()

            candidates = data.get("candidates", [])
            for candidate in candidates:
                parts = (
                    candidate.get("content", {}).get("parts", [])
                )
                for part in parts:
                    inline_data = part.get("inlineData")
                    if inline_data and inline_data.get(
                        "mimeType", ""
                    ).startswith("image/"):
                        return base64.b64decode(
                            inline_data["data"]
                        )

    return None


async def generate_palette_swatch(
    palette_key: str, palette: dict
) -> bytes | None:
    """Generate a palette swatch mockup image via Gemini."""
    try:
        tokens = palette["tokens"]
        primary = tokens["Primary"][0]
        accent = tokens["Accent"][0]
        bg = tokens["Background"][0]
        card = tokens["Card"][0]
        text_color = tokens["Text"][0]
        muted = tokens["Muted"][0]

        prompt = (
            f"Create a dark-themed UI mockup for a tech company website. "
            f"Show a hero section with a navigation bar and a services "
            f"card grid. Use EXACTLY these colors: background {bg}, "
            f"card surfaces {card}, primary accent {primary}, secondary "
            f"accent {accent}, heading text {text_color}, body text "
            f"{muted}. The cards should have subtle glow effects in the "
            f"primary color. Modern, clean, minimal design. "
            f"No readable text, use placeholder lines instead. "
            f"The mockup should feel like a real website screenshot."
        )

        return await _call_gemini_image(prompt)
    except Exception as e:
        print(f"  ERROR generating palette {palette_key}: {e}")
        return None


async def generate_logo_concept(
    direction: dict, palette: dict, variant: str
) -> bytes | None:
    """Generate a logo concept image via Gemini."""
    try:
        primary = palette["tokens"]["Primary"][0]
        accent = palette["tokens"]["Accent"][0]
        style_variants = {
            "a": "on a dark background, bold and prominent",
            "b": "on a white background, clean and minimal",
            "c": "on dark background with subtle gradient glow",
        }
        style = style_variants.get(variant, style_variants["a"])

        prompt = (
            f"Design a professional logo for 'S2 Foundry', an AI "
            f"product studio. Creative direction: {direction['name']} "
            f"- {direction['description']} Use the colors {primary} "
            f"and {accent} as the main logo colors. Present the logo "
            f"{style}. The logo should be clean, modern, and scalable. "
            f"Professional brand identity quality. Square format, "
            f"centered composition, generous whitespace around the mark."
        )

        return await _call_gemini_image(prompt)
    except Exception as e:
        print(
            f"  ERROR generating logo "
            f"{direction['id']}{variant}: {e}"
        )
        return None


async def upload_image(image_bytes: bytes, filename: str) -> str | None:
    """Upload image bytes directly to Supabase Storage."""
    import httpx

    supabase_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    bucket = "cmo-agent"

    if not supabase_url or not supabase_key:
        print("  WARN: Supabase not configured, skipping upload")
        return None

    try:
        storage_path = f"s2_foundry/brand_exploration/{filename}"
        upload_url = (
            f"{supabase_url}/storage/v1/object/{bucket}/{storage_path}"
        )
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                upload_url,
                headers={
                    "Authorization": f"Bearer {supabase_key}",
                    "Content-Type": "image/png",
                    "x-upsert": "true",
                },
                content=image_bytes,
            )
            if resp.status_code >= 400:
                print(f"  Supabase response: {resp.text[:200]}")
            resp.raise_for_status()

        public_url = (
            f"{supabase_url}/storage/v1/object/public"
            f"/{bucket}/{storage_path}"
        )
        return public_url
    except Exception as e:
        print(f"  ERROR uploading {filename}: {e}")
        return None


async def generate_all_images() -> dict:
    """Generate all palette swatches and logo concepts, upload to CDN."""
    image_urls = {}

    # Use palette A (Warm Forge) as the default for logo generation
    # All palettes get their own swatch mockup
    default_palette = PALETTES["A"]

    print("\n--- Generating palette swatch mockups ---")
    for key, palette in PALETTES.items():
        print(f"  Generating palette {key}: {palette['name']}...")
        img_bytes = await generate_palette_swatch(key, palette)
        if img_bytes:
            url = await upload_image(img_bytes, f"palette_{key}.png")
            if url:
                image_urls[f"palette_{key}"] = url
                print(f"  Uploaded palette {key}: {url}")
        await asyncio.sleep(5)  # Rate limit buffer

    print("\n--- Generating logo concepts ---")
    for direction in LOGO_DIRECTIONS:
        for variant in ["a", "b"]:
            key = f"logo_{direction['id']}{variant}"
            print(
                f"  Generating {key}: "
                f"{direction['name']} (variant {variant})..."
            )
            img_bytes = await generate_logo_concept(
                direction, default_palette, variant
            )
            if img_bytes:
                url = await upload_image(img_bytes, f"{key}.png")
                if url:
                    image_urls[key] = url
                    print(f"  Uploaded {key}: {url}")
            await asyncio.sleep(5)  # Rate limit buffer

    print(f"\n--- Generated {len(image_urls)} images total ---")
    return image_urls


# ── Render content into Google Doc ─────────────────────────────────────────

def _render_content(docs_service, doc_id: str, sections: list) -> None:
    """Render sections into the Google Doc body."""
    requests = []
    cursor = 1

    def _heading_style(level: int) -> str:
        mapping = {
            1: "HEADING_1",
            2: "HEADING_2",
            3: "HEADING_3",
            4: "HEADING_4",
        }
        return mapping.get(level, "HEADING_1")

    for section in sections:
        heading = section.get("heading", "")
        level = section.get("level", 1)
        content_blocks = section.get("content", [])

        if heading:
            heading_text = heading + "\n"
            requests.append(
                {
                    "insertText": {
                        "location": {"index": cursor},
                        "text": heading_text,
                    }
                }
            )
            h_start = cursor
            h_end = cursor + len(heading_text)
            requests.append(
                {
                    "updateParagraphStyle": {
                        "range": {
                            "startIndex": h_start,
                            "endIndex": h_end,
                        },
                        "paragraphStyle": {
                            "namedStyleType": _heading_style(level),
                            "spaceAbove": {"magnitude": 12, "unit": "PT"},
                            "spaceBelow": {"magnitude": 4, "unit": "PT"},
                        },
                        "fields": "namedStyleType,spaceAbove,spaceBelow",
                    }
                }
            )
            cursor = h_end

        for block in content_blocks:
            block_type = block.get("type", "paragraph")

            if block_type == "paragraph":
                text = block.get("text", "")
                if not text and text != "":
                    continue
                if text == "":
                    text = " "
                para_text = text + "\n"
                requests.append(
                    {
                        "insertText": {
                            "location": {"index": cursor},
                            "text": para_text,
                        }
                    }
                )
                p_start = cursor
                p_end = cursor + len(para_text)
                requests.append(
                    {
                        "updateParagraphStyle": {
                            "range": {
                                "startIndex": p_start,
                                "endIndex": p_end,
                            },
                            "paragraphStyle": {
                                "namedStyleType": "NORMAL_TEXT",
                                "spaceBelow": {
                                    "magnitude": 6,
                                    "unit": "PT",
                                },
                            },
                            "fields": "namedStyleType,spaceBelow",
                        }
                    }
                )
                cursor = p_end

            elif block_type in ("bullets", "numbered_list"):
                items = block.get("items", [])
                if not items:
                    continue
                list_start = cursor
                for item in items:
                    item_text = str(item) + "\n"
                    requests.append(
                        {
                            "insertText": {
                                "location": {"index": cursor},
                                "text": item_text,
                            }
                        }
                    )
                    cursor += len(item_text)
                list_end = cursor
                preset = (
                    "BULLET_DISC_CIRCLE_SQUARE"
                    if block_type == "bullets"
                    else "NUMBERED_DECIMAL_NESTED"
                )
                requests.append(
                    {
                        "createParagraphBullets": {
                            "range": {
                                "startIndex": list_start,
                                "endIndex": list_end,
                            },
                            "bulletPreset": preset,
                        }
                    }
                )

            elif block_type == "image":
                # Flush pending requests before inserting image
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []

                url = block.get("url", "")
                width = block.get("width", 400)
                height = block.get("height", 300)

                if url:
                    # Insert a newline, then the image
                    docs_service.documents().batchUpdate(
                        documentId=doc_id,
                        body={
                            "requests": [
                                {
                                    "insertText": {
                                        "location": {"index": cursor},
                                        "text": "\n",
                                    }
                                }
                            ]
                        },
                    ).execute()
                    cursor += 1

                    docs_service.documents().batchUpdate(
                        documentId=doc_id,
                        body={
                            "requests": [
                                {
                                    "insertInlineImage": {
                                        "location": {"index": cursor},
                                        "uri": url,
                                        "objectSize": {
                                            "width": {
                                                "magnitude": width,
                                                "unit": "PT",
                                            },
                                            "height": {
                                                "magnitude": height,
                                                "unit": "PT",
                                            },
                                        },
                                    }
                                }
                            ]
                        },
                    ).execute()
                    cursor += 1  # inline image occupies 1 index

                    # Re-read cursor position after image insert
                    doc_state = (
                        docs_service.documents()
                        .get(documentId=doc_id)
                        .execute()
                    )
                    body_content = doc_state.get("body", {}).get("content", [])
                    if body_content:
                        cursor = body_content[-1].get("endIndex", cursor) - 1

            elif block_type == "table":
                t_headers = block.get("headers", [])
                t_rows = block.get("rows", [])
                if not t_headers:
                    continue
                num_cols = len(t_headers)
                num_rows = 1 + len(t_rows)

                requests.append(
                    {
                        "insertTable": {
                            "rows": num_rows,
                            "columns": num_cols,
                            "location": {"index": cursor},
                        }
                    }
                )
                if requests:
                    docs_service.documents().batchUpdate(
                        documentId=doc_id, body={"requests": requests}
                    ).execute()
                    requests = []

                doc_state = (
                    docs_service.documents()
                    .get(documentId=doc_id)
                    .execute()
                )
                table_element = None
                for elem in doc_state.get("body", {}).get("content", []):
                    if "table" in elem:
                        table_element = elem

                if table_element:
                    table = table_element["table"]
                    all_table_rows = [t_headers] + t_rows
                    cell_inserts = []
                    for ri, row_data in enumerate(all_table_rows):
                        if ri >= len(table.get("tableRows", [])):
                            break
                        table_row = table["tableRows"][ri]
                        for ci, cell_val in enumerate(row_data):
                            if ci >= len(
                                table_row.get("tableCells", [])
                            ):
                                break
                            cell = table_row["tableCells"][ci]
                            cell_content = cell.get("content", [])
                            if cell_content:
                                cell_idx = cell_content[0].get(
                                    "startIndex", 0
                                )
                                cell_text = str(cell_val)
                                if cell_text:
                                    cell_inserts.append(
                                        (cell_idx, cell_text)
                                    )

                    cell_inserts.sort(
                        key=lambda x: x[0], reverse=True
                    )
                    for cell_idx, cell_text in cell_inserts:
                        requests.append(
                            {
                                "insertText": {
                                    "location": {"index": cell_idx},
                                    "text": cell_text,
                                }
                            }
                        )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id,
                            body={"requests": requests},
                        ).execute()
                        requests = []

                    # Bold header row
                    doc_state2 = (
                        docs_service.documents()
                        .get(documentId=doc_id)
                        .execute()
                    )
                    table_elem2 = None
                    for elem in doc_state2.get("body", {}).get(
                        "content", []
                    ):
                        if "table" in elem:
                            table_elem2 = elem
                    if table_elem2 and table_elem2["table"].get(
                        "tableRows"
                    ):
                        header_row = table_elem2["table"]["tableRows"][0]
                        for hcell in header_row.get("tableCells", []):
                            for para in hcell.get("content", []):
                                si = para.get("startIndex", 0)
                                ei = para.get("endIndex", si)
                                if ei > si:
                                    requests.append(
                                        {
                                            "updateTextStyle": {
                                                "range": {
                                                    "startIndex": si,
                                                    "endIndex": ei,
                                                },
                                                "textStyle": {
                                                    "bold": True
                                                },
                                                "fields": "bold",
                                            }
                                        }
                                    )
                    if requests:
                        docs_service.documents().batchUpdate(
                            documentId=doc_id,
                            body={"requests": requests},
                        ).execute()
                        requests = []

                doc_state = (
                    docs_service.documents()
                    .get(documentId=doc_id)
                    .execute()
                )
                body_content = doc_state.get("body", {}).get(
                    "content", []
                )
                if body_content:
                    last_elem = body_content[-1]
                    cursor = last_elem.get("endIndex", cursor) - 1
                requests.append(
                    {
                        "insertText": {
                            "location": {"index": cursor},
                            "text": "\n",
                        }
                    }
                )
                cursor += 1

    if requests:
        docs_service.documents().batchUpdate(
            documentId=doc_id, body={"requests": requests}
        ).execute()


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    """Create or update the Brand Exploration Google Doc."""
    parser = argparse.ArgumentParser(
        description="Create S2 Foundry Brand Exploration Google Doc"
    )
    parser.add_argument(
        "--update",
        metavar="DOC_ID",
        help="Update an existing Google Doc instead of creating new",
    )
    parser.add_argument(
        "--skip-images",
        action="store_true",
        help="Skip Gemini image generation (text-only doc)",
    )
    args = parser.parse_args()

    from cmo_agent.agents.docs import _normalize_sections
    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
        share_file_restricted,
    )

    oauth_path = (
        "/Users/nickshutwell/Desktop/CMO Agent"
        "/data/google-token.json"
    )
    scopes = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive",
    ]
    credentials = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path="",
        scopes=scopes,
    )
    if credentials is None:
        print("ERROR: Could not load Google credentials.")
        sys.exit(1)

    from googleapiclient.discovery import build

    docs_service = build("docs", "v1", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    # Generate images if not skipped
    image_urls = {}
    if not args.skip_images:
        print("Generating brand exploration images via Gemini...")
        image_urls = asyncio.run(generate_all_images())
    else:
        print("Skipping image generation (--skip-images)")

    structure = build_document_structure(image_urls)
    title = structure["title"]
    sections = _normalize_sections(structure, skip_toc=False)

    if args.update:
        doc_id = args.update
        print(f"\nUpdating existing Google Doc: {doc_id}")
        print(f"Sections: {len(sections)}")

        doc = docs_service.documents().get(documentId=doc_id).execute()
        body_content = doc.get("body", {}).get("content", [])
        if body_content:
            end_index = body_content[-1].get("endIndex", 2) - 1
            if end_index > 1:
                docs_service.documents().batchUpdate(
                    documentId=doc_id,
                    body={
                        "requests": [
                            {
                                "deleteContentRange": {
                                    "range": {
                                        "startIndex": 1,
                                        "endIndex": end_index,
                                    }
                                }
                            }
                        ]
                    },
                ).execute()
                print("Cleared existing content")

        _render_content(docs_service, doc_id, sections)

        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print("\nGoogle Doc updated successfully!")
        print(f"URL: {docs_url}")

    else:
        print(f"\nBuilding Google Doc: {title}")
        print(f"Sections: {len(sections)}")

        doc = (
            docs_service.documents()
            .create(body={"title": title})
            .execute()
        )
        doc_id = doc["documentId"]
        print(f"Document created: {doc_id}")

        _render_content(docs_service, doc_id, sections)

        share_file_restricted(drive_service, doc_id)

        folder_id = ensure_drive_folder(drive_service)
        if folder_id:
            move_file_to_folder(drive_service, doc_id, folder_id)

        docs_url = f"https://docs.google.com/document/d/{doc_id}/edit"
        print("\nGoogle Doc created successfully!")
        print(f"URL: {docs_url}")


if __name__ == "__main__":
    main()
