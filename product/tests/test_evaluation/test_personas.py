"""Tests for persona bank loading."""

from __future__ import annotations

import pytest

from subprime.core.models import InvestorProfile


# ---------------------------------------------------------------------------
# load_personas
# ---------------------------------------------------------------------------


class TestLoadPersonas:
    def test_returns_list(self):
        from subprime.evaluation.personas import load_personas

        personas = load_personas()
        assert isinstance(personas, list)

    def test_returns_twenty_five_personas(self):
        from subprime.evaluation.personas import load_personas

        personas = load_personas()
        assert len(personas) == 25

    def test_all_are_investor_profiles(self):
        from subprime.evaluation.personas import load_personas

        personas = load_personas()
        for p in personas:
            assert isinstance(p, InvestorProfile), f"{p} is not InvestorProfile"

    def test_ids_include_p01_through_p25(self):
        from subprime.evaluation.personas import load_personas

        personas = load_personas()
        ids = {p.id for p in personas}
        assert {"P01", "P02", "P03", "P04", "P05"}.issubset(ids)
        assert len(ids) == 25

    def test_p01_is_tony_stark(self):
        from subprime.evaluation.personas import load_personas

        personas = load_personas()
        p01 = [p for p in personas if p.id == "P01"][0]
        assert p01.name == "Tony Stark"
        assert p01.age == 25
        assert p01.risk_appetite == "aggressive"
        assert p01.investment_horizon_years == 30
        assert p01.monthly_investible_surplus_inr == 50000

    def test_p02_is_hermione_granger(self):
        from subprime.evaluation.personas import load_personas

        personas = load_personas()
        p02 = [p for p in personas if p.id == "P02"][0]
        assert p02.name == "Hermione Granger"
        assert p02.age == 35
        assert p02.risk_appetite == "moderate"

    def test_p04_is_conservative(self):
        from subprime.evaluation.personas import load_personas

        personas = load_personas()
        p04 = [p for p in personas if p.id == "P04"][0]
        assert p04.risk_appetite == "conservative"


# ---------------------------------------------------------------------------
# get_persona
# ---------------------------------------------------------------------------


class TestGetPersona:
    def test_returns_investor_profile(self):
        from subprime.evaluation.personas import get_persona

        p = get_persona("P01")
        assert isinstance(p, InvestorProfile)

    def test_p01_is_tony(self):
        from subprime.evaluation.personas import get_persona

        p = get_persona("P01")
        assert p.name == "Tony Stark"

    def test_p05_is_gordon(self):
        from subprime.evaluation.personas import get_persona

        p = get_persona("P05")
        assert p.name == "Gordon Gekko"

    def test_invalid_id_raises_value_error(self):
        from subprime.evaluation.personas import get_persona

        with pytest.raises(ValueError, match="INVALID"):
            get_persona("INVALID")

    def test_empty_id_raises_value_error(self):
        from subprime.evaluation.personas import get_persona

        with pytest.raises(ValueError):
            get_persona("")
