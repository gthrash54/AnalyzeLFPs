#!/usr/bin/env python
"""Generate docs/recipes.md from the registry.

Written rather than hand-maintained because a hand-maintained list of parameters
is wrong within a month and nobody can tell which half. `tests/unit/test_recipe_docs.py`
fails when the file on disk is not what this produces, so the choice is to
regenerate it or to notice.

    uv run python scripts/gen_recipe_docs.py          # write it
    uv run python scripts/gen_recipe_docs.py --check  # exit 1 if stale
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = REPO_ROOT / "docs" / "recipes.md"

HEADER = """# Recipes

Generated from the registry by `scripts/gen_recipe_docs.py`. Do not edit by hand;
edit the recipe and regenerate.

A recipe is declared once and becomes callable from Python, the CLI, the API, and
the agent. Every run goes through `registry.run`, which checks the QC gate,
evaluates guardrails before anything is computed, opens a run record, and writes
the outputs.

    python -m dbsspeech run <recipe> --subject <study_id> --claim "..." \\
        --set <param>=<value>

A parameter left unset uses the default in the table. Defaults shown as `null`
are resolved elsewhere, from a config file the recipe names in its description.
"""


def _type_of(prop: dict[str, Any]) -> str:
    """A readable type, flattening the anyOf that an optional field produces."""
    if "enum" in prop:
        return " | ".join(str(v) for v in prop["enum"])
    branches = [b for b in prop.get("anyOf", []) if b.get("type") != "null"]
    for branch in branches:
        if "enum" in branch:
            return " | ".join(str(v) for v in branch["enum"])
    if branches:
        kinds = []
        for branch in branches:
            kind = branch.get("type", "")
            if kind == "array":
                items = branch.get("items", {})
                kind = f"list[{items.get('type', 'any')}]"
            kinds.append(str(kind))
        return " | ".join(k for k in kinds if k)
    kind = prop.get("type", "")
    if kind == "array":
        return f"list[{prop.get('items', {}).get('type', 'any')}]"
    return str(kind)


def _default_of(prop: dict[str, Any]) -> str:
    if "default" not in prop:
        return "required"
    value = prop["default"]
    if value is None:
        return "null"
    if isinstance(value, str):
        return f"`{value}`" if value else "empty"
    return f"`{value}`"


def render() -> str:
    from dbsspeech.recipes import describe_all

    parts = [HEADER]
    recipes = describe_all()
    parts.append("\n## Registered\n")
    for spec in recipes:
        parts.append(f"- [`{spec['name']}`](#{spec['name']}) version "
                     f"{spec['version']}: {spec['description']}")
    parts.append("")

    for spec in recipes:
        parts.append(f"\n## {spec['name']}\n")
        parts.append(f"Version {spec['version']}. {spec['description']}\n")

        schema = spec.get("params_schema") or {}
        properties = schema.get("properties") or {}
        if properties:
            parts.append("| parameter | type | default | what it does |")
            parts.append("|---|---|---|---|")
            for name, prop in properties.items():
                description = str(prop.get("description", "")).replace("\n", " ").strip()
                parts.append(
                    f"| `{name}` | {_type_of(prop)} | {_default_of(prop)} | "
                    f"{description} |"
                )
            parts.append("")

        explanations = spec.get("option_explanations") or {}
        for group, options in explanations.items():
            parts.append(f"\n### {group}\n")
            for option in options:
                parts.append(f"- **{option['value']}** ({option.get('label', '')}): "
                             f"{option.get('description', '')}")
                if option.get("when_to_use"):
                    parts.append(f"  - when to use: {option['when_to_use']}")
                if option.get("caveat"):
                    parts.append(f"  - caveat: {option['caveat']}")
            parts.append("")

    return "\n".join(parts).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if docs/recipes.md is not what this generates")
    args = parser.parse_args(argv)

    generated = render()
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else ""
        if current != generated:
            print(f"{OUTPUT.relative_to(REPO_ROOT)} is stale. Regenerate it:\n"
                  "  uv run python scripts/gen_recipe_docs.py", file=sys.stderr)
            return 1
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(generated)
    print(f"wrote {OUTPUT.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
