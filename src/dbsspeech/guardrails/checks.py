"""The checks themselves.

Each returns a `Finding` when it fires and `None` when it does not, or when the
context does not carry enough information to judge. A check that cannot see what
it needs stays quiet rather than guessing; guessing here would either block valid
work or give false assurance.

Severity comes from `configs/guardrails.yaml`, not from these functions. A check
decides whether something is true, the config decides how much it matters.

Numbered to match docs/guardrails.md.
"""

from __future__ import annotations

from typing import Any

from .base import CheckContext, Finding, Severity
from .engine import register_check

# Placeholder severity: the engine replaces it with the configured value.
_S = Severity.WARN


@register_check("G1_shared_reference_common_mode")
def shared_reference(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """A monopolar montage on a shared reference makes common mode look like signal."""
    if ctx.reference_scheme is None:
        return None
    if ctx.reference_scheme != "monopolar":
        return None
    if ctx.reference_is_shared is False:
        return None
    return Finding(
        guardrail="G1_shared_reference_common_mode",
        severity=_S,
        message=(
            "monopolar requested on a shared-reference recording, so any common-mode "
            "signal will appear as an effect on every channel at once"
        ),
        detail={
            "reference_scheme": ctx.reference_scheme,
            "shared_reference": ctx.reference_is_shared,
        },
        remedy=(
            "use a bipolar montage (bipolar_vertical preserves per-segment identity). "
            "Keep monopolar only for a deliberate montage comparison."
        ),
    )


@register_check("G5_window_longer_than_phenomenon")
def window_too_long(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """An analysis window much longer than the event cannot resolve it."""
    if ctx.window_s is None or not ctx.claimed_event_duration_s:
        return None
    ratio_max = float(spec.get("max_window_to_event_ratio", 5.0))
    ratio = ctx.window_s / ctx.claimed_event_duration_s
    if ratio <= ratio_max:
        return None
    return Finding(
        guardrail="G5_window_longer_than_phenomenon",
        severity=_S,
        message=(
            f"the {ctx.window_s} s analysis window is {ratio:.0f}x the "
            f"{ctx.claimed_event_duration_s} s event being claimed, so it integrates "
            "over many of them and cannot resolve one"
        ),
        detail={"window_s": ctx.window_s, "event_s": ctx.claimed_event_duration_s,
                "ratio": round(ratio, 1), "max_ratio": ratio_max},
        remedy=(
            "shorten the window, or use a wavelet or filter-bank method for any "
            "burst-level claim"
        ),
    )


@register_check("G6_decimation_removes_claimed_band")
def band_above_cutoff(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """Refuse to report a band the anti-alias filter removed."""
    if ctx.usable_bandwidth_hz is None or not ctx.requested_bands:
        return None
    offenders = {
        name: (lo, hi)
        for name, (lo, hi) in ctx.requested_bands.items()
        if hi > ctx.usable_bandwidth_hz
    }
    if not offenders:
        return None
    return Finding(
        guardrail="G6_decimation_removes_claimed_band",
        severity=_S,
        message=(
            f"{len(offenders)} requested band(s) reach above the usable bandwidth of "
            f"{ctx.usable_bandwidth_hz:.0f} Hz, where the anti-alias filter has already "
            "removed the content"
        ),
        detail={
            "usable_bandwidth_hz": round(ctx.usable_bandwidth_hz, 1),
            "sfreq_hz": ctx.sfreq_hz,
            "bands_above_cutoff": offenders,
        },
        remedy=(
            "decimate less, or drop those bands. Usable bandwidth is 0.4 x the "
            "sampling rate, not the Nyquist frequency."
        ),
        overridable=False,
    )


@register_check("G8_db_without_z")
def db_without_z(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """dB alone lets dynamic range read as effect size."""
    if not spec.get("require_z_alongside_db", True):
        return None
    if ctx.reports_db is None:
        return None
    if not ctx.reports_db or ctx.reports_z:
        return None
    return Finding(
        guardrail="G8_db_without_z",
        severity=_S,
        message=(
            "result reports dB without a z-score against its own baseline, so band "
            "differences in absolute power will read as differences in effect size"
        ),
        detail={"reports_db": ctx.reports_db, "reports_z": ctx.reports_z},
        remedy="report both. Low-frequency dominance that collapses under z was never an effect.",
    )


@register_check("G10_window_provenance")
def window_provenance(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """Flag windows that were assumed, or are known to be under revision."""
    if not ctx.window_rows:
        return None
    flag_sources = set(spec.get("flag_derived_from", ["assumed"]))
    flag_status = set(spec.get("flag_status", ["draft", "under_revision"]))
    suspect = [
        {
            "condition": r.get("condition"),
            "derived_from": r.get("derived_from"),
            "status": r.get("status"),
        }
        for r in ctx.window_rows
        if r.get("derived_from") in flag_sources or r.get("status") in flag_status
    ]
    if not suspect:
        return None
    return Finding(
        guardrail="G10_window_provenance",
        severity=_S,
        message=(
            f"{len(suspect)} window(s) used by this run are assumed or under revision, "
            "so any result depending on them inherits that"
        ),
        detail={"windows": suspect},
        remedy=(
            "re-derive the window from the microphone, EMG, or video, and set "
            "derived_from accordingly. Until then the result carries this flag."
        ),
    )


@register_check("G11_control_condition_missing")
def control_condition_missing(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """A claim analyzed without the control condition that would rule out its confound.

    One rule per confound, all declared in configs/guardrails.yaml, because
    which control a claim needs is a fact about a paradigm and not about this
    code. The original rule, that a speech claim needs a movement-only control,
    is now one entry among several rather than the only shape the check can
    take.

    Every rule is evaluated and all that fire are reported together. Returning
    only the first would hide the second confound until the first was fixed,
    which is the wrong number of review cycles.
    """
    if not ctx.conditions:
        return None

    used = set(ctx.conditions)
    fired: list[dict[str, Any]] = []
    for rule in _control_rules(spec):
        applies = set(rule.get("applies_to_conditions") or ())
        satisfying = set(rule.get("satisfying_conditions") or ())
        if not applies or not (used & applies):
            continue
        if satisfying & used:
            continue
        fired.append(
            {
                "claim": sorted(used & applies),
                "would_satisfy": sorted(satisfying),
                "because": rule.get("because", ""),
            }
        )

    if not fired:
        return None

    reasons = "; ".join(r["because"] for r in fired if r["because"])
    satisfying_all = sorted({s for r in fired for s in r["would_satisfy"]})
    return Finding(
        guardrail="G11_control_condition_missing",
        severity=_S,
        message=(
            f"{len(fired)} claim(s) are analyzed without a control condition that "
            f"would rule out a confound: {reasons}"
            if reasons
            else "a claim is analyzed without the control condition it needs"
        ),
        detail={"conditions": sorted(used), "unmet": fired},
        remedy=(
            f"include one of {satisfying_all}, or state the limitation on the figure"
        ),
    )


def _control_rules(spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Rules from the config, accepting the single-rule form this check began as.

    The original spec named `applies_to_conditions` and `satisfying_conditions`
    at the top level. A config written that way keeps working and is read as one
    rule, so generalizing the check does not silently disarm an installation
    that has not been updated.
    """
    rules = spec.get("rules")
    if isinstance(rules, list) and rules:
        return [r for r in rules if isinstance(r, dict)]
    if spec.get("applies_to_conditions") or spec.get("satisfying_conditions"):
        return [
            {
                "applies_to_conditions": spec.get("applies_to_conditions") or (),
                "satisfying_conditions": spec.get("satisfying_conditions") or (),
                "because": spec.get("because", ""),
            }
        ]
    return []


@register_check("G12_baseline_on_smoothed_data")
def smoothed_baseline(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """Smoothing before estimating a baseline narrows it and inflates every z."""
    if not ctx.baseline_is_smoothed:
        return None
    return Finding(
        guardrail="G12_baseline_on_smoothed_data",
        severity=_S,
        message=(
            "baseline statistics are being computed on smoothed data, which narrows "
            "the baseline distribution and inflates every z-score derived from it"
        ),
        detail={"baseline_is_smoothed": True},
        remedy="compute baseline mean and standard deviation on unsmoothed data",
        overridable=False,
    )


@register_check("G2_effect_tracks_electrode_not_state")
def missing_baseline_subtraction(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """Per-contact comparisons need a per-contact baseline subtracted first."""
    if ctx.per_contact_baseline_subtracted is None:
        return None
    if ctx.per_contact_baseline_subtracted:
        return None
    return Finding(
        guardrail="G2_effect_tracks_electrode_not_state",
        severity=_S,
        message=(
            "a per-contact comparison is running without a per-contact baseline "
            "subtracted, so it will measure which contact sits best rather than what "
            "the brain is doing"
        ),
        detail={"per_contact_baseline_subtracted": False},
        remedy="subtract each contact's baseline-condition value before comparing contacts",
    )


@register_check("G3_ratio_before_average")
def ratio_before_average(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """Averaging power then taking the ratio is a different quantity."""
    if ctx.ratio_before_average is None or ctx.ratio_before_average:
        return None
    return Finding(
        guardrail="G3_ratio_before_average",
        severity=_S,
        message=(
            "a ratio or contrast is being formed after averaging across channels, "
            "which by Jensen's inequality is not the same quantity as the average "
            "of the per-channel ratios, and is not the one anyone means"
        ),
        detail={"ratio_before_average": False},
        remedy="compute the ratio per channel first, then average across channels",
        overridable=False,
    )


@register_check("G4_threshold_across_conditions")
def threshold_across_conditions(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """A shared threshold turns an amplitude difference into a fake structural one."""
    if not spec.get("require_within_condition_threshold", True):
        return None
    if ctx.threshold_within_condition is None or ctx.threshold_within_condition:
        return None
    return Finding(
        guardrail="G4_threshold_across_conditions",
        severity=_S,
        message=(
            "a single threshold is applied across conditions while comparing "
            "structure, so a condition with larger amplitude will appear to have "
            "different structure when only its amplitude differs"
        ),
        detail={"threshold_within_condition": False},
        remedy="set the threshold within each condition before comparing occupancy or duration",
    )


@register_check("G7_emg_contamination_in_high_band")
def emg_contamination(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """Speech EMG lives where raising the sampling rate opens the band up."""
    if not ctx.requested_bands or not ctx.conditions:
        return None
    applies = set(spec.get("escalate_only_for_conditions", ["overt"]))
    if not (set(ctx.conditions) & applies):
        return None

    emg_lo, emg_hi = spec.get("emg_band_hz", [100.0, 1000.0])
    overlapping = {
        name: (lo, hi)
        for name, (lo, hi) in ctx.requested_bands.items()
        if hi > emg_lo and lo < emg_hi
    }
    if not overlapping:
        return None

    bipolar = (ctx.reference_scheme or "").startswith("bipolar")
    if bipolar and ctx.emg_regressed:
        return None

    remedies = []
    if not bipolar:
        remedies.append("use a bipolar montage")
    if ctx.emg_available and not ctx.emg_regressed:
        remedies.append("regress the EMG channels out")
    elif not ctx.emg_available:
        remedies.append("no EMG channel is included, so contamination cannot be measured")
    return Finding(
        guardrail="G7_emg_contamination_in_high_band",
        severity=_S,
        message=(
            f"{len(overlapping)} requested band(s) overlap the speech EMG range "
            f"({emg_lo:.0f} to {emg_hi:.0f} Hz) during a speech condition, so muscle "
            "activity can appear as neural signal"
        ),
        detail={"overlapping_bands": overlapping, "reference_scheme": ctx.reference_scheme,
                "emg_available": ctx.emg_available, "emg_regressed": ctx.emg_regressed},
        remedy="; ".join(remedies) or "confirm the contamination has been addressed",
    )


@register_check("G9_nonstationarity_exceeds_effect")
def nonstationarity(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """If the biggest thing in the recording is not the manipulation, say so."""
    if ctx.max_excursion_db is None or not ctx.reported_effect_db:
        return None
    ratio_min = float(spec.get("excursion_to_effect_ratio", 1.0))
    ratio = abs(ctx.max_excursion_db) / abs(ctx.reported_effect_db)
    if ratio < ratio_min:
        return None
    # The ratio alone is not comparable between runs, so report the duration it
    # was measured over. An excursion grows with recording length whenever the
    # baseline is closer to a random walk than to a bounded process, so the same
    # physiology yields a larger ratio in a longer recording.
    over = (f" over {ctx.recording_duration_s:.0f} s of recording"
            if ctx.recording_duration_s else "")
    detail = {"max_excursion_db": ctx.max_excursion_db,
              "reported_effect_db": ctx.reported_effect_db, "ratio": round(ratio, 2),
              "recording_duration_s": ctx.recording_duration_s}
    return Finding(
        guardrail="G9_nonstationarity_exceeds_effect",
        severity=_S,
        message=(
            f"the largest spontaneous excursion in this recording is "
            f"{abs(ctx.max_excursion_db):.1f} dB, which is {ratio:.1f}x the reported "
            f"effect of {abs(ctx.reported_effect_db):.1f} dB{over}"
        ),
        detail=detail,
        remedy=(
            "the contrast needs a stability argument: show the effect is not a "
            "spontaneous excursion that happens to align with a condition. "
            "Compare the ratio only against runs of similar duration: the "
            "excursion grows with recording length"
        ),
    )


@register_check("G13_path_and_filename_policy")
def path_policy(ctx: CheckContext, spec: dict[str, Any]) -> Finding | None:
    """Raw paths must not reach a derivative unless the site says they are safe."""
    if not ctx.paths_in_outputs:
        return None
    if ctx.filenames_deidentified:
        return None
    return Finding(
        guardrail="G13_path_and_filename_policy",
        severity=_S,
        message=(
            f"{len(ctx.paths_in_outputs)} raw path(s) would be written into this "
            "run's outputs or record, and configs/privacy.yaml does not declare "
            "filenames de-identified at this site"
        ),
        detail={"paths": list(ctx.paths_in_outputs)[:5],
                "filenames_deidentified": ctx.filenames_deidentified},
        remedy=(
            "refer to the recording by its manifest key (study_id, session, "
            "acquisition), or set filenames_deidentified in configs/privacy.yaml "
            "if your export naming has been confirmed safe"
        ),
        overridable=False,
    )
