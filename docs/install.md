# Installing

Ten minutes, on a machine with no recordings and no permissions arranged.

For putting this on a lab machine for other people, read `docs/deploy.md`
instead. This page is for a laptop.

## What you need

- Python 3.11 or 3.12. Not 3.13; some of the scientific stack is not there yet.
- [uv](https://docs.astral.sh/uv/), which manages the environment and the lock
  file.
- Node 20 or newer, for the web app.
- Git.

## Setting it up

```bash
git clone <this repository>
cd dbsspeech
uv sync --extra dev
cd web && npm install && cd ..
```

Check it:

```bash
uv run pytest -q -m "not realdata"
```

Everything should pass. The `realdata` tests are skipped automatically because
`data/` is empty, which is correct on a fresh clone: those tests read real
intraoperative recordings, and a fresh clone has none.

## The ten-minute walkthrough

Build a demo project. It writes a synthetic subject, takes it through the real QC
review, and runs every recipe once:

```bash
uv run python -m dbsspeech seed
```

That prints the command to start the app against it. It looks like this:

```bash
DBSSPEECH_MANIFEST=demo/manifest DBSSPEECH_DATA=demo/data \
DBSSPEECH_DERIVATIVES=demo/derivatives DBSSPEECH_RUNS=demo/runs ./scripts/dev.sh
```

Then open http://127.0.0.1:5173 and click through:

- **Subjects** shows `demo01`, its lead, its contacts, and its QC status.
- **QC** shows what detection found. The demo has four flags, and two of them
  are the stimulating contacts, which the reviewer kept rather than excluding.
  The reason is on the row.
- **Runs** lists five runs, one per recipe. Open one to see its claim, its
  parameters, what QC removed, and the figures.
- **Compare** puts two of them side by side.
- **Status** says whether a worker is running.

The demo recording is synthetic and contains a planted 20 Hz oscillation and a
planted 250 Hz resonance after each stimulation artifact. When a recipe finds
those, it is finding what was put there.

Delete `demo/` when you are done with it. Nothing else refers to it.

## Working on real recordings

`data/` is where the recordings live, and it is read-only: nothing in this
software writes to it. On the lab machine it is a symlink into the cloud-synced
folder holding the recordings.

A subject is not visible until it is in the manifest. `manifest/subjects.csv`
and its four companion files are the data contract, described in
`docs/schema.md`. Then:

```bash
uv run python -m dbsspeech validate     # the manifest against the schema
uv run python -m dbsspeech status       # subjects, QC state, recent runs
```

A subject cannot be analyzed until its QC review is signed. That is the gate,
and it is enforced in the package rather than in the interface, so no path
around it exists. `docs/qc-guide.md` is the review.

## Running it day to day

```bash
./scripts/dev.sh
```

Starts three things: the API on port 8000, a worker that executes runs, and the
web app on port 5173. Ctrl-C stops all three.

The worker matters. Runs execute there, not in the web process, so a run
survives a page reload and an API restart. Without a worker running, a submitted
run waits in the queue, and the Status screen says so.

## When something is wrong

`docs/troubleshooting.md` has the errors we have actually hit, with what they
mean. If yours is not there, add it once you work it out.
