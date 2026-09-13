import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("10_stochastic", "04_point_processes_and_phase_locking")

m.md(r'''# Lesson STO 4: Events Rather Than Samples {{VARIANT}}

**Foundations · Probability and Stochastic Processes for Neural Data**

{{INSTRUCTIONS}}

Everything in this course so far has been a time series: a value at every sample.
A spike train is not that. It is a list of times at which something happened, and
the estimators built for time series do not transfer to it unchanged.

The lesson ends by deriving a number SPK 4 checks against and does not explain:
that phase locking under the null is $\sqrt{\pi}/2\sqrt{N}$. That formula turns
out to say something more damaging than SPK 4 draws from it, which Section 4
measures.

**What it assumes**

| From | What is used |
|---|---|
| STO 1 | That an estimator has a distribution, and how to check one against a named distribution. |

**What it underwrites**

SPK 4's phase-locking null and its warning that raw PLV compares spike counts,
and SPK 2's threshold arithmetic, which assumes a firing statistic.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

rng = np.random.default_rng(401)

RATE_HZ = 20.0     # a plausible tonic rate for an STN unit
WINDOW_S = 5.0

print("Environment initialized for Lesson STO 4")''')

m.md(r'''---

## 1. The Poisson process, and the two ways to describe it

The simplest model of a spike train says events happen independently at a
constant rate. That single assumption fixes everything else, and it can be
described from either end:

- **Counts.** The number of spikes in a window of length $T$ is Poisson with mean
  $\lambda T$. A Poisson distribution has variance equal to its mean, so the
  **Fano factor**, variance over mean, is 1.
- **Intervals.** The time between consecutive spikes is exponential with mean
  $1/\lambda$. An exponential has standard deviation equal to its mean, so the
  **coefficient of variation** of the intervals is 1.

Both are the same statement, and both give 1, which is why either number is used
as a reference point. STO 1 met the same distribution from the other direction:
the periodogram was exponential, and its standard deviation equalled its mean for
the same reason.''')

m.task(
'''def poisson_spike_times(rate_hz: float, duration_s: float, gen) -> np.ndarray:
    """Spike times of a homogeneous Poisson process, by accumulating intervals.

    Draw exponential intervals until they run past `duration_s`, then keep the
    times that fall inside it.
    """
    # TODO: draw generously many exponential intervals with mean 1/rate_hz
    # TODO: cumulative-sum them into spike times
    # TODO: return only the times below duration_s
    raise NotImplementedError("Implement poisson_spike_times")


def fano_factor(counts: np.ndarray) -> float:
    """Variance over mean of a set of spike counts. Exactly 1 for Poisson."""
    # TODO: one line
    raise NotImplementedError("Implement fano_factor")''',
'''def poisson_spike_times(rate_hz: float, duration_s: float, gen) -> np.ndarray:
    """Spike times of a homogeneous Poisson process, by accumulating intervals.

    Draw exponential intervals until they run past `duration_s`, then keep the
    times that fall inside it.
    """
    # Draw with a wide margin so the process is very unlikely to run short. The
    # count is Poisson, so overshooting by five standard deviations is cheap.
    expected = rate_hz * duration_s
    n_draw = int(expected + 10 * np.sqrt(expected) + 100)
    times = np.cumsum(gen.exponential(1.0 / rate_hz, n_draw))
    return times[times < duration_s]


def fano_factor(counts: np.ndarray) -> float:
    """Variance over mean of a set of spike counts. Exactly 1 for Poisson."""
    return float(np.var(counts) / np.mean(counts))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
N_TRIALS = 20_000
gen = np.random.default_rng(1)

counts = np.array([len(poisson_spike_times(RATE_HZ, WINDOW_S, gen)) for _ in range(4000)])
print(f"{RATE_HZ:.0f} Hz over {WINDOW_S:.0f} s, 4000 windows\\n")
print(f"  mean count {counts.mean():.2f}, expected {RATE_HZ * WINDOW_S:.0f}")
print(f"  variance   {counts.var():.2f}")
print(f"  Fano factor {fano_factor(counts):.4f}")
assert abs(counts.mean() - RATE_HZ * WINDOW_S) < 2.0, "the rate is what it says"
assert abs(fano_factor(counts) - 1.0) < 0.08, "a Poisson count has variance equal to its mean"

# The intervals, which say the same thing a different way.
intervals = gen.exponential(1.0 / RATE_HZ, 200_000)
cv = float(intervals.std() / intervals.mean())
print(f"\\n  mean interval {intervals.mean() * 1000:.2f} ms, expected "
      f"{1000 / RATE_HZ:.2f}")
print(f"  coefficient of variation {cv:.4f}")
assert abs(cv - 1.0) < 0.02, "an exponential has standard deviation equal to its mean"
assert stats.kstest(intervals, 'expon', args=(0, 1 / RATE_HZ)).statistic < 0.01, \\
    "and the intervals really are exponential, not merely spread like one"

# Counts and intervals are two descriptions of one process, so a train built from
# exponential intervals must produce Poisson counts. A Kolmogorov-Smirnov test is
# the wrong instrument here: it is defined for continuous distributions and a
# count is not one. Compare the two step functions directly instead.
from_intervals = np.array([len(poisson_spike_times(RATE_HZ, 1.0, gen)) for _ in range(20_000)])
support = np.arange(0, from_intervals.max() + 1)
empirical_cdf = np.searchsorted(np.sort(from_intervals), support, side="right") / from_intervals.size
largest_gap = float(np.max(np.abs(empirical_cdf - stats.poisson.cdf(support, RATE_HZ))))
print(f"\\n  largest gap between the count distribution and Poisson({RATE_HZ:.0f}): "
      f"{largest_gap:.4f}")
assert largest_gap < 0.02, "accumulating exponential intervals gives Poisson counts, as it must"

print("\\nBoth descriptions gave 1, from the same underlying assumption that events do not")
print("know about each other. That is the reference point every real spike train gets")
print("compared against, and Section 2 is about how far from it they are.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. No neuron is Poisson

A real neuron cannot fire twice in immediate succession. After a spike there is a
refractory period of a few milliseconds during which the next one is impossible,
and that single piece of biophysics is enough to break both numbers from
Section 1.

The effect is easy to predict in direction and worth measuring in size. Forbidding
short intervals removes the shortest ones from the distribution, which reduces
their spread, so the coefficient of variation falls below 1. Fewer very short
intervals also means the count in a window varies less, so the Fano factor falls
below 1 too. A refractory neuron is **more regular** than chance, not less.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
def refractory_train(rate_hz, duration_s, refractory_s, gen):
    """Spike times with a hard refractory period after every spike."""
    expected = rate_hz * duration_s
    n_draw = int(expected + 10 * np.sqrt(expected) + 100)
    # A dead time added to every exponential interval. The resulting process has
    # a lower rate than `rate_hz`, which Section 2's table has to account for.
    intervals = gen.exponential(1.0 / rate_hz, n_draw) + refractory_s
    times = np.cumsum(intervals)
    return times[times < duration_s]

print(f"{'refractory (ms)':>16} {'CV of intervals':>17} {'Fano of counts':>16} "
      f"{'realised rate':>15}")
measured = {}
for refractory_ms in (0.0, 2.0, 5.0, 10.0):
    refractory_s = refractory_ms / 1000.0
    g2 = np.random.default_rng(500 + int(refractory_ms))
    long_train = refractory_train(RATE_HZ, 3000.0, refractory_s, g2)
    intervals = np.diff(long_train)
    window_counts = np.histogram(long_train, bins=np.arange(0, 3000.0, WINDOW_S))[0]
    measured[refractory_ms] = (float(intervals.std() / intervals.mean()),
                               fano_factor(window_counts))
    print(f"{refractory_ms:>16.0f} {measured[refractory_ms][0]:>17.4f} "
          f"{measured[refractory_ms][1]:>16.4f} {len(long_train) / 3000.0:>14.1f} Hz")

assert abs(measured[0.0][0] - 1.0) < 0.03, "with no refractory period, CV is 1"
assert abs(measured[0.0][1] - 1.0) < 0.08, "and so is the Fano factor"
for refractory_ms in (2.0, 5.0, 10.0):
    assert measured[refractory_ms][0] < measured[0.0][0], "a refractory period lowers CV"
    assert measured[refractory_ms][1] < measured[0.0][1], "and lowers the Fano factor"
assert measured[10.0][0] < 0.9 and measured[10.0][1] < 0.8, \\
    "and 10 ms of it moves both a long way from 1"

print(f"\\n  a 10 ms refractory period at {RATE_HZ:.0f} Hz took the CV from "
      f"{measured[0.0][0]:.2f} to {measured[10.0][0]:.2f}")
print(f"  and the Fano factor from {measured[0.0][1]:.2f} to {measured[10.0][1]:.2f}")

print("\\nSo a sub-Poisson Fano factor is what a healthy refractory neuron looks like, not")
print("evidence of anything interesting. This matters for reading the number in the")
print("other direction too: SPK 3 uses interval statistics to judge whether a sorted")
print("unit is one neuron or two, and the reason that works is exactly this. A single")
print("unit cannot violate its own refractory period, so intervals shorter than it are")
print("evidence of contamination rather than of fast firing.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Where SPK 4's null comes from

Phase locking asks whether spikes happen at a preferred phase of an ongoing
oscillation. The standard measure takes the phase at each spike, treats each as a
unit vector in the complex plane, and reports the length of their average:

$$\mathrm{PLV} = \left|\frac{1}{N}\sum_{j} e^{i\theta_j}\right|$$

If there is no locking the phases are uniform, so the vectors point in random
directions and mostly cancel. They do not cancel completely. The sum of $N$
random unit vectors is a two-dimensional random walk of $N$ steps, and STO 3
established that such a walk ends up a distance of order $\sqrt{N}$ from the
origin rather than at it. Dividing by $N$ gives a PLV of order $1/\sqrt{N}$.

The constant follows from the walk's endpoint being Rayleigh distributed, whose
mean is $\sqrt{\pi/2}$ times its scale. Carrying that through gives

$$\mathbb{E}[\mathrm{PLV}_{\text{null}}] = \frac{\sqrt{\pi}}{2\sqrt{N}}$$

which is the number SPK 4 compares against.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def phase_locking_value(phases: np.ndarray) -> np.ndarray:
    """Length of the mean unit vector, along the last axis."""
    return np.abs(np.exp(1j * phases).mean(axis=-1))

N_DRAWS = 20_000
g3 = np.random.default_rng(7)
print(f"phases drawn uniformly, so the true locking is zero\\n")
print(f"{'spikes N':>10} {'measured PLV':>14} {'sqrt(pi)/2/sqrt(N)':>20} {'ratio':>8}")
null_plv = {}
for n_spikes in (5, 10, 50, 200, 1000):
    phases = g3.uniform(0, 2 * np.pi, (N_DRAWS, n_spikes))
    null_plv[n_spikes] = float(phase_locking_value(phases).mean())
    predicted = np.sqrt(np.pi) / (2 * np.sqrt(n_spikes))
    print(f"{n_spikes:>10} {null_plv[n_spikes]:>14.5f} {predicted:>20.5f} "
          f"{null_plv[n_spikes] / predicted:>8.4f}")
    tolerance = 0.05 if n_spikes >= 10 else 0.03
    assert abs(null_plv[n_spikes] / predicted - 1.0) < tolerance, \\
        f"the null PLV must be sqrt(pi)/2/sqrt(N) at N={n_spikes}"

# The distribution behind it, not just its mean: the resultant length of a
# 2D random walk is Rayleigh.
resultant = np.abs(np.exp(1j * g3.uniform(0, 2 * np.pi, (N_DRAWS, 400))).sum(axis=-1))
scale = np.sqrt(400 / 2)
print(f"\\n  KS of the resultant length against Rayleigh(scale=sqrt(N/2)): "
      f"{stats.kstest(resultant, 'rayleigh', args=(0, scale)).statistic:.4f}")
assert stats.kstest(resultant, 'rayleigh', args=(0, scale)).statistic < 0.02, \\
    "the whole distribution is Rayleigh, which is where the constant comes from"

# A PLV of 0.28 means nothing at 10 spikes and a great deal at 1000.
print(f"\\n  a PLV of {null_plv[10]:.2f} is the AVERAGE under no locking at 10 spikes,")
print(f"  and {null_plv[10] / null_plv[1000]:.0f} times the average at 1000")
assert null_plv[10] > 5 * null_plv[1000], "so the same PLV means opposite things at two counts"

print("\\nThe null PLV is not zero and it depends on the spike count, which is the whole")
print("problem. STO 3's random walk is doing the work: N unit vectors that cancel on")
print("average still land sqrt(N) from the origin, and dividing by N leaves 1/sqrt(N).")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. Which means PLV compares firing rates

SPK 4 states that raw PLV compares spike counts. Section 3 says why, and this
section measures what it costs, because the size of the effect decides whether it
is a caveat or a confound.

The setup below holds the true locking fixed and varies only the number of spikes.
Any difference in the reported PLV is therefore an artifact. Since a real
comparison is usually between two conditions whose firing rates differ, that is
exactly the situation this app is in whenever it compares locking across
conditions.

There is a repair. The **pairwise phase consistency** averages the cosine of the
angle between every pair of spikes rather than taking the length of their mean.
A pair of independent phases has expected cosine zero regardless of how many
pairs there are, so the count cancels. It can be computed without forming the
pairs:

$$\mathrm{PPC} = \frac{\left|\sum_j e^{i\theta_j}\right|^2 - N}{N(N-1)}$$''')

m.task(
'''def pairwise_phase_consistency(phases: np.ndarray) -> np.ndarray:
    """Unbiased phase locking, from the identity above.

    Equal to the average cosine of the angle between all distinct pairs, but
    computed from the resultant so it costs O(N) rather than O(N^2).
    """
    # TODO: N is the size of the last axis
    # TODO: form the complex sum along the last axis
    # TODO: return (|sum|^2 - N) / (N * (N - 1))
    raise NotImplementedError("Implement pairwise_phase_consistency")''',
'''def pairwise_phase_consistency(phases: np.ndarray) -> np.ndarray:
    """Unbiased phase locking, from the identity above.

    Equal to the average cosine of the angle between all distinct pairs, but
    computed from the resultant so it costs O(N) rather than O(N^2).
    """
    n = phases.shape[-1]
    resultant = np.exp(1j * phases).sum(axis=-1)
    # |sum|^2 expands to N self-terms plus every ordered pair, so subtracting N
    # and dividing by N(N-1) leaves exactly the mean over distinct pairs.
    return (np.abs(resultant) ** 2 - n) / (n * (n - 1))''')

m.code('''# --- TEST CELL FOR STEP 4 ---
KAPPA = 0.8            # von Mises concentration: genuine, fixed, modest locking
N_REPS = 8000
g4 = np.random.default_rng(31)

# The identity, against the definition it claims to equal.
small = g4.vonmises(0.0, KAPPA, (200, 12))
by_definition = np.array([
    np.mean([np.cos(row[a] - row[b]) for a in range(12) for b in range(12) if a != b])
    for row in small
])
print(f"PPC identity against the explicit pairwise average: max difference "
      f"{np.max(np.abs(pairwise_phase_consistency(small) - by_definition)):.2e}")
assert np.allclose(pairwise_phase_consistency(small), by_definition, atol=1e-12)

print(f"\\nidentical true locking in every row; only the spike count changes\\n")
print(f"{'spikes N':>10} {'PLV':>9} {'null PLV':>10} {'PPC':>9}")
plv_by_n, ppc_by_n = {}, {}
for n_spikes in (10, 25, 50, 100, 400):
    phases = g4.vonmises(0.0, KAPPA, (N_REPS, n_spikes))
    plv_by_n[n_spikes] = float(phase_locking_value(phases).mean())
    ppc_by_n[n_spikes] = float(pairwise_phase_consistency(phases).mean())
    print(f"{n_spikes:>10} {plv_by_n[n_spikes]:>9.4f} "
          f"{np.sqrt(np.pi) / (2 * np.sqrt(n_spikes)):>10.4f} {ppc_by_n[n_spikes]:>9.4f}")

# PLV falls toward the truth as N grows; PPC is already there.
assert plv_by_n[10] > plv_by_n[400], "PLV is inflated at small N and settles as N grows"
ppc_values = list(ppc_by_n.values())
assert max(ppc_values) - min(ppc_values) < 0.005, "PPC does not depend on N at all"
# PPC estimates the SQUARE of the asymptotic PLV, which is worth knowing before
# comparing the two columns.
print(f"\\n  PPC is {np.mean(ppc_values):.4f}; the large-N PLV squared is "
      f"{plv_by_n[400] ** 2:.4f}")
assert abs(np.mean(ppc_values) - plv_by_n[400] ** 2) < 0.01, \\
    "PPC estimates the squared locking, so it is not on the same scale as PLV"

# The confound, stated as a comparison between two conditions.
print(f"\\ntwo conditions with the SAME locking and different firing rates\\n")
print(f"{'condition A':>12} {'condition B':>12} {'apparent PLV effect':>21} "
      f"{'apparent PPC effect':>21}")
for n_a, n_b in ((100, 100), (100, 50), (100, 25), (100, 10)):
    plv_gap = plv_by_n[n_b] - plv_by_n[n_a]
    ppc_gap = ppc_by_n[n_b] - ppc_by_n[n_a]
    print(f"{n_a:>12} {n_b:>12} {plv_gap:>+21.4f} {ppc_gap:>+21.4f}")
    assert abs(ppc_gap) < 0.01, "PPC reports no effect, which is correct"
assert plv_by_n[10] - plv_by_n[100] > 0.05, \\
    "PLV reports a substantial effect where there is none"

print("\\nA condition with ten spikes and a condition with a hundred, locked identically,")
print(f"differ in reported PLV by {plv_by_n[10] - plv_by_n[100]:+.3f}. Against locking values in the")
print("0.2 to 0.5 range that is not a caveat, it is the size of a result.")
print("\\nAnd the direction is the dangerous one. A quieter condition reports MORE locking,")
print("so any manipulation that reduces firing rate, which describes most of what")
print("stimulation does, produces an apparent increase in phase locking for free.")
print("\\nPPC removed it completely, and the reason is worth keeping separate from the")
print("formula: the bias comes from N self-terms in the squared resultant, and PPC")
print("subtracts exactly those. It is not a correction factor fitted to anything, it is")
print("the same quantity with the self-comparisons left out.")
print("\\nTwo things to carry into SPK 4. PPC estimates the SQUARE of the locking, so it")
print("is not interchangeable with PLV in a figure. And subsampling every condition to a")
print("common spike count also works, at the cost of throwing away data from the")
print("condition that had more.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **A Poisson process is one assumption described two ways.** Counts are Poisson
   with a Fano factor of 1, intervals are exponential with a coefficient of
   variation of 1, and building a train from exponential intervals produces
   Poisson counts, as it must.
2. **A refractory period alone makes a neuron sub-Poisson.** Ten milliseconds of
   it took the interval CV from 1.01 to 0.83 and the Fano factor from 1.01 to
   0.67. A Fano factor below 1 is what a healthy neuron looks like, and it is
   also why SPK 3's contamination check works: a single unit cannot violate its
   own refractory period.
3. **The phase-locking null is $\sqrt{\pi}/2\sqrt{N}$, and it comes from STO 3.**
   $N$ unit vectors with random directions are a two-dimensional random walk, so
   they land a distance of order $\sqrt{N}$ from the origin rather than at it.
   The resultant length is Rayleigh distributed, verified against the whole
   distribution and not just its mean, and the constant follows from the Rayleigh
   mean.
4. **So raw PLV compares spike counts.** With the true locking held fixed, a
   condition with 10 spikes reported a PLV about 0.06 higher than one with 100.
   Against locking values of 0.2 to 0.5 that is the size of a result, and the
   direction is the dangerous one: a quieter condition reports more locking, so
   anything that lowers firing rate manufactures an apparent increase.
5. **Pairwise phase consistency removes it exactly.** Its value did not move
   across a fortyfold range of spike counts. The bias is the $N$ self-terms in
   the squared resultant and PPC subtracts precisely those, so it is the same
   quantity with self-comparisons excluded rather than a fitted correction. It
   estimates the **square** of the locking, which is not the same scale as PLV.

That completes Probability and Stochastic Processes. The four lessons together
supply what the rest of this curriculum had been assuming: STO 1 the distribution
of an estimator, STO 2 the price of correlation, STO 3 what happens when there is
no stationary distribution at all, and STO 4 the same arithmetic for data made of
events.

### Exercises

**Exercise 1.** Section 2's model adds a hard dead time to an exponential
interval, which is one of several ways to build a refractory process. Implement a
second, where the rate recovers gradually after a spike, and say whether the CV
and Fano factor distinguish the two.

**Exercise 2.** Section 4 offers subsampling as an alternative to PPC. Work out
how much statistical power subsampling costs when one condition has four times
the spikes of the other, and say at what ratio you would prefer it to PPC anyway.

**Exercise 3.** SPK 4 reports PLV. Decide whether this app should report PPC
instead, alongside, or not at all, given that PPC is on a squared scale and
existing figures use PLV. State what would have to change in
`configs/statistics.yaml` for the answer to be readable from a figure caption.

---

That is the end of the Foundations course on probability. Everything after it in
the program uses these results, and until now used them on trust.
''')

m.emit()
verify("10_stochastic", "04_point_processes_and_phase_locking")
print("  STO 4 OK")
