"""Manifest loading and validation.

The manifests are the authoritative description of what was recorded. This
module loads them, checks the invariants stated in `docs/schema.md`, and reports
every violation at once rather than raising on the first.

Reporting all violations matters: manifests are hand-curated, and a validator
that stops at the first error turns one editing pass into ten.

Vocabularies and lead models come from `configs/`, so extending either is a
config change. A term not defined there is an error that names the term.
"""

from __future__ import annotations

import csv
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# Overridable so one checkout can serve a different project: the demo built by
# `dbsspeech seed`, or a deployment whose manifest lives on a mounted volume
# rather than in the image. The other DBSSPEECH_* paths already work this way,
# and without this one they point at a project whose subjects are not in the
# manifest they are read from.
DEFAULT_MANIFEST_DIR = Path(os.environ.get("DBSSPEECH_MANIFEST", REPO_ROOT / "manifest"))
DEFAULT_CONFIG_DIR = REPO_ROOT / "configs"

_TRUE = {"true", "t", "yes", "y", "1"}
_FALSE = {"false", "f", "no", "n", "0"}


def _to_bool(value: str) -> bool | None:
    """Parse a manifest boolean. None means empty or unparseable."""
    v = (value or "").strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return None


@dataclass
class ValidationReport:
    """Every problem found, so one editing pass can fix them all."""

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def __str__(self) -> str:
        lines = [f"ERROR: {e}" for e in self.errors] + [f"warning: {w}" for w in self.warnings]
        return "\n".join(lines) if lines else "manifests valid"


@dataclass
class Manifest:
    """Parsed manifest tables, as lists of row dicts keyed by column name."""

    subjects: list[dict[str, str]]
    streams: list[dict[str, str]]
    leads: list[dict[str, str]]
    channels: list[dict[str, str]]
    windows: list[dict[str, str]]
    # Optional. A lab without imaging has no coordinates, and every recipe must
    # work without them, so this reads as an empty list rather than an error.
    coordinates: list[dict[str, str]] = field(default_factory=list)

    def subject_keys(self) -> set[tuple[str, str]]:
        return {(r["study_id"], r["session"]) for r in self.subjects}

    def channels_for(self, study_id: str, session: str) -> list[dict[str, str]]:
        return [
            r for r in self.channels if r["study_id"] == study_id and r["session"] == session
        ]


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [
            {k: (v or "").strip() for k, v in row.items() if k is not None}
            for row in csv.DictReader(f)
        ]


def load_manifest(manifest_dir: Path | None = None) -> Manifest:
    """Load every manifest table. Missing files read as empty."""
    d = Path(manifest_dir or DEFAULT_MANIFEST_DIR)
    return Manifest(
        subjects=_read_csv(d / "subjects.csv"),
        streams=_read_csv(d / "streams.csv"),
        leads=_read_csv(d / "leads.csv"),
        channels=_read_csv(d / "channels.csv"),
        windows=_read_csv(d / "windows.csv"),
        coordinates=_read_csv(d / "coordinates.csv"),
    )


def load_configs(config_dir: Path | None = None) -> dict[str, Any]:
    """Load the config files the validator needs."""
    d = Path(config_dir or DEFAULT_CONFIG_DIR)
    out: dict[str, Any] = {}
    for name in ("vocabularies", "leads", "qc_thresholds", "bands", "statistics",
                 "privacy", "erna", "markers", "guardrails"):
        path = d / f"{name}.yaml"
        out[name] = yaml.safe_load(path.read_text()) if path.exists() else {}
    return out


def _contacts_for_model(configs: dict[str, Any], model: str) -> list[str] | None:
    lead = (configs.get("leads", {}).get("leads") or {}).get(model)
    if lead is None:
        return None
    return [str(c["id"]) for c in lead.get("contacts", [])]


def validate(
    manifest: Manifest, configs: dict[str, Any] | None = None
) -> ValidationReport:
    """Check the invariants in docs/schema.md. Reports all violations."""
    configs = configs if configs is not None else load_configs()
    rep = ValidationReport()
    vocab = configs.get("vocabularies") or {}
    regions = set(vocab.get("regions") or {})
    conditions = set(vocab.get("conditions") or {})
    sources = set(vocab.get("window_sources") or [])
    statuses = set(vocab.get("window_status") or [])

    subject_keys = manifest.subject_keys()

    # 1. Every dependent row points at a known subject.
    for table, rows in (
        ("streams", manifest.streams),
        ("leads", manifest.leads),
        ("channels", manifest.channels),
        ("windows", manifest.windows),
        ("coordinates", manifest.coordinates),
    ):
        for i, r in enumerate(rows, start=2):
            key = (r.get("study_id", ""), r.get("session", ""))
            if key not in subject_keys:
                rep.error(f"{table}.csv line {i}: {key} has no row in subjects.csv")

    # 2. Channel identity is unique, and ch_index is a usable channel number.
    #
    # Both halves used to be missing and both produced wrong data silently.
    # `io/loader.py` builds a numpy index as `int(ch_index) - 1`, so:
    #
    #   ch_index = 0   -> index -1, which numpy resolves to the LAST channel of
    #                     the stream. In range, so nothing raises. An
    #                     out-of-range value does raise IndexError in both
    #                     readers, which is why this one is the dangerous case.
    #   "1" and "01"   -> two distinct strings, so the uniqueness check below saw
    #                     two channels, while the loader mapped both to index 0.
    #                     Two contacts, one physical channel, no report.
    #
    # Normalising to an int before keying fixes the second, and the range check
    # fixes the first.
    n_channels_by_stream: dict[tuple[str, str, str], int] = {}
    for r in manifest.streams:
        try:
            n_channels_by_stream[(r["study_id"], r["session"], r["stream"])] = int(
                r["n_channels"]
            )
        except (KeyError, TypeError, ValueError):
            continue

    seen: dict[tuple[str, str, str, int], int] = {}
    for i, r in enumerate(manifest.channels, start=2):
        raw = (r.get("ch_index") or "").strip()
        try:
            index = int(raw)
        except ValueError:
            rep.error(
                f"channels.csv line {i}: ch_index {raw!r} is not an integer"
            )
            continue
        if index < 1:
            rep.error(
                f"channels.csv line {i}: ch_index is {index}; channel numbers are "
                "1-based. 0 becomes -1 as an array index, which silently reads "
                "the last channel of the stream."
            )
            continue

        stream_key = (r["study_id"], r["session"], r["stream"])
        declared = n_channels_by_stream.get(stream_key)
        if declared is not None and index > declared:
            rep.error(
                f"channels.csv line {i}: ch_index {index} is beyond the "
                f"{declared} channel(s) streams.csv declares for {r['stream']!r}"
            )
            continue

        key = (*stream_key, index)
        if key in seen:
            rep.error(
                f"channels.csv line {i}: duplicate of line {seen[key]} for {key}. "
                f"ch_index {raw!r} is the same channel as the earlier row even if "
                "it is written differently."
            )
        seen[key] = i

    leads_by_id = {(r["study_id"], r["session"], r["lead_id"]): r for r in manifest.leads}

    for i, r in enumerate(manifest.channels, start=2):
        include = _to_bool(r.get("include", ""))
        # 3. An excluded channel says why.
        if include is False and not r.get("exclude_reason"):
            rep.error(f"channels.csv line {i}: include is false but exclude_reason is empty")
        if include is None:
            rep.error(
                f"channels.csv line {i}: include must be true or false, "
                f"got {r.get('include')!r}"
            )

        # 7. Region is in the vocabulary.
        region = r.get("region", "")
        if region and regions and region not in regions:
            rep.error(
                f"channels.csv line {i}: region {region!r} is not in "
                f"configs/vocabularies.yaml (have: {sorted(regions)})"
            )

        # 4 and 5. Depth channels reference a real lead and a real contact on it.
        lead_id = r.get("lead_id", "")
        if lead_id:
            lead = leads_by_id.get((r["study_id"], r["session"], lead_id))
            if lead is None:
                rep.error(f"channels.csv line {i}: lead_id {lead_id!r} has no row in leads.csv")
            else:
                contacts = _contacts_for_model(configs, lead["lead_model"])
                if contacts is None:
                    rep.error(
                        f"leads.csv: lead_model {lead['lead_model']!r} is not defined in "
                        "configs/leads.yaml"
                    )
                elif r.get("lead_contact") and r["lead_contact"] not in contacts:
                    rep.error(
                        f"channels.csv line {i}: lead_contact {r['lead_contact']!r} is not a "
                        f"contact of {lead['lead_model']} (have: {contacts})"
                    )

    # 6. A lead's channel range matches its model's contact count.
    for i, r in enumerate(manifest.leads, start=2):
        contacts = _contacts_for_model(configs, r.get("lead_model", ""))
        if contacts is None:
            continue
        try:
            span = int(r["channel_last"]) - int(r["channel_first"]) + 1
        except (KeyError, ValueError):
            rep.error(f"leads.csv line {i}: channel_first/channel_last must be integers")
            continue
        if span != len(contacts):
            rep.error(
                f"leads.csv line {i}: channel range covers {span} channels but "
                f"{r['lead_model']} has {len(contacts)} contacts"
            )
        # 10. No anatomical direction claim without rotation.
        if not r.get("rotation_deg"):
            rep.warn(
                f"leads.csv line {i}: rotation_deg empty for {r.get('lead_id')!r}; "
                "anatomical direction claims are blocked for this lead"
            )

    # 11. Contact coordinates name a real lead, a real contact, and a space.
    spaces = set(vocab.get("coordinate_spaces") or {})
    sources_of_coords = set(vocab.get("coordinate_sources") or [])
    lead_models = {
        (r.get("study_id"), r.get("session"), r.get("lead_id")): r.get("lead_model", "")
        for r in manifest.leads
    }
    seen_contacts: dict[tuple[str, str, str, str], int] = {}
    for i, r in enumerate(manifest.coordinates, start=2):
        lead_key = (r.get("study_id"), r.get("session"), r.get("lead_id"))
        if lead_key not in lead_models:
            rep.error(
                f"coordinates.csv line {i}: lead_id {r.get('lead_id')!r} has no "
                "row in leads.csv"
            )
            continue

        contact = str(r.get("contact", ""))
        contacts = _contacts_for_model(configs, lead_models[lead_key])
        if contacts is not None and contact not in contacts:
            rep.error(
                f"coordinates.csv line {i}: contact {contact!r} is not on "
                f"{lead_models[lead_key]}"
            )

        key = (*lead_key, contact)
        if key in seen_contacts:
            rep.error(
                f"coordinates.csv line {i}: duplicate of line {seen_contacts[key]} "
                f"for {key}"
            )
        seen_contacts[key] = i

        for axis in ("x_mm", "y_mm", "z_mm"):
            try:
                float(r[axis])
            except (KeyError, TypeError, ValueError):
                rep.error(f"coordinates.csv line {i}: {axis} must be a number")

        if spaces and r.get("space") not in spaces:
            rep.error(
                f"coordinates.csv line {i}: space {r.get('space')!r} is not in "
                "the vocabulary"
            )
        if sources_of_coords and r.get("source") not in sources_of_coords:
            rep.error(
                f"coordinates.csv line {i}: source {r.get('source')!r} is not in "
                "the vocabulary"
            )
        # A coordinate locates a contact. It says nothing about which way a
        # directional segment faces, so it must not be read as unlocking the
        # direction claims that invariant 10 gates on rotation.
        if r.get("space") == "native":
            rep.warn(
                f"coordinates.csv line {i}: space is 'native', so this position "
                "is not comparable across subjects"
            )

    # 7 and 8. Window vocabulary and non-overlap within a condition.
    by_cond: dict[tuple[str, str, str], list[tuple[float, float, int]]] = {}
    for i, r in enumerate(manifest.windows, start=2):
        cond = r.get("condition", "")
        if conditions and cond not in conditions:
            rep.error(f"windows.csv line {i}: condition {cond!r} is not in the vocabulary")
        if sources and r.get("derived_from") not in sources:
            rep.error(
                f"windows.csv line {i}: derived_from {r.get('derived_from')!r} "
                "is not in the vocabulary"
            )
        if statuses and r.get("status") not in statuses:
            rep.error(f"windows.csv line {i}: status {r.get('status')!r} is not in the vocabulary")
        if r.get("derived_from") == "assumed":
            rep.warn(f"windows.csv line {i}: window is assumed, not measured (guardrail G10)")
        if r.get("status") == "under_revision":
            rep.warn(
                f"windows.csv line {i}: {cond!r} is under revision; results depending on it "
                "are flagged (guardrail G10)"
            )
        try:
            t0, t1 = float(r["t_start_s"]), float(r["t_end_s"])
        except (KeyError, ValueError):
            rep.error(f"windows.csv line {i}: t_start_s and t_end_s must be numbers")
            continue
        if t1 <= t0:
            rep.error(f"windows.csv line {i}: t_end_s ({t1}) must exceed t_start_s ({t0})")
        by_cond.setdefault((r["study_id"], r["session"], cond), []).append((t0, t1, i))

    for (sid, ses, cond), spans in by_cond.items():
        spans.sort()
        for (a0, a1, ia), (b0, b1, ib) in zip(spans, spans[1:], strict=False):
            if b0 < a1:
                rep.error(
                    f"windows.csv lines {ia} and {ib}: {cond!r} windows overlap for "
                    f"{sid}/{ses} ([{a0}, {a1}) and [{b0}, {b1}))"
                )

    # Cross-check: channel counts against the declared streams.
    stream_ch = {
        (r["study_id"], r["session"], r["stream"]): r.get("n_channels", "")
        for r in manifest.streams
    }
    counted: dict[tuple[str, str, str], int] = {}
    for r in manifest.channels:
        key = (r["study_id"], r["session"], r["stream"])
        counted[key] = counted.get(key, 0) + 1
    for key, n in counted.items():
        declared = stream_ch.get(key)
        if declared is None:
            rep.error(f"channels.csv: stream {key[2]!r} has no row in streams.csv")
        elif declared.isdigit() and int(declared) != n:
            rep.error(
                f"streams.csv: {key[2]!r} declares {declared} channels but channels.csv "
                f"has {n} rows for it"
            )

    return rep


def iter_included(manifest: Manifest, study_id: str, session: str) -> Iterable[dict[str, str]]:
    """Channels marked include for one recording. Silence is exclusion."""
    for r in manifest.channels_for(study_id, session):
        if _to_bool(r.get("include", "")) is True:
            yield r
