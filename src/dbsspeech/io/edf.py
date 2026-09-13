"""Reader for EDF and EDF+ recordings.

EDF is the interchange format most clinical neurophysiology systems export, so
supporting it is what lets a recording from a different institution enter the
pipeline without a conversion step.

Opening reads the header only; MNE reads sample windows on demand.

Two format facts this reader depends on:

Identification
    An EDF file begins with an 8-character version field that is ``"0"``
    followed by seven spaces, and its header is at least 256 bytes. That pair
    is what `sniff` checks. The extension alone is not enough, and BDF, which
    is EDF-shaped but begins with a ``0xFF`` byte, is deliberately not claimed
    here: it would need its own reader and its own tests.

Annotations
    In EDF+ the markers live in an ``EDF Annotations`` signal rather than a
    separate file. MNE parses that signal into annotations, so `epochs`
    behaves the same as it does for BrainVision. Plain EDF has no markers and
    reports no epochs, which is correct rather than a failure.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from ._mne_base import MneRecording
from .base import register_reader

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mne.io import BaseRaw

FORMAT = "edf"

_SUFFIX = ".edf"

# EDF version field: "0" then seven spaces. BDF begins 0xFF and is not claimed.
_MAGIC = b"0       "
_MIN_HEADER_BYTES = 256


class EdfRecording(MneRecording):
    """Lazily-read EDF or EDF+ recording. Opening reads the header only."""

    FORMAT = FORMAT
    ENTRY_SUFFIX = _SUFFIX

    @staticmethod
    def _open_raw(path: Path) -> BaseRaw:
        import mne

        # infer_types=True lets MNE assign channel types from the standard
        # "EEG Fpz" style prefixes an EDF label carries, which is what makes
        # the stream grouping in _mne_base reflect the file rather than
        # collapsing everything into one stream.
        return mne.io.read_raw_edf(
            path, preload=False, infer_types=True, verbose="ERROR"
        )


def sniff(path: Path) -> bool:
    """True when the path is an EDF file, or a directory holding exactly one."""
    p = Path(path)
    if p.is_dir():
        candidates = sorted(p.glob(f"*{_SUFFIX}"))
        return len(candidates) == 1 and sniff(candidates[0])
    if p.suffix.lower() != _SUFFIX:
        return False
    if p.stat().st_size < _MIN_HEADER_BYTES:
        return False
    with open(p, "rb") as fh:
        return fh.read(len(_MAGIC)) == _MAGIC


register_reader(FORMAT, EdfRecording, sniff, entry_suffixes=(".edf",))
