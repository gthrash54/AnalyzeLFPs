"""The scrubber never lets an identifier out, and never over-reaches into the sanctioned ones.

Two properties are guarded here, and they pull in opposite directions. Every
string that could leave the build (a log line, a ledger row, an exception
message) must come out free of configured patterns, staging paths, Box paths,
TDT tank stems, and filename date stamps, in that order, and scrubbing twice
must equal scrubbing once. At the same time a study ID on its own and a block
name must survive, because they are the only identifiers the store is allowed
to carry and a ledger that redacts them is useless.

The third property is about the guard itself: `assert_clean` must refuse dirty
text without quoting it, because the exception it raises is precisely the kind
of thing that gets logged.

Every fixture value here is synthetic. The study IDs (`ug0001`, `uh0000`) do
not exist, the six-digit groups are an impossible date (month 13, day 32) and
an impossible time (25:99:99), and the eight-digit stamp is the same impossible
date. A test at the bottom, run only with the archive named, checks that no
digit run in tests/ occurs in the archive listing; that is the guard against a
real acquisition date sneaking into a fixture.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from dbsspeech.derive.config import DeriveConfig, PrivacyConfig, load_config
from dbsspeech.derive.model import Quarantine
from dbsspeech.derive.redact import (
    BOX_TOKEN,
    PATH_TOKEN,
    REDACTED,
    RULE_BOX,
    RULE_FILENAME_DATE,
    RULE_FORBIDDEN_ROOT,
    RULE_PATTERN,
    RULE_TANK_STEM,
    UNPRINTABLE,
    Scrubber,
    redact_exception,
    scrubber_from_config,
)

pytestmark = pytest.mark.unit

# The patterns as shipped in configs/derive.yaml, spelled out so the test does
# not depend on the file and reads as a specification.
CONFIG_PATTERNS = [
    r"u[gh]\d{4}-\d{6}-\d{6}",
    r"\d{1,2}/\d{1,2}/\d{4}",
    r"\d{4}-\d{2}-\d{2}",
]

STAGING = Path("/srv/staging")

# Synthetic identifiers. Nonexistent study IDs, an impossible date, an
# impossible time. See the module docstring.
STEM = "uh0000-991332-259999"
STEM_UNDERSCORE = "ug0001_991332_259999"
ISO_DATE = "1999-13-40"
US_DATE = "13/40/1999"
FILENAME_STAMP = "date_19991340 time_2599"


@pytest.fixture
def scrubber() -> Scrubber:
    return Scrubber(CONFIG_PATTERNS, forbidden_path_roots=[STAGING])


# ---- rule 1: configured patterns -----------------------------------------------


def test_a_configured_date_pattern_is_replaced_with_the_redacted_token(scrubber):
    assert scrubber.scrub(f"acquired {ISO_DATE} at noon") == f"acquired {REDACTED} at noon"
    assert scrubber.scrub(f"acquired {US_DATE} at noon") == f"acquired {REDACTED} at noon"


def test_every_configured_pattern_is_applied_not_just_the_first(scrubber):
    text = f"{ISO_DATE} then {US_DATE} then {STEM}"
    assert scrubber.scrub(text) == f"{REDACTED} then {REDACTED} then {REDACTED}"


def test_a_scrubber_with_no_patterns_and_no_roots_still_applies_the_floor():
    bare = Scrubber([])
    assert bare.scrub(f"plain text {ISO_DATE}") == f"plain text {ISO_DATE}"
    assert bare.scrub(f"tank {STEM}") == f"tank {REDACTED}"


def test_a_pattern_that_matches_the_empty_string_is_refused_at_construction():
    with pytest.raises(ValueError, match="empty string"):
        Scrubber(["x*"])


@pytest.mark.parametrize("pattern", ["redact", "<", r"pa\w+>", "box"])
def test_a_pattern_that_matches_inside_an_output_token_is_refused_at_construction(pattern):
    with pytest.raises(ValueError, match="matches the token"):
        Scrubber([pattern])


# ---- rule 2: forbidden roots -----------------------------------------------------


def test_an_absolute_path_under_a_forbidden_root_becomes_the_path_token(scrubber):
    text = "cannot open /srv/staging/ug0001/stage1 surgery/ERPs.vhdr"
    assert scrubber.scrub(text) == f"cannot open {PATH_TOKEN}"


def test_a_forbidden_path_that_contains_a_tank_stem_still_collapses_to_one_token(scrubber):
    text = f"/srv/staging/ug0001/stage1 surgery/{STEM}_motor.tsq"
    assert scrubber.scrub(text) == PATH_TOKEN


def test_a_forbidden_path_that_contains_a_configured_date_still_collapses_to_one_token(scrubber):
    text = f"read /srv/staging/ug0001/{ISO_DATE} session/{STEM}/x.tev failed"
    assert scrubber.scrub(text) == f"read {PATH_TOKEN}"


def test_the_path_token_does_not_eat_prose_after_a_colon_space(scrubber):
    text = "/srv/staging/ug0001/stage1 surgery/ERPs.vhdr: file not found"
    assert scrubber.scrub(text) == f"{PATH_TOKEN}: file not found"


def test_a_quoted_path_keeps_its_quotes_and_the_words_around_it(scrubber):
    text = "source '/srv/staging/ug0001/stage1 surgery' is not synced"
    assert scrubber.scrub(text) == f"source '{PATH_TOKEN}' is not synced"


def test_a_sibling_directory_that_merely_shares_a_prefix_is_not_a_forbidden_path(scrubber):
    assert scrubber.is_clean("/srv/staging2/ok.txt")


def test_a_path_outside_every_forbidden_root_is_left_alone(scrubber):
    assert scrubber.is_clean("/home/someone/derivatives/ug0001/out.h5")


def test_a_tilde_root_matches_both_its_tilde_and_expanded_spellings():
    home = Path.home()
    s = Scrubber([], forbidden_path_roots=[Path("~/staging_for_tests")])
    assert s.scrub("~/staging_for_tests/ug0001/x.tsq") == PATH_TOKEN
    assert s.scrub(f"{home}/staging_for_tests/ug0001/x.tsq") == PATH_TOKEN


def test_forbidden_roots_accept_strings_as_well_as_paths():
    s = Scrubber([], forbidden_path_roots=["/srv/other"])  # type: ignore[list-item]
    assert s.scrub("/srv/other/thing") == PATH_TOKEN


@pytest.mark.parametrize("root", ["staging", ".", "relative/dir"])
def test_a_relative_forbidden_root_is_refused_at_construction(root):
    with pytest.raises(ValueError, match="must be absolute"):
        Scrubber([], forbidden_path_roots=[Path(root)])


# ---- rule 3: Box, remote and mount point -----------------------------------------


def test_an_rclone_style_box_remote_path_is_caught(scrubber):
    text = "copying Box:Lab Raw Data/some folder/file.tev failed"
    scrubbed = scrubber.scrub(text)
    assert scrubbed == f"copying {BOX_TOKEN}"
    assert "Lab Raw Data" not in scrubbed


def test_a_box_path_whose_folder_carries_a_configured_date_still_collapses_to_one_token(
    scrubber,
):
    text = f"Box:Lab Raw Data/{ISO_DATE} case 12345 Lastname/x.tev"
    assert scrubber.scrub(text) == BOX_TOKEN


def test_a_box_mount_path_whose_folder_carries_a_tank_stem_still_collapses(scrubber):
    text = f"/home/someone/Box/Lab Raw Data/{STEM}/case 12345 Lastname/x.tev"
    assert scrubber.scrub(text) == f"/home/someone{BOX_TOKEN}"


def test_a_windows_style_box_path_is_caught(scrubber):
    text = r"C:\Users\someone\Box\Lab Raw Data\folder\file.tev"
    assert scrubber.scrub(text) == rf"C:\Users\someone{BOX_TOKEN}"


def test_the_box_mount_point_is_caught_from_the_box_segment_onward(scrubber):
    text = "read /home/someone/Box/Lab Raw Data/folder/file.tev"
    assert scrubber.scrub(text) == f"read /home/someone{BOX_TOKEN}"


def test_a_folder_whose_name_merely_contains_box_is_a_box_segment(scrubber):
    assert scrubber.scrub("/mnt/MyBoxSync/folder/file") == f"/mnt{BOX_TOKEN}"


def test_the_word_box_in_prose_is_not_a_path_segment(scrubber):
    assert scrubber.is_clean("Nothing here talks to Box.")
    assert scrubber.is_clean("a box of contacts")


def test_the_box_rule_is_case_sensitive(scrubber):
    assert scrubber.is_clean("/home/u/box/folder/file")
    assert scrubber.is_clean("box:remote/path")


# ---- rule 4: the tank-stem floor ---------------------------------------------------


@pytest.mark.parametrize(
    "stem",
    [
        STEM,
        STEM_UNDERSCORE,
        STEM.upper(),
        STEM.replace("-", " "),
    ],
)
def test_a_tank_stem_is_redacted_even_when_no_pattern_is_configured(stem):
    bare = Scrubber([])
    assert bare.scrub(f"tank {stem}_lesion_cog.tsq") == f"tank {REDACTED}_lesion_cog.tsq"


def test_a_tank_whose_subject_field_is_not_a_study_id_is_still_a_tank_stem():
    bare = Scrubber([])
    assert bare.scrub("testsub-991332-259999_cog_baseline.tsq") == f"{REDACTED}_cog_baseline.tsq"


def test_a_stem_whose_subject_starts_with_a_digit_is_outside_the_floor():
    # Documented limit: the floor keys on a word-shaped subject field. The
    # archive holds no tank named this way today; the configured patterns are
    # what would have to catch one.
    bare = Scrubber([])
    assert bare.is_clean("3099-991332-259999")


def test_the_floor_names_the_tank_stem_rule_when_the_patterns_missed_it():
    bare = Scrubber([])
    assert bare.violations(STEM) == (RULE_TANK_STEM,)


# ---- rule 5: the filename date-stamp floor ----------------------------------------------


def test_a_brainvision_style_date_stamp_is_redacted_with_no_pattern_configured():
    bare = Scrubber([])
    name = f"BRAINaim1_{FILENAME_STAMP} stimuli_ordered.csv"
    assert bare.scrub(name) == f"BRAINaim1_{REDACTED} stimuli_ordered.csv"
    assert bare.violations(name) == (RULE_FILENAME_DATE,)


def test_a_date_stamp_without_a_time_is_still_redacted():
    bare = Scrubber([])
    assert bare.scrub("x_date_19991340 protocol.dat") == f"x_{REDACTED} protocol.dat"


def test_the_shipped_config_leaves_no_eight_digit_run_in_a_date_stamped_name():
    s = scrubber_from_config(load_config(), extra_roots=[STAGING])
    scrubbed = s.scrub(f"BRAINaim2_{FILENAME_STAMP} stimulation protocol.dat")
    assert re.search(r"\d{8}", scrubbed) is None


def test_the_word_date_followed_by_a_short_number_is_not_a_stamp(scrubber):
    assert scrubber.is_clean("date_1999 is not a stamp; update_12345678 is a counter")


# ---- what must survive -------------------------------------------------------------


@pytest.mark.parametrize("study_id", ["uh0001", "ug0002", "UG0003"])
def test_a_study_id_on_its_own_survives(scrubber, study_id):
    assert scrubber.is_clean(f"building {study_id} stage1 surgery")


def test_a_block_name_survives(scrubber):
    assert scrubber.is_clean("block increment1_depth1_DNU quarantined: unmapped_stream")


def test_a_ledger_style_line_with_study_id_session_and_block_survives(scrubber):
    assert scrubber.is_clean("ug0002 | stage1 surgery | erp001 | done | 12.5 s")


def test_a_study_id_followed_by_one_six_digit_group_is_not_a_tank_stem(scrubber):
    assert scrubber.is_clean("ug0001-991332")


# ---- order, idempotence, and the API around it ----------------------------------------


def test_rules_fire_in_the_documented_order_and_the_result_is_fully_tokenized(scrubber):
    text = f"{ISO_DATE}; /srv/staging/x; Box:y/z; {STEM_UNDERSCORE}; a_{FILENAME_STAMP}"
    assert scrubber.violations(text) == (
        RULE_PATTERN,
        RULE_FORBIDDEN_ROOT,
        RULE_BOX,
        RULE_TANK_STEM,
        RULE_FILENAME_DATE,
    )
    assert (
        scrubber.scrub(text) == f"{REDACTED}; {PATH_TOKEN}; {BOX_TOKEN}; {REDACTED}; a_{REDACTED}"
    )


def test_each_line_of_a_multi_line_message_is_scrubbed_on_its_own(scrubber):
    text = "\n".join(
        [
            f"first: {ISO_DATE}",
            "second: /srv/staging/ug0001/x.tsq",
            "third: Box:remote/folder",
            f"fourth: tank {STEM}",
            "fifth: ug0001 erp001 fine",
        ]
    )
    assert scrubber.scrub(text) == "\n".join(
        [
            f"first: {REDACTED}",
            f"second: {PATH_TOKEN}",
            f"third: {BOX_TOKEN}",
            f"fourth: tank {REDACTED}",
            "fifth: ug0001 erp001 fine",
        ]
    )


def test_scrubbing_is_idempotent(scrubber):
    text = (
        f"{ISO_DATE} read /srv/staging/ug0001/stage1 surgery/{STEM}.tsq; "
        f"then Box:Lab Raw Data/{US_DATE}/g.tev; tank {STEM_UNDERSCORE} for ug0001 erp001; "
        f"file BRAINaim1_{FILENAME_STAMP} protocol.dat"
    )
    once = scrubber.scrub(text)
    assert scrubber.scrub(once) == once
    assert scrubber.is_clean(once)


def test_the_tokens_themselves_are_clean(scrubber):
    assert scrubber.is_clean(f"{REDACTED} {PATH_TOKEN} {BOX_TOKEN}")


def test_empty_text_is_clean_and_unchanged(scrubber):
    assert scrubber.scrub("") == ""
    assert scrubber.assert_clean("") == ""


def test_assert_clean_returns_clean_text_unchanged(scrubber):
    text = "ug0001 erp001 done"
    assert scrubber.assert_clean(text) is text


def test_assert_clean_never_leaks_the_offending_text():
    secret = "/srv/staging/ug0001/stage1 surgery/ERPs.vhdr"
    s = Scrubber(CONFIG_PATTERNS, forbidden_path_roots=[STAGING])
    with pytest.raises(ValueError) as info:
        s.assert_clean(f"opening {secret}")
    message = str(info.value)
    assert secret not in message
    assert "staging" not in message
    assert "ERPs" not in message
    assert str(len(f"opening {secret}")) in message
    assert RULE_FORBIDDEN_ROOT in message


def test_assert_clean_names_every_rule_that_fired(scrubber):
    with pytest.raises(ValueError) as info:
        scrubber.assert_clean(f"{ISO_DATE} and {STEM_UNDERSCORE}")
    assert RULE_PATTERN in str(info.value)
    assert RULE_TANK_STEM in str(info.value)


# ---- exceptions ---------------------------------------------------------------------


def test_redact_exception_returns_the_class_name_and_a_scrubbed_message(scrubber):
    exc = FileNotFoundError("/srv/staging/ug0001/stage1 surgery/x.tsq")
    name, message = redact_exception(exc, scrubber)
    assert name == "FileNotFoundError"
    assert message == PATH_TOKEN


def test_redact_exception_keeps_a_quarantine_reason_readable(scrubber):
    exc = Quarantine("bulk_not_synced", f"ug0001 erp001 tank {STEM}")
    name, message = redact_exception(exc, scrubber)
    assert name == "Quarantine"
    assert message == f"bulk_not_synced: ug0001 erp001 tank {REDACTED}"


def test_redact_exception_handles_an_exception_with_no_message(scrubber):
    assert redact_exception(RuntimeError(), scrubber) == ("RuntimeError", "")


def test_redact_exception_survives_an_exception_whose_str_raises(scrubber):
    class Unprintable(Exception):
        def __str__(self) -> str:
            raise RuntimeError("no string for you")

    assert redact_exception(Unprintable(), scrubber) == ("Unprintable", UNPRINTABLE)


def test_redact_exception_flattens_an_exception_group_and_scrubs_its_members(scrubber):
    group = ExceptionGroup(
        "two failed", [ValueError(f"tank {STEM}"), OSError("/srv/staging/ug0001/x")]
    )
    name, message = redact_exception(group, scrubber)
    assert name == "ExceptionGroup"
    assert STEM not in message
    assert "staging" not in message
    # Python's own group message ("two failed (2 sub-exceptions)") stays; the
    # members follow it.
    assert message == (
        f"two failed (2 sub-exceptions); member ValueError: tank {REDACTED}; "
        f"member OSError: {PATH_TOKEN}"
    )


def test_redact_exception_scrubs_an_explicit_cause_chain(scrubber):
    try:
        try:
            raise OSError(f"cannot read /srv/staging/ug0001/{STEM}.tsq")
        except OSError as inner:
            raise RuntimeError("block failed") from inner
    except RuntimeError as outer:
        name, message = redact_exception(outer, scrubber)
    assert name == "RuntimeError"
    assert message == f"block failed; caused by OSError: cannot read {PATH_TOKEN}"


def test_redact_exception_does_not_loop_on_a_cause_cycle(scrubber):
    a = RuntimeError("a")
    b = RuntimeError("b")
    a.__cause__ = b
    b.__cause__ = a
    name, message = redact_exception(a, scrubber)
    assert name == "RuntimeError"
    assert message.startswith("a; caused by RuntimeError: b")


# ---- config -----------------------------------------------------------------------


def test_scrubber_from_config_uses_the_configured_patterns_and_extra_roots():
    cfg = DeriveConfig(privacy=PrivacyConfig(redact_patterns=[r"secret\d+"]))
    s = scrubber_from_config(cfg, extra_roots=[STAGING])
    assert s.scrub("secret42 at /srv/staging/x") == f"{REDACTED} at {PATH_TOKEN}"
    assert s.forbidden_path_roots == (STAGING,)


def test_scrubber_from_config_refuses_to_forbid_nothing():
    # A pipeline scrubber with rule 2 switched off would pass every staging
    # path through, silently. The factory makes that a construction error.
    with pytest.raises(ValueError, match="extra_roots"):
        scrubber_from_config(DeriveConfig(), extra_roots=[])


def test_scrubber_from_the_shipped_config_redacts_a_tank_stem_and_a_date():
    s = scrubber_from_config(load_config(), extra_roots=[STAGING])
    assert s.scrub(f"{STEM} on {ISO_DATE}") == f"{REDACTED} on {REDACTED}"
    assert s.is_clean("ug0002 stage1 surgery erp001")


# ---- the fixtures themselves ----------------------------------------------------------

# Where the staging archive is on the machine that runs this check. Unset on
# CI and on a fresh checkout, so the test skips there; it exists to catch a real
# acquisition date pasted into a test as a fixture value.
STAGING_ROOT_ENV = "DBS_STAGING_ROOT"


@pytest.mark.realdata
def test_no_digit_run_in_any_test_file_occurs_in_the_archive_listing():
    root_str = os.environ.get(STAGING_ROOT_ENV)
    if not root_str:
        pytest.skip(f"{STAGING_ROOT_ENV} is not set")
    root = Path(root_str).expanduser()
    if not root.is_dir():
        pytest.skip(f"{STAGING_ROOT_ENV} does not name a directory")
    digit_run = re.compile(r"\d{6,8}")
    in_archive: set[str] = set()
    for entry in root.rglob("*"):
        if "_inventory" in entry.relative_to(root).parts:
            continue
        in_archive.update(digit_run.findall(entry.name))
    tests_dir = Path(__file__).resolve().parents[1]
    offenders: dict[str, set[str]] = {}
    for test_file in tests_dir.rglob("*.py"):
        found = set(digit_run.findall(test_file.read_text())) & in_archive
        if found:
            offenders[str(test_file.relative_to(tests_dir))] = found
    # Report the files and the count only; the runs themselves are the secret.
    summary = {name: len(runs) for name, runs in offenders.items()}
    assert not offenders, f"test files carry digit runs found in the archive: {summary}"
