"""Validator tests: each invariant from docs/schema.md gets a broken manifest.

Built in tmp dirs from a known-good baseline, so a test names exactly one defect
and asserts the validator reports it. No real data.
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from dbsspeech.manifest import load_configs, load_manifest, validate

pytestmark = pytest.mark.unit

SID, SES = "S01", "ses1"

BASE: dict[str, tuple[list[str], list[list[str]]]] = {
    "subjects.csv": (
        ["study_id", "session", "hemisphere", "format", "root_relpath", "acquisition", "notes"],
        [[SID, SES, "R", "tdt_mat", "block", "acq", ""]],
    ),
    "streams.csv": (
        ["study_id", "session", "stream", "n_channels", "sfreq_hz", "units", "role",
         "relpath", "notes"],
        [[SID, SES, "neur", "8", "2000.0", "V", "neural", "", ""]],
    ),
    "leads.csv": (
        ["study_id", "session", "lead_id", "target", "hemisphere", "lead_model",
         "channel_first", "channel_last", "rotation_deg", "notes"],
        [[SID, SES, "lead1", "stn", "R", "unknown_directional_1331", "1", "8", "0", ""]],
    ),
    "channels.csv": (
        ["study_id", "session", "stream", "ch_index", "ch_name", "region", "lead_id",
         "lead_contact", "site", "include", "exclude_reason"],
        [
            [SID, SES, "neur", str(i + 1), f"c{i + 1}", "stn", "lead1", cid, "", "true", ""]
            for i, cid in enumerate(["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"])
        ],
    ),
    "windows.csv": (
        ["study_id", "session", "condition", "t_start_s", "t_end_s", "derived_from",
         "status", "notes"],
        [[SID, SES, "overt", "10.0", "20.0", "microphone", "in_use", ""]],
    ),
}


def _write(dirpath: Path, edits: dict | None = None) -> Path:
    dirpath.mkdir(parents=True, exist_ok=True)
    tables = {k: (h, [row[:] for row in rows]) for k, (h, rows) in BASE.items()}
    if edits:
        for name, fn in edits.items():
            fn(tables[name][1])
    for name, (header, rows) in tables.items():
        with (dirpath / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)
    return dirpath


@pytest.fixture(scope="module")
def configs():
    return load_configs()


def _report(tmp_path, configs, edits=None, name="m"):
    d = _write(tmp_path / name, edits)
    return validate(load_manifest(d), configs)


def test_baseline_is_valid(tmp_path, configs):
    rep = _report(tmp_path, configs)
    assert rep.ok, rep


def test_orphan_row_is_reported(tmp_path, configs):
    def edit(rows):
        rows[0] = ["GHOST", *rows[0][1:]]

    rep = _report(tmp_path, configs, {"channels.csv": edit})
    assert any("no row in subjects.csv" in e for e in rep.errors), rep


def test_duplicate_channel_is_reported(tmp_path, configs):
    rep = _report(tmp_path, configs, {"channels.csv": lambda r: r.append(r[0][:])})
    assert any("duplicate" in e for e in rep.errors), rep


def test_exclusion_without_a_reason_is_reported(tmp_path, configs):
    def edit(rows):
        rows[0][9], rows[0][10] = "false", ""
    rep = _report(tmp_path, configs, {"channels.csv": edit})
    assert any("exclude_reason is empty" in e for e in rep.errors), rep


def test_unparseable_include_is_reported(tmp_path, configs):
    rep = _report(tmp_path, configs, {"channels.csv": lambda r: r[0].__setitem__(9, "maybe")})
    assert any("include must be true or false" in e for e in rep.errors), rep


def test_region_outside_the_vocabulary_names_the_term(tmp_path, configs):
    rep = _report(tmp_path, configs, {"channels.csv": lambda r: r[0].__setitem__(5, "hippocampus")})
    assert any("'hippocampus'" in e and "vocabularies" in e for e in rep.errors), rep


def test_unknown_lead_id_is_reported(tmp_path, configs):
    rep = _report(tmp_path, configs, {"channels.csv": lambda r: r[0].__setitem__(6, "lead9")})
    assert any("has no row in leads.csv" in e for e in rep.errors), rep


def test_contact_not_on_the_declared_model_is_reported(tmp_path, configs):
    """The point of device-driven naming: a contact must exist on that lead."""
    rep = _report(tmp_path, configs, {"channels.csv": lambda r: r[0].__setitem__(7, "99z")})
    assert any("is not a contact of" in e for e in rep.errors), rep


def test_channel_range_mismatched_to_model_is_reported(tmp_path, configs):
    rep = _report(tmp_path, configs, {"leads.csv": lambda r: r[0].__setitem__(7, "6")})
    assert any("has 8 contacts" in e for e in rep.errors), rep


def test_missing_rotation_warns_and_blocks_direction_claims(tmp_path, configs):
    rep = _report(tmp_path, configs, {"leads.csv": lambda r: r[0].__setitem__(8, "")})
    assert rep.ok, "missing rotation is a warning, not an error"
    assert any("direction claims are blocked" in w for w in rep.warnings), rep


def test_overlapping_windows_are_reported(tmp_path, configs):
    def edit(rows):
        rows.append([SID, SES, "overt", "15.0", "25.0", "microphone", "in_use", ""])
    rep = _report(tmp_path, configs, {"windows.csv": edit})
    assert any("overlap" in e for e in rep.errors), rep


def test_adjacent_windows_do_not_overlap(tmp_path, configs):
    def edit(rows):
        rows.append([SID, SES, "overt", "20.0", "30.0", "microphone", "in_use", ""])
    rep = _report(tmp_path, configs, {"windows.csv": edit})
    assert rep.ok, rep


def test_backwards_window_is_reported(tmp_path, configs):
    rep = _report(tmp_path, configs, {"windows.csv": lambda r: r[0].__setitem__(4, "5.0")})
    assert any("must exceed" in e for e in rep.errors), rep


def test_assumed_window_warns(tmp_path, configs):
    rep = _report(tmp_path, configs, {"windows.csv": lambda r: r[0].__setitem__(5, "assumed")})
    assert any("assumed, not measured" in w for w in rep.warnings), rep


def test_stream_channel_count_mismatch_is_reported(tmp_path, configs):
    rep = _report(tmp_path, configs, {"streams.csv": lambda r: r[0].__setitem__(3, "16")})
    assert any("declares 16 channels" in e for e in rep.errors), rep


def test_all_violations_are_reported_together(tmp_path, configs):
    """A validator that stops at the first error turns one pass into ten."""
    def channels(rows):
        rows[0][5] = "hippocampus"
        rows[1][9], rows[1][10] = "false", ""
    rep = _report(tmp_path, configs, {"channels.csv": channels})
    assert len(rep.errors) >= 2, rep


def test_project_manifests_are_valid():
    """The committed manifests must satisfy their own contract."""
    rep = validate(load_manifest())
    assert rep.ok, str(rep)


# ---- D1. ch_index is a channel number, and identity is numeric ---------------
#
# ch_index reaches numpy as `int(ch_index) - 1` in io/loader.py. Two ways that
# went wrong silently, and neither was validated.


def test_ch_index_zero_is_reported(tmp_path, configs):
    """0 becomes -1, which numpy resolves to the LAST channel of the stream. In
    range, so nothing raises, and the wrong contact is analysed under the right
    name. An out-of-range index raises IndexError in both readers, which is why
    this one is the dangerous case rather than the obvious one."""
    def edit(rows):
        rows[0][3] = "0"

    rep = _report(tmp_path, configs, {"channels.csv": edit})
    assert any("1-based" in e for e in rep.errors), rep


def test_a_negative_ch_index_is_reported(tmp_path, configs):
    def edit(rows):
        rows[0][3] = "-2"

    rep = _report(tmp_path, configs, {"channels.csv": edit})
    assert any("1-based" in e for e in rep.errors), rep


def test_a_non_integer_ch_index_is_reported(tmp_path, configs):
    def edit(rows):
        rows[0][3] = "two"

    rep = _report(tmp_path, configs, {"channels.csv": edit})
    assert any("not an integer" in e for e in rep.errors), rep


def test_a_ch_index_beyond_the_declared_count_is_reported(tmp_path, configs):
    """streams.csv declares 8 channels. Reaching past them raises IndexError at
    read time, which is a crash in the middle of a run rather than a validation
    error before it."""
    def edit(rows):
        rows[0][3] = "99"

    rep = _report(tmp_path, configs, {"channels.csv": edit})
    assert any("beyond the" in e for e in rep.errors), rep


def test_the_same_channel_written_two_ways_is_a_duplicate(tmp_path, configs):
    """Identity keyed on the raw string, so "1" and "01" were two channels to
    the validator and one channel to the loader: two contacts, one physical
    signal, no report."""
    def edit(rows):
        twin = rows[0][:]
        twin[3] = "01"
        twin[4] = "c1_again"
        twin[7] = "2a"
        rows.append(twin)

    rep = _report(tmp_path, configs, {"channels.csv": edit})
    assert any("duplicate" in e for e in rep.errors), rep


def test_the_baseline_channel_indices_are_still_accepted(tmp_path, configs):
    """Guard the guard: the new checks must not reject an ordinary manifest."""
    rep = _report(tmp_path, configs)
    assert not [e for e in rep.errors if "ch_index" in e], rep
