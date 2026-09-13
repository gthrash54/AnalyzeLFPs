import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("03_spatial", "03_ecog_grids_and_seeg")

m.md(r'''# Lesson REC 3: ECoG Grids, Strips, and Stereo-EEG Shafts {{VARIANT}}

**Acquisition · Recording Physics and Electrode Geometry**

{{INSTRUCTIONS}}

REC 1 and REC 2 covered a lead that goes into a nucleus. This module covers arrays that
sit on or pass through cortex, and its centre is a result that SIG 1 already taught
in a different domain: **an electrode array samples space, so it can alias in
space**, and the consequences are exactly as irreversible as they were in time.

**What it assumes**

| From | What is used |
|---|---|
| SIG 1 | The sampling theorem, the folding map, and that aliasing is irreversible. |
| SIG 3 | That the Fourier transform applies to any sampled coordinate, not only time. |
| REC 1 | $1/(4\pi\sigma r)$, superposition, and spatial reach. |

**What it underwrites**

Any claim that an effect is focal, and any comparison of spatial extent between
a grid and a strip with different spacing.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(14)
SIGMA = 0.3
print("Environment initialized for Lesson REC 3")''')

m.md(r'''---

## 1. A contact is a spatial average, not a point

REC 1 treated contacts as points. A real ECoG electrode is a disc 2 to 3 mm across
for a standard clinical grid, and it measures the **average** potential over its
surface, not the potential at its centre.

Averaging over a disc of diameter $d$ is a convolution in space, so it is a
spatial low-pass filter with a cutoff around $1/d$. A standard 2.3 mm clinical
contact therefore cannot report structure finer than a couple of millimetres, no
matter how densely the grid is spaced, because the individual measurement has
already blurred it.

High-density arrays shrink the contact as well as the spacing, and both matter
for different reasons: contact size sets the blur, spacing sets what comes next.''')

m.task(
'''def disc_average_potential(source_xy, source_current_a, contact_xy, contact_diameter_mm,
                           depth_mm=1.0, n_samples=400, sigma=SIGMA, rng=None) -> float:
    """Mean potential over a circular contact, from one point source below it.

    Sample `n_samples` points uniformly over the disc and average the monopole
    potential from the source at `depth_mm` below the plane.
    """
    # TODO: draw n_samples uniform points in a disc of the given diameter,
    #       centred on contact_xy (hint: r = R*sqrt(u) for uniform area sampling)
    # TODO: distance from each point to the source, including depth_mm in z
    # TODO: return the mean of I / (4 pi sigma r), with r in metres
    raise NotImplementedError("Implement disc_average_potential")''',
'''def disc_average_potential(source_xy, source_current_a, contact_xy, contact_diameter_mm,
                           depth_mm=1.0, n_samples=400, sigma=SIGMA, rng=None) -> float:
    """Mean potential over a circular contact, from one point source below it.

    Sample `n_samples` points uniformly over the disc and average the monopole
    potential from the source at `depth_mm` below the plane.
    """
    gen = np.random.default_rng(0) if rng is None else rng
    radius = contact_diameter_mm / 2.0
    u = gen.random(n_samples)
    theta = gen.random(n_samples) * 2 * np.pi
    rr = radius * np.sqrt(u)
    px = contact_xy[0] + rr * np.cos(theta)
    py = contact_xy[1] + rr * np.sin(theta)
    d_mm = np.sqrt((px - source_xy[0]) ** 2 + (py - source_xy[1]) ** 2 + depth_mm ** 2)
    return float(np.mean(source_current_a / (4 * np.pi * sigma * d_mm * 1e-3)))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
gen = np.random.default_rng(1)

# (a) A very small contact must reproduce the point-source answer.
point = 1e-9 / (4 * np.pi * SIGMA * 1.0e-3)
tiny = disc_average_potential((0, 0), 1e-9, (0, 0), 0.01, depth_mm=1.0, n_samples=8000, rng=gen)
print(f"point-source potential at 1 mm : {point*1e6:.3f} uV")
print(f"0.01 mm contact, averaged      : {tiny*1e6:.3f} uV")
assert abs(tiny - point) / point < 0.01, "a tiny contact must agree with the point formula"

# (b) A large contact reads LESS from a source directly beneath it, because most of
# its area is further away. Averaging is a low-pass, and low-pass loses peaks.
print(f"\\n{'contact diameter':>18} {'reading over source':>21}")
readings = {}
for d in (0.05, 0.5, 2.3, 5.0):
    readings[d] = disc_average_potential((0, 0), 1e-9, (0, 0), d, depth_mm=1.0,
                                         n_samples=20000, rng=gen)
    print(f"{d:>15.2f} mm {readings[d]*1e6:>18.3f} uV")
assert readings[5.0] < readings[0.05], "a bigger contact reads a focal source lower"

# (c) The blur, measured: scan a source past contacts of two sizes and compare the
# width of the resulting spatial profile.
offsets = np.linspace(-6, 6, 61)
def profile(diameter):
    v = np.array([disc_average_potential((o, 0), 1e-9, (0, 0), diameter, depth_mm=1.0,
                                         n_samples=4000, rng=np.random.default_rng(7))
                  for o in offsets])
    return v / v.max()

def fwhm_mm(prof):
    above = prof > 0.5
    idx = np.flatnonzero(above)
    return float(offsets[idx[-1]] - offsets[idx[0]])

for d in (0.5, 2.3, 5.0):
    print(f"contact {d:>4.1f} mm: spatial FWHM {fwhm_mm(profile(d)):.2f} mm")
assert fwhm_mm(profile(5.0)) > fwhm_mm(profile(0.5)), "a larger contact blurs more"
print("\\nStep 1 passed. Contact size sets a blur that no amount of dense spacing undoes.")''')

m.md(r'''---

## 2. Spatial aliasing, which is SIG 1 in a different coordinate

SIG 1's argument used time only incidentally. Sampling any coordinate at spacing
$\Delta x$ imposes a Nyquist limit at

$$k_{\text{Nyquist}} = \frac{1}{2\Delta x} \quad \text{cycles per mm}$$

and any spatial structure finer than that folds down, by the same map, into a
coarser apparent pattern. On a clinical grid with 10 mm spacing, structure
repeating every 5 mm or faster is not merely missed. It reappears as something
larger and smoother, and it is not recoverable afterwards.

The physics is on your side here in a way it was not in time. Section 1's contact
blur is a genuine anti-alias filter, applied by geometry rather than by choice, so
a large contact on a widely spaced grid is partly protected. A **small** contact
on a **widely spaced** grid is the dangerous combination: sharp measurements,
sparsely sampled, with nothing suppressing the fine structure before it folds.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
def spatial_alias(k_true_per_mm, spacing_mm):
    """Apparent spatial frequency after sampling at `spacing_mm`. SIG 1's folding map."""
    ks = 1.0 / spacing_mm
    folded = k_true_per_mm % ks
    return float(min(folded, ks - folded))

print(f"{'true (cyc/mm)':>15} {'period (mm)':>13} {'apparent':>10} {'apparent period':>17}")
for k in (0.02, 0.05, 0.10, 0.14, 0.20):
    a = spatial_alias(k, 10.0)
    period = 1 / k
    ap = f"{1/a:>13.1f} mm" if a > 1e-9 else "     uniform"
    print(f"{k:>15.3f} {period:>13.1f} {a:>10.3f} {ap:>17}")

assert spatial_alias(0.02, 10.0) == 0.02, "structure coarser than Nyquist is faithful"
assert spatial_alias(0.14, 10.0) < 0.05, "finer structure folds to something coarser"
assert np.isclose(spatial_alias(0.10, 10.0), 0.0), "exactly at the sampling frequency it looks uniform"

# The demonstration: a cortical pattern sampled by two grids.
x_fine = np.linspace(0, 80, 4001)
K_TRUE = 0.14                                  # cycles/mm, a ~7 mm repeat
pattern = np.sin(2 * np.pi * K_TRUE * x_fine)

print(f"\\ntrue pattern: {1/K_TRUE:.1f} mm repeat")
for spacing, label in ((10.0, "clinical grid, 10 mm"), (4.0, "high density, 4 mm"),
                       (2.0, "very dense, 2 mm")):
    xs = np.arange(0, 80, spacing)
    samples = np.sin(2 * np.pi * K_TRUE * xs)
    k_apparent = spatial_alias(K_TRUE, spacing)
    nyq = 1 / (2 * spacing)
    ok = "faithful" if K_TRUE < nyq else f"ALIASED to {1/k_apparent:.1f} mm"
    print(f"  {label:>22}: Nyquist {nyq:.3f} cyc/mm -> {ok}")

assert K_TRUE > 1 / (2 * 10.0), "a 7 mm pattern is above the Nyquist of a 10 mm grid"
assert K_TRUE < 1 / (2 * 2.0), "and below that of a 2 mm grid"
print("\\nStep 2 passed. The grid spacing decides what spatial scales exist for you,")
print("and structure below it does not vanish, it is relabelled.")''')

m.md(r'''---

## 3. Stereo-EEG samples a volume, and mostly does not

An sEEG shaft carries contacts along a line through a three-dimensional volume.
Along the shaft the spacing is a few millimetres, so Section 2's argument applies
directly. Perpendicular to it there is no sampling at all: the nearest other
shaft may be centimetres away.

The right way to think about the resulting coverage is as a fraction of the
volume within reach of any contact, and REC 1 supplies the reach. Below, that
fraction is computed for a realistic implant.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
LFP_REACH_MM = 4.6          # from REC 1
BRAIN_VOLUME_CM3 = 1200.0

def implant_coverage(n_shafts, contacts_per_shaft, reach_mm=LFP_REACH_MM,
                     contact_spacing_mm=3.5):
    """Fraction of a brain volume within `reach_mm` of any contact.

    Contacts on one shaft overlap heavily, so model each shaft as a cylinder of
    radius `reach_mm` and length (contacts-1)*spacing + 2*reach, rather than
    summing spheres and double counting.
    """
    length_mm = (contacts_per_shaft - 1) * contact_spacing_mm + 2 * reach_mm
    per_shaft_mm3 = np.pi * reach_mm ** 2 * length_mm
    total_cm3 = n_shafts * per_shaft_mm3 / 1000.0
    return float(total_cm3 / BRAIN_VOLUME_CM3), float(total_cm3)

print(f"{'implant':>34} {'volume covered':>16} {'fraction':>10}")
for n, c, label in ((8, 10, "8 shafts, 10 contacts"),
                    (14, 12, "14 shafts, 12 contacts"),
                    (20, 16, "20 shafts, 16 contacts")):
    frac, vol = implant_coverage(n, c)
    print(f"{label:>34} {vol:>13.1f} cm3 {frac:>9.1%}")

frac_typical, _ = implant_coverage(14, 12)
assert frac_typical < 0.25, "even a large sEEG implant reaches a minority of the brain"
assert frac_typical > 0.02, "but it is not negligible either"
print(f"\\nA typical implant is within LFP reach of {frac_typical:.0%} of the volume.")

# Sensitivity to the reach assumption, which is the weakest number here.
print(f"\\n{'assumed reach':>15} {'coverage':>10}")
for r in (2.0, 4.6, 8.0):
    print(f"{r:>12.1f} mm {implant_coverage(14, 12, reach_mm=r)[0]:>9.1%}")
lo = implant_coverage(14, 12, reach_mm=2.0)[0]
hi = implant_coverage(14, 12, reach_mm=8.0)[0]
assert hi > 3 * lo, "the answer depends strongly on a reach that REC 1 could only estimate"
print("\\nThe spread across plausible reaches is large, which is the honest finding:")
print("coverage is a number you must state your assumptions for, not quote.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. What you established

1. A contact averages over its surface, so contact **size** applies a spatial
   low-pass. A 5 mm contact reads a focal source lower than a 0.05 mm one and
   blurs the spatial profile measurably. No spacing choice undoes that blur.
2. Sampling space aliases exactly as sampling time does. On a 10 mm clinical
   grid, structure repeating every 7 mm folds and reappears as a coarser pattern,
   irreversibly. Contact size acts as a physical anti-alias filter, so small
   contacts on a widely spaced grid are the dangerous combination.
3. An sEEG implant of 14 shafts is within LFP reach of under 4 percent of the
   brain volume, and that figure moves from 0.6 to 12.8 percent across
   plausible assumptions about reach alone. It is a number to state assumptions
   for, not to quote.

### Exercises

**Exercise 1.** Compute the contact diameter that would act as a matched
anti-alias filter for a 10 mm grid, in the sense that its spatial cutoff sits at
the grid's spatial Nyquist. Compare it to standard clinical contact sizes. Are
clinical grids accidentally well designed?

**Exercise 2.** High-gamma activity is often treated as a proxy for local firing
and reported as focal. Using Section 1's blur and Section 2's aliasing, state the
smallest spatial extent a standard clinical grid can honestly claim, and find a
published claim finer than that.

**Exercise 3.** Section 3 modelled each shaft as a cylinder. Two shafts 8 mm
apart have overlapping cylinders. Redo the calculation with the overlap removed
and say whether the conclusion changes.

---

**Next: REC 4, Neuropixels.** The opposite regime: hundreds of sites at 20 micron
pitch, where space is oversampled rather than undersampled, and the problems are
entirely different.
''')

m.emit()
verify("03_spatial", "03_ecog_grids_and_seeg")
print("  REC 3 OK")
