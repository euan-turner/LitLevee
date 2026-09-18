"""Centralised application configuration.

All configuration is loaded from environment variables (optionally via a
``.env`` file, or GitHub Actions secrets in CI). Nothing else in the
codebase should call ``os.environ`` directly -- go through :data:`settings`
instead.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Slack (chat:write only -- see new_design.md section 22) -----------
    slack_bot_token: str = Field(default="", description="xoxb-... bot token")
    slack_channel_id: str = Field(
        default="", description="Private #literature-<user> channel ID"
    )

    # --- Database ------------------------------------------------------------
    database_path: str = Field(
        default="litagent.db", description="Path to the SQLite database file"
    )

    # --- LLM / embeddings ------------------------------------------------
    llm_api_key: str = Field(default="", description="API key for the LLM provider")
    llm_model: str = Field(default="gpt-4.1-mini", description="Default LLM model id")
    embedding_api_key: str = Field(
        default="", description="API key for the embedding provider (may equal llm_api_key)"
    )
    embedding_model: str = Field(
        default="text-embedding-3-small", description="Default embedding model id"
    )

    # --- External data sources -------------------------------------------
    semantic_scholar_api_key: str = Field(default="", description="Optional S2 API key")
    openalex_api_key: str = Field(
        default="",
        description="OpenAlex API key for higher rate limits (the `mailto` polite-pool "
        "parameter is deprecated in favour of this)",
    )

    # --- Relevance funnel thresholds (section 11, configurable per section) -
    lexical_candidate_limit: int = Field(
        default=300, description="Max candidates kept by the cheap lexical filter"
    )
    embedding_candidate_limit: int = Field(
        default=60, description="Max candidates kept by the embedding-similarity filter"
    )
    embedding_similarity_threshold: float = Field(
        default=0.2, description="Minimum cosine similarity to survive the embedding filter"
    )
    llm_classify_limit: int = Field(
        default=30, description="Max candidates sent to the LLM relevance classifier per run"
    )
    relevance_score_threshold: float = Field(
        default=0.4, description="Minimum LLM relevance score to avoid the 'irrelevant' category"
    )

    # --- Digest / monitoring --------------------------------------------
    digest_hour_utc: int = Field(default=13, ge=0, le=23, description="Informational only: GH Actions cron controls actual timing")

    # --- Paper analysis ---------------------------------------------------
    max_pdf_text_chars: int = Field(
        default=40_000, description="Cap on extracted PDF text sent to the analysis prompt"
    )

    # --- Misc --------------------------------------------------------------
    log_level: str = Field(default="INFO")
    environment: str = Field(default="development")


@lru_cache
def get_settings() -> Settings:
    """Return a cached, process-wide Settings instance."""
    return Settings()


settings = get_settings()
