"""Agent factory - constructs and wires all agents."""

from __future__ import annotations

from pathlib import Path

import structlog

from ..config import Settings
from ..db.database import Database
from ..llm.anthropic import AnthropicLLM
from ..media.storage import MediaStorage
from ..n8n.client import N8NClient
from ..n8n.service import N8NService
from ..text.overlay import TextOverlay
from ..text.proofreader import Proofreader
from ..workspace.manager import WorkspaceManager
from .acquisition import AcquisitionAgent
from .compliance import MarketingComplianceAgent
from .composition_planner import CompositionPlannerAgent
from .conversion_optimization import ConversionOptimizationAgent
from .deck import DeckAgent
from .docs import DocsAgent
from .editorial import EditorialLeadAgent
from .experiment_engineer import ExperimentEngineerAgent
from .google_alerts import GoogleAlertsIngestAgent
from .growth_ideas import GrowthIdeasAgent
from .gtm import GTMAgent
from .knowledge_base import KnowledgeBaseAgent
from .legal_strategy import LegalStrategyAgent
from .lifecycle_marketing import LifecycleMarketingAgent
from .linkedin_partnerships import LinkedInPartnershipsAgent
from .marketing_analytics import MarketingAnalyticsAgent
from .motion_graphics import MotionGraphicsAgent
from .orchestrator import CMOOrchestratorAgent
from .performance_marketer import PerformanceMarketerAgent
from .reddit_ingest import RedditIngestAgent
from .registry import AgentRegistry
from .research import ResearchAgent
from .sales_ops import SalesOpsAgent
from .seo_aeo import SEOAEOAgent
from .sheets import SheetsAgent
from .social_media import SocialMediaManagerAgent
from .telesales import TelesalesAgent
from .ux_ui_design import UxUiDesignAgent
from .video import VideoAgent
from .visual import VisualAgent
from .workflow_builder import WorkflowBuilderAgent
from .workflow_healer import WorkflowHealerAgent
from .writer import WriterAgent

logger = structlog.get_logger()


class AgentFactory:
    """Constructs all agents with proper dependencies and LLM model assignments."""

    @staticmethod
    async def create_all(
        settings: Settings,
        db: Database,
        n8n_client: N8NClient,
        brand_voices_dir: Path | None = None,
    ) -> AgentRegistry:
        """Build every agent and return a populated registry.

        Model assignment:
        - Scanning agents (Research, Reddit, Google Alerts): Haiku (cheap, fast)
        - Writing agent and Orchestrator: Sonnet (quality)

        Agents listed in settings.disabled_agents are skipped (passed as None
        to the orchestrator, which already handles Optional agents).
        """
        api_key = settings.get_llm_api_key()
        voices_dir = brand_voices_dir or Path(settings.brand_voices_dir)

        disabled = set(settings.disabled_agents)
        if disabled:
            logger.info("agents_disabled", agents=sorted(disabled))

        def _enabled(agent_id: str) -> bool:
            return agent_id not in disabled

        # LLM instances
        scanning_llm = AnthropicLLM(
            api_key=api_key,
            model=settings.llm_model_scanning,
            max_tokens=settings.llm_max_tokens,
            temperature=0.5,  # Lower temp for factual scanning
        )
        writing_llm = AnthropicLLM(
            api_key=api_key,
            model=settings.llm_model_writing,
            max_tokens=settings.llm_max_tokens,
            temperature=0.7,
        )
        premium_llm = AnthropicLLM(
            api_key=api_key,
            model=settings.llm_model_premium,
            max_tokens=settings.llm_max_tokens,
            temperature=0.7,
        )
        orchestrator_llm = AnthropicLLM(
            api_key=api_key,
            model=settings.llm_model,
            max_tokens=settings.llm_max_tokens,
            temperature=settings.llm_temperature,
        )

        # Workspace manager
        workspace_mgr = WorkspaceManager(db, voices_dir)

        # Shared services
        proofreader = Proofreader(llm=scanning_llm)

        # Resolve font path to absolute (prevents CWD-dependent failures → bitmap fallback)
        font_path = settings.default_font_path
        if font_path and not Path(font_path).is_absolute():
            font_path = str(Path(font_path).resolve())
        if font_path and not Path(font_path).exists():
            logger.warning("default_font_not_found", path=font_path)

        text_overlay = TextOverlay(default_font_path=font_path)

        # Resolve Google credentials path to absolute (prevents CWD-dependent failures)
        google_creds = settings.google_credentials_path
        if google_creds and not Path(google_creds).is_absolute():
            google_creds = str(Path(google_creds).resolve())

        # Resolve Google OAuth token path to absolute
        google_oauth = settings.google_oauth_token_path
        if google_oauth and not Path(google_oauth).is_absolute():
            google_oauth = str(Path(google_oauth).resolve())

        # Media storage
        media_storage = MediaStorage(
            db=db,
            supabase_url=settings.supabase_url,
            supabase_service_role_key=settings.supabase_service_role_key,
            supabase_bucket=settings.supabase_bucket,
        )

        # Sub-agents — skip construction for disabled agents (pass None to orchestrator)
        research_agent = (
            ResearchAgent(llm=scanning_llm, db=db, media_storage=media_storage)
            if _enabled("research_agent")
            else None
        )
        reddit_agent = (
            RedditIngestAgent(llm=scanning_llm, db=db) if _enabled("reddit_ingest_agent") else None
        )
        google_alerts_agent = (
            GoogleAlertsIngestAgent(llm=scanning_llm, db=db, n8n_client=n8n_client)
            if _enabled("google_alerts_agent")
            else None
        )
        writer_agent = (
            WriterAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                proofreader=proofreader,
                scanning_llm=scanning_llm,
            )
            if _enabled("writer_agent")
            else None
        )
        visual_agent = (
            VisualAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                openai_api_key=settings.openai_api_key,
                gemini_api_key=settings.gemini_api_key,
                gemini_image_model=settings.gemini_image_model,
                fal_api_key=settings.fal_api_key,
                sdxl_model=settings.sdxl_model,
                media_storage=media_storage,
                proofreader=proofreader,
                text_overlay=text_overlay,
                scanning_llm=scanning_llm,
            )
            if _enabled("create_visual")
            else None
        )
        video_agent = (
            VideoAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                fal_api_key=settings.fal_api_key,
                openai_api_key=settings.openai_api_key,
                video_output_dir=settings.video_output_dir,
                media_storage=media_storage,
                scanning_llm=scanning_llm,
            )
            if _enabled("video_agent")
            else None
        )
        deck_agent = (
            DeckAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                google_credentials_path=google_creds,
                google_oauth_token_path=google_oauth,
                media_storage=media_storage,
                proofreader=proofreader,
                scanning_llm=scanning_llm,
            )
            if _enabled("deck_agent")
            else None
        )
        docs_agent = (
            DocsAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                google_credentials_path=google_creds,
                google_oauth_token_path=google_oauth,
                media_storage=media_storage,
                proofreader=proofreader,
                scanning_llm=scanning_llm,
            )
            if _enabled("docs_agent")
            else None
        )
        sheets_agent = (
            SheetsAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                google_credentials_path=google_creds,
                google_oauth_token_path=google_oauth,
                media_storage=media_storage,
                proofreader=proofreader,
            )
            if _enabled("sheets_agent")
            else None
        )
        motion_graphics_agent = (
            MotionGraphicsAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                remotion_project_dir=settings.remotion_project_dir,
                motion_output_dir=settings.motion_output_dir,
                media_storage=media_storage,
                scanning_llm=scanning_llm,
            )
            if _enabled("motion_graphics_agent")
            else None
        )
        lifecycle_marketing_agent = (
            LifecycleMarketingAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("lifecycle_marketing_agent")
            else None
        )
        growth_ideas_agent = (
            GrowthIdeasAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("growth_ideas_agent")
            else None
        )
        gtm_agent = (
            GTMAgent(
                llm=premium_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("gtm_agent")
            else None
        )
        seo_aeo_agent = (
            SEOAEOAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("seo_aeo_agent")
            else None
        )
        composition_llm = AnthropicLLM(
            api_key=api_key,
            model=settings.llm_model_writing,
            max_tokens=settings.llm_max_tokens,
            temperature=0.3,  # Low temp for deterministic layout specs
        )
        composition_planner_agent = (
            CompositionPlannerAgent(llm=composition_llm, db=db, workspace_manager=workspace_mgr)
            if _enabled("composition_planner_agent")
            else None
        )
        marketing_analytics_agent = (
            MarketingAnalyticsAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("marketing_analytics_agent")
            else None
        )
        performance_marketer_agent = (
            PerformanceMarketerAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("performance_marketer_agent")
            else None
        )
        social_media_agent = (
            SocialMediaManagerAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("social_media_agent")
            else None
        )
        acquisition_agent = (
            AcquisitionAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("acquisition_agent")
            else None
        )
        conversion_optimization_agent = (
            ConversionOptimizationAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("conversion_optimization_agent")
            else None
        )
        ux_ui_design_agent = (
            UxUiDesignAgent(
                llm=premium_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("ux_ui_design_agent")
            else None
        )
        compliance_agent = (
            MarketingComplianceAgent(llm=premium_llm, db=db, workspace_manager=workspace_mgr)
            if _enabled("compliance_agent")
            else None
        )
        legal_strategy_agent = (
            LegalStrategyAgent(
                llm=premium_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("legal_strategy_agent")
            else None
        )
        telesales_agent = (
            TelesalesAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("telesales_agent")
            else None
        )
        sales_ops_agent = (
            SalesOpsAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("sales_ops_agent")
            else None
        )
        linkedin_partnerships_agent = (
            LinkedInPartnershipsAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                scanning_llm=scanning_llm,
            )
            if _enabled("linkedin_partnerships_agent")
            else None
        )
        knowledge_base_agent = (
            KnowledgeBaseAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                memory_store_path=settings.memory_store_path,
            )
            if _enabled("knowledge_base_agent")
            else None
        )
        experiment_engineer_agent = (
            ExperimentEngineerAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                experiments_dir=settings.experiments_dir,
                analytics_dir=settings.analytics_dir,
            )
            if _enabled("experiment_engineer_agent")
            else None
        )
        editorial_agent = (
            EditorialLeadAgent(
                llm=writing_llm,
                db=db,
                workspace_manager=workspace_mgr,
                editorial_data_dir=settings.editorial_data_dir,
                scanning_llm=scanning_llm,
            )
            if _enabled("editorial_agent")
            else None
        )
        # Shared n8n service layer (used by Builder and Healer)
        n8n_service = N8NService(n8n_client)

        workflow_healer_agent = (
            WorkflowHealerAgent(
                llm=writing_llm, db=db, n8n_client=n8n_client, n8n_service=n8n_service
            )
            if _enabled("workflow_healer_agent")
            else None
        )
        workflow_builder_agent = (
            WorkflowBuilderAgent(
                llm=writing_llm,
                db=db,
                n8n_service=n8n_service,
                n8n_base_url=settings.n8n_base_url,
            )
            if _enabled("workflow_builder_agent")
            else None
        )

        # Router (token optimization — off by default)
        router = None
        if settings.router_enabled:
            from ..routing.catalog import build_router_prompt
            from ..routing.router import AgentRouter

            router_llm = AnthropicLLM(
                api_key=api_key,
                model=settings.router_model,
                max_tokens=300,
                temperature=0.2,
            )
            router = AgentRouter(llm=router_llm, router_prompt=build_router_prompt(disabled))
            logger.info("router_enabled", model=settings.router_model)

        # Orchestrator
        orchestrator = CMOOrchestratorAgent(
            llm=orchestrator_llm,
            db=db,
            n8n_client=n8n_client,
            workspace_manager=workspace_mgr,
            research_agent=research_agent,
            reddit_agent=reddit_agent,
            google_alerts_agent=google_alerts_agent,
            writer_agent=writer_agent,
            visual_agent=visual_agent,
            video_agent=video_agent,
            deck_agent=deck_agent,
            performance_marketer_agent=performance_marketer_agent,
            social_media_agent=social_media_agent,
            workflow_healer_agent=workflow_healer_agent,
            workflow_builder_agent=workflow_builder_agent,
            docs_agent=docs_agent,
            sheets_agent=sheets_agent,
            motion_graphics_agent=motion_graphics_agent,
            lifecycle_marketing_agent=lifecycle_marketing_agent,
            growth_ideas_agent=growth_ideas_agent,
            marketing_analytics_agent=marketing_analytics_agent,
            acquisition_agent=acquisition_agent,
            conversion_optimization_agent=conversion_optimization_agent,
            compliance_agent=compliance_agent,
            legal_strategy_agent=legal_strategy_agent,
            telesales_agent=telesales_agent,
            sales_ops_agent=sales_ops_agent,
            linkedin_partnerships_agent=linkedin_partnerships_agent,
            knowledge_base_agent=knowledge_base_agent,
            experiment_engineer_agent=experiment_engineer_agent,
            editorial_agent=editorial_agent,
            gtm_agent=gtm_agent,
            seo_aeo_agent=seo_aeo_agent,
            composition_planner_agent=composition_planner_agent,
            ux_ui_design_agent=ux_ui_design_agent,
            media_storage=media_storage,
            router=router,
        )

        # Registry — only register non-None agents
        registry = AgentRegistry()
        registry.media_storage = media_storage
        registry.register(orchestrator)
        all_agents = [
            research_agent,
            reddit_agent,
            google_alerts_agent,
            writer_agent,
            visual_agent,
            video_agent,
            deck_agent,
            docs_agent,
            sheets_agent,
            lifecycle_marketing_agent,
            performance_marketer_agent,
            social_media_agent,
            motion_graphics_agent,
            growth_ideas_agent,
            marketing_analytics_agent,
            acquisition_agent,
            conversion_optimization_agent,
            compliance_agent,
            legal_strategy_agent,
            telesales_agent,
            sales_ops_agent,
            linkedin_partnerships_agent,
            knowledge_base_agent,
            experiment_engineer_agent,
            editorial_agent,
            gtm_agent,
            seo_aeo_agent,
            composition_planner_agent,
            workflow_healer_agent,
            workflow_builder_agent,
            ux_ui_design_agent,
        ]
        for agent in all_agents:
            if agent is not None:
                registry.register(agent)

        logger.info(
            "agents_created",
            agents=registry.list_agents(),
            scanning_model=settings.llm_model_scanning,
            writing_model=settings.llm_model_writing,
            premium_model=settings.llm_model_premium,
            orchestrator_model=settings.llm_model,
        )

        return registry
