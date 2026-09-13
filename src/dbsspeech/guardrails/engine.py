"""Running guardrails, and deciding what stops a run.

Behavior chosen deliberately: a blocking guardrail refuses before anything is
computed, explains itself, and names the override. Nothing is produced, so a
blocked result cannot reach a figure by accident.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

import yaml

from .base import CheckContext, Finding, GuardrailBlocked, Override, Severity

CheckFn = Callable[[CheckContext, dict[str, Any]], Finding | None]

_CHECKS: dict[str, CheckFn] = {}

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "guardrails.yaml"


def register_check(name: str) -> Callable[[CheckFn], CheckFn]:
    """Register a check under the key it uses in configs/guardrails.yaml."""

    def decorator(fn: CheckFn) -> CheckFn:
        if name in _CHECKS:
            raise ValueError(f"guardrail {name!r} already registered")
        _CHECKS[name] = fn
        return fn

    return decorator


def registered_checks() -> tuple[str, ...]:
    return tuple(sorted(_CHECKS))


def load_config(path: Path | None = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_CONFIG)
    return yaml.safe_load(p.read_text()) if p.exists() else {}


def run_checks(
    context: CheckContext,
    config: dict[str, Any] | None = None,
    overrides: Iterable[Override] | dict[str, str] | None = None,
    blocking: bool = True,
) -> tuple[list[Finding], list[Override]]:
    """Run every configured check. Returns findings and the overrides applied.

    Raises `GuardrailBlocked` if any blocking finding was not overridden, before
    the caller computes anything.

    `blocking=False` collects those findings and returns them instead of raising.
    That is for the pass that runs AFTER a recipe, where the result already
    exists: refusing at that point would leave a half-written record and would
    not un-compute anything. A blocking rule that only becomes decidable after
    the fact is reported, loudly, and the reader decides.
    """
    config = config if config is not None else load_config()
    settings = (config or {}).get("guardrails") or {}

    applied = _normalize_overrides(overrides)
    findings: list[Finding] = []

    for name, check in sorted(_CHECKS.items()):
        spec = settings.get(name) or {}
        severity = Severity(spec.get("severity", "warn"))
        if severity is Severity.OFF:
            continue
        finding = check(context, spec)
        if finding is None:
            continue
        # The config decides severity; the check decides whether it fired.
        #
        # Config can only tighten. `allow_override: true` used to re-open a check
        # the code had declared closed, because this read
        # `spec.get("allow_override", finding.overridable)` and the config value
        # won outright. G3, G6, G12 and G13 pass `overridable=False` precisely
        # because they are arithmetic rather than judgment, and base.py says so;
        # a line in a YAML file should not be able to contradict that. The
        # shipped config happens to say false for all four, so this was latent,
        # but the invariant was not the authority it claimed to be.
        overridable = finding.overridable and spec.get("allow_override", True)
        findings.append(
            Finding(
                guardrail=name,
                severity=severity,
                message=finding.message,
                detail=finding.detail,
                remedy=finding.remedy,
                overridable=bool(overridable),
            )
        )

    unresolved = [
        f
        for f in findings
        if f.severity is Severity.BLOCK
        and not (f.overridable and f.guardrail in applied)
    ]
    if unresolved and blocking:
        raise GuardrailBlocked(unresolved)

    used = [applied[f.guardrail] for f in findings if f.guardrail in applied]
    return findings, used


def _normalize_overrides(
    overrides: Iterable[Override] | dict[str, str] | None,
) -> dict[str, Override]:
    if overrides is None:
        return {}
    if isinstance(overrides, dict):
        return {k: Override(k, v) for k, v in overrides.items()}
    return {o.guardrail: o for o in overrides}


def summarize(findings: list[Finding], overrides: list[Override]) -> dict[str, Any]:
    """The block a run record stores, so a result carries what was checked."""
    return {
        "checks_run": list(registered_checks()),
        "findings": [
            {
                "guardrail": f.guardrail,
                "severity": f.severity.value,
                "message": f.message,
                "detail": f.detail,
            }
            for f in findings
        ],
        "overrides": [{"guardrail": o.guardrail, "reason": o.reason} for o in overrides],
    }
