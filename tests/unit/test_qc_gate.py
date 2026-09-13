"""The approval gate, and whether approved decisions actually take effect."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from dbsspeech.io.loader import open_session
from dbsspeech.manifest import load_configs, load_manifest
from dbsspeech.qc import (
    APPROVED,
    IN_REVIEW,
    REOPENED,
    UNREVIEWED,
    Flag,
    QCNotApproved,
    applied_actions,
    decide,
    load_decisions,
    propose,
    reopen,
    require_approved,
    save_decisions,
    sign,
    status,
)
from tests.fixtures.make_tdt_fixture import N_NEURAL_CH, SFREQ_NEURAL, make_fixture

pytestmark = pytest.mark.unit

SID, SES = "S01", "ses1"
CONTACTS = ["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"]


def _flag(target: str, action: str = "exclude_channel") -> Flag:
    return Flag("channel", target, "flat_channel", {"std": 1e-9}, action, "high",
                detector="flat_channel")


@pytest.fixture
def derivatives(tmp_path):
    return tmp_path / "derivatives"


# ---- status transitions ------------------------------------------------------

def test_unreviewed_before_detection_runs(derivatives):
    assert status(SID, derivatives) == UNREVIEWED


def test_in_review_once_flags_exist(derivatives):
    propose([_flag("c1")], SID, derivatives)
    assert status(SID, derivatives) == IN_REVIEW


def test_approved_after_deciding_and_signing(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    save_decisions(SID, decide(rows, rows[0]["flag_id"], True, "garrett"), derivatives)
    sign(SID, "garrett", derivatives)
    assert status(SID, derivatives) == APPROVED


def test_a_clean_recording_is_approvable(derivatives):
    """Zero flags means detection ran and found nothing, not that it never ran."""
    propose([], SID, derivatives)
    sign(SID, "garrett", derivatives)
    assert status(SID, derivatives) == APPROVED


def test_editing_a_decision_after_signing_invalidates_the_signature(derivatives):
    """The signature certifies a set of judgments, not a subject."""
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    save_decisions(SID, decide(rows, rows[0]["flag_id"], True, "garrett"), derivatives)
    sign(SID, "garrett", derivatives)
    assert status(SID, derivatives) == APPROVED

    rows = load_decisions(SID, derivatives)
    save_decisions(SID, decide(rows, rows[0]["flag_id"], False, "garrett",
                               reason="changed my mind"), derivatives)
    assert status(SID, derivatives) == REOPENED


def test_reopening_is_logged_and_changes_status(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    save_decisions(SID, decide(rows, rows[0]["flag_id"], True, "g"), derivatives)
    sign(SID, "g", derivatives)
    reopen(SID, "walker", "rest window replaced", derivatives)
    assert status(SID, derivatives) == REOPENED


def test_reopening_without_a_reason_is_refused(derivatives):
    with pytest.raises(ValueError, match="requires a reason"):
        reopen(SID, "walker", "  ", derivatives)


def test_signing_with_undecided_flags_names_them(derivatives):
    propose([_flag("c1"), _flag("c2")], SID, derivatives)
    with pytest.raises(QCNotApproved, match="undecided"):
        sign(SID, "garrett", derivatives)


def test_signing_before_detection_says_what_to_do(derivatives):
    with pytest.raises(QCNotApproved, match="run QC detection first"):
        sign(SID, "garrett", derivatives)


def test_an_anonymous_signature_is_refused(derivatives):
    propose([], SID, derivatives)
    with pytest.raises(ValueError, match="reviewer"):
        sign(SID, "   ", derivatives)


def test_require_approved_explains_what_to_do(derivatives):
    propose([_flag("c1")], SID, derivatives)
    with pytest.raises(QCNotApproved, match="Finish the review"):
        require_approved(SID, derivatives)


def test_a_stale_flag_does_not_block_signing(derivatives):
    """A flag that stopped firing needs no decision."""
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    save_decisions(SID, rows, derivatives)
    propose([], SID, derivatives)  # c1 no longer fires, becomes stale
    sign(SID, "garrett", derivatives)
    assert status(SID, derivatives) == APPROVED


# ---- approved actions actually take effect -----------------------------------

def _approved_exclusion(derivatives, target: str) -> None:
    _, _, rows = propose([_flag(target)], SID, derivatives)
    save_decisions(SID, decide(rows, rows[0]["flag_id"], True, "garrett"), derivatives)
    sign(SID, "garrett", derivatives)


def test_applied_actions_lists_only_approved_ones(derivatives):
    _, _, rows = propose([_flag("lead1:2a"), _flag("lead1:2b")], SID, derivatives)
    rows = decide(rows, rows[0]["flag_id"], True, "garrett")
    rows = decide(rows, rows[1]["flag_id"], False, "garrett", reason="looked fine")
    save_decisions(SID, rows, derivatives)
    actions = applied_actions(SID, derivatives)
    assert len(actions) == 1


@pytest.fixture
def project(tmp_path_factory):
    base = tmp_path_factory.mktemp("gate")
    make_fixture(base / "data" / "block" / "synthetic_block.mat")
    m = base / "manifest"
    m.mkdir()

    def write(name, header, rows):
        with (m / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write("subjects.csv",
          ["study_id", "session", "hemisphere", "format", "root_relpath",
           "acquisition", "acquisition_date", "notes"],
          [[SID, SES, "R", "tdt_mat", "block", "acq", "", ""]])
    write("streams.csv",
          ["study_id", "session", "stream", "n_channels", "sfreq_hz", "units",
           "role", "relpath", "notes"],
          [[SID, SES, "neur", str(N_NEURAL_CH), str(SFREQ_NEURAL), "V", "neural", "", ""]])
    write("leads.csv",
          ["study_id", "session", "lead_id", "target", "hemisphere", "lead_model",
           "channel_first", "channel_last", "rotation_deg", "notes"],
          [[SID, SES, "lead1", "stn", "R", "unknown_directional_1331", "1", "8", "0", ""]])
    write("channels.csv",
          ["study_id", "session", "stream", "ch_index", "ch_name", "region",
           "lead_id", "lead_contact", "site", "include", "exclude_reason"],
          [[SID, SES, "neur", str(i + 1), f"c{i+1}", "stn", "lead1", cid, "", "true", ""]
           for i, cid in enumerate(CONTACTS)])
    write("windows.csv",
          ["study_id", "session", "condition", "t_start_s", "t_end_s",
           "derived_from", "status", "notes"],
          [[SID, SES, "overt", "0.0", "2.0", "microphone", "in_use", ""]])
    return base


def _session(project):
    return open_session(SID, SES, manifest=load_manifest(project / "manifest"),
                        configs=load_configs(), data_dir=project / "data")


def test_an_approved_exclusion_actually_removes_the_contact(project, derivatives):
    """The record must not claim an action that never took effect."""
    _approved_exclusion(derivatives, "lead1:2a")
    with _session(project) as s:
        assert "2a" in s.leads()["lead1"].contact_ids
        effective = s.apply_qc(applied_actions(SID, derivatives))
        assert "2a" not in s.leads()["lead1"].contact_ids
        assert effective[0]["effect"].startswith("dropped 2a")


def test_a_dropped_contact_removes_the_derivations_needing_it(project, derivatives):
    _approved_exclusion(derivatives, "lead1:1")
    with _session(project) as s:
        s.apply_qc(applied_actions(SID, derivatives))
        sig = s.read_derived("lead1", "bipolar_vertical", tmin=0.0, tmax=1.0)
        assert all(not n.endswith("-1") for n in sig.names)
        assert any("not available" in note for note in sig.notes)


def test_an_annotation_retains_every_sample(project, derivatives):
    """Never delete. A window flag is an annotation, not a cut."""
    _, _, rows = propose([_flag("lead1:2a", "annotate_window")], SID, derivatives)
    save_decisions(SID, decide(rows, rows[0]["flag_id"], True, "garrett"), derivatives)
    sign(SID, "garrett", derivatives)
    with _session(project) as s:
        before = s.read_derived("lead1", "monopolar", tmin=0.0, tmax=1.0).data.shape
        effective = s.apply_qc(applied_actions(SID, derivatives))
        after = s.read_derived("lead1", "monopolar", tmin=0.0, tmax=1.0).data.shape
        assert before == after
        assert "samples retained" in effective[0]["effect"]
        assert s.qc_annotations


def test_a_notch_is_recorded_as_a_recommendation_not_applied(project, derivatives):
    _, _, rows = propose([_flag("lead1:2a", "notch")], SID, derivatives)
    save_decisions(SID, decide(rows, rows[0]["flag_id"], True, "garrett"), derivatives)
    sign(SID, "garrett", derivatives)
    with _session(project) as s:
        effective = s.apply_qc(applied_actions(SID, derivatives))
        assert "not applied here" in effective[0]["effect"]


def test_an_action_naming_an_unknown_contact_takes_no_effect(project, derivatives):
    _approved_exclusion(derivatives, "lead1:nope")
    with _session(project) as s:
        assert s.apply_qc(applied_actions(SID, derivatives)) == []
        assert len(s.leads()["lead1"].contact_ids) == 8


def test_approval_json_records_the_counts(derivatives):
    _, _, rows = propose([_flag("c1"), _flag("c2")], SID, derivatives)
    rows = decide(rows, rows[0]["flag_id"], True, "g")
    rows = decide(rows, rows[1]["flag_id"], False, "g", reason="fine")
    save_decisions(SID, rows, derivatives)
    approval = sign(SID, "g", derivatives)
    assert approval["n_flags"] == 2
    assert approval["n_approved"] == 1
    stored = json.loads((Path(derivatives) / "qc" / f"sub-{SID}" / "approval.json").read_text())
    assert stored["reviewer"] == "g"
