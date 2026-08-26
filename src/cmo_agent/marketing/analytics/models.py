"""Analytics data models."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MetricType(str, Enum):
    """Types of marketing metrics."""

    IMPRESSIONS = "impressions"
    CLICKS = "clicks"
    CONVERSIONS = "conversions"
    REVENUE = "revenue"
    SPEND = "spend"
    OPEN_RATE = "open_rate"
    CLICK_RATE = "click_rate"
    BOUNCE_RATE = "bounce_rate"
    ENGAGEMENT_RATE = "engagement_rate"
    FOLLOWERS = "followers"
    SHARES = "shares"
    COMMENTS = "comments"


class MetricData(BaseModel):
    """A single metric data point."""

    metric_type: MetricType
    value: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    channel: str | None = None
    campaign_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChannelMetrics(BaseModel):
    """Aggregated metrics for a channel."""

    channel: str
    period_start: datetime
    period_end: datetime

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
    def cpa(self) -> float:
        """Cost per acquisition."""
        return (self.spend / self.conversions) if self.conversions > 0 else 0.0

    @property
    def roas(self) -> float:
        """Return on ad spend."""
        return (self.revenue / self.spend) if self.spend > 0 else 0.0


class AnalyticsReport(BaseModel):
    """Marketing analytics report."""

    id: str | None = None
    title: str
    period_start: datetime
    period_end: datetime

    # Overall metrics
    total_impressions: int = 0
    total_clicks: int = 0
    total_conversions: int = 0
    total_spend: float = 0.0
    total_revenue: float = 0.0

    # Channel breakdown
    channel_metrics: list[ChannelMetrics] = Field(default_factory=list)

    # Top performers
    top_campaigns: list[dict[str, Any]] = Field(default_factory=list)
    top_content: list[dict[str, Any]] = Field(default_factory=list)

    # AI-generated insights
    insights: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    # Metadata
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    generated_by: str = "cmo_agent"

    @property
    def overall_ctr(self) -> float:
        """Overall click-through rate."""
        return (
            (self.total_clicks / self.total_impressions * 100)
            if self.total_impressions > 0
            else 0.0
        )

    @property
    def overall_conversion_rate(self) -> float:
        """Overall conversion rate."""
        return (self.total_conversions / self.total_clicks * 100) if self.total_clicks > 0 else 0.0

    @property
    def overall_roas(self) -> float:
        """Overall return on ad spend."""
        return (self.total_revenue / self.total_spend) if self.total_spend > 0 else 0.0

    def summary(self) -> str:
        """Generate a text summary of the report."""
        return f"""Marketing Report: {self.title}
Period: {self.period_start.date()} to {self.period_end.date()}

Key Metrics:
- Impressions: {self.total_impressions:,}
- Clicks: {self.total_clicks:,} (CTR: {self.overall_ctr:.2f}%)
- Conversions: {self.total_conversions:,} (CVR: {self.overall_conversion_rate:.2f}%)
- Spend: ${self.total_spend:,.2f}
- Revenue: ${self.total_revenue:,.2f}
- ROAS: {self.overall_roas:.2f}x

Top Insights:
{chr(10).join(f"- {i}" for i in self.insights[:3])}

Recommendations:
{chr(10).join(f"- {r}" for r in self.recommendations[:3])}
"""
