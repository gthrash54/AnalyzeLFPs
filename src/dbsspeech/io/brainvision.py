"""Reader for BrainVision recordings (`.vhdr` header, `.eeg` data, `.vmrk` markers).

Opening reads no samples: the `.eeg` is memory-mapped and touched only when
`read` asks for a window.

It must nonetheless be present. `mne.io.read_raw_brainvision` opens the data
file to establish its length, so a `FileNotFoundError` naming the `.eeg` means
the bulk has not been synced, not that the header is bad. This is the one place
BrainVision differs from the TDT tank reader, which can report structure from
its `.tsq` index with no bulk at all, and it means a BrainVision block cannot be
triaged from the header alone.

The `.vhdr` is a plain INI-style text file whose first line is a fixed magic
string. That line is what identifies the format; the extension alone is not
enough, because `.vhdr` is generic enough to collide.

Marker handling lives in `_mne_base`: MNE reads the `.vmrk` into annotations,
and each distinct marker label becomes one `EpochSeries`, which is what lets a
paradigm's own triggers stand in for hand-written condition windows.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._mne_base import MneRecording
from .base import register_reader

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mne.io import BaseRaw

FORMAT = "brainvision"

_SUFFIX = ".vhdr"

# First line of every BrainVision header. Vendors vary the version suffix, so
# only the stable prefix is matched.
_MAGIC = b"Brain Vision Data Exchange Header File"


class BrainVisionRecording(MneRecording):
    """Lazily-read BrainVision recording. Opening reads the header only."""

    FORMAT = FORMAT
    ENTRY_SUFFIX = _SUFFIX

    @staticmethod
    def _open_raw(path: Path) -> BaseRaw:
        import mne

        # verbose="ERROR" keeps MNE's per-file chatter out of run logs. It
        # suppresses MNE's own logging only; anything raised still raises.
        return mne.io.read_raw_brainvision(path, preload=False, verbose="ERROR")


def sniff(path: Path) -> bool:
    """True when the path is a BrainVision header, or a directory holding one."""
    p = Path(path)
    if p.is_dir():
        candidates = sorted(p.glob(f"*{_SUFFIX}"))
        return len(candidates) == 1 and sniff(candidates[0])
    if p.suffix.lower() != _SUFFIX:
        return False
    with open(p, "rb") as fh:
        return fh.read(len(_MAGIC)) == _MAGIC


register_reader(FORMAT, BrainVisionRecording, sniff, entry_suffixes=(".vhdr",))
