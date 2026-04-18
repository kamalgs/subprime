"""Configuration for the Subprime project.

Loads settings from environment variables and/or .env file.
"""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


DEFAULT_MODEL = os.environ.get("SUBPRIME_MODEL", "anthropic:claude-haiku-4-5")


def model_provider(model: str) -> str:
    """Return the provider prefix from a PydanticAI model string.

    Examples: ``"anthropic:claude-haiku-4-5"`` → ``"anthropic"``,
    ``"openai:meta-llama/Llama-3.1-70B"`` → ``"openai"``,
    ``"groq:llama-3.1-70b"`` → ``"groq"``.
    Falls back to ``"anthropic"`` when there is no colon prefix.
    """
    if ":" in model:
        return model.split(":", 1)[0]
    return "anthropic"


def is_anthropic(model: str) -> bool:
    """True when *model* targets the Anthropic API."""
    return model_provider(model) == "anthropic"


def is_together(model: str) -> bool:
    """True when *model* targets Together AI (together: prefix)."""
    return model_provider(model) == "together"


def is_bedrock(model: str) -> bool:
    """True when *model* targets AWS Bedrock (bedrock: prefix).

    Use this for Claude via Bedrock when the Anthropic direct API is
    rate-limited. The suffix after ``bedrock:`` is the Bedrock inference
    profile ID (e.g. ``us.anthropic.claude-sonnet-4-6``). Region is read
    from ``AWS_REGION`` / ``AWS_DEFAULT_REGION`` / AWS config default.
    """
    return model_provider(model) == "bedrock"


def is_vllm(model: str) -> bool:
    """True when *model* targets a self-hosted vLLM endpoint (vllm: prefix).

    The endpoint URL is read from VLLM_BASE_URL. Intended for subprime-infra
    serving on Lambda/RunPod: ``vllm:Qwen/Qwen3.5-9B``.
    """
    return model_provider(model) == "vllm"


def is_qwen3(model: str) -> bool:
    """True for Qwen3 / Qwen3.5 variants (configurable thinking via chat template)."""
    name = model.split(":", 1)[-1].lower()
    return "qwen3" in name


def supports_thinking(model: str) -> bool:
    """True when *model* supports extended thinking."""
    return is_anthropic(model) or is_qwen3(model)


def together_model_name(model: str) -> str:
    """Strip the ``together:`` prefix and return the raw Together model id."""
    return model.split(":", 1)[1] if ":" in model else model


def build_model(model: str, *, role: str | None = None):
    """Return either a model string (for native PydanticAI providers) or a
    configured model instance.

    For ``together:`` prefixes, constructs an OpenAI-compatible chat model
    pointed at Together's endpoint. For ``vllm:`` prefixes, points at a
    self-hosted endpoint resolved from env vars (see below). Other prefixes
    (anthropic, openai, groq…) pass through as strings.

    vLLM endpoint resolution (per role):
        VLLM_ADVISOR_BASE_URL  — when role="advisor"
        VLLM_JUDGE_BASE_URL    — when role="judge"
        VLLM_BASE_URL          — fallback for either
    """
    if is_together(model):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.together import TogetherProvider

        api_key = os.environ.get("TOGETHER_API_KEY")
        return OpenAIChatModel(
            together_model_name(model),
            provider=TogetherProvider(api_key=api_key),
        )
    if is_bedrock(model):
        # Bedrock uses cross-region inference profiles for Claude 4.x
        # (e.g. us.anthropic.claude-sonnet-4-6). BEDROCK_REGION explicitly
        # overrides AWS config; defaults to us-east-1 (where Claude profiles
        # are always available) since the user's aws config may point at a
        # region that doesn't host Claude (e.g. ap-south-2).
        from pydantic_ai.models.bedrock import BedrockConverseModel
        from pydantic_ai.providers.bedrock import BedrockProvider

        region = (
            os.environ.get("BEDROCK_REGION")
            or os.environ.get("AWS_REGION")
            or os.environ.get("AWS_DEFAULT_REGION")
            or "us-east-1"
        )
        return BedrockConverseModel(
            together_model_name(model),
            provider=BedrockProvider(region_name=region),
        )
    if is_vllm(model):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        role_env = {"advisor": "VLLM_ADVISOR_BASE_URL", "judge": "VLLM_JUDGE_BASE_URL"}.get(role or "")
        base_url = (
            (role_env and os.environ.get(role_env))
            or os.environ.get("VLLM_BASE_URL")
            or "http://localhost:8000/v1"
        )
        return OpenAIChatModel(
            together_model_name(model),  # strips "vllm:" prefix, returns the HF id
            provider=OpenAIProvider(base_url=base_url, api_key="EMPTY"),
        )
    return model


def build_model_settings(
    model: str,
    *,
    cache: bool = True,
    thinking: bool = False,
) -> dict:
    """Build provider-appropriate model_settings for a PydanticAI Agent.

    Anthropic: prompt caching + native thinking toggle.
    Qwen3 / Qwen3.5 (vLLM or Together): ``extra_body.chat_template_kwargs.enable_thinking``.
    Other open-weight chat models: default output cap only.
    """
    settings: dict = {}
    if is_anthropic(model):
        if cache:
            settings["anthropic_cache_instructions"] = "1h"
        if thinking and supports_thinking(model):
            settings["thinking"] = "medium"
            settings["max_tokens"] = 32000
    elif is_qwen3(model):
        # Qwen chat template accepts enable_thinking via extra_body — works for
        # both vLLM and Together AI OpenAI-compatible endpoints.
        settings["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": bool(thinking)}
        }
        # Thinking mode interleaves reasoning before the final answer; give it
        # generous headroom so structured outputs don't truncate mid-JSON.
        # Non-thinking uses a tighter budget that still leaves room for the
        # full InvestmentPlan JSON plus any retry commentary.
        settings["max_tokens"] = 24000 if thinking else 6000
    if not thinking and "max_tokens" not in settings:
        settings["max_tokens"] = 8192
    return settings

# Web advisor model config — override via env vars.
# ADVISOR_MODEL: model used by the junior advisor to draft plans.
# REFINE_MODEL:  model used by the senior reviewer to polish drafts.
#                Set to "none" (string) or leave unset to skip refinement.
ADVISOR_MODEL: str = os.environ.get("ADVISOR_MODEL", "anthropic:claude-haiku-4-5")
_refine_env = os.environ.get("REFINE_MODEL", "anthropic:claude-sonnet-4-6")
REFINE_MODEL: str | None = None if _refine_env.lower() == "none" else _refine_env

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

# PostgreSQL — None means fall back to in-memory
DATABASE_URL: str | None = os.environ.get("DATABASE_URL")

# SMTP for OTP emails
SMTP_HOST: str | None = os.environ.get("SMTP_HOST")
SMTP_PORT: int = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER: str | None = os.environ.get("SMTP_USER")
SMTP_PASSWORD: str | None = os.environ.get("SMTP_PASSWORD")
SMTP_FROM: str = os.environ.get("SMTP_FROM", "noreply@finadvisor.gkamal.online")

# OTP settings
OTP_DAILY_LIMIT: int = int(os.environ.get("OTP_DAILY_LIMIT", "100"))
OTP_EXPIRY_MINUTES: int = int(os.environ.get("OTP_EXPIRY_MINUTES", "10"))


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
