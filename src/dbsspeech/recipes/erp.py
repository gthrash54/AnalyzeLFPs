"""erp_epochs: event-locked averages from the markers a recording carries.

The first recipe here that is locked to events rather than to blocks. Every
other recipe contrasts condition windows, which is what the speech protocol
needed because it has no markers at all. BrainVision and EDF files bring their
own triggers, so an ERP becomes possible: cut a window around each marker onset,
correct each trial to its own pre-event baseline, and average.

Four choices that decide whether the average means anything:

Baseline before averaging, per trial
    Each trial is corrected to its own pre-event baseline and only then
    averaged. Averaging first and correcting the average afterwards removes a
    single common offset instead of the drift that differs trial to trial,
    which is a different quantity and a worse one.

The baseline must precede the event
    A baseline window overlapping the response subtracts part of the response
    from itself and shrinks the very effect being measured. A baseline that
    does not end at or before zero is refused rather than warned about.

Trials are counted, and too few is refused
    An ERP is an average, and an average over four trials is not one. The trial
    count travels into every row and the summary, and a derivation with fewer
    than `min_trials` produces no result rather than a noisy one that looks
    like the others.

Peak latency is reported only inside a stated window
    The largest deflection anywhere in an epoch is usually noise or the edge.
    Peak amplitude and latency are measured inside `peak_window_s`, which is a
    parameter, so the search range reaches the run record instead of being
    chosen after seeing the data.

Epoching, baseline correction and averaging are arithmetic on an array rather
than signal processing, so they are done with numpy here instead of building an
`mne.Epochs`. Constructing one would mean synthesizing an `mne.Info` for a
montage this package already derived, and a unit or scaling mistake in that
conversion would be invisible in the output.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator

from ..preprocess import available_schemes, cutoff_fraction_from, usable_bandwidth_hz
from ..stats import options_for_schema
from .psd import _shared_guardrail_context
from .registry import RecipeContext, RecipeResult, recipe

NAME = "erp_epochs"


class ErpParams(BaseModel):
    """Parameters for erp_epochs."""

    event_label: str | None = Field(
        default=None,
        description=(
            "Marker label to lock to, as the reader reports it. None lists the "
            "labels the recording carries and refuses, rather than picking one."
        ),
    )
    condition: str | None = Field(
        default=None,
        description=(
            "Restrict to events falling inside this condition's windows. None "
            "uses every event in the recording."
        ),
    )
    leads: list[str] | None = Field(default=None, description="None means every lead.")
    references: list[str] | None = Field(default=None)
    primary_reference: str = Field(default="bipolar_vertical")

    tmin_s: float = Field(
        default=-0.2, description="Epoch start relative to the event, usually negative."
    )
    tmax_s: float = Field(default=0.8, description="Epoch end relative to the event.")
    baseline_start_s: float = Field(default=-0.2)
    baseline_end_s: float = Field(
        default=0.0,
        description="Must be at or before 0: a baseline overlapping the response "
                    "subtracts the response from itself.",
    )
    peak_window_start_s: float = Field(default=0.0)
    peak_window_end_s: float = Field(
        default=0.5,
        description="Peak amplitude and latency are measured only inside this "
                    "window, so the search range is stated rather than chosen "
                    "after seeing the data.",
    )

    min_trials: int = Field(
        default=10, ge=1,
        description="Below this, no average is produced. An average over a "
                    "handful of trials is not an ERP.",
    )
    sfreq_target_hz: float = Field(default=1000.0, gt=0)

    @model_validator(mode="after")
    def _check_windows(self) -> ErpParams:
        if self.tmax_s <= self.tmin_s:
            raise ValueError("tmax_s must be after tmin_s")
        if self.baseline_end_s > 0:
            raise ValueError(
                "baseline_end_s must be at or before 0; a baseline overlapping "
                "the response subtracts part of the response from itself"
            )
        if self.baseline_end_s <= self.baseline_start_s:
            raise ValueError("baseline_end_s must be after baseline_start_s")
        if self.baseline_start_s < self.tmin_s:
            raise ValueError("the baseline starts before the epoch does")
        if self.peak_window_end_s <= self.peak_window_start_s:
            raise ValueError("peak_window_end_s must be after peak_window_start_s")
        if self.peak_window_end_s > self.tmax_s:
            raise ValueError("the peak window extends past the end of the epoch")
        return self


def available_events(session: Any) -> dict[str, int]:
    """Marker labels the recording carries, with their event counts."""
    return {label: len(series) for label, series in session.recording.epochs.items()}


def _recording_end_s(session: Any) -> float:
    durations = [info.duration_s for info in session.recording.streams.values()]
    return max(durations) if durations else 0.0


def _within_recording(onsets: np.ndarray, end_s: float, params: ErpParams) -> np.ndarray:
    """Onsets whose whole epoch fits inside the recording.

    Dropped here, before reading, rather than discovered afterwards. A truncated
    epoch is a different length from the rest, and the first trial read is what
    establishes the length every other trial is checked against, so one event
    near the start or the end would otherwise leave every full trial looking
    like the mismatched one.
    """
    return onsets[(onsets + params.tmin_s >= 0.0) & (onsets + params.tmax_s <= end_s)]


def _onsets(session: Any, params: ErpParams) -> np.ndarray:
    """Event onsets in seconds, optionally restricted to one condition."""
    epochs = session.recording.epochs
    series = epochs[params.event_label]
    onsets = np.asarray(series.onsets, dtype=float)
    if params.condition is None:
        return onsets
    spans = [
        (float(r["t_start_s"]), float(r["t_end_s"]))
        for r in session.windows(params.condition)
    ]
    if not spans:
        return np.empty(0)
    keep = np.zeros(onsets.shape, dtype=bool)
    for t0, t1 in spans:
        keep |= (onsets >= t0) & (onsets < t1)
    return onsets[keep]


def _epoch_matrix(
    session: Any, lead_id: str, scheme: str, onsets: np.ndarray, params: ErpParams
) -> tuple[np.ndarray, np.ndarray, tuple[str, ...], tuple[str, ...], float]:
    """Stack of epochs as (n_trials, n_derivations, n_times), plus the time axis."""
    trials: list[np.ndarray] = []
    names: tuple[str, ...] = ()
    rows: tuple[str, ...] = ()
    sfreq = 0.0
    n_times = 0

    for onset in onsets:
        sig = session.read_derived(
            lead_id, scheme,
            tmin=onset + params.tmin_s,
            tmax=onset + params.tmax_s,
            sfreq_target_hz=params.sfreq_target_hz,
        )
        if sig.data.size == 0:
            continue
        if not names:
            names, rows, sfreq = sig.names, sig.rows, sig.sfreq_hz
            n_times = sig.data.shape[1]
        # Reads at different offsets can differ by a sample from rounding. A
        # trial of the wrong length is dropped rather than padded, because
        # padding invents samples at exactly the latency being measured.
        if sig.data.shape[1] != n_times:
            continue
        trials.append(sig.data)

    if not trials:
        return np.empty((0, 0, 0)), np.empty(0), names, rows, sfreq

    stack = np.stack(trials)
    times = params.tmin_s + np.arange(n_times) / sfreq
    return stack, times, names, rows, sfreq


def _baseline_correct(
    stack: np.ndarray, times: np.ndarray, params: ErpParams
) -> np.ndarray:
    """Subtract each trial's own pre-event mean. Per trial, before averaging."""
    mask = (times >= params.baseline_start_s) & (times <= params.baseline_end_s)
    if not mask.any():
        raise RuntimeError(
            "the baseline window contains no samples; widen it or raise "
            "sfreq_target_hz"
        )
    baseline = stack[:, :, mask].mean(axis=2, keepdims=True)
    return stack - baseline


def guardrail_context(session: Any, params: ErpParams) -> dict[str, Any]:
    """What the guardrails can see before anything is computed.

    The same defect as `pac_modulation_index` had: this was assembled after the
    epochs were averaged and handed back on `RecipeResult`, which nothing reads,
    so the run was checked against two of thirteen guardrails and the other
    eleven reported nothing because they were shown nothing.

    An event-locked average has no band of its own, so `requested_range` is the
    honest one: everything up to the anti-alias cutoff, because an ERP is a
    broadband waveform and G6 should judge it on the rate it is computed at.
    """
    usable = usable_bandwidth_hz(
        params.sfreq_target_hz, cutoff_fraction_from(session.configs)
    )
    return {
        "reference_scheme": params.primary_reference,
        "reference_is_shared": True,
        "sfreq_hz": params.sfreq_target_hz,
        "usable_bandwidth_hz": usable,
        "requested_bands": {"requested_range": (0.0, usable)},
        # The shortest thing this can resolve is one epoch.
        "window_s": float(params.tmax_s - params.tmin_s),
        "conditions": (params.condition,) if params.condition else (),
        # An ERP is in the recording's own units, not decibels and not z.
        "reports_db": False,
        "reports_z": False,
        "baseline_is_smoothed": False,
        # Every trial is corrected to its own pre-event baseline before averaging.
        "per_contact_baseline_subtracted": True,
        **_shared_guardrail_context(session, params),
    }


@recipe(
    NAME,
    "Event-locked averages from a recording's own task markers, with per-trial "
    "baseline correction, trial counts on every row, and peak latency measured "
    "only inside a stated window.",
    ErpParams,
    version="1",
)
def erp_epochs(ctx: RecipeContext) -> RecipeResult:
    params: ErpParams = ctx.params
    session = ctx.session

    events = available_events(session)
    if not events:
        raise RuntimeError(
            "this recording carries no task markers, so there is nothing to lock "
            "to. Use a window-based recipe instead."
        )
    if params.event_label is None:
        raise RuntimeError(
            f"event_label is required. This recording carries: {events}"
        )
    if params.event_label not in events:
        raise RuntimeError(
            f"no marker {params.event_label!r} in this recording; it carries {events}"
        )

    found = _onsets(session, params)
    end_s = _recording_end_s(session)
    onsets = _within_recording(found, end_s, params)
    dropped = int(found.size - onsets.size)
    if dropped:
        ctx.log(
            f"{dropped} event(s) dropped: their epoch would extend past the "
            f"start or end of the {end_s:.1f}s recording"
        )
    if onsets.size < params.min_trials:
        raise RuntimeError(
            f"{onsets.size} event(s) for {params.event_label!r}"
            + (f" inside condition {params.condition!r}" if params.condition else "")
            + f", under min_trials={params.min_trials}. An average over this many "
            "trials is not an ERP."
        )

    lead_ids = params.leads or list(session.leads())
    schemes = params.references or list(available_schemes())

    rows: list[dict[str, Any]] = []
    waveforms: dict[tuple[str, str, str], np.ndarray] = {}
    time_axis: np.ndarray | None = None
    ctx.log(
        f"event={params.event_label!r} n_events={onsets.size} "
        f"condition={params.condition} epoch=[{params.tmin_s},{params.tmax_s}]s "
        f"baseline=[{params.baseline_start_s},{params.baseline_end_s}]s"
    )

    for lead_id in lead_ids:
        lead = session.leads()[lead_id]
        for scheme in schemes:
            stack, times, names, row_labels, sfreq = _epoch_matrix(
                session, lead_id, scheme, onsets, params
            )
            if stack.size == 0 or stack.shape[0] < params.min_trials:
                ctx.log(
                    f"{lead_id}/{scheme}: {stack.shape[0] if stack.size else 0} usable "
                    f"trial(s), under min_trials={params.min_trials}; skipped"
                )
                continue

            corrected = _baseline_correct(stack, times, params)
            evoked = corrected.mean(axis=0)
            # Standard error across trials, which is what an ERP figure needs to
            # be read honestly. Trials from one recording are not independent,
            # and the summary says so.
            sem = corrected.std(axis=0, ddof=1) / np.sqrt(corrected.shape[0])
            time_axis = times

            peak_mask = (
                (times >= params.peak_window_start_s)
                & (times <= params.peak_window_end_s)
            )
            for i, name in enumerate(names):
                waveforms[(lead_id, scheme, name)] = evoked[i]
                segment = evoked[i][peak_mask]
                segment_times = times[peak_mask]
                index = int(np.argmax(np.abs(segment)))
                rows.append({
                    "study_id": session.study_id,
                    "lead_id": lead_id,
                    "target": lead.target,
                    "scheme": scheme,
                    "derivation": name,
                    "row": row_labels[i],
                    "event_label": params.event_label,
                    "condition": params.condition or "",
                    "n_trials": int(corrected.shape[0]),
                    "peak_amplitude": float(segment[index]),
                    "peak_latency_s": float(segment_times[index]),
                    "peak_sem": float(sem[i][peak_mask][index]),
                    "baseline_rms": float(
                        np.sqrt(np.mean(evoked[i][
                            (times >= params.baseline_start_s)
                            & (times <= params.baseline_end_s)
                        ] ** 2))
                    ),
                })

    if not rows:
        raise RuntimeError(
            "no evoked average computed: every lead and scheme had fewer than "
            f"min_trials={params.min_trials} usable trials"
        )

    long = pd.DataFrame(rows)
    out = ctx.out_dir
    long.to_parquet(out / "erp_peaks.parquet", index=False)
    long.to_csv(out / "erp_peaks.csv", index=False)

    if time_axis is not None and waveforms:
        wide = pd.DataFrame({"time_s": time_axis})
        for (lead_id, scheme, name), trace in sorted(waveforms.items()):
            wide[f"{lead_id}|{scheme}|{name}"] = trace
        wide.to_parquet(out / "erp_waveforms.parquet", index=False)

    figures = _figures(ctx, waveforms, time_axis, params)

    summary = {
        "recipe": NAME,
        "event_label": params.event_label,
        "condition": params.condition,
        "n_events_found": int(found.size),
        "n_events_at_edges_dropped": dropped,
        "n_trials_used": int(long["n_trials"].max()),
        "epoch_s": [params.tmin_s, params.tmax_s],
        "baseline_s": [params.baseline_start_s, params.baseline_end_s],
        "peak_window_s": [params.peak_window_start_s, params.peak_window_end_s],
        "caveats": [
            "Trials come from one continuous recording and are not independent, "
            "so the standard error across trials understates the uncertainty of "
            "any claim about this subject.",
            "Peak amplitude and latency are measured only inside peak_window_s; "
            "a deflection outside it is not reported.",
            f"Each trial was corrected to its own baseline over "
            f"[{params.baseline_start_s}, {params.baseline_end_s}] s before averaging.",
        ],
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))

    return RecipeResult(
        tables={"erp_peaks": long},
        figures=figures,
        summary=summary,
    )


def _figures(
    ctx: RecipeContext,
    waveforms: dict[tuple[str, str, str], np.ndarray],
    times: np.ndarray | None,
    params: ErpParams,
) -> list:
    if times is None or not waveforms:
        return []
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    primary = {k: v for k, v in waveforms.items() if k[1] == params.primary_reference}
    if not primary:
        return []
    leads = sorted({k[0] for k in primary})

    fig, axes = plt.subplots(
        len(leads), 1, figsize=(6.0, 2.6 * len(leads)), squeeze=False, sharex=True
    )
    for r, lead_id in enumerate(leads):
        ax = axes[r][0]
        for (lid, _, name), trace in sorted(primary.items()):
            if lid != lead_id:
                continue
            ax.plot(times, trace, linewidth=0.9, label=name)
        ax.axvline(0, color="black", linewidth=0.8)
        ax.axhline(0, color="black", linewidth=0.5)
        # The baseline span, drawn so a reader can see it precedes the event
        # rather than taking the caption's word for it.
        ax.axvspan(params.baseline_start_s, params.baseline_end_s,
                   color="0.85", zorder=0)
        ax.set_ylabel(f"{lead_id}\namplitude", fontsize=8)
        ax.legend(fontsize=6, ncol=2, frameon=False)
    axes[-1][0].set_xlabel("Time from event (s)", fontsize=8)

    fig.suptitle(
        f"{NAME} · {params.event_label} · baseline shaded · run {ctx.run.run_id}",
        fontsize=8,
    )
    fig.tight_layout()
    paths = []
    for ext in ("png", "svg"):
        path = ctx.out_dir / f"erp_epochs.{ext}"
        fig.savefig(path, dpi=150)
        paths.append(path)
    plt.close(fig)
    return paths


erp_epochs.guardrail_context = guardrail_context
erp_epochs.option_explanations = options_for_schema
