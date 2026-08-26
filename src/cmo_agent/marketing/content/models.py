"""Content data models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    """Types of marketing content."""

    EMAIL = "email"
    SOCIAL_POST = "social_post"
    BLOG_POST = "blog_post"
    AD_COPY = "ad_copy"
    LANDING_PAGE = "landing_page"
    NEWSLETTER = "newsletter"
    PRESS_RELEASE = "press_release"
    VIDEO_SCRIPT = "video_script"


class ContentTone(str, Enum):
    """Content tone options."""

    PROFESSIONAL = "professional"
    CASUAL = "casual"
    FORMAL = "formal"
    FRIENDLY = "friendly"
    URGENT = "urgent"
    INSPIRATIONAL = "inspirational"
    HUMOROUS = "humorous"
    EDUCATIONAL = "educational"


class GeneratedContent(BaseModel):
    """AI-generated marketing content."""

    id: str | None = None
    content_type: ContentType
    topic: str
    tone: ContentTone = ContentTone.PROFESSIONAL

    # Generated parts
    headline: str = ""
    subheadline: str = ""
    body: str = ""
    call_to_action: str = ""

    # Variations for A/B testing
    variations: list[dict[str, str]] = Field(default_factory=list)

    # Metadata
    channel: str | None = None
    target_audience: str = ""
    keywords: list[str] = Field(default_factory=list)

    # Generation info
    model_used: str = ""
    prompt_used: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)

    def to_formatted_text(self) -> str:
        """Return content as formatted text."""
        parts = []
        if self.headline:
            parts.append(f"# {self.headline}")
        if self.subheadline:
            parts.append(f"## {self.subheadline}")
        if self.body:
            parts.append(self.body)
        if self.call_to_action:
            parts.append(f"\n**{self.call_to_action}**")
        return "\n\n".join(parts)


class ContentRequest(BaseModel):
    """Request for content generation."""

    content_type: ContentType
    topic: str
    tone: ContentTone = ContentTone.PROFESSIONAL
    channel: str | None = None
    target_audience: str = ""
    keywords: list[str] = Field(default_factory=list)
    max_length: int | None = None
    include_variations: bool = False
    variation_count: int = 3
    additional_instructions: str = ""
