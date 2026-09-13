import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("06_connectivity", "01_plv_and_the_zero_lag_trap")

m.md(r'''# Lesson CON 1: Phase-Locking Value and the Zero-Lag Volume Trap {{VARIANT}}

**Analysis · Connectivity and Spectral Coupling**

{{INSTRUCTIONS}}

Two contacts show synchronised beta. The natural conclusion is that the two
regions are communicating. This module builds the measure that supports that
conclusion and then shows that the measure is satisfied, at its maximum value,
by a situation involving no communication at all.

**What it assumes**

| From | What is used |
|---|---|
| REC 1, LIN 4 | That volume conduction puts one source on every contact, instantaneously. |
| SIG 2, SIG 6 | Bandpass filtering, and that phase is defined only within a band. |
| SPK 4 | The phase-locking value, and that it is biased by sample count. |

**What it underwrites**

Guardrail **G1**, from its connectivity side, and every claim of functional
coupling between two intracranial contacts.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, hilbert

rng = np.random.default_rng(101)
FS = 1000.0
BETA = (13.0, 30.0)
print("Environment initialized for Lesson CON 1")''')

m.md(r'''---

## 1. Phase locking between two continuous signals

SPK 4 computed a phase-locking value between spikes and a field. Between two
continuous signals it is the same quantity over the phase **difference**:

$$\text{PLV} = \left|\frac{1}{T}\sum_{t} e^{i\left(\phi_1(t) - \phi_2(t)\right)}\right|$$

It is 1 when the phase difference is constant, whatever that constant is, and 0
when the difference is uniformly distributed. Note carefully what it does not
care about: the **value** of the constant. A phase difference locked at zero and
one locked at 90 degrees both give PLV 1.

That indifference is the whole problem, and Section 2 is why.''')

m.task(
'''def band_phase(x: np.ndarray, band=BETA, fs: float = FS) -> np.ndarray:
    """Instantaneous phase within `band`. SIG 6: filter first, then Hilbert."""
    # TODO: butter + filtfilt over the band, then np.angle of scipy.signal.hilbert
    raise NotImplementedError("Implement band_phase")


def plv(phase_a: np.ndarray, phase_b: np.ndarray) -> float:
    """Phase-locking value between two phase series, in [0, 1]."""
    # TODO: magnitude of the mean of exp(i * (phase_a - phase_b))
    raise NotImplementedError("Implement plv")


def mean_phase_lag(phase_a: np.ndarray, phase_b: np.ndarray) -> float:
    """Mean phase difference in radians, in (-pi, pi]."""
    # TODO: angle of the mean of exp(i * (phase_a - phase_b))
    raise NotImplementedError("Implement mean_phase_lag")''',
'''def band_phase(x: np.ndarray, band=BETA, fs: float = FS) -> np.ndarray:
    """Instantaneous phase within `band`. SIG 6: filter first, then Hilbert."""
    b, a = butter(4, list(band), btype='band', fs=fs)
    return np.angle(hilbert(filtfilt(b, a, x)))


def plv(phase_a: np.ndarray, phase_b: np.ndarray) -> float:
    """Phase-locking value between two phase series, in [0, 1]."""
    return float(np.abs(np.mean(np.exp(1j * (phase_a - phase_b)))))


def mean_phase_lag(phase_a: np.ndarray, phase_b: np.ndarray) -> float:
    """Mean phase difference in radians, in (-pi, pi]."""
    return float(np.angle(np.mean(np.exp(1j * (phase_a - phase_b)))))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
T = 60000
t = np.arange(T) / FS

# (a) A signal against a shifted copy of itself: PLV must be 1 at any lag.
base = filtfilt(*butter(4, list(BETA), btype='band', fs=FS), rng.standard_normal(T))
ph_base = band_phase(base)
print(f"{'construction':>34} {'PLV':>8} {'mean lag (deg)':>16}")
for shift_deg in (0, 45, 90, 180):
    analytic = hilbert(base)
    shifted = np.real(analytic * np.exp(1j * np.deg2rad(shift_deg)))
    ph_s = band_phase(shifted)
    print(f"{'same signal, ' + str(shift_deg) + ' deg shift':>34} "
          f"{plv(ph_base, ph_s):>8.4f} {np.rad2deg(mean_phase_lag(ph_base, ph_s)):>15.1f}")
    assert plv(ph_base, ph_s) > 0.99, "a constant phase difference gives PLV 1 at any value"

# (b) Two independent signals: PLV near zero, and SPK 4's bias sets how near.
indep_a = filtfilt(*butter(4, list(BETA), btype='band', fs=FS), rng.standard_normal(T))
indep_b = filtfilt(*butter(4, list(BETA), btype='band', fs=FS), rng.standard_normal(T))
plv_indep = plv(band_phase(indep_a), band_phase(indep_b))
print(f"\\ntwo independent signals, PLV: {plv_indep:.4f}")
assert plv_indep < 0.1, "independent signals must not lock"
print("\\nStep 1 passed. PLV measures whether the phase difference is CONSTANT, and")
print("says nothing about what the constant is.")''')

m.md(r'''---

## 2. Volume conduction gives PLV 1 with no interaction

REC 1 established that extracellular potential is a linear, **instantaneous**
superposition: no time constant, no propagation delay at these scales. LIN 4 wrote
that as $X = AS$.

Take one source and two contacts. Both record $a_1 s(t)$ and $a_2 s(t)$ plus
their own local noise. The two recordings are scaled copies of the same waveform
**at the same instant**, so their phases are identical, so their phase difference
is exactly zero, so the PLV is exactly 1.

No interaction. No communication. No delay. The maximum possible value of the
measure, produced by geometry.

This is not an edge case for a DBS lead. REC 1 measured the LFP reach at several
millimetres against contact spacings of 0.5 to 2 mm, so **every pair of contacts
on a lead sees shared sources**, and a beta PLV near 1 between them is the
expected result of doing nothing wrong.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
source = filtfilt(*butter(4, list(BETA), btype='band', fs=FS), rng.standard_normal(T))

print(f"{'local noise, relative to source':>34} {'PLV':>8} {'mean lag (deg)':>16}")
lags, plvs = {}, {}
for noise_ratio in (0.0, 0.25, 1.0, 4.0):
    ch1 = 1.0 * source + noise_ratio * filtfilt(
        *butter(4, list(BETA), btype='band', fs=FS), rng.standard_normal(T))
    ch2 = 0.6 * source + noise_ratio * filtfilt(
        *butter(4, list(BETA), btype='band', fs=FS), rng.standard_normal(T))
    p1, p2 = band_phase(ch1), band_phase(ch2)
    plvs[noise_ratio] = plv(p1, p2)
    lags[noise_ratio] = np.rad2deg(mean_phase_lag(p1, p2))
    print(f"{noise_ratio:>34g} {plvs[noise_ratio]:>8.4f} {lags[noise_ratio]:>15.1f}")

assert plvs[0.0] > 0.999, "pure volume conduction gives PLV 1 exactly"
assert plvs[0.25] > 0.5, "and it survives substantial independent local activity"
assert plvs[0.0] > plvs[0.25] > plvs[1.0] > plvs[4.0], \\
    "local activity dilutes it monotonically"
# The giveaway is the lag, and it is zero wherever there is anything to lock to.
for ratio, val in lags.items():
    if plvs[ratio] > 0.1:
        assert abs(val) < 5.0, f"volume conduction locks at ZERO lag; got {val:.1f} deg"
print("\\nWherever the PLV is meaningful the lag is within a degree of zero. At a noise")
print("ratio of 4 the PLV has collapsed to 0.03, so its lag is an angle of nothing.")

# The distinguishing feature: a real interaction has a real delay.
DELAY_MS = 12.0
delayed = np.r_[np.zeros(int(DELAY_MS)), source[:-int(DELAY_MS)]]
ch_a = source + 0.5 * filtfilt(*butter(4, list(BETA), btype='band', fs=FS),
                               rng.standard_normal(T))
ch_b = delayed + 0.5 * filtfilt(*butter(4, list(BETA), btype='band', fs=FS),
                                rng.standard_normal(T))
pa, pb = band_phase(ch_a), band_phase(ch_b)
lag_real = np.rad2deg(mean_phase_lag(pa, pb))
expected = -360.0 * 20.0 * DELAY_MS / 1000.0        # at a 20 Hz centre frequency
print(f"\\ntrue interaction with a {DELAY_MS:.0f} ms delay:")
print(f"  PLV {plv(pa, pb):.4f}, mean lag {lag_real:.1f} deg "
      f"(expected about {expected:.0f} deg at 20 Hz)")
assert abs(lag_real) > 20.0, "a real delay produces a NON-zero phase lag"
assert plv(pa, pb) > 0.5, "and still locks"

print("\\nBoth cases give a high PLV. Only the lag distinguishes them, and PLV")
print("discards the lag by construction. That is the trap.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. What a montage does, and does not, fix

LIN 2 and LIN 4 established that a zero-sum montage removes a shared reference.
It does **not** remove volume conduction, and the difference matters here.

A shared reference adds the same signal to every contact, so subtracting two
contacts cancels it exactly. Volume conduction delivers the same source to
several contacts with **different gains**, because the contacts sit at different
distances. A difference of two unequal copies is not zero; it is a smaller copy
of the same waveform, still at zero lag.

So a bipolar montage reduces the amplitude of the shared source but leaves its
phase relationship intact. The PLV between two bipolar derivations that share a
source is still inflated, and by an amount that depends on geometry rather than
on physiology.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
# Four contacts along a lead, one shared source, gains falling with distance.
GAINS = np.array([1.0, 0.72, 0.45, 0.3])

def build(local_amp, gen):
    local = [filtfilt(*butter(4, list(BETA), btype='band', fs=FS), gen.standard_normal(T))
             for _ in range(4)]
    return np.array([g * source + local_amp * lo for g, lo in zip(GAINS, local)])

def null_pair(gen):
    n = [filtfilt(*butter(4, list(BETA), btype='band', fs=FS), gen.standard_normal(T))
         for _ in range(4)]
    return plv(band_phase(n[0] - n[1]), band_phase(n[2] - n[3]))

print(f"{'local activity':>15} {'monopolar PLV':>15} {'bipolar PLV':>13} {'bipolar null':>14}")
mono_p, bip_p, null_p = {}, {}, {}
for local_amp in (0.05, 0.15, 0.5, 1.5):
    gen = np.random.default_rng(int(local_amp * 1000) + 5)
    C = build(local_amp, gen)
    mono_p[local_amp] = plv(band_phase(C[0]), band_phase(C[3]))
    bip_p[local_amp] = plv(band_phase(C[0] - C[1]), band_phase(C[2] - C[3]))
    null_p[local_amp] = null_pair(gen)
    print(f"{local_amp:>15g} {mono_p[local_amp]:>15.4f} {bip_p[local_amp]:>13.4f} "
          f"{null_p[local_amp]:>14.4f}")

# The montage always helps.
for a in mono_p:
    assert bip_p[a] < mono_p[a], f"the montage must reduce the inflation at local={a}"

# But how much is left is decided by the recording, not by the montage.
assert bip_p[0.05] > 0.5, \\
    "with contacts dominated by a shared source, bipolar PLV is still hugely inflated"
assert bip_p[0.05] > 15 * null_p[0.05], "far above its own null"
assert bip_p[0.5] < 0.15, "with plenty of local activity the montage nearly suffices"

lag_low = np.rad2deg(mean_phase_lag(
    band_phase(build(0.05, np.random.default_rng(55))[0] - build(0.05, np.random.default_rng(55))[1]),
    band_phase(build(0.05, np.random.default_rng(55))[2] - build(0.05, np.random.default_rng(55))[3])))
print(f"\\nand the residual is still at near-zero lag: {lag_low:.1f} deg")
assert abs(lag_low) < 25.0, "what survives the montage is still zero-lag, so still not interaction"

print("\\nThe montage always helps and never finishes the job. How much survives is set")
print("by the ratio of shared source to independent local activity, which is a")
print("property of where the contacts happen to sit, not something you choose. With")
print(f"contacts dominated by one source the bipolar PLV is still {bip_p[0.05]:.2f} against a")
print(f"null of {null_p[0.05]:.2f}, and it is still at zero lag, so it is still not interaction.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. PLV measures whether a phase difference is **constant**, not what it is. A
   signal against a 0, 45, 90 or 180 degree shifted copy of itself gives PLV 1 in
   every case.
2. Volume conduction is instantaneous, so two contacts sharing a source have
   identical phase and **PLV 1 exactly**, with no interaction of any kind. It
   survives a great deal of independent local activity. Since REC 1 measured LFP
   reach in millimetres against contact spacings under 2 mm, every pair on a lead
   shares sources and an inflated beta PLV is the expected result of nothing
   going wrong.
3. The only thing separating the two cases is the **phase lag**, which is zero
   for volume conduction and non-zero for a real delay, and PLV discards it by
   construction.
4. A bipolar montage always reduces the inflation and never finishes the job, and
   how much survives is decided by the recording rather than by the montage. With
   contacts dominated by one shared source the bipolar PLV is still 0.79 against
   a null of 0.01; with plenty of independent local activity it falls to 0.06.
   What survives is still at zero lag, so it is still not interaction.

### Exercises

**Exercise 1.** REC 1 gave the falloff of an LFP source with distance. Compute the
expected residual PLV between two bipolar derivations for contact spacings of
0.5, 1 and 2 mm, and say which lead geometry is least exposed.

**Exercise 2.** Section 2 planted a 12 ms delay and recovered a phase lag close
to the prediction $-360 f \tau$. Show that the recovered lag becomes ambiguous
once $f\tau$ exceeds a half cycle, and state the longest delay a 20 Hz analysis
can measure without ambiguity.

**Exercise 3.** Two contacts show beta PLV of 0.85 with a mean lag of 3 degrees.
Write the two sentences you would put in a paper: what you can claim, and what
you would need to measure to claim more.

---

**Next: CON 2, the weighted phase lag index.** If the lag is the only thing that
distinguishes the two cases, the obvious repair is a measure that ignores
everything except the lag. That is what CON 2 builds, and it has a cost.
''')

m.emit()
verify("06_connectivity", "01_plv_and_the_zero_lag_trap")
print("  CON 1 OK")
