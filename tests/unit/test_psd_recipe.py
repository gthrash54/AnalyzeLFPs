"""psd_by_condition, end to end on synthetic data.

The fixture plants a 20 Hz signal on two contacts only, so the recipe either
recovers it where it was planted or the test fails. No real data.
"""

from __future__ import annotations

import csv
import json

import pytest

from dbsspeech.guardrails import GuardrailBlocked
from dbsspeech.recipes import get, run
from dbsspeech.recipes.psd import PsdParams
from tests.fixtures.make_tdt_fixture import (
    BETA_HZ,
    N_NEURAL_CH,
    SFREQ_NEURAL,
    make_fixture,
)

pytestmark = pytest.mark.unit

SID, SES = "S01", "ses1"
CONTACTS = ["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    base = tmp_path_factory.mktemp("proj")
    make_fixture(base / "data" / "block" / "synthetic_block.mat")
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
          [[SID, SES, "overt", "0.0", "2.0", "microphone", "in_use", ""],
           [SID, SES, "metro", "2.0", "4.0", "emg", "in_use", ""]])
    return base


def _approve(tmp_path):
    """Take the fixture subject through detection and sign-off.

    Tests exercise the real gate rather than disabling it, because the gate is
    the property most worth not breaking by accident.
    """
    from dbsspeech.qc import propose, sign

    derivatives = tmp_path / "derivatives"
    propose([], SID, derivatives)          # clean recording: detection found nothing
    sign(SID, "test-reviewer", derivatives)


def _run(project, tmp_path, overrides=None, **params):
    _approve(tmp_path)
    return run(
        "psd_by_condition", SID, SES,
        claim="test run",
        overrides=overrides,
        params={"fmax": 200.0, "sfreq_target_hz": SFREQ_NEURAL, **params},
        manifest_dir=project / "manifest",
        data_dir=project / "data",
        runs_dir=tmp_path / "runs",
        derivatives_dir=tmp_path / "derivatives",
    )


def _record(tmp_path, rid):
    return json.loads((tmp_path / "runs" / f"{rid}.json").read_text())


def test_recipe_is_registered_with_a_schema():
    spec = get("psd_by_condition")
    assert spec.version == "1"
    assert "primary_reference" in spec.schema()["properties"]


def test_defaults_are_the_decided_ones():
    p = PsdParams()
    assert p.unit == "window"
    assert p.primary_reference == "bipolar_vertical"
    assert p.sfreq_target_hz == 8138.0
    assert p.method == "welch"
    assert p.window_s == 1.0
    assert p.baseline_center == "grand_mean"
    assert p.baseline_scale == "pooled_within_condition"


def test_a_run_produces_tables_figures_and_a_record(project, tmp_path):
    rid = _run(project, tmp_path)
    rec = _record(tmp_path, rid)
    assert rec["status"] == "ok"
    for expected in ("psd_long.parquet", "psd_by_row.csv", "psd_by_region.csv",
                     "montage_spread.csv", "summary.json", "psd_db.png",
                     "montage_comparison.png", "config.json"):
        assert expected in rec["outputs"], expected


def test_every_montage_is_computed(project, tmp_path):
    rid = _run(project, tmp_path)
    assert len(_record(tmp_path, rid)["summary"]["schemes"]) == 5


def test_both_units_are_reported(project, tmp_path):
    """Guardrail G8: dB alone lets dynamic range read as effect size."""
    import pandas as pd

    rid = _run(project, tmp_path)
    long = pd.read_parquet(tmp_path / "derivatives" / "results" / rid / "psd_long.parquet")
    assert {"db", "z"} <= set(long.columns)
    assert long["db"].notna().all()


def test_the_planted_signal_is_found_where_it_was_planted(project, tmp_path):
    """The fixture puts 20 Hz on contacts 1 and 2a only."""
    import pandas as pd

    rid = _run(
        project, tmp_path,
        references=["monopolar"], primary_reference="monopolar",
        overrides={"G1_shared_reference_common_mode": "checking a planted signal per contact"},
    )
    long = pd.read_parquet(tmp_path / "derivatives" / "results" / rid / "psd_long.parquet")
    near = long[(long["freq_hz"] - BETA_HZ).abs() < 1.5]
    by_contact = near.groupby("derivation")["db"].mean().sort_values(ascending=False)
    assert set(by_contact.index[:2]) == {"1", "2a"}, by_contact.to_dict()


def test_per_row_aggregate_exists(project, tmp_path):
    import pandas as pd

    rid = _run(project, tmp_path)
    by_row = pd.read_csv(tmp_path / "derivatives" / "results" / rid / "psd_by_row.csv")
    assert set(by_row["row"].unique()) & {"lower_segments", "upper_segments"}


def test_scoping_to_one_lead_and_condition(project, tmp_path):
    rid = _run(project, tmp_path, leads=["lead1"], conditions=["overt"])
    assert _record(tmp_path, rid)["summary"]["conditions"] == ["overt"]


def test_pseudo_epochs_give_more_segments_than_one_window(project, tmp_path):
    import pandas as pd

    a = _run(project, tmp_path, unit="window", conditions=["overt"])
    b = _run(project, tmp_path, unit="pseudo_epoch", epoch_s=0.5, window_s=0.5,
             conditions=["overt"])
    read = lambda r: pd.read_parquet(  # noqa: E731
        tmp_path / "derivatives" / "results" / r / "psd_long.parquet"
    )
    assert len(read(b)) > len(read(a))


def test_monopolar_as_primary_is_blocked(project, tmp_path):
    """Guardrail G1 fires before anything is computed."""
    with pytest.raises(GuardrailBlocked, match="common-mode"):
        _run(project, tmp_path, primary_reference="monopolar")


def test_monopolar_primary_proceeds_when_overridden(project, tmp_path):
    _approve(tmp_path)
    rid = run(
        "psd_by_condition", SID, SES,
        claim="deliberate montage comparison",
        params={"primary_reference": "monopolar", "fmax": 200.0,
                "sfreq_target_hz": SFREQ_NEURAL},
        overrides={"G1_shared_reference_common_mode": "montage comparison"},
        manifest_dir=project / "manifest",
        data_dir=project / "data",
        runs_dir=tmp_path / "runs",
        derivatives_dir=tmp_path / "derivatives",
    )
    rec = _record(tmp_path, rid)
    assert rec["guardrails"]["overrides"][0]["reason"] == "montage comparison"


def test_a_band_above_the_cutoff_is_refused(project, tmp_path):
    """Guardrail G6, not overridable: fmax above 0.4x the target rate."""
    with pytest.raises(GuardrailBlocked, match="usable bandwidth"):
        _run(project, tmp_path, fmax=900.0, sfreq_target_hz=1000.0)


def test_summary_reports_the_montage_spread(project, tmp_path):
    rid = _run(project, tmp_path)
    summary = _record(tmp_path, rid)["summary"]
    assert summary["montage_spread_db_max"] is not None
    assert summary["primary_reference"] == "bipolar_vertical"


def test_input_is_keyed_not_pathed(project, tmp_path):
    rid = _run(project, tmp_path)
    entry = _record(tmp_path, rid)["inputs"][0]
    assert entry["key"] == {"study_id": SID, "session": SES}
    assert entry["sha256"]


# ---- B7. the branch named welch computes welch --------------------------------

def test_the_welch_branch_matches_scipy_welch():
    """scipy.signal.spectrogram defaults to ("tukey_periodic", 0.25) while
    scipy.signal.welch defaults to Hann, so the branch named "welch" was
    computing something else. Measured before the fix: a median 11.9 percent
    difference from scipy.signal.welch on the same data.

    Asserted against the library rather than against a stored number, so this
    keeps holding if scipy changes its defaults again.
    """
    import numpy as np
    from scipy.signal import welch

    from dbsspeech.recipes.psd import PsdParams, _segment_spectra

    rng = np.random.default_rng(0)
    sfreq = 1000.0
    data = rng.standard_normal((2, 8000))
    params = PsdParams(method="welch", window_s=1.0, fmin=1.0, fmax=200.0)

    freqs, power = _segment_spectra(data, sfreq, params)
    ours = power.mean(axis=1)              # (channels, freqs), averaged segments

    nperseg = int(round(params.window_s * sfreq))
    f_ref, p_ref = welch(data, fs=sfreq, nperseg=nperseg, noverlap=nperseg // 2)
    keep = (f_ref >= params.fmin) & (f_ref <= params.fmax)

    np.testing.assert_allclose(freqs, f_ref[keep], rtol=0, atol=1e-12)
    np.testing.assert_allclose(ours, p_ref[:, keep], rtol=1e-9)


def test_a_tukey_taper_would_not_have_passed_that():
    """Guard the guard: show the assertion above is not vacuous by checking the
    library default really does differ."""
    import numpy as np
    from scipy.signal import spectrogram, welch

    rng = np.random.default_rng(0)
    sfreq, x = 1000.0, rng.standard_normal(8000)
    nperseg = 1000

    _, p_welch = welch(x, fs=sfreq, nperseg=nperseg, noverlap=nperseg // 2)
    _, _, s_default = spectrogram(x, fs=sfreq, nperseg=nperseg,
                                  noverlap=nperseg // 2, mode="psd")
    p_default = s_default.mean(axis=1)
    median_rel = float(np.median(np.abs(p_welch - p_default) / p_welch))
    assert median_rel > 0.05, "the library default no longer differs; revisit B7"


def test_both_methods_segment_the_same_way():
    """B7b. welch overlapped by 50 percent and multitaper not at all, so the same
    recording gave the two methods different segment counts, and db_sd, and
    therefore z, was not comparable between them."""
    import numpy as np

    from dbsspeech.recipes.psd import PsdParams, _segment_spectra

    rng = np.random.default_rng(1)
    sfreq = 1000.0
    data = rng.standard_normal((2, 6000))

    _, welch_power = _segment_spectra(
        data, sfreq, PsdParams(method="welch", window_s=1.0, fmin=1.0, fmax=100.0)
    )
    _, mt_power = _segment_spectra(
        data, sfreq, PsdParams(method="multitaper", window_s=1.0, fmin=1.0, fmax=100.0)
    )
    assert welch_power.shape[1] == mt_power.shape[1], (
        f"welch gave {welch_power.shape[1]} segments, "
        f"multitaper gave {mt_power.shape[1]}"
    )


# ---- D5. one long table, one frequency grid ----------------------------------

def test_an_epoch_shorter_than_the_spectral_window_is_refused():
    """Frequency resolution is 1 / window_s, and an epoch cannot supply more
    resolution than its own length. This used to be accepted and silently
    resolved by shrinking nperseg, which gave those rows their own frequency
    grid."""
    from dbsspeech.recipes.psd import PsdParams

    with pytest.raises(ValueError, match="too short to hold"):
        PsdParams(unit="pseudo_epoch", epoch_s=0.5, window_s=1.0)


def test_the_same_pairing_is_refused_for_bandpower():
    from dbsspeech.recipes.bandpower import BandpowerParams

    with pytest.raises(ValueError, match="too short to hold"):
        BandpowerParams(unit="pseudo_epoch", epoch_s=0.2, window_s=1.0)


def test_matching_epoch_and_window_are_accepted():
    from dbsspeech.recipes.psd import PsdParams

    assert PsdParams(unit="pseudo_epoch", epoch_s=0.5, window_s=0.5).window_s == 0.5
    assert PsdParams(unit="pseudo_epoch", epoch_s=2.0, window_s=1.0).epoch_s == 2.0


def test_window_mode_does_not_care_about_epoch_s():
    """epoch_s is unused in window mode, so it must not constrain anything."""
    from dbsspeech.recipes.psd import PsdParams

    assert PsdParams(unit="window", epoch_s=0.1, window_s=1.0).window_s == 1.0


def test_a_stretch_shorter_than_nperseg_is_refused_by_the_spectra_helper():
    """The backstop under the validator. Clamping here is what made the split
    invisible: the caller got a spectrum on a grid it did not ask for."""
    import numpy as np

    from dbsspeech.recipes.psd import PsdParams, _segment_spectra

    params = PsdParams(window_s=1.0)
    short = np.zeros((2, 400))            # 0.4 s at 1000 Hz
    with pytest.raises(ValueError, match="shorter than"):
        _segment_spectra(short, 1000.0, params)


def test_requested_nperseg_is_one_definition():
    """Two recipes and the skip checks all have to agree on this number; a
    disagreement is what put two grids in one table."""
    from dbsspeech.recipes.psd import PsdParams, requested_nperseg

    assert requested_nperseg(1000.0, PsdParams(window_s=1.0)) == 1000
    assert requested_nperseg(500.0, PsdParams(window_s=2.0)) == 1000
    # Floored, so a tiny window still gives a usable segment.
    assert requested_nperseg(100.0, PsdParams(window_s=0.01)) == 16
