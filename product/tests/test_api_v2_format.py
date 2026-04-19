"""Tests for the plan-text prose formatter."""
from apps.web.api_v2._format import format_as_bullets


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


def test_short_newline_separated_lines_preserved():
    text = "Line one is brief.\nLine two also.\nLine three fits."
    assert format_as_bullets(text) == text


def test_idempotent_on_reformatted_text():
    text = "Alpha beta gamma. Delta epsilon zeta. Eta theta iota."
    once = format_as_bullets(text)
    twice = format_as_bullets(once)
    assert once == twice
