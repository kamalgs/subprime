"""Tests for interactive profile gathering."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from subprime.core.models import InvestorProfile


@pytest.fixture
def complete_profile():
    return InvestorProfile(
        id="interactive",
        name="Arjun Mehta",
        age=25,
        risk_appetite="aggressive",
        investment_horizon_years=30,
        monthly_investible_surplus_inr=50000,
        existing_corpus_inr=200000,
        liabilities_inr=0,
        financial_goals=["Retire by 55 with 10Cr corpus"],
        life_stage="Early career",
        tax_bracket="new_regime",
    )


@pytest.mark.asyncio
async def test_gather_profile_bulk_bypass(complete_profile):
    """If existing_profile is provided, return it immediately without calling send_message."""
    from subprime.advisor.profile import gather_profile

    async def mock_send(msg: str) -> str:
        raise AssertionError("send_message should not be called in bulk mode")

    result = await gather_profile(send_message=mock_send, existing_profile=complete_profile)
    assert result.name == "Arjun Mehta"
    assert result.age == 25


@pytest.mark.asyncio
async def test_gather_profile_bulk_returns_same_object(complete_profile):
    """Bulk mode should return the exact same profile object."""
    from subprime.advisor.profile import gather_profile

    result = await gather_profile(send_message=AsyncMock(), existing_profile=complete_profile)
    assert result is complete_profile


@pytest.mark.asyncio
async def test_gather_profile_interactive_calls_run_conversation(complete_profile):
    """Interactive mode delegates to _run_conversation."""
    from subprime.advisor.profile import gather_profile

    async def mock_send(msg: str) -> str:
        return "I'm 25, aggressive investor, 50k per month"

    with patch("subprime.advisor.profile._run_conversation") as mock_conv:
        mock_conv.return_value = ("conversation text", complete_profile)
        result = await gather_profile(send_message=mock_send)

    assert isinstance(result, InvestorProfile)
    assert result.name == "Arjun Mehta"
    mock_conv.assert_called_once()


@pytest.mark.asyncio
async def test_gather_profile_returns_investor_profile_type():
    """The return type must be InvestorProfile."""
    from subprime.advisor.profile import gather_profile

    profile = InvestorProfile(
        id="test",
        name="Test",
        age=30,
        risk_appetite="moderate",
        investment_horizon_years=10,
        monthly_investible_surplus_inr=10000,
        existing_corpus_inr=0,
        liabilities_inr=0,
        financial_goals=["Save"],
        life_stage="Mid career",
        tax_bracket="new_regime",
    )
    result = await gather_profile(send_message=AsyncMock(), existing_profile=profile)
    assert isinstance(result, InvestorProfile)
