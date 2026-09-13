import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("07_guardrails", "03_emg_contamination_in_speech")

m.md(r'''# Lesson GRL 3: Muscle Contamination in the Speech Band {{VARIANT}}

**Scientific Integrity · Closed-Loop Neuromodulation and Scientific Guardrails**

{{INSTRUCTIONS}}

This module exists because the curriculum was caught out. GRL 5 collects the
thirteen guardrails and names, for each, the module that derived the number it
thresholds on. Guardrail **G7** had no such module. Its parameters were quoted
from `configs/guardrails.yaml` and nothing here had checked them.

G7 is muscle contamination. Its configured band is 100 to 1000 Hz, it requires a
bipolar montage, and it escalates from a warning to a block above 100 Hz **for
overt speech only**. Every one of those three choices is a claim, and this module
tests them.

**What it assumes**

| From | What is used |
|---|---|
| SIG 3, SIG 4 | Welch, and that a band is an interval on a frequency axis. |
| SPK 1 | The method: measure a contaminant's share of a band against the physiology, rather than arguing about it. |
| LIN 4, CON 1 | That a far-field source arrives on every contact at once, and what a zero-sum montage does to it. |
| REC 1 | That a local source falls off steeply and a distant one does not. |

**What it underwrites**

Guardrail **G7**, all three of its settings.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, welch

rng = np.random.default_rng(19)
FS = 1000.0

# From configs/guardrails.yaml, G7_emg_contamination_in_high_band. Restated so
# this notebook runs standalone; tests/unit/test_curriculum.py asserts they match.
EMG_BAND_HZ = (100.0, 1000.0)
ESCALATE_ABOVE_HZ = 100.0
ESCALATE_ONLY_FOR = ["overt"]
REQUIRE_BIPOLAR = True

# From configs/bands.yaml.
BANDS = {"beta 13-30": (13.0, 30.0), "low gamma 30-60": (30.0, 60.0),
         "high gamma 70-150": (70.0, 150.0)}

def bandpass(x, lo, hi, order=4):
    return filtfilt(*butter(order, [lo, hi], btype='band', fs=FS), x)


def aperiodic_lfp(n_samples, amplitude_uv, exponent=1.5, seed=0, fs=FS):
    """A 1/f background, as CON 4 established a real LFP spectrum is.

    This matters here: a flat background would give every band the same power and
    make EMG's share look identical everywhere, which is not what happens.
    """
    gen = np.random.default_rng(seed)
    white = gen.standard_normal(n_samples)
    freqs = np.fft.rfftfreq(n_samples, 1.0 / fs)
    freqs[0] = 1.0
    pink = np.fft.irfft(np.fft.rfft(white) / freqs ** (exponent / 2.0), n=n_samples)
    return amplitude_uv * pink / np.std(pink)

print("Environment initialized for Lesson GRL 3")''')

m.md(r'''---

## 1. Where muscle energy lands

Surface electromyogram from the face, jaw and neck is broadband. Its power rises
from about 20 Hz, peaks somewhere near 100 Hz, and extends past 400 Hz. It is not
an oscillation and it has no peak to fit; it is the summed firing of many motor
units, so its spectrum is smooth and wide.

Compare that to the bands an intracranial speech study reports. Beta sits below
it. High gamma, 70 to 150 Hz, sits **inside** it. So the question is not whether
EMG overlaps high gamma, which it plainly does, but how much of a high-gamma
measurement it accounts for at realistic amplitudes.

That is SPK 1's question in a different costume, and SPK 1's answer there was that the
famous contaminant turned out to be negligible. Ask it again rather than assume
the answer transfers.''')

m.task(
'''def emg_signal(n_samples: int, amplitude_uv: float, gate=None, seed: int = 0,
               fs: float = FS) -> np.ndarray:
    """Surface EMG: broadband 20 to 400 Hz, optionally gated by an envelope.

    `gate` is a per-sample envelope in [0, 1] saying when the muscle is active.
    Production equivalent: none. EMG is measured, not modelled, and the honest
    move in a real study is to record it on a separate channel.
    """
    # TODO: draw white noise and bandpass it to 20-400 Hz
    # TODO: normalise to unit standard deviation, then scale by amplitude_uv
    # TODO: multiply by the gate when one is given
    raise NotImplementedError("Implement emg_signal")


def band_power(x: np.ndarray, band, fs: float = FS) -> float:
    """Mean Welch power in a band."""
    # TODO: welch with nperseg=4096, then mean over the band
    raise NotImplementedError("Implement band_power")''',
'''def emg_signal(n_samples: int, amplitude_uv: float, gate=None, seed: int = 0,
               fs: float = FS) -> np.ndarray:
    """Surface EMG: broadband 20 to 400 Hz, optionally gated by an envelope.

    `gate` is a per-sample envelope in [0, 1] saying when the muscle is active.
    Production equivalent: none. EMG is measured, not modelled, and the honest
    move in a real study is to record it on a separate channel.
    """
    gen = np.random.default_rng(seed)
    raw = bandpass(gen.standard_normal(n_samples), 20.0, 400.0)
    raw = amplitude_uv * raw / np.std(raw)
    return raw if gate is None else raw * gate


def band_power(x: np.ndarray, band, fs: float = FS) -> float:
    """Mean Welch power in a band."""
    f, p = welch(x, fs, nperseg=4096)
    sel = (f >= band[0]) & (f < band[1])
    return float(np.mean(p[sel]))''')

m.code('''# --- TEST CELL FOR STEP 1 ---
T = 120000
lfp = aperiodic_lfp(T, 20.0, seed=11)                 # a 20 uV 1/f background, as in CON 4

# A 1/f background puts almost all its power at low frequencies, so its power
# PER HERTZ at 100 Hz is small. A broadband contaminant does not fall off, so its
# share is not one number: it depends on the band and on the muscle's amplitude.
print(f"{'EMG amplitude':>14} " + " ".join(f"{n.split()[0]:>11}" for n in BANDS) + f"{'150-300':>11}")
shares = {}
for amp in (0.5, 1.0, 3.0, 10.0, 30.0):
    e = emg_signal(T, amp, seed=1)
    row = {n: band_power(e, b) / band_power(lfp, b) for n, b in BANDS.items()}
    row["150-300"] = band_power(e, (150.0, 300.0)) / band_power(lfp, (150.0, 300.0))
    shares[amp] = row
    print(f"{amp:>11.1f} uV " + " ".join(f"{row[n]:>10.0%}" for n in list(BANDS) + ["150-300"]))

# The share rises steeply with frequency, at every amplitude, because the
# background falls and the muscle does not.
for amp in shares:
    r = shares[amp]
    assert r["beta 13-30"] < r["low gamma 30-60"] < r["high gamma 70-150"] < r["150-300"], \\
        f"the share must rise with frequency at {amp} uV"

# Below about a microvolt the muscle is a rounding error in beta and already
# comparable to the physiology in high gamma. That asymmetry is the finding.
assert shares[1.0]["beta 13-30"] < 0.05, "beta is essentially spared at 1 uV"
assert shares[1.0]["high gamma 70-150"] > 0.15, "high gamma is not"

# The amplitude at which muscle equals the physiology in each band.
print(f"\\n{'band':>20} {'EMG amplitude that doubles the band':>36}")
for name, band in list(BANDS.items()) + [("150-300", (150.0, 300.0))]:
    unit = band_power(emg_signal(T, 1.0, seed=1), band)
    needed = np.sqrt(band_power(lfp, band) / unit)
    print(f"{name:>20} {needed:>32.1f} uV")
    if name == "beta 13-30":
        beta_needed = needed
    if name == "high gamma 70-150":
        hg_needed = needed
assert hg_needed < 0.25 * beta_needed, \\
    "it takes far less muscle to matter in high gamma than in beta"
print("\\nStep 1 passed. Unlike SPK 1's spike bleed, which needed a background twelve")
print("times below normal before it mattered, muscle reaches the physiology in high")
print("gamma at amplitudes that are entirely ordinary.")''')

m.md(r'''---

## 2. Time-locking is what makes it dangerous

A constant contaminant raises a band in every condition and cancels in a
contrast. Muscle activity does not do that. The face and jaw are active
**during speech and not before it**, so the contamination is time-locked to
exactly the event whose response is being measured.

That gives it the shape of a finding: high-gamma power rises at speech onset,
returns to baseline after, and is absent in the pre-trial window. Every property
a cortical speech response is expected to have.

Below, a recording contains **no cortical response at all**. Only muscle.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
TRIAL_S, N_TRIALS = 2.0, 60
SPEECH_ON, SPEECH_DUR = 0.5, 0.6

gate = np.zeros(T)
onsets = []
for k in range(N_TRIALS):
    start = int((k * TRIAL_S + SPEECH_ON) * FS)
    stop = start + int(SPEECH_DUR * FS)
    if stop < T:
        gate[start:stop] = 1.0
        onsets.append(start)
gate = filtfilt(*butter(2, 8.0, btype='low', fs=FS), gate)   # muscles ramp, not step

EMG_UV = 3.0                                     # ordinary, from Section 1
recording = lfp + emg_signal(T, EMG_UV, gate=gate, seed=2)

def band_envelope(x, band):
    from scipy.signal import hilbert
    return np.abs(hilbert(bandpass(x, *band)))

hg = band_envelope(recording, BANDS["high gamma 70-150"])
pre = np.mean([hg[o - int(0.4 * FS):o].mean() for o in onsets if o > int(0.4 * FS)])
during = np.mean([hg[o:o + int(SPEECH_DUR * FS)].mean() for o in onsets])
print(f"high-gamma envelope before speech : {pre:.3f}")
print(f"high-gamma envelope during speech : {during:.3f}")
print(f"increase                          : {during/pre:.2f}x")
assert during / pre > 1.3, "muscle alone produces a clear speech-locked high-gamma rise"

# It has the time course of a response, because the muscle has the time course of
# the behaviour. Check the shape, not just the magnitude.
window = np.arange(-int(0.5 * FS), int(1.2 * FS))
avg = np.mean([hg[o + window] for o in onsets if o + window[0] >= 0 and o + window[-1] < T], axis=0)
peak_ms = 1000.0 * window[int(np.argmax(avg))] / FS
print(f"\\npeak of the trial-averaged envelope: {peak_ms:+.0f} ms relative to speech onset")
assert 0 < peak_ms < 1000 * SPEECH_DUR, "it peaks during speech, as a real response would"
assert avg[window < -int(0.1 * FS)].mean() < avg[(window > 0) & (window < int(SPEECH_DUR * FS))].mean(), \\
    "and it is flat before onset"
print("\\nStep 2 passed. No cortex was involved. A trial-averaged high-gamma response,")
print("flat before onset, peaking during speech, is what a jaw muscle looks like.")''')

m.md(r'''---

## 3. Why G7 requires a bipolar montage

REC 1 established that a source's falloff depends on its distance. Muscle sits
centimetres away from an intracranial contact, so on the scale of a lead's
contact spacing it is a **far field**: it arrives on every contact at very nearly
the same amplitude. Cortical high gamma is local and does not.

LIN 4 and CON 1 established what a zero-sum montage does to something arriving equally
on every contact: it removes it. So a bipolar derivation should reject muscle
strongly while preserving a local cortical source, and the ratio between those
two is the whole justification for `require_bipolar`.

Measure both, because a montage that removed the contaminant and the signal
together would be no use.''')

m.task(
'''def contact_pair(local_source, far_source, far_gradient: float, local_falloff: float,
                 background_a, background_b):
    """Two contacts seeing one LOCAL source and one FAR source.

    The far source arrives at nearly equal amplitude on both, differing by
    `far_gradient`. The local source falls off by `local_falloff` between them.
    Returns (contact_a, contact_b).
    """
    # TODO: contact a sees the local source at full strength and the far source at 1.0
    # TODO: contact b sees the local source at local_falloff and the far source
    #       at (1 - far_gradient)
    # TODO: add each contact's own background
    raise NotImplementedError("Implement contact_pair")''',
'''def contact_pair(local_source, far_source, far_gradient: float, local_falloff: float,
                 background_a, background_b):
    """Two contacts seeing one LOCAL source and one FAR source.

    The far source arrives at nearly equal amplitude on both, differing by
    `far_gradient`. The local source falls off by `local_falloff` between them.
    Returns (contact_a, contact_b).
    """
    a = local_source + far_source + background_a
    b = local_falloff * local_source + (1.0 - far_gradient) * far_source + background_b
    return a, b''')

m.code('''# --- TEST CELL FOR STEP 3 ---
muscle = emg_signal(T, EMG_UV, gate=gate, seed=5)
cortical_hg = bandpass(rng.standard_normal(T), 70.0, 150.0)
cortical_hg = 1.5 * cortical_hg / np.std(cortical_hg) * gate     # local, speech-locked
bg_a = aperiodic_lfp(T, 20.0, seed=21)
bg_b = aperiodic_lfp(T, 20.0, seed=22)
HG = BANDS["high gamma 70-150"]
zero = np.zeros(T)

# Measure what the montage does to each SOURCE, with no background, because a
# background that differs between contacts does not cancel and would swamp the
# comparison. Its effect is measured separately below.
print(f"{'far-field gradient':>19} {'muscle kept':>13} {'cortex kept':>13} {'advantage':>11}")
kept = {}
for grad in (0.00, 0.02, 0.10, 0.30):
    ma, mb = contact_pair(zero, muscle, grad, 0.35, zero, zero)
    ca, cb = contact_pair(cortical_hg, zero, grad, 0.35, zero, zero)
    m_keep = band_power(mb - ma, HG) / band_power(ma, HG)
    c_keep = band_power(cb - ca, HG) / band_power(ca, HG)
    kept[grad] = (m_keep, c_keep)
    adv = "exact" if m_keep < 1e-12 else f"{c_keep / m_keep:.0f}x"
    print(f"{grad:>18.0%} {m_keep:>12.2%} {c_keep:>12.2%} {adv:>10}")

assert kept[0.00][0] < 1e-6, "a perfectly uniform far field cancels exactly"
assert kept[0.02][0] < 0.1 * kept[0.02][1], \\
    "a bipolar montage must remove far more muscle than cortex"
assert kept[0.30][0] > kept[0.02][0], \\
    "and the advantage shrinks as the far field stops being uniform"
print("\\nThat is require_bipolar. A zero-sum derivation cancels whatever arrives")
print("equally on both contacts, and muscle is centimetres away while cortex is not.")

# The cost, which is real and is why this is a mitigation rather than a fix:
# each contact's own background is independent, so differencing ADDS it.
mono = band_power(bg_a, HG)
bip = band_power(bg_b - bg_a, HG)
print(f"\\nindependent background per contact, monopolar : {mono:.4g}")
print(f"the same after differencing                  : {bip:.4g}  ({bip/mono:.2f}x)")
assert 1.5 < bip / mono < 2.5, \\
    "differencing two independent backgrounds roughly doubles their power"
print("Differencing doubles whatever is NOT shared, so the montage buys a large")
print("rejection of the far field and pays for it in local noise. Worth it here,")
print("because the far field was the thing that looked like a finding.")
print("\\nStep 3 passed.")''')

m.md(r'''---

## 4. Why it escalates for overt speech only

The configured rule escalates from warning to blocking only for the `overt`
condition. That is not caution about a particular task; it is the one place where
a control exists.

Inner speech engages no articulators, so it carries no articulatory EMG.
A high-gamma increase present during overt speech and absent during inner speech
is consistent with either a cortical speech response or with muscle. A high-gamma
increase present in **both** cannot be muscle.

So the overt-against-inner contrast is a discriminator, and it is the same shape
of argument as guardrail G11: the claim needs the condition that would rule out
its confound. G7 escalates for overt because that is the condition where the
confound is live.''')

m.code('''# --- TEST CELL FOR STEP 4 ---
def trial_response(signal, band=HG):
    env = band_envelope(signal, band)
    p = np.mean([env[o - int(0.4 * FS):o].mean() for o in onsets if o > int(0.4 * FS)])
    d = np.mean([env[o:o + int(SPEECH_DUR * FS)].mean() for o in onsets])
    return d / p

scenarios = {
    "muscle only":            (np.zeros(T), emg_signal(T, EMG_UV, gate=gate, seed=7)),
    "cortex only":            (cortical_hg, np.zeros(T)),
    "both":                   (cortical_hg, emg_signal(T, EMG_UV, gate=gate, seed=7)),
}
print(f"{'what is present':>18} {'overt':>9} {'inner':>9} {'verdict':>34}")
results = {}
for name, (ctx, mus) in scenarios.items():
    overt = lfp + ctx + mus                # articulators move: muscle present
    inner = lfp + ctx                      # no articulators: no muscle
    results[name] = (trial_response(overt), trial_response(inner))
    verdict = ("could be either" if results[name][1] < 1.15
               else "cannot be muscle")
    print(f"{name:>18} {results[name][0]:>8.2f}x {results[name][1]:>8.2f}x {verdict:>34}")

# Muscle alone shows a response in overt and nothing in inner.
assert results["muscle only"][0] > 1.3 and results["muscle only"][1] < 1.15, \\
    "muscle produces an overt-only response"
# Cortex shows one in both, which is the discriminating pattern.
assert results["cortex only"][1] > 1.15, "a cortical response survives into inner speech"
assert results["both"][1] > 1.15, "and so does the cortical part of a mixed response"

print("\\nAn overt-only high-gamma increase is exactly what muscle produces, and")
print("exactly what a purely articulatory cortical response would produce too. The")
print("inner-speech row is what separates them, and G7 escalates for overt because")
print(f"escalate_only_for_conditions is {ESCALATE_ONLY_FOR}: that is the condition")
print("where the confound is live and the control is therefore required.")
print("\\nStep 4 passed.")''')

m.md(r'''---

## 5. What you established

1. Surface EMG is broadband while the LFP background falls as $1/f$, so muscle's
   share of a band rises steeply with frequency at every amplitude. At 1
   microvolt it is 1 percent of beta but 21 percent of high gamma, and it takes
   five times less muscle to double high gamma than to double beta, 2.2 against
   11.2 microvolts.
   Unlike SPK 1's spike bleed, which needed a background twelve times below normal
   before it mattered, **this contaminant reaches the physiology at ordinary
   amplitudes.**
2. Muscle is time-locked to speech, so it produces a trial-averaged high-gamma
   response that is flat before onset and peaks during the utterance. Every
   property a cortical response is expected to have, with no cortex involved.
3. A bipolar montage cancels a perfectly uniform far field exactly and keeps a
   large fraction of a local source, an advantage of orders of magnitude at a
   realistic gradient. That is `require_bipolar`. It degrades as the far field
   stops being uniform, and it doubles whatever background is *not* shared
   between the contacts, so it is a mitigation with a stated price rather than a
   fix.
4. An overt-only high-gamma increase is consistent with muscle. One that survives
   into inner speech is not. That is why G7 escalates for `overt` alone: it is
   the condition where the confound is live and a control is therefore required,
   which is guardrail G11's argument wearing G7's clothes.

### Exercises

**Exercise 1.** G7's band starts at 100 Hz. Using Section 1, decide whether that
lower edge is well chosen, and say what a study reporting a 70 to 100 Hz effect
should conclude from the fact that it sits below the guardrail's band.

**Exercise 2.** Section 3 modelled muscle as arriving uniformly. Real EMG has a
spatial gradient set by which muscle is active. Find the gradient at which
bipolar rejection stops being worth the loss of local signal, and say what you
would do beyond that point.

**Exercise 3.** The honest fix is to record EMG on a dedicated channel and
regress it out, which is what `prompt_emg_regression` in the config asks for.
Implement that regression here, and measure how much of the muscle it removes.
Then say what it costs if the EMG channel is itself contaminated by the cortical
signal.

---

**Next: GRL 4, non-stationarity.** The other guardrail whose number nothing derived.
''')

m.emit()
verify("07_guardrails", "03_emg_contamination_in_speech")
print("  GRL 3 OK")
