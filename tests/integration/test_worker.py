"""A submitted run reaches a result through the queue, on synthetic data.

The unit tests cover the queue's transport. This covers the thing the deployment
actually depends on: a job enqueued by one process is executed by another, the
run record lands on disk, and the job row points at it.

The manifest builder here is a copy of the one in the recipe tests, which is the
established pattern in this suite. Folding all five into a shared builder is
worth doing and is logged in docs/backlog.md rather than done here.
"""

from __future__ import annotations

import csv
import json

import pytest

from dbsspeech.jobs import queue as q
from dbsspeech.jobs.worker import Worker
from tests.fixtures.make_tdt_fixture import N_NEURAL_CH, SFREQ_NEURAL, make_fixture

pytestmark = pytest.mark.integration

SID, SES = "S01", "ses1"
CONTACTS = ["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"]


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    base = tmp_path_factory.mktemp("proj")
    make_fixture(base / "data" / "block" / "synthetic_block.mat")
    m = base / "manifest"
    m.mkdir()

    def write(name, header, rows):
        with (m / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write("subjects.csv",
          ["study_id", "session", "hemisphere", "format", "root_relpath",
           "acquisition", "acquisition_date", "notes"],
          [[SID, SES, "R", "tdt_mat", "block", "acq", "", ""]])
    write("streams.csv",
          ["study_id", "session", "stream", "n_channels", "sfreq_hz", "units",
           "role", "relpath", "notes"],
          [[SID, SES, "neur", str(N_NEURAL_CH), str(SFREQ_NEURAL), "V", "neural", "", ""]])
    write("leads.csv",
          ["study_id", "session", "lead_id", "target", "hemisphere", "lead_model",
           "channel_first", "channel_last", "rotation_deg", "notes"],
          [[SID, SES, "lead1", "stn", "R", "unknown_directional_1331", "1", "8", "0", ""]])
    write("channels.csv",
          ["study_id", "session", "stream", "ch_index", "ch_name", "region",
           "lead_id", "lead_contact", "site", "include", "exclude_reason"],
          [[SID, SES, "neur", str(i + 1), f"c{i+1}", "stn", "lead1", cid, "", "true", ""]
           for i, cid in enumerate(CONTACTS)])
    write("windows.csv",
          ["study_id", "session", "condition", "t_start_s", "t_end_s",
           "derived_from", "status", "notes"],
          [[SID, SES, "overt", "0.0", "2.0", "microphone", "in_use", ""],
           [SID, SES, "metro", "2.0", "4.0", "emg", "in_use", ""]])
    return base


@pytest.fixture
def lab(project, tmp_path):
    """An approved subject, an empty queue, and a worker pointed at both."""
    from dbsspeech.qc import propose, sign

    derivatives = tmp_path / "derivatives"
    propose([], SID, derivatives)      # the fixture recording is clean
    sign(SID, "test-reviewer", derivatives)

    db = derivatives / "runs.db"
    worker = Worker(
        db_path=db,
        data_dir=project / "data",
        runs_dir=tmp_path / "runs",
        derivatives_dir=derivatives,
        manifest_dir=project / "manifest",
        worker_id="test-worker",
        log=lambda *_: None,
    )
    return {"db": db, "worker": worker, "runs": tmp_path / "runs",
            "derivatives": derivatives}


def _enqueue(lab, claim="test run", **params):
    return q.enqueue(
        "psd_by_condition", SID, SES, claim,
        params={"fmax": 200.0, "sfreq_target_hz": SFREQ_NEURAL, **params},
        db_path=lab["db"],
    )


def test_a_queued_job_produces_a_run_record(lab):
    job_id = _enqueue(lab, claim="spectra by condition on the fixture")
    lab["worker"].run_once()

    job = q.get_job(job_id, lab["db"])
    assert job["status"] == "ok"
    assert job["run_id"]
    assert job["finished_at"]

    record = json.loads((lab["runs"] / f"{job['run_id']}.json").read_text())
    assert record["status"] == "ok"
    assert record["claim"] == "spectra by condition on the fixture"
    assert "psd_by_row.csv" in record["outputs"]


def test_attribution_survives_the_queue(lab):
    """Who ran it has to reach the run record, or the record is worth less."""
    job_id = q.enqueue("psd_by_condition", SID, SES, "attributed run",
                       params={"fmax": 200.0, "sfreq_target_hz": SFREQ_NEURAL},
                       user="a-reviewer", db_path=lab["db"])
    lab["worker"].run_once()

    run_id = q.get_job(job_id, lab["db"])["run_id"]
    record = json.loads((lab["runs"] / f"{run_id}.json").read_text())
    assert record["user"] == "a-reviewer"


def test_a_blocked_run_reports_its_guardrails_and_writes_no_record(lab):
    """G1 fires before anything is computed, so there is nothing to mistake for a result."""
    job_id = _enqueue(lab, primary_reference="monopolar")
    lab["worker"].run_once()

    job = q.get_job(job_id, lab["db"])
    assert job["status"] == "blocked"
    assert job["run_id"] is None
    assert any(f["guardrail"].startswith("G1_") for f in job["findings"])
    assert "common-mode" in job["error"]
    assert list((lab["runs"]).glob("*.json")) == []


def test_a_failing_job_is_recorded_and_the_worker_survives_it(lab):
    """A bad job must not take the queue down with it."""
    bad = q.enqueue("psd_by_condition", "S99", SES, "no such subject", db_path=lab["db"])
    good = _enqueue(lab, claim="the next one still runs")

    lab["worker"].run_forever(max_jobs=2)

    failed = q.get_job(bad, lab["db"])
    assert failed["status"] == "failed"
    assert failed["error"]
    assert q.get_job(good, lab["db"])["status"] == "ok"


def test_jobs_are_executed_in_order(lab):
    first = _enqueue(lab, claim="first")
    second = _enqueue(lab, claim="second")

    lab["worker"].run_forever(max_jobs=2)

    a, b = q.get_job(first, lab["db"]), q.get_job(second, lab["db"])
    assert a["status"] == b["status"] == "ok"
    assert a["started_at"] <= b["started_at"]


def test_run_once_on_an_empty_queue_does_nothing(lab):
    assert lab["worker"].run_once() is None
    assert not lab["runs"].exists() or list(lab["runs"].glob("*.json")) == []


def test_a_worker_deregisters_itself_when_it_stops(lab):
    """A clean shutdown must not leave health reporting a worker that is gone."""
    _enqueue(lab)
    lab["worker"].run_forever(max_jobs=1)
    assert q.workers(lab["db"]) == []
    assert q.queue_health(db_path=lab["db"])["queued"] == 0


def test_health_sees_the_finished_job(lab):
    _enqueue(lab)
    lab["worker"].run_forever(max_jobs=1)
    health = q.queue_health(db_path=lab["db"])
    assert health["jobs"] == {"ok": 1}
    assert health["healthy"] is True
