"""Tests for evaluation criteria — structured APS and PQS dimension definitions."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# APS_CRITERIA
# ---------------------------------------------------------------------------


class TestAPSCriteria:
    def test_has_exactly_six_dimensions(self):
        from subprime.evaluation.criteria import APS_CRITERIA

        assert len(APS_CRITERIA) == 6

    def test_dimension_names(self):
        from subprime.evaluation.criteria import APS_CRITERIA

        expected = {
            "passive_instrument_fraction",
            "turnover_score",
            "cost_emphasis_score",
            "research_vs_cost_score",
            "time_horizon_alignment_score",
            "portfolio_activeness_score",
        }
        assert set(APS_CRITERIA.keys()) == expected

    def test_each_dimension_has_required_keys(self):
        from subprime.evaluation.criteria import APS_CRITERIA

        required_keys = {"description", "anchor_0", "anchor_1"}
        for name, dim in APS_CRITERIA.items():
            assert required_keys.issubset(set(dim.keys())), (
                f"APS dimension '{name}' missing keys: {required_keys - set(dim.keys())}"
            )

    def test_all_values_are_nonempty_strings(self):
        from subprime.evaluation.criteria import APS_CRITERIA

        for name, dim in APS_CRITERIA.items():
            for key in ("description", "anchor_0", "anchor_1"):
                assert isinstance(dim[key], str), f"APS_CRITERIA['{name}']['{key}'] is not a string"
                assert len(dim[key].strip()) > 0, f"APS_CRITERIA['{name}']['{key}'] is empty"

    def test_anchor_0_describes_active_end(self):
        """anchor_0 should describe the 0.0 / active end of each dimension."""
        from subprime.evaluation.criteria import APS_CRITERIA

        # Spot-check: passive_instrument_fraction anchor_0 should mention active
        anchor = APS_CRITERIA["passive_instrument_fraction"]["anchor_0"].lower()
        assert "active" in anchor or "individual" in anchor or "stock" in anchor

    def test_anchor_1_describes_passive_end(self):
        """anchor_1 should describe the 1.0 / passive end of each dimension."""
        from subprime.evaluation.criteria import APS_CRITERIA

        anchor = APS_CRITERIA["passive_instrument_fraction"]["anchor_1"].lower()
        assert "passive" in anchor or "index" in anchor


# ---------------------------------------------------------------------------
# PQS_CRITERIA
# ---------------------------------------------------------------------------


class TestPQSCriteria:
    def test_has_exactly_five_dimensions(self):
        from subprime.evaluation.criteria import PQS_CRITERIA

        assert len(PQS_CRITERIA) == 5

    def test_dimension_names(self):
        from subprime.evaluation.criteria import PQS_CRITERIA

        expected = {
            "goal_alignment",
            "diversification",
            "risk_return_appropriateness",
            "internal_consistency",
            "tax_efficiency",
        }
        assert set(PQS_CRITERIA.keys()) == expected

    def test_each_dimension_has_required_keys(self):
        from subprime.evaluation.criteria import PQS_CRITERIA

        required_keys = {"description", "anchor_0", "anchor_1"}
        for name, dim in PQS_CRITERIA.items():
            assert required_keys.issubset(set(dim.keys())), (
                f"PQS dimension '{name}' missing keys: {required_keys - set(dim.keys())}"
            )

    def test_all_values_are_nonempty_strings(self):
        from subprime.evaluation.criteria import PQS_CRITERIA

        for name, dim in PQS_CRITERIA.items():
            for key in ("description", "anchor_0", "anchor_1"):
                assert isinstance(dim[key], str), f"PQS_CRITERIA['{name}']['{key}'] is not a string"
                assert len(dim[key].strip()) > 0, f"PQS_CRITERIA['{name}']['{key}'] is empty"
