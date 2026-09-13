"""pynm_features: wrapping py_neuromodulation without letting it re-reference twice."""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest

from dbsspeech.recipes import get, run
from dbsspeech.recipes.pynm import (
    HEAVY_FEATURES,
    PynmParams,
    _feature_times_seconds,
    build_channels,
    label_conditions,
)
from tests.fixtures.make_tdt_fixture import N_NEURAL_CH, SFREQ_NEURAL, make_fixture

pytestmark = pytest.mark.unit

SID, SES = "S01", "ses1"
CONTACTS = ["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"]


# ---- pieces in isolation -----------------------------------------------------

def test_channels_frame_has_the_columns_they_require():
    frame = build_channels(["a-b", "c-d"], "stn")
    assert list(frame.columns) == [
        "name", "rereference", "used", "target", "type", "status", "new_name"
    ]


def test_their_rereferencing_is_switched_off():
    """We apply our own montage first; their default would apply a second one."""
    assert set(build_channels(["a"], "stn")["rereference"]) == {"None"}


def test_depth_and_cortical_channels_get_their_vocabulary():
    assert build_channels(["a"], "stn")["type"].iloc[0] == "dbs"
    assert build_channels(["a"], "gpi")["type"].iloc[0] == "dbs"
    assert build_channels(["a"], "ecog")["type"].iloc[0] == "ecog"


def test_condition_labels_follow_the_windows():
    times = np.array([0.5, 1.5, 2.5, 3.5])
    windows = [
        {"condition": "overt", "t_start_s": 1.0, "t_end_s": 2.0, "status": "in_use"},
        {"condition": "rest", "t_start_s": 3.0, "t_end_s": 4.0, "status": "under_revision"},
    ]
    labels, statuses = label_conditions(times, windows)
    assert labels == ["", "overt", "", "rest"]
    assert statuses[3] == "under_revision"


def test_rows_outside_every_window_are_kept_not_dropped():
    """A reader should see how much of the recording was in no condition."""
    labels, _ = label_conditions(np.array([0.0, 9.0]), [
        {"condition": "overt", "t_start_s": 1.0, "t_end_s": 2.0}
    ])
    assert labels == ["", ""]


def test_feature_times_are_normalized_against_the_recording_length():
    """Measured: their unit is milliseconds. Checked, not assumed."""
    import pandas as pd

    ms = pd.DataFrame({"time": [1000.0, 2000.0, 4000.0]})
    np.testing.assert_allclose(_feature_times_seconds(ms, 4.0), [1.0, 2.0, 4.0])

    seconds = pd.DataFrame({"time": [1.0, 2.0, 3.0]})
    np.testing.assert_allclose(_feature_times_seconds(seconds, 4.0), [1.0, 2.0, 3.0])


def test_an_unrecognizable_time_unit_refuses_rather_than_guesses():
    """A wrong unit mislabels every row's condition silently."""
    import pandas as pd

    absurd = pd.DataFrame({"time": [1e9]})
    with pytest.raises(ValueError, match="Refusing to guess"):
        _feature_times_seconds(absurd, 4.0)


def test_heavy_features_are_off_by_default():
    assert set(PynmParams().features or []) == set()
    assert "fooof" in HEAVY_FEATURES


# ---- the recipe --------------------------------------------------------------

@pytest.fixture(scope="module")
def project(tmp_path_factory):
    base = tmp_path_factory.mktemp("pynm")
    make_fixture(base / "data" / "block" / "block.mat")
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
          [[SID, SES, "lead1", "stn", "R", "unknown_directional_1331", "1", "8", "0", ""]])
    write("channels.csv",
          ["study_id", "session", "stream", "ch_index", "ch_name", "region",
           "lead_id", "lead_contact", "site", "include", "exclude_reason"],
          [[SID, SES, "neur", str(i + 1), f"c{i+1}", "stn", "lead1", cid, "", "true", ""]
           for i, cid in enumerate(CONTACTS)])
    write("windows.csv",
          ["study_id", "session", "condition", "t_start_s", "t_end_s",
           "derived_from", "status", "notes"],
          [[SID, SES, "overt", "0.5", "2.0", "microphone", "in_use", ""],
           [SID, SES, "metro", "2.0", "3.5", "emg", "in_use", ""]])
    return base


def _run(project, tmp_path, **params):
    from dbsspeech.qc import propose, sign

    propose([], SID, tmp_path / "derivatives")
    sign(SID, "test-reviewer", tmp_path / "derivatives")
    return run(
        "pynm_features", SID, SES, claim="test run",
        params={"sfreq_target_hz": SFREQ_NEURAL,
                "sampling_rate_features_hz": 5.0, **params},
        manifest_dir=project / "manifest", data_dir=project / "data",
        runs_dir=tmp_path / "runs", derivatives_dir=tmp_path / "derivatives",
    )


def _record(tmp_path, rid):
    return json.loads((tmp_path / "runs" / f"{rid}.json").read_text())


def test_registered():
    assert get("pynm_features").version == "1"


def test_a_run_produces_features_and_their_settings(project, tmp_path):
    rid = _run(project, tmp_path)
    outputs = _record(tmp_path, rid)["outputs"]
    assert "features.parquet" in outputs
    assert "pynm_settings.json" in outputs, "their settings must be reproducible"


def test_their_version_is_recorded(project, tmp_path):
    """A feature set is only comparable if you know which version produced it."""
    rid = _run(project, tmp_path)
    summary = _record(tmp_path, rid)["summary"]
    assert summary["py_neuromodulation_version"] != "unknown"


def test_the_run_records_that_their_rereferencing_was_off(project, tmp_path):
    rid = _run(project, tmp_path)
    assert "disabled" in _record(tmp_path, rid)["summary"]["their_rereferencing"]


def test_our_bands_drive_their_frequency_ranges(project, tmp_path):
    """Config over code has to survive the boundary into another library."""
    rid = _run(project, tmp_path)
    ranges = _record(tmp_path, rid)["summary"]["frequency_ranges_hz"]
    assert "beta" in ranges, ranges
    assert ranges["beta"] == [13.0, 30.0]


def test_features_are_labelled_by_condition(project, tmp_path):
    import pandas as pd

    rid = _run(project, tmp_path)
    frame = pd.read_parquet(tmp_path / "derivatives" / "results" / rid / "features.parquet")
    assert set(frame["condition"].unique()) >= {"overt", "metro"}
    assert "time_s" in frame.columns


def test_heavy_features_are_absent_unless_asked_for(project, tmp_path):
    rid = _run(project, tmp_path)
    enabled = _record(tmp_path, rid)["summary"]["features_enabled"]
    assert not set(enabled) & set(HEAVY_FEATURES)


def test_naming_features_enables_exactly_that_set(project, tmp_path):
    rid = _run(project, tmp_path, features=["welch", "linelength"])
    assert set(_record(tmp_path, rid)["summary"]["features_enabled"]) == {
        "welch", "linelength"
    }


def test_an_unknown_feature_names_the_available_ones(project, tmp_path):
    with pytest.raises(ValueError, match="available"):
        _run(project, tmp_path, features=["not_a_feature"])
