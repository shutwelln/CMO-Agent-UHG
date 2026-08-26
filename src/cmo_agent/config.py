"""Configuration management using Pydantic settings."""

from __future__ import annotations

from functools import lru_cache
from typing import List, Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Main application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    environment: Literal["development", "staging", "production"] = Field(
        default="development", alias="ENVIRONMENT"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    debug: bool = Field(default=False, alias="DEBUG")

    # Agent toggling (comma-separated agent IDs to disable)
    disabled_agents: List[str] = Field(default_factory=list, alias="DISABLED_AGENTS")

    # n8n settings
    n8n_base_url: str = Field(default="http://localhost:5678", alias="N8N_BASE_URL")
    n8n_api_key: str = Field(default="", alias="N8N_API_KEY")
    n8n_timeout: float = Field(default=30.0)
    n8n_max_retries: int = Field(default=3)

    # LLM settings
    llm_provider: Literal["anthropic", "openai"] = Field(default="anthropic", alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-sonnet-4-6", alias="LLM_MODEL")
    llm_model_scanning: str = Field(default="claude-haiku-4-5-20251001", alias="LLM_MODEL_SCANNING")
    llm_model_writing: str = Field(default="claude-sonnet-4-6", alias="LLM_MODEL_WRITING")
    llm_model_premium: str = Field(default="claude-opus-4-6", alias="LLM_MODEL_PREMIUM")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")
    llm_temperature: float = Field(default=0.7, alias="LLM_TEMPERATURE")

    # API Keys
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    fal_api_key: str = Field(default="", alias="FAL_API_KEY")

    # Image generation — tiered models
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    gemini_image_model: str = Field(
        default="gemini-3-pro-image-preview", alias="GEMINI_IMAGE_MODEL"
    )
    sdxl_model: str = Field(default="fal-ai/fast-sdxl", alias="SDXL_MODEL")

    # Video generation output
    video_output_dir: str = Field(default="./data/videos", alias="VIDEO_OUTPUT_DIR")

    # Motion graphics (Remotion)
    remotion_project_dir: str = Field(default="./data/remotion", alias="REMOTION_PROJECT_DIR")
    motion_output_dir: str = Field(default="./data/motion_graphics", alias="MOTION_OUTPUT_DIR")

    # Slack settings (Socket Mode)
    slack_bot_token: str = Field(default="", alias="SLACK_BOT_TOKEN")
    slack_app_token: str = Field(default="", alias="SLACK_APP_TOKEN")
    slack_signing_secret: str = Field(default="", alias="SLACK_SIGNING_SECRET")
    slack_admin_users: str = Field(default="", alias="SLACK_ADMIN_USERS")

    # Memory settings
    memory_enabled: bool = Field(default=True, alias="MEMORY_ENABLED")
    memory_max_turns: int = Field(default=6, alias="MEMORY_MAX_TURNS")
    memory_max_stored: int = Field(default=30, alias="MEMORY_MAX_STORED")
    memory_db_path: str = Field(default="./data/slack_memory.db", alias="MEMORY_DB_PATH")

    # Phase 2: Database & workspace settings
    db_path: str = Field(default="./data/cmo_agent.db", alias="DB_PATH")
    default_workspace: str = Field(default="", alias="DEFAULT_WORKSPACE")
    brand_voices_dir: str = Field(default="./data/brand_voices", alias="BRAND_VOICES_DIR")

    # Phase 2: Scheduler
    scheduler_enabled: bool = Field(default=False, alias="SCHEDULER_ENABLED")

    # Ralph Loop quality refinement
    refinement_enabled: bool = Field(default=False, alias="REFINEMENT_ENABLED")
    refinement_enabled_visual: bool = Field(default=True, alias="REFINEMENT_ENABLED_VISUAL")

    # Workflow healing
    heal_check_interval: int = Field(default=3600, alias="HEAL_CHECK_INTERVAL")
    heal_check_enabled: bool = Field(default=True, alias="HEAL_CHECK_ENABLED")

    # Phase 2: Google Slides API (service account credentials)
    google_credentials_path: str = Field(default="", alias="GOOGLE_CREDENTIALS_PATH")

    # Google OAuth2 token (preferred over service account for consumer Gmail)
    google_oauth_token_path: str = Field(default="", alias="GOOGLE_OAUTH_TOKEN_PATH")

    # Font settings for text overlay
    default_font_path: str = Field(default="./data/fonts/Inter-Bold.otf", alias="DEFAULT_FONT_PATH")

    # Supabase Storage (optional — centralized media CDN)
    supabase_url: str = Field(default="", alias="SUPABASE_URL")
    supabase_service_role_key: str = Field(default="", alias="SUPABASE_SERVICE_ROLE_KEY")
    supabase_bucket: str = Field(default="cmo-media", alias="SUPABASE_BUCKET")

    # Phase 2: Slack notification channels
    slack_notification_channel: str = Field(default="", alias="SLACK_NOTIFICATION_CHANNEL")
    slack_growth_ideas_channel: str = Field(default="", alias="SLACK_GROWTH_IDEAS_CHANNEL")
    growth_ideas_schedule_hour: int = Field(default=6, alias="GROWTH_IDEAS_SCHEDULE_HOUR")
    growth_ideas_schedule_minute: int = Field(default=0, alias="GROWTH_IDEAS_SCHEDULE_MINUTE")
    growth_ideas_tz_offset: float = Field(default=-6.0, alias="GROWTH_IDEAS_TZ_OFFSET")
    growth_ideas_frequency_days: int = Field(default=1, alias="GROWTH_IDEAS_FREQUENCY_DAYS")
    growth_ideas_count_min: int = Field(default=5, alias="GROWTH_IDEAS_COUNT_MIN")
    growth_ideas_count_max: int = Field(default=10, alias="GROWTH_IDEAS_COUNT_MAX")
    growth_ideas_spreadsheet_id: str = Field(default="", alias="GROWTH_IDEAS_SPREADSHEET_ID")

    # Router (token optimization)
    router_enabled: bool = Field(default=True, alias="ROUTER_ENABLED")
    router_model: str = Field(default="claude-haiku-4-5-20251001", alias="ROUTER_MODEL")
    token_budget_warn: int = Field(default=2500, alias="TOKEN_BUDGET_WARN")
    token_instrumentation: bool = Field(default=True, alias="TOKEN_INSTRUMENTATION")

    # Knowledge Base / Memory Curator
    memory_store_path: str = Field(default="./data/memory", alias="MEMORY_STORE_PATH")

    # Experiments
    experiments_dir: str = Field(default="./data/experiments", alias="EXPERIMENTS_DIR")
    analytics_dir: str = Field(default="./data/analytics", alias="ANALYTICS_DIR")

    # Customer.io (Lifecycle Marketing)
    customerio_app_api_key: str = Field(default="", alias="CUSTOMERIO_APP_API_KEY")

    # Editorial
    editorial_data_dir: str = Field(default="./data/editorial", alias="EDITORIAL_DATA_DIR")

    # GA4 Analytics
    ga4_property_id: str = Field(default="", alias="GA4_PROPERTY_ID")
    ga4_measurement_id: str = Field(default="", alias="GA4_MEASUREMENT_ID")
    ga4_api_secret: str = Field(default="", alias="GA4_API_SECRET")
    gtm_container_id: str = Field(default="", alias="GTM_CONTAINER_ID")

    # Claude Code CLI integration
    claude_code_cwd: str = Field(default=".", alias="CLAUDE_CODE_CWD")
    claude_code_max_message_length: int = Field(
        default=3000, alias="CLAUDE_CODE_MAX_MESSAGE_LENGTH"
    )
    claude_code_plan_timeout_ms: int = Field(default=120000, alias="CLAUDE_CODE_PLAN_TIMEOUT_MS")
    claude_code_build_timeout_ms: int = Field(default=600000, alias="CLAUDE_CODE_BUILD_TIMEOUT_MS")
    claude_code_binary: str = Field(default="claude", alias="CLAUDE_CODE_BINARY")

    # ElevenLabs (audio generation, optional)
    elevenlabs_api_key: str = Field(default="", alias="ELEVENLABS_API_KEY")
    pexels_api_key: str = Field(default="", alias="PEXELS_API_KEY")

    def get_llm_api_key(self) -> str:
        """Get the API key for the configured LLM provider."""
        if self.llm_provider == "anthropic":
            return self.anthropic_api_key
        return self.openai_api_key


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
