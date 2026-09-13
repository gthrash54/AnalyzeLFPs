"""pac_modulation_index: the estimator wrapper and its refusals.

The test that matters most plants coupling at a known pair of frequencies and
checks the recipe finds it there. A PAC implementation that returns plausible
numbers without recovering a signal it was handed is the failure mode worth
guarding, because nothing downstream would notice.
"""

from __future__ import annotations

import numpy as np
import pytest

from dbsspeech.recipes import available, get
from dbsspeech.recipes.pac import (
    METHODS,
    NAME,
    PacParams,
    _amplitude_range,
    _comodulogram,
    _phase_range,
    _too_short,
)

pytestmark = pytest.mark.unit

SFREQ_HZ = 500.0
PHASE_HZ = 8.0
AMPLITUDE_HZ = 80.0


def _coupled_signal(seconds: float = 20.0, coupled: bool = True) -> np.ndarray:
    """A slow rhythm whose phase gates a fast one, or the two independent."""
    t = np.arange(0, seconds, 1.0 / SFREQ_HZ)
    rng = np.random.default_rng(0)
    phase = 2 * np.pi * PHASE_HZ * t
    envelope = (1 + np.cos(phase)) / 2 if coupled else 1.0
    return (
        np.sin(phase)
        + 0.6 * envelope * np.sin(2 * np.pi * AMPLITUDE_HZ * t)
        + 0.1 * rng.normal(size=t.size)
    )


def _params(**kwargs) -> PacParams:
    base = {
        "phase_fq_min_hz": 4.0,
        "phase_fq_max_hz": 16.0,
        "phase_fq_step_hz": 2.0,
        "phase_fq_width_hz": 2.0,
        "amplitude_fq_min_hz": 50.0,
        "amplitude_fq_max_hz": 120.0,
        "amplitude_fq_step_hz": 10.0,
        "n_surrogates": 0,
        "sfreq_target_hz": SFREQ_HZ,
    }
    base.update(kwargs)
    return PacParams(**base)


def test_the_recipe_is_registered():
    assert NAME in available()
    assert get(NAME).params_model is PacParams


def test_defaults_choose_the_modulation_index():
    """tort is the most reported measure, so it is the comparable default."""
    assert PacParams().method == "tort"
    assert PacParams().n_surrogates > 0


def test_every_documented_method_is_accepted():
    for method in METHODS:
        assert PacParams(method=method).method == method


def test_an_unknown_method_is_refused():
    with pytest.raises(ValueError):
        PacParams(method="not_a_method")


def test_frequency_ranges_come_from_the_parameters():
    params = _params()
    assert _phase_range(params).tolist() == [4.0, 6.0, 8.0, 10.0, 12.0, 14.0]
    assert _amplitude_range(params).tolist() == [50.0, 60.0, 70.0, 80.0, 90.0, 100.0, 110.0]


def test_planted_coupling_is_recovered_at_the_frequencies_it_was_planted_at():
    params = _params()
    raw, corrected = _comodulogram(_coupled_signal(), SFREQ_HZ, params)
    assert corrected is None  # n_surrogates=0

    phase_fqs = _phase_range(params)
    amp_fqs = _amplitude_range(params)
    peak = np.unravel_index(int(np.argmax(raw)), raw.shape)
    assert phase_fqs[peak[0]] == pytest.approx(PHASE_HZ, abs=2.0)
    assert amp_fqs[peak[1]] == pytest.approx(AMPLITUDE_HZ, abs=10.0)


def test_an_uncoupled_signal_gives_a_much_weaker_peak():
    """Otherwise the test above would pass on any signal at all."""
    params = _params()
    coupled, _ = _comodulogram(_coupled_signal(coupled=True), SFREQ_HZ, params)
    flat, _ = _comodulogram(_coupled_signal(coupled=False), SFREQ_HZ, params)
    assert coupled.max() > 5 * flat.max()


def test_surrogates_produce_a_corrected_map_of_the_same_shape():
    params = _params(n_surrogates=20)
    raw, corrected = _comodulogram(_coupled_signal(seconds=12.0), SFREQ_HZ, params)
    assert corrected is not None
    assert corrected.shape == raw.shape


# ---- refusals ----------------------------------------------------------------

def test_a_window_too_short_for_the_slowest_phase_frequency_is_refused():
    params = _params(phase_fq_min_hz=4.0)
    # Ten cycles of 4 Hz is 2.5 s.
    assert _too_short(1.0, params) is not None
    assert _too_short(5.0, params) is None


def test_the_refusal_says_what_would_be_long_enough():
    reason = _too_short(0.5, _params(phase_fq_min_hz=4.0))
    assert reason is not None
    assert "2.50s" in reason
    assert "4.0 Hz" in reason


def test_a_lower_phase_frequency_demands_a_longer_window():
    assert _too_short(3.0, _params(phase_fq_min_hz=4.0)) is None
    assert _too_short(3.0, _params(phase_fq_min_hz=2.0)) is not None


def test_the_default_phase_width_does_not_exceed_the_default_step():
    """The default that was wrong once.

    A phase filter wider than the step makes neighbouring bins admit the same
    rhythm. Measured on 8 Hz phase driving 80 Hz amplitude with a 2 Hz step, a
    4 Hz width put the peak at 4 Hz, confidently and wrongly. Pinning the
    relationship here so the default cannot drift back.
    """
    defaults = PacParams()
    assert defaults.phase_fq_width_hz <= defaults.phase_fq_step_hz


def test_a_wide_phase_filter_stops_the_phase_axis_discriminating():
    """The evidence behind the default, on the signal that produced it."""
    narrow = _params(phase_fq_width_hz=2.0)
    wide = _params(phase_fq_width_hz=4.0)
    signal = _coupled_signal()
    phase_fqs = _phase_range(narrow)

    sharp, _ = _comodulogram(signal, SFREQ_HZ, narrow)
    blurred, _ = _comodulogram(signal, SFREQ_HZ, wide)

    sharp_peak = phase_fqs[np.unravel_index(int(np.argmax(sharp)), sharp.shape)[0]]
    assert sharp_peak == pytest.approx(PHASE_HZ, abs=2.0)

    # Contrast across the phase axis, high when one bin stands out.
    def spread(comod):
        profile = comod.max(axis=1)
        return float(profile.max() / profile.mean())

    assert spread(sharp) > spread(blurred)
