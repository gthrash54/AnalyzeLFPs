"""Joining a recording to its manifest.

The reader knows about files. The manifest knows what the channels are. This
module is where they meet, and it is the only place that resolves a manifest row
to a channel index in a stream.

Nothing here decides anything scientific. Channel inclusion, lead geometry, and
window boundaries all come from the manifest, which is authoritative. A channel
absent from the manifest is not analyzed: silence is exclusion.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from ..manifest import DEFAULT_CONFIG_DIR, Manifest, load_configs, load_manifest
from ..preprocess import apply_montage, build_montage
from ..preprocess.resample import decimate_stream, suggest_factor, usable_bandwidth_hz
from .base import PrivacyPolicy, Recording, entry_suffixes
from .base import open_recording as _open

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


@dataclass(frozen=True)
class LeadView:
    """One lead's contacts, in ventral-to-dorsal order, with their channel indices."""

    lead_id: str
    target: str
    lead_model: str
    stream: str
    contact_ids: tuple[str, ...]
    channel_indices: tuple[int, ...]
    rotation_deg: float | None = None

    @property
    def has_rotation(self) -> bool:
        """False blocks any anatomical direction claim (schema invariant 10)."""
        return self.rotation_deg is not None


@dataclass(frozen=True)
class DerivedSignal:
    """Re-referenced data plus everything needed to describe how it was made."""

    lead_id: str
    scheme: str
    names: tuple[str, ...]
    data: np.ndarray
    sfreq_hz: float
    usable_bandwidth_hz: float
    decimation_factor: int
    decimation_stages: int
    rows: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()


@dataclass
class Session:
    """One recording, with its manifest resolved. Close when done."""

    study_id: str
    session: str
    recording: Recording
    manifest: Manifest
    configs: dict[str, Any]
    _leads: dict[str, LeadView] = field(default_factory=dict)
    # What QC actually removed, as opposed to what was approved. The run record
    # must report the former: a record claiming an action that never took effect
    # is worse than one that claims nothing.
    qc_applied: list[dict[str, str]] = field(default_factory=list)
    qc_annotations: list[dict[str, Any]] = field(default_factory=list)

    def apply_qc(self, actions: list[dict[str, str]]) -> list[dict[str, str]]:
        """Apply approved QC decisions. Returns only what took effect.

        Channel exclusions drop contacts, so a montage derivation needing one is
        dropped too and says so. Window annotations are carried, never applied:
        no sample is deleted, and a recipe decides how to treat an annotated
        span.

        Targets are named `<lead_id>:<contact>` by the QC collection step.
        """
        applied: list[dict[str, str]] = []
        for action in actions:
            kind = action.get("action", "")
            target = action.get("target", "")

            if kind == "exclude_channel" and ":" in target:
                lead_id, contact = target.split(":", 1)
                lead = self._leads.get(lead_id)
                if lead is None or contact not in lead.contact_ids:
                    continue
                keep = [
                    (cid, idx)
                    for cid, idx in zip(lead.contact_ids, lead.channel_indices, strict=False)
                    if cid != contact
                ]
                self._leads[lead_id] = replace(
                    lead,
                    contact_ids=tuple(c for c, _ in keep),
                    channel_indices=tuple(i for _, i in keep),
                )
                applied.append({**action, "effect": f"dropped {contact} from {lead_id}"})

            elif kind == "annotate_window":
                self.qc_annotations.append(dict(action))
                applied.append({**action, "effect": "annotated, samples retained"})

            elif kind == "notch":
                # Recorded as a recommendation. Applying a filter is an analysis
                # decision a recipe makes, not something QC does to the data.
                applied.append({**action, "effect": "recommended, not applied here"})

        self.qc_applied = applied
        return applied

    # ---- manifest views ------------------------------------------------------

    def leads(self) -> dict[str, LeadView]:
        return dict(self._leads)

    def windows(self, condition: str | None = None) -> list[dict[str, str]]:
        rows = [
            r
            for r in self.manifest.windows
            if r["study_id"] == self.study_id and r["session"] == self.session
        ]
        if condition is not None:
            rows = [r for r in rows if r["condition"] == condition]
        return rows

    def conditions(self) -> tuple[str, ...]:
        seen: list[str] = []
        for r in self.windows():
            if r["condition"] not in seen:
                seen.append(r["condition"])
        return tuple(seen)

    def contact_rows(self, lead_id: str) -> tuple[str, ...]:
        """Row label per contact, for the per-row aggregate."""
        lead = self._leads[lead_id]
        spec = self._lead_spec(lead.lead_model)
        contacts = spec.get("contacts", [])
        by_id = {str(c["id"]): c for c in contacts}

        # Label by position among rows of the same kind, not by absolute row
        # index. Row indices are a config detail; ventral versus dorsal is the
        # thing findings are stated in, so it must not depend on how a model
        # happens to number its rows.
        ring_rows = sorted({int(c["row"]) for c in contacts if c.get("kind") == "ring"})
        seg_rows = sorted({int(c["row"]) for c in contacts if c.get("kind") == "segment"})

        def label(row: int, kind: str) -> str:
            rows = ring_rows if kind == "ring" else seg_rows
            suffix = "ring" if kind == "ring" else "segments"
            if not rows:
                return "unknown"
            if row == rows[0]:
                return f"ventral_{suffix}" if kind == "ring" else f"lower_{suffix}"
            if row == rows[-1]:
                return f"dorsal_{suffix}" if kind == "ring" else f"upper_{suffix}"
            return f"mid_{suffix}_{rows.index(row)}"

        labels: list[str] = []
        for cid in lead.contact_ids:
            contact = by_id[cid]
            labels.append(label(int(contact["row"]), contact.get("kind", "ring")))
        return tuple(labels)

    def _lead_spec(self, model: str) -> dict[str, Any]:
        spec = (self.configs.get("leads", {}).get("leads") or {}).get(model)
        if spec is None:
            raise KeyError(
                f"lead_model {model!r} is not defined in configs/leads.yaml; "
                "add it there rather than special-casing it in code"
            )
        return spec

    # ---- reading -------------------------------------------------------------

    def read_derived(
        self,
        lead_id: str,
        scheme: str,
        tmin: float | None = None,
        tmax: float | None = None,
        sfreq_target_hz: float | None = None,
    ) -> DerivedSignal:
        """Read a window from one lead and apply a montage.

        Decimation happens after re-referencing, so the anti-alias filter acts on
        the derived signal rather than on channels that are about to be
        subtracted from each other.
        """
        lead = self._leads[lead_id]
        raw = self.recording.read(
            lead.stream, channels=list(lead.channel_indices), tmin=tmin, tmax=tmax
        )
        spec = self._lead_spec(lead.lead_model)
        montage = build_montage(scheme, spec, lead_id, available=set(lead.contact_ids))
        derived = apply_montage(raw, list(lead.contact_ids), montage)

        sfreq = self.recording.streams[lead.stream].sfreq_hz
        factor, stages = 1, 0
        if sfreq_target_hz:
            factor = suggest_factor(sfreq, sfreq_target_hz)
            if factor > 1:
                result = decimate_stream(derived, sfreq, factor)
                derived, sfreq, stages = result.data, result.sfreq_hz, result.n_stages

        return DerivedSignal(
            lead_id=lead_id,
            scheme=scheme,
            names=montage.names,
            data=derived,
            sfreq_hz=sfreq,
            usable_bandwidth_hz=usable_bandwidth_hz(sfreq),
            decimation_factor=factor,
            decimation_stages=stages,
            rows=self._derivation_rows(lead_id, montage.names),
            notes=montage.notes,
        )

    def _derivation_rows(self, lead_id: str, names: tuple[str, ...]) -> tuple[str, ...]:
        """Label each derivation by the row of its leading contact."""
        lead = self._leads[lead_id]
        rows = dict(zip(lead.contact_ids, self.contact_rows(lead_id), strict=False))
        return tuple(rows.get(n.split("-", 1)[0], "unknown") for n in names)

    def close(self) -> None:
        self.recording.close()

    def __enter__(self) -> Session:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def open_session(
    study_id: str,
    session: str,
    manifest: Manifest | None = None,
    configs: dict[str, Any] | None = None,
    data_dir: Path | None = None,
    policy: PrivacyPolicy | None = None,
) -> Session:
    """Open a recording named by the manifest.

    The manifest supplies the format and the path, so nothing here sniffs or
    guesses. Included channels only.
    """
    manifest = manifest if manifest is not None else load_manifest()
    configs = configs if configs is not None else load_configs()

    subject = next(
        (
            r
            for r in manifest.subjects
            if r["study_id"] == study_id and r["session"] == session
        ),
        None,
    )
    if subject is None:
        raise KeyError(f"no subjects.csv row for {study_id!r}/{session!r}")

    if policy is None:
        privacy_path = Path(DEFAULT_CONFIG_DIR) / "privacy.yaml"
        privacy = yaml.safe_load(privacy_path.read_text()) if privacy_path.exists() else {}
        policy = PrivacyPolicy.from_mapping(privacy, subject["format"])

    root = Path(data_dir or DEFAULT_DATA_DIR) / subject["root_relpath"]
    path = root if root.is_file() else _sole_recording(root, subject["format"])
    recording = _open(path, format=subject["format"], policy=policy)

    leads: dict[str, LeadView] = {}
    for lead_row in manifest.leads:
        if (lead_row["study_id"], lead_row["session"]) != (study_id, session):
            continue
        included = [
            c
            for c in manifest.channels_for(study_id, session)
            if c.get("lead_id") == lead_row["lead_id"]
            and (c.get("include", "").strip().lower() in {"true", "t", "yes", "1"})
        ]
        included.sort(key=lambda c: int(c["ch_index"]))
        if not included:
            continue
        rotation = lead_row.get("rotation_deg", "").strip()
        leads[lead_row["lead_id"]] = LeadView(
            lead_id=lead_row["lead_id"],
            target=lead_row["target"],
            lead_model=lead_row["lead_model"],
            stream=included[0]["stream"],
            contact_ids=tuple(c["lead_contact"] for c in included),
            # Manifest channel indices are 1-based, as the hardware numbers them.
            channel_indices=tuple(int(c["ch_index"]) - 1 for c in included),
            rotation_deg=float(rotation) if rotation else None,
        )

    return Session(
        study_id=study_id,
        session=session,
        recording=recording,
        manifest=manifest,
        configs=configs,
        _leads=leads,
    )


def _sole_recording(root: Path, format: str) -> Path:
    """Find the one recording file in a block directory, or say why it cannot."""
    # From the registry, not a table kept here. A table kept here is a table
    # that goes stale the next time a reader is added.
    suffixes = entry_suffixes(format)
    candidates = [p for p in sorted(root.glob("*")) if p.suffix.lower() in suffixes]
    if not candidates:
        raise FileNotFoundError(f"no {format} recording in {root}")
    if len(candidates) > 1:
        raise ValueError(
            f"{len(candidates)} candidate recordings in {root}; "
            "point root_relpath at the file rather than the directory"
        )
    return candidates[0]
