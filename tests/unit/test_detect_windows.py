"""Proposing condition windows from task markers.

Built against a synthetic recording rather than the fixtures, so the marker
layout can be stated exactly. The cases that matter are the ones a real
recording produced: a per-trial trigger stream sitting beside a handful of
block markers, which the first version of this module handled catastrophically
by proposing thousands of overlapping rows and discarding every real window.
"""

from __future__ import annotations

import numpy as np
import pytest

from dbsspeech.detect import propose_windows, proposed_rows
from dbsspeech.io.base import EpochSeries, StreamInfo

pytestmark = pytest.mark.unit


class FakeRecording:
    """Only the surface the proposer touches: streams and epochs."""

    def __init__(self, epochs: dict[str, EpochSeries], duration_s: float = 100.0):
        self._epochs = epochs
        self._duration = duration_s

    @property
    def epochs(self):
        return self._epochs

    @property
    def streams(self):
        return {
            "eeg": StreamInfo(
                name="eeg",
                n_channels=4,
                sfreq_hz=100.0,
                n_samples=int(self._duration * 100),
                dtype="float64",
            )
        }


def _series(name: str, onsets, durations=None) -> EpochSeries:
    onsets = np.asarray(onsets, dtype=float)
    # No durations means instantaneous markers, which is what a trigger is.
    offsets = (
        onsets.copy()
        if durations is None
        else onsets + np.asarray(durations, dtype=float)
    )
    return EpochSeries(name=name, onsets=onsets, offsets=offsets)


BLOCK_CONFIG = {
    "default_extent": "until_next",
    "min_duration_s": 0.5,
    "max_events_per_binding": 200,
    "bindings": [{"pattern": "Block", "condition": "cue"}],
}


def test_a_recording_without_markers_says_so():
    proposals = propose_windows(FakeRecording({}), "s1", "sess", BLOCK_CONFIG)
    assert proposed_rows(proposals) == []
    assert not proposals.proposals[0].detectable
    assert "no task markers" in proposals.proposals[0].reason


def test_an_unbound_label_is_reported_not_guessed():
    rec = FakeRecording({"Mystery": _series("Mystery", [10.0, 20.0])})
    proposals = propose_windows(rec, "s1", "sess", BLOCK_CONFIG)
    assert proposed_rows(proposals) == []
    unbound = [p for p in proposals.proposals if p.field == "marker"]
    assert [p.value for p in unbound] == ["Mystery"]
    assert "no binding" in unbound[0].reason


def test_until_next_spans_marker_to_marker_and_then_to_the_end():
    rec = FakeRecording({"Block": _series("Block", [10.0, 30.0, 60.0])}, duration_s=100.0)
    rows = proposed_rows(propose_windows(rec, "s1", "sess", BLOCK_CONFIG))
    assert [(r["t_start_s"], r["t_end_s"]) for r in rows] == [
        (10.0, 30.0),
        (30.0, 60.0),
        (60.0, 100.0),
    ]


def test_a_proposed_row_is_draft_and_marked_as_marker_derived():
    rec = FakeRecording({"Block": _series("Block", [10.0, 30.0])})
    row = proposed_rows(propose_windows(rec, "s1", "sess", BLOCK_CONFIG))[0]
    assert row["status"] == "draft"
    assert row["derived_from"] == "task_marker"
    assert row["study_id"] == "s1"
    assert row["session"] == "sess"
    assert row["condition"] == "cue"


def test_a_window_shorter_than_the_minimum_is_refused():
    rec = FakeRecording({"Block": _series("Block", [10.0, 10.1, 40.0])})
    rows = proposed_rows(propose_windows(rec, "s1", "sess", BLOCK_CONFIG))
    assert (10.0, 10.1) not in [(r["t_start_s"], r["t_end_s"]) for r in rows]


def test_fixed_extent_uses_the_configured_length():
    config = {
        **BLOCK_CONFIG,
        "bindings": [
            {"pattern": "Block", "condition": "cue", "extent": {"fixed_s": 2.0}}
        ],
    }
    rec = FakeRecording({"Block": _series("Block", [10.0, 30.0])})
    rows = proposed_rows(propose_windows(rec, "s1", "sess", config))
    assert [(r["t_start_s"], r["t_end_s"]) for r in rows] == [(10.0, 12.0), (30.0, 32.0)]


def test_annotation_extent_proposes_nothing_for_a_zero_length_marker():
    config = {
        **BLOCK_CONFIG,
        "bindings": [{"pattern": "Block", "condition": "cue", "extent": "annotation"}],
    }
    rec = FakeRecording({"Block": _series("Block", [10.0, 30.0])})
    assert proposed_rows(propose_windows(rec, "s1", "sess", config)) == []


def test_annotation_extent_uses_a_recorded_duration():
    config = {
        **BLOCK_CONFIG,
        "bindings": [{"pattern": "Block", "condition": "cue", "extent": "annotation"}],
    }
    rec = FakeRecording({"Block": _series("Block", [10.0], durations=[5.0])})
    rows = proposed_rows(propose_windows(rec, "s1", "sess", config))
    assert [(r["t_start_s"], r["t_end_s"]) for r in rows] == [(10.0, 15.0)]


# ---- the failures a real recording produced ---------------------------------

def _trial_dense_recording():
    """A block marker beside a per-trial trigger, as a real BrainVision file had."""
    triggers = np.arange(5.0, 95.0, 0.01)  # 9000 events, 10 ms apart
    return FakeRecording(
        {
            "Block": _series("Block", [10.0, 50.0]),
            "Trial": _series("Trial", triggers),
        },
        duration_s=100.0,
    )


def test_a_trial_dense_binding_proposes_nothing_and_says_why():
    config = {
        **BLOCK_CONFIG,
        "bindings": [
            {"pattern": "Block", "condition": "cue"},
            {"pattern": "Trial", "condition": "task", "extent": {"fixed_s": 2.0}},
        ],
    }
    proposals = propose_windows(_trial_dense_recording(), "s1", "sess", config)
    rejected = [
        p
        for p in proposals.proposals
        if p.field == "window" and not p.detectable and p.evidence.get("marker") == "Trial"
    ]
    assert len(rejected) == 1
    assert "trials rather than a condition" in rejected[0].reason
    assert all(r["condition"] != "task" for r in proposed_rows(proposals))


def test_a_trial_dense_label_does_not_truncate_the_block_windows():
    """The subtler half: density must not end someone else's window either."""
    config = {
        **BLOCK_CONFIG,
        "bindings": [
            {"pattern": "Block", "condition": "cue"},
            {"pattern": "Trial", "condition": "task", "extent": {"fixed_s": 2.0}},
        ],
    }
    rows = proposed_rows(propose_windows(_trial_dense_recording(), "s1", "sess", config))
    assert [(r["t_start_s"], r["t_end_s"]) for r in rows] == [(10.0, 50.0), (50.0, 100.0)]


def test_an_unbound_dense_label_also_does_not_truncate_a_window():
    rec = _trial_dense_recording()
    rows = proposed_rows(propose_windows(rec, "s1", "sess", BLOCK_CONFIG))
    assert [(r["t_start_s"], r["t_end_s"]) for r in rows] == [(10.0, 50.0), (50.0, 100.0)]


def test_a_longer_pattern_outranks_a_shorter_one():
    config = {
        **BLOCK_CONFIG,
        "bindings": [
            {"pattern": "Block", "condition": "cue"},
            {"pattern": "Block/rest", "condition": "rest"},
        ],
    }
    rec = FakeRecording({"Block/rest": _series("Block/rest", [10.0, 40.0])})
    rows = proposed_rows(propose_windows(rec, "s1", "sess", config))
    assert {r["condition"] for r in rows} == {"rest"}


def test_no_bindings_configured_proposes_nothing():
    """The shipped default. Reporting labels beats guessing at them."""
    rec = FakeRecording({"Block": _series("Block", [10.0, 40.0])})
    proposals = propose_windows(rec, "s1", "sess", {"bindings": []})
    assert proposed_rows(proposals) == []
    assert [p.value for p in proposals.proposals if p.field == "marker"] == ["Block"]
