#!/usr/bin/env python3
"""Transform YouTube renders into Facebook-ready video packages.

Copies YouTube long-form (16:9) → Facebook Feed video
Copies YouTube Shorts (9:16) → Facebook Reel
Generates Facebook-specific metadata (caption, hashtags, CTA link).

Usage:
    python scripts/facebook_video_prepare.py                    # all available
    python scripts/facebook_video_prepare.py --limit 2          # first 2
    python scripts/facebook_video_prepare.py --slug medicare-explained-simple-guide
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List

_PROJECT_ROOT = Path(__file__).resolve().parents[1]

YOUTUBE_DIR = _PROJECT_ROOT / "data" / "youtube" / "ready"
FACEBOOK_DIR = _PROJECT_ROOT / "data" / "facebook" / "ready"

BASE_URL = "https://saverwell.com/guides"


def find_ready_articles(slug: str = "", limit: int = 0) -> List[str]:
    """Find YouTube slugs that have rendered videos ready for Facebook."""
    if not YOUTUBE_DIR.exists():
        return []

    slugs: List[str] = []
    for slug_dir in sorted(YOUTUBE_DIR.iterdir()):
        if not slug_dir.is_dir():
            continue
        # Skip short-form dirs (they are paired with the main slug)
        if slug_dir.name.endswith("-short"):
            continue
        if slug and slug_dir.name != slug:
            continue
        # Need at least a script.json to be considered ready
        if not (slug_dir / "script.json").exists():
            continue
        slugs.append(slug_dir.name)

    if limit:
        slugs = slugs[:limit]
    return slugs


def prepare_facebook_package(slug: str) -> Dict[str, Any]:
    """Create Facebook video package from YouTube renders."""
    yt_long_dir = YOUTUBE_DIR / slug
    yt_short_dir = YOUTUBE_DIR / f"{slug}-short"
    fb_dir = FACEBOOK_DIR / slug
    fb_dir.mkdir(parents=True, exist_ok=True)

    result: Dict[str, Any] = {"slug": slug, "feed": None, "reel": None}

    # Load YouTube metadata for caption generation
    metadata: Dict[str, Any] = {}
    meta_path = yt_long_dir / "metadata.json"
    if meta_path.exists():
        metadata = json.loads(meta_path.read_text())

    title = metadata.get("title", slug.replace("-", " ").title())
    tags = metadata.get("tags", [])

    # Copy long-form → feed.mp4
    yt_video = yt_long_dir / "video.mp4"
    if yt_video.exists():
        feed_path = fb_dir / "feed.mp4"
        shutil.copy2(yt_video, feed_path)
        result["feed"] = str(feed_path)
        print(f"  Feed video: {feed_path.name} ({yt_video.stat().st_size // 1024}KB)")

    # Copy short → reel.mp4
    yt_short_video = yt_short_dir / "video.mp4"
    if yt_short_video.exists():
        reel_path = fb_dir / "reel.mp4"
        shutil.copy2(yt_short_video, reel_path)
        result["reel"] = str(reel_path)
        print(f"  Reel video: {reel_path.name} ({yt_short_video.stat().st_size // 1024}KB)")

    # Generate Facebook metadata
    hashtags = _generate_hashtags(tags)
    caption = _generate_caption(title, metadata.get("description", ""), hashtags)
    guide_url = f"{BASE_URL}/{slug}?utm_source=facebook&utm_medium=video&utm_campaign=guide"

    fb_metadata = {
        "title": title,
        "caption": caption,
        "hashtags": hashtags,
        "cta_url": guide_url,
        "alt_text": f"Video guide: {title}",
        "source_slug": slug,
        "formats": {
            "feed": "16:9 landscape (1920x1080)" if result["feed"] else None,
            "reel": "9:16 portrait (1080x1920)" if result["reel"] else None,
        },
    }

    meta_out = fb_dir / "metadata.json"
    meta_out.write_text(json.dumps(fb_metadata, indent=2, ensure_ascii=False))
    result["metadata"] = str(meta_out)

    return result


def _generate_hashtags(tags: List[str]) -> List[str]:
    """Generate 3-5 Facebook-relevant hashtags from article tags."""
    base_tags = ["#Saverwell", "#SeniorSavings"]
    tag_map = {
        "medicare": "#Medicare",
        "health-insurance": "#HealthInsurance",
        "seniors": "#SeniorLiving",
        "retirement": "#Retirement",
        "social-security": "#SocialSecurity",
        "insurance": "#Insurance",
        "dental": "#DentalCare",
        "hearing": "#HearingAids",
        "vision": "#VisionCare",
        "phone": "#SeniorTech",
        "scam": "#ScamProtection",
        "savings": "#MoneySaving",
        "tax": "#TaxTips",
        "medicaid": "#Medicaid",
    }
    for tag in tags:
        tag_lower = tag.lower()
        for key, hashtag in tag_map.items():
            if key in tag_lower and hashtag not in base_tags:
                base_tags.append(hashtag)
                if len(base_tags) >= 5:
                    break
        if len(base_tags) >= 5:
            break
    return base_tags


def _generate_caption(title: str, description: str, hashtags: List[str]) -> str:
    """Generate Facebook caption (2200 char limit, first 125 visible)."""
    # First 125 chars should be compelling (visible without "See more")
    hook = title
    if len(hook) > 120:
        hook = hook[:117] + "..."

    body = description[:500] if description else ""

    hashtag_str = " ".join(hashtags)
    caption = f"{hook}\n\n{body}\n\n{hashtag_str}"

    # Enforce 2200 char limit
    if len(caption) > 2200:
        caption = caption[:2197] + "..."

    return caption


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare Facebook videos from YouTube renders")
    parser.add_argument("--slug", type=str, default="", help="Single article slug")
    parser.add_argument("--limit", type=int, default=0, help="Max articles to process")
    args = parser.parse_args()

    slugs = find_ready_articles(slug=args.slug, limit=args.limit)
    print(f"Found {len(slugs)} articles with YouTube renders\n")

    if not slugs:
        print("Nothing to prepare. Run youtube_batch_produce.py first.")
        return

    prepared = 0
    for i, slug in enumerate(slugs, 1):
        print(f"[{i}/{len(slugs)}] {slug}")
        result = prepare_facebook_package(slug)
        has_content = result.get("feed") or result.get("reel")
        if has_content:
            prepared += 1
            print(f"  Metadata: {result['metadata']}")
        else:
            print("  No video files found — skipping (scripts only?)")
        print()

    print(f"Done. Prepared {prepared}/{len(slugs)} Facebook packages.")
    print(f"Output: {FACEBOOK_DIR}")


if __name__ == "__main__":
    main()
