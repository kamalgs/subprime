"""Auto-fallback wrapper for OpenRouter balance errors.

When OpenRouter returns a 402 (insufficient credits), retry the same
prompt with a different model fetched from the ``advisor_model_fallback``
feature flag. Typical use: prod runs on cheap-but-OR-billed Mimo /
DeepSeek; fallback flag is set to a BYOK model (e.g. Haiku via the
user's Anthropic key) so the app keeps working when OR credits run dry.

Only OR balance errors are retried — other exceptions (network, bad
output, rate limit) bubble up unchanged so we don't mask real bugs.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


def _is_or_balance_error(exc: Exception) -> bool:
    """True when *exc* looks like an OpenRouter insufficient-credits error.

    OR returns 402 with messages like ``"Insufficient credits"`` or
    ``"You have no credits remaining"``. We match on either the status
    code or those phrases to be robust against minor wording changes.
    """
    msg = str(exc).lower()
    if "402" in msg:
        return True
    return any(
        phrase in msg
        for phrase in (
            "insufficient credit",
            "no credits",
            "out of credit",
            "payment required",
        )
    )


async def run_with_or_fallback(
    factory: Callable[[str], Any],
    primary_model: str,
    prompt: str,
) -> Any:
    """Run an Agent; on OR insufficient-balance, retry with fallback model.

    ``factory(model)`` must return a configured Agent. The function calls
    ``await agent.run(prompt)`` and returns whatever that returns. On a
    balance error, looks up ``advisor_model_fallback`` from the flags
    module and retries once with that model.
    """
    agent = factory(primary_model)
    try:
        return await agent.run(prompt)
    except Exception as e:
        if not _is_or_balance_error(e):
            raise
        try:
            from subprime.flags import get_value

            fallback = await get_value("advisor_model_fallback", default=None)
        except Exception:
            logger.exception("flag lookup for advisor_model_fallback failed")
            fallback = None
        if not fallback or not isinstance(fallback, str):
            logger.warning("OR balance error and no advisor_model_fallback configured — re-raising")
            raise
        logger.warning(
            "OR balance error on %s — falling back to %s",
            primary_model,
            fallback,
        )
        return await factory(fallback).run(prompt)


async def run_factory_with_or_fallback(
    runner: Callable[[str], Awaitable[Any]],
    primary_model: str,
) -> Any:
    """Variant of run_with_or_fallback when the prompt is closed over.

    ``runner(model)`` is an async callable that builds the agent + runs
    it with whatever prompt the caller wants. Use when the prompt isn't
    a single string (e.g. multi-part user message construction).
    """
    try:
        return await runner(primary_model)
    except Exception as e:
        if not _is_or_balance_error(e):
            raise
        try:
            from subprime.flags import get_value

            fallback = await get_value("advisor_model_fallback", default=None)
        except Exception:
            logger.exception("flag lookup for advisor_model_fallback failed")
            fallback = None
        if not fallback or not isinstance(fallback, str):
            logger.warning("OR balance error and no advisor_model_fallback configured — re-raising")
            raise
        logger.warning(
            "OR balance error on %s — falling back to %s",
            primary_model,
            fallback,
        )
        return await runner(fallback)
