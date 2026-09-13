"""coordinates.csv: contact positions, and what a position does not license.

Optional by design. A lab without imaging has none, every recipe must work
without them, and a missing file reads as an empty table rather than an error.

The subtler property is the one at the bottom of this file: a coordinate locates
a contact and says nothing about which way a directional segment faces. Adding
positions must not quietly unlock the anatomical direction claims that
invariant 10 gates on lead rotation.
"""

from __future__ import annotations

import pytest

from dbsspeech.manifest import Manifest, load_configs, load_manifest, validate

pytestmark = pytest.mark.unit


@pytest.fixture(scope="module")
def configs():
    return load_configs()


@pytest.fixture(scope="module")
def base():
    """A self-contained manifest with one subject and one lead.

    This used to be `load_manifest()`, the repository's own manifest, which held
    a real subject whose rows these tests leaned on. The public repository ships
    header-only manifests, so a test that needs a lead to exist has to declare
    one. Same lead model and contact naming as `dbsspeech seed`, so a coordinate
    row written here is one the demo could really carry.
    """
    return Manifest(
        subjects=[{"study_id": "demo01", "session": "ses1", "hemisphere": "R",
                   "format": "tdt_mat", "root_relpath": "block",
                   "acquisition": "demo", "acquisition_date": "", "notes": ""}],
        streams=[],
        leads=[{"study_id": "demo01", "session": "ses1", "lead_id": "lead1",
                "target": "stn", "hemisphere": "R",
                "lead_model": "unknown_directional_1331",
                "channel_first": "1", "channel_last": "8",
                "rotation_deg": "", "notes": ""}],
        channels=[], windows=[], coordinates=[],
    )


def _coord(**kwargs):
    row = {
        "study_id": "demo01",
        "session": "ses1",
        "lead_id": "lead1",
        "contact": "1",
        "x_mm": "-12.4",
        "y_mm": "-14.1",
        "z_mm": "-7.8",
        "space": "MNI152NLin2009bAsym",
        "source": "lead_dbs",
    }
    row.update(kwargs)
    return row


def _with(base: Manifest, rows) -> Manifest:
    return Manifest(
        subjects=base.subjects,
        streams=base.streams,
        leads=base.leads,
        channels=base.channels,
        windows=base.windows,
        coordinates=rows,
    )


def test_a_missing_coordinates_file_is_not_an_error(base, configs):
    """Every lab that has no imaging must still validate."""
    assert base.coordinates == []
    assert validate(base, configs).ok


def test_a_well_formed_row_validates(base, configs):
    assert validate(_with(base, [_coord()]), configs).ok


def test_a_lead_with_no_row_in_leads_csv_is_refused(base, configs):
    report = validate(_with(base, [_coord(lead_id="lead9")]), configs)
    assert not report.ok
    assert any("has no row in leads.csv" in e for e in report.errors)


def test_a_contact_not_on_that_lead_model_is_refused(base, configs):
    report = validate(_with(base, [_coord(contact="99")]), configs)
    assert not report.ok
    assert any("is not on" in e for e in report.errors)


def test_a_non_numeric_coordinate_is_refused(base, configs):
    report = validate(_with(base, [_coord(y_mm="posterior")]), configs)
    assert not report.ok
    assert any("y_mm must be a number" in e for e in report.errors)


def test_a_missing_axis_is_refused(base, configs):
    row = _coord()
    del row["z_mm"]
    report = validate(_with(base, [row]), configs)
    assert not report.ok
    assert any("z_mm must be a number" in e for e in report.errors)


def test_an_unknown_space_is_refused(base, configs):
    report = validate(_with(base, [_coord(space="somewhere")]), configs)
    assert not report.ok
    assert any("space" in e and "vocabulary" in e for e in report.errors)


def test_an_unknown_source_is_refused(base, configs):
    report = validate(_with(base, [_coord(source="vibes")]), configs)
    assert not report.ok
    assert any("source" in e and "vocabulary" in e for e in report.errors)


def test_the_same_contact_twice_is_refused(base, configs):
    report = validate(_with(base, [_coord(), _coord(x_mm="-12.5")]), configs)
    assert not report.ok
    assert any("duplicate" in e for e in report.errors)


def test_two_contacts_on_the_same_lead_are_fine(base, configs):
    rows = [_coord(contact="1"), _coord(contact="2a", z_mm="-5.8")]
    assert validate(_with(base, rows), configs).ok


def test_a_native_space_position_warns_that_it_is_not_comparable(base, configs):
    report = validate(_with(base, [_coord(space="native")]), configs)
    assert report.ok  # a warning, not an error
    assert any("not comparable across subjects" in w for w in report.warnings)


def test_a_coordinate_does_not_lift_the_rotation_warning(base, configs):
    """A position locates a contact; it does not say which way a segment faces."""
    report = validate(_with(base, [_coord()]), configs)
    assert any("rotation_deg empty" in w for w in report.warnings)


def test_the_vocabulary_says_which_spaces_are_comparable(configs):
    spaces = configs["vocabularies"]["coordinate_spaces"]
    assert spaces["native"]["comparable_across_subjects"] is False
    assert spaces["MNI152NLin2009bAsym"]["comparable_across_subjects"] is True
