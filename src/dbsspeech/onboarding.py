"""Getting a new dataset far enough to be reviewable.

Adding a subject means five linked CSVs satisfying the invariants in
`docs/schema.md`, which is the largest single obstacle to anyone outside this
lab using the package at all. Most of that work is transcription: the format,
the paths, the stream names, the channel counts, the sampling rates and the
event markers are all stated by the recording. This module reads them.

Two functions, and the split between them is the point:

`inspect` reads and proposes. It opens nothing it cannot open, writes nothing,
and returns what it found beside what it could not determine. Every value it
suggests is a suggestion.

`commit` writes, and only what a person confirmed. It merges the rows it is
given into the existing manifest, validates the result as a whole, and refuses
to write anything at all if validation fails. A manifest that is invalid on
disk is worse than one that is incomplete, because `load_manifest` is what every
recipe depends on.

What is deliberately not proposed: which channels to include, which target a
lead sits in, and where the conditions are. Those are the review. A wizard that
filled them with plausible defaults would produce a manifest that looks finished
and is not, and nothing downstream could tell the difference.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .detect.manifest_rows import (
    LEFT_TO_REVIEW,
    STREAM_COLUMNS,
    SUBJECT_COLUMNS,
    draft_manifest,
    find_blocks,
)
from .detect.windows import WINDOW_COLUMNS, propose_windows, proposed_rows
from .io import open_recording
from .manifest import DEFAULT_MANIFEST_DIR, Manifest, load_configs, load_manifest, validate

# Tables `commit` can write, and the column order each file declares.
TABLE_COLUMNS: dict[str, tuple[str, ...]] = {
    "subjects": SUBJECT_COLUMNS,
    "streams": STREAM_COLUMNS,
    "windows": WINDOW_COLUMNS,
}

# Keys that identify a row, so committing twice does not silently duplicate it.
TABLE_KEYS: dict[str, tuple[str, ...]] = {
    "subjects": ("study_id", "session"),
    "streams": ("study_id", "session", "stream"),
    "windows": ("study_id", "session", "condition", "t_start_s"),
}


def inspect(
    path: str | Path,
    study_id: str | None = None,
    session: str | None = None,
    configs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Report what a recording or a tree of recordings states about itself.

    `path` may be one block or a `<study_id>/<block>` tree. Nothing is written.
    """
    path = Path(path)
    configs = configs if configs is not None else load_configs()
    marker_config = configs.get("markers") or {}

    out: dict[str, Any] = {
        "path_is_tree": False,
        "blocks": [],
        "unreadable": [],
        "left_to_review": dict(LEFT_TO_REVIEW),
        "not_proposed": [
            "channels.csv: which channels are usable, and the region each sits in",
            "leads.csv: which target a lead is in, its model, and its rotation",
            "windows.csv beyond markers: a condition with no marker is derived "
            "from a signal, by a person",
        ],
    }

    # A directory holding study directories is a tree; a directory holding a
    # recording is one block. Deciding by what is inside beats a flag the
    # caller has to get right.
    tree_blocks = find_blocks(path) if path.is_dir() else []
    if tree_blocks:
        out["path_is_tree"] = True
        draft = draft_manifest(path)
        out["proposed_rows"] = {
            "subjects": draft.subjects,
            "streams": draft.streams,
        }
        out["unreadable"] = [
            {"block": where, "error": why} for where, why in draft.unreadable
        ]
        out["study_ids"] = draft.study_ids
        out["blocks"] = [
            {"study_id": sid, "block": block.name} for sid, block in tree_blocks
        ]
        return out

    # One block.
    try:
        recording = open_recording(path)
    except Exception as exc:
        out["unreadable"] = [{"block": path.name, "error": f"{type(exc).__name__}: {exc}"}]
        return out

    try:
        out["format"] = recording.format
        out["streams"] = {
            name: {
                "n_channels": info.n_channels,
                "sfreq_hz": info.sfreq_hz,
                "n_samples": info.n_samples,
                "duration_s": round(info.duration_s, 3),
                "usable_bandwidth_hz": info.usable_bandwidth_hz,
                "channel_ids": list(info.channel_ids),
            }
            for name, info in sorted(recording.streams.items())
        }
        out["markers"] = {
            label: len(series) for label, series in sorted(recording.epochs.items())
        }
        out["metadata"] = recording.metadata

        if study_id and session:
            proposals = propose_windows(recording, study_id, session, marker_config)
            out["proposed_rows"] = {"windows": proposed_rows(proposals)}
            out["window_notes"] = [p.describe() for p in proposals.proposals]
        elif recording.epochs:
            out["window_notes"] = [
                "study_id and session are needed before window rows can be "
                "proposed from these markers"
            ]
    finally:
        recording.close()
    return out


class CommitRefused(Exception):
    """The rows would produce a manifest that does not validate."""

    def __init__(self, errors: list[str], warnings: list[str] | None = None) -> None:
        self.errors = errors
        self.warnings = warnings or []
        super().__init__(
            f"{len(errors)} validation error(s); nothing was written. "
            + "; ".join(errors[:3])
        )


def _key(row: dict[str, Any], columns: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(str(row.get(c, "")) for c in columns)


def commit(
    rows: dict[str, list[dict[str, Any]]],
    manifest_dir: Path | None = None,
    configs: dict[str, Any] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Merge confirmed rows into the manifest, validating before writing.

    `rows` maps a table name in `TABLE_COLUMNS` to the rows to add. Existing
    rows are kept; a row whose key already exists is reported as a duplicate and
    skipped rather than overwriting, because overwriting a reviewed row from an
    import is how a curated decision disappears without trace.

    Raises `CommitRefused` when the merged manifest fails validation, having
    written nothing.
    """
    directory = Path(manifest_dir or DEFAULT_MANIFEST_DIR)
    configs = configs if configs is not None else load_configs()

    unknown = sorted(set(rows) - set(TABLE_COLUMNS))
    if unknown:
        raise ValueError(
            f"cannot write table(s) {unknown}; this writes only "
            f"{sorted(TABLE_COLUMNS)}. channels.csv and leads.csv are the "
            "review and are edited by a person."
        )

    existing = load_manifest(directory)
    merged: dict[str, list[dict[str, Any]]] = {
        "subjects": list(existing.subjects),
        "streams": list(existing.streams),
        "leads": list(existing.leads),
        "channels": list(existing.channels),
        "windows": list(existing.windows),
    }

    added: dict[str, int] = {}
    duplicates: list[dict[str, Any]] = []
    for table, new_rows in rows.items():
        columns = TABLE_COLUMNS[table]
        key_columns = TABLE_KEYS[table]
        seen = {_key(r, key_columns) for r in merged[table]}
        kept = 0
        for row in new_rows:
            key = _key(row, key_columns)
            if key in seen:
                duplicates.append({"table": table, "key": list(key)})
                continue
            seen.add(key)
            merged[table].append({c: row.get(c, "") for c in columns})
            kept += 1
        added[table] = kept

    report = validate(
        Manifest(
            subjects=merged["subjects"],
            streams=merged["streams"],
            leads=merged["leads"],
            channels=merged["channels"],
            windows=merged["windows"],
        ),
        configs,
    )
    if not report.ok:
        raise CommitRefused(list(report.errors), list(report.warnings))

    written: list[str] = []
    if not dry_run:
        directory.mkdir(parents=True, exist_ok=True)
        for table in rows:
            if not added.get(table):
                continue
            columns = TABLE_COLUMNS[table]
            path = directory / f"{table}.csv"
            # Written whole rather than appended: a partial append leaves a file
            # that parses but is missing rows, and the validation above was of
            # the whole file.
            tmp = path.with_suffix(".csv.tmp")
            with open(tmp, "w", newline="", encoding="utf-8") as fh:
                writer = csv.DictWriter(fh, fieldnames=list(columns))
                writer.writeheader()
                for row in merged[table]:
                    writer.writerow({c: row.get(c, "") for c in columns})
            tmp.replace(path)
            written.append(path.name)

    return {
        "added": added,
        "duplicates_skipped": duplicates,
        "written": written,
        "dry_run": dry_run,
        "warnings": list(report.warnings),
    }


__all__ = ["CommitRefused", "TABLE_COLUMNS", "TABLE_KEYS", "commit", "inspect"]
