"""Editing configuration safely, with history.

Config over code only helps if a non-coder can change config. That means editing
`configs/*.yaml` from the interface, which in turn means three things the file
system does not give you: validation before a bad value reaches a run, a history
so a change can be explained later, and a guarantee that changing a threshold
does not silently rewrite the past.

The third is the important one. Editing a QC threshold must not retroactively
change an approved subject: approval certifies a specific set of judgments, and
those judgments were made against the numbers as they were. New values apply to
future runs and future QC proposals only, and the interface says so.
"""

from __future__ import annotations

from .store import (
    ConfigError,
    diff_versions,
    list_configs,
    list_versions,
    read_config,
    read_version,
    validate_config,
    write_config,
)

__all__ = [
    "ConfigError",
    "diff_versions",
    "list_configs",
    "list_versions",
    "read_config",
    "read_version",
    "validate_config",
    "write_config",
]
