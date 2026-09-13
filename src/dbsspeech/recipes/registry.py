"""The recipe registry.

A recipe is declared once with a typed parameter model and becomes callable from
Python, the CLI, the API, and the agent. One implementation, one set of
guardrails, one run record, whatever called it.

`run` is the only sanctioned entry point. It checks the QC gate, evaluates
guardrails before anything is computed, opens a run record, calls the recipe, and
writes the outputs. Calling a recipe function directly bypasses all four, which is
why the registry does the orchestration rather than the recipe.

The gate is checked first, before guardrails and before the run record, so an
unreviewed subject produces no directory, no record, and no partial output.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from ..guardrails import CheckContext, run_checks, summarize
from ..io import filenames_deidentified_for
from ..io.loader import Session, open_session
from ..manifest import load_configs, load_manifest
from ..qc import applied_actions, require_approved
from ..qc.gate import status as qc_status
from ..runs import index_run, record

DEFAULT_DERIVATIVES = Path(__file__).resolve().parents[3] / "derivatives"


@dataclass
class RecipeContext:
    """What a recipe is given. It reads; the registry writes."""

    session: Session
    configs: dict[str, Any]
    run: Any
    params: BaseModel

    @property
    def out_dir(self) -> Path:
        return self.run.out_dir

    def log(self, message: str) -> None:
        self.run.log(message)


@dataclass
class RecipeResult:
    """What a recipe returns."""

    tables: dict[str, Any] = field(default_factory=dict)
    figures: list[Path] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    # There is deliberately no `guardrail_context` here. It used to exist, and
    # two recipes filled it in at the end of a run, which reads as though the
    # guardrails saw the result. Nothing consumed it, so those two ran against
    # two of thirteen checks for as long as the field was accepted. Guardrails
    # are evaluated before anything is computed, from `fn.guardrail_context`;
    # passing one here is now a TypeError at the call site rather than eleven
    # checks quietly returning nothing.


@dataclass(frozen=True)
class Recipe:
    name: str
    description: str
    params_model: type[BaseModel]
    fn: Callable[[RecipeContext], RecipeResult]
    version: str = "1"
    # The question a person would actually ask, in their words. `psd_by_condition`
    # means nothing on someone's first run; "which frequencies are stronger in one
    # condition than another" does. The agent matches against this to choose a
    # recipe, and the run screen offers these rather than function names. Empty
    # falls back to the description, so a recipe without one still works.
    question: str = ""
    # What lands in the run directory, in words, so the answer to "what will I
    # get" does not require running it once to find out.
    produces: str = ""

    def schema(self) -> dict[str, Any]:
        """The parameter schema, with the recipe's own labels and grouping folded in.

        Pydantic titles a field by title-casing its name, which turns
        `sfreq_target_hz` into "Sfreq Target Hz". A recipe can do better by
        declaring `LABELS`, and can say which handful of its parameters a person
        actually has to decide by declaring `ESSENTIAL`. Both are optional: a
        recipe that declares neither behaves exactly as before, which is what
        keeps this from being a flag day for every recipe ever written.

        Folded in here rather than written into each `Field(...)` so that the
        labels sit together in one readable block next to the parameters they
        name, and so that adding this cost no recipe a forty-line diff.
        """
        schema = self.params_model.model_json_schema()
        labels: dict[str, str] = getattr(self.params_model, "LABELS", {})
        essential: tuple[str, ...] = getattr(self.params_model, "ESSENTIAL", ())
        for name, prop in (schema.get("properties") or {}).items():
            if name in labels:
                prop["title"] = labels[name]
            if essential:
                # Only when the recipe has said which are which. Absent that,
                # the interface shows everything rather than guessing that a
                # parameter is advanced because nobody got round to saying.
                prop["x-group"] = "essential" if name in essential else "advanced"
        return schema

    def asked_as(self) -> str:
        return self.question or self.description


_RECIPES: dict[str, Recipe] = {}


def recipe(
    name: str,
    description: str,
    params: type[BaseModel],
    version: str = "1",
    question: str = "",
    produces: str = "",
) -> Callable[[Callable[[RecipeContext], RecipeResult]], Callable]:
    """Register an analysis under `name`.

    Changing behavior means bumping `version`, not editing history.
    """

    def decorator(fn: Callable[[RecipeContext], RecipeResult]) -> Callable:
        if name in _RECIPES:
            raise ValueError(f"recipe {name!r} is already registered")
        _RECIPES[name] = Recipe(name, description, params, fn, version, question, produces)
        return fn

    return decorator


def available() -> tuple[str, ...]:
    return tuple(sorted(_RECIPES))


def get(name: str) -> Recipe:
    try:
        return _RECIPES[name]
    except KeyError:
        raise KeyError(f"unknown recipe {name!r}; registered: {available()}") from None


def describe_all() -> list[dict[str, Any]]:
    """Name, description, and JSON schema per recipe. The UI builds forms from this."""
    out = []
    for r in (_RECIPES[n] for n in available()):
        entry = {
            "name": r.name,
            "description": r.description,
            "question": r.asked_as(),
            "produces": r.produces,
            "version": r.version,
            "params_schema": r.schema(),
        }
        # A recipe may explain its own choices. The interface renders these
        # beside the corresponding field rather than leaving a bare enum.
        explain = getattr(r.fn, "option_explanations", None)
        if explain is not None:
            entry["option_explanations"] = explain()
        out.append(entry)
    return out


def _window_span_s(rows: list[dict[str, Any]]) -> float | None:
    """Elapsed time from the first window's start to the last window's end.

    Returns None rather than a wrong number when the manifest does not carry
    usable times, since a guardrail message that quotes a fabricated duration is
    worse than one that quotes none.
    """
    starts, ends = [], []
    for row in rows:
        for key, sink in (("t_start_s", starts), ("t_end_s", ends)):
            try:
                sink.append(float(row[key]))
            except (KeyError, TypeError, ValueError):
                return None
    if not starts or not ends:
        return None
    span = max(ends) - min(starts)
    return span if span > 0 else None


def _prepare_guardrail_context(
    name: str, params: BaseModel, session: Session, extra: dict[str, Any]
) -> CheckContext:
    """Everything the checks can see before the recipe runs."""
    p = params.model_dump()
    conditions = tuple(extra.get("conditions") or session.conditions())
    # Only the windows this run actually reads. Judging a run on windows it never
    # touched produces a warning nobody can act on, which is how a check becomes
    # noise people learn to ignore.
    rows = extra.get("window_rows")
    if rows is None:
        rows = [r for r in session.windows() if r["condition"] in conditions]
    skip = {"conditions", "window_rows"}
    fields = {k: v for k, v in extra.items() if k not in skip}
    # G9 compares a baseline excursion to a reported effect. That ratio is not
    # comparable between runs of different length, because an excursion grows
    # with elapsed time whenever the baseline is closer to a random walk than to
    # a bounded process. So the duration travels with the ratio.
    #
    # The span from the first window's start to the last window's end, not the
    # sum of the window durations: drift accumulates during the gaps between
    # windows as well as inside them, and it is the elapsed time that sets how
    # far the baseline can have wandered.
    fields.setdefault("recording_duration_s", _window_span_s(rows))
    return CheckContext(
        recipe=name,
        params=p,
        conditions=conditions,
        window_rows=rows,
        **fields,
    )


def run(
    name: str,
    study_id: str,
    session_id: str,
    claim: str,
    params: BaseModel | dict[str, Any] | None = None,
    user: str | None = None,
    overrides: dict[str, str] | None = None,
    manifest_dir: Path | None = None,
    data_dir: Path | None = None,
    runs_dir: Path | None = None,
    derivatives_dir: Path | None = None,
) -> str:
    """Run a recipe with provenance and guardrails. Returns the run id.

    Guardrails are evaluated before the run record is opened, so a blocked run
    produces no directory and no record: there is nothing to mistake for a
    result.
    """
    spec = get(name)
    model = params if isinstance(params, BaseModel) else spec.params_model(**(params or {}))
    manifest = load_manifest(manifest_dir)
    configs = load_configs()

    derivatives = Path(derivatives_dir) if derivatives_dir else DEFAULT_DERIVATIVES
    # The gate comes first: an unreviewed subject must produce no directory, no
    # record, and no partial output. Turning it off is a deliberate config change.
    qc_config = configs.get("qc_thresholds") or {}
    if qc_config.get("enforce_gate", True):
        require_approved(study_id, derivatives)

    with open_session(
        study_id, session_id, manifest=manifest, configs=configs, data_dir=data_dir
    ) as session:
        # Apply what QC approved, before the recipe sees the data. The session
        # reports what actually took effect, which is what the record stores.
        qc_effective = session.apply_qc(applied_actions(study_id, derivatives))

        precheck = getattr(spec.fn, "guardrail_context", None)
        extra = precheck(session, model) if precheck else {}
        context = _prepare_guardrail_context(name, model, session, extra)
        findings, applied = run_checks(context, overrides=overrides)

        with record(
            name,
            model,
            claim,
            user=user,
            runs_dir=runs_dir,
            derivatives_dir=derivatives_dir,
        ) as run_handle:
            run_handle.guardrails = summarize(findings, applied)
            # What QC decided, carried on the result so a reader knows which
            # channels and windows were removed and who removed them.
            run_handle.qc = {
                "status": qc_status(study_id, derivatives),
                "enforced": bool(qc_config.get("enforce_gate", True)),
                "applied": qc_effective,
                "annotations": session.qc_annotations,
            }
            run_handle.snapshot_config(
                {
                    "recipe": {"name": name, "version": spec.version},
                    "params": model.model_dump(),
                    **configs,
                }
            )
            # The policy travels with the call. `add_input` records a location
            # only when the site has declared filenames safe for this format;
            # otherwise the hash and the manifest key identify the input and the
            # filename is never written down. Guardrail G13 is told the same
            # answer, so the check and the writer cannot disagree.
            run_handle.add_input(
                session.recording.path,
                key={"study_id": study_id, "session": session_id},
                filenames_deidentified=filenames_deidentified_for(
                    configs.get("privacy") or {}, session.recording.format
                ),
            )
            for finding in findings:
                run_handle.log(f"guardrail {finding.guardrail}: {finding.message}")

            result = spec.fn(RecipeContext(session, configs, run_handle, model))
            run_handle.summary = result.summary
            for figure in result.figures:
                run_handle.add_output(figure)

            # A second pass, for the rules that cannot be decided from a plan.
            # G9 compares a baseline excursion to the effect a run reports, and
            # neither number exists until the recipe has produced one, so the
            # pre-run pass above can never evaluate it.
            #
            # This pass does not block. The result already exists, so refusing
            # would leave a half-written record without un-computing anything.
            after = getattr(spec.fn, "guardrail_context_after", None)
            if after is not None:
                post = after(session, model, result) or {}
                if post:
                    post_context = _prepare_guardrail_context(
                        name, model, session, {**extra, **post}
                    )
                    post_findings, post_applied = run_checks(
                        post_context, overrides=overrides, blocking=False
                    )
                    # Every check runs again in the second pass, so a rule that
                    # already fired before the recipe would be reported twice.
                    # Keep only what the result made newly decidable, or the
                    # record reads as though the run tripped the same guardrail
                    # twice.
                    already = {f.guardrail for f in findings}
                    post_findings = [f for f in post_findings if f.guardrail not in already]
                    for finding in post_findings:
                        run_handle.log(
                            f"guardrail {finding.guardrail} (after the run): "
                            f"{finding.message}"
                        )
                    # Kept beside the pre-run block rather than merged into it,
                    # so a reader can tell which findings were knowable before
                    # the data was touched and which needed the result.
                    run_handle.guardrails = {
                        **run_handle.guardrails,
                        "after": summarize(post_findings, post_applied),
                    }

    # The index is a mirror of runs/*.json and can always be rebuilt, so a
    # failure to write it must not fail a run that already produced its record.
    with contextlib.suppress(Exception):
        index_run(run_handle.to_dict(), db_path=_db_path(derivatives_dir))
    return run_handle.run_id


def _db_path(derivatives_dir: Path | None) -> Path | None:
    return Path(derivatives_dir) / "runs.db" if derivatives_dir else None
