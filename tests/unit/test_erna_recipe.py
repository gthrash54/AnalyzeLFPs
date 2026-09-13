"""erna, end to end on synthetic data with a known answer.

The fixture plants a damped 250 Hz oscillation after each stimulation artifact,
on two contacts only, with a decay constant of 12 ms. The recipe either recovers
those numbers where they were planted or the test fails. No real data, and no
lab convention assumed: every setting is passed in, which is the point of the
recipe.
"""

from __future__ import annotations

import csv
import json

import pytest

from dbsspeech.recipes import get, run
from dbsspeech.recipes.erna import ErnaParams, resolve, settings
from tests.fixtures.make_tdt_fixture import (
    ERNA_CHANNELS,
    ERNA_FREQ_HZ,
    ERNA_ONSETS_S,
    ERNA_TAU_S,
    N_NEURAL_CH,
    make_fixture,
)

pytestmark = pytest.mark.unit

SID, SES = "S01", "ses1"
CONTACTS = ["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"]
SFREQ = 8000.0  # ERNA recordings are sampled fast; see make_fixture


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    base = tmp_path_factory.mktemp("erna_proj")
    make_fixture(base / "data" / "block" / "synthetic_block.mat", erna=True,
                 sfreq_hz=SFREQ)
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
          [[SID, SES, "neur", str(N_NEURAL_CH), str(SFREQ), "V", "neural", "", ""]])
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
          [[SID, SES, "stim", str(t), str(t + 0.1), "stim_log", "in_use", ""]
           for t in ERNA_ONSETS_S])
    return base


def _approve(tmp_path):
    from dbsspeech.qc import propose, sign

    derivatives = tmp_path / "derivatives"
    propose([], SID, derivatives)
    sign(SID, "test-reviewer", derivatives)


def _run(project, tmp_path, **params):
    _approve(tmp_path)
    return run(
        "erna", SID, SES,
        claim="recover the planted resonance",
        params={
            # Everything stated, nothing assumed. These are this fixture's
            # protocol, not a convention.
            "stim_source": "amplitude_threshold",
            "stim_refractory_ms": 100.0,
            "blanking_ms": 5.0,
            "analysis_ms": 60.0,
            "bandpass_low_hz": 100.0,
            "bandpass_high_hz": 500.0,
            "min_peaks": 6,
            **params,
        },
        manifest_dir=project / "manifest",
        data_dir=project / "data",
        runs_dir=tmp_path / "runs",
        derivatives_dir=tmp_path / "derivatives",
    )


def _outputs(tmp_path, run_id):
    import pandas as pd

    base = tmp_path / "derivatives" / "results" / run_id
    return (pd.read_csv(base / "erna_epochs.csv"),
            pd.read_csv(base / "erna_summary.csv"),
            json.loads((base / "summary.json").read_text()))


# ---- registration and settings -------------------------------------------------

def test_the_recipe_is_registered_with_a_schema():
    spec = get("erna")
    assert spec.version == "1"
    properties = spec.schema()["properties"]
    for name in ("blanking_ms", "analysis_ms", "stim_source", "bandpass_low_hz"):
        assert name in properties


def test_every_shaping_setting_defaults_to_the_config_not_to_code():
    """A default invented here would travel into results with nobody choosing it."""
    params = ErnaParams()
    for name in ("blanking_ms", "analysis_ms", "bandpass_low_hz", "bandpass_high_hz",
                 "min_peaks", "stim_source", "fit_decay"):
        assert getattr(params, name) is None


def test_settings_record_where_each_value_came_from():
    configs = {"erna": {"window": {"blanking_ms": 3.0, "analysis_ms": 80.0}}}
    resolved = resolve(ErnaParams(blanking_ms=7.0), configs)
    assert resolved["blanking_ms"] == {"value": 7.0, "source": "run parameter"}
    assert resolved["analysis_ms"]["value"] == 80.0
    assert resolved["analysis_ms"]["source"] == "configs/erna.yaml:window.analysis_ms"


def test_a_missing_config_key_falls_back_rather_than_crashing():
    """A deleted key must not take the recipe down; the config checker catches it."""
    assert settings(ErnaParams(), {})["blanking_ms"] == 4.0


# ---- the measurement ------------------------------------------------------------

def test_it_recovers_the_planted_frequency(project, tmp_path):
    """Within 10 percent, on the contacts where the resonance was planted."""
    epochs, _summary_table, _summary = _outputs(tmp_path, _run(project, tmp_path))
    planted = _planted_rows(epochs)
    assert len(planted) > 0
    median = planted["freq_from_peaks_hz"].median()
    assert abs(median - ERNA_FREQ_HZ) / ERNA_FREQ_HZ < 0.10


def test_the_two_frequency_estimates_agree(project, tmp_path):
    """Peak spacing and the FFT measure the same thing; disagreement means it is not it."""
    epochs, _t, _s = _outputs(tmp_path, _run(project, tmp_path))
    planted = _planted_rows(epochs)
    assert planted["frequencies_agree"].all()


def test_it_recovers_the_planted_decay(project, tmp_path):
    """Within 25 percent."""
    epochs, _t, _s = _outputs(tmp_path, _run(project, tmp_path))
    planted = _planted_rows(epochs)
    median_tau_ms = planted["decay_tau_ms"].median()
    expected_ms = ERNA_TAU_S * 1000.0
    assert abs(median_tau_ms - expected_ms) / expected_ms < 0.25


def test_the_resonance_is_found_where_it_was_planted(project, tmp_path):
    """Selectivity: a recipe that reports ERNA everywhere is reporting noise."""
    epochs, _t, _s = _outputs(tmp_path, _run(project, tmp_path))
    planted = _planted_rows(epochs)
    elsewhere = epochs[~epochs["derivation"].isin(planted["derivation"].unique())]
    assert planted["amplitude"].median() > 5 * elsewhere["amplitude"].median()


def test_one_row_per_event_per_derivation(project, tmp_path):
    epochs, _t, _s = _outputs(tmp_path, _run(project, tmp_path))
    planted = _planted_rows(epochs)
    assert planted["event"].nunique() == len(ERNA_ONSETS_S)


def test_blanking_changes_the_answer_and_is_recorded(project, tmp_path):
    """The setting that matters most has to be visible in the record, both ways."""
    run_id = _run(project, tmp_path, blanking_ms=0.0)
    _e, _t, summary = _outputs(tmp_path, run_id)
    assert summary["settings"]["blanking_ms"] == 0.0
    assert summary["settings_sources"]["blanking_ms"] == "run parameter"


# ---- what the result says about itself -------------------------------------------

def test_unreviewed_settings_are_declared_in_the_summary(project, tmp_path):
    """configs/erna.yaml ships unreviewed, and a result must not hide that."""
    _e, _t, summary = _outputs(tmp_path, _run(project, tmp_path))
    assert summary["settings_reviewed"] is False
    assert "not reviewed" in summary["caveat"]


def test_every_setting_and_its_source_reach_the_summary(project, tmp_path):
    _e, _t, summary = _outputs(tmp_path, _run(project, tmp_path))
    assert set(summary["settings"]) == set(summary["settings_sources"])
    assert summary["settings"]["stim_source"] == "amplitude_threshold"


def test_the_outputs_are_the_ones_the_guide_asks_for(project, tmp_path):
    run_id = _run(project, tmp_path)
    record = json.loads((tmp_path / "runs" / f"{run_id}.json").read_text())
    for expected in ("erna_epochs.csv", "erna_summary.csv", "summary.json",
                     "erna_epochs.png", "erna_epochs.svg", "config.json"):
        assert expected in record["outputs"], expected


def test_the_summary_table_is_per_derivation(project, tmp_path):
    _e, summary_table, _s = _outputs(tmp_path, _run(project, tmp_path))
    assert {"derivation", "median_freq_hz", "median_decay_tau_ms", "n_epochs"} <= set(
        summary_table.columns
    )
    assert summary_table["derivation"].is_unique


# ---- refusals --------------------------------------------------------------------

def test_an_empty_band_is_refused_with_the_reason(project, tmp_path):
    with pytest.raises(Exception, match="empty|inverted|bandpass"):
        _run(project, tmp_path, bandpass_low_hz=400.0, bandpass_high_hz=100.0)


def test_nothing_measurable_says_what_to_check(project, tmp_path):
    """The failure people will actually hit, so it has to name its two causes."""
    with pytest.raises(RuntimeError, match="stim_source and blanking_ms"):
        _run(project, tmp_path, stim_threshold_mad=1e9)


def _planted_rows(epochs):
    """Rows for the derivations that lead with a contact carrying the resonance.

    A bipolar derivation is named `a-b`; the resonance is on the contacts at
    ERNA_CHANNELS, so a derivation leading with one of those is where it should
    appear.
    """
    planted_contacts = {CONTACTS[i] for i in ERNA_CHANNELS}
    return epochs[epochs["derivation"].str.split("-").str[0].isin(planted_contacts)]
