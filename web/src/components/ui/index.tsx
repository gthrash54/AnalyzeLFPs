// The shared components. A page composes these and does not write its own
// padding, border, or color classes; a page needing a one-off class means one of
// these is missing something. See web/DESIGN.md.

import type { ButtonHTMLAttributes, ReactNode } from "react";

import type { Tone } from "./tones";

export { DataTable } from "./DataTable";
export type { Column } from "./DataTable";

// ---------------------------------------------------------------------------
// Status
// ---------------------------------------------------------------------------

const TONES: Record<Tone, string> = {
  ok: "bg-ok-soft text-ok-ink ring-ok-line",
  warn: "bg-warn-soft text-warn-ink ring-warn-line",
  danger: "bg-danger-soft text-danger-ink ring-danger-line",
  muted: "bg-surface-sunken text-ink-muted ring-line",
};

/** One word of status, in a status color. Never color alone: it always has a word. */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-control px-1.5 py-0.5 text-micro font-medium
        tracking-wide whitespace-nowrap ring-1 ring-inset ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Structure
// ---------------------------------------------------------------------------

/** The title of a screen. Once per screen, with anything actionable on the right. */
export function PageHeader({ title, subtitle, actions }: {
  title: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className="mb-4 flex flex-wrap items-end justify-between gap-x-3 gap-y-2">
      <div className="min-w-0">
        <h1 className="truncate text-display font-semibold tracking-tight text-ink">{title}</h1>
        {subtitle && (
          <p className="mt-0.5 truncate font-mono text-small text-ink-muted">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

/** A titled region. The hint is for the sentence that stops a wrong assumption. */
export function Panel({ title, children, hint, actions }: {
  title?: string;
  children: ReactNode;
  hint?: string;
  actions?: ReactNode;
}) {
  return (
    <section className="rounded-card border border-line bg-surface">
      {/* A panel with a hint and no title used to drop the hint on the floor. */}
      {(title || hint || actions) && (
        <header
          className="flex flex-wrap items-start justify-between gap-x-3 gap-y-1
            rounded-t-card border-b border-line-subtle bg-surface-sunken px-3 py-2"
        >
          <div className="min-w-0">
            {title && <h2 className="truncate text-heading font-semibold text-ink">{title}</h2>}
            {hint && <p className="max-w-prose text-small text-ink-muted">{hint}</p>}
          </div>
          {actions && <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-3">{children}</div>
    </section>
  );
}

/** Nothing to show, and what to do about it. An empty screen with no next step
    is a dead end, so the action is part of the component rather than optional
    decoration. */
export function EmptyState({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div className="rounded-card border border-dashed border-line px-4 py-8 text-center">
      <p className="mx-auto max-w-prose text-body text-ink-muted">{children}</p>
      {action && <div className="mt-3 flex justify-center">{action}</div>}
    </div>
  );
}

/** The shape of content that has not arrived. Sized by the caller, because a
    skeleton the wrong shape is worse than none: the page jumps when it loads. */
export function Skeleton({ rows = 3, className = "" }: { rows?: number; className?: string }) {
  return (
    <div className={`space-y-2 ${className}`} aria-busy="true" aria-live="polite">
      <span className="sr-only">Loading</span>
      {Array.from({ length: rows }, (_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded-control bg-surface-sunken ring-1 ring-line-subtle"
          // Uneven widths, so it reads as text rather than as a progress bar.
          style={{ width: `${100 - (i % 3) * 12}%` }}
        />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Controls
// ---------------------------------------------------------------------------

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "danger";
};

// Three states rather than two: a button that only changes on hover gives no
// feedback on a trackpad press, and a run is not something to click twice.
const VARIANTS = {
  primary: "bg-accent text-white hover:bg-accent-hover active:bg-accent-ink disabled:hover:bg-accent",
  secondary:
    "bg-surface text-ink ring-1 ring-inset ring-line hover:bg-surface-hover " +
    "active:bg-surface-sunken disabled:hover:bg-surface",
  danger: "bg-danger text-white hover:bg-danger-ink active:bg-danger-ink disabled:hover:bg-danger",
} as const;

/** One size. A second size is a layout that has not been decided. */
export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={`inline-flex items-center justify-center gap-1.5 rounded-control px-2.5 py-1
        text-small font-medium whitespace-nowrap transition-colors
        disabled:cursor-not-allowed disabled:opacity-55
        ${VARIANTS[variant]} ${className}`}
    />
  );
}

/** A labelled input. The caveat is the part a first-year would not know to ask
    about, so it is shown rather than hidden behind a tooltip. */
export function Field({ label, help, caveat, error, children }: {
  label: string;
  help?: string;
  caveat?: string;
  error?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="text-small font-medium text-ink">{label}</span>
      {children}
      {help && <span className="mt-1 block text-small text-ink-muted">{help}</span>}
      {caveat && (
        <span className="mt-1 block border-l-2 border-warn-line pl-2 text-small text-warn-ink">
          Caveat: {caveat}
        </span>
      )}
      {error && <span className="mt-1 block text-small text-danger">{error}</span>}
    </label>
  );
}


/** An identifier or a measured number: monospace, and copyable without ambiguity. */
export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono text-micro tabular ${className}`}>{children}</span>;
}
