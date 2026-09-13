import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { DecisionRow, QcState } from "../api/types";
import type { ActionOption, FlagMeaning } from "../components/FlagRow";
import { FlagRow } from "../components/FlagRow";
import { Badge, Button, EmptyState, Panel } from "../components/ui";
import { inputClass, statusTone } from "../components/ui/tones";

/** Reviewing a subject: read the report, decide each flag, sign. */
export function Qc() {
  const { studyId = "" } = useParams();
  const [state, setState] = useState<QcState | null>(null);
  const [reviewer, setReviewer] = useState(
    () => localStorage.getItem("dbsspeech.reviewer") ?? "",
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState("");
  // What a flag means and what may be done about it, both from
  // configs/qc_thresholds.yaml. The screen shows the lab's words, not its own.
  const [actions, setActions] = useState<ActionOption[]>([]);
  const [meanings, setMeanings] = useState<Record<string, FlagMeaning>>({});

  const load = useCallback(() => {
    api.qc(studyId).then(setState).catch((e: Error) => setError(e.message));
  }, [studyId]);

  useEffect(load, [load]);

  useEffect(() => {
    api.qcVocabulary()
      .then(({ actions: a, detectors }) => { setActions(a); setMeanings(detectors); })
      // A missing vocabulary is not worth blocking a review over: the rows fall
      // back to the detector's own name and the proposed action.
      .catch(() => undefined);
  }, []);
  useEffect(() => localStorage.setItem("dbsspeech.reviewer", reviewer), [reviewer]);

  const act = async (fn: () => Promise<QcState>) => {
    setBusy(true);
    setError(null);
    try {
      setState(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : (e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  const active = useMemo(
    () => (state?.decisions ?? []).filter((d) => d.status === "active"),
    [state],
  );
  const shown = useMemo(
    () => (filter ? active.filter((d) => d.flag_type === filter) : active),
    [active, filter],
  );
  const types = useMemo(
    () => Array.from(new Set(active.map((d) => d.flag_type))).sort(),
    [active],
  );

  if (error && !state) return <Panel title="QC"><p className="text-body text-danger">{error}</p></Panel>;
  if (!state) return <Panel title="QC"><EmptyState>Loading…</EmptyState></Panel>;

  const canSign = state.n_undecided === 0 && reviewer.trim().length > 0;

  const decide = (
    row: DecisionRow,
    decision: { approved: boolean; reason: string; action_taken: string | null },
  ) =>
    act(() => api.qcDecide(studyId, {
      flag_id: row.flag_id,
      approved: decision.approved,
      reviewer,
      reason: decision.reason,
      action_taken: decision.action_taken,
    }));

  return (
    <div className="space-y-3">
      <Panel>
        <div className="flex flex-wrap items-center gap-3">
          <Badge tone={statusTone(state.status)}>{state.status}</Badge>
          <span className="text-body text-ink-muted">
            {state.n_flags} flags, <b>{state.n_undecided}</b> undecided
          </span>
          <input
            className={inputClass}
            placeholder="your name (required to decide)"
            value={reviewer}
            onChange={(e) => setReviewer(e.target.value)}
          />
          <Button
            disabled={busy}
            onClick={() => act(() => api.qcPropose(studyId))}
          >
            Re-run detection
          </Button>
          <Button
            variant="primary"
            disabled={busy || !canSign}
            onClick={() => act(() => api.qcSign(studyId, reviewer))}
          >
            Sign off
          </Button>
          {!canSign && state.n_undecided > 0 && (
            <span className="text-small text-ink-muted">
              {state.n_undecided} flag(s) still undecided.
            </span>
          )}
        </div>
        {error && <p className="mt-2 text-body text-danger">{error}</p>}
        {state.history.length > 0 && (
          <ul className="mt-3 space-y-0.5 text-small text-ink-muted">
            {state.history.slice(-4).map((h, i) => (
              <li key={i}>
                {h.at} · <b>{h.event}</b> by {h.reviewer} {h.reason ?? ""}
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel title="Report" hint="Generated from the same detection pass">
          {state.report_available ? (
            <iframe
              title="QC report"
              className="h-[70vh] w-full rounded border border-line-subtle"
              src={api.qcReportUrl(studyId)}
            />
          ) : (
            <EmptyState>No report yet. Run detection.</EmptyState>
          )}
        </Panel>

        <Panel title="Flags" hint="Rejecting a flag requires a reason">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <select
              className={inputClass}
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
            >
              <option value="">all types ({active.length})</option>
              {types.map((t) => (
                <option key={t} value={t}>
                  {t} ({active.filter((d) => d.flag_type === t).length})
                </option>
              ))}
            </select>
            {/* Bulk approval must state its scope, so it is only offered when a
                type is selected. There is no approve-everything button. */}
            <Button
              disabled={busy || !filter || !reviewer.trim()}
              title={filter ? `Approve all ${filter}` : "Pick a flag type first"}
              onClick={() => act(() => api.qcDecideBulk(studyId, {
                approved: true, reviewer, flag_type: filter,
                reason: `bulk approval of ${filter}`,
              }))}
            >
              {filter ? `Approve all ${filter}` : "Approve all of one type"}
            </Button>
          </div>

          {shown.length === 0 ? (
            <EmptyState>Nothing to review here.</EmptyState>
          ) : (
            <ul className="max-h-[62vh] overflow-y-auto">
              {shown.map((row) => (
                <FlagRow
                  key={row.flag_id}
                  row={row}
                  meaning={meanings[row.flag_type]}
                  actions={actions}
                  busy={busy}
                  canDecide={reviewer.trim().length > 0}
                  onDecide={(decision) => decide(row, decision)}
                />
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </div>
  );
}
