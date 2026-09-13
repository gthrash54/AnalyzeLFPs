"""pac_modulation_index: phase-amplitude coupling per derivation and condition.

Whether the phase of a slow rhythm organizes the amplitude of a fast one, which
in the basal ganglia is the beta-to-gamma coupling reported to change with
stimulation and with movement.

Computed by `pactools.Comodulogram`, not by hand. PAC is unusually easy to get
wrong in ways that still produce a plausible picture, and the traps are in the
estimator rather than in the plotting:

Filter bandwidth, in both directions
    The amplitude filter must be wide enough to contain the phase frequency as
    a sideband, or coupling that exists cannot appear at all. pactools' 'auto'
    satisfies that by using twice the highest phase frequency, and that is the
    default here.

    The phase filter has the opposite failure, and it is the one that produces
    a confident wrong answer rather than a null. Too wide, and neighbouring
    phase bins all admit the same rhythm, so the phase axis stops discriminating
    and the reported peak is whichever bin noise favours. Measured on a signal
    with 8 Hz phase driving 80 Hz amplitude, stepping phase every 2 Hz: a width
    of 4 Hz gave a flat profile across 4 to 12 Hz and put the peak at 4 Hz, the
    wrong answer, while 2 Hz recovered 8 Hz cleanly. The default is therefore
    2 Hz, matching the step, and the recipe warns when the width exceeds the
    step because that is the regime where bins overlap.

Surrogates
    A modulation index is positive for noise. Without a null it is not evidence
    of anything, so `n_surrogates` defaults to a real number and the summary
    reports the surrogate-corrected value beside the raw one.

Sharp edges
    A non-sinusoidal waveform produces harmonics that read as coupling. This is
    a genuine confound rather than an artifact of the method, so it is reported
    as a caveat on every result rather than silently corrected.

Estimator choice
    `tort` is the default because the modulation index is the most reported
    measure and therefore the most comparable, but the estimator is a parameter
    and travels into the record: `canolty`, `ozkurt`, `penny` and `vanwijk` all
    answer slightly different questions and disagree on the same data.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ..preprocess import available_schemes, cutoff_fraction_from, usable_bandwidth_hz
from ..stats import options_for_schema
from .psd import _shared_guardrail_context, _windows_for
from .registry import RecipeContext, RecipeResult, recipe

NAME = "pac_modulation_index"

# Estimators pactools implements. Named here so an unknown one is refused with
# the list rather than failing inside the library.
METHODS = ("tort", "canolty", "ozkurt", "penny", "vanwijk")

# A comodulogram on a very short window is dominated by edge effects. Below this
# many cycles of the slowest phase frequency, the window is skipped and said so.
MIN_PHASE_CYCLES = 10.0


class PacParams(BaseModel):
    """Parameters for pac_modulation_index."""

    leads: list[str] | None = Field(default=None, description="None means every lead.")
    conditions: list[str] | None = Field(
        default=None, description="None means every condition in the manifest."
    )
    references: list[str] | None = Field(
        default=None, description="None means every scheme."
    )
    primary_reference: str = Field(default="bipolar_vertical")

    phase_fq_min_hz: float = Field(default=4.0, gt=0)
    phase_fq_max_hz: float = Field(default=40.0, gt=0)
    phase_fq_step_hz: float = Field(default=2.0, gt=0)
    phase_fq_width_hz: float = Field(
        default=2.0, gt=0,
        description=(
            "Bandwidth of the phase filter, in Hz. Keep it at or below "
            "phase_fq_step_hz: wider than the step means neighbouring bins "
            "admit the same rhythm, the phase axis stops discriminating, and "
            "the reported peak moves to whichever bin noise favours."
        ),
    )

    amplitude_fq_min_hz: float = Field(default=50.0, gt=0)
    amplitude_fq_max_hz: float = Field(default=200.0, gt=0)
    amplitude_fq_step_hz: float = Field(default=10.0, gt=0)
    amplitude_fq_width_hz: float | None = Field(
        default=None,
        description=(
            "Bandwidth of the amplitude filter, in Hz. None means pactools' "
            "'auto', which is twice the highest phase frequency. That is the "
            "sideband condition: the amplitude filter must be wide enough to "
            "contain the phase frequency as a sideband, or coupling that exists "
            "cannot appear at all."
        ),
    )

    method: Literal["tort", "canolty", "ozkurt", "penny", "vanwijk"] = Field(
        default="tort",
        description=(
            "tort is the modulation index, the most reported and so the most "
            "comparable. The estimators disagree on the same data, so this "
            "travels into the run record."
        ),
    )
    n_surrogates: int = Field(
        default=200, ge=0,
        description=(
            "A modulation index is positive for noise, so a null is not optional. "
            "0 disables surrogates and the summary then says the value is "
            "uncorrected."
        ),
    )
    sfreq_target_hz: float = Field(default=1000.0, gt=0)
    seed: int = Field(default=0)


def _phase_range(params: PacParams) -> np.ndarray:
    return np.arange(
        params.phase_fq_min_hz, params.phase_fq_max_hz, params.phase_fq_step_hz
    )


def _amplitude_range(params: PacParams) -> np.ndarray:
    return np.arange(
        params.amplitude_fq_min_hz,
        params.amplitude_fq_max_hz,
        params.amplitude_fq_step_hz,
    )


def _too_short(duration_s: float, params: PacParams) -> str | None:
    """Why this window cannot carry a comodulogram, or None."""
    needed = MIN_PHASE_CYCLES / params.phase_fq_min_hz
    if duration_s < needed:
        return (
            f"{duration_s:.2f}s is under {needed:.2f}s, which is "
            f"{MIN_PHASE_CYCLES:.0f} cycles of the slowest phase frequency "
            f"({params.phase_fq_min_hz} Hz)"
        )
    return None


def _comodulogram(
    signal: np.ndarray, sfreq_hz: float, params: PacParams
) -> tuple[np.ndarray, np.ndarray | None]:
    """Raw comodulogram, and the surrogate-corrected one when surrogates ran."""
    from pactools import Comodulogram

    estimator = Comodulogram(
        fs=sfreq_hz,
        low_fq_range=_phase_range(params),
        low_fq_width=params.phase_fq_width_hz,
        high_fq_range=_amplitude_range(params),
        # pactools spells "choose it for me" as the string 'auto', not None,
        # and 'auto' is 2 * max(low_fq_range), the sideband condition above.
        high_fq_width=(
            "auto"
            if params.amplitude_fq_width_hz is None
            else params.amplitude_fq_width_hz
        ),
        method=params.method,
        n_surrogates=params.n_surrogates,
        progress_bar=False,
        random_state=params.seed,
    )
    estimator.fit(signal)
    raw = np.asarray(estimator.comod_, dtype=float)

    # pactools computes the surrogate z-score itself, against the distribution
    # of the surrogate maximum, which is the comparison that controls for
    # searching the whole comodulogram rather than testing one cell picked
    # after seeing it. Its version is used rather than a local one so there is
    # only one definition of what the correction means.
    corrected = None
    if params.n_surrogates:
        z = getattr(estimator, "comod_z_score_", None)
        if z is not None:
            corrected = np.asarray(z, dtype=float).reshape(raw.shape)
    return raw, corrected


def guardrail_context(session: Any, params: PacParams) -> dict[str, Any]:
    """What the guardrails can see before anything is computed.

    This recipe used to build the same dictionary at the end of the run and hand
    it back on `RecipeResult`, which nothing reads. The effect was that
    `pac_modulation_index` was evaluated against two of the thirteen guardrails,
    silently: the eleven that need to know the reference scheme, the sampling
    rate, the bands or the conditions had nothing to look at, so they returned
    nothing rather than firing. A guardrail that cannot see a run is not a
    guardrail that passed it.

    Everything here comes from `params` and the manifest, because a check that
    ran after the computation would be a description, not a gate.
    """
    conditions = tuple(params.conditions or session.conditions())
    phase = (float(params.phase_fq_min_hz), float(params.phase_fq_max_hz))
    amplitude = (float(params.amplitude_fq_min_hz), float(params.amplitude_fq_max_hz))
    return {
        "reference_scheme": params.primary_reference,
        "reference_is_shared": True,
        "sfreq_hz": params.sfreq_target_hz,
        "usable_bandwidth_hz": usable_bandwidth_hz(
            params.sfreq_target_hz, cutoff_fraction_from(session.configs)
        ),
        "requested_bands": {
            "pac_phase": phase,
            "pac_amplitude": amplitude,
            # G6 compares the highest thing asked for against the anti-alias
            # cutoff, and for this recipe that is the top of the amplitude range.
            "requested_range": (phase[0], amplitude[1]),
        },
        # The shortest stretch this analysis can resolve is one cycle of the
        # slowest phase frequency; MIN_PHASE_CYCLES of them must fit in a window.
        "window_s": MIN_PHASE_CYCLES / float(params.phase_fq_min_hz),
        "conditions": conditions,
        # A modulation index is a normalized distance between distributions. It
        # is neither a decibel nor a z score, so G8 has nothing to complain about.
        "reports_db": False,
        "reports_z": False,
        "baseline_is_smoothed": False,
        # `per_contact_baseline_subtracted` is deliberately absent, not False.
        # G2 asks whether a per-contact baseline was subtracted before contacts
        # are compared, and this recipe has no baseline condition to subtract:
        # the modulation index is a normalized KL divergence computed within one
        # contact, so it is dimensionless and invariant to that contact's gain.
        # Reporting False would assert that a baseline step exists and was
        # skipped. G2 returns None on an unset field, which is the honest answer
        # to a question that does not apply.
        #
        # What this does not cover, and a reader comparing contacts should know:
        # MI is invariant to gain but not to signal-to-noise. A noisier contact
        # reads lower, and no guardrail will say so for this recipe.
        **_shared_guardrail_context(session, params),
    }


@recipe(
    NAME,
    "Phase-amplitude coupling per derivation and condition, by pactools "
    "Comodulogram, with surrogate correction and the waveform-shape caveat "
    "stated on every result.",
    PacParams,
    version="1",
)
def pac_modulation_index(ctx: RecipeContext) -> RecipeResult:
    params: PacParams = ctx.params
    session = ctx.session

    lead_ids = params.leads or list(session.leads())
    conditions = params.conditions or list(session.conditions())
    schemes = params.references or list(available_schemes())

    phase_fqs = _phase_range(params)
    amp_fqs = _amplitude_range(params)
    if phase_fqs.size == 0 or amp_fqs.size == 0:
        raise RuntimeError(
            "empty frequency range: check phase_fq_* and amplitude_fq_* parameters"
        )

    nyquist = params.sfreq_target_hz / 2.0
    if float(amp_fqs.max()) >= nyquist:
        raise RuntimeError(
            f"amplitude range reaches {amp_fqs.max():.0f} Hz, at or above Nyquist "
            f"({nyquist:.0f} Hz) for sfreq_target_hz={params.sfreq_target_hz}. "
            "Raise sfreq_target_hz or lower amplitude_fq_max_hz."
        )

    phase_bins_overlap = params.phase_fq_width_hz > params.phase_fq_step_hz
    if phase_bins_overlap:
        ctx.log(
            f"phase_fq_width_hz ({params.phase_fq_width_hz}) exceeds "
            f"phase_fq_step_hz ({params.phase_fq_step_hz}), so adjacent phase "
            "bins overlap and the phase frequency of any peak is not resolved"
        )

    rows: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    ctx.log(
        f"leads={lead_ids} conditions={conditions} method={params.method} "
        f"phase={phase_fqs.min()}-{phase_fqs.max()}Hz "
        f"amplitude={amp_fqs.min()}-{amp_fqs.max()}Hz "
        f"surrogates={params.n_surrogates}"
    )

    for lead_id in lead_ids:
        lead = session.leads()[lead_id]
        for scheme in schemes:
            for condition in conditions:
                for t0, t1, window in _windows_for(ctx, condition):
                    reason = _too_short(t1 - t0, params)
                    if reason is not None:
                        skipped.append(
                            {"lead_id": lead_id, "scheme": scheme,
                             "condition": condition, "reason": reason}
                        )
                        ctx.log(f"skipped {lead_id}/{scheme}/{condition}: {reason}")
                        continue

                    sig = session.read_derived(
                        lead_id, scheme, tmin=t0, tmax=t1,
                        sfreq_target_hz=params.sfreq_target_hz,
                    )
                    for i, name in enumerate(sig.names):
                        raw, corrected = _comodulogram(
                            sig.data[i], sig.sfreq_hz, params
                        )
                        peak = np.unravel_index(int(np.argmax(raw)), raw.shape)
                        rows.append({
                            "study_id": session.study_id,
                            "lead_id": lead_id,
                            "target": lead.target,
                            "scheme": scheme,
                            "derivation": name,
                            "row": sig.rows[i],
                            "condition": condition,
                            "window_status": window.get("status", ""),
                            "method": params.method,
                            "peak_phase_hz": float(phase_fqs[peak[0]]),
                            "peak_amplitude_hz": float(amp_fqs[peak[1]]),
                            "peak_mi": float(raw[peak]),
                            "peak_mi_z": (
                                float(corrected[peak]) if corrected is not None else None
                            ),
                            "mean_mi": float(raw.mean()),
                            "surrogates": params.n_surrogates,
                        })

    if not rows:
        raise RuntimeError(
            "no comodulogram computed. Every window was too short for the "
            "configured phase range, or the manifest defines no windows."
        )

    long = pd.DataFrame(rows)
    out = ctx.out_dir
    long.to_parquet(out / "pac_long.parquet", index=False)
    long.to_csv(out / "pac_summary.csv", index=False)

    caveats = [
        "A non-sinusoidal waveform produces harmonics that read as coupling. "
        "This is a confound of the measurement, not an artifact to correct, so "
        "inspect the raw waveform before claiming coupling.",
        f"Estimator is {params.method!r}; the estimators disagree on the same "
        "data and a different one may not reproduce this.",
    ]
    if phase_bins_overlap:
        caveats.append(
            f"phase_fq_width_hz ({params.phase_fq_width_hz}) is wider than "
            f"phase_fq_step_hz ({params.phase_fq_step_hz}), so adjacent phase "
            "bins overlap. The amplitude frequency of a peak is still "
            "meaningful; its phase frequency is not resolved."
        )
    if not params.n_surrogates:
        caveats.append(
            "n_surrogates is 0, so every modulation index here is uncorrected "
            "and positive values are expected from noise alone."
        )

    summary = {
        "recipe": NAME,
        "method": params.method,
        "phase_fq_hz": [float(phase_fqs.min()), float(phase_fqs.max())],
        "amplitude_fq_hz": [float(amp_fqs.min()), float(amp_fqs.max())],
        "n_surrogates": params.n_surrogates,
        "n_derivations": int(long["derivation"].nunique()),
        "conditions": sorted(long["condition"].unique().tolist()),
        "skipped_windows": skipped,
        "caveats": caveats,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))

    return RecipeResult(
        tables={"pac_long": long},
        figures=[],
        summary=summary,
    )


pac_modulation_index.guardrail_context = guardrail_context
pac_modulation_index.option_explanations = options_for_schema
