"""Read a BrainVision `.vhdr` as text, without the `.eeg` beside it.

The derivative builder plans a block from the staged index tier before the
bulk `.eeg` has been fetched: which rate, how many channels, what binary
layout, how large the fetch will be. `mne.io.read_raw_brainvision` cannot help
there because it opens the `.eeg` on construction to establish the recording
length, and refuses when it is absent. This module reads only the header.

Why this lives in `derive/` and not `io/`: CLAUDE.md reserves the opening of
raw BrainVision files for `src/dbsspeech/io/`, and that rule exists so sample
data never flows through an unaudited path. This module never touches sample
data; it reads the text index of a recording, which is what the planner needs
and all the planner may have. It is the header-only counterpart of
`io/brainvision.py`, kept next to the planner that consumes it. That exception
is an engineering decision that belongs in `docs/decisions.md`; if it is ever
revisited, only the import in the planner changes.

The `.vhdr` is an INI file with one documented irregularity: the trailing
`[Comment]` section is free text (amplifier serials, an impedance table), not
key=value pairs, so everything from that line on is dropped before
`configparser.ConfigParser.read_string` sees the rest. That is the same
truncation MNE performs internally. Within the three key sections the format
never uses multi-line values, so the parser is run with `allow_no_value=False`
and every line is stripped of leading whitespace first: a line without `=` is
then a parse error and can never act as an INI continuation line. Channel
entries follow the documented form `Ch<n>=<name>,<reference>,<resolution>,
<unit>`, with a comma inside a name written as the escape `\\1`.

Required keys: `DataFile`, `DataFormat` (must be `BINARY`; an ASCII header
describes no `.eeg`), `DataOrientation`, `NumberOfChannels`, and
`SamplingInterval` in `[Common Infos]`; `BinaryFormat` in `[Binary Infos]`;
one `Ch<n>` per channel in `[Channel Infos]`. `MarkerFile` is optional.
`SamplingInterval` and every stated resolution must be finite and positive
(checked with `math.isfinite`), because a NaN or zero rate would propagate
silently into resample planning.

Nothing here computes the number of samples. That needs the size of the
`.eeg` and belongs to whoever has it. `BvHeader.bytes_per_sample` is provided
so that caller can do the division without knowing the format table.

Privacy: a `.vhdr` names its data and marker files, and a BrainVision export
may carry an identifier in those names, as may the `.vhdr` filename itself.
The parsed names are returned because the loader needs them to find the bulk
file; they must not be written into a derivative, a run record, or a log.
Error messages are ledger-safe by construction: they name keys and sections,
never header values, and `read_header` labels them with the neutral token
`<vhdr>` rather than the filename unless the caller supplies its own
already-redacted label through `source`.
"""

from __future__ import annotations

import configparser
import math
import re
from dataclasses import dataclass
from pathlib import Path

MAGIC_PREFIX = "Brain Vision Data Exchange Header File"

# The label error messages carry when the caller does not supply one. It is
# deliberately not the filename: see the privacy note in the module docstring.
DEFAULT_SOURCE = "<vhdr>"

_COMMON = "Common Infos"
_BINARY = "Binary Infos"
_CHANNELS = "Channel Infos"
_COMMENT = "Comment"

# The BrainVision escape for a comma inside a channel name.
_COMMA_ESCAPE = "\\1"
# Unit assumed by the BrainVision Core Data Format when the field is omitted.
_DEFAULT_UNIT = "µV"

_CHANNEL_KEY = re.compile(r"^Ch(\d+)$")
_COMMENT_HEADER = re.compile(r"^\s*\[\s*" + _COMMENT + r"\s*\]\s*$", re.IGNORECASE)

# Bytes per sample per channel for each documented BinaryFormat.
_BYTES_PER_SAMPLE: dict[str, int] = {
    "IEEE_FLOAT_32": 4,
    "IEEE_FLOAT_64": 8,
    "INT_16": 2,
    "UINT_16": 2,
    "INT_32": 4,
}


@dataclass(frozen=True)
class BvChannel:
    """One `Ch<n>=` entry. `index` is the 1-based number from the key."""

    index: int
    name: str
    reference: str
    resolution: float | None
    unit: str


@dataclass(frozen=True)
class BvHeader:
    """Everything a `.vhdr` states about the layout of its `.eeg`."""

    sampling_interval_us: float
    sfreq_hz: float
    n_channels: int
    binary_format: str
    data_orientation: str
    data_file: str
    marker_file: str
    channels: tuple[BvChannel, ...]

    @property
    def bytes_per_sample(self) -> int:
        """Bytes one channel's one sample occupies on disk, from `binary_format`.

        Multiply by `n_channels` and divide the `.eeg` size by the product to
        get the number of samples, when the `.eeg` is finally present.
        """
        try:
            return _BYTES_PER_SAMPLE[self.binary_format]
        except KeyError:
            raise ValueError(
                f"BinaryFormat {self.binary_format!r} is not a documented BrainVision format"
            ) from None

    @property
    def channel_names(self) -> tuple[str, ...]:
        return tuple(ch.name for ch in self.channels)


def read_header(path: Path | str, *, source: str = DEFAULT_SOURCE) -> BvHeader:
    """Parse the `.vhdr` at `path`. The `.eeg` and `.vmrk` need not exist.

    The bytes are decoded with `bytes.decode` as `utf-8-sig` first (which also
    drops a byte order mark if one is present), falling back to `latin-1` on
    a `UnicodeDecodeError`. Line endings may be LF or CRLF.

    `source` is the label every error message starts with. It defaults to the
    neutral `<vhdr>`, never the filename, so that `str(exc)` can go straight
    into the ledger. A caller that wants a diagnosable label passes its own
    study ID / session / block label, which is already redacted by design.
    """
    raw = Path(path).read_bytes()
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return parse_header(text, source=source)


def parse_header(text: str, source: str = DEFAULT_SOURCE) -> BvHeader:
    """Parse header text already in memory. `source` labels error messages."""
    lines = text.splitlines()
    if not lines or not lines[0].strip().startswith(MAGIC_PREFIX):
        raise ValueError(f"{source}: first line is not a BrainVision header magic line")

    cfg = _read_ini(_strip_comment_section(lines[1:]), source)

    common = _section(cfg, _COMMON, source)
    binary = _section(cfg, _BINARY, source)
    channel_section = _section(cfg, _CHANNELS, source)

    data_format = _str_key(common, "DataFormat", _COMMON, source).upper()
    if data_format != "BINARY":
        raise ValueError(
            f"{source}: DataFormat is {data_format!r}; only BINARY headers describe an .eeg"
        )

    interval = _float_key(common, "SamplingInterval", _COMMON, source)
    if not _is_positive_finite(interval):
        raise ValueError(
            f"{source}: SamplingInterval in [{_COMMON}] must be a finite positive number"
        )
    n_channels = _int_key(common, "NumberOfChannels", _COMMON, source)
    if n_channels <= 0:
        raise ValueError(f"{source}: NumberOfChannels in [{_COMMON}] must be positive")

    channels = _parse_channels(channel_section, source)
    if len(channels) != n_channels:
        raise ValueError(
            f"{source}: NumberOfChannels is {n_channels} but [{_CHANNELS}] "
            f"lists {len(channels)} Ch entries"
        )
    expected = tuple(range(1, n_channels + 1))
    if tuple(ch.index for ch in channels) != expected:
        raise ValueError(f"{source}: [{_CHANNELS}] keys are not Ch1..Ch{n_channels}")

    return BvHeader(
        sampling_interval_us=interval,
        sfreq_hz=1e6 / interval,
        n_channels=n_channels,
        binary_format=_str_key(binary, "BinaryFormat", _BINARY, source).upper(),
        data_orientation=_str_key(common, "DataOrientation", _COMMON, source).upper(),
        data_file=_str_key(common, "DataFile", _COMMON, source),
        # MarkerFile is optional in the format; a header without one is valid.
        marker_file=common.get("MarkerFile", "").strip(),
        channels=channels,
    )


# ---- pieces --------------------------------------------------------------------


def _strip_comment_section(lines: list[str]) -> str:
    """Everything before the `[Comment]` line, joined with LF.

    Each kept line is stripped of leading whitespace so that no line can be
    taken by configparser as the continuation of the one above; BrainVision
    never writes multi-line values. Splitting on `str.splitlines` first is
    what makes CRLF input harmless.
    """
    kept: list[str] = []
    for line in lines:
        if _COMMENT_HEADER.match(line):
            break
        kept.append(line.lstrip())
    return "\n".join(kept) + "\n"


def _read_ini(body: str, source: str) -> configparser.ConfigParser:
    """`configparser.ConfigParser` tuned to the BrainVision dialect.

    Only `=` separates key from value (a `:` may appear inside a value), `;`
    starts a comment, key case is preserved, and no `%` interpolation is
    attempted because a unit or a name may legitimately contain one. A line
    without `=` is refused (`allow_no_value=False`), so free text that strays
    into a key section is a `ValueError` naming the source, never a silent key.

    `AttributeError` is caught alongside `configparser.Error` because CPython's
    parser raises a bare one from `_read` when a valueless key is followed by
    an indented line; that path is closed by `allow_no_value=False` and the
    leading-whitespace strip, and the catch is there so it stays closed.
    """
    cfg = configparser.ConfigParser(
        delimiters=("=",),
        comment_prefixes=(";",),
        inline_comment_prefixes=None,
        interpolation=None,
        strict=True,
        allow_no_value=False,
    )
    cfg.optionxform = str  # type: ignore[assignment, method-assign]
    try:
        cfg.read_string(body, source=source)
    except (configparser.Error, AttributeError) as exc:
        raise ValueError(f"{source}: malformed header: {exc.__class__.__name__}") from exc
    return cfg


def _section(cfg: configparser.ConfigParser, name: str, source: str) -> configparser.SectionProxy:
    if not cfg.has_section(name):
        raise ValueError(f"{source}: missing section [{name}]")
    return cfg[name]


def _str_key(section: configparser.SectionProxy, key: str, name: str, source: str) -> str:
    value = section.get(key)
    if value is None or not value.strip():
        raise ValueError(f"{source}: missing key {key} in section [{name}]")
    return value.strip()


def _float_key(section: configparser.SectionProxy, key: str, name: str, source: str) -> float:
    value = _str_key(section, key, name, source)
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"{source}: key {key} in section [{name}] is not a number") from None


def _int_key(section: configparser.SectionProxy, key: str, name: str, source: str) -> int:
    """`int(value)` directly, so `nan`, `inf`, and `2.7` are all refused as non-integers."""
    value = _str_key(section, key, name, source)
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"{source}: key {key} in section [{name}] is not an integer") from None


def _is_positive_finite(x: float) -> bool:
    return math.isfinite(x) and x > 0


def _parse_channels(section: configparser.SectionProxy, source: str) -> tuple[BvChannel, ...]:
    found: list[BvChannel] = []
    for key, value in section.items():
        m = _CHANNEL_KEY.match(key)
        if m is None:
            continue
        found.append(_parse_channel(int(m.group(1)), value, source))
    found.sort(key=lambda ch: ch.index)
    return tuple(found)


def _parse_channel(index: int, value: str, source: str) -> BvChannel:
    fields = [f.replace(_COMMA_ESCAPE, ",").strip() for f in value.split(",")]
    # Pad to the four documented fields; later fields are "future extensions".
    fields += [""] * (4 - len(fields))
    name, reference, resolution_text, unit = fields[:4]
    if not name:
        raise ValueError(f"{source}: Ch{index} in [{_CHANNELS}] has no channel name")
    resolution: float | None
    if resolution_text:
        try:
            resolution = float(resolution_text)
        except ValueError:
            raise ValueError(
                f"{source}: Ch{index} in [{_CHANNELS}] has a non-numeric resolution"
            ) from None
        if not _is_positive_finite(resolution):
            raise ValueError(
                f"{source}: Ch{index} in [{_CHANNELS}] resolution must be finite and positive"
            )
    else:
        resolution = None
    return BvChannel(
        index=index,
        name=name,
        reference=reference,
        resolution=resolution,
        unit=unit or _DEFAULT_UNIT,
    )
