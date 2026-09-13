"""Generate the SIG 2 student and solutions notebooks from one source."""
from __future__ import annotations

import json
import pathlib

CELLS: list[tuple[str, str, str | None]] = []
def md(s): CELLS.append(("markdown", s, None))
def code(s): CELLS.append(("code", s, None))
def task(stu, sol): CELLS.append(("code", stu, sol))

md(r"""# Lesson SIG 2: Filtering and Zero-Phase Distortion {{VARIANT}}

**Foundations · Signal Processing for Neural Time Series**

{{INSTRUCTIONS}}

SIG 1 ended by decimating a recording and measuring what its anti-alias filter
removed. It used `scipy.signal.decimate(..., zero_phase=True)` and discarded ten
percent of each end of the result without saying why. This module is that debt.

Everything here builds on SIG 1 and nothing else: sampling rate, Nyquist, and the
idea that a filter has a cutoff below the new Nyquist. No linear algebra from
Linear Algebra is required.

**What you will be able to do**

- Write both filter families as difference equations and run them by hand
- Measure group delay rather than assume it, and say what a causal filter does
  to a reported latency
- Explain what zero-phase filtering buys, and the three things it costs
- Recognise an oscillation that a filter manufactured out of a transient

**What this underwrites in the analysis app**

- Every latency this app reports. `tfr_onset` defines onset from filtered data,
  and a causal filter would move every one of those numbers.
- Guardrail **G5**, time-frequency window too long for the effect. Section 5
  shows where the spurious rhythm it guards against comes from.
""")

code("""import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, freqz, lfilter

np.random.seed(42)
FS = 1000.0   # Hz, the rate SIG 1 decimated to
print("Environment initialized for Lesson SIG 2")""")

md(r"""---

## 1. A filter is a difference equation

Every linear filter in this course computes each output sample from a weighted
sum of recent inputs and, sometimes, recent outputs:

$$y[n] = \underbrace{\sum_{k=0}^{M-1} b_k\, x[n-k]}_{\text{feed-forward}}
        \; - \; \underbrace{\sum_{k=1}^{N-1} a_k\, y[n-k]}_{\text{feedback}}$$

With no feedback ($N=1$) the impulse response has finite length $M$, giving a
**FIR** filter. With feedback the impulse response never exactly reaches zero,
giving an **IIR** filter. IIR filters reach a given sharpness with far fewer
coefficients, which is why `scipy.signal.decimate` used a Chebyshev IIR filter in
SIG 1, and they are the reason phase becomes a problem later in this notebook.

Taking the $z$-transform of both sides gives the frequency response

$$H(e^{j\omega}) = \frac{\sum_k b_k e^{-j\omega k}}{1 + \sum_k a_k e^{-j\omega k}}$$

whose magnitude tells you what each frequency is scaled by, and whose phase tells
you what each frequency is delayed by. Almost everyone reads the magnitude plot
and ignores the phase plot. The phase plot is where the latency errors live.""")

task(
'''def apply_fir(x: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Run the FIR difference equation y[n] = sum_k b[k] * x[n-k].

    Same length as `x`. Samples before the start of the signal count as zero.

    Production equivalent: `scipy.signal.lfilter(b, [1.0], x)`, and for long
    signals `scipy.signal.oaconvolve`, which does this by FFT.
    """
    # TODO: allocate an output array of the same length as x
    # TODO: for each output index n, sum b[k] * x[n - k] over k, skipping n - k < 0
    # TODO: return the result
    raise NotImplementedError("Implement apply_fir")''',
'''def apply_fir(x: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Run the FIR difference equation y[n] = sum_k b[k] * x[n-k].

    Same length as `x`. Samples before the start of the signal count as zero.

    Production equivalent: `scipy.signal.lfilter(b, [1.0], x)`, and for long
    signals `scipy.signal.oaconvolve`, which does this by FFT.
    """
    y = np.zeros(len(x), dtype=float)
    for n in range(len(x)):
        acc = 0.0
        for k in range(len(b)):
            if n - k >= 0:
                acc += b[k] * x[n - k]
        y[n] = acc
    return y''')

code("""# --- TEST CELL FOR STEP 1: TWO INDEPENDENT REFERENCES ---
# (a) against convolution, which is the definition of what a FIR filter does
# (b) against the analytic frequency response, measured tone by tone

rng = np.random.default_rng(0)
x_test = rng.standard_normal(200)
b_test = np.array([0.2, -0.5, 0.31, 0.04])

assert np.allclose(apply_fir(x_test, b_test), np.convolve(x_test, b_test)[:len(x_test)]), \\
    "apply_fir must equal truncated convolution"

# Measured gain at a tone must match |H| from the coefficients alone.
n = np.arange(4000)
print(f"{'probe (Hz)':>11} {'measured gain':>14} {'analytic |H|':>13}")
for probe in (20.0, 60.0, 150.0, 300.0):
    tone = np.sin(2 * np.pi * probe * n / FS)
    out = apply_fir(tone, b_test)[500:]          # discard the start-up transient
    measured = np.sqrt(2.0 * np.mean(out ** 2))  # RMS -> amplitude for a sinusoid
    w, h = freqz(b_test, [1.0], worN=[2 * np.pi * probe / FS])
    analytic = float(np.abs(h[0]))
    print(f"{probe:>11.0f} {measured:>14.4f} {analytic:>13.4f}")
    assert np.isclose(measured, analytic, rtol=1e-3), \\
        f"gain at {probe} Hz: measured {measured:.4f}, analytic {analytic:.4f}"

print("\\nStep 1 passed: the implementation matches convolution and the analytic response.")""")

md(r"""---

## 2. Phase, and the delay nobody plots

A filter delays different frequencies by different amounts. The delay applied to
the envelope of a narrowband signal centred at $\omega$ is the **group delay**

$$\tau_g(\omega) = -\frac{d\,\angle H(e^{j\omega})}{d\omega}$$

Two cases matter.

A **symmetric FIR** filter, $b_k = b_{M-1-k}$, has phase exactly linear in
$\omega$, so $\tau_g$ is the same constant at every frequency:
$$\tau_g = \frac{M-1}{2}\ \text{samples}$$
Every frequency is delayed equally, so the waveform shape is preserved and the
whole thing shifts. That is correctable: subtract the known constant.

An **IIR** filter has no such symmetry. Its group delay varies with frequency,
and near the edges of a passband it peaks sharply. Nothing about the waveform is
preserved, and no single number corrects it.

Rather than trusting either claim, measure it. A delay between two signals is the
lag that maximises their cross-correlation.""")

task(
'''def measured_delay_samples(x: np.ndarray, y: np.ndarray) -> int:
    """Lag, in samples, that best aligns `y` with `x`.

    Positive means `y` lags `x`. Use full cross-correlation and take the lag at
    the maximum. Production equivalent: `scipy.signal.correlate` with
    `scipy.signal.correlation_lags`.
    """
    # TODO: cross-correlate y against x with np.correlate(..., mode='full')
    # TODO: the lag axis for mode='full' runs from -(len(x)-1) to +(len(y)-1)
    # TODO: return the lag at the maximum of the cross-correlation
    raise NotImplementedError("Implement measured_delay_samples")''',
'''def measured_delay_samples(x: np.ndarray, y: np.ndarray) -> int:
    """Lag, in samples, that best aligns `y` with `x`.

    Positive means `y` lags `x`. Use full cross-correlation and take the lag at
    the maximum. Production equivalent: `scipy.signal.correlate` with
    `scipy.signal.correlation_lags`.
    """
    xc = np.correlate(y - np.mean(y), x - np.mean(x), mode="full")
    lags = np.arange(-(len(x) - 1), len(y))
    return int(lags[int(np.argmax(xc))])''')

code("""# --- TEST CELL FOR STEP 2 ---
# (a) recover a delay that was constructed, so the ground truth is known exactly
sig = np.sin(2 * np.pi * 20 * np.arange(1000) / FS) * np.hanning(1000)
for true_shift in (0, 7, 23, 61):
    shifted = np.r_[np.zeros(true_shift), sig[:len(sig) - true_shift]]
    got = measured_delay_samples(sig, shifted)
    assert got == true_shift, f"constructed shift {true_shift}, measured {got}"

# (b) a symmetric FIR must show exactly (M-1)/2 samples, at EVERY frequency
b_ma = np.ones(21) / 21.0                      # M = 21, so tau_g = 10 samples
print(f"{'probe (Hz)':>11} {'measured delay':>15} {'predicted (M-1)/2':>19}")
for probe in (10.0, 20.0, 30.0):
    tone = np.sin(2 * np.pi * probe * np.arange(3000) / FS) * np.hanning(3000)
    delay = measured_delay_samples(tone, apply_fir(tone, b_ma))
    print(f"{probe:>11.0f} {delay:>15d} {(len(b_ma) - 1) // 2:>19d}")
    assert delay == (len(b_ma) - 1) // 2, f"linear phase must delay every frequency equally"

print("\\nStep 2 passed: a symmetric FIR delays all frequencies by the same constant.")""")

md(r"""---

## 3. What a causal filter does to a reported latency

This is not a stylistic concern. The `tfr_onset` recipe in this app reports when
a response begins, and onset is defined on filtered data. Filter causally and
every onset you report is late by the group delay at that band, which for a sharp
IIR filter is not a small number and is not the same across bands.

Below: a beta burst with a known onset, passed through a causal fourth-order
Butterworth bandpass. The onset is planted, so the truth is known and the error
is measured rather than argued.

Onset is read the way this app reads it, from an envelope: rectify, smooth, and
take the first crossing of a fraction of the peak. The smoother is the symmetric
FIR from Section 2, so its own delay is a known constant and gets subtracted.
Every tool here is one this notebook already built.""")

task(
'''def apply_iir(x: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Run the full difference equation, feedback included.

    y[n] = (sum_k b[k] x[n-k] - sum_{k>=1} a[k] y[n-k]) / a[0]

    Production equivalent: `scipy.signal.lfilter(b, a, x)`. For anything sharp,
    production code should use second-order sections (`sosfilt`) instead, because
    a high-order transfer function in this direct form is numerically fragile.
    """
    # TODO: allocate an output array of the same length as x
    # TODO: for each n, accumulate the feed-forward terms b[k] * x[n-k]
    # TODO: subtract the feedback terms a[k] * y[n-k] for k >= 1
    # TODO: divide by a[0] and store
    raise NotImplementedError("Implement apply_iir")''',
'''def apply_iir(x: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Run the full difference equation, feedback included.

    y[n] = (sum_k b[k] x[n-k] - sum_{k>=1} a[k] y[n-k]) / a[0]

    Production equivalent: `scipy.signal.lfilter(b, a, x)`. For anything sharp,
    production code should use second-order sections (`sosfilt`) instead, because
    a high-order transfer function in this direct form is numerically fragile.
    """
    y = np.zeros(len(x), dtype=float)
    for n in range(len(x)):
        acc = 0.0
        for k in range(len(b)):
            if n - k >= 0:
                acc += b[k] * x[n - k]
        for k in range(1, len(a)):
            if n - k >= 0:
                acc -= a[k] * y[n - k]
        y[n] = acc / a[0]
    return y''')

code("""# --- TEST CELL FOR STEP 3 ---
b_beta, a_beta = butter(4, [13.0, 30.0], btype='band', fs=FS)

# (a) against scipy's own implementation of the same recursion.
# Note the tolerance, and why it is not machine precision.
chk = np.random.default_rng(1).standard_normal(500)
ref_chk = lfilter(b_beta, a_beta, chk)
rel = np.max(np.abs(apply_iir(chk, b_beta, a_beta) - ref_chk)) / np.max(np.abs(ref_chk))
assert rel < 1e-5, f"apply_iir must match scipy.signal.lfilter, relative error {rel:.2e}"
print(f"apply_iir agrees with scipy.signal.lfilter to {rel:.1e} relative.")
print(f"Not to machine precision. This 8th-order response has poles at radius "
      f"{np.min(np.abs(np.roots(a_beta))):.3f} to {np.max(np.abs(np.roots(a_beta))):.3f}, "
      "so direct-form")
print("arithmetic is ill-conditioned and two correct implementations drift apart.")
print("That is exactly why production code uses second-order sections: scipy.signal.sosfilt.\\n")

# (b) the latency consequence, measured against a planted onset
duration = 3.0
t = np.arange(int(FS * duration)) / FS
onset_s = 1.0
envelope = (t >= onset_s) * (1 - np.exp(-(t - onset_s).clip(0) / 0.05))
burst = envelope * np.sin(2 * np.pi * 20 * t)

SMOOTHER = np.ones(51) / 51.0

def envelope_onset_ms(y, frac=0.25):
    # First crossing of `frac` of the peak envelope, in ms.
    # Rectify, smooth with the symmetric FIR from Section 2, then subtract that
    # smoother's own (M-1)/2 delay, which Section 2 established is a constant.
    env = apply_fir(np.abs(y), SMOOTHER)
    lag = (len(SMOOTHER) - 1) // 2
    env = np.r_[env[lag:], np.zeros(lag)]
    return 1000.0 * int(np.flatnonzero(env > frac * np.max(env))[0]) / FS

baseline = envelope_onset_ms(burst)
print(f"Planted onset                  : {onset_s * 1000:.0f} ms")
print(f"Measured on the unfiltered burst: {baseline:.0f} ms "
      f"({baseline - 1000:+.0f} ms, the envelope's own rise time)\\n")

print(f"{'band':>16} {'causal onset':>14} {'error vs truth':>16}")
causal_errors = {}
for lo, hi, label in [(13.0, 30.0, 'beta 13-30'), (18.0, 22.0, 'narrow 18-22')]:
    bb, aa = butter(4, [lo, hi], btype='band', fs=FS)
    got = envelope_onset_ms(apply_iir(burst, bb, aa))
    causal_errors[label] = got - 1000.0
    print(f"{label:>16} {got:>11.0f} ms {got - 1000.0:>13.0f} ms")

assert causal_errors['beta 13-30'] > 30.0, "a causal beta filter delays onset substantially"
assert causal_errors['narrow 18-22'] > causal_errors['beta 13-30'], \\
    "a narrower filter rings longer, so it delays onset more"

causal = apply_iir(burst, b_beta, a_beta)
print("\\nStep 3 passed. A causal filter cannot respond before its input, so every")
print("onset read through one is late, and by an amount that depends on the band.")""")

md(r"""---

## 4. Zero-phase filtering, and its three costs

Run the filter forwards, reverse the result, run it again, reverse back. The
delay incurred in the forward pass is undone exactly by the backward pass, so the
combined operation has **zero phase at every frequency**. That is what
`scipy.signal.filtfilt` does, and what `zero_phase=True` did in SIG 1.

It is not free.

1. **The magnitude response is squared.** Two passes of $H$ give $|H|^2$. A
   filter specified with a $-3$ dB cutoff delivers $-6$ dB there instead, so the
   effective passband is narrower than the one you asked for.
2. **The filter is non-causal.** Output at time $n$ depends on input after $n$.
   Harmless offline. Impossible in a closed loop, which is why adaptive DBS
   cannot use it and has to live with causal group delay.
3. **The edges are wrong.** The backward pass starts from the end of a finite
   record, so both ends carry a transient. `filtfilt` pads to reduce this, but
   padding is a guess about data you do not have. This is why SIG 1 discarded ten
   percent from each end before measuring.
4. **It can report an onset before the event.** This is the same non-causality as
   cost 2, but it is worth stating separately because it does not look like an
   error. The backward pass smears energy backwards in time, so a burst that
   began at $t$ produces envelope above threshold before $t$. Section 3 measured
   a causal filter arriving late. Below, the zero-phase filter on a narrow
   low-frequency band arrives *early*, which is not a smaller mistake than being
   late. It is a mistake that will survive review, because nobody checks whether
   a response preceded its stimulus.""")

task(
'''def zero_phase_filter(x: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Forward-backward filtering: filter, reverse, filter, reverse.

    Production equivalent: `scipy.signal.filtfilt`, which additionally pads the
    signal to soften the edge transients this simple version leaves in place.
    """
    # TODO: filter x forwards with apply_iir
    # TODO: reverse the result, filter it again, and reverse it back
    raise NotImplementedError("Implement zero_phase_filter")''',
'''def zero_phase_filter(x: np.ndarray, b: np.ndarray, a: np.ndarray) -> np.ndarray:
    """Forward-backward filtering: filter, reverse, filter, reverse.

    Production equivalent: `scipy.signal.filtfilt`, which additionally pads the
    signal to soften the edge transients this simple version leaves in place.
    """
    forward = apply_iir(x, b, a)
    backward = apply_iir(forward[::-1], b, a)
    return backward[::-1]''')

code("""# --- TEST CELL FOR STEP 4: TEST ALL THREE CLAIMS, NOT JUST THE HEADLINE ---
zp = zero_phase_filter(burst, b_beta, a_beta)

# Claim 1: zero phase at EVERY frequency, not just on average. Measure on steady
# tones across the passband, where the delay of the causal filter also varies.
print(f"{'probe (Hz)':>11} {'causal delay':>14} {'zero-phase delay':>18}")
tone_n = np.arange(2000)
for probe in (16.0, 20.0, 25.0):
    tone = np.sin(2 * np.pi * probe * tone_n / FS)
    d_causal = measured_delay_samples(tone, apply_iir(tone, b_beta, a_beta))
    d_zp = measured_delay_samples(tone, zero_phase_filter(tone, b_beta, a_beta))
    print(f"{probe:>11.0f} {d_causal:>11d} sa {d_zp:>15d} sa")
    assert d_zp == 0, f"forward-backward must have zero delay at {probe} Hz, got {d_zp}"

# And on the burst, the lag the causal filter introduced is gone.
causal_onset_err = envelope_onset_ms(causal) - 1000.0
zp_onset_err = envelope_onset_ms(zp) - 1000.0
print(f"\\nOnset error, causal     : {causal_onset_err:+.0f} ms")
print(f"Onset error, zero-phase : {zp_onset_err:+.0f} ms")
assert abs(zp_onset_err) < abs(causal_onset_err), "forward-backward must remove the lag"

# Claim 2: the magnitude response is SQUARED. Measure it, do not assume it.
print(f"\\n{'probe (Hz)':>11} {'single pass':>12} {'fwd-back':>10} {'single^2':>10}")
mid = slice(1000, 3000)
for probe in (20.0, 35.0, 45.0):
    tone = np.sin(2 * np.pi * probe * np.arange(4000) / FS)
    g1 = np.sqrt(2 * np.mean(apply_iir(tone, b_beta, a_beta)[mid] ** 2))
    g2 = np.sqrt(2 * np.mean(zero_phase_filter(tone, b_beta, a_beta)[mid] ** 2))
    print(f"{probe:>11.0f} {g1:>12.4f} {g2:>10.4f} {g1 ** 2:>10.4f}")
    assert np.isclose(g2, g1 ** 2, rtol=0.05), \\
        f"two passes must give |H|^2: got {g2:.4f}, expected {g1 ** 2:.4f}"

# Claim 3: the edges cannot be trusted. The burst above conveniently starts at
# zero, which hides this, so use a record that does not: continuous noise plus an
# ongoing rhythm, the shape real data actually has. Compare this unpadded version
# against scipy's filtfilt, which pads.
rng_edge = np.random.default_rng(3)
cont = (rng_edge.standard_normal(2000)
        + 3.0 * np.sin(2 * np.pi * 20 * np.arange(2000) / FS))
mine = zero_phase_filter(cont, b_beta, a_beta)
ref = filtfilt(b_beta, a_beta, cont)

def disagreement(sl):
    return float(np.max(np.abs(mine[sl] - ref[sl])) / np.sqrt(np.mean(ref[sl] ** 2)))

d_interior = disagreement(slice(500, 1500))
d_end = disagreement(slice(-50, None))
print("\\ndisagreement with scipy.filtfilt, as a fraction of local RMS:")
print(f"  interior         : {d_interior:>8.2%}")
print(f"  first 50 samples : {disagreement(slice(0, 50)):>8.2%}")
print(f"  last 50 samples  : {d_end:>8.2%}")
assert d_interior < 0.01, "the interior must agree, since the algorithm is identical"
assert d_end > 20 * d_interior, "the edges are where padding matters, and it matters a lot"
print("Same algorithm, same coefficients. The only difference is what each one")
print("assumed about the samples that do not exist beyond the end of the record.")
# Claim 4: zero-phase filtering can place an onset BEFORE the event.
print(f"\\n{'band':>16} {'causal':>10} {'zero-phase':>12}")
zp_errors = {}
for lo, hi, label in [(13.0, 30.0, 'beta 13-30'), (4.0, 8.0, 'theta 4-8')]:
    bb, aa = butter(4, [lo, hi], btype='band', fs=FS)
    e_causal = envelope_onset_ms(apply_iir(burst, bb, aa)) - 1000.0
    e_zp = envelope_onset_ms(zero_phase_filter(burst, bb, aa)) - 1000.0
    zp_errors[label] = e_zp
    print(f"{label:>16} {e_causal:>7.0f} ms {e_zp:>9.0f} ms")

assert zp_errors['theta 4-8'] < -50.0, \\
    "the theta zero-phase onset should land well before the burst actually started"
print("\\nThe theta row reports the burst starting before it started. The filter is")
print("non-causal, so it is allowed to, and no plot of the magnitude response shows it.")
print("\\nStep 4 passed: zero delay, squared magnitude, untrustworthy edges, and a")
print("filter that can put an effect before its cause.")""")

md(r"""---

## 5. The oscillation the filter invented

A narrow bandpass filter has a long, ringing impulse response, because a narrow
band in frequency is a long function in time. Feed it something with no rhythm at
all, such as a single step, and what comes out oscillates at the centre of the
passband and decays over several cycles.

This is not a subtle effect and it is not a bug. It is what the filter is for.
The danger is that the output is indistinguishable, by eye and by most burst
detectors, from a real beta burst. A movement artifact, an electrode touch, or a
stimulation onset is a step. Filter it into the beta band and it becomes a
"burst" with a plausible duration.

The narrower the filter, the longer the invented burst. That is the mechanism
guardrail **G5** exists to catch.""")

code("""step = np.zeros(1500)
step[750:] = 1.0
t_ms = (np.arange(len(step)) - 750) / FS * 1000.0

fig, axes = plt.subplots(3, 1, figsize=(11, 7), sharex=True)
axes[0].plot(t_ms, step, color='#171717', lw=1.8)
axes[0].set_title('Input: one step. No oscillation anywhere in it.', fontweight='bold')
axes[0].set_ylabel('Amplitude')

ring_cycles = {}
for ax, (lo, hi, label) in zip(axes[1:], [(13.0, 30.0, 'beta, 13 to 30 Hz'),
                                          (18.0, 22.0, 'narrow, 18 to 22 Hz')]):
    bb, aa = butter(4, [lo, hi], btype='band', fs=FS)
    rung = zero_phase_filter(step, bb, aa)
    ax.plot(t_ms, rung, color='#06b6d4', lw=1.8)
    peak = np.max(np.abs(rung))
    above = np.abs(rung) > 0.1 * peak
    span_ms = (np.flatnonzero(above)[-1] - np.flatnonzero(above)[0]) / FS * 1000.0
    ring_cycles[label] = span_ms * (lo + hi) / 2.0 / 1000.0
    ax.set_title(f'Filtered to {label}: rings for {span_ms:.0f} ms, '
                 f'about {ring_cycles[label]:.1f} cycles', fontweight='bold')
    ax.set_ylabel('Amplitude')

axes[-1].set_xlabel('Time relative to the step (ms)')
plt.tight_layout()
plt.show()

assert ring_cycles['narrow, 18 to 22 Hz'] > ring_cycles['beta, 13 to 30 Hz'], \\
    "a narrower passband must ring for more cycles"
print("A step contains no oscillation. Both traces above are artifacts of the filter.")
print(f"Narrowing the band from 17 Hz wide to 4 Hz wide grew the invented burst from "
      f"{ring_cycles['beta, 13 to 30 Hz']:.1f} to {ring_cycles['narrow, 18 to 22 Hz']:.1f} cycles.")""")

md(r"""---

## 6. What you established

1. FIR and IIR filters are the same difference equation with and without
   feedback, and you ran both by hand and checked them against `lfilter`.
2. A symmetric FIR delays every frequency by exactly $(M-1)/2$ samples. You
   measured that rather than assuming it.
3. A causal IIR bandpass over beta delays a burst by a measurable amount, and
   every onset reported through it is late by that amount. This is why
   `tfr_onset` matters more than it looks.
4. Forward-backward filtering removes the delay exactly, squares the magnitude
   response, cannot run in a closed loop, and leaves untrustworthy edges. You
   tested all four.
5. A narrow bandpass turns a step into a multi-cycle oscillation at the centre of
   its passband, and narrowing the band lengthens the invention.

### Exercises

**Exercise 1.** SIG 1 established that `scipy.signal.decimate` places its anti-alias
cutoff at $0.8 \times$ the new Nyquist. Take the Chebyshev filter it uses at a
decimation factor of 24 from 24 kHz, and measure its group delay across 1 to
400 Hz. Is it flat? What would using it causally do to a latency reported at
350 Hz compared with one reported at 10 Hz?

**Exercise 2.** Section 5 used a step. Replace it with a single one-sample
impulse and measure the ringing again. Then explain, in terms of the relationship
between passband width and impulse response length, why a burst detector run on
narrowband-filtered data reports durations that depend on the filter rather than
on the brain.

**Exercise 3.** Adaptive DBS cannot use `filtfilt`. Given the causal delay you
measured in Section 3, and a stimulation controller that updates every 100 ms,
what fraction of a control interval is spent waiting for the filter? Propose one
change to the filter design that reduces it, and state what you give up.

---

**Next: the preprocessing capstone.** It joins this module to SIG 1 and to the
montage algebra of Linear Algebra, and it walks
`src/dbsspeech/preprocess/` line by line: why re-referencing comes before
decimation, why decimation reports its usable bandwidth, and why an artifact
becomes an annotation instead of a deleted sample.
""")

VARIANT_TAG = {"student": "[STUDENT WORKBOOK]", "solutions": "[SOLUTIONS GUIDE]"}
INSTRUCTIONS = {
    "student": (
        "> **STUDENT INSTRUCTIONS.** Each task cell raises `NotImplementedError`.\n"
        "> Replace the `TODO` comments with an implementation, then run the test cell\n"
        "> that follows. Every test cell checks your work against something independent\n"
        "> of your implementation, so passing means the result is right rather than\n"
        "> merely self-consistent. Work the cells in order.\n"
    ),
    "solutions": (
        "> **SOLUTIONS GUIDE.** Reference implementations with the same test cells the\n"
        "> student workbook uses. Executed in CI by `tests/unit/test_curriculum.py`, so\n"
        "> every number below is verified on every commit.\n"
    ),
}

def build(which: str) -> dict:
    cells = []
    for kind, stu, sol in CELLS:
        src = sol if (which == "solutions" and sol) else stu
        src = src.replace("{{VARIANT}}", VARIANT_TAG[which]).replace("{{INSTRUCTIONS}}", INSTRUCTIONS[which])
        c = {"cell_type": kind, "metadata": {}, "source": src.splitlines(keepends=True)}
        if kind == "code":
            c["execution_count"] = None
            c["outputs"] = []
        cells.append(c)
    return {"cells": cells,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python", "version": "3.12"}},
            "nbformat": 4, "nbformat_minor": 5}

# Repository root, found from this file rather than hard-coded.
BASE = pathlib.Path(__file__).resolve().parents[2]
for which in ("student", "solutions"):
    nb = build(which)
    name = f"02_filtering_zero_phase_{which}.ipynb"
    for d in (BASE / "curriculum" / "02_dsp", BASE / "web" / "public" / "notebooks"):
        (d / name).write_text(json.dumps(nb, indent=1) + "\n")
    print(f"wrote {name} ({len(nb['cells'])} cells)")
