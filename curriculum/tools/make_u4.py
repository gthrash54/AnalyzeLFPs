import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("04_spikes", "04_psth_and_spike_field_coherence")

m.md(r'''# Lesson SPK 4: Peri-Stimulus Histograms and Spike-Field Coherence {{VARIANT}}

**Analysis · Spike Trains and Single-Unit Activity · final lesson**

{{INSTRUCTIONS}}

SPK 3 established a unit. This module asks what it responds to, and what it is
coupled to, and the second question carries a bias that has produced a great deal
of confident literature.

**What it assumes**

| From | What is used |
|---|---|
| SIG 3 | That resolution is set by window duration, and the effect of a taper. |
| SIG 4 | That the periodogram is inconsistent, and that averaging reduces variance. |
| SIG 6 | The analytic signal, and that phase is defined only within a band. |
| SPK 3 | A sorted unit with a known contamination. |

**What it underwrites**

Guardrail **G11**, which requires a control condition, and guardrail **G8**,
which asks for a z-score against a null rather than a raw number.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, hilbert

rng = np.random.default_rng(51)
FS = 1000.0
print("Environment initialized for Lesson SPK 4")''')

m.md(r'''---

## 1. The histogram, and the bin width nobody justifies

A peri-stimulus time histogram counts spikes in bins relative to an event and
averages over trials. The only free parameter is the bin width, and it makes the
same trade SIG 3 and SIG 5 already made twice.

Wide bins average more spikes, so the estimate is less noisy, and they smear a
sharp response. Narrow bins localise it and are dominated by counting noise,
because the number of spikes in a bin is small and Poisson.

The relative standard error of a bin containing $\lambda$ expected spikes is
$1/\sqrt{\lambda}$, and $\lambda$ is proportional to bin width times trial count.
So halving the bin width costs $\sqrt{2}$ in noise, and the honest way to choose
is to state the narrowest response you intend to claim and pick a width below it.''')

m.task(
'''def psth(spike_times_s, event_times_s, window_s=(-0.5, 1.0), bin_s=0.02):
    """Peri-stimulus time histogram in spikes per second.

    Returns (bin_centres_s, rate_hz). Normalise by bin width and trial count so
    the result is a firing rate rather than a count.

    Production equivalent: `elephant.statistics.time_histogram`, or
    `mne.Epochs` for the field side of the same alignment.
    """
    # TODO: build bin edges over window_s with spacing bin_s
    # TODO: for each event, histogram (spike_times - event) within the window
    # TODO: sum across events, divide by (n_events * bin_s) to get Hz
    # TODO: return bin centres and the rate
    raise NotImplementedError("Implement psth")''',
'''def psth(spike_times_s, event_times_s, window_s=(-0.5, 1.0), bin_s=0.02):
    """Peri-stimulus time histogram in spikes per second.

    Returns (bin_centres_s, rate_hz). Normalise by bin width and trial count so
    the result is a firing rate rather than a count.

    Production equivalent: `elephant.statistics.time_histogram`, or
    `mne.Epochs` for the field side of the same alignment.
    """
    edges = np.arange(window_s[0], window_s[1] + bin_s / 2, bin_s)
    counts = np.zeros(len(edges) - 1)
    for ev in event_times_s:
        rel = spike_times_s - ev
        rel = rel[(rel >= window_s[0]) & (rel < window_s[1])]
        counts += np.histogram(rel, bins=edges)[0]
    centres = (edges[:-1] + edges[1:]) / 2
    return centres, counts / (len(event_times_s) * bin_s)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
# A unit with a known response: baseline 5 Hz, a 40 Hz burst lasting 50 ms at t=0.
BASE_HZ, PEAK_HZ, RESP_MS = 5.0, 45.0, 50.0
N_TRIALS, TRIAL_S = 300, 2.0

def simulate(n_trials=N_TRIALS, seed=0):
    gen = np.random.default_rng(seed)
    events, spikes = [], []
    for k in range(n_trials):
        t0 = k * TRIAL_S + 0.5
        events.append(t0)
        n_base = gen.poisson(BASE_HZ * TRIAL_S)
        spikes.extend(k * TRIAL_S + gen.random(n_base) * TRIAL_S)
        n_resp = gen.poisson((PEAK_HZ - BASE_HZ) * RESP_MS / 1000.0)
        spikes.extend(t0 + gen.random(n_resp) * RESP_MS / 1000.0)
    return np.sort(np.array(spikes)), np.array(events)

spk, ev = simulate()
centres, rate = psth(spk, ev, bin_s=0.01)

baseline = float(np.mean(rate[centres < -0.1]))
peak = float(np.max(rate[(centres >= 0) & (centres < RESP_MS / 1000.0)]))
print(f"planted baseline {BASE_HZ:.0f} Hz, measured {baseline:.2f} Hz")
print(f"planted peak     {PEAK_HZ:.0f} Hz, measured {peak:.2f} Hz")
assert abs(baseline - BASE_HZ) < 1.0, "the PSTH must recover the baseline rate"
assert peak > 0.6 * PEAK_HZ, "and must recover most of the response"

# The bin-width trade, measured on both axes at once.
print(f"\\n{'bin (ms)':>10} {'peak (Hz)':>11} {'baseline noise':>16} {'response width':>16}")
for bin_s in (0.002, 0.005, 0.02, 0.1):
    c, r = psth(spk, ev, bin_s=bin_s)
    base_noise = float(np.std(r[c < -0.1]))
    above = r > (BASE_HZ + np.max(r)) / 2
    width_ms = float(np.sum(above) * bin_s * 1000)
    print(f"{bin_s*1000:>9.0f} {np.max(r):>11.1f} {base_noise:>16.2f} {width_ms:>13.0f} ms")

c_fine, r_fine = psth(spk, ev, bin_s=0.002)
c_coarse, r_coarse = psth(spk, ev, bin_s=0.1)
assert np.std(r_fine[c_fine < -0.1]) > np.std(r_coarse[c_coarse < -0.1]), \\
    "narrow bins are noisier"
assert np.max(r_coarse) < np.max(r_fine), "and wide bins flatten the peak"
print("\\nStep 1 passed. Same trade as SIG 3 and SIG 5: precision in time against variance.")''')

m.md(r'''---

## 2. Spike-field coherence, and the bias that is not a finding

Spike-field coherence asks whether a unit fires at a preferred phase of an
oscillation. The natural measure is the phase-locking value: take the field's
instantaneous phase at each spike time, using SIG 6's analytic signal, and compute
the length of the mean unit vector.

$$\text{PLV} = \left|\frac{1}{N}\sum_{j=1}^{N} e^{i\phi_j}\right|$$

Here is the problem. For $N$ **independent** phases, the sum is a random walk of
$N$ unit steps, whose expected length is $\sqrt{N}$, not zero. So

$$\mathbb{E}[\text{PLV}] \approx \frac{\sqrt{\pi}}{2\sqrt{N}} \quad \text{under the null}$$

The measured coherence of a unit that is not coupled to anything is **not zero,
and it depends on how many spikes you collected.** A unit that fires more in one
condition will therefore show lower PLV in that condition, from arithmetic alone,
and comparing PLV between conditions with different spike counts compares spike
counts.''')

m.task(
'''def phase_locking_value(phases_rad: np.ndarray) -> float:
    """Length of the mean unit vector over a set of phases, in [0, 1]."""
    # TODO: mean of exp(1j * phases), then its absolute value
    raise NotImplementedError("Implement phase_locking_value")


def spike_phases(field: np.ndarray, spike_idx: np.ndarray, band, fs: float = FS):
    """Instantaneous phase of `field` within `band`, sampled at spike times.

    SIG 6: filter first, then take the analytic signal. A phase from unfiltered
    broadband data does not refer to the band you mean.
    """
    # TODO: bandpass the field with butter + filtfilt over `band`
    # TODO: take np.angle of the analytic signal (scipy.signal.hilbert)
    # TODO: return the phases at the given spike indices
    raise NotImplementedError("Implement spike_phases")''',
'''def phase_locking_value(phases_rad: np.ndarray) -> float:
    """Length of the mean unit vector over a set of phases, in [0, 1]."""
    return float(np.abs(np.mean(np.exp(1j * np.asarray(phases_rad)))))


def spike_phases(field: np.ndarray, spike_idx: np.ndarray, band, fs: float = FS):
    """Instantaneous phase of `field` within `band`, sampled at spike times.

    SIG 6: filter first, then take the analytic signal. A phase from unfiltered
    broadband data does not refer to the band you mean.
    """
    b, a = butter(4, list(band), btype='band', fs=fs)
    phase = np.angle(hilbert(filtfilt(b, a, field)))
    return phase[np.asarray(spike_idx, dtype=int)]''')

m.code('''# --- TEST CELL FOR STEP 2 ---
# (a) PLV must be 1 for identical phases and near 0 for many uniform ones.
assert np.isclose(phase_locking_value(np.zeros(100)), 1.0), "identical phases lock perfectly"
big_uniform = rng.random(400000) * 2 * np.pi
assert phase_locking_value(big_uniform) < 0.01, "many uniform phases nearly cancel"

# (b) THE BIAS. With NO coupling at all, PLV depends only on the spike count, and
# it follows sqrt(pi)/(2 sqrt(N)). Measure it against that prediction.
print(f"{'spikes N':>10} {'measured PLV':>14} {'sqrt(pi)/2/sqrt(N)':>20}")
for N in (10, 30, 100, 1000, 10000):
    vals = [phase_locking_value(rng.random(N) * 2 * np.pi) for _ in range(400)]
    predicted = np.sqrt(np.pi) / (2 * np.sqrt(N))
    print(f"{N:>10} {np.mean(vals):>14.4f} {predicted:>20.4f}")
    assert abs(np.mean(vals) - predicted) < 0.25 * predicted, \\
        f"the null PLV at N={N} must follow the random-walk prediction"

print("\\nA unit coupled to nothing shows PLV 0.28 with 10 spikes and 0.009 with 10000.")
print("The number is a spike count in disguise.")

# (c) The consequence for a between-condition comparison, with no coupling anywhere.
t = np.arange(60000) / FS
field = filtfilt(*butter(4, [15.0, 25.0], btype='band', fs=FS), rng.standard_normal(len(t)))
rest_idx = np.sort(rng.choice(len(t) - 1, size=200, replace=False))
task_idx = np.sort(rng.choice(len(t) - 1, size=2000, replace=False))
plv_rest = phase_locking_value(spike_phases(field, rest_idx, (15.0, 25.0)))
plv_task = phase_locking_value(spike_phases(field, task_idx, (15.0, 25.0)))
print(f"\\nno coupling in either condition, spikes chosen at random:")
print(f"  rest, {len(rest_idx):>4} spikes: PLV {plv_rest:.4f}")
print(f"  task, {len(task_idx):>4} spikes: PLV {plv_task:.4f}")
assert plv_rest > plv_task, \\
    "the condition with fewer spikes shows HIGHER coherence, with no coupling present"
print("\\nRest looks more coherent than task. Nothing is coupled. The unit simply")
print("fired less during rest.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. The fix, and what it costs

Two repairs are standard and both are worth understanding rather than invoking.

**Match the spike counts.** Subsample the larger condition to the size of the
smaller, repeatedly, and compare distributions. This removes the bias exactly,
because both sides then have the same null, and it costs statistical power in
proportion to how unequal the counts were.

**Compare against a shuffled null.** Recompute the PLV many times with the spike
times shifted relative to the field, which destroys any real coupling while
preserving both the spike count and the field's structure. Report the z-score
against that null rather than the raw PLV. This is guardrail G8's requirement,
applied to a coherence rather than to a spectrum.

Below, both are applied to data with a genuine coupling planted in one condition
only, and each is checked for whether it recovers the truth.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
b_beta, a_beta = butter(4, [15.0, 25.0], btype='band', fs=FS)
field_beta = filtfilt(b_beta, a_beta, rng.standard_normal(len(t)))
phase_beta = np.angle(hilbert(field_beta))

def draw_spikes(n, coupling, gen):
    """Spike indices, `coupling` in [0,1] biasing them toward phase 0."""
    idx = []
    while len(idx) < n:
        cand = gen.integers(100, len(t) - 100, size=n * 4)
        keep = gen.random(len(cand)) < (1 - coupling) + coupling * (1 + np.cos(phase_beta[cand])) / 2
        idx.extend(cand[keep].tolist())
    return np.sort(np.array(idx[:n]))

REST_N, TASK_N = 250, 2500
rest_spk = draw_spikes(REST_N, 0.0, np.random.default_rng(61))     # no coupling
task_spk = draw_spikes(TASK_N, 0.6, np.random.default_rng(62))     # real coupling

raw_rest = phase_locking_value(phase_beta[rest_spk])
raw_task = phase_locking_value(phase_beta[task_spk])
print(f"raw PLV: rest {raw_rest:.4f} ({REST_N} spikes), task {raw_task:.4f} ({TASK_N} spikes)")

# Repair 1: match the counts.
sub = [phase_locking_value(phase_beta[np.random.default_rng(s).choice(task_spk, REST_N,
                                                                     replace=False)])
       for s in range(200)]
print(f"\\ncount-matched task PLV: {np.mean(sub):.4f} +/- {np.std(sub):.4f} "
      f"(rest {raw_rest:.4f})")
assert np.mean(sub) > raw_rest, "with counts matched, the real coupling still shows"

# Repair 2: z-score against a circular-shift null, which preserves spike count.
def shift_null(spk_idx, n_perm=300):
    out = []
    for s in range(n_perm):
        shift = np.random.default_rng(700 + s).integers(1000, len(t) - 1000)
        out.append(phase_locking_value(phase_beta[(spk_idx + shift) % len(t)]))
    return np.array(out)

z = {}
for name, spk_idx, raw in (("rest", rest_spk, raw_rest), ("task", task_spk, raw_task)):
    null = shift_null(spk_idx)
    z[name] = (raw - null.mean()) / null.std()
    print(f"{name:>6}: raw {raw:.4f}, null {null.mean():.4f} +/- {null.std():.4f}, "
          f"z = {z[name]:+.2f}")

assert z["task"] > 3.0, "a real coupling must survive as a large z"
assert abs(z["rest"]) < 3.0, "and an absent one must not"
assert z["task"] > z["rest"], "the z-score orders the conditions correctly"
print("\\nHere the planted coupling was strong enough that the raw numbers already")
print("pointed the right way. What the null adds is the part you cannot get from a")
print("raw PLV: rest's 0.046 is BELOW its own null of 0.057, so it is not weak")
print("coupling, it is no coupling. Only the null can tell those apart, and only the")
print("null gives task's 0.231 a magnitude. That is what G8 asks for.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established, and what Spike Trains established

1. A PSTH recovers a planted baseline and response, and its bin width trades
   time precision against counting noise at the rate $1/\sqrt{\lambda}$. Choose
   it from the narrowest response you intend to claim, and say so.
2. **Phase-locking value is biased by spike count.** Under the null it is
   $\sqrt{\pi}/2\sqrt{N}$, which the measurement confirms across three orders of
   magnitude of $N$. A unit coupled to nothing shows PLV 0.28 with 10 spikes and
   0.009 with 10000, so comparing raw PLV between conditions with different
   firing rates compares firing rates.
3. Count matching and a circular-shift null both repair it. With a coupling
   planted in one condition only, the count-matched comparison held up and the
   z-scores separated $+20.5$ from $-0.36$. The null does something a raw PLV
   cannot: rest's 0.046 sits *below* its own null of 0.057, so it is no coupling
   rather than weak coupling. That is guardrail G8 applied to a coherence.

**Spike Trains is complete.** SPK 1 split the bands and found that the famous spike-bleed
contamination of high gamma does not survive measurement at realistic amplitudes.
SPK 2 showed the noise estimator decides the threshold and the threshold decides the
between-condition comparison. SPK 3 turned cluster quality into a number, and found
the two ways that number lies. SPK 4 found that the standard measure of spike-field
coupling is a spike count until you correct it.

### Exercises

**Exercise 1.** The PLV bias is $\sqrt{\pi}/2\sqrt{N}$. Derive the corresponding
bias for the pairwise phase consistency, which is constructed to be unbiased, and
verify numerically that it is.

**Exercise 2.** Section 3's circular shift preserves the field and the spike
count but destroys the spike train's own autocorrelation relative to the field.
Construct a case where that matters, using a bursty unit, and propose a null that
preserves burst structure.

**Exercise 3.** SPK 3 established that clusters carry contamination. Add 10 percent
contamination from an uncoupled neighbour to the task unit here and recompute the
z-score. How much contamination does it take to lose a real coupling, and what
does that imply about reporting coherence for units above a quality threshold?
''')

m.emit()
verify("04_spikes", "04_psth_and_spike_field_coherence")
print("  SPK 4 OK")
