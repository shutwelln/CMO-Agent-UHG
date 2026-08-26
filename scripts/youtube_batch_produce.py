#!/usr/bin/env python3
"""Batch produce YouTube videos from guide articles.

Reads published guide articles from Supabase, generates scripts,
voiceover, stock footage, and renders professional videos to data/youtube/ready/.

Usage:
    python scripts/youtube_batch_produce.py                    # produce for all articles
    python scripts/youtube_batch_produce.py --limit 5          # first 5 articles
    python scripts/youtube_batch_produce.py --slug medicare-explained-simple-guide
    python scripts/youtube_batch_produce.py --shorts-only      # only YouTube Shorts
    python scripts/youtube_batch_produce.py --scripts-only     # scripts only, no render
    python scripts/youtube_batch_produce.py --render-only      # render existing scripts only
    python scripts/youtube_batch_produce.py --platform all     # all platform exports
    python scripts/youtube_batch_produce.py --platform youtube_shorts  # single platform
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
import structlog

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from cmo_agent.config import Settings  # noqa: E402
from cmo_agent.youtube.producer import YouTubeVideoProducer  # noqa: E402
from cmo_agent.youtube.script_generator import (  # noqa: E402
    VideoScript,
    YouTubeScriptGenerator,
)

logger = structlog.get_logger()

OUTPUT_DIR = _PROJECT_ROOT / "data" / "youtube" / "ready"

_ALL_PLATFORMS = ["youtube_shorts", "facebook_reels", "facebook_feed"]


async def fetch_articles(
    settings: Settings,
    slug: str = "",
    limit: int = 0,
) -> List[Dict[str, Any]]:
    """Fetch published guide articles from Supabase."""
    params: Dict[str, str] = {
        "select": (
            "slug,title,subtitle,overview_md,"
            "key_takeaways_md,body_md,faq_md,seo_keywords,tags"
        ),
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


def _build_producer(settings: Settings) -> YouTubeVideoProducer:
    """Build a YouTubeVideoProducer with all settings."""
    return YouTubeVideoProducer(
        elevenlabs_api_key=settings.elevenlabs_api_key,
        anthropic_api_key=settings.anthropic_api_key,
        pexels_api_key=settings.pexels_api_key,
        bgm_path=settings.youtube_bgm_path,
        clip_cache_dir=settings.youtube_clip_cache_dir,
        scanning_model=settings.llm_model_scanning,
    )


async def main() -> None:
    parser = argparse.ArgumentParser(description="Batch produce YouTube videos")
    parser.add_argument("--slug", type=str, default="", help="Single article slug")
    parser.add_argument("--limit", type=int, default=0, help="Max articles to process")
    parser.add_argument("--shorts-only", action="store_true", help="Only generate Shorts")
    parser.add_argument(
        "--scripts-only", action="store_true",
        help="Only generate scripts, skip rendering",
    )
    parser.add_argument(
        "--render-only", action="store_true",
        help="Render existing scripts only, no LLM calls",
    )
    parser.add_argument(
        "--platform",
        type=str,
        default="all",
        choices=["all", "youtube_long", "youtube_shorts", "facebook_reels", "facebook_feed"],
        help="Platform to export (default: all)",
    )
    args = parser.parse_args()

    # Load settings from .env
    settings = Settings()

    # Determine which platforms to export
    if args.platform == "all":
        platforms = _ALL_PLATFORMS
    elif args.platform == "youtube_long":
        platforms = []  # Long-form is always produced, no separate export needed
    else:
        platforms = [args.platform]

    # render-only mode: load existing scripts and render videos
    if args.render_only:
        await _render_only_mode(settings, args.slug, args.limit, args.shorts_only, platforms)
        return

    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY required")
        sys.exit(1)

    if not settings.supabase_url:
        print("ERROR: SUPABASE_URL required")
        sys.exit(1)

    # Check optional keys
    if not settings.elevenlabs_api_key:
        print("WARNING: ELEVENLABS_API_KEY not set — voiceover will be skipped")
    if not settings.pexels_api_key:
        print("WARNING: PEXELS_API_KEY not set — stock footage will be skipped (Remotion fallback)")

    # Fetch articles
    articles = await fetch_articles(settings, slug=args.slug, limit=args.limit)
    print(f"Found {len(articles)} articles")

    # Skip articles that already have scripts
    to_process = []
    for art in articles:
        slug = art["slug"]
        slug_dir = OUTPUT_DIR / slug
        if (slug_dir / "script.json").exists():
            print(f"  Skipping {slug} (already produced)")
            continue
        to_process.append(art)

    print(f"Articles to process: {len(to_process)}")
    if not to_process:
        print("Nothing to do.")
        return

    # Initialize generators
    script_gen = YouTubeScriptGenerator(
        anthropic_api_key=settings.anthropic_api_key,
        writing_model=settings.llm_model_writing,
    )

    producer = _build_producer(settings)

    produced = 0
    failed = 0

    for i, art in enumerate(to_process, 1):
        slug = art["slug"]
        print(f"\n[{i}/{len(to_process)}] {slug}")

        # Generate long-form script (skip if shorts-only)
        if not args.shorts_only:
            print("  Generating long-form script...")
            long_script = await script_gen.generate_long_script(art)
            if long_script:
                if args.scripts_only:
                    out_dir = OUTPUT_DIR / slug
                    out_dir.mkdir(parents=True, exist_ok=True)
                    (out_dir / "script.json").write_text(
                        json.dumps(long_script.to_dict(), indent=2)
                    )
                    print(f"    Script saved ({long_script.word_count} words)")
                else:
                    result = await producer.produce(long_script, platforms=platforms)
                    if result and result.get("status") in ("complete", "partial"):
                        produced += 1
                        status = result.get("status")
                        exports = result.get("exports", {})
                        print(f"    Produced: {status} ({len(exports)} platform exports)")
                    elif result and result.get("status") == "qa_failed":
                        produced += 1
                        qa = result.get("qa", {})
                        failed_names = [
                            name for name, r in qa.get("results", {}).items()
                            if not r.get("passed")
                        ]
                        print(f"    QA FAILED: {', '.join(failed_names)}")
                        for name in failed_names:
                            errs = qa["results"][name].get("errors", [])
                            for e in errs:
                                print(f"      - {e}")
                    else:
                        failed += 1
                        print("    FAILED")
            else:
                failed += 1
                print("    Script generation FAILED")

        # Generate Shorts script
        print("  Generating Shorts script...")
        short_script = await script_gen.generate_short_script(art)
        if short_script:
            short_dir = OUTPUT_DIR / f"{slug}-short"
            if args.scripts_only:
                short_dir.mkdir(parents=True, exist_ok=True)
                (short_dir / "script.json").write_text(
                    json.dumps(short_script.to_dict(), indent=2)
                )
                print(f"    Short script saved ({short_script.word_count} words)")
            else:
                result = await producer.produce(short_script, output_dir=short_dir)
                if result:
                    print(f"    Short produced: {result.get('status')}")

        # Pause between articles
        if i < len(to_process):
            await asyncio.sleep(2.0)

    print(f"\nDone. Produced: {produced} | Failed: {failed}")
    print(f"Output: {OUTPUT_DIR}")


def _load_script_from_json(path: Path) -> Optional[VideoScript]:
    """Load a VideoScript from a saved script.json file."""
    try:
        data = json.loads(path.read_text())
        return VideoScript(
            slug=data["slug"],
            title=data["title"],
            format=data.get("format", "long"),
            duration_seconds=data.get("duration_seconds", 150),
            hook=data.get("hook", ""),
            sections=data.get("sections", []),
            outro=data.get("outro", ""),
            cta=data.get("cta", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            chapter_markers=data.get("chapter_markers", []),
        )
    except Exception as e:
        print(f"  ERROR loading script: {e}")
        return None


async def _render_only_mode(
    settings: Settings,
    slug: str,
    limit: int,
    shorts_only: bool,
    platforms: List[str],
) -> None:
    """Render videos from existing script.json files (no LLM calls for scripts)."""
    print("=== RENDER-ONLY MODE ===\n")

    # Find dirs with script.json
    candidates: List[Path] = []
    for slug_dir in sorted(OUTPUT_DIR.iterdir()):
        if not slug_dir.is_dir():
            continue
        if slug and not slug_dir.name.startswith(slug):
            continue
        if slug_dir.name.endswith("-short"):
            continue
        if not (slug_dir / "script.json").exists():
            continue
        candidates.append(slug_dir)

    if limit:
        candidates = candidates[:limit]

    print(f"Found {len(candidates)} articles with existing scripts\n")
    if not candidates:
        print("Nothing to render.")
        return

    producer = _build_producer(settings)

    produced = 0
    failed = 0

    for i, slug_dir in enumerate(candidates, 1):
        s = slug_dir.name
        print(f"[{i}/{len(candidates)}] {s}")

        # Render long-form
        if not shorts_only:
            script = _load_script_from_json(slug_dir / "script.json")
            if script:
                print(f"  Rendering long-form ({script.word_count} words)...")
                result = await producer.produce(script, platforms=platforms)
                if result and result.get("status") in ("complete", "partial"):
                    produced += 1
                    exports = result.get("exports", {})
                    print(f"    -> {result.get('status')} ({len(exports)} exports)")
                elif result and result.get("status") == "qa_failed":
                    produced += 1
                    qa = result.get("qa", {})
                    failed_names = [
                        name for name, r in qa.get("results", {}).items()
                        if not r.get("passed")
                    ]
                    print(f"    -> QA FAILED: {', '.join(failed_names)}")
                    for name in failed_names:
                        for e in qa["results"][name].get("errors", []):
                            print(f"         {e}")
                else:
                    failed += 1
                    print("    -> FAILED")

        # Render short-form
        short_dir = OUTPUT_DIR / f"{s}-short"
        short_script_path = short_dir / "script.json"
        if short_script_path.exists():
            short_script = _load_script_from_json(short_script_path)
            if short_script:
                print(f"  Rendering short ({short_script.word_count} words)...")
                result = await producer.produce(short_script, output_dir=short_dir)
                if result and result.get("status") in ("complete", "partial"):
                    produced += 1
                    print(f"    -> {result.get('status')}")
                else:
                    failed += 1
                    print("    -> FAILED")

    print(f"\nDone. Produced: {produced} | Failed: {failed}")
    print(f"Output: {OUTPUT_DIR}")


if __name__ == "__main__":
    asyncio.run(main())
