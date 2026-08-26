"""Generate fresh DSDN TikTok content and write to the existing Google Sheet.

Generates 7-10 content packages and a 7-day weekly calendar using the updated
prompts (10s max, 8-word hooks, short captions, engagement comments), then
clears old content from the sheet and writes the new batch as Week 1.

Usage:
    python scripts/generate_new_content.py [--week 2026-W12]
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
from cmo_agent.tiktok.hooks import (  # noqa: E402
    format_content_themes_for_prompt,
    format_engagement_comments_for_prompt,
    format_hook_library_for_prompt,
)

SHEET_ID = "1jhQQ3YtWSPUZltD46h3Y5Izptx7JkZ-SO19P85aMN74"
OAUTH_TOKEN = "data/google-token.json"

# Tab names on the existing sheet
PACKAGES_TAB = "Content Packages"
CALENDAR_TAB = "Weekly Calendar"


def _get_sheets_service():
    creds = get_google_credentials(
        oauth_token_path=OAUTH_TOKEN,
        service_account_path="",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    return build("sheets", "v4", credentials=creds)


def _clear_tab(service, tab_name: str) -> None:
    """Clear all data rows (keep header) from a tab."""
    try:
        service.spreadsheets().values().clear(
            spreadsheetId=SHEET_ID,
            range=f"'{tab_name}'!A2:Z5000",
        ).execute()
        print(f"  Cleared {tab_name}")
    except Exception as e:
        print(f"  Warning: could not clear {tab_name}: {e}")


def _write_rows(service, tab_name: str, headers: list, rows: list) -> None:
    """Write headers + rows to a tab."""
    # Write headers
    service.spreadsheets().values().update(
        spreadsheetId=SHEET_ID,
        range=f"'{tab_name}'!A1",
        valueInputOption="RAW",
        body={"values": [headers]},
    ).execute()
    # Write data
    if rows:
        service.spreadsheets().values().update(
            spreadsheetId=SHEET_ID,
            range=f"'{tab_name}'!A2",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute()
    print(f"  Wrote {len(rows)} rows to {tab_name}")


async def generate_content_packages(llm, count: int = 10) -> list:
    """Generate content packages via LLM."""
    hook_library = format_hook_library_for_prompt()
    content_themes = format_content_themes_for_prompt()
    engagement_comments = format_engagement_comments_for_prompt()

    prompt = f"""Generate {count} complete TikTok content packages for the Down Syndrome Diagnosis Network (DSDN).

{content_themes}

{engagement_comments}

HOOK FORMULAS (select from these, 8 WORDS MAX):
{hook_library}

For each package, output a JSON object with ALL of these fields:
- content_format: one of trending_sound_overlay/photo_carousel/talking_head_broll/transformation/day_in_the_life/educational_overlay/community_story/awareness_facts
- content_type: one of educational/emotional/community/awareness/fundraising/celebration
- mission_area: one of diagnosis_delivery/parent_connection/medical_information/family_reach/medical_relationships/sustainable_funding/engagement_0_to_3
- hook: The attention-grabbing first line, 8 WORDS OR FEWER
- hook_formula_used: The hook formula id used
- short_caption: Punchy 2-3 sentence caption, UNDER 300 CHARACTERS
- suggested_comments: Array of 3-5 engagement-bait comments
- caption: Full TikTok caption (MAX 2200 characters)
- hashtags: Array of 5-10 hashtags
- estimated_duration: "8s" or "10s" ONLY
- cta: Call to action
- dsdn_mission_score: 1-5 (must be 3+)
- trend_relevance_score: 1-5
- production_difficulty: easy/medium/hard

DISTRIBUTION REQUIREMENTS:
- ~3 packages about diagnosis experience
- ~3 packages about myth vs reality
- ~3-4 packages about what DS really means
- Use DIFFERENT content_format for each package
- Mix content_types and mission_areas

RULES:
- hook MUST be 8 words or fewer
- estimated_duration MUST be "8s" or "10s"
- short_caption MUST be under 300 characters
- Person-first language: "child with Down syndrome", not "Down syndrome child"
- No em dashes or en dashes in ANY text

Output ONLY a JSON array of {count} package objects. No markdown, no explanation."""

    resp = await llm.complete(
        messages=[Message(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=8000,
    )
    return _parse_json_array(resp.content)


async def generate_weekly_calendar(llm) -> list:
    """Generate a 7-day content calendar via LLM."""
    hook_library = format_hook_library_for_prompt()
    content_themes = format_content_themes_for_prompt()
    engagement_comments = format_engagement_comments_for_prompt()

    prompt = f"""Create a 7-day TikTok content calendar for DSDN (Down Syndrome Diagnosis Network).

{content_themes}

{engagement_comments}

HOOK FORMULAS (8 WORDS MAX):
{hook_library}

REQUIREMENTS:
- 7 days, one primary post per day (Monday through Sunday)
- ALL videos 10 seconds or less
- ALL hooks 8 words or fewer
- Use AT LEAST 5 different content_format values
- Distribute across 3 themes: diagnosis experience, myth vs reality, what DS really means
- Person-first language: "child with Down syndrome"
- No em dashes or en dashes

For each day, output:
- day: Monday/Tuesday/etc.
- content_format: one of the 8 formats
- content_type: educational/emotional/community/awareness/fundraising/celebration
- mission_area: the DSDN mission area
- hook: 8 WORDS OR FEWER
- hook_formula_used: The formula id
- brief: 2-3 sentence content description
- short_caption: Under 300 characters
- suggested_comments: Array of 3-5 engagement comments
- estimated_duration: "8s" or "10s" ONLY
- hashtags: 5-8 hashtags
- production_difficulty: easy/medium/hard

Output ONLY a JSON array of 7 day objects. No markdown, no explanation."""

    resp = await llm.complete(
        messages=[Message(role="user", content=prompt)],
        temperature=0.7,
        max_tokens=6000,
    )
    return _parse_json_array(resp.content)


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


async def main():
    parser = argparse.ArgumentParser(description="Generate DSDN TikTok content")
    parser.add_argument("--week", default=None, help="Week label (e.g. 2026-W12)")
    parser.add_argument("--count", type=int, default=10, help="Number of content packages")
    parser.add_argument("--append", action="store_true", help="Append instead of clear+write")
    args = parser.parse_args()

    # Determine week label
    if args.week:
        week_label = args.week
    else:
        now = datetime.now(timezone.utc)
        week_label = f"{now.year}-W{now.isocalendar()[1]:02d}"

    print(f"Week: {week_label}")
    print(f"Generating {args.count} content packages...")

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        return
    llm = AnthropicLLM(api_key=api_key, model="claude-sonnet-4-20250514")

    # Generate content
    packages = await generate_content_packages(llm, count=args.count)
    if not packages:
        print("ERROR: Failed to generate content packages")
        return

    # Assign IDs and week
    for pkg in packages:
        if not pkg.get("id"):
            pkg["id"] = f"tiktok_{uuid4().hex[:8]}"
        pkg["week"] = week_label

    print(f"  Generated {len(packages)} packages")

    # Validate hooks
    for pkg in packages:
        hook = pkg.get("hook", "")
        word_count = len(hook.split())
        dur = pkg.get("estimated_duration", "")
        caption = pkg.get("short_caption", "")
        comments = pkg.get("suggested_comments", [])
        issues = []
        if word_count > 8:
            issues.append(f"hook={word_count} words")
        if dur not in ("8s", "10s"):
            issues.append(f"duration={dur}")
        if len(caption) > 300:
            issues.append(f"caption={len(caption)} chars")
        if len(comments) < 3:
            issues.append(f"comments={len(comments)}")
        if issues:
            print(f"  WARNING [{pkg.get('id')}]: {', '.join(issues)}")

    print("Generating weekly calendar...")
    calendar = await generate_weekly_calendar(llm)
    if not calendar:
        print("ERROR: Failed to generate weekly calendar")
        return

    # Assign IDs and week to calendar
    for day in calendar:
        if not day.get("id"):
            day["id"] = f"cal_{week_label}_{day.get('day', 'unknown')}"
        day["week"] = week_label

    print(f"  Generated {len(calendar)} calendar days")

    # Write to Google Sheet
    print("Writing to Google Sheet...")
    service = _get_sheets_service()

    # Content Packages tab
    pkg_headers = [
        "ID", "Week", "Format", "Hook", "Short Caption", "Suggested Comments",
        "Caption", "Hashtags", "Duration", "Mission Area", "Content Type",
        "Mission Score", "Difficulty", "Status",
    ]

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

    # Weekly Calendar tab
    cal_headers = [
        "ID", "Week", "Day", "Format", "Hook", "Short Caption", "Suggested Comments",
        "Brief", "Hashtags", "Duration", "Difficulty", "Status",
    ]

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

    if not args.append:
        _clear_tab(service, PACKAGES_TAB)
        _clear_tab(service, CALENDAR_TAB)

    _write_rows(service, PACKAGES_TAB, pkg_headers, pkg_rows)
    _write_rows(service, CALENDAR_TAB, cal_headers, cal_rows)

    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}"
    print(f"\nDone! Sheet: {sheet_url}")
    print(f"  {len(packages)} content packages in '{PACKAGES_TAB}'")
    print(f"  {len(calendar)} calendar days in '{CALENDAR_TAB}'")


if __name__ == "__main__":
    asyncio.run(main())
