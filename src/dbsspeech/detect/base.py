"""The proposal type every detector returns."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# Confidence bands, per configs/layout_detection.yaml.
HIGH, MEDIUM, LOW = 0.9, 0.6, 0.0


@dataclass(frozen=True)
class Proposal:
    """One thing a detector believes, with its reasons.

    `detectable` is False for facts no signal can establish, such as which
    nucleus a lead sits in. Those are presented as a ranked choice with the
    reason detection cannot settle them, never as a guess.
    """

    field: str
    value: Any
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    alternatives: tuple[Any, ...] = ()
    detectable: bool = True
    reason: str = ""

    @property
    def band(self) -> str:
        if not self.detectable:
            return "not detectable"
        if self.confidence >= HIGH:
            return "high"
        return "medium" if self.confidence >= MEDIUM else "low"

    @property
    def prefill(self) -> bool:
        """Whether the interface should pre-select this value."""
        return self.detectable and self.confidence >= HIGH

    def describe(self) -> str:
        """One line a person can act on. This is the troubleshooting surface."""
        head = f"{self.field}: {self.value!r} ({self.band}"
        head += f" {self.confidence:.2f})" if self.detectable else ")"
        if self.alternatives:
            head += f"  alternatives: {list(self.alternatives)}"
        if self.reason:
            head += f"\n    {self.reason}"
        for key, val in self.evidence.items():
            head += f"\n    {key}: {val}"
        return head


@dataclass
class ProposalSet:
    """Everything detection concluded about one recording."""

    proposals: list[Proposal] = field(default_factory=list)

    def add(self, proposal: Proposal) -> None:
        self.proposals.append(proposal)

    def by_field(self, name: str) -> list[Proposal]:
        return [p for p in self.proposals if p.field == name]

    def needs_selection(self) -> list[Proposal]:
        """Proposals a person must resolve: undetectable, or below prefill."""
        return [p for p in self.proposals if not p.prefill]

    def report(self) -> str:
        return "\n".join(p.describe() for p in self.proposals)
