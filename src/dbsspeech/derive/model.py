"""Types shared across the derive package.

Kept in one small module so `pipeline`, `writer`, `ledger` and the external
driver agree on the shape of a job and a result without importing each other.
Nothing here carries a path from Box, a case number, or an acquisition date;
a block is identified by study ID, session and block name only.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Status = Literal["planned", "claimed", "building", "done", "failed", "quarantined", "skipped"]


class Quarantine(Exception):
    """The block cannot be built as policy stands, for a reason a person must see.

    Raised, never guessed around. `reason` is a short machine-readable tag
    (`unmapped_stream`, `rate_not_exactly_rational`, `epoch_clock_origin`,
    `bulk_not_synced`, `filter_did_not_meet_spec`), `detail` is for the ledger.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class BlockJob:
    """One block to build, already staged on local disk.

    `local_dir` is the directory holding the block. For TDT a block is a
    directory and `entry` is None. For BrainVision several recordings sit as
    files in one session directory, so a block is one `.vhdr` and `entry`
    names it; the reader is opened on that file rather than on the directory.
    """

    study_id: str
    session: str
    block: str
    source_format: str
    local_dir: Path
    entry: Path | None = None

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.study_id, self.session, self.block)

    @property
    def open_path(self) -> Path:
        """What to hand to `open_recording`."""
        return self.entry if self.entry is not None else self.local_dir


@dataclass(frozen=True)
class ProductRecord:
    """What was written for one stream."""

    stream: str
    product: str
    role: str
    n_channels: int
    n_samples_in: int
    n_samples_out: int
    sfreq_in_hz: float
    sfreq_out_hz: float
    data_sha256: str
    # FilterReport.as_attrs(), or {} for a native-rate product.
    filter_attrs: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BlockResult:
    """Outcome of building one block. Error text is already redacted."""

    study_id: str
    session: str
    block: str
    status: Status
    out_relpath: str | None = None
    out_sha256: str | None = None
    out_bytes: int = 0
    # Microphone products may be written to a separate, unsynced root; this is
    # that file's path relative to the audio root, or None if none was written.
    audio_relpath: str | None = None
    products: list[ProductRecord] = field(default_factory=list)
    epochs_written: list[str] = field(default_factory=list)
    quarantine_reason: str | None = None
    error_class: str | None = None
    error_message: str | None = None
    seconds: float = 0.0

    @property
    def key(self) -> tuple[str, str, str]:
        return (self.study_id, self.session, self.block)

    @property
    def ok(self) -> bool:
        return self.status == "done"
