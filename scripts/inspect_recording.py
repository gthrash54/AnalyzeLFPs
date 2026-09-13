"""Throwaway inspector for an unfamiliar recording file.

Reports structure only: group and dataset names, shapes, dtypes, and small
numeric attributes. Deliberately does NOT print the contents of anything that
could carry an identifier; for such fields it reports the field name, dtype, and
length so a de-identification step can be planned without reproducing the text.

Reads metadata and tiny slices only, so it is safe on a multi-gigabyte file.

Usage:
    uv run python scripts/inspect_recording.py <path> [--max-depth N]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Field names whose values may carry identifiers. Names are printed, values never.
SENSITIVE_HINTS = (
    "subject", "name", "patient", "mrn", "dob", "birth", "id",
    "date", "time", "start", "stop", "comment", "note", "experiment",
)


def _is_sensitive(name: str) -> bool:
    low = name.lower()
    return any(h in low for h in SENSITIVE_HINTS)


def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def inspect_hdf5(path: Path, max_depth: int) -> None:
    import h5py

    with h5py.File(path, "r") as f:
        print(f"HDF5: {path.name}")
        print(f"file size: {_fmt_bytes(path.stat().st_size)}")
        root_attrs = dict(f.attrs)
        if root_attrs:
            print(f"root attrs: {sorted(root_attrs)}")
        print()

        def walk(name: str, obj, depth: int) -> None:
            if depth > max_depth:
                return
            pad = "  " * depth
            short = name.rsplit("/", 1)[-1] or "/"
            if hasattr(obj, "shape"):  # Dataset
                size = obj.dtype.itemsize
                for d in obj.shape:
                    size *= d
                line = f"{pad}{short:<20} shape={obj.shape} dtype={obj.dtype} ({_fmt_bytes(size)})"
                print(line)
                # Small numeric datasets are structural (rates, counts): show them.
                # Anything possibly textual or identifying: describe, never print.
                n = 1
                for d in obj.shape:
                    n *= d
                if _is_sensitive(short):
                    print(f"{pad}  [value withheld: name suggests a possible identifier]")
                elif n <= 4 and obj.dtype.kind in "fiu":
                    try:
                        print(f"{pad}  value: {obj[()]!r}")
                    except Exception as exc:  # pragma: no cover
                        print(f"{pad}  (unreadable: {exc})")
                elif obj.dtype.kind in "fiu" and n > 4:
                    try:
                        head = obj[(0,) * (obj.ndim - 1)][:3] if obj.ndim > 1 else obj[:3]
                        print(f"{pad}  first values along last axis: {list(head)}")
                    except Exception:
                        pass
            else:  # Group
                print(f"{pad}{short}/")
                for key in obj:
                    walk(f"{name}/{key}", obj[key], depth + 1)

        for key in f:
            walk(key, f[key], 0)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--max-depth", type=int, default=4)
    args = ap.parse_args()
    if not args.path.exists():
        print(f"no such file: {args.path}", file=sys.stderr)
        return 1
    inspect_hdf5(args.path, args.max_depth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
