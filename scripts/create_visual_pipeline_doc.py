"""Create a Google Doc: Visual Pipeline Technical Architecture.

Builds the document structure in-memory and calls DocsAgent._build_google_doc()
directly, bypassing LLM generation so every technical detail is accurate.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))


def _build_structure() -> dict:
    """Return the full document structure dict."""
    return {
        "title": "Visual Pipeline Technical Architecture — CMO Agent",
        "include_toc": True,
        "sections": [
            # ── 1. Overview ──────────────────────────────────────────
            {
                "heading": "Overview",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The CMO Agent visual content system provides end-to-end creation of "
                            "images, compositions, motion graphics, and AI-generated video through "
                            "four specialized sub-agents. Each agent owns a distinct rendering "
                            "pipeline and cost profile, but all share a unified media storage layer "
                            "(Supabase CDN (Content Delivery Network) + SQLite tracking) and are "
                            "orchestrated by the same CMO Orchestrator Agent."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Agent", "What It Produces", "Rendering", "Cost"],
                        "rows": [
                            [
                                "Visual Agent",
                                "Textless photographs, illustrations, abstract backgrounds",
                                "External API (SDXL / DALL-E 3 / Gemini 3 Pro)",
                                "$0.01 - $0.10 per image",
                            ],
                            [
                                "Composition Planner + Renderer",
                                "Text-on-visual: diagrams, dashboards, timelines, ecosystem maps",
                                "Local Remotion (npx remotion still / render)",
                                "Free (local CPU) + optional photo background",
                            ],
                            [
                                "Motion Graphics Agent",
                                "Animated text, data viz, branded intros, kinetic typography",
                                "Local Remotion (npx remotion render)",
                                "Free (local CPU)",
                            ],
                            [
                                "Video Agent",
                                "AI-generated cinematic video clips",
                                "External API (Kling 2.1 / Kling 2.6 Pro / Sora 2)",
                                "$0.10 - $5.00 per clip",
                            ],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "All four agents are accessible from Slack, the web UI, and the CLI. "
                            "The orchestrator decides which agent to invoke based on the user's "
                            "request — no manual routing is required."
                        ),
                    },
                ],
            },
            # ── 2. Slack Bot → Orchestrator Flow ─────────────────────
            {
                "heading": "Slack Bot to Orchestrator Flow",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All three interaction surfaces — Slack, web UI, CLI — converge on "
                            "the same pipeline. Here is the Slack path, which is the primary "
                            "production interface."
                        ),
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            "User sends a message in Slack (DM or channel mention).",
                            "The Slack bot (Socket Mode via slack_bolt) receives the event and extracts the user text, thread context, and channel ID.",
                            "The bot instantiates a CMOSession (runtime/session.py), which is the unified async session manager.",
                            "CMOSession resolves the workspace from the Slack channel mapping (e.g., #saverwell-content → saverwell, #dsdn-content → dsdn).",
                            "CMOSession calls AgentFactory.create_all() to construct the orchestrator and all sub-agents with proper LLM model assignments.",
                            "The user message is passed to CMOOrchestratorAgent.process_message(), which enters the ReAct (Reason + Act) loop.",
                            "The orchestrator's LLM (Sonnet) reads the user request and decides which tool(s) to call — including sub-agent tools like create_visual, motion_graphics_agent, or video_agent.",
                            "Each sub-agent runs its own ReAct loop (max 10 iterations), returns an AgentResult, and the orchestrator synthesizes the final response.",
                            "The response is posted back to the Slack thread with media URLs, cost summaries, and draft IDs.",
                        ],
                    },
                ],
            },
            # ── 3. Orchestrator Delegation ───────────────────────────
            {
                "heading": "Orchestrator Delegation",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The CMO Orchestrator Agent (agents/orchestrator.py) is the central "
                            "routing brain. Sub-agents are registered as tools on the orchestrator's "
                            "ToolRegistry, which auto-generates JSON Schema from Python type hints. "
                            "The orchestrator's LLM (Sonnet) sees tool descriptions and decides "
                            "which agent to invoke — there is no hard-coded routing logic."
                        ),
                    },
                ],
            },
            {
                "heading": "Tool Registration Pattern",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Each sub-agent is wrapped in a tool function on the orchestrator's "
                            "ToolRegistry. The tool function calls agent.process_message() with "
                            "the user's request and returns the AgentResult. The orchestrator "
                            "never directly calls sub-agent internals — only the public "
                            "process_message() interface."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "**Exception:** The unified create_visual tool bypasses the Visual "
                            "Agent's ReAct loop for photo generation (calling _call_dalle / "
                            "_call_sdxl / _call_gemini directly) to reduce latency and token cost. "
                            "For compositions (diagrams, dashboards, etc.), it invokes the "
                            "Composition Planner's process_message() to get a structured spec, "
                            "then renders via CompositionRenderer."
                        ),
                    },
                ],
            },
            {
                "heading": "4-Step Media Creation Approval Flow",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The orchestrator's system prompt mandates a 4-step approval flow "
                            "for all visual content creation:"
                        ),
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            "ASK — Clarify what the visual should show (subject, audience, platform).",
                            "PLAN — Present a plan with tier/cost info and wait for user approval.",
                            "APPROVE — User confirms the plan (or adjusts tier/format).",
                            "EXECUTE — Call create_visual (or video_agent / motion_graphics_agent) once per asset.",
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "This prevents surprise costs and ensures the user controls which "
                            "tier and provider is used for each piece of content."
                        ),
                    },
                ],
            },
            # ── 4. Visual Agent (Image Generation) ───────────────────
            {
                "heading": "Visual Agent (Image Generation)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Visual Agent (agents/visual.py) generates textless images using "
                            "a three-tier model system. It produces NO text in images — all "
                            "typography is handled by the Composition Pipeline or Pillow text "
                            "overlay. Every prompt is prefixed with an explicit no-text instruction."
                        ),
                    },
                ],
            },
            {
                "heading": "Three-Tier Image System",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": [
                            "Tier",
                            "Provider / Model",
                            "Cost per Image",
                            "Best For",
                            "API",
                        ],
                        "rows": [
                            [
                                "Low (Budget)",
                                "Stable Diffusion XL via FAL.ai (fal-ai/fast-sdxl)",
                                "~$0.01-$0.03",
                                "Bulk SEO filler, background illustrations, experiments",
                                "FAL_API_KEY",
                            ],
                            [
                                "Medium (Standard) — default",
                                "DALL-E 3 via OpenAI API",
                                "~$0.04-$0.08",
                                "Landing pages, DMA pages, merchant tiles",
                                "OPENAI_API_KEY",
                            ],
                            [
                                "High (Premium)",
                                "Gemini 3 Pro (gemini-3-pro-image-preview)",
                                "~$0.05-$0.10",
                                "Hero banners, homepage visuals, investor decks",
                                "GEMINI_API_KEY",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Standard Platform Dimensions",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Platform", "Dimensions"],
                        "rows": [
                            ["Instagram / Social square", "1024x1024"],
                            ["Instagram Story / Pinterest", "1024x1792"],
                            ["Facebook / Twitter / LinkedIn", "1792x1024"],
                            ["Newsletter / Blog hero", "1792x1024"],
                        ],
                    },
                ],
            },
            {
                "heading": "Prompt Optimization",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Visual Agent's create_image_prompt tool uses the LLM (Sonnet) to "
                            "refine a user description into an optimized image prompt. Rules enforced: "
                            "(1) absolutely no text in the image, (2) concrete scene description "
                            "(subjects, lighting, camera angle, depth of field), (3) specific colors "
                            "and composition, (4) brand-appropriate style. The generate_social_graphic "
                            "tool combines prompt creation + image generation + optional Pillow text "
                            "overlay in one call."
                        ),
                    },
                ],
            },
            # ── 5. Composition Planner Agent ─────────────────────────
            {
                "heading": "Composition Planner Agent",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Composition Planner (agents/composition_planner.py) is the "
                            "design brain for text-on-visual compositions. It translates user "
                            "requests into structured specs (template selection, props, background "
                            "prompts) that Remotion templates render deterministically. The LLM "
                            "makes all creative decisions; the templates execute them pixel-perfectly."
                        ),
                    },
                ],
            },
            {
                "heading": "10 Parametric Templates",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Template", "Best For", "Required Props"],
                        "rows": [
                            ["HeroOverlay", "Hero banners, social graphics, titled thumbnails", "title"],
                            ["LowerThird", "Speaker labels, name cards, video captions", "name"],
                            ["DataDashboard", "KPI dashboards, metric summaries, performance snapshots", "title, metrics[]"],
                            ["ProcessFlow", "Workflows, process diagrams, how-it-works sections", "title, steps[]"],
                            ["EcosystemMap", "Org charts, ecosystem diagrams, relationship maps", "hub, clusters[]"],
                            ["ComparisonGrid", "Feature comparisons, pricing tiers, pros/cons", "title, items[]"],
                            ["CalloutOverlay", "Annotated screenshots, product callouts", "callouts[]"],
                            ["TimelineSequence", "Roadmaps, project timelines, milestones", "title, events[]"],
                            ["QuoteCard", "Testimonials, customer quotes, mission statements", "quote, attribution"],
                            ["StaticLayout", "Complex custom diagrams (catch-all)", "title, nodes[]"],
                        ],
                    },
                ],
            },
            {
                "heading": "Quick Mode vs Planning Mode",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "**Quick mode (preferred):** The planner calls plan_composition with "
                            "template_id, template_props, and background_prompt in a single call. "
                            "Returns spec_ready immediately. One LLM turn completes the task."
                        ),
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "**Planning mode:** The planner calls plan_composition with just a "
                            "description to get template guidance, then calls emit_composition_spec "
                            "with the structured spec. Two LLM turns. Used when the planner needs "
                            "to reason about template selection first."
                        ),
                    },
                ],
            },
            {
                "heading": "Background Prompt Engineering",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "Background prompts are optimized for compositing — they describe "
                            "textless images designed to work behind template overlays. Rules: "
                            "(1) explicit negative space where text will be placed, (2) low "
                            "complexity behind text areas, (3) color coordination with overlay "
                            "colors, (4) never include text in prompts, (5) compositing-friendly "
                            "(dark backgrounds for DataDashboard, cinematic for HeroOverlay, "
                            "subtle gradients for EcosystemMap)."
                        ),
                    },
                ],
            },
            {
                "heading": "Validation Rules",
                "level": 2,
                "content": [
                    {
                        "type": "bullets",
                        "items": [
                            "Maximum 14 nodes/items per composition (split into panels if more needed)",
                            "Minimum font sizes: title 48px, body 22px, label 18px (at 1080p)",
                            "Text must fit within 120px safe margins from edges",
                            "WCAG AA contrast ratio (4.5:1) between text and background",
                            "No overlapping text elements",
                            "Node positions must be within 0-100 bounds (StaticLayout)",
                        ],
                    },
                ],
            },
            {
                "heading": "Design Tokens",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All templates share a design token system defined in "
                            "data/remotion/src/tokens.ts — typography scales, spacing units, "
                            "animation curves, and color palettes. This ensures visual consistency "
                            "across all 10 templates without per-template styling."
                        ),
                    },
                ],
            },
            # ── 6. Composition Renderer (Remotion) ───────────────────
            {
                "heading": "Composition Renderer (Remotion)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The CompositionRenderer (text/composition_renderer.py) is the "
                            "execution engine for the Composition Planner's specs. It converts "
                            "structured template specs into rendered PNG images or MP4 videos "
                            "using the Remotion CLI."
                        ),
                    },
                ],
            },
            {
                "heading": "Static PNG vs Animated MP4",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Mode", "CLI Command", "Output", "Use Case"],
                        "rows": [
                            [
                                "Static",
                                "npx remotion still src/templateIndex.ts {TemplateId} output.png --props=props.json",
                                "Single-frame PNG",
                                "Social graphics, blog images, newsletter headers",
                            ],
                            [
                                "Motion",
                                "npx remotion render src/templateIndex.ts {TemplateId}-Motion output.mp4 --props=props.json",
                                "Animated MP4",
                                "Social video, animated dashboards, video overlays",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Rendering Pipeline",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Validate template ID against AVAILABLE_TEMPLATES list.",
                            "Write template_props to a temporary JSON file (props-{uuid}.json).",
                            "Resolve composition ID from template + mode + format (e.g., DataDashboard-Square for square static).",
                            "Execute npx remotion still (or render) as an async subprocess with 5-minute timeout.",
                            "Verify output file exists and is non-empty.",
                            "Clean up temporary props file.",
                            "Return absolute path to rendered file.",
                        ],
                    },
                ],
            },
            {
                "heading": "Format Resolution",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Output Format", "Resolution", "Composition ID Suffix"],
                        "rows": [
                            ["Landscape (default)", "1920x1080", "(none) — e.g., DataDashboard"],
                            ["Square", "1080x1080", "-Square — e.g., DataDashboard-Square"],
                            ["Motion (animated)", "1920x1080", "-Motion — e.g., DataDashboard-Motion"],
                        ],
                    },
                ],
            },
            # ── 7. Motion Graphics Agent ─────────────────────────────
            {
                "heading": "Motion Graphics Agent",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Motion Graphics Agent (agents/motion_graphics.py) creates "
                            "freeform programmatic animations — logo reveals, kinetic typography, "
                            "animated data visualizations, branded intros — using LLM-generated "
                            "React/TypeScript code rendered by Remotion. This is fundamentally "
                            "different from the Composition Planner (which uses parametric "
                            "templates) and the Video Agent (which uses AI video generation APIs)."
                        ),
                    },
                ],
            },
            {
                "heading": "Three Complexity Tiers",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": [
                            "Tier",
                            "Description",
                            "Max Duration",
                            "Render Time",
                            "Cost",
                        ],
                        "rows": [
                            [
                                "Simple",
                                "Basic text animation, logo reveal, lower third",
                                "15 seconds",
                                "~7-15 seconds",
                                "Free (local CPU)",
                            ],
                            [
                                "Standard",
                                "Multi-element animation, transitions, animated data points",
                                "30 seconds",
                                "~15-40 seconds",
                                "Free (local CPU)",
                            ],
                            [
                                "Complex",
                                "Full motion graphic with multiple scenes, particle effects",
                                "60 seconds",
                                "~30-90 seconds",
                                "Free (local CPU)",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "LLM-Generated Code Pipeline",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "The agent's LLM (Sonnet) generates a complete React/TypeScript Remotion composition from the user description, brand voice, and reference docs.",
                            "Post-generation font size enforcement: a regex pass scans all fontSize values and bumps any below the absolute minimum (28px at 1080p, 50px at 1920p).",
                            "Truncation repair: if the LLM output is truncated (missing export default), the agent detects unmatched braces/parens and auto-closes them.",
                            "The composition file is written to data/remotion/src/compositions/{id}.tsx.",
                            "Root.tsx is rewritten to register the new composition with correct dimensions and frame count.",
                            "npx remotion render is executed with a 180-second timeout.",
                            "The rendered MP4 is uploaded to Supabase CDN and saved as a draft.",
                        ],
                    },
                ],
            },
            {
                "heading": "Audio Options",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Track", "Description", "BPM"],
                        "rows": [
                            ["Corporate Ambient", "Piano arpeggios over warm pad chords with soft kick/hi-hat groove", "90"],
                            ["Calm & Inspirational", "Flowing piano arpeggios with lush string pads and gentle bass", "72"],
                            ["Energetic & Upbeat", "Driving synth chords with lead melody, punchy kick/snare, octave bass line", "120"],
                            ["None (default)", "Silent — visual only", "N/A"],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "Audio visualization styles: none (default), bars (equalizer frequency bars), "
                            "waveform (horizontal SVG waveform), pulse (background glow that reacts to beat). "
                            "All audio features use Remotion's @remotion/media-utils package."
                        ),
                    },
                ],
            },
            {
                "heading": "Font Size Enforcement",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The LLM often ignores font size instructions, so the agent applies "
                            "programmatic enforcement after code generation. Concrete minimums "
                            "are computed from the render dimensions:"
                        ),
                    },
                    {
                        "type": "table",
                        "headers": ["Element", "Minimum at 1080p", "Minimum at 1920p"],
                        "rows": [
                            ["Headings / Hero Titles", "96px (fontWeight 800)", "170px"],
                            ["Subtitles / Section Heads", "48px (fontWeight 700)", "84px"],
                            ["Body Text / Labels", "32px (fontWeight 500)", "58px"],
                            ["Metric Values / Big Numbers", "110px (fontWeight 900)", "196px"],
                            ["Absolute Minimum (any text)", "28px", "50px"],
                        ],
                    },
                ],
            },
            # ── 8. Video Agent (AI Video) ────────────────────────────
            {
                "heading": "Video Agent (AI Video)",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The Video Agent (agents/video.py) generates AI video clips from "
                            "text prompts using external APIs. It supports both text-to-video "
                            "and image-to-video generation. All videos are downloaded to local "
                            "storage to persist beyond temporary API URLs."
                        ),
                    },
                ],
            },
            {
                "heading": "Three-Tier Video System",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": [
                            "Tier",
                            "Provider / Model",
                            "Cost per 5s Clip",
                            "Max Duration",
                            "Poll Timeout",
                            "API Key",
                        ],
                        "rows": [
                            [
                                "Low",
                                "fal.ai / Kling 2.1 Master",
                                "$0.10-$0.30",
                                "10 seconds",
                                "180 seconds",
                                "FAL_API_KEY",
                            ],
                            [
                                "Medium",
                                "fal.ai / Kling 2.6 Pro (with audio)",
                                "$0.35-$0.60",
                                "10 seconds",
                                "240 seconds",
                                "FAL_API_KEY",
                            ],
                            [
                                "High",
                                "OpenAI / Sora 2",
                                "$2.00-$5.00",
                                "20 seconds",
                                "360 seconds",
                                "OPENAI_API_KEY",
                            ],
                        ],
                    },
                ],
            },
            {
                "heading": "Video Generation Pipeline",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "get_video_pricing is called first (mandatory) to show the user available tiers and costs.",
                            "User selects a tier; the orchestrator calls generate_video.",
                            "The LLM (Sonnet) optimizes the user's prompt for the selected provider (brand voice, motion/camera/lighting specifics, under 500 characters).",
                            "For fal.ai tiers: submit job to the fal.ai Queue API (POST queue.fal.run), poll status endpoint every 5 seconds until COMPLETED.",
                            "For Sora tier: submit job to OpenAI Videos API (POST api.openai.com/v1/videos), poll status until completed, then download MP4 binary from content endpoint.",
                            "Video is downloaded to data/videos/ to persist beyond temporary API URLs.",
                            "Video is uploaded to Supabase CDN if configured.",
                            "A draft record is created in the database with all metadata.",
                        ],
                    },
                ],
            },
            {
                "heading": "Platform Formats",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["Platform", "Aspect Ratio", "Recommended Duration"],
                        "rows": [
                            ["Instagram Reel / TikTok", "9:16 vertical", "15-60 seconds"],
                            ["YouTube Short", "9:16 vertical", "Up to 60 seconds"],
                            ["YouTube standard", "16:9 horizontal", "2-10 minutes"],
                            ["LinkedIn", "16:9 or 1:1", "30s - 2 min"],
                            ["Facebook / Twitter", "16:9 or 1:1", "15s - 2 min"],
                            ["Story format", "9:16 vertical", "15-second segments"],
                        ],
                    },
                ],
            },
            # ── 9. Media Storage & Delivery ──────────────────────────
            {
                "heading": "Media Storage and Delivery",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All visual agents share the MediaStorage class (media/storage.py) "
                            "for unified CDN upload and metadata tracking. The system gracefully "
                            "degrades when Supabase is not configured — database records are "
                            "always created, but cdn_url will be None."
                        ),
                    },
                ],
            },
            {
                "heading": "Supabase CDN Pipeline",
                "level": 2,
                "content": [
                    {
                        "type": "numbered_list",
                        "items": [
                            "Agent generates media (image bytes, local file path, or remote URL).",
                            "MediaStorage.upload_from_url() downloads the content, or upload_from_file() reads the local file.",
                            "Bytes are uploaded to Supabase Storage via POST /storage/v1/object/{bucket}/{path} with x-upsert: true.",
                            "The public CDN URL is constructed: {supabase_url}/storage/v1/object/public/{bucket}/{path}.",
                            "A media_assets DB record is created with asset_id, workspace_id, media_type, cdn_url, local_path, source_agent, prompt, and metadata.",
                            "If the media is linked to a draft, the asset's draft_id is set via link_to_draft().",
                        ],
                    },
                ],
            },
            {
                "heading": "Storage Path Convention",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "All paths follow the pattern: **{workspace_id}/{media_type}/{YYYY-MM}/{filename}**. "
                            "For example: saverwell/image/2026-02/a1b2c3d4e5f6.png. "
                            "This ensures workspace isolation and time-based organization."
                        ),
                    },
                ],
            },
            {
                "heading": "Local Fallback",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "When Supabase is not configured (SUPABASE_URL and "
                            "SUPABASE_SERVICE_ROLE_KEY not set), media files are stored locally: "
                            "images in the API response URLs (temporary), videos in data/videos/, "
                            "motion graphics in data/motion_graphics/, compositions in "
                            "data/compositions/. The media_assets DB record is still created with "
                            "local_path populated."
                        ),
                    },
                ],
            },
            # ── 10. LLM Model Assignments ────────────────────────────
            {
                "heading": "LLM (Large Language Model) Assignments",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The system uses a model-per-role assignment strategy to balance "
                            "cost, speed, and quality. Models are configured in config.py and "
                            "instantiated by AgentFactory.create_all()."
                        ),
                    },
                    {
                        "type": "table",
                        "headers": [
                            "Role",
                            "Model",
                            "Temperature",
                            "Agents",
                        ],
                        "rows": [
                            [
                                "Orchestrator",
                                "claude-sonnet-4-6 (LLM_MODEL)",
                                "0.7",
                                "CMO Orchestrator",
                            ],
                            [
                                "Scanning (cheap, fast)",
                                "claude-haiku-4-5 (LLM_MODEL_SCANNING)",
                                "0.5",
                                "Research, Reddit Ingest, Google Alerts, Proofreader",
                            ],
                            [
                                "Writing (quality)",
                                "claude-sonnet-4-6 (LLM_MODEL_WRITING)",
                                "0.7",
                                "Writer, Visual, Video, Motion Graphics, Composition Planner, Deck, Docs, Sheets, + most other agents",
                            ],
                            [
                                "Premium (high stakes)",
                                "claude-opus-4-6 (LLM_MODEL_PREMIUM)",
                                "0.7",
                                "Compliance, Legal Strategy, GTM",
                            ],
                        ],
                    },
                    {
                        "type": "paragraph",
                        "text": (
                            "All four visual agents (Visual, Composition Planner, Motion Graphics, "
                            "Video) use the writing_llm (Sonnet). The Proofreader, which spell-checks "
                            "text before rendering, uses scanning_llm (Haiku) for cost efficiency."
                        ),
                    },
                ],
            },
            # ── 11. How Agents Coordinate ────────────────────────────
            {
                "heading": "How Agents Coordinate",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The orchestrator provides a unified create_visual tool that routes "
                            "to the correct pipeline based on the visual_type parameter and "
                            "description keywords."
                        ),
                    },
                ],
            },
            {
                "heading": "Deterministic Routing via create_visual",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": (
                            "The _needs_composition() function (orchestrator.py) performs a "
                            "deterministic check — no LLM call required. If visual_type is in "
                            "the COMPOSITION_TYPES set (diagram, infographic, dashboard, flow, "
                            "timeline, comparison, ecosystem, hero_banner, quote, process, grid, "
                            "scorecard, map, chart) OR the description contains composition keywords, "
                            "the request routes to the composition pipeline. Otherwise, it routes "
                            "to direct photo generation."
                        ),
                    },
                ],
            },
            {
                "heading": "Composition Pipeline (Sequential Orchestration)",
                "level": 2,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "When create_visual routes to the composition pipeline, the orchestrator executes these steps sequentially:",
                    },
                    {
                        "type": "numbered_list",
                        "items": [
                            "Pre-flight check: verify npx is on PATH (Remotion requires Node.js).",
                            "PLAN — Call Composition Planner's process_message() with the description. The planner's LLM selects a template, fills props, and generates a textless background prompt. Returns a spec_ready result.",
                            "VALIDATE — Run prop reasonableness checks (Level 2 QA): empty arrays, title overflow, node position bounds.",
                            "BACKGROUND — If background_style is 'photo' (or 'auto' for HeroOverlay/QuoteCard/CalloutOverlay), call _generate_textless_background() which uses the Visual Agent's image generation APIs to create a background image.",
                            "RENDER — Instantiate CompositionRenderer and call render_static() (PNG) or render_motion() (MP4). This runs npx remotion still/render as an async subprocess.",
                            "VERIFY — Check that the output file exists and is non-empty.",
                            "UPLOAD — Upload to Supabase CDN via MediaStorage and return the CDN URL + asset ID.",
                        ],
                    },
                ],
            },
            {
                "heading": "When Each Agent Is Selected",
                "level": 2,
                "content": [
                    {
                        "type": "table",
                        "headers": ["User Request", "Agent Selected", "Why"],
                        "rows": [
                            [
                                '"Create a hero banner for our launch"',
                                "create_visual → Composition Pipeline",
                                "hero_banner is in COMPOSITION_TYPES",
                            ],
                            [
                                '"Generate a photo of a senior couple"',
                                "create_visual → Direct Photo",
                                "visual_type=photo, no composition keywords",
                            ],
                            [
                                '"Make an animated bar chart of our KPIs"',
                                "Motion Graphics Agent",
                                "Animated + data viz = freeform Remotion animation",
                            ],
                            [
                                '"Create a cinematic product video"',
                                "Video Agent",
                                "AI-generated video from prompt (not programmatic)",
                            ],
                            [
                                '"Show our org chart as a diagram"',
                                "create_visual → Composition Pipeline",
                                "diagram is in COMPOSITION_TYPES",
                            ],
                            [
                                '"Make a logo reveal animation"',
                                "Motion Graphics Agent",
                                "Freeform animation, not a parametric template",
                            ],
                        ],
                    },
                ],
            },
            # ── 12. Summary: All Visual Content Options ──────────────
            {
                "heading": "Summary: All Visual Content Options",
                "level": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "text": "Master comparison of every visual content creation pathway in the system:",
                    },
                    {
                        "type": "table",
                        "headers": [
                            "Agent / Tool",
                            "Output Format",
                            "Cost",
                            "Speed",
                            "Quality Tier",
                        ],
                        "rows": [
                            [
                                "Visual Agent (SDXL)",
                                "PNG image",
                                "~$0.01-$0.03",
                                "~3-5 seconds",
                                "Budget — bulk/experiments",
                            ],
                            [
                                "Visual Agent (DALL-E 3)",
                                "PNG image",
                                "~$0.04-$0.08",
                                "~5-10 seconds",
                                "Standard — production use",
                            ],
                            [
                                "Visual Agent (Gemini 3 Pro)",
                                "PNG image",
                                "~$0.05-$0.10",
                                "~5-15 seconds",
                                "Premium — hero content",
                            ],
                            [
                                "Composition Pipeline (solid bg)",
                                "PNG or MP4",
                                "Free",
                                "~5-15 seconds render",
                                "Deterministic — text-on-visual",
                            ],
                            [
                                "Composition Pipeline (photo bg)",
                                "PNG or MP4",
                                "$0.04-$0.10 (bg image)",
                                "~10-20 seconds total",
                                "Premium — text-on-photo",
                            ],
                            [
                                "Motion Graphics (Simple)",
                                "MP4 video",
                                "Free",
                                "~7-15 seconds render",
                                "Basic animations",
                            ],
                            [
                                "Motion Graphics (Standard)",
                                "MP4 video",
                                "Free",
                                "~15-40 seconds render",
                                "Multi-element animations",
                            ],
                            [
                                "Motion Graphics (Complex)",
                                "MP4 video",
                                "Free",
                                "~30-90 seconds render",
                                "Full motion graphics",
                            ],
                            [
                                "Video Agent (Kling 2.1)",
                                "MP4 video",
                                "~$0.10-$0.30 / 5s",
                                "~60-180 seconds",
                                "AI video — drafts/social",
                            ],
                            [
                                "Video Agent (Kling 2.6 Pro)",
                                "MP4 video",
                                "~$0.35-$0.60 / 5s",
                                "~60-240 seconds",
                                "AI video — polished marketing",
                            ],
                            [
                                "Video Agent (Sora 2)",
                                "MP4 video",
                                "~$2.00-$5.00 / clip",
                                "~120-360 seconds",
                                "AI video — hero/ads",
                            ],
                        ],
                    },
                ],
            },
            # ── Key Source Files ──────────────────────────────────────
            {
                "heading": "Key Source Files",
                "level": 1,
                "content": [
                    {
                        "type": "table",
                        "headers": ["File", "Role"],
                        "rows": [
                            ["agents/orchestrator.py", "Central routing brain: create_visual tool, composition pipeline, photo generation"],
                            ["agents/visual.py", "Visual Agent: 3-tier image generation (SDXL, DALL-E 3, Gemini 3 Pro)"],
                            ["agents/composition_planner.py", "Composition Planner: 10 templates, validation, background prompt engineering"],
                            ["text/composition_renderer.py", "CompositionRenderer: Remotion CLI executor (still/render)"],
                            ["agents/motion_graphics.py", "Motion Graphics Agent: LLM-generated Remotion compositions, font enforcement"],
                            ["agents/video.py", "Video Agent: Kling/Sora AI video generation with polling"],
                            ["media/storage.py", "MediaStorage: Supabase CDN upload + SQLite tracking"],
                            ["agents/factory.py", "AgentFactory: LLM model assignments and agent construction"],
                            ["config.py", "Settings: API keys, model names, output directories"],
                            ["google_auth.py", "Google OAuth2 token loading and auto-refresh"],
                            ["data/remotion/src/templates/", "10 parametric Remotion template source files"],
                            ["data/remotion/src/tokens.ts", "Shared design token system (typography, spacing, colors)"],
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

    credentials = get_google_credentials(
        oauth_token_path=oauth_token_path,
        service_account_path=service_account_path,
        scopes=SCOPES,
    )
    if credentials is None:
        print("ERROR: No Google credentials found. Check GOOGLE_OAUTH_TOKEN_PATH in .env.")
        return

    docs_service = build("docs", "v1", credentials=credentials)
    drive_service = build("drive", "v3", credentials=credentials)

    # ── Build document via DocsAgent._build_google_doc() ──────────────
    # We instantiate a minimal DocsAgent just to reuse its _build_google_doc method.
    # This avoids duplicating the complex Google Docs API cursor logic.
    from cmo_agent.agents.docs import DocsAgent

    agent = DocsAgent.__new__(DocsAgent)  # bypass __init__
    agent._docs_service = docs_service
    agent._drive_service = drive_service

    structure = _build_structure()
    result = agent._build_google_doc(structure, workspace_id="saverwell")

    if result.get("status") == "created":
        print(f"\nGoogle Doc created successfully!")
        print(f"URL: {result['google_docs_url']}")
    else:
        print(f"\nFailed to create Google Doc: {result}")


if __name__ == "__main__":
    main()
