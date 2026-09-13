"""Proposing condition windows from the task markers in a recording.

There are no task markers in the recordings this project started with, so every
window in `windows.csv` was derived by hand from a microphone envelope and an
EMG trace. Formats that carry their own triggers, BrainVision and EDF+, make
part of that mechanical: a marker already says when something happened, and the
only open question is what it meant and how far the window extends.

This module answers neither of those on its own. It reads the bindings a lab
declares in `configs/markers.yaml`, applies them, and returns proposals with the
evidence attached, in the same "propose, never decide" shape the layout
detectors use. Nothing is written to a manifest. An unbound marker label is
reported as unbound rather than guessed at, because a wrong condition label
produces a result that looks right.

The window extent is the part that cannot be inferred, so it is named per
binding and travels into the proposal:

    until_next   onset to the next marker of any label, end of recording for
                 the last. Suits block designs and invents no constant.
    fixed_s      onset plus a stated number of seconds, for trial designs.
    annotation   the marker's own onset and offset from the file.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..io.base import Recording
from .base import MEDIUM, Proposal, ProposalSet

UNTIL_NEXT = "until_next"
FIXED = "fixed_s"
ANNOTATION = "annotation"

DEFAULT_MIN_DURATION_S = 0.5

# A binding that matches more markers than this is describing trials, not
# conditions. Real recordings carry per-trial trigger streams with thousands of
# events beside a handful of block markers, and treating those as conditions
# produces thousands of overlapping rows that no one can review and that mean
# nothing as a contrast. Trial structure belongs to an epoching recipe.
DEFAULT_MAX_EVENTS_PER_BINDING = 200

# Fields of a proposed windows.csv row, in the order the file declares them.
WINDOW_COLUMNS = (
    "study_id",
    "session",
    "condition",
    "t_start_s",
    "t_end_s",
    "derived_from",
    "status",
    "notes",
)


@dataclass(frozen=True)
class _Binding:
    pattern: str
    condition: str
    extent: str
    fixed_s: float | None = None
    note: str = ""


def _bindings(config: dict[str, Any]) -> list[_Binding]:
    """Bindings, longest pattern first so a specific code outranks a general one."""
    default_extent = str(config.get("default_extent", UNTIL_NEXT))
    out: list[_Binding] = []
    for raw in config.get("bindings") or []:
        if not isinstance(raw, dict):
            continue
        pattern = str(raw.get("pattern", "")).strip()
        condition = str(raw.get("condition", "")).strip()
        if not pattern or not condition:
            continue
        extent_spec = raw.get("extent", default_extent)
        extent, fixed_s = _parse_extent(extent_spec, default_extent)
        out.append(
            _Binding(pattern, condition, extent, fixed_s, str(raw.get("note", "")))
        )
    out.sort(key=lambda b: len(b.pattern), reverse=True)
    return out


def _parse_extent(spec: Any, default: str) -> tuple[str, float | None]:
    """Accept `until_next`, `annotation`, or `{fixed_s: N}`."""
    if isinstance(spec, dict):
        if FIXED in spec:
            return FIXED, float(spec[FIXED])
        # A mapping naming anything else is a config error worth surfacing as a
        # fallback to the default rather than a crash mid-proposal.
        return default, None
    text = str(spec)
    if text in (UNTIL_NEXT, ANNOTATION):
        return text, None
    return default, None


def _boundary_onsets(recording: Recording, labels: set[str]) -> list[float]:
    """Onsets that may end a window, sorted.

    Only labels bound to a condition and not rejected as trial-dense count. Two
    kinds of marker must not chop a block: one nobody has declared a meaning
    for, and a per-trial trigger firing thousands of times. Including either
    collapses every block window to the millisecond gap before the next tick,
    which is how the first version of this silently discarded every real window
    on the one recording it was tested against.
    """
    onsets = [
        float(onset)
        for label, series in recording.epochs.items()
        if label in labels
        for onset in series.onsets
    ]
    return sorted(onsets)


def _recording_end_s(recording: Recording) -> float:
    durations = [info.duration_s for info in recording.streams.values()]
    return max(durations) if durations else 0.0


def propose_windows(
    recording: Recording,
    study_id: str,
    session: str,
    config: dict[str, Any] | None = None,
) -> ProposalSet:
    """Propose `windows.csv` rows from the markers in `recording`.

    `config` is the parsed `configs/markers.yaml`. Returns a `ProposalSet`; the
    caller decides what to do with it, and nothing here touches a manifest.
    """
    config = config or {}
    out = ProposalSet()

    epochs = recording.epochs
    if not epochs:
        out.add(
            Proposal(
                field="window",
                value=None,
                confidence=0.0,
                detectable=False,
                reason=(
                    "this recording carries no task markers, so windows must be "
                    "derived from a signal instead"
                ),
            )
        )
        return out

    bindings = _bindings(config)
    min_duration = float(config.get("min_duration_s", DEFAULT_MIN_DURATION_S))
    max_events = int(config.get("max_events_per_binding", DEFAULT_MAX_EVENTS_PER_BINDING))
    end_s = _recording_end_s(recording)

    # Resolve every label to its binding first. Which labels are usable has to
    # be settled before any window is cut, because a trial-dense label must not
    # act as a boundary for the block labels either.
    matched: dict[str, _Binding] = {}
    for label in sorted(epochs):
        binding = next((b for b in bindings if b.pattern in label), None)
        if binding is not None:
            matched[label] = binding

    dense = {
        label for label, _ in matched.items() if len(epochs[label]) > max_events
    }
    for label in sorted(dense):
        out.add(
            Proposal(
                field="window",
                value=matched[label].condition,
                confidence=0.0,
                detectable=False,
                evidence={"marker": label, "n_events": len(epochs[label])},
                reason=(
                    f"{len(epochs[label])} events exceeds max_events_per_binding "
                    f"({max_events}), so this label marks trials rather than a "
                    "condition; windows.csv describes conditions, and trial "
                    "structure belongs to an epoching recipe"
                ),
            )
        )

    usable = set(matched) - dense
    every_onset = _boundary_onsets(recording, usable)

    bound_labels: set[str] = set(matched)
    for label in sorted(usable):
        series = epochs[label]
        binding = matched[label]
        for index in range(len(series)):
            start = float(series.onsets[index])
            stop = _extent_end(binding, series, index, every_onset, end_s)
            if stop is None:
                continue
            if stop - start < min_duration:
                out.add(
                    Proposal(
                        field="window",
                        value=binding.condition,
                        confidence=0.0,
                        detectable=True,
                        evidence={
                            "marker": label,
                            "t_start_s": round(start, 3),
                            "t_end_s": round(stop, 3),
                            "rule": binding.extent,
                        },
                        reason=(
                            f"shorter than min_duration_s ({min_duration} s), so it "
                            "reads as a trigger artifact rather than a condition"
                        ),
                    )
                )
                continue
            out.add(
                Proposal(
                    field="window",
                    value=binding.condition,
                    # A bound marker measures when something happened, but
                    # what it meant is the lab's declaration, not a detection.
                    # Deliberately below prefill: a person confirms the binding
                    # once, in the config, and the rows stay draft regardless.
                    confidence=MEDIUM,
                    evidence={
                        "marker": label,
                        "t_start_s": round(start, 3),
                        "t_end_s": round(stop, 3),
                        "rule": _rule_text(binding),
                        "row": _row(study_id, session, binding, start, stop, label),
                    },
                    reason=binding.note or f"marker {label!r} is bound to {binding.condition!r}",
                )
            )

    unbound = sorted(set(epochs) - bound_labels)
    for label in unbound:
        out.add(
            Proposal(
                field="marker",
                value=label,
                confidence=0.0,
                detectable=False,
                evidence={"n_events": len(epochs[label])},
                reason=(
                    "no binding in configs/markers.yaml names this label, so what "
                    "it means is undeclared and no window is proposed"
                ),
            )
        )
    return out


def _rule_text(binding: _Binding) -> str:
    if binding.extent == FIXED:
        return f"fixed_s={binding.fixed_s}"
    return binding.extent


def _extent_end(
    binding: _Binding,
    series: Any,
    index: int,
    every_onset: list[float],
    end_s: float,
) -> float | None:
    """Where the window ends, or None when this rule proposes nothing here."""
    start = float(series.onsets[index])

    if binding.extent == FIXED and binding.fixed_s:
        return start + float(binding.fixed_s)

    if binding.extent == ANNOTATION:
        offsets = getattr(series, "offsets", None)
        if offsets is None or index >= len(offsets):
            return None
        stop = float(offsets[index])
        # A zero-length annotation is an instant, not a window. Saying so is
        # better than silently widening it to something invented.
        return stop if stop > start else None

    # until_next: the next onset of any label, else the end of the recording.
    later = [o for o in every_onset if o > start]
    return min(later) if later else (end_s if end_s > start else None)


def _row(
    study_id: str,
    session: str,
    binding: _Binding,
    start: float,
    stop: float,
    label: str,
) -> dict[str, Any]:
    """A proposed `windows.csv` row.

    `derived_from` is `task_marker` and `status` is `draft`, both already in
    configs/vocabularies.yaml. Draft is the point: a proposal that entered the
    manifest as `in_use` would be indistinguishable from a reviewed window.
    """
    return {
        "study_id": study_id,
        "session": session,
        "condition": binding.condition,
        "t_start_s": round(start, 3),
        "t_end_s": round(stop, 3),
        "derived_from": "task_marker",
        "status": "draft",
        "notes": f"proposed from marker {label!r} by {_rule_text(binding)}",
    }


def proposed_rows(proposals: ProposalSet) -> list[dict[str, Any]]:
    """The `windows.csv` rows in a proposal set, in recording order."""
    rows = [
        p.evidence["row"]
        for p in proposals.proposals
        if p.field == "window" and "row" in p.evidence
    ]
    return sorted(rows, key=lambda r: (r["t_start_s"], r["condition"]))


__all__ = [
    "ANNOTATION",
    "FIXED",
    "UNTIL_NEXT",
    "WINDOW_COLUMNS",
    "proposed_rows",
    "propose_windows",
]
