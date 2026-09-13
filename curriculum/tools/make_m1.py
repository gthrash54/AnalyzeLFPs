import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("05_dynamics", "01_state_space_and_manifolds")

m.md(r'''# Lesson POP 1: Neural State Space and Low-Dimensional Manifolds {{VARIANT}}

**Analysis · Population Dynamics and Latent Structure**

{{INSTRUCTIONS}}

LIN 1 opened with the idea that an instant of population activity is a point
in a high-dimensional space and that activity traces a trajectory through it.
This module makes that quantitative, and then spends its second half on the claim
that trajectory lives on a low-dimensional manifold, which is the most repeated
result in systems neuroscience and the one most often measured incorrectly.

**What it assumes**

| From | What is used |
|---|---|
| LIN 4 | The sample covariance, its rank limit $\min(C, T-1)$, and shrinkage. |
| LIN 5 | Eigendecomposition, variance explained, and that components are not sources. |
| SPK 4 | That a measure can be biased by how much data you collected. |

**What it underwrites**

Any statement of the form "population activity was $k$-dimensional", and the
comparison of such a number between two conditions or two recordings.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(71)

def sample_covariance(X):
    """From LIN 4."""
    Xc = X - X.mean(axis=1, keepdims=True)
    return (Xc @ Xc.T) / (X.shape[1] - 1)

print("Environment initialized for Lesson POP 1")''')

m.md(r'''---

## 1. Dimensionality as a number

"How many dimensions" needs a definition, because the rank of a covariance
matrix is almost always full and almost always uninformative. The standard
answer is the **participation ratio**, which asks how many eigenvalues are
effectively contributing:

$$\text{PR} = \frac{\left(\sum_i \lambda_i\right)^2}{\sum_i \lambda_i^2}$$

It has the properties you want. For $k$ equal eigenvalues and the rest zero it
returns exactly $k$. For one dominant eigenvalue it returns close to 1. It is
continuous, so it does not need a threshold, and it needs no choice of a variance
cutoff, which is the arbitrary step in "number of PCs to reach 90 percent".''')

m.task(
'''def participation_ratio(eigenvalues: np.ndarray) -> float:
    """Effective dimensionality: (sum lambda)^2 / sum(lambda^2).

    Production equivalent: there is no single standard implementation; this
    definition is used directly in the population-dynamics literature.
    """
    # TODO: clip negatives to zero (numerical noise in a covariance estimate)
    # TODO: return (sum)^2 / sum of squares
    raise NotImplementedError("Implement participation_ratio")''',
'''def participation_ratio(eigenvalues: np.ndarray) -> float:
    """Effective dimensionality: (sum lambda)^2 / sum(lambda^2).

    Production equivalent: there is no single standard implementation; this
    definition is used directly in the population-dynamics literature.
    """
    lam = np.clip(np.asarray(eigenvalues, dtype=float), 0.0, None)
    denom = np.sum(lam ** 2)
    if denom == 0:
        return 0.0
    return float(np.sum(lam) ** 2 / denom)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
# The defining cases, checked directly.
assert np.isclose(participation_ratio(np.ones(7)), 7.0), "k equal eigenvalues gives exactly k"
assert np.isclose(participation_ratio(np.r_[np.ones(3), np.zeros(20)]), 3.0), \\
    "zeros must not count"
assert participation_ratio(np.r_[100.0, np.full(50, 0.01)]) < 1.3, \\
    "one dominant eigenvalue gives close to 1"
assert np.isclose(participation_ratio(np.ones(5)), participation_ratio(np.full(5, 88.0))), \\
    "it is scale invariant, as a dimensionality must be"

print(f"{'eigenvalue pattern':>34} {'participation ratio':>21}")
for name, lam in (("5 equal", np.ones(5)),
                  ("5 equal + 45 tiny", np.r_[np.ones(5), np.full(45, 1e-4)]),
                  ("one dominant", np.r_[100.0, np.full(49, 0.01)]),
                  ("50 equal", np.ones(50)),
                  ("geometric decay 0.8", 0.8 ** np.arange(50))):
    print(f"{name:>34} {participation_ratio(lam):>21.2f}")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The estimate is biased down by finite data

LIN 4 established that a covariance estimated from $T$ samples of $C$ channels is
badly conditioned unless $T \gg C$, and that its smallest eigenvalues are
estimation noise. That noise is not symmetric in its effect here.

A finite sample spreads the eigenvalue spectrum: the large eigenvalues are
over-estimated and the small ones under-estimated, which is the Marchenko-Pastur
result. The participation ratio is a ratio of sums of powers of those
eigenvalues, so spreading them **lowers** it.

The consequence is direct and unpleasant. **A recording with fewer samples will
report a lower dimensionality than an identical recording with more**, even
though nothing about the underlying activity differs. Comparing dimensionality
between two conditions of different length, or between two subjects with
different amounts of usable data, compares data quantity.

Below, the true dimensionality is known exactly, because the data is generated
from independent channels.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
C = 40                                    # channels; the TRUE dimensionality is 40
print(f"{C} independent channels, so the true participation ratio is {C}\\n")
print(f"{'samples T':>10} {'T/C':>6} {'estimated PR':>14} {'as % of truth':>16}")
prs = {}
for T in (50, 100, 400, 2000, 20000):
    X = rng.standard_normal((C, T))
    lam = np.linalg.eigvalsh(sample_covariance(X))
    prs[T] = participation_ratio(lam)
    print(f"{T:>10} {T/C:>6.1f} {prs[T]:>14.2f} {100*prs[T]/C:>15.1f}%")

assert prs[50] < 0.7 * C, "with T/C ~ 1 the estimate is badly biased down"
assert prs[20000] > 0.95 * C, "with plenty of data it recovers the truth"
assert prs[50] < prs[400] < prs[20000], "the bias shrinks monotonically with data"

# The comparison that this breaks: two conditions of different length, identical
# underlying activity.
X_long = rng.standard_normal((C, 4000))
pr_long = participation_ratio(np.linalg.eigvalsh(sample_covariance(X_long)))
pr_short = participation_ratio(np.linalg.eigvalsh(sample_covariance(X_long[:, :150])))
print(f"\\nSAME activity, measured over 4000 samples : PR {pr_long:.2f}")
print(f"SAME activity, measured over  150 samples : PR {pr_short:.2f}")
assert pr_short < 0.85 * pr_long, \\
    "a shorter condition reports lower dimensionality from nothing but its length"
print(f"\\nA {100*(1-pr_short/pr_long):.0f} percent drop in reported dimensionality, with no")
print("change whatsoever in the underlying activity. Only the epoch was shorter.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Low dimensionality that is real, and low dimensionality that is smoothing

Section 2's bias comes from too little data. There is a second route to a low
number that has nothing to do with sampling, and it is easier to fall into
because it is a step everyone takes.

Spike trains are converted to rates by smoothing, usually with a Gaussian kernel
of tens of milliseconds. Smoothing is a low-pass filter, and SIG 3 established that
a filter concentrates power into fewer frequencies. Applied to each channel
independently it does not create cross-channel correlation, so it does not by
itself lower dimensionality. But it does reduce the **effective number of
independent samples**, because neighbouring time points are no longer
independent, and Section 2 showed that fewer effective samples means lower
apparent dimensionality.

So the smoothing kernel is a dimensionality knob. Below, genuinely
high-dimensional activity is smoothed with kernels of increasing width and the
reported dimensionality is measured.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def gaussian_smooth(X, sigma_bins):
    """Smooth each channel independently with a Gaussian kernel."""
    if sigma_bins <= 0:
        return X
    half = int(np.ceil(4 * sigma_bins))
    k = np.exp(-0.5 * (np.arange(-half, half + 1) / sigma_bins) ** 2)
    k /= k.sum()
    return np.array([np.convolve(row, k, mode='same') for row in X])

T_FIXED = 600
X_raw = rng.standard_normal((C, T_FIXED))       # truly 40-dimensional, independent
print(f"{C} independent channels, {T_FIXED} time bins, true PR = {C}\\n")
print(f"{'kernel sigma':>14} {'effective samples':>19} {'reported PR':>13}")
prs_s = {}
for sigma in (0, 2, 5, 10, 25):
    Xs = gaussian_smooth(X_raw, sigma)
    prs_s[sigma] = participation_ratio(np.linalg.eigvalsh(sample_covariance(Xs)))
    eff = T_FIXED / max(1.0, 2 * np.sqrt(np.pi) * sigma) if sigma else T_FIXED
    print(f"{sigma:>11} bins {eff:>19.0f} {prs_s[sigma]:>13.2f}")

assert prs_s[25] < 0.5 * prs_s[0], "heavy smoothing halves the reported dimensionality"
assert prs_s[0] > prs_s[2] > prs_s[10] > prs_s[25], "and the effect is monotonic in kernel width"

# What is the mechanism? The measured correlations rise too, so check whether the
# channels genuinely became coupled or whether this is the same finite-sample
# effect wearing a different hat.
corr_raw = np.abs(np.corrcoef(X_raw)[~np.eye(C, dtype=bool)])
corr_smooth = np.abs(np.corrcoef(gaussian_smooth(X_raw, 25))[~np.eye(C, dtype=bool)])
n_eff = T_FIXED / (2 * np.sqrt(np.pi) * 25)
print(f"\\nmedian |correlation| between channels, unsmoothed : {np.median(corr_raw):.3f}")
print(f"median |correlation| between channels, smoothed   : {np.median(corr_smooth):.3f}")
print(f"1/sqrt(effective samples) = 1/sqrt({n_eff:.0f}) = {1/np.sqrt(n_eff):.3f}")

# The channels are INDEPENDENT by construction, so the true correlation is zero in
# both cases. The measured value is sampling noise, whose scale is 1/sqrt(N).
assert np.median(corr_smooth) > np.median(corr_raw), \\
    "the MEASURED correlation rises after smoothing"
assert abs(np.median(corr_smooth) - 0.67 / np.sqrt(n_eff)) < 0.15, \\
    "and its size is what sampling noise at the effective N predicts, not coupling"
assert abs(np.median(corr_raw) - 0.67 / np.sqrt(T_FIXED)) < 0.05, \\
    "as it is before smoothing, at the full N"
print("\\nThe channels were generated independently, so the true correlation is zero")
print("in both rows. The measured value is sampling noise, and its size tracks")
print("1/sqrt(effective samples) in both cases. Smoothing did not couple anything.")
print("It destroyed independent time points, and Section 2 showed that both inflates")
print("apparent correlation and deflates apparent dimensionality. One cause, two")
print("symptoms, and the second one gets published.")

print(f"\\nSo the reported dimensionality moved from {prs_s[0]:.1f} to {prs_s[25]:.1f} by")
print("changing an analysis parameter, on data whose true dimensionality never changed.")
print("A dimensionality is not comparable across papers unless the kernel matches.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. The participation ratio gives a threshold-free effective dimensionality:
   exactly $k$ for $k$ equal eigenvalues, near 1 for one dominant one, and scale
   invariant.
2. It is **biased downward by finite data**. With 40 independent channels and
   $T/C \approx 1.2$ the estimate recovers 55 percent of the truth,
   and it approaches the truth only when $T$ is hundreds of times $C$. A shorter
   epoch reports lower dimensionality with no change in the activity, so
   comparing dimensionality between conditions of different length compares
   length.
3. Smoothing spike trains into rates destroys independent time points. On truly
   independent channels a 25-bin kernel dropped the reported dimensionality from
   37.4 to 7.1 and simultaneously raised the median measured correlation from
   0.028 to 0.234. Neither is a change in the data: both track
   $1/\sqrt{N_{\text{eff}}}$, so one cause produces two symptoms, and the second
   is the one that gets published.
4. Together: a published dimensionality is a statement about epoch length and
   smoothing kernel at least as much as about the brain, and it is not comparable
   across studies that differ in either.

### Exercises

**Exercise 1.** LIN 4 offered shrinkage as the repair for a poorly conditioned
covariance. Apply it here and measure whether shrinkage reduces the
dimensionality bias, leaves it, or makes it worse. Explain the result in terms of
what shrinkage does to an eigenvalue spectrum.

**Exercise 2.** Construct activity that genuinely lives on a 5-dimensional
manifold inside 40 channels, and find the combination of epoch length and
smoothing kernel that makes truly 40-dimensional activity report the same number.
What would distinguish the two cases?

**Exercise 3.** Section 2's bias has a known form, the Marchenko-Pastur
distribution for the eigenvalues of a sample covariance of white noise. Use it to
build a null: what participation ratio would you expect from pure noise at your
$C$ and $T$? Report your measured dimensionality as a z-score against that,
following guardrail G8.

---

**Next: POP 2, latent factor models.** The participation ratio counts dimensions
without naming them. POP 2 asks what the dimensions are, and separates the part of
the covariance that is shared across neurons from the part that is not.
''')

m.emit()
verify("05_dynamics", "01_state_space_and_manifolds")
print("  POP 1 OK")
