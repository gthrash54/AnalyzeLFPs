"""Run records and their index."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from dbsspeech.runs import get_run, list_runs, make_run_id, record, reindex
from dbsspeech.runs.record import REPO_ROOT, repo_relpath

pytestmark = pytest.mark.unit


@pytest.fixture
def dirs(tmp_path):
    return tmp_path / "runs", tmp_path / "derivatives"


def _read(runs_dir, run_id):
    return json.loads((runs_dir / f"{run_id}.json").read_text())


def test_run_id_is_timestamp_then_name():
    rid = make_run_id("psd_by_condition", datetime(2026, 9, 3, 14, 15, 0))
    assert rid == "20260903_141500_psd_by_condition"


def test_run_id_sanitizes_awkward_names():
    assert "/" not in make_run_id("a/b c", datetime(2026, 1, 1))


def test_two_runs_in_the_same_second_do_not_collide(dirs):
    """One-second id resolution would otherwise overwrite a result silently."""
    runs, derivs = dirs
    ids = []
    for _ in range(3):
        with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
            ids.append(run.run_id)
    assert len(set(ids)) == 3
    assert len(list(runs.glob("*.json"))) == 3


def test_a_run_writes_a_record(dirs):
    runs, derivs = dirs
    with record("psd", {"method": "welch"}, "beta is higher during overt speech",
                runs_dir=runs, derivatives_dir=derivs) as run:
        pass
    rec = _read(runs, run.run_id)
    assert rec["status"] == "ok"
    assert rec["claim"] == "beta is higher during overt speech"
    assert rec["params"] == {"method": "welch"}


def test_a_run_without_a_claim_is_refused(dirs):
    """A result whose purpose was never stated cannot be reviewed."""
    runs, derivs = dirs
    with (
        pytest.raises(ValueError, match="needs a claim"),
        record("psd", {}, "   ", runs_dir=runs, derivatives_dir=derivs),
    ):
        pass


def test_failure_still_writes_a_record_and_reraises(dirs):
    """A run that vanishes when it breaks is a run nobody can debug."""
    runs, derivs = dirs
    with (
        pytest.raises(RuntimeError, match="boom"),
        record("psd", {}, "will fail", runs_dir=runs, derivatives_dir=derivs) as run,
    ):
        raise RuntimeError("boom")
    rec = _read(runs, run.run_id)
    assert rec["status"] == "failed"
    assert "boom" in rec["error"]


def test_inputs_are_hashed_and_keyed_not_pathed(dirs, tmp_path):
    """Guardrail G13: identify an input by manifest key and hash, not by location."""
    runs, derivs = dirs
    src = tmp_path / "outside" / "recording.mat"
    src.parent.mkdir()
    src.write_bytes(b"payload")
    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        digest = run.add_input(src, key={"study_id": "S01", "session": "ses1"})
    rec = _read(runs, run.run_id)
    entry = rec["inputs"][0]
    assert entry["sha256"] == digest
    assert entry["key"] == {"study_id": "S01", "session": "ses1"}
    assert entry["relpath"] is None, "a path outside the repo must not be recorded"


def test_a_path_inside_the_repo_is_withheld_unless_filenames_are_declared_safe(dirs):
    """The case that used to leak, and the reason G13 could never catch it.

    A lab that copies recordings into `data/` rather than symlinking them has an
    input that resolves INSIDE the repository, so the old code recorded its
    relative path, filename included, whatever the site had answered for
    `filenames_deidentified`. For the TDT formats that answer is false, measured:
    the date in a tank filename matched the acquisition date in the block's own
    notes 287 times out of 401 and was one day out 114 times. So the filename
    carried a date and the record carried the filename.

    `filenames_deidentified` defaults to False, so a caller that has not thought
    about it gets the safe behaviour.
    """
    runs, derivs = dirs
    inside = REPO_ROOT / "tests" / "fixtures" / "__init__.py"
    assert inside.exists(), "picking a file that really is inside the repo"

    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        run.add_input(inside, key={"study_id": "S01"})
    withheld = _read(runs, run.run_id)["inputs"][0]
    assert withheld["relpath"] is None, "a filename must not be recorded by default"
    assert withheld["sha256"], "the hash still identifies it"

    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        run.add_input(inside, key={"study_id": "S01"}, filenames_deidentified=True)
    allowed = _read(runs, run.run_id)["inputs"][0]
    assert allowed["relpath"] == "tests/fixtures/__init__.py"


def test_repo_relpath_answers_inside_and_outside():
    """One helper, because add_input and guardrail G13 must not disagree.

    When they did, G13 was handed the assertion "nothing writes a raw path"
    rather than the evidence, so `if not ctx.paths_in_outputs` returned early and
    the check could not fire on any run.
    """
    assert repo_relpath(REPO_ROOT / "pyproject.toml") == "pyproject.toml"
    assert repo_relpath("/etc/hostname") is None


def test_hash_matches_hashlib(dirs, tmp_path):
    import hashlib

    runs, derivs = dirs
    src = tmp_path / "f.bin"
    src.write_bytes(b"some bytes")
    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        digest = run.add_input(src)
    assert digest == hashlib.sha256(b"some bytes").hexdigest()


def test_outputs_are_discovered_and_relative(dirs):
    runs, derivs = dirs
    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        (run.out_dir / "psd_long.csv").write_text("x")
        (run.out_dir / "fig").mkdir()
        (run.out_dir / "fig" / "a.png").write_bytes(b"")
    rec = _read(runs, run.run_id)
    assert "psd_long.csv" in rec["outputs"]
    assert "fig/a.png" in rec["outputs"]
    assert not any(o.startswith("/") for o in rec["outputs"])


def test_config_snapshot_is_written_as_json_for_matlab(dirs):
    """YAML is the source of truth; JSON is what MATLAB can read."""
    runs, derivs = dirs
    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        run.snapshot_config({"bands": {"beta": [13, 30]}})
    snapshot = json.loads((run.out_dir / "config.json").read_text())
    assert snapshot["bands"]["beta"] == [13, 30]
    assert _read(runs, run.run_id)["config_sha256"] is not None


def test_config_hash_is_stable_across_key_order(dirs):
    runs, derivs = dirs
    hashes = []
    for cfg in ({"a": 1, "b": 2}, {"b": 2, "a": 1}):
        with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
            run.snapshot_config(cfg)
        hashes.append(_read(runs, run.run_id)["config_sha256"])
    assert hashes[0] == hashes[1]


def test_log_lines_land_in_the_output_dir(dirs):
    runs, derivs = dirs
    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        run.log("started")
        run.log("finished")
    text = (run.out_dir / "run.log").read_text()
    assert "started" in text and "finished" in text


def test_versions_cover_the_libraries_that_change_numbers(dirs):
    runs, derivs = dirs
    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        pass
    versions = _read(runs, run.run_id)["versions"]
    assert {"python", "numpy", "scipy"} <= set(versions)


def test_pydantic_params_are_accepted(dirs):
    pydantic = pytest.importorskip("pydantic")

    class Params(pydantic.BaseModel):
        fmin: float = 1.0

    runs, derivs = dirs
    with record("psd", Params(), "c", runs_dir=runs, derivatives_dir=derivs) as run:
        pass
    assert _read(runs, run.run_id)["params"] == {"fmin": 1.0}


# ---- store -------------------------------------------------------------------

def test_reindex_round_trips(dirs):
    runs, derivs = dirs
    ids = []
    for i in range(3):
        with record(f"r{i}", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
            ids.append(run.run_id)
    db = derivs / "runs.db"
    assert reindex(runs, db) == 3
    assert get_run(ids[0], db)["run_id"] == ids[0]


def test_list_runs_filters_by_status(dirs):
    runs, derivs = dirs
    with record("ok_run", {}, "c", runs_dir=runs, derivatives_dir=derivs):
        pass
    with (
        pytest.raises(RuntimeError),
        record("bad_run", {}, "c", runs_dir=runs, derivatives_dir=derivs),
    ):
        raise RuntimeError("x")
    db = derivs / "runs.db"
    reindex(runs, db)
    assert [r["name"] for r in list_runs(status="failed", db_path=db)] == ["bad_run"]


def test_index_records_guardrail_counts(dirs):
    runs, derivs = dirs
    with record("psd", {}, "c", runs_dir=runs, derivatives_dir=derivs) as run:
        run.guardrails = {
            "findings": [{"guardrail": "G1", "severity": "block"}],
            "overrides": [{"guardrail": "G1", "reason": "comparison"}],
        }
    db = derivs / "runs.db"
    reindex(runs, db)
    row = list_runs(db_path=db)[0]
    assert row["n_blocking"] == 1
    assert row["n_overrides"] == 1


def test_reindex_survives_a_corrupt_record(dirs):
    runs, derivs = dirs
    with record("good", {}, "c", runs_dir=runs, derivatives_dir=derivs):
        pass
    (runs / "broken.json").write_text("{not json")
    assert reindex(runs, derivs / "runs.db") == 1


def test_missing_run_returns_none(dirs):
    runs, derivs = dirs
    db = derivs / "runs.db"
    reindex(runs, db)
    assert get_run("nope", db) is None


# ---- paths never reach a run record ------------------------------------------

def test_a_repository_frame_keeps_the_file_and_line_a_developer_needs():
    from dbsspeech.runs.record import _REPO, redact_paths

    line = f'File "{_REPO}/src/dbsspeech/io/loader.py", line 325, in _sole_recording'
    assert redact_paths(line) == (
        'File "src/dbsspeech/io/loader.py", line 325, in _sole_recording'
    )


def test_a_frame_outside_the_repository_loses_its_path_and_keeps_its_line():
    """A library frame localizes a bug by function and line. The filename is the
    part that names somebody's home directory."""
    from dbsspeech.runs.record import redact_paths

    line = 'File "/home/somebody/env/lib/python3.12/site-packages/mne/io.py", line 12, in read'
    out = redact_paths(line)
    assert out == 'File "<path>", line 12, in read'
    assert "somebody" not in out


def test_a_failure_to_open_a_recording_cannot_write_the_filename():
    """The reason this exists. `runs/` is committed, a raw acquisition filename
    can carry a name and a date of surgery, and the message that reports a
    missing file quotes the path it tried."""
    from dbsspeech.runs.record import redact_paths

    message = (
        "FileNotFoundError: no tdt_mat recording in "
        "/mnt/sync/recordings/SURNAME_FIRST_2024-01-01/block"
    )
    out = redact_paths(message)
    assert "SURNAME" not in out
    assert "2024-01-01" not in out
    assert out.endswith("<path>")


def test_text_with_no_path_is_left_alone():
    from dbsspeech.runs.record import redact_paths

    assert redact_paths("ValueError: fmin must be below fmax") == (
        "ValueError: fmin must be below fmax"
    )
    assert redact_paths("") == ""


def test_a_recorded_failure_carries_no_absolute_path(dirs):
    """End to end, through the context manager that writes the record."""
    runs, derivs = dirs
    with pytest.raises(FileNotFoundError), record("psd", {}, "a run that fails",
                runs_dir=runs, derivatives_dir=derivs) as run:
        run_id = run.run_id
        raise FileNotFoundError(
            "no tdt_mat recording in /mnt/sync/rec/SURNAME_FIRST/block"
        )

    rec = _read(runs, run_id)
    assert rec["status"] == "failed"
    assert "SURNAME" not in rec["error"]
    assert "/mnt/sync" not in rec["error"]
    # The traceback is still there: redaction is not deletion.
    assert "FileNotFoundError" in rec["error"]
