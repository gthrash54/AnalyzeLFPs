"""Full-rate stream summaries: exact statistics and a spectrum from a stream of windows.

The property guarded here is that the summary describes the whole native-rate
stream regardless of how it was cut into windows or sub-blocks. A block is fed
in pieces because it does not fit in memory, and the pieces must not leak into
the numbers: rms, min, max, rail counts and the common-mode fractions must be
the same whether the block arrived whole or in fragments, and the spectrum
must land on the same peak. Each statistic is also checked against a signal
with a known answer, so a wrong formula cannot pass by being consistently
wrong; the spectrum in particular is pinned to scipy's own welch output and to
the analytic level of white noise, so a wrong window, scaling, detrend or
within-window average cannot hide behind a peak that lands in the right bin.
"""

from __future__ import annotations

import numpy as np
import pytest
from scipy.fft import rfftfreq
from scipy.signal import welch

from dbsspeech.derive.config import PsdConfig, SummaryConfig
from dbsspeech.derive.summarize import (
    PSD_DETREND,
    PSD_METHOD,
    PSD_SCALING,
    PSD_WINDOW,
    StreamSummarizer,
    StreamSummary,
)

pytestmark = pytest.mark.unit

SFREQ = 1000.0
CFG = SummaryConfig(full_rate_psd=PsdConfig(enabled=True, nperseg_s=1.0, overlap=0.5))

TDT_48K = 390625 / 8  # 48828.125
TDT_24K = 390625 / 16  # 24414.0625
TDT_12K = 390625 / 32  # 12207.03125


def _noise(n_channels: int, n_samples: int, seed: int = 0) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n_channels, n_samples))


def _summarize(
    data: np.ndarray, chunk_size: int | None = None, cfg: SummaryConfig = CFG, **kw
) -> StreamSummary:
    s = StreamSummarizer(SFREQ, data.shape[0], cfg, **kw)
    if chunk_size is None:
        s.update(data)
    else:
        for start in range(0, data.shape[1], chunk_size):
            s.update(data[:, start : start + chunk_size])
    return s.finalize()


# ---- spectrum ------------------------------------------------------------------


def test_a_planted_sinusoid_is_the_psd_peak_within_one_bin():
    f0 = 137.0
    t = np.arange(int(10 * SFREQ)) / SFREQ
    data = np.vstack([np.sin(2 * np.pi * f0 * t), 0.01 * _noise(1, t.size)[0]])
    data[0] += 0.01 * _noise(1, t.size, seed=3)[0]
    out = _summarize(data, chunk_size=2000)
    peak_hz = out.psd_freqs_hz[np.argmax(out.psd_db[0])]
    bin_hz = out.psd_freqs_hz[1] - out.psd_freqs_hz[0]
    assert abs(peak_hz - f0) <= bin_hz
    assert out.psd_method == PSD_METHOD
    assert out.psd_db.dtype == np.float32
    assert out.psd_db.shape == (2, out.psd_freqs_hz.size)


def test_one_window_reproduces_scipy_welch_with_the_documented_settings():
    """Pins fs, window, nperseg, noverlap, detrend, scaling and the within-window average.

    With a single window there is nothing to aggregate across windows, so the
    stored spectrum must be scipy's own welch output in dB to float32 rounding.
    Any change to one of the settings shifts the level or the shape and fails.
    """
    data = _noise(3, 5000, seed=21)
    out = _summarize(data)
    _, ref = welch(
        data,
        fs=SFREQ,
        window="hann",
        nperseg=1000,
        noverlap=500,
        detrend="constant",
        scaling="density",
        average="median",
    )
    np.testing.assert_allclose(out.psd_db, 10.0 * np.log10(ref), atol=1e-4, rtol=0)
    assert out.n_windows == 1
    assert (PSD_WINDOW, PSD_DETREND, PSD_SCALING) == ("hann", "constant", "density")


def test_white_noise_comes_out_at_its_analytic_one_sided_density():
    """Variance sigma^2 sampled at fs has one-sided density 2 sigma^2 / fs.

    Density scaling gives that level; spectrum scaling would sit 1.8 dB away
    at this segment length. The median of per-window medians rides a few
    tenths of a dB under the mean, well inside the 1 dB allowed here.
    """
    sigma = 0.3
    data = sigma * _noise(1, 120_000, seed=8)
    out = _summarize(data, chunk_size=10_000)
    expected_db = 10.0 * np.log10(2.0 * sigma**2 / SFREQ)
    # DC and Nyquist bins have half the degrees of freedom; skip them.
    level = float(out.psd_db[0, 1:-1].mean())
    assert level == pytest.approx(expected_db, abs=1.0)


@pytest.mark.parametrize("sfreq", [TDT_48K, TDT_24K, TDT_12K, SFREQ])
def test_the_frequency_grid_is_rfftfreq_of_the_rounded_segment_length(sfreq):
    """At a TDT rate nperseg_s * sfreq is not an integer; it is rounded once, consistently."""
    s = StreamSummarizer(sfreq, 1, CFG)
    nperseg = int(round(CFG.full_rate_psd.nperseg_s * sfreq))
    assert s.nperseg == nperseg
    assert s.noverlap == int(0.5 * nperseg)
    s.update(_noise(1, 2 * nperseg + 7))
    out = s.finalize()
    np.testing.assert_array_equal(out.psd_freqs_hz, rfftfreq(nperseg, d=1.0 / sfreq))
    assert out.psd_freqs_hz[0] == 0.0
    assert out.psd_freqs_hz[-1] == pytest.approx(sfreq / 2, abs=out.psd_freqs_hz[1])


def test_archive_rates_round_to_the_documented_segment_lengths():
    for sfreq, nperseg, noverlap in [
        (TDT_48K, 48828, 24414),
        (TDT_24K, 24414, 12207),
        (TDT_12K, 12207, 6103),
    ]:
        s = StreamSummarizer(sfreq, 1, CFG)
        assert (s.nperseg, s.noverlap) == (nperseg, noverlap)


def test_a_window_shorter_than_one_segment_is_skipped_for_the_psd_but_counted_elsewhere():
    data = _noise(2, 2500)
    out = _summarize(data, chunk_size=1000)  # windows of 1000, 1000, 500
    assert out.n_windows == 2
    assert out.n_samples == 2500
    np.testing.assert_array_equal(out.vmax, data.max(axis=1))


def test_a_stream_with_no_window_long_enough_yields_an_empty_spectrum_but_full_stats():
    data = _noise(3, 600)
    out = _summarize(data)
    assert out.n_windows == 0
    assert out.psd_freqs_hz.size == 0
    assert out.psd_db.shape == (3, 0)
    np.testing.assert_allclose(out.rms, np.sqrt((data**2).mean(axis=1)))


def test_a_disabled_psd_leaves_the_spectrum_empty():
    cfg = SummaryConfig(full_rate_psd=PsdConfig(enabled=False))
    out = _summarize(_noise(2, 5000), cfg=cfg)
    assert out.psd_db.shape == (2, 0)
    assert out.n_windows == 0
    assert out.n_samples == 5000


def test_an_all_zero_channel_has_a_finite_spectrum():
    out = _summarize(np.zeros((1, 4000)))
    assert np.all(np.isfinite(out.psd_db))


def test_the_dc_bin_reflects_the_detrend_and_not_the_offset():
    """welch removes each segment's mean, so a constant lands at the floor at 0 Hz.

    The offset is still described, by vmin and vmax; and the detrend is named
    in the attributes so a reader knows why the DC bin says nothing about it.
    """
    out = _summarize(np.full((1, 4000), 3.0))
    assert out.psd_db[0, 0] < -60.0
    assert out.vmin[0] == out.vmax[0] == 3.0
    assert out.as_attrs()["psd_detrend"] == "constant"


def test_mean_aggregation_across_windows_is_honored():
    """With mean, a single loud window lifts the aggregate; with median it does not.

    The mean path holds a running sum instead of every window, so it is also
    checked against the plain mean of per-window welch spectra.
    """
    quiet = 0.01 * _noise(1, 5000)
    loud = quiet.copy()
    loud[:, :1000] *= 100.0
    med = _summarize(loud, chunk_size=1000)
    cfg = SummaryConfig(full_rate_psd=PsdConfig(aggregate="mean"))
    mean = _summarize(loud, chunk_size=1000, cfg=cfg)
    assert mean.psd_db.mean() > med.psd_db.mean() + 3.0
    assert med.as_attrs()["psd_aggregate_across_windows"] == "median"
    assert mean.as_attrs()["psd_aggregate_across_windows"] == "mean"

    per_window = [
        welch(
            loud[:, a : a + 1000],
            fs=SFREQ,
            window="hann",
            nperseg=1000,
            noverlap=500,
            detrend="constant",
            scaling="density",
            average="median",
        )[1]
        for a in range(0, 5000, 1000)
    ]
    ref = 10.0 * np.log10(np.mean(per_window, axis=0))
    np.testing.assert_allclose(mean.psd_db, ref, atol=1e-4, rtol=0)


def test_more_windows_than_the_initial_capacity_are_all_kept_for_the_median():
    """The per-window stack grows; every window must survive the copy on growth."""
    data = _noise(1, 11_000, seed=4)
    data[:, 5000:6000] *= 1000.0  # one loud window out of eleven
    out = _summarize(data, chunk_size=1000)
    assert out.n_windows == 11
    per_window = np.stack(
        [
            welch(
                data[:, a : a + 1000],
                fs=SFREQ,
                window="hann",
                nperseg=1000,
                noverlap=500,
                detrend="constant",
                scaling="density",
                average="median",
            )[1]
            for a in range(0, 11_000, 1000)
        ]
    )
    ref = 10.0 * np.log10(np.median(per_window, axis=0))
    np.testing.assert_allclose(out.psd_db, ref, atol=1e-4, rtol=0)


def test_finalize_can_be_called_twice_with_the_same_answer():
    s = StreamSummarizer(SFREQ, 2, CFG)
    for a in range(0, 9000, 1500):
        s.update(_noise(2, 1500, seed=a))
    first = s.finalize()
    second = s.finalize()
    np.testing.assert_array_equal(first.psd_db, second.psd_db)
    np.testing.assert_array_equal(first.rms, second.rms)


# ---- amplitude statistics ------------------------------------------------------


def test_rms_of_a_known_signal_is_exact():
    """A sinusoid of amplitude A over whole cycles has rms A / sqrt(2); a constant has rms |c|."""
    t = np.arange(int(4 * SFREQ)) / SFREQ
    data = np.vstack([3.0 * np.sin(2 * np.pi * 10.0 * t), np.full(t.size, -2.5)])
    out = _summarize(data, chunk_size=700)
    assert out.rms[0] == pytest.approx(3.0 / np.sqrt(2.0), rel=1e-12)
    assert out.rms[1] == pytest.approx(2.5, rel=1e-15)


def test_min_and_max_are_over_the_whole_stream():
    data = _noise(3, 5000)
    data[1, 4999] = 50.0  # in the short final window
    data[2, 0] = -50.0
    out = _summarize(data, chunk_size=1000)
    np.testing.assert_array_equal(out.vmin, data.min(axis=1))
    np.testing.assert_array_equal(out.vmax, data.max(axis=1))
    assert out.vmax[1] == 50.0
    assert out.vmin[2] == -50.0


def test_n_at_rail_counts_exact_hits_on_either_rail():
    data = _noise(2, 3000)
    data[0, [5, 17, 2999]] = 32767.0
    data[0, [40]] = -32767.0
    data[1, 100] = 32766.999  # close is not at the rail
    out = _summarize(data, chunk_size=1000, rail_value=32767.0)
    np.testing.assert_array_equal(out.n_at_rail, [4, 0])
    assert out.n_at_rail.dtype.kind == "i"


def test_asymmetric_rails_are_counted_as_a_low_high_pair():
    """int16 converters rail at -32768 and 32767; a symmetric rail would miss one side."""
    rng = np.random.default_rng(2)
    data = rng.integers(-1000, 1000, (2, 3000), dtype=np.int16)
    data[0, [1, 2, 3]] = -32768
    data[1, [7, 2999]] = 32767
    data[1, 8] = -32767
    out = _summarize(data, chunk_size=1000, rail_value=(-32768, 32767))
    np.testing.assert_array_equal(out.n_at_rail, [3, 2])
    assert out.vmin[0] == -32768.0
    assert out.vmax[1] == 32767.0
    attrs = out.as_attrs()
    assert (attrs["rail_low"], attrs["rail_high"]) == (-32768.0, 32767.0)


def test_a_float32_stream_is_matched_by_the_rail_it_actually_carries():
    """The rail is compared in the chunk's own dtype, so a float64 spec finds float32 hits.

    The value here is the kind a converter produces: not a round decimal.
    """
    rail = -0.8191404375
    data = _noise(2, 4000, seed=5).astype(np.float32)
    data[1, [0, 1000, 3999]] = np.float32(rail)
    out = _summarize(data, chunk_size=1000, rail_value=(rail, 10.0))
    np.testing.assert_array_equal(out.n_at_rail, [0, 3])


def test_n_at_rail_is_all_zeros_when_no_rail_value_is_given():
    data = _noise(2, 1000)
    data[0, 3] = 1.0
    out = _summarize(data)
    np.testing.assert_array_equal(out.n_at_rail, [0, 0])
    assert np.isnan(out.as_attrs()["rail_low"])


def test_a_malformed_rail_is_refused():
    with pytest.raises(ValueError):
        StreamSummarizer(SFREQ, 1, CFG, rail_value=(1.0, -1.0))
    with pytest.raises(ValueError):
        StreamSummarizer(SFREQ, 1, CFG, rail_value=(1.0, 2.0, 3.0))  # type: ignore[arg-type]


def test_samples_at_the_running_extreme_are_counted_without_a_rail():
    """A saturation plateau shows as many samples at vmin or vmax.

    The count restarts when a later chunk finds a new extreme and accumulates
    when a later chunk ties it, so it is the count over the whole stream.
    """
    data = _noise(2, 6000, seed=6)
    data[0, 100:110] = -7.0  # a plateau in the first chunk
    data[0, 2500:2503] = -9.0  # a lower plateau later: count restarts at 3
    data[0, 5990] = -9.0  # a tie in the last chunk: count becomes 4
    data[1, [5, 1005, 5005]] = 12.0
    out = _summarize(data, chunk_size=1000)
    np.testing.assert_array_equal(out.n_at_vmin, [4, 1])
    np.testing.assert_array_equal(out.n_at_vmax, [1, 3])
    assert out.vmin[0] == -9.0
    assert out.vmax[1] == 12.0


def test_a_non_finite_sample_is_refused_rather_than_poisoning_the_stream():
    for bad in (np.nan, np.inf, -np.inf):
        data = _noise(2, 500)
        data[1, 250] = bad
        s = StreamSummarizer(SFREQ, 2, CFG)
        with pytest.raises(ValueError, match="non-finite"):
            s.update(data)


# ---- common mode ---------------------------------------------------------------


def test_the_same_signal_on_every_channel_puts_all_variance_in_pc1():
    base = _noise(1, 8000)[0]
    data = np.vstack([base, 2.0 * base, -0.5 * base, base + 100.0])
    out = _summarize(data, chunk_size=1000)
    assert out.pc1_variance_fraction == pytest.approx(1.0, abs=1e-9)
    assert out.pc1_correlation_fraction == pytest.approx(1.0, abs=1e-9)


def test_independent_noise_channels_put_about_one_over_n_in_pc1():
    n_channels = 8
    data = _noise(n_channels, 200_000, seed=7)
    out = _summarize(data, chunk_size=30_000)
    assert out.pc1_variance_fraction == pytest.approx(1.0 / n_channels, abs=0.03)
    assert out.pc1_correlation_fraction == pytest.approx(1.0 / n_channels, abs=0.03)


def test_one_hot_channel_dominates_the_covariance_fraction_but_not_the_correlation_fraction():
    """Why both numbers exist: a 100x gain is not a common-mode signal.

    The covariance fraction reads near 1.0 for it, as the spec defines it; the
    correlation fraction stays at 1/n, as independent channels should.
    """
    n_channels = 4
    data = _noise(n_channels, 200_000, seed=12)
    data[0] *= 100.0
    out = _summarize(data, chunk_size=25_000)
    assert out.pc1_variance_fraction > 0.99
    assert out.pc1_correlation_fraction == pytest.approx(1.0 / n_channels, abs=0.03)


def test_a_large_dc_offset_does_not_ruin_the_covariance():
    """The shifted accumulator must give the same answer with a 1e9 offset as without.

    Without the shift the unshifted sums of squares lose the signal entirely
    at this offset (the result becomes NaN), so a tight comparison against
    the offset-free answer is what proves the guard works.
    """
    base = _noise(2, 20_000, seed=11)
    plain = _summarize(base, chunk_size=3000)
    offset = _summarize(base + 1e9, chunk_size=3000)
    assert offset.pc1_variance_fraction == pytest.approx(plain.pc1_variance_fraction, rel=1e-6)
    assert offset.pc1_correlation_fraction == pytest.approx(
        plain.pc1_correlation_fraction, rel=1e-6
    )


def test_pc1_is_nan_when_there_is_no_variance_to_apportion():
    out = _summarize(np.zeros((3, 100)))
    assert np.isnan(out.pc1_variance_fraction)
    assert np.isnan(out.pc1_correlation_fraction)


def test_a_flat_channel_is_left_out_of_the_correlation_fraction():
    """A zero-variance channel has no correlation; the others still get their 1/k."""
    data = _noise(3, 100_000, seed=13)
    data[2] = 4.0
    out = _summarize(data, chunk_size=20_000)
    assert out.pc1_correlation_fraction == pytest.approx(0.5, abs=0.03)


# ---- chunk and sub-block invariance ---------------------------------------------


def test_statistics_do_not_depend_on_how_the_stream_was_chunked():
    data = _noise(4, 12_345, seed=5)
    data[2, [10, 5000, 12_344]] = 1.0
    whole = _summarize(data, rail_value=1.0)
    parts = _summarize(data, chunk_size=1000, rail_value=1.0)
    uneven = StreamSummarizer(SFREQ, 4, CFG, rail_value=1.0)
    for a, b in [(0, 1), (1, 1500), (1500, 1501), (1501, 9000), (9000, 12_345)]:
        uneven.update(data[:, a:b])
    ragged = uneven.finalize()

    for other in (parts, ragged):
        np.testing.assert_array_equal(other.vmin, whole.vmin)
        np.testing.assert_array_equal(other.vmax, whole.vmax)
        np.testing.assert_array_equal(other.n_at_rail, whole.n_at_rail)
        np.testing.assert_array_equal(other.n_at_vmin, whole.n_at_vmin)
        np.testing.assert_array_equal(other.n_at_vmax, whole.n_at_vmax)
        assert other.n_samples == whole.n_samples
        # Sums in float64 differ only in rounding order between chunkings.
        np.testing.assert_allclose(other.rms, whole.rms, rtol=1e-9)
        assert other.pc1_variance_fraction == pytest.approx(whole.pc1_variance_fraction, rel=1e-9)
        assert other.pc1_correlation_fraction == pytest.approx(
            whole.pc1_correlation_fraction, rel=1e-9
        )


def test_the_sub_block_size_changes_memory_and_nothing_else():
    """A tiny sub-block that does not divide the window evenly must give the same numbers."""
    data = _noise(3, 10_007, seed=15).astype(np.float32)
    data[1, [4, 4000, 10_006]] = np.float32(2.5)
    big = _summarize(data, chunk_size=2500, rail_value=2.5)
    small = _summarize(data, chunk_size=2500, rail_value=2.5, subblock_bytes=8 * 3 * 13)
    np.testing.assert_array_equal(small.vmin, big.vmin)
    np.testing.assert_array_equal(small.vmax, big.vmax)
    np.testing.assert_array_equal(small.n_at_rail, big.n_at_rail)
    np.testing.assert_array_equal(small.n_at_vmin, big.n_at_vmin)
    np.testing.assert_array_equal(small.n_at_vmax, big.n_at_vmax)
    np.testing.assert_array_equal(small.psd_db, big.psd_db)
    np.testing.assert_allclose(small.rms, big.rms, rtol=1e-9)
    assert small.pc1_variance_fraction == pytest.approx(big.pc1_variance_fraction, rel=1e-9)
    assert small.n_samples == big.n_samples == 10_007


def test_the_spectrum_agrees_across_chunkings_within_tolerance():
    """Median of per-window medians versus one median over every segment.

    White noise has a flat spectrum, so the two estimators agree bin by bin up
    to estimator variance. No bin may be far off, nearly every bin must be
    close, and there must be no systematic offset between the two.
    """
    data = _noise(2, 60_000, seed=9)
    whole = _summarize(data)
    parts = _summarize(data, chunk_size=6000)
    np.testing.assert_array_equal(parts.psd_freqs_hz, whole.psd_freqs_hz)
    diff = parts.psd_db - whole.psd_db
    assert np.abs(diff).max() < 4.0
    assert np.mean(np.abs(diff) < 1.5) > 0.95
    assert np.abs(np.median(diff)) < 0.3


def test_the_caller_s_chunk_is_not_modified():
    data = _noise(2, 3000, seed=16) + 5.0
    before = data.copy()
    _summarize(data, chunk_size=1000, rail_value=5.0)
    np.testing.assert_array_equal(data, before)


# ---- shape and contract --------------------------------------------------------


def test_arrays_and_attrs_split_the_summary_the_way_a_store_wants():
    out = _summarize(_noise(3, 4000), rail_value=5.0)
    arrays = out.as_arrays()
    attrs = out.as_attrs()
    for key in (
        "psd_freqs_hz",
        "psd_db",
        "rms",
        "vmin",
        "vmax",
        "n_at_rail",
        "n_at_vmin",
        "n_at_vmax",
    ):
        assert isinstance(arrays[key], np.ndarray)
    for key in (
        "psd_method",
        "psd_nperseg",
        "psd_noverlap",
        "psd_window",
        "psd_detrend",
        "psd_scaling",
        "psd_within_window_average",
        "pc1_variance_fraction",
        "pc1_correlation_fraction",
        "n_samples",
        "n_windows",
        "n_channels",
        "rail_low",
        "rail_high",
    ):
        assert key in attrs
    assert attrs["psd_nperseg"] == 1000
    assert attrs["psd_noverlap"] == 500
    assert (attrs["rail_low"], attrs["rail_high"]) == (-5.0, 5.0)
    assert attrs["n_channels"] == 3
    assert not any(isinstance(v, np.ndarray) for v in attrs.values())


def test_summary_arrays_are_read_only():
    out = _summarize(_noise(2, 3000))
    for arr in out.as_arrays().values():
        assert not arr.flags.writeable
    with pytest.raises(ValueError):
        out.rms[0] = 0.0


def test_a_window_with_the_wrong_channel_count_is_refused():
    s = StreamSummarizer(SFREQ, 2, CFG)
    with pytest.raises(ValueError, match="n_samples"):
        s.update(np.zeros((3, 100)))
    with pytest.raises(ValueError, match="n_samples"):
        s.update(np.zeros(100))


def test_a_non_numeric_window_is_refused():
    s = StreamSummarizer(SFREQ, 1, CFG)
    with pytest.raises(ValueError, match="dtype"):
        s.update(np.zeros((1, 10), dtype=bool))


def test_an_empty_window_is_a_no_op():
    s = StreamSummarizer(SFREQ, 2, CFG)
    s.update(np.zeros((2, 0)))
    out = s.finalize()
    assert out.n_samples == 0
    assert np.all(np.isnan(out.rms))
