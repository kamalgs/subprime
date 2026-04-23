"""Tests for the fund display-name generator."""

from subprime.data.display_names import generate_display_name


def test_strips_direct_growth_plan_option():
    got = generate_display_name(
        "HDFC Index Fund - NIFTY 50 Plan - Direct Plan - Growth Option",
        amc="HDFC Mutual Fund",
    )
    # Order/case may vary slightly — check that key tokens survive and noise is gone
    lower = got.lower()
    assert "hdfc" in lower and "nifty" in lower and "50" in lower and "index" in lower
    for noise in ("direct", "plan", "growth", "option", "fund"):
        assert noise not in lower


def test_preserves_flexi_cap_category():
    got = generate_display_name(
        "Parag Parikh Flexi Cap Fund - Direct Plan - Growth",
        amc="Parag Parikh",
    )
    assert got == "Parag Parikh Flexi Cap"


def test_strips_idcw_and_regular():
    got = generate_display_name("Axis Bluechip Fund Regular IDCW", amc="Axis")
    assert got == "Axis Bluechip"


def test_prepends_amc_when_missing():
    got = generate_display_name("Bluechip Fund Direct Growth", amc="Axis Mutual Fund")
    assert got.startswith("Axis")


def test_preserves_numeric_tokens():
    got = generate_display_name("UTI Nifty 50 Index Fund Direct Growth", amc="UTI")
    assert "50" in got
    assert "Nifty" in got
    assert "Direct" not in got
    assert "Growth" not in got


def test_empty_input_returns_empty():
    assert generate_display_name("", amc="HDFC") == ""


def test_truncates_long_names():
    long = "Very Long Fund Name That Keeps Going And Going Forever Fund Direct"
    got = generate_display_name(long, amc="Axis", max_len=20)
    assert len(got) <= 20
    assert got.endswith("…") or len(got) <= 20


def test_fallback_returns_original_if_stripping_empties():
    got = generate_display_name("Direct Growth Plan Option Fund")
    # All-noise input: returns original rather than empty string
    assert got
