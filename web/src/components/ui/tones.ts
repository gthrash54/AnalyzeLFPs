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

/** The one input style, so every field on every screen is the same height.
 *
 *  The focus ring is the global one from index.css rather than a border color
 *  change: a 1px border going teal is easy to miss, and it was the only place
 *  in the app where focus looked different from everywhere else. */
const INPUT_BASE =
  "rounded-control border border-line bg-surface px-2 py-1 text-body text-ink " +
  "transition-colors hover:border-ink-muted disabled:cursor-not-allowed " +
  "disabled:bg-surface-sunken disabled:text-ink-muted";

/** A field on its own line, under its label. */
export const inputClass = `mt-1 block w-full ${INPUT_BASE}`;

/** The same control sitting in a row beside others, where full width would push
 *  everything after it onto its own line. Two exports rather than one plus an
 *  override, because Tailwind decides a w-full against w-auto collision by
 *  stylesheet order and not by the order they are written in. */
export const inlineInputClass = INPUT_BASE;

/** A link that does a button's job, in the primary style. Two screens hand a
 *  person on to the next step with an <a> rather than a <button>, because the
 *  step is a different page; they should still look like the Button they sit
 *  beside. */
export const linkButtonClass =
  "inline-flex items-center justify-center rounded-control bg-accent px-2.5 py-1 " +
  "text-small font-medium whitespace-nowrap text-white transition-colors " +
  "hover:bg-accent-hover active:bg-accent-ink";

/** A link inside running text. Underlined, because color alone is not a link. */
export const textLinkClass =
  "text-accent underline underline-offset-2 transition-colors hover:text-accent-ink";
