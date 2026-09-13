import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("07_guardrails", "02_adaptive_dbs_control_loops")

m.md(r'''# Module G2: Adaptive DBS Control Loops {{VARIANT}}

**Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails**

{{INSTRUCTIONS}}

Adaptive DBS measures a biomarker, usually beta power, and adjusts stimulation
in response. Every module in Signal Processing measured a delay somewhere in that chain,
and every one of those delays now sits inside a feedback loop, where delay stops
being an inconvenience and becomes a stability problem.

**What it assumes**

| From | What is used |
|---|---|
| SIG 2 | That a causal filter is late, and how late depends on the band. |
| SIG 5 | That an envelope estimate over $N$ cycles smears events by about that long. |
| POP 3 | That an online estimator trades responsiveness against noise. |
| G1 | That the beta estimate arriving at the controller is contaminated. |

**What it underwrites**

Every closed-loop stimulation claim, and the reason `configs/erna.yaml` records
that its defaults are unreviewed.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(151)
DT_MS = 10.0                     # controller update interval
print("Environment initialized for Module G2")''')

m.md(r'''---

## 1. The latency budget

Between a physiological change and the stimulator responding sit several delays,
each of which an earlier module measured:

| Stage | Source | Typical |
|---|---|---|
| Causal bandpass to beta | SIG 2 measured 63 ms for a 13-30 Hz filter | 40 to 200 ms |
| Envelope estimation | SIG 5: about $\sigma_t$, and longer for more cycles | 30 to 100 ms |
| Smoothing or averaging | a design choice | 0 to 200 ms |
| Decision and telemetry | device | 5 to 50 ms |

They add. A loop using a 7-cycle beta estimate with a causal filter and modest
smoothing is looking at the brain as it was **a fifth of a second ago**, and it
is applying a correction computed from that.

The first thing to do with a control loop is add up its delays, because Section 2
shows that the sum, not any individual term, decides whether the loop is
stable.''')

m.task(
'''def loop_latency_ms(filter_ms: float, envelope_cycles: float, centre_hz: float,
                    smoothing_ms: float, device_ms: float) -> dict:
    """Total loop latency, broken down by stage.

    The envelope term is one standard deviation of a Morlet envelope at
    `centre_hz` with `envelope_cycles` cycles, which SIG 5 gives as
    sigma_t = n_cycles / (2 pi f0).

    Returns a dict of the stages plus "total".
    """
    # TODO: envelope_ms = 1000 * envelope_cycles / (2 * pi * centre_hz)
    # TODO: sum the four contributions and return the breakdown plus the total
    raise NotImplementedError("Implement loop_latency_ms")''',
'''def loop_latency_ms(filter_ms: float, envelope_cycles: float, centre_hz: float,
                    smoothing_ms: float, device_ms: float) -> dict:
    """Total loop latency, broken down by stage.

    The envelope term is one standard deviation of a Morlet envelope at
    `centre_hz` with `envelope_cycles` cycles, which SIG 5 gives as
    sigma_t = n_cycles / (2 pi f0).

    Returns a dict of the stages plus "total".
    """
    envelope_ms = 1000.0 * envelope_cycles / (2.0 * np.pi * centre_hz)
    stages = {"filter": float(filter_ms), "envelope": float(envelope_ms),
              "smoothing": float(smoothing_ms), "device": float(device_ms)}
    stages["total"] = float(sum(stages.values()))
    return stages''')

m.code('''# --- TEST CELL FOR STEP 1 ---
budget = loop_latency_ms(filter_ms=63.0, envelope_cycles=7.0, centre_hz=20.0,
                         smoothing_ms=100.0, device_ms=20.0)
print(f"{'stage':>12} {'ms':>8}")
for k, v in budget.items():
    print(f"{k:>12} {v:>8.1f}")

# The filter term is SIG 2's measured value, not a guess.
assert np.isclose(budget["filter"], 63.0), "SIG 2 measured 63 ms for a causal 13-30 Hz filter"
# The envelope term is SIG 5's sigma_t.
assert np.isclose(budget["envelope"], 1000 * 7.0 / (2 * np.pi * 20.0), rtol=1e-9)
assert budget["total"] > 200.0, "an ordinary configuration exceeds a fifth of a second"

print(f"\\ntotal loop latency: {budget['total']:.0f} ms")
print(f"beta cycles elapsed while the loop decides: {budget['total'] / 50.0:.1f}")

# A faster configuration, and what it gives up (SIG 2 and SIG 5 both priced this).
fast = loop_latency_ms(filter_ms=20.0, envelope_cycles=3.0, centre_hz=20.0,
                       smoothing_ms=20.0, device_ms=20.0)
print(f"\\naggressive configuration total: {fast['total']:.0f} ms")
assert fast["total"] < 0.5 * budget["total"], "the delays can be cut substantially"
print("SIG 2 measured what the shorter filter costs in selectivity, and SIG 5 what the")
print("3-cycle envelope costs in frequency precision. Neither is free.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Delay in a feedback loop is not an inconvenience

Outside a loop, delay makes an estimate late. Inside one, it makes the correction
apply to a state that has already changed, and if the loop keeps correcting, the
correction can arrive in phase with the thing it is correcting and amplify it.

The simplest model that shows this is a proportional controller acting on a
first-order plant with a delay $\tau$:

$$b_{t} = b_{t-1} + \frac{\Delta t}{T_{\text{plant}}}
\left(b_{\text{drive}} - b_{t-1} - g\, u_{t-\tau}\right)$$

with $u = \max(0, b - \text{target})$. The behaviour is decided by the product of
gain and delay, not by either alone, which means a gain that is safe on the bench
becomes unstable when someone lengthens a smoothing window.''')

m.task(
'''def simulate_loop(gain: float, delay_ms: float, n_steps: int = 3000,
                  dt_ms: float = DT_MS, plant_tau_ms: float = 120.0,
                  drive: float = 1.0, target: float = 0.4,
                  noise: float = 0.0, gen=None) -> np.ndarray:
    """Simulate a proportional adaptive-stimulation loop. Returns the biomarker."""
    # TODO: keep a history of the control signal so it can be read `delay_ms` ago
    # TODO: at each step, u = max(0, b_delayed - target) * gain
    # TODO: db = (dt/plant_tau) * (drive - b - u), plus optional noise
    # TODO: clip the biomarker at zero and record it
    raise NotImplementedError("Implement simulate_loop")''',
'''def simulate_loop(gain: float, delay_ms: float, n_steps: int = 3000,
                  dt_ms: float = DT_MS, plant_tau_ms: float = 120.0,
                  drive: float = 1.0, target: float = 0.4,
                  noise: float = 0.0, gen=None) -> np.ndarray:
    """Simulate a proportional adaptive-stimulation loop. Returns the biomarker."""
    gen = np.random.default_rng(0) if gen is None else gen
    lag = max(1, int(round(delay_ms / dt_ms)))
    b = drive
    hist = [b] * (lag + 1)
    out = np.zeros(n_steps)
    for i in range(n_steps):
        b_seen = hist[-lag]
        u = gain * max(0.0, b_seen - target)
        db = (dt_ms / plant_tau_ms) * (drive - b - u)
        b = max(0.0, b + db + (noise * gen.standard_normal() if noise else 0.0))
        hist.append(b)
        out[i] = b
    return out''')

m.code('''# --- TEST CELL FOR STEP 2 ---
def oscillation_index(trace, skip=1000):
    """Standard deviation of the settled portion, relative to its mean."""
    tail = trace[skip:]
    return float(np.std(tail) / max(np.mean(tail), 1e-9))

print(f"{'gain':>6} {'delay (ms)':>12} {'g x delay':>11} {'final level':>13} {'oscillation':>13}")
osc = {}
for gain, delay in ((1.0, 20.0), (1.0, 250.0), (3.0, 100.0), (3.0, 250.0), (6.0, 250.0)):
    tr = simulate_loop(gain, delay)
    osc[(gain, delay)] = oscillation_index(tr)
    print(f"{gain:>6.1f} {delay:>12.0f} {gain*delay:>11.0f} {np.mean(tr[1000:]):>13.3f} "
          f"{osc[(gain, delay)]:>13.4f}")

# A short delay is stable at every gain tried.
assert osc[(1.0, 20.0)] < 0.01, "a fast loop settles"
# Raising gain OR delay destabilises, and their product is what matters.
assert osc[(3.0, 250.0)] > 10 * osc[(1.0, 20.0)], "gain x delay drives the instability"
assert osc[(6.0, 250.0)] > osc[(3.0, 250.0)], "and more gain at the same delay is worse"
assert osc[(1.0, 250.0)] < osc[(3.0, 250.0)], "as is more delay at the same gain"

# The clinically relevant statement: find the gain at which a given delay becomes
# unstable, and show that it falls as delay rises.
print(f"\\n{'delay (ms)':>12} {'largest stable gain':>21}")
limits = {}
for delay in (50.0, 150.0, 250.0, 400.0):
    stable = [g for g in np.arange(0.5, 12.0, 0.5)
              if oscillation_index(simulate_loop(g, delay)) < 0.05]
    limits[delay] = max(stable) if stable else 0.0
    print(f"{delay:>12.0f} {limits[delay]:>21.1f}")

assert limits[50.0] > limits[400.0], \\
    "the usable gain falls as the loop gets slower"
print("\\nThe stability limit is a property of the whole loop. Section 1's budget is")
print("therefore not bookkeeping: lengthening a smoothing window by 100 ms lowers")
print("the gain the device may safely use, and nothing in the device knows that.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. What the contaminated biomarker does

G1 established that the beta estimate reaching the controller is not clean. Two
of its findings enter the loop directly.

The stimulation artifact's harmonics fold into beta at implanted sensing rates,
so part of the measured beta **is the stimulation**. That closes a second loop the
designer did not intend: more stimulation produces more apparent beta, which
calls for more stimulation.

And the blanking guard band raises broadband power, so the contamination is not
constant. It changes when stimulation amplitude changes.

The consequence is a positive feedback path in parallel with the intended
negative one, and it is measurable.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def simulate_contaminated(gain, delay_ms, contamination, n_steps=3000,
                          dt_ms=DT_MS, plant_tau_ms=120.0, drive=1.0, target=0.4):
    """As before, but the MEASURED biomarker includes a fraction of the stimulation.

    `contamination` is how much apparent beta each unit of stimulation adds,
    which is G1's folded artifact entering the very band being controlled.
    """
    lag = max(1, int(round(delay_ms / dt_ms)))
    b = drive
    u = 0.0
    hist_meas = [b] * (lag + 1)
    out = np.zeros(n_steps)
    for i in range(n_steps):
        measured_then = hist_meas[-lag]
        u = gain * max(0.0, measured_then - target)
        db = (dt_ms / plant_tau_ms) * (drive - b - u)
        b = max(0.0, b + db)
        hist_meas.append(b + contamination * u)          # what the device SEES
        out[i] = b
    return out

def device_view(gain, delay_ms, contamination, n_steps=4000):
    """What the DEVICE logs: the contaminated biomarker it is controlling on."""
    lag = max(1, int(round(delay_ms / DT_MS)))
    b, hist, seen = 1.0, [1.0] * (lag + 1), []
    for _ in range(n_steps):
        u = gain * max(0.0, hist[-lag] - 0.4)
        b = max(0.0, b + (DT_MS / 120.0) * (1.0 - b - u))
        hist.append(b + contamination * u)
        seen.append(hist[-1])
    return float(np.mean(seen[2000:]))

GAIN, DELAY = 1.0, 100.0          # a stable configuration, from Section 2's table
print(f"gain {GAIN}, delay {DELAY:.0f} ms, a loop Section 2 showed is stable\\n")
print(f"{'contamination':>15} {'TRUE beta':>11} {'beta the DEVICE logs':>22} {'oscillation':>13}")
truth, logged = {}, {}
for c in (0.0, 0.2, 0.4, 0.6):
    tr = simulate_contaminated(GAIN, DELAY, c, n_steps=4000)
    truth[c] = float(np.mean(tr[2000:]))
    logged[c] = device_view(GAIN, DELAY, c)
    print(f"{c:>15.2f} {truth[c]:>11.3f} {logged[c]:>22.3f} "
          f"{oscillation_index(tr, skip=2000):>13.4f}")

assert oscillation_index(simulate_contaminated(GAIN, DELAY, 0.6, n_steps=4000),
                         skip=2000) < 0.01, "this configuration stays stable throughout"

# The finding: the two move in OPPOSITE directions.
assert truth[0.6] < truth[0.0], "contamination makes the loop over-stimulate"
assert logged[0.6] > logged[0.0], "while the number the device logs goes UP"
print(f"\\nAs contamination rises from 0 to 0.6, true beta falls from {truth[0.0]:.3f} to")
print(f"{truth[0.6]:.3f} while the number in the device's log rises from {logged[0.0]:.3f} to")
print(f"{logged[0.6]:.3f}. They move in OPPOSITE directions.")
print("\\nA clinician reading the telemetry sees beta rising and concludes the patient")
print("needs more stimulation. The patient is already receiving more, and their real")
print("beta is falling because of it. Every quantity in that chain is behaving")
print("exactly as designed.")
print("\\nA closed-loop system cannot validate itself from its own control signal. An")
print("open-loop recording with stimulation held fixed is the only way to see the")
print("difference, which is why it is not optional.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. Loop latency is a sum of delays that earlier modules measured individually.
   An ordinary configuration, SIG 2's 63 ms causal beta filter plus SIG 5's 7-cycle
   envelope plus modest smoothing, exceeds **200 ms**, which is four beta cycles.
2. Inside a feedback loop, delay and gain multiply. The largest stable gain falls
   as the loop slows, so lengthening a smoothing window silently reduces the gain
   the device may safely use, and nothing in the device knows that happened.
3. G1's folded artifact enters the controlled band, so part of the measured beta
   **is the stimulation**. As contamination rises, true beta **falls** while the
   number the device logs **rises**. They move in opposite directions, so a
   clinician reading the telemetry sees beta increasing and concludes more
   stimulation is needed, while the patient's real beta is falling because of the
   stimulation already delivered.
4. A closed-loop system cannot validate itself from its own control signal. An
   open-loop recording with stimulation held fixed is the only way to see the
   difference, which is why it is not optional.

### Exercises

**Exercise 1.** Section 2's controller is proportional. Add an integral term and
find whether it improves or worsens the stability limit at 250 ms of delay.
Explain the result in terms of what integration does to phase.

**Exercise 2.** Real adaptive DBS uses hysteresis: separate thresholds for
turning stimulation up and down. Add it, and measure how much it buys in
stability and what it costs in responsiveness.

**Exercise 3.** Using Section 3, derive the contamination fraction at which the
loop becomes unstable rather than merely biased, for a gain of 3 and a delay of
150 ms. Then use G1's folding table to find the sensing rate that would produce
it.

---

**Next: GRL 3, muscle contamination.** Two guardrails remain whose thresholds no
module has derived, and GRL 3 and GRL 4 are those two. GRL 5 then collects them all, and states for each which module supplies the
number it thresholds on.
''')

m.emit()
verify("07_guardrails", "02_adaptive_dbs_control_loops")
print("  GRL 2 OK")
