"""Shared `Recording` implementation for formats MNE opens lazily.

BrainVision and EDF differ only in which MNE function opens them and how a file
is recognized. Everything else, the stream grouping, the windowed read, the
privacy split, is identical, so it lives here once and each format contributes
a loader and a sniffer.

Three decisions worth stating, because each is a place a reader can be silently
wrong:

Streams
    These formats hold one continuous recording at one sampling rate, not
    several streams the way a TDT block does. Channels are grouped by the
    channel type MNE reports, so a file that distinguishes ``eeg`` from ``emg``
    surfaces two streams and a file that types everything the same surfaces
    one. Grouping is by what the file declares, never by guessing from a
    channel name. A stream's `role` is a judgment and stays in the manifest.

Orientation and dtype
    `mne.io.BaseRaw.get_data` returns ``(n_channels, n_samples)``, which is
    already the `Recording` contract, so no transpose happens here. It also
    returns float64 regardless of the on-disk dtype, which is why `StreamInfo`
    reports float64: the field describes what `read` hands back.

Laziness
    Every loader passes ``preload=False``, so opening reads the header and no
    samples. `streams` and `epochs` are built on first access, not on open.
"""

from __future__ import annotations

import abc
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

import numpy as np

from .base import (
    DEFAULT_PRIVACY_POLICY,
    EpochSeries,
    PrivacyPolicy,
    Recording,
    StreamInfo,
)

if TYPE_CHECKING:  # pragma: no cover - typing only
    from mne.io import BaseRaw

# Fields in `mne.Info` that can carry an identifier. The configured set lives in
# configs/privacy.yaml so a site extends it without a code change; this is the
# fallback used when a policy declares nothing for the format.
#
# meas_date is restricted by default, unlike the TDT readers, because for these
# formats it is the acquisition timestamp written by the amplifier and a surgery
# date is recoverable from it. A site that has judged otherwise says so in
# configs/privacy.yaml.
DEFAULT_RESTRICTED_INFO_FIELDS = frozenset(
    {
        "subject_info",
        "meas_date",
        "experimenter",
        "description",
    }
)

# What `read` returns, not what is on disk. See the module docstring.
_READ_DTYPE = "float64"


class MneRecording(Recording):
    """A recording opened through MNE, read in windows and never preloaded."""

    #: Registry key, set by each concrete reader.
    FORMAT: ClassVar[str] = ""

    #: Suffix of the file that opens this format, used to resolve a directory.
    ENTRY_SUFFIX: ClassVar[str] = ""

    def __init__(self, path: str | Path, policy: PrivacyPolicy | None = None) -> None:
        self.path = self._resolve(Path(path))
        self.policy = policy or DEFAULT_PRIVACY_POLICY
        self._restricted = (
            self.policy.restricted_metadata_fields or DEFAULT_RESTRICTED_INFO_FIELDS
        )
        self._raw: BaseRaw | None = self._open_raw(self.path)
        self._streams: dict[str, StreamInfo] | None = None
        self._epochs: dict[str, EpochSeries] | None = None
        # Stream name -> channel indices into the underlying Raw, ascending.
        self._picks: dict[str, list[int]] = {}

    # -- format hooks -------------------------------------------------------

    @staticmethod
    @abc.abstractmethod
    def _open_raw(path: Path) -> BaseRaw:
        """Open the file with the right MNE reader, without preloading."""

    @classmethod
    def _resolve(cls, path: Path) -> Path:
        """Accept either the entry file or a directory holding exactly one.

        Staged recordings arrive as a block directory, so pointing a manifest
        row at the directory is the natural thing to write. More than one
        candidate is refused rather than picked, because choosing for the
        caller here would silently analyze the wrong recording.
        """
        if not path.is_dir():
            return path
        candidates = sorted(path.glob(f"*{cls.ENTRY_SUFFIX}"))
        if len(candidates) != 1:
            raise ValueError(
                f"expected exactly one {cls.ENTRY_SUFFIX} in {path.name}, "
                f"found {len(candidates)}; name the file in the manifest"
            )
        return candidates[0]

    # -- Recording ----------------------------------------------------------

    @property
    def format(self) -> str:
        return self.FORMAT

    @property
    def _open(self) -> BaseRaw:
        if self._raw is None:
            raise ValueError(f"{self.path.name} is closed")
        return self._raw

    @property
    def streams(self) -> dict[str, StreamInfo]:
        if self._streams is None:
            self._streams = self._build_streams()
        return self._streams

    def _build_streams(self) -> dict[str, StreamInfo]:
        raw = self._open
        names = list(raw.ch_names)
        types = list(raw.get_channel_types())
        sfreq = float(raw.info["sfreq"])
        n_samples = int(raw.n_times)

        groups: dict[str, list[int]] = {}
        for index, kind in enumerate(types):
            groups.setdefault(kind, []).append(index)

        out: dict[str, StreamInfo] = {}
        for kind, picks in groups.items():
            self._picks[kind] = picks
            out[kind] = StreamInfo(
                name=kind,
                n_channels=len(picks),
                sfreq_hz=sfreq,
                n_samples=n_samples,
                dtype=_READ_DTYPE,
                start_time_s=float(raw.first_time),
                channel_ids=tuple(names[i] for i in picks),
            )
        return out

    @property
    def epochs(self) -> dict[str, EpochSeries]:
        if self._epochs is None:
            self._epochs = self._build_epochs()
        return self._epochs

    def _build_epochs(self) -> dict[str, EpochSeries]:
        """One series per distinct marker label.

        Grouping by label rather than returning one flat list is what makes a
        marker usable as a condition: a label is the thing a paradigm names,
        and `windows.csv` is written in those terms.
        """
        raw = self._open
        annotations = raw.annotations
        if len(annotations) == 0:
            return {}

        # Annotation onsets are on the same clock as the data, offset by
        # first_time. Subtracting it makes them relative to the first sample,
        # which is what every consumer of EpochSeries assumes.
        first = float(raw.first_time)
        grouped: dict[str, list[tuple[float, float]]] = {}
        # strict=True: MNE keeps these three arrays the same length, and a
        # silent truncation here would drop markers without an error.
        for onset, duration, label in zip(
            annotations.onset,
            annotations.duration,
            annotations.description,
            strict=True,
        ):
            grouped.setdefault(str(label), []).append(
                (float(onset) - first, float(duration))
            )

        out: dict[str, EpochSeries] = {}
        for label, items in grouped.items():
            onsets = np.array([o for o, _ in items], dtype=float)
            durations = np.array([d for _, d in items], dtype=float)
            out[label] = EpochSeries(
                name=label,
                onsets=onsets,
                offsets=onsets + durations,
            )
        return out

    @property
    def metadata(self) -> dict[str, Any]:
        """Structural metadata. Identifier-bearing fields are excluded."""
        raw = self._open
        info = raw.info
        out: dict[str, Any] = {"format": self.FORMAT}
        # Whether a filename is safe to surface is a site policy, not a fact
        # about acquisition systems. A manifest key remains the better way to
        # refer to a recording, because a path is machine-specific.
        if self.policy.filenames_deidentified:
            out["path_name"] = self.path.name

        out["sfreq_hz"] = float(info["sfreq"])
        out["n_channels"] = len(raw.ch_names)
        out["n_samples"] = int(raw.n_times)
        out["duration_s"] = float(raw.n_times) / float(info["sfreq"])

        counts: dict[str, int] = {}
        for kind in raw.get_channel_types():
            counts[kind] = counts.get(kind, 0) + 1
        out["channel_types"] = counts

        for field in ("highpass", "lowpass", "line_freq"):
            value = info.get(field)
            if value is not None:
                out[f"{field}_hz"] = float(value)

        out["n_annotations"] = len(raw.annotations)
        out["restricted_fields_present"] = sorted(
            field
            for field in self._restricted
            if info.get(field) is not None
        )
        return out

    def read_restricted_metadata(self) -> dict[str, Any]:
        """See `Recording.read_restricted_metadata`. De-identification only."""
        info = self._open.info
        out: dict[str, Any] = {}
        for field in sorted(self._restricted):
            value = info.get(field)
            if value is None:
                continue
            # meas_date is a datetime and subject_info a dict; both are
            # rendered as text so a caller cannot accidentally do arithmetic
            # on an identifier and call the result a result.
            out[field] = str(value)
        return out

    def read(
        self,
        stream: str,
        channels: Sequence[int] | None = None,
        tmin: float | None = None,
        tmax: float | None = None,
    ) -> np.ndarray:
        try:
            info = self.streams[stream]
        except KeyError:
            raise KeyError(
                f"no stream {stream!r} in {self.path.name}; have {sorted(self.streams)}"
            ) from None

        start = 0 if tmin is None else self.time_to_sample(stream, tmin)
        stop = info.n_samples if tmax is None else self.time_to_sample(stream, tmax)
        if stop < start:
            raise ValueError(
                f"tmax ({tmax}) precedes tmin ({tmin}) for stream {stream!r}"
            )

        if channels is None:
            requested = list(range(info.n_channels))
        else:
            requested = [int(c) for c in channels]
            out_of_range = [c for c in requested if not 0 <= c < info.n_channels]
            if out_of_range:
                raise IndexError(
                    f"channels {out_of_range} out of range for stream {stream!r} "
                    f"with {info.n_channels} channels"
                )

        picks = self._picks[stream]
        # Read the stream's channels in file order, then select. Handing MNE a
        # reordered or repeated pick list is not guaranteed to come back in the
        # order given, and a silently permuted channel axis is the worst class
        # of bug this reader could have. Reordering in numpy afterwards is
        # explicit and cheap.
        window = self._open.get_data(picks=picks, start=start, stop=stop)
        if channels is not None:
            window = window[requested, :]
        return np.ascontiguousarray(window)

    def close(self) -> None:
        raw = getattr(self, "_raw", None)
        if raw is not None:
            close = getattr(raw, "close", None)
            if callable(close):
                close()
            self._raw = None
