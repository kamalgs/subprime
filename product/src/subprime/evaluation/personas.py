"""Persona bank — load investor profiles from the JSON fixture."""

from __future__ import annotations

import json
from pathlib import Path

from subprime.core.models import InvestorProfile

_DEFAULT_BANK = Path(__file__).parent / "personas" / "bank.json"


def load_personas(path: Path | None = None) -> list[InvestorProfile]:
    """Load all investor personas from the bank JSON file.

    Args:
        path: Optional path to a custom bank.json. Defaults to the
              bundled personas/bank.json.

    Returns:
        A list of validated InvestorProfile instances.

    Raises:
        FileNotFoundError: If the bank file does not exist.
    """
    bank_path = path or _DEFAULT_BANK
    raw = json.loads(bank_path.read_text())
    return [InvestorProfile(**entry) for entry in raw]


def get_persona(persona_id: str, path: Path | None = None) -> InvestorProfile:
    """Load a single persona by ID.

    Args:
        persona_id: The persona identifier (e.g., "P01").
        path: Optional path to a custom bank.json.

    Returns:
        The matching InvestorProfile.

    Raises:
        ValueError: If no persona with the given ID is found.
    """
    personas = load_personas(path)
    for p in personas:
        if p.id == persona_id:
            return p
    raise ValueError(f"Persona '{persona_id}' not found. Available IDs: {[p.id for p in personas]}")
