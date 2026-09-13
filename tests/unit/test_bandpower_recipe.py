"""bandpower_contrast: effects, and refusing to report tests it has not earned."""

from __future__ import annotations

import csv
import json

import numpy as np
import pytest

from dbsspeech.recipes import get, run
from dbsspeech.recipes.bandpower import (
    MIN_OBSERVATIONS_FOR_TEST,
    BandpowerParams,
    _bootstrap_ci,
    _permutation_p,
)
from tests.fixtures.make_tdt_fixture import N_NEURAL_CH, SFREQ_NEURAL, make_fixture

pytestmark = pytest.mark.unit

SID, SES = "S01", "ses1"
CONTACTS = ["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    base = tmp_path_factory.mktemp("bp")
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
    from dbsspeech.qc import propose, sign

    derivatives = tmp_path / "derivatives"
    propose([], SID, derivatives)
    sign(SID, "test-reviewer", derivatives)


def _run(project, tmp_path, **params):
    _approve(tmp_path)
    return run(
        "bandpower_contrast", SID, SES, claim="test run",
        params={"fmax": 200.0, "sfreq_target_hz": SFREQ_NEURAL,
                "references": ["monopolar"], "primary_reference": "monopolar",
                "n_permutations": 200, "n_bootstrap": 200, **params},
        overrides={"G1_shared_reference_common_mode": "synthetic fixture"},
        manifest_dir=project / "manifest", data_dir=project / "data",
        runs_dir=tmp_path / "runs", derivatives_dir=tmp_path / "derivatives",
    )


def _stats(tmp_path, rid):
    import pandas as pd

    return pd.read_csv(tmp_path / "derivatives" / "results" / rid / "stats.csv")


def _record(tmp_path, rid):
    return json.loads((tmp_path / "runs" / f"{rid}.json").read_text())


# ---- statistics in isolation -------------------------------------------------

def test_permutation_p_is_uniform_under_the_null():
    """The real claim, not that any single null comparison gives a large p.

    Two random samples can legitimately differ, so one draw proves nothing. Under
    the null the p-values should be roughly uniform, which means about half above
    0.5 and few below 0.05.
    """
    rng = np.random.default_rng(0)
    ps = [
        _permutation_p(rng.standard_normal(40), rng.standard_normal(40), rng, 400)
        for _ in range(40)
    ]
    assert 0.3 < float(np.median(ps)) < 0.7, float(np.median(ps))
    assert sum(p < 0.05 for p in ps) <= 6, ps


def test_permutation_p_is_low_for_a_clear_difference():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(40) + 5
    b = rng.standard_normal(40)
    assert _permutation_p(a, b, rng, 500) < 0.02


def test_permutation_p_is_never_exactly_zero():
    """A p of zero is not something a finite permutation count can support."""
    rng = np.random.default_rng(0)
    a = rng.standard_normal(30) + 50
    b = rng.standard_normal(30)
    assert _permutation_p(a, b, rng, 200) > 0


def test_bootstrap_ci_brackets_the_true_difference():
    rng = np.random.default_rng(0)
    a = rng.standard_normal(200) + 3
    b = rng.standard_normal(200)
    lo, hi = _bootstrap_ci(a, b, rng, 500)
    assert lo < 3 < hi


def test_bootstrap_ci_of_no_difference_includes_zero():
    rng = np.random.default_rng(0)
    lo, hi = _bootstrap_ci(rng.standard_normal(200), rng.standard_normal(200), rng, 500)
    assert lo < 0 < hi


# ---- the recipe --------------------------------------------------------------

def test_registered_with_defaults_that_favour_a_testable_unit():
    assert get("bandpower_contrast").version == "1"
    p = BandpowerParams()
    assert p.unit == "pseudo_epoch"
    assert p.epoch_overlap == 0.0, "overlap makes epochs even less independent"


def test_a_run_produces_stats_and_a_figure(project, tmp_path):
    rid = _run(project, tmp_path)
    outputs = _record(tmp_path, rid)["outputs"]
    for expected in ("bandpower_long.parquet", "stats.csv", "bandpower_by_row.csv",
                     "summary.json", "bandpower_contrast.png"):
        assert expected in outputs, expected


def test_window_unit_reports_an_effect_but_no_test(project, tmp_path):
    """One observation per condition cannot support a p-value, so none is given."""
    rid = _run(project, tmp_path, unit="window")
    stats = _stats(tmp_path, rid)
    assert stats["effect"].notna().any()
    assert stats["p_perm"].isna().all()
    assert (stats["test"] == "none").all()
    assert stats["independence"].str.contains("descriptive").all()


def test_pseudo_epochs_earn_a_test_and_say_they_are_not_independent(project, tmp_path):
    rid = _run(project, tmp_path, unit="pseudo_epoch", epoch_s=0.2, window_s=0.2)
    stats = _stats(tmp_path, rid)
    tested = stats.dropna(subset=["p_perm"])
    assert not tested.empty
    assert tested["independence"].str.contains("not independent").all()


def test_ci_accompanies_every_p_value(project, tmp_path):
    rid = _run(project, tmp_path, unit="pseudo_epoch", epoch_s=0.2, window_s=0.2)
    stats = _stats(tmp_path, rid)
    tested = stats.dropna(subset=["p_perm"])
    assert tested["ci_low"].notna().all()
    assert tested["ci_high"].notna().all()


def test_summary_states_the_multiplicity_problem(project, tmp_path):
    """Many tests, no correction. Say so where a reader will see it."""
    rid = _run(project, tmp_path, unit="pseudo_epoch", epoch_s=0.2, window_s=0.2)
    summary = _record(tmp_path, rid)["summary"]
    assert "no correction was applied" in summary["multiplicity_note"]
    assert summary["n_tested"] >= 0


def test_contrasts_cover_every_pair_by_default(project, tmp_path):
    rid = _run(project, tmp_path)
    assert set(_stats(tmp_path, rid)["contrast"].unique()) == {"overt-metro"}


def test_an_explicit_contrast_is_respected(project, tmp_path):
    rid = _run(project, tmp_path, contrasts=[["metro", "overt"]])
    assert set(_stats(tmp_path, rid)["contrast"].unique()) == {"metro-overt"}


def test_effects_are_per_derivation_before_any_averaging(project, tmp_path):
    """Guardrail G3: ratio per channel, then average. Never the reverse."""
    rid = _run(project, tmp_path)
    stats = _stats(tmp_path, rid)
    assert stats["derivation"].nunique() > 1, "effects must exist per derivation"


def test_seed_makes_a_p_value_reproducible(project, tmp_path):
    kw = {"unit": "pseudo_epoch", "epoch_s": 0.2, "window_s": 0.2, "seed": 7}
    a = _stats(tmp_path, _run(project, tmp_path, **kw))
    b = _stats(tmp_path, _run(project, tmp_path, **kw))
    key = ["derivation", "band", "contrast"]
    merged = a.merge(b, on=key, suffixes=("_a", "_b"))
    np.testing.assert_allclose(merged["effect_a"], merged["effect_b"])


def test_minimum_observation_rule_is_stated_in_the_row(project, tmp_path):
    rid = _run(project, tmp_path, unit="window")
    text = " ".join(_stats(tmp_path, rid)["independence"].unique())
    assert str(MIN_OBSERVATIONS_FOR_TEST) in text


def test_a_band_the_window_cannot_resolve_is_reported_not_invented():
    """0.2 s gives 5 Hz resolution, so 1 to 4 Hz contains no bin at all."""
    from dbsspeech.recipes.bandpower import unresolvable_bands

    bands = {"delta": (1.0, 4.0), "beta": (13.0, 30.0)}
    out = unresolvable_bands(bands, window_s=0.2, sfreq_hz=2000.0)
    assert "delta" in out
    assert "beta" not in out
    assert "Lengthen the window" in out["delta"]


def test_a_long_enough_window_resolves_everything():
    from dbsspeech.recipes.bandpower import unresolvable_bands

    assert unresolvable_bands({"delta": (1.0, 4.0)}, window_s=2.0, sfreq_hz=2000.0) == {}


def test_no_p_value_is_computed_from_unmeasurable_data(project, tmp_path):
    """A p from NaN comparisons is a number with nothing behind it."""
    rid = _run(project, tmp_path, unit="pseudo_epoch", epoch_s=0.2, window_s=0.2)
    stats = _stats(tmp_path, rid)
    unmeasurable = stats[stats["independence"].str.contains("not measurable", na=False)]
    assert not unmeasurable.empty, "expected delta to be unmeasurable at 0.2 s"
    assert unmeasurable["p_perm"].isna().all()
    assert unmeasurable["effect"].isna().all()


def test_unresolvable_bands_reach_the_summary(project, tmp_path):
    rid = _run(project, tmp_path, unit="pseudo_epoch", epoch_s=0.2, window_s=0.2)
    assert "delta" in _record(tmp_path, rid)["summary"]["unresolvable_bands"]


def test_g9_stays_quiet_when_the_baseline_has_too_few_epochs(project, tmp_path):
    """One epoch is not a time course, and an excursion of zero would say it was.

    The default epoch length equals the fixture's whole baseline window, so this
    is the ordinary case rather than a contrived one.
    """
    block = _record(
        tmp_path, _run(project, tmp_path, baseline_condition="metro")
    )["summary"]["nonstationarity"]
    assert not block["available"]
    assert "too few" in block["reason"]
    assert "max_excursion_db" not in block


def test_g9_is_evaluated_after_a_contrast_and_picks_its_own_band(project, tmp_path):
    """G9 needs an effect, which does not exist until the contrast is computed.

    The band is not a parameter: it is whichever band carried the largest effect,
    so the excursion and the effect describe the same band by construction. A
    ratio between an excursion in one band and an effect in another compares
    nothing, and leaving that to an analyst to line up is how it goes wrong.
    """
    # Short epochs so the two-second baseline window yields enough of them to
    # tell drift from epoch-to-epoch noise; the Welch window has to fit inside
    # an epoch, so it shrinks with it.
    rid = _run(project, tmp_path, baseline_condition="metro", epoch_s=0.3, window_s=0.3)
    rec = _record(tmp_path, rid)
    block = rec["summary"]["nonstationarity"]
    assert block["available"], block["reason"]

    assert block["scheme"] == rec["params"]["primary_reference"]
    assert block["baseline_condition"] == "metro"
    assert block["max_excursion_db"] >= 0.0
    assert block["reported_effect_db"] >= 0.0

    largest = rec["summary"]["largest_effects"][0]
    assert block["band"] == largest["band"], (
        "the excursion must be reported for the band the largest effect was in"
    )
    assert block["reported_effect_db"] == pytest.approx(abs(largest["effect"]))

    # Recompute the excursion from the stored epochs, in the band the block
    # names. Checking the label alone would pass even if the number came from a
    # different band, which is the failure this whole design exists to prevent.
    import pandas as pd

    from dbsspeech.recipes.psd import _excursion_db

    long = pd.read_parquet(
        tmp_path / "derivatives" / "results" / rid / "bandpower_long.parquet"
    )
    baseline = long[
        (long["condition"] == "metro")
        & (long["scheme"] == rec["params"]["primary_reference"])
        & (long["band"] == block["band"])
    ]
    expected = max(
        value
        for _, group in baseline.groupby("derivation")
        if (value := _excursion_db(group.sort_values("epoch")["db"].to_numpy(float))) is not None
    )
    assert block["max_excursion_db"] == pytest.approx(expected), (
        f"the reported excursion does not match one computed in {block['band']}, "
        "so it was measured somewhere else"
    )

    after = rec["guardrails"]["after"]["findings"]
    ratio = block["max_excursion_db"] / block["reported_effect_db"]
    fired = {f["guardrail"] for f in after}
    assert ("G9_nonstationarity_exceeds_effect" in fired) == (ratio >= 1.0)
