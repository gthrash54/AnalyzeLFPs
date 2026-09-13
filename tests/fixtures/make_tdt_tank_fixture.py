"""Write a synthetic TDT tank: a `.tsq` index and its `.tev` data file.

Byte-for-byte the layout a real tank uses, so a round trip through the reader
exercises the same code path real data does. Nothing here is derived from a
recording; the layout was established by reading one.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

TYPE_STREAM = 0x8101
TYPE_STRON = 0x101
HEADER_WORDS = 10

SFREQ = 1000.0
N_CHANNELS = 4
SAMPLES_PER_RECORD = 64
N_RECORDS = 20  # per channel
SEED = 0

STORE = b"neur"
EPOC = b"Cam1"


def make_tank(directory: Path, name: str = "synthetic") -> Path:
    """Write `<name>.tsq` and `<name>.tev`. Returns the .tsq path."""
    directory.mkdir(parents=True, exist_ok=True)
    tsq_path = directory / f"{name}.tsq"
    tev_path = directory / f"{name}.tev"

    rng = np.random.default_rng(SEED)
    total = SAMPLES_PER_RECORD * N_RECORDS
    # A distinct ramp per channel, so a mis-assembled read is obvious rather than
    # merely wrong: channel c holds c*1e6 + sample index.
    data = np.stack(
        [np.arange(total, dtype=np.float32) + c * 1_000_000 for c in range(N_CHANNELS)]
    )
    data += rng.standard_normal(data.shape).astype(np.float32) * 1e-3

    records: list[bytes] = []
    tev = bytearray()

    def pack(size, type_, code, channel, sortcode, timestamp, ev, fmt, freq):
        return struct.pack(
            "<iI4sHHdqif", size, type_, code, channel, sortcode, timestamp, ev, fmt, freq
        )

    # Streams: records interleaved by channel within each time block, as TDT writes.
    for r in range(N_RECORDS):
        t = r * SAMPLES_PER_RECORD / SFREQ
        for c in range(N_CHANNELS):
            offset = len(tev)
            chunk = data[c, r * SAMPLES_PER_RECORD : (r + 1) * SAMPLES_PER_RECORD]
            tev.extend(chunk.tobytes())
            records.append(
                pack(SAMPLES_PER_RECORD + HEADER_WORDS, TYPE_STREAM, STORE,
                     c + 1, 0, t, offset, 0, SFREQ)
            )

    # Epochs: the ev field carries a float64 value rather than an offset.
    for i in range(5):
        records.append(
            pack(HEADER_WORDS, TYPE_STRON, EPOC, 1, 0, i * 0.25,
                 struct.unpack("<q", struct.pack("<d", float(i + 1)))[0], 0, 0.0)
        )

    tsq_path.write_bytes(b"".join(records))
    tev_path.write_bytes(bytes(tev))
    return tsq_path


def expected_channel(channel: int, start: int, stop: int) -> np.ndarray:
    """The ramp the fixture planted, for comparison in tests."""
    return np.arange(start, stop, dtype=np.float64) + channel * 1_000_000


if __name__ == "__main__":
    out = make_tank(Path(__file__).parent / "tank")
    print(f"wrote {out} and {out.with_suffix('.tev')}")
