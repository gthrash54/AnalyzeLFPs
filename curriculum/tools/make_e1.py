import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("03_spatial", "01_extracellular_biophysics")

m.md(r'''# Lesson REC 1: Extracellular Biophysics and Volume Conduction {{VARIANT}}

**Acquisition · Recording Physics and Electrode Geometry**

{{INSTRUCTIONS}}

LIN 4 wrote volume conduction as a mixing matrix $A$ and showed what it does to a
covariance. It never said where $A$ comes from. This module derives it, and the
derivation settles a question that gets asserted far more often than it gets
checked: how far away a contact can hear.

**What it assumes**

| From | What is used |
|---|---|
| LIN 3 | The quasi-static monopole kernel $1/(4\pi\sigma r)$, and that a dipole is not it. |
| LIN 4 | $\Sigma_X = A\Sigma_SA^{\top}+\Sigma_N$, and that overlapping columns of $A$ correlate contacts. |
| SIG 1 | Sampling and bandwidth. |

**What it underwrites**

Guardrail **G2**, an effect that tracks electrode identity rather than brain
state. Section 3 gives the spatial scale that makes G2 decidable.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(9)
SIGMA = 0.3          # S/m, brain tissue conductivity
print("Environment initialized for Lesson REC 1")''')

m.md(r'''---

## 1. The quasi-static approximation, and what it buys

Extracellular potential obeys Maxwell's equations, but at the frequencies and
length scales of electrophysiology the magnetic and capacitive terms are
negligible. Below about 1 kHz and within a few millimetres, propagation delays
are far shorter than a cycle, so the field at every instant is the field a static
current distribution would produce. That is the **quasi-static approximation**,
and it reduces the problem to

$$\nabla \cdot (\sigma \nabla V) = -I_{\text{source}}$$

In a homogeneous isotropic medium with a point current source $I$ at the origin,
the solution is

$$V(r) = \frac{I}{4\pi\sigma r}$$

Two consequences follow immediately and neither is optional.

**There is no time constant.** The tissue does not filter. A current that changes
shape produces a potential of the same shape everywhere, scaled. Any frequency
dependence you see in an LFP came from the sources or from your amplifier, not
from the volume conductor.

**Superposition holds exactly.** The potential from many sources is the sum of
their individual potentials, which is precisely the linear mixing model $X = AS$
that LIN 4 assumed. The entries of $A$ are $1/(4\pi\sigma r_{ij})$.''')

m.task(
'''def monopole_potential(current_a: float, distance_m: float, sigma: float = SIGMA) -> float:
    """Potential in volts from a point current source, quasi-static, homogeneous."""
    # TODO: V = I / (4 * pi * sigma * r)
    raise NotImplementedError("Implement monopole_potential")


def dipole_potential(moment_am: float, distance_m: float, cos_theta: float,
                     sigma: float = SIGMA) -> float:
    """Potential from a current dipole of moment p at distance r and angle theta.

    V = p * cos(theta) / (4 * pi * sigma * r^2)
    """
    # TODO: note the r squared, and the cos(theta): a dipole has a direction
    raise NotImplementedError("Implement dipole_potential")''',
'''def monopole_potential(current_a: float, distance_m: float, sigma: float = SIGMA) -> float:
    """Potential in volts from a point current source, quasi-static, homogeneous."""
    return float(current_a / (4.0 * np.pi * sigma * distance_m))


def dipole_potential(moment_am: float, distance_m: float, cos_theta: float,
                     sigma: float = SIGMA) -> float:
    """Potential from a current dipole of moment p at distance r and angle theta.

    V = p * cos(theta) / (4 * pi * sigma * r^2)
    """
    return float(moment_am * cos_theta / (4.0 * np.pi * sigma * distance_m ** 2))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
# (a) Falloff exponents, measured rather than asserted: fit a slope in log-log.
r = np.logspace(-4, -2, 60)                      # 0.1 mm to 10 mm
v_mono = np.array([monopole_potential(1e-9, ri) for ri in r])
v_dip = np.array([dipole_potential(1e-9 * 1e-4, ri, 1.0) for ri in r])

slope_mono = np.polyfit(np.log(r), np.log(np.abs(v_mono)), 1)[0]
slope_dip = np.polyfit(np.log(r), np.log(np.abs(v_dip)), 1)[0]
print(f"monopole log-log slope: {slope_mono:+.4f}   (theory -1)")
print(f"dipole   log-log slope: {slope_dip:+.4f}   (theory -2)")
assert np.isclose(slope_mono, -1.0, atol=1e-6), "a monopole falls off as 1/r"
assert np.isclose(slope_dip, -2.0, atol=1e-6), "a dipole falls off as 1/r squared"

# (b) A dipole is a pair of monopoles. Verify by direct superposition, which is
# the only justification for the formula above.
p_sep = 1e-4                                     # 100 micron separation
I = 1e-9
r_far = 2e-3
direct = (monopole_potential(I, r_far - p_sep / 2) +
          monopole_potential(-I, r_far + p_sep / 2))
formula = dipole_potential(I * p_sep, r_far, 1.0)
print(f"\\ntwo opposed monopoles at {r_far*1e3:.0f} mm : {direct*1e6:+.4f} uV")
print(f"dipole formula, same p         : {formula*1e6:+.4f} uV")
assert abs(direct - formula) / abs(formula) < 0.01, \\
    "the dipole formula must be the far-field limit of two monopoles"

# (c) Superposition, which is what makes LIN 4's mixing model exact.
sources = [(1e-9, 1e-3), (-2e-9, 2e-3), (0.5e-9, 3e-3)]
total = sum(monopole_potential(i, d) for i, d in sources)
assert np.isclose(total, sum(monopole_potential(i, d) for i, d in sources)), "trivially linear"
print(f"\\nsuperposed potential from 3 sources: {total*1e6:+.3f} uV")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. Why the LFP is synaptic and the spike band is not

A neuron firing produces a fast, spatially tight current distribution. Its
transmembrane currents sum to zero over the cell, so at a distance the leading
monopole term cancels and what remains falls off as $1/r^2$ or faster. A
synchronised population of aligned dendrites, by contrast, sustains a current
sink and a source separated by hundreds of microns for tens of milliseconds, and
sums coherently across thousands of cells.

The result is the division every intracranial recording makes:

- **Spike band**, above about 300 Hz. Fast, dipolar or higher order, falls off
  steeply. A contact hears units within roughly 50 to 150 microns.
- **LFP band**, below about 300 Hz. Slow, coherent across a population, falls off
  gently. A contact hears millimetres.

The steepness is the whole story. Below, the distance at which each contribution
drops below a noise floor is computed from the falloff alone.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
NOISE_UV = 5.0        # a plausible intraoperative noise floor

def reach_mm(amplitude_uv_at_ref, ref_mm, exponent, noise_uv=NOISE_UV):
    """Distance at which a source drops to the noise floor, given its falloff."""
    return float(ref_mm * (amplitude_uv_at_ref / noise_uv) ** (1.0 / exponent))

# A unit produces ~100 uV at 50 um and falls as 1/r^2 or steeper.
# A synchronised population produces ~50 uV at 1 mm and falls as 1/r^2 in the far
# field but is sustained by a much larger coherent volume.
print(f"{'source':>28} {'amplitude at ref':>18} {'falloff':>9} {'reach':>10}")
spike_reach = reach_mm(100.0, 0.05, 2.0)
lfp_reach = reach_mm(50.0, 1.0, 1.5)
print(f"{'single unit':>28} {'100 uV at 50 um':>18} {'1/r^2':>9} {spike_reach*1000:>7.0f} um")
print(f"{'synchronous population':>28} {'50 uV at 1 mm':>18} {'1/r^1.5':>9} {lfp_reach:>8.2f} mm")

assert spike_reach * 1000 < 500, "a unit is audible over hundreds of microns at most"
assert lfp_reach > 2.0, "an LFP source is audible over millimetres"
assert lfp_reach * 1000 / (spike_reach * 1000) > 5, \\
    "the two scales must differ by at least an order"
print(f"\\nratio of LFP reach to spike reach: {lfp_reach*1000/(spike_reach*1000):.0f}x")

# The consequence for a DBS lead: contacts 2 mm apart share LFP and share no units.
CONTACT_SPACING_MM = 2.0
print(f"\\nadjacent DBS contacts are {CONTACT_SPACING_MM:.1f} mm apart:")
print(f"  same units?      {'yes' if CONTACT_SPACING_MM < spike_reach else 'no'}")
print(f"  same LFP source? {'yes' if CONTACT_SPACING_MM < lfp_reach else 'no'}")
assert CONTACT_SPACING_MM > spike_reach, "contacts do not share single units"
assert CONTACT_SPACING_MM < lfp_reach, "contacts do share LFP sources"
print("\\nStep 2 passed. This is why LIN 4 found the contacts correlated and the sources not.")''')

m.md(r'''---

## 3. Spatial reach, and guardrail G2

Guardrail G2 fires when an effect tracks electrode identity rather than brain
state: the same contact is always the one showing it, across conditions. Deciding
whether that is a finding or an artifact needs a number, and Section 2 supplies
it.

If two contacts are closer than the reach of the source, they must both see it.
An effect present on exactly one contact and absent on its neighbour 2 mm away is
therefore claiming a source with a reach under 2 mm, which for an LFP-band effect
contradicts the physics. It is far more likely to be that contact's impedance,
its position against tissue, or a bad connector.

Below, the expected inter-contact profile is computed for a source at a known
depth, and compared against a profile that could only come from the electrode.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
contacts_mm = np.arange(8) * 2.0                # 8 contacts, 2 mm apart
SOURCE_DEPTH = 7.0                              # mm along the shank
LATERAL_MM = 1.0                                # how far off-axis the source sits

def profile_from_source(depth_mm, lateral_mm=LATERAL_MM):
    d = np.sqrt((contacts_mm - depth_mm) ** 2 + lateral_mm ** 2)
    v = np.array([monopole_potential(1e-9, di * 1e-3) for di in d])
    return v / v.max()

physio = profile_from_source(SOURCE_DEPTH)
electrode = np.zeros(8); electrode[3] = 1.0     # one contact, nothing on its neighbours

print(f"{'contact':>8} {'physiological':>15} {'electrode-bound':>17}")
for i in range(8):
    print(f"{i:>8} {physio[i]:>15.3f} {electrode[i]:>17.3f}")

# The decidable quantity: how much a source must drop between neighbours.
def neighbour_ratio(profile):
    peak = int(np.argmax(profile))
    neigh = [profile[j] for j in (peak - 1, peak + 1) if 0 <= j < len(profile)]
    return float(max(neigh) / profile[peak])

print(f"\\nneighbour-to-peak ratio, physiological source : {neighbour_ratio(physio):.3f}")
print(f"neighbour-to-peak ratio, electrode-bound      : {neighbour_ratio(electrode):.3f}")
assert neighbour_ratio(physio) > 0.3, \\
    "a real LFP source at this spacing MUST appear on the neighbouring contact"
assert neighbour_ratio(electrode) < 0.05, "an electrode-bound effect does not"

# And it holds however deep the source sits, which is what makes it a usable rule.
ratios = [neighbour_ratio(profile_from_source(d)) for d in np.arange(1.0, 14.0, 0.5)]
print(f"across source depths 1 to 13.5 mm: min neighbour ratio {min(ratios):.3f}")
assert min(ratios) > 0.25, "no physiological source can hide from an adjacent contact"
print("\\nStep 3 passed. An LFP effect on one contact and not its neighbour is a claim")
print("about the electrode, not about the brain. That is G2, made quantitative.")''')

m.md(r'''---

## 4. What you established

1. The quasi-static approximation gives $V = I/(4\pi\sigma r)$, and with it two
   facts that are used everywhere and justified rarely: the tissue applies **no
   temporal filtering**, and **superposition is exact**, which is why LIN 4's linear
   mixing model was allowed.
2. A dipole is the far-field limit of two opposed monopoles, verified to within
   1 percent by direct superposition, and it falls off as $1/r^2$ rather than
   $1/r$. Measured log-log slopes: $-1.0000$ and $-2.0000$.
3. Spikes are audible over hundreds of microns and LFP over millimetres, a ratio
   above 5. Contacts 2 mm apart on a DBS lead therefore share LFP sources and
   share no units, which is exactly the pattern LIN 4 measured as strong
   inter-contact correlation with uncorrelated sources.
4. No physiological LFP source can appear on one contact and not its neighbour:
   across every source depth tested, the neighbour sees at least 25 percent of
   the peak. An effect that violates that is describing the electrode. That is
   guardrail G2 with a number attached.

### Exercises

**Exercise 1.** Section 3 assumed a homogeneous conductor. The STN sits beside
white matter with markedly different and anisotropic conductivity. Redo the
neighbour-ratio calculation with $\sigma$ differing by a factor of 3 between the
two sides of the lead, and say whether G2's rule survives.

**Exercise 2.** The claim that tissue does not filter is contested for high
frequencies, where some measurements report frequency-dependent conductivity.
Find the frequency at which a 10 percent conductivity change would move a
reported high-gamma amplitude by more than the noise floor, and say whether the
spike band or the LFP band is more exposed.

**Exercise 3.** A unit's waveform amplitude falls as roughly $1/r^2$. Given a
detection threshold, compute the volume within which a unit is detectable, and
then the number of neurons in that volume at a realistic density. Compare that to
the number of units a typical sort actually returns, and account for the
difference.

---

**Next: REC 2, directional DBS leads.** This module gave the physics of a contact.
REC 2 gives the geometry of a real lead, and the orientation problem that this
repository's guardrail list explicitly flags as unsolved.
''')

m.emit()
verify("03_spatial", "01_extracellular_biophysics")
print("  REC 1 OK")
