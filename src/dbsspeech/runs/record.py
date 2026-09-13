"""Run records: the provenance written for every recipe execution.

This is the reproducibility appendix, the methods section, and the audit trail,
produced for free on every run. No run record, no result.

Two rules the guide fixes and this enforces:

Paths are relative and manifest-keyed
    A run record never stores an absolute path. Inputs are identified by their
    manifest key (`study_id`, `session`, `acquisition`) plus a content hash, so a
    record means the same thing on another machine and carries nothing about
    where a file happened to sit. See guardrail G13.

A failed run still writes a record
    An exception inside the block produces a record with status `failed` and the
    traceback. A run that vanishes when it breaks is a run nobody can debug.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import subprocess
import traceback
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RUNS_DIR = REPO_ROOT / "runs"
DEFAULT_DERIVATIVES_DIR = REPO_ROOT / "derivatives"

# Libraries whose version can change a number. Recorded on every run.
_TRACKED_PACKAGES = (
    "numpy",
    "scipy",
    "pandas",
    "mne",
    "mne_bids",
    "h5py",
    "py_neuromodulation",
)


def _sha256(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _git(*args: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() if out.returncode == 0 else None


def _commit() -> str | None:
    """The commit this code came from, in a working tree or in a container.

    An image has no .git, so `git rev-parse` answers nothing there and every
    containerized run would record no commit at all. The build stamps the commit
    it built from into the environment instead. A working tree still wins,
    because it is the answer that can be wrong in the interesting way: dirty.
    """
    return _git("rev-parse", "HEAD") or os.environ.get("DBSSPEECH_GIT_COMMIT") or None


def _dirty() -> bool:
    """Whether the code that ran is in no commit.

    In a working tree that is what `git status` says. In an image the code cannot
    change under a run, so it is dirty only if the tree it was built from was,
    which the build records.
    """
    if _git("rev-parse", "HEAD") is not None:
        return bool(_git("status", "--porcelain"))
    return os.environ.get("DBSSPEECH_GIT_DIRTY", "").lower() in {"1", "true", "yes"}


def versions() -> dict[str, str]:
    import importlib

    out: dict[str, str] = {"python": platform.python_version()}
    for name in _TRACKED_PACKAGES:
        try:
            module = importlib.import_module(name)
        except Exception:
            continue
        out[name] = str(getattr(module, "__version__", "unknown"))
    return out


# Absolute paths are stripped out of anything that reaches a run record, because
# `runs/` is committed and a traceback is the one field nobody writes by hand.
#
# The absolute path a checkout lives under is the visible half of the problem
# and the harmless half. The half that matters is that a failure to open a
# recording reports the path it tried, and a raw acquisition filename can carry a
# patient name or a date of surgery. `configs/privacy.yaml` already says whether
# filenames are de-identified, and the answer for this lab is no. So a run that
# fails while opening a file would write the one thing the hard rule forbids,
# into the one directory that is version controlled.
#
# The traceback is kept rather than dropped: a run that vanishes when it breaks
# is a run nobody can debug, and that was the whole reason for recording it. Only
# the paths are rewritten.
# A traceback quotes the file it is in, so a quoted absolute path can be handled
# whole, spaces and all. Anything else absolute is matched bare, and the
# lookbehind stops it firing on a relative path that already has a slash in it.
_REPO = str(Path(__file__).resolve().parents[3])
_QUOTED_PATH = re.compile(r'"((?:[A-Za-z]:[\\/]|/)[^"]*)"')
_BARE_PATH = re.compile(r"""(?<![\w./~-])(?:[A-Za-z]:[\\/]|/)[^\s'"<>|]*""")


def repo_relpath(path: str | Path) -> str | None:
    """The path relative to the repository, or None if it resolves outside it.

    One place, because two callers need the same answer and they must not
    disagree: `Run.add_input` decides what a record stores, and
    `recipes/psd.py` reports to guardrail G13 what a run would store. When those
    two drifted, G13 was handed the assertion "nothing writes a raw path" rather
    than the evidence, and could never fire.

    Outside the repository there is nothing portable to record, and the absolute
    path may name a subject, so the answer is None rather than a best effort.
    """
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return None


def redact_paths(text: str) -> str:
    """Rewrite absolute paths in `text` so a run record carries no filesystem.

    Paths inside the repository become relative, so a traceback still names the
    file and line a developer needs. Everything else becomes `<path>`: outside
    the repository there is nothing a reader of a run record can act on, and
    there may be an identifier. A frame through the environment loses its
    filename and keeps its line number and function, which is the part that
    localizes a bug in a library.

    A bare path containing a space can still survive in part. Tracebacks quote
    the paths they report, so this has to be a message a library formatted
    itself; the check that matters is that nothing under `data/` reaches here,
    and those are reported quoted or by manifest key.
    """
    if not text:
        return text

    def _quoted(match: re.Match[str]) -> str:
        path = match.group(1)
        if path.startswith(_REPO):
            return '"' + path[len(_REPO):].lstrip("/") + '"'
        return '"<path>"'

    out = _QUOTED_PATH.sub(_quoted, text)
    out = out.replace(_REPO + "/", "").replace(_REPO, ".")
    return _BARE_PATH.sub("<path>", out)


@dataclass
class Run:
    """The handle a recipe writes through."""

    run_id: str
    name: str
    claim: str
    user: str
    out_dir: Path
    params: dict[str, Any] = field(default_factory=dict)
    inputs: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    guardrails: dict[str, Any] = field(default_factory=dict)
    qc: dict[str, Any] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)
    config_snapshot: dict[str, Any] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""
    status: str = "running"
    error: str | None = None
    _log_lines: list[str] = field(default_factory=list)

    def add_input(
        self,
        path: str | Path,
        key: dict[str, str] | None = None,
        filenames_deidentified: bool = False,
    ) -> str:
        """Register an input by content hash and manifest key.

        `key` is how the input is actually identified. The location is recorded
        only when both of these hold:

        - the file resolves inside the repository, so the path is not
          machine-specific, and
        - `configs/privacy.yaml` declares filenames de-identified for this
          format, so the filename itself is safe to write down.

        The second condition is the one that used to be missing. A lab that
        copies recordings into `data/` rather than symlinking them had the
        relative path recorded, filename included, however the site had answered
        `filenames_deidentified`. For the TDT formats that answer is now false,
        measured: of 401 staged tanks the date in the filename matched the
        acquisition date in the block's own notes 287 times and was one day out
        114 times. So the filename carried a date, and the record carried the
        filename.

        Defaulting to False means a caller that has not thought about it gets the
        safe behaviour. Guardrail G13 covers the same ground from the other
        direction, and `recipes/psd.py` reports to it what this method would
        actually write rather than asserting that it writes nothing.
        """
        p = Path(path)
        entry: dict[str, Any] = {"sha256": _sha256(p), "bytes": p.stat().st_size}
        if key:
            entry["key"] = dict(key)
        entry["relpath"] = repo_relpath(p) if filenames_deidentified else None
        self.inputs.append(entry)
        return entry["sha256"]

    def log(self, message: str) -> None:
        stamp = datetime.now(UTC).isoformat(timespec="seconds")
        self._log_lines.append(f"{stamp}  {message}")

    def snapshot_config(self, configs: dict[str, Any]) -> None:
        """Store the resolved config, and write it as JSON for MATLAB.

        YAML is the hand-edited source of truth; this JSON is the machine-readable
        proof of what actually ran, and MATLAB reads it without a YAML parser.
        See docs/interop.md.
        """
        self.config_snapshot = configs
        self.out_dir.mkdir(parents=True, exist_ok=True)
        (self.out_dir / "config.json").write_text(json.dumps(configs, indent=2, default=str))

    def add_output(self, path: str | Path) -> None:
        p = Path(path)
        self.outputs.append(str(p.relative_to(self.out_dir)) if p.is_absolute() else str(p))

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "name": self.name,
            "claim": self.claim,
            "user": self.user,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "status": self.status,
            "error": self.error,
            "git_commit": _commit(),
            "git_dirty": _dirty(),
            "params": self.params,
            "inputs": self.inputs,
            "outputs": sorted(self.outputs),
            "guardrails": self.guardrails,
            "qc": self.qc,
            "summary": self.summary,
            "config_sha256": _config_hash(self.config_snapshot),
            "versions": versions(),
        }


def _config_hash(config: dict[str, Any]) -> str | None:
    if not config:
        return None
    blob = json.dumps(config, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()


def make_run_id(
    name: str,
    when: datetime | None = None,
    runs_dir: Path | None = None,
) -> str:
    """`YYYYMMDD_HHMMSS_<name>`, as the guide specifies, made unique.

    The timestamp has one-second resolution, so two runs started in the same
    second would collide and the second would silently overwrite the first, both
    its record and its output directory. When `runs_dir` is given, a taken id
    gets a `-2`, `-3` suffix rather than destroying a result.
    """
    stamp = (when or datetime.now()).strftime("%Y%m%d_%H%M%S")
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in name)
    base = f"{stamp}_{safe}"
    if runs_dir is None:
        return base
    candidate, n = base, 1
    while (Path(runs_dir) / f"{candidate}.json").exists():
        n += 1
        candidate = f"{base}-{n}"
    return candidate


@contextmanager
def record(
    name: str,
    params: dict[str, Any] | Any,
    claim: str,
    user: str | None = None,
    runs_dir: Path | None = None,
    derivatives_dir: Path | None = None,
) -> Iterator[Run]:
    """Open a run, yield the handle, and write the record on the way out.

    Writes on success and on failure. An exception propagates after the record is
    written, so the caller still sees it.
    """
    if not claim or not claim.strip():
        raise ValueError(
            "a run needs a claim: one sentence saying what this run is meant to show. "
            "A result whose purpose was never stated cannot be reviewed."
        )

    if hasattr(params, "model_dump"):
        params = params.model_dump()

    runs_dir = Path(runs_dir or DEFAULT_RUNS_DIR)
    derivatives_dir = Path(derivatives_dir or DEFAULT_DERIVATIVES_DIR)

    run_id = make_run_id(name, runs_dir=runs_dir)
    run = Run(
        run_id=run_id,
        name=name,
        claim=claim.strip(),
        user=user or _git("config", "user.name") or "unknown",
        out_dir=derivatives_dir / "results" / run_id,
        params=dict(params or {}),
        started_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    run.out_dir.mkdir(parents=True, exist_ok=True)

    try:
        yield run
        run.status = "ok"
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised
        run.status = "failed"
        run.error = redact_paths(
            "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        )
        raise
    finally:
        run.finished_at = datetime.now(UTC).isoformat(timespec="seconds")
        # Always discover, then union with anything the recipe named explicitly.
        # Discovering only when nothing was added meant one add_output() call
        # silently hid every other file the run produced.
        if run.out_dir.exists():
            found = {
                str(p.relative_to(run.out_dir))
                for p in run.out_dir.rglob("*")
                if p.is_file()
            }
            run.outputs = sorted(found | set(run.outputs))
        if run._log_lines:
            (run.out_dir / "run.log").write_text("\n".join(run._log_lines) + "\n")
            if "run.log" not in run.outputs:
                run.outputs.append("run.log")
        runs_dir.mkdir(parents=True, exist_ok=True)
        (runs_dir / f"{run_id}.json").write_text(json.dumps(run.to_dict(), indent=2))
