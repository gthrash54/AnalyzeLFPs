"""Decimation, with the usable bandwidth stated rather than assumed.

`scipy.signal.decimate` and MATLAB's `decimate` both apply an anti-alias filter
before downsampling. The filter's cutoff is a fraction of the new Nyquist, so the
usable bandwidth after decimation is meaningfully lower than the new Nyquist
itself, and analysis that ignores this reports content the filter removed.

Guardrail G6 refuses a run whose requested bands reach above that cutoff. This
module provides the number the guardrail checks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Both scipy and MATLAB place the anti-alias cutoff here, as a fraction of the
# new Nyquist. Overridable from configs/guardrails.yaml, and that override now
# actually works: `cutoff_fraction_from` below is what makes the sentence true.
DEFAULT_CUTOFF_FRACTION = 0.8


def cutoff_fraction_from(configs: dict | None) -> float:
    """The configured anti-alias cutoff, as a fraction of Nyquist.

    `configs/guardrails.yaml` has offered `antialias_cutoff_fraction_of_nyquist`
    since G6 was written and nothing read it, while four recipes hard-coded
    `sfreq * 0.4`, which is the same quantity expressed as a fraction of the
    sampling rate rather than of Nyquist. A lab lowering the config value saw
    the file change and no behaviour change, and had no way to tell.

    Reads the config where it exists and falls back to the documented default,
    so a manifest loaded without guardrails still works.
    """
    spec = (
        ((configs or {}).get("guardrails") or {}).get("guardrails") or {}
    ).get("G6_decimation_removes_claimed_band") or {}
    value = spec.get("antialias_cutoff_fraction_of_nyquist")
    try:
        fraction = float(value)
    except (TypeError, ValueError):
        return DEFAULT_CUTOFF_FRACTION
    if not 0.0 < fraction <= 1.0:
        raise ValueError(
            "antialias_cutoff_fraction_of_nyquist is a fraction of Nyquist and "
            f"must be in (0, 1]; configs/guardrails.yaml says {fraction!r}"
        )
    return fraction


def usable_bandwidth_hz(
    sfreq_hz: float, cutoff_fraction: float = DEFAULT_CUTOFF_FRACTION
) -> float:
    """Highest frequency the data supports after anti-alias filtering."""
    return sfreq_hz / 2.0 * cutoff_fraction


@dataclass(frozen=True)
class DecimationResult:
    """Decimated data plus what the decimation did to the bandwidth."""

    data: np.ndarray
    sfreq_hz: float
    factor: int
    usable_bandwidth_hz: float
    n_stages: int

    @property
    def nyquist_hz(self) -> float:
        return self.sfreq_hz / 2.0


def decimate_stream(
    data: np.ndarray,
    sfreq_hz: float,
    factor: int,
    cutoff_fraction: float = DEFAULT_CUTOFF_FRACTION,
    max_single_stage: int = 13,
) -> DecimationResult:
    """Decimate ``(n_channels, n_samples)`` by an integer factor.

    A single stage is preferred: chaining stages chains filters, and the combined
    response is harder to state and to reproduce in another language. scipy warns
    above a factor of 13 for IIR stability, so larger factors are split, and the
    number of stages is reported so a run record can carry it.
    """
    from scipy.signal import decimate as _decimate

    if factor < 1:
        raise ValueError(f"decimation factor must be at least 1, got {factor}")
    if factor == 1:
        return DecimationResult(
            data=data,
            sfreq_hz=sfreq_hz,
            factor=1,
            usable_bandwidth_hz=usable_bandwidth_hz(sfreq_hz, cutoff_fraction),
            n_stages=0,
        )

    stages = _factor_stages(factor, max_single_stage)
    out = data
    for stage in stages:
        # zero_phase applies the filter forwards and backwards, so no group delay
        # is introduced. MATLAB's decimate does the same by default.
        out = _decimate(out, stage, axis=-1, zero_phase=True)

    new_sfreq = sfreq_hz / factor
    return DecimationResult(
        data=out,
        sfreq_hz=new_sfreq,
        factor=factor,
        usable_bandwidth_hz=usable_bandwidth_hz(new_sfreq, cutoff_fraction),
        n_stages=len(stages),
    )


def _factor_stages(factor: int, max_single_stage: int) -> list[int]:
    """Split a factor into stages, preferring one."""
    if factor <= max_single_stage:
        return [factor]
    stages: list[int] = []
    remaining = factor
    for candidate in range(max_single_stage, 1, -1):
        while remaining % candidate == 0 and remaining > max_single_stage:
            stages.append(candidate)
            remaining //= candidate
    if remaining > 1:
        stages.append(remaining)
    return stages


def suggest_factor(sfreq_hz: float, target_hz: float) -> int:
    """Largest integer factor whose result is at or above `target_hz`."""
    if target_hz <= 0 or target_hz >= sfreq_hz:
        return 1
    return max(1, int(sfreq_hz // target_hz))
