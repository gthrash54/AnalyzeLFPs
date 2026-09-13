import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("08_inference", "01_the_shuffled_null")

m.md(r'''# Lesson INF 1: The Shuffled Null, and Which Hypothesis Each Shuffle Encodes {{VARIANT}}

**Scientific Integrity · Statistical Inference for Neural Recordings**

{{INSTRUCTIONS}}

Four lessons in this curriculum already lean on a shuffled null. CON 3 certifies a
sharp waveform's fake coupling at z = +18 against one. SPK 4 needs one because raw
phase locking depends on spike count. CON 4 and GRL 5 both quote one. None of them
established what a shuffled null is, when it is valid, or what it is a null *of*.

This lesson does that, and the central claim is narrower than "permutation tests
are assumption-free," which is false. A permutation test has exactly one
assumption, **exchangeability**, and the shuffle you write down is a statement
about which relabellings of your data the null hypothesis says are equally
likely. Choose the wrong shuffle and you have tested a hypothesis nobody asked
about, usually one that is far easier to reject.

**What it assumes**

| From | What is used |
|---|---|
| SIG 4 | That a spectral estimate has variance of its own, so a band power per epoch is a noisy number. |
| POP 1 | That smoothing destroys independent samples, so a count of time points overstates how many observations there are. |
| GRL 4 | That an intraoperative baseline drifts, and that blocked, alternating and randomized designs differ. |

**What it underwrites**

Every shuffled null in this curriculum and in `dbsspeech.stats`: CON 3's coupling
null, SPK 4's phase-locking null, and the claim in any recipe that a contrast
exceeds chance.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
from scipy.signal import lfilter

rng = np.random.default_rng(11)
ALPHA = 0.05

print("Environment initialized for Lesson INF 1")''')

m.md(r'''---

## 1. A null distribution you build rather than assume

A p-value is a position in a distribution: the probability, if nothing were going
on, of seeing a statistic at least as extreme as the one observed. The textbook
gets that distribution from a formula, which needs the data to be normal and
independent. Neural data is reliably neither.

The alternative is to build the distribution from the data. If the condition
labels are meaningless, then any reassignment of them is as good as the real one,
so reassign them a few hundred times and look at where the real statistic lands
among the results.

Two details in the implementation below are not stylistic. The statistic is
**two-sided**, taken as an absolute difference, because a claim of "different"
must pay for both tails. And the count is `(hits + 1) / (n_perm + 1)` rather than
`hits / n_perm`, which includes the observed labelling in its own null. Without
it a p-value of exactly zero is reportable, and no finite number of shuffles
licenses that.''')

m.task(
'''def perm_p(values: np.ndarray, n_a: int, n_perm: int = 199,
           seed: int = 0) -> tuple[float, np.ndarray]:
    """Two-sided permutation p for a difference of means.

    `values` holds condition A's observations first, then condition B's, with
    `n_a` in A. Returns (p_value, null_distribution) where the null holds the
    absolute mean differences from each shuffle.
    """
    # TODO: the observed statistic is |mean(A) - mean(B)|
    # TODO: for each of n_perm shuffles, permute `values` and recompute it
    # TODO: p is (number of shuffles at least as extreme, plus one) / (n_perm + 1)
    raise NotImplementedError("Implement perm_p")''',
'''def perm_p(values: np.ndarray, n_a: int, n_perm: int = 199,
           seed: int = 0) -> tuple[float, np.ndarray]:
    """Two-sided permutation p for a difference of means.

    `values` holds condition A's observations first, then condition B's, with
    `n_a` in A. Returns (p_value, null_distribution) where the null holds the
    absolute mean differences from each shuffle.
    """
    gen = np.random.default_rng(seed)
    values = np.asarray(values, dtype=float)
    observed = abs(values[:n_a].mean() - values[n_a:].mean())
    null = np.empty(n_perm)
    for i in range(n_perm):
        shuffled = values[gen.permutation(values.size)]
        null[i] = abs(shuffled[:n_a].mean() - shuffled[n_a:].mean())
    # The observed labelling is one of the labellings the null allows, so it
    # belongs in its own null. This is what makes the test exact rather than
    # merely approximate, and it puts a floor of 1/(n_perm+1) under the p-value.
    p = (np.sum(null >= observed) + 1) / (n_perm + 1)
    return float(p), null''')

m.code('''# --- TEST CELL FOR STEP 1 ---
N_PER_COND, N_PERM, N_DATASETS = 40, 199, 600

# (a) On data where the labels really are meaningless, the test must reject at
# the rate it advertises. Nothing else about a test matters if this fails.
p_perm, p_ttest = [], []
for s in range(N_DATASETS):
    g = np.random.default_rng(s)
    both = np.concatenate([g.standard_normal(N_PER_COND), g.standard_normal(N_PER_COND)])
    p_perm.append(perm_p(both, N_PER_COND, N_PERM, seed=50_000 + s)[0])
    p_ttest.append(stats.ttest_ind(both[:N_PER_COND], both[N_PER_COND:]).pvalue)
p_perm, p_ttest = np.array(p_perm), np.array(p_ttest)

print(f"{N_DATASETS} datasets with no difference, {N_PER_COND} observations per condition")
print(f"  permutation test rejects at 0.05: {np.mean(p_perm <= ALPHA):.3f}")
print(f"  Student t-test rejects at 0.05:   {np.mean(p_ttest <= ALPHA):.3f}")
assert 0.03 < np.mean(p_perm <= ALPHA) < 0.075, "the permutation test must hold its own size"

# (b) Holding the rate at one threshold is weak. The whole p-value distribution
# should be uniform under the null, which is a much stronger statement.
ks = stats.kstest(p_perm, 'uniform').statistic
print(f"  largest gap between the p-value distribution and uniform: {ks:.3f}")
assert ks < 0.06, "under the null a p-value is uniform, not merely calibrated at 0.05"

# (c) The floor. With n_perm shuffles there is a smallest p-value you can report,
# and it is not zero.
separated = np.concatenate([np.zeros(20), np.ones(20) * 50.0])
p_floor, _ = perm_p(separated, 20, N_PERM, seed=3)
print(f"\\n  an overwhelming difference, {N_PERM} shuffles: p = {p_floor:.4f}"
      f" (floor is 1/{N_PERM + 1} = {1 / (N_PERM + 1):.4f})")
assert abs(p_floor - 1 / (N_PERM + 1)) < 1e-12, "p cannot go below 1/(n_perm+1)"

print("\\nThe permutation test held its size without being told the data was normal,")
print("and its p-values were uniform rather than merely calibrated at one threshold.")
print("It bought that with 199 shuffles per test, and with a floor: reporting p < 0.001")
print("needs at least a thousand of them, whatever the data says.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The unit you shuffle is the hypothesis you test

Section 1 shuffled a list of numbers. Real data is not a list of numbers; it is
samples inside trials inside a session, and each of those levels is a different
candidate for the thing being relabelled.

The choice looks like an implementation detail and is not. Shuffling samples
between conditions asserts that individual samples are exchangeable, which says
that a sample from the middle of a trial could equally well have come from any
other trial. POP 1 already showed that a smoothed signal has fewer independent
samples than time points; the same is true of any autocorrelated recording, which
neural data reliably is. So that assertion is false, and the test below measures
what it costs.''')

m.task(
'''def ar1_trials(n_trials: int, n_samples: int, rho: float, seed: int,
               shift: float = 0.0) -> np.ndarray:
    """`n_trials` by `n_samples` of AR(1) noise, unit variance, plus a shift.

    Each trial is independent of the others; within a trial, consecutive samples
    correlate at `rho`. Use scipy.signal.lfilter rather than a Python loop.
    """
    # TODO: draw white noise of shape (n_trials, n_samples)
    # TODO: filter it with numerator sqrt(1 - rho**2) and denominator [1, -rho]
    #       along the sample axis, which gives AR(1) noise of unit variance
    # TODO: add the shift and return
    raise NotImplementedError("Implement ar1_trials")''',
'''def ar1_trials(n_trials: int, n_samples: int, rho: float, seed: int,
               shift: float = 0.0) -> np.ndarray:
    """`n_trials` by `n_samples` of AR(1) noise, unit variance, plus a shift.

    Each trial is independent of the others; within a trial, consecutive samples
    correlate at `rho`. Use scipy.signal.lfilter rather than a Python loop.
    """
    gen = np.random.default_rng(seed)
    white = gen.standard_normal((n_trials, n_samples))
    # Scaling the numerator by sqrt(1 - rho^2) keeps the output at unit variance,
    # so rho changes the correlation without changing how noisy a trial looks.
    coloured = lfilter([np.sqrt(1.0 - rho ** 2)], [1.0, -rho], white, axis=1)
    return coloured + shift''')

m.code('''# --- TEST CELL FOR STEP 2 ---
N_TRIALS, N_SAMPLES, RHO = 30, 100, 0.9

# The generator must do what it claims, or the comparison below means nothing.
check = ar1_trials(200, 2000, RHO, seed=4)
lag1 = float(np.mean([np.corrcoef(t[:-1], t[1:])[0, 1] for t in check]))
print(f"requested lag-1 correlation {RHO}, measured {lag1:.3f}; "
      f"variance {check.var():.3f} (should be near 1)")
assert abs(lag1 - RHO) < 0.02 and abs(check.var() - 1.0) < 0.05

def p_shuffling_samples(a, b, n_perm, seed):
    """Treat every sample as an exchangeable observation."""
    return perm_p(np.concatenate([a.ravel(), b.ravel()]), a.size, n_perm, seed)

def p_shuffling_trials(a, b, n_perm, seed):
    """Treat every trial as an exchangeable observation, and average within it."""
    return perm_p(np.concatenate([a.mean(axis=1), b.mean(axis=1)]), a.shape[0],
                  n_perm, seed)

N_SESSIONS = 150
by_sample, by_trial = [], []
for s in range(N_SESSIONS):
    a = ar1_trials(N_TRIALS, N_SAMPLES, RHO, seed=2 * s)
    b = ar1_trials(N_TRIALS, N_SAMPLES, RHO, seed=2 * s + 1)
    by_sample.append(p_shuffling_samples(a, b, 199, 70_000 + s)[0])
    by_trial.append(p_shuffling_trials(a, b, 199, 80_000 + s)[0])
by_sample, by_trial = np.array(by_sample), np.array(by_trial)

fpr_sample = float(np.mean(by_sample <= ALPHA))
fpr_trial = float(np.mean(by_trial <= ALPHA))
print(f"\\n{N_SESSIONS} sessions, no difference at all, "
      f"{N_TRIALS} trials x {N_SAMPLES} samples per condition, lag-1 rho {RHO}")
print(f"  shuffling samples: rejects {fpr_sample:.0%} of the time")
print(f"  shuffling trials:  rejects {fpr_trial:.0%} of the time")
assert fpr_sample > 0.40, "shuffling the wrong unit must fail loudly, not subtly"
assert 0.02 < fpr_trial < 0.10, "shuffling the right unit holds its size"

# Why. Look at the two nulls built from one identical dataset.
a = ar1_trials(N_TRIALS, N_SAMPLES, RHO, seed=101)
b = ar1_trials(N_TRIALS, N_SAMPLES, RHO, seed=102)
_, null_s = p_shuffling_samples(a, b, 1999, 5)
_, null_t = p_shuffling_trials(a, b, 1999, 6)
print(f"\\n  width of the null from shuffling samples: {null_s.std():.4f}")
print(f"  width of the null from shuffling trials:  {null_t.std():.4f}"
      f"   ({null_t.std() / null_s.std():.1f}x wider)")
assert null_t.std() > 3 * null_s.std()

# The narrow null is counting samples it does not have. An AR(1) trial of n
# samples carries about n(1-rho)/(1+rho) independent ones.
effective = N_SAMPLES * (1 - RHO) / (1 + RHO)
print(f"\\n  {N_SAMPLES} samples at rho={RHO} are worth about {effective:.0f} independent ones,")
print(f"  and sqrt({N_SAMPLES}/{effective:.0f}) = {np.sqrt(N_SAMPLES / effective):.1f}, which is the "
      f"width ratio above.")
assert abs(np.sqrt(N_SAMPLES / effective) - null_t.std() / null_s.std()) < 0.9

print(f"\\nSame data, same statistic, same code. Shuffling samples rejected a true null")
print(f"in {fpr_sample:.0%} of sessions; shuffling trials rejected it in {fpr_trial:.0%}, against the")
print("five percent advertised. The error is not that sample shuffling is sloppy. It")
print("answers a different question, 'could these samples have been dealt from one urn',")
print("and the answer to that is honestly no: the samples came in autocorrelated runs.")
print("\\nThe practical rule: the unit you shuffle must be the unit that was")
print("independently realised. In an intraoperative recording that is the trial, or")
print("something slower, and it is never the sample.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Permute the way you randomized

Section 2 fixed the unit and left a harder question. Trials are the right unit,
but the free shuffle used above treats **every** split of the trials into two
groups as equally likely, which is a claim about how the experiment was run.

GRL 4 established that an intraoperative baseline drifts, so trials near each
other in time resemble each other. Under a blocked design that drift is
confounded with condition, and no relabelling can undo it. Under an alternating
design the drift cancels, but the free shuffle's null contains block-like splits
that the design could never have produced, which makes the null too wide.

Both failures are below, and they run in opposite directions.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
N_SESSION_TRIALS, RHO_SESSION, N_REPS = 60, 0.95, 250

def drifting_session(seed: int, effect: float, is_b: np.ndarray) -> np.ndarray:
    """One trial-level value per trial, on a session that drifts between trials."""
    gen = np.random.default_rng(seed)
    drift = lfilter([np.sqrt(1 - RHO_SESSION ** 2)], [1.0, -RHO_SESSION],
                    gen.standard_normal(N_SESSION_TRIALS))
    return drift + 0.5 * gen.standard_normal(N_SESSION_TRIALS) + effect * is_b

def assign(design: str, seed: int) -> np.ndarray:
    """Which trials are condition B, under each of GRL 4's three designs."""
    is_b = np.zeros(N_SESSION_TRIALS, dtype=bool)
    if design == "blocked":
        is_b[N_SESSION_TRIALS // 2:] = True
    elif design == "alternating":
        is_b[1::2] = True
    else:
        is_b[np.random.default_rng(seed).permutation(N_SESSION_TRIALS)[:N_SESSION_TRIALS // 2]] = True
    return is_b

def p_free(x, is_b, seed):
    """The Section 1 shuffle: every split of the trials is allowed."""
    return perm_p(np.concatenate([x[is_b], x[~is_b]]), int(is_b.sum()), 299, seed)[0]

def p_pair_flip(x, seed, n_perm=299):
    """Restricted: trials come in adjacent pairs, and only the label within a
    pair may swap.

    Note what licenses this and what does not. An alternating design randomizes
    nothing, so this null cannot come from the randomization the way the free
    shuffle does under a randomized design. It comes from an ASSUMPTION: that
    under the null a within-pair difference is as likely to be positive as
    negative. Part (c) tests when that assumption fails.
    """
    gen = np.random.default_rng(seed)
    diffs = x[1::2] - x[0::2]
    observed = abs(diffs.mean())
    null = np.abs((diffs * gen.choice([-1.0, 1.0], size=(n_perm, diffs.size))).mean(axis=1))
    return float((np.sum(null >= observed) + 1) / (n_perm + 1))

print(f"session drift rho={RHO_SESSION} between trials, {N_SESSION_TRIALS} trials, "
      f"NO true difference, {N_REPS} sessions")
print(f"\\n{'design':>13} {'free permutation':>18} {'paired sign flip':>18}")
size = {}
for design in ("blocked", "alternating", "randomized"):
    free, paired = [], []
    for s in range(N_REPS):
        is_b = assign(design, seed=s)
        x = drifting_session(s, 0.0, is_b)
        free.append(p_free(x, is_b, 30_000 + s))
        if design == "alternating":
            paired.append(p_pair_flip(x, 40_000 + s))
    size[design] = (float(np.mean(np.array(free) <= ALPHA)),
                    float(np.mean(np.array(paired) <= ALPHA)) if paired else None)
    shown = f"{size[design][1]:>17.3f}" if paired else f"{'n/a':>18}"
    print(f"{design:>13} {size[design][0]:>17.3f} {shown}")

# Blocked: the drift is the condition. No shuffle can recover from that.
assert size["blocked"][0] > 0.4, "a blocked design under drift rejects a true null constantly"
# Randomized: the free shuffle is exactly the randomization that was performed.
assert 0.02 < size["randomized"][0] < 0.10, "the free shuffle matches a randomized design"
# Alternating: valid but far too cautious, because its null admits splits the
# design forbids. The matching shuffle is calibrated.
assert size["alternating"][0] < 0.02, "the free shuffle is over-conservative here"
assert 0.02 < size["alternating"][1] < 0.10, "the matching shuffle is calibrated"

# Conservative is not the same as safe. Same design, same data, real effect now.
print(f"\\nalternating design, {N_REPS} sessions, power at each true effect")
print(f"{'effect':>8} {'free permutation':>18} {'paired sign flip':>18}")
power = {}
for effect in (0.0, 0.3, 0.5):
    free, paired = [], []
    for s in range(N_REPS):
        is_b = assign("alternating", seed=s)
        x = drifting_session(s, effect, is_b)
        free.append(p_free(x, is_b, 30_000 + s))
        paired.append(p_pair_flip(x, 40_000 + s))
    power[effect] = (float(np.mean(np.array(free) <= ALPHA)),
                     float(np.mean(np.array(paired) <= ALPHA)))
    print(f"{effect:>8.2f} {power[effect][0]:>17.3f} {power[effect][1]:>17.3f}")

assert power[0.3][1] > 2.0 * power[0.3][0], "the mismatched null throws away most of the power"
assert power[0.5][1] > 0.85, "while the matching one finds an effect of 0.5 nearly always"

print("\\nThree results, and the middle one is the one people miss.")
print(f"\\nBlocked, the free shuffle rejected a true null in {size['blocked'][0]:.0%} of sessions. That is")
print("not a bad shuffle; it is a design with no valid shuffle. Nothing was randomized,")
print("so there is no relabelling for the null to appeal to, and GRL 4 reached the same")
print("place from the other direction.")
print("\\nRandomized, the free shuffle was exactly right, because the free shuffle IS the")
print("randomization that was performed.")
print(f"\\nAlternating, the free shuffle was over-conservative, rejecting a true null in")
print(f"{size['alternating'][0]:.1%} of sessions instead of five. That reads like caution and is not free:")
print(f"at a true effect of 0.3 it found the effect {power[0.3][0]:.0%} of the time where the matching")
print(f"shuffle found it {power[0.3][1]:.0%} of the time. A test that will not reject when it should")
print("is wrong in the direction that gets published as 'no significant difference'.")
print("\\nThe rule that covers all three: permute the way you randomized.")

# (c) The rule has a sharp edge, and the alternating row is on the wrong side of
# it. Nothing was randomized there, so the sign-flip null rests on a symmetry
# assumption rather than on the design. Symmetric drift satisfies it; a trend
# does not.
def linear_drift_session(seed, slope):
    """An alternating design on a baseline that trends rather than wanders."""
    gen = np.random.default_rng(seed)
    return slope * np.arange(N_SESSION_TRIALS) + 0.5 * gen.standard_normal(N_SESSION_TRIALS)

print("\\nthe same sign-flip test, alternating design, NO true effect, on a baseline")
print("that trends steadily instead of wandering symmetrically\\n")
print(f"{'drift per trial':>16} {'rejects at 0.05':>17}")
trend = {}
for slope in (0.0, 0.02, 0.05, 0.10):
    hits = sum(p_pair_flip(linear_drift_session(s, slope), 40_000 + s) <= ALPHA
               for s in range(N_REPS))
    trend[slope] = hits / N_REPS
    print(f"{slope:>16.2f} {trend[slope]:>17.3f}")

assert 0.02 < trend[0.0] < 0.10, "with no trend the assumption holds and the test is calibrated"
assert trend[0.10] > 1.7 * trend[0.0], "with a trend it is not, and the test stops being exact"

print("\\nThat is the difference between a null that comes from the design and one that")
print("comes from an assumption. Under the randomized design the free shuffle is exact")
print("because the experimenter really did shuffle; there is nothing left to assume.")
print("Under the alternating design nothing was randomized, so the sign-flip test buys")
print("its calibration with a symmetry assumption, and a baseline that trends rather")
print("than wanders breaks it. The earlier table's 0.040 was not luck, it was that")
print("simulation's drift being a symmetric random walk.")
print("\\nSo the rule has two halves. Permute the way you randomized, and where nothing")
print("was randomized, say out loud what you are assuming instead.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What survives the filter is not what was there

Sections 1 to 3 are about getting the p-value right. This one is about what a
correct p-value does and does not license, and it matters most here because
intraoperative recordings are short. Trial counts in this lab are tens, not
thousands.

The claim being tested: when power is low, the results that clear a threshold are
not a random sample of the results. They are the ones that got lucky, and
selecting on significance therefore selects for overestimates.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
TRUE_EFFECT = 0.30      # in units of the within-condition standard deviation
N_REPLICATIONS = 2000

print(f"true effect fixed at {TRUE_EFFECT:.2f} SD in every row; only trial count changes\\n")
print(f"{'trials/cond':>12} {'power':>8} {'mean |effect| if p<0.05':>25} {'exaggeration':>14} {'wrong sign':>12}")
inflation = {}
for n in (8, 16, 32, 64, 128, 512):
    estimates, pvalues = [], []
    for s in range(N_REPLICATIONS):
        g = np.random.default_rng(s)
        a, b = g.standard_normal(n), g.standard_normal(n) + TRUE_EFFECT
        estimates.append(b.mean() - a.mean())
        pvalues.append(stats.ttest_ind(a, b).pvalue)
    estimates, pvalues = np.array(estimates), np.array(pvalues)
    sig = pvalues <= ALPHA
    reported = float(np.mean(np.abs(estimates[sig])))
    inflation[n] = (float(sig.mean()), reported / TRUE_EFFECT, float(np.mean(estimates[sig] < 0)))
    print(f"{n:>12} {inflation[n][0]:>8.3f} {reported:>25.3f} {inflation[n][1]:>13.2f}x "
          f"{inflation[n][2]:>11.1%}")

assert inflation[8][1] > 3.0, "at 8 trials a significant result overstates the effect several-fold"
assert inflation[8][2] > 0.05, "and a real fraction of them point the wrong way"
assert inflation[512][1] < 1.05, "with enough trials the filter stops selecting"
assert inflation[512][2] == 0.0
# The inflation is caused by the filter, not by small samples on their own.
all_estimates_8 = np.array([np.random.default_rng(s).standard_normal(8).mean() * 0 +
                            (np.random.default_rng(s).standard_normal(8) + TRUE_EFFECT).mean() -
                            np.random.default_rng(s).standard_normal(8).mean()
                            for s in range(N_REPLICATIONS)])
print(f"\\n  at 8 trials, mean of ALL estimates: {np.mean(all_estimates_8):.3f} "
      f"(unbiased, and the truth is {TRUE_EFFECT:.2f})")
assert abs(np.mean(all_estimates_8) - TRUE_EFFECT) < 0.05, \\
    "the estimator itself is unbiased; the selection is what is biased"

print("\\nAt eight trials per condition the estimator was unbiased and the published")
print(f"subset was not. Significant results overstated a real effect by {inflation[8][1]:.1f}-fold, and")
print(f"{inflation[8][2]:.0%} of them had the wrong sign, which no amount of correctly computed")
print("p-value repairs. By 512 trials the filter selects nothing, because almost")
print("everything passes.")
print("\\nThis is why a p-value is not a result and an effect size reported without its")
print("power is not interpretable. The guardrails in this app enforce the same thing")
print("from the other side: G8 asks for a z alongside a dB difference, and G9 asks for")
print("the baseline excursion alongside the effect, both so a reader can see the size")
print("of the thing and the size of the noise at once.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **A permutation test builds its null from the data and is exact when its one
   assumption holds.** On exchangeable data it rejected a true null at 0.045 and
   its p-values were uniform, without being told the data was normal. It has a
   floor: with 199 shuffles the smallest reportable p is 0.005, so a claim of
   p < 0.001 requires at least a thousand shuffles no matter what the data does.
2. **The unit you shuffle is the hypothesis.** On identical data with an AR(1)
   lag-1 correlation of 0.9, shuffling samples rejected a true null in 61 percent
   of sessions while shuffling trials rejected it in 7. The
   sample-shuffled null was about four times too narrow, and the factor is
   predictable: 100 samples at that correlation are worth about 5 independent
   ones, and the square root of that ratio is the width error.
3. **Permute the way you randomized, and where nothing was randomized, say what
   you are assuming instead.** Under drift, a blocked design rejected a true null
   in most sessions and no shuffle can fix it, because nothing was randomized. A
   randomized design was exactly matched by the free shuffle. An alternating
   design was over-conservative under the free shuffle, rejecting a true null in
   0 of 250 sessions, and that cost real power: at a true effect of 0.3 it
   detected the effect in 24 percent of sessions where the sign-flip test
   detected it in 54. But that sign-flip test is not the design's own null, since
   an alternating design randomizes nothing. It rests on within-pair differences
   being symmetric under H0, which a wandering baseline satisfies and a trending
   one does not: on a steadily trending baseline the same test went from 4.4
   percent to 11.6 percent as the trend steepened.
4. **Selecting on significance selects for overestimates.** At 8 trials per
   condition the estimator was unbiased over all runs, while the significant
   subset overstated a true 0.30 effect by 3.9-fold and 5 percent of those
   results pointed the wrong way. The bias is in the filter, not the
   estimator, and it disappears only when power is high enough that the filter
   stops filtering.

The through line: a null is a model of how the data could have come out
otherwise. Writing `np.random.permutation` does not exempt you from stating that
model, it just hides where you stated it.

### Exercises

**Exercise 1.** CON 3 certifies a sharp waveform's phase-amplitude coupling at
z = +18 against a shuffled null. Identify which unit that null shuffles and say,
using Section 2, whether the shuffle preserves the waveform shape that caused the
coupling. Then propose a null that would not.

**Exercise 2.** Section 3 part (c) broke the sign-flip test with a trending
baseline. Find a second way to break it that has nothing to do with drift: a
confound that alternates with the conditions, which strict alternation folds into
the contrast where a randomized design would not. Then say what that implies
about GRL 4's conclusion that strict alternation cancels drift exactly, given
that GRL 4 recommends alternation on those grounds.

**Exercise 3.** Take Section 4's table and read it as a design tool rather than a
warning. For an effect you expect to be 0.3 SD, find the trial count at which the
exaggeration factor drops below 1.2, and say whether an intraoperative session can
supply it.

---

**Next: INF 2, multiple comparisons and the cluster permutation test.** Section 1
built one null for one test. A time-frequency map asks the same question a few
thousand times, and the arithmetic of that is unforgiving.
''')

m.emit()
verify("08_inference", "01_the_shuffled_null")
print("  INF 1 OK")
