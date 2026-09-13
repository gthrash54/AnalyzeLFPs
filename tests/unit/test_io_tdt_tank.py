"""Native TDT tank reader, round-tripped through a synthetic tank."""

from __future__ import annotations

import numpy as np
import pytest

from dbsspeech.io import available_formats, open_recording
from tests.fixtures.make_tdt_tank_fixture import (
    N_CHANNELS,
    N_RECORDS,
    SAMPLES_PER_RECORD,
    SFREQ,
    expected_channel,
    make_tank,
)

pytestmark = pytest.mark.unit

TOTAL = SAMPLES_PER_RECORD * N_RECORDS


@pytest.fixture(scope="module")
def tank(tmp_path_factory):
    return make_tank(tmp_path_factory.mktemp("tank"))


def test_format_is_registered():
    assert "tdt_tank" in available_formats()


def test_a_tsq_is_sniffed_as_a_tank(tank):
    with open_recording(tank) as rec:
        assert rec.format == "tdt_tank"


def test_a_directory_holding_one_tank_is_accepted(tank):
    with open_recording(tank.parent) as rec:
        assert rec.format == "tdt_tank"


def test_structure_comes_from_the_index(tank):
    with open_recording(tank) as rec:
        info = rec.streams["neur"]
        assert info.n_channels == N_CHANNELS
        assert info.sfreq_hz == SFREQ
        assert info.n_samples == TOTAL
        assert info.duration_s == pytest.approx(TOTAL / SFREQ)


def test_full_read_reassembles_every_record_in_order(tank):
    """Records are interleaved by channel; a mis-assembled read shows immediately."""
    with open_recording(tank) as rec:
        data = rec.read("neur")
    assert data.shape == (N_CHANNELS, TOTAL)
    for c in range(N_CHANNELS):
        np.testing.assert_allclose(data[c], expected_channel(c, 0, TOTAL), atol=0.01)


def test_window_read_crosses_record_boundaries(tank):
    """The interesting case: a window that starts and ends mid-record."""
    with open_recording(tank) as rec:
        start, stop = 100, 300  # spans several 64-sample records
        data = rec.read("neur", tmin=start / SFREQ, tmax=stop / SFREQ)
    assert data.shape == (N_CHANNELS, stop - start)
    for c in range(N_CHANNELS):
        np.testing.assert_allclose(data[c], expected_channel(c, start, stop), atol=0.01)


def test_window_inside_a_single_record(tank):
    with open_recording(tank) as rec:
        data = rec.read("neur", tmin=10 / SFREQ, tmax=40 / SFREQ)
    np.testing.assert_allclose(data[0], expected_channel(0, 10, 40), atol=0.01)


def test_channel_selection_order_is_respected(tank):
    with open_recording(tank) as rec:
        data = rec.read("neur", channels=[2, 0], tmin=0.0, tmax=0.05)
    np.testing.assert_allclose(data[0], expected_channel(2, 0, 50), atol=0.01)
    np.testing.assert_allclose(data[1], expected_channel(0, 0, 50), atol=0.01)


def test_adjacent_windows_are_half_open(tank):
    with open_recording(tank) as rec:
        a = rec.read("neur", tmin=0.0, tmax=0.1)
        b = rec.read("neur", tmin=0.1, tmax=0.2)
        whole = rec.read("neur", tmin=0.0, tmax=0.2)
    np.testing.assert_allclose(np.hstack([a, b]), whole)


def test_epochs_are_read_from_the_index(tank):
    with open_recording(tank) as rec:
        cam = rec.epochs["Cam1"]
    assert len(cam) == 5
    np.testing.assert_allclose(cam.values, [1.0, 2.0, 3.0, 4.0, 5.0])


def test_bad_channel_index_raises(tank):
    with open_recording(tank) as rec, pytest.raises(IndexError, match="out of range"):
        rec.read("neur", channels=[99])


def test_unknown_stream_lists_available(tank):
    with open_recording(tank) as rec, pytest.raises(KeyError, match="no stream"):
        rec.read("nope")


def test_reversed_window_raises(tank):
    with open_recording(tank) as rec, pytest.raises(ValueError, match="precedes"):
        rec.read("neur", tmin=0.2, tmax=0.1)


def test_structure_readable_without_the_tev_but_reads_explain(tank, tmp_path):
    """Triage on an unsynced tank: structure yes, samples no, with a clear reason."""
    lonely = tmp_path / "index_only"
    lonely.mkdir()
    target = lonely / tank.name
    target.write_bytes(tank.read_bytes())
    with open_recording(target) as rec:
        assert rec.streams["neur"].n_samples == TOTAL
        with pytest.raises(FileNotFoundError, match="no matching .tev"):
            rec.read("neur")


def test_metadata_carries_no_restricted_fields(tank):
    with open_recording(tank) as rec:
        assert rec.metadata["restricted_fields_present"] == []
        assert rec.read_restricted_metadata() == {}
