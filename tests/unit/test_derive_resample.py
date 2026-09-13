"""Exact-ratio resampling, and the measured anti-alias report that travels with it.

Two properties matter and both are checked against signals, not against the
implementation. A tone inside the declared usable band must come through
within 0.1 dB, or the derivative is quietly attenuating real data. A tone above
the output Nyquist must be gone by at least 80 dB, or it folds into the
retained band and shows up later as a finding.

The third thing pinned here is the reason this module exists at all: the
default `resample_poly` window would fail the second property, and the report
is what lets a later analysis prove the filter it inherited did not.
"""

from __future__ import annotations

import numpy as np
import pytest

from dbsspeech.derive.resample import (
    FilterSpec,
    RateNotRational,
    design_antialias,
    exact_rate_string,
    exact_ratio,
    resample_exact,
    resample_to,
)

pytestmark = pytest.mark.unit

TDT_48K = 390625 / 8       # 48828.125
TDT_24K = 390625 / 16      # 24414.0625
TDT_12K = 390625 / 32      # 12207.03125


# ---- exact ratios -------------------------------------------------------------

@pytest.mark.parametrize(
    ("sfreq_in", "target", "expected"),
    [
        (TDT_48K, 8000, (512, 3125)),
        (TDT_48K, 16000, (1024, 3125)),
        (TDT_48K, 1000, (64, 3125)),
        (TDT_24K, 8000, (1024, 3125)),
        (TDT_24K, 16000, (2048, 3125)),
        (TDT_12K, 2000, (512, 3125)),
        (50000.0, 8000, (4, 25)),
        (25000.0, 8000, (8, 25)),
        (10000.0, 8000, (4, 5)),
        (8000.0, 8000, (1, 1)),
    ],
)
def test_archive_rates_convert_by_exact_small_rationals(sfreq_in, target, expected):
    assert exact_ratio(sfreq_in, target) == expected


def test_the_ratio_reproduces_the_target_exactly():
    up, down = exact_ratio(TDT_48K, 8000)
    assert TDT_48K * up / down == 8000.0


def test_a_rate_that_is_not_ours_is_refused_rather_than_approximated():
    with pytest.raises(RateNotRational):
        exact_ratio(8138.02, 8000)


def test_exact_rate_strings_are_provenance_friendly():
    assert exact_rate_string(TDT_48K) == "390625/8"
    assert exact_rate_string(8000.0) == "8000/1"


# ---- the designed filter, measured -------------------------------------------

@pytest.fixture(scope="module")
def design_48k_to_8k():
    return design_antialias(512, 3125, TDT_48K)


def test_the_report_states_the_output_rate_exactly(design_48k_to_8k):
    _, report = design_48k_to_8k
    assert report.sfreq_out_hz == 8000.0
    assert report.sfreq_out_exact == "8000/1"
    assert report.sfreq_in_exact == "390625/8"


def test_the_measured_stopband_starts_at_the_output_nyquist(design_48k_to_8k):
    """Nothing above the new Nyquist may survive above the stated attenuation.

    `kaiserord` estimates the transition width, so the measured -90 dB point
    can land a fraction of a percent past the designed edge. That sliver folds
    to just below the Nyquist, far outside the usable band, and the alias-floor
    measurement below is the guarantee that actually covers the usable band.
    Held to one percent here so a real design error cannot hide behind it.
    """
    _, report = design_48k_to_8k
    assert report.measured_stopband_edge_hz <= report.nyquist_out_hz * 1.01
    assert report.attenuation_at_out_nyquist_db < -80.0


def test_the_alias_floor_is_measured_and_deep(design_48k_to_8k):
    _, report = design_48k_to_8k
    assert report.alias_floor_db <= -80.0


def test_the_usable_band_is_the_designed_passband_when_the_measurement_agrees(design_48k_to_8k):
    _, report = design_48k_to_8k
    assert report.passband_edge_hz == pytest.approx(0.8 * 4000.0)
    assert report.usable_bandwidth_hz == pytest.approx(report.passband_edge_hz, abs=5.0)
    assert report.minus_0p1_db_hz >= report.usable_bandwidth_hz - 5.0


def test_the_report_flattens_to_attributes_with_the_numbers_a_guardrail_needs(design_48k_to_8k):
    _, report = design_48k_to_8k
    attrs = report.as_attrs()
    for key in ("usable_bandwidth_hz", "alias_floor_db", "filter_coeff_sha256",
                "sfreq_out_exact", "resample_up", "resample_down"):
        assert key in attrs
    assert attrs["resample_method"] == "scipy.signal.resample_poly"


def test_a_spec_the_design_cannot_meet_is_refused():
    """Asking for a 40 dB filter but demanding a -80 dB floor must not pass silently."""
    spec = FilterSpec(stopband_attenuation_db=40.0, require_measured_alias_floor_db=-80.0)
    with pytest.raises(ValueError, match="alias floor"):
        design_antialias(512, 3125, TDT_48K, spec)


# ---- what the filter does to signals -----------------------------------------

def _tone(freq_hz: float, sfreq_hz: float, seconds: float, n_channels: int = 2) -> np.ndarray:
    t = np.arange(int(seconds * sfreq_hz)) / sfreq_hz
    x = np.sin(2 * np.pi * freq_hz * t)
    return np.tile(x, (n_channels, 1))


def _rms_in_middle(x: np.ndarray) -> float:
    n = x.shape[-1]
    mid = x[..., n // 4: 3 * n // 4]
    return float(np.sqrt(np.mean(mid**2)))


def test_a_tone_inside_the_usable_band_survives_within_a_tenth_of_a_decibel(design_48k_to_8k):
    taps, report = design_48k_to_8k
    f = 0.9 * report.usable_bandwidth_hz  # 2880 Hz, well inside 3200
    x = _tone(f, TDT_48K, seconds=2.0)
    y = resample_exact(x, 512, 3125, taps)
    loss_db = 20 * np.log10(_rms_in_middle(y) / _rms_in_middle(x))
    assert abs(loss_db) < 0.1


def test_a_tone_above_the_output_nyquist_is_gone_by_eighty_decibels(design_48k_to_8k):
    """0.6 * fs_out would fold to 0.4 * fs_out, right inside the usable band."""
    taps, _ = design_48k_to_8k
    x = _tone(0.6 * 8000.0, TDT_48K, seconds=2.0)
    y = resample_exact(x, 512, 3125, taps)
    loss_db = 20 * np.log10(_rms_in_middle(y) / _rms_in_middle(x))
    assert loss_db < -80.0


def test_the_output_length_matches_the_exact_ratio(design_48k_to_8k):
    taps, _ = design_48k_to_8k
    n_in = int(TDT_48K * 1.0)  # 48828 samples, a hair under one second
    y = resample_exact(np.zeros((3, n_in)), 512, 3125, taps)
    assert y.shape[0] == 3
    assert y.shape[1] == int(np.ceil(n_in * 512 / 3125))


def test_channels_do_not_bleed_into_each_other(design_48k_to_8k):
    taps, _ = design_48k_to_8k
    x = _tone(1000.0, TDT_48K, seconds=1.0, n_channels=2)
    x[1] = 0.0
    y = resample_exact(x, 512, 3125, taps)
    assert np.abs(y[1]).max() == 0.0
    assert np.abs(y[0]).max() > 0.5


def test_resample_to_does_the_whole_thing_and_identity_is_a_copy():
    x = _tone(500.0, TDT_48K, seconds=0.5)
    y, report = resample_to(x, TDT_48K, 8000)
    assert report.sfreq_out_hz == 8000.0
    assert y.shape[1] == int(np.ceil(x.shape[1] * 512 / 3125))

    same, ident = resample_to(x, TDT_48K, TDT_48K)
    assert ident.design == "identity"
    assert same is not x
    np.testing.assert_array_equal(same, x)


def test_a_non_2d_array_is_refused():
    with pytest.raises(ValueError, match="n_channels, n_samples"):
        resample_exact(np.zeros(10), 1, 2, np.ones(3))
