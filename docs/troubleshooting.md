# Troubleshooting

Errors we have actually hit, and what they meant. Not a list of everything that
could go wrong: an invented troubleshooting guide sends people down paths nobody
has walked.

Add to it when you work something out. The entry is worth more than the memory.

---

## "This subject has not completed QC review"

`QCNotApproved`, from every direction: the app, the CLI, the API, a notebook.

Working as intended. The gate refuses analysis on a subject nobody has signed
off. Open its QC page, decide the flags, sign. `docs/qc-guide.md` is how.

Do not switch `enforce_gate` off in `configs/qc_thresholds.yaml` to get past it.
That setting exists for a lab that has a different review process, not for an
afternoon when the review is inconvenient.

## A run was submitted and nothing happened

It is sitting in the queue because no worker is running. Runs execute in a
separate process, so they survive an API restart.

```bash
python -m dbsspeech worker      # or: docker compose -f docker/compose.yml up -d worker
```

The Status screen says this in words, and `dbsspeech status` prints it. If a
worker is running and the job is still queued, check that both are pointed at the
same `DBSSPEECH_DERIVATIVES`, since that is where the queue lives.

## "no measurable ERNA epochs" with zero events found

Seen while building the demo, 2026-09-08, and the cause is worth knowing.

QC detection flags a stimulating contact as a kurtosis outlier, correctly, and
proposes excluding it. Approving that proposal excludes the contact carrying the
ERNA, so the recipe then finds nothing on a recording full of stimulation.

Approve the flag, set its action to `none`, and say why. The artifact is the
signal the recording was made for.

If the contacts are present and events are still zero, the detection threshold is
the next thing to look at: `stim_threshold_mad`, and `stim_refractory_ms`, which
must be set below the spacing of the events you want counted separately.

## "All arrays must be of the same length" from tfr_onset

Seen 2026-09-08, fixed the same day. A condition window too close to the start of
the recording could not supply the pre-onset period asked for, so its map came
out shorter than the others and could not be stacked with them.

Now those windows are skipped with a line in the run log saying which and why. On
an older checkout, either move `tmin` closer to zero or use a window that is not
flush against the start of the recording.

## Every realdata test fails on a fresh clone

They should be skipped, not failed. `tests/conftest.py` decides by looking for
anything inside `data/`.

Two ways this has gone wrong. On a fresh clone `data/` is empty and the tests
skip, which is correct. In a git worktree, `data/` does not exist at all, and
several tests marked `unit` that happen to read the real recording will fail
rather than skip. Symlink `data/` into the worktree, or run them from the main
checkout.

There was also a real bug here, fixed in `1ce62b3`: the guard used
`Path.iterdir()` outside its own `try`, and `iterdir` is lazy, so the exception
for a missing directory was raised after the guard had already returned.

## The backup script exits 1, or its archive has no databases

Both fixed 2026-09-08, both found by running it rather than reading it.

The retention loop failed under `set -e` when there was nothing to delete, so
every backup to a fresh destination reported failure. And `tar --exclude` applies
to every member regardless of which `-C` it came from, so excluding the live
databases also excluded the consistent snapshots being added back under the same
names, silently.

If you are looking at an old archive, check it has `var/app.db` and
`derivatives/runs.db` in it:

```bash
tar -tzf <archive> | grep '\.db$'
```

## "permission denied while trying to connect to the Docker API"

The user running the command is not in the `docker` group, or the daemon is not
running. On a lab machine this is a conversation with whoever administers it.

Nothing else in this software needs Docker. `python -m dbsspeech serve` and
`python -m dbsspeech worker` are the same two processes the containers run.

## A result says its code is in no commit

Not an error. The run record is marked dirty because the working tree had
uncommitted changes when it ran, so the exact code cannot be recovered from the
commit alone. The result is provisional. Commit, and re-run anything you intend
to show someone.
