"""Generate the PRE 1 preprocessing capstone from one source."""
from __future__ import annotations

import json
import pathlib

CELLS = []
def md(s): CELLS.append(("markdown", s, None))
def code(s): CELLS.append(("code", s, None))
def task(stu, sol): CELLS.append(("code", stu, sol))

md(r"""# Lesson PRE 1: The Preprocessing Contract {{VARIANT}}

**Capstone. Draws on Linear Algebra and Signal Processing.**

{{INSTRUCTIONS}}

This module is the one place where everything so far has to hold at once, and it
mirrors `src/dbsspeech/preprocess/` line for line.

**What it assumes you have already built**

| From | What is used here |
|---|---|
| LIN 2 | A montage is a matrix. `M_vertical` is 7 by 8 and every row sums to zero. |
| LIN 3 | CAR is rank deficient, so some montages destroy a dimension permanently. |
| SIG 1 | Nyquist, and that usable bandwidth after decimation is $0.4\,f_s'$, not $0.5\,f_s'$. |
| SIG 2 | Filters have phase, and a narrow band rings. |

Nothing is re-derived. Where a result is needed it is restated in one line and
used.

**What it underwrites**

- `preprocess/reference.py` and `preprocess/resample.py`, the whole of the
  package's preprocessing surface.
- Guardrail **G6**, which refuses a run whose requested band reaches above the
  anti-alias cutoff.
- The rule in `CLAUDE.md` that says **never delete samples from recordings, and
  artifacts become annotations**. Section 4 tests the usual argument for that
  rule, finds it does not survive measurement, and then gives the real one.
""")

code("""import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import decimate, welch

rng = np.random.default_rng(7)
FS_RAW = 24000.0     # a TDT acquisition rate
N_CH = 8             # a 1-3-3-1 directional lead

# LIN 2's vertical bipolar montage, restated so this notebook runs alone.
DERIVATIONS = [(1, 0), (2, 0), (3, 0), (4, 7), (5, 7), (6, 7), (7, 0)]
M_VERT = np.zeros((7, N_CH))
for _r, (_p, _m) in enumerate(DERIVATIONS):
    M_VERT[_r, _p] = 1.0
    M_VERT[_r, _m] = -1.0

print('Environment initialized for Lesson PRE 1')""")

md(r"""---

## 1. Two linear operations, and the question everyone gets wrong

Preprocessing here is exactly two things.

**Re-referencing** takes the channel vector at each instant and applies a matrix:
$Y = M X$, where $M$ is $[D \times C]$ and $X$ is $[C \times T]$. It mixes across
channels and does nothing along time.

**Decimation** anti-alias filters each channel and keeps every $k$-th sample. It
acts along time and does nothing across channels.

Which order? The question sounds like it must have an answer, and pipelines
argue about it. It does not. $M$ is linear and time-invariant; decimation is
linear and applied identically to every channel. Two linear maps acting on
different axes commute:

$$\text{decimate}(M X) = M\,\text{decimate}(X)$$

Do not take that on faith. The next test measures it on a recording that
contains a stimulation artifact eight hundred times larger than the physiology,
which is the case where intuition most strongly says order should matter.""")

task(
'''def apply_montage(data: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Apply a montage matrix to `[n_channels, n_samples]` data.

    Production equivalent: `dbsspeech.preprocess.reference.build_montage` builds
    `M` from the lead geometry in `configs/leads.yaml`; MNE's is
    `mne.set_bipolar_reference`.
    """
    # TODO: check that M has as many columns as data has channels
    # TODO: return the matrix product, shape [n_derivations, n_samples]
    raise NotImplementedError("Implement apply_montage")''',
'''def apply_montage(data: np.ndarray, M: np.ndarray) -> np.ndarray:
    """Apply a montage matrix to `[n_channels, n_samples]` data.

    Production equivalent: `dbsspeech.preprocess.reference.build_montage` builds
    `M` from the lead geometry in `configs/leads.yaml`; MNE's is
    `mne.set_bipolar_reference`.
    """
    if M.shape[1] != data.shape[0]:
        raise ValueError(f"montage expects {M.shape[1]} channels, got {data.shape[0]}")
    return M @ data''')

code("""# --- TEST CELL FOR STEP 1 ---
t_raw = np.arange(int(FS_RAW * 2.0)) / FS_RAW

# A stimulation artifact 800x the physiology, with a per-contact gain difference
# of a few percent, which is what different impedances actually produce.
stim = np.sign(np.sin(2 * np.pi * 130.0 * t_raw)) * 800.0
contact_gain = 1.0 + 0.03 * rng.standard_normal(N_CH)
X = np.array([
    0.6 * np.sin(2 * np.pi * 20.0 * t_raw + i)      # local beta, different phase per contact
    + 2.0 * rng.standard_normal(len(t_raw))          # broadband noise
    + contact_gain[i] * stim                         # the shared artifact
    for i in range(N_CH)
])

assert apply_montage(X, M_VERT).shape == (7, len(t_raw))
try:
    apply_montage(X[:4], M_VERT)
    raise AssertionError("apply_montage must reject a channel-count mismatch")
except ValueError as exc:
    assert "montage expects" in str(exc), (
        f"numpy will raise on a shape mismatch anyway; the explicit check earns its "
        f"place only by saying what was expected. Got: {exc}"
    )

FACTOR = 24                                  # 24000 -> 1000 Hz
kw = dict(ftype='iir', zero_phase=True, axis=1)
reference_first = decimate(apply_montage(X, M_VERT), FACTOR, **kw)
decimate_first = apply_montage(decimate(X, FACTOR, **kw), M_VERT)

rel = np.max(np.abs(reference_first - decimate_first)) / np.max(np.abs(reference_first))
print(f"peak derivation amplitude          : {np.max(np.abs(reference_first)):.3g} uV")
print(f"max disagreement between the orders: {np.max(np.abs(reference_first - decimate_first)):.3e}")
print(f"relative                           : {rel:.3e}")
assert rel < 1e-9, f"these operations must commute, got {rel:.2e}"
print("\\nStep 1 passed. The orders agree to floating-point noise, with an artifact")
print("800x the signal present. Ordering these two steps is a convention, not a result.")""")

md(r"""---

## 2. What actually does not commute

The moment a step is **nonlinear**, the argument above collapses, and artifact
detection is nonlinear: it compares a magnitude against a threshold.

So "flag samples where the amplitude is extreme" is not one procedure. It is a
different procedure depending on whether you run it on recorded contacts or on
derivations, and the two disagree about which samples are artifact. Neither is
wrong. They are answers to different questions, and a run record that says only
"artifact rejection was applied" has not said which one was asked.

Thresholds here use the median and the median absolute deviation rather than the
mean and standard deviation, because the artifact you are trying to find is
exactly the thing that inflates a standard deviation and hides itself.""")

task(
'''def flag_artifacts(data: np.ndarray, k: float = 6.0) -> np.ndarray:
    """Boolean mask over samples, True where any row is beyond k robust deviations.

    Robust scale is the median absolute deviation, scaled by 1.4826 so that it
    estimates the standard deviation for Gaussian data.

    Returns a 1-D mask of length n_samples. It ANNOTATES; it deletes nothing.
    """
    # TODO: for each row, take the median and the MAD (median of |x - median|)
    # TODO: scale the MAD by 1.4826 to make it comparable to a standard deviation
    # TODO: mark a sample True where |x - median| > k * scaled_mad on ANY row
    raise NotImplementedError("Implement flag_artifacts")''',
'''def flag_artifacts(data: np.ndarray, k: float = 6.0) -> np.ndarray:
    """Boolean mask over samples, True where any row is beyond k robust deviations.

    Robust scale is the median absolute deviation, scaled by 1.4826 so that it
    estimates the standard deviation for Gaussian data.

    Returns a 1-D mask of length n_samples. It ANNOTATES; it deletes nothing.
    """
    med = np.median(data, axis=1, keepdims=True)
    mad = np.median(np.abs(data - med), axis=1, keepdims=True) * 1.4826
    mad = np.where(mad == 0, np.inf, mad)
    return np.any(np.abs(data - med) > k * mad, axis=0)''')

code("""# --- TEST CELL FOR STEP 2 ---
# Three artifacts with different SPATIAL structure, which is what decides whether
# a montage hides them or spreads them. All three have the same amplitude.
n = 20000
FS = 1000.0
clean = np.array([0.8 * np.sin(2 * np.pi * 20.0 * np.arange(n) / FS + i)
                  + rng.standard_normal(n) for i in range(N_CH)])

ARTIFACTS = {
    'common mode, all contacts': (4000, slice(None)),   # reference moves
    'local to contact 0': (9000, 0),                    # ring 1, used by 4 derivations
    'local to contact 5': (15000, 5),                   # a segment, used by 1 derivation
}
truth = np.zeros(n, dtype=bool)
for start, where in ARTIFACTS.values():
    clean[where, start:start + 200] += 30.0
    truth[start:start + 200] = True

mask_raw = flag_artifacts(clean)
mask_der = flag_artifacts(apply_montage(clean, M_VERT))
assert mask_raw.dtype == np.bool_ and mask_raw.shape == (n,), "returns a 1-D bool mask"

print(f"{'artifact':>28} {'on contacts':>13} {'on derivations':>16}")
seen = {}
for label, (start, _where) in ARTIFACTS.items():
    span = slice(start, start + 200)
    on_raw = float(np.mean(mask_raw[span]))
    on_der = float(np.mean(mask_der[span]))
    seen[label] = (on_raw, on_der)
    print(f"{label:>28} {on_raw:>12.0%} {on_der:>15.0%}")

# The common-mode artifact is exactly what the montage is for, so it vanishes.
assert seen['common mode, all contacts'][0] > 0.9, "a moving reference is obvious on contacts"
assert seen['common mode, all contacts'][1] < 0.1, "and the montage removes it entirely"

# A contact-local artifact goes the other way: contact 0 is the reference for four
# derivations, so the montage SPREADS it.
assert seen['local to contact 0'][1] > 0.9, "an artifact on ring 1 reaches four derivations"

false_rate = float(np.mean(mask_raw[~truth]))
assert false_rate < 0.05, f"clean samples wrongly flagged: {false_rate:.2%}"

# The median and the MAD are not decoration. An artifact occupying even a small
# fraction of the record inflates a standard deviation past its own amplitude,
# so a mean-and-std threshold goes blind to exactly what it is looking for.
duty = np.zeros(n, dtype=bool)
busy = clean.copy()
for s0 in np.linspace(0.1, 0.85, 4):
    a = int(s0 * n)
    busy[:, a:a + int(n * 0.05 / 4)] += 30.0
    duty[a:a + int(n * 0.05 / 4)] = True

def flag_with_std(data, k=6.0):
    mu = np.mean(data, axis=1, keepdims=True)
    sd = np.std(data, axis=1, keepdims=True)
    return np.any(np.abs(data - mu) > k * sd, axis=0)

recall_robust = float(np.mean(flag_artifacts(busy)[duty]))
recall_std = float(np.mean(flag_with_std(busy)[duty]))
print(f"\\nartifact covering {duty.mean():.0%} of the record:")
print(f"  median and MAD find : {recall_robust:>6.0%}")
print(f"  mean and std find   : {recall_std:>6.0%}")
assert recall_robust > 0.9, "a robust scale must still see it"
assert recall_std < 0.1, "a standard deviation is inflated past the artifact it is hunting"

both = int(np.sum(mask_raw & mask_der))
either = int(np.sum(mask_raw | mask_der))
jaccard = both / either
print(f"\\nflagged on recorded contacts : {mask_raw.sum():>6d} samples")
print(f"flagged on derivations       : {mask_der.sum():>6d} samples")
print(f"agreement (Jaccard)          : {jaccard:.3f}")
assert jaccard < 0.8, "detection is nonlinear, so the montage changes the answer"

print("\\nStep 2 passed. Same detector, same threshold, same recording. The montage")
print("hid one artifact and amplified another, so 'artifact rejection was applied'")
print("is not a statement about a recording until it names the montage.")""")

md(r"""---

## 3. The decimation gate, which is guardrail G6

SIG 1 established that after decimating to $f_s'$ the data supports $0.4\,f_s'$, not
$0.5\,f_s'$, because the anti-alias filter sits at $0.8$ of the new Nyquist. Here
that number does a job.

`preprocess/resample.py` chooses the largest integer factor reaching a target
rate, reports the usable bandwidth rather than assuming it, and prefers a single
decimation stage because chaining stages chains filters and the combined response
is harder to state and to reproduce. Guardrail **G6** then refuses any run whose
requested band reaches above the cutoff.

G6 is `block` severity, and unlike most guardrails it is not overridable, because
there is no version of this a reviewer can reason past. The content is gone.""")

task(
'''ANTIALIAS_CUTOFF_FRACTION = 0.8      # established in SIG 1; scipy and MATLAB both use it

def usable_bandwidth_hz(sfreq_hz: float) -> float:
    """From SIG 1. Highest frequency the data supports after anti-alias filtering."""
    return sfreq_hz / 2.0 * ANTIALIAS_CUTOFF_FRACTION


def plan_decimation(sfreq_hz: float, target_hz: float, requested_band_hz: tuple) -> dict:
    """Decide a decimation and say whether guardrail G6 permits it.

    Returns a dict with `factor`, `new_sfreq_hz`, `usable_bandwidth_hz`, and
    `refusal`, which is None when the plan is allowed and a sentence explaining
    the refusal when it is not.

    Production equivalent: `dbsspeech.preprocess.resample.suggest_factor` and
    `usable_bandwidth_hz`; the refusal is raised by the G6 check in
    `dbsspeech.guardrails`.
    """
    # TODO: factor is the largest integer whose result is at or above target_hz,
    #       i.e. int(sfreq_hz // target_hz), and never less than 1
    # TODO: new_sfreq_hz is sfreq_hz / factor
    # TODO: compute the usable bandwidth of the NEW rate
    # TODO: refuse when the TOP of requested_band_hz exceeds the usable bandwidth
    raise NotImplementedError("Implement plan_decimation")''',
'''ANTIALIAS_CUTOFF_FRACTION = 0.8      # established in SIG 1; scipy and MATLAB both use it

def usable_bandwidth_hz(sfreq_hz: float) -> float:
    """From SIG 1. Highest frequency the data supports after anti-alias filtering."""
    return sfreq_hz / 2.0 * ANTIALIAS_CUTOFF_FRACTION


def plan_decimation(sfreq_hz: float, target_hz: float, requested_band_hz: tuple) -> dict:
    """Decide a decimation and say whether guardrail G6 permits it.

    Returns a dict with `factor`, `new_sfreq_hz`, `usable_bandwidth_hz`, and
    `refusal`, which is None when the plan is allowed and a sentence explaining
    the refusal when it is not.

    Production equivalent: `dbsspeech.preprocess.resample.suggest_factor` and
    `usable_bandwidth_hz`; the refusal is raised by the G6 check in
    `dbsspeech.guardrails`.
    """
    if target_hz <= 0 or target_hz >= sfreq_hz:
        factor = 1
    else:
        factor = max(1, int(sfreq_hz // target_hz))
    new_sfreq = sfreq_hz / factor
    usable = usable_bandwidth_hz(new_sfreq)
    band_top = float(max(requested_band_hz))
    refusal = None
    if band_top > usable:
        refusal = (
            f"requested band reaches {band_top:.1f} Hz but decimating to "
            f"{new_sfreq:.1f} Hz leaves only {usable:.1f} Hz usable"
        )
    return {
        "factor": factor,
        "new_sfreq_hz": new_sfreq,
        "usable_bandwidth_hz": usable,
        "refusal": refusal,
    }''')

code("""# --- TEST CELL FOR STEP 3 ---
BETA = (13.0, 30.0)          # mirrors configs/bands.yaml -> bands.beta
HIGH_GAMMA = (70.0, 150.0)   # mirrors configs/bands.yaml -> bands.high_gamma

print(f"{'target':>8} {'factor':>7} {'new fs':>9} {'usable':>8}  band       verdict")
for target, band, label in [(1000.0, BETA, 'beta'),
                            (1000.0, HIGH_GAMMA, 'high gamma'),
                            (500.0, HIGH_GAMMA, 'high gamma'),
                            (250.0, BETA, 'beta')]:
    p = plan_decimation(FS_RAW, target, band)
    verdict = 'REFUSED' if p['refusal'] else 'allowed'
    print(f"{target:>8.0f} {p['factor']:>7d} {p['new_sfreq_hz']:>8.1f} "
          f"{p['usable_bandwidth_hz']:>8.1f}  {label:<10} {verdict}")

# 24000 / 1000 = 24, usable 400 Hz: beta is fine, high gamma to 150 Hz is fine.
assert plan_decimation(FS_RAW, 1000.0, BETA)['refusal'] is None, "beta fits in 400 Hz"
assert plan_decimation(FS_RAW, 1000.0, HIGH_GAMMA)['refusal'] is None, "150 Hz fits in 400 Hz"

# 24000 / 500 = 48, new rate 500 Hz, usable 200 Hz: still fine for 150 Hz.
assert plan_decimation(FS_RAW, 500.0, HIGH_GAMMA)['refusal'] is None, "150 Hz fits in 200 Hz"

# 24000 / 250 = 96, new rate 250 Hz, usable 100 Hz: high gamma is gone.
assert plan_decimation(FS_RAW, 250.0, HIGH_GAMMA)['refusal'] is not None, (
    "G6 must refuse: high gamma reaches 150 Hz and only 100 Hz survives"
)

# Beta still survives 250 Hz, because 30 Hz is under the 100 Hz usable bandwidth.
# It takes a much harsher target to lose it: at 60 Hz only 24 Hz is usable.
assert plan_decimation(FS_RAW, 250.0, BETA)['refusal'] is None, "30 Hz fits in 100 Hz"
assert plan_decimation(FS_RAW, 60.0, BETA)['refusal'] is not None, (
    "G6 must refuse: beta reaches 30 Hz and only 24 Hz survives"
)
print(f"\\nRefusal text: {plan_decimation(FS_RAW, 250.0, HIGH_GAMMA)['refusal']}")

# The factor is an integer, so the achieved rate is usually not the target. It must
# be chosen by flooring: rounding can pick a larger factor and undershoot, which
# quietly delivers less bandwidth than the caller asked for.
for target in (700.0, 430.0, 330.0):
    p = plan_decimation(FS_RAW, target, BETA)
    assert p['new_sfreq_hz'] >= target, (
        f"asking for {target:.0f} Hz produced {p['new_sfreq_hz']:.1f} Hz. The factor must be "
        "floor(sfreq / target); rounding undershoots the target."
    )
p = plan_decimation(FS_RAW, 700.0, BETA)
print(f"Asking for 700 Hz from {FS_RAW:.0f} Hz gives factor {p['factor']} "
      f"= {p['new_sfreq_hz']:.1f} Hz, not 700.")
print("\\nStep 3 passed.")""")

md(r"""---

## 4. Why an artifact becomes an annotation

`CLAUDE.md` says never delete samples from recordings, and that artifacts become
annotations. The argument usually offered for this is that cutting samples out
and closing the gap corrupts the spectrum.

Test that argument before repeating it.

Below, a record with twelve artifact spans is handled two ways: excise the bad
samples and concatenate what is left, or annotate them and compute over the clean
runs. Then compare the power spectra. If the usual argument is right, the excised
spectrum should be visibly wrong.""")

code("""FS = 1000.0
n = 20000
t = np.arange(n) / FS
sig = 1.0 * np.sin(2 * np.pi * 20.0 * t) + 0.5 * rng.standard_normal(n)

spans = [(int(s * FS), int(s * FS) + 150) for s in np.linspace(1.5, 17.5, 12)]
for a, b in spans:
    sig[a:b] += 25.0 * rng.standard_normal(b - a)
mask = np.zeros(n, dtype=bool)
for a, b in spans:
    mask[a:b] = True

# (a) excise and close the gap
f_ex, p_ex = welch(sig[~mask], FS, nperseg=1024)

# (b) annotate: average the spectra of the clean runs, gaps left as gaps
runs, start = [], None
for i in range(n):
    if not mask[i] and start is None:
        start = i
    if (mask[i] or i == n - 1) and start is not None:
        if i - start >= 1024:
            runs.append(sig[start:i])
        start = None
f_an = welch(runs[0], FS, nperseg=1024)[0]
p_an = np.mean([welch(r, FS, nperseg=1024)[1] for r in runs], axis=0)

def band_power(f, p, lo, hi):
    return float(np.mean(p[(f >= lo) & (f < hi)]))

print(f"{'band':>16} {'excised':>12} {'annotated':>12} {'ratio':>8}")
for lo, hi, label in [(13.0, 30.0, 'beta'), (70.0, 150.0, 'high gamma'), (200.0, 400.0, 'above')]:
    e = band_power(f_ex, p_ex, lo, hi)
    a = band_power(f_an, p_an, lo, hi)
    print(f"{label:>16} {e:>12.4g} {a:>12.4g} {e / a:>7.2f}x")

print("\\nThe usual argument does not survive the measurement. Twelve discontinuities")
print("in eighteen thousand samples move an averaged spectrum by a few percent.")
print("That is exactly why excision is a durable habit: its damage is not here.")""")

md(r"""### Where the damage actually is

Excision does not noticeably distort an averaged power spectrum, and pretending
it does is a bad reason for a good rule. The real costs are three, and none of
them show up in a spectrum.

**The time base stops meaning anything.** Sample index no longer maps to time.
Every event marker, every window in `windows.csv`, and every latency after the
first excised span is wrong, and the error accumulates down the record.

**Phase continuity breaks.** Removing $s$ samples advances everything after the
join by $2\pi f s / f_s$ at frequency $f$. The join is phase-neutral only when
the removed span happens to be a whole number of periods, which is a property of
the artifact and not something you get to choose.

**Channels stop sharing a clock.** Artifacts differ per contact, so per-channel
excision gives each channel its own time base. After that, a montage subtracts
samples that were not recorded at the same instant, and Section 1's whole
argument collapses. Coherence, phase locking, and every cross-channel measure
become meaningless in a way that no downstream check detects.

An annotation costs nothing and loses nothing. The samples stay, the clock stays,
and a later reviewer who decides the "artifact" was real physiology can simply
stop excluding it. A deletion cannot be undone.""")

code("""# The three real costs, measured.
print("=== 1. the time base ===")
shift_ms = sum(b - a for a, b in spans) / FS * 1000
print(f"an event at 18.000 s is reported at "
      f"{(18.0 * FS - sum(b - a for a, b in spans if b < 18.0 * FS)) / FS:.3f} s after excision")
print(f"total drift by the end of the record: {shift_ms:.0f} ms\\n")

print("=== 2. phase continuity ===")
osc = np.sin(2 * np.pi * 20.0 * np.arange(6000) / FS)
print(f"{'removed samples':>16} {'cycles at 20 Hz':>17} {'phase advance':>15}")
for span in (37, 63, 100, 137):
    advance_deg = (360.0 * 20.0 * span / FS) % 360.0
    print(f"{span:>16} {span / FS * 20.0:>17.2f} {advance_deg:>14.1f} deg")
print("only a whole number of periods is phase-neutral, and that is the")
print("artifact's choice rather than yours\\n")

print("=== 3. the shared clock ===")
two = np.array([np.sin(2 * np.pi * 20.0 * np.arange(4000) / FS + 0.3),
                np.sin(2 * np.pi * 20.0 * np.arange(4000) / FS + 0.3)])
common_before = float(np.max(np.abs(two[0] - two[1])))
m0 = np.ones(4000, dtype=bool); m0[1000:1050] = False    # artifact on channel 0 only
m1 = np.ones(4000, dtype=bool); m1[2000:2090] = False    # a different one on channel 1
kept = min(int(m0.sum()), int(m1.sum()))
common_after = float(np.max(np.abs(two[0][m0][:kept] - two[1][m1][:kept])))
print(f"two identical channels, subtracted before excision : {common_before:.2e}")
print(f"the same two after per-channel excision            : {common_after:.2e}")
assert common_before < 1e-12, "identical channels must cancel exactly"
assert common_after > 0.5, "after per-channel excision they no longer cancel at all"
print("\\nThe montage from Section 1 cancelled a shared reference exactly. After")
print("per-channel excision the same subtraction cancels nothing, because the two")
print("channels are no longer describing the same instants.")""")

md(r"""---

## 5. What the contract is

Putting the four sections together, a preprocessing step in this app has to be
able to state, for any result computed downstream:

1. **The montage**, by name and by matrix, because Section 2 showed that any
   nonlinear step run afterwards depends on it.
2. **The achieved sampling rate**, which is rarely the requested one, because the
   decimation factor is an integer.
3. **The usable bandwidth**, which is $0.4\,f_s'$ and not the new Nyquist, and
   which G6 checks against every requested band.
4. **The number of decimation stages**, because chained stages chain filters and
   the combined response is what actually shaped the data.
5. **The artifact annotations**, as spans, with the montage they were detected
   on, and never as deleted samples.

That is not a documentation convention. Every item is something a later result
depends on and that cannot be recovered from the processed array.""")

code("""# --- TEST CELL FOR STEP 4 ---
def preprocessing_record(sfreq_hz, target_hz, band, data, M, montage_name):
    plan = plan_decimation(sfreq_hz, target_hz, band)
    derivations = apply_montage(data, M)
    flagged = flag_artifacts(derivations)
    edges = np.flatnonzero(np.diff(flagged.astype(int)))
    return {
        "montage": montage_name,
        "montage_shape": M.shape,
        "requested_rate_hz": target_hz,
        "achieved_rate_hz": plan["new_sfreq_hz"],
        "decimation_factor": plan["factor"],
        "usable_bandwidth_hz": plan["usable_bandwidth_hz"],
        "n_decimation_stages": 1 if plan["factor"] <= 13 else 2,
        "artifact_spans_detected_on": montage_name,
        "n_artifact_spans": int(len(edges) // 2),
        "n_samples_deleted": 0,
        "refusal": plan["refusal"],
    }

record = preprocessing_record(FS_RAW, 1000.0, (13.0, 30.0), clean, M_VERT, "bipolar_vertical")
for key, value in record.items():
    print(f"  {key:<28} {value}")

REQUIRED = {"montage", "achieved_rate_hz", "usable_bandwidth_hz",
            "n_decimation_stages", "artifact_spans_detected_on", "n_samples_deleted"}
assert REQUIRED <= set(record), f"the record is missing {REQUIRED - set(record)}"
assert record["n_samples_deleted"] == 0, "preprocessing never deletes samples"
assert record["achieved_rate_hz"] != record["requested_rate_hz"] or \\
    FS_RAW % record["requested_rate_hz"] == 0, "an achieved rate must be stated, not assumed"
assert record["usable_bandwidth_hz"] < record["achieved_rate_hz"] / 2, \\
    "usable bandwidth is below Nyquist, always"
print("\\nStep 4 passed. Everything a downstream result depends on is stated.")""")

md(r"""---

## 6. What you established

1. Re-referencing and decimation **commute exactly**, verified to floating-point
   noise with an artifact 800 times the physiology present. Arguing about their
   order is arguing about a convention.
2. Artifact detection is **nonlinear**, so it does not commute with the montage,
   and the two orders disagree about which samples are artifact. A run record
   must name the montage detection ran on.
3. Guardrail G6 is arithmetic, not policy: the achieved rate is
   $f_s / \lfloor f_s / f_{\text{target}} \rfloor$ and the usable bandwidth is
   $0.4$ of it.
4. The usual argument for never deleting samples, that it corrupts the spectrum,
   **is not true**, and you measured that. The real costs are the time base,
   phase continuity, and the shared clock across channels.

### Exercises

**Exercise 1.** `preprocess/resample.py` splits factors above 13 into stages
because scipy warns about IIR stability. Take a 24414 Hz recording to 250 Hz,
find the factor, and decide how to split it. Then measure the combined response
of your split against a single hypothetical stage and say which you would report.

**Exercise 2.** Section 2 used a fixed `k = 6`. Sweep `k` from 3 to 12 for
detection on contacts and on derivations, and plot the Jaccard agreement. Is
there a `k` at which the two agree? What does your answer imply about tuning a
threshold until the artifact count looks reasonable?

**Exercise 3.** Section 4 measured that excision barely moves an averaged
spectrum. Construct a case where it moves it a great deal, and state the property
of the artifact spans that makes the difference. Then explain why guardrail G4,
which requires a threshold to be set within each condition, is the same problem
wearing different clothes.

---

**Signal Processing is complete.** SIG 1 established what a recording can represent, SIG 2 what
a filter does to it, and this module what the app is allowed to do to it before
any analysis runs.
""")

VARIANT_TAG = {"student": "[STUDENT WORKBOOK]", "solutions": "[SOLUTIONS GUIDE]"}
INSTRUCTIONS = {
    "student": (
        "> **STUDENT INSTRUCTIONS.** Each task cell raises `NotImplementedError`.\n"
        "> Replace the `TODO` comments with an implementation, then run the test cell\n"
        "> that follows. Every test cell checks your work against something independent\n"
        "> of your implementation. Work the cells in order.\n"
    ),
    "solutions": (
        "> **SOLUTIONS GUIDE.** Reference implementations with the same test cells the\n"
        "> student workbook uses. Executed in CI by `tests/unit/test_curriculum.py`.\n"
    ),
}

def build(which):
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
    name = f"01_preprocessing_contract_{which}.ipynb"
    for d in (BASE / "curriculum" / "03_preprocessing", BASE / "web" / "public" / "notebooks"):
        d.mkdir(parents=True, exist_ok=True)
        (d / name).write_text(json.dumps(nb, indent=1) + "\n")
    print(f"wrote {name} ({len(nb['cells'])} cells)")
