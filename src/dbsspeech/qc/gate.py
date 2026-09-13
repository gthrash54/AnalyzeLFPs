"""The approval gate: no analysis on unreviewed data.

The most valuable line in the system, because it is the one that cannot be
forgotten. It lives in the package, so every path reaches it: the CLI, the API,
the agent, and a lab member poking at the package in a notebook. The interface
reflects the gate; it never reimplements it.

Status is derived, never stored as a field someone can set:

    unreviewed  no decisions file exists
    in_review   decisions exist, some active flag is undecided
    approved    every active flag is decided, and a signature covers the exact
                decisions file that is on disk right now
    reopened    a signature exists but no longer matches the decisions file, or
                the last history event was a reopen

The signature carries a hash of the decisions file. Editing a decision after
signing therefore invalidates the approval automatically, which is the property
that makes an approval mean something: it certifies a specific set of judgments,
not a subject.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .decisions import (
    ACTIVE,
    append_history,
    load_decisions,
    qc_dir,
    read_history,
)

UNREVIEWED = "unreviewed"
IN_REVIEW = "in_review"
APPROVED = "approved"
REOPENED = "reopened"


class QCNotApproved(Exception):
    """Raised when analysis is attempted on data that is not signed off."""

    def __init__(self, study_id: str, status: str, detail: str = "") -> None:
        self.study_id = study_id
        self.status = status
        message = (
            f"{study_id} is {status}, so it cannot be analyzed yet. "
            f"{detail}".strip()
        )
        super().__init__(message)


def _decisions_path(study_id: str, derivatives_dir: Path) -> Path:
    return qc_dir(study_id, derivatives_dir) / "decisions.tsv"


def _approval_path(study_id: str, derivatives_dir: Path) -> Path:
    return qc_dir(study_id, derivatives_dir) / "approval.json"


def decisions_digest(study_id: str, derivatives_dir: Path) -> str | None:
    path = _decisions_path(study_id, derivatives_dir)
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_approval(study_id: str, derivatives_dir: Path) -> dict[str, Any] | None:
    path = _approval_path(study_id, derivatives_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError:
        return None


def has_been_reviewed(study_id: str, derivatives_dir: Path) -> bool:
    """Whether detection has run, regardless of whether it found anything.

    A decisions file with no rows means a clean recording, which is reviewable
    and signable. Treating that as `unreviewed` would make a clean subject
    impossible to approve.
    """
    return _decisions_path(study_id, derivatives_dir).exists()


def status(study_id: str, derivatives_dir: Path) -> str:
    """Derive the current status. Never reads a stored status field."""
    if not has_been_reviewed(study_id, derivatives_dir):
        return UNREVIEWED

    history = read_history(study_id, derivatives_dir)
    approval = load_approval(study_id, derivatives_dir)

    if approval is not None:
        if approval.get("decisions_sha256") != decisions_digest(study_id, derivatives_dir):
            # The decisions changed after signing, so the signature no longer
            # covers what is on disk.
            return REOPENED
        for event in reversed(history):
            if event.get("event") in {"sign", "reopen"}:
                return REOPENED if event["event"] == "reopen" else APPROVED
        return APPROVED

    return IN_REVIEW


def undecided_rows(study_id: str, derivatives_dir: Path) -> list[dict[str, str]]:
    return [
        r
        for r in load_decisions(study_id, derivatives_dir)
        if r.get("status", ACTIVE) == ACTIVE and not (r.get("approved") or "").strip()
    ]


def sign(study_id: str, reviewer: str, derivatives_dir: Path) -> dict[str, Any]:
    """Sign off a subject. Refuses while any active flag is undecided."""
    if not has_been_reviewed(study_id, derivatives_dir):
        raise QCNotApproved(
            study_id, UNREVIEWED,
            "There is nothing to sign: run QC detection first.",
        )
    rows = load_decisions(study_id, derivatives_dir)
    pending = undecided_rows(study_id, derivatives_dir)
    if pending:
        raise QCNotApproved(
            study_id, IN_REVIEW,
            f"{len(pending)} flag(s) are still undecided: "
            f"{', '.join(sorted(r['flag_id'] for r in pending)[:5])}"
            f"{' and more' if len(pending) > 5 else ''}.",
        )
    if not reviewer.strip():
        raise ValueError("a signature needs a reviewer: an anonymous approval is not one")

    active = [r for r in rows if r.get("status", ACTIVE) == ACTIVE]
    approval = {
        "study_id": study_id,
        "reviewer": reviewer,
        "decisions_sha256": decisions_digest(study_id, derivatives_dir),
        "n_flags": len(active),
        "n_approved": sum(1 for r in active if (r.get("approved") or "").lower() == "true"),
    }
    path = _approval_path(study_id, derivatives_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(approval, indent=2))
    append_history(study_id, derivatives_dir, "sign", reviewer,
                   decisions_sha256=approval["decisions_sha256"],
                   n_flags=approval["n_flags"])
    return approval


def reopen(study_id: str, reviewer: str, reason: str, derivatives_dir: Path) -> None:
    """Reopen a signed subject. Data gets re-inspected; that must be logged."""
    if not reason.strip():
        raise ValueError(
            "reopening requires a reason: the history is what explains why a "
            "signed subject was reconsidered"
        )
    append_history(study_id, derivatives_dir, "reopen", reviewer, reason=reason)


def require_approved(study_id: str, derivatives_dir: Path) -> None:
    """Raise unless `study_id` is approved. The gate itself."""
    current = status(study_id, derivatives_dir)
    if current == APPROVED:
        return
    detail = {
        UNREVIEWED: "Run QC detection, review the flags, then sign.",
        IN_REVIEW: "Some flags are still undecided. Finish the review, then sign.",
        REOPENED: "The decisions changed after signing, or it was reopened. Sign again.",
    }.get(current, "")
    raise QCNotApproved(study_id, current, detail)


def applied_actions(study_id: str, derivatives_dir: Path) -> list[dict[str, str]]:
    """The approved actions a loader should apply, for the run record."""
    return [
        {
            "flag_id": r["flag_id"],
            "target_type": r["target_type"],
            "target": r["target"],
            "flag_type": r["flag_type"],
            "action": r.get("action_taken") or r.get("proposed_action", ""),
            "reviewer": r.get("reviewer", ""),
        }
        for r in load_decisions(study_id, derivatives_dir)
        if r.get("status", ACTIVE) == ACTIVE
        and (r.get("approved") or "").lower() == "true"
        and (r.get("action_taken") or r.get("proposed_action"))
        not in ("", "none")
    ]
