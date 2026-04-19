"""
Application Configuration

Centralized configuration management using Pydantic Settings.
Supports environment variables and .env files.
"""

from functools import lru_cache
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings.

    All settings can be overridden via environment variables.
    Example: TTS_API_URL=https://example.com
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # API Configuration
    app_name: str = Field(default="TTS API", description="Application name")
    app_version: str = Field(default="1.0.0", description="Application version")
    debug: bool = Field(default=False, description="Debug mode")

    # TTS Service Configuration
    tts_api_url: str = Field(
        default="https://sb-modal-ws--spark-tts-salt-sparktts-generate.modal.run",
        description="External TTS API URL",
    )
    request_timeout_seconds: int = Field(
        default=120, description="Timeout for TTS API requests in seconds"
    )

    # Modal STT Service Configuration
    modal_stt_api_url: str = Field(
        default="https://sb-modal-ws--asr-whisper-large-v3-salt-model-transcribe.modal.run",
        description="Modal Whisper ASR API URL for speech-to-text",
    )
    max_text_length: int = Field(
        default=10000, description="Maximum allowed text length for TTS"
    )

    # GCP Storage Configuration
    gcp_bucket_name: str = Field(
        default="your-tts-audio-bucket",
        description="GCP Storage bucket name for audio files",
    )
    gcp_project_id: Optional[str] = Field(
        default=None, description="GCP Project ID (optional, uses default if not set)"
    )
    gcp_service_account_email: Optional[str] = Field(
        default=None,
        description="GCP Service Account email for IAM-based signed URL generation (required for Cloud Run)",
    )
    signed_url_expiry_minutes: int = Field(
        default=30, description="Expiry time for signed URLs in minutes"
    )

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")

    # Database Configuration
    database_url: str = Field(
        default="sqlite+aiosqlite:///./test.db",
        description="Database connection URL",
    )
    environment: str = Field(
        default="development",
        description="Application environment (development, staging, production)",
    )
    db_echo: bool = Field(
        default=False,
        description="Enable SQLAlchemy query logging (auto-disabled in production)",
    )
    db_pool_size: int = Field(
        default=50,
        description="Database connection pool size (20 in production, 50 otherwise)",
    )
    db_max_overflow: int = Field(
        default=0,
        description="Maximum overflow connections (10 in production, 0 otherwise)",
    )
    db_pool_recycle: int = Field(
        default=600,
        description="Connection pool recycle time in seconds",
    )
    db_ssl_enabled: bool = Field(
        default=False,
        description="Enable SSL for database connections in production",
    )

    # Google Analytics Data API
    ga_impersonation_target: Optional[str] = Field(
        default=None,
        description=(
            "Service account email to impersonate for the Google Analytics "
            "Data API (e.g. ga-reader@sb-gcp-project-01.iam.gserviceaccount.com)."
        ),
    )
    ga_properties_raw: str = Field(
        default="",
        alias="GA_PROPERTIES",
        description=(
            "Comma-separated `id:name` pairs, e.g. "
            "'506611499:Sunflower,448469065:Sunbird Speech'."
        ),
    )
    ga_cache_ttl_seconds: int = Field(
        default=3600, description="TTL for cached GA report payloads."
    )
    ga_request_timeout_seconds: int = Field(
        default=30, description="Timeout for a single GA Data API call."
    )
    cache_backend: str = Field(
        default="memory",
        description="Cache backend: 'memory' (default) or 'upstash'.",
    )

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.environment.lower() == "production"

    @property
    def ga_properties(self) -> dict[str, str]:
        """Parse GA_PROPERTIES env string into {property_id: display_name}."""
        result: dict[str, str] = {}
        for part in self.ga_properties_raw.split(","):
            part = part.strip()
            if ":" not in part:
                continue
            prop_id, name = part.split(":", 1)
            prop_id, name = prop_id.strip(), name.strip()
            if prop_id and name:
                result[prop_id] = name
        return result

    @property
    def ga_enabled(self) -> bool:
        """True iff both GA impersonation target and properties are configured."""
        return bool(self.ga_impersonation_target) and bool(self.ga_properties)

    @property
    def database_url_async(self) -> str:
        """
        Get the async-compatible database URL.

        Converts 'postgres://' to 'postgresql+asyncpg://' for async support.
        """
        if self.database_url and self.database_url.startswith("postgres://"):
            return self.database_url.replace("postgres://", "postgresql+asyncpg://", 1)
        return self.database_url

    @property
    def effective_db_pool_size(self) -> int:
        """Get pool size based on environment."""
        return 20 if self.is_production else self.db_pool_size

    @property
    def effective_db_max_overflow(self) -> int:
        """Get max overflow based on environment."""
        return 10 if self.is_production else self.db_max_overflow

    @property
    def effective_db_echo(self) -> bool:
        """Get echo setting - disabled in production."""
        return self.db_echo and not self.is_production


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Global settings instance
settings = get_settings()
