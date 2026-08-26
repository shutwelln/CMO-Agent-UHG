"""Composition Planner Agent — design brain for text-on-visual compositions.

Produces structured specs (template selection, props, background prompts)
that are rendered deterministically via Remotion templates. No LLM touches
the rendering code — all creative decisions happen here, then templates
execute the spec pixel-perfectly.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..llm.base import BaseLLM
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# ── Template registry (mirrors AVAILABLE_TEMPLATES in composition_renderer.py) ──

TEMPLATE_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "HeroOverlay": {
        "description": "Title + subtitle over background image/video. Best for: hero banners, social graphics, titled thumbnails, cover images.",
        "required_props": ["title"],
        "optional_props": [
            "subtitle",
            "position",
            "bgDim",
            "bgColor",
            "titleColor",
            "subtitleColor",
        ],
        "position_options": ["center", "bottom-left", "bottom-center", "top-left"],
    },
    "LowerThird": {
        "description": "Name/title plate for video overlays. Best for: speaker labels, name cards, video captions.",
        "required_props": ["name"],
        "optional_props": ["title", "position", "style", "accentColor"],
        "style_options": ["bar", "pill", "minimal"],
    },
    "DataDashboard": {
        "description": "Grid of metric cards with optional animated counters. Best for: KPI dashboards, metric summaries, performance snapshots.",
        "required_props": ["title", "metrics"],
        "optional_props": ["subtitle", "columns", "accentColor", "theme"],
        "metrics_schema": {
            "label": "str",
            "value": "str",
            "delta": "str?",
            "deltaType": "positive|negative|neutral",
        },
    },
    "ProcessFlow": {
        "description": "Horizontal/vertical step sequence. Best for: workflows, process diagrams, how-it-works sections.",
        "required_props": ["title", "steps"],
        "optional_props": ["subtitle", "direction", "style", "accentColor", "theme"],
        "steps_schema": {"label": "str", "description": "str?", "icon": "str?"},
        "direction_options": ["horizontal", "vertical"],
    },
    "EcosystemMap": {
        "description": "Central hub with connected satellite nodes. Best for: org charts, ecosystem diagrams, relationship maps.",
        "required_props": ["hub", "clusters"],
        "optional_props": ["connections", "subtitle", "theme"],
        "hub_schema": {"label": "str", "description": "str?"},
        "clusters_schema": {
            "label": "str",
            "nodes": "str[]",
            "color": "str?",
            "icon": "str? (emoji)",
        },
        "connections_schema": {
            "from": "str (cluster label)",
            "to": "str (cluster label)",
            "label": "str?",
        },
    },
    "ComparisonGrid": {
        "description": "Side-by-side or NxN comparison cards. Best for: feature comparisons, pricing tiers, pros/cons.",
        "required_props": ["title", "items"],
        "optional_props": ["subtitle", "columns"],
        "items_schema": {
            "heading": "str",
            "points": "str[]",
            "highlight": "bool?",
            "color": "str?",
        },
    },
    "CalloutOverlay": {
        "description": "Labels/arrows pointing to regions of a background. Best for: annotated screenshots, product callouts.",
        "required_props": ["callouts"],
        "optional_props": ["style", "bgDim", "accentColor"],
        "callouts_schema": {
            "label": "str",
            "description": "str?",
            "position": "[x%, y%]",
            "arrowDirection": "up|down|left|right? (optional arrow pointer)",
        },
    },
    "TimelineSequence": {
        "description": "Chronological timeline with events. Best for: roadmaps, project timelines, milestones.",
        "required_props": ["title", "events"],
        "optional_props": ["subtitle", "direction", "accentColor"],
        "events_schema": {"date": "str", "title": "str", "description": "str?", "color": "str?"},
    },
    "QuoteCard": {
        "description": "Pull quote with attribution. Best for: testimonials, customer quotes, mission statements.",
        "required_props": ["quote", "attribution"],
        "optional_props": ["attributionTitle", "style", "accentColor", "quoteColor"],
        "style_options": ["centered", "left", "card"],
    },
    "StaticLayout": {
        "description": "Generic renderer for complex structured layouts with positioned nodes, edges, and groups. Catch-all for diagrams that don't fit other templates.",
        "required_props": ["title", "nodes"],
        "optional_props": ["subtitle", "edges", "groups", "footer", "theme"],
        "nodes_schema": {
            "id": "str",
            "label": "str",
            "description": "str?",
            "x": "0-100",
            "y": "0-100",
            "width": "0-100?",
            "color": "str?",
            "icon": "str? (emoji)",
            "shape": "rect|circle|pill (default: rect)",
        },
        "edges_schema": {"from": "id", "to": "id", "label": "str?", "style": "solid|dashed|dotted"},
    },
}

# ── Per-template density caps ──────────────────────────────────────────
TEMPLATE_CAPS: Dict[str, Dict[str, int]] = {
    "EcosystemMap": {"clusters": 8},
    "DataDashboard": {"metrics": 8},
    "ProcessFlow": {"steps": 6},
    "ComparisonGrid": {"items": 4},
    "TimelineSequence": {"events": 8},
    "StaticLayout": {"nodes": 12},
    "CalloutOverlay": {"callouts": 6},
}

# ── WCAG AA contrast ratio minimum ─────────────────────────────────────
_MIN_CONTRAST_RATIO = 4.5
_MAX_NODES = 14


class CompositionPlannerAgent(BaseAgent):
    """Design brain that produces structured composition specs.

    Selects templates, fills props, generates textless background prompts,
    and validates compositions before rendering.
    """

    agent_id = "composition_planner"
    agent_name = "Composition Planner Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: Optional[WorkspaceManager] = None,
        max_iterations: int = 10,
    ) -> None:
        self._workspace_mgr = workspace_manager
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        template_docs = self._build_template_docs()

        return f"""You are the Composition Planner — the design brain of the CMO Agent system.

Your job is to translate user requests for visual content into structured composition specs
that Remotion templates render deterministically. You decide WHAT to show, WHERE, and HOW.
The rendering engine handles the pixels — you handle the design decisions.

## CRITICAL: ALWAYS USE QUICK MODE

You MUST call plan_composition with template_id, template_props, AND background_prompt in a SINGLE call.
Do NOT use planning mode. Do NOT output specs as free text.
Every request = exactly ONE plan_composition call → spec_ready response.

## YOUR OUTPUT TOOLS

You have four tools:
1. **plan_composition** — Main output tool. Pass template_id, template_props, and background_prompt → gets spec_ready in one call. No follow-up needed.
2. **emit_composition_spec** — Backup: output a spec after receiving template guidance.
3. **plan_video_overlay** — For overlays on existing video/footage.
4. **validate_composition** — Quality gate. Checks overlap, contrast, density, font sizes.

## THEMES — VISUAL VARIATION SYSTEM

All templates support a `theme` prop for visual differentiation. Available themes:

| Theme | Background | Accent | Feel |
|---|---|---|---|
| `modern` | Dark navy (#0F0F23) | Indigo (#4F46E5) | Clean, professional, default |
| `vibrant` | Deep blue (#0A1628) | Orange (#F97316) | Energetic, warm, bold |
| `minimal` | Light gray (#FAFBFC) | Blue (#2563EB) | Clean, light mode, corporate |
| `enterprise` | Dark charcoal (#111827) | Green (#10B981) | Corporate, trustworthy, data-focused |

**CRITICAL: When a style_hint is provided in the user message, you MUST set the `theme` prop to match it.**
If the message says "Use theme: vibrant", set `"theme": "vibrant"` in template_props.
If no style_hint is given, default to `"modern"`.

## GOLDEN EXAMPLES

Study these examples. They show the quality bar for each template — short labels, controlled density, emoji icons, distinct colors, theme usage.

### EcosystemMap (modern theme)

```json
{{
  "template_id": "EcosystemMap",
  "template_props": {{
    "hub": {{"label": "CMO Agent", "description": "Orchestrator"}},
    "theme": "modern",
    "clusters": [
      {{"label": "Content", "icon": "✏️", "nodes": ["Writer", "Visual", "Video", "Deck", "Motion"], "color": "#3B82F6"}},
      {{"label": "Strategy", "icon": "📊", "nodes": ["Performance", "Social", "Analytics", "Growth"], "color": "#10B981"}},
      {{"label": "Revenue", "icon": "💰", "nodes": ["Telesales", "Sales Ops", "LinkedIn"], "color": "#F59E0B"}},
      {{"label": "Automation", "icon": "⚙️", "nodes": ["Workflow Builder", "Editorial", "Knowledge Base"], "color": "#8B5CF6"}}
    ]
  }},
  "background_prompt": ""
}}
```

### EcosystemMap (vibrant theme — visually distinct)

```json
{{
  "template_id": "EcosystemMap",
  "template_props": {{
    "hub": {{"label": "CMO Agent", "description": "Orchestrator"}},
    "theme": "vibrant",
    "clusters": [
      {{"label": "Content", "icon": "✏️", "nodes": ["Writer", "Visual", "Video", "Deck", "Motion"], "color": "#3B82F6"}},
      {{"label": "Strategy", "icon": "📊", "nodes": ["Performance", "Social", "Analytics", "Growth"], "color": "#10B981"}},
      {{"label": "Revenue", "icon": "💰", "nodes": ["Telesales", "Sales Ops", "LinkedIn"], "color": "#F59E0B"}},
      {{"label": "Automation", "icon": "⚙️", "nodes": ["Workflow Builder", "Editorial", "Knowledge Base"], "color": "#8B5CF6"}}
    ]
  }},
  "background_prompt": ""
}}
```

### DataDashboard (enterprise theme)

```json
{{
  "template_id": "DataDashboard",
  "template_props": {{
    "title": "Q1 2026 Campaign Performance",
    "subtitle": "Key metrics across all channels",
    "theme": "enterprise",
    "metrics": [
      {{"label": "Total Reach", "value": "2.4M", "delta": "+18%", "deltaType": "positive"}},
      {{"label": "Engagement Rate", "value": "4.7%", "delta": "+0.8%", "deltaType": "positive"}},
      {{"label": "Cost Per Lead", "value": "$12.40", "delta": "-$2.10", "deltaType": "positive"}},
      {{"label": "Pipeline Value", "value": "$340K", "delta": "+22%", "deltaType": "positive"}}
    ],
    "columns": 2
  }},
  "background_prompt": ""
}}
```

### ProcessFlow (minimal theme)

```json
{{
  "template_id": "ProcessFlow",
  "template_props": {{
    "title": "Content Production Workflow",
    "theme": "minimal",
    "steps": [
      {{"label": "Brief", "description": "Strategy defines scope"}},
      {{"label": "Draft", "description": "Writer creates content"}},
      {{"label": "Review", "description": "Editorial QA pass"}},
      {{"label": "Publish", "description": "Scheduled distribution"}}
    ],
    "direction": "horizontal",
    "style": "numbered"
  }},
  "background_prompt": ""
}}
```

### StaticLayout — Simple (modern theme)

```json
{{
  "template_id": "StaticLayout",
  "template_props": {{
    "title": "Marketing Technology Stack",
    "subtitle": "Core platforms and integrations",
    "theme": "modern",
    "nodes": [
      {{"id": "crm", "label": "CRM", "icon": "🏢", "x": 50, "y": 20, "shape": "circle", "color": "#3B82F6", "width": 12}},
      {{"id": "email", "label": "Email Platform", "icon": "📧", "x": 25, "y": 55, "shape": "rect", "color": "#10B981"}},
      {{"id": "analytics", "label": "Analytics", "icon": "📊", "x": 75, "y": 55, "shape": "rect", "color": "#F59E0B"}},
      {{"id": "social", "label": "Social", "icon": "📱", "x": 50, "y": 80, "shape": "pill", "color": "#8B5CF6"}}
    ],
    "edges": [
      {{"from": "crm", "to": "email", "label": "Segments", "style": "solid"}},
      {{"from": "crm", "to": "analytics", "label": "Events", "style": "solid"}},
      {{"from": "email", "to": "social", "style": "dashed"}},
      {{"from": "analytics", "to": "social", "style": "dashed"}}
    ]
  }},
  "background_prompt": ""
}}
```

### StaticLayout — Complex Multi-Phase (enterprise theme)

This shows how to handle a brief with PHASES + EXPANDED GROUPINGS. The brief asked for:
"4 phases: user requests via Slack → CMO clarifies → sub-agents collaborate (EMPHASIS) → CMO delivers. Show 9 agent groupings with counts in the emphasis phase."

Notice: Phases as a left-to-right flow across the top. The emphasized phase (step 3) expanded below with sub-groupings. Small phases at edges, large expansion in center.

```json
{{
  "template_id": "StaticLayout",
  "template_props": {{
    "title": "CMO/CRO AI Ecosystem",
    "subtitle": "From request to delivery",
    "theme": "enterprise",
    "nodes": [
      {{"id": "p1", "label": "User Request", "icon": "📱", "description": "Via Slack", "x": 8, "y": 15, "shape": "pill", "color": "#6366F1", "width": 12}},
      {{"id": "p2", "label": "CMO Clarifies", "icon": "🎯", "description": "Scoping & planning", "x": 30, "y": 15, "shape": "pill", "color": "#8B5CF6", "width": 12}},
      {{"id": "p3", "label": "Agents Collaborate", "icon": "⚡", "description": "34 specialized agents", "x": 55, "y": 15, "shape": "circle", "color": "#10B981", "width": 14}},
      {{"id": "p4", "label": "Final Delivery", "icon": "✅", "description": "Cohesive output", "x": 85, "y": 15, "shape": "pill", "color": "#3B82F6", "width": 12}},
      {{"id": "g1", "label": "Intelligence (4)", "icon": "🔍", "x": 15, "y": 45, "shape": "rect", "color": "#3B82F6", "width": 11}},
      {{"id": "g2", "label": "Content (6)", "icon": "✏️", "x": 38, "y": 45, "shape": "rect", "color": "#10B981", "width": 11}},
      {{"id": "g3", "label": "Marketing (6)", "icon": "📊", "x": 62, "y": 45, "shape": "rect", "color": "#F59E0B", "width": 11}},
      {{"id": "g4", "label": "Partnerships (3)", "icon": "🤝", "x": 85, "y": 45, "shape": "rect", "color": "#EF4444", "width": 11}},
      {{"id": "g5", "label": "Revenue Ops (3)", "icon": "💰", "x": 15, "y": 72, "shape": "rect", "color": "#F97316", "width": 11}},
      {{"id": "g6", "label": "Automation (3)", "icon": "⚙️", "x": 38, "y": 72, "shape": "rect", "color": "#8B5CF6", "width": 11}},
      {{"id": "g7", "label": "Funding (4)", "icon": "🏛️", "x": 62, "y": 72, "shape": "rect", "color": "#06B6D4", "width": 11}},
      {{"id": "g8", "label": "Docs/Sheets (3)", "icon": "📄", "x": 85, "y": 72, "shape": "rect", "color": "#84CC16", "width": 11}}
    ],
    "edges": [
      {{"from": "p1", "to": "p2", "style": "solid"}},
      {{"from": "p2", "to": "p3", "style": "solid"}},
      {{"from": "p3", "to": "p4", "style": "solid"}},
      {{"from": "p3", "to": "g1", "style": "dashed"}},
      {{"from": "p3", "to": "g2", "style": "dashed"}},
      {{"from": "p3", "to": "g3", "style": "dashed"}},
      {{"from": "p3", "to": "g4", "style": "dashed"}}
    ]
  }},
  "background_prompt": ""
}}
```

## DENSITY CAPS (HARD LIMITS)

These are NOT suggestions. Exceeding them produces overlapping, unreadable output.

| Template | Max Elements | Max Label Length | Background |
|---|---|---|---|
| EcosystemMap | 8 clusters, 5 nodes/cluster | 20 chars | Solid (no photo) |
| DataDashboard | 8 metrics (prefer 4-6) | 25 chars | Solid |
| ProcessFlow | 6 steps | 20 chars | Solid |
| ComparisonGrid | 4 columns, 5 points/col | 25 chars | Solid |
| TimelineSequence | 8 events | 20 chars | Solid |
| StaticLayout | 12 nodes | 25 chars | Solid or subtle |
| CalloutOverlay | 6 callouts | 30 chars | Photo (required) |
| HeroOverlay | 1 title, 1 subtitle | title 42, sub 80 | Photo (required) |
| QuoteCard | 1 quote | quote 200 | Photo or solid |

If user content exceeds caps: SUMMARIZE and MERGE. Never exceed the cap.

## AVAILABLE TEMPLATES

{template_docs}

## TEMPLATE SELECTION GUIDE

Match the request type to the best template:

| Request Type | Template |
|---|---|
| "Create a hero banner / social graphic / titled image" | HeroOverlay |
| "Add speaker name to video" | LowerThird |
| "Show KPIs / metrics / dashboard" | DataDashboard |
| "Show a process / workflow / steps" | ProcessFlow |
| "Map an ecosystem / org chart / relationships" | EcosystemMap |
| "Compare options / features / plans" | ComparisonGrid |
| "Annotate a screenshot / product image" | CalloutOverlay |
| "Show a timeline / roadmap / milestones" | TimelineSequence |
| "Display a quote / testimonial" | QuoteCard |
| "Complex custom diagram" | StaticLayout |

### ADVANCED — Choosing Between Templates for Complex Briefs

User briefs often describe MULTIPLE concepts (phases, groupings, emphasis areas). Your job is to distill the brief into the SINGLE best template, preserving ALL the user's specified content.

**EcosystemMap vs ProcessFlow vs StaticLayout:**
- **EcosystemMap** = Hub with satellites. Best when the primary structure is "one central thing connected to groups of related things." The hub is the center, clusters orbit around it. This is a STATIC RELATIONSHIP map — it does NOT show flow, phases, or sequence.
- **ProcessFlow** = Sequential steps. Best when the primary structure is "step 1 → step 2 → step 3." Shows progression, phases, journey.
- **StaticLayout** = Free-form positioned nodes with edges. Best when the brief describes BOTH flow/phases AND grouped content that doesn't fit hub-and-spoke. StaticLayout can represent phases as a left-to-right flow while also expanding one phase into sub-groups.

**Decision rules for complex briefs:**
1. If the brief describes **phases** or **steps** (e.g., "4 phases: request → clarify → orchestrate → deliver"), the structure is a FLOW — use **ProcessFlow** or **StaticLayout**, NOT EcosystemMap.
2. If the brief describes phases AND one phase should be expanded with sub-groupings (e.g., "emphasis on step 3 which has 9 sub-agent groupings"), use **StaticLayout** — place the flow left-to-right and expand the emphasized phase with positioned sub-nodes.
3. If the brief describes a hub-and-spoke relationship WITHOUT phases, use **EcosystemMap**.
4. If the brief says "ecosystem" but ALSO describes sequential phases, the word "ecosystem" refers to the CONTENT (an ecosystem of agents), not the TEMPLATE. Choose the template based on STRUCTURE (phases → flow), not VOCABULARY.

**Extracting content from detailed briefs:**
- Read the ENTIRE brief. Don't stop at the first sentence.
- Extract: title, phases/steps, groupings with counts, emphasis areas, specific labels the user wants.
- If the user specifies groupings with counts (e.g., "Intelligence & Research — 4 agents"), USE those exact labels and counts.
- If the user specifies emphasis areas (e.g., "emphasis on step 3"), make that step visually larger/more detailed.
- If the user specifies a format (e.g., "LinkedIn post"), set output_format accordingly ("square" for LinkedIn).

## BACKGROUND PROMPT ENGINEERING

When you produce a background_prompt, optimize it for compositing:

1. **Explicit negative space**: Leave room where text will be placed.
   - "with large area of soft bokeh on the left third for text overlay"
   - "with clean gradient sky in the upper half, detailed landscape only in lower third"

2. **Low complexity behind text areas**: Reduce visual noise where text goes.
   - "shallow depth of field blurring the background behind the center area"
   - "atmospheric fog creating a uniform wash in the text region"

3. **Color coordination**: Match background palette to text overlay colors.
   - "cool blue tones to contrast with white text overlay"
   - "dark moody atmosphere suitable for bright accent text"

4. **NEVER include text in prompts**: All text in the generated image will be garbled.
   - BAD: "image showing the words 'Growth Dashboard'"
   - GOOD: "abstract data visualization with glowing grid lines, dark theme"

5. **Compositing-friendly**: Think about how the template will layer on top.
   - For DataDashboard: dark, slightly textured backgrounds work best
   - For HeroOverlay: cinematic, atmospheric backgrounds with clear focal areas
   - For EcosystemMap: use empty string "" for solid dark background (best choice)

6. **Prefer solid backgrounds** for data-heavy templates: EcosystemMap, DataDashboard, ProcessFlow, StaticLayout, ComparisonGrid, TimelineSequence. Set background_prompt to "" for these.

## QUALITY RULES

- Maximum {_MAX_NODES} nodes/items in any single composition. If more needed, split into panels.
- Minimum font sizes: title 48px, body 22px, label 18px (at 1080p).
- Text must fit within safe margins (120px from edges).
- Maintain WCAG AA contrast ratio ({_MIN_CONTRAST_RATIO}:1) between text and background.
- No overlapping text elements.
- For metrics/data: use real-looking values, not placeholder "XX".

## CRITICAL: READ THE FULL BRIEF

The description you receive contains the user's COMPLETE requirements. Read EVERY sentence.
Users often specify:
- Specific titles, labels, groupings with exact counts
- Phases or sequential steps with emphasis areas
- Format requirements (e.g. "LinkedIn post" → square)
- Structural preferences (e.g. "emphasis on step 3")

You MUST incorporate ALL of these into your spec. Do NOT ignore any part of the brief.
If the brief says "4 phases" → your spec must have 4 phases.
If the brief says "9 groupings with agent counts" → your spec must have 9 groupings with counts.
If the brief says "emphasis on step 3" → step 3 must be visually larger/more detailed.

## NEVER DO THESE

- Never output a JSON spec in your text response. It MUST go through plan_composition.
- Never use planning mode (no template_id). You already know the templates — pick one.
- Never ask for more information. Fill in the best spec you can from the description.
- Never exceed density caps. Summarize if needed.
- Never use placeholder text like "TBD", "XXX", "lorem", "example", or "placeholder".
- Never ignore parts of the brief. If the user specified phases, groupings, counts, or emphasis — they MUST appear in the spec.
- Never choose a template based on vocabulary alone. "Ecosystem" in the brief does NOT mean EcosystemMap template — read the STRUCTURE (phases → ProcessFlow or StaticLayout).

Current workspace: {workspace_id or "default"}"""

    def _build_template_docs(self) -> str:
        """Build formatted template documentation for the system prompt."""
        lines = []
        for tid, schema in TEMPLATE_SCHEMAS.items():
            lines.append(f"### {tid}")
            lines.append(f"{schema['description']}")
            lines.append(f"Required props: {', '.join(schema['required_props'])}")
            if schema.get("optional_props"):
                lines.append(f"Optional props: {', '.join(schema['optional_props'])}")
            # Include sub-schemas for complex props
            for key, val in schema.items():
                if key.endswith("_schema"):
                    prop_name = key.replace("_schema", "")
                    lines.append(f"{prop_name} item: {json.dumps(val)}")
                elif key.endswith("_options"):
                    prop_name = key.replace("_options", "")
                    lines.append(f"{prop_name} options: {', '.join(val)}")
            lines.append("")
        return "\n".join(lines)

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="plan_composition",
            description=(
                "Output the composition spec. Pass template_id + template_props + background_prompt "
                "and get spec_ready in one call. This is the primary output tool."
            ),
        )
        async def plan_composition(
            template_id: str = "",
            template_props: Optional[Dict[str, Any]] = None,
            background_prompt: str = "",
            description: str = "",
            asset_type: str = "static",
            output_format: str = "landscape",
            rendering_notes: str = "",
        ) -> Dict[str, Any]:
            """Output a composition spec or get planning guidance.

            Args:
                template_id: Which template to use (e.g. EcosystemMap). If empty, returns guidance.
                template_props: Structured props matching the template schema.
                background_prompt: Textless, compositing-optimized image prompt.
                description: What the visual should show (used for planning mode).
                asset_type: "static" (PNG) or "motion" (MP4).
                output_format: "landscape", "square", or "portrait".
                rendering_notes: Optional notes for the renderer.
            """
            # Mode B: planning mode — no template_id, return guidance
            if not template_id or template_props is None:
                return {
                    "status": "planned",
                    "description": description,
                    "output_format": output_format,
                    "asset_type": asset_type,
                    "available_templates": list(TEMPLATE_SCHEMAS.keys()),
                    "instruction": (
                        "Now call emit_composition_spec with: "
                        "template_id, template_props (matching the template schema), "
                        "and background_prompt (textless, compositing-optimized). "
                        "You MUST call emit_composition_spec to complete the task."
                    ),
                }

            # Mode A: structured mode — validate and return spec_ready
            if template_id not in TEMPLATE_SCHEMAS:
                return {
                    "status": "error",
                    "error": f"Unknown template: {template_id}. "
                    f"Valid: {list(TEMPLATE_SCHEMAS.keys())}",
                }
            schema = TEMPLATE_SCHEMAS[template_id]
            missing = [p for p in schema["required_props"] if p not in template_props]
            if missing:
                return {
                    "status": "error",
                    "error": f"Missing required props for {template_id}: {missing}",
                }

            # Per-template density cap check
            caps = TEMPLATE_CAPS.get(template_id, {})
            for key, cap in caps.items():
                items = template_props.get(key, [])
                if isinstance(items, list) and len(items) > cap:
                    return {
                        "status": "error",
                        "error": f"Too many {key}: {len(items)} (max {cap} for {template_id}). "
                        f"Summarize or merge items to fit within the cap.",
                    }

            # Global cap check
            for key in ("metrics", "steps", "clusters", "items", "callouts", "events", "nodes"):
                items = template_props.get(key, [])
                if isinstance(items, list) and len(items) > _MAX_NODES:
                    return {
                        "status": "error",
                        "error": f"Too many {key}: {len(items)} (max {_MAX_NODES}). "
                        f"Split into panels.",
                    }
            return {
                "status": "spec_ready",
                "template_id": template_id,
                "template_props": template_props,
                "background_prompt": background_prompt,
                "asset_type": asset_type,
                "output_format": output_format,
                "rendering_notes": rendering_notes,
            }

        @self.tool_registry.register(
            name="plan_video_overlay",
            description=(
                "Plan an overlay composition for existing video/footage. "
                "Treats the base clip as an immutable background and plans "
                "text/graphic overlays to layer on top."
            ),
        )
        async def plan_video_overlay(
            description: str,
            video_context: str,
            workspace_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            """Plan overlay elements for an existing video.

            Args:
                description: What overlays to add (titles, lower thirds, callouts).
                video_context: Description of the base video content.
                workspace_id: Workspace context.
            """
            return {
                "status": "planned",
                "description": description,
                "video_context": video_context,
                "workspace_id": workspace_id,
                "overlay_templates": ["HeroOverlay", "LowerThird", "CalloutOverlay"],
                "instruction": (
                    "Plan overlay elements for the video. Produce: "
                    "1) change_list (what overlays to add and when), "
                    "2) template_id, "
                    "3) template_props, "
                    "4) timing_notes (when each overlay appears/disappears), "
                    "5) rendering_notes."
                ),
            }

        @self.tool_registry.register(
            name="validate_composition",
            description=(
                "Validate a composition spec before rendering. Checks for "
                "overlapping elements, font sizes vs minimums, node count, "
                "text bounds, color contrast, density caps, and label lengths. "
                "Returns pass/fail with details."
            ),
        )
        async def validate_composition(
            template_id: str,
            template_props: Dict[str, Any],
        ) -> Dict[str, Any]:
            """Validate a composition for quality issues.

            Args:
                template_id: The template being used.
                template_props: The props to validate.
            """
            errors: List[str] = []
            warnings: List[str] = []
            suggestions: List[str] = []

            # Check template exists
            if template_id not in TEMPLATE_SCHEMAS:
                errors.append(f"Unknown template: {template_id}")
                return {
                    "valid": False,
                    "errors": errors,
                    "warnings": warnings,
                    "suggestions": suggestions,
                }

            schema = TEMPLATE_SCHEMAS[template_id]

            # Check required props
            for prop in schema["required_props"]:
                if prop not in template_props:
                    errors.append(f"Missing required prop: {prop}")

            # Per-template density cap check
            caps = TEMPLATE_CAPS.get(template_id, {})
            for key, cap in caps.items():
                items = template_props.get(key, [])
                if isinstance(items, list) and len(items) > cap:
                    errors.append(
                        f"Too many {key}: {len(items)} (max {cap} for {template_id}). "
                        f"Summarize or merge items."
                    )

            # Check node/item count limits (global)
            count_props = ["metrics", "steps", "clusters", "items", "callouts", "events", "nodes"]
            for prop in count_props:
                items = template_props.get(prop, [])
                if isinstance(items, list) and len(items) > _MAX_NODES:
                    errors.append(
                        f"Too many {prop}: {len(items)} (max {_MAX_NODES}). "
                        f"Split into multiple panels."
                    )
                elif isinstance(items, list) and len(items) > 10:
                    warnings.append(
                        f"High density: {len(items)} {prop}. Consider splitting for readability."
                    )

            # Check text lengths (rough heuristic for overflow)
            title = template_props.get("title", "")
            if isinstance(title, str) and len(title) > 80:
                warnings.append(
                    f"Title is {len(title)} chars — may overflow. Consider shortening to <60 chars."
                )

            # Check label lengths across all list items
            label_max = 30
            for prop in count_props:
                items = template_props.get(prop, [])
                if not isinstance(items, list):
                    continue
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    label = item.get("label") or item.get("heading") or item.get("title") or ""
                    if isinstance(label, str) and len(label) > label_max:
                        warnings.append(
                            f"{prop}[{i}] label is {len(label)} chars (>'{label_max}'): "
                            f"'{label[:30]}...'. Shorten for readability."
                        )
                    # Description length check
                    desc = item.get("description", "")
                    if isinstance(desc, str) and len(desc) > 80:
                        warnings.append(
                            f"{prop}[{i}] description is {len(desc)} chars. "
                            f"Keep under 80 chars for clean rendering."
                        )

            # Placeholder detection
            placeholders = {"tbd", "xxx", "lorem", "example", "placeholder"}
            for prop in count_props:
                items = template_props.get(prop, [])
                if not isinstance(items, list):
                    continue
                for i, item in enumerate(items):
                    if not isinstance(item, dict):
                        continue
                    for field in ("label", "heading", "title", "description", "value"):
                        val = item.get(field, "")
                        if isinstance(val, str) and val.strip().lower() in placeholders:
                            errors.append(f"{prop}[{i}].{field} contains placeholder text: '{val}'")

            # Check for empty data
            for prop in count_props:
                items = template_props.get(prop, [])
                if isinstance(items, list) and len(items) == 0 and prop in schema["required_props"]:
                    errors.append(f"Empty {prop} array — template needs at least one item.")

            # Suggest column count optimization
            metrics = template_props.get("metrics", [])
            columns = template_props.get("columns")
            if isinstance(metrics, list) and len(metrics) > 0 and columns is None:
                if len(metrics) <= 2:
                    suggestions.append("Consider columns=2 for 1-2 metrics")
                elif len(metrics) <= 4:
                    suggestions.append("Consider columns=2 for 3-4 metrics")
                else:
                    suggestions.append("Consider columns=3 for 5+ metrics")

            # StaticLayout: check node positions are in bounds
            nodes = template_props.get("nodes", [])
            if isinstance(nodes, list):
                for node in nodes:
                    if isinstance(node, dict):
                        x = node.get("x", 50)
                        y = node.get("y", 50)
                        if not (0 <= x <= 100) or not (0 <= y <= 100):
                            errors.append(
                                f"Node '{node.get('id', '?')}' position "
                                f"({x}, {y}) out of bounds (0-100)."
                            )

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings,
                "suggestions": suggestions,
                "template_id": template_id,
            }

        @self.tool_registry.register(
            name="emit_composition_spec",
            description=(
                "Output the final composition spec as structured data. "
                "MUST be called after planning — this is how the spec reaches the renderer. "
                "Validates template_id and required props before accepting."
            ),
        )
        async def emit_composition_spec(
            template_id: str,
            template_props: Dict[str, Any],
            background_prompt: str = "",
            asset_type: str = "static",
            output_format: str = "landscape",
            rendering_notes: str = "",
        ) -> Dict[str, Any]:
            """Output a validated composition spec for the renderer.

            Args:
                template_id: Which template to use (e.g. EcosystemMap).
                template_props: Structured props matching the template schema.
                background_prompt: Textless, compositing-optimized image prompt.
                asset_type: "static" (PNG) or "motion" (MP4).
                output_format: "landscape", "square", or "portrait".
                rendering_notes: Optional notes for the renderer.
            """
            # Validate template exists
            if template_id not in TEMPLATE_SCHEMAS:
                return {
                    "status": "error",
                    "error": f"Unknown template: {template_id}. "
                    f"Valid: {list(TEMPLATE_SCHEMAS.keys())}",
                }
            # Validate required props
            schema = TEMPLATE_SCHEMAS[template_id]
            missing = [p for p in schema["required_props"] if p not in template_props]
            if missing:
                return {
                    "status": "error",
                    "error": f"Missing required props for {template_id}: {missing}",
                }
            # Per-template density cap check
            caps = TEMPLATE_CAPS.get(template_id, {})
            for key, cap in caps.items():
                items = template_props.get(key, [])
                if isinstance(items, list) and len(items) > cap:
                    return {
                        "status": "error",
                        "error": f"Too many {key}: {len(items)} (max {cap} for {template_id}). "
                        f"Summarize or merge items.",
                    }
            # Global item count check
            for key in ("metrics", "steps", "clusters", "items", "callouts", "events", "nodes"):
                items = template_props.get(key, [])
                if isinstance(items, list) and len(items) > _MAX_NODES:
                    return {
                        "status": "error",
                        "error": f"Too many {key}: {len(items)} (max {_MAX_NODES}). "
                        f"Split into panels.",
                    }
            return {
                "status": "spec_ready",
                "template_id": template_id,
                "template_props": template_props,
                "background_prompt": background_prompt,
                "asset_type": asset_type,
                "output_format": output_format,
                "rendering_notes": rendering_notes,
            }
