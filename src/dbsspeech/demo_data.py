"""Generate a synthetic TDT-shaped recording, for tests and for the demo project.

Deterministic, tiny, and structurally identical to a real TDT MATLAB v7.3
export: same group layout, same (n_samples, n_channels) orientation, same
uint16 char arrays for strings, same gzip chunking along the sample axis.

No patient data. Nothing here is derived from a real recording; the layout was
established by inspecting one, and only the layout is reproduced.

In the package rather than under `tests/` because `python -m dbsspeech seed`
builds the demo project from it, and an installed package has no test suite to
import from. `tests/fixtures/make_tdt_fixture.py` re-exports it.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

# Small enough to commit, long enough to window.
SFREQ_NEURAL = 2000.0
SFREQ_AUDIO = 1000.0
DURATION_S = 4.0
N_NEURAL_CH = 8
N_AUDIO_CH = 1
BETA_HZ = 20.0
BETA_CHANNELS = (0, 1)  # planted only here, so tests can assert selectivity
SEED = 0

# Stimulation and the ringing after it, for the ERNA recipe. Off by default:
# every other test asserts on a recording without stimulation in it, and adding
# an artifact two orders of magnitude above the signal would change what those
# tests measure.
ERNA_CHANNELS = (2, 3)
ERNA_FREQ_HZ = 250.0          # what the recipe has to recover
ERNA_TAU_S = 0.012            # decay constant, likewise
ERNA_AMPLITUDE_V = 4e-5
ERNA_ONSETS_S = (0.30, 0.80, 1.30, 1.80, 2.30, 2.80, 3.30)
ERNA_ARTIFACT_V = 5e-3        # the stimulation artifact, deliberately enormous
ERNA_ARTIFACT_MS = 1.0        # how long it lasts
ERNA_RESPONSE_DELAY_MS = 2.0  # from the artifact to the start of the ringing


def _write_matlab_string(group, name: str, text: str) -> None:
    """Write a string the way MATLAB v7.3 does: uint16 code points, column vector."""
    codes = np.array([ord(c) for c in text], dtype=np.uint16).reshape(-1, 1)
    group.create_dataset(name, data=codes)


def erna_onsets(duration_s: float) -> tuple[float, ...]:
    """Stimulation onsets for a recording of this length.

    `ERNA_ONSETS_S` is the canonical set for the four-second fixture, and the
    ERNA tests assert on it, so a recording of that length or shorter gets
    exactly it. A longer recording continues the same 0.5 s cadence to the end.

    Stimulation does not stop after three seconds, and pretending it does had a
    consequence: the kurtosis detector judges a channel by its median 10 s
    block, so in a twelve-second demo three seconds of artifact was diluted into
    nine seconds of noise, the stimulating contacts stopped being flagged, and
    the demo silently lost the review decision it exists to teach.
    """
    if duration_s <= DURATION_S:
        return ERNA_ONSETS_S
    onsets = list(ERNA_ONSETS_S)
    step = 0.5
    t = onsets[-1] + step
    while t <= duration_s - 0.2:
        onsets.append(round(t, 2))
        t += step
    return tuple(onsets)


def _plant_erna(
    neural: np.ndarray, sfreq_hz: float, duration_s: float = DURATION_S
) -> np.ndarray:
    """Add stimulation artifacts, each followed by a damped oscillation.

    The shape a recipe has to cope with, not a shape that makes it easy: an
    artifact two orders of magnitude above the signal, a gap, then ringing at a
    known frequency decaying with a known time constant. A recipe that recovers
    the frequency without blanking the artifact is recovering it by accident.
    """
    for onset_s in erna_onsets(duration_s):
        start = int(round(onset_s * sfreq_hz))
        artifact_n = max(1, int(round(ERNA_ARTIFACT_MS * sfreq_hz / 1000.0)))
        # Biphasic, like a stimulation pulse and the amplifier recovering from it.
        for i in range(artifact_n):
            if start + i < neural.shape[0]:
                sign = 1.0 if i < artifact_n / 2 else -1.0
                neural[start + i, list(ERNA_CHANNELS)] += sign * ERNA_ARTIFACT_V

        ring_start = start + artifact_n + int(
            round(ERNA_RESPONSE_DELAY_MS * sfreq_hz / 1000.0)
        )
        n_ring = int(round(6 * ERNA_TAU_S * sfreq_hz))
        stop = min(ring_start + n_ring, neural.shape[0])
        if stop <= ring_start:
            continue
        t_ring = np.arange(stop - ring_start) / sfreq_hz
        ring = (
            ERNA_AMPLITUDE_V
            * np.exp(-t_ring / ERNA_TAU_S)
            * np.sin(2 * np.pi * ERNA_FREQ_HZ * t_ring)
        ).astype(np.float32)
        for ch in ERNA_CHANNELS:
            neural[ring_start:stop, ch] += ring
    return neural


def make_fixture(
    path: Path,
    erna: bool = False,
    sfreq_hz: float = SFREQ_NEURAL,
    duration_s: float = DURATION_S,
) -> Path:
    """Write the synthetic block to `path` and return it.

    `duration_s` defaults to the four seconds every existing test asserts
    against. The demo project asks for more, because two recipes cannot run on
    four seconds at their real defaults: a comodulogram needs ten cycles of its
    slowest phase frequency inside a single window, which is 2.5 s at 4 Hz, and
    an event-locked average needs ten trials. Bending those two parameters down
    until a four-second recording satisfied them would have produced a demo that
    ran and taught the wrong lesson about what either recipe needs.

    `erna` adds stimulation artifacts and the ringing after them on
    `ERNA_CHANNELS`. It is off by default because every other test asserts on a
    recording with no stimulation in it, and an artifact this large would change
    what those tests measure.

    `sfreq_hz` raises the neural rate. The default 2 kHz gives eight samples per
    cycle at the planted ERNA frequency, which quantizes peak times enough to
    move a frequency estimate by more than the tolerance a test should allow. An
    ERNA recording is sampled fast for exactly this reason, so the ERNA test
    builds its fixture that way rather than loosening what it asserts.
    """
    import h5py

    rng = np.random.default_rng(SEED)
    n_neural = int(sfreq_hz * duration_s)
    n_audio = int(SFREQ_AUDIO * duration_s)

    t = np.arange(n_neural) / sfreq_hz
    neural = rng.standard_normal((n_neural, N_NEURAL_CH)).astype(np.float32) * 1e-5
    beta = (2e-5 * np.sin(2 * np.pi * BETA_HZ * t)).astype(np.float32)
    for ch in BETA_CHANNELS:
        neural[:, ch] += beta
    if erna:
        neural = _plant_erna(neural, sfreq_hz, duration_s)

    audio = (rng.standard_normal((n_audio, N_AUDIO_CH)) * 1e-3).astype(np.float32)

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        streams = f.create_group("importdata/streams")

        for name, data, sfreq in (
            ("neur", neural, sfreq_hz),
            ("mic_", audio, SFREQ_AUDIO),
        ):
            g = streams.create_group(name)
            g.create_dataset(
                "data",
                data=data,
                # Chunked along samples across the full channel width, as TDT exports are.
                chunks=(min(256, data.shape[0]), data.shape[1]),
                compression="gzip",
            )
            g.create_dataset("fs", data=np.array([[sfreq]], dtype=np.float64))
            g.create_dataset("startTime", data=np.array([[0.0]], dtype=np.float64))
            g.create_dataset(
                "channel",
                data=np.arange(1, data.shape[1] + 1, dtype=np.uint16).reshape(-1, 1),
            )
            _write_matlab_string(g, "name", name)

        ep = f.create_group("importdata/epocs/Cam1")
        onsets = np.arange(0.0, duration_s, 0.5).reshape(1, -1)
        ep.create_dataset("onset", data=onsets)
        ep.create_dataset("offset", data=onsets + 0.01)
        ep.create_dataset("data", data=np.arange(1, onsets.size + 1, dtype=float).reshape(1, -1))

        info = f.create_group("importdata/info")
        # Structural, safe to surface.
        _write_matlab_string(info, "duration", f"00:00:00:{int(duration_s):02d}")
        info.create_dataset("snipChannel", data=np.array([[0.0]]))
        # Identifier-shaped, must be withheld by Recording.metadata. These are
        # obvious fakes; the point is that the reader refuses to surface them.
        _write_matlab_string(info, "Subject", "FIXTURE-SUBJ")
        _write_matlab_string(info, "date", "1970-01-01")
        _write_matlab_string(info, "tankpath", "/fake/tank/path")
        _write_matlab_string(info, "blockname", "fixture_block")

    return path


if __name__ == "__main__":  # pragma: no cover - a convenience, not a code path
    out = Path("synthetic_block.mat")
    make_fixture(out)
    print(f"wrote {out} ({out.stat().st_size / 1024:.0f} KB)")
