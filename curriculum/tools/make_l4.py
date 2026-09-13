import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("01_linear_algebra", "04_covariance_volume_conduction")

m.md(r'''# Lesson LIN 4: Covariance Matrices and Volume Conduction {{VARIANT}}

**Foundations · Applied Linear Algebra for Neural Arrays**

{{INSTRUCTIONS}}

LIN 1 claimed, without proving it, that an effect appearing on every contact
at once is usually the reference moving rather than the brain. This module is
where that becomes arithmetic.

**What it assumes**

| From | What is used |
|---|---|
| LIN 2 | A montage is a matrix, and $M$ applied to channels gives derivations. |
| LIN 3 | Condition number from singular values, and that a singular matrix does not announce itself. |

**What it underwrites**

Guardrail **G1**, monopolar common mode. By the end you will be able to compute
the fraction of a covariance matrix that a shared reference is responsible for,
which is the quantity G1 is a threshold on.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(4)
print("Environment initialized for Lesson LIN 4")''')

m.md(r'''---

## 1. The sample covariance matrix

For $[C \times T]$ data $X$ with the mean removed along time, the sample
covariance is

$$\hat{\Sigma} = \frac{1}{T-1} X_c X_c^{\top}$$

The $T-1$ rather than $T$ is Bessel's correction: dividing by $T$ gives an
estimator biased low, because the sample mean is itself fitted from the data and
sits closer to the samples than the true mean does.

Every entry is an inner product between two channels, which is LIN 1's dot
product with the mean removed. The diagonal is variance; the off-diagonal is
covariance; normalise by the square roots of the diagonal and you have the
correlation matrix, which is LIN 1's cosine similarity of centred vectors.''')

m.task(
'''def sample_covariance(X: np.ndarray) -> np.ndarray:
    """Covariance of `[n_channels, n_samples]` data, using Bessel's correction.

    Production equivalent: `np.cov`, or `mne.compute_covariance` when the data is
    epoched and you want it estimated per condition.
    """
    # TODO: subtract the mean of each channel, along the time axis
    # TODO: form the [C x C] product of the centred data with its own transpose
    # TODO: divide by (n_samples - 1), not n_samples
    raise NotImplementedError("Implement sample_covariance")''',
'''def sample_covariance(X: np.ndarray) -> np.ndarray:
    """Covariance of `[n_channels, n_samples]` data, using Bessel's correction.

    Production equivalent: `np.cov`, or `mne.compute_covariance` when the data is
    epoched and you want it estimated per condition.
    """
    Xc = X - X.mean(axis=1, keepdims=True)
    return (Xc @ Xc.T) / (X.shape[1] - 1)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
X = rng.standard_normal((6, 5000)) * np.array([[1.0], [2.0], [0.5], [3.0], [1.5], [1.0]])
C = sample_covariance(X)

assert C.shape == (6, 6)
assert np.allclose(C, C.T), "a covariance matrix is symmetric by construction"
assert np.allclose(C, np.cov(X)), "must agree with np.cov, which also uses T-1"

# Bessel's correction is not decoration. Check the bias directly by estimating a
# known variance many times from short records.
true_var, n_short, trials = 4.0, 5, 4000
draws = rng.standard_normal((trials, n_short)) * np.sqrt(true_var)
biased = np.mean([np.sum((d - d.mean()) ** 2) / n_short for d in draws])
corrected = np.mean([np.sum((d - d.mean()) ** 2) / (n_short - 1) for d in draws])
print(f"true variance                    : {true_var:.4f}")
print(f"mean estimate dividing by T      : {biased:.4f}  (low by {100*(1-biased/true_var):.1f}%)")
print(f"mean estimate dividing by T-1    : {corrected:.4f}")
assert abs(corrected - true_var) < abs(biased - true_var), "T-1 must be the less biased estimator"
assert abs(biased / true_var - (n_short - 1) / n_short) < 0.05, "the bias is exactly (T-1)/T"
print("\\nStep 1 passed. The bias dividing by T is exactly (T-1)/T, which is why T-1 is used.")''')

m.md(r'''---

## 2. Volume conduction, written as a matrix

Extracellular potential is a linear superposition. A contact does not record a
source; it records every source, weighted by a mixing coefficient that falls off
with distance. Write $P$ sources and $C$ contacts as

$$X = A S + N$$

where $S$ is $[P \times T]$ source activity, $A$ is the $[C \times P]$ mixing
matrix, and $N$ is sensor noise. Then the covariance follows directly:

$$\Sigma_X = A \Sigma_S A^{\top} + \Sigma_N$$

Read that equation carefully, because it is the whole of guardrail G1. Even when
$\Sigma_S$ is **diagonal**, meaning the sources are mutually uncorrelated and
nothing in the brain is synchronised at all, $A \Sigma_S A^{\top}$ is
**not diagonal** unless the columns of $A$ are orthogonal, which they never are
for contacts that share a volume conductor.

So correlation between contacts is the default state of an electrode array. It
is what geometry produces on its own, and observing it is not evidence of
anything.''')

m.task(
'''def predicted_covariance(A: np.ndarray, source_var: np.ndarray, noise_var: float) -> np.ndarray:
    """Covariance implied by the mixing model, for UNCORRELATED sources.

    `source_var` is the per-source variance, i.e. the diagonal of Sigma_S.
    """
    # TODO: build the diagonal source covariance from source_var
    # TODO: apply the mixing:  A @ Sigma_S @ A.T
    # TODO: add independent sensor noise on the diagonal
    raise NotImplementedError("Implement predicted_covariance")''',
'''def predicted_covariance(A: np.ndarray, source_var: np.ndarray, noise_var: float) -> np.ndarray:
    """Covariance implied by the mixing model, for UNCORRELATED sources.

    `source_var` is the per-source variance, i.e. the diagonal of Sigma_S.
    """
    sigma_s = np.diag(source_var)
    return A @ sigma_s @ A.T + noise_var * np.eye(A.shape[0])''')

m.code('''# --- TEST CELL FOR STEP 2 ---
# A physical mixing matrix: 8 contacts on a shank, 3 sources at different depths.
contact_mm = np.linspace(0, 7.0, 8)
source_mm = np.array([1.0, 3.5, 6.0])
A_mix = 1.0 / (1.0 + np.abs(contact_mm[:, None] - source_mm[None, :]) ** 2)

SOURCE_VAR = np.array([4.0, 1.0, 2.25])
NOISE_VAR = 0.05
T = 200000

# Simulate from the model with provably uncorrelated sources.
S = rng.standard_normal((3, T)) * np.sqrt(SOURCE_VAR)[:, None]
Xmix = A_mix @ S + rng.standard_normal((8, T)) * np.sqrt(NOISE_VAR)

empirical = sample_covariance(Xmix)
predicted = predicted_covariance(A_mix, SOURCE_VAR, NOISE_VAR)
err = np.max(np.abs(empirical - predicted)) / np.max(np.abs(predicted))
print(f"largest relative disagreement, model vs simulation: {err:.3%}")
assert err < 0.05, "the model must predict the covariance of data generated from it"

# The sources really are uncorrelated. Confirm before drawing the conclusion.
source_corr = np.corrcoef(S)
off = source_corr[~np.eye(3, dtype=bool)]
print(f"largest |correlation| BETWEEN SOURCES : {np.max(np.abs(off)):.4f}")
assert np.max(np.abs(off)) < 0.02, "the sources must be uncorrelated for the point to land"

# And yet the contacts are strongly correlated.
chan_corr = empirical / np.sqrt(np.outer(np.diag(empirical), np.diag(empirical)))
off_chan = np.abs(chan_corr[~np.eye(8, dtype=bool)])
print(f"median |correlation| BETWEEN CONTACTS : {np.median(off_chan):.4f}")
print(f"largest |correlation| BETWEEN CONTACTS: {np.max(off_chan):.4f}")
ratio = float(np.median(off_chan) / np.max(np.abs(off)))
print(f"ratio, contact correlation to source correlation: {ratio:.0f}x")
assert np.median(off_chan) > 0.3, "geometry alone produces substantial inter-contact correlation"
assert np.max(off_chan) > 0.9, "and near-perfect correlation for the closest pairs"
assert ratio > 50, "the contacts are correlated orders of magnitude more than the sources"
print("\\nStep 2 passed. The sources are uncorrelated to 0.001 and the contacts are")
print("correlated to a median of 0.42, rising to 0.97 for adjacent pairs. Correlation")
print("between contacts is what an electrode array does at rest, not a finding.")''')

m.md(r'''---

## 3. Adding a shared reference, which is guardrail G1

A shared reference adds one more term. If every contact carries the same
reference signal $r(t)$ with variance $\sigma_r^2$, then $X \to X + \mathbf{1}r$
and

$$\Sigma \to \Sigma + \sigma_r^2\, \mathbf{1}\mathbf{1}^{\top}$$

That added term is rank one, it is constant across every entry, and it drives
every correlation toward $+1$ as $\sigma_r^2$ grows. It has a signature that
distinguishes it from real synchronisation: it affects **all pairs equally**, so
the spread of the off-diagonal correlations collapses even as their mean rises.

G1's thresholds are exactly these two quantities: the fraction of channels
affected, and the spread between them.''')

m.task(
'''def common_mode_fraction(C: np.ndarray) -> float:
    """Fraction of total variance carried by the all-channels-together direction.

    Project the covariance onto the normalised all-ones vector and compare that
    to the total variance. Returns a number in [0, 1].
    """
    # TODO: build the normalised all-ones vector u = 1 / sqrt(C_channels)
    # TODO: the variance along u is u.T @ C @ u
    # TODO: total variance is the trace of C; return the ratio
    raise NotImplementedError("Implement common_mode_fraction")''',
'''def common_mode_fraction(C: np.ndarray) -> float:
    """Fraction of total variance carried by the all-channels-together direction.

    Project the covariance onto the normalised all-ones vector and compare that
    to the total variance. Returns a number in [0, 1].
    """
    n = C.shape[0]
    u = np.ones(n) / np.sqrt(n)
    return float((u @ C @ u) / np.trace(C))''')

m.code('''# --- TEST CELL FOR STEP 3 ---
M_VERT = np.zeros((7, 8))
for _r, (_p, _mn) in enumerate([(1, 0), (2, 0), (3, 0), (4, 7), (5, 7), (6, 7), (7, 0)]):
    M_VERT[_r, _p] = 1.0
    M_VERT[_r, _mn] = -1.0

print(f"{'reference sd':>13} {'mean |r|':>10} {'sd of |r|':>11} {'common mode':>13} {'after montage':>15}")
rows = {}
for ref_sd in (0.0, 1.0, 3.0, 10.0):
    Xr = Xmix[:, :40000] + ref_sd * rng.standard_normal(40000)[None, :]
    Cr = sample_covariance(Xr)
    corr = Cr / np.sqrt(np.outer(np.diag(Cr), np.diag(Cr)))
    off = np.abs(corr[~np.eye(8, dtype=bool)])
    cm = common_mode_fraction(Cr)
    cm_after = common_mode_fraction(sample_covariance(M_VERT @ Xr))
    rows[ref_sd] = (float(np.mean(off)), float(np.std(off)), cm, cm_after)
    print(f"{ref_sd:>13.1f} {np.mean(off):>10.3f} {np.std(off):>11.3f} {cm:>13.1%} {cm_after:>15.1%}")

# The signature: a shared reference raises the mean correlation and COLLAPSES its
# spread, because it adds the same thing to every pair.
assert rows[10.0][0] > rows[0.0][0], "a shared reference raises mean correlation"
assert rows[10.0][1] < rows[0.0][1], "and collapses the spread between pairs"
assert rows[10.0][2] > 0.9, "at this amplitude it dominates the variance"

# A montage whose rows sum to zero removes the reference entirely. The test is not
# that the number goes to zero, it is that the number stops depending on the
# reference at all: identical to machine precision across a 10x amplitude range.
# The bound is 1e-12 rather than something comfortable because the measured spread
# is 2.8e-17, and a bound loose enough to pass under a real leak tests nothing.
after = [rows[k][3] for k in rows]
assert max(after) - min(after) < 1e-12, (
    f"after a zero-sum montage the reference must leave no trace; got spread {max(after)-min(after):.2e}"
)
assert rows[10.0][3] < 0.25 * rows[10.0][2], "and it must be far below the unreferenced value"

# The residual is not the reference. Several derivations subtract the SAME contact,
# so they share a term of their own. That is visible in the montage matrix alone,
# with no data involved, so measure it here rather than asserting it.
_shared = [r for r in range(7) if M_VERT[r, 0] == -1.0]
_rowcorr = np.corrcoef(M_VERT)
_pairs = [_rowcorr[i, j] for i in _shared for j in _shared if i < j]
print(f"\\ncommon mode remaining after the montage: {rows[10.0][3]:.1%}, at every reference level")
print("That residual is not the amplifier reference, which is gone. It is Ring 1:")
print(f"{len(_shared)} of these seven derivations subtract it in common, which correlates")
print(f"their rows at exactly {np.mean(_pairs):.2f} before any data is recorded.")
assert len(_shared) == 4, "four derivations reference Ring 1 in this montage"
assert abs(np.mean(_pairs) - 0.5) < 1e-9, (
    "two rows sharing one of their two entries correlate at 0.5 by construction"
)
print("\\nStep 3 passed. Rising mean correlation with collapsing spread is the")
print("fingerprint of a moving reference, and it is what G1 thresholds on.")''')

m.md(r'''---

## 4. When the estimate itself is the problem

Everything above assumed the covariance was known. It is estimated, from $T$
samples, and the estimate has its own failure mode that has nothing to do with
the brain.

$\hat{\Sigma}$ is built from $T$ outer products of $C$-dimensional vectors, so its
rank is at most $\min(C, T-1)$. With fewer samples than channels it is
**singular by construction**, and LIN 3 established that a singular matrix
does not raise when you invert it. Even above that threshold, the estimate is
badly conditioned until $T$ is many times $C$, and every method that inverts a
covariance, which includes beamforming, whitening, and the spatial filters in
LIN 6, inherits that conditioning.

The standard repair is **shrinkage**: pull the estimate toward a well-conditioned
target, usually a scaled identity.

$$\hat{\Sigma}_{\alpha} = (1-\alpha)\hat{\Sigma} + \alpha \frac{\text{tr}(\hat{\Sigma})}{C} I$$

This is biased on purpose. It trades a little accuracy in the well-estimated
directions for a large gain in the badly estimated ones, which is the same
bargain LIN 3 made with Tikhonov.''')

m.task(
'''def shrink_covariance(C: np.ndarray, alpha: float) -> np.ndarray:
    """Linear shrinkage toward a scaled identity with the same average variance.

    Production equivalent: `sklearn.covariance.LedoitWolf`, which estimates alpha
    from the data rather than taking it as an argument, and
    `mne.compute_covariance(..., method='shrunk')`.
    """
    # TODO: the target is (trace(C) / n_channels) * I, which matches C's average variance
    # TODO: return the convex combination (1 - alpha) * C + alpha * target
    raise NotImplementedError("Implement shrink_covariance")''',
'''def shrink_covariance(C: np.ndarray, alpha: float) -> np.ndarray:
    """Linear shrinkage toward a scaled identity with the same average variance.

    Production equivalent: `sklearn.covariance.LedoitWolf`, which estimates alpha
    from the data rather than taking it as an argument, and
    `mne.compute_covariance(..., method='shrunk')`.
    """
    n = C.shape[0]
    target = (np.trace(C) / n) * np.eye(n)
    return (1.0 - alpha) * C + alpha * target''')

m.code('''# --- TEST CELL FOR STEP 4 ---
n_ch = 32
truth = np.eye(n_ch) + 0.4 * np.ones((n_ch, n_ch))    # a known, well-conditioned target
root = np.linalg.cholesky(truth)

print(f"{'samples T':>10} {'rank':>6} {'condition number':>18} {'inv raises?':>12}")
conds = {}
for T_n in (16, 32, 64, 256, 4096):
    Xs = root @ rng.standard_normal((n_ch, T_n))
    Cs = sample_covariance(Xs)
    conds[T_n] = np.linalg.cond(Cs)
    try:
        np.linalg.inv(Cs)
        raised = "no"
    except np.linalg.LinAlgError:
        raised = "yes"
    print(f"{T_n:>10} {np.linalg.matrix_rank(Cs):>6} {conds[T_n]:>18.3e} {raised:>12}")

assert np.linalg.matrix_rank(sample_covariance(root @ rng.standard_normal((n_ch, 16)))) < n_ch, \\
    "fewer samples than channels gives a rank-deficient estimate"
assert conds[4096] < conds[64] < conds[32], "conditioning improves as T grows"

# Shrinkage repairs the conditioning of the worst case.
C_bad = sample_covariance(root @ rng.standard_normal((n_ch, 16)))
print(f"\\n{'alpha':>7} {'condition number':>18} {'error vs truth':>16}")
for alpha in (0.0, 0.01, 0.1, 0.3):
    Cs = shrink_covariance(C_bad, alpha)
    kappa = np.linalg.cond(Cs)
    err_t = np.linalg.norm(Cs - truth) / np.linalg.norm(truth)
    print(f"{alpha:>7.2f} {kappa:>18.3e} {err_t:>15.1%}")

assert np.linalg.cond(shrink_covariance(C_bad, 0.1)) < 1e-3 * np.linalg.cond(C_bad), \\
    "shrinkage must fix the conditioning by orders of magnitude"
assert np.trace(shrink_covariance(C_bad, 0.5)) == np.trace(C_bad) or \\
    np.isclose(np.trace(shrink_covariance(C_bad, 0.5)), np.trace(C_bad)), \\
    "shrinkage toward a trace-matched target preserves total variance"
print("\\nStep 4 passed. Shrinkage preserves total variance and buys conditioning")
print("with bias, which is the same trade LIN 3 made with Tikhonov.")''')

m.md(r'''---

## 5. What you established

1. $\hat{\Sigma} = X_c X_c^{\top} / (T-1)$, and the $T-1$ removes a bias that is
   exactly $(T-1)/T$, which you measured rather than accepted.
2. $\Sigma_X = A\Sigma_S A^{\top} + \Sigma_N$. Even with **zero** coupling
   between sources, contacts in a shared volume conductor come out correlated at
   a median of about $0.42$, rising to $0.97$ for the closest pairs, while the
   sources themselves correlate at $0.001$. Correlation between contacts is the
   resting state of an electrode array, and observing it is not a finding.
3. A shared reference adds a rank-one term that raises mean correlation from
   $0.47$ to $0.99$ while collapsing its spread from $0.31$ to $0.007$. That pair
   of movements is the fingerprint guardrail G1 thresholds on. A zero-sum montage
   removes it completely: the common-mode fraction of the derivations is
   identical to machine precision, a spread of 3e-17, across a tenfold change in
   reference amplitude. What remains, 18 percent, is not the reference but Ring 1,
   which four of the seven derivations subtract in common, correlating their rows
   at exactly 0.5 before any data is recorded.
4. A covariance estimated from fewer samples than channels is singular by
   construction, and LIN 3 established that it will not tell you so.
   Shrinkage restores conditioning and preserves total variance.

### Exercises

**Exercise 1.** Section 2 used $A_{ij} = 1/(1 + d^2)$. Replace it with the
monopole kernel from LIN 3, $1/(4\pi\sigma d)$, and recompute the median
inter-contact correlation. Does the conclusion depend on the kernel, or only on
the fact that the columns of $A$ are not orthogonal?

**Exercise 2.** Section 3 detected a shared reference from the mean and spread of
the off-diagonal correlations. Construct genuine, physiological synchronisation
that raises the mean by the same amount, and show that the spread behaves
differently. What does that tell you about the reliability of G1's threshold?

**Exercise 3.** For $C = 32$ channels, find the smallest $T$ at which the
unshrunk condition number falls below $10^3$. Express your answer as a multiple
of $C$, and then say what that implies for estimating a covariance per condition
from short intraoperative recordings.

---

**Next: LIN 5, eigendecomposition and principal component analysis.** It takes the
covariance built here and asks what its eigenvectors are, and whether they are
the sources.
''')

m.emit()
ns = verify("01_linear_algebra", "04_covariance_volume_conduction")
print("  LIN 4 OK, symbols:", [k for k in ("sample_covariance", "predicted_covariance",
      "common_mode_fraction", "shrink_covariance") if k in ns])
