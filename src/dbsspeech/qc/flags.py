"""Quality-control flag detectors.

Pure functions over ``(data, sfreq, channel names, regions, thresholds)``. They
propose; they never decide. Separating detection from decision is what makes the
pipeline defensible: a reviewer sees exactly why something was flagged, with the
numbers, and can overrule it.

Two rules the guide fixes and these enforce:

Never delete
    A window flag becomes an annotation, not a cut. Recipes decide how to treat
    annotations. No detector removes a sample.

Refuse to propose on too few channels
    Robust statistics over four to eight contacts are fragile. Below
    `min_channels_for_outlier_stats` a within-region detector reports its
    evidence with no proposed action, so a reviewer sees the number without being
    nudged by a threshold that could not support it.

Deliberately not using pyprep's NoisyChannels, which the guide suggests. It is
tuned for scalp EEG with dozens of electrodes and its correlation and RANSAC
heuristics assume neighbors that a 1-3-3-1 depth lead does not have. The
detectors here are the same ideas computed within region, with the channel-count
guard the guide's own warning calls for.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any

import numpy as np

_EPS = np.finfo(float).tiny


@dataclass(frozen=True)
class Flag:
    """A machine-proposed concern, with the evidence that produced it."""

    target_type: str          # channel | window | trial
    target: str
    flag_type: str
    evidence: dict[str, Any] = field(default_factory=dict)
    proposed_action: str = ""
    severity: str = "low"
    detector: str = ""

    @property
    def flag_id(self) -> str:
        """Stable across re-runs, so a reviewer's decision survives re-detection.

        Includes the detector, because two detectors can raise the same concern
        about the same target: both peer-comparison detectors report
        insufficient_channels for a group with too few contacts. Without it their
        ids collide and one silently overwrites the other's decision.
        """
        import hashlib

        key = f"{self.target_type}|{self.target}|{self.flag_type}|{self.detector}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    def describe(self) -> str:
        parts = [f"[{self.severity}] {self.flag_type} on {self.target}"]
        if self.proposed_action:
            parts.append(f"proposed: {self.proposed_action}")
        for key, value in self.evidence.items():
            parts.append(f"{key}={value}")
        return "  ".join(parts)


def _robust_z(values: np.ndarray) -> np.ndarray:
    """Median and MAD based z. Resistant to the outliers it is looking for."""
    median = np.median(values)
    mad = np.median(np.abs(values - median))
    # 1.4826 makes the MAD comparable to a standard deviation for normal data.
    scale = 1.4826 * mad
    if scale <= 0:
        return np.zeros_like(values)
    return (values - median) / scale


def _band_power(data: np.ndarray, sfreq: float, lo: float, hi: float) -> np.ndarray:
    """Mean power in a band, per channel, by periodogram."""
    n = data.shape[1]
    freqs = np.fft.rfftfreq(n, 1.0 / sfreq)
    spectrum = np.abs(np.fft.rfft(data, axis=1)) ** 2
    mask = (freqs >= lo) & (freqs < hi)
    if not mask.any():
        return np.zeros(data.shape[0])
    return spectrum[:, mask].mean(axis=1)


def _comparison_groups(
    regions: Sequence[str],
    kinds: Sequence[str] | None,
    grouping: str,
) -> dict[str, list[int]]:
    """Group channels into sets that are fair to compare against each other.

    `region_and_kind` keeps rings apart from segments. A ring contact has roughly
    twice a segment's surface area, so it reads systematically different noise
    characteristics, and pooling them flags every ring for being a ring.
    """
    out: dict[str, list[int]] = {}
    for i, region in enumerate(regions):
        if grouping == "region_and_kind" and kinds is not None and i < len(kinds) and kinds[i]:
            label = f"{region}/{kinds[i]}"
        else:
            label = region
        out.setdefault(label, []).append(i)
    return out


def _enabled(thresholds: dict[str, Any], name: str) -> dict[str, Any] | None:
    spec = (thresholds.get("detectors") or {}).get(name)
    return spec if spec and spec.get("enabled", True) else None


# ---------------------------------------------------------------------------
# Channel-level detectors
# ---------------------------------------------------------------------------

def flat_channel(data, sfreq, names, regions, thresholds) -> list[Flag]:
    """A channel whose variance has collapsed relative to its peers."""
    spec = _enabled(thresholds, "flat_channel")
    if spec is None:
        return []
    stds = data.std(axis=1)
    median = np.median(stds)
    if median <= 0:
        return []
    cutoff = median * float(spec["std_fraction_of_median"])
    return [
        Flag(
            "channel", names[i], "flat_channel",
            {"std": float(stds[i]), "median_std": float(median),
             "fraction_of_median": round(float(stds[i] / median), 6)},
            spec["proposed_action"], spec["severity"],
        )
        for i in range(len(names))
        if stds[i] < cutoff
    ]


def _within_group_outlier(
    values: np.ndarray, names, regions, spec, flag_type: str, min_channels: int,
    kinds: Sequence[str] | None = None, grouping: str = "region_and_kind",
) -> list[Flag]:
    # flag_type doubles as the detector name for these two.
    """Shared body for detectors comparing a statistic within a peer group."""
    flags: list[Flag] = []
    for region, idx in _comparison_groups(regions, kinds, grouping).items():
        subset = values[idx]
        enough = len(idx) >= min_channels
        z = _robust_z(subset) if enough else np.zeros(len(idx))
        for position, channel in enumerate(idx):
            evidence: dict[str, Any] = {
                "group": region,
                "n_channels_in_group": len(idx),
                "value": round(float(subset[position]), 6),
                "group_median": round(float(np.median(subset)), 6),
            }
            if not enough:
                # Too few channels to support a threshold. Report, do not propose.
                if position == 0:
                    flags.append(
                        Flag("channel", f"group:{region}", "insufficient_channels",
                             {**evidence, "minimum_required": min_channels,
                              "detector": flag_type},
                             "", "low", detector=flag_type)
                    )
                continue
            evidence["robust_z"] = round(float(z[position]), 3)
            if abs(z[position]) > float(spec["robust_z_max"]):
                flags.append(
                    Flag("channel", names[channel], flag_type, evidence,
                         spec["proposed_action"], spec["severity"], detector=flag_type)
                )
    return flags


def variance_outlier(data, sfreq, names, regions, thresholds, kinds=None) -> list[Flag]:
    """A channel far from its peer group's typical amplitude, either way."""
    spec = _enabled(thresholds, "variance_outlier")
    if spec is None:
        return []
    log_std = np.log10(data.std(axis=1) + _EPS)
    return _within_group_outlier(
        log_std, names, regions, spec, "variance_outlier",
        int(thresholds.get("min_channels_for_outlier_stats", 4)),
        kinds, thresholds.get("outlier_grouping", "region_and_kind"),
    )


def _block_median_kurtosis(
    data: np.ndarray, sfreq: float, block_s: float
) -> tuple[np.ndarray, int]:
    """Median excess kurtosis over fixed-length blocks, per channel.

    Kurtosis over a whole record grows with its length, because a longer record
    is more likely to contain an extreme value, so a threshold on it means
    different things at different durations. Measured on real data: median 170
    over 60 s and 1429 over 515 s of the same channels.

    Taking the median across fixed-length blocks removes that dependence. The
    statistic then answers "how heavy-tailed is a typical block of this channel",
    which is duration-stable and is the question the detector was always meant to
    ask. A single artifact no longer drags the whole channel's number up either,
    which is what the window detector is for.

    Returns the per-channel statistic and the block count actually used, which is
    part of the evidence: a median over very few blocks is not robust, so the
    block width shrinks until there are enough of them.
    """
    from scipy.stats import kurtosis as _kurtosis

    # A median over two blocks is their mean, so one bad block drags it and the
    # statistic stops being robust. Shrink the block until there are enough of
    # them, and only fall back to the whole record when even that is impossible.
    min_blocks = 5
    width = max(16, int(round(block_s * sfreq)))
    if data.shape[1] // width < min_blocks:
        width = max(16, data.shape[1] // min_blocks)

    n_blocks = data.shape[1] // width
    if n_blocks < 3:
        return _kurtosis(data, axis=1, fisher=True, bias=False), 1
    blocks = data[:, : n_blocks * width].reshape(data.shape[0], n_blocks, width)
    per_block = _kurtosis(blocks, axis=2, fisher=True, bias=False)
    return np.median(per_block, axis=1), n_blocks


def kurtosis_outlier(data, sfreq, names, regions, thresholds) -> list[Flag]:
    """Rare large excursions: pops, spikes, a loose connection."""
    spec = _enabled(thresholds, "kurtosis_outlier")
    if spec is None:
        return []

    block_s = float(spec.get("block_s", 10.0))
    values, n_blocks = _block_median_kurtosis(data, sfreq, block_s)
    cutoff = float(spec["max_excess_kurtosis"])
    duration = round(data.shape[1] / sfreq, 1)
    return [
        Flag("channel", names[i], "kurtosis_outlier",
             {"median_block_excess_kurtosis": round(float(values[i]), 2),
              "threshold": cutoff, "block_s": block_s, "n_blocks": n_blocks,
              "duration_s": duration},
             spec["proposed_action"], spec["severity"], detector="kurtosis_outlier")
        for i in range(len(names))
        if values[i] > cutoff
    ]


def hf_noise_ratio(data, sfreq, names, regions, thresholds, kinds=None) -> list[Flag]:
    """A channel whose high-frequency content dominates, relative to its peers."""
    spec = _enabled(thresholds, "hf_noise_ratio")
    if spec is None:
        return []
    lo_band, hi_band = spec["low_band_hz"], spec["high_band_hz"]
    if hi_band[1] > sfreq / 2:
        return []  # the band does not exist at this sampling rate
    low = _band_power(data, sfreq, lo_band[0], lo_band[1])
    high = _band_power(data, sfreq, hi_band[0], hi_band[1])
    ratio = np.log10((high + _EPS) / (low + _EPS))
    return _within_group_outlier(
        ratio, names, regions, spec, "hf_noise_ratio",
        int(thresholds.get("min_channels_for_outlier_stats", 4)),
        kinds, thresholds.get("outlier_grouping", "region_and_kind"),
    )


def line_noise(data, sfreq, names, regions, thresholds, mains_hz: float = 60.0) -> list[Flag]:
    """Mains prominence at the fundamental and harmonics."""
    spec = _enabled(thresholds, "line_noise")
    if spec is None:
        return []
    freqs = np.fft.rfftfreq(data.shape[1], 1.0 / sfreq)
    spectrum = np.abs(np.fft.rfft(data, axis=1)) ** 2
    width = float(spec["neighborhood_hz"])
    cutoff = float(spec["ratio_max"])
    flags: list[Flag] = []
    for i, name in enumerate(names):
        worst_ratio, worst_harmonic = 0.0, 0.0
        for harmonic in (mains_hz, mains_hz * 2, mains_hz * 3):
            if harmonic >= sfreq / 2:
                break
            peak = (freqs >= harmonic - 1) & (freqs <= harmonic + 1)
            around = ((freqs >= harmonic - width) & (freqs <= harmonic + width)) & ~peak
            if not peak.any() or not around.any():
                continue
            ratio = float(spectrum[i, peak].max() / (spectrum[i, around].mean() + _EPS))
            if ratio > worst_ratio:
                worst_ratio, worst_harmonic = ratio, harmonic
        if worst_ratio > cutoff:
            flags.append(
                Flag("channel", name, "line_noise",
                     {"harmonic_hz": worst_harmonic, "peak_to_neighborhood": round(worst_ratio, 1),
                      "threshold": cutoff, "mains_hz": mains_hz},
                     spec["proposed_action"], spec["severity"], detector="line_noise")
            )
    return flags


def clipping(data, sfreq, names, regions, thresholds) -> list[Flag]:
    """A saturated amplifier repeats its rail, so the extreme value recurs."""
    spec = _enabled(thresholds, "clipping")
    if spec is None:
        return []
    cutoff = float(spec["fraction_at_rail_max"])
    flags: list[Flag] = []
    for i, name in enumerate(names):
        channel = data[i]
        extreme = np.max(np.abs(channel))
        if extreme <= 0:
            continue
        at_rail = np.isclose(np.abs(channel), extreme, rtol=1e-6)
        fraction = float(at_rail.mean())
        if fraction > cutoff:
            flags.append(
                Flag("channel", name, "clipping",
                     {"fraction_at_rail": round(fraction, 6), "rail_value": float(extreme),
                      "threshold": cutoff},
                     spec["proposed_action"], spec["severity"], detector="clipping")
            )
    return flags


# ---------------------------------------------------------------------------
# Window and trial detectors
# ---------------------------------------------------------------------------

def amplitude_window(data, sfreq, names, regions, thresholds) -> list[Flag]:
    """Transient artifact: a window far outside a channel's own typical range.

    Proposes an annotation, never a cut. Recipes decide how to treat it.
    """
    spec = _enabled(thresholds, "amplitude_window")
    if spec is None:
        return []
    width = max(1, int(round(float(spec["window_s"]) * sfreq)))
    z_max = float(spec["robust_z_max"])
    n_windows = data.shape[1] // width
    if n_windows < 8:
        return []

    flags: list[Flag] = []
    for i, name in enumerate(names):
        blocks = data[i, : n_windows * width].reshape(n_windows, width)
        ptp = blocks.max(axis=1) - blocks.min(axis=1)
        if not np.any(ptp > 0):
            continue
        # Robust z on log amplitude, matching the other outlier detectors. A bare
        # ratio to the median has no interpretable false-positive rate, and it
        # scales differently depending on how spread the channel already is.
        z = _robust_z(np.log10(ptp + _EPS))
        over = z > z_max
        if not over.any():
            continue

        # Merge contiguous windows into one episode. An artifact is an episode,
        # not five separate seconds, and one flag per second is unreviewable:
        # on a real 515 s block that produced 238 flags for what a person would
        # describe as a handful of events.
        edges = np.flatnonzero(np.diff(over.astype(int)))
        starts = ([0] if over[0] else []) + list(edges[over[edges + 1]] + 1)
        for start in starts:
            end = start
            while end + 1 < n_windows and over[end + 1]:
                end += 1
            t0 = float(start * width / sfreq)
            t1 = float((end + 1) * width / sfreq)
            span = slice(start, end + 1)
            flags.append(
                Flag("window", f"{name}@{t0:.2f}s", "amplitude_window",
                     {"channel": name, "t_start_s": round(t0, 3),
                      "t_end_s": round(t1, 3),
                      "n_windows": int(end - start + 1),
                      "peak_robust_z": round(float(z[span].max()), 2),
                      "peak_ptp": round(float(ptp[span].max()), 6),
                      "median_ptp": round(float(np.median(ptp)), 6),
                      "reference_span_s": round(data.shape[1] / sfreq, 1)},
                     spec["proposed_action"], spec["severity"],
                     detector="amplitude_window")
            )
    return flags


def trial_amplitude_outlier(
    data, sfreq, names, regions, thresholds, trials: Sequence[dict[str, Any]] | None = None
) -> list[Flag]:
    """A condition window whose amplitude is unlike that channel's others."""
    spec = _enabled(thresholds, "trial_amplitude_outlier")
    if spec is None or not trials:
        return []
    n_trials = len(trials)
    if n_trials < int(thresholds.get("min_channels_for_outlier_stats", 4)):
        return []
    cutoff = float(spec["robust_z_max"])
    flags: list[Flag] = []
    for i, name in enumerate(names):
        ptp = []
        for trial in trials:
            lo = max(0, int(float(trial["t_start_s"]) * sfreq))
            hi = min(data.shape[1], int(float(trial["t_end_s"]) * sfreq))
            segment = data[i, lo:hi]
            ptp.append(float(segment.max() - segment.min()) if segment.size else 0.0)
        z = _robust_z(np.asarray(ptp))
        for t, trial in enumerate(trials):
            if abs(z[t]) > cutoff:
                flags.append(
                    Flag("trial", f"{name}@{trial.get('condition', t)}",
                         "trial_amplitude_outlier",
                         {"channel": name, "condition": trial.get("condition"),
                          "ptp": round(ptp[t], 6), "robust_z": round(float(z[t]), 2)},
                         spec["proposed_action"], spec["severity"],
                         detector="trial_amplitude_outlier")
                )
    return flags


DETECTORS = (
    flat_channel,
    variance_outlier,
    kurtosis_outlier,
    hf_noise_ratio,
    line_noise,
    clipping,
    amplitude_window,
)


def detect_all(
    data: np.ndarray,
    sfreq: float,
    names: Sequence[str],
    regions: Sequence[str],
    thresholds: dict[str, Any],
    trials: Sequence[dict[str, Any]] | None = None,
    mains_hz: float = 60.0,
    kinds: Sequence[str] | None = None,
) -> list[Flag]:
    """Run every enabled detector. Order is stable so reports diff cleanly.

    `kinds` says whether each channel is a ring or a segment, which lets the
    peer-comparison detectors avoid judging a ring against segments.
    """
    flags: list[Flag] = []
    for detector in DETECTORS:
        if detector is line_noise:
            flags.extend(detector(data, sfreq, names, regions, thresholds, mains_hz))
        elif detector in (variance_outlier, hf_noise_ratio):
            flags.extend(detector(data, sfreq, names, regions, thresholds, kinds))
        else:
            flags.extend(detector(data, sfreq, names, regions, thresholds))
    flags.extend(
        trial_amplitude_outlier(data, sfreq, names, regions, thresholds, trials)
    )
    return sorted(flags, key=lambda f: (f.target_type, f.flag_type, f.target))
