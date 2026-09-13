"""Resolving `filenames_deidentified`, which is declared per format.

The setting gates guardrail G13, which refuses to let a raw path reach a
derivative and is not overridable. Two code paths read it: `PrivacyPolicy`,
which decides whether a reader surfaces a filename, and the PSD recipe, which
builds the guardrail context. These tests exist to keep those two answering the
same question, because the way they would diverge is silent: `bool()` of a
non-empty per-format mapping is True, which would pass G13 for every format at
once.
"""

from __future__ import annotations

import pytest
import yaml

from dbsspeech.io import PrivacyPolicy, filenames_deidentified_for

pytestmark = pytest.mark.unit

CONFIG_PATH = "configs/privacy.yaml"


def test_a_plain_boolean_applies_to_every_format():
    config = {"filenames_deidentified": True}
    assert filenames_deidentified_for(config, "tdt_mat") is True
    assert filenames_deidentified_for(config, "brainvision") is True


def test_a_mapping_answers_per_format():
    config = {"filenames_deidentified": {"tdt_mat": True, "brainvision": False}}
    assert filenames_deidentified_for(config, "tdt_mat") is True
    assert filenames_deidentified_for(config, "brainvision") is False


def test_a_format_absent_from_the_mapping_is_not_declared_safe():
    """Registering a reader must never silently opt its filenames in."""
    config = {"filenames_deidentified": {"tdt_mat": True}}
    assert filenames_deidentified_for(config, "some_new_format") is False


def test_a_missing_setting_is_not_declared_safe():
    assert filenames_deidentified_for({}, "tdt_mat") is False


def test_a_mapping_is_never_read_as_one_blanket_true():
    """The specific failure this resolver exists to prevent.

    `bool({"tdt_mat": True})` is True. A caller doing that would hand G13 a
    True for a format the site never declared safe.
    """
    config = {"filenames_deidentified": {"tdt_mat": True}}
    assert bool(config["filenames_deidentified"]) is True
    assert filenames_deidentified_for(config, "brainvision") is False


def test_the_policy_carries_the_resolved_value():
    config = {
        "filenames_deidentified": {"tdt_mat": True, "brainvision": False},
        "restricted_metadata_fields": {"brainvision": ["subject_info"]},
    }
    assert PrivacyPolicy.from_mapping(config, "tdt_mat").filenames_deidentified is True

    brainvision = PrivacyPolicy.from_mapping(config, "brainvision")
    assert brainvision.filenames_deidentified is False
    assert brainvision.restricted_metadata_fields == frozenset({"subject_info"})


def test_the_shipped_config_withholds_filenames_for_the_mne_formats():
    """The archive's BrainVision filenames embed an acquisition date."""
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    assert filenames_deidentified_for(config, "brainvision") is False
    assert filenames_deidentified_for(config, "edf") is False


def test_the_shipped_config_refuses_tdt_filenames_too():
    """No format is exempt, because the TDT timestamp is an acquisition time.

    This test previously asserted the opposite, on the config's own claim that
    the timestamp embedded in a TDT filename was an upload time recorded on a
    day deliberately separated from the procedure. That claim was measured
    against the archive on 2026-09-09 and is false: of 401 staged tanks, the
    YYMMDD field matched the acquisition date in the block's own Notes.txt
    exactly 287 times and differed by one day 114 times, with none consistent
    with a separate upload day.

    Guardrail G13 takes its effective severity from this setting and is not
    overridable, so a true here would hand a privacy check a blanket pass.
    """
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    assert filenames_deidentified_for(config, "tdt_mat") is False
    assert filenames_deidentified_for(config, "tdt_tank") is False
