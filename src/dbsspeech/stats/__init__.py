"""Statistical normalization, with every choice explained."""

from __future__ import annotations

from .normalize import (
    CENTERS,
    SCALES,
    NormalizationChoice,
    describe_choice,
    load_options,
    normalize,
    options_for_schema,
)

__all__ = [
    "CENTERS",
    "SCALES",
    "NormalizationChoice",
    "describe_choice",
    "load_options",
    "normalize",
    "options_for_schema",
]
