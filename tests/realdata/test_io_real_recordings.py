"""Contract tests against whatever real recordings are mounted.

Deliberately dataset-agnostic: these assert that the `Recording` contract holds
for real files, not that any particular subject looks a particular way. Facts
about a specific recording belong in docs/datasets/, not in a test.

Skipped automatically when data/ is empty or missing (see tests/conftest.py).
"""

from __future__ import annotations

import pytest

from dbsspeech.io import open_recording
from dbsspeech.io.tdt_mat import sniff

pytestmark = pytest.mark.realdata

# Bounded search depth. data/ may be a symlink to cloud-synced storage holding
# hundreds of subject folders, and a recursive walk there streams over the
# network for minutes. Never glob the archive root.
_MAX_DEPTH = 2


def _find_recordings(root, limit: int = 3) -> list:
    found = []
    for depth in range(_MAX_DEPTH + 1):
        pattern = "/".join(["*"] * depth + ["*.mat"]) if depth else "*.mat"
        for candidate in sorted(root.glob(pattern)):
            if candidate.is_file() and sniff(candidate):
                found.append(candidate)
                if len(found) >= limit:
                    return found
    return found


@pytest.fixture(scope="module")
def recordings(data_dir):
    found = _find_recordings(data_dir)
    if not found:
        pytest.skip(f"no TDT .mat recordings within depth {_MAX_DEPTH} of {data_dir}")
    return found


def test_streams_are_structurally_sane(recordings):
    for path in recordings:
        with open_recording(path) as rec:
            assert rec.streams, f"{path.name} reports no streams"
            for name, info in rec.streams.items():
                assert info.n_channels > 0, f"{path.name}:{name}"
                assert info.sfreq_hz > 0, f"{path.name}:{name}"
                assert info.n_samples > 0, f"{path.name}:{name}"


def test_read_orientation_and_window_length(recordings):
    """Returns (n_channels, n_samples), and a window is the length asked for."""
    for path in recordings:
        with open_recording(path) as rec:
            name, info = next(iter(rec.streams.items()))
            span = min(1.0, info.duration_s / 2)
            data = rec.read(name, tmin=0.0, tmax=span)
            assert data.ndim == 2
            assert data.shape[0] == info.n_channels
            assert data.shape[1] == pytest.approx(span * info.sfreq_hz, abs=2)


def test_channel_subset_matches_full_read(recordings):
    for path in recordings:
        with open_recording(path) as rec:
            name, info = next(iter(rec.streams.items()))
            if info.n_channels < 2:
                continue
            span = min(0.5, info.duration_s / 2)
            full = rec.read(name, tmin=0.0, tmax=span)
            subset = rec.read(name, channels=[1, 0], tmin=0.0, tmax=span)
            assert (subset[0] == full[1]).all()
            assert (subset[1] == full[0]).all()


def test_identifiers_do_not_escape_the_io_layer(recordings):
    """Whatever a real header carries, metadata must not surface it."""
    for path in recordings:
        with open_recording(path) as rec:
            restricted = rec.read_restricted_metadata()
            blob = repr(rec.metadata)
            for key, value in restricted.items():
                if isinstance(value, str) and len(value) > 3:
                    assert value not in blob, f"{path.name}: {key} leaked into metadata"
