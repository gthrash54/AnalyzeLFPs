import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Proposal, Subject } from "../api/types";
import { GuardrailList } from "../components/GuardrailList";
import { Badge, Button, EmptyState, Panel } from "../components/ui";

/** A subject and session identify one recording, and both are needed to ask. */
const keyOf = (s: Subject) => `${s.study_id}/${s.session}`;

/** Describe an analysis in words; see what it would do before it does it. */
export function Ask() {
  // Paradigm-neutral, because the conditions a question can name come from the
  // selected subject's manifest rather than from anything this app assumes.
  const [question, setQuestion] = useState("beta power by condition");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  const [selected, setSelected] = useState<string>("");
  const navigate = useNavigate();

  useEffect(() => {
    api
      .subjects()
      .then((rows) => {
        setSubjects(rows);
        // Select the first rather than a hardcoded subject: which recordings
        // exist is a property of the manifest, not of this build.
        if (rows.length > 0) setSelected(keyOf(rows[0]));
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  const current = subjects?.find((s) => keyOf(s) === selected) ?? null;

  const ask = async () => {
    if (!current) return;
    setBusy(true);
    setError(null);
    try {
      // The subject is chosen above rather than hard-coded, which was the
      // reason this screen briefly had no subject at all. `recipe: null` lets
      // the agent choose the analysis, which is what this screen is for.
      setProposal(await api.propose({
        question,
        study_id: current.study_id,
        session: current.session,
        recipe: null,
      }));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <Panel title="Ask" hint="Runs locally. Nothing about a recording leaves this machine.">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <label className="text-micro font-medium text-ink-muted" htmlFor="ask-subject">
            Subject
          </label>
          <select
            id="ask-subject"
            className="rounded border border-line px-2 py-1.5 text-body disabled:opacity-50"
            value={selected}
            onChange={(e) => {
              setSelected(e.target.value);
              // The old proposal was about a different recording, so keeping it
              // on screen beside a new subject would misattribute it.
              setProposal(null);
            }}
            disabled={!subjects || subjects.length === 0}
          >
            {subjects?.map((s) => (
              <option key={keyOf(s)} value={keyOf(s)}>
                {s.study_id} · {s.session}
              </option>
            ))}
          </select>
          {/* The gate refuses a run on unreviewed data, so say so before the
              question is asked rather than after. This reflects the gate; it
              never decides anything. */}
          {current && (
            <Badge tone={current.qc_status === "approved" ? "ok" : "warn"}>
              {current.qc_status}
            </Badge>
          )}
        </div>
        <div className="flex gap-2">
          <input
            className="flex-1 rounded border border-line px-2 py-1.5 text-body"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && ask()}
            placeholder="what do you want to look at?"
          />
          <Button
            variant="primary"
            onClick={ask}
            disabled={busy || !question.trim() || !current}
          >
            {busy ? "Thinking…" : "Ask"}
          </Button>
        </div>
        {subjects && subjects.length === 0 && (
          <p className="mt-2 text-small text-ink-muted">
            No subjects in the manifest yet. Add rows to <code>manifest/subjects.csv</code>,
            or derive them with <code>dbsspeech draft-manifest</code>.
          </p>
        )}
        {current && current.conditions.length > 0 && (
          <p className="mt-2 text-micro text-ink-muted">
            Conditions available: {current.conditions.map((c) => c.condition).join(", ")}
          </p>
        )}
        {error && <p className="mt-2 text-body text-danger">{error}</p>}
      </Panel>

      {!proposal && <Panel title="Proposal"><EmptyState>Ask something to see what it would run.</EmptyState></Panel>}

      {proposal && (
        <>
          <Panel title="Proposal" hint={proposal.recipe}>
            <div className="mb-3 flex items-center gap-2">
              {proposal.blocked
                ? <Badge tone="danger">blocked as proposed</Badge>
                : <Badge tone="ok">would run</Badge>}
            </div>
            <ul className="space-y-2">
              {proposal.reasoning.map((r) => (
                <li key={r.name} className="text-body">
                  <code className="text-ink">{r.name} = {JSON.stringify(r.value)}</code>
                  <p className="text-ink-muted">{r.reason}</p>
                </li>
              ))}
            </ul>
            {proposal.reasoning.length === 0 && <EmptyState>Nothing inferred; defaults apply.</EmptyState>}
            <Button
              className="mt-3"
              disabled={proposal.blocked}
              onClick={() =>
                navigate("/run", {
                  state: {
                    params: proposal.params,
                    recipe: proposal.recipe,
                    // Carried so the Run screen can re-ask against the subject
                    // you pick there, rather than starting from a blank box.
                    question,
                  },
                })
              }
            >
              Take these parameters to Run
            </Button>
          </Panel>

          <Panel title="Guardrails" hint="Evaluated against these parameters, before anything runs">
            <GuardrailList hits={proposal.guardrails} />
          </Panel>

          {proposal.caveats.length > 0 && (
            <Panel title="Caveats">
              <ul className="list-disc space-y-1 pl-5 text-body text-ink">
                {proposal.caveats.map((c) => <li key={c}>{c}</li>)}
              </ul>
            </Panel>
          )}

          {proposal.questions.length > 0 && (
            <Panel title="It could not determine" hint="Answer these rather than accepting a default">
              <ul className="list-disc space-y-1 pl-5 text-body text-ink">
                {proposal.questions.map((q) => <li key={q}>{q}</li>)}
              </ul>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
