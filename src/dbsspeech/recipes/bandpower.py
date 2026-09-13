"""bandpower_contrast: band power per condition, and honest contrasts between them.

The dissertation question in recipe form: are there spectral changes in STN and
GPi during speech and inner speech, and do they differ from movement.

Three things this recipe refuses to do, because each is a way to get a wrong
answer that looks right:

Ratio before average
    Band power is integrated per derivation, then contrasts are formed per
    derivation, and only then averaged across derivations. Averaging power first
    and taking the ratio after is a different quantity by Jensen's inequality,
    and it is not the one anyone means. Guardrail G3.

A p-value it has not earned
    With `unit="window"` there is one observation per condition, so no test is
    possible and none is reported: the effect is descriptive and says so. With
    pseudo-epochs there is an n, but the epochs come from one continuous
    recording and are not independent, so the permutation test is reported with
    that stated on every row rather than in a footnote nobody reads.

Parametric tests
    Trial counts are small and the distributions are not normal. Everything here
    is permutation and bootstrap.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field, model_validator

from ..preprocess import available_schemes, cutoff_fraction_from, usable_bandwidth_hz
from ..stats import CENTERS, SCALES, describe_choice, options_for_schema
from .psd import (
    MIN_SEGMENTS_FOR_EXCURSION,
    ClaimedEventDuration,
    _epoch_bounds,
    _excursion_db,
    _segment_spectra,
    _shared_guardrail_context,
    _to_db,
    _windows_for,
    requested_nperseg,
)
from .registry import RecipeContext, RecipeResult, recipe

NAME = "bandpower_contrast"

# Below this many observations per condition, a permutation test is not
# meaningful and none is reported.
MIN_OBSERVATIONS_FOR_TEST = 5


class BandpowerParams(BaseModel):
    """Parameters for bandpower_contrast."""

    # See PsdParams for why these live here rather than in each Field call.
    LABELS: ClassVar[dict[str, str]] = {
        "leads": "Leads to include",
        "conditions": "Conditions to compare",
        "contrasts": "Pairs to compare (blank means every pair)",
        "bands": "Frequency bands (blank means configs/bands.yaml)",
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
        "log10": "Compare log power rather than raw power",
        "n_permutations": "Permutations for the test",
        "n_bootstrap": "Bootstrap samples for the interval",
        "seed": "Random seed, so the test repeats exactly",
        "baseline_center": "What z is measured from",
        "baseline_scale": "What z is measured in",
        "baseline_condition": "Baseline condition",
    }
    ESSENTIAL: ClassVar[tuple[str, ...]] = (
        "conditions", "contrasts", "bands", "primary_reference",
    )
    claimed_event_duration_s: ClaimedEventDuration = None

    leads: list[str] | None = Field(default=None, description="None means every lead.")
    conditions: list[str] | None = Field(
        default=None, description="None means every condition in the manifest."
    )
    contrasts: list[list[str]] | None = Field(
        default=None,
        description=(
            "Condition pairs to compare, as [a, b]. None means every pair present, "
            "which keeps the comparison symmetric rather than privileging one."
        ),
    )
    bands: dict[str, list[float]] | None = Field(
        default=None, description="None means the bands in configs/bands.yaml."
    )
    unit: Literal["window", "pseudo_epoch"] = Field(
        default="pseudo_epoch",
        description=(
            "pseudo_epoch gives an n so a contrast can be tested, at the cost that "
            "epochs from one recording are not independent. window gives one "
            "observation per condition and no test at all."
        ),
    )
    epoch_s: float = Field(default=2.0, gt=0)
    epoch_overlap: float = Field(default=0.0, ge=0, lt=1,
                                description="Overlap makes epochs even less independent.")
    references: list[str] | None = Field(default=None)
    primary_reference: str = Field(default="bipolar_vertical")
    sfreq_target_hz: float = Field(default=8138.0, gt=0)
    method: Literal["welch", "multitaper"] = Field(default="welch")
    window_s: float = Field(default=1.0, gt=0)

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

    fmin: float = Field(default=1.0, ge=0)
    fmax: float = Field(default=200.0, gt=0)
    log10: bool = Field(default=True, description="Work in dB. Ratios become differences.")
    n_permutations: int = Field(default=5000, ge=100)
    n_bootstrap: int = Field(default=2000, ge=100)
    seed: int = Field(default=0, description="Recorded, so a p-value is reproducible.")
    baseline_center: Literal[CENTERS] = Field(default="grand_mean")  # type: ignore[valid-type]
    baseline_scale: Literal[SCALES] = Field(default="pooled_within_condition")  # type: ignore[valid-type]
    baseline_condition: str = Field(default="rest")


def _band_edges(ctx: RecipeContext, params: BandpowerParams) -> dict[str, tuple[float, float]]:
    if params.bands:
        return {k: (float(v[0]), float(v[1])) for k, v in params.bands.items()}
    configured = (ctx.configs.get("bands") or {}).get("bands") or {}
    return {
        name: (float(lo), float(hi))
        for name, (lo, hi) in configured.items()
        if hi <= params.fmax
    }


def _integrate(freqs: np.ndarray, power: np.ndarray, lo: float, hi: float) -> np.ndarray:
    """Mean power in a band, per observation. Returns one value per row of `power`.

    NaN when the band contains no frequency bin, which happens when the analysis
    window is too short to resolve it: a 0.2 s epoch gives 5 Hz resolution, and
    the 1 to 4 Hz delta band then has nothing in it at all. The caller must treat
    that as unmeasurable rather than as a number.
    """
    mask = (freqs >= lo) & (freqs < hi)
    if not mask.any():
        return np.full(power.shape[0], np.nan)
    return power[:, mask].mean(axis=1)


def unresolvable_bands(
    bands: dict[str, tuple[float, float]], window_s: float, sfreq_hz: float
) -> dict[str, str]:
    """Bands the analysis window cannot resolve, with the reason.

    Frequency resolution is 1 / window_s. A band narrower than that, or one whose
    range falls between bins, cannot be measured however long the recording is.
    Reporting a number for it would be inventing one.
    """
    resolution = 1.0 / window_s
    n = max(1, int(round(window_s * sfreq_hz)))
    freqs = np.fft.rfftfreq(n, 1.0 / sfreq_hz)
    out: dict[str, str] = {}
    for name, (lo, hi) in bands.items():
        if not ((freqs >= lo) & (freqs < hi)).any():
            out[name] = (
                f"no frequency bin falls in {lo}-{hi} Hz at {resolution:.2f} Hz "
                f"resolution (window {window_s} s). Lengthen the window to at "
                f"least {1.0 / max(hi - lo, 1e-9):.2f} s to resolve it."
            )
    return out


def _permutation_p(a: np.ndarray, b: np.ndarray, rng: np.random.Generator, n: int) -> float:
    """Two-sided permutation test on the difference of means.

    Labels are shuffled, not values resampled, which is what makes this a test of
    the labelling rather than of the spread.
    """
    observed = abs(float(a.mean() - b.mean()))
    pooled = np.concatenate([a, b])
    n_a = len(a)
    count = 0
    for _ in range(n):
        rng.shuffle(pooled)
        if abs(float(pooled[:n_a].mean() - pooled[n_a:].mean())) >= observed:
            count += 1
    # Add-one correction: a p-value of exactly zero is not something this many
    # permutations can support.
    return (count + 1) / (n + 1)


def _bootstrap_ci(
    a: np.ndarray, b: np.ndarray, rng: np.random.Generator, n: int
) -> tuple[float, float]:
    diffs = np.empty(n)
    for i in range(n):
        diffs[i] = (
            rng.choice(a, len(a), replace=True).mean()
            - rng.choice(b, len(b), replace=True).mean()
        )
    return float(np.percentile(diffs, 2.5)), float(np.percentile(diffs, 97.5))


def guardrail_context(session: Any, params: BandpowerParams) -> dict[str, Any]:
    conditions = tuple(params.conditions or session.conditions())
    configured = (session.configs.get("bands") or {}).get("bands") or {}
    bands = {
        name: (float(lo), float(hi))
        for name, (lo, hi) in (params.bands or configured).items()
    }
    return {
        "reference_scheme": params.primary_reference,
        "reference_is_shared": True,
        "sfreq_hz": params.sfreq_target_hz,
        "usable_bandwidth_hz": usable_bandwidth_hz(
            params.sfreq_target_hz, cutoff_fraction_from(session.configs)
        ),
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
    "Band power per derivation and condition, with permutation-tested contrasts "
    "and bootstrap confidence intervals. No parametric tests.",
    BandpowerParams,
    version="1",
    question="Is power in a named band, such as beta, higher in one condition than "
             "another, and is the difference bigger than chance?",
    produces="Band power per derivation and condition, each contrast with a "
             "permutation p-value and a bootstrap interval, and a figure per band.",
)
def bandpower_contrast(ctx: RecipeContext) -> RecipeResult:
    params: BandpowerParams = ctx.params
    session = ctx.session
    rng = np.random.default_rng(params.seed)

    lead_ids = params.leads or list(session.leads())
    conditions = params.conditions or list(session.conditions())
    schemes = params.references or list(available_schemes())
    bands = _band_edges(ctx, params)
    if not bands:
        raise RuntimeError(
            "no bands to analyze: configs/bands.yaml defines none below fmax"
        )

    unresolvable = unresolvable_bands(bands, params.window_s, params.sfreq_target_hz)
    for band, reason in unresolvable.items():
        ctx.log(f"band {band} is not resolvable: {reason}")

    rows: list[dict[str, Any]] = []
    skipped_short: list[dict[str, Any]] = []
    ctx.log(f"leads={lead_ids} conditions={conditions} bands={sorted(bands)}")

    for lead_id in lead_ids:
        lead = session.leads()[lead_id]
        for scheme in schemes:
            for condition in conditions:
                for t0, t1, window in _windows_for(ctx, condition):
                    for index, (e0, e1) in enumerate(_epoch_bounds(t0, t1, params)):
                        sig = session.read_derived(
                            lead_id, scheme, tmin=e0, tmax=e1,
                            sfreq_target_hz=params.sfreq_target_hz,
                        )
                        needed = requested_nperseg(sig.sfreq_hz, params)
                        if sig.data.shape[1] < needed:
                            ctx.log(
                                f"{lead_id}/{scheme}/{condition}: a stretch of "
                                f"{sig.data.shape[1] / sig.sfreq_hz:.3f}s is shorter "
                                f"than window_s={params.window_s}s, so its spectrum "
                                "would sit on a different frequency grid. Skipped."
                            )
                            skipped_short.append(
                                {"condition": condition, "lead_id": lead_id,
                                 "scheme": scheme,
                                 "duration_s": round(sig.data.shape[1] / sig.sfreq_hz, 4)}
                            )
                            continue
                        freqs, power = _segment_spectra(sig.data, sig.sfreq_hz, params)
                        # Average the per-segment spectra within this epoch, then
                        # integrate. Power first, band second, ratio last.
                        mean_power = power.mean(axis=1)
                        for i, name in enumerate(sig.names):
                            for band, (lo, hi) in bands.items():
                                value = float(
                                    _integrate(freqs, mean_power[i : i + 1], lo, hi)[0]
                                )
                                rows.append({
                                    "study_id": session.study_id,
                                    "lead_id": lead_id,
                                    "target": lead.target,
                                    "scheme": scheme,
                                    "derivation": name,
                                    "row": sig.rows[i],
                                    "condition": condition,
                                    "window_status": window.get("status", ""),
                                    "epoch": index,
                                    "band": band,
                                    "power": value,
                                    "db": _to_db(np.array([value]))[0],
                                })

    if not rows:
        raise RuntimeError("no band power computed; check the manifest windows")

    long = pd.DataFrame(rows)
    value_col = "db" if params.log10 else "power"
    stats = _contrasts(long, params, rng, value_col)
    summary = _summary(long, stats, params, value_col)
    # A skipped stretch is a dropped observation. The log says so while the run
    # is happening; the summary says so afterwards, which is when somebody reads
    # it.
    if skipped_short:
        summary["skipped_short_stretches"] = skipped_short
        summary["n_skipped_short_stretches"] = len(skipped_short)
    summary["unresolvable_bands"] = unresolvable
    summary["nonstationarity"] = _nonstationarity(long, stats, params)

    out = ctx.out_dir
    long.to_parquet(out / "bandpower_long.parquet", index=False)
    stats.to_csv(out / "stats.csv", index=False)
    _by_row(long, value_col).to_csv(out / "bandpower_by_row.csv", index=False)
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    figures = _figures(ctx, stats, params)

    return RecipeResult(tables={"bandpower_long": long, "stats": stats},
                        figures=figures, summary=summary)


def _contrasts(
    long: pd.DataFrame, params: BandpowerParams, rng: np.random.Generator, value_col: str
) -> pd.DataFrame:
    """One row per derivation, band and contrast. Effect first, test only if earned."""
    present = list(dict.fromkeys(long["condition"]))
    pairs = (
        [tuple(p) for p in params.contrasts]
        if params.contrasts
        else [(a, b) for i, a in enumerate(present) for b in present[i + 1:]]
    )

    out: list[dict[str, Any]] = []
    grouped = long.groupby(["lead_id", "target", "scheme", "derivation", "row", "band"])
    for (lead_id, target, scheme, derivation, row_label, band), block in grouped:
        by_condition = {c: g[value_col].to_numpy() for c, g in block.groupby("condition")}
        for a, b in pairs:
            if a not in by_condition or b not in by_condition:
                continue
            va, vb = by_condition[a], by_condition[b]
            # Drop non-finite observations before anything is computed. A band the
            # window could not resolve produces NaN, and a p-value derived from
            # NaN comparisons is a number with no meaning behind it.
            va, vb = va[np.isfinite(va)], vb[np.isfinite(vb)]
            if va.size == 0 or vb.size == 0:
                out.append({
                    "lead_id": lead_id, "target": target, "scheme": scheme,
                    "derivation": derivation, "row": row_label, "band": band,
                    "contrast": f"{a}-{b}", "condition_a": a, "condition_b": b,
                    "n_a": 0, "n_b": 0, "effect": np.nan,
                    "units": "dB" if value_col == "db" else "power",
                    "p_perm": np.nan, "ci_low": np.nan, "ci_high": np.nan,
                    "test": "none",
                    "independence": (
                        "band not measurable at this window length; no bins fall "
                        "inside it"
                    ),
                })
                continue

            effect = float(va.mean() - vb.mean())
            n_min = min(len(va), len(vb))
            testable = n_min >= MIN_OBSERVATIONS_FOR_TEST

            record: dict[str, Any] = {
                "lead_id": lead_id, "target": target, "scheme": scheme,
                "derivation": derivation, "row": row_label, "band": band,
                "contrast": f"{a}-{b}", "condition_a": a, "condition_b": b,
                "n_a": len(va), "n_b": len(vb),
                "effect": effect,
                "units": "dB" if value_col == "db" else "power",
            }
            if testable:
                record["p_perm"] = _permutation_p(va.copy(), vb.copy(), rng,
                                                  params.n_permutations)
                lo, hi = _bootstrap_ci(va, vb, rng, params.n_bootstrap)
                record["ci_low"], record["ci_high"] = lo, hi
                record["test"] = "permutation, labels shuffled"
                # Stated on every row, not in a footnote: epochs from one
                # continuous recording are not independent observations.
                record["independence"] = (
                    "pseudo-epochs from one recording; not independent, so p is "
                    "anti-conservative"
                    if params.unit == "pseudo_epoch"
                    else "one observation per condition"
                )
            else:
                record["p_perm"] = np.nan
                record["ci_low"] = record["ci_high"] = np.nan
                record["test"] = "none"
                record["independence"] = (
                    f"only {n_min} observation(s) per condition; a test needs at "
                    f"least {MIN_OBSERVATIONS_FOR_TEST}. Effect is descriptive."
                )
            out.append(record)
    return pd.DataFrame(out)


def _by_row(long: pd.DataFrame, value_col: str) -> pd.DataFrame:
    """Per-row aggregate. Averaging happens last, after per-derivation values."""
    return (
        long.groupby(["lead_id", "target", "scheme", "row", "condition", "band"])
        .agg(value=(value_col, "mean"), n_derivations=("derivation", "nunique"),
             n_epochs=("epoch", "nunique"))
        .reset_index()
    )


def _nonstationarity(
    long: pd.DataFrame, stats: pd.DataFrame, params: BandpowerParams
) -> dict[str, Any]:
    """Guardrail G9's two numbers: the baseline's drift and the effect reported.

    The band is not a parameter here. It is whichever band carried the largest
    effect, so the excursion and the effect describe the same band by
    construction rather than by an analyst remembering to line them up.
    """
    primary = stats[stats["scheme"] == params.primary_reference].dropna(subset=["effect"])
    if primary.empty:
        return {"available": False, "reason": "no contrast on the primary reference"}
    largest = primary.reindex(primary["effect"].abs().sort_values(ascending=False).index).iloc[0]
    band = str(largest["band"])
    reported_effect = float(abs(largest["effect"]))

    baseline = long[
        (long["condition"] == params.baseline_condition)
        & (long["scheme"] == params.primary_reference)
        & (long["band"] == band)
    ]
    if baseline.empty:
        return {
            "available": False,
            "reason": f"baseline condition {params.baseline_condition!r} has no {band} epochs",
        }

    excursions: list[tuple[float, str]] = []
    too_short = 0
    for derivation, group in baseline.groupby("derivation"):
        series = group.sort_values("epoch")["db"].to_numpy(dtype=float)
        value = _excursion_db(series)
        if value is None:
            too_short += 1
            continue
        excursions.append((value, str(derivation)))
    if not excursions:
        reason = (
            f"the baseline gave fewer than {MIN_SEGMENTS_FOR_EXCURSION} epochs per "
            f"derivation, which is too few to separate drift from epoch noise"
            if too_short
            else "no baseline epochs on the primary reference"
        )
        return {"available": False, "reason": reason}
    max_excursion, worst = max(excursions, key=lambda pair: pair[0])

    return {
        "available": True,
        "band": band,
        "scheme": params.primary_reference,
        "baseline_condition": params.baseline_condition,
        "max_excursion_db": max_excursion,
        "excursion_derivation": worst,
        "n_derivations_checked": len(excursions),
        "reported_effect_db": reported_effect,
    }


def guardrail_context_after(
    session: Any, params: BandpowerParams, result: Any
) -> dict[str, Any]:
    """What G9 needs, which only exists once a contrast has been computed."""
    block = (result.summary or {}).get("nonstationarity") or {}
    if not block.get("available"):
        return {}
    return {
        "max_excursion_db": block["max_excursion_db"],
        "reported_effect_db": block["reported_effect_db"],
    }


def _summary(
    long: pd.DataFrame, stats: pd.DataFrame, params: BandpowerParams, value_col: str
) -> dict[str, Any]:
    choice = describe_choice(params.baseline_center, params.baseline_scale,
                             params.baseline_condition)
    primary = stats[stats["scheme"] == params.primary_reference]
    tested = primary.dropna(subset=["p_perm"])
    # The note used to count only the primary montage while stats.csv carried
    # every montage, so it understated the tests actually computed by roughly the
    # montage count. The summary reported the larger number as n_contrast_rows on
    # the next line, so it contradicted itself in one screen. A reader who picks
    # the best-looking montage is multiplying by all of them, whatever the
    # headline figure shows.
    all_tested = stats.dropna(subset=["p_perm"])
    largest = (
        primary.reindex(primary["effect"].abs().sort_values(ascending=False).index)
        .head(8)[["target", "row", "band", "contrast", "effect", "p_perm"]]
        .to_dict("records")
        if not primary.empty
        else []
    )
    return {
        "recipe": NAME,
        "unit": params.unit,
        "primary_reference": params.primary_reference,
        "normalization": choice.to_record(),
        "n_contrast_rows": int(len(stats)),
        "n_tested": int(len(tested)),
        "n_untested": int(len(primary) - len(tested)),
        "bands": sorted(long["band"].unique().tolist()),
        "conditions": sorted(long["condition"].unique().tolist()),
        "largest_effects": largest,
        "multiplicity_note": (
            f"{len(all_tested)} tests were computed across "
            f"{stats['scheme'].nunique()} montage(s) and no correction was "
            f"applied, of which {len(tested)} are in the primary montage "
            f"({params.primary_reference}). Treat any single p-value "
            "accordingly."
        ),
        "windows_under_revision": sorted(
            long.loc[long["window_status"] == "under_revision", "condition"]
            .unique().tolist()
        ),
    }


def _figures(ctx: RecipeContext, stats: pd.DataFrame, params: BandpowerParams) -> list:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    primary = stats[stats["scheme"] == params.primary_reference]
    if primary.empty:
        return []

    out, paths = ctx.out_dir, []
    targets = sorted(primary["target"].unique())
    bands = sorted(primary["band"].unique())
    contrasts = sorted(primary["contrast"].unique())

    fig, axes = plt.subplots(1, max(1, len(targets)),
                             figsize=(5.5 * max(1, len(targets)), 4), squeeze=False)
    x = np.arange(len(bands))
    for ax, target in zip(axes[0], targets, strict=False):
        sub = primary[primary["target"] == target]
        width = 0.8 / max(1, len(contrasts))
        for k, contrast in enumerate(contrasts):
            c = sub[sub["contrast"] == contrast]
            means = [c[c["band"] == b]["effect"].mean() for b in bands]
            lows = [c[c["band"] == b]["ci_low"].mean() for b in bands]
            highs = [c[c["band"] == b]["ci_high"].mean() for b in bands]
            err = None
            if not all(np.isnan(lows)):
                err = [np.abs(np.array(means) - np.array(lows)),
                       np.abs(np.array(highs) - np.array(means))]
            ax.bar(x + k * width - 0.4 + width / 2, means, width, label=contrast,
                   yerr=err, capsize=2, error_kw={"linewidth": 0.8})
        ax.axhline(0, color="black", linewidth=0.8)
        ax.set_xticks(x)
        ax.set_xticklabels(bands, rotation=45, ha="right", fontsize=7)
        ax.set_title(target.upper(), fontsize=9)
        ax.set_ylabel("Effect (dB)", fontsize=8)
        ax.grid(alpha=0.25, axis="y")
    axes[0][0].legend(fontsize=7)
    caption = f"{NAME} · run {ctx.run.run_id}"
    if primary["p_perm"].isna().all():
        caption += " · descriptive only, no test earned at this n"
    fig.suptitle(caption, fontsize=8)
    fig.tight_layout()
    for ext in ("png", "svg"):
        path = out / f"bandpower_contrast.{ext}"
        fig.savefig(path, dpi=150)
        paths.append(path)
    plt.close(fig)
    return paths


bandpower_contrast.guardrail_context = guardrail_context
bandpower_contrast.guardrail_context_after = guardrail_context_after
bandpower_contrast.option_explanations = options_for_schema
