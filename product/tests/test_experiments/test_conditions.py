"""Tests for experiment conditions — BASELINE, LYNCH, BOGLE constants and helpers."""

from __future__ import annotations

import pytest


class TestConditionConstants:
    """Verify the three condition constants exist and have correct properties."""

    def test_baseline_exists(self):
        from subprime.experiments.conditions import BASELINE

        assert BASELINE.name == "baseline"

    def test_baseline_has_empty_hooks(self):
        from subprime.experiments.conditions import BASELINE

        assert BASELINE.prompt_hooks == {}

    def test_baseline_has_description(self):
        from subprime.experiments.conditions import BASELINE

        assert len(BASELINE.description) > 0

    def test_lynch_exists(self):
        from subprime.experiments.conditions import LYNCH

        assert LYNCH.name == "lynch"

    def test_lynch_has_philosophy_hook(self):
        from subprime.experiments.conditions import LYNCH

        assert "philosophy" in LYNCH.prompt_hooks

    def test_lynch_philosophy_is_nontrivial(self):
        from subprime.experiments.conditions import LYNCH

        content = LYNCH.prompt_hooks["philosophy"]
        assert len(content) > 200, "Lynch philosophy prompt should be substantial"

    def test_lynch_philosophy_mentions_active(self):
        from subprime.experiments.conditions import LYNCH

        content = LYNCH.prompt_hooks["philosophy"].lower()
        assert "active" in content

    def test_bogle_exists(self):
        from subprime.experiments.conditions import BOGLE

        assert BOGLE.name == "bogle"

    def test_bogle_has_philosophy_hook(self):
        from subprime.experiments.conditions import BOGLE

        assert "philosophy" in BOGLE.prompt_hooks

    def test_bogle_philosophy_is_nontrivial(self):
        from subprime.experiments.conditions import BOGLE

        content = BOGLE.prompt_hooks["philosophy"]
        assert len(content) > 200, "Bogle philosophy prompt should be substantial"

    def test_bogle_philosophy_mentions_index(self):
        from subprime.experiments.conditions import BOGLE

        content = BOGLE.prompt_hooks["philosophy"].lower()
        assert "index" in content

    def test_conditions_list_includes_core_three(self):
        """CONDITIONS now bundles the core triad + dose-response variants
        added in M1.2. The core three must still be present; order is
        allowed to vary to accommodate new variants."""
        from subprime.experiments.conditions import CONDITIONS

        names = {c.name for c in CONDITIONS}
        assert {"baseline", "lynch", "bogle"}.issubset(names)
        # At least the three core + two mild + two hard + bogle_nofunds
        assert len(CONDITIONS) >= 3

    def test_conditions_list_starts_with_baseline(self):
        """Baseline should always be first so plotting and tables key off
        a stable anchor condition."""
        from subprime.experiments.conditions import CONDITIONS

        assert CONDITIONS[0].name == "baseline"


class TestGetCondition:
    """Test the get_condition lookup helper."""

    def test_get_baseline(self):
        from subprime.experiments.conditions import BASELINE, get_condition

        assert get_condition("baseline") is BASELINE

    def test_get_lynch(self):
        from subprime.experiments.conditions import LYNCH, get_condition

        assert get_condition("lynch") is LYNCH

    def test_get_bogle(self):
        from subprime.experiments.conditions import BOGLE, get_condition

        assert get_condition("bogle") is BOGLE

    def test_unknown_raises_value_error(self):
        from subprime.experiments.conditions import get_condition

        with pytest.raises(ValueError, match="Unknown condition"):
            get_condition("nonexistent")

    def test_unknown_raises_value_error_empty_string(self):
        from subprime.experiments.conditions import get_condition

        with pytest.raises(ValueError, match="Unknown condition"):
            get_condition("")
