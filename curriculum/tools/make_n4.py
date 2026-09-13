import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("07_guardrails", "04_nonstationarity_and_drift")

m.md(r'''# Lesson GRL 4: Non-Stationarity Larger Than the Effect {{VARIANT}}

**Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails**

{{INSTRUCTIONS}}

The second guardrail GRL 5 found unbacked. **G9** fires when a baseline excursion
exceeds the effect being claimed, at a configured
`excursion_to_effect_ratio` of 1.0, and nothing in this curriculum had checked
that number.

The physical situation is ordinary rather than exotic. An intraoperative
recording drifts: the electrode settles, tissue responds to the insertion,
anaesthetic depth changes, the patient's arousal changes over an hour. None of
that is the effect anybody is studying, and all of it moves the numbers being
compared.

**What it assumes**

| From | What is used |
|---|---|
| SIG 4 | Welch, and that a spectral estimate has variance of its own. |
| POP 1 | That smoothing destroys independent samples, so a drift estimate has fewer than it looks. |
| CON 4 | That band power moves when the aperiodic component moves, with no oscillation involved. |

**What it underwrites**

Guardrail **G9**, its threshold, and the experimental design that makes it moot.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, welch

rng = np.random.default_rng(29)
FS = 1000.0
BETA = (13.0, 30.0)

# From configs/guardrails.yaml, G9_nonstationarity_exceeds_effect. Restated so
# the notebook runs standalone; the test suite asserts it still matches.
EXCURSION_TO_EFFECT_RATIO = 1.0

def band_power(x, band=BETA, fs=FS):
    f, p = welch(x, fs, nperseg=1024)
    sel = (f >= band[0]) & (f < band[1])
    return float(np.mean(p[sel]))

print("Environment initialized for Lesson GRL 4")''')

m.md(r'''---

## 1. An excursion is a range, not a variance

"The baseline drifts" needs a number before it can be compared to anything. The
useful one is the **excursion**: how far the baseline's own level wanders over
the recording, measured on the same quantity and in the same units as the effect.

Note what that is not. It is not the sample-to-sample variance, which SIG 4 already
showed is large and which averaging reduces. Drift is slow, so averaging does not
touch it: a longer window gives a better estimate of a baseline that has moved,
not a better estimate of where it is now.

That distinction is the whole guardrail. Variance shrinks with data and drift
does not, so a study can have arbitrarily tight error bars around a number that
is wrong.''')

m.task(
'''def drifting_beta(n_epochs: int, epoch_s: float, drift_amplitude: float,
                  effect: float = 0.0, effect_from: int | None = None,
                  seed: int = 0, fs: float = FS) -> tuple:
    """Beta power per epoch, on a slowly drifting baseline.

    The baseline follows a slow sinusoid of peak-to-peak `drift_amplitude`,
    relative to a level of 1.0. From epoch `effect_from` onward, `effect` is
    added. Returns (per_epoch_power, true_baseline).
    """
    # TODO: build a slow drift over n_epochs: 1 + (drift_amplitude/2)*sin over one cycle
    # TODO: add `effect` to epochs from effect_from onward, if given
    # TODO: add per-epoch measurement noise of about 3 percent
    # TODO: return the noisy series and the drift WITHOUT the effect
    raise NotImplementedError("Implement drifting_beta")


def excursion(series: np.ndarray) -> float:
    """Peak-to-peak wander of the slow component of a series.

    Smooth away the epoch-to-epoch noise first, so this measures drift rather
    than variance, then take the range of what is left.
    """
    # TODO: smooth with a moving average about a fifth of the series long
    # TODO: return max minus min of the smoothed series
    raise NotImplementedError("Implement excursion")''',
'''def drifting_beta(n_epochs: int, epoch_s: float, drift_amplitude: float,
                  effect: float = 0.0, effect_from: int | None = None,
                  seed: int = 0, fs: float = FS) -> tuple:
    """Beta power per epoch, on a slowly drifting baseline.

    The baseline follows a slow sinusoid of peak-to-peak `drift_amplitude`,
    relative to a level of 1.0. From epoch `effect_from` onward, `effect` is
    added. Returns (per_epoch_power, true_baseline).
    """
    gen = np.random.default_rng(seed)
    k = np.arange(n_epochs)
    baseline = 1.0 + (drift_amplitude / 2.0) * np.sin(2 * np.pi * k / n_epochs)
    series = baseline.copy()
    if effect_from is not None:
        series[effect_from:] += effect
    series = series + 0.03 * gen.standard_normal(n_epochs)
    return series, baseline


def excursion(series: np.ndarray) -> float:
    """Peak-to-peak wander of the slow component of a series.

    Smooth away the epoch-to-epoch noise first, so this measures drift rather
    than variance, then take the range of what is left.
    """
    win = max(3, len(series) // 5)
    kernel = np.ones(win) / win
    smooth = np.convolve(series, kernel, mode='valid')
    return float(np.max(smooth) - np.min(smooth))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
N_EPOCHS, EPOCH_S = 120, 2.0

# (a) The excursion must recover the drift that is actually there, measured against
# the true baseline the generator returns, and must not be fooled by the noise.
print(f"{'planted':>9} {'true excursion':>16} {'measured':>10}")
for planted in (0.0, 0.2, 0.5):
    series, truth = drifting_beta(N_EPOCHS, EPOCH_S, planted, seed=1)
    measured = excursion(series)
    true_exc = float(np.max(truth) - np.min(truth))
    print(f"{planted:>9.1f} {true_exc:>16.3f} {measured:>10.3f}")
    assert abs(measured - true_exc) < 0.12, f"excursion must recover {true_exc:.3f}"

# The true baseline is the drift alone. An effect must not appear in it, or every
# comparison below would be checking the analysis against itself.
_, no_effect = drifting_beta(N_EPOCHS, EPOCH_S, 0.0, effect=0.5,
                             effect_from=N_EPOCHS // 2, seed=9)
assert float(np.max(no_effect) - np.min(no_effect)) < 1e-9, \\
    "the returned baseline must contain the drift and nothing else"

# (b) The distinction that matters: variance falls with more epochs, drift does not.
print(f"\\n{'epochs':>8} {'sd of epochs':>14} {'excursion':>11}")
for n in (30, 120, 480):
    s, _ = drifting_beta(n, EPOCH_S, 0.4, seed=2)
    # Standard error of the mean is what a longer recording buys you.
    print(f"{n:>8} {np.std(s)/np.sqrt(n):>14.4f} {excursion(s):>11.3f}")

sem_short = np.std(drifting_beta(30, EPOCH_S, 0.4, seed=2)[0]) / np.sqrt(30)
sem_long = np.std(drifting_beta(480, EPOCH_S, 0.4, seed=2)[0]) / np.sqrt(480)
exc_short = excursion(drifting_beta(30, EPOCH_S, 0.4, seed=2)[0])
exc_long = excursion(drifting_beta(480, EPOCH_S, 0.4, seed=2)[0])
print(f"\\nsixteen times the data shrank the error bar by {sem_short/sem_long:.1f}x "
      f"and the excursion by {exc_short/exc_long:.2f}x")
# Sixteen times the data divides the error bar by sqrt(16) = 4, not by 2. Assert the
# factor theory predicts, so the number cannot drift away from the claim beside it.
assert 3.5 < sem_short / sem_long < 4.5, "the error bar falls as 1/sqrt(n), so 16x data quarters it"
assert exc_long > 0.7 * exc_short, "the drift does not shrink at all"
print("\\nSixteen times the data quartered the error bar, exactly the 1/sqrt(n) the")
print("textbook promises, and left the drift where it was. That is why an excursion")
print("has to be reported next to an effect, and why a tight confidence interval is")
print("not evidence that a comparison is sound.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Where you put the baseline decides the answer

A blocked design records one condition then the other. If the baseline drifts
between the blocks, the difference between them contains the drift, and there is
no way to separate the two from the data alone.

The symptom is that the measured effect depends on **which** stretch of the
recording is called baseline. A real effect does not care.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
TRUE_EFFECT = 0.15
WINDOWS = (("first 20 epochs", slice(0, 20)),
           ("epochs 20-40", slice(20, 40)),
           ("epochs 40-60", slice(40, 60)),
           ("all pre-effect epochs", slice(0, N_EPOCHS // 2)))

def measure_all_windows(drift_amp, seed):
    """Estimate the same effect once per choice of baseline window."""
    ser, _ = drifting_beta(N_EPOCHS, EPOCH_S, drift_amp, effect=TRUE_EFFECT,
                           effect_from=N_EPOCHS // 2, seed=seed)
    return [float(np.mean(ser[N_EPOCHS // 2:]) - np.mean(ser[sl])) for _, sl in WINDOWS]

print(f"true effect: {TRUE_EFFECT:+.3f}, planted from epoch {N_EPOCHS//2}, excursion 0.50\\n")
print(f"{'baseline window':>22} {'measured effect':>17} {'error':>9}")
for (name, _), est in zip(WINDOWS, measure_all_windows(0.5, seed=3)):
    print(f"{name:>22} {est:>+16.3f} {est - TRUE_EFFECT:>+8.3f}")

# One recording proves nothing. Repeat over many and report three quantities:
# how far the estimates land from the truth, how far they spread from each
# other, and how often they get the sign of the effect wrong.
def summarise(drift_amp, n_seeds=200):
    err, spread, wrong_sign = [], [], []
    for s in range(n_seeds):
        est = measure_all_windows(drift_amp, seed=s)
        err.append(np.mean([abs(e - TRUE_EFFECT) for e in est]))
        spread.append(max(est) - min(est))
        wrong_sign.append(np.mean([e < 0 for e in est]))
    return float(np.mean(err)), float(np.mean(spread)), float(np.mean(wrong_sign))

print(f"\\n{'excursion':>10} {'mean |error|':>14} {'spread':>9} {'wrong sign':>12}")
stats = {}
for drift in (0.0, 0.5):
    stats[drift] = summarise(drift)
    print(f"{drift:>10.2f} {stats[drift][0]:>14.3f} {stats[drift][1]:>9.3f} {stats[drift][2]:>11.0%}")

drift_err, drift_spread, drift_sign = stats[0.5]
flat_err, flat_spread, flat_sign = stats[0.0]

assert drift_err > 2 * TRUE_EFFECT, "the error must exceed the effect being measured"
assert drift_sign > 0.99, "and the drift must flip the sign of the effect essentially always"
assert drift_spread > 0.5 * TRUE_EFFECT, \\
    "the baseline window alone must move the answer by a good fraction of the effect"

assert flat_err < 0.1 * TRUE_EFFECT, "without drift the same analysis is accurate"
assert flat_sign < 0.01, "gets the sign right"
assert flat_spread < 0.2 * drift_spread, "and barely depends on the baseline window"

print("\\nWith an excursion 3.3 times the effect, the average estimate was wrong by more")
print("than twice the effect, and every baseline window reported a decrease where the")
print("truth was an increase. The same code, same effect, no drift: accurate to a few")
print("percent, correct sign every time.")
print("\\nNote which of those three numbers a reader could ever see. The spread across")
print("baseline windows is visible, because it is the analyst's own choice and can be")
print("recomputed. The error and the flipped sign cannot be, because the truth is not")
print("available. The spread was smaller than the error, so it understates the damage,")
print("and it is still the only warning the data offers on its own.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Where does the estimate actually break?

G9 compares the excursion to the effect and fires at a ratio of 1.0. That number
deserves testing rather than acceptance: does the answer stop being trustworthy
at a ratio of 1, or somewhere else?

Below, the effect is held fixed while the drift is swept. At each level the
comparison is repeated many times with a randomly chosen baseline window, and
what is counted is how often the estimate lands within half the true effect.
"Within half" is an arbitrary standard, but it is stated, and the shape of the
curve does not depend on where it is set.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
TRIALS = 400

def reliability(drift_amp, true_effect=TRUE_EFFECT, tol=0.5):
    """Fraction of random baseline windows whose estimate is within tol of the truth."""
    hits = 0
    for s in range(TRIALS):
        gen = np.random.default_rng(1000 + s)
        ser, _ = drifting_beta(N_EPOCHS, EPOCH_S, drift_amp, effect=true_effect,
                               effect_from=N_EPOCHS // 2, seed=1000 + s)
        start = int(gen.integers(0, N_EPOCHS // 2 - 20))
        est = float(np.mean(ser[N_EPOCHS // 2:]) - np.mean(ser[start:start + 20]))
        if abs(est - true_effect) < tol * true_effect:
            hits += 1
    return hits / TRIALS

print(f"true effect {TRUE_EFFECT:.2f}, baseline window chosen at random each time\\n")
print(f"{'excursion':>10} {'ratio':>7} {'usable estimate':>17} {'G9':>8}")
rel = {}
for drift in (0.0, 0.05, 0.075, 0.09, 0.1, 0.11, 0.12, 0.135, 0.15, 0.3):
    ratio = drift / TRUE_EFFECT
    rel[round(ratio, 3)] = reliability(drift)
    fires = "fires" if ratio >= EXCURSION_TO_EFFECT_RATIO else "quiet"
    print(f"{drift:>10.3f} {ratio:>7.2f} {rel[round(ratio,3)]:>16.0%} {fires:>8}")

assert rel[0.0] > 0.95, "with no drift the estimate is reliable wherever the baseline sits"
assert rel[2.0] < 0.05, "with drift twice the effect it essentially never is"

# Locate the half-reliability point: the ratio at which a coin flip decides
# whether the analysis is usable.
ratios = sorted(rel)
half = next(r for r in ratios if rel[r] < 0.5)
print(f"\\nreliability at ratio 0.50: {rel[0.5]:.0%}")
print(f"reliability at ratio 1.00: {rel[1.0]:.0%}   <- the configured threshold")
print(f"first ratio below 50 percent: {half:.2f}")

assert rel[0.5] > 0.9, "at half the configured ratio the estimate is still fine"
assert rel[1.0] < 0.1, "at the configured ratio it is already gone"
assert 0.5 < half < 1.0, "so the transition happens BELOW the configured threshold"

print(f"\\nThis is not what the threshold implies. The estimate is still good at a ratio")
print(f"of 0.5 and already ruined at 1.0; the collapse happens around {half:.2f}, below the")
print("line G9 draws. By the time the rule fires, the analysis it is warning about has")
print("been unusable for a while.")
print("\\nThat does not make the guardrail useless, and it does not make 1.0 the wrong")
print("number to ship. The curve above is for one drift shape, one effect size and one")
print("definition of usable; a threshold set at the measured transition for this")
print("simulation would fire constantly on recordings shaped differently. What the")
print("measurement does establish is the direction of the error: G9 is permissive, so a")
print("quiet G9 is not evidence that a comparison is clean, and the ratio itself should")
print("be reported next to the effect rather than reduced to fired-or-not.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. The design that makes the guardrail moot

Everything above is a property of a **blocked** design: all of one condition, then
all of the other. Drift is slow, so it is nearly constant within a block and
different between blocks, which is exactly the structure that turns it into an
apparent effect.

Interleave the conditions and the drift becomes common to both. Whatever the
baseline is doing at minute forty, it is doing to both conditions, and the
contrast subtracts it. This is the same argument as guardrail G11 and as LIN 6's
generalised eigendecomposition: a contrast removes what is common. Here what is
common is the passage of time.

Two ways to interleave are compared, because they do not cost the same thing.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
def three_designs(drift_amp, seed, true_effect=TRUE_EFFECT, n_epochs=N_EPOCHS):
    """The same effect and the same drift, assigned to conditions three ways."""
    gen = np.random.default_rng(seed)
    k = np.arange(n_epochs)
    drift = 1.0 + (drift_amp / 2.0) * np.sin(2 * np.pi * k / n_epochs)
    noise = 0.03 * gen.standard_normal(n_epochs)

    blocked = np.zeros(n_epochs, dtype=bool)
    blocked[n_epochs // 2:] = True            # all control, then all task
    alternating = np.zeros(n_epochs, dtype=bool)
    alternating[::2] = True                   # strict ABAB
    randomized = np.zeros(n_epochs, dtype=bool)
    randomized[gen.permutation(n_epochs)[:n_epochs // 2]] = True   # random order

    out = {}
    for name, is_task in (("blocked", blocked), ("alternating", alternating),
                          ("randomized", randomized)):
        signal = drift + noise + true_effect * is_task
        out[name] = float(np.mean(signal[is_task]) - np.mean(signal[~is_task]))
    return out

N_REP = 300
print(f"true effect {TRUE_EFFECT:+.3f} in every cell; bias and spread over {N_REP} recordings\\n")
print(f"{'excursion':>10} " + " ".join(f"{n:>22}" for n in ("blocked", "alternating", "randomized")))
print(f"{'':>10} " + " ".join(f"{'bias':>11}{'sd':>11}" for _ in range(3)))
res = {}
for drift in (0.0, 0.15, 0.3, 0.6):
    reps = [three_designs(drift, s) for s in range(N_REP)]
    res[drift] = {k: (float(np.mean([r[k] for r in reps])) - TRUE_EFFECT,
                      float(np.std([r[k] for r in reps]))) for k in reps[0]}
    cells = " ".join(f"{res[drift][n][0]:>+11.4f}{res[drift][n][1]:>11.4f}"
                     for n in ("blocked", "alternating", "randomized"))
    print(f"{drift:>10.2f} {cells}")

# Blocked: the drift becomes bias, and the bias grows with the drift.
assert abs(res[0.6]["blocked"][0]) > 2 * TRUE_EFFECT, "blocked bias exceeds the effect"
assert abs(res[0.6]["blocked"][0]) > 3 * abs(res[0.15]["blocked"][0]), "and grows with drift"

# Both interleaved designs remove essentially all of that bias.
for name in ("alternating", "randomized"):
    assert abs(res[0.6][name][0]) < 0.05 * TRUE_EFFECT, f"{name} removes the bias"

# But they do not cost the same. Randomization converts the drift into variance;
# strict alternation does not, because it samples the drift symmetrically.
assert res[0.6]["randomized"][1] > 5 * res[0.6]["alternating"][1], \\
    "randomized order pays for its unbiasedness in variance"
assert res[0.6]["randomized"][1] > 5 * res[0.0]["randomized"][1], \\
    "and that variance is the drift, since it grows with the drift"
assert abs(res[0.6]["alternating"][1] - res[0.0]["alternating"][1]) < 0.002, \\
    "strict alternation's spread does not depend on the drift at all"

print("\\nBlocked turns the drift into bias: at an excursion four times the effect the")
print("answer was wrong by more than twice the effect, with a tight spread around the")
print("wrong value. Both interleaved designs removed that bias.")
print("\\nThey did not remove it at the same price. Randomized order converted the drift")
print("into variance, its spread growing about sevenfold across the sweep, so the drift")
print("still costs statistical power and shows up honestly in the error bar. Strict")
print("alternation cancelled the drift outright, because sampling every other epoch")
print("samples a slow trend symmetrically.")
print("\\nThat exact cancellation is also alternation's weakness, and it is why it is not")
print("simply the better choice: anything else in the recording that alternates or")
print("nearly alternates with the conditions is cancelled into the contrast instead,")
print("and nothing in the data will say so. Randomization gives up the free lunch to")
print("buy protection against confounds nobody thought to model.")
print("\\nG9 is a warning about an analysis. The decision that makes it moot is a design")
print("decision, taken before the recording starts.")
print("\\nStep 4 passed.")''')
m.md(r'''---

## 5. What you established

1. An **excursion** is the slow wander of a baseline, and it is a different
   quantity from variance. Sixteen times the data quartered the error bar, the
   1/sqrt(n) the textbook promises, and left the excursion where it was. A tight
   confidence interval is therefore not evidence that a comparison is sound.
2. On a recording drifting 3.3 times the effect, the estimate was wrong by more
   than twice the effect and **every** choice of baseline window reported a
   decrease where the truth was an increase. The same analysis without drift was
   accurate to a few percent. Only the spread across baseline choices is visible
   to a reader, and it understated the damage.
3. **G9's threshold is permissive.** The estimate was still usable at a ratio of
   0.5 and essentially never usable at 1.0, with the collapse near 0.73, below
   the line the rule draws. That is one drift shape and one definition of usable,
   so it does not mean 1.0 is the wrong number to ship, but it does fix the
   direction of the error: a quiet G9 is not evidence that a comparison is clean.
   Report the ratio, not whether it fired.
4. **Interleaving removes the bias; it does not remove the drift.** Blocked was
   wrong by twice the effect with a tight spread around the wrong value.
   Randomized order was unbiased but converted the drift into variance, its
   spread growing sevenfold across the sweep. Strict alternation cancelled the
   drift exactly, and that exactness is its weakness, because it cancels any
   other alternating confound into the contrast just as silently.

The general form: drift is a confound that averaging cannot fix, a guardrail can
only flag late, and a design can remove entirely. The order of those three is the
lesson.

### Exercises

**Exercise 1.** Section 1 modelled drift as one slow sinusoid, which has a
characteristic timescale. Real drift is closer to a random walk, which does not.
Repeat Section 3 with a random walk and say whether the excursion is still the
right summary, and whether the transition sits in the same place.

**Exercise 2.** CON 4 established that an aperiodic exponent change moves band power
with no oscillation involved, which is one physical source of the drift modelled
here. Fit the aperiodic component per epoch on a drifting recording and show
whether the drift lives in the offset, the exponent, or a peak, then say which of
those three a bipolar montage would reduce.

**Exercise 3.** Interleaving is not always available. A drug is not
interleavable, and neither is a stimulation state that takes minutes to settle.
For such a comparison, propose what to report alongside the effect, and state
what claim the result can and cannot support.

---

**Next: GRL 5, the thirteen guardrails.** With this module and GRL 3, every arithmetic
guardrail in the app now has a module that measured the number it thresholds on.
''')

m.emit()
verify("07_guardrails", "04_nonstationarity_and_drift")
print("  GRL 4 OK")