"""The process that executes queued runs.

One loop: claim a job, run the recipe through `registry.run`, record what
happened. The worker adds nothing scientific. It does not touch parameters, skip
the QC gate, or decide anything about a result; it is the thing that lets a run
outlive the HTTP request that asked for it.

Runs stay serial per worker. A recipe reads a whole recording into memory, so two
at once on a lab machine is how you get an out-of-memory kill halfway through
someone's analysis. Concurrency is more worker processes, deliberately started.
"""

from __future__ import annotations

import signal
import threading
import time
from pathlib import Path
from typing import Any

from ..guardrails import GuardrailBlocked
from ..recipes import get as get_recipe
from ..recipes import run as run_recipe
from . import queue as q

# How often a busy worker says it is still alive. Well under the stale threshold,
# so one missed pulse does not fail a healthy job.
DEFAULT_HEARTBEAT_S = 15.0
DEFAULT_POLL_S = 2.0


class Worker:
    """Claims and executes jobs. One at a time, in this process."""

    def __init__(
        self,
        db_path: Path | None = None,
        data_dir: Path | None = None,
        runs_dir: Path | None = None,
        derivatives_dir: Path | None = None,
        manifest_dir: Path | None = None,
        poll_interval_s: float = DEFAULT_POLL_S,
        heartbeat_interval_s: float = DEFAULT_HEARTBEAT_S,
        stale_after_s: float = q.DEFAULT_STALE_AFTER_S,
        worker_id: str | None = None,
        log: Any = print,
    ) -> None:
        self.derivatives_dir = Path(derivatives_dir) if derivatives_dir else None
        self.db_path = Path(db_path) if db_path else q.default_db_path(self.derivatives_dir)
        self.data_dir = Path(data_dir) if data_dir else None
        self.runs_dir = Path(runs_dir) if runs_dir else None
        self.manifest_dir = Path(manifest_dir) if manifest_dir else None
        self.poll_interval_s = poll_interval_s
        self.heartbeat_interval_s = heartbeat_interval_s
        self.stale_after_s = stale_after_s
        self.worker_id = worker_id or q.make_worker_id()
        self.log = log
        self._stop = threading.Event()

    # -- lifecycle ---------------------------------------------------------

    def stop(self) -> None:
        """Ask the loop to finish the current job and then exit."""
        self._stop.set()

    def install_signal_handlers(self) -> None:
        """SIGTERM and SIGINT stop after the current job, not during it.

        Docker sends SIGTERM and waits before SIGKILL. Abandoning a recipe
        mid-write to save a few seconds of shutdown would leave exactly the
        partial output that `reap_stale` then has to warn about.
        """
        def handle(signum, _frame):  # noqa: ANN001 - signal handler signature
            name = signal.Signals(signum).name
            self.log(f"{name} received; finishing the current job, then stopping")
            self.stop()

        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, handle)

    # -- the loop ----------------------------------------------------------

    def run_forever(self, max_jobs: int | None = None) -> int:
        """Poll until stopped. Returns the number of jobs executed.

        Reaping happens here rather than in `/health` because a health check
        should report state, not change it. The consequence is worth stating:
        when the only worker dies, its job stays `running` until a worker is
        started again, which is also the moment anyone can do something about it.
        """
        q.register_worker(self.worker_id, self.db_path)
        self.log(f"worker {self.worker_id} ready; db {self.db_path}")
        done = 0
        try:
            while not self._stop.is_set():
                for job_id in q.reap_stale(self.stale_after_s, self.db_path):
                    self.log(f"failed stale job {job_id}: its worker stopped without finishing")
                job = q.claim(self.worker_id, self.db_path)
                if job is None:
                    q.worker_seen(self.worker_id, "idle", None, self.db_path)
                    self._stop.wait(self.poll_interval_s)
                    continue
                self.execute(job)
                done += 1
                if max_jobs is not None and done >= max_jobs:
                    break
        finally:
            q.unregister_worker(self.worker_id, self.db_path)
            self.log(f"worker {self.worker_id} stopped after {done} job(s)")
        return done

    def run_once(self) -> dict[str, Any] | None:
        """Claim and execute at most one job. Returns the finished job, or None."""
        q.register_worker(self.worker_id, self.db_path)
        try:
            job = q.claim(self.worker_id, self.db_path)
            if job is None:
                return None
            self.execute(job)
            return q.get_job(job["job_id"], self.db_path)
        finally:
            q.unregister_worker(self.worker_id, self.db_path)

    # -- one job -----------------------------------------------------------

    def execute(self, job: dict[str, Any]) -> None:
        """Run one job to a terminal state. Never raises for a failed recipe.

        A recipe that raises is a result about the recipe, not about the worker:
        it belongs in the job row where the person who submitted it will see it.
        A worker that exits on a bad parameter takes every queued job down with
        it.
        """
        job_id = job["job_id"]
        q.worker_seen(self.worker_id, "busy", job_id, self.db_path)
        self.log(f"{job_id}: {job['recipe']} on {job['study_id']}/{job['session']}")
        pulse = self._start_pulse(job_id)
        try:
            run_id = run_recipe(
                job["recipe"], job["study_id"], job["session"],
                claim=job["claim"], params=job["params"],
                overrides=job["overrides"] or None, user=job["user"],
                manifest_dir=self.manifest_dir, data_dir=self.data_dir,
                runs_dir=self.runs_dir, derivatives_dir=self.derivatives_dir,
            )
        except GuardrailBlocked as exc:
            q.finish(job_id, "blocked", error=str(exc),
                     findings=[
                         {"guardrail": f.guardrail, "severity": f.severity.value,
                          "message": f.message, "remedy": f.remedy,
                          "overridable": f.overridable}
                         for f in exc.findings
                     ],
                     db_path=self.db_path)
            self.log(f"{job_id}: blocked by guardrails")
        except Exception as exc:  # noqa: BLE001 - reported to whoever submitted it
            q.finish(job_id, "failed", error=f"{type(exc).__name__}: {exc}",
                     db_path=self.db_path)
            self.log(f"{job_id}: failed: {type(exc).__name__}: {exc}")
        else:
            q.finish(job_id, "ok", run_id=run_id, db_path=self.db_path)
            self.log(f"{job_id}: ok, run {run_id}")
        finally:
            pulse.set()
            q.worker_seen(self.worker_id, "idle", None, self.db_path)

    def _start_pulse(self, job_id: str) -> threading.Event:
        """Heartbeat on a separate thread, because the recipe blocks this one."""
        stop = threading.Event()

        def beat() -> None:
            while not stop.wait(self.heartbeat_interval_s):
                q.heartbeat(job_id, self.worker_id, self.db_path)
                q.worker_seen(self.worker_id, "busy", job_id, self.db_path)

        threading.Thread(target=beat, name=f"heartbeat-{job_id}", daemon=True).start()
        return stop


def validate_job(recipe: str, params: dict[str, Any]) -> None:
    """Raise if a recipe name or its parameters are wrong. Used before enqueueing.

    Kept beside the worker so the check that guards the queue and the code that
    drains it cannot drift apart.
    """
    spec = get_recipe(recipe)
    spec.params_model(**(params or {}))


def main(argv: list[str] | None = None) -> int:
    """`python -m dbsspeech.jobs.worker`, for a container entrypoint."""
    from ..cli import main as cli_main

    return cli_main(["worker", *(argv or [])])


if __name__ == "__main__":  # pragma: no cover - container entrypoint
    raise SystemExit(main())


# Kept out of the class so a caller can wait without constructing a worker.
def wait_for(
    job_id: str,
    timeout_s: float = 60.0,
    interval_s: float = 0.25,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Block until a job reaches a terminal state. For tests and scripts."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        job = q.get_job(job_id, db_path)
        if job is not None and job["status"] in q.DONE:
            return job
        time.sleep(interval_s)
    return q.get_job(job_id, db_path)


__all__ = [
    "DEFAULT_HEARTBEAT_S",
    "DEFAULT_POLL_S",
    "Worker",
    "main",
    "validate_job",
    "wait_for",
]
