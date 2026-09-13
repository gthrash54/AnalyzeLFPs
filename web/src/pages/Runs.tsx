import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { RunSummaryRow } from "../api/types";
import { Badge, DataTable, EmptyState, Panel, Skeleton } from "../components/ui";
import { statusTone } from "../components/ui/tones";
import type { Column } from "../components/ui";

const COLUMNS: Column<RunSummaryRow>[] = [
  {
    key: "run_id",
    header: "run",
    value: (r) => r.run_id,
    mono: true,
    render: (r) => (
      <Link className="text-accent underline" to={`/runs/${r.run_id}`}>
        {r.run_id}
      </Link>
    ),
  },
  { key: "name", header: "recipe", value: (r) => r.name },
  {
    key: "status",
    header: "status",
    value: (r) => r.status,
    render: (r) => (
      <span className="flex flex-wrap gap-1">
        <Badge tone={statusTone(r.status)}>{r.status}</Badge>
        {r.n_overrides > 0 && <Badge tone="warn">{r.n_overrides} overridden</Badge>}
        {/* A result from a dirty tree came from code in no commit. */}
        {r.git_dirty === 1 && <Badge tone="warn">dirty tree</Badge>}
      </span>
    ),
  },
  {
    key: "claim",
    header: "claim",
    value: (r) => r.claim,
    render: (r) => <span className="text-ink-muted">{r.claim}</span>,
  },
];

export function Runs() {
  const [rows, setRows] = useState<RunSummaryRow[] | null>(null);
  useEffect(() => { api.runs().then(setRows).catch(() => setRows([])); }, []);

  if (!rows) {
    return <Panel><Skeleton rows={5} /></Panel>;
  }
  if (rows.length === 0) {
    return (
      <Panel>
        <EmptyState>
          No runs yet. Start one from the Run screen, or build a demo project with
          `python -m dbsspeech seed`.
        </EmptyState>
      </Panel>
    );
  }

  return (
    <Panel>
      <DataTable
        rows={rows}
        rowKey={(r) => r.run_id}
        columns={COLUMNS}
        initialSort={{ key: "run_id", direction: "desc" }}
        caption="Every run, including the ones that failed or were blocked"
      />
    </Panel>
  );
}
