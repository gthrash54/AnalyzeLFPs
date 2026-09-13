"""The decisions table: the versioned record of human judgment.

A flag is a proposal. A decision is a person's answer to it, with a reason and a
timestamp. They live in separate files because they have different lifetimes: a
flag is recomputed whenever detection runs, a decision is written once and must
survive every later run.

The merge is the whole point. Re-running detection must never overwrite what a
reviewer wrote. New flags are appended, decided flags keep their columns, and a
flag that no longer fires is marked `stale` rather than deleted, so the record
still shows that someone once judged it and what they said.

Files, per subject, under `derivatives/qc/sub-<study_id>/`:

    flags.json      what detection found this time, with full evidence
    decisions.tsv   one row per flag_id, carrying the reviewer's columns
    history.jsonl   append-only log of sign and reopen events
"""

from __future__ import annotations

import csv
import json
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .flags import Flag

# Written by detection, never by a reviewer.
DETECTED_COLUMNS = (
    "flag_id",
    "target_type",
    "target",
    "flag_type",
    "evidence_summary",
    "proposed_action",
    "severity",
    "status",
)

# Written by a reviewer, never by detection. The merge preserves these.
REVIEWER_COLUMNS = ("approved", "action_taken", "reviewer", "reviewed_at", "reason")

COLUMNS = DETECTED_COLUMNS + REVIEWER_COLUMNS

# A flag that stopped firing. Kept so the record shows it was once judged.
STALE = "stale"
ACTIVE = "active"


def qc_dir(study_id: str, derivatives_dir: Path) -> Path:
    return Path(derivatives_dir) / "qc" / f"sub-{study_id}"


def _summarize(evidence: dict[str, Any], limit: int = 200) -> str:
    """Evidence as one readable line for a spreadsheet."""
    parts = [f"{k}={v}" for k, v in evidence.items()]
    text = ", ".join(parts)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def write_flags(flags: list[Flag], study_id: str, derivatives_dir: Path) -> Path:
    """Write the full detection output, evidence included."""
    d = qc_dir(study_id, derivatives_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "flags.json"
    path.write_text(
        json.dumps(
            {
                "study_id": study_id,
                "detected_at": _now(),
                "n_flags": len(flags),
                "flags": [{"flag_id": f.flag_id, **asdict(f)} for f in flags],
            },
            indent=2,
            default=str,
        )
    )
    return path


def load_decisions(study_id: str, derivatives_dir: Path) -> list[dict[str, str]]:
    """Read the decisions table. Missing file reads as empty."""
    path = qc_dir(study_id, derivatives_dir) / "decisions.tsv"
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [dict(row) for row in csv.DictReader(f, delimiter="\t")]


def save_decisions(
    study_id: str, rows: list[dict[str, str]], derivatives_dir: Path
) -> Path:
    d = qc_dir(study_id, derivatives_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "decisions.tsv"
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, delimiter="\t",
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    return path


def merge_decisions(
    existing: list[dict[str, str]], flags: list[Flag]
) -> list[dict[str, str]]:
    """Fold a fresh detection into an existing table without losing judgment.

    Existing rows keep every reviewer column. Detected columns are refreshed,
    because evidence changes when thresholds or data change and a reviewer should
    see the current numbers. A row whose flag no longer fires becomes `stale`.
    """
    by_id = {row["flag_id"]: dict(row) for row in existing}
    seen: set[str] = set()
    merged: list[dict[str, str]] = []

    for flag in flags:
        fid = flag.flag_id
        seen.add(fid)
        detected = {
            "flag_id": fid,
            "target_type": flag.target_type,
            "target": flag.target,
            "flag_type": flag.flag_type,
            "evidence_summary": _summarize(flag.evidence),
            "proposed_action": flag.proposed_action,
            "severity": flag.severity,
            "status": ACTIVE,
        }
        previous = by_id.get(fid)
        if previous is None:
            merged.append({**detected, **{c: "" for c in REVIEWER_COLUMNS}})
        else:
            # Reviewer columns win; detected columns are refreshed.
            merged.append({**previous, **detected})

    # Rows whose flag stopped firing. Kept, marked, never deleted.
    for fid, row in by_id.items():
        if fid not in seen:
            merged.append({**row, "status": STALE})

    return merged


def propose(
    flags: list[Flag], study_id: str, derivatives_dir: Path
) -> tuple[Path, Path, list[dict[str, str]]]:
    """Run one detection pass into the decisions table. Idempotent."""
    flags_path = write_flags(flags, study_id, derivatives_dir)
    rows = merge_decisions(load_decisions(study_id, derivatives_dir), flags)
    decisions_path = save_decisions(study_id, rows, derivatives_dir)
    return flags_path, decisions_path, rows


def undecided(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Active rows a reviewer has not answered. Stale rows need no answer."""
    return [
        r for r in rows
        if r.get("status", ACTIVE) == ACTIVE and not (r.get("approved") or "").strip()
    ]


def decide(
    rows: list[dict[str, str]],
    flag_id: str,
    approved: bool,
    reviewer: str,
    reason: str = "",
    action_taken: str | None = None,
) -> list[dict[str, str]]:
    """Record one reviewer decision.

    A rejection or a changed action needs a reason: without one, the record
    cannot tell a considered override from a mis-click.
    """
    out = []
    found = False
    for row in rows:
        if row["flag_id"] != flag_id:
            out.append(row)
            continue
        found = True
        changed = action_taken is not None and action_taken != row.get("proposed_action")
        if (not approved or changed) and not reason.strip():
            raise ValueError(
                "rejecting a flag, or changing its action, requires a reason: "
                "the record cannot otherwise tell a considered override from a slip"
            )
        out.append(
            {
                **row,
                "approved": "true" if approved else "false",
                "action_taken": action_taken
                if action_taken is not None
                else (row.get("proposed_action", "") if approved else "none"),
                "reviewer": reviewer,
                "reviewed_at": _now(),
                "reason": reason,
            }
        )
    if not found:
        raise KeyError(f"no flag {flag_id!r} in this decisions table")
    return out


def select(
    rows: list[dict[str, str]],
    flag_type: str | None = None,
    severity: str | None = None,
    target: str | None = None,
    only_undecided: bool = True,
) -> list[dict[str, str]]:
    """Rows matching a filter. Used to scope a bulk decision.

    There is deliberately no "everything" default: a bulk decision must state
    what it covers, so the history shows what a reviewer actually looked at.
    """
    out = []
    for row in rows:
        if row.get("status", ACTIVE) != ACTIVE:
            continue
        if only_undecided and (row.get("approved") or "").strip():
            continue
        if flag_type and row.get("flag_type") != flag_type:
            continue
        if severity and row.get("severity") != severity:
            continue
        if target and target not in row.get("target", ""):
            continue
        out.append(row)
    return out


def decide_many(
    rows: list[dict[str, str]],
    flag_ids: Sequence[str],
    approved: bool,
    reviewer: str,
    reason: str = "",
    action_taken: str | None = None,
) -> list[dict[str, str]]:
    """Apply the same decision to several flags.

    Convenience over `decide`, not a different rule: the same reason requirement
    applies, so a bulk rejection still has to say why.
    """
    wanted = set(flag_ids)
    out = rows
    for flag_id in sorted(wanted):
        out = decide(out, flag_id, approved, reviewer, reason, action_taken)
    return out


def append_history(
    study_id: str, derivatives_dir: Path, event: str, reviewer: str, **detail: Any
) -> Path:
    """Append-only log of sign and reopen events."""
    d = qc_dir(study_id, derivatives_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / "history.jsonl"
    with path.open("a") as f:
        f.write(json.dumps({"event": event, "reviewer": reviewer,
                            "at": _now(), **detail}) + "\n")
    return path


def read_history(study_id: str, derivatives_dir: Path) -> list[dict[str, Any]]:
    path = qc_dir(study_id, derivatives_dir) / "history.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
