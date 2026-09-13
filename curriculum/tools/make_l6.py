import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("01_linear_algebra", "06_generalized_eigendecomposition")

m.md(r'''# Lesson LIN 6: Generalised Eigendecomposition and Spatial Filters {{VARIANT}}

**Foundations · Applied Linear Algebra for Neural Arrays · final lesson**

{{INSTRUCTIONS}}

LIN 5 ended on a complaint: PCA maximises variance, and the largest thing in an
intracranial recording is almost never the interesting thing. It is the
reference, or the stimulation artifact, or whichever source happens to sit
closest to a contact.

The fix is to stop asking for the biggest signal and start asking for the biggest
**difference between two conditions**. That single change turns an ill-posed
question into a well-posed one, and the linear algebra that answers it is a small
extension of LIN 5.

**What it assumes**

| From | What is used |
|---|---|
| LIN 4 | The mixing model, and shrinkage for a covariance that cannot be inverted. |
| LIN 5 | $\Sigma = V\Lambda V^{\top}$, `jacobi_eigh`, and the rotation ambiguity that made PCA unable to name a source. |
| LIN 3 | Condition number, and that a near-singular matrix inverts without complaint. |

**What it underwrites**

The `bandpower_contrast` recipe compares a condition against its control.
Guardrail **G11** requires that control to exist. This module is why the contrast
is the scientifically meaningful object and the single condition is not.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(17)

def sample_covariance(X):
    """From LIN 4."""
    Xc = X - X.mean(axis=1, keepdims=True)
    return (Xc @ Xc.T) / (X.shape[1] - 1)

def jacobi_eigh(C, sweeps=100):
    """From LIN 5. Eigenvalues descending, eigenvectors in columns."""
    A = np.array(C, dtype=float, copy=True)
    n = A.shape[0]
    V = np.eye(n)
    for _ in range(sweeps):
        if np.sum(np.triu(A, 1) ** 2) < 1e-30:
            break
        for p in range(n):
            for q in range(p + 1, n):
                if abs(A[p, q]) < 1e-300:
                    continue
                theta = (A[q, q] - A[p, p]) / (2.0 * A[p, q])
                sign = 1.0 if theta >= 0 else -1.0
                t = sign / (abs(theta) + np.sqrt(theta * theta + 1.0))
                c = 1.0 / np.sqrt(t * t + 1.0)
                s = t * c
                G = np.eye(n); G[p, p] = c; G[q, q] = c; G[p, q] = s; G[q, p] = -s
                A = G.T @ A @ G
                V = V @ G
    order = np.argsort(np.diag(A))[::-1]
    return np.diag(A)[order], V[:, order]

print("Environment initialized for Lesson LIN 6")''')

m.md(r'''---

## 1. A better objective

A spatial filter is a weight vector $w$ producing one virtual channel
$y(t) = w^{\top}x(t)$. Its variance under a covariance $\Sigma$ is
$w^{\top}\Sigma w$.

PCA maximises $w^{\top}\Sigma w$ subject to $\|w\|=1$. Instead, take two
conditions, with covariances $\Sigma_S$ from the condition of interest and
$\Sigma_N$ from its control, and maximise the **ratio**:

$$R(w) = \frac{w^{\top}\Sigma_S\, w}{w^{\top}\Sigma_N\, w}$$

This is the Rayleigh quotient. It has two properties that matter here. It is
scale invariant, $R(cw) = R(w)$, so there is no normalisation constraint to
impose. And setting its gradient to zero gives

$$\Sigma_S w = \lambda\, \Sigma_N w$$

a **generalised** eigenvalue problem whose largest $\lambda$ is the largest
achievable ratio, attained at its eigenvector.

Anything present in both conditions, the reference, the artifact, the anatomy,
appears in $\Sigma_S$ and $\Sigma_N$ alike and cancels in the ratio. That is the
whole trick.''')

m.task(
'''def rayleigh_quotient(w: np.ndarray, C_s: np.ndarray, C_n: np.ndarray) -> float:
    """Ratio of variance under C_s to variance under C_n, for filter `w`."""
    # TODO: numerator is w.T @ C_s @ w, denominator is w.T @ C_n @ w
    raise NotImplementedError("Implement rayleigh_quotient")''',
'''def rayleigh_quotient(w: np.ndarray, C_s: np.ndarray, C_n: np.ndarray) -> float:
    """Ratio of variance under C_s to variance under C_n, for filter `w`."""
    return float((w @ C_s @ w) / (w @ C_n @ w))''')

m.md(r'''### Solving it by whitening

The generalised problem reduces to an ordinary one. Factor
$\Sigma_N = U D U^{\top}$ with LIN 5's routine and build the inverse square root
$\Sigma_N^{-1/2} = U D^{-1/2} U^{\top}$. Then

$$\Sigma_S w = \lambda \Sigma_N w
\;\Longleftrightarrow\;
\underbrace{\Sigma_N^{-1/2}\Sigma_S\Sigma_N^{-1/2}}_{\text{symmetric}} u = \lambda u,
\qquad w = \Sigma_N^{-1/2}u$$

That $D^{-1/2}$ is where this becomes dangerous. It divides by the square roots
of the eigenvalues of the control covariance, so a direction the control barely
sampled is amplified enormously, and LIN 4 showed that with $T$ near $C$ the
smallest eigenvalues are estimation noise. LIN 3 showed the inversion will
not warn you. Shrinkage is not optional here.''')

m.task(
'''def ged(C_s: np.ndarray, C_n: np.ndarray, alpha: float = 0.01):
    """Generalised eigendecomposition of (C_s, C_n), largest ratio first.

    `alpha` shrinks C_n toward a scaled identity before inverting it, as in LIN 4.

    Returns (ratios, filters, C_n_used) with filters in COLUMNS. `C_n_used` is the
    SHRUNK denominator, returned because it is the matrix the ratios are actually
    ratios against; see the test cell.

    Production equivalent: `scipy.linalg.eigh(C_s, C_n)`. In MNE the same
    algebra appears as CSP (`mne.decoding.CSP`) and in xDAWN.
    """
    # TODO: shrink C_n toward (trace(C_n)/n) * I by alpha, as in LIN 4
    # TODO: eigendecompose the shrunk C_n with jacobi_eigh
    # TODO: build C_n^{-1/2} = U diag(d ** -0.5) U.T
    # TODO: symmetrically whiten C_s, eigendecompose that, and map back: w = C_n^{-1/2} u
    # TODO: return the shrunk C_n alongside, since that is the true denominator
    raise NotImplementedError("Implement ged")''',
'''def ged(C_s: np.ndarray, C_n: np.ndarray, alpha: float = 0.01):
    """Generalised eigendecomposition of (C_s, C_n), largest ratio first.

    `alpha` shrinks C_n toward a scaled identity before inverting it, as in LIN 4.

    Returns (ratios, filters, C_n_used) with filters in COLUMNS. `C_n_used` is the
    SHRUNK denominator, returned because it is the matrix the ratios are actually
    ratios against; see the test cell.

    Production equivalent: `scipy.linalg.eigh(C_s, C_n)`. In MNE the same
    algebra appears as CSP (`mne.decoding.CSP`) and in xDAWN.
    """
    n = C_n.shape[0]
    target = (np.trace(C_n) / n) * np.eye(n)
    C_reg = (1.0 - alpha) * C_n + alpha * target

    d, U = jacobi_eigh(C_reg)
    d = np.clip(d, 1e-300, None)
    whiten = U @ np.diag(d ** -0.5) @ U.T

    lam, u = jacobi_eigh(whiten @ C_s @ whiten)
    return lam, whiten @ u, C_reg''')

m.code('''# --- TEST CELL FOR STEP 1 ---
# 8 contacts, 3 sources. During the task condition, source 1 alone gets stronger.
contact_mm = np.linspace(0, 7.0, 8)
source_mm = np.array([1.0, 3.5, 6.0])
A_mix = 1.0 / (1.0 + np.abs(contact_mm[:, None] - source_mm[None, :]) ** 2)
TARGET = 0                                   # the source that changes

REST_VAR = np.array([1.0, 3.0, 2.0])         # source 1 is NOT the largest at rest
TASK_VAR = np.array([4.0, 3.0, 2.0])         # and only source 1 changes
T = 60000
REF_SD = 6.0                                 # a large shared reference, present in both

def record(var):
    S = rng.standard_normal((3, T)) * np.sqrt(var)[:, None]
    ref = REF_SD * rng.standard_normal(T)
    return A_mix @ S + ref[None, :] + 0.2 * rng.standard_normal((8, T))

X_task, X_rest = record(TASK_VAR), record(REST_VAR)
C_s, C_n = sample_covariance(X_task), sample_covariance(X_rest)

ratios, filters, C_n_used = ged(C_s, C_n)

# (a) Each eigenvalue must equal the Rayleigh quotient of its own eigenvector. This
# checks the solver against the objective it claims to optimise, not against
# another solver. Note the denominator: C_n_used, not C_n.
for i in range(len(ratios)):
    r = rayleigh_quotient(filters[:, i], C_s, C_n_used)
    assert np.isclose(r, ratios[i], rtol=1e-6), f"filter {i}: ratio {r:.6f} != eigenvalue {ratios[i]:.6f}"

# Shrinkage changed the OBJECTIVE, not only the arithmetic. Against the unshrunk
# covariance the same filter achieves a different, larger ratio. Report the one you
# actually optimised.
r_shrunk = rayleigh_quotient(filters[:, 0], C_s, C_n_used)
r_raw = rayleigh_quotient(filters[:, 0], C_s, C_n)
print(f"top filter, ratio against the shrunk C_n   : {r_shrunk:.4f}  <- the eigenvalue")
print(f"top filter, ratio against the original C_n : {r_raw:.4f}")
assert not np.isclose(r_shrunk, r_raw, rtol=1e-3), (
    "with alpha > 0 these must differ; a report that conflates them overstates the result"
)
# With alpha = 0 there is no shrinkage and the two coincide exactly.
r0, f0, cn0 = ged(C_s, C_n, alpha=0.0)
assert np.allclose(cn0, C_n), "alpha=0 must leave the denominator untouched"
assert np.isclose(rayleigh_quotient(f0[:, 0], C_s, C_n), r0[0], rtol=1e-6)

# (b) the top filter must beat every random filter, since it is the maximiser.
best_random = max(rayleigh_quotient(rng.standard_normal(8), C_s, C_n_used) for _ in range(20000))
print(f"top GED ratio             : {ratios[0]:.4f}")
print(f"best of 20000 random filters: {best_random:.4f}")
assert ratios[0] > best_random, "the top eigenvector must maximise the quotient"

# (c) and it must agree with scipy's generalised solver.
from scipy.linalg import eigh as scipy_eigh
ref_ratios = np.sort(scipy_eigh(C_s, C_n_used, eigvals_only=True))[::-1]
assert np.allclose(ratios, ref_ratios, rtol=1e-3), "must agree with scipy.linalg.eigh(C_s, C_n_used)"
print(f"\\nratios: {np.round(ratios, 4)}")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. What the filter found, and what PCA found instead

The comparison that matters is against LIN 5. Both methods return a spatial
direction. PCA returns the direction of greatest variance in the task condition;
GED returns the direction of greatest task-to-rest ratio.

The recording below contains a shared reference six times larger than anything
physiological, and the source that actually changes between conditions is not the
largest source even at task. This is the ordinary situation, not an adversarial
one.

The true answer is known: the spatial pattern of the changing source is column
`TARGET` of the mixing matrix. So both methods can simply be scored against it.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
def alignment_deg(vec, target):
    """Angle between two directions, ignoring sign."""
    c = abs(float(vec @ target) / (np.linalg.norm(vec) * np.linalg.norm(target)))
    return float(np.degrees(np.arccos(min(1.0, c))))

true_pattern = A_mix[:, TARGET]
ones_dir = np.ones(8)

# GED returns a FILTER. Its spatial PATTERN is C_n @ w, which is what to compare
# against a mixing column; the filter itself is the inverse-model row.
ged_pattern = C_n_used @ filters[:, 0]

pca_vals, pca_vecs = jacobi_eigh(C_s)
pca_pattern = pca_vecs[:, 0]

print(f"{'method':>22} {'angle to true source':>22} {'angle to reference':>20}")
for name, pat in (("PCA on task data", pca_pattern), ("GED task vs rest", ged_pattern)):
    print(f"{name:>22} {alignment_deg(pat, true_pattern):>19.1f} deg "
          f"{alignment_deg(pat, ones_dir):>17.1f} deg")

assert alignment_deg(pca_pattern, ones_dir) < 10.0, \\
    "PCA should lock onto the reference, which is the largest thing present"
assert alignment_deg(ged_pattern, true_pattern) < 15.0, \\
    "GED should recover the source that actually changed"
assert alignment_deg(ged_pattern, true_pattern) < alignment_deg(pca_pattern, true_pattern), \\
    "GED must beat PCA at finding the changing source"

# Now the practical figure: variance ratio achieved by each virtual channel.
def achieved_ratio(w):
    return rayleigh_quotient(w, C_s, C_n_used)

best_channel = max(range(8), key=lambda i: C_s[i, i] / C_n[i, i])
print(f"\\n{'virtual channel':>22} {'task/rest variance ratio':>26}")
print(f"{'best single contact':>22} {C_s[best_channel, best_channel] / C_n[best_channel, best_channel]:>25.3f}")
print(f"{'PCA component 1':>22} {achieved_ratio(pca_pattern):>25.3f}")
print(f"{'GED filter 1':>22} {achieved_ratio(filters[:, 0]):>25.3f}")
assert achieved_ratio(filters[:, 0]) > 2 * (C_s[best_channel, best_channel] / C_n[best_channel, best_channel]), \\
    "the spatial filter must substantially beat the best single contact"
# Shrinkage is insurance, and insurance has a premium. This control condition has
# 60000 samples of 8 channels, so C_n is well estimated and there is little to
# insure against. Over-shrinking here throws away the answer.
print(f"\\n{'alpha':>7} {'top ratio':>11} {'angle to true source':>22}")
for a in (0.0, 0.01, 0.05, 0.2):
    lam_a, w_a, cn_a = ged(C_s, C_n, alpha=a)
    print(f"{a:>7.2f} {lam_a[0]:>11.3f} {alignment_deg(cn_a @ w_a[:, 0], true_pattern):>19.1f} deg")

lam_lo, w_lo, cn_lo = ged(C_s, C_n, alpha=0.0)
lam_hi, w_hi, cn_hi = ged(C_s, C_n, alpha=0.2)
assert alignment_deg(cn_lo @ w_lo[:, 0], true_pattern) < 5.0, \\
    "with plentiful data and no shrinkage the recovery should be nearly exact"
assert alignment_deg(cn_hi @ w_hi[:, 0], true_pattern) > 30.0, \\
    "and over-shrinking should visibly destroy it"
print("\\nkappa(C_n) here is {:.1e}, which needs no rescue. Section 3 is the case that does.".format(
    np.linalg.cond(C_n)))
print("\\nStep 2 passed. PCA reported the amplifier. GED reported the source that changed,")
print("without being told anything except which samples were task and which were rest.")''')

m.md(r'''---

## 3. Where it breaks, and why LIN 4 is a prerequisite

The whitening step inverts $\Sigma_N$. LIN 4 established that a covariance estimated
from $T$ samples has rank at most $\min(C, T-1)$, so with a short control
condition, which is the normal case intraoperatively, $\Sigma_N$ is singular or
nearly so. LIN 3 established that inverting it raises nothing.

The failure is therefore silent and it is spectacular: the filter that maximises
the ratio becomes the one pointing at whichever direction the control condition
happened to sample least. The eigenvalue is enormous, the result looks like a
triumphant discovery, and it is noise.

Below, the length of the control condition is varied with everything else held
fixed. Watch two columns rather than one. The ratio is what a paper would report;
the angle is whether the answer is right.''')

m.code('''print(f"{'control samples':>16} {'kappa(C_n)':>12} {'top ratio':>11} {'angle to true':>15} {'alpha':>7}")
for T_n in (10, 30, 200, 20000):
    Xn_short = record(REST_VAR)[:, :T_n]
    Cn_short = sample_covariance(Xn_short)
    for alpha in (0.0, 0.05):
        lam_s, w_s, cn_used = ged(C_s, Cn_short, alpha=alpha)
        ang = alignment_deg(cn_used @ w_s[:, 0], true_pattern)
        print(f"{T_n:>16} {np.linalg.cond(Cn_short):>12.2e} {lam_s[0]:>11.3g} "
              f"{ang:>12.1f} deg {alpha:>7.2f}")

# Unregularised, a control shorter than the channel count gives an absurd ratio
# from a direction it never sampled.
_Cn10 = sample_covariance(record(REST_VAR)[:, :10])
lam_bad, _, _ = ged(C_s, _Cn10, alpha=0.0)
lam_ok, w_ok, _ = ged(C_s, _Cn10, alpha=0.05)
print(f"\\nunregularised top ratio with 10 control samples: {lam_bad[0]:.3g}")
print(f"regularised   top ratio with 10 control samples: {lam_ok[0]:.3g}")
assert lam_bad[0] > 10 * lam_ok[0], "without shrinkage the ratio is meaningless and huge"
assert np.isfinite(lam_ok[0]), "with shrinkage it stays finite"

# The uncomfortable part. Shrinkage stopped the ratio from being absurd. It did NOT
# recover the source: with ten control samples both angles sit near 49 degrees,
# which is no better than guessing.
ang_bad = alignment_deg(_Cn10 @ ged(C_s, _Cn10, alpha=0.0)[1][:, 0], true_pattern)
ang_ok = alignment_deg(ged(C_s, _Cn10, alpha=0.05)[2] @ ged(C_s, _Cn10, alpha=0.05)[1][:, 0],
                       true_pattern)
print(f"\\nangle to the true source, 10 control samples, alpha=0.00 : {ang_bad:.1f} deg")
print(f"angle to the true source, 10 control samples, alpha=0.05 : {ang_ok:.1f} deg")
assert ang_bad > 40 and ang_ok > 40, "neither setting recovers the source from ten samples"
print("\\nA ratio of {:.0f} looks like the best result anyone ever got. It is the".format(lam_bad[0]))
print("reciprocal of an eigenvalue estimated from ten samples of eight channels.")
print("Shrinkage stopped the number from looking spectacular. It did not make the")
print("answer right, and nothing could have: the control condition never sampled the")
print("directions the filter needed. The fix is a longer control, not a better solver.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established, and what Linear Algebra established

1. Maximising $w^{\top}\Sigma_S w / w^{\top}\Sigma_N w$ gives the generalised
   problem $\Sigma_S w = \lambda\Sigma_N w$, solved by whitening with
   $\Sigma_N^{-1/2}$. You verified each eigenvalue against the Rayleigh quotient
   of its own eigenvector, and beat twenty thousand random filters.
2. With a shared reference six times larger than the physiology, PCA returns the
   reference and GED returns the source that changed. Whatever is common to both
   conditions cancels in the ratio, which is why a contrast is the meaningful
   object and a single condition is not. That is guardrail G11 as linear algebra.
3. The whitening step inverts the control covariance, so LIN 4's shrinkage is a
   prerequisite rather than a refinement. Without it, a short control produces an
   enormous ratio from a direction it never sampled, silently. But shrinkage is
   insurance with a premium: on a well-estimated covariance, $\alpha = 0$
   recovers the source to $0.1$ degrees and $\alpha = 0.2$ misses it by $46$.
   The parameter belongs in the run record, because the result depends on it.

**Linear Algebra is complete.** LIN 1 established that a dot product is a projection. LIN 2
made a montage a matrix. LIN 3 showed that inverting a matrix built from nearby
contacts amplifies noise without warning. LIN 4 showed that volume conduction fills
the covariance whether or not anything is coupled. LIN 5 showed that its
eigenvectors are a subspace and not a set of sources. LIN 6 showed what to ask
instead.

### Exercises

**Exercise 1.** GED filters are $\Sigma_N$-orthogonal rather than orthonormal.
Verify that $w_i^{\top}\Sigma_N w_j = 0$ for $i \ne j$, and explain why that,
rather than ordinary orthogonality, is the right notion here.

**Exercise 2.** Section 2 scored the pattern as $\Sigma_N w$. Score $\Sigma_S w$
instead and see whether the answer changes. Then explain the difference between a
spatial filter and a spatial pattern, and which of the two may be interpreted
anatomically.

**Exercise 3.** Swap the conditions, computing GED of rest against task. Show
that the eigenvalues are the reciprocals of the originals and the filters are
unchanged. What does that imply about a study that reports only the filter with
the largest eigenvalue?
''')

m.emit()
ns = verify("01_linear_algebra", "06_generalized_eigendecomposition")
print("  LIN 6 OK, symbols:", [k for k in ("ged", "rayleigh_quotient", "jacobi_eigh") if k in ns])
