interface Result {
  claim: string;
  value: string;
}

export interface NotebookModuleProps {
  course: string;
  title: string;
  summary: string;
  stem: string;
  builds: Array<[string, string]>;
  underwrites: string[];
  results: Result[];
}

/**
 * Presentation for a module whose teaching happens in the notebook rather than in
 * a widget. Shows what the module assumes, what it establishes, and the numbers
 * its CI-verified test cells actually produce.
 */
export function NotebookModule({
  course,
  title,
  summary,
  stem,
  builds,
  underwrites,
  results,
}: NotebookModuleProps) {
  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-stone-200 bg-stone-900 p-6 text-white shadow-sm">
        <div className="inline-flex items-center gap-2 rounded-md border border-cyan-800/60 bg-cyan-950 px-2.5 py-1 text-xs font-medium text-cyan-400">
          {course}
        </div>
        <h1 className="mt-2 text-2xl font-bold tracking-tight">{title}</h1>
        <p className="mt-1 max-w-3xl text-sm text-stone-300">{summary}</p>
        <div className="mt-4 flex flex-wrap gap-2">
          <a
            href={`/notebooks/${stem}_student.ipynb`}
            download={`${stem}_student.ipynb`}
            className="inline-block rounded-lg bg-cyan-500 px-4 py-2 text-sm font-semibold text-stone-950 shadow-sm transition-colors hover:bg-cyan-400"
          >
            Download Workbook (.ipynb)
          </a>
          <a
            href={`/notebooks/${stem}_solutions.ipynb`}
            download={`${stem}_solutions.ipynb`}
            className="inline-block rounded-lg border border-stone-600 px-4 py-2 text-sm font-semibold text-stone-200 transition-colors hover:bg-stone-800"
          >
            Solutions
          </a>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
          <h2 className="text-sm font-semibold text-stone-900">What it assumes</h2>
          <p className="mt-1 text-xs text-stone-500">
            Nothing is re-derived. Each result below was built somewhere earlier.
          </p>
          <dl className="mt-3 space-y-2">
            {builds.map(([from, what]) => (
              <div key={from} className="rounded-lg border border-stone-200 bg-stone-50 p-2.5">
                <dt className="text-[11px] font-semibold uppercase tracking-wider text-cyan-700">
                  {from}
                </dt>
                <dd className="mt-0.5 text-xs leading-relaxed text-stone-600">{what}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs lg:col-span-2">
          <h2 className="text-sm font-semibold text-stone-900">What it establishes</h2>
          <p className="mt-1 text-xs text-stone-500">
            Every module below is executed on every commit, so these numbers are what
            the code currently produces. Where a number is load-bearing the notebook
            also asserts it; the rest are printed.
          </p>
          <div className="mt-3 space-y-2">
            {results.map((r) => (
              <div
                key={r.claim}
                className="flex flex-wrap items-baseline justify-between gap-2 rounded-lg border border-stone-200 bg-stone-50 p-2.5"
              >
                <span className="text-xs leading-relaxed text-stone-700">{r.claim}</span>
                <span className="font-mono text-xs font-semibold text-cyan-700">{r.value}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-stone-200 bg-white p-5 shadow-xs">
        <h2 className="text-sm font-semibold text-stone-900">What it underwrites in this app</h2>
        <ul className="mt-2 space-y-1.5">
          {underwrites.map((u) => (
            <li key={u} className="flex gap-2 text-xs leading-relaxed text-stone-600">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-cyan-600" />
              <span>{u}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
