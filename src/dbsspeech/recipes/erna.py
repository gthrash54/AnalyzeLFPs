"""erna: amplitude, frequency, and decay of evoked resonant neural activity.

ERNA is the ringing that follows a burst of DBS stimulation, measured on the
electrode that produced it. Amplitude, frequency, and how fast it decays are what
the lab wants out of it.

**This recipe does not know your ERNA definition, and does not pretend to.**
There is no single one. ERNA is defined by a stimulation protocol, and protocols
differ in pulse rate, burst length, burst spacing, amplifier blanking, and what
counts as the response window. Rather than encode one lab's convention as though
it were the method, every number that shapes the answer is a parameter with a
default in `configs/erna.yaml`, and the resolved value of each is written into
the run record and printed in the figure caption.

Those defaults are starting points and say so. Until someone who knows the
protocol has reviewed them and set `defaults_reviewed: true`, every run carries a
note on its figure and in its summary saying the settings were not reviewed. A
number produced under unreviewed defaults is a number about this software, not
about a brain.

What it does, per stimulation event and per derivation:

1. Discard `blanking_ms` after the event. This is the whole analysis. Too short
   and a recovering amplifier is measured as a resonance; too long and the first
   and largest cycles are gone. It is a parameter, it is logged, and it is on the
   figure.
2. Band-pass the analysis window with a fourth-order Butterworth applied forwards
   and backwards (`scipy.signal.butter`, `scipy.signal.sosfiltfilt`). An IIR of
   short impulse response rather than MNE's default FIR, because the window is
   about a tenth of a second and a long filter would smear the artifact edge
   straight into it.
3. Find successive extrema (`scipy.signal.find_peaks`, on the signal and its
   negation).
4. Amplitude: the first peak-to-trough excursion, in the recording's units.
5. Frequency, two ways that have to agree: the reciprocal of the median
   inter-peak interval, and the spectral peak inside the band (`numpy.fft.rfft`).
   Disagreement beyond `max_frequency_disagreement` marks the epoch, because two
   measurements of one thing disagreeing means it is not that thing.
6. Decay: a straight line fitted to the log of successive extrema amplitudes
   against time (`scipy.stats.linregress`), reported as a time constant with its
   R-squared. Below `min_r_squared` the constant is reported as missing rather
   than as a bad number.

Stimulation events come from one of three sources, none of which is assumed:
the artifact in the signal itself, condition windows in `manifest/windows.csv`,
or an epoch store in the recording.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ..preprocess import cutoff_fraction_from, usable_bandwidth_hz
from .psd import _shared_guardrail_context
from .registry import RecipeContext, RecipeResult, recipe

NAME = "erna"

# Where a setting lands when neither the run nor the config supplies it. Only
# reached if someone deletes a key from configs/erna.yaml; every one of these is
# also stated there, with what it does.
SETTING_PATHS: dict[str, Any] = {
    "stim.source": "amplitude_threshold",
    "stim.threshold_mad": 12.0,
    "stim.refractory_ms": 100.0,
    "stim.condition": "",
    "stim.epoch_store": "",
    "window.blanking_ms": 4.0,
    "window.analysis_ms": 100.0,
    "band.low_hz": 100.0,
    "band.high_hz": 500.0,
    "peaks.min_peaks": 4,
    "peaks.min_prominence_fraction": 0.1,
    "peaks.max_interval_jitter": 0.35,
    "decay.fit": True,
    "decay.min_r_squared": 0.5,
    "quality.max_frequency_disagreement": 0.25,
}


class ErnaParams(BaseModel):
    """Parameters for erna.

    Every field that shapes a number defaults to None, meaning "take it from
    `configs/erna.yaml`". That is deliberate: a default written here would be a
    convention this code invented, and it would travel into results without
    anyone choosing it. The resolved values, and where each came from, are in
    every run record.
    """

    # Twenty parameters is a wall to anyone who has not run this before. Three of
    # them decide the answer: where the stimulation events are, how much to blank
    # after each, and how long a window to measure. The rest have config defaults
    # and belong under Advanced.
    LABELS: ClassVar[dict[str, str]] = {
        "leads": "Leads to include",
        "primary_reference": "Montage the result is reported in",
        "references": "Montages to compute",
        "sfreq_target_hz": "Analyze at this sampling rate (Hz)",
        "stim_source": "Where the stimulation events are",
        "stim_threshold_mad": "Artifact threshold (median absolute deviations)",
        "stim_refractory_ms": "Minimum spacing between events (ms)",
        "stim_condition": "Condition marking stimulation",
        "stim_epoch_store": "Epoch store holding the events",
        "max_events": "Most events to analyze",
        "blanking_ms": "Discard after each pulse (ms)",
        "analysis_ms": "Measure this long afterwards (ms)",
        "bandpass_low_hz": "Band-pass, low edge (Hz)",
        "bandpass_high_hz": "Band-pass, high edge (Hz)",
        "min_peaks": "Fewest peaks to measure an epoch",
        "min_prominence_fraction": "Peak prominence (fraction of the largest)",
        "max_interval_jitter": "How irregular before the ringing counts as over",
        "fit_decay": "Fit the decay",
        "min_r_squared": "Smallest acceptable fit quality",
        "max_frequency_disagreement": "Tolerated disagreement between the two frequencies",
    }
    ESSENTIAL: ClassVar[tuple[str, ...]] = (
        "stim_source", "blanking_ms", "analysis_ms",
    )

    leads: list[str] | None = Field(default=None, description="None means every lead.")
    primary_reference: str = Field(
        default="bipolar_vertical",
        description="ERNA is recorded on the stimulating lead, so a montage that "
                    "keeps per-contact identity is usually what you want.",
    )
    references: list[str] | None = Field(
        default=None, description="None means the primary reference only.")
    sfreq_target_hz: float | None = Field(
        default=None, gt=0,
        description="None keeps the recording's own rate. ERNA lives in the "
                    "hundreds of hertz, so decimating far is how you lose it. "
                    "Guardrail G6 refuses a band above the anti-alias cutoff.",
    )

    stim_source: Literal["amplitude_threshold", "windows", "epochs"] | None = Field(
        default=None,
        description="How stimulation events are located: the artifact in the "
                    "signal, condition windows from the manifest, or an epoch "
                    "store in the recording.",
    )
    stim_threshold_mad: float | None = Field(
        default=None, gt=0,
        description="amplitude_threshold only. Median absolute deviations above "
                    "the median that count as an artifact.",
    )
    stim_refractory_ms: float | None = Field(
        default=None, gt=0,
        description="Minimum spacing between events. This is what stops one "
                    "artifact being counted as several; set it just under the "
                    "spacing of the events you want counted separately.",
    )
    stim_condition: str | None = Field(
        default=None, description="windows source: which condition's windows are events.")
    stim_epoch_store: str | None = Field(
        default=None, description="epochs source: which epoch store, by name.")
    max_events: int = Field(
        default=500, ge=1,
        description="Cap on events analyzed, oldest first. A recording with "
                    "thousands is usually a detection that is firing on noise.",
    )

    blanking_ms: float | None = Field(
        default=None, ge=0,
        description="Milliseconds discarded after each event. The single most "
                    "consequential setting here.",
    )
    analysis_ms: float | None = Field(
        default=None, gt=0, description="Milliseconds analyzed after the blanking.")
    bandpass_low_hz: float | None = Field(default=None, gt=0)
    bandpass_high_hz: float | None = Field(default=None, gt=0)
    min_peaks: int | None = Field(
        default=None, ge=2,
        description="Fewest successive peaks for an epoch to be measured at all.")
    min_prominence_fraction: float | None = Field(default=None, gt=0, le=1.0)
    max_interval_jitter: float | None = Field(
        default=None, gt=0,
        description="How far one interval between extrema may differ from the "
                    "ones before it before the resonance is considered over. "
                    "This is what stops noise after the ringing being measured "
                    "as part of it.",
    )
    fit_decay: bool | None = Field(default=None)
    min_r_squared: float | None = Field(default=None, ge=0.0, le=1.0)
    max_frequency_disagreement: float | None = Field(default=None, gt=0)


def _config(configs: dict[str, Any]) -> dict[str, Any]:
    return configs.get("erna") or {}


def _from_config(configs: dict[str, Any], path: str) -> Any:
    node: Any = _config(configs)
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return SETTING_PATHS[path]
        node = node[part]
    return node


def resolve(params: ErnaParams, configs: dict[str, Any]) -> dict[str, Any]:
    """Every setting, its value, and where it came from.

    Returned rather than folded into the params object so the run record can say
    "this came from the config" or "this was set for this run". Six months later
    that is the difference between a reproducible result and a puzzle.
    """
    mapping = {
        "stim_source": "stim.source",
        "stim_threshold_mad": "stim.threshold_mad",
        "stim_refractory_ms": "stim.refractory_ms",
        "stim_condition": "stim.condition",
        "stim_epoch_store": "stim.epoch_store",
        "blanking_ms": "window.blanking_ms",
        "analysis_ms": "window.analysis_ms",
        "bandpass_low_hz": "band.low_hz",
        "bandpass_high_hz": "band.high_hz",
        "min_peaks": "peaks.min_peaks",
        "min_prominence_fraction": "peaks.min_prominence_fraction",
        "max_interval_jitter": "peaks.max_interval_jitter",
        "fit_decay": "decay.fit",
        "min_r_squared": "decay.min_r_squared",
        "max_frequency_disagreement": "quality.max_frequency_disagreement",
    }
    out: dict[str, Any] = {}
    for field_name, config_path in mapping.items():
        given = getattr(params, field_name)
        if given is None:
            out[field_name] = {"value": _from_config(configs, config_path),
                               "source": f"configs/erna.yaml:{config_path}"}
        else:
            out[field_name] = {"value": given, "source": "run parameter"}
    return out


def settings(params: ErnaParams, configs: dict[str, Any]) -> dict[str, Any]:
    """Just the values, for the code that has to do the arithmetic."""
    return {k: v["value"] for k, v in resolve(params, configs).items()}


def review_state(configs: dict[str, Any]) -> dict[str, Any]:
    """Whether anyone has looked at these settings, and what they said."""
    cfg = _config(configs)
    return {
        "reviewed": bool(cfg.get("defaults_reviewed", False)),
        "reviewed_by": str(cfg.get("reviewed_by", "") or ""),
        "reviewed_on": str(cfg.get("reviewed_on", "") or ""),
        "protocol_note": str(cfg.get("protocol_note", "") or "").strip(),
    }


# ---------------------------------------------------------------------------
# Finding the stimulation events
# ---------------------------------------------------------------------------

def _events_from_amplitude(
    signal: np.ndarray, sfreq_hz: float, threshold_mad: float, refractory_ms: float
) -> np.ndarray:
    """Sample indices where the stimulation artifact starts.

    Robust units throughout: the artifact is orders of magnitude larger than the
    signal, so a median absolute deviation threshold finds it without any
    assumption about amplitude, and a mean would be dragged by the artifact it is
    supposed to detect.
    """
    trace = np.max(np.abs(signal), axis=0) if signal.ndim > 1 else np.abs(signal)
    median = float(np.median(trace))
    mad = float(np.median(np.abs(trace - median)))
    if mad <= 0:
        return np.array([], dtype=int)
    # 1.4826 puts a MAD on the same scale as a standard deviation for normal data.
    above = trace - median > threshold_mad * mad * 1.4826
    if not above.any():
        return np.array([], dtype=int)

    starts = np.flatnonzero(above & ~np.concatenate(([False], above[:-1])))
    refractory = int(round(refractory_ms * sfreq_hz / 1000.0))
    kept: list[int] = []
    for index in starts:
        if not kept or index - kept[-1] >= refractory:
            kept.append(int(index))
    return np.asarray(kept, dtype=int)


def _events_from_windows(ctx: RecipeContext, condition: str) -> np.ndarray:
    """Window starts as stimulation events, for a lab that logs its stimulation.

    Naming no condition means every window in the manifest, which is rarely what
    anyone means and is silent about it otherwise. It is allowed, and it says so.
    """
    if not condition:
        ctx.log(
            "stim_source is 'windows' with no stim_condition set, so every window "
            "in the manifest is being treated as a stimulation event. Set "
            "stim_condition to the condition that marks stimulation."
        )
    rows = ctx.session.windows(condition or None)
    return np.asarray([float(r["t_start_s"]) for r in rows], dtype=float)


def _events_from_epochs(ctx: RecipeContext, store: str) -> np.ndarray:
    epochs = getattr(ctx.session.recording, "epochs", None) or {}
    if store and store in epochs:
        rows = epochs[store]
    elif len(epochs) == 1:
        rows = next(iter(epochs.values()))
    else:
        raise ValueError(
            f"stim_source is 'epochs' but {store or 'no store'} is not one of "
            f"{sorted(epochs)}. Name the store with stim_epoch_store."
        )
    return np.asarray([float(r["onset"]) for r in rows], dtype=float)


# ---------------------------------------------------------------------------
# Measuring one epoch
# ---------------------------------------------------------------------------

def _bandpass(segment: np.ndarray, sfreq_hz: float, low: float, high: float) -> np.ndarray:
    """Fourth-order Butterworth, zero phase (scipy.signal.butter, sosfiltfilt).

    Zero phase matters here: a phase shift moves the peaks, and peak times are
    what the frequency and the decay are measured from.
    """
    from scipy.signal import butter, sosfiltfilt

    nyquist = sfreq_hz / 2.0
    high = min(high, nyquist * 0.95)
    if low >= high:
        raise ValueError(
            f"bandpass {low}-{high} Hz is empty at {sfreq_hz:g} Hz. Lower "
            "bandpass_low_hz, or record faster."
        )
    sos = butter(4, [low / nyquist, high / nyquist], btype="bandpass", output="sos")
    padlen = 3 * (sos.shape[0] * 2)
    if segment.size <= padlen:
        raise ValueError(
            f"analysis window is {segment.size} samples, too short to filter. "
            "Raise analysis_ms or the sampling rate."
        )
    return np.asarray(sosfiltfilt(sos, segment))


def _extrema(segment: np.ndarray, min_prominence_fraction: float) -> np.ndarray:
    """Indices of successive peaks and troughs, in time order."""
    from scipy.signal import find_peaks

    span = float(np.max(np.abs(segment))) if segment.size else 0.0
    if span <= 0:
        return np.array([], dtype=int)
    prominence = min_prominence_fraction * span
    peaks, _ = find_peaks(segment, prominence=prominence)
    troughs, _ = find_peaks(-segment, prominence=prominence)
    return np.sort(np.concatenate([peaks, troughs]).astype(int))


def _regular_run(extrema: np.ndarray, tolerance: float) -> np.ndarray:
    """The leading run of evenly spaced extrema, which is what ringing looks like.

    Everything after it is measured on whatever is left in the window, and what
    is left once the resonance has decayed is noise. Taking every extremum in the
    window instead lets that noise into both the frequency, through irregular
    intervals, and the decay, through an envelope that flattens out at the noise
    floor and reports a time constant far too long. It is the difference between
    measuring the response and measuring how long the window was.

    The reference spacing is the running median of the intervals accepted so far,
    so one odd interval near the start does not set the standard for the rest.
    """
    if extrema.size < 3:
        return extrema
    intervals = np.diff(extrema).astype(float)
    seed = float(np.median(intervals[: min(5, intervals.size)]))
    if seed <= 0:
        return extrema[:1]

    kept = [int(extrema[0])]
    accepted: list[float] = []
    for index, gap in zip(extrema[1:], intervals, strict=True):
        reference = float(np.median(accepted)) if accepted else seed
        if abs(gap - reference) > tolerance * reference:
            break
        kept.append(int(index))
        accepted.append(float(gap))
    return np.asarray(kept, dtype=int)


def _spectral_peak(segment: np.ndarray, sfreq_hz: float, low: float, high: float) -> float:
    """Dominant frequency inside the band, by FFT. Confirms the peak spacing.

    Given the span the resonance actually occupies, not the whole window: a
    spectrum of the window measures the ringing and whatever followed it, which
    is the noise the peak-spacing estimate was careful to exclude.

    Zero-padded before the transform. That adds no resolution, but for one
    dominant sinusoid it locates the peak between bins instead of on one, and a
    ten-cycle segment has bins tens of hertz wide.
    """
    if segment.size < 4:
        return float("nan")
    windowed = segment * np.hanning(segment.size)
    n_fft = max(1024, 4 * segment.size)
    spectrum = np.abs(np.fft.rfft(windowed, n=n_fft))
    freqs = np.fft.rfftfreq(n_fft, 1.0 / sfreq_hz)
    inside = (freqs >= low) & (freqs <= high)
    if not inside.any():
        return float("nan")
    return float(freqs[inside][int(np.argmax(spectrum[inside]))])


def _decay_constant(
    times_s: np.ndarray, amplitudes: np.ndarray, min_r_squared: float
) -> tuple[float, float]:
    """Time constant in milliseconds and the fit's R-squared.

    A straight line through the log of successive extrema amplitudes
    (scipy.stats.linregress). Returns NaN for the constant when the fit is worse
    than asked for, or when the envelope grows rather than decays: a decay
    constant with no fit behind it is exactly the number that ends up in a
    figure.
    """
    from scipy.stats import linregress

    usable = amplitudes > 0
    if usable.sum() < 3:
        return float("nan"), float("nan")
    fit = linregress(times_s[usable], np.log(amplitudes[usable]))
    r_squared = float(fit.rvalue**2)
    if fit.slope >= 0 or r_squared < min_r_squared:
        return float("nan"), r_squared
    return float(-1000.0 / fit.slope), r_squared


def _measure(
    segment: np.ndarray, sfreq_hz: float, cfg: dict[str, Any]
) -> dict[str, Any] | None:
    """One derivation, one epoch. None when there is nothing measurable."""
    filtered = _bandpass(segment, sfreq_hz, cfg["bandpass_low_hz"], cfg["bandpass_high_hz"])
    found = _extrema(filtered, cfg["min_prominence_fraction"])
    extrema = _regular_run(found, cfg["max_interval_jitter"])
    if extrema.size < cfg["min_peaks"]:
        return None

    times = extrema / sfreq_hz
    values = filtered[extrema]

    # Amplitude: the first excursion, peak to the trough that follows it, or the
    # other way around when the ringing starts negative.
    first_to_second = float(abs(values[0] - values[1]))

    intervals = np.diff(times)
    # Successive extrema are half a cycle apart, so a full period is two of them.
    period_s = 2.0 * float(np.median(intervals)) if intervals.size else float("nan")
    freq_peaks = 1.0 / period_s if period_s > 0 else float("nan")
    resonance = filtered[: int(extrema[-1]) + 1]
    freq_fft = _spectral_peak(resonance, sfreq_hz, cfg["bandpass_low_hz"],
                              cfg["bandpass_high_hz"])
    disagreement = (
        abs(freq_peaks - freq_fft) / freq_peaks
        if np.isfinite(freq_peaks) and np.isfinite(freq_fft) and freq_peaks > 0
        else float("nan")
    )

    tau_ms, r_squared = (float("nan"), float("nan"))
    if cfg["fit_decay"]:
        tau_ms, r_squared = _decay_constant(times, np.abs(values), cfg["min_r_squared"])

    agrees = bool(
        np.isfinite(disagreement) and disagreement <= cfg["max_frequency_disagreement"]
    )
    return {
        "n_extrema": int(extrema.size),
        "amplitude": first_to_second,
        "freq_from_peaks_hz": freq_peaks,
        "freq_from_fft_hz": freq_fft,
        "freq_disagreement": disagreement,
        "frequencies_agree": agrees,
        "decay_tau_ms": tau_ms,
        "decay_r_squared": r_squared,
        "_filtered": filtered,
        "_extrema": extrema,
    }


# ---------------------------------------------------------------------------
# Guardrails
# ---------------------------------------------------------------------------

def guardrail_context(session: Any, params: ErnaParams) -> dict[str, Any]:
    cfg = settings(params, session.configs)
    sfreq = params.sfreq_target_hz or _native_sfreq(session, params)
    return {
        "reference_scheme": params.primary_reference,
        "reference_is_shared": True,
        "sfreq_hz": sfreq,
        "usable_bandwidth_hz": usable_bandwidth_hz(
            sfreq or 0.0, cutoff_fraction_from(session.configs)
        ),
        "requested_bands": {"erna": (cfg["bandpass_low_hz"], cfg["bandpass_high_hz"])},
        # The phenomenon is the response window itself, which is what makes this
        # recipe's window the right one by construction rather than by luck.
        "window_s": cfg["analysis_ms"] / 1000.0,
        "claimed_event_duration_s": cfg["analysis_ms"] / 1000.0,
        "conditions": (cfg["stim_condition"],) if cfg["stim_condition"] else (),
        "reports_db": False,
        "reports_z": False,
        "baseline_is_smoothed": False,
        # G2 asks whether a per-contact comparison subtracted a per-contact
        # baseline first, because otherwise the comparison measures which contact
        # sits best rather than what the brain is doing. Reported as None, "the
        # check cannot judge this", rather than False, and the reason is not that
        # it is inconvenient. An evoked response is measured inside each
        # derivation's own post-stimulus window against its own pre-stimulus
        # state; there is no cross-condition contrast for a baseline condition to
        # correct. And ranking contacts by response amplitude is not a confound
        # here, it is the measurement: which contact resonates is the question
        # ERNA is asked. If that reasoning is wrong, set this to False and every
        # ERNA run will require an explicit override with a reason.
        "per_contact_baseline_subtracted": None,
        **_shared_guardrail_context(session, params),
    }


def _native_sfreq(session: Any, params: ErnaParams) -> float | None:
    lead_ids = params.leads or list(session.leads())
    if not lead_ids:
        return None
    stream = session.leads()[lead_ids[0]].stream
    return float(session.recording.streams[stream].sfreq_hz)


# ---------------------------------------------------------------------------
# The recipe
# ---------------------------------------------------------------------------

@recipe(
    NAME,
    "Amplitude, frequency, and decay of evoked resonant neural activity after "
    "each stimulation event. Every setting that shapes the answer is a "
    "parameter, defaulting to configs/erna.yaml.",
    ErnaParams,
    version="1",
    question="After each stimulation pulse, how large is the ringing, what "
             "frequency does it resonate at, and how fast does it decay?",
    produces="One row per stimulation event and derivation with amplitude, "
             "frequency and decay, per-contact medians, and an example epoch figure.",
)
def erna(ctx: RecipeContext) -> RecipeResult:
    params: ErnaParams = ctx.params
    session = ctx.session
    cfg = settings(params, session.configs)
    resolved = resolve(params, session.configs)
    review = review_state(session.configs)

    if not review["reviewed"]:
        ctx.log(
            "configs/erna.yaml has defaults_reviewed: false. These settings are "
            "starting points, not this lab's protocol. Every output says so."
        )
    ctx.log(
        f"blanking {cfg['blanking_ms']} ms, analysing {cfg['analysis_ms']} ms, "
        f"band {cfg['bandpass_low_hz']}-{cfg['bandpass_high_hz']} Hz, "
        f"events from {cfg['stim_source']}"
    )

    lead_ids = params.leads or list(session.leads())
    schemes = params.references or [params.primary_reference]

    rows: list[dict[str, Any]] = []
    examples: dict[str, dict[str, Any]] = {}
    skipped = {"too_few_peaks": 0}
    event_counts: dict[str, int] = {}

    for lead_id in lead_ids:
        lead = session.leads()[lead_id]
        for scheme in schemes:
            signal = session.read_derived(
                lead_id, scheme, sfreq_target_hz=params.sfreq_target_hz
            )
            sfreq = signal.sfreq_hz
            onsets_s = _event_times(ctx, signal, cfg, sfreq)
            if onsets_s.size > params.max_events:
                ctx.log(f"{lead_id}/{scheme}: {onsets_s.size} events, keeping the "
                        f"first {params.max_events}")
                onsets_s = onsets_s[: params.max_events]
            event_counts[f"{lead_id}|{scheme}"] = int(onsets_s.size)
            if onsets_s.size == 0:
                continue

            start_offset = int(round(cfg["blanking_ms"] * sfreq / 1000.0))
            length = int(round(cfg["analysis_ms"] * sfreq / 1000.0))

            for event_index, onset_s in enumerate(onsets_s):
                i0 = int(round(onset_s * sfreq)) + start_offset
                i1 = i0 + length
                if i1 > signal.data.shape[1]:
                    continue
                for row_index, name in enumerate(signal.names):
                    measured = _measure(signal.data[row_index, i0:i1], sfreq, cfg)
                    if measured is None:
                        skipped["too_few_peaks"] += 1
                        continue
                    filtered = measured.pop("_filtered")
                    extrema = measured.pop("_extrema")
                    key = f"{lead_id}|{scheme}|{name}"
                    if key not in examples:
                        examples[key] = {
                            "lead_id": lead_id, "scheme": scheme, "derivation": name,
                            "onset_s": float(onset_s), "sfreq_hz": sfreq,
                            "filtered": filtered, "extrema": extrema,
                            "tau_ms": measured["decay_tau_ms"],
                        }
                    rows.append({
                        "study_id": session.study_id, "session": session.session,
                        "lead_id": lead_id, "target": lead.target, "scheme": scheme,
                        "derivation": name, "event": event_index,
                        "onset_s": round(float(onset_s), 4),
                        **measured,
                    })

    if not rows:
        raise RuntimeError(
            "no measurable ERNA epochs. Check stim_source and blanking_ms: with "
            f"{sum(event_counts.values())} event(s) found and "
            f"{skipped['too_few_peaks']} epoch(s) rejected for having fewer than "
            f"{cfg['min_peaks']} peaks, the usual causes are a detection firing on "
            "noise or an analysis window that starts after the response."
        )

    epochs = pd.DataFrame(rows)
    summary_table = _summarize(epochs)

    out = ctx.out_dir
    epochs.to_csv(out / "erna_epochs.csv", index=False)
    summary_table.to_csv(out / "erna_summary.csv", index=False)

    summary = {
        "recipe": NAME,
        "settings": {k: v["value"] for k, v in resolved.items()},
        "settings_sources": {k: v["source"] for k, v in resolved.items()},
        "settings_reviewed": review["reviewed"],
        "protocol_note": review["protocol_note"],
        "n_events": event_counts,
        "n_epochs_measured": int(len(epochs)),
        "n_epochs_rejected_too_few_peaks": skipped["too_few_peaks"],
        "n_epochs_frequencies_disagree": int((~epochs["frequencies_agree"]).sum()),
        "median_frequency_hz": _median(epochs, "freq_from_peaks_hz"),
        "median_amplitude": _median(epochs, "amplitude"),
        "median_decay_tau_ms": _median(epochs, "decay_tau_ms"),
        "caveat": (
            "Settings were not reviewed against a stimulation protocol. They are "
            "this software's starting points. Set defaults_reviewed in "
            "configs/erna.yaml once someone who knows the protocol has looked."
            if not review["reviewed"] else
            f"Settings reviewed by {review['reviewed_by'] or 'unnamed'} "
            f"on {review['reviewed_on'] or 'an unrecorded date'}."
        ),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    figures = _figures(ctx, examples, summary_table, cfg, review)

    return RecipeResult(
        tables={"erna_epochs": epochs, "erna_summary": summary_table},
        figures=figures,
        summary=summary,
    )


def _event_times(
    ctx: RecipeContext, signal: Any, cfg: dict[str, Any], sfreq_hz: float
) -> np.ndarray:
    """Stimulation event onsets in seconds, from whichever source was chosen."""
    source = cfg["stim_source"]
    if source == "windows":
        return _events_from_windows(ctx, cfg["stim_condition"])
    if source == "epochs":
        return _events_from_epochs(ctx, cfg["stim_epoch_store"])
    indices = _events_from_amplitude(
        signal.data, sfreq_hz, cfg["stim_threshold_mad"], cfg["stim_refractory_ms"]
    )
    return indices / sfreq_hz


def _median(frame: pd.DataFrame, column: str) -> float | None:
    values = frame[column].dropna()
    return round(float(values.median()), 4) if len(values) else None


def _summarize(epochs: pd.DataFrame) -> pd.DataFrame:
    """Per derivation medians. Medians because one bad epoch should not move it."""
    grouped = epochs.groupby(["lead_id", "target", "scheme", "derivation"], dropna=False)
    summary = grouped.agg(
        n_epochs=("amplitude", "size"),
        n_frequencies_agree=("frequencies_agree", "sum"),
        median_amplitude=("amplitude", "median"),
        median_freq_hz=("freq_from_peaks_hz", "median"),
        median_freq_fft_hz=("freq_from_fft_hz", "median"),
        median_decay_tau_ms=("decay_tau_ms", "median"),
        median_decay_r_squared=("decay_r_squared", "median"),
    ).reset_index()
    return summary.sort_values(["lead_id", "scheme", "derivation"]).reset_index(drop=True)


def _figures(
    ctx: RecipeContext, examples: dict[str, dict[str, Any]],
    summary: pd.DataFrame, cfg: dict[str, Any], review: dict[str, Any],
) -> list:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    keys = sorted(examples)[:8]
    n = len(keys)
    if n == 0:
        return []

    fig, axes = plt.subplots(n + 1, 1, figsize=(8, 1.6 * (n + 1) + 1.5), squeeze=False)
    for ax, key in zip(axes[:n, 0], keys, strict=False):
        example = examples[key]
        signal = example["filtered"]
        times_ms = np.arange(signal.size) / example["sfreq_hz"] * 1000.0
        ax.plot(times_ms, signal * 1e6, linewidth=0.8)
        ax.plot(times_ms[example["extrema"]], signal[example["extrema"]] * 1e6,
                "o", markersize=2.5)
        ax.set_ylabel(example["derivation"], fontsize=7)
        ax.tick_params(labelsize=6)
    axes[n - 1, 0].set_xlabel("ms after blanking ends", fontsize=7)

    ax = axes[n, 0]
    if len(summary):
        labels = [f"{r.derivation}" for r in summary.itertuples()]
        ax.bar(range(len(summary)), summary["median_freq_hz"].fillna(0.0))
        ax.set_xticks(range(len(summary)))
        ax.set_xticklabels(labels, rotation=90, fontsize=6)
        ax.set_ylabel("median freq (Hz)", fontsize=7)
        ax.tick_params(labelsize=6)

    caption = (
        f"run {ctx.run.run_id} | blanking {cfg['blanking_ms']} ms, "
        f"window {cfg['analysis_ms']} ms, band {cfg['bandpass_low_hz']}-"
        f"{cfg['bandpass_high_hz']} Hz, events from {cfg['stim_source']}"
    )
    if not review["reviewed"]:
        caption += "\nSETTINGS NOT REVIEWED against a stimulation protocol."
    elif review["protocol_note"]:
        caption += f"\n{review['protocol_note'][:180]}"
    fig.suptitle("ERNA: example epoch per derivation", fontsize=9)
    fig.text(0.01, 0.005, caption, fontsize=6, va="bottom")
    fig.tight_layout(rect=(0, 0.04, 1, 0.98))

    out = ctx.out_dir
    paths = [out / "erna_epochs.png", out / "erna_epochs.svg"]
    for path in paths:
        fig.savefig(path, dpi=150)
    plt.close(fig)
    return paths


# The registry looks this up on the recipe function, before anything is computed.
erna.guardrail_context = guardrail_context
