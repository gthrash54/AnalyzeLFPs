import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("02_dsp", "06_hilbert_instantaneous_features")

m.md(r'''# Lesson SIG 6: The Hilbert Transform and Instantaneous Features {{VARIANT}}

**Foundations · Signal Processing for Neural Time Series · final lesson**

{{INSTRUCTIONS}}

SIG 5 got an amplitude and a phase at one frequency by convolving with a complex
kernel. This module gets the same two quantities without choosing a centre
frequency at all, which sounds strictly better and is the source of the most
common misuse in the field.

The catch is in the word "instantaneous". It has a precise meaning, that meaning
requires the signal to be narrowband, and nothing in the arithmetic checks
whether it is.

**What it assumes**

| From | What is used |
|---|---|
| SIG 2 | Bandpass filtering, zero-phase filtering, and that a narrow filter rings. |
| SIG 3 | The DFT, and that a real signal has a conjugate-symmetric spectrum. |
| SIG 5 | That amplitude and phase come together from a complex representation. |

**What it underwrites**

Burst detection, which thresholds an envelope. Phase-amplitude coupling in Track
06, which needs a phase. And guardrail **G7**, which is about a band containing
something other than what you named it.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, hilbert as scipy_hilbert

rng = np.random.default_rng(6)
FS = 1000.0
print("Environment initialized for Lesson SIG 6")''')

m.md(r'''---

## 1. The analytic signal

A real signal has a conjugate-symmetric spectrum: $X[-k] = \overline{X[k]}$. The
negative frequencies carry no information the positive ones do not already have,
and their only role is to cancel the imaginary parts so the result comes out
real.

Delete them, and keep the energy the same by doubling what remains:

$$X_a[k] = \begin{cases}
X[0] & k = 0\\
2X[k] & 0 < k < N/2\\
X[N/2] & k = N/2\\
0 & k > N/2
\end{cases}$$

The inverse transform $x_a(t)$ is the **analytic signal**. Its real part is the
original, and its imaginary part is the Hilbert transform of the original, which
is the same signal with every frequency component shifted by $-90$ degrees.

Written in polar form, $x_a(t) = A(t)e^{i\phi(t)}$, it hands you an envelope and
a phase for free. That is exactly what SIG 5's wavelet produced, with one difference
that decides everything below: the wavelet chose a frequency band, and this does
not.''')

m.task(
'''def analytic_signal(x: np.ndarray) -> np.ndarray:
    """Analytic signal of a real 1-D array, via the FFT.

    Production equivalent: `scipy.signal.hilbert`, which does exactly this.
    """
    # TODO: N = len(x); take the full FFT
    # TODO: build a multiplier h that is 1 at DC, 2 for positive frequencies,
    #       0 for negative ones, and 1 at Nyquist when N is even
    # TODO: return the inverse FFT of X * h
    raise NotImplementedError("Implement analytic_signal")''',
'''def analytic_signal(x: np.ndarray) -> np.ndarray:
    """Analytic signal of a real 1-D array, via the FFT.

    Production equivalent: `scipy.signal.hilbert`, which does exactly this.
    """
    N = len(x)
    X = np.fft.fft(x)
    h = np.zeros(N)
    if N % 2 == 0:
        h[0] = 1.0
        h[N // 2] = 1.0
        h[1:N // 2] = 2.0
    else:
        h[0] = 1.0
        h[1:(N + 1) // 2] = 2.0
    return np.fft.ifft(X * h)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
x1 = rng.standard_normal(2048)
xa = analytic_signal(x1)

# (a) The real part must be the original signal. That is the defining property.
assert np.allclose(np.real(xa), x1, atol=1e-9), "the real part must be the input"

# (b) The spectrum must be one-sided. Check the negative half is gone.
Xa = np.fft.fft(xa)
neg = np.abs(Xa[len(x1) // 2 + 1:])
assert np.max(neg) < 1e-9 * np.max(np.abs(Xa)), "negative frequencies must be removed"
print(f"largest surviving negative-frequency component: {np.max(neg):.2e}")

# (c) Only now, against scipy.
assert np.allclose(xa, scipy_hilbert(x1), atol=1e-9), "must agree with scipy.signal.hilbert"

# (d) On a pure tone, the envelope is flat and the phase advances linearly.
t = np.arange(4000) / FS
tone = 3.0 * np.sin(2 * np.pi * 20.0 * t)
env = np.abs(analytic_signal(tone))
mid = slice(500, 3500)
print(f"\\nenvelope of a constant 3.0 amplitude tone: mean {env[mid].mean():.4f}, "
      f"sd {env[mid].std():.2e}")
assert np.isclose(env[mid].mean(), 3.0, rtol=1e-3), "the envelope must read the amplitude"
assert env[mid].std() < 1e-6, "and it must be flat for a constant tone"
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Envelope, phase, and instantaneous frequency

From $x_a = Ae^{i\phi}$:

$$A(t) = |x_a(t)|, \qquad \phi(t) = \arg x_a(t), \qquad
f_{\text{inst}}(t) = \frac{1}{2\pi}\frac{d\phi}{dt}$$

The envelope is what burst detection thresholds. The phase is what
phase-amplitude coupling correlates against. The instantaneous frequency is the
one that causes trouble.

Unwrapping is required before differentiating, because $\arg$ returns values in
$(-\pi,\pi]$ and a real phase advances without bound. That is mechanical. The
trouble is conceptual and comes next.''')

m.task(
'''def envelope(x: np.ndarray) -> np.ndarray:
    """Amplitude envelope. Production equivalent: np.abs(scipy.signal.hilbert(x))."""
    # TODO: magnitude of the analytic signal
    raise NotImplementedError("Implement envelope")


def instantaneous_phase(x: np.ndarray) -> np.ndarray:
    """Unwrapped instantaneous phase in radians."""
    # TODO: unwrap the argument of the analytic signal
    raise NotImplementedError("Implement instantaneous_phase")


def instantaneous_frequency(x: np.ndarray, fs: float) -> np.ndarray:
    """Instantaneous frequency in Hz, from the phase derivative.

    Returns an array one sample shorter than `x`.
    """
    # TODO: differentiate the unwrapped phase and scale by fs / (2 * pi)
    raise NotImplementedError("Implement instantaneous_frequency")''',
'''def envelope(x: np.ndarray) -> np.ndarray:
    """Amplitude envelope. Production equivalent: np.abs(scipy.signal.hilbert(x))."""
    return np.abs(analytic_signal(x))


def instantaneous_phase(x: np.ndarray) -> np.ndarray:
    """Unwrapped instantaneous phase in radians."""
    return np.unwrap(np.angle(analytic_signal(x)))


def instantaneous_frequency(x: np.ndarray, fs: float) -> np.ndarray:
    """Instantaneous frequency in Hz, from the phase derivative.

    Returns an array one sample shorter than `x`.
    """
    return np.diff(instantaneous_phase(x)) * fs / (2.0 * np.pi)''')

m.code('''# --- TEST CELL FOR STEP 2 ---
# (a) A pure tone: instantaneous frequency must be the tone's frequency, flat.
f_inst = instantaneous_frequency(tone, FS)
print(f"pure 20 Hz tone: inst freq mean {f_inst[mid].mean():.4f} Hz, "
      f"sd {f_inst[mid].std():.2e}")
assert np.isclose(f_inst[mid].mean(), 20.0, rtol=1e-4)
assert f_inst[mid].std() < 1e-6, "a pure tone has one frequency at every instant"

# (b) An amplitude-modulated tone: the envelope must recover the modulator, which
# is known exactly because we built it.
mod = 1.0 + 0.6 * np.sin(2 * np.pi * 2.0 * t)
am = mod * np.sin(2 * np.pi * 40.0 * t)
env_am = envelope(am)
err = np.max(np.abs(env_am[mid] - mod[mid]))
print(f"\\nAM signal: largest envelope error vs the true modulator: {err:.4f}")
assert err < 0.02, "the envelope must track a slow modulator of a fast carrier"

# (c) A frequency-modulated tone: instantaneous frequency must track the sweep.
sweep_hz = 20.0 + 5.0 * np.sin(2 * np.pi * 1.0 * t)
phase = 2 * np.pi * np.cumsum(sweep_hz) / FS
fm = np.sin(phase)
f_meas = instantaneous_frequency(fm, FS)
err_f = np.max(np.abs(f_meas[mid] - sweep_hz[:-1][mid]))
print(f"FM signal: largest instantaneous-frequency error: {err_f:.4f} Hz")
assert err_f < 0.5, "instantaneous frequency must follow a genuine narrowband sweep"
print("\\nStep 2 passed. On narrowband signals all three quantities do what they claim.")''')

m.md(r'''---

## 3. Where it stops meaning anything

Everything in Section 2 was narrowband: one oscillation, slowly modulated. Real
local field potential is not. It is broadband, dominated by an aperiodic $1/f$
component, and the analytic signal of such a record still returns an envelope, a
phase, and an instantaneous frequency, with no warning attached.

The failure is visible in the arithmetic. When two comparable components at
different frequencies are present, the resultant phasor sweeps backwards during
part of every beat cycle, so $d\phi/dt$ goes **negative**. A negative
instantaneous frequency is not a physical quantity; it is a sign that the
question was malformed.

The requirement is that the signal be narrowband enough that its amplitude and
phase vary on separable timescales, which is the Bedrosian condition. In practice
this means: **filter first, and interpret only within the band you filtered
to.** That is why SIG 2 came before this module, and it is why an envelope computed
on unfiltered LFP is not a beta envelope no matter what it is called.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def negative_fraction(x):
    """Fraction of samples where the instantaneous frequency is negative."""
    f = instantaneous_frequency(x, FS)
    return float(np.mean(f[200:-200] < 0))

# Build a realistic broadband LFP: 1/f aperiodic plus a beta oscillation.
n = 20000
white = rng.standard_normal(n)
freqs = np.fft.rfftfreq(n, 1 / FS)
freqs[0] = 1.0
pink = np.fft.irfft(np.fft.rfft(white) / np.sqrt(freqs), n=n)
pink = 3.0 * pink / np.std(pink)
tb = np.arange(n) / FS
# The planted beta must have a VARYING amplitude, or "does the envelope track the
# truth" is a correlation against a constant and means nothing.
beta_env_true = 1.5 * (1.0 + 0.9 * np.sin(2 * np.pi * 0.7 * tb))
lfp = pink + beta_env_true * np.sin(2 * np.pi * 20.0 * tb)

b_beta, a_beta = butter(4, [13.0, 30.0], btype='band', fs=FS)
lfp_beta = filtfilt(b_beta, a_beta, lfp)

print(f"{'signal':>34} {'negative inst freq':>20} {'median inst freq':>18}")
for name, sig in (("pure 20 Hz tone", tone),
                  ("broadband LFP, unfiltered", lfp),
                  ("same LFP, filtered to 13-30 Hz", lfp_beta)):
    f = instantaneous_frequency(sig, FS)[200:-200]
    print(f"{name:>34} {negative_fraction(sig):>19.1%} {np.median(f):>16.1f} Hz")

assert negative_fraction(lfp) > 0.15, \\
    "on broadband data the phase runs backwards a substantial fraction of the time"
assert negative_fraction(lfp_beta) < 0.02, "filtering to a band repairs it"
assert negative_fraction(tone) < 1e-3, "a pure tone never runs backwards"

# And the envelope is not innocent either: the unfiltered envelope is dominated by
# whatever is largest, which here is the aperiodic component, not beta.
env_raw = envelope(lfp)
env_band = envelope(lfp_beta)
r_raw = float(np.corrcoef(env_raw[500:-500], beta_env_true[500:-500])[0, 1])
r_band = float(np.corrcoef(env_band[500:-500], beta_env_true[500:-500])[0, 1])
print(f"\\ncorrelation of the measured envelope with the true beta envelope:")
print(f"  unfiltered : {r_raw:+.3f}")
print(f"  band-passed: {r_band:+.3f}")
assert abs(r_raw) < 0.3, "an unfiltered envelope is not a beta envelope"
assert r_band > 0.6, "a band-passed envelope tracks the beta amplitude it was filtered for"
assert r_band > 5 * abs(r_raw), "and it does so far better than the unfiltered one"

# Cross-check against SIG 5: a Morlet wavelet on the same band should agree.
def morlet(f0, nc, fs):
    st = nc / (2 * np.pi * f0)
    half = int(np.ceil(3 * st * fs))
    tt = np.arange(-half, half + 1) / fs
    w = np.exp(2j * np.pi * f0 * tt) * np.exp(-tt ** 2 / (2 * st ** 2))
    return w / np.sqrt(np.sum(np.abs(w) ** 2))

# To compare fairly the two must span the SAME band. The Butterworth passband is
# 13 to 30 Hz, a full width of 17 Hz, so by SIG 5's sigma_f = f0 / n_cycles and
# FWHM = 2.355 * sigma_f, the matching wavelet has n_cycles = 2.355 * 20 / 17.
n_cycles_matched = 2.355 * 20.0 / 17.0
wav_env = np.abs(np.convolve(lfp, morlet(20.0, n_cycles_matched, FS), mode='same'))
r_cross = float(np.corrcoef(env_band[1000:-1000], wav_env[1000:-1000])[0, 1])
r_mismatched = float(np.corrcoef(
    env_band[1000:-1000],
    np.abs(np.convolve(lfp, morlet(20.0, 7.0, FS), mode='same'))[1000:-1000])[0, 1])
print(f"\\nHilbert on 13-30 Hz vs Morlet, {n_cycles_matched:.1f} cycles (matched): r = {r_cross:+.3f}")
print(f"Hilbert on 13-30 Hz vs Morlet, 7.0 cycles (narrower) : r = {r_mismatched:+.3f}")
assert r_cross > 0.9, "matched bandwidths must agree closely"
assert r_cross > r_mismatched, "and mismatched ones must agree less well"
print("\\nStep 3 passed. Filter first, or the words envelope and phase do not refer")
print("to the band you think you are talking about.")''')

m.md(r'''---

## 4. What you established, and what Signal Processing established

1. The analytic signal deletes the negative frequencies and doubles the rest. Its
   real part is the input and its spectrum is one-sided, both verified before any
   comparison to a library.
2. On narrowband signals the envelope recovers a known modulator to within 0.02
   and the instantaneous frequency follows a known sweep to within 0.5 Hz.
3. On realistic broadband LFP the instantaneous frequency is **negative** a large
   fraction of the time, which is not a physical quantity, and the envelope
   correlates near zero with the true beta envelope. Bandpass filtering repairs
   both.
4. Hilbert on a filtered signal and a Morlet wavelet at the same centre frequency
   agree closely. They are two routes to the same complex representation, and SIG 5's
   time-frequency trade is present in both, hidden in the filter's bandwidth
   rather than named in a cycle count.

**Signal Processing is complete.** SIG 1 established what a recording can represent. SIG 2, what
a filter does to it and what that costs a latency. SIG 3, that resolution is
duration and that a taper decides what is visible. SIG 4, that the obvious spectral
estimator never converges. SIG 5, that time and frequency precision trade at a fixed
rate. SIG 6, that the instantaneous quantities everyone reports are defined only
inside a band someone had to choose.

### Exercises

**Exercise 1.** Section 3 filtered to 13 to 30 Hz. Repeat the negative-frequency
measurement for bands of width 2, 5, 10 and 20 Hz centred on 20 Hz. How narrow
does a band have to be before instantaneous frequency is well behaved, and what
does SIG 2 say that narrowness costs?

**Exercise 2.** Burst detection thresholds an envelope, often at a percentile of
the envelope distribution. Show that the threshold you obtain depends on the
filter bandwidth, and connect this to guardrail G4, which requires a threshold to
be set within each condition.

**Exercise 3.** The Bedrosian condition asks that the amplitude and the carrier
occupy non-overlapping frequency ranges. Construct an amplitude-modulated signal
that violates it, and show that the envelope no longer recovers the modulator
even though nothing in the code complains.
''')

m.emit()
verify("02_dsp", "06_hilbert_instantaneous_features")
print("  SIG 6 OK")
