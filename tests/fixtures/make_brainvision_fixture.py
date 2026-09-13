"""Generate a synthetic BrainVision recording for tests.

Deterministic, tiny, and written by `pybv`, so the header, binary layout and
marker file are produced by the same library ecosystem that reads them rather
than by hand-rolled bytes that might drift from the real format.

No patient data. Nothing here derives from a real recording.

The signal is built so tests can assert selectivity rather than merely that
something was read: a beta oscillation is planted only on `BETA_CHANNELS`, and
markers are placed at known times under two distinct labels.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

SFREQ_HZ = 500.0
DURATION_S = 8.0
N_CHANNELS = 6
BETA_HZ = 20.0
BETA_CHANNELS = (0, 1)  # planted only here
BETA_AMPLITUDE_UV = 40.0
NOISE_UV = 2.0
SEED = 0

# (onset sample, description code, duration samples). Two distinct codes, so
# grouping into separate EpochSeries is observable, and one code repeated, so a
# series holds more than one onset. MNE reads code N back as "Stimulus/S  N".
MARKERS = (
    (1000, 1, 1),
    (2000, 2, 1),
    (3000, 1, 1),
)

#: Labels MNE reports for MARKERS, in the order the codes appear.
MARKER_LABELS = ("Stimulus/S  1", "Stimulus/S  2")

CH_NAMES = tuple(f"ch{i + 1}" for i in range(N_CHANNELS))


def make_brainvision_fixture(folder: Path, name: str = "synthetic") -> Path:
    """Write `<folder>/<name>.vhdr` plus its `.eeg` and `.vmrk`, returning the header."""
    import pybv

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)

    n_samples = int(SFREQ_HZ * DURATION_S)
    rng = np.random.default_rng(SEED)
    data = rng.normal(0.0, NOISE_UV, (N_CHANNELS, n_samples))

    t = np.arange(n_samples) / SFREQ_HZ
    for channel in BETA_CHANNELS:
        data[channel] += BETA_AMPLITUDE_UV * np.sin(2 * np.pi * BETA_HZ * t)

    # pybv's event columns are (onset_sample, description_code, duration_samples)
    # in that order. The description code is what becomes the marker label, so
    # getting the middle column wrong silently collapses every marker into one.
    events = np.array(MARKERS, dtype=int)

    pybv.write_brainvision(
        data=data,
        sfreq=SFREQ_HZ,
        ch_names=list(CH_NAMES),
        fname_base=name,
        folder_out=str(folder),
        events=events,
        unit="µV",
        overwrite=True,
    )
    return folder / f"{name}.vhdr"


if __name__ == "__main__":  # pragma: no cover - manual use
    import sys

    out = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    print(make_brainvision_fixture(out))
