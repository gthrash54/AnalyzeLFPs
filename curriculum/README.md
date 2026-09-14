# Program of Study

Forty-six lessons on the probability, mathematics, signal processing, statistics
and machine learning behind this analysis app, written at neuroengineering PhD
level and organised as eleven courses in five groups.

Each lesson is a pair of notebooks. The **student workbook** leaves the core
functions unimplemented behind `TODO` comments and `NotImplementedError`; the
**solutions guide** fills them in. Both carry the same test cells, and every
solutions notebook is executed in CI by `tests/unit/test_curriculum.py`, so every
number quoted below is verified on every commit.

The same files are mirrored into `web/public/notebooks/` and surfaced by the
Learn section of the app, which adds an interactive page for some lessons. The
mirror is checked byte for byte by the test suite.

## Courses

Lessons are cited by a course tag and a number: **SIG 4** is the fourth lesson of
Signal Processing. Those citations are load-bearing rather than decorative, and
`test_every_lesson_citation_points_at_a_lesson_that_exists` fails the suite if
one of them points at a lesson that does not exist.

| Group | Course | Tag | Lessons |
|---|---|---|---|
| Foundations | Probability and Stochastic Processes for Neural Data | STO | 4 |
| Foundations | Applied Linear Algebra for Neural Arrays | LIN | 6 |
| Foundations | Signal Processing for Neural Time Series | SIG | 6 |
| Acquisition | Recording Physics and Electrode Geometry | REC | 5 |
| Acquisition | The Preprocessing Contract | PRE | 1 |
| Analysis | Spike Trains and Single-Unit Activity | SPK | 4 |
| Analysis | Population Dynamics and Latent Structure | POP | 3 |
| Analysis | Connectivity and Spectral Coupling | CON | 4 |
| Scientific Integrity | Closed-Loop Neuromodulation and Scientific Guardrails | GRL | 5 |
| Scientific Integrity | Statistical Inference for Neural Recordings | INF | 3 |
| Electives | Machine Learning and Neural Decoding | DEC | 5 |

The **Electives** group is marked as such deliberately. In the degree this
curriculum was audited against, statistical inference is core and machine
learning is not, and that ordering is right for this app too: nothing in the
package currently depends on DEC, while every recipe depends on INF. Decoding is
here because it is the obvious next thing somebody will try, and because trying
it without INF 1's null and DEC 2's fold rule produces numbers that are not
true.

What remains missing is recorded in `docs/backlog.md`: neuroanatomy and
pathophysiology, neuroimaging and lead localization, random variables and
stochastic processes, and neuroethics.

## Running them

The notebooks need `jupyterlab` and `ipykernel`, which are in the dev extra:

```
uv sync --extra dev
uv run jupyter lab curriculum/
```

Everything is synthetic and seeded. No lesson reads `data/`, and none needs the
lab's recordings.

### Without installing the app

The lessons stand alone. They do not import `dbsspeech`, and you do not need
FastAPI, MNE, the docker tooling or the guardrail stack to work through them:

```
python -m venv .venv && . .venv/bin/activate
pip install -r curriculum/requirements.txt
jupyter lab curriculum/
```

That is numpy, scipy, matplotlib, scikit-learn and fooof. Verified on
2026-09-13 by building a virtual environment containing nothing else,
confirming `import dbsspeech` fails inside it, and executing one solutions
notebook from each of the eleven courses.

Six notebooks mention the package in comments of the form
`Production equivalent: dbsspeech.preprocess.resample.suggest_factor`. Those
point at the code the lesson is teaching the mathematics behind. They are
cross-references, not imports, and nothing breaks without the package present.




```
Probability ─→ Linear Algebra ─┐
                ├─→ PRE 1 ─→ Recording Physics ─→ Spike Trains ─┐
Signal Proc.  ─┘                                                 ├─→ Guardrails
                     Population Dynamics ────────────────────────┤
                     Connectivity ─────────────────────────────── ┘

Guardrails ─→ Inference ─→ Decoding
```

There is no refresher anywhere. A lesson may use only what an earlier lesson
actually built, which is why the prerequisite tables at the top of each notebook
name specific lessons rather than topics.

## Foundations: Probability and Stochastic Processes for Neural Data (STO)

`curriculum/10_stochastic/`

| | Module | What it establishes |
|---|---|---|
| STO 1 | An estimator is a random variable | A periodogram reads below half the truth 39% of the time however long the record; `recipes/psd.py` averages in dB, which offsets every value by -2.51 dB and cancels in every contrast |
| STO 2 | Autocorrelation and effective sample size | For 1/f noise n_eff grows as 0.233 ln(n), so a thousandfold more data cuts the error bar by 1.6x rather than 32x |
| STO 3 | Random walks and spurious correlation | Two independent walks correlate at 0.42 and the standard test calls it significant 93% of the time, worsening with more data |
| STO 4 | Events rather than samples | The phase-locking null is sqrt(pi)/2/sqrt(N), so a condition with 10 spikes reports 0.06 more locking than one with 100 |

## Foundations: Applied Linear Algebra for Neural Arrays (LIN)

`curriculum/01_linear_algebra/`

| | Module | What it establishes |
|---|---|---|
| LIN 1 | Vectors, neural state space, and the dot product duality | A dot product is a projection, and cosine similarity is amplitude-blind |
| LIN 2 | Matrices as spatial operators | A montage is a matrix whose rows sum to zero; CAR is rank-deficient |
| LIN 3 | Matrix inverses, conditioning, multicollinearity | Contacts 0.1 mm apart give κ = 2436; a singular matrix inverts without complaint |
| LIN 4 | Covariance matrices and volume conduction | Sources uncorrelated at 0.001 give contacts correlated at 0.42; this is guardrail G1 |
| LIN 5 | Eigendecomposition and PCA | PCA recovers the subspace to 0.01° and never the sources |
| LIN 6 | Generalised eigendecomposition | With a reference 6× the physiology, PCA returns the amplifier and GED the source |

## Foundations: Signal Processing for Neural Time Series (SIG)

`curriculum/02_dsp/`

| | Module | What it establishes |
|---|---|---|
| SIG 1 | Sampling, Nyquist, aliasing | Aliasing is a relabelling, not noise; usable bandwidth is 0.4 fs |
| SIG 2 | Filtering and zero-phase distortion | A causal beta filter reports onset 63 ms late; zero-phase can report it 191 ms early |
| SIG 3 | The Fourier transform from the ground up | Resolution is 1/T; zero-padding 32× resolves nothing extra |
| SIG 4 | Welch and multitaper | The periodogram never converges; multitaper wins by 9%, not a landslide |
| SIG 5 | Complex Morlet wavelets | σt·σf = 1/2π exactly; a 12-cycle wavelet reports a 100 ms burst as 166 ms |
| SIG 6 | The Hilbert transform | Instantaneous frequency is negative 31.9% of the time on broadband LFP |

## Acquisition: The Preprocessing Contract (PRE)

`curriculum/03_preprocessing/`

| | Module | What it establishes |
|---|---|---|
| PRE 1 | The preprocessing contract | Re-referencing and decimation commute to 3.7e-12; artifact detection does not |

## Acquisition: Recording Physics and Electrode Geometry (REC)

`curriculum/03_spatial/`

| | Module | What it establishes |
|---|---|---|
| REC 1 | Extracellular biophysics | Spike reach 224 µm against LFP reach 4.6 mm; this makes guardrail G2 decidable |
| REC 2 | Directional DBS leads | One fixed source is reported on segment b, a, or c depending on lead rotation |
| REC 3 | ECoG grids, strips, sEEG | A 7.1 mm cortical pattern aliases to 25 mm on a clinical grid |
| REC 4 | Neuropixels and drift | One site pitch of drift takes profile correlation from 1.000 to 0.596 |
| REC 5 | What a contact label means | The best row is the true best row 67% of the time at 4 segments, and an anatomical label is wrong with probability Phi(-margin/sigma) |

## Analysis: Spike Trains and Single-Unit Activity (SPK)

`curriculum/04_spikes/`

| | Module | What it establishes |
|---|---|---|
| SPK 1 | Splitting LFP from spikes | Spike bleed into high gamma is 0.08%, and the famous claim does not survive measurement |
| SPK 2 | Robust spike detection | A non-robust threshold costs 36.6% recall in the busier condition |
| SPK 3 | Sorting and quality metrics | Complementary-tuning contamination reads under half the truth |
| SPK 4 | PSTH and spike-field coherence | Phase locking under the null is √π/2√N, so raw PLV compares spike counts |

## Analysis: Population Dynamics and Latent Structure (POP)

`curriculum/05_dynamics/`

| | Module | What it establishes |
|---|---|---|
| POP 1 | State space and manifolds | Smoothing alone moved reported dimensionality from 37.4 to 7.1 |
| POP 2 | Latent factors and demixing | Factor analysis fails exactly as PCA does unless given a spare factor |
| POP 3 | Kalman online decoding | The gain is set by two covariances nobody measures, and the filter cannot detect its own misspecification |

## Analysis: Connectivity and Spectral Coupling (CON)

`curriculum/06_connectivity/`

| | Module | What it establishes |
|---|---|---|
| CON 1 | Phase-locking value | Volume conduction gives PLV 1.0000 with no interaction |
| CON 2 | wPLI and directionality | Spurious Granger is largest when two regions are equidistant from a hidden driver |
| CON 3 | Phase-amplitude coupling | A sharp waveform manufactures coupling that a shuffled null certifies at z = +18 |
| CON 4 | Aperiodic against periodic | A slope rotation and a real oscillation both raise beta, by 1.42× and 1.46× |

## Scientific Integrity: Closed-Loop Neuromodulation and Guardrails (GRL)

`curriculum/07_guardrails/`

| | Module | What it establishes |
|---|---|---|
| GRL 1 | Stimulation artifact and blanking | The guard band, not the pulse, raises high-gamma power sevenfold |
| GRL 2 | Adaptive DBS control loops | True beta falls while the number the device logs rises |
| GRL 3 | EMG contamination in the speech band | Gated muscle with no cortex present produces a 1.65× speech-locked high-gamma rise |
| GRL 4 | Non-stationarity larger than the effect | At an excursion 3.3× the effect, every baseline window reports the wrong sign |
| GRL 5 | The thirteen guardrails | Eleven of thirteen thresholds are now derived by a lesson here, and five can be screened from a plan before any data is touched |

## Scientific Integrity: Statistical Inference for Neural Recordings (INF)

`curriculum/08_inference/`

| | Module | What it establishes |
|---|---|---|
| INF 1 | The shuffled null | Shuffling samples instead of trials rejects a true null 61% of the time; the rule is to permute the way you randomized |
| INF 2 | Multiple comparisons and cluster tests | A 200-point smoothed map asks about 26 independent questions, and a significant cluster has no edges |
| INF 3 | What a z score means | `whole_recording` shrinks every effect by exactly 1-f, and at two conditions `across_conditions` makes every z exactly 0.7071 |

## Electives: Machine Learning and Neural Decoding (DEC)

`curriculum/09_decoding/`

| | Module | What it establishes |
|---|---|---|
| DEC 1 | Least squares and ridge from scratch | Duplicating one contact raises its apparent importance 2.8x while the decoder's predictions do not move |
| DEC 2 | Cross-validation on autocorrelated data | With no relationship at all, random five-fold reports r = 0.94; the same recording under contiguous folds reports nothing |
| DEC 3 | Backpropagation from scratch | A gradient checks against arithmetic to 1e-9, and a wrong one still trains and still looks converged |
| DEC 4 | Nonlinear against linear | The crossover is between 160 and 320 trials, and at 40 trials it would take 218 sessions to establish which model is better |
| DEC 5 | Weights are not an encoding map | With a nuisance present, weight magnitude ranks contacts at 0.31 against the truth, and one matrix multiply restores 0.90 |


#

## Contributing a lesson

The generator pattern matters more than the notebook. Write one Python source
declaring the cell list, with each task cell carrying both a `TODO` body and a
reference body, and emit both variants from it. Hand-maintaining two notebooks
lets them drift, which is how LIN 3 lost its variant tag.

Two rules that are not negotiable:

- **Verify before you write.** Several planned lessons in this curriculum turned
  out to be false when measured, including "re-reference before decimating" and
  "spike bleed contaminates high gamma". Run the experiment first and write what
  it says.
- **Bite-test every assertion.** Inject the bug the test is supposed to catch and
  confirm it fails. Earlier rounds found test cells that green-lit broken
  implementations, including one where a cosine similarity with no normalisation
  passed.
