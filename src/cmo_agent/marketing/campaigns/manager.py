"""Campaign management service."""

from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from .models import Campaign, CampaignChannel, CampaignStatus

logger = structlog.get_logger()


class CampaignManager:
    """Service for managing marketing campaigns.

    Provides CRUD operations and lifecycle management for campaigns.
    In a production system, this would integrate with a database.
    """

    def __init__(self) -> None:
        # In-memory storage for now; replace with database in production
        self._campaigns: dict[str, Campaign] = {}

    async def create(
        self,
        name: str,
        channels: list[str],
        target_audience: str = "",
        goals: str = "",
        description: str = "",
    ) -> Campaign:
        """Create a new campaign."""
        campaign_id = str(uuid4())

        # Convert channel strings to enum
        channel_enums = []
        for ch in channels:
            try:
                channel_enums.append(CampaignChannel(ch))
            except ValueError:
                logger.warning("invalid_channel", channel=ch)

        campaign = Campaign(
            id=campaign_id,
            name=name,
            description=description,
            channels=channel_enums,
            target_audience=target_audience,
            goals=goals,
        )

        self._campaigns[campaign_id] = campaign
        logger.info("campaign_created", campaign_id=campaign_id, name=name)

        return campaign

    async def get(self, campaign_id: str) -> Campaign | None:
        """Get a campaign by ID."""
        return self._campaigns.get(campaign_id)

    async def update(
        self,
        campaign_id: str,
        **updates: Any,
    ) -> Campaign | None:
        """Update a campaign."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None

        for key, value in updates.items():
            if hasattr(campaign, key):
                setattr(campaign, key, value)

        campaign.updated_at = datetime.utcnow()
        logger.info("campaign_updated", campaign_id=campaign_id)

        return campaign

    async def delete(self, campaign_id: str) -> bool:
        """Delete a campaign."""
        if campaign_id in self._campaigns:
            del self._campaigns[campaign_id]
            logger.info("campaign_deleted", campaign_id=campaign_id)
            return True
        return False

    async def list(
        self,
        status: CampaignStatus | None = None,
        channel: CampaignChannel | None = None,
    ) -> list[Campaign]:
        """List campaigns with optional filtering."""
        campaigns = list(self._campaigns.values())

        if status:
            campaigns = [c for c in campaigns if c.status == status]

        if channel:
            campaigns = [c for c in campaigns if channel in c.channels]

        return campaigns

    async def activate(self, campaign_id: str) -> Campaign | None:
        """Activate a campaign."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None

        campaign.status = CampaignStatus.ACTIVE
        campaign.updated_at = datetime.utcnow()
        logger.info("campaign_activated", campaign_id=campaign_id)

        return campaign

    async def pause(self, campaign_id: str) -> Campaign | None:
        """Pause a campaign."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None

        campaign.status = CampaignStatus.PAUSED
        campaign.updated_at = datetime.utcnow()
        logger.info("campaign_paused", campaign_id=campaign_id)

        return campaign

    async def complete(self, campaign_id: str) -> Campaign | None:
        """Mark a campaign as completed."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None

        campaign.status = CampaignStatus.COMPLETED
        campaign.updated_at = datetime.utcnow()
        logger.info("campaign_completed", campaign_id=campaign_id)

        return campaign

    async def add_workflow(
        self,
        campaign_id: str,
        workflow_id: str,
    ) -> Campaign | None:
        """Associate an n8n workflow with a campaign."""
        campaign = self._campaigns.get(campaign_id)
        if not campaign:
            return None

        if workflow_id not in campaign.workflow_ids:
            campaign.workflow_ids.append(workflow_id)
            campaign.updated_at = datetime.utcnow()
            logger.info(
                "workflow_added_to_campaign",
                campaign_id=campaign_id,
                workflow_id=workflow_id,
            )

        return campaign
