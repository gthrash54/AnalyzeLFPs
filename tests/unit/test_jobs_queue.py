"""The job queue: claiming, heartbeats, terminal states, and reaping.

No recordings and no recipes here. This is the transport, and the property that
matters most is that two workers never get the same job.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime, timedelta

import pytest

from dbsspeech.jobs import queue as q

pytestmark = pytest.mark.unit


@pytest.fixture
def db(tmp_path):
    return tmp_path / "runs.db"


def _enqueue(db, claim="what this run is meant to show", **kw):
    return q.enqueue("psd_by_condition", "S01", "ses1", claim, db_path=db, **kw)


def test_a_queued_job_round_trips(db):
    job_id = _enqueue(db, params={"fmax": 200.0}, overrides={"G10": "under revision"},
                      user="analyst")
    job = q.get_job(job_id, db)
    assert job["status"] == "queued"
    assert job["params"] == {"fmax": 200.0}
    assert job["overrides"] == {"G10": "under revision"}
    assert job["user"] == "analyst"
    assert job["attempts"] == 0
    assert job["run_id"] is None


def test_unknown_job_is_none(db):
    assert q.get_job("nope", db) is None


def test_claiming_marks_the_job_running_and_records_the_worker(db):
    job_id = _enqueue(db)
    claimed = q.claim("worker-a", db)
    assert claimed["job_id"] == job_id
    assert claimed["status"] == "running"
    assert claimed["claimed_by"] == "worker-a"
    assert claimed["attempts"] == 1
    assert claimed["heartbeat_at"]


def test_a_claimed_job_is_not_claimed_again(db):
    _enqueue(db)
    assert q.claim("worker-a", db) is not None
    assert q.claim("worker-b", db) is None


def test_claiming_an_empty_queue_returns_none(db):
    assert q.claim("worker-a", db) is None


def test_jobs_are_claimed_oldest_first(db):
    first = _enqueue(db, claim="first")
    second = _enqueue(db, claim="second")
    assert q.claim("worker-a", db)["job_id"] == first
    assert q.claim("worker-b", db)["job_id"] == second


def test_concurrent_workers_never_share_a_job(db):
    """The whole point of IMMEDIATE. Ten threads, five jobs, no duplicates."""
    ids = {_enqueue(db, claim=f"job {i}") for i in range(5)}
    got: list[str] = []
    lock = threading.Lock()

    def take(name: str) -> None:
        job = q.claim(name, db)
        if job is not None:
            with lock:
                got.append(job["job_id"])

    threads = [threading.Thread(target=take, args=(f"worker-{i}",)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert sorted(got) == sorted(ids)
    assert len(set(got)) == len(got)


def test_finishing_records_the_run_id(db):
    job_id = _enqueue(db)
    q.claim("worker-a", db)
    q.finish(job_id, "ok", run_id="20260908_120000_psd_by_condition", db_path=db)
    job = q.get_job(job_id, db)
    assert job["status"] == "ok"
    assert job["run_id"] == "20260908_120000_psd_by_condition"
    assert job["finished_at"]


def test_a_blocked_job_keeps_its_findings(db):
    """A block is the useful answer, so it has to survive the transport intact."""
    job_id = _enqueue(db)
    q.claim("worker-a", db)
    q.finish(job_id, "blocked", error="G6 refuses a band above the cutoff",
             findings=[{"guardrail": "G6", "severity": "block",
                        "message": "band above the anti-alias cutoff",
                        "remedy": "raise sfreq_target_hz", "overridable": False}],
             db_path=db)
    job = q.get_job(job_id, db)
    assert job["status"] == "blocked"
    assert job["findings"][0]["guardrail"] == "G6"
    assert job["findings"][0]["overridable"] is False


def test_finish_refuses_a_non_terminal_state(db):
    job_id = _enqueue(db)
    with pytest.raises(ValueError, match="terminal"):
        q.finish(job_id, "running", db_path=db)


def test_heartbeat_only_from_the_worker_that_holds_the_job(db):
    """Otherwise a second worker could keep a dead job looking alive."""
    job_id = _enqueue(db)
    q.claim("worker-a", db)
    _backdate(db, job_id, seconds=600)
    stale = q.get_job(job_id, db)["heartbeat_at"]

    q.heartbeat(job_id, "worker-b", db)
    assert q.get_job(job_id, db)["heartbeat_at"] == stale

    q.heartbeat(job_id, "worker-a", db)
    assert q.age_seconds(q.get_job(job_id, db)["heartbeat_at"]) < 5


def _backdate(db, job_id, seconds):
    """Age a heartbeat without sleeping."""
    stamp = (datetime.now(UTC) - timedelta(seconds=seconds)).isoformat(timespec="seconds")
    with sqlite3.connect(db) as conn:
        conn.execute("UPDATE jobs SET heartbeat_at = ? WHERE job_id = ?", (stamp, job_id))


def test_a_stale_job_is_failed_with_a_reason_that_says_output_may_be_partial(db):
    job_id = _enqueue(db)
    q.claim("worker-a", db)
    _backdate(db, job_id, seconds=600)

    assert q.reap_stale(120.0, db) == [job_id]
    job = q.get_job(job_id, db)
    assert job["status"] == "failed"
    assert "partial" in job["error"]
    assert "worker-a" in job["error"]


def test_a_live_job_is_not_reaped(db):
    job_id = _enqueue(db)
    q.claim("worker-a", db)
    assert q.reap_stale(120.0, db) == []
    assert q.get_job(job_id, db)["status"] == "running"


def test_a_stale_job_is_not_requeued(db):
    """Deliberate: re-running automatically would hide a half-written result."""
    job_id = _enqueue(db)
    q.claim("worker-a", db)
    _backdate(db, job_id, seconds=600)
    q.reap_stale(120.0, db)
    assert q.claim("worker-b", db) is None
    assert q.get_job(job_id, db)["attempts"] == 1


def test_listing_filters_by_status(db):
    ok_id = _enqueue(db, claim="finished")
    _enqueue(db, claim="waiting")
    q.claim("worker-a", db)
    q.finish(ok_id, "ok", run_id="r1", db_path=db)

    assert [j["job_id"] for j in q.list_jobs("ok", db_path=db)] == [ok_id]
    assert len(q.list_jobs(db_path=db)) == 2


# ---- workers ------------------------------------------------------------------

def test_a_registered_worker_is_reported_as_recently_seen(db):
    q.register_worker("worker-a", db)
    seen = q.workers(db)
    assert len(seen) == 1
    assert seen[0]["state"] == "idle"
    assert seen[0]["seconds_since_seen"] < 5


def test_a_worker_that_shut_down_cleanly_is_not_reported_as_late(db):
    q.register_worker("worker-a", db)
    q.unregister_worker("worker-a", db)
    assert q.workers(db) == []


def test_health_is_unhealthy_when_work_is_queued_and_nothing_is_running(db):
    _enqueue(db)
    health = q.queue_health(db_path=db)
    assert health["queued"] == 1
    assert health["workers"] == 0
    assert health["healthy"] is False
    assert "no worker" in health["note"]


def test_health_is_healthy_with_a_live_worker(db):
    _enqueue(db)
    q.register_worker("worker-a", db)
    health = q.queue_health(db_path=db)
    assert health["workers_responsive"] is True
    assert health["healthy"] is True
    assert health["note"] == ""


def test_an_idle_queue_with_no_worker_is_healthy_but_says_so(db):
    """Nothing is wrong yet, and the reason a run would wait is still worth saying."""
    health = q.queue_health(db_path=db)
    assert health["healthy"] is True
    assert "would wait" in health["note"]


def test_health_counts_jobs_by_status(db):
    ok_id = _enqueue(db, claim="one")
    _enqueue(db, claim="two")
    q.claim("worker-a", db)
    q.finish(ok_id, "ok", run_id="r1", db_path=db)
    assert q.queue_health(db_path=db)["jobs"] == {"ok": 1, "queued": 1}


def test_reading_a_queue_that_does_not_exist_creates_nothing(tmp_path):
    """A health check that creates a database is changing what it reports on.

    It also silently makes a directory, which on a deployment is how you get a
    queue in a path nobody meant to use.
    """
    missing = tmp_path / "nowhere" / "runs.db"

    assert q.get_job("anything", missing) is None
    assert q.list_jobs(db_path=missing) == []
    assert q.workers(missing) == []
    assert q.reap_stale(120.0, missing) == []
    health = q.queue_health(db_path=missing)

    assert health["jobs"] == {}
    assert health["queued"] == 0
    assert not missing.exists()
    assert not missing.parent.exists()


def test_the_first_write_does_create_it(tmp_path):
    """Reads stay out of the way; a write is allowed to bring it into being."""
    db = tmp_path / "nowhere" / "runs.db"
    _enqueue(db)
    assert db.exists()
    assert len(q.list_jobs(db_path=db)) == 1


def test_age_seconds_tolerates_a_missing_or_unparsable_stamp():
    assert q.age_seconds(None) is None
    assert q.age_seconds("") is None
    assert q.age_seconds("not a timestamp") is None
