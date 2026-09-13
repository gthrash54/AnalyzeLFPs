import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("09_decoding", "04_nonlinear_against_linear")

m.md(r'''# Lesson DEC 4: Whether Any of This Beats a Straight Line {{VARIANT}}

**Electives · Machine Learning and Neural Decoding**

{{INSTRUCTIONS}}

DEC 3 built a network that can represent things ridge cannot. Whether to use one
on an intraoperative recording is a different question, and it is usually
answered by reputation rather than by measurement.

It has a measurable answer, and the answer is a boundary rather than a verdict.
It depends on three things you can estimate for your own data: how much of the
signal is out of reach of a linear model, how much noise there is, and how many
trials you have. This lesson locates that boundary, and then asks the question
underneath it, which is whether a single session could tell you which side of the
boundary you are on.

**What it assumes**

| From | What is used |
|---|---|
| DEC 1 | Ridge, and that a penalty has to be chosen on held-out data. |
| DEC 2 | That the held-out data has to respect time, and that a leaky estimate is worse than a noisy one. |
| DEC 3 | What a network is, and that its weights are not identified. |
| INF 1 | That a difference measured once, with a spread larger than itself, is not a result. |

**What it underwrites**

Any claim in this lab that a nonlinear decoder is or is not worth using, and the
trial counts that claim would need.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
from sklearn.linear_model import Ridge
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

rng = np.random.default_rng(73)

N_CONTACTS, N_SOURCES = 16, 3
NOISE = 1.2      # chosen so a linear decoder lands near r = 0.5, as reported values do
MIXING = np.random.default_rng(0).uniform(0.3, 1.0, (N_SOURCES, N_CONTACTS))


def recording(n_trials: int, seed: int, nonlinear_fraction: float) -> tuple:
    """Contacts, and a target of which `nonlinear_fraction` is out of linear reach.

    The linear part is a weighted sum of the sources. The nonlinear part is a
    product of two of them, which no linear function of the contacts can
    represent. Both are standardised before mixing so the fraction means what it
    says.
    """
    gen = np.random.default_rng(seed)
    sources = gen.standard_normal((n_trials, N_SOURCES))
    x = (sources @ MIXING
         + gen.standard_normal((n_trials, 1))
         + 0.3 * gen.standard_normal((n_trials, N_CONTACTS)))
    linear = sources @ np.array([1.0, -0.6, 0.4])
    nonlinear = 1.6 * sources[:, 1] * sources[:, 2]
    linear = linear / linear.std()
    nonlinear = nonlinear / nonlinear.std()
    q = nonlinear_fraction
    y = (np.sqrt(1 - q) * linear + np.sqrt(q) * nonlinear
         + NOISE * gen.standard_normal(n_trials))
    return x, y


def corr(a, b) -> float:
    return float(np.corrcoef(a, b)[0, 1])


def fit_network(X, y, seed):
    """One hidden layer of 32 units, standardised inputs, penalised."""
    return make_pipeline(
        StandardScaler(),
        MLPRegressor(hidden_layer_sizes=(32,), max_iter=3000, random_state=seed,
                     alpha=1.0, learning_rate_init=0.01),
    ).fit(X, y)


print("Environment initialized for Lesson DEC 4")''')

m.task(
'''def fit_ridge(X: np.ndarray, y: np.ndarray) -> Ridge:
    """Ridge with its penalty chosen on held-out data, as DEC 1 and DEC 2 require.

    Hold out the LAST quarter of the trials rather than a random quarter, and
    fit on the rest. Try each alpha, keep the one scoring best on the holdout,
    then refit that alpha on everything.
    """
    # TODO: hold out the last quarter, at least 4 trials
    # TODO: for each alpha in (0.1, 1, 10, 100, 1000), fit on the head and score
    #       on the tail with corr()
    # TODO: refit the winning alpha on all the data and return it
    # TODO: the holdout is contiguous and at the end on purpose. Say why before
    #       you write it, then check your answer against DEC 2 Section 2.
    raise NotImplementedError("Implement fit_ridge")


def sessions_for_power(differences: np.ndarray, alpha: float = 0.05,
                       power: float = 0.8) -> float:
    """How many sessions a paired comparison of this size and spread would need.

    For a paired test the required n is ((z_(1-alpha/2) + z_power) * sd / |mean|)^2.
    Return infinity when the mean difference is exactly zero.
    """
    # TODO: mean and sample standard deviation (ddof=1) of the differences
    # TODO: z_(1-alpha/2) is about 1.96 at alpha=0.05, z_power about 0.84 at 0.8;
    #       get them from scipy.stats.norm.ppf rather than hard-coding
    # TODO: square the whole thing
    raise NotImplementedError("Implement sessions_for_power")''',
'''def fit_ridge(X: np.ndarray, y: np.ndarray) -> Ridge:
    """Ridge with its penalty chosen on held-out data, as DEC 1 and DEC 2 require.

    Hold out the LAST quarter of the trials rather than a random quarter, and
    fit on the rest. Try each alpha, keep the one scoring best on the holdout,
    then refit that alpha on everything.
    """
    holdout = max(4, len(y) // 4)
    best_score, best_alpha = -np.inf, 1.0
    for alpha in (0.1, 1.0, 10.0, 100.0, 1000.0):
        trained = Ridge(alpha=alpha).fit(X[:-holdout], y[:-holdout])
        score = corr(trained.predict(X[-holdout:]), y[-holdout:])
        if score > best_score:
            best_score, best_alpha = score, alpha
    # The holdout is contiguous and at the end because DEC 2 measured what a
    # random holdout does on an autocorrelated recording: it reports a decoder
    # that is not there. Nothing in this lesson would look different if the
    # penalty were chosen on a leaky split, which is exactly the danger.
    return Ridge(alpha=best_alpha).fit(X, y)


def sessions_for_power(differences: np.ndarray, alpha: float = 0.05,
                       power: float = 0.8) -> float:
    """How many sessions a paired comparison of this size and spread would need.

    For a paired test the required n is ((z_(1-alpha/2) + z_power) * sd / |mean|)^2.
    Return infinity when the mean difference is exactly zero.
    """
    d = np.asarray(differences, dtype=float)
    mean = float(d.mean())
    if mean == 0.0:
        return float("inf")
    z_alpha = float(stats.norm.ppf(1 - alpha / 2))
    z_power = float(stats.norm.ppf(power))
    return float(((z_alpha + z_power) * d.std(ddof=1) / abs(mean)) ** 2)''')

m.code('''# --- TEST CELL FOR STEP 0 ---
# Both helpers are checked before anything is concluded with them.
_gen = np.random.default_rng(1)
_X = _gen.standard_normal((200, 5))
_y = _X @ np.array([1.0, 0.0, -1.0, 0.0, 0.5]) + 0.5 * _gen.standard_normal(200)
_fitted = fit_ridge(_X, _y)
assert isinstance(_fitted, Ridge), "fit_ridge returns a fitted Ridge"
assert _fitted.alpha in (0.1, 1.0, 10.0, 100.0, 1000.0), "chosen from the grid"
assert _fitted.n_features_in_ == 5, "and refitted on all the data"
print(f"fit_ridge on an easy linear problem: chose alpha={_fitted.alpha:g}, "
      f"r={corr(_fitted.predict(_X), _y):.3f}")

# The power formula against a case with a known answer. Two points with mean 1
# and sample SD 1 need exactly (z_0.975 + z_0.8)^2 sessions.
_d = np.array([1.0 - np.sqrt(2) / 2, 1.0 + np.sqrt(2) / 2])
assert abs(_d.mean() - 1.0) < 1e-12 and abs(_d.std(ddof=1) - 1.0) < 1e-12
theory = float((stats.norm.ppf(0.975) + stats.norm.ppf(0.8)) ** 2)
print(f"sessions_for_power on a difference of exactly one SD: "
      f"{sessions_for_power(_d):.3f}, theory {theory:.3f}")
assert abs(sessions_for_power(_d) - theory) < 1e-9

# n scales as 1/mean^2, so halving the effect at fixed spread quadruples the cost.
_half = _d - 0.5                       # mean 0.5, same spread
assert abs(_half.std(ddof=1) - 1.0) < 1e-12
assert abs(sessions_for_power(_half) / sessions_for_power(_d) - 4.0) < 1e-9, \\
    "half the effect costs four times the sessions"
assert sessions_for_power(np.array([1.0, -1.0])) == float("inf"), \\
    "a zero mean difference needs infinitely many"

print("\\nStep 0 passed.")''')

m.md(r'''---

## 1. Is there anything to win?

A comparison between model classes is only meaningful if the more flexible class
can do something the simpler one cannot. That has to be established before any
learning curve is drawn, because if the truth is linear then the whole question
is about the cost of flexibility and none of it is about the benefit.

The target here has a dial. At `nonlinear_fraction = 0` the signal is a weighted
sum of the sources, which a linear function of the contacts can represent
exactly. At 0.5 half of it is a product of two sources, which no linear function
can represent at any sample size.

The ceiling is measured with a sample large enough that estimation error is
negligible, so what is left is the representational limit.''')

m.code('''# --- TEST CELL FOR STEP 1 ---
N_CEILING, N_TEST = 20_000, 6000
FRACTIONS = (0.0, 0.25, 0.5)

print(f"ceilings from {N_CEILING} training trials, so estimation error is not the issue\\n")
print(f"{'nonlinear fraction':>19} {'ridge':>8} {'network':>9} {'headroom':>10}")
ceiling = {}
for q in FRACTIONS:
    X_test, y_test = recording(N_TEST, 999, q)
    X_big, y_big = recording(N_CEILING, 5, q)
    ridge_ceiling = corr(Ridge(alpha=1.0).fit(X_big, y_big).predict(X_test), y_test)
    net_ceiling = corr(fit_network(X_big, y_big, 0).predict(X_test), y_test)
    ceiling[q] = (ridge_ceiling, net_ceiling)
    print(f"{q:>19.2f} {ridge_ceiling:>8.3f} {net_ceiling:>9.3f} "
          f"{net_ceiling - ridge_ceiling:>10.3f}")

# With a linear truth there is nothing to win, and the network must not invent any.
assert abs(ceiling[0.0][1] - ceiling[0.0][0]) < 0.03, \\
    "on a linear truth the two classes have the same ceiling"
# With a nonlinear truth there is something real to win.
assert ceiling[0.5][1] - ceiling[0.5][0] > 0.1, "and a nonlinear truth leaves real headroom"
assert ceiling[0.5][0] < ceiling[0.0][0], "which the linear model provably cannot reach"

print("\\nAt a linear truth the two ceilings are the same to three decimals, so any")
print("difference a learning curve shows at that setting is cost rather than benefit.")
print(f"At half the signal nonlinear there is {ceiling[0.5][1] - ceiling[0.5][0]:.2f} of correlation "
      f"that a linear decoder")
print("cannot reach however many trials it is given. That is the prize, and the rest of")
print("this lesson is about what it costs to collect it.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The learning curves, and where they cross

Now the same comparison at sample sizes a real session might supply. Each cell
fits both models on `n` trials and scores them on the same large test set, and
repeats over independent sessions so that the spread is visible.

The spread is not decoration. A table of means alone would answer "which model is
better" and would not answer "could I tell", which is the question Section 4
returns to.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
N_SEEDS = 8
SIZES = (40, 80, 160, 320, 800)

def sweep(q):
    X_test, y_test = recording(N_TEST, 999, q)
    rows = {}
    for n in SIZES:
        ridge_scores, net_scores = [], []
        for s in range(N_SEEDS):
            X_train, y_train = recording(n, 100 + s, q)
            ridge_scores.append(corr(fit_ridge(X_train, y_train).predict(X_test), y_test))
            net_scores.append(corr(fit_network(X_train, y_train, s).predict(X_test), y_test))
        rows[n] = (np.array(ridge_scores), np.array(net_scores))
    return rows

results = {}
for q in FRACTIONS:
    results[q] = sweep(q)
    print(f"\\n  {q:.0%} of the signal is nonlinear "
          f"(ceiling: ridge {ceiling[q][0]:.3f}, network {ceiling[q][1]:.3f})")
    print(f"  {'trials':>8} {'ridge':>16} {'network':>16} {'network ahead':>15}")
    for n in SIZES:
        r, net = results[q][n]
        print(f"  {n:>8} {r.mean():>9.3f}+-{r.std():<5.3f} {net.mean():>9.3f}+-{net.std():<5.3f} "
              f"{np.mean(net > r):>14.0%}")

# (a) On a linear truth, flexibility is a pure cost at every sample size tested.
for n in SIZES:
    r, net = results[0.0][n]
    assert net.mean() <= r.mean() + 0.02, \\
        f"with nothing nonlinear to find, the network cannot beat ridge at n={n}"

# (b) On a nonlinear truth the ordering REVERSES with sample size. That reversal,
# not either endpoint, is the result.
small_r, small_net = results[0.25][SIZES[0]]
large_r, large_net = results[0.25][SIZES[-1]]
assert small_net.mean() < small_r.mean(), "at the smallest sample the linear model wins"
assert large_net.mean() > large_r.mean(), "at the largest it loses"
# The SUSTAINED crossover: the smallest sample from which the network is ahead
# and stays ahead. A single crossing can be sampling noise, and at these spreads
# one usually is.
def sustained_crossover(rows):
    for i, n in enumerate(SIZES):
        if all(rows[m][1].mean() > rows[m][0].mean() for m in SIZES[i:]):
            return n
    return None

crossover = sustained_crossover(results[0.25])
print(f"\\n  at 25% nonlinear, the network takes the lead for good between "
      f"{SIZES[SIZES.index(crossover) - 1]} and {crossover} trials")
assert 100 < crossover < 1000, "and the crossover is in the hundreds, not the tens"
assert sustained_crossover(results[0.0]) is None, \\
    "with a linear truth the network never takes a lasting lead at any size tested"

# (c) Even with half the signal unreachable, the linear model wins at small n.
r_small, net_small = results[0.5][SIZES[0]]
assert abs(net_small.mean() - r_small.mean()) < 0.1, \\
    "at 40 trials the two are indistinguishable even when half the signal is nonlinear"

print("\\nThree readings, and the third is the one that applies here.")
print("\\nOn a linear truth the network never won, at any sample size. Flexibility is not")
print("free even when it goes unused: the extra parameters have to be estimated from")
print("the same trials, and estimating them costs accuracy.")
print("\\nOn a nonlinear truth the ordering reverses. The network is worse at small")
print("samples and better at large ones, and the crossover sits in the hundreds of")
print("trials rather than the tens. Below it the network is paying for a capacity it")
print("cannot yet estimate; above it the capacity starts paying for itself.")
print("\\nAt forty trials, with HALF the signal out of linear reach, the two were")
print("indistinguishable. That is the intraoperative regime. The nonlinearity is still")
print("there and still unreachable by ridge; there is simply not enough data to learn")
print("what shape it has, so the flexible model spends its capacity on noise.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. What the flexible model actually spends

Section 2 shows the network losing at small samples, which is easy to describe as
overfitting and worth being more precise about. DEC 1 measured the same tradeoff
for the ridge penalty; this section measures it for model class.

The comparison below fits both models many times on small samples and separates
how far the average prediction is from the truth from how far individual fits are
from that average, exactly as DEC 1 Section 3 did.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
N_FITS, N_TRAIN_SMALL, Q_MID = 25, 80, 0.25
X_probe, y_probe = recording(1500, 4242, Q_MID)
X_ceiling, y_ceiling = recording(N_CEILING, 5, Q_MID)
best_possible = fit_network(X_ceiling, y_ceiling, 0).predict(X_probe)

def spread_of(fit_fn):
    preds = np.array([fit_fn(*recording(N_TRAIN_SMALL, 7000 + f, Q_MID), f)
                      for f in range(N_FITS)])
    average = preds.mean(axis=0)
    return (float(np.mean((average - best_possible) ** 2)),
            float(np.mean(preds.var(axis=0))))

ridge_bias, ridge_var = spread_of(lambda X, y, f: fit_ridge(X, y).predict(X_probe))
net_bias, net_var = spread_of(lambda X, y, f: fit_network(X, y, f).predict(X_probe))

print(f"{N_FITS} independent sessions of {N_TRAIN_SMALL} trials, {Q_MID:.0%} nonlinear signal\\n")
print(f"{'model':>10} {'bias^2':>10} {'variance':>10} {'total':>10}")
print(f"{'ridge':>10} {ridge_bias:>10.4f} {ridge_var:>10.4f} {ridge_bias + ridge_var:>10.4f}")
print(f"{'network':>10} {net_bias:>10.4f} {net_var:>10.4f} {net_bias + net_var:>10.4f}")

assert net_bias < ridge_bias, "the network is the less biased model, as its ceiling promised"
assert net_var > ridge_var, "and it pays for that in variance"
print(f"\\n  the network cut bias by {(1 - net_bias / ridge_bias):.0%} and multiplied variance by "
      f"{net_var / ridge_var:.1f}x")

print("\\nSo the network is not worse at small samples because it is a bad model. It is")
print("the less biased of the two, which is the whole reason to want it: its average")
print("prediction is closer to what a perfect fit would say. What it cannot do at eighty")
print("trials is hold still, and the variance it pays exceeds the bias it saves.")
print("\\nThat framing predicts the fix and rules one out. More trials reduce variance and")
print("do not touch bias, which is why the curves in Section 2 cross. A stronger penalty")
print("on the network also reduces variance, and it reintroduces bias, which is why it")
print("only helps up to a point. Nothing about choosing a cleverer architecture changes")
print("the arithmetic, because the shortage is trials.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. Could one session tell you?

Sections 2 and 3 used many independent sessions and a test set of six thousand
trials. A real comparison has one session, and the honest question is not which
model is better but whether the data available could establish it.

The table below takes the paired difference between the two models, session by
session, and asks the question INF 1 asks of any effect: how large is it compared
to how much it moves. From that, how many sessions a comparison would need.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
N_PAIRED = 12
X_test_mid, y_test_mid = recording(N_TEST, 999, Q_MID)

print(f"paired difference, network minus ridge, {Q_MID:.0%} nonlinear signal, "
      f"{N_PAIRED} sessions each\\n")
print(f"{'trials':>8} {'mean difference':>17} {'SD of it':>10} {'network ahead':>15} "
      f"{'sessions for 80% power':>24}")
paired = {}
for n in SIZES:
    differences = []
    for s in range(N_PAIRED):
        X_train, y_train = recording(n, 400 + s, Q_MID)
        ridge_score = corr(fit_ridge(X_train, y_train).predict(X_test_mid), y_test_mid)
        net_score = corr(fit_network(X_train, y_train, s).predict(X_test_mid), y_test_mid)
        differences.append(net_score - ridge_score)
    d = np.array(differences)
    needed = sessions_for_power(d)
    paired[n] = (float(d.mean()), float(d.std(ddof=1)), float(np.mean(d > 0)), needed)
    print(f"{n:>8} {d.mean():>+17.3f} {d.std(ddof=1):>10.3f} {np.mean(d > 0):>14.0%} "
          f"{needed:>24.0f}")

# At intraoperative sizes the difference is smaller than its own spread.
assert abs(paired[40][0]) < paired[40][1], \\
    "at 40 trials the difference between the two models is smaller than how much it moves"
assert paired[40][3] > 100, "so a comparison there would need an impossible number of sessions"
# At large sizes the same comparison is easy.
assert paired[800][3] < 20, "at 800 trials a handful of sessions settles it"
assert paired[800][2] > 0.9, "and the network wins in nearly every one"

print(f"\\n  at 40 trials the difference was {paired[40][0]:+.3f} with a spread of "
      f"{paired[40][1]:.3f} across sessions, and the network came out ahead in "
      f"{paired[40][2]:.0%} of them")
print(f"  at 800 trials it was {paired[800][0]:+.3f} with a spread of {paired[800][1]:.3f}, "
      f"and the network came out ahead in {paired[800][2]:.0%}")

print("\\nThe last column is the lesson, and it is not monotone. At forty and eighty")
print(f"trials the comparison needs {paired[40][3]:.0f} and {paired[80][3]:.0f} sessions, because the difference")
print("is smaller than its own run-to-run spread. From a hundred and sixty trials")
print("upward a handful of sessions settles it. So the comparison becomes answerable")
print("at roughly the same trial count at which the answer changes, which is the")
print("awkward part: the regime where you can measure which model is better is not the")
print("regime you are recording in.")
print("\\nWhat that rules out is the sentence 'we tried a neural network and it did")
print("better'. On one session at intraoperative trial counts, which model comes out")
print("ahead is close to a coin flip, and the coin lands on the network often enough")
print("that trying it and keeping the result will produce that sentence regularly. INF 1")
print("Section 4 measured the same shape: a comparison run where power is low reports")
print("the runs that got lucky.")
print("\\nWhat it does not rule out is using a network. The honest version is a prior")
print("decision rather than a per-session comparison. Estimate where you sit on Section")
print("2's boundary from the trial count you can actually collect, choose accordingly,")
print("and record the choice in the analysis plan, where DEC 2's fold rule already has")
print("to be recorded anyway.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **A comparison of model classes needs a headroom measurement first.** With a
   linear truth the two classes had the same ceiling to three decimals, so any
   difference is cost rather than benefit. With half the signal nonlinear the
   network's ceiling was about 0.14 of correlation above the linear one, which no
   number of trials lets a linear decoder reach.
2. **Flexibility is not free when it goes unused.** On a linear truth the network
   never beat ridge at any sample size tested, because its extra parameters still
   have to be estimated from the same trials.
3. **On a nonlinear truth the ordering reverses, and the crossover is in the
   hundreds of trials.** The network was worse at forty and better at eight
   hundred. At forty trials with half the signal out of linear reach the two were
   indistinguishable: the nonlinearity was there and unreachable by ridge, and
   there was still not enough data to learn its shape.
4. **The network is the less biased model and the more variable one.** At eighty
   trials it cut squared bias substantially and multiplied variance several-fold,
   and the variance it paid exceeded the bias it saved. That framing says what
   fixes it, which is trials, and what does not, which is architecture.
5. **At intraoperative trial counts a single session cannot answer the
   question.** At forty trials the paired difference was +0.030 against a
   session-to-session spread of 0.157, with the network ahead in 42 percent of
   sessions, which is a coin flip; establishing the difference would take about
   220 sessions, and about 110 at eighty trials. From a hundred and sixty trials
   upward a handful settles it, and by then the answer has started to change.
   The comparison becomes answerable at roughly the trial count where its answer
   flips, so the regime in which you can measure which model is better is not
   the regime this lab records in.

The practical consequence is that "which model is better here" should be decided
before the recording from the trial count, not after it from the result. Deciding
it afterwards is the selection effect INF 1 measured, wearing different clothes.

### Exercises

**Exercise 1.** The crossover was located at one noise level. Repeat Section 2
with the noise halved and again with it doubled, and say how the crossover trial
count scales with signal-to-noise. Then estimate, from a real `psd_by_condition`
run, which regime this lab's recordings are in.

**Exercise 2.** The network here has 32 hidden units. Sweep that from 4 to 128 at
80 trials and say whether a smaller network recovers the small-sample loss, and
what that implies about the claim that the shortage is trials rather than
architecture.

**Exercise 3.** Section 4 computed sessions needed from a paired difference.
Sessions are not free and trials within a session are cheaper. Work out whether
twelve sessions of 80 trials or three sessions of 320 answers the question
better, and say what assumption about between-session variability your answer
depends on.

---

**Next: DEC 5, what a decoder is telling you about the brain.** Every lesson in
this course has ended on the same warning from a different direction. The last
one states it once, and gives the one thing that can be read off a decoder
honestly.
''')

m.emit()
verify("09_decoding", "04_nonlinear_against_linear")
print("  DEC 4 OK")
