"""A block can be planned from its `.vhdr` alone, with no `.eeg` on disk.

The property guarded here is that every layout fact the builder needs before
fetching the bulk file (rate, channel count, binary format, orientation, the
names of the sibling files) comes out of the header text exactly, across the
irregularities the format documents: free text in `[Comment]`, `;` comments,
a comma escaped as `\\1` inside a channel name, omitted fields, CRLF endings,
and a header that is not UTF-8. Nothing here touches sample data, because the
whole point is that none exists yet when this runs.

The second thing pinned is that a malformed header fails loudly, as a
`ValueError` and nothing else, and names the key it could not accept, so a
planning failure is diagnosable from the ledger line without opening the
file. That includes values Python would happily parse into something wrong:
`nan`, `inf`, an overflowing literal, or a fractional channel count.

The third is that the error message is ledger-safe: it never carries the
`.vhdr` filename, because `configs/privacy.yaml` declares BrainVision export
names as not de-identified.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dbsspeech.derive.bvheader import (
    DEFAULT_SOURCE,
    BvChannel,
    BvHeader,
    parse_header,
    read_header,
)

pytestmark = pytest.mark.unit

MAGIC = "Brain Vision Data Exchange Header File Version 1.0"

# Modeled on the actiCHamp export layout, with synthetic values throughout.
# The [Comment] block deliberately has the shape of real amplifier text that
# configparser cannot digest: a bare word followed by an indented table line,
# a rule of equals signs, and a duplicated line. If the parser ever stops
# discarding [Comment] before reading the INI, this fixture fails to parse.
MINIMAL = f"""{MAGIC}
; Data created by a synthetic test fixture

[Common Infos]
Codepage=UTF-8
DataFile=block.eeg
MarkerFile=block.vmrk
DataFormat=BINARY
; Data orientation: MULTIPLEXED=ch1,pt1, ch2,pt1 ...
DataOrientation=MULTIPLEXED
NumberOfChannels=3
; Sampling interval in microseconds
SamplingInterval=20

[Binary Infos]
BinaryFormat=IEEE_FLOAT_32

[Channel Infos]
; Each entry: Ch<Channel number>=<Name>,<Reference channel name>,
; <Scaling factor in "Unit">,<Unit>, Future extensions..
; Commas in channel names are coded as "\\1".
Ch1=ECOG_A1,,1.0,µV
Ch2=ECOG_A2,REF,0.5,µV
Ch3=STIM\\1MON,,,

[Comment]
Synthetic recorder V0.0

Amplifier
Module 1  (5010) SN: 0000000
Module 2  n.a.
Module 2  n.a.
Version: DLL_00.00.00.00

Reference channel: ref

Impedance [KOhm] at 00:00:00 (recording started at 00:00:00)
  1 ECOG_A1: 14
  2 ECOG_A2: Out of Range!
  3 STIM,MON: 9

Channels
=======
  1  ECOG_A1  1  0.1 µV  DC  280 Hz  Off
"""


def _write(tmp_path: Path, text: str, encoding: str = "utf-8") -> Path:
    p = tmp_path / "block.vhdr"
    p.write_bytes(text.encode(encoding))
    return p


# ---- the layout facts come out exactly ----------------------------------------


def test_the_header_parses_without_any_eeg_or_vmrk_beside_it(tmp_path):
    p = _write(tmp_path, MINIMAL)
    assert not (tmp_path / "block.eeg").exists()
    hdr = read_header(p)
    assert isinstance(hdr, BvHeader)
    assert hdr.data_file == "block.eeg"
    assert hdr.marker_file == "block.vmrk"


def test_the_sampling_rate_is_one_million_over_the_interval_in_microseconds():
    hdr = parse_header(MINIMAL)
    assert hdr.sampling_interval_us == 20.0
    assert hdr.sfreq_hz == 50000.0


@pytest.mark.parametrize(
    ("interval", "sfreq"), [("100", 10000.0), ("40", 25000.0), ("1000", 1000.0)]
)
def test_every_archive_interval_maps_to_its_round_rate(interval, sfreq):
    hdr = parse_header(MINIMAL.replace("SamplingInterval=20", f"SamplingInterval={interval}"))
    assert hdr.sfreq_hz == sfreq


def test_binary_format_and_orientation_are_reported_as_written():
    hdr = parse_header(MINIMAL)
    assert hdr.binary_format == "IEEE_FLOAT_32"
    assert hdr.data_orientation == "MULTIPLEXED"
    assert hdr.n_channels == 3


def test_bytes_per_sample_follows_the_binary_format():
    assert parse_header(MINIMAL).bytes_per_sample == 4
    hdr = parse_header(MINIMAL.replace("IEEE_FLOAT_32", "INT_16"))
    assert hdr.bytes_per_sample == 2
    with pytest.raises(ValueError, match="BinaryFormat"):
        _ = parse_header(MINIMAL.replace("IEEE_FLOAT_32", "SOMETHING_ELSE")).bytes_per_sample


# ---- channel entries ----------------------------------------------------------


def test_channels_come_back_in_order_with_one_based_indices():
    hdr = parse_header(MINIMAL)
    assert [ch.index for ch in hdr.channels] == [1, 2, 3]
    assert hdr.channel_names == ("ECOG_A1", "ECOG_A2", "STIM,MON")
    assert hdr.channels[1] == BvChannel(
        index=2, name="ECOG_A2", reference="REF", resolution=0.5, unit="µV"
    )


def test_the_documented_comma_escape_becomes_a_comma_in_the_name():
    assert parse_header(MINIMAL).channels[2].name == "STIM,MON"


def test_a_missing_resolution_is_none_and_a_missing_unit_defaults_to_microvolts():
    ch = parse_header(MINIMAL).channels[2]
    assert ch.resolution is None
    assert ch.unit == "µV"
    assert ch.reference == ""


def test_channel_entries_out_of_key_order_are_sorted_by_index():
    text = MINIMAL.replace(
        "Ch1=ECOG_A1,,1.0,µV\nCh2=ECOG_A2,REF,0.5,µV\nCh3=STIM\\1MON,,,",
        "Ch3=STIM\\1MON,,,\nCh1=ECOG_A1,,1.0,µV\nCh2=ECOG_A2,REF,0.5,µV",
    )
    assert parse_header(text).channel_names == ("ECOG_A1", "ECOG_A2", "STIM,MON")


# ---- the irregularities the format documents ---------------------------------


def test_the_free_text_comment_section_is_discarded_before_the_ini_is_read():
    """The fixture's [Comment] is amplifier text configparser cannot read.

    Parsing succeeds only because everything from the `[Comment]` line on is
    dropped first; the same text with that one line removed must fail, and
    fail as a ValueError. This pins the strip as the thing that makes the
    archive parse, not a tolerance in configparser.
    """
    hdr = parse_header(MINIMAL)
    assert hdr.n_channels == 3
    assert hdr.channel_names == ("ECOG_A1", "ECOG_A2", "STIM,MON")

    without_comment_line = MINIMAL.replace("[Comment]\n", "")
    assert "Amplifier" in without_comment_line
    with pytest.raises(ValueError, match="malformed header"):
        parse_header(without_comment_line)


def test_the_comment_section_header_is_matched_case_insensitively_with_padding():
    assert parse_header(MINIMAL.replace("[Comment]", "  [ comment ]  ")).n_channels == 3


def test_a_bare_word_followed_by_an_indented_line_in_a_key_section_is_a_value_error():
    """CPython's configparser raises a bare AttributeError on this shape when a
    valueless key is allowed; the contract is a ValueError naming the source."""
    text = MINIMAL.replace("SamplingInterval=20\n", "SamplingInterval=20\nNotes\n  extra text\n")
    with pytest.raises(ValueError, match=DEFAULT_SOURCE):
        parse_header(text)


def test_a_misspelled_comment_section_is_a_value_error_not_an_attribute_error():
    text = MINIMAL.replace("[Comment]", "[Comments]")
    with pytest.raises(ValueError):
        parse_header(text)


def test_semicolon_comment_lines_inside_key_sections_are_ignored():
    hdr = parse_header(MINIMAL)
    assert hdr.n_channels == 3
    assert all(not ch.name.startswith(";") for ch in hdr.channels)


def test_windows_line_endings_parse_identically(tmp_path):
    p = _write(tmp_path, MINIMAL.replace("\n", "\r\n"))
    assert read_header(p) == parse_header(MINIMAL)


def test_a_latin1_header_is_decoded_on_utf8_failure(tmp_path):
    """The micro sign is 0xB5 in latin-1, which is not valid UTF-8 on its own."""
    p = _write(tmp_path, MINIMAL, encoding="latin-1")
    with pytest.raises(UnicodeDecodeError):
        p.read_bytes().decode("utf-8")
    hdr = read_header(p)
    assert hdr.channels[0].unit == "µV"
    assert hdr.sfreq_hz == 50000.0


def test_a_utf8_byte_order_mark_does_not_hide_the_magic_line(tmp_path):
    p = _write(tmp_path, MINIMAL, encoding="utf-8-sig")
    assert read_header(p).sfreq_hz == 50000.0


def test_a_header_without_a_marker_file_is_still_valid():
    hdr = parse_header(MINIMAL.replace("MarkerFile=block.vmrk\n", ""))
    assert hdr.marker_file == ""


# ---- malformed headers fail loudly and name the key --------------------------


@pytest.mark.parametrize(
    ("line", "key"),
    [
        ("SamplingInterval=20\n", "SamplingInterval"),
        ("NumberOfChannels=3\n", "NumberOfChannels"),
        ("DataFile=block.eeg\n", "DataFile"),
        ("DataFormat=BINARY\n", "DataFormat"),
        ("DataOrientation=MULTIPLEXED\n", "DataOrientation"),
        ("BinaryFormat=IEEE_FLOAT_32\n", "BinaryFormat"),
    ],
)
def test_a_missing_required_key_is_named_in_the_error(line, key):
    with pytest.raises(ValueError, match=key):
        parse_header(MINIMAL.replace(line, ""))


def test_a_missing_section_is_named_in_the_error():
    text = MINIMAL.replace("[Binary Infos]\nBinaryFormat=IEEE_FLOAT_32\n", "")
    with pytest.raises(ValueError, match=r"\[Binary Infos\]"):
        parse_header(text)


def test_a_channel_count_that_disagrees_with_the_entries_is_refused():
    with pytest.raises(ValueError, match="NumberOfChannels"):
        parse_header(MINIMAL.replace("NumberOfChannels=3", "NumberOfChannels=4"))


def test_a_non_numeric_interval_is_refused():
    with pytest.raises(ValueError, match="SamplingInterval"):
        parse_header(MINIMAL.replace("SamplingInterval=20", "SamplingInterval=fast"))


@pytest.mark.parametrize("bad", ["nan", "inf", "-inf", "1e400", "-20", "0"])
def test_a_non_finite_or_non_positive_interval_is_refused_not_turned_into_a_rate(bad):
    """`nan` would give sfreq nan; `inf` and `1e400` would give sfreq 0.0."""
    with pytest.raises(ValueError, match="SamplingInterval"):
        parse_header(MINIMAL.replace("SamplingInterval=20", f"SamplingInterval={bad}"))


@pytest.mark.parametrize("bad", ["nan", "inf", "1e400", "2.7", "3.0", "three", ""])
def test_a_channel_count_that_is_not_an_integer_is_a_value_error_naming_the_key(bad):
    """int() refuses all of these; float() would accept the first five and either
    overflow, raise a message with no key name, or silently truncate."""
    with pytest.raises(ValueError, match="NumberOfChannels"):
        parse_header(MINIMAL.replace("NumberOfChannels=3", f"NumberOfChannels={bad}"))


def test_a_zero_or_negative_channel_count_is_refused():
    for bad in ("0", "-3"):
        with pytest.raises(ValueError, match="NumberOfChannels"):
            parse_header(MINIMAL.replace("NumberOfChannels=3", f"NumberOfChannels={bad}"))


@pytest.mark.parametrize("bad", ["nan", "inf", "1e400", "0", "-1.0", "big"])
def test_a_resolution_that_is_not_a_finite_positive_number_is_refused(bad):
    with pytest.raises(ValueError, match="Ch2"):
        parse_header(MINIMAL.replace("Ch2=ECOG_A2,REF,0.5,µV", f"Ch2=ECOG_A2,REF,{bad},µV"))


def test_a_channel_entry_with_no_name_is_refused():
    with pytest.raises(ValueError, match="Ch1"):
        parse_header(MINIMAL.replace("Ch1=ECOG_A1,,1.0,µV", "Ch1=,,1.0,µV"))


def test_channel_keys_that_skip_an_index_are_refused():
    text = MINIMAL.replace("Ch3=STIM\\1MON,,,", "Ch4=STIM\\1MON,,,")
    with pytest.raises(ValueError, match="Ch1..Ch3"):
        parse_header(text)


def test_a_file_that_is_not_a_brainvision_header_is_refused():
    with pytest.raises(ValueError, match="magic"):
        parse_header("[Common Infos]\nSamplingInterval=20\n")


def test_an_ascii_data_format_is_refused_because_it_describes_no_eeg():
    with pytest.raises(ValueError, match="DataFormat"):
        parse_header(MINIMAL.replace("DataFormat=BINARY", "DataFormat=ASCII"))


def test_the_header_is_immutable():
    hdr = parse_header(MINIMAL)
    with pytest.raises(AttributeError):
        hdr.sfreq_hz = 1.0  # type: ignore[misc]


# ---- error messages are ledger-safe -------------------------------------------


def test_read_header_errors_never_carry_the_filename(tmp_path):
    """A BrainVision export name is not de-identified; it must not reach the ledger."""
    p = tmp_path / "SUBJECT_export_surgery.vhdr"
    p.write_text(MINIMAL.replace("SamplingInterval=20\n", ""), encoding="utf-8")
    with pytest.raises(ValueError) as info:
        read_header(p)
    message = str(info.value)
    assert p.stem not in message
    assert p.name not in message
    assert str(tmp_path) not in message
    assert message.startswith(DEFAULT_SOURCE)


def test_a_caller_supplied_source_label_replaces_the_neutral_token(tmp_path):
    p = _write(tmp_path, MINIMAL.replace("SamplingInterval=20\n", ""))
    with pytest.raises(ValueError, match=r"^ug0003/ses-01/block7: "):
        read_header(p, source="ug0003/ses-01/block7")
