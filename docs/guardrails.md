# Guardrails

Checks the app runs so that a known mistake cannot be made quietly. Each one
exists because it has already cost someone real time, here or in the literature.

Design rules for this layer:

- A guardrail **explains**, it does not just block. The message says what was
  detected, why it matters, and what to do instead.
- A guardrail can be **overridden**, and the override is recorded in the run
  record with the reason. Silent overrides defeat the purpose.
- Severity is `block`, `warn`, or `note`. Only `block` stops a run, and only
  where the result would be actively misleading rather than merely suboptimal.
- Every guardrail cites its source: a finding in `docs/findings.md`, a dataset
  note under `docs/datasets/`, or a reference.
- Every guardrail is **configurable**. Severity and thresholds live in
  `configs/guardrails.yaml`, so a lab can tune or disable one without touching
  code. Rules are stated generally here; no threshold is hardcoded to a dataset.

This is the layer that lets a first-year student run an analysis the PI would
accept. The student gets the same checks a careful analyst applies by habit.

## G1. Monopolar common-mode

**Severity: block, overridable.** A recipe requesting `monopolar` on a shared
reference montage stops and explains.

An effect appearing on nearly every channel simultaneously, with little spread
between channels, is the reference moving rather than the brain. Default to a
bipolar montage; offer monopolar only for an explicit montage comparison.

Thresholds: `min_fraction_channels_affected`, `max_iqr_db`.

## G2. Effect that tracks electrode identity, not brain state

**Severity: block, overridable.** Before any directional or per-contact
comparison, subtract a per-contact baseline taken from a different condition.

A per-contact map built from total power measures which contact sits best, not
what the brain is doing. If such a map correlates strongly with the baseline
condition and cannot change with task state, it is measuring impedance and
placement. Subtracting a per-contact baseline first is what makes the comparison
about state.

Threshold: `max_corr_with_baseline`.

## G3. Jensen's inequality on ratios

**Severity: block.** Compute the ratio per channel, then average. Never average
then take the ratio. The two differ and only the first answers the question
asked. Applies to power ratios, dB contrasts, and normalized bandpower.

## G4. Threshold set across conditions when testing structure

**Severity: warn.** When comparing burst structure, occupancy, or duration
between conditions, the threshold must be set within each condition. A shared
threshold turns an amplitude difference into a fake structural difference.

Where this has been checked, structure measured with a within-condition threshold
was indistinguishable across conditions while amplitude differed. A shared
threshold would have reported a structural effect that is not there.

## G5. Time-frequency window too long for the effect

**Severity: warn.** If the analysis window exceeds the duration of the
phenomenon being claimed, say so. A multi-second STFT window integrates many
cycles and many bursts, so it cannot resolve burst-scale events that a Hilbert or
filter-bank analysis reports. Prefer wavelet or filter-bank methods for any
burst-level claim.

Threshold: `max_window_to_event_ratio`.

## G6. Decimation silently removing the band being claimed

**Severity: block.** Compare the effective bandwidth after decimation against
the highest frequency any requested band touches. Refuse if the band is above
the anti-alias cutoff.

Both `scipy.signal.decimate` and MATLAB's `decimate` apply a Chebyshev filter at
0.8 times Nyquist, so the usable bandwidth after decimation is
`0.4 * sfreq_after`. State the usable bandwidth wherever a decimated rate is
chosen, and prefer a single decimation stage over chained ones.

Threshold: `antialias_cutoff_fraction_of_nyquist`.

## G7. Muscle contamination in the speech band

**Severity: warn, escalating to block for overt speech above the configured
frequency.** Speech EMG occupies roughly 100 to 1000 Hz, exactly the range that
opens up when the sampling rate is raised. Raising bandwidth during an overt
speech task therefore increases muscle contamination in the band of interest.
Require bipolar referencing, and prompt for EMG regression, before reporting a
high-frequency effect during overt speech.

Thresholds: `emg_band_hz`, `escalate_to_block_above_hz`.

## G8. Dynamic range mistaken for effect size

**Severity: note.** Report an effect in dB alongside a z-score against its own
baseline distribution. Bands differ enormously in absolute power, so a raw dB
plot mostly shows dynamic range. Low-frequency dominance that collapses under
z-scoring was never an effect size.

## G9. Non-stationarity larger than the effect

**Severity: warn.** Before reporting a condition contrast, check the same
recording for spontaneous excursions outside any task window. Absence of a
systematic drift is not evidence of stability. If the largest excursion in the
recording exceeds the condition effect, the contrast needs a stability argument.

Threshold: `excursion_to_effect_ratio`.

## G10. Window provenance

**Severity: warn.** Any window whose `derived_from` is `assumed` is flagged
wherever it appears, and any window marked `under_revision` is flagged in results
that depend on it. Windows come from data, never from assumption.

## G11. A claim is analyzed without the control condition it needs

**Severity: warn.** A contrast that omits the condition which would rule out its
confound does not support the claim it appears to. The original case is speech:
speech is a motor act, so any low-frequency change during speech has a motor
explanation until a movement-only condition rules it out. That is now one rule
among several rather than the only shape the check can take.

Rules ship in `configs/guardrails.yaml` under `rules`, each naming
`applies_to_conditions`, `satisfying_conditions`, and a `because` sentence shown
to the reviewer. Which control a claim needs is a fact about a paradigm, not
about this code, so adding one is a config line.

Currently configured:

| Claim | Satisfied by | Because |
|---|---|---|
| `overt`, `inner` | `metro`, `move` | speech is a motor act |
| `move`, `imagery` | `rest` | no baseline to separate the movement from |
| `task` | `rest`, `cue` | cannot separate the effect from the evoking stimulus |
| `dbs_on` | `dbs_off` | one state described is not a contrast |

Every rule is evaluated and all that fire are reported in one finding, because
surfacing one confound at a time costs a review cycle each. A rule for a
paradigm the lab does not run is inert: it fires only when the run analyzes one
of its `applies_to_conditions`.

The older flat form, `satisfying_conditions` and `applies_to_conditions` at the
top level, is still read as a single rule, so an un-updated config is not
silently disarmed.

Renamed from `G11_motor_control_missing`; run records written before
2026-09-08 name the old id.

## G12. Baseline statistics computed on smoothed data

**Severity: block.** Smoothing before estimating a baseline distribution narrows
it and inflates every subsequent z-score. Baseline statistics come from
unsmoothed data.

## What the config offers, and what it does not

`configs/guardrails.yaml` is the tunable surface. Every key in it is read by a
check; a key that changes nothing does not belong there, because a lab that edits
one and sees no behaviour change concludes the guardrail was retuned. Eleven keys
were in that state until 2026-09-09 and have been moved into this document, which
is where an intention without an implementation belongs.

What was removed, and what the check actually does instead:

**G1** offered `min_fraction_channels_affected: 0.9` and `max_iqr_db: 0.5`, which
describe a data test: an effect appearing on nearly every channel at once, with
little spread between them, is the reference moving rather than the brain. The
check does not measure that. It fires when the requested `primary_reference` is
`monopolar`, which is a parameter test wearing a data test's documentation. The
data test remains worth writing; it needs per-channel effect sizes, which the
check context does not currently carry.

Note also that `psd_by_condition` computes and writes every montage on a default
run, while G1 only inspects the headline scheme. A monopolar montage therefore
reaches `derivatives/` on runs where G1 is silent, which is intended (the montage
comparison is how the common-mode problem is demonstrated) but is worth knowing.

**G2** offered `max_corr_with_baseline: 0.8` and
`requires_per_contact_baseline_subtraction: true`. The check fires when a recipe
reports that it did not subtract a per-contact baseline, which is the second key
restated as behaviour rather than as a threshold. The first describes a stronger
test, correlating each contact's map against the baseline condition, which is not
implemented and would need the per-contact maps in the context.

**G7** offered `escalate_to_block_above_hz: 100.0`, `require_bipolar: true` and
`prompt_emg_regression: true`. The check warns, and its remedy text says what to
do; none of the three changed severity or blocked anything. Escalation to a block
above a frequency is a reasonable rule and is not implemented. What the finding
recommends, a bipolar montage and EMG regression, is in the remedy sentence,
which is where the reviewer reads it.

**G13** offered `forbid_raw_path_in` and `reference_recordings_by`, both of which
restate the policy described in this document's G13 section, and `policy_source`,
which named `configs/privacy.yaml` without being read. The prose above is the
authority.

There is a live gap here worth stating plainly rather than leaving in a config
key. G13 inspects `paths_in_outputs` on the check context, and the only place in
the package that populates that field sets it to the empty tuple. So G13
short-circuits on every run and has never fired. Redacting run-record tracebacks
(2026-09-09) closed the specific path that leaked, but the check that was
supposed to catch it in general still does not.

**G6** is the exception and went the other way. Its
`antialias_cutoff_fraction_of_nyquist` is now read by
`preprocess.cutoff_fraction_from` and used by every recipe to report its usable
bandwidth, replacing a `0.4` hard-coded in seven places, which was the same
number written as a fraction of the sampling rate rather than of Nyquist.
Lowering it narrows what any run may claim.

## Not yet implemented

Listed so they are not forgotten: multiple-comparison handling across contacts
and bands; minimum trial counts before a permutation test is meaningful; a check
that segment orientation is known before any anatomical direction claim (lead
rotation is frequently unknown, and without it segment labels cannot be mapped to
anatomy).

## G13. Path and filename policy

**Severity: configurable, default block.** Whether raw filenames and directory
names are free of identifiers depends on how a site names and exports its files.
It is declared in `configs/privacy.yaml` as `filenames_deidentified`, and the
default is `false` so that a site which has not confirmed it gets the careful
behavior.

When false, the reader withholds the filename from `Recording.metadata` and
nothing may propagate a raw path into a derivative, a run record, a log line, a
figure caption, or a commit message.

Regardless of the setting, results refer to recordings by manifest key
(`study_id`, `session`, `acquisition`). That is a provenance and portability rule
as much as a privacy one: a path is machine-specific, a manifest key is not.

Metadata fields are governed separately and always: anything listed under
`restricted_metadata_fields` is withheld from `metadata` and reachable only
through `read_restricted_metadata`, whatever the filename policy says. Recording
metadata is where operator names and acquisition paths actually live.
