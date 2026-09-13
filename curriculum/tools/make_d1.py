import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("09_decoding", "01_least_squares_and_ridge")

m.md(r'''# Lesson DEC 1: Least Squares and Ridge, Built and Then Checked {{VARIANT}}

**Electives · Machine Learning and Neural Decoding**

{{INSTRUCTIONS}}

POP 3's Kalman filter is the only decoder this curriculum has built, and it is a
specialised one. This course builds the general case, starting with the model
almost every neural decoding paper actually fits underneath whatever it is
called: a linear map from contacts to a behavioural variable, regularised.

The lesson has two halves that are easy to confuse. The first is mechanical: the
normal equations, ridge, and a check that a hand-written solver agrees with
`sklearn` to machine precision. That part is not where the difficulty is. The
second half is that a fitted weight vector is not a measurement of anything, and
Section 4 makes that concrete in a way that Section 1 cannot.

**What it assumes**

| From | What is used |
|---|---|
| LIN 3 | Condition number, multicollinearity, and that a near-singular matrix inverts without complaining. |
| LIN 4 | That a shared reference makes contacts correlate, and that shrinkage trades bias for stability. |
| INF 1 | That an estimate selected for looking good is not an unbiased estimate. |

**What it underwrites**

Every decoding result this app could produce, DEC 2's cross-validation argument,
and DEC 5's distinction between a decoder's weights and a source's activity.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from sklearn.linear_model import LinearRegression, Ridge

rng = np.random.default_rng(41)

N_CONTACTS = 16
N_SOURCES = 3
# The true encoding lives in source space, and no contact sees a source alone.
BETA_TRUE = np.array([2.0, -1.0, 0.5])

# One array, fixed once. Every call to recording() below draws new trials from
# the SAME electrode geometry, which is what a second block of the same session
# is. Redrawing the mixing per seed would make a held-out set a different
# patient on a different lead, and every generalisation number in this lesson
# would be measuring transfer between arrays instead of between trials.
MIXING = np.random.default_rng(0).uniform(0.3, 1.0, (N_SOURCES, N_CONTACTS))


def recording(n_trials: int, seed: int, ref_sd: float = 1.5,
              noise: float = 1.0) -> tuple[np.ndarray, np.ndarray]:
    """Contacts see a mixture of latent sources plus a shared reference.

    This is LIN 4's model with a behavioural variable attached. `y` depends on
    the sources; the decoder only ever sees the contacts.
    """
    gen = np.random.default_rng(seed)
    sources = gen.standard_normal((n_trials, N_SOURCES))
    reference = ref_sd * gen.standard_normal((n_trials, 1))
    x = sources @ MIXING + reference + 0.3 * gen.standard_normal((n_trials, N_CONTACTS))
    y = sources @ BETA_TRUE + noise * gen.standard_normal(n_trials)
    return x, y


print("Environment initialized for Lesson DEC 1")''')

m.md(r'''---

## 1. The normal equations, and a check that is worth making

Least squares picks the weight vector minimising the squared error. Setting the
derivative to zero gives the **normal equations**, and the whole of linear
decoding is one line of linear algebra:

$$(X^\top X)\,w = X^\top y$$

Ridge adds a penalty on the size of the weights, which adds a constant to the
diagonal:

$$(X^\top X + \alpha I)\,w = X^\top y$$

LIN 3 already said what that diagonal does. A near-singular matrix inverts
without complaining and returns nonsense; adding to the diagonal moves the
smallest eigenvalues away from zero, which is the same move as LIN 4's shrinkage.

Two implementation details are not cosmetic. **Centre the columns and the target**
rather than fitting an intercept as a weight, because ridge would otherwise
penalise the intercept and shrink the whole fit toward zero. And **solve** rather
than invert: `np.linalg.solve` is both faster and better conditioned than forming
an explicit inverse.''')

m.task(
'''def fit_linear(X: np.ndarray, y: np.ndarray, alpha: float = 0.0) -> tuple[np.ndarray, float]:
    """Ridge regression from the normal equations. alpha=0 is ordinary least squares.

    Returns (weights, intercept). Centre the columns of X and the target, solve
    for the weights, and recover the intercept from the means.
    """
    # TODO: centre X by its column means and y by its mean
    # TODO: solve (Xc.T @ Xc + alpha * I) w = Xc.T @ yc, with solve rather than inv
    # TODO: the intercept is y.mean() - X.mean(axis=0) @ w
    raise NotImplementedError("Implement fit_linear")


def predict(X: np.ndarray, weights: np.ndarray, intercept: float) -> np.ndarray:
    """Apply a fitted linear decoder."""
    # TODO: one line
    raise NotImplementedError("Implement predict")''',
'''def fit_linear(X: np.ndarray, y: np.ndarray, alpha: float = 0.0) -> tuple[np.ndarray, float]:
    """Ridge regression from the normal equations. alpha=0 is ordinary least squares.

    Returns (weights, intercept). Centre the columns of X and the target, solve
    for the weights, and recover the intercept from the means.
    """
    x_mean = X.mean(axis=0)
    y_mean = float(y.mean())
    xc = X - x_mean
    # Penalising the intercept would shrink the whole fit toward zero rather than
    # toward the mean, which is why the centring happens before the penalty.
    gram = xc.T @ xc + alpha * np.eye(X.shape[1])
    weights = np.linalg.solve(gram, xc.T @ (y - y_mean))
    return weights, y_mean - x_mean @ weights


def predict(X: np.ndarray, weights: np.ndarray, intercept: float) -> np.ndarray:
    """Apply a fitted linear decoder."""
    return X @ weights + intercept''')

m.code('''# --- TEST CELL FOR STEP 1 ---
X, y = recording(200, seed=0)

# (a) Against a library that solves the same problem a different way. Agreement
# to machine precision means the arithmetic is right, not merely plausible.
w_ols, b_ols = fit_linear(X, y, alpha=0.0)
sk_ols = LinearRegression().fit(X, y)
print(f"OLS, hand-written against sklearn: max |weight difference| = "
      f"{np.max(np.abs(w_ols - sk_ols.coef_)):.2e}")
print(f"                                   intercept difference   = "
      f"{abs(b_ols - sk_ols.intercept_):.2e}")
assert np.allclose(w_ols, sk_ols.coef_, atol=1e-9)
assert abs(b_ols - sk_ols.intercept_) < 1e-9

print(f"\\n{'alpha':>8} {'max |scratch - sklearn|':>26}")
for alpha in (1.0, 10.0, 100.0, 1000.0):
    w_mine, b_mine = fit_linear(X, y, alpha)
    sk = Ridge(alpha=alpha, fit_intercept=True).fit(X, y)
    print(f"{alpha:>8.0f} {np.max(np.abs(w_mine - sk.coef_)):>26.2e}")
    assert np.allclose(w_mine, sk.coef_, atol=1e-8), f"ridge disagrees at alpha={alpha}"
    assert abs(b_mine - sk.intercept_) < 1e-8, "and the intercept must match too"

# (b) The properties that make it least squares at all, checked directly rather
# than inferred from the library agreeing.
residual = y - predict(X, w_ols, b_ols)
print(f"\\nOLS residual orthogonal to every column of X: max |X.T r| = "
      f"{np.max(np.abs((X - X.mean(axis=0)).T @ residual)):.2e}")
assert np.max(np.abs((X - X.mean(axis=0)).T @ residual)) < 1e-8, \\
    "the residual of a least squares fit is orthogonal to the design; that IS the solution"

# Ridge shrinks. Monotonically, and toward zero, and never past it.
norms = [np.linalg.norm(fit_linear(X, y, a)[0]) for a in (0.0, 1.0, 10.0, 100.0, 1e4, 1e8)]
print(f"weight norm as alpha goes 0 to 1e8: " + ", ".join(f"{n:.3f}" for n in norms))
assert all(a > b for a, b in zip(norms, norms[1:])), "more penalty must mean smaller weights"
assert norms[-1] < 1e-3, "and an enormous penalty drives them to zero"

print("\\nThe hand-written solver and sklearn agree to about 1e-14, which is the")
print("arithmetic, not the statistics. Everything difficult about decoding is still")
print("ahead: nothing above says whether any of these weights should be believed.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Why a neural decoder needs the penalty

Ridge is often introduced as insurance against having more features than samples.
That is not the situation here: sixteen contacts and two hundred trials is a
comfortable ratio. The problem is the one LIN 4 measured, which is that contacts
recording through a shared reference are strongly correlated with each other.

When columns of $X$ are nearly collinear, $X^\top X$ is nearly singular, and the
weight that minimises training error is nearly unconstrained along the directions
with almost no variance. The fit is fine. The weights are not.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
correlations = np.corrcoef(X.T)[np.triu_indices(N_CONTACTS, 1)]
print(f"{N_CONTACTS} contacts, {len(y)} trials")
print(f"  median |correlation| between contacts: {np.median(np.abs(correlations)):.3f}")
print(f"  condition number of X'X:               {np.linalg.cond(X.T @ X):.0f}")
assert np.median(np.abs(correlations)) > 0.8, "a shared reference makes contacts move together"

# Instability is not visible in one fit, so resample. If the weights mean
# anything, they should not move much when the trials are redrawn.
def bootstrap_weights(alpha, n_boot=200):
    out = []
    for b in range(n_boot):
        gen = np.random.default_rng(1000 + b)
        idx = gen.integers(0, len(y), len(y))
        out.append(fit_linear(X[idx], y[idx], alpha)[0])
    return np.array(out)

print(f"\\n{'alpha':>8} {'mean bootstrap SD of a weight':>32}")
spread = {}
for alpha in (0.0, 10.0, 200.0):
    spread[alpha] = float(bootstrap_weights(alpha).std(axis=0).mean())
    print(f"{alpha:>8.0f} {spread[alpha]:>32.3f}")
assert spread[0.0] > 3 * spread[200.0], "the penalty is what makes a weight reproducible"

# And the instability is real error, not just wobble: held-out performance.
X_train, y_train = recording(120, seed=7)
X_test, y_test = recording(4000, seed=8)
print(f"\\n{'alpha':>8} {'train MSE':>11} {'held-out MSE':>14}")
held_out = {}
train_mse = {}
for alpha in (0.0, 1.0, 10.0, 50.0, 200.0, 1000.0, 5000.0):
    w, b = fit_linear(X_train, y_train, alpha)
    train_mse[alpha] = float(np.mean((predict(X_train, w, b) - y_train) ** 2))
    held_out[alpha] = float(np.mean((predict(X_test, w, b) - y_test) ** 2))
    print(f"{alpha:>8.0f} {train_mse[alpha]:>11.3f} {held_out[alpha]:>14.3f}")

best_alpha = min(held_out, key=held_out.get)
print(f"\\n  best held-out alpha: {best_alpha:.0f}, MSE {held_out[best_alpha]:.3f}, "
      f"against {held_out[0.0]:.3f} unpenalised")
assert best_alpha > 0, "the penalised decoder generalises better than the unpenalised one"
assert held_out[best_alpha] < 0.95 * held_out[0.0]

# The point that Section 3 needs: training error CANNOT choose alpha, because it
# is monotone in alpha. Its minimum is always at zero penalty, always.
increasing = all(train_mse[a] <= train_mse[b] + 1e-9
                 for a, b in zip(sorted(train_mse), sorted(train_mse)[1:]))
print(f"  training error increases monotonically with alpha: {increasing}")
assert increasing, "adding a penalty can only ever make the training fit worse"
assert min(train_mse, key=train_mse.get) == 0.0, \\
    "so training error always picks alpha=0, whatever the right answer is"

print(f"\\nUnder resampling the unpenalised weights moved {spread[0.0] / spread[200.0]:.1f} times as much as")
print(f"they do at alpha = 200, and {spread[0.0] / spread[10.0]:.1f} times as much as at the alpha = 10 the")
print("held-out curve above picks. How large that effect is depends on which penalty")
print("you compare against, so the comparison means nothing with the alpha unnamed.")
print("The penalty also bought real held-out accuracy, not just tidier numbers.")
print("\\nThe last two lines are the ones that matter for the rest of this course. The")
print("training error is monotone in alpha, so its minimum is at alpha = 0 no matter")
print("what the data says. A quantity that always gives the same answer cannot be")
print("used to choose. Something outside the training set has to.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. What the penalty is trading

The held-out curve in Section 2 is a U, and the two arms of it are the two halves
of the bias-variance decomposition. At $\alpha = 0$ the decoder is unbiased and
unstable. At large $\alpha$ it is stable and wrong. The minimum is wherever those
two costs cross, and where that is depends on the data, not on a convention.

This section measures the two arms separately, by fitting many independent
training sets and asking two different questions about the resulting predictions:
how far the **average** prediction is from the truth, and how far individual
predictions are from that average.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
N_FITS, N_TRAIN = 120, 80
X_probe, y_probe = recording(2000, seed=99)
# The best a linear decoder on these contacts could ever do, estimated from a
# sample large enough that its own error is negligible. Bias is measured against
# this rather than against y, because no linear decoder can reach y.
_w_best, _b_best = fit_linear(*recording(200_000, seed=100), 0.0)
truth = predict(X_probe, _w_best, _b_best)

def bias_variance(alpha):
    """Split held-out error into what stays wrong and what moves around."""
    preds = np.empty((N_FITS, len(y_probe)))
    for f in range(N_FITS):
        Xf, yf = recording(N_TRAIN, seed=5000 + f)
        w, b = fit_linear(Xf, yf, alpha)
        preds[f] = predict(X_probe, w, b)
    mean_prediction = preds.mean(axis=0)
    bias_sq = float(np.mean((mean_prediction - truth) ** 2))
    variance = float(np.mean(preds.var(axis=0)))
    return bias_sq, variance, float(np.mean((preds - y_probe) ** 2))

print(f"{N_FITS} independent training sets of {N_TRAIN} trials each\\n")
print(f"{'alpha':>8} {'bias^2':>10} {'variance':>10} {'total error':>13}")
bv = {}
for alpha in (0.0, 3.0, 10.0, 100.0, 5000.0, 100_000.0):
    bv[alpha] = bias_variance(alpha)
    print(f"{alpha:>8.0f} {bv[alpha][0]:>10.4f} {bv[alpha][1]:>10.4f} {bv[alpha][2]:>13.4f}")

biases = [bv[a][0] for a in sorted(bv)]
variances = [bv[a][1] for a in sorted(bv)]
assert all(a <= b + 1e-9 for a, b in zip(biases, biases[1:])), "bias grows with the penalty"
assert variances[0] > 3 * min(variances), "variance falls sharply as the penalty comes in"
best = min(bv, key=lambda a: bv[a][2])
assert best not in (min(bv), max(bv)), "and the best total sits strictly between the extremes"
print(f"\\n  lowest total error at alpha = {best:.0f}, which is neither end of the sweep")

# Variance falls and then stops falling. It cannot reach zero, because a fully
# penalised decoder still predicts the training set's mean, and that mean has
# sampling variability of its own.
floor = float(np.var(y_probe) / N_TRAIN)
settled = bv[100_000.0][1]
print(f"  variance at the heaviest penalty: {settled:.4f}")
print(f"  var(y)/n, the sampling variance of a training-set mean: {floor:.4f}")
assert variances[-1] < 0.4 * variances[0], "variance falls a long way and then stops"
assert abs(settled - variances[-2]) < 0.02, "it has stopped falling by the end of the sweep"
assert 0.7 < settled / floor < 1.6, \\
    "and it stops near var(y)/n, which is what a fully penalised decoder still predicts"

print("\\nBias rose monotonically across the whole sweep while variance fell sharply and")
print("then stopped, and the best total error sat strictly between the extremes. That is")
print("the tradeoff stated as a measurement rather than as a diagram.")
print("\\nThe plateau is worth a second look, because the usual diagram does not have one.")
print("Variance cannot be driven to zero: a fully penalised decoder still predicts the")
print("training set's mean, and that mean moves from one training set to the next. It")
print(f"settled at {settled:.4f} against a predicted var(y)/n of {floor:.4f}, which is agreement to")
print("about twenty percent on a variance estimated from 120 fits. The floor is a")
print("property of how many trials you recorded, not of any modelling choice.")
print("\\nNotice what this section needed that a real analysis does not have: 120")
print("independent training sets and a probe set of 2000 trials with the truth known.")
print("An intraoperative session provides one training set and no truth. Getting an")
print("honest version of this curve from the data you actually have is the whole")
print("subject of DEC 2, and it is harder than it looks.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. A weight is not a measurement of a contact

Everything so far treats the weight vector as a means to a prediction. It is
routinely read as something else: a map of which contacts carry the signal, and
therefore of where the physiology is.

The test below does nothing to the physiology at all. It adds copies of one
contact, the way a denser array would, and asks what happens to that contact's
apparent importance and to the decoder's actual behaviour.

The arithmetic is worth predicting before running it. If $k$ columns are
identical and share a total weight $s$, the penalty $\alpha \sum w_i^2$ is
smallest when they split it evenly, giving $\alpha s^2/k$. The effective penalty
on that source is therefore $\alpha/k$: the more electrodes report a source, the
less the model is charged for leaning on it.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
TUNED, HEAVY = 10.0, 200.0     # Section 2's best penalty, and a heavier one
X_dup, y_dup = recording(300, seed=11)
X_dup_test, y_dup_test = recording(3000, seed=12)
def with_copies(k):
    """The same array, with contact 0 reported by k near-identical channels.

    Seeded from k, so the same k always gives the same copies and the table below
    can be read as a sweep over one thing rather than over the random state too.
    """
    gen = np.random.default_rng(300 + k)
    extra = [X_dup[:, [0]] + 0.02 * gen.standard_normal((len(y_dup), 1)) for _ in range(k - 1)]
    extra_test = [X_dup_test[:, [0]] + 0.02 * gen.standard_normal((len(y_dup_test), 1))
                  for _ in range(k - 1)]
    return np.hstack([X_dup] + extra), np.hstack([X_dup_test] + extra_test)

def source_weight_and_predictions(k, alpha):
    Xk, Xk_test = with_copies(k)
    w, b = fit_linear(Xk, y_dup, alpha)
    total = float(w[0] + w[N_CONTACTS:].sum())
    return total, predict(Xk_test, w, b)

_pair = with_copies(2)[0]
duplicate_r = float(np.corrcoef(_pair[:, 0], _pair[:, -1])[0, 1])
print(f"contact 0 duplicated k times; nothing about the sources or the task changes")
print(f"a duplicate correlates with contact 0 at r = {duplicate_r:.4f}\\n")

base = {a: source_weight_and_predictions(1, a) for a in (TUNED, HEAVY)}
print(f"{'':>4} {'alpha = 10 (tuned)':>28} {'alpha = 200 (heavier)':>30}")
print(f"{'k':>4} {'weight':>10}{'vs k=1':>9}{'pred r':>9} {'weight':>11}{'vs k=1':>9}{'pred r':>10}")
ratio = {TUNED: {}, HEAVY: {}}
pred_corr = {TUNED: {}, HEAVY: {}}
for k in (1, 2, 4, 8):
    cells = []
    for alpha in (TUNED, HEAVY):
        total, pred = source_weight_and_predictions(k, alpha)
        ratio[alpha][k] = total / base[alpha][0]
        pred_corr[alpha][k] = float(np.corrcoef(pred, base[alpha][1])[0, 1])
        cells.append(f"{total:>10.4f}{ratio[alpha][k]:>8.2f}x{pred_corr[alpha][k]:>9.4f}")
    print(f"{k:>4} {cells[0]:>28} {cells[1]:>30}")

for alpha in (TUNED, HEAVY):
    seq = [ratio[alpha][k] for k in (1, 2, 4, 8)]
    assert all(a < b for a, b in zip(seq, seq[1:])), \
        f"at alpha={alpha:.0f}, every extra copy raises the same source's apparent importance"
    for k in (2, 4, 8):
        assert pred_corr[alpha][k] > 0.99, "while the decoder's predictions do not move"

# The distortion is a property of the penalty, not of the data. The heavier the
# penalty, the more the weight map reports the montage rather than the brain.
assert ratio[HEAVY][8] > 2.0, "a heavy penalty more than doubles the apparent importance"
assert ratio[TUNED][8] < 1.5, "a light one distorts far less"
for k in (2, 4, 8):
    assert ratio[HEAVY][k] > ratio[TUNED][k], "the distortion grows with the penalty"
# The idealised factor k is an upper bound approached only when the penalty
# dominates the data. Carrying the same algebra further gives a ratio of
# (g + alpha)/(g + alpha/k), with g the duplicated column's residual sum of
# squares, which is below k for any finite g whether or not other contacts are
# present. That is why the tuned penalty distorts less than the heavy one.
assert ratio[HEAVY][8] < 8.0, "the idealised factor of k is an upper bound, not a prediction"

print(f"\\n  Eight copies of one contact raised its apparent importance {ratio[HEAVY][8]:.1f}x at the")
print(f"  heavier penalty and {ratio[TUNED][8]:.2f}x at the tuned one, while every decoder in the")
print("  table made predictions correlating above 0.99 with the original.")

print("\\nSo the weight on a contact answers a question about the montage, not about the")
print("brain. It rose because more channels happened to report the same source, which")
print("is a fact about how the array was built. LIN 4 made the same point for")
print("covariance and G1 enforces it; this is the decoding version.")
print("\\nThe second column is the part worth carrying forward. The distortion is not a")
print("fixed property of the data, it scales with the penalty, because the penalty is")
print("what makes splitting a weight across duplicates cheaper than concentrating it.")
print("A heavily regularised decoder has a smoother, better-looking weight map and a")
print("less faithful one, and nothing about the map itself says which you are looking")
print("at.")
print("\\nThis does not make ridge wrong, and it does not make the decoder worse: the")
print("predictions never moved. It makes ONE reading of the output wrong, the reading")
print("that treats a weight map as a picture of where the signal is. DEC 5 is about")
print("what you can put in its place.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **Linear decoding is one line of linear algebra, and it is worth checking
   against a library.** A hand-written ridge solver agreed with `sklearn` to
   about 1e-14 at every penalty tested, and the OLS residual was orthogonal to
   the design to about 1e-12, which is the defining property rather than a
   consequence.
   Centre before penalising, or the intercept gets shrunk too.
2. **A neural decoder needs the penalty because of collinearity, not because of
   dimensionality.** Sixteen contacts and two hundred trials is a comfortable
   ratio, and the contacts still correlated at a median 0.94 through a shared
   reference, giving a condition number near 900. Under resampling the
   unpenalised weights moved about 7.6 times as much as at alpha = 200 and about
   1.7 times as much as at the alpha = 10 the held-out curve picks, and the
   penalty bought real held-out accuracy.
3. **Training error cannot choose the penalty.** It is monotone increasing in
   alpha, so its minimum is at alpha = 0 for every dataset that will ever exist.
   Something outside the training set has to make the choice, which is DEC 2.
4. **Bias and variance moved in opposite directions across the sweep**, with the
   best total error strictly between the extremes. Measuring them separately took
   120 independent training sets and a known ground truth, neither of which an
   intraoperative session provides.
5. **A decoder weight is a fact about the montage as much as about the brain.**
   Duplicating one contact changes no physiology, and it raised the total weight
   on that source monotonically with the number of copies, because k identical
   columns split a weight and pay a penalty of only alpha/k for it. Every decoder
   in the table predicted the same thing, correlating above 0.99 with the
   original. The size of the distortion is set by the penalty rather than by the
   data: eight copies raised the apparent importance about 2.8x at alpha = 200
   and about 1.2x at the tuned alpha = 10. A heavily regularised decoder has a
   smoother weight map and a less faithful one, and the map does not say which.

The through line: everything in this lesson that was easy to check was
arithmetic, and everything that was hard to check was interpretation. That ratio
does not improve as the models get bigger.

### Exercises

**Exercise 1.** Ridge is not invariant to the units of a column: a contact
measured in microvolts and one in millivolts are penalised differently. Show this
by rescaling one column, then say whether standardising the columns first fixes
it, and what standardising costs when contacts genuinely differ in amplitude
because one of them is closer to the source.

**Exercise 2.** Section 4 used exact duplicates. Repeat it with copies that
correlate at 0.9 rather than to four decimal places, and find where the effect
disappears. Then
say, using LIN 4's measured contact correlations, which regime a real DBS lead is
in.

**Exercise 3.** Section 2's held-out curve used 4000 test trials, which is not
available intraoperatively. Estimate how much the location of the optimal alpha
moves if the test set has 40 trials instead, and say what that implies about
reporting a tuned hyperparameter as though it were a property of the recording.

---

**Next: DEC 2, cross-validation on data that is not independent.** Section 2 left
one question open, which is where the held-out set comes from when there is only
one recording. The standard answer is k-fold cross-validation, and on neural time
series the standard answer is wrong in a way that inflates accuracy.
''')

m.emit()
verify("09_decoding", "01_least_squares_and_ridge")
print("  DEC 1 OK")
