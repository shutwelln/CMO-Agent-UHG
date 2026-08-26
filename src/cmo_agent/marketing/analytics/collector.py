"""Metrics collection and aggregation."""

from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

import structlog

from ...llm.base import BaseLLM, Message
from .models import AnalyticsReport, ChannelMetrics, MetricData, MetricType

logger = structlog.get_logger()


class MetricsCollector:
    """Collects and aggregates marketing metrics.

    In a production system, this would integrate with various
    marketing platforms (Google Ads, Meta, email providers, etc.)
    via n8n workflows or direct API calls.
    """

    def __init__(self, llm: BaseLLM | None = None) -> None:
        self.llm = llm
        # In-memory storage; replace with time-series DB in production
        self._metrics: list[MetricData] = []

    async def record_metric(
        self,
        metric_type: MetricType,
        value: float,
        channel: str | None = None,
        campaign_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MetricData:
        """Record a metric data point."""
        metric = MetricData(
            metric_type=metric_type,
            value=value,
            channel=channel,
            campaign_id=campaign_id,
            metadata=metadata or {},
        )
        self._metrics.append(metric)
        logger.debug(
            "metric_recorded",
            type=metric_type.value,
            value=value,
            channel=channel,
        )
        return metric

    async def get_metrics(
        self,
        campaign_id: str | None = None,
        channel: str | None = None,
        metric_type: MetricType | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[MetricData]:
        """Query metrics with optional filters."""
        results = self._metrics

        if campaign_id:
            results = [m for m in results if m.campaign_id == campaign_id]
        if channel:
            results = [m for m in results if m.channel == channel]
        if metric_type:
            results = [m for m in results if m.metric_type == metric_type]
        if start_date:
            results = [m for m in results if m.timestamp >= start_date]
        if end_date:
            results = [m for m in results if m.timestamp <= end_date]

        return results

    async def aggregate_by_channel(
        self,
        start_date: datetime,
        end_date: datetime,
    ) -> list[ChannelMetrics]:
        """Aggregate metrics by channel for a time period."""
        metrics = await self.get_metrics(start_date=start_date, end_date=end_date)

        # Group by channel
        channel_data: dict[str, dict[str, float]] = {}

        for metric in metrics:
            channel = metric.channel or "unknown"
            if channel not in channel_data:
                channel_data[channel] = {
                    "impressions": 0,
                    "clicks": 0,
                    "conversions": 0,
                    "spend": 0,
                    "revenue": 0,
                }

            type_key = metric.metric_type.value
            if type_key in channel_data[channel]:
                channel_data[channel][type_key] += metric.value

        # Convert to ChannelMetrics
        results = []
        for channel, data in channel_data.items():
            results.append(
                ChannelMetrics(
                    channel=channel,
                    period_start=start_date,
                    period_end=end_date,
                    impressions=int(data.get("impressions", 0)),
                    clicks=int(data.get("clicks", 0)),
                    conversions=int(data.get("conversions", 0)),
                    spend=data.get("spend", 0),
                    revenue=data.get("revenue", 0),
                )
            )

        return results

    async def generate_report(
        self,
        title: str,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        include_insights: bool = True,
    ) -> AnalyticsReport:
        """Generate a comprehensive analytics report."""
        if end_date is None:
            end_date = datetime.utcnow()
        if start_date is None:
            start_date = end_date - timedelta(days=30)

        logger.info(
            "generating_report",
            title=title,
            start=start_date,
            end=end_date,
        )

        # Get channel metrics
        channel_metrics = await self.aggregate_by_channel(start_date, end_date)

        # Calculate totals
        total_impressions = sum(cm.impressions for cm in channel_metrics)
        total_clicks = sum(cm.clicks for cm in channel_metrics)
        total_conversions = sum(cm.conversions for cm in channel_metrics)
        total_spend = sum(cm.spend for cm in channel_metrics)
        total_revenue = sum(cm.revenue for cm in channel_metrics)

        report = AnalyticsReport(
            id=str(uuid4()),
            title=title,
            period_start=start_date,
            period_end=end_date,
            total_impressions=total_impressions,
            total_clicks=total_clicks,
            total_conversions=total_conversions,
            total_spend=total_spend,
            total_revenue=total_revenue,
            channel_metrics=channel_metrics,
        )

        # Generate AI insights if LLM is available
        if include_insights and self.llm:
            insights, recommendations = await self._generate_insights(report)
            report.insights = insights
            report.recommendations = recommendations

        logger.info("report_generated", report_id=report.id)
        return report

    async def _generate_insights(
        self,
        report: AnalyticsReport,
    ) -> tuple[list[str], list[str]]:
        """Use LLM to generate insights and recommendations."""
        if not self.llm:
            return [], []

        prompt = f"""Analyze this marketing performance data and provide insights and recommendations.

Report Period: {report.period_start.date()} to {report.period_end.date()}

Overall Metrics:
- Impressions: {report.total_impressions:,}
- Clicks: {report.total_clicks:,}
- CTR: {report.overall_ctr:.2f}%
- Conversions: {report.total_conversions:,}
- Conversion Rate: {report.overall_conversion_rate:.2f}%
- Spend: ${report.total_spend:,.2f}
- Revenue: ${report.total_revenue:,.2f}
- ROAS: {report.overall_roas:.2f}x

Channel Performance:
{self._format_channel_metrics(report.channel_metrics)}

Please provide:
1. 3-5 key insights about the performance
2. 3-5 actionable recommendations

Format your response as:
INSIGHTS:
- [insight 1]
- [insight 2]
...

RECOMMENDATIONS:
- [recommendation 1]
- [recommendation 2]
..."""

        response = await self.llm.complete(
            messages=[Message(role="user", content=prompt)],
            temperature=0.5,
        )

        # Parse response
        insights = []
        recommendations = []
        current_section = None

        for line in response.content.split("\n"):
            line = line.strip()
            if line.upper().startswith("INSIGHTS"):
                current_section = "insights"
            elif line.upper().startswith("RECOMMENDATIONS"):
                current_section = "recommendations"
            elif line.startswith("-") and current_section:
                item = line[1:].strip()
                if current_section == "insights":
                    insights.append(item)
                else:
                    recommendations.append(item)

        return insights, recommendations

    def _format_channel_metrics(self, metrics: list[ChannelMetrics]) -> str:
        """Format channel metrics for the prompt."""
        if not metrics:
            return "No channel data available"

        lines = []
        for cm in metrics:
            lines.append(
                f"- {cm.channel}: {cm.impressions:,} impressions, "
                f"{cm.clicks:,} clicks ({cm.ctr:.2f}% CTR), "
                f"${cm.spend:,.2f} spend, ${cm.revenue:,.2f} revenue"
            )
        return "\n".join(lines)
