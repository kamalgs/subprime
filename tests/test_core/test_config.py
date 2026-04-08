"""Tests for subprime.core.config — Settings via pydantic-settings.

Google-style small tests: fast, deterministic, no network calls.
"""

from __future__ import annotations

import os

import pytest


class TestSettings:
    def test_defaults(self, monkeypatch):
        """Settings should have sensible defaults for all non-secret fields."""
        # Ensure env var is set so construction doesn't fail
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-key-123")

        from subprime.core.config import Settings

        s = Settings()
        assert s.default_model == "claude-sonnet-4-6"
        assert s.mfdata_base_url == "https://api.mfdata.in"
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

    def test_api_key_is_secret_str(self, monkeypatch):
        """API key should be a SecretStr — not accidentally logged."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-secret")

        from subprime.core.config import Settings

        s = Settings()
        # str() should mask the value
        assert "sk-secret" not in str(s.anthropic_api_key)
        # But get_secret_value reveals it
        assert s.anthropic_api_key.get_secret_value() == "sk-secret"
