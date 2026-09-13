"""Readers. The only place in the package that touches raw acquisition files."""

from __future__ import annotations

# Imported for the side effect: importing a reader registers it.
from . import brainvision, edf, tdt_mat, tdt_tank  # noqa: F401
from .base import (
    DEFAULT_PRIVACY_POLICY,
    EpochSeries,
    PrivacyPolicy,
    Recording,
    StreamInfo,
    all_entry_suffixes,
    available_formats,
    entry_suffixes,
    filenames_deidentified_for,
    open_recording,
    register_reader,
)

__all__ = [
    "DEFAULT_PRIVACY_POLICY",
    "EpochSeries",
    "PrivacyPolicy",
    "Recording",
    "StreamInfo",
    "all_entry_suffixes",
    "available_formats",
    "entry_suffixes",
    "filenames_deidentified_for",
    "open_recording",
    "register_reader",
]
