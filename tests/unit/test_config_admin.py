"""Config admin: validation, history, and not rewriting the past."""

from __future__ import annotations

import pytest

from dbsspeech.configs_admin import (
    ConfigError,
    diff_versions,
    list_configs,
    list_versions,
    read_config,
    read_version,
    validate_config,
    write_config,
)

pytestmark = pytest.mark.unit

GOOD_BANDS = "bands:\n  beta: [13.0, 30.0]\n  high_gamma: [70.0, 150.0]\n"


@pytest.fixture
def workspace(tmp_path):
    configs = tmp_path / "configs"
    configs.mkdir()
    (configs / "bands.yaml").write_text(GOOD_BANDS)
    return configs, tmp_path / "history"


# ---- what is editable --------------------------------------------------------

def test_only_analysis_configs_are_editable():
    """leads is a device catalogue; privacy governs what may leave the machine."""
    names = {c["name"] for c in list_configs()}
    assert "bands" in names and "qc_thresholds" in names
    assert "leads" not in names
    assert "privacy" not in names


def test_editing_a_non_editable_config_is_refused():
    with pytest.raises(ConfigError, match="not editable"):
        read_config("privacy")


# ---- validation --------------------------------------------------------------

def test_invalid_yaml_says_why():
    with pytest.raises(ConfigError, match="not valid YAML"):
        validate_config("bands", "bands: [unclosed\n")


def test_a_band_with_inverted_edges_is_refused():
    with pytest.raises(ConfigError, match="at or below low edge"):
        validate_config("bands", "bands:\n  beta: [30, 13]\n")


def test_a_band_with_a_zero_low_edge_is_refused():
    with pytest.raises(ConfigError, match="above zero"):
        validate_config("bands", "bands:\n  dc: [0, 4]\n")


def test_a_non_numeric_band_edge_is_refused():
    with pytest.raises(ConfigError, match="must be numbers"):
        validate_config("bands", "bands:\n  beta: [low, high]\n")


def test_removing_a_guardrail_from_the_config_is_refused():
    """A guardrail absent from the config silently stops running."""
    from dbsspeech.guardrails import registered_checks

    partial = {"guardrails": {registered_checks()[0]: {"severity": "warn"}}}
    import yaml

    with pytest.raises(ConfigError, match="would stop running"):
        validate_config("guardrails", yaml.safe_dump(partial))


def test_an_unknown_guardrail_severity_lists_the_valid_ones():
    import yaml

    from dbsspeech.guardrails import registered_checks

    rails = {name: {"severity": "warn"} for name in registered_checks()}
    rails[registered_checks()[0]]["severity"] = "catastrophic"
    with pytest.raises(ConfigError, match="valid values"):
        validate_config("guardrails", yaml.safe_dump({"guardrails": rails}))


def test_a_statistics_option_missing_its_caveat_is_refused():
    """Those strings are shown beside the choice; an empty one teaches nothing."""
    import yaml

    from dbsspeech.stats import CENTERS, SCALES

    doc = {
        "centers": {c: {"label": c, "description": "d", "when_to_use": "w",
                        "caveat": "c"} for c in CENTERS},
        "scales": {s: {"label": s, "description": "d", "when_to_use": "w",
                       "caveat": "c"} for s in SCALES},
    }
    doc["scales"][SCALES[0]]["caveat"] = "   "
    with pytest.raises(ConfigError, match="caveat"):
        validate_config("statistics", yaml.safe_dump(doc))


def test_the_shipped_configs_all_validate():
    """Every editable config, not a list that goes stale when one is added.

    A shipped config its own checker refuses is not a small problem: the config
    admin screen refuses to save an edit to it, and the reason is a file nobody
    touched.
    """
    from dbsspeech.configs_admin.store import EDITABLE

    for name in EDITABLE:
        validate_config(name, read_config(name))


def test_an_erna_config_missing_a_setting_the_recipe_reads_is_refused():
    """Otherwise a run silently falls back to a value nobody chose."""
    text = read_config("erna").replace("blanking_ms: 4.0", "")
    with pytest.raises(ConfigError, match="window.blanking_ms"):
        validate_config("erna", text)


def test_an_inverted_erna_band_is_refused():
    text = read_config("erna").replace("low_hz: 100.0", "low_hz: 900.0")
    with pytest.raises(ConfigError, match="inverted or empty"):
        validate_config("erna", text)


def test_a_detector_without_words_a_reviewer_can_read_is_refused():
    """The review screen shows these instead of the detector's function name."""
    text = read_config("qc_thresholds").replace("    label: Spiky channel\n", "")
    with pytest.raises(ConfigError, match="kurtosis_outlier.*label"):
        validate_config("qc_thresholds", text)


def test_dropping_the_none_action_is_refused():
    """Without it nobody can keep a contact whose artifact is the signal."""
    text = read_config("qc_thresholds").replace(
        "  none:\n    label: Keep it as it is\n", "  removed:\n    label: x\n",
    )
    with pytest.raises(ConfigError, match="must include 'none'"):
        validate_config("qc_thresholds", text)


def test_a_detector_proposing_an_undeclared_action_is_refused():
    text = read_config("qc_thresholds").replace(
        "    proposed_action: notch", "    proposed_action: set_on_fire",
    )
    with pytest.raises(ConfigError, match="not one of the declared actions"):
        validate_config("qc_thresholds", text)


def test_claiming_the_erna_defaults_were_reviewed_needs_a_name():
    """The flag means a person who knows the protocol looked. Name them."""
    text = read_config("erna").replace("defaults_reviewed: false",
                                       "defaults_reviewed: true")
    with pytest.raises(ConfigError, match="reviewed_by"):
        validate_config("erna", text)


# ---- writing and history -----------------------------------------------------

def test_a_write_needs_an_author_and_a_reason(workspace):
    configs, history = workspace
    with pytest.raises(ConfigError, match="author"):
        write_config("bands", GOOD_BANDS, "", "why", configs, history)
    with pytest.raises(ConfigError, match="reason"):
        write_config("bands", GOOD_BANDS, "garrett", "  ", configs, history)


def test_a_write_archives_what_was_there_before(workspace):
    configs, history = workspace
    new = "bands:\n  beta: [13.0, 35.0]\n"
    write_config("bands", new, "garrett", "widened beta after review", configs, history)

    assert (configs / "bands.yaml").read_text() == new
    versions = list_versions("bands", history)
    assert len(versions) == 1
    assert read_version("bands", versions[0].path.stem, history) == GOOD_BANDS


def test_history_records_who_and_why(workspace):
    configs, history = workspace
    write_config("bands", GOOD_BANDS, "garrett", "no change, testing", configs, history)
    version = list_versions("bands", history)[0]
    assert version.author == "garrett"
    assert version.reason == "no change, testing"


def test_an_invalid_write_changes_nothing(workspace):
    configs, history = workspace
    with pytest.raises(ConfigError):
        write_config("bands", "bands:\n  beta: [30, 13]\n", "g", "oops", configs, history)
    assert (configs / "bands.yaml").read_text() == GOOD_BANDS
    assert list_versions("bands", history) == []


def test_the_response_says_a_change_does_not_rewrite_the_past(workspace):
    """Editing a threshold must not retroactively change an approved subject."""
    configs, history = workspace
    result = write_config("bands", GOOD_BANDS, "g", "r", configs, history)
    assert "already approved are unaffected" in result["applies_to"]


def test_diff_shows_what_changed(workspace):
    configs, history = workspace
    write_config("bands", "bands:\n  beta: [13.0, 35.0]\n", "g", "widened",
                 configs, history)
    version = list_versions("bands", history)[0]
    diff = diff_versions("bands", version.path.stem, configs, history)
    assert "-  beta: [13.0, 30.0]" in diff
    assert "+  beta: [13.0, 35.0]" in diff


def test_versions_are_newest_first(workspace):
    import time

    configs, history = workspace
    for i in range(2):
        write_config("bands", f"bands:\n  beta: [13.0, {30 + i}.0]\n",
                     "g", f"change {i}", configs, history)
        time.sleep(1.05)
    versions = list_versions("bands", history)
    assert len(versions) == 2
    assert versions[0].saved_at >= versions[1].saved_at
