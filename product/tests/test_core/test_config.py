"""Tests for subprime.core.config — Settings via pydantic-settings.

Google-style small tests: fast, deterministic, no network calls.
"""

from __future__ import annotations


class TestSettings:
    def test_defaults(self, monkeypatch):
        """Settings should have sensible defaults for all non-secret fields."""
        # Ensure env var is set so construction doesn't fail
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key-123")

        from subprime.core.config import Settings

        s = Settings()
        assert s.default_model == "claude-haiku-4-5"
        assert s.mfdata_base_url == "https://mfdata.in/api/v1"
        assert s.results_dir == "results"

    def test_api_key_from_env(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-my-secret-key")

        from subprime.core.config import Settings

        s = Settings()
        assert s.anthropic_api_key.get_secret_value() == "sk-my-secret-key"

    def test_override_model(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("DEFAULT_MODEL", "gpt-4o-mini")

        from subprime.core.config import Settings

        s = Settings()
        assert s.default_model == "gpt-4o-mini"

    def test_override_results_dir(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("RESULTS_DIR", "/tmp/my_results")

        from subprime.core.config import Settings

        s = Settings()
        assert s.results_dir == "/tmp/my_results"

    def test_override_mfdata_base_url(self, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
        monkeypatch.setenv("MFDATA_BASE_URL", "http://localhost:8080")

        from subprime.core.config import Settings

        s = Settings()
        assert s.mfdata_base_url == "http://localhost:8080"

    def test_together_model_routes_to_openai_chat_model(self, monkeypatch):
        """together: prefix should produce a configured OpenAIChatModel."""
        monkeypatch.setenv("TOGETHER_API_KEY", "tgp_v1_test")

        from pydantic_ai.models.openai import OpenAIChatModel

        from subprime.core.config import (
            build_model,
            build_model_settings,
            is_qwen3,
            is_together,
        )

        m = build_model("together:Qwen/Qwen3.5-397B-A17B")
        assert isinstance(m, OpenAIChatModel)
        assert m.model_name == "Qwen/Qwen3.5-397B-A17B"

        assert is_together("together:google/gemma-4-31B-it") is True
        assert is_together("anthropic:claude-haiku-4-5") is False
        assert is_qwen3("together:Qwen/Qwen3.5-397B-A17B") is True
        assert is_qwen3("together:google/gemma-4-31B-it") is False

        # Qwen3.5 still gets chat_template_kwargs for thinking toggle
        s = build_model_settings("together:Qwen/Qwen3.5-397B-A17B", thinking=False)
        assert s["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False

        # Gemma doesn't — just default max_tokens cap
        s = build_model_settings("together:google/gemma-4-31B-it")
        assert "extra_body" not in s
        assert s["max_tokens"] == 16384

    def test_non_together_model_passes_through_as_string(self):
        from subprime.core.config import build_model

        assert build_model("anthropic:claude-haiku-4-5") == "anthropic:claude-haiku-4-5"
        assert build_model("openai:gpt-4o-mini") == "openai:gpt-4o-mini"

    def test_api_key_is_secret_str(self, monkeypatch):
        """API key should be a SecretStr — not accidentally logged."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")

        from subprime.core.config import Settings

        s = Settings()
        # str() should mask the value
        assert "sk-secret" not in str(s.anthropic_api_key)
        # But get_secret_value reveals it
        assert s.anthropic_api_key.get_secret_value() == "sk-secret"
