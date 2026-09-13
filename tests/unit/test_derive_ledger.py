"""The resume ledger: no block is built twice, no progress is lost, nothing leaks.

Five properties are guarded here, each because its failure is silent.

Claiming is exclusive: two workers pulling from the same file must between
them receive every planned block exactly once. A duplicate claim wastes hours;
a dropped one leaves a hole in the store that nobody notices until an analysis
asks for that block.

Ownership is checked: a worker whose claim was reset and handed to someone
else must be refused when it reports late, or its stale failure would reopen a
block that is being built and its stale completion would mark a half-written
file as done.

Resume is exact: a block is rebuilt when, and only when, it is not done under
the current policy hash. A ledger that reopened too much would rebuild the
store on every run; one that reopened too little would leave stale derivatives
that quietly disagree with the config that claims to describe them.

Recovery is conservative: stale claims and files that do not match their row
go back to `planned`, the only thing ever deleted is a `.part` file no row
points to, and reconcile will not run at all while workers are active.

Privacy is not the ledger's job, but the ledger must give the scrub it is
handed the last word on every text value, so a redact pattern from
`configs/derive.yaml` can never be matched by anything the file holds; and it
must refuse, not rewrite, an identifier the scrub would alter, or the row
would point at a file that does not exist.
"""

from __future__ import annotations

import contextlib
import hashlib
import re
import sqlite3
import threading
from collections import Counter
from collections.abc import Callable
from pathlib import Path

import numpy as np
import pytest

from dbsspeech.derive.config import load_config
from dbsspeech.derive.ledger import (
    Ledger,
    LedgerStateError,
    PlannedBlock,
    ReconcileReport,
    UnknownBlockError,
)
from dbsspeech.derive.model import BlockResult, ProductRecord

pytestmark = pytest.mark.unit

T0 = "2000-01-01T00:00:00Z"
T1 = "2000-01-01T00:10:00Z"
T2 = "2000-01-01T01:00:00Z"
T0_S = 946684800.0  # T0 as seconds since the epoch
CONFIG_A = "a" * 64
CONFIG_B = "b" * 64


def _planned(i: int, study: str = "sub-001") -> PlannedBlock:
    return PlannedBlock(
        study_id=study,
        session=f"ses-{i // 10:02d}",
        block=f"Block-{i % 10}",
        source_format="tdt_mat",
        local_hint=f"hint-{i:04d}",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _product(**overrides: object) -> ProductRecord:
    fields: dict[str, object] = dict(
        stream="ecog", product="lfp", role="lfp", n_channels=2,
        n_samples_in=1000, n_samples_out=100, sfreq_in_hz=1000.0,
        sfreq_out_hz=100.0, data_sha256="c" * 64,
    )
    fields.update(overrides)
    return ProductRecord(**fields)  # type: ignore[arg-type]


def _done_result(
    pb: PlannedBlock, relpath: str, sha: str, nbytes: int,
    products: list[ProductRecord] | None = None,
) -> BlockResult:
    return BlockResult(
        study_id=pb.study_id,
        session=pb.session,
        block=pb.block,
        status="done",
        out_relpath=relpath,
        out_sha256=sha,
        out_bytes=nbytes,
        products=[_product()] if products is None else products,
        epochs_written=["Stim"],
        seconds=1.5,
    )


@pytest.fixture
def ledger(tmp_path: Path) -> Ledger:
    led = Ledger(tmp_path / "_ledger.db", max_attempts=3)
    led.ensure_schema()
    return led


# ---- planning ------------------------------------------------------------------

def test_upsert_inserts_new_keys_and_leaves_existing_rows_untouched(ledger: Ledger):
    rows = [_planned(i) for i in range(5)]
    assert ledger.upsert_planned(rows, now=T0) == 5
    assert ledger.summary() == {"planned": 5}

    ledger.claim("w1", n=2, now=T0)
    # Re-planning the same keys plus one new one must not reset the claimed two.
    assert ledger.upsert_planned([*rows, _planned(99)], now=T1) == 1
    assert ledger.summary() == {"planned": 4, "claimed": 2}


def test_a_claim_round_trips_the_source_format_and_local_hint(ledger: Ledger):
    pb = _planned(3)
    ledger.upsert_planned([pb], now=T0)
    (got,) = ledger.claim("w1", now=T0)
    assert got == pb
    row = ledger.get(pb.key)
    assert row is not None
    assert row["status"] == "claimed"
    assert row["worker"] == "w1"
    assert row["claimed_at"] == T0


def test_claiming_from_an_empty_queue_returns_nothing(ledger: Ledger):
    assert ledger.claim("w1", n=5, now=T0) == []
    assert ledger.claim("w1", n=0, now=T0) == []


def test_claim_returns_the_lowest_keys_in_key_order_and_rejects_a_non_integer_n(
    ledger: Ledger,
):
    ledger.upsert_planned([_planned(i) for i in (7, 3, 12, 5)], now=T0)
    got = ledger.claim("w1", n=3, now=T0)
    assert [pb.key for pb in got] == sorted(pb.key for pb in got)
    assert [pb.block for pb in got] == ["Block-3", "Block-5", "Block-7"]
    for bad in (2.5, "3", True):
        with pytest.raises(TypeError):
            ledger.claim("w1", n=bad, now=T0)  # type: ignore[arg-type]


# ---- exclusive claiming under concurrency -------------------------------------

def test_two_workers_claiming_concurrently_share_every_block_exactly_once(tmp_path: Path):
    """Threads hammer one db file; the union of claims must be the full set, no repeats."""
    db = tmp_path / "_ledger.db"
    led = Ledger(db)
    led.ensure_schema()
    all_blocks = [_planned(i) for i in range(120)]
    led.upsert_planned(all_blocks, now=T0)

    taken: dict[str, list[PlannedBlock]] = {"w1": [], "w2": [], "w3": []}
    start = threading.Barrier(len(taken))

    def run(worker: str) -> None:
        own = Ledger(db)  # each worker opens its own connections
        start.wait()
        while True:
            got = own.claim(worker, n=3, now=T1)
            if not got:
                return
            taken[worker].extend(got)

    threads = [threading.Thread(target=run, args=(w,)) for w in taken]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    everything = [pb for got in taken.values() for pb in got]
    counts = Counter(pb.key for pb in everything)
    assert set(counts) == {pb.key for pb in all_blocks}
    assert all(n == 1 for n in counts.values()), counts
    assert led.summary() == {"claimed": 120}


def test_a_claimer_that_waited_for_the_lock_sees_the_other_writer_s_rows_as_taken(
    tmp_path: Path,
):
    """Forced contention, so the interleaving is not left to the scheduler.

    A raw connection takes the reserved lock with BEGIN IMMEDIATE and holds
    it; a claimer started meanwhile must block. The raw writer then marks the
    first sixty rows claimed and commits. If the claimer had read the planned
    set before waiting, it would hand out those sixty again.
    """
    db = tmp_path / "_ledger.db"
    led = Ledger(db)
    led.ensure_schema()
    all_blocks = [_planned(i) for i in range(120)]
    led.upsert_planned(all_blocks, now=T0)
    first_sixty = {pb.key for pb in sorted(all_blocks, key=lambda b: b.key)[:60]}

    holder = sqlite3.connect(db, isolation_level=None)
    holder.execute("BEGIN IMMEDIATE")

    got: list[PlannedBlock] = []
    waiter = threading.Thread(target=lambda: got.extend(led.claim("late", n=200, now=T1)))
    waiter.start()
    waiter.join(timeout=0.3)
    assert waiter.is_alive(), "the claimer should be blocked on the reserved lock"

    holder.executemany(
        "UPDATE blocks SET status = 'claimed', worker = 'raw', claimed_at = ? "
        "WHERE study_id = ? AND session = ? AND block = ?",
        [(T1, *key) for key in first_sixty],
    )
    holder.execute("COMMIT")
    holder.close()
    waiter.join(timeout=10.0)
    assert not waiter.is_alive()

    assert {pb.key for pb in got} == {pb.key for pb in all_blocks} - first_sixty
    assert led.summary() == {"claimed": 120}


# ---- done and needs_rebuild ----------------------------------------------------

def test_complete_records_the_output_and_needs_rebuild_tracks_the_config_hash(
    ledger: Ledger, tmp_path: Path
):
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    ledger.claim("w1", now=T0)
    ledger.mark_building(pb.key, "w1", now=T0, source_sha256="d" * 64, source_bytes=1234)

    ledger.complete(
        _done_result(pb, "sub-001/ses-00/Block-0.h5", "e" * 64, 4096), "w1",
        config_sha256=CONFIG_A, builder_version="0.1.0", now=T1,
    )

    row = ledger.get(pb.key)
    assert row is not None
    assert row["status"] == "done"
    assert row["out_relpath"] == "sub-001/ses-00/Block-0.h5"
    assert row["out_sha256"] == "e" * 64
    assert row["out_bytes"] == 4096
    assert row["config_sha256"] == CONFIG_A
    assert row["builder_version"] == "0.1.0"
    assert row["source_sha256"] == "d" * 64
    assert row["source_bytes"] == 1234
    assert row["finished_at"] == T1
    assert '"epochs_written": ["Stim"]' in row["products_json"]
    assert '"product": "lfp"' in row["products_json"]

    assert ledger.needs_rebuild(pb.key, CONFIG_A) is False
    assert ledger.needs_rebuild(pb.key, CONFIG_B) is True
    assert ledger.needs_rebuild(("sub-999", "ses-00", "Block-0"), CONFIG_A) is True


def test_complete_refuses_a_result_that_is_not_done_or_has_no_output(ledger: Ledger):
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    ledger.claim("w1", now=T0)
    bad = BlockResult(pb.study_id, pb.session, pb.block, status="failed")
    with pytest.raises(ValueError, match="done result"):
        ledger.complete(bad, "w1", config_sha256=CONFIG_A, builder_version="0.1.0", now=T1)
    no_output = BlockResult(pb.study_id, pb.session, pb.block, status="done")
    with pytest.raises(ValueError, match="out_relpath"):
        ledger.complete(no_output, "w1", config_sha256=CONFIG_A, builder_version="0", now=T1)
    assert ledger.get(pb.key)["status"] == "claimed"  # type: ignore[index]


def test_complete_converts_numpy_scalars_in_products_and_refuses_nan(ledger: Ledger):
    """A numpy int64 from an array shape must not leave the row stuck in `building`."""
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    ledger.claim("w1", now=T0)
    ledger.mark_building(pb.key, "w1", now=T0)

    numpy_product = _product(
        n_channels=np.int64(2),
        n_samples_out=np.sum(np.zeros((2, 10)).shape[1:]),
        sfreq_in_hz=np.float64(48828.125),
        filter_attrs={"taps": np.arange(3), "atten_db": np.float32(90.0)},
    )
    ledger.complete(
        _done_result(pb, "sub-001/x.h5", "e" * 64, 1, products=[numpy_product]), "w1",
        config_sha256=CONFIG_A, builder_version="0", now=T1,
    )
    row = ledger.get(pb.key)
    assert row is not None
    assert row["status"] == "done"
    assert '"n_channels": 2' in row["products_json"]
    assert '"n_samples_out": 10' in row["products_json"]
    assert '"taps": [0, 1, 2]' in row["products_json"]

    # A NaN would be emitted as a bare token no JSON reader accepts; the
    # block is recorded as failed, not left in `building`.
    pb2 = _planned(1)
    ledger.upsert_planned([pb2], now=T0)
    ledger.claim("w1", now=T0)
    ledger.mark_building(pb2.key, "w1", now=T0)
    with pytest.raises(ValueError):
        ledger.complete(
            _done_result(pb2, "sub-001/y.h5", "e" * 64, 1,
                         products=[_product(sfreq_out_hz=float("nan"))]), "w1",
            config_sha256=CONFIG_A, builder_version="0", now=T1,
        )
    row2 = ledger.get(pb2.key)
    assert row2 is not None
    assert row2["status"] == "failed"
    assert row2["error_class"] == "ValueError"
    assert row2["attempts"] == 1


def test_a_block_that_is_not_done_always_needs_a_rebuild(ledger: Ledger):
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    assert ledger.needs_rebuild(pb.key, CONFIG_A) is True
    ledger.claim("w1", now=T0)
    ledger.fail(pb.key, "w1", "OSError", "disk full", retryable=False, now=T1)
    assert ledger.needs_rebuild(pb.key, CONFIG_A) is True


# ---- failures and retries ------------------------------------------------------

def test_a_retryable_failure_returns_to_planned_until_attempts_reach_the_maximum(
    ledger: Ledger,
):
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)

    for attempt in (1, 2):
        (got,) = ledger.claim("w1", now=T0)
        assert got.key == pb.key
        ledger.fail(pb.key, "w1", "TimeoutError", "box hiccup", retryable=True, now=T1)
        row = ledger.get(pb.key)
        assert row is not None
        assert row["attempts"] == attempt
        assert row["status"] == "planned", attempt
        assert row["worker"] is None
        assert row["claimed_at"] is None
        assert row["error_class"] == "TimeoutError"

    ledger.claim("w1", now=T0)
    ledger.fail(pb.key, "w1", "TimeoutError", "box hiccup", retryable=True, now=T2)
    row = ledger.get(pb.key)
    assert row is not None
    assert row["attempts"] == 3
    assert row["status"] == "failed"
    assert ledger.claim("w1", now=T2) == []


def test_a_non_retryable_failure_fails_on_the_first_attempt(ledger: Ledger):
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    ledger.claim("w1", now=T0)
    ledger.fail(pb.key, "w1", "ValueError", "bad header", retryable=False, now=T1)
    row = ledger.get(pb.key)
    assert row is not None
    assert row["status"] == "failed"
    assert row["attempts"] == 1
    assert row["error_message"] == "bad header"
    assert row["finished_at"] == T1


def test_quarantine_parks_the_block_with_its_reason(ledger: Ledger):
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    ledger.claim("w1", now=T0)
    ledger.quarantine(pb.key, "w1", "unmapped_stream", "stream 'xyz1' has no role", now=T1)
    row = ledger.get(pb.key)
    assert row is not None
    assert row["status"] == "quarantined"
    assert row["quarantine_reason"] == "unmapped_stream"
    assert row["error_message"] == "stream 'xyz1' has no role"
    assert ledger.iter_status("quarantined")[0]["block"] == pb.block


# ---- ownership --------------------------------------------------------------------

def test_a_worker_whose_claim_was_reset_and_reassigned_is_refused_when_it_reports_late(
    ledger: Ledger,
):
    """After reset_stale hands the block to w2, nothing w1 says may touch the row."""
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    (got,) = ledger.claim("w1", now=T0)
    ledger.mark_building(got.key, "w1", now=T0)
    assert ledger.reset_stale(older_than_s=1.0, now_s=T0_S + 3600.0) == 1
    (again,) = ledger.claim("w2", now=T2)
    assert again.key == pb.key
    ledger.mark_building(pb.key, "w2", now=T2)

    with pytest.raises(LedgerStateError):
        ledger.fail(pb.key, "w1", "TimeoutError", "late", retryable=True, now=T2)
    with pytest.raises(LedgerStateError):
        ledger.complete(_done_result(pb, "sub-001/late.h5", "e" * 64, 1), "w1",
                        config_sha256=CONFIG_A, builder_version="0", now=T2)
    with pytest.raises(LedgerStateError):
        ledger.quarantine(pb.key, "w1", "late", "late", now=T2)
    with pytest.raises(LedgerStateError):
        ledger.mark_building(pb.key, "w1", now=T2)

    row = ledger.get(pb.key)
    assert row is not None
    assert row["status"] == "building"
    assert row["worker"] == "w2"
    assert row["attempts"] == 0
    assert ledger.needs_rebuild(pb.key, CONFIG_A) is True

    # The rightful owner is unaffected.
    ledger.complete(_done_result(pb, "sub-001/ok.h5", "e" * 64, 1), "w2",
                    config_sha256=CONFIG_A, builder_version="0", now=T2)
    assert ledger.needs_rebuild(pb.key, CONFIG_A) is False


def test_fail_on_a_done_row_or_an_unclaimed_row_is_refused_and_changes_nothing(
    ledger: Ledger,
):
    done, planned = _planned(0), _planned(1)
    ledger.upsert_planned([done, planned], now=T0)
    (got,) = ledger.claim("w1", now=T0)
    assert got.key == done.key
    ledger.complete(_done_result(done, "sub-001/d.h5", "e" * 64, 1), "w1",
                    config_sha256=CONFIG_A, builder_version="0", now=T1)

    with pytest.raises(LedgerStateError):
        ledger.fail(done.key, "w1", "E", "late", retryable=True, now=T2)
    with pytest.raises(LedgerStateError):
        ledger.fail(planned.key, "w1", "E", "never claimed", retryable=True, now=T2)

    assert ledger.get(done.key)["status"] == "done"  # type: ignore[index]
    assert ledger.get(done.key)["out_relpath"] == "sub-001/d.h5"  # type: ignore[index]
    assert ledger.get(planned.key)["attempts"] == 0  # type: ignore[index]
    assert ledger.summary() == {"done": 1, "planned": 1}


def test_every_transition_on_an_unknown_key_raises_instead_of_doing_nothing(ledger: Ledger):
    ghost = ("sub-000", "ses-00", "Block-0")
    with pytest.raises(UnknownBlockError):
        ledger.mark_building(ghost, "w1", now=T0)
    with pytest.raises(UnknownBlockError):
        ledger.complete(BlockResult(*ghost, status="done", out_relpath="a", out_sha256="b"),
                        "w1", config_sha256=CONFIG_A, builder_version="0", now=T0)
    with pytest.raises(UnknownBlockError):
        ledger.fail(ghost, "w1", "E", "m", retryable=False, now=T0)
    with pytest.raises(UnknownBlockError):
        ledger.quarantine(ghost, "w1", "r", "d", now=T0)
    assert ledger.summary() == {}


# ---- timestamps -------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_now",
    ["2000-01-01T00:00:00", "946684800", "2000-01-01 00:00:00Z", "2000-13-01T00:00:00Z", ""],
)
def test_a_now_without_an_explicit_zone_or_that_does_not_parse_is_refused(
    ledger: Ledger, bad_now: str
):
    """A naive string would be read as UTC by julianday and make fresh claims look old."""
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    with pytest.raises(ValueError) as info:
        ledger.claim("w1", now=bad_now)
    assert bad_now not in str(info.value) or bad_now == ""
    with pytest.raises(ValueError):
        ledger.upsert_planned([_planned(1)], now=bad_now)
    assert ledger.summary() == {"planned": 1}


def test_offset_aware_timestamps_are_parsed_relative_to_utc(ledger: Ledger):
    """`+00:00`, `-05:00` and fractional seconds all measure age correctly."""
    blocks = [_planned(i) for i in range(3)]
    ledger.upsert_planned(blocks, now=T0)
    (a,) = ledger.claim("w1", now="2000-01-01T00:00:00+00:00")   # == T0
    (b,) = ledger.claim("w2", now="1999-12-31T19:30:00-05:00")   # == T0 + 30 min
    (c,) = ledger.claim("w3", now="2000-01-01T00:59:00.250Z")    # == T0 + 59 min

    # 45 minute timeout at T0 + 1 h: only the claim at T0 is older.
    assert ledger.reset_stale(older_than_s=45 * 60, now_s=T0_S + 3600.0) == 1
    assert ledger.get(a.key)["status"] == "planned"  # type: ignore[index]
    assert ledger.get(b.key)["status"] == "claimed"  # type: ignore[index]
    assert ledger.get(c.key)["status"] == "claimed"  # type: ignore[index]


# ---- stale claims ----------------------------------------------------------------

def test_reset_stale_reopens_only_rows_older_than_the_timeout(ledger: Ledger):
    """Claimed at T0 and T1; a 55 minute timeout evaluated at T2 catches T0 only."""
    blocks = [_planned(i) for i in range(3)]
    ledger.upsert_planned(blocks, now=T0)
    (old,) = ledger.claim("w1", now=T0)          # 60 min before T2
    (fresh,) = ledger.claim("w2", now=T1)        # 50 min before T2
    ledger.mark_building(old.key, "w1", now=T0)  # building, but still stale

    now_s = T0_S + 3600.0                        # T2 as seconds since the epoch
    assert ledger.reset_stale(older_than_s=55 * 60, now_s=now_s) == 1

    assert ledger.get(old.key)["status"] == "planned"  # type: ignore[index]
    assert ledger.get(old.key)["worker"] is None  # type: ignore[index]
    assert ledger.get(fresh.key)["status"] == "claimed"  # type: ignore[index]
    assert ledger.summary() == {"planned": 2, "claimed": 1}

    # A wider timeout at the same instant leaves the fresh one alone too.
    assert ledger.reset_stale(older_than_s=2 * 3600, now_s=now_s) == 0


def test_mark_building_restarts_the_stale_clock(ledger: Ledger):
    """A long fetch before the build must not count against the build's timeout."""
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    ledger.claim("w1", now=T0)
    ledger.mark_building(pb.key, "w1", now=T2)  # build starts an hour after the claim
    assert ledger.get(pb.key)["claimed_at"] == T2  # type: ignore[index]
    # 30 min timeout evaluated 10 min after the build started: not stale.
    assert ledger.reset_stale(older_than_s=30 * 60, now_s=T0_S + 3600.0 + 600.0) == 0
    assert ledger.get(pb.key)["status"] == "building"  # type: ignore[index]


def test_reset_stale_treats_an_unparseable_or_null_claimed_at_as_stale(ledger: Ledger):
    """A damaged row must be recoverable; julianday returning NULL is not a free pass."""
    blocks = [_planned(i) for i in range(2)]
    ledger.upsert_planned(blocks, now=T0)
    a, b = ledger.claim("w1", n=2, now=T0)
    # Corrupt the clock behind the ledger's back; the ledger itself refuses such values.
    with contextlib.closing(sqlite3.connect(ledger.db_path)) as conn, conn:
        conn.execute("UPDATE blocks SET claimed_at = '946684800' WHERE block = ?", (a.block,))
        conn.execute("UPDATE blocks SET claimed_at = NULL WHERE block = ?", (b.block,))
    # A timeout no real claim could exceed: only the broken clocks are reset.
    assert ledger.reset_stale(older_than_s=1e9, now_s=T0_S) == 2
    assert ledger.summary() == {"planned": 2}


def test_reset_stale_ignores_done_and_failed_rows(ledger: Ledger):
    blocks = [_planned(i) for i in range(2)]
    ledger.upsert_planned(blocks, now=T0)
    a, b = ledger.claim("w1", n=2, now=T0)
    ledger.complete(_done_result(a, "a.h5", "e" * 64, 1), "w1",
                    config_sha256=CONFIG_A, builder_version="0", now=T0)
    ledger.fail(b.key, "w1", "E", "m", retryable=False, now=T0)
    assert ledger.reset_stale(older_than_s=0.0, now_s=1e12) == 0
    assert ledger.summary() == {"done": 1, "failed": 1}


# ---- reconcile -------------------------------------------------------------------

def test_reconcile_reopens_missing_and_changed_files_and_removes_stray_parts(
    ledger: Ledger, tmp_path: Path
):
    out_root = tmp_path / "store"
    (out_root / "sub-001").mkdir(parents=True)
    blocks = [_planned(i) for i in range(3)]
    ledger.upsert_planned(blocks, now=T0)
    intact, deleted, changed = ledger.claim("w1", n=3, now=T0)

    files: dict[str, Path] = {}
    for pb, name in ((intact, "intact.h5"), (deleted, "deleted.h5"), (changed, "changed.h5")):
        path = out_root / "sub-001" / name
        path.write_bytes(f"payload of {name}".encode())
        files[name] = path
        ledger.complete(
            _done_result(pb, f"sub-001/{name}", _sha256(path), path.stat().st_size), "w1",
            config_sha256=CONFIG_A, builder_version="0", now=T1,
        )
    assert ledger.summary() == {"done": 3}

    files["deleted.h5"].unlink()
    files["changed.h5"].write_bytes(b"different bytes")
    stray = out_root / "sub-001" / "half-written.h5.part"
    stray.write_bytes(b"...")
    nested_stray = out_root / "sub-002" / "deeper.part"
    nested_stray.parent.mkdir()
    nested_stray.write_bytes(b"...")

    report = ledger.reconcile(out_root, hasher=_sha256)

    assert isinstance(report, ReconcileReport)
    assert report.checked == 3
    assert report.reopened_missing == [deleted.key]
    assert report.reopened_mismatch == [changed.key]
    assert sorted(report.removed_parts) == ["sub-001/half-written.h5.part", "sub-002/deeper.part"]
    assert not stray.exists()
    assert not nested_stray.exists()

    assert ledger.get(intact.key)["status"] == "done"  # type: ignore[index]
    assert ledger.get(deleted.key)["status"] == "planned"  # type: ignore[index]
    assert ledger.get(changed.key)["status"] == "planned"  # type: ignore[index]
    # The changed file is still there: reconcile reopens rows, it never deletes data.
    assert files["changed.h5"].exists()
    assert files["intact.h5"].exists()

    # Reopened blocks are claimable again.
    assert {pb.key for pb in ledger.claim("w2", n=5, now=T2)} == {deleted.key, changed.key}


def test_reconcile_refuses_to_run_while_workers_are_active_unless_forced(
    ledger: Ledger, tmp_path: Path
):
    """A live worker's .part is indistinguishable from a stray one on disk."""
    out_root = tmp_path / "store"
    (out_root / "sub-001").mkdir(parents=True)
    ledger.upsert_planned([_planned(0)], now=T0)
    (pb,) = ledger.claim("w1", now=T0)
    ledger.mark_building(pb.key, "w1", now=T0)
    live_part = out_root / "sub-001" / "ses-00__Block-0.h5.part"
    live_part.write_bytes(b"partial")

    with pytest.raises(LedgerStateError, match="active"):
        ledger.reconcile(out_root, hasher=_sha256)
    assert live_part.exists()

    # `keep` lets a driver that forces the run still protect what it knows is live.
    report = ledger.reconcile(out_root, hasher=_sha256, force=True,
                              keep=lambda p: p.name.startswith("ses-00__"))
    assert report.removed_parts == []
    assert live_part.exists()

    report = ledger.reconcile(out_root, hasher=_sha256, force=True)
    assert report.removed_parts == ["sub-001/ses-00__Block-0.h5.part"]


def test_reconcile_never_deletes_a_part_that_a_done_row_points_to(
    ledger: Ledger, tmp_path: Path
):
    out_root = tmp_path / "store"
    (out_root / "sub-001").mkdir(parents=True)
    ledger.upsert_planned([_planned(0)], now=T0)
    (pb,) = ledger.claim("w1", now=T0)
    pointed = out_root / "sub-001" / "pointed.h5.part"
    pointed.write_bytes(b"whatever the row says it is")
    ledger.complete(
        _done_result(pb, "sub-001/pointed.h5.part", _sha256(pointed), 1), "w1",
        config_sha256=CONFIG_A, builder_version="0", now=T1,
    )
    report = ledger.reconcile(out_root, hasher=_sha256)
    assert report.removed_parts == []
    assert report.reopened == []
    assert pointed.exists()
    assert ledger.get(pb.key)["status"] == "done"  # type: ignore[index]


def test_reconcile_on_a_root_that_does_not_exist_yet_is_a_no_op(ledger: Ledger, tmp_path: Path):
    report = ledger.reconcile(tmp_path / "nowhere", hasher=_sha256)
    assert report == ReconcileReport()


# ---- summary and listing -----------------------------------------------------------

def test_summary_counts_every_status_and_iter_status_returns_rows_in_key_order(ledger: Ledger):
    blocks = [_planned(i) for i in range(4)]
    ledger.upsert_planned(blocks, now=T0)
    a, b = ledger.claim("w1", n=2, now=T0)
    ledger.mark_building(b.key, "w1", now=T0)
    assert ledger.summary() == {"planned": 2, "claimed": 1, "building": 1}
    planned = ledger.iter_status("planned")
    assert [r["block"] for r in planned] == ["Block-2", "Block-3"]
    assert planned[0]["local_hint"] == "hint-0002"


def test_the_schema_is_idempotent_and_the_key_is_unique(tmp_path: Path):
    led = Ledger(tmp_path / "_ledger.db")
    led.ensure_schema()
    led.ensure_schema()
    led.upsert_planned([_planned(0)], now=T0)
    with (
        contextlib.closing(sqlite3.connect(led.db_path)) as conn,
        pytest.raises(sqlite3.IntegrityError),
    ):
        conn.execute(
            "INSERT INTO blocks (study_id, session, block) VALUES (?, ?, ?)", _planned(0).key
        )


def test_a_failed_transaction_surfaces_the_original_exception(ledger: Ledger):
    """The rollback guard must not replace the caller's error with its own."""
    with pytest.raises(RuntimeError, match="original"), ledger._immediate() as conn:
        conn.execute("COMMIT")  # the transaction is gone before the exception fires
        raise RuntimeError("original")


# ---- privacy: the scrub has the last word ------------------------------------------

def _scrub_from_config() -> tuple[re.Pattern[str], Callable[[str], str]]:
    patterns = load_config().privacy.redact_patterns
    assert patterns, "the shipped config must carry redact patterns"
    joined = re.compile("|".join(f"(?:{p})" for p in patterns))

    def scrub(text: str) -> str:
        return joined.sub("[redacted]", text)

    return joined, scrub


def test_every_free_text_value_passes_through_the_scrub_so_nothing_matching_a_pattern_is_stored(
    tmp_path: Path,
):
    """The ledger SCRUBS free text rather than raises, using the callable it is handed.

    The offending token below is synthetic and shaped like a TDT tank stem only
    so that it matches the shipped `u[gh]\\d{4}-\\d{6}-\\d{6}` pattern. Every
    free-text column is exercised: worker, local_hint, source_format, error
    text, quarantine reason and detail, builder version, and the products
    JSON. Identifiers (the key, output path, hashes) are covered by the next
    test: they are refused, not rewritten.
    """
    joined, scrub = _scrub_from_config()
    stem = "ug0000-000000-000000"
    assert joined.search(stem), "test token must match the shipped pattern"

    db = tmp_path / "_ledger.db"
    led = Ledger(db, scrub=scrub)
    led.ensure_schema()

    blocks = [
        PlannedBlock("sub-001", "ses-00", "Block-0", "tdt_mat", f"staged/{stem}/x"),
        PlannedBlock("sub-001", "ses-00", "Block-1", f"fmt-{stem}", "hint"),
        PlannedBlock("sub-001", "ses-00", "Block-2", "tdt_mat", "hint"),
    ]
    led.upsert_planned(blocks, now=T0)
    worker = f"worker-{stem}"
    a, b, c = led.claim(worker, n=3, now=T0)
    assert stem not in a.local_hint and stem not in b.source_format

    # The same (scrubbed) worker name is what ownership is checked against.
    led.mark_building(a.key, worker, now=T0, source_sha256="d" * 64, source_bytes=1)
    result = BlockResult(
        a.study_id, a.session, a.block, status="done",
        out_relpath="sub-001/clean.h5", out_sha256="e" * 64, out_bytes=1,
        products=[_product(stream=f"mic_{stem}", product="mic", role="mic")],
        epochs_written=[f"Epoc-{stem}"],
    )
    led.complete(result, worker, config_sha256="g" * 64, builder_version=f"v-{stem}", now=T1)
    led.fail(b.key, worker, f"Err{stem}", f"could not open {stem}.mat", retryable=True, now=T1)
    led.quarantine(c.key, worker, f"reason-{stem}", f"see {stem} for detail", now=T1)

    with contextlib.closing(sqlite3.connect(db)) as conn:
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute("SELECT * FROM blocks")]
    # The build clock is the one exception. `claimed_at` and `finished_at`
    # are the caller's `now`, stored verbatim so `reset_stale` can parse them,
    # and the shipped date pattern matches any ISO date including that one.
    # They say when the store was built, never when a recording was made.
    clock_columns = {"claimed_at", "finished_at"}
    for row in rows:
        for column, value in row.items():
            if column in clock_columns:
                assert value in (None, T0, T1), (column, value)
            elif isinstance(value, str):
                assert not joined.search(value), (column, value)
    assert "[redacted]" in led.get(a.key)["worker"]  # type: ignore[index]
    assert "[redacted]" in led.get(a.key)["products_json"]  # type: ignore[index]
    assert "[redacted]" in led.get(b.key)["error_message"]  # type: ignore[index]
    assert "[redacted]" in led.get(c.key)["quarantine_reason"]  # type: ignore[index]

    # Belt and braces: the token never reached the file at all, not even in a
    # page that was later overwritten.
    assert stem.encode() not in db.read_bytes()


def test_an_identifier_the_scrub_would_alter_is_refused_rather_than_rewritten(
    tmp_path: Path,
):
    """A scrubbed relpath or hash is a dangling pointer, so it must never be stored.

    The shipped date pattern would fire on a session name carrying a date;
    the key is refused at planning time. A relpath, output hash, config hash
    or source hash that the scrub would change is refused at completion time
    and the row is left as it was.
    """
    joined, scrub = _scrub_from_config()
    stem = "ug0000-000000-000000"
    led = Ledger(tmp_path / "_ledger.db", scrub=scrub)
    led.ensure_schema()

    with pytest.raises(ValueError, match="session") as info:
        led.upsert_planned(
            [PlannedBlock("sub-001", "ses__2000-01-01", "Block-0", "tdt_mat", "h")], now=T0
        )
    assert "2000-01-01" not in str(info.value)
    assert led.summary() == {}

    pb = _planned(0)
    led.upsert_planned([pb], now=T0)
    led.claim("w1", now=T0)
    with pytest.raises(ValueError, match="source_sha256"):
        led.mark_building(pb.key, "w1", now=T0, source_sha256=f"sha-{stem}")
    for column, kwargs in (
        ("out_relpath", {"relpath": f"sub-001/{stem}.h5"}),
        ("out_sha256", {"sha": f"sha-{stem}"}),
    ):
        args = {"relpath": "sub-001/ok.h5", "sha": "e" * 64, **kwargs}
        with pytest.raises(ValueError, match=column) as info:
            led.complete(_done_result(pb, args["relpath"], args["sha"], 1), "w1",
                         config_sha256="g" * 64, builder_version="0", now=T1)
        assert stem not in str(info.value)
    with pytest.raises(ValueError, match="config_sha256"):
        led.complete(_done_result(pb, "sub-001/ok.h5", "e" * 64, 1), "w1",
                     config_sha256=f"cfg-{stem}", builder_version="0", now=T1)

    row = led.get(pb.key)
    assert row is not None
    assert row["status"] == "claimed"
    assert row["out_relpath"] is None
    assert row["source_sha256"] is None

    # Once stored correctly, the identifier round-trips unchanged and resume works.
    led.complete(_done_result(pb, "sub-001/ok.h5", "e" * 64, 1), "w1",
                 config_sha256="g" * 64, builder_version="0", now=T1)
    assert led.needs_rebuild(pb.key, "g" * 64) is False


def test_without_a_scrub_the_ledger_stores_text_as_given(ledger: Ledger):
    """No privacy logic lives here; the builder must supply the scrub."""
    pb = _planned(0)
    ledger.upsert_planned([pb], now=T0)
    ledger.claim("w1", now=T0)
    ledger.fail(pb.key, "w1", "E", "verbatim message", retryable=False, now=T1)
    assert ledger.get(pb.key)["error_message"] == "verbatim message"  # type: ignore[index]
