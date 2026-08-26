"""End-to-end test: produce TikTok videos from local source assets.

1. Define 3 content packages (one per source video)
2. Render each via Remotion (TikTokOverlay-Portrait-Motion)
3. Create a Google Sheet production dashboard
4. Log results with video paths

Run:  python scripts/test_tiktok_pipeline.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from cmo_agent.text.composition_renderer import CompositionRenderer
from cmo_agent.tiktok.models import (
    ContentFormat,
    ContentType,
    MissionArea,
    ProductionDifficulty,
    TikTokContentPackage,
)

# ── Source videos + content packages ──────────────────────────────────────

SOURCE_DIR = Path(__file__).resolve().parent.parent / "data" / "dsdn" / "tiktok-videos"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "dsdn" / "tiktok_produced"

PACKAGES = [
    {
        "id": "tiktok_swimming_01",
        "source_file": "18f4cf74173242a9bec87906147c6e12.mov",
        "package": TikTokContentPackage(
            id="tiktok_swimming_01",
            content_format=ContentFormat.day_in_the_life,
            content_type=ContentType.celebration,
            mission_area=MissionArea.parent_connection,
            hook="Watch this little swimmer go",
            caption="Just keep swimming. This is what joy looks like. #DownSyndrome #SwimLife #DSDN #Inclusion #JoyfulKids",
            hashtags=["#DownSyndrome", "#SwimLife", "#DSDN", "#Inclusion", "#JoyfulKids"],
            text_overlays=["Watch this little swimmer go"],
            estimated_duration="15s",
            cta="Follow @thedsdn for more family moments",
            dsdn_mission_score=4,
            trend_relevance_score=3,
            production_difficulty=ProductionDifficulty.easy,
        ),
    },
    {
        "id": "tiktok_bestlife_02",
        "source_file": "5509016ace294d389cbed9821534a7ea.mov",
        "package": TikTokContentPackage(
            id="tiktok_bestlife_02",
            content_format=ContentFormat.awareness_facts,
            content_type=ContentType.awareness,
            mission_area=MissionArea.family_reach,
            hook="Kids with Down syndrome are out here living their best lives",
            caption="No limits. Just love, laughter, and living their best lives. #DownSyndrome #LivingTheirBestLife #DSDN #Awareness #Inclusion #DisabilityJoy",
            hashtags=["#DownSyndrome", "#LivingTheirBestLife", "#DSDN", "#Awareness", "#Inclusion"],
            text_overlays=["Kids with Down syndrome are out here living their best lives"],
            estimated_duration="15s",
            cta="Link in bio to connect with DSDN",
            dsdn_mission_score=5,
            trend_relevance_score=4,
            production_difficulty=ProductionDifficulty.easy,
        ),
    },
    {
        "id": "tiktok_hockey_03",
        "source_file": "7209cc48d44a49b2b2803c2dceb2cf66.mov",
        "package": TikTokContentPackage(
            id="tiktok_hockey_03",
            content_format=ContentFormat.community_story,
            content_type=ContentType.community,
            mission_area=MissionArea.parent_connection,
            hook='"He may not be able to do the same things as other kids."',
            caption="They said he might not keep up. He is out here playing hockey. Every child deserves the chance to prove the world wrong. #DownSyndrome #HockeyKids #DSDN #MythBuster #Inclusion",
            hashtags=["#DownSyndrome", "#HockeyKids", "#DSDN", "#MythBuster", "#Inclusion"],
            text_overlays=['"He may not be able to do the same things as other kids."'],
            estimated_duration="15s",
            cta="Follow @thedsdn for more stories",
            dsdn_mission_score=5,
            trend_relevance_score=5,
            production_difficulty=ProductionDifficulty.easy,
        ),
    },
]


async def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    renderer = CompositionRenderer(
        remotion_project_dir=str(
            Path(__file__).resolve().parent.parent / "data" / "remotion"
        ),
        output_dir=str(OUTPUT_DIR),
    )

    results = []

    for item in PACKAGES:
        pkg = item["package"]
        source_path = str(SOURCE_DIR / item["source_file"])
        pkg_id = item["id"]

        if not Path(source_path).exists():
            print(f"SKIP {pkg_id}: source file not found at {source_path}")
            continue

        print(f"\n{'='*60}")
        print(f"PRODUCING: {pkg_id}")
        print(f"Source: {item['source_file']}")
        print(f"Hook: {pkg.hook}")
        print(f"Format: {pkg.content_format.value}")
        print(f"{'='*60}")

        # Determine text style
        text_style = "bold"
        if pkg.content_format == ContentFormat.community_story:
            text_style = "quote"

        # Determine text color
        text_color = "#FFFFFF"
        if pkg.content_type in (ContentType.community, ContentType.awareness):
            text_color = "#2563EB"

        # Determine animation
        animation = "fade-up"
        if pkg.content_format in (
            ContentFormat.educational_overlay,
            ContentFormat.awareness_facts,
        ):
            animation = "word-by-word"

        # Build props
        text = pkg.text_overlays[0] if pkg.text_overlays else pkg.hook
        props = {
            "text": text,
            "subtext": pkg.cta or "",
            "textPosition": "bottom-center",
            "textColor": text_color,
            "textStyle": text_style,
            "bgDim": 0.15,
            "textShadow": True,
            "animation": animation,
        }

        print(f"Props: {json.dumps(props, indent=2)}")

        try:
            video_path = await renderer.render_motion(
                template_id="TikTokOverlay",
                props=props,
                duration_seconds=15,
                fps=30,
                output_format="portrait",
                background_video_path=source_path,
            )
            print(f"SUCCESS: {video_path}")
            results.append({
                "id": pkg_id,
                "status": "produced",
                "video_path": video_path,
                "hook": pkg.hook,
            })
        except Exception as e:
            print(f"FAILED: {e}")
            results.append({
                "id": pkg_id,
                "status": "failed",
                "error": str(e),
            })

    # Summary
    print(f"\n{'='*60}")
    print("PRODUCTION SUMMARY")
    print(f"{'='*60}")
    produced = [r for r in results if r["status"] == "produced"]
    failed = [r for r in results if r["status"] == "failed"]
    print(f"Produced: {len(produced)}/{len(results)}")
    print(f"Failed: {len(failed)}/{len(results)}")

    for r in produced:
        print(f"  {r['id']}: {r['video_path']}")

    for r in failed:
        print(f"  {r['id']}: ERROR - {r['error']}")


if __name__ == "__main__":
    asyncio.run(main())
