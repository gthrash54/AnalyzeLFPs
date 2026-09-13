// The fixed mapping from a status word to a color, so a tone always means the
// same thing on every screen. See the badge conventions in web/DESIGN.md.
//
// Its own file rather than sitting beside the components, because a module that
// exports both components and plain functions loses fast refresh in development.

export type Tone = "ok" | "warn" | "danger" | "muted";

export function statusTone(status: string): Tone {
  if (status === "approved" || status === "ok") return "ok";
  if (status === "blocked" || status === "failed") return "danger";
  if (["in_review", "reopened", "queued", "running"].includes(status)) return "warn";
  return "muted";
}

export function severityTone(severity: string): Tone {
  if (severity === "block") return "danger";
  if (severity === "warn") return "warn";
  return "muted";
}

/** The one input style, so every field on every screen is the same height. */
export const inputClass =
  "mt-0.5 w-full rounded border border-line bg-surface px-2 py-1 text-body " +
  "focus:border-accent focus:outline-none";
