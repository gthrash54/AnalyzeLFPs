"""Impedance parsing and geometry detection, on synthesized sweeps.

Values are shaped like real hardware exports but invented, so nothing here
depends on a real recording.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from dbsspeech.detect import assess_contact_quality, classify_contacts, propose_lead_models
from dbsspeech.detect.geometry import RING, SEGMENT, geometry_from_labels
from dbsspeech.io.impedance import NOT_MEASURED, pair_differential, read_sweep

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def _write_sweep(path, values, freq=2240, ref=None, n=None):
    n = n or len(values)
    cols = ["TIME (S)", "FREQUENCY (Hz)"] + [f"R{i} (kOhm)" for i in range(1, n + 1)]
    if ref is not None:
        cols.append("REF (kOhm)")
    row = [22, freq] + list(values) + ([ref] if ref is not None else [])
    path.write_text(",".join(cols) + "\n" + ",".join(str(v) for v in row) + "\n")
    return path


RING_SEG_RING = [1.14, 2.33, 2.39, 2.32, 2.88, 2.67, 2.71, 1.49]


@pytest.fixture
def leads_config():
    return yaml.safe_load(open("configs/leads.yaml"))


def test_not_measured_sentinel_is_not_a_value(tmp_path):
    p = _write_sweep(tmp_path / "s.csv", [1.2, NOT_MEASURED, 1.4])
    sweep = read_sweep(p)
    assert sweep.values == {1: 1.2, 3: 1.4}
    assert sweep.missing(3) == [2]


def test_rows_merge_so_a_split_sweep_reads_as_one(tmp_path):
    p = tmp_path / "s.csv"
    p.write_text(
        "TIME (S),FREQUENCY (Hz),R1 (kOhm),R2 (kOhm)\n"
        "22,560,14.48,-1.00\n"
        "32,560,-1.00,13.35\n"
    )
    assert read_sweep(p).values == {1: 14.48, 2: 13.35}


def test_reference_and_frequency_are_captured(tmp_path):
    p = _write_sweep(tmp_path / "s.csv", [1.2, 1.3], ref=1.49)
    sweep = read_sweep(p)
    assert sweep.reference == 1.49
    assert sweep.frequency_hz == 2240


def test_ring_and_segment_classification(tmp_path):
    p = _write_sweep(tmp_path / "s.csv", RING_SEG_RING)
    labels = classify_contacts(read_sweep(p), 1, 8)
    assert labels == [RING] + [SEGMENT] * 6 + [RING]


def test_geometry_shorthand_from_labels():
    assert geometry_from_labels([RING] + [SEGMENT] * 6 + [RING]) == [1, 3, 3, 1]
    assert geometry_from_labels([RING] * 4) == [1, 1, 1, 1]


def test_directional_geometry_is_detected_and_vendor_is_not(tmp_path, leads_config):
    """Geometry is measurable; the manufacturer is not, so it is not guessed."""
    p = _write_sweep(tmp_path / "s.csv", RING_SEG_RING)
    proposal = propose_lead_models(read_sweep(p), 1, 8, leads_config)
    assert proposal.evidence["geometry"] == [1, 3, 3, 1]
    assert proposal.value.startswith("unknown"), "must not name a vendor it cannot see"
    assert proposal.prefill is False, "an unresolved vendor must not pre-select"
    assert len(proposal.alternatives) >= 2


def test_ring_only_lead_is_detected(tmp_path, leads_config):
    p = _write_sweep(tmp_path / "s.csv", [1.2, 1.25, 1.18, 1.3])
    proposal = propose_lead_models(read_sweep(p), 1, 4, leads_config)
    assert proposal.evidence["geometry"] == [1, 1, 1, 1]


def test_geometry_matching_no_configured_model_says_so(tmp_path, leads_config):
    p = _write_sweep(tmp_path / "s.csv", [1.1, 2.5, 1.2])
    proposal = propose_lead_models(read_sweep(p), 1, 3, leads_config)
    assert proposal.value is None
    assert "matches no model" in proposal.reason


def test_open_circuit_is_flagged(tmp_path):
    p = _write_sweep(tmp_path / "s.csv", [1.2, 536.87])
    flags = assess_contact_quality(read_sweep(p))
    assert [f.value for f in flags] == ["open_circuit"]
    assert flags[0].confidence >= 0.9


def test_high_impedance_is_flagged_separately_from_open(tmp_path):
    p = _write_sweep(tmp_path / "s.csv", [1.2, 37.34])
    assert [f.value for f in assess_contact_quality(read_sweep(p))] == ["high_impedance"]


def test_differential_channel_is_only_as_good_as_its_worse_electrode(tmp_path):
    """An EMG channel with one good and one open electrode is an open channel."""
    p = _write_sweep(tmp_path / "s.csv", [9.34, 536.87])
    sweep = read_sweep(p)
    flags = assess_contact_quality(sweep, pairs=pair_differential(sweep))
    assert [f.value for f in flags] == ["open_circuit"]
    assert flags[0].evidence["electrodes"] == (1, 2)


def test_clean_contacts_produce_no_flags(tmp_path):
    p = _write_sweep(tmp_path / "s.csv", RING_SEG_RING)
    assert assess_contact_quality(read_sweep(p)) == []


def test_every_lead_declares_a_row_spacing_and_whether_it_is_confirmed():
    """Physical geometry has to be a field, not a phrase inside a model name.

    REC 5 computes distances from contact spacing and had to sweep a plausible
    range because the only spacing in this config lived inside strings like
    "3389 (1.5 mm spacing)". A number a program cannot read is not configuration.

    The paired flag matters as much as the number. Vendor literature uses
    "spacing" for both the centre-to-centre pitch and the gap between contact
    edges, and those differ by a factor of two on a typical lead, so a
    transcribed number is not a verified one.
    """
    leads = yaml.safe_load((REPO_ROOT / "configs" / "leads.yaml").read_text())["leads"]
    assert leads, "no leads configured"
    for name, spec in leads.items():
        assert "row_spacing_mm" in spec, f"{name} does not declare row_spacing_mm"
        assert "spacing_confirmed" in spec, f"{name} does not say whether it is confirmed"
        spacing = spec["row_spacing_mm"]
        assert spacing is None or (isinstance(spacing, (int, float)) and spacing > 0), (
            f"{name}: row_spacing_mm must be a positive number or null, got {spacing!r}"
        )
        if spec["spacing_confirmed"]:
            assert spacing is not None, (
                f"{name} claims a confirmed spacing without giving one"
            )


def test_no_distance_is_computed_from_an_unconfirmed_spacing():
    """Nothing may quietly use a spacing nobody has checked.

    Every entry is currently unconfirmed, so the correct number of places in the
    package reading this field is zero. When the first one appears it has to
    refuse on `spacing_confirmed: false` rather than proceed, and this test is
    where that intention is written down.
    """
    leads = yaml.safe_load((REPO_ROOT / "configs" / "leads.yaml").read_text())["leads"]
    unconfirmed = [n for n, s in leads.items() if not s["spacing_confirmed"]]
    readers = [
        path
        for path in (REPO_ROOT / "src").rglob("*.py")
        if "row_spacing_mm" in path.read_text()
    ]
    assert not readers or not unconfirmed, (
        f"{[p.name for p in readers]} read row_spacing_mm while "
        f"{unconfirmed} are unconfirmed; a reader must check spacing_confirmed first"
    )
