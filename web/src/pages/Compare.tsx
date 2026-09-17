import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api/client";
import type { Comparison, RunSummaryRow } from "../api/types";
import { Badge, EmptyState, Panel } from "../components/ui";
import { inputClass } from "../components/ui/tones";

const show = (v: unknown) =>
  v === undefined ? <i className="text-ink-muted">unset</i> : JSON.stringify(v);

/** Two runs side by side. "Which settings did you use" becomes a lookup. */
export function Compare() {
  const [search, setSearch] = useSearchParams();
  const [runs, setRuns] = useState<RunSummaryRow[]>([]);
  // Keyed by the pair it describes. Without the key, a slow answer for one
  // pair can arrive after a fast answer for the next and overwrite it, which
  // shows one run's parameters under another run's heading.
  const [result, setResult] = useState<{ pair: string; data: Comparison } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [onlyChanged, setOnlyChanged] = useState(true);

  const a = search.get("a") ?? "";
  const b = search.get("b") ?? "";

  useEffect(() => {
    api.runs().then(setRuns).catch(() => setRuns([]));
  }, []);

  const pair = `${a}|${b}`;

  useEffect(() => {
    if (!a || !b) return;
    let live = true;
    api.compare(a, b)
      // Cleared on success rather than before the request, so the effect does
      // not set state synchronously just to blank a field.
      .then((data) => { if (live) { setResult({ pair, data }); setError(null); } })
      .catch((e: Error) => { if (live) setError(e.message); });
    return () => { live = false; };
  }, [a, b, pair]);

  // Derived rather than cleared in an effect: clearing state synchronously
  // inside an effect starts a second render for something already knowable here.
  const comparison = result?.pair === pair ? result.data : null;

  const pick = (side: "a" | "b", value: string) => {
    const next = new URLSearchParams(search);
    next.set(side, value);
    setSearch(next);
  };

  const selector = (side: "a" | "b", value: string) => (
    <select
      className={inputClass}
      value={value}
      onChange={(e) => pick(side, e.target.value)}
    >
      <option value="">choose a run…</option>
      {runs.map((r) => (
        <option key={r.run_id} value={r.run_id}>
          {r.run_id} · {r.name}
        </option>
      ))}
    </select>
  );

  const rows = comparison
    ? comparison.params.filter((row) => !onlyChanged || row.changed)
    : [];

  return (
    <div className="space-y-3">
      <Panel>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block">
            <span className="text-small font-medium text-ink">A</span>
            {selector("a", a)}
          </label>
          <label className="block">
            <span className="text-small font-medium text-ink">B</span>
            {selector("b", b)}
          </label>
        </div>
        {error && (
          <p className="mt-3 rounded-control bg-danger-soft px-2 py-1.5 text-body text-danger-ink">
            {error}
          </p>
        )}
      </Panel>

      {!comparison && <Panel title="Difference"><EmptyState>Pick two runs.</EmptyState></Panel>}

      {comparison && (
        <>
          <Panel title="Difference" hint={`${comparison.n_changed} parameter(s) differ`}>
            <div className="mb-3 flex flex-wrap gap-2">
              {/* Two things that quietly invalidate a comparison, said out loud. */}
              {!comparison.same_recipe && (
                <Badge tone="warn">different recipes: not a like-for-like comparison</Badge>
              )}
              {!comparison.same_code && (
                <Badge tone="warn">different code versions: the difference may be the code</Badge>
              )}
              {(comparison.a.git_dirty || comparison.b.git_dirty) && (
                <Badge tone="warn">a run came from a dirty tree; its code is in no commit</Badge>
              )}
              {comparison.same_recipe && comparison.same_code && comparison.n_changed === 0 && (
                <Badge tone="ok">same recipe, same code, identical parameters</Badge>
              )}
            </div>

            <label className="mb-2 flex w-fit items-center gap-2 text-small text-ink-muted
              transition-colors hover:text-ink">
              <input
                type="checkbox"
                className="accent-accent"
                checked={onlyChanged}
                onChange={(e) => setOnlyChanged(e.target.checked)}
              />
              only show parameters that differ
            </label>

            {rows.length === 0 ? (
              <EmptyState>No parameters differ.</EmptyState>
            ) : (
              <div className="-mx-3 -mb-3 overflow-x-auto">
                <table className="w-full min-w-xl border-collapse text-body">
                  <thead className="bg-surface-sunken text-left text-small text-ink-muted">
                    <tr>
                      <th scope="col" className="border-y border-line px-2 py-2 font-medium">
                        parameter
                      </th>
                      <th scope="col" className="border-y border-line px-2 py-2 font-medium">A</th>
                      <th scope="col" className="border-y border-line px-2 py-2 font-medium">B</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => (
                      <tr
                        key={row.param}
                        className={`border-b border-line-subtle last:border-0 ${
                          row.changed ? "bg-warn-soft" : ""
                        }`}
                      >
                        <td className="px-2 py-2 font-medium text-ink">{row.param}</td>
                        <td className="px-2 py-2 font-mono text-small tabular text-ink">
                          {show(row.a)}
                        </td>
                        <td className="px-2 py-2 font-mono text-small tabular text-ink">
                          {show(row.b)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Panel>

          <Panel title="Claims">
            <div className="grid gap-3 sm:grid-cols-2 text-body">
              {[comparison.a, comparison.b].map((side) => (
                <div key={side.run_id}>
                  <div className="font-mono text-micro text-ink-muted">{side.run_id}</div>
                  <p className="mt-1 max-w-prose text-ink">{side.claim}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel title="Figures" hint="Matched by filename, so the same panel sits beside itself">
            {comparison.shared_figures.length === 0 ? (
              <EmptyState>No figures in common.</EmptyState>
            ) : (
              <div className="space-y-4">
                {comparison.shared_figures.map((name) => (
                  <div key={name}>
                    <div className="mb-1 font-mono text-small text-ink-muted">{name}</div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <img
                        className="w-full rounded-card border border-line-subtle bg-surface"
                        src={api.fileUrl(comparison.a.run_id, name)}
                        alt={`A ${name}`}
                      />
                      <img
                        className="w-full rounded-card border border-line-subtle bg-surface"
                        src={api.fileUrl(comparison.b.run_id, name)}
                        alt={`B ${name}`}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </Panel>
        </>
      )}
    </div>
  );
}
