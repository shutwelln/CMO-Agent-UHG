"""Abstract base class for marketing channels."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class ChannelPublishResult(BaseModel):
    """Result of publishing content to a channel."""

    success: bool
    channel: str
    content_id: str | None = None
    external_id: str | None = None
    published_at: datetime | None = None
    url: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = {}


class MarketingChannel(ABC):
    """Abstract base class for marketing channel integrations.

    Each channel adapter handles the specifics of publishing
    content and retrieving metrics for that platform.
    """

    @property
    @abstractmethod
    def channel_name(self) -> str:
        """Unique identifier for this channel."""
        pass

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable channel name."""
        pass

    @abstractmethod
    async def publish(
        self,
        content: dict[str, Any],
        **kwargs: Any,
    ) -> ChannelPublishResult:
        """Publish content to the channel.

        Args:
            content: Content to publish (headline, body, media, etc.)
            **kwargs: Channel-specific options

        Returns:
            ChannelPublishResult with success status and details
        """
        pass

    @abstractmethod
    async def schedule(
        self,
        content: dict[str, Any],
        publish_at: datetime,
        **kwargs: Any,
    ) -> ChannelPublishResult:
        """Schedule content for future publication.

        Args:
            content: Content to publish
            publish_at: When to publish
            **kwargs: Channel-specific options

        Returns:
            ChannelPublishResult with scheduling details
        """
        pass

    @abstractmethod
    async def get_metrics(
        self,
        content_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Retrieve performance metrics for published content.

        Args:
            content_id: ID of the published content
            **kwargs: Channel-specific options

        Returns:
            Dictionary of metrics (impressions, clicks, etc.)
        """
        pass

    async def validate_content(
        self,
        content: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate content for this channel.

        Args:
            content: Content to validate

        Returns:
            Tuple of (is_valid, list of error messages)
        """
        errors: list[str] = []

        if not content.get("body"):
            errors.append("Content body is required")

        return len(errors) == 0, errors

    async def health_check(self) -> bool:
        """Check if the channel integration is healthy."""
        return True


class N8NChannelAdapter(MarketingChannel):
    """Base adapter that executes n8n workflows for channel operations.

    This adapter delegates to n8n workflows for actual publishing,
    making it easy to integrate with any platform n8n supports.
    """

    def __init__(
        self,
        n8n_client: Any,
        publish_workflow_id: str | None = None,
        metrics_workflow_id: str | None = None,
    ):
        self.n8n = n8n_client
        self.publish_workflow_id = publish_workflow_id
        self.metrics_workflow_id = metrics_workflow_id

    @property
    def channel_name(self) -> str:
        return "n8n_generic"

    @property
    def display_name(self) -> str:
        return "n8n Workflow"

    async def publish(
        self,
        content: dict[str, Any],
        **kwargs: Any,
    ) -> ChannelPublishResult:
        """Publish by executing an n8n workflow."""
        if not self.publish_workflow_id:
            return ChannelPublishResult(
                success=False,
                channel=self.channel_name,
                error="No publish workflow configured",
            )

        try:
            execution = await self.n8n.execute_workflow(
                self.publish_workflow_id,
                {"content": content, **kwargs},
            )

            return ChannelPublishResult(
                success=True,
                channel=self.channel_name,
                external_id=execution.id,
                published_at=datetime.utcnow(),
                metadata={"execution_id": execution.id},
            )
        except Exception as e:
            return ChannelPublishResult(
                success=False,
                channel=self.channel_name,
                error=str(e),
            )

    async def schedule(
        self,
        content: dict[str, Any],
        publish_at: datetime,
        **kwargs: Any,
    ) -> ChannelPublishResult:
        """Schedule by triggering a scheduled n8n workflow."""
        # n8n handles scheduling internally via workflow triggers
        return await self.publish(
            content,
            scheduled_for=publish_at.isoformat(),
            **kwargs,
        )

    async def get_metrics(
        self,
        content_id: str,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Get metrics by executing an n8n workflow."""
        if not self.metrics_workflow_id:
            return {"error": "No metrics workflow configured"}

        try:
            execution = await self.n8n.execute_workflow(
                self.metrics_workflow_id,
                {"content_id": content_id, **kwargs},
            )
            return {"execution_id": execution.id, "status": execution.status.value}
        except Exception as e:
            return {"error": str(e)}
