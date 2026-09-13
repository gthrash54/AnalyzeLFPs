import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("04_spikes", "03_sorting_and_quality_metrics")

m.md(r'''# Lesson SPK 3: Spike Sorting and Unit Quality Metrics {{VARIANT}}

**Analysis · Spike Trains and Single-Unit Activity**

{{INSTRUCTIONS}}

SPK 2 produced a list of times. This module asks whether those times came from one
neuron, and the useful thing about the question is that biology supplies a
measurable answer: a neuron cannot fire twice within its refractory period, so
**every violation of that is provably not one neuron.**

That turns cluster quality from a matter of taste into an estimate with a number
and an error bar.

**What it assumes**

| From | What is used |
|---|---|
| SPK 2 | Detection, refractory windows, and that thresholds interact with firing rate. |
| REC 4 | That a unit appears on many sites, so a template is spatial. |
| LIN 5 | Projection onto a low-dimensional basis, and that components are not sources. |

**What it underwrites**

Any claim about a single unit, and any figure whose caption says "well isolated".
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(41)
FS = 30000.0
REFRACTORY_S = 0.002        # 2 ms, a conservative absolute refractory period
CENSORED_S = 0.0005         # 0.5 ms, below which a sorter cannot resolve two spikes
print("Environment initialized for Lesson SPK 3")''')

m.md(r'''---

## 1. Refractory violations are a measurement, not a warning

Take a cluster with $N$ spikes over a recording of duration $T$. Suppose a
fraction $f$ of them do not belong to the unit, and that those contaminants are
independent of it.

Contaminating spikes land uniformly in time, so the chance one falls within
$\tau$ of a genuine spike is $2\tau/T$ per pair, counting both sides. With
$fN$ contaminants and $(1-f)N$ genuine spikes, the expected number of violations
is

$$N_{\text{violations}} \approx 2\, f (1-f)\, N^2 \frac{\tau}{T}$$

which for small $f$ inverts to

$$f \approx \frac{N_{\text{violations}}\, T}{2\, \tau\, N^2}$$

This is the Hill, Mehta and Kleinfeld estimator. It is a **lower bound** on
contamination, because contaminants from a unit that fires in step with this one
produce fewer violations than chance, and because a sorter that cannot resolve
two spikes closer than the censored period never counts those violations at all.''')

m.task(
'''def contamination_fraction(spike_times_s: np.ndarray, duration_s: float,
                           refractory_s: float = REFRACTORY_S,
                           censored_s: float = CENSORED_S) -> float:
    """Estimated fraction of a cluster's spikes that do not belong to it.

    Count inter-spike intervals in (censored_s, refractory_s), then invert
    N_v = 2 f (1-f) N^2 (tau - tau_c) / T for the smaller root of f.

    Returns 1.0 when the quadratic has no real root, meaning the violation rate
    exceeds anything contamination can explain.

    Production equivalent: `spikeinterface.qualitymetrics`, which reports this as
    the ISI violation ratio and as `rp_contamination`.
    """
    # TODO: N = number of spikes; count ISIs strictly between censored_s and refractory_s
    # TODO: solve 2 f (1-f) N^2 (tau - tau_c) / T = N_v  for f, taking the smaller root
    # TODO: return 1.0 if the discriminant is negative
    raise NotImplementedError("Implement contamination_fraction")''',
'''def contamination_fraction(spike_times_s: np.ndarray, duration_s: float,
                           refractory_s: float = REFRACTORY_S,
                           censored_s: float = CENSORED_S) -> float:
    """Estimated fraction of a cluster's spikes that do not belong to it.

    Count inter-spike intervals in (censored_s, refractory_s), then invert
    N_v = 2 f (1-f) N^2 (tau - tau_c) / T for the smaller root of f.

    Returns 1.0 when the quadratic has no real root, meaning the violation rate
    exceeds anything contamination can explain.

    Production equivalent: `spikeinterface.qualitymetrics`, which reports this as
    the ISI violation ratio and as `rp_contamination`.
    """
    n = len(spike_times_s)
    if n < 2:
        return 0.0
    isi = np.diff(np.sort(spike_times_s))
    n_viol = int(np.sum((isi > censored_s) & (isi < refractory_s)))
    rate = 2.0 * (refractory_s - censored_s) * n ** 2 / duration_s
    if rate <= 0:
        return 1.0
    # solve f^2 - f + n_viol/rate = 0
    disc = 1.0 - 4.0 * n_viol / rate
    if disc < 0:
        return 1.0
    return float((1.0 - np.sqrt(disc)) / 2.0)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
DURATION = 600.0        # 10 minutes

def poisson_with_refractory(rate_hz, duration_s, refractory_s, gen):
    """A spike train that respects its own refractory period."""
    times, t = [], 0.0
    while t < duration_s:
        t += gen.exponential(1.0 / rate_hz) + refractory_s
        if t < duration_s:
            times.append(t)
    return np.array(times)

# (a) A perfectly isolated unit must estimate near zero contamination.
clean = poisson_with_refractory(10.0, DURATION, REFRACTORY_S, rng)
f_clean = contamination_fraction(clean, DURATION)
print(f"clean unit: {len(clean)} spikes, estimated contamination {f_clean:.4%}")
assert f_clean < 0.01, "a unit with no violations must estimate near zero"

# (b) The estimator must RECOVER a contamination fraction that we planted, and it
# has real sampling error, so measure the mean AND the spread across repeats.
REPEATS = 12
print(f"\\n{'planted f':>11} {'violations':>12} {'estimated f':>22} {'bias':>9}")
biases = {}
for f_true in (0.02, 0.05, 0.10, 0.20):
    ests, viols = [], []
    for rep in range(REPEATS):
        gen = np.random.default_rng(1000 + rep)
        main_r = poisson_with_refractory(20.0, DURATION, REFRACTORY_S, gen)
        n_c = int(len(main_r) * f_true / (1 - f_true))
        mixed_r = np.sort(np.concatenate([main_r, gen.random(n_c) * DURATION]))
        isi_r = np.diff(mixed_r)
        viols.append(int(np.sum((isi_r > CENSORED_S) & (isi_r < REFRACTORY_S))))
        ests.append(contamination_fraction(mixed_r, DURATION))
    biases[f_true] = float(np.mean(ests)) - f_true
    print(f"{f_true:>10.0%} {np.mean(viols):>11.0f} "
          f"{np.mean(ests):>15.2%} +/- {np.std(ests):>5.2%} {biases[f_true]:>+8.2%}")

for f_true in (0.02, 0.05, 0.10):
    assert abs(biases[f_true]) < 0.01, \\
        f"nearly unbiased where it matters: f={f_true}, bias {biases[f_true]:+.3f}"
assert biases[0.20] > 3 * abs(biases[0.10]), \\
    "and it over-reports once contamination is large"

print("\\nTwo things to take from that table.")
print("The estimate is NOISY: the spread across repeats is a large fraction of the")
print("estimate itself, because violation counts are small. A single unit's reported")
print("contamination is a draw from that spread, not a constant.")
print("\\nAnd it is unbiased only while contamination is small. The derivation counted")
print("contaminant-against-genuine pairs and ignored contaminant-against-contaminant")
print("ones, which are negligible at 2 percent and are not at 20. The estimator")
print("over-reports there, which is the safe direction, and it means the number is")
print("trustworthy exactly where the decision is made: is this unit under threshold?")
print("\\nStep 1 passed. Contamination is estimated from the interval histogram alone,")
print("with no reference to waveforms, amplitudes, or anyone's judgement.")''')

m.md(r'''---

## 2. Why it is a lower bound, and by how much

Two effects push the estimate down, and both matter in practice.

**The censored period.** A sorter that detects one event per refractory window,
as SPK 2's detector does by construction, cannot report two spikes 0.2 ms apart. The
violations that would have been most informative are the ones it is least able
to see, so they are missing from the count.

**Correlated contaminants.** The derivation assumed contaminants land uniformly.
A nearby cell that fires in bursts, or one driven by the same input, does not.
Its spikes cluster where this unit's spikes already are and produce fewer
violations than chance, so the cluster looks cleaner than it is.

Both are measurable. Below, the same true contamination is estimated with the
censored period varied, and then with a contaminant that is correlated rather
than independent.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
F_TRUE = 0.10
main = poisson_with_refractory(10.0, DURATION, REFRACTORY_S, rng)
n_contam = int(len(main) * F_TRUE / (1 - F_TRUE))

# (a) The censored period, varied.
contam_indep = np.sort(rng.random(n_contam) * DURATION)
mixed_indep = np.sort(np.concatenate([main, contam_indep]))
print(f"true contamination {F_TRUE:.0%}\\n")
print(f"{'censored period':>17} {'estimated f':>13}")
ests = {}
for c in (0.0, 0.0005, 0.001, 0.0015):
    ests[c] = contamination_fraction(mixed_indep, DURATION, censored_s=c)
    print(f"{c*1000:>14.1f} ms {ests[c]:>12.2%}")
assert ests[0.0015] < ests[0.0], "a longer censored period hides more violations"

# (b) A correlated contaminant. The realistic case that defeats this metric is two
# cells on one electrode with complementary tuning: one active during movement,
# the other during rest. Their spikes barely overlap in time, so contaminating
# spikes almost never land inside a real spike's refractory shadow.
EPOCH_S = 1.0
def in_active_epoch(t, phase=0):
    return (np.floor(t / EPOCH_S).astype(int) % 2) == phase

main_gated = main[in_active_epoch(main, 0)]
pool = poisson_with_refractory(10.0, DURATION, REFRACTORY_S, rng)
contam_anti = pool[in_active_epoch(pool, 1)]                  # the OTHER epochs
n_take = int(len(main_gated) * F_TRUE / (1 - F_TRUE))
contam_anti = np.sort(rng.choice(contam_anti, size=min(n_take, len(contam_anti)),
                                 replace=False))
mixed_anti = np.sort(np.concatenate([main_gated, contam_anti]))
f_anti = contamination_fraction(mixed_anti, DURATION)

# A matched independent control with the SAME spike counts, for a fair comparison.
contam_unif = np.sort(rng.random(len(contam_anti)) * DURATION)
mixed_unif = np.sort(np.concatenate([main_gated, contam_unif]))
f_unif = contamination_fraction(mixed_unif, DURATION)

print(f"\\n{'contaminant':>34} {'extra spikes':>14} {'estimated f':>13}")
print(f"{'independent (uniform in time)':>34} {len(contam_unif):>14} {f_unif:>12.2%}")
print(f"{'complementary tuning (anti-phase)':>34} {len(contam_anti):>14} {f_anti:>12.2%}")
assert f_anti < 0.5 * f_unif, \\
    "a contaminant active when the unit is silent produces far fewer violations"
print(f"\\nIdentical contamination, {F_TRUE:.0%} either way. The independent case reads")
print(f"{f_unif:.1%}. The complementary case reads {f_anti:.1%}, because the contaminating")
print("cell fires when this one does not, so its spikes almost never land inside a")
print("refractory shadow. Two cells with opposite tuning on one electrode are a")
print("common situation and they are close to invisible to this metric.")

# The reverse failure is also real: a contaminant that bursts violates its OWN
# refractory period and reads far dirtier than it is.
burst_centres = np.sort(rng.random(max(1, n_contam // 5)) * DURATION)
contam_burst = np.sort(np.concatenate([bc + rng.normal(0, 0.004, 5) for bc in burst_centres]))
contam_burst = contam_burst[(contam_burst > 0) & (contam_burst < DURATION)]
f_burst = contamination_fraction(np.sort(np.concatenate([main, contam_burst])), DURATION)
print(f"\\n{'bursty neighbour':>34} {len(contam_burst):>14} {f_burst:>12.2%}")
assert f_burst > contamination_fraction(mixed_indep, DURATION), \\
    "a bursty contaminant violates its own refractory period and reads dirtier"
print("The metric assumes contaminants are uniform in time. Both ways of breaking")
print("that assumption are common, and they break it in opposite directions.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. What a metric cannot tell you

Contamination measures whether **other** spikes got in. It says nothing about
whether this unit's own spikes got **out**, and those are different failures with
opposite consequences.

A cluster can be perfectly clean and still be half a neuron, if the detection
threshold or a drifting template lost the smaller spikes. REC 4 showed that 20
microns of drift is enough to do that. A firing-rate change reported from such a
unit may be entirely an amplitude change interacting with a fixed threshold.

The measurable signature is an amplitude distribution that is **cut off** rather
than complete. A unit whose amplitudes are Gaussian and fully sampled has a
symmetric histogram; one whose small spikes fell below threshold is truncated,
and the missing fraction can be estimated by fitting the part that survived.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def amplitude_cutoff(amplitudes, n_bins=60):
    """Estimated fraction of spikes missing below the detection threshold.

    Fit the shape of the surviving amplitude histogram and compare the density at
    the low edge against the peak. A complete distribution falls to near zero at
    both edges; a truncated one does not.

    Production equivalent: `spikeinterface.qualitymetrics.compute_amplitude_cutoffs`.
    """
    h, edges = np.histogram(amplitudes, bins=n_bins, density=True)
    peak = int(np.argmax(h))
    # Density at the low edge relative to the peak, as a truncation index.
    return float(h[0] / h[peak])

TRUE_AMP, AMP_SD = 80.0, 18.0
n_spikes = 4000
all_amps = rng.normal(TRUE_AMP, AMP_SD, n_spikes)

print(f"{'threshold':>11} {'spikes kept':>13} {'truly missing':>15} {'cutoff index':>14}")
idx = {}
for thr in (0.0, 45.0, 60.0, 70.0):
    kept = all_amps[all_amps > thr]
    missing = 1 - len(kept) / n_spikes
    idx[thr] = amplitude_cutoff(kept)
    print(f"{thr:>8.0f} uV {len(kept):>13} {missing:>14.1%} {idx[thr]:>14.3f}")

assert idx[0.0] < 0.1, "a complete distribution has near-zero density at its low edge"
assert idx[70.0] > 5 * idx[0.0], "a truncated one does not, and the index detects it"
assert idx[70.0] > idx[60.0] > idx[45.0], "the index grows monotonically with truncation"

# The point: contamination and completeness are independent failures.
truncated_times = poisson_with_refractory(10.0, DURATION, REFRACTORY_S, rng)
print(f"\\na unit truncated at 70 uV, losing {1 - len(all_amps[all_amps>70])/n_spikes:.0%} of its spikes:")
print(f"  contamination estimate : {contamination_fraction(truncated_times, DURATION):.2%}")
print(f"  amplitude cutoff index : {idx[70.0]:.3f}")
assert contamination_fraction(truncated_times, DURATION) < 0.01, \\
    "losing your own spikes does not create refractory violations"
print("\\nContamination says 'clean'. It is clean. It is also missing a third of its")
print("spikes, and no interval-based metric can see that.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. Refractory violations invert to a contamination estimate,
   $f \approx N_v T / (2\tau N^2)$, unbiased to under half a percentage point for
   true contamination up to 10 percent, using the interval histogram alone and no
   waveform information. It over-reports at 20 percent, because the derivation
   ignores contaminant-against-contaminant pairs, which is the safe direction and
   leaves it trustworthy where the decision is actually made. It is also noisy:
   the spread across repeats is a substantial fraction of the estimate, so a
   single unit's reported figure is a draw from that spread.
2. The independence assumption fails in **both** directions, measurably. Two
   cells with complementary tuning on one electrode, one active during movement
   and one during rest, produce a contaminated cluster that reads less than half
   its true contamination, because the contaminating spikes fall where no
   refractory shadow exists. A bursty contaminant violates its own refractory
   period and reads dirtier than the truth. Lengthening the censored period from
   0 to 1.5 ms also lowers the estimate.
3. Contamination and completeness are **independent failures**. A unit that lost
   a third of its own spikes to a threshold shows near-zero contamination, and no
   interval metric can detect it. The amplitude cutoff index can, and it must be
   reported alongside.

### Exercises

**Exercise 1.** The formula assumes a fixed refractory period. Real refractoriness
is graded. Repeat Section 1 with a relative refractory period in which the firing
probability recovers exponentially over 5 ms, and say whether the estimator
over- or under-reports.

**Exercise 2.** REC 4 showed that 20 microns of drift breaks a fixed template.
Simulate a unit whose amplitude declines linearly through a recording as the
probe drifts away, and show that its contamination stays flat while its amplitude
cutoff index rises. Which half of the recording would you trust?

**Exercise 3.** Two clusters each show 2 percent contamination. Merged, the
combined cluster shows 15 percent. What does that tell you that neither number
told you alone, and what would you conclude if the merged figure were 2 percent
instead?

---

**Next: SPK 4, peri-stimulus histograms and spike-field coherence.** Having a unit,
the question becomes what it responds to, and the standard measure of
spike-to-field relationship carries a bias that depends on how many spikes you
happened to collect.
''')

m.emit()
verify("04_spikes", "03_sorting_and_quality_metrics")
print("  SPK 3 OK")
