// One QC flag, and the decision about it.
//
// A flag asks two questions and they are separate. Is the observation real, and
// what should be done about it. The old screen offered approve or reject, which
// silently answered the second with whatever detection proposed. That made the
// most important review decision in this project impossible to express: a
// stimulating contact is genuinely spiky, and excluding it deletes the signal
// the recording was made for. The right answer is to approve the flag and take
// no action, with a reason.
//
// Every word here comes from configs/qc_thresholds.yaml: the flag's plain name,
// what it means, and the actions on offer. A reviewer reads what the lab wrote,
// not what a component author guessed.

import { useState } from "react";
import type { DecisionRow } from "../api/types";
import { Badge, Button } from "./ui";
import { inputClass, severityTone } from "./ui/tones";

export interface ActionOption {
  value: string;
  label: string;
  description: string;
}

export interface FlagMeaning {
  label: string;
  means: string;
}

/** Evidence arrives as `key=value, key=value`. Shown as pairs, not as a string. */
function evidencePairs(summary: string): [string, string][] {
  return summary
    .split(",")
    .map((part) => part.trim())
    .filter(Boolean)
    .map((part) => {
      const [key, ...rest] = part.split("=");
      return [key.trim().replace(/_/g, " "), rest.join("=").trim()] as [string, string];
    });
}

export function FlagRow({ row, meaning, actions, busy, canDecide, onDecide }: {
  row: DecisionRow;
  meaning?: FlagMeaning;
  actions: ActionOption[];
  busy: boolean;
  canDecide: boolean;
  onDecide: (decision: {
    approved: boolean;
    reason: string;
    action_taken: string | null;
  }) => void;
}) {
  const [open, setOpen] = useState(false);
  const [action, setAction] = useState(row.proposed_action || "none");
  const [reason, setReason] = useState("");

  const decided = Boolean(row.approved);
  const changedAction = action !== (row.proposed_action || "none");
  const chosen = actions.find((a) => a.value === action);

  // The package refuses a rejection or a changed action without a reason. The
  // button says so rather than the server saying it after a click.
  const needsReason = changedAction;
  const canSubmit = canDecide && !busy && (!needsReason || reason.trim().length > 0);

  return (
    <li className="border-b border-line-subtle py-2 last:border-0">
      <div className="flex flex-wrap items-baseline gap-2">
        <Badge tone={severityTone(row.severity)}>{row.severity}</Badge>
        <span className="font-medium text-ink">{meaning?.label ?? row.flag_type}</span>
        <span className="font-mono text-micro text-ink-muted">{row.target}</span>
        {decided && (
          <Badge tone={row.approved === "true" ? "ok" : "muted"}>
            {row.approved === "true" ? "approved" : "rejected"}
            {row.action_taken ? ` · ${row.action_taken}` : ""}
          </Badge>
        )}
      </div>

      {meaning?.means && (
        <p className="mt-0.5 text-small text-ink-muted">{meaning.means}</p>
      )}

      {row.evidence_summary && (
        <dl className="mt-1 flex flex-wrap gap-x-4 gap-y-0.5">
          {evidencePairs(row.evidence_summary).map(([key, value]) => (
            <div key={key} className="flex gap-1">
              <dt className="text-micro text-ink-muted">{key}</dt>
              <dd className="font-mono text-micro tabular text-ink">{value}</dd>
            </div>
          ))}
        </dl>
      )}

      {decided ? (
        row.reason && <p className="mt-1 text-small text-ink-muted">{row.reason}</p>
      ) : !open ? (
        <div className="mt-2 flex flex-wrap gap-1">
          <Button
            variant="primary"
            disabled={!canDecide || busy}
            onClick={() =>
              onDecide({ approved: true, reason: "", action_taken: null })
            }
          >
            {/* Some flags propose nothing: the peer-comparison detectors raise
                insufficient_channels when they cannot judge at all. Offering to
                "do the proposed thing" there promises an action that does not
                exist. */}
            {row.proposed_action
              ? `Real, ${(actions.find((a) => a.value === row.proposed_action)?.label ?? row.proposed_action).toLowerCase()}`
              : "Real, nothing to do"}
          </Button>
          <Button disabled={!canDecide || busy} onClick={() => setOpen(true)}>
            Something else
          </Button>
        </div>
      ) : (
        <div className="mt-2 space-y-2 rounded border border-line-subtle bg-surface-sunken p-2">
          <label className="block">
            <span className="text-small font-medium text-ink">What should happen</span>
            <select
              className={inputClass}
              value={action}
              onChange={(e) => setAction(e.target.value)}
            >
              {actions.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                  {a.value === row.proposed_action ? " (proposed)" : ""}
                </option>
              ))}
            </select>
            {chosen && (
              <span className="mt-0.5 block text-small text-ink-muted">
                {chosen.description}
              </span>
            )}
          </label>

          <label className="block">
            <span className="text-small font-medium text-ink">
              Why{needsReason ? "" : " (optional)"}
            </span>
            <input
              className={inputClass}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="what you saw, and why this is the right thing to do about it"
            />
          </label>

          <div className="flex flex-wrap gap-1">
            <Button
              variant="primary"
              disabled={!canSubmit}
              onClick={() =>
                onDecide({ approved: true, reason, action_taken: action })
              }
            >
              The flag is real
            </Button>
            <Button
              variant="danger"
              disabled={!canDecide || busy || !reason.trim()}
              onClick={() =>
                onDecide({ approved: false, reason, action_taken: null })
              }
            >
              Detection was wrong
            </Button>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
          </div>
          {needsReason && !reason.trim() && (
            <p className="text-small text-ink-muted">
              Changing the action needs a reason: the record cannot otherwise tell a
              considered override from a slip.
            </p>
          )}
        </div>
      )}
    </li>
  );
}
