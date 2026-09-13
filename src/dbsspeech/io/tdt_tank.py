"""Reader for raw TDT tanks: the `.tsq` event index plus the `.tev` data file.

Most blocks in a case are never converted to MATLAB, so this reader is what makes
them usable without a manual conversion step. It also reads stimulation epochs
straight from the index, where they already are, rather than depending on a
conversion to carry them.

Layout, verified against a real tank rather than written from memory:

`.tsq` is a flat array of 40-byte records:

    offset  size  field
    0       4     size       record length in 4-byte words, including this header
    4       4     type       0x8101 stream, 0x101 STRON, 0x102 STROFF, 0x8801 mark
    8       4     code       four-character store name
    12      2     channel    1-based
    14      2     sortcode
    16      8     timestamp  seconds, on the tank clock
    24      8     ev         byte offset into .tev for a stream; a float64 value for an epoch
    32      4     format     0 float32, 1 int32, 2 int16, 3 int8, 4 float64
    36      4     frequency  Hz

The header is 10 words, so a stream record holds ``size - 10`` words of data. For
float32 at 4 bytes per sample that is ``size - 10`` samples per record per
channel, and records for a channel are contiguous in time.

`.tev` is a flat binary; the index says where each chunk lives, so a windowed read
is a seek and a slice. No part of the file is loaded to answer a question about
structure.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
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

FORMAT = "tdt_tank"

_TSQ_RECORD_BYTES = 40
_TSQ_HEADER_WORDS = 10

# TDT event type codes.
_TYPE_STREAM = 0x8101
_TYPE_STRON = 0x101
_TYPE_STROFF = 0x102

# TDT format codes to numpy dtypes.
_FORMATS: dict[int, np.dtype] = {
    0: np.dtype("<f4"),
    1: np.dtype("<i4"),
    2: np.dtype("<i2"),
    3: np.dtype("<i1"),
    4: np.dtype("<f8"),
}

_TSQ_DTYPE = np.dtype(
    [
        ("size", "<i4"),
        ("type", "<i4"),
        ("code", "S4"),
        ("channel", "<u2"),
        ("sortcode", "<u2"),
        ("timestamp", "<f8"),
        ("ev", "<i8"),
        ("format", "<i4"),
        ("frequency", "<f4"),
    ]
)


@dataclass(frozen=True)
class _StoreIndex:
    """Where every chunk of one stream lives in the .tev."""

    name: str
    channels: np.ndarray       # 1-based channel per record
    timestamps: np.ndarray
    offsets: np.ndarray        # byte offset into .tev
    samples_per_record: int
    dtype: np.dtype
    sfreq_hz: float

    @property
    def channel_ids(self) -> np.ndarray:
        return np.unique(self.channels)


def _read_index(tsq_path: Path) -> np.ndarray:
    raw = np.fromfile(tsq_path, dtype=np.uint8)
    n = len(raw) // _TSQ_RECORD_BYTES
    return raw[: n * _TSQ_RECORD_BYTES].view(_TSQ_DTYPE)


def sniff(path: Path) -> bool:
    """True when the path is a `.tsq`, or a directory holding exactly one."""
    p = Path(path)
    if p.is_file():
        return p.suffix.lower() == ".tsq"
    if p.is_dir():
        return len(list(p.glob("*.tsq"))) == 1
    return False


class TdtTankRecording(Recording):
    """A raw TDT tank, read lazily through its own index."""

    def __init__(self, path: Path, policy: PrivacyPolicy | None = None) -> None:
        p = Path(path)
        if p.is_dir():
            candidates = sorted(p.glob("*.tsq"))
            if len(candidates) != 1:
                raise ValueError(
                    f"expected exactly one .tsq in {p}, found {len(candidates)}"
                )
            p = candidates[0]

        self.path = p
        self.policy = policy or DEFAULT_PRIVACY_POLICY
        # A tank can be opened with only its index. Structure comes from the
        # .tsq alone, which makes triage possible on a tank whose bulk data has
        # not been synced; read() is what needs the .tev.
        self._tev = p.with_suffix(".tev")

        self._index = _read_index(p)
        self._stores: dict[str, _StoreIndex] = {}
        self._streams: dict[str, StreamInfo] | None = None
        self._epochs: dict[str, EpochSeries] | None = None
        self._handle = None
        self._build_stores()

    # ---- structure -----------------------------------------------------------

    def _build_stores(self) -> None:
        idx = self._index
        stream_mask = idx["type"] == _TYPE_STREAM
        for code in np.unique(idx["code"][stream_mask]):
            name = code.decode("latin-1").rstrip("\x00").strip()
            if not name:
                continue
            rows = idx[stream_mask & (idx["code"] == code)]
            dtype = _FORMATS.get(int(rows["format"][0]), _FORMATS[0])
            words = int(rows["size"][0]) - _TSQ_HEADER_WORDS
            samples = words * 4 // dtype.itemsize
            self._stores[name] = _StoreIndex(
                name=name,
                channels=rows["channel"].astype(np.int64),
                timestamps=rows["timestamp"].astype(np.float64),
                offsets=rows["ev"].astype(np.int64),
                samples_per_record=samples,
                dtype=dtype,
                sfreq_hz=float(rows["frequency"][0]),
            )

    @property
    def format(self) -> str:
        return FORMAT

    @property
    def streams(self) -> dict[str, StreamInfo]:
        if self._streams is None:
            out: dict[str, StreamInfo] = {}
            for name, store in self._stores.items():
                ids = store.channel_ids
                n_records_per_channel = int(np.sum(store.channels == ids[0]))
                out[name] = StreamInfo(
                    name=name,
                    n_channels=int(ids.size),
                    sfreq_hz=store.sfreq_hz,
                    n_samples=n_records_per_channel * store.samples_per_record,
                    dtype=str(store.dtype),
                    start_time_s=float(store.timestamps.min()),
                    channel_ids=tuple(str(int(c)) for c in ids),
                )
            self._streams = out
        return self._streams

    @property
    def epochs(self) -> dict[str, EpochSeries]:
        if self._epochs is None:
            idx = self._index
            out: dict[str, EpochSeries] = {}
            on_mask = idx["type"] == _TYPE_STRON
            for code in np.unique(idx["code"][on_mask]):
                name = code.decode("latin-1").rstrip("\x00").strip()
                if not name:
                    continue
                rows = idx[on_mask & (idx["code"] == code)]
                off = idx[(idx["type"] == _TYPE_STROFF) & (idx["code"] == code)]
                # For epochs the ev field carries a float64 value, not an offset.
                values = rows["ev"].view("<f8")
                out[name] = EpochSeries(
                    name=name,
                    onsets=rows["timestamp"].astype(np.float64) - self._t0(),
                    offsets=(
                        off["timestamp"].astype(np.float64) - self._t0()
                        if off.size
                        else np.empty(0)
                    ),
                    values=np.asarray(values, dtype=np.float64),
                )
            self._epochs = out
        return self._epochs

    def _t0(self) -> float:
        """Tank clock zero: the earliest timestamp in the index."""
        stamps = self._index["timestamp"]
        positive = stamps[stamps > 0]
        return float(positive.min()) if positive.size else 0.0

    @property
    def metadata(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "format": FORMAT,
            "n_index_records": int(self._index.size),
            "stores": sorted(self._stores),
        }
        if self.policy.filenames_deidentified:
            out["path_name"] = self.path.name
        out["restricted_fields_present"] = []
        return out

    def read_restricted_metadata(self) -> dict[str, Any]:
        """A tank's index carries no subject fields; the sidecar text files do."""
        return {}

    # ---- data ----------------------------------------------------------------

    def read(
        self,
        stream: str,
        channels: Sequence[int] | None = None,
        tmin: float | None = None,
        tmax: float | None = None,
    ) -> np.ndarray:
        if not self._tev.exists():
            raise FileNotFoundError(
                f"{self.path.name} has no matching .tev beside it, so structure is "
                "readable but samples are not. Sync the .tev, or use the .mat export "
                "if one exists."
            )
        try:
            store = self._stores[stream]
        except KeyError:
            raise KeyError(
                f"no stream {stream!r} in {self.path.name}; have {sorted(self._stores)}"
            ) from None

        info = self.streams[stream]
        start = 0 if tmin is None else self.time_to_sample(stream, tmin)
        stop = info.n_samples if tmax is None else self.time_to_sample(stream, tmax)
        if stop < start:
            raise ValueError(f"tmax ({tmax}) precedes tmin ({tmin}) for stream {stream!r}")

        ids = store.channel_ids
        if channels is None:
            wanted = list(range(len(ids)))
        else:
            wanted = [int(c) for c in channels]
            bad = [c for c in wanted if not 0 <= c < len(ids)]
            if bad:
                raise IndexError(
                    f"channels {bad} out of range for stream {stream!r} "
                    f"with {len(ids)} channels"
                )

        npts = store.samples_per_record
        first_rec, last_rec = start // npts, (stop - 1) // npts if stop > start else start // npts
        out = np.empty((len(wanted), stop - start), dtype=np.float64)

        with self._tev.open("rb") as fh:
            for row, ch_pos in enumerate(wanted):
                ch = int(ids[ch_pos])
                mask = store.channels == ch
                offsets = store.offsets[mask]
                order = np.argsort(store.timestamps[mask], kind="stable")
                offsets = offsets[order]
                lo = max(0, first_rec)
                hi = min(len(offsets) - 1, last_rec)
                chunks = []
                for r in range(lo, hi + 1):
                    fh.seek(int(offsets[r]))
                    buf = np.frombuffer(
                        fh.read(npts * store.dtype.itemsize), dtype=store.dtype
                    )
                    chunks.append(buf)
                joined = np.concatenate(chunks) if chunks else np.empty(0, store.dtype)
                begin = start - lo * npts
                out[row] = joined[begin : begin + (stop - start)]
        return out

    def close(self) -> None:
        return None


register_reader(FORMAT, TdtTankRecording, sniff, entry_suffixes=(".tsq",))
