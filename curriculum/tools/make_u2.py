import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("04_spikes", "02_robust_spike_detection")

m.md(r'''# Lesson SPK 2: Robust Spike Detection {{VARIANT}}

**Analysis · Spike Trains and Single-Unit Activity**

{{INSTRUCTIONS}}

SPK 1 separated the spike band. This module decides what counts as a spike in it,
and the decision turns on estimating a noise level from data that contains the
thing you are looking for.

PRE 1 already showed that a standard deviation goes blind to an artifact occupying
five percent of a record. Here the contaminant is spikes, the situation is the
normal one rather than a pathology, and the same estimator fails the same way.

**What it assumes**

| From | What is used |
|---|---|
| SPK 1 | The band split, and the spike waveform's shape and duration. |
| PRE 1 | That the median absolute deviation is robust where a standard deviation is not. |
| LIN 1 | Template matching by projection, and that cosine similarity is amplitude-blind. |

**What it underwrites**

Guardrail **G4**, a threshold set across conditions when testing structure.
Section 3 shows what a shared threshold does when firing rates differ.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(31)
FS = 30000.0
REFRACTORY_MS = 1.0
print("Environment initialized for Lesson SPK 2")''')

m.md(r'''---

## 1. The noise level cannot be a standard deviation

Detection thresholds are set as a multiple of the background noise level, so
everything depends on estimating that level. The obvious estimator, the standard
deviation of the filtered trace, includes the spikes, and spikes are precisely
the large excursions that inflate it.

The standard robust alternative, from Quiroga, Nadasdy and Ben-Shaul, is

$$\hat{\sigma} = \frac{\text{median}(|x|)}{0.6745}$$

where $0.6745$ is the value that makes this agree with the standard deviation for
Gaussian data, because the median absolute value of a standard normal is
$\Phi^{-1}(0.75) \approx 0.6745$.

The constant is doing real work, and it is checkable rather than magic.''')

m.task(
'''def robust_sigma(x: np.ndarray) -> float:
    """Noise level estimate that spikes cannot inflate.

    sigma_hat = median(|x|) / 0.6745

    Production equivalent: this is the standard estimator in spike sorting;
    `scipy.stats.median_abs_deviation(x, scale='normal')` computes the closely
    related median absolute deviation about the median.
    """
    # TODO: median of the absolute values, divided by 0.6745
    raise NotImplementedError("Implement robust_sigma")''',
'''def robust_sigma(x: np.ndarray) -> float:
    """Noise level estimate that spikes cannot inflate.

    sigma_hat = median(|x|) / 0.6745

    Production equivalent: this is the standard estimator in spike sorting;
    `scipy.stats.median_abs_deviation(x, scale='normal')` computes the closely
    related median absolute deviation about the median.
    """
    return float(np.median(np.abs(x)) / 0.6745)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
# (a) The constant is not arbitrary. Derive it and check.
from scipy.stats import norm
print(f"Phi^-1(0.75) = {norm.ppf(0.75):.6f}, the constant used is 0.6745")
assert abs(norm.ppf(0.75) - 0.6745) < 1e-3, "the constant is the 75th percentile of a standard normal"

# (b) On pure Gaussian noise both estimators agree.
pure = rng.standard_normal(200000) * 12.0
print(f"\\npure noise, true sd 12.0: std {np.std(pure):.3f}, robust {robust_sigma(pure):.3f}")
assert abs(robust_sigma(pure) - 12.0) < 0.2, "must be unbiased on Gaussian data"
assert abs(np.std(pure) - 12.0) < 0.2, "so must the standard deviation, when nothing contaminates it"

# (c) Add spikes, which is the normal state of a spike-band recording.
def spike_waveform(fs=FS, width_ms=1.0):
    n = int(width_ms * 1e-3 * fs)
    t = np.linspace(-1, 1, n)
    w = -np.exp(-t ** 2 / 0.08) + 0.35 * np.exp(-(t - 0.45) ** 2 / 0.12)
    return (w - w.mean()) / np.max(np.abs(w - w.mean()))

def make_trace(rate_hz, seconds=20.0, noise_uv=12.0, amp_uv=100.0, seed=0):
    gen = np.random.default_rng(seed)
    n = int(seconds * FS)
    refr = int(REFRACTORY_MS * 1e-3 * FS)
    times, last = [], -refr
    for i in range(n):
        if i - last > refr and gen.random() < rate_hz / FS:
            times.append(i); last = i
    trace = gen.standard_normal(n) * noise_uv
    wf = spike_waveform() * amp_uv
    for t0 in times:
        if t0 + len(wf) < n:
            trace[t0:t0 + len(wf)] += wf
    return trace, np.array(times)

print(f"\\n{'rate':>8} {'duty cycle':>11} {'std':>9} {'robust':>9} {'std infl.':>10} {'rob infl.':>11}")
infl = {}
for rate in (10.0, 100.0, 400.0):
    tr, _ = make_trace(rate, seed=int(rate))
    duty = rate * 1e-3          # a 1 ms spike at `rate` Hz occupies rate*1ms of the record
    infl[rate] = (np.std(tr) / 12.0, robust_sigma(tr) / 12.0)
    print(f"{rate:>5.0f} Hz {duty:>10.0%} {np.std(tr):>9.3f} {robust_sigma(tr):>9.3f} "
          f"{infl[rate][0]:>9.2f}x {infl[rate][1]:>10.2f}x")

for rate in (10.0, 100.0, 400.0):
    assert infl[rate][1] < infl[rate][0], f"the robust estimate is less inflated at {rate} Hz"
assert infl[400.0][0] > 2.0, "spikes badly inflate the standard deviation at high rates"
assert infl[10.0][1] < 1.05, "and leave the robust estimate essentially untouched at low rates"

print("\\nRobustness is not immunity, and the limit is duty cycle. A 1 ms spike at")
print("400 Hz occupies 40 percent of the record, so the spikes ARE the bulk and even")
print("a median moves with them. PRE 1 found the same boundary from the other side:")
print("a standard deviation went blind at 5 percent occupancy, a median survived it.")
print("\\nStep 1 passed. The estimator that includes the spikes reports a larger noise")
print("floor, so it raises the threshold, so it finds fewer spikes. It is self-limiting.")''')

m.md(r'''---

## 2. Detection, and the two ways to miscount

With a threshold at $k\hat{\sigma}$, detection is a crossing test. Two mistakes
follow immediately and both are worth naming.

A spike lasts about a millisecond and so stays above threshold for many samples.
Counting crossings rather than events multiplies every count. PRE 1 made the same
error deliberately and caught it; here it is the default behaviour of a naive
loop.

And a real neuron cannot fire twice within its refractory period, roughly 1 ms.
Detections closer than that are either one spike counted twice or two cells being
treated as one, and either way the count is wrong. Enforcing a refractory window
during detection is not a cosmetic step.''')

m.task(
'''def detect_spikes(x: np.ndarray, k: float = 4.0, fs: float = FS,
                  refractory_ms: float = REFRACTORY_MS) -> np.ndarray:
    """Indices of detected spikes: threshold crossings, one per refractory window.

    Threshold at k * robust_sigma(x), on the NEGATIVE peak, since an
    extracellular action potential is predominantly negative-going.

    Production equivalent: the detection stage of any sorter; in
    `spikeinterface` this is `detect_peaks`.
    """
    # TODO: threshold = -k * robust_sigma(x)
    # TODO: find samples below the threshold
    # TODO: group consecutive/nearby detections and keep the most negative sample
    #       in each group, enforcing a refractory gap in samples
    raise NotImplementedError("Implement detect_spikes")''',
'''def detect_spikes(x: np.ndarray, k: float = 4.0, fs: float = FS,
                  refractory_ms: float = REFRACTORY_MS) -> np.ndarray:
    """Indices of detected spikes: threshold crossings, one per refractory window.

    Threshold at k * robust_sigma(x), on the NEGATIVE peak, since an
    extracellular action potential is predominantly negative-going.

    Production equivalent: the detection stage of any sorter; in
    `spikeinterface` this is `detect_peaks`.
    """
    thresh = -k * robust_sigma(x)
    below = np.flatnonzero(x < thresh)
    if below.size == 0:
        return np.array([], dtype=int)
    refr = int(refractory_ms * 1e-3 * fs)
    picks, group = [], [below[0]]
    for idx in below[1:]:
        if idx - group[-1] <= refr:
            group.append(idx)
        else:
            picks.append(group[int(np.argmin(x[group]))])
            group = [idx]
    picks.append(group[int(np.argmin(x[group]))])
    return np.array(picks, dtype=int)''')

m.code('''# --- TEST CELL FOR STEP 2 ---
trace, truth = make_trace(50.0, seconds=20.0, seed=11)
found = detect_spikes(trace, k=4.0)

def match(found_idx, true_idx, tol_samples=int(0.5e-3 * FS)):
    """True positives, misses and false positives, matched within tolerance."""
    tp = sum(1 for t in true_idx if np.any(np.abs(found_idx - t) <= tol_samples))
    fp = sum(1 for f in found_idx if not np.any(np.abs(true_idx - f) <= tol_samples))
    return tp, len(true_idx) - tp, fp

tp, miss, fp = match(found, truth)
print(f"planted {len(truth)} spikes, detected {len(found)}")
print(f"  true positives : {tp}")
print(f"  missed         : {miss}")
print(f"  false positives: {fp}")
assert tp / len(truth) > 0.95, "a 100 uV spike against 12 uV noise must be found"
assert fp < 0.05 * len(truth), "and 4 sigma must not fire often on noise alone"

# The crossing-versus-event error, made explicit.
naive = int(np.sum(trace < -4.0 * robust_sigma(trace)))
print(f"\\nsamples below threshold : {naive}")
print(f"events after refractory  : {len(found)}")
print(f"ratio                    : {naive/len(found):.1f}x")
assert naive > 3 * len(found), "counting samples inflates the spike count several fold"

# No detection may violate the refractory period, by construction.
gaps_ms = np.diff(found) / FS * 1000
assert gaps_ms.min() >= REFRACTORY_MS * 0.99, \\
    f"detections must respect the refractory window, min gap was {gaps_ms.min():.3f} ms"
print(f"\\nsmallest gap between detections: {gaps_ms.min():.3f} ms (refractory "
      f"{REFRACTORY_MS:.1f} ms)")

# Threshold sweep: the trade every sorter makes.
print(f"\\n{'k':>5} {'detected':>10} {'recall':>9} {'false pos':>11}")
for k in (2.0, 3.0, 4.0, 5.0, 6.0):
    f_k = detect_spikes(trace, k=k)
    tp_k, _, fp_k = match(f_k, truth)
    print(f"{k:>5.1f} {len(f_k):>10} {tp_k/len(truth):>8.1%} {fp_k:>11}")
assert len(detect_spikes(trace, k=2.0)) > len(detect_spikes(trace, k=6.0)), \\
    "a lower threshold detects more, including more of what is not there"
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Why a shared threshold is guardrail G4

Section 1 established that the threshold is proportional to an estimate of the
noise. Section 1 also established that the **robust** estimate is unaffected by
firing rate, which is exactly what makes it safe to compare across conditions.

Now consider what happens if you use the non-robust estimate instead and compare
two conditions with different firing rates. Rest has few spikes and a low
standard deviation, so a low threshold. Task has many spikes and a higher
standard deviation, so a higher threshold. The detector has become **less
sensitive in the condition with more activity**, which biases every comparison
toward finding nothing, and does so invisibly.

This is guardrail G4, which requires a threshold to be set within each condition
when comparing structure, seen from its other side: a threshold derived from the
data is a threshold that differs between conditions unless the estimator is
insensitive to what differs.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
REST_RATE, TASK_RATE = 20.0, 200.0
tr_rest, tru_rest = make_trace(REST_RATE, seconds=20.0, seed=21)
tr_task, tru_task = make_trace(TASK_RATE, seconds=20.0, seed=22)

print(f"{'estimator':>10} {'condition':>10} {'noise est':>11} {'threshold':>11} {'recall':>9}")
results = {}
for est_name, est in (("std", np.std), ("robust", robust_sigma)):
    for cond, tr, tru in (("rest", tr_rest, tru_rest), ("task", tr_task, tru_task)):
        sigma = float(est(tr))
        thresh_uv = 4.0 * sigma
        below = np.flatnonzero(tr < -thresh_uv)
        refr = int(REFRACTORY_MS * 1e-3 * FS)
        picks, group = [], ([below[0]] if below.size else [])
        for idx in below[1:]:
            if idx - group[-1] <= refr:
                group.append(idx)
            else:
                picks.append(group[int(np.argmin(tr[group]))]); group = [idx]
        if group:
            picks.append(group[int(np.argmin(tr[group]))])
        picks = np.array(picks, dtype=int)
        tp_c, _, _ = match(picks, tru)
        results[(est_name, cond)] = (sigma, thresh_uv, tp_c / len(tru))
        print(f"{est_name:>10} {cond:>10} {sigma:>11.3f} {thresh_uv:>11.2f} "
              f"{tp_c/len(tru):>8.1%}")

# The non-robust estimator raises its own threshold in the busier condition.
std_rest = results[("std", "rest")][1]
std_task = results[("std", "task")][1]
rob_rest = results[("robust", "rest")][1]
rob_task = results[("robust", "task")][1]
print(f"\\nthreshold difference, task minus rest:")
print(f"  std estimator    : {std_task - std_rest:+.2f} uV")
print(f"  robust estimator : {rob_task - rob_rest:+.2f} uV")
assert std_task > std_rest, "the non-robust threshold rises with firing rate"
assert abs(rob_task - rob_rest) < 0.4 * (std_task - std_rest), \\
    "the robust threshold barely moves, which is what makes conditions comparable"

# And the consequence: a sensitivity difference between conditions, from nothing
# but the analysis.
recall_gap_std = results[("std", "rest")][2] - results[("std", "task")][2]
recall_gap_rob = results[("robust", "rest")][2] - results[("robust", "task")][2]
print(f"\\nrecall gap between conditions (rest minus task):")
print(f"  std estimator    : {recall_gap_std:+.2%}")
print(f"  robust estimator : {recall_gap_rob:+.2%}")
# With 100 uV spikes against thresholds of 49 to 89 uV there is margin to spare,
# so the recall gap is small either way. The threshold moved; the answer did not.
# Repeat with units near the threshold, which is where most real units sit.
print(f"\\n{'spike amp':>10} {'estimator':>10} {'recall rest':>13} {'recall task':>13} {'gap':>8}")
gaps = {}
for amp in (100.0, 45.0):
    for est_name, est in (("std", np.std), ("robust", robust_sigma)):
        rec = {}
        for cond, seed, rate in (("rest", 31, REST_RATE), ("task", 32, TASK_RATE)):
            tr_a, tru_a = make_trace(rate, seconds=20.0, amp_uv=amp, seed=seed)
            th = 4.0 * float(est(tr_a))
            bel = np.flatnonzero(tr_a < -th)
            refr = int(REFRACTORY_MS * 1e-3 * FS)
            pk, grp = [], ([bel[0]] if bel.size else [])
            for idx in bel[1:]:
                if idx - grp[-1] <= refr:
                    grp.append(idx)
                else:
                    pk.append(grp[int(np.argmin(tr_a[grp]))]); grp = [idx]
            if grp:
                pk.append(grp[int(np.argmin(tr_a[grp]))])
            tp_a, _, _ = match(np.array(pk, dtype=int), tru_a)
            rec[cond] = tp_a / len(tru_a)
        gaps[(amp, est_name)] = rec["rest"] - rec["task"]
        print(f"{amp:>8.0f}uV {est_name:>10} {rec['rest']:>12.1%} {rec['task']:>12.1%} "
              f"{rec['rest'] - rec['task']:>+7.1%}")

assert abs(gaps[(45.0, "std")]) > abs(gaps[(45.0, "robust")]), \\
    "near threshold, the non-robust estimator costs recall in the busier condition"
assert abs(gaps[(45.0, "std")]) > abs(gaps[(100.0, "std")]), \\
    "and the bias grows as units approach the threshold"
print("\\nWith units well above threshold the moved threshold costs nothing. With")
print("units near it, the non-robust estimator loses spikes in the busier condition")
print("only, which is a between-condition difference manufactured by the analysis.")
print("\\nStep 3 passed. A threshold computed from a statistic that the condition")
print("changes is a different threshold per condition, which is what G4 forbids.")''')

m.md(r'''---

## 4. What you established

1. The $0.6745$ in the robust noise estimator is $\Phi^{-1}(0.75)$, verified, not
   a magic number. On Gaussian data both estimators are unbiased.
2. At 400 Hz multi-unit activity the standard deviation is inflated 2.25 times
   above the true noise level and the robust estimate 1.34 times. Robustness is
   not immunity: a 1 ms spike at 400 Hz occupies 40 percent of the record, so the
   spikes are the bulk and even a median moves. PRE 1 found the same boundary from
   the other side. The non-robust estimator raises its own threshold in response
   to the spikes it is meant to find, which is self-limiting.
3. Counting threshold crossings rather than refractory-separated events inflates
   the spike count several fold, and no detection may sit closer than the
   refractory period.
4. Comparing conditions with a non-robust threshold moves the threshold by
   $+34$ microvolts between rest and task, against $+7.5$ for the robust one.
   With units far above threshold that costs nothing; with units near it, the
   detector loses spikes in the busier condition only, manufacturing a
   between-condition difference from the analysis alone. That is guardrail G4
   seen from the estimator's side.

### Exercises

**Exercise 1.** The threshold sweep in Section 2 traded recall against false
positives. Plot the full curve for spike amplitudes of 40, 70 and 100 microvolts
against 12 microvolts of noise, and find the amplitude below which no threshold
gives both recall above 90 percent and fewer than 5 percent false positives.

**Exercise 2.** LIN 1 established that cosine similarity is amplitude-blind while a
matched filter is not. Implement both as detectors here and compare their
recall-versus-false-positive curves. Which is preferable, and does the answer
depend on whether the units have similar amplitudes?

**Exercise 3.** Real noise in the spike band is not Gaussian; it contains the
tails of many distant spikes, the multi-unit hash. Estimate the robust sigma of a
trace built from 2000 Hz of distant small spikes with no local unit at all, and
say what a 4 sigma threshold means in that setting.

---

**Next: SPK 3, sorting and quality metrics.** Detection produced a list of times.
SPK 3 asks whether those times came from one neuron, and finds that the refractory
period supplies a quantitative answer.
''')

m.emit()
verify("04_spikes", "02_robust_spike_detection")
print("  SPK 2 OK")
