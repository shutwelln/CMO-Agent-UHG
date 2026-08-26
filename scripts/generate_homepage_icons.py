#!/usr/bin/env python3
"""Generate 4 How It Works icons via Gemini and insert into the homepage redesign Google Doc.

Usage:  python scripts/generate_homepage_icons.py
"""
from __future__ import annotations

import base64
import io
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

OUTPUT_DIR = ROOT / "data" / "saverwell" / "hero_options"
DOC_ID = "18ddUK7r4uKMLb77gFAA0NY2y_3uYfbYdDi_FGYtKeuU"
GEMINI_MODEL = "gemini-3.1-flash-image-preview"

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]

# Shared style preamble for all icon prompts
ICON_STYLE = (
    "Flat vector icon illustration on a plain white background. "
    "Clean, minimal, modern design. Exactly 3 colors: teal (#2A9D8F), "
    "gold/amber (#F4B942), and light teal (#E6F5F3). "
    "The icon sits centered inside a light teal (#E6F5F3) circle. "
    "Consistent 2px stroke weight throughout. No text, no labels, no words. "
    "No gradients, no 3D effects, no shadows. Flat design only. "
    "SVG-style crisp edges. Square composition. "
)

ICON_PROMPTS: List[Dict[str, str]] = [
    {
        "key": "icon_find_discounts",
        "label": "Find Discounts",
        "prompt": (
            ICON_STYLE
            + "A map location pin with a percent sign (%) inside it. "
            "The pin outline is teal (#2A9D8F) with 2px strokes. "
            "The percent symbol inside the pin is gold/amber (#F4B942). "
            "The pin sits centered inside a light teal (#E6F5F3) circle. "
            "Communicates 'local savings near you.' "
            "No text, no words, no labels anywhere in the image."
        ),
    },
    {
        "key": "icon_protect_savings",
        "label": "Protect Your Savings",
        "prompt": (
            ICON_STYLE
            + "A shield with a checkmark inside it. "
            "The shield outline is teal (#2A9D8F) with 2px strokes. "
            "The checkmark inside is also teal (#2A9D8F). "
            "The shield sits centered inside a light teal (#E6F5F3) circle. "
            "Communicates safety and trust. "
            "No text, no words, no labels anywhere in the image."
        ),
    },
    {
        "key": "icon_read_guides",
        "label": "Read Our Guides",
        "prompt": (
            ICON_STYLE
            + "An open book with a small lightbulb floating just above it. "
            "The book outline is teal (#2A9D8F) with 2px strokes. "
            "The lightbulb is gold/amber (#F4B942). "
            "Both sit centered inside a light teal (#E6F5F3) circle. "
            "Communicates knowledge and insight. "
            "No text, no words, no labels anywhere in the image."
        ),
    },
    {
        "key": "icon_store_directory",
        "label": "Browse Store Directory",
        "prompt": (
            ICON_STYLE
            + "A storefront icon (simple building facade with an awning) "
            "with a small 2x2 grid of four dots next to it or below it, "
            "representing a directory or catalog. "
            "The storefront outline is teal (#2A9D8F) with 2px strokes. "
            "The four dots are gold/amber (#F4B942). "
            "Both sit centered inside a light teal (#E6F5F3) circle. "
            "Communicates browsing a catalog of stores. "
            "No text, no words, no labels anywhere in the image."
        ),
    },
]


def generate_image(api_key: str, prompt: str, aspect_ratio: str = "1:1") -> bytes:
    """Call Gemini 3.1 Flash Image to generate an icon."""
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
    """Compress to JPEG if too large."""
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


def upload_to_supabase(image_bytes: bytes, filename: str) -> str:
    """Upload to Supabase and return public URL."""
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


def get_services():
    """Return (docs_service, drive_service)."""
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
    docs = build("docs", "v1", credentials=creds)
    return docs


def find_section_end(doc: Dict[str, Any], heading_text: str) -> int:
    """Find the end index of a section by its heading text.

    Returns the index just before the next heading of the same or higher level,
    or the document end.
    """
    body = doc.get("body", {}).get("content", [])
    found_heading = False
    heading_level = None

    for elem in body:
        para = elem.get("paragraph", {})
        style = para.get("paragraphStyle", {})
        named_style = style.get("namedStyleType", "")

        # Get text content of this paragraph
        text = ""
        for el in para.get("elements", []):
            text += el.get("textRun", {}).get("content", "")
        text = text.strip()

        if found_heading:
            # Check if we hit a heading of same or higher level
            if named_style.startswith("HEADING_"):
                try:
                    level = int(named_style.split("_")[1])
                    if level <= heading_level:
                        # Return start of this next section
                        return elem.get("startIndex", 1)
                except (ValueError, IndexError):
                    pass
        else:
            # Look for our target heading
            if heading_text in text and named_style.startswith("HEADING_"):
                found_heading = True
                try:
                    heading_level = int(named_style.split("_")[1])
                except (ValueError, IndexError):
                    heading_level = 1

    # If we found the heading but no next section, return doc end
    if body:
        return body[-1].get("endIndex", 1) - 1
    return 1


def insert_icons_into_doc(docs_service: Any, icon_entries: List[Dict[str, str]]) -> None:
    """Insert icon images into the Icon Descriptions section of the doc."""

    # Find the "Icon Descriptions" section
    doc = docs_service.documents().get(documentId=DOC_ID).execute()

    # We want to insert after the "Icon Descriptions" heading's content.
    # Find "Color Palette" section start - we'll insert between Color Palette and
    # Icon Descriptions. Actually, let's insert AFTER the Icon Descriptions numbered list.
    # Better approach: find the next H1 after "Icon Redesign Spec" and insert before it.

    # Find insertion point: right before "New Content Preview Sections" heading
    insert_before = find_section_end(doc, "Icon Redesign Spec")
    cursor = insert_before

    requests: List[Dict[str, Any]] = []

    # Add a sub-heading for the generated icons
    heading = "Generated Icon Previews\n"
    requests.append({"insertText": {"location": {"index": cursor}, "text": heading}})
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": cursor, "endIndex": cursor + len(heading)},
            "paragraphStyle": {
                "namedStyleType": "HEADING_2",
                "spaceAbove": {"magnitude": 10, "unit": "PT"},
                "spaceBelow": {"magnitude": 4, "unit": "PT"},
            },
            "fields": "namedStyleType,spaceAbove,spaceBelow",
        }
    })
    cursor += len(heading)

    intro = "Icons generated via Gemini. Use these as reference or export as SVG for production.\n"
    requests.append({"insertText": {"location": {"index": cursor}, "text": intro}})
    requests.append({
        "updateParagraphStyle": {
            "range": {"startIndex": cursor, "endIndex": cursor + len(intro)},
            "paragraphStyle": {
                "namedStyleType": "NORMAL_TEXT",
                "spaceBelow": {"magnitude": 6, "unit": "PT"},
            },
            "fields": "namedStyleType,spaceBelow",
        }
    })
    cursor += len(intro)

    # Flush heading + intro
    docs_service.documents().batchUpdate(
        documentId=DOC_ID, body={"requests": requests}
    ).execute()
    requests = []
    time.sleep(0.5)

    for entry in icon_entries:
        # Re-read doc for accurate cursor
        doc = docs_service.documents().get(documentId=DOC_ID).execute()
        body = doc.get("body", {}).get("content", [])

        # Find the cursor after our "Generated Icon Previews" section content
        # Use the last known position by scanning for our intro text
        # Simpler: just find end of doc after our last insert
        # We inserted heading + intro, now find cursor after those
        found = False
        for elem in body:
            para = elem.get("paragraph", {})
            for el in para.get("elements", []):
                text = el.get("textRun", {}).get("content", "")
                if "Icons generated via Gemini" in text:
                    cursor = elem.get("endIndex", 1)
                    found = True

        if not found:
            # Fallback: use the last element
            cursor = body[-1].get("endIndex", 1) - 1 if body else 1

        # Insert label
        label = entry["label"] + "\n"
        requests.append({"insertText": {"location": {"index": cursor}, "text": label}})
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": cursor, "endIndex": cursor + len(label)},
                "textStyle": {"bold": True},
                "fields": "bold",
            }
        })
        cursor += len(label)

        # Insert newline for image
        requests.append({"insertText": {"location": {"index": cursor}, "text": "\n"}})
        cursor += 1

        # Insert image (square, 120x120 pt)
        size_pt = 120
        requests.append({
            "insertInlineImage": {
                "location": {"index": cursor - 1},
                "uri": entry["url"],
                "objectSize": {
                    "width": {"magnitude": size_pt, "unit": "PT"},
                    "height": {"magnitude": size_pt, "unit": "PT"},
                },
            }
        })

        # Add CDN URL below
        cdn_line = f"\n{entry['url']}\n"
        # We need to flush the image first, then add the URL
        docs_service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": requests}
        ).execute()
        requests = []
        time.sleep(0.5)

        # Re-read and add CDN URL
        doc = docs_service.documents().get(documentId=DOC_ID).execute()
        body = doc.get("body", {}).get("content", [])
        cursor = body[-1].get("endIndex", 1) - 1 if body else 1

        # Find actual insertion point after the image we just inserted
        # Scan backwards from the section we're building in
        for elem in reversed(body):
            ei = elem.get("endIndex", 0)
            if ei > 0:
                cursor = ei - 1
                break

        requests.append({"insertText": {"location": {"index": cursor}, "text": cdn_line}})
        requests.append({
            "updateParagraphStyle": {
                "range": {"startIndex": cursor, "endIndex": cursor + len(cdn_line)},
                "paragraphStyle": {
                    "namedStyleType": "NORMAL_TEXT",
                    "spaceBelow": {"magnitude": 8, "unit": "PT"},
                },
                "fields": "namedStyleType,spaceBelow",
            }
        })
        requests.append({
            "updateTextStyle": {
                "range": {"startIndex": cursor, "endIndex": cursor + len(cdn_line)},
                "textStyle": {
                    "fontSize": {"magnitude": 8, "unit": "PT"},
                    "foregroundColor": {
                        "color": {"rgbColor": {"red": 0.42, "green": 0.45, "blue": 0.5}}
                    },
                },
                "fields": "fontSize,foregroundColor",
            }
        })

        docs_service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": requests}
        ).execute()
        requests = []
        time.sleep(0.5)
        print(f"  Inserted: {entry['label']}")

    if requests:
        docs_service.documents().batchUpdate(
            documentId=DOC_ID, body={"requests": requests}
        ).execute()


def main() -> None:
    from cmo_agent.config import Settings

    settings = Settings()
    api_key = settings.gemini_api_key
    if not api_key:
        raise RuntimeError("Missing GEMINI_API_KEY in .env")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print(f"Using model: {GEMINI_MODEL}")
    print()

    # ── Step 1: Generate icons ────────────────────────────────
    icon_entries: List[Dict[str, str]] = []

    for entry in ICON_PROMPTS:
        key = entry["key"]
        label = entry["label"]
        prompt = entry["prompt"]
        local_path = OUTPUT_DIR / f"{key}.png"

        print(f"[{label}]")

        if local_path.exists():
            print(f"  Using cached: {local_path}")
            img_bytes = local_path.read_bytes()
        else:
            print("  Generating icon...")
            img_bytes = generate_image(api_key, prompt, aspect_ratio="1:1")
            local_path.write_bytes(img_bytes)
            print(f"  Saved locally: {local_path} ({len(img_bytes):,} bytes)")

        # ── Step 2: Upload to Supabase ────────────────────────
        print("  Uploading to Supabase...")
        cdn_url = upload_to_supabase(img_bytes, f"{key}.png")
        icon_entries.append({"key": key, "label": label, "url": cdn_url})
        print()

    # ── Step 3: Insert into Google Doc ────────────────────────
    print("Initializing Google Docs API...")
    docs_svc = get_services()

    print("Inserting icons into document...")
    insert_icons_into_doc(docs_svc, icon_entries)

    print(f"\nDone! View the updated doc:")
    print(f"https://docs.google.com/document/d/{DOC_ID}/edit")


if __name__ == "__main__":
    main()
