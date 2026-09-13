"""Lead geometry and contact quality, from the hardware's own impedance export.

Segment contacts have roughly half a ring contact's surface area, so they read
proportionally higher impedance. A directional lead therefore shows a
low-high-high-low pattern down the shank, which fixes both the geometry and the
ventral-to-dorsal ordering.

What this establishes and what it cannot:

- Geometry: yes. Ring versus segment is a physical property the measurement sees.
- Vendor: no. Several manufacturers ship the same 1-3-3-1 geometry with different
  contact numbering, so every model whose geometry fits is offered and a person
  picks. Guessing here mislabels every figure downstream.
- Target, hemisphere, rotation: no. Surgical and imaging facts, not properties of
  a measurement.
"""

from __future__ import annotations

from typing import Any

from ..io.impedance import ImpedanceSweep
from .base import HIGH, MEDIUM, Proposal

RING, SEGMENT = "ring", "segment"

# Defaults, overridden by configs/layout_detection.yaml and qc_thresholds.
DEFAULT_SEGMENT_RATIO_MIN = 1.5
DEFAULT_OPEN_CIRCUIT_KOHM = 100.0
DEFAULT_HIGH_IMPEDANCE_KOHM = 25.0


def classify_contacts(
    sweep: ImpedanceSweep,
    first: int,
    last: int,
    segment_ratio_min: float = DEFAULT_SEGMENT_RATIO_MIN,
) -> list[str]:
    """Label each contact in ``[first, last]`` as ring or segment.

    Uses the minimum impedance in the span as the ring reference, because a lead
    always has at least one ring and rings read lowest. A contact at or above
    `segment_ratio_min` times that reference is a segment.
    """
    values = [sweep.values.get(c) for c in range(first, last + 1)]
    present = [v for v in values if v is not None]
    if not present:
        return []
    ring_reference = min(present)
    out: list[str] = []
    for v in values:
        if v is None:
            out.append("unknown")
        else:
            out.append(SEGMENT if v >= ring_reference * segment_ratio_min else RING)
    return out


def geometry_from_labels(labels: list[str]) -> list[int]:
    """Collapse a contact labeling into the geometry shorthand, ventral to dorsal.

    ``[ring, seg, seg, seg, seg, seg, seg, ring]`` becomes ``[1, 3, 3, 1]``:
    rings are their own row, and a run of segments splits into rows of three.
    """
    out: list[int] = []
    run = 0
    for label in labels:
        if label == SEGMENT:
            run += 1
            continue
        if run:
            out.extend(_split_segment_run(run))
            run = 0
        out.append(1)
    if run:
        out.extend(_split_segment_run(run))
    return out


def _split_segment_run(n: int) -> list[int]:
    """A run of segments is rows of three; anything else is reported as it is."""
    if n % 3 == 0:
        return [3] * (n // 3)
    return [n]


def propose_lead_models(
    sweep: ImpedanceSweep,
    first: int,
    last: int,
    leads_config: dict[str, Any],
    segment_ratio_min: float = DEFAULT_SEGMENT_RATIO_MIN,
) -> Proposal:
    """Offer every configured lead model whose geometry matches the measurement."""
    labels = classify_contacts(sweep, first, last, segment_ratio_min)
    geometry = geometry_from_labels(labels)
    n_contacts = last - first + 1

    models = (leads_config or {}).get("leads") or {}
    matches = [
        key
        for key, spec in models.items()
        if spec.get("geometry") == geometry and spec.get("n_contacts") == n_contacts
    ]
    # When several vendors share this geometry, the measurement cannot choose
    # between them, so the proposed value is the honest placeholder and the
    # specific vendors are the alternatives. Proposing a named vendor here would
    # mislabel every figure downstream on nothing more than alphabetical order.
    placeholders = [k for k in matches if k.startswith("unknown")]
    specific = sorted(k for k in matches if not k.startswith("unknown"))

    values = [sweep.values.get(c) for c in range(first, last + 1)]
    rings = [v for v, label in zip(values, labels, strict=False) if label == RING and v]
    segs = [v for v, label in zip(values, labels, strict=False) if label == SEGMENT and v]
    evidence: dict[str, Any] = {
        "channels": f"{first}-{last}",
        "impedance_kOhm": values,
        "labels": labels,
        "geometry": geometry,
        "ring_mean_kOhm": round(sum(rings) / len(rings), 2) if rings else None,
        "segment_mean_kOhm": round(sum(segs) / len(segs), 2) if segs else None,
        "segment_to_ring_ratio": (
            round((sum(segs) / len(segs)) / (sum(rings) / len(rings)), 2)
            if rings and segs
            else None
        ),
    }

    if not matches:
        return Proposal(
            field="lead_model",
            value=None,
            confidence=0.0,
            evidence=evidence,
            detectable=True,
            reason=(
                f"measured geometry {geometry} matches no model in configs/leads.yaml. "
                "Add the model, or check that the channel range is right."
            ),
        )

    if len(specific) == 1 and not placeholders:
        return Proposal(
            field="lead_model",
            value=specific[0],
            confidence=HIGH,
            evidence=evidence,
            detectable=True,
            reason=f"geometry {geometry} matches exactly one configured model.",
        )

    # Geometry is measured; the vendor is not. Propose the placeholder.
    proposed = placeholders[0] if placeholders else None
    return Proposal(
        field="lead_model",
        value=proposed,
        confidence=MEDIUM,
        evidence=evidence,
        alternatives=tuple(specific),
        detectable=True,
        reason=(
            f"geometry {geometry} is measured, the manufacturer is not: "
            f"{len(specific)} configured models share this geometry and number their "
            "contacts differently. Proposing the placeholder rather than a vendor. "
            "Confirm against the implant record, then set the real model."
        ),
    )


def assess_contact_quality(
    sweep: ImpedanceSweep,
    open_circuit_kohm: float = DEFAULT_OPEN_CIRCUIT_KOHM,
    high_impedance_kohm: float = DEFAULT_HIGH_IMPEDANCE_KOHM,
    pairs: list[tuple[int, int]] | None = None,
) -> list[Proposal]:
    """Flag contacts the hardware says are open or poorly connected.

    `pairs` describes a differential bank, where each recorded channel is two
    electrodes; a channel is only as good as its worse electrode.
    """
    out: list[Proposal] = []

    def judge(label: str, worst: float, detail: dict[str, Any]) -> None:
        if worst >= open_circuit_kohm:
            out.append(
                Proposal(
                    field="contact_quality",
                    value="open_circuit",
                    confidence=HIGH,
                    evidence={"target": label, **detail},
                    reason=(
                        f"{worst} kOhm is at or above the open-circuit threshold "
                        f"({open_circuit_kohm} kOhm). The hardware sees no connection; "
                        "exclude unless the measurement itself is suspect."
                    ),
                )
            )
        elif worst >= high_impedance_kohm:
            out.append(
                Proposal(
                    field="contact_quality",
                    value="high_impedance",
                    confidence=MEDIUM,
                    evidence={"target": label, **detail},
                    reason=(
                        f"{worst} kOhm exceeds the high-impedance threshold "
                        f"({high_impedance_kohm} kOhm). Usable but noisy; review before including."
                    ),
                )
            )

    if pairs is not None:
        for i, (a, b) in enumerate(pairs, start=1):
            va, vb = sweep.values.get(a), sweep.values.get(b)
            if va is None or vb is None:
                continue
            judge(f"channel {i}", max(va, vb), {"electrodes": (a, b), "kOhm": (va, vb)})
        return out

    for channel, value in sweep.measured().items():
        judge(f"contact {channel}", value, {"kOhm": value})
    return out
