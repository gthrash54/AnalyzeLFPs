"""BrainVision reader, round-tripped through a synthetic recording."""

from __future__ import annotations

import numpy as np
import pytest

from dbsspeech.io import PrivacyPolicy, available_formats, open_recording
from tests.fixtures.make_brainvision_fixture import (
    BETA_CHANNELS,
    BETA_HZ,
    CH_NAMES,
    DURATION_S,
    MARKER_LABELS,
    MARKERS,
    N_CHANNELS,
    SFREQ_HZ,
    make_brainvision_fixture,
)

pytestmark = pytest.mark.unit

N_SAMPLES = int(SFREQ_HZ * DURATION_S)


@pytest.fixture(scope="module")
def vhdr(tmp_path_factory):
    return make_brainvision_fixture(tmp_path_factory.mktemp("bv"))


def test_format_is_registered():
    assert "brainvision" in available_formats()


def test_a_vhdr_is_sniffed_as_brainvision(vhdr):
    with open_recording(vhdr) as rec:
        assert rec.format == "brainvision"


def test_a_directory_holding_one_header_is_accepted(vhdr):
    with open_recording(vhdr.parent) as rec:
        assert rec.format == "brainvision"


def test_a_file_with_the_right_suffix_but_wrong_magic_is_not_claimed(tmp_path):
    impostor = tmp_path / "not_really.vhdr"
    impostor.write_text("[Common Infos]\nDataFile=nope.eeg\n")
    with pytest.raises(ValueError, match="could not identify the format"):
        open_recording(impostor)


def test_structure_is_reported(vhdr):
    with open_recording(vhdr) as rec:
        info = rec.streams["eeg"]
        assert info.n_channels == N_CHANNELS
        assert info.sfreq_hz == pytest.approx(SFREQ_HZ)
        assert info.n_samples == N_SAMPLES
        assert info.channel_ids == CH_NAMES
        assert info.duration_s == pytest.approx(DURATION_S)


def test_nyquist_is_reported_for_guardrail_g6(vhdr):
    with open_recording(vhdr) as rec:
        assert rec.streams["eeg"].usable_bandwidth_hz == pytest.approx(SFREQ_HZ / 2)


def test_read_returns_channels_by_samples(vhdr):
    with open_recording(vhdr) as rec:
        window = rec.read("eeg", tmin=0.0, tmax=1.0)
    assert window.shape == (N_CHANNELS, int(SFREQ_HZ))


def test_a_window_is_half_open_so_adjacent_windows_do_not_overlap(vhdr):
    with open_recording(vhdr) as rec:
        first = rec.read("eeg", tmin=0.0, tmax=1.0)
        second = rec.read("eeg", tmin=1.0, tmax=2.0)
        whole = rec.read("eeg", tmin=0.0, tmax=2.0)
    assert np.allclose(np.concatenate([first, second], axis=1), whole)


def test_channel_selection_follows_the_order_requested(vhdr):
    with open_recording(vhdr) as rec:
        forward = rec.read("eeg", channels=[0, 1], tmin=0.0, tmax=0.5)
        reversed_ = rec.read("eeg", channels=[1, 0], tmin=0.0, tmax=0.5)
    assert np.allclose(forward[0], reversed_[1])
    assert np.allclose(forward[1], reversed_[0])


def test_the_planted_oscillation_is_only_on_the_channels_it_was_planted_on(vhdr):
    with open_recording(vhdr) as rec:
        data = rec.read("eeg")
    spectrum = np.abs(np.fft.rfft(data, axis=1))
    freqs = np.fft.rfftfreq(data.shape[1], 1.0 / SFREQ_HZ)
    beta_bin = int(np.argmin(np.abs(freqs - BETA_HZ)))
    power = spectrum[:, beta_bin]
    planted = power[list(BETA_CHANNELS)]
    bare = power[[c for c in range(N_CHANNELS) if c not in BETA_CHANNELS]]
    assert planted.min() > 10 * bare.max()


def test_markers_become_one_epoch_series_per_label(vhdr):
    with open_recording(vhdr) as rec:
        epochs = rec.epochs
    assert set(epochs) == set(MARKER_LABELS)
    assert len(epochs["Stimulus/S  1"]) == 2
    assert len(epochs["Stimulus/S  2"]) == 1


def test_marker_onsets_are_seconds_from_the_first_sample(vhdr):
    with open_recording(vhdr) as rec:
        onsets = sorted(
            float(o) for series in rec.epochs.values() for o in series.onsets
        )
    expected = sorted(sample / SFREQ_HZ for sample, _, _ in MARKERS)
    assert onsets == pytest.approx(expected)


def test_an_unknown_stream_names_the_streams_that_exist(vhdr):
    with open_recording(vhdr) as rec, pytest.raises(KeyError, match="eeg"):
        rec.read("nosuchstream")


def test_a_reversed_window_is_refused(vhdr):
    with open_recording(vhdr) as rec, pytest.raises(ValueError, match="precedes"):
        rec.read("eeg", tmin=2.0, tmax=1.0)


def test_an_out_of_range_channel_is_refused(vhdr):
    with open_recording(vhdr) as rec, pytest.raises(IndexError, match="out of range"):
        rec.read("eeg", channels=[N_CHANNELS])


def test_metadata_never_carries_a_restricted_field(vhdr):
    policy = PrivacyPolicy(
        filenames_deidentified=False,
        restricted_metadata_fields=frozenset({"subject_info", "meas_date"}),
    )
    with open_recording(vhdr, format="brainvision", policy=policy) as rec:
        meta = rec.metadata
    assert "subject_info" not in meta
    assert "meas_date" not in meta
    assert meta["format"] == "brainvision"


def test_the_filename_is_withheld_unless_the_policy_allows_it(vhdr):
    withheld = PrivacyPolicy(filenames_deidentified=False)
    allowed = PrivacyPolicy(filenames_deidentified=True)
    with open_recording(vhdr, format="brainvision", policy=withheld) as rec:
        assert "path_name" not in rec.metadata
    with open_recording(vhdr, format="brainvision", policy=allowed) as rec:
        assert rec.metadata["path_name"] == vhdr.name


def test_restricted_metadata_is_a_separate_deliberate_call(vhdr):
    with open_recording(vhdr, format="brainvision") as rec:
        restricted = rec.read_restricted_metadata()
    assert isinstance(restricted, dict)
    # Every value is text, so no caller can do arithmetic on an identifier and
    # present the result as a number.
    assert all(isinstance(v, str) for v in restricted.values())


def test_closing_twice_is_safe(vhdr):
    rec = open_recording(vhdr)
    rec.close()
    rec.close()
