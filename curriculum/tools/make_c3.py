import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("06_connectivity", "03_phase_amplitude_coupling")

m.md(r'''# Lesson CON 3: Phase-Amplitude Coupling and Waveform Shape {{VARIANT}}

**Analysis · Connectivity and Spectral Coupling**

{{INSTRUCTIONS}}

CON 1 and CON 2 dealt with a confound coming from geometry. This one comes from
nothing but the **shape** of a waveform, and it needs no second region, no
volume conduction and no shared reference to produce a large, significant,
publishable result.

**What it assumes**

| From | What is used |
|---|---|
| SIG 3 | That a non-sinusoidal periodic signal has energy at integer multiples of its fundamental. |
| SIG 6 | The analytic signal, the envelope, and that phase is defined only within a band. |
| SPK 4 | That a coupling measure needs a null, not a threshold. |

**What it underwrites**

Guardrail **G8**, which asks for a z-score against a null, and any
cross-frequency claim made about subthalamic beta, which is famously
non-sinusoidal.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, hilbert, sawtooth

rng = np.random.default_rng(121)
FS = 1000.0
PHASE_BAND = (13.0, 30.0)
AMP_BAND = (50.0, 150.0)

def bandpass(x, band, fs=FS):
    return filtfilt(*butter(4, list(band), btype='band', fs=fs), x)

print("Environment initialized for Lesson CON 3")''')

m.md(r'''---

## 1. The modulation index

Phase-amplitude coupling asks whether the amplitude of a fast rhythm depends on
the phase of a slow one. Tort's modulation index makes that precise:

1. Take the slow band's phase and the fast band's envelope, both from SIG 6.
2. Bin the phase, and average the envelope within each bin.
3. Normalise the result to a distribution over bins.
4. Report how far that distribution sits from uniform, as a
   Kullback-Leibler divergence scaled to $[0, 1]$:

$$\text{MI} = \frac{D_{KL}(P \parallel U)}{\log N_{\text{bins}}}$$

MI is zero when the fast envelope is flat across slow phase and grows as the
dependence sharpens. It is a clean measure of the thing it measures. The question
this module asks is what else produces the thing it measures.''')

m.task(
'''def modulation_index(x: np.ndarray, phase_band=PHASE_BAND, amp_band=AMP_BAND,
                     n_bins: int = 18, fs: float = FS) -> float:
    """Tort's modulation index between the phase of `phase_band` and the
    amplitude envelope of `amp_band`, both taken from the SAME signal.

    Production equivalent: `pactools.Comodulogram`, which is a dependency of this
    project, and `tensorpac`.
    """
    # TODO: phase = angle(hilbert(bandpass(x, phase_band)))
    # TODO: amp   = abs(hilbert(bandpass(x, amp_band)))
    # TODO: bin the phase into n_bins over (-pi, pi], mean the amplitude per bin
    # TODO: normalise the per-bin means to sum to 1, giving P
    # TODO: return KL(P || uniform) / log(n_bins)
    raise NotImplementedError("Implement modulation_index")''',
'''def modulation_index(x: np.ndarray, phase_band=PHASE_BAND, amp_band=AMP_BAND,
                     n_bins: int = 18, fs: float = FS) -> float:
    """Tort's modulation index between the phase of `phase_band` and the
    amplitude envelope of `amp_band`, both taken from the SAME signal.

    Production equivalent: `pactools.Comodulogram`, which is a dependency of this
    project, and `tensorpac`.
    """
    phase = np.angle(hilbert(bandpass(x, phase_band, fs)))
    amp = np.abs(hilbert(bandpass(x, amp_band, fs)))
    edges = np.linspace(-np.pi, np.pi, n_bins + 1)
    idx = np.clip(np.digitize(phase, edges) - 1, 0, n_bins - 1)
    means = np.array([amp[idx == b].mean() if np.any(idx == b) else 0.0
                      for b in range(n_bins)])
    total = means.sum()
    if total <= 0:
        return 0.0
    P = means / total
    nz = P > 0
    kl = np.log(n_bins) + np.sum(P[nz] * np.log(P[nz]))
    return float(kl / np.log(n_bins))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
T = 120000
t = np.arange(T) / FS
F_SLOW, F_FAST = 20.0, 90.0

# (a) No coupling: independent slow and fast rhythms plus noise.
no_pac = (np.sin(2 * np.pi * F_SLOW * t)
          + 0.4 * np.sin(2 * np.pi * F_FAST * t + rng.random() * 6.28)
          + 0.5 * rng.standard_normal(T))

# (b) Genuine coupling: the fast amplitude is modulated by the slow phase.
slow = np.sin(2 * np.pi * F_SLOW * t)
envelope = 0.5 * (1 + np.cos(2 * np.pi * F_SLOW * t))
real_pac = slow + 0.4 * envelope * np.sin(2 * np.pi * F_FAST * t) + 0.5 * rng.standard_normal(T)

mi_none = modulation_index(no_pac)
mi_real = modulation_index(real_pac)
print(f"no coupling      : MI {mi_none:.5f}")
print(f"genuine coupling : MI {mi_real:.5f}")
assert mi_real > 10 * mi_none, "the measure must detect real coupling"
assert mi_none < 0.005, "and report near zero when there is none"

# It is a sinusoid throughout, so nothing here is about waveform shape yet.
print("\\nStep 1 passed. On sinusoids the modulation index does exactly what it says.")''')

m.md(r'''---

## 2. A sharp waveform manufactures coupling

Subthalamic beta is not a sinusoid. It is sharp, asymmetric, and often described
as sawtooth-like, and that is a well-documented property of the signal rather
than a defect of the recording.

SIG 3 established what follows: a periodic waveform that is not a sinusoid has
energy at **integer multiples** of its fundamental. A 20 Hz sawtooth has
components at 40, 60, 80, 100 Hz and upward, all of them **phase-locked to the
fundamental**, because they are the same waveform.

Now put that through the modulation index. The high-frequency components live in
the amplitude band. Their amplitude peaks wherever the sharp feature of the
waveform occurs, which is at a fixed phase of the fundamental. The measure sees
an envelope that depends on slow phase and reports coupling.

There is no coupling. There is one oscillation with a shape.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
# A single non-sinusoidal oscillator. One rhythm, no second process anywhere.
SHARP_WIDTH = 0.05

def sharp_oscillator(width, wander=0.02, seed=0):
    """A non-sinusoidal oscillator with a slowly wandering phase.

    Real beta is neither sinusoidal nor perfectly periodic. The wander matters
    for Section 3: a PERFECTLY periodic signal is unchanged by a circular shift,
    which makes a shuffled null degenerate.
    """
    gen = np.random.default_rng(seed)
    phase = 2 * np.pi * F_SLOW * t + np.cumsum(gen.standard_normal(T)) * wander
    return sawtooth(phase, width=width) + 0.5 * gen.standard_normal(T)

sharp = sharp_oscillator(SHARP_WIDTH, seed=3)
mi_sharp = modulation_index(sharp)

pure = np.sin(2 * np.pi * F_SLOW * t) + 0.5 * rng.standard_normal(T)
mi_pure = modulation_index(pure)

print(f"{'signal':>44} {'MI':>10}")
print(f"{'pure 20 Hz sinusoid + noise':>44} {mi_pure:>10.5f}")
print(f"{'20 Hz SAWTOOTH + noise (one oscillator)':>44} {mi_sharp:>10.5f}")
print(f"{'genuine 20-90 Hz coupling, from Section 1':>44} {mi_real:>10.5f}")

assert mi_sharp > 10 * mi_pure, "a sharp waveform manufactures a modulation index"
assert mi_sharp > 0.3 * mi_real, \\
    "and it is the same order as genuine coupling, not a small perturbation"

# Confirm the mechanism is harmonics, by looking at the spectrum.
from scipy.signal import welch
f_ax, P_sharp = welch(sawtooth(2 * np.pi * F_SLOW * t, width=SHARP_WIDTH), FS, nperseg=4096)
harmonics = [F_SLOW * k for k in (1, 2, 3, 4, 5)]
print(f"\\npower at harmonics of {F_SLOW:.0f} Hz in the sawtooth:")
for h in harmonics:
    print(f"  {h:>5.0f} Hz : {P_sharp[np.argmin(np.abs(f_ax - h))]:.4g}")
in_amp_band = [h for h in [F_SLOW * k for k in range(1, 9)]
               if AMP_BAND[0] <= h <= AMP_BAND[1]]
print(f"\\nharmonics falling inside the {AMP_BAND[0]:.0f}-{AMP_BAND[1]:.0f} Hz amplitude band: {in_amp_band}")
assert len(in_amp_band) >= 3, "several harmonics land in the amplitude band, which is the mechanism"

# The sharper the waveform, the stronger the harmonics, the larger the fake MI.
print(f"\\n{'waveform sharpness':>20} {'MI':>10}")
for width in (0.5, 0.35, 0.2, 0.05):
    label = "symmetric" if width == 0.5 else f"width {width}"
    print(f"{label:>20} {modulation_index(sharp_oscillator(width, seed=3)):>10.5f}")
mi_symmetric = modulation_index(sharp_oscillator(0.5, seed=3))
assert modulation_index(sharp_oscillator(0.05, seed=3)) > 10 * mi_symmetric, \\
    "sharper asymmetry gives more harmonic energy and a larger spurious MI"
print("\\nStep 2 passed. One oscillator, no coupling of any kind, and a modulation")
print("index comparable to the genuine case.")''')

m.md(r'''---

## 3. Telling them apart

The two cases are distinguishable, and the way in is a fact about harmonics that
Section 2 skipped past.

**A single harmonic has a constant envelope.** A pure 60 Hz sinusoid has the same
amplitude at every moment, so on its own it produces no modulation of anything.
Spurious coupling therefore requires the amplitude band to contain **at least
two** harmonics, whose beating produces an envelope that rises and falls at their
difference frequency, which is the fundamental.

That gives a diagnostic that costs one line. **Narrow the amplitude band.** Once
it holds a single harmonic, harmonic-driven coupling disappears, because there is
nothing left to beat against. Genuine coupling does not care: its envelope
modulation is a property of the signal, not of how many components you included.

A shuffled null does not help, and it is worth being explicit about why: the
harmonics are real features of the real signal, so they survive any shuffle that
leaves the waveform intact.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
# DIAGNOSTIC 1: narrow the amplitude band until it holds one harmonic.
print(f"{'amplitude band':>18} {'harmonics inside':>18} {'MI sawtooth':>13} {'MI genuine':>12}")
narrow_sharp, narrow_real = {}, {}
for lo, hi in [(50, 150), (70, 110), (70, 90), (50, 70)]:
    n_harm = sum(1 for k in range(1, 12) if lo <= F_SLOW * k <= hi)
    narrow_sharp[(lo, hi)] = modulation_index(sharp, amp_band=(lo, hi))
    narrow_real[(lo, hi)] = modulation_index(real_pac, amp_band=(lo, hi))
    print(f"{f'{lo}-{hi} Hz':>18} {n_harm:>18} {narrow_sharp[(lo,hi)]:>13.5f} "
          f"{narrow_real[(lo,hi)]:>12.5f}")

assert narrow_sharp[(50, 150)] > 20 * narrow_sharp[(70, 90)], \\
    "harmonic-driven coupling collapses once the band holds a single harmonic"
assert narrow_real[(70, 90)] > 5 * narrow_sharp[(70, 90)], \\
    "while genuine coupling survives the same narrowing"
print("\\nA single harmonic has a flat envelope, so it cannot modulate anything. The")
print("spurious coupling needed two of them beating together, and narrowing the band")
print("removed the second. Genuine coupling was untouched.")

# DIAGNOSTIC 2: remove the asymmetry and the coupling must go with it.
symmetric = sharp_oscillator(0.5, seed=3)
print(f"\\nMI of the sharp waveform     : {mi_sharp:.5f}")
print(f"MI after making it symmetric : {modulation_index(symmetric):.5f}")
assert modulation_index(symmetric) < 0.05 * mi_sharp, \\
    "if shape explains the coupling, removing the shape must remove the coupling"

# AND THE NON-DIAGNOSTIC: a shuffle null does not rescue you.
def shuffle_null_z(x, n_perm=60):
    obs = modulation_index(x)
    amp = np.abs(hilbert(bandpass(x, AMP_BAND)))
    ph = np.angle(hilbert(bandpass(x, PHASE_BAND)))
    edges = np.linspace(-np.pi, np.pi, 19)
    idx = np.clip(np.digitize(ph, edges) - 1, 0, 17)
    null = []
    for sd in range(n_perm):
        shift = np.random.default_rng(900 + sd).integers(1000, len(x) - 1000)
        rolled = np.roll(amp, shift)
        means = np.array([rolled[idx == b].mean() for b in range(18)])
        P = means / means.sum()
        null.append(float((np.log(18) + np.sum(P * np.log(P))) / np.log(18)))
    null = np.array(null)
    return (obs - null.mean()) / null.std()

z_sharp = shuffle_null_z(sharp)
z_periodic = shuffle_null_z(sawtooth(2 * np.pi * F_SLOW * t, width=SHARP_WIDTH)
                            + 0.5 * rng.standard_normal(T))
print(f"\\nz against a shuffled null, realistic sharp oscillator : {z_sharp:+.1f}")
print(f"z against a shuffled null, PERFECTLY periodic version  : {z_periodic:+.1f}")
assert z_sharp > 5.0, "the spurious coupling is HIGHLY significant against a shuffle"
assert abs(z_periodic) < 5.0, "and a perfectly periodic signal makes the null degenerate"
print("\\nThe second row is a warning about the null itself. A circular shift of a")
print("perfectly periodic signal returns a perfectly periodic signal, so the null")
print("distribution equals the observed value and the test reports nothing. Real")
print("signals wander enough for the null to work, and then it reports the spurious")
print("coupling as overwhelmingly significant.")
print("\\nA shuffle null does not save you. The harmonics are real features of the real")
print("signal, so they survive any shuffle that leaves the waveform intact. This")
print("result is significant, reproducible, and not coupling. Guardrail G8's z-score")
print("is necessary here and it is not sufficient.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. The modulation index does what it claims on sinusoids: near zero without
   coupling, an order of magnitude larger with it.
2. **A single non-sinusoidal oscillator produces a modulation index of the same
   order as genuine coupling**, with no second process anywhere. The mechanism is
   SIG 3's: a sharp waveform has harmonics at integer multiples of its fundamental,
   several land in the amplitude band, and they are phase-locked to the
   fundamental because they are the same waveform. Sharper asymmetry gives more.
3. A shuffled null **does not detect this**. The spurious coupling is highly
   significant, because the harmonics are genuine features of the genuine signal.
   Guardrail G8's z-score is necessary and here it is not sufficient.
4. Two things do separate the cases, and the first costs one line. **Narrow the
   amplitude band.** A single harmonic has a constant envelope and cannot
   modulate anything, so spurious coupling needs two harmonics beating together
   and collapses by more than twentyfold once the band holds only one. Genuine
   coupling survives the same narrowing. **And remove the asymmetry**: if shape
   explains the coupling, symmetrising the waveform removes it, which it does.

### Exercises

**Exercise 1.** Subthalamic beta is reported as non-sinusoidal in Parkinson's
disease, and its sharpness is reported to change with medication and with
stimulation. Sketch the paper that would result from measuring PAC on and off
medication without checking waveform shape, and state which of Section 3's three
diagnostics would have caught it.

**Exercise 2.** Section 3's phase-consistency test used four amplitude bands.
Derive how many you need to distinguish harmonics from real coupling at a given
noise level, and implement the test as a single number with a null.

**Exercise 3.** A genuine coupling and a harmonic artifact can coexist. Construct
a signal containing both, and find whether any of the three diagnostics can
report the genuine part's magnitude rather than merely flagging contamination.

---

**Next: CON 4, the aperiodic component.** Every measure so far took a band and
treated its power as a quantity. CON 4 asks what a band's power is measuring when
the spectrum under it is sloped, and finds that a great many band-power effects
are slope changes.
''')

m.emit()
verify("06_connectivity", "03_phase_amplitude_coupling")
print("  CON 3 OK")
