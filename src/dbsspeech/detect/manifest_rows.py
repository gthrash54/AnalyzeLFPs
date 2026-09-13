"""Deriving manifest rows from a tree of recordings.

Adding a subject means writing five linked CSVs. Two of them are not judgment
at all: `subjects.csv` needs the format and the path, and `streams.csv` needs
the stream names, channel counts and sampling rates, all of which the recording
states about itself. Typing them by hand is transcription, and transcription is
where a channel count quietly becomes wrong.

So this reads them. It deliberately does not fill anything else. `hemisphere`,
`units` and `role` are left empty, and `channels.csv`, `leads.csv` and
`windows.csv` are not produced at all, because those are the review: which
channels are usable and why, which lead sits in which target, where the
conditions are in time. A plausible guess in one of those cells is worse than a
blank one, because a blank is visibly unanswered.

The tree is expected to be `<root>/<study_id>/<block>/...`, which is what a
staged archive looks like. Every registered format is recognized, from the
reader registry rather than a list kept here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..io import PrivacyPolicy, all_entry_suffixes, open_recording

SUBJECT_COLUMNS = (
    "study_id",
    "session",
    "hemisphere",
    "format",
    "root_relpath",
    "acquisition",
    "acquisition_date",
    "notes",
)

STREAM_COLUMNS = (
    "study_id",
    "session",
    "stream",
    "n_channels",
    "sfreq_hz",
    "units",
    "role",
    "relpath",
    "notes",
)

# Columns this never fills, and why, so the omission reads as deliberate.
LEFT_TO_REVIEW = {
    "hemisphere": "which side, from the operative record",
    "acquisition_date": "a site decides whether this is an identifier",
    "units": "scale is unverified until someone checks the amplifier settings",
    "role": "what a stream is for is a judgment about the paradigm",
}


@dataclass
class DraftManifest:
    """Derived rows, plus what could not be read."""

    subjects: list[dict[str, Any]] = field(default_factory=list)
    streams: list[dict[str, Any]] = field(default_factory=list)
    unreadable: list[tuple[str, str]] = field(default_factory=list)

    @property
    def study_ids(self) -> list[str]:
        return sorted({row["study_id"] for row in self.subjects})


def _entry_files(block: Path, suffixes: set[str]) -> list[Path]:
    return sorted(p for p in block.glob("*") if p.suffix.lower() in suffixes)


def find_blocks(root: Path) -> list[tuple[str, Path]]:
    """Every `(study_id, block_dir)` under `root` holding a recording.

    A study directory may hold blocks directly or nest them a level deeper, so
    the search is recursive and a directory qualifies by containing an entry
    file rather than by sitting at a fixed depth.
    """
    suffixes = {s for group in all_entry_suffixes().values() for s in group}
    out: list[tuple[str, Path]] = []
    for study_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if study_dir.name.startswith("_") or study_dir.name.startswith("."):
            continue
        seen: set[Path] = set()
        for candidate in sorted(study_dir.rglob("*")):
            if not candidate.is_file() or candidate.suffix.lower() not in suffixes:
                continue
            block = candidate.parent
            if block not in seen:
                seen.add(block)
                out.append((study_dir.name, block))
    return out


def draft_manifest(
    root: Path,
    study_ids: list[str] | None = None,
    policy: PrivacyPolicy | None = None,
) -> DraftManifest:
    """Derive `subjects.csv` and `streams.csv` rows from the recordings in `root`."""
    root = Path(root)
    suffixes = {s for group in all_entry_suffixes().values() for s in group}
    draft = DraftManifest()

    for study_id, block in find_blocks(root):
        if study_ids and study_id not in study_ids:
            continue
        entries = _entry_files(block, suffixes)
        if not entries:
            continue
        try:
            recording = open_recording(entries[0], policy=policy)
        except Exception as exc:
            draft.unreadable.append(
                (f"{study_id}/{block.name}", f"{type(exc).__name__}: {exc}"[:160])
            )
            continue

        try:
            # One block is one session. A study that means something else by
            # "session" renames the column values; the shape is the same.
            session = block.name
            draft.subjects.append(
                {
                    "study_id": study_id,
                    "session": session,
                    "hemisphere": "",
                    "format": recording.format,
                    "root_relpath": str(block.relative_to(root)),
                    "acquisition": block.name,
                    "acquisition_date": "",
                    "notes": "",
                }
            )
            for name, info in sorted(recording.streams.items()):
                draft.streams.append(
                    {
                        "study_id": study_id,
                        "session": session,
                        "stream": name,
                        "n_channels": info.n_channels,
                        "sfreq_hz": info.sfreq_hz,
                        "units": "",
                        "role": "",
                        "relpath": "",
                        "notes": "",
                    }
                )
        finally:
            recording.close()

    return draft


def verify_readable(
    root: Path,
    study_ids: list[str] | None = None,
    policy: PrivacyPolicy | None = None,
) -> dict[str, dict[str, Any]]:
    """Open every block under `root` and report what the readers made of it.

    Staging is not finished when the bytes land, it is finished when the package
    can open them. Running that as its own step means a staging problem is found
    here and not three layers down inside a recipe.
    """
    root = Path(root)
    suffixes = {s for group in all_entry_suffixes().values() for s in group}
    report: dict[str, dict[str, Any]] = {}

    for study_id, block in find_blocks(root):
        if study_ids and study_id not in study_ids:
            continue
        entry = report.setdefault(
            study_id, {"blocks": 0, "opened": 0, "failed": 0, "errors": []}
        )
        entry["blocks"] += 1
        entries = _entry_files(block, suffixes)
        try:
            recording = open_recording(entries[0], policy=policy)
        except Exception as exc:
            entry["failed"] += 1
            entry["errors"].append(
                {"block": block.name, "error": f"{type(exc).__name__}: {exc}"[:200]}
            )
            continue
        try:
            entry["opened"] += 1
        finally:
            recording.close()
    return report


__all__ = [
    "LEFT_TO_REVIEW",
    "STREAM_COLUMNS",
    "SUBJECT_COLUMNS",
    "DraftManifest",
    "draft_manifest",
    "find_blocks",
    "verify_readable",
]
