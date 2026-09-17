import type { GuardrailHit } from "../api/types";
import type { Tone } from "./ui/tones";
import { Badge } from "./ui";
import { severityTone } from "./ui/tones";

// The severity is already in the badge; the rule shows it a second time as the
// edge of the card, so a blocking finding is findable in a list of eight
// without reading any of them.
const EDGE: Record<Tone, string> = {
  ok: "border-l-ok",
  warn: "border-l-warn",
  danger: "border-l-danger",
  muted: "border-l-line",
};

/** Guardrails, shown with what to do rather than only what is wrong. */
export function GuardrailList({ hits }: { hits: GuardrailHit[] }) {
  if (hits.length === 0) {
    return <p className="text-body text-ink-muted">No guardrails fire for these parameters.</p>;
  }
  return (
    <ul className="space-y-2">
      {hits.map((hit) => {
        const tone = severityTone(hit.severity);
        return (
          <li
            key={hit.guardrail}
            className={`rounded-card border border-l-2 border-line-subtle bg-surface p-2.5
              ${EDGE[tone]}`}
          >
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={tone}>{hit.severity}</Badge>
              <code className="font-mono text-small font-medium text-ink">{hit.guardrail}</code>
              {hit.overridable === "False" && <Badge tone="muted">not overridable</Badge>}
            </div>
            <p className="mt-1.5 max-w-prose text-body text-ink">{hit.message}</p>
            {hit.remedy && (
              <p className="mt-1 max-w-prose text-body text-ink-muted">
                <span className="font-medium text-ink">What to do: </span>
                {hit.remedy}
              </p>
            )}
          </li>
        );
      })}
    </ul>
  );
}
