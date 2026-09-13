# MATLAB and Python

Some of this lab works in MATLAB, some in Python. The existing pipeline for the
first subject is roughly twenty MATLAB scripts with findings already established
from them.

The answer is **not** to make the code run in both languages. It is to make the
artifacts readable from both, and to write each analysis once.

## What is already portable

| Layer | Format | MATLAB | Python |
|---|---|---|---|
| Raw recordings | TDT `.mat`, which is HDF5 v7.3 | `h5read`, `load` | `h5py` |
| Recordings, stage 2 | BrainVision | `read_brainvision.m` | `mne` |
| Tabular outputs | Parquet, CSV | `parquetread`, `readtable` | `pandas` |
| Run records | JSON | `jsondecode` | `json` |
| Figures | PNG, SVG | viewable | viewable |

The data layer has no lock-in in either direction. That is most of the problem
already solved.

## The one real friction point, and the fix

Configuration is YAML, which is pleasant to hand-edit and is not readable by
MATLAB without an add-on. So **every run writes a resolved `config.json` into its
output directory** alongside the YAML-sourced settings. YAML stays the source of
truth for humans; JSON is the machine-readable snapshot, and it is what proves
which settings produced a result. MATLAB users read the snapshot and never need a
YAML parser.

## Reading a Python result from MATLAB

`scripts/matlab/load_run.m` takes a run ID and returns the record, the config
snapshot, every output table, and the figure paths. About sixty lines, not a
port. It warns when a run was produced from a dirty working tree, because the
code that made it is then in no commit.

```matlab
run = load_run('20260903_141500_psd_by_condition');
head(run.tables.psd_long)
run.record.params
```

## Calling across the boundary

Possible in both directions and deliberately not relied upon:

- MATLAB can call Python (`pyenv`, `py.` prefix). It works, but it is sensitive
  to which interpreter MATLAB finds, and this project's environment is a uv venv
  outside the repo, which makes that setup a per-machine chore.
- Python can call MATLAB through the MATLAB Engine API, which needs MATLAB
  installed and licensed on whatever machine runs the app, including the
  deployment target. That is a hard constraint to accept for a lab server.

Neither is forbidden. Neither is load-bearing.

## Porting an existing analysis: parity first

When an analysis that already exists in MATLAB is implemented as a recipe, the
recipe must reproduce the MATLAB result on the same input window before it
replaces anything. Findings already reported to a PI cannot quietly change
because the language changed.

The differences that actually bite:

- `decimate` uses a Chebyshev design in both, but filter order, zero-phase
  handling, and chained versus single-stage decimation all shift the result.
  Decimation parameters are part of the parity test, not an implementation
  detail.
- MATLAB's `bandpass` defaults to an FIR design with zero-phase filtering, and
  the resulting filter can be very long at low frequencies. `scipy` defaults
  differ. Filter design is stated explicitly on both sides.
- Array orientation: MATLAB shows a stream as `(channels, samples)`; the same
  data read from HDF5 in Python appears as `(samples, channels)`. The reader
  normalizes to `(channels, samples)` once. See `src/dbsspeech/io/tdt_mat.py`.
- Indexing is 1-based in MATLAB and 0-based in Python. Channel numbers in the
  manifest are the manufacturer's own labels, which are neither; that is why the
  manifest carries `ch_index` separately from `lead_contact`.

Parity tests live in `tests/integration/` and compare against reference values
exported from the MATLAB pipeline, not against a reimplementation of it.

## Rule of thumb

Write the analysis once, in the app. Read the results anywhere. If an analysis
exists in both languages, one of them is about to drift.
