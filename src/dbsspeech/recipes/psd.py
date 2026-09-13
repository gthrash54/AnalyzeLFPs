"""psd_by_condition: power spectral density per derivation, per condition.

The first recipe. Every parameter below was decided deliberately; see
docs/decisions.md, entries dated 2026-09-03.

What it does, in order: read each condition's window, re-reference under every
requested montage, decimate, estimate the spectrum per time segment, and report
the mean in dB alongside a z against a chosen baseline. Tables keep every
derivation and add a per-row aggregate, because the dorsal-versus-ventral
distinction is where the existing directional finding lives.

Units, both always. dB alone lets dynamic range read as effect size, since bands
differ enormously in absolute power. z alone is hard to compare against a
literature that mostly reports dB. Guardrail G8 enforces the pairing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any, ClassVar, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator

from ..io import filenames_deidentified_for
from ..runs.record import repo_relpath
from ..preprocess import available_schemes, cutoff_fraction_from, usable_bandwidth_hz
from ..stats import CENTERS, SCALES, describe_choice, normalize, options_for_schema
from .registry import RecipeContext, RecipeResult, recipe

NAME = "psd_by_condition"


# One definition, reused by every recipe with an analysis window, so the recipes
# cannot drift on what they are asking the analyst to state.
ClaimedEventDuration = Annotated[
    float | None,
    Field(
        default=None,
        gt=0,
        description=(
            "Duration in seconds of the event this run is claiming, if it claims "
            "one: a burst, a response, a transient. Guardrail G5 compares it to "
            "the analysis window, because a window several times longer than the "
            "event integrates over many of them and cannot resolve one. Leave it "
            "unset when the run makes no claim about an event, and G5 stays "
            "quiet: a guardrail cannot judge a claim nobody made."
        ),
    ),
]


class PsdParams(BaseModel):
    """Parameters for psd_by_condition. Defaults are the decided ones."""

    # Labels a person reads, and the four decisions that are actually theirs.
    # Everything else has a defensible default and sits under Advanced. See
    # Recipe.schema, which folds these into the parameter schema the interface
    # builds its form from.
    LABELS: ClassVar[dict[str, str]] = {
        "leads": "Leads to include",
        "conditions": "Conditions to compare",
        "unit": "One value per condition, or many short epochs",
        "epoch_s": "Epoch length (seconds)",
        "epoch_overlap": "Epoch overlap (0 to 1)",
        "references": "Montages to compute",
        "primary_reference": "Montage the result is reported in",
        "sfreq_target_hz": "Analyze at this sampling rate (Hz)",
        "method": "Spectral estimator",
        "window_s": "Welch window length (seconds)",
        "fmin": "Lowest frequency (Hz)",
        "fmax": "Highest frequency (Hz)",
        "baseline_center": "What z is measured from",
        "baseline_scale": "What z is measured in",
        "baseline_condition": "Baseline condition",
    }
    ESSENTIAL: ClassVar[tuple[str, ...]] = (
        "conditions", "fmin", "fmax", "primary_reference",
    )

    leads: list[str] | None = Field(
        default=None, description="Lead ids to run. None means every lead in the manifest."
    )
    conditions: list[str] | None = Field(
        default=None, description="Conditions to run. None means every window in the manifest."
    )
    unit: Literal["window", "pseudo_epoch"] = Field(
        default="window",
        description=(
            "window: one row per condition, covering the whole window. Its db_sd "
            "is the spread across the spectral segments inside that window, not "
            "an n=1 quantity, so read it as local variability rather than as a "
            "trial-level error. pseudo_epoch: fixed epochs give one row each; "
            "db_sd is still the within-epoch segment spread, and the epochs are "
            "not independent of one another."
        ),
    )
    epoch_s: float = Field(default=2.0, gt=0, description="Pseudo-epoch length, seconds.")
    epoch_overlap: float = Field(
        default=0.5, ge=0, lt=1, description="Pseudo-epoch overlap fraction."
    )
    references: list[str] | None = Field(
        default=None, description="Montages to compute. None means all of them."
    )
    primary_reference: str = Field(
        default="bipolar_vertical",
        description="Montage used for the headline figure.",
    )
    sfreq_target_hz: float = Field(
        default=8138.0, gt=0, description="Decimate toward this rate. Usable bandwidth is 0.4x it."
    )
    claimed_event_duration_s: ClaimedEventDuration = None
    band_of_interest: str = Field(
        default="beta",
        description=(
            "Band from configs/bands.yaml that this run is about. It selects the "
            "headline peak in the summary and supplies guardrail G9's excursion "
            "and effect. One band for both, because the effect G9 weighs against "
            "the baseline should be the effect the run reports."
        ),
    )
    method: Literal["welch", "multitaper"] = Field(default="welch")
    window_s: float = Field(default=1.0, gt=0, description="Spectral window, seconds.")
    fmin: float = Field(default=1.0, ge=0)
    fmax: float = Field(default=200.0, gt=0)
    # Centre and scale are chosen separately because they answer different
    # questions: the centre decides what a result is compared against, the scale
    # decides what counts as a large difference. Every option's meaning, when to
    # use it, and its caveat live in configs/statistics.yaml and travel into the
    # schema, the run record, and the figure caption.
    baseline_center: Literal[CENTERS] = Field(  # type: ignore[valid-type]
        default="grand_mean",
        description="What each condition is compared against. See configs/statistics.yaml.",
    )
    baseline_scale: Literal[SCALES] = Field(  # type: ignore[valid-type]
        default="pooled_within_condition",
        description="What counts as a large difference. See configs/statistics.yaml.",
    )
    baseline_condition: str = Field(
        default="rest",
        description="Which condition acts as the baseline, when centre or scale is 'condition'.",
    )


    @model_validator(mode="after")
    def _an_epoch_must_hold_a_spectral_window(self):
        """A window_s spectrum cannot be computed inside a shorter epoch.

        The old code resolved this silently, with `nperseg = min(nperseg,
        data.shape[1])`: the epoch got a smaller nperseg and therefore a coarser
        frequency grid than the one asked for, and where epochs of different
        lengths mixed in one run those rows went into the same long table on
        different grids. Grouping on freq_hz then neither fails nor warns, and
        the grids partially overlap, so a grand mean is taken over a mixture of
        two resolutions rather than obviously splitting.

        Refused rather than clamped, because clamping is what made it invisible.
        Set window_s to at most epoch_s, or lengthen the epoch.
        """
        if self.unit == "pseudo_epoch" and self.epoch_s < self.window_s:
            raise ValueError(
                f"epoch_s ({self.epoch_s}s) is shorter than window_s "
                f"({self.window_s}s), so each pseudo-epoch is too short to hold "
                "the spectral window it is asked for. Frequency resolution is "
                "1 / window_s, and an epoch cannot supply more resolution than "
                "its own length. Lower window_s to at most epoch_s, or raise "
                "epoch_s."
            )
        return self


@dataclass
class _Spectra:
    """Per-segment spectra for one derivation set under one condition."""

    freqs: np.ndarray          # (n_freqs,)
    segments: np.ndarray       # (n_derivations, n_segments, n_freqs), power
    names: tuple[str, ...]
    rows: tuple[str, ...]


def requested_nperseg(sfreq: float, params: Any) -> int:
    """Samples per spectral segment, from `window_s` and the rate.

    One place, because two recipes and the checks that skip short stretches all
    have to agree on it. A disagreement here is what produced a long table
    holding two different frequency grids.
    """
    return max(16, int(round(params.window_s * sfreq)))


def _segment_spectra(
    data: np.ndarray, sfreq: float, params: PsdParams
) -> tuple[np.ndarray, np.ndarray]:
    """Return (freqs, power) with power shaped (n_channels, n_segments, n_freqs)."""
    nperseg = requested_nperseg(sfreq, params)
    if data.shape[1] < nperseg:
        # This used to clamp: `nperseg = min(nperseg, data.shape[1])`. A shorter
        # stretch then got a smaller nperseg and therefore its own frequency
        # grid, and those rows went into the same long table as everything else.
        # Grouping on freq_hz afterwards does not fail and does not warn; the
        # grids partially overlap, so a grand mean is taken over a silent mixture
        # of two resolutions. Measured on a 1 s request: a 0.6 s stretch shares
        # 101 of its 301 bins with the 501 of a full-length one, so it is neither
        # comparable nor obviously separate.
        raise ValueError(
            f"{data.shape[1]} samples is shorter than the {nperseg} that "
            f"window_s={params.window_s} asks for at {sfreq:g} Hz. A shorter "
            "stretch would get its own frequency grid. Callers skip these."
        )

    if params.method == "multitaper":
        from mne.time_frequency import psd_array_multitaper

        # Multitaper gives one estimate per segment window, so segment first.
        #
        # Half a segment, matching the welch branch. These two used to disagree:
        # welch overlapped by 50 percent and multitaper not at all, so the same
        # recording gave the two methods different segment counts, and db_sd, and
        # therefore z, was not comparable between them.
        #
        # Overlap is close to free here rather than a way of inventing data. A
        # Hann taper heavily downweights the segment edges, which is exactly
        # where 50 percent overlapping segments share samples: measured lag-1
        # correlation between neighbouring segment estimates is +0.014, so the
        # effective sample size is about 97 percent of the segment count. It is
        # also why Welch specified 50 percent in the first place.
        step = max(1, nperseg // 2)
        starts = range(0, data.shape[1] - nperseg + 1, step)
        blocks = [data[:, s : s + nperseg] for s in starts] or [data]
        out = []
        for block in blocks:
            psd, freqs = psd_array_multitaper(
                block, sfreq, fmin=params.fmin, fmax=params.fmax,
                adaptive=False, normalization="full", verbose=False,
            )
            out.append(psd)
        return freqs, np.stack(out, axis=1)

    from scipy.signal import spectrogram

    # `window="hann"` is not the default and has to be said. scipy.signal
    # spectrogram defaults to ("tukey_periodic", 0.25) while scipy.signal.welch
    # defaults to Hann, so the branch named "welch" was computing something else:
    # measured on the installed scipy, a median 11.9 percent difference from
    # scipy.signal.welch on the same data, up to 75 percent in a single bin. With
    # Hann passed explicitly the two agree to 2.4e-15, so a reader reproducing a
    # number in scipy or in MATLAB's pwelch gets the number we published.
    #
    # spectrogram rather than welch because welch averages the segments away and
    # db_sd is the spread across them.
    freqs, _, sxx = spectrogram(
        data, fs=sfreq, nperseg=nperseg, noverlap=nperseg // 2,
        window="hann", scaling="density", mode="psd", axis=-1,
    )
    keep = (freqs >= params.fmin) & (freqs <= params.fmax)
    # spectrogram returns (channels, freqs, times); move to (channels, times, freqs)
    return freqs[keep], np.moveaxis(sxx[:, keep, :], -1, 1)


def _to_db(power: np.ndarray) -> np.ndarray:
    """Power to decibels, guarding the log against zeros."""
    return 10.0 * np.log10(np.maximum(power, np.finfo(float).tiny))


def _windows_for(ctx: RecipeContext, condition: str) -> list[tuple[float, float, dict]]:
    return [
        (float(r["t_start_s"]), float(r["t_end_s"]), r)
        for r in ctx.session.windows(condition)
    ]


def _epoch_bounds(t0: float, t1: float, params: PsdParams) -> list[tuple[float, float]]:
    if params.unit == "window":
        return [(t0, t1)]
    step = params.epoch_s * (1.0 - params.epoch_overlap)
    out, t = [], t0
    while t + params.epoch_s <= t1:
        out.append((t, t + params.epoch_s))
        t += step
    return out or [(t0, t1)]



def _paths_a_run_would_write(session: Any, privacy: dict[str, Any]) -> tuple[str, ...]:
    """Locations this run would record, for guardrail G13.

    One entry per input whose path `Run.add_input` would actually store: inside
    the repository, and permitted by `configs/privacy.yaml` for that format.
    Anything outside the repository has no portable location to record, and
    anything whose format is not declared de-identified has its location
    withheld, so neither reaches an output and neither belongs here.

    Kept beside the guardrail context rather than inside `add_input` so the
    check can be evaluated before the run opens, which is the only point at
    which refusing still un-computes something.
    """
    if not filenames_deidentified_for(privacy, session.recording.format):
        return ()
    recorded = repo_relpath(session.recording.path)
    return (recorded,) if recorded else ()


def _shared_guardrail_context(session: Any, params: Any) -> dict[str, Any]:
    """Context fields both recipes supply identically.

    Kept in one place so the two recipes cannot drift on what they claim about
    themselves, which is how a guardrail ends up checking a lie.
    """
    # Is there an EMG channel included that could be regressed out?
    emg_available = any(
        row.get("region") == "emg" and row.get("include", "").lower() == "true"
        for row in session.manifest.channels_for(session.study_id, session.session)
    )
    privacy = (session.configs.get("privacy") or {})
    return {
        # What the analyst says this run is about, for G5. Read off the params
        # rather than required of them, so a recipe without the field simply
        # makes no claim.
        "claimed_event_duration_s": getattr(params, "claimed_event_duration_s", None),
        # Both recipes integrate per derivation and average last, by construction.
        "ratio_before_average": True,
        "emg_available": emg_available,
        "emg_regressed": False,
        # Computed, not asserted. This used to be a bare `()` beside the comment
        # "nothing writes a raw path into its outputs", which is the shape of
        # mistake G13 exists to catch: the check was handed the conclusion
        # instead of the evidence, so `if not ctx.paths_in_outputs` returned
        # early and G13 could never fire on any run.
        #
        # What a run would actually write is the input location, and `add_input`
        # writes it only when the site has declared filenames safe for this
        # format. So this asks the same two questions in the same order and
        # reports the answer. Empty here means "this run will write no path",
        # verified rather than claimed.
        "paths_in_outputs": _paths_a_run_would_write(session, privacy),
        # Resolved per format: the setting may be a per-format mapping, and
        # bool() of one would hand G13 a True for every format at once.
        "filenames_deidentified": filenames_deidentified_for(
            privacy, session.recording.format
        ),
    }


def guardrail_context(session: Any, params: PsdParams) -> dict[str, Any]:
    """What the guardrails can see before anything is computed."""
    conditions = tuple(params.conditions or session.conditions())
    bands = {
        name: (float(lo), float(hi))
        for name, (lo, hi) in (
            (session.configs.get("bands", {}).get("bands") or {}).items()
        )
        if hi <= params.fmax
    }
    bands["requested_range"] = (params.fmin, params.fmax)
    usable = usable_bandwidth_hz(
        params.sfreq_target_hz, cutoff_fraction_from(session.configs)
    )
    return {
        "reference_scheme": params.primary_reference,
        # Intraoperative DBS recordings share a reference across contacts. The
        # montage comparison this recipe runs is how that is demonstrated.
        "reference_is_shared": True,
        "sfreq_hz": params.sfreq_target_hz,
        "usable_bandwidth_hz": usable,
        "requested_bands": bands,
        "window_s": params.window_s,
        "conditions": conditions,
        "reports_db": True,
        "reports_z": True,
        "baseline_is_smoothed": False,
        "per_contact_baseline_subtracted": True,
        **_shared_guardrail_context(session, params),
    }


@recipe(
    NAME,
    "Power spectral density per derivation and condition, under every montage, "
    "reported in dB alongside a z against a chosen baseline.",
    PsdParams,
    version="1",
    question="What does the spectrum look like in each condition, and where across "
             "the frequency range do they differ?",
    produces="A spectrum per derivation and condition in dB and z, tables at row and "
             "region level, and figures comparing the montages.",
)
def psd_by_condition(ctx: RecipeContext) -> RecipeResult:
    params: PsdParams = ctx.params
    session = ctx.session

    lead_ids = params.leads or list(session.leads())
    conditions = params.conditions or list(session.conditions())
    schemes = params.references or list(available_schemes())

    records: list[dict[str, Any]] = []
    skipped_short: list[dict[str, Any]] = []
    ctx.log(f"leads={lead_ids} conditions={conditions} schemes={schemes}")

    for lead_id in lead_ids:
        lead = session.leads()[lead_id]
        for scheme in schemes:
            for condition in conditions:
                for t0, t1, row in _windows_for(ctx, condition):
                    for e0, e1 in _epoch_bounds(t0, t1, params):
                        sig = session.read_derived(
                            lead_id, scheme, tmin=e0, tmax=e1,
                            sfreq_target_hz=params.sfreq_target_hz,
                        )
                        needed = requested_nperseg(sig.sfreq_hz, params)
                        if sig.data.shape[1] < needed:
                            ctx.log(
                                f"{lead_id}/{scheme}/{condition}: a stretch of "
                                f"{sig.data.shape[1] / sig.sfreq_hz:.3f}s is shorter "
                                f"than window_s={params.window_s}s, so it would get "
                                "its own frequency grid and never compare with the "
                                "rest of the table. Skipped."
                            )
                            skipped_short.append(
                                {"condition": condition, "lead_id": lead_id,
                                 "scheme": scheme,
                                 "duration_s": round(sig.data.shape[1] / sig.sfreq_hz, 4)}
                            )
                            continue
                        freqs, power = _segment_spectra(sig.data, sig.sfreq_hz, params)
                        db = _to_db(power)
                        for i, name in enumerate(sig.names):
                            records.append(
                                {
                                    "study_id": session.study_id,
                                    "session": session.session,
                                    "lead_id": lead_id,
                                    "target": lead.target,
                                    "scheme": scheme,
                                    "derivation": name,
                                    "row": sig.rows[i],
                                    "condition": condition,
                                    "window_status": row.get("status", ""),
                                    "freqs": freqs,
                                    "db_segments": db[i],
                                }
                            )
                        ctx.log(
                            f"{lead_id}/{scheme}/{condition} {e0:.1f}-{e1:.1f}s "
                            f"-> {db.shape[1]} segments @ {sig.sfreq_hz:.0f} Hz"
                        )

    if not records:
        raise RuntimeError(
            "no spectra computed: check that the manifest windows fall inside the "
            "recording and that at least one channel is included"
        )

    long = _build_long_table(records, params)
    tables = _aggregate(long)
    figures = _figures(ctx, long, params)

    out = ctx.out_dir
    long.to_parquet(out / "psd_long.parquet", index=False)
    tables["by_row"].to_csv(out / "psd_by_row.csv", index=False)
    tables["by_region"].to_csv(out / "psd_by_region.csv", index=False)
    tables["montage_spread"].to_csv(out / "montage_spread.csv", index=False)

    summary = _summary(long, tables, params, ctx.configs)
    # A skipped stretch is a dropped observation. The log says so while the run
    # is happening; the summary says so afterwards, which is when somebody reads
    # it.
    if skipped_short:
        summary["skipped_short_stretches"] = skipped_short
        summary["n_skipped_short_stretches"] = len(skipped_short)
    # G9's two numbers. They cannot be known before the recipe runs, which is why
    # the guardrail engine evaluates them in a second pass afterwards.
    summary["nonstationarity"] = _nonstationarity(records, long, params, ctx.configs)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))

    return RecipeResult(
        tables={"psd_long": long, **tables},
        figures=figures,
        summary=summary,
    )


MIN_SEGMENTS_FOR_EXCURSION = 5


def _band_of_interest(params: PsdParams, configs: dict[str, Any]) -> tuple[float, float] | None:
    """Edges of the run's band, from configs/bands.yaml. None if it is not defined.

    Never a literal. A band edge written into code is a band edge nobody can
    change without a release, and the two places in this file that need one used
    to disagree: the summary searched 13 to 35 Hz for a beta peak while the
    config called beta 13 to 30.
    """
    bands = (configs.get("bands") or {}).get("bands") or {}
    edges = bands.get(params.band_of_interest)
    if not edges:
        return None
    return float(edges[0]), float(edges[1])


def _excursion_db(series: np.ndarray) -> float | None:
    """Peak-to-peak wander of the slow component, as GRL 4 defines it.

    Smooth first, with a moving average about a fifth of the series long, so this
    measures drift rather than segment-to-segment variance. The distinction is
    the whole of guardrail G9: variance falls as more data is averaged and drift
    does not, so a tight error bar is not evidence that a comparison is sound.

    Matching GRL 4's definition matters because GRL 4 is where the threshold of
    1.0 was measured. A different smoothing would give a different number against
    the same threshold.
    """
    # Too few segments to smooth is not an excursion of zero, it is an
    # unmeasurable one, and the caller has to be able to tell those apart. A
    # window run as one observation gives one segment, and reporting 0.0 there
    # would let G9 compute a ratio of zero and stay quiet on the grounds that
    # nothing drifted, when nothing was looked at.
    if series.size < MIN_SEGMENTS_FOR_EXCURSION:
        return None
    window = max(3, series.size // 5)
    if window > series.size:
        return None
    kernel = np.ones(window) / window
    smooth = np.convolve(series, kernel, mode="valid")
    return float(np.max(smooth) - np.min(smooth))


def _nonstationarity(
    records: list[dict[str, Any]], long: pd.DataFrame, params: PsdParams,
    configs: dict[str, Any],
) -> dict[str, Any]:
    """The baseline excursion and the largest effect this run reports, for G9.

    Both are computed in one band on the primary reference, because a ratio
    between numbers taken from different bands or different montages compares
    nothing. The band comes from configs/bands.yaml.
    """
    edges = _band_of_interest(params, configs)
    if edges is None:
        return {
            "available": False,
            "reason": f"band {params.band_of_interest!r} is not configured",
        }
    lo, hi = edges

    baseline = params.baseline_condition
    if baseline not in set(long["condition"]):
        return {"available": False, "reason": f"baseline condition {baseline!r} not in this run"}

    # The excursion: the slow wander of band power across the baseline's own
    # segments, per derivation, taking the worst. Segments within one record are
    # in time order, which is what the smoothing assumes.
    excursions: list[tuple[float, str]] = []
    too_short = 0
    for rec in records:
        if rec["condition"] != baseline or rec["scheme"] != params.primary_reference:
            continue
        freqs = np.asarray(rec["freqs"], dtype=float)
        mask = (freqs >= lo) & (freqs < hi)
        if not mask.any():
            continue
        per_segment = np.asarray(rec["db_segments"], dtype=float)[:, mask].mean(axis=1)
        value = _excursion_db(per_segment)
        if value is None:
            too_short += 1
            continue
        excursions.append((value, str(rec["derivation"])))
    if not excursions:
        reason = (
            f"the baseline gave fewer than {MIN_SEGMENTS_FOR_EXCURSION} segments per "
            f"derivation, which is too few to separate drift from segment noise"
            if too_short
            else "no baseline segments on the primary reference"
        )
        return {"available": False, "reason": reason}
    max_excursion, worst_derivation = max(excursions, key=lambda pair: pair[0])

    # The effect: the largest contrast this run reports in the same band and
    # montage, against the same baseline.
    primary = long[(long["scheme"] == params.primary_reference)
                   & (long["freq_hz"] >= lo) & (long["freq_hz"] < hi)]
    by_condition = primary.groupby(["derivation", "condition"])["db"].mean().unstack()
    if baseline not in by_condition.columns or by_condition.shape[1] < 2:
        return {"available": False, "reason": "no condition to contrast against the baseline"}
    contrasts = by_condition.drop(columns=[baseline]).sub(by_condition[baseline], axis=0)
    reported_effect = float(np.nanmax(np.abs(contrasts.to_numpy())))

    return {
        "available": True,
        "band_hz": [lo, hi],
        "band": params.band_of_interest,
        "scheme": params.primary_reference,
        "baseline_condition": baseline,
        "max_excursion_db": max_excursion,
        "excursion_derivation": worst_derivation,
        "n_derivations_checked": len(excursions),
        "reported_effect_db": reported_effect,
    }


def guardrail_context_after(
    session: Any, params: PsdParams, result: Any
) -> dict[str, Any]:
    """What guardrail G9 needs, which only exists once the recipe has run.

    Returns nothing when the run could not produce the pair, so that G9 stays
    quiet rather than firing on a number that was not measured.
    """
    block = (result.summary or {}).get("nonstationarity") or {}
    if not block.get("available"):
        return {}
    return {
        "max_excursion_db": block["max_excursion_db"],
        "reported_effect_db": block["reported_effect_db"],
    }


def _build_long_table(records: list[dict[str, Any]], params: PsdParams) -> pd.DataFrame:
    """One row per derivation, condition, scheme, frequency, with dB and z."""
    frames = []
    for rec in records:
        freqs, db_segments = rec["freqs"], rec["db_segments"]
        frames.append(
            pd.DataFrame(
                {
                    **{
                        k: rec[k]
                        for k in (
                            "study_id", "session", "lead_id", "target", "scheme",
                            "derivation", "row", "condition", "window_status",
                        )
                    },
                    "freq_hz": freqs,
                    "db": db_segments.mean(axis=0),
                    "db_sd": db_segments.std(axis=0, ddof=1) if db_segments.shape[0] > 1 else 0.0,
                    "n_segments": db_segments.shape[0],
                }
            )
        )
    long = pd.concat(frames, ignore_index=True)
    return _add_z(long, params)


def _add_z(long: pd.DataFrame, params: PsdParams) -> pd.DataFrame:
    """Add the z column, using the chosen centre and scale."""
    choice = describe_choice(
        params.baseline_center, params.baseline_scale, params.baseline_condition
    )
    key = ["lead_id", "scheme", "derivation", "freq_hz"]
    long = long.copy()
    long["z"] = normalize(long, choice, key)
    # Carried on every row so a table read on its own still says what z meant.
    long["z_definition"] = choice.sentence()
    return long


def _aggregate(long: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per-row and per-region aggregates, plus the across-montage spread."""
    by_row = (
        long.groupby(["lead_id", "target", "scheme", "row", "condition", "freq_hz"])
        .agg(db=("db", "mean"), z=("z", "mean"), n_derivations=("derivation", "nunique"))
        .reset_index()
    )
    by_region = (
        long.groupby(["target", "scheme", "condition", "freq_hz"])
        .agg(db=("db", "mean"), z=("z", "mean"), n_derivations=("derivation", "nunique"))
        .reset_index()
    )
    # How much the answer depends on the montage: guardrail G1 made visible.
    spread = (
        by_region.groupby(["target", "condition", "freq_hz"])["db"]
        .agg(db_min="min", db_max="max", db_range=lambda s: float(s.max() - s.min()))
        .reset_index()
    )
    return {"by_row": by_row, "by_region": by_region, "montage_spread": spread}


def _summary(
    long: pd.DataFrame, tables: dict[str, pd.DataFrame], params: PsdParams,
    configs: dict[str, Any],
) -> dict[str, Any]:
    primary = long[long["scheme"] == params.primary_reference]
    edges = _band_of_interest(params, configs)
    if edges is None:
        in_band = primary.iloc[0:0]
    else:
        in_band = primary[(primary["freq_hz"] >= edges[0]) & (primary["freq_hz"] < edges[1])]
    peaks = (
        in_band.loc[in_band.groupby(["target", "condition"])["db"].idxmax()]
        [["target", "condition", "freq_hz", "db", "z"]]
        if not in_band.empty
        else pd.DataFrame()
    )
    spread = tables["montage_spread"]
    choice = describe_choice(
        params.baseline_center, params.baseline_scale, params.baseline_condition
    )
    return {
        "recipe": NAME,
        "primary_reference": params.primary_reference,
        "normalization": choice.to_record(),
        "unit": params.unit,
        "n_rows": int(len(long)),
        "schemes": sorted(long["scheme"].unique().tolist()),
        "conditions": sorted(long["condition"].unique().tolist()),
        # Named so the peak table below is readable without knowing the params.
        "band_of_interest": params.band_of_interest,
        "band_of_interest_hz": list(edges) if edges else None,
        "peak_in_band_by_target_condition": (
            peaks.to_dict("records") if not peaks.empty else []
        ),
        "montage_spread_db_median": (
            float(spread["db_range"].median()) if not spread.empty else None
        ),
        "montage_spread_db_max": (
            float(spread["db_range"].max()) if not spread.empty else None
        ),
        "windows_under_revision": sorted(
            long.loc[long["window_status"] == "under_revision", "condition"].unique().tolist()
        ),
    }


def _z_sentence(params: PsdParams) -> str:
    return describe_choice(
        params.baseline_center, params.baseline_scale, params.baseline_condition
    ).sentence()


def _figures(ctx: RecipeContext, long: pd.DataFrame, params: PsdParams) -> list:
    """Headline figure under the primary montage, plus the across-montage spread."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    out = ctx.out_dir
    paths = []
    run_id = ctx.run.run_id

    primary = long[long["scheme"] == params.primary_reference]
    targets = sorted(primary["target"].unique())
    conditions = sorted(primary["condition"].unique())

    for value, label in (("db", "Power (dB)"), ("z", "z vs baseline")):
        fig, axes = plt.subplots(
            1, max(1, len(targets)), figsize=(6 * max(1, len(targets)), 4), squeeze=False
        )
        for ax, target in zip(axes[0], targets, strict=False):
            sub = primary[primary["target"] == target]
            for condition in conditions:
                s = sub[sub["condition"] == condition].groupby("freq_hz")[value].mean()
                ax.plot(s.index, s.to_numpy(), label=condition, linewidth=1.0)
            ax.set_title(f"{target.upper()}  ({params.primary_reference})")
            ax.set_xlabel("Frequency (Hz)")
            ax.set_ylabel(label)
            ax.set_xscale("log")
            ax.grid(alpha=0.3, which="both")
        axes[0][0].legend(fontsize=8)
        caption = f"{NAME}  ·  {value}  ·  run {run_id}"
        if value == "z":
            caption += f"\n{_z_sentence(params)}"
        fig.suptitle(caption, fontsize=8)
        fig.tight_layout()
        for ext in ("png", "svg"):
            p = out / f"psd_{value}.{ext}"
            fig.savefig(p, dpi=150)
            paths.append(p)
        plt.close(fig)

    # Montage spread: the reason monopolar is not a default.
    fig, ax = plt.subplots(figsize=(7, 4))
    for scheme in sorted(long["scheme"].unique()):
        s = long[long["scheme"] == scheme].groupby("freq_hz")["db"].mean()
        ax.plot(s.index, s.to_numpy(), label=scheme, linewidth=1.0)
    ax.set_xscale("log")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Power (dB)")
    ax.set_title(f"Montage comparison  ·  run {run_id}", fontsize=9)
    ax.grid(alpha=0.3, which="both")
    ax.legend(fontsize=8)
    fig.tight_layout()
    for ext in ("png", "svg"):
        p = out / f"montage_comparison.{ext}"
        fig.savefig(p, dpi=150)
        paths.append(p)
    plt.close(fig)
    return paths


# The registry looks for these: one builds the guardrail context before running,
# the other gives an interface the words to show beside each parameter choice.
psd_by_condition.guardrail_context = guardrail_context
psd_by_condition.guardrail_context_after = guardrail_context_after
psd_by_condition.option_explanations = options_for_schema
