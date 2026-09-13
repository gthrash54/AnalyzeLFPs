"""A database-backed queue for recipe runs.

Runs used to execute in FastAPI's `BackgroundTasks`, inside the web process. That
has three failure modes a deployed lab machine will hit. A run dies silently when
the API restarts, and nothing anywhere records that it ever started. Its status
lives in a dictionary no other process can read, so a second API worker answers
"no such handle" for a run the first one is executing. And one long analysis
competes with every HTTP request inside the same interpreter.

The queue is two tables in `derivatives/runs.db`, beside the run index. SQLite
rather than Redis or RQ because the deployment target is one lab machine, and a
broker is a second service to install, back up, restore, and explain to whoever
inherits this. Claiming is one conditional UPDATE inside an IMMEDIATE
transaction, so two workers cannot take the same job.

A job is not a result. `runs/<run_id>.json` stays the record of what happened. A
job row only says whether the work got done, and points at the record.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ..runs.record import DEFAULT_DERIVATIVES_DIR

# Terminal states. A job in one of these is never claimed again.
DONE = ("ok", "failed", "blocked")

# How long a running job may go without a heartbeat before it is presumed dead.
# Generous, because a heartbeat only stops when the process is gone: a busy CPU
# does not delay it, since the writer runs on its own thread.
DEFAULT_STALE_AFTER_S = 120.0

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    recipe       TEXT NOT NULL,
    study_id     TEXT NOT NULL,
    session      TEXT NOT NULL,
    claim        TEXT NOT NULL,
    params       TEXT NOT NULL DEFAULT '{}',
    overrides    TEXT NOT NULL DEFAULT '{}',
    user         TEXT,
    status       TEXT NOT NULL,
    run_id       TEXT,
    error        TEXT,
    findings     TEXT,
    claimed_by   TEXT,
    attempts     INTEGER NOT NULL DEFAULT 0,
    enqueued_at  TEXT NOT NULL,
    started_at   TEXT,
    heartbeat_at TEXT,
    finished_at  TEXT
);
CREATE INDEX IF NOT EXISTS jobs_status_idx ON jobs(status, enqueued_at);

CREATE TABLE IF NOT EXISTS workers (
    worker_id  TEXT PRIMARY KEY,
    host       TEXT,
    pid        INTEGER,
    started_at TEXT NOT NULL,
    last_seen  TEXT NOT NULL,
    state      TEXT NOT NULL DEFAULT 'idle',
    job_id     TEXT
);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def age_seconds(stamp: str | None, now: datetime | None = None) -> float | None:
    """Seconds since an ISO timestamp, or None when there is no usable timestamp."""
    if not stamp:
        return None
    try:
        then = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if then.tzinfo is None:
        then = then.replace(tzinfo=UTC)
    reference = now or datetime.now(UTC)
    return reference.timestamp() - then.timestamp()


def default_db_path(derivatives_dir: Path | None = None) -> Path:
    return Path(derivatives_dir or DEFAULT_DERIVATIVES_DIR) / "runs.db"


def exists(db_path: Path | None = None) -> bool:
    """Whether there is a queue database yet. Reads use this to stay read-only."""
    return Path(db_path or default_db_path()).exists()


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    """A connection in autocommit mode, with WAL and a busy timeout.

    Both matter once the API and a worker hold the same file open: WAL lets a
    reader run while a writer commits, and the busy timeout turns the remaining
    contention into a short wait instead of `database is locked`. Autocommit is
    deliberate; `claim` opens its own IMMEDIATE transaction.

    Creates the file and its directory. Every read here checks `exists` first,
    because a monitoring endpoint that creates a database is a monitoring
    endpoint that changes what it is reporting on.
    """
    path = Path(db_path or default_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30.0, isolation_level=None)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.executescript(SCHEMA)
        yield conn
    finally:
        conn.close()


def _job(row: sqlite3.Row) -> dict[str, Any]:
    job = dict(row)
    job["params"] = json.loads(job["params"] or "{}")
    job["overrides"] = json.loads(job["overrides"] or "{}")
    job["findings"] = json.loads(job["findings"]) if job["findings"] else None
    return job


def make_job_id() -> str:
    """Sortable by time, unique without a lock."""
    return f"{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"


def enqueue(
    recipe: str,
    study_id: str,
    session: str,
    claim: str,
    params: dict[str, Any] | None = None,
    overrides: dict[str, str] | None = None,
    user: str | None = None,
    db_path: Path | None = None,
) -> str:
    """Add a job and return its id. Validation belongs to the caller.

    The queue does not check the recipe name or the parameters. The API does that
    before enqueueing, so a bad request fails at the request rather than minutes
    later in a worker log nobody is watching.
    """
    job_id = make_job_id()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO jobs (job_id, recipe, study_id, session, claim, params, "
            "overrides, user, status, enqueued_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?)",
            (job_id, recipe, study_id, session, claim,
             json.dumps(params or {}), json.dumps(overrides or {}), user, _now()),
        )
    return job_id


def get_job(job_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    if not exists(db_path):
        return None
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
    return _job(row) if row else None


def list_jobs(
    status: str | None = None, limit: int = 50, db_path: Path | None = None
) -> list[dict[str, Any]]:
    if not exists(db_path):
        return []
    sql = "SELECT * FROM jobs"
    args: list[Any] = []
    if status:
        sql += " WHERE status = ?"
        args.append(status)
    sql += " ORDER BY enqueued_at DESC, rowid DESC LIMIT ?"
    args.append(limit)
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_job(r) for r in rows]


def claim(worker_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    """Take the oldest queued job, or return None when there is nothing to do.

    The SELECT and the UPDATE are one IMMEDIATE transaction. IMMEDIATE takes the
    write lock up front, so a second worker cannot read the same row and believe
    it owns it too. That is the one bug this module has to not have.
    """
    stamp = _now()
    with connect(db_path) as conn:
        conn.execute("BEGIN IMMEDIATE")
        try:
            # rowid, not job_id, breaks the tie. Timestamps are second-resolution
            # and a job id ends in random hex, so two runs submitted in the same
            # second would otherwise execute in arbitrary order. rowid is
            # insertion order, and nothing here deletes a job.
            row = conn.execute(
                "SELECT job_id FROM jobs WHERE status = 'queued' "
                "ORDER BY enqueued_at, rowid LIMIT 1"
            ).fetchone()
            if row is None:
                conn.execute("COMMIT")
                return None
            conn.execute(
                "UPDATE jobs SET status = 'running', claimed_by = ?, started_at = ?, "
                "heartbeat_at = ?, attempts = attempts + 1 WHERE job_id = ?",
                (worker_id, stamp, stamp, row["job_id"]),
            )
            claimed = conn.execute(
                "SELECT * FROM jobs WHERE job_id = ?", (row["job_id"],)
            ).fetchone()
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    return _job(claimed)


def heartbeat(job_id: str, worker_id: str, db_path: Path | None = None) -> None:
    """Say the job is still being worked on. Only its own worker may say so."""
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET heartbeat_at = ? WHERE job_id = ? AND claimed_by = ? "
            "AND status = 'running'",
            (_now(), job_id, worker_id),
        )


def finish(
    job_id: str,
    status: str,
    run_id: str | None = None,
    error: str | None = None,
    findings: list[dict[str, Any]] | None = None,
    db_path: Path | None = None,
) -> None:
    if status not in DONE:
        raise ValueError(f"{status!r} is not a terminal state; expected one of {DONE}")
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = ?, run_id = ?, error = ?, findings = ?, "
            "finished_at = ? WHERE job_id = ?",
            (status, run_id, error, json.dumps(findings) if findings else None,
             _now(), job_id),
        )


def reap_stale(
    stale_after_s: float = DEFAULT_STALE_AFTER_S, db_path: Path | None = None
) -> list[str]:
    """Fail running jobs whose worker stopped heartbeating. Returns their ids.

    They are failed, not requeued. A worker that died partway through a recipe
    may have left half-written output, and re-running it automatically would make
    that invisible: the analyst would see one result and no sign that a first
    attempt ended in the middle of writing. Failing loudly puts the decision to
    re-run back with the person who can look at what is on disk.
    """
    if not exists(db_path):
        return []
    now = datetime.now(UTC)
    dead: list[str] = []
    with connect(db_path) as conn:
        rows = conn.execute(
            "SELECT job_id, claimed_by, heartbeat_at FROM jobs WHERE status = 'running'"
        ).fetchall()
        for row in rows:
            age = age_seconds(row["heartbeat_at"], now)
            if age is None or age <= stale_after_s:
                continue
            dead.append(row["job_id"])
            conn.execute(
                "UPDATE jobs SET status = 'failed', error = ?, finished_at = ? "
                "WHERE job_id = ?",
                (f"worker {row['claimed_by']} stopped without finishing this job "
                 f"(no heartbeat for {age:.0f}s). Anything it wrote is partial. "
                 f"Re-run once you know why the worker stopped.",
                 _now(), row["job_id"]),
            )
    return dead


# ---------------------------------------------------------------------------
# Workers
# ---------------------------------------------------------------------------

def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


def register_worker(worker_id: str, db_path: Path | None = None) -> None:
    stamp = _now()
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO workers (worker_id, host, pid, started_at, last_seen, state) "
            "VALUES (?, ?, ?, ?, ?, 'idle') "
            "ON CONFLICT(worker_id) DO UPDATE SET started_at = excluded.started_at, "
            "last_seen = excluded.last_seen, state = 'idle', job_id = NULL",
            (worker_id, socket.gethostname(), os.getpid(), stamp, stamp),
        )


def worker_seen(
    worker_id: str,
    state: str = "idle",
    job_id: str | None = None,
    db_path: Path | None = None,
) -> None:
    """A worker's own pulse, independent of any job.

    An idle worker still has to prove it is alive, or `/health` cannot tell "no
    work to do" from "nothing is running and every submitted run will sit queued
    forever".
    """
    with connect(db_path) as conn:
        conn.execute(
            "UPDATE workers SET last_seen = ?, state = ?, job_id = ? WHERE worker_id = ?",
            (_now(), state, job_id, worker_id),
        )


def unregister_worker(worker_id: str, db_path: Path | None = None) -> None:
    """Remove a worker that shut down cleanly, so it is not reported as late."""
    with connect(db_path) as conn:
        conn.execute("DELETE FROM workers WHERE worker_id = ?", (worker_id,))


def workers(db_path: Path | None = None) -> list[dict[str, Any]]:
    if not exists(db_path):
        return []
    now = datetime.now(UTC)
    with connect(db_path) as conn:
        rows = conn.execute("SELECT * FROM workers ORDER BY worker_id").fetchall()
    out = []
    for row in rows:
        entry = dict(row)
        entry["seconds_since_seen"] = age_seconds(row["last_seen"], now)
        out.append(entry)
    return out


def queue_health(
    stale_after_s: float = DEFAULT_STALE_AFTER_S, db_path: Path | None = None
) -> dict[str, Any]:
    """What `/health` and the status page report.

    `healthy` is false when work is queued and no worker has been heard from
    recently, because that is the state where the app looks fine and quietly
    does nothing.
    """
    counts: dict[str, int] = {}
    if exists(db_path):
        with connect(db_path) as conn:
            counts = {
                row["status"]: row["n"]
                for row in conn.execute(
                    "SELECT status, COUNT(*) AS n FROM jobs GROUP BY status"
                )
            }
    live = workers(db_path)
    ages = [w["seconds_since_seen"] for w in live if w["seconds_since_seen"] is not None]
    youngest = min(ages) if ages else None
    responsive = youngest is not None and youngest <= stale_after_s
    queued = counts.get("queued", 0)
    if responsive:
        note = ""
    elif queued:
        note = (f"{queued} job(s) queued and no worker has reported in. Start one with "
                "`python -m dbsspeech worker`, or `docker compose up -d worker`.")
    else:
        note = "no worker running; a submitted run would wait"
    return {
        "jobs": counts,
        "queued": queued,
        "running": counts.get("running", 0),
        "workers": len(live),
        "workers_responsive": responsive,
        "seconds_since_worker_seen": youngest,
        "stale_after_s": stale_after_s,
        "healthy": responsive or queued == 0,
        "note": note,
    }
