"""Export bundles: how a result leaves the app with its provenance attached.

A figure pasted into a slide loses everything that made it defensible. A bundle
is the opposite: a zip that carries the figures, the tables, the run record, the
config as it was, and a README a person can read without this software.

The README is the point. Six months from now the question is not "where is the
file" but "what was this, who ran it, against which code, and what did the checks
say". That has to be answerable from the zip alone.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]


def _readme(record: dict[str, Any], files: list[str]) -> str:
    lines = [
        f"Run {record.get('run_id', 'unknown')}",
        "=" * (4 + len(str(record.get("run_id", "unknown")))),
        "",
        f"Claim:    {record.get('claim', '(none stated)')}",
        f"Recipe:   {record.get('name', 'unknown')}",
        f"Ran by:   {record.get('user', 'unknown')}",
        f"Started:  {record.get('started_at', 'unknown')}",
        f"Status:   {record.get('status', 'unknown')}",
        "",
    ]

    commit = record.get("git_commit")
    lines.append(f"Code:     {commit or 'unknown'}")
    if record.get("git_dirty"):
        lines += [
            "",
            "WARNING: this run was produced from a working tree with uncommitted",
            "changes. The code that made these numbers is in no commit and cannot",
            "be recovered from the repository. Treat the result as provisional.",
        ]
    lines.append("")

    qc = record.get("qc") or {}
    if qc:
        lines += [f"QC:       {qc.get('status', 'unknown')}"]
        applied = qc.get("applied") or []
        if applied:
            lines.append(f"          {len(applied)} approved QC action(s) applied:")
            for action in applied[:12]:
                lines.append(
                    f"            {action.get('target', '?')}: "
                    f"{action.get('effect', action.get('action', ''))}"
                )
        else:
            lines.append("          no QC actions were applied to this data")
        lines.append("")

    guardrails = record.get("guardrails") or {}
    findings = guardrails.get("findings") or []
    overrides = guardrails.get("overrides") or []
    lines.append(f"Guardrails: {len(findings)} fired, {len(overrides)} overridden")
    for finding in findings:
        lines.append(f"  [{finding.get('severity')}] {finding.get('guardrail')}")
        lines.append(f"      {finding.get('message', '')}")
    for override in overrides:
        lines.append(f"  OVERRIDDEN {override.get('guardrail')}")
        lines.append(f"      reason given: {override.get('reason', '')}")
    lines.append("")

    summary = record.get("summary") or {}
    normalization = summary.get("normalization") or {}
    if normalization.get("sentence"):
        lines += [f"Normalization: {normalization['sentence']}", ""]

    inputs = record.get("inputs") or []
    if inputs:
        lines.append("Inputs (identified by manifest key and content hash):")
        for entry in inputs:
            key = entry.get("key") or {}
            key_text = ", ".join(f"{k}={v}" for k, v in key.items()) or "(no key)"
            lines.append(f"  {key_text}")
            lines.append(f"    sha256 {entry.get('sha256', '')[:16]}...")
        lines.append("")

    versions = record.get("versions") or {}
    if versions:
        lines.append("Library versions:")
        for name, version in sorted(versions.items()):
            lines.append(f"  {name}: {version}")
        lines.append("")

    lines.append("Contents of this bundle:")
    for name in sorted(files):
        lines.append(f"  {name}")
    lines += [
        "",
        f"Bundled {datetime.now(UTC).isoformat(timespec='seconds')}.",
        "",
        "To regenerate this result, check out the commit above and re-run the",
        "recipe with the parameters in run.json against the same manifest.",
    ]
    return "\n".join(lines) + "\n"


def build_bundle(
    run_id: str,
    runs_dir: Path | None = None,
    derivatives_dir: Path | None = None,
    config_dir: Path | None = None,
) -> bytes:
    """Return the bundle as bytes, so it can be streamed or written."""
    runs_dir = Path(runs_dir or REPO_ROOT / "runs")
    derivatives_dir = Path(derivatives_dir or REPO_ROOT / "derivatives")
    config_dir = Path(config_dir or REPO_ROOT / "configs")

    record_path = runs_dir / f"{run_id}.json"
    if not record_path.exists():
        raise FileNotFoundError(f"no run record for {run_id!r}")
    record = json.loads(record_path.read_text())

    out_dir = derivatives_dir / "results" / run_id
    outputs = sorted(p for p in out_dir.rglob("*") if p.is_file()) if out_dir.exists() else []

    names: list[str] = []
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in outputs:
            relative = path.relative_to(out_dir)
            folder = (
                "figures" if path.suffix in {".png", ".svg"}
                else "tables" if path.suffix in {".csv", ".parquet", ".nc"}
                else "other"
            )
            arcname = f"{folder}/{relative}"
            archive.write(path, arcname)
            names.append(arcname)

        archive.writestr("run.json", json.dumps(record, indent=2))
        names.append("run.json")

        # The config as it was for this run, not as it is now. A bundle that
        # picked up today's thresholds would misrepresent what produced it.
        snapshot = out_dir / "config.json"
        if snapshot.exists():
            archive.writestr("configs/config.json", snapshot.read_text())
            names.append("configs/config.json")
        else:
            for path in sorted(config_dir.glob("*.yaml")):
                archive.writestr(f"configs/current/{path.name}", path.read_text())
                names.append(f"configs/current/{path.name}")
            archive.writestr(
                "configs/NOTE.txt",
                "This run did not save a config snapshot, so the CURRENT configs\n"
                "are included instead. They may differ from what produced this\n"
                "result. Check run.json for the config hash.\n",
            )
            names.append("configs/NOTE.txt")

        archive.writestr("README.txt", _readme(record, names))

    return buffer.getvalue()
