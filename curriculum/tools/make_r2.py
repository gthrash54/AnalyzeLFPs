import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("10_stochastic", "02_autocorrelation_and_effective_sample_size")

m.md(r'''# Lesson STO 2: Autocorrelation and the Effective Sample Size {{VARIANT}}

**Foundations · Probability and Stochastic Processes for Neural Data**

{{INSTRUCTIONS}}

STO 1 assumed every draw was independent. Nothing recorded from a brain is.

INF 1 already measured what that costs, and used a formula it did not derive:
that $n$ samples of an AR(1) process with lag-one correlation $\rho$ are worth
about $n(1-\rho)/(1+\rho)$ independent ones. This lesson derives it, checks it,
and then finds the case where it is badly wrong, which is the case neural data
is actually in.

**What it assumes**

| From | What is used |
|---|---|
| STO 1 | That an estimator has a distribution, and that its variance can be computed rather than guessed. |

**What it underwrites**

INF 1's effective sample size and its blocked-shuffle argument, GRL 4's result
that drift does not shrink with more data, and DEC 2's fold rule.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import lfilter

rng = np.random.default_rng(211)

BURN_IN = 5000     # lfilter starts from rest; discard the ramp, as DEC 2 learned


def ar1(n: int, rho: float, gen, n_records: int = 1) -> np.ndarray:
    """AR(1) noise of unit variance. rho=0 gives white noise."""
    white = gen.standard_normal((n_records, n + BURN_IN))
    if rho == 0.0:
        return white[:, BURN_IN:]
    return lfilter([np.sqrt(1 - rho ** 2)], [1.0, -rho], white, axis=1)[:, BURN_IN:]


def one_over_f(n: int, gen) -> np.ndarray:
    """A single long 1/f series, shaped in the frequency domain.

    Power falls as 1/f, which CON 4 established is the shape of a real LFP
    spectrum before any oscillation is added.
    """
    spectrum = np.fft.rfft(gen.standard_normal(n))
    freqs = np.arange(spectrum.size, dtype=float)
    spectrum[0] = 0.0                        # no DC, so the series has mean zero
    spectrum[1:] /= np.sqrt(freqs[1:])       # amplitude 1/sqrt(f), power 1/f
    return np.fft.irfft(spectrum)


print("Environment initialized for Lesson STO 2")''')

m.md(r'''---

## 1. The autocorrelation function

The autocorrelation at lag $k$ is the correlation between the series and itself
shifted by $k$. For an AR(1) process, where each sample is $\rho$ times the last
plus fresh noise, it is exactly $\rho^k$: correlation decays geometrically, and
the process forgets at a rate set by $\rho$ alone.

The useful summary is how long it takes to forget. At $\rho = 0.9$ the
correlation is still 0.35 ten samples later; at $\rho = 0.5$ it is 0.001.''')

m.task(
'''def autocorrelation(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Correlation of x with itself at lags 1..max_lag."""
    # TODO: for each lag, correlate x[:-lag] against x[lag:]
    # TODO: return an array of length max_lag
    raise NotImplementedError("Implement autocorrelation")''',
'''def autocorrelation(x: np.ndarray, max_lag: int) -> np.ndarray:
    """Correlation of x with itself at lags 1..max_lag."""
    return np.array([float(np.corrcoef(x[:-lag], x[lag:])[0, 1])
                     for lag in range(1, max_lag + 1)])''')

m.code('''# --- TEST CELL FOR STEP 1 ---
LONG = 200_000
series = ar1(LONG, 0.9, np.random.default_rng(1))[0]
measured = autocorrelation(series, 10)

print(f"AR(1) with rho = 0.9, {LONG} samples\\n")
print(f"{'lag':>5} {'measured':>10} {'rho^lag':>9}")
for lag in (1, 2, 3, 5, 10):
    print(f"{lag:>5} {measured[lag - 1]:>10.4f} {0.9 ** lag:>9.4f}")
    assert abs(measured[lag - 1] - 0.9 ** lag) < 0.01, "the ACF of an AR(1) is exactly rho^lag"

white = ar1(LONG, 0.0, np.random.default_rng(2))[0]
assert np.max(np.abs(autocorrelation(white, 10))) < 0.02, "white noise forgets immediately"

# How many samples until the correlation drops below 0.1, which is the practical
# question: at what separation are two samples nearly independent?
print(f"\\n{'rho':>6} {'lag where ACF < 0.1':>21}")
for rho in (0.0, 0.5, 0.9, 0.95, 0.99):
    lag = 1 if rho == 0 else int(np.ceil(np.log(0.1) / np.log(rho)))
    print(f"{rho:>6.2f} {lag:>21}")
assert int(np.ceil(np.log(0.1) / np.log(0.99))) > 200, \\
    "at rho=0.99 two samples are still correlated hundreds of steps apart"

print("\\nThe correlation decays geometrically, so a single number fixes the whole")
print("function. That is what makes the next section possible in closed form, and it is")
print("also the assumption Section 3 breaks.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. What correlation does to the mean

The variance of a sample mean of correlated data is not $\sigma^2/n$. Writing the
mean as a sum and expanding the square, every pair contributes its covariance:

$$\mathrm{Var}(\bar x) = \frac{\sigma^2}{n}\left[1 + 2\sum_{k=1}^{n-1}\left(1 - \frac{k}{n}\right)\rho^k\right]$$

The bracket is the **variance inflation factor**. For large $n$ the geometric sum
converges and the factor tends to $(1+\rho)/(1-\rho)$, which gives the effective
sample size INF 1 used:

$$n_{\text{eff}} = n\,\frac{1-\rho}{1+\rho}$$

Both forms are tested below, because the difference between them turns out to
explain a small discrepancy INF 1 left unexplained.''')

m.task(
'''def variance_inflation(n: int, rho: float) -> float:
    """The exact bracket above: how much correlation inflates Var(mean).

    This is the finite-n form, with the (1 - k/n) weights, not the limit.
    """
    # TODO: sum over lags 1..n-1 of (1 - k/n) * rho**k
    # TODO: return 1 + 2 * that sum
    raise NotImplementedError("Implement variance_inflation")


def effective_n(n: int, rho: float) -> float:
    """How many independent samples n correlated ones are worth."""
    # TODO: n divided by the inflation factor
    raise NotImplementedError("Implement effective_n")''',
'''def variance_inflation(n: int, rho: float) -> float:
    """The exact bracket above: how much correlation inflates Var(mean).

    This is the finite-n form, with the (1 - k/n) weights, not the limit.
    """
    lags = np.arange(1, n)
    # The (1 - k/n) weight counts how many pairs are k apart in a record of n,
    # and it is what makes this exact rather than asymptotic.
    return float(1 + 2 * np.sum((1 - lags / n) * rho ** lags))


def effective_n(n: int, rho: float) -> float:
    """How many independent samples n correlated ones are worth."""
    return n / variance_inflation(n, rho)''')

m.code('''# --- TEST CELL FOR STEP 2 ---
N, N_RECORDS = 200, 20_000

print(f"variance of the sample mean over {N_RECORDS} records of {N} samples\\n")
print(f"{'rho':>6} {'measured n*Var':>16} {'exact formula':>15} {'asymptotic':>12} "
      f"{'n_eff exact':>13}")
for rho in (0.0, 0.5, 0.8, 0.9, 0.95):
    means = ar1(N, rho, np.random.default_rng(400 + int(rho * 100)), N_RECORDS).mean(axis=1)
    measured_inflation = N * float(means.var())
    exact = variance_inflation(N, rho)
    asymptotic = (1 + rho) / (1 - rho)
    print(f"{rho:>6.2f} {measured_inflation:>16.3f} {exact:>15.3f} {asymptotic:>12.3f} "
          f"{effective_n(N, rho):>13.1f}")
    assert abs(measured_inflation - exact) < 0.1 * exact, \\
        f"the exact formula must predict the measured inflation at rho={rho}"

# The two forms differ, and the difference grows with rho: the geometric sum has
# not converged when the correlation length is a real fraction of the record.
print(f"\\n{'n':>7} {'rho':>6} {'exact':>9} {'asymptotic':>12} {'error of asymptotic':>21}")
for n, rho in ((100, 0.9), (1000, 0.9), (100, 0.95)):
    exact, asymptotic = variance_inflation(n, rho), (1 + rho) / (1 - rho)
    print(f"{n:>7} {rho:>6.2f} {exact:>9.3f} {asymptotic:>12.3f} "
          f"{(asymptotic / exact - 1):>20.1%}")
assert variance_inflation(1000, 0.9) > variance_inflation(100, 0.9), \\
    "the asymptotic form is approached from below as the record lengthens"

# INF 1 measured a null 4.2 times too narrow and predicted the ratio from the
# asymptotic effective sample size, printing sqrt(100/5) = 4.4. It called the
# factor predictable and moved on, which it was. The exact form does better.
inf1_n, inf1_rho = 100, 0.9
asymptotic_ratio = np.sqrt(inf1_n / (inf1_n * (1 - inf1_rho) / (1 + inf1_rho)))
exact_ratio = np.sqrt(variance_inflation(inf1_n, inf1_rho))
print(f"\\n  INF 1, {inf1_n} samples at rho {inf1_rho}, measured a width ratio of 4.2")
print(f"    from the asymptotic n_eff: {asymptotic_ratio:.2f}  "
      f"(off by {abs(asymptotic_ratio - 4.2) / 4.2:.1%})")
print(f"    from the exact n_eff:      {exact_ratio:.2f}  "
      f"(off by {abs(exact_ratio - 4.2) / 4.2:.1%})")
assert abs(exact_ratio - 4.2) < abs(asymptotic_ratio - 4.2), \\
    "the exact form lands closer to what INF 1 actually measured"

print("\\nThe exact formula predicted the measured inflation at every rho, and the")
print("asymptotic one overstates it whenever the correlation length is a real fraction")
print("of the record. At 100 samples and rho 0.9 that is a 10 percent error in the")
print("variance, which is 5 percent once the square root turns it into a width ratio.")
print("Both forms land within a few percent of what INF 1 measured, and the exact one")
print("lands closer. That is a refinement rather than a repair: INF 1's number was")
print("right, and this says how much of the remaining wobble was the formula rather")
print("than the simulation.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Where the formula stops working

Everything above rests on the correlation decaying geometrically, so that the sum
$\sum_k \rho^k$ converges to something finite. A process with that property has a
**correlation time**, and beyond it samples are effectively independent.

Neural field potentials do not have one. CON 4 established that an LFP spectrum
is dominated by an aperiodic component falling as $1/f$, and a $1/f$ process has
correlation at every timescale, because there is no frequency below which it runs
out of power. The sum does not converge, and the effective sample size stops
being a fixed fraction of $n$.

The measurement below asks the practical version of that: take one long
recording, average it in blocks of increasing length, and see how fast the
variance of the block means actually falls.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
M = 1 << 21     # about two million samples of each process
gen = np.random.default_rng(11)
processes = {
    "AR(1), rho = 0.9": ar1(M, 0.9, gen)[0],
    "1/f noise": one_over_f(M, gen),
}

def n_eff_from_blocks(x, block):
    """Effective sample size of a block mean, measured rather than assumed."""
    n_blocks = len(x) // block
    block_means = x[:n_blocks * block].reshape(n_blocks, block).mean(axis=1)
    return float(x.var() / block_means.var())

BLOCKS = (10, 40, 160, 640, 2560, 10240)
print(f"{'block length':>13} " + "".join(f"{name:>30}" for name in processes))
print(f"{'':>13} " + "".join(f"{'n_eff':>15}{'n_eff / n':>15}" for _ in processes))
table = {name: {} for name in processes}
for block in BLOCKS:
    cells = ""
    for name, x in processes.items():
        table[name][block] = n_eff_from_blocks(x, block)
        cells += f"{table[name][block]:>15.1f}{table[name][block] / block:>15.4f}"
    print(f"{block:>13} " + cells)

ar_name, f_name = "AR(1), rho = 0.9", "1/f noise"

# (a) For AR(1) the ratio settles, and it settles on the Section 2 prediction.
settled = [table[ar_name][b] / b for b in (640, 2560, 10240)]
predicted_ratio = (1 - 0.9) / (1 + 0.9)
print(f"\\n  AR(1): n_eff/n settles at {np.mean(settled):.4f}, "
      f"against (1-rho)/(1+rho) = {predicted_ratio:.4f}")
assert max(settled) - min(settled) < 0.005, "the AR(1) ratio stops changing"
assert abs(np.mean(settled) - predicted_ratio) < 0.006, "and it stops at the predicted value"

# (b) For 1/f it never settles, and n_eff grows like the logarithm of n.
ratios = [table[f_name][b] / b for b in BLOCKS]
assert ratios[-1] < 0.1 * ratios[0], "the 1/f ratio keeps falling, so there is no fixed n_eff/n"
slope, intercept = np.polyfit(np.log(BLOCKS), [table[f_name][b] for b in BLOCKS], 1)
print(f"  1/f:   n_eff is fitted by {slope:.3f} * ln(n) + {intercept:.3f}")
predicted = slope * np.log(np.array(BLOCKS)) + intercept
assert np.max(np.abs(predicted - [table[f_name][b] for b in BLOCKS])) < 0.25, \\
    "n_eff grows like the logarithm of the record length, not like a fraction of it"

# (c) What that buys you, in the only currency that matters.
first, last = BLOCKS[0], BLOCKS[-1]
for name in processes:
    gain = np.sqrt(table[name][last] / table[name][first])
    print(f"\\n  {name}: going from {first} to {last} samples, a factor of {last // first},")
    print(f"    cut the error bar by {gain:.1f}x  (independent samples would give "
          f"{np.sqrt(last / first):.0f}x)")
assert np.sqrt(table[f_name][last] / table[f_name][first]) < 2.0, \\
    "a thousandfold more 1/f data does not even halve the error bar"

print("\\nFor the AR(1) process the effective sample size is a fixed fraction of the")
print("record, and that fraction is the one Section 2 derived. Averaging works exactly")
print("as advertised, just at five percent efficiency.")
print("\\nFor 1/f noise it is not a fraction of anything. The effective sample size grows")
print("like the logarithm of the record length, so a thousandfold increase in data cut")
print("the error bar by less than a factor of two, where independent samples would have")
print("cut it by thirty-two. There is no correlation time to wait out, because a 1/f")
print("process has structure at every timescale including timescales longer than the")
print("recording.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. The result this curriculum has been circling

GRL 4 measured that sixteen times the data quartered an error bar and left a
baseline excursion exactly where it was, and treated drift and variance as two
separate things that behave differently. Section 3 says they are one thing seen
at two timescales.

A $1/f$ process has power at every frequency, including frequencies whose period
exceeds the recording. Those components cannot be distinguished from a trend, and
averaging cannot reduce them, because averaging only reduces what fluctuates
within the window. What GRL 4 called drift is the low-frequency end of exactly
the process whose effective sample size Section 3 measured.

That reframing makes a prediction, which is testable: an estimate's error should
stop improving at a rate set by how much low-frequency power there is, and the
sweep below varies that directly.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
gen4 = np.random.default_rng(77)

def shaped_noise(n, exponent, gen):
    """Noise with power falling as 1/f^exponent. 0 is white, 2 is a random walk."""
    spectrum = np.fft.rfft(gen.standard_normal(n))
    freqs = np.arange(spectrum.size, dtype=float)
    spectrum[0] = 0.0
    spectrum[1:] /= freqs[1:] ** (exponent / 2)
    out = np.fft.irfft(spectrum)
    return out / out.std()

print("how the error bar improves with more data, by how steep the spectrum is\\n")
print(f"{'exponent':>9} {'what it is':>22} {'n_eff at 40':>13} {'n_eff at 10240':>16} "
      f"{'error bar gain':>16}")
NAMES = {0.0: "white noise", 0.5: "shallow aperiodic",
         1.0: "1/f, a real LFP", 2.0: "a random walk"}
gains = {}
for exponent in (0.0, 0.5, 1.0, 2.0):
    x = shaped_noise(M, exponent, gen4)
    small = n_eff_from_blocks(x, 40)
    large = n_eff_from_blocks(x, 10240)
    gains[exponent] = np.sqrt(large / small)
    print(f"{exponent:>9.1f} {NAMES[exponent]:>22} {small:>13.1f} {large:>16.1f} "
          f"{gains[exponent]:>15.1f}x")

ideal = np.sqrt(10240 / 40)
print(f"\\n  independent samples over the same 256-fold increase would give {ideal:.0f}x")
assert gains[0.0] > 0.8 * ideal, "white noise gets the full square-root benefit"
assert gains[1.0] < 0.25 * ideal, "a real LFP spectrum gets a small fraction of it"
assert gains[2.0] < 1.5, "and a random walk gets essentially nothing"
assert gains[0.0] > gains[0.5] > gains[1.0] > gains[2.0], \\
    "the benefit of more data falls monotonically as the spectrum steepens"

print("\\n  the steeper the spectrum, the less a longer recording is worth, and the")
print("  ordering is strict across the whole sweep")

print("\\nSo GRL 4's two behaviours are one behaviour. White noise averages down at the")
print("full 1/sqrt(n); a random walk does not average down at all, which is precisely")
print("what GRL 4 observed when it called drift immune to averaging. A real LFP sits")
print("between them and closer to the bad end.")
print("\\nThree practical consequences, none of which is 'record longer'.")
print("\\nFirst, an error bar computed as sd/sqrt(n) on a neural time series is wrong by")
print("the square root of the inflation factor, which Section 2 showed reaches 17 at")
print("rho 0.9 and Section 3 showed has no fixed value at all for 1/f. That is a factor")
print("of four or more, not a correction.")
print("\\nSecond, this is why INF 1's shuffle has to respect blocks and DEC 2's folds have")
print("to be contiguous. Both rules are the same statement: the number of independent")
print("things in the recording is far smaller than the number of samples, and any")
print("procedure that treats samples as exchangeable is counting data it does not have.")
print("\\nThird, the design fix GRL 4 recommended is the only one that works. Interleaving")
print("conditions moves the comparison to a timescale where the noise is white, and")
print("nothing about how long you record does that.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **An AR(1) process has autocorrelation exactly $\rho^k$,** so one number fixes
   the whole function, and the lag at which correlation falls below 0.1 is 22
   samples at $\rho = 0.9$ and over 200 at $\rho = 0.99$.
2. **Correlation inflates the variance of a sample mean by a computable factor,**
   $1 + 2\sum_k (1-k/n)\rho^k$, which predicted the measured inflation at every
   $\rho$ tested. Its limit gives INF 1's $n_{\text{eff}} = n(1-\rho)/(1+\rho)$.
3. **The finite-$n$ form is the better predictor of what INF 1 measured.** INF 1
   measured a null 4.2 times too narrow. The asymptotic effective sample size
   predicts 4.36, which is 3.8 percent high; the exact finite-$n$ form predicts
   4.15, which is 1.3 percent low. The two differ by 10 percent in the variance
   and by 5 percent in the width ratio, because of the square root.
4. **For a $1/f$ process there is no effective sample size worth the name.**
   Measured by block averaging on one long recording, $n_{\text{eff}}$ grew like
   $0.23\ln n$ rather than as a fixed fraction of $n$. A thousandfold increase in
   data cut the error bar by less than a factor of two, where independent samples
   would have cut it by thirty-two.
5. **Drift and variance are the same phenomenon at different timescales.** The
   benefit of a longer recording fell monotonically as the spectrum steepened,
   from the full square root for white noise to essentially nothing for a random
   walk, with a real LFP much closer to the random walk. What GRL 4 called drift
   is the low-frequency end of the process whose averaging efficiency Section 3
   measured.

The consequence for this app is that `sd/sqrt(n)` is not an error bar for
anything recorded from a brain, and that the fixes are design fixes. INF 1's
blocked shuffle, DEC 2's contiguous folds and GRL 4's interleaving are three
statements of one fact.

### Exercises

**Exercise 1.** Section 2's exact formula needs $\rho$, which is estimated from
the same data. Measure how badly $\hat\rho$ is biased at $n = 40$, and say
whether the bias makes the effective sample size look larger or smaller than it
is, and therefore which way the error is dangerous.

**Exercise 2.** The block-averaging method in Section 3 estimates
$n_{\text{eff}}$ without assuming any model. Apply it to the per-epoch band power
in GRL 4's drift simulation and say how many independent epochs that lesson's 120
actually contained.

**Exercise 3.** Section 4 claims that interleaving moves the comparison to a
timescale where the noise is white. State that as a claim about the spectrum of
the contrast rather than of the signal, and verify it for the alternating design
in INF 1 Section 3.

---

**Next: STO 3, random walks and the processes with no stationary distribution.**
Section 4's steepest case turned out to be the one this curriculum keeps meeting,
and it is the case where most of the intuitions above stop applying entirely.
''')

m.emit()
verify("10_stochastic", "02_autocorrelation_and_effective_sample_size")
print("  STO 2 OK")
