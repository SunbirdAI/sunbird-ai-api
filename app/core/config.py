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
    signed_url_expiry_minutes: int = Field(
        default=30, description="Expiry time for signed URLs in minutes"
    )

    # Server Configuration
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8000, description="Server port")
    workers: int = Field(default=1, description="Number of worker processes")

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return not self.debug


@lru_cache
def get_settings() -> Settings:
    """
    Get cached settings instance.

    Uses lru_cache to ensure settings are only loaded once.
    """
    return Settings()


# Global settings instance
settings = get_settings()
