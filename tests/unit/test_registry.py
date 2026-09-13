"""Recipe registry: registration, schema export, and lookup errors.

The orchestration path (guardrails, run record, outputs) is exercised once a real
recipe exists; these cover the registry's own contract.
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel, Field

from dbsspeech.recipes import registry

pytestmark = pytest.mark.unit


class DemoParams(BaseModel):
    fmin: float = Field(default=1.0, description="low edge, Hz")
    method: str = "welch"


@pytest.fixture
def clean_registry():
    saved = dict(registry._RECIPES)
    registry._RECIPES.clear()
    try:
        yield registry
    finally:
        registry._RECIPES.clear()
        registry._RECIPES.update(saved)


def test_registration_makes_a_recipe_available(clean_registry):
    @clean_registry.recipe("demo", "a demo", DemoParams)
    def _demo(ctx):
        return clean_registry.RecipeResult()

    assert clean_registry.available() == ("demo",)
    assert clean_registry.get("demo").description == "a demo"


def test_duplicate_registration_is_refused(clean_registry):
    @clean_registry.recipe("demo", "first", DemoParams)
    def _a(ctx):
        return clean_registry.RecipeResult()

    with pytest.raises(ValueError, match="already registered"):

        @clean_registry.recipe("demo", "second", DemoParams)
        def _b(ctx):
            return clean_registry.RecipeResult()


def test_unknown_recipe_lists_the_registered_ones(clean_registry):
    @clean_registry.recipe("demo", "a demo", DemoParams)
    def _demo(ctx):
        return clean_registry.RecipeResult()

    with pytest.raises(KeyError, match="registered"):
        clean_registry.get("nope")


def test_schema_export_drives_the_ui_form(clean_registry):
    """describe_all is what the web app builds parameter forms from."""

    @clean_registry.recipe("demo", "a demo", DemoParams, version="2")
    def _demo(ctx):
        return clean_registry.RecipeResult()

    described = clean_registry.describe_all()[0]
    assert described["name"] == "demo"
    assert described["version"] == "2"
    props = described["params_schema"]["properties"]
    assert props["fmin"]["default"] == 1.0
    assert props["fmin"]["description"] == "low edge, Hz"


def test_recipe_version_defaults_to_one(clean_registry):
    @clean_registry.recipe("demo", "a demo", DemoParams)
    def _demo(ctx):
        return clean_registry.RecipeResult()

    assert clean_registry.get("demo").version == "1"


@pytest.mark.unit
def test_window_span_is_the_elapsed_time_not_the_sum_of_windows():
    """G9's excursion ratio needs the duration it was measured over.

    An excursion grows with elapsed time whenever the baseline is closer to a
    random walk than to a bounded process, which STO 3 measured at 1.6*sqrt(t).
    So the same physiology gives a larger ratio in a longer recording and the
    ratio is not comparable between runs without the duration beside it.

    The span, not the sum: drift accumulates during the gaps between windows as
    well as inside them.
    """
    rows = [
        {"t_start_s": "10.0", "t_end_s": "20.0"},
        {"t_start_s": "100.0", "t_end_s": "110.0"},
    ]
    assert registry._window_span_s(rows) == 100.0, (
        "10 to 110 is a span of 100 s, even though the windows total 20"
    )


@pytest.mark.unit
def test_window_span_declines_to_guess_when_the_times_are_unusable():
    """A message quoting a fabricated duration is worse than one quoting none."""
    assert registry._window_span_s([]) is None
    assert registry._window_span_s([{"t_start_s": "0.0"}]) is None, "missing end"
    assert registry._window_span_s([{"t_start_s": "", "t_end_s": "5.0"}]) is None, "blank"
    assert registry._window_span_s([{"t_start_s": "a", "t_end_s": "5.0"}]) is None, "not a number"
    assert registry._window_span_s(
        [{"t_start_s": "5.0", "t_end_s": "5.0"}]
    ) is None, "a zero-length span is not a duration"


@pytest.mark.unit
def test_a_post_run_pass_does_not_block_a_result_that_already_exists():
    """Refusing after the recipe has run would leave a half-written record.

    G9 compares a baseline excursion to the effect a run reports, and neither
    exists before the recipe produces one. So it is evaluated in a second pass
    afterwards, and that pass reports rather than raises: the computation has
    already happened and blocking would not un-do it.
    """
    from dbsspeech.guardrails import CheckContext, GuardrailBlocked, run_checks

    config = {"guardrails": {"G9_nonstationarity_exceeds_effect": {
        "severity": "block", "excursion_to_effect_ratio": 1.0}}}
    ctx = CheckContext(recipe="x", params={}, conditions=(), window_rows=[])
    ctx.max_excursion_db, ctx.reported_effect_db = 4.0, 1.0

    with pytest.raises(GuardrailBlocked):
        run_checks(ctx, config)

    findings, _ = run_checks(ctx, config, blocking=False)
    assert [f.guardrail for f in findings] == ["G9_nonstationarity_exceeds_effect"], (
        "the finding is still reported, it just does not raise"
    )
