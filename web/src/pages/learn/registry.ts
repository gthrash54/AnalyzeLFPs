import type { NotebookModuleProps } from "./NotebookModule";

/**
 * Modules whose teaching happens in the notebook rather than in a bespoke widget.
 * Every number under `results` is produced by a CI-verified test cell.
 */
export const NOTEBOOK_MODULES: Record<string, NotebookModuleProps> = {
  "STO 1": {
    course: "Foundations · Probability and Stochastic Processes for Neural Data",
    title: "An Estimator Is a Random Variable",
    summary:
      "The first lesson of the program, written last. Every number computed from a recording is a draw from a distribution, and the shape of it decides what the number may mean.",
    stem: "01_estimators_are_random_variables",
    builds: [
      ["Nothing", "This is the first lesson of the curriculum."],
    ],
    underwrites: [
      "SIG 4's chi-squared claim and the whole case for Welch's method.",
      "The db and db_sd columns produced by dbsspeech.recipes.psd, and a finding about how they are computed.",
    ],
    results: [
      { claim: "Bias of the sample variance dividing by n", value: "exactly 1 - 1/n, so 25 percent low at n=4" },
      { claim: "Distribution of a periodogram at one bin", value: "exponential, KS 0.004 against it" },
      { claim: "Its standard deviation relative to its mean", value: "1.00, at every record length" },
      { claim: "Fraction of records reading below half the truth", value: "39 percent" },
      { claim: "Fraction reading above twice the truth", value: "14 percent" },
      { claim: "Effect of a 64-fold longer record on that", value: "none" },
      { claim: "Relative error after averaging k segments", value: "1/sqrt(k), to three decimals at every k" },
      { claim: "Averaging power then converting: bias at k=1 and k=64", value: "-2.51 dB falling to -0.03" },
      { claim: "Converting then averaging, which is what psd.py does", value: "-2.51 dB at every k" },
      { claim: "So the contrast residue, 40 segments against 4", value: "under 0.01 dB, it cancels" },
      { claim: "What the other ordering would have left there", value: "0.51 dB, so the cruder one is safer" },
      { claim: "Where the constant survives", value: "normalize.py's centre of none, which is not a contrast" },
    ],
  },
  "STO 2": {
    course: "Foundations · Probability and Stochastic Processes for Neural Data",
    title: "Autocorrelation and the Effective Sample Size",
    summary:
      "INF 1 used a formula for how many independent samples a correlated recording is worth. Here is where it comes from, and the case where it is badly wrong.",
    stem: "02_autocorrelation_and_effective_sample_size",
    builds: [
      ["STO 1", "That an estimator has a distribution, and that its variance can be computed."],
    ],
    underwrites: [
      "INF 1's effective sample size and its blocked-shuffle argument.",
      "GRL 4's result that drift does not shrink with more data, and DEC 2's fold rule.",
    ],
    results: [
      { claim: "Autocorrelation of an AR(1) at lag k", value: "exactly rho^k" },
      { claim: "Lag at which correlation falls below 0.1, rho=0.99", value: "over 200 samples" },
      { claim: "Variance inflation of the mean, exact form", value: "predicts the measurement at every rho" },
      { claim: "INF 1 measured a null-width ratio of", value: "4.2" },
      { claim: "What the asymptotic formula predicts", value: "4.36" },
      { claim: "What the exact finite-n formula predicts", value: "4.15, off by 1.3 percent" },
      { claim: "AR(1) n_eff/n as the record grows", value: "settles at 0.055, the predicted 0.053" },
      { claim: "1/f noise n_eff as the record grows", value: "0.233 * ln(n), not a fraction of n" },
      { claim: "Error bar gain from 1000x more 1/f data", value: "1.6x, where independence gives 32x" },
      { claim: "Gain by spectral slope: white, 1/f, random walk", value: "14.7x, 1.6x, 1.0x" },
    ],
  },
  "STO 3": {
    course: "Foundations · Probability and Stochastic Processes for Neural Data",
    title: "Random Walks, and Correlations That Are Not There",
    summary:
      "The limiting case, where the effective sample size stops growing entirely. Two independent series that a standard test calls correlated nine times out of ten.",
    stem: "03_random_walks_and_spurious_correlation",
    builds: [
      ["STO 1", "That an estimator has a distribution."],
      ["STO 2", "Effective sample size, and that a steep spectrum destroys the benefit of more data."],
    ],
    underwrites: [
      "A qualification to guardrail G9's excursion-to-effect ratio.",
      "The reason CON 1 and CON 2's connectivity results need stationary inputs.",
    ],
    results: [
      { claim: "Variance of a random walk at time t", value: "exactly t, without bound" },
      { claim: "Its excursion over t steps", value: "1.6 * sqrt(t), so 42x over a 1000x span" },
      { claim: "A stationary process's excursion over the same span", value: "4.7x, growing only with log t" },
      { claim: "Consequence for G9 at a fixed effect", value: "quiet at 10 samples, fires at 100" },
      { claim: "Two INDEPENDENT random walks, mean |r|", value: "0.42" },
      { claim: "How often the standard test calls that significant", value: "66 percent at n=50" },
      { claim: "The same at n=1000", value: "93 percent, and rising with n" },
      { claim: "AR(1) rho=0.9, same null", value: "about 53 percent" },
      { claim: "White noise, same null", value: "5 percent, as it should be" },
      { claim: "Linear detrending as a fix, at n=2000", value: "still 92 percent" },
      { claim: "First differencing as a fix", value: "5 percent at every n" },
      { claim: "What differencing costs when the signal is in the levels", value: "|r| 0.93 becomes 0.11" },
    ],
  },
  "STO 4": {
    course: "Foundations · Probability and Stochastic Processes for Neural Data · final lesson",
    title: "Events Rather Than Samples",
    summary:
      "A spike train is a list of times, not a time series. SPK 4's phase-locking null comes out of this, and it says something more damaging than SPK 4 draws from it.",
    stem: "04_point_processes_and_phase_locking",
    builds: [
      ["STO 1", "That an estimator has a distribution, and how to check one against a named distribution."],
      ["STO 3", "That a sum of random steps lands sqrt(N) from the origin, not at it."],
    ],
    underwrites: [
      "SPK 4's phase-locking null and its warning that raw PLV compares spike counts.",
      "SPK 3's contamination check, which rests on a unit not violating its own refractory period.",
    ],
    results: [
      { claim: "Fano factor of a Poisson count", value: "1.00" },
      { claim: "Coefficient of variation of its intervals", value: "1.00, the same statement" },
      { claim: "A 10 ms refractory period: CV and Fano", value: "0.832 and 0.671, so sub-Poisson" },
      { claim: "Phase-locking value under no locking", value: "sqrt(pi)/2/sqrt(N), verified at five counts" },
      { claim: "Where that comes from", value: "a 2D random walk of N unit steps" },
      { claim: "Distribution of the resultant length", value: "Rayleigh, KS 0.007" },
      { claim: "Same true locking, 10 spikes against 100", value: "PLV differs by 0.062" },
      { claim: "Direction of that artifact", value: "a quieter condition reports MORE locking" },
      { claim: "Pairwise phase consistency over the same range", value: "flat to within 0.005" },
      { claim: "What PPC estimates", value: "the SQUARE of the locking, not the same scale" },
    ],
  },
  "LIN 4": {
    course: "Foundations · Applied Linear Algebra for Neural Arrays",
    title: "Covariance Matrices and Volume Conduction",
    summary:
      "LIN 1 claimed that an effect on every contact at once is usually the reference moving rather than the brain. This is where that becomes arithmetic.",
    stem: "04_covariance_volume_conduction",
    builds: [
      ["LIN 2", "A montage is a matrix, and M applied to channels gives derivations."],
      ["LIN 3", "Condition number from singular values, and that a singular matrix does not announce itself."],
    ],
    underwrites: [
      "Guardrail G1, monopolar common mode. The module computes the fraction of a covariance matrix a shared reference is responsible for, which is the quantity G1 thresholds on.",
      "Every recipe that estimates a covariance per condition from a short intraoperative recording.",
    ],
    results: [
      { claim: "Bias from dividing by T instead of T−1, measured over 4000 trials", value: "18.9% low" },
      { claim: "Correlation between three provably uncorrelated sources", value: "0.001" },
      { claim: "Median correlation between contacts recording them", value: "0.42" },
      { claim: "Correlation between the closest pair of contacts", value: "0.97" },
      { claim: "Mean |r| across contacts as reference SD goes 0 → 10", value: "0.47 → 0.99" },
      { claim: "Spread of |r| over the same range, the G1 fingerprint", value: "0.31 → 0.007" },
      { claim: "Common mode left after a zero-sum montage, at every reference level", value: "18.3%" },
      { claim: "Condition number of a 32-channel covariance from 16 samples", value: "2.3e18" },
      { claim: "Does np.linalg.inv raise on it?", value: "no" },
      { claim: "Condition number after 1% shrinkage, and error vs truth", value: "1.27e3, 83% to 56%" },
    ],
  },
  "LIN 5": {
    course: "Foundations · Applied Linear Algebra for Neural Arrays",
    title: "Eigendecomposition and Principal Component Analysis",
    summary:
      "What the eigenvectors of a covariance matrix are, and then the question everyone actually wants answered: whether they are the sources. They are not, and the reason is worth more than the technique.",
    stem: "05_eigendecomposition_pca",
    builds: [
      ["LIN 4", "The sample covariance, the mixing model, and shrinkage."],
      ["LIN 3", "Condition number, and that a rank-deficient matrix inverts silently."],
    ],
    underwrites: [
      "Any dimensionality claim made about an electrode array, and the reading of a scree plot as a source count.",
      "LIN 6, which needs the eigenbasis to whiten a covariance.",
    ],
    results: [
      { claim: "Max |Σv − λv| over all eigenpairs, from a hand-written Jacobi solver", value: "1.6e-14" },
      { claim: "Orthonormality error of the recovered basis", value: "2.0e-15" },
      { claim: "Variance increments for 3 sources in 8 contacts", value: "58%, 31%, 9%, then 0.35% flat" },
      { claim: "Angle between PC1 and the all-ones direction, reference SD 0 → 8", value: "34° → 0.2°" },
      { claim: "Variance explained by PC1 at reference SD 8", value: "98.9%" },
      { claim: "Principal angles, PCA subspace vs true mixing subspace", value: "0.01°, 0.06°, 0.11°" },
      { claim: "Best correlation of any component with any single true source", value: "0.93" },
      { claim: "Components straddling more than one source", value: "1 of 3" },
    ],
  },
  "LIN 6": {
    course: "Foundations · Applied Linear Algebra for Neural Arrays · final lesson",
    title: "Generalised Eigendecomposition and Spatial Filters",
    summary:
      "PCA maximises variance, and the largest thing in an intracranial recording is almost never the interesting thing. Maximising a ratio between two conditions turns an ill-posed question into a well-posed one.",
    stem: "06_generalized_eigendecomposition",
    builds: [
      ["LIN 4", "The mixing model, and shrinkage for a covariance that cannot be inverted."],
      ["LIN 5", "Σ = VΛVᵀ, the Jacobi solver, and the rotation ambiguity that stopped PCA naming a source."],
      ["LIN 3", "That a near-singular matrix inverts without complaint."],
    ],
    underwrites: [
      "The bandpower_contrast recipe, and guardrail G11, which requires a control condition to exist. This module is why the contrast is the meaningful object and the single condition is not.",
      "CSP and xDAWN, which are this algebra with different names.",
    ],
    results: [
      { claim: "Top GED ratio vs best of 20,000 random filters", value: "2.228 vs 2.082" },
      { claim: "Same filter scored against shrunk vs original denominator", value: "2.228 vs 3.067" },
      { claim: "PCA on task data: angle to true source, and to the reference", value: "46.3°, 0.4°" },
      { claim: "GED task vs rest: angle to true source, and to the reference", value: "5.3°, 42.7°" },
      { claim: "Task/rest variance ratio: best contact, PCA, GED", value: "1.08, 1.01, 2.23" },
      { claim: "Angle to true source as shrinkage α goes 0 → 0.2", value: "0.1° → 46.1°" },
      { claim: "Top ratio from 10 control samples, unregularised vs α=0.05", value: "77.8 vs 3.28" },
      { claim: "Angle to true source in both of those cases", value: "48.7°, 44.1°" },
    ],
  },
  "SIG 3": {
    course: "Foundations · Signal Processing for Neural Time Series",
    title: "The Fourier Transform from the Ground Up",
    summary:
      "The transform SIG 1 and SIG 2 were implicitly using, then the two things about it that are routinely got wrong: what sets frequency resolution, and what happens when a signal does not sit exactly on a bin.",
    stem: "03_fourier_from_the_ground_up",
    builds: [
      ["SIG 1", "Sampling rate, Nyquist, and the folding map."],
      ["SIG 2", "That a filter has a magnitude and a phase response."],
    ],
    underwrites: [
      "The psd_by_condition recipe, and guardrail G5. Section 2 is where the window length in that guardrail comes from.",
    ],
    results: [
      { claim: "Orthogonality of the DFT basis over the window", value: "exact to 1e-9" },
      { claim: "Two tones 2 Hz apart, resolved by a 0.25 s window", value: "no (1 peak)" },
      { claim: "Same window zero-padded 32x, giving 4001 bins", value: "still 1 peak" },
      { claim: "Same 0.25 s sampled at 30 kHz instead of 1 kHz", value: "still 1 peak" },
      { claim: "Resolved once the window reaches 1 s", value: "2 peaks" },
      { claim: "Worst sidelobe, tone half a bin off, rectangular window", value: "-20.9 dB" },
      { claim: "Same tone with a Hann, then a Blackman taper", value: "-52.6, -62.2 dB" },
      { claim: "Main lobe width paid for it (rect / Hann / Blackman)", value: "1.22 / 2.03 / 2.28 bins" },
      { claim: "Visibility of an 80 Hz component beside a 100x larger 3.5 Hz one", value: "27 to 31,335" },
    ],
  },
  "SIG 4": {
    course: "Foundations · Signal Processing for Neural Time Series",
    title: "Welch's Method and Multitaper Spectral Estimation",
    summary:
      "Estimating a spectrum is harder than transforming a signal, and it opens with the fact that makes it hard: the obvious estimator does not get better as you collect more data.",
    stem: "04_welch_and_multitaper",
    builds: [
      ["SIG 1", "Sampling rate and Nyquist."],
      ["SIG 3", "The DFT, resolution 1/T, and the effect of a taper."],
    ],
    underwrites: [
      "The psd_by_condition recipe, which is Welch.",
      "Guardrail G8, which asks for a z-score beside any dB figure, because a single spectrum's apparent structure is largely variance.",
    ],
    results: [
      { claim: "Periodogram relative SD across a 64x increase in data", value: "1.00 to 1.00" },
      { claim: "Welch relative SD vs the 1/sqrt(K) prediction, K = 7 to 511", value: "0.380/0.378 ... 0.051/0.044" },
      { claim: "Naive Welch match to multitaper resolution", value: "silently 2x blurrier" },
      { claim: "Effective resolution of that naive match vs multitaper", value: "3.96 vs 1.95 Hz" },
      { claim: "Relative SD at genuinely matched resolution, Welch vs multitaper", value: "0.415 vs 0.376" },
      { claim: "Honest multitaper advantage", value: "9 percent, not a landslide" },
    ],
  },
  "SIG 5": {
    course: "Foundations · Signal Processing for Neural Time Series",
    title: "Complex Morlet Wavelets and the Time-Frequency Trade",
    summary:
      "A spectrum that changes with time, and the discovery that SIG 3's resolution trade returns in a sharper form: a bound on knowing when against knowing what frequency.",
    stem: "05_morlet_wavelets",
    builds: [
      ["SIG 2", "Convolution, and that a narrow filter rings for many cycles."],
      ["SIG 3", "The DFT, resolution 1/T, and the effect of a taper."],
      ["SIG 4", "That an estimator has variance, and that resolution is bought."],
    ],
    underwrites: [
      "The tfr_onset recipe, and guardrail G5. Section 3 computes the number G5 compares against.",
    ],
    results: [
      { claim: "Gabor product sigma_t x sigma_f across 3 frequencies and 3 cycle counts", value: "0.15915 every time" },
      { claim: "Measured spectral FWHM vs predicted, 20 Hz at 3 cycles", value: "15.72 vs 15.70 Hz" },
      { claim: "Spectral sigma, Gaussian vs boxcar of equal duration", value: "2.03 vs 10.04 Hz" },
      { claim: "Wavelet support at 7 cycles, 5 Hz vs 80 Hz", value: "1339 vs 85 ms" },
      { claim: "A 100 ms burst measured at 3 cycles", value: "76 ms (0.76x)" },
      { claim: "The same burst measured at 12 cycles", value: "166 ms (1.66x)" },
      { claim: "G5 verdict at 7 and 12 cycles for a 100 ms burst", value: "refuse: ruler longer than object" },
    ],
  },
  "SIG 6": {
    course: "Foundations · Signal Processing for Neural Time Series · final lesson",
    title: "The Hilbert Transform and Instantaneous Features",
    summary:
      "Amplitude and phase without choosing a centre frequency, which sounds strictly better and is the source of the most common misuse in the field. The word instantaneous has a precise meaning, and nothing in the arithmetic checks whether it applies.",
    stem: "06_hilbert_instantaneous_features",
    builds: [
      ["SIG 2", "Bandpass filtering, zero-phase filtering, and that a narrow filter rings."],
      ["SIG 3", "That a real signal has a conjugate-symmetric spectrum."],
      ["SIG 5", "That amplitude and phase come together from a complex representation."],
    ],
    underwrites: [
      "Burst detection, which thresholds an envelope, and phase-amplitude coupling in CON 3, which needs a phase.",
      "Guardrail G7, which is about a band containing something other than what you named it.",
    ],
    results: [
      { claim: "Envelope of a constant-amplitude tone: mean and SD", value: "3.0000, 3.7e-14" },
      { claim: "Envelope error against a known AM modulator", value: "0.0000" },
      { claim: "Instantaneous-frequency error against a known FM sweep", value: "0.031 Hz" },
      { claim: "Negative instantaneous frequency on broadband LFP", value: "31.9 percent of samples" },
      { claim: "Same LFP filtered to 13-30 Hz", value: "0.7 percent" },
      { claim: "Envelope correlation with true beta, unfiltered vs filtered", value: "0.111 vs 0.717" },
      { claim: "Hilbert vs Morlet at matched bandwidth, and mismatched", value: "0.953 vs 0.867" },
    ],
  },
  "REC 1": {
    course: "Acquisition · Recording Physics and Electrode Geometry",
    title: "Extracellular Biophysics and Volume Conduction",
    summary:
      "LIN 4 wrote volume conduction as a mixing matrix and never said where it came from. This derives it, and settles how far away a contact can hear.",
    stem: "01_extracellular_biophysics",
    builds: [
      ["LIN 3", "The quasi-static monopole kernel, and that a dipole is not it."],
      ["LIN 4", "The mixing model, and that overlapping columns correlate contacts."],
    ],
    underwrites: [
      "Guardrail G2, an effect that tracks electrode identity rather than brain state. Section 3 gives the spatial scale that makes G2 decidable.",
    ],
    results: [
      { claim: "Measured log-log falloff, monopole and dipole", value: "-1.0000, -2.0000" },
      { claim: "Dipole formula vs two opposed monopoles, far field", value: "agree to 1%" },
      { claim: "Spike reach at a 5 uV noise floor", value: "224 um" },
      { claim: "LFP reach at the same floor", value: "4.64 mm" },
      { claim: "Ratio, and what it means for 2 mm contact spacing", value: "21x; shared LFP, no shared units" },
      { claim: "Minimum neighbour-to-peak ratio across all source depths", value: "0.447" },
      { claim: "Neighbour ratio for an electrode-bound effect", value: "0.000" },
    ],
  },
  "REC 2": {
    course: "Acquisition · Recording Physics and Electrode Geometry",
    title: "Directional DBS Leads and the Orientation Problem",
    summary:
      "The geometry of a real 1-3-3-1 lead, then a problem this repository lists under guardrails not yet implemented: without lead rotation, segment labels cannot be mapped to anatomy.",
    stem: "02_directional_dbs_leads",
    builds: [
      ["REC 1", "The monopole kernel, superposition, and spatial reach."],
      ["LIN 2", "That a montage is a matrix whose rows must sum to zero."],
    ],
    underwrites: [
      "configs/leads.yaml, whose confirmed:false flag exists because of Section 3.",
      "The unimplemented orientation guardrail in docs/guardrails.md.",
    ],
    results: [
      { claim: "Segment area vs ring, and resulting impedance", value: "1/3 area, 3.00x impedance" },
      { claim: "Ring-segment-ring impedance signature across 8 contacts", value: "1,3,3,3,3,3,3,1" },
      { claim: "Single-segment steering contrast at 1 / 2 / 4 mm", value: "4.48 / 1.93 / 1.38" },
      { claim: "Equal weights are not a ring: contrast at 1 mm", value: "1.43" },
      { claim: "Segment reported for one fixed 75 deg source, across rotations", value: "b, a, a, a, a, c" },
      { claim: "Worst-case angular error from unknown rotation", value: "60 degrees" },
      { claim: "What survives without rotation", value: "off-axis yes, direction no" },
    ],
  },
  "REC 3": {
    course: "Acquisition · Recording Physics and Electrode Geometry",
    title: "ECoG Grids, Strips, and Stereo-EEG Shafts",
    summary:
      "An electrode array samples space, so it can alias in space, and the consequences are exactly as irreversible as they were in time.",
    stem: "03_ecog_grids_and_seeg",
    builds: [
      ["SIG 1", "The sampling theorem, the folding map, and that aliasing is irreversible."],
      ["REC 1", "The monopole kernel, superposition, and spatial reach."],
    ],
    underwrites: [
      "Any claim that an effect is focal, and any comparison of spatial extent between arrays with different spacing.",
    ],
    results: [
      { claim: "A 0.01 mm contact vs the point-source formula", value: "agree to 1%" },
      { claim: "Spatial FWHM, 0.5 mm vs 5 mm contact", value: "blur grows measurably" },
      { claim: "A 7.1 mm cortical pattern on a 10 mm clinical grid", value: "aliases to 25 mm" },
      { claim: "Same pattern on a 4 mm and a 2 mm grid", value: "9.1 mm, then faithful" },
      { claim: "Structure at exactly the grid spacing", value: "looks uniform" },
      { claim: "sEEG coverage, 14 shafts of 12 contacts", value: "3.7% of brain volume" },
      { claim: "Same implant across plausible reach assumptions", value: "0.6% to 12.8%" },
    ],
  },
  "REC 4": {
    course: "Acquisition · Recording Physics and Electrode Geometry",
    title: "Neuropixels, Spatial Oversampling, and Drift",
    summary:
      "The opposite regime from a clinical grid: 20 micron pitch against a 200 micron spike reach, where aliasing is not the problem and the difficulty moves to a probe that will not hold still.",
    stem: "04_neuropixels_and_drift",
    builds: [
      ["REC 1", "Spike reach of roughly 200 microns, and 1/r^2 falloff."],
      ["REC 3", "Spatial sampling and the spatial Nyquist argument."],
      ["LIN 1", "The dot product as a projection, and template matching."],
    ],
    underwrites: [
      "SPK 3, which sorts spikes. This module supplies the reason sorting is a spatial problem rather than a per-channel one.",
    ],
    results: [
      { claim: "Sites within reach of one unit: Neuropixels vs DBS lead", value: "42 vs 1" },
      { claim: "Optimal number of sites to combine for SNR", value: "42, not 384" },
      { claim: "AP vs LFP data rate", value: "14.40 vs 1.20 MB/s (12x)" },
      { claim: "G6 usable-bandwidth check, both streams", value: "both pass" },
      { claim: "One hour of recording, AP stream", value: "51.8 GB" },
      { claim: "Profile correlation after one site pitch of drift (20 um)", value: "1.000 to 0.596" },
      { claim: "After 100 um", value: "-0.03" },
      { claim: "Identical 100 um drift on a 2 mm-spaced lead", value: "1.0000, invisible" },
    ],
  },
  "REC 5": {
    course: "Acquisition · Recording Physics and Electrode Geometry · final lesson",
    title: "What a Contact Label Means",
    summary:
      "\"Contact 2b, in STN, showed the effect\" contains three claims. The recording supports one of them well, one weakly, and one not at all.",
    stem: "05_localization_and_contact_labels",
    builds: [
      ["REC 1", "That an LFP falls off as a power of distance and reaches millimetres."],
      ["REC 2", "The 1-3-3-1 geometry, and that lead rotation is frequently unknown."],
      ["STO 1", "The spread of a dB value averaged over k segments, from the trigamma function."],
    ],
    underwrites: [
      "Any statement in this app that names an anatomical target for a contact, and the wording of a legend that names a best contact.",
    ],
    results: [
      { claim: "Moving a source 0.2 mm across the midpoint between rows", value: "changes amplitudes 7 percent and flips the winner" },
      { claim: "At the midpoint itself", value: "the two rows record the same amplitude bit for bit" },
      { claim: "Median gap, best row to second, at 1.5 mm pitch", value: "1.98 dB" },
      { claim: "The same at 3.0 mm pitch", value: "5.45 dB" },
      { claim: "Estimator spread at 4 segments, the ordering psd.py uses", value: "2.78 dB, larger than the gap it must beat" },
      { claim: "The other ordering's spread, for comparison", value: "2.31 dB, so the app uses the noisier one" },
      { claim: "Best row correctly identified, 1.5 mm pitch, 4 segments", value: "67 percent" },
      { claim: "The same at 64 segments", value: "90 percent, a recording-length decision" },
      { claim: "How much that depends on the assumed source distance", value: "44 to 86 percent, so quote the shape not the number" },
      { claim: "Chance an anatomical label is wrong, one boundary", value: "Phi(-margin/sigma), so only the ratio matters" },
      { claim: "Margin 1 mm against registration error 1 mm", value: "16 percent, about one label in six" },
      { claim: "Rows-in-target changed by a 1 mm error, 1.5 mm lead", value: "45 percent of the time" },
      { claim: "The same on the 3.0 mm lead at a 6 mm target", value: "0 percent, but only because 6 mm is two of its pitches" },
      { claim: "Move the target to 9 mm", value: "the wide lead is wrong 100 percent of the time" },
      { claim: "Of the three numbers a reader needs", value: "the app has two; the margin needs a registration it never does" },
    ],
  },
  "SPK 1": {
    course: "Analysis · Spike Trains and Single-Unit Activity",
    title: "Splitting LFP from Spikes, and What Leaks Across",
    summary:
      "Every pipeline splits slow from fast and treats them as separate measurements. This builds the split properly, then tests the contamination claim everybody repeats.",
    stem: "01_band_split_and_spike_bleed",
    builds: [
      ["SIG 1, SIG 2", "Nyquist, filter design, and that a filter has a phase."],
      ["REC 1, REC 4", "That spikes fall off steeply, and the hardware AP/LFP split."],
    ],
    underwrites: [
      "Guardrail G7, contamination in a high band, in the version that applies when the contaminant is the brain itself.",
    ],
    results: [
      { claim: "Reconstruction error of lfp + spikes vs the original", value: "0.18%" },
      { claim: "Spike energy below 300 Hz, 2 ms vs 0.5 ms waveform", value: "3.5% vs 0.03%" },
      { claim: "Spike share of 70-150 Hz power at realistic amplitudes", value: "0.08%" },
      { claim: "High-gamma change from an 8x multi-unit rate increase", value: "under 2%" },
      { claim: "Where the bleed actually lives", value: "250-300 Hz, 20x larger" },
      { claim: "Background needed for the received claim to hold", value: "4.9 uV, 12x below typical" },
      { claim: "Spike share if a montage cuts the background 10x", value: "0.08% to 7.6%" },
    ],
  },
  "SPK 2": {
    course: "Analysis · Spike Trains and Single-Unit Activity",
    title: "Robust Spike Detection",
    summary:
      "Deciding what counts as a spike turns on estimating a noise level from data that contains the thing you are looking for.",
    stem: "02_robust_spike_detection",
    builds: [
      ["SPK 1", "The band split and the spike waveform."],
      ["PRE 1", "That the median absolute deviation is robust where a standard deviation is not."],
    ],
    underwrites: [
      "Guardrail G4, a threshold set across conditions when testing structure.",
    ],
    results: [
      { claim: "The 0.6745 constant is Phi-inverse(0.75)", value: "0.674490, verified" },
      { claim: "Noise inflation at 400 Hz firing: std vs robust", value: "2.25x vs 1.34x" },
      { claim: "Why robustness has a limit", value: "1 ms spike at 400 Hz = 40% duty" },
      { claim: "Threshold crossings vs refractory-separated events", value: "several-fold inflation" },
      { claim: "Threshold shift rest to task: std vs robust", value: "+34.4 vs +7.5 uV" },
      { claim: "Recall gap for 45 uV units: std vs robust", value: "36.6% vs 17.8%" },
    ],
  },
  "SPK 3": {
    course: "Analysis · Spike Trains and Single-Unit Activity",
    title: "Spike Sorting and Unit Quality Metrics",
    summary:
      "Biology supplies a measurable answer to whether a cluster is one neuron: a neuron cannot fire twice within its refractory period, so every violation is provably not one neuron.",
    stem: "03_sorting_and_quality_metrics",
    builds: [
      ["SPK 2", "Detection, refractory windows, and thresholds interacting with rate."],
      ["REC 4", "That a unit appears on many sites, so a template is spatial."],
    ],
    underwrites: [
      "Any claim about a single unit, and any figure whose caption says well isolated.",
    ],
    results: [
      { claim: "Bias recovering planted contamination up to 10%", value: "under 0.5 points" },
      { claim: "Bias at 20% contamination, and why", value: "+3.4, ignores contaminant pairs" },
      { claim: "Spread across repeats at 5% contamination", value: "5.13% +/- 1.01%" },
      { claim: "Complementary-tuning contaminant vs independent", value: "reads under half the truth" },
      { claim: "Bursty contaminant", value: "reads dirtier, up to 100%" },
      { claim: "A unit that lost 30% of its own spikes", value: "contamination 0.00%" },
      { claim: "Amplitude cutoff index for that unit", value: "0.754 vs 0.009 complete" },
    ],
  },
  "SPK 4": {
    course: "Analysis · Spike Trains and Single-Unit Activity · final lesson",
    title: "Peri-Stimulus Histograms and Spike-Field Coherence",
    summary:
      "What a unit responds to, and what it is coupled to. The second question carries a bias that has produced a great deal of confident literature.",
    stem: "04_psth_and_spike_field_coherence",
    builds: [
      ["SIG 3, SIG 4", "Resolution from duration, and that averaging reduces variance."],
      ["SIG 6", "The analytic signal, and that phase is defined only within a band."],
      ["SPK 3", "A sorted unit with known contamination."],
    ],
    underwrites: [
      "Guardrail G11, which requires a control condition, and guardrail G8, which asks for a z-score against a null.",
    ],
    results: [
      { claim: "PSTH recovers planted baseline and peak", value: "5 Hz and 45 Hz" },
      { claim: "Null PLV vs sqrt(pi)/2/sqrt(N), N = 10 to 10000", value: "0.290/0.280 ... 0.0087/0.0089" },
      { claim: "Uncoupled unit, 10 spikes vs 10000", value: "PLV 0.28 vs 0.009" },
      { claim: "No coupling anywhere: rest 200 spikes vs task 2000", value: "PLV 0.108 vs 0.004" },
      { claim: "With real coupling in task only, z against a shift null", value: "+20.45 vs -0.36" },
      { claim: "What the null adds that a raw PLV cannot", value: "rest sits below its own null" },
    ],
  },
  "POP 1": {
    course: "Analysis · Population Dynamics and Latent Structure",
    title: "Neural State Space and Low-Dimensional Manifolds",
    summary:
      "The most repeated result in systems neuroscience, and the one most often measured incorrectly.",
    stem: "01_state_space_and_manifolds",
    builds: [
      ["LIN 4", "Sample covariance, its rank limit, and shrinkage."],
      ["LIN 5", "Eigendecomposition and variance explained."],
      ["SPK 4", "That a measure can be biased by how much data you collected."],
    ],
    underwrites: [
      "Any statement that population activity was k-dimensional, and any comparison of that number between conditions or recordings.",
    ],
    results: [
      { claim: "Participation ratio for k equal eigenvalues", value: "exactly k" },
      { claim: "40 independent channels estimated from T/C = 1.2", value: "55% of the truth" },
      { claim: "Same activity over 4000 vs 150 samples", value: "PR 39.6 vs 33.9" },
      { claim: "Reported dimensionality across smoothing kernels 0 to 25 bins", value: "37.4 to 7.1" },
      { claim: "Measured inter-channel correlation over the same range", value: "0.028 to 0.234" },
      { claim: "True correlation in both cases", value: "zero, by construction" },
    ],
  },
  "POP 2": {
    course: "Analysis · Population Dynamics and Latent Structure",
    title: "Latent Factor Models and Demixing",
    summary:
      "Factor analysis makes one extra assumption than PCA and gets a great deal for it, provided you give it a spare factor.",
    stem: "02_latent_factors_and_demixing",
    builds: [
      ["LIN 4", "The mixing model and the covariance."],
      ["LIN 5", "PCA as a rotation, and the rotation ambiguity."],
      ["POP 1", "That finite data biases a dimensionality estimate."],
    ],
    underwrites: [
      "Any latent-variable summary of a population, and the comparison of such a summary between conditions.",
    ],
    results: [
      { claim: "One bad contact, 40x variance: PCA", value: "90.0 deg off" },
      { claim: "Same data, factor analysis with k = 1", value: "90.0 deg off, a Heywood case" },
      { claim: "Same data, factor analysis with k = 2", value: "1.5 deg" },
      { claim: "Where the failure begins", value: "bad channel above 4x shared variance" },
      { claim: "Marginalisation recovers the planted 2:1 energy split", value: "1.97" },
      { claim: "Both marginal axes recovered to", value: "under 0.5 deg" },
      { claim: "With a shared reference, FA's factor moves toward all-ones", value: "and 46 deg off the truth" },
      { claim: "After common average reference", value: "back to 18 deg" },
      { claim: "After a DIFFERENCING montage", value: "89 deg, and EM never converges" },
      { claim: "Why: differencing a block loading leaves", value: "one nonzero entry, unidentifiable" },
    ],
  },
  "POP 3": {
    course: "Analysis · Population Dynamics and Latent Structure · final lesson",
    title: "Recursive Online Decoding with the Kalman Filter",
    summary:
      "A brain-computer interface must estimate the state now, from data up to now, and its behaviour is set by two covariances nobody measures.",
    stem: "03_kalman_online_decoding",
    builds: [
      ["LIN 4", "Covariance, and that a poor one inverts silently."],
      ["SIG 2", "That a causal filter has an unavoidable group delay."],
      ["POP 2", "The observation model."],
    ],
    underwrites: [
      "GRL 2's adaptive DBS control loop, which is this filter with a controller attached.",
    ],
    results: [
      { claim: "Kalman vs per-sample least squares", value: "72% lower RMSE" },
      { claim: "Misstating measurement noise by 100x", value: "RMSE 0.103 to 0.272" },
      { claim: "What the filter's own uncertainty reports about it", value: "nothing; it never sees residuals" },
      { claim: "Residual variance does carry the evidence", value: "0.485 vs 0.571" },
      { claim: "Lag to a step: trusts data vs trusts model", value: "12 vs 57 samples" },
      { claim: "Pre-step noise for those two", value: "0.097 vs 0.039" },
    ],
  },
  // CON 1 renders through ZeroLagLab.tsx. This entry is the fallback if that page
  // is ever removed, and the reachability test checks one of the two exists.
  "CON 2": {
    course: "Analysis · Connectivity and Spectral Coupling",
    title: "The Weighted Phase Lag Index, and Directionality",
    summary:
      "Build a measure that sees nothing but the lag, confirm it works, then measure what it costs.",
    stem: "02_wpli_and_directionality",
    builds: [
      ["CON 1", "The zero-lag trap, and that a montage only partly repairs it."],
      ["SIG 3, SIG 4", "The cross-spectrum."],
      ["SIG 6", "The analytic signal."],
    ],
    underwrites: [
      "Every directed or undirected connectivity claim between two intracranial contacts.",
    ],
    results: [
      { claim: "Volume conduction: PLV vs wPLI", value: "0.77 vs 0.06" },
      { claim: "True 12 ms interaction: PLV vs wPLI", value: "0.79 vs 0.99" },
      { claim: "Genuine zero-lag coupling from common drive", value: "PLV 0.40, wPLI 0.09" },
      { claim: "What wPLI reports for real zero-lag coupling", value: "essentially nothing" },
      { claim: "Granger, genuine one-way drive", value: "0.097 vs 0.001 reverse" },
      { claim: "Granger, hidden common driver, NO connection", value: "0.040 with 2x asymmetry" },
      { claim: "Spurious Granger when delays are nearly equal", value: "22.6, ten times the real one" },
      { claim: "After conditioning on the driver", value: "0.0003" },
    ],
  },
  "CON 3": {
    course: "Analysis · Connectivity and Spectral Coupling",
    title: "Phase-Amplitude Coupling and Waveform Shape",
    summary:
      "A confound needing no second region, no volume conduction and no shared reference: just the shape of the waveform.",
    stem: "03_phase_amplitude_coupling",
    builds: [
      ["SIG 3", "That a non-sinusoidal periodic signal has harmonics."],
      ["SIG 6", "The analytic signal and the envelope."],
      ["SPK 4", "That a coupling measure needs a null."],
    ],
    underwrites: [
      "Guardrail G8, and any cross-frequency claim about subthalamic beta, which is famously non-sinusoidal.",
    ],
    results: [
      { claim: "Modulation index, no coupling vs genuine coupling", value: "0.00008 vs 0.00714" },
      { claim: "A single sharp oscillator, no coupling anywhere", value: "0.01917" },
      { claim: "Symmetric version of the same oscillator", value: "0.00008" },
      { claim: "Harmonics falling inside the 50-150 Hz band", value: "60, 80, 100, 120, 140 Hz" },
      { claim: "Narrowing the band to one harmonic: spurious", value: "0.01941 to 0.00000" },
      { claim: "Same narrowing, genuine coupling", value: "0.00714 to 0.00295" },
      { claim: "z against a shuffled null, spurious case", value: "+18.0, highly significant" },
      { claim: "Same test on a perfectly periodic signal", value: "+1.0, the null is degenerate" },
    ],
  },
  "CON 4": {
    course: "Analysis · Connectivity and Spectral Coupling · final lesson",
    title: "Aperiodic Decay against Periodic Oscillations",
    summary:
      "Every module that took a band and reported its power assumed band power measures an oscillation. It measures two things.",
    stem: "04_aperiodic_and_periodic",
    builds: [
      ["SIG 4", "Welch, and that a spectral estimate has variance."],
      ["SIG 3", "That a band is an interval on a frequency axis, nothing more."],
      ["SPK 1", "That 1/f dominates an LFP spectrum."],
    ],
    underwrites: [
      "Guardrail G8, and the bandpower_contrast recipe, which reports a band and therefore both components at once.",
    ],
    results: [
      { claim: "Offset change of +0.3: every band moves by", value: "1.995x, identically" },
      { claim: "Exponent change as a rotation about 60 Hz", value: "theta up 1.93x, low gamma down 0.70x" },
      { claim: "Exponent recovered across 0.8 to 3.0", value: "within 0.01" },
      { claim: "Peaks invented in a purely aperiodic spectrum", value: "1 entry, height 0.000" },
      { claim: "Beta rise from a slope rotation", value: "1.42x" },
      { claim: "Beta rise from a genuine oscillation increase", value: "1.46x" },
      { claim: "Fitted exponent change for those two", value: "+0.50 vs -0.00" },
      { claim: "Fitted peak height change", value: "opposite signs" },
    ],
  },
  "GRL 1": {
    course: "Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails",
    title: "Stimulation Artifact and the Cost of Blanking",
    summary:
      "The standard mitigation is a deletion of samples, and its cost is not where intuition puts it.",
    stem: "01_stimulation_artifact_and_blanking",
    builds: [
      ["SIG 1", "Aliasing and quantization with a large signal present."],
      ["SIG 3, SIG 4", "That a periodic operation creates energy at its own rate."],
      ["PRE 1", "That excision costs the time base, not the average spectrum."],
    ],
    underwrites: [
      "G2's control loop, and every recording made with stimulation on.",
    ],
    results: [
      { claim: "Artifact to beta amplitude ratio", value: "66,667x" },
      { claim: "Bits reaching the beta with the range set for the artifact", value: "0.0 of 16" },
      { claim: "Blanking the pulse alone, all bands", value: "within 4%" },
      { claim: "An 8-sample guard band: high gamma", value: "1.90x" },
      { claim: "A 24-sample guard band: high gamma", value: "7.19x" },
      { claim: "Beta at every guard setting", value: "1.00x, so nothing warns you" },
      { claim: "130 Hz harmonics at a 250 Hz sensing rate", value: "two land in beta" },
    ],
  },
  "GRL 2": {
    course: "Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails",
    title: "Adaptive DBS Control Loops",
    summary:
      "Every delay SIG 2 measured now sits inside a feedback loop, where delay stops being an inconvenience and becomes a stability problem.",
    stem: "02_adaptive_dbs_control_loops",
    builds: [
      ["SIG 2", "That a causal filter is late, and how late depends on the band."],
      ["SIG 5", "That an envelope estimate smears events by about sigma_t."],
      ["POP 3", "That an online estimator trades responsiveness against noise."],
      ["G1", "That the beta estimate reaching the controller is contaminated."],
    ],
    underwrites: [
      "Every closed-loop stimulation claim, and the reason configs/erna.yaml records that its defaults are unreviewed.",
    ],
    results: [
      { claim: "Ordinary configuration total loop latency", value: "239 ms, about 4 beta cycles" },
      { claim: "Largest stable gain at 50 ms delay", value: "4.5" },
      { claim: "Largest stable gain at 400 ms delay", value: "1.0" },
      { claim: "True beta as contamination goes 0 to 0.6", value: "0.700 falls to 0.571" },
      { claim: "The number the device logs, same range", value: "0.700 rises to 0.829" },
      { claim: "Direction of those two", value: "opposite" },
    ],
  },
  "GRL 3": {
    course: "Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails",
    title: "EMG Contamination in the Speech Band",
    summary:
      "Muscle is the one contaminant that is locked to the task, so averaging over trials builds it up instead of averaging it away.",
    stem: "03_emg_contamination_in_speech",
    builds: [
      ["SIG 4", "Welch, and reading a contaminant's share of a band."],
      ["SPK 1", "The method of comparing a contaminant against the physiology, applied there to spike bleed."],
      ["REC 1", "That a bipolar montage cancels what two contacts share."],
    ],
    underwrites: [
      "Guardrail G7, its emg_band_hz of 100 to 1000 Hz, its require_bipolar mitigation, and why it escalates to block for overt speech only.",
    ],
    results: [
      { claim: "EMG amplitude reaching beta at ordinary levels", value: "11.2 uV" },
      { claim: "The same EMG reaching high gamma", value: "2.2 uV" },
      { claim: "Speech-locked high-gamma rise from muscle with no cortex present", value: "1.65x" },
      { claim: "When that muscle-only rise peaks", value: "+521 ms after onset" },
      { claim: "Bipolar rejection of a uniform far field", value: "exact" },
      { claim: "What bipolar costs in unshared background", value: "doubles it" },
      { claim: "Muscle-only, overt then inner speech", value: "1.67x then 0.99x" },
      { claim: "Cortex-only, overt then inner speech", value: "1.73x then 1.73x" },
    ],
  },
  "GRL 4": {
    course: "Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails",
    title: "Non-Stationarity Larger Than the Effect",
    summary:
      "Drift is a confound that averaging cannot fix, a guardrail can only flag late, and a design can remove entirely. The order of those three is the lesson.",
    stem: "04_nonstationarity_and_drift",
    builds: [
      ["SIG 4", "Welch, and that a spectral estimate has variance of its own."],
      ["POP 1", "That smoothing destroys independent samples."],
      ["CON 4", "That band power moves when the aperiodic component moves, with no oscillation involved."],
    ],
    underwrites: [
      "Guardrail G9 and its excursion_to_effect_ratio of 1.0, and the case for interleaving conditions rather than blocking them.",
    ],
    results: [
      { claim: "Effect of 16x more data on the error bar", value: "quartered, the 1/sqrt(n) the textbook promises" },
      { claim: "Effect of 16x more data on the excursion", value: "unchanged" },
      { claim: "Mean error at an excursion 3.3x the effect", value: "0.319, against a true effect of 0.150" },
      { claim: "Baseline windows reporting the wrong sign there", value: "100 percent of them" },
      { claim: "Usable estimates at ratio 0.5, then at 1.0", value: "99%, then 1%" },
      { claim: "Where the collapse actually happens", value: "ratio 0.73, below the threshold" },
      { claim: "Blocked design bias at excursion 4x the effect", value: "-0.38 against a true +0.15" },
      { claim: "Randomized interleaving: bias, and spread", value: "bias removed, but spread grows 7x" },
      { claim: "Strict alternation", value: "cancels the drift exactly, and any other alternating confound with it" },
    ],
  },
  "GRL 5": {
    course: "Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails · final lesson",
    title: "The Thirteen Scientific Guardrails",
    summary:
      "Every module in this curriculum has been underwriting a guardrail. This one collects them and names the module that supplies each number.",
    stem: "05_the_thirteen_guardrails",
    builds: [
      ["Everything", "This module is the index."],
    ],
    underwrites: [
      "configs/guardrails.yaml, docs/guardrails.md, guardrails/checks.py and qc/gate.py.",
      "The gate is enforced in the package rather than the interface, so a rule cannot be avoided by using a different front end.",
    ],
    results: [
      { claim: "Guardrails, and how many block a run outright", value: "13, of which 6 block" },
      { claim: "Guardrails whose number a module here derives", value: "11 of 13" },
      { claim: "The other two", value: "G10 and G13, provenance rules with no number" },
      { claim: "Measures with a non-physiological process that mimics them", value: "8 catalogued" },
      { claim: "Analysis parameters that silently decide a result", value: "7 catalogued" },
      { claim: "Modules those two tables draw on", value: "13 of 46" },
      { claim: "Guardrails screenable from a plan before touching data", value: "5 of 13" },
      { claim: "Each rule fires on its own trigger and nothing else", value: "verified, 1 finding each" },
    ],
  },
  "INF 1": {
    course: "Scientific Integrity · Statistical Inference for Neural Recordings",
    title: "The Shuffled Null, and Which Hypothesis Each Shuffle Encodes",
    summary:
      "A permutation test is not assumption-free. It has exactly one assumption, and the shuffle you write down is where you state it.",
    stem: "01_the_shuffled_null",
    builds: [
      ["SIG 4", "That a spectral estimate has variance of its own."],
      ["POP 1", "That neural time series are autocorrelated, so neighbouring samples are not independent."],
      ["GRL 4", "That a baseline drifts, and that blocked, alternating and randomized designs differ."],
    ],
    underwrites: [
      "Every shuffled null in the curriculum and in dbsspeech.stats: CON 3's coupling null, SPK 4's phase-locking null, and any claim that a contrast beats chance.",
    ],
    results: [
      { claim: "Permutation test on exchangeable data, false positive rate", value: "0.045 against a nominal 0.05" },
      { claim: "Largest gap between its p-values and uniform", value: "0.038" },
      { claim: "Smallest reportable p with 199 shuffles", value: "0.005, and it is not zero" },
      { claim: "Shuffling samples inside AR(1) trials, rho 0.9", value: "rejects a true null 61 percent of the time" },
      { claim: "Shuffling trial labels on the same data", value: "7 percent" },
      { claim: "Why: width of the sample-shuffled null", value: "4.2x too narrow, and sqrt(100/5) predicts it" },
      { claim: "Blocked design under drift, free shuffle", value: "63 percent false positives, and no shuffle can fix it" },
      { claim: "Randomized design, free shuffle", value: "4.0 percent, because the free shuffle is the randomization" },
      { claim: "Alternating design, free shuffle", value: "0 percent, conservative rather than safe" },
      { claim: "Its matching sign-flip test on a trending baseline", value: "0.044 to 0.116 as the trend steepens, so it is not exact" },
      { claim: "Power cost of that, at a true effect of 0.3", value: "24 percent against the matching test's 54" },
      { claim: "Significant results at 8 trials per condition", value: "overstate a 0.30 effect 3.9x" },
      { claim: "And how many of them point the wrong way", value: "5 percent" },
    ],
  },
  "INF 2": {
    course: "Scientific Integrity · Statistical Inference for Neural Recordings",
    title: "Multiple Comparisons and the Cluster Permutation Test",
    summary:
      "A time-frequency map asks the same question a few thousand times. The correction this field uses is built here from scratch, along with the thing it does not give you.",
    stem: "02_multiple_comparisons_and_clusters",
    builds: [
      ["INF 1", "The permutation null, the unit-of-exchangeability argument, and the 1/(B+1) floor."],
      ["SIG 5", "That a time-frequency map is a smoothed picture, so neighbouring cells are not independent."],
    ],
    underwrites: [
      "Any claim that a contrast is significant somewhere in a map, and the wording of every figure caption that reports one.",
    ],
    results: [
      { claim: "Empty 200-point map, any point significant at 0.05", value: "0.730 of maps" },
      { claim: "Independent tests that rate implies", value: "26, not 200" },
      { claim: "What the smoothing kernel's resel count says", value: "14, about half, so a lower bound" },
      { claim: "Bonferroni false positive rate on empty maps", value: "0.000, the cost of assuming 200 tests" },
      { claim: "Benjamini-Hochberg on the same maps", value: "0.010" },
      { claim: "Power at a weak effect: Bonferroni, BH, cluster", value: "0.285, 0.435, 0.490" },
      { claim: "At the strong effect, where both are near ceiling", value: "0.865, 0.960, 0.945, so BH is level with it" },
      { claim: "Cluster test false positive rate", value: "0.060" },
      { claim: "Lenient vs strict threshold, broad weak effect", value: "0.287 against 0.160" },
      { claim: "The same two thresholds on a narrow strong effect", value: "0.380 against 0.533, a crossover" },
      { claim: "True effect width 20, reported width as the effect grows", value: "21, 24, 29, then 35" },
      { claim: "Reported window at the largest effect", value: "83 to 117, against a truth of 90 to 110" },
      { claim: "A 20-point effect after the pipeline's own smoothing", value: "already 22 points wide" },
    ],
  },
  "INF 3": {
    course: "Scientific Integrity · Statistical Inference for Neural Recordings · final lesson",
    title: "What a z Score Means, and the Twenty Ways to Compute One",
    summary:
      "configs/statistics.yaml offers four centres and five scales, and every one produces a column labelled z. Three of its caveats are arithmetic, and this lesson proves them.",
    stem: "03_what_a_z_score_means",
    builds: [
      ["INF 1", "That a number needs a null before it is a result."],
      ["SIG 4", "That a band power estimate has a spread across segments, which is where db_sd comes from."],
      ["GRL 4", "That a baseline window is a choice, and the choice moves the answer."],
    ],
    underwrites: [
      "configs/statistics.yaml in full, and the caveat strings the interface shows beside each option.",
      "Guardrail G8, which asks for a z alongside any dB difference.",
    ],
    results: [
      { claim: "One cell, one true effect, the twenty centre-and-scale pairs", value: "z from 1.04 to 3.49" },
      { claim: "How many would be called large at |z| >= 2", value: "8 of 20" },
      { claim: "whole_recording shrinkage, derived and verified", value: "exactly 1 - f, the task fraction" },
      { claim: "grand_mean when a third condition is added", value: "mean z moves 3.84 to 10.21, with no new data" },
      { claim: "A named baseline over the same change", value: "unmoved" },
      { claim: "across_conditions ceiling on |z|", value: "(k-1)/sqrt(k), verified at k = 2, 3, 4, 6" },
      { claim: "And at two conditions", value: "every z is exactly 0.7071, whatever the data" },
      { claim: "Same true effect, one condition 3x noisier: own_condition", value: "reported 2.9x apart" },
      { claim: "The same pair under the pooled scale", value: "reported equal, which they are" },
      { claim: "Top-|dB| channel is also top-|z| channel", value: "19 percent of runs" },
      { claim: "|z| of the top-|dB| channel", value: "below 2 in 45 percent of runs" },
      { claim: "Which ranking finds the truly largest effect", value: "dB 54 percent, z 27, so z is not an effect estimate" },
      { claim: "An oracle z given each channel's exact noise", value: "28 percent, so the gap is the estimand, not the estimate" },
    ],
  },
  "DEC 1": {
    course: "Electives · Machine Learning and Neural Decoding",
    title: "Least Squares and Ridge, Built and Then Checked",
    summary:
      "The model almost every decoding paper fits underneath whatever it is called. The arithmetic is one line; the part that is hard to check is what a weight means.",
    stem: "01_least_squares_and_ridge",
    builds: [
      ["LIN 3", "Condition number, multicollinearity, and that a near-singular matrix inverts without complaining."],
      ["LIN 4", "That a shared reference makes contacts correlate, and that shrinkage trades bias for stability."],
      ["INF 1", "That an estimate selected for looking good is not an unbiased estimate."],
    ],
    underwrites: [
      "Every decoding result this app could produce, DEC 2's cross-validation argument, and DEC 5's activation pattern.",
    ],
    results: [
      { claim: "Hand-written ridge against sklearn, every penalty tested", value: "agree to about 1e-14" },
      { claim: "OLS residual against every column of the design", value: "orthogonal to about 1e-12" },
      { claim: "Median correlation between contacts on a shared reference", value: "0.94, condition number 887" },
      { claim: "Bootstrap spread of a weight, unpenalised against alpha=200", value: "7.6x larger" },
      { claim: "The same against the tuned alpha=10", value: "1.7x, so the factor needs its alpha named" },
      { claim: "Held-out MSE, unpenalised against best", value: "2.001 to 1.608 at alpha=10" },
      { claim: "Can training error choose the penalty?", value: "no, it is monotone in alpha, so its minimum is always 0" },
      { claim: "Bias squared across the penalty sweep", value: "0.003 to 4.74, rising monotonically" },
      { claim: "Variance across the same sweep", value: "0.397 falling to 0.091, and then stopping" },
      { claim: "Where it stops, against var(y)/n", value: "0.091 against 0.077, the training mean's own spread" },
      { claim: "Duplicating one contact 8 times, at alpha=200", value: "its apparent importance rises 2.8x" },
      { claim: "The same at the tuned alpha=10", value: "1.2x, so the distortion scales with the penalty" },
      { claim: "What the decoder's predictions did meanwhile", value: "correlated above 0.99 with the original" },
    ],
  },
  "DEC 2": {
    course: "Electives · Machine Learning and Neural Decoding",
    title: "Cross-Validation on Data That Is Not Independent",
    summary:
      "The single most common way a decoding result is inflated. Every honest number in this lesson is zero, and random five-fold reports up to 0.94.",
    stem: "02_cross_validation_on_autocorrelated_data",
    builds: [
      ["DEC 1", "Ridge, and that training error cannot choose a penalty."],
      ["INF 1", "That the unit you treat as independent is a claim about the data."],
      ["GRL 4", "That a session drifts, so points near each other in time resemble each other."],
    ],
    underwrites: [
      "Any decoding accuracy this app reports.",
      "The case for a fourteenth guardrail on how folds are drawn, which the lesson states and does not adopt.",
    ],
    results: [
      { claim: "Hand-written k-fold against sklearn KFold", value: "identical predictions" },
      { claim: "Independent samples, no relationship: what every scheme reports", value: "nothing, as it should" },
      { claim: "Autocorrelated at rho 0.95, no relationship: random k-fold, ridge", value: "0.586" },
      { claim: "The same cell with nearest neighbours", value: "0.940, and the truth is zero" },
      { claim: "The same recording under contiguous folds", value: "under 0.10" },
      { claim: "At rho = 0, which identifies the cause", value: "every scheme reports nothing" },
      { claim: "With a real relationship: random k-fold against the truth", value: "0.691 against 0.238, a 2.9x overstatement" },
      { claim: "Contiguous folds against the same truth", value: "0.182, accurate and 3.1x more variable" },
      { claim: "Which estimate carries the tighter error bar", value: "the wrong one" },
      { claim: "Penalty chosen by leaky CV: what it achieves", value: "0.210 against an oracle 0.249" },
      { claim: "What it reports having achieved", value: "0.702, which is 3.3x what it delivered" },
      { claim: "So what the leak damages", value: "the number, not the model" },
    ],
  },
  "DEC 3": {
    course: "Electives · Machine Learning and Neural Decoding",
    title: "Backpropagation, and How to Know It Is Right",
    summary:
      "A gradient is the one thing in machine learning with a ground truth available locally. A wrong gradient still trains, which is why you check.",
    stem: "03_backpropagation_from_scratch",
    builds: [
      ["LIN 2", "That a matrix is a linear operator, and that a montage applied to channels is one."],
      ["DEC 1", "Least squares, ridge, and that a fitted weight is not a measurement."],
    ],
    underwrites: [
      "DEC 4's comparison of nonlinear against linear decoders, and DEC 5's argument that a network has no weight map to transform.",
    ],
    results: [
      { claim: "Analytic gradient against central differences", value: "1.1e-9 at worst, 2e-10 on the weight matrices" },
      { claim: "The same check with the tanh derivative left out", value: "0.20 and 0.41, wrong at the first decimal" },
      { claim: "What the broken gradient's training curve did", value: "cut the loss 74 percent, then flattened" },
      { claim: "Where it settled against the correct gradient", value: "18x worse, and still looked converged" },
      { claim: "Linear-activation network against ordinary least squares", value: "agree to about 1e-15" },
      { claim: "Numbers the network holds to express 4 of them", value: "35" },
      { claim: "Five networks, same data, different starts: predictions", value: "correlate above 0.99" },
      { claim: "The same five networks' weight vectors", value: "correlate 0.03 on average, -0.52 at worst" },
      { claim: "Reordering the hidden units", value: "changes predictions by 4e-16" },
      { claim: "Flipping one unit's sign", value: "changes them by exactly zero" },
      { claim: "Weight settings computing the same function, 6 units", value: "exactly 46,080 from those two symmetries" },
    ],
  },
  "DEC 4": {
    course: "Electives · Machine Learning and Neural Decoding",
    title: "Whether Any of This Beats a Straight Line",
    summary:
      "Not a verdict but a boundary, in trial count and how much of the signal is out of linear reach. The intraoperative regime sits on the wrong side of it.",
    stem: "04_nonlinear_against_linear",
    builds: [
      ["DEC 1", "Ridge, and that a penalty has to be chosen on held-out data."],
      ["DEC 3", "What a network is, and that its weights are not identified."],
      ["INF 1", "That a difference measured once, with a spread larger than itself, is not a result."],
    ],
    underwrites: [
      "Any claim in this lab that a nonlinear decoder is or is not worth using, and the trial counts that claim would need.",
    ],
    results: [
      { claim: "Ceiling with a linear truth: ridge against network", value: "0.605 against 0.604, nothing to win" },
      { claim: "Ceiling with half the signal nonlinear", value: "0.438 against 0.576, real headroom" },
      { claim: "Linear truth, every sample size tested", value: "the network never wins" },
      { claim: "25 percent nonlinear, 40 trials: ridge against network", value: "0.395 against 0.338" },
      { claim: "The same at 800 trials", value: "0.519 against 0.561, the ordering reversed" },
      { claim: "Where the network takes the lead for good", value: "between 160 and 320 trials" },
      { claim: "Half the signal nonlinear, at 40 trials", value: "indistinguishable, 38 percent network wins" },
      { claim: "At 80 trials: what the network trades", value: "62 percent less bias, 4.2x the variance" },
      { claim: "Sessions to establish which is better, at 40 trials", value: "218" },
      { claim: "The same at 800 trials", value: "1" },
      { claim: "So a single intraoperative session decides it", value: "by coin flip" },
    ],
  },
  "DEC 5": {
    course: "Electives · Machine Learning and Neural Decoding · final lesson",
    title: "A Decoder's Weights Are Not an Encoding Map",
    summary:
      "A filter's job includes subtracting what it does not want, so the contact recording nothing of interest can be the one it leans on hardest.",
    stem: "05_weights_are_not_an_encoding_map",
    builds: [
      ["LIN 2", "That a montage is a matrix, and a difference of contacts is a spatial filter."],
      ["LIN 4", "That a shared reference puts a large common component on every contact, which is G1."],
      ["LIN 6", "That a spatial filter and the pattern it recovers are different vectors."],
      ["DEC 1", "Ridge, and that a weight is not a measurement."],
    ],
    underwrites: [
      "Every figure in this app that colours contacts by a model coefficient, and the sentence written under it.",
    ],
    results: [
      { claim: "With no nuisance: weight magnitude against the true pattern", value: "ranks it at 0.97, no sign errors" },
      { claim: "With a nuisance 5x the source: the same ranking", value: "falls to 0.31" },
      { claim: "The contact recording none of the source", value: "gets one of the largest weights" },
      { claim: "Contacts that do record it, given negative weights", value: "3 of 10" },
      { claim: "The decoder doing all this", value: "correlates above 0.99 with the source" },
      { claim: "Activation pattern, one matrix multiply", value: "ranks the contacts at 0.90" },
      { claim: "Its sign errors, nuisance from 0 to 10x the source", value: "none at any level" },
      { claim: "One generator against two weaker ones either side", value: "patterns correlate 0.98, same peak contact" },
      { claim: "Two networks decoding the same source", value: "no weight vector to transform at all" },
      { claim: "Their per-contact input weights against the truth", value: "0.38 and 0.39, against the linear pattern's 1.00" },
    ],
  },
};
