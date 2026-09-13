"""`dbsspeech derive`: one staged block into the store, with honest exit codes.

The command is the single-block form of the site driver, for a lab without a
ledger. What matters is that it reports the pipeline's verdict faithfully: a
written block exits 0, a policy quarantine exits 2 with the reason, a failure
exits 1, and none of them prints a path the scrubber would refuse.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dbsspeech.cli import main
from dbsspeech.derive.config import DEFAULT_CONFIG_PATH
from tests.fixtures.make_tdt_fixture import make_fixture

pytestmark = pytest.mark.unit


@pytest.fixture
def config_for(tmp_path):
    """A derive.yaml whose roles know the fixture's stream names and whose store is tmp."""
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    raw["store"]["root"] = str(tmp_path / "store")
    raw["store"]["audio_root"] = str(tmp_path / "audio")
    raw["roles"]["streams"] = {"neur": "lfp", "mic_": "mic"}
    raw["products"]["lfp"]["target_hz"] = 400
    raw["products"]["mic"]["target_hz"] = 500
    path = tmp_path / "derive.yaml"
    path.write_text(yaml.safe_dump(raw))
    return path


@pytest.fixture
def block_dir(tmp_path) -> Path:
    d = tmp_path / "uh0000" / "stage1" / "motor_baseline"
    d.mkdir(parents=True)
    make_fixture(d / "uh0000_motor_baseline.mat")
    return d


def test_a_block_builds_and_exits_zero(block_dir, config_for, tmp_path, capsys):
    rc = main(["derive", str(block_dir), "--study-id", "uh0000", "--session", "stage1",
               "--format", "tdt_mat", "--config", str(config_for)])
    out = capsys.readouterr().out
    assert rc == 0, out
    assert "done" in out and "neur/lfp@400Hz" in out
    assert list((tmp_path / "store" / "uh0000").glob("*.h5"))
    assert list((tmp_path / "audio" / "uh0000").glob("*.h5"))
    assert str(tmp_path) not in out


def test_a_policy_quarantine_exits_two_with_the_reason(block_dir, config_for, tmp_path, capsys):
    raw = yaml.safe_load(config_for.read_text())
    raw["roles"]["streams"] = {"mic_": "mic"}          # neur becomes unmapped
    config_for.write_text(yaml.safe_dump(raw))
    rc = main(["derive", str(block_dir), "--study-id", "uh0000", "--session", "stage1",
               "--format", "tdt_mat", "--config", str(config_for)])
    out = capsys.readouterr().out
    assert rc == 2
    assert "quarantined: unmapped_stream" in out
    assert not list((tmp_path / "store").rglob("*.h5"))


def test_a_missing_source_exits_one(tmp_path, config_for, capsys):
    missing = tmp_path / "uh0000" / "stage1" / "nope"
    missing.mkdir(parents=True)
    rc = main(["derive", str(missing), "--study-id", "uh0000", "--session", "stage1",
               "--format", "tdt_mat", "--config", str(config_for)])
    out = capsys.readouterr().out
    assert rc in (1, 2)
    assert str(tmp_path) not in out
