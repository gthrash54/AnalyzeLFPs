# Maintaining this

For whoever keeps it running, including you in a year when you have forgotten
the parts you wrote quickly.

Everything here is a procedure with the exact commands, because a tool whose
maintenance lives in one person's head has a bus factor of one.

---

## Adding a subject

1. **Put the recording where `data/` can see it.** Never copy raw files into the
   repository. `data/` is read-only to this software and is a symlink to the
   synced folder holding the recordings.

2. **Write the manifest rows.** Five files, described in `docs/schema.md`. The
   minimum is one row in `subjects.csv`, one per stream in `streams.csv`, one per
   lead in `leads.csv`, one per channel in `channels.csv`, and one per condition
   window in `windows.csv`.

   Study IDs only. No name, MRN, initials, or date of surgery, in any field,
   including `notes`.

3. **Check it before trusting it:**

   ```bash
   uv run python -m dbsspeech validate
   ```

   Every violation is reported at once, so fix the list rather than the first.

4. **Look at what the reader sees**, which catches a wrong `root_relpath` or a
   stream named differently from the manifest:

   ```bash
   uv run python -m dbsspeech inspect data/<block>
   ```

5. **Run detection, then review it.** No analysis runs until it is signed:

   ```bash
   uv run python -m dbsspeech qc propose --subject <study_id>
   ```

   Then the QC page in the app. `docs/qc-guide.md` is what to think about while
   deciding.

## Adding a recipe

The procedure is meant to be followable by a motivated student. If it is not,
that is a defect in the procedure.

1. **Write it** in `src/dbsspeech/recipes/<name>.py`. Copy the shape of
   `psd.py`: a `BaseModel` for parameters, a function taking `RecipeContext` and
   returning `RecipeResult`, and the `@recipe(...)` decorator.

2. **Declare the words a person reads.** In the decorator, `question` (what a
   person would ask, in their words) and `produces` (what lands in the run
   directory). On the parameter model, `LABELS` for readable field names with
   units, and `ESSENTIAL` for the handful that decide the answer. Without these
   the run screen falls back to Python field names, which is what the interface
   was rewritten to stop doing.

3. **Tell the guardrails what it does.** Define `guardrail_context(session,
   params)` and attach it: `<fn>.guardrail_context = guardrail_context`. This is
   the recipe's own account of itself, and the checks are only as honest as it
   is.

4. **Register it** by importing the module in `src/dbsspeech/recipes/__init__.py`.

5. **Test it against a planted signal.** Not "it runs": put something in the
   synthetic fixture and assert the recipe finds it, with the tolerance stated.
   See `tests/unit/test_erna_recipe.py`.

6. **Regenerate the docs**, or the test that guards them fails:

   ```bash
   uv run python scripts/gen_recipe_docs.py
   uv run pytest -q -m "not realdata"
   ```

7. **Write a dated entry in `docs/decisions.md`** saying what it does and which
   choices were deliberate.

## Changing a threshold or a band

Two routes, and they differ in who can use them.

**From the app**, Configs page: validated before it is written, archived with an
author and a reason, and refused without a reason. This is the route for anyone
who is not editing code.

**From a file**, for `configs/*.yaml` directly. If you do this, record why in
`docs/decisions.md` yourself; the file route has no history.

Two things that are true either way. An edit never changes a result that already
exists: run records carry the config that produced them. And an edit does not
retroactively change an approved subject, because an approval certifies the
judgments made against the numbers as they were.

`leads.yaml` and `privacy.yaml` are deliberately not editable from the app. One
is a device catalogue and the other governs what may leave the machine.

## Updating dependencies

Never on the main branch, and never without the full suite.

```bash
git switch -c deps-$(date +%Y%m%d)
uv lock --upgrade
uv sync --extra dev
uv run pytest -q -m "not realdata"
uv run pytest -q -m realdata        # only with data/ mounted; do not skip it
cd web && npm update && npm run build && npm run lint
```

The realdata tests matter here more than anywhere else: a scipy or MNE change
that alters a number will not show up on synthetic data with round values.

If a number moves, stop. Find out which library changed and why before deciding
whether the new number or the old one is right. Then write it down in
`docs/findings.md`, because a changed result with no explanation is the thing
nobody can defend later.

## Backups, and testing a restore

```bash
scripts/backup.sh /path/to/backups
```

Nightly, keeping the last 30:

```cron
15 2 * * * cd /path/to/dbsspeech && ./scripts/backup.sh /path/to/backups >> /var/log/dbsspeech-backup.log 2>&1
```

**Test a restore before you need one.** A backup nobody has restored is a
hypothesis. The procedure is in `docs/deploy.md`; the short version is stop the
services, untar into place, fix ownership, start them, and then run
`python -m dbsspeech status` and confirm the subjects and runs you expect.

What is in a backup: `runs/`, `derivatives/`, `var/`, `configs/`, `manifest/`.
What is not: `data/`. The recordings are large, read-only, and backed up where
they live.

## A monthly half hour

- Run the full suite, including realdata, on a clean checkout.
- Take a backup and restore it somewhere scratch. Confirm the databases open.
- Update dependencies on a branch, as above. Merge it or write down why not.
- Read `docs/backlog.md` and either do something or delete what no longer
  matters. A backlog nobody prunes stops being read.
- Check `docs/build-status.md` still describes reality.

## Who to ask

- **The data, the conditions, what a result means**: the PI.
- **Where things are and why they are that way**: `docs/decisions.md`, which is
  dated and searchable, then Garrett.
- **What broke**: `docs/troubleshooting.md` first. Add to it when you work
  something out, while you still remember.

## What to be careful about

The rules that exist because breaking them is quiet rather than loud:

- **Study IDs only**, everywhere, including commit messages and figure captions.
- **`data/` is read-only.** Nothing writes to a recording, and no analysis
  deletes samples. An artifact becomes an annotation.
- **Every analysis goes through `registry.run`.** That is what writes the run
  record and enforces the QC gate. There is no quick check that skips it.
- **Do not switch `enforce_gate` off** to get past a subject that has not been
  reviewed. Review it.
- **Thresholds, bands and windows live in `configs/`**, never in code.
