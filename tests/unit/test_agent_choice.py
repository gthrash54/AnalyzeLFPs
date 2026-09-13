"""The agent choosing a recipe, and re-checking values a person edited.

Both exist for the guided run flow: the first turns "what do you want to find
out" into a recipe, the second makes the review step honest by dry-running the
guardrails against what is actually about to run.
"""

from __future__ import annotations

import pytest

from dbsspeech.agent.propose import choose_recipe, propose
from dbsspeech.recipes import available

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("is beta higher during speech than during rest", "bandpower_contrast"),
        ("how big is the resonance after each stimulation pulse", "erna"),
        ("how does power change over time around speech onset", "tfr_onset"),
        ("what does the spectrum look like in each condition", "psd_by_condition"),
    ],
)
def test_a_question_reaches_the_recipe_that_answers_it(question, expected):
    assert choose_recipe(question)[0] == expected


def test_the_choice_says_what_it_matched_on():
    """A choice whose basis is invisible is one nobody can correct."""
    _, reason = choose_recipe("how fast does the resonance decay after stimulation")
    assert "matched on" in reason
    assert "resonance" in reason or "stimulation" in reason or "decay" in reason


def test_an_empty_question_falls_back_and_says_so():
    name, reason = choose_recipe("")
    assert name == "psd_by_condition"
    assert "starting point" in reason


def test_a_question_about_nothing_in_particular_falls_back():
    name, reason = choose_recipe("please do the thing with the wibble")
    assert name in available()
    assert "starting point" in reason


def test_a_named_band_beats_a_generic_verb():
    """The case that changed the scoring.

    Scored on word length, "change" (6) outweighed "beta" (4) and this question
    reached tfr_onset, 11 to 9. A person who names a frequency band has told you
    which analysis they want. Inverse document frequency says so: "beta" appears
    in one recipe's own sentence, "change" in one, "power" in three, and the
    weights follow from that rather than from spelling.
    """
    name, reason = choose_recipe("does beta power change during overt speech compared to rest")
    assert name == "bandpower_contrast"
    assert reason.startswith("matched on beta")


def test_a_plural_still_finds_the_singular():
    """"conditions" reaching "condition" is not a hard question, and asked in the
    plural it used to match nothing at all and fall back silently."""
    name, reason = choose_recipe("is high gamma different between conditions")
    assert name in available()
    assert "starting point" not in reason
    assert "condition" in reason


def test_every_offered_example_reaches_its_own_recipe():
    """The examples on the Run screen are the first thing a student clicks, so a
    mismatch there is the worst possible first impression. Each one is worded
    from a recipe's own question; each must come back to it."""
    for question, expected in [
        ("Is beta higher during overt speech than during rest?", "bandpower_contrast"),
        ("What does the spectrum look like in each condition?", "psd_by_condition"),
        ("How does power change over time around speech onset?", "tfr_onset"),
        ("How large is the ringing after each stimulation pulse?", "erna"),
    ]:
        assert choose_recipe(question)[0] == expected, question


def test_choosing_is_recorded_on_the_proposal():
    proposal = propose("is beta higher during speech than rest", recipe=None)
    assert proposal.recipe == "bandpower_contrast"
    assert "matched on" in proposal.understood["recipe_reason"]


def test_naming_a_recipe_skips_the_choosing():
    proposal = propose("anything at all", recipe="tfr_onset")
    assert proposal.recipe == "tfr_onset"
    assert "recipe_reason" not in proposal.understood


# ---- values a person set ---------------------------------------------------------

def test_a_value_you_set_wins_over_one_the_agent_inferred():
    """Otherwise the review step would quietly undo the edit it is showing you."""
    inferred = propose("look at beta", recipe="psd_by_condition")
    assert inferred.params["fmax"] == 30.0

    mine = propose("look at beta", recipe="psd_by_condition", params={"fmax": 90.0})
    assert mine.params["fmax"] == 90.0


def test_a_value_you_set_is_explained_as_yours():
    proposal = propose("", recipe="psd_by_condition", params={"fmax": 90.0})
    reason = next(r for r in proposal.reasoning if r.name == "fmax")
    assert reason.confidence == "yours"
    assert reason.reason == "you set this"


def test_setting_a_value_replaces_the_agents_reasoning_for_it():
    """Two rows for one parameter, disagreeing, is worse than none."""
    proposal = propose("look at beta", recipe="psd_by_condition", params={"fmax": 90.0})
    assert len([r for r in proposal.reasoning if r.name == "fmax"]) == 1


def test_parameters_the_recipe_would_refuse_come_back_as_a_question():
    """Better here than after the button: the review step is where surprises end."""
    proposal = propose("", recipe="psd_by_condition", params={"method": "not_a_method"})
    assert any("would be refused" in q for q in proposal.questions)


def test_an_unknown_recipe_is_reported_rather_than_raised():
    proposal = propose("", recipe="no_such_recipe")
    assert any("not a registered recipe" in q for q in proposal.questions)


# ---- fields somebody emptied -------------------------------------------------------

def test_a_cleared_field_is_not_inferred_again():
    """Emptying a field is a decision. Filling it back in overrules it."""
    inferred = propose("look at beta", recipe="psd_by_condition")
    assert inferred.params["fmax"] == 30.0

    after = propose("look at beta", recipe="psd_by_condition", cleared=["fmax"])
    assert "fmax" not in after.params
    # And only that one: clearing is per field, not a reset.
    assert after.params["fmin"] == 13.0


def test_a_cleared_field_says_the_recipe_default_applies():
    proposal = propose("look at beta", recipe="psd_by_condition", cleared=["fmax"])
    reason = next(r for r in proposal.reasoning if r.name == "fmax")
    assert reason.confidence == "cleared"
    assert "recipe's own default" in reason.reason
    assert reason.value is None


def test_clearing_wins_over_a_value_sent_in_the_same_breath():
    """The form sends both while a field is mid-edit; the clear is the later act."""
    proposal = propose(
        "look at beta", recipe="psd_by_condition",
        params={"fmax": 90.0}, cleared=["fmax"],
    )
    assert "fmax" not in proposal.params


def test_clearing_something_never_set_is_harmless():
    proposal = propose("", recipe="psd_by_condition", cleared=["window_s"])
    assert "window_s" not in proposal.params


def test_the_dry_run_still_happens_for_edited_values():
    """The point of re-checking: a block is found before the run, not after."""
    proposal = propose(
        "", recipe="psd_by_condition", params={"primary_reference": "monopolar"}
    )
    assert proposal.blocked
    assert any("G1" in g["guardrail"] for g in proposal.guardrails)
