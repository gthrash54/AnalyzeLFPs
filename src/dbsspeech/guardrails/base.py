"""Guardrail types.

A guardrail asks whether the analysis about to run answers the question it claims
to. That is a different question from QC, which asks whether the signal is usable.

Three rules the engine enforces, from docs/guardrails.md:

- A guardrail explains. The message says what was detected, why it matters, and
  what to do instead. A bare refusal teaches nothing.
- A guardrail can be overridden, and the override is recorded in the run record
  with its reason. Silent overrides defeat the purpose.
- Only `block` stops a run, and only where the result would be actively
  misleading rather than merely suboptimal. Three checks are not overridable at
  all, because they are arithmetic rather than judgment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Severity(StrEnum):
    BLOCK = "block"
    WARN = "warn"
    NOTE = "note"
    OFF = "off"


@dataclass(frozen=True)
class Finding:
    """One guardrail firing on one run."""

    guardrail: str
    severity: Severity
    message: str
    detail: dict[str, Any] = field(default_factory=dict)
    remedy: str = ""
    overridable: bool = True

    def describe(self) -> str:
        head = f"[{self.severity.value}] {self.guardrail}: {self.message}"
        if self.remedy:
            head += f"\n    what to do: {self.remedy}"
        for key, value in self.detail.items():
            head += f"\n    {key}: {value}"
        if self.severity is Severity.BLOCK:
            head += (
                f"\n    override: pass overrides={{'{self.guardrail}': '<your reason>'}}"
                if self.overridable
                else "\n    NOT overridable: this is arithmetic, not a judgment call."
            )
        return head


@dataclass(frozen=True)
class Override:
    """A deliberate decision to proceed past a guardrail."""

    guardrail: str
    reason: str

    def __post_init__(self) -> None:
        if not self.reason or not self.reason.strip():
            raise ValueError(
                f"override of {self.guardrail!r} needs a reason; an unexplained "
                "override is indistinguishable from not having the check"
            )


class GuardrailBlocked(Exception):
    """Raised when a blocking guardrail fires and was not overridden."""

    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        body = "\n\n".join(f.describe() for f in findings)
        n = len(findings)
        super().__init__(
            f"{n} blocking guardrail{'s' if n != 1 else ''} fired. "
            f"Nothing was computed.\n\n{body}"
        )


@dataclass
class CheckContext:
    """What a guardrail needs to know about the run about to happen.

    Deliberately a flat bag rather than a typed hierarchy: checks are added over
    time and each needs a different slice, so a check reads the keys it cares
    about and ignores the rest. A check that finds nothing to inspect returns no
    finding rather than guessing.
    """

    recipe: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    reference_scheme: str | None = None
    reference_is_shared: bool | None = None
    sfreq_hz: float | None = None
    usable_bandwidth_hz: float | None = None
    requested_bands: dict[str, tuple[float, float]] = field(default_factory=dict)
    window_s: float | None = None
    claimed_event_duration_s: float | None = None
    conditions: tuple[str, ...] = ()
    window_rows: list[dict[str, Any]] = field(default_factory=list)
    reports_db: bool | None = None
    reports_z: bool | None = None
    baseline_is_smoothed: bool | None = None
    per_contact_baseline_subtracted: bool | None = None

    # G3: whether a ratio or contrast is formed per channel before averaging.
    ratio_before_average: bool | None = None
    # G4: whether a structural threshold was set within each condition.
    threshold_within_condition: bool | None = None
    # G7: whether an EMG channel exists and was regressed out.
    emg_available: bool | None = None
    emg_regressed: bool | None = None
    # G9: the largest spontaneous excursion, and the effect being reported.
    # `recording_duration_s` is not used to decide whether G9 fires. It is
    # carried so the ratio can be reported with the duration beside it, because
    # the ratio is not comparable between recordings of different lengths: under
    # a random-walk baseline the excursion grows as sqrt(duration), measured in
    # curriculum/10_stochastic/03_random_walks_and_spurious_correlation.
    max_excursion_db: float | None = None
    reported_effect_db: float | None = None
    recording_duration_s: float | None = None
    # G13: paths this run would write into its outputs or record.
    paths_in_outputs: tuple[str, ...] = ()
    filenames_deidentified: bool | None = None

    extra: dict[str, Any] = field(default_factory=dict)
