#!/usr/bin/env python3
"""One-time DSDN TikTok analysis: discover trends, score alignment,
generate content packages + weekly calendar, output to Google Sheet."""

from __future__ import annotations

import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


async def main() -> None:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

    from cmo_agent.llm.anthropic import AnthropicLLM
    from cmo_agent.llm.base import Message
    from cmo_agent.tiktok.hooks import HOOK_FORMULAS, format_hook_library_for_prompt
    from cmo_agent.tiktok.trends import discover_trends, score_dsdn_alignment

    # ── 1. Set up LLM ────────────────────────────────────────────────
    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set in .env")
        sys.exit(1)
    llm = AnthropicLLM(
        api_key=api_key,
        model=os.getenv("MODEL_WRITING", "claude-sonnet-4-5-20250929"),
        max_tokens=8192,
    )

    # ── 2. Discover trends ────────────────────────────────────────────
    print("Discovering TikTok trends...")
    trends = await discover_trends(llm)
    print(f"  Found {len(trends)} trends")

    # ── 3. Score DSDN alignment ───────────────────────────────────────
    print("Scoring DSDN mission alignment...")
    trends = await score_dsdn_alignment(trends, llm)
    scored_trends = sorted(
        [t for t in trends if t.dsdn_alignment_score is not None],
        key=lambda t: t.dsdn_alignment_score or 0,
        reverse=True,
    )
    print(f"  {len(scored_trends)} trends scored")

    # ── 4. Generate content packages for top 5 trends ─────────────────
    top_trends = scored_trends[:5]
    topics_desc = "; ".join([f"{t.name} ({t.description[:60]})" for t in top_trends])

    hook_library = format_hook_library_for_prompt()
    pkg_prompt = f"""Generate 5 complete TikTok content packages for DSDN based on these top trends:
{topics_desc}

HOOK FORMULAS (select from these):
{hook_library}

For each package, output a JSON object with ALL of these fields:
- content_format: one of trending_sound_overlay/photo_carousel/talking_head_broll/transformation/day_in_the_life/educational_overlay/community_story/awareness_facts
- content_type: one of educational/emotional/community/awareness/fundraising/celebration
- mission_area: one of diagnosis_delivery/parent_connection/medical_information/family_reach/medical_relationships/sustainable_funding/engagement_0_to_3
- hook: The attention-grabbing first line (from hook formula library)
- hook_formula_used: The hook formula id used
- script_segments: Array of {{time_range, narration, visual_direction, text_overlay, music_note}}
- caption: TikTok caption (MAX 2200 characters), includes call-to-action
- hashtags: Array of 5-10 hashtags
- sound_suggestion: Recommended sound or "Original voiceover"
- editing_instructions: Array of {{step, action, description, timing}}
- media_suggestions: Array of {{usage, fallback_description}}
- text_overlays: Array of overlay text strings
- estimated_duration: "15s", "30s", or "60s"
- cta: Call to action
- sensitivity_notes: Array of sensitivity considerations
- dsdn_mission_score: 1-5 (must be 3+)
- trend_relevance_score: 1-5
- production_difficulty: easy/medium/hard

RULES:
- Person-first language: "child with Down syndrome", not "Down syndrome child"
- No em dashes or en dashes in ANY text
- Caption MUST be under 2200 characters
- Every package must score 3+ on dsdn_mission_score
- Use DIFFERENT content_format for each package to ensure variety

Output ONLY a JSON array of 5 package objects. No markdown, no explanation."""

    print("Generating content packages...")
    # Generate packages one at a time to avoid token truncation
    packages = []
    for i, trend in enumerate(top_trends[:5]):
        single_prompt = f"""Generate 1 complete TikTok content package for DSDN about this trend:
{trend.name}: {trend.description}

HOOK FORMULAS (select from these):
{hook_library}

Output a JSON object with ALL of these fields:
- content_format: one of trending_sound_overlay/photo_carousel/talking_head_broll/transformation/day_in_the_life/educational_overlay/community_story/awareness_facts
- content_type: one of educational/emotional/community/awareness/fundraising/celebration
- mission_area: one of diagnosis_delivery/parent_connection/medical_information/family_reach/medical_relationships/sustainable_funding/engagement_0_to_3
- hook: The attention-grabbing first line (from hook formula library)
- hook_formula_used: The hook formula id used
- script_segments: Array of {{time_range, narration, visual_direction, text_overlay}}
- caption: TikTok caption (MAX 2200 characters), includes call-to-action
- hashtags: Array of 5-10 hashtags
- sound_suggestion: Recommended sound or "Original voiceover"
- editing_instructions: Array of {{step, action, description, timing}}
- media_suggestions: Array of {{usage, fallback_description}}
- text_overlays: Array of overlay text strings
- estimated_duration: "15s", "30s", or "60s"
- cta: Call to action
- sensitivity_notes: Array of sensitivity considerations
- dsdn_mission_score: 1-5 (must be 3+)
- trend_relevance_score: 1-5
- production_difficulty: easy/medium/hard

RULES:
- Person-first language: "child with Down syndrome", not "Down syndrome child"
- No em dashes or en dashes in ANY text
- Caption MUST be under 2200 characters

Output ONLY valid JSON. No markdown, no explanation."""

        print(f"  Package {i + 1}/5: {trend.name}...")
        resp = await llm.complete(
            messages=[Message(role="user", content=single_prompt)],
            temperature=0.7,
        )
        pkg = _parse_json_object(resp.content)
        if pkg:
            packages.append(pkg)
    print(f"  Generated {len(packages)} packages")

    # ── 5. Generate weekly calendar ───────────────────────────────────
    trends_context = "\n".join([f"- {t.name}: {t.description}" for t in top_trends])
    cal_prompt = f"""Create a 7-day TikTok content calendar for DSDN.

CURRENT TRENDS (incorporate where relevant):
{trends_context}

HOOK FORMULAS:
{hook_library}

REQUIREMENTS:
- 7 days, one primary post per day (Monday through Sunday)
- Use AT LEAST 5 different content_format values across the week
- Mix content_types: at least 3 different types
- Mix mission_areas: at least 3 different areas
- No two consecutive days should have the same content_format
- Include at least one educational, one emotional, and one community post
- Person-first language: "child with Down syndrome", not "Down syndrome child"
- No em dashes or en dashes

For each day, output:
- day: Monday/Tuesday/etc.
- content_format: one of the 8 formats
- content_type: educational/emotional/community/awareness/fundraising/celebration
- mission_area: the DSDN mission area
- hook: Attention-grabbing opening (from hook formula library)
- hook_formula_used: The formula id
- brief: 2-3 sentence content description
- estimated_duration: "15s", "30s", or "60s"
- production_difficulty: easy/medium/hard
- hashtags: 5-8 hashtags
- caption_preview: First 100 chars of the caption

Output ONLY a JSON array of 7 day objects. No markdown, no explanation."""

    print("Generating weekly calendar...")
    cal_resp = await llm.complete(
        messages=[Message(role="user", content=cal_prompt)],
        temperature=0.7,
    )
    calendar = _parse_json_array(cal_resp.content)
    print(f"  Generated {len(calendar)}-day calendar")

    # ── 6. Build Google Sheet ─────────────────────────────────────────
    print("Creating Google Sheet...")
    sheet_url = _create_google_sheet(scored_trends, packages, calendar, HOOK_FORMULAS)
    print(f"\nDone! Google Sheet: {sheet_url}")


def _parse_json_array(text: str) -> list:
    """Extract a JSON array from LLM text."""
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


def _parse_json_object(text: str) -> dict:
    """Extract a JSON object from LLM text."""
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    for marker in ("```json", "```"):
        if marker in text:
            try:
                start = text.index(marker) + len(marker)
                end = text.index("```", start)
                result = json.loads(text[start:end].strip())
                if isinstance(result, dict):
                    return result
            except (json.JSONDecodeError, ValueError):
                pass

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            result = json.loads(text[start : end + 1])
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return {}


def _create_google_sheet(trends, packages, calendar, hook_formulas) -> str:
    """Create a multi-tab Google Sheet with all analysis results."""
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
        share_file_restricted,
    )

    oauth_path = os.path.join(
        os.path.dirname(__file__), "..", "data", "google-token.json"
    )
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
    ]
    credentials = get_google_credentials(
        oauth_token_path=oauth_path,
        service_account_path="",
        scopes=scopes,
    )
    if not credentials:
        raise RuntimeError("No Google credentials found")

    sheets_svc = build("sheets", "v4", credentials=credentials)
    drive_svc = build("drive", "v3", credentials=credentials)

    # Create spreadsheet with 4 tabs
    spreadsheet = (
        sheets_svc.spreadsheets()
        .create(
            body={
                "properties": {"title": "DSDN TikTok Content Analysis"},
                "sheets": [
                    {"properties": {"title": "Trends", "index": 0}},
                    {"properties": {"title": "Content Packages", "index": 1}},
                    {"properties": {"title": "Weekly Calendar", "index": 2}},
                    {"properties": {"title": "Hook Formulas", "index": 3}},
                ],
            },
            fields="spreadsheetId,spreadsheetUrl,sheets",
        )
        .execute()
    )
    sheet_id = spreadsheet["spreadsheetId"]
    sheet_url = spreadsheet["spreadsheetUrl"]
    tab_ids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in spreadsheet["sheets"]}

    # ── Tab 1: Trends ─────────────────────────────────────────────────
    trend_headers = [
        "Name",
        "Type",
        "Description",
        "DSDN Score",
        "Niche?",
        "Sensitivity Flags",
        "Suggested Formats",
    ]
    trend_rows = []
    for t in trends:
        trend_rows.append(
            [
                t.name,
                t.trend_type.value,
                t.description,
                t.dsdn_alignment_score or "",
                "Yes" if t.niche_relevance else "No",
                ", ".join(t.sensitivity_flags) if t.sensitivity_flags else "",
                ", ".join(f.value for f in t.suggested_formats)
                if t.suggested_formats
                else "",
            ]
        )
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Trends'!A1",
        valueInputOption="RAW",
        body={"values": [trend_headers] + trend_rows},
    ).execute()

    # ── Tab 2: Content Packages ───────────────────────────────────────
    pkg_headers = [
        "Format",
        "Content Type",
        "Mission Area",
        "Hook",
        "Hook Formula",
        "Caption",
        "Hashtags",
        "Sound",
        "Duration",
        "Difficulty",
        "Mission Score",
        "Trend Score",
        "CTA",
        "Sensitivity Notes",
        "Script (full)",
        "Editing Instructions",
        "Media Direction",
    ]
    pkg_rows = []
    for p in packages:
        # Build script text
        segments = p.get("script_segments", [])
        script_text = ""
        for seg in segments:
            tr = seg.get("time_range", "")
            narr = seg.get("narration", "")
            vis = seg.get("visual_direction", "")
            overlay = seg.get("text_overlay", "")
            script_text += f"[{tr}] {narr}"
            if vis:
                script_text += f" | Visual: {vis}"
            if overlay:
                script_text += f" | Overlay: {overlay}"
            script_text += "\n"

        # Build editing instructions text
        edits = p.get("editing_instructions", [])
        edit_text = ""
        for e in edits:
            step = e.get("step", "")
            action = e.get("action", "")
            desc = e.get("description", "")
            timing = e.get("timing", "")
            edit_text += f"{step}. [{action}] {desc}"
            if timing:
                edit_text += f" @{timing}"
            edit_text += "\n"

        # Build media suggestions text
        media = p.get("media_suggestions", [])
        media_text = ""
        for m in media:
            usage = m.get("usage", "")
            fallback = m.get("fallback_description", "")
            fname = m.get("filename", "")
            media_text += f"{usage}: {fname or fallback}\n"

        pkg_rows.append(
            [
                p.get("content_format", ""),
                p.get("content_type", ""),
                p.get("mission_area", ""),
                p.get("hook", ""),
                p.get("hook_formula_used", ""),
                p.get("caption", ""),
                ", ".join(p.get("hashtags", [])),
                p.get("sound_suggestion", ""),
                p.get("estimated_duration", ""),
                p.get("production_difficulty", ""),
                p.get("dsdn_mission_score", ""),
                p.get("trend_relevance_score", ""),
                p.get("cta", ""),
                ", ".join(p.get("sensitivity_notes", [])),
                script_text.strip(),
                edit_text.strip(),
                media_text.strip(),
            ]
        )
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Content Packages'!A1",
        valueInputOption="RAW",
        body={"values": [pkg_headers] + pkg_rows},
    ).execute()

    # ── Tab 3: Weekly Calendar ────────────────────────────────────────
    cal_headers = [
        "Day",
        "Format",
        "Content Type",
        "Mission Area",
        "Hook",
        "Hook Formula",
        "Brief",
        "Duration",
        "Difficulty",
        "Hashtags",
        "Caption Preview",
    ]
    cal_rows = []
    for d in calendar:
        cal_rows.append(
            [
                d.get("day", ""),
                d.get("content_format", ""),
                d.get("content_type", ""),
                d.get("mission_area", ""),
                d.get("hook", ""),
                d.get("hook_formula_used", ""),
                d.get("brief", ""),
                d.get("estimated_duration", ""),
                d.get("production_difficulty", ""),
                ", ".join(d.get("hashtags", [])),
                d.get("caption_preview", ""),
            ]
        )
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Weekly Calendar'!A1",
        valueInputOption="RAW",
        body={"values": [cal_headers] + cal_rows},
    ).execute()

    # ── Tab 4: Hook Formulas ──────────────────────────────────────────
    hook_headers = [
        "ID",
        "Name",
        "Template",
        "Examples",
        "Best For",
    ]
    hook_rows = []
    for h in hook_formulas:
        hook_rows.append(
            [
                h["id"],
                h["name"],
                h["template"],
                "\n".join(h.get("examples", [])),
                ", ".join(h.get("best_for", [])),
            ]
        )
    sheets_svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range="'Hook Formulas'!A1",
        valueInputOption="RAW",
        body={"values": [hook_headers] + hook_rows},
    ).execute()

    # ── Formatting ────────────────────────────────────────────────────
    format_requests = []
    for tab_name, sid in tab_ids.items():
        # Bold header row
        format_requests.append(
            {
                "repeatCell": {
                    "range": {
                        "sheetId": sid,
                        "startRowIndex": 0,
                        "endRowIndex": 1,
                    },
                    "cell": {
                        "userEnteredFormat": {
                            "textFormat": {"bold": True},
                            "backgroundColor": {
                                "red": 0.85,
                                "green": 0.92,
                                "blue": 0.98,
                            },
                        }
                    },
                    "fields": "userEnteredFormat(textFormat,backgroundColor)",
                }
            }
        )
        # Freeze header
        format_requests.append(
            {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sid,
                        "gridProperties": {"frozenRowCount": 1},
                    },
                    "fields": "gridProperties.frozenRowCount",
                }
            }
        )
        # Auto-resize columns
        format_requests.append(
            {
                "autoResizeDimensions": {
                    "dimensions": {
                        "sheetId": sid,
                        "dimension": "COLUMNS",
                        "startIndex": 0,
                        "endIndex": 20,
                    }
                }
            }
        )

    sheets_svc.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": format_requests},
    ).execute()

    # ── Share & organize ──────────────────────────────────────────────
    share_file_restricted(drive_svc, sheet_id)

    folder_id = ensure_drive_folder(drive_svc)
    if folder_id:
        move_file_to_folder(drive_svc, sheet_id, folder_id)

    return sheet_url


if __name__ == "__main__":
    asyncio.run(main())
