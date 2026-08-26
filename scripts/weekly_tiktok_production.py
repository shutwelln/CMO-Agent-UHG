"""One-command weekly TikTok content production pipeline.

Chains the full pipeline:
1. Catalog sync - re-scan Drive folder for new source assets
2. Generate content - 7 new content packages for the target week
3. Append to sheet - add packages and calendar rows (not clear+rewrite)
4. Produce videos - match to catalog, render, upload to Drive, update sheet
5. Summary - print stats and optionally post Slack notification

Usage:
    python scripts/weekly_tiktok_production.py --week 2026-W13
    python scripts/weekly_tiktok_production.py  # auto-detect current week
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import dotenv  # noqa: E402

dotenv.load_dotenv()

from googleapiclient.discovery import build  # noqa: E402

from cmo_agent.google_auth import get_google_credentials  # noqa: E402
from cmo_agent.llm.anthropic import AnthropicLLM  # noqa: E402
from cmo_agent.llm.base import Message  # noqa: E402
from cmo_agent.text.composition_renderer import CompositionRenderer  # noqa: E402
from cmo_agent.tiktok.drive_sync import TikTokDriveSync  # noqa: E402
from cmo_agent.tiktok.hooks import (  # noqa: E402
    format_content_themes_for_prompt,
    format_engagement_comments_for_prompt,
    format_hook_library_for_prompt,
)
from cmo_agent.tiktok.media_catalog import MediaCatalog  # noqa: E402
from cmo_agent.tiktok.models import TikTokContentPackage  # noqa: E402
from cmo_agent.tiktok.performance import PerformanceStore  # noqa: E402
from cmo_agent.tiktok.producer import TikTokVideoProducer  # noqa: E402

# ── Constants ─────────────────────────────────────────────────────────

SHEET_ID = "1jhQQ3YtWSPUZltD46h3Y5Izptx7JkZ-SO19P85aMN74"
DRIVE_FOLDER_ID = "1Rs3Cqq4QBxr8oI2UGbGXlyYlzeHza3p9"
PRODUCED_FOLDER_ID = "12v0yO3hegF5P-PyI5rgjgkUfIJe0xP4i"
OAUTH_TOKEN = "data/google-token.json"
CATALOG_PATH = "data/dsdn/tiktok_media_catalog.jsonl"
PERFORMANCE_PATH = "data/dsdn/tiktok_performance.jsonl"
PACKAGES_TAB = "Content Packages"
CALENDAR_TAB = "Weekly Calendar"


def _get_sheets_service():
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN,
        service_account_path="",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def _parse_json_array(text: str) -> list:
    """Extract a JSON array from LLM output."""
    try:
        result = json.loads(text)
        if isinstance(result, list):
            return result
    except json.JSONDecodeError:
        pass
    for marker in ("```json", "```"):
        if marker in text:
            try:
                start = text.index(marker) + len(marker)
                end = text.index("```", start)
                result = json.loads(text[start:end].strip())
                if isinstance(result, list):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, list):
                return result
        except json.JSONDecodeError:
            pass
    return []


# ── Phase 1: Catalog Sync ────────────────────────────────────────────


async def catalog_sync(drive_sync: TikTokDriveSync, catalog: MediaCatalog, llm) -> dict:
    """Re-scan Drive folder and catalog any new files."""
    print("\n=== Phase 1: Catalog Sync ===")

    list_result = await drive_sync.list_source_assets()
    if list_result.get("status") != "listed":
        print(f"  Drive listing failed: {list_result}")
        return {"new": 0, "errors": 0}

    drive_files = list_result.get("files", [])
    print(f"  {len(drive_files)} files on Drive")

    uncataloged = catalog.get_uncataloged_drive(drive_files)
    print(f"  {len(uncataloged)} uncataloged files")

    if not uncataloged:
        print("  All files already cataloged.")
        return {"new": 0, "errors": 0}

    newly_cataloged = 0
    errors = 0

    for i, df in enumerate(uncataloged[:50], 1):
        file_id = df["id"]
        filename = df["name"]
        temp_path = None
        try:
            print(f"  [{i}/{min(len(uncataloged), 50)}] {filename}...", end=" ", flush=True)
            temp_path = drive_sync.download_single_asset(file_id, filename)
            if not temp_path:
                print("SKIP")
                errors += 1
                continue
            entry = await catalog.catalog_file(temp_path, llm, drive_file_id=file_id)
            newly_cataloged += 1
            print(f"OK ({len(entry.tags)} tags)")
        except Exception as e:
            errors += 1
            print(f"ERROR: {e}")
        finally:
            if temp_path:
                drive_sync.cleanup_temp_asset(temp_path)

    catalog.save()
    print(f"  Cataloged {newly_cataloged} new files, {errors} errors")
    return {"new": newly_cataloged, "errors": errors}


# ── Phase 2: Generate Content ────────────────────────────────────────


async def generate_content(llm, week_label: str, count: int = 7) -> tuple:
    """Generate content packages and weekly calendar."""
    print(f"\n=== Phase 2: Generate Content (Week {week_label}) ===")

    hook_library = format_hook_library_for_prompt()
    content_themes = format_content_themes_for_prompt()
    engagement_comments = format_engagement_comments_for_prompt()

    # Check for performance data to feed back
    perf_context = ""
    perf_store = PerformanceStore(store_path=PERFORMANCE_PATH)
    top = perf_store.get_top_performers(limit=3)
    if top:
        perf_context = "\nTOP PERFORMING CONTENT (learn from these hooks and formats):\n"
        for r in top:
            perf_context += f"- {r.package_id}: {r.views} views, {r.likes} likes\n"

    prompt = f"""Generate {count} complete TikTok content packages for the Down Syndrome Diagnosis Network (DSDN).

{content_themes}

{engagement_comments}
{perf_context}

HOOK FORMULAS (select from these, 8 WORDS MAX):
{hook_library}

For each package, output a JSON object with ALL fields:
- content_format: one of trending_sound_overlay/photo_carousel/talking_head_broll/transformation/day_in_the_life/educational_overlay/community_story/awareness_facts
- content_type: one of educational/emotional/community/awareness/fundraising/celebration
- mission_area: one of diagnosis_delivery/parent_connection/medical_information/family_reach/medical_relationships/sustainable_funding/engagement_0_to_3
- hook: 8 WORDS OR FEWER
- hook_formula_used: formula id
- short_caption: Under 300 characters, 2-3 sentences
- suggested_comments: Array of 3-5 engagement comments
- caption: Full caption (max 2200 chars)
- hashtags: Array of 5-10
- estimated_duration: "8s" or "10s" ONLY
- cta: Short call to action
- dsdn_mission_score: 1-5 (3+)
- trend_relevance_score: 1-5
- production_difficulty: easy/medium/hard

DISTRIBUTION: ~2-3 diagnosis experience, ~2-3 myth vs reality, ~2 what DS really means
Use DIFFERENT content_format for each. No em dashes. Person-first language.

Output ONLY a JSON array. No markdown."""

    print(f"  Generating {count} content packages...")
    resp = await llm.complete(
        messages=[Message(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=8000,
    )
    packages = _parse_json_array(resp.content)

    if not packages:
        print("  ERROR: Failed to generate packages")
        return [], []

    for pkg in packages:
        if not pkg.get("id"):
            pkg["id"] = f"tiktok_{uuid4().hex[:8]}"
        pkg["week"] = week_label

    print(f"  Generated {len(packages)} packages")

    # Generate calendar
    cal_prompt = f"""Create a 7-day TikTok content calendar for DSDN.

{content_themes}
{engagement_comments}

HOOK FORMULAS (8 WORDS MAX):
{hook_library}

7 days (Mon-Sun). ALL videos 10s or less. ALL hooks 8 words max.
At least 5 different formats. Mix content themes.
Person-first language. No em dashes.

Per day: day, content_format, content_type, mission_area, hook, hook_formula_used,
brief, short_caption, suggested_comments, estimated_duration ("8s"/"10s"), hashtags, production_difficulty.

Output ONLY a JSON array. No markdown."""

    print("  Generating weekly calendar...")
    cal_resp = await llm.complete(
        messages=[Message(role="user", content=cal_prompt)],
        temperature=0.7,
        max_tokens=6000,
    )
    calendar = _parse_json_array(cal_resp.content)

    if calendar:
        for day in calendar:
            if not day.get("id"):
                day["id"] = f"cal_{week_label}_{day.get('day', 'unknown')}"
            day["week"] = week_label
        print(f"  Generated {len(calendar)} calendar days")
    else:
        print("  WARNING: Failed to generate calendar")

    return packages, calendar


# ── Phase 3: Append to Sheet ─────────────────────────────────────────


def append_to_sheet(service, packages: list, calendar: list) -> dict:
    """Append new packages and calendar rows to the existing sheet."""
    print("\n=== Phase 3: Append to Sheet ===")

    pkg_rows = []
    for pkg in packages:
        comments = pkg.get("suggested_comments", [])
        comments_str = " | ".join(comments) if isinstance(comments, list) else str(comments)
        pkg_rows.append([
            pkg.get("id", ""),
            pkg.get("week", ""),
            pkg.get("content_format", ""),
            pkg.get("hook", ""),
            pkg.get("short_caption", ""),
            comments_str,
            pkg.get("caption", ""),
            ", ".join(pkg.get("hashtags", [])),
            pkg.get("estimated_duration", ""),
            pkg.get("mission_area", ""),
            pkg.get("content_type", ""),
            str(pkg.get("dsdn_mission_score", "")),
            pkg.get("production_difficulty", ""),
            "Draft",
        ])

    if pkg_rows:
        service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range=f"'{PACKAGES_TAB}'!A2",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": pkg_rows},
        ).execute()
        print(f"  Appended {len(pkg_rows)} rows to {PACKAGES_TAB}")

    cal_rows = []
    for day in calendar:
        comments = day.get("suggested_comments", [])
        comments_str = " | ".join(comments) if isinstance(comments, list) else str(comments)
        cal_rows.append([
            day.get("id", ""),
            day.get("week", ""),
            day.get("day", ""),
            day.get("content_format", ""),
            day.get("hook", ""),
            day.get("short_caption", ""),
            comments_str,
            day.get("brief", ""),
            ", ".join(day.get("hashtags", [])),
            day.get("estimated_duration", ""),
            day.get("production_difficulty", ""),
            "Draft",
        ])

    if cal_rows:
        service.spreadsheets().values().append(
            spreadsheetId=SHEET_ID,
            range=f"'{CALENDAR_TAB}'!A2",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": cal_rows},
        ).execute()
        print(f"  Appended {len(cal_rows)} rows to {CALENDAR_TAB}")

    return {"packages": len(pkg_rows), "calendar": len(cal_rows)}


# ── Phase 4: Produce Videos ──────────────────────────────────────────


async def produce_videos(
    packages: list,
    catalog: MediaCatalog,
    drive_sync: TikTokDriveSync,
    service,
) -> dict:
    """Render videos for each package, upload to Drive, update sheet."""
    print("\n=== Phase 4: Produce Videos ===")

    renderer = CompositionRenderer(remotion_dir="data/remotion")
    producer = TikTokVideoProducer(
        composition_renderer=renderer,
        media_catalog=catalog,
        drive_sync=drive_sync,
        output_dir="./data/dsdn/tiktok_produced",
    )

    produced = 0
    failed = 0

    # Read sheet to find row numbers for the packages we just wrote
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=SHEET_ID, range=f"'{PACKAGES_TAB}'!A1:N5000")
            .execute()
        )
        all_rows = result.get("values", [])
    except Exception as e:
        print(f"  ERROR reading sheet: {e}")
        return {"produced": 0, "failed": len(packages)}

    # Build ID -> row_number map
    id_to_row = {}
    for i, row in enumerate(all_rows[1:], start=2):
        if row:
            id_to_row[row[0]] = i

    for i, pkg_data in enumerate(packages, 1):
        pkg_id = pkg_data.get("id", f"unknown_{i}")
        hook = pkg_data.get("hook", "")
        fmt = pkg_data.get("content_format", "educational_overlay")
        duration = pkg_data.get("estimated_duration", "10s")
        row_num = id_to_row.get(pkg_id)

        print(f"\n  [{i}/{len(packages)}] {pkg_id}: \"{hook}\" ({duration})")

        try:
            package = TikTokContentPackage(
                id=pkg_id,
                content_format=fmt,
                content_type=pkg_data.get("content_type", "awareness"),
                mission_area=pkg_data.get("mission_area", "family_reach"),
                hook=hook,
                text_overlays=[hook] if hook else [],
                estimated_duration=duration,
                dsdn_mission_score=pkg_data.get("dsdn_mission_score", 3),
                trend_relevance_score=pkg_data.get("trend_relevance_score", 3),
            )
        except Exception as e:
            print(f"    SKIP: {e}")
            failed += 1
            continue

        if row_num:
            service.spreadsheets().values().update(
                spreadsheetId=SHEET_ID,
                range=f"'{PACKAGES_TAB}'!N{row_num}",
                valueInputOption="RAW",
                body={"values": [["Producing"]]},
            ).execute()

        result = await producer.produce(package)

        if result.status == "produced":
            video_url = result.drive_url or result.cdn_url or result.video_path
            if row_num:
                service.spreadsheets().values().update(
                    spreadsheetId=SHEET_ID,
                    range=f"'{PACKAGES_TAB}'!N{row_num}:O{row_num}",
                    valueInputOption="RAW",
                    body={"values": [["Produced", video_url]]},
                ).execute()
            produced += 1
            print(f"    Produced: {video_url}")
        else:
            if row_num:
                service.spreadsheets().values().update(
                    spreadsheetId=SHEET_ID,
                    range=f"'{PACKAGES_TAB}'!N{row_num}",
                    valueInputOption="RAW",
                    body={"values": [["Failed"]]},
                ).execute()
            failed += 1
            print(f"    FAILED: {result.error}")

    return {"produced": produced, "failed": failed}


# ── Main Pipeline ─────────────────────────────────────────────────────


async def main():
    parser = argparse.ArgumentParser(description="Weekly TikTok production pipeline")
    parser.add_argument("--week", default=None, help="Week label (e.g. 2026-W13)")
    parser.add_argument("--count", type=int, default=7, help="Number of content packages")
    parser.add_argument("--skip-catalog", action="store_true", help="Skip Drive catalog sync")
    parser.add_argument("--skip-produce", action="store_true", help="Skip video production")
    args = parser.parse_args()

    # Determine week label
    if args.week:
        week_label = args.week
    else:
        now = datetime.now(timezone.utc)
        week_label = f"{now.year}-W{now.isocalendar()[1]:02d}"

    print(f"{'='*60}")
    print(f"DSDN TikTok Weekly Production - {week_label}")
    print(f"{'='*60}")

    # Initialize shared resources
    drive_sync = TikTokDriveSync(
        google_credentials_path="",
        google_oauth_token_path=OAUTH_TOKEN,
        drive_folder_id=DRIVE_FOLDER_ID,
    )
    catalog = MediaCatalog(catalog_path=CATALOG_PATH)
    catalog.load()
    sheets_service = _get_sheets_service()

    # Use Haiku for vision (cheaper), Sonnet for content generation
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        return
    vision_llm = AnthropicLLM(api_key=api_key, model="claude-haiku-4-5-20251001")
    content_llm = AnthropicLLM(api_key=api_key, model="claude-sonnet-4-20250514")

    # Phase 1: Catalog sync
    catalog_stats = {"new": 0, "errors": 0}
    if not args.skip_catalog:
        catalog_stats = await catalog_sync(drive_sync, catalog, vision_llm)
    else:
        print("\n=== Phase 1: Catalog Sync (SKIPPED) ===")

    # Phase 2: Generate content
    packages, calendar = await generate_content(content_llm, week_label, count=args.count)
    if not packages:
        print("\nERROR: No content generated. Aborting.")
        return

    # Phase 3: Append to sheet
    sheet_stats = append_to_sheet(sheets_service, packages, calendar)

    # Phase 4: Produce videos
    prod_stats = {"produced": 0, "failed": 0}
    if not args.skip_produce:
        prod_stats = await produce_videos(packages, catalog, drive_sync, sheets_service)
    else:
        print("\n=== Phase 4: Produce Videos (SKIPPED) ===")

    # Summary
    print(f"\n{'='*60}")
    print(f"SUMMARY - {week_label}")
    print(f"{'='*60}")
    print(f"  Catalog: {catalog_stats['new']} new files indexed, {catalog_stats['errors']} errors")
    print(f"  Content: {len(packages)} packages, {len(calendar)} calendar days")
    print(f"  Sheet: {sheet_stats['packages']} package rows, {sheet_stats['calendar']} calendar rows appended")
    print(f"  Videos: {prod_stats['produced']} produced, {prod_stats['failed']} failed")
    print(f"  Sheet: https://docs.google.com/spreadsheets/d/{SHEET_ID}")
    print(f"  Drive: https://drive.google.com/drive/folders/{PRODUCED_FOLDER_ID}")


if __name__ == "__main__":
    asyncio.run(main())
