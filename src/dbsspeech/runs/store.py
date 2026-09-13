"""SQLite index over the run records.

`runs/*.json` is the source of truth and is committed. This database is a
queryable mirror, lives in git-ignored `derivatives/`, and can be rebuilt from
the JSON at any time with `reindex`. Nothing should ever exist only here.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any

from .record import DEFAULT_DERIVATIVES_DIR, DEFAULT_RUNS_DIR

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id      TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    claim       TEXT,
    user        TEXT,
    started_at  TEXT,
    finished_at TEXT,
    status      TEXT,
    git_commit  TEXT,
    git_dirty   INTEGER,
    n_blocking  INTEGER DEFAULT 0,
    n_overrides INTEGER DEFAULT 0,
    record      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS runs_name_idx   ON runs(name);
CREATE INDEX IF NOT EXISTS runs_status_idx ON runs(status);
"""


def default_db_path(derivatives_dir: Path | None = None) -> Path:
    return Path(derivatives_dir or DEFAULT_DERIVATIVES_DIR) / "runs.db"


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path or default_db_path())
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def _row_from_record(rec: dict[str, Any]) -> tuple:
    guardrails = rec.get("guardrails") or {}
    findings = guardrails.get("findings") or []
    return (
        rec["run_id"],
        rec.get("name", ""),
        rec.get("claim"),
        rec.get("user"),
        rec.get("started_at"),
        rec.get("finished_at"),
        rec.get("status"),
        rec.get("git_commit"),
        int(bool(rec.get("git_dirty"))),
        sum(1 for f in findings if f.get("severity") == "block"),
        len(guardrails.get("overrides") or []),
        json.dumps(rec),
    )


def index_run(rec: dict[str, Any], db_path: Path | None = None) -> None:
    with connect(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            _row_from_record(rec),
        )


def reindex(runs_dir: Path | None = None, db_path: Path | None = None) -> int:
    """Rebuild the index from `runs/*.json`. Returns the number indexed."""
    d = Path(runs_dir or DEFAULT_RUNS_DIR)
    records = []
    for path in sorted(d.glob("*.json")):
        try:
            records.append(json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError):
            continue
    with connect(db_path) as conn:
        conn.execute("DELETE FROM runs")
        conn.executemany(
            "INSERT OR REPLACE INTO runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            [_row_from_record(r) for r in records],
        )
    return len(records)


def list_runs(
    name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
    clauses, args = [], []
    if name:
        clauses.append("name = ?")
        args.append(name)
    if status:
        clauses.append("status = ?")
        args.append(status)
    where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
    sql = f"SELECT * FROM runs{where} ORDER BY started_at DESC LIMIT ?"
    args.append(limit)
    with connect(db_path) as conn, closing(conn.execute(sql, args)) as cur:
        return [dict(row) for row in cur.fetchall()]


def get_run(run_id: str, db_path: Path | None = None) -> dict[str, Any] | None:
    with connect(db_path) as conn, closing(
        conn.execute("SELECT record FROM runs WHERE run_id = ?", (run_id,))
    ) as cur:
        row = cur.fetchone()
    return json.loads(row["record"]) if row else None
