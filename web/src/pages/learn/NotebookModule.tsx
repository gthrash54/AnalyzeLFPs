import { Panel } from "../../components/ui";
import { linkButtonClass } from "../../components/ui/tones";

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
 *
 * It used to draw its own dark hero, its own radii and its own cyan, which made
 * the curriculum look like a different product from the rest of the app. The
 * regions are the app's panels now; only the header keeps a tint, because a
 * lesson really is a different kind of screen from a run record.
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
    <div className="space-y-3">
      <header className="rounded-card border border-line bg-surface-sunken p-4">
        <p className="text-micro font-semibold uppercase tracking-wider text-accent">{course}</p>
        <h2 className="mt-1 text-display font-semibold tracking-tight text-ink">{title}</h2>
        <p className="mt-1 max-w-prose text-body text-ink-muted">{summary}</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {/* Real links rather than buttons: these download a file, and a
              middle click should open it. */}
          <a
            href={`/notebooks/${stem}_student.ipynb`}
            download={`${stem}_student.ipynb`}
            className={linkButtonClass}
          >
            Download workbook (.ipynb)
          </a>
          <a
            href={`/notebooks/${stem}_solutions.ipynb`}
            download={`${stem}_solutions.ipynb`}
            className="inline-flex items-center justify-center rounded-control bg-surface px-2.5
              py-1 text-small font-medium text-ink ring-1 ring-inset ring-line transition-colors
              hover:bg-surface-hover"
          >
            Solutions
          </a>
        </div>
      </header>

      <div className="grid gap-3 lg:grid-cols-3">
        <Panel
          title="What it assumes"
          hint="Nothing is re-derived. Each result below was built somewhere earlier."
        >
          <dl className="space-y-2">
            {builds.map(([from, what]) => (
              <div key={from} className="rounded-card border border-line-subtle bg-surface-sunken p-2">
                <dt className="text-micro font-semibold uppercase tracking-wider text-accent">
                  {from}
                </dt>
                <dd className="mt-0.5 text-small leading-relaxed text-ink-muted">{what}</dd>
              </div>
            ))}
          </dl>
        </Panel>

        <div className="lg:col-span-2">
          <Panel
            title="What it establishes"
            hint="Every module is executed on every commit, so these are the numbers the code produces now."
          >
            <ul className="divide-y divide-line-subtle">
              {results.map((r) => (
                <li
                  key={r.claim}
                  className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-0.5
                    py-1.5 first:pt-0 last:pb-0"
                >
                  <span className="text-body leading-relaxed text-ink">{r.claim}</span>
                  <span className="font-mono text-small tabular font-medium text-accent">
                    {r.value}
                  </span>
                </li>
              ))}
            </ul>
          </Panel>
        </div>
      </div>

      <Panel title="What it underwrites in this app">
        <ul className="space-y-1.5">
          {underwrites.map((u) => (
            <li key={u} className="flex gap-2 text-body leading-relaxed text-ink-muted">
              <span aria-hidden="true" className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-accent" />
              <span className="max-w-prose">{u}</span>
            </li>
          ))}
        </ul>
      </Panel>
    </div>
  );
}
