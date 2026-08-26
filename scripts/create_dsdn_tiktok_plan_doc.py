"""Create a Google Doc: DSDN TikTok Trends & Content Agent - Implementation Plan.

Builds the document structure in-memory and calls DocsAgent._build_google_doc()
directly, bypassing LLM generation so every detail is accurate.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _build_structure() -> dict:
    """Return the full document structure dict."""
    return {
        "title": "DSDN TikTok Trends & Content Agent - Implementation Plan",
        "include_toc": True,
        "sections": [
            # ── 1. Executive Summary ─────────────────────────────────
            {
                "heading": "Executive Summary",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "DSDN has 106,000+ social media followers and 3 million+ views in "
                            "FY25, but currently lacks a systematic way to capitalize on TikTok "
                            "trends with mission-aligned content. This plan introduces the DSDN "
                            "TikTok Trends & Content Agent (Phase 26 of the CMO Agent system), "
                            "an AI-powered sub-agent that discovers TikTok trends, matches them "
                            "to DSDN's mission, produces ready-to-edit content packages with "
                            "recurring series support, and tracks performance to improve over time."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Phase 1 (this plan) delivers content planning only: scripts, captions, "
                            "hashtags, editing instructions, and media direction. Phase 2 (deferred) "
                            "will add rendered video output and expansion to Instagram Reels and "
                            "YouTube Shorts."
                        ),
                    },
                ],
            },
            # ── 2. Goals & Success Criteria ──────────────────────────
            {
                "heading": "Goals and Success Criteria",
                "level": 1,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Systematically discover and evaluate TikTok trends for DSDN relevance",
                            "Generate complete, ready-to-edit content packages (script, caption, hashtags, editing instructions)",
                            "Support recurring content series with episode tracking and cadence management",
                            "Catalog DSDN's photo/video library using vision AI for intelligent media matching",
                            "Track published content performance and generate improvement insights",
                            "Deliver a daily Slack digest of top trend-matched content ideas",
                            "Maintain DSDN's sensitivity standards, person-first language, and mission alignment in all output",
                        ],
                    },
                ],
            },
            {
                "heading": "Success Metrics",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Metric", "Target", "Measurement"],
                        "rows": [
                            [
                                "Content packages generated per week",
                                "5-10",
                                "Count of packages with status=draft",
                            ],
                            [
                                "Trends discovered per scan",
                                "8-12",
                                "Cache file trend count",
                            ],
                            [
                                "DSDN alignment score average",
                                "3.5+/5",
                                "Average across generated packages",
                            ],
                            [
                                "Content variety",
                                "4+ formats per week",
                                "Unique content_format values in weekly calendar",
                            ],
                            [
                                "Person-first language compliance",
                                "100%",
                                "Zero violations in generated output",
                            ],
                        ],
                    },
                ],
            },
            # ── 3. Architecture ──────────────────────────────────────
            {
                "heading": "Architecture",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The agent follows the established CMO Agent sub-agent pattern. A single "
                            "DSDNTikTokAgent (inheriting from BaseAgent) is registered as a tool on "
                            "the CMO Orchestrator. It uses a tiktok/ utility package for models, "
                            "trend caching, media cataloging, hook formulas, and performance tracking."
                        ),
                    },
                ],
            },
            {
                "heading": "Agent Position in the System",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The DSDN TikTok Agent sits alongside the existing DSDN-specific agents "
                            "(DSDN Ideas, Grant Intelligence, Grant Writing, Corporate Sponsorship, "
                            "Ecosystem Intelligence, Outreach Scanner). It always targets "
                            "workspace_id='dsdn' and imports DSDN constants (DSDN_ORG_PROFILE, "
                            "DSDN_PROGRAMS_DETAIL, DSDN_CURRENT_INITIATIVES) for mission context."
                        ),
                    },
                ],
            },
            {
                "heading": "Boundaries with Other Agents",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Agent", "Boundary"],
                        "rows": [
                            [
                                "Social Media Manager",
                                "Handles general social content calendars and platform strategy across all brands. TikTok Agent is DSDN-specific and TikTok-focused.",
                            ],
                            [
                                "DSDN Ideas Agent",
                                "Generates strategic growth ideas for DSDN (not content packages). TikTok Agent produces ready-to-edit TikTok content.",
                            ],
                            [
                                "Video Agent",
                                "Generates AI video clips from prompts. TikTok Agent produces content plans/scripts that a human edits. Phase 2 may chain to Video Agent for rendering.",
                            ],
                            [
                                "Writer Agent",
                                "Handles long-form content, newsletters, articles. TikTok Agent handles short-form TikTok scripts and captions.",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Data Flow",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Trend Discovery: LLM scans for current TikTok trends (general + DS/disability/parenting niche). Results cached with 4-hour TTL (Time To Live).",
                            "Alignment Scoring: Each trend is scored 1-5 on DSDN mission alignment. Sensitivity flags are identified.",
                            "Content Generation: High-scoring trends are matched to content formats and hook formulas. The LLM generates complete content packages.",
                            "Media Matching: If a media catalog exists, packages reference specific files. Otherwise, descriptive media direction is provided.",
                            "Draft Storage: Packages are stored as drafts in the database (content_type='tiktok_content_package').",
                            "Performance Loop: After publishing, metrics are recorded and fed back into future generation.",
                        ],
                    },
                ],
            },
            # ── 4. New Files ─────────────────────────────────────────
            {
                "heading": "New Files",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All new code lives in two locations: the tiktok/ utility package "
                            "(6 files) and the agent module (1 file), plus 2 test files."
                        ),
                    },
                ],
            },
            {
                "heading": "tiktok/models.py - Pydantic Models",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All data models for the TikTok system. Uses Pydantic v2 with "
                            "field validators."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Model", "Purpose", "Key Fields"],
                        "rows": [
                            [
                                "TikTokTrend",
                                "A discovered or manually-input TikTok trend",
                                "trend_type (hashtag/sound/format/challenge/niche_community), name, description, view_count, dsdn_alignment_score (1-5), expires_at (72h TTL), sensitivity_flags, niche_relevance",
                            ],
                            [
                                "ContentSeries",
                                "A recurring content series concept",
                                "series_name, series_concept, recurring_format, content_type, mission_area, episode_cadence, hook_formula_id, episodes[], total_planned_episodes",
                            ],
                            [
                                "TikTokContentPackage",
                                "A complete content package ready for production",
                                "content_format (8 types), hook, hook_formula_used, script_segments[], caption (max 2200 chars), hashtags, editing_instructions[], media_suggestions[], dsdn_mission_score (1-5), trend_relevance_score (1-5), production_difficulty",
                            ],
                            [
                                "ScriptSegment",
                                "A timed segment within a TikTok script",
                                "time_range, narration, visual_direction, text_overlay, music_note",
                            ],
                            [
                                "EditingInstruction",
                                "A single editing step for post-production",
                                "step, action (cut_to/overlay_text/add_transition/speed_change/zoom/split_screen), description, timing",
                            ],
                            [
                                "MediaSuggestion",
                                "A media file suggestion for a package",
                                "catalog_entry_id, filename, usage (hero_shot/b_roll/carousel_slide_N), clip_range, fallback_description",
                            ],
                            [
                                "CatalogEntry",
                                "An entry in the vision-AI media catalog",
                                "filename, file_path, media_type (photo/video), description (vision-generated), tags, people_count, setting, emotion, activities",
                            ],
                            [
                                "PerformanceRecord",
                                "Metrics for a published TikTok video",
                                "package_id, views, likes, comments, shares, saves, profile_visits, watch_time_avg",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "8 Content Formats",
                "level": 3,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Format", "Description", "Difficulty"],
                        "rows": [
                            [
                                "trending_sound_overlay",
                                "DSDN photos/videos set to trending audio",
                                "Easy",
                            ],
                            [
                                "photo_carousel",
                                "Multiple photos with music + text overlays",
                                "Easy",
                            ],
                            [
                                "talking_head_broll",
                                "Spokesperson talking over supplementary footage",
                                "Medium",
                            ],
                            [
                                "transformation",
                                "Growth, milestone, journey stories",
                                "Medium",
                            ],
                            [
                                "day_in_the_life",
                                "Authentic family moments",
                                "Easy",
                            ],
                            [
                                "educational_overlay",
                                "Facts, stats, resources with visual backgrounds",
                                "Easy",
                            ],
                            [
                                "community_story",
                                "Parent testimonials, connection moments",
                                "Medium",
                            ],
                            [
                                "awareness_facts",
                                "Quick-hit Down syndrome facts for general audience",
                                "Easy",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "tiktok/hooks.py - Hook Formula Library",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "A built-in library of 10 proven TikTok hook formulas adapted for DSDN. "
                            "Each formula has a template with variable slots, DSDN-specific examples, "
                            "and content type recommendations. The agent selects appropriate hooks "
                            "based on the content type being generated."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Hook Formula", "Template", "Best For"],
                        "rows": [
                            [
                                "Curiosity Gap",
                                "Nobody tells you this about {topic}...",
                                "Educational, Awareness",
                            ],
                            [
                                "Emotional Reveal",
                                "The moment {event} changed everything.",
                                "Emotional, Community",
                            ],
                            [
                                "POV",
                                "POV: {scenario}",
                                "Emotional, Community, Awareness",
                            ],
                            [
                                "Direct Question",
                                "What would you do if {scenario}?",
                                "Educational, Awareness",
                            ],
                            [
                                "List / Countdown",
                                "{N} things I wish I knew about {topic}",
                                "Educational, Awareness",
                            ],
                            [
                                "Before vs After",
                                "Before {event} vs after",
                                "Transformation, Community",
                            ],
                            [
                                "Pattern Interrupt",
                                "Stop scrolling if {condition}",
                                "Awareness, Community",
                            ],
                            [
                                "Wait For It",
                                "[Visual setup]... wait for it...",
                                "Emotional, Celebration",
                            ],
                            [
                                "Myth Buster",
                                "People think {myth}. Here's the truth.",
                                "Educational, Awareness",
                            ],
                            [
                                "Day in the Life",
                                "A day in the life of {persona}",
                                "Community, Awareness",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "tiktok/media_catalog.py - Vision-AI Media Catalog",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "JSONL-based media catalog that uses Claude's vision capabilities to "
                            "generate rich descriptions of DSDN's photos and videos. This enables "
                            "intelligent media matching when generating content packages."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "scan_directory(path): Find photos (.jpg, .png, .heic, .webp) and videos (.mp4, .mov, .m4v) recursively",
                            "catalog_file(path, llm): Send image to Claude vision (Haiku) for rich description - people count, setting, emotion, activities, tags",
                            "search(query, media_type, limit): Keyword search across all descriptions and tags",
                            "get_uncataloged(file_paths): Return files not yet in the catalog (for incremental cataloging)",
                            "Storage: data/dsdn/tiktok_media_catalog.jsonl, deduped by filename",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "When the media catalog is empty (no photos/videos organized yet), "
                            "content packages include descriptive media direction instead of specific "
                            "file references. The agent works fully without a media library."
                        ),
                    },
                ],
            },
            {
                "heading": "tiktok/trends.py - Trend Discovery & Caching",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "LLM-powered trend discovery with a JSON cache layer. Prompts the LLM "
                            "to identify current TikTok trends (both general and niche "
                            "DS/disability/parenting community trends)."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "discover_trends(llm): LLM identifies 8-12 current trends (sounds, hashtags, challenges, formats)",
                            "add_manual_trend(name, description, trend_type): Accept user-described trends",
                            "score_dsdn_alignment(trends, llm): LLM scores each trend 1-5 on DSDN mission fit, flags sensitivity concerns",
                            "Cache with 4-hour TTL (Time To Live) at data/dsdn/tiktok_trends.json",
                            "72-hour trend expiration: trends auto-expire after 72 hours (TikTok trend lifecycle)",
                        ],
                    },
                ],
            },
            {
                "heading": "tiktok/performance.py - Performance Tracking",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "JSONL-based performance tracking for published TikTok content. Stores "
                            "views, likes, comments, shares, saves, profile visits, and watch time."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "record_performance(record): Append metrics to JSONL store",
                            "get_top_performers(limit, sort_by): Find best-performing content by any metric",
                            "get_series_performance(series_id): Aggregate metrics across a content series",
                            "get_format_performance(): Which content formats perform best overall",
                            "generate_insights(llm): LLM analyzes performance data and recommends adjustments for future content",
                            "Storage: data/dsdn/tiktok_performance.jsonl",
                        ],
                    },
                ],
            },
            # ── 5. Agent: 9 Tools ────────────────────────────────────
            {
                "heading": "Agent Tools (9 Total)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The DSDNTikTokAgent (agents/dsdn_tiktok.py) inherits from BaseAgent "
                            "and registers 9 tools. The agent always targets workspace_id='dsdn'."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Tool", "Purpose", "Output"],
                        "rows": [
                            [
                                "scan_tiktok_trends",
                                "LLM-powered trend discovery (general TikTok + DS/disability/parenting niche). Caches results with 4h TTL.",
                                "List of TikTokTrend objects with descriptions and suggested formats",
                            ],
                            [
                                "input_trend",
                                "Accept a manually described trend from the user. Auto-scores DSDN alignment.",
                                "Single TikTokTrend with alignment score",
                            ],
                            [
                                "match_trends_to_dsdn",
                                "Score cached trends on DSDN mission alignment (1-5). Filter by minimum score and sensitivity flags.",
                                "Filtered and scored trend list",
                            ],
                            [
                                "catalog_media_library",
                                "Scan a directory, generate vision-AI descriptions for uncataloged files, update JSONL catalog.",
                                "Catalog stats (total, photos, videos, newly cataloged)",
                            ],
                            [
                                "search_media",
                                "Keyword search across the media catalog. Filter by media type (photo/video).",
                                "List of matching CatalogEntry objects",
                            ],
                            [
                                "create_content_series",
                                "Design a recurring series concept with template, cadence, planned episodes, and hook formula selection.",
                                "ContentSeries object with episode briefs",
                            ],
                            [
                                "generate_content_package",
                                "Generate 1-5 complete TikTok content packages for a trend/topic/series episode. Uses hook formulas. Stores as draft.",
                                "List of TikTokContentPackage objects with scripts, captions, hashtags, editing instructions",
                            ],
                            [
                                "generate_weekly_calendar",
                                "Generate a full week of varied content (mix of formats, types, series episodes). Ensures variety across content pillars.",
                                "7-day content calendar with daily package assignments",
                            ],
                            [
                                "record_performance",
                                "Log performance metrics for a published video. When enough data exists, generates improvement insights.",
                                "Confirmation + optional insights report",
                            ],
                        ],
                    },
                ],
            },
            # ── 6. Workflows ─────────────────────────────────────────
            {
                "heading": "Workflows",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "The agent supports five primary workflows, each building on the tools above.",
                    },
                ],
            },
            {
                "heading": "Workflow 1: Trend-Based Content Ideas",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "scan_tiktok_trends - discover current trends",
                            "match_trends_to_dsdn - score alignment, filter by min score",
                            "generate_content_package - create packages for top trends",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Use case: 'What TikTok trends can DSDN capitalize on right now?'",
                    },
                ],
            },
            {
                "heading": "Workflow 2: Specific Trend Content",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "input_trend - user describes a trend they've seen",
                            "generate_content_package - create packages for that trend",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Use case: 'I saw a trend using the sound XYZ, create content for DSDN'",
                    },
                ],
            },
            {
                "heading": "Workflow 3: Weekly Content Calendar",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "scan_tiktok_trends - discover current trends",
                            "match_trends_to_dsdn - score and filter",
                            "generate_weekly_calendar - create 7-day plan with variety",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Use case: 'Generate a week of TikTok content for DSDN'",
                    },
                ],
            },
            {
                "heading": "Workflow 4: Recurring Series",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "create_content_series - design series concept, template, cadence",
                            "generate_content_package - create package for each episode",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Use case: 'Create a TikTok series about DSDN Rockin' Retreats'",
                    },
                ],
            },
            {
                "heading": "Workflow 5: Performance Loop",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "record_performance - log metrics after publishing",
                            "Insights auto-generated when enough data exists",
                            "Insights inform future content generation prompts",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": "Use case: 'Record metrics for our last TikTok: 50K views, 3K likes'",
                    },
                ],
            },
            # ── 7. Content Package Detail ────────────────────────────
            {
                "heading": "Content Package Detail",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Each generated content package includes the following components:",
                    },
                    {
                        "type": "table",
                        "headers": ["Component", "Description", "Example"],
                        "rows": [
                            [
                                "Hook (first 1-3 seconds)",
                                "Attention-grabbing opening line from the hook formula library",
                                "\"Nobody tells you this about a Down syndrome diagnosis...\"",
                            ],
                            [
                                "Script Segments",
                                "Timed script with narration, visual direction, text overlays, and music notes",
                                "0:00-0:03: Hook (text overlay: \"What they don't tell you\")",
                            ],
                            [
                                "Caption",
                                "TikTok caption text (max 2200 characters) with call-to-action",
                                "\"When we got our daughter's diagnosis, we felt alone. Then we found DSDN...\"",
                            ],
                            [
                                "Hashtags",
                                "Relevant hashtags mixing trending + evergreen + DSDN-specific",
                                "#DownSyndrome #DSDN #T21 #NewParent #DisabilityTikTok",
                            ],
                            [
                                "Sound Suggestion",
                                "Recommended trending sound or original audio direction",
                                "\"Use trending sound: [name]\" or \"Original voiceover\"",
                            ],
                            [
                                "Editing Instructions",
                                "Step-by-step post-production guide",
                                "Step 1: Cut to hero shot at 0:03. Step 2: Overlay text at 0:05.",
                            ],
                            [
                                "Media Suggestions",
                                "Specific files from catalog OR descriptive fallback direction",
                                "\"Use family_retreat_2024_03.jpg as hero\" or \"Warm photo of parent holding baby\"",
                            ],
                            [
                                "Sensitivity Notes",
                                "Flags for emotional content, privacy considerations",
                                "\"Ensure consent for any family photos. Frame diagnosis positively.\"",
                            ],
                            [
                                "Scores",
                                "Mission alignment (1-5) and trend relevance (1-5)",
                                "Mission: 5/5, Trend: 4/5",
                            ],
                        ],
                    },
                ],
            },
            # ── 8. Sensitivity & Safety Rules ────────────────────────
            {
                "heading": "Sensitivity and Safety Rules",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All content generated by this agent must comply with DSDN's "
                            "sensitivity standards. These rules are embedded in the agent's "
                            "system prompt and enforced during generation."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Person-first language always: 'child with Down syndrome', never 'Down syndrome child' or 'Down's kid'",
                            "Down syndrome is never capitalized as 'Down Syndrome' (lowercase 's' in syndrome)",
                            "Never use deficit language: avoid 'suffers from', 'afflicted by', 'victim of', 'confined to'",
                            "Frame diagnosis as a journey, not a tragedy. Focus on connection, community, and hope",
                            "Never share identifiable information about families without explicit consent",
                            "Avoid medical claims or advice. Direct to DSDN resources and medical professionals",
                            "Flag content involving loss, difficult diagnoses, or medical complications for human review",
                            "Never exploit children or families for engagement. Celebrate, don't sensationalize",
                            "All content must be medically accurate and unbiased",
                            "Anti-AI writing rules: no em dashes, no en dashes, no mid-sentence bolding",
                        ],
                    },
                ],
            },
            # ── 9. System Prompt Design ──────────────────────────────
            {
                "heading": "System Prompt Design",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The agent's system prompt includes the full DSDN organization context "
                            "from dsdn_constants.py (DSDN_ORG_PROFILE, DSDN_PROGRAMS_DETAIL, "
                            "DSDN_CURRENT_INITIATIVES), the complete hook formula library, all 8 "
                            "content format definitions, sensitivity rules, person-first language "
                            "requirements, anti-AI writing rules, and TikTok platform best practices."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "The prompt instructs the LLM to follow the 5 workflows above, always "
                            "use the hook formula library, enforce caption length limits, vary "
                            "content across the 8 formats, and include sensitivity notes for "
                            "emotionally charged content."
                        ),
                    },
                ],
            },
            # ── 10. Orchestrator Wiring ──────────────────────────────
            {
                "heading": "Orchestrator Integration",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The agent is wired into the CMO Orchestrator following the standard "
                            "sub-agent pattern."
                        ),
                    },
                ],
            },
            {
                "heading": "orchestrator.py Changes",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Add dsdn_tiktok_agent: Optional[BaseAgent] = None constructor parameter",
                            "Store as self._dsdn_tiktok",
                            "Register tool with description: 'Delegate a DSDN TikTok task: scan trends, match to mission, catalog photos/videos with vision AI, design content series, generate content packages with hook formulas, create weekly content calendars, and track performance. Always uses workspace_id=dsdn.'",
                            "Add delegation guideline in system prompt: 'When asked about DSDN TikTok content, TikTok trends for DSDN, TikTok series, or DSDN short-form video content, delegate to dsdn_tiktok_agent'",
                            "Add boundary rule: 'BOUNDARY: DSDN TikTok Agent handles TikTok-specific content packages for DSDN. Social Media Agent handles general social strategy. DSDN Ideas Agent handles strategic ideas. Video Agent handles AI video generation.'",
                        ],
                    },
                ],
            },
            {
                "heading": "factory.py Changes",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Import DSDNTikTokAgent from agents.dsdn_tiktok",
                            "Instantiate with writing_llm (Sonnet) + scanning_llm (Haiku for vision cataloging)",
                            "Pass to orchestrator constructor as dsdn_tiktok_agent=",
                            "Register in AgentRegistry",
                        ],
                    },
                ],
            },
            {
                "heading": "session.py Changes",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Add 'dsdn_tiktok_agent' to the _format_action() map: "
                            "'Delegated to DSDN TikTok Agent: {instruction}'"
                        ),
                    },
                ],
            },
            {
                "heading": "config.py Changes",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "dsdn_tiktok_media_dir: str = '' (path to DSDN media folder, empty until organized)",
                            "dsdn_tiktok_trends_cache: str = 'data/dsdn/tiktok_trends.json'",
                            "dsdn_tiktok_catalog_path: str = 'data/dsdn/tiktok_media_catalog.jsonl'",
                            "dsdn_tiktok_performance_path: str = 'data/dsdn/tiktok_performance.jsonl'",
                            "slack_dsdn_tiktok_channel: str = '#dsdn-tiktok' (Slack channel for daily digest)",
                        ],
                    },
                ],
            },
            {
                "heading": "routing/catalog.py Changes",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Add to AGENT_CATALOG: 'dsdn_tiktok_agent': 'DSDN TikTok trends, "
                            "content packages, series'. Add to DSDN routing rule."
                        ),
                    },
                ],
            },
            # ── 11. Scheduler: Daily Digest ──────────────────────────
            {
                "heading": "Scheduled Task: Daily TikTok Trends Digest",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "A new scheduled task (make_daily_tiktok_trends) follows the "
                            "make_daily_growth_ideas pattern. Runs daily and posts a Slack digest "
                            "to #dsdn-tiktok."
                        ),
                    },
                ],
            },
            {
                "heading": "Daily Digest Flow",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Scan TikTok trends (general + niche)",
                            "Score DSDN alignment for all discovered trends",
                            "Filter to trends scoring 3+/5",
                            "Generate 3-5 content package summaries for top trends",
                            "Post structured Slack Block Kit digest with trend names, scores, suggested formats, and package previews",
                        ],
                    },
                ],
            },
            {
                "heading": "Slack Digest Format",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Slack digest uses Block Kit with a header ('DSDN TikTok Trends'), "
                            "context line showing trend count and scan time, dividers between trends, "
                            "and expandable sections for each content package summary. Follows the "
                            "same pattern as the Growth Ideas and DSDN Ideas digests."
                        ),
                    },
                ],
            },
            # ── 12. Data Storage ─────────────────────────────────────
            {
                "heading": "Data Storage",
                "level": 1,
                "content": [
                    {
                        "type": "table",
                        "headers": ["File", "Format", "Purpose"],
                        "rows": [
                            [
                                "data/dsdn/tiktok_trends.json",
                                "JSON with _meta + trends array",
                                "Trend cache with 4h TTL",
                            ],
                            [
                                "data/dsdn/tiktok_media_catalog.jsonl",
                                "JSONL (one CatalogEntry per line)",
                                "Vision-AI media descriptions",
                            ],
                            [
                                "data/dsdn/tiktok_performance.jsonl",
                                "JSONL (one PerformanceRecord per line)",
                                "Published content metrics",
                            ],
                            [
                                "cmo_agent.db (drafts table)",
                                "SQLite row",
                                "Generated content packages (content_type='tiktok_content_package')",
                            ],
                        ],
                    },
                ],
            },
            # ── 13. Tests ────────────────────────────────────────────
            {
                "heading": "Test Coverage",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Two test files covering model validation, business logic, and agent "
                            "tool registration."
                        ),
                    },
                ],
            },
            {
                "heading": "test_dsdn_tiktok.py",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "All Pydantic model validation (TikTokTrend, ContentSeries, TikTokContentPackage, etc.)",
                            "Trend expiration logic (72h TTL)",
                            "Hook formula template rendering and lookup",
                            "Content package caption length enforcement (max 2200 chars)",
                            "Series episode numbering",
                            "Weekly calendar variety (no duplicate formats in a single day)",
                            "Performance record storage and retrieval",
                            "Person-first language checks in system prompts",
                            "Agent tool registration (9 tools)",
                        ],
                    },
                ],
            },
            {
                "heading": "test_media_catalog.py",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "JSONL roundtrip (write + read)",
                            "Dedup by filename on save",
                            "Keyword search across descriptions and tags",
                            "Directory scanning (photo and video extensions)",
                            "get_uncataloged() correctly filters already-cataloged files",
                            "Stats calculation (photo/video counts)",
                        ],
                    },
                ],
            },
            # ── 14. Implementation Order ─────────────────────────────
            {
                "heading": "Implementation Order",
                "level": 1,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "tiktok/models.py - All Pydantic models (already started)",
                            "tiktok/hooks.py - Hook formula library (already started)",
                            "tiktok/media_catalog.py - Vision-based catalog (already started)",
                            "tiktok/trends.py - Trend discovery + caching (already started)",
                            "tiktok/performance.py - Performance tracking (already started)",
                            "tiktok/__init__.py - Package init with re-exports",
                            "agents/dsdn_tiktok.py - Main agent with 9 tools",
                            "config.py - Add settings",
                            "factory.py, orchestrator.py, session.py - Wiring",
                            "routing/catalog.py - Router catalog entry",
                            "scheduler/tasks.py - Daily digest task",
                            "tests/unit/test_dsdn_tiktok.py + test_media_catalog.py",
                            "CLAUDE.md - Documentation update (Phase 26)",
                            "ruff format, ruff check, pytest",
                        ],
                    },
                ],
            },
            # ── 15. Phase 2 (Deferred) ───────────────────────────────
            {
                "heading": "Phase 2 (Deferred)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The following capabilities are explicitly deferred to a future phase. "
                            "They are documented here for planning purposes but will NOT be built "
                            "in this implementation."
                        ),
                    },
                    {
                        "type": "bullets",
                        "items": [
                            "Rendered video output: Chain to Video Agent or Motion Graphics Agent for actual TikTok video rendering",
                            "Instagram Reels and YouTube Shorts expansion: Multi-platform content adaptation with platform-specific formatting",
                            "TikTok API integration: Direct posting, analytics pull, comment monitoring (requires TikTok developer account)",
                            "Automated media library organization: Auto-tag and sort DSDN's existing photo/video archive",
                            "A/B testing framework: Test different hooks, formats, and posting times with statistical validation",
                        ],
                    },
                ],
            },
            # ── 16. Verification Checklist ───────────────────────────
            {
                "heading": "Verification Checklist",
                "level": 1,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "ruff format src/ tests/ && ruff check src/ tests/ passes",
                            "pytest tests/unit/test_dsdn_tiktok.py tests/unit/test_media_catalog.py passes",
                            "cmo chat routes 'scan TikTok trends for DSDN' to the agent",
                            "cmo chat routes 'create a TikTok series about DSDN retreats' to the agent",
                            "cmo chat routes 'generate a week of TikTok content for DSDN' to the agent",
                            "Content packages contain: hook from formula library, timed script, caption <2200 chars, hashtags, editing instructions",
                            "Series concepts have: recurring template, episode cadence, hook formula reference",
                            "Weekly calendars have variety across content types and formats (no duplicates)",
                            "Person-first language in all output, no em dashes, no mid-sentence bolding",
                            "Drafts stored in DB with content_type='tiktok_content_package'",
                            "When media catalog is empty, packages include descriptive media direction",
                            "Performance records persist and generate_insights produces actionable recommendations",
                        ],
                    },
                ],
            },
        ],
    }


def main() -> None:
    """Build the Google Doc and print the URL."""
    import os

    from dotenv import load_dotenv

    load_dotenv()

    # ── Lazy import Google libraries ──────────────────────────────────
    from googleapiclient.discovery import build

    from cmo_agent.google_auth import (
        ensure_drive_folder,
        get_google_credentials,
        move_file_to_folder,
    )

    SCOPES = [
        "https://www.googleapis.com/auth/documents",
        "https://www.googleapis.com/auth/drive.file",
    ]

    # Resolve token path (same logic as DocsAgent)
    oauth_token_path = os.getenv("GOOGLE_OAUTH_TOKEN_PATH", "data/google-token.json")
    if oauth_token_path and not Path(oauth_token_path).is_absolute():
        oauth_token_path = str(Path(oauth_token_path).resolve())

    service_account_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "")
    if service_account_path and not Path(service_account_path).is_absolute():
        service_account_path = str(Path(service_account_path).resolve())

    # Force OAuth (not service account) — service account lacks Docs API permission
    credentials = get_google_credentials(
        oauth_token_path=oauth_token_path,
        service_account_path="",  # skip service account for Docs
        scopes=SCOPES,
    )
    if credentials is None:
        print("ERROR: No Google credentials found. Check GOOGLE_OAUTH_TOKEN_PATH in .env.")
        return

    docs_service = build("docs", "v1", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    # ── Build document via DocsAgent._build_google_doc() ──────────────
    from cmo_agent.agents.docs import DocsAgent

    agent = DocsAgent.__new__(DocsAgent)  # bypass __init__
    agent._docs_service = docs_service
    agent._drive_service = drive_service

    structure = _build_structure()
    result = agent._build_google_doc(structure, workspace_id="dsdn")

    if result.get("status") == "created":
        print(f"\nGoogle Doc created successfully!")
        print(f"URL: {result['google_docs_url']}")
    else:
        print(f"\nFailed to create Google Doc: {result}")


if __name__ == "__main__":
    main()
