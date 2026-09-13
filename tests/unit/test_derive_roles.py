"""Names to roles: nothing is guessed, and every gap is reported at once.

Three properties are guarded. First, a stream or channel name that policy does
not list never gets a role by proximity: it either stops the block with a
`Quarantine` or, when the policy says skip, is left out, and which of the two
happens is decided by the config and not by the code. Second, when channels are
unmapped the error names ALL of them, quoted, in input order, so one look at
the ledger shows every gap in `configs/derive.yaml` rather than the first one
found. Third, a channel matching two roles is an error rather than a
first-match, because a silent first-match is how a microphone ends up in the
LFP product.

The shipped `configs/derive.yaml` is exercised too, with stream and channel
names copied from a sweep of the staged archive (408 .tsq, 151 .vhdr), so the
patterns in that file cannot drift away from the archive without a test
noticing. The full sweep lives in tests/realdata/test_derive_roles_archive.py.
"""

from __future__ import annotations

import pytest

from dbsspeech.derive.config import DeriveConfig, load_config
from dbsspeech.derive.model import Quarantine
from dbsspeech.derive.roles import classify_channels, classify_stream, group_by_role

pytestmark = pytest.mark.unit


def _cfg(on_unmapped: str = "quarantine", **overrides: object) -> DeriveConfig:
    roles = {
        "streams": {"ecos": "lfp", "mic_": "mic", "MonA": "monitor"},
        "channel_patterns": {
            "lfp": [r"^ecog", r"^dbs\d"],
            "emg": [r"fdi", r"^oo_"],
            "mic": [r"^mic"],
            "micro": [r"^no_"],
            "ignore": [r"notconnected"],
        },
        "on_unmapped": on_unmapped,
    }
    roles.update(overrides)
    return DeriveConfig.model_validate({"roles": roles})


# ---- streams -------------------------------------------------------------------

def test_a_listed_stream_name_returns_its_role():
    assert classify_stream("ecos", _cfg()) == "lfp"
    assert classify_stream("MonA", _cfg()) == "monitor"


def test_stream_lookup_is_case_sensitive_so_mona_is_not_MonA():
    with pytest.raises(Quarantine) as exc:
        classify_stream("mona", _cfg())
    assert exc.value.reason == "unmapped_stream"
    assert exc.value.detail == "'mona'"


def test_an_unlisted_stream_quarantines_under_the_default_policy():
    with pytest.raises(Quarantine) as exc:
        classify_stream("xyzw", _cfg())
    assert exc.value.reason == "unmapped_stream"
    assert exc.value.detail == "'xyzw'"


def test_an_unlisted_stream_returns_empty_when_policy_says_skip():
    assert classify_stream("xyzw", _cfg("skip")) == ""


def test_stream_lookup_is_exact_not_prefix_or_substring():
    # "ecos" is listed; "ecos2" and "eco" are not the same store.
    with pytest.raises(Quarantine) as exc:
        classify_stream("ecos2", _cfg())
    assert exc.value.reason == "unmapped_stream"
    with pytest.raises(Quarantine) as exc:
        classify_stream("eco", _cfg())
    assert exc.value.reason == "unmapped_stream"


def test_an_empty_stream_name_is_still_visible_in_the_detail():
    with pytest.raises(Quarantine) as exc:
        classify_stream("", _cfg())
    assert exc.value.reason == "unmapped_stream"
    assert exc.value.detail == "''"
    assert str(exc.value) == "unmapped_stream: ''"


# ---- channels ------------------------------------------------------------------

def test_channels_get_one_role_each_in_input_order():
    names = ["ECOG_A1", "DBS12", "fdi_contra", "mic", "NotConnected"]
    assert classify_channels(names, _cfg()) == ["lfp", "lfp", "emg", "mic", ""]


def test_channel_patterns_match_case_insensitively():
    assert classify_channels(["ECOG_A3", "Ecog_a3", "ecog_a3"], _cfg()) == ["lfp"] * 3


def test_patterns_are_searched_not_anchored_unless_the_pattern_anchors():
    # "fdi" has no anchor, so it matches anywhere; "^oo_" only at the start.
    assert classify_channels(["left_FDI"], _cfg()) == ["emg"]
    with pytest.raises(Quarantine) as exc:
        classify_channels(["x_oo_y"], _cfg())
    assert exc.value.reason == "unmapped_channel"
    assert exc.value.detail == "'x_oo_y'"


def test_ignore_wins_over_a_role_that_would_also_match():
    # Both "^ecog" (lfp) and "notconnected" (ignore) hit; ignore wins silently.
    assert classify_channels(["ecog_NotConnected"], _cfg()) == [""]


def test_ignore_wins_over_a_name_two_roles_would_otherwise_fight_over():
    cfg = _cfg(channel_patterns={"lfp": [r"^ecog"], "mic": [r"ecog"], "ignore": [r"_nc$"]})
    assert classify_channels(["ecog_nc"], cfg) == [""]
    with pytest.raises(Quarantine) as exc:
        classify_channels(["ecog_1"], cfg)
    assert exc.value.reason == "ambiguous_channel"


def test_every_unmapped_channel_is_listed_not_just_the_first():
    names = ["ecog_a1", "bogus_a", "mic", "bogus_b", "bogus_c"]
    with pytest.raises(Quarantine) as exc:
        classify_channels(names, _cfg())
    assert exc.value.reason == "unmapped_channel"
    assert exc.value.detail == "'bogus_a', 'bogus_b', 'bogus_c'"


def test_unmapped_detail_keeps_input_order_and_drops_repeats():
    names = ["zz", "bogus", "aa", "bogus", "zz"]
    with pytest.raises(Quarantine) as exc:
        classify_channels(names, _cfg())
    assert exc.value.detail == "'zz', 'bogus', 'aa'"


def test_an_empty_channel_name_is_quoted_so_it_does_not_vanish_from_the_detail():
    with pytest.raises(Quarantine) as exc:
        classify_channels([""], _cfg())
    assert exc.value.reason == "unmapped_channel"
    assert exc.value.detail == "''"
    with pytest.raises(Quarantine) as exc:
        classify_channels(["", "bogus"], _cfg())
    assert exc.value.detail == "'', 'bogus'"


def test_a_comma_inside_a_channel_name_stays_inside_its_quotes():
    # BrainVision allows a comma in a name (escaped as \1 in the header), so
    # the detail must not read as three names here.
    with pytest.raises(Quarantine) as exc:
        classify_channels(["bogus,a", "b"], _cfg())
    assert exc.value.detail == "'bogus,a', 'b'"


def test_unmapped_channels_become_empty_when_policy_says_skip():
    names = ["ecog_a1", "bogus", "mic"]
    assert classify_channels(names, _cfg("skip")) == ["lfp", "", "mic"]


def test_a_channel_matching_two_roles_is_ambiguous_not_first_match():
    cfg = _cfg(channel_patterns={"lfp": [r"^ecog"], "mic": [r"ecog"]})
    with pytest.raises(Quarantine) as exc:
        classify_channels(["ecog_1"], cfg)
    assert exc.value.reason == "ambiguous_channel"
    assert exc.value.detail == "'ecog_1' -> lfp/mic"


def test_two_patterns_of_the_same_role_are_not_ambiguous():
    cfg = _cfg(channel_patterns={"lfp": [r"^ecog", r"ecog", r"_a\d+$"]})
    assert classify_channels(["ecog_a1"], cfg) == ["lfp"]


def test_ambiguity_is_an_error_even_when_policy_says_skip():
    cfg = _cfg("skip", channel_patterns={"lfp": [r"^ecog"], "mic": [r"ecog"]})
    with pytest.raises(Quarantine) as exc:
        classify_channels(["ecog_1"], cfg)
    assert exc.value.reason == "ambiguous_channel"


def test_ambiguity_is_reported_before_unmapped_and_lists_every_ambiguous_name():
    cfg = _cfg(channel_patterns={"lfp": [r"^ecog"], "mic": [r"ecog"]})
    with pytest.raises(Quarantine) as exc:
        classify_channels(["ecog_1", "bogus", "ecog_2"], cfg)
    assert exc.value.reason == "ambiguous_channel"
    assert exc.value.detail == "'ecog_1' -> lfp/mic, 'ecog_2' -> lfp/mic"


def test_empty_channel_list_classifies_to_empty_list():
    assert classify_channels([], _cfg()) == []


def test_a_bare_string_is_refused_rather_than_split_into_letters():
    # Sequence[str] admits str; iterating "ecog_a1" would classify seven
    # letters and, under skip, silently drop the channel.
    with pytest.raises(TypeError, match="sequence of channel names"):
        classify_channels("ecog_a1", _cfg("skip"))
    with pytest.raises(TypeError, match="sequence of channel names"):
        group_by_role("ecog_a1", _cfg("skip"))


def test_a_config_with_no_channel_patterns_quarantines_every_channel():
    cfg = DeriveConfig.model_validate({"roles": {"on_unmapped": "quarantine"}})
    with pytest.raises(Quarantine) as exc:
        classify_channels(["ecog_a1", "mic"], cfg)
    assert exc.value.reason == "unmapped_channel"
    assert exc.value.detail == "'ecog_a1', 'mic'"


# ---- grouping ------------------------------------------------------------------

def test_group_by_role_returns_ascending_indices_per_role_and_omits_ignored():
    names = ["ecog_a1", "fdi_contra", "ecog_a2", "NotConnected", "mic", "DBS1"]
    groups = group_by_role(names, _cfg())
    assert groups == {"lfp": [0, 2, 5], "emg": [1], "mic": [4]}


def test_group_by_role_keys_follow_role_order_not_first_appearance():
    names = ["mic", "fdi_contra", "ecog_a1"]
    assert list(group_by_role(names, _cfg())) == ["lfp", "emg", "mic"]


def test_group_by_role_raises_the_same_quarantine_as_classify_channels():
    with pytest.raises(Quarantine) as exc:
        group_by_role(["ecog_a1", "bogus"], _cfg())
    assert exc.value.reason == "unmapped_channel"
    assert exc.value.detail == "'bogus'"


def test_group_by_role_omits_skipped_channels_under_skip_policy():
    assert group_by_role(["bogus", "ecog_a1"], _cfg("skip")) == {"lfp": [1]}


# ---- the shipped policy --------------------------------------------------------

@pytest.fixture(scope="module")
def shipped() -> DeriveConfig:
    return load_config()


# Every stream name the staged uh .tsq indexes carry, from the archive sweep.
@pytest.mark.parametrize(
    ("stream", "role"),
    [
        ("ecos", "lfp"), ("ecog", "lfp"), ("dbs1", "lfp"), ("LFP1", "lfp"), ("RSn1", "lfp"),
        ("emgg", "emg"), ("emg_", "emg"), ("mic_", "mic"), ("micp", "mic"),
        ("macp", "micro"), ("marw", "micro"), ("raww", "micro"),
        ("spkk", "micro"), ("spik", "micro"), ("spie", "micro"),
        ("MonA", "monitor"),
    ],
)
def test_shipped_policy_maps_every_tdt_store_the_archive_carries(shipped, stream, role):
    assert classify_stream(stream, shipped) == role


@pytest.mark.parametrize(
    "store",
    ["Cam1", "PeA/", "PeB/", "PeC/", "CnA/", "CnB/", "AmpA", "AmpB", "AmpC",
     "CntA", "CntB", "CntC", "DelA", "DelB", "DelC", "ChnA", "ChnB", "Note", "Tick", "PerB"],
)
def test_shipped_policy_does_not_classify_epoch_stores_as_streams(shipped, store):
    # Epoch stores are listed by the tank reader under .epochs, not .streams,
    # so they never reach classify_stream; if one did, it must not get a role.
    with pytest.raises(Quarantine) as exc:
        classify_stream(store, shipped)
    assert exc.value.reason == "unmapped_stream"


# One name per spelling family the 151 staged .vhdr actually use.
@pytest.mark.parametrize(
    ("channel", "role"),
    [
        ("ecog_a1", "lfp"), ("ECOG_A28", "lfp"), ("ECOG_P6", "lfp"), ("ECOGA1", "lfp"),
        ("ECOGP6", "lfp"), ("DBS1", "lfp"), ("DBS9", "lfp"), ("DBS16", "lfp"),
        ("OO", "emg"), ("OO_contra", "emg"), ("oo_contra", "emg"),
        ("FDI", "emg"), ("FDI_contra", "emg"), ("FDI_ipsi", "emg"),
        ("FCU", "emg"), ("fcu_contra", "emg"), ("GASTROC", "emg"), ("gastroc_contra", "emg"),
        ("TA_contra", "emg"), ("ta_contra", "emg"), ("emg_1", "emg"), ("emg_4", "emg"),
        ("mic", "mic"), ("MIC", "mic"),
        ("macro_raw", "micro"), ("spikes", "micro"),
        ("ao_MACRO_raw", "micro"), ("ao_MICRO_raw", "micro"), ("ao_MICRO_spike", "micro"),
        ("NO_MACRO_RAW", "micro"), ("NO_MICRO_RAW", "micro"), ("NO_MICRO_SPK", "micro"),
    ],
)
def test_shipped_policy_maps_the_brainvision_channel_vocabulary(shipped, channel, role):
    assert classify_channels([channel], shipped) == [role]


def test_shipped_policy_ignores_the_unwired_channel_spellings(shipped):
    assert classify_channels(["NotConnected", "not_connected_3"], shipped) == ["", ""]


def test_shipped_policy_splits_a_typical_vhdr_layout_into_products(shipped):
    names = [
        "ECOG_A1", "ECOG_A2", "ECOG_P1", "ECOG_P2", "DBS1", "DBS2",
        "OO_contra", "FDI_contra", "FCU_contra", "TA_contra", "MIC",
        "NO_MACRO_RAW", "NO_MICRO_RAW", "NO_MICRO_SPK",
    ]
    assert group_by_role(names, shipped) == {
        "lfp": [0, 1, 2, 3, 4, 5],
        "emg": [6, 7, 8, 9],
        "mic": [10],
        "micro": [11, 12, 13],
    }


def test_shipped_policy_resolves_bare_micro_raw_to_micro(shipped):
    """The mic pattern is '^mic(?!ro)' so a bare 'micro_raw' is micro, not ambiguous."""
    assert classify_channels(["micro_raw"], shipped) == ["micro"]


def test_shipped_policy_ignores_bare_alpha_omega_inputs(shipped):
    """ao_1..ao_3 are unconnected Alpha Omega inputs; ignored, never quarantined.

    They are candidate blank-pin artifact controls and should get a role of
    their own (docs/backlog.md); until then the policy drops them silently
    rather than blocking ten ug headers.
    """
    assert classify_channels(["ao_1", "ao_2", "ao_3"], shipped) == ["", "", ""]


def test_ambiguity_in_the_shipped_policy_is_refused_rather_than_first_matched(shipped):
    # Guards the module's contract independent of whether the config bug above
    # is fixed: whichever way the config goes, a bare "micro_raw" is never
    # silently written into the mic product.
    try:
        roles = classify_channels(["micro_raw"], shipped)
    except Quarantine as exc:
        assert exc.reason == "ambiguous_channel"
        assert exc.detail == "'micro_raw' -> mic/micro"
    else:
        assert roles == ["micro"]
