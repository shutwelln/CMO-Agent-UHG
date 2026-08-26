#!/usr/bin/env python3
"""Head-to-head test: DALL-E 3 HD vs Imagen 4 vs Gemini 2.5 Flash.

Generates 1 guide image and 1 protection image from each provider (6 total),
saves them to /tmp/thumbnail_test/ for visual comparison.

Usage:
    python scripts/test_thumbnail_providers.py

Requires:
    OPENAI_API_KEY  — for DALL-E 3
    GOOGLE_API_KEY  — for Imagen 4 and Gemini 2.5 Flash
    pip install httpx Pillow google-genai
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import time
from pathlib import Path

import httpx

OUTPUT_DIR = Path("/tmp/thumbnail_test")
TARGET_WIDTH = 1200
TARGET_HEIGHT = 630

# ── Test prompts ────────────────────────────────────────────────────────────

GUIDE_PROMPT = (
    "Editorial photograph shot on a Nikon D850 with 85mm f/1.4 lens. A 68-year-old "
    "woman with silver-gray hair sits at a light wood kitchen table, reading a "
    "printed document through tortoiseshell reading glasses. She wears a cream "
    "linen blouse. Morning sunlight streams through a window to her left. A white "
    "ceramic coffee mug sits nearby. Background: soft-focus kitchen shelves with a "
    "small potted herb plant and a teal (#2A9D8F) decorative bowl. Natural skin "
    "texture with visible pores and subtle laugh lines. Calm, focused expression. "
    "No airbrushed or synthetic appearance. No text, no words, no letters, no "
    "logos, no watermarks, no overlays."
)

PROTECTION_PROMPT = (
    "Editorial photograph shot on a Canon EOS R5 with 50mm f/1.8 lens. A 70-year-old "
    "woman with gray hair in a soft bun sits in a comfortable armchair, holding a "
    "cordless phone slightly away from her ear with a cautious, thoughtful "
    "expression. She wears a cozy rust-orange cardigan. A notepad and pen sit on "
    "the armrest. Warm afternoon light from a nearby window. Background: a tidy "
    "living room with a bookshelf and a teal (#2A9D8F) ceramic vase with dried "
    "flowers. Natural skin, natural wrinkles, authentic cautious expression. No "
    "text, no words, no letters, no logos, no watermarks, no overlays."
)

TEST_CASES = [
    ("guide", GUIDE_PROMPT),
    ("protection", PROTECTION_PROMPT),
]


# ── Image conversion ───────────────────────────────────────────────────────


def convert_to_webp(raw_bytes: bytes) -> bytes:
    """Resize to 1200x630 and convert to WebP."""
    from PIL import Image

    img = Image.open(io.BytesIO(raw_bytes))
    if img.mode == "RGBA":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[3])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    img = img.resize((TARGET_WIDTH, TARGET_HEIGHT), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=85, method=4)
    return buf.getvalue()


# ── Provider: DALL-E 3 HD ──────────────────────────────────────────────────


async def generate_dalle(api_key: str, prompt: str) -> bytes:
    """Generate via DALL-E 3 HD, return raw image bytes."""
    no_text_prefix = "Generate a purely visual image with no text, letters, or words. "
    async with httpx.AsyncClient(timeout=120.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/images/generations",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "dall-e-3",
                "prompt": no_text_prefix + prompt,
                "n": 1,
                "size": "1792x1024",
                "quality": "hd",
                "style": "natural",
            },
        )
        resp.raise_for_status()
        image_url = resp.json()["data"][0]["url"]

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(image_url)
        resp.raise_for_status()
        return resp.content


# ── Provider: Imagen 4 ─────────────────────────────────────────────────────


def generate_imagen4(api_key: str, prompt: str) -> bytes:
    """Generate via Imagen 4, return raw image bytes."""
    from google import genai

    client = genai.Client(api_key=api_key)
    no_text_prefix = "Generate a purely visual image with no text, letters, or words. "
    response = client.models.generate_images(
        model="imagen-4.0-generate-001",
        prompt=no_text_prefix + prompt,
        config=genai.types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="16:9",
            person_generation="allow_adult",
        ),
    )
    if not response.generated_images:
        raise RuntimeError("Imagen 4 returned no images")
    return response.generated_images[0].image.image_bytes


# ── Provider: Gemini 2.5 Flash ─────────────────────────────────────────────


def generate_gemini(api_key: str, prompt: str) -> bytes:
    """Generate via Gemini 2.5 Flash native image generation, return raw image bytes."""
    from google import genai

    client = genai.Client(api_key=api_key)
    no_text_prefix = "Generate a purely visual image with no text, letters, or words. "
    response = client.models.generate_content(
        model="gemini-3-pro-image-preview",
        contents=no_text_prefix + prompt,
        config=genai.types.GenerateContentConfig(
            response_modalities=["IMAGE"],
        ),
    )
    # Extract image bytes from response parts
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return part.inline_data.data
    raise RuntimeError("Gemini returned no image data")


# ── Main ───────────────────────────────────────────────────────────────────


async def main() -> None:
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    google_key = os.environ.get("GEMINI_API_KEY", "")

    if not openai_key:
        print("WARNING: OPENAI_API_KEY not set — skipping DALL-E 3")
    if not google_key:
        print("WARNING: GEMINI_API_KEY not set — skipping Imagen 4 and Gemini")

    if not openai_key and not google_key:
        print("ERROR: Set at least one API key.")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results: list[tuple[str, str, int, float]] = []  # (provider, slug, size_kb, elapsed)

    for slug, prompt in TEST_CASES:
        # DALL-E 3 HD
        if openai_key:
            print(f"\n→ DALL-E 3 HD: {slug}...")
            t0 = time.time()
            try:
                raw = await generate_dalle(openai_key, prompt)
                webp = convert_to_webp(raw)
                path = OUTPUT_DIR / f"dalle_{slug}.webp"
                path.write_bytes(webp)
                elapsed = time.time() - t0
                results.append(("dalle", slug, len(webp) // 1024, round(elapsed, 1)))
                print(f"  ✓ {path} ({len(webp) // 1024} KB, {elapsed:.1f}s)")
            except Exception as e:
                print(f"  ✗ DALL-E failed: {e}")

        # Imagen 4
        if google_key:
            print(f"\n→ Imagen 4: {slug}...")
            t0 = time.time()
            try:
                raw = generate_imagen4(google_key, prompt)
                webp = convert_to_webp(raw)
                path = OUTPUT_DIR / f"imagen4_{slug}.webp"
                path.write_bytes(webp)
                elapsed = time.time() - t0
                results.append(("imagen4", slug, len(webp) // 1024, round(elapsed, 1)))
                print(f"  ✓ {path} ({len(webp) // 1024} KB, {elapsed:.1f}s)")
            except Exception as e:
                print(f"  ✗ Imagen 4 failed: {e}")

        # Gemini 2.5 Flash
        if google_key:
            print(f"\n→ Gemini 2.5 Flash: {slug}...")
            t0 = time.time()
            try:
                raw = generate_gemini(google_key, prompt)
                webp = convert_to_webp(raw)
                path = OUTPUT_DIR / f"gemini_{slug}.webp"
                path.write_bytes(webp)
                elapsed = time.time() - t0
                results.append(("gemini", slug, len(webp) // 1024, round(elapsed, 1)))
                print(f"  ✓ {path} ({len(webp) // 1024} KB, {elapsed:.1f}s)")
            except Exception as e:
                print(f"  ✗ Gemini failed: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"{'Provider':<12} {'Slug':<14} {'Size (KB)':<12} {'Time (s)':<10}")
    print("-" * 48)
    for provider, slug, size_kb, elapsed in results:
        print(f"{provider:<12} {slug:<14} {size_kb:<12} {elapsed:<10}")
    print(f"\nImages saved to: {OUTPUT_DIR}")
    print("Open them side-by-side to pick the winner.")


if __name__ == "__main__":
    asyncio.run(main())
