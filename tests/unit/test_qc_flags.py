"""QC detectors, against signals with defects planted deliberately.

Each test plants exactly one problem and asserts that detector finds it and the
clean channels do not. A detector that fires on clean data is worse than no
detector, because people learn to ignore it.
"""

from __future__ import annotations

import numpy as np
import pytest
import yaml

from dbsspeech.qc import Flag, detect_all
from dbsspeech.qc.flags import (
    amplitude_window,
    clipping,
    flat_channel,
    hf_noise_ratio,
    kurtosis_outlier,
    line_noise,
    trial_amplitude_outlier,
    variance_outlier,
)

pytestmark = pytest.mark.unit

SFREQ = 1000.0
N = 8
DURATION = 20


@pytest.fixture(scope="module")
def thresholds():
    return yaml.safe_load(open("configs/qc_thresholds.yaml"))


@pytest.fixture
def clean():
    """Eight well-behaved channels in one region."""
    rng = np.random.default_rng(0)
    data = rng.standard_normal((N, int(SFREQ * DURATION))) * 1e-5
    names = [f"c{i+1}" for i in range(N)]
    regions = ["stn"] * N
    return data, names, regions


def _targets(flags: list[Flag], flag_type: str) -> set[str]:
    return {f.target for f in flags if f.flag_type == flag_type}


# ---- clean data must stay quiet ---------------------------------------------

def test_clean_data_raises_nothing_but_possibly_line_noise(clean, thresholds):
    data, names, regions = clean
    flags = detect_all(data, SFREQ, names, regions, thresholds)
    unexpected = [f for f in flags if f.flag_type != "line_noise"]
    assert unexpected == [], [f.describe() for f in unexpected]


# ---- individual detectors ----------------------------------------------------

def test_flat_channel_is_caught(clean, thresholds):
    data, names, regions = clean
    data[3] *= 0.0001
    assert _targets(flat_channel(data, SFREQ, names, regions, thresholds),
                    "flat_channel") == {"c4"}


def test_variance_outlier_is_caught(clean, thresholds):
    data, names, regions = clean
    data[5] *= 40
    assert "c6" in _targets(variance_outlier(data, SFREQ, names, regions, thresholds),
                            "variance_outlier")


def test_high_frequency_noise_is_caught(clean, thresholds):
    data, names, regions = clean
    t = np.arange(data.shape[1]) / SFREQ
    data[1] += 3e-5 * np.sin(2 * np.pi * 150 * t)
    assert "c2" in _targets(hf_noise_ratio(data, SFREQ, names, regions, thresholds),
                            "hf_noise_ratio")


def test_line_noise_is_caught_and_proposes_a_notch(clean, thresholds):
    data, names, regions = clean
    t = np.arange(data.shape[1]) / SFREQ
    data[0] += 5e-5 * np.sin(2 * np.pi * 60 * t)
    flags = line_noise(data, SFREQ, names, regions, thresholds)
    hit = next(f for f in flags if f.target == "c1")
    assert hit.proposed_action == "notch", "line noise is expected in an OR; notch, do not exclude"
    assert hit.evidence["harmonic_hz"] == 60.0


def test_line_noise_respects_a_fifty_hertz_mains(clean, thresholds):
    data, names, regions = clean
    t = np.arange(data.shape[1]) / SFREQ
    data[0] += 5e-5 * np.sin(2 * np.pi * 50 * t)
    flags = line_noise(data, SFREQ, names, regions, thresholds, mains_hz=50.0)
    assert next(f for f in flags if f.target == "c1").evidence["mains_hz"] == 50.0


def test_clipping_is_caught(clean, thresholds):
    data, names, regions = clean
    rail = float(np.max(np.abs(data[4])))
    data[4, :2000] = rail
    assert _targets(clipping(data, SFREQ, names, regions, thresholds), "clipping") == {"c5"}


def test_amplitude_window_annotates_rather_than_cuts(clean, thresholds):
    """Never delete samples. A window flag is an annotation."""
    data, names, regions = clean
    data[6, 8000:9000] *= 60
    flags = amplitude_window(data, SFREQ, names, regions, thresholds)
    assert flags, "planted artifact not caught"
    hit = flags[0]
    assert hit.proposed_action == "annotate_window"
    assert hit.target_type == "window"
    assert hit.evidence["t_start_s"] == pytest.approx(8.0, abs=1.0)


def test_contiguous_windows_merge_into_one_episode(clean, thresholds):
    """An artifact is an episode, not five separate seconds."""
    data, names, regions = clean
    data[6, 8000:13000] *= 60          # five seconds of artifact
    flags = amplitude_window(data, SFREQ, names, regions, thresholds)
    on_channel = [f for f in flags if f.evidence["channel"] == "c7"]
    assert len(on_channel) == 1, [f.evidence for f in on_channel]
    assert on_channel[0].evidence["n_windows"] >= 4
    assert on_channel[0].evidence["t_end_s"] - on_channel[0].evidence["t_start_s"] >= 4


def test_separate_artifacts_stay_separate(clean, thresholds):
    data, names, regions = clean
    data[6, 2000:3000] *= 60
    data[6, 15000:16000] *= 60
    on_channel = [f for f in amplitude_window(data, SFREQ, names, regions, thresholds)
                  if f.evidence["channel"] == "c7"]
    assert len(on_channel) == 2


def test_kurtosis_statistic_is_duration_stable(thresholds):
    """The old whole-record statistic grew with length; this one must not."""
    from dbsspeech.qc.flags import _block_median_kurtosis

    rng = np.random.default_rng(0)
    long_signal = rng.standard_normal((2, int(SFREQ * 400))) * 1e-5
    short = long_signal[:, : int(SFREQ * 60)]
    k_short, _ = _block_median_kurtosis(short, SFREQ, 10.0)
    k_long, _ = _block_median_kurtosis(long_signal, SFREQ, 10.0)
    assert abs(float(np.median(k_long)) - float(np.median(k_short))) < 0.5


def test_a_single_transient_does_not_condemn_a_channel(clean, thresholds):
    """That is what the window detector is for; kurtosis judges typical blocks."""
    data, names, regions = clean
    data[2, 5000] = data[2].std() * 400
    assert kurtosis_outlier(data, SFREQ, names, regions, thresholds) == []


def test_a_persistently_heavy_tailed_channel_is_caught(clean, thresholds):
    data, names, regions = clean
    rng = np.random.default_rng(1)
    # Heavy tails in every block, not one excursion.
    data[2] = rng.standard_t(2.0, size=data.shape[1]) * 1e-5
    data[2, ::50] *= 30
    assert "c3" in _targets(kurtosis_outlier(data, SFREQ, names, regions, thresholds),
                            "kurtosis_outlier")


def test_trial_outlier_uses_the_condition_windows(clean, thresholds):
    data, names, regions = clean
    trials = [{"condition": f"c{i}", "t_start_s": i * 2, "t_end_s": i * 2 + 2} for i in range(8)]
    data[0, 4000:6000] *= 50  # third trial on channel one
    flags = trial_amplitude_outlier(data, SFREQ, names, regions, thresholds, trials)
    assert any(f.evidence["condition"] == "c2" for f in flags)


# ---- the guard the guide's own warning calls for -----------------------------

def test_too_few_channels_reports_evidence_but_proposes_nothing(thresholds):
    """Robust statistics over three contacts cannot support a threshold."""
    rng = np.random.default_rng(0)
    data = rng.standard_normal((3, 5000)) * 1e-5
    data[0] *= 50
    flags = variance_outlier(data, SFREQ, ["a", "b", "c"], ["stn"] * 3, thresholds)
    assert [f.flag_type for f in flags] == ["insufficient_channels"]
    assert flags[0].proposed_action == "", "must not propose an action it cannot support"
    assert flags[0].evidence["minimum_required"] == 4


def test_rings_are_not_judged_against_segments(thresholds):
    """A ring has twice a segment's surface area, so pooling them flags physics."""
    rng = np.random.default_rng(0)
    data = np.vstack([
        rng.standard_normal((2, 5000)) * 3e-5,   # two rings, naturally different
        rng.standard_normal((6, 5000)) * 1e-5,   # six segments
    ])
    names = [f"c{i+1}" for i in range(8)]
    regions = ["stn"] * 8
    kinds = ["ring"] * 2 + ["segment"] * 6

    pooled = variance_outlier(data, SFREQ, names, regions,
                              {**thresholds, "outlier_grouping": "region"})
    split = variance_outlier(data, SFREQ, names, regions, thresholds, kinds)

    assert any(f.flag_type == "variance_outlier" for f in pooled), "pooled should flag the rings"
    assert not any(f.flag_type == "variance_outlier" for f in split)
    # Two rings cannot support a threshold, and the detector says so.
    assert any(f.flag_type == "insufficient_channels" for f in split)


def test_outliers_are_judged_within_region_not_across(thresholds):
    """A quiet region must not make a normal channel in a loud region an outlier."""
    rng = np.random.default_rng(0)
    data = np.vstack([
        rng.standard_normal((4, 5000)) * 1e-5,   # stn
        rng.standard_normal((4, 5000)) * 1e-3,   # ecog, 100x larger by nature
    ])
    names = [f"c{i+1}" for i in range(8)]
    regions = ["stn"] * 4 + ["ecog"] * 4
    assert variance_outlier(data, SFREQ, names, regions, thresholds) == []


# ---- config behavior ---------------------------------------------------------

def test_a_disabled_detector_does_not_run(clean, thresholds):
    """A PI disagreeing a detector should exist is config, not a code change."""
    data, names, regions = clean
    data[3] *= 0.0001
    off = {**thresholds, "detectors": {**thresholds["detectors"],
                                       "flat_channel": {**thresholds["detectors"]["flat_channel"],
                                                        "enabled": False}}}
    assert flat_channel(data, SFREQ, names, regions, off) == []


def test_flag_ids_are_stable_across_runs(clean, thresholds):
    """A reviewer's decision must survive re-detection."""
    data, names, regions = clean
    data[3] *= 0.0001
    first = detect_all(data, SFREQ, names, regions, thresholds)
    second = detect_all(data.copy(), SFREQ, names, regions, thresholds)
    assert [f.flag_id for f in first] == [f.flag_id for f in second]


def test_flag_id_changes_with_the_target():
    a = Flag("channel", "c1", "flat_channel")
    b = Flag("channel", "c2", "flat_channel")
    assert a.flag_id != b.flag_id


def test_detect_all_finds_several_planted_problems(clean, thresholds):
    data, names, regions = clean
    data[3] *= 0.0001                                   # flat
    rail = float(np.max(np.abs(data[4])))
    data[4, :2000] = rail                               # clipped
    data[6, 8000:9000] *= 60                            # transient
    found = {f.flag_type for f in detect_all(data, SFREQ, names, regions, thresholds)}
    assert {"flat_channel", "clipping", "amplitude_window"} <= found


def test_every_flag_carries_evidence_and_a_severity(clean, thresholds):
    data, names, regions = clean
    data[3] *= 0.0001
    for f in detect_all(data, SFREQ, names, regions, thresholds):
        assert f.evidence, f.flag_type
        assert f.severity in {"low", "med", "high"}


def test_high_band_beyond_nyquist_is_skipped(clean, thresholds):
    """At a low sampling rate the high band does not exist; do not invent it."""
    data, names, regions = clean
    assert hf_noise_ratio(data, 150.0, names, regions, thresholds) == []


def test_flag_ids_are_unique_within_one_detection(thresholds):
    """Two detectors can raise the same concern about the same target.

    Both peer-comparison detectors report insufficient_channels for a group with
    too few contacts. If their ids collide, one silently overwrites the other's
    decision in the merge.
    """
    rng = np.random.default_rng(0)
    data = rng.standard_normal((8, 8000)) * 1e-5
    names = [f"c{i+1}" for i in range(8)]
    regions = ["stn"] * 8
    kinds = ["ring"] * 2 + ["segment"] * 6  # two rings: below the minimum

    flags = detect_all(data, SFREQ, names, regions, thresholds, kinds=kinds)
    ids = [f.flag_id for f in flags]
    assert len(ids) == len(set(ids)), "flag ids collided"

    insufficient = [f for f in flags if f.flag_type == "insufficient_channels"]
    assert len({f.detector for f in insufficient}) > 1, "expected two detectors to report"
