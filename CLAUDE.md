# dbsspeech

Analysis app for intraoperative DBS (STN/GPi) and ECoG recordings.
Python package + FastAPI + React. Read docs/architecture.md and
docs/schema.md before touching data code.

## Hard rules
- Study IDs only. Never write patient names, MRNs, initials, dates of
  surgery, or any identifier anywhere: code, comments, filenames, commit
  messages, run records, logs, tests, docs. If you encounter one, stop
  and tell me.
- Raw BrainVision files (.vhdr/.eeg/.vmrk) are opened ONLY in
  src/dbsspeech/io/. Everything else consumes BIDS or derivatives.
- Never delete samples from recordings. Artifacts become annotations.
- Every analysis runs through registry.run so it gets a run record and
  passes the QC gate. No exceptions, including 'quick checks'.
- The QC gate (qc/gate.py) is enforced in the package. The UI reflects
  it and never reimplements it.
- Bands, thresholds, windows, subject lists live in configs/. Never
  hard-code them.
- Prefer MNE, mne-bids, scipy, py_neuromodulation functions over
  hand-rolled DSP. Name the library function in the docstring.
- data/ is read-only. Never write into data/ or into BIDS raw folders.
- Do not touch anything outside this repository.

## Asking
- Ask with the structured multiple-choice question tool, never as prose
  buried in a report. Every open decision gets options with their real
  tradeoffs stated, including the one you recommend and why.
- Ask ONE question at a time and wait for the answer before the next,
  unless I say otherwise. A batch of four is harder to answer well than
  four single questions.
- Ask on science, decide on engineering. Structure, naming, tests, and
  tooling are yours. Anything that could change a scientific result, or a
  number that would reach a figure, a paper or a talk, is the
  maintainer's.
- If I answer with a question back, answer it, give a recommendation, and
  proceed. Do not re-ask.

## Workflow
- For any change touching more than three files: write a plan listing
  files to create/modify, then wait for my go.
- Run 'uv run pytest -q -m "not realdata"' before declaring done.
  Run realdata tests too when data/ is mounted.
- Prefer small, reviewable diffs. I read every diff, meaning every
  authored diff: uv.lock and other generated files get a line count, not
  a read. A review pass that includes 2,300 lines of resolved
  dependencies trains you to click through everything, which is how the
  one real change gets missed. Start with 'git diff --stat', then read
  what a person wrote.
- When unsure about a library API, inspect the installed package or
  say you are unsure. Do not guess signatures.
- New scientific findings: one dated line in docs/findings.md.
- Engineering decisions with tradeoffs: dated entry in docs/decisions.md.
- Missing features noticed while doing something else go to
  docs/backlog.md, not into the current change.

## Style
- Python 3.11+, type hints, pydantic for parameter models, ruff clean.
- Tests: unit (no data), integration (fixture), realdata (skipped
  without data/).
- TypeScript strict; no 'any'.
- Figures: matplotlib, PNG + SVG, run_id in the caption.
- American English in all text. No em dashes.
