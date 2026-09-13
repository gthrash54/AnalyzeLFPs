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
  ok: "bg-ok-soft text-ok-ink ring-ok/30",
  warn: "bg-warn-soft text-warn-ink ring-warn/30",
  danger: "bg-danger-soft text-danger-ink ring-danger/30",
  muted: "bg-surface-sunken text-ink-muted ring-line",
};

/** One word of status, in a status color. Never color alone: it always has a word. */
export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-block rounded px-1.5 py-0.5 text-micro font-medium ring-1 ${TONES[tone]}`}
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
    <header className="mb-3 flex items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="truncate text-display font-semibold text-ink">{title}</h1>
        {subtitle && <p className="mt-0.5 text-small text-ink-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
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
    <section className="rounded border border-line bg-surface">
      {title && (
        <header className="flex items-start justify-between gap-3 border-b border-line-subtle px-3 py-2">
          <div className="min-w-0">
            <h2 className="text-heading font-semibold text-ink">{title}</h2>
            {hint && <p className="mt-0.5 text-small text-ink-muted">{hint}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
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
    <div className="py-6 text-center">
      <p className="text-body text-ink-muted">{children}</p>
      {action && <div className="mt-2 flex justify-center">{action}</div>}
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
          className="h-4 animate-pulse rounded bg-surface-sunken ring-1 ring-line-subtle"
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

const VARIANTS = {
  primary: "bg-accent text-white hover:bg-accent-hover disabled:bg-ink-muted",
  secondary: "bg-surface text-ink ring-1 ring-line hover:bg-surface-sunken",
  danger: "bg-danger text-white hover:bg-danger/90",
} as const;

/** One size. A second size is a layout that has not been decided. */
export function Button({ variant = "secondary", className = "", ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={`rounded px-2 py-1 text-small font-medium transition-colors
        disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${className}`}
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
      {help && <span className="mt-0.5 block text-small text-ink-muted">{help}</span>}
      {caveat && <span className="mt-0.5 block text-small text-warn-ink">Caveat: {caveat}</span>}
      {error && <span className="mt-0.5 block text-small text-danger">{error}</span>}
    </label>
  );
}


/** An identifier or a measured number: monospace, and copyable without ambiguity. */
export function Mono({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <span className={`font-mono text-micro tabular ${className}`}>{children}</span>;
}
