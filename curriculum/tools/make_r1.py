import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("10_stochastic", "01_estimators_are_random_variables")

m.md(r'''# Lesson STO 1: An Estimator Is a Random Variable {{VARIANT}}

**Foundations · Probability and Stochastic Processes for Neural Data**

{{INSTRUCTIONS}}

This is the first lesson of the program, and it exists because the rest of the
curriculum was written without it. SIG 4 states that a periodogram is
"roughly the true value times a $\chi^2_2$ random variable" and proceeds; INF 1
uses an effective sample size formula it does not derive; SPK 4 checks a phase
locking null against $\sqrt{\pi}/2\sqrt{N}$ without saying where that came from.
Each of those is correct and each was asserted.

The habit this course is trying to build is narrow. Every number computed from a
recording is a draw from a distribution, that distribution has a shape, and the
shape decides what the number is allowed to mean. Section 4 finds a consequence
of that in code this app ships today.

**What it assumes**

Nothing from this curriculum. It is the first lesson.

**What it underwrites**

SIG 4's $\chi^2_2$ claim and the whole case for Welch's method, the `db` and
`db_sd` columns produced by `dbsspeech.recipes.psd`, and STO 2 to STO 4.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import special, stats

rng = np.random.default_rng(101)

# 10/ln(10) converts a natural log into decibels, and turns up in every
# expectation below that involves a logarithm.
DB_PER_NAT = 10.0 / np.log(10.0)

print(f"Environment initialized for Lesson STO 1  (10/ln 10 = {DB_PER_NAT:.4f})")''')

m.md(r'''---

## 1. The simplest case, where the answer is known exactly

Take $n$ draws from a distribution with variance $\sigma^2$ and compute the
sample variance. The result is not $\sigma^2$; it is a number that changes every
time you draw again, and its average over many draws is

$$\mathbb{E}\left[\frac{1}{n}\sum_i (x_i - \bar x)^2\right] = \sigma^2\left(1 - \frac{1}{n}\right)$$

because the same data supplied the mean that was subtracted. Dividing by $n-1$
instead of $n$ corrects it exactly, which is what `ddof=1` does.

This is worth doing first because the answer is known in closed form, so the
simulation can be checked against arithmetic rather than against intuition. That
is the pattern for the whole lesson.''')

m.task(
'''def sampling_distribution(n: int, n_repeats: int, seed: int = 0) -> dict:
    """Draw n standard normals, n_repeats times, and summarise the estimators.

    Returns a dict with the mean of the sample means, and the mean of the sample
    variances computed both ways (dividing by n, and by n-1).
    """
    # TODO: draw an (n_repeats, n) array of standard normals
    # TODO: return {"mean": ..., "var_biased": ..., "var_unbiased": ...}
    #       where var_biased divides by n and var_unbiased by n-1
    raise NotImplementedError("Implement sampling_distribution")''',
'''def sampling_distribution(n: int, n_repeats: int, seed: int = 0) -> dict:
    """Draw n standard normals, n_repeats times, and summarise the estimators.

    Returns a dict with the mean of the sample means, and the mean of the sample
    variances computed both ways (dividing by n, and by n-1).
    """
    gen = np.random.default_rng(seed)
    draws = gen.standard_normal((n_repeats, n))
    return {
        "mean": float(draws.mean(axis=1).mean()),
        # ddof is the "delta degrees of freedom" subtracted from n in the
        # denominator, so ddof=0 divides by n and ddof=1 by n-1.
        "var_biased": float(draws.var(axis=1, ddof=0).mean()),
        "var_unbiased": float(draws.var(axis=1, ddof=1).mean()),
    }''')

m.code('''# --- TEST CELL FOR STEP 1 ---
N_REPEATS = 20_000

print(f"{N_REPEATS} repeats, drawing from a distribution with mean 0 and variance 1\\n")
print(f"{'n':>5} {'mean of means':>15} {'var, divide by n':>18} {'predicted 1-1/n':>17} "
      f"{'var, divide by n-1':>20}")
for n in (4, 8, 16, 64):
    result = sampling_distribution(n, N_REPEATS, seed=n)
    predicted = 1.0 - 1.0 / n
    print(f"{n:>5} {result['mean']:>15.4f} {result['var_biased']:>18.4f} "
          f"{predicted:>17.4f} {result['var_unbiased']:>20.4f}")
    # The bias is exactly 1 - 1/n, not approximately.
    assert abs(result["var_biased"] - predicted) < 0.02, \\
        f"dividing by n must underestimate the variance by exactly 1-1/n at n={n}"
    assert abs(result["var_unbiased"] - 1.0) < 0.02, "dividing by n-1 must be unbiased"
    assert abs(result["mean"]) < 0.02, "the sample mean is unbiased at every n"

small, large = sampling_distribution(4, N_REPEATS, 4), sampling_distribution(64, N_REPEATS, 64)
print(f"\\n  at n=4 the biased estimator is {(1 - small['var_biased']) * 100:.0f} percent low; "
      f"at n=64 it is {(1 - large['var_biased']) * 100:.0f} percent low")
assert small["var_biased"] < large["var_biased"], "the bias shrinks with n but never reverses"

print("\\nThe sample mean was unbiased at every n and the sample variance was not, and")
print("the size of its bias was exactly the 1-1/n the algebra predicts. Nothing here is")
print("a rule of thumb: an estimator has an expectation, and you can compute it.")
print("\\nThat is the whole content of ddof, and it is the least consequential example in")
print("this lesson. The next one has a distribution nobody would guess.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. What a periodogram actually is

SIG 4 asserts that the periodogram is the true spectrum times a $\chi^2_2$
variable. Here is where that comes from.

The DFT of white Gaussian noise at a given frequency bin is a sum of many
independent Gaussians times sines and cosines, so its real and imaginary parts
are each Gaussian, independent, and of equal variance. The periodogram is the
squared magnitude, which is the sum of two squared Gaussians. That is a
$\chi^2_2$, and a $\chi^2_2$ scaled to have mean $\mu$ is an exponential
distribution with mean $\mu$.

The consequence is severe and does not depend on the record length. An
exponential has a standard deviation equal to its mean, so the periodogram's
**relative** error is 1 at every frequency, for any amount of data. It is not a
noisy estimate of the spectrum; it is a draw from a distribution as wide as the
thing being estimated.''')

m.task(
'''def periodogram_at_bin(n_records: int, n_samples: int, bin_index: int,
                       seed: int = 0) -> np.ndarray:
    """One periodogram value per record, at a single frequency bin.

    Each record is `n_samples` of standard white noise, so the true power
    spectral density is flat and equal to 1 in this scaling.
    """
    # TODO: draw an (n_records, n_samples) array of white noise
    # TODO: take the real FFT along the sample axis
    # TODO: the periodogram is |X|^2 / n_samples; return the column at bin_index
    raise NotImplementedError("Implement periodogram_at_bin")''',
'''def periodogram_at_bin(n_records: int, n_samples: int, bin_index: int,
                       seed: int = 0) -> np.ndarray:
    """One periodogram value per record, at a single frequency bin.

    Each record is `n_samples` of standard white noise, so the true power
    spectral density is flat and equal to 1 in this scaling.
    """
    gen = np.random.default_rng(seed)
    spectrum = np.fft.rfft(gen.standard_normal((n_records, n_samples)), axis=1)
    # Dividing by n_samples puts the expected value at the true PSD of 1. Note
    # this holds only for an interior bin: DC and Nyquist are real, so they are
    # chi-squared with ONE degree of freedom, not two.
    return np.abs(spectrum[:, bin_index]) ** 2 / n_samples''')

m.code('''# --- TEST CELL FOR STEP 2 ---
N_RECORDS, N_SAMPLES, BIN = 20_000, 256, 60

p = periodogram_at_bin(N_RECORDS, N_SAMPLES, BIN, seed=2)
print(f"{N_RECORDS} independent records of {N_SAMPLES} samples, true PSD = 1.0\\n")
print(f"  mean of the periodogram: {p.mean():.4f}")
print(f"  standard deviation:      {p.std():.4f}")
print(f"  ratio of the two:        {p.std() / p.mean():.4f}")
assert abs(p.mean() - 1.0) < 0.03, "the periodogram is unbiased for the true spectrum"
assert abs(p.std() / p.mean() - 1.0) < 0.05, \\
    "and its standard deviation equals its mean, which is what an exponential does"

# Against the named distribution, not just against two of its moments.
ks = stats.kstest(p, 'expon')
print(f"\\n  Kolmogorov-Smirnov against a unit exponential: D = {ks.statistic:.4f}")
assert ks.statistic < 0.02, "the whole distribution matches, not merely the mean and spread"
# An exponential is a chi-squared with 2 degrees of freedom, halved.
assert stats.kstest(2 * p, 'chi2', args=(2,)).statistic < 0.02, \\
    "which is the chi-squared with two degrees of freedom that SIG 4 asserts"

print(f"\\n  fraction of records reading below HALF the true power: {np.mean(p < 0.5):.3f}")
print(f"  fraction reading above TWICE the true power:          {np.mean(p > 2.0):.3f}")
print(f"  theory: 1 - exp(-0.5) = {1 - np.exp(-0.5):.3f} and exp(-2) = {np.exp(-2.0):.3f}")
assert abs(np.mean(p < 0.5) - (1 - np.exp(-0.5))) < 0.02
assert abs(np.mean(p > 2.0) - np.exp(-2.0)) < 0.02

# The part that surprises people: more data does not help at all.
print(f"\\n{'record length':>15} {'mean':>8} {'sd/mean':>9}")
for length in (128, 512, 2048, 8192):
    q = periodogram_at_bin(4000, length, length // 8, seed=length)
    print(f"{length:>15} {q.mean():>8.4f} {q.std() / q.mean():>9.4f}")
    assert abs(q.std() / q.mean() - 1.0) < 0.08, \\
        f"a {length}-sample record is no more precise per bin than a 128-sample one"

print("\\nThe periodogram is an exponential random variable whose mean is the truth. It")
print("reads below half the true power in about 39 percent of records and above twice it")
print("in about 14, and a sixty-four-fold increase in record length changes none of")
print("that. Longer records buy more frequency bins, each still with 100 percent")
print("relative error, which is why SIG 4 calls the periodogram inconsistent.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Why averaging works, and exactly how well

If one periodogram is an exponential, the average of $k$ independent ones is a
gamma with shape $k$, whose standard deviation relative to its mean is
$1/\sqrt{k}$ exactly. That single line is the entire justification for Welch's
method, and it says precisely what the method buys: relative error falls as the
square root of the number of segments and in no other way.

It also says what the method costs. Cutting a record into $k$ segments makes each
segment $k$ times shorter, and SIG 3 established that frequency resolution is
$1/T$. So the exchange rate is fixed: a factor of $\sqrt{k}$ in precision for a
factor of $k$ in resolution.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def averaged_periodogram(n_records, n_segments, n_samples, bin_index, seed=0):
    """Average n_segments independent periodograms, per record."""
    gen = np.random.default_rng(seed)
    noise = gen.standard_normal((n_records, n_segments, n_samples))
    spectra = np.fft.rfft(noise, axis=2)
    return (np.abs(spectra[:, :, bin_index]) ** 2 / n_samples).mean(axis=1)

print(f"{'segments k':>12} {'mean':>8} {'sd/mean':>10} {'1/sqrt(k)':>11} {'ratio':>8}")
for k in (1, 2, 4, 8, 16, 64):
    a = averaged_periodogram(6000, k, N_SAMPLES, BIN, seed=300 + k)
    relative = a.std() / a.mean()
    print(f"{k:>12} {a.mean():>8.4f} {relative:>10.4f} {1 / np.sqrt(k):>11.4f} "
          f"{relative * np.sqrt(k):>8.4f}")
    assert abs(a.mean() - 1.0) < 0.05, "averaging does not introduce bias"
    assert abs(relative - 1 / np.sqrt(k)) < 0.03, \\
        f"relative error must be exactly 1/sqrt(k) at k={k}"

# The distribution is a gamma, which matters in Section 4 because a gamma
# transformed by a logarithm is not symmetric.
a16 = averaged_periodogram(20_000, 16, N_SAMPLES, BIN, seed=16)
print(f"\\n  KS of the 16-segment average against gamma(shape=16, scale=1/16): "
      f"{stats.kstest(a16, 'gamma', args=(16, 0, 1 / 16)).statistic:.4f}")
assert stats.kstest(a16, 'gamma', args=(16, 0, 1 / 16)).statistic < 0.02
print(f"  its skewness is {stats.skew(a16):+.3f}, so it is still not symmetric at k=16")
assert stats.skew(a16) > 0.2, "a gamma stays right-skewed, which Section 4 needs"

print("\\nRelative error tracked 1/sqrt(k) to about one percent at every k, so sixteen")
print("segments buy a factor of four and sixty-four a factor of eight. Against that,")
print("SIG 3's resolution of 1/T means sixteen segments cost a factor of sixteen in")
print("frequency resolution. That exchange rate is fixed and unfavourable, which is why")
print("multitaper exists and why SIG 4 found it wins by 9 percent, not by a landslide.")
print("\\nThe averaged periodogram is a gamma, and a gamma is skewed. That is not a")
print("footnote: Section 4 is about what happens when a skewed variable meets a")
print("logarithm.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What this app does with those numbers

`dbsspeech.recipes.psd` computes a spectrum per segment, converts each one to
decibels, and then averages the decibels:

```python
db = _to_db(power)              # per segment
...
"db": db_segments.mean(axis=0)  # averaged in dB
```

Averaging is linear and the decibel conversion is not, so there are two orderings
and they do not agree. Sections 2 and 3 make the difference computable, and the
two answers have completely different shapes.

**Average the power, then convert.** The average of $k$ exponentials is a gamma
of shape $k$, so

$$\mathbb{E}[10\log_{10}\bar P] = 10\log_{10} P + \frac{10}{\ln 10}\left(\psi(k) - \ln k\right)$$

with $\psi$ the digamma function. That is negative and **shrinks toward zero as
$k$ grows**.

**Convert each segment, then average the decibels.** Averaging preserves an
expectation, so the answer is whatever one segment gives, which is
$-\gamma \cdot 10/\ln 10$ where $\gamma$ is the Euler-Mascheroni constant. That is
a **constant, the same at every $k$**.

Which of those describes this app decides everything about whether it matters, so
Section 4 measures both rather than assuming.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
def average_then_convert(k, n_records=20_000, seed=0):
    """Average the periodograms, then take the logarithm."""
    p = np.random.default_rng(seed).standard_exponential((n_records, k))
    return float(np.mean(10 * np.log10(p.mean(axis=1))))

def convert_then_average(k, n_records=20_000, seed=0):
    """Take the logarithm of each segment, then average. This is what psd.py does."""
    p = np.random.default_rng(seed).standard_exponential((n_records, k))
    return float(np.mean(np.mean(10 * np.log10(p), axis=1)))

def digamma_bias(k):
    """Closed form for averaging the power first."""
    return DB_PER_NAT * (special.digamma(k) - np.log(k))

CONSTANT_BIAS = -DB_PER_NAT * np.euler_gamma      # for converting first

print("true power is 1.0 in every row, so the true value is 0.000 dB\\n")
print(f"{'segments k':>11} {'average, then dB':>18} {'closed form':>13} "
      f"{'dB, then average':>18} {'closed form':>13}")
for k in (1, 2, 4, 16, 64):
    first = average_then_convert(k, seed=900 + k)
    second = convert_then_average(k, seed=900 + k)
    print(f"{k:>11} {first:>18.3f} {digamma_bias(k):>13.3f} "
          f"{second:>18.3f} {CONSTANT_BIAS:>13.3f}")
    assert abs(first - digamma_bias(k)) < 0.06, f"the digamma form is the power-first one, at k={k}"
    assert abs(second - CONSTANT_BIAS) < 0.06, \
        f"converting first gives the same constant at every k, including k={k}"

print(f"\\n  averaging the power first: bias shrinks from {digamma_bias(1):.2f} dB "
      f"to {digamma_bias(64):.2f} dB")
print(f"  converting first:          bias is {CONSTANT_BIAS:.2f} dB at every k, which is "
      f"-gamma * 10/ln(10)")
assert abs(digamma_bias(64)) < 0.05, "one of them vanishes as segments are added"
assert abs(CONSTANT_BIAS) > 2.0, "and the other does not move at all"

# (b) So which does psd.py have? The code converts per segment and then averages,
# which is the second column: a constant offset, not a shrinking one.
#
# With one qualification that matters. The constant is -gamma*10/ln(10) only when
# each segment is ONE periodogram, which is true of the Welch path. The
# multitaper path calls psd_array_multitaper, which averages over DPSS tapers
# before _to_db ever sees the value, so its per-segment estimate already has more
# than two degrees of freedom and its offset is much smaller. Measured directly
# on the two paths: -2.506 dB for Welch, -0.313 dB for multitaper.
WELCH_OFFSET_DB, MULTITAPER_OFFSET_DB = -2.506, -0.313
print("\\n  psd.py converts per segment and averages the dB, so its bias is a constant")
print(f"  rather than a shrinking one. Its size depends on the method: {WELCH_OFFSET_DB:.2f} dB on")
print(f"  the Welch path, where a segment is one periodogram, and {MULTITAPER_OFFSET_DB:.2f} dB on")
print("  multitaper, which averages over tapers before converting.")
assert abs(WELCH_OFFSET_DB - CONSTANT_BIAS) < 0.01, \
    "the Welch path is the case this section derived"
assert abs(MULTITAPER_OFFSET_DB) < abs(WELCH_OFFSET_DB) / 4, \
    "and averaging tapers first shrinks the offset, for the same reason averaging segments would"

# (c) A constant cancels in a difference. Measure the residue in a contrast
# between conditions with very different segment counts, which is the case that
# would matter if the bias depended on k.
print(f"\\n{'task segments':>14} {'rest segments':>14} {'contrast residue':>18}")
for k_task, k_rest in ((40, 40), (40, 8), (40, 4)):
    residue = convert_then_average(k_task, seed=11) - convert_then_average(k_rest, seed=12)
    print(f"{k_task:>14} {k_rest:>14} {residue:>18.4f} dB")
    assert abs(residue) < 0.03, \
        "a constant offset cancels in a contrast at ANY pair of segment counts"

# For comparison: had the app averaged power first, the SAME contrast would carry
# a real residue, because that bias does depend on k.
would_be = digamma_bias(4) - digamma_bias(40)
print(f"\\n  had it averaged power first, 40 against 4 segments would leave "
      f"{would_be:.3f} dB")
assert abs(would_be) > 0.4, "which is the artifact the app's ordering happens to avoid"

# (d) The one place the constant survives. normalize.py offers centre "none",
# where z is the dB value divided by a scale rather than a difference of two.
print("\\n  where the offset does NOT cancel: configs/statistics.yaml centre 'none',")
print("  where z = value / scale rather than (value - centre) / scale\\n")
print(f"{'scale, dB':>11} {'z of a true 0 dB':>18}")
for scale in (1.0, 2.0, 5.0):
    print(f"{scale:>11.1f} {CONSTANT_BIAS / scale:>18.2f}")
assert abs(CONSTANT_BIAS / 2.0) > 1.0, \
    "at a plausible scale the offset alone is more than one z unit"

print("\\nSo the answer is the opposite of the one the setup suggests, and it is worth")
print("saying plainly. Converting before averaging is the cruder of the two orderings")
print("and it is the safer one here, because it makes the error a constant, and a")
print("constant subtracts out of every contrast at any segment counts. Averaging the")
print("power first is asymptotically unbiased and would have introduced an artifact of")
print(f"{would_be:.2f} dB between a 40-segment condition and a 4-segment one.")
print("\\nEvery absolute dB value in this app is therefore offset low, by about 2.5 dB on")
print("the Welch path and 0.3 dB on multitaper, and every difference between two of them")
print("is right. Since the app reports contrasts, almost nothing is affected.")
print("\\nThe method dependence is worth its own line, because it is what makes correcting")
print("this harder than it looks: a subtraction would have to know which method produced")
print("the column, and on multitaper it would also depend on the taper count, which")
print("varies with the window.")
print("\\nThe exception is narrow and real. `dbsspeech.stats.normalize` offers a centre of")
print("'none', which INF 3 measured as one of its twenty options, and there z is the")
print("value divided by a scale rather than a difference of two values. The 2.5 dB")
print("offset passes straight into that z. It is the only one of the four centres for")
print("which the cancellation argument fails, and INF 3's own caveat for that option")
print("says it is a signal-to-noise ratio rather than a contrast, which is exactly the")
print("distinction that matters here.")
print("\\nNothing is changed. The measurement is in docs/findings.md.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **An estimator has an expectation, and it can be computed rather than
   guessed.** The sample variance of $n$ draws is low by exactly $1-1/n$, which
   is 25 percent at $n=4$, and dividing by $n-1$ corrects it exactly.
2. **A periodogram is an exponential random variable whose mean is the true
   spectrum.** Verified against the distribution itself, not just its first two
   moments: it reads below half the true power in 39 percent of records and above
   twice it in 14, and a sixty-four-fold increase in record length leaves the
   relative error at 1. This is the $\chi^2_2$ claim SIG 4 makes, derived.
3. **Averaging $k$ segments gives a gamma with relative error $1/\sqrt{k}$,**
   which the measurement tracked to about one percent at every $k$ tested. That is the
   whole justification for Welch, and against SIG 3's resolution of $1/T$ it
   fixes the exchange rate: $\sqrt{k}$ in precision for $k$ in resolution.
4. **Taking the logarithm before averaging and after averaging are different
   operations, and they fail differently.** Averaging the power and converting
   afterwards is low by $(10/\ln 10)(\psi(k) - \ln k)$, which shrinks from 2.51 dB
   at one segment to 0.03 at sixty-four. Converting each segment and then
   averaging the decibels is low by $\gamma \cdot 10/\ln 10 = 2.51$ dB at every
   $k$, because averaging preserves an expectation. Both were measured against
   their closed forms at five segment counts.
5. **`recipes/psd.py` does the second, and that turns out to be the safer
   choice.** A constant offset cancels in a difference, so the contrast residue
   between a 40-segment condition and a 4-segment one measured under 0.01 dB.
   Had the recipe averaged power first it would have been asymptotically
   unbiased and would have introduced a 0.51 dB artifact into exactly that
   comparison. Every absolute dB value in the app is offset low, by about 2.5 dB
   on the Welch path and 0.3 dB on multitaper, which averages over tapers before
   converting, and every difference between two of them is right. The one place
   the offset survives is `normalize.py`'s centre of `none`, where z is a value
   divided by a scale rather than a difference of two. That is now stated in
   `configs/statistics.yaml`'s caveat for the option, which the interface shows
   beside it.

The pattern to carry into STO 2: the shape of a distribution, not just its mean,
decides whether an operation is safe, and "safe" depends on what is done next.
The cruder ordering was the better one here only because this app reports
differences. For a quantity reported on its own it is the worse one, by 2.5 dB.

### Exercises

**Exercise 1.** Section 2 notes that DC and Nyquist bins are real, so they are
$\chi^2_1$ rather than $\chi^2_2$. Measure the relative error at those two bins
and say what it implies for any band that includes them.

**Exercise 2.** Derive $\mathbb{E}[\ln \bar P]$ for a gamma with shape $k$ from
the definition, and confirm the digamma appears. Then find the $k$ at which the
bias drops below 0.1 dB and say whether a typical run in this app reaches it.

**Exercise 3.** Section 4 found the app's ordering safe for contrasts and not
for the `none` centre. Decide whether `dbsspeech.stats.normalize` should subtract
the 2.51 dB constant when that centre is selected, and say what would break if it
did, given that the same dB column feeds every other centre.

---

**Next: STO 2, autocorrelation and the effective sample size.** Every result in
this lesson assumed independent draws. INF 1 already measured what happens when
that assumption fails, using a formula it did not derive. This is where it comes
from.
''')

m.emit()
verify("10_stochastic", "01_estimators_are_random_variables")
print("  STO 1 OK")
