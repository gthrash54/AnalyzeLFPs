"""Guardrail engine semantics and each implemented check."""

from __future__ import annotations

import pytest

from dbsspeech.guardrails import (
    CheckContext,
    GuardrailBlocked,
    Override,
    Severity,
    load_config,
    registered_checks,
    run_checks,
    summarize,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def config():
    return load_config()


def _clean() -> CheckContext:
    """A context that should fire nothing."""
    return CheckContext(
        recipe="psd_by_condition",
        reference_scheme="bipolar_vertical",
        reference_is_shared=True,
        sfreq_hz=8138.0,
        usable_bandwidth_hz=3255.2,
        requested_bands={"beta": (13.0, 30.0), "high_gamma": (70.0, 150.0)},
        window_s=1.0,
        conditions=("overt", "metro", "rest"),
        reports_db=True,
        reports_z=True,
        baseline_is_smoothed=False,
        per_contact_baseline_subtracted=True,
        # A clean run is one that already did the right thing, not one that was
        # never asked. High gamma during overt speech overlaps the EMG band, so
        # a run that fires nothing must have a bipolar montage and EMG regressed.
        ratio_before_average=True,
        threshold_within_condition=True,
        emg_available=True,
        emg_regressed=True,
        filenames_deidentified=True,
    )


# ---- engine semantics --------------------------------------------------------

def test_a_clean_run_fires_nothing(config):
    findings, overrides = run_checks(_clean(), config)
    assert findings == []
    assert overrides == []


def test_blocking_check_refuses_before_computing(config):
    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    with pytest.raises(GuardrailBlocked) as exc:
        run_checks(ctx, config)
    assert "Nothing was computed" in str(exc.value)


def test_block_message_explains_and_names_the_override(config):
    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    with pytest.raises(GuardrailBlocked) as exc:
        run_checks(ctx, config)
    text = str(exc.value)
    assert "common-mode" in text, "must say why it matters"
    assert "what to do" in text, "must say what to do instead"
    assert "override:" in text, "must name the override"


def test_override_with_a_reason_proceeds_and_is_recorded(config):
    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    findings, used = run_checks(
        ctx, config, overrides={"G1_shared_reference_common_mode": "montage comparison"}
    )
    assert [o.reason for o in used] == ["montage comparison"]
    assert any(f.severity is Severity.BLOCK for f in findings)


def test_override_without_a_reason_is_refused():
    with pytest.raises(ValueError, match="needs a reason"):
        Override("G1_shared_reference_common_mode", "   ")


def test_arithmetic_checks_cannot_be_overridden(config):
    """G6 is not a judgment call, so an override must not get past it."""
    ctx = _clean()
    ctx.requested_bands = {"mua": (1000.0, 3000.0)}
    ctx.usable_bandwidth_hz = 813.8
    with pytest.raises(GuardrailBlocked) as exc:
        run_checks(ctx, config, overrides={"G6_decimation_removes_claimed_band": "please"})
    assert "NOT overridable" in str(exc.value)


def test_a_check_switched_off_in_config_does_not_run():
    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    findings, _ = run_checks(
        ctx, {"guardrails": {"G1_shared_reference_common_mode": {"severity": "off"}}}
    )
    assert "G1_shared_reference_common_mode" not in [f.guardrail for f in findings]


def test_severity_comes_from_config_not_from_the_check():
    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    findings, _ = run_checks(
        ctx, {"guardrails": {"G1_shared_reference_common_mode": {"severity": "note"}}}
    )
    g1 = next(f for f in findings if f.guardrail == "G1_shared_reference_common_mode")
    assert g1.severity is Severity.NOTE


def test_summary_is_what_a_run_record_stores(config):
    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    findings, used = run_checks(
        ctx, config, overrides={"G1_shared_reference_common_mode": "comparison"}
    )
    block = summarize(findings, used)
    assert block["overrides"] == [
        {"guardrail": "G1_shared_reference_common_mode", "reason": "comparison"}
    ]
    assert block["checks_run"] == list(registered_checks())


# ---- individual checks -------------------------------------------------------

def test_g1_ignores_monopolar_when_the_reference_is_not_shared(config):
    """Scoped to G1. Monopolar also trips G7, correctly, which is a separate concern."""
    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    ctx.reference_is_shared = False
    findings, _ = run_checks(ctx, config)
    assert "G1_shared_reference_common_mode" not in [f.guardrail for f in findings]


def test_monopolar_during_speech_trips_both_reference_and_emg_checks(config):
    """Two different real concerns: common mode, and muscle in the high band."""
    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    findings, _ = run_checks(
        ctx, config, overrides={"G1_shared_reference_common_mode": "montage comparison"}
    )
    fired = {f.guardrail for f in findings}
    assert "G1_shared_reference_common_mode" in fired
    assert "G7_emg_contamination_in_high_band" in fired


def test_g5_fires_when_the_window_dwarfs_the_event(config):
    ctx = _clean()
    ctx.window_s, ctx.claimed_event_duration_s = 2.0, 0.063
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G5_window_longer_than_phenomenon"]


def test_g5_quiet_when_the_window_suits_the_event(config):
    ctx = _clean()
    ctx.window_s, ctx.claimed_event_duration_s = 1.0, 0.5
    assert run_checks(ctx, config)[0] == []


def test_g6_names_only_the_offending_bands(config):
    ctx = _clean()
    ctx.usable_bandwidth_hz = 813.8
    ctx.requested_bands = {"beta": (13.0, 30.0), "mua": (1000.0, 3000.0)}
    with pytest.raises(GuardrailBlocked) as exc:
        run_checks(ctx, config)
    detail = exc.value.findings[0].detail["bands_above_cutoff"]
    assert set(detail) == {"mua"}


def test_g8_fires_on_db_without_z(config):
    ctx = _clean()
    ctx.reports_z = False
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G8_db_without_z"]


def test_g10_flags_a_window_under_revision(config):
    ctx = _clean()
    ctx.window_rows = [
        {"condition": "overt", "derived_from": "microphone", "status": "in_use"},
        {"condition": "rest", "derived_from": "microphone", "status": "under_revision"},
    ]
    findings, _ = run_checks(ctx, config)
    flagged = findings[0].detail["windows"]
    assert [w["condition"] for w in flagged] == ["rest"]


def test_g10_flags_an_assumed_window(config):
    ctx = _clean()
    ctx.window_rows = [{"condition": "overt", "derived_from": "assumed", "status": "in_use"}]
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G10_window_provenance"]


def test_g11_fires_on_speech_without_a_motor_control(config):
    ctx = _clean()
    ctx.conditions = ("overt", "rest")
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G11_control_condition_missing"]


def test_g11_satisfied_by_the_metronome_condition(config):
    ctx = _clean()
    ctx.conditions = ("overt", "metro", "rest")
    assert run_checks(ctx, config)[0] == []


def test_g11_fires_for_a_motor_claim_with_no_resting_baseline(config):
    """The rule family covers paradigms other than speech."""
    ctx = _clean()
    ctx.conditions = ("move",)
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G11_control_condition_missing"]
    assert "rest" in findings[0].remedy


def test_g11_fires_for_stimulation_on_without_stimulation_off(config):
    ctx = _clean()
    ctx.conditions = ("dbs_on",)
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G11_control_condition_missing"]
    assert "dbs_off" in findings[0].remedy


def test_g11_is_satisfied_by_the_matching_control(config):
    for conditions in (("move", "rest"), ("dbs_on", "dbs_off"), ("task", "rest")):
        ctx = _clean()
        ctx.conditions = conditions
        assert run_checks(ctx, config)[0] == [], conditions


def test_g11_reports_every_unmet_rule_at_once(config):
    """Reporting one confound at a time would cost a review cycle each."""
    ctx = _clean()
    ctx.conditions = ("overt", "dbs_on")
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G11_control_condition_missing"]
    unmet = findings[0].detail["unmet"]
    assert len(unmet) == 2
    claims = sorted(c for rule in unmet for c in rule["claim"])
    assert claims == ["dbs_on", "overt"]


def test_g11_still_reads_the_older_single_rule_config():
    """Generalizing the check must not disarm a config written the old way."""
    from dbsspeech.guardrails.checks import control_condition_missing

    ctx = _clean()
    ctx.conditions = ("overt", "rest")
    spec = {"applies_to_conditions": ["overt", "inner"],
            "satisfying_conditions": ["metro"]}
    assert control_condition_missing(ctx, spec) is not None

    ctx.conditions = ("overt", "metro")
    assert control_condition_missing(ctx, spec) is None


def test_g11_with_no_rules_configured_fires_nothing():
    from dbsspeech.guardrails.checks import control_condition_missing

    ctx = _clean()
    ctx.conditions = ("overt", "rest")
    assert control_condition_missing(ctx, {}) is None


def test_g12_blocks_a_smoothed_baseline_and_cannot_be_overridden(config):
    ctx = _clean()
    ctx.baseline_is_smoothed = True
    with pytest.raises(GuardrailBlocked) as exc:
        run_checks(ctx, config, overrides={"G12_baseline_on_smoothed_data": "fine"})
    assert "NOT overridable" in str(exc.value)


def test_g2_fires_without_per_contact_baseline_subtraction(config):
    ctx = _clean()
    ctx.per_contact_baseline_subtracted = False
    with pytest.raises(GuardrailBlocked) as exc:
        run_checks(ctx, config)
    assert exc.value.findings[0].guardrail == "G2_effect_tracks_electrode_not_state"


def test_checks_stay_quiet_when_the_context_says_nothing(config):
    """An empty context must not fire everything; a check that cannot see, waits."""
    findings, _ = run_checks(CheckContext(recipe="x"), config)
    assert findings == []


def test_every_configured_guardrail_with_a_check_is_registered(config):
    """Config and code must not drift apart silently."""
    configured = set(config.get("guardrails") or {})
    implemented = set(registered_checks())
    assert implemented <= configured, f"implemented but unconfigured: {implemented - configured}"


# ---- the five added later ----------------------------------------------------

def test_g3_blocks_averaging_before_the_ratio(config):
    """Jensen's inequality is arithmetic, so this one cannot be overridden."""
    ctx = _clean()
    ctx.ratio_before_average = False
    with pytest.raises(GuardrailBlocked, match="Jensen"):
        run_checks(ctx, config, overrides={"G3_ratio_before_average": "please"})


def test_g4_fires_on_a_threshold_shared_across_conditions(config):
    ctx = _clean()
    ctx.threshold_within_condition = False
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G4_threshold_across_conditions"]


def test_g7_fires_when_a_band_overlaps_speech_emg(config):
    ctx = _clean()
    ctx.emg_regressed = False
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G7_emg_contamination_in_high_band"]


def test_g7_says_so_when_there_is_no_emg_to_regress(config):
    ctx = _clean()
    ctx.emg_available, ctx.emg_regressed = False, False
    findings, _ = run_checks(ctx, config)
    assert "cannot be measured" in findings[0].remedy


def test_g7_quiet_for_bands_below_the_emg_range(config):
    ctx = _clean()
    ctx.emg_regressed = False
    ctx.requested_bands = {"beta": (13.0, 30.0)}
    assert run_checks(ctx, config)[0] == []


def test_g7_quiet_when_no_speech_condition_is_analyzed(config):
    ctx = _clean()
    ctx.emg_regressed = False
    ctx.conditions = ("metro", "rest")
    assert run_checks(ctx, config)[0] == []


def test_g9_fires_when_an_excursion_dwarfs_the_effect(config):
    ctx = _clean()
    ctx.max_excursion_db, ctx.reported_effect_db = 4.3, 2.0
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G9_nonstationarity_exceeds_effect"]
    assert findings[0].detail["ratio"] == pytest.approx(2.15)


def test_g9_reports_the_duration_the_excursion_was_measured_over(config):
    """The ratio is not comparable between runs of different length, so say the length.

    An excursion grows with recording duration whenever the baseline is closer to
    a random walk than to a bounded process, so the same physiology gives a
    larger ratio in a longer recording. Measured in STO 3, which found the
    excursion of a random walk growing as 1.6*sqrt(t). G9 still fires on the
    ratio alone; the duration is carried so a reader can tell two runs apart.
    """
    ctx = _clean()
    ctx.max_excursion_db, ctx.reported_effect_db = 4.3, 2.0
    ctx.recording_duration_s = 515.0
    findings, _ = run_checks(ctx, config)
    assert [f.guardrail for f in findings] == ["G9_nonstationarity_exceeds_effect"]
    assert findings[0].detail["recording_duration_s"] == 515.0
    assert "515 s" in findings[0].message, (
        f"the duration belongs in the message a person reads: {findings[0].message!r}"
    )
    assert "recording length" in findings[0].remedy


def test_g9_still_reads_cleanly_when_the_duration_is_unknown(config):
    """Nothing upstream is required to supply it, so the message must survive its absence."""
    ctx = _clean()
    ctx.max_excursion_db, ctx.reported_effect_db = 4.3, 2.0
    findings, _ = run_checks(ctx, config)
    assert findings[0].detail["recording_duration_s"] is None
    assert findings[0].message.endswith("dB"), findings[0].message
    assert " s of recording" not in findings[0].message


def test_g9_quiet_when_the_effect_is_the_largest_thing(config):
    ctx = _clean()
    ctx.max_excursion_db, ctx.reported_effect_db = 1.0, 4.0
    assert run_checks(ctx, config)[0] == []


def test_g13_blocks_a_raw_path_when_filenames_are_not_declared_safe(config):
    ctx = _clean()
    ctx.filenames_deidentified = False
    ctx.paths_in_outputs = ("/some/raw/uh0000-991231.mat",)
    with pytest.raises(GuardrailBlocked, match="manifest key"):
        run_checks(ctx, config, overrides={"G13_path_and_filename_policy": "no"})


def test_g13_quiet_where_the_site_declares_filenames_safe(config):
    ctx = _clean()
    ctx.filenames_deidentified = True
    ctx.paths_in_outputs = ("/some/raw/block.mat",)
    assert run_checks(ctx, config)[0] == []


def test_every_guardrail_in_the_docs_is_implemented(config):
    """The gap between what the docs claim and what runs is the bug class."""
    import re
    from pathlib import Path

    documented = set(re.findall(r"^## (G\d+)\.", Path("docs/guardrails.md").read_text(),
                                re.M))
    implemented = {name.split("_")[0] for name in registered_checks()}
    assert documented <= implemented, documented - implemented


# ---- C2. config can tighten, never re-open -----------------------------------

def test_config_cannot_reopen_a_check_the_code_declared_closed(config):
    """G3, G6, G12 and G13 pass overridable=False because they are arithmetic
    rather than judgment, and base.py says so. The engine used to read
    `spec.get("allow_override", finding.overridable)`, so a line of YAML won
    outright. The shipped config says false for all four, so this was latent."""
    import copy

    from dbsspeech.guardrails import GuardrailBlocked, run_checks

    ctx = _clean()
    ctx.ratio_before_average = False            # fires G3, which is not overridable

    loosened = copy.deepcopy(config)
    loosened["guardrails"]["G3_ratio_before_average"]["allow_override"] = True

    with pytest.raises(GuardrailBlocked) as exc:
        run_checks(ctx, loosened, overrides={"G3_ratio_before_average": "let me"})
    assert "G3_ratio_before_average" in str(exc.value)


def test_config_can_still_close_a_check_the_code_left_open(config):
    """Tightening still works: allow_override false on an overridable check
    means the override is refused."""
    import copy

    from dbsspeech.guardrails import GuardrailBlocked, run_checks

    ctx = _clean()
    ctx.reference_scheme = "monopolar"          # fires G1, which is overridable

    tightened = copy.deepcopy(config)
    tightened["guardrails"]["G1_shared_reference_common_mode"]["allow_override"] = False

    with pytest.raises(GuardrailBlocked):
        run_checks(ctx, tightened,
                   overrides={"G1_shared_reference_common_mode": "synthetic"})


def test_an_overridable_check_is_still_overridable(config):
    """Guard the guard: the change must not have closed everything."""
    from dbsspeech.guardrails import run_checks

    ctx = _clean()
    ctx.reference_scheme = "monopolar"
    findings, applied = run_checks(
        ctx, config, overrides={"G1_shared_reference_common_mode": "synthetic fixture"}
    )
    assert any(o.guardrail == "G1_shared_reference_common_mode" for o in applied)


# ---- C1. the config promises only what it delivers ---------------------------

def test_every_guardrail_config_key_is_read_by_some_code():
    """A key that changes nothing is worse than no key: a lab edits it, sees the
    file change and no behaviour change, and concludes the guardrail was
    retuned. Eleven keys were in that state; the intent behind them is now prose
    in docs/guardrails.md.

    Deliberately a crude textual search. It does not try to prove a key is used
    correctly, only that deleting it would be noticed by something.
    """
    import re
    from pathlib import Path

    import yaml

    root = Path(__file__).resolve().parents[2]
    cfg = yaml.safe_load((root / "configs" / "guardrails.yaml").read_text())

    keys = set(cfg.get("defaults") or {})
    for spec in (cfg.get("guardrails") or {}).values():
        if isinstance(spec, dict):
            keys.update(spec)

    source = "\n".join(
        f.read_text()
        for f in (root / "src" / "dbsspeech").rglob("*.py")
        if "__pycache__" not in str(f)
    )
    unread = sorted(
        k for k in keys if not re.search(r"[\"']" + re.escape(k) + r"[\"']", source)
    )
    assert not unread, (
        "configs/guardrails.yaml offers keys no code reads: "
        f"{unread}. Wire them up, or move the intent to docs/guardrails.md."
    )


def test_the_antialias_fraction_actually_reaches_a_recipe():
    """The one key that went the other way: it was dead, and seven recipes
    hard-coded the same number as a fraction of the sampling rate."""
    from dbsspeech.manifest import load_configs
    from dbsspeech.preprocess import cutoff_fraction_from, usable_bandwidth_hz

    configs = load_configs()
    assert cutoff_fraction_from(configs) == pytest.approx(0.8)
    # The shipped value reproduces the number the recipes used to hard-code.
    assert usable_bandwidth_hz(8138.0, cutoff_fraction_from(configs)) == pytest.approx(
        8138.0 * 0.4
    )
    # And changing it changes the answer, which is the whole point.
    lowered = {"guardrails": {"guardrails": {
        "G6_decimation_removes_claimed_band": {
            "antialias_cutoff_fraction_of_nyquist": 0.5
        }
    }}}
    assert cutoff_fraction_from(lowered) == pytest.approx(0.5)
    assert usable_bandwidth_hz(1000.0, cutoff_fraction_from(lowered)) == pytest.approx(
        250.0
    )


@pytest.mark.parametrize("bad", [0.0, -0.1, 1.5])
def test_a_nonsense_antialias_fraction_is_refused(bad):
    from dbsspeech.preprocess import cutoff_fraction_from

    cfg = {"guardrails": {"guardrails": {
        "G6_decimation_removes_claimed_band": {
            "antialias_cutoff_fraction_of_nyquist": bad
        }
    }}}
    with pytest.raises(ValueError, match="fraction of Nyquist"):
        cutoff_fraction_from(cfg)


def test_a_missing_guardrail_config_falls_back_to_the_documented_default():
    from dbsspeech.preprocess import DEFAULT_CUTOFF_FRACTION, cutoff_fraction_from

    assert cutoff_fraction_from(None) == DEFAULT_CUTOFF_FRACTION
    assert cutoff_fraction_from({}) == DEFAULT_CUTOFF_FRACTION
