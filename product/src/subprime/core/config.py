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


def is_workers_ai(model: str) -> bool:
    """True when *model* targets Cloudflare Workers AI (workers-ai: prefix).

    Example: ``workers-ai:@cf/meta/llama-3.3-70b-instruct-fp8-fast``.
    Always routed through AI Gateway — Workers AI direct endpoints aren't
    supported (the gateway is cheaper to configure than duplicating auth).
    """
    return model_provider(model) == "workers-ai"


def is_openrouter(model: str) -> bool:
    """True when *model* targets OpenRouter (openrouter: prefix).

    Example: ``openrouter:qwen/qwen3-30b-a3b-instruct``. OpenAI-compatible
    API at https://openrouter.ai/api/v1. Auth: OPENROUTER_API_KEY.
    """
    return model_provider(model) == "openrouter"


def is_groq(model: str) -> bool:
    """True when *model* targets Groq (groq: prefix).

    Example: ``groq:llama-3.3-70b-versatile``. Routed through AI Gateway
    when configured.
    """
    return model_provider(model) == "groq"


def is_google_gla(model: str) -> bool:
    """True when *model* targets Google AI Studio (Generative Language API).

    Example: ``google-gla:gemini-2.5-flash``.
    Uses the free-tier AI Studio API; not the Vertex AI production path.
    Routed through AI Gateway when configured.
    """
    return model_provider(model) == "google-gla"


# Providers whose function-calling implementation preserves nested JSON types
# reliably enough for pydantic-ai's tool-output mode to work on our schemas.
# Everything else falls back to prompted output (JSON-in-text) with a repair
# pass by a small model.
_TOOL_CALL_RELIABLE = {
    "anthropic",
    "bedrock",  # Claude on Bedrock — same model family as anthropic
    "google-gla",
    "google-vertex",
    "groq",
    "openai",
    "together",  # generally fine for Qwen3-235B which is what we use
}


def tool_calls_reliable(model: str) -> bool:
    """True when this provider's function-calling layer is trusted for
    complex nested schemas (array-of-objects, nested models, etc.).

    When False, agents must use PromptedOutput rather than ToolOutput —
    otherwise Llama/Qwen on Workers-AI-style compat layers emit arguments
    as JSON-wrapped strings and parsing fails.
    """
    return model_provider(model) in _TOOL_CALL_RELIABLE


def ai_gateway_base_url() -> str | None:
    """Return the Cloudflare AI Gateway base URL, e.g.
    'https://gateway.ai.cloudflare.com/v1/<acct>/<gateway>'. None when the
    gateway isn't configured — in which case providers go direct."""
    return os.environ.get("AI_GATEWAY_BASE_URL") or None


def _ai_gateway_cache_key() -> str | None:
    """Value for the ``cf-aig-cache-key`` request header.

    AI Gateway appends this to its auto-generated cache key so bumping it
    force-invalidates cached responses without manual dashboard work.
    Defaults to the short git SHA of the deploy (set via env by the
    container's build step) + a hash of the prompt files so a prompt
    tweak also bumps the key.
    """
    v = os.environ.get("AI_GATEWAY_CACHE_VERSION")
    if v:
        return v
    # Fall back: SUBPRIME_PROMPT_VERSION + commit SHA derived at module
    # load time. Good enough for invalidation when the image changes.
    pv = os.environ.get("SUBPRIME_PROMPT_VERSION", "")
    return f"v{pv}" if pv else None


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


def _default_headers() -> dict[str, str]:
    """HTTP headers added to every outbound LLM call. Currently just the
    AI Gateway cache-key header when configured."""
    headers: dict[str, str] = {}
    key = _ai_gateway_cache_key()
    if key:
        headers["cf-aig-cache-key"] = key
    return headers


def _gateway_http_client(extra_headers: dict[str, str] | None = None):
    """Shared httpx AsyncClient preconfigured with the cf-aig-cache-key
    header so every call automatically participates in AI Gateway's
    versioned cache namespace.
    """
    import httpx

    hdrs = _default_headers()
    if extra_headers:
        hdrs.update(extra_headers)
    return httpx.AsyncClient(headers=hdrs, timeout=httpx.Timeout(600.0))


def build_model(model: str, *, role: str | None = None):
    """Return either a model string (for native PydanticAI providers) or a
    configured model instance.

    Providers and how they're routed:
      together:<hf-id>     — Together AI. Via AI Gateway if AI_GATEWAY_BASE_URL
                             is set, else direct.
      anthropic:<id>       — Anthropic. Direct string returned (PydanticAI
                             instantiates); when AI_GATEWAY_BASE_URL is set
                             we build an AnthropicModel with a custom base.
      bedrock:<profile-id> — Claude via AWS Bedrock. Direct — AI Gateway
                             support requires signed requests we don't bother
                             with yet.
      workers-ai:<model>   — Cloudflare Workers AI (via AI Gateway only).
      vllm:<hf-id>         — Self-hosted vLLM at VLLM_*_BASE_URL.
      <other prefixes>     — pass through as string.
    """
    gateway = ai_gateway_base_url()

    if is_together(model):
        # Cloudflare AI Gateway does not support Together AI as a provider
        # (confirmed: gateway returns {"code": 2008, "message": "Invalid
        # provider"} for `together`, `together-ai`, `togetherai` slugs).
        # Always go direct — we lose gateway-side caching for Together calls,
        # but the alternative is a broken advisor.
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.together import TogetherProvider

        api_key = os.environ.get("TOGETHER_API_KEY")
        name = together_model_name(model)
        return OpenAIChatModel(name, provider=TogetherProvider(api_key=api_key))

    if is_openrouter(model):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        api_key = os.environ.get("OPENROUTER_API_KEY")
        name = together_model_name(model)  # strips "openrouter:"
        # OpenRouter recommends HTTP-Referer + X-Title headers for attribution.
        import httpx

        http_client = httpx.AsyncClient(
            headers={
                "HTTP-Referer": "https://finadvisor.gkamal.online",
                "X-Title": "Benji (Subprime)",
            },
            timeout=httpx.Timeout(600.0),
        )
        return OpenAIChatModel(
            name,
            provider=OpenAIProvider(
                base_url="https://openrouter.ai/api/v1",
                api_key=api_key,
                http_client=http_client,
            ),
        )

    if is_groq(model):
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        api_key = os.environ.get("GROQ_API_KEY")
        name = together_model_name(model)  # strips "groq:"
        if gateway:
            return OpenAIChatModel(
                name,
                provider=OpenAIProvider(
                    base_url=f"{gateway.rstrip('/')}/groq/openai/v1",
                    api_key=api_key,
                    http_client=_gateway_http_client(),
                ),
            )
        return OpenAIChatModel(
            name,
            provider=OpenAIProvider(
                base_url="https://api.groq.com/openai/v1",
                api_key=api_key,
            ),
        )

    if is_workers_ai(model):
        if not gateway:
            raise RuntimeError("workers-ai:* models require AI_GATEWAY_BASE_URL to be set")
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        # Workers AI exposes an OpenAI-compatible endpoint at /v1 under
        # the ai gateway. The model id is the '@cf/...' slug.
        name = together_model_name(model)  # strips "workers-ai:"
        return OpenAIChatModel(
            name,
            provider=OpenAIProvider(
                base_url=f"{gateway.rstrip('/')}/workers-ai/v1",
                api_key=os.environ.get("CLOUDFLARE_API_TOKEN", "EMPTY"),
                http_client=_gateway_http_client(),
            ),
        )

    if is_google_gla(model):
        # Google AI Studio (free Generative Language API). Route via
        # AI Gateway when configured — the provider accepts a custom
        # base_url + http_client so our cf-aig-cache-key header rides
        # along on every call.
        from pydantic_ai.models.google import GoogleModel
        from pydantic_ai.providers.google import GoogleProvider

        api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        name = together_model_name(model)  # strips "google-gla:"
        if gateway:
            return GoogleModel(
                name,
                provider=GoogleProvider(
                    api_key=api_key,
                    base_url=f"{gateway.rstrip('/')}/google-ai-studio",
                    http_client=_gateway_http_client(),
                ),
            )
        return GoogleModel(name, provider=GoogleProvider(api_key=api_key))
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

        role_env = {"advisor": "VLLM_ADVISOR_BASE_URL", "judge": "VLLM_JUDGE_BASE_URL"}.get(
            role or ""
        )
        base_url = (
            (role_env and os.environ.get(role_env))
            or os.environ.get("VLLM_BASE_URL")
            or "http://localhost:8000/v1"
        )
        return OpenAIChatModel(
            together_model_name(model),  # strips "vllm:" prefix, returns the HF id
            provider=OpenAIProvider(base_url=base_url, api_key="EMPTY"),
        )

    if is_anthropic(model) and gateway:
        # Anthropic through AI Gateway: use the AnthropicModel with a
        # custom base_url so all calls land in the gateway and participate
        # in its cache + analytics.
        from pydantic_ai.models.anthropic import AnthropicModel
        from pydantic_ai.providers.anthropic import AnthropicProvider

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        name = together_model_name(model)  # strips "anthropic:"
        return AnthropicModel(
            name,
            provider=AnthropicProvider(
                api_key=api_key,
                base_url=f"{gateway.rstrip('/')}/anthropic",
                http_client=_gateway_http_client(),
            ),
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
        settings["extra_body"] = {"chat_template_kwargs": {"enable_thinking": bool(thinking)}}
        # Thinking mode interleaves reasoning before the final answer; give it
        # generous headroom so structured outputs don't truncate mid-JSON.
        # Non-thinking uses a tighter budget that still leaves room for the
        # full InvestmentPlan JSON plus any retry commentary.
        settings["max_tokens"] = 24000 if thinking else 6000
    if not thinking and "max_tokens" not in settings:
        settings["max_tokens"] = 16384
    return settings


# Web advisor model config — override via env vars.
# ADVISOR_MODEL: model used by the junior advisor to draft plans.
# REFINE_MODEL:  model used by the senior reviewer to polish drafts.
#                Set to "none" (string) or leave unset to skip refinement.
ADVISOR_MODEL: str = os.environ.get("ADVISOR_MODEL", "anthropic:claude-haiku-4-5")
# Basic-tier override. When set, plan + strategy for the free archetype
# flow route here instead of ADVISOR_MODEL. Intended for a smaller, faster,
# cheaper model fronted by AI Gateway so repeat archetype selections
# cache. Empty / unset → everyone uses ADVISOR_MODEL.
ADVISOR_MODEL_BASIC: str = os.environ.get("ADVISOR_MODEL_BASIC", "")
_refine_env = os.environ.get("REFINE_MODEL", "anthropic:claude-sonnet-4-6")
REFINE_MODEL: str | None = None if _refine_env.lower() == "none" else _refine_env

# Data store paths — override via SUBPRIME_DATA_DIR env var for deployment
DATA_DIR = Path(os.environ.get("SUBPRIME_DATA_DIR", str(Path.home() / ".subprime" / "data")))
DB_PATH = DATA_DIR / "subprime.duckdb"

# Conversations directory (captured advise sessions)
CONVERSATIONS_DIR = Path(os.environ.get("SUBPRIME_CONVERSATIONS_DIR", "conversations"))

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
