import type { GuardrailHit } from "../api/types";
import { Badge } from "./ui";
import { severityTone } from "./ui/tones";

/** Guardrails, shown with what to do rather than only what is wrong. */
export function GuardrailList({ hits }: { hits: GuardrailHit[] }) {
  if (hits.length === 0) {
    return <p className="text-body text-ink-muted">No guardrails fire for these parameters.</p>;
  }
  return (
    <ul className="space-y-2">
      {hits.map((hit) => (
        <li key={hit.guardrail} className="rounded border border-line-subtle p-2">
          <div className="flex items-center gap-2">
            <Badge tone={severityTone(hit.severity)}>{hit.severity}</Badge>
            <code className="text-small text-ink">{hit.guardrail}</code>
            {hit.overridable === "False" && <Badge tone="muted">not overridable</Badge>}
          </div>
          <p className="mt-1 text-body text-ink">{hit.message}</p>
          {hit.remedy && <p className="mt-1 text-body text-ink-muted">What to do: {hit.remedy}</p>}
        </li>
      ))}
    </ul>
  );
}
