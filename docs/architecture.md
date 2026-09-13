# Architecture

Status: scaffold. This describes the intended shape, not code that exists.

## Shape

A Python backend does all computation. A React front end, added later, is a client
over an HTTP API and holds no analysis logic. Nothing in the front end should be able
to produce a number that the backend cannot reproduce from a run record.

```
BrainVision export        manifest/            configs/
(.vhdr/.eeg/.vmrk)        subjects.csv         bands.yaml
        |                 channels.csv         qc_thresholds.yaml
        v                        |                    |
   dbsspeech.io  <---------------+--------------------+
        |
        v
   dbsspeech.qc          channel and segment flags, never silent drops
        |
        v
 dbsspeech.recipes       versioned analysis units
        |
        v
   dbsspeech.runs        run record + outputs -> derivatives/
        |
        v
   dbsspeech.api         FastAPI surface -> React client
```

## Packages

`io`
: Readers, one per acquisition format, behind a single loader that dispatches on
  the `format` column of `manifest/subjects.csv`. `tdt_mat` reads TDT MATLAB
  v7.3 files, which are HDF5, so one stream or one time window can be pulled
  without loading the whole file; `brainvision` reads stage 2 exports. Adding a
  format is a new reader plus a new value in the manifest, not a change anywhere
  downstream. The only place that touches the file system for raw data.

`qc`
: Threshold checks from `configs/qc_thresholds.yaml`. Produces a report of flags.
  Deciding what to exclude is a caller's job, not this package's; the report is
  advisory and always written out.

`guardrails`
: Method checks that run before and after a recipe, described in
  `docs/guardrails.md`. Distinct from `qc`: QC asks whether the signal is usable,
  guardrails ask whether the analysis about to be run answers the question it
  claims to. Each check explains itself, can be overridden, and records the
  override with its reason in the run record. This is what lets a first-year
  student produce an analysis a PI would accept.

`recipes`
: Analysis units. Each recipe is versioned, declares its inputs and parameters,
  and is pure with respect to the file system apart from what `runs` hands it.
  Changing a recipe's behavior means bumping its version, not editing history.

`runs`
: Execution and provenance. Given a recipe, a subject set, and a config, produces
  a directory under `derivatives/results/<run_id>/` with the outputs, and writes the
  run record to `runs/<run_id>.json` recording code version, config hash, input
  hashes, parameters, and user. `runs/` is committed; `derivatives/` is not.

`api`
: FastAPI application exposing manifests, QC reports, recipes, runs, and the
  agent session. Thin. It validates with Pydantic models and delegates.

`agent`
: The conversational layer. A user describes what they want to look at, the agent
  proposes a recipe and parameters, explains the tradeoffs and any guardrail that
  applies, and runs it on confirmation. It composes existing recipes and never
  computes anything itself, so every number it produces still carries a run
  record. Not in the original build guide; added because talking through an
  analysis and then performing it is the point of the app.

## Conventions

- Manifests are hand-curated and authoritative. Code never infers a subject's
  hemisphere or a channel's region from a file name.
- Band edges and QC thresholds live in `configs/`. A literal frequency in analysis
  code is a bug.
- Every number that reaches the front end traces to a run record in `runs/`.
- No patient-identifiable information anywhere in this repository, including
  manifests, commit messages, and test fixtures.

## Two audiences

The interface has to work for a PI who will notice a wrong montage immediately,
and for a first-year student who does not yet know montage matters. The
resolution is that the guardrail layer carries the expertise: defaults are the
careful choice, deviations are explained rather than forbidden, and every
override is recorded. Neither audience gets a different pipeline.

## Open

Stimulation artifact handling, the ERNA path, and word-level alignment are
unsettled. See `docs/decisions.md`.
