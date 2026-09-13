// Starting a run, as four decisions rather than thirty fields.
//
// The old screen put a recipe list, a subject list, a claim box and every
// parameter a recipe has on one page, labelled with the field names from the
// Python. That is usable if you already know what psd_by_condition is and which
// two of its twelve parameters matter. It is not usable on a first run, which is
// the case this is built for.
//
// The agent does the work at every step. It chooses the recipe from what you
// asked, explains each value it picked, re-checks the ones you change, and
// dry-runs the guardrails against what you are actually about to start. So the
// last screen before the button says what will happen, and a block is something
// you read beforehand rather than a red box afterwards.
//
// Nothing here decides anything the package does not already decide. Every
// label, every reason and every refusal comes from the server.

import { useCallback, useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { Proposal, ProposedParameter, Recipe, RunHandle, Subject } from "../api/types";
import { GuardrailList } from "../components/GuardrailList";
import { countByGroup } from "../components/schema";
import { SchemaForm } from "../components/SchemaForm";
import { Badge, Button, EmptyState, Panel, Skeleton } from "../components/ui";
import { inputClass, statusTone } from "../components/ui/tones";
import {
  blockingGuardrails,
  clearedFrom,
  paramsToSubmit,
  readiness,
  selectable,
  subjectKey,
} from "./runFlow";

const STEPS = ["Subject", "Question", "Settings", "Check"] as const;
type Step = 0 | 1 | 2 | 3 | 4; // 4 is "running"

// Offered rather than invented: each maps to a real recipe through the agent's
// own matching, so what they demonstrate is the matching, not a shortcut past it.
const EXAMPLES = [
  "Is beta higher during overt speech than during rest?",
  "What does the spectrum look like in each condition?",
  "How does power change over time around speech onset?",
  "How large is the ringing after each stimulation pulse?",
];

/** The agent's reasoning, keyed by parameter, for showing against each field. */
function byName(reasoning: ProposedParameter[]): Record<string, ProposedParameter> {
  return Object.fromEntries(reasoning.map((r) => [r.name, r]));
}

function StepBar({ step, onGo }: { step: Step; onGo: (s: Step) => void }) {
  return (
    <ol className="mb-3 flex flex-wrap items-center gap-1 text-small">
      {STEPS.map((label, i) => {
        const state = i === step ? "current" : i < step ? "done" : "todo";
        return (
          <li key={label} className="flex items-center gap-1">
            <button
              type="button"
              // Only backwards: a step you have not reached has nothing in it yet.
              disabled={i >= step}
              onClick={() => onGo(i as Step)}
              className={`rounded px-2 py-0.5 ${
                state === "current"
                  ? "bg-accent-soft font-medium text-accent"
                  : state === "done"
                    ? "text-ink-muted hover:bg-surface-sunken hover:text-ink"
                    : "text-ink-muted opacity-50"
              }`}
            >
              {i + 1}. {label}
            </button>
            {i < STEPS.length - 1 && <span aria-hidden="true" className="text-ink-muted">→</span>}
          </li>
        );
      })}
    </ol>
  );
}

export function Run() {
  const location = useLocation() as {
    state?: {
      params?: Record<string, unknown>;
      recipe?: string;
      question?: string;
      /** Sent by the Subjects screen: start on the question, not the list. */
      subjectKey?: string;
    };
  };
  const navigate = useNavigate();

  const [step, setStep] = useState<Step>(0);
  const [subjects, setSubjects] = useState<Subject[] | null>(null);
  const [recipes, setRecipes] = useState<Recipe[]>([]);
  const [subject, setSubject] = useState<Subject | null>(null);
  const [question, setQuestion] = useState(location.state?.question ?? "");
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [values, setValues] = useState<Record<string, unknown>>(location.state?.params ?? {});
  // Fields emptied on purpose. Tracked separately from `values`, because
  // "never set" and "set, then removed" have to reach the agent as different
  // things: it infers for the first and must not for the second.
  const [cleared, setCleared] = useState<string[]>([]);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [claim, setClaim] = useState("");
  const [overrides, setOverrides] = useState<Record<string, string>>({});
  const [handle, setHandle] = useState<RunHandle | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  useEffect(() => {
    api.subjects()
      .then((all) => {
        setSubjects(all);
        // Arriving from a subject card: that choice is already made, so skip
        // the step that asks for it. Only when it is approved, since the step
        // exists to stop an unreviewed subject reaching a run.
        const wanted = location.state?.subjectKey;
        const found = all.find((s) => `${s.study_id}/${s.session}` === wanted);
        if (found && found.qc_status === "approved") {
          setSubject(found);
          setStep(1);
        }
      })
      .catch(() => setSubjects([]));
    api.recipes().then(setRecipes).catch(() => setRecipes([]));
    // Read once, on mount: this is an entry condition, not a subscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const recipe = recipes.find((r) => r.name === proposal?.recipe);

  /** Choose a recipe from the question and move on. Declared once because there
   *  are three ways to ask for it: the button, the Enter key, and clicking one
   *  of the examples. A student pressing Enter and having nothing happen has
   *  learned that the box does not work, not that there is a button below it. */
  const workOut = async (text?: string) => {
    const asked = (text ?? question).trim();
    if (!asked || busy) return;
    const next = await ask({ recipe: null, params: {}, question: asked });
    if (next) { setValues(next.params); setStep(2); }
  };

  /** Ask the agent. Used to choose a recipe, and again whenever a value changes. */
  const ask = useCallback(
    async (opts: {
      recipe?: string | null;
      params?: Record<string, unknown>;
      cleared?: string[];
      // An example button sets the question and asks in the same click. React
      // state has not updated by then, so the text has to travel with the call
      // rather than be read back from state.
      question?: string;
    }) => {
      if (!subject) return null;
      setBusy(true);
      setError(null);
      try {
        const next = await api.propose({
          question: opts.question ?? question,
          study_id: subject.study_id,
          session: subject.session,
          recipe: opts.recipe === undefined ? (proposal?.recipe ?? null) : opts.recipe,
          params: opts.params ?? {},
          cleared: opts.cleared ?? [],
        });
        setProposal(next);
        return next;
      } catch (e) {
        setError((e as Error).message);
        return null;
      } finally {
        setBusy(false);
      }
    },
    [question, subject, proposal?.recipe],
  );

  // Re-check with the agent as values change, so the guardrails and the
  // validation on the Check step describe the run as it now stands. Debounced,
  // because this runs while somebody is still typing a number.
  useEffect(() => {
    if (step < 2 || !subject || !proposal) return;
    const id = window.setTimeout(() => { void ask({ params: values, cleared }); }, 400);
    return () => window.clearTimeout(id);
    // `ask` and `proposal` are deliberately not dependencies: including them
    // would re-fire on the answer this very effect caused.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [values, cleared, step, subject]);

  // Poll while a run is in flight, and stop as soon as it settles.
  useEffect(() => {
    if (!handle || ["ok", "failed", "blocked"].includes(handle.status)) return;
    timer.current = window.setInterval(async () => {
      const next = await api.runStatus(handle.handle);
      setHandle(next);
      if (next.status === "ok" && next.run_id) navigate(`/runs/${next.run_id}`);
    }, 1000);
    return () => { if (timer.current) window.clearInterval(timer.current); };
  }, [handle, navigate]);

  const start = async () => {
    if (!subject || !proposal) return;
    setError(null);
    try {
      setHandle(await api.createRun({
        recipe: proposal.recipe,
        study_id: subject.study_id,
        session: subject.session,
        claim,
        params: paramsToSubmit(proposal),
        overrides,
      }));
      setStep(4);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  // ---- step 1: which recording ------------------------------------------------

  if (step === 0) {
    return (
      <>
        <StepBar step={step} onGo={setStep} />
        <Panel title="Which recording?" hint="Only reviewed subjects can be analyzed.">
          {!subjects ? (
            <Skeleton rows={3} />
          ) : subjects.length === 0 ? (
            <EmptyState>
              No subjects in the manifest. Build a demo one with
              `python -m dbsspeech seed`.
            </EmptyState>
          ) : (
            <ul className="space-y-1">
              {subjects.map((s) => {
                const approved = selectable(s);
                return (
                  <li key={subjectKey(s)}>
                    <button
                      type="button"
                      disabled={!approved}
                      onClick={() => { setSubject(s); setStep(1); }}
                      className={`w-full rounded border px-3 py-2 text-left ${
                        approved
                          ? "border-line hover:bg-surface-sunken"
                          : "border-line-subtle opacity-70"
                      }`}
                    >
                      <span className="flex flex-wrap items-center gap-2">
                        <span className="font-medium">{subjectKey(s)}</span>
                        <Badge tone={statusTone(s.qc_status)}>{s.qc_status}</Badge>
                        <span className="text-small text-ink-muted">
                          {s.n_channels_included} channels ·{" "}
                          {s.leads.map((l) => l.target).join(", ")} ·{" "}
                          {s.conditions.map((c) => c.condition).join(", ")}
                        </span>
                      </span>
                      {!approved && (
                        <span className="mt-1 block text-small text-warn-ink">
                          QC review is not signed, so the gate refuses every run on this
                          subject. Open its QC page to review and sign.
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>
      </>
    );
  }

  // ---- step 2: what do you want to find out -----------------------------------

  if (step === 1) {
    return (
      <>
        <StepBar step={step} onGo={setStep} />
        <Panel
          title="What do you want to find out?"
          hint="Ordinary words. This picks the analysis and explains what it picked."
        >
          <textarea
            className={`${inputClass} h-20`}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                void workOut();
              }
            }}
            placeholder="for example: is beta higher during overt speech than during rest?"
          />
          <div className="mt-2 flex flex-wrap gap-1">
            {EXAMPLES.map((example) => (
              <Button
                key={example}
                disabled={busy}
                onClick={() => { setQuestion(example); void workOut(example); }}
              >
                {example}
              </Button>
            ))}
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Button
              variant="primary"
              disabled={busy || !question.trim()}
              onClick={() => { void workOut(); }}
            >
              {busy ? "Thinking…" : "Work out what to run"}
            </Button>
            <span className="text-small text-ink-muted">
              Runs on this machine. No model call, and nothing about a recording leaves it.
            </span>
          </div>
          {error && <p className="mt-2 text-body text-danger">{error}</p>}
        </Panel>
      </>
    );
  }

  // ---- step 3: the few settings that matter ------------------------------------

  if (step === 2 && proposal && recipe) {
    const counts = countByGroup(recipe);
    const reasons = byName(proposal.reasoning);
    return (
      <>
        <StepBar step={step} onGo={setStep} />
        <div className="space-y-3">
          <Panel title="This is what it will run" hint={proposal.asks}>
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="ok">{proposal.recipe}</Badge>
              {typeof proposal.understood.recipe_reason === "string" && (
                <span className="text-small text-ink-muted">
                  {proposal.understood.recipe_reason}
                </span>
              )}
            </div>
            {proposal.produces && (
              <p className="mt-2 text-small text-ink-muted">
                You will get: {proposal.produces}
              </p>
            )}
            <label className="mt-3 block">
              <span className="text-small font-medium text-ink">
                Not what you meant? Pick the analysis yourself
              </span>
              <select
                className={inputClass}
                value={proposal.recipe}
                onChange={async (e) => {
                  const next = await ask({ recipe: e.target.value, params: {} });
                  if (next) setValues(next.params);
                }}
              >
                {recipes.map((r) => (
                  <option key={r.name} value={r.name}>
                    {r.question ?? r.description}
                  </option>
                ))}
              </select>
            </label>
          </Panel>

          {proposal.questions.length > 0 && (
            <Panel title="It could not work these out">
              <ul className="space-y-1">
                {proposal.questions.map((q) => (
                  <li key={q} className="text-body text-warn-ink">{q}</li>
                ))}
              </ul>
            </Panel>
          )}

          <Panel
            title="Settings"
            hint={
              counts.advanced > 0
                ? `The ${counts.essential} that decide the answer. The other ${counts.advanced} have defaults.`
                : "This recipe has not marked any of its parameters as advanced, so all are shown."
            }
          >
            <SchemaForm
              recipe={recipe}
              values={values}
              onChange={(next) => {
                // A key present but undefined is a field somebody emptied. It
                // stays empty: the recipe's own default applies, and nothing
                // fills it back in.
                setCleared(clearedFrom(next));
                setValues(next);
              }}
              group={showAdvanced ? "all" : "essential"}
              reasons={reasons}
            />
            {counts.advanced > 0 && (
              <Button
                className="mt-3"
                onClick={() => setShowAdvanced((v) => !v)}
              >
                {showAdvanced
                  ? "Hide the advanced settings"
                  : `Show the other ${counts.advanced} settings`}
              </Button>
            )}
          </Panel>

          <div className="flex items-center gap-2">
            <Button variant="primary" onClick={() => setStep(3)}>
              Check it over
            </Button>
            {busy && <span className="text-small text-ink-muted">Re-checking…</span>}
          </div>
        </div>
      </>
    );
  }

  // ---- step 4: what will happen ------------------------------------------------

  if (step === 3 && proposal && recipe) {
    const blocking = blockingGuardrails(proposal, overrides);
    const { ready, blockers } = readiness(proposal, claim, overrides);

    return (
      <>
        <StepBar step={step} onGo={setStep} />
        <div className="space-y-3">
          <Panel title="What is about to happen">
            <p className="text-body">
              <b>{proposal.recipe}</b> on <b>{subject && subjectKey(subject)}</b>.{" "}
              {proposal.produces}
            </p>
            {proposal.caveats.length > 0 && (
              <ul className="mt-2 space-y-1">
                {proposal.caveats.map((c) => (
                  <li key={c} className="text-small text-warn-ink">{c}</li>
                ))}
              </ul>
            )}
          </Panel>

          <Panel
            title="Method checks"
            hint="Run before anything is computed, against the settings above."
          >
            {proposal.guardrails.length === 0 ? (
              <p className="text-body text-ink-muted">
                Nothing fired. The analysis answers the question it claims to.
              </p>
            ) : (
              <GuardrailList hits={proposal.guardrails} />
            )}
            {blocking.map((g) => (
              <label key={g.guardrail} className="mt-3 block">
                <span className="text-small font-medium text-ink">
                  To run anyway, say why {g.guardrail} does not apply here
                </span>
                <input
                  className={inputClass}
                  value={overrides[g.guardrail] ?? ""}
                  placeholder="this reason is written into the run record"
                  onChange={(e) =>
                    setOverrides((o) => ({ ...o, [g.guardrail]: e.target.value }))
                  }
                />
              </label>
            ))}
          </Panel>

          <Panel
            title="What is this meant to show?"
            hint="One sentence. It goes into the run record, and it is what makes the result citable."
          >
            <input
              className={inputClass}
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              placeholder="for example: beta is higher in overt speech than rest in the STN"
            />
          </Panel>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="primary" disabled={!ready} onClick={start}>
              Run it
            </Button>
          </div>
          {/* Every reason it cannot start, rather than a dead button. */}
          {blockers.map((b) => (
            <p key={b} className="text-small text-ink-muted">{b}</p>
          ))}
          {error && <p className="text-body text-danger">{error}</p>}
        </div>
      </>
    );
  }

  // ---- running -----------------------------------------------------------------

  return (
    <>
      <StepBar step={3} onGo={setStep} />
      <Panel title="Running">
        {handle ? (
          <>
            <Badge tone={statusTone(handle.status)}>{handle.status}</Badge>
            {handle.status === "queued" && (
              <p className="mt-2 text-small text-ink-muted">
                Waiting for a worker. If this does not move, check the Status screen:
                a run needs a worker process, and without one it waits.
              </p>
            )}
            {handle.status === "blocked" && handle.findings && (
              <div className="mt-2"><GuardrailList hits={handle.findings} /></div>
            )}
            {handle.status === "failed" && (
              <pre className="mt-2 overflow-x-auto rounded bg-surface-sunken p-2 text-small">
                {handle.error}
              </pre>
            )}
          </>
        ) : (
          <EmptyState action={<Button onClick={() => setStep(0)}>Start again</Button>}>
            Nothing running.
          </EmptyState>
        )}
      </Panel>
    </>
  );
}
