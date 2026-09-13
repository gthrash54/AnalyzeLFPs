"""Montage derivation and decimation."""

from __future__ import annotations

import numpy as np
import pytest
import yaml

from dbsspeech.preprocess import apply_montage, available_schemes, build_montage
from dbsspeech.preprocess.resample import (
    decimate_stream,
    suggest_factor,
    usable_bandwidth_hz,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def leads():
    return yaml.safe_load(open("configs/leads.yaml"))["leads"]


@pytest.fixture(scope="module")
def directional(leads):
    return leads["unknown_directional_1331"]


@pytest.fixture(scope="module")
def ring_lead(leads):
    return leads["medtronic_3389"]


def test_vertical_references_each_segment_row_to_its_nearest_ring(directional):
    """Lower segments to the ventral ring, upper segments to the dorsal ring."""
    names = set(build_montage("bipolar_vertical", directional).names)
    assert {"2a-1", "2b-1", "2c-1"} <= names, "lower row must use the ventral ring"
    assert {"3a-4", "3b-4", "3c-4"} <= names, "upper row must use the dorsal ring"
    assert "4-1" in names, "ring to ring derivation missing"


def test_horizontal_stays_within_a_row(directional):
    names = build_montage("bipolar_horizontal", directional).names
    assert set(names) == {"2a-2b", "2b-2c", "2c-2a", "3a-3b", "3b-3c", "3c-3a"}


def test_horizontal_is_undefined_without_segments(ring_lead):
    montage = build_montage("bipolar_horizontal", ring_lead)
    assert len(montage) == 0
    assert any("undefined" in n for n in montage.notes)


def test_ring_lead_still_derives(ring_lead):
    """Geometry drives the derivation, so a non-directional lead works unchanged."""
    assert list(build_montage("bipolar_adjacent", ring_lead).names) == ["1-0", "2-1", "3-2"]


def test_monopolar_is_passthrough(directional):
    montage = build_montage("monopolar", directional)
    assert len(montage) == 8
    assert all(d.kind == "monopolar" for d in montage.derivations)


def test_car_weights_sum_to_zero(directional):
    for d in build_montage("car", directional).derivations:
        assert sum(d.weights.values()) == pytest.approx(0.0)


def test_every_bipolar_derivation_sums_to_zero(directional):
    """A difference derivation must reject a constant offset."""
    for scheme in ("bipolar_vertical", "bipolar_horizontal", "bipolar_adjacent"):
        for d in build_montage(scheme, directional).derivations:
            assert sum(d.weights.values()) == pytest.approx(0.0), f"{scheme}:{d.name}"


def test_unavailable_contacts_drop_derivations_and_say_so(directional):
    available = {c["id"] for c in directional["contacts"]} - {"1"}
    montage = build_montage("bipolar_vertical", directional, available=available)
    assert all("-1" not in n for n in montage.names)
    assert any("not available" in n for n in montage.notes)


def test_apply_montage_computes_the_differences(directional):
    order = [c["id"] for c in directional["contacts"]]
    data = np.arange(8 * 4, dtype=float).reshape(8, 4)
    montage = build_montage("bipolar_vertical", directional)
    out = apply_montage(data, order, montage)
    assert out.shape == (len(montage), 4)
    i = montage.names.index("2a-1")
    np.testing.assert_allclose(out[i], data[order.index("2a")] - data[order.index("1")])


def test_bipolar_rejects_common_mode(directional):
    """The reason guardrail G1 exists, asserted rather than assumed."""
    order = [c["id"] for c in directional["contacts"]]
    rng = np.random.default_rng(0)
    local = rng.standard_normal((8, 500)) * 0.01
    common = np.ones((8, 1)) * rng.standard_normal((1, 500)) * 5.0
    data = local + common

    mono = apply_montage(data, order, build_montage("monopolar", directional))
    bipolar = apply_montage(data, order, build_montage("bipolar_vertical", directional))
    assert mono.std() > 10 * bipolar.std()


def test_apply_montage_rejects_mismatched_channel_count(directional):
    """Data rows and contact names must agree, or the mapping is meaningless."""
    order = [c["id"] for c in directional["contacts"]]  # 8 names
    montage = build_montage("bipolar_vertical", directional)
    with pytest.raises(ValueError, match="contact_order"):
        apply_montage(np.zeros((3, 10)), order, montage)


def test_apply_montage_names_the_contact_it_cannot_find(directional):
    """A derivation needing an absent contact fails loudly, naming it."""
    montage = build_montage("bipolar_vertical", directional)
    with pytest.raises(KeyError, match="needs contact"):
        apply_montage(np.zeros((3, 10)), ["1", "2a", "2b"], montage)


def test_unknown_scheme_lists_the_known_ones(directional):
    with pytest.raises(ValueError, match="unknown reference scheme"):
        build_montage("telepathy", directional)


def test_all_schemes_build_for_both_geometries(directional, ring_lead):
    for spec in (directional, ring_lead):
        for scheme in available_schemes():
            build_montage(scheme, spec)


# ---- decimation --------------------------------------------------------------

def test_usable_bandwidth_is_below_nyquist():
    """The anti-alias cutoff sits at 0.8 of Nyquist, so state it, do not assume it."""
    assert usable_bandwidth_hz(8138.0) == pytest.approx(3255.2)
    assert usable_bandwidth_hz(2034.5) == pytest.approx(813.8)


def test_suggest_factor_hits_walkers_target():
    assert suggest_factor(48828.125, 8000) == 6


def test_single_stage_is_preferred():
    result = decimate_stream(np.random.default_rng(0).standard_normal((2, 6000)), 48828.125, 6)
    assert result.n_stages == 1
    assert result.sfreq_hz == pytest.approx(8138.02, rel=1e-4)
    assert result.data.shape == (2, 1000)


def test_large_factor_splits_into_stages():
    result = decimate_stream(np.random.default_rng(0).standard_normal((1, 4800)), 48828.125, 24)
    assert result.n_stages > 1
    assert result.factor == 24


def test_factor_one_is_a_no_op():
    data = np.ones((2, 10))
    result = decimate_stream(data, 1000.0, 1)
    assert result.data is data
    assert result.n_stages == 0


def test_decimation_preserves_a_signal_below_the_cutoff():
    fs, f0 = 4000.0, 50.0
    t = np.arange(int(fs * 2)) / fs
    data = np.sin(2 * np.pi * f0 * t)[None, :]
    out = decimate_stream(data, fs, 4)
    freqs = np.fft.rfftfreq(out.data.shape[1], 1 / out.sfreq_hz)
    peak = freqs[np.argmax(np.abs(np.fft.rfft(out.data[0])))]
    assert peak == pytest.approx(f0, abs=1.0)


def test_invalid_factor_raises():
    with pytest.raises(ValueError, match="at least 1"):
        decimate_stream(np.zeros((1, 10)), 1000.0, 0)
