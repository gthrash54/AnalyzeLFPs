import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("03_spatial", "04_neuropixels_and_drift")

m.md(r'''# Lesson REC 4: Neuropixels, Spatial Oversampling, and Drift {{VARIANT}}

**Acquisition · Recording Physics and Electrode Geometry · final lesson**

{{INSTRUCTIONS}}

REC 3 ended in the undersampled regime, where a clinical grid cannot see structure
finer than its spacing. This module is the opposite extreme. A Neuropixels 1.0
probe carries 960 sites at roughly 20 micron vertical pitch, of which 384 can be
recorded at once, and REC 1 established that a unit is audible over a couple of
hundred microns.

So each unit is seen by **many** sites. That changes everything: the array is
spatially oversampled, aliasing is not the problem, and the problems that replace
it are ones an undersampled array never has.

**What it assumes**

| From | What is used |
|---|---|
| REC 1 | Spike reach of roughly 200 microns, and $1/r^2$ or steeper falloff. |
| REC 3 | Spatial sampling and the spatial Nyquist argument. |
| LIN 1 | The dot product as a projection, and template matching. |
| SIG 1 | Band splits and sampling rates. |

**What it underwrites**

Spike Trains, which sorts spikes. This module supplies the reason sorting is a
spatial problem rather than a per-channel one.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

rng = np.random.default_rng(21)

# Neuropixels 1.0, from the probe specification.
SITE_PITCH_UM = 20.0        # vertical spacing between rows of sites
N_SITES_TOTAL = 960         # sites on the shank
N_CHANNELS = 384            # recordable simultaneously
AP_BAND_HZ = (300.0, 10000.0)
AP_RATE_HZ = 30000.0
LFP_BAND_HZ = (0.5, 500.0)
LFP_RATE_HZ = 2500.0
SPIKE_REACH_UM = 200.0      # from REC 1
print("Environment initialized for Lesson REC 4")''')

m.md(r'''---

## 1. Oversampling, and what it is worth

REC 3's question was whether the array samples finely enough. Here the answer is
plainly yes, so the useful question is the reverse: **how many sites see the same
unit**, and what that redundancy buys.

A site pitch of 20 microns against a spike reach of about 200 microns puts ten
rows of sites on either side of the unit. Rows, not sites: the sites are staggered
two to a row, so the count is $(2 \times 10 + 1) \times 2 = 42$, and dividing reach
by pitch to get 20 is the mistake the geometry invites. Those are not 42
independent measurements of different things; they are 42 noisy views of one
waveform, whose relative amplitudes encode where the neuron is.

That is why a Neuropixels spike sorter is a spatial algorithm. Its template is
not a waveform, it is a waveform **per channel**: a spatiotemporal object whose
amplitude profile across sites localises the cell. Sorting on one channel at a
time throws away the information that separates two cells with similar waveforms
at different depths.''')

m.task(
'''def sites_within_reach(reach_um: float = SPIKE_REACH_UM,
                       pitch_um: float = SITE_PITCH_UM,
                       sites_per_row: int = 2) -> int:
    """How many recording sites lie within `reach_um` of a unit.

    Neuropixels sites are arranged in rows of `sites_per_row` along the shank,
    one row every `pitch_um`. Count the rows whose distance along the shank is
    within reach, both directions, and multiply.
    """
    # TODO: rows within reach in one direction is floor(reach / pitch)
    # TODO: total rows is 2 * that + 1 (the row level with the unit)
    # TODO: multiply by sites_per_row
    raise NotImplementedError("Implement sites_within_reach")''',
'''def sites_within_reach(reach_um: float = SPIKE_REACH_UM,
                       pitch_um: float = SITE_PITCH_UM,
                       sites_per_row: int = 2) -> int:
    """How many recording sites lie within `reach_um` of a unit.

    Neuropixels sites are arranged in rows of `sites_per_row` along the shank,
    one row every `pitch_um`. Count the rows whose distance along the shank is
    within reach, both directions, and multiply.
    """
    rows_one_side = int(reach_um // pitch_um)
    return int((2 * rows_one_side + 1) * sites_per_row)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
n_seen = sites_within_reach()
print(f"site pitch {SITE_PITCH_UM:.0f} um, spike reach {SPIKE_REACH_UM:.0f} um")
print(f"sites within reach of one unit: {n_seen}")
assert n_seen > 10, "a unit must be visible on many sites; that is the whole design"

# Contrast with a DBS lead from REC 2, at 2 mm spacing.
dbs_seen = sites_within_reach(reach_um=SPIKE_REACH_UM, pitch_um=2000.0, sites_per_row=1)
print(f"same reach on a DBS lead at 2 mm spacing: {dbs_seen} contact")
assert dbs_seen == 1, "a DBS contact hears a unit alone or not at all"

# What the redundancy buys: averaging n independent noisy views improves SNR by
# sqrt(n), but only for the sites that actually see the unit.
def snr_gain(n_sites_used, n_sites_seeing=n_seen):
    """SNR gain from combining sites, with no gain from sites that see only noise."""
    useful = min(n_sites_used, n_sites_seeing)
    return float(useful / np.sqrt(n_sites_used))

print(f"\\n{'sites combined':>16} {'SNR gain':>10}")
for k in (1, 4, 20, 40, 100):
    print(f"{k:>16} {snr_gain(k):>10.2f}x")
best_k = max(range(1, 200), key=snr_gain)
print(f"\\nbest number of sites to combine: {best_k}, gain {snr_gain(best_k):.2f}x")
assert best_k == n_seen, "adding sites that see only noise makes the estimate worse"
assert snr_gain(100) < snr_gain(n_seen), "more channels is not automatically better"
print("\\nStep 1 passed. Redundancy helps only across the sites that see the unit.")
print("Combining all 384 would dilute the template with pure noise.")''')

m.md(r'''---

## 2. The band split, and why it is done in hardware

SIG 1 established that a recording must be sampled fast enough for its content and
that decimation removes bandwidth irreversibly. A Neuropixels probe resolves the
tension between spikes and LFP by splitting the signal into two streams at
acquisition:

| Stream | Band | Rate | Why |
|---|---|---|---|
| AP | 0.3 to 10 kHz | 30 kHz | Spikes last about 1 ms and need the bandwidth. |
| LFP | 0.5 to 500 Hz | 2.5 kHz | Slow, and 384 channels at 30 kHz is a lot of data. |

Doing this in hardware rather than in software is not merely an optimisation.
Recording 384 channels at 30 kHz with 10 bits is a substantial data rate, and the
LFP stream at 2.5 kHz costs a twelfth of that. But the split is also a commitment:
each stream is anti-alias filtered before decimation, so guardrail **G6** applies
per stream, and the usable bandwidth of the LFP stream is 0.4 times 2.5 kHz,
which is 1 kHz, comfortably above its 500 Hz band edge.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
def data_rate_mb_s(n_channels, rate_hz, bits=10):
    return float(n_channels * rate_hz * bits / 8 / 1e6)

ap_rate = data_rate_mb_s(N_CHANNELS, AP_RATE_HZ)
lfp_rate = data_rate_mb_s(N_CHANNELS, LFP_RATE_HZ)
print(f"AP stream  : {ap_rate:>7.2f} MB/s   ({N_CHANNELS} ch at {AP_RATE_HZ/1000:.0f} kHz)")
print(f"LFP stream : {lfp_rate:>7.2f} MB/s   ({N_CHANNELS} ch at {LFP_RATE_HZ/1000:.1f} kHz)")
print(f"ratio      : {ap_rate/lfp_rate:>7.1f}x")
assert np.isclose(ap_rate / lfp_rate, AP_RATE_HZ / LFP_RATE_HZ), \\
    "the rate ratio is exactly the sampling ratio"

# SIG 1's Nyquist check, applied to both streams.
for name, band, rate in (("AP", AP_BAND_HZ, AP_RATE_HZ), ("LFP", LFP_BAND_HZ, LFP_RATE_HZ)):
    nyq = rate / 2
    usable = 0.4 * rate            # guardrail G6, from SIG 1
    ok = band[1] <= usable
    print(f"\\n{name} stream: band tops at {band[1]:.0f} Hz")
    print(f"  Nyquist {nyq:.0f} Hz, usable after anti-aliasing {usable:.0f} Hz -> "
          f"{'OK' if ok else 'G6 REFUSES'}")
    assert ok, f"the {name} stream must not claim a band above its usable bandwidth"

# One hour of recording, which is the practical reason the split exists.
hours = 1.0
print(f"\\none hour of recording: AP {ap_rate*3600*hours/1000:.1f} GB, "
      f"LFP {lfp_rate*3600*hours/1000:.1f} GB")
assert ap_rate * 3600 / 1000 > 40, "the AP stream is tens of gigabytes per hour"
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Drift, which is the problem oversampling creates

A DBS contact and a unit either are or are not within 200 microns of each other,
and nothing changes that during a recording. A Neuropixels probe is a long thin
shank in soft moving tissue, and over an hour the brain moves relative to it by
tens of microns from pulsation, respiration, and slow relaxation.

Twenty microns is one site pitch. So a drift that would be invisible on a
widely spaced array moves a unit **onto different channels** here, and a sorter
that assumed a fixed spatial template will split one neuron into several units,
or merge two.

The oversampling that made localisation possible is exactly what makes drift
consequential. Below, the effect is measured directly: a unit's amplitude profile
across sites is computed before and after a drift, and the correlation between
them is the quantity a fixed-template sorter depends on.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
site_depths_um = np.arange(0, 800, SITE_PITCH_UM)      # 40 rows

def amplitude_profile(unit_depth_um, lateral_um=15.0):
    """Spike amplitude at each site, falling as 1/r^2 from REC 1."""
    d = np.sqrt((site_depths_um - unit_depth_um) ** 2 + lateral_um ** 2)
    return 1.0 / d ** 2

base = amplitude_profile(400.0)
print(f"{'drift':>8} {'profile correlation':>21} {'peak site moves by':>21}")
corrs = {}
for drift_um in (0.0, 5.0, 20.0, 50.0, 100.0):
    moved = amplitude_profile(400.0 + drift_um)
    corrs[drift_um] = float(np.corrcoef(base, moved)[0, 1])
    shift = int(np.argmax(moved)) - int(np.argmax(base))
    print(f"{drift_um:>6.0f}um {corrs[drift_um]:>21.4f} {shift:>18} sites")

assert corrs[0.0] > 0.999, "no drift, no change"
assert corrs[100.0] < 0.6, "100 microns of drift substantially changes the profile"
assert corrs[20.0] < corrs[5.0], "the degradation is monotonic in drift"

# The consequence: a fixed template's match score falls, and below a threshold the
# sorter stops recognising the unit as itself.
MATCH_THRESHOLD = 0.9
lost_at = min(d for d in corrs if corrs[d] < MATCH_THRESHOLD)
print(f"\\nat a match threshold of {MATCH_THRESHOLD}, a fixed template stops")
print(f"recognising this unit after {lost_at:.0f} um of drift, which is "
      f"{lost_at/SITE_PITCH_UM:.1f} site pitches.")
assert lost_at <= 50.0, "tens of microns is enough to break a fixed template"

# Why this is specific to dense arrays: repeat with DBS-scale spacing.
dbs_depths = np.arange(0, 16000, 2000.0)
def dbs_profile(unit_depth_um):
    d = np.sqrt((dbs_depths - unit_depth_um) ** 2 + 15.0 ** 2)
    return 1.0 / d ** 2
dbs_corr = float(np.corrcoef(dbs_profile(8000.0), dbs_profile(8000.0 + 100.0))[0, 1])
print(f"\\nsame 100 um drift on a 2 mm-spaced lead: profile correlation {dbs_corr:.4f}")
assert dbs_corr > corrs[100.0], "coarse spacing is insensitive to drift of this size"
print("\\nStep 3 passed. Dense spatial sampling is what makes drift matter, and it is")
print("why modern sorters estimate and correct drift before matching templates.")''')

m.md(r'''---

## 4. What you established, and what Recording Physics established

1. At 20 micron pitch and a 200 micron spike reach, a unit is seen on 42 sites
   against exactly 1 on a DBS lead. The 42 is worth deriving rather than
   estimating: reach over pitch gives ten rows either side, and the staggered
   two-per-row layout doubles that to 42. Combining those sites improves SNR, but
   only up to the number that actually see the unit: including all 384 is worse
   than including 42. Redundancy is bounded by physics, not by channel count.
2. The AP and LFP streams are split in hardware, at a data-rate ratio of exactly
   12, and each independently satisfies guardrail G6's usable-bandwidth check.
3. Drift of **one site pitch**, 20 microns, drops a unit's cross-site amplitude
   profile correlation from 1.000 to 0.596, and 100 microns takes it to $-0.03$.
   A fixed template stops recognising the unit after 20 microns. The identical
   100 micron drift on a 2 mm-spaced lead leaves the correlation at 1.0000.
   **Dense sampling is what makes drift a problem**, which is the price of the
   localisation it buys.

**Recording Physics is complete.** REC 1 derived the mixing matrix LIN 4 assumed and gave the
spatial scales. REC 2 showed that a directional lead's anatomical claims rest on a
rotation nobody measured. REC 3 showed that a clinical grid aliases in space exactly
as SIG 1's recording aliased in time. REC 4 showed the opposite regime, where space is
oversampled and the difficulty moves to keeping track of a probe that will not
hold still.

### Exercises

**Exercise 1.** Section 1 found an optimal number of sites to combine. Redo it
with the falloff exponent from REC 1 changed from 2 to 3, and say how sensitive the
answer is to a quantity REC 1 could only estimate.

**Exercise 2.** Section 3 modelled drift as a rigid translation. Real drift is
non-rigid: different depths move by different amounts. Construct a non-rigid
drift and show that a single global correction cannot fix it.

**Exercise 3.** REC 3's spatial Nyquist argument says a 20 micron pitch resolves
spatial frequencies up to 25 cycles per mm. Using REC 1's falloff, compute the
spatial frequency content of a single unit's amplitude profile and decide whether
Neuropixels is oversampled, critically sampled, or still undersampled for
localising one cell.
''')

m.emit()
verify("03_spatial", "04_neuropixels_and_drift")
print("  REC 4 OK")
