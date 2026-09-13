"""The derive policy: refuses typos, hashes stably, and ships sane defaults.

The property that matters most is the last one below: two configs that differ
only in key order or whitespace must hash the same, and two that differ in any
value must not. The ledger uses this hash to decide which blocks a policy
change reopens, so a hash that moved for no reason would rebuild the store and
a hash that failed to move would leave stale derivatives in place.
"""

from __future__ import annotations

import pathlib

import pytest
import yaml
from pydantic import ValidationError

from dbsspeech.derive.config import DEFAULT_CONFIG_PATH, DeriveConfig, load_config

pytestmark = pytest.mark.unit


def test_the_shipped_config_loads_and_names_every_role_a_product():
    cfg = load_config()
    assert cfg.schema_version == 1
    for role in ("lfp", "emg", "mic", "micro", "monitor"):
        assert cfg.product_for(role) is not None, role


def test_the_shipped_policy_matches_the_decisions_on_record():
    """8 kHz LFP, 16 kHz mic, 2 kHz EMG, native microelectrode."""
    cfg = load_config()
    assert cfg.products["lfp"].target_hz == 8000
    assert cfg.products["mic"].target_hz == 16000
    assert cfg.products["emg"].target_hz == 2000
    assert cfg.products["micro"].target_hz == "native"
    assert cfg.referencing.apply == "none"
    assert cfg.roles.on_unmapped == "quarantine"


def test_the_store_root_is_outside_the_repository_and_expands_home():
    cfg = load_config()
    root = cfg.store.root_path()
    assert root.is_absolute()
    assert "~" not in str(root)
    # The invariant is that the derivative store lives OUTSIDE the repository,
    # so a sync client or a `git add -A` can never pick it up. This used to
    # assert that one particular username was absent from the path, which
    # passed vacuously anywhere but the machine it was written on.
    repo = pathlib.Path(__file__).resolve().parents[2]
    assert repo not in root.parents and root != repo, (
        f"the derivative store must not sit inside the repository: {root}"
    )


def test_an_unknown_key_is_an_error_not_a_silently_ignored_setting():
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    raw["store"]["chunk_target_byts"] = 1  # typo
    with pytest.raises(ValidationError):
        DeriveConfig.model_validate(raw)


def test_a_product_for_a_nonexistent_role_is_refused():
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    raw["products"]["video"] = {"name": "vid", "target_hz": 100}
    with pytest.raises(ValidationError, match="not a role"):
        DeriveConfig.model_validate(raw)


def test_a_bad_regex_is_refused_at_load_time():
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    raw["roles"]["channel_patterns"]["lfp"].append("([unclosed")
    with pytest.raises(ValidationError):
        DeriveConfig.model_validate(raw)


def test_the_hash_ignores_layout_and_tracks_values():
    raw = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text())
    a = DeriveConfig.model_validate(raw)

    reordered = dict(reversed(list(raw.items())))
    b = DeriveConfig.model_validate(reordered)
    assert a.sha256() == b.sha256()

    raw["products"]["lfp"]["target_hz"] = 1000
    c = DeriveConfig.model_validate(raw)
    assert c.sha256() != a.sha256()
