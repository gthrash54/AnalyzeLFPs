import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("06_connectivity", "02_wpli_and_directionality")

m.md(r'''# Lesson CON 2: The Weighted Phase Lag Index, and Directionality {{VARIANT}}

**Analysis · Connectivity and Spectral Coupling**

{{INSTRUCTIONS}}

CON 1 ended with a clean diagnosis: volume conduction and true interaction both
give a high phase-locking value, and only the **lag** separates them. So build a
measure that sees nothing but the lag.

That is the weighted phase lag index, and this module builds it, confirms it does
what it claims, and then measures what it costs, because a measure that discards
zero-lag coupling discards real zero-lag coupling too.

**What it assumes**

| From | What is used |
|---|---|
| CON 1 | The PLV, the zero-lag trap, and that a montage only partly repairs it. |
| SIG 3, SIG 4 | The cross-spectrum, and that a spectral estimate has variance. |
| SIG 6 | The analytic signal. |

**What it underwrites**

Every directed or undirected connectivity claim between two intracranial
contacts, and guardrail **G1** from its connectivity side.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, hilbert

rng = np.random.default_rng(111)
FS = 1000.0
BETA = (13.0, 30.0)

def bandpass(x, band=BETA, fs=FS):
    return filtfilt(*butter(4, list(band), btype='band', fs=fs), x)

print("Environment initialized for Lesson CON 2")''')

m.md(r'''---

## 1. Throw away the real part

The cross-spectrum between two signals is
$S_{12} = X_1 \overline{X_2}$, and its phase is the phase difference CON 1 measured.
Write it in Cartesian form. A phase difference of exactly zero puts $S_{12}$ on
the **positive real axis**, so its imaginary part is exactly zero. A phase
difference of $\pi$ puts it on the negative real axis: also zero imaginary part.

So the imaginary part of the cross-spectrum is blind, by construction, to
anything instantaneous. Volume conduction contributes nothing to it.

The **phase lag index** takes the sign of that imaginary part and averages it, and
the **weighted** version weights each sample by $|\mathrm{Im}(S_{12})|$, so
samples whose phase difference is near 0 or $\pi$, where the sign is decided by
noise, count for little:

$$\text{wPLI} = \frac{\left|\,\mathbb{E}\!\left[\mathrm{Im}(S_{12})\right]\right|}
{\mathbb{E}\!\left[\left|\mathrm{Im}(S_{12})\right|\right]}$$''')

m.task(
'''def cross_spectrum(x: np.ndarray, y: np.ndarray, band=BETA, fs: float = FS) -> np.ndarray:
    """Time-resolved cross-spectrum in a band, via the analytic signal.

    S_xy(t) = X(t) * conj(Y(t)) where X and Y are the band-limited analytic
    signals. Its phase is the instantaneous phase difference.
    """
    # TODO: bandpass both, take scipy.signal.hilbert of each
    # TODO: return the product of the first with the conjugate of the second
    raise NotImplementedError("Implement cross_spectrum")


def wpli(x: np.ndarray, y: np.ndarray, band=BETA, fs: float = FS) -> float:
    """Weighted phase lag index, in [0, 1].

    Production equivalent: `mne.connectivity.spectral_connectivity_epochs`
    with method='wpli'.
    """
    # TODO: imaginary part of the cross-spectrum
    # TODO: return |mean(Im)| / mean(|Im|), guarding a zero denominator
    raise NotImplementedError("Implement wpli")''',
'''def cross_spectrum(x: np.ndarray, y: np.ndarray, band=BETA, fs: float = FS) -> np.ndarray:
    """Time-resolved cross-spectrum in a band, via the analytic signal.

    S_xy(t) = X(t) * conj(Y(t)) where X and Y are the band-limited analytic
    signals. Its phase is the instantaneous phase difference.
    """
    ax = hilbert(bandpass(x, band, fs))
    ay = hilbert(bandpass(y, band, fs))
    return ax * np.conj(ay)


def wpli(x: np.ndarray, y: np.ndarray, band=BETA, fs: float = FS) -> float:
    """Weighted phase lag index, in [0, 1].

    Production equivalent: `mne.connectivity.spectral_connectivity_epochs`
    with method='wpli'.
    """
    im = np.imag(cross_spectrum(x, y, band, fs))
    denom = np.mean(np.abs(im))
    if denom == 0:
        return 0.0
    return float(abs(np.mean(im)) / denom)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
T = 60000
source = bandpass(rng.standard_normal(T))

def plv(x, y):
    s = cross_spectrum(x, y)
    return float(abs(np.mean(np.exp(1j * np.angle(s)))))

# (a) Volume conduction: two scaled copies of one source, no delay.
vc_a = 1.0 * source + 0.3 * bandpass(rng.standard_normal(T))
vc_b = 0.6 * source + 0.3 * bandpass(rng.standard_normal(T))

# (b) A real interaction with a delay.
DELAY = 12
delayed = np.r_[np.zeros(DELAY), source[:-DELAY]]
tr_a = source + 0.3 * bandpass(rng.standard_normal(T))
tr_b = delayed + 0.3 * bandpass(rng.standard_normal(T))

# (c) Nothing at all.
in_a = bandpass(rng.standard_normal(T))
in_b = bandpass(rng.standard_normal(T))

print(f"{'case':>28} {'PLV':>8} {'wPLI':>8}")
rows = {}
for name, a, b in (("volume conduction, no delay", vc_a, vc_b),
                   ("true interaction, 12 ms lag", tr_a, tr_b),
                   ("independent", in_a, in_b)):
    rows[name] = (plv(a, b), wpli(a, b))
    print(f"{name:>28} {rows[name][0]:>8.4f} {rows[name][1]:>8.4f}")

assert rows["volume conduction, no delay"][0] > 0.7, "PLV is fooled, as CON 1 showed"
assert rows["volume conduction, no delay"][1] < 0.1, "wPLI is not"
assert rows["true interaction, 12 ms lag"][1] > 0.4, "and it still sees a real lag"
assert rows["independent"][1] < 0.1, "and reports nothing when there is nothing"

print("\\nPLV cannot tell the first two apart. wPLI separates them by a factor of")
print(f"{rows['true interaction, 12 ms lag'][1]/max(rows['volume conduction, no delay'][1],1e-9):.0f}.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. What it costs: zero-lag coupling is real too

wPLI is blind to instantaneous relationships **by construction**, and it cannot
distinguish "instantaneous because it is the same source" from "instantaneous
because two regions are genuinely synchronised at zero lag".

The second happens. Two areas receiving a **common drive** from a third are
synchronised at near-zero lag with no direct connection, and two reciprocally
connected areas can also settle into near-zero-lag synchrony. Both are real
physiology and wPLI reports zero for both.

So wPLI is not a better PLV. It answers a narrower question: **is there a
consistent non-zero lag?** A wPLI of zero means "no evidence of lagged coupling",
which is not the same as "no coupling", and reporting it as the latter is the
mirror image of CON 1's error.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
# Genuine zero-lag coupling: two DIFFERENT sources driven by a common input, each
# with its own strong local activity. There is real shared structure here, and it
# is not volume conduction, because the two channels are not copies of one signal.
common = bandpass(rng.standard_normal(T))
zl_a = 0.7 * common + 0.7 * bandpass(rng.standard_normal(T))
zl_b = 0.7 * common + 0.7 * bandpass(rng.standard_normal(T))

print(f"{'case':>34} {'PLV':>8} {'wPLI':>8}")
for name, a, b in (("common drive, genuinely zero lag", zl_a, zl_b),
                   ("independent", in_a, in_b)):
    print(f"{name:>34} {plv(a, b):>8.4f} {wpli(a, b):>8.4f}")

assert plv(zl_a, zl_b) > 0.3, "there IS real shared structure here"
assert wpli(zl_a, zl_b) < 0.12, "and wPLI reports essentially nothing"
print("\\nReal coupling, and wPLI cannot see it. That is not a defect: it is what")
print("'ignores everything except the lag' means. It is a defect only if you read")
print("the zero as 'not coupled'.")

# The honest summary is that the two measures answer different questions, and
# reporting both is more informative than choosing one.
print(f"\\n{'case':>34} {'PLV':>8} {'wPLI':>8} {'reading':>34}")
for name, a, b in (("volume conduction", vc_a, vc_b),
                   ("common drive, zero lag", zl_a, zl_b),
                   ("true lagged interaction", tr_a, tr_b),
                   ("nothing", in_a, in_b)):
    p, w = plv(a, b), wpli(a, b)
    if p > 0.25 and w < 0.12:
        reading = "shared or zero-lag, undecided"
    elif p > 0.25 and w > 0.3:
        reading = "lagged interaction"
    else:
        reading = "no evidence of either"
    print(f"{name:>34} {p:>8.4f} {w:>8.4f} {reading:>34}")

print("\\nHigh PLV with low wPLI is the ambiguous cell, and it holds two very")
print("different situations. Nothing in either number resolves it, which is why")
print("the resolution has to come from anatomy or from an experimental manipulation.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Direction, and the assumption underneath it

Both measures so far are symmetric. Granger causality asks a directed question:
does the past of $x$ improve prediction of $y$ beyond $y$'s own past?

$$F_{x \to y} = \ln \frac{\mathrm{var}\left(y_t \mid y_{<t}\right)}
{\mathrm{var}\left(y_t \mid y_{<t},\, x_{<t}\right)}$$

It is a comparison of two regressions, and it is genuinely directional. The
assumption it rests on is the one that fails here: **no unobserved common
input**. If a third region drives both with different delays, the one that
receives it earlier will appear to cause the other, and the arithmetic will be
correct while the conclusion is wrong.

That is the same confound as CON 1's, wearing a direction.''')

m.task(
'''def granger(x: np.ndarray, y: np.ndarray, order: int = 10) -> float:
    """Granger causality from x to y, in nats.

    Fit y_t on its own `order` past samples, then on those plus x's `order` past
    samples, by least squares. Return ln(var_reduced / var_full).

    Production equivalent: `statsmodels.tsa.stattools.grangercausalitytests`,
    which also supplies significance.
    """
    # TODO: build a lagged design matrix of y's past, and one of x's past
    # TODO: regress y on the y-only design, take the residual variance
    # TODO: regress y on [y-past, x-past], take the residual variance
    # TODO: return log(var_restricted / var_full)
    raise NotImplementedError("Implement granger")''',
'''def granger(x: np.ndarray, y: np.ndarray, order: int = 10) -> float:
    """Granger causality from x to y, in nats.

    Fit y_t on its own `order` past samples, then on those plus x's `order` past
    samples, by least squares. Return ln(var_reduced / var_full).

    Production equivalent: `statsmodels.tsa.stattools.grangercausalitytests`,
    which also supplies significance.
    """
    n = len(y)
    target = y[order:]
    y_past = np.column_stack([y[order - k - 1:n - k - 1] for k in range(order)])
    x_past = np.column_stack([x[order - k - 1:n - k - 1] for k in range(order)])

    def resid_var(design):
        d = np.column_stack([design, np.ones(len(design))])
        beta, *_ = np.linalg.lstsq(d, target, rcond=None)
        return float(np.var(target - d @ beta))

    v_restricted = resid_var(y_past)
    v_full = resid_var(np.column_stack([y_past, x_past]))
    return float(np.log(v_restricted / max(v_full, 1e-300)))''')

m.code('''# --- TEST CELL FOR STEP 3 ---
# (a) A genuine one-way influence: x drives y with a delay.
drive = bandpass(rng.standard_normal(T))
gx = drive + 0.3 * bandpass(rng.standard_normal(T))
gy = np.r_[np.zeros(15), drive[:-15]] + 0.6 * bandpass(rng.standard_normal(T))
f_xy, f_yx = granger(gx, gy), granger(gy, gx)
print(f"true x -> y with a 15 ms delay:  F(x->y) {f_xy:.4f}, F(y->x) {f_yx:.4f}")
assert f_xy > f_yx, "the true direction must dominate"
assert f_xy > 0.05, "and be substantial"

# (b) The confound: a hidden third region drives BOTH, reaching one sooner.
hidden = bandpass(rng.standard_normal(T))
hx = np.r_[np.zeros(5), hidden[:-5]] + 0.6 * bandpass(rng.standard_normal(T))
hy = np.r_[np.zeros(20), hidden[:-20]] + 0.6 * bandpass(rng.standard_normal(T))
c_xy, c_yx = granger(hx, hy), granger(hy, hx)
print(f"hidden common driver, no x-y link: F(x->y) {c_xy:.4f}, F(y->x) {c_yx:.4f}")
assert c_xy > c_yx, "the earlier-reached channel appears to cause the later one"
assert c_xy > 2 * c_yx, "and the asymmetry is as clear as a real one"
assert c_xy > 0.02, "and the magnitude is large enough to be reported as a finding"

print(f"\\nThe spurious flow is {c_xy:.3f} with a {c_xy/max(c_yx,1e-9):.1f}x directional")
print(f"asymmetry, against {f_xy:.3f} for the genuine influence. Smaller here, and the")
print("same kind of number, arrived at with no connection between x and y at all.")
print("How large it gets is set by the difference between the two delays, which is")
print("anatomy you did not measure. Granger did not make a mistake: it answered the")
print("question it was asked, which is about prediction and not about connection.")

# How large can it get? Sweep the delay difference. The answer is not the one
# intuition offers.
print(f"\\n{'delay to x':>11} {'delay to y':>11} {'difference':>11} {'F(x->y)':>10} {'F(y->x)':>9}")
sweep = {}
for dx, dy in ((2, 30), (5, 20), (5, 12), (18, 20)):
    sx = np.r_[np.zeros(dx), hidden[:-dx]] + 0.6 * bandpass(rng.standard_normal(T))
    sy = np.r_[np.zeros(dy), hidden[:-dy]] + 0.6 * bandpass(rng.standard_normal(T))
    sweep[dy - dx] = (granger(sx, sy), granger(sy, sx))
    print(f"{dx:>9} ms {dy:>9} ms {dy-dx:>9} ms {sweep[dy-dx][0]:>10.4f} "
          f"{sweep[dy-dx][1]:>9.4f}")

assert sweep[2][0] > sweep[28][0], \\
    "the spurious influence is LARGEST when the two delays are close, not far apart"
assert sweep[2][0] > 10 * f_xy, "and there it dwarfs a genuine one-way drive"

print("\\nRead that table carefully, because it inverts the intuition. The spurious")
print("influence is largest when the two delays are CLOSE together, not far apart.")
print("Two regions almost equidistant from a common driver make one channel a")
print("near-perfect shifted copy of the other, so its past predicts the other's")
print("present almost exactly, and Granger reports an influence far larger than")
print("the genuine one-way drive measured above. Symmetrically placed regions are")
print("the dangerous case, and they are the ones least likely to arouse suspicion.")

# (c) The control that would distinguish them, if the third region were recorded.
def granger_conditional(x, y, z, order=10):
    """Granger from x to y, conditioning on a third signal z."""
    n = len(y)
    target = y[order:]
    def lags(v):
        return np.column_stack([v[order - k - 1:n - k - 1] for k in range(order)])
    def resid_var(design):
        d = np.column_stack([design, np.ones(len(design))])
        beta, *_ = np.linalg.lstsq(d, target, rcond=None)
        return float(np.var(target - d @ beta))
    base = np.column_stack([lags(y), lags(z)])
    return float(np.log(resid_var(base) / max(resid_var(np.column_stack([base, lags(x)])), 1e-300)))

cond = granger_conditional(hx, hy, hidden)
print(f"\\nconditioning on the hidden driver: F(x->y | z) {cond:.4f} (was {c_xy:.4f})")
assert cond < 0.35 * c_xy, "conditioning on the true driver removes most of the spurious flow"
print("\\nThe spurious directed influence largely disappears once the common driver is")
print("included. Which is only possible if you recorded it.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. The imaginary part of the cross-spectrum is zero for any instantaneous
   relationship, so wPLI is blind to volume conduction by construction. On the
   same data where PLV cannot separate volume conduction from a 12 ms
   interaction, wPLI separates them by more than an order of magnitude.
2. **wPLI is not a better PLV.** It answers a narrower question, and it reports
   essentially nothing for genuine zero-lag coupling from a common drive, which
   is real physiology. A wPLI of zero means no evidence of *lagged* coupling.
   Reading it as no coupling is the mirror image of CON 1's error.
3. High PLV with low wPLI is an ambiguous cell holding two very different
   situations, and neither number resolves it. The resolution has to come from
   anatomy or from an experimental manipulation.
4. Granger causality is genuinely directional and rests on there being no
   unobserved common input. A hidden third region reaching one channel 15 ms
   sooner than the other produced a directed influence of 0.040 with a 2-fold
   asymmetry, against 0.097 for a genuine one-way drive, with **no connection
   between the two channels at all**. Its size is set by the delay difference,
   which is anatomy you did not measure. Conditioning on the driver removes most
   of it, which is only possible if you recorded it. Worse, the spurious flow is
   **largest when the two delays are close**: two regions nearly equidistant from
   a common driver produced a value ten times the genuine one-way drive, because
   one channel is then a near-perfect shifted copy of the other.

### Exercises

**Exercise 1.** Section 1 used a 12 ms delay at a 20 Hz centre frequency. Sweep
the delay from 0 to 25 ms and plot wPLI. Where are the zeros, and what does that
say about a wPLI of zero between two regions you believe are connected?

**Exercise 2.** CON 1 measured that a bipolar montage leaves a residual zero-lag
PLV. Compute wPLI on the same montaged pairs and confirm it is unaffected. Then
state which of the two measures makes a montage more or less important.

**Exercise 3.** For the hidden-driver case in Section 3, find the pair of delays
that makes the spurious Granger influence largest, and the pair that makes it
zero. What does the existence of the second pair imply about interpreting a null
Granger result?

---

**Next: CON 3, phase-amplitude coupling.** A cross-frequency measure, and a
confound that does not come from volume conduction at all but from the shape of
the waveform.
''')

m.emit()
verify("06_connectivity", "02_wpli_and_directionality")
print("  CON 2 OK")
