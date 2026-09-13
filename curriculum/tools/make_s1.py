"""Generate the SIG 1 student and solutions notebooks from one source.

Both variants share cell structure by construction; only bodies marked SOLUTION
differ from their STUDENT counterpart.
"""
from __future__ import annotations

import json
import pathlib

CELLS: list[tuple[str, str, str | None]] = []  # (kind, student_src, solution_src)

def md(src): CELLS.append(("markdown", src, None))
def code(src): CELLS.append(("code", src, None))
def task(student, solution): CELLS.append(("code", student, solution))

# ---------------------------------------------------------------- 0 title
md(r"""# Lesson SIG 1: Sampling, Nyquist, and Aliasing {{VARIANT}}

{{INSTRUCTIONS}}

**Foundations · Signal Processing for Neural Time Series**

This is the entry point of Signal Processing. It assumes NumPy fluency and nothing from
Foundations · Applied Linear Algebra for Neural Arrays

By the end you will be able to state, and prove numerically, exactly which
frequencies a recording can support, where the ones it cannot support end up
instead, and how many bits of your converter a stimulation artifact costs you.

**What this module underwrites in the analysis app**

- `src/dbsspeech/preprocess/resample.py`, which reports usable bandwidth rather
  than assuming it.
- Guardrail **G6**, which refuses a run whose requested bands reach above the
  anti-alias cutoff. G6 is not a policy choice. It falls out of the arithmetic
  in Section 5.

**What the next module needs from this one.** SIG 2 (filtering and zero-phase
distortion) takes the anti-alias filter built here and asks what its phase
response does to a measured latency.
""")

# ---------------------------------------------------------------- 1 imports
code("""import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import decimate

np.random.seed(42)
print("Environment initialized for Lesson SIG 1")""")

# ---------------------------------------------------------------- 2 md
md(r"""---

## 1. The sampling theorem, and the map it implies

Sampling a continuous signal $x(t)$ at rate $f_s$ keeps only $x(n/f_s)$ for
integer $n$. The Nyquist-Shannon theorem says that if $x$ is band-limited with no
energy at or above $f_s/2$, then $x$ is recoverable exactly from those samples by

$$x(t) = \sum_{n=-\infty}^{\infty} x\!\left(\frac{n}{f_s}\right)
         \operatorname{sinc}\!\left(f_s t - n\right)$$

The condition is the whole content. Violate it and you do not lose the offending
component. You **relabel** it.

Take a cosine at frequency $f$ and sample it:

$$\cos\!\left(2\pi f \frac{n}{f_s}\right)$$

Adding any integer multiple of $f_s$ to $f$ adds an integer multiple of $2\pi n$
to the argument, which cosine does not notice. And because cosine is even,
$f$ and $-f$ give the same samples. Compose the two and every frequency collapses
onto a representative in $[0, f_s/2]$:

$$f_{\text{alias}} = \min\left(f \bmod f_s,\; f_s - (f \bmod f_s)\right)$$

This is a **map**, not an error term. It is exact, it is deterministic, and it is
not recoverable after the fact: once two components share samples, no filter
applied afterwards can separate them.""")

# ---------------------------------------------------------------- 3 task 1
task(
"""def alias_frequency(f_hz: float, fs_hz: float) -> float:
    \"\"\"Frequency in [0, fs/2] that is indistinguishable from `f_hz` at `fs_hz`.

    Production equivalent: there is none, because no library offers it. Every
    signal-processing stack assumes you checked before you sampled.
    \"\"\"
    # TODO: reduce f_hz modulo fs_hz
    # TODO: fold anything above the Nyquist frequency back down (cosine is even)
    # TODO: return the representative in [0, fs_hz / 2]
    raise NotImplementedError("Implement alias_frequency")""",
"""def alias_frequency(f_hz: float, fs_hz: float) -> float:
    \"\"\"Frequency in [0, fs/2] that is indistinguishable from `f_hz` at `fs_hz`.

    Production equivalent: there is none, because no library offers it. Every
    signal-processing stack assumes you checked before you sampled.
    \"\"\"
    folded = float(f_hz) % float(fs_hz)
    if folded > fs_hz / 2.0:
        folded = fs_hz - folded
    return float(folded)""")

# ---------------------------------------------------------------- 4 test 1
code("""# --- TEST CELL FOR STEP 1: INDEPENDENT VERIFICATION ---
# The formula is not checked against itself. It is checked against the samples.
# If alias_frequency is right, a cosine at f and a cosine at its alias must
# produce SAMPLE-FOR-SAMPLE identical sequences. That is ground truth.

fs = 1000.0
n = np.arange(2000)
t = n / fs

for f_true in [1300.0, 1700.0, 2000.0, 990.0, 130.0, 4321.0]:
    f_alias = alias_frequency(f_true, fs)
    seq_true = np.cos(2 * np.pi * f_true * t)
    seq_alias = np.cos(2 * np.pi * f_alias * t)
    assert np.allclose(seq_true, seq_alias, atol=1e-9), (
        f"{f_true} Hz and its claimed alias {f_alias} Hz do not share samples"
    )
    assert 0.0 <= f_alias <= fs / 2.0
    print(f"  {f_true:>7.1f} Hz at {fs:.0f} Hz is indistinguishable from {f_alias:>6.1f} Hz")

# A component already below Nyquist must be left alone.
assert alias_frequency(20.0, 1000.0) == 20.0
print("\\nStep 1 passed: the folding map is confirmed by the samples themselves.")""")

# ---------------------------------------------------------------- 5 md
md(r"""---

## 2. What the recording actually looks like

The plot below samples a 30 Hz cosine at 40 Hz. Nyquist is 20 Hz, so 30 Hz is
above it and folds to $40 - 30 = 10$ Hz.

The point is not that the samples are a poor record of the 30 Hz signal. The
point is that they are a **perfect** record of a 10 Hz signal. Nothing downstream
can tell the difference, because there is no difference: the two curves pass
through identical points at every sampling instant.""")

# ---------------------------------------------------------------- 6 figure
code("""fs_demo = 40.0
f_demo = 30.0
f_folded = alias_frequency(f_demo, fs_demo)

t_dense = np.linspace(0, 0.4, 4000)
n_demo = np.arange(int(0.4 * fs_demo) + 1)
t_samp = n_demo / fs_demo

plt.figure(figsize=(11, 4))
plt.plot(t_dense * 1000, np.cos(2 * np.pi * f_demo * t_dense),
         color='#06b6d4', lw=1.6, label=f'True signal, {f_demo:.0f} Hz')
plt.plot(t_dense * 1000, np.cos(2 * np.pi * f_folded * t_dense),
         color='#f59e0b', lw=1.6, ls='--', label=f'Alias, {f_folded:.0f} Hz')
plt.plot(t_samp * 1000, np.cos(2 * np.pi * f_demo * t_samp),
         'o', color='#171717', ms=7, zorder=5, label=f'Samples at {fs_demo:.0f} Hz')
plt.axhline(0, color='#d4d4d4', lw=0.8)
plt.xlabel('Time (ms)')
plt.ylabel('Amplitude')
plt.title(f'{f_demo:.0f} Hz sampled at {fs_demo:.0f} Hz is {f_folded:.0f} Hz. '
          'Both curves hit every sample.', fontweight='bold')
plt.legend(loc='upper right')
plt.grid(True, alpha=0.3, ls='--')
plt.tight_layout()
plt.show()

residual = np.max(np.abs(np.cos(2 * np.pi * f_demo * t_samp)
                         - np.cos(2 * np.pi * f_folded * t_samp)))
print(f"Largest disagreement between the two curves at any sampling instant: {residual:.2e}")""")

# ---------------------------------------------------------------- 7 md
md(r"""---

## 3. Quantization: the second thing sampling costs you

An ideal $N$-bit converter spanning full-scale range $V_{FS}$ has step
$q = V_{FS}/2^{N}$. Quantization error is well modelled as uniform on
$[-q/2, q/2]$, giving variance $q^2/12$, and for a full-scale sinusoid the
familiar result

$$\text{SNR}_{\text{dB}} = 6.02 N + 1.76$$

That number describes a signal that **fills the converter**. Intraoperative
recording rarely offers that. Local field potentials live at tens of microvolts.
If the amplifier range is set wide enough to keep a stimulation artifact three
orders of magnitude larger from clipping, the LFP occupies a small fraction of
the available codes, and the bits it actually receives are

$$N_{\text{eff}} = N + \log_2\!\left(\frac{A_{\text{signal}}}{V_{FS}}\right)$$

This is why gain staging is a scientific decision and not a technician's detail.
A 16-bit converter can deliver 8 effective bits to your LFP if the range was set
for the artifact.""")

# ---------------------------------------------------------------- 8 task 2
task(
"""def effective_bits(signal_amplitude_v: float, full_scale_v: float, n_bits: int) -> float:
    \"\"\"Bits actually delivered to a signal of amplitude `signal_amplitude_v`.

    Production equivalent: none. This is a property of the acquisition hardware
    and has to be reasoned about before the recording, not after.
    \"\"\"
    # TODO: the signal spans (signal_amplitude_v / full_scale_v) of the range
    # TODO: each halving of that fraction costs exactly one bit
    # TODO: clamp at 0.0, since a signal below one quantization step gets nothing
    raise NotImplementedError("Implement effective_bits")""",
"""def effective_bits(signal_amplitude_v: float, full_scale_v: float, n_bits: int) -> float:
    \"\"\"Bits actually delivered to a signal of amplitude `signal_amplitude_v`.

    Production equivalent: none. This is a property of the acquisition hardware
    and has to be reasoned about before the recording, not after.
    \"\"\"
    if signal_amplitude_v <= 0.0 or full_scale_v <= 0.0:
        return 0.0
    bits = n_bits + np.log2(signal_amplitude_v / full_scale_v)
    return float(max(0.0, bits))""")

# ---------------------------------------------------------------- 9 test 2
code("""# --- TEST CELL FOR STEP 2: EMPIRICAL, NOT ANALYTIC ---
# The analytic claim is SNR = 6.02 * N_eff + 1.76 dB. We do not check that
# formula against itself. We quantize a real waveform and MEASURE the SNR.

def measured_snr_db(amplitude_v, full_scale_v, n_bits, fs=10000.0, seconds=1.0):
    t = np.arange(int(fs * seconds)) / fs
    clean = amplitude_v * np.sin(2 * np.pi * 20.0 * t)
    step = (2 * full_scale_v) / (2 ** n_bits)
    quantized = np.round(clean / step) * step
    err = quantized - clean
    return 10 * np.log10(np.mean(clean ** 2) / np.mean(err ** 2))

FULL_SCALE = 1.0       # +/- 1 V amplifier range, set to survive a stim artifact
N_BITS = 16

print(f"{'LFP amplitude':>16} {'N_eff':>7} {'predicted dB':>13} {'measured dB':>12}")
for amp in [1.0, 1e-2, 1e-3, 1e-4]:
    neff = effective_bits(amp, FULL_SCALE, N_BITS)
    predicted = 6.02 * neff + 1.76
    measured = measured_snr_db(amp, FULL_SCALE, N_BITS)
    print(f"{amp*1e6:>13.0f} uV {neff:>7.2f} {predicted:>13.1f} {measured:>12.1f}")
    assert abs(predicted - measured) < 2.0, "effective_bits disagrees with measurement"

lfp_bits = effective_bits(50e-6, FULL_SCALE, N_BITS)
assert lfp_bits < 6.0, "a 50 uV LFP in a +/-1 V range should be starved of bits"
print(f"\\nA 50 uV LFP inside a +/-1 V range gets {lfp_bits:.1f} of 16 bits.")
print("Step 2 passed: measurement confirms the effective-bits model.")""")

# ---------------------------------------------------------------- 10 md
md(r"""---

## 4. Where this becomes a clinical result rather than an exercise

Deep brain stimulation runs at 130 to 185 Hz. A stimulation artifact is not a
sinusoid: it is a narrow pulse train, so it carries substantial energy at
integer multiples of the stimulation frequency.

Now sample that at 250 Hz, a rate used by implanted sensing devices where power
and telemetry budgets are tight. Nyquist is 125 Hz, so the fundamental and every
harmonic fold. Apply the map from Section 1 to the second harmonic of a
135 Hz stimulus:

$$2 \times 135 = 270 \;\text{Hz} \quad\longrightarrow\quad 270 \bmod 250 = 20\ \text{Hz}$$

Twenty hertz. The middle of the beta band, which is the band used as the control
signal for adaptive DBS and the band most often reported as a biomarker of
parkinsonian state.

The artifact does not look like an artifact after folding. It is narrowband, it
sits where the physiology is expected, and it scales with stimulation amplitude,
which is exactly the covariation an experimenter is hoping to see. Nothing
applied after sampling separates it from real beta.

The band edges below are stated here because this notebook has to stand alone
when downloaded. In the analysis app they are never written into code: they come
from `configs/bands.yaml`, and the test suite asserts that the values in this
notebook still match that file.""")

# ---------------------------------------------------------------- 11 task 3
task(
"""BETA_BAND_HZ = (13.0, 30.0)   # mirrors configs/bands.yaml -> bands.beta

def fold_harmonics(stim_hz: float, fs_hz: float, n_harmonics: int = 6) -> dict[int, float]:
    \"\"\"Where harmonics 1..n of `stim_hz` land once sampled at `fs_hz`.

    Returns {harmonic_number: aliased_frequency_hz}.
    \"\"\"
    # TODO: for each harmonic k in 1..n_harmonics, the true frequency is k * stim_hz
    # TODO: use alias_frequency to find where it lands
    # TODO: return a dict keyed by k
    raise NotImplementedError("Implement fold_harmonics")""",
"""BETA_BAND_HZ = (13.0, 30.0)   # mirrors configs/bands.yaml -> bands.beta

def fold_harmonics(stim_hz: float, fs_hz: float, n_harmonics: int = 6) -> dict[int, float]:
    \"\"\"Where harmonics 1..n of `stim_hz` land once sampled at `fs_hz`.

    Returns {harmonic_number: aliased_frequency_hz}.
    \"\"\"
    return {k: alias_frequency(k * stim_hz, fs_hz) for k in range(1, n_harmonics + 1)}""")

# ---------------------------------------------------------------- 12 test 3
code("""# --- TEST CELL FOR STEP 3 ---
FS_SENSE = 250.0
lo, hi = BETA_BAND_HZ

contaminating = {}
print(f"Sampling at {FS_SENSE:.0f} Hz. Beta band is {lo:.0f} to {hi:.0f} Hz.\\n")
print(f"{'stim (Hz)':>10} " + " ".join(f"{'h'+str(k):>7}" for k in range(1, 7)) + "   verdict")
for stim in [130.0, 135.0, 140.0, 145.0, 160.0, 180.0]:
    folded = fold_harmonics(stim, FS_SENSE)
    hits = [k for k, f in folded.items() if lo <= f <= hi]
    if hits:
        contaminating[stim] = hits
    row = " ".join(f"{folded[k]:>7.1f}" for k in range(1, 7))
    verdict = f"beta hit via h{hits[0]}" if hits else "clear of beta"
    print(f"{stim:>10.1f} {row}   {verdict}")

# The worked example from the text, verified rather than asserted.
assert fold_harmonics(135.0, 250.0)[2] == 20.0
assert 135.0 in contaminating
print("\\nStep 3 passed. Stimulation frequencies whose harmonics land in beta at "
      f"{FS_SENSE:.0f} Hz: {sorted(contaminating)}")
print("Every one of these is a clinically ordinary setting.")""")

# ---------------------------------------------------------------- 13 md
md(r"""---

## 5. The anti-alias filter, and why usable bandwidth is below Nyquist

Nothing above removes energy. Decimation has to, before it throws samples away,
which is what an anti-alias filter is for. `scipy.signal.decimate` and MATLAB's
`decimate` both apply one, and both place its cutoff at a fraction of the **new**
Nyquist rather than at the new Nyquist itself, because a real filter needs a
transition band in which to fall.

That fraction is 0.8 in both. So after decimating to $f_s'$:

$$\text{Nyquist} = \frac{f_s'}{2}
\qquad
\text{usable bandwidth} = 0.8 \times \frac{f_s'}{2} = 0.4\, f_s'$$

Decimate to 1000 Hz and your Nyquist is 500 Hz, but your data supports 400 Hz.
The 100 Hz between them is not empty. It is attenuated by an amount you did not
record and cannot state, which is worse than empty, because a spectrum will
happily plot values there.

This is the number guardrail **G6** checks. G6 refuses a run whose requested
bands reach above it, and its severity is `block`, because unlike most guardrails
there is no version of this that a reviewer can reason their way past: the
content is gone.""")

# ---------------------------------------------------------------- 14 task 4
task(
"""ANTIALIAS_CUTOFF_FRACTION = 0.8   # scipy and MATLAB both use this

def usable_bandwidth_hz(sfreq_hz: float,
                        cutoff_fraction: float = ANTIALIAS_CUTOFF_FRACTION) -> float:
    \"\"\"Highest frequency the data supports after anti-alias filtering.

    Production equivalent: `dbsspeech.preprocess.resample.usable_bandwidth_hz`,
    which is this function and is what guardrail G6 reads. The decimation itself
    is `scipy.signal.decimate`.
    \"\"\"
    # TODO: Nyquist is sfreq_hz / 2
    # TODO: the filter cutoff sits at cutoff_fraction of that
    raise NotImplementedError("Implement usable_bandwidth_hz")""",
"""ANTIALIAS_CUTOFF_FRACTION = 0.8   # scipy and MATLAB both use this

def usable_bandwidth_hz(sfreq_hz: float,
                        cutoff_fraction: float = ANTIALIAS_CUTOFF_FRACTION) -> float:
    \"\"\"Highest frequency the data supports after anti-alias filtering.

    Production equivalent: `dbsspeech.preprocess.resample.usable_bandwidth_hz`,
    which is this function and is what guardrail G6 reads. The decimation itself
    is `scipy.signal.decimate`.
    \"\"\"
    return float(sfreq_hz / 2.0 * cutoff_fraction)""")

# ---------------------------------------------------------------- 15 test 4
code("""# --- TEST CELL FOR STEP 4: MEASURE THE FILTER, DO NOT TRUST THE FORMULA ---
# Build probe tones across the new Nyquist, decimate, and measure what survives.

FS_RAW = 24000.0
FACTOR = 24
FS_NEW = FS_RAW / FACTOR                 # 1000 Hz
usable = usable_bandwidth_hz(FS_NEW)     # 400 Hz
assert usable == 400.0

seconds = 2.0
t_raw = np.arange(int(FS_RAW * seconds)) / FS_RAW

def surviving_amplitude(probe_hz):
    raw = np.sin(2 * np.pi * probe_hz * t_raw)
    small = decimate(raw, FACTOR, ftype='iir', zero_phase=True)
    t_new = np.arange(len(small)) / FS_NEW
    ref = np.exp(-2j * np.pi * probe_hz * t_new)
    edge = len(small) // 10                       # discard filter edge transients
    return float(2 * np.abs(np.mean(small[edge:-edge] * ref[edge:-edge])))

print(f"Raw {FS_RAW:.0f} Hz, decimated by {FACTOR} to {FS_NEW:.0f} Hz")
print(f"Nyquist after decimation : {FS_NEW/2:.0f} Hz")
print(f"Usable bandwidth (G6)    : {usable:.0f} Hz\\n")
print(f"{'probe (Hz)':>11} {'surviving amplitude':>20}")
survival = {}
for probe in [50.0, 200.0, 350.0, 400.0, 450.0, 490.0]:
    survival[probe] = surviving_amplitude(probe)
    print(f"{probe:>11.0f} {survival[probe]:>20.3f}")

assert survival[50.0] > 0.95, "content well inside the band must survive intact"
assert survival[490.0] < 0.5, "content between usable bandwidth and Nyquist must not"
print("\\nStep 4 passed. Between 400 and 500 Hz the data is neither present nor")
print("absent, it is attenuated by an unstated amount. That is what G6 refuses.")""")

# ---------------------------------------------------------------- 16 md
md(r"""---

## 6. What you established

1. Aliasing is a deterministic relabelling, not noise, and it is irreversible.
   You proved this by showing the sample sequences are identical, not by
   inspecting a picture.
2. A converter's bit depth is a statement about a full-scale signal. Your signal
   gets $N + \log_2(A/V_{FS})$ bits, which for intraoperative LFP beside a
   stimulation artifact is a serious loss.
3. Ordinary clinical stimulation settings, sampled at ordinary implanted-device
   rates, place stimulation harmonics inside the beta band. This is arithmetic,
   it is not avoidable downstream, and it is why a beta biomarker that tracks
   stimulation amplitude deserves suspicion before it deserves a paper.
4. Usable bandwidth after decimation is $0.4 f_s'$, not $0.5 f_s'$, and guardrail
   G6 blocks on the difference.

### Exercises

**Exercise 1.** `suggest_factor` in `preprocess/resample.py` returns the largest
integer factor reaching a target rate. Take a 24414 Hz recording and a 1000 Hz
target. Compute the factor, the resulting rate, and the usable bandwidth. Then
decide whether a high-gamma analysis at 70 to 150 Hz survives it, and whether
your answer changes if the target is 500 Hz.

**Exercise 2.** Section 4 used the second harmonic. Write a search over
stimulation frequencies from 100 to 200 Hz in 1 Hz steps and sampling rates in
{200, 250, 422, 500, 1000} Hz, and report every pair for which any harmonic up to
the sixth lands inside beta. Which sampling rate is safest, and is the safest one
safe for every stimulation frequency or only for the common ones?

**Exercise 3.** The uniform-error model behind $6.02N + 1.76$ assumes the
quantization error is uncorrelated with the signal. Construct a signal for which
that assumption fails badly, measure the real SNR, and explain what the model
missed. A sinusoid at an exact submultiple of the sampling rate is a good start.

---

**Next: SIG 2, filtering and zero-phase distortion.** The anti-alias filter used in
Section 5 was applied with `zero_phase=True`. SIG 2 asks what that flag actually
does, what it costs, and why a causal filter would have moved every latency
reported by this app.
""")

# ------------------------------------------------------------------ emit
VARIANT_TAG = {"student": "[STUDENT WORKBOOK]", "solutions": "[SOLUTIONS GUIDE]"}
INSTRUCTIONS = {
    "student": (
        "> **STUDENT INSTRUCTIONS.** Each task cell raises `NotImplementedError`.\n"
        "> Replace the `TODO` comments with an implementation, then run the test cell\n"
        "> that follows it. Every test cell verifies your work against something\n"
        "> independent of your implementation, so passing it means the result is\n"
        "> right rather than self-consistent. Work the cells in order: later sections\n"
        "> use the functions you write earlier.\n"
    ),
    "solutions": (
        "> **SOLUTIONS GUIDE.** Reference implementations, with the same test cells\n"
        "> the student workbook uses. This file is executed in CI by\n"
        "> `tests/unit/test_curriculum.py`, so every number below is verified on\n"
        "> every commit.\n"
    ),
}


def build(which: str) -> dict:
    cells = []
    for kind, student_src, solution_src in CELLS:
        src = solution_src if (which == "solutions" and solution_src) else student_src
        src = src.replace("{{VARIANT}}", VARIANT_TAG[which])
        src = src.replace("{{INSTRUCTIONS}}", INSTRUCTIONS[which])
        cell = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            cell["execution_count"] = None
            cell["outputs"] = []
        cells.append(cell)
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }

# Repository root, found from this file rather than hard-coded.
BASE = pathlib.Path(__file__).resolve().parents[2]
for which in ("student", "solutions"):
    nb = build(which)
    name = f"01_sampling_nyquist_aliasing_{which}.ipynb"
    for d in (BASE / "curriculum" / "02_dsp", BASE / "web" / "public" / "notebooks"):
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(nb, indent=1) + "\n")
    print(f"wrote {name} ({len(nb['cells'])} cells)")
