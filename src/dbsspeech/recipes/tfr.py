"""tfr_onset: time-frequency around the onset of each condition.

Spectral contrasts average over a whole window. Speech has dynamics: onset,
sustained production, offset. This is the recipe that shows them, and it is the
groundwork for the word-level resolution the PI asked for.

What "onset" means here, stated because it is not the usual thing. There are no
task markers in these recordings, so onset is the start of a condition window as
recorded in `manifest/windows.csv`, and a window's provenance travels with the
result. A window derived from a microphone envelope is a real onset; one marked
`assumed` is not, and guardrail G10 says so.

Two failure modes this avoids by construction:

Edge artifacts
    A wavelet needs signal either side of the time it reports. The read is padded
    by the longest wavelet's half-length and cropped afterwards, so no reported
    time-frequency point was computed from data that was not there.

Memory
    A full-resolution TFR of every channel at once is large. Channels are
    processed one at a time and averaged as they go, so peak memory is one
    channel's map rather than the whole array.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator

from ..preprocess import cutoff_fraction_from, usable_bandwidth_hz
from ..stats import options_for_schema
from .psd import ClaimedEventDuration, _shared_guardrail_context, _windows_for
from .registry import RecipeContext, RecipeResult, recipe

NAME = "tfr_onset"

# A figure with one panel per window stops being readable long before the data
# stops being useful. Past this, the figure is a sample and the files are the
# result; the log says so when it happens.
MAX_FIGURE_COLUMNS = 8


class TfrParams(BaseModel):
    """Parameters for tfr_onset."""

    # The words a person reads while deciding, and the handful they actually have
    # to decide. Without these the form showed fourteen fields at once, titled
    # from the field names: "Sfreq Target Hz", "N Cycles Factor", "Fmin". Every
    # one of them has a defensible default, so showing all fourteen asked a
    # student to review thirteen decisions that were already made for them.
    LABELS: ClassVar[dict[str, str]] = {
        "leads": "Leads to include",
        "conditions": "Conditions to map",
        "references": "Montages to compute",
        "primary_reference": "Montage the result is reported in",
        "tmin": "Start of the map, relative to onset (seconds)",
        "tmax": "End of the map, relative to onset (seconds)",
        "fmin": "Lowest frequency (Hz)",
        "fmax": "Highest frequency (Hz)",
        "n_freqs": "How many frequencies",
        "n_cycles_factor": "Time against frequency resolution",
        "method": "Time-frequency estimator",
        "sfreq_target_hz": "Analyze at this sampling rate (Hz)",
        "decim": "Keep every nth output sample",
        "baseline_mode": "How each frequency is normalized",
        "baseline_tmin": "Start of the baseline (seconds)",
        "baseline_tmax": "End of the baseline (seconds)",
    }
    ESSENTIAL: ClassVar[tuple[str, ...]] = (
        "conditions", "tmin", "tmax", "fmin", "fmax", "primary_reference",
    )
    claimed_event_duration_s: ClaimedEventDuration = None

    leads: list[str] | None = Field(default=None)
    conditions: list[str] | None = Field(default=None)
    references: list[str] | None = Field(
        default=None,
        description="None means the primary reference only. TFR is expensive; "
                    "computing five montages multiplies the cost.",
    )
    primary_reference: str = Field(default="bipolar_vertical")

    tmin: float = Field(default=-2.0, description="Seconds relative to window onset.")
    tmax: float = Field(default=8.0, description="Seconds relative to window onset.")
    fmin: float = Field(default=2.0, gt=0)
    fmax: float = Field(default=150.0, gt=0)
    n_freqs: int = Field(default=40, ge=4, description="Log-spaced between fmin and fmax.")
    min_cycles: float = Field(
        default=3.0, ge=1.0,
        description=(
            "Floor on the number of cycles per wavelet. Below about three the "
            "Morlet is a broadband envelope detector rather than a frequency "
            "estimate, so the frequency axis stops meaning what it says."
        ),
    )
    n_cycles_factor: float = Field(
        default=0.5,
        description="n_cycles = freq * this. Higher means better frequency "
                    "resolution and worse time resolution.",
    )
    method: Literal["morlet", "multitaper"] = Field(default="morlet")
    sfreq_target_hz: float = Field(
        default=1000.0, gt=0,
        description="TFR is expensive; a lower rate is usually right. Guardrail G6 "
                    "still refuses any band above the anti-alias cutoff.",
    )
    decim: int = Field(default=4, ge=1, description="Temporal decimation of the output.")
    baseline_mode: Literal["logratio", "percent", "zscore", "none"] = Field(
        default="logratio",
        description="How each frequency is normalized against the pre-onset baseline.",
    )
    baseline_tmin: float = Field(default=-2.0)
    baseline_tmax: float = Field(default=-0.25)

    @model_validator(mode="after")
    def _baseline_must_lie_inside_the_map(self) -> TfrParams:
        """A baseline outside the epoch selects nothing, and selecting nothing
        used to return raw power that was then labelled dB.

        Checked here rather than mid-run so it costs a validation error rather
        than a wasted convolution over every channel, and so the Check step in
        the interface shows it before the run is submitted.
        """
        if self.baseline_mode == "none":
            return self
        if self.baseline_tmax <= self.baseline_tmin:
            raise ValueError(
                f"baseline_tmax ({self.baseline_tmax}) must be after "
                f"baseline_tmin ({self.baseline_tmin})"
            )
        if self.baseline_tmin >= self.tmax or self.baseline_tmax <= self.tmin:
            raise ValueError(
                f"the baseline window [{self.baseline_tmin}, {self.baseline_tmax}] "
                f"lies outside the epoch [{self.tmin}, {self.tmax}], so it would "
                f"select no samples. With baseline_mode={self.baseline_mode!r} the "
                "result is expressed relative to that baseline, and there would be "
                "nothing to express it against."
            )
        return self


def _frequencies(params: TfrParams) -> np.ndarray:
    return np.logspace(np.log10(params.fmin), np.log10(params.fmax), params.n_freqs)


def _n_cycles(params: TfrParams, freqs: np.ndarray) -> np.ndarray:
    """Cycles per wavelet at each frequency, floored.

    `n_cycles_factor` alone gives a constant wavelet duration at every frequency,
    which is a deliberate constant-duration tiling and is what an onset analysis
    wants: the time resolution does not degrade as you go down the map. It breaks
    at the bottom. At the default factor of 0.5 the wavelet is 1.0 cycle at 2 Hz,
    and a one-cycle Morlet has a bandwidth so wide it is an envelope detector.
    The map advertised delta and theta and measured something else there.

    The floor makes the low end real rather than nominal, at the cost of time
    resolution below roughly 5.4 Hz on the default grid: 1.5 s of smearing at
    2 Hz rather than 0.5 s. That cost is not a choice. A 2 Hz event cannot be
    localised to better than about half a cycle whatever we do, and the previous
    setting did not escape it either; it simply did not say so.

    This is a speech project, and delta and theta are where the speech envelope
    and syllable rate live, so raising `fmin` out of the broken region was the
    wrong way to fix it.
    """
    return np.maximum(freqs * params.n_cycles_factor, params.min_cycles)


# MNE builds a Morlet kernel out to five standard deviations either side of its
# centre, not out to one nominal cycle. Measured against the installed MNE:
# morlet(1000.0, [2.0], n_cycles=1.0) returns 795 samples, and 795 / 1000 divided
# by sigma_t = 1 / (2 * pi * 2) is 9.99, so the kernel spans +/- 5 sigma_t.
MORLET_SIGMAS = 5.0


def _pad_seconds(
    freqs: np.ndarray, n_cycles: np.ndarray, sfreq_hz: float | None = None
) -> float:
    """How much real signal each edge of the read needs, in seconds.

    Five standard deviations of the widest Gaussian envelope on the frequency
    grid, because that is the extent of the kernel MNE actually convolves.

    This used to be half the nominal wavelet duration, `max(n_cycles / freqs) /
    2`, which is 0.25 s at the defaults against a 0.3975 s kernel half-support:
    37 percent short at every frequency, not only at the low edge. The module
    docstring's guarantee that no reported point was computed from data that was
    not there did not hold, and `test_no_reported_point_sits_on_an_edge` did not
    catch it because it asserted that the reported time range lay inside the
    requested bounds, which is a different claim from the one its name makes.

    sigma_t = n_cycles / (2 * pi * f), so this is 5 * n_cycles / (2 * pi * f),
    maximised over the grid.
    """
    sigma_t = n_cycles / (2.0 * np.pi * freqs)
    pad = float(np.max(MORLET_SIGMAS * sigma_t))
    if sfreq_hz:
        # MNE rounds the kernel to a whole number of samples, and rounding can
        # go up, so the analytic five sigma can be short by a fraction of one
        # sample. Round the pad up to the next whole sample at the rate the
        # analysis runs at, which covers that exactly rather than approximately.
        pad = float(np.ceil(pad * sfreq_hz) / sfreq_hz)
    return pad


def _apply_baseline(
    power: np.ndarray, times: np.ndarray, params: TfrParams
) -> np.ndarray:
    """Normalize each frequency against the pre-onset baseline.

    Baseline statistics come from the unsmoothed power, which guardrail G12
    requires: smoothing first narrows the baseline and inflates every z.
    """
    if params.baseline_mode == "none":
        return power
    mask = (times >= params.baseline_tmin) & (times <= params.baseline_tmax)
    if not mask.any():
        # Returning `power` here was the bug. The caller stores the result and
        # labels it with the unit implied by baseline_mode, so unbaselined power
        # of order 1e-10 was written as decibels and drawn on a colour scale
        # shared with maps that really were decibels. The model validator above
        # is what normally prevents this; this is the backstop, and it is loud.
        raise RuntimeError(
            f"the baseline window [{params.baseline_tmin}, {params.baseline_tmax}] "
            f"selected no samples from a map spanning [{times[0]:.3f}, "
            f"{times[-1]:.3f}]. Refusing to return unbaselined power labelled "
            f"{params.baseline_mode!r}."
        )
    base = power[:, mask]
    mean = base.mean(axis=1, keepdims=True)
    if params.baseline_mode == "percent":
        return 100.0 * (power - mean) / np.maximum(mean, np.finfo(float).tiny)
    if params.baseline_mode == "zscore":
        sd = base.std(axis=1, ddof=1, keepdims=True)
        return (power - mean) / np.where(sd > 0, sd, np.nan)
    return 10.0 * np.log10(
        np.maximum(power, np.finfo(float).tiny) / np.maximum(mean, np.finfo(float).tiny)
    )


def _tfr_one_channel(
    signal: np.ndarray, sfreq: float, freqs: np.ndarray, n_cycles: np.ndarray,
    params: TfrParams,
) -> np.ndarray:
    """Time-frequency power for one channel. Shape (n_freqs, n_times)."""
    data = signal[np.newaxis, np.newaxis, :]
    if params.method == "multitaper":
        from mne.time_frequency import tfr_array_multitaper as _tfr

        power = _tfr(data, sfreq=sfreq, freqs=freqs, n_cycles=n_cycles,
                     output="power", decim=params.decim, verbose=False)
    else:
        from mne.time_frequency import tfr_array_morlet as _tfr

        power = _tfr(data, sfreq=sfreq, freqs=freqs, n_cycles=n_cycles,
                     output="power", decim=params.decim, verbose=False)
    return np.asarray(power)[0, 0]


def guardrail_context(session: Any, params: TfrParams) -> dict[str, Any]:
    conditions = tuple(params.conditions or session.conditions())
    configured = (session.configs.get("bands") or {}).get("bands") or {}
    bands = {
        name: (float(lo), float(hi))
        for name, (lo, hi) in configured.items()
        if hi <= params.fmax
    }
    bands["requested_range"] = (params.fmin, params.fmax)
    freqs = _frequencies(params)
    n_cycles = _n_cycles(params, freqs)
    # The shortest event this analysis can resolve is the shortest wavelet.
    shortest = float(np.min(n_cycles / freqs))
    return {
        "reference_scheme": params.primary_reference,
        "reference_is_shared": True,
        "sfreq_hz": params.sfreq_target_hz,
        # The anti-alias cutoff comes from configs/guardrails.yaml now. It was
        # hard-coded here as 0.4, which is 0.8 of Nyquist written as a
        # fraction of the sampling rate, duplicating
        # preprocess.DEFAULT_CUTOFF_FRACTION and ignoring the config key
        # that claimed to control it.
        "usable_bandwidth_hz": usable_bandwidth_hz(
            params.sfreq_target_hz, cutoff_fraction_from(session.configs)
        ),
        "requested_bands": bands,
        "window_s": shortest,
        "conditions": conditions,
        "reports_db": params.baseline_mode == "logratio",
        "reports_z": params.baseline_mode == "zscore",
        "baseline_is_smoothed": False,
        "per_contact_baseline_subtracted": True,
        **_shared_guardrail_context(session, params),
    }


@recipe(
    NAME,
    "Time-frequency power around the onset of each condition window, baselined "
    "against the pre-onset period, averaged within region.",
    TfrParams,
    version="1",
    question="How does power change over time around the start of a condition, "
             "rather than averaged over the whole window?",
    produces="A time-frequency map per lead and per condition window, baselined "
             "to its own pre-onset period, plus the provenance of every onset it "
             "used. Repeat windows are kept separate rather than averaged.",
)
def tfr_onset(ctx: RecipeContext) -> RecipeResult:
    params: TfrParams = ctx.params
    session = ctx.session

    lead_ids = params.leads or list(session.leads())
    conditions = params.conditions or list(session.conditions())
    schemes = params.references or [params.primary_reference]
    freqs = _frequencies(params)
    n_cycles = _n_cycles(params, freqs)
    pad = _pad_seconds(freqs, n_cycles, params.sfreq_target_hz)
    ctx.log(f"padding each read by {pad:.2f} s so no reported point sits on an edge")

    # Keyed by window, not just by condition. Without the onset in the key a
    # second window for the same condition overwrote the first, while
    # `provenance` went on recording both, so window_provenance.csv claimed N
    # windows had contributed to a map that came from one of them and nothing in
    # the output could contradict it. Latent only while every condition had
    # exactly one window, which is not the shape of a repeated-trial paradigm.
    #
    # Repeats are kept separate rather than averaged. Averaging is the obvious
    # move and it is a choice about the science: the mean of per-trial decibels
    # and the decibels of the mean are different numbers, and which one a reader
    # wants depends on the question. The recipe emits one map per window and
    # leaves that to whoever reads it.
    maps: dict[tuple[str, str, str, str, float], np.ndarray] = {}
    times_out: np.ndarray | None = None
    provenance: list[dict[str, Any]] = []

    for lead_id in lead_ids:
        lead = session.leads()[lead_id]
        for scheme in schemes:
            for condition in conditions:
                for t0, _t1, window in _windows_for(ctx, condition):
                    # A window too close to the start of the recording cannot
                    # supply the pre-onset period that was asked for. Skipped
                    # rather than shortened: a map covering a different time
                    # range than the others is not comparable to them, and
                    # averaging it in silently makes the baseline mean one thing
                    # for some conditions and another for the rest.
                    # The pad is part of what has to exist. Without it in this
                    # check, `read_from` clamps silently at zero and the earliest
                    # reported point is computed from a truncated kernel, which
                    # is the guarantee failing quietly rather than loudly.
                    if t0 + params.tmin - pad < 0:
                        ctx.log(
                            f"{lead_id}/{scheme}/{condition}: onset at {t0:.2f}s is "
                            f"less than {abs(params.tmin) + pad:.2f}s from the start "
                            "of the recording, so the requested pre-onset period plus "
                            "the wavelet padding does not exist. Skipped."
                        )
                        continue
                    read_from = t0 + params.tmin - pad
                    read_to = t0 + params.tmax + pad
                    sig = session.read_derived(
                        lead_id, scheme, tmin=read_from, tmax=read_to,
                        sfreq_target_hz=params.sfreq_target_hz,
                    )
                    if sig.data.shape[1] < 32:
                        continue
                    # The same problem at the other end: a read truncated by the
                    # end of the recording gives a shorter map, and maps of
                    # different lengths cannot be stacked or compared.
                    expected = (read_to - read_from) * sig.sfreq_hz
                    if sig.data.shape[1] < expected * 0.999:
                        ctx.log(
                            f"{lead_id}/{scheme}/{condition}: onset at {t0:.2f}s runs "
                            f"past the end of the recording for the requested "
                            f"{params.tmax:.2f}s after onset. Skipped."
                        )
                        continue

                    # One channel at a time: peak memory is one map, not the array.
                    accumulated: np.ndarray | None = None
                    for i in range(sig.data.shape[0]):
                        power = _tfr_one_channel(sig.data[i], sig.sfreq_hz, freqs,
                                                 n_cycles, params)
                        accumulated = power if accumulated is None else accumulated + power
                    assert accumulated is not None
                    accumulated /= sig.data.shape[0]

                    n_times = accumulated.shape[1]
                    times = (
                        read_from + np.arange(n_times) * params.decim / sig.sfreq_hz - t0
                    )
                    # Crop the padding away. Every remaining point had signal on
                    # both sides when it was computed.
                    keep = (times >= params.tmin) & (times <= params.tmax)
                    accumulated, times = accumulated[:, keep], times[keep]

                    normalized = _apply_baseline(accumulated, times, params)
                    maps[(lead_id, lead.target, scheme, condition, t0)] = normalized
                    # Every surviving window spans exactly [tmin, tmax]: the two
                    # skips above drop anything the recording cannot supply, so
                    # the time vectors are identical by construction. Asserted
                    # rather than assumed, because the failure is a wrong axis on
                    # a map rather than an exception.
                    if times_out is not None and (
                        times_out.shape != times.shape
                        or not np.allclose(times_out, times)
                    ):
                        raise RuntimeError(
                            "windows produced different time axes; this should be "
                            "impossible after the start and end skips above"
                        )
                    times_out = times
                    provenance.append({
                        "lead_id": lead_id, "condition": condition, "scheme": scheme,
                        "onset_s": t0,
                        "derived_from": window.get("derived_from", ""),
                        "window_status": window.get("status", ""),
                    })
                    ctx.log(
                        f"{lead_id}/{scheme}/{condition} onset {t0:.2f}s: "
                        f"{normalized.shape}"
                    )

    if not maps or times_out is None:
        raise RuntimeError("no time-frequency maps computed; check the manifest windows")

    out = ctx.out_dir
    long = _to_long(maps, freqs, times_out)
    long.to_parquet(out / "tfr_long.parquet", index=False)
    pd.DataFrame(provenance).to_csv(out / "window_provenance.csv", index=False)
    _write_netcdf(maps, freqs, times_out, out / "tfr.nc", params)

    summary = _summary(maps, freqs, times_out, provenance, params)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    figures = _figures(ctx, maps, freqs, times_out, params)

    return RecipeResult(tables={"tfr_long": long}, figures=figures, summary=summary)


def _to_long(maps, freqs: np.ndarray, times: np.ndarray) -> pd.DataFrame:
    """Tidy form, decimated in frequency so the file stays openable."""
    step = max(1, len(freqs) // 20)
    frames = []
    for (lead_id, target, scheme, condition, onset_s), power in maps.items():
        for fi in range(0, len(freqs), step):
            frames.append(pd.DataFrame({
                "lead_id": lead_id, "target": target, "scheme": scheme,
                "condition": condition, "onset_s": onset_s, "freq_hz": freqs[fi],
                "time_s": times, "value": power[fi],
            }))
    return pd.concat(frames, ignore_index=True)


def _write_netcdf(maps, freqs, times, path, params: TfrParams) -> None:
    """Full-resolution maps as a labelled array, readable from MATLAB too."""
    import xarray as xr

    keys = sorted(maps)
    array = xr.DataArray(
        np.stack([maps[k] for k in keys]),
        dims=("map", "freq", "time"),
        coords={
            "map": [
                f"{lead}|{target}|{scheme}|{cond}|{onset:.3f}s"
                for lead, target, scheme, cond, onset in keys
            ],
            "freq": freqs,
            "time": times,
        },
        attrs={"baseline_mode": params.baseline_mode, "method": params.method,
               "units": {"logratio": "dB", "percent": "%", "zscore": "z",
                         "none": "power"}[params.baseline_mode]},
    )
    try:
        array.to_netcdf(path)
    except (ValueError, ImportError) as exc:  # no netCDF backend installed
        array.to_dataset(name="power").to_dataframe().reset_index().to_parquet(
            path.with_suffix(".parquet")
        )
        path.with_suffix(".txt").write_text(
            f"netCDF unavailable ({exc}); wrote {path.stem}.parquet instead\n"
        )


def _summary(maps, freqs, times, provenance, params: TfrParams) -> dict[str, Any]:
    peaks = []
    for (_lead_id, target, scheme, condition, onset_s), power in sorted(maps.items()):
        if scheme != params.primary_reference:
            continue
        finite = np.nan_to_num(power, nan=-np.inf)
        fi, ti = np.unravel_index(int(np.argmax(finite)), finite.shape)
        peaks.append({
            "target": target, "condition": condition,
            "onset_s": round(float(onset_s), 3),
            "peak_freq_hz": round(float(freqs[fi]), 2),
            "peak_time_s": round(float(times[ti]), 3),
            "peak_value": round(float(power[fi, ti]), 3),
        })
    suspect = sorted({
        p["condition"] for p in provenance
        if p["derived_from"] == "assumed" or p["window_status"] == "under_revision"
    })
    return {
        "recipe": NAME,
        "method": params.method,
        "baseline_mode": params.baseline_mode,
        "n_maps": len(maps),
        # One map per window per lead per montage. Stated because a reader
        # counting conditions will otherwise expect fewer.
        "n_windows_per_condition": {
            cond: len({k[4] for k in maps if k[3] == cond})
            for cond in sorted({k[3] for k in maps})
        },
        "freq_range_hz": [round(float(freqs[0]), 2), round(float(freqs[-1]), 2)],
        "time_range_s": [round(float(times[0]), 3), round(float(times[-1]), 3)],
        # Time resolution per frequency, because it is no longer constant down
        # the map: below `min_cycles / n_cycles_factor` Hz the floor binds and
        # the wavelet lengthens. A reader looking at a smear near onset in the
        # bottom rows should be able to see that it is the wavelet, not the
        # brain, without recomputing anything.
        "time_resolution_s": {
            f"{float(f):.2f}": round(float(nc / f), 4)
            for f, nc in zip(freqs, _n_cycles(params, freqs), strict=True)
        },
        "shortest_resolvable_event_s": round(
            float(np.min(_n_cycles(params, freqs) / freqs)), 4
        ),
        "longest_resolvable_event_s": round(
            float(np.max(_n_cycles(params, freqs) / freqs)), 4
        ),
        "min_cycles_binds_below_hz": round(
            float(params.min_cycles / params.n_cycles_factor), 2
        ),
        "peaks": peaks,
        "windows_needing_care": suspect,
        "onset_note": (
            "Onset is the start of a condition window in manifest/windows.csv, "
            "not a task marker in the signal. Where a recording carries markers "
            "they can be turned into windows with `dbsspeech windows`, and the "
            "window then records task_marker as its provenance; where it does "
            "not, the window was decided by a person. Which of those applies to "
            "each onset here is in window_provenance.csv, and it is the "
            "difference between a measured onset and an asserted one."
        ),
    }


def _figures(ctx: RecipeContext, maps, freqs, times, params: TfrParams) -> list:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    primary = {k: v for k, v in maps.items() if k[2] == params.primary_reference}
    if not primary:
        return []
    targets = sorted({k[1] for k in primary})
    # One column per window, not per condition. The previous version took
    # `match[0]` when several maps shared a condition, which silently drew one
    # trial and labelled it with the condition's name.
    columns = sorted({(k[3], k[4]) for k in primary})
    if len(columns) > MAX_FIGURE_COLUMNS:
        ctx.log(
            f"{len(columns)} windows; the figure shows the first "
            f"{MAX_FIGURE_COLUMNS}. Every map is in tfr.nc and tfr_long.parquet."
        )
        columns = columns[:MAX_FIGURE_COLUMNS]

    fig, axes = plt.subplots(
        len(targets), len(columns),
        figsize=(3.4 * len(columns), 2.8 * len(targets)),
        squeeze=False, sharex=True, sharey=True,
    )
    stacked = np.concatenate([v[np.isfinite(v)].ravel() for v in primary.values()])
    limit = float(np.percentile(np.abs(stacked), 98)) if stacked.size else 1.0

    # More than one window per condition means the column title has to say which
    # one, or two panels carry the same label and different data.
    repeated = {
        cond for cond, _ in columns
        if len({o for c, o in columns if c == cond}) > 1
    }

    for r, target in enumerate(targets):
        for c, (condition, onset_s) in enumerate(columns):
            ax = axes[r][c]
            match = [
                v for k, v in primary.items()
                if k[1] == target and k[3] == condition and k[4] == onset_s
            ]
            if not match:
                ax.set_axis_off()
                continue
            ax.pcolormesh(times, freqs, match[0], cmap="RdBu_r",
                          vmin=-limit, vmax=limit, shading="auto")
            ax.set_yscale("log")
            ax.axvline(0, color="black", linewidth=0.8)
            if r == 0:
                ax.set_title(
                    f"{condition}\n{onset_s:.2f}s" if condition in repeated
                    else condition,
                    fontsize=9,
                )
            if c == 0:
                ax.set_ylabel(f"{target.upper()}\nHz", fontsize=8)
            if r == len(targets) - 1:
                ax.set_xlabel("Time from onset (s)", fontsize=8)

    units = {"logratio": "dB", "percent": "%", "zscore": "z", "none": "power"}
    fig.suptitle(
        f"{NAME} · {units[params.baseline_mode]} vs pre-onset baseline · "
        f"run {ctx.run.run_id}",
        fontsize=8,
    )
    fig.tight_layout()
    paths = []
    for ext in ("png", "svg"):
        path = ctx.out_dir / f"tfr_onset.{ext}"
        fig.savefig(path, dpi=150)
        paths.append(path)
    plt.close(fig)
    return paths


tfr_onset.guardrail_context = guardrail_context
tfr_onset.option_explanations = options_for_schema
