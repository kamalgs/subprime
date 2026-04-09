"""Configuration for the Subprime project.

Loads settings from environment variables and/or .env file.
"""

from __future__ import annotations

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_MODEL = "anthropic:claude-haiku-4-5"


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: SecretStr
    default_model: str = "claude-haiku-4-5"
    mfdata_base_url: str = "https://mfdata.in/api/v1"
    results_dir: str = "results"
