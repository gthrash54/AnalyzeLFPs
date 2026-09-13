"""Reader for TDT blocks exported to MATLAB v7.3 (`.mat`), which is HDF5.

Verified against a real export rather than written from memory. Layout:

    /importdata/streams/<name>/data       (n_samples, n_channels) float32, gzip
    /importdata/streams/<name>/fs         sampling rate, Hz
    /importdata/streams/<name>/channel    channel numbers
    /importdata/streams/<name>/startTime  stream start on the block clock
    /importdata/epocs/<name>/onset|offset|data
    /importdata/info/                     block metadata, some of it identifying

Two properties of this layout matter enough to state:

Transpose
    MATLAB writes column-major, so a MATLAB ``[28 x 25169920]`` array appears to
    h5py as ``(25169920, 28)``. This reader returns ``(n_channels, n_samples)``
    per the `Recording` contract, so the transpose happens here once.

Chunking
    Observed chunks of ``(585, 28)`` with gzip: chunked along samples, whole
    channel dimension per chunk. Reading a time window across all channels is
    therefore cheap (about 60 ms for 2 s of 28-channel data at 48 kHz), while
    reading one channel over a long span still decompresses every chunk it
    spans. Prefer windowed reads; do not iterate channel by channel over the
    whole recording.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from .base import (
    DEFAULT_PRIVACY_POLICY,
    EpochSeries,
    PrivacyPolicy,
    Recording,
    StreamInfo,
    register_reader,
)

FORMAT = "tdt_mat"

_ROOT = "importdata"
_STREAMS = f"{_ROOT}/streams"
_EPOCS = f"{_ROOT}/epocs"
_INFO = f"{_ROOT}/info"

# Fallback restricted set, used when no policy is supplied. The configured set
# lives in configs/privacy.yaml so a site can extend it without a code change.
_DEFAULT_RESTRICTED_INFO_FIELDS = frozenset(
    {
        "Subject",
        "Experiment",
        "User",
        "blockname",
        "date",
        "Start",
        "Stop",
        "utcStartTime",
        "utcStopTime",
        "tankpath",
    }
)


def _decode_matlab_string(arr: Any) -> str:
    """Decode a MATLAB v7.3 char array, stored as uint16 code points."""
    values = np.asarray(arr).ravel()
    return "".join(chr(int(c)) for c in values if int(c) != 0)


def _scalar(arr: Any) -> float:
    return float(np.asarray(arr).ravel()[0])


def sniff(path: Path) -> bool:
    """True when the file is HDF5 and carries the TDT export layout."""
    import h5py

    if not h5py.is_hdf5(path):
        return False
    with h5py.File(path, "r") as f:
        return _STREAMS in f or _EPOCS in f


class TdtMatRecording(Recording):
    """Lazily-read TDT block. Opening reports structure and reads no samples."""

    def __init__(self, path: Path, policy: PrivacyPolicy | None = None) -> None:
        import h5py

        self.path = Path(path)
        self.policy = policy or DEFAULT_PRIVACY_POLICY
        self._restricted = (
            self.policy.restricted_metadata_fields or _DEFAULT_RESTRICTED_INFO_FIELDS
        )
        self._file = h5py.File(self.path, "r")
        self._streams: dict[str, StreamInfo] | None = None
        self._epochs: dict[str, EpochSeries] | None = None

    @property
    def format(self) -> str:
        return FORMAT

    @property
    def streams(self) -> dict[str, StreamInfo]:
        if self._streams is None:
            self._streams = self._build_streams()
        return self._streams

    def _build_streams(self) -> dict[str, StreamInfo]:
        out: dict[str, StreamInfo] = {}
        group = self._file.get(_STREAMS)
        if group is None:
            return out
        for name in group:
            node = group[name]
            if "data" not in node:
                continue
            data = node["data"]
            # (n_samples, n_channels) as stored; see the module docstring.
            n_samples, n_channels = int(data.shape[0]), int(data.shape[1])
            channel_ids: tuple[str, ...] = ()
            if "channel" in node:
                channel_ids = tuple(
                    str(int(c)) for c in np.asarray(node["channel"]).ravel()
                )
            out[name] = StreamInfo(
                name=name,
                n_channels=n_channels,
                sfreq_hz=_scalar(node["fs"]) if "fs" in node else 0.0,
                n_samples=n_samples,
                dtype=str(data.dtype),
                start_time_s=_scalar(node["startTime"]) if "startTime" in node else 0.0,
                channel_ids=channel_ids,
            )
        return out

    @property
    def epochs(self) -> dict[str, EpochSeries]:
        if self._epochs is None:
            self._epochs = self._build_epochs()
        return self._epochs

    def _build_epochs(self) -> dict[str, EpochSeries]:
        out: dict[str, EpochSeries] = {}
        group = self._file.get(_EPOCS)
        if group is None:
            return out
        for name in group:
            node = group[name]
            # An export can store an epoc entry as a bare scalar dataset (seen
            # in the archive: a uint64 under /epocs with no onset table). A
            # membership test on a dataset raises; only groups, which have
            # keys, can carry an onset table. h5py is imported lazily in this
            # module, so the check is on shape rather than on type.
            if not hasattr(node, "keys") or "onset" not in node:
                continue
            out[name] = EpochSeries(
                name=name,
                onsets=np.asarray(node["onset"]).ravel(),
                offsets=np.asarray(node["offset"]).ravel() if "offset" in node else np.empty(0),
                values=np.asarray(node["data"]).ravel() if "data" in node else np.empty(0),
            )
        return out

    @property
    def metadata(self) -> dict[str, Any]:
        """Structural metadata. Identifier-bearing fields are excluded."""
        out: dict[str, Any] = {"format": FORMAT}
        # Whether a filename is safe to surface is a site policy, not a fact
        # about acquisition systems. Included only when the policy says so; a
        # manifest key is still the better way to refer to a recording, because
        # a path is machine-specific.
        if self.policy.filenames_deidentified:
            out["path_name"] = self.path.name
        info = self._file.get(_INFO)
        if info is not None:
            for key in info:
                if key in self._restricted:
                    continue
                node = info[key]
                arr = np.asarray(node)
                if arr.dtype == np.uint16:
                    out[key] = _decode_matlab_string(arr)
                elif arr.size == 1:
                    out[key] = arr.ravel()[0].item()
        out["restricted_fields_present"] = sorted(
            k for k in (info or {}) if k in self._restricted
        )
        return out

    def read_restricted_metadata(self) -> dict[str, Any]:
        """See `Recording.read_restricted_metadata`. De-identification only."""
        out: dict[str, Any] = {}
        info = self._file.get(_INFO)
        if info is None:
            return out
        for key in info:
            if key not in self._restricted:
                continue
            arr = np.asarray(info[key])
            if arr.dtype == np.uint16:
                out[key] = _decode_matlab_string(arr)
            else:
                out[key] = arr.ravel().tolist()
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
            raise ValueError(f"tmax ({tmax}) precedes tmin ({tmin}) for stream {stream!r}")

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

        dataset = self._file[f"{_STREAMS}/{stream}/data"]

        # Read the full channel width for the window, then select. The data is
        # chunked across the whole channel dimension, so a fancy-index read of a
        # channel subset costs the same decompression while being much slower in
        # h5py. Selecting afterwards in numpy is cheaper.
        window = dataset[start:stop, :]
        if channels is not None:
            window = window[:, requested]

        # (n_samples, n_channels) as stored -> (n_channels, n_samples) per contract.
        return np.ascontiguousarray(window.T)

    def close(self) -> None:
        f = getattr(self, "_file", None)
        if f is not None:
            f.close()
            self._file = None  # type: ignore[assignment]


register_reader(FORMAT, TdtMatRecording, sniff, entry_suffixes=(".mat",))
