import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("07_guardrails", "05_the_thirteen_guardrails")

m.md(r'''# Module G3: The Thirteen Scientific Guardrails {{VARIANT}}

**Guardrails. Final module of the curriculum.**

{{INSTRUCTIONS}}

Every module in this curriculum has been underwriting a guardrail. This one
collects them and states, for each, the module that supplies the number it
thresholds on.

That is the point of the whole sequence. A guardrail is not a policy someone
chose. It is arithmetic somebody did once, written down so it does not have to be
redone under time pressure with a patient in theatre.

**What it assumes**

All of it. This module is the index.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import numpy as np

# The guardrails, as implemented in configs/guardrails.yaml. Restated here so the
# notebook runs standalone; tests/unit/test_curriculum.py asserts that this table
# still matches the config, so it cannot drift.
GUARDRAILS = {
    "G1": dict(key="G1_shared_reference_common_mode", severity="block",
               name="Monopolar common-mode", derived_in="LIN 4, CON 1, REC 1",
               number="A shared reference raises mean inter-contact correlation from 0.47 to "
                      "0.99 while collapsing its spread from 0.31 to 0.007. Volume conduction "
                      "alone gives PLV 1.0 with no interaction."),
    "G2": dict(key="G2_effect_tracks_electrode_not_state", severity="block",
               name="Effect that tracks electrode identity, not brain state",
               derived_in="REC 1",
               number="No physiological LFP source can hide from an adjacent contact: the "
                      "minimum neighbour-to-peak ratio across all source depths is 0.447, "
                      "against 0.000 for an electrode-bound effect."),
    "G3": dict(key="G3_ratio_before_average", severity="block",
               name="Jensen's inequality on ratios", derived_in="SIG 4",
               number="A periodogram bin is chi-square with 2 degrees of freedom, whose "
                      "standard deviation equals its mean: relative sd measured at 1.00 across "
                      "a 64x increase in data. That distribution is strongly skewed, so the "
                      "mean of ratios and the ratio of means are different numbers."),
    "G4": dict(key="G4_threshold_across_conditions", severity="warn",
               name="Threshold set across conditions when testing structure",
               derived_in="SPK 2",
               number="A non-robust threshold moves +34.4 uV between rest and task against "
                      "+7.5 uV for a robust one, costing 36.6 percent recall in the busier "
                      "condition for units near threshold."),
    "G5": dict(key="G5_window_longer_than_phenomenon", severity="warn",
               name="Time-frequency window too long for the effect", derived_in="SIG 5, SIG 3",
               number="SIG 5 measured the cost directly: a 100 ms burst read with a 12-cycle "
                      "wavelet at 20 Hz is reported as 166 ms. The config is more permissive "
                      "than that measurement, warning only above "
                      "max_window_to_event_ratio = 5.0, so a plan can satisfy the guardrail "
                      "and still overstate a duration."),
    "G6": dict(key="G6_decimation_removes_claimed_band", severity="block",
               name="Decimation silently removing the band being claimed",
               derived_in="SIG 1, PRE 1",
               number="Usable bandwidth after decimation is 0.4 x the new rate, not half of "
                      "it. Measured: content at 400 Hz survives at 0.99, at 450 Hz at 0.11."),
    "G7": dict(key="G7_emg_contamination_in_high_band", severity="warn",
               name="Muscle contamination in the speech band",
               derived_in="GRL 3",
               number="EMG, over emg_band_hz = 100 to 1000 Hz, escalating to block above "
                      "100 Hz for overt speech. GRL 3 measured it: muscle at ordinary amplitude "
                      "puts 11.2 uV into beta and 2.2 uV into high gamma, and gated EMG alone, "
                      "with no cortex present, produced a 1.65x speech-locked high-gamma rise. "
                      "The overt-only escalation is justified by the inner-speech control, "
                      "where muscle gives 0.99x and cortex still gives 1.73x."),
    "G8": dict(key="G8_db_without_z", severity="note",
               name="Dynamic range mistaken for effect size", derived_in="SIG 4, CON 4, SPK 4",
               number="The periodogram's relative standard deviation stays at 1.0 across a "
                      "64x increase in data. A 1.42x beta increase from a slope rotation is "
                      "indistinguishable from a 1.46x increase from a real oscillation."),
    "G9": dict(key="G9_nonstationarity_exceeds_effect", severity="warn",
               name="Non-stationarity larger than the effect",
               derived_in="GRL 4",
               number="Fires when a baseline excursion exceeds the effect, at "
                      "excursion_to_effect_ratio = 1.0. GRL 4 measured it: at a ratio of 3.3 every "
                      "choice of baseline window reported a decrease where the truth was an "
                      "increase. It also found the threshold permissive, with the estimate "
                      "still usable at ratio 0.5 and collapsing near 0.73, so a quiet G9 is "
                      "not evidence that a comparison is clean."),
    "G10": dict(key="G10_window_provenance", severity="warn",
                name="Window provenance", derived_in="not a measurement",
                number="Flags any window whose derived_from is 'assumed', or whose status is "
                       "draft or under_revision. A metadata rule about where a number came "
                       "from, not arithmetic about what it equals."),
    "G11": dict(key="G11_control_condition_missing", severity="warn",
                name="A claim is analyzed without the control condition it needs",
                derived_in="LIN 6, CON 2, SPK 4",
                number="With a reference six times the physiology, PCA on one condition "
                       "returns the amplifier at 0.4 degrees while GED against a control "
                       "returns the real source at 5.3 degrees."),
    "G12": dict(key="G12_baseline_on_smoothed_data", severity="block",
                name="Baseline statistics computed on smoothed data",
                derived_in="POP 1, SIG 2",
                number="Smoothing destroys independent samples: a 25-bin kernel took 600 time "
                       "points to 7 effective ones, inflating measured correlation from 0.028 "
                       "to 0.234 with no coupling added. A baseline distribution estimated on "
                       "such data is narrower than the truth, so every later z-score inflates."),
    "G13": dict(key="G13_path_and_filename_policy", severity="block",
                name="Path and filename policy", derived_in="not a measurement",
                number="A privacy and provenance rule. Results refer to recordings by manifest "
                       "key because a path is machine-specific."),
}
print(f"{len(GUARDRAILS)} guardrails loaded")''')

m.md(r'''---

## 1. The table

Read the `derived_in` column as the answer to "why is this number what it is".
Every one of them was measured in a module of this curriculum, on synthetic data
where the truth was known, rather than asserted.''')

m.code('''# --- TEST CELL FOR STEP 1 ---
print(f"{'id':>4} {'severity':>9} {'derived in':>14}  name")
print("-" * 96)
for gid, g in GUARDRAILS.items():
    print(f"{gid:>4} {g['severity']:>9} {g['derived_in']:>14}  {g['name']}")

assert len(GUARDRAILS) == 13, "there are thirteen"
severities = {g["severity"] for g in GUARDRAILS.values()}
assert severities == {"block", "warn", "note"}, f"unexpected severities: {severities}"

blocks = [k for k, g in GUARDRAILS.items() if g["severity"] == "block"]
print(f"\\nblocking: {', '.join(blocks)} ({len(blocks)} of 13)")
assert len(blocks) == 6, "six guardrails block a run outright"

# Which of them does this curriculum actually derive a number for? Naming the
# gaps honestly is more useful than claiming coverage.
derived = [k for k, g in GUARDRAILS.items()
           if not g["derived_in"].startswith("not ")]
provenance = [k for k, g in GUARDRAILS.items() if g["derived_in"] == "not a measurement"]
owed = [k for k, g in GUARDRAILS.items() if g["derived_in"] == "not derived here"]
print(f"\\nderived by a module here : {', '.join(derived)}  ({len(derived)} of 13)")
print(f"provenance, not arithmetic: {', '.join(provenance)}")
print(f"arithmetic, but owed a module: {', '.join(owed) if owed else 'none'}")
assert len(derived) == 11, "eleven of the thirteen have their number derived in this curriculum"
assert set(provenance) == {"G10", "G13"}, "the other two are provenance rules, not arithmetic"
assert not owed, "no arithmetic guardrail is left without a module that measured its number"
print("\\nEvery guardrail that thresholds on a quantity now has a module that measured")
print("that quantity. The two remaining are provenance rules, which have no number to")
print("measure: they check where a value came from, not what it equals.")
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. What each one is actually protecting against

The numbers, stated. This is the section to come back to.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
import textwrap
for gid, g in GUARDRAILS.items():
    print(f"\\n{gid} [{g['severity']}] {g['name']}")
    print(f"   derived in: {g['derived_in']}")
    for line in textwrap.wrap(g["number"], 74):
        print(f"   {line}")

# Every entry must carry a number or an explicit statement that it does not.
for gid, g in GUARDRAILS.items():
    assert len(g["number"]) > 40, f"{gid} must state what it thresholds on"
    has_digit = any(ch.isdigit() for ch in g["number"])
    is_provenance = g["derived_in"] == "not a measurement"
    assert has_digit or is_provenance, f"{gid} must cite a quantity or be a provenance rule"
print("\\n\\nStep 2 passed. Eleven of thirteen have their number derived here and the")
print("other two are provenance rules with no number to derive. G7's EMG threshold comes")
print("from GRL 3 and G9's drift ratio from GRL 4, the two modules written last precisely")
print("because this table showed they were missing.")''')

m.md(r'''---

## 3. The pattern

Reading the table end to end, the same shape appears repeatedly, and it is worth
naming because it is what the curriculum was really about.

**A measure has a non-physiological process that produces its signature at full
strength.** Volume conduction produces the maximum phase-locking value. A sharp
waveform produces cross-frequency coupling that survives a shuffled null. A slope
rotation produces a band-power increase indistinguishable from an oscillation. A
short epoch produces low dimensionality. A stimulation artifact produces beta.

In every case the confound is **common**, the signature is **identical**, and the
diagnostic is **cheap**. That combination is why the rules are worth writing down:
not because the mistake is subtle, but because it is easy to make, easy to check,
and impossible to detect afterwards from the result alone.

The second recurring shape is that **the analysis parameter is the finding**.
Smoothing kernel decides dimensionality. Guard band decides high gamma. Segment
length decides spectral variance. Number of factors decides whether factor
analysis works at all. Assumed measurement noise decides a decoder's latency. In
each case a number that feels like a formatting choice determines the result, and
it is usually not reported.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
# The two patterns, as a checklist that can be applied to any new analysis.
CONFOUND_PAIRS = {
    "phase locking":        ("volume conduction", "CON 1"),
    "cross-frequency coupling": ("non-sinusoidal waveform", "CON 3"),
    "band power":           ("aperiodic slope rotation", "CON 4"),
    "dimensionality":       ("short epoch or heavy smoothing", "POP 1"),
    "beta biomarker":       ("folded stimulation harmonics", "G1"),
    "directed connectivity": ("unobserved common driver", "CON 2"),
    "spike-field coherence": ("spike count", "SPK 4"),
    "cluster quality":      ("contaminant with complementary tuning", "SPK 3"),
}
PARAMETER_DECIDES = {
    "smoothing kernel":     ("reported dimensionality", "POP 1"),
    "blanking guard band":  ("high-gamma power", "G1"),
    "Welch segment length": ("spectral variance and resolution", "SIG 4"),
    "number of factors":    ("whether factor analysis beats PCA", "POP 2"),
    "assumed measurement noise": ("decoder latency and accuracy", "POP 3"),
    "wavelet cycle count":  ("reported burst duration", "SIG 5"),
    "shrinkage alpha":      ("recovered spatial filter", "LIN 6"),
}

print("MEASURE -> the non-physiological process that mimics it\\n")
for measure, (confound, mod) in CONFOUND_PAIRS.items():
    print(f"  {measure:>26}  <-  {confound:<42} [{mod}]")

print("\\n\\nPARAMETER -> what it silently decides\\n")
for param, (decides, mod) in PARAMETER_DECIDES.items():
    print(f"  {param:>26}  ->  {decides:<42} [{mod}]")

assert len(CONFOUND_PAIRS) >= 8, "the pattern recurs across at least eight measures"
assert len(PARAMETER_DECIDES) >= 7, "and at least seven parameters decide a result"
all_mods = {m for _, m in CONFOUND_PAIRS.values()} | {m for _, m in PARAMETER_DECIDES.values()}
print(f"\\n\\nmodules involved: {len(all_mods)} of the curriculum's 46")
assert len(all_mods) >= 10, "the pattern is not confined to one track"
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. Applying them to a plan, before running anything

The gate in `qc/gate.py` runs against a completed analysis. The cheaper moment to
catch a problem is before it starts, when the plan is still a set of numbers.

Every guardrail in the table thresholds on a quantity that is known in advance:
the montage, the decimation target, the requested band, the analysis window, the
condition set. So a plan can be screened against most of them without touching
data, and the arithmetic is all from earlier modules.

Implement that screen.''')

m.task(
'''def screen_plan(plan: dict) -> list:
    """Which guardrails would refuse this analysis plan, and why.

    `plan` may contain:
        montage           str, e.g. "monopolar" or "bipolar_vertical"
        sfreq_hz          float, the acquisition rate
        target_hz         float, the decimation target
        band_hz           (lo, hi), the requested band
        window_s          float, the analysis window
        effect_duration_s float, the shortest effect the claim is about
        conditions        list of condition names present
        reports_db        bool, whether the result is reported in dB
        reports_z         bool, whether a z-score accompanies it

    Return a list of (guardrail_id, reason) for every rule that would fire.
    Use only arithmetic from this curriculum:
      G6  usable bandwidth after decimation is 0.4 * achieved rate, and the
          achieved rate is sfreq / floor(sfreq / target)          [SIG 1, PRE 1]
      G5  a window must be shorter than the effect it measures     [SIG 5]
      G1  monopolar on a shared reference                          [LIN 4, CON 1]
      G8  a dB figure without a z-score                            [SIG 4, CON 4]
      G11 a condition analysed without its control                 [LIN 6, CON 2]
    """
    # TODO: start with an empty list of findings
    # TODO: G6  factor = floor(sfreq/target); achieved = sfreq/factor;
    #           usable = 0.4*achieved; fire if max(band) > usable
    # TODO: G5  fire if window_s > effect_duration_s
    # TODO: G1  fire if montage == "monopolar"
    # TODO: G8  fire if reports_db and not reports_z
    # TODO: G11 fire if "overt" or "inner" is present without "metro" or "move"
    # TODO: return the findings
    raise NotImplementedError("Implement screen_plan")''',
'''def screen_plan(plan: dict) -> list:
    """Which guardrails would refuse this analysis plan, and why.

    `plan` may contain:
        montage           str, e.g. "monopolar" or "bipolar_vertical"
        sfreq_hz          float, the acquisition rate
        target_hz         float, the decimation target
        band_hz           (lo, hi), the requested band
        window_s          float, the analysis window
        effect_duration_s float, the shortest effect the claim is about
        conditions        list of condition names present
        reports_db        bool, whether the result is reported in dB
        reports_z         bool, whether a z-score accompanies it

    Return a list of (guardrail_id, reason) for every rule that would fire.
    Use only arithmetic from this curriculum:
      G6  usable bandwidth after decimation is 0.4 * achieved rate, and the
          achieved rate is sfreq / floor(sfreq / target)          [SIG 1, PRE 1]
      G5  a window must be shorter than the effect it measures     [SIG 5]
      G1  monopolar on a shared reference                          [LIN 4, CON 1]
      G8  a dB figure without a z-score                            [SIG 4, CON 4]
      G11 a condition analysed without its control                 [LIN 6, CON 2]
    """
    findings = []

    sfreq = plan.get("sfreq_hz")
    target = plan.get("target_hz")
    band = plan.get("band_hz")
    if sfreq and target and band:
        factor = max(1, int(sfreq // target))
        achieved = sfreq / factor
        usable = 0.4 * achieved
        if max(band) > usable:
            findings.append(("G6", f"band reaches {max(band):.0f} Hz but decimating to "
                                   f"{achieved:.1f} Hz leaves {usable:.1f} Hz usable"))

    window = plan.get("window_s")
    effect = plan.get("effect_duration_s")
    if window and effect and window > effect:
        findings.append(("G5", f"window {window*1000:.0f} ms exceeds the "
                               f"{effect*1000:.0f} ms effect it measures"))

    if plan.get("montage") == "monopolar":
        findings.append(("G1", "monopolar on a shared reference cannot separate "
                               "reference motion from brain synchronisation"))

    if plan.get("reports_db") and not plan.get("reports_z"):
        findings.append(("G8", "a dB figure without a z-score reports dynamic range"))

    conditions = set(plan.get("conditions", []))
    if conditions & {"overt", "inner"} and not conditions & {"metro", "move"}:
        findings.append(("G11", "speech is a motor act; a movement-only control is "
                                "needed to rule out the motor explanation"))

    return findings''')

m.code('''# --- TEST CELL FOR STEP 1 ---
# A plan that should pass everything.
clean_plan = dict(montage="bipolar_vertical", sfreq_hz=24000.0, target_hz=1000.0,
                  band_hz=(13.0, 30.0), window_s=0.05, effect_duration_s=0.2,
                  conditions=["overt", "move", "rest"], reports_db=True, reports_z=True)
assert screen_plan(clean_plan) == [], f"a clean plan must pass: {screen_plan(clean_plan)}"
print("clean plan: no findings")

# A plan that trips every rule this screen knows about.
bad_plan = dict(montage="monopolar", sfreq_hz=24000.0, target_hz=250.0,
                band_hz=(70.0, 150.0), window_s=0.4, effect_duration_s=0.1,
                conditions=["overt", "rest"], reports_db=True, reports_z=False)
found = screen_plan(bad_plan)
print(f"\\ndeliberately bad plan, {len(found)} findings:")
for gid, why in found:
    print(f"  {gid}: {why}")

ids = {gid for gid, _ in found}
assert ids == {"G1", "G5", "G6", "G8", "G11"}, f"expected all five, got {ids}"

# Each rule must fire on its own trigger and not on anything else.
print(f"\\n{'changed from the clean plan':>42} {'fires':>22}")
for label, override in (
        ("montage -> monopolar", dict(montage="monopolar")),
        ("decimate to 250 Hz with a 70-150 band", dict(target_hz=250.0, band_hz=(70.0, 150.0))),
        ("window 400 ms for a 100 ms effect", dict(window_s=0.4, effect_duration_s=0.1)),
        ("report dB with no z-score", dict(reports_z=False)),
        ("drop the movement control", dict(conditions=["overt", "rest"])),
):
    probe = dict(clean_plan)
    probe.update(override)
    fired = {gid for gid, _ in screen_plan(probe)}
    print(f"{label:>42} {','.join(sorted(fired)) or 'nothing':>22}")
    assert len(fired) == 1, f"{label} should trip exactly one rule, tripped {fired}"

# And the G6 arithmetic must match SIG 1 and PRE 1 exactly.
beta_at_250 = dict(clean_plan); beta_at_250.update(target_hz=250.0)
assert screen_plan(beta_at_250) == [], "beta survives 250 Hz: 30 Hz is under 100 Hz usable"
beta_at_60 = dict(clean_plan); beta_at_60.update(target_hz=60.0)
assert any(g == "G6" for g, _ in screen_plan(beta_at_60)), \\
    "beta does not survive 60 Hz: 30 Hz is over 24 Hz usable"
print("\\nStep 1 passed. Most of the table can be screened before any data is touched.")''')

m.md(r'''---

## 5. What to do with this

Three habits follow from the table, and none of them is expensive.

**Name the confound before running the analysis.** For any measure you are about
to compute, the table's first column tells you what produces its signature for
free. Decide in advance what you would do if you saw it.

**Report the parameters that decide the result.** Smoothing kernel, guard band,
segment length, cycle count, shrinkage, assumed noise. If a number in the second
column is not in your methods section, your result is not reproducible in the
sense that matters.

**Prefer the diagnostic to the significance test.** CON 3's spurious coupling was
overwhelmingly significant against a shuffled null and disappeared when the
amplitude band was narrowed to one harmonic. CON 4's slope change was a real,
significant band-power increase. Significance answers "is this different from
noise". The diagnostics answer "is this what I think it is", and that is the
question guardrails are for.

---

### Where the numbers live in this repository

- `configs/guardrails.yaml`, the thresholds and severities
- `docs/guardrails.md`, the prose for each rule
- `src/dbsspeech/guardrails/checks.py`, the enforcement
- `src/dbsspeech/qc/gate.py`, the gate every run passes

The gate is enforced in the package rather than in the interface, so a rule
cannot be avoided by using a different front end. That is a deliberate design
decision and it is the reason this curriculum exists: the rules are only worth
enforcing if somebody has checked the arithmetic behind them, and now somebody
has.

### Exercises

**Exercise 1.** `docs/guardrails.md` lists guardrails not yet implemented,
including a check that segment orientation is known before any anatomical
direction claim. REC 2 measured the worst-case error at 60 degrees. Write the
threshold and the refusal message that check should use.

**Exercise 2.** Take a recent paper in this field and score it against the two
tables in Section 3. How many of the confounds could its methods section rule
out, and how many of the deciding parameters does it report?

**Exercise 3.** Add a fourteenth guardrail. State the measure, the confound, the
diagnostic, the threshold, the severity, and the module of this curriculum that
would derive the number. If no module derives it, write that module.
''')

m.emit()
verify("07_guardrails", "05_the_thirteen_guardrails")
print("  GRL 5 OK")
