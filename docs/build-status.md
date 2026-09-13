# Build status

> **the first subject analyzed is approved.** Signed 2026-09-09 by garrett. The 51 outstanding flags
> were all `amplitude_window`, and they turned out to be six synchronous events
> rather than 51 problems: whole-array excursions at 21, 23, 25, 31, 290 and 291
> seconds, most of them on every contact of both leads at once. An excursion on
> sixteen contacts of two separately implanted leads in the same second is one
> event in the room, not sixteen bad channels. Treated as artifact and
> annotated, which removes nothing, and marked provisional pending the PI's review.
>
> Real-data runs are therefore unblocked for the first time.

Where we are against the build guide (`dbsspeech_build_guide.docx`, v1.0,
2026-09-03). This file is the tracker so any session can pick up without reading
the guide.

Status values: **done**, **blocked**, **pending**, **changed** (being done
differently from the guide, with the reason in `docs/decisions.md`).

## Phases 0 to 3

| Step | Title | Status | Note |
|---|---|---|---|
| P0.1 | Scaffold the repository | done | Two guide defects fixed: fixture gitignore, summary.json vs run record. |
| P0.2 | Install the harness rules | done | Appendix B adapted to the current settings schema. |
| P0.3 | Inspect a raw recording | done | Done as TDT rather than BrainVision. Layout in `docs/datasets/`. |
| P1.1 | Data contract | done | `docs/schema.md` plus `manifest.py`, ten invariants, all violations reported at once. |
| P1.2 | Reader layer | changed | TDT rather than BIDS conversion: `io/tdt_mat.py` and `io/tdt_tank.py` behind a format-agnostic contract. BrainVision and BIDS conversion still pending. |
| P1.3 | Synthetic fixture and loader | done | `dbsspeech.demo_data` (moved into the package in 4.4, since `seed` uses it), `io/loader.py`. |
| P1.4 | Run records | done | Inputs keyed by manifest key plus hash, never by path. Failed runs still write a record. |
| P1.5 | Recipe registry and PSD | done | `psd_by_condition`, end to end on the real recording. |
| P1.6 | API skeleton | done | Plus uploads and the agent, which are not in the guide. |
| P1.7 | First screen | done | Vite, React, TypeScript, Tailwind. |
| P2.1 | Flag detectors | done | Peer groups respect lead geometry. |
| P2.2 | QC report and decisions table | done | A model, then a renderer. The merge cannot lose judgment. |
| P2.3 | Approval gate | done | Previously existed only in a docstring. Enforced in the package. |
| P2.4 | Review screen | done | QC over HTTP. |
| P2.5 | Calibrate with real subjects | **blocked** | Needs a calibration session on real recordings with the PI. The first subject analyzed is now reviewed and signed, so that conversation is the only remaining blocker. The statistics were made honest so that calibrating them is worth doing; see `docs/findings.md`. |
| P3.1 | Band power contrasts | done | `bandpower_contrast`, and three refusals. |
| P3.2 | Time-frequency around onset | done | `tfr_onset`, with onset defined honestly. |
| P3.3 | py_neuromodulation as a recipe | done | `pynm_features`, written against the installed package. |
| P3.4 | ERNA recipe | changed, done | Built without a lab convention, on Garrett's instruction: every setting that shapes the answer is a parameter defaulting to `configs/erna.yaml`, and a run says in its record and on its figure that those defaults are unreviewed. Recovers a planted 250 Hz and 12 ms decay from the fixture to within 1.6 and 8.3 percent. Never met a real stimulation recording; the data is there when the first subject analyzed clears QC (`increment1_depth1-6`, `increment2_depth1_2` through `depth6`, `clinical_dbs1/2`). |
| P3.5 | Results and compare screens | done | Compare screen, and table paging. |
| P3.6 | Slash commands | done | Deliberately unable to approve or override. |

## Phase 4

| Step | Title | Status | Note |
|---|---|---|---|
| P4.1 | Users and attribution | done | Accounts, roles, and a guard against binding unauthenticated. |
| P4.2 | Config admin and export bundles | done | History with author and reason; bundles carry a README readable without this software. |
| P4.3 | Deployment | done, unverified | Below. |
| P4.4 | Seed data, onboarding, docs | done | Below. |
| P4.5 | Design pass | done | Done on the guide's own stated direction rather than waiting for reference screenshots, on Garrett's instruction. `web/DESIGN.md`, tokens in one file, seven shared components, every page on them. No behavior or route changed. Review it and correct what is wrong; that was the trade. |

### P4.3, what landed

- **Runs execute in a worker, not in the API process.** A database-backed queue
  in `derivatives/runs.db` (`src/dbsspeech/jobs/`), and `python -m dbsspeech worker`.
  `BackgroundTasks` survives as `DBSSPEECH_EXECUTOR=background` for solo work.
- **`docker/`**: one image for the API and the worker, a multi-stage build for
  the front end, `compose.yml`, an optional nginx profile, and `.env.example`
  listing every setting with what happens if you get it wrong.
- **`/health`** reports versions, database connectivity, and worker heartbeat
  age; the Status screen shows it and says in words when no worker is running.
- **`scripts/backup.sh`** with a cron line and a tested restore.
- **`docs/deploy.md`**: exact commands, permissions, updating, restoring.

**The image has never been built.** The session that wrote it had no reachable
Docker daemon. Everything else here is tested; that step is not. First build on
the target machine is the test:

```bash
GIT_COMMIT=$(git rev-parse HEAD) GIT_DIRTY=false \
  docker compose -f docker/compose.yml build
```

### P4.4, what landed

- **`python -m dbsspeech seed`** builds a demo project: a synthetic subject
  through the real QC review and one run per recipe, in about twenty seconds. It
  refuses to overwrite an existing demo without `--overwrite`.
- **Docs**: `install.md`, `concepts.md`, `qc-guide.md`, `troubleshooting.md`, and
  `recipes.md` generated from the registry with a test that fails when it is
  stale. README rewritten for a new lab member.
- **In-app help** on every screen, keyed by route, collapsed by default.
- **Friendly errors** in `api/errors.py`: what happened and what to do next, with
  the technical text kept beside it. Also applied to failures recorded by a
  worker, which the run screen shows.
- `DBSSPEECH_MANIFEST` overrides the manifest directory, without which the demo
  project cannot be opened in the app.

## Added, not in the guide

| Item | Status | Why |
|---|---|---|
| `docs/guardrails.md` + `guardrails/` | done, 13 of 13 | Thirteen method checks drawn from traps already hit. |
| `configs/leads.yaml` | done | Contact naming is a device property, extensible by config. |
| `io/impedance.py` + `detect/geometry.py` | done | Reproduced the verified 1-3-3-1 signature independently. |
| `configs/statistics.yaml` + `stats/` | done | Centre and scale chosen separately, each carrying its caveat into the UI and the run record. |
| `configs/vocabularies.yaml` | done | Extending a vocabulary is a config line, not a code change. |
| `manifest/streams.csv` | done | One recording, several streams at different rates. |
| `manifest/leads.csv` | done | A subject has N leads, each with its own model and target. |
| `manifest/windows.csv` | done | There are no task markers. Windows are derived and carry provenance. |
| Agent layer | done | Deterministic proposer at `POST /agent/propose`. No model call, nothing leaves the machine. |
| `configs/erna.yaml` | new | ERNA is defined by a stimulation protocol, and protocols differ. Every setting sits here with a paragraph on what it does, editable from the config admin screen. |
| `docs/interop.md` + `scripts/matlab/load_run.m` | done | MATLAB reads results without a port. |
| `docs/backlog.md` | new | Things noticed while doing something else. |
| `docs/maintenance.md` | new | Adding a subject, adding a recipe, changing a threshold, updating dependencies, restoring a backup, and a monthly half hour. |
| `docs/CHANGELOG.md` | new | What exists, and the gaps, in the words of someone using it. |

### P4.5, what landed

`web/DESIGN.md` states the direction and the conventions. Colors, five type
sizes and the spacing scale are tokens in `src/index.css`, and pages use roles
(`text-muted`) rather than palette values (`text-stone-500`). Seven shared
components in `src/components/ui/`: PageHeader, Panel, DataTable, Badge, Button,
Field, EmptyState, Skeleton. Every page composes them, no page writes its own
color or padding, the screen title and the help panel are both keyed by route in
one place, and `statusTone` is one function rather than a copy per page.

Nothing about behavior changed. Look at it and say what is wrong.

## Phase 5

| Step | Title | Status | Note |
|---|---|---|---|
| P5.1 | Pilot with one fellow | **blocked** | Needs a person who has not used it. Everything they would touch is built and seeded, and `docs/pilot.md` is the session script: what they do, what to write down, and how to triage it. |
| P5.2 | Fix, re-pilot, hand off | part done | `docs/maintenance.md` and `docs/CHANGELOG.md` are written. v1.0.0 is deliberately not tagged: the guide puts the tag after the pilot, nobody outside the authors has used this, and the container image has never been built. |

## Next session starts here

**Phase 5, the pilot with one fellow.** Sit with someone who has not used it,
give them the demo project, and watch where they stop. Then fix, re-pilot, hand
off.

Before that, two things are worth doing and neither needs anyone else:

- Wire `motor_baseline` in as the true rest window, which clears the G10 flag on
  every result currently using `rest`.
- The BrainVision reader, which P1.2 still lists as pending. Everything so far is
  TDT.

Cheap and still outstanding: wire `motor_baseline` in as the true rest window,
which resolves the G10 flag on every result that currently uses `rest`.

## Running it

```bash
uv run python -m dbsspeech seed   # a demo project, no recordings needed
./scripts/dev.sh                  # API, worker, and the web app
```

API at http://127.0.0.1:8000/api/docs, app at http://127.0.0.1:5173, status at
http://127.0.0.1:5173/status.

A single run without the interface:

```bash
uv run python -c "
from dbsspeech.recipes import run
print(run('psd_by_condition', '<study_id>', '<session>',
          claim='what this run is meant to show'))"
```

CLI: `python -m dbsspeech status | validate | ask | run | qc | users | seed |
 jobs | worker | inspect | serve`.
worker | inspect | serve`.

## Blocked on someone else

- **IT and information security**: where de-identified research data may be hosted, whether campus SSO
  is available, network rules. Blocks exposing the deployment past localhost.
- **Implant record**: manufacturer and model of both the first subject analyzed leads. Until then
  `lead_model` stays `unknown_directional_1331`.
- **Lead rotation**: unknown, so no anatomical direction claim is possible.
- **Open with the PI**: word-level resolution, a true rest window, 6 to 10 kHz, and QC
  calibration. The rest window likely resolves to the `motor_baseline` block, a
  dedicated baseline in the same case and the smallest file in the set at 99 MB.
- **ERNA parameters**: the recipe runs without them, and the numbers it produces
  are about its own defaults until someone who knows the stimulation protocol
  sets `configs/erna.yaml` and marks it reviewed. That is a half hour with
  whoever knows the stimulation protocol, not a blocker.

## Housekeeping left alone deliberately

A few smoke-test run records sit in `runs/` from verifying the PSD recipe. They
are honest records of real runs, so they were not deleted without asking; remove
them if you would rather the provenance log start clean.
