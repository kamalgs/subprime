"""Unit tests for finetuning.personas_gen."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from subprime.core.models import InvestorProfile
from subprime.finetuning.personas_gen import generate_personas


def _profile(idx: int) -> InvestorProfile:
    return InvestorProfile(
        id=f"G{idx:03d}",
        name=f"Persona {idx}",
        age=30 + idx,
        risk_appetite="moderate",
        investment_horizon_years=15,
        monthly_investible_surplus_inr=50_000,
        existing_corpus_inr=500_000,
        liabilities_inr=0,
        financial_goals=["retirement"],
        life_stage="mid_career",
        tax_bracket="30%",
    )


@pytest.mark.asyncio
async def test_generate_personas_happy_path() -> None:
    fake_rows = [_profile(1), _profile(2), _profile(3)]

    class _Result:
        output = fake_rows

    fake_run = AsyncMock(return_value=_Result())
    with patch("subprime.finetuning.personas_gen.Agent") as MockAgent:
        MockAgent.return_value.run = fake_run
        out = await generate_personas(3, model="anthropic:test")

    assert len(out) == 3
    assert all(isinstance(p, InvestorProfile) for p in out)
    assert [p.id for p in out] == ["G001", "G002", "G003"]
    fake_run.assert_awaited_once()
