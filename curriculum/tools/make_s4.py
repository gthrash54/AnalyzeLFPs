import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("02_dsp", "04_welch_and_multitaper")

m.md(r'''# Lesson SIG 4: Welch's Method and Multitaper Spectral Estimation {{VARIANT}}

**Foundations · Signal Processing for Neural Time Series**

{{INSTRUCTIONS}}

SIG 3 transformed a signal. This module estimates a **spectrum**, which is a
different and harder problem, and it opens with the fact that makes it hard: the
obvious estimator does not get better as you collect more data.

**What it assumes**

| From | What is used |
|---|---|
| SIG 1 | Sampling rate and Nyquist. |
| SIG 3 | The DFT, that resolution is $1/T$, and that a taper trades sidelobes for main-lobe width. |

**What it underwrites**

The `psd_by_condition` recipe, which is Welch. Guardrail **G8**, which asks for a
z-score beside any dB figure, because Section 1 explains why a single spectrum's
apparent structure is largely variance.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import welch as scipy_welch
from scipy.signal.windows import dpss

rng = np.random.default_rng(8)
FS = 1000.0
print("Environment initialized for Lesson SIG 4")''')

m.md(r'''---

## 1. The periodogram does not converge

The natural estimator of the power spectral density from $N$ samples is the
periodogram,

$$\hat{S}(f_k) = \frac{1}{N f_s}\left|X[k]\right|^2$$

It is asymptotically unbiased: on average it converges to the true spectrum. But
its **variance does not shrink with $N$**. At every frequency, the estimate is
roughly the true value times a $\chi^2_2$ random variable, whose standard
deviation equals its mean, no matter how much data went in.

The reason is a counting argument. Doubling $N$ doubles the number of frequency
bins, so each bin is still estimated from the same two numbers, a real and an
imaginary part. More data buys more bins, not better bins.

The practical consequence is that a single periodogram of a long recording looks
richly structured, and almost all of that structure is noise. Below, the relative
standard deviation of the estimate is measured as $N$ grows by a factor of 64.''')

m.task(
'''def periodogram(x: np.ndarray, fs: float) -> tuple:
    """One-sided power spectral density from a single DFT. Returns (freqs, psd).

    Scale so that summing the psd times the bin width recovers the signal
    variance, i.e. divide |X|^2 by (N * fs) and double every bin except DC and,
    when N is even, Nyquist.

    Production equivalent: `scipy.signal.periodogram`.
    """
    # TODO: N = len(x); take np.fft.rfft and its squared magnitude
    # TODO: divide by (N * fs)
    # TODO: double all bins except DC (and Nyquist when N is even)
    # TODO: return np.fft.rfftfreq(N, 1/fs) and the psd
    raise NotImplementedError("Implement periodogram")''',
'''def periodogram(x: np.ndarray, fs: float) -> tuple:
    """One-sided power spectral density from a single DFT. Returns (freqs, psd).

    Scale so that summing the psd times the bin width recovers the signal
    variance, i.e. divide |X|^2 by (N * fs) and double every bin except DC and,
    when N is even, Nyquist.

    Production equivalent: `scipy.signal.periodogram`.
    """
    N = len(x)
    X = np.fft.rfft(x)
    psd = (np.abs(X) ** 2) / (N * fs)
    psd[1:] *= 2.0
    if N % 2 == 0:
        psd[-1] /= 2.0
    return np.fft.rfftfreq(N, 1.0 / fs), psd''')

m.code('''# --- TEST CELL FOR STEP 1 ---
# (a) The scaling is right if the integrated psd recovers the variance (Parseval).
x_var = rng.standard_normal(4096) * 3.0
f_p, p_p = periodogram(x_var, FS)
integrated = np.sum(p_p) * (f_p[1] - f_p[0])
print(f"signal variance      : {np.var(x_var):.4f}")
print(f"integrated periodogram: {integrated:.4f}")
assert np.isclose(integrated, np.var(x_var), rtol=0.02), "the psd must integrate to the variance"

# (b) And it must match scipy's, which is a separate implementation.
from scipy.signal import periodogram as scipy_periodogram
# scipy detrends by default; ours does not, so compare like with like.
f_s, p_s = scipy_periodogram(x_var, FS, detrend=False)
assert np.allclose(p_p, p_s, rtol=1e-8), "must agree with scipy.signal.periodogram"

# (c) The claim: variance does NOT fall with N. White noise, so the truth is flat.
TRUE_PSD = 2.0 / FS      # unit-variance white noise, one-sided
print(f"\\n{'N':>8} {'mean/true':>11} {'relative sd':>13}")
rel_sds = {}
for N in (256, 1024, 4096, 16384):
    ests = np.array([periodogram(rng.standard_normal(N), FS)[1] for _ in range(300)])
    band = ests[:, (ests.shape[1] // 4):(ests.shape[1] // 2)]
    rel_sds[N] = float(np.std(band) / np.mean(band))
    print(f"{N:>8} {np.mean(band) / TRUE_PSD:>11.3f} {rel_sds[N]:>13.3f}")

assert abs(rel_sds[16384] - rel_sds[256]) < 0.15, \\
    "the relative sd must stay put across a 64x increase in data"
assert 0.8 < rel_sds[16384] < 1.2, "for a chi-square with 2 dof, sd equals the mean"
print("\\n64 times the data, the same relative uncertainty. Every bin is still")
print("estimated from one real and one imaginary number.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Welch: buy variance with resolution

Since one long record gives one bad estimate per bin, cut it into $K$ segments,
periodogram each, and average. Independent estimates average down, so the
variance falls roughly as $1/K$.

Nothing is free, and SIG 3 already named the price. Each segment is shorter, so by
$\Delta f = 1/T$ the resolution is $K$ times coarser. Welch's method is a dial
between a noisy sharp estimate and a smooth blunt one, and where you set it is a
scientific choice about the width of the feature you are looking for.

Overlapping the segments recovers some efficiency, because a taper throws away
the data at the segment edges. Half overlap with a Hann window is the usual
setting and is what `psd_by_condition` uses.''')

m.task(
'''def welch_psd(x: np.ndarray, fs: float, nperseg: int, overlap: float = 0.5) -> tuple:
    """Welch's averaged, tapered periodogram. Returns (freqs, psd).

    Split into segments of `nperseg` with the given fractional overlap, apply a
    Hann taper, periodogram each, and average. Compensate for the taper by
    dividing by the mean of its square, so white noise still reads back its true
    level.

    Production equivalent: `scipy.signal.welch`, which is what the
    `psd_by_condition` recipe calls.
    """
    # TODO: step = int(nperseg * (1 - overlap)); build the Hann window
    # TODO: for each segment start, take the segment, remove its mean, apply the window
    # TODO: periodogram it, and divide by mean(window ** 2) to undo the taper's loss
    # TODO: average the segment psds and return
    raise NotImplementedError("Implement welch_psd")''',
'''def welch_psd(x: np.ndarray, fs: float, nperseg: int, overlap: float = 0.5) -> tuple:
    """Welch's averaged, tapered periodogram. Returns (freqs, psd).

    Split into segments of `nperseg` with the given fractional overlap, apply a
    Hann taper, periodogram each, and average. Compensate for the taper by
    dividing by the mean of its square, so white noise still reads back its true
    level.

    Production equivalent: `scipy.signal.welch`, which is what the
    `psd_by_condition` recipe calls.
    """
    step = max(1, int(round(nperseg * (1.0 - overlap))))
    win = np.hanning(nperseg)
    correction = np.mean(win ** 2)
    acc = None
    count = 0
    for start in range(0, len(x) - nperseg + 1, step):
        seg = x[start:start + nperseg]
        seg = (seg - seg.mean()) * win
        freqs, psd = periodogram(seg, fs)
        acc = psd if acc is None else acc + psd
        count += 1
    return freqs, (acc / count) / correction''')

m.code('''# --- TEST CELL FOR STEP 2 ---
long_noise = rng.standard_normal(65536)

# (a) Level is preserved: white noise still reads its true psd after tapering.
f_w, p_w = welch_psd(long_noise, FS, nperseg=1024)
print(f"true psd of unit white noise : {TRUE_PSD:.5f}")
print(f"Welch estimate, median       : {np.median(p_w):.5f}")
assert np.isclose(np.median(p_w), TRUE_PSD, rtol=0.1), "the taper correction must preserve level"

# (b) Variance falls as 1/K, and resolution falls with it. Both, measured.
print(f"\\n{'nperseg':>9} {'segments K':>11} {'df (Hz)':>9} {'relative sd':>13} {'1/sqrt(K)':>11}")
for nperseg in (16384, 4096, 1024, 256):
    f_k, p_k = welch_psd(long_noise, FS, nperseg=nperseg)
    K = 1 + (len(long_noise) - nperseg) // max(1, int(nperseg * 0.5))
    band = p_k[(f_k > 100) & (f_k < 400)]
    print(f"{nperseg:>9} {K:>11} {FS/nperseg:>9.3f} {np.std(band)/np.mean(band):>13.3f} "
          f"{1/np.sqrt(K):>11.3f}")

_, p_few = welch_psd(long_noise, FS, nperseg=16384)
_, p_many = welch_psd(long_noise, FS, nperseg=256)
sd_few = np.std(p_few) / np.mean(p_few)
sd_many = np.std(p_many) / np.mean(p_many)
assert sd_many < 0.35 * sd_few, "more segments must give a visibly smoother estimate"

# (c) Against scipy, which implements the same method independently.
f_ref, p_ref = scipy_welch(long_noise, FS, nperseg=1024, noverlap=512, window='hann',
                           detrend='constant')
assert np.allclose(p_w, p_ref, rtol=0.02), "must agree with scipy.signal.welch"
print("\\nStep 2 passed. Variance falls like 1/sqrt(K) and resolution falls like K.")
print("Welch is a dial, and where it is set is a claim about the feature you expect.")''')

m.md(r'''---

## 3. Multitaper: buy variance without shortening the window

Welch shortens the window to get independent estimates. Multitaper gets them a
different way: keep the **whole** window and project it onto $K$ tapers that are
mutually orthogonal, so their periodograms are approximately independent and can
be averaged.

The tapers are the discrete prolate spheroidal sequences, the Slepian sequences,
which are the functions maximally concentrated in a chosen bandwidth. The
time-bandwidth product $NW$ sets that bandwidth, and $K \le 2NW - 1$ tapers are
usable before the later ones start leaking.

The trade is now explicit and better posed than Welch's. You choose a spectral
resolution $2W$ directly, and receive $2NW-1$ averages at that resolution, using
every sample in the record rather than throwing away the ends of segments.''')

m.task(
'''def multitaper_psd(x: np.ndarray, fs: float, nw: float = 4.0, k: int | None = None) -> tuple:
    """Multitaper power spectral density using DPSS tapers. Returns (freqs, psd).

    `nw` is the time-bandwidth product; `k` defaults to 2*nw - 1 tapers.

    Note the scaling. `dpss(..., norm=2)` returns tapers of unit ENERGY, meaning
    sum(w**2) = 1, while `periodogram` above already divides by N. Multiplying the
    tapers by sqrt(N) makes mean(w**2) = 1 instead, which is the convention the
    periodogram expects, and white noise then reads back its true level.

    Production equivalent: `mne.time_frequency.psd_array_multitaper`, and
    `scipy.signal.windows.dpss` for the tapers themselves.
    """
    # TODO: default k to int(2 * nw) - 1
    # TODO: get tapers with dpss(len(x), nw, Kmax=k, norm=2), then scale by sqrt(len(x))
    # TODO: remove the mean of x, then periodogram x * taper for each taper
    # TODO: return the average over tapers
    raise NotImplementedError("Implement multitaper_psd")''',
'''def multitaper_psd(x: np.ndarray, fs: float, nw: float = 4.0, k: int | None = None) -> tuple:
    """Multitaper power spectral density using DPSS tapers. Returns (freqs, psd).

    `nw` is the time-bandwidth product; `k` defaults to 2*nw - 1 tapers.

    Note the scaling. `dpss(..., norm=2)` returns tapers of unit ENERGY, meaning
    sum(w**2) = 1, while `periodogram` above already divides by N. Multiplying the
    tapers by sqrt(N) makes mean(w**2) = 1 instead, which is the convention the
    periodogram expects, and white noise then reads back its true level.

    Production equivalent: `mne.time_frequency.psd_array_multitaper`, and
    `scipy.signal.windows.dpss` for the tapers themselves.
    """
    if k is None:
        k = int(2 * nw) - 1
    tapers = dpss(len(x), nw, Kmax=k, norm=2) * np.sqrt(len(x))
    xc = x - x.mean()
    acc = None
    for taper in tapers:
        freqs, psd = periodogram(xc * taper, fs)
        acc = psd if acc is None else acc + psd
    return freqs, acc / k''')

m.code('''# --- TEST CELL FOR STEP 3 ---
seg = rng.standard_normal(4096)

# (a) The tapers really are orthonormal. That is what makes averaging them valid.
tap = dpss(4096, 4.0, Kmax=7, norm=2)
gram = tap @ tap.T
assert np.allclose(gram, np.eye(7), atol=1e-8), "DPSS tapers must be orthonormal"
print(f"taper orthonormality error: {np.max(np.abs(gram - np.eye(7))):.2e}")

# (b) Level preserved.
f_m, p_m = multitaper_psd(seg, FS, nw=4.0)
print(f"multitaper median psd: {np.median(p_m):.5f}  (true {TRUE_PSD:.5f})")
assert np.isclose(np.median(p_m), TRUE_PSD, rtol=0.15), "multitaper must preserve level"

# (c) The comparison that matters, and the trap in setting it up.
# Multitaper with NW=4 over 4096 samples resolves 2W = 2*NW/T = 1.95 Hz.
# The tempting Welch match is nperseg = FS / 1.95 = 512, because that makes the
# BIN SPACING 1.95 Hz. That is wrong. SIG 3 measured that a Hann taper widens the
# main lobe to 2.03 bins, so 512-sample segments actually resolve 3.96 Hz.
HANN_MAIN_LOBE_BINS = 2.03            # measured in SIG 3
RESOLUTION_HZ = 2 * 4.0 / (4096 / FS)

naive_nperseg = int(round(FS / RESOLUTION_HZ))
fair_nperseg = int(round(HANN_MAIN_LOBE_BINS * FS / RESOLUTION_HZ))
print(f"\\nmultitaper resolution, 2*NW/T : {RESOLUTION_HZ:.2f} Hz, from 7 tapers")
print(f"naive Welch match  : nperseg={naive_nperseg:>4}, bin spacing {FS/naive_nperseg:.2f} Hz, "
      f"but effective {HANN_MAIN_LOBE_BINS*FS/naive_nperseg:.2f} Hz")
print(f"fair  Welch match  : nperseg={fair_nperseg:>4}, bin spacing {FS/fair_nperseg:.2f} Hz, "
      f"effective {HANN_MAIN_LOBE_BINS*FS/fair_nperseg:.2f} Hz")
assert abs(HANN_MAIN_LOBE_BINS * FS / fair_nperseg - RESOLUTION_HZ) < 0.15, \\
    "the fair segment length must actually deliver the multitaper resolution"

trials = 400
sd_mt, sd_naive, sd_fair = [], [], []
for _ in range(trials):
    sig = rng.standard_normal(4096)
    _, pm = multitaper_psd(sig, FS, nw=4.0)
    sd_mt.append(np.std(pm[(f_m > 100) & (f_m < 400)]) / np.mean(pm[(f_m > 100) & (f_m < 400)]))
    for nps, store in ((naive_nperseg, sd_naive), (fair_nperseg, sd_fair)):
        fw, pw = welch_psd(sig, FS, nperseg=nps)
        band = pw[(fw > 100) & (fw < 400)]
        store.append(np.std(band) / np.mean(band))

mt_sd, naive_sd, fair_sd = np.mean(sd_mt), np.mean(sd_naive), np.mean(sd_fair)
print(f"\\n{'estimator':>26} {'effective res':>14} {'relative sd':>13}")
print(f"{'Welch, naive match':>26} {HANN_MAIN_LOBE_BINS*FS/naive_nperseg:>11.2f} Hz {naive_sd:>13.3f}")
print(f"{'Welch, fair match':>26} {HANN_MAIN_LOBE_BINS*FS/fair_nperseg:>11.2f} Hz {fair_sd:>13.3f}")
print(f"{'multitaper, NW=4':>26} {RESOLUTION_HZ:>11.2f} Hz {mt_sd:>13.3f}")

# The naive comparison flatters Welch, and it does so by giving it twice the
# blur. That is the finding, not a detail of setup.
assert naive_sd < mt_sd, "the naive match makes Welch look better"
assert HANN_MAIN_LOBE_BINS * FS / naive_nperseg > 1.8 * RESOLUTION_HZ, \\
    "because it is quietly resolving half as finely"

# At genuinely matched resolution the two are close, with multitaper slightly ahead.
assert mt_sd <= fair_sd * 1.05, "at matched resolution multitaper must not be worse"
assert abs(mt_sd - fair_sd) / fair_sd < 0.25, "and the honest gap is small, not dramatic"
print(f"\\nAt matched resolution the gap is {100*(fair_sd - mt_sd)/fair_sd:.0f} percent, not the")
print("landslide multitaper is often sold as. Its real advantage here is that NW")
print("states the resolution outright, while Welch's is a segment length times a")
print("window factor that nobody writes down, which is how the naive match above")
print("came to be off by two.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. The periodogram is **inconsistent**. Across a 64-fold increase in data its
   relative standard deviation stayed near 1.0, because each bin is always
   estimated from one real and one imaginary number. Structure in a single
   spectrum is mostly variance, which is why guardrail G8 asks for a z-score
   beside any dB figure.
2. Welch trades resolution for variance at a rate of $1/\sqrt{K}$ against $K$.
   Where you set that dial is a claim about the width of the feature you expect
   to find, and it belongs in a run record.
3. Comparing Welch against multitaper requires matching **effective** resolution,
   not bin spacing. A Hann taper widens the main lobe to 2.03 bins, as SIG 3
   measured, so the obvious segment length resolves half as finely as it appears
   to and flatters Welch. Corrected, multitaper is slightly ahead, by a few
   percent rather than the landslide it is often sold as. Its real advantage is
   that $NW$ states the resolution outright, while Welch's is a segment length
   times a window factor that nobody writes down.

### Exercises

**Exercise 1.** `psd_by_condition` uses Welch. Compute, for a 10 s intraoperative
epoch at 1 kHz, the segment length that resolves a 4 Hz-wide beta peak, and the
number of averages it leaves you. Then do the same for a 2 s epoch and say
whether the comparison between the two conditions is still fair.

**Exercise 2.** Section 3 matched resolutions using $2W = 2NW/T$. Verify that
formula empirically by finding the width of the multitaper response to a pure
tone, and check it against the Welch segment length you would need.

**Exercise 3.** The periodogram's $\chi^2_2$ distribution is strongly skewed, so
the mean of several spectra and the spectrum of the mean are different things.
Construct a case where averaging in dB rather than in power changes the answer,
and say which is correct.

---

**Next: SIG 5, complex Morlet wavelets.** This module estimated one spectrum for a
whole record. SIG 5 asks for a spectrum that changes with time, and finds that the
resolution trade of Section 2 reappears as a trade between time and frequency.
''')

m.emit()
verify("02_dsp", "04_welch_and_multitaper")
print("  SIG 4 OK")
