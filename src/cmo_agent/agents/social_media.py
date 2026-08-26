"""Social Media Manager Agent - strategy, content calendars, and engagement planning."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import structlog

from ..db.database import Database
from ..db.repositories import ConfigRepo, DraftRepo, OpportunityRepo
from ..llm.base import BaseLLM, Message
from ..quality import QualityCriterion, RefinementConfig, RefinementLoop
from ..quality.hooks import build_hook_chain, make_em_dash_hook
from ..workspace.manager import WorkspaceManager
from .base import BaseAgent

logger = structlog.get_logger()

# Quality criteria for social media content
_SOCIAL_MEDIA_CRITERIA = [
    QualityCriterion(
        name="platform_fit",
        description="Content tailored to the target platform's format, norms, and audience expectations",
    ),
    QualityCriterion(
        name="engagement_potential",
        description="Likely to drive likes, comments, shares, saves, or clicks",
    ),
    QualityCriterion(
        name="brand_voice",
        description="Consistent with the brand's tone, personality, and messaging guidelines",
    ),
    QualityCriterion(
        name="visual_hook", description="Strong visual or opening hook that stops the scroll"
    ),
    QualityCriterion(
        name="hashtag_relevance",
        description="Hashtags are relevant, appropriately mixed (broad + niche), and not banned/restricted",
    ),
]


class SocialMediaManagerAgent(BaseAgent):
    """Handles social media strategy, content calendars, and engagement planning."""

    agent_id = "social_media_agent"
    agent_name = "Social Media Manager Agent"

    def __init__(
        self,
        llm: BaseLLM,
        db: Database,
        workspace_manager: WorkspaceManager,
        scanning_llm: Optional[BaseLLM] = None,
        max_iterations: int = 10,
    ) -> None:
        self._drafts = DraftRepo(db)
        self._opportunities = OpportunityRepo(db)
        self._config = ConfigRepo(db)
        self._workspace_mgr = workspace_manager
        self._scanning_llm = scanning_llm
        super().__init__(llm=llm, db=db, max_iterations=max_iterations)

    def get_system_prompt(self, workspace_id: Optional[str] = None) -> str:
        return """You are the Social Media Manager Agent, a specialist in social media strategy and community growth.

Your expertise covers:
- Content calendar creation and editorial planning
- Platform-specific strategy (Instagram, TikTok, LinkedIn, Twitter/X, Facebook, YouTube)
- Hashtag research and optimization
- Engagement strategies and community management
- Posting schedule optimization based on audience behavior
- Audience growth tactics and follower acquisition
- Content pillars and thematic planning
- Social media analytics interpretation

IMPORTANT RULES:
- All specific platform claims MUST be flagged with [VERIFY] prefix
- Strategic plans are saved as drafts for human review
- The Writer Agent handles actual content creation — you handle strategy and planning
- Tailor recommendations to the brand's voice and target audience
- Consider platform algorithm changes and best practices
- ANTI-AI WRITING (MANDATORY): NEVER use em dashes (—) or en dashes (–). NEVER bold words mid-sentence. Use commas, periods, semicolons, or " - " instead. Bolding is only for headers or standalone labels."""

    def register_tools(self) -> None:
        @self.tool_registry.register(
            name="create_content_calendar",
            description="Create a content calendar with themes, post types, and scheduling for specified platforms.",
        )
        async def create_content_calendar(
            workspace_id: str,
            period: str,
            platforms: List[str],
            themes: List[str],
            posts_per_week: int = 5,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Create a detailed content calendar.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

PERIOD: {period}
PLATFORMS: {", ".join(platforms)}
THEMES/PILLARS: {", ".join(themes)}
POSTING FREQUENCY: {posts_per_week} posts per week

Structure the calendar as:
1. **Content Pillars Overview** — How themes map to brand goals
2. **Weekly Schedule** — Day-by-day plan with:
   - Platform
   - Content type (carousel, reel, story, text post, video, etc.)
   - Theme/pillar
   - Topic/hook
   - Best posting time
   - CTA (call to action)
3. **Content Mix Ratio** — % breakdown by type (educational, entertaining, promotional, community)
4. **Hashtag Strategy** — Platform-specific hashtag sets per theme
5. **Repurposing Plan** — How to adapt content across platforms
6. **Key Dates & Events** — Relevant dates to plan around during this period

Flag any platform-specific algorithm claims with [VERIFY]."""

            config = RefinementConfig(
                criteria=_SOCIAL_MEDIA_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="social_media_calendar",
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)
            body = result.content

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="content_calendar",
                title=f"Content Calendar: {period}",
                body=body,
            )

            return {
                "draft_id": draft.id,
                "title": f"Content Calendar: {period}",
                "body_preview": body[:500],
                "platforms": platforms,
                "posts_per_week": posts_per_week,
                "status": "pending",
            }

        @self.tool_registry.register(
            name="create_platform_strategy",
            description="Create a comprehensive strategy for a specific social media platform.",
        )
        async def create_platform_strategy(
            workspace_id: str,
            platform: str,
            goals: str,
            current_followers: int = 0,
            timeframe: str = "3 months",
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            followers_context = ""
            if current_followers > 0:
                followers_context = f"\nCURRENT FOLLOWERS: {current_followers:,}"

            prompt = f"""Create a comprehensive social media strategy for {platform}.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

PLATFORM: {platform}
GOALS: {goals}{followers_context}
TIMEFRAME: {timeframe}

Structure the strategy as:
1. **Platform Overview** — Why {platform} fits this brand and audience
2. **Account Optimization** — Profile, bio, link, highlight setup
3. **Content Strategy** — Content types, formats, and mix that work best on {platform}
4. **Growth Strategy** — Organic tactics to build followers and reach
5. **Engagement Playbook** — How to interact with audience (response templates, DM strategy, comment strategy)
6. **Posting Schedule** — Optimal days and times based on audience behavior
7. **Hashtag/Discovery Strategy** — Platform-specific discovery tactics
8. **Collaboration & Partnerships** — Influencer and cross-promotion opportunities
9. **KPIs & Milestones** — Monthly targets for the timeframe
10. **Tools & Resources Needed** — What's required to execute

Flag any platform-specific best practice claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="social_strategy",
                title=f"{platform} Strategy: {goals[:60]}",
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"{platform} Strategy: {goals[:60]}",
                "body_preview": response.content[:500],
                "platform": platform,
                "status": "pending",
            }

        @self.tool_registry.register(
            name="research_hashtags",
            description="Research and recommend hashtags for a topic on a specific platform.",
        )
        async def research_hashtags(
            workspace_id: str,
            topic: str,
            platform: str = "instagram",
            count: int = 30,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            prompt = f"""Research and recommend hashtags for the following topic.

BRAND CONTEXT:
{brand_voice[:300] if brand_voice else "No brand voice configured."}

TOPIC: {topic}
PLATFORM: {platform}
REQUESTED COUNT: {count}

Provide hashtags organized as:
1. **High Volume (broad reach)** — Popular hashtags with large audiences
2. **Medium Volume (targeted)** — Niche-relevant hashtags with moderate competition
3. **Low Volume (highly specific)** — Long-tail hashtags for precise targeting
4. **Branded** — Brand-specific or campaign-specific hashtags to create/use
5. **Banned/Avoid** — Any known restricted hashtags to steer clear of

For each category, provide the hashtags and a brief note on why they're recommended.
Flag any specific volume or reach claims with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.6,
            )

            return {
                "hashtags": response.content,
                "topic": topic,
                "platform": platform,
            }

        @self.tool_registry.register(
            name="create_engagement_strategy",
            description="Create an engagement and community management strategy for a platform.",
        )
        async def create_engagement_strategy(
            workspace_id: str,
            platform: str,
            focus: str,
            current_engagement_rate: float = 0.0,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            engagement_context = ""
            if current_engagement_rate > 0:
                engagement_context = f"\nCURRENT ENGAGEMENT RATE: {current_engagement_rate}%"

            prompt = f"""Create a detailed engagement and community management strategy.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

PLATFORM: {platform}
FOCUS AREA: {focus}{engagement_context}

Structure the strategy as:
1. **Engagement Audit** — What good engagement looks like for this brand/platform
2. **Response Framework** — How/when to respond to comments, DMs, mentions
3. **Proactive Engagement** — Outreach tactics (commenting on related accounts, joining conversations)
4. **Community Building** — How to foster a sense of community
5. **UGC (User-Generated Content) Strategy** — How to encourage and leverage UGC
6. **Engagement Hooks** — Types of posts that drive interaction (polls, questions, challenges)
7. **Crisis Response Plan** — How to handle negative comments or PR issues
8. **Metrics & Tracking** — What to measure and target benchmarks

Flag any engagement rate benchmarks with [VERIFY]."""

            response = await self.llm.complete(
                messages=[Message(role="user", content=prompt)],
                temperature=0.7,
            )

            draft = await self._drafts.create(
                workspace_id=workspace_id,
                content_type="engagement_strategy",
                title=f"Engagement Strategy: {platform} - {focus[:50]}",
                body=response.content,
            )

            return {
                "draft_id": draft.id,
                "title": f"Engagement Strategy: {platform} - {focus[:50]}",
                "body_preview": response.content[:500],
                "platform": platform,
                "status": "pending",
            }

        @self.tool_registry.register(
            name="suggest_content_ideas",
            description="Suggest content ideas based on recent opportunities, trends, and content pillars.",
        )
        async def suggest_content_ideas(
            workspace_id: str,
            count: int = 10,
            platforms: Optional[List[str]] = None,
            content_pillars: Optional[List[str]] = None,
        ) -> Dict[str, Any]:
            brand_voice = await self._workspace_mgr.get_brand_voice(workspace_id)

            # Pull recent opportunities for inspiration
            opps = await self._opportunities.list_by_workspace(workspace_id, limit=10)
            opp_context = ""
            if opps:
                opp_lines = [f"- {o.title}: {(o.content or '')[:150]}" for o in opps[:10]]
                opp_context = "\n\nRECENT OPPORTUNITIES/TRENDS:\n" + "\n".join(opp_lines)

            platforms_str = ", ".join(platforms) if platforms else "all platforms"
            pillars_str = ", ".join(content_pillars) if content_pillars else "general"

            prompt = f"""Suggest {count} content ideas for social media.

BRAND CONTEXT:
{brand_voice[:500] if brand_voice else "No brand voice configured."}

TARGET PLATFORMS: {platforms_str}
CONTENT PILLARS: {pillars_str}{opp_context}

For each idea, provide:
1. **Title/Hook** — The attention-grabbing angle
2. **Platform** — Best platform for this content
3. **Format** — Post type (carousel, reel, story, thread, etc.)
4. **Content Pillar** — Which pillar it falls under
5. **Brief Description** — 1-2 sentences on the content
6. **Why Now** — Why this is timely or relevant

Prioritize ideas that leverage the recent opportunities/trends listed above."""

            config = RefinementConfig(
                criteria=_SOCIAL_MEDIA_CRITERIA,
                max_iterations=2,
                quality_threshold=7.0,
                log_prefix="social_media_ideas",
                generation_temperature=0.8,
            )
            hooks = build_hook_chain(make_em_dash_hook())
            loop = RefinementLoop(
                config=config,
                generation_llm=self.llm,
                critique_llm=self._scanning_llm,
            )
            result = await loop.generate_and_refine(prompt, brand_voice or "", hooks)

            return {
                "ideas": result.content,
                "count": count,
                "platforms": platforms or ["all"],
                "based_on_opportunities": len(opps),
            }
