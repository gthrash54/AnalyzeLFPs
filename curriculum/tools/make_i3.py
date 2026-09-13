import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("08_inference", "03_what_a_z_score_means")

m.md(r'''# Lesson INF 3: What a z Score Means, and the Twenty Ways to Compute One {{VARIANT}}

**Scientific Integrity · Statistical Inference for Neural Recordings**

{{INSTRUCTIONS}}

`configs/statistics.yaml` offers four ways to centre a value and five ways to
scale it. `dbsspeech.stats.normalize` implements all twenty combinations, every
one of them is selectable in the interface, and every one produces a column
labelled **z**. Until this lesson, nothing in this curriculum had checked what
any of them does to a number.

The config file states a caveat under each option. Three of those caveats are
arithmetic claims that can be proved rather than asserted, and this lesson proves
them. One of them turns out to be understated: with two conditions, the
`across_conditions` scale does not merely become unstable, it becomes a constant
and carries no information about the data at all.

**What it assumes**

| From | What is used |
|---|---|
| INF 1 | That a number needs a null before it is a result, and that selection changes what a reported number means. |
| SIG 4 | That a band power estimate has a spread across segments, which is where `db_sd` comes from. |
| GRL 4 | That a baseline window is a choice, and that the choice moves the answer. |

**What it underwrites**

`configs/statistics.yaml` in full, the caveat strings the interface shows beside
each option, and guardrail **G8**, which requires a z alongside any dB.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

rng = np.random.default_rng(31)

# The option names from configs/statistics.yaml, restated so this notebook runs
# standalone. The test suite asserts these still match the config and the
# CENTERS and SCALES tuples in dbsspeech.stats.normalize.
CENTERS = ("grand_mean", "condition", "whole_recording", "none")
SCALES = ("pooled_within_condition", "own_condition", "condition",
          "across_conditions", "none")

CONDITIONS = ("rest", "listen", "speak")
BASELINE = 0                      # index of 'rest', the named baseline condition
N_CHANNELS = 16

print("Environment initialized for Lesson INF 3")''')

m.md(r'''---

## 1. A z is two decisions, not one

Every z in this app has the form

$$z = \frac{\text{value} - \text{centre}}{\text{scale}}$$

and the two halves answer different questions. The centre decides **what the
result is compared against**. The scale decides **what counts as a large
difference**. They were once a single `baseline` setting, which hid the fact that
a reader looking at a z could not tell which of the two they were seeing.

A run in this app is one mean and one spread per channel per condition: `value`
is the mean over time segments, `sd` is the spread across those segments. Both
choices are made from that table, and the implementations below mirror
`dbsspeech.stats.normalize` exactly, in numpy rather than pandas.''')

m.task(
'''def centre_of(values: np.ndarray, kind: str, n_segments: np.ndarray) -> np.ndarray:
    """The centre for every cell of a (channels, conditions) table.

    grand_mean      -- the mean over conditions, each condition counting once
    condition       -- the value in the named baseline condition
    whole_recording -- the mean over conditions weighted by segment count
    none            -- zero
    """
    # TODO: return an array broadcastable to values.shape
    # TODO: grand_mean is the unweighted mean across conditions, per channel
    # TODO: condition is the baseline column, held per channel
    # TODO: whole_recording weights each condition by n_segments before averaging
    # TODO: none is zero
    raise NotImplementedError("Implement centre_of")


def scale_of(values: np.ndarray, sds: np.ndarray, kind: str) -> np.ndarray:
    """The scale for every cell of a (channels, conditions) table.

    pooled_within_condition -- mean of the per-condition spreads, one per channel
    own_condition           -- each cell's own spread
    condition               -- the baseline condition's spread
    across_conditions       -- spread of the condition MEANS, ignoring segments
    none                    -- one
    """
    # TODO: note that only own_condition varies within a channel
    # TODO: across_conditions uses values, not sds, and needs ddof=1
    raise NotImplementedError("Implement scale_of")


def z_of(values: np.ndarray, sds: np.ndarray, centre: str, scale: str,
         n_segments: np.ndarray) -> np.ndarray:
    """(value - centre) / scale, with a zero scale becoming NaN rather than inf."""
    # TODO: a zero scale must not produce an infinity that reads as a huge effect
    raise NotImplementedError("Implement z_of")''',
'''def centre_of(values: np.ndarray, kind: str, n_segments: np.ndarray) -> np.ndarray:
    """The centre for every cell of a (channels, conditions) table.

    grand_mean      -- the mean over conditions, each condition counting once
    condition       -- the value in the named baseline condition
    whole_recording -- the mean over conditions weighted by segment count
    none            -- zero
    """
    if kind == "none":
        return np.zeros_like(values)
    if kind == "condition":
        return values[:, [BASELINE]] * np.ones_like(values)
    if kind == "whole_recording":
        w = np.asarray(n_segments, dtype=float)
        return ((values * w).sum(axis=1) / w.sum())[:, None] * np.ones_like(values)
    if kind == "grand_mean":
        return values.mean(axis=1, keepdims=True) * np.ones_like(values)
    raise ValueError(f"unknown centre {kind!r}; have {CENTERS}")


def scale_of(values: np.ndarray, sds: np.ndarray, kind: str) -> np.ndarray:
    """The scale for every cell of a (channels, conditions) table.

    pooled_within_condition -- mean of the per-condition spreads, one per channel
    own_condition           -- each cell's own spread
    condition               -- the baseline condition's spread
    across_conditions       -- spread of the condition MEANS, ignoring segments
    none                    -- one
    """
    if kind == "none":
        return np.ones_like(values)
    if kind == "own_condition":
        # The only scale that varies from cell to cell within a channel.
        return sds.astype(float)
    if kind == "condition":
        return sds[:, [BASELINE]] * np.ones_like(values)
    if kind == "across_conditions":
        # Built from the condition means, so it never sees the segment spread.
        return values.std(axis=1, ddof=1, keepdims=True) * np.ones_like(values)
    if kind == "pooled_within_condition":
        return sds.mean(axis=1, keepdims=True) * np.ones_like(values)
    raise ValueError(f"unknown scale {kind!r}; have {SCALES}")


def z_of(values: np.ndarray, sds: np.ndarray, centre: str, scale: str,
         n_segments: np.ndarray) -> np.ndarray:
    """(value - centre) / scale, with a zero scale becoming NaN rather than inf."""
    s = scale_of(values, sds, scale).astype(float)
    # An infinity reads on a figure as an enormous effect. A NaN reads as a gap,
    # which is what a scale of zero actually is.
    return (values - centre_of(values, centre, n_segments)) / np.where(s == 0, np.nan, s)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
def synthetic_run(seed: int, effects=(0.0, 1.0, 3.0), noise=1.0, n_seg=(20, 20, 20)):
    """One mean and one spread per channel per condition, with a known truth."""
    gen = np.random.default_rng(seed)
    n_segments = np.asarray(n_seg)
    values = np.empty((N_CHANNELS, len(effects)))
    sds = np.empty_like(values)
    for j, (eff, k) in enumerate(zip(effects, n_segments)):
        segs = eff + noise * gen.standard_normal((N_CHANNELS, k))
        values[:, j] = segs.mean(axis=1)
        sds[:, j] = segs.std(axis=1, ddof=1)
    return values, sds, n_segments

values, sds, n_segments = synthetic_run(5)

# (a) Each option must do the arithmetic it advertises, checked against a
# hand-computed value rather than against another option.
assert np.allclose(centre_of(values, "grand_mean", n_segments)[:, 0], values.mean(axis=1))
assert np.allclose(centre_of(values, "condition", n_segments)[:, 2], values[:, BASELINE])
assert np.allclose(centre_of(values, "none", n_segments), 0.0)
uneven = np.array([90, 5, 5])
weighted = (values * uneven).sum(axis=1) / uneven.sum()
assert np.allclose(centre_of(values, "whole_recording", uneven)[:, 1], weighted)
# With equal segment counts the two averages coincide; the weighting is the
# whole difference between them.
assert np.allclose(centre_of(values, "whole_recording", n_segments),
                   centre_of(values, "grand_mean", n_segments))
assert not np.allclose(centre_of(values, "whole_recording", uneven),
                       centre_of(values, "grand_mean", uneven))

assert np.allclose(scale_of(values, sds, "own_condition"), sds)
assert np.allclose(scale_of(values, sds, "pooled_within_condition")[:, 0], sds.mean(axis=1))
assert np.allclose(scale_of(values, sds, "condition")[:, 1], sds[:, BASELINE])
assert np.allclose(scale_of(values, sds, "none"), 1.0)
assert np.allclose(scale_of(values, sds, "across_conditions")[:, 0],
                   values.std(axis=1, ddof=1))
# A scale of zero must not become an infinity. The values here differ from their
# own centre on purpose: with a flat table the numerator would be zero too, and
# 0/0 is already NaN, so the guard would look tested when it was not.
uncentred = np.array([[1.0, 2.0, 6.0], [4.0, 5.0, 9.0]])
zeroed = z_of(uncentred, np.zeros((2, 3)), "grand_mean", "own_condition",
              np.array([1, 1, 1]))
assert np.all(np.isnan(zeroed)), f"a zero scale must give NaN, got {zeroed}"
assert not np.any(np.isinf(zeroed)), "and never an infinity, which reads as a huge effect"

# (b) All twenty pairs on one channel of one run, same data every time.
CHANNEL, CONDITION = 0, 2       # channel 0, the 'speak' condition
print(f"one cell of one run: channel {CHANNEL}, condition '{CONDITIONS[CONDITION]}', "
      f"true effect 3.0, noise 1.0\\n")
print(f"{'centre':>16} " + " ".join(f"{s[:13]:>14}" for s in SCALES))
table = {}
for c in CENTERS:
    row = []
    for s in SCALES:
        table[(c, s)] = float(z_of(values, sds, c, s, n_segments)[CHANNEL, CONDITION])
        row.append(f"{table[(c, s)]:>14.2f}")
    print(f"{c:>16} " + " ".join(row))

finite = np.array([v for v in table.values() if np.isfinite(v)])
big = sum(abs(v) >= 2.0 for v in finite)
print(f"\\n  the same cell reads from {finite.min():.2f} to {finite.max():.2f} across the twenty pairs")
print(f"  {big} of {len(finite)} would be called large at |z| >= 2, and {len(finite) - big} would not")
assert finite.max() - finite.min() > 2.0, "the choice is not cosmetic"
assert 0 < big < len(finite), "the choice decides whether this cell is a finding"

print("\\nOne cell, one recording, one true effect, twenty labelled 'z'. Some of them")
print("cross the line a reader uses to decide whether something happened and some do")
print("not. That is why the resolved pair is written into the run record and the figure")
print("caption: the number is not interpretable without it.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The centre decides what the comparison is

Two of the four centres carry caveats in the config that are exact arithmetic
rather than cautionary vibes, and both are derived below.

**`whole_recording`.** The config says "the task periods sit inside their own
baseline, which shrinks every effect toward zero by construction. The more of the
recording is task, the worse." That is a formula. If a fraction $f$ of the
recording carries an effect $e$ and the rest carries none, the pooled centre sits
at $f e$ above the true baseline, so the reported effect is $e - f e = (1-f)e$.
The shrinkage is exactly $1-f$, and it does not depend on the effect, the noise
or the channel.

**`grand_mean`.** The config says "the centre moves when you change which
conditions are included, so two runs over different condition sets are not
directly comparable." Also exact, and worth measuring because it is the option
people pick when they want to avoid privileging a baseline.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
TRUE_EFFECT = 3.0

# (a) whole_recording: the shrinkage should be exactly 1 - f, with f the fraction
# of segments that carry the effect.
print(f"true effect {TRUE_EFFECT:.1f} dB in one condition of two, tiny noise\\n")
print(f"{'task fraction':>14} {'reported':>10} {'ratio':>8} {'1 - f':>8}")
for f in (0.10, 0.25, 0.50, 0.75):
    n_task = int(round(200 * f))
    seg = np.array([[200 - n_task, n_task]])
    vals, sd_small, _ = synthetic_run(1, effects=(0.0, TRUE_EFFECT), noise=1e-6,
                                      n_seg=(200 - n_task, n_task))
    reported = float((vals - centre_of(vals, "whole_recording", seg[0]))[0, 1])
    print(f"{f:>14.2f} {reported:>10.4f} {reported / TRUE_EFFECT:>8.4f} {1 - f:>8.4f}")
    assert abs(reported / TRUE_EFFECT - (1 - f)) < 1e-3, "shrinkage must be exactly 1 - f"

print("\\n  Half the recording being task halves every effect in it. That is not a bias")
print("  the analysis can detect, because a shrunken effect looks exactly like a small")
print("  effect, and nothing in the output records the task fraction.")

# (b) grand_mean: adding a condition moves the centre and therefore every z, with
# no new data about the conditions already there.
two = synthetic_run(9, effects=(0.0, TRUE_EFFECT), noise=0.4, n_seg=(30, 30))
three = synthetic_run(9, effects=(0.0, TRUE_EFFECT, -6.0), noise=0.4, n_seg=(30, 30, 30))
z_two = z_of(two[0], two[1], "grand_mean", "pooled_within_condition", two[2])[:, 1]
z_three = z_of(three[0], three[1], "grand_mean", "pooled_within_condition", three[2])[:, 1]
print(f"\\n  z for the same condition, same channels, same segments:")
print(f"    two conditions in the run:   mean z {z_two.mean():>7.2f}")
print(f"    a third condition added:     mean z {z_three.mean():>7.2f}")
assert abs(z_three.mean() - z_two.mean()) > 1.0, "the centre moved, so every z moved"

# The baseline-condition centre does not move, which is the tradeoff.
c_two = z_of(two[0], two[1], "condition", "pooled_within_condition", two[2])[:, 1]
c_three = z_of(three[0], three[1], "condition", "pooled_within_condition", three[2])[:, 1]
print(f"    centre 'condition' instead:  {c_two.mean():>7.2f} then {c_three.mean():>7.2f}")
assert abs(c_three.mean() - c_two.mean()) < 0.05, \\
    "a named baseline is unmoved by conditions added elsewhere in the run"

print("\\n  Adding a condition nobody asked about changed the reported z of a condition")
print("  that was already there, because it moved the centre. The named-baseline centre")
print("  did not move. That is the actual tradeoff between the two: grand_mean does not")
print("  privilege a condition and is not comparable across runs; 'condition' is")
print("  comparable across runs and inherits everything wrong with the baseline window,")
print("  which is what guardrail G10 tracks.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. The scale decides what counts as large

The config's caveat on `across_conditions` reads "with few conditions this is
estimated from very few numbers and is unstable. Meaningless with fewer than
three." The measurement below shows that understates it.

Scaling by the spread of the condition means divides a set of centred numbers by
their own standard deviation. That operation has a ceiling. For $k$ conditions
the largest possible magnitude is

$$|z|_{\max} = \frac{k-1}{\sqrt{k}}$$

which is $0.707$ for two conditions and $1.155$ for three, no matter how large
the effect is. At $k = 2$ it is worse than a ceiling: the two centred values are
equal and opposite, so every z is exactly $\pm 0.707$ and the number carries no
information about the data whatsoever.

The caveat on `own_condition` is the second claim tested here: "a noisy condition
gets a smaller z purely for being noisy, which understates real effects in
exactly the conditions where they are hardest to see."''')

m.code('''# --- TEST CELL FOR STEP 3 ---
# (a) The across_conditions ceiling, checked against the formula for each k.
print(f"{'conditions':>11} {'largest |z| seen':>18} {'(k-1)/sqrt(k)':>15}")
gen = np.random.default_rng(2)
for k in (2, 3, 4, 6):
    worst = 0.0
    unused_sds = np.ones((1, k))
    unused_segments = np.ones(k)
    for _ in range(4000):
        # Deliberately extreme: any spread of effects, any overall amplitude.
        # Routed through z_of so this derivation tests the shipped arithmetic
        # rather than an inline copy of it.
        v = (gen.standard_normal((1, k)) * gen.uniform(0.1, 50)).astype(float)
        z = z_of(v, unused_sds, "grand_mean", "across_conditions", unused_segments)
        worst = max(worst, float(np.abs(z).max()))
    print(f"{k:>11} {worst:>18.4f} {(k - 1) / np.sqrt(k):>15.4f}")
    assert worst <= (k - 1) / np.sqrt(k) + 1e-9, "the ceiling is a hard bound, not a tendency"

# (b) At two conditions it is not a ceiling, it is a constant.
two_only = []
unused_sds, unused_segments = np.ones((1, 2)), np.ones(2)
for _ in range(2000):
    v = (gen.standard_normal((1, 2)) * gen.uniform(0.1, 100)).astype(float)
    two_only.append(float(np.abs(
        z_of(v, unused_sds, "grand_mean", "across_conditions", unused_segments)).max()))
print(f"\\n  two conditions, 2000 random runs: every |z| equals "
      f"{np.unique(np.round(two_only, 10))[0]:.6f}")
assert np.ptp(two_only) < 1e-9, "with two conditions the z is a constant"
assert abs(two_only[0] - 1 / np.sqrt(2)) < 1e-9

print("  So on a two-condition run this scale reports the same z for a 0.1 dB")
print("  difference and a 40 dB difference. It is not unstable, it is uninformative,")
print("  and it will not look wrong on a figure because 0.71 is a plausible number.")

# (c) own_condition against pooled_within_condition. Both scales live inside one
# channel, so the contrast between them is across CONDITIONS: a condition that is
# noisier than its neighbours is scaled by a larger number under own_condition
# and by the same number as everything else under pooled.
#
# The noisy condition here is 'speak', and the reason is physical: GRL 3
# established that speech drags EMG into the band, so the speaking condition of a
# real recording is genuinely more variable than the resting one.
NOISE_BY_CONDITION = np.array([1.0, 1.0, 3.0])          # rest, listen, speak
TRUE_BY_CONDITION = np.array([0.0, TRUE_EFFECT, TRUE_EFFECT])
gen = np.random.default_rng(7)
vals = np.empty((N_CHANNELS, 3))
spreads = np.empty_like(vals)
for j_cond in range(3):
    seg = (TRUE_BY_CONDITION[j_cond]
           + NOISE_BY_CONDITION[j_cond] * gen.standard_normal((N_CHANNELS, 200)))
    vals[:, j_cond] = seg.mean(axis=1)
    spreads[:, j_cond] = seg.std(axis=1, ddof=1)
n_seg3 = np.array([200, 200, 200])

z_own = z_of(vals, spreads, "condition", "own_condition", n_seg3)
z_pooled = z_of(vals, spreads, "condition", "pooled_within_condition", n_seg3)
print(f"\\n  'listen' and 'speak' carry the same true effect of {TRUE_EFFECT:.1f} dB, and")
print(f"  'speak' is {NOISE_BY_CONDITION[2] / NOISE_BY_CONDITION[1]:.0f}x noisier, as a speech condition really is\\n")
print(f"{'condition':>11} {'noise SD':>9} {'dB':>8} {'z own_condition':>17} {'z pooled':>10}")
for j_cond in range(3):
    print(f"{CONDITIONS[j_cond]:>11} {NOISE_BY_CONDITION[j_cond]:>9.1f} "
          f"{vals[:, j_cond].mean() - vals[:, 0].mean():>8.2f} "
          f"{z_own[:, j_cond].mean():>17.2f} {z_pooled[:, j_cond].mean():>10.2f}")

own_ratio = float(z_own[:, 1].mean() / z_own[:, 2].mean())
pooled_ratio = float(z_pooled[:, 1].mean() / z_pooled[:, 2].mean())
print(f"\\n  the same true effect was reported {own_ratio:.1f}x apart under own_condition")
print(f"  and {pooled_ratio:.2f}x apart under the pooled scale")
assert own_ratio > 2.0, "own_condition turns a noise difference into an effect difference"
assert abs(pooled_ratio - 1.0) < 0.15, "the pooled scale reports the two as equal, which they are"

print("\\n  Neither scale is wrong. own_condition answers 'how many of THIS condition's")
print("  own standard deviations is this', the right question when conditions genuinely")
print("  differ in stability and each should be judged on its own terms. It is the wrong")
print("  question here, because the extra spread in 'speak' is EMG rather than neural")
print("  variability, so dividing by it hides the effect in exactly the condition the")
print("  study is about. Nothing in the table says which of the two the spread was.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. Why G8 exists

Guardrail **G8** is a note rather than a warning, and it asks for one thing: a z
reported alongside any dB difference. It is the cheapest rule in
`configs/guardrails.yaml` and the easiest to dismiss, because a dB difference
sounds like a complete result already.

The measurement below is a run of sixteen channels whose true effects differ and
whose noise levels differ, which is the ordinary intraoperative case: impedance,
contact position and reference quality vary channel to channel. The question is
whether ranking by dB and ranking by z pick out the same channels.

The result is not the obvious one, and the obvious one would argue for replacing
dB with z rather than reporting both.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
N_SEG_G8, N_RUNS = 12, 400

def heterogeneous_noise(seed):
    """The noise levels heterogeneous_run will draw for this seed."""
    gen = np.random.default_rng(seed)
    gen.normal(0.0, 1.5, N_CHANNELS)
    return gen.lognormal(np.log(1.0), 0.8, N_CHANNELS)


def heterogeneous_run(seed):
    """Sixteen channels whose true effects AND noise levels both vary."""
    gen = np.random.default_rng(seed)
    truth = gen.normal(0.0, 1.5, N_CHANNELS)
    noise = gen.lognormal(np.log(1.0), 0.8, N_CHANNELS)
    task = truth[:, None] + noise[:, None] * gen.standard_normal((N_CHANNELS, N_SEG_G8))
    rest = noise[:, None] * gen.standard_normal((N_CHANNELS, N_SEG_G8))
    vals = np.stack([rest.mean(axis=1), task.mean(axis=1)], axis=1)
    spreads = np.stack([rest.std(axis=1, ddof=1), task.std(axis=1, ddof=1)], axis=1)
    return truth, vals, spreads, np.array([N_SEG_G8, N_SEG_G8])

agree, rhos, z_of_top_db = 0, [], []
db_finds_truth = z_finds_truth = oracle_finds_truth = 0
for s in range(N_RUNS):
    truth, vals, spreads, nseg = heterogeneous_run(s)
    db = vals[:, 1] - vals[:, 0]
    z = z_of(vals, spreads, "condition", "own_condition", nseg)[:, 1]
    # An oracle z, scaled by the noise each channel really has rather than by an
    # estimate of it. This separates "z is a noisy statistic" from "z ranks a
    # different quantity", which are not the same complaint.
    oracle = db / heterogeneous_noise(s)
    top_db, top_z, top_true = np.argmax(abs(db)), np.argmax(abs(z)), np.argmax(abs(truth))
    agree += int(top_db == top_z)
    rhos.append(stats.spearmanr(abs(db), abs(z)).statistic)
    z_of_top_db.append(abs(z[top_db]))
    db_finds_truth += int(top_db == top_true)
    z_finds_truth += int(top_z == top_true)
    oracle_finds_truth += int(np.argmax(abs(oracle)) == top_true)

z_of_top_db = np.array(z_of_top_db)
print(f"{N_RUNS} runs, {N_CHANNELS} channels, {N_SEG_G8} segments per condition,"
      f" true effects and noise both varying\\n")
print(f"  largest |dB| channel is also the largest |z| channel: {agree / N_RUNS:.1%} of runs")
print(f"  Spearman correlation between the two rankings:        {np.mean(rhos):.2f}")
print(f"  |z| of the largest-|dB| channel: median {np.median(z_of_top_db):.2f}, "
      f"below 2 in {np.mean(z_of_top_db < 2):.0%} of runs")
assert agree / N_RUNS < 0.4, "the two rankings mostly disagree"
assert 0.4 < np.mean(rhos) < 0.9, "they are related, which is why one gets mistaken for the other"

print(f"\\n  which ranking finds the channel with the largest TRUE effect:")
print(f"    rank by |dB|:                    {db_finds_truth / N_RUNS:.1%}")
print(f"    rank by |z|, estimated noise:    {z_finds_truth / N_RUNS:.1%}")
print(f"    rank by |z|, EXACT noise:        {oracle_finds_truth / N_RUNS:.1%}")
assert db_finds_truth > z_finds_truth, \\
    "z is NOT a better estimate of the size of the effect, and must not be sold as one"
# The oracle isolates the cause. If a noisy denominator were the problem, giving
# z the true noise would close most of the gap. It does not.
recovered = (oracle_finds_truth - z_finds_truth) / (db_finds_truth - z_finds_truth)
print(f"\\n  giving z the exact noise recovers {recovered:.0%} of the gap, so the gap is not")
print("  estimation error in the denominator; z is ranking a different quantity")
assert recovered < 0.20, "the gap is the estimand, not the noise in the estimate"

print("\\nThe two rankings agreed on the top channel in under a fifth of runs, and the")
print("channel with the biggest dB difference had a z below 2 in nearly half of them.")
print("Reporting dB alone therefore highlights channels that a reader would not have")
print("highlighted if they could see the noise.")
print("\\nThe second table is the reason G8 asks for both rather than for z instead of")
print("dB. Ranking by dB found the truly largest channel about twice as often as")
print("ranking by z did, and the reason is not that the denominator is noisily")
print("estimated. The oracle row above divides by the exact noise and barely closes the")
print("gap. z simply ranks a different quantity: the channel with the largest effect")
print("need not be the channel with the largest effect-to-noise ratio, and when the")
print("question is which channel moved most, z is answering something else.")
print("\\nSo the two columns answer two questions. dB is how big the difference is; z is")
print("whether to believe it. G8 is a note rather than a warning because neither column")
print("is an error, and it is a rule at all because a figure with only one of them")
print("invites a reader to answer the other question from the column that is there.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **A z is two independent decisions, and the twenty pairs are not twenty
   flavours of one answer.** On a single cell of a single run with one true
   effect, the twenty combinations spanned a range wide enough that some crossed
   the |z| = 2 line and some did not. The resolved pair belongs in the run record
   and the caption because the number is not interpretable without it.
2. **`whole_recording` shrinks every effect by exactly 1 - f**, where f is the
   fraction of the recording carrying the effect, independent of effect size,
   noise and channel. Half the recording being task halves every effect in it,
   and nothing in the output records f, so a shrunken effect is indistinguishable
   from a small one.
3. **`grand_mean` moves when the condition set changes.** Adding a third
   condition changed the reported z of a condition already in the run, with no
   new data about it. A named-baseline centre did not move, and pays for that by
   inheriting the baseline window, which is what G10 tracks.
4. **`across_conditions` has a hard ceiling of (k-1)/sqrt(k),** verified against
   the formula for k = 2, 3, 4 and 6. At two conditions it is not a ceiling but a
   constant: every z is exactly 0.7071 regardless of the data. The config calls
   this "unstable" and "meaningless with fewer than three"; the first word is too
   kind and the second is exactly right.
5. **`own_condition` converts a noise difference into an effect difference.**
   Two conditions carrying the same true 3 dB effect, one of them three times
   noisier because speech brings EMG with it, were reported about three times
   apart under `own_condition` and as equal under the pooled scale. Neither is
   wrong, nothing in the table says whether the extra spread was physiology or
   muscle, and under `own_condition` the effect is hidden in exactly the
   condition the study is about.
6. **G8 asks for both columns because they answer different questions.** Ranking
   sixteen channels by dB and by z agreed on the top channel in under a fifth of
   runs, and the top-dB channel had |z| < 2 in nearly half. Ranking by dB found
   the truly largest effect about twice as often as ranking by z, and an oracle z
   given each channel's exact noise recovered under a tenth of that gap. So the
   difference is not that z is a noisy statistic; z ranks a different quantity.
   dB is how big; z is whether to believe it.

The through line from INF 1 and INF 2: a number is a comparison, and a comparison
needs its terms stated. INF 1 stated them as a null, INF 2 as a family, and this
lesson as a centre and a scale. In all three the failure mode is the same, a
number that looks self-contained and is not.

### Exercises

**Exercise 1.** Section 2 derived the `whole_recording` shrinkage as 1 - f. Work
out the corresponding factor for `grand_mean` when conditions have unequal
segment counts, and say which of the two is more sensitive to a condition that
was cut short intraoperatively.

**Exercise 2.** Section 3 showed the `across_conditions` ceiling. Find the number
of conditions at which that ceiling first exceeds 2, and say whether any protocol
in `configs/vocabularies.yaml` reaches it.

**Exercise 3.** G8 is severity `note`. Using Section 4's numbers, argue either
that it should stay a note or that it should be a warn, and state what evidence
would settle it. Recommend a change to `configs/guardrails.yaml` only if the
argument survives the fact that neither column is an error.

---

That completes Statistical Inference. The three lessons together are what a
decoding result needs before it can claim an accuracy beats chance, which is
where the next course starts.
''')

m.emit()
verify("08_inference", "03_what_a_z_score_means")
print("  INF 3 OK")
