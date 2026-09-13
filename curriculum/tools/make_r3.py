import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("10_stochastic", "03_random_walks_and_spurious_correlation")

m.md(r'''# Lesson STO 3: Random Walks, and Correlations That Are Not There {{VARIANT}}

**Foundations · Probability and Stochastic Processes for Neural Data**

{{INSTRUCTIONS}}

STO 2 ended on a process whose effective sample size barely grew with the
recording. This lesson takes the limiting case, where it does not grow at all.

A random walk has no stationary distribution. It has no mean to converge to, no
variance that settles, and no correlation time after which it forgets. Almost
every habit built on stationary data fails on it, and the failures are not subtle:
Section 3 finds two completely independent series that a standard test calls
significantly correlated in more than nine cases out of ten, with the rate
getting worse the more data you collect.

GRL 4 left an exercise asking what changes when its drift is modelled as a random
walk rather than a slow sinusoid. This lesson answers it, and the answer
qualifies a guardrail that is shipping.

**What it assumes**

| From | What is used |
|---|---|
| STO 1 | That an estimator has a distribution. |
| STO 2 | The autocorrelation function, effective sample size, and that a steep spectrum destroys the benefit of more data. |

**What it underwrites**

A qualification to guardrail **G9**'s excursion-to-effect ratio, and the reason
CON 1 and CON 2's connectivity results need stationary inputs.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
from scipy.signal import detrend, lfilter

rng = np.random.default_rng(307)
BURN_IN = 3000


def random_walk(n: int, n_records: int, gen) -> np.ndarray:
    """A cumulative sum of white noise: the canonical non-stationary process."""
    return np.cumsum(gen.standard_normal((n_records, n)), axis=1)


def ar1(n: int, rho: float, n_records: int, gen) -> np.ndarray:
    """AR(1) of unit variance, for contrast. Stationary for any |rho| < 1."""
    white = gen.standard_normal((n_records, n + BURN_IN))
    return lfilter([np.sqrt(1 - rho ** 2)], [1.0, -rho], white, axis=1)[:, BURN_IN:]


print("Environment initialized for Lesson STO 3")''')

m.md(r'''---

## 1. A process with nowhere to settle

An AR(1) with $|\rho| < 1$ pulls back toward zero: the $\rho$ multiplying the
previous value shrinks it, and the process has a variance it returns to. Set
$\rho = 1$ and the pull disappears. Each step adds noise to wherever the process
already is, so the variance of the position after $t$ steps is exactly $t$, and
grows without bound.

That single change removes the thing every stationary result depends on. There is
no distribution the values are drawn from, so "the mean of this recording" is not
an estimate of anything.''')

m.task(
'''def variance_over_time(process: np.ndarray) -> np.ndarray:
    """Variance across records, at each time point.

    `process` is (n_records, n_times). This is a variance ACROSS realisations at
    a fixed time, which is the thing a stationary process holds constant.
    """
    # TODO: one number per time point
    raise NotImplementedError("Implement variance_over_time")


def excursion(process: np.ndarray) -> np.ndarray:
    """Peak-to-peak range of each record.

    GRL 4 smooths before taking the range, so that its excursion measures drift
    rather than epoch-to-epoch noise. Here the range is taken raw, which for a
    random walk is nearly the same thing and for a noisy series is not.
    """
    # TODO: max minus min along the time axis
    raise NotImplementedError("Implement excursion")''',
'''def variance_over_time(process: np.ndarray) -> np.ndarray:
    """Variance across records, at each time point.

    `process` is (n_records, n_times). This is a variance ACROSS realisations at
    a fixed time, which is the thing a stationary process holds constant.
    """
    return process.var(axis=0)


def excursion(process: np.ndarray) -> np.ndarray:
    """Peak-to-peak range of each record.

    GRL 4 smooths before taking the range, so that its excursion measures drift
    rather than epoch-to-epoch noise. Here the range is taken raw, which for a
    random walk is nearly the same thing and for a noisy series is not.
    """
    return process.max(axis=1) - process.min(axis=1)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
N_RECORDS, N_TIMES = 4000, 2000
gen = np.random.default_rng(1)
walk = random_walk(N_TIMES, N_RECORDS, gen)
stationary = ar1(N_TIMES, 0.9, N_RECORDS, gen)

walk_var = variance_over_time(walk)
ar_var = variance_over_time(stationary)

print(f"variance across {N_RECORDS} records, at four time points\\n")
print(f"{'t':>7} {'random walk':>14} {'t itself':>10} {'AR(1) rho=0.9':>15}")
for t in (10, 100, 1000, 2000):
    print(f"{t:>7} {walk_var[t - 1]:>14.1f} {t:>10} {ar_var[t - 1]:>15.3f}")
    assert abs(walk_var[t - 1] - t) < 0.15 * t, "a random walk's variance IS the elapsed time"

# The stationary process holds still; the walk does not.
assert np.std(ar_var) < 0.1 * np.mean(ar_var), "the AR(1) variance does not change with time"
assert walk_var[-1] > 100 * walk_var[9], "the walk's variance grows without bound"
print(f"\\n  AR(1) variance over the whole record: {ar_var.min():.3f} to {ar_var.max():.3f}")
print(f"  walk variance over the whole record:  {walk_var.min():.3f} to {walk_var.max():.1f}")

print("\\nThe AR(1) has a variance and the walk has a variance-so-far. Every quantity in")
print("this curriculum that is described as 'the' mean or 'the' power of a recording")
print("assumes the first case, and the rest of this lesson is about what goes wrong when")
print("the second one holds.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The excursion is not a property of the recording

GRL 4 defined an excursion as the peak-to-peak wander of a baseline, measured G9
against it, and modelled the drift as one slow sinusoid. A sinusoid has a fixed
amplitude, so its excursion is a fixed number and a ratio against an effect is a
meaningful thing to threshold.

Under a random walk it is not. The walk's variance grows as $t$, so its
peak-to-peak range grows as $\sqrt{t}$: the longer the recording, the larger the
excursion, without limit and without anything changing physiologically.

This is GRL 4's Exercise 1, and the answer is that G9's ratio depends on how long
you recorded.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
gen2 = np.random.default_rng(5)
print(f"mean peak-to-peak excursion over t steps, {2000} records each\\n")
print(f"{'t':>7} {'random walk':>13} {'sqrt(t)':>9} {'ratio':>7} {'AR(1) rho=0.9':>15}")
walk_exc, ar_exc = {}, {}
for t in (10, 100, 1000, 10000):
    walk_exc[t] = float(np.mean(excursion(random_walk(t, 2000, gen2))))
    ar_exc[t] = float(np.mean(excursion(ar1(t, 0.9, 2000, gen2))))
    print(f"{t:>7} {walk_exc[t]:>13.2f} {np.sqrt(t):>9.2f} "
          f"{walk_exc[t] / np.sqrt(t):>7.2f} {ar_exc[t]:>15.2f}")

# The walk's excursion is proportional to sqrt(t); the constant settles.
ratios = [walk_exc[t] / np.sqrt(t) for t in (100, 1000, 10000)]
assert max(ratios) - min(ratios) < 0.2, "the walk's excursion is a fixed multiple of sqrt(t)"
assert walk_exc[10000] / walk_exc[10] > 30, "so it grows without bound"

# The stationary process's excursion grows too, but only logarithmically: it is
# the largest of t draws from a fixed distribution.
assert ar_exc[10000] / ar_exc[10] < 8, "a stationary excursion grows only as sqrt(log t)"
print(f"\\n  over a thousandfold increase in t, the walk's excursion grew "
      f"{walk_exc[10000] / walk_exc[10]:.0f}x")
print(f"  and the stationary process's grew {ar_exc[10000] / ar_exc[10]:.1f}x")

# What that does to G9. The rule fires when excursion / effect exceeds 1.0.
EXCURSION_TO_EFFECT_RATIO = 1.0     # configs/guardrails.yaml, G9
EFFECT = 8.0
print(f"\\n  a fixed effect of {EFFECT:.0f}, and G9 firing at a ratio of "
      f"{EXCURSION_TO_EFFECT_RATIO:.1f}\\n")
print(f"{'recording length':>18} {'excursion':>11} {'ratio':>8} {'G9':>8}")
for t in (10, 100, 1000, 10000):
    ratio = walk_exc[t] / EFFECT
    print(f"{t:>18} {walk_exc[t]:>11.2f} {ratio:>8.2f} "
          f"{'fires' if ratio >= EXCURSION_TO_EFFECT_RATIO else 'quiet':>8}")
quiet_at_short = walk_exc[10] / EFFECT < EXCURSION_TO_EFFECT_RATIO
fires_at_long = walk_exc[10000] / EFFECT >= EXCURSION_TO_EFFECT_RATIO
assert quiet_at_short and fires_at_long, \\
    "the same physiology passes G9 in a short recording and fails it in a long one"

print("\\nThat is GRL 4's Exercise 1 answered, and the answer qualifies the rule rather")
print("than refuting it. Under a sinusoidal drift the excursion is a property of the")
print("recording. Under a random walk it is a property of the recording AND its length,")
print("growing as the square root of it, so the same underlying process passes G9 in a")
print("short recording and fails it in a long one with nothing physiological different.")
print("\\nThe rule is still worth having: an excursion larger than the effect is still a")
print("reason to distrust the comparison, whatever produced it. What the rule cannot do")
print("is be compared across recordings of different lengths, and nothing in the ratio")
print("as reported says how long the recording was.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Two independent walks look strongly correlated

This is the failure that costs the most, because it produces a positive result
rather than a missing one.

Correlate two series that have nothing to do with each other. If they are white
noise the correlation is near zero and a test rejects at its nominal five
percent. If they are random walks, both wander, and over any finite stretch one
wandering series will resemble another far more often than chance allows. The
test does not know that, because it was derived assuming independent samples.

The measurement below is a null: every pair below is generated independently, so
every rejection is false.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def correlation_and_rejection(x, y):
    """Per-record Pearson r, summarised three ways.

    Returns (mean |r|, fraction with |r| above 0.5, fraction the standard t-test
    calls significant at 0.05).
    """
    xc = x - x.mean(axis=1, keepdims=True)
    yc = y - y.mean(axis=1, keepdims=True)
    r = (xc * yc).sum(axis=1) / np.sqrt((xc ** 2).sum(axis=1) * (yc ** 2).sum(axis=1))
    n = x.shape[1]
    t = r * np.sqrt((n - 2) / np.maximum(1 - r ** 2, 1e-12))
    p = 2 * stats.t.sf(np.abs(t), n - 2)
    return float(np.mean(np.abs(r))), float(np.mean(np.abs(r) > 0.5)), float(np.mean(p < 0.05))

N_PAIRS = 3000
print(f"{N_PAIRS} INDEPENDENT pairs. Every rejection below is false.\\n")
print(f"{'n':>7} {'process':>16} {'mean |r|':>10} {'P(|r| > 0.5)':>14} {'rejects at 0.05':>17}")
rejection = {}
for n in (50, 200, 1000):
    g3 = np.random.default_rng(700 + n)
    pairs = {
        "white noise": (g3.standard_normal((N_PAIRS, n)), g3.standard_normal((N_PAIRS, n))),
        "AR(1) rho=0.9": (ar1(n, 0.9, N_PAIRS, g3), ar1(n, 0.9, N_PAIRS, g3)),
        "random walk": (random_walk(n, N_PAIRS, g3), random_walk(n, N_PAIRS, g3)),
    }
    for name, (x, y) in pairs.items():
        mean_r, big, reject = correlation_and_rejection(x, y)
        rejection[(n, name)] = reject
        print(f"{n:>7} {name:>16} {mean_r:>10.3f} {big:>14.3f} {reject:>17.3f}")
    print()

# White noise behaves. Everything else does not.
for n in (50, 200, 1000):
    assert abs(rejection[(n, "white noise")] - 0.05) < 0.02, \\
        "the standard test is correct on the data it was derived for"
    assert rejection[(n, "AR(1) rho=0.9")] > 0.3, "autocorrelation alone breaks it badly"
    assert rejection[(n, "random walk")] > 0.6, "and a random walk breaks it completely"

# The part that makes this different from every other error in the curriculum.
walk_rates = [rejection[(n, "random walk")] for n in (50, 200, 1000)]
print(f"  random walk rejection rate as n grows: " + ", ".join(f"{r:.2f}" for r in walk_rates))
assert walk_rates[0] < walk_rates[1] < walk_rates[2], \\
    "more data makes this WORSE, which almost nothing else in statistics does"
white_rates = [rejection[(n, "white noise")] for n in (50, 200, 1000)]
print(f"  white noise, same sweep:               " + ", ".join(f"{r:.2f}" for r in white_rates))

print("\\nTwo series with nothing in common correlated at about 0.42 on average, and the")
print(f"standard test called it significant in {rejection[(50, 'random walk')]:.0%} of pairs at fifty samples and")
print(f"{rejection[(1000, 'random walk')]:.0%} at a thousand. The rate rises with the amount of data, which is worth")
print("sitting with: collecting more of this recording makes a false result more likely,")
print("not less, because a longer walk wanders further and looks more like a trend.")
print("\\nAn AR(1) at rho 0.9 is not safe either, at around half. It is a stationary")
print("process, so the rate at least stops rising, but STO 2 already said why the test")
print("fails: it counts samples where it should count independent samples.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What to do, and what it costs

Two treatments are in common use and only one of them works.

**Detrending** removes a fitted straight line. It is the obvious move and it
addresses the wrong thing: a random walk is not a trend plus noise, it is a
process whose direction changes at random, so removing one straight line leaves
most of the wander behind.

**Differencing** replaces each series with its step-to-step changes. The
increments of a random walk are white by construction, so the test's assumption
is restored exactly. The cost is not statistical but scientific: a test on
differences asks whether the two series *change* together, which is a different
question from whether their *levels* go together, and if the science is about
levels then the answer does not address it.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
N_TREAT = 3000
print(f"two INDEPENDENT random walks, {N_TREAT} pairs, three treatments\\n")
print(f"{'n':>7} {'treatment':>20} {'mean |r|':>10} {'rejects at 0.05':>17}")
treated = {}
for n in (100, 500, 2000):
    g4 = np.random.default_rng(1500 + n)
    x, y = random_walk(n, N_TREAT, g4), random_walk(n, N_TREAT, g4)
    for name, fx, fy in (("raw levels", x, y),
                         ("linear detrend", detrend(x, axis=1), detrend(y, axis=1)),
                         ("first difference", np.diff(x, axis=1), np.diff(y, axis=1))):
        mean_r, _, reject = correlation_and_rejection(fx, fy)
        treated[(n, name)] = (mean_r, reject)
        print(f"{n:>7} {name:>20} {mean_r:>10.3f} {reject:>17.3f}")
    print()

for n in (100, 500, 2000):
    assert treated[(n, "first difference")][1] < 0.08, \\
        f"differencing restores the nominal rate exactly, at n={n}"
    assert treated[(n, "linear detrend")][1] > 0.5, \\
        "while detrending leaves most of the problem in place"
print(f"  detrending at n=2000 still rejects {treated[(2000, 'linear detrend')][1]:.0%} "
      f"of the time, against a nominal 5")

# The cost, measured. A relationship that lives in the LEVELS survives
# differencing badly once there is any observation noise.
print("\\nnow a REAL relationship: two channels sharing one drifting source, plus noise\\n")
print(f"{'observation noise':>18} {'levels |r|':>12} {'detected':>10} "
      f"{'differences |r|':>17} {'detected':>10}")
g5 = np.random.default_rng(21)
shared = random_walk(500, N_TREAT, g5)
cost = {}
for noise_sd in (0.5, 2.0):
    x = shared + noise_sd * g5.standard_normal((N_TREAT, 500))
    y = shared + noise_sd * g5.standard_normal((N_TREAT, 500))
    lr, _, ld = correlation_and_rejection(x, y)
    dr, _, dd = correlation_and_rejection(np.diff(x, axis=1), np.diff(y, axis=1))
    levels, diffs = (lr, ld), (dr, dd)
    cost[noise_sd] = (levels, diffs)
    print(f"{noise_sd:>18.1f} {levels[0]:>12.3f} {levels[1]:>10.3f} "
          f"{diffs[0]:>17.3f} {diffs[1]:>10.3f}")

assert cost[2.0][0][0] > 0.8, "the relationship in the levels is strong and real"
assert cost[2.0][1][0] < 0.3, "and differencing throws most of it away"
assert cost[2.0][1][1] < 0.85, "including the ability to detect it at all"

print("\\nDifferencing was exact at every sample size, and detrending was not close: a")
print("random walk is not a line plus noise, so removing a line does not remove it.")
print("\\nThe cost is real and it is not statistical. When the two channels share a")
print("drifting source and each is observed with noise, the relationship lives in the")
print("levels: at an observation noise of 2.0 the levels correlate 0.93 and the")
print("differences 0.11, and the test on differences misses it a third of the time. The")
print("increments of a slow shared process are mostly observation noise, so differencing")
print("is a filter that removes the signal along with the problem.")
print("\\nThe honest summary is that a correlation between two non-stationary series")
print("cannot be rescued by a transformation, because the question itself is")
print("ill-posed: 'do these levels move together' has no stable answer when neither has")
print("a level. Difference them and you have asked a well-posed and different question.")
print("Which of the two you want is a scientific decision that has to be made before the")
print("test, not chosen from whichever gives a smaller p-value.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **A random walk has no stationary distribution.** Its variance across records
   equals the elapsed time exactly, so "the mean of this recording" estimates
   nothing, while an AR(1)'s variance held constant across the same span.
2. **Its excursion grows as $\sqrt{t}$, without limit.** Over a thousandfold
   increase in recording length the walk's peak-to-peak range grew about
   fortyfold, while a stationary process's grew fivefold. The second is the
   sqrt(2 ln t) growth of a maximum over more draws, which is why it is slow.
3. **That qualifies G9.** The rule compares an excursion to an effect at a fixed
   ratio of 1.0. Under a sinusoidal drift, which is what GRL 4 modelled, the
   excursion is a property of the recording. Under a random walk it is a property
   of the recording and its duration, so the same physiology passes G9 in a short
   recording and fails it in a long one. The ratio as reported does not say how
   long the recording was.
4. **Two independent random walks correlate at about 0.42, and the standard test
   calls it significant in 66 to 93 percent of pairs.** The rate rises with the
   amount of data, which almost nothing else in statistics does: a longer walk
   wanders further and resembles a trend more. An AR(1) at 0.9 rejects around
   half the time; white noise rejects at the nominal five percent.
5. **Detrending does not fix it and differencing does, at a price.** Linear
   detrending still rejected more than 90 percent of the time at 2000 samples,
   because a walk is not a line plus noise. Differencing restored the nominal
   rate exactly at every size. But when two channels share a drifting source and
   each carries observation noise, the relationship lives in the levels: at a
   noise of 2.0 the levels correlated 0.93 and the differences 0.11.

The general statement, which STO 2 reached from the other side: a question about
levels has no stable answer when the levels have no distribution. Differencing
does not answer that question better, it replaces it with a different one, and
which question you want is decided before the data, not after.

### Exercises

**Exercise 1.** Section 2 shows G9's ratio depends on recording length under a
walk. Propose what the run record would have to store for the ratio to be
comparable across runs, and check whether `dbsspeech.registry` already stores it.

**Exercise 2.** CON 1 measured a phase-locking value of 1.0000 under volume
conduction, on stationary simulated data. Repeat its measurement with a slow
random-walk component added to both channels and say whether the zero-lag
diagnostic still separates volume conduction from interaction.

**Exercise 3.** The two-sided choice in Section 4 has a third option this lesson
did not test: model the shared drift explicitly and test the residual. Implement
it for the Section 4 example, and say what it assumes that differencing does not.

---

**Next: STO 4, processes made of events rather than samples.** Spike trains are
not time series, and the estimators this course has built do not apply to them
unchanged. SPK 4's phase-locking null comes out of that lesson.
''')

m.emit()
verify("10_stochastic", "03_random_walks_and_spurious_correlation")
print("  STO 3 OK")
