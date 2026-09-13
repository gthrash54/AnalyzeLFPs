# Decisions

Append-only. Each entry records what was decided, when, and why, so a later reader
does not relitigate it from scratch. Newest last.

## 2026-09-03 Scaffold only, no analysis code

The repository is created as structure alone: package tree, configs, manifests, docs,
and a test harness. No analysis is written yet. The reason is that the recording
parameters and the manifest contract are not settled, and analysis written before
those are fixed would have to be thrown away.

## 2026-09-03 uv as the environment manager

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. uv was not
installed on this machine and was added through the official standalone installer to
`~/.local/bin`, without sudo. Resolved to Python 3.12.14. The existing conda
`phd-prep` environment is deliberately not used: this project needs a lock file and
an environment that a collaborator can reproduce exactly, and `phd-prep` is a personal
study environment with a different purpose.

## 2026-09-03 py_neuromodulation is a hard dependency

`py-neuromodulation` installs cleanly under uv on macOS arm64 (version 0.1.7) and
imports without error, so it is a required runtime dependency rather than an optional
extra. It is included because it already implements the intraoperative DBS feature
pipeline this project would otherwise rewrite: band power, sharpwave and bursting
features, and the real-time framing that adaptive DBS work needs. It pulls a large
dependency tree, including `pyqtgraph` and `xarray`. If that footprint becomes a
problem for the API container, the fallback is to move it to an optional extra and
import it lazily inside the recipes that use it.

## 2026-09-03 Python pinned to >=3.11,<3.13

MNE 1.12.1 and py-neuromodulation both support 3.11 and 3.12. The upper bound is
there because the scientific stack lags on new releases and a broken resolve during
an analysis push is worse than a late upgrade. Revisit when 3.13 wheels are routine.

## 2026-09-03 Only summary.json escapes derivatives/

`data/` and `derivatives/` are git-ignored. The exception is `summary.json` per run,
which is small, text, and diffable, and carries the provenance needed to regenerate
the rest. The alternative, committing figures and tables, makes the repository large
and makes review meaningless.

## 2026-09-03 Manifests are authoritative, not inferred

Subject hemisphere, channel region, and channel inclusion come from
`manifest/*.csv` and are never guessed from file names or header text. Intraoperative
exports have inconsistent naming across cases, and inference there fails silently in
exactly the way that produces a wrong result nobody catches.

## 2026-09-03 React front end not yet scaffolded

The layout requested for this commit contains no front-end directory, so none was
created. `.gitignore` already excludes `web/dist/` in anticipation. The front end
is a separate piece of work once the API surface exists.

## 2026-09-03 Environment kept outside cloud sync via a symlinked .venv

This checkout lived inside a cloud-synced folder. The environment is about 20,000 files and
1.2 GB, which the sync client would copy continuously; the failure mode is a sync conflict
inside a virtual environment, which is silent corruption rather than a visible error.

`UV_PROJECT_ENVIRONMENT` was rejected: it is an environment variable only, not a
`uv.toml` key (verified against uv 0.12.9, which rejects `project-environment` as an
unknown field), so setting it would mean either a global export that points every uv
project on the machine at one shared directory, or a per-shell variable that a bare
`uv sync` from a plain terminal would silently miss and rebuild inside the
synced tree.

Instead `.venv` is a symlink to `~/.venvs/analyzedbs`. Verified that uv installs
through the symlink, leaves it intact across repeated syncs, and that `uv run`,
`.venv/bin/python`, and Pylance all resolve normally. No environment variable is
needed in any shell, and the footgun is closed: even a bare `uv sync` from any
terminal lands outside the synced tree.

Still open: whether raw recordings in `data/` may sit in cloud-synced storage at all. Git
ignores that directory, a sync client does not. That is an IRB and IT question to
settle before the first real export lands, not a technical one.

## 2026-09-03 Ground rules recorded in a project CLAUDE.md

Three rules, in `CLAUDE.md` and summarized in the README: read authored diffs and skip
generated ones, keep recordings out of anything that syncs or commits, and require a
`summary.json` behind every number that reaches a figure. Recorded in the repository
rather than held as habit so they survive a collaborator and a later session.

## 2026-09-03 Fixture files exempted from the recording-format gitignore

The build guide's step P0.1 specifies ignoring `*.eeg`, `*.vhdr`, `*.vmrk`, `*.fif`
globally. Step P1.3 then writes the synthetic subject as BrainVision into
`tests/fixtures/raw/` and says "commit all outputs". Verified with `git check-ignore`
that the P0.1 rules silently swallow the fixture: it would never be committed, and
every fixture test would pass on this machine and fail on a clean checkout, in CI, and
on a lab-mate's laptop, with no error message pointing at the cause.

Four negation rules now re-include `tests/fixtures/**/*.{eeg,vhdr,vmrk,fif}`. Verified
that a fixture `.vhdr` is committable while `data/anything.vhdr` stays ignored. The
fixture is synthetic and contains no patient data, so the identifier rule is not in
tension with this.

## 2026-09-03 Run records live in runs/, not derivatives/summary.json

The P0.1 `.gitignore` spec carries an exception for `derivatives/**/summary.json`, but
step P1.4 defines the provenance file as `runs/<run_id>.json`, and section 1.5 marks
`runs/` as committed. Nothing in the guide ever writes a `summary.json`. The earlier
scaffold docs here had followed the gitignore rather than P1.4 and described
`summary.json` as the provenance file; `docs/architecture.md`, `docs/schema.md`, and
the README are corrected to `runs/<run_id>.json`. The unused exception is left in
`.gitignore` as specified, harmless because nothing matches it.

## 2026-09-03 data/ is a symlink, so no tracked .gitkeep inside it

Step 0.3 mounts `data/` as a symlink to the sync folder holding the recordings. A
tracked `data/.gitkeep` would be written into that sync folder, so it is removed.
Verified that `tests/conftest.py` still detects recordings correctly through a
symlinked `data/`: `Path.rglob` resolves the top-level symlink, so `realdata` tests
skip when the folder is empty and run when it is populated.

## 2026-09-03 Claude Code settings adapted from Appendix B to the current schema

Appendix B is written against an older permission syntax. Changes made, with the
reasoning, since the guide asks for the current schema rather than a guess:

- Bash rules use the `Tool(prefix:*)` form (`Bash(uv run:*)`), not `Bash(uv run *)`.
  The space-star form is not the documented prefix-match syntax.
- Path rules are gitignore-style relative to the settings file (`Edit(src/**)`), and
  the absolute deny for the Obsidian vault uses the `//` absolute prefix.
- `Bash(git *)` is narrowed to specific read and commit subcommands, and
  `Bash(git push:*)` is denied outright, matching the standing rule that nothing is
  pushed without being asked.
- The PostToolUse hook calls `.claude/hooks/pytest_on_code_change.sh` rather than
  inlining pytest, because step P0.2 asks for the tests to run only when the edited
  path is under `src/` or `tests/`, and a matcher cannot express that. The script
  reads the hook payload, treats pytest's exit 5 (nothing collected) as success while
  the scaffold has no tests, and exits 2 on real failure so the failure is fed back
  rather than swallowed. Appendix B's `|| true` would hide every failing test.
  All four branches verified: docs edit skips, src edit with no tests passes, src edit
  with a failing test reports and exits 2, malformed payload exits cleanly.

Open tension, not resolved here: the guide denies `WebFetch` and `WebSearch`, but step
P3.3 requires reading py_neuromodulation's current docs and step P0.2 suggests
consulting current Claude Code docs. Denied as specified; reading installed package
source is the workaround, and the deny can be relaxed to `ask` if that proves too tight.

## 2026-09-03 The project generalizes; the first subject analyzed is the first case, not the definition

Standing requirement from Garrett: the app must be customizable and
generalizable. Consequences applied throughout the data contract. Contact naming
moved to `configs/leads.yaml` keyed by device model, because it depends on
manufacturer and on whether the lead is directional, and a fixed vocabulary would
break on the next implant. Region, condition, window-provenance, and
reference-scheme vocabularies moved to `configs/vocabularies.yaml`, so extending
any of them is a config line. The reader is chosen by a `format` column rather
than assumed. Nothing in the schema hardcodes a channel count, a sampling rate, a
task, or a vendor.

## 2026-09-03 TDT MATLAB v7.3 is the first reader, not BrainVision

The build guide assumes BrainVision end to end. The block actually under analysis
is TDT Synapse output saved as MATLAB v7.3, which is HDF5, so h5py can pull one
stream or one time window without loading 1.5 GB. BrainVision appears only in
stage 2 (ERNA stim protocol). Building the walking skeleton on BrainVision would
have meant building it on data not currently being analyzed. `io/` therefore
becomes a small reader registry dispatching on `subjects.csv:format`, with
`tdt_mat` first and `brainvision` second.

## 2026-09-03 Manifests split from two files to five

P0.1 specifies `subjects.csv` and `channels.csv`. That cannot express this
dataset. One recording carries streams at 48828.1, 24414.1, and 12207.0 Hz, so
`sfreq_expected` as a subject-level column is wrong; rate is a stream property,
hence `streams.csv`. A subject has two leads with different targets and
potentially different models, hence `leads.csv`. There are no task markers at all
in stage 1, so conditions come from windows derived from the microphone and EMG,
which must carry provenance and a revision status, hence `windows.csv`. The guide
assumed `events.tsv` derived from markers; there are none to derive from.

## 2026-09-03 A guardrails layer, separate from QC

New, not in the guide. QC asks whether the signal is usable. Guardrails ask
whether the analysis about to run answers the question it claims to. Twelve are
drafted in `docs/guardrails.md` from traps already hit on this dataset: monopolar
common-mode, effects tracking electrode identity, Jensen's inequality on ratios,
thresholds set across conditions, analysis windows longer than the phenomenon,
decimation removing the claimed band, speech EMG contamination, dB versus z,
non-stationarity exceeding the effect, window provenance, missing motor control,
and smoothed baselines.

Each check explains rather than merely blocks, can be overridden, and records the
override with its reason in the run record. This is how the app serves both
audiences at once: the defaults are what a careful analyst would choose, so a
first-year student gets the same checks a PI applies by habit, without either
getting a different pipeline.

## 2026-09-03 data/ points at the local working copy, and nothing recurses into Box

`data/` was briefly symlinked to the Box root, which holds 464 subject folders
that stream on demand. A recursive walk there takes minutes and pulls files over
the network. `tests/conftest.py` did exactly that on every pytest start, via
`rglob`. Fixed to a depth-one scan that stops at the first entry: 0.17 s against
the mount, down from a walk that had to be killed.

`data/` now points at `~/Documents/DBS_local/`, the local working copy. Box stays
reachable by absolute path for the steps that genuinely need the archive, so
nothing inside the repo can walk it by accident. Rule for anything added later:
enumerate one subject at a time, never glob the archive root.

## 2026-09-03 Bipolar is the default reference, everywhere

Not a preference. On the first subject analyzed monopolar produced a +2.59 dB high-gamma effect on
all 28 contacts at once with IQR 0.23 dB, which fell to +0.3 dB under either
bipolar montage. Every recipe taking a reference parameter defaults to a bipolar
scheme, and `configs/vocabularies.yaml` marks monopolar and CAR as not
safe-by-default with the reason attached. Monopolar remains available so a
montage comparison can be run deliberately.

## 2026-09-03 Layout is detected and confirmed, never assumed

Standing requirement: recordings will all be DBS and ECoG, but layouts and
configurations will differ, and the app should catch that automatically where it
can and offer a selection where it cannot.

The pattern mirrors QC: detection proposes, a person confirms, the manifest
records the decision. Detection never writes a manifest directly, because a
proposal with evidence that a human accepted is auditable and a silent guess is
not. Re-running detection on a confirmed recording reports disagreements rather
than overwriting. Configured in `configs/layout_detection.yaml`.

Detectable from the signal, with confidence and evidence attached: stream roles
(from name, channel count, and rate), contiguous channel blocks that look like
separate arrays, ring versus segment geometry from the impedance signature,
sampling rate, mains frequency at 50 versus 60 Hz, and whether a shared reference
is in use.

Not detectable, and therefore presented as a ranked selection rather than
guessed: lead manufacturer, anatomical target, hemisphere, lead rotation, and
ECoG strip location. Impedance separates rings from segments but cannot identify
a vendor, and several manufacturers ship the same 1-3-3-1 geometry with different
contact numbering, so a guess there mislabels every figure downstream. Target and
hemisphere are surgical facts, not properties of the signal.

Condition windows are a middle case: proposable from the microphone envelope, EMG,
or video frame times when no task markers exist, always with `derived_from` set to
whichever signal produced them, never assumed.

## 2026-09-03 Dataset-specific content quarantined from the contract

Everything specific to one recording moved to `docs/datasets/`, leaving
`docs/schema.md` as the general contract. Guardrail thresholds moved from prose
into `configs/guardrails.yaml`, so each of the twelve checks can be tuned,
downgraded, or disabled by a lab without touching code, and the rules themselves
are stated generally rather than with one dataset's numbers baked in. Three
guardrails are deliberately not overridable, because they are arithmetic rather
than judgment: ratio-before-average, decimation removing a claimed band, and
baseline statistics computed on smoothed data.

## 2026-09-03 TDT reader first, verified against the file rather than written from memory

`scripts/inspect_recording.py` reported the actual HDF5 layout before any reader
code was written. Findings that shaped the implementation: streams live at
`/importdata/streams/<name>/` with `data`, `fs`, `channel`, and `startTime`;
`data` is stored `(n_samples, n_channels)`, the transpose of what MATLAB
displays, because MATLAB writes column-major; strings are uint16 char arrays;
`data` is gzip-chunked `(585, 28)`, chunked along samples across the full channel
width.

That chunking decides the read strategy. A 2 s window across all 28 channels
takes about 60 ms, while reading one channel across a long span still
decompresses every chunk it touches. `read` therefore pulls the full channel
width for the window and selects afterwards in numpy, and the docstring tells
callers to prefer windowed reads over per-channel iteration.

The reader normalizes to `(n_channels, n_samples)` so the transpose happens once,
in one place, and nothing downstream transposes again.

## 2026-09-03 Identifiers stop at the io layer, filenames included

`Recording.metadata` returns structural fields only. Identifier-bearing fields
are reachable solely through `read_restricted_metadata`, so touching them is a
deliberate, greppable act, and it exists for de-identification rather than for
analysis.

A real-data test caught that `metadata` included the filename, which reaches
anything the metadata feeds. See the correction entry below for what that
timestamp actually is; the handling became a declared policy rather than an
assumption. Run records store the content hash plus the manifest key, never the
path as found on disk.

This is the argument for real-data tests that assert a contract rather than a
dataset: the synthetic fixture could not have caught it, because a fixture is not
named after a patient.

## 2026-09-03 MATLAB interop through artifacts, not shared code

Question raised directly: does the app work for people who use MATLAB. The data
layer already does, in both directions. TDT `.mat` is HDF5, Parquet and CSV and
JSON and PNG are all readable from MATLAB, so no analysis output is locked to
Python.

The friction is YAML, which MATLAB cannot read without an add-on. Fixed by
writing a resolved `config.json` into every run directory: YAML stays the
hand-edited source of truth, JSON is the machine-readable snapshot that proves
which settings produced a result. `scripts/matlab/load_run.m` reads a run record,
its config snapshot, its tables, and its figures in about sixty lines.

Cross-language calling (MATLAB's `py.`, Python's MATLAB Engine API) is possible
in both directions and deliberately not load-bearing: the first is sensitive to
which interpreter MATLAB finds, and the second requires a MATLAB license on the
deployment target, which is a bad constraint for a lab server.

The rule that matters when porting: a recipe reimplementing an existing MATLAB
analysis must reproduce its result on the same window before replacing it.
Findings already shown to a PI must not change because the language changed.
Decimation parameters, filter design, array orientation, and 1- versus 0-based
indexing are the four places results actually diverge, so they are named in
`docs/interop.md` and become parity tests rather than assumptions.

## 2026-09-03 Correction: the filename timestamp is an upload time, not a surgery date

The earlier entry called the `YYMMDD-HHMMSS` stamp in the raw TDT filenames a
surgery date. That was wrong, and Garrett corrected it: uploads are deliberately
performed on days separated from the procedure, so the file timestamp cannot be
used to recover when surgery happened. That separation is an existing
de-identification practice, not an accident.

What the filenames actually contain is the study ID and the block name, both of
which the hard rules permit. So the filename here is not an identifier, and the
blanket claim that acquisition systems name files after the subject and the
session date does not hold for this lab and should not have been generalized from
one observation.

What survives the correction is narrower and is now a declared policy rather than
an assumption. `configs/privacy.yaml` carries `filenames_deidentified`, default
`false`, set `true` here with the upload-day convention recorded as the reason. A
site that has not confirmed its export naming gets the careful behavior; this lab
gets its filenames back. `PrivacyPolicy` is passed to `open_recording`, and an
omitted policy withholds more rather than less.

Restricted metadata fields are governed separately and unconditionally, because
recording metadata is where operator names and acquisition paths genuinely live,
and that is true regardless of filename convention. The list moved from a
hardcoded frozenset into `configs/privacy.yaml`, per format, so extending it is a
config line.

Guardrail G13 was rewritten accordingly: it is now a policy check whose severity
follows the config, not a claim that filenames are always identifiers. The rule
that recordings are referred to by manifest key survives on its own merits, since
a path is machine-specific and a manifest key is not.

Lesson recorded because it will recur: a single real recording is evidence about
that recording. Generalizing a privacy claim from one filename produced a rule
that was both wrong and more restrictive than the lab needs. Ask before encoding
an observation as a policy.

## 2026-09-03 The hardware impedance export is the detection input

"Go off whatever the box says." The amplifier writes an impedance sweep per bank,
and that file is the most direct evidence available about what is physically
connected, so it is what detection reads rather than inferring contact roles from
the signal.

`io/impedance.py` parses the export generically: any `R<n> (kOhm)` column is a
channel, `REF` is the reference, `-1.00` means not measured rather than a value,
and rows are merged so a bank measured across two sweeps reads as one set.
Differential banks are paired, because an EMG channel is two electrodes and is
only as good as its worse one.

`detect/geometry.py` classifies ring versus segment from the ratio to the lowest
impedance in the span, since a lead always has at least one ring and rings read
lowest. Run on the first recording it reproduced the verified signature without
being told it: `[1, 3, 3, 1]` on both leads, segment-to-ring ratios 1.94 and 2.11.

One design fix during the work. The detector first proposed a named vendor
because it sorted first alphabetically among the models sharing that geometry.
That is exactly the mislabeling the design was supposed to prevent: several
manufacturers ship 1-3-3-1 with different contact numbering. It now proposes the
`unknown_directional_1331` placeholder, refuses to prefill, and offers the
specific vendors as alternatives for a person to choose from.

The same run independently supported two manifest decisions that had been made
from the datasheet alone: EMG channel 3 carries a 37.34 kOhm electrode, above the
high-impedance threshold, and channel 4 reads 536.87 kOhm on both electrodes,
which is an open circuit. Two sources agreeing is worth more than either alone,
and where they disagree neither silently wins.

## 2026-09-03 `ecog_site` generalized to `site`

Every non-depth channel has a site, not only cortical ones. EMG channels carry a
muscle. The column is now `site` and holds a strip location, a muscle name, or
empty when unknown. Applied: FDI, FCU, TA on EMG channels 1 to 3, with channel 4
unassigned and excluded as an open circuit.

## 2026-09-03 Acquisition date is permitted

Decided by Garrett: the acquisition date and time record when a block was
recorded, are not treated as sensitive here, and are useful for ordering sessions
and matching against an operative log. Removed from the restricted metadata list
in `configs/privacy.yaml` and added to `subjects.csv` as `acquisition_date`. A
site that disagrees adds the fields back to its own list and leaves the column
blank.

## 2026-09-03 No numerical parity requirement for now

Decided by Garrett: build the recipes and add parity against the existing MATLAB
pipeline later, rather than exporting reference values first.

The risk, recorded so it is a choice rather than an oversight: without a
reference, the Python implementation becomes the de facto truth by default, and a
finding already shown to the PI could change because the language changed without
anyone noticing. The four places results actually diverge are named in
`docs/interop.md`. When a recipe reproduces an existing MATLAB analysis, exporting
a reference window before trusting the new numbers is still the cheap insurance.

## 2026-09-03 Recipe parameters, decided by Garrett

Four scientific choices for the first recipe, all resolved toward making the
choice visible and recorded rather than baked in.

**Unit of analysis: both, as a parameter.** Conditions here are single continuous
windows, not repeated trials, so the guide's trial assumption does not hold. The
recipe takes `unit`, either the whole window (one observation per condition,
honest at n=1, descriptive only) or fixed-length pseudo-epochs (gives an n and
permits permutation tests, at the cost that the epochs are not independent, which
any p-value must account for). Window is the default.

**Reference: compute every montage each run.** Rather than picking one default,
the recipe derives monopolar and each bipolar scheme and reports the spread
across channels. This makes guardrail G1 self-evidencing instead of asserted, and
turns montage sensitivity into a routine output rather than a special study. It
costs several times the compute per run, which is affordable at this data size.

**Rate: parameter, defaulting to 8138 Hz.** Decimating 48828.125 by 6 in a single
stage, usable to about 3255 Hz, which meets the PI's 6 to 10 kHz request. Runs
can be reproduced at the old 2034.5 Hz for comparison by setting the parameter.
Guardrail G6 refuses any requested band above the anti-alias cutoff.

**Estimator: parameter, Welch at 1 s default, multitaper available.** Exposed
through the registry so the choice appears in the UI and in every run record.
Guardrail G5 warns when the window is long relative to the effect claimed.

## 2026-09-03 Montage derivations come from geometry, and one was wrong

`preprocess/reference.py` builds derivations from the lead's declared geometry
rather than from a hardcoded contact order, so the same code produces correct
pairs for a 1-3-3-1 directional lead and for a four-ring lead.

The first implementation of `bipolar_vertical` chose the nearest ring *below*
each segment row. On a 1-3-3-1 lead that sent both segment rows to the ventral
ring, which is not the montage in use here and quietly changes what the
derivation means. Corrected to the nearest ring by distance, which yields the
lower segments against the ventral ring and the upper segments against the dorsal
ring. In Garrett's aliases that is `1a-0, 1b-0, 1c-0` and `2a-3, 2b-3, 2c-3`,
matching his existing montage exactly.

A test now asserts that every bipolar derivation's weights sum to zero, so a
derivation that fails to reject a constant offset cannot ship, and another
asserts that bipolar reduces an injected common-mode signal by an order of
magnitude, which is the premise of G1 stated as a test rather than a claim.

## 2026-09-03 Guardrail engine: refuse, explain, offer the override

Decided by Garrett. A blocking guardrail stops the run before anything is
computed, states what fired and why it matters, and names the exact override.
Nothing is produced, so a blocked result cannot reach a figure by accident. The
alternative considered and rejected was running anyway and stamping the output,
which fails the moment a stamped figure is cropped into a slide.

Three properties of the design worth stating:

Severity lives in config, not in code. A check decides whether something is true;
`configs/guardrails.yaml` decides how much it matters. A lab can downgrade or
disable any check without touching Python, and the same check can block here and
merely note elsewhere.

An override needs a reason, enforced in the constructor rather than by
convention. An unexplained override is indistinguishable from not having the
check, so `Override` refuses to exist without one, and the reason goes into the
run record.

Three checks refuse overrides entirely: ratio-before-average, decimation removing
a claimed band, and baseline statistics on smoothed data. These are arithmetic
rather than judgment, and an override there would only ever record that someone
wanted a wrong number.

A check that cannot see what it needs returns nothing rather than guessing.
Guessing in either direction is worse than silence: blocking valid work teaches
people to override reflexively, and firing on absent evidence gives false
assurance.

Eight of the thirteen are implemented, being the ones the first recipe can
actually evaluate. G3, G4, G7, G9 and G13 need context the recipe layer does not
yet produce; they stay documented and configured so the gap is visible.

## 2026-09-03 First recipe parameters, remaining three decided

**Primary montage: bipolar_vertical, with the across-montage spread reported
alongside.** Matches the montage Garrett's existing figures and decks use, so new
results stay comparable to what the PI has already seen, while the spread panel
keeps the choice visible rather than hidden.

**Granularity: per derivation and per row.** Tables keep every derivation and add
an explicit row-level aggregate (ventral ring, lower segments, upper segments,
dorsal ring), because row is the level finding 7 lives at: the effect localizes to
the dorsal rows. Averaging to region before writing out would have hidden it.

**Units: dB and z, always, side by side.** Finding 4 is that z-scoring deflates
everything, so the two tell different stories and both belong on every result.
The dB theta to high-gamma ratio of 24x becomes 4x in z; reporting only dB lets
dynamic range read as effect size. Baseline statistics come from unsmoothed data,
which guardrail G12 enforces and refuses to let anyone override.

## 2026-09-03 Decimation happens after re-referencing

The loader re-references first, then decimates. The alternative filters channels
that are about to be subtracted from each other, which applies the anti-alias
filter twice to the common-mode component and once to the difference. Doing it in
this order means the filter acts on the signal actually analyzed, and the run
record can state one decimation factor and one stage count for the derived data.

## 2026-09-03 Row labels come from geometry, not from row numbering

A bug caught by reading the loader's output against the physical lead. Contact
rows were labeled by comparing the absolute row index against half the row count,
which put the upper segment row of a 1-3-3-1 lead into `lower_segments`. Finding 7
says the effect localizes to the dorsal rows, so that mislabeling would have
inverted the one result the per-row aggregate exists to test.

Labels now come from position among rows of the same kind: the first ring row is
ventral, the last is dorsal, the first segment row is lower, the last is upper.
Row indices are a config detail, and no finding should depend on how a lead model
happens to number them.

## 2026-09-03 z baseline is a parameter, defaulting to each condition's own distribution

Decided by Garrett. The default z-scores each channel against the variability
within the same condition window, so no cross-condition baseline is needed and
the rest window being under revision does not contaminate every result. It
answers "how unusual is this for this channel" rather than "how does this compare
to rest".

`rest` and `whole_recording` remain available as parameter values. Results using
`rest` inherit the G10 flag until that window is replaced, and `whole_recording`
includes the task periods inside its own baseline, which shrinks any effect toward
zero by construction. Every figure states which baseline produced it.

## 2026-09-03 Correction: the stim epochs were never recorded in this block

An earlier entry and commit said `PeA/`, `Note` and `MonA` "did not survive
conversion to .mat", inferred from their appearing in `StoresListing.txt` but not
in the export. That inference was wrong.

Reading the tank's own event index directly (`.tsq`, 207,886 records) shows only
four stores with events: `ecos`, `emgg`, `mic_`, and `Cam1`. There are no `PeA/`
events at all. `StoresListing.txt` describes what the Synapse rig had configured,
not what fired during a given block, and `motor_lesion_2leads` is a lesion-testing
and speech block with no stimulation in it. The `.mat` export is complete.

This matters because it changes ERNA from a data-recovery problem into a
which-block problem. Stimulation data exists in `increment1_depth1-6`,
`increment2_depth1_2` through `depth6`, and `clinical_dbs1/2`.

Lesson, and it is the second time today: a configuration file describes intent,
and an index describes what happened. Read the one that records events before
concluding that data was lost.

## 2026-09-03 The other blocks are raw TDT tanks, not .mat

Only `motor_lesion_2leads` has been converted. Every other block in the case
exists as a raw TDT tank (`.tsq` index plus `.tev` data). Analyzing ERNA or using
a different block as a rest baseline therefore needs either a native tank reader
in `io/`, or those blocks converted to `.mat` first.

Sizes observed: `motor_baseline` is a 99 MB `.tev`, `increment2_depth1_2` is
1.18 GB, `motor_baseline_metronome` is 1.29 GB. The full set is many gigabytes
streaming from Box, so whichever path is chosen, blocks are fetched one at a time.

`motor_baseline` is the obvious candidate for the true rest window the PI asked
for: it is a dedicated baseline block in the same case, and at 99 MB it is the
cheapest block in the set to pull.

## 2026-09-03 Native TDT tank reader, alongside the .mat reader

Decided by Garrett: build a native `.tsq` plus `.tev` reader first, and keep the
`.mat` reader for blocks already converted. Two readers, which is what the format
registry was built for: `subjects.csv:format` selects one, and nothing downstream
changes.

The tank reader is the one that unblocks work. Only `motor_lesion_2leads` is a
`.mat`, so without it every ERNA block and every candidate rest block needs a
manual MATLAB step before the app can see it. Reading tanks directly also gets
the stimulation epochs from the index, where they already are, rather than
depending on a conversion to carry them.

`.tsq` parsing is already demonstrated: 40-byte records of size, type, 4-character
store code, channel, sortcode, timestamp, offset, format and frequency, and it
reported the four active stores in the first block correctly. `.tev` is a flat
binary that the index points into, so a windowed read is a seek and a slice, which
suits the same lazy interface `tdt_mat` already implements.

Order of work is therefore: tank reader, then `psd_by_condition`, which is when a
figure first appears.

## 2026-09-03 Native TDT tank reader, verified two ways

`io/tdt_tank.py` reads a raw tank: the `.tsq` index plus the `.tev` data file,
registered as format `tdt_tank` alongside `tdt_mat`. Every block in a case is now
reachable without a manual MATLAB conversion.

Record layout established by reading a real index rather than from memory:
40 bytes of size, type, four-character store code, channel, sortcode, timestamp,
ev, format, frequency. `size` counts 4-byte words including the 10-word header, so
a float32 stream record holds `size - 10` samples. For a store whose records
carry 4096 samples that gives `size` 4106, which is exactly what the `.mat`
export reports for the same store, and is what confirmed the interpretation.

Verified two independent ways, because a binary format read wrongly produces
plausible numbers rather than an error:

Against the real block, structure only. From the index alone the reader reports
28 channels at 48828.125 Hz with 25,169,920 samples, 4 at 12207.031, and 1 at
24414.062, all identical to what the `.mat` export reports for the same block.

Against a synthetic tank, data included. `tests/fixtures/make_tdt_tank_fixture.py`
writes a byte-accurate `.tsq` and `.tev` where channel c holds `c * 1e6 + sample
index`, so a mis-assembled read is obvious rather than merely wrong. Records are
interleaved by channel as TDT writes them, and the tests cover full reads, windows
crossing record boundaries, windows inside one record, channel reordering, and
half-open adjacency.

Design choice: a tank opens with only its index. Structure comes from the `.tsq`
alone, so a tank whose bulk data has not been synced can still be triaged, which
is exactly the question asked of this case earlier today. `read` is what needs the
`.tev`, and says so plainly when it is missing.

The `ev` field is an offset for stream records and a float64 value for epoch
records, which is why epochs are decoded through a view rather than a cast.

## 2026-09-04 psd_by_condition, and four bugs it exposed

The first recipe. Reads each condition's window, re-references under every
requested montage, decimates, estimates the spectrum per time segment, and
reports the mean in dB alongside a z. Tables keep every derivation and add
per-row and per-region aggregates; outputs are Parquet, CSV and JSON as decided.

Running it on the real recording found four defects that component tests had not:

**Explicitly named outputs suppressed discovery of everything else.** A record
listed six figures and no tables, because discovery ran only when nothing had
been added by hand and the registry names each figure. Discovery now always runs
and unions with whatever was named. A rule written as "if empty" that should have
been "always, then merge".

**Guardrails judged windows the run never touched.** G10 fired about the rest
window on a run over overt and metro only. A warning nobody can act on is how a
check becomes noise people learn to ignore, so the context now carries only the
windows the run actually reads. Verified silent without rest, firing with it.

**`registry.run` accepted an `overrides` argument and never passed it on.** The
documented escape hatch did nothing, so a blocking guardrail could not be
overridden through the sanctioned path at all. Caught because a test asserted the
override worked rather than asserting the block fired.

**Run ids collided within a second.** `YYYYMMDD_HHMMSS_<name>` has one-second
resolution, so two runs started in the same second overwrote each other, record
and output directory both. It surfaced as one test passing alone and failing in
the suite, which is the shape a real concurrency bug takes. Ids now take a `-2`
suffix rather than destroying a result.

The z semantics under the default `own_condition` baseline center each condition
on the grand mean across conditions and scale by the pooled within-condition
standard deviation across segments. That is one reading of "z against the
variability within that same condition", and it is the single modeling choice
here that Garrett should confirm rather than inherit.

Observed on a first real run, over overt and metro on the STN lead at 2034.5 Hz:
a beta peak near 20 Hz in both conditions, and a median across-montage spread of
12.2 dB with a maximum of 16.8 dB. The spread is the point: which montage is
chosen moves the answer by more than most reported effects.

## 2026-09-04 The z centre and scale are separate, choosable, and explained

Decided by Garrett, and it generalizes past this recipe: the analysis must be
customizable, with an explanation of what each choice does travelling alongside
it.

Centre and scale are now independent parameters, because they answer different
questions. The centre decides what a result is compared against; the scale
decides what counts as a large difference. The previous single `baseline`
setting coupled them and hid which of the two a reader was looking at.

Four centres (grand mean across conditions, a named baseline condition, all
segments pooled and weighted by duration, none) and five scales (pooled
within-condition, each condition's own, the baseline condition's,
between-condition spread, none). Twenty combinations, all tested.

The design point is `configs/statistics.yaml`. Every option carries a label, a
description, when to use it, and its caveat, and those strings reach three places
from that one source: the JSON schema an interface builds its form from, the run
record, and the figure caption. A z that appears in a table or a slide can always
be traced back to a sentence saying what it meant, without anyone remembering.

Caveats are stated rather than implied, because they are the part a first-year
student will not know to ask about. Pooled scaling lets one noisy condition shrink
every z. Own-condition scaling gives a noisy condition a smaller z purely for
being noisy, understating effects exactly where they are hardest to see.
Whole-recording centring puts the task periods inside their own baseline.
Between-condition spread is meaningless with fewer than three conditions.

Two arithmetic guarantees: a zero scale becomes NaN rather than infinity, because
an infinite z reads as an enormous effect while a NaN is noticed; and asking for a
baseline condition absent from the run is an error naming what is available,
rather than a silent fallback.

Defaults are the grand mean and the pooled within-condition scale, which need no
rest window and so inherit nothing from a window still under revision.

## 2026-09-04 API covers read-and-run, upload, and the agent

Decided by Garrett: all three in the first pass rather than the guide's
read-and-run surface alone.

Ten routes. `/subjects` and `/recipes` expose what the interface needs to build
itself, including the option explanations from `configs/statistics.yaml`, so a
parameter form shows caveats beside each choice rather than a bare enum.
`/configs/{name}` serves a config file so the interface can display thresholds it
did not hardcode.

Runs execute as background tasks and return a handle immediately. Parameters are
validated against the recipe's Pydantic model before anything is queued, so a
typo fails in milliseconds with a message rather than after a long read. A
blocked guardrail comes back as status `blocked` with the findings and their
remedies attached, not as a generic failure.

`/runs/{id}/files/{path}` resolves the target and checks containment before
touching the filesystem, so a crafted path cannot escape a run directory.

## 2026-09-04 Upload stores a file and deliberately writes no manifest row

An upload is not a decision about what a channel is. The manifest is
hand-curated and authoritative, and inferring rows from a filename would be
exactly the guessing the layout-detection design exists to avoid. So `/uploads`
stores the file, reports which reader would open it, and returns the steps a
person still has to take.

Refusals are informative: an unsupported extension names the supported list, an
oversized file is refused mid-stream and the partial file removed, and a filename
is reduced to its basename so it can never be a location.

## 2026-09-04 The agent is deterministic and local

Decided by Garrett. No model call and no network. Everything the proposer knows
comes from the manifest, the recipe schemas, `configs/statistics.yaml`, and
`configs/guardrails.yaml`, so nothing about a recording leaves the machine and no
API key or IT conversation is needed before it is useful.

It reads a plain-language request and returns proposed parameters, the reason for
each, the caveats attached to the statistics it would use, and the questions it
could not answer. Anything it could not determine comes back as a question rather
than a default quietly applied.

The most useful thing it does is dry-run the guardrails against the parameters it
is about to suggest, so a block is reported before a run starts rather than after.
Asked for beta in the STN during overt speech it proposes 13 to 30 Hz on lead1
over the overt window, and warns that no motor control condition is included, so
any low-frequency change will have a motor explanation the run cannot exclude.
Asked for high gamma at monopolar it refuses and says why.

Rule-based is not a placeholder for this layer, it is the tool surface a model
would drive later. The interface is shaped so a model backend can be swapped in
without changing what a caller sees.

## 2026-09-04 Command line over the same package the API calls

`python -m dbsspeech` with six subcommands: `status`, `validate`, `ask`, `run`,
`inspect`, `serve`. It calls the package directly, so a run started in a terminal
is indistinguishable from one started in a browser: same guardrails, same run
record, same provenance. Nothing here reimplements anything, which is the whole
reason the registry does the orchestration.

`ask` is the terminal face of the agent. It prints the proposed parameters, the
reason for each, the guardrails that would fire with their remedies, the caveats
of the statistics it would use, what it could not determine, and then the exact
`run` command to execute it. When a guardrail would block, it says so and prints
no command, because handing over a command that cannot work is worse than
handing over nothing.

`run` exits 2 when a guardrail blocks, so a shell pipeline notices rather than
carrying on. `--set` parses values as JSON first, so numbers, booleans and lists
keep their type, falling back to a comma-split list and then a bare string.
`--override` requires `guardrail=reason` and refuses a bare guardrail name, which
is the same rule the `Override` constructor enforces.

`status` marks a window under revision with an asterisk and explains the mark,
and flags any run produced from a dirty working tree, because the code that made
it is then in no commit.

## 2026-09-04 Node install blocked by this project's own deny rule

Installing Node for the front end needed `curl`, which `.claude/settings.json`
denies. Routing around it was possible and was not done: a guardrail that gets
bypassed the first time it is inconvenient is not a guardrail. Garrett runs the
one command himself and the rule stays intact.

Recorded because the same situation will recur, and the answer should be the same
each time.

## 2026-09-04 Dependency lists were diverging silently

`uv add --group dev` writes to `[dependency-groups]`, while `uv sync --extra dev`
reads `[project.optional-dependencies]`. The two dev lists drifted apart and a
test dependency vanished on the next sync, which surfaced as a collection error
rather than as anything pointing at the cause.

The two lists are now identical, with a comment saying to keep them so, and a
test asserts they agree. `python-multipart` moved from dev to runtime, where it
belongs: the upload route fails at import without it, so it is not optional.

## 2026-09-04 Front end: Vite, React, TypeScript, Tailwind

Five routes. Ask is the landing page rather than Subjects, because describing an
analysis in words and seeing what it would do is the point of the app; the
guide's Subjects-first ordering assumes you already know which recipe you want.

The parameter form generates itself from the recipe's JSON schema, and renders
the description and caveat the server sends for each option beside the field.
That is why `configs/statistics.yaml` carries prose: adding a parameter, or
changing what a choice means, needs no front-end change at all.

Three things are shown by default that an interface usually hides. A lead whose
rotation is unknown is badged on the subject card, because that gates every
anatomical direction claim. A window under revision is badged wherever it
appears. A run produced from a dirty working tree is badged in the runs table and
on the result, because the code that made it is in no commit.

Vite proxies `/api` to the backend, so the browser talks to a single origin and
the CORS surface stays as narrow as it was. The API still binds to localhost and
still has no auth; nothing here changes that.

The typed client is hand-written and strict, no `any`. If the server's shape
drifts, a page fails to compile rather than rendering something wrong.

`scripts/dev.sh` starts both and stops both on Ctrl-C.

Node was installed as a standalone tarball into `~/.local/node`, matching how uv
was installed: no sudo, no system files, removable by deleting one directory.
Garrett ran the command himself because this project's settings deny `curl`, and
that rule was left intact.

## 2026-09-04 QC flag detectors, and peer groups that respect lead geometry

Eight detectors as pure functions: flat channel, variance outlier, kurtosis
outlier, high-frequency noise ratio, line noise, clipping, amplitude window, and
trial amplitude outlier. Every one returns flags with the numbers behind them and
a proposed action, and none of them decides anything.

Never delete: an amplitude excursion becomes an annotation, not a cut. Recipes
decide how to treat annotations.

Refuse to propose on too few channels: below `min_channels_for_outlier_stats` a
peer-comparison detector reports its evidence with no proposed action, so a
reviewer sees the number without being nudged by a threshold that could not
support it. That is the guide's own warning about robust statistics over four to
eight contacts, enforced rather than remembered.

Peer groups respect lead geometry. `outlier_grouping` defaults to
`region_and_kind`, comparing rings with rings and segments with segments, because
a ring has roughly twice a segment's surface area. Running the pooled version on
real data flagged both ventral rings for high-frequency noise and variance, with
values below the group median: flagged for being rings. See docs/findings.md.

Line noise proposes a notch rather than exclusion, since mains is expected in an
operating room, and the mains frequency is a parameter so a 50 Hz site works.

Flag ids are a stable hash of target, type and target type, so a reviewer's
decision survives re-detection. That is what makes the merge behavior in the next
step possible.

Deliberately not using pyprep's NoisyChannels, which the guide suggests. It is
tuned for scalp EEG with dozens of electrodes, and its correlation and RANSAC
heuristics assume spatial neighbors a depth lead does not have. These detectors
are the same ideas computed within a defensible peer group.

Every detector can be disabled in config rather than deleted, because a PI
disagreeing that a detector should exist is different from a bug.

## 2026-09-04 Ring contacts stay reported, not judged

Decided by Garrett, on the finding that a directional lead has only two ring
contacts and they differ from segments by design. Detection reports the evidence
and proposes nothing, which is what the statistic can honestly support, and puts
a person on the two contacts that need judgment rather than a threshold.

Rejected: inventing absolute thresholds now. A threshold with no calibration
behind it that quietly passes everything is worse than no threshold, because it
looks like a check.

Still open, and better: comparing a ring against the same ring in the case's
other blocks, which is the right peer group. Blocked until blocks are chosen and
their data is reachable.

## 2026-09-04 Decisions table, and a merge that cannot lose judgment

Flags and decisions live in separate files because they have different
lifetimes. A flag is recomputed whenever detection runs; a decision is written
once and must survive every later run.

The merge rule: reviewer columns are preserved, detected columns are refreshed,
new flags are appended, and a flag that no longer fires is marked `stale` rather
than deleted. Refreshing evidence matters as much as preserving judgment, because
thresholds and data change and a reviewer should be looking at current numbers.
Keeping stale rows matters because the record should still show that someone once
judged that flag and what they said.

Flag ids are a stable hash of target, target type and flag type, which is what
makes any of this possible across runs.

A rejection, or an action different from the one proposed, requires a reason,
enforced in `decide` rather than by convention. Without one the record cannot
distinguish a considered override from a mis-click, and the difference is exactly
what a reviewer is being asked to supply.

History is append-only in `history.jsonl`, so signing and reopening leave a trail
that no later run rewrites.

## 2026-09-04 QC report: a model, then a renderer

Decided by Garrett: self-contained HTML now, MNE's Report later if a reviewer
wants the familiar format.

The risk in "both" is that two report paths drift on content. So the report is
split: `build_model` decides what goes in, `render_html` decides how it looks. A
second renderer reads the same model, so adding one cannot change what a report
contains. Anything that belongs in every report goes in the model, never in a
renderer.

The HTML embeds its figures, so it opens anywhere, survives being emailed, and
needs nothing installed at review time. A real report for the first subject is
140 KB.

Three things the report does that are about trust rather than presentation. It
names the subject by study ID and carries no filesystem path, and a test asserts
that: a report leaves the machine, and a path can name a subject or a date. It
escapes all evidence, because evidence is data and not markup. And it turns
`insufficient_channels` into a plain-language note saying those contacts need a
human look rather than a threshold, so the thing the statistics could not do is
visible instead of absent.

Window snippets are capped and downsampled for display. A reviewer has to be able
to open the file.

## 2026-09-04 The QC gate existed only in a docstring

Found by auditing the work rather than by a test failing. `registry.run`'s
docstring claimed a recipe called directly "bypasses provenance and the gate".
There was no gate. `require_approved` and `load_approved` did not exist anywhere
in the package, and every recipe had been running on unreviewed data unchecked
while a comment asserted otherwise.

That is worse than a missing feature. A docstring asserting a safety property
that does not exist is how a reviewer concludes the property is covered.

`qc/gate.py` now derives status rather than storing it: `unreviewed` when
detection has not run, `in_review` while any active flag is undecided, `approved`
when every active flag is decided and a signature covers the exact decisions file
on disk, `reopened` when the signature no longer matches or a reopen is the last
history event.

The signature carries a hash of the decisions file, so editing a decision after
signing invalidates the approval automatically. That is what makes an approval
mean something: it certifies a specific set of judgments, not a subject.

The gate is checked first in `registry.run`, before guardrails and before the run
record is opened, so an unreviewed subject produces no directory, no record, and
no partial output.

A bug the wiring exposed: a clean recording could not be signed. `status` treated
an empty decisions list as `unreviewed`, conflating "detection has not run" with
"detection found nothing". A subject with zero flags has been reviewed and must
be approvable. Now decided by file existence.

Recipe tests go through the real gate rather than disabling it, because the gate
is the property most worth not breaking by accident.

## 2026-09-04 CLI gains qc, and its own exit code for the gate

`python -m dbsspeech qc status | sign | reopen`. Signing refuses while any active
flag is undecided, and names the pending flags.

`run` exits 3 when the gate refuses, distinct from 2 for a guardrail block, and
prints where to look. Without that the gate raised through the CLI as a
traceback, which is a real gap: the first thing a person sees when the most
important check in the system fires should not be a stack trace.

## 2026-09-04 QC review workflow, and thresholds left deliberately wrong

`python -m dbsspeech qc propose | list | approve | status | sign | reopen`.

`propose` runs detection over every included contact, monopolar, writes the
report and the decisions table. QC judges channels as recorded: re-referencing is
an analysis choice, and a bad contact is bad under any montage.

`approve` is scoped and has no `--all`. It requires at least one of
`--flag-type`, `--severity` or `--target`, plus a named reviewer, and offers
`--dry-run`. A bulk decision must state what it covers, so the history shows what
a reviewer actually looked at. That is the difference between bulk approval and
rubber-stamping.

A bug the first real run exposed: `flag_id` hashed only target and type, so two
detectors raising the same concern about the same target collided. Both
peer-comparison detectors report `insufficient_channels` for a group with too few
contacts, and one silently overwrote the other's decision in the merge. The
detector is now part of the identity, with a test asserting ids are unique within
one detection pass.

Two `str.replace` edits silently no-opped during this work, leaving a parser that
accepted new subcommands whose handlers did not exist. Anchored replacements now
assert they matched. A patch that quietly does nothing is worse than one that
fails.

Thresholds were left wrong on purpose. The first full-recording run flagged 258
concerns, 238 of them amplitude windows and 16 of them every channel for
kurtosis, and the honest reading is that two statistics are duration-dependent
rather than that the recording is bad. Retuning until the output looked reasonable
would have produced a QC layer that always passes. The numbers and their cause are
in docs/findings.md, the config says which thresholds are uncalibrated and why,
and the subject stays `in_review`.

## 2026-09-04 Approved QC decisions now take effect, having previously done nothing

Second instance of the same bug class as the missing gate, found the same way.
`registry.run` wrote the approved actions into the run record, and nothing applied
them. A reviewer could approve "exclude lead1:2a" and the recipe would analyze it
anyway, while the record asserted the exclusion had happened.

A record claiming an action that never took effect is worse than a record
claiming nothing, because it is the artifact someone checks when they want to
know what was excluded.

`Session.apply_qc` now applies decisions and returns only what actually took
effect, and that is what the record stores. Three behaviors, deliberately
different:

Channel exclusion drops the contact, and any montage derivation needing it is
dropped too, with a note saying which. That reuses the existing mechanism for an
unavailable contact rather than adding a second path.

Window annotation is carried, never applied. No sample is deleted; the annotation
reaches the recipe, which decides how to treat the span. Never delete is a rule
about the data, not about how QC is recorded.

A notch is recorded as a recommendation and not applied, because filtering is an
analysis decision a recipe makes with its own parameters, not something QC does
to the data on the way past.

An action naming a contact that does not exist takes no effect and is not
reported as applied, so a stale decision from an earlier manifest cannot silently
claim to have removed something.

## 2026-09-04 QC over HTTP, and the review screen

Seven routes under `/qc`, and a two-pane review page: the generated report in an
iframe on the left, the flag table on the right.

The package's rules reach the API rather than being restated there. Rejecting a
flag without a reason returns 422 because `decide` raises, not because the route
checks. Signing with undecided flags returns 409 because `sign` raises. The API
translates exceptions into status codes and does nothing else, which is what
keeps one set of rules rather than two that drift.

Bulk decisions require a scope over HTTP for the same reason they do on the
command line, and the screen only offers "approve all" once a flag type is
selected. There is no approve-everything button anywhere. That is the difference
between bulk review and rubber-stamping, and it is worth the extra click.

The subject list now reports the real gate status rather than the placeholder
`unreviewed` it had been returning, with a test asserting the two agree. A page
showing a status the gate does not agree with is how someone concludes a subject
is reviewed when it is not.

The reviewer name is remembered in local storage, because a review session is
dozens of decisions and retyping a name each time is how people start sharing one
browser tab and losing attribution.

Rejecting prompts for a reason in the browser before sending, rather than letting
the request fail with a 422. The rule is enforced in the package; the interface
just asks the question at the right moment.

## 2026-09-04 bandpower_contrast, and three refusals

The dissertation question in recipe form: are there spectral changes in STN and
GPi during speech and inner speech, and do they differ from movement.

Three things it refuses to do, each a way to get a wrong answer that looks right.

**A p-value it has not earned.** With `unit="window"` there is one observation per
condition, so no test is possible and none is reported: the effect is descriptive
and the row says so. Below five observations per condition the same applies. The
alternative, reporting a p-value from two numbers, is worse than reporting none.

**A p-value that hides its dependence.** With pseudo-epochs there is an n, but the
epochs come from one continuous recording and are not independent, so the
permutation test is anti-conservative. That is stated on every row of the stats
table rather than in a footnote, and `epoch_overlap` defaults to zero because
overlap makes it worse. The summary states that many tests were run with no
multiplicity correction.

**Ratio before average.** Band power is integrated per derivation, contrasts are
formed per derivation, and only then are they averaged. Averaging power first and
taking the ratio after is a different quantity by Jensen's inequality, and not the
one anyone means. Guardrail G3, enforced by the shape of the computation.

Everything is permutation and bootstrap. No parametric tests: trial counts are
small and the distributions are not normal. The permutation shuffles labels
rather than resampling values, which makes it a test of the labelling. A p-value
of exactly zero is impossible by construction, because a finite permutation count
cannot support one.

## 2026-09-04 A band the window cannot resolve is reported, not invented

Found by a test asserting every p-value has a confidence interval beside it. One
row had a p and a NaN interval, which meant a p-value had been computed from NaN
comparisons: a number with nothing behind it.

The cause is scientific rather than numerical. Frequency resolution is one over
the window length, so a 0.2 s epoch gives 5 Hz resolution and the 1 to 4 Hz delta
band contains no frequency bin at all. The recipe was integrating over an empty
mask, producing NaN, and then testing it.

`unresolvable_bands` now reports which bands the chosen window cannot measure and
how long a window would be needed. Non-finite observations are dropped before any
statistic is computed, and a contrast with nothing measurable is recorded as
unmeasurable rather than given an effect.

Worth stating because it generalizes: a band narrower than the frequency
resolution cannot be measured however long the recording is. More data does not
fix a window that is too short.

## 2026-09-04 Compare, and the two things that quietly invalidate one

`/compare?a=&b=` and a page for it. Parameters that differ are highlighted,
figures are matched by filename so the same panel sits beside itself, and the
claims are shown together.

Two warnings the page raises that a parameter diff alone would hide. If the two
runs used different recipes it is not a like-for-like comparison. If they used
different git commits, the difference may be the code rather than the settings,
which is the failure mode that makes "we changed one parameter" wrong. A run from
a dirty tree is flagged too, since its code is in no commit and cannot be
recovered.

`/runs/{id}/tables/{name}` pages a table so a large CSV does not have to load
whole, with the same containment check the file route uses: the resolved path
must stay inside the run directory.

## 2026-09-04 Slash commands, deliberately unable to approve or override

Five commands in `.claude/commands/`: `/status`, `/qc`, `/run`, `/findings`,
`/compare`. They call the package CLI, so a run started from a slash command is
the same run with the same gate, guardrails and record.

Two limits written into the command text rather than left to judgment. `/qc` runs
detection and summarizes what needs deciding, and is told not to approve
anything: approving is Garrett's decision and a bulk approval has to state its
scope. `/run` is told never to add an override unless he asked in that message,
and never to invent the reason. An override whose reason was written by the thing
being overridden is not a record of judgment.

`/run` also explains the exit codes, because 3 (the QC gate refusing unreviewed
data) and 2 (a blocking guardrail) need different responses and are easy to
confuse.

## 2026-09-06 All thirteen guardrails implemented, and the gap closed

Five were documented and configured but never ran: G3 ratio before average, G4
thresholds across conditions, G7 EMG contamination, G9 non-stationarity, G13 path
policy. Eight of thirteen firing while the docs described thirteen is the same
gap that produced the missing gate and the unapplied QC decisions, so a test now
asserts every guardrail documented in `docs/guardrails.md` is registered in code.

G3 and G13 are not overridable. Jensen's inequality is arithmetic, and a raw path
in a derivative at a site that has not declared its filenames safe is not a
judgment call.

Implementing G7 immediately fired on the existing test fixture, which was correct
and worth keeping. The fixture described a run requesting high gamma during overt
speech with no EMG regression, which is exactly the contamination G7 exists to
catch. The fixture now describes a run that already did the right thing, bipolar
with EMG regressed, rather than one that was never asked.

Three tests were over-asserting. They checked G1's behavior by asserting nothing
at all fired, so implementing a second, unrelated check broke them. They now
assert about G1 specifically, plus a new test that monopolar during speech trips
both G1 and G7, because those are two different real concerns and both should
fire.

The recipes supply the new context from one shared helper rather than each
declaring it separately, so the two cannot drift on what they claim about
themselves. A guardrail checking a claim the recipe got wrong is worse than no
guardrail.

## 2026-09-06 tfr_onset, and what "onset" means without markers

Spectral contrasts average over a whole window; speech has onset, sustained
production and offset. This is the recipe that shows them, and the groundwork for
the word-level resolution the PI asked for.

Onset needs stating because it is not the usual thing. There are no task markers
in these recordings, so onset is the start of a condition window from
`manifest/windows.csv`. The provenance of each window travels with the result in
`window_provenance.csv`, so a reader can see whether an onset was measured from a
microphone envelope or assumed. Guardrail G10 flags the assumed ones, and the
summary carries a note saying what onset means here rather than leaving it to be
inferred.

Two failure modes avoided by construction rather than by care.

Edge artifacts: a wavelet needs signal either side of the time it reports, so the
read is padded by the longest wavelet's half-length and cropped afterwards. No
reported time-frequency point was computed from data that was not there, and a
test asserts the map spans exactly the requested range.

Memory: a full-resolution TFR of every channel at once is large. Channels are
processed one at a time and averaged as they go, so peak memory is one channel's
map rather than the whole array.

`references` defaults to the primary montage alone rather than all five, unlike
the other recipes. TFR is expensive and computing five montages multiplies the
cost for a comparison that band power already provides more cheaply.

Full-resolution maps go to netCDF as a labelled array, with a Parquet fallback
when no netCDF backend is installed, because a missing optional backend should
not lose a result. The tidy table is decimated in frequency so it stays openable.

## 2026-09-07 pynm_features, written against the installed package

Their feature set is standardized and published, so using it as a library gives
those features without maintaining them and makes outputs comparable to other
labs' work. Inspected version 0.1.7 rather than writing from memory, as the guide
insists, and three findings shaped the wrapper.

**Their re-referencing has to be switched off.** The channels frame's
`rereference` column defaults to a common average. We apply our own montage
before handing the data over, so leaving their default would re-reference
already-referenced data. Silent, and wrong. It accepts the string `"None"`, and
the run record states that it was disabled and why.

**Their bands can be driven from ours.** `settings.frequency_ranges_hz` is a
plain dict of `FrequencyRange`, so `configs/bands.yaml` replaces their four
defaults. Config over code survives the boundary into another library rather than
stopping at it.

**Their `time` column is milliseconds.** Measured, not assumed: 4000 for a four
second recording. The first implementation guessed the unit from a magic
threshold, which silently labelled every feature row with no condition at all.
The unit is now checked against the recording length, and an unrecognizable span
raises rather than guessing, because a wrong unit mislabels every row and nothing
about the output looks wrong.

Their heavier features are off unless named: fooof, nolds, bispectrum, coherence,
mne_connectivity. They are slow, several need more channels than a lead has, and
none is calibrated for this data. Naming a feature enables exactly that set, and
an unknown name lists what is available.

Their version goes in the summary, because a feature set is only comparable if
you know which version produced it, and their exact settings are written out so a
run can be reproduced against it.

## 2026-09-07 Accounts, and the guard that matters more than the passwords

Local accounts with argon2id hashing, three ordered roles (reviewer, analyst,
admin) so a check reads as "at least this role", and session tokens in
`var/app.db`.

`var/` rather than `derivatives/`, which is where the guide put it. Everything in
`derivatives/` is regenerable and git-ignored, and accounts are neither: losing
them is not "re-run the pipeline", it is every past decision's attribution
pointing at nothing.

**The bind guard is the part that matters.** `serve` refuses any host but
localhost while authentication is disabled. The realistic failure here is not a
weak password; it is someone passing `--host 0.0.0.0` to see the app from another
machine and leaving an unauthenticated interface answering on a hospital network.
That is now impossible without deliberately setting `DBSSPEECH_REQUIRE_AUTH`.

Auth defaults to off so single-user local work is unchanged, and every request
then runs as a notional `local` admin. The code path is the same either way, so
the authenticated path is not a rarely-exercised branch.

Smaller decisions, each with a reason:

Login returns the same error for an unknown email and a wrong password, because a
different message tells an attacker which addresses exist. Attribution on a run
comes from the session rather than a field the caller filled in. Users are
disabled, never deleted, since deleting one orphans every decision they signed.
Passwords are prompted for and never taken as command-line arguments, which would
put them in shell history and in `ps` output. There is no self-service reset; an
admin resets from the command line, as the guide specifies.

Ruff's B008 was exempted for `fastapi.Depends`, `fastapi.File` and `require_role`
only. Those are the framework's own idiom, evaluated once at import, so the
mutable-default hazard the rule exists for does not apply. Nothing else is
exempted.

## 2026-09-07 Config admin, and what a config change must not do

Config over code only helps if a non-coder can change config, which means editing
from the interface. That needs three things the file system does not give you.

**Validation before a bad value reaches a run.** Each config has a checker that
says what is wrong rather than failing generically: a band with its edges
inverted, a guardrail severity that is not a severity, a QC detector with no
proposed action, a statistics option missing the caveat that gets shown beside
it. An invalid write changes nothing at all.

The guardrail checker does one thing worth naming: it refuses a config that has
dropped a guardrail the code implements, because an absent guardrail silently
stops running. Disabling one has to be `severity: off`, which is visible.

**History, with who and why.** Every save archives the previous contents with an
author and a reason. A threshold with no rationale is the thing nobody can defend
six months later, so `write_config` refuses without one.

Versions live in `var/config_history/`, not git. A config edit from a browser
should not create a commit in the analyst's working tree: that entangles a
threshold change with whatever code is half-written at the time and makes
`git status` misrepresent what they were doing.

**A guarantee that the past is not rewritten.** Editing a threshold does not
retroactively change an approved subject. An approval certifies the judgments
made against the numbers as they were, so new values apply to future runs and
future QC proposals only. The write response says this in words the interface can
show, rather than leaving each interface to invent the wording.

`leads.yaml` and `privacy.yaml` are deliberately not editable here. One is a
device catalogue and the other governs what may leave the machine; neither should
change from a browser.

## 2026-09-07 Export bundles, and a README that answers the real question

A figure pasted into a slide loses everything that made it defensible. A bundle
carries the figures, the tables, the run record, the config as it was, and a
README readable without this software.

The README is the point. Six months on the question is not "where is the file",
it is "what was this, who ran it, against which code, and what did the checks
say". So it carries the claim, the author, the commit, every guardrail that fired,
every override with the reason given, what QC actually removed, the normalization
in words, the inputs as manifest keys and hashes rather than paths, and library
versions. A run from a dirty tree gets an explicit warning that its code is in no
commit and the result is provisional.

The config in a bundle is the snapshot that ran, not the current file. A bundle
picking up today's thresholds would misrepresent what produced the result. When a
run predates snapshotting, the current configs are included with a note saying
they may differ.

## 2026-09-08 Runs execute in a worker, and the queue is a table

Runs used to execute in FastAPI's `BackgroundTasks`, inside the web process.
That is fine for one person on one machine and wrong for anything deployed: a
run dies silently when the API restarts and nothing records that it started, its
status lives in a dictionary no other process can read, and one long analysis
competes with every HTTP request in the same interpreter.

**SQLite, not Redis or RQ.** The deployment target is one lab machine. A broker
is a second service to install, back up, restore, and explain to whoever
inherits this, in exchange for throughput nobody here needs. The queue is two
tables in `derivatives/runs.db`, beside the run index. Claiming is one
conditional UPDATE inside an IMMEDIATE transaction, which is what makes it
impossible for two workers to take the same job, and there is a test that runs
ten threads at five jobs to say so.

Ordering ties break on rowid, not on the job id. Timestamps have one-second
resolution and a job id ends in random hex, so two runs submitted in the same
second would otherwise execute in arbitrary order. That was a real bug, found by
the test that asserts first-in-first-out.

**A stale job fails; it is not retried.** When a worker dies partway through a
recipe it may have left half-written output. Re-running automatically would hide
that: the analyst would see one result and no sign that a first attempt ended in
the middle of writing. The job is failed with a message that says the output may
be partial and that re-running is a decision for someone who can look at what is
on disk.

**`queue` is the default and `background` survives as a setting.** Working alone
on one machine with no worker running is a reasonable way to work, and removing
it would push people toward starting a worker they forget to stop. It is honest
about itself: the response says the run will not survive a restart. `scripts/dev.sh`
now starts a worker alongside the API, so the default path needs no second
terminal.

**Health reports and never repairs.** Reaping stale jobs happens in the worker
loop, not in `/health`. A monitoring endpoint that changes state gives you a
system whose behavior depends on who last looked at it. The cost is that a job
belonging to a worker that died stays `running` until a worker starts again,
which is also the moment anyone can act on it. That is in `docs/backlog.md`.

## 2026-09-08 What containerizing broke, and what it took to not break it

Three things that were true in a working tree stop being true in an image.

**No `.git`, so no provenance.** Run records read the commit with
`git rev-parse`, which answers nothing inside a container. Every containerized
run would have recorded no commit, and every bundle README would have called the
result provisional. The build now stamps the commit into the environment and the
record falls back to it. A working tree still wins, because it is the answer that
can be wrong in the interesting way: dirty.

**`configs/` cannot be image content.** The config admin screen writes to
`configs/*.yaml`. Baked into the image, an edit made in the browser would work,
persist for the life of the container, and vanish on the next rebuild. It is a
mounted directory. `manifest/` is mounted for the same reason, since its rows
are edited by hand.

**`data/` is mounted read-only, so uploads cannot live under it.** The local
default puts uploads in `data/uploads`. In a container that directory is on a
read-only mount, deliberately, so the deployment puts them under `var/`.

The API also serves the built front end, which means one origin and one port and
no CORS surface at all. The front end's API base had to become empty in a
production build, since the `/api` prefix exists only for the Vite dev proxy.
That failure would have been silent: every call 404s against index.html.

**The web app is built in the image, not committed.** A committed `dist/` drifts
from the source that produced it and nobody notices until a screen behaves like
last month's code.

## 2026-09-08 Backups, and two bugs that only testing found

`scripts/backup.sh` covers `runs/`, `derivatives/`, `var/`, `configs/`, and
`manifest/`. Not `data/`: the recordings are large, read-only, and backed up
where they live, and a backup that takes an hour is a backup nobody runs.

The databases are snapshotted with `sqlite3 .backup` rather than copied, because
a plain copy of a database being written to is a corrupt database and this runs
from cron while a worker may be finishing a run.

Two bugs, both found by running it rather than reading it:

The retention loop failed under `set -e` when there was nothing to delete, so
every backup on a fresh destination exited non-zero. A nightly cron job that
always reports failure is a cron job whose failures stop being read.

Worse: `tar --exclude` applies to every member regardless of which `-C` it came
from, so excluding the live databases also excluded the snapshots being added
back under the same names. The archive was silently missing both databases. It
is now two passes into an uncompressed archive, appending the snapshots, then
gzip, which keeps a restore to a single untar with no files to move afterward.
A restore round trip has been run once, and the integrity check passes.

## 2026-09-08 ERNA without a definition to copy

The build guide says not to guess this lab's ERNA definition, and to stop and ask
the PI for the window and blanking convention. Garrett's instruction changes the
shape of the step rather than skipping it: the recipe does not need to produce a
number out of the box, it needs the capability to be there with parameters any
neuroscientist can set for their own protocol.

So nothing is encoded as the method. ERNA is defined by a stimulation protocol,
and protocols differ in pulse rate, burst length, burst spacing, amplifier
blanking, and what counts as the response window. Every number that shapes the
answer is a run parameter, defaulting to `configs/erna.yaml`, and the resolved
value of each is written into the run record beside where it came from: "run
parameter" or "configs/erna.yaml:window.blanking_ms". Six months on that is the
difference between a reproducible result and a puzzle.

**Parameters default to None rather than to a number.** A default written into
the parameter model would be a convention this code invented, and it would travel
into results with nobody having chosen it. None means "take it from the config",
where the value sits next to a paragraph saying what it does.

**`defaults_reviewed` is false and the recipe says so, everywhere.** In the
summary, in the run record, and printed on the figure. Setting it to true
requires naming who reviewed it; the config checker refuses the flag without a
name. A number produced under unreviewed defaults is a number about this
software, not about a brain, and it should be impossible to paste it into a slide
without that following it.

**Three sources for stimulation events**, none assumed: the artifact in the
signal itself, condition windows from the manifest, or an epoch store in the
recording. Labs that log stimulation and labs that do not both have a path.

**Only the evenly spaced leading run of extrema is measured.** This was found by
testing rather than by design. Taking every extremum in the analysis window let
the noise after the ringing into both estimates: the frequency came out 14
percent low, and the decay constant came out 21 ms against a planted 12 ms,
because the envelope flattens at the noise floor and a flat envelope fits as a
long time constant. Ringing is evenly spaced and noise is not, so the run stops
at the first interval that breaks the spacing, with the tolerance a parameter.
The frequency confirmation by FFT is likewise taken over the span the resonance
occupies rather than over the whole window.

**Guardrail G2 is reported as not applicable, not as false.** G2 blocks a
per-contact comparison that has not subtracted a per-contact baseline, because
otherwise it measures which contact sits best rather than what the brain is
doing. An evoked response is measured inside each derivation's own
post-stimulus window; there is no cross-condition contrast for a baseline
condition to correct, and which contact resonates is the question ERNA is asked
rather than a confound. That reasoning is written where the value is set, and
one line reverses it: set the field to False and every ERNA run needs an
explicit override with a reason.

**Validation.** The fixture plants a damped 250 Hz oscillation with a 12 ms decay
constant after each of seven stimulation artifacts, on two contacts. The recipe
recovers 254 Hz by peak spacing and 250 Hz by FFT, and a decay constant of
11.0 ms. The guide asks for 10 percent and 25 percent; this is 1.6 and 8.3. The
stimulation content is off by default, because every other test asserts on a
recording with no stimulation in it, and the ERNA fixture is built at 8 kHz
because eight samples per cycle quantizes peak times enough to move a frequency
estimate past what a test should tolerate. An ERNA recording is sampled fast for
that reason; loosening the assertion instead would have hidden it.

None of this has met a real stimulation recording. It cannot until the first subject analyzed clears
QC, and the numbers it produces then still need someone who knows the protocol to
set the parameters first.

## 2026-09-08 The demo, and what building it exposed

`python -m dbsspeech seed` writes a synthetic subject into a demo root, takes it
through the real QC review, and runs every registered recipe. Adoption is decided
in the first ten minutes, and the first ten minutes cannot depend on a subject
clearing QC review.

**It goes through the gate rather than around it.** Nothing here sets
`enforce_gate` false. What a new person sees is the workflow they will use, and
every approval in the demo is attributable to a reviewer named `demo`, who is
obviously not a person.

**It does not blanket-approve, because blanket approval is the wrong answer and
the demo would be teaching it.** Detection flags the two stimulating contacts as
kurtosis outliers, correctly, and proposes excluding them. Approving that
proposal deletes the ERNA. They are approved as real with the action changed to
`none` and a reason, which is also the path a reviewer takes when they disagree
with a proposal. The first version of the seed did blanket-approve, and the ERNA
recipe then found nothing on a recording full of stimulation. That is the most
useful thing the demo teaches, so it is now what the demo shows.

**The fixture generator moved into the package**, as `dbsspeech.demo_data`. A
shipped command cannot import from `tests/`: an installed package does not have
it, and neither does the container image. `tests/fixtures/make_tdt_fixture.py`
re-exports it so the recipe tests did not all have to change in the same commit.

**`DBSSPEECH_MANIFEST` now overrides the manifest directory.** Every other path
was already overridable, and without this one the demo project is a set of
recordings whose subjects are absent from the manifest being read.

**One real bug, found by the demo rather than by a test.** `tfr_onset` crashed
with "All arrays must be of the same length" when a condition window sat close
enough to the start of the recording that the requested pre-onset period did not
exist: its map came out shorter and could not be stacked with the others. Those
windows are now skipped, with a line saying which and why, at both ends of the
recording. Shortening them instead would have been worse: a map covering a
different time range is not comparable to the others, and averaging it in makes
the baseline mean one thing for some conditions and another for the rest.

## 2026-09-08 Documentation that cannot go stale, and errors that say what to do

`docs/recipes.md` is generated from the registry by `scripts/gen_recipe_docs.py`,
and a test fails when the file on disk is not what the generator produces. A
hand-maintained parameter list is wrong within a month and nobody can tell which
half is wrong. The prose pages are hand-written, because a generator has nothing
to say about why the QC gate exists.

`docs/troubleshooting.md` contains only errors that have actually happened, with
dates. An invented troubleshooting guide sends people down paths nobody has
walked, and the two entries added on the day this was written both came from
running something rather than reading it.

API errors are mapped in one place, `api/errors.py`, keyed by exception name
rather than by class, because a job failure arrives from another process as text
and the name is all there is. Each entry answers two questions: what happened,
and what to do next. The technical text is kept beside the friendly message
rather than replacing it, since someone will paste it into a message asking for
help.

In-app help is one component keyed by route rather than a paragraph inside each
page, so the wording stays consistent with `docs/concepts.md` and a new page
cannot quietly ship without any. Collapsed by default: help that must be
dismissed on every visit stops being read.

## 2026-09-08 The design pass, done without the screenshots

The guide asks for three reference screenshots before this step. Garrett chose to
go with the direction the guide already states rather than wait, so the direction
is the one written into `web/DESIGN.md`: a well-made lab instrument, not a
marketing site, with the result reviewable and correctable afterwards.

Three rules, and the rest follows from them. Density is a feature, because a
scientist comparing eight contacts wants them in one view and generous whitespace
is just scrolling. Color means something or it is not used, so there is one
accent and the status colors are reserved for status. Nothing decorative competes
with data: no shadows, no gradients, no animation beyond a focus ring.

**Tokens, not palette values.** Every color, size and space is defined once in
`src/index.css` under Tailwind's `@theme`, and pages use the role. `text-muted`
rather than `text-stone-500` means the decision lives in one file, and it makes
the eventual dark mode a second value per token rather than a search through
every screen. The five type sizes are a deliberate ceiling; wanting a sixth is a
signal that the layout is wrong.

Teal for the accent rather than blue, because blue reads as a hyperlink and
because the status colors need the cool end of the range left alone.

**One table.** Every screen had been writing its own `<table>`, with its own
header styling and its own idea of how a numeric column aligns, which is how two
screens end up disagreeing about what a run id looks like. `DataTable` sorts
client side on purpose: these are tens of rows, and a server round trip to sort a
list already on screen is worse than no sorting.

**The screen title moved out of the pages** and into one route-keyed header, so a
page cannot invent its own heading style and the nav label and the title cannot
drift apart. Same reasoning as the help panel, which was already built that way.

**`statusTone` is one function.** Two pages had their own copy of the mapping
from a status word to a color, and they had already diverged on what `queued`
looks like. A color that means one thing on one screen and another elsewhere is
worse than no color.

The tone helpers live in `ui/tones.ts` rather than beside the components, because
a module exporting both components and plain functions loses fast refresh in
development. The lint rule that says so was worth listening to.

Not done: dark mode, which needs a second value for every token and a check of
the status colors against a dark ground, and which nobody has asked for. And no
behavior changed here. Nothing was added, no route moved, and the only page whose
markup changed structurally is the run log, which now composes the shared table.

## 2026-09-08 A BrainVision reader written twice, and the one that was kept

Two sessions were working this repository at the same time without seeing each
other, and both wrote a BrainVision reader on the same afternoon. This one was
reverted, in the commit that follows it.

The other is better and it is worth saying why, because the reasons are the ones
to reach for next time. It factors an `MneRecording` base that BrainVision and
EDF both use, so the second MNE-backed format cost almost nothing. It taught
`register_reader` about entry suffixes rather than leaving the loader with a
hard-coded table of format to extension. Its sniffer accepts a directory holding
one header, which is how a block actually arrives. And it says out loud that a
BrainVision header cannot be triaged without its `.eeg`, unlike a TDT tank,
which is the sort of thing you only write down after being bitten.

Both restricted `meas_date` for the same reason, independently: for these
formats the amplifier's clock is a surgery date. Two people reaching that
separately is the best evidence yet that the rule is the right one.

One thing the reverted work had that the surviving one does not: a test taking a
BrainVision recording through the loader, the manifest and a montage, rather than
testing the reader alone. That is in `docs/backlog.md` to port.

The process lesson is larger than the file. Two agents on one checkout, neither
able to see the other's uncommitted work, will duplicate whatever is next on the
shared list. A branch that is not visible to the other worker is not coordination.

## 2026-09-08 A run flow for a first run, with the agent doing the work

Garrett's judgement on the interface: not usable by a PhD student doing one of
his first runs, and the run-and-parameters path needs rewriting for that person.
He also asked that the agent be used as far as it usefully can be.

What was wrong is worth recording, because it is what any replacement has to
avoid. Recipes were listed by function name, so choosing one required already
knowing what `psd_by_condition` does. Subjects were listed as `<study_id>/<session>`
with no QC state, so the first sign that a subject was unreviewed was a failed
run. Every parameter appeared at once in a flat grid labelled with the Python
field names, twelve for PSD and twenty for ERNA, with nothing to say that two of
them decide the answer and the rest have defensible defaults. The claim was one
input among three. And nothing said what would happen until after the button, so
a beginner's first meeting with a guardrail was a red box saying it had refused.

**Four steps, one decision each.** Subject, question, settings, check. A subject
that has not cleared QC cannot be selected and says why on its own row rather
than failing minutes later. The question step takes ordinary words. The settings
step shows only what the recipe called essential, with the rest one button away.
The check step says what will run, what it will produce, which method checks
fired, and asks for the claim.

**The agent is the engine of three of those four steps**, which is what makes the
flow possible rather than merely prettier. It chooses the recipe by matching the
question against the sentences each recipe ships with, and says what it matched
on. It explains each value it set, shown against the field it set. It re-checks
values as they are edited and dry-runs the guardrails against them. So the last
screen before the button describes the run about to happen, and a block is read
beforehand rather than discovered afterwards.

Everything the flow says comes from the server: the labels, the reasons, the
caveats, the refusals. A component that invented any of them would be a second
place where the science is described, and the two would drift.

**The one-page version was considered and rejected.** It was cheaper and it kept
the property that makes the current screen hard: it opens showing everything.
Leaning on Ask instead was also considered, and is effectively what happened,
except that Ask is now inside the flow rather than beside it. A proposal you have
to carry to another screen by hand is a proposal most people will not use.

A bug fell out of the rewrite: `Ask` hard-coded `<study_id>/<session>` as the subject it
proposed against, so its answers described a recording nobody had chosen. It now
asks without a subject, and the run flow asks again once one is picked.

**Never infer a default.** The first version re-inferred a value for a field
somebody had emptied, on the reasoning that the agent's guess was a sensible
default. Garrett's ruling, and he is right: emptying a field is a decision, and
an assistant that helpfully fills it back in has overruled it. Cleared fields are
now tracked separately from unset ones and travel to the agent as their own list,
because "never set" and "set, then removed" have to mean different things. The
field stays empty and the recipe's own default applies, which is what the person
asked for.

The rest of the agent already worked this way, which is worth noting: where it
has no evidence for a value it asks a question rather than filling one in. The
clearing case was the one place it decided something on nobody's behalf.

## 2026-09-09 The review screen could not express the decision that matters most

Found while looking at QC with the same eye as the run flow. A flag asks two
questions, and they are separate: is the observation real, and what should be
done about it. The screen offered Approve and Reject, and approving silently
accepted whatever detection proposed. So the most important review decision in
this project could not be made in the browser at all.

The case that proves it is the one the demo teaches. A stimulating contact is
genuinely spiky; excluding it deletes the signal the recording was made for. The
right answer is to approve the flag and take no action, with a reason. `seed`
does exactly that in Python, and a reviewer in the interface could not.

Now each flag offers the proposed action, every other declared action, and
`none`, with a reason required whenever the action differs from the proposal.
Rejection also lives there, described as "detection was wrong", which is what
rejecting means and is different from disagreeing about the remedy.

**The words come from `configs/qc_thresholds.yaml`.** Every detector carries a
plain-language `label` and a `means` sentence, and there is an `actions` block
saying what each choice does. The config checker refuses a detector without
them, refuses a proposed action that is not declared, and refuses a config with
no `none` action, because dropping it would quietly remove the ability to keep a
contact. These are decisions about data, so the words somebody reads while
deciding belong in a file with an author and a reason rather than in a component.

Two smaller things went with it. Evidence was a raw `key=value, key=value`
string; it is now shown as pairs, with the numbers in a monospace column. And
the reason for a rejection was collected with `window.prompt`, which is
unstyled, loses what you typed if you mis-click, and cannot be reviewed before
sending. It is an ordinary field now.

## 2026-09-09 The API moves under /api so it stops shadowing the app

The single-page app was mounted on the same FastAPI instance that serves the API,
with the SPA fallback catching whatever the API did not claim. That works only
while the two never want the same path, and they wanted four of them. `/subjects`,
`/runs`, `/runs/<id>` and `/qc/<id>` are all real screens and all real endpoints,
and the API won every one: opening the Subjects screen returned a page of JSON.
Half the interface was unreachable in a deployment and every test still passed,
because the tests asked the API app for API paths and got them.

The fix is a root application that mounts the API at `/api` and the app at `/`.
Nothing about the API changes except its prefix, the browser still talks to one
origin, and the collision cannot recur: a screen and an endpoint no longer share
a namespace. The dev proxy drops its rewrite for the same reason, so the path that
works in development is the path that works in a container.

The reason this survived so long is worth recording. It is invisible to unit
tests, invisible to `curl /api/...`, and invisible to reading the code. It was
found by taking a screenshot of the running app.

## 2026-09-09 Flag vocabulary lives in the config, including the non-detectors

`insufficient_channels` is not a detector. The peer-comparison detectors raise it
when a group is too small to support an outlier statistic, so it carries no
threshold and proposes no action. It also had no entry in `qc_thresholds.yaml`,
and the review screen falls back to the raw type name when a flag has no entry,
which is how a reviewer met it as the literal string `insufficient_channels` next
to a flag that offered to "do the proposed thing" that did not exist.

`flag_types:` now sits beside `detectors:` for exactly these, and `/qc/vocabulary`
merges the two. A flag type with no words a person can read is a bug in the
config, not something the interface should paper over with a guess.

## 2026-09-09 The recipe chooser weights words by rarity, not by length

Asked "does beta power change during overt speech compared to rest", the chooser
returned `tfr_onset`. It scored a shared word by its length, so "change" (six
letters) outweighed "beta" (four) and the time-frequency recipe beat the band
contrast, 11 to 9. Length was never a measure of anything; it was standing in for
informativeness and getting it backwards.

Inverse document frequency asks the question that was meant all along: how much
does this word narrow the field. "power" appears in three of five recipes and is
now worth almost nothing, "beta" appears in one and is close to decisive. The
property that mattered is kept: nothing is hard-coded per recipe, the weights
fall out of whatever recipes are registered, and a recipe added tomorrow is still
matched on the sentence its author wrote.

A plural is folded onto its singular on both sides, because "is high gamma
different between conditions" previously matched nothing at all and fell back to
the default while reporting that it had understood nothing. That is a fair report
of a bad outcome, but the outcome was avoidable.

The reason string now leads with the word that carried the most weight, so
"matched on beta, power" reads as an explanation rather than a list.

## 2026-09-09 Every recipe declares its labels and its essential parameters

`tfr_onset` and `pynm_features` had neither, and the form is built from them. A
student who asked about speech onset was shown fourteen fields at once, titled
from the field names by a regular expression: "Sfreq Target Hz", "N Cycles
Factor", "Fmin", "Decim". All fourteen have defensible defaults, so the screen
was asking someone to review thirteen decisions that had already been made for
them, in a vocabulary they would have to reverse-engineer.

With `LABELS` and `ESSENTIAL` declared, the same screen shows six named settings
and a button offering the other ten. Both fields are optional by design and the
form falls back to showing everything, which is the right fallback and also the
reason two recipes sat in it unnoticed. A recipe that declares neither is now the
exception rather than a silent default.

## 2026-09-09 The question box answers the Enter key

Typing a question and pressing Enter did nothing: the flow advanced only from a
button below the box. A person who presses Enter and sees no response has learned
that the box does not work, not that they should look further down the page. The
example questions had the same shape of problem in a smaller way, filling the box
and requiring a second click to ask what had just been chosen.

One function now decides a recipe, reached three ways: the button, Enter without
Shift, and clicking an example. Because an example sets the question and asks in
the same click, the text travels with the call rather than being read back from
React state that has not updated yet.
## 2026-09-08 BrainVision and EDF readers, and one shared MNE base

`brainvision` was declared in `api/main.py:UPLOAD_SUFFIXES` from the start but no
reader was ever registered, so opening one raised `unknown format 'brainvision'`.
That gap was invisible while `the first subject analyzed` was the only subject, because it is a TDT
tank. It stopped being invisible once the Box archive was inventoried: across the
29 study IDs staged locally, 31 blocks fail to open on exactly this, and
BrainVision holds most of the recording volume in the program.

Both formats are read through MNE, `mne.io.read_raw_brainvision` and
`mne.io.read_raw_edf`, always with `preload=False`. They differ only in the
loader and the sniffer, so the shared behavior lives in `io/_mne_base.py` and
each format contributes about sixty lines. EDF is included alongside BrainVision
because it is what a site with different hardware exports, and supporting it is
most of what "usable outside this lab" means in practice.

Three choices inside that base are worth recording.

**Streams are channel types.** These formats hold one recording at one sampling
rate, not several streams the way a TDT block does. Channels are grouped by the
type MNE reports, so a file distinguishing `eeg` from `emg` yields two streams
and a file typing everything the same yields one. Grouping is by what the file
declares and never by pattern-matching a channel name, because a guess here
would silently change which channels an analysis averages over. A stream's
`role` remains a manifest judgment.

**Channel order is fixed in numpy, not in MNE.** `read` asks MNE for the
stream's channels in file order and reorders afterwards. Handing MNE a reordered
or repeated pick list is not guaranteed to come back in the order given, and a
silently permuted channel axis is the worst failure this layer could have: every
number downstream stays plausible.

**`meas_date` is restricted for these formats, unlike `tdt_mat`.** The exemption
in `configs/privacy.yaml` rests on TDT filename timestamps being upload times,
deliberately separated from the procedure. An MNE `meas_date` is the amplifier's
acquisition timestamp, from which a surgery date follows directly, so the
conservative default applies and a site removes the line if it disagrees.

BIDS is deliberately not included. `mne_bids.read_raw_bids` addresses a recording
by entities (root, subject, session, task, run, datatype) rather than by a path,
and `subjects.csv:root_relpath` cannot express that. Adding it means a manifest
schema change, which is a bigger decision than a reader and is left to be taken
on its own.

The EDF test fixture is written byte by byte in `tests/fixtures/make_edf_fixture.py`
rather than exported, because MNE's EDF export needs `edfio`, which is not
installed, and adding a dependency so a test can produce four hundred bytes of
header is a poor trade. The BrainVision fixture uses `pybv`, which is already a
dependency.

## 2026-09-08 filenames_deidentified is declared per format

Staging the Box archive surfaced 58 files named
`BRAINaim1_date_<YYYYMMDD> time_<HHMM> ...`, an acquisition date and time in the
filename. `configs/privacy.yaml` declared `filenames_deidentified: true` for the
whole site, and the comment justifying it is specific to TDT: acquisition
filenames carry the study ID and the block name, and the embedded timestamp is
the upload time, deliberately recorded on a day separated from the procedure.
That reasoning is sound and does not extend to BrainVision or EDF.

The setting is now either a boolean, which still applies to every format, or a
mapping of format to boolean. A format absent from the mapping resolves to
false, so registering a reader never silently opts its filenames in. Shipped
values: `tdt_mat` and `tdt_tank` true, `brainvision` and `edf` false.

Resolution lives in one function, `io.base.filenames_deidentified_for`, and both
readers of the setting call it. That matters more than it looks. The setting
gates guardrail G13, which refuses to write a raw path into a derivative and is
`overridable=False`. `recipes/psd.py` had been computing it as
`bool(privacy.get("filenames_deidentified", False))`, reading the raw config
value rather than going through `PrivacyPolicy`. Against a per-format mapping
that expression evaluates to True, because a non-empty dict is truthy, which
would have handed G13 a blanket pass for every format at once. A safety check
quietly succeeding is the worst available failure, so the duplicate spelling was
removed rather than fixed in place, and `tests/unit/test_privacy_policy.py`
asserts the difference directly.

Nothing had leaked: the draft manifests generated from the staged archive
contain no date-like strings, and the MNE-backed readers withhold `meas_date`
independently of this flag.

## 2026-09-08 Paradigm terms move from Python into the vocabulary

The agent special-cased one word. `agent/propose.py` matched a question against
the session's condition names and then, separately, mapped the literal string
"speech" to the condition `overt`. Every other paradigm had no equivalent, so a
motor or cognitive lab got name-only matching and no way to fix it without
editing the module.

Conditions in `configs/vocabularies.yaml` now carry `aliases`, and the agent
builds its match table from them. Matching is longest-phrase-first, so "imagined
speech" resolves to `inner` rather than being swallowed by the `speech` alias of
`overt`. An alias is eligible only when the session actually has windows for
that condition, so the vocabulary can never propose something unanalyzable. The
terse `{label, description}` entry shape is still valid.

Vocabulary was added for movement, motor imagery, sensory cue, cognitive task,
and stimulation on and off. Listing a condition does not create it: a condition
is analyzable only where `windows.csv` defines a window, so entries no lab has
used cost nothing.

`G11_motor_control_missing` became `G11_control_condition_missing` and now reads
a `rules` list, one entry per confound, each naming what it applies to, what
would satisfy it, and the sentence the reviewer sees. Four rules ship: speech
needs a movement control, movement needs a resting baseline, a cognitive task
needs rest or the cue alone, and stimulation-on needs stimulation-off. All
firing rules are reported in one finding rather than the first only, because
surfacing one confound per review cycle is the wrong number of cycles.

Two compatibility notes. The old flat spelling, `applies_to_conditions` and
`satisfying_conditions` at the top level, is still read as a single rule, so a
config that has not been updated is not silently disarmed, and there is a test
for exactly that. The rename does break a name: five run records in `runs/`
list `G11_motor_control_missing` under `checks_run`. They are the smoke-test
records `docs/build-status.md` already offers to delete, and the alternative was
keeping an id that says "motor control" on a check that also enforces resting
baselines and stimulation contrasts, which would mislead every future reader of
a run record.

Not done here: the ERP, phase-amplitude coupling, and aperiodic recipes from the
same section. Each is roughly the size of an existing recipe, about 400 lines
plus 200 of tests, and two of them need a dependency decision that changes what
a number means. `specparam` is not installed and `fooof` 1.1.1 is, but announces
its own deprecation on import; `pactools` is not installed and the modulation
index would otherwise be hand-rolled against the guidance to prefer library DSP.
Those are decisions to take deliberately rather than inside a large diff.

## 2026-09-08 Windows proposed from task markers, and what a window is not

Every window in `windows.csv` was derived by hand from a microphone envelope,
because the recordings this project started with carry no task markers. The
BrainVision and EDF readers changed that: those formats bring their own
triggers, and `Recording.epochs` already returns one series per marker label.

`detect/windows.py` turns bindings declared in `configs/markers.yaml` into
proposed rows, with `derived_from: task_marker` and `status: draft`. It writes
nothing. `python -m dbsspeech windows <path> <study_id> <session>` prints the
proposals for review and `--csv` emits rows to paste. A proposal that entered
the manifest as `in_use` would be indistinguishable from a reviewed window,
which is the whole reason the draft status exists.

Marker codes live in their own config rather than in `vocabularies.yaml`. The
vocabulary is the shared list of condition names every lab inherits; `S 13`
means whatever one paradigm decided, and nothing outside that lab can read it.
Mixing them would push one site's private codes into everyone's file.

The window extent cannot be inferred, so it is named per binding and travels
into the proposal: `until_next`, `fixed_s: N`, or `annotation`. Default is
`until_next`, which suits block designs and invents no constant.

Two failures found by running it against a real recording rather than only the
fixtures, both now covered by tests.

The `ug0002` block carries 9,849 events on a per-trial trigger beside 5 block
markers. Bound as a condition with `fixed_s: 2.0`, it proposed 9,849 overlapping
two-second rows: unreviewable, and meaningless as a contrast. `windows.csv`
describes conditions; trial structure belongs to an epoching recipe. A binding
matching more than `max_events_per_binding` events now proposes nothing and says
why.

The subtler half is worse. `until_next` originally meant the next marker of any
label, reasoning that a same-label rule would run a window through the condition
that follows it. With a dense trigger present, every real block window collapsed
to the millisecond gap before the next tick and was then discarded by the
minimum-duration filter, so the correct answer was silently replaced by nothing
at all. Boundaries now come only from labels that are bound and not trial-dense.
With both fixes the same recording yields two block windows, 90.8 to 128.5 s and
128.8 s to the end, which is what its 5 block markers describe.

The shipped `bindings` list is empty. An unbound label is reported as unbound
with its event count, never guessed at, because a wrong condition label produces
a result that looks right.

## 2026-09-08 Curriculum notebooks restate config values, and a test enforces it

A downloaded `.ipynb` has to run with no repository around it, so a teaching
notebook cannot import `configs/bands.yaml` or call into `dbsspeech`. That
collides with the rule that bands and thresholds live in `configs/`.

Resolved by restating rather than importing, and then testing the restatement.
Module S1 writes `BETA_BAND_HZ = (13.0, 30.0)` with a comment naming its source,
and reimplements `usable_bandwidth_hz` from scratch. `tests/unit/test_curriculum.py`
then asserts that the notebook's band equals `configs/bands.yaml` and that its
function returns the same value as `dbsspeech.preprocess.resample.usable_bandwidth_hz`
at four sampling rates. Change the config and the curriculum fails CI rather than
drifting quietly into teaching a number the app no longer uses.

The alternative, importing the package from the notebook, was rejected because it
makes the deliverable unusable for its purpose: a student downloads one file and
runs it.

Both assertions were verified to fail when the notebook is corrupted, which is
the property that matters. Injecting `(13.0, 31.0)` produces `S1 teaches beta as
(13.0, 31.0) but configs/bands.yaml says (13.0, 30.0)`.

## 2026-09-08 Student and solutions notebooks are generated from one source

Module 01 and 02 were authored as two hand-maintained `.ipynb` files each, and
module 03 drifted: its student and solutions markdown became byte-identical, so
the student workbook lost the `[STUDENT WORKBOOK]` tag and its instructions block.
The notebook sync test compares `curriculum/` against `web/public/notebooks/`, but
nothing compared a student file against its own solutions file.

S1 is generated instead: one Python source declares the cell list, and task cells
carry both a `TODO` body and a reference body. The two notebooks cannot diverge
structurally because they are the same list rendered twice.

Not retrofitted to modules 01 to 03, which would be a large rewrite of working
content for no behavioural gain. The generator lives outside the repository for
now; promoting it is a separate decision, and the honest cost of leaving it out
is that the four existing notebooks stay hand-edited.

## 2026-09-08 Onboarding tooling moves into the package

Two tools written while staging the Box archive lived outside the repository and
hardcoded one machine's paths. Both are what an external lab needs on day one,
and neither had anything site-specific in it, so they are now
`src/dbsspeech/detect/manifest_rows.py` plus two CLI commands:

    python -m dbsspeech draft-manifest <root> [--out DIR] [--study-id ID]
    python -m dbsspeech verify <root> [--study-id ID] [--verbose]

`draft-manifest` derives `subjects.csv` and `streams.csv` from a tree of
recordings. It fills only what a recording states about itself: format, path,
stream names, channel counts, sampling rates. `hemisphere`, `acquisition_date`,
`units` and `role` come back empty and `channels.csv`, `leads.csv` and
`windows.csv` are not derived at all, because those are the review. The reason
is stated in `LEFT_TO_REVIEW` and printed by the command, so the omission reads
as deliberate rather than unfinished.

`verify` opens every recording under a root and reports which ones the readers
take. Staging is not finished when the bytes land, it is finished when the
package can open them, and running that as its own step means a staging problem
surfaces there rather than three layers down inside a recipe.

The two tools that stay outside are the ones that talk to Box over rclone and
handle the site case numbers. Those are genuinely local, and moving them in
would put one institution's storage layout into everyone's package.

## 2026-09-08 The reader registry owns entry suffixes

`loader.py` kept its own map of format to file suffix so that a manifest row
pointing at a directory could find the one recording in it. Adding the `edf`
reader did not update that map, so `edf` resolved to an empty suffix tuple and
every EDF directory raised "no edf recording", while every test still passed
because no test opened an EDF directory through the loader.

`register_reader` now takes `entry_suffixes`, and `loader.py` asks the registry.
A second table describing the same fact is a table that goes stale the next time
someone adds a reader, which is exactly what happened here.

## 2026-09-08 Ruff excludes worktrees and teaching notebooks

`ruff check .` reported errors that were not the repository's. Git worktrees
under `.claude/worktrees/` are other checkouts of this same repo at other
commits and mid-change, so linting them reports another branch's unfinished work
as failures here. Teaching notebooks under `curriculum/` and
`web/public/notebooks/` are the other case: ruff lints `.ipynb` by default, and
a curriculum cell is written to be read on a slide rather than to satisfy a
line-length rule.

Both are now in `extend-exclude`, so `ruff check .` with no flags passes. The
package code the notebooks teach is still linted; the lesson is not.

## 2026-09-08 Ask no longer hardcodes a subject

`web/src/pages/Ask.tsx` sent `api.propose(question, "the first subject analyzed", "stage1")` with
both identifiers written into the source, so the agent screen answered about one
recording no matter what the manifest held. It now loads `api.subjects()`,
offers a subject and session selector, and defaults to the first row rather than
a named one: which recordings exist is a property of the manifest, not of the
build.

Three things were added because they prevent a specific confusion rather than
because a form usually has them. The QC status of the selected subject sits
beside the selector, since the gate refuses a run on unreviewed data and saying
so before the question is asked beats saying so after; this reflects the gate
and never decides anything. The available conditions are listed, because a
question can only name a condition the manifest defines. Changing subject clears
the standing proposal, because leaving it on screen beside a different subject
would misattribute a result.

The default question changed from "beta in the STN during overt speech" to
"beta power by condition". A speech-specific example in the first field a new
user sees teaches the wrong thing about what the app is for.

## 2026-09-08 Front-end build: the premise was wrong, the risk was elsewhere

The brief asked for cross-platform build handling "without architecture-specific
native module mismatches". Checked rather than assumed: `web/package-lock.json`
already carries native binaries for darwin arm64 and x64, linux x64 and arm64 in
both gnu and musl, and win32, and npm selects per platform through
`optionalDependencies`. There is no mismatch to fix, and changing the lockfile
to chase one would have made things worse.

The real risk is the one `.venv` already has a carve-out for. `web/node_modules`
is 168 MB across 1,227 files; it is gitignored, and a sync client does not read
`.gitignore`. The README now documents the same symlink treatment for it that
`.venv` gets, and says plainly that a `node_modules` must never be copied
between machines.

`engines: {"node": ">=20.19"}` is declared, which an external contributor
otherwise has to discover by failing.

## 2026-09-08 Filter latency is measured on the envelope, not by cross-correlation

Module S2 needed to show what a causal filter does to a reported onset. The
obvious instrument, the lag maximising the cross-correlation between input and
output, gave 1 sample for a beta burst through a causal fourth-order Butterworth
bandpass. That is wrong, and wrong in a way that looks plausible.

Cross-correlation between two narrowband oscillatory signals is maximised where
the carriers align, not where the envelopes align, and carrier alignment is
ambiguous modulo the period, 50 ms at 20 Hz. It measures phase delay and the
question was about group delay.

Onset is now read the way `tfr_onset` reads it: rectify, smooth with a symmetric
FIR, subtract that smoother's own known linear-phase delay, and take the first
crossing of a fraction of the peak. The same causal filter then shows a 63 ms
late onset over 13 to 30 Hz and 213 ms over 18 to 22 Hz.

Cross-correlation is still used in the module, on steady tones, where carrier
alignment is exactly the right measurement. The lesson is that the two questions
need different instruments, which the module now says explicitly.

Worth recording because the wrong answer was self-consistent and would have
shipped: an assertion of `delay > 0` passes on 1 sample.

## 2026-09-08 Aperiodic parameterization already shipped; PAC needed pactools

Section 4.3 asked for three recipes. Checking what was already installed changed
two of the three answers.

**Aperiodic needs no recipe.** `fooof` is already a dependency, transitively,
because `py-neuromodulation` requires it and ships `features/fooof.py`. The
existing `pynm_features` recipe lists `fooof` in `HEAVY_FEATURES`, so it is
opt-in and off by default rather than absent. Enabling it returns aperiodic
exponent, offset and knee plus periodic centre frequency, bandwidth and height
over the aperiodic fit. Writing a parallel specparam recipe would have produced
a second aperiodic implementation that disagrees with the first, which is worse
than having none. The remaining work there is documentation and defaults, not
code.

**PAC needed a dependency.** py_neuromodulation has no phase-amplitude coupling
feature. Its coupling-adjacent features are `bispectrum`, which is quadratic
phase coupling and a different question, `coherence`, which is between channels
rather than across frequencies, and `sharpwave_analysis`, which is waveform
shape. So `pactools` 0.3.1 is now a dependency. It resolved without disturbing
anything else, two packages changed, and it computes correctly against numpy
2.5.2 despite its age.

`pac_modulation_index` wraps `pactools.Comodulogram`. `tort` is the default
because the modulation index is the most reported and therefore the most
comparable measure, but the estimator is a parameter and travels into the run
record, since the five estimators disagree on the same data. Surrogates default
to 200 and the surrogate z-score comes from pactools' own `comod_z_score_`
rather than a local calculation, so there is one definition of what the
correction means.

Two things measurement decided rather than assumption.

`high_fq_width` is spelled `'auto'` by pactools, not `None`, and `'auto'` means
twice the highest phase frequency. That is the sideband condition: the amplitude
filter must be wide enough to contain the phase frequency as a sideband or
coupling that exists cannot appear at all. Passing `None` raised a TypeError
inside the library's filter.

The phase filter width was wrong and the tests caught it. The first default was
4 Hz against a 2 Hz step. On a synthetic signal with 8 Hz phase driving 80 Hz
amplitude, that produced a flat profile across 4 to 12 Hz and reported the peak
at 4 Hz: not a null result, a confident wrong one, because overlapping bins all
admit the same rhythm and the peak lands wherever noise favours. At 2 Hz width
the same signal recovers 8 Hz cleanly. The default is now 2 Hz, the recipe logs
and adds a caveat when the width exceeds the step, and two tests pin both the
relationship and the evidence.

The recipe also refuses a window shorter than ten cycles of the slowest phase
frequency, naming the duration that would be long enough, and refuses an
amplitude range reaching Nyquist.

## 2026-09-08 erp_epochs, the first event-locked recipe

Every other recipe contrasts condition windows, because the speech protocol has
no markers and every window in it was derived by hand from a microphone. The
BrainVision and EDF readers changed that, so `erp_epochs` locks to the markers a
recording carries: `Recording.epochs` supplies the onsets, optionally restricted
to those falling inside one condition's windows.

Four choices decide whether the average means anything, and each is enforced
rather than documented.

Baseline correction is per trial, before averaging. Correcting the average
afterwards removes one common offset instead of the drift that differs trial to
trial, which is a different and worse quantity. A test plants a different
per-trial offset and checks the per-trial route is the tighter one.

A baseline window that does not end at or before zero is refused by the
parameter model, not warned about, because it subtracts part of the response
from itself and shrinks the effect being measured. Three other geometric errors
are refused the same way: a reversed epoch, a baseline starting before the epoch
does, and a peak window extending past its end.

Trials are counted and too few is refused. `min_trials` defaults to 10, the
count travels into every row and the summary, and a lead or scheme with fewer
usable trials produces no result rather than a noisy one that sits beside the
others looking equivalent.

Peak amplitude and latency are measured only inside `peak_window_s`. The largest
deflection anywhere in an epoch is usually noise or an edge, so the search range
is a parameter and reaches the run record instead of being chosen after seeing
the data.

Epoching, baseline correction and averaging are done in numpy rather than
through `mne.Epochs`. That is a deliberate exception to preferring library DSP:
these are arithmetic on an array, and building an `mne.Info` for a montage this
package already derived would add a conversion in which a unit or scaling
mistake would be invisible in the output.

One implementation detail worth recording: reads at different event offsets can
differ by one sample from rounding, and a short trial is dropped rather than
padded. Padding would invent samples at exactly the latency being measured.

A note on the tests. The first version planted a 5-unit response in noise of
sigma 12 over 60 trials, which leaves a standard error of 1.55, so taking the
largest absolute value across the peak window picked a noise excursion of 7.7
and the test failed. That was the test being under-powered rather than the code
being wrong, and the fix was to make the average genuinely clean, sigma 3 over
100 trials. A test that depends on the random seed to pass is not testing the
averaging.

## 2026-09-08 Two preprocessing claims that did not survive measurement

The preprocessing capstone was planned around two lessons. Both were checked
before being written, and both were wrong.

**"Re-reference before decimating."** This is stated as a rule in a lot of
pipeline documentation and it is empty. Re-referencing is linear across channels
and time-invariant; decimation is linear along time and applied identically to
every channel. Two linear maps on different axes commute. Measured on eight
channels carrying a stimulation artifact 800 times the physiology, the two orders
agree to 3.7e-12 relative. The module now proves the commutation instead of
asserting an ordering.

What does not commute is any nonlinear step, and artifact detection is one: it
compares a magnitude against a threshold. A common-mode artifact is flagged on
100 percent of samples when detected on contacts and 0 percent when detected on
derivations, because the montage removes it. An artifact on ring 1 goes the other
way and reaches four derivations. Jaccard agreement between the two orders is
0.667. So the ordering that matters is where the nonlinear step sits, and a run
record has to name the montage detection ran on.

**"Excising samples corrupts the spectrum."** This is the argument usually given
for the `CLAUDE.md` rule that artifacts become annotations. It does not hold:
twelve excised spans in eighteen thousand samples move an averaged Welch spectrum
by 2 to 3 percent in beta, high gamma and above. Teaching a false reason for a
true rule is worse than teaching no reason, because the first student who checks
stops believing the rule.

The real costs are stated and measured instead: the time base drifts 1800 ms by
the end of the record, phase advances by `2*pi*f*s/fs` at the join and is
neutral only when the removed span is a whole number of periods, and per-channel
excision gives each channel its own clock, after which two identical channels
that cancelled to 0.00e+00 cancel to 1.17e+00.

Recorded because both wrong versions were plausible, and one of them is
repeated in the documentation of several analysis packages.

## 2026-09-08 Onboarding backend: inspect proposes, commit refuses

Five linked CSVs satisfying ten invariants is the largest obstacle to anyone
outside this lab using the package. Most of that work is transcription, so
`src/dbsspeech/onboarding.py` reads what a recording states about itself, and
`POST /onboarding/inspect` and `POST /onboarding/create` expose it.

The split between the two functions is the design. `inspect` opens, reports and
writes nothing; every value it returns is a proposal, and the response carries a
`not_proposed` list naming what it deliberately left out, so an empty channels
table cannot be mistaken for a complete one. `commit` writes, and only rows a
person confirmed.

Four refusals in `commit`, each guarding a way the manifest could quietly become
wrong.

It validates the merged manifest as a whole and writes nothing at all if
validation fails, raising `CommitRefused` with the errors. A manifest that
parses but violates an invariant is worse than an incomplete one: `load_manifest`
is what every recipe depends on, nothing downstream would report the breach, and
the first symptom would be a wrong number.

It never overwrites an existing row. A row whose key already exists is reported
as a duplicate and skipped, because overwriting a reviewed row from a rerun
import is how a curated decision disappears without trace. There is a test that
reruns an import over a curated window and checks the curated status and notes
survive.

It writes only `subjects`, `streams` and `windows`. `channels.csv` and
`leads.csv` are refused outright with a message saying they are the review, not
the import. Which channels are usable and which target a lead is in are the
judgments the whole QC layer exists to record.

It writes whole files through a temporary path and a rename, not appends. The
validation above was of the whole file, so a partial append could leave a file
that parses and was never the thing validated.

The API returns 422 with the validation errors rather than a 500, because a
caller that gets a 500 learns only that something went wrong, and which
invariant broke is the entire useful content.

Not done here: the React wizard from the same section. `web/src/App.tsx` and
several components are being edited right now in the `deploy-4-3` worktree, and
the wizard needs a route in exactly that file. The backend is complete and
tested, so the screen can be built against it whenever that work lands.

## 2026-09-08 The repository can now open its own teaching material

The Learn page hands students `.ipynb` files and `pyproject.toml` declared no
notebook tooling in either dev list, so `uv sync --extra dev` produced an
environment that could not open them. `jupyterlab` and `ipykernel` are now
declared in both.

Adding the dependency exposed three defects that only a real kernel finds.
Modules 01 and 02 had no `kernelspec`, so Jupyter would prompt for a kernel on
the two modules a student reaches first. Module 03 was `nbformat_minor` 4 while
everything else was 5. And no notebook carried cell `id` fields, which `nbformat`
warns will become a hard error. All twelve now validate, and all six solutions
notebooks execute end to end through `nbclient` against a real kernel rather than
through the `exec`-based harness in `tests/unit/test_curriculum.py`.

The test suite still uses `exec` rather than `nbclient`, because `exec` runs in
1.8 seconds against roughly 9 seconds for six kernel round trips, and it is the
path that lets a test reach into the notebook namespace and assert on `record` or
`causal_errors`. `nbclient` is now available for a test that wants to prove a
notebook works in the tool a student will actually use.

## 2026-09-08 coordinates.csv, and what a position does not license

An optional sixth manifest table mapping a contact to a position, so a result
can be reported by anatomy rather than only by contact index. Optional is the
important half: a lab without imaging has no such file, it reads as an empty
table, `validate` passes, and every recipe works without it. Backward
compatibility was checked against the existing manifest before anything else.

`space` and `source` come from new vocabularies. The space entries carry
`comparable_across_subjects`, which is the fact that matters: a position in
`native` space is correct for that subject and means nothing between subjects,
so it validates with a warning and a group claim needs a template space.

The load-bearing decision is what a coordinate does **not** do. It locates a
contact. It says nothing about which way a directional segment faces, which is
what invariant 10 gates on `rotation_deg`. Adding positions must not quietly
unlock direction claims, so invariant 10 now says so explicitly and a test
asserts the rotation warning survives a fully populated coordinates table. The
alternative, letting an imaging-derived position feel like it settles
orientation, is exactly how an unfounded anatomical claim reaches a figure.

Invariant 11 checks that a row names a lead in `leads.csv`, a contact on that
lead's model, three numeric axes, and a known space and source, and that a
contact appears at most once per lead. Thirteen tests, including one confirming
a missing file is not an error.

Not done: parsing `ea_reconstruction.mat`. Lead-DBS writes a MATLAB structure
whose layout varies by version, and the existing TDT readers were both written
against a real file rather than from memory. Writing this one blind would be
guessing at a layout, so it waits for a sample export. `coordinates.csv` is the
interchange format in the meantime, and a converter can fill it later without
any change to the schema.

## 2026-09-09 The curriculum is complete, and what building it changed

Thirty-one modules across seven tracks plus a preprocessing capstone, each a
student workbook and a solutions guide, all executed in CI. Three decisions in
it are worth recording because they were not obvious at the start.

**Modules are generated, not hand-written.** One Python source declares the cell
list; task cells carry both a `TODO` body and a reference body; both variants are
emitted from it. Modules L1 to L3 were hand-maintained as two files each and
drifted: L3 lost its `[STUDENT WORKBOOK]` tag and its instructions block, which
is exactly the failure the generator makes impossible. The generators live
outside the repository for now, which is the honest cost of this choice: the
notebooks are the artifact and regenerating one needs a script that is not
checked in.

**Notebooks restate config values rather than importing them.** A downloaded
`.ipynb` has to run with no repository around it, so it cannot read
`configs/bands.yaml` or import `dbsspeech`. Restating a value would let it drift,
so the test suite asserts the restatement: S1's beta band against
`configs/bands.yaml`, P1's `usable_bandwidth_hz` against
`preprocess/resample.py`, and G3's entire guardrail table against
`configs/guardrails.yaml`. Change a config and the curriculum fails CI rather
than quietly teaching a number the app no longer uses.

**Presentation is data, not code.** Modules whose teaching is in the notebook use
one `NotebookModule` component driven by `web/src/pages/learn/registry.ts`;
only modules where interaction genuinely teaches something got a bespoke page.
Six did. A test asserts every notebook on disk is referenced by the UI and that
no module is left switched off, which caught four modules that had been built and
never activated.

## 2026-09-09 Five planned lessons that measurement contradicted

Recorded because each was plausible, each is widely repeated, and each would have
shipped if it had not been checked first. This is now the first rule in
`curriculum/README.md`.

**"Re-reference before decimating."** Both operations are linear on different
axes, so they commute. Measured at 3.7e-12 relative with a stimulation artifact
800 times the physiology present. What does not commute is artifact detection,
because thresholding is nonlinear: a common-mode artifact is flagged on 100
percent of samples on contacts and 0 percent on derivations.

**"Excising samples corrupts the spectrum."** It does not. Twelve excised spans
in eighteen thousand samples move an averaged Welch spectrum by 2 to 3 percent.
The real costs are the time base, phase continuity, and the shared clock across
channels, none of which appear in a spectrum.

**"Spike bleed contaminates high gamma."** At realistic amplitudes spikes
contribute 0.08 percent of 70-150 Hz power, and an eightfold multi-unit rate
increase moves it under 2 percent. The claim needs an aperiodic background twelve
times smaller than typical. It becomes true where a montage has suppressed the
background, which is the useful version of the warning.

**"Multitaper is much better than Welch."** At genuinely matched resolution it is
better by 9 percent. The naive resolution match flatters Welch by silently giving
it twice the blur, because a Hann taper widens the main lobe to 2.03 bins.

**"Factor analysis is robust to a bad channel."** With one factor it fails
exactly as PCA does, at 89.9 degrees, because a factor loading on a single
channel is indistinguishable from that channel's private noise. It needs a spare
factor, and the number of factors therefore decides whether the method has its
advertised advantage at all.

A sixth, from the connectivity track, inverts an intuition rather than refuting a
claim: spurious Granger causality from a hidden common driver is **largest when
the two regions are nearly equidistant from it**, reaching ten times the value of
a genuine one-way drive, because one channel is then a near-perfect shifted copy
of the other.

## 2026-09-09 A slow test turned out to be a modelling error

`tests/unit/test_curriculum.py` reached eleven minutes once all 31 modules were
in it, which is long enough that people stop running it before declaring done.
Profiling put 595 seconds of a 638 second total in one module, M2, and 43 seconds
in the other thirty.

Two things were wrong, and only one of them was performance.

The suite re-executed a notebook once per test that wanted its namespace, so a
notebook with three targeted tests ran four times. `run_notebook` now caches per
session and returns a shallow copy, so a test that rebinds a name cannot affect
another.

The real cost was a single `FactorAnalysis` fit taking 203 seconds and using 1016
EM iterations without converging. That is not a slow fit, it is a **degenerate
model**, and the reason is the module's own subject. M2's Section 3 applied a
differencing montage to a factor loaded on a block of six contacts. Differencing
adjacent contacts cancels a block everywhere except at its boundary, leaving a
loading on exactly one derivation, and Section 1 of the same module establishes
that a factor loading on a single channel is indistinguishable from that
channel's private noise. The likelihood surface is flat, so EM crawls.

Section 3 now uses common average reference, which removes the shared term and
leaves the spatial structure, recovering the factor from 46 degrees off to 18.
The differencing montage stays in the module as the cautionary case, with its
non-convergence reported as the symptom it is. The module is better for it, and
the lesson it gained, that the montage is part of the model rather than a
preprocessing step, is one nothing else in the curriculum was making.

Sample count also came down from 20000 to 4000, which is `T/C = 333` and far past
the point L4 showed matters. Suite time went from 662 seconds to 15.

## 2026-09-09 What the validation pass changed

A review agent audited build, reachability, accessibility and feasibility across
the finished curriculum. Four of its findings were defects in what the curriculum
teaches rather than in how it is presented, and those are the ones worth
recording.

**The guardrail index described four rules as things they are not.** G3's table
called G7 "contamination in a high band" and attributed it to U1's spike-bleed
measurement. G7 is muscle contamination, over `emg_band_hz` of 100 to 1000 Hz,
escalating to block for overt speech. Spike bleed is neural and touches none of
its parameters. G9 was attributed to M1's dimensionality results, which are not
non-stationarity. G10, a metadata rule about where a window came from, was given
P1's decimation arithmetic. And G5 was taught as a refusal at a window-to-effect
ratio of 1.0 where the config warns at 5.0.

The table now says which guardrails this curriculum actually derives a number
for: nine of thirteen. Two are provenance rules with no number, and **two, G7 and
G9, are real thresholds no module reaches**. Naming the gap is more useful than
claiming coverage, and it says what the next two modules should be.

The test now checks the guardrail NAME against the headings in
`docs/guardrails.md`, not only the id and severity. An id check cannot see a rule
described as something else, which is exactly the defect that got through.

**Two modules used a frequency band the project deliberately does not define.**
C4 and G1 both used `gamma 30-70`. `configs/bands.yaml` has `low_gamma` at 30 to
60 and `high_gamma` at 70 to 150, and the gap exists because
`line_noise.fundamental` is 60 Hz. Both were measuring across the notch. A new
test refuses any band in any notebook that spans the line-noise frequency without
being one the config defines.

**The app claimed more verification than it had.** The notebook-module page said
"every number here is produced by a test cell that runs on every commit" above
values that are printed rather than asserted. The wording now says what is true:
every module is executed on every commit, load-bearing numbers are asserted, the
rest are printed.

**Accessibility had not been started.** No `aria-*`, no labels, no keyboard path
anywhere in the Learn section, and the default landing module was a drag-only
widget. Fixed: 14 sliders named, 11 figures given `role="img"` and a description,
tracks and modules made a real tablist with `aria-selected`, the L1 vector handles
made keyboard-operable with arrow keys, DBS contacts and matrix rows given Enter
and Space, `text-stone-400` on light grounds raised to `stone-600` (2.48:1 to
about 5.7:1), the selected module button moved to `cyan-700` (3.60:1 to 5.28:1),
and the projection line in L1, which is that module's entire teaching point,
moved off `#581c87` at 1.82:1 against its own background. Legends now name the
encoding, solid against dashed, rather than the colour. A static test now fails
on an unnamed slider, an unlabelled figure, or a pointer-only interaction.

Also: `strict` is now actually enabled in `tsconfig.app.json`, which the code
already passed but the build did not enforce; `scikit-learn` and `fooof` are
declared rather than arriving transitively through `py-neuromodulation`; the three
bespoke pages that linked only a student workbook now link solutions too; CI
executes the student notebooks as well, requiring them to fail only where a task
is withheld; and the root README no longer says the repository is a scaffold with
no tests.

## 2026-09-09 Contrast ratios, measured rather than assumed

The accessibility fixes swapped Tailwind classes, which is only a fix if the new
classes actually clear the threshold. Measured from the OKLCH values in the
shipped stylesheet, converting through OKLab to linear sRGB and applying the WCAG
relative-luminance formula. The conversion reproduces Tailwind's own hex values,
`stone-400` as `#a6a09b` and `cyan-600` as `#0092b8`, which is the check that it
is right.

| pair | before | after |
|---|---|---|
| body text on a light tile | `stone-400`, 2.48 | `stone-600`, 7.32 |
| accent text on white | `cyan-600`, 3.60 | `cyan-700`, 5.28 |
| warning text on white | `amber-600`, 3.19 | `amber-700`, 5.05 |
| selected module button | white on `cyan-600`, 3.60 | white on `cyan-700`, 5.28 |

All four were below the 4.5:1 needed for body text and all four now clear it.
`rose-600` was already at 4.51 and moved to `rose-700` for consistency.

Worth recording because the first attempt at this measurement was wrong: the
OKLab transform returns **linear** sRGB, and applying the sRGB gamma decode to it
again gave `stone-400` a ratio of 6.18 against a true 2.48, which would have
reported the problem as already solved. The check that caught it was reproducing
Tailwind's published hex values, not the ratios themselves.

Contrast on dark panels was left alone: `stone-400` on `stone-950` is above 6:1
and was never the problem.

## 2026-09-09 N4 measures the guardrail it underwrites, and disagrees with it

Every module in Track 07 exists to derive a number the app enforces. N4 was
written to underwrite `G9_nonstationarity_exceeds_effect`, and the measurement
did not agree with the shipped threshold: the estimate collapses near a ratio of
0.73, not 1.0. That is the second time this curriculum has been written to
justify a number and found the number questionable, after G5's ratio.

The decision was to report the disagreement inside the teaching module rather
than quietly adjust either the threshold or the lesson. Three options were open:

**Change the config to 0.73.** Rejected. The evidence is one drift shape, one
effect size, and one arbitrary definition of "usable". Fitting a shipped
threshold to a single simulation is exactly the arithmetic-somebody-did-once
problem the guardrails exist to prevent, and it would make the app noisier on
recordings shaped differently.

**Soften the module to agree with the config.** Rejected outright. Writing what
the experiment says is the standard the whole curriculum is built on, and five
planned lessons have already been deleted for failing it.

**Teach the disagreement.** Taken. Section 3 reports the sweep, states that the
threshold is permissive, states why 1.0 is still defensible to ship, and draws
the conclusion that transfers: the direction of the error is known even though
the right number is not, so a quiet G9 is not evidence that a comparison is
clean, and the ratio itself belongs next to the effect rather than being reduced
to fired-or-not. The threshold question went to docs/backlog.md as a scientific
decision, and the finding to docs/findings.md.

This also settles what Track 07 is for. A module that can only ever agree with
the config is not verifying anything, it is restating it. N4 is the first module
whose measurement pushes back, and that is the outcome that makes the other
twelve worth having.

## 2026-09-09 Track 07 file prefixes, and the flat notebook mirror

Two smaller things, both caught by tests rather than by reading.

Renaming the Track 07 module ids to N1/N2/N5 left the FILE names alone, so N3's
`03_emg_contamination_in_speech` and N5's `03_the_thirteen_guardrails` shared a
`03_` prefix. N5 is now `05_the_thirteen_guardrails`, matching its id. The
listing order in the track directory is the only thing this affects, but the
prefixes are the only ordering the directory has.

`web/public/notebooks/` is FLAT: every notebook sits at the top level, keyed by a
filename that must therefore be unique across all seven tracks. Attempting to
refresh it with `rsync -a --delete` from `curriculum/` created a nested tree and
deleted the entire flat mirror, which
`test_notebook_sync_between_curriculum_and_public` caught immediately. The mirror
does not need refreshing by hand at all: `nbgen.emit()` already writes both
trees on every generator run. The rebuild now asserts filename uniqueness before
copying, since the flat layout silently depends on it.


## 2026-09-09 What the curriculum reviewers found, and the two comments that lied

Two bounded reviewers audited the curriculum after the first attempt failed. The
first agent had been given an open brief, ran six hours, and returned nothing: it
fell into a loop of over-specific PubMed queries that each matched no articles.
Its replacements were given a tool-call budget, an order to stop and report
partial findings with named coverage gaps, and a flat ban on external literature
search. Both returned usable findings in under seven minutes.

Four findings were real and are fixed.

**N4 said sixteen times the data halved the error bar. It quarters it.** The
error bar falls as 1/sqrt(n), so 16x the data divides it by 4, and the notebook's
own printed table said 0.0266 to 0.0066. The assertion behind the claim was
`sem_long < 0.5 * sem_short`, which is true of a 4x reduction and so passed
while the prose beside it was wrong. It now asserts `3.5 < ratio < 4.5`, the
factor theory predicts. A bound loose enough to pass under the wrong explanation
is not a test of the explanation.

**N3 said one microvolt of EMG is a sixth of high gamma. It is 21 percent.** The
notebook printed 21 in its own table. Rewritten to the measured numbers, and to
the comparison that carries the lesson: it takes five times less muscle to double
high gamma than to double beta, 2.2 against 11.2 microvolts.

**N3 and N4 both claimed a test enforced their restated config values, and no
such test existed.** This is worse than saying nothing. The config-fidelity-by-
test pattern only works if the test is real, and a reader who trusts the comment
has no reason to re-derive the number. `test_guardrail_notebooks_restate_their_
config_values_correctly` now checks G7's band, escalation frequency, escalation
conditions and require_bipolar, and G9's ratio, against `configs/guardrails.yaml`.
Writing it immediately caught a second error, my own: the config key is
`escalate_to_block_above_hz`, not `escalate_above_hz`.

**The Learn tablist had tab semantics without tab relationships.** Tabs carried
`role="tab"` and `aria-selected` but no `aria-controls`, and the panel had no id,
so a screen reader was told these were tabs and then given no way to say which
region a tab governed. Native buttons kept it operable by Tab and Enter, which is
why the gap survived: it degrades the announcement, not the clicking. Added ids,
`aria-controls`, `aria-labelledby`, a roving tabindex, and arrow/Home/End
handling, with a test.

Two findings were not real, and both were my fault for leaving a trap. The
reviewer reported the README naming only Tracks 02 and 05 as prerequisites for
Track 07, which I had already corrected before it read the file. It also reported
N1, N2 and N5 as having no generator, because theirs were still named
`make_g1.py`, `make_g2.py` and `make_g3.py` from before the module ids were
renamed to N1/N2/N5. The files were right there under the old name. They are now
`make_n1.py`, `make_n2.py` and `make_n5.py`. A reviewer misled by a stale name is
evidence about the name, not about the reviewer.


## 2026-09-09 Courses and lessons, not tracks and modules

The curriculum read like a course catalogue for a video site: "Track 07", "N5",
"Module 03". It is meant to read like a graduate program of study, so the
vocabulary changed and the citation keys changed with it.

Eight courses in four groups, each lesson cited by a course tag and a number.
`L4` became `LIN 4`, `S3` became `SIG 3`, `N5` became `GRL 5`. 1,694 citations
across 109 files.

**Why the tags rather than course numbers.** A numbered scheme, `NENG 702`, reads
most like a real program and was the first proposal. It was rejected because this
material is not a registrar course, and something that looks like one could be
mistaken for one if it ever leaves the lab. The tag carries the same information
without the false authority.

**The rename had one genuine trap and the check found it.** `N3` was both a
lesson id and a variable in SIG 3, where it held a sample count. A blanket
word-boundary replace would have rewritten `N3 = 1000` into a citation and broken
the notebook, silently, because the module would still execute. The sweep was
therefore preceded by a scan for lesson ids used as Python identifiers outside
string literals, which found exactly that one case; it is now `N_1S`. Guardrail
ids `G1` to `G13` are a separate namespace and were excluded from the map, with a
post-condition asserting none of them was rewritten.

**Two new tests, because the citations are now load-bearing.**
`test_every_lesson_citation_points_at_a_lesson_that_exists` walks every notebook
and fails on a citation to a lesson that does not exist. Nothing checked this
before: a reference to `S3` in a sentence pointed nowhere in particular, and a
renumbering would have left the prose reading perfectly well while meaning
nothing. `test_the_learn_ui_and_the_tests_agree_on_which_lessons_exist` pins the
interface's list against the suite's, so a lesson cannot exist in one and not the
other. Both were bite-tested by planting a citation to `SIG 9` and by deleting
`CON 3` from the interface.

The new scheme is also what makes the first test possible. `C1` is a plausible
variable name and `CON 1` is not, so a citation is now unambiguous to a machine
as well as to a reader. That was a side effect of the naming, not the reason for
it, and it is the more valuable half.


## 2026-09-09 A rename checker that only knows the new syntax is blind

The lesson rename was reviewed by a subagent, which found a class of breakage the
new test could not see, and that is the part worth recording.

LIN 1 to LIN 3 had **two** citation styles, not one. Besides `L1`, `L2` and `L3`
they were also cited as `Module 01`, `Module 02` and `Module 03`, a spelling left
over from when those three notebooks were the whole curriculum. The rename map
covered the first style and knew nothing of the second, so 82 citations were left
pointing at a naming scheme that no longer existed. One sentence in POP 2 ended up
reading "the conclusion Module 02, LIN 4 and PRE 1 reached", mixing both styles in
a single list, which is what made it obvious once seen.

`test_every_lesson_citation_points_at_a_lesson_that_exists` could not catch this.
It matches the eight course tags, and `Module 02` contains none of them, so the
stranded references were invisible to the test written specifically to catch
stranded references. A checker built from the new vocabulary cannot see the old
vocabulary at all, which is precisely the population a rename endangers.

The fix is `test_no_lesson_uses_a_retired_citation_style`, which bans the retired
spellings outright rather than trying to resolve them. Running it immediately
found a second stranded style nobody had mentioned: `Track 01` through `Track 07`
in every notebook's subheading and in prose, 37 files' worth, still describing a
structure that no longer existed either.

One judgement call inside the fix. `Module 03` looked like it might not always
mean LIN 3: REC 1's prerequisite table cites it for the quasi-static monopole
kernel, and REC 1 is the only lesson with seventeen mentions of that kernel, so a
blanket replacement risked inventing a false citation. Checking rather than
assuming showed LIN 3 does derive the kernel, in cell 5, as its example of a
genuinely ill-conditioned leadfield. The citation was correct and only its label
was stale.

Also removed: CON 1 had both a bespoke page and a registry entry. Learn.tsx checks
for a bespoke page first, so the entry was unreachable, while the numeric-drift
test went on validating numbers it never displayed. Content that is kept honest
but never shown reads as covered when it is not.
`test_no_lesson_has_both_a_bespoke_page_and_a_registry_entry` now forbids it, and
also asserts that the two rendering paths between them cover every lesson exactly
once.


## 2026-09-09 Inference is a Scientific Integrity course, and it follows Guardrails

The Inference course (INF 1 to INF 3) closes the largest gap the curriculum audit found,
since BST 622 is core rather than elective. Two placement questions had real
answers rather than arbitrary ones.

**Which group.** Inference could have gone in Analysis, beside Connectivity and
Population Dynamics. It is in Scientific Integrity instead, because what these
three lessons actually teach is what a number does not license: INF 1 that a
p-value computed correctly still selects for overestimates, INF 2 that a
significant cluster has no edges, INF 3 that a column labelled z means twenty
different things. That is the same job GRL 5 does for the guardrails.

**Which order.** Guardrails was previously last, and Inference now follows it.
This is a real dependency and not a preference: INF 1 Section 3 and INF 3
Section 2 both build on GRL 4's result that a drifting baseline makes the choice
of design, not the choice of test, the thing that decides the answer. Putting
Inference first would have meant restating that argument or asserting it, and
the curriculum's rule is that a lesson may use only what an earlier lesson built.

The cost is that "Guardrails is last" is no longer true and the README's order
diagram gained an edge. The alternative was a weaker INF 1.

**A new config-fidelity test.** INF 3 derives `configs/statistics.yaml`, so it
restates the four centre and five scale names to run standalone.
`test_inference_notebook_restates_the_normalization_options_correctly` asserts
those names still match both the config and `dbsspeech.stats.normalize`, since
either could be edited alone. This is the same pattern as the guardrail
threshold test, and it exists for the same reason: a lesson that derives a config
value is only worth having if it is still deriving the shipped one.

## 2026-09-09 Notebook stdout is cached with the namespace, not re-executed

`test_ui_numbers_still_match_what_the_notebooks_print` checks every number the
Learn page quotes against what the notebook actually prints. It built its own
namespace and executed each stemmed notebook itself, outside `_NOTEBOOK_CACHE`,
because the cache held only the namespace and it needed stdout. So every lesson
with a registry entry ran twice per session.

That was tolerable at 33 cheap lessons and stopped being tolerable when INF 2
arrived at 43 seconds, which is most of a minute paid twice. The cache now holds
`(namespace, stdout)` from one execution, `run_notebook` returns the first and a
new `notebook_stdout` returns the second.

Measured on the full unit suite: 160 s before Inference existed, 98 s after
Inference plus this change. Three lessons were added and the suite got faster.

The tradeoff is that notebook prints now go to a buffer rather than to pytest's
own capture, so they no longer appear in `-s` output. The failure path still
quotes the failing cell's source, which is what a person actually needs.

## 2026-09-09 The retired-citation guard now scans the interface, not just the notebooks

`test_no_lesson_uses_a_retired_citation_style` banned "Track 0" and "Module 0"
across `curriculum/**/*.ipynb` and stopped there. A review of the Inference
change found four live "Track 0N" citations in `web/src/pages/learn/registry.ts`,
which had survived the entire Track-to-Course rename and a full content audit
because no test looked at that file. Extending the scan to `Learn.tsx` and
`web/src/pages/learn/*.ts*` immediately surfaced six more, in the bespoke lab
pages, where they were user-visible course headers reading "Track 02 · Digital
Signal Processing".

All ten are fixed and the UI files are in the scan. The general point is the one
the test's own docstring already made and did not act on: a checker built from
the new vocabulary is blind to exactly what a rename strands, and scoping it to
the directory you happened to be renaming reintroduces the blindness one level up.

## 2026-09-09 Decoding is an Electives group, and it does not add a guardrail

**A fifth group.** The Decoding course (DEC 1 to DEC 5) went into a new
**Electives** group rather than into Analysis. The audit this curriculum was
measured against has statistical inference as core and machine learning as
elective, and that ordering is right here for a concrete reason rather than a
deferential one: every recipe in the package depends on what INF establishes, and
nothing in the package depends on DEC at all. Marking the group elective says
that plainly, and it uses the elective-block structure Garrett asked for.

**It comes last.** DEC 2 and DEC 4 both build on INF 1's result that an estimate
selected for looking good is not an unbiased estimate, so Decoding follows
Inference, which already follows Guardrails.

**It proposes a guardrail and does not adopt one.** DEC 2 measures the case for
G14, cross-validation folds must respect time, and stops. The evidence is strong,
recorded in `docs/backlog.md`, and adopting it would change what the package
enforces and require a new field in the run record. That is a decision about what
the app does to real analyses, so it is Garrett's, and a lesson is not the place
to make it. This is the first time a curriculum lesson has produced a guardrail
proposal rather than underwriting an existing rule, and the split seems right:
the lesson owns the measurement, the config owns the enforcement.

**A confound found while reviewing.** DEC 2's rho sweep uses `scipy.signal.lfilter`,
which starts from rest, so the first few 1/(1-rho) samples ramp up from zero
variance. At rho = 0.95 that is tens of epochs, which would have made the rho = 0
control the only stationary row in the table, and that row exists precisely to
rule out everything except the autocorrelation. The generator now discards a
400-sample burn-in. It moved the honest transfer number from 0.179 to 0.238 and
left every conclusion intact.

## 2026-09-09 The Learn page shows its groups, and starts on a course that exists

Two things a review of the Decoding change turned up in `Learn.tsx`, neither
introduced by it.

**The group was data the interface never used.** Every course carries a `group`
field, and nothing read it: the tab bar was a flat map over ten courses. So
`curriculum/README.md` and `docs/decisions.md` both described an Electives group
that a reader of the app could not see, which makes the distinction a private
note rather than a statement. The tab bar now renders the five groups with a
label above each. It stays one `role="tablist"` so the arrow-key pattern still
walks the whole set, and the group labels are `aria-hidden` with the group name
folded into each tab's `aria-label` instead, so a screen reader hears it once per
tab rather than as a stray text node inside a tablist.

**The initial state named a course that does not exist.** `selectedCourse`
started at `"01_linalg"`, a retired id; no course matches it. `currentCourse`
falls back to `COURSES[0]` so the right panel rendered, which is why this
survived, but on first paint `aria-selected` was false on every tab and no tab
carried the selected style. It now starts at `COURSES[0].id` and the first lesson
of that course, so the data cannot drift away from the default again.

## 2026-09-09 The derivative store: 8 kHz, one pass, no montage, HDF5, .mat over .tev

The archive is 791 GB and analysis cannot read it from Box on every run. A
one-pass derivative store is being built (`src/dbsspeech/derive/`, driver in
the archive's `_tools/`). Six decisions, each with the alternative it beat.

**LFP is stored at exactly 8000 Hz, not 1000 Hz and not 8138 Hz.** A 1 kHz
store was the first draft. It was rejected because ERNA sits at 200 to 500 Hz
and would land on or past the anti-alias skirt, because 130 Hz stimulation
harmonics have to be resolved to be removed properly rather than folded into
the band of interest, and because a band discarded in an archival pass cannot
be recovered while a band kept can be decimated at analysis time for nothing.
8138.02 Hz was the previously recorded default, from decimating 48828.125 by
six. Every rate in this archive is an exact rational (390625/8, 390625/16,
390625/32, and round BrainVision rates), so exactly 8000 is 512/3125 of the
TDT rate and costs the same as integer decimation under `resample_poly`. One
uniform grid across both rigs, for 1.7 percent of bandwidth nobody used.

**The anti-alias filter is designed and measured, not defaulted.** The default
window `scipy.signal.resample_poly` builds puts its -6 dB point on the new
Nyquist, so content just above it folds back barely attenuated. The store
designs a Kaiser filter with `scipy.signal.kaiserord` and `firwin` for a
passband at 0.8 of the output Nyquist, a stopband at the output Nyquist, and
90 dB, then measures the response with `scipy.signal.freqz` and writes the
measured passband edge, -3 dB point, stopband edge, attenuation at Nyquist and
worst-case alias floor into every output. For 48828.125 to 8000: 178,595 taps,
usable to 3200 Hz, -92.7 dB at 4000 Hz, alias floor -100.9 dB. Guardrail G6
can now read a measured `usable_bandwidth_hz` instead of assuming 0.8 of
Nyquist. `preprocess/resample.py` is untouched; G6 and the recipes depend on
it, and it answers a different question.

**No re-referencing in the store.** A bipolar montage is a fixed linear
combination across channels; the anti-alias filter is a fixed linear operator
along time applied identically to every channel. They commute exactly, so a
montage derived from the 8 kHz store is the same result as montage-then-
resample. Baking a montage in would also bake in a per-contact lead assignment
that has been curated for one subject of twenty-nine, and would make G1's
common-mode check an assertion instead of a measurement. The store records
per-stream common-mode diagnostics at the native rate instead, so G1 has its
evidence without a second read of Box.

**HDF5, one file per block, chunked at full channel width.** Zarr would add
two dependencies and a large inode count for a benefit (concurrent intra-block
writes, object storage) that does not apply to one process per block on a
local disk. Parquet is a table format and continuous multichannel arrays are
not a table. NPY has no chunking, so a time-window read across channels costs
the whole array. HDF5 is already a dependency (`tdt_mat.py` reads it), gzip
and shuffle are standard filters, and MATLAB reads the result natively, which
matters for this lab. Chunks hold every channel and about 4 MiB of samples,
so the dominant access pattern, a time window across all channels, costs one
chunk; a single channel over a long span decompresses every chunk it spans,
the same tradeoff `tdt_mat.py` already documents. Crash safety comes from
writing to `.part` and `os.replace`, not from the format.

**Read the .mat export, not the .tev tank, wherever both exist.** The
inventory's 851 rows are 441 logical blocks; 389 exist as both. Tank-preferred
is 611 GB to transfer, .mat-preferred is 454 GB, and the .mat is chunked along
samples at full channel width, which is the windowed all-channel read the
build does, where `TdtTankRecording.read()` makes one strided pass over the
whole .tev per channel. Events still come from the .tsq index in every case,
because it is already staged and free.

**The store lives in `~/Dropbox/DBS Derivatives`.** Not `derivatives/`, which
sat inside a cloud-synced folder and would sync 50 GB of recordings to cloud
storage whatever `.gitignore` says. The staging archive stays local and
unsynced, because the crosswalk holding case numbers must never leave the
machine.

Two facts measured along the way that the build has to respect: the sample
rate does NOT follow block type (`clinical_dbs` carries `ecos` at 48828.125 Hz
in 13 blocks and 24414.0625 Hz in 2; `increment` has both), so rate is read
per stream per block; and `StreamInfo.start_time_s` on a tank is a Unix epoch
timestamp, so the store writes `t0_s = 0.0` and relative offsets only.

## 2026-09-09 Probability goes first, and two gaps are declared out of scope

**The course order changed.** The program opened with linear algebra and assumed
probability throughout: SIG 4 asserted a chi-squared distribution, INF 1 used an
effective sample size formula it did not derive, SPK 4 checked a phase-locking
null against a constant it did not explain. Each was correct and each was
asserted. STO 1 to STO 4 derive them, so Probability is now the first course in
Foundations and the order diagram gained an edge at the front rather than the
back.

That makes it the third course written out of dependency order, after Inference
and Decoding. The pattern is worth naming: the lessons that turned out to be
load-bearing were the ones nobody thought to write, because their results were
being used comfortably without them.

**Two gaps are now declared rather than pending.** Neuroanatomy and neuroethics
are in `docs/backlog.md` as curriculum gaps, and they are not going to be
filled here. Neither can be measured against a simulated ground truth, and the
rule that every number in a lesson is one its code printed is what makes the rest
checkable. Writing them would produce the only lessons in the program whose
claims could not be verified by running them, which would quietly change what a
lesson in this curriculum is. `curriculum/README.md` now says so under "What this
curriculum does not teach", so the absence reads as a decision rather than as
work outstanding. Lead localization stays open, because it is measurable.

**Two findings about shipped code, neither acted on, and one of them was wrong at first.** STO 1 found that
`recipes/psd.py` averages in decibels. STO 3 found that G9's excursion ratio
grows with recording length under a random walk, so it is not comparable between
runs. Both are measured in `docs/findings.md`, and the second has options in
`docs/backlog.md`.

The first was initially wrong, and the way it was wrong is worth recording. STO 1
derived the bias of averaging power and then converting, and attributed it to
code that converts and then averages. Those are different operations: the first
is low by an amount that shrinks with segment count, the second by a constant
2.51 dB. The lesson then reasoned from the wrong one to a contrast artifact of
0.51 dB that does not exist, and proposed a guardrail for it. A review caught it
the same day, the measurement now covers both orderings, and the proposal is
withdrawn in `docs/backlog.md` rather than deleted.

The correct answer inverts the original one: converting first is the cruder
operation and the safer one here, because a constant offset cancels in every
contrast at any segment counts, while the asymptotically unbiased ordering would
have introduced exactly the artifact the lesson wrongly claimed to find. What
survives is narrow: `normalize.py`'s centre of `none` divides a dB value rather
than differencing it, so the constant reaches z there alone.

The general lesson is the one this curriculum keeps relearning from the other
direction. The simulation was right, the closed form was right, and the sentence
connecting them to the code was not, which is the same failure mode as the seven
Section 5 errors the first audit found. Describing what code does is not a
substitute for measuring the thing it does.

## 2026-09-09 Three curriculum proposals answered

**G14, cross-validation folds must respect time: stays in the backlog.** No
recipe does cross-validation or decoding today, so the rule would have nothing to
fire on. It gets written with the first decoding recipe, against something
concrete, with the run-record field shaped to whatever that recipe actually
stores. The alternative, shipping it now as a placeholder, would put a rule in
`configs/guardrails.yaml` that cannot fire and would make GRL 5's index of
thirteen guardrails describe fourteen, one of which does nothing.

**G9 now reports the duration its ratio was measured over.** STO 3 measured that
a random-walk baseline's excursion grows as 1.6*sqrt(t), so the excursion-to-effect
ratio means different things in recordings of different lengths. `CheckContext`
gained `recording_duration_s`, the finding's message and detail carry it, and the
remedy says to compare only against runs of similar duration. The threshold is
untouched at 1.0, so no run's verdict changes and nothing already reviewed moves.
Normalising the excursion by sqrt(duration) was rejected: it assumes the
random-walk end of the spectral range that STO 2 showed real LFP only approaches,
it would need its own derivation and threshold, and it would change which runs
fire including ones already signed off.

**The `none` centre is documented rather than corrected.** `psd.py`'s constant dB
offset cancels in every contrast, and `normalize.py`'s centre of `none` is the
one option that divides rather than differences, so the offset reaches z there.
`configs/statistics.yaml`'s caveat now says so. Subtracting the constant was
rejected on a fact measured while framing the question: the offset is 2.51 dB on
the Welch path and 0.31 dB on multitaper, because MNE averages over DPSS tapers
before the dB conversion. `normalize.py` has no idea which method produced the
column, and on multitaper the number also depends on the taper count. A
subtraction that guessed the method wrong would be worse than the offset it
removed.

The pattern across all three: the measurement was worth having in every case, and
in every case the right action was smaller than the measurement suggested. Two of
the three ended in a sentence rather than a code change, and the third changed a
message rather than a threshold.


## 2026-09-09 The acquisition date comes out of subjects.csv

Decided by Garrett. `manifest/subjects.csv` carried a populated `acquisition_date`
for `the first subject analyzed`. For an intraoperative block that value is the date of surgery, which
the hard rule forbids anywhere in the repository. The value is now blank. The
literal date is deliberately not repeated here, because recording it in this file
would reintroduce exactly what the change removes.

The column was added on 2026-09-03 on the premise that the timestamp in a TDT
filename was an upload time, written on days deliberately separated from the
procedure. That premise was tested against the archive on 2026-09-09 and does not
hold: of 401 staged tanks, 287 filename dates equalled the acquisition date in the
block's own `Notes.txt`, 114 differed by exactly one day, and none was consistent
with an upload on a separate day. `configs/privacy.yaml` now sets
`filenames_deidentified` false for both TDT formats.

**Correction, 2026-09-10.** An earlier version of this entry said the config flip
"restores guardrail G13". That was wrong, and dbs-speech-app-98 caught it. G13
opens with `if not ctx.paths_in_outputs: return None`, and nothing populates that
field: `_shared_guardrail_context` in `recipes/psd.py` hardcodes it to the empty
tuple, and all six recipes import that helper. So G13 returns None on every run
whatever the config says. The flip changed the severity G13 would apply if it
ever fired, not whether it fires. The comment at that line, "Nothing writes a raw
path into its outputs", is an assertion standing in for the check: G13 exists to
verify exactly that claim and is handed the answer instead of the evidence. The
privacy work is not closed by the config change alone.

**The column stays, only the value goes.** Dropping it was considered and
rejected. A site that has confirmed its own filenames and acquisition dates are
not sensitive may legitimately want the field, and this branch generalizes for
other labs. `detect/manifest_rows.py` already emits the column empty and names it
in `LEFT_TO_REVIEW`, so blanking the value makes the one hand-written manifest
agree with what `draft-manifest` produces rather than standing as the single
exception.

`docs/schema.md` described the column as permitted by `configs/privacy.yaml`. That
was true when written and became false when the config reversed, so the row now
states the measurement and the resulting policy.

**What this does not do.** The date remains in git history from `6c40c99` onward.
Removing it there means rewriting `main`, which invalidates the worktrees under
`.claude/worktrees/`. That is a separate decision and has not been made.

## 2026-09-09 G9's duration comes from the window span, and leads.yaml gains a real spacing field

Two loose ends from the curriculum work, both closed.

**The duration G9 reports is the window span, not the sum of window durations.**
`_prepare_guardrail_context` already knows which windows a run reads, so the
duration is computable there for every recipe with no recipe change. The span
from the first window's start to the last window's end is the right quantity
rather than the total time inside the windows, because drift accumulates during
the gaps too, and it is elapsed time that sets how far a baseline can have
wandered. On the current manifest for the first subject analyzed the two differ by more than a factor
of two: 417 s of span against 188 s of window. `_window_span_s` returns None
rather than a wrong number when the manifest has no usable times, since a
guardrail quoting a fabricated duration is worse than one quoting none.

Worth stating plainly: nothing in the package computes `max_excursion_db` either,
so G9 does not fire on any real run today. This change means the duration will be
there when something does, not that G9 started reporting it.

**`configs/leads.yaml` now has `row_spacing_mm` and `spacing_confirmed`.** REC 5
computes distances from contact pitch and had to sweep a plausible range, because
the only spacing in that file lived inside model name strings like
"3389 (1.5 mm spacing)". A number a program cannot read is not configuration.

The field is defined precisely as centre-to-centre, because vendor literature
uses "spacing" for both the pitch and the gap between contact edges and those
differ by a factor of two on a typical lead. The two numbers now present were
transcribed from the model strings and are marked `spacing_confirmed: false`,
which says both that the value is unchecked and that which convention the model
string meant is unknown. That flag is separate from `confirmed`, which is about
contact numbering: a lead can have trustworthy numbering and unverified geometry.

Everything is unconfirmed today, so the correct number of places in the package
reading the field is zero, and a test asserts exactly that. When the first reader
appears it has to refuse on an unconfirmed spacing rather than proceed. REC 5
restates the two values with a test tying them to the config, and that test also
fails if either is marked confirmed, so the lesson's caveat about transcribed
numbers cannot silently become wrong.


## 2026-09-09 Unit tests were signing off a real subject

`tests/unit/test_cli.py` drove the command line against the real subject with no
`--derivatives`, so three tests read and wrote the repository's live QC store.
Two of them asserted that the subject was unreviewed and that `qc sign` would be
refused. Both were true when written. Once the subject was actually reviewed and
signed, `qc sign` stopped refusing and started succeeding, so the test that
existed to prove a refusal became the thing performing the signature.

`history.jsonl` for that subject holds 33 events: one real sign by `garrett`, and
32 by `g`, the dummy reviewer in the test file, one for each run of the suite
since. `approval.json` records whichever came last, so the reviewer of record on
an approved subject had become `g`. Because the suite is required before
declaring work done, following the workflow rule was what caused this, which is
why it accumulated unnoticed rather than being caught once. The last event, at
19:22:56, was appended while diagnosing this: confirming that the three failures
were not caused by an unrelated change meant running the still-unfixed tests
once more.

**What was and was not damaged.** Every one of the 32 events carries the same
`decisions_sha256` and the same flag count as the real sign. The test re-signed a
decision set identical to the one already approved, so no flag decision changed
and no scientific judgment was altered. The damage is to attribution and to the
audit trail, which for a component whose entire purpose is provenance is still
worth a record.

**The fix, and why the first test is shaped differently.** The two `qc` tests now
build a one-flag store under `tmp_path` and pass `--derivatives`, so they exercise
the same code against a store they own. The `run` subcommand has no
`--derivatives`, and adding one purely for a test would put a flag in the
interface that no operator needs. That test's stated contract is that the gate
gets its own exit code and message, distinct from a guardrail block, so it now
raises `QCNotApproved` directly and asserts the mapping. That is a narrower test
than before and a truer one: it no longer passes or fails based on the review
state of an unrelated subject.

Restoring the reviewer in `approval.json` is deliberately not done here. A
sign-off should be issued by the signing command and by the person signing, not
written into a JSON file by an agent repairing its own mess, so the field stays
as it is until Garrett re-signs through the CLI.

## 2026-09-09 Guardrails gain a second pass, after the recipe, and G9 goes live

G9 could not fire, and the reason was structural rather than a missing function.
Guardrails run before the recipe on purpose, so that a blocked run leaves no
directory and no record. G9 compares a baseline excursion to the effect a run
reports, and neither number exists until the recipe has produced one. Nothing in
`src/` set either input.

**A second pass runs after the recipe.** A recipe may declare
`guardrail_context_after(session, params, result)`; if it does, the runner
rebuilds the context with those fields and evaluates the checks again. Blocking
rules still run first and still block, so the no-record-for-a-blocked-run
property is untouched.

**That pass does not block.** `run_checks` gained `blocking=False`. Refusing after
the recipe has run would leave a half-written record and would not un-compute
anything, so a blocking rule that only becomes decidable afterwards is reported
loudly instead. Two tests cover it: one that the engine collects rather than
raises, and one that the runner actually asks for it, because the first passes
even if the call site forgets.

**It reports only what the result made decidable.** Every check runs again in the
second pass, so a rule that already fired before the recipe would appear twice
and the record would read as though the run tripped it twice. The post-run
findings are filtered against the pre-run ones.

**The record keeps its shape.** The pre-run block stays at the top level, so
`Result.tsx` and anything else reading `guardrails.findings` still works, and the
second pass lands under `guardrails.after`. The UI renders it under "Checked
after the run" rather than merging, because a reader should be able to tell what
was knowable before the data was touched.

**What psd computes, and what it refuses to.** `max_excursion_db` follows GRL 4's
definition exactly, smoothing with a moving average about a fifth of the series
before taking the peak-to-peak, because GRL 4 is where the threshold of 1.0 was
measured and a different smoothing would give a different number against the same
threshold. `reported_effect_db` is the largest condition contrast in the same
band and the same montage, because a ratio between numbers from different bands
compares nothing. The band comes from `configs/bands.yaml` through a new
`guardrail_band` parameter.

Three cases report nothing rather than a number: no baseline condition in the
run, an unconfigured band, and a baseline giving fewer than five segments per
derivation. The last was found by running it: the test fixture's two-second
windows produced an excursion of 0.0, which G9 would have read as a stable
baseline when in fact nothing had been looked at. An unmeasurable excursion is
not a small one.

**Still hard-coded, and not changed here:** `_summary` in psd.py filters beta as
13 to 35 Hz inline, while `configs/bands.yaml` says beta is 13 to 30. That
predates this change and moving it would alter a reported number, so it is noted
rather than fixed.

## 2026-09-09 Every dormant guardrail audited, G5 wired, G4 left alone

Making G9 live raised the obvious question: was it the only rule that could not
fire? Checking every `CheckContext` field against what `src/` actually sets found
two more, and one false alarm.

**The false alarm.** `ratio_before_average`, `emg_available`, `paths_in_outputs`
and `filenames_deidentified` appear only in `psd.py`, which looked like G3, G7 and
G13 working for one recipe. They are supplied by `_shared_guardrail_context`,
which lives in `psd.py` and is imported by all six recipes, so those rules were
already live everywhere. Worth recording because the grep was misleading in a way
that would have produced a confident and wrong change.

**G5 was dormant and is now live.** Nothing set `claimed_event_duration_s`, and
nothing could derive it: the duration of the event a run claims is a statement by
the analyst, not a property of the recording. The four recipes with an analysis
window now carry the field, defaulting to None, and the shared context helper
reads it off the params so a recipe without the field simply makes no claim.
G5 then compares it to the window: a 1 s window claiming a 50 ms burst is 20x
against a configured limit of 5x.

Defaulting to None matters. Every run has a window, so a rule that fired whenever
the window was long would fire on runs saying nothing about an event at all. A
guardrail cannot judge a claim nobody made.

**G4 is dormant by design and was left alone.** It guards a threshold applied
across conditions while comparing structure, and no recipe compares structure via
a threshold. Wiring it would put a rule in `configs/guardrails.yaml` that cannot
fire, which is the reasoning that kept G14 out. It becomes live when a recipe
that thresholds arrives, and not before.

**G9 now covers bandpower as well as psd**, and picks its band differently there.
`psd` takes the band from a parameter; `bandpower` computes many bands at once and
uses whichever carried the largest effect, so the excursion and the effect
describe the same band by construction rather than by an analyst lining them up.
Both refuse rather than report when the baseline gives too few epochs.

**A test that documented rather than checked.** The first version of the
bandpower test asserted that the reported band label matched the largest effect's
band. That label is assigned from the effect regardless, so swapping the
excursion to a different band still passed. It now recomputes the excursion from
the stored epochs in the named band and compares, and that version fails when the
band is swapped. The distinction is the point of the whole design, so a test that
could not see it was worse than none.
## 2026-09-09 The generalization branch is merged in rather than reimplemented

`generalize-for-other-labs` had already built BrainVision and EDF readers, a
shared MNE base, windows from task markers, coordinates, the paradigm
vocabulary, and two recipes. This branch had the API mount fix, the guided run
flow, the recipe chooser and `erna`. Neither was an ancestor of the other and
both descend from `main`, so the two halves of the app were diverging in
parallel: the readers had nowhere to be driven from and the interface had only
TDT to open.

Merging was the only option that produced a testable whole. Seven conflicts, all
resolved toward the union rather than a side: both sets of CLI subcommands, both
config files, both appended decision logs, all seven recipes. Two were genuine
disagreements. `Ask.tsx` had a subject selector added on one branch and removed
on the other; the selector stayed, because the objection that removed it was to a
*hard-coded* subject and a picker is the answer to that. The README kept this
branch's intro and layout table and the other's node_modules, VS Code and
curriculum sections.

The merge exposed a defect neither branch could have had. `seed` and
`test_seed.py` are this branch's; `erp_epochs` and `pac_modulation_index` are the
other's; and `test_every_registered_recipe_runs` asserts that every registered
recipe runs on the demo project. Neither recipe could. See the next entry.

## 2026-09-09 The demo recording is twelve seconds, not four

`test_every_registered_recipe_runs` is the only test that runs every recipe in
one pass, and after the merge two recipes failed it. A comodulogram needs ten
cycles of its slowest phase frequency inside a single window, which is 2.5 s at
the 4 Hz default, and the demo's windows were 1.5 s. An event-locked average
needs ten trials, and the four-second fixture carried six inside a window.

The cheap fix was to lower both floors in the demo parameters until four seconds
satisfied them. That was tried and rejected: a new lab member reading
`DEMO_PARAMS` would take a 10 Hz phase floor and a lowered trial minimum as what
these recipes need, and both numbers are the ones that decide whether the result
means anything. Theta-gamma coupling is most of why anyone runs PAC, and it lives
below the floor that would have been written down.

So `make_fixture` takes a `duration_s`, defaulting to the four seconds every
existing test asserts against, and the demo asks for twelve. Both recipes then
run at their real defaults. Two demo parameters remain, and both are about cost
rather than correctness: one montage instead of five, because `references=None`
means every scheme for these two recipes, and a decimated rate for PAC. Without
the montage limit the demo took over ten minutes.

## 2026-09-09 Guardrail context is attached to the function, and cannot be returned

`pac_modulation_index` and `erp_epochs` both built a guardrail context at the end
of a run and handed it back on `RecipeResult.guardrail_context`. Nothing read
that field. `registry.py` evaluates guardrails before anything is computed, from
`fn.guardrail_context`, and neither recipe set it. Both therefore ran against two
of thirteen checks, and the other eleven reported nothing because they were shown
nothing, which is indistinguishable in a run record from eleven checks that
passed.

Both now declare a module-level `guardrail_context(session, params)` that derives
everything from parameters and the manifest, as the other five do. A context
assembled after the computation could only ever have been a description of what
happened, not a gate on whether it should.

The field is removed from `RecipeResult` entirely. Keeping it would leave the
same mistake available, and the audit that found this made the point precisely:
had the field not existed, `guardrail_context=` would have been a `TypeError` at
import instead of eleven guardrails silently declining to fire.

## 2026-09-09 Run records carry no absolute paths

`runs/` is committed. A failed run stored `traceback.format_exception` verbatim,
and the traceback from a recording that will not open reports the path it tried.
Raw acquisition filenames are not de-identified at this site, `configs/privacy.yaml`
says so, and a surname and a date of surgery in a filename would have gone
straight into version control. That is the CLAUDE.md hard rule and guardrail G13.

The traceback is kept, because a run that vanishes when it breaks is a run nobody
can debug, and that is the reason it is recorded at all. Only paths are rewritten:
inside the repository they become relative, so a frame still names the file and
line; everywhere else the path becomes `<path>` and the line number and function
survive, which is the part that localizes a bug in a library.

Dropping the traceback was the other option and it costs more than it saves. The
paths outside the repository are the ones a reader of a run record cannot act on
anyway: they name a machine that is not theirs.

## 2026-09-09 G2 does not judge pac_modulation_index, and says so by omission

Attaching `pac_modulation_index` to the guardrail layer had an immediate effect:
`G2_effect_tracks_electrode_not_state` blocked every run of it. That is the fix
working. It is also a real question, and the answer decides whether a guardrail
is disabled or a valid recipe is unrunnable, so it was Garrett's.

The decision is to leave `per_contact_baseline_subtracted` unset. G2 returns
`None` on an unset field, so it declines to judge rather than passing, and the
distinction is visible in the code. Reporting `False` would assert that a
per-contact baseline step exists in this recipe and was skipped, which is not
true: there is no baseline condition in a comodulogram. Reporting `True` would
assert a step that was never performed, and a later reader could not tell an
asserted `True` from a performed one.

The substantive reason it is safe: Tort's modulation index is a normalized
Kullback-Leibler divergence computed within a single contact, so doubling that
contact's gain leaves it unchanged. G2 exists to stop a comparison that measures
which contact sits best, and gain is what "sits best" means here.

The residual risk was accepted knowingly and is recorded in `docs/findings.md`:
MI is invariant to gain but not to signal-to-noise, so a noisier contact reads
lower for reasons unrelated to coupling, and no guardrail checks that.

## 2026-09-09 Stimulation runs the length of the demo recording

Lengthening the demo to twelve seconds silently broke the review decision the
demo exists to teach. The stimulating contacts stopped being flagged as kurtosis
outliers, so `_split_decisions` found nothing to keep, and
`test_the_stimulating_contacts_are_kept_with_a_reason` failed with the flags
themselves gone rather than the decision being wrong.

The cause is a real property of the detector rather than a bug in it. Kurtosis is
taken as the median across 10 s blocks, deliberately, so that a threshold means
the same thing at any recording length. Three seconds of stimulation artifact in
a four-second recording dominates every block; the same three seconds in twelve
does not survive a median.

`erna_onsets(duration_s)` now continues the same 0.5 s cadence to the end of the
recording, and returns exactly `ERNA_ONSETS_S` at four seconds or less so the
ERNA tests that assert on it are untouched. Stimulation not stopping after three
seconds is also the truthful version.

## 2026-09-09 tfr_onset emits one map per window, and does not average repeats

The map key was `(lead, target, scheme, condition)` and did not carry the
window, so a second window for the same condition overwrote the first while
`provenance.append` went on recording both. `window_provenance.csv` would
therefore claim two windows had contributed to a map that came from one of them,
and nothing else in the output could contradict it. Latent only because every
manifest and every fixture in the project had exactly one window per condition,
which is not the shape of a repeated-trial paradigm.

The key now carries the onset. What to do with the repeats was Garrett's call and
the answer is to keep them separate: one map per window, no averaging. The reason
it is a decision rather than an oversight is that the mean of per-trial decibels
and the decibels of the mean are different numbers, and which one a reader wants
depends on the question they are asking. The recipe stops guessing.

Consequences worth knowing. `tfr_long.parquet` gains an `onset_s` column and the
netCDF map labels gain the onset, so both are wider than before for a manifest
with repeats and identical for one without. `summary.json` gains
`n_windows_per_condition`, because a reader counting conditions would otherwise
expect fewer maps than there are. The figure draws one panel per window rather
than per condition, and titles the column with the onset when a condition has
more than one; past `MAX_FIGURE_COLUMNS` it draws a sample and says so in the
log, because a figure with forty panels is not a figure.

The figure previously took `match[0]` when several maps shared a condition, which
drew one arbitrary trial under the condition's name. That is gone with the cause.

## 2026-09-09 The window skips that make one time axis possible now have tests

A window too near the start of a recording cannot supply the requested pre-onset
period, and one too near the end cannot supply the post-onset period. Both are
already skipped rather than shortened, which is what lets every surviving map
share one time axis and the netCDF stack succeed.

Neither skip had a test. The audit reached the same conclusion from the other
branch, where the guards do not exist and the run dies at the write step after
all the expensive work is done. Three tests now cover it: a window at 0.5 s with
tmin at -2.0, a window at 9.5 s with tmax at +5.0 in a twelve-second recording,
and the invariant those two exist to protect, that every map in the netCDF spans
exactly the requested range.

The recipe also now raises if two windows somehow produce different time axes,
rather than silently keeping the last one. That should be unreachable; the
failure it prevents is a map carrying a time axis that is wrong by an offset,
which produces no exception and a wrong figure.

## 2026-09-09 Two endpoints that wrote without a role, and a path that escaped

Round 2 of the audit found both. Neither was reachable from the interface, which
is why neither had been noticed: the app does not call them the way an attacker
would.

`POST /qc/{study_id}/decisions/bulk` had no `require_role` dependency while
`PUT /qc/{study_id}/decisions`, `POST /qc/{study_id}/sign` and
`POST /qc/{study_id}/reopen` all required a reviewer. It is the write that
decides many flags at once, so it was the cheapest way to approve a subject's
entire QC without being anybody. It now requires a reviewer, like its siblings.

`POST /uploads` had no role either, and worse, it built its target as
`UPLOAD_DIR / study_id / session` from raw query parameters. The filename was
reduced to its basename; the directory components were not. Measured:
`study_id="../../.."` resolves to `/etc`. Combined with no authentication, an
anonymous caller could write a file with an allowed extension anywhere the
process could write, and the upload area is inside `data/`, which is the
symlink into synced storage, which means it would also have synced.

Study IDs and session names now go through `_check_identifier`: letters, digits,
underscore and hyphen, one to sixty-four characters. Deliberately stricter than
necessary. No dots, so no traversal; no separators of any kind, so no new one.
The resolved target is then checked to be inside the upload area anyway, because
the identifier rule is what stops this and the containment check is what catches
the next way somebody finds around it. `GET /uploads` is a directory listing of
`data/` and now takes a role too.

Twelve tests, because the failure mode is silent and the fix on each endpoint is
a single dependency argument that a later refactor can quietly drop. The
traversal cases assert not only the status code but that nothing was written.

## 2026-09-09 Stage 2 of the audit, and one finding it got wrong

Four changes that move numbers, each with a `docs/findings.md` entry. Garrett
chose each; the evidence for each was measured here rather than taken from the
audit, and that mattered once.

B5, the pooled scale. `pooled_within_condition` returned
`groupby(key)[sd_col].mean()`, the arithmetic mean of the per-condition standard
deviations. A pooled SD is the root of the segment-weighted mean of the
variances. `n_segments` was already on every row, so the correct weighting cost
nothing. Verified against the closed form on six cases including the degenerate
one where every condition contributed a single segment and each weight is zero,
which falls back to the unweighted root mean square. The project's own fixture
moves by 8 percent, and an existing test asserted the wrong value: the test and
the code agreed with each other and both were wrong, which is the failure mode
worth naming.

`across_conditions` now refuses a group with one condition rather than returning
`std` of a single value, which is NaN, which emptied the whole z column silently.

B7, the taper. The branch named `welch` called `scipy.signal.spectrogram`, whose
default is `("tukey_periodic", 0.25)`. Median 11.9 percent from
`scipy.signal.welch` on the same data. The test asserts against the library
rather than a stored number, so scipy changing its defaults again is caught
rather than absorbed, and a second test checks the library default still differs
so the first cannot go vacuous.

B7b, the one the audit got wrong. It reported that 50 percent overlapping
segments are correlated and therefore make `db_sd` underestimate the spread, and
recommended dropping to non-overlapping segments. Measured across white, pink and
1/f^2 noise at three durations, the overlap SD is 0.4 to 2.6 percent HIGHER, and
the lag-1 correlation is +0.014. A Hann taper downweights the segment edges,
which is exactly where overlapping segments share samples, which is why Welch
specified 50 percent. Making that change would have discarded half the data and
inflated z. What was real in the finding is the asymmetry underneath it: welch
overlapped and multitaper did not, so `db_sd` was not comparable between methods.
Multitaper now steps by half a segment too.

The general point is worth keeping. An audit finding is a hypothesis with a file
and line attached. Three of these four survived measurement and one did not, and
the one that did not was the one whose recommended fix would have made the
numbers worse.

B6, multiplicity. The note counted the primary montage while `stats.csv` carried
all five, and the summary printed the larger `n_contrast_rows` on the next line,
so it disagreed with itself in one screen. It now reports both, because a reader
who fixes on a montage in advance is in a different position from one who reads
five and reports the best.

B8, the unit modes. No numbers change. `unit="window"` was documented as "honest
at n=1" while its `db_sd` is the spread across the spectral segments inside the
window, which is a large n and a legitimate scale, just not the one the sentence
promised. The description now says what the number is.

## 2026-09-09 The wavelet pad matches the kernel MNE actually convolves

`_pad_seconds` returned half the nominal wavelet duration. MNE builds a Morlet
out to five standard deviations either side, which is 0.3975 s at the defaults
against a supplied 0.25 s: 37 percent short, and short at every frequency rather
than only at the low edge, because the default tiling makes sigma_t constant.

The pad is now `5 * n_cycles / (2 * pi * f)` maximised over the grid, rounded up
to a whole sample at the analysis rate. The rounding is not decoration: MNE
rounds its kernel to an integer sample count and can round up, so the analytic
five sigma can be short by a fraction of a sample, which a test caught.

Two consequences worth naming. The start and end skips now include the pad, so a
window whose padding would run off the recording is skipped rather than having
`read_from` clamp silently at zero; without that the guarantee held only for
windows that happened to sit far enough in. And measured on both the demo and
`manifest/windows.csv`, the larger pad costs no windows at all, so this was a
correctness fix with no tradeoff to weigh.

`test_no_reported_point_sits_on_an_edge` asserted that the reported time range
lay inside the requested bounds, which is a claim about cropping, not about
padding, and is not what its name says. It has been split: the range assertion
keeps a name that describes it, and a new test with the old name checks the pad
against MNE's real kernel length at four different `n_cycles_factor` values.
A second test asserts that MNE's kernel still exceeds the old rule, so the first
cannot quietly become vacuous if MNE changes.

## 2026-09-09 tfr_onset floors n_cycles at 3, and reports its own time resolution

Garrett's call, taken after the numbers were corrected: I had quoted the cost of
this option as a pad of 2.39 s, which is the full kernel length rather than the
half-support. The real figure is 1.19 s, half what I said, and it costs no
windows on the real manifest.

`n_cycles = 0.5 * freq` is a constant-duration tiling, which is a reasonable
choice for an onset analysis because time resolution then does not degrade down
the map. It breaks at the bottom: 1.0 cycle at 2 Hz is an envelope detector, so
the map advertised delta and theta and measured something else there.

The floor makes the low end real. The alternative was to raise `fmin` out of the
broken region, which was rejected because this is a speech project and the speech
envelope and syllable rate live in exactly delta and theta.

The cost is time resolution below 5.42 Hz, and that cost is inherent rather than
introduced: a 2 Hz event cannot be localised better than about half a cycle by
any method. `summary.json` now carries `time_resolution_s` per frequency, plus
`min_cycles_binds_below_hz`, so a reader seeing a smear near onset in the bottom
rows can tell it is the wavelet rather than the brain. `min_cycles=1.0` restores
the old behaviour for anyone who wants constant-duration tiling deliberately.

## 2026-09-09 An empty baseline raises instead of returning raw power

`_apply_baseline` returned `power` unchanged when the baseline mask selected
nothing. The caller then stored it and labelled it with the unit implied by
`baseline_mode`, so unbaselined power of order 1e-10 was written as decibels and
drawn on a colour scale shared with maps that really were decibels.

Reachable from ordinary parameters: `tmin=0.0` with the default baseline of
[-2.0, -0.25] selects no samples.

A model validator on `TfrParams` now rejects a baseline that does not intersect
the epoch, so it costs a validation error before anything is read rather than a
wasted convolution over every channel, and the Check step in the interface shows
it before the run is submitted. `_apply_baseline` still raises if it is somehow
reached with an empty mask, because a backstop that returns a plausible-looking
wrong answer is worse than no backstop.

## 2026-09-09 Every key in guardrails.yaml is read, or it is not a key

The config presented tunable thresholds that no code consumed. A lab lowering
`max_corr_with_baseline` would see the file change, see no behaviour change, and
conclude the guardrail had been retuned. That is worse than having no knob: it is
a false assurance, and the file is the surface a site is invited to tune.

The audit reported ten such keys. Verifying it found eleven, because it missed
`policy_source` on G13. Writing a test that fails when any key is unread found a
twelfth, `require_override_reason` under `defaults:`, which neither pass caught
because both had looked only under `guardrails:`. That key was the worst of the
set: an override without a reason is refused unconditionally by
`Override.__post_init__`, so the key implied a switch that, had anyone set it to
false, the code would have gone on ignoring. It is gone, and the reason it cannot
be configured is written where it used to sit.

Garrett chose prose over implementation for the rest, which is the smaller and
more honest change: none of the removed keys had a calibrated threshold behind
it, so wiring them up would have traded a silent no-op for a number invented
here. `docs/guardrails.md` now says, per guardrail, what the check actually tests
and what the removed keys described, including that G1 is a parameter test
wearing a data test's documentation.

One key went the other way. `antialias_cutoff_fraction_of_nyquist` had a real
consumer waiting: seven call sites across the recipes hard-coded `sfreq * 0.4`,
which is the same quantity as `0.8` of Nyquist written against the sampling rate,
duplicating `preprocess.DEFAULT_CUTOFF_FRACTION` and ignoring the config that
claimed to control it. `preprocess.cutoff_fraction_from` reads it now, the
recipes call `usable_bandwidth_hz` with it, and the shipped value reproduces the
old number exactly, so nothing moves unless somebody edits the file, which is the
point. `manifest.load_configs` gained `guardrails` so a session can see it.

The test that found the twelfth key stays: any future key that nothing reads
fails the suite, naming the key and offering both remedies. It is a crude textual
search on purpose. It cannot tell whether a key is used correctly, only whether
deleting it would be noticed, and that is the failure being guarded against.

While writing the prose, one thing became clear enough to state plainly rather
than leave implicit: G13 inspects `paths_in_outputs`, and the single place in the
package that populates that field sets it to the empty tuple, so G13 has never
fired on any run. Redacting run-record tracebacks closed the path that actually
leaked; the check meant to catch that class of leak in general still does not
work. It is written down in `docs/guardrails.md` rather than left as a key that
looks like configuration.

## 2026-09-09 ch_index is validated as a channel number

`io/loader.py` turns `ch_index` into a numpy index as `int(ch_index) - 1`, and
`manifest.validate` checked neither the value nor, effectively, its identity.

`ch_index = 0` became `-1`, which numpy resolves to the last channel of the
stream. It is in range, so nothing raises, and a contact is analysed under
another contact's name. Round 2 of the audit corrected round 1 by noting that an
out-of-range index does raise `IndexError` in both readers, which is true and is
why index zero is the dangerous case rather than the obvious one.

Identity keyed on the raw string, so `"1"` and `"01"` were two rows to the
validator and one channel to the loader: two contacts, one physical signal, and
no duplicate reported. Keying on the parsed integer fixes that.

Validation now requires `ch_index` to parse as an integer, to be at least one,
and to fall inside the `n_channels` that `streams.csv` declares for its stream.
The last of those turns an `IndexError` in the middle of a run into an error
before it starts.

## 2026-09-09 One long table, one frequency grid

`_segment_spectra` clamped with `nperseg = min(nperseg, data.shape[1])`, so a
stretch shorter than `window_s` silently got a coarser frequency grid, and those
rows joined the same long table as everything else. Grouping on `freq_hz`
afterwards neither fails nor warns.

The audit called this latent. It is not. Measured: against a 1.0 s request, a
0.6 s stretch produces 301 bins at 1.667 Hz spacing where a full one produces 501
at 1.000 Hz, and the two share 101 bins, every 5 Hz, because 1.667 times three
and 1.000 times five are both 5.0. Partial overlap is worse than none. Some rows
compare and most do not, so a grand mean is taken over a mixture of two
resolutions rather than obviously splitting into two groups.

It was also reachable on every run of the demo and most of the bandpower tests,
which paired `epoch_s` of 0.2 or 0.5 with the default `window_s` of 1.0. Two
tests already passed a matching `window_s`, so somebody had noticed the pairing
mattered without noticing why.

That pairing is a contradiction: frequency resolution is one over `window_s`, and
an epoch cannot supply more resolution than its own length. Both parameter models
now refuse it, with the arithmetic in the message. Refused rather than clamped,
because clamping is what made it invisible. `_segment_spectra` raises on a short
stretch as a backstop, and both recipes skip a stretch that cannot fill the
window, logging it and recording it in `summary.json` under
`skipped_short_stretches`, because a skipped stretch is a dropped observation and
the log is read while the run happens rather than afterwards.

`requested_nperseg` is now the single definition of that number, because the
recipes and the skip checks all have to agree on it, and a disagreement between
them is exactly what put two grids in one table.

The demo's `bandpower_contrast` parameters gain `window_s: 0.5` to match their
`epoch_s`, so the walkthrough stops teaching the contradiction.
