"""Export bundles: everything needed to defend a result, in one file."""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from dbsspeech.runs import build_bundle

pytestmark = pytest.mark.unit


@pytest.fixture
def run(tmp_path):
    runs = tmp_path / "runs"
    runs.mkdir()
    out = tmp_path / "derivatives" / "results" / "r1"
    out.mkdir(parents=True)
    (out / "psd_db.png").write_bytes(b"\x89PNG")
    (out / "psd_long.csv").write_text("a,b\n1,2\n")
    (out / "config.json").write_text('{"bands": {"beta": [13, 30]}}')
    (runs / "r1.json").write_text(json.dumps({
        "run_id": "r1", "name": "psd_by_condition", "claim": "beta rises in overt speech",
        "user": "garrett", "status": "ok", "started_at": "2026-09-07T10:00:00+00:00",
        "git_commit": "abc1234", "git_dirty": False,
        "inputs": [{"key": {"study_id": "demo01"}, "sha256": "d" * 64}],
        "outputs": ["psd_db.png", "psd_long.csv"],
        "guardrails": {
            "findings": [{"guardrail": "G10_window_provenance", "severity": "warn",
                          "message": "the rest window is under revision"}],
            "overrides": [{"guardrail": "G1_shared_reference_common_mode",
                           "reason": "deliberate montage comparison"}],
        },
        "qc": {"status": "approved",
               "applied": [{"target": "lead1:2a", "effect": "dropped 2a from lead1"}]},
        "summary": {"normalization": {"sentence": "z = (value - grand mean) / pooled SD"}},
        "versions": {"python": "3.12.14", "numpy": "2.0.0"},
    }))
    return tmp_path


def _open(tmp_path, run_id="r1"):
    payload = build_bundle(run_id, runs_dir=tmp_path / "runs",
                           derivatives_dir=tmp_path / "derivatives")
    return zipfile.ZipFile(io.BytesIO(payload))


def test_figures_and_tables_are_sorted_into_folders(run):
    names = _open(run).namelist()
    assert "figures/psd_db.png" in names
    assert "tables/psd_long.csv" in names


def test_the_run_record_is_included(run):
    with _open(run).open("run.json") as f:
        assert json.load(f)["run_id"] == "r1"


def test_the_config_snapshot_is_the_one_that_ran(run):
    """A bundle picking up today's config would misrepresent what produced it."""
    names = _open(run).namelist()
    assert "configs/config.json" in names
    assert not any(n.startswith("configs/current/") for n in names)


def test_a_run_without_a_snapshot_says_the_configs_may_differ(run):
    (run / "derivatives" / "results" / "r1" / "config.json").unlink()
    archive = _open(run)
    assert "configs/NOTE.txt" in archive.namelist()
    assert "may differ" in archive.read("configs/NOTE.txt").decode()


def test_the_readme_answers_what_this_was(run):
    readme = _open(run).read("README.txt").decode()
    assert "beta rises in overt speech" in readme
    assert "garrett" in readme
    assert "abc1234" in readme


def test_the_readme_carries_the_guardrails_and_overrides(run):
    readme = _open(run).read("README.txt").decode()
    assert "G10_window_provenance" in readme
    assert "OVERRIDDEN" in readme
    assert "deliberate montage comparison" in readme


def test_the_readme_carries_what_qc_removed(run):
    readme = _open(run).read("README.txt").decode()
    assert "dropped 2a from lead1" in readme


def test_the_readme_warns_about_a_dirty_tree(run):
    record = json.loads((run / "runs" / "r1.json").read_text())
    record["git_dirty"] = True
    (run / "runs" / "r1.json").write_text(json.dumps(record))
    readme = _open(run).read("README.txt").decode()
    assert "in no commit" in readme
    assert "provisional" in readme


def test_the_readme_says_how_to_regenerate(run):
    assert "To regenerate" in _open(run).read("README.txt").decode()


def test_inputs_appear_as_keys_and_hashes_not_paths(run):
    readme = _open(run).read("README.txt").decode()
    assert "study_id=demo01" in readme
    assert "sha256 dddddddddddddddd" in readme


def test_an_unknown_run_raises(run):
    with pytest.raises(FileNotFoundError, match="no run record"):
        build_bundle("nope", runs_dir=run / "runs",
                     derivatives_dir=run / "derivatives")
