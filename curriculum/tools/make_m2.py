import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("05_dynamics", "02_latent_factors_and_demixing")

m.md(r'''# Lesson POP 2: Latent Factor Models and Demixing {{VARIANT}}

**Analysis · Population Dynamics and Latent Structure**

{{INSTRUCTIONS}}

POP 1 counted dimensions without naming them. LIN 5 tried to name them and failed, for
a reason worth restating: PCA returns an orthonormal basis, and it treats every
scrap of variance alike, including variance that belongs to one channel only.

Factor analysis makes one extra assumption and gets a great deal for it. It says
each channel's variance splits into a part **shared** with other channels and a
part **private** to it, and it models the two separately.

**What it assumes**

| From | What is used |
|---|---|
| LIN 4 | The mixing model, the covariance, and shrinkage. |
| LIN 5 | Eigendecomposition, PCA as a rotation, and the rotation ambiguity. |
| POP 1 | The participation ratio, and that finite data biases it. |

**What it underwrites**

Any latent-variable summary of a population, and the comparison of such a
summary between conditions.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from sklearn.decomposition import FactorAnalysis, PCA

rng = np.random.default_rng(81)

def sample_covariance(X):
    """From LIN 4."""
    Xc = X - X.mean(axis=1, keepdims=True)
    return (Xc @ Xc.T) / (X.shape[1] - 1)

print("Environment initialized for Lesson POP 2")''')

m.md(r'''---

## 1. The model, and the one assumption that matters

Factor analysis writes each observation as

$$x = \Lambda f + \epsilon, \qquad
\mathbb{E}[ff^{\top}] = I, \qquad
\mathbb{E}[\epsilon\epsilon^{\top}] = \Psi \ \text{diagonal}$$

so the covariance decomposes as

$$\Sigma = \Lambda\Lambda^{\top} + \Psi$$

The whole content is that $\Psi$ is **diagonal**. Private noise is uncorrelated
across channels by definition, so anything correlated must be shared and belongs
in $\Lambda$. PCA has no such term: it models $\Sigma$ with $\Lambda\Lambda^{\top}$
alone and must therefore absorb private noise into its components.

That difference is invisible when every channel has the same private variance,
because then $\Psi = \sigma^2 I$ shifts every eigenvalue equally and rotates
nothing. It becomes decisive the moment channels differ in how noisy they are,
which for an electrode array is always.''')

m.task(
'''def simulate_factor_model(loading: np.ndarray, private_var: np.ndarray,
                          n_samples: int, gen) -> np.ndarray:
    """Generate `[n_channels, n_samples]` data from x = Lambda f + eps.

    `loading` is [n_channels, n_factors]; `private_var` is [n_channels], the
    DIAGONAL of Psi. Factors are unit-variance and independent.
    """
    # TODO: draw factors, shape [n_factors, n_samples], standard normal
    # TODO: draw private noise per channel with the given variances
    # TODO: return loading @ factors + noise
    raise NotImplementedError("Implement simulate_factor_model")


def top_pca_direction(X: np.ndarray) -> np.ndarray:
    """Leading eigenvector of the sample covariance, unit norm.

    Production equivalent: `sklearn.decomposition.PCA`.
    """
    # TODO: eigendecompose the sample covariance with np.linalg.eigh
    # TODO: return the eigenvector for the LARGEST eigenvalue
    raise NotImplementedError("Implement top_pca_direction")''',
'''def simulate_factor_model(loading: np.ndarray, private_var: np.ndarray,
                          n_samples: int, gen) -> np.ndarray:
    """Generate `[n_channels, n_samples]` data from x = Lambda f + eps.

    `loading` is [n_channels, n_factors]; `private_var` is [n_channels], the
    DIAGONAL of Psi. Factors are unit-variance and independent.
    """
    n_factors = loading.shape[1]
    factors = gen.standard_normal((n_factors, n_samples))
    noise = gen.standard_normal((len(private_var), n_samples)) * np.sqrt(private_var)[:, None]
    return loading @ factors + noise


def top_pca_direction(X: np.ndarray) -> np.ndarray:
    """Leading eigenvector of the sample covariance, unit norm.

    Production equivalent: `sklearn.decomposition.PCA`.
    """
    vals, vecs = np.linalg.eigh(sample_covariance(X))
    return vecs[:, int(np.argmax(vals))]''')

m.code('''# --- TEST CELL FOR STEP 1 ---
C, T = 12, 4000
true_loading = np.zeros((C, 1))
true_loading[:, 0] = np.r_[np.ones(6), np.zeros(6)]     # one factor on the first 6 channels

# (a) Equal private noise: PCA and FA agree, because Psi = sigma^2 I rotates nothing.
equal_psi = np.full(C, 1.0)
X_eq = simulate_factor_model(true_loading, equal_psi, T, rng)

def align_deg(v, target):
    c = abs(float(v @ target) / (np.linalg.norm(v) * np.linalg.norm(target)))
    return float(np.degrees(np.arccos(min(1.0, c))))

pca_eq = top_pca_direction(X_eq)
fa_eq = FactorAnalysis(n_components=1, random_state=0, max_iter=500).fit(X_eq.T).components_[0]
print(f"equal private noise:  PCA {align_deg(pca_eq, true_loading[:,0]):5.1f} deg, "
      f"FA {align_deg(fa_eq, true_loading[:,0]):5.1f} deg from the true loading")
assert align_deg(pca_eq, true_loading[:, 0]) < 5.0, "with equal noise PCA is fine"
assert align_deg(fa_eq, true_loading[:, 0]) < 5.0, "and so is FA"

# (b) One very noisy channel, which is the normal state of an electrode array.
uneven_psi = np.full(C, 1.0)
uneven_psi[-1] = 40.0                                    # one bad contact
X_un = simulate_factor_model(true_loading, uneven_psi, T, rng)

def best_component_angle(model, target):
    """Angle of the best-aligned component, since factor order is arbitrary."""
    return min(align_deg(c, target) for c in model.components_)

pca_un = top_pca_direction(X_un)
a_pca = align_deg(pca_un, true_loading[:, 0])
print(f"\\none bad contact, private variance 40 against a shared variance of 1\\n")
print(f"{'method':>22} {'angle to the true shared axis':>32}")
print(f"{'PCA':>22} {a_pca:>28.1f} deg")

angles = {}
for k in (1, 2, 3):
    fa_k = FactorAnalysis(n_components=k, random_state=0, max_iter=500).fit(X_un.T)
    angles[k] = best_component_angle(fa_k, true_loading[:, 0])
    print(f"{'factor analysis, k=' + str(k):>22} {angles[k]:>28.1f} deg")

assert a_pca > 60.0, "PCA's leading component is captured by the noisiest channel"

# The result that matters, and it is not the one usually advertised.
assert angles[1] > 60.0, \\
    "with only one factor, FA fails EXACTLY as PCA does"
assert angles[2] < 10.0, "with a spare factor it recovers the true axis"
assert angles[3] < 10.0, "and stays recovered"

print("\\nFactor analysis is not automatically immune. With k=1 it fails exactly as")
print("PCA does, and the reason is worth knowing: a factor that loads on a SINGLE")
print("channel is mathematically indistinguishable from that channel's private")
print("noise. The likelihood is flat between the two, so the optimiser is free to")
print("sit on the useless solution, and it does. This is a Heywood case.")
print("\\nGive it one factor to spare and the degeneracy resolves: the bad channel")
print("takes a factor of its own and the real shared axis takes the other.")

# How bad does the channel have to be? Sweep it.
print(f"\\n{'bad channel variance':>21} {'PCA':>8} {'FA k=1':>9} {'FA k=2':>9}")
for bad in (4.0, 9.0, 40.0):
    psi_b = np.full(C, 1.0); psi_b[-1] = bad
    X_b = simulate_factor_model(true_loading, psi_b, T, rng)
    fa1 = FactorAnalysis(n_components=1, random_state=0, max_iter=500).fit(X_b.T)
    fa2 = FactorAnalysis(n_components=2, random_state=0, max_iter=500).fit(X_b.T)
    print(f"{bad:>21.0f} {align_deg(top_pca_direction(X_b), true_loading[:,0]):>7.1f} "
          f"{best_component_angle(fa1, true_loading[:,0]):>8.1f} "
          f"{best_component_angle(fa2, true_loading[:,0]):>8.1f}")
print("\\nBelow about 4x the shared variance nothing goes wrong. Above it, the number")
print("of factors stops being a cosmetic choice and starts deciding the answer.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Demixing: variance that depends on condition, and variance that does not

A second problem is orthogonal to the first. Population activity during a task
contains variance driven by time within a trial, variance driven by which
condition the trial was, and variance driven by their interaction. PCA finds the
largest directions of the total, which mixes all three, so its components are
uninterpretable as "the condition axis" or "the time axis".

Demixed PCA solves this by decomposing the data into condition-marginalised
parts first, and finding components within each. The important part is the
decomposition, not the algorithm: once you have separated

$$X = \bar{X}_{\text{time}} + \bar{X}_{\text{condition}} + X_{\text{interaction}} + \text{noise}$$

you can ask how much variance each carries, and that number is the answer to most
questions people ask a decomposition for.''')

m.task(
'''def marginalise(trials: np.ndarray, labels: np.ndarray) -> dict:
    """Split trial-averaged activity into time, condition, and interaction parts.

    `trials` is [n_trials, n_channels, n_times]; `labels` gives each trial's
    condition. Returns a dict with keys "time", "condition", "interaction",
    each broadcast to [n_conditions, n_channels, n_times] so their energies are
    directly comparable.

    Production equivalent: the dPCA reference implementation
    (Kobak et al.); this is its marginalisation step.
    """
    # TODO: grand mean over trials and time -> subtract it from everything first
    # TODO: "time" is the mean over ALL trials at each time point, minus grand mean
    # TODO: "condition" is each condition's mean over time, minus the grand mean.
    #       Do NOT average these across conditions: +a and -a would cancel.
    # TODO: "interaction" is what is left of the per-condition time courses
    # TODO: broadcast all three to [K, C, T] so their energies are comparable
    raise NotImplementedError("Implement marginalise")''',
'''def marginalise(trials: np.ndarray, labels: np.ndarray) -> dict:
    """Split trial-averaged activity into time, condition, and interaction parts.

    `trials` is [n_trials, n_channels, n_times]; `labels` gives each trial's
    condition. Returns a dict with keys "time", "condition", "interaction",
    each broadcast to [n_conditions, n_channels, n_times] so their energies are
    directly comparable.

    Production equivalent: the dPCA reference implementation
    (Kobak et al.); this is its marginalisation step.
    """
    conds = np.unique(labels)
    n_t = trials.shape[2]
    grand = trials.mean(axis=(0, 2), keepdims=True)[0]                       # [C, 1]
    per_cond = np.stack([trials[labels == c].mean(axis=0) for c in conds])   # [K, C, T]

    time_part = trials.mean(axis=0) - grand                                  # [C, T]
    cond_dev = per_cond.mean(axis=2, keepdims=True) - grand[None]            # [K, C, 1]
    interaction = per_cond - grand[None] - time_part[None] - cond_dev

    # All three returned on the same [K, C, T] grid, so their energies compare.
    return {"time": np.repeat(time_part[None], len(conds), axis=0),
            "condition": np.repeat(cond_dev, n_t, axis=2),
            "interaction": interaction}''')

m.code('''# --- TEST CELL FOR STEP 2 ---
N_TRIALS, N_CH, N_T, N_COND = 240, 15, 60, 2
tt = np.linspace(0, 1, N_T)

# Build activity with KNOWN amounts of each kind of variance.
# Unit-norm axes, so the gains below control the planted energy directly rather
# than being multiplied by whatever norm a random draw happened to have.
time_axis = rng.standard_normal(N_CH); time_axis /= np.linalg.norm(time_axis)
cond_axis = rng.standard_normal(N_CH); cond_axis /= np.linalg.norm(cond_axis)
TIME_GAIN, COND_GAIN, NOISE = 4.0, 2.0, 0.5

labels = rng.integers(0, N_COND, N_TRIALS)
trials = np.zeros((N_TRIALS, N_CH, N_T))
time_profile = np.sin(2 * np.pi * tt)
for i, lab in enumerate(labels):
    trials[i] = (TIME_GAIN * np.outer(time_axis, time_profile)
                 + COND_GAIN * (1 if lab == 1 else -1) * np.outer(cond_axis, np.ones(N_T))
                 + NOISE * rng.standard_normal((N_CH, N_T)))

parts = marginalise(trials, labels)
energies = {k: float(np.sum(v ** 2)) for k, v in parts.items()}
total = sum(energies.values())
print(f"{'component':>14} {'energy':>12} {'share':>9}")
for k, v in energies.items():
    print(f"{k:>14} {v:>12.1f} {v/total:>8.1%}")

# Planted: time energy per condition is TIME_GAIN^2 * mean(sin^2) = 16 * 0.5 = 8,
# condition energy is COND_GAIN^2 = 4. So time should be about twice condition.
ratio = energies["time"] / energies["condition"]
print(f"\\nplanted time:condition energy ratio 2.0, measured {ratio:.2f}")
assert 1.5 < ratio < 2.7, \\
    f"the marginalisation must recover the planted energy split, got {ratio:.2f}"
assert energies["condition"] > 10 * energies["interaction"], \\
    "and real condition variance must not vanish into the interaction term"
u_cond = np.linalg.svd(parts["condition"][0], full_matrices=False)[0][:, 0]
print(f"recovered condition axis is {align_deg(u_cond, cond_axis):.1f} deg from the planted one")
assert align_deg(u_cond, cond_axis) < 10.0, "the condition marginal must recover its axis"

# The time part must actually point along the axis we planted.
u_time = np.linalg.svd(parts["time"][0], full_matrices=False)[0][:, 0]
ang_time = align_deg(u_time, time_axis)
print(f"\\nrecovered time axis is {ang_time:.1f} deg from the planted one")
assert ang_time < 10.0, "the time marginalisation must recover the time axis"

# And PCA on the raw trial-averaged data mixes them, which is the point.
raw_mean = trials.mean(axis=0)
u_pca = np.linalg.svd(raw_mean - raw_mean.mean(axis=1, keepdims=True),
                      full_matrices=False)[0][:, 0]
print(f"PCA's leading axis is {align_deg(u_pca, time_axis):.1f} deg from time, "
      f"{align_deg(u_pca, cond_axis):.1f} deg from condition")
print("\\nNote what PCA did here: it found the time axis, accurately. It did not")
print("produce a mixture, because time carries twice the energy of condition and")
print("the two axes are nearly orthogonal. The problem is not that PCA is wrong.")
print("It is that PCA can only hand you the LARGEST direction, so the condition")
print("axis is simply absent from its first component, and nothing in its output")
print("tells you a second, smaller, differently-meaning axis exists.")
print("\\nStep 2 passed. Marginalising first names the parts before ranking them.")''')

m.md(r'''---

## 3. What the extra assumption costs

Factor analysis buys its advantage with an assumption, and the assumption is
falsifiable. $\Psi$ diagonal means private noise is uncorrelated across channels.

LIN 4 established that this is **false** for an electrode array. Volume conduction
puts every source on every contact, and a shared reference puts the amplifier on
all of them. Noise that is correlated across channels does not fit in a diagonal
$\Psi$, so factor analysis must absorb it into $\Lambda$ and report it as a
shared factor, which is exactly what it was designed to avoid.

So the repair is not a better estimator. It is a montage, applied first, and this
is the same conclusion PRE 1 reached from a different direction.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
# Add correlated noise that is NOT a real factor: a shared reference, as in LIN 4.
shared_ref_sd = 3.0
X_ref = simulate_factor_model(true_loading, uneven_psi, T, rng) \\
        + shared_ref_sd * rng.standard_normal(T)[None, :]

fa_ref_model = FactorAnalysis(n_components=2, random_state=0, max_iter=500).fit(X_ref.T)
ones = np.ones(C)
ang_ref_true = min(align_deg(c, true_loading[:, 0]) for c in fa_ref_model.components_)
ang_ref_ones = min(align_deg(c, ones) for c in fa_ref_model.components_)
print(f"with a shared reference present, FA with k=2:")
print(f"  best factor is {ang_ref_true:5.1f} deg from the true loading")
print(f"  best factor is {ang_ref_ones:5.1f} deg from the all-ones direction")
assert ang_ref_ones < 20.0, \\
    "correlated noise does not fit a diagonal Psi, so FA reports it as a factor"

# The repair: a montage that removes the shared term. Common average reference,
# M = I - (1/C) 11^T, which Lesson LIN 2 built and Lesson LIN 3 showed is rank C-1.
M_car = np.eye(C) - np.ones((C, C)) / C
X_car = M_car @ X_ref
true_car = M_car @ true_loading[:, 0]
fa_car = FactorAnalysis(n_components=2, random_state=0, max_iter=500).fit(X_car.T)
ang_car = min(align_deg(c, true_car) for c in fa_car.components_)
print(f"\\nafter common average reference, FA with k=2:")
print(f"  best factor is {ang_car:5.1f} deg from the true loading")
assert ang_car < ang_ref_true, "removing the shared term must help"
assert ang_car < 30.0, "and it should land near the real factor"

# Now a montage that does NOT work, and the reason is Section 1 again.
M_diff = np.zeros((C - 1, C))
for i in range(C - 1):
    M_diff[i, i] = 1.0
    M_diff[i, i + 1] = -1.0
true_diff = M_diff @ true_loading[:, 0]
print(f"\\nthe same loading, seen through two montages:")
print(f"  after CAR         : {np.round(true_car, 2)}")
print(f"  after differencing: {np.round(true_diff, 2)}")
n_nonzero = int(np.sum(np.abs(true_diff) > 1e-9))
assert n_nonzero == 1, "differencing a block loading leaves ONE nonzero entry"

fa_diff = FactorAnalysis(n_components=2, random_state=0, max_iter=100).fit((M_diff @ X_ref).T)
ang_diff = min(align_deg(c, true_diff) for c in fa_diff.components_)
print(f"\\nafter the differencing montage, FA with k=2:")
print(f"  best factor is {ang_diff:5.1f} deg from the true loading")
print(f"  EM iterations used: {fa_diff.n_iter_} of a 100 cap")
assert ang_diff > 60.0, "and it cannot recover the factor at all"
assert fa_diff.n_iter_ >= 100, "because the problem is degenerate, so EM never converges"

print("\\nThe factor was loaded on the first six contacts, a block. Differencing")
print("adjacent contacts cancels it everywhere except at the block boundary, leaving")
print("a loading on exactly ONE derivation. Section 1 established that a factor")
print("loading on a single channel is indistinguishable from that channel's private")
print("noise, so it is unidentifiable, and the symptom is that EM runs to its")
print("iteration cap without converging.")
print("\\nThe montage is part of the model, not a preprocessing detail. CAR removes")
print("the shared reference and leaves the structure; differencing removes the shared")
print("reference and destroys it. Which one is right depends on the spatial shape of")
print("the thing you are looking for, which is a scientific choice.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. Factor analysis splits $\Sigma = \Lambda\Lambda^{\top} + \Psi$ with $\Psi$
   diagonal, and PCA has no such term. With equal private variance the two agree
   to within a degree. With **one bad contact**, PCA lands 89.8 degrees from the
   true shared axis, and so does factor analysis **with one factor**: a factor
   loading on a single channel is indistinguishable from that channel's private
   noise, the likelihood is flat between them, and the optimiser sits on the
   useless solution. That is a Heywood case. Given one factor to spare, FA
   recovers the axis to 1.5 degrees. The number of factors is not cosmetic; it
   decides whether the method has its advertised advantage at all.
2. Marginalising activity into time, condition and interaction parts before
   decomposing recovers the planted 2:1 energy split to 1.99, and both axes to
   under half a degree. PCA on the total is not wrong here, it finds the time
   axis accurately, but it can only return the largest direction, so the
   condition axis is absent from its output and nothing signals that it exists.
3. Factor analysis's assumption is **false for an electrode array**. With a
   shared reference present its leading factor swings to the all-ones direction
   and displaces the real one. A zero-sum montage restores it. That is the same
   conclusion LIN 2, LIN 4 and PRE 1 reached, arrived at from a fourth direction.

### Exercises

**Exercise 1.** Section 1 used one noisy channel out of twelve. Sweep the number
of noisy channels from 1 to 11 and find where PCA and factor analysis converge
again. Explain the endpoint.

**Exercise 2.** Gaussian-process factor analysis adds a smoothness prior over
time to the model in Section 1. Given POP 1's finding that smoothing lowers apparent
dimensionality, predict what the smoothness prior does to the number of factors
GPFA reports, and design a check.

**Exercise 3.** Section 3 recovered the factor after a bipolar montage, at a
worse angle than the no-reference case. LIN 2 measured the correlation a
bipolar montage induces between derivations. Connect the two, and say what
montage would be better here and what it would cost.

---

**Next: POP 3, recursive online decoding.** POP 1 and POP 2 described activity after the
fact. A brain-computer interface must estimate the state now, from data up to
now, which is a different problem with a different solution.
''')

m.emit()
verify("05_dynamics", "02_latent_factors_and_demixing")
print("  POP 2 OK")
