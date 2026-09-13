"""Shared notebook generator. Each module declares cells; this emits both variants."""
from __future__ import annotations

import json
import pathlib

# Repository root, found from this file rather than hard-coded.
BASE = pathlib.Path(__file__).resolve().parents[2]
PUBLIC = BASE / "web" / "public" / "notebooks"

VARIANT_TAG = {"student": "[STUDENT WORKBOOK]", "solutions": "[SOLUTIONS GUIDE]"}
INSTRUCTIONS = {
    "student": (
        "> **STUDENT INSTRUCTIONS.** Each task cell raises `NotImplementedError`.\n"
        "> Replace the `TODO` comments with an implementation, then run the test cell\n"
        "> that follows. Every test cell checks your work against something independent\n"
        "> of your implementation, so passing means the result is right rather than\n"
        "> merely self-consistent. Work the cells in order.\n"
    ),
    "solutions": (
        "> **SOLUTIONS GUIDE.** Reference implementations with the same test cells the\n"
        "> student workbook uses. Executed in CI by `tests/unit/test_curriculum.py`.\n"
    ),
}


class Module:
    def __init__(self, track_dir: str, stem: str):
        self.track_dir = track_dir
        self.stem = stem
        self.cells: list[tuple[str, str, str | None]] = []

    def md(self, src):
        self.cells.append(("markdown", src, None))
        return self

    def code(self, src):
        self.cells.append(("code", src, None))
        return self

    def task(self, stu, sol):
        self.cells.append(("code", stu, sol))
        return self

    def _build(self, which: str) -> dict:
        out = []
        for i, (kind, stu, sol) in enumerate(self.cells):
            src = sol if (which == "solutions" and sol) else stu
            src = src.replace("{{VARIANT}}", VARIANT_TAG[which])
            src = src.replace("{{INSTRUCTIONS}}", INSTRUCTIONS[which])
            c = {"cell_type": kind, "id": f"cell-{i:02d}", "metadata": {},
                 "source": src.splitlines(keepends=True)}
            if kind == "code":
                c["execution_count"] = None
                c["outputs"] = []
            out.append(c)
        return {"cells": out,
                "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python",
                                            "name": "python3"},
                             "language_info": {"name": "python", "version": "3.12"}},
                "nbformat": 4, "nbformat_minor": 5}

    def emit(self):
        for which in ("student", "solutions"):
            nb = self._build(which)
            name = f"{self.stem}_{which}.ipynb"
            for d in (BASE / "curriculum" / self.track_dir, PUBLIC):
                d.mkdir(parents=True, exist_ok=True)
                (d / name).write_text(json.dumps(nb, indent=1) + "\n")
        print(f"  {self.stem}: {len(self.cells)} cells")


def verify(track_dir: str, stem: str) -> dict:
    """Execute the solutions notebook and return its namespace, or raise."""
    import matplotlib
    matplotlib.use("Agg")
    p = BASE / "curriculum" / track_dir / f"{stem}_solutions.ipynb"
    nb = json.loads(p.read_text())
    ns: dict = {}
    for i, c in enumerate(nb["cells"]):
        if c["cell_type"] != "code":
            continue
        try:
            exec("".join(c["source"]), ns)
        except Exception as e:
            raise SystemExit(f"!!! {stem} CELL {i} FAILED: {type(e).__name__}: {e}") from e
    return ns
