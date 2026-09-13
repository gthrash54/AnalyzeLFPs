// A collapsible explanation for whichever screen you are on.
//
// One file rather than a paragraph inside each page, because the value is in
// these texts saying the same things in the same words as docs/concepts.md. A
// new lab member reads the screen, not the documentation, so the screen has to
// carry the two or three sentences that stop a wrong assumption forming.
//
// Closed by default. Help that must be dismissed every visit stops being read.

import { useLocation } from "react-router-dom";

interface Topic {
  title: string;
  body: string[];
}

const TOPICS: { match: (path: string) => boolean; topic: Topic }[] = [
  {
    match: (p) => p === "/",
    topic: {
      title: "What this screen does",
      body: [
        "Describe an analysis in ordinary words and this proposes a recipe and its parameters, explains each choice, and shows the guardrails that would fire before anything runs.",
        "It is deterministic and local. There is no model call, and nothing about a recording leaves this machine.",
        "It proposes; it never runs. You review the parameters and start the run yourself.",
      ],
    },
  },
  {
    match: (p) => p.startsWith("/subjects"),
    topic: {
      title: "What a subject is here",
      body: [
        "One recording session, described by the manifest rather than by the files on disk: its leads and their targets, which contacts are included, and the condition windows.",
        "A subject cannot be analyzed until QC review is signed. The QC status shown here is the real gate, not a label.",
        "A condition marked under revision still runs, and every result that uses it is flagged.",
      ],
    },
  },
  {
    match: (p) => p.startsWith("/qc/"),
    topic: {
      title: "Reviewing quality control",
      body: [
        "Detection proposes flags with the evidence it used. You decide each one; nothing is removed until you approve it, and signing is refused while any flag is undecided.",
        "Approving a flag is not the same as accepting its proposed action. Change the action when the proposal is wrong, and say why: a stimulation artifact is real without meaning the contact should be dropped.",
        "Nothing here deletes samples. An artifact becomes an annotation, and the decisions travel with every result computed afterwards.",
      ],
    },
  },
  {
    match: (p) => p === "/run",
    topic: {
      title: "Starting a run",
      body: [
        "Every run states a claim: one sentence about what it is meant to show. It goes into the run record, and six months later it is the difference between a result and a file.",
        "Guardrails are evaluated before anything is computed. A blocked run produces no output at all, and an override is recorded with the reason you give.",
        "Runs execute in a worker process, so closing this page does not stop one. The Status screen shows whether a worker is running.",
      ],
    },
  },
  {
    match: (p) => /^\/runs\/.+/.test(p),
    topic: {
      title: "Reading a result",
      body: [
        "The run record is the result: the claim, who ran it, the code it ran, every parameter, what QC removed, and every guardrail that fired.",
        "Cite a result by its run id. A figure pasted into a slide loses all of this; an export bundle keeps it.",
        "A run marked as coming from a dirty tree was computed by code that is in no commit, so it cannot be reproduced exactly.",
      ],
    },
  },
  {
    match: (p) => p.startsWith("/runs"),
    topic: {
      title: "The run log",
      body: [
        "Every analysis that has been performed, including the ones that failed or were blocked. Failures are kept on purpose: a provenance log that only lists successes is a sales brochure.",
        "Open one to see its parameters and outputs, or compare two to see what actually differs between them.",
      ],
    },
  },
  {
    match: (p) => p.startsWith("/compare"),
    topic: {
      title: "Comparing two runs",
      body: [
        "Which settings differed, side by side, so 'which parameters did you use' is a lookup rather than a conversation.",
        "It also says whether the two ran on the same code. Two results from different commits can differ for reasons no parameter shows.",
      ],
    },
  },
  {
    match: (p) => p.startsWith("/status"),
    topic: {
      title: "Is this thing working",
      body: [
        "Runs are executed by a worker process, separate from this web app. With no worker running, a submitted run waits in the queue and nothing appears to happen.",
        "This screen says whether one is running, when it last reported in, and what is queued. It also shows the library versions, which is what a run record pins.",
      ],
    },
  },
];

export function Help() {
  const { pathname } = useLocation();
  const found = TOPICS.find((entry) => entry.match(pathname));
  if (!found) return null;

  return (
    <details className="mb-3 rounded border border-line-subtle bg-surface-sunken px-3 py-2">
      <summary className="cursor-pointer text-small font-medium text-ink-muted hover:text-ink">
        {found.topic.title}
      </summary>
      <div className="mt-2 space-y-1.5">
        {found.topic.body.map((line) => (
          <p key={line} className="text-small leading-relaxed text-ink-muted">
            {line}
          </p>
        ))}
      </div>
    </details>
  );
}
