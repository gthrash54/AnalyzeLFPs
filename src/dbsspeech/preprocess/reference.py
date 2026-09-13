"""Montage-aware re-referencing.

A derivation is a weighted combination of recorded channels. Every scheme below
is built from the lead's declared geometry, so the same code produces the right
pairs for a 1-3-3-1 directional lead and for a four-ring lead without knowing
which it has.

Why this matters more than usual here: on a shared reference every contact sees
the same common-mode signal, which appears as an effect on every channel at once.
Guardrail G1 exists for that reason, and `monopolar` is retained only so a
montage comparison can be run deliberately.

Scheme definitions, stated because "bipolar" alone is ambiguous:

`monopolar`
    As recorded. Not a derivation. Available for comparison only.

`bipolar_vertical`
    Along the shank. Each segment minus its nearest ring, and the dorsal ring
    minus the ventral ring. On a 1-3-3-1 lead that gives the lower segments
    against the ventral ring and the upper segments against the dorsal ring.
    Preserves per-segment identity, which is what any directional analysis needs.

`bipolar_horizontal`
    Within a segment row: a-b, b-c, c-a. Strongest common-mode rejection, but it
    destroys per-segment values, so a directional claim cannot be made from it.

`bipolar_adjacent`
    Same segment letter across adjacent rows, plus ring to nearest segment row
    mean. Conventional nearest-neighbor derivation.

`car`
    Common average across the included contacts of one lead. Note that averaging
    across few contacts spreads a strong local signal into every other
    derivation; `configs/vocabularies.yaml` marks it not safe by default.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

SCHEMES = (
    "monopolar",
    "bipolar_vertical",
    "bipolar_horizontal",
    "bipolar_adjacent",
    "car",
)


def available_schemes() -> tuple[str, ...]:
    return SCHEMES


@dataclass(frozen=True)
class Derivation:
    """One output channel: a weighted sum of recorded contacts.

    `weights` maps a contact id to its coefficient. A bipolar pair is
    ``{"2a": 1.0, "1": -1.0}``.
    """

    name: str
    weights: dict[str, float]
    kind: str = "bipolar"

    @property
    def contacts(self) -> tuple[str, ...]:
        return tuple(self.weights)


@dataclass(frozen=True)
class Montage:
    """A full set of derivations for one lead under one scheme."""

    scheme: str
    lead_id: str
    derivations: tuple[Derivation, ...] = ()
    notes: tuple[str, ...] = field(default_factory=tuple)

    def __len__(self) -> int:
        return len(self.derivations)

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(d.name for d in self.derivations)


def _rows(lead_spec: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    """Group a model's contacts by row index, ventral to dorsal."""
    out: dict[int, list[dict[str, Any]]] = {}
    for contact in lead_spec.get("contacts", []):
        out.setdefault(int(contact["row"]), []).append(contact)
    return dict(sorted(out.items()))


def build_montage(
    scheme: str,
    lead_spec: dict[str, Any],
    lead_id: str = "lead",
    available: set[str] | None = None,
) -> Montage:
    """Build the derivations for one lead under `scheme`.

    `available` restricts to contacts that survived QC; a derivation needing a
    missing contact is dropped and the omission is recorded in `notes`.
    """
    if scheme not in SCHEMES:
        raise ValueError(f"unknown reference scheme {scheme!r}; have {SCHEMES}")

    rows = _rows(lead_spec)
    ring_rows = [r for r, cs in rows.items() if len(cs) == 1]
    seg_rows = [r for r, cs in rows.items() if len(cs) > 1]
    ids = [str(c["id"]) for c in lead_spec.get("contacts", [])]
    have = available if available is not None else set(ids)

    derivations: list[Derivation] = []
    notes: list[str] = []

    def add(name: str, weights: dict[str, float], kind: str = "bipolar") -> None:
        missing = [c for c in weights if c not in have]
        if missing:
            notes.append(f"{name} dropped: contact(s) {missing} not available")
            return
        derivations.append(Derivation(name, weights, kind))

    if scheme == "monopolar":
        for cid in ids:
            add(cid, {cid: 1.0}, kind="monopolar")

    elif scheme == "car":
        present = [c for c in ids if c in have]
        if present:
            w = 1.0 / len(present)
            for cid in present:
                weights = {cid: 1.0 - w}
                weights.update({o: -w for o in present if o != cid})
                add(f"{cid}-car", weights, kind="car")

    elif scheme == "bipolar_vertical":
        for row in seg_rows:
            # The NEAREST ring by distance, not the one below. On a 1-3-3-1 lead
            # the lower segment row references the ventral ring and the upper row
            # references the dorsal ring; preferring "below" would send both to
            # the ventral ring and silently change what the derivation means.
            if not ring_rows:
                notes.append(f"row {row}: no ring contact to reference against")
                continue
            nearest = min(ring_rows, key=lambda r, _row=row: (abs(r - _row), r))
            ring_id = str(rows[nearest][0]["id"])
            for contact in rows[row]:
                cid = str(contact["id"])
                add(f"{cid}-{ring_id}", {cid: 1.0, ring_id: -1.0})
        if len(ring_rows) >= 2:
            lo, hi = str(rows[min(ring_rows)][0]["id"]), str(rows[max(ring_rows)][0]["id"])
            add(f"{hi}-{lo}", {hi: 1.0, lo: -1.0})

    elif scheme == "bipolar_horizontal":
        for row in seg_rows:
            contacts = [str(c["id"]) for c in rows[row]]
            for a, b in zip(contacts, contacts[1:] + contacts[:1], strict=False):
                add(f"{a}-{b}", {a: 1.0, b: -1.0})
        if not seg_rows:
            notes.append("no segment rows: horizontal derivation is undefined")

    elif scheme == "bipolar_adjacent":
        row_indices = list(rows)
        for lower, upper in zip(row_indices, row_indices[1:], strict=False):
            lo_contacts, up_contacts = rows[lower], rows[upper]
            if len(lo_contacts) == len(up_contacts):
                # Same segment letter, or ring to ring.
                for a, b in zip(lo_contacts, up_contacts, strict=False):
                    aid, bid = str(b["id"]), str(a["id"])
                    add(f"{aid}-{bid}", {aid: 1.0, bid: -1.0})
            else:
                # Ring against the mean of the neighboring segment row.
                ring, segs = (
                    (lo_contacts[0], up_contacts)
                    if len(lo_contacts) == 1
                    else (up_contacts[0], lo_contacts)
                )
                rid = str(ring["id"])
                w = 1.0 / len(segs)
                weights = {rid: 1.0}
                weights.update({str(s["id"]): -w for s in segs})
                add(f"{rid}-rowmean", weights)

    return Montage(scheme=scheme, lead_id=lead_id, derivations=tuple(derivations),
                   notes=tuple(notes))


def apply_montage(
    data: np.ndarray, contact_order: list[str], montage: Montage
) -> np.ndarray:
    """Apply a montage to ``(n_contacts, n_samples)`` data.

    `contact_order` names the row order of `data`. Returns
    ``(n_derivations, n_samples)`` in `montage.names` order.
    """
    if data.shape[0] != len(contact_order):
        raise ValueError(
            f"data has {data.shape[0]} rows but contact_order names "
            f"{len(contact_order)} contacts"
        )
    index = {cid: i for i, cid in enumerate(contact_order)}
    out = np.zeros((len(montage.derivations), data.shape[1]), dtype=np.float64)
    for i, derivation in enumerate(montage.derivations):
        for cid, weight in derivation.weights.items():
            try:
                row = index[cid]
            except KeyError:
                raise KeyError(
                    f"derivation {derivation.name!r} needs contact {cid!r}, "
                    f"which is not in contact_order {contact_order}"
                ) from None
            out[i] += weight * data[row]
    return out
