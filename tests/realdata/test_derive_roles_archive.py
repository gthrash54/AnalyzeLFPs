"""The shipped role policy against every name the staged archive actually carries.

Guards one property: `configs/derive.yaml` and the archive cannot drift apart
unnoticed. Every stream name in every staged TDT index and every channel name
in every staged BrainVision header is run through the classifier, and the set
of names it cannot place is asserted to be EXACTLY the set already known and
recorded here. A new unmapped name fails this test; so does fixing the config,
which is the prompt to shrink the known set and drop the matching strict
xfail markers in tests/unit/test_derive_roles.py.

Only structure is read. The TDT reader opens on the `.tsq` index alone and
`read()` is never called, so this runs on the index staging tier without any
`.tev` present. Headers are parsed by `dbsspeech.derive.bvheader.read_header`,
which never opens the `.eeg`.

Skipped when the staging archive is absent. Its default location is
`~/DBS Data` (see docs); `DBSSPEECH_ARCHIVE` overrides it. Nothing under
`_inventory/` or `_tools/` is ever listed, because the globs start at the
`u[gh]*` study folders. No path from the archive appears in an assertion
message; only counts and channel or store names do.
"""

from __future__ import annotations

import contextlib
import os
from collections import Counter
from pathlib import Path

import pytest

from dbsspeech.derive.bvheader import read_header
from dbsspeech.derive.config import DeriveConfig, load_config
from dbsspeech.derive.model import Quarantine
from dbsspeech.derive.roles import classify_channels, classify_stream
from dbsspeech.io.tdt_tank import TdtTankRecording

pytestmark = pytest.mark.realdata

# Channel names the shipped policy is known not to place, by reason. Update
# these when configs/derive.yaml changes; the assertions below are exact.
# Both empty since 2026-09-09: the mic pattern no longer swallows micro_raw, and
# the bare Alpha Omega inputs ao_1..ao_3 are ignored (see docs/backlog.md for
# the blank-pin role they should eventually get). A name appearing here again
# means the shipped policy regressed against the archive.
KNOWN_UNMAPPED_CHANNELS: frozenset[str] = frozenset()
KNOWN_AMBIGUOUS_CHANNELS: frozenset[str] = frozenset()
KNOWN_UNMAPPED_STREAMS: frozenset[str] = frozenset()


def _archive_root() -> Path:
    return Path(os.environ.get("DBSSPEECH_ARCHIVE", "~/DBS Data")).expanduser()


@pytest.fixture(scope="module")
def archive() -> Path:
    root = _archive_root()
    if not root.is_dir():
        pytest.skip("staging archive not present; set DBSSPEECH_ARCHIVE or stage to ~/DBS Data")
    return root


@pytest.fixture(scope="module")
def shipped() -> DeriveConfig:
    return load_config()


@pytest.fixture(scope="module")
def tank_names(archive: Path) -> tuple[Counter[str], Counter[str], list[set[str]]]:
    """Per-file counts of stream and epoch store names, plus each file's stream set.

    Paths stay local to this fixture on purpose: tank filenames carry an
    acquisition timestamp, and a fixture argument is rendered in a failure
    trace. Only names and counts leave here.
    """
    paths = sorted(archive.glob("u[gh]*/**/*.tsq"))
    if not paths:
        pytest.skip("no staged .tsq indexes under the archive")
    streams: Counter[str] = Counter()
    epochs: Counter[str] = Counter()
    per_file: list[set[str]] = []
    for path in paths:
        rec = TdtTankRecording(path)
        names = set(rec.streams)
        streams.update(names)
        epochs.update(set(rec.epochs))
        per_file.append(names)
    return streams, epochs, per_file


@pytest.fixture(scope="module")
def header_names(archive: Path) -> tuple[Counter[str], list[list[str]]]:
    """Per-file counts of channel names, plus each file's channel list in order."""
    paths = sorted(archive.glob("u[gh]*/**/*.vhdr"))
    if not paths:
        pytest.skip("no staged .vhdr headers under the archive")
    counts: Counter[str] = Counter()
    per_file: list[list[str]] = []
    for path in paths:
        names = list(read_header(path).channel_names)
        counts.update(set(names))
        per_file.append(names)
    return counts, per_file


def test_epoch_stores_never_appear_as_streams(tank_names):
    streams, epochs, _ = tank_names
    leaked = set(streams) & set(epochs)
    assert not leaked, f"epoch stores listed under .streams: {sorted(leaked)}"
    slashed = {n for n in streams if "/" in n}
    assert not slashed, f"epoch-style names under .streams: {sorted(slashed)}"


def test_every_staged_stream_name_maps_except_the_known_set(shipped, tank_names):
    streams, _, _ = tank_names
    unmapped: dict[str, int] = {}
    for name, n_files in sorted(streams.items()):
        try:
            classify_stream(name, shipped)
        except Quarantine as exc:
            assert exc.reason == "unmapped_stream"
            unmapped[name] = n_files
    assert set(unmapped) == set(KNOWN_UNMAPPED_STREAMS), (
        f"unmapped stream names and file counts: {unmapped}"
    )


def test_every_staged_channel_name_maps_except_the_known_sets(shipped, header_names):
    counts, _ = header_names
    unmapped: dict[str, int] = {}
    ambiguous: dict[str, int] = {}
    for name, n_files in sorted(counts.items()):
        try:
            classify_channels([name], shipped)
        except Quarantine as exc:
            if exc.reason == "unmapped_channel":
                unmapped[name] = n_files
            elif exc.reason == "ambiguous_channel":
                ambiguous[name] = n_files
            else:
                raise
    assert set(unmapped) == set(KNOWN_UNMAPPED_CHANNELS), (
        f"unmapped channel names and file counts: {unmapped}"
    )
    assert set(ambiguous) == set(KNOWN_AMBIGUOUS_CHANNELS), (
        f"ambiguous channel names and file counts: {ambiguous}"
    )


def test_whole_headers_fail_only_because_of_the_known_names(shipped, header_names):
    """A header quarantines if and only if it carries a known-gap name."""
    _, per_file = header_names
    known = KNOWN_UNMAPPED_CHANNELS | KNOWN_AMBIGUOUS_CHANNELS
    mismatches = 0
    for names in per_file:
        expected_fail = bool(set(names) & known)
        try:
            classify_channels(names, shipped)
        except Quarantine:
            failed = True
        else:
            failed = False
        mismatches += failed != expected_fail
    assert mismatches == 0, f"{mismatches} headers fail or pass for a reason not listed here"


def test_every_tank_has_at_least_one_stream_that_maps(shipped, tank_names):
    _, _, per_file = tank_names
    empty = 0
    for names in per_file:
        roles = set()
        for name in names:
            with contextlib.suppress(Quarantine):
                roles.add(classify_stream(name, shipped))
        empty += not roles
    assert empty == 0, f"{empty} tanks would produce nothing under the shipped policy"
