"""The demo project: built, reviewed, and run, on synthetic data.

This is the ten-minute path for a new lab member, so it is worth a test that
actually walks it. It is also the only test that runs every registered recipe in
one pass, which is how a recipe that breaks on a short recording gets noticed
before someone else finds it.
"""

from __future__ import annotations

import json

import pytest

from dbsspeech.seed import REVIEWER, STUDY_ID, seed

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    root = tmp_path_factory.mktemp("demo_root") / "demo"
    return seed(root=root, log=lambda *_: None)


def test_every_registered_recipe_runs(seeded):
    from dbsspeech.recipes import available

    assert seeded.failures == {}
    assert set(seeded.runs) == set(available())


def test_the_subject_passes_the_real_gate(seeded):
    """Nothing here switches the gate off; the demo goes through the workflow."""
    assert seeded.qc_status == "approved"
    assert seeded.n_flags > 0


def test_the_stimulating_contacts_are_kept_with_a_reason(seeded):
    """Detection proposes excluding them, and excluding them deletes the ERNA."""
    import csv

    path = seeded.root / "derivatives" / "qc" / f"sub-{STUDY_ID}" / "decisions.tsv"
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f, delimiter="\t"))

    kept = [r for r in rows if r["action_taken"] == "none"]
    assert kept, "the stimulating contacts should have been kept"
    for row in kept:
        assert row["approved"] == "true"      # the flag is real
        assert "stimulation artifact" in row["reason"]
        assert row["reviewer"] == REVIEWER


def test_the_erna_run_found_the_planted_resonance(seeded):
    """End to end: fixture, QC, gate, recipe, record."""
    from dbsspeech.demo_data import ERNA_FREQ_HZ

    run_id = seeded.runs["erna"]
    record = json.loads((seeded.root / "runs" / f"{run_id}.json").read_text())
    assert record["status"] == "ok"
    recovered = record["summary"]["median_frequency_hz"]
    assert abs(recovered - ERNA_FREQ_HZ) / ERNA_FREQ_HZ < 0.10


def test_runs_are_attributed_to_the_demo_reviewer(seeded):
    for run_id in seeded.runs.values():
        record = json.loads((seeded.root / "runs" / f"{run_id}.json").read_text())
        assert record["user"] == REVIEWER
        assert record["claim"]


def test_nothing_was_written_outside_the_demo_root(seeded):
    """A demo that pollutes the real provenance log is worse than no demo."""
    repo_runs = seeded.root.parent.parent
    assert seeded.root in (seeded.root / "runs").parents
    for run_id in seeded.runs.values():
        assert (seeded.root / "runs" / f"{run_id}.json").exists()
        assert not (repo_runs / "runs" / f"{run_id}.json").exists()


def test_seeding_twice_refuses_rather_than_overwriting(seeded):
    with pytest.raises(FileExistsError, match="overwrite"):
        seed(root=seeded.root, log=lambda *_: None)


def test_overwrite_rebuilds_it(tmp_path):
    root = tmp_path / "demo"
    first = seed(root=root, log=lambda *_: None)
    second = seed(root=root, overwrite=True, log=lambda *_: None)
    assert second.runs and second.runs != first.runs
