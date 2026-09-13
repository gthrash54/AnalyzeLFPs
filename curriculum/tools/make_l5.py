import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("01_linear_algebra", "05_eigendecomposition_pca")

m.md(r'''# Lesson LIN 5: Eigendecomposition and Principal Component Analysis {{VARIANT}}

**Foundations · Applied Linear Algebra for Neural Arrays**

{{INSTRUCTIONS}}

LIN 4 built the covariance matrix and showed that volume conduction fills its
off-diagonal. This module asks what its eigenvectors are, and then answers the
question everyone actually wants answered, which is whether they are the sources.

They are not, and the reason is worth more than the technique.

**What it assumes**

| From | What is used |
|---|---|
| LIN 4 | $\hat{\Sigma} = X_cX_c^{\top}/(T-1)$, the mixing model $\Sigma_X = A\Sigma_SA^{\top}+\Sigma_N$, and shrinkage. |
| LIN 3 | Condition number, and that a rank-deficient matrix inverts silently. |
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(11)

def sample_covariance(X):
    """From LIN 4, restated so this notebook runs standalone."""
    Xc = X - X.mean(axis=1, keepdims=True)
    return (Xc @ Xc.T) / (X.shape[1] - 1)

print("Environment initialized for Lesson LIN 5")''')

m.md(r'''---

## 1. Eigendecomposition of a covariance matrix

A covariance matrix is symmetric and positive semi-definite, which buys two
guarantees that do not hold for general matrices: its eigenvalues are real and
non-negative, and its eigenvectors can be chosen orthonormal. So

$$\Sigma = V \Lambda V^{\top}, \qquad V^{\top}V = I, \qquad \lambda_i \ge 0$$

Each $\lambda_i$ is the variance of the data projected onto $v_i$, because
$v_i^{\top}\Sigma v_i = \lambda_i$. Since the trace is preserved under this
rotation, $\sum_i \lambda_i = \text{tr}(\Sigma)$ is the total variance, and the
eigenvalues partition it.

We build this with the cyclic Jacobi rotation method rather than calling a
library, because the algorithm is short and makes the orthogonality explicit: it
repeatedly applies a rotation that zeroes one off-diagonal entry, and the product
of those rotations is $V$.''')

m.task(
'''def jacobi_eigh(C: np.ndarray, sweeps: int = 100):
    """Eigenvalues and eigenvectors of a symmetric matrix, largest first.

    Returns (eigenvalues, eigenvectors) with eigenvectors in COLUMNS, so that
    C @ V[:, i] == eigenvalues[i] * V[:, i].

    Production equivalent: `np.linalg.eigh`, which you should use in real code.
    """
    # TODO: copy C into A, and start V as the identity
    # TODO: repeat sweeps: for each pair p < q, build the rotation that zeroes A[p, q]
    #       theta = (A[q,q] - A[p,p]) / (2 * A[p,q])
    #       t = sign(theta) / (|theta| + sqrt(theta^2 + 1)), c = 1/sqrt(t^2+1), s = t*c
    # TODO: apply the rotation to A on both sides, and accumulate it into V
    # TODO: sort by eigenvalue descending and return
    raise NotImplementedError("Implement jacobi_eigh")''',
'''def jacobi_eigh(C: np.ndarray, sweeps: int = 100):
    """Eigenvalues and eigenvectors of a symmetric matrix, largest first.

    Returns (eigenvalues, eigenvectors) with eigenvectors in COLUMNS, so that
    C @ V[:, i] == eigenvalues[i] * V[:, i].

    Production equivalent: `np.linalg.eigh`, which you should use in real code.
    """
    A = np.array(C, dtype=float, copy=True)
    n = A.shape[0]
    V = np.eye(n)
    for _ in range(sweeps):
        off = np.sum(np.triu(A, 1) ** 2)
        if off < 1e-30:
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
                G = np.eye(n)
                G[p, p] = c; G[q, q] = c; G[p, q] = s; G[q, p] = -s
                A = G.T @ A @ G
                V = V @ G
    order = np.argsort(np.diag(A))[::-1]
    return np.diag(A)[order], V[:, order]''')

m.code('''# --- TEST CELL FOR STEP 1 ---
A_test = rng.standard_normal((6, 6))
C_test = A_test @ A_test.T                      # symmetric positive semi-definite

vals, vecs = jacobi_eigh(C_test)

# (a) the defining property, checked directly rather than against another routine
for i in range(len(vals)):
    residual = np.max(np.abs(C_test @ vecs[:, i] - vals[i] * vecs[:, i]))
    assert residual < 1e-8, f"eigenpair {i} does not satisfy C v = lambda v (residual {residual:.2e})"

# (b) orthonormality, which is what makes this a rotation
assert np.allclose(vecs.T @ vecs, np.eye(6), atol=1e-9), "eigenvectors must be orthonormal"

# (c) reconstruction, and the trace identity
assert np.allclose(vecs @ np.diag(vals) @ vecs.T, C_test, atol=1e-8), "V L V.T must rebuild C"
assert np.isclose(np.sum(vals), np.trace(C_test)), "eigenvalues must partition the total variance"

# (d) and only now, agreement with the library
ref = np.sort(np.linalg.eigvalsh(C_test))[::-1]
assert np.allclose(vals, ref, atol=1e-8), "must agree with np.linalg.eigh"

print(f"eigenvalues: {np.round(vals, 4)}")
print(f"max |C v - lambda v| over all pairs : {max(np.max(np.abs(C_test @ vecs[:, i] - vals[i] * vecs[:, i])) for i in range(6)):.2e}")
print(f"orthonormality error                : {np.max(np.abs(vecs.T @ vecs - np.eye(6))):.2e}")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. PCA is a rotation, and variance explained is a ratio

Principal component analysis is nothing more than expressing the data in the
eigenbasis of its own covariance:

$$Y = V^{\top} X_c$$

Because $V$ is orthonormal this is a rigid rotation: no information is created or
destroyed, and the total variance is unchanged. What changes is the coordinate
system. In the new one the covariance is diagonal, so the components are
uncorrelated, and they are ordered so that the first carries the most variance
available in any single direction.

"Variance explained" by the first $k$ components is then just

$$\frac{\sum_{i=1}^{k}\lambda_i}{\sum_{i=1}^{C}\lambda_i}$$

Note what this quantity is not. It is a statement about how concentrated the
variance is, not about how many things are happening in the brain.''')

m.task(
'''def pca_project(X: np.ndarray, V: np.ndarray, k: int) -> np.ndarray:
    """Project centred data onto the first `k` principal directions.

    Returns `[k, n_samples]`. Production equivalent: `sklearn.decomposition.PCA`,
    or `mne.decoding.UnsupervisedSpatialFilter`.
    """
    # TODO: centre X along time
    # TODO: project with the first k eigenvector COLUMNS: V[:, :k].T @ Xc
    raise NotImplementedError("Implement pca_project")


def variance_explained(eigenvalues: np.ndarray, k: int) -> float:
    """Fraction of total variance carried by the first `k` components."""
    # TODO: ratio of the first k eigenvalues to all of them
    raise NotImplementedError("Implement variance_explained")''',
'''def pca_project(X: np.ndarray, V: np.ndarray, k: int) -> np.ndarray:
    """Project centred data onto the first `k` principal directions.

    Returns `[k, n_samples]`. Production equivalent: `sklearn.decomposition.PCA`,
    or `mne.decoding.UnsupervisedSpatialFilter`.
    """
    Xc = X - X.mean(axis=1, keepdims=True)
    return V[:, :k].T @ Xc


def variance_explained(eigenvalues: np.ndarray, k: int) -> float:
    """Fraction of total variance carried by the first `k` components."""
    return float(np.sum(eigenvalues[:k]) / np.sum(eigenvalues))''')

m.code('''# --- TEST CELL FOR STEP 2 ---
# LIN 4's mixing model: 3 uncorrelated sources into 8 contacts.
contact_mm = np.linspace(0, 7.0, 8)
source_mm = np.array([1.0, 3.5, 6.0])
A_mix = 1.0 / (1.0 + np.abs(contact_mm[:, None] - source_mm[None, :]) ** 2)
SOURCE_VAR = np.array([4.0, 1.0, 2.25])

T = 60000
S_true = rng.standard_normal((3, T)) * np.sqrt(SOURCE_VAR)[:, None]
X = A_mix @ S_true + 0.2 * rng.standard_normal((8, T))

C = sample_covariance(X)
vals, vecs = jacobi_eigh(C)
Y = pca_project(X, vecs, 8)

# The rotation preserves total variance exactly. That is the whole claim.
assert np.isclose(np.sum(np.var(Y, axis=1, ddof=1)), np.trace(C), rtol=1e-6), \\
    "an orthonormal rotation cannot change total variance"

# Components are uncorrelated by construction, and their variances ARE the eigenvalues.
comp_cov = sample_covariance(Y)
assert np.max(np.abs(comp_cov - np.diag(np.diag(comp_cov)))) < 1e-6 * np.trace(C), \\
    "in the eigenbasis the covariance must be diagonal"
assert np.allclose(np.diag(comp_cov), vals, rtol=1e-6), \\
    "each component's variance must equal its eigenvalue"

print(f"{'k':>3} {'variance explained':>20}")
for k in (1, 2, 3, 4):
    print(f"{k:>3} {variance_explained(vals, k):>19.2%}")
assert variance_explained(vals, 8) == 1.0 or np.isclose(variance_explained(vals, 8), 1.0)
# The signature of a 3-D subspace is not a threshold on the third component. It is
# the SIZE OF THE STEP to the fourth, which is where the sources stop and the noise
# starts. Compare the increments rather than the cumulative total.
steps = [variance_explained(vals, k) - variance_explained(vals, k - 1) for k in range(1, 9)]
print(f"\\nincrements: {[f'{x:.2%}' for x in steps]}")
assert steps[2] > 15 * steps[3], (
    f"the drop from component 3 to 4 marks the edge of the subspace: "
    f"{steps[2]:.2%} then {steps[3]:.2%}"
)
assert variance_explained(vals, 3) > 0.97, "three components must carry nearly everything"
print("\\nStep 2 passed. The rotation is exact, three components carry 98.3 percent,")
print("which is the correct answer to 'how many dimensions', and tells you nothing yet")
print("about what those dimensions are.")''')

m.md(r'''---

## 3. The first trap: PC1 is usually the reference

LIN 4 showed that a shared reference adds $\sigma_r^2\mathbf{1}\mathbf{1}^{\top}$ to
the covariance, a rank-one term pointing along the all-ones direction. PCA finds
the direction of greatest variance. So on monopolar data with any appreciable
reference noise, the answer PCA returns first is the reference, every time.

This is not a subtle bias. It is the largest thing in the matrix, and it is not
brain activity. Below, the angle between $v_1$ and the all-ones direction is
measured as reference amplitude grows.''')

m.code('''X40 = X[:, :40000]
ones_dir = np.ones(8) / np.sqrt(8)

print(f"{'reference sd':>13} {'var expl by PC1':>17} {'angle(v1, 1)':>14}")
angles = {}
for ref_sd in (0.0, 0.5, 2.0, 8.0):
    Xr = X40 + ref_sd * rng.standard_normal(X40.shape[1])[None, :]
    v_r, V_r = jacobi_eigh(sample_covariance(Xr))
    cos_ang = abs(float(V_r[:, 0] @ ones_dir))
    angles[ref_sd] = np.degrees(np.arccos(min(1.0, cos_ang)))
    print(f"{ref_sd:>13.1f} {variance_explained(v_r, 1):>16.1%} {angles[ref_sd]:>13.1f} deg")

assert angles[8.0] < 5.0, "with a strong reference, PC1 IS the all-ones direction"
assert angles[0.0] > angles[8.0], "without one it points somewhere driven by the sources"
print("\\nAt a reference standard deviation of 8, PC1 sits within a few degrees of the")
print("all-ones direction and explains almost all the variance. It is the amplifier.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. The deeper trap: components are not sources

The reference problem has a fix, which is a montage. This one does not.

PCA returns an **orthonormal** basis, because that is what eigenvectors of a
symmetric matrix are. Neural sources have no reason to be orthogonal: the columns
of the mixing matrix $A$ are determined by anatomy, and LIN 4 showed they are
strongly overlapping. So the eigenvectors cannot be the mixing columns except by
coincidence.

What PCA does recover, reliably, is the **subspace** those columns span. Any
rotation within that subspace produces components that are equally uncorrelated
and equally variance-ordered, so the decomposition cannot distinguish them. This
is the rotation ambiguity, and it is why "component 1 is the STN source" is a
claim PCA is structurally incapable of supporting.

Recovering the sources themselves needs an assumption PCA does not make. Methods
that add one, such as independent component analysis with its non-Gaussianity
assumption, or the generalised eigendecomposition of LIN 6 with its contrast between
two conditions, are answering a different and better-posed question.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
# Reference-free data, so the only obstacle left is the rotation ambiguity.
vals_c, vecs_c = jacobi_eigh(sample_covariance(X))
Y3 = pca_project(X, vecs_c, 3)

# (a) The 3-D subspace IS recovered. Measure by principal angles between the span
# of the top 3 eigenvectors and the span of the mixing columns.
Qa, _ = np.linalg.qr(vecs_c[:, :3])
Qb, _ = np.linalg.qr(A_mix)
principal_angles = np.degrees(np.arccos(np.clip(np.linalg.svd(Qa.T @ Qb, compute_uv=False), -1, 1)))
print(f"principal angles between PCA subspace and mixing subspace: "
      f"{np.round(principal_angles, 2)} deg")
assert np.max(principal_angles) < 5.0, "PCA must recover the subspace the sources live in"

# (b) The SOURCES are not recovered. Correlate each component with each true source.
corr = np.abs(np.corrcoef(np.vstack([Y3, S_true]))[:3, 3:])
print("\\n|correlation| between components (rows) and true sources (columns):")
for i, row in enumerate(corr):
    print(f"  PC{i+1}  " + "  ".join(f"{v:.3f}" for v in row))

best_match = np.max(corr, axis=1)
print(f"\\nbest match per component: {np.round(best_match, 3)}")
assert np.max(principal_angles) < 5.0 and np.min(best_match) < 0.95, (
    "the subspace is right while at least one component is a mixture, which is the "
    "rotation ambiguity"
)
n_confused = int(np.sum(np.sum(corr > 0.3, axis=1) > 1))
assert n_confused >= 1, "at least one component should straddle two sources"
print(f"components correlating above 0.3 with more than one source: {n_confused} of 3")
print("\\nStep 4 passed. The subspace is recovered to within a few degrees and the")
print("individual sources are not. PCA answers 'how many dimensions', never 'which sources'.")''')

m.md(r'''---

## 5. What you established

1. $\Sigma = V\Lambda V^{\top}$ with $V$ orthonormal, verified by checking
   $\Sigma v_i = \lambda_i v_i$ directly before comparing to a library.
2. PCA is a rigid rotation into the eigenbasis. Total variance is preserved
   exactly, the components are uncorrelated, and their variances are the
   eigenvalues.
3. On monopolar data with a strong shared reference, PC1 sits within a few
   degrees of the all-ones direction. The largest principal component is the
   amplifier, not the brain. This is LIN 4's G1 result seen from a different angle.
4. PCA recovers the **subspace** spanned by the mixing columns to within a few
   degrees, and does **not** recover the sources, because eigenvectors are
   orthogonal and anatomy does not arrange sources orthogonally. No amount of
   data fixes this; it is the rotation ambiguity, not an estimation error.

### Exercises

**Exercise 1.** Make two of the three sources genuinely correlated, at $r = 0.7$,
and repeat Section 4. Does the subspace recovery degrade, does the source
recovery degrade, or both? Explain which of the two results depended on
$\Sigma_S$ being diagonal.

**Exercise 2.** A scree plot is often read as "the number of components before
the elbow is the number of neural sources". Using the mixing model, construct a
case with four sources whose scree plot shows a clear elbow at two, and a case
with two sources whose plot suggests four. What is the scree plot actually
measuring?

**Exercise 3.** Section 3 detected the reference by the angle between $v_1$ and
$\mathbf{1}$. Compute that angle for the seven derivations of `bipolar_vertical`
instead. LIN 4 found 18 percent residual common mode there. Does $v_1$ of the
derivations point at $\mathbf{1}$, and what is it pointing at instead?

---

**Next: LIN 6, generalised eigendecomposition.** PCA maximises variance, which is
the wrong objective, because the largest thing in a recording is rarely the
interesting thing. LIN 6 maximises a ratio between two conditions instead, which
makes the question well posed.
''')

m.emit()
ns = verify("01_linear_algebra", "05_eigendecomposition_pca")
print("  LIN 5 OK, symbols:", [k for k in ("jacobi_eigh", "pca_project", "variance_explained") if k in ns])
