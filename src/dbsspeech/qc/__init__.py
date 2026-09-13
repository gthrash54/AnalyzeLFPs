"""Quality control.

Detection proposes flags with evidence. A person decides. The gate refuses
analysis on anything not signed off, and lives in the package so every path
reaches it: CLI, API, agent, and a notebook.
"""

from __future__ import annotations

from .decisions import (
    ACTIVE,
    COLUMNS,
    REVIEWER_COLUMNS,
    STALE,
    append_history,
    decide,
    decide_many,
    load_decisions,
    merge_decisions,
    propose,
    qc_dir,
    read_history,
    save_decisions,
    select,
    undecided,
)
from .flags import DETECTORS, Flag, detect_all
from .gate import (
    APPROVED,
    IN_REVIEW,
    REOPENED,
    UNREVIEWED,
    QCNotApproved,
    applied_actions,
    has_been_reviewed,
    reopen,
    require_approved,
    sign,
    status,
)
from .report import Figure, ReportModel, build_model, render_html, write_report

__all__ = [
    "ACTIVE",
    "APPROVED",
    "COLUMNS",
    "DETECTORS",
    "IN_REVIEW",
    "REOPENED",
    "REVIEWER_COLUMNS",
    "STALE",
    "UNREVIEWED",
    "Figure",
    "Flag",
    "QCNotApproved",
    "ReportModel",
    "append_history",
    "applied_actions",
    "build_model",
    "decide",
    "decide_many",
    "detect_all",
    "has_been_reviewed",
    "load_decisions",
    "merge_decisions",
    "propose",
    "qc_dir",
    "read_history",
    "render_html",
    "reopen",
    "require_approved",
    "save_decisions",
    "select",
    "sign",
    "status",
    "undecided",
    "write_report",
]
