# Data schema

The data contract. Every disagreement about what a column means gets settled
here, in writing, once.

Designed to generalize. Nothing below hardcodes a manufacturer, a sampling rate,
a channel count, a task, a montage, or a file format. The first subject analyzed
is a case, not the definition. Per-recording observations live in
`docs/datasets/`.

## Manifests

Five files, hand-curated, authoritative. Code never infers any of this from file
names or header text. Vocabularies for the enum columns live in
`configs/vocabularies.yaml`; a term not listed there is an error that names the
term, never a silent pass.

### `manifest/subjects.csv`

One row per recording session.

| Column | Meaning |
|---|---|
| `study_id` | De-identified study code. Never an MRN, name, or date of surgery. |
| `session` | Session label, for example `ses1`. One row per session per subject. |
| `hemisphere` | `L`, `R`, or `bilateral`. |
| `format` | Reader to use: `tdt_mat`, `brainvision`, and whatever is added later. |
| `root_relpath` | Path to the recording root, relative to `data/`. |
| `acquisition` | Free text naming the block, for example `motor_baseline`. |
| `acquisition_date` | ISO date the block was recorded, or empty. Empty in this repository, and empty is the safe default. Whether a recording date is sensitive depends on your protocol and your IRB, and a date that can be tied to an individual is the kind of field that is easy to add and hard to remove once it has been committed. Fill it only if your site has confirmed it may be recorded. `configs/privacy.yaml` governs the related question of whether raw *filenames* may be written into a derivative, which is a separate setting. |
| `notes` | Anything that changes how the recording should be read. |

`format` exists because this project is not single-format. The readers that ship
handle TDT `.mat` (MATLAB v7.3, so HDF5), TDT tanks, BrainVision and EDF. The
loader dispatches on this column, so supporting a new acquisition system is a new
reader plus a new value here, and nothing else in the package changes.

### `manifest/streams.csv`

One row per stream. A single recording carries several streams at different
sampling rates, so rate is a property of the stream, never of the subject.

| Column | Meaning |
|---|---|
| `study_id`, `session` | Foreign key to `subjects.csv`. |
| `stream` | Store name as it appears in the file, for example `ecos`, `emgg`, `mic_`, `Cam1`. |
| `n_channels` | Channel count in this stream. |
| `sfreq_hz` | Native sampling rate. Checked against the file at load. |
| `units` | Recorded units, or `unknown`. |
| `role` | `neural`, `emg`, `audio`, `video`, `stim`, `other`. |
| `relpath` | Path within the recording root, when the stream is a separate file. |
| `notes` | |

Streams may share a clock without sharing a rate. Anything aligning across
streams states which clock it used.

### `manifest/leads.csv`

One row per implanted lead. A subject has as many rows as leads.

| Column | Meaning |
|---|---|
| `study_id`, `session` | Foreign key. |
| `lead_id` | Short label unique within the subject, for example `lead1`, `lead2`. |
| `target` | Region key from the vocabulary: `stn`, `gpi`, `vim`. |
| `hemisphere` | `L` or `R`. |
| `lead_model` | Key into `configs/leads.yaml`. Determines contact naming and geometry. |
| `channel_first`, `channel_last` | Inclusive channel index range within its stream. |
| `rotation_deg` | Segment orientation, or empty when unknown. Empty blocks any anatomical direction claim. |
| `notes` | |

Contact naming is a property of the device, so it lives in `configs/leads.yaml`
rather than being fixed here. That file carries, per model, the manufacturer's
own contact `id`, an optional short `alias` for figures, the row index, and
whether each contact is a ring or a segment. Adding a lead model is a config
entry, not a code change.

Geometry can be checked electrically from the ring-segment-ring impedance
signature, since segments have roughly half a ring's surface area and read
higher. That check flags a mismatch against the declared model. It never
relabels anything: impedance separates rings from segments but cannot identify a
manufacturer.

### `manifest/channels.csv`

One row per channel. Where a channel is declared usable, and why it is not.

| Column | Meaning |
|---|---|
| `study_id`, `session` | Foreign key. |
| `stream` | Which stream this channel belongs to. |
| `ch_index` | Index within the stream, as stored. |
| `ch_name` | Name as it appears in the file, if it has one. |
| `region` | Key from the region vocabulary. |
| `lead_id` | Foreign key to `leads.csv` for depth channels. Empty otherwise. |
| `lead_contact` | Contact `id` from the lead model. Empty for non-lead channels. |
| `site` | Anatomical or anatomical-adjacent site for the channel: a cortical strip location, a muscle name for EMG. Empty when unknown. Generalized from an ECoG-only column because every non-depth channel has a site. |
| `include` | Whether the channel enters analysis. |
| `exclude_reason` | Required when `include` is false. |

### `manifest/windows.csv`

One row per task window. Some recordings carry no task markers at all, so a
condition boundary is often derived rather than read, and every row must carry the
provenance of how it was decided. `derived_from` is that field, and `assumed` is
a legitimate value whose whole purpose is to be visible: guardrail G10 flags any
result that depends on a window nobody measured.

| Column | Meaning |
|---|---|
| `study_id`, `session` | Foreign key. |
| `condition` | Key from the condition vocabulary. |
| `t_start_s`, `t_end_s` | Bounds in seconds on the neural clock. |
| `derived_from` | `microphone`, `emg`, `video`, `task_marker`, `datasheet`, or `assumed`. |
| `status` | `draft`, `in_use`, `under_revision`, or `superseded`. |
| `notes` | |

`derived_from: assumed` exists so an unverified window is visibly unverified.
`status: under_revision` marks a window known to be inadequate while its
replacement is in progress, and any result depending on one is flagged.

### `manifest/coordinates.csv`

Optional. Where each contact sits, when imaging says so. A lab without imaging
has no such file, it reads as an empty table, and every recipe works without it.

| Column | Meaning |
|---|---|
| `study_id`, `session`, `lead_id` | which lead, keyed as in `leads.csv` |
| `contact` | a contact `id` defined for that lead's `lead_model` |
| `x_mm`, `y_mm`, `z_mm` | position, millimetres, in `space` |
| `space` | from `coordinate_spaces` in `configs/vocabularies.yaml` |
| `source` | from `coordinate_sources`; provenance, not method detail |

Two properties worth stating rather than assuming.

A position in `native` space is correct for that subject and means nothing
between subjects, so it validates with a warning and a group claim needs a
template space. The vocabulary marks which spaces are comparable.

**A coordinate does not license a direction claim.** It locates a contact; it
says nothing about which way a directional segment faces. That remains gated on
`rotation_deg` by invariant 10, and there is a test that adding coordinates does
not lift the rotation warning.

## Invariants

Statements that must always hold. These become tests.

1. Every `study_id` in a dependent manifest appears in `subjects.csv`.
2. `(study_id, session, stream, ch_index)` is unique in `channels.csv`.
3. Every channel with `include` false has a non-empty `exclude_reason`.
4. Every depth channel has a `lead_id`, and that lead exists in `leads.csv`.
5. Every `lead_contact` is a contact `id` defined for that lead's `lead_model`.
6. A lead's channel range covers exactly the contact count its model declares.
7. Every `region`, `condition`, `derived_from`, and `status` value appears in
   `configs/vocabularies.yaml`.
8. Windows of the same condition in the same session do not overlap.
9. A channel absent from `channels.csv` is not analyzed. Silence is exclusion.
10. Any anatomical direction claim requires a non-empty `rotation_deg`. A
    contact coordinate does not satisfy this: position is not orientation.
11. Every row in `coordinates.csv` names a lead in `leads.csv`, a contact on
    that lead's model, three numeric axes, and a `space` and `source` in the
    vocabulary. A contact appears at most once per lead.

## Outputs

Recipe outputs go to `derivatives/results/<run_id>/`, git-ignored. The run record
goes to `runs/<run_id>.json`, committed, so provenance is in version control
while bulk outputs are not.

The run record carries at minimum: `run_id` (`YYYYMMDD_HHMMSS_<name>`), name,
claim, user, timestamps, status, `git_commit`, `git_dirty`, params, inputs with
SHA256 hashes, outputs, library versions, the QC decisions applied, and any
guardrail overrides with their stated reasons. Paths are relative, never
absolute.

Tabular outputs are Parquet or CSV. Figures are PNG plus SVG, with the `run_id`
in the caption, plus the data frame that produced them.

## Layout detection and selection

Recordings differ in channel order, stream naming, lead count, and montage. The
app inspects a file, proposes a layout with evidence and a confidence, and a
person confirms it. The confirmed answer is written to the manifests, which
remain authoritative. Detection never writes a manifest directly, for the same
reason QC flags never write decisions: a proposal a human accepted is auditable,
a silent guess is not.

What can be detected from the signal: stream roles, contiguous channel blocks
that look like separate arrays, ring versus segment geometry from impedance,
sampling rate, mains frequency, and whether a shared reference is in use.

What cannot, and is therefore presented as a choice: lead manufacturer (several
vendors ship the same 1-3-3-1 geometry with different contact numbering),
anatomical target, hemisphere, lead rotation, and ECoG strip location. These are
surgical and imaging facts, not properties of the recorded signal.

Configured in `configs/layout_detection.yaml`. Re-running detection on a
confirmed recording reports disagreements rather than overwriting.

## Per-dataset notes

Observations about specific recordings live in `docs/datasets/`, not here. This
file stays the general contract.
