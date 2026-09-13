"""docs/recipes.md is generated, so it can go stale. This is what notices.

A hand-checked list of parameters is wrong within a month and nobody can tell
which half. The generator is the source; this test is the alarm.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "gen_recipe_docs.py"


def _generator():
    """Load the script as a module. It is a script, not an installed entry point."""
    spec = importlib.util.spec_from_file_location("gen_recipe_docs", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["gen_recipe_docs"] = module
    spec.loader.exec_module(module)
    return module


def test_the_generated_recipe_docs_are_current():
    generator = _generator()
    expected = generator.render()
    actual = generator.OUTPUT.read_text() if generator.OUTPUT.exists() else ""
    assert actual == expected, (
        "docs/recipes.md does not match the registry. Regenerate it:\n"
        "  uv run python scripts/gen_recipe_docs.py"
    )


def test_every_registered_recipe_is_documented():
    from dbsspeech.recipes import available

    text = _generator().OUTPUT.read_text()
    for name in available():
        assert f"## {name}" in text, f"{name} is registered but not in docs/recipes.md"


def test_the_check_flag_agrees_with_the_file_on_disk():
    assert _generator().main(["--check"]) == 0


def test_every_parameter_reaches_the_table():
    """A parameter nobody documented is a parameter nobody sets."""
    from dbsspeech.recipes import describe_all

    text = _generator().OUTPUT.read_text()
    for spec in describe_all():
        for name in (spec.get("params_schema") or {}).get("properties", {}):
            assert f"`{name}`" in text, f"{spec['name']}.{name} is not documented"
