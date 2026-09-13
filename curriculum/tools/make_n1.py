import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("07_guardrails", "01_stimulation_artifact_and_blanking")

m.md(r'''# Module G1: Stimulation Artifact and the Cost of Blanking {{VARIANT}}

**Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails**

{{INSTRUCTIONS}}

Recording while stimulating is the central technical problem of adaptive DBS, and
the standard mitigation, blanking the stimulus, is a deletion of samples. PRE 1
established what deleting samples costs. This module measures that cost in the
one setting where the deletion is periodic, which turns out to be the worst case.

**What it assumes**

| From | What is used |
|---|---|
| SIG 1 | Aliasing, the folding map, and quantization with a large signal present. |
| SIG 3 | That a periodic operation on a signal creates energy at its own rate. |
| SIG 4 | Welch, and that a spectral estimate has variance. |
| PRE 1 | That excision costs the time base and phase continuity, not the average spectrum. |

**What it underwrites**

G2's control loop, and every recording made with stimulation on.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import welch, butter, filtfilt

rng = np.random.default_rng(141)
FS = 24000.0
STIM_HZ = 130.0
PULSE_US = 60.0
print("Environment initialized for Module G1")''')

m.md(r'''---

## 1. The scale of the problem

A therapeutic DBS pulse delivers a few volts across a contact. A beta
oscillation is tens of microvolts. The ratio is five to six orders of magnitude,
and both arrive at the same amplifier.

SIG 1 already priced this. The converter's range must accommodate the artifact
without clipping, and the LFP then occupies
$N + \log_2(A_{\text{LFP}}/V_{FS})$ bits. That is not a small correction: it is
the difference between a usable recording and a quantised one.''')

m.task(
'''def stim_train(n_samples: int, fs: float = FS, stim_hz: float = STIM_HZ,
               pulse_us: float = PULSE_US, amplitude_uv: float = 2e6) -> np.ndarray:
    """A biphasic stimulation artifact train.

    Each pulse is `pulse_us` microseconds of positive followed by the same of
    negative, repeating at `stim_hz`.
    """
    # TODO: pulse length in samples = pulse_us * 1e-6 * fs, at least 1
    # TODO: period in samples = fs / stim_hz
    # TODO: for each pulse start, write +amplitude then -amplitude
    raise NotImplementedError("Implement stim_train")''',
'''def stim_train(n_samples: int, fs: float = FS, stim_hz: float = STIM_HZ,
               pulse_us: float = PULSE_US, amplitude_uv: float = 2e6) -> np.ndarray:
    """A biphasic stimulation artifact train.

    Each pulse is `pulse_us` microseconds of positive followed by the same of
    negative, repeating at `stim_hz`.
    """
    out = np.zeros(n_samples)
    w = max(1, int(round(pulse_us * 1e-6 * fs)))
    period = fs / stim_hz
    k = 0
    while True:
        start = int(round(k * period))
        if start + 2 * w >= n_samples:
            break
        out[start:start + w] = amplitude_uv
        out[start + w:start + 2 * w] = -amplitude_uv
        k += 1
    return out''')

m.code('''# --- TEST CELL FOR STEP 1 ---
T = int(FS * 4.0)
t = np.arange(T) / FS

beta = 30.0 * np.sin(2 * np.pi * 20.0 * t)                 # 30 uV beta
noise = 8.0 * rng.standard_normal(T)
artifact = stim_train(T)
recording = beta + noise + artifact

pulses = int(np.sum(np.diff((artifact > 0).astype(int)) == 1))
print(f"pulses in {T/FS:.0f} s at {STIM_HZ:.0f} Hz: {pulses} (expected about {STIM_HZ*4:.0f})")
assert abs(pulses - STIM_HZ * 4) < 5, "the train must run at the stimulation rate"

print(f"\\nbeta amplitude     : {np.max(np.abs(beta)):>12.1f} uV")
print(f"artifact amplitude : {np.max(np.abs(artifact)):>12.1f} uV")
print(f"ratio              : {np.max(np.abs(artifact))/np.max(np.abs(beta)):>12.0f}x")
assert np.max(np.abs(artifact)) / np.max(np.abs(beta)) > 1e4, \\
    "the artifact is four or more orders of magnitude larger"

# SIG 1's effective bits, applied.
def effective_bits(signal_uv, full_scale_uv, n_bits=16):
    return max(0.0, n_bits + np.log2(signal_uv / full_scale_uv))

full_scale = np.max(np.abs(artifact)) * 1.1
print(f"\\nADC range must reach   : {full_scale:>12.0f} uV")
print(f"bits reaching the beta : {effective_bits(30.0, full_scale):>12.1f} of 16")
assert effective_bits(30.0, full_scale) < 3.0, \\
    "with the range set for the artifact, the LFP gets almost nothing"
print("\\nStep 1 passed. Before any filtering, the converter has already been spent")
print("on the artifact. This is SIG 1's quantization result, arriving as a design problem.")''')

m.md(r'''---

## 2. Blanking, and where its cost actually falls

The standard mitigation replaces the samples around each pulse with an
interpolation. PRE 1 established what deleting samples costs, and found the damage
was in the time base and phase continuity rather than in an averaged spectrum.

Blanking differs from PRE 1's case in a way that helps: the samples are **replaced,
not removed**, so the time base survives intact and every event marker still
points where it did. That is a real advantage and it is why blanking is done this
way.

What it costs instead is measured below, and the answer is not where intuition
puts it. The pulse itself is about one percent of the record. The **guard band**
around each pulse, which exists because the amplifier needs time to recover, is
an order of magnitude more, and it is the guard band that decides everything.''')

m.task(
'''def blank_and_interpolate(x: np.ndarray, artifact: np.ndarray,
                          guard_samples: int = 8) -> np.ndarray:
    """Replace each artifact region, plus a guard on either side, by a straight line.

    Production equivalent: this is what most commercial and research systems do;
    the alternative in Section 3 is template subtraction.
    """
    # TODO: find where |artifact| > 0, and dilate that mask by guard_samples
    # TODO: for each contiguous blanked run, linearly interpolate between the
    #       last good sample before it and the first good sample after it
    raise NotImplementedError("Implement blank_and_interpolate")''',
'''def blank_and_interpolate(x: np.ndarray, artifact: np.ndarray,
                          guard_samples: int = 8) -> np.ndarray:
    """Replace each artifact region, plus a guard on either side, by a straight line.

    Production equivalent: this is what most commercial and research systems do;
    the alternative in Section 3 is template subtraction.
    """
    bad = np.abs(artifact) > 0
    if guard_samples > 0:
        k = np.ones(2 * guard_samples + 1)
        bad = np.convolve(bad.astype(float), k, mode='same') > 0
    out = np.array(x, dtype=float, copy=True)
    good = np.flatnonzero(~bad)
    if good.size == 0:
        return out
    idx = np.flatnonzero(bad)
    out[idx] = np.interp(idx, good, out[good])
    return out''')

m.code('''# --- TEST CELL FOR STEP 2 ---
clean = beta + noise                      # what we would have recorded with stim off\nBANDS = {"beta 13-30": (13, 30), "low gamma 30-60": (30, 60), "high gamma 70-150": (70, 150),
         "200-500": (200, 500), "1k-3k": (1000, 3000)}
f_ax, P_clean = welch(clean, FS, nperseg=16384)

def band_power(P, lo, hi):
    sel = (f_ax >= lo) & (f_ax < hi)
    return float(np.mean(P[sel]))

print(f"{'guard':>6} {'% replaced':>11} " + " ".join(f"{k:>18}" for k in BANDS))
ratios = {}
for guard in (0, 8, 24):
    b = blank_and_interpolate(recording, artifact, guard_samples=guard)
    pct = float(np.mean(b != recording))
    _, P_b = welch(b, FS, nperseg=16384)
    ratios[guard] = {n: band_power(P_b, lo, hi) / band_power(P_clean, lo, hi)
                     for n, (lo, hi) in BANDS.items()}
    print(f"{guard:>6} {pct:>10.1%} " +
          " ".join(f"{ratios[guard][n]:>17.2f}x" for n in BANDS))
    assert np.max(np.abs(b)) < 1e3, "blanking must remove the artifact itself"

# The pulse alone is nearly harmless. It is the guard band that does the damage.
for n in BANDS:
    assert abs(ratios[0][n] - 1.0) < 0.15, \\
        f"blanking only the pulse leaves {n} essentially untouched"
assert ratios[24]["high gamma 70-150"] > 5.0, \\
    "a wide guard band multiplies high-gamma power several-fold"
assert ratios[8]["high gamma 70-150"] > 1.5, "and a modest one still nearly doubles it"

# Beta is untouched at every setting, which is exactly why this goes unnoticed.
for guard in (0, 8, 24):
    assert abs(ratios[guard]["beta 13-30"] - 1.0) < 0.1, \\
        "beta survives every guard band, so nothing warns you"

# And the highest frequencies go DOWN, because interpolation is a smoother.
assert ratios[24]["1k-3k"] < 0.9, "interpolation removes high-frequency content"

print("\\nRead the beta column first: 1.00x at every setting. The band the device")
print("uses is untouched, so nothing in a beta analysis will ever warn you.")
print("\\nNow read gamma and high gamma. A 24-sample guard replaces 27 percent of the")
print("record with straight lines, and straight lines joined end to end have corners.")
print("Corners are broadband. High-gamma power rises SEVENFOLD, and the very highest")
print("frequencies fall, because interpolation is also a smoother.")
print("\\nThe guard band is not a detail of the artifact removal. It is the parameter")
print("that decides whether a high-gamma result from a stimulating recording means")
print("anything, and it is rarely reported.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Where the artifact's harmonics land, and why the sampling rate decides

Section 2 dealt with what blanking does in the time domain. Independently of it,
the stimulation train itself is periodic at 130 Hz, so SIG 3 says it carries energy
at every multiple of 130 Hz, and SIG 1 says any of those above half the sampling
rate folds down.

At 24 kHz nothing folds: 130 Hz and its first dozens of harmonics are all well
below Nyquist. Decimate to a rate typical of an implanted sensing device and the
harmonics fold into the physiological bands, and SIG 1's arithmetic says exactly
where.

This is the same calculation SIG 1 made for the raw artifact. It applies again,
unchanged, to the artifact that blanking created, which is the point: mitigating
in the time domain did not remove the problem from the frequency domain.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def alias_frequency(f_hz, fs_hz):
    """From SIG 1."""
    folded = float(f_hz) % float(fs_hz)
    return float(min(folded, fs_hz - folded))

BETA_BAND = (13.0, 30.0)
print(f"stimulation at {STIM_HZ:.0f} Hz; where its harmonics land after decimation\\n")
print(f"{'target rate':>12} " + " ".join(f"{'h' + str(k):>7}" for k in range(1, 7)) + "   verdict")
hits = {}
for target in (24000.0, 1000.0, 500.0, 250.0):
    landed = [alias_frequency(STIM_HZ * k, target) for k in range(1, 7)]
    in_beta = [k + 1 for k, v in enumerate(landed) if BETA_BAND[0] <= v <= BETA_BAND[1]]
    hits[target] = in_beta
    row = " ".join(f"{v:>7.1f}" for v in landed)
    print(f"{target:>9.0f} Hz {row}   "
          f"{'beta hit via h' + ','.join(map(str, in_beta)) if in_beta else 'clear'}")

assert not hits[24000.0], "at the acquisition rate nothing folds into beta"
assert hits[250.0], "at an implanted sensing rate, harmonics land in beta"

# And SIG 1's guardrail G6 check applies to the decimation itself.
def usable_bandwidth_hz(sfreq, cutoff_fraction=0.8):
    return sfreq / 2.0 * cutoff_fraction

print(f"\\n{'rate':>8} {'usable bandwidth':>18} {'stim fundamental':>18} {'survives?':>11}")
for target in (1000.0, 500.0, 250.0):
    ub = usable_bandwidth_hz(target)
    print(f"{target:>5.0f} Hz {ub:>15.0f} Hz {STIM_HZ:>15.0f} Hz "
          f"{'yes' if STIM_HZ < ub else 'FOLDED':>11}")
assert STIM_HZ > usable_bandwidth_hz(250.0), \\
    "at 250 Hz the fundamental is above the usable bandwidth and must fold"

print("\\nSection 2 showed the guard band decides your high-gamma result. This section")
print("shows the sampling rate decides your beta result: at 250 Hz two harmonics of")
print("an ordinary 130 Hz stimulus land inside the beta band, and the fundamental is")
print("above the bandwidth guardrail G6 will certify. That is the band the device")
print("uses to decide whether to stimulate. G2 closes a loop around exactly it.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. A stimulation artifact is four or more orders of magnitude larger than beta.
   With the converter range set to accommodate it, the LFP receives under 3 of 16
   bits, which is SIG 1's quantization result arriving as a hardware design problem
   before any analysis begins.
2. Blanking replaces samples rather than removing them, so unlike PRE 1's excision
   the time base survives. Its cost is elsewhere and it is **not** where intuition
   puts it. Blanking the pulse alone touches nothing: every band stays within 4
   percent. The **guard band** does the damage. At 24 samples it replaces 27
   percent of the record with straight lines, whose corners are broadband, and
   high-gamma power rises **sevenfold** while the highest frequencies fall
   because interpolation is also a smoother. Beta is 1.00x at every setting, so
   a beta analysis will never warn you.
3. The stimulation train's own harmonics obey SIG 1's folding map. At the 24 kHz
   acquisition rate nothing folds. At an implanted sensing rate of 250 Hz,
   harmonics land inside the beta band, and the fundamental is above the usable
   bandwidth that guardrail G6 checks.
4. Together: the guard band decides your high-gamma result, the sampling rate
   decides your beta result, and neither is usually stated.

### Exercises

**Exercise 1.** Template subtraction estimates the artifact waveform by averaging
over many pulses and subtracts it, rather than deleting. Implement it and compare
the injected power at 130 Hz against blanking. What assumption does it need about
the artifact that blanking does not?

**Exercise 2.** Section 2 used an 8-sample guard band. Sweep it from 0 to 40 and
plot injected power at the stimulation frequency against residual artifact. Is
there a setting that gives neither?

**Exercise 3.** Stimulation frequency is a clinical parameter, usually between
130 and 185 Hz. Using SIG 1's folding map, find the stimulation frequencies that are
safest for a device sensing at 250 Hz, and say whether that consideration should
ever influence a clinical setting.

---

**Next: GRL 2, adaptive DBS control loops.** This module produced a contaminated
beta estimate. G2 closes a feedback loop around it and asks what the total
latency does to the result.
''')

m.emit()
verify("07_guardrails", "01_stimulation_artifact_and_blanking")
print("  GRL 1 OK")
