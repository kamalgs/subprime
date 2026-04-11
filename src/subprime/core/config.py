"""Configuration for the Subprime project.

Loads settings from environment variables and/or .env file.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_MODEL = "anthropic:claude-haiku-4-5"

# Data store paths — override via SUBPRIME_DATA_DIR env var for deployment
DATA_DIR = Path(
    os.environ.get("SUBPRIME_DATA_DIR", str(Path.home() / ".subprime" / "data"))
)
DB_PATH = DATA_DIR / "subprime.duckdb"

# Conversations directory (captured advise sessions)
CONVERSATIONS_DIR = Path(
    os.environ.get("SUBPRIME_CONVERSATIONS_DIR", "conversations")
)

# GitHub dataset URLs for the InertExpert2911/Mutual_Fund_Data repository
GITHUB_RAW_BASE = "https://raw.githubusercontent.com/InertExpert2911/Mutual_Fund_Data/main"
GITHUB_LFS_BASE = "https://media.githubusercontent.com/media/InertExpert2911/Mutual_Fund_Data/main"
SCHEMES_CSV_URL = f"{GITHUB_RAW_BASE}/mutual_fund_data.csv"
NAV_PARQUET_URL = f"{GITHUB_LFS_BASE}/mutual_fund_nav_history.parquet"

# Curation: top-N funds per category in the fund universe
CURATED_TOP_N = 15


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
