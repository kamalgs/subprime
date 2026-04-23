"""Tests for the perspectives module."""

from __future__ import annotations

import pytest

from subprime.advisor.perspectives import (
    PERSPECTIVES,
    Perspective,
    get_default_perspectives,
    get_perspective,
)


def test_perspectives_has_five_entries():
    assert len(PERSPECTIVES) == 5


def test_get_perspective_by_name():
    p = get_perspective("balanced")
    assert isinstance(p, Perspective)
    assert p.name == "balanced"


def test_get_perspective_unknown_raises():
    with pytest.raises(ValueError, match="Unknown perspective"):
        get_perspective("nonexistent_perspective")


def test_get_default_perspectives_three():
    perspectives = get_default_perspectives(3)
    assert len(perspectives) == 3
    names = [p.name for p in perspectives]
    assert names == ["balanced", "growth", "defensive"]


def test_get_default_perspectives_five():
    perspectives = get_default_perspectives(5)
    assert len(perspectives) == 5
    names = [p.name for p in perspectives]
    assert names == ["balanced", "growth", "defensive", "goal_based", "tax_optimised"]


def test_each_perspective_has_nonempty_fields():
    for p in PERSPECTIVES:
        assert p.name, f"Perspective has empty name: {p}"
        assert p.description, f"Perspective {p.name} has empty description"
        assert p.prompt, f"Perspective {p.name} has empty prompt"


def test_perspective_names_are_unique():
    names = [p.name for p in PERSPECTIVES]
    assert len(names) == len(set(names)), "Perspective names must be unique"


def test_all_perspectives_retrievable():
    for p in PERSPECTIVES:
        retrieved = get_perspective(p.name)
        assert retrieved is p
