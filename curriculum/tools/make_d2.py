import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("09_decoding", "02_cross_validation_on_autocorrelated_data")

m.md(r'''# Lesson DEC 2: Cross-Validation on Data That Is Not Independent {{VARIANT}}

**Electives · Machine Learning and Neural Decoding**

{{INSTRUCTIONS}}

DEC 1 ended on a problem it could not solve. The penalty has to be chosen using
data the model has not seen, and an intraoperative session provides one
recording. The standard answer is k-fold cross-validation: hold out a fifth,
train on the rest, rotate.

That answer is correct when the observations are independent. INF 1 established
that neural observations are not, and this lesson measures what k-fold does when
they are not. The result is the single most common way a decoding result is
inflated, it is not subtle, and it is invisible from inside the analysis.

Everything below is measured on data containing **no relationship at all**
between the recording and the target. Every honest number in this lesson is zero.

**What it assumes**

| From | What is used |
|---|---|
| DEC 1 | Ridge, the held-out argument, and that training error cannot choose a penalty. |
| INF 1 | That the unit you treat as independent is a claim about the data, and that autocorrelation makes neighbouring samples redundant. |
| GRL 4 | That a session drifts, so points near each other in time resemble each other. |

**What it underwrites**

Any decoding accuracy this app reports, and the case for a new guardrail, which
Section 4 states and does not adopt.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import lfilter
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold
from sklearn.neighbors import KNeighborsRegressor

rng = np.random.default_rng(53)

N_TIME = 600       # epochs in a session
N_CHANNELS = 16
N_LAGS = 6         # temporal embedding, as a real decoder uses
RHO = 0.95         # epoch-to-epoch autocorrelation


BURN_IN = 400      # >> 1/(1-rho) at the largest rho used, so the output is stationary


def ar1(n, rho, gen, shape=()):
    """Autocorrelated noise of unit variance, or white noise when rho is 0.

    lfilter starts from rest, so the first few 1/(1-rho) samples ramp up from
    zero variance. At rho = 0.95 that is tens of epochs, and it would make the
    rho = 0 row of Section 2 the only stationary one, which is exactly the
    confound that row exists to rule out. Generate extra and discard it.
    """
    white = gen.standard_normal((*shape, n + BURN_IN))
    if rho == 0.0:
        return white[..., BURN_IN:]
    filtered = lfilter([np.sqrt(1 - rho ** 2)], [1.0, -rho], white, axis=-1)
    return filtered[..., BURN_IN:]


def session(seed: int, rho: float = RHO, coupling: float = 0.0,
            n_time: int = N_TIME) -> tuple[np.ndarray, np.ndarray]:
    """One recording: lagged channel features, and a target.

    `coupling` is the true relationship. At 0.0 the target is generated
    independently of every channel, so any apparent decoding is an artifact.
    """
    gen = np.random.default_rng(seed)
    raw = ar1(n_time, rho, gen, (N_CHANNELS,)).T
    y = ar1(n_time, rho, gen)
    if coupling:
        y = np.sqrt(1 - coupling ** 2) * y + coupling * raw[:, 0]
    features = np.hstack([np.roll(raw, lag, axis=0) for lag in range(N_LAGS)])
    return features[N_LAGS:], y[N_LAGS:]


def corr(a, b) -> float:
    """Correlation between prediction and truth, which is how decoding is reported."""
    return float(np.corrcoef(a, b)[0, 1])


print("Environment initialized for Lesson DEC 2")''')

m.md(r'''---

## 1. k-fold, and what it is entitled to assume

Cross-validation estimates how well a model will do on data it has not seen, by
repeatedly refusing to look at part of the data it has. Split into k folds, and
for each fold train on the other k-1 and predict this one. Every observation
ends up predicted by a model that never saw it.

The last sentence is the whole argument, and it contains a hidden step. A model
that never saw observation *i* may still have seen observation *i-1*, and if
those two are nearly the same observation, then "never saw it" is false in the
only sense that matters.

Build the estimator first, and check it on data where the assumption holds.''')

m.task(
'''def cross_val_predict(X, y, make_model, folds: list[np.ndarray],
                      embargo: int = 0) -> np.ndarray:
    """Out-of-fold prediction for every sample.

    For each fold, train on everything outside it and predict inside it. With
    `embargo` > 0, also drop that many samples on each side of the fold from the
    training set, which only makes sense for contiguous folds.
    """
    # TODO: allocate an output array the length of y
    # TODO: for each fold, build the training index: everything not in the fold,
    #       and with an embargo, nothing within `embargo` of the fold's span either
    # TODO: fit a fresh model on the training rows and predict the fold's rows
    raise NotImplementedError("Implement cross_val_predict")


def random_folds(n: int, k: int, seed: int) -> list[np.ndarray]:
    """k folds of shuffled indices: the default everywhere, and the subject of this lesson."""
    # TODO: permute 0..n-1 and split into k roughly equal parts
    raise NotImplementedError("Implement random_folds")


def blocked_folds(n: int, k: int) -> list[np.ndarray]:
    """k folds of CONTIGUOUS indices, so a fold is a stretch of the recording."""
    # TODO: split 0..n-1 in order, without shuffling
    raise NotImplementedError("Implement blocked_folds")''',
'''def cross_val_predict(X, y, make_model, folds: list[np.ndarray],
                      embargo: int = 0) -> np.ndarray:
    """Out-of-fold prediction for every sample.

    For each fold, train on everything outside it and predict inside it. With
    `embargo` > 0, also drop that many samples on each side of the fold from the
    training set, which only makes sense for contiguous folds.
    """
    n = len(y)
    out = np.empty(n)
    everything = np.arange(n)
    for fold in folds:
        if embargo:
            # A gap on each side, so the nearest training sample is `embargo`
            # away in time rather than adjacent to the fold boundary.
            low, high = fold.min() - embargo, fold.max() + embargo
            train = everything[(everything < low) | (everything > high)]
        else:
            train = np.setdiff1d(everything, fold)
        out[fold] = make_model().fit(X[train], y[train]).predict(X[fold])
    return out


def random_folds(n: int, k: int, seed: int) -> list[np.ndarray]:
    """k folds of shuffled indices: the default everywhere, and the subject of this lesson."""
    return np.array_split(np.random.default_rng(seed).permutation(n), k)


def blocked_folds(n: int, k: int) -> list[np.ndarray]:
    """k folds of CONTIGUOUS indices, so a fold is a stretch of the recording."""
    return np.array_split(np.arange(n), k)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
K = 5

# (a) The folds must partition the data, or "predicted by a model that never saw
# it" is false before any statistics happen.
for name, folds in (("random", random_folds(97, K, seed=1)), ("blocked", blocked_folds(97, K))):
    pooled = np.concatenate(folds)
    assert len(folds) == K, f"{name} must produce {K} folds"
    assert sorted(pooled.tolist()) == list(range(97)), f"{name} folds must partition the data"
    assert max(len(f) for f in folds) - min(len(f) for f in folds) <= 1, "and be balanced"
assert all(np.all(np.diff(f) == 1) for f in blocked_folds(100, K)), "blocked folds are contiguous"
assert not all(np.all(np.diff(f) == 1) for f in random_folds(100, K, seed=1)), "random folds are not"

# (b) Against sklearn: the same split rule must produce the same predictions.
X_ind, y_ind = session(0, rho=0.0)
mine = cross_val_predict(X_ind, y_ind, lambda: Ridge(alpha=10.0), blocked_folds(len(y_ind), K))
theirs = np.empty(len(y_ind))
for train, test in KFold(n_splits=K, shuffle=False).split(X_ind):
    theirs[test] = Ridge(alpha=10.0).fit(X_ind[train], y_ind[train]).predict(X_ind[test])
print(f"hand-written k-fold against sklearn KFold: max |difference| = "
      f"{np.max(np.abs(mine - theirs)):.2e}")
assert np.allclose(mine, theirs, atol=1e-10)

# (c) The control that licenses everything after it. On INDEPENDENT samples with
# no true relationship, every scheme must report nothing.
print(f"\\nindependent samples (rho = 0), no true relationship, so the honest answer is 0")
print(f"{'scheme':>18} {'reported r':>12}")
n_ind = len(y_ind)
for name, folds in (("random k-fold", random_folds(n_ind, K, seed=2)),
                    ("blocked k-fold", blocked_folds(n_ind, K))):
    r = corr(cross_val_predict(X_ind, y_ind, lambda: Ridge(alpha=10.0), folds), y_ind)
    print(f"{name:>18} {r:>12.3f}")
    assert abs(r) < 0.12, f"{name} must report nothing when there is nothing"

print("\\nWith independent samples the estimator does what it says: it found no signal")
print("where there was none, whichever way the folds were cut. Everything that follows")
print("changes one thing about the data and nothing about the code.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The same code, on data with a memory

Now make the recording autocorrelated, which is the only change. The target is
still generated independently of every channel, so the honest answer is still
exactly zero.

Two models are used, because the size of the problem depends on how flexible the
model is. Ridge can only take linear combinations. A nearest-neighbour regressor
can, in effect, look up whichever training sample most resembles the test sample,
and under a random split the most similar training sample is usually the one
recorded immediately before it.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
N_SESSIONS = 12
MODELS = {"ridge": lambda: Ridge(alpha=10.0),
          "nearest neighbours": lambda: KNeighborsRegressor(n_neighbors=5)}

def scheme_scores(rho, coupling=0.0, n_sessions=N_SESSIONS, embargo=40):
    """Reported r under each scheme, plus the honest number from a fresh session."""
    out = {name: {"random": [], "blocked": [], "embargo": [], "honest": []} for name in MODELS}
    for s in range(n_sessions):
        X, y = session(s, rho, coupling)
        X_fresh, y_fresh = session(10_000 + s, rho, coupling)
        n = len(y)
        for name, make in MODELS.items():
            out[name]["random"].append(
                corr(cross_val_predict(X, y, make, random_folds(n, K, seed=s)), y))
            out[name]["blocked"].append(
                corr(cross_val_predict(X, y, make, blocked_folds(n, K)), y))
            out[name]["embargo"].append(
                corr(cross_val_predict(X, y, make, blocked_folds(n, K), embargo=embargo), y))
            out[name]["honest"].append(corr(make().fit(X, y).predict(X_fresh), y_fresh))
    return {name: {k: float(np.mean(v)) for k, v in d.items()} for name, d in out.items()}

print("NO true relationship anywhere in this table. Every honest cell is r = 0.\\n")
print(f"{'rho':>6} {'model':>20} {'random k-fold':>15} {'blocked':>9} "
      f"{'+embargo':>10} {'fresh session':>15}")
table = {}
for rho in (0.0, 0.5, 0.8, 0.95):
    table[rho] = scheme_scores(rho)
    for name in MODELS:
        row = table[rho][name]
        print(f"{rho:>6.2f} {name:>20} {row['random']:>15.3f} {row['blocked']:>9.3f} "
              f"{row['embargo']:>10.3f} {row['honest']:>15.3f}")

# (a) With no autocorrelation, nothing goes wrong. This is what identifies the cause.
for name in MODELS:
    assert abs(table[0.0][name]["random"]) < 0.12, "at rho=0 the random split is honest"

# (b) With autocorrelation, the random split reports a decoder that does not exist,
# and the damage grows with the autocorrelation.
leak = [table[r]["ridge"]["random"] for r in (0.0, 0.5, 0.8, 0.95)]
assert all(a < b for a, b in zip(leak, leak[1:])), "the inflation grows with rho"
assert table[0.95]["ridge"]["random"] > 0.4, "and is large at a realistic rho"
assert table[0.95]["nearest neighbours"]["random"] > 0.85, \\
    "a flexible model can exploit the leak almost perfectly"

# (c) Every honest column is still zero, so the signal really is absent.
for rho in table:
    for name in MODELS:
        assert abs(table[rho][name]["honest"]) < 0.15, "there was never anything to find"
        assert abs(table[rho][name]["blocked"]) < 0.15, "and a contiguous split says so"

print(f"\\nAt rho = 0.95, which is ordinary for band power across neighbouring epochs,")
print(f"random five-fold reported r = {table[0.95]['ridge']['random']:.2f} for ridge and "
      f"{table[0.95]['nearest neighbours']['random']:.2f} for nearest")
print("neighbours. The truth in both cells is zero. A fresh session put it under 0.07,")
print("and a contiguous split of the SAME recording put it under 0.10: not identically")
print("zero on 594 epochs, but nothing anyone would report.")
print("\\nThe rho = 0 row is what makes this a diagnosis rather than an observation.")
print("Nothing about the model, the features or the fold count changed down the table;")
print("only the autocorrelation did, and the inflation appeared with it.")
print("\\nThe mechanism is not exotic. Under a random split the training set contains the")
print("epoch either side of every test epoch. Those neighbours have nearly the same")
print("channel values and nearly the same target, so predicting a test epoch is closer")
print("to looking up an answer than to generalising. The more flexible the model, the")
print("better it looks it up: nearest neighbours is the extreme case because looking up")
print("the closest training sample is literally what it does.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. What a contiguous split costs

Section 2 says to cut the folds in contiguous blocks, so that a held-out stretch
is separated in time from everything the model trained on. That is the fix, and
it is not free. This section prices it.

A blocked fold is a different kind of sample from a random one. It is a
particular stretch of the session, with whatever the drift was doing at that
point, so its estimate is noisier from session to session. A random fold averages
over the whole recording and therefore looks stable, which is worth stating
plainly: the leaky estimate is tighter as well as wrong, and tightness is what
people read as reliability.

To price it honestly the data now contains a real relationship, because an
estimator's variance is only interesting when there is something to estimate.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
COUPLING = 0.4
N_PRICE = 40

def spread_of_estimates(scheme, alpha=100.0, n=N_PRICE):
    """The distribution of what each scheme reports, over independent sessions."""
    values = []
    for s in range(n):
        X, y = session(s, RHO, COUPLING)
        if scheme == "honest":
            X_fresh, y_fresh = session(20_000 + s, RHO, COUPLING)
            values.append(corr(Ridge(alpha=alpha).fit(X, y).predict(X_fresh), y_fresh))
        else:
            folds = (random_folds(len(y), K, seed=s) if scheme == "random"
                     else blocked_folds(len(y), K))
            values.append(corr(cross_val_predict(X, y, lambda: Ridge(alpha=alpha), folds), y))
    return float(np.mean(values)), float(np.std(values))

print(f"a REAL relationship this time (coupling {COUPLING}), rho {RHO}, "
      f"{N_PRICE} sessions, ridge alpha=100\\n")
print(f"{'scheme':>28} {'mean reported r':>17} {'SD across sessions':>20}")
price = {}
for scheme in ("random k-fold", "blocked k-fold", "honest"):
    price[scheme] = spread_of_estimates(scheme.split()[0])
    print(f"{scheme:>28} {price[scheme][0]:>17.3f} {price[scheme][1]:>20.3f}")

honest_mean, honest_sd = price["honest"]
random_mean, random_sd = price["random k-fold"]
blocked_mean, blocked_sd = price["blocked k-fold"]

assert random_mean > 2.5 * honest_mean, "the random split still overstates by a wide margin"
assert abs(blocked_mean - honest_mean) < 0.1, "the blocked split lands near the truth"
assert blocked_sd > 1.5 * random_sd, "and pays for that with a noisier estimate"
print(f"\\n  the random split overstated the truth by {random_mean / honest_mean:.1f}x")
print(f"  the blocked split was accurate and about {blocked_sd / random_sd:.1f}x more variable")

print("\\nSo the choice is not between a good estimator and a bad one. It is between an")
print("estimator that is accurate and noisy and one that is precise and wrong, and the")
print("second reports the smaller error bar. A confidence interval computed across")
print("random folds is an interval around a number that does not mean what it says,")
print("which is the failure GRL 4 Section 1 reached from the other side: an error bar")
print("that shrinks with more data is not evidence that a comparison is sound, because")
print("what is wrong with it does not shrink.")
print("\\nThe blocked estimate's extra variance is real information, not a defect. It is")
print("telling you that how well this decoder works depends on which stretch of the")
print("session you ask about, which is a true and useful fact about a drifting")
print("recording, and one the random split averages away.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What the leak actually damages

The obvious worry is that a leaky estimate picks the wrong model. Section 4 tests
that directly, by choosing ridge's penalty with each scheme and then measuring
what the chosen penalty really achieves on a fresh session.

The result is not the obvious one, and it changes what the guardrail at the end
of this section should say.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
import collections

ALPHAS = (1.0, 10.0, 100.0, 1000.0, 10_000.0, 100_000.0)
N_SELECT = 20

chosen = {"random": [], "blocked": []}
achieved = {"random": [], "blocked": []}
reported = {"random": [], "blocked": []}
oracle = []

for s in range(N_SELECT):
    X, y = session(s, RHO, COUPLING)
    X_fresh, y_fresh = session(20_000 + s, RHO, COUPLING)
    truth_by_alpha = {a: corr(Ridge(alpha=a).fit(X, y).predict(X_fresh), y_fresh)
                      for a in ALPHAS}
    oracle.append(max(truth_by_alpha.values()))
    for scheme in ("random", "blocked"):
        folds = (random_folds(len(y), K, seed=s) if scheme == "random"
                 else blocked_folds(len(y), K))
        scores = {a: corr(cross_val_predict(X, y, lambda a=a: Ridge(alpha=a), folds), y)
                  for a in ALPHAS}
        best = max(scores, key=scores.get)
        chosen[scheme].append(best)
        achieved[scheme].append(truth_by_alpha[best])
        reported[scheme].append(scores[best])

print(f"choosing ridge's penalty by cross-validation, {N_SELECT} sessions, "
      f"true coupling {COUPLING}\\n")
print(f"{'scheme':>10} {'alpha it picks':>32} {'r it reports':>13} {'r it achieves':>14}")
for scheme in ("random", "blocked"):
    counts = collections.Counter(chosen[scheme])
    picks = " ".join(f"{a:g}x{counts[a]}" for a in ALPHAS if counts[a])
    print(f"{scheme:>10} {picks:>32} {np.mean(reported[scheme]):>13.3f} "
          f"{np.mean(achieved[scheme]):>14.3f}")
print(f"{'oracle':>10} {'(the best alpha, known only here)':>32} {'-':>13} "
      f"{np.mean(oracle):>14.3f}")

# The model it ends up with is fine. Note what that does and does not show: the
# leaky scheme returned the SAME alpha in every session, so it did not
# discriminate among penalties, it returned a constant that happens to sit near
# the optimum on this grid. The honest scheme genuinely varied.
assert len(set(chosen["random"])) == 1, \\
    "the leaky scheme picked one alpha every time, which is not selection"
assert len(set(chosen["blocked"])) > 1, "while the honest scheme discriminated"
assert np.mean(achieved["random"]) > 0.8 * np.mean(oracle), \\
    "and the constant it returned is still a usable penalty"
assert abs(np.mean(achieved["random"]) - np.mean(achieved["blocked"])) < 0.05, \\
    "and it is not measurably worse at selecting than the honest scheme"
# The number it reports is not fine.
assert np.mean(reported["random"]) > 3 * np.mean(achieved["random"]), \\
    "while the accuracy it reports is several times what it delivers"
assert abs(np.mean(reported["blocked"]) - np.mean(achieved["blocked"])) < 0.1, \\
    "the blocked scheme reports roughly what it delivers"

gap = np.mean(reported["random"]) / np.mean(achieved["random"])
print(f"\\n  the leaky scheme selected a penalty achieving {np.mean(achieved['random']):.3f}, "
      f"against an oracle of {np.mean(oracle):.3f},")
print(f"  and reported {np.mean(reported['random']):.3f}, which is {gap:.1f} times what it delivered")

print("\\nThat is not the failure most people expect, and it is worse in the way that")
print("matters here. The leak did not leave you with a bad model; both schemes ended up")
print("near the oracle. It is worth being precise about why: the leaky scheme returned")
print("the same penalty in every session rather than discriminating among them, and")
print("that constant happens to sit near the optimum on this grid, so 'it selected well'")
print("is generous. What the leak destroyed was the number,")
print("and the number is the deliverable.")
print("and the number is the deliverable. A decoder that genuinely achieves r = 0.2 is")
print("a legitimate finding about a hard problem. The same decoder reported at r = 0.7")
print("is a claim about the brain that is not true, and everything downstream, a power")
print("calculation, a comparison against another cohort, a decision about whether a")
print("contact is worth stimulating, inherits it.")
print("\\nThis is the same shape as INF 1 Section 4. There the estimator was unbiased and")
print("the filter was biased; here the model selection is sound and the reported")
print("accuracy is not. In both cases the machinery works and the sentence written")
print("underneath it is false.")

print("\\n--- A GUARDRAIL THIS CURRICULUM PROPOSES AND DOES NOT ADOPT ---")
print("\\nEvery arithmetic guardrail in configs/guardrails.yaml has a lesson behind it")
print("that measured its number. This lesson has the measurement for one that does not")
print("exist yet:")
print("\\n  G14, cross-validation folds must respect time. Warn when a reported decoding")
print("  accuracy comes from folds drawn at random over an autocorrelated recording,")
print("  and require either contiguous folds or a stated embargo.")
print("\\nThe evidence is Section 2's table: at rho = 0.95 with no relationship at all,")
print("random folds reported 0.59 for a linear model and 0.94 for a flexible one, while")
print("the same recording under contiguous folds reported under 0.10. The rule is")
print("cheap to check, because a run record already knows how the folds were made.")
print("\\nAdding a guardrail changes what the app enforces, so this lesson states the case")
print("and stops. The proposal is in docs/backlog.md.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **k-fold cross-validation is honest when its assumption holds.** On
   independent samples with no true relationship, random and contiguous folds
   both reported nothing, and a hand-written implementation matched
   `sklearn.model_selection.KFold` to 1e-10 on the same split.
2. **The assumption is exchangeability, and neural recordings break it.** With
   the target still generated independently of every channel, random five-fold
   reported r = 0.59 for ridge and r = 0.94 for nearest neighbours at an
   epoch-to-epoch autocorrelation of 0.95. The honest answer in every one of
   those cells is zero, and both a fresh session and a contiguous split of the
   same recording put it under 0.10.
3. **The cause is the autocorrelation, not the model.** At rho = 0 the same code
   on the same models reported nothing, and the inflation grew monotonically with
   rho. The more flexible the model, the more completely it exploits the leak,
   because under a random split the most similar training sample to a test epoch
   is usually the epoch recorded next to it.
4. **The fix costs variance, and the leaky estimate is the tighter one.** With a
   real relationship present, contiguous folds landed near the truth with a
   standard deviation about three times larger than the random split's, while the
   random split sat several times too high with a narrow spread. A tight interval
   around a wrong number is the failure mode GRL 4 Section 1 reached from the
   other direction, where sixteen times the data quartered the error bar and left
   the drift exactly where it was.
5. **What the leak damages is the reported number, not the model.** Choosing
   ridge's penalty by leaky cross-validation selected a penalty that performed
   about as well as the one chosen honestly, and close to the best available, and
   then reported an accuracy several times what it delivered. The machinery
   worked; the sentence written underneath it was false.

That last point is the reason this lesson proposes a guardrail about how folds
are drawn rather than about which model is used. The model was never the problem.

### Exercises

**Exercise 1.** Section 3 used an embargo of 40 epochs without justifying it.
Derive an embargo from the autocorrelation instead: find the lag at which the
autocorrelation of these features falls below 0.1, and check whether an embargo
of that length changes Section 2's blocked column.

**Exercise 2.** The sessions here are one continuous block. Real recordings have
conditions interleaved, and GRL 4 recommends interleaving them. Work out whether
interleaved conditions make the leak better or worse, and what that implies about
combining GRL 4's design advice with this lesson's analysis advice.

**Exercise 3.** Write the check that guardrail G14 would need: given a run
record, decide whether the folds respected time. State what the run record would
have to store that it does not store today, and whether that is a change to
`registry.run` or to the recipe.

---

**Next: DEC 3, backpropagation from scratch.** Everything so far has been linear
and had a closed-form solution. The next lesson removes both of those, and
replaces the closed form with a gradient that can be checked against arithmetic.
''')

m.emit()
verify("09_decoding", "02_cross_validation_on_autocorrelated_data")
print("  DEC 2 OK")
