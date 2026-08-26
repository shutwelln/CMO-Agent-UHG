"""UX/UI Design Agent - website UX audits, design systems, component specs, accessibility."""

from __future__ import annotations

import base64
import json
import mimetypes
from pathlib import Path
from typing import Any, Dict, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# Quality criteria for RefinementLoop (5 dimensions)
_UX_UI_CRITERIA = [
    QualityCriterion(
        name="visual_hierarchy",
        description="Layout, typography, spacing create clear eye-flow and content prioritization",
    ),
    QualityCriterion(
        name="accessibility_compliance",
        description=(
            "WCAG 2.1 AA: contrast >= 4.5:1, touch targets >= 44px, "
            "ARIA landmarks, keyboard navigation, screen reader support"
        ),
    ),
    QualityCriterion(
        name="interaction_design_quality",
        description=(
            "States (hover/focus/active/disabled), transitions, "
            "loading/error/empty UX fully specified with timing"
        ),
    ),
    QualityCriterion(
        name="responsive_design_completeness",
        description="Mobile/tablet/desktop breakpoints fully covered with layout shifts documented",
    ),
    QualityCriterion(
        name="implementation_specificity",
        description=(
            "Concrete Tailwind classes, shadcn/ui component names, "
            "exact px/rem values, CSS properties - ready for developer handoff"
        ),
    ),
]

# Workspace-specific design system context can be injected here by adding entries below
# (key = workspace_id.lower(), value = design system spec string).
_DESIGN_SYSTEM_CONTEXTS: dict[str, str] = {}


class UxUiDesignAgent(BaseAgent):
    """Handles website UX/UI design: audits, design systems, component specs, accessibility.

    Produces implementation-ready specs for React/Tailwind/shadcn developers.
    Does NOT design experiments (CRO), own funnel strategy (Acquisition),
    or define page taxonomy (SEO/AEO).
    """

    agent_id = "ux_ui_design_agent"
    agent_name = "UX/UI Design Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._config = ConfigRepo(db)
        self._workspace_mgr = workspace_manager
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    async def _get_design_system_context(self, workspace_id: str) -> str:
        """Load persisted design system context for the workspace."""
        try:
            rows = await self._config.get(workspace_id, "design_system_context")
            if rows:
                return rows
        except Exception:
            pass
        return ""

    async def _save_design_system_context(self, workspace_id: str, context: str) -> None:
        """Persist design system context for the workspace."""
        try:
            await self._config.set(workspace_id, "design_system_context", context)
        except Exception as e:
            logger.warning("failed_to_save_design_context", error=str(e))

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        workspace_context = ""
        if workspace_id:
            workspace_context = _DESIGN_SYSTEM_CONTEXTS.get(workspace_id.lower(), "")

        return f"""You are the UX/UI Design Agent, a specialist in website user experience and interface design.

Your mission: Audit, design, and spec website UX/UI improvements that are implementation-ready for developers.

EXPERTISE DOMAINS (8 areas):
1. Design system governance - typography scales, color palettes, spacing tokens, design tokens
2. Component design specs - React/Tailwind/shadcn props, variants, states, composition patterns
3. Page layout and visual hierarchy - grid systems, whitespace, content priority, F-pattern and Z-pattern scanning
4. Navigation architecture - mega-menus, mobile nav, dropdowns, sticky headers, breadcrumbs, footer
5. Interaction design - hover/focus/active states, transitions, loading/error/empty states, form UX, micro-interactions
6. Accessibility (WCAG 2.1 AA) - color contrast >= 4.5:1, focus indicators, touch targets >= 44px, ARIA landmarks, keyboard navigation, screen reader support, skip links
7. Responsive design - mobile-first breakpoints, touch vs pointer, fluid typography, layout shifts
8. UX heuristic evaluation - Nielsen's 10 heuristics, cognitive load reduction, Fitts's Law, Hick's Law, Jakob's Law
{workspace_context}
SCOPE BOUNDARIES:
- YOU OWN: design system, component specs, page layout, nav architecture, interaction design, accessibility, responsive design, UX evaluation, design-to-dev handoff, screenshot-based UX audits
- Acquisition Agent: funnel strategy, friction identification (identifies WHAT pages have problems)
- CRO Agent: experiment design, A/B test governance (tests proposed changes)
- SEO/AEO Agent: page taxonomy, URL structures, structured data, information architecture
- Visual Agent: image generation
- Writer Agent: content copy

HANDOFF PROTOCOLS:
- FROM Acquisition: Receives friction reports, produces design fixes
- TO CRO: Structured recommendation (current state, proposed design, UX rationale, metric) for experiment design
- TO Writer: Copy requirements (tone, length, purpose) for UI components
- FROM SEO/AEO: Page governance standards, integrates into specs

OUTPUT FORMAT:
All specs must be implementation-ready with concrete values:
- Tailwind CSS classes (not vague "add spacing")
- shadcn/ui component names (not "use a modal")
- Exact px/rem values for spacing, sizing
- CSS transition properties with timing
- ARIA attributes and roles
- Responsive breakpoint behavior

IMPORTANT RULES:
- All benchmark claims MUST be flagged with [VERIFY] prefix
- All specs are saved as drafts for human review
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes or en dashes. NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels.
- When evaluating screenshots, provide specific, actionable findings with exact coordinates/areas referenced"""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="run_ux_audit",
            description="Comprehensive UX audit: heuristic evaluation (Nielsen's 10), accessibility (WCAG 2.1 AA), visual hierarchy, interaction design, responsive behavior, prioritized fixes with implementation specs.",
        )
        async def run_ux_audit(
            workspace_id: str,
            page_description: str,
            page_type: str = "landing_page",
            target_audience: str = "",
            current_issues: str = "",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            design_ctx = await self._get_design_system_context(workspace_id)

            prompt = f"""Conduct a comprehensive UX/UI audit of this page.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
DESIGN SYSTEM CONTEXT: {design_ctx[:1000] if design_ctx else "No saved design system."}
PAGE TYPE: {page_type}
PAGE DESCRIPTION: {page_description}
TARGET AUDIENCE: {target_audience or "Not specified"}
KNOWN ISSUES: {current_issues or "None reported"}

Structure the audit with these sections:

## 1. Heuristic Evaluation (Nielsen's 10)
For each applicable heuristic, rate severity (Critical/Major/Minor/Good) and provide specific findings:
- Visibility of system status
- Match between system and real world
- User control and freedom
- Consistency and standards
- Error prevention
- Recognition rather than recall
- Flexibility and efficiency of use
- Aesthetic and minimalist design
- Help users recognize, diagnose, and recover from errors
- Help and documentation

## 2. Accessibility Audit (WCAG 2.1 AA)
- Color contrast compliance (4.5:1 body text, 3:1 large text)
- Touch target sizes (minimum 44x44px)
- Keyboard navigation and focus management
- ARIA landmarks and roles
- Screen reader experience
- Form labels and error messages
- Skip links and heading hierarchy

## 3. Visual Hierarchy Analysis
- Content prioritization and scanning patterns (F/Z pattern)
- Typography hierarchy effectiveness
- Whitespace usage and content density
- CTA visibility and prominence
- Above-the-fold content effectiveness

## 4. Interaction Design Review
- State management (hover, focus, active, disabled, loading, error, empty)
- Transition and animation quality
- Form UX (validation, error recovery, progressive disclosure)
- Feedback mechanisms (toasts, inline, confirmation)

## 5. Responsive Design Assessment
- Mobile layout effectiveness
- Touch interaction readiness
- Breakpoint transition smoothness
- Content reflow and priority shifts

## 6. Prioritized Recommendations
For each recommendation:
- Priority: P0 (critical) / P1 (high) / P2 (medium) / P3 (nice-to-have)
- Current state: what exists now
- Proposed fix: implementation-ready spec with Tailwind classes, component names, exact values
- UX rationale: which heuristic/principle this addresses
- Metric to track: how to measure improvement

Flag all benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_UX_UI_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="ux_audit_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"UX Audit: {page_type} - {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="ux_audit",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="design_spec",
            description="Generate or audit design system, component specs, or page layouts. Covers typography, colors, spacing, component standards, design tokens, section ordering, grid systems, content density. Also persists design context.",
        )
        async def design_spec(
            workspace_id: str,
            spec_type: str,
            subject: str,
            requirements: str = "",
            current_state: str = "",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            design_ctx = await self._get_design_system_context(workspace_id)

            type_instructions = {
                "design_system": """Create a comprehensive design system specification:
## Typography Scale
- Font family, weights, sizes for each level (h1-h6, body, caption, overline)
- Line heights and letter spacing
- Tailwind classes for each

## Color Palette
- Primary, secondary, accent, neutral, semantic (success, warning, error, info)
- HSL values and Tailwind custom colors
- Contrast ratios for all text/background combinations

## Spacing System
- Base unit and scale (4px, 8px, 12px, 16px, 24px, 32px, 48px, 64px)
- Component internal padding standards
- Section spacing standards

## Component Standards
- Button variants (primary, secondary, ghost, destructive) with sizes (sm, md, lg)
- Card patterns (content card, feature card, pricing card)
- Form field standards
- Navigation patterns

## Animation and Transitions
- Timing functions and durations
- Standard transitions for common interactions
- Motion principles""",
                "component": f"""Create a detailed component specification for: {subject}

## Component Overview
- Purpose and use cases
- shadcn/ui base component (if applicable)

## Props and Variants
- All props with types and defaults
- Size variants with exact Tailwind classes
- Color/theme variants

## States
- Default, hover, focus, active, disabled, loading, error
- Exact Tailwind classes and CSS for each state

## Responsive Behavior
- Mobile (< 640px), Tablet (640-1024px), Desktop (> 1024px)
- Layout changes per breakpoint

## Accessibility
- ARIA attributes and roles
- Keyboard interaction pattern
- Screen reader announcements

## Usage Examples
- Code-ready JSX with Tailwind classes""",
                "page_layout": f"""Create a page layout specification for: {subject}

## Page Structure
- Section ordering with content purpose
- Grid system (columns, gaps, container width)
- Content density per section

## Visual Hierarchy
- Primary, secondary, tertiary content zones
- CTA placement and prominence
- Whitespace distribution

## Responsive Layouts
- Mobile stack order
- Tablet adjustments
- Desktop multi-column layout
- Exact Tailwind grid/flex classes per breakpoint

## Section Specifications
For each section:
- Component composition
- Spacing (padding, margins)
- Background treatment
- Content constraints (max-width, line clamp)

## Interaction Points
- Scroll behaviors (sticky elements, parallax, reveal)
- Click/tap targets with minimum sizing
- Form placement and flow""",
            }

            spec_instruction = type_instructions.get(
                spec_type,
                f"Create a detailed {spec_type} specification for: {subject}",
            )

            prompt = f"""Generate an implementation-ready design specification.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
DESIGN SYSTEM CONTEXT: {design_ctx[:1000] if design_ctx else "No saved design system."}
SPEC TYPE: {spec_type}
SUBJECT: {subject}
REQUIREMENTS: {requirements or "None specified"}
CURRENT STATE: {current_state or "New design - no existing version"}

{spec_instruction}

All values must be concrete and implementation-ready:
- Use Tailwind CSS classes (e.g., "p-6 md:p-8 lg:p-10")
- Reference shadcn/ui components by name (e.g., "Card from @/components/ui/card")
- Provide exact px/rem values alongside Tailwind classes
- Include responsive breakpoint behavior
- Include accessibility attributes

Flag all benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_UX_UI_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix=f"ux_design_spec_{spec_type}_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            # Persist design system context if this was a design_system spec
            if spec_type == "design_system":
                await self._save_design_system_context(workspace_id, result.content[:3000])

            title = f"Design Spec ({spec_type}): {subject}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type=f"design_spec_{spec_type}",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="navigation_design",
            description="Header/navbar, mega-menu/dropdowns, mobile nav, footer, breadcrumbs, in-page nav with responsive specs.",
        )
        async def navigation_design(
            workspace_id: str,
            site_structure: str,
            navigation_goals: str = "",
            current_navigation: str = "",
            page_count_estimate: int = 0,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            design_ctx = await self._get_design_system_context(workspace_id)

            prompt = f"""Design a comprehensive navigation system.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
DESIGN SYSTEM CONTEXT: {design_ctx[:1000] if design_ctx else "No saved design system."}
SITE STRUCTURE: {site_structure}
NAVIGATION GOALS: {navigation_goals or "Improve discoverability and reduce friction"}
CURRENT NAVIGATION: {current_navigation or "Not described"}
ESTIMATED PAGE COUNT: {page_count_estimate or "Unknown"}

## 1. Desktop Navigation
- Header layout (logo, nav items, CTAs, utilities)
- Primary nav pattern (flat links, dropdowns, mega-menu)
- Secondary nav (utility bar, account, search)
- Active state indicators
- Exact Tailwind/shadcn implementation

## 2. Mobile Navigation
- Trigger pattern (hamburger, bottom nav, tab bar)
- Drawer/sheet implementation (left, right, bottom)
- Navigation hierarchy in mobile context
- Touch target sizing (min 44x44px)
- Gesture support (swipe to close)
- shadcn Sheet/Drawer component spec

## 3. Footer Navigation
- Content organization (columns, sections)
- Link hierarchy and grouping
- Legal/utility links placement
- Newsletter/CTA placement

## 4. Breadcrumbs
- When to show (depth >= 2 recommended)
- Schema markup (BreadcrumbList JSON-LD)
- Responsive truncation strategy
- shadcn Breadcrumb component spec

## 5. In-Page Navigation
- Table of contents for long pages
- Anchor links with smooth scroll
- Sticky sub-nav for deep pages
- Progress indicators

## 6. Accessibility
- Skip navigation link
- ARIA navigation landmarks (nav, role="navigation")
- Keyboard navigation (Tab, Arrow keys, Escape, Enter)
- Focus trap for mobile nav overlay
- Screen reader announcements for state changes

## 7. Responsive Breakpoints
- < 640px: mobile nav
- 640-1024px: simplified desktop or mobile
- > 1024px: full desktop nav
- Transition behavior between breakpoints

All specs must include exact Tailwind classes and shadcn/ui component references.
Flag all benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_UX_UI_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="ux_navigation_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Navigation Design: {workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="navigation_design",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="interaction_design",
            description="Transitions, loading/error states, form UX, micro-interactions, animation specs with exact CSS/Tailwind values.",
        )
        async def interaction_design(
            workspace_id: str,
            interaction_context: str,
            interaction_type: str = "general",
            component_or_page: str = "",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            design_ctx = await self._get_design_system_context(workspace_id)

            prompt = f"""Design detailed interaction specifications.

BRAND CONTEXT: {brand_voice[:500] if brand_voice else "No brand voice configured."}
DESIGN SYSTEM CONTEXT: {design_ctx[:1000] if design_ctx else "No saved design system."}
CONTEXT: {interaction_context}
INTERACTION TYPE: {interaction_type}
COMPONENT/PAGE: {component_or_page or "General"}

## 1. State Definitions
For each interactive element, define ALL states:
- Default: resting appearance
- Hover: cursor over (desktop only)
- Focus: keyboard focus (visible focus ring)
- Active: being clicked/pressed
- Disabled: non-interactive appearance
- Loading: async operation in progress
- Error: validation or operation failure
- Success: operation completed
- Empty: no data/content available

For each state provide:
- Tailwind classes
- CSS custom properties if needed
- Transition properties (property, duration, easing)

## 2. Transitions and Animations
- Enter/exit animations for dynamic content
- Page transition patterns
- Loading skeletons (shadcn Skeleton component)
- Progress indicators
- Timing: fast (150ms), base (200ms), slow (300ms)
- Easing: cubic-bezier(0.4, 0, 0.2, 1) for standard, cubic-bezier(0, 0, 0.2, 1) for decelerate

## 3. Loading and Error UX
- Skeleton loading patterns
- Spinner/progress placement
- Error message patterns (inline, toast, banner)
- Retry mechanisms
- Empty state design
- Optimistic UI patterns

## 4. Form UX
- Input validation timing (onBlur vs onChange)
- Error message placement and style
- Progressive disclosure
- Multi-step form patterns
- Auto-save indicators
- Submission feedback

## 5. Micro-interactions
- Button press feedback
- Toggle animations
- Accordion expand/collapse
- Tooltip appearance
- Notification badges
- Scroll-triggered reveals

## 6. Accessibility
- Focus visible styles (2px solid, offset 2px)
- Reduced motion support (@media (prefers-reduced-motion))
- ARIA live regions for dynamic content
- Status announcements for screen readers

All values must be exact Tailwind classes or CSS properties.
Flag all benchmark claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_UX_UI_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="ux_interaction_refinement",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice, hooks)

            title = f"Interaction Design: {interaction_type} - {component_or_page or workspace_id}"
            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="interaction_design",
                title=title,
                body=result.content,
            )

            return {
                "draft_id": draft.id,
                "title": title,
                "body_preview": result.content[:500],
                "status": "pending",
            }

        @self.tool_registry.register(
            name="screenshot_ux_audit",
            description="Vision-based UX audit from screenshot. Sends image to Claude vision for analysis across 8 UX dimensions with specific, actionable findings.",
        )
        async def screenshot_ux_audit(
            workspace_id: str,
            screenshot_path: str,
            page_type: str = "landing_page",
            audit_focus: str = "",
        ) -> Dict[str, Any]:
            # Read and encode the screenshot
            path = Path(screenshot_path)
            if not path.exists():
                return {"error": f"Screenshot not found: {screenshot_path}"}

            image_bytes = path.read_bytes()
            mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")

            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            design_ctx = await self._get_design_system_context(workspace_id)

            eval_prompt = f"""Analyze this screenshot as a UX/UI expert. Provide a detailed audit.

PAGE TYPE: {page_type}
AUDIT FOCUS: {audit_focus or "Full UX evaluation"}
BRAND CONTEXT: {brand_voice[:300] if brand_voice else "Not specified"}
DESIGN SYSTEM: {design_ctx[:500] if design_ctx else "Not specified"}

Evaluate across these 8 dimensions. For each, provide a score (1-10) and specific findings:

1. Visual Hierarchy (1-10): Is content prioritized? Do eyes flow naturally? Are CTAs prominent?
2. Typography (1-10): Readability, scale consistency, weight usage, line spacing
3. Color Usage (1-10): Palette consistency, contrast, emotional tone, brand alignment
4. Spacing/Whitespace (1-10): Content density, breathing room, grouping clarity
5. Accessibility (1-10): Visible contrast issues, touch target sizes, focus indicators
6. Navigation Clarity (1-10): Can users find what they need? Is the current location clear?
7. Content Density (1-10): Information overload vs. scannability, progressive disclosure
8. Mobile Readiness (1-10): Would this work on mobile? Touch-friendly? Responsive indicators?

For EACH finding, reference the specific area of the screenshot (top/middle/bottom, left/right).

Then provide:

## Top 5 Priority Fixes
For each:
- What: specific issue found
- Where: location in the screenshot
- Why: UX principle violated
- Fix: implementation-ready spec (Tailwind classes, component changes)
- Impact: expected improvement

Return as JSON:
{{"scores": {{"visual_hierarchy": N, "typography": N, "color_usage": N, "spacing": N, "accessibility": N, "navigation_clarity": N, "content_density": N, "mobile_readiness": N}}, "overall_score": N, "findings": ["..."], "priority_fixes": [{{"what": "...", "where": "...", "why": "...", "fix": "...", "impact": "..."}}]}}"""

            # Build multimodal message (same pattern as visual_evaluator.py)
            content_blocks = [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": eval_prompt,
                },
            ]

            response = await self.llm.complete(
                messages=[Message(role="user", content=content_blocks)],
                temperature=0.3,
            )

            # Parse JSON response
            try:
                # Try to extract JSON from response
                text = response.content
                json_start = text.find("{")
                json_end = text.rfind("}") + 1
                if json_start >= 0 and json_end > json_start:
                    audit_result = json.loads(text[json_start:json_end])
                else:
                    audit_result = {"raw_analysis": text}
            except (json.JSONDecodeError, ValueError):
                audit_result = {"raw_analysis": response.content}

            # Format as readable draft content
            scores = audit_result.get("scores", {})
            overall = audit_result.get("overall_score", "N/A")
            findings = audit_result.get("findings", [])
            fixes = audit_result.get("priority_fixes", [])

            body_parts = [f"# Screenshot UX Audit: {page_type}\n"]
            body_parts.append(f"**Overall Score**: {overall}/10\n")

            if scores:
                body_parts.append("## Dimension Scores")
                for dim, score in scores.items():
                    label = dim.replace("_", " ").title()
                    body_parts.append(f"- {label}: {score}/10")
                body_parts.append("")

            if findings:
                body_parts.append("## Key Findings")
                for i, finding in enumerate(findings, 1):
                    body_parts.append(f"{i}. {finding}")
                body_parts.append("")

            if fixes:
                body_parts.append("## Priority Fixes")
                for i, fix in enumerate(fixes, 1):
                    body_parts.append(f"\n### Fix {i}: {fix.get('what', 'N/A')}")
                    body_parts.append(f"- Where: {fix.get('where', 'N/A')}")
                    body_parts.append(f"- Why: {fix.get('why', 'N/A')}")
                    body_parts.append(f"- Fix: {fix.get('fix', 'N/A')}")
                    body_parts.append(f"- Impact: {fix.get('impact', 'N/A')}")

            body = "\n".join(body_parts)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="screenshot_ux_audit",
                title=f"Screenshot UX Audit: {page_type} - {workspace_id}",
                body=body,
            )

            return {
                "draft_id": draft.id,
                "title": f"Screenshot UX Audit: {page_type}",
                "scores": scores,
                "overall_score": overall,
                "priority_fixes_count": len(fixes),
                "body_preview": body[:500],
                "status": "pending",
            }
