import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nbgen import Module, verify

m = Module("04_spikes", "01_band_split_and_spike_bleed")

m.md(r'''# Lesson SPK 1: Splitting LFP from Spikes, and What Leaks Across {{VARIANT}}

**Analysis · Spike Trains and Single-Unit Activity**

{{INSTRUCTIONS}}

Every intracranial pipeline splits the signal into a slow band and a fast band
and treats them as separate measurements. This module builds that split properly
and then demonstrates the contamination it does not remove, which is responsible
for a large and confidently reported literature.

**What it assumes**

| From | What is used |
|---|---|
| SIG 1 | Nyquist, and that decimation removes bandwidth irreversibly. |
| SIG 2 | Filter design, transition bands, and that a filter has a phase. |
| SIG 4 | Welch, and that a spectrum estimate has variance. |
| REC 1 | That spikes fall off steeply and LFP gently. |
| REC 4 | The AP and LFP streams, split in hardware at 0.3-10 kHz and 0.5-500 Hz. |

**What it underwrites**

Guardrail **G7**, muscle and other contamination in a high band. This module
supplies the version of G7 that applies when the contaminant is the brain itself.
''')

m.code('''import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from scipy.signal import butter, filtfilt, welch

rng = np.random.default_rng(23)
FS = 30000.0                      # AP-band rate, as in REC 4
SPLIT_HZ = 300.0                  # the conventional divide
print("Environment initialized for Lesson SPK 1")''')

m.md(r'''---

## 1. Why 300 Hz, and what the number actually rests on

The split is conventionally placed near 300 Hz. That is not a property of the
brain; it is where two spectra happen to cross.

An extracellular action potential lasts on the order of a millisecond, so its
energy is concentrated above roughly 500 Hz. Synaptic and dendritic currents are
slow and their power falls steeply with frequency, following the aperiodic
$1/f^{\chi}$ decay. Around a few hundred hertz the falling LFP power and the
rising spike contribution are comparable, and any split in that region separates
most of one from most of the other.

"Most" is doing real work in that sentence. The distributions overlap, so a
filter cannot remove what a band genuinely contains, and Section 3 is about what
remains.''')

m.task(
'''def split_bands(x: np.ndarray, fs: float, split_hz: float = SPLIT_HZ, order: int = 4):
    """Split a wideband recording into (lfp, spike_band) with zero-phase filters.

    Use `scipy.signal.butter` for both, and `filtfilt` so neither band is delayed
    relative to the other, which SIG 2 showed a causal filter would do differently
    per band.

    Production equivalent: the hardware split described in REC 4, or
    `mne.io.Raw.filter` applied twice.
    """
    # TODO: design a lowpass at split_hz and a highpass at split_hz
    # TODO: apply each with filtfilt
    # TODO: return (lfp, spikes)
    raise NotImplementedError("Implement split_bands")''',
'''def split_bands(x: np.ndarray, fs: float, split_hz: float = SPLIT_HZ, order: int = 4):
    """Split a wideband recording into (lfp, spike_band) with zero-phase filters.

    Use `scipy.signal.butter` for both, and `filtfilt` so neither band is delayed
    relative to the other, which SIG 2 showed a causal filter would do differently
    per band.

    Production equivalent: the hardware split described in REC 4, or
    `mne.io.Raw.filter` applied twice.
    """
    b_lo, a_lo = butter(order, split_hz, btype='low', fs=fs)
    b_hi, a_hi = butter(order, split_hz, btype='high', fs=fs)
    return filtfilt(b_lo, a_lo, x), filtfilt(b_hi, a_hi, x)''')

m.code('''# --- TEST CELL FOR STEP 1 ---
def spike_waveform(fs=FS, width_ms=1.0):
    """A biphasic extracellular action potential, zero-mean."""
    n = int(width_ms * 1e-3 * fs)
    t = np.linspace(-1, 1, n)
    w = -np.exp(-t ** 2 / 0.08) + 0.35 * np.exp(-(t - 0.45) ** 2 / 0.12)
    return w - w.mean()

def make_recording(rate_hz, seconds, fs=FS, amp_uv=80.0, seed=0):
    """Poisson spike train convolved with a waveform, plus 1/f LFP and noise."""
    gen = np.random.default_rng(seed)
    n = int(seconds * fs)
    train = (gen.random(n) < rate_hz / fs).astype(float)
    wf = spike_waveform(fs)
    spikes = np.convolve(train, wf, mode='same') * amp_uv
    white = gen.standard_normal(n)
    freqs = np.fft.rfftfreq(n, 1 / fs); freqs[0] = 1.0
    pink = np.fft.irfft(np.fft.rfft(white) / freqs ** 0.6, n=n)
    pink = 60.0 * pink / np.std(pink)
    return spikes + pink + 4.0 * gen.standard_normal(n), train

wide, train = make_recording(20.0, 4.0, seed=1)
lfp, spk = split_bands(wide, FS)

# (a) The split is complete: the two bands sum back to the original, up to the
# transition region. Check the reconstruction error is small.
recon_err = np.std(wide - (lfp + spk)) / np.std(wide)
print(f"reconstruction error of lfp + spikes vs original: {recon_err:.3%}")
assert recon_err < 0.10, "the two bands must account for nearly all the signal"

# (b) Each band is where it claims to be.
f, P_lfp = welch(lfp, FS, nperseg=8192)
_, P_spk = welch(spk, FS, nperseg=8192)
below = f < 100
above = (f > 1000) & (f < 5000)
print(f"\\nLFP band power below 100 Hz vs above 1 kHz : "
      f"{np.mean(P_lfp[below])/np.mean(P_lfp[above]):.3e}")
print(f"spike band power above 1 kHz vs below 100 Hz: "
      f"{np.mean(P_spk[above])/np.mean(P_spk[below]):.3e}")
assert np.mean(P_lfp[below]) > 1e3 * np.mean(P_lfp[above]), "the LFP band must be slow"
assert np.mean(P_spk[above]) > 1e3 * np.mean(P_spk[below]), "the spike band must be fast"
print("\\nStep 1 passed.")''')

m.md(r'''---

## 2. The waveform sets where the spike energy sits

The choice of 300 Hz rests on the claim that a spike is fast. Check it rather
than assume it: take the waveform alone, with no train and no noise, and find
where its energy actually lives.

That number depends on the waveform width, which varies substantially between
cell types. Narrow-spiking interneurons have waveforms roughly half the duration
of broad-spiking pyramidal cells, so their energy sits proportionally higher. A
split that cleanly separates one may not separate the other.''')

m.code('''# --- TEST CELL FOR STEP 2 ---
def energy_fraction_below(width_ms, cutoff_hz, fs=FS):
    """Fraction of a spike waveform's energy below `cutoff_hz`."""
    w = spike_waveform(fs, width_ms)
    n_fft = 1 << 16
    P = np.abs(np.fft.rfft(w, n=n_fft)) ** 2
    fr = np.fft.rfftfreq(n_fft, 1 / fs)
    return float(P[fr < cutoff_hz].sum() / P.sum())

print(f"{'waveform width':>16} {'energy below 300 Hz':>21} {'peak frequency':>16}")
for width in (0.5, 1.0, 2.0):
    w = spike_waveform(FS, width)
    n_fft = 1 << 16
    P = np.abs(np.fft.rfft(w, n=n_fft)) ** 2
    fr = np.fft.rfftfreq(n_fft, 1 / FS)
    print(f"{width:>13.1f} ms {energy_fraction_below(width, 300.0):>20.1%} "
          f"{fr[int(np.argmax(P))]:>13.0f} Hz")

narrow = energy_fraction_below(0.5, 300.0)
broad = energy_fraction_below(2.0, 300.0)
assert broad > narrow, "a broader waveform puts more energy below the split"
assert broad > 0.02, "a 2 ms waveform leaves a real fraction of its energy in the LFP band"
assert broad > 100 * narrow, "and two orders of magnitude more than a narrow one"
print(f"\\nA 2 ms waveform leaves {broad:.1%} of its energy below 300 Hz, against "
      f"{narrow:.2%} for a 0.5 ms one, a factor of {broad/narrow:.0f}: "
      f"more than two orders of magnitude apart.")
print("Per spike that residue is small. Section 3 multiplies it by the firing rate.")
print("The split is a compromise across cell types, not a clean separation of one.")
print("\\nStep 2 passed.")''')

m.md(r'''---

## 3. Spike bleed: the claim, and whether it survives measurement

Here is a claim you will meet constantly. A spike waveform leaves some energy
below 300 Hz, as Section 2 showed. A population's firing rate rises during a
task. So the low-band power should rise with it, broadband, and the top of the
LFP band is what gets called high gamma. Therefore, the argument goes, a reported
high-gamma response may be nothing but filtered spikes.

The argument is sound in structure. Whether it matters is a quantitative
question, and it is answerable: build a recording where the **only** thing that
differs between conditions is the firing rate, holding the same aperiodic
background sample fixed, and measure.

Note the design carefully. Using a different background draw per condition would
make the comparison meaningless, because the background varies far more between
draws than the spikes contribute.''')

m.code('''# --- TEST CELL FOR STEP 3 ---
def background(seed, seconds, amp_uv, fs=FS):
    """Aperiodic 1/f LFP, with amplitude stated in microvolts RMS."""
    gen = np.random.default_rng(seed)
    n = int(seconds * fs)
    white = gen.standard_normal(n)
    fr = np.fft.rfftfreq(n, 1 / fs); fr[0] = 1.0
    pink = np.fft.irfft(np.fft.rfft(white) / fr ** 0.6, n=n)
    return amp_uv * pink / np.std(pink)

def spike_component(rate_hz, seed, seconds, amp_uv=80.0, fs=FS):
    gen = np.random.default_rng(seed)
    n = int(seconds * fs)
    train = (gen.random(n) < rate_hz / fs).astype(float)
    return np.convolve(train, spike_waveform(fs), mode='same') * amp_uv

def band_power(sig, lo, hi, fs=FS):
    fr, P = welch(sig, fs, nperseg=16384)
    return float(np.mean(P[(fr >= lo) & (fr < hi)]))

SEC = 8.0
BG_UV = 60.0                       # a realistic aperiodic LFP amplitude
REST_MUA, TASK_MUA = 50.0, 400.0   # multi-unit rate, an eightfold increase

bg = background(1, SEC, BG_UV)
spk_rest = spike_component(REST_MUA, 7, SEC)
spk_task = spike_component(TASK_MUA, 7, SEC)

print(f"multi-unit rate {REST_MUA:.0f} -> {TASK_MUA:.0f} Hz, identical background sample\\n")
print(f"{'band':>12} {'spikes alone':>14} {'background':>12} {'spikes as % of bg':>19} {'measured change':>17}")
BANDS = {"beta 13-30": (13, 30), "high gamma 70-150": (70, 150),
         "150-250": (150, 250), "250-300": (250, 300), "spike band 500-1k": (500, 1000)}
shares, changes = {}, {}
for name, (lo, hi) in BANDS.items():
    s_task = band_power(spk_task, lo, hi)
    b = band_power(bg, lo, hi)
    rest_p = band_power(bg + spk_rest, lo, hi)
    task_p = band_power(bg + spk_task, lo, hi)
    shares[name] = s_task / b
    changes[name] = task_p / rest_p
    print(f"{name:>12} {s_task:>14.3g} {b:>12.3g} {shares[name]:>18.2%} {changes[name]:>16.2f}x")

# The finding: at realistic amplitudes the contamination of high gamma is
# two orders of magnitude below anything measurable.
assert shares["high gamma 70-150"] < 0.01, \\
    "spikes contribute under 1 percent of high-gamma power at realistic amplitudes"
assert changes["high gamma 70-150"] < 1.02, "so an 8x rate change moves it by under 2 percent"

# Contamination is real, but it lives immediately below the split, not at 70-150.
assert shares["250-300"] > 10 * shares["high gamma 70-150"], \\
    "the bleed is concentrated just under the cutoff"
assert shares["spike band 500-1k"] > 0.5, "and above it, the spikes ARE the signal"

# So state the condition under which the received claim WOULD hold.
s50 = band_power(spk_rest, 70, 150)
s400 = band_power(spk_task, 70, 150)
bg_hg = band_power(bg, 70, 150)
needed_power = (s400 - 1.10 * s50) / 0.10          # for a 10% change in high gamma
needed_amp = BG_UV * np.sqrt(needed_power / bg_hg)
print(f"\\nFor this rate change to move high-gamma power by 10 percent, the aperiodic")
print(f"background would have to be {needed_amp:.1f} uV RMS instead of {BG_UV:.0f} uV,")
print(f"which is {BG_UV/needed_amp:.0f} times smaller than a typical recording.")
assert needed_amp < BG_UV / 5, "the required background is far below anything realistic"

# But the ratio is not fixed by nature. Power goes as amplitude squared, so a
# montage that cancels shared LFP without cancelling local spikes raises the
# spike share quadratically. LIN 2 measured exactly such a montage.
for reduction in (1, 2, 4, 10):
    print(f"  background reduced {reduction:>2}x  ->  spike share of high gamma "
          f"{shares['high gamma 70-150'] * reduction ** 2:>7.2%}")
assert shares["high gamma 70-150"] * 10 ** 2 > 10 * shares["high gamma 70-150"], \\
    "the share rises with the SQUARE of any reduction in background amplitude"
print("\\nStep 3 passed. The received claim is checkable and, at realistic amplitudes,")
print("false by two orders of magnitude. It becomes true only where the aperiodic")
print("background has been suppressed, which is precisely what a bipolar montage does.")''')

m.md(r'''---

## 4. What you established

1. A zero-phase split at 300 Hz reconstructs the original to within a few
   percent, and each band is where it claims to be by three orders of magnitude.
2. The 300 Hz figure is a compromise across cell types, not a clean separation.
   A 2 ms waveform leaves 3.5 percent of its energy below the split against
   0.03 percent for a 0.5 ms one, more than two orders of magnitude apart.
   Narrow-spiking and broad-spiking cells are not treated equally by one filter.
3. The widely repeated claim that spike bleed contaminates high gamma **does not
   survive measurement at realistic amplitudes**. With an identical background
   sample and an eightfold multi-unit rate increase, spikes contribute 0.08
   percent of 70-150 Hz power and move it by under 2 percent. The contamination
   is real but lives immediately below the split, at 250-300 Hz, where it is
   twenty times larger.
4. The claim would hold if the aperiodic background were about twelve times
   smaller than typical. That is not a hypothetical: power goes as amplitude
   squared, so any montage that cancels shared LFP without cancelling local
   spikes raises the spike share quadratically. LIN 2 measured exactly such a
   montage. **The right question is not whether spike bleed happens, but what
   your montage did to the ratio**, which is guardrail G7 asked properly.

### Exercises

**Exercise 1.** Section 3 used a Poisson train. Real firing is not Poisson: it
has refractoriness and often bursts. Repeat the measurement with a bursty train
at the same mean rate and say whether the bleed gets stronger or weaker, and why.

**Exercise 2.** Section 3 found the spike share of high gamma to be 0.08 percent
for one assumed spike amplitude and one background amplitude. Both are estimates.
Redo the calculation across spike amplitudes from 30 to 300 microvolts and
background amplitudes from 5 to 100 microvolts, and produce the region of that
plane in which the received claim is true. Then say where a bipolar STN
derivation sits in it.

**Exercise 3.** REC 4 showed that Neuropixels splits bands in hardware, before any
of this. Does hardware splitting prevent spike bleed into the LFP stream, reduce
it, or leave it unchanged? Answer from the filter, not from intuition.

---

**Next: SPK 2, robust spike detection.** Having separated the spike band, the
question is what counts as a spike in it, and the answer turns on an estimator
that PRE 1 already showed goes blind in exactly the situation you need it.
''')

m.emit()
verify("04_spikes", "01_band_split_and_spike_bleed")
print("  SPK 1 OK")
