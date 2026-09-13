"""Onboarding: inspect proposes, commit refuses.

The property worth guarding is that `commit` never leaves an invalid manifest on
disk. `load_manifest` is what every recipe depends on, so a manifest that parses
but violates an invariant is worse than one that is merely incomplete: nothing
downstream would report it, and the first symptom would be a wrong number.
"""

from __future__ import annotations

import shutil

import pytest

from dbsspeech.manifest import load_manifest, validate
from dbsspeech.onboarding import TABLE_COLUMNS, CommitRefused, commit, inspect
from tests.fixtures.make_brainvision_fixture import (
    CH_NAMES,
    MARKER_LABELS,
    SFREQ_HZ,
    make_brainvision_fixture,
)

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def block(tmp_path_factory):
    return make_brainvision_fixture(tmp_path_factory.mktemp("block"))


@pytest.fixture
def manifest_dir(tmp_path):
    """A copy of the real manifest, so a write cannot touch the repository's."""
    target = tmp_path / "manifest"
    shutil.copytree("manifest", target)
    # The repository's manifests are header-only now, so a commit that must
    # reference an existing subject needs one to exist. Written here rather than
    # shipped, which is the point: onboarding is what adds the first subject.
    (target / "subjects.csv").write_text(
        "study_id,session,hemisphere,format,root_relpath,acquisition,"
        "acquisition_date,notes\n"
        "demo01,ses1,R,brainvision,block,demo,,synthetic\n"
    )
    # One curated window, so the test that a commit never overwrites an existing
    # decision has an existing decision to protect. `in_use` is the status an
    # import must not be allowed to downgrade to `draft`.
    (target / "windows.csv").write_text(
        "study_id,session,condition,t_start_s,t_end_s,derived_from,status,notes\n"
        "demo01,ses1,overt,1.0,3.0,microphone,in_use,curated by hand\n"
    )
    return target


# ---- inspect ------------------------------------------------------------------

def test_inspect_reports_the_streams_a_recording_states(block):
    found = inspect(block)
    assert found["format"] == "brainvision"
    assert found["streams"]["eeg"]["n_channels"] == len(CH_NAMES)
    assert found["streams"]["eeg"]["sfreq_hz"] == pytest.approx(SFREQ_HZ)


def test_inspect_reports_the_markers_it_found(block):
    found = inspect(block)
    assert set(found["markers"]) == set(MARKER_LABELS)


def test_inspect_names_what_it_deliberately_did_not_propose(block):
    """So an empty channels table is never mistaken for a complete one."""
    found = inspect(block)
    assert found["not_proposed"]
    joined = " ".join(found["not_proposed"])
    assert "channels.csv" in joined
    assert "leads.csv" in joined


def test_inspect_reports_an_unreadable_block_rather_than_raising(tmp_path):
    broken = tmp_path / "broken"
    make_brainvision_fixture(broken)
    next(broken.glob("*.eeg")).unlink()
    found = inspect(broken)
    assert found["unreadable"]
    assert "FileNotFoundError" in found["unreadable"][0]["error"]


def test_inspect_recognizes_a_tree_of_study_directories(tmp_path):
    root = tmp_path / "stage"
    make_brainvision_fixture(root / "sub001" / "blockA")
    found = inspect(root)
    assert found["path_is_tree"] is True
    assert found["study_ids"] == ["sub001"]
    assert found["proposed_rows"]["subjects"]


def test_inspect_writes_nothing(block):
    before = sorted(p.name for p in block.parent.rglob("*"))
    inspect(block, study_id="s1", session="sess")
    assert sorted(p.name for p in block.parent.rglob("*")) == before


# ---- commit -------------------------------------------------------------------

def _window(**kwargs):
    row = {
        "study_id": "demo01",
        "session": "ses1",
        "condition": "move",
        "t_start_s": 600.0,
        "t_end_s": 610.0,
        "derived_from": "task_marker",
        "status": "draft",
        "notes": "",
    }
    row.update(kwargs)
    return row


def test_a_valid_row_is_written(manifest_dir):
    result = commit({"windows": [_window()]}, manifest_dir=manifest_dir)
    assert result["added"]["windows"] == 1
    assert "windows.csv" in result["written"]
    rows = load_manifest(manifest_dir).windows
    assert any(r["condition"] == "move" for r in rows)


def test_the_manifest_still_validates_after_a_commit(manifest_dir):
    commit({"windows": [_window()]}, manifest_dir=manifest_dir)
    assert validate(load_manifest(manifest_dir)).ok


def test_an_invalid_row_is_refused_and_nothing_is_written(manifest_dir):
    before = (manifest_dir / "windows.csv").read_text()
    with pytest.raises(CommitRefused) as exc:
        commit({"windows": [_window(condition="not_a_condition")]},
               manifest_dir=manifest_dir)
    assert any("not in the vocabulary" in e for e in exc.value.errors)
    assert (manifest_dir / "windows.csv").read_text() == before


def test_a_dry_run_validates_without_writing(manifest_dir):
    before = (manifest_dir / "windows.csv").read_text()
    result = commit({"windows": [_window()]}, manifest_dir=manifest_dir, dry_run=True)
    assert result["dry_run"] is True
    assert result["added"]["windows"] == 1
    assert result["written"] == []
    assert (manifest_dir / "windows.csv").read_text() == before


def test_committing_the_same_row_twice_does_not_duplicate_it(manifest_dir):
    commit({"windows": [_window()]}, manifest_dir=manifest_dir)
    again = commit({"windows": [_window()]}, manifest_dir=manifest_dir)
    assert again["added"]["windows"] == 0
    assert again["duplicates_skipped"]


def test_an_existing_row_is_never_overwritten(manifest_dir):
    """A curated decision must not disappear because an import reran."""
    original = [r for r in load_manifest(manifest_dir).windows
                if r["condition"] == "overt"][0]
    commit({"windows": [_window(condition="overt",
                                t_start_s=original["t_start_s"],
                                status="draft", notes="from an import")]},
           manifest_dir=manifest_dir)
    after = [r for r in load_manifest(manifest_dir).windows
             if r["condition"] == "overt"][0]
    assert after["status"] == original["status"]
    assert after["notes"] == original["notes"]


def test_channels_and_leads_cannot_be_written(manifest_dir):
    """They are the review, not the import."""
    for table in ("channels", "leads"):
        with pytest.raises(ValueError, match="cannot write table"):
            commit({table: [{}]}, manifest_dir=manifest_dir)


def test_only_the_declared_tables_are_writable():
    assert set(TABLE_COLUMNS) == {"subjects", "streams", "windows"}
