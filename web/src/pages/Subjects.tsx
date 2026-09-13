import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Subject } from "../api/types";
import { Badge, Button, EmptyState, Panel, Skeleton } from "../components/ui";
import { statusTone } from "../components/ui/tones";

export function Subjects() {
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.subjects().then(setSubjects).catch((e: Error) => setError(e.message));
  }, []);

  if (error) return <Panel><p className="text-body text-danger">{error}</p></Panel>;
  if (!subjects) return <Panel><Skeleton rows={4} /></Panel>;
  if (subjects.length === 0) {
    return (
      <Panel>
        <EmptyState>
          No subjects in the manifest. Add rows to manifest/subjects.csv, or build a
          demo one with `python -m dbsspeech seed`.
        </EmptyState>
      </Panel>
    );
  }

  return (
    <div className="space-y-3">
      {subjects.map((s) => {
        const key = `${s.study_id}/${s.session}`;
        const approved = s.qc_status === "approved";
        return (
          <Panel
            key={key}
            title={`${s.study_id} · ${s.session}`}
            hint={`${s.format} · ${s.hemisphere} hemisphere · ${s.acquisition}`}
            actions={
              // What to do next, from here. An approved subject is ready to
              // analyze; an unreviewed one needs the review first, and saying so
              // on the card is cheaper than finding out from a refused run.
              approved ? (
                <Button
                  variant="primary"
                  onClick={() => navigate("/run", { state: { subjectKey: key } })}
                >
                  Analyze this subject
                </Button>
              ) : (
                <Link
                  className="rounded bg-accent px-2 py-1 text-small font-medium text-white"
                  to={`/qc/${s.study_id}`}
                >
                  Review its QC
                </Link>
              )
            }
          >
            <div className="mb-3 flex flex-wrap items-center gap-2">
              <Badge tone={statusTone(s.qc_status)}>{s.qc_status}</Badge>
              {!approved && (
                <span className="text-small text-ink-muted">
                  Until this is signed, the gate refuses every analysis on this subject.
                </span>
              )}
              <Link className="text-small text-accent underline" to={`/qc/${s.study_id}`}>
                QC page
              </Link>
            </div>

            <dl className="grid gap-3 sm:grid-cols-3">
              <div>
                <dt className="text-small font-medium text-ink-muted">Channels</dt>
                <dd className="text-body">
                  {s.n_channels_included} included of {s.n_channels}
                </dd>
              </div>
              <div>
                <dt className="text-small font-medium text-ink-muted">Leads</dt>
                <dd className="flex flex-wrap gap-1 text-body">
                  {s.leads.map((lead) => (
                    <span key={lead.lead_id} className="flex items-center gap-1">
                      <Badge tone="muted">{lead.target.toUpperCase()}</Badge>
                      {/* Rotation gates every anatomical direction claim, so it is
                          stated on the subject card rather than buried. */}
                      {!lead.rotation_known && <Badge tone="warn">rotation unknown</Badge>}
                    </span>
                  ))}
                </dd>
              </div>
              <div>
                <dt className="text-small font-medium text-ink-muted">Conditions</dt>
                {/* Duration and provenance in the open, not in a title attribute.
                    Where a window came from decides whether a result about onset
                    means anything, and a tooltip is invisible on a touch screen
                    and to a screen reader both. */}
                <dd className="space-y-0.5">
                  {s.conditions.map((c) => (
                    <div key={c.condition} className="flex flex-wrap items-baseline gap-1">
                      <Badge tone={c.status === "in_use" ? "ok" : "warn"}>
                        {c.condition}
                      </Badge>
                      <span className="text-small text-ink-muted">
                        {c.duration_s.toFixed(0)}s, from {c.derived_from}
                        {c.status !== "in_use" && `, ${c.status.replace(/_/g, " ")}`}
                      </span>
                    </div>
                  ))}
                </dd>
              </div>
            </dl>

            {s.conditions.some((c) => c.derived_from === "assumed") && (
              <p className="mt-3 text-small text-warn-ink">
                A window marked <b>assumed</b> was not measured from anything. Results
                that use it rest on a guess, and guardrail G10 says so on every one.
              </p>
            )}

            {s.leads.some((l) => l.lead_model.startsWith("unknown")) && (
              <p className="mt-3 text-small text-warn-ink">
                Lead model is a placeholder: geometry is confirmed electrically, the
                manufacturer is not. Contact labels stay provisional until the implant
                record is checked.
              </p>
            )}
          </Panel>
        );
      })}
    </div>
  );
}
