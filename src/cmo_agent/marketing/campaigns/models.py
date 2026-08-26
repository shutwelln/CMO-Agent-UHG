"""Campaign data models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CampaignStatus(str, Enum):
    """Campaign lifecycle status."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CampaignChannel(str, Enum):
    """Marketing channels."""

    EMAIL = "email"
    SOCIAL_TWITTER = "social_twitter"
    SOCIAL_LINKEDIN = "social_linkedin"
    SOCIAL_FACEBOOK = "social_facebook"
    SOCIAL_INSTAGRAM = "social_instagram"
    PAID_GOOGLE = "paid_google"
    PAID_META = "paid_meta"
    SMS = "sms"
    PUSH = "push"


class CampaignContent(BaseModel):
    """Content for a specific channel."""

    channel: CampaignChannel
    headline: str
    body: str
    call_to_action: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class CampaignMetrics(BaseModel):
    """Campaign performance metrics."""

    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    spend: float = 0.0
    revenue: float = 0.0

    @property
    def ctr(self) -> float:
        """Click-through rate."""
        return (self.clicks / self.impressions * 100) if self.impressions > 0 else 0.0

    @property
    def conversion_rate(self) -> float:
        """Conversion rate."""
        return (self.conversions / self.clicks * 100) if self.clicks > 0 else 0.0

    @property
    def roas(self) -> float:
        """Return on ad spend."""
        return (self.revenue / self.spend) if self.spend > 0 else 0.0


class Campaign(BaseModel):
    """Marketing campaign definition."""

    id: str | None = None
    name: str
    description: str = ""
    status: CampaignStatus = CampaignStatus.DRAFT

    # Targeting
    target_audience: str = ""
    goals: str = ""

    # Channels and content
    channels: list[CampaignChannel] = Field(default_factory=list)
    content: list[CampaignContent] = Field(default_factory=list)

    # Scheduling
    start_date: datetime | None = None
    end_date: datetime | None = None

    # n8n integration
    workflow_ids: list[str] = Field(default_factory=list)

    # Metrics
    metrics: CampaignMetrics = Field(default_factory=CampaignMetrics)

    # Metadata
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def add_content(self, content: CampaignContent) -> None:
        """Add content for a channel."""
        # Remove existing content for this channel
        self.content = [c for c in self.content if c.channel != content.channel]
        self.content.append(content)

    def get_content(self, channel: CampaignChannel) -> CampaignContent | None:
        """Get content for a specific channel."""
        for content in self.content:
            if content.channel == channel:
                return content
        return None

    def is_active(self) -> bool:
        """Check if campaign is currently active."""
        if self.status != CampaignStatus.ACTIVE:
            return False
        now = datetime.utcnow()
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True
