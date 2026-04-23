"""Advisor module — financial advisor agent, prompts, planning."""

from subprime.advisor.agent import create_advisor, create_strategy_advisor, load_prompt
from subprime.advisor.evaluator import PlanEvaluation, evaluate_plans
from subprime.advisor.perspectives import (
    PERSPECTIVES,
    Perspective,
    get_default_perspectives,
    get_perspective,
)
from subprime.advisor.planner import generate_plan, generate_strategy
from subprime.advisor.profile import gather_profile

__all__ = [
    "PERSPECTIVES",
    "Perspective",
    "PlanEvaluation",
    "create_advisor",
    "create_strategy_advisor",
    "evaluate_plans",
    "gather_profile",
    "generate_plan",
    "generate_strategy",
    "get_default_perspectives",
    "get_perspective",
    "load_prompt",
]
