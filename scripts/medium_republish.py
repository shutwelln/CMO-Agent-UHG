#!/usr/bin/env python3
"""Format guide articles for Medium republishing.

Reads published articles from Supabase and converts them to
Medium-optimized markdown with canonical tags, saved to data/medium/ready/.

Usage:
    python scripts/medium_republish.py                          # all articles
    python scripts/medium_republish.py --limit 10
    python scripts/medium_republish.py --slug medicare-explained-simple-guide
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from pathlib import Path
from typing import Any, Dict, List

import httpx
import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402

logger = structlog.get_logger()

OUTPUT_DIR = _PROJECT_ROOT / "data" / "medium" / "ready"


async def fetch_articles(
    settings: Settings,
    slug: str = "",
    limit: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch published guide articles from Supabase."""
    params: Dict[str, str] = {
        "select": "slug,title,subtitle,overview_md,key_takeaways_md,"
        "body_md,savings_tips_md,watch_out_md,faq_md,seo_keywords,tags,reading_minutes",
        "publish_web": "eq.true",
        "order": "slug",
    }
    if slug:
        params["slug"] = f"eq.{slug}"
    if limit:
        params["limit"] = str(limit)

    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(
            f"{settings.supabase_url}/rest/v1/guide_articles",
            headers={
                "apikey": settings.supabase_service_role_key,
                "Authorization": f"Bearer {settings.supabase_service_role_key}",
            },
            params=params,
        )
        resp.raise_for_status()
        return resp.json()


def format_for_medium(article: Dict[str, Any]) -> str:
    """Convert a guide article to Medium-optimized markdown.

    Adds:
    - Engaging intro hook (not just the overview)
    - Canonical URL tag
    - Clean formatting (no raw HTML)
    - Source attribution
    - CTA at the end
    """
    slug = article.get("slug", "")
    title = article.get("title", "")
    subtitle = article.get("subtitle", "")
    overview = article.get("overview_md", "") or ""
    key_takeaways = article.get("key_takeaways_md", "") or ""
    body = article.get("body_md", "") or ""
    savings_tips = article.get("savings_tips_md", "") or ""
    watch_out = article.get("watch_out_md", "") or ""
    faq = article.get("faq_md", "") or ""
    reading_minutes = article.get("reading_minutes", 5)
    tags = article.get("tags", []) or []
    keywords = article.get("seo_keywords", []) or []

    canonical_url = f"https://saverwell.com/guides/{slug}"
    utm_url = f"{canonical_url}?utm_source=medium&utm_medium=article&utm_campaign={slug}"

    # Build Medium-formatted article
    parts: List[str] = []

    # Title and subtitle
    parts.append(f"# {title}")
    if subtitle:
        parts.append(f"*{subtitle}*")
    parts.append("")

    # Canonical tag (Medium supports this in import)
    parts.append(f"> Originally published at [Saverwell]({canonical_url})")
    parts.append("")

    # Reading time
    parts.append(f"*{reading_minutes} min read*")
    parts.append("")

    # Overview as intro
    parts.append(overview)
    parts.append("")

    # Key takeaways
    if key_takeaways:
        parts.append("## Key Takeaways")
        parts.append(key_takeaways)
        parts.append("")

    # Main body
    if body:
        # Clean up body for Medium (remove any HTML, fix heading levels)
        cleaned_body = _clean_for_medium(body)
        parts.append(cleaned_body)
        parts.append("")

    # Savings tips
    if savings_tips:
        parts.append("## How to Save Money")
        parts.append(savings_tips)
        parts.append("")

    # Watch out
    if watch_out:
        parts.append("## Watch Out For")
        parts.append(watch_out)
        parts.append("")

    # FAQ
    if faq:
        parts.append("## Frequently Asked Questions")
        parts.append(faq)
        parts.append("")

    # CTA
    parts.append("---")
    parts.append("")
    parts.append(
        f"*This guide is part of the [Saverwell]({utm_url}) library "
        "helping seniors save money and stay safe. "
        "Visit us for more free guides on Medicare, insurance, "
        "retirement finances, and fraud protection.*"
    )
    parts.append("")

    # Tags for Medium
    if tags:
        tag_line = " ".join(f"#{t.replace('-', '').replace(' ', '')}" for t in tags[:5])
        parts.append(tag_line)

    return "\n".join(parts)


def _clean_for_medium(text: str) -> str:
    """Clean markdown for Medium compatibility."""
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)

    # Ensure heading levels start at ## (# is the title)
    text = re.sub(r"^# ", "## ", text, flags=re.MULTILINE)

    # Remove excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)

    return text.strip()


async def main() -> None:
    parser = argparse.ArgumentParser(description="Format articles for Medium")
    parser.add_argument("--slug", type=str, default="", help="Single article slug")
    parser.add_argument("--limit", type=int, default=0, help="Max articles to process")
    args = parser.parse_args()

    settings = Settings()

    if not settings.supabase_url:
        print("ERROR: SUPABASE_URL required")
        sys.exit(1)

    # Fetch articles
    articles = await fetch_articles(settings, slug=args.slug, limit=args.limit)
    print(f"Found {len(articles)} articles")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Skip articles that already have Medium drafts
    to_process = []
    for art in articles:
        out_path = OUTPUT_DIR / f"{art['slug']}.md"
        if out_path.exists():
            print(f"  Skipping {art['slug']} (already formatted)")
            continue
        to_process.append(art)

    print(f"Articles to format: {len(to_process)}")
    if not to_process:
        print("Nothing to do.")
        return

    formatted = 0
    for i, art in enumerate(to_process, 1):
        slug = art["slug"]
        print(f"[{i}/{len(to_process)}] {slug}")

        try:
            md = format_for_medium(art)
            out_path = OUTPUT_DIR / f"{slug}.md"
            out_path.write_text(md, encoding="utf-8")
            formatted += 1
            print(f"  OK ({len(md)} chars)")
        except Exception as e:
            print(f"  ERROR: {e}")

    print(f"\nDone. Formatted: {formatted}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
