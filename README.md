# dbsspeech

Analysis for intraoperative deep brain stimulation and ECoG recordings: the
subcortical recordings made during electrode implantation, with speech, movement
and stimulation conditions.

It exists so that an analysis is reproducible by someone who was not there. Every
result carries the claim it was meant to support, the code that produced it, the
parameters, what quality control removed, and every methodological check that
fired. A figure without that is a picture.

It also carries a **curriculum**: 46 lessons on the mathematics behind the
guardrails, at graduate level, in `curriculum/`, surfaced by the Learn section of
the app, and executed on every commit. See
[`curriculum/README.md`](curriculum/README.md) for the index and reading order.

The lessons stand alone. They do not import this package, and you can take the
whole course without installing it:

```bash
pip install -r curriculum/requirements.txt
jupyter lab curriculum/
```

MIT licensed. See [`LICENSE`](LICENSE).

## Ten minutes, no recordings needed

```bash
uv sync --extra dev
uv run python -m dbsspeech seed
```

`seed` builds a demo project under `demo/`: a synthetic subject with a planted
20 Hz oscillation and a planted 250 Hz resonance after each stimulation
artifact, taken through the real QC review and run through every recipe. It
prints the command to open the app against it.

The manifests in `manifest/` ship **empty**, with headers only. There is no
bundled subject, because a real one cannot be published and a fake one in the
authoritative table invites someone to analyze it by accident. `seed` writes its
demo into its own tree and never touches `manifest/` or `data/`.

For the web interface as well:

```bash
npm --prefix web install
./scripts/dev.sh          # API, a worker, and the web app together
```

App at http://127.0.0.1:5173, API docs at http://127.0.0.1:8000/docs.

## What it does

- **Reads** TDT recordings (MATLAB exports and native tanks), BrainVision and
  EDF, behind a format-agnostic reader. Raw files are opened in exactly one
  place, `src/dbsspeech/io/`.
- **Describes** them in a hand-curated manifest, the authority on what was
  recorded: leads, targets, contacts, streams, and condition windows with their
  provenance. Nothing is inferred from a filename.
- **Reviews** them: automatic detection proposes flags with evidence, a person
  decides each one and signs, and until they do, an approval gate refuses every
  analysis on that subject from every direction, including the Python API.
- **Analyzes** them through recipes: spectra by condition, band power contrasts
  with permutation tests, time-frequency around onset, phase-amplitude coupling,
  event-locked averages, py_neuromodulation's feature set, and ERNA.
  `docs/recipes.md` lists every parameter and is generated from the registry.
- **Checks** each run against thirteen guardrails before anything is computed,
  each one drawn from a way of getting a wrong answer that looks right.
- **Records** all of it in a run record per run, and packages it into an export
  bundle whose README reads without this software.

Nothing leaves the machine. There is no model call and no cloud service.

## Using your own recordings

The manifest is the contract, and it is written by hand on purpose. Read
[`docs/schema.md`](docs/schema.md) first: five CSV files, ten invariants, and a
validator that names the term it did not recognise rather than guessing.

```bash
python -m dbsspeech validate                       # manifest against the schema
python -m dbsspeech status                         # subjects, QC state, queue, runs
python -m dbsspeech qc detect --subject <study_id>  # propose flags
python -m dbsspeech qc list   --subject <study_id>  # review them
python -m dbsspeech qc sign   --subject <study_id> --reviewer <name>
python -m dbsspeech run psd_by_condition --subject <study_id> --claim "..."
python -m dbsspeech ask "beta in the STN during overt speech"
```

`ask` proposes a recipe and parameters, explains each choice, shows the
guardrails that would fire, and prints the exact `run` command. It never runs
anything itself.

### Known limitations, before you trust a number

**Lead geometry is unverified for two models.** `configs/leads.yaml` carries
`row_spacing_mm: null` and `spacing_confirmed: false` for the models whose
inter-row spacing has not been checked against an implant record or a vendor
drawing. Anything that depends on physical distance between contacts will refuse
rather than guess. Supply your own confirmed geometry for your hardware.

**Rotation gates direction claims.** A lead with an empty `rotation_deg` blocks
every anatomical direction claim, by design and by test. A contact coordinate
does not lift that: a position locates a contact and says nothing about which way
a directional segment faces.

**Windows carry their provenance, and `assumed` means assumed.** If a condition
boundary was not measured from a microphone, EMG, video or a real task marker,
say so in `derived_from` and guardrail G10 will flag every result that depends on
it. That is the intended behaviour, not a nuisance.

## Rules the code enforces

Full text in [`CLAUDE.md`](CLAUDE.md), which is written for this lab but whose
first four rules are worth adopting anywhere.

1. **Study IDs only.** No names, MRNs, initials, or dates of surgery anywhere:
   code, comments, filenames, commit messages, logs, or figures. Whether a
   recording *date* is safe to record depends on your protocol and your IRB;
   `acquisition_date` ships empty and empty is the safe default.
2. **`data/` is read-only.** Nothing here writes to a recording, and no analysis
   deletes samples. An artifact becomes an annotation.
3. **Every analysis goes through `registry.run`.** That is what produces the run
   record and enforces the QC gate. There is no quick check that skips it.
4. **Bands, thresholds and windows live in `configs/`,** never in code, and are
   editable from the app with a recorded author and reason.

## Tests

```bash
uv run pytest -q -m "not realdata"    # everything that needs no recordings
uv run pytest -q -m realdata          # only with data/ mounted
```

Three markers: `unit` (fast, no recordings), `integration` (several components on
synthetic data), and `realdata` (reads `data/`, skipped automatically when it is
empty, so a clean checkout runs green). Test fixtures are generated by
`tests/fixtures/make_*_fixture.py` rather than committed, so there is nothing to
download.

The curriculum has its own file, which executes every solutions notebook and
checks that their claims still match `configs/`:

```bash
uv run pytest tests/unit/test_curriculum.py
```

That one is memory-hungry, because it executes 46 notebooks. To work through the
lessons rather than test them:

```bash
uv run jupyter lab curriculum/
```

`docs/recipes.md` is generated, and a test fails when it goes stale:

```bash
uv run python scripts/gen_recipe_docs.py
```

## Documentation

New here? [`docs/install.md`](docs/install.md), then
[`docs/concepts.md`](docs/concepts.md). Twenty-five minutes, and the second one is
the part that matters.

| | |
|---|---|
| `docs/install.md` | setting it up, and the ten-minute walkthrough |
| `docs/concepts.md` | the five ideas the whole thing rests on |
| `docs/schema.md` | the manifest, and the ten invariants it obeys |
| `docs/guardrails.md` | the thirteen checks, and where each came from |
| `docs/qc-guide.md` | how to review a subject, and what the decisions mean |
| `docs/recipes.md` | every recipe and parameter, generated from the registry |
| `docs/architecture.md` | how the pieces fit |
| `docs/decisions.md` | why things are the way they are, dated |
| `docs/findings.md` | what analysis has shown, dated |
| `docs/troubleshooting.md` | errors actually hit, and what they meant |
| `docs/maintenance.md` | adding a subject, a recipe, a threshold, a dependency |
| `docs/deploy.md` | putting it on a lab machine |
| `docs/interop.md` | reading results from MATLAB |
| `docs/CHANGELOG.md` | what exists, and the known gaps |
| `docs/build-status.md` | where the build is, and what is next |
| `docs/backlog.md` | noticed, deliberately not done yet |

## Layout

| Path | Holds |
|---|---|
| `src/dbsspeech/` | the package: `io`, `qc`, `recipes`, `guardrails`, `runs`, `jobs`, `api` |
| `manifest/` | the data contract, hand-curated. Ships empty |
| `configs/` | bands, thresholds, statistics options, lead geometry, ERNA settings |
| `data/` | raw recordings. Read-only, never committed |
| `derivatives/` | results and QC decisions. Regenerable, never committed |
| `runs/` | one JSON record per run. Small, text, safe to commit |
| `var/` | accounts and config history. Backed up, never committed |
| `web/` | the front end: Vite, React, TypeScript. Node 20.19 or newer |
| `docker/` | the deployment |
| `tests/` | `unit`, `integration`, `realdata` |
| `curriculum/` | 46 lessons, and the generators that emit them |
| `scripts/` | one-off and batch entry points |

Nothing derived from a recording belongs in version control except the run
records in `runs/`, which are small, text, and carry the provenance needed to
regenerate everything else. A failed run's traceback is scrubbed of absolute
paths before it is written there.

## Deployment

`docker/` holds a compose file, an nginx front end, and a worker.
[`docs/deploy.md`](docs/deploy.md) is the guide. Two things to know before you
expose it beyond localhost:

- The API publishes on `127.0.0.1` by default. `BIND=0.0.0.0` binds **every**
  interface, including whatever network the machine is on at the time. To reach
  it from one other machine, bind that machine's address specifically.
- `DBSSPEECH_REQUIRE_AUTH=true` gates every write. Read routes are currently
  open, so treat the port as readable by anyone who can reach it, and create an
  account with `scripts/ship.sh admin` before you rely on it.

**This has not had an independent security review.** It was built for a single
lab on a trusted network, and it should not be exposed to the internet without
one. `scripts/ship.sh funnel` exists for a tailnet, not for the public. If you
deploy it somewhere reachable, put it behind your institution's own
authentication and treat the read surface as open.
