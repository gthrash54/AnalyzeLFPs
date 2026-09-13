import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api } from "../api/client";
import type { RunRecord } from "../api/types";
import { Badge, EmptyState, Panel } from "../components/ui";
import { severityTone } from "../components/ui/tones";

export function Result() {
  const { runId = "" } = useParams();
  const [record, setRecord] = useState<RunRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.run(runId).then(setRecord).catch((e: Error) => setError(e.message));
  }, [runId]);

  if (error) return <Panel title="Result"><p className="text-body text-danger">{error}</p></Panel>;
  if (!record) return <Panel title="Result"><EmptyState>Loading…</EmptyState></Panel>;

  const figures = record.outputs.filter((o) => o.endsWith(".png"));
  const tables = record.outputs.filter((o) => o.endsWith(".csv") || o.endsWith(".parquet"));
  const normalization = record.summary?.normalization as { sentence?: string } | undefined;

  return (
    <div className="space-y-3">
      <Panel title={record.run_id} hint={`${record.name} · ${record.user}`}>
        <p className="text-body text-ink">{record.claim}</p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Badge tone={record.status === "ok" ? "ok" : "danger"}>{record.status}</Badge>
          {record.git_commit && <code className="text-small text-ink-muted">{record.git_commit.slice(0, 8)}</code>}
          {record.git_dirty && <Badge tone="warn">dirty tree: this code is in no commit</Badge>}
        </div>
        {normalization?.sentence && (
          <p className="mt-2 text-small text-ink-muted">{normalization.sentence}</p>
        )}
      </Panel>

      {(record.guardrails.findings?.length ||
        record.guardrails.overrides?.length ||
        record.guardrails.after?.findings?.length ||
        record.guardrails.after?.overrides?.length) && (
        <Panel title="Guardrails">
          <ul className="space-y-1 text-body">
            {record.guardrails.findings?.map((f) => (
              <li key={f.guardrail} className="flex gap-2">
                <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
                <span className="text-ink">{f.message}</span>
              </li>
            ))}
            {record.guardrails.overrides?.map((o) => (
              <li key={o.guardrail} className="flex gap-2">
                <Badge tone="warn">overridden</Badge>
                <span className="text-ink"><code>{o.guardrail}</code>: {o.reason}</span>
              </li>
            ))}
          </ul>
          {/* Checks that needed the result. Labelled rather than merged, so a
              reader can see which findings were available before the run. */}
          {(record.guardrails.after?.findings?.length ||
            record.guardrails.after?.overrides?.length) && (
            <div className="mt-3 border-t border-stone-200 pt-3">
              <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-stone-500">
                Checked after the run
              </p>
              <ul className="space-y-1 text-sm">
                {record.guardrails.after?.findings?.map((f) => (
                  <li key={f.guardrail} className="flex gap-2">
                    <Badge tone={severityTone(f.severity)}>{f.severity}</Badge>
                    <span className="text-stone-700">{f.message}</span>
                  </li>
                ))}
                {record.guardrails.after?.overrides?.map((o) => (
                  <li key={o.guardrail} className="flex gap-2">
                    <Badge tone="warn">overridden</Badge>
                    <span className="text-stone-700"><code>{o.guardrail}</code>: {o.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </Panel>
      )}

      <Panel title="Figures" hint="The run id is in every caption, so a screenshot carries its provenance">
        {figures.length === 0 ? <EmptyState>No figures.</EmptyState> : (
          <div className="grid gap-3">
            {figures.map((f) => (
              <figure key={f}>
                <img className="w-full rounded border border-line-subtle" src={api.fileUrl(runId, f)} alt={f} />
                <figcaption className="mt-1 text-small text-ink-muted">{f}</figcaption>
              </figure>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Tables">
        {tables.length === 0 ? <EmptyState>No tables.</EmptyState> : (
          <ul className="space-y-1 text-body">
            {tables.map((t) => (
              <li key={t}>
                <a className="text-ink underline" href={api.fileUrl(runId, t)} download>{t}</a>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <Panel title="Parameters">
        <pre className="overflow-x-auto rounded bg-surface-sunken p-2 text-small">
          {JSON.stringify(record.params, null, 2)}
        </pre>
      </Panel>
    </div>
  );
}
