import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("08_inference", "02_multiple_comparisons_and_clusters")

m.md(r'''# Lesson INF 2: Multiple Comparisons and the Cluster Permutation Test {{VARIANT}}

**Scientific Integrity · Statistical Inference for Neural Recordings**

{{INSTRUCTIONS}}

INF 1 built one null for one comparison. Nothing in this app makes one
comparison. A time-frequency map from `tfr_onset` is a few thousand cells, each
of which could be tested; a channel-by-band table is a few hundred. Asking the
same question that many times changes what a p-value of 0.05 means, and the
change is larger than most people expect and smaller than the textbook formula
predicts.

This lesson builds the correction this field actually uses, the **cluster
permutation test**, from the pieces INF 1 established. It also establishes the
thing that test does not give you, which is the part that gets misreported.

**What it assumes**

| From | What is used |
|---|---|
| INF 1 | The permutation null, the unit-of-exchangeability argument, and the 1/(B+1) floor. |
| SIG 5 | That a time-frequency map is a smoothed picture, so neighbouring cells are not independent. |
| POP 1 | That smoothing destroys independent samples. |

**What it underwrites**

Any claim in this app that a contrast is significant somewhere in a map, and the
wording of every figure caption that reports one.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
from scipy.ndimage import gaussian_filter1d, label

rng = np.random.default_rng(23)
ALPHA = 0.05

N_TIME = 200        # time points in the map under test
N_TRIALS = 40       # trials per condition
SMOOTH = 6.0        # Gaussian sigma, in points, of the analysis smoothing
DF = 2 * N_TRIALS - 2
W0, W1 = 90, 110    # where a planted effect lives, when there is one

# Rescale so the smoothed noise has unit variance, which makes the planted
# effects below readable as multiples of the noise a single trial carries.
_SCALE = 1.0 / gaussian_filter1d(
    np.random.default_rng(0).standard_normal((400, N_TIME)), SMOOTH, axis=1).std()


def two_conditions(seed: int, effect: float = 0.0,
                   w0: int = W0, w1: int = W1) -> tuple[np.ndarray, np.ndarray]:
    """Trials by time for two conditions, with an effect planted in [w0, w1).

    The effect is added BEFORE smoothing, because in a real pipeline the effect
    and the noise pass through the same estimator. This matters in Section 4.
    """
    gen = np.random.default_rng(seed)
    planted = np.zeros(N_TIME)
    planted[w0:w1] = effect
    a = gaussian_filter1d(gen.standard_normal((N_TRIALS, N_TIME)), SMOOTH, axis=1)
    b = gaussian_filter1d(gen.standard_normal((N_TRIALS, N_TIME)) + planted, SMOOTH, axis=1)
    return a * _SCALE, b * _SCALE


def t_maps(x: np.ndarray, splits: np.ndarray) -> np.ndarray:
    """Independent-samples t at every time point, for every labelling in `splits`.

    `x` is (trials, time) with both conditions stacked; `splits` is
    (n_labellings, trials) of booleans marking condition B. Vectorised over
    labellings because the permutation loop below needs hundreds of them.
    """
    n = splits.shape[1]
    nb = splits.sum(axis=1)[:, None].astype(float)
    b_mask, a_mask = splits.astype(float), (~splits).astype(float)
    sum_b, sum_a = b_mask @ x, a_mask @ x
    mb, ma = sum_b / nb, sum_a / (n - nb)
    # Sums of squares rather than (x - mean)**2, which would build a
    # (labellings, trials, time) array for every call. At a few hundred
    # labellings that temporary is millions of numbers and it is most of the
    # cost of this lesson. The identity is exact; the cancellation it can suffer
    # needs values far from zero, and these are t-scaled.
    squares = x ** 2
    sumsq_b, sumsq_a = b_mask @ squares, a_mask @ squares
    vb = (sumsq_b - nb * mb ** 2) / (nb - 1)
    va = (sumsq_a - (n - nb) * ma ** 2) / (n - nb - 1)
    pooled = np.sqrt(((nb - 1) * vb + (n - nb - 1) * va) / (n - 2))
    return (mb - ma) / (pooled * np.sqrt(1 / nb + 1 / (n - nb)))


def largest_cluster_masses(t: np.ndarray, threshold: float) -> np.ndarray:
    """Largest cluster mass in each row of a stack of t-maps, all at once.

    The same quantity as the first entry of `cluster_masses(row, threshold)` for
    every row, without a Python loop. The permutation loops call this hundreds of
    times per map and it is most of the cost of this lesson.

    The trick is a False column between rows, so a run of suprathreshold points
    can never span two of them, and then one pass over the flattened array.
    Section 3 checks it against the readable version rather than assuming.
    """
    magnitude = np.abs(t)
    above = magnitude > threshold
    n_rows, n_time = magnitude.shape
    flat_above = np.concatenate([above, np.zeros((n_rows, 1), dtype=bool)], axis=1).ravel()
    flat_magnitude = np.concatenate([magnitude, np.zeros((n_rows, 1))], axis=1).ravel()
    edges = np.diff(np.concatenate([[0], flat_above.view(np.int8), [0]]))
    starts, ends = np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)
    running = np.concatenate([[0.0], np.cumsum(flat_magnitude)])
    masses = running[ends] - running[starts]
    out = np.zeros(n_rows)
    if masses.size:
        np.maximum.at(out, starts // (n_time + 1), masses)
    return out


def observed_t(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """The t-map for the real labelling."""
    split = np.zeros((1, 2 * N_TRIALS), dtype=bool)
    split[0, N_TRIALS:] = True
    return t_maps(np.concatenate([a, b]), split)[0]


print("Environment initialized for Lesson INF 2")''')

m.md(r'''---

## 1. How many questions is a map?

Take a map with no effect anywhere and test every point at 0.05. The chance that
at least one point comes out significant is the quantity that matters, because
that is what a person scanning the figure will find and report.

If the points were independent the answer would be 1 minus 0.95 to the power of
the number of points, which for 200 points is indistinguishable from certainty.
Neighbouring points in a smoothed map are not independent, so the true rate is
lower. It is measured below, and the gap between the two answers is itself
informative: it says how many independent questions the map really contains.''')

m.code('''# --- TEST CELL FOR STEP 1 ---
N_SIMS = 200

any_point = 0
for s in range(N_SIMS):
    t = observed_t(*two_conditions(s, effect=0.0))
    p = 2 * stats.t.sf(np.abs(t), DF)
    any_point += int((p <= ALPHA).any())
rate = any_point / N_SIMS

independent_prediction = 1 - (1 - ALPHA) ** N_TIME
print(f"{N_SIMS} maps of {N_TIME} points, no effect anywhere, each point tested at {ALPHA}")
print(f"  at least one significant point: {rate:.3f}")
print(f"  if the points were independent: {independent_prediction:.4f}")
print(f"  if there were only one test:    {ALPHA:.4f}")

assert rate > 0.5, "testing every point of a map is nothing like testing once"
assert rate < 0.95, "and it is not the independent-tests prediction either"

# Invert the independent-tests formula to ask how many independent questions a
# map of this smoothness is really asking.
effective = np.log(1 - rate) / np.log(1 - ALPHA)
# A resel is one smoothing kernel width: the standard rule of thumb for the same
# quantity, computed from the kernel rather than from the simulation.
resels = N_TIME / (SMOOTH * 2.355)
print(f"\\n  the measured rate implies {effective:.0f} independent tests, not {N_TIME}")
print(f"  the kernel's full width at half maximum gives {resels:.1f} resels")
assert 10 < effective < 60, "a smoothed map asks far fewer questions than it has points"

print(f"\\nThe map has {N_TIME} points and asks roughly {effective:.0f} independent questions. The")
print(f"kernel's own rule of thumb says {resels:.0f}, which is the same order and about half,")
print("so the rule of thumb is a lower bound here rather than an estimate. What both")
print("agree on is the part that matters: a correction is needed, and one built for 200")
print("independent tests will be far too harsh.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Two corrections that control two different things

**Bonferroni** divides the threshold by the number of tests. It controls the
family-wise error rate, the probability of even one false positive anywhere, and
it does so under any dependence structure whatsoever. That generality is exactly
why it is wasteful here: Section 1 measured about 26 independent questions and
Bonferroni charges for 200.

**Benjamini-Hochberg** controls the false discovery rate, the expected fraction
of the points you call significant that are not. That is a weaker guarantee and a
different one. Under a global null with nothing true anywhere, any false positive
makes the discovery fraction 1, so controlling FDR at q also holds the
family-wise rate at q in that case; once something real is present, the two come
apart and FDR permits false positives in proportion to true ones.

Both are measured below on the same maps, first for size and then for power.''')

m.task(
'''def benjamini_hochberg(p: np.ndarray, q: float = 0.05) -> np.ndarray:
    """Boolean mask of the points BH declares significant at false discovery rate q.

    Sort the p-values, find the largest rank k whose p is at or below q*k/m, and
    reject everything up to that rank.
    """
    # TODO: order the p-values ascending and keep the ordering
    # TODO: compare each ranked p against q * rank / m, with rank starting at 1
    # TODO: take the LARGEST passing rank, not the first failure, and reject to there
    # TODO: return a boolean mask in the original ordering
    raise NotImplementedError("Implement benjamini_hochberg")''',
'''def benjamini_hochberg(p: np.ndarray, q: float = 0.05) -> np.ndarray:
    """Boolean mask of the points BH declares significant at false discovery rate q.

    Sort the p-values, find the largest rank k whose p is at or below q*k/m, and
    reject everything up to that rank.
    """
    p = np.asarray(p, dtype=float)
    m = p.size
    order = np.argsort(p)
    passes = p[order] <= q * (np.arange(1, m + 1) / m)
    mask = np.zeros(m, dtype=bool)
    if passes.any():
        # The largest passing rank, not the first failing one. Rejecting up to
        # the last pass is what makes BH a step-up procedure rather than a
        # step-down one, and it is where hand-rolled versions go wrong.
        mask[order[: np.max(np.where(passes)[0]) + 1]] = True
    return mask''')

m.code('''# --- TEST CELL FOR STEP 2 ---
# (a) A worked example with a known answer, so the implementation is checked
# against arithmetic rather than against itself.
example = np.array([0.001, 0.008, 0.039, 0.041, 0.900])
# The rank thresholds q*k/m for k = 1..5 at q = 0.05 are 0.01, 0.02, 0.03, 0.04
# and 0.05. Ranks 1 and 2 pass; rank 3 fails at 0.039 > 0.03 and rank 4 fails at
# 0.041 > 0.04, so the largest passing rank is 2 and BH makes two rejections.
got = benjamini_hochberg(example, q=0.05)
print("worked example:", example, "->", got.astype(int))
assert got.tolist() == [True, True, False, False, False], "BH rejects to the largest passing rank"

# Move the fourth p-value just under its threshold and BH must now reject four,
# including the third, which fails its own threshold. That step-up behaviour is
# the whole difference from Bonferroni.
stepped = benjamini_hochberg(np.array([0.001, 0.008, 0.039, 0.0399, 0.900]), q=0.05)
assert stepped.tolist() == [True, True, True, True, False], \\
    "a later pass drags the earlier failures in with it"

# (b) Size, on maps with nothing in them.
bonf = bh = 0
for s in range(N_SIMS):
    p = 2 * stats.t.sf(np.abs(observed_t(*two_conditions(s, 0.0))), DF)
    bonf += int((p <= ALPHA / N_TIME).any())
    bh += int(benjamini_hochberg(p, q=ALPHA).any())
size = {"Bonferroni": bonf / N_SIMS, "Benjamini-Hochberg": bh / N_SIMS}
print(f"\\nfalse positive rate over {N_SIMS} empty maps")
for k, v in size.items():
    print(f"  {k:>20}: {v:.3f}")
assert size["Bonferroni"] < 0.02, "Bonferroni holds the family-wise rate"
assert size["Benjamini-Hochberg"] < 0.06, "and so does BH when nothing is true"

# (c) Power, on maps with a real effect in 20 of the 200 points.
print(f"\\n{'effect':>7} {'Bonferroni':>12} {'Benjamini-Hochberg':>20}")
power = {}
for effect in (0.15, 0.25):
    b_hits = h_hits = 0
    for s in range(N_SIMS):
        p = 2 * stats.t.sf(np.abs(observed_t(*two_conditions(s, effect))), DF)
        b_hits += int((p <= ALPHA / N_TIME).any())
        h_hits += int(benjamini_hochberg(p, q=ALPHA).any())
    power[effect] = (b_hits / N_SIMS, h_hits / N_SIMS)
    print(f"{effect:>7.2f} {power[effect][0]:>12.3f} {power[effect][1]:>20.3f}")

assert power[0.15][1] > power[0.15][0], "BH finds the weak effect more often than Bonferroni"

print("\\nBoth corrections held the false positive rate, and Bonferroni held it so far")
print("below the nominal five percent that the number is a warning rather than a")
print(f"reassurance: it is paying for {N_TIME} independent tests when Section 1 measured")
print(f"about {effective:.0f}. BH recovered some of that, and it did so by guaranteeing something")
print("weaker. Neither uses the fact that makes this map cheap to correct, which is")
print("that a real effect occupies neighbouring points and noise mostly does not.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. The cluster permutation test

The structure Section 2 threw away is adjacency. A physiological effect is smooth
in time and frequency, so it shows up as a run of neighbouring points that all
lean the same way. Isolated noise excursions do not.

The test that uses this has four steps, and only the fourth is subtle.

1. Compute the statistic at every point.
2. Threshold it, and group the surviving points into connected clusters.
3. Give each cluster a **mass**: the sum of the statistic over its points, which
   rewards a cluster for being both large and strong.
4. Build a null for the mass, by shuffling as INF 1 shuffled, recomputing the
   whole map each time, and keeping only the **largest** cluster mass from each
   shuffled map.

Step 4 is what buys the correction. Comparing against the distribution of the
maximum, rather than against the distribution of any one cluster, is a
family-wise statement: under the null, the chance that the biggest real cluster
beats the biggest shuffled cluster is what it is regardless of how many clusters
the map happened to contain.

The threshold in step 2 is a free parameter and not a nuisance one. Part (c)
measures what it does.''')

m.task(
'''def cluster_masses(t: np.ndarray, threshold: float) -> list[tuple[float, np.ndarray]]:
    """Connected runs of |t| above `threshold`, each with its summed |t|.

    Returns a list of (mass, indices), largest mass first. Use
    scipy.ndimage.label to find the connected runs.
    """
    # TODO: label the connected runs of |t| > threshold
    # TODO: for each label, sum |t| over its points; that sum is the mass
    # TODO: return (mass, indices) pairs sorted by descending mass
    raise NotImplementedError("Implement cluster_masses")


def cluster_test(a: np.ndarray, b: np.ndarray, threshold_p: float = 0.05,
                 n_perm: int = 199, seed: int = 0) -> tuple[np.ndarray, list]:
    """Cluster permutation test. Returns (t_map, significant clusters).

    Each significant cluster is (p_value, indices). Shuffle the trial labels,
    which is the unit INF 1 established, and keep the maximum cluster mass from
    each shuffled map.
    """
    # TODO: threshold_p is two-sided, so the t threshold is the 1 - threshold_p/2 quantile
    # TODO: build n_perm random labellings of the 2*N_TRIALS trials, half in B
    # TODO: for each, take the LARGEST cluster mass, or 0.0 if there are no clusters
    # TODO: p for a real cluster is (number of shuffled maxima at least as big, +1)/(n_perm+1)
    raise NotImplementedError("Implement cluster_test")''',
'''def cluster_masses(t: np.ndarray, threshold: float) -> list[tuple[float, np.ndarray]]:
    """Connected runs of |t| above `threshold`, each with its summed |t|.

    Returns a list of (mass, indices), largest mass first. Use
    scipy.ndimage.label to find the connected runs.
    """
    magnitude = np.abs(t)
    labels, n_found = label(magnitude > threshold)
    out = []
    for k in range(1, n_found + 1):
        idx = np.where(labels == k)[0]
        out.append((float(magnitude[idx].sum()), idx))
    return sorted(out, key=lambda pair: -pair[0])


def cluster_test(a: np.ndarray, b: np.ndarray, threshold_p: float = 0.05,
                 n_perm: int = 199, seed: int = 0) -> tuple[np.ndarray, list]:
    """Cluster permutation test. Returns (t_map, significant clusters).

    Each significant cluster is (p_value, indices). Shuffle the trial labels,
    which is the unit INF 1 established, and keep the maximum cluster mass from
    each shuffled map.
    """
    threshold = stats.t.ppf(1 - threshold_p / 2, DF)
    x = np.concatenate([a, b])
    n_total = x.shape[0]

    gen = np.random.default_rng(seed)
    splits = np.zeros((n_perm, n_total), dtype=bool)
    for i in range(n_perm):
        splits[i, gen.permutation(n_total)[: n_total // 2]] = True

    # One null for the whole map, made of maxima. Keeping every cluster from
    # every shuffle instead would give a null for "a cluster" and would not
    # correct for anything.
    null = largest_cluster_masses(t_maps(x, splits), threshold)

    t = observed_t(a, b)
    found = []
    for mass, idx in cluster_masses(t, threshold):
        p = (np.sum(null >= mass) + 1) / (n_perm + 1)
        if p <= ALPHA:
            found.append((float(p), idx))
    return t, found''')

m.code('''# --- TEST CELL FOR STEP 3 ---
# (a) The mass is a sum, so it must reward extent and amplitude together.
probe = np.zeros(N_TIME)
probe[10:14] = 5.0          # short and tall:  mass 20
probe[50:70] = 1.5          # long and short:  mass 30
masses = cluster_masses(probe, threshold=1.0)
print("two planted clusters, masses:", [round(mass, 1) for mass, _ in masses])
assert [round(mass, 1) for mass, _ in masses] == [30.0, 20.0], "sorted by mass, largest first"
assert len(cluster_masses(probe, threshold=2.0)) == 1, "raising the threshold drops the weak one"
assert cluster_masses(np.zeros(N_TIME), 1.0) == [], "an empty map has no clusters"

# (a2) The fast path used inside every permutation loop, checked against the
# readable one. If these disagreed the whole section would be wrong and nothing
# else here would notice, because the readable version is never run on a shuffle.
THRESH_PROBE = stats.t.ppf(0.975, DF)
probe_rows = np.array([observed_t(*two_conditions(s, 0.0)) for s in range(40)])
by_hand = np.array([max((mass for mass, _ in cluster_masses(row, THRESH_PROBE)), default=0.0)
                    for row in probe_rows])
vectorised = largest_cluster_masses(probe_rows, THRESH_PROBE)
print(f"fast path against the readable one, over {len(probe_rows)} maps: "
      f"max difference {np.max(np.abs(by_hand - vectorised)):.1e}")
assert np.allclose(by_hand, vectorised, rtol=0, atol=1e-9), \
    "the vectorised cluster mass must agree with the one just verified"
assert np.array_equal(by_hand == 0, vectorised == 0), \
    "including which maps have no cluster at all"

# (b) Size and power, against the Section 2 corrections on identical maps.
def cluster_rate(effect, n_sims=N_SIMS, threshold_p=0.05, w0=W0, w1=W1):
    hits, extents = 0, []
    for s in range(n_sims):
        a, b = two_conditions(s, effect, w0, w1)
        _, found = cluster_test(a, b, threshold_p, n_perm=199, seed=s + 500_000)
        if found:
            hits += 1
            extents.append(sum(len(idx) for _, idx in found))
    return hits / n_sims, extents

null_rate, _ = cluster_rate(0.0)
print(f"\\nfalse positive rate over {N_SIMS} empty maps: {null_rate:.3f}")
assert 0.015 < null_rate < 0.11, "the maximum-statistic null holds the family-wise rate"

print(f"\\n{'effect':>7} {'Bonferroni':>12} {'BH':>8} {'cluster':>9}")
cluster_power = {}
for effect in (0.15, 0.25):
    cluster_power[effect], _ = cluster_rate(effect)
    print(f"{effect:>7.2f} {power[effect][0]:>12.3f} {power[effect][1]:>8.3f} "
          f"{cluster_power[effect]:>9.3f}")
assert cluster_power[0.15] > power[0.15][0], "the cluster test beats Bonferroni on the weak effect"
assert cluster_power[0.25] > power[0.25][0], "and on the strong one"
assert cluster_power[0.15] > power[0.15][1], "it beats BH where power is scarce"
# It does NOT beat BH everywhere, and the table above says so: at the strong
# effect both are near ceiling and BH is marginally ahead. Assert the shape of
# the result rather than the story that would be tidier.
assert abs(cluster_power[0.25] - power[0.25][1]) < 0.05, \
    "at the strong effect the two are level, and the cluster test's advantage is at low power"

# (c) Step 4 is the correction, so it needs its own evidence. Compare the
# maximum-statistic null against a null that pools EVERY cluster from every
# shuffle, on empty maps of varying size and smoothness.
def two_nulls_fwer(n_time, smooth, n_sims=120, n_perm=199, threshold_p=0.05):
    """False positive rate of the max-statistic null and the pooled-cluster null.

    The maximum column calls cluster_test itself rather than reimplementing it,
    so a cluster_test that stopped taking the maximum would show up here as the
    two columns agreeing.
    """
    thr = stats.t.ppf(1 - threshold_p / 2, DF)
    scale = 1.0 / gaussian_filter1d(
        np.random.default_rng(0).standard_normal((300, n_time)), smooth, axis=1).std()
    hit_max = hit_pooled = 0
    counts = []
    for s in range(n_sims):
        gen = np.random.default_rng(s + 300_000)
        a = gaussian_filter1d(gen.standard_normal((N_TRIALS, n_time)), smooth, axis=1) * scale
        b = gaussian_filter1d(gen.standard_normal((N_TRIALS, n_time)), smooth, axis=1) * scale
        hit_max += int(bool(cluster_test(a, b, threshold_p, n_perm, seed=s + 300_000)[1]))

        # The same test with the maximum removed: every cluster from every
        # shuffle goes into one pool.
        x = np.concatenate([a, b])
        splits = np.zeros((n_perm, 2 * N_TRIALS), dtype=bool)
        for i in range(n_perm):
            splits[i, gen.permutation(2 * N_TRIALS)[:N_TRIALS]] = True
        per_shuffle = [[mass for mass, _ in cluster_masses(row, thr)]
                       for row in t_maps(x, splits)]
        counts.append(np.mean([len(c) for c in per_shuffle]))
        pooled = np.array([v for c in per_shuffle for v in (c or [0.0])])
        observed = [mass for mass, _ in cluster_masses(observed_t(a, b), thr)]
        hit_pooled += int(any((np.sum(pooled >= mm) + 1) / (pooled.size + 1) <= ALPHA
                              for mm in observed))
    return float(np.mean(counts)), hit_max / n_sims, hit_pooled / n_sims

print("\\nempty maps, two ways of building the null")
print(f"{'points':>7} {'sigma':>6} {'clusters per map':>17} {'maximum':>9} {'every cluster':>15}")
nulls = {}
for n_time, smooth in ((200, 6.0), (200, 1.5), (1000, 6.0)):
    nulls[(n_time, smooth)] = two_nulls_fwer(n_time, smooth)
    per_map, fmax, fpool = nulls[(n_time, smooth)]
    print(f"{n_time:>7} {smooth:>6.1f} {per_map:>17.1f} {fmax:>9.3f} {fpool:>15.3f}")

for key, (per_map, fmax, fpool) in nulls.items():
    assert fmax < 0.11, f"the maximum-statistic null holds its size at {key}"

# What the pooled null costs, expressed as a ratio to the maximum on the SAME
# maps, so the comparison does not depend on how many simulations were run.
inflation = {k: v[2] / max(v[1], 1e-9) for k, v in nulls.items()}
one_cluster = inflation[(200, 6.0)]
assert one_cluster < 2.0, "on a map holding about one cluster per shuffle, the two agree"
for key in ((200, 1.5), (1000, 6.0)):
    assert inflation[key] > 3.0, f"the pooled null is badly inflated at {key}"
    assert inflation[key] > 2 * one_cluster, \
        "and the damage grows with the number of clusters a map contains"

maxima = ", ".join(f"{v[1]:.3f}" for v in nulls.values())
print(f"\\n  The maximum gave {maxima} against a nominal 0.05. Each row is 120 maps, so")
print("  each carries about two points of sampling error and all three are consistent")
print("  with holding their size. The pooled null is not:")
print(f"  it ran {one_cluster:.1f}x the maximum's rate on the map holding about one cluster per")
print(f"  shuffle, and {inflation[(1000, 6.0)]:.0f}x on the map holding about six.")
print("\\n  The first row is why this mistake is easy to miss. With one cluster per shuffle")
print("  the maximum and the pool are nearly the same distribution, so a small map will")
print("  not reveal the error. On a map with several, the pooled null is padded with")
print("  small clusters that push the real one down the ranking. A real time-frequency")
print("  map is the last row, not the first.")

# (d) The cluster-forming threshold decides WHICH effects the test can find.
print("\\npower by cluster-forming threshold, at two shapes of true effect")
print(f"{'true effect':>30} {'lenient (p=0.05)':>18} {'strict (p=0.001)':>18}")
shapes = {"broad and weak, 140 points": (0.048, 30, 170),
          "narrow and strong, 6 points": (0.42, 97, 103)}
by_threshold = {}
for name, (effect, w0, w1) in shapes.items():
    lenient, _ = cluster_rate(effect, n_sims=150, threshold_p=0.05, w0=w0, w1=w1)
    strict, _ = cluster_rate(effect, n_sims=150, threshold_p=0.001, w0=w0, w1=w1)
    by_threshold[name] = (lenient, strict)
    print(f"{name:>30} {lenient:>18.3f} {strict:>18.3f}")

broad = by_threshold["broad and weak, 140 points"]
narrow = by_threshold["narrow and strong, 6 points"]
assert broad[0] > broad[1], "a lenient threshold favours broad weak effects"
assert narrow[1] > narrow[0], "a strict threshold favours narrow strong ones"

print("\\nThe cluster test held its size and beat Bonferroni at both effects, because it")
print("used the one fact Bonferroni ignores: real effects have extent. Against BH the")
print("picture is narrower than the usual telling. It won clearly where power was")
print("scarce, at the weak effect, and drew at the strong one, where both are near")
print("ceiling and there is nothing left to win. The cluster test's advantage is a")
print("low-power advantage, which is the regime this lab records in.")
print("\\nPart (d) is the part to remember. The cluster-forming threshold is not a")
print("detail of implementation, it is a statement about the shape of effect you are")
print("looking for, and the two rows above cross over. A threshold chosen after seeing")
print("the map is a garden of forking paths; it belongs in the analysis plan.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. A significant cluster does not have edges

The cluster test answers one question: **do these two conditions differ
somewhere in this map?** It is a single test producing a single p-value, and that
p-value attaches to the map, not to the cluster that carried it.

This is routinely over-read. A figure shows a shaded significant window from 86
to 114 ms and the text says the effect began at 86 ms and lasted 28 ms. Neither
claim was tested. The cluster's edges are where the statistic happened to fall
below an arbitrary threshold, and the section below measures how badly they
describe the truth.

The tell is that the reported extent grows with the strength of the effect, while
the true extent never moves.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
TRUE_WIDTH = W1 - W0
print(f"the planted effect always occupies points {W0} to {W1}, a width of {TRUE_WIDTH}\\n")
print(f"{'effect':>7} {'detected':>9} {'reported onset':>15} {'reported offset':>16} {'reported width':>15}")

reported = {}
for effect in (0.15, 0.25, 0.40, 0.80):
    onsets, offsets, widths = [], [], []
    for s in range(N_SIMS):
        _, found = cluster_test(*two_conditions(s, effect), 0.05, 199, seed=s + 500_000)
        if found:
            points = np.concatenate([idx for _, idx in found])
            onsets.append(int(points.min()))
            offsets.append(int(points.max()) + 1)
            widths.append(len(points))
    reported[effect] = (len(onsets) / N_SIMS, float(np.median(onsets)),
                        float(np.median(offsets)), float(np.median(widths)))
    print(f"{effect:>7.2f} {reported[effect][0]:>9.3f} {reported[effect][1]:>15.0f} "
          f"{reported[effect][2]:>16.0f} {reported[effect][3]:>15.0f}")

# The truth is fixed. The report is not, and it moves in one direction.
assert reported[0.80][3] > reported[0.15][3], \\
    "a stronger effect is reported as a longer effect, though it is not one"
assert reported[0.80][3] > 1.5 * TRUE_WIDTH, "and by the largest effect the overstatement is gross"
assert reported[0.80][1] < W0 and reported[0.80][2] > W1, \\
    "the reported window brackets the true one on both sides"

growth = reported[0.80][3] / reported[0.15][3]
print(f"\\n  reported width grew {growth:.1f}x across the sweep; true width never changed")
print(f"  at effect 0.80 the reported window is {reported[0.80][1]:.0f} to {reported[0.80][2]:.0f}, "
      f"against a truth of {W0} to {W1}")

# Two mechanisms, and only one of them is the analyst's fault. Even a perfectly
# sharp effect gets smeared by the pipeline's own smoothing, which is why the
# effect in two_conditions is added before the filter.
sharp = np.zeros(N_TIME)
sharp[W0:W1] = 1.0
smeared = gaussian_filter1d(sharp, SMOOTH)
half_width = int(np.sum(smeared > 0.5 * smeared.max()))
print(f"\\n  the planted box, put through the same smoothing, is already {half_width} points wide")
print(f"  at half maximum before any noise or thresholding is involved")
assert half_width > TRUE_WIDTH, "the estimator itself widens the effect"

print("\\nSo the reported extent is wrong for two reasons that need separating. The")
print("smoothing widens a sharp effect before any test happens, and that part is a")
print("property of the estimator that SIG 5 already quantified. On top of it, a bigger")
print("effect pushes more of its smeared skirt above the cluster-forming threshold, so")
print("the reported duration grows with effect size even though the true duration is")
print("constant.")
print("\\nOne caveat on the table, which cuts the right way. Each row averages only the")
print("runs where something was detected, and at the weakest effect that is half of")
print("them. Conditioning on detection selects the runs where noise helped, which")
print("inflates the weak-effect widths, so the true growth across the sweep is if")
print("anything steeper than the table shows.")
print("\\nWhat the test licenses is one sentence: the conditions differ somewhere in this")
print("map, at p = the cluster's p-value. Onset, offset, duration and peak location are")
print("not part of the output. If onset is the scientific question, it needs a test")
print("whose null is about onset, which SIG 2 already showed is a harder problem than")
print("it looks.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **A smoothed map asks far fewer questions than it has points.** Testing every
   one of 200 points at 0.05 on an empty map produced at least one significant
   point in 73 percent of maps. The independent-tests formula predicts effective
   certainty, and inverting the measured rate gives about 26 independent
   questions. The smoothing kernel's resel count says 14, roughly half, so at
   this smoothing the rule of thumb undercounts. One configuration does not make
   that a general bound, and it is quoted here as what was measured.
2. **Bonferroni and Benjamini-Hochberg control different things and both ignore
   the map's structure.** Bonferroni held the family-wise rate near zero rather
   than near 0.05, which is the cost of assuming 200 independent tests. BH bought
   power back by guaranteeing something weaker: a fraction of discoveries, not
   the absence of any.
3. **The cluster permutation test uses adjacency, and the maximum-statistic null
   is what makes it a correction.** It held its size and beat both alternatives
   on the same maps, and beat Benjamini-Hochberg where power was scarce while
   drawing with it at the strong effect, where both are near ceiling. Replacing
   the maximum with a null that pools every cluster
   from every shuffle cost little on a map holding about one cluster per
   shuffle and several times the nominal rate on maps holding four to six, while
   the maximum gave 0.083, 0.042 and 0.025 over 120 maps a row, all consistent
   with holding their size at about two points of sampling error. That is why the mistake is easy to
   miss on a small map: with one cluster per shuffle the maximum and the pool
   are nearly the same distribution.
   The cluster-forming threshold is a scientific choice, not a default: a lenient
   threshold found a broad weak effect more often, a strict one found a narrow
   strong effect more often, and the two rows crossed over.
4. **A significant cluster has no edges.** With the true effect fixed at 20
   points, the reported width grew steadily as the effect got stronger, and the
   reported window bracketed the truth on both sides. Part of that is the
   estimator's own smoothing, which widens a sharp 20-point effect before any
   test runs. The output of the test is "these conditions differ somewhere in
   this map," and nothing about when.

The through line from INF 1: every one of these procedures is a null, and the
null is a claim about what could have come out otherwise. Bonferroni's claim is
about 200 independent tests, the cluster test's is about the largest cluster in a
relabelled map, and neither claim mentions the thing people report, which is
where the effect was.

### Exercises

**Exercise 1.** Extend `cluster_masses` to two dimensions so it works on a
time-frequency map, using `scipy.ndimage.label` with a connectivity structure.
Then say what changes about Section 1's effective-test count when the map is
smoothed in both time and frequency, and check your answer by simulation.

**Exercise 2.** Section 3 part (c) showed the cluster-forming threshold trading
sensitivity between effect shapes. Design the analysis plan sentence you would
write in advance for a beta desynchronisation during speech, and justify the
threshold you picked from the physiology rather than from the data.

**Exercise 3.** CON 3 reported a coupling z of +18 from a shuffled null at one
fixed phase band and one fixed amplitude band, so nothing there needed
correcting. A comodulogram sweeps both bands and turns that single test into a
map. Using Section 1, work out how many independent questions a comodulogram of
plausible size actually asks, and how large an uncorrected z would have to be to
survive it. Then say whether +18 would.

---

**Next: INF 3, what a z-score means.** Both of these lessons compared a number to
a null. `configs/statistics.yaml` offers four ways to centre that number and five
ways to scale it, and the twenty combinations are not twenty flavours of the same
answer.
''')

m.emit()
verify("08_inference", "02_multiple_comparisons_and_clusters")
print("  INF 2 OK")
