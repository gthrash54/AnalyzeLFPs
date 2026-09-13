# Reviewing quality control

The half hour that decides whether a subject's results mean anything. It is
judgment, not clicking, and this page is what to think about while doing it.

Practise on the demo first: `python -m dbsspeech seed` builds a subject with
four real flags, two of which are the interesting kind.

## The shape of it

```bash
python -m dbsspeech qc propose --subject <study_id>   # run detection
```

Then open `http://127.0.0.1:5173/qc/<study_id>`, or use
`python -m dbsspeech qc list --subject <study_id>`.

Detection proposes. You decide each flag. You sign. Signing is refused while any
active flag is undecided, so there is no half-reviewed state that later looks
approved.

Until it is signed, every recipe on that subject is refused, from every
direction. That is the point.

## What each decision means

A flag has two questions, and they are separate.

**Is the observation real?** Approving says yes: the statistic is what detection
says it is. Rejecting says the detector was wrong, and needs a reason.

**Is the proposed action right?** Separate. Detection proposes what it usually
takes to make a recording usable, and it does not know why the recording was
made. Change the action when the proposal would throw away the signal of
interest, and say why.

The second question is the one people skip, and it is where the demo's example
lives: a stimulating contact is flagged as a kurtosis outlier, correctly, because
the stimulation artifact is enormously peaked. The proposed action is to exclude
the contact. Excluding it would delete the ERNA. The right decision is to approve
the flag, set the action to `none`, and write down that the artifact is the
signal.

## What the detectors look for

Set in `configs/qc_thresholds.yaml`, tunable without touching code.

| flag | what it means | usual action |
|---|---|---|
| `flat_channel` | a channel with no variance. Disconnected or dead. | exclude the channel |
| `line_noise` | mains and its harmonics dominating. | notch, or exclude |
| `amplitude_excursion` | episodes far outside the channel's own distribution. | annotate the window |
| `kurtosis_outlier` | a heavy-tailed channel: spikes, artifact, stimulation. | exclude, or keep and annotate |
| `variance_outlier` | a channel far from its peers in overall power. | exclude the channel |
| `hf_noise_ratio` | too much energy above the physiological range. | exclude the channel |
| `insufficient_channels` | a peer group too small to judge anybody against. | nothing to do; it is telling you the comparison is weak |

Peer groups respect lead geometry: a directional segment is compared with the
other segments in its row, not with the rings. A ring compared against segments
would flag every ring on every lead.

Two of these statistics depend on recording duration, which was fixed once and is
worth knowing about: block width shrinks until there are at least five blocks, so
a median over two blocks does not stop being a median. The evidence on the row
says how many blocks were used.

## Reading the evidence

Every flag carries the numbers it fired on: the statistic, the threshold, the
peer group, the number of blocks. Read them. A kurtosis of 841 against a
threshold of 20 is a different situation from 22 against 20, and the decision
should be different too.

The thresholds are uncalibrated. They were chosen to be defensible rather than to
match this lab's recordings, and calibrating them against real subjects is an
open item with the PI. Until then, expect to disagree with detection sometimes,
and write down why when you do: those disagreements are what calibration will be
built from.

## Signing, and changing your mind

Signing records who and when. It does not freeze the subject forever: `reopen`
puts it back into review, requires a reason, and is recorded in the history.
Results computed before a reopen keep the QC state they were computed under,
which is in their run records.

Editing a threshold later does not retroactively change an approved subject. An
approval certifies the judgments made against the numbers as they were, so new
thresholds apply to future runs and future proposals only.

## What reaches the results

Approved actions are applied when a recording is opened for analysis, and what
actually took effect is written into every run record: which channels were
dropped, which windows were annotated, and who decided. A reader of a result can
see what was removed from it without asking anyone.
