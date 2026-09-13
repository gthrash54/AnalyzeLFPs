"""Generate a synthetic EDF recording for tests.

Written byte by byte rather than through an exporter, because MNE's EDF export
needs `edfio`, and adding a dependency so that a test can produce four hundred
bytes of header is a poor trade. The format is small and fully specified, so
writing it here is cheap and documents what the reader is parsing.

EDF layout, all header fields being space-padded ASCII:

    offset  size  field
    0       8     version, "0" then seven spaces
    8       80    local patient identification
    88      80    local recording identification
    168     8     start date, dd.mm.yy
    176     8     start time, hh.mm.ss
    184     8     header size in bytes
    192     44    reserved
    236     8     number of data records
    244     8     duration of a data record, seconds
    252     4     number of signals, ns

    then ns copies of each field in turn: label(16), transducer(80),
    dimension(8), physical min(8), physical max(8), digital min(8),
    digital max(8), prefiltering(80), samples per record(8), reserved(32)

    then the data records, little-endian int16, signal by signal.

No patient data. The patient field is the EDF+ "unknown" convention, four
literal ``X`` tokens, so nothing name-shaped exists in the repository even as a
fixture. The start timestamp is fixed and synthetic, and its only purpose is to
give the privacy tests a restricted field that is reliably present.

Channel labels carry the EDF+ ``TYPE Name`` prefix, which is what lets the
reader group channels into more than one stream.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

SFREQ_HZ = 250.0
RECORD_SECONDS = 1
N_RECORDS = 8
DURATION_S = RECORD_SECONDS * N_RECORDS
BETA_HZ = 20.0
BETA_AMPLITUDE_UV = 40.0
NOISE_UV = 2.0
SEED = 0

# (label, is_beta). The prefixes are EDF+ channel types, so the reader sees
# two channel types and therefore two streams.
SIGNALS = (
    ("EEG ch1", True),
    ("EEG ch2", True),
    ("EEG ch3", False),
    ("EMG ch4", False),
)
BETA_CHANNELS = tuple(i for i, (_, beta) in enumerate(SIGNALS) if beta)

PHYS_MIN_UV = -1000.0
PHYS_MAX_UV = 1000.0
DIG_MIN = -32768
DIG_MAX = 32767

_START_DATE = "01.01.00"
_START_TIME = "00.00.00"
_PATIENT = "X X X X"
_RECORDING = "Startdate 01-JAN-2000 X X synthetic"


def _pad(text: str, width: int) -> bytes:
    value = str(text)
    if len(value) > width:
        raise ValueError(f"EDF field {value!r} exceeds {width} bytes")
    return value.ljust(width).encode("ascii")


def make_edf_fixture(folder: Path, name: str = "synthetic") -> Path:
    """Write `<folder>/<name>.edf` and return its path."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.edf"

    samples_per_record = int(SFREQ_HZ * RECORD_SECONDS)
    n_samples = samples_per_record * N_RECORDS
    n_signals = len(SIGNALS)

    rng = np.random.default_rng(SEED)
    micro = rng.normal(0.0, NOISE_UV, (n_signals, n_samples))
    t = np.arange(n_samples) / SFREQ_HZ
    for channel in BETA_CHANNELS:
        micro[channel] += BETA_AMPLITUDE_UV * np.sin(2 * np.pi * BETA_HZ * t)

    # Physical to digital is the linear map EDF defines from the two ranges.
    scale = (DIG_MAX - DIG_MIN) / (PHYS_MAX_UV - PHYS_MIN_UV)
    digital = np.clip(
        np.round((micro - PHYS_MIN_UV) * scale + DIG_MIN), DIG_MIN, DIG_MAX
    ).astype("<i2")

    header = b"".join(
        (
            _pad("0", 8),
            _pad(_PATIENT, 80),
            _pad(_RECORDING, 80),
            _pad(_START_DATE, 8),
            _pad(_START_TIME, 8),
            _pad(256 + 256 * n_signals, 8),
            _pad("", 44),
            _pad(N_RECORDS, 8),
            _pad(RECORD_SECONDS, 8),
            _pad(n_signals, 4),
        )
    )

    labels = [label for label, _ in SIGNALS]
    signal_header = b"".join(
        (
            b"".join(_pad(label, 16) for label in labels),
            b"".join(_pad("", 80) for _ in labels),          # transducer
            b"".join(_pad("uV", 8) for _ in labels),         # physical dimension
            b"".join(_pad(int(PHYS_MIN_UV), 8) for _ in labels),
            b"".join(_pad(int(PHYS_MAX_UV), 8) for _ in labels),
            b"".join(_pad(DIG_MIN, 8) for _ in labels),
            b"".join(_pad(DIG_MAX, 8) for _ in labels),
            b"".join(_pad("", 80) for _ in labels),          # prefiltering
            b"".join(_pad(samples_per_record, 8) for _ in labels),
            b"".join(_pad("", 32) for _ in labels),          # reserved
        )
    )

    with open(path, "wb") as fh:
        fh.write(header)
        fh.write(signal_header)
        for record in range(N_RECORDS):
            start = record * samples_per_record
            stop = start + samples_per_record
            for signal in range(n_signals):
                fh.write(struct.pack(f"<{samples_per_record}h",
                                     *digital[signal, start:stop]))
    return path


if __name__ == "__main__":  # pragma: no cover - manual use
    import sys

    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(make_edf_fixture(out))
