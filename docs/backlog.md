# Backlog

Things noticed while doing something else. Not decisions, not findings: work that
was deliberately not done at the time, with enough context to pick up later.

Newest first.

## 2026-09-09, what stops this running on another lab's data

An audit of the assumptions in the code, in the order they would stop someone.
None of this is needed for this lab's own recordings; all of it is what "plug and
play for all types of neuroscientists" would require.

**Two of these are now done**, by merging `generalize-for-other-labs`: readers
for BrainVision and EDF are registered, so `available_formats()` returns four,
and `detect/windows.py` proposes condition windows from a recording's own task
markers. The three below that are still open are marked. The audit was written
against this branch before that merge, which is why the first item reads as
though nothing existed.

- ~~**Only TDT recordings can be opened.**~~ DONE, see decisions 2026-09-08. `available_formats()` returns
  `('tdt_mat', 'tdt_tank')`. `io/loader.py` lists a `.vhdr` suffix for a
  `brainvision` format that has no registered reader, so asking for it fails
  after the manifest validates rather than before. This is the first and largest
  wall: a lab recording on BrainVision, Blackrock, Intan, or anything exported
  to EDF cannot get past the front door. The reader interface itself is the good
  news: `io/base.py` has a registry with `register_reader(name, factory,
  sniffer)`, so a format is a new module, not a change to anything else.
  Either register a reader or drop `brainvision` from that suffix table, because
  a format named in the code and absent from the registry reads as supported.

- STILL OPEN. **Mains frequency is a 60 Hz default that nothing ever overrides.**
  `qc.flags.line_noise` and `qc.report` both take `mains_hz` and default it to
  60. No call site anywhere passes it, so a 50 Hz lab silently gets a 60 Hz
  detector and a QC figure with red lines in the wrong places.
  `configs/bands.yaml` fixes `line_noise.fundamental: 60.0`, and
  `configs/layout_detection.yaml` already specifies a detector that would choose
  between 50 and 60 by spectral prominence. Wire the config value through first;
  the detector is the nicer answer later.

- STILL OPEN, and the second half of it is a correctness bug rather than a
  portability gap. **`sfreq_target_hz` defaults to 8138 Hz in three places in
  Python**, which is
  this rig's TDT rate (24414.0625 / 3) and nobody else's. It is a decimation
  target, so a slower recording is left alone rather than broken. The real
  problem is downstream: `psd._shared_guardrail_context` reports
  `sfreq_hz: params.sfreq_target_hz` and `usable_bandwidth_hz: target * 0.4`,
  which is the *requested* rate, not the rate decimation achieved. On a 1000 Hz
  recording with the default untouched, G6 computes a usable bandwidth of
  3255 Hz and would pass a band that the data cannot support. Report the achieved
  rate, and move the default into a config.

- STILL OPEN, partly. **Only some layout detectors exist.**
  `configs/layout_detection.yaml` describes `stream_role`,
  `channel_block_structure`, `lead_geometry`, `ecog_strip_location` and a mains
  detector. `detect/` implements `lead_geometry` alone. The config reads as a
  description of the app and is a description of the intent.

- ~~**Windows are typed in by hand, and nothing reads markers from a file.**~~
  DONE: `detect/windows.py` and `dbsspeech windows`.
  `window_sources` in `configs/vocabularies.yaml` lists `task_marker` as a legal
  provenance, and no code path produces one: every window in the project comes
  from a person editing `manifest/windows.csv`. For a lab whose recordings carry
  real event codes this is the difference between minutes and an afternoon per
  session, and G10 will mark every one of those windows unverified until then.

What is already general, and did not need changing: the condition vocabulary,
regions, reference schemes and window provenance all live in
`configs/vocabularies.yaml` and extend by adding a line. Seven lead models across
four manufacturers live in `configs/leads.yaml`, `lead_id` is optional per
channel so an ECoG strip needs no geometry, bands and QC thresholds are config,
and no subject identifier appears anywhere in `src/` or `configs/`.

## 2026-09-09, the front end

- **There is no front-end test runner, and the interface is now the part with
  the most recent change and the least coverage.** The run flow, the QC review
  rows and the schema form are checked by TypeScript and by eye, nothing more.
  The rules worth testing are already extracted and free of React, in
  `web/src/pages/runFlow.ts`: what makes a subject selectable, what counts as a
  cleared field, and what stops a run from starting.

  Not done here because `web/node_modules` in a worktree is a symlink to the
  main checkout's, so installing would put packages in somebody else's tree, and
  a real `node_modules` inside the repository would sync thousands of files to
  cloud sync, which is the reason `.venv` is a symlink in the first place. Add
  vitest and @testing-library/react from the main checkout, where neither
  applies.

## 2026-09-08, from the reverted BrainVision work

- **Port the session-level BrainVision test.** The reverted duplicate had an
  integration test taking a recording from a manifest row through the loader and
  a montage, asserting the derivation names and that decimation still applies.
  The surviving reader is tested on its own. "Adding a format changes no other
  layer" is only worth claiming if something checks it, and nothing does yet.
  It was `tests/integration/test_brainvision_session.py` in commit 1368536.

## 2026-09-08, the interface

- **Dark mode.** The tokens are in one place specifically so this is cheap, but
  it needs a second value for every token and a check of the status colors
  against a dark ground. Nobody has asked.

- **`Compare.tsx` sets state inside an effect**, which oxlint warns about and
  which predates the design pass. It works; it will bite when the page grows.
  The fix is to derive the value during render rather than in an effect.

- **No screenshots of the design.** The guide's step asks for before and after
  images via Playwright, which needs a browser this session did not have. Worth
  doing once, if only to have something to argue about.

- **The design pass was done without reference screenshots**, on the direction
  the guide states. If the result is wrong, the cheapest correction is three
  screenshots and one more pass, not an argument about tokens.

## 2026-09-08, ERNA

- **The ERNA recipe has never seen stimulation in a real recording.** Everything
  it does is validated against a planted signal. The first real run will need
  `stim_refractory_ms` set to the burst spacing of the protocol, and will
  probably need `blanking_ms` adjusted by looking at an epoch rather than by
  reasoning. Blocked behind the first subject analyzed clearing QC.

- **Contact ranking is not reported as such.** ERNA is used clinically to pick a
  contact, and the summary has the per-derivation medians to do it, but nothing
  ranks them or says which contact wins. Deliberately left out: a ranking is a
  clinical claim, and it should be added when someone asks for it in the form
  they want to read.

- **No sanity check that stimulation was actually on.** Running the recipe over a
  recording with no stimulation gives few epochs and a note, rather than saying
  "there is no stimulation here". Worth a guardrail once there is a real
  recording to calibrate it against.

## 2026-09-08

- **The five test manifest builders should be one.** `test_psd_recipe`,
  `test_bandpower_recipe`, `test_pynm_recipe`, `test_qc_gate`, and now
  `tests/integration/test_worker` each build the same synthetic subject with a
  near-identical `project` fixture. A shared builder in `tests/fixtures/` would
  be about forty lines lighter and would stop them drifting apart. Not done
  during step 4.3, because refactoring four passing test files is not the same
  change as adding a queue.

- **Verify the container build.** `docker/` was written and never built: the
  Docker daemon was not reachable from the session that wrote it. First build on
  a real machine is the test. Watch for the `py-neuromodulation` install, which
  is the heaviest dependency and the most likely to need a build tool the slim
  image does not have.

- **A worker that dies leaves its job `running` until a worker restarts.**
  Reaping happens in the worker loop, not in `/health`, because a health check
  should report state rather than change it. With exactly one worker and no
  restart, a job can sit in `running` indefinitely. Options, if this becomes
  annoying: a `dbsspeech jobs --reap` command, or a periodic reaper. It is
  visible on the Status screen either way.

- **Uploads are not covered by the backup script.** `var/uploads` in a container
  holds recordings a user uploaded but has not yet been added to the manifest.
  They are raw data, which the backup deliberately skips, but they are also the
  only copy until someone files them. Decide which of the two they are.
Things noticed while doing something else. Not scoped, not scheduled.

## Curriculum

Findings from the review pass on 2026-09-08. The four blocking items were fixed
that day; everything below was left.

### Asserts that cannot fail

RESOLVED 2026-09-08. All five were repaired and each fix was verified by
re-injecting the original bug and confirming the test cell now fails. The
spectral scan in module 01 was refactored into `scan_power_profile(signal)` so
the check can exercise the student's own code rather than a reimplementation.
Power is now pinned by two properties rather than by the location of its peak:
quadratic scaling in amplitude, and phase invariance. Dropping either projection
of the quadrature pair now reports 1.56e+06 for a sine against 1.13e-25 for a
cosine, and fails.

### Content

- Module 01's Neuropixels demo uses a 0.4 uV noise floor against a specified
  13.4 uV RMS, so the planted spike sits below the real noise floor and the
  section's stated motivation is never stressed.
- Module 01's Kilosort description omits ZCA whitening, spatiotemporal templates
  and matching-pursuit peeling. It describes a single-channel matched filter.
- Module 02's contact labels (`2A`, `2B`, `2C`) contradict `configs/leads.yaml`,
  which gives `boston_cartesia` ids `1..8` and warns "VERIFY BEFORE USE".
  "Abbott Directed" is not a product name.
- Module 02 plants beta on exactly one contact with zero spread, so the bipolar
  derivation recovers it at full amplitude and the montage appears to cost
  nothing. Volume conduction would partially cancel it.
- Module 03 declares Tikhonov a success at 73.8 percent relative error. A sweep
  over 200 lambda values shows 73.7 percent is the ceiling, so this is the
  method's limit rather than a tuning miss. The words bias and variance never
  appear.
- Module 03 gives DBS contact spacing as 0.5 mm in cell 0 and 0.1 mm in cell 5.
  0.5 mm is right; 0.1 mm matches neither DBS segments nor Neuropixels.
- Module 01 cell 17 still writes "independent (orthogonal)" in the cell whose
  subject is that conflation. Its own output prints r = +0.0951.
- Module 01 cell 8's `theta = |theta_b - theta_a|` returns 340 degrees where the
  angle is 20. Correct for the vectors used; wrong if a student reuses it.
- The 1/f model is presented as what LFP is, not as a simplification. The
  aperiodic exponent is fitted and state-dependent.

### Consistency and hygiene

- Module 02 uses `np.linspace(0, 0.5, 500)` with default `endpoint=True`, giving
  998 Hz where 1000 is declared. Module 01 correctly uses `endpoint=False`.
- Module 03's student notebook pre-answers Task 3 and its solutions add a
  `max(r, 1e-6)` guard the student instructions never mention.
- Modules 01 and 02 have no `kernelspec`, so Jupyter prompts for a kernel.
- Em dashes in modules 01 and 02, against the style rule.
- Module 02 hand-rolls what `mne.set_bipolar_reference` and
  `mne.set_eeg_reference` do, without naming either.

## Curriculum, remaining

- Module 02's simulation still plants beta on one contact with zero spread, so a
  bipolar montage appears to cost nothing. Now contradicted by the tradeoff text
  added to cell 2, which is an improvement but not a fix.
- Module S2 leaves second-order sections named but not built. `apply_iir` is
  direct form, which is why its agreement with scipy is 1e-7 rather than machine
  precision. A `sosfilt` task would close that, and would belong in S2 or in the
  preprocessing capstone.

## Curriculum, remaining after completion

- RESOLVED. The generators now live in `curriculum/tools/`, are path-independent,
  and a test asserts every generated module still has one.
- **G7 and G9 are owed a module.** Both are real thresholds that no module in the
  curriculum derives: muscle contamination over 100 to 1000 Hz, and baseline
  excursion against effect size. G3 now names the gap rather than papering over it.
- `web/public/notebooks/` is still a hand-maintained mirror of `curriculum/`. A
  test enforces it; a six-line copy step in the build would remove the class of
  problem entirely.
- L1 and L2 withhold answers with `= ...` placeholders rather than the
  `raise NotImplementedError` the README documents, so a student who runs an
  unfilled cell gets "float() argument must be ... not 'ellipsis'" instead of a
  clear instruction. The test accepts both; the student experience differs.
- Contrast was fixed by class substitution, not measured in a browser. The ratios
  quoted come from the reviewer's computation against the shipped CSS.
- Modules L1 to L3 were written before the generator pattern and are still
  hand-maintained. They are the only ones that can drift.
- Six modules have bespoke interactive pages; twenty-five use the generic
  notebook-module page. Some of those twenty-five would teach better with a
  widget, particularly C1 (the zero-lag trap), S5 (the time-frequency trade) and
  G2 (the control loop).

## Tooling

- RESOLVED 2026-09-08. `jupyterlab` and `ipykernel` added to both dev lists in
  `pyproject.toml`. All twelve notebooks now validate against `nbformat` and all
  six solutions notebooks execute through a real kernel via `nbclient`.
  Modules 01 and 02 gained the `kernelspec` they were missing, module 03 moved
  from `nbformat_minor` 4 to 5, and every cell now carries an `id`, which
  `nbformat` warns will become a hard error.
- `web/public/notebooks/` is a hand-maintained flat copy of `curriculum/`. A test
  enforces the copy; a six-line build step would remove the class of problem.
- Nothing in the suite covers the TSX widgets or the notebook download links.
- `configs/guardrails.yaml` sets `G9_nonstationarity_exceeds_effect` to
  `excursion_to_effect_ratio: 1.0`, but N4 measured the blocked-comparison
  estimate collapsing near ratio 0.73, with 99 percent of baseline choices still
  usable at 0.5 and 1 percent at 1.0. The threshold is permissive: it fires after
  the analysis it warns about has already failed. Lowering it is a scientific
  decision for Garrett, and the evidence is one simulated drift shape, so the
  check that should decide it is a random-walk drift with no characteristic
  timescale. See docs/findings.md, 2026-09-09.
- `tests/unit/test_cli.py` asserts against live project state and mutates it.
  `test_qc_status_reports_the_gate_state` expects `the first subject analyzed` to read `in_review`,
  while `test_qc_sign_refuses_while_flags_are_undecided` signs the subject, so
  the trio passes on a fresh checkout and fails on every run afterwards. They
  broke for real on 2026-09-09 when the subject was signed through the app at
  08:17, which is a legitimate review action, not a test problem. These should
  build their own QC tree under `tmp_path` rather than reading `derivatives/`.
  Not fixed here because the fix changes what the tests assert about a real
  signature, which is a judgement call about the gate rather than about tests.

## Curriculum gaps against a neuroengineering PhD

Audited 2026-09-09 against the graduate catalog. The degree is 72 hours from a
BS, 51 from an MS. Its core is IDNE 701/702, GRD 717 Principles of Scientific
Integrity, BST 622 Statistical Methods II, and EE 638/738 Neural Time Series Data
Analysis, plus a 3-hour math requirement, 9 hours of engineering electives and 9
hours of neuroscience electives.

Our ten courses are, in effect, one and a half of those: EE 638/738, plus the
part of BST 622 this app actually leans on. Linear Algebra spills into the math
requirement, and Guardrails does what GRD 717 does, quantitatively. What is
missing, in order of how much it costs this app:

- ~~**Statistical inference.**~~ **Closed 2026-09-09** by the Inference course
  (INF 1 to INF 3). `configs/statistics.yaml` is now derived rather than
  asserted, including three of its caveats proved as arithmetic, and the shuffled
  nulls CON 3, CON 4, SPK 4 and GRL 5 lean on are established in INF 1. What INF
  does not cover from BST 622: regression and the general linear model, ANOVA
  with more than two conditions, and mixed-effects models for repeated measures
  across subjects. Those matter for a group-level analysis this app does not yet
  do, so they are a smaller gap than the one just closed.
- ~~**Machine learning and neural decoding.**~~ **Closed 2026-09-09** by the
  Decoding course (DEC 1 to DEC 5), placed in a new Electives group because in
  the real degree this material is elective while BST 622 is core. Ridge from
  scratch against sklearn, cross-validation on autocorrelated data, backprop with
  finite-difference gradient checks, nonlinear against linear at realistic trial
  counts, and the activation-pattern transform. What DEC does not cover from the
  four courses it stands in for: convolutional and recurrent architectures,
  anything about training at a scale where optimisation itself is the problem,
  and closed-loop BMI, which is EE 767's subject and overlaps GRL 2.
- **Neuroanatomy and neurophysiology.** GBSC 744 Neuroanatomy, NBL 700 Cellular
  and Molecular Neurobiology. We have REC 1's extracellular biophysics and
  nothing else: no basal ganglia circuitry, no pathophysiology of the disorders
  that motivate the surgery. **Deliberately not filled**, and now said so in
  `curriculum/README.md` under "What this curriculum does not teach": it cannot
  be measured against a simulated ground truth, and a lesson whose claims cannot
  be checked by running it would be the only one in the program.
- **Neuroimaging.** NBL 743 Methods in Neuroimaging, VIS 757 Functional MRI, EE
  726 Digital Image Processing. We teach lead geometry but nothing about how you
  know where the lead actually is: localization, atlas registration, tractography.
- ~~**Random variables and stochastic processes.**~~ **Closed 2026-09-09** by the
  Probability course (STO 1 to STO 4), placed first in Foundations because three
  earlier courses were assuming it. It derives SIG 4's chi-squared claim, INF 1's
  effective sample size including the finite-n correction INF 1 left unexplained,
  and SPK 4's phase-locking null. It also produced two findings about shipped
  code, below and in `docs/findings.md`.
- **Neuroethics.** PHL 402. Our Scientific Integrity course covers research
  integrity, which is a different thing from agency, identity and consent under
  chronic stimulation. Relevant to a speech app specifically. **Deliberately not
  filled**, for the same reason as neuroanatomy.

- ~~**Lead localization.**~~ **Closed 2026-09-09** by REC 5, which measures what
  a contact label can and cannot support. It does not close neuroimaging: this
  app performs no registration, so REC 5 ends in a wording rule rather than a
  guardrail, and the margin such a rule would fire on exists in no run record.
  Atlas registration, tractography and image processing remain open, and they are
  the part that needs a new capability rather than a new lesson.

- **`configs/leads.yaml` records contact spacing only inside a model name
  string**, as `3389 (1.5 mm spacing)`. REC 5 had to sweep the pitch over a
  plausible range rather than read it. With a numeric field, REC 5's Sections 2
  and 4 could be computed for a real run instead of swept. Small, and it is what
  stands between that arithmetic and anything the app could evaluate.

## WITHDRAWN 2026-09-09: the dB-averaging proposal

STO 1 originally proposed a guardrail flagging conditions being contrasted with
unequal segment counts, on the grounds that averaging in dB biases by an amount
that depends on the segment count. A review the same day showed the reasoning
applied to the opposite ordering to the one `recipes/psd.py` uses. The real bias
is a constant 2.51 dB, it cancels in every contrast regardless of segment counts,
and the guardrail would have flagged a problem that does not exist. Corrected
measurement in `docs/findings.md`.

What survives is much smaller and needs no guardrail: `normalize.py`'s centre of
`none` divides a dB value by a scale rather than differencing it, so the constant
offset reaches z there.

**Decided 2026-09-09: documented, no code change.** `configs/statistics.yaml`'s
caveat for that centre now states the offset and that it is the only centre where
it survives. Subtracting it was rejected because the constant is method
dependent, measured at 2.51 dB on the Welch path and 0.31 dB on multitaper, which
averages over DPSS tapers before the dB conversion. `normalize.py` does not know
which method produced the column, and on multitaper the value would also depend
on the taper count. A subtraction that guessed wrong would be worse than the
offset, which at least cancels everywhere except this one option.

## DONE 2026-09-09: G9 now reports the duration its ratio was measured over

**Decided and implemented.** `CheckContext` gained `recording_duration_s`, G9's
message ends with "over N s of recording" when it is supplied, the detail dict
carries it, and the remedy says to compare the ratio only against runs of similar
duration. The 1.0 threshold is unchanged, so no run's verdict moves and nothing
already reviewed changes. Two tests cover it, including the case where the
duration is absent, since nothing upstream is required to supply it yet.

Still to do: whichever recipe computes `max_excursion_db` should populate
`recording_duration_s` alongside it. Until it does, the field is None and the
message reads exactly as it did before.

Raised by STO 3, answering GRL 4's own Exercise 1.

G9 fires when a baseline excursion exceeds the effect at a ratio of 1.0. GRL 4
derived that threshold with drift modelled as a slow sinusoid, whose excursion is
a fixed property of the recording. STO 3 measured what happens under a random
walk, which is the other end of the range CON 4's aperiodic spectrum sits in: the
excursion grows as 1.6*sqrt(t), by a factor of 42 over a thousandfold increase in
recording length, with nothing physiological different.

So the same process passes G9 in a short recording and fails it in a long one,
and the ratio as reported does not say how long the recording was.

**Options.** Report the recording length beside the ratio, so two runs can be
compared at all. Or normalise the excursion by sqrt(duration) before thresholding,
which assumes the random-walk end of the range and would need its own derivation.
Or leave the rule as a within-run flag and say in `docs/guardrails.md` that the
ratio is not comparable between runs.

**Recommendation:** the first. It is a reporting change rather than a threshold
change, and STO 3's Exercise 1 asks whether `dbsspeech.registry` already stores
the duration.

**Not adopted.** `configs/guardrails.yaml` is unchanged.

## psd.py's _summary hard-codes the beta band as 13 to 35 Hz

Noticed 2026-09-09 while making G9 live. `configs/bands.yaml` defines beta as
13 to 30, and `_summary` filters `freq_hz >= 13 & <= 35` inline for its peak
table. The project rule is that bands live in configs and are never hard-coded.

Not changed, because the peak frequency and dB in every existing summary would
move, and that is a reported number. It needs a deliberate decision about whether
to reissue affected summaries, not a quiet edit. The new `guardrail_band`
parameter added in the same change reads the config properly, so the two now
disagree inside one file, which is the argument for fixing it.

## Proposed guardrail G14: cross-validation folds must respect time

**Decided 2026-09-09: stays here, not shipped.** No recipe in the package does
cross-validation or decoding (`grep` for `KFold`, `cross_val`, `Ridge`, `decoder`
across `src/dbsspeech/` returns nothing), so the rule would have nothing to fire
on. It gets written alongside the first decoding recipe, when there is something
to check and a real run record to add the fold-scheme field to. Shipping it now
would put a rule in `configs/guardrails.yaml` that cannot fire, which is what
makes GRL 5's index worth reading.

Raised by DEC 2, which measured the case and deliberately did not adopt it.

**The rule.** Warn when a reported decoding accuracy comes from folds drawn at
random over an autocorrelated recording. Require either contiguous folds or a
stated embargo, and record which in the run record.

**The evidence**, all from `curriculum/09_decoding/02_cross_validation_on_autocorrelated_data`:

- On a recording where the target is generated independently of every channel, so
  the honest answer is exactly zero, random five-fold reported r = 0.59 for ridge
  and r = 0.94 for a nearest-neighbour model at an epoch-to-epoch autocorrelation
  of 0.95. The same recording under contiguous folds reported under 0.10, and a
  fresh session confirmed under 0.07.
- The inflation is caused by the autocorrelation and not by the model: at rho = 0
  every scheme reported nothing, and the inflation grew monotonically with rho.
- With a real relationship present, random folds overstated the truth by 2.9x
  while contiguous folds landed within 0.06 of it. The leaky estimate also
  carried the *tighter* spread across sessions, 0.089 against 0.278, so it looks
  more reliable as well as being wrong.
- What the leak damages is the reported number rather than the model: the penalty
  chosen under leaky cross-validation achieved 0.210 against an oracle of 0.249,
  and reported 0.702.

**What it would cost.** The check is cheap, because whether folds were contiguous
is known at the point they are made. It needs one field in the run record that
does not exist today, naming the fold scheme and the embargo. DEC 2's Exercise 3
sets that out as a student exercise, and the open question there is whether the
field belongs to `registry.run` or to the recipe.

**Not adopted.** `configs/guardrails.yaml` still ships thirteen rules.

Not applicable to a self-paced curriculum: IDNE 773 Lab Rotation, IDNE 798/799
research hours, IDNE 796 Journal Club, GBS 725 Grant Writing, EE 610 Technical
Communication.

## 2026-09-09 Derivative store follow-ups (from the module build reviews)

- **A `blank` role for unconnected amplifier inputs.** Bush et al. 2022's strongest
  artifact control was a headstage pin connected to nothing. This archive has that
  for free: 8 to 16 unconnected inputs per TDT block (railed at 536.87 kOhm in the
  impedance sheets, and stored anyway inside `ecos`), and the `ao_1..ao_3` Alpha
  Omega inputs in the ug BrainVision headers, labeled `notConnected` in the
  sidecars. `configs/derive.yaml` currently ignores `^ao_\d+$`. Add a `blank` role
  and product so they are kept and labeled as controls rather than dropped.
- **A canonical archive-root setting.** `tests/realdata/test_derive_roles_archive.py`
  finds the staging archive at `~/DBS Data` with a `DBSSPEECH_ARCHIVE` override,
  and the redact archive-literal guard uses `DBS_STAGING_ROOT`. Nothing in the
  package names the archive. One setting, one name.
- **A realdata summarize test** against the one staged BrainVision waveform
  (`ug0002/stage2 surgery/erp001.eeg`), where channel DBS4 is railed for 100% of
  samples; a good fixture for the rail counters and the two PC1 statistics.
- **Signal-level liveness.** The impedance rail test decides contact liveness for
  TDT only; BrainVision has no sheets. A rail-fraction plus variance test per
  channel, computed by `summarize`, should feed the same `live` verdict.
- **`SummaryConfig.per_channel_stats` is not used to filter output** (every
  statistic is computed in one pass). Either make the list authoritative at the
  write step or remove it from the config.
- **`Ledger` policy knobs** (`max_attempts`, `stale_timeout_s`) now live in
  `configs/derive.yaml:build`; the driver must pass them through.
- **Ledger reconcile re-hashes every done file on every restart.** Correct but
  slow: at 60 GB it is several minutes, at the full store closer to twenty. A
  size-and-mtime check first, hashing only on mismatch or on demand, keeps the
  guarantee for a fraction of the cost. Seen 2026-09-09 restarting after a
  memory kill.
- **Heartbeat and pulse-comb removal from EMG before any envelope
  periodicity test.** The ECG rides on every EMG channel; the first subject's terminal
  block carries a 0.5 Hz-spaced comb on all four. R-peak detection on the
  channel with the strongest comb, an averaged template, subtraction at
  every beat; validate on the envelope spectrum. Until then EMG tremor is
  reported and not trusted (`_tools/state_labels.py`, 2026-09-09).
- **EMG muscle names per case** (`emgg` 1 to 4). A named orbicularis oris or
  laryngeal channel is a speech-articulation channel, not a tremor channel,
  and the labeler could use it as such. Needs the OR record or the lab.
- **Video motion energy from decoded frames still carries the encoder's
  keyframe comb.** Removed at the frame level in the labeler; the cleaner
  place is `_tools/video_motion.py` at decode time (skip or interpolate the
  I-frame transitions), which would clean the series for every consumer at
  the cost of re-decoding 77 blocks.
