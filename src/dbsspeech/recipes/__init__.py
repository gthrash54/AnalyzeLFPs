"""Registered analyses.

A recipe is declared once with a typed parameter model and becomes callable from
Python, the CLI, the API, and the agent. `registry.run` is the only sanctioned
entry point: it evaluates guardrails before anything is computed, opens a run
record, and writes the outputs. Calling a recipe function directly bypasses both
provenance and the gate.

Registered: `psd_by_condition`, `bandpower_contrast`, `tfr_onset`,
`pynm_features`, `erna`, `pac_modulation_index`, `erp_epochs`.
"""

from __future__ import annotations

# Importing a recipe module registers it.
from . import bandpower, erna, erp, pac, psd, pynm, tfr  # noqa: F401
from .registry import (
    Recipe,
    RecipeContext,
    RecipeResult,
    available,
    describe_all,
    get,
    recipe,
    run,
)

__all__ = [
    "Recipe",
    "RecipeContext",
    "RecipeResult",
    "available",
    "describe_all",
    "get",
    "recipe",
    "run",
]
