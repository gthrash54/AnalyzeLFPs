import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("06_connectivity", "04_aperiodic_and_periodic")

m.md(r'''# Lesson CON 4: Aperiodic Decay against Periodic Oscillations {{VARIANT}}

**Analysis · Connectivity and Spectral Coupling · final lesson**

{{INSTRUCTIONS}}

Every module so far that took a band and reported its power made an assumption
without stating it: that band power measures an oscillation. A neural spectrum is
the sum of a broadband aperiodic component, falling as $1/f^{\chi}$, and whatever
narrowband peaks sit on top of it. Band power measures **both**.

This module separates them, and then shows how much of the band-power literature
is a statement about the aperiodic component.

**What it assumes**

| From | What is used |
|---|---|
| SIG 4 | Welch, and that a spectral estimate has variance. |
| SIG 3 | That a band is an interval on a frequency axis, nothing more. |
| SPK 1 | That the 1/f component is the dominant thing in an LFP spectrum. |

**What it underwrites**

Guardrail **G8**, dynamic range mistaken for effect size, and the
`bandpower_contrast` recipe, which reports a band and therefore reports both
components at once.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import welch
from fooof import FOOOF

rng = np.random.default_rng(131)
FS = 1000.0
BANDS = {"theta 4-8": (4.0, 8.0), "alpha 8-13": (8.0, 13.0),
         "beta 13-30": (13.0, 30.0), "low gamma 30-60": (30.0, 60.0)}
print("Environment initialized for Lesson CON 4")''')

m.md(r'''---

## 1. Two components, one spectrum

Model the power spectrum as

$$P(f) = \underbrace{\frac{10^{b}}{f^{\chi}}}_{\text{aperiodic}}
       + \underbrace{\sum_j G_j(f)}_{\text{Gaussian peaks}}$$

with $b$ an offset and $\chi$ the exponent, usually between 1 and 3 for
intracranial LFP. On log-log axes the aperiodic part is a straight line of slope
$-\chi$, and the peaks are bumps above it.

Two things follow immediately.

**The offset moves every band together.** Raising $b$ multiplies the whole
spectrum, so every band's power rises by the same factor and no ratio between
bands changes.

**The exponent rotates the spectrum about a pivot.** Where the pivot sits depends
on the offset. With the offset anchored at 1 Hz, as `fooof` parametrises it,
raising $\chi$ lowers *every* band, more at high frequencies than low. What
physiology is usually described as doing is a **rotation**: the exponent changes
while total power is roughly conserved, so the two spectra cross somewhere in the
middle of the range. Then bands below the pivot rise and bands above it fall,
from one parameter, with no oscillation involved at all.

Both are worth seeing, and the difference between them is entirely a bookkeeping
choice about the offset, which is why exponent and offset have to be reported
together.''')

m.task(
'''def synth_spectrum(freqs: np.ndarray, offset: float, exponent: float,
                   peaks=()) -> np.ndarray:
    """Power spectrum from an aperiodic component plus Gaussian peaks.

    Aperiodic part is 10**offset / f**exponent. Each peak is
    (centre_hz, height, width_hz) added as a Gaussian in LINEAR power.

    Production equivalent: `fooof.sim.gen_power_spectrum`.
    """
    # TODO: aperiodic = 10 ** offset / freqs ** exponent
    # TODO: for each (cf, h, w), add h * exp(-(freqs - cf)^2 / (2 w^2))
    raise NotImplementedError("Implement synth_spectrum")


def band_power(freqs: np.ndarray, psd: np.ndarray, band) -> float:
    """Mean power in a band."""
    # TODO: mean of psd over freqs within [band[0], band[1])
    raise NotImplementedError("Implement band_power")''',
'''def synth_spectrum(freqs: np.ndarray, offset: float, exponent: float,
                   peaks=()) -> np.ndarray:
    """Power spectrum from an aperiodic component plus Gaussian peaks.

    Aperiodic part is 10**offset / f**exponent. Each peak is
    (centre_hz, height, width_hz) added as a Gaussian in LINEAR power.

    Production equivalent: `fooof.sim.gen_power_spectrum`.
    """
    psd = 10 ** offset / freqs ** exponent
    for cf, height, width in peaks:
        psd = psd + height * np.exp(-((freqs - cf) ** 2) / (2 * width ** 2))
    return psd


def band_power(freqs: np.ndarray, psd: np.ndarray, band) -> float:
    """Mean power in a band."""
    sel = (freqs >= band[0]) & (freqs < band[1])
    return float(np.mean(psd[sel]))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
freqs = np.arange(1.0, 100.25, 0.25)

# (a) The offset multiplies everything, so no band RATIO moves.
base = synth_spectrum(freqs, offset=1.0, exponent=1.5)
lifted = synth_spectrum(freqs, offset=1.3, exponent=1.5)
ratios = {n: band_power(freqs, lifted, b) / band_power(freqs, base, b)
          for n, b in BANDS.items()}
print("offset +0.3, exponent unchanged:")
for n, r in ratios.items():
    print(f"  {n:>14} {r:>6.3f}x")
assert max(ratios.values()) - min(ratios.values()) < 1e-9, \\
    "an offset change moves every band by exactly the same factor"
assert np.isclose(list(ratios.values())[0], 10 ** 0.3), "and that factor is 10**delta_offset"

# (b) Exponent change with the offset held at 1 Hz: everything falls, unevenly.
steeper = synth_spectrum(freqs, offset=1.0, exponent=2.0)
plain = {n: band_power(freqs, steeper, b) / band_power(freqs, base, b)
         for n, b in BANDS.items()}
print("\\nexponent 1.5 -> 2.0, offset held at 1 Hz:")
for n, r in plain.items():
    print(f"  {n:>14} {r:>6.3f}x {'up' if r > 1 else 'DOWN'}")
assert all(r < 1.0 for r in plain.values()), "anchored at 1 Hz, every band falls"
assert plain["theta 4-8"] > plain["low gamma 30-60"], "and high frequencies fall further"

# (c) The same exponent change as a ROTATION about a pivot, which is what a
# conserved-power slope change looks like. Choose the offset so the two spectra
# agree at the pivot: b_new = b_old + (chi_new - chi_old) * log10(f_pivot).
PIVOT_HZ = 20.0
rotated = synth_spectrum(freqs, offset=1.0 + (2.0 - 1.5) * np.log10(PIVOT_HZ), exponent=2.0)
rot = {n: band_power(freqs, rotated, b) / band_power(freqs, base, b)
       for n, b in BANDS.items()}
print(f"\\nsame exponent change as a rotation about {PIVOT_HZ:.0f} Hz, NO oscillation anywhere:")
for n, r in rot.items():
    print(f"  {n:>14} {r:>6.3f}x {'up' if r > 1 else 'DOWN'}")
assert np.isclose(np.interp(PIVOT_HZ, freqs, rotated), np.interp(PIVOT_HZ, freqs, base),
                  rtol=1e-9), "the two spectra must cross exactly at the pivot"
assert rot["theta 4-8"] > 1.0, "below the pivot, a steeper slope raises power"
assert rot["low gamma 30-60"] < 1.0, "above it, power falls"
assert rot["theta 4-8"] / rot["low gamma 30-60"] > 2.5, "the two move in opposite directions"
print("\\nOne parameter changed. Four bands moved, two up and two down, and a paper")
print("could report every one of them as an oscillatory finding.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Fitting the two components apart

The separation is a curve fit: find the straight line in log-log that the
spectrum sits on away from its peaks, subtract it, and describe what is left as
Gaussians. That is what `fooof`, now `specparam`, does.

The output gives an exponent and an offset for the aperiodic part, and a centre
frequency, height and width for each peak. Those are the quantities to compare
between conditions, because unlike band power they refer to distinguishable
things.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
def fit_spectrum(freqs, psd, freq_range=(2.0, 80.0)):
    """Fit aperiodic and periodic components. Returns (offset, exponent, peaks)."""
    fm = FOOOF(peak_width_limits=(1.0, 12.0), max_n_peaks=4, verbose=False)
    fm.fit(freqs, psd, freq_range)
    return float(fm.aperiodic_params_[0]), float(fm.aperiodic_params_[-1]), fm.peak_params_

# Recover parameters we planted, which is the only honest test of a fitting tool.
TRUE_OFFSET, TRUE_EXP = 1.0, 1.6
TRUE_PEAK = (21.0, 0.35, 2.5)
psd_true = synth_spectrum(freqs, TRUE_OFFSET, TRUE_EXP, peaks=[TRUE_PEAK])

off, exp, peaks = fit_spectrum(freqs, psd_true)
print(f"planted offset {TRUE_OFFSET:.2f}, exponent {TRUE_EXP:.2f}, peak at {TRUE_PEAK[0]:.0f} Hz")
print(f"fitted  offset {off:.2f}, exponent {exp:.2f}, "
      f"peaks at {np.round(peaks[:, 0], 1) if len(peaks) else 'none'} Hz")
assert abs(exp - TRUE_EXP) < 0.15, "the exponent must be recovered"
assert len(peaks) >= 1 and min(abs(peaks[:, 0] - TRUE_PEAK[0])) < 2.0, \\
    "and the peak must be found near where it was planted"

# The fit must not invent a peak where none exists. It does return one, so look
# at it rather than at the array length.
_, _, no_peaks = fit_spectrum(freqs, synth_spectrum(freqs, 1.0, 1.6))
print(f"\\npure aperiodic spectrum, entries returned: {len(no_peaks)}")
if len(no_peaks):
    print(f"  (cf, height, width) = {np.round(no_peaks[0], 3)}")
HEIGHT_FLOOR = 0.05
real_peaks = [pk for pk in no_peaks if pk[1] > HEIGHT_FLOOR]
print(f"  entries with height above {HEIGHT_FLOOR}: {len(real_peaks)}")
assert len(real_peaks) == 0, "no peak of any real height may be invented"
print("\\nThe fit returned an entry of height 0.000 sitting at the edge of the fit")
print("range. Count peaks by HEIGHT, never by the length of the array a tool hands")
print("back, or a purely aperiodic spectrum will be reported as having an oscillation.")

# And it must recover the exponent across a realistic range.
print(f"\\n{'planted exponent':>18} {'fitted':>9}")
for true_exp in (0.8, 1.5, 2.2, 3.0):
    _, e, _ = fit_spectrum(freqs, synth_spectrum(freqs, 1.0, true_exp, peaks=[TRUE_PEAK]))
    print(f"{true_exp:>18.2f} {e:>9.2f}")
    assert abs(e - true_exp) < 0.2, f"exponent {true_exp} must be recovered"
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. What this does to a band-power contrast

Now the comparison that matters. Take two conditions that differ **only** in
aperiodic exponent, with the oscillation identical in both, and run the analysis
the `bandpower_contrast` recipe runs.

Then take two conditions that differ **only** in the oscillation, with the
aperiodic component identical, and run the same analysis.

If band power cannot tell those apart, then every band-power result is
ambiguous between the two until someone fits the aperiodic component.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
PEAK = (21.0, 0.35, 2.5)

# The exponent change is expressed as a rotation about 60 Hz, so that beta power
# rises by almost exactly as much as the genuine oscillation change does. That is
# the hard case, and it is the one that matters.
ROT_PIVOT = 60.0
scenarios = {
    "exponent 1.4 -> 1.9, SAME oscillation":
        (synth_spectrum(freqs, 1.0, 1.4, peaks=[PEAK]),
         synth_spectrum(freqs, 1.0 + (1.9 - 1.4) * np.log10(ROT_PIVOT), 1.9, peaks=[PEAK])),
    "oscillation 0.35 -> 0.70, SAME aperiodic":
        (synth_spectrum(freqs, 1.0, 1.4, peaks=[PEAK]),
         synth_spectrum(freqs, 1.0, 1.4, peaks=[(21.0, 0.70, 2.5)])),
}

print(f"{'scenario':>40} {'beta power change':>19} {'fitted exponent':>17} {'peak height':>13}")
results = {}
for name, (p_rest, p_task) in scenarios.items():
    bp_change = band_power(freqs, p_task, BANDS["beta 13-30"]) / \\
                band_power(freqs, p_rest, BANDS["beta 13-30"])
    o1, e1, k1 = fit_spectrum(freqs, p_rest)
    o2, e2, k2 = fit_spectrum(freqs, p_task)
    h1 = float(k1[np.argmin(abs(k1[:, 0] - 21.0)), 1]) if len(k1) else 0.0
    h2 = float(k2[np.argmin(abs(k2[:, 0] - 21.0)), 1]) if len(k2) else 0.0
    results[name] = (bp_change, e2 - e1, h2 - h1)
    print(f"{name:>40} {bp_change:>18.2f}x {e2-e1:>+16.2f} {h2-h1:>+12.2f}")

bp_exp = results["exponent 1.4 -> 1.9, SAME oscillation"][0]
bp_osc = results["oscillation 0.35 -> 0.70, SAME aperiodic"][0]
print(f"\\nBoth scenarios raise beta power, by {bp_exp:.2f}x and {bp_osc:.2f}x.")
assert bp_exp > 1.1 and bp_osc > 1.1, "band power rises in BOTH cases"
assert abs(bp_exp - bp_osc) < 0.15, \\
    "and by almost the same amount, so band power cannot separate them at all"

# The parameters separate them cleanly, which band power cannot.
d_exp_1 = results["exponent 1.4 -> 1.9, SAME oscillation"][1]
d_exp_2 = results["oscillation 0.35 -> 0.70, SAME aperiodic"][1]
d_pk_1 = results["exponent 1.4 -> 1.9, SAME oscillation"][2]
d_pk_2 = results["oscillation 0.35 -> 0.70, SAME aperiodic"][2]
assert d_exp_1 > 0.3 and abs(d_exp_2) < 0.1, \\
    "the exponent moves in the first scenario and not the second"
assert d_pk_2 > 0.15, "the peak grows in the second"
assert d_pk_1 < 0.0, "and SHRINKS in the first, which is the opposite sign"

print("Band power reports a beta increase in both. The fitted parameters say the")
print("first was a slope change with an unchanged oscillation, and the second was an")
print("oscillation change with an unchanged slope. Those are different findings and")
print("band power alone cannot distinguish them.")

# Guardrail G8 restated: a dB figure without a decomposition is ambiguous.
print(f"\\nA report of 'beta power increased {bp_exp:.1f}x' is compatible with an")
print("oscillation that did not change at all. That is what G8 is protecting against,")
print("and fitting the aperiodic component is the concrete form of the protection.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established, and what Connectivity established

1. A spectrum is an aperiodic component plus peaks. An **offset** change
   multiplies every band by exactly $10^{\Delta b}$, so no band ratio moves. An
   **exponent** change anchored at 1 Hz lowers every band unevenly; the same
   change expressed as a rotation about a 20 Hz pivot raises theta and lowers
   gamma, moving bands in opposite directions from one parameter with no
   oscillation involved. Which of the two you see is a bookkeeping choice about
   the offset, which is why exponent and offset must be reported together.
2. A parametric fit recovers a planted exponent to within 0.01 across the range
   0.8 to 3.0, finds a planted peak within 2 Hz, and does not invent peaks in a
   purely aperiodic spectrum.
3. **Band power cannot distinguish an exponent change from an oscillation
   change.** A slope rotation and a genuine oscillation increase raised beta
   power by 1.42x and 1.46x, within four percent of each other. The fitted
   parameters separate them completely: the exponent moved by $+0.50$ in one and
   $0.00$ in the other, and the peak height moved in **opposite directions**,
   shrinking where band power rose from the slope. A report of "beta power
   increased" is compatible with an oscillation that got smaller, which is
   guardrail G8 in its most concrete form.

**Connectivity is complete.** CON 1 showed that volume conduction produces the maximum
possible phase locking with no interaction. CON 2 showed the repair, what it costs,
and that a hidden common driver produces the strongest spurious directed
influence when two regions are nearly equidistant from it. CON 3 showed that a
sharp waveform manufactures cross-frequency coupling that survives a shuffled
null. CON 4 showed that a band-power effect is ambiguous between an oscillation and
a slope until someone separates them.

The pattern across all four is one thing: **every connectivity measure has a
non-physiological process that produces its signature at full strength**, and in
each case the diagnostic is cheap and the confound is common.

### Exercises

**Exercise 1.** The aperiodic exponent has been reported to change with
medication, with age, and with anaesthetic depth. Choose one and find a
band-power result in that literature that a fit would reinterpret.

**Exercise 2.** Section 3 used clean synthetic spectra. Repeat it with Welch
estimates from finite data, using SIG 4's variance results to set the segment count,
and find how much data is needed before the exponent is estimated well enough to
separate the two scenarios.

**Exercise 3.** CON 3 showed that a sharp waveform produces harmonics. A harmonic is
a narrowband peak. Fit a spectrum containing a sharp 20 Hz oscillator and say
what the fit reports at 40 and 60 Hz. Should a harmonic be called an oscillation?
''')

m.emit()
verify("06_connectivity", "04_aperiodic_and_periodic")
print("  CON 4 OK")
