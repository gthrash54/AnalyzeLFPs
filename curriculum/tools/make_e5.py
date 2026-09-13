import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("03_spatial", "05_localization_and_contact_labels")

m.md(r'''# Lesson REC 5: What a Contact Label Means {{VARIANT}}

**Acquisition · Recording Physics and Electrode Geometry**

{{INSTRUCTIONS}}

Every figure this app can produce eventually says something of the form "contact
2b, in STN, showed the effect". That sentence contains two claims of very
different kinds, and they fail in different ways.

**Which contact recorded the largest signal** is a fact about the recording. No
imaging is involved, and registration cannot change it.

**Where that contact is** is an inference from a registration of the lead to an
anatomical space, and it is only as good as that registration.

The first claim looks like the solid one. Section 2 measures both and finds the
opposite of what that intuition suggests: at a realistic segment count on a
tight-pitch lead, the identity of the best contact is wrong about three times in
ten, before any imaging enters the argument.

**What it assumes**

| From | What is used |
|---|---|
| REC 1 | That an LFP falls off as a power of distance, and reaches millimetres rather than microns. |
| REC 2 | The 1-3-3-1 geometry, and that lead rotation is frequently unknown. |
| STO 1 | The spread of a dB value averaged over k segments, which is the trigamma form. |

**What it underwrites**

Any statement in this app that names an anatomical target for a contact, and the
wording of a figure legend that names a best contact. It is also why
`configs/leads.yaml` now carries a numeric `row_spacing_mm` with a
`spacing_confirmed` flag: this lesson needed a distance and found one inside a
model name string, which is not a number a program can read.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy import special, stats

rng = np.random.default_rng(505)

# From REC 1: a synchronised population gives about 50 uV at 1 mm and falls as a
# power of distance in the far field. The exponent matters less here than the
# fact that it is smooth, which is Section 1's point.
AMPLITUDE_AT_1MM_UV = 50.0
FALLOFF_EXPONENT = 1.5
N_ROWS = 4                    # the 1-3-3-1 lead of REC 2 has four rows

# From configs/leads.yaml, medtronic_3389 and medtronic_3387. Restated so the
# notebook runs standalone; the test suite asserts these still match the config.
#
# Both are marked spacing_confirmed: false there, and the reason is worth
# carrying into the lesson rather than leaving in the config. The numbers were
# transcribed from the model names, and vendor literature uses "spacing" for
# both the centre-to-centre pitch and the gap between contact edges, which differ
# by a factor of two on a typical lead. So these are the right two numbers to
# reason with and the wrong two to compute a patient's anatomy from, which is
# exactly the distinction this lesson is about.
PITCHES_MM = (1.5, 3.0)
PITCH_SOURCE = ("medtronic_3389", "medtronic_3387")


def amplitude_uv(distance_mm):
    """LFP amplitude at a distance, from REC 1's falloff."""
    # The floor stops the model claiming infinite amplitude at zero distance,
    # which is a modelling convenience and not a physical statement.
    return AMPLITUDE_AT_1MM_UV * np.maximum(distance_mm, 0.2) ** -FALLOFF_EXPONENT


def db_spread(k_segments):
    """Standard deviation of the dB value this app actually computes.

    STO 1 established that one segment's periodogram is exponential, and that
    `recipes/psd.py` converts EACH segment to decibels and then averages the
    decibels. So the quantity here is a mean of k independent per-segment dB
    values, and its spread is one segment's spread divided by sqrt(k).

    One segment's spread is (10/ln 10) * sqrt(trigamma(1)) = 5.57 dB. It is worth
    being explicit that this is the dB-then-average branch: the OTHER ordering,
    averaging the power first, has spread (10/ln 10) * sqrt(trigamma(k)), which is
    smaller and does not describe this app. Section 2 verifies both by simulation
    rather than asserting either.
    """
    one_segment = (10.0 / np.log(10.0)) * np.sqrt(special.polygamma(1, 1))
    return one_segment / np.sqrt(k_segments)


def db_spread_if_power_averaged(k_segments):
    """The spread of the ordering psd.py does NOT use, kept for the comparison."""
    return (10.0 / np.log(10.0)) * np.sqrt(special.polygamma(1, k_segments))


print("Environment initialized for Lesson REC 5")''')

m.md(r'''---

## 1. A smooth field read by a discrete array

The physics is smooth. Move a source a tenth of a millimetre and every contact's
amplitude changes a little. Nothing in the field has an edge.

Both of the claims in the opening sentence, though, are discrete. "Which contact
is largest" picks one of four rows, and "which structure is it in" picks one of
two sides of a boundary. Reading a smooth field through a discrete question means
there are positions where an arbitrarily small change flips the answer, and
positions where a large change does not.

That is not a defect of the array. It is what asking a categorical question of a
continuous quantity always does, and the useful move is to measure how close to
a flip you are rather than to pretend the answer is firm.''')

m.task(
'''def contact_depths(pitch_mm: float, n_rows: int = N_ROWS) -> np.ndarray:
    """Depths of the contact rows along the lead axis, centred on zero."""
    # TODO: n_rows evenly spaced by pitch_mm, with mean zero
    raise NotImplementedError("Implement contact_depths")


def amplitudes_at_rows(source_depth_mm: float, source_radius_mm: float,
                       pitch_mm: float) -> np.ndarray:
    """Amplitude seen by each row, for a source offset from the lead axis.

    The distance from a row to the source is the hypotenuse of the along-axis
    offset and the radial offset.
    """
    # TODO: get the row depths
    # TODO: distance is sqrt((depth - source_depth)^2 + source_radius^2)
    # TODO: return amplitude_uv of those distances
    raise NotImplementedError("Implement amplitudes_at_rows")''',
'''def contact_depths(pitch_mm: float, n_rows: int = N_ROWS) -> np.ndarray:
    """Depths of the contact rows along the lead axis, centred on zero."""
    depths = np.arange(n_rows) * pitch_mm
    return depths - depths.mean()


def amplitudes_at_rows(source_depth_mm: float, source_radius_mm: float,
                       pitch_mm: float) -> np.ndarray:
    """Amplitude seen by each row, for a source offset from the lead axis.

    The distance from a row to the source is the hypotenuse of the along-axis
    offset and the radial offset.
    """
    depths = contact_depths(pitch_mm)
    distance = np.hypot(depths - source_depth_mm, source_radius_mm)
    return amplitude_uv(distance)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
PITCH = 1.5
depths = contact_depths(PITCH)
print(f"a {N_ROWS}-row lead at {PITCH} mm pitch, depths {np.round(depths, 2)} mm, "
      f"span {depths[-1] - depths[0]:.1f} mm\\n")
assert len(depths) == N_ROWS
assert abs(depths.mean()) < 1e-12, "centred on zero"
assert np.allclose(np.diff(depths), PITCH), "evenly spaced by the pitch"

# The field is smooth: a small move in the source moves every amplitude a little.
# Look near the midpoint between two rows, which is where the discrete question
# is closest to undecided.
MIDPOINT = float(np.mean(depths[2:4]))
base = amplitudes_at_rows(MIDPOINT - 0.10, 2.0, PITCH)
nudged = amplitudes_at_rows(MIDPOINT + 0.10, 2.0, PITCH)
print(f"  the midpoint between rows 2 and 3 is at {MIDPOINT:.2f} mm")
print(f"  amplitudes 0.1 mm below it: {np.round(base, 2)} uV")
print(f"  amplitudes 0.1 mm above it: {np.round(nudged, 2)} uV")
relative_change = float(np.max(np.abs(nudged - base) / base))
print(f"  largest relative change over that 0.2 mm: {relative_change:.1%}")
assert relative_change < 0.15, "two tenths of a millimetre is a small change to the field"

# But the ANSWER to a discrete question flips inside that same small move.
print(f"\\n{'source depth mm':>16} {'amplitudes uV':>36} {'largest row':>12}")
winners = []
for depth in (MIDPOINT - 0.10, MIDPOINT - 0.01, MIDPOINT, MIDPOINT + 0.01, MIDPOINT + 0.10):
    a = amplitudes_at_rows(depth, 2.0, PITCH)
    winners.append(int(np.argmax(a)))
    print(f"{depth:>16.2f} {str(np.round(a, 3)):>36} {winners[-1]:>12}")
assert len(set(winners)) > 1, "the winning row changes across the midpoint"
assert winners[0] != winners[-1], "and it is the two ends that differ"
# At the midpoint itself the two rows are equidistant, so the answer is a tie
# broken by argmax's tie-breaking rule rather than by anything physical.
tied = amplitudes_at_rows(MIDPOINT, 2.0, PITCH)
assert abs(tied[2] - tied[3]) < 1e-9, "at the midpoint the two rows record the same amplitude"

print("\\nThe field moved by seven percent and the answer to 'which row is largest'")
print("changed completely, and at the midpoint itself the two rows record amplitudes")
print("equal to nine decimal places, so which one is reported is decided by the")
print("tie-breaking rule inside argmax. That is the shape of every result in this")
print("lesson: nothing is wrong with the physics or the array, and a categorical reading")
print("of a continuous quantity has places where it is decided by nothing at all.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The measured claim, which imaging cannot help with

Take the electrophysiological question on its own. There is no registration in
it: the amplitudes are measured, and the largest one wins.

Two facts decide how well that works. REC 1 established that an LFP reaches
millimetres, which is larger than the pitch of either lead in
`configs/leads.yaml`, so several rows see the same source at comparable strength.
And STO 1 established that a single segment's periodogram is exponential, which
fixes the spread of the dB value this app computes.

That second number needs care, because STO 1 also established that the two
orderings of averaging and converting behave differently, and the same care is
needed for the spread as for the bias. `psd.py` averages **decibels**, so its
estimate is a mean of $k$ per-segment dB values and its spread is one segment's
spread divided by $\sqrt{k}$, or $(10/\ln 10)\sqrt{\psi_1(1)/k}$, which is 2.78 dB
at four segments. Averaging the power first would give
$(10/\ln 10)\sqrt{\psi_1(k)}$, which is 2.31 dB, and does not describe this app.
Section 2 checks both against simulation rather than taking either on trust.

Put that together with the geometry and the question is whether the gap between
the best row and the second is large compared to the noise on measuring it.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
N_DRAWS = 20_000

# (a) Which spread is the right one? Simulate both orderings rather than trusting
# a formula, because STO 1 was originally wrong about exactly this distinction.
gen0 = np.random.default_rng(77)
print(f"{'segments k':>11} {'dB-then-average':>17} {'closed form':>13} "
      f"{'power-then-dB':>15} {'closed form':>13}")
for k in (4, 16, 64):
    p = gen0.standard_exponential((200_000, k))
    measured_db_first = float(np.std(np.mean(10 * np.log10(p), axis=1)))
    measured_power_first = float(np.std(10 * np.log10(p.mean(axis=1))))
    print(f"{k:>11} {measured_db_first:>17.3f} {db_spread(k):>13.3f} "
          f"{measured_power_first:>15.3f} {db_spread_if_power_averaged(k):>13.3f}")
    assert abs(measured_db_first - db_spread(k)) < 0.03, \
        "psd.py averages decibels, so its spread is one segment's divided by sqrt(k)"
    assert abs(measured_power_first - db_spread_if_power_averaged(k)) < 0.03, \
        "and the trigamma(k) form belongs to the ordering psd.py does not use"
assert db_spread(4) > db_spread_if_power_averaged(4), \
    "the ordering this app uses is the noisier of the two, as well as the more biased"
print(f"\\n  the app's ordering is the noisier one: {db_spread(4):.2f} dB against "
      f"{db_spread_if_power_averaged(4):.2f} at four segments")

# (b) How far does the best row stand out, before any noise?
def separation_db(pitch_mm, radius_range=(1.0, 3.0), n_draws=N_DRAWS, seed=2):
    """How far the best row beats the second, in dB, over random source positions."""
    gen = np.random.default_rng(seed)
    depths = contact_depths(pitch_mm)
    source_depth = gen.uniform(depths[0] - pitch_mm / 2, depths[-1] + pitch_mm / 2, n_draws)
    radius = gen.uniform(*radius_range, n_draws)
    distance = np.hypot(depths[None, :] - source_depth[:, None], radius[:, None])
    ordered = np.sort(20 * np.log10(amplitude_uv(distance)), axis=1)[:, ::-1]
    return ordered[:, 0] - ordered[:, 1]

print(f"\\nhow far the best row beats the second, over random source positions\\n")
print(f"{'pitch mm':>9} {'median gap dB':>15} {'gap below 1 dB':>16}")
gaps = {}
for pitch in PITCHES_MM:
    gaps[pitch] = separation_db(pitch)
    print(f"{pitch:>9.1f} {np.median(gaps[pitch]):>15.2f} {np.mean(gaps[pitch] < 1.0):>15.1%}")
assert np.median(gaps[1.5]) < np.median(gaps[3.0]), "a tighter pitch separates rows less"
assert np.median(gaps[1.5]) < 4.0, "and on the tight lead the gap is a few dB at most"

# (c) Put the estimator noise on it. Two assumptions are being made here and both
# are stated rather than buried: the noise is Gaussian in dB, and it is
# independent across rows. Part (d) tests the second.
def argmax_accuracy(pitch_mm, k_segments, radius_range=(1.0, 3.0),
                    noise_correlation=0.0, n_draws=N_DRAWS, seed=3):
    gen = np.random.default_rng(seed)
    depths = contact_depths(pitch_mm)
    source_depth = gen.uniform(depths[0] - pitch_mm / 2, depths[-1] + pitch_mm / 2, n_draws)
    radius = gen.uniform(*radius_range, n_draws)
    distance = np.hypot(depths[None, :] - source_depth[:, None], radius[:, None])
    truth = 20 * np.log10(amplitude_uv(distance))
    # A shared component plus an independent one gives the requested correlation
    # between any two rows without needing a full covariance matrix.
    shared = gen.standard_normal((n_draws, 1))
    private = gen.standard_normal(truth.shape)
    noise = (np.sqrt(noise_correlation) * shared
             + np.sqrt(1.0 - noise_correlation) * private)
    measured = truth + db_spread(k_segments) * noise
    return float(np.mean(np.argmax(measured, axis=1) == np.argmax(truth, axis=1)))

print(f"\\n{'pitch mm':>9} {'segments k':>11} {'estimator sd dB':>16} "
      f"{'best row identified':>20}")
accuracy = {}
for pitch in PITCHES_MM:
    for k in (4, 16, 64):
        accuracy[(pitch, k)] = argmax_accuracy(pitch, k)
        print(f"{pitch:>9.1f} {k:>11} {db_spread(k):>16.2f} {accuracy[(pitch, k)]:>19.1%}")

assert accuracy[(1.5, 4)] < 0.8, \
    "on the tight lead at four segments the best row is often not the best row"
assert accuracy[(1.5, 64)] > accuracy[(1.5, 4)], "more segments help"
assert accuracy[(3.0, 4)] > accuracy[(1.5, 4)], "and a wider pitch helps more"

# (d) The independence assumption, tested. Rows of one lead share a reference and
# see overlapping sources, so their estimator noise is positively correlated.
# Correlated noise partly cancels in the DIFFERENCE between rows, which is what
# argmax compares, so independence is the pessimistic assumption.
print(f"\\nthe same question with correlated noise across rows, 1.5 mm pitch, k=4\\n")
print(f"{'noise correlation':>18} {'best row identified':>20}")
correlated = {}
for rho in (0.0, 0.3, 0.5, 0.8):
    correlated[rho] = argmax_accuracy(1.5, 4, noise_correlation=rho)
    print(f"{rho:>18.1f} {correlated[rho]:>19.1%}")
assert correlated[0.8] > correlated[0.0], \
    "correlated noise cancels in the comparison, so independence is the pessimistic case"
print(f"\\n  so the {accuracy[(1.5, 4)]:.0%} above is a lower bound. REC 1 measured an LFP reach of")
print("  4.6 mm against a 1.5 mm pitch, so the rows do see overlapping sources and the")
print("  true correlation is not zero.")

# (e) And the source geometry, which the sweep above fixed by assumption.
print(f"\\nsensitivity to the assumed source radius, 1.5 mm pitch, k=4\\n")
print(f"{'radius range mm':>17} {'best row identified':>20}")
by_radius = {}
for lo, hi in ((0.5, 1.5), (1.0, 2.0), (1.0, 3.0), (2.0, 4.0), (3.0, 5.0)):
    by_radius[(lo, hi)] = argmax_accuracy(1.5, 4, radius_range=(lo, hi))
    marker = "  <- used above" if (lo, hi) == (1.0, 3.0) else ""
    print(f"{f'{lo} to {hi}':>17} {by_radius[(lo, hi)]:>19.1%}{marker}")
assert by_radius[(0.5, 1.5)] > by_radius[(3.0, 5.0)], \
    "a source close to the lead is easier to localise along it"
assert max(by_radius.values()) - min(by_radius.values()) > 0.2, \
    "and the exact accuracy depends strongly on an assumption nothing here justifies"

print(f"\\nAt {PITCHES_MM[0]} mm pitch and four segments the reported best row was the true best")
print(f"row {accuracy[(1.5, 4)]:.0%} of the time. The reason is in the columns beside it: the median gap")
print(f"between first and second is {np.median(gaps[1.5]):.1f} dB and the estimator's own spread at four")
print(f"segments is {db_spread(4):.1f} dB. The quantity being compared is smaller than the noise on")
print("measuring it.")
print("\\nThe exact percentage should not be quoted on its own. It moved from "
      f"{min(by_radius.values()):.0%} to {max(by_radius.values()):.0%}")
print("across defensible assumptions about how far the source sits from the lead, and")
print("nothing in this lesson or in REC 1 argues for one of those ranges over another.")
print("What survives the sweep is the shape: accuracy well below certainty at every")
print("setting, worse on the tighter pitch, and better with more segments.")
print("\\nSo the claim that needed no imaging at all is not well determined, and it can be")
print(f"improved without any imaging either: sixty-four segments take it to {accuracy[(1.5, 64)]:.0%}. That is")
print("a recording-length decision, made before the case, and it is the only lever in")
print("this section.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. The anatomical claim, where the margin is the whole story

Now the other half. Suppose the best row is known. Saying it is in a target
requires knowing where the lead sits in the anatomy, and that comes from
registering imaging to an atlas or to a planned trajectory.

The useful way to state a registration error is not as a general accuracy figure
but against the **margin**: how far the contact is from the nearest boundary of
the structure. For a single boundary at distance $m$, with the registration error
Gaussian of standard deviation $\sigma$ along the relevant axis, the chance the
contact is really on the other side is

$$P(\text{flip}) = \Phi\!\left(-\frac{m}{\sigma}\right)$$

one-sided, because only a shift in one direction crosses that boundary. A
structure thin enough that both of its boundaries are within a few $\sigma$ needs
both terms, and Section 4 shows the array where that happens. What matters in
either case is the ratio $m/\sigma$ and nothing else: an accuracy figure quoted
without a margin says nothing at all.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def flip_probability(margin_mm, sigma_mm):
    """Chance a contact this far inside a single boundary is really outside it."""
    if sigma_mm <= 0:
        return 0.0
    return float(stats.norm.sf(margin_mm / sigma_mm))


def flip_probability_thin(margin_mm, half_width_mm, sigma_mm):
    """The same for a structure of finite width, counting both boundaries.

    The contact sits `margin_mm` inside the near boundary, so it is
    2*half_width - margin from the far one.
    """
    if sigma_mm <= 0:
        return 0.0
    far = 2.0 * half_width_mm - margin_mm
    return float(stats.norm.sf(margin_mm / sigma_mm) + stats.norm.sf(far / sigma_mm))


SIGMAS = (0.5, 1.0, 2.0)
print("probability the anatomical label is wrong, one boundary at the stated margin\\n")
print(f"{'margin mm':>10} " + "".join(f"{'sigma ' + str(s) + ' mm':>16}" for s in SIGMAS))
for margin in (0.5, 1.0, 2.0, 3.0):
    print(f"{margin:>10.1f} " + "".join(f"{flip_probability(margin, s):>16.1%}" for s in SIGMAS))

# Check the closed form against a simulation of the thing it actually describes:
# a signed registration shift crossing ONE boundary. Taking the absolute value
# instead would re-derive a two-sided answer and test nothing.
gen = np.random.default_rng(9)
print()
for margin, sigma in ((1.0, 1.0), (2.0, 1.0), (1.0, 2.0)):
    shifts = gen.normal(0.0, sigma, 400_000)
    simulated = float(np.mean(shifts > margin))
    print(f"  margin {margin} mm, sigma {sigma} mm: closed form "
          f"{flip_probability(margin, sigma):.4f}, simulated {simulated:.4f}")
    assert abs(simulated - flip_probability(margin, sigma)) < 0.005, \
        "the one-sided form must match a signed shift crossing one boundary"

# The far boundary contributes essentially nothing unless the structure is thin.
print(f"\\n  a contact 1 mm inside a 6 mm target, sigma 1 mm:")
print(f"    near boundary alone: {flip_probability(1.0, 1.0):.4f}")
print(f"    both boundaries:     {flip_probability_thin(1.0, 3.0, 1.0):.4f}")
assert abs(flip_probability_thin(1.0, 3.0, 1.0) - flip_probability(1.0, 1.0)) < 1e-4, \
    "in a 6 mm target the far boundary is 5 mm away and contributes nothing"
for width in (6.0, 3.0, 2.5):
    both = flip_probability_thin(1.0, width / 2, 1.0)
    print(f"  a contact 1 mm inside a {width:.1f} mm target, sigma 1 mm: {both:.4f}"
          f"  ({both / flip_probability(1.0, 1.0):.2f}x the one-sided answer)")
assert flip_probability_thin(1.0, 1.25, 1.0) > 1.35 * flip_probability(1.0, 1.0), \
    "in a thin structure the far boundary does matter, which is when to use both terms"

# Only the ratio matters, which is the reportable fact.
assert abs(flip_probability(1.0, 0.5) - flip_probability(2.0, 1.0)) < 1e-12, \
    "margin 1 with sigma 0.5 and margin 2 with sigma 1.0 are the same problem"
print(f"\\n  margin 1.0 with sigma 0.5, and margin 2.0 with sigma 1.0, both give "
      f"{flip_probability(1.0, 0.5):.1%}")
assert flip_probability(1.0, 1.0) > 0.15, "at a margin equal to the error it is far from settled"
assert flip_probability(3.0, 1.0) < 0.005, "at three times the error it is settled"

print("\\nA registration accuracy of one millimetre sounds precise and means nothing on")
print(f"its own. Against a three millimetre margin it settles the question at "
      f"{flip_probability(3.0, 1.0):.1%}; against a")
print(f"one millimetre margin it leaves {flip_probability(1.0, 1.0):.0%}, roughly one label in six, on the wrong")
print("side of the boundary.")
print("\\nThe practical consequence is a reporting one. A contact label carries no")
print("information about which of those situations produced it, so the margin belongs")
print("beside it. REC 2 made the same argument about rotation: a segment label without a")
print("known orientation is a direction claim with nothing behind it, and this is the")
print("along-axis version of it.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. Which lead is more robust is not the question it sounds like

A natural reading of Sections 2 and 3 is that the wider pitch is better: it
separates the rows more, so the best-row claim is firmer. That is true and it is
only half of the tradeoff.

The other half is how much of the array sits inside the structure at all, and it
turns out to depend on something narrower than span. A count of rows in a target
is stable when a shift that pushes one row out simultaneously brings another in,
and that happens when the target length is close to a whole multiple of the
pitch. It is a commensurability between two lengths, not a general property of a
long array.

Section 4 measures the count for both leads at one target length, then sweeps the
target length to find out which of the two explanations is doing the work.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
TARGET_LENGTH_MM = 6.0     # a plausible along-axis extent for a subcortical target
N_SHIFTS = 20_000

def rows_inside(pitch_mm, sigma_mm, target_length=TARGET_LENGTH_MM,
                n_shifts=N_SHIFTS, seed=4):
    """Distribution of how many rows are called inside the target, under registration error."""
    gen = np.random.default_rng(seed)
    depths = contact_depths(pitch_mm)
    shifts = gen.normal(0.0, sigma_mm, n_shifts)
    inside = np.abs(depths[None, :] - shifts[:, None]) <= target_length / 2
    return inside.sum(axis=1)

print(f"rows called inside a {TARGET_LENGTH_MM:.0f} mm target, under registration error\\n")
print(f"{'pitch mm':>9} {'array span':>11} {'sigma mm':>9} {'mean rows':>10} "
      f"{'range':>8} {'differs from truth':>19}")
disagreement = {}
for pitch in PITCHES_MM:
    span = contact_depths(pitch)[-1] - contact_depths(pitch)[0]
    truth = int(rows_inside(pitch, 0.0)[0])
    for sigma in (0.0, 1.0, 2.0):
        counts = rows_inside(pitch, sigma)
        disagreement[(pitch, sigma)] = float(np.mean(counts != truth))
        print(f"{pitch:>9.1f} {span:>10.1f} {sigma:>9.1f} {counts.mean():>10.2f} "
              f"{str(counts.min()) + '-' + str(counts.max()):>8} "
              f"{disagreement[(pitch, sigma)]:>18.1%}")

# With no error, both leads give a definite answer.
for pitch in PITCHES_MM:
    assert disagreement[(pitch, 0.0)] == 0.0, "no error, no disagreement"

# The tight lead fits inside the target with little to spare, so a shift pushes a
# row out. The wide lead is longer than the target, so the count is pinned.
assert disagreement[(1.5, 1.0)] > 0.3, \\
    "the short array's count is changed by a 1 mm error in a third of cases"
assert disagreement[(3.0, 1.0)] < 0.05, \\
    "while the long array's is barely touched by the same error"
print(f"\\n  a 1 mm registration error changed the count on the {PITCHES_MM[0]} mm lead "
      f"{disagreement[(1.5, 1.0)]:.0%} of the time")
print(f"  and on the {PITCHES_MM[1]} mm lead {disagreement[(3.0, 1.0)]:.0%} of the time")

# Is that stability about span exceeding the target, or about the target being a
# whole number of pitches? Sweep the target length and find out.
print(f"\\nthe same question at other target lengths, sigma 1 mm\\n")
print(f"{'target mm':>10} {'1.5 mm lead':>13} {'3.0 mm lead':>13}")
sweep = {}
for length in (6.0, 6.5, 6.9, 7.0, 7.5, 9.0):
    sweep[length] = tuple(
        float(np.mean(rows_inside(p_, 1.0, target_length=length)
                      != int(rows_inside(p_, 0.0, target_length=length)[0])))
        for p_ in PITCHES_MM
    )
    print(f"{length:>10.2f} {sweep[length][0]:>12.1%} {sweep[length][1]:>12.1%}")

# The wide lead's perfect stability is specific to 6 mm, which is exactly two of
# its 3 mm pitches. Move the target half a millimetre and it is gone.
assert sweep[6.0][1] < 0.01, "at 6 mm, two whole pitches, the wide lead's count is pinned"
assert sweep[6.5][1] > 10 * max(sweep[6.0][1], 1e-4), \
    "half a millimetre of target length destroys it, so this is commensurability"
crossover = next(length for length in sorted(sweep) if sweep[length][1] > sweep[length][0])
print(f"\\n  the ordering reverses between {max(l for l in sorted(sweep) if l < crossover):.1f} "
      f"and {crossover:.1f} mm of target length,")
print(f"  and at 9 mm, where the wide lead's span equals the target exactly so both end")
print(f"  rows sit on a boundary, it is wrong {sweep[9.0][1]:.0%} of the time against the tight")
print(f"  lead's {sweep[9.0][0]:.0%}")
assert crossover < 7.5, "the reversal is within a millimetre of the target used above"
assert sweep[9.0][1] > 0.9, "and at 9 mm the wide lead is the unstable one"

print("\\nSo the wide lead's perfect score at 6 mm was not robustness. It was a coincidence")
print("between two lengths: 6 mm is exactly two of its 3 mm pitches, so a shift that")
print("pushes one row out of the target brings the next one in at the same moment, and")
print("the count never changes. Half a millimetre of target length destroys it, and by")
print(f"{crossover:.1f} mm the ordering has reversed.")
print("\\nThe first question, which row is largest, really is about pitch, and the wide")
print("lead really is better at it at every setting tested. The second is not about span")
print("or pitch but about how the two lengths line up, which is a property of the pair")
print("and not of the lead. A lead is not robust or fragile on its own: it is robust for")
print("a question, given a structure, and a comparison that does not name both is")
print("comparing nothing.")

print("\\n--- WHAT TO REPORT ---")
print("\\nThree numbers turn every claim in this lesson from a label into something a")
print("reader can check, and the app already has two of them.")
print("\\n  1. The segment count behind each dB value. Section 2 turns it into a")
print("     probability that the best row is the best row. psd.py already stores it as")
print("     n_segments.")
print("  2. The gap in dB between the best row and the second. Section 2 shows it is")
print("     the quantity the estimator noise has to beat, and it is computable from")
print("     numbers already in the run.")
print("  3. The margin from the contact to the nearest boundary of the named structure,")
print("     with the registration error. Section 3 shows the ratio of those two is the")
print("     whole answer. This one the app does not have, because it does not do")
print("     registration at all.")
print("\\nThe third is why this lesson does not propose a guardrail. A rule that fires on")
print("a margin needs a margin, and nothing in the pipeline produces one. What the")
print("lesson supports today is a wording rule rather than a check: a figure that names")
print("a target is making a claim the recording cannot support on its own.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. **A smooth field read through a categorical question has places where the
   answer is decided by nothing.** Moving a source 0.2 mm across the midpoint
   between two rows changed every amplitude by 7 percent and changed which row
   was largest. At the midpoint the two rows record the same amplitude bit for
   bit, so which is reported comes from the tie-breaking inside `argmax`.
2. **The estimator's spread depends on which ordering the recipe uses, and this
   app uses the noisier one.** `psd.py` averages decibels, so its spread is one
   segment's divided by sqrt(k), which is 2.78 dB at four segments. Averaging the
   power first would give 2.31 dB. Both were verified by simulation, because STO
   1 was originally wrong about this same distinction for the bias.
3. **The claim that needs no imaging is not well determined.** On a 1.5 mm pitch
   lead the median gap between the best row and the second is 1.98 dB, smaller
   than the estimator spread it must beat. The reported best row was the true
   best row 67 percent of the time at four segments, 80 at sixteen, 90 at
   sixty-four. That last is a recording-length decision made before the case, and
   it is the only lever.
4. **That percentage is an assumption as much as a measurement.** It ranged from
   44 to 86 percent across defensible ranges for how far the source sits from the
   lead, and nothing here or in REC 1 argues for one range. It also assumes the
   estimator noise is independent across rows, which is the pessimistic choice:
   at a noise correlation of 0.8 the same setting gives 82 percent, and REC 1's
   4.6 mm reach against a 1.5 mm pitch means the true correlation is not zero.
   What survives is the shape, not the number.
5. **A registration accuracy figure means nothing without a margin.** For a
   single boundary the chance of a wrong label is Phi(-margin/sigma), verified
   against a signed shift crossing that boundary. One millimetre of error against
   a one millimetre margin leaves 16 percent, about one label in six; against
   three millimetres it leaves 0.1. Only the ratio matters. A second boundary
   contributes nothing in a 6 mm target and 42 percent more in a 2.5 mm one.
6. **The stability of a contact count is a property of two lengths, not of a
   lead.** A 1 mm error changed the rows-in-target count 45 percent of the time
   on the 1.5 mm lead and 0 percent on the 3.0 mm lead, at a 6 mm target. That
   zero is a coincidence: 6 mm is exactly two of the wide lead's pitches, so a
   shift pushing one row out brings another in at the same instant. Half a
   millimetre of target length takes it to 13 percent, the ordering reverses by
   6.9 mm, and at 9 mm the wide lead is wrong every time.
7. **Two of the three numbers a reader needs are already stored and the third
   does not exist.** Segment count and the best-to-second gap are computable from
   what `psd.py` writes. The margin is not, because this pipeline performs no
   registration, which is why this lesson ends in a wording rule and not a
   guardrail.

The sentence this lesson started with, "contact 2b, in STN, showed the effect",
contains one claim the recording supports weakly, one it does not support at all,
and one it supports well. The effect is the well-supported part.

Two of this lesson's own numbers moved during review, both because a formula was
attached to the wrong branch of a two-way choice. That is the same error STO 1
made about the dB bias, repeated here about the dB spread, in a lesson that cites
the corrected STO 1. The habit that catches it is in Section 2 part (a): simulate
both branches and let the measurement pick.

### Exercises

**Exercise 1.** `configs/leads.yaml` records contact spacing only inside a model
name string, as "3389 (1.5 mm spacing)". Propose the field it should carry
instead, and say which of this lesson's four sections could then be computed for
a real run rather than swept over a plausible range.

**Exercise 2.** Section 2 held the source on the lead axis at a random radius.
REC 2 showed that a segmented row resolves direction only if the rotation is
known. Repeat Section 2 for the segments of one row rather than for the rows, and
say whether an unknown rotation makes the best-segment claim worse than the
best-row claim or merely different.

**Exercise 3.** Section 4 ends in a wording rule. Write it: the sentence a figure
legend should use when the target is named but no registration was performed, and
the sentence it should use when one was. State what the second needs stored that
the first does not.

---

That is the end of Recording Physics and Electrode Geometry. REC 1 established
what a contact can hear, REC 2 what its label means around the lead, REC 3 and
REC 4 how the array samples space, and this lesson what happens when a smooth
field is read through a discrete question.
''')

m.emit()
verify("03_spatial", "05_localization_and_contact_labels")
print("  REC 5 OK")
