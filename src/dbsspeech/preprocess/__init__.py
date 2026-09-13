"""Preprocessing: re-referencing and resampling.

Everything here is montage-aware, meaning it reads the lead geometry from
`configs/leads.yaml` rather than assuming a contact ordering. A lead with a
different geometry produces different derivations from the same code.
"""

from __future__ import annotations

from .reference import (
    Derivation,
    Montage,
    apply_montage,
    available_schemes,
    build_montage,
)
from .resample import (
    DEFAULT_CUTOFF_FRACTION,
    cutoff_fraction_from,
    decimate_stream,
    usable_bandwidth_hz,
)

__all__ = [
    "Derivation",
    "Montage",
    "apply_montage",
    "available_schemes",
    "build_montage",
    "DEFAULT_CUTOFF_FRACTION",
    "cutoff_fraction_from",
    "decimate_stream",
    "usable_bandwidth_hz",
]
