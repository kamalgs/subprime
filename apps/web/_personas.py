"""Thin wrapper to import personas without triggering subprime.evaluation.__init__.

subprime.evaluation.__init__ imports judges.py which requires pydantic_ai.
In the web layer, we only need the persona bank (pure JSON/Pydantic).
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PERSONAS_PY = Path(__file__).resolve().parent.parent.parent / "src" / "subprime" / "evaluation" / "personas.py"


def _load_module():  # type: ignore[return]
    """Load personas.py without triggering evaluation/__init__.py."""
    import sys
    if "subprime.evaluation.personas" in sys.modules:
        return sys.modules["subprime.evaluation.personas"]
    spec = importlib.util.spec_from_file_location("subprime.evaluation.personas", _PERSONAS_PY)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["subprime.evaluation.personas"] = mod  # register before exec to handle circular refs
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


def load_personas():
    return _load_module().load_personas()


def get_persona(persona_id: str):
    return _load_module().get_persona(persona_id)
