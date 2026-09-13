"""Joining manifest to recording: channel resolution, montage, row labels.

Uses a synthetic manifest over the synthetic TDT fixture, so nothing here needs
real data.
"""

from __future__ import annotations

import csv

import numpy as np
import pytest

from dbsspeech.io.loader import open_session
from dbsspeech.manifest import load_configs, load_manifest
from tests.fixtures.make_tdt_fixture import N_NEURAL_CH, SFREQ_NEURAL, make_fixture

pytestmark = pytest.mark.unit

SID, SES = "S01", "ses1"
CONTACTS = ["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"]


@pytest.fixture(scope="module")
def configs():
    return load_configs()


@pytest.fixture(scope="module")
def session_root(tmp_path_factory):
    """A data dir and manifest dir describing the synthetic fixture."""
    base = tmp_path_factory.mktemp("session")
    data = base / "data" / "block"
    make_fixture(data / "synthetic_block.mat")

    m = base / "manifest"
    m.mkdir()

    def write(name, header, rows):
        with (m / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write("subjects.csv",
          ["study_id", "session", "hemisphere", "format", "root_relpath",
           "acquisition", "acquisition_date", "notes"],
          [[SID, SES, "R", "tdt_mat", "block", "acq", "", ""]])
    write("streams.csv",
          ["study_id", "session", "stream", "n_channels", "sfreq_hz", "units",
           "role", "relpath", "notes"],
          [[SID, SES, "neur", str(N_NEURAL_CH), str(SFREQ_NEURAL), "V", "neural", "", ""]])
    write("leads.csv",
          ["study_id", "session", "lead_id", "target", "hemisphere", "lead_model",
           "channel_first", "channel_last", "rotation_deg", "notes"],
          [[SID, SES, "lead1", "stn", "R", "unknown_directional_1331", "1", "8", "", ""]])
    write("channels.csv",
          ["study_id", "session", "stream", "ch_index", "ch_name", "region",
           "lead_id", "lead_contact", "site", "include", "exclude_reason"],
          [[SID, SES, "neur", str(i + 1), f"c{i+1}", "stn", "lead1", cid, "", "true", ""]
           for i, cid in enumerate(CONTACTS)])
    write("windows.csv",
          ["study_id", "session", "condition", "t_start_s", "t_end_s",
           "derived_from", "status", "notes"],
          [[SID, SES, "overt", "0.5", "2.0", "microphone", "in_use", ""],
           [SID, SES, "rest", "2.0", "3.5", "microphone", "under_revision", ""]])
    return base


@pytest.fixture
def session(session_root, configs):
    with open_session(SID, SES, manifest=load_manifest(session_root / "manifest"),
                      configs=configs, data_dir=session_root / "data") as s:
        yield s


def test_leads_resolve_from_the_manifest(session):
    lead = session.leads()["lead1"]
    assert lead.target == "stn"
    assert lead.contact_ids == tuple(CONTACTS)
    assert lead.stream == "neur"


def test_manifest_channel_indices_are_one_based(session):
    """The manifest numbers channels as the hardware does; the reader is 0-based."""
    assert session.leads()["lead1"].channel_indices == tuple(range(8))


def test_missing_rotation_is_visible_and_blocks_direction_claims(session):
    assert session.leads()["lead1"].has_rotation is False


def test_conditions_come_from_the_windows_table(session):
    assert session.conditions() == ("overt", "rest")


def test_row_labels_follow_geometry_not_row_numbering(session):
    """Upper segments must not be labeled lower; finding-level claims depend on it."""
    assert session.contact_rows("lead1") == (
        "ventral_ring",
        "lower_segments", "lower_segments", "lower_segments",
        "upper_segments", "upper_segments", "upper_segments",
        "dorsal_ring",
    )


def test_derived_signal_carries_its_provenance(session):
    sig = session.read_derived("lead1", "bipolar_vertical", tmin=0.0, tmax=1.0)
    assert sig.scheme == "bipolar_vertical"
    assert sig.data.shape[0] == len(sig.names)
    assert sig.usable_bandwidth_hz == pytest.approx(sig.sfreq_hz * 0.4)


def test_derivation_rows_label_by_leading_contact(session):
    sig = session.read_derived("lead1", "bipolar_vertical", tmin=0.0, tmax=1.0)
    rows = dict(zip(sig.names, sig.rows, strict=False))
    assert rows["2a-1"] == "lower_segments"
    assert rows["3a-4"] == "upper_segments"


def test_decimation_is_applied_after_referencing(session):
    """Filtering the derived signal, not channels about to be subtracted."""
    full = session.read_derived("lead1", "bipolar_vertical", tmin=0.0, tmax=2.0)
    dec = session.read_derived(
        "lead1", "bipolar_vertical", tmin=0.0, tmax=2.0, sfreq_target_hz=500
    )
    assert dec.decimation_factor == 4
    assert dec.decimation_stages == 1
    assert dec.sfreq_hz == pytest.approx(full.sfreq_hz / 4)
    assert dec.data.shape[0] == full.data.shape[0]


def test_every_scheme_loads(session):
    for scheme in ("monopolar", "bipolar_vertical", "bipolar_horizontal",
                   "bipolar_adjacent", "car"):
        sig = session.read_derived("lead1", scheme, tmin=0.0, tmax=0.5)
        assert sig.data.shape[1] > 0


def test_excluded_channels_are_absent(session_root, configs):
    """Silence is exclusion: a channel marked out never reaches the montage."""
    m = session_root / "manifest"
    rows = list(csv.reader((m / "channels.csv").open()))
    original = [r[:] for r in rows]
    rows[1][9], rows[1][10] = "false", "test exclusion"
    with (m / "channels.csv").open("w", newline="") as f:
        csv.writer(f).writerows(rows)
    try:
        with open_session(SID, SES, manifest=load_manifest(m), configs=configs,
                          data_dir=session_root / "data") as s:
            assert "1" not in s.leads()["lead1"].contact_ids
            sig = s.read_derived("lead1", "bipolar_vertical", tmin=0.0, tmax=0.5)
            assert all("-1" not in n for n in sig.names)
            assert any("not available" in n for n in sig.notes)
    finally:
        with (m / "channels.csv").open("w", newline="") as f:
            csv.writer(f).writerows(original)


def test_unknown_subject_names_the_key(session_root, configs):
    with pytest.raises(KeyError, match="no subjects.csv row"):
        open_session("NOPE", SES, manifest=load_manifest(session_root / "manifest"),
                     configs=configs, data_dir=session_root / "data")


def test_bipolar_output_differs_from_monopolar(session):
    mono = session.read_derived("lead1", "monopolar", tmin=0.0, tmax=1.0)
    bip = session.read_derived("lead1", "bipolar_vertical", tmin=0.0, tmax=1.0)
    assert not np.allclose(mono.data[:7], bip.data)
