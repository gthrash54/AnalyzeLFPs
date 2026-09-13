"""Impedance sweeps exported by the acquisition hardware.

The amplifier measures every contact and writes a CSV. That file is the most
direct evidence available about what is physically connected, so it is what the
app goes on rather than inferring contact roles from the signal.

Format, as exported by TDT PZ5 and IZV banks:

    TIME (S),FREQUENCY (Hz),R1 (kOhm),R2 (kOhm),...,REF (kOhm)
    22,2240,1.13,1.38,...,-1.00
    30,2240,-1.00,-1.00,...,1.49

Parsed generically: any column matching ``R<n> (kOhm)`` is a channel, ``REF`` is
the reference when present, and ``-1.00`` means "not measured in this sweep"
rather than a real value. A sweep may measure only some channels, so several
rows are merged, most recent valid value winning.

Nothing here decides anything. It reports measurements; `dbsspeech.detect`
interprets them and a person confirms.
"""

from __future__ import annotations

import contextlib
import csv
import re
from dataclasses import dataclass
from pathlib import Path

# -1.00 is the sentinel the hardware writes for a channel it did not measure.
NOT_MEASURED = -1.0

_CHANNEL_RE = re.compile(r"^R(\d+)\s*\((\w+)\)$", re.IGNORECASE)
_REF_RE = re.compile(r"^REF\s*\((\w+)\)$", re.IGNORECASE)


@dataclass(frozen=True)
class ImpedanceSweep:
    """One hardware impedance export.

    `values` maps 1-based channel number to impedance in kOhm. Channels the
    hardware did not measure are absent rather than present as a sentinel.
    """

    path: Path
    values: dict[int, float]
    reference: float | None
    frequency_hz: float | None
    unit: str = "kOhm"

    @property
    def n_channels(self) -> int:
        return max(self.values, default=0)

    def measured(self) -> dict[int, float]:
        return dict(sorted(self.values.items()))

    def missing(self, expected: int) -> list[int]:
        """Channel numbers up to `expected` with no measurement."""
        return [c for c in range(1, expected + 1) if c not in self.values]


def read_sweep(path: str | Path) -> ImpedanceSweep:
    """Parse one impedance CSV.

    Merges every row, so a bank measured across two sweeps reads as one set of
    values. Later rows win, which matches how the hardware re-measures.
    """
    p = Path(path)
    values: dict[int, float] = {}
    reference: float | None = None
    frequency: float | None = None
    unit = "kOhm"

    with p.open(newline="") as f:
        for row in csv.DictReader(f):
            for column, raw in row.items():
                if column is None or raw is None:
                    continue
                text = raw.strip()
                if not text:
                    continue
                key = column.strip()

                if key.upper().startswith("FREQUENCY"):
                    with contextlib.suppress(ValueError):
                        frequency = float(text)
                    continue

                match = _CHANNEL_RE.match(key)
                if match:
                    unit = match.group(2)
                    try:
                        value = float(text)
                    except ValueError:
                        continue
                    if value != NOT_MEASURED:
                        values[int(match.group(1))] = value
                    continue

                if _REF_RE.match(key):
                    try:
                        value = float(text)
                    except ValueError:
                        continue
                    if value != NOT_MEASURED:
                        reference = value

    return ImpedanceSweep(
        path=p, values=values, reference=reference, frequency_hz=frequency, unit=unit
    )


def find_sweeps(recording_dir: str | Path) -> list[Path]:
    """Impedance CSVs beside a recording, sorted.

    Depth one only: a recording directory is small, and the archive it may live
    in is not.
    """
    d = Path(recording_dir)
    if not d.is_dir():
        return []
    return sorted(p for p in d.glob("*.csv") if _looks_like_sweep(p))


def _looks_like_sweep(path: Path) -> bool:
    try:
        with path.open(newline="") as f:
            header = f.readline()
    except OSError:
        return False
    return any(_CHANNEL_RE.match(c.strip()) for c in header.split(","))


def pair_differential(sweep: ImpedanceSweep) -> list[tuple[int, int]]:
    """Group a differential bank into consecutive electrode pairs.

    EMG banks wire two electrodes per recorded channel, so an 8-electrode sweep
    describes 4 channels. Returns the (positive, negative) electrode numbers per
    channel, in channel order.
    """
    electrodes = sorted(sweep.values)
    return [(a, b) for a, b in zip(electrodes[::2], electrodes[1::2], strict=False)]
