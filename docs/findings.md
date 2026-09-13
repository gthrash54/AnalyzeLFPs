# Findings

Running log of results. Newest first. One entry per finding, not per session.

Each entry should name the run it came from, so the number can be regenerated:

```
## YYYY-MM-DD Short title

Run: derivatives/<recipe>/<version>/<run_id>
Subjects: n = ?, which ones
Claim: one sentence.
Evidence: the specific numbers, with the uncertainty.
Caveats: what would overturn this.
```

## 2026-09-09 G9's excursion-to-effect threshold of 1.0 is permissive

Not a result about the brain, but a result about one of our own guardrails, and
it could change a number worth showing the PI.

Run: `curriculum/07_guardrails/04_nonstationarity_and_drift_solutions.ipynb`,
regenerate with `MPLBACKEND=Agg uv run python curriculum/tools/make_n4.py`.
Subjects: none. Simulated beta power over 120 epochs, drift modelled as one slow
sinusoid, effect planted in the second half.

Claim: `G9_nonstationarity_exceeds_effect` fires at
`excursion_to_effect_ratio: 1.0`, but a blocked comparison stops being
trustworthy well below that ratio, so a quiet G9 is not evidence that a
comparison is clean.

Evidence: holding the effect fixed and sweeping the drift, with the baseline
window chosen at random and "usable" defined as landing within half the true
effect, 400 repetitions per level gave 99 percent usable at ratio 0.50, 58
percent at 0.67, and 1 percent at 1.00. The half-reliability point is near 0.73.
At ratio 3.3 the mean absolute error was 0.319 against a true effect of 0.150,
and every baseline window in 200 recordings reported a decrease where the truth
was an increase.

A second result from the same module: interleaving removes the bias but not the
drift. Blocked assignment gave a bias of -0.38 against a true +0.15 with a tight
spread of 0.005 around the wrong value. Randomized interleaving removed the bias
to within 2 percent of the effect but converted the drift into variance, its
spread growing from 0.005 to 0.039 across the sweep. Strict alternation cancelled
the drift exactly, which is also its weakness, since it cancels any other
alternating confound into the contrast just as silently.

Caveats: one drift shape, one effect size, one definition of usable, and no real
recording. A threshold set at 0.73 for this simulation would likely fire
constantly on recordings shaped differently, so this does not establish that 1.0
is the wrong number to ship. What it does establish is the DIRECTION of the
error, which is the part that transfers. Whether to lower the threshold is a
scientific decision and is on the backlog, not made here. A random-walk drift,
which has no characteristic timescale, would be the check that decides it.


## 2026-09-09 The time-frequency map advertised delta and theta and measured neither

Run: none yet. Changes every tfr_onset map below about 5.4 Hz, and the padding
of every map at every frequency.

Claim: with `n_cycles = 0.5 * freq`, the wavelet at the default `fmin` of 2 Hz
was 1.0 cycle. A one-cycle Morlet has a bandwidth comparable to its centre
frequency, so it is a broadband envelope detector rather than a frequency
estimate, and the bottom rows of the map did not mean what the frequency axis
said they meant.

Evidence: measured against MNE 1.12.1. `n_cycles` now has a floor of 3, which is
where MNE's own guidance puts the point below which a frequency axis stops being
interpretable. On the default 2 to 150 Hz grid of 40 frequencies the floor binds
below 5.42 Hz, affecting 10 of them. Time resolution at 2 Hz goes from 0.5 s to
1.5 s, and the required padding from 0.398 s to 1.194 s. On
`manifest/windows.csv` the larger pad costs no windows: the earliest onset is at
85 s and the requirement is 3.19 s of margin.

Separately and in the same recipe: the padding was half the nominal wavelet
duration, 0.25 s at the defaults, while MNE builds its Morlet kernel out to five
standard deviations either side, 0.3975 s at the same settings. Measured
`morlet(1000.0, [2.0], n_cycles=1.0)` returns 795 samples, and 795 samples over
sigma_t = 1 / (2 pi 2) is 9.99, so the kernel spans plus or minus five sigma. The
pad was 37 percent short at every frequency, so the module's guarantee that no
reported point was computed from data that was not there was false for the
earliest and latest reported points of every map ever produced.

Caveats: the loss of time resolution below 5.4 Hz is not a cost of this change,
it is a cost of asking for 2 Hz at all. A 2 Hz event cannot be localised to
better than roughly half a cycle by any method; the previous setting did not
escape that, it only failed to say so. `summary.json` now reports
`time_resolution_s` per frequency so the smearing at each row of a map is
readable without recomputing it. Setting `min_cycles=1.0` restores the previous
constant-duration tiling, which is a legitimate choice for an onset analysis and
should be a deliberate one.

Raising `fmin` above the broken region was the alternative and was rejected: this
is a speech project, and the speech envelope and syllable rate live in delta and
theta, so that would have deleted the band most likely to matter.

## 2026-09-09 Every z on the default scale was inflated, by 1.00 to 1.8 times

Run: none yet. This changes the value of `z` in every future psd and bandpower
run, and invalidates the `z` column of every past one.

Claim: `pooled_within_condition`, the default scale, computed the arithmetic
mean of the per-condition standard deviations rather than a pooled standard
deviation, so it was systematically too small and every z it divided was too
large.

Evidence: a pooled SD is `sqrt(sum((n_i - 1) * s_i^2) / sum(n_i - 1))`. The mean
of the SDs is smaller whenever the SDs differ, by Jensen's inequality, with
equality only when they are all equal. Measured on synthetic groups: 1.000x for
equal SDs, 1.003x for SDs of 1.8, 2.0, 2.2, 1.249x for 0.5, 2.0, 5.0, and 1.805x
for those same SDs with segment counts of 5, 10 and 50. The project's own test
fixture, SDs of 2, 1 and 3, moves by 1.080x.

Caveats: the correction makes z smaller, so nothing that was previously
non-significant becomes significant because of it. Any figure or number already
shown carrying a z from this scale is too large by a factor that depends on how
unequal the conditions' variability was, and cannot be corrected without
rerunning. It is the same inequality, in the same direction, that guardrail G3
already refuses to let a recipe commit when it forms a ratio after averaging.

## 2026-09-09 The spectral method named welch was not computing welch

Run: none yet. Changes every psd and bandpower number.

Claim: `method="welch"` called `scipy.signal.spectrogram`, whose default taper
is `("tukey_periodic", 0.25)`, not the Hann taper `scipy.signal.welch` uses.

Evidence: measured on the installed scipy, averaging the spectrogram segments
and comparing against `scipy.signal.welch` on the same data with the same
`nperseg` and `noverlap` gives a median relative difference of 11.9 percent and
a maximum of 75 percent in a single bin. Passing `window="hann"` explicitly
brings the two into agreement to 2.4e-15, machine precision.

Caveats: a reader who reproduced one of our numbers in MATLAB's `pwelch` or with
`scipy.signal.welch` would have found it did not match, and the discrepancy is
largest in the bins with the least power, where a Tukey taper's higher sidelobes
matter most. The fix is asserted against the library rather than against a
stored number, so it survives scipy changing its defaults again.

## 2026-09-09 Overlapping Welch segments do not underestimate the spread

Run: none. Recorded because a proposed change rested on the opposite belief and
was not made.

Claim: 50 percent overlapping segments with a Hann taper are very nearly
independent, so the standard deviation across them is not biased downward and
`n_segments` is a reasonable count of observations.

Evidence: measured over 200 to 300 trials each of white, pink and 1/f^2 noise at
8, 16 and 60 second durations, the SD across 50 percent overlapping segments is
consistently 0.4 to 2.6 percent HIGHER than the SD across disjoint segments,
never lower. The lag-1 correlation between neighbouring segment estimates in dB
is +0.014, giving an effective sample size of about 97 percent of the segment
count.

Caveats: this is a property of the Hann taper, which heavily downweights the
segment edges, which is exactly where 50 percent overlapping segments share
samples. It is the reason Welch specified 50 percent. It would not hold for a
rectangular window. The practical consequence is that moving to non-overlapping
segments would have discarded half the data, made the SD noisier, and slightly
inflated z rather than correcting it.

## 2026-09-09 The multiplicity note undercounted by the number of montages

Run: none yet. Changes the reported test count in every bandpower summary.

Claim: `multiplicity_note` counted only the primary montage while `stats.csv`
carries every montage computed, so it understated the tests actually run by
roughly the montage count, five by default.

Evidence: `tested` was `stats[stats["scheme"] == params.primary_reference]
.dropna(subset=["p_perm"])`. The same summary reported `n_contrast_rows` as
`len(stats)`, the full count, on the next line, so it contradicted itself within
one screen.

Caveats: the note now reports both the total and the primary-montage subset,
because a reader who fixes on the primary montage in advance is in a different
multiple-comparisons position from one who looks at all five and reports the
best. No correction is applied either way; the note says so.

## 2026-09-09 A modulation index is invariant to contact gain, not to contact noise

Run: none. This is a property of the statistic, recorded because a guardrail
decision now rests on it.

Claim: Tort's modulation index can be compared across contacts without a
per-contact baseline subtraction, but only with respect to amplitude scaling.

`pac_modulation_index` was attached to the guardrail layer and
`G2_effect_tracks_electrode_not_state` immediately blocked it. G2 asks whether a
per-contact baseline was subtracted before contacts are compared, because
otherwise a comparison measures which contact sits best rather than what the
brain is doing. The recipe has no baseline condition to subtract, so the field is
now left unset and G2 declines to judge rather than firing.

That is defensible for the reason G2 exists: the modulation index is a normalized
Kullback-Leibler divergence between the observed distribution of amplitude across
phase bins and the uniform one, computed within a single contact. Doubling a
contact's gain doubles both the amplitude and the normalizer and leaves MI
unchanged, so MI cannot track which contact has the larger signal.

The limitation to state on any figure comparing MI across contacts: MI is not
invariant to signal-to-noise. Additive noise flattens the amplitude-by-phase
distribution toward uniform, so a noisier contact reads lower MI for reasons that
have nothing to do with coupling. G2 will not catch this, and no other guardrail
checks it either. A cross-contact MI comparison should be read alongside a
per-contact noise measure, and the QC hf_noise_ratio flag is the one already
computed.

## 2026-09-04 Pooling rings with segments produces false QC flags

Not a scientific result about the brain, but a methods finding that will affect
every subject with a directional lead.

Running the QC detectors over 60 s of overt speech on the first subject analyzed, monopolar, at
2034.5 Hz, comparing each contact against all others on its lead flagged both
leads' ventral ring contacts for high-frequency noise and for variance. Their
values were BELOW the group median, not above: they were flagged for being
unlike the segments, which they are, by construction.

A ring contact has roughly twice a segment's surface area. That is the same
physical fact the geometry detector uses to tell rings from segments by
impedance, and it means rings and segments are not comparable populations for an
outlier test.

Comparing within ring and within segment instead removed all four flags. Since a
1-3-3-1 lead has only two rings, which is below the minimum channel count for a
robust statistic, the rings now correctly report insufficient_channels rather
than a threshold that cannot be supported.

Practical consequence: on a directional lead, ring contacts cannot be QC'd by
comparison with their neighbors. They need either an absolute threshold, a
comparison against the same contact in other recordings, or a reviewer looking at
them. Worth raising with the PI in the QC calibration session.

## 2026-09-04 Two QC statistics are duration-dependent, so fixed thresholds do not transfer

Found by running the detectors over the full 515 s block rather than the 60 s
window used while developing them. Same data, same channels, same code.

**Excess kurtosis grows with duration.** Median across the 16 monopolar contacts
was 170 over 60 s and 1429 over the full block. That is expected of a heavy-tailed
process: a longer record is more likely to contain an extreme value, so the fourth
moment keeps climbing. The configured threshold of 20 therefore flags every
channel on any real recording, and raising it would only push the problem to the
next duration.

**The amplitude-window rate depends on the span analyzed.** 24.7 percent of
one-second windows exceeded eight times the median over a 60 s span, and 2.9
percent over the full 515 s block, because the median is taken over whatever was
loaded. The same window can pass or fail depending on how much data the caller
passed in.

**Line noise is segment-dependent, not just duration-dependent.** Prominence at
60 Hz on the first contact was about 135 over the 85 to 145 s speech window and
about 2 over the first 60 s of the block. Mains contamination genuinely varies
across a case, so a single per-channel verdict for a whole recording is the wrong
shape for this detector.

Consequences, none of them fixed by picking better numbers:

1. A threshold on raw kurtosis is not a transferable statistic. Either compare
   only across equal spans, or use something duration-stable.
2. The amplitude detector needs a fixed reference, computed once over the whole
   recording and passed in, rather than recomputed over whatever slice is loaded.
3. Line noise should be reported per window, not per channel.

Thresholds were deliberately NOT retuned. Adjusting a threshold until the flags
look reasonable is fitting the threshold to the data, and it would produce a QC
layer that always passes. The numbers are recorded, the config says they are
uncalibrated and why, and the evidence on every affected flag now carries the
duration or reference span it came from.

Agenda item for the calibration session with the PI.

## 2026-09-04 Fixing the two statistics, rather than their thresholds

Follow-up to the entry above. Both detectors were changed at the level of the
statistic. Neither threshold moved.

**Kurtosis is now the median across fixed-length blocks**, rather than over the
whole record. Measured on the same 16 contacts: the whole-record statistic gave
median 170 over 60 s and 1429 over 515 s; the block-median gives 0.8 and 0.6.
Duration-stable, and near zero, which is what a clean LFP channel should look
like. The old number was a handful of transients dragging the fourth moment of
the entire record.

That also fixes what the detector means. A single artifact no longer condemns a
channel, which is the window detector's job, while a channel that is heavy-tailed
in every block is still caught.

One robustness problem surfaced while testing: a median over two blocks is their
mean, so one bad block drags it and the statistic stops being robust. The block
width now shrinks until there are at least five, and the count used is part of the
evidence.

**Amplitude windows use a robust z on log peak-to-peak, and merge into episodes.**
A bare ratio to the median has no interpretable false-positive rate. Merging
contiguous windows matters more: an artifact is an episode, not five separate
seconds, and one flag per second is unreviewable.

Effect on the real recording, same data, same thresholds: 258 flags became 55.
The 16 kurtosis flags, which were every channel, went to zero. The 238
amplitude flags became 51 episodes, about three per channel over 515 s.

Still uncalibrated, and still an agenda item. The point of this change was to make
the statistics answer the question they claim to, so that calibrating them with
the PI is worth doing.

## 2026-09-09 The Inference course, and three claims in configs/statistics.yaml that turn out to be arithmetic

**The unit you shuffle is the hypothesis you test.** On identical AR(1) trials
with a lag-1 correlation of 0.9, shuffling samples between conditions rejected a
true null in 61 percent of sessions while shuffling trial labels rejected it in
7. The sample-shuffled null was 4.2x too narrow, and the factor is predictable:
100 samples at that correlation carry about 5 independent ones, and sqrt(100/5)
is the width error.

**Permute the way you randomized, and where nothing was randomized, say what you
are assuming instead.** Under a session drift of rho 0.95, a free label
permutation rejected a true null in 63 percent of blocked sessions, in 4.0
percent of randomized ones, and in 0 percent of alternating ones. The
over-conservative case is not the safe one: at a true effect of 0.3 the free
shuffle found the effect in 24 percent of alternating sessions where a paired
sign-flip test found it in 54. That sign-flip test is not the design's own null,
though, because an alternating design randomizes nothing. It rests on within-pair
differences being symmetric under the null, which a wandering baseline satisfies
and a trending one does not: on a steadily trending baseline the same test went
from 4.4 to 11.6 percent as the trend steepened.

**Selecting on significance selects for overestimates.** At 8 trials per
condition the estimator was unbiased over all runs while the significant subset
overstated a true 0.30 effect by 3.9x, with 5 percent of those results pointing
the wrong way. This is the intraoperative trial count, not a hypothetical one.

**A smoothed map asks far fewer questions than it has points.** Testing all 200
points of an empty smoothed time course at 0.05 produced a significant point in
73 percent of maps, which inverts to about 26 independent tests. The smoothing
kernel's resel count says 14, so at this smoothing the rule of thumb undercounts;
one configuration does not make that a general bound. Bonferroni's false positive
rate on those maps was 0.000, which is what paying for 200 independent tests
buys. The cluster permutation test beat Bonferroni at both effect sizes tested
and beat Benjamini-Hochberg only where power was scarce, drawing with it at the
strong effect where both are near ceiling: its advantage is a low-power
advantage, which is the regime this lab records in.

**The maximum-statistic null is what makes a cluster test a correction, and the
mistake hides on small maps.** Replacing the maximum with a null pooling every
cluster from every shuffle cost little on a map holding about one cluster per
shuffle, where the two are nearly the same distribution, and ran several times
the nominal rate on maps holding four to six.

**A significant cluster has no edges, and its reported extent grows with the
effect.** With a true effect fixed at 20 points, the reported cluster width went
21, 24, 29, 35 as the effect strengthened, and the reported window at the largest
effect was 83 to 117 against a truth of 90 to 110. Part of that is the
estimator's own smoothing, which widens a sharp 20-point effect to 22 points
before any test runs. The cluster test licenses "these conditions differ
somewhere in this map" and nothing about when.

**`configs/statistics.yaml`, three caveats proved rather than asserted.** The
`whole_recording` centre shrinks every effect by exactly 1-f, where f is the
fraction of the recording carrying the effect, independent of effect size, noise
and channel. The `across_conditions` scale has a hard ceiling of (k-1)/sqrt(k) on
|z|, verified at k = 2, 3, 4 and 6; at two conditions it is not a ceiling but a
constant, and every z is exactly 0.7071 regardless of the data, so the config's
"unstable" is too kind and its "meaningless with fewer than three" is exact. The
`own_condition` scale reported two conditions carrying the same true 3 dB effect
2.9x apart when one was 3x noisier, where the pooled scale reported them equal.

**G8 asks for both columns because they answer different questions.** Over 400
runs of 16 channels with heterogeneous true effects and noise, the largest-|dB|
channel was also the largest-|z| channel in 19 percent of runs, and the
largest-|dB| channel had |z| below 2 in 45 percent. Ranking by dB found the truly
largest effect 54 percent of the time against z's 27. That gap is not the noise
in the denominator: an oracle z given each channel's exact noise scored 28
percent, recovering 5 percent of the gap. z ranks a different quantity, since the
channel with the largest effect need not be the channel with the largest
effect-to-noise ratio. dB is how big; z is whether to believe it.

## 2026-09-09 TDT filenames encode the date of surgery, so the privacy config was wrong

`configs/privacy.yaml` declared `filenames_deidentified: true` for both TDT
formats, justified in its own prose by the claim that the timestamp embedded in
a raw TDT filename is the UPLOAD time, recorded on days deliberately separated
from the procedure.

That claim was testable and is false. For each staged tank the `YYMMDD` field in
the filename was compared against the acquisition date in that block's own
`Notes.txt`:

    287 of 401   filename date equals the acquisition date exactly
    114 of 401   differ by exactly one day
      0 of 401   consistent with an upload on a separate day

The one-day cases are what a timezone offset or a block crossing midnight
produces, not evidence of a separate upload. The filenames carry the date of
surgery to within a day.

Two consequences. Guardrail G13 reads its effective severity from this flag and
is not overridable, so the wrong value handed a privacy check a blanket pass for
every TDT recording in the archive, which is most of it. And separately,
`StreamInfo.start_time_s` on a tank is a Unix epoch timestamp rather than an
offset from the block start, so writing it into any derivative writes the
surgery datetime into that file. A derivative store must record `t0_s = 0.0` and
relative offsets only.

Both TDT formats are now `false`. The general point is that a config comment
asserting a fact about the data is a claim, not a policy, and the archive was
sitting there the whole time to check it against.

## 2026-09-09 The Decoding course: what a fitted parameter is not

**Random k-fold on an autocorrelated recording invents a decoder.** With the
target generated independently of every channel, so the honest answer is exactly
zero, random five-fold reported r = 0.59 for ridge and r = 0.94 for a
nearest-neighbour model at an epoch-to-epoch autocorrelation of 0.95. Contiguous
folds on the same recording reported under 0.10 and a fresh session under 0.07.
At rho = 0 every scheme reported nothing, which identifies the cause as the
autocorrelation rather than the model. Full case in `docs/backlog.md` as a
proposed G14, not adopted.

**The leak damages the number, not the model.** With a real relationship present,
the penalty chosen under leaky cross-validation achieved 0.210 against an oracle
of 0.249 and reported 0.702. The leaky estimate also carried the tighter spread
across sessions, 0.089 against contiguous folds' 0.278, so it looks more reliable
as well as being wrong.

**A ridge weight is a fact about the montage.** Duplicating one contact, which
changes no physiology, raised the total weight on that source 2.8x at a heavy
penalty and 1.2x at the tuned one, while the decoder's predictions correlated
above 0.99 with the original throughout. The distortion scales with the penalty,
because the penalty is what makes splitting a weight across duplicates cheap.

**Training error can never choose a ridge penalty.** It is monotone
non-decreasing in alpha for any X and y, which is a theorem rather than a
property of the data, so its minimum is at alpha = 0 for every dataset.

**A wrong gradient still trains.** Dropping the tanh derivative from a backward
pass produced a gradient disagreeing with central differences at the first
decimal place, a training curve that cut the loss 74 percent and then flattened
like an ordinary converged run, and a final loss 18 times worse than the correct
gradient's. The check that catches it costs two forward passes per parameter and
agreed with the correct gradient to 1.1e-9.

**A network's weights are not identified.** Five networks trained on identical
data made predictions correlating above 0.99 with weight vectors correlating 0.03
on average and -0.52 for one pair. Reordering six hidden units changes the
predictions by 4e-16 and flipping a unit's sign changes them by exactly zero, so
those two symmetries alone give exactly 46,080 weight settings computing the same
function.

**Nonlinear beats linear only above a few hundred trials.** With a linear truth a
network never beat ridge at any sample size. With a quarter of the signal out of
linear reach it took the lead for good between 160 and 320 trials, and at 40
trials with half the signal nonlinear the two were indistinguishable. At 80
trials the network cut squared bias 62 percent and multiplied variance 4.2x. At
40 trials per session, establishing which model is better would take about 218
sessions; at 800 trials it takes one.

**A decoder's weight map stops describing the array as soon as there is anything
to subtract.** With no nuisance, weight magnitude ranked contacts against the true
pattern at Spearman 0.97. With a shared nuisance five times the source, that fell
to 0.31: the contact recording none of the source acquired one of the largest
weights, and 3 of 10 contacts that do record it were given negative weights. The
decoder correlated above 0.99 with the source throughout, so this is a good
filter rather than a bad model, and a filter subtracts.

**One matrix multiply restores it, for linear decoders only.** Multiplying the
weights by the data covariance gives a vector proportional to the true pattern,
because the covariance undoes exactly the cancellation the weights perform. Rank
agreement was above 0.85 at every nuisance level from zero to ten times the
source, with no sign errors anywhere. It remains a pattern over contacts and not
a source location: one generator, and two weaker generators either side of it,
produced patterns correlating 0.98 with the same peak contact. There is no
version of the transform for a network, because there is no single weight vector
to multiply.

## 2026-09-09 recipes/psd.py averages in decibels, and that is the safer of the two orderings

**Corrected the same day.** The first version of this entry claimed the bias
depends on the segment count and leaves up to 0.51 dB in a contrast between
conditions of unequal length. That was wrong: it described the opposite ordering
to the one the code uses. A review caught it and the measurement below replaces
it. The proposed guardrail that followed from the error has been withdrawn from
`docs/backlog.md`.

`_segment_spectra` returns power, `_to_db` converts each segment, and
`db_segments.mean(axis=0)` averages the decibels. Averaging is linear and the
decibel conversion is not, so there are two orderings with different behaviour:

| segments k | average power, then convert | convert, then average |
|---|---|---|
| 1 | -2.51 dB | -2.51 dB |
| 2 | -1.17 | -2.51 |
| 4 | -0.56 | -2.50 |
| 16 | -0.14 | -2.52 |
| 64 | -0.03 | -2.50 |

Averaging the power first is low by `(10/ln 10)(psi(k) - ln k)`, which vanishes as
segments are added. Converting first is low by `gamma * 10/ln 10 = 2.507 dB` at
every k, because averaging preserves an expectation. Both matched their closed
forms to better than 0.06 dB.

**The app does the second, and for the contrasts it reports that is the better
choice.** A constant offset cancels in a difference at any pair of segment
counts: the measured residue between a 40-segment condition and a 4-segment one
is under 0.01 dB. Had the recipe averaged power first it would have been
asymptotically unbiased on absolute values and would have introduced a 0.51 dB
artifact into exactly that comparison.

So every absolute dB value the app has produced is about 2.5 dB low, and every
difference between two of them is right.

**The constant is method dependent.** It is `gamma*10/ln 10` only when each
segment is a single periodogram, which is the Welch path. `_segment_spectra`'s
multitaper branch calls `psd_array_multitaper`, which averages over DPSS tapers
before `_to_db` sees the value, so that estimate already has more than two
degrees of freedom. Measured on both paths with the recipe's own settings:
**-2.506 dB for Welch, -0.313 dB for multitaper.** This is what makes correcting
the offset harder than it looks, since a subtraction would have to know which
method produced the column.

**The one exception.** `dbsspeech.stats.normalize` offers a centre of `none`,
where `_center` returns zero and z is the value divided by a scale rather than a
difference of two values. The 2.51 dB offset passes into that z undiminished: at
a scale of 2 dB it is 1.25 z units on its own. It is the only one of the four
centres for which the cancellation fails, and `configs/statistics.yaml` already
describes that option as a signal-to-noise ratio rather than a contrast.

Not changed.

## 2026-09-09 The Probability course, and two things it found in shipped code

**A periodogram's relative error is 1, at every record length.** It is an
exponential random variable whose mean is the true spectrum, verified against the
whole distribution (KS 0.004) rather than its first two moments. It reads below
half the true power in 39 percent of records and above twice it in 14, and a
sixty-four-fold increase in record length changes none of that. Averaging k
segments gives relative error 1/sqrt(k), to three decimals at every k tested.
This derives what SIG 4 asserted.

**For 1/f noise there is no effective sample size worth the name.** Measured by
block averaging on one long recording, n_eff grew as 0.233*ln(n) rather than as a
fixed fraction of n. A thousandfold increase in data cut the error bar by 1.6x
where independent samples would cut it by 32x. Sweeping the spectral slope, the
gain from a 256-fold longer record was 14.7x for white noise, 4.3x at a shallow
aperiodic slope, 1.6x for 1/f, and 1.0x for a random walk. GRL 4's drift and
ordinary variance are the same phenomenon at two timescales.

**The finite-n correction closes a gap INF 1 left open.** INF 1 measured a null
4.2 times too narrow and predicted 4.36 from the asymptotic effective sample
size. The exact finite-n form predicts 4.15, which is the whole discrepancy.

**Two independent random walks correlate at 0.42, and the standard test calls it
significant 93 percent of the time at n=1000.** The rate rises with the amount of
data, which almost nothing else does. An AR(1) at rho 0.9 rejects about 53
percent of the time; white noise 5. Linear detrending still rejects 92 percent at
n=2000, because a walk is not a line plus noise. First differencing restores the
nominal rate exactly, and costs real signal when the relationship is in the
levels: at an observation noise of 2.0 the levels correlate 0.93 and the
differences 0.11.

**G9's excursion ratio depends on recording length.** Under a random walk the
excursion grows as 1.6*sqrt(t), 42-fold over a thousandfold increase in duration,
so the same process passes G9 in a short recording and fails it in a long one.
GRL 4 derived the threshold under a sinusoidal drift, where the excursion is a
fixed property of the recording. Proposal in `docs/backlog.md`; nothing changed.

**Raw PLV compares spike counts, and the size of it is the size of a result.**
The null phase-locking value is sqrt(pi)/2/sqrt(N), derived here from the
resultant of a two-dimensional random walk being Rayleigh distributed (KS 0.007)
rather than checked against a prediction as SPK 4 does. With true locking held
fixed, a condition with 10 spikes reported a PLV 0.062 higher than one with 100,
against locking values of 0.2 to 0.5. The direction is the dangerous one: a
quieter condition reports more locking, so anything that lowers firing rate
manufactures an apparent increase. Pairwise phase consistency was flat to within
0.005 across a fortyfold range of counts, and estimates the square of the
locking rather than the locking.

**A refractory period alone makes a neuron sub-Poisson.** Ten milliseconds took
the interval CV from 1.00 to 0.83 and the Fano factor from 1.02 to 0.69, so a
Fano factor below 1 is what a healthy unit looks like.

## 2026-09-09 A dual-lead block contains interleaved speech and rest, labeled from video and microphone

First state labels on a block with cortex and both leads live: subject H
rainbow_passage, 116 s, read from the derivative store (mic at 16 kHz) and the
block's camera video (20 fps, 2318 frames against 2315 Cam1 events, aligned in
order). On a one-second grid, with movement as video motion energy above
median plus three MAD and voice as mic RMS more than 6 dB above its quietest
decile:

    speech only     63 %
    neither (rest)  26 %     longest still stretch 50 s
    both             9 %
    movement only    3 %

So the within-block contrast the plan needs exists in the terminal dual-lead
blocks, at least for speech against rest, and it comes from the signal, not
the block name. Two caveats that decide what this is worth. The mic label does
not yet separate the patient from the examiner, so "voiced" overstates patient
speech until diarization runs. And the audit's speech-vibration control (Bush
2022) has not been applied; a block labeled "speech" from the mic is exactly
where that artifact lives, so nothing here is a neural result yet.

Also settled: every block has an .avi in Box (the audit's "no motion signal in
this project" was a staging artifact), and Cam1 frame times put its frames on
the neural clock to within three frames. Video shows a face and stays local.
Tool: `~/DBS Data/_tools/video_motion.py` (system ffmpeg, no new dependency).

## 2026-09-09 First speech-vibration screen: no speech-specific coherence, but a common-mode mic pickup at rest

Per-channel coherence between the microphone and every `ecos` channel on
subject H rainbow_passage, over exact one-second segments labeled speech (73 s)
against segments labeled rest (30 s), monopolar and non-overlapping bipolar.
Tool: `~/DBS Data/_tools/audio_coherence.py`.

The Bush et al. 2022 vibration component would show as coherence in the voice
band (80 to 300 Hz) during speech and not at rest. It does not: the speech to
rest ratio of mean F0-band coherence is 1.0 to 1.3 on every channel in both
montages, and no channel reaches the 3x flag. At this sensitivity, on this
block, the speech-vibration artifact is not evident.

What is evident is something else. Coherence with the microphone at REST is
0.17 on every monopolar cortical channel (identical to three decimals across
channels, peak at 138 Hz) and up to 0.50 on bipolar lead pair 21-22 at 402 Hz,
against a statistical floor near 0.03 for 30 segments. Neither frequency is a
spectral line in the store's native-rate PSD summaries of either signal, so
this is a stable phase relation at modest power, not shared mains. Identical
values across all monopolar channels is the signature of the shared reference
(guardrail G1's concern), meaning the microphone channel and the amplifier
share a common-mode component. Bipolar referencing reduces it on the strip and
does not remove it on lead 2.

Consequences. The microphone cannot be used as a regressor against neural
channels without first removing that shared component, and any mic-derived
"speech" label must be paired with this screen per block. The unconnected
amplifier inputs the audit recommended as blank-pin controls are the right
tool for characterizing it, and this dual-lead block has none, so the
single-lead blocks (eight unconnected inputs each) are where to measure it.

## 2026-09-09 What a contact label can support, and what it cannot

REC 5. "Contact 2b, in STN, showed the effect" contains three claims of different
strength, and the intuition about which is solid is backwards.

**Corrected during review.** The first version used the wrong branch of STO 1's
two-way ordering for the estimator spread, and a two-sided boundary probability
where the setup has one boundary. Both are fixed below and both moved a headline
number. It is the same class of error STO 1 itself made about the dB bias, which
is why Section 2 now simulates both branches instead of citing one.

**The estimator spread depends on the ordering, and this app uses the noisier
one.** `psd.py` averages decibels, so its spread is one segment's divided by
sqrt(k): 2.78 dB at four segments. Averaging power first gives 2.31 dB. Both
verified by simulation.

**The claim needing no imaging is the weakest.** On a 1.5 mm pitch lead the
median gap between the best row and the second is 1.98 dB, smaller than the 2.78
dB spread it must beat. The reported best row was the true best row **67 percent
of the time** at four segments, 80 at sixteen, 90 at sixty-four. On a 3.0 mm lead
the gap is 5.45 dB and the figures are 86, 93, 97.

**That percentage is an assumption as much as a measurement.** It ranges 44 to 86
percent across defensible assumptions about how far the source sits from the
lead, and it assumes estimator noise independent across rows, which is the
pessimistic choice: at correlation 0.8 the same setting gives 82 percent, and
REC 1's 4.6 mm reach against a 1.5 mm pitch means the true correlation is not
zero. The shape is robust; the number is not.

**Nothing physical decides the answer at a boundary.** Moving a source 0.2 mm
across the midpoint between rows changes every amplitude by 7 percent and flips
the winner. At the midpoint the two rows record the same amplitude bit for bit,
so `argmax`'s tie-breaking decides it.

**A registration accuracy figure is meaningless without a margin.** For a single
boundary the chance of a wrong label is `Phi(-margin/sigma)`, verified against a
signed shift crossing that boundary. Margin 1 mm with error 1 mm gives 16
percent, about one label in six; margin 3 mm gives 0.1 percent. Only the ratio
matters. A second boundary adds nothing in a 6 mm target and 42 percent more in a
2.5 mm one.

**The stability of a contact count belongs to two lengths, not to a lead.** A 1
mm error changed the rows-in-target count 45 percent of the time on the 1.5 mm
lead and 0 percent on the 3.0 mm lead at a 6 mm target. That zero is a
coincidence: 6 mm is exactly two of the wide lead's pitches, so a shift pushing
one row out brings another in at the same instant. At 6.5 mm it is 13 percent,
the ordering reverses by 6.9 mm, and at 9 mm the wide lead is wrong every time.

**Two of the three numbers a reader needs are already stored.** Segment count
(`n_segments`) and the best-to-second gap are computable from what `psd.py`
writes. The margin is not, because this app performs no registration, which is
why REC 5 ends in a wording rule rather than a guardrail proposal.

## 2026-09-09 The common-mode signal, measured on inputs connected to nothing

subject H increment1_depth1 records 28 channels with one lead implanted, so
contacts 21 to 28 are amplifier inputs connected to no electrode: the blank
pin control Bush et al. 2022 used. On the 55 seconds of that block with no
stimulation epoch within half a second (`~/DBS Data/_analysis/blank_pins.py`,
working rate 8 kHz):

    the eight blank inputs are identical to each other to three decimals
    rms 7.1 x the median connected channel
    coherence with the microphone channel: max 0.33 at 131 Hz,
        voice band (80 to 300 Hz) mean 0.034
    mean coherence with connected channels, 60 to 1000 Hz:
        monopolar 0.106, non-overlapping bipolar 0.069

Reading. A floating input carries the amplifier's reference and whatever
couples into the headstage; that eight inputs agree exactly says it is one
signal. Its coherence with the microphone at 131 Hz, and the 138 Hz seen at
rest on the passage block, mean the mic channel and the amplifier share an
electrical component near the stimulator's 130 Hz; acoustic speech does not
enter the neural channels this way (voice band coherence is at the floor).
Bipolar referencing removes about a third of the common-mode share, not all
of it. Every dual-lead block has all 28 contacts connected and so no blank
pin; the common-mode signal for those blocks has to be estimated from the
channels themselves, and this measurement is the reference for how large it
is. The per-block spectrum is saved as blank_pins_psd.npz.

## 2026-09-09 Equipment lines defeat segment re-pairing surrogates, and they are common-mode

First state-resolved spectra and coupling on subject H rainbow_passage and
motor_lesion_dbs2 (bipolar, 1 kHz working rate, states equalized to 27 to
30 s). Two things to know before any of it is read as physiology.

The strip's specparam "peaks" form an evenly spaced comb (roughly 9.5 Hz
apart: 20, 29, 38, 47, 57 Hz; 17.5, 26, 36, 46, 55, 65 Hz in the motor block)
and both leads show fixed lines at 28, 48 and 97 Hz in every state. The
blank-pin common-mode spectrum from increment1_depth1 carries lines at 20, 31,
37, 48, 49, 50 and 96 Hz. These are equipment, riding on the amplifier's
common-mode signal, present in the bipolar montage, and specparam calls them
peaks. Any band claim has to exclude them first.

A line at an integer frequency has the same phase in every one-second
segment. A surrogate that re-pairs whole segments therefore cannot destroy
its coherence, and on the first coupling run the null came out as large as
the measurement (lead1 to lead2 at rest, low beta: dwPLI 0.42 against a
surrogate 95th percentile of 0.45). Replaced with a cyclic shift of one site's
continuous signal by a random offset that is at least two seconds and never a
whole number of seconds, and with per-block line detection whose bins are
excluded from every band average (`~/DBS Data/_analysis/state_coupling.py`).

## 2026-09-09 No single signal statistic tells a floating input from a connected lead across rigs

Needed for subject C and subject D, which have no impedance sheet. Three candidate
rules, each tested on twenty seconds from the middle of five subject C blocks and
four subject H blocks whose lead status is known from the census or the protocol.

    pairwise correlation within a contact range
        subject H blank pins ~1.00; but a connected lead against a distant shared
        reference reads 0.81 to 0.98 in subject C; no threshold separates them.
    amplitude of adjacent differences over monopolar amplitude
        subject H blank pins 0.23; subject C floating inputs 1.0 to 2.0 (independent
        noise) in some blocks and 0.02 in others; the reference configuration
        changes across a case and the statistic with it.
    aperiodic exponent, 2 to 100 Hz
        floating inputs -0.26 to 0.44; connected leads 0.86 to 1.12 in
        stimulation-off blocks but 0.28 to 0.50 in stimulation-on blocks,
        overlapping the floating range.

So the floating inputs on the subject C rig are independent low-amplitude noise,
those on the subject H rig one loud identical signal, and stimulation flattens a
connected lead's spectrum into the floating range. Adopted instead, for
subjects without a sheet: the protocol rule that all seven sheeted subjects
satisfy without exception, increment2 blocks and terminal two-lead blocks are
dual-lead, increment1 and everything earlier are not. The signal-based
selection that preceded it over-selected eight increment1 blocks and
motor_baseline in subject C; those labels remain on disk and are not in the
cohort table.

## 2026-09-09 Regressing the blank-pin signal out makes things worse; bipolar removes the inter-site common mode

A teammate session proposed regressing the measured blank-pin signal out of
every channel in place of bipolar re-referencing, on the grounds that the
reference is measured directly and a 1-3-3-1 lead has no clean non-overlapping
pairing. Tested on subject H increment1_depth1 (55 stimulation-free seconds,
8 kHz working rate), mean coherence in 60 to 1000 Hz:

    montage                                   with the mic   strip to lead 1
    monopolar                                     0.020           0.267
    bipolar non-overlapping                       0.016           0.008
    monopolar minus blank-pin projection          0.030           0.386
    monopolar minus channel-median projection     0.021           0.174

The blank-pin mean correlates -0.57 with the median of the connected
channels: a floating input does not carry the common-mode mix a connected
electrode carries, so projecting it out injects rather than removes. The
figure recorded earlier, that bipolar removes only a third of the common
mode, was coherence of the blank pins with connected channels; the quantity
that matters for connectivity, coherence between connected channels at
different sites, falls from 0.27 to 0.008 under bipolar. Bipolar stays as the
montage, and the open problem is the pairing rule on a 1-3-3-1 lead, not the
montage class.

## 2026-09-09 The stimulation blocks need a train-conditioned split before any state contrast is read

The PeA epochs in the increment blocks are individual pulses at 130 Hz
(median inter-onset interval 7.7 ms) delivered in about 54 trains of 0.7 to
2.5 s per block, the same scripted sequence in every subject (2,601 pulses in
subject H increment2_depth1 and in subject E increment2_depth3 alike). Pulses land
in roughly 60 percent of seconds. A behavioral state label that ignores this
is therefore confounded with stimulation: the first cross-subject table's
large, uniform "speech minus rest" increases in stimulation blocks (5 of 5
subjects) are, until shown otherwise, stimulation-on against
stimulation-off.

Built: `~/DBS Data/_analysis/stim_split.py` writes a per-second table beside
each block (`stim_on` when any pulse falls within 0.5 s of the second), the
shared loader honors an on/off filter, and the spectra and coupling tools
write `_stimoff` and `_stimon` outputs. The runner gives stimulation blocks
two conditioned passes and never an unconditioned one; the aggregator reports
three conditions (awake, stimulation-block off-seconds, stimulation-block
on-seconds) and never pools them. On subject H increment2_depth3 the split
leaves 54 off-seconds of 148, enough for 24 s per state; the off-seconds
coupling between the leads sits inside its null for every band, which is
what a 24 s estimate on stimulation-free seconds should show absent a large
effect. The conditioned rerun across all nine subjects was queued at session
end; its report lands at ~/DBS Derivatives/analysis/cohort_coupling_report.txt.

## 2026-09-09 The camera's keyframe interval puts a 5.0 Hz line in every motion series, and the first tremor detector called it tremor

The OR video is MPEG-4 with an I-frame every 12 frames (ffprobe, three
subjects, two frame rates). An I-frame is quantized differently from the
P-frames around it, so the frame-difference energy steps into and out of it:
a comb at fps/12 (1.67 Hz at 20 fps; 1.63 Hz measured) whose third harmonic
is 5.0 Hz, inside the tremor band, in every second of every block. A 4 to 8 Hz
periodicity test on the raw motion series flagged a third of all seconds at
"5.0 Hz" in subject E and subject H alike. Two more traps in the same pass: the
`Cam1` frame timestamps arrive in bursts (gaps of 0.4 ms to 170 ms), so the
median gap is not the frame rate and interpolating onto it invents a 6 to
7 Hz timing comb; and a ratio of the band's peak to the median periodogram
bin flags white noise in most windows, because the largest of seventeen
exponential bins is always several medians up.

Fixed in `_tools/state_labels.py`: the keyframe period is measured from the
series by frame index and the two affected frames of each cycle are
interpolated over; frames are placed evenly between the first and last
timestamp (count over span is the rate); the tremor statistic is the band
peak over a log-log aperiodic fit, threshold 10 (exceeded by chance about
once in a thousand windows), with harmonics of any sub-band fundamental
excluded. Video tremor then falls to 0 to 35 s per block on five blocks,
with the runs short (1 to 7 s) except 35 s at a 6.0 Hz median on subject H's
motor block, the one block where a tremor state is plausible and worth a
look by eye.

The EMG envelope is a weaker tremor detector and is reported, not trusted.
Speech modulates a facial or laryngeal envelope at syllable rate, 4 to 7 Hz,
so with the four `emgg` muscles unnamed an EMG tremor flag during a voiced
second cannot be told from talking (19 of 23 EMG-flagged seconds on the
passage block are voiced); the combined flag takes EMG only when the mic is
quiet. the first subject's terminal block shows a 0.5 Hz-spaced comb on all four raw
EMG channels (something in the room with a two-second cycle, not the
heartbeat) and the envelope test flags two thirds of it; a comb detector
built to catch this returned the smallest lag on every block and was
removed rather than tuned. Heartbeat and pulse-comb template subtraction is
the proper remedy and is on the backlog. EMG movement (envelope above the
channel's median plus three robust SDs) agrees with the video movement flag
on only 2 of 13, 3 of 31, 11 of 42 video-movement seconds across three
blocks: the two flags see different things (a hand in frame versus a
recorded muscle), and the state keeps the video flag by default with
`--move-source` as the switch. Nothing here is neural; the cohort table now
carries tremor, tremor-while-voiced and EMG-movement seconds per block so
these facts sit beside the state counts.

## 2026-09-09 The coupling estimator and its null pass their synthetic checks

`_analysis/test_state_coupling.py`, six tests: planted low-beta coupling
(band-limited noise shared with a 12 ms lag under independent noise) is
recovered above its continuous-shift null in its band and nowhere else; a
shared zero-lag reference that drives magnitude coherence above 0.5 gives
dwPLI below 0.1; the debiased estimator's mean under the null is within 0.02
at 200 s and 0.05 at 20 s; the continuous shift takes planted coupling to
under half its measured value; a pure 48 Hz line keeps dwPLI near 1 under
whole-segment re-pairing and under continuous shift alike (the archive's
lesson: lines are excluded, never nulled); and the stimulation split flags
the seconds around each pulse with the margin. The first draft of these
tests planted a sinusoid and failed instructively: a sinusoid keeps a
constant lag under any constant shift, which is exactly what an equipment
line is. Planted coupling must be noise.

