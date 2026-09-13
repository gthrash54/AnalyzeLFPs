"""The decisions table. Re-detection must never overwrite human judgment."""

from __future__ import annotations

import pytest

from dbsspeech.qc import (
    Flag,
    append_history,
    decide,
    load_decisions,
    merge_decisions,
    propose,
    read_history,
    save_decisions,
    undecided,
)

pytestmark = pytest.mark.unit

SID = "S01"


def _flag(target: str, kind: str = "flat_channel", **evidence) -> Flag:
    return Flag("channel", target, kind, evidence or {"std": 1e-9},
                "exclude_channel", "high")


@pytest.fixture
def derivatives(tmp_path):
    return tmp_path / "derivatives"


def test_propose_writes_both_files(derivatives):
    flags_path, decisions_path, rows = propose([_flag("c1")], SID, derivatives)
    assert flags_path.exists() and decisions_path.exists()
    assert len(rows) == 1
    assert rows[0]["proposed_action"] == "exclude_channel"


def test_a_new_flag_starts_undecided(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    assert rows[0]["approved"] == ""
    assert undecided(rows) == rows


def test_reviewer_columns_survive_re_detection(derivatives):
    """The whole point: running propose again must not erase judgment."""
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    rows = decide(rows, rows[0]["flag_id"], approved=True, reviewer="garrett")
    save_decisions(SID, rows, derivatives)

    _, _, again = propose([_flag("c1")], SID, derivatives)
    assert again[0]["approved"] == "true"
    assert again[0]["reviewer"] == "garrett"
    assert again[0]["reviewed_at"]


def test_evidence_is_refreshed_while_judgment_is_kept(derivatives):
    """A reviewer should see current numbers, not the ones they first saw."""
    _, _, rows = propose([_flag("c1", std=1e-9)], SID, derivatives)
    rows = decide(rows, rows[0]["flag_id"], approved=True, reviewer="garrett")
    save_decisions(SID, rows, derivatives)

    _, _, again = propose([_flag("c1", std=5e-9)], SID, derivatives)
    assert "5e-09" in again[0]["evidence_summary"]
    assert again[0]["approved"] == "true"


def test_a_new_flag_is_appended_not_replacing(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    rows = decide(rows, rows[0]["flag_id"], approved=True, reviewer="garrett")
    save_decisions(SID, rows, derivatives)

    _, _, again = propose([_flag("c1"), _flag("c2")], SID, derivatives)
    assert len(again) == 2
    assert {r["target"] for r in again} == {"c1", "c2"}
    assert next(r for r in again if r["target"] == "c1")["approved"] == "true"


def test_a_flag_that_stops_firing_goes_stale_not_deleted(derivatives):
    """The record must still show that someone judged it, and what they said."""
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    rows = decide(rows, rows[0]["flag_id"], approved=False,
                  reviewer="garrett", reason="looked fine on the raw trace")
    save_decisions(SID, rows, derivatives)

    _, _, again = propose([_flag("c2")], SID, derivatives)
    stale = next(r for r in again if r["target"] == "c1")
    assert stale["status"] == "stale"
    assert stale["reason"] == "looked fine on the raw trace"


def test_a_stale_row_is_not_counted_as_undecided(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    save_decisions(SID, rows, derivatives)
    _, _, again = propose([_flag("c2")], SID, derivatives)
    assert [r["target"] for r in undecided(again)] == ["c2"]


def test_proposing_twice_with_no_change_is_idempotent(derivatives):
    _, _, first = propose([_flag("c1"), _flag("c2")], SID, derivatives)
    _, _, second = propose([_flag("c1"), _flag("c2")], SID, derivatives)
    assert [r["flag_id"] for r in first] == [r["flag_id"] for r in second]
    assert all(r["status"] == "active" for r in second)


def test_rejecting_without_a_reason_is_refused(derivatives):
    """A record cannot tell a considered override from a mis-click."""
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    with pytest.raises(ValueError, match="requires a reason"):
        decide(rows, rows[0]["flag_id"], approved=False, reviewer="garrett")


def test_changing_the_action_without_a_reason_is_refused(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    with pytest.raises(ValueError, match="requires a reason"):
        decide(rows, rows[0]["flag_id"], approved=True, reviewer="g",
               action_taken="annotate_window")


def test_approving_the_proposed_action_needs_no_reason(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    out = decide(rows, rows[0]["flag_id"], approved=True, reviewer="garrett")
    assert out[0]["action_taken"] == "exclude_channel"


def test_rejection_records_no_action_taken(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    out = decide(rows, rows[0]["flag_id"], approved=False, reviewer="g",
                 reason="ring contact, expected")
    assert out[0]["action_taken"] == "none"


def test_deciding_an_unknown_flag_raises(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    with pytest.raises(KeyError, match="no flag"):
        decide(rows, "deadbeef", approved=True, reviewer="g")


def test_decisions_round_trip_through_the_file(derivatives):
    _, _, rows = propose([_flag("c1")], SID, derivatives)
    rows = decide(rows, rows[0]["flag_id"], approved=True, reviewer="garrett")
    save_decisions(SID, rows, derivatives)
    assert load_decisions(SID, derivatives)[0]["reviewer"] == "garrett"


def test_history_is_append_only(derivatives):
    append_history(SID, derivatives, "sign", "garrett", n_flags=3)
    append_history(SID, derivatives, "reopen", "walker", reason="rest window replaced")
    events = read_history(SID, derivatives)
    assert [e["event"] for e in events] == ["sign", "reopen"]
    assert events[1]["reason"] == "rest window replaced"


def test_merge_needs_no_files_at_all():
    """Pure function, so the merge rule can be reasoned about on its own."""
    merged = merge_decisions([], [_flag("c1")])
    assert merged[0]["status"] == "active"
    assert merged[0]["reviewer"] == ""
