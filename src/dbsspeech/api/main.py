"""FastAPI surface: subjects, recipes, runs, uploads, and the agent.

Thin by design. Every route validates with Pydantic and delegates to the package,
so the scientific logic and the QC gate exist in exactly one place. The interface
reflects them; it never reimplements them.

Bound to localhost and unauthenticated. Auth arrives in Phase 4, and nothing here
should be exposed to a network before it does.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as package_version
from pathlib import Path
from typing import Any

import yaml
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.datastructures import Headers
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __name__ as PACKAGE
from ..agent import propose
from ..auth import AuthError, User, user_for_token
from ..auth import login as auth_login
from ..auth import logout as auth_logout
from ..auth.store import DEFAULT_DB as AUTH_DB
from ..configs_admin import (
    ConfigError,
    diff_versions,
    list_configs,
    list_versions,
    read_config,
    read_version,
    validate_config,
    write_config,
)
from ..guardrails import GuardrailBlocked
from ..io.loader import open_session
from ..jobs import queue as jobs
from ..jobs.worker import validate_job
from ..manifest import load_configs, load_manifest, validate
from ..qc import (
    QCNotApproved,
    build_model,
    decide,
    load_decisions,
    read_history,
    save_decisions,
    select,
    undecided,
    write_report,
)
from ..qc import propose as qc_propose
from ..qc import reopen as qc_reopen
from ..qc import sign as qc_sign
from ..qc import status as qc_status
from ..recipes import describe_all
from ..recipes import get as get_recipe
from ..recipes import run as run_recipe
from ..runs import build_bundle, get_run, list_runs, reindex, versions
from . import errors

REPO_ROOT = Path(__file__).resolve().parents[3]


def _env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default)))


DATA_DIR = _env_path("DBSSPEECH_DATA", REPO_ROOT / "data")
DERIVATIVES_DIR = _env_path("DBSSPEECH_DERIVATIVES", REPO_ROOT / "derivatives")
RUNS_DIR = _env_path("DBSSPEECH_RUNS", REPO_ROOT / "runs")
UPLOAD_DIR = _env_path("DBSSPEECH_UPLOADS", REPO_ROOT / "data" / "uploads")
MAX_UPLOAD_BYTES = int(os.environ.get("DBSSPEECH_MAX_UPLOAD_BYTES", 8 * 1024**3))

# Where runs execute. "queue" hands the work to a `dbsspeech worker` process and
# is the only mode fit to be deployed: a run survives an API restart and its
# status is readable by every process. "background" keeps the Phase 1 behavior of
# running inside the web process, which is convenient when you are working alone
# on one machine and do not want a second terminal.
EXECUTOR = os.environ.get("DBSSPEECH_EXECUTOR", "queue").strip().lower()
if EXECUTOR not in {"queue", "background"}:
    raise RuntimeError(
        f"DBSSPEECH_EXECUTOR={EXECUTOR!r} is not understood; use 'queue' or 'background'"
    )

# Built front end, served by the API so a deployment is one origin and one port.
# Absent in development, where Vite serves it and proxies /api here.
WEB_DIST = _env_path("DBSSPEECH_WEB_DIST", REPO_ROOT / "web" / "dist")

# Auth is off for single-user local work and must be on for anything reachable by
# another machine. `serve` refuses to bind to a non-localhost host without it,
# which is the property that actually matters: the failure mode here is not a
# weak password, it is an unauthenticated app on a hospital network.
REQUIRE_AUTH = os.environ.get("DBSSPEECH_REQUIRE_AUTH", "").lower() in {"1", "true", "yes"}
SESSION_COOKIE = "dbsspeech_session"

# When auth is off every request is this notional user, so attribution still has
# a value and the code path is the same either way.
LOCAL_USER = User(id=0, name="local", email="local@localhost", role="admin")

# Formats the reader layer can open, by extension.
UPLOAD_SUFFIXES = {".mat": "tdt_mat", ".tsq": "tdt_tank", ".tev": "tdt_tank",
                   ".vhdr": "brainvision", ".eeg": "brainvision", ".vmrk": "brainvision"}

# FastAPI's File() must not be constructed in a default argument each call.
_UPLOAD_FILE = File(...)

try:
    APP_VERSION = package_version("analyzedbs")
except PackageNotFoundError:  # pragma: no cover - only when run from a source tree
    APP_VERSION = "unknown"

app = FastAPI(
    title="dbsspeech",
    description="Lab-internal analysis for intraoperative DBS and ECoG recordings.",
    version=APP_VERSION,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-process run status, used only by the "background" executor. The queue keeps
# its status in the database, where a second process can read it.
_status: dict[str, dict[str, Any]] = {}


def _jobs_db() -> Path:
    """Read at call time, because tests point DERIVATIVES_DIR somewhere empty."""
    return DERIVATIVES_DIR / "runs.db"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    recipe: str
    study_id: str
    session: str
    claim: str = Field(min_length=1, description="One sentence: what this run is meant to show.")
    params: dict[str, Any] = Field(default_factory=dict)
    overrides: dict[str, str] = Field(
        default_factory=dict,
        description="Guardrail name to reason. An override without a reason is refused.",
    )
    user: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


def current_user(request: Request) -> User:
    """The signed-in user, or the local user when auth is off."""
    if not REQUIRE_AUTH:
        return LOCAL_USER
    user = user_for_token(request.cookies.get(SESSION_COOKIE, ""))
    if user is None:
        raise HTTPException(401, "not signed in")
    return user


def require_role(role: str):
    """Dependency factory. Roles are ordered, so this means 'at least'."""

    def dependency(user: User = Depends(current_user)) -> User:
        if not user.can(role):
            raise HTTPException(
                403, f"this needs the {role} role or above; you have {user.role}"
            )
        return user

    return dependency


class DecisionUpdate(BaseModel):
    flag_id: str
    approved: bool
    reviewer: str = Field(min_length=1, description="An anonymous decision is not one.")
    reason: str = ""
    action_taken: str | None = None


class BulkDecision(BaseModel):
    """A bulk decision must state what it covers. There is deliberately no 'all'."""

    approved: bool
    reviewer: str = Field(min_length=1)
    reason: str = ""
    flag_type: str | None = None
    severity: str | None = None
    target: str | None = None


class SignRequest(BaseModel):
    reviewer: str = Field(min_length=1)


class ReopenRequest(BaseModel):
    reviewer: str = Field(min_length=1)
    reason: str = Field(min_length=1, description="Why a signed subject is reconsidered.")


class ConfigWrite(BaseModel):
    text: str
    reason: str = Field(min_length=1,
                        description="Why this change. A threshold with no rationale "
                                    "is the thing nobody can defend later.")


class AgentRequest(BaseModel):
    question: str
    study_id: str | None = None
    session: str | None = None
    recipe: str | None = Field(
        default="psd_by_condition",
        description="None means let the agent choose from the question.",
    )
    params: dict[str, Any] = Field(
        default_factory=dict,
        description="Values already chosen. They win over anything inferred, and "
                    "the guardrail dry-run then describes the run you would "
                    "actually start rather than the one the agent suggested.",
    )
    cleared: list[str] = Field(
        default_factory=list,
        description="Fields emptied on purpose. Nothing is inferred for them, so "
                    "the recipe's own default applies. Emptying a field is a "
                    "decision; filling it back in would overrule it.",
    )


class OnboardingInspectRequest(BaseModel):
    path: str
    study_id: str | None = None
    session: str | None = None


class OnboardingCommitRequest(BaseModel):
    """Rows a person confirmed in the wizard, not rows a detector guessed."""

    rows: dict[str, list[dict[str, Any]]]
    dry_run: bool = False


# ---------------------------------------------------------------------------
# Health and manifests
# ---------------------------------------------------------------------------

def _database_health(path: Path) -> dict[str, Any]:
    """Can this database actually be opened and read, not merely does it exist.

    A missing file is normal on a first start, since every store creates its own
    tables. A file that exists and cannot be opened is the interesting case: a
    volume mounted read-only, or a permission mismatch between the container user
    and the host directory. That is a deployment error worth naming.
    """
    import sqlite3

    if not path.exists():
        return {"path": str(path), "present": False, "ok": True,
                "note": "not created yet; it appears on first use"}
    try:
        with contextlib.closing(sqlite3.connect(path, timeout=5.0)) as conn:
            conn.execute("SELECT 1").fetchone()
    except sqlite3.Error as exc:
        return {"path": str(path), "present": True, "ok": False, "note": str(exc)}
    return {"path": str(path), "present": True, "ok": True, "note": ""}


@app.get("/health")
def health() -> dict[str, Any]:
    """Everything an operator needs to answer "is this thing working".

    Reports only. It never reaps a stale job or repairs anything, because a
    monitoring endpoint that changes state gives you a system whose behavior
    depends on who last looked at it.
    """
    report = validate(load_manifest())
    queue = jobs.queue_health(db_path=_jobs_db())
    databases = {
        "runs": _database_health(_jobs_db()),
        "accounts": _database_health(AUTH_DB),
    }
    ok = report.ok and queue["healthy"] and all(d["ok"] for d in databases.values())
    return {
        "package": PACKAGE,
        "ok": ok,
        "versions": {"app": APP_VERSION, **versions()},
        "manifest_valid": report.ok,
        "manifest_errors": report.errors,
        "manifest_warnings": report.warnings,
        "data_dir_present": DATA_DIR.exists(),
        "auth_required": REQUIRE_AUTH,
        "executor": EXECUTOR,
        "databases": databases,
        "queue": queue,
    }


@app.get("/subjects")
def subjects() -> list[dict[str, Any]]:
    """Recordings in the manifest, with what is known about each."""
    manifest = load_manifest()
    out = []
    for row in manifest.subjects:
        sid, ses = row["study_id"], row["session"]
        channels = manifest.channels_for(sid, ses)
        included = [c for c in channels if c.get("include", "").lower() == "true"]
        windows = [
            w for w in manifest.windows
            if w["study_id"] == sid and w["session"] == ses
        ]
        out.append(
            {
                **row,
                "n_channels": len(channels),
                "n_channels_included": len(included),
                "leads": [
                    {"lead_id": lr["lead_id"], "target": lr["target"],
                     "lead_model": lr["lead_model"],
                     "rotation_known": bool(lr.get("rotation_deg", "").strip())}
                    for lr in manifest.leads
                    if (lr["study_id"], lr["session"]) == (sid, ses)
                ],
                "conditions": [
                    {"condition": w["condition"], "status": w["status"],
                     "derived_from": w["derived_from"],
                     "duration_s": float(w["t_end_s"]) - float(w["t_start_s"])}
                    for w in windows
                ],
                "qc_status": qc_status(sid, DERIVATIVES_DIR),
            }
        )
    return out


@app.get("/recipes")
def recipes() -> list[dict[str, Any]]:
    """Recipes with their parameter schemas and the words explaining each choice."""
    return describe_all()


@app.get("/configs/{name}")
def config(name: str) -> dict[str, Any]:
    """A config file, so the interface can show thresholds it did not hardcode."""
    path = REPO_ROOT / "configs" / f"{name}.yaml"
    if not path.exists() or path.parent != REPO_ROOT / "configs":
        raise HTTPException(404, f"no config {name!r}")
    return yaml.safe_load(path.read_text())


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@app.post("/agent/propose")
def agent_propose(request: AgentRequest) -> dict[str, Any]:
    """Turn a plain-language request, or a set of chosen values, into a proposal.

    Deterministic and local. Nothing about a recording leaves the machine.

    Called at three points in a run, which is why it takes both a question and
    parameters: to choose a recipe from what someone asked, to explain the values
    it suggests, and to re-check the values they then edited. The last of those
    is what makes the review step honest, since the guardrails are evaluated
    against what is about to run.
    """
    if request.recipe is not None:
        try:
            get_recipe(request.recipe)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from None

    configs = load_configs()
    for extra in ("bands", "statistics"):
        path = REPO_ROOT / "configs" / f"{extra}.yaml"
        if path.exists():
            configs[extra] = yaml.safe_load(path.read_text())

    session = None
    try:
        if request.study_id and request.session:
            session = open_session(request.study_id, request.session, data_dir=DATA_DIR)
        proposal = propose(request.question, session=session, configs=configs,
                           recipe=request.recipe, params=request.params,
                           cleared=request.cleared).to_dict()
        # What the chosen recipe is for and what it writes, so the review step
        # can say what you are about to get without a second request.
        spec = get_recipe(proposal["recipe"])
        proposal["asks"] = spec.asked_as()
        proposal["produces"] = spec.produces
        return proposal
    finally:
        if session is not None:
            session.close()


# ---------------------------------------------------------------------------
# Onboarding
# ---------------------------------------------------------------------------

@app.post("/onboarding/inspect")
def onboarding_inspect(request: OnboardingInspectRequest) -> dict[str, Any]:
    """Report what a recording or tree states about itself. Writes nothing.

    Every value here is a proposal. The response also names what was
    deliberately not proposed, so a caller cannot mistake an empty channels
    table for a complete one.
    """
    from ..onboarding import inspect as inspect_path

    target = Path(request.path).expanduser()
    if not target.exists():
        raise HTTPException(404, f"no such path: {target.name}")
    try:
        return inspect_path(target, request.study_id, request.session)
    except Exception as exc:
        raise HTTPException(400, f"{type(exc).__name__}: {exc}") from None


@app.post("/onboarding/create")
def onboarding_create(request: OnboardingCommitRequest) -> dict[str, Any]:
    """Merge confirmed rows into the manifest, or refuse and write nothing.

    422 carries the validation errors, because a caller that gets a 500 learns
    only that something went wrong, and the whole point is which invariant the
    rows broke.
    """
    from ..onboarding import CommitRefused
    from ..onboarding import commit as commit_rows

    try:
        return commit_rows(request.rows, dry_run=request.dry_run)
    except CommitRefused as exc:
        raise HTTPException(
            422, {"errors": exc.errors, "warnings": exc.warnings}
        ) from None
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from None


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

@app.post("/auth/login")
def auth_sign_in(request: LoginRequest, response: Response) -> dict[str, Any]:
    if not REQUIRE_AUTH:
        return {"user": LOCAL_USER.__dict__, "auth_required": False}
    try:
        token = auth_login(request.email, request.password)
    except AuthError as exc:
        raise HTTPException(401, str(exc)) from None
    # HTTP-only so page scripts cannot read it; SameSite=lax so it is not sent
    # from another site. Not marked secure, because deployment terminates TLS.
    response.set_cookie(SESSION_COOKIE, token, httponly=True, samesite="lax")
    user = user_for_token(token)
    return {"user": user.__dict__ if user else None, "auth_required": True}


@app.post("/auth/logout")
def auth_sign_out(request: Request, response: Response) -> dict[str, Any]:
    token = request.cookies.get(SESSION_COOKIE, "")
    if token:
        auth_logout(token)
    response.delete_cookie(SESSION_COOKIE)
    return {"ok": True}


@app.get("/auth/me")
def auth_me(user: User = Depends(current_user)) -> dict[str, Any]:
    return {"user": user.__dict__, "auth_required": REQUIRE_AUTH}


# ---------------------------------------------------------------------------
# Quality control
# ---------------------------------------------------------------------------

def _qc_payload(study_id: str) -> dict[str, Any]:
    rows = load_decisions(study_id, DERIVATIVES_DIR)
    return {
        "study_id": study_id,
        "status": qc_status(study_id, DERIVATIVES_DIR),
        "n_flags": len(rows),
        "n_undecided": len(undecided(rows)),
        "decisions": rows,
        "history": read_history(study_id, DERIVATIVES_DIR),
        "report_available": (
            DERIVATIVES_DIR / "qc" / f"sub-{study_id}" / "report.html"
        ).exists(),
    }


@app.get("/qc/vocabulary")
def qc_vocabulary() -> dict[str, Any]:
    """What a flag means and what may be done about it.

    Served from `configs/qc_thresholds.yaml` rather than written into the review
    screen, so the words somebody reads while deciding are the lab's own and a
    change to them is a config edit with an author and a reason.

    Declared before `/qc/{study_id}` so the literal path wins over the parameter.
    """
    config = load_configs().get("qc_thresholds") or {}
    actions = config.get("actions") or {}
    # Detectors, plus the flag types that no detector owns. The peer-comparison
    # detectors emit `insufficient_channels` when they cannot judge, and it
    # reached a reviewer as that bare string until it was given words here.
    described = {**(config.get("detectors") or {}), **(config.get("flag_types") or {})}
    return {
        "actions": [
            {"value": name, "label": spec.get("label", name),
             "description": spec.get("description", "")}
            for name, spec in actions.items()
        ],
        "detectors": {
            name: {"label": spec.get("label", name), "means": spec.get("means", "")}
            for name, spec in described.items()
        },
    }


@app.get("/qc/{study_id}")
def qc_detail(study_id: str) -> dict[str, Any]:
    return _qc_payload(study_id)


@app.post("/qc/{study_id}/propose")
def qc_run_detection(study_id: str, session: str = "ses1") -> dict[str, Any]:
    """Run detection and write the report. Reviewer columns are preserved."""
    from ..cli import _qc_collect

    try:
        data, sfreq, names, regions, flags, windows = _qc_collect(study_id, session)
    except (KeyError, FileNotFoundError) as exc:
        raise HTTPException(404, str(exc)) from None
    qc_propose(flags, study_id, DERIVATIVES_DIR)
    model = build_model(study_id, session, data, sfreq, names, regions, flags, windows)
    write_report(model, DERIVATIVES_DIR)
    return {"n_flags": len(flags), **_qc_payload(study_id)}


@app.put("/qc/{study_id}/decisions")
def qc_decide(
    study_id: str, update: DecisionUpdate,
    user: User = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    rows = load_decisions(study_id, DERIVATIVES_DIR)
    try:
        rows = decide(rows, update.flag_id, update.approved, update.reviewer,
                      update.reason, update.action_taken)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        # Rejecting or changing an action without a reason.
        raise HTTPException(422, str(exc)) from None
    save_decisions(study_id, rows, DERIVATIVES_DIR)
    return _qc_payload(study_id)


@app.post("/qc/{study_id}/decisions/bulk")
def qc_decide_bulk(
    study_id: str, bulk: BulkDecision,
    user: User = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    if not (bulk.flag_type or bulk.severity or bulk.target):
        raise HTTPException(
            422,
            "a bulk decision needs a scope: flag_type, severity or target. "
            "The history has to show what was actually looked at.",
        )
    rows = load_decisions(study_id, DERIVATIVES_DIR)
    matched = select(rows, flag_type=bulk.flag_type, severity=bulk.severity,
                     target=bulk.target)
    reason = bulk.reason or f"bulk decision by scope, {len(matched)} flag(s)"
    try:
        for row in matched:
            rows = decide(rows, row["flag_id"], bulk.approved, bulk.reviewer, reason)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    save_decisions(study_id, rows, DERIVATIVES_DIR)
    return {"n_decided": len(matched), **_qc_payload(study_id)}


@app.post("/qc/{study_id}/sign")
def qc_sign_off(
    study_id: str, request: SignRequest,
    user: User = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    try:
        approval = qc_sign(study_id, request.reviewer, DERIVATIVES_DIR)
    except QCNotApproved as exc:
        raise HTTPException(409, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {"approval": approval, **_qc_payload(study_id)}


@app.post("/qc/{study_id}/reopen")
def qc_reopen_subject(
    study_id: str, request: ReopenRequest,
    user: User = Depends(require_role("reviewer")),
) -> dict[str, Any]:
    try:
        qc_reopen(study_id, request.reviewer, request.reason, DERIVATIVES_DIR)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return _qc_payload(study_id)


@app.get("/qc/{study_id}/report")
def qc_report(study_id: str) -> FileResponse:
    path = DERIVATIVES_DIR / "qc" / f"sub-{study_id}" / "report.html"
    if not path.exists():
        raise HTTPException(404, "no report yet; run detection first")
    return FileResponse(path, media_type="text/html")


# ---------------------------------------------------------------------------
# Runs
# ---------------------------------------------------------------------------

@app.post("/runs", status_code=202)
def create_run(
    request: RunRequest, background: BackgroundTasks,
    user: User = Depends(require_role("analyst")),
) -> dict[str, Any]:
    """Validate, then hand the work to a worker. Returns a handle immediately.

    Validation is here so a wrong recipe name or parameter fails at the request,
    rather than minutes later in a worker log nobody is watching. Guardrails run
    inside the recipe, before anything is computed, so a blocked run reports its
    explanation instead of producing a partial result.
    """
    try:
        validate_job(request.recipe, request.params)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from None
    except Exception as exc:
        raise HTTPException(422, f"invalid parameters: {exc}") from None

    # Attribution comes from the session, not from a field the caller filled in.
    request.user = user.name

    if EXECUTOR == "background":
        return _run_in_this_process(request, background)

    job_id = jobs.enqueue(
        request.recipe, request.study_id, request.session, request.claim,
        params=request.params, overrides=request.overrides or None,
        user=request.user, db_path=_jobs_db(),
    )
    # A queued run with no worker looks identical to a queued run with a busy
    # one, so the answer says which it is at the moment of submission.
    note = jobs.queue_health(db_path=_jobs_db())["note"]
    return {"handle": job_id, "job_id": job_id, "status": "queued",
            "executor": "queue", "worker_note": note}


def _run_in_this_process(
    request: RunRequest, background: BackgroundTasks
) -> dict[str, Any]:
    """The development fallback: execute inside the web process.

    Kept because a single-machine session with no worker running is a reasonable
    way to work, and losing that would push people toward starting a worker they
    then forget to stop. Not fit for a deployment: this status dictionary dies
    with the process, and so does the run.
    """
    handle = f"pending_{len(_status) + 1}"
    _status[handle] = {"status": "queued", "run_id": None, "error": None}

    def execute() -> None:
        _status[handle]["status"] = "running"
        try:
            run_id = run_recipe(
                request.recipe, request.study_id, request.session,
                claim=request.claim, params=request.params,
                overrides=request.overrides or None, user=request.user,
                data_dir=DATA_DIR, runs_dir=RUNS_DIR, derivatives_dir=DERIVATIVES_DIR,
            )
            _status[handle].update(status="ok", run_id=run_id)
        except GuardrailBlocked as exc:
            _status[handle].update(
                status="blocked",
                error=str(exc),
                findings=[{"guardrail": f.guardrail, "severity": f.severity.value,
                           "message": f.message, "remedy": f.remedy,
                           "overridable": f.overridable} for f in exc.findings],
            )
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller
            _status[handle].update(status="failed", error=str(exc))

    background.add_task(execute)
    return {"handle": handle, "status": "queued", "executor": "background",
            "worker_note": "running inside the API process; it will not survive a restart"}


@app.get("/runs/status/{handle}")
def run_status(handle: str) -> dict[str, Any]:
    """Status of a submitted run, whichever executor took it."""
    job = jobs.get_job(handle, _jobs_db())
    if job is not None:
        # A failure recorded by a worker is a class name and a message. The run
        # screen shows it, so it gets the same explanation an HTTP error would.
        explained = errors.explain_text(job["error"] or "") if job["error"] else None
        return {
            "handle": handle, "status": job["status"], "run_id": job["run_id"],
            "error": job["error"], "findings": job["findings"],
            "explanation": explained,
            "recipe": job["recipe"], "study_id": job["study_id"],
            "enqueued_at": job["enqueued_at"], "started_at": job["started_at"],
            "finished_at": job["finished_at"], "worker": job["claimed_by"],
        }
    if handle in _status:
        return {"handle": handle, **_status[handle]}
    raise HTTPException(404, f"no such handle {handle!r}")


@app.get("/jobs")
def list_queue(status: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
    """The queue itself. What the status page shows, and what a run's wait means."""
    return jobs.list_jobs(status=status, limit=limit, db_path=_jobs_db())


@app.get("/runs")
def runs(name: str | None = None, status: str | None = None, limit: int = 50) -> list[dict]:
    reindex(RUNS_DIR, DERIVATIVES_DIR / "runs.db")
    rows = list_runs(name=name, status=status, limit=limit,
                     db_path=DERIVATIVES_DIR / "runs.db")
    for row in rows:
        row.pop("record", None)
    return rows


@app.get("/runs/{run_id}")
def run_detail(run_id: str) -> dict[str, Any]:
    record = get_run(run_id, DERIVATIVES_DIR / "runs.db")
    if record is None:
        path = RUNS_DIR / f"{run_id}.json"
        if not path.exists():
            raise HTTPException(404, f"no run {run_id!r}")
        record = json.loads(path.read_text())
    return record


@app.get("/runs/{run_id}/tables/{name}")
def run_table(run_id: str, name: str, limit: int = 500, offset: int = 0) -> dict[str, Any]:
    """A page of one output table, so a large CSV does not have to load whole."""
    import pandas as pd

    base = (DERIVATIVES_DIR / "results" / run_id).resolve()
    for suffix in (".csv", ".parquet", ""):
        candidate = (base / f"{name}{suffix}").resolve()
        if candidate.is_relative_to(base) and candidate.is_file():
            break
    else:
        raise HTTPException(404, f"no table {name!r} in run {run_id!r}")

    frame = (
        pd.read_parquet(candidate)
        if candidate.suffix == ".parquet"
        else pd.read_csv(candidate)
    )
    page = frame.iloc[offset : offset + limit]
    return {
        "name": candidate.name,
        "columns": list(frame.columns),
        "n_rows": int(len(frame)),
        "offset": offset,
        "rows": json.loads(page.to_json(orient="records")),
    }


@app.get("/compare")
def compare(a: str, b: str) -> dict[str, Any]:
    """Two runs side by side, with the parameters that differ called out.

    The diff is the point: "which settings did you use" becomes a lookup rather
    than a conversation.
    """
    records = {}
    for run_id in (a, b):
        record = get_run(run_id, DERIVATIVES_DIR / "runs.db")
        if record is None:
            path = RUNS_DIR / f"{run_id}.json"
            if not path.exists():
                raise HTTPException(404, f"no run {run_id!r}")
            record = json.loads(path.read_text())
        records[run_id] = record

    ra, rb = records[a], records[b]
    pa, pb = ra.get("params", {}), rb.get("params", {})
    keys = sorted(set(pa) | set(pb))
    param_diff = [
        {"param": k, "a": pa.get(k), "b": pb.get(k), "changed": pa.get(k) != pb.get(k)}
        for k in keys
    ]

    def figures(record: dict[str, Any]) -> list[str]:
        return sorted(o for o in record.get("outputs", []) if o.endswith(".png"))

    shared = sorted(set(figures(ra)) & set(figures(rb)))
    return {
        "a": {"run_id": a, "claim": ra.get("claim"), "recipe": ra.get("name"),
              "status": ra.get("status"), "git_commit": ra.get("git_commit"),
              "git_dirty": ra.get("git_dirty"), "summary": ra.get("summary", {}),
              "figures": figures(ra)},
        "b": {"run_id": b, "claim": rb.get("claim"), "recipe": rb.get("name"),
              "status": rb.get("status"), "git_commit": rb.get("git_commit"),
              "git_dirty": rb.get("git_dirty"), "summary": rb.get("summary", {}),
              "figures": figures(rb)},
        "params": param_diff,
        "n_changed": sum(1 for row in param_diff if row["changed"]),
        "shared_figures": shared,
        "same_recipe": ra.get("name") == rb.get("name"),
        # Comparing across code versions is legitimate but has to be visible.
        "same_code": ra.get("git_commit") == rb.get("git_commit"),
    }


# ---------------------------------------------------------------------------
# Config administration
# ---------------------------------------------------------------------------

@app.get("/admin/configs")
def admin_list_configs(user: User = Depends(require_role("admin"))) -> list[dict[str, Any]]:
    return list_configs()


@app.get("/admin/configs/{name}")
def admin_read_config(
    name: str, user: User = Depends(require_role("admin"))
) -> dict[str, Any]:
    try:
        return {
            "name": name,
            "text": read_config(name),
            "versions": [v.to_dict() for v in list_versions(name)],
        }
    except ConfigError as exc:
        raise HTTPException(404, str(exc)) from None


@app.post("/admin/configs/{name}/validate")
def admin_validate_config(
    name: str, body: ConfigWrite, user: User = Depends(require_role("admin"))
) -> dict[str, Any]:
    """Check without saving, so the editor can show errors as you type."""
    try:
        validate_config(name, body.text)
    except ConfigError as exc:
        return {"valid": False, "error": str(exc)}
    return {"valid": True, "error": None}


@app.put("/admin/configs/{name}")
def admin_write_config(
    name: str, body: ConfigWrite, user: User = Depends(require_role("admin"))
) -> dict[str, Any]:
    try:
        return write_config(name, body.text, author=user.name, reason=body.reason)
    except ConfigError as exc:
        raise HTTPException(422, str(exc)) from None


@app.get("/admin/configs/{name}/diff/{version_id}")
def admin_diff_config(
    name: str, version_id: str, user: User = Depends(require_role("admin"))
) -> dict[str, Any]:
    try:
        return {"name": name, "version_id": version_id,
                "diff": diff_versions(name, version_id)}
    except ConfigError as exc:
        raise HTTPException(404, str(exc)) from None


@app.get("/admin/configs/{name}/versions/{version_id}")
def admin_read_version(
    name: str, version_id: str, user: User = Depends(require_role("admin"))
) -> dict[str, Any]:
    try:
        return {"name": name, "version_id": version_id,
                "text": read_version(name, version_id)}
    except ConfigError as exc:
        raise HTTPException(404, str(exc)) from None


# ---------------------------------------------------------------------------
# Bundles
# ---------------------------------------------------------------------------

@app.get("/runs/{run_id}/bundle.zip")
def run_bundle(run_id: str) -> Response:
    """Everything needed to defend this result, in one file."""
    try:
        payload = build_bundle(run_id, runs_dir=RUNS_DIR,
                               derivatives_dir=DERIVATIVES_DIR)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{run_id}.zip"'},
    )


@app.get("/runs/{run_id}/files/{path:path}")
def run_file(run_id: str, path: str) -> FileResponse:
    """Serve a file from one run's output directory, and nowhere else."""
    base = (DERIVATIVES_DIR / "results" / run_id).resolve()
    target = (base / path).resolve()
    # Containment check before touching the filesystem: a crafted path must not
    # escape the run directory.
    if not target.is_relative_to(base):
        raise HTTPException(400, "path escapes the run directory")
    if not target.is_file():
        raise HTTPException(404, f"no file {path!r} in run {run_id!r}")
    return FileResponse(target)


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------

# Study IDs and session names reach the filesystem, so they are checked against
# what the manifest already allows rather than being trusted. Deliberately
# strict: letters, digits, underscore and hyphen. No dots, so no traversal, and
# no separators of any kind.
_IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def _check_identifier(field: str, value: str) -> None:
    if not _IDENTIFIER.fullmatch(value or ""):
        raise HTTPException(
            422,
            f"{field} must be 1 to 64 characters of letters, digits, underscore "
            f"or hyphen; got {value!r}",
        )


@app.post("/uploads", status_code=201)
async def upload(
    study_id: str, session: str, file: UploadFile = _UPLOAD_FILE,
    user: User = Depends(require_role("analyst")),
) -> dict[str, Any]:
    """Accept a recording file into an upload area under data/.

    Does NOT write a manifest row. The manifest is hand-curated and authoritative,
    and an upload is not a decision about what a channel is. The response says
    which format the reader would use and what still has to be filled in by hand.
    """
    # `study_id` and `session` used to be interpolated into the target path as
    # they arrived. The filename was reduced to its basename; the directories
    # were not, so `study_id="../../.."` resolved out of the upload area
    # entirely, and this endpoint required no role. An anonymous caller could
    # write a file with an allowed extension anywhere the process could write,
    # and the upload area is inside `data/`, which on many sites is a symlink
    # into cloud-synced storage.
    _check_identifier("study_id", study_id)
    _check_identifier("session", session)

    name = Path(file.filename or "").name
    suffix = Path(name).suffix.lower()
    if suffix not in UPLOAD_SUFFIXES:
        raise HTTPException(
            415,
            f"unsupported extension {suffix!r}; readers exist for "
            f"{sorted(set(UPLOAD_SUFFIXES))}",
        )
    if not name or name.startswith("."):
        raise HTTPException(400, "a file name is required")

    target_dir = UPLOAD_DIR / study_id / session
    target = target_dir / name
    # Belt and braces. The identifier check above is what actually stops this,
    # and this is what catches the next way somebody finds around it.
    if not target.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(400, "upload path escapes the upload area")
    target_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    with target.open("wb") as out:
        while chunk := await file.read(1 << 20):
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise HTTPException(413, f"file exceeds {MAX_UPLOAD_BYTES} bytes")
            out.write(chunk)

    return {
        "stored_as": str(target.relative_to(DATA_DIR)) if target.is_relative_to(DATA_DIR)
        else str(target),
        "bytes": written,
        "format": UPLOAD_SUFFIXES[suffix],
        "manifest_written": False,
        "next_steps": [
            "Add a subjects.csv row with this format and root_relpath.",
            "Add streams.csv, leads.csv and channels.csv rows; layout detection can "
            "propose lead geometry from the impedance export.",
            "Add windows.csv rows with derived_from set to whatever measured them.",
        ],
    }


@app.get("/uploads")
def list_uploads(
    user: User = Depends(require_role("analyst")),
) -> list[dict[str, Any]]:
    if not UPLOAD_DIR.exists():
        return []
    return [
        {
            "path": str(p.relative_to(UPLOAD_DIR)),
            "bytes": p.stat().st_size,
            "format": UPLOAD_SUFFIXES.get(p.suffix.lower()),
        }
        for p in sorted(UPLOAD_DIR.rglob("*"))
        if p.is_file()
    ]


# ---------------------------------------------------------------------------
# The built front end
# ---------------------------------------------------------------------------

class _SpaFiles(StaticFiles):
    """Static files, with client-side routes falling back to index.html.

    Vite builds one HTML file. `/qc/demo01` is a route inside it, not a file on
    disk, so reloading any page but the root would otherwise be a 404.

    Two things do not fall back, and both matter.

    A path whose last segment has an extension. Returning index.html for a
    missing `.js` turns a broken build into a blank page and a console error
    about unexpected HTML, which is a bad half hour for whoever has to work out
    what went wrong.

    A request that did not ask for HTML. This mount is last, so it also catches
    every API path that matched no route, and answering those with a page would
    turn a mistyped or malformed API call into a 200. The client-side routes
    that need the fallback (`/runs/<id>`, `/qc/<id>`) share their prefixes with
    API routes, so the path cannot be the discriminator. What the caller asked
    for can: a browser navigating sends `Accept: text/html`, and a fetch does
    not.
    """

    async def get_response(self, path: str, scope):  # noqa: ANN001, ANN201 - starlette's
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or "." in path.rsplit("/", 1)[-1]:
                raise
            if "text/html" not in Headers(scope=scope).get("accept", ""):
                raise
            return await super().get_response("index.html", scope)


def mount_web(application: FastAPI, dist: Path) -> bool:
    """Serve a built front end from this API. Returns whether there was one.

    Mounted last, so every API route above takes precedence. In development
    there is no build and this does nothing; Vite serves the app and proxies
    /api here.
    """
    if not (dist / "index.html").is_file():
        return False
    application.mount("/", _SpaFiles(directory=dist, html=True), name="web")
    return True


def build_root(api_app: FastAPI, dist: Path) -> FastAPI:
    """The application actually served: the API under /api, the app at the root.

    They cannot share a namespace. With the API's routes registered at the root,
    `/subjects` matches the API and returns JSON, so a browser reloading the
    subjects page, or anyone opening a shared link to it, gets a wall of JSON
    instead of the application. Four of the eight screens collided this way:
    /subjects, /runs, /runs/<id> and /qc/<id>.

    Development did not show it, because Vite serves the app there and proxies
    only /api onward, which is exactly the arrangement this now makes true in
    both places: the API lives at /api everywhere, and everything else is the
    front end.
    """
    root = FastAPI(
        title="dbsspeech",
        description="Lab-internal analysis for intraoperative DBS and ECoG recordings.",
        version=APP_VERSION,
    )
    root.mount("/api", api_app)
    mount_web(root, dist)
    return root


WEB_MOUNTED = mount_web(app, WEB_DIST)

# What `serve` runs. `app` itself stays mounted at the root of its own sub
# application, so tests and any direct caller keep working unchanged.
root_app = build_root(app, WEB_DIST)

# Registered after the routes, before serving. Routes that already catch an
# exception and raise HTTPException keep their own wording; these catch the ones
# that would otherwise reach the client as a 500 and a class name.
errors.install(app)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Run the API.

    Refuses to bind anywhere but localhost unless authentication is enabled. The
    failure mode worth preventing is not a weak password; it is an
    unauthenticated app answering on a hospital network because someone passed
    --host 0.0.0.0 to see it from another machine.
    """
    import uvicorn

    local = {"127.0.0.1", "localhost", "::1"}
    if host not in local and not REQUIRE_AUTH:
        raise RuntimeError(
            f"refusing to bind to {host!r} with authentication disabled. "
            "Set DBSSPEECH_REQUIRE_AUTH=true and create a user with "
            "`python -m dbsspeech users add`, or bind to 127.0.0.1."
        )
    # The root application, not the API alone: the API answers under /api and
    # the built front end has the rest of the paths, so a reload of /subjects
    # reaches the app rather than the route of the same name.
    uvicorn.run(root_app, host=host, port=port)
