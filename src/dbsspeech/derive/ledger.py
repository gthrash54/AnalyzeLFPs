"""The resume ledger: which blocks are planned, claimed, built, failed, or quarantined.

A full pass over the archive takes hours and is bounded by Box bandwidth, so
the build has to survive being interrupted and has to let several workers pull
from one queue without ever building the same block twice. Both needs are met
by one SQLite file at `<out_root>/_ledger.db`, opened with the standard
library `sqlite3` module in the per-operation connection style of
`dbsspeech.runs.store`.

Four design rules keep this module small and honest.

The ledger never invents a timestamp. Every mutating call takes the current
time from the caller as ISO-8601 text (`now`), and `reset_stale` takes the
current time as seconds since the epoch (`now_s`). Nothing here imports
`datetime`, so a test can replay any clock it likes and the result is exact.
Age comparisons are done inside SQLite with its `julianday` function. Because
`julianday` reads a zone-less string as UTC, which would make every claim from
a machine on local time look hours old, `now` must carry an explicit `Z` or
`+HH:MM` offset; a string without one, or one `julianday` cannot parse, is
refused with `ValueError` before anything is written.

The ledger has no privacy logic of its own. It accepts a `scrub` callable and
gives it the last word on every text value, in one of two ways. Free text
(worker, local hint, source format, builder version, error and quarantine
text, the products JSON) is stored as the scrub returns it. Identifiers the
ledger later compares (the block key, `out_relpath`, `out_sha256`,
`config_sha256`, `source_sha256`) are refused with `ValueError` if the scrub
would change them, because a rewritten identifier is a dangling pointer that
would make `reconcile` or `needs_rebuild` rebuild the block forever. The
`claimed_at` and `finished_at` columns are the caller's build clock, stored
verbatim so SQLite can parse them; they say when the store was built, never
when a recording was made. With no scrub given, text is stored as received. A
`local_hint` is an opaque token the driver maps to a staged source on its own
side; it is scrubbed like every other text value precisely so that a Box path
or a case number can never end up here by accident.

Claiming is atomic and ownership is checked. `claim` runs a single
`UPDATE ... RETURNING` inside a `BEGIN IMMEDIATE` transaction, which takes
SQLite's reserved lock before the rows are selected, so two workers on the
same file cannot be handed the same block. This SQLite (3.35 or newer)
supports `RETURNING`; the module checks the library version at import and
refuses to run on an older one rather than fall back to a weaker
select-then-update. Every later transition (`mark_building`, `complete`,
`fail`, `quarantine`) names the worker and only applies to a row that worker
still holds in `claimed` or `building`; a worker whose claim was reset by
`reset_stale` and reassigned gets `LedgerStateError` instead of silently
overwriting the new owner's row, and a key the ledger has never seen gets
`UnknownBlockError`.

Reconcile runs alone. It deletes stray `*.part` files, and a `.part` that a
live worker has open is indistinguishable from a stray one on disk, so
`reconcile` refuses to run while any row is `claimed` or `building` unless the
driver passes `force=True` and takes responsibility.
"""

from __future__ import annotations

import json
import operator
import re
import sqlite3
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .model import BlockResult, Status

BlockKey = tuple[str, str, str]

LEDGER_FILENAME = "_ledger.db"
DEFAULT_MAX_ATTEMPTS = 3

# `UPDATE ... RETURNING` arrived in SQLite 3.35.0 (2021). The atomic claim
# depends on it; refusing early beats discovering the gap under two workers.
_MIN_SQLITE = (3, 35, 0)
if sqlite3.sqlite_version_info < _MIN_SQLITE:  # pragma: no cover
    raise ImportError(
        f"dbsspeech.derive.ledger needs SQLite >= {'.'.join(map(str, _MIN_SQLITE))} for "
        f"UPDATE ... RETURNING; found {sqlite3.sqlite_version}"
    )

SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    study_id          TEXT NOT NULL,
    session           TEXT NOT NULL,
    block             TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'planned',
    worker            TEXT,
    claimed_at        TEXT,
    out_relpath       TEXT,
    out_sha256        TEXT,
    out_bytes         INTEGER,
    config_sha256     TEXT,
    builder_version   TEXT,
    source_format     TEXT,
    source_sha256     TEXT,
    source_bytes      INTEGER,
    local_hint        TEXT,
    attempts          INTEGER NOT NULL DEFAULT 0,
    error_class       TEXT,
    error_message     TEXT,
    quarantine_reason TEXT,
    products_json     TEXT,
    finished_at       TEXT,
    PRIMARY KEY (study_id, session, block)
);
CREATE INDEX IF NOT EXISTS blocks_status_idx ON blocks(status);
"""

_KEY_COLS = "study_id, session, block"
_PLANNED_COLS = "study_id, session, block, source_format, local_hint"
_KEY_WHERE = "study_id = ? AND session = ? AND block = ?"
# A transition is only valid on a row the named worker still holds.
_OWNED_WHERE = f"{_KEY_WHERE} AND worker = ? AND status IN ('claimed', 'building')"
_ACTIVE_STATUSES = ("claimed", "building")

# Seconds since the Unix epoch, computed by SQLite from ISO-8601 text.
# julianday(...) of 1970-01-01T00:00:00Z is 2440587.5.
_EPOCH_S_SQL = "((julianday({col}) - 2440587.5) * 86400.0)"

# The shape `now` must have: date, `T`, time, optional fraction, and an
# explicit zone. The zone is what keeps `julianday` from guessing UTC.
_ISO_WITH_ZONE = re.compile(
    r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$"
)


class LedgerStateError(RuntimeError):
    """A transition was refused because the row is not in the state it needs.

    Raised when a worker acts on a block it no longer owns (its claim was
    reset and handed to someone else, or the block already reached a final
    status), and when `reconcile` is asked to run while workers are active.
    The message names the block key and the status only.
    """


class UnknownBlockError(LookupError):
    """A transition named a key the ledger has never planned."""


@dataclass(frozen=True)
class PlannedBlock:
    """One block the driver intends to build.

    `local_hint` is an opaque token the driver uses to find the staged source.
    It is never a Box path, a filename, or a case number; the driver keeps its
    own mapping from hint to location and that mapping never enters the ledger.
    """

    study_id: str
    session: str
    block: str
    source_format: str
    local_hint: str

    @property
    def key(self) -> BlockKey:
        return (self.study_id, self.session, self.block)


@dataclass(frozen=True)
class ReconcileReport:
    """What `Ledger.reconcile` found and did. Keys only, never paths from Box."""

    checked: int = 0
    reopened_missing: list[BlockKey] = field(default_factory=list)
    reopened_mismatch: list[BlockKey] = field(default_factory=list)
    removed_parts: list[str] = field(default_factory=list)

    @property
    def reopened(self) -> list[BlockKey]:
        return [*self.reopened_missing, *self.reopened_mismatch]


def _identity(text: str) -> str:
    return text


def _json_default(value: Any) -> Any:
    """Make numpy scalars and arrays JSON-native for `json.dumps`.

    `numpy.generic.item` turns a numpy scalar into the matching Python scalar
    and `numpy.ndarray.tolist` does the same for arrays; anything else is a
    genuine error and is reported as `json.dumps` would report it.
    """
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"object of type {type(value).__name__} is not JSON serializable")


def _check_now(conn: sqlite3.Connection, now: str) -> str:
    """Refuse a `now` that lacks a zone or that SQLite's `julianday` cannot read.

    The message reports the length of the offending text and never the text
    itself, since the exception is exactly the kind of thing that gets logged.
    """
    if not isinstance(now, str) or not _ISO_WITH_ZONE.match(now):
        raise ValueError(
            f"now must be ISO-8601 with an explicit Z or +HH:MM offset; "
            f"got text of length {len(now) if isinstance(now, str) else 0}"
        )
    if conn.execute("SELECT julianday(?)", (now,)).fetchone()[0] is None:
        raise ValueError(f"now is not a date julianday can parse; got text of length {len(now)}")
    return now


class Ledger:
    """Resume ledger over a SQLite file; see the module docstring for the rules.

    `scrub` has the last word on every text value stored, except the block
    key; identifiers are refused rather than rewritten. `max_attempts` bounds
    how many times a retryable failure sends a block back to `planned`; it is
    policy and belongs in `DeriveConfig`, so the builder should pass it in
    from there rather than rely on the default here.
    """

    def __init__(
        self,
        db_path: Path,
        *,
        scrub: Callable[[str], str] | None = None,
        max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self.db_path = Path(db_path)
        self._scrub: Callable[[str], str] = scrub or _identity
        self.max_attempts = max_attempts

    # ---- connection ---------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        """One connection per operation, autocommit off the table until BEGIN.

        `isolation_level=None` puts the connection in autocommit mode so that
        transactions start exactly where this module says `BEGIN IMMEDIATE` and
        nowhere else. `timeout` makes a second writer wait for the lock rather
        than fail, which is what a pool of workers on one file needs.
        """
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=30.0, isolation_level=None)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def _immediate(self) -> Iterator[sqlite3.Connection]:
        """A write transaction that holds the reserved lock from its first statement.

        On an exception the transaction is rolled back only if it is still
        open (`Connection.in_transaction`); SQLite ends a transaction on its
        own after some errors, and a ROLLBACK then would raise and hide the
        original exception.
        """
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                yield conn
            except BaseException:
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    # ---- text policy ----------------------------------------------------------

    def _text(self, value: str | None) -> str | None:
        """Free text: stored as the scrub returns it."""
        return None if value is None else self._scrub(value)

    def _ident(self, column: str, value: str | None) -> str | None:
        """An identifier the ledger compares later: refused if the scrub would change it."""
        if value is None:
            return None
        if self._scrub(value) != value:
            raise ValueError(
                f"{column} of length {len(value)} would be altered by the scrub and cannot "
                "be stored as an identifier"
            )
        return value

    def _checked_key(self, key: BlockKey) -> BlockKey:
        study_id, session, block = key
        return (
            str(self._ident("study_id", study_id)),
            str(self._ident("session", session)),
            str(self._ident("block", block)),
        )

    @staticmethod
    def _require_owned(
        conn: sqlite3.Connection, cur: sqlite3.Cursor, key: BlockKey, worker: str
    ) -> None:
        """After an owned UPDATE: exactly one row changed, or explain why not."""
        if cur.rowcount == 1:
            return
        row = conn.execute(f"SELECT status, worker FROM blocks WHERE {_KEY_WHERE}", key).fetchone()
        if row is None:
            raise UnknownBlockError(f"block {key!r} is not in the ledger")
        raise LedgerStateError(
            f"block {key!r} is {row['status']!r} and not held by worker {worker!r}; "
            "the transition was refused"
        )

    # ---- planning and claiming ---------------------------------------------

    def upsert_planned(self, rows: Iterable[PlannedBlock], *, now: str) -> int:
        """Insert unseen keys as `planned`; rows already present are left alone.

        Uses `INSERT ... ON CONFLICT DO NOTHING`, so a re-run of the driver
        against an existing ledger never resets progress. Returns the number of
        rows actually inserted. `now` is validated for uniformity with every
        other mutating call; a planned row has no timestamp yet.
        """
        values = [
            (*self._checked_key(r.key), self._text(r.source_format), self._text(r.local_hint))
            for r in rows
        ]
        with self._immediate() as conn:
            _check_now(conn, now)
            if not values:
                return 0
            before = conn.total_changes
            conn.executemany(
                f"INSERT INTO blocks ({_PLANNED_COLS}) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(study_id, session, block) DO NOTHING",
                values,
            )
            return conn.total_changes - before

    def claim(self, worker: str, n: int = 1, *, now: str) -> list[PlannedBlock]:
        """Atomically move up to `n` planned blocks to `claimed` for `worker`.

        One `UPDATE ... RETURNING` inside `BEGIN IMMEDIATE`. The reserved lock
        is taken before the subquery picks rows, so a concurrent claimer waits
        and then sees the rows already marked; no block is handed out twice.
        The lowest `n` keys are taken and the result is sorted by key in
        Python, since SQLite does not define the order of RETURNING rows, so
        the pass is reproducible. `n` must be an integer (`operator.index`).
        """
        if isinstance(n, bool):
            raise TypeError("n must be an integer, not a bool")
        n = operator.index(n)
        if n < 1:
            return []
        with self._immediate() as conn:
            _check_now(conn, now)
            cur = conn.execute(
                "UPDATE blocks SET status = 'claimed', worker = ?, claimed_at = ? "
                f"WHERE status = 'planned' AND ({_KEY_COLS}) IN ("
                f"    SELECT {_KEY_COLS} FROM blocks WHERE status = 'planned' "
                f"    ORDER BY {_KEY_COLS} LIMIT ?"
                f") RETURNING {_PLANNED_COLS}",
                (self._text(worker), now, n),
            )
            rows = cur.fetchall()
        blocks = [
            PlannedBlock(
                study_id=r["study_id"],
                session=r["session"],
                block=r["block"],
                source_format=r["source_format"] or "",
                local_hint=r["local_hint"] or "",
            )
            for r in rows
        ]
        return sorted(blocks, key=lambda b: b.key)

    def mark_building(
        self,
        key: BlockKey,
        worker: str,
        *,
        now: str,
        source_sha256: str | None = None,
        source_bytes: int | None = None,
    ) -> None:
        """The worker has the source staged and is starting the transform.

        `claimed_at` is refreshed so the stale timeout measures from the start
        of the build, not from the claim, which may have preceded a long fetch.
        The staged source's hash and size are recorded here when the driver
        has them, since this is the moment it does. Refused unless `worker`
        still holds the row.
        """
        who = self._text(worker)
        with self._immediate() as conn:
            _check_now(conn, now)
            cur = conn.execute(
                "UPDATE blocks SET status = 'building', claimed_at = ?, "
                "source_sha256 = COALESCE(?, source_sha256), "
                "source_bytes = COALESCE(?, source_bytes) "
                f"WHERE {_OWNED_WHERE}",
                (now, self._ident("source_sha256", source_sha256), source_bytes, *key, who),
            )
            self._require_owned(conn, cur, key, worker)

    # ---- outcomes -------------------------------------------------------------

    def complete(
        self,
        result: BlockResult,
        worker: str,
        *,
        config_sha256: str,
        builder_version: str,
        now: str,
    ) -> None:
        """Record a finished block: output location, hash, size, and products.

        `products_json` holds one JSON object: `{"products": [...],
        "epochs_written": [...], "seconds": float}` built with `dataclasses.
        asdict` on each `ProductRecord` and serialized by `json.dumps` with
        `allow_nan=False` and a default that converts numpy scalars, so a
        stray `numpy.int64` or NaN cannot poison the row. If the products
        still cannot be serialized the block is recorded as a non-retryable
        failure and the error is re-raised, so a row is never left in
        `building` with nothing to explain it. A result whose status is not
        `done`, or that lacks `out_relpath` or `out_sha256`, is refused;
        failures and quarantines have their own calls. Refused unless
        `worker` still holds the row.
        """
        if result.status != "done":
            raise ValueError(f"complete() takes a done result, got status {result.status!r}")
        if not result.out_relpath or not result.out_sha256:
            raise ValueError("a done result must carry out_relpath and out_sha256")
        key = result.key
        payload = {
            "products": [asdict(p) for p in result.products],
            "epochs_written": list(result.epochs_written),
            "seconds": result.seconds,
        }
        try:
            products_json = json.dumps(
                payload, sort_keys=True, allow_nan=False, default=_json_default
            )
        except (TypeError, ValueError) as exc:
            self.fail(
                key, worker, type(exc).__name__, "products are not JSON serializable",
                retryable=False, now=now,
            )
            raise
        who = self._text(worker)
        with self._immediate() as conn:
            _check_now(conn, now)
            cur = conn.execute(
                "UPDATE blocks SET status = 'done', out_relpath = ?, out_sha256 = ?, "
                "out_bytes = ?, config_sha256 = ?, builder_version = ?, products_json = ?, "
                "finished_at = ?, error_class = NULL, error_message = NULL, "
                "quarantine_reason = NULL "
                f"WHERE {_OWNED_WHERE}",
                (
                    self._ident("out_relpath", result.out_relpath),
                    self._ident("out_sha256", result.out_sha256),
                    int(result.out_bytes),
                    self._ident("config_sha256", config_sha256),
                    self._text(builder_version),
                    self._text(products_json),
                    now,
                    *key,
                    who,
                ),
            )
            self._require_owned(conn, cur, key, worker)

    def fail(
        self,
        key: BlockKey,
        worker: str,
        error_class: str,
        message: str,
        retryable: bool,
        *,
        now: str,
    ) -> None:
        """Count an attempt; go back to `planned` if retryable and attempts remain.

        The attempt counter and the status decision live in one SQL statement
        so the count read is the count acted on, even with other workers busy.
        Refused unless `worker` still holds the row, so a late failure from a
        worker whose claim was reset cannot reopen a block someone else is
        building, and a `done` or never-claimed row is never touched.
        """
        who = self._text(worker)
        with self._immediate() as conn:
            _check_now(conn, now)
            cur = conn.execute(
                "UPDATE blocks SET attempts = attempts + 1, "
                "error_class = ?, error_message = ?, finished_at = ?, "
                "status = CASE WHEN ? AND attempts + 1 < ? THEN 'planned' ELSE 'failed' END, "
                "worker = CASE WHEN ? AND attempts + 1 < ? THEN NULL ELSE worker END, "
                "claimed_at = CASE WHEN ? AND attempts + 1 < ? THEN NULL ELSE claimed_at END "
                f"WHERE {_OWNED_WHERE}",
                (
                    self._text(error_class),
                    self._text(message),
                    now,
                    int(retryable), self.max_attempts,
                    int(retryable), self.max_attempts,
                    int(retryable), self.max_attempts,
                    *key,
                    who,
                ),
            )
            self._require_owned(conn, cur, key, worker)

    def quarantine(self, key: BlockKey, worker: str, reason: str, detail: str, *, now: str) -> None:
        """Park a block a person must look at. `reason` is the tag, `detail` the text.

        Refused unless `worker` still holds the row.
        """
        who = self._text(worker)
        with self._immediate() as conn:
            _check_now(conn, now)
            cur = conn.execute(
                "UPDATE blocks SET status = 'quarantined', quarantine_reason = ?, "
                "error_message = ?, finished_at = ?, worker = NULL, claimed_at = NULL "
                f"WHERE {_OWNED_WHERE}",
                (self._text(reason), self._text(detail), now, *key, who),
            )
            self._require_owned(conn, cur, key, worker)

    # ---- recovery -------------------------------------------------------------

    def reset_stale(self, older_than_s: float, now_s: float) -> int:
        """Return `claimed` or `building` rows older than the timeout to `planned`.

        Age is `now_s` minus the row's `claimed_at`, the latter converted to
        seconds since the epoch by SQLite's `julianday`. A row whose
        `claimed_at` is NULL or unparseable (`julianday` returns NULL) is
        treated as stale, so a damaged row can always recover instead of
        sitting in `claimed` forever. Returns the number reset.
        """
        epoch = _EPOCH_S_SQL.format(col="claimed_at")
        with self._immediate() as conn:
            cur = conn.execute(
                "UPDATE blocks SET status = 'planned', worker = NULL, claimed_at = NULL "
                "WHERE status IN ('claimed', 'building') "
                f"AND (julianday(claimed_at) IS NULL OR (? - {epoch}) > ?)",
                (float(now_s), float(older_than_s)),
            )
            return int(cur.rowcount)

    def reconcile(
        self,
        out_root: Path,
        hasher: Callable[[Path], str],
        *,
        force: bool = False,
        keep: Callable[[Path], bool] | None = None,
    ) -> ReconcileReport:
        """Check every `done` row against disk and clean up abandoned partial files.

        A done row whose file is missing, or whose `hasher(path)` differs from
        the stored `out_sha256`, goes back to `planned`. Nothing that a row
        points to is ever deleted: the only removals are stray `*.part` files
        under `out_root`, found with `pathlib.Path.rglob`, excluding any
        `.part` that a done row's `out_relpath` names and any for which
        `keep(path)` is True. The hasher is supplied by the caller so this
        module does not choose the hashing policy.

        This must run while no worker is active. A `.part` a live worker has
        open looks exactly like a stray one, and deleting it makes that
        worker's final `os.replace` fail. So `reconcile` raises
        `LedgerStateError` when any row is `claimed` or `building` unless
        `force=True`, in which case the driver is asserting that those rows
        are dead (it should normally call `reset_stale` first, which is what
        turns dead claims back into `planned`).
        """
        out_root = Path(out_root)
        active = {k: v for k, v in self.summary().items() if k in _ACTIVE_STATUSES}
        if active and not force:
            raise LedgerStateError(
                f"reconcile refused: {active} rows are still active; run reset_stale first "
                "or pass force=True"
            )
        with self._connect() as conn:
            done = conn.execute(
                f"SELECT {_KEY_COLS}, out_relpath, out_sha256 FROM blocks WHERE status = 'done' "
                f"ORDER BY {_KEY_COLS}"
            ).fetchall()

        missing: list[BlockKey] = []
        mismatch: list[BlockKey] = []
        pointed_to: set[Path] = set()
        for r in done:
            key: BlockKey = (r["study_id"], r["session"], r["block"])
            relpath = r["out_relpath"]
            path = out_root / relpath if relpath else None
            if path is not None:
                pointed_to.add(path)
            if path is None or not path.is_file():
                missing.append(key)
            elif hasher(path) != r["out_sha256"]:
                mismatch.append(key)

        reopen = [*missing, *mismatch]
        if reopen:
            with self._immediate() as conn:
                conn.executemany(
                    "UPDATE blocks SET status = 'planned', worker = NULL, claimed_at = NULL "
                    f"WHERE {_KEY_WHERE} AND status = 'done'",
                    reopen,
                )

        removed: list[str] = []
        if out_root.is_dir():
            for part in sorted(out_root.rglob("*.part")):
                if not part.is_file() or part in pointed_to:
                    continue
                if keep is not None and keep(part):
                    continue
                part.unlink()
                removed.append(part.relative_to(out_root).as_posix())

        return ReconcileReport(
            checked=len(done),
            reopened_missing=missing,
            reopened_mismatch=mismatch,
            removed_parts=removed,
        )

    # ---- queries ----------------------------------------------------------------

    def needs_rebuild(self, key: BlockKey, config_sha256: str) -> bool:
        """True unless the block is `done` under exactly this policy hash."""
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT status, config_sha256 FROM blocks WHERE {_KEY_WHERE}", tuple(key)
            ).fetchone()
        if row is None:
            return True
        return not (row["status"] == "done" and row["config_sha256"] == config_sha256)

    def summary(self) -> dict[str, int]:
        """Row counts by status, for the progress line and the final report."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM blocks GROUP BY status ORDER BY status"
            ).fetchall()
        return {r["status"]: int(r["n"]) for r in rows}

    def iter_status(self, status: Status) -> list[dict[str, Any]]:
        """Every row with the given status, as plain dicts, in key order."""
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM blocks WHERE status = ? ORDER BY {_KEY_COLS}", (status,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get(self, key: BlockKey) -> dict[str, Any] | None:
        """One row as a dict, or None. Handy for the driver and for tests."""
        with self._connect() as conn:
            row = conn.execute(f"SELECT * FROM blocks WHERE {_KEY_WHERE}", tuple(key)).fetchone()
        return dict(row) if row is not None else None
