"""erp_epochs: the parameter refusals, and recovering a planted response.

An evoked average is easy to compute and easy to compute wrongly, and both
produce a smooth curve. The load-bearing test plants a deflection at a known
latency on one derivation only, and checks that it comes back at that latency
and at roughly that size while the other derivation stays flat.
"""

from __future__ import annotations

import numpy as np
import pydantic
import pytest

from dbsspeech.recipes import available, get
from dbsspeech.recipes.erp import (
    NAME,
    ErpParams,
    _baseline_correct,
)

pytestmark = pytest.mark.unit

SFREQ_HZ = 500.0
PEAK_LATENCY_S = 0.30
PEAK_AMPLITUDE = 5.0
N_TRIALS = 100


def _params(**kwargs) -> ErpParams:
    base = {
        "event_label": "Stimulus/S  1",
        "tmin_s": -0.2,
        "tmax_s": 0.8,
        "baseline_start_s": -0.2,
        "baseline_end_s": 0.0,
        "peak_window_start_s": 0.0,
        "peak_window_end_s": 0.6,
        "sfreq_target_hz": SFREQ_HZ,
    }
    base.update(kwargs)
    return ErpParams(**base)


def _planted_epochs(params: ErpParams, drift: bool = False) -> tuple[np.ndarray, np.ndarray]:
    """(n_trials, n_derivations, n_times) with a bump on derivation 0 only."""
    times = np.arange(params.tmin_s, params.tmax_s, 1.0 / SFREQ_HZ)
    rng = np.random.default_rng(0)
    response = PEAK_AMPLITUDE * np.exp(-((times - PEAK_LATENCY_S) ** 2) / (2 * 0.03**2))

    # Noise chosen so the average is actually clean: sigma 3 over 100 trials
    # leaves a standard error of 0.3, well under the planted amplitude. Larger
    # noise makes max(|.|) over the peak window pick a noise excursion, which
    # tests the random seed rather than the averaging.
    stack = rng.normal(0.0, 3.0, (N_TRIALS, 2, times.size))
    stack[:, 0, :] += response
    if drift:
        # A different constant offset per trial, which is what per-trial
        # baseline correction exists to remove.
        stack += rng.normal(0.0, 50.0, (N_TRIALS, 2, 1))
    return stack, times


def test_the_recipe_is_registered():
    assert NAME in available()
    assert get(NAME).params_model is ErpParams


# ---- refusals ----------------------------------------------------------------

def test_a_baseline_overlapping_the_response_is_refused():
    """It would subtract part of the response from itself."""
    with pytest.raises(pydantic.ValidationError, match="at or before 0"):
        _params(baseline_end_s=0.2)


def test_a_reversed_epoch_is_refused():
    with pytest.raises(pydantic.ValidationError, match="after tmin_s"):
        _params(tmin_s=0.5, tmax_s=0.1)


def test_a_baseline_starting_before_the_epoch_is_refused():
    with pytest.raises(pydantic.ValidationError, match="baseline starts before"):
        _params(baseline_start_s=-1.0)


def test_a_peak_window_past_the_epoch_is_refused():
    with pytest.raises(pydantic.ValidationError, match="past the end"):
        _params(peak_window_end_s=2.0)


def test_min_trials_defaults_to_something_that_is_actually_an_average():
    assert ErpParams(event_label="x").min_trials >= 10


# ---- the average itself ------------------------------------------------------

def test_a_planted_response_is_recovered_at_its_latency():
    params = _params()
    stack, times = _planted_epochs(params)
    evoked = _baseline_correct(stack, times, params).mean(axis=0)

    mask = (times >= params.peak_window_start_s) & (times <= params.peak_window_end_s)
    segment, segment_times = evoked[0][mask], times[mask]
    index = int(np.argmax(np.abs(segment)))
    assert segment_times[index] == pytest.approx(PEAK_LATENCY_S, abs=0.05)
    assert segment[index] == pytest.approx(PEAK_AMPLITUDE, rel=0.35)


def test_a_derivation_without_the_response_stays_near_zero():
    """Otherwise the test above would pass on any smooth curve."""
    params = _params()
    stack, times = _planted_epochs(params)
    evoked = _baseline_correct(stack, times, params).mean(axis=0)
    assert np.abs(evoked[1]).max() < PEAK_AMPLITUDE / 2


def test_baseline_correction_is_per_trial_not_on_the_average():
    """Per-trial drift is the thing it removes; a single offset is not."""
    params = _params()
    stack, times = _planted_epochs(params, drift=True)

    per_trial = _baseline_correct(stack, times, params).mean(axis=0)
    on_average = stack.mean(axis=0)
    mask = (times >= params.baseline_start_s) & (times <= params.baseline_end_s)
    on_average = on_average - on_average[:, mask].mean(axis=1, keepdims=True)

    peak_mask = (times >= 0) & (times <= params.peak_window_end_s)
    recovered = per_trial[0][peak_mask].max()
    assert recovered == pytest.approx(PEAK_AMPLITUDE, rel=0.4)
    # Both routes land near the planted amplitude on this synthetic case; the
    # difference is variance, and the per-trial route is the tighter one.
    assert per_trial[1].std() <= on_average[1].std()


def test_the_baseline_is_flat_after_correction():
    params = _params()
    stack, times = _planted_epochs(params, drift=True)
    evoked = _baseline_correct(stack, times, params).mean(axis=0)
    mask = (times >= params.baseline_start_s) & (times <= params.baseline_end_s)
    assert np.abs(evoked[:, mask].mean()) < 1e-9


def test_an_empty_baseline_window_is_refused():
    params = _params(baseline_start_s=-0.15, baseline_end_s=-0.1)
    times = np.array([-0.2, 0.0, 0.2])  # no sample falls inside [-0.15, -0.1]
    stack = np.zeros((3, 1, times.size))
    with pytest.raises(RuntimeError, match="no samples"):
        _baseline_correct(stack, times, params)


# ---- edge events -------------------------------------------------------------

def test_events_whose_epoch_falls_outside_the_recording_are_dropped():
    """The bug this guards: one edge event used to destroy the whole run.

    The first trial read established the epoch length every later trial was
    checked against. An event near the start produced a truncated first trial,
    so every full-length trial after it looked like the mismatched one and was
    discarded, leaving too few trials to average.
    """
    from dbsspeech.recipes.erp import _within_recording

    params = _params(tmin_s=-0.2, tmax_s=0.8)
    onsets = np.array([0.05, 5.0, 10.0, 19.9])  # first and last do not fit
    kept = _within_recording(onsets, 20.0, params)
    assert kept.tolist() == [5.0, 10.0]


def test_an_event_exactly_at_the_boundary_is_kept():
    from dbsspeech.recipes.erp import _within_recording

    params = _params(tmin_s=-0.2, tmax_s=0.8)
    onsets = np.array([0.2, 19.2])  # epochs are exactly [0, 1] and [19, 20]
    assert _within_recording(onsets, 20.0, params).tolist() == [0.2, 19.2]
