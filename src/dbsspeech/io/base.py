"""Format-agnostic recording interface and reader registry.

Everything downstream of this module works with `Recording`, `StreamInfo`, and
`EpochSeries`. Nothing downstream knows what an acquisition system is. Adding a
format means writing a reader and registering it; no other layer changes.

Two conventions fixed here, because getting either wrong is silent and expensive:

Orientation
    `Recording.read` always returns ``(n_channels, n_samples)``. Acquisition
    formats disagree about this (MATLAB v7.3 stores the transpose of what MATLAB
    displays, for instance), so each reader normalizes and the rest of the
    codebase never transposes again.

Identifiers
    Raw files carry subject names, surgery dates, and operator names in their
    metadata. Those stop here. `Recording.metadata` returns only structural
    fields. Identifier-bearing fields are reachable only through
    `read_restricted_metadata`, which exists so a de-identification step can
    inspect what needs stripping, and which must never feed a derivative, a log,
    a filename, or a figure.
"""

from __future__ import annotations

import abc
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np


@dataclass(frozen=True)
class PrivacyPolicy:
    """What a site considers safe to surface from a recording.

    Defaults are conservative, so a site that has declared nothing gets the
    careful behavior. Load the configured policy with `from_mapping`.
    """

    filenames_deidentified: bool = False
    restricted_metadata_fields: frozenset[str] = frozenset()

    @classmethod
    def from_mapping(cls, config: dict[str, Any], format: str) -> PrivacyPolicy:
        """Build the policy for one format from a parsed `configs/privacy.yaml`."""
        per_format = (config.get("restricted_metadata_fields") or {}).get(format) or []
        return cls(
            filenames_deidentified=filenames_deidentified_for(config, format),
            restricted_metadata_fields=frozenset(per_format),
        )


def filenames_deidentified_for(config: dict[str, Any], format: str) -> bool:
    """Whether a site declares filenames safe to surface, for one format.

    Whether a filename carries an identifier is a property of how one
    acquisition system names its exports, not of the site as a whole, so this
    accepts either form:

        filenames_deidentified: true            one answer for every format
        filenames_deidentified:                 per format
          tdt_mat: true
          brainvision: false

    A format absent from the mapping is False, so registering a reader never
    silently opts its filenames in.

    This is a module function rather than only a `from_mapping` step because
    guardrail G13 reads the same setting when deciding whether a raw path may
    reach a derivative, and G13 is not overridable. Two spellings of "is this
    site's naming safe" would eventually disagree, and the failure would be a
    safety check quietly passing: `bool()` of a non-empty per-format mapping is
    True for every format at once.
    """
    value = config.get("filenames_deidentified", False)
    if isinstance(value, dict):
        return bool(value.get(format, False))
    return bool(value)


DEFAULT_PRIVACY_POLICY = PrivacyPolicy()


@dataclass(frozen=True)
class StreamInfo:
    """Structural description of one continuous stream."""

    name: str
    n_channels: int
    sfreq_hz: float
    n_samples: int
    dtype: str
    start_time_s: float = 0.0
    channel_ids: tuple[str, ...] = ()

    @property
    def duration_s(self) -> float:
        return self.n_samples / self.sfreq_hz if self.sfreq_hz else 0.0

    @property
    def usable_bandwidth_hz(self) -> float:
        """Nyquist for this stream. Guardrail G6 compares bands against this."""
        return self.sfreq_hz / 2.0


@dataclass(frozen=True)
class EpochSeries:
    """Discrete event times sharing the recording clock.

    `onsets` and `offsets` are seconds. `values` carries whatever the format
    attaches to each event (a frame index, a marker code); it may be empty.
    """

    name: str
    onsets: np.ndarray
    offsets: np.ndarray = field(default_factory=lambda: np.empty(0))
    values: np.ndarray = field(default_factory=lambda: np.empty(0))

    def __len__(self) -> int:
        return int(self.onsets.size)


class Recording(abc.ABC):
    """One recording session, opened lazily.

    Implementations must not read sample data on open. A multi-gigabyte file is
    the normal case, so opening reports structure and nothing more.
    """

    path: Path

    @property
    @abc.abstractmethod
    def format(self) -> str:
        """Registry key of the reader that produced this object."""

    @property
    @abc.abstractmethod
    def streams(self) -> dict[str, StreamInfo]:
        """Structural description of every continuous stream, by name."""

    @property
    @abc.abstractmethod
    def epochs(self) -> dict[str, EpochSeries]:
        """Discrete event series, by name. Empty when the format has none."""

    @property
    @abc.abstractmethod
    def metadata(self) -> dict[str, Any]:
        """Structural metadata.

        Never contains a field the active `PrivacyPolicy` restricts. The
        filename is included only when the policy declares filenames
        de-identified; regardless, prefer the manifest key when referring to a
        recording, because a path is machine-specific and a manifest key is not.
        """

    @abc.abstractmethod
    def read(
        self,
        stream: str,
        channels: Sequence[int] | None = None,
        tmin: float | None = None,
        tmax: float | None = None,
    ) -> np.ndarray:
        """Read a window as ``(n_channels, n_samples)``.

        `channels` are zero-based indices into the stream, in the order given.
        `tmin` and `tmax` are seconds relative to the stream start; None means
        the corresponding end of the recording. The window is half-open,
        ``[tmin, tmax)``, so adjacent windows do not share a sample.
        """

    @abc.abstractmethod
    def read_restricted_metadata(self) -> dict[str, Any]:
        """Metadata fields that may carry identifiers.

        Separate from `metadata` so that reaching them is always a deliberate,
        greppable act. For de-identification only. Never write the result into a
        derivative, a run record, a log, a filename, or a figure.
        """

    def time_to_sample(self, stream: str, t: float) -> int:
        """Convert seconds to a sample index within a stream, clamped in range."""
        info = self.streams[stream]
        idx = int(round(t * info.sfreq_hz))
        return max(0, min(idx, info.n_samples))

    def __enter__(self) -> Recording:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        """Release file handles. Safe to call more than once.

        Intentionally a concrete no-op rather than abstract: not every format
        holds an open handle, and readers that do override this.
        """
        return None


# --------------------------------------------------------------------------
# Reader registry
# --------------------------------------------------------------------------

ReaderFactory = Callable[..., Recording]
Sniffer = Callable[[Path], bool]

_READERS: dict[str, ReaderFactory] = {}
_SNIFFERS: dict[str, Sniffer] = {}
_ENTRY_SUFFIXES: dict[str, tuple[str, ...]] = {}


def register_reader(
    name: str,
    factory: ReaderFactory,
    sniffer: Sniffer | None = None,
    entry_suffixes: Sequence[str] = (),
) -> None:
    """Register a reader under a format key.

    The key is what `manifest/subjects.csv:format` holds. `sniffer` is optional
    and is only consulted when no format was declared.

    `entry_suffixes` names the file that opens the format, lowercase and with
    the dot, so a caller holding a directory can find the one recording in it.
    It is declared here rather than in a table elsewhere because a table
    elsewhere is a table that gets forgotten: `edf` was added as a reader and
    the separate map in `loader.py` was not updated, which made every EDF
    directory unopenable while every test still passed.
    """
    if name in _READERS:
        raise ValueError(f"reader already registered for format {name!r}")
    _READERS[name] = factory
    if sniffer is not None:
        _SNIFFERS[name] = sniffer
    _ENTRY_SUFFIXES[name] = tuple(s.lower() for s in entry_suffixes)


def entry_suffixes(format: str) -> tuple[str, ...]:
    """Suffixes that open `format`, empty when the reader declared none."""
    return _ENTRY_SUFFIXES.get(format, ())


def all_entry_suffixes() -> dict[str, tuple[str, ...]]:
    """Every registered format's entry suffixes, for callers scanning a tree."""
    return dict(_ENTRY_SUFFIXES)


def available_formats() -> tuple[str, ...]:
    return tuple(sorted(_READERS))


def open_recording(
    path: str | Path,
    format: str | None = None,
    policy: PrivacyPolicy | None = None,
) -> Recording:
    """Open a recording, dispatching on `format` or by sniffing the file.

    Declaring the format in the manifest is the supported path. Sniffing exists
    for the inspection step, before a manifest row exists. When sniffing is
    ambiguous it raises rather than picking, because a wrong reader produces
    plausible nonsense rather than an error.

    `policy` defaults to the conservative `PrivacyPolicy`, so an omitted policy
    withholds more rather than less.
    """
    policy = policy or DEFAULT_PRIVACY_POLICY
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)

    if format is not None:
        try:
            factory = _READERS[format]
        except KeyError:
            raise ValueError(
                f"unknown format {format!r}; registered: {available_formats()}"
            ) from None
        return factory(p, policy)

    matches = [name for name, sniff in _SNIFFERS.items() if _safe_sniff(sniff, p)]
    if not matches:
        raise ValueError(
            f"could not identify the format of {p.name}. "
            f"Declare it in the manifest; registered formats: {available_formats()}"
        )
    if len(matches) > 1:
        raise ValueError(
            f"{p.name} matched more than one format ({matches}). "
            "Declare the format in the manifest rather than relying on sniffing."
        )
    return _READERS[matches[0]](p, policy)


def _safe_sniff(sniff: Sniffer, p: Path) -> bool:
    """A sniffer that raises is a sniffer that says no."""
    try:
        return bool(sniff(p))
    except Exception:
        return False
