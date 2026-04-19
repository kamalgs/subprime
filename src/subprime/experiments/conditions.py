"""Experiment conditions — baseline, Lynch-spiked, and Bogle-spiked.

Each Condition bundles a name, description, and prompt_hooks dict
that gets passed to the advisor agent to inject (or omit) a philosophy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@dataclass(frozen=True)
class Condition:
    """An experimental condition for the subprime experiment."""

    name: str
    description: str
    prompt_hooks: dict[str, str] = field(default_factory=dict)


def _load_philosophy(name: str) -> str:
    """Read a philosophy prompt from experiments/prompts/{name}.md.

    Args:
        name: Philosophy file name without extension (e.g. "lynch", "bogle").

    Returns:
        The philosophy prompt content, stripped of surrounding whitespace.

    Raises:
        FileNotFoundError: If the prompt file does not exist.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Philosophy prompt not found: {path}")
    return path.read_text().strip()


# ---------------------------------------------------------------------------
# Pre-built conditions
# ---------------------------------------------------------------------------

BASELINE = Condition(
    name="baseline",
    description="Neutral advisor — no philosophy contamination (prime baseline)",
    prompt_hooks={},
)

LYNCH = Condition(
    name="lynch",
    description="Spiked with Peter Lynch's active stock-picking philosophy",
    prompt_hooks={"philosophy": _load_philosophy("lynch")},
)

BOGLE = Condition(
    name="bogle",
    description="Spiked with John Bogle's passive index-investing philosophy",
    prompt_hooks={"philosophy": _load_philosophy("bogle")},
)

LYNCH_MILD = Condition(
    name="lynch_mild",
    description="Mild active-investing nudge — hedged suggestions toward stock-picking",
    prompt_hooks={"philosophy": _load_philosophy("lynch_mild")},
)

LYNCH_HARD = Condition(
    name="lynch_hard",
    description="Hard active-investing push — imperative directives with explicit passive rejection",
    prompt_hooks={"philosophy": _load_philosophy("lynch_hard")},
)

BOGLE_MILD = Condition(
    name="bogle_mild",
    description="Mild passive-investing nudge — hedged suggestions toward index funds",
    prompt_hooks={"philosophy": _load_philosophy("bogle_mild")},
)

BOGLE_HARD = Condition(
    name="bogle_hard",
    description="Hard passive-investing push — imperative directives with explicit active rejection",
    prompt_hooks={"philosophy": _load_philosophy("bogle_hard")},
)

BOGLE_NOFUNDS = Condition(
    name="bogle_nofunds",
    description="Bogle philosophy without specific fund name examples — control for fund-name specificity",
    prompt_hooks={"philosophy": _load_philosophy("bogle_nofunds")},
)

CONDITIONS: list[Condition] = [BASELINE, LYNCH_MILD, LYNCH, LYNCH_HARD, BOGLE_MILD, BOGLE, BOGLE_HARD, BOGLE_NOFUNDS]

_CONDITIONS_MAP: dict[str, Condition] = {c.name: c for c in CONDITIONS}


def get_condition(name: str) -> Condition:
    """Look up a condition by name.

    Args:
        name: The condition name ("baseline", "lynch", or "bogle").

    Returns:
        The matching Condition instance.

    Raises:
        ValueError: If no condition with the given name exists.
    """
    if name not in _CONDITIONS_MAP:
        available = list(_CONDITIONS_MAP.keys())
        raise ValueError(
            f"Unknown condition '{name}'. Available conditions: {available}"
        )
    return _CONDITIONS_MAP[name]
