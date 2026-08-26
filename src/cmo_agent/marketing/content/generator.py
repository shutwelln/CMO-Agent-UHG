"""AI-powered content generation."""

from uuid import uuid4

import structlog

from ...llm.base import BaseLLM, Message
from .models import ContentRequest, ContentType, ContentTone, GeneratedContent

logger = structlog.get_logger()


class ContentGenerator:
    """AI-powered marketing content generator.

    Uses LLMs to generate various types of marketing content
    including emails, social posts, ad copy, and more.
    """

    def __init__(self, llm: BaseLLM) -> None:
        self.llm = llm

    def _build_prompt(self, request: ContentRequest) -> str:
        """Build the generation prompt based on content type and parameters."""
        type_guidelines = {
            ContentType.EMAIL: """
- Write a compelling subject line
- Keep the email concise and scannable
- Include a clear call-to-action
- Use personalization placeholders like {{first_name}} where appropriate""",
            ContentType.SOCIAL_POST: """
- Keep it concise (under 280 characters for Twitter)
- Use engaging hooks
- Include relevant hashtags
- Make it shareable""",
            ContentType.BLOG_POST: """
- Write an SEO-friendly title
- Include an engaging introduction
- Use subheadings for structure
- Provide actionable insights""",
            ContentType.AD_COPY: """
- Lead with the benefit
- Create urgency
- Keep it punchy and direct
- Include a strong call-to-action""",
            ContentType.NEWSLETTER: """
- Write an engaging subject line
- Include a mix of content sections
- Use clear formatting
- End with a clear next step""",
        }

        tone_descriptions = {
            ContentTone.PROFESSIONAL: "professional and authoritative",
            ContentTone.CASUAL: "casual and conversational",
            ContentTone.FORMAL: "formal and polished",
            ContentTone.FRIENDLY: "warm and approachable",
            ContentTone.URGENT: "urgent and compelling",
            ContentTone.INSPIRATIONAL: "inspiring and motivational",
            ContentTone.HUMOROUS: "light-hearted and witty",
            ContentTone.EDUCATIONAL: "informative and educational",
        }

        prompt = f"""Generate {request.content_type.value} content about: {request.topic}

Tone: {tone_descriptions.get(request.tone, "professional")}
{f"Target Audience: {request.target_audience}" if request.target_audience else ""}
{f"Channel: {request.channel}" if request.channel else ""}
{f"Keywords to include: {', '.join(request.keywords)}" if request.keywords else ""}

Guidelines for {request.content_type.value}:
{type_guidelines.get(request.content_type, "")}

{f"Additional instructions: {request.additional_instructions}" if request.additional_instructions else ""}

Please provide the content in this exact format:
HEADLINE: [Your headline here]
SUBHEADLINE: [Optional subheadline]
BODY: [Main content body]
CTA: [Call to action]"""

        if request.max_length:
            prompt += f"\n\nKeep the total content under {request.max_length} characters."

        return prompt

    async def generate(
        self,
        content_type: str,
        topic: str,
        tone: str = "professional",
        channel: str | None = None,
        target_audience: str = "",
        keywords: list[str] | None = None,
        include_variations: bool = False,
    ) -> GeneratedContent:
        """Generate marketing content.

        Args:
            content_type: Type of content (email, social_post, ad_copy, etc.)
            topic: Topic or subject matter
            tone: Desired tone (professional, casual, etc.)
            channel: Target channel/platform
            target_audience: Description of target audience
            keywords: Keywords to include
            include_variations: Whether to generate A/B variations

        Returns:
            GeneratedContent with headline, body, and CTA
        """
        # Parse enums
        try:
            ct = ContentType(content_type)
        except ValueError:
            ct = ContentType.SOCIAL_POST

        try:
            t = ContentTone(tone)
        except ValueError:
            t = ContentTone.PROFESSIONAL

        request = ContentRequest(
            content_type=ct,
            topic=topic,
            tone=t,
            channel=channel,
            target_audience=target_audience,
            keywords=keywords or [],
            include_variations=include_variations,
        )

        prompt = self._build_prompt(request)

        logger.info(
            "generating_content",
            content_type=content_type,
            topic=topic,
            tone=tone,
        )

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.8,
        )

        # Parse the response
        content = self._parse_response(response.content, request)
        content.prompt_used = prompt

        logger.info("content_generated", content_id=content.id)

        return content

    def _parse_response(
        self,
        response_text: str,
        request: ContentRequest,
    ) -> GeneratedContent:
        """Parse LLM response into structured content."""
        content = GeneratedContent(
            id=str(uuid4()),
            content_type=request.content_type,
            topic=request.topic,
            tone=request.tone,
            channel=request.channel,
            target_audience=request.target_audience,
            keywords=request.keywords,
        )

        # Parse the formatted response
        lines = response_text.strip().split("\n")
        current_section = None
        current_text: list[str] = []

        for line in lines:
            line_upper = line.upper().strip()

            if line_upper.startswith("HEADLINE:"):
                if current_section and current_text:
                    self._set_section(content, current_section, current_text)
                current_section = "headline"
                current_text = [line.split(":", 1)[1].strip() if ":" in line else ""]
            elif line_upper.startswith("SUBHEADLINE:"):
                if current_section and current_text:
                    self._set_section(content, current_section, current_text)
                current_section = "subheadline"
                current_text = [line.split(":", 1)[1].strip() if ":" in line else ""]
            elif line_upper.startswith("BODY:"):
                if current_section and current_text:
                    self._set_section(content, current_section, current_text)
                current_section = "body"
                current_text = [line.split(":", 1)[1].strip() if ":" in line else ""]
            elif line_upper.startswith("CTA:"):
                if current_section and current_text:
                    self._set_section(content, current_section, current_text)
                current_section = "cta"
                current_text = [line.split(":", 1)[1].strip() if ":" in line else ""]
            else:
                current_text.append(line)

        # Set the last section
        if current_section and current_text:
            self._set_section(content, current_section, current_text)

        # If parsing failed, use the whole response as body
        if not content.body and not content.headline:
            content.body = response_text

        return content

    def _set_section(
        self,
        content: GeneratedContent,
        section: str,
        text_lines: list[str],
    ) -> None:
        """Set a content section from parsed lines."""
        text = "\n".join(text_lines).strip()
        if section == "headline":
            content.headline = text
        elif section == "subheadline":
            content.subheadline = text
        elif section == "body":
            content.body = text
        elif section == "cta":
            content.call_to_action = text

    async def generate_variations(
        self,
        content: GeneratedContent,
        count: int = 3,
    ) -> GeneratedContent:
        """Generate A/B test variations of existing content."""
        prompt = f"""Create {count} variations of this marketing content for A/B testing.
Keep the same general message but vary the approach, tone, or wording.

Original:
Headline: {content.headline}
Body: {content.body}
CTA: {content.call_to_action}

Provide variations in this format:
VARIATION 1:
Headline: ...
Body: ...
CTA: ...

VARIATION 2:
...
"""

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.9,
        )

        # Parse variations (simplified)
        content.variations = [{"raw": response.content}]

        return content
