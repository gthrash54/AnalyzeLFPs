# Changelog

What changed, and what it means for someone using this. The reasoning lives in
`docs/decisions.md`, dated to match.

## Unreleased

Not tagged v1.0.0 yet, deliberately. The guide puts the tag after the pilot, and
two things are still open: nobody outside the people who built it has used it,
and the container image has never been built. Tagging now would put a version
number on a claim that has not been tested.

### The analysis layer

- Five recipes: `psd_by_condition`, `bandpower_contrast`, `tfr_onset`,
  `pynm_features`, and `erna`. Every parameter is documented in
  `docs/recipes.md`, generated from the registry.
- Thirteen guardrails, evaluated before anything is computed, each one drawn
  from a trap somebody has actually fallen into.
- A QC layer where detection proposes with evidence and a person decides, with
  an approval gate enforced in the package so every path reaches it.
- Run records carrying the claim, the code, the parameters, the inputs by hash,
  what QC removed, and every check that fired. Export bundles that read without
  this software.

### Running it

- Runs execute in a worker process against a database-backed queue, so a run
  survives an API restart and its status is readable by every process.
- A deployment in `docker/`: one image for the API and the worker, a health
  endpoint reporting versions, database connectivity and worker heartbeat, and a
  backup script with a tested restore.
- `python -m dbsspeech seed` builds a demo project in about twenty seconds: a
  synthetic subject through the real QC review and one run per recipe.

### The interface

- The run flow is four steps rather than one page of thirty fields. The agent
  chooses the analysis from a plain-language question, explains every value,
  re-checks what you edit, and dry-runs the guardrails against it, so what is
  about to happen is on screen before the button.
- QC review can express the decision that matters: a flag can be real while the
  proposed action is wrong. The words a reviewer reads come from
  `configs/qc_thresholds.yaml`.
- One set of shared components and one set of design tokens, described in
  `web/DESIGN.md`.

### Known gaps

- The container image has not been built. First `docker compose build` on the
  target machine is the test.
- ERNA's settings are unreviewed defaults until someone who knows the
  stimulation protocol sets them; every run says so on its figure.
- QC thresholds are uncalibrated against real recordings.
- No pilot has happened. Nobody outside the authors has used this.
