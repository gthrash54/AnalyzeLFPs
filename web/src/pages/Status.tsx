// What an operator needs to answer "is this thing working", and the one screen
// that explains a run which was submitted and has not moved: almost always no
// worker is running.

import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { Health, JobRow } from "../api/types";
import { Badge, DataTable, EmptyState, Panel } from "../components/ui";
import { statusTone } from "../components/ui/tones";
import type { Column } from "../components/ui";

const REFRESH_MS = 5000;

const JOB_COLUMNS: Column<JobRow>[] = [
  {
    key: "enqueued_at",
    header: "submitted",
    value: (job) => job.enqueued_at,
    mono: true,
    className: "text-ink-muted",
  },
  {
    key: "recipe",
    header: "recipe",
    value: (job) => job.recipe,
    render: (job) => (
      <>
        {job.recipe} <span className="text-ink-muted">{job.study_id}</span>
      </>
    ),
  },
  {
    key: "status",
    header: "status",
    value: (job) => job.status,
    render: (job) => <Badge tone={statusTone(job.status)}>{job.status}</Badge>,
  },
  {
    key: "claim",
    header: "claim",
    value: (job) => job.claim,
    render: (job) => (
      <div className="text-ink-muted">
        {job.run_id ? (
          <Link className="text-accent underline" to={`/runs/${job.run_id}`}>
            {job.claim}
          </Link>
        ) : (
          job.claim
        )}
        {job.error && <div className="mt-1 text-small text-danger">{job.error}</div>}
      </div>
    ),
  },
];

function ago(seconds: number | null): string {
  if (seconds === null) return "never";
  if (seconds < 60) return `${Math.round(seconds)}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  return `${Math.round(seconds / 3600)} h ago`;
}

export function Status() {
  const [health, setHealth] = useState<Health | null>(null);
  const [jobs, setJobs] = useState<JobRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    const load = () => {
      api.health()
        .then((h) => { if (live) { setHealth(h); setError(null); } })
        .catch((e: Error) => { if (live) setError(e.message); });
      api.jobs().then((rows) => { if (live) setJobs(rows); }).catch(() => undefined);
    };
    load();
    const timer = setInterval(load, REFRESH_MS);
    return () => { live = false; clearInterval(timer); };
  }, []);

  if (error) {
    return (
      <Panel>
        <p className="text-body text-danger">The API did not answer: {error}</p>
      </Panel>
    );
  }
  if (!health) return <Panel><EmptyState>Loading…</EmptyState></Panel>;

  const q = health.queue;

  return (
    <div className="space-y-4">
      <Panel hint="Refreshes every few seconds.">
        <div className="flex flex-wrap items-center gap-2 text-body">
          <Badge tone={health.ok ? "ok" : "warn"}>{health.ok ? "ok" : "needs attention"}</Badge>
          <span className="text-ink-muted">version {health.versions.app}</span>
          <Badge tone="muted">{health.executor}</Badge>
          <Badge tone={health.auth_required ? "ok" : "warn"}>
            {health.auth_required ? "authenticated" : "no auth"}
          </Badge>
          {!health.data_dir_present && <Badge tone="danger">no data directory</Badge>}
          {!health.manifest_valid && <Badge tone="danger">manifest invalid</Badge>}
        </div>
        {health.manifest_errors.map((e) => (
          <p key={e} className="mt-2 text-body text-danger">{e}</p>
        ))}
      </Panel>

      <Panel
        title="Runs are executed by"
        hint="A worker is a separate process. Without one, submitted runs wait."
      >
        <div className="flex flex-wrap items-center gap-2 text-body">
          <Badge tone={q.workers_responsive ? "ok" : q.queued > 0 ? "danger" : "warn"}>
            {q.workers} worker{q.workers === 1 ? "" : "s"}
          </Badge>
          <span className="text-ink-muted">last heard from {ago(q.seconds_since_worker_seen)}</span>
          <span className="text-ink-muted">{q.queued} queued, {q.running} running</span>
        </div>
        {q.note && <p className="mt-2 text-body text-warn-ink">{q.note}</p>}
      </Panel>

      <Panel title="Databases">
        <table className="w-full text-body">
          <tbody>
            {Object.entries(health.databases).map(([name, db]) => (
              <tr key={name} className="border-t border-line-subtle align-top first:border-t-0">
                <td className="w-24 py-1">{name}</td>
                <td className="py-1">
                  <Badge tone={db.ok ? "ok" : "danger"}>{db.ok ? "ok" : "unreadable"}</Badge>
                </td>
                <td className="py-1 pl-2 font-mono text-small text-ink-muted">{db.path}</td>
                <td className="py-1 pl-2 text-ink-muted">{db.note}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Panel>

      <Panel title="Queue" hint="The most recent submissions, newest first.">
        {jobs.length === 0 ? (
          <EmptyState>Nothing submitted yet.</EmptyState>
        ) : (
          <DataTable
            rows={jobs}
            rowKey={(job) => job.job_id}
            caption="Submitted runs, newest first"
            columns={JOB_COLUMNS}
          />
        )}
      </Panel>

      <Panel title="Versions" hint="The libraries whose version can change a number.">
        <div className="grid grid-cols-2 gap-x-4 text-body sm:grid-cols-3">
          {Object.entries(health.versions).map(([name, version]) => (
            <div key={name} className="flex justify-between border-t border-line-subtle py-1">
              <span className="text-ink-muted">{name}</span>
              <span className="font-mono text-small">{version}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
