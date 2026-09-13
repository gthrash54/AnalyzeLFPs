// The rules of the run flow, with no React in them.
//
// These were conditionals buried in JSX, which is a poor place for them: they
// are the rules that decide whether somebody may start an analysis, and they
// should be readable in a diff without reading a component. They are also the
// rules most worth testing the moment this project has a front-end test runner,
// which it does not yet (see docs/backlog.md).

import type { Proposal, Subject } from "../api/types";

export type Values = Record<string, unknown>;

/** The manifest key for a subject: what every screen calls it. */
export function subjectKey(s: Subject): string {
  return `${s.study_id}/${s.session}`;
}

/** Only a signed subject may be analyzed. The gate refuses the rest anyway;
 *  this is so somebody learns that here rather than from a failed run. */
export function selectable(s: Subject): boolean {
  return s.qc_status === "approved";
}

/** Fields present but empty: somebody removed a value that was there.
 *
 *  Distinct from a field that was never set. The agent infers for the second and
 *  must not for the first, so the two cannot be collapsed into one absence. */
export function clearedFrom(values: Values): string[] {
  return Object.entries(values)
    .filter(([, v]) => v === undefined)
    .map(([k]) => k);
}

/** Guardrails that stop a run, and whether each has been given a reason. */
export function blockingGuardrails(
  proposal: Proposal,
  overrides: Record<string, string>,
): { guardrail: string; message: string; excused: boolean }[] {
  return proposal.guardrails
    .filter((g) => g.severity === "block")
    .map((g) => ({
      guardrail: g.guardrail,
      message: g.message,
      excused: Boolean(overrides[g.guardrail]?.trim()),
    }));
}

export interface Readiness {
  ready: boolean;
  /** Why not, in the order somebody should deal with them. Empty when ready. */
  blockers: string[];
}

/** Whether the run may start, and what is stopping it.
 *
 *  Every reason is stated rather than the button simply being dead. A disabled
 *  control with no explanation is the thing people file bugs about, and here the
 *  explanations are the interesting part: a claim is required because a result
 *  whose purpose was never stated cannot be reviewed, and a blocking guardrail
 *  needs a reason because the reason is what goes into the record.
 */
export function readiness(
  proposal: Proposal | null,
  claim: string,
  overrides: Record<string, string>,
): Readiness {
  const blockers: string[] = [];
  if (!proposal) {
    return { ready: false, blockers: ["Nothing has been proposed yet."] };
  }
  if (!claim.trim()) {
    blockers.push("A claim is required: one sentence saying what this is meant to show.");
  }
  const unexcused = blockingGuardrails(proposal, overrides).filter((g) => !g.excused);
  for (const g of unexcused) {
    blockers.push(`${g.guardrail} blocks this run until you say why it does not apply.`);
  }
  // The agent validates against the recipe's own parameter model, so this is the
  // recipe refusing, not the interface guessing.
  for (const question of proposal.questions) {
    if (question.includes("refused")) blockers.push(question);
  }
  return { ready: blockers.length === 0, blockers };
}

/** Parameters to submit: what the agent settled on, minus anything unset.
 *
 *  Taken from the proposal rather than the form, because the proposal is what
 *  the guardrails were just checked against. Submitting anything else would mean
 *  the dry run described a different analysis from the one that ran.
 */
export function paramsToSubmit(proposal: Proposal): Values {
  return Object.fromEntries(
    Object.entries(proposal.params).filter(([, v]) => v !== undefined),
  );
}
