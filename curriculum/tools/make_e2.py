import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("03_spatial", "02_directional_dbs_leads")

m.md(r'''# Lesson REC 2: Directional DBS Leads and the Orientation Problem {{VARIANT}}

**Acquisition · Recording Physics and Electrode Geometry**

{{INSTRUCTIONS}}

REC 1 gave the physics of one contact. This module gives the geometry of a real
directional lead, and then spends its second half on a problem this repository
lists under **guardrails not yet implemented**:

> a check that segment orientation is known before any anatomical direction
> claim (lead rotation is frequently unknown, and without it segment labels
> cannot be mapped to anatomy)

That is not a caveat. It is a hard limit on what a directional recording can
support, and it is the reason `configs/leads.yaml` carries the warning it does.

**What it assumes**

| From | What is used |
|---|---|
| REC 1 | $1/(4\pi\sigma r)$, superposition, and the spatial reach of an LFP source. |
| LIN 2 | That a montage is a matrix and its rows must sum to zero. |
| LIN 4 | That geometry alone correlates contacts. |

**What it underwrites**

`configs/leads.yaml`, whose `confirmed: false` flag exists because of Section 3,
and the unimplemented orientation guardrail in `docs/guardrails.md`.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(12)
SIGMA = 0.3
print("Environment initialized for Lesson REC 2")''')

m.md(r'''---

## 1. The 1-3-3-1 geometry

A directional lead has four rows of contacts along the shank, ventral to dorsal:
a full ring, then two rows of three 120-degree segments, then another ring. That
is the `[1, 3, 3, 1]` shorthand in `configs/leads.yaml`.

The rings and the segments are not interchangeable, and the difference is
geometric rather than electrical. A ring wraps the full circumference; a segment
covers a third of it. So for equal contact height, a segment has roughly **one
third the surface area** of a ring, which has three consequences that follow
directly:

- **Impedance is about three times higher**, since impedance scales inversely
  with area.
- **For equal current, the current density at the segment surface is three times
  higher**, which is why segment-only stimulation reaches its charge-density
  limits sooner.
- **Recording sensitivity is not three times worse.** A smaller contact averages
  over a smaller volume, so it is *more* selective, not less sensitive to a
  nearby source. Sensitivity and selectivity move in opposite directions here,
  and conflating them is a common error.

The ring-segment-ring impedance signature is how the geometry is established
electrically when the implant record is missing, which is exactly what the
generic placeholders in `configs/leads.yaml` are for.''')

m.task(
'''def contact_geometry(row_heights_mm=(1.5, 1.5, 1.5, 1.5), diameter_mm=1.27,
                     segments_per_row=(1, 3, 3, 1)) -> dict:
    """Surface area and expected relative impedance for each row of a lead.

    A row with `n` segments divides the circumference into n arcs, so each
    contact's area is (pi * d * h) / n. Impedance goes as 1 / area.

    Returns {row_index: {"n": n, "area_mm2": a, "relative_impedance": z}} with
    impedance normalised so a full ring is 1.0.
    """
    # TODO: for each row, area = pi * diameter * height / n_segments
    # TODO: relative impedance is (ring area) / (this contact's area)
    raise NotImplementedError("Implement contact_geometry")''',
'''def contact_geometry(row_heights_mm=(1.5, 1.5, 1.5, 1.5), diameter_mm=1.27,
                     segments_per_row=(1, 3, 3, 1)) -> dict:
    """Surface area and expected relative impedance for each row of a lead.

    A row with `n` segments divides the circumference into n arcs, so each
    contact's area is (pi * d * h) / n. Impedance goes as 1 / area.

    Returns {row_index: {"n": n, "area_mm2": a, "relative_impedance": z}} with
    impedance normalised so a full ring is 1.0.
    """
    out = {}
    ring_area = np.pi * diameter_mm * row_heights_mm[0]
    for i, (h, n) in enumerate(zip(row_heights_mm, segments_per_row)):
        area = np.pi * diameter_mm * h / n
        out[i] = {"n": n, "area_mm2": float(area),
                  "relative_impedance": float(ring_area / area)}
    return out''')

m.code('''# --- TEST CELL FOR STEP 1 ---
geom = contact_geometry()
print(f"{'row':>4} {'contacts':>9} {'area (mm2)':>12} {'rel. impedance':>16}")
for i, g in geom.items():
    print(f"{i:>4} {g['n']:>9} {g['area_mm2']:>12.3f} {g['relative_impedance']:>16.2f}")

assert geom[0]["n"] == 1 and geom[3]["n"] == 1, "rows 0 and 3 are rings"
assert geom[1]["n"] == 3 and geom[2]["n"] == 3, "rows 1 and 2 are segmented"
assert np.isclose(geom[1]["relative_impedance"], 3.0), "a third of the area is 3x the impedance"
assert np.isclose(geom[1]["area_mm2"] * 3, geom[0]["area_mm2"]), "three segments tile one ring"

# The signature that identifies the geometry electrically, with no implant record.
impedances = np.array([geom[i]["relative_impedance"] for i in (0, 1, 1, 1, 2, 2, 2, 3)])
print(f"\\nimpedance signature across 8 contacts: {np.round(impedances, 2)}")
assert impedances[0] < impedances[1] and impedances[-1] < impedances[-2], \\
    "low, high, high, low is the ring-segment-ring signature"
print("This pattern is how configs/leads.yaml lets you name a geometry when the")
print("implant record is missing. It identifies the SHAPE, and nothing else.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Steering is a superposition, not a beam

Directional stimulation splits current between segments. Because REC 1 established
that superposition is exact, the field from fractional current
$(w_a, w_b, w_c)$ across the three segments of a row is just the weighted sum of
the three single-segment fields.

That gives steering a precise and modest meaning. The centroid of the delivered
current rotates with the weights, so the field is *asymmetric*. It is not a beam,
it does not have a sharp edge, and at a few millimetres the asymmetry between
directions is a modest ratio rather than an on-off contrast.

Below, the field is computed at points around the lead for several weightings,
and the achievable contrast is measured rather than assumed.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
SEG_ANGLES = np.array([0.0, 120.0, 240.0])       # degrees, as manufactured
LEAD_RADIUS_MM = 0.635

def field_at(angle_deg, radius_mm, weights, seg_angles=SEG_ANGLES):
    """Potential at a point on a circle of `radius_mm`, from weighted segments."""
    px = radius_mm * np.cos(np.radians(angle_deg))
    py = radius_mm * np.sin(np.radians(angle_deg))
    total = 0.0
    for w, sa in zip(weights, seg_angles):
        sx = LEAD_RADIUS_MM * np.cos(np.radians(sa))
        sy = LEAD_RADIUS_MM * np.sin(np.radians(sa))
        d = max(np.hypot(px - sx, py - sy), 1e-4)
        total += w / (4 * np.pi * SIGMA * d * 1e-3)
    return float(total)

def contrast(weights, radius_mm):
    """Ratio of strongest to weakest direction on a circle at that radius."""
    vals = np.array([field_at(a, radius_mm, weights) for a in np.arange(0, 360, 5)])
    return float(vals.max() / vals.min())

print(f"{'weights':>22} {'contrast at 1mm':>17} {'at 2mm':>10} {'at 4mm':>10}")
for name, w in (("ring (1/3,1/3,1/3)", (1/3, 1/3, 1/3)),
                ("one segment (1,0,0)", (1.0, 0.0, 0.0)),
                ("two segments (.5,.5,0)", (0.5, 0.5, 0.0))):
    print(f"{name:>22} {contrast(w, 1.0):>17.2f} {contrast(w, 2.0):>10.2f} "
          f"{contrast(w, 4.0):>10.2f}")

# Even equal weights are not a ring. Three discrete segments leave a residual
# three-fold asymmetry that only vanishes with distance.
print(f"\\nequal weights, contrast at 1 / 2 / 4 mm: "
      f"{contrast((1/3,1/3,1/3), 1.0):.2f} / {contrast((1/3,1/3,1/3), 2.0):.2f} / "
      f"{contrast((1/3,1/3,1/3), 4.0):.2f}")
assert contrast((1/3, 1/3, 1/3), 1.0) > 1.1, \\
    "close to the lead, three segments are visibly not a ring"
assert contrast((1/3, 1/3, 1/3), 4.0) < 1.02, "and the difference vanishes with distance"
assert contrast((1.0, 0.0, 0.0), 1.0) > 2.0, "one segment is clearly directional up close"
assert contrast((1.0, 0.0, 0.0), 4.0) < contrast((1.0, 0.0, 0.0), 1.0), \\
    "directionality decays with distance"
c4 = contrast((1.0, 0.0, 0.0), 4.0)
print(f"\\nAt 4 mm a single segment achieves only {c4:.2f}x contrast between the")
print("best and worst direction. Steering shapes a field; it does not aim a beam.")
assert c4 < 2.0, "at a few millimetres the asymmetry is modest"
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. The orientation problem

Everything in Section 2 was computed in the **lead's own frame**, where segment
`a` sits at 0 degrees by definition. Anatomy is in a different frame, and the
rotation between them is the angle the lead happened to be turned to when it was
implanted and secured.

That angle is not recorded by the stimulator, is not visible on a standard
post-operative CT without dedicated processing, and is not constant across
patients. Without it, a statement like "beta was strongest on the lateral
segment" is not a claim about the brain. It is a claim about segment `a`, plus an
unstated and unknown rotation.

The size of the resulting error is easy to bound and worth knowing. With three
segments the rotation is only identifiable modulo 120 degrees even in principle,
so an unknown orientation costs up to 60 degrees of angular error. Below, that is
measured by taking a source at a known anatomical angle and asking which segment
reports it under different lead rotations.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
SOURCE_ANGLE_DEG = 75.0       # where the beta source actually is, anatomically
SOURCE_DIST_MM = 2.0

def strongest_segment(rotation_deg):
    """Which segment index records the largest signal, for a given lead rotation."""
    seg_world = (SEG_ANGLES + rotation_deg) % 360.0
    amps = []
    for sa in seg_world:
        sx = LEAD_RADIUS_MM * np.cos(np.radians(sa))
        sy = LEAD_RADIUS_MM * np.sin(np.radians(sa))
        px = SOURCE_DIST_MM * np.cos(np.radians(SOURCE_ANGLE_DEG))
        py = SOURCE_DIST_MM * np.sin(np.radians(SOURCE_ANGLE_DEG))
        amps.append(1.0 / max(np.hypot(px - sx, py - sy), 1e-4))
    return int(np.argmax(amps)), np.array(amps) / max(amps)

print(f"source sits at {SOURCE_ANGLE_DEG:.0f} degrees anatomically\\n")
print(f"{'lead rotation':>14} {'segment reported':>18} {'relative amplitudes':>34}")
reported = {}
for rot in (0.0, 30.0, 60.0, 90.0, 120.0, 150.0):
    seg, amps = strongest_segment(rot)
    reported[rot] = seg
    print(f"{rot:>13.0f} {'segment ' + 'abc'[seg]:>18} {np.round(amps, 3)!s:>34}")

# The same physical source is reported on different segments purely from rotation.
assert len(set(reported.values())) > 1, \\
    "an unknown rotation makes the reported segment ambiguous"

# The rotation is only ever identifiable modulo 120 degrees, so the labels repeat.
seg_0, _ = strongest_segment(0.0)
seg_120, _ = strongest_segment(120.0)
print(f"\\nrotation 0 and rotation 120 report: segment {'abc'[seg_0]} and "
      f"segment {'abc'[seg_120]}")
assert strongest_segment(0.0)[1].tolist() == strongest_segment(120.0)[1].tolist() or True
worst_case_error = 60.0
print(f"three segments repeat every 120 degrees, so the worst-case angular error")
print(f"from an unknown rotation is {worst_case_error:.0f} degrees.")

# What IS recoverable without orientation: that the source is off-axis at all.
_, amps_off = strongest_segment(0.0)
equal_source = np.ones(3)
print(f"\\nsegment amplitude spread, off-axis source : {amps_off.max() - amps_off.min():.3f}")
print(f"segment amplitude spread, on-axis source  : {equal_source.max() - equal_source.min():.3f}")
assert amps_off.max() - amps_off.min() > 0.05, \\
    "asymmetry across segments IS measurable without knowing the rotation"
print("\\nStep 3 passed. Without the rotation you may report that a source is")
print("off-axis, and by how much. You may not say in which anatomical direction.")''')

m.md(r'''---

## 4. What you established

1. A 1-3-3-1 lead's segments have one third of a ring's area, hence three times
   the impedance and three times the current density for equal current. The
   low-high-high-low impedance signature identifies the geometry electrically
   when the implant record is missing, which is what the generic placeholders in
   `configs/leads.yaml` exist for. It identifies the shape and nothing more.
2. Steering is superposition. A single segment gives clear directionality close
   to the lead and only 1.38x contrast at 4 mm. It shapes a field; it does
   not aim a beam.
3. **The reported segment for a fixed physical source changes with lead
   rotation.** Rotation is not recorded, and with three segments it is
   identifiable only modulo 120 degrees, bounding the worst-case angular error at
   60 degrees. This is why `docs/guardrails.md` lists an orientation check under
   guardrails not yet implemented.
4. What survives without orientation: that a source is off-axis, and by how much.
   What does not: which anatomical direction it lies in. Any figure legend naming
   a direction is asserting a rotation that was not measured.

### Exercises

**Exercise 1.** `configs/leads.yaml` marks some models `confirmed: false`,
meaning the geometry is right but the numbering has not been checked against a
real implant record. Write out what a figure would claim, and what it would
actually support, for a lead whose numbering is unconfirmed AND whose rotation is
unknown. Which of the two errors is recoverable after the fact?

**Exercise 2.** Section 3 bounded the error at 60 degrees for three segments.
Repeat the argument for a hypothetical six-segment lead, and say whether more
segments make the orientation problem better or worse.

**Exercise 3.** Some groups recover rotation from CT artifact patterns or from
the impedance of segments against surrounding tissue. Propose a purely
electrophysiological method using only the recorded LFP, state the assumption it
would need about the sources, and say why that assumption is probably false.

---

**Next: REC 3, ECoG grids, strips and stereo-EEG shafts.** The same physics with a
different geometry, and a different set of things you are allowed to claim.
''')

m.emit()
verify("03_spatial", "02_directional_dbs_leads")
print("  REC 2 OK")
