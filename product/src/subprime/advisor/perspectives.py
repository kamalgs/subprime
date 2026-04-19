"""Investment perspectives for multi-agent plan generation.

Each perspective represents a distinct advisory viewpoint. Premium mode
generates a plan from each perspective, then an evaluator picks the best.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Perspective:
    """A named advisory perspective with a system prompt addition."""
    name: str
    description: str  # one-line for display
    prompt: str  # injected into the advisor system prompt


# The core perspectives — each gives genuinely different advice
PERSPECTIVES: list[Perspective] = [
    Perspective(
        name="balanced",
        description="Balanced approach — best fund in each asset class",
        prompt=(
            "## Your Perspective: Best-of-Breed Multi-Asset\n\n"
            "Pick the single best fund in each asset class. Focus on quality over quantity. "
            "A compact portfolio of 4-6 funds, each the best in its category. "
            "Include a SIP step-up plan (suggest 10% annual increase). "
            "Provide a year-by-year asset allocation schedule showing how the mix should "
            "evolve as the investor ages (e.g. reduce equity by 5% every 5 years after age 40)."
        ),
    ),
    Perspective(
        name="goal_based",
        description="Goal-based — dedicated funds for each financial goal",
        prompt=(
            "## Your Perspective: Horses for Courses (Goal-Based)\n\n"
            "Assign specific funds to specific goals. If the investor has retirement + "
            "child education + emergency, each goal gets its own allocation with funds "
            "matched to the goal's timeline. Shorter goals get safer funds. "
            "Include a SIP step-up plan and specific review milestones tied to each goal. "
            "Show how allocations should shift as each goal approaches."
        ),
    ),
    Perspective(
        name="growth",
        description="Growth tilt — maximise long-term wealth creation",
        prompt=(
            "## Your Perspective: Aggressive Growth\n\n"
            "Maximise long-term wealth creation. Overweight equity, especially mid-cap "
            "and small-cap for higher growth potential. Accept higher short-term swings "
            "for better long-term outcomes. Include a SIP step-up plan with aggressive "
            "annual increases (15%). Show a glide path that gradually reduces risk only "
            "in the last 5-7 years before the goal deadline."
        ),
    ),
    Perspective(
        name="defensive",
        description="Defensive — protect capital, steady growth",
        prompt=(
            "## Your Perspective: Capital Protection\n\n"
            "Prioritise capital protection and steady returns. Overweight large-cap, "
            "index funds, and debt. Minimise small-cap and sectoral exposure. "
            "Include a conservative SIP step-up (5% annual). "
            "The allocation schedule should maintain a safety buffer throughout — "
            "never more than 60% in stocks regardless of age. "
            "Highlight downside protection in bear scenarios."
        ),
    ),
    Perspective(
        name="tax_optimised",
        description="Tax-optimised — minimise tax drag across the portfolio",
        prompt=(
            "## Your Perspective: Tax-Efficient Investing\n\n"
            "Optimise for after-tax returns. Use ELSS for 80C benefits if on old regime. "
            "Prefer funds held for 1+ years to benefit from long-term capital gains treatment. "
            "Consider debt funds for 3+ year horizons for indexation benefits. "
            "Structure SIP amounts to maximise tax efficiency. "
            "Include a SIP step-up plan that accounts for annual tax planning. "
            "Show the estimated tax savings alongside the investment plan."
        ),
    ),
]


def get_perspective(name: str) -> Perspective:
    """Look up a perspective by name."""
    for p in PERSPECTIVES:
        if p.name == name:
            return p
    raise ValueError(f"Unknown perspective: {name}. Available: {[p.name for p in PERSPECTIVES]}")


def get_default_perspectives(n: int = 3) -> list[Perspective]:
    """Return the default set of perspectives for premium mode.

    Picks a balanced spread: balanced + growth + defensive for 3,
    adds goal_based and tax_optimised for 5.
    """
    order = ["balanced", "growth", "defensive", "goal_based", "tax_optimised"]
    return [get_perspective(name) for name in order[:n]]
