import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("02_dsp", "05_morlet_wavelets")

m.md(r'''# Lesson SIG 5: Complex Morlet Wavelets and the Time-Frequency Trade {{VARIANT}}

**Foundations · Signal Processing for Neural Time Series**

{{INSTRUCTIONS}}

SIG 4 estimated one spectrum for a whole record. Intraoperative recordings are not
stationary: a beta burst starts and stops, and a spectrum averaged over the whole
epoch says nothing about when. This module builds a spectrum that changes with
time, and finds that SIG 3's resolution trade returns in a sharper form, as a
trade between knowing **when** and knowing **what frequency**.

**What it assumes**

| From | What is used |
|---|---|
| SIG 2 | Convolution, and that a narrow filter rings for many cycles. |
| SIG 3 | The DFT, that resolution is $1/T$, and the effect of a taper. |
| SIG 4 | That an estimator has variance, and that resolution is bought. |

**What it underwrites**

The `tfr_onset` recipe, and guardrail **G5**, time-frequency window too long for
the effect. Section 3 computes the number G5 compares against.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(5)
FS = 1000.0
print("Environment initialized for Lesson SIG 5")''')

m.md(r'''---

## 1. The wavelet is a windowed complex exponential

A complex Morlet wavelet at centre frequency $f_0$ is a complex sinusoid
multiplied by a Gaussian envelope:

$$\psi(t) = e^{2\pi i f_0 t}\, e^{-t^2 / 2\sigma_t^2}$$

Two choices define it. The sinusoid decides which frequency the wavelet responds
to. The Gaussian width $\sigma_t$ decides over how long a stretch of signal it
looks, and it is conventionally set through the number of cycles:

$$\sigma_t = \frac{n_{\text{cycles}}}{2\pi f_0}$$

Because the wavelet is complex, convolving a signal with it returns a complex
time series whose magnitude is an amplitude envelope at $f_0$ and whose argument
is a phase. That is why one convolution gives both, and it is why SIG 6's Hilbert
transform will turn out to be the same idea in different clothing.

Note what $n_{\text{cycles}}$ being fixed across frequencies implies:
$\sigma_t \propto 1/f_0$, so a wavelet bank looks at high frequencies over a
short window and low frequencies over a long one. That is usually what you want,
and it is never what a fixed-length Fourier window does.''')

m.task(
'''def morlet_wavelet(freq_hz: float, n_cycles: float, fs: float) -> np.ndarray:
    """Complex Morlet wavelet, unit energy, spanning +/- 3 sigma.

    Production equivalent: `mne.time_frequency.morlet`, and
    `scipy.signal.morlet2`.
    """
    # TODO: sigma_t = n_cycles / (2 * pi * freq_hz)
    # TODO: build a time vector from -3*sigma_t to +3*sigma_t at 1/fs spacing
    # TODO: wavelet = exp(2j*pi*freq_hz*t) * exp(-t**2 / (2*sigma_t**2))
    # TODO: normalise to unit energy: divide by sqrt(sum(|w|**2))
    raise NotImplementedError("Implement morlet_wavelet")''',
'''def morlet_wavelet(freq_hz: float, n_cycles: float, fs: float) -> np.ndarray:
    """Complex Morlet wavelet, unit energy, spanning +/- 3 sigma.

    Production equivalent: `mne.time_frequency.morlet`, and
    `scipy.signal.morlet2`.
    """
    sigma_t = n_cycles / (2.0 * np.pi * freq_hz)
    half = int(np.ceil(3.0 * sigma_t * fs))
    t = np.arange(-half, half + 1) / fs
    w = np.exp(2j * np.pi * freq_hz * t) * np.exp(-(t ** 2) / (2.0 * sigma_t ** 2))
    return w / np.sqrt(np.sum(np.abs(w) ** 2))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
w20 = morlet_wavelet(20.0, 7.0, FS)

assert np.iscomplexobj(w20), "a Morlet wavelet is complex; that is the point"
assert np.isclose(np.sum(np.abs(w20) ** 2), 1.0), "unit energy"

# It responds at its own frequency and nowhere else. Check by scanning tones.
def response(wav, probe_hz, fs=FS):
    n = np.arange(4000)
    tone = np.exp(2j * np.pi * probe_hz * n / fs)
    return float(np.abs(np.convolve(tone, wav, mode='valid')).mean())

probes = np.arange(5.0, 41.0, 1.0)
resp = np.array([response(w20, p) for p in probes])
peak_hz = float(probes[int(np.argmax(resp))])
print(f"peak response of a 20 Hz, 7-cycle wavelet: {peak_hz:.0f} Hz")
assert peak_hz == 20.0, "the wavelet must respond at its centre frequency"

# Width scales with 1/f0 at fixed cycles, which is the whole design.
print(f"\\n{'freq':>6} {'sigma_t (ms)':>14} {'support (ms)':>14}")
for f0 in (5.0, 20.0, 80.0):
    wav = morlet_wavelet(f0, 7.0, FS)
    print(f"{f0:>5.0f}  {1000 * 7.0 / (2 * np.pi * f0):>13.1f} {1000 * len(wav) / FS:>13.1f}")
assert len(morlet_wavelet(5.0, 7.0, FS)) > 10 * len(morlet_wavelet(80.0, 7.0, FS)), \\
    "at fixed cycles a low-frequency wavelet spans a much longer stretch of signal"
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The trade is a theorem, not a tuning parameter

The Gaussian envelope has width $\sigma_t$ in time. Its Fourier transform is
another Gaussian, of width

$$\sigma_f = \frac{1}{2\pi\sigma_t} = \frac{f_0}{n_{\text{cycles}}}$$

so the product is fixed:

$$\sigma_t\,\sigma_f = \frac{1}{2\pi}$$

This is the Gabor limit. It is not a property of Morlet wavelets and cannot be
improved by a better choice of window: the Gaussian is the function that
**attains** it, and every other window does worse. Raising
$n_{\text{cycles}}$ buys frequency precision and pays in time precision, at a
fixed exchange rate, forever.

So "which $n_{\text{cycles}}$" is not a preference. It is a statement about
whether you are asking when something happened or what frequency it was, and you
cannot have both beyond this bound.''')

m.task(
'''def resolutions(freq_hz: float, n_cycles: float) -> tuple:
    """Time and frequency resolution of a Morlet wavelet, as (sigma_t_s, sigma_f_hz).

    Use the standard conventions: sigma_t = n_cycles / (2*pi*f0), and
    sigma_f = 1 / (2*pi*sigma_t).
    """
    # TODO: compute sigma_t from n_cycles and freq_hz
    # TODO: compute sigma_f as its Fourier counterpart
    raise NotImplementedError("Implement resolutions")''',
'''def resolutions(freq_hz: float, n_cycles: float) -> tuple:
    """Time and frequency resolution of a Morlet wavelet, as (sigma_t_s, sigma_f_hz).

    Use the standard conventions: sigma_t = n_cycles / (2*pi*f0), and
    sigma_f = 1 / (2*pi*sigma_t).
    """
    sigma_t = n_cycles / (2.0 * np.pi * freq_hz)
    sigma_f = 1.0 / (2.0 * np.pi * sigma_t)
    return float(sigma_t), float(sigma_f)''')

m.code('''# --- TEST CELL FOR STEP 2 ---
# (a) The product is constant. Check across frequencies and cycle counts.
print(f"{'f0':>5} {'cycles':>7} {'sigma_t (ms)':>14} {'sigma_f (Hz)':>14} {'product':>10}")
for f0 in (10.0, 20.0, 60.0):
    for nc in (3.0, 7.0, 12.0):
        st, sf = resolutions(f0, nc)
        print(f"{f0:>5.0f} {nc:>7.0f} {1000*st:>13.1f} {sf:>14.2f} {st*sf:>10.5f}")
        assert np.isclose(st * sf, 1 / (2 * np.pi)), "the Gabor product is fixed at 1/2pi"

# (b) Measure it rather than trusting the formula: build the wavelet and read its
# actual spectral width off the FFT.
for f0, nc in ((20.0, 7.0), (20.0, 3.0), (60.0, 7.0)):
    wav = morlet_wavelet(f0, nc, FS)
    n_fft = 1 << 15
    # The wavelet is complex, so use the full FFT and keep the positive half.
    spec = np.abs(np.fft.fft(wav, n=n_fft))
    all_freqs = np.fft.fftfreq(n_fft, 1 / FS)
    keep = all_freqs >= 0
    mag, freqs = spec[keep], all_freqs[keep]
    half_max = mag > 0.5 * mag.max()
    fwhm = freqs[half_max][-1] - freqs[half_max][0]
    predicted_fwhm = 2 * np.sqrt(2 * np.log(2)) * resolutions(f0, nc)[1]
    print(f"\\nf0={f0:.0f} Hz, {nc:.0f} cycles: measured FWHM {fwhm:.2f} Hz, "
          f"predicted {predicted_fwhm:.2f} Hz")
    assert abs(fwhm - predicted_fwhm) / predicted_fwhm < 0.12, \\
        "the measured spectral width must match sigma_f"

# (c) No window beats the Gaussian. Compare against a boxcar of the same duration.
wav = morlet_wavelet(20.0, 7.0, FS)
box = np.exp(2j * np.pi * 20.0 * np.arange(len(wav)) / FS)
box = box / np.sqrt(np.sum(np.abs(box) ** 2))
def spectral_sigma(kernel):
    n_fft = 1 << 15
    spec = np.abs(np.fft.fft(kernel, n=n_fft)) ** 2
    all_fr = np.fft.fftfreq(n_fft, 1 / FS)
    keep = all_fr >= 0
    mag, fr = spec[keep], all_fr[keep]
    mag = mag / mag.sum()
    mean = np.sum(fr * mag)
    return float(np.sqrt(np.sum((fr - mean) ** 2 * mag)))
print(f"\\nsame duration, spectral sigma: Gaussian {spectral_sigma(wav):.3f} Hz, "
      f"boxcar {spectral_sigma(box):.3f} Hz")
assert spectral_sigma(wav) < spectral_sigma(box), \\
    "the Gaussian attains the Gabor bound; a boxcar of equal length does worse"
print("\\nStep 2 passed. The trade is a bound, not a knob you can out-engineer.")''')

m.md(r'''---

## 3. What this costs an onset claim, which is guardrail G5

The `tfr_onset` recipe reports when a response begins. SIG 2 showed that a causal
filter delays that estimate. A wavelet is applied non-causally, so it does not
delay the onset, but it **smears** it: a burst that started instantaneously is
reported as ramping up over roughly $\sigma_t$ either side.

At 20 Hz with 7 cycles, $\sigma_t$ is 56 ms. A burst lasting 100 ms is therefore
being measured with a ruler longer than the thing it measures, and its apparent
duration is set by the wavelet rather than by the brain.

That is guardrail G5, stated exactly: refuse when the analysis window is long
compared with the effect. Below, the wavelet's own smearing is measured against a
burst of known length.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def wavelet_power(x, f0, n_cycles, fs=FS):
    wav = morlet_wavelet(f0, n_cycles, fs)
    return np.abs(np.convolve(x, wav, mode='same')) ** 2

def measured_duration_ms(power, frac=0.5):
    above = power > frac * power.max()
    idx = np.flatnonzero(above)
    return 1000.0 * (idx[-1] - idx[0]) / FS if len(idx) > 1 else 0.0

t = np.arange(3000) / FS
TRUE_MS = 100.0
burst = np.zeros(3000)
on = (t >= 1.0) & (t < 1.0 + TRUE_MS / 1000.0)
burst[on] = np.sin(2 * np.pi * 20.0 * t[on])

print(f"true burst duration: {TRUE_MS:.0f} ms\\n")
print(f"{'cycles':>7} {'sigma_t (ms)':>14} {'measured duration':>19} {'overestimate':>14}")
meas = {}
for nc in (3.0, 5.0, 7.0, 12.0):
    st, _ = resolutions(20.0, nc)
    d = measured_duration_ms(wavelet_power(burst, 20.0, nc))
    meas[nc] = d
    print(f"{nc:>7.0f} {1000*st:>13.1f} {d:>16.0f} ms {d/TRUE_MS:>13.2f}x")

assert meas[12.0] > meas[3.0], "more cycles smears a short burst more"
assert meas[12.0] > 1.5 * TRUE_MS, "12 cycles at 20 Hz cannot measure a 100 ms burst"
assert meas[3.0] < 1.5 * TRUE_MS, "3 cycles can, at the cost of frequency precision"

# The G5 rule, made arithmetic: the wavelet must be short relative to the effect.
print(f"\\n{'cycles':>7} {'2*sigma_t (ms)':>16} {'vs 100 ms burst':>18}")
for nc in (3.0, 7.0, 12.0):
    st, _ = resolutions(20.0, nc)
    ratio = 2000.0 * st / TRUE_MS
    verdict = "usable" if ratio < 1.0 else "REFUSE, ruler longer than the object"
    print(f"{nc:>7.0f} {2000*st:>15.1f} {verdict:>40}")
assert 2000 * resolutions(20.0, 12.0)[0] > TRUE_MS, "G5 must refuse the 12-cycle case"
print("\\nStep 3 passed. The reported duration of a short burst is a property of the")
print("wavelet, not of the brain, unless the wavelet is shorter than the burst.")''')

m.md(r'''---

## 4. What you established

1. A complex Morlet wavelet is a Gaussian-windowed complex exponential. Because
   it is complex, one convolution returns an amplitude and a phase.
2. $\sigma_t\sigma_f = 1/2\pi$ exactly, verified analytically and then measured
   off the wavelet's own spectrum to within 12 percent. A boxcar of the same
   duration does strictly worse, because the Gaussian attains the bound.
3. At fixed $n_{\text{cycles}}$ the wavelet is short at high frequencies and long
   at low ones, which a fixed Fourier window never is.
4. A 100 ms burst measured with a 12-cycle wavelet at 20 Hz is reported as
   lasting far longer than it did, because $2\sigma_t$ exceeds the burst. That
   comparison is guardrail G5, and it is arithmetic rather than judgement.

### Exercises

**Exercise 1.** Beta bursts are reported in the literature with durations from
about 50 to 500 ms. For each of 3, 7 and 12 cycles at 20 Hz, find the shortest
burst whose duration you could report honestly. Then say what that implies about
comparing burst durations between two papers that used different cycle counts.

**Exercise 2.** Some analyses vary $n_{\text{cycles}}$ with frequency, for
example from 3 at 4 Hz to 10 at 100 Hz. Work out $\sigma_t$ and $\sigma_f$ across
that range and explain what is being held roughly constant, and why that might be
preferable to a fixed cycle count.

**Exercise 3.** Section 3 measured duration at half maximum. Repeat it at a
threshold of 0.1 and of 0.9 of maximum. How much of a reported burst duration is
a property of the threshold rather than of the signal?

---

**Next: SIG 6, the Hilbert transform.** A wavelet gives amplitude and phase at one
frequency by convolving with a complex kernel. SIG 6 gets the same two quantities a
different way, and the comparison exposes exactly what "instantaneous frequency"
can and cannot mean.
''')

m.emit()
verify("02_dsp", "05_morlet_wavelets")
print("  SIG 5 OK")
