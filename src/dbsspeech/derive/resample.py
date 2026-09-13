"""Exact-ratio resampling with a measured, not assumed, anti-alias response.

Three facts drive the design.

First, every acquisition rate in this archive is an exact small rational. TDT
reports 390625/8, 390625/16 and 390625/32 Hz (48828.125, 24414.0625 and
12207.03125), bit-exactly, and the BrainVision rig runs at round numbers. So a
target of exactly 8000 Hz is 512/3125 of 48828.125, and `scipy.signal.
resample_poly` reaches it in one polyphase stage at the cost of integer
decimation. There is no reason to accept a drifted rate like 8138.02 Hz.

Second, the default window `resample_poly` designs its filter with puts the
-6 dB point ON the new Nyquist, so content just above it folds back barely
attenuated. The filter is therefore designed here explicitly, with
`scipy.signal.kaiserord` and `scipy.signal.firwin`, for a stated passband, a
stopband at the new Nyquist, and a stated attenuation.

Third, the response is then MEASURED with `scipy.signal.freqz` and written into
the `FilterReport` that travels with every derivative. "This analysis did not
claim a band the filter removed" becomes something a later reader checks
against a number, not against a convention that 0.8 of Nyquist is safe.

Nothing here re-references. A bipolar montage is a linear combination across
channels and the filter is a linear operator along time, so they commute
exactly; deferring the montage costs nothing and keeps the store free of a
guess about per-contact lead assignment that has not been curated yet.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from fractions import Fraction

import numpy as np
from scipy.signal import firwin, freqz, kaiserord, resample_poly

# Denominators of the rates actually present in this archive top out at 3125
# (from 390625 = 5^8). Anything needing more is not one of our rates and is
# refused rather than approximated.
DEFAULT_MAX_DENOMINATOR = 3125


class RateNotRational(ValueError):
    """The requested conversion is not an exact small rational of the input."""


@dataclass(frozen=True)
class FilterSpec:
    """What the anti-alias filter is asked to do.

    Fractions are of the OUTPUT Nyquist. The default passband of 0.8 matches the
    convention guardrail G6 already assumes, so a derivative built with these
    defaults is usable to exactly the band G6 expects, and now provably so.
    """

    passband_fraction_of_out_nyquist: float = 0.8
    stopband_fraction_of_out_nyquist: float = 1.0
    stopband_attenuation_db: float = 90.0
    # The measured alias floor must be at least this good or the design is
    # refused. Slightly looser than the attenuation asked for, because the
    # measurement is a worst case over every image band.
    require_measured_alias_floor_db: float = -80.0

    def __post_init__(self) -> None:
        lo = self.passband_fraction_of_out_nyquist
        hi = self.stopband_fraction_of_out_nyquist
        if not 0.0 < lo < hi <= 1.0:
            raise ValueError(
                "need 0 < passband < stopband <= 1 (fractions of output Nyquist), got "
                f"{self.passband_fraction_of_out_nyquist} and "
                f"{self.stopband_fraction_of_out_nyquist}"
            )
        if self.stopband_attenuation_db <= 0:
            raise ValueError("stopband attenuation must be positive dB")


@dataclass(frozen=True)
class FilterReport:
    """The filter that was applied and what it measurably did.

    Every field ending in `_hz` is in output-rate terms, so a reader of the
    derivative compares them directly against the bands it wants to claim.
    """

    up: int
    down: int
    sfreq_in_hz: float
    sfreq_out_hz: float
    sfreq_in_exact: str
    sfreq_out_exact: str
    design: str
    ntaps: int
    coeff_sha256: str
    # Designed.
    passband_edge_hz: float
    stopband_edge_hz: float
    stopband_attenuation_db: float
    # Measured with freqz.
    minus_0p1_db_hz: float
    minus_3_db_hz: float
    measured_stopband_edge_hz: float
    attenuation_at_out_nyquist_db: float
    alias_floor_db: float
    # The number a later guardrail consumes.
    usable_bandwidth_hz: float

    @property
    def nyquist_out_hz(self) -> float:
        return self.sfreq_out_hz / 2.0

    def as_attrs(self) -> dict[str, float | int | str]:
        """Flat mapping suitable for an HDF5 attribute set or a JSON sidecar."""
        return {
            "resample_up": self.up,
            "resample_down": self.down,
            "resample_method": "scipy.signal.resample_poly",
            "sfreq_in_hz": self.sfreq_in_hz,
            "sfreq_out_hz": self.sfreq_out_hz,
            "sfreq_in_exact": self.sfreq_in_exact,
            "sfreq_out_exact": self.sfreq_out_exact,
            "filter_design": self.design,
            "filter_ntaps": self.ntaps,
            "filter_coeff_sha256": self.coeff_sha256,
            "passband_edge_hz": self.passband_edge_hz,
            "stopband_edge_hz": self.stopband_edge_hz,
            "stopband_attenuation_db": self.stopband_attenuation_db,
            "minus_0p1_db_hz": self.minus_0p1_db_hz,
            "minus_3_db_hz": self.minus_3_db_hz,
            "measured_stopband_edge_hz": self.measured_stopband_edge_hz,
            "attenuation_at_out_nyquist_db": self.attenuation_at_out_nyquist_db,
            "alias_floor_db": self.alias_floor_db,
            "usable_bandwidth_hz": self.usable_bandwidth_hz,
        }


def exact_ratio(
    sfreq_in_hz: float,
    target_hz: float,
    max_denominator: int = DEFAULT_MAX_DENOMINATOR,
) -> tuple[int, int]:
    """(up, down) such that sfreq_in * up / down == target, exactly.

    Uses `fractions.Fraction` on the float values directly. The archive's rates
    are exact binary fractions, so this recovers their true rational form
    without any limit_denominator rounding. A rate that is not one of ours
    produces a huge denominator and is refused, because silently approximating
    a sample rate is how a derivative ends up 1.7 percent off and nobody
    notices for a year.
    """
    if sfreq_in_hz <= 0 or target_hz <= 0:
        raise ValueError("sample rates must be positive")
    ratio = Fraction(target_hz) / Fraction(sfreq_in_hz)
    if ratio.denominator > max_denominator:
        raise RateNotRational(
            f"{sfreq_in_hz} Hz -> {target_hz} Hz is {ratio.numerator}/{ratio.denominator}, "
            f"denominator exceeds {max_denominator}; not an exact rate of this archive"
        )
    return ratio.numerator, ratio.denominator


def exact_rate_string(sfreq_hz: float) -> str:
    """'390625/8' for 48828.125, '1000/1' for 1000. Provenance-friendly."""
    f = Fraction(sfreq_hz)
    return f"{f.numerator}/{f.denominator}"


def design_antialias(
    up: int,
    down: int,
    sfreq_in_hz: float,
    spec: FilterSpec | None = None,
) -> tuple[np.ndarray, FilterReport]:
    """Design the filter for one exact ratio and measure what it does.

    The filter runs at the upsampled rate `sfreq_in * up`, which is where
    `resample_poly` applies it. Edges are placed relative to the OUTPUT Nyquist,
    which is the lower of the two Nyquists whenever `down > up`, so the same
    spec is correct for both decimation and mild upsampling.

    Uses `scipy.signal.kaiserord` for the tap count and beta,
    `scipy.signal.firwin` for the taps, and `scipy.signal.freqz` to measure the
    result. Refuses to return a filter whose measured alias floor misses the
    spec.
    """
    spec = spec or FilterSpec()
    if up < 1 or down < 1:
        raise ValueError("up and down must be positive integers")

    sfreq_out = sfreq_in_hz * up / down
    fs_design = sfreq_in_hz * up
    nyq_design = fs_design / 2.0
    nyq_out = sfreq_out / 2.0
    # Cutoff can never exceed the input Nyquist either; for upsampling that is
    # the binding one.
    nyq_limit = min(nyq_out, sfreq_in_hz / 2.0)

    pass_hz = spec.passband_fraction_of_out_nyquist * nyq_limit
    stop_hz = spec.stopband_fraction_of_out_nyquist * nyq_limit
    width = (stop_hz - pass_hz) / nyq_design

    ntaps, beta = kaiserord(spec.stopband_attenuation_db, width)
    if ntaps % 2 == 0:
        ntaps += 1  # odd length: type I FIR, symmetric, exact linear phase
    cutoff = (pass_hz + stop_hz) / 2.0 / nyq_design
    taps = firwin(ntaps, cutoff, window=("kaiser", beta))
    taps = np.asarray(taps, dtype=np.float64)

    report = _measure(
        taps=taps,
        up=up,
        down=down,
        sfreq_in_hz=sfreq_in_hz,
        sfreq_out_hz=sfreq_out,
        fs_design=fs_design,
        pass_hz=pass_hz,
        stop_hz=stop_hz,
        spec=spec,
        design=f"kaiser(beta={beta:.3f}) firwin, cutoff {cutoff * nyq_design:.3f} Hz",
    )
    if report.alias_floor_db > spec.require_measured_alias_floor_db:
        raise ValueError(
            f"designed filter measures an alias floor of {report.alias_floor_db:.1f} dB, "
            f"worse than the required {spec.require_measured_alias_floor_db:.1f} dB"
        )
    return taps, report


def _measure(
    *,
    taps: np.ndarray,
    up: int,
    down: int,
    sfreq_in_hz: float,
    sfreq_out_hz: float,
    fs_design: float,
    pass_hz: float,
    stop_hz: float,
    spec: FilterSpec,
    design: str,
) -> FilterReport:
    # Enough points to resolve the transition band comfortably. freqz takes
    # the FFT path for an integer worN with a scalar denominator, so this is
    # cheap even for a filter of a hundred thousand taps.
    n_points = int(2 ** np.ceil(np.log2(max(len(taps) * 8, 2**16))))
    w, h = freqz(taps, worN=n_points, fs=fs_design)
    mag = np.abs(h)
    mag_db = 20.0 * np.log10(np.maximum(mag, 1e-300)) - 20.0 * np.log10(max(mag[0], 1e-300))

    def first_below(threshold_db: float) -> float:
        idx = np.argmax(mag_db < threshold_db)
        return float(w[idx]) if mag_db[idx] < threshold_db else float(w[-1])

    minus_0p1 = first_below(-0.1)
    minus_3 = first_below(-3.0)
    # Measured stopband edge: first frequency from which the response never
    # again rises above -attenuation. Looking from the top down finds the last
    # violation.
    above = np.nonzero(mag_db > -spec.stopband_attenuation_db)[0]
    if above.size and above[-1] + 1 < w.size:
        measured_stop = float(w[above[-1] + 1])
    else:
        measured_stop = float(w[-1])

    nyq_out = sfreq_out_hz / 2.0
    at_nyq = float(np.interp(nyq_out, w, mag_db))

    # Usable band: what was designed, unless the measurement came in short.
    usable = min(pass_hz, minus_0p1)

    # Alias floor: worst response among every frequency that folds into the
    # usable band after sampling at sfreq_out. f folds to |f - k*fs_out| for
    # the nearest integer k, so anything above the output Nyquist whose folded
    # image lands inside [0, usable] counts.
    folded = np.abs(w - np.round(w / sfreq_out_hz) * sfreq_out_hz)
    candidates = (w > nyq_out) & (folded <= usable)
    alias_floor = float(mag_db[candidates].max()) if candidates.any() else float("-inf")

    return FilterReport(
        up=up,
        down=down,
        sfreq_in_hz=sfreq_in_hz,
        sfreq_out_hz=sfreq_out_hz,
        sfreq_in_exact=exact_rate_string(sfreq_in_hz),
        sfreq_out_exact=exact_rate_string(sfreq_out_hz),
        design=design,
        ntaps=int(len(taps)),
        coeff_sha256=hashlib.sha256(taps.tobytes()).hexdigest(),
        passband_edge_hz=pass_hz,
        stopband_edge_hz=stop_hz,
        stopband_attenuation_db=spec.stopband_attenuation_db,
        minus_0p1_db_hz=minus_0p1,
        minus_3_db_hz=minus_3,
        measured_stopband_edge_hz=measured_stop,
        attenuation_at_out_nyquist_db=at_nyq,
        alias_floor_db=alias_floor,
        usable_bandwidth_hz=usable,
    )


def resample_exact(data: np.ndarray, up: int, down: int, taps: np.ndarray) -> np.ndarray:
    """Resample ``(n_channels, n_samples)`` by ``up/down`` with the given taps.

    `scipy.signal.resample_poly` with an array `window` uses it directly as the
    FIR coefficients (scaled by `up` internally), which is what makes the
    measured report above describe the filter that actually ran. Polyphase
    computes only the retained samples, so the exact ratio costs the same as
    integer decimation. `padtype="line"` extends the edges linearly, which
    keeps the transient at the start and end of a block small.
    """
    if data.ndim != 2:
        raise ValueError(f"expected (n_channels, n_samples), got shape {data.shape}")
    if up == 1 and down == 1:
        return np.array(data, dtype=np.float64, copy=True)
    return resample_poly(
        np.asarray(data, dtype=np.float64), up, down, axis=-1, window=taps, padtype="line"
    )


def resample_to(
    data: np.ndarray,
    sfreq_in_hz: float,
    target_hz: float,
    spec: FilterSpec | None = None,
    max_denominator: int = DEFAULT_MAX_DENOMINATOR,
) -> tuple[np.ndarray, FilterReport]:
    """Convenience: ratio, design, measure, resample, in one call."""
    up, down = exact_ratio(sfreq_in_hz, target_hz, max_denominator)
    if up == down:
        report = _identity_report(sfreq_in_hz)
        return resample_exact(data, 1, 1, np.ones(1)), report
    taps, report = design_antialias(up, down, sfreq_in_hz, spec)
    return resample_exact(data, up, down, taps), report


def _identity_report(sfreq_hz: float) -> FilterReport:
    exact = exact_rate_string(sfreq_hz)
    return FilterReport(
        up=1, down=1, sfreq_in_hz=sfreq_hz, sfreq_out_hz=sfreq_hz,
        sfreq_in_exact=exact, sfreq_out_exact=exact, design="identity", ntaps=1,
        coeff_sha256=hashlib.sha256(np.ones(1).tobytes()).hexdigest(),
        passband_edge_hz=sfreq_hz / 2.0, stopband_edge_hz=sfreq_hz / 2.0,
        stopband_attenuation_db=float("inf"), minus_0p1_db_hz=sfreq_hz / 2.0,
        minus_3_db_hz=sfreq_hz / 2.0, measured_stopband_edge_hz=sfreq_hz / 2.0,
        attenuation_at_out_nyquist_db=0.0, alias_floor_db=float("-inf"),
        usable_bandwidth_hz=sfreq_hz / 2.0,
    )
