"""Dump a lesson's prose numbers beside the numbers its code actually prints.

Usage:  MPLBACKEND=Agg uv run python curriculum/tools/audit_prose_numbers.py <stem> [...]
        MPLBACKEND=Agg uv run python curriculum/tools/audit_prose_numbers.py --list

One invocation per module. Prints three blocks: PROSE NUMBERS (every numeric
token in markdown cells, with context), PRINTED NUMBERS (every numeric token in
captured stdout), and PROSE-ONLY (prose numbers with no close match in stdout),
which is where the discrepancies live. Judge PROSE-ONLY by hand: section
numbers, years, band edges and config values are expected there.
"""
import contextlib
import io
import json
import pathlib
import re
import sys

import matplotlib

matplotlib.use("Agg")


REPO = pathlib.Path(__file__).resolve().parents[2]
CURR = REPO / "curriculum"

NUM = re.compile(r"-?\d+\.?\d*")


def find(stem):
    hits = sorted(CURR.rglob(f"{stem}*_solutions.ipynb"))
    if not hits:
        sys.exit(f"no solutions notebook matching {stem!r}")
    return hits[0]


def numbers(text):
    return {float(m) for m in NUM.findall(text) if m not in {"-", "."}}


def close(v, pool, rel=0.02):
    return any(abs(v - p) <= max(rel * abs(v), 1e-9) for p in pool)


def main(stems):
    for stem in stems:
        path = find(stem)
        nb = json.loads(path.read_text())
        md = [
            "".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown"
        ]
        code = ["".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code"]

        buf, ns, err = io.StringIO(), {}, None
        with contextlib.redirect_stdout(buf):
            for cell in code:
                try:
                    exec(cell, ns)
                except Exception as exc:  # noqa: BLE001 - reporting, not handling
                    err = f"{type(exc).__name__}: {exc}"
                    break
        out = buf.getvalue()

        print("=" * 78)
        print(f"MODULE {path.name}")
        if err:
            print(f"!!! EXECUTION FAILED: {err}")
        print("=" * 78)
        print("\n--- PRINTED (stdout) ---")
        print(out.strip()[:6000])

        printed = numbers(out)
        print("\n--- PROSE NUMBERS NOT PRINTED BY THE CODE ---")
        print("(section numbers, config values and band edges belong here; a")
        print(" measured-sounding claim does not)")
        for cell in md:
            for line in cell.split("\n"):
                vals = [v for v in numbers(line) if not close(v, printed)]
                # Ignore bare small integers: list markers, section numbers, years.
                vals = [v for v in vals if not (v == int(v) and abs(v) <= 12)]
                if vals:
                    print(f"  {sorted(vals)}  <-  {line.strip()[:150]}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] == "--list":
        for p in sorted(CURR.rglob("*_solutions.ipynb")):
            print(p.relative_to(CURR))
        sys.exit()
    main(args)
