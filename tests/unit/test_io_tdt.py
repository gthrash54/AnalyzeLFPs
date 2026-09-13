"""Unit tests for the TDT reader, against a synthetic fixture.

These must pass with no data/ directory present, so nothing here touches a real
recording.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from dbsspeech.io import PrivacyPolicy, available_formats, open_recording
from dbsspeech.io.base import Recording
from tests.fixtures.make_tdt_fixture import (
    BETA_CHANNELS,
    BETA_HZ,
    DURATION_S,
    N_NEURAL_CH,
    SFREQ_AUDIO,
    SFREQ_NEURAL,
    make_fixture,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def block(tmp_path_factory) -> str:
    path = tmp_path_factory.mktemp("tdt") / "synthetic_block.mat"
    return str(make_fixture(path))


def test_format_is_registered():
    assert "tdt_mat" in available_formats()


def test_sniffing_identifies_the_format(block):
    with open_recording(block) as rec:  # no format declared
        assert rec.format == "tdt_mat"


def test_declared_format_is_honored(block):
    with open_recording(block, format="tdt_mat") as rec:
        assert isinstance(rec, Recording)


def test_unknown_format_names_the_registered_ones(block):
    with pytest.raises(ValueError, match="unknown format"):
        open_recording(block, format="not_a_format")


def test_stream_structure(block):
    with open_recording(block) as rec:
        assert set(rec.streams) == {"neur", "mic_"}
        neur = rec.streams["neur"]
        assert neur.n_channels == N_NEURAL_CH
        assert neur.sfreq_hz == SFREQ_NEURAL
        assert neur.duration_s == pytest.approx(DURATION_S)
        assert neur.usable_bandwidth_hz == SFREQ_NEURAL / 2
        assert rec.streams["mic_"].sfreq_hz == SFREQ_AUDIO


def test_read_returns_channels_by_samples(block):
    """The transpose from stored (samples, channels) happens in the reader."""
    with open_recording(block) as rec:
        data = rec.read("neur")
        assert data.shape == (N_NEURAL_CH, int(SFREQ_NEURAL * DURATION_S))


def test_channel_selection_order_is_respected(block):
    with open_recording(block) as rec:
        both = rec.read("neur", channels=[3, 1])
        one = rec.read("neur", channels=[1])
        assert both.shape[0] == 2
        np.testing.assert_array_equal(both[1], one[0])


def test_time_window_is_half_open(block):
    """Adjacent windows must not share a sample."""
    with open_recording(block) as rec:
        a = rec.read("neur", tmin=0.0, tmax=1.0)
        b = rec.read("neur", tmin=1.0, tmax=2.0)
        whole = rec.read("neur", tmin=0.0, tmax=2.0)
        assert a.shape[1] == b.shape[1] == int(SFREQ_NEURAL)
        np.testing.assert_array_equal(np.hstack([a, b]), whole)


def test_planted_signal_is_recovered_where_planted(block):
    """A 20 Hz peak exists on the planted channels and not elsewhere."""
    with open_recording(block) as rec:
        data = rec.read("neur")
    freqs = np.fft.rfftfreq(data.shape[1], 1 / SFREQ_NEURAL)
    power = np.abs(np.fft.rfft(data, axis=1)) ** 2
    peak_bin = int(np.argmin(np.abs(freqs - BETA_HZ)))
    planted = [power[c, peak_bin] for c in BETA_CHANNELS]
    clean = [power[c, peak_bin] for c in range(N_NEURAL_CH) if c not in BETA_CHANNELS]
    assert min(planted) > 20 * max(clean)


def test_bad_channel_index_raises_with_the_range(block):
    with open_recording(block) as rec, pytest.raises(IndexError, match="out of range"):
        rec.read("neur", channels=[99])


def test_unknown_stream_lists_available_streams(block):
    with open_recording(block) as rec, pytest.raises(KeyError, match="no stream"):
        rec.read("nope")


def test_reversed_window_raises(block):
    with open_recording(block) as rec, pytest.raises(ValueError, match="precedes"):
        rec.read("neur", tmin=2.0, tmax=1.0)


def test_epochs_are_exposed(block):
    with open_recording(block) as rec:
        assert "Cam1" in rec.epochs
        cam = rec.epochs["Cam1"]
        assert len(cam) == 8
        assert cam.onsets[0] == pytest.approx(0.0)


def test_metadata_withholds_restricted_fields(block):
    """The central privacy guarantee: restricted fields do not leave the io layer."""
    with open_recording(block) as rec:
        meta = rec.metadata
        blob = repr(meta)
        for secret in ("FIXTURE-SUBJ", "1970-01-01", "/fake/tank/path", "fixture_block"):
            assert secret not in blob, f"{secret!r} leaked into metadata"
        assert "duration" in meta
        assert set(meta["restricted_fields_present"]) >= {"Subject", "date", "tankpath"}


def test_default_policy_withholds_the_filename(block):
    """An unspecified policy withholds more, not less."""
    with open_recording(block) as rec:
        assert "path_name" not in rec.metadata


def test_policy_can_declare_filenames_deidentified(block):
    """Sites whose export naming is known safe can surface the filename."""
    policy = PrivacyPolicy(filenames_deidentified=True)
    with open_recording(block, policy=policy) as rec:
        assert rec.metadata["path_name"].endswith(".mat")


def test_policy_restricted_field_set_is_configurable(block):
    """A site can widen or narrow what is withheld without a code change."""
    policy = PrivacyPolicy(restricted_metadata_fields=frozenset({"duration"}))
    with open_recording(block, policy=policy) as rec:
        meta = rec.metadata
        assert "duration" not in meta
        # Subject is no longer restricted under this policy, so it surfaces.
        assert meta["Subject"] == "FIXTURE-SUBJ"
        assert meta["restricted_fields_present"] == ["duration"]


def test_policy_loads_from_the_project_config():
    """configs/privacy.yaml parses into a policy for a named format."""
    import yaml

    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / "configs" / "privacy.yaml").read_text())
    policy = PrivacyPolicy.from_mapping(config, "tdt_mat")
    # False since 2026-09-09: the timestamp in a TDT filename is the
    # acquisition time, so a surgery date follows from it. See
    # tests/unit/test_privacy_policy.py for the measurement.
    assert policy.filenames_deidentified is False
    assert "Subject" in policy.restricted_metadata_fields
    assert "tankpath" in policy.restricted_metadata_fields


def test_restricted_metadata_is_reachable_only_deliberately(block):
    with open_recording(block) as rec:
        restricted = rec.read_restricted_metadata()
        assert restricted["Subject"] == "FIXTURE-SUBJ"
        assert "duration" not in restricted


def test_close_is_idempotent(block):
    rec = open_recording(block)
    rec.close()
    rec.close()


def test_a_scalar_node_under_epocs_is_ignored_not_fatal(tmp_path):
    """Seen in the archive: an epoc entry stored as a bare uint64, not a group.

    `"onset" in node` on a dataset raises TypeError, which took a whole block
    down. Only groups can carry an onset table; anything else is skipped.
    """
    import shutil

    import h5py

    from dbsspeech.io.tdt_mat import _EPOCS

    src = make_fixture(tmp_path / "with_scalar.mat")
    with h5py.File(src, "r+") as f:
        f.require_group(_EPOCS).create_dataset("junk", data=np.uint64(3))
    with open_recording(src, format="tdt_mat") as rec:
        epochs = rec.epochs
    assert "junk" not in epochs
    shutil.rmtree(tmp_path, ignore_errors=True)
