"""EDF reader, round-tripped through a synthetic recording."""

from __future__ import annotations

import numpy as np
import pytest

from dbsspeech.io import PrivacyPolicy, available_formats, open_recording
from tests.fixtures.make_edf_fixture import (
    BETA_CHANNELS,
    BETA_HZ,
    DURATION_S,
    SFREQ_HZ,
    SIGNALS,
    make_edf_fixture,
)

pytestmark = pytest.mark.unit

N_SAMPLES = int(SFREQ_HZ * DURATION_S)
N_EEG = sum(1 for label, _ in SIGNALS if label.startswith("EEG"))
N_EMG = sum(1 for label, _ in SIGNALS if label.startswith("EMG"))


@pytest.fixture(scope="module")
def edf(tmp_path_factory):
    return make_edf_fixture(tmp_path_factory.mktemp("edf"))


def test_format_is_registered():
    assert "edf" in available_formats()


def test_an_edf_is_sniffed_as_edf(edf):
    with open_recording(edf) as rec:
        assert rec.format == "edf"


def test_a_directory_holding_one_edf_is_accepted(edf):
    with open_recording(edf.parent) as rec:
        assert rec.format == "edf"


def test_a_file_with_the_right_suffix_but_wrong_magic_is_not_claimed(tmp_path):
    impostor = tmp_path / "not_really.edf"
    impostor.write_bytes(b"\xffBIOSEMI" + b" " * 512)
    with pytest.raises(ValueError, match="could not identify the format"):
        open_recording(impostor)


def test_channels_group_into_streams_by_the_type_the_file_declares(edf):
    with open_recording(edf) as rec:
        streams = rec.streams
    assert set(streams) == {"eeg", "emg"}
    assert streams["eeg"].n_channels == N_EEG
    assert streams["emg"].n_channels == N_EMG


def test_structure_is_reported(edf):
    with open_recording(edf) as rec:
        info = rec.streams["eeg"]
        assert info.sfreq_hz == pytest.approx(SFREQ_HZ)
        assert info.n_samples == N_SAMPLES
        assert info.duration_s == pytest.approx(DURATION_S)


def test_read_returns_channels_by_samples(edf):
    with open_recording(edf) as rec:
        window = rec.read("eeg", tmin=0.0, tmax=1.0)
    assert window.shape == (N_EEG, int(SFREQ_HZ))


def test_streams_are_read_independently(edf):
    with open_recording(edf) as rec:
        eeg = rec.read("eeg", tmin=0.0, tmax=1.0)
        emg = rec.read("emg", tmin=0.0, tmax=1.0)
    assert eeg.shape[0] == N_EEG
    assert emg.shape[0] == N_EMG


def test_a_window_is_half_open_so_adjacent_windows_do_not_overlap(edf):
    with open_recording(edf) as rec:
        first = rec.read("eeg", tmin=0.0, tmax=1.0)
        second = rec.read("eeg", tmin=1.0, tmax=2.0)
        whole = rec.read("eeg", tmin=0.0, tmax=2.0)
    assert np.allclose(np.concatenate([first, second], axis=1), whole)


def test_the_planted_oscillation_is_only_on_the_channels_it_was_planted_on(edf):
    with open_recording(edf) as rec:
        data = rec.read("eeg")
    spectrum = np.abs(np.fft.rfft(data, axis=1))
    freqs = np.fft.rfftfreq(data.shape[1], 1.0 / SFREQ_HZ)
    beta_bin = int(np.argmin(np.abs(freqs - BETA_HZ)))
    power = spectrum[:, beta_bin]
    # BETA_CHANNELS index the file; within the eeg stream they are the same
    # leading channels, because the EEG-typed signals come first.
    planted = power[list(BETA_CHANNELS)]
    bare = power[[c for c in range(N_EEG) if c not in BETA_CHANNELS]]
    assert planted.min() > 10 * bare.max()


def test_plain_edf_reports_no_epochs(edf):
    """Plain EDF carries no markers. Empty is correct, not a failure."""
    with open_recording(edf) as rec:
        assert rec.epochs == {}


def test_metadata_never_carries_a_restricted_field(edf):
    policy = PrivacyPolicy(
        filenames_deidentified=False,
        restricted_metadata_fields=frozenset({"subject_info", "meas_date"}),
    )
    with open_recording(edf, format="edf", policy=policy) as rec:
        meta = rec.metadata
    assert "subject_info" not in meta
    assert "meas_date" not in meta


def test_the_acquisition_timestamp_is_restricted_by_default(edf):
    """A surgery date is recoverable from an amplifier timestamp."""
    with open_recording(edf, format="edf") as rec:
        assert "meas_date" in rec.metadata["restricted_fields_present"]
        assert "meas_date" in rec.read_restricted_metadata()


def test_an_out_of_range_channel_is_refused(edf):
    with open_recording(edf) as rec, pytest.raises(IndexError, match="out of range"):
        rec.read("eeg", channels=[N_EEG])


def test_closing_twice_is_safe(edf):
    rec = open_recording(edf)
    rec.close()
    rec.close()
