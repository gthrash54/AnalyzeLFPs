"""Deriving manifest rows from a tree of recordings.

Two properties matter more than the row counts. The columns that are judgment
must come back empty, because a plausible guess in one of them is worse than a
blank. And an unreadable block must be reported rather than skipped, because a
subject that silently loses a block is a subject whose manifest is wrong in a
way nobody will notice.
"""

from __future__ import annotations

import pytest

from dbsspeech.detect.manifest_rows import (
    LEFT_TO_REVIEW,
    draft_manifest,
    find_blocks,
    verify_readable,
)
from tests.fixtures.make_brainvision_fixture import (
    CH_NAMES,
    SFREQ_HZ,
    make_brainvision_fixture,
)
from tests.fixtures.make_edf_fixture import make_edf_fixture

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def tree(tmp_path_factory):
    """`<root>/<study_id>/<block>/` with two formats and one broken block."""
    root = tmp_path_factory.mktemp("stage")

    make_brainvision_fixture(root / "sub001" / "blockA")
    make_edf_fixture(root / "sub001" / "blockB")
    make_edf_fixture(root / "sub002" / "only")

    # A BrainVision header whose .eeg was never synced: the exact shape of the
    # failure a partially staged archive produces.
    broken = root / "sub002" / "missing_bulk"
    make_brainvision_fixture(broken)
    next(broken.glob("*.eeg")).unlink()

    # Ignored: the staging area's own bookkeeping directories.
    (root / "_inventory").mkdir()
    (root / "_inventory" / "notes.txt").write_text("not a recording")
    return root


def test_blocks_are_found_under_each_study_id(tree):
    found = find_blocks(tree)
    assert {study for study, _ in found} == {"sub001", "sub002"}
    assert len(found) == 4


def test_underscore_directories_are_skipped(tree):
    assert all(study != "_inventory" for study, _ in find_blocks(tree))


def test_rows_are_derived_for_every_readable_block(tree):
    draft = draft_manifest(tree)
    assert len(draft.subjects) == 3
    assert draft.study_ids == ["sub001", "sub002"]


def test_the_format_comes_from_the_reader_not_the_extension(tree):
    draft = draft_manifest(tree)
    formats = {row["session"]: row["format"] for row in draft.subjects}
    assert formats["blockA"] == "brainvision"
    assert formats["blockB"] == "edf"


def test_stream_rows_carry_what_the_recording_states(tree):
    draft = draft_manifest(tree, study_ids=["sub001"])
    eeg = [
        row
        for row in draft.streams
        if row["session"] == "blockA" and row["stream"] == "eeg"
    ]
    assert len(eeg) == 1
    assert eeg[0]["n_channels"] == len(CH_NAMES)
    assert eeg[0]["sfreq_hz"] == pytest.approx(SFREQ_HZ)


def test_judgment_columns_are_left_empty(tree):
    draft = draft_manifest(tree)
    for row in draft.subjects:
        assert row["hemisphere"] == ""
        assert row["acquisition_date"] == ""
    for row in draft.streams:
        assert row["units"] == ""
        assert row["role"] == ""


def test_the_columns_left_empty_are_documented():
    """So the omission reads as deliberate rather than unfinished."""
    assert set(LEFT_TO_REVIEW) == {"hemisphere", "acquisition_date", "units", "role"}
    assert all(why for why in LEFT_TO_REVIEW.values())


def test_an_unreadable_block_is_reported_not_skipped(tree):
    draft = draft_manifest(tree)
    assert len(draft.unreadable) == 1
    where, why = draft.unreadable[0]
    assert "missing_bulk" in where
    assert "FileNotFoundError" in why


def test_a_root_relpath_is_relative_so_it_survives_a_move(tree):
    draft = draft_manifest(tree)
    for row in draft.subjects:
        assert not row["root_relpath"].startswith("/")
        assert row["root_relpath"].startswith(row["study_id"])


def test_study_ids_can_be_limited(tree):
    draft = draft_manifest(tree, study_ids=["sub002"])
    assert draft.study_ids == ["sub002"]


def test_verify_counts_what_opens_and_what_does_not(tree):
    report = verify_readable(tree)
    assert report["sub001"] == {"blocks": 2, "opened": 2, "failed": 0, "errors": []}
    assert report["sub002"]["blocks"] == 2
    assert report["sub002"]["opened"] == 1
    assert report["sub002"]["failed"] == 1
    assert "missing_bulk" in report["sub002"]["errors"][0]["block"]
