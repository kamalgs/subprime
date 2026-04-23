"""Tests for the plan-text prose formatter."""

from apps.web.api_v2._format import (
    format_as_bullets,
    format_plan_prose,
    normalize_list_item,
)


def test_wall_of_text_becomes_bulleted():
    text = (
        "This plan is built for long-term wealth creation. It allocates "
        "70% to equity for growth and 20% to debt for stability. Gold at "
        "10% hedges inflation risk over decades. The funds selected have "
        "low expense ratios and consistent returns."
    )
    got = format_as_bullets(text)
    assert got.startswith("- ")
    assert got.count("\n-") >= 2
    assert "long-term wealth creation" in got


def test_preserves_existing_markdown_bullets():
    text = "- First point\n- Second point\n- Third point"
    assert format_as_bullets(text) == text


def test_preserves_numbered_list():
    text = "1. Open account on Groww\n2. Start SIP\n3. Review yearly"
    assert format_as_bullets(text) == text


def test_preserves_headings():
    text = "## Section\nParagraph here."
    assert format_as_bullets(text) == text


def test_single_sentence_left_alone():
    text = "A short statement."
    assert format_as_bullets(text) == text


def test_empty_input_returns_empty():
    assert format_as_bullets("") == ""


def test_short_newline_separated_lines_are_bulleted():
    """Previously preserved as-is; tightened heuristic now always bullets
    multi-sentence prose (newlines alone collapse to <br> in Prose and
    still read as a wall)."""
    text = "Line one is brief.\nLine two also.\nLine three fits."
    out = format_as_bullets(text)
    assert out.startswith("- ")
    assert out.count("\n- ") == 2


def test_idempotent_on_reformatted_text():
    text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
    once = format_as_bullets(text)
    twice = format_as_bullets(once)
    assert once == twice


# ── normalize_list_item + format_plan_prose ───────────────────────────────────


def test_normalize_strips_leading_dash():
    assert normalize_list_item("- Market volatility") == "Market volatility"


def test_normalize_strips_leading_asterisk_and_number():
    assert normalize_list_item("* Concentration risk") == "Concentration risk"
    assert normalize_list_item("1. Tax impact") == "Tax impact"
    assert normalize_list_item("1) Foreign allocation") == "Foreign allocation"


def test_normalize_collapses_internal_newlines():
    assert (
        normalize_list_item("Stock markets drop.\nYour value goes down.")
        == "Stock markets drop. Your value goes down."
    )


def test_normalize_preserves_plain_text():
    assert normalize_list_item("Stock markets can drop 20-30%") == "Stock markets can drop 20-30%"


def test_normalize_empty_or_none_safe():
    assert normalize_list_item("") == ""
    assert normalize_list_item(None) is None  # type: ignore[arg-type]


class _FakePlan:
    """Duck-typed plan used in prose-format tests — avoids importing Pydantic."""

    def __init__(self, **kw):
        self.rationale = kw.get("rationale", "")
        self.setup_phase = kw.get("setup_phase", "")
        self.rebalancing_guidelines = kw.get("rebalancing_guidelines", "")
        self.risks = kw.get("risks", [])
        self.review_checkpoints = kw.get("review_checkpoints", [])
        self.allocations = kw.get("allocations", [])


def test_format_plan_prose_strips_double_bullets_from_list_items():
    """Each risk item must not contain a leading bullet marker after
    format_plan_prose — otherwise the frontend <li><Prose/></li> renders
    a nested bullet."""
    plan = _FakePlan(
        risks=[
            "- Market volatility can push the portfolio down 20-30% in a bad year.",
            "* Concentration in equity means slower recovery if markets stay flat.",
        ],
        review_checkpoints=[
            "1. Year 3: switch small-cap fund if it underperforms category by >3%.",
        ],
    )
    format_plan_prose(plan)
    for item in plan.risks + plan.review_checkpoints:
        assert not item.lstrip().startswith(("-", "*", "+", "•"))
        assert not item.lstrip()[:3].startswith(("1.", "1)"))
