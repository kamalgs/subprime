"""Tests for the OpenRouter balance-error auto-fallback wrapper."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from subprime.advisor._fallback import _is_or_balance_error, run_with_or_fallback


def test_is_or_balance_error_recognises_402() -> None:
    class _E(Exception):
        pass

    assert _is_or_balance_error(_E("status_code: 402, body: {}")) is True
    assert _is_or_balance_error(_E("Payment Required")) is True
    assert _is_or_balance_error(_E("Insufficient credits")) is True
    assert _is_or_balance_error(_E("You have no credits remaining")) is True


def test_is_or_balance_error_ignores_other_failures() -> None:
    class _E(Exception):
        pass

    assert _is_or_balance_error(_E("rate limit exceeded")) is False
    assert _is_or_balance_error(_E("connection reset")) is False
    assert _is_or_balance_error(_E("validation error")) is False


@pytest.mark.asyncio
async def test_fallback_used_on_balance_error(monkeypatch) -> None:
    """On 402, factory is called twice: once with primary, once with fallback."""

    monkeypatch.setattr(
        "subprime.flags.get_value",
        AsyncMock(return_value="openrouter:anthropic/claude-haiku-4.5"),
    )

    primary_agent = AsyncMock()
    primary_agent.run = AsyncMock(side_effect=Exception("status_code: 402"))
    fallback_agent = AsyncMock()
    fallback_agent.run = AsyncMock(return_value="ok")

    seen: list[str] = []

    def factory(model: str):
        seen.append(model)
        return primary_agent if "primary" in model else fallback_agent

    out = await run_with_or_fallback(factory, "primary-model", "hello")

    assert out == "ok"
    assert seen == ["primary-model", "openrouter:anthropic/claude-haiku-4.5"]
    primary_agent.run.assert_awaited_once_with("hello")
    fallback_agent.run.assert_awaited_once_with("hello")


@pytest.mark.asyncio
async def test_no_fallback_when_flag_unset(monkeypatch) -> None:
    """If advisor_model_fallback is empty, the original error re-raises."""

    monkeypatch.setattr("subprime.flags.get_value", AsyncMock(return_value=None))

    primary_agent = AsyncMock()
    primary_agent.run = AsyncMock(side_effect=Exception("Insufficient credits"))

    with pytest.raises(Exception, match="Insufficient credits"):
        await run_with_or_fallback(lambda m: primary_agent, "primary", "x")


@pytest.mark.asyncio
async def test_non_balance_error_not_retried(monkeypatch) -> None:
    """Network / validation errors must propagate immediately (no fallback call)."""

    monkeypatch.setattr(
        "subprime.flags.get_value",
        AsyncMock(return_value="should-not-be-called"),
    )
    primary_agent = AsyncMock()
    primary_agent.run = AsyncMock(side_effect=Exception("connection reset"))

    seen: list[str] = []

    def factory(model: str):
        seen.append(model)
        return primary_agent

    with pytest.raises(Exception, match="connection reset"):
        await run_with_or_fallback(factory, "primary", "x")
    assert seen == ["primary"], "fallback factory must not be invoked"
