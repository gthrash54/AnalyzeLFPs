# The five ideas

Everything else in this software follows from these. Fifteen minutes, in plain
language, no code.

## 1. The manifest is the truth, not the files

A folder of recordings tells you almost nothing. Which contacts are on which
lead, which lead is in STN and which in GPi, which channel is a microphone,
where in the recording somebody was speaking: none of that is in the file, and
some of it cannot be recovered from the file at all.

So it lives in `manifest/`: five small text tables, one row per thing, curated by
a person. `subjects.csv` says what was recorded and in what format. `leads.csv`
says a subject has two leads, this model, this target. `channels.csv` maps each
channel to a contact, a region, and whether it is included. `streams.csv` exists
because one recording carries several streams at different sampling rates.
`windows.csv` says when each condition happened.

If it is not in the manifest, this software does not know it, and will say so
rather than guess. `docs/schema.md` has the ten rules the manifest has to obey,
and `dbsspeech validate` checks all of them at once rather than stopping at the
first.

## 2. Windows have provenance, because there are no task markers

These recordings have no event triggers. Nobody pressed a button when speech
started. Every condition window was decided afterwards, by looking at something:
a microphone envelope, an EMG channel, a note in the log, or somebody's memory.

`windows.csv` records which. A window derived from a microphone is a
measurement. A window marked `assumed` is a guess, and every result computed
from it is flagged as resting on a guess. That flag is guardrail G10, and it is
not a formality: the difference between a real onset and an assumed one is the
difference between a time-frequency result and a picture.

## 3. QC is a decision a person makes, and the gate enforces it

Detection is automatic. Judgment is not.

The detectors look for the things that make a channel unusable: flat channels,
line noise, amplitude excursions, contacts whose statistics sit far from their
peers. Each flag carries the evidence that produced it and a proposed action.

Then a person decides, one flag at a time, and signs. Until they sign, the gate
refuses every recipe on that subject, from every direction: the web app, the
command line, the API, a notebook. The gate lives in the package, not in the
interface, so there is no path around it.

Two things about the decisions are deliberate. **Approving a flag is not the same
as accepting its proposed action.** Detection can be right that a signal is
extreme and wrong about what to do: a stimulation artifact makes a contact look
terrible by every statistic, and excluding that contact would throw away the
signal the recording was made for. Change the action, give a reason, and both
are recorded. **Nothing deletes samples.** An artifact becomes an annotation. A
recording is evidence, and evidence is not edited.

## 4. A run record is the result

A figure is not a result. A figure is a picture of one.

Every analysis goes through one function, `registry.run`, which checks the gate,
evaluates the guardrails before anything is computed, and writes a record to
`runs/<run_id>.json`. That record has the claim you stated, who ran it, the
commit the code was at, every parameter, the hash of every input, the library
versions, what QC removed, and every guardrail that fired along with any
overrides and their reasons.

Cite a result by its run id. Six months later that is the difference between a
number you can defend and a PNG in a folder. An export bundle wraps the record,
the figures, the tables, and the config that was in force into one directory with
a README that reads without this software.

A run from a dirty working tree is marked as such, because code that is in no
commit cannot be reproduced.

## 5. Guardrails check whether the analysis answers the question

QC asks whether the signal is usable. Guardrails ask something different: whether
the analysis about to run answers the question it claims to.

There are thirteen, listed in `docs/guardrails.md`, and each came from a trap
somebody has actually fallen into. A monopolar montage on a shared reference
turns common mode into signal. A ratio taken after averaging is not the average
of the ratios. A dB number without a z beside it lets dynamic range read as
effect size. A band above the anti-alias cutoff is not in the data at all.

They run before anything is computed, so a blocked run produces no output to
mistake for a result. Most can be overridden, and an override requires a reason
that is written into the record. Three cannot be overridden, because they are
arithmetic rather than judgment.

Severity is configuration, in `configs/guardrails.yaml`, so a lab can downgrade
one deliberately. Deleting one is refused: a guardrail removed from the config
would silently stop running.

---

## Where things live

| | |
|---|---|
| `data/` | the recordings. Read-only, never written to. |
| `manifest/` | the data contract, curated by hand. |
| `configs/` | bands, thresholds, statistics options, ERNA settings. Editable in the app, with history. |
| `derivatives/` | results, QC decisions, and the run index. Regenerable. |
| `runs/` | one JSON record per run. Small, text, committed. |
| `var/` | accounts, sessions, config history. Backed up, not regenerable. |

## Words used here

**Study id** the only identifier that appears anywhere. Never a name, an MRN, a
date of surgery, or initials.

**Derivation** one channel after a montage is applied: `2b-1` is contact 2b
referenced to contact 1.

**Montage, or reference scheme** how contacts are combined: monopolar, bipolar
vertical, bipolar horizontal, bipolar adjacent, or common average.

**Recipe** one analysis, declared once, callable from anywhere.

**Claim** the sentence you write before a run saying what it is meant to show.

**Flag** one QC observation about one target, with evidence.

**Run id** the timestamped name of a run, and the way to cite its result.
