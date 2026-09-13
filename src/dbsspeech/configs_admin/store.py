"""Reading, validating and versioning the YAML configs.

Versions live in `var/config_history/`, one file per save, named by timestamp and
config. Git would be the obvious home, but a config edit from a browser should
not create a commit in the analyst's working tree: that entangles a threshold
change with whatever code is half-written at the time, and makes `git status`
lie about what the analyst was doing.

Every save records who made it and why, because a threshold with no rationale is
the thing nobody can defend six months later.
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CONFIG_DIR = REPO_ROOT / "configs"
HISTORY_DIR = REPO_ROOT / "var" / "config_history"

# Only these are editable. bands and thresholds are the point; leads.yaml is a
# device catalogue and privacy.yaml governs what may leave the machine, so
# neither should be changeable from a browser.
EDITABLE = ("bands", "qc_thresholds", "guardrails", "statistics", "vocabularies", "erna")


class ConfigError(Exception):
    """Raised when a config is unknown, unparseable, or fails validation."""


@dataclass(frozen=True)
class Version:
    config: str
    saved_at: str
    author: str
    reason: str
    path: Path

    def to_dict(self) -> dict[str, Any]:
        return {"config": self.config, "saved_at": self.saved_at,
                "author": self.author, "reason": self.reason,
                "version_id": self.path.stem}


def _path(name: str, config_dir: Path | None = None) -> Path:
    if name not in EDITABLE:
        raise ConfigError(
            f"{name!r} is not editable here; editable configs are {list(EDITABLE)}"
        )
    return Path(config_dir or CONFIG_DIR) / f"{name}.yaml"


def list_configs(config_dir: Path | None = None) -> list[dict[str, Any]]:
    out = []
    for name in EDITABLE:
        path = Path(config_dir or CONFIG_DIR) / f"{name}.yaml"
        out.append({
            "name": name,
            "exists": path.exists(),
            "bytes": path.stat().st_size if path.exists() else 0,
        })
    return out


def read_config(name: str, config_dir: Path | None = None) -> str:
    """The raw text, so comments survive a round trip through the editor."""
    path = _path(name, config_dir)
    if not path.exists():
        raise ConfigError(f"no config file at {path.name}")
    return path.read_text()


def validate_config(name: str, text: str) -> dict[str, Any]:
    """Parse and check the shape. Raises with the reason, never a bare failure."""
    try:
        parsed = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ConfigError(f"not valid YAML: {exc}") from None
    if not isinstance(parsed, dict):
        raise ConfigError("a config must be a mapping at the top level")

    checker = _CHECKS.get(name)
    if checker is not None:
        checker(parsed)
    return parsed


def _check_bands(parsed: dict[str, Any]) -> None:
    bands = parsed.get("bands")
    if not isinstance(bands, dict) or not bands:
        raise ConfigError("bands.yaml needs a non-empty 'bands' mapping")
    for band, edges in bands.items():
        if not (isinstance(edges, list | tuple) and len(edges) == 2):
            raise ConfigError(f"band {band!r} must be a [low, high] pair")
        low, high = edges
        if not all(isinstance(v, int | float) for v in edges):
            raise ConfigError(f"band {band!r} edges must be numbers")
        if low <= 0:
            raise ConfigError(f"band {band!r} low edge must be above zero")
        if high <= low:
            raise ConfigError(
                f"band {band!r} has high edge {high} at or below low edge {low}"
            )


def _check_guardrails(parsed: dict[str, Any]) -> None:
    from ..guardrails import registered_checks
    from ..guardrails.base import Severity

    rails = parsed.get("guardrails")
    if not isinstance(rails, dict):
        raise ConfigError("guardrails.yaml needs a 'guardrails' mapping")
    known = set(registered_checks())
    for name, spec in rails.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"guardrail {name!r} must be a mapping")
        severity = spec.get("severity", "warn")
        try:
            Severity(severity)
        except ValueError:
            raise ConfigError(
                f"guardrail {name!r} has severity {severity!r}; "
                f"valid values are {[s.value for s in Severity]}"
            ) from None
    # A guardrail removed from the config stops running, which is a real way to
    # disable a check by accident. Say so rather than letting it pass silently.
    missing = sorted(known - set(rails))
    if missing:
        raise ConfigError(
            f"these guardrails are implemented but absent from the config, so they "
            f"would stop running: {missing}. Set severity 'off' to disable one "
            "deliberately."
        )


def _check_qc_thresholds(parsed: dict[str, Any]) -> None:
    detectors = parsed.get("detectors")
    if not isinstance(detectors, dict) or not detectors:
        raise ConfigError("qc_thresholds.yaml needs a non-empty 'detectors' mapping")

    actions = parsed.get("actions")
    if not isinstance(actions, dict) or not actions:
        raise ConfigError(
            "qc_thresholds.yaml needs an 'actions' mapping: the review screen "
            "offers exactly these, and a reviewer cannot choose what is not here"
        )
    for name, spec in actions.items():
        for field in ("label", "description"):
            if not str((spec or {}).get(field, "")).strip():
                raise ConfigError(
                    f"action {name!r} needs a non-empty {field!r}: it is read while "
                    "someone decides what to do about a flag"
                )
    if "none" not in actions:
        raise ConfigError(
            "actions must include 'none'. Approving a flag says the observation is "
            "real; the action says what to do about it, and sometimes the answer is "
            "nothing. Without it a reviewer cannot keep a contact whose artifact is "
            "the signal of interest."
        )

    for name, spec in detectors.items():
        if not isinstance(spec, dict):
            raise ConfigError(f"detector {name!r} must be a mapping")
        if "proposed_action" not in spec:
            raise ConfigError(f"detector {name!r} needs a proposed_action")
        if spec["proposed_action"] not in actions:
            raise ConfigError(
                f"detector {name!r} proposes {spec['proposed_action']!r}, which is "
                f"not one of the declared actions {sorted(actions)}"
            )
        if spec.get("severity") not in {"low", "med", "high"}:
            raise ConfigError(
                f"detector {name!r} needs severity low, med or high"
            )
        # A flag nobody can read is a flag nobody can decide.
        for field in ("label", "means"):
            if not str(spec.get(field, "")).strip():
                raise ConfigError(
                    f"detector {name!r} needs a non-empty {field!r}: the review "
                    "screen shows it instead of the detector's function name"
                )


def _check_statistics(parsed: dict[str, Any]) -> None:
    from ..stats import CENTERS, SCALES

    for group, expected in (("centers", CENTERS), ("scales", SCALES)):
        options = parsed.get(group)
        if not isinstance(options, dict):
            raise ConfigError(f"statistics.yaml needs a {group!r} mapping")
        missing = sorted(set(expected) - set(options))
        if missing:
            raise ConfigError(f"{group} is missing {missing}, which the code offers")
        for key, info in options.items():
            for field in ("label", "description", "when_to_use", "caveat"):
                if not str((info or {}).get(field, "")).strip():
                    raise ConfigError(
                        f"{group}.{key} needs a non-empty {field!r}: these strings "
                        "are shown beside the choice in the interface"
                    )


def _check_erna(parsed: dict[str, Any]) -> None:
    """ERNA settings, checked for the mistakes that quietly produce a number.

    This config exists because no ERNA definition is universal. The checks here
    are the ones where a wrong value does not fail, it just answers wrongly.
    """
    from ..recipes.erna import SETTING_PATHS

    for path in SETTING_PATHS:
        section, key = path.split(".")
        node = parsed.get(section)
        if not isinstance(node, dict) or key not in node:
            raise ConfigError(
                f"erna.yaml is missing {path!r}. Every setting the recipe reads has "
                "to be present here, or a run would silently fall back to a value "
                "nobody chose."
            )

    band = parsed["band"]
    if float(band["low_hz"]) >= float(band["high_hz"]):
        raise ConfigError(
            f"erna band {band['low_hz']}-{band['high_hz']} Hz has its edges "
            "inverted or empty"
        )
    if float(parsed["window"]["analysis_ms"]) <= 0:
        raise ConfigError("erna window.analysis_ms must be positive")
    if float(parsed["window"]["blanking_ms"]) < 0:
        raise ConfigError("erna window.blanking_ms cannot be negative")
    if int(parsed["peaks"]["min_peaks"]) < 2:
        raise ConfigError(
            "erna peaks.min_peaks below 2 means a frequency from a single "
            "interval, which is a number with no measurement behind it"
        )
    if parsed["stim"]["source"] not in {"amplitude_threshold", "windows", "epochs"}:
        raise ConfigError(
            f"erna stim.source {parsed['stim']['source']!r} is not one of "
            "amplitude_threshold, windows, epochs"
        )

    # Claiming the settings were reviewed without saying who is not a review.
    if parsed.get("defaults_reviewed") and not str(parsed.get("reviewed_by", "")).strip():
        raise ConfigError(
            "defaults_reviewed is true but reviewed_by is empty. The point of the "
            "flag is that a person who knows the stimulation protocol looked at "
            "these numbers; name them."
        )


_CHECKS = {
    "bands": _check_bands,
    "erna": _check_erna,
    "guardrails": _check_guardrails,
    "qc_thresholds": _check_qc_thresholds,
    "statistics": _check_statistics,
}


def list_versions(name: str, history_dir: Path | None = None) -> list[Version]:
    d = Path(history_dir or HISTORY_DIR)
    if not d.is_dir():
        return []
    out = []
    for path in sorted(d.glob(f"{name}__*.yaml"), reverse=True):
        meta_path = path.with_suffix(".json")
        meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        out.append(Version(name, meta.get("saved_at", ""), meta.get("author", ""),
                           meta.get("reason", ""), path))
    return out


def read_version(name: str, version_id: str, history_dir: Path | None = None) -> str:
    path = Path(history_dir or HISTORY_DIR) / f"{version_id}.yaml"
    if not path.exists() or not path.name.startswith(f"{name}__"):
        raise ConfigError(f"no saved version {version_id!r} of {name!r}")
    return path.read_text()


def write_config(
    name: str,
    text: str,
    author: str,
    reason: str,
    config_dir: Path | None = None,
    history_dir: Path | None = None,
) -> dict[str, Any]:
    """Validate, archive the previous contents, then write.

    The previous version is archived rather than the new one, so history reads as
    "what it was before this change", and the current file is always the live
    value rather than a copy of it.
    """
    if not author.strip():
        raise ConfigError("a config change needs an author")
    if not reason.strip():
        raise ConfigError(
            "a config change needs a reason: a threshold with no rationale is the "
            "thing nobody can defend six months later"
        )

    validate_config(name, text)
    path = _path(name, config_dir)
    history = Path(history_dir or HISTORY_DIR)
    history.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    version_id = f"{name}__{stamp}"
    if path.exists():
        (history / f"{version_id}.yaml").write_text(path.read_text())
        (history / f"{version_id}.json").write_text(json.dumps({
            "config": name,
            "saved_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "author": author.strip(),
            "reason": reason.strip(),
            "replaced_by_edit": True,
        }, indent=2))

    path.write_text(text)
    return {
        "config": name,
        "version_id": version_id,
        "author": author.strip(),
        "reason": reason.strip(),
        # Said here so an interface can show it without inventing the wording.
        "applies_to": (
            "future runs and future QC proposals. Subjects already approved are "
            "unaffected: an approval certifies the judgments made against the "
            "numbers as they were."
        ),
    }


def diff_versions(
    name: str, version_id: str, config_dir: Path | None = None,
    history_dir: Path | None = None,
) -> str:
    """Unified diff from a saved version to what is live now."""
    old = read_version(name, version_id, history_dir).splitlines(keepends=True)
    new = read_config(name, config_dir).splitlines(keepends=True)
    return "".join(difflib.unified_diff(old, new, fromfile=version_id,
                                        tofile=f"{name}.yaml (current)"))
