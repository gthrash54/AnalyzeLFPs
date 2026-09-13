"""The conversational layer, deterministic for now.

You describe what you want to look at; this proposes a recipe and parameters,
explains the tradeoffs, and says which guardrails will fire before anything runs.
It composes existing recipes and computes nothing itself, so every number it
leads to still carries a run record.

No model call and no network. Everything it knows comes from the manifest, the
recipe schemas, `configs/statistics.yaml`, and `configs/guardrails.yaml`. Nothing
about a recording leaves the machine. The interface is shaped so a model backend
can be swapped in later without changing what a caller sees.
"""

from __future__ import annotations

from .propose import Proposal, ProposedParameter, propose

__all__ = ["Proposal", "ProposedParameter", "propose"]
