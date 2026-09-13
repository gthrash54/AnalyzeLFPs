"""Full-rate summaries of a stream, computed before it is resampled.

The derivative store keeps each stream at a lower rate than it was recorded.
Everything above the anti-alias cutoff is gone from the store, so this module
describes it before it goes: a Welch spectrum over the whole native band, exact
per-channel amplitude statistics, counts of samples pinned at the converter
rail or at the channel's own extreme, and the numbers guardrail G1 needs to
spot a common-mode failure (one signal appearing on every channel).

A whole block does not fit in memory, so the summarizer is fed a stream of
windows and keeps only accumulators between them. Inside `update` each window
is folded in fixed-size sub-blocks, so peak memory is bounded by the sub-block
size and not by the window the caller hands in (see "Memory" below).

Amplitude statistics
    Per-channel sums of squares, minima, maxima, rail counts and extreme
    counts. Sums are float64 and use `numpy.sum`, which reduces pairwise, so
    `rms` is exact over the whole stream up to float64 rounding order and does
    not depend on how the stream was cut into windows (agreement to about
    1e-9 relative on real blocks). `vmin`, `vmax`, `n_at_rail`, `n_at_vmin`
    and `n_at_vmax` are compared in the chunk's native dtype and are exact.

Rail counts
    `n_at_rail` counts samples equal to the rail value. The rail must be the
    exact value the converter emits at saturation, in the units the chunk
    carries, not a decimal literal that is merely close: a BrainVision channel
    that saturates at -0.8191404375 V is not found by 0.8191. A single float
    means a symmetric pair (-v, +v); a (low, high) pair handles converters
    whose rails differ, such as int16 at (-32768, 32767). The comparison is
    made in the chunk's own dtype (the rail is cast to it first) so a float32
    stream is matched by its float32 value. `n_at_vmin` and `n_at_vmax` need
    no rail: they count how many samples sit exactly on the channel's running
    minimum and maximum, which flags a saturation plateau at any rail value.

Channel covariance
    A running sum of outer products (`chunk @ chunk.T`) and a running sum,
    from which the covariance matrix follows at the end. Data are shifted by
    the first sample of the stream before accumulating, the standard guard
    against cancellation when a channel carries a large DC offset. The
    eigenvalues come from `numpy.linalg.eigvalsh`.

    `pc1_variance_fraction` is the largest eigenvalue of the covariance over
    their sum: near 1.0 means one signal is on every channel, near 1/n means
    the channels are independent. It is scale dependent by construction: one
    channel at 100x the gain of the others dominates the total variance and
    reads as common mode on its own. `pc1_correlation_fraction` is the same
    ratio on the correlation matrix (each channel standardized to unit
    variance, from the same accumulators), which is scale free and stays near
    1/n for independent channels whatever their gains. Both are reported so
    the consumer can tell a hot channel from a shared signal. Channels with
    zero variance are left out of the correlation matrix, since their
    correlation is undefined.

Spectrum
    `scipy.signal.welch` on each window (hann, constant detrend, density
    scaling, median across segments within the window), then the median (or
    mean, per config) across windows. This is a median of per-window medians
    rather than one median over every segment of the block. It bounds memory
    to one spectrum per window, about n_channels * nperseg/2 float32 values,
    instead of one spectrum per segment, which for an hour at 48828 Hz with
    one-second segments and 50 percent overlap would be 7200 spectra per
    channel. The nesting is acceptable because the spectrum is a description
    for a human and a guardrail, not an estimator a result depends on: the
    median of medians of a stationary process converges to the same value as
    the flat median, and for a non-stationary block the window-level median is
    if anything more robust to a transient than a flat median over all
    segments would be. With `aggregate: mean` only a running sum is held.
    Windows shorter than one Welch segment are skipped for the spectrum (there
    is nothing to estimate) but still count toward every other statistic.
    Because welch detrends each segment by its mean, the DC bin does not
    describe a DC offset; `vmin` and `vmax` do.

Memory
    `update` never materializes a float64 copy of the whole window. Each
    sub-block is cast into two reusable float64 buffers of `subblock_bytes`
    each, and welch runs one channel at a time into a preallocated float32
    spectrum, so its scratch is a few copies of one channel's window rather
    than of all channels at once. Per-window spectra for the median are kept
    in one growing array that is partitioned in place at `finalize`, so the
    median makes no further copy.

Non-finite samples
    A NaN or infinity would silently poison every accumulator for the rest of
    the stream, so `update` refuses a chunk that contains one with a
    ValueError. The block then fails loudly and the ledger records why.

Nothing here knows a study ID, a path or a time of day; it sees arrays only.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy.fft import rfftfreq
from scipy.signal import welch

from dbsspeech.derive.config import SummaryConfig

PSD_METHOD = "scipy.signal.welch"
PSD_WINDOW = "hann"
PSD_DETREND = "constant"
PSD_SCALING = "density"
PSD_WITHIN_WINDOW_AVERAGE = "median"

# Size of each of the two float64 working buffers a window is folded through.
DEFAULT_SUBBLOCK_BYTES = 16 * 1024 * 1024

RailValue = float | tuple[float, float]


@dataclass(frozen=True)
class StreamSummary:
    """What was measured about one stream at its native rate.

    `psd_db` is `10 * log10` of the aggregated power spectral density, in dB
    relative to one unit squared per Hz, float32 with shape
    ``(n_channels, n_freqs)``. When the spectrum was disabled or no window was
    long enough to estimate one, `psd_freqs_hz` and `psd_db` are empty along
    the frequency axis.

    `n_windows` counts the windows that entered the spectrum. `n_samples` counts
    every sample, including those in windows too short for the spectrum.

    Arrays are read-only, so the frozen contract holds for their contents too.
    """

    psd_freqs_hz: np.ndarray
    psd_db: np.ndarray
    psd_method: str
    rms: np.ndarray
    vmin: np.ndarray
    vmax: np.ndarray
    n_at_rail: np.ndarray
    pc1_variance_fraction: float
    n_samples: int
    n_windows: int
    pc1_correlation_fraction: float = float("nan")
    n_at_vmin: np.ndarray | None = None
    n_at_vmax: np.ndarray | None = None
    psd_nperseg: int = 0
    psd_noverlap: int = 0
    psd_aggregate: str = "median"
    rail_low: float | None = None
    rail_high: float | None = None

    @property
    def n_channels(self) -> int:
        return int(self.rms.shape[0])

    def as_arrays(self) -> dict[str, np.ndarray]:
        """The per-channel and per-frequency arrays, for datasets in a store."""
        zeros = np.zeros(self.n_channels, dtype=np.int64)
        return {
            "psd_freqs_hz": self.psd_freqs_hz,
            "psd_db": self.psd_db,
            "rms": self.rms,
            "vmin": self.vmin,
            "vmax": self.vmax,
            "n_at_rail": self.n_at_rail,
            "n_at_vmin": zeros if self.n_at_vmin is None else self.n_at_vmin,
            "n_at_vmax": zeros if self.n_at_vmax is None else self.n_at_vmax,
        }

    def as_attrs(self) -> dict[str, Any]:
        """Flat scalars describing how the arrays were made, for an attribute set."""
        return {
            "psd_method": self.psd_method,
            "psd_window": PSD_WINDOW,
            "psd_detrend": PSD_DETREND,
            "psd_scaling": PSD_SCALING,
            "psd_within_window_average": PSD_WITHIN_WINDOW_AVERAGE,
            "psd_aggregate_across_windows": self.psd_aggregate,
            "psd_nperseg": self.psd_nperseg,
            "psd_noverlap": self.psd_noverlap,
            "psd_units": "dB re 1 unit^2/Hz",
            "pc1_variance_fraction": self.pc1_variance_fraction,
            "pc1_correlation_fraction": self.pc1_correlation_fraction,
            "n_samples": self.n_samples,
            "n_windows": self.n_windows,
            "n_channels": self.n_channels,
            "rail_low": float("nan") if self.rail_low is None else float(self.rail_low),
            "rail_high": float("nan") if self.rail_high is None else float(self.rail_high),
        }


def _rail_bounds(rail_value: RailValue | None) -> tuple[float, float] | None:
    """Normalize a rail spec to (low, high); a single value means (-|v|, +|v|)."""
    if rail_value is None:
        return None
    if isinstance(rail_value, tuple):
        if len(rail_value) != 2:
            raise ValueError("rail_value must be a float or a (low, high) pair")
        low, high = float(rail_value[0]), float(rail_value[1])
        if low > high:
            raise ValueError("rail_value low must not exceed high")
        return low, high
    v = abs(float(rail_value))
    return -v, v


class StreamSummarizer:
    """Accumulate `StreamSummary` statistics over windows of one stream.

    Feed `update` with ``(n_channels, n_samples)`` windows at the native rate,
    in any window size, then call `finalize`. Windows need not be equal in
    length and the last one may be short. `subblock_bytes` sizes each of the
    two float64 working buffers; it changes memory, never a result.
    """

    def __init__(
        self,
        sfreq_hz: float,
        n_channels: int,
        cfg: SummaryConfig,
        rail_value: RailValue | None = None,
        *,
        subblock_bytes: int = DEFAULT_SUBBLOCK_BYTES,
    ) -> None:
        if sfreq_hz <= 0:
            raise ValueError("sfreq_hz must be positive")
        if n_channels < 1:
            raise ValueError("n_channels must be at least 1")
        if subblock_bytes < 1:
            raise ValueError("subblock_bytes must be positive")
        self.sfreq_hz = float(sfreq_hz)
        self.n_channels = int(n_channels)
        self.cfg = cfg
        self.rail = _rail_bounds(rail_value)
        self.subblock_samples = max(int(subblock_bytes // (8 * self.n_channels)), 1)

        psd = cfg.full_rate_psd
        self.psd_enabled = bool(psd.enabled)
        self.nperseg = max(int(round(psd.nperseg_s * self.sfreq_hz)), 1)
        self.noverlap = int(psd.overlap * self.nperseg)
        if self.noverlap >= self.nperseg:
            self.noverlap = self.nperseg - 1
        self.aggregate = psd.aggregate
        self.n_freqs = self.nperseg // 2 + 1

        n = self.n_channels
        self._n_samples = 0
        self._sumsq = np.zeros(n, dtype=np.float64)
        self._min = np.full(n, np.inf, dtype=np.float64)
        self._max = np.full(n, -np.inf, dtype=np.float64)
        self._n_at_rail = np.zeros(n, dtype=np.int64)
        self._n_at_vmin = np.zeros(n, dtype=np.int64)
        self._n_at_vmax = np.zeros(n, dtype=np.int64)
        # Covariance accumulators on data shifted by the first sample seen.
        self._shift: np.ndarray | None = None
        self._shifted_sum = np.zeros(n, dtype=np.float64)
        self._outer = np.zeros((n, n), dtype=np.float64)
        # Working buffers, allocated on first use to the sub-block size.
        self._buf: np.ndarray | None = None
        self._sq: np.ndarray | None = None
        # Spectra: one float32 row block per window (median), or a running
        # float64 sum (mean).
        self._n_windows = 0
        self._psd_stack: np.ndarray | None = None
        self._psd_sum = np.zeros((n, self.n_freqs), dtype=np.float64)

    # ---- feeding --------------------------------------------------------------

    def update(self, chunk: np.ndarray) -> None:
        """Fold one ``(n_channels, n_samples)`` window into the accumulators.

        The chunk is read in its own dtype; only sub-block sized float64 copies
        are made. Raises ValueError on a wrong shape, a non-numeric dtype, or a
        non-finite sample.
        """
        x = np.asarray(chunk)
        if x.ndim != 2 or x.shape[0] != self.n_channels:
            raise ValueError(f"expected ({self.n_channels}, n_samples), got shape {tuple(x.shape)}")
        if x.dtype.kind not in "iuf":
            raise ValueError(f"chunk must be integer or float, got dtype {x.dtype}")
        n = x.shape[1]
        if n == 0:
            return
        if self._shift is None:
            self._shift = x[:, 0].astype(np.float64)

        step = self.subblock_samples
        for start in range(0, n, step):
            self._fold(x[:, start : start + step])

        if self.psd_enabled and n >= self.nperseg:
            self._add_spectrum(x)

    def _fold(self, blk: np.ndarray) -> None:
        """Accumulate one sub-block: exact extremes and counts, then float64 sums."""
        m = blk.shape[1]
        if blk.dtype.kind == "f":
            finite = np.isfinite(blk)
            if not finite.all():
                bad = (~finite).sum(axis=1)
                raise ValueError(f"non-finite sample in chunk: {bad.tolist()} per channel")

        bmin = blk.min(axis=1)
        bmax = blk.max(axis=1)
        at_min = (blk == bmin[:, None]).sum(axis=1)
        at_max = (blk == bmax[:, None]).sum(axis=1)
        self._n_at_vmin = _merge_extreme_count(
            self._n_at_vmin, at_min, bmin.astype(np.float64), self._min, lower_is_new=True
        )
        self._n_at_vmax = _merge_extreme_count(
            self._n_at_vmax, at_max, bmax.astype(np.float64), self._max, lower_is_new=False
        )
        np.minimum(self._min, bmin, out=self._min)
        np.maximum(self._max, bmax, out=self._max)

        if self.rail is not None:
            low = np.asarray(self.rail[0], dtype=blk.dtype)
            high = np.asarray(self.rail[1], dtype=blk.dtype)
            hits = blk == low
            if high != low:
                hits |= blk == high
            self._n_at_rail += hits.sum(axis=1)

        buf, sq = self._buffers(m)
        np.copyto(buf, blk)
        np.multiply(buf, buf, out=sq)
        self._sumsq += sq.sum(axis=1)
        assert self._shift is not None
        buf -= self._shift[:, None]
        self._shifted_sum += buf.sum(axis=1)
        self._outer += buf @ buf.T
        self._n_samples += m

    def _buffers(self, m: int) -> tuple[np.ndarray, np.ndarray]:
        if self._buf is None or self._sq is None:
            shape = (self.n_channels, self.subblock_samples)
            self._buf = np.empty(shape, dtype=np.float64)
            self._sq = np.empty(shape, dtype=np.float64)
        return self._buf[:, :m], self._sq[:, :m]

    def _add_spectrum(self, x: np.ndarray) -> None:
        """welch one channel at a time into a float32 row block; store or sum it."""
        if self.aggregate == "median":
            stack = self._grow_stack()
            target = stack[self._n_windows]
        else:
            target = np.empty((self.n_channels, self.n_freqs), dtype=np.float32)
        for i in range(self.n_channels):
            row = np.asarray(x[i], dtype=np.float64)
            _, pxx = welch(
                row,
                fs=self.sfreq_hz,
                window=PSD_WINDOW,
                nperseg=self.nperseg,
                noverlap=self.noverlap,
                detrend=PSD_DETREND,
                scaling=PSD_SCALING,
                average=PSD_WITHIN_WINDOW_AVERAGE,
            )
            target[i] = pxx
        if self.aggregate != "median":
            self._psd_sum += target
        self._n_windows += 1

    def _grow_stack(self) -> np.ndarray:
        """The per-window spectrum array, doubled in capacity when it is full."""
        k = self._n_windows
        if self._psd_stack is None or k >= self._psd_stack.shape[0]:
            cap = 4 if self._psd_stack is None else 2 * self._psd_stack.shape[0]
            new = np.empty((cap, self.n_channels, self.n_freqs), dtype=np.float32)
            if self._psd_stack is not None:
                new[:k] = self._psd_stack[:k]
            self._psd_stack = new
        return self._psd_stack

    # ---- reducing -------------------------------------------------------------

    def finalize(self) -> StreamSummary:
        """Reduce the accumulators to a `StreamSummary`.

        Safe to call more than once: the median partitions the spectrum stack
        in place, which reorders values within each (channel, frequency) column
        but leaves every column's multiset, and so every aggregate, unchanged.
        """
        n = self._n_samples
        if n > 0:
            rms = np.sqrt(self._sumsq / n)
            vmin = self._min.copy()
            vmax = self._max.copy()
        else:
            rms = np.full(self.n_channels, np.nan)
            vmin = np.full(self.n_channels, np.nan)
            vmax = np.full(self.n_channels, np.nan)

        arrays = {
            "psd_freqs_hz": self._psd_freqs(),
            "psd_db": self._psd_db(),
            "rms": rms,
            "vmin": vmin,
            "vmax": vmax,
            "n_at_rail": self._n_at_rail.copy(),
            "n_at_vmin": self._n_at_vmin.copy(),
            "n_at_vmax": self._n_at_vmax.copy(),
        }
        for arr in arrays.values():
            arr.setflags(write=False)

        rail_low, rail_high = (None, None) if self.rail is None else self.rail
        return StreamSummary(
            psd_method=PSD_METHOD,
            pc1_variance_fraction=self._pc1_variance_fraction(),
            pc1_correlation_fraction=self._pc1_correlation_fraction(),
            n_samples=n,
            n_windows=self._n_windows,
            psd_nperseg=self.nperseg if self.psd_enabled else 0,
            psd_noverlap=self.noverlap if self.psd_enabled else 0,
            psd_aggregate=self.aggregate,
            rail_low=rail_low,
            rail_high=rail_high,
            **arrays,
        )

    def _psd_freqs(self) -> np.ndarray:
        if not self.psd_enabled or self._n_windows == 0:
            return np.empty(0, dtype=np.float64)
        # Same grid welch returns for a one-sided real spectrum of nperseg points.
        return np.asarray(rfftfreq(self.nperseg, d=1.0 / self.sfreq_hz), dtype=np.float64)

    def _psd_db(self) -> np.ndarray:
        k = self._n_windows
        if not self.psd_enabled or k == 0:
            return np.empty((self.n_channels, 0), dtype=np.float32)
        if self.aggregate == "median":
            assert self._psd_stack is not None
            linear = np.median(self._psd_stack[:k], axis=0, overwrite_input=True)
        else:
            linear = self._psd_sum / k
        # An all-zero channel has zero density; clamp so dB stays finite.
        floor = float(np.finfo(np.float32).tiny)
        linear = np.maximum(np.asarray(linear, dtype=np.float64), floor)
        return (10.0 * np.log10(linear)).astype(np.float32)

    def covariance(self) -> np.ndarray:
        """Sample covariance ``(n_channels, n_channels)`` of everything seen so far.

        NaN when fewer than two samples have arrived. The shift by the first
        sample cancels exactly in the covariance, so this is the covariance of
        the raw data.
        """
        n = self._n_samples
        if n < 2:
            return np.full((self.n_channels, self.n_channels), np.nan)
        s = self._shifted_sum
        return (self._outer - np.outer(s, s) / n) / (n - 1)

    def _pc1_variance_fraction(self) -> float:
        if self._n_samples < 2:
            return float("nan")
        eig = np.linalg.eigvalsh(self.covariance())
        total = float(eig.sum())
        if not np.isfinite(total) or total <= 0.0:
            return float("nan")
        return float(eig[-1] / total)

    def _pc1_correlation_fraction(self) -> float:
        """Largest eigenvalue of the correlation matrix over its trace.

        Channels with zero (or non-finite) variance are dropped first; the
        trace of what remains is the number of channels kept.
        """
        if self._n_samples < 2:
            return float("nan")
        cov = self.covariance()
        var = np.diag(cov)
        keep = np.isfinite(var) & (var > 0.0)
        if not keep.any():
            return float("nan")
        sd = np.sqrt(var[keep])
        corr = cov[np.ix_(keep, keep)] / np.outer(sd, sd)
        eig = np.linalg.eigvalsh(corr)
        total = float(eig.sum())
        if not np.isfinite(total) or total <= 0.0:
            return float("nan")
        return float(eig[-1] / total)


def _merge_extreme_count(
    running: np.ndarray,
    block_count: np.ndarray,
    block_extreme: np.ndarray,
    running_extreme: np.ndarray,
    *,
    lower_is_new: bool,
) -> np.ndarray:
    """Count of samples at the running extreme after seeing one more block.

    A block that beats the running extreme restarts the count; one that ties
    it adds to the count; one that does not reach it leaves the count alone.
    """
    beats = block_extreme < running_extreme if lower_is_new else block_extreme > running_extreme
    ties = block_extreme == running_extreme
    return np.where(beats, block_count, np.where(ties, running + block_count, running))
