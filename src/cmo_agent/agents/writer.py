"""Writer Agent - content generation with brand voice and quality refinement."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import DraftRepo, OpportunityRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook, make_proofread_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# Writer quality criteria
_WRITER_CRITERIA = [
    QualityCriterion(name="brand_voice", description="Brand voice alignment"),
    QualityCriterion(name="clarity", description="Clarity and readability"),
    QualityCriterion(
        name="fact_checking", description="Factual claims properly flagged with [VERIFY]"
    ),
    QualityCriterion(name="engagement", description="Engaging and actionable"),
]


class WriterAgent(BaseAgent):
    """Creates marketing content in brand voice with quality refinement."""

    agent_id = "writer_agent"
    agent_name = "Writer Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        proofreader: Optional[Any] = None,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._opportunities = OpportunityRepo(db)
        self._workspace_mgr = workspace_manager
        self._proofreader = proofreader
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        # Brand voice is injected dynamically per tool call, not here,
        # because the base system prompt is set once at the start.
        return """You are the Writer Agent, a specialized content creator for marketing teams.

You produce: newsletters, blog posts, Reddit replies, and social media content.
All content goes through human approval before publishing.

IMPORTANT RULES:
- All specific claims MUST be flagged with [VERIFY] prefix
- Never auto-publish; all content is saved as drafts
- Include sources/references where applicable
- Follow the brand voice guidelines exactly when provided
- ABBREVIATIONS: Always spell out abbreviations/acronyms on first use with the abbreviation in parentheses — e.g., "Total Addressable Market (TAM)". After the first occurrence, use the abbreviation only.
- ANTI-AI WRITING (MANDATORY):
  • NEVER use em dashes (—) or en dashes (–). Use commas, periods, semicolons, or " - " (spaced hyphen) instead.
  • NEVER bold words in the middle of a sentence. Bolding is only for section headers or standalone labels.
  These patterns are obvious AI tells. Strip them from all output.

When generating content, always return it with clear sections and structure.

SEARCH CONTENT RULES:
- For any content targeting search engines (blog posts, DMA pages, location pages,
  merchant pages, comparison pages, informational guides), you MUST follow the structured
  brief from the SEO/AEO Agent exactly.
- Do NOT independently choose keyword targets for search content.
- Follow all heading structures, FAQ requirements, direct answer blocks, word count ranges,
  and schema instructions specified in the brief.
- Non-search content (newsletters, Reddit replies, social media posts, email copy) does
  NOT require an SEO brief."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="draft_newsletter",
            description="Generate a newsletter draft in brand voice. Supports quality refinement loop.",
        )
        async def draft_newsletter(
            workspace_id: str,
            topic: str,
            opportunity_ids: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)
            opp_context = await self._gather_opportunities(opportunity_ids)

            prompt = self._build_content_prompt(
                content_type="newsletter",
                topic=topic,
                brand_voice=brand_voice,
                extra_context=opp_context,
            )

            body, verify_flags = await self._generate_with_refinement(prompt, brand_voice)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="newsletter",
                title=topic,
                body=body,
                verify_flags=verify_flags,
                opportunity_ids=opportunity_ids,
            )

            return {
                "draft_id": draft.id,
                "title": topic,
                "body_preview": body[:500],
                "verify_flags": verify_flags,
                "status": "pending",
            }

        @self.tool_registry.register(
            name="draft_blog_post",
            description="Generate a blog post draft in brand voice.",
        )
        async def draft_blog_post(
            workspace_id: str,
            topic: str,
            target_length: str = "medium",
            seo_keywords: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            length_guide = {
                "short": "~500 words",
                "medium": "~1000 words",
                "long": "~2000 words",
            }.get(target_length, "~1000 words")

            extra = f"Target length: {length_guide}"
            if seo_keywords:
                extra += f"\nSEO keywords to include: {', '.join(seo_keywords)}"

            prompt = self._build_content_prompt(
                content_type="blog post",
                topic=topic,
                brand_voice=brand_voice,
                extra_context=extra,
            )

            body, verify_flags = await self._generate_with_refinement(prompt, brand_voice)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="blog",
                title=topic,
                body=body,
                verify_flags=verify_flags,
            )

            return {
                "draft_id": draft.id,
                "title": topic,
                "body_preview": body[:500],
                "verify_flags": verify_flags,
                "status": "pending",
            }

        @self.tool_registry.register(
            name="draft_reddit_reply",
            description="Generate a helpful Reddit reply that optionally mentions the brand.",
        )
        async def draft_reddit_reply(
            workspace_id: str,
            post_title: str,
            post_content: str,
            subreddit: str,
            opportunity_id: Optional[str] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Write a helpful Reddit reply for r/{subreddit}.

BRAND VOICE:
{brand_voice}

ORIGINAL POST:
Title: {post_title}
Content: {post_content[:1000]}

GUIDELINES:
- Be genuinely helpful FIRST
- Match the subreddit's tone and culture
- Only mention the brand if it naturally fits and adds value
- Keep it conversational and authentic
- Flag any specific claims with [VERIFY]
- Do NOT be salesy or promotional"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            body = response.content

            if self._proofreader:
                try:
                    pr = await self._proofreader.proofread(body, context="reddit reply")
                    if pr.has_corrections:
                        body = pr.corrected_text
                except Exception:
                    pass

            verify_flags = _extract_verify_flags(body)
            opp_ids = [opportunity_id] if opportunity_id else None

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="reddit_reply",
                title=f"Reply: {post_title[:80]}",
                body=body,
                verify_flags=verify_flags,
                opportunity_ids=opp_ids,
            )

            return {
                "draft_id": draft.id,
                "subreddit": subreddit,
                "body_preview": body[:500],
                "verify_flags": verify_flags,
                "status": "pending",
            }

        @self.tool_registry.register(
            name="draft_social_post",
            description="Generate social media content for a specific platform.",
        )
        async def draft_social_post(
            workspace_id: str,
            platform: str,
            topic: str,
            max_length: Optional[int] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            length_note = ""
            if max_length:
                length_note = f"\nMaximum length: {max_length} characters"
            elif platform.lower() == "twitter":
                length_note = "\nMaximum length: 280 characters"

            prompt = f"""Write a {platform} post about: {topic}

BRAND VOICE:
{brand_voice}

GUIDELINES:
- Optimized for {platform} engagement
- Include relevant hashtags if appropriate{length_note}
- Flag any specific claims with [VERIFY]"""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.8,
            )

            body = response.content

            if self._proofreader:
                try:
                    pr = await self._proofreader.proofread(body, context="social media post")
                    if pr.has_corrections:
                        body = pr.corrected_text
                except Exception:
                    pass

            verify_flags = _extract_verify_flags(body)

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="social",
                title=f"{platform}: {topic[:60]}",
                body=body,
                verify_flags=verify_flags,
            )

            return {
                "draft_id": draft.id,
                "platform": platform,
                "body": body,
                "verify_flags": verify_flags,
                "status": "pending",
            }

        @self.tool_registry.register(
            name="revise_draft",
            description="Revise an existing draft based on feedback.",
        )
        async def revise_draft(draft_id: str, feedback: str) -> Dict[str, Any]:
            draft = await self._drafts.get(draft_id)
            if not draft:
                return {"error": f"Draft {draft_id} not found"}

            brand_voice = await self._workspace_mgr.get_brand_voice(draft.workspace_id)

            prompt = f"""Revise the following {draft.content_type} based on the feedback.

BRAND VOICE:
{brand_voice}

CURRENT DRAFT:
{draft.body}

FEEDBACK:
{feedback}

Produce the revised version. Flag any new claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            new_body = response.content

            if self._proofreader:
                try:
                    pr = await self._proofreader.proofread(new_body, context="draft revision")
                    if pr.has_corrections:
                        new_body = pr.corrected_text
                except Exception:
                    pass

            verify_flags = _extract_verify_flags(new_body)
            await self._drafts.update_body(draft_id, new_body, verify_flags)

            return {
                "draft_id": draft_id,
                "body_preview": new_body[:500],
                "verify_flags": verify_flags,
                "status": "revised",
            }

        @self.tool_registry.register(
            name="get_draft",
            description="Retrieve a draft by its ID.",
        )
        async def get_draft(draft_id: str) -> Dict[str, Any]:
            draft = await self._drafts.get(draft_id)
            if not draft:
                return {"error": f"Draft {draft_id} not found"}
            return draft.model_dump(mode="json")


    # ── Internal methods ──────────────────────────────────────────────────

    async def _generate_with_refinement(
        self, prompt: str, brand_voice: str
    ) -> tuple[str, List[str]]:
        """Generate content with a Ralph-style quality refinement loop.

        Uses the shared RefinementLoop with Haiku for critique and Sonnet
        for generation/revision, plus em-dash and proofreading post-hooks.
        """
        config = RefinementConfig(
            criteria=_WRITER_CRITERIA,
            max_iterations=3,
            quality_threshold=7.0,
            log_prefix="writer_refinement",
            extra_revision_instructions="Keep [VERIFY] flags on all claims.",
        )
        hooks = build_hook_chain(
            make_em_dash_hook(),
            make_proofread_hook(self._proofreader, "marketing content")
            if self._proofreader
            else None,
        )
        loop = RefinementLoop(
            config=config,
            generation_llm=self.llm,
            critique_llm=self._scanning_llm,
        )
        result = await loop.generate_and_refine(prompt, brand_voice, hooks)
        verify_flags = _extract_verify_flags(result.content)
        return result.content, verify_flags

    def _build_content_prompt(
        self,
        content_type: str,
        topic: str,
        brand_voice: str,
        extra_context: str = "",
    ) -> str:
        parts = [f"Write a {content_type} about: {topic}"]

        if brand_voice:
            parts.append(f"\nBRAND VOICE:\n{brand_voice}")

        if extra_context:
            parts.append(f"\nADDITIONAL CONTEXT:\n{extra_context}")

        parts.append("""
REQUIREMENTS:
- Follow the brand voice exactly
- Flag all specific claims with [VERIFY] prefix
- Include clear sections with headers
- Be engaging and actionable
- Include sources/references where applicable""")

        return "\n".join(parts)

    async def _gather_opportunities(self, opportunity_ids: Optional[List[str]]) -> str:
        if not opportunity_ids:
            return ""
        pieces = []
        for oid in opportunity_ids[:5]:
            opp = await self._opportunities.get(oid)
            if opp:
                pieces.append(f"- {opp.title}: {(opp.content or '')[:200]}")
        if pieces:
            return "Reference opportunities:\n" + "\n".join(pieces)
        return ""


def _extract_verify_flags(text: str) -> List[str]:
    """Extract all [VERIFY] flagged claims from content."""
    pattern = r"\[VERIFY\]\s*(.+?)(?:\n|$)"
    matches = re.findall(pattern, text)
    return [m.strip() for m in matches]
