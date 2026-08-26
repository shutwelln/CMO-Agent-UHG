"""Application entry point and dependency initialization."""

import structlog
from typing import AsyncIterator
from contextlib import asynccontextmanager

from .config import get_settings, Settings
from .core.agent import CMOAgent
from .llm.anthropic import AnthropicLLM
from .llm.base import BaseLLM
from .n8n.client import N8NClient
from .marketing.campaigns.manager import CampaignManager
from .marketing.content.generator import ContentGenerator
from .marketing.analytics.collector import MetricsCollector


def configure_logging(settings: Settings) -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
            if settings.environment == "production"
            else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def create_llm(settings: Settings) -> BaseLLM:
    """Create an LLM instance based on configuration."""
    if settings.llm.provider == "anthropic":
        return AnthropicLLM(
            api_key=settings.anthropic_api_key,
            model=settings.llm.model,
            max_tokens=settings.llm.max_tokens,
            temperature=settings.llm.temperature,
        )
    else:
        raise ValueError(f"Unsupported LLM provider: {settings.llm.provider}")


def create_n8n_client(settings: Settings) -> N8NClient:
    """Create an n8n client instance."""
    return N8NClient(
        base_url=settings.n8n.base_url,
        api_key=settings.n8n.api_key,
        timeout=settings.n8n.timeout,
        max_retries=settings.n8n.max_retries,
    )


async def create_agent(settings: Settings | None = None) -> CMOAgent:
    """Create and configure the CMO Agent.

    Args:
        settings: Optional settings; if not provided, loaded from environment

    Returns:
        Configured CMOAgent instance
    """
    if settings is None:
        settings = get_settings()

    configure_logging(settings)

    llm = create_llm(settings)
    n8n_client = create_n8n_client(settings)

    agent = CMOAgent(
        llm=llm,
        n8n_client=n8n_client,
    )

    return agent


@asynccontextmanager
async def create_agent_context(
    settings: Settings | None = None,
) -> AsyncIterator[CMOAgent]:
    """Create an agent with proper resource management.

    Usage:
        async with create_agent_context() as agent:
            response = await agent.process_message("Hello", context)
    """
    agent = await create_agent(settings)

    async with agent.n8n:
        yield agent


class CMOAgentApp:
    """Main application class for the CMO Agent.

    Provides a high-level interface for initializing and running
    the agent with all its dependencies.
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()
        self._agent: CMOAgent | None = None
        self._llm: BaseLLM | None = None
        self._n8n: N8NClient | None = None
        self._campaign_manager: CampaignManager | None = None
        self._content_generator: ContentGenerator | None = None
        self._metrics_collector: MetricsCollector | None = None

    async def initialize(self) -> None:
        """Initialize all application components."""
        configure_logging(self.settings)

        self._llm = create_llm(self.settings)
        self._n8n = create_n8n_client(self.settings)
        self._campaign_manager = CampaignManager()
        self._content_generator = ContentGenerator(self._llm)
        self._metrics_collector = MetricsCollector(self._llm)

        self._agent = CMOAgent(
            llm=self._llm,
            n8n_client=self._n8n,
        )

    async def start(self) -> None:
        """Start the application (open connections, etc.)."""
        if self._n8n:
            await self._n8n._ensure_client()

    async def stop(self) -> None:
        """Stop the application (close connections, cleanup)."""
        if self._n8n:
            await self._n8n.close()

    @property
    def agent(self) -> CMOAgent:
        """Get the CMO Agent instance."""
        if self._agent is None:
            raise RuntimeError("Application not initialized. Call initialize() first.")
        return self._agent

    @property
    def campaign_manager(self) -> CampaignManager:
        """Get the campaign manager."""
        if self._campaign_manager is None:
            raise RuntimeError("Application not initialized.")
        return self._campaign_manager

    @property
    def content_generator(self) -> ContentGenerator:
        """Get the content generator."""
        if self._content_generator is None:
            raise RuntimeError("Application not initialized.")
        return self._content_generator

    @property
    def metrics_collector(self) -> MetricsCollector:
        """Get the metrics collector."""
        if self._metrics_collector is None:
            raise RuntimeError("Application not initialized.")
        return self._metrics_collector

    async def __aenter__(self) -> "CMOAgentApp":
        """Enter async context."""
        await self.initialize()
        await self.start()
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context."""
        await self.stop()
