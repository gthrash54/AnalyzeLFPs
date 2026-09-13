"""Condition detection in the agent, which is driven by the vocabulary config.

The point of these tests is that no paradigm term is written into Python. The
agent used to special-case the word "speech"; it now reads aliases from
`configs/vocabularies.yaml`, so a lab running a motor, cognitive or stimulation
paradigm extends a config file rather than this module.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dbsspeech.agent.propose import propose

pytestmark = pytest.mark.unit

CONFIG_DIR = Path("configs")


@pytest.fixture(scope="module")
def configs():
    return {
        "vocabularies": yaml.safe_load((CONFIG_DIR / "vocabularies.yaml").read_text()),
        "bands": yaml.safe_load((CONFIG_DIR / "bands.yaml").read_text()),
    }


class FakeSession:
    """The surface `propose` uses: conditions, leads, and windows."""

    def __init__(self, conditions: tuple[str, ...]) -> None:
        self._conditions = conditions

    def conditions(self):
        return self._conditions

    def leads(self):
        return {}

    def windows(self):
        return [
            {"condition": c, "status": "in_use", "derived_from": "task_marker"}
            for c in self._conditions
        ]


def _conditions_for(question: str, available: tuple[str, ...], configs) -> list[str]:
    proposal = propose(question, session=FakeSession(available), configs=configs)
    return proposal.params.get("conditions") or []


def test_a_condition_named_outright_is_matched(configs):
    got = _conditions_for("beta during overt", ("overt", "rest"), configs)
    assert got == ["overt"]


def test_speech_resolves_through_the_vocabulary_not_through_code(configs):
    got = _conditions_for("beta in the STN during speech", ("overt", "metro"), configs)
    assert got == ["overt"]


def test_a_longer_alias_wins_over_a_shorter_one(configs):
    """'imagined speech' is inner speech, not overt speech plus a modifier."""
    got = _conditions_for("beta during imagined speech", ("overt", "inner"), configs)
    assert got == ["inner"]


def test_a_motor_paradigm_resolves(configs):
    got = _conditions_for("beta during movement vs baseline", ("move", "rest"), configs)
    assert sorted(got) == ["move", "rest"]


def test_a_stimulation_contrast_resolves(configs):
    got = _conditions_for(
        "gamma during stim on vs stim off", ("dbs_on", "dbs_off"), configs
    )
    assert sorted(got) == ["dbs_off", "dbs_on"]


def test_a_cognitive_paradigm_resolves(configs):
    got = _conditions_for("beta during working memory", ("task", "rest"), configs)
    assert got == ["task"]


def test_an_alias_never_proposes_a_condition_the_session_lacks(configs):
    """The manifest decides what exists; the vocabulary only names things."""
    got = _conditions_for("beta during speech", ("move", "rest"), configs)
    assert "overt" not in got


def test_the_reasoning_says_which_phrase_produced_the_condition(configs):
    proposal = propose(
        "beta during speech", session=FakeSession(("overt", "metro")), configs=configs
    )
    why = " ".join(p.reason for p in proposal.reasoning if p.name == "conditions")
    assert "speech" in why
    assert "overt" in why


def test_conditions_are_absent_when_nothing_matches(configs):
    got = _conditions_for("beta in the STN", ("overt", "rest"), configs)
    assert got == []


def test_a_vocabulary_without_aliases_still_works(configs):
    """The terse `{label, description}` entry shape remains valid config."""
    terse = {
        "vocabularies": {
            "conditions": {
                "overt": {"label": "Overt speech", "description": "aloud"},
                "rest": {"label": "Rest", "description": "quiet"},
            }
        }
    }
    got = _conditions_for("beta during overt", ("overt", "rest"), terse)
    assert got == ["overt"]
