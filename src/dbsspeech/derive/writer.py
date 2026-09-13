"""Streaming, crash-safe HDF5 block writer that any h5py or MATLAB reader can open.

One file per block, one dataset per stream product, every number the file
needs to be understood written next to it as an attribute. The file is built
under a `.part` name and renamed into place with `os.replace` only when the
whole block succeeded, so a reader that finds a `.h5` can trust it and a crash
mid-build leaves nothing behind but a `.part` that the next run truncates.

Datasets are created with `h5py.Group.create_dataset` (resizable along time,
chunked at the full channel width, gzip plus the shuffle filter as the policy
says) and grown with `h5py.Dataset.resize`, so a multi-gigabyte stream is
never held in memory. Strings are written with `h5py.string_dtype` in fixed
UTF-8 so MATLAB's `h5readatt` returns them as text; booleans are written as
int8 because MATLAB reads an HDF5 enum as a cell of names, not as a logical.

Privacy is enforced here one final time, on every name, key and string value
that would land in the file. The configured redact patterns are applied through
`dbsspeech.derive.redact.Scrubber`, which also carries the hard-coded tank-stem
and Box floors, and this module adds a floor of its own for compact dates,
URIs and filesystem paths. The upstream pipeline is expected to have redacted
already; this module refuses rather than trusts. It never writes an absolute
start time: `t0_s` is always 0.0, because on this archive the raw start time
is a surgery timestamp.

Content hashes are streamed through `hashlib.sha256` during `append`; nothing
is re-read. See `HASH_ORDER_NOTE` and `recompute_hashes` for the byte order.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from importlib import metadata
from pathlib import Path, PurePath, PurePosixPath, PureWindowsPath
from types import TracebackType
from typing import Any

import h5py
import numpy as np

from dbsspeech.derive.config import DeriveConfig
from dbsspeech.derive.model import BlockJob, ProductRecord
from dbsspeech.derive.redact import Scrubber

DEFAULT_UNITS = "unknown (TDT Scale: Unity)"
REFERENCE_NOTE = "shared, as recorded; no re-referencing applied"
LAYOUT_NOTE = "h5py/C: (n_channels, n_samples); MATLAB h5read: (n_samples, n_channels)"
# The whole-stream hash is time-major: sample 0 of every channel, then sample 1,
# and so on. That is the order the samples arrive in during a streaming build,
# `data.tobytes(order="F")` for the (n_channels, n_samples) array h5py returns,
# and the native memory order of the (n_samples, n_channels) array MATLAB's
# h5read returns. A single streaming sha256 cannot reproduce C order across
# channel rows, so `channel_sha256` carries the C-order hash of each row.
HASH_ORDER_NOTE = (
    "time-major: sha256 of data.tobytes(order='F') for the h5py (n_channels, n_samples) "
    "array; equal to the C-order bytes of a single-channel stream. channel_sha256[i] is "
    "sha256 of data[i, :].tobytes() (C order)."
)
BOOL_NOTE = "booleans are stored as int8 (0/1) so MATLAB reads a number, not an enum"

# Root attributes this module owns. A provenance key with one of these names
# cannot override the value the writer computes.
RESERVED_ROOT_ATTRS: frozenset[str] = frozenset(
    {
        "schema_version",
        "study_id",
        "session",
        "block",
        "session_sanitized",
        "block_sanitized",
        "source_format",
        "config_sha256",
        "builder_version",
        "t0_s",
        "time_origin",
        "layout",
        "bool_encoding",
    }
)
# Dataset attributes this module owns; caller attrs cannot override them.
RESERVED_PRODUCT_ATTRS: frozenset[str] = frozenset(
    {
        "role",
        "sfreq_out_hz",
        "t0_s",
        "n_channels",
        "channel_ids",
        "layout",
        "dtype",
        "reference",
        "n_samples",
        "n_nonfinite",
        "data_sha256",
        "data_sha256_order",
        "channel_sha256",
        "name",
    }
)

_SAFE_NAME = re.compile(r"[^A-Za-z0-9_.\-]")
_WHITESPACE = re.compile(r"\s+")

# Box markers, case-insensitive: `box:` or `box/` as its own token, or a path
# segment containing `box` (the FUSE mount point, or any folder named for it).
_BOX_TOKEN = re.compile(r"(?<![A-Za-z0-9])box(?=[:/\\])", re.IGNORECASE)
_BOX_SEGMENT = re.compile(r"[/\\][^/\\\s]*box[^/\\\s]*(?=[/\\]|$)", re.IGNORECASE)

# A token that is an absolute path with at least two components, anywhere in
# the string. `~/` counts: it names a directory on a specific machine. Any
# `<scheme>://` URI counts too (file://, smb://, sftp://).
_EMBEDDED_PATH = re.compile(
    r"(?:^|[\s\"'=(\[,;])(?:~?/[^\s/\"']+/[^\s\"']*|[A-Za-z]:[\\/][^\s\"']+|\\\\[^\s\"']+)"
)
_URI = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9+.\-]*://")

# A month word on its own: "dec" must not match the start of "decimate".
_MONTH = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?"
    r"|sep(?:t|tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])"
)

# The floor this module applies on top of the configured patterns and the
# scrubber's own floors. Each is anchored on non-alphanumerics so a hex digest
# (letters bound every digit run) cannot trip it.
_FLOOR_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    # Compact YYYYMMDD with a valid month and day.
    (
        "compact date",
        re.compile(
            r"(?<![A-Za-z0-9])(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
            r"(?![A-Za-z0-9])"
        ),
    ),
    # BrainVision export naming: `date_YYYYMMDD` and `time_HHMM`.
    ("date_ field", re.compile(r"(?i)date_\d{6,8}(?![A-Za-z0-9])")),
    # A bare TDT timestamp, two six-digit groups, with the subject dropped.
    ("six-six timestamp", re.compile(r"(?<![A-Za-z0-9])\d{6}[-_ ]\d{6}(?![A-Za-z0-9])")),
    # ISO and slash dates, so a config with no redact_patterns still refuses them.
    ("ISO date", re.compile(r"(?<![0-9])\d{4}-\d{2}-\d{2}(?![0-9])")),
    ("slash date", re.compile(r"(?<![0-9])\d{1,2}/\d{1,2}/\d{4}(?![0-9])")),
    # Dotted numeric dates: 12.05.1999 or 1999.12.05.
    (
        "dotted date",
        re.compile(r"(?<![A-Za-z0-9.])(?:\d{1,2}\.\d{1,2}\.\d{4}|\d{4}\.\d{1,2}\.\d{1,2})(?![0-9.])"),
    ),
    # Month-name dates: May 12, 1999; 12 May 1999; Sept. 3 1999.
    (
        "month-name date",
        re.compile(
            r"(?i)(?<![A-Za-z])" + _MONTH + r"\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}(?![0-9])"
            r"|(?<![0-9])\d{1,2}(?:st|nd|rd|th)?\s+" + _MONTH + r"\.?,?\s+\d{4}(?![0-9])"
        ),
    ),
)

# A numeric attribute under a key like these is a timestamp until proven
# otherwise. A Unix epoch is ~1.7e9 and a compact date is ~2e7; a duration or
# a sample count in a block never reaches 1e6 seconds.
_TIMESTAMP_KEY = re.compile(r"date|time|stamp|epoch_s|meas_", re.IGNORECASE)
_TIMESTAMP_KEY_ALLOWED: frozenset[str] = frozenset({"t0_s", "time_origin"})
_TIMESTAMP_MAGNITUDE = 1e6

_REFUSED_TYPES: tuple[type, ...] = (PurePath, _dt.date, _dt.datetime, _dt.time, np.datetime64)


class PrivacyRefusal(ValueError):
    """A name, key or value that must not reach a derivative was offered to the writer."""


def _builder_version() -> str:
    try:
        return metadata.version("analyzedbs")
    except metadata.PackageNotFoundError:
        return "unknown"


def sanitize_name(name: str) -> str:
    """Restrict a session or block name to letters, digits, `_`, `-` and `.`.

    Runs of whitespace become a single underscore; any other character becomes
    an underscore. The original name is stored as an attribute by the caller,
    so nothing is lost, only made safe as a path component.
    """
    out = _SAFE_NAME.sub("_", _WHITESPACE.sub("_", name.strip()))
    if not out or out in {".", ".."} or out.startswith("."):
        raise ValueError(f"name {name!r} does not sanitize to a usable filename")
    return out


def hdf_name(name: str) -> str:
    """A group or dataset name for an HDF5 path from a stream, product or epoch name.

    Trailing slashes are dropped (TDT epoc stores are named like `PeA/`), then
    the rest goes through `sanitize_name`, so a `/` in the middle cannot create
    a nested group. The original name is kept as a `name` attribute.
    """
    return sanitize_name(name.rstrip("/\\"))


def _looks_like_absolute_path(text: str) -> bool:
    stripped = text.strip()
    if PurePosixPath(stripped).is_absolute() or PureWindowsPath(stripped).is_absolute():
        return True
    if stripped.startswith("~/") or stripped.startswith("~\\"):
        return True
    return _EMBEDDED_PATH.search(text) is not None or _URI.search(text) is not None


class PrivacyChecker:
    """Refuses any string that matches the policy, names a path, or looks like a date.

    The configured `cfg.privacy.redact_patterns` run through
    `dbsspeech.derive.redact.Scrubber`, whose `violations` also applies the
    hard-coded Box and tank-stem floors, so an upper-case or underscore-joined
    tank stem is refused whatever the config says. On top of that this class
    refuses case-insensitive Box markers, absolute paths and URIs, compact and
    month-name dates, and numeric timestamps under a date-like key.
    """

    def __init__(self, patterns: Iterable[str]) -> None:
        self._scrubber = Scrubber(list(patterns))

    def check(self, text: str, where: str) -> None:
        """Raise `PrivacyRefusal` naming the rule, never quoting the text."""
        if _BOX_TOKEN.search(text) or _BOX_SEGMENT.search(text):
            raise PrivacyRefusal(f"{where}: refuses a Box reference")
        if _looks_like_absolute_path(text):
            raise PrivacyRefusal(f"{where}: refuses a filesystem path or URI")
        fired = self._scrubber.violations(text)
        if fired:
            raise PrivacyRefusal(f"{where}: refuses a value; redaction rule(s) {', '.join(fired)}")
        for label, pattern in _FLOOR_PATTERNS:
            if pattern.search(text):
                raise PrivacyRefusal(f"{where}: refuses a value that looks like a {label}")

    def check_attrs(self, attrs: Mapping[str, Any], where: str) -> None:
        for key, value in attrs.items():
            self.check(str(key), f"{where} attribute key")
            self.check_value(value, f"{where} attribute {key!r}", key=str(key))

    def check_value(self, value: Any, where: str, key: str | None = None) -> None:
        """Check one value, descending into arrays, sequences and mappings."""
        if isinstance(value, _REFUSED_TYPES):
            raise PrivacyRefusal(
                f"{where}: refuses a {type(value).__name__}; paths and datetimes never travel"
            )
        if isinstance(value, bytes):
            self.check(value.decode("utf-8", errors="replace"), where)
        elif isinstance(value, str):
            self.check(value, where)
        elif isinstance(value, np.ndarray):
            if value.dtype.kind in ("U", "S", "O"):
                for item in value.ravel():
                    self.check_value(item, where)
            elif value.dtype.kind == "M":
                raise PrivacyRefusal(f"{where}: refuses a datetime array")
            elif key is not None and value.dtype.kind in ("i", "u", "f"):
                self._check_number(value, where, key)
        elif isinstance(value, (list, tuple)):
            for item in value:
                self.check_value(item, where, key)
        elif isinstance(value, Mapping):
            self.check_attrs(value, where)
        elif key is not None and isinstance(value, (int, float, np.integer, np.floating)):
            self._check_number(value, where, key)

    @staticmethod
    def _check_number(value: Any, where: str, key: str) -> None:
        """Refuse a large number under a date-like key; `numpy.abs` and `numpy.max`."""
        if isinstance(value, (bool, np.bool_)) or key in _TIMESTAMP_KEY_ALLOWED:
            return
        if not _TIMESTAMP_KEY.search(key):
            return
        arr = np.asarray(value, dtype=np.float64)
        if arr.size == 0:
            return
        with np.errstate(invalid="ignore"):
            magnitude = float(np.nanmax(np.abs(arr)))
        if magnitude >= _TIMESTAMP_MAGNITUDE:
            raise PrivacyRefusal(
                f"{where}: refuses a number of magnitude >= {_TIMESTAMP_MAGNITUDE:g} "
                "under a date-like key; it looks like a timestamp"
            )


def _string_attr(value: str) -> np.ndarray:
    """A scalar fixed-length UTF-8 attribute via `h5py.string_dtype`."""
    raw = value.encode("utf-8")
    return np.array(raw, dtype=h5py.string_dtype("utf-8", max(len(raw), 1)))


def _string_array(values: Iterable[str]) -> np.ndarray:
    """A variable-length UTF-8 string array via `h5py.string_dtype`."""
    return np.array(list(values), dtype=h5py.string_dtype("utf-8"))


def _encode_attr(value: Any) -> Any:
    """What actually goes into `h5py.AttributeManager` for one value.

    Fails closed: anything that is not a bool, number, string, bytes, None, a
    numeric or string numpy array, or a homogeneous list of strings or numbers
    raises `TypeError` here, before a file exists, rather than deep inside h5py.
    """
    if isinstance(value, _REFUSED_TYPES):
        raise PrivacyRefusal(f"a {type(value).__name__} may not be written as an attribute")
    if isinstance(value, (bool, np.bool_)):
        return np.int8(1 if value else 0)
    if isinstance(value, str):
        return _string_attr(value)
    if isinstance(value, bytes):
        return _string_attr(value.decode("utf-8"))
    if value is None:
        return _string_attr("")
    if isinstance(value, (int, float, np.integer, np.floating)):
        return value
    if isinstance(value, np.ndarray):
        if value.dtype.kind in ("U", "S", "O"):
            return _string_array(str(v) for v in value.ravel())
        if value.dtype.kind == "b":
            return value.astype(np.int8)
        if value.dtype.kind in ("i", "u", "f"):
            return value
        raise TypeError(f"attribute array of dtype {value.dtype} is not supported")
    if isinstance(value, (list, tuple)):
        if not value:
            return np.empty(0, dtype=np.float64)
        if all(isinstance(v, str) for v in value):
            return _string_array(value)
        if all(isinstance(v, (bool, np.bool_)) for v in value):
            return np.array([1 if v else 0 for v in value], dtype=np.int8)
        if all(
            isinstance(v, (int, float, np.integer, np.floating))
            and not isinstance(v, (bool, np.bool_))
            for v in value
        ):
            return np.asarray(value)
        raise TypeError("attribute lists must be all strings or all numbers")
    raise TypeError(f"attribute of type {type(value).__name__} is not supported")


def _encode_attrs(attrs: Mapping[str, Any]) -> dict[str, Any]:
    return {str(k): _encode_attr(v) for k, v in attrs.items()}


def _write_encoded(target: h5py.HLObject, encoded: Mapping[str, Any]) -> None:
    for key, value in encoded.items():
        target.attrs[key] = value


def _jsonable(value: Any) -> Any:
    """Coerce numpy scalars and arrays so `json.dumps(asdict(record))` works.

    `numpy.generic.item` and `numpy.ndarray.tolist` do the conversion.
    """
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def recompute_hashes(dataset: h5py.Dataset, window: int = 1 << 16) -> tuple[str, list[str]]:
    """Recompute `(data_sha256, channel_sha256)` from a stored product dataset.

    Streams the dataset in time windows of `window` samples so a large product
    is never held in memory. The whole-stream hash is time-major, per
    `HASH_ORDER_NOTE`; the per-channel hashes are the C-order bytes of each
    channel row. Hashes use `hashlib.sha256`.
    """
    n_channels, n_samples = dataset.shape
    whole = hashlib.sha256()
    rows = [hashlib.sha256() for _ in range(n_channels)]
    for start in range(0, n_samples, max(1, window)):
        block = np.ascontiguousarray(dataset[:, start : start + window])
        whole.update(block.tobytes(order="F"))
        for i in range(n_channels):
            rows[i].update(block[i].tobytes())
    return whole.hexdigest(), [r.hexdigest() for r in rows]


@dataclass
class ProductHandle:
    """An open, growing waveform dataset; `append` chunks, then `close`."""

    stream: str
    product: str
    role: str
    n_channels: int
    sfreq_out_hz: float
    sfreq_in_hz: float
    n_samples_in: int | None
    filter_attrs: dict[str, Any]
    _dataset: h5py.Dataset
    _dtype: np.dtype[Any]
    _hasher: Any
    _row_hashers: list[Any] = field(default_factory=list)
    _n_samples: int = 0
    _n_nonfinite: int = 0
    _closed: bool = False

    @property
    def n_samples(self) -> int:
        return self._n_samples

    @property
    def n_nonfinite(self) -> int:
        """Samples that became NaN or inf in the cast to the store dtype, or arrived so."""
        return self._n_nonfinite

    @property
    def closed(self) -> bool:
        return self._closed

    def append(self, chunk: np.ndarray) -> None:
        """Append ``(n_channels, n_new)`` samples, converting to the store dtype.

        Grows the dataset with `h5py.Dataset.resize` and feeds the converted
        bytes to `hashlib.sha256`: the whole-stream hasher in time-major order
        and one hasher per channel row in C order, so nothing is re-read.
        Non-finite samples after the cast are counted (`numpy.isfinite`), not
        altered; the count lands in the `n_nonfinite` attribute.
        """
        if self._closed:
            raise RuntimeError(f"{self.stream}/{self.product} is already closed")
        arr = np.asarray(chunk)
        if arr.ndim != 2 or arr.shape[0] != self.n_channels:
            raise ValueError(
                f"{self.stream}/{self.product}: expected ({self.n_channels}, n_new), "
                f"got shape {arr.shape}"
            )
        n_new = int(arr.shape[1])
        if n_new == 0:
            return
        with np.errstate(over="ignore", invalid="ignore"):
            stored = np.ascontiguousarray(arr, dtype=self._dtype)
        self._n_nonfinite += int(np.count_nonzero(~np.isfinite(stored)))
        start = self._n_samples
        self._dataset.resize((self.n_channels, start + n_new))
        self._dataset[:, start : start + n_new] = stored
        self._hasher.update(stored.tobytes(order="F"))
        for i, hasher in enumerate(self._row_hashers):
            hasher.update(stored[i].tobytes())
        self._n_samples = start + n_new

    def close(self) -> ProductRecord:
        """Finalize attributes and return the record the ledger stores."""
        if self._closed:
            raise RuntimeError(f"{self.stream}/{self.product} is already closed")
        digest = self._hasher.hexdigest()
        row_digests = [h.hexdigest() for h in self._row_hashers]
        self._dataset.attrs["n_samples"] = np.int64(self._n_samples)
        self._dataset.attrs["n_nonfinite"] = np.int64(self._n_nonfinite)
        self._dataset.attrs["data_sha256"] = _string_attr(digest)
        self._dataset.attrs["data_sha256_order"] = _string_attr(HASH_ORDER_NOTE)
        self._dataset.attrs["channel_sha256"] = _string_array(row_digests)
        self._closed = True
        return ProductRecord(
            stream=self.stream,
            product=self.product,
            role=self.role,
            n_channels=self.n_channels,
            n_samples_in=self.n_samples_in if self.n_samples_in is not None else self._n_samples,
            n_samples_out=self._n_samples,
            sfreq_in_hz=self.sfreq_in_hz,
            sfreq_out_hz=self.sfreq_out_hz,
            data_sha256=digest,
            filter_attrs=_jsonable(self.filter_attrs),
        )


class BlockWriter:
    """Write one block to ``<out_root>/<study_id>/<session>__<block>.h5``.

    Use as a context manager. The file is ``.h5.part`` while open. On a clean
    exit it is flushed, fsynced and renamed with `os.replace`, which is atomic
    on POSIX; on an exception, including one raised while entering, the
    ``.part`` is removed and the exception is re-raised. Session and block
    names are sanitized for the filename and the originals are recorded as
    root attributes.

    A live ``.part`` belonging to another process is never unlinked: HDF5's
    own file lock refuses the second opener, and the inode of the ``.part``
    is checked again before the rename so a file this writer did not create
    is never renamed into place. A finished ``.h5`` whose original session and
    block names differ from this job's is a sanitization collision and is
    refused rather than overwritten.
    """

    def __init__(
        self,
        out_root: Path,
        job: BlockJob,
        cfg: DeriveConfig,
        provenance: dict[str, Any],
    ) -> None:
        self.job = job
        self.cfg = cfg
        self.privacy = PrivacyChecker(cfg.privacy.redact_patterns)
        self.provenance = dict(provenance)
        self.records: list[ProductRecord] = []
        self.epochs_written: list[str] = []

        for label, value in (
            ("study_id", job.study_id),
            ("session", job.session),
            ("block", job.block),
            ("source_format", job.source_format),
        ):
            self.privacy.check(value, label)
        self.privacy.check_attrs(self.provenance, "provenance")
        # Encoding here fails closed before any file exists.
        self._provenance_encoded = _encode_attrs(self.provenance)

        study_dir = Path(out_root).expanduser() / sanitize_name(job.study_id)
        stem = f"{sanitize_name(job.session)}__{sanitize_name(job.block)}"
        self.path: Path = study_dir / f"{stem}.h5"
        self.part_path: Path = study_dir / f"{stem}.h5.part"
        self._dtype = np.dtype(cfg.store.dtype)
        self._file: h5py.File | None = None
        self._part_identity: tuple[int, int] | None = None
        self._handles: list[ProductHandle] = []

    # ---- lifecycle -------------------------------------------------------

    def _root_attrs(self) -> dict[str, Any]:
        fixed: dict[str, Any] = {
            "schema_version": np.int64(self.cfg.schema_version),
            "study_id": self.job.study_id,
            "session": self.job.session,
            "block": self.job.block,
            "session_sanitized": sanitize_name(self.job.session),
            "block_sanitized": sanitize_name(self.job.block),
            "source_format": self.job.source_format,
            "config_sha256": self.cfg.sha256(),
            "builder_version": _builder_version(),
            "t0_s": np.float64(0.0),
            "time_origin": "block start; all times in this file are seconds from t0_s",
            "layout": LAYOUT_NOTE,
            "bool_encoding": BOOL_NOTE,
        }
        # Provenance first, the writer's own keys last, so nothing in the
        # provenance dict can forge a study ID or smuggle in a start time.
        merged = dict(self._provenance_encoded)
        merged.update(_encode_attrs(fixed))
        return merged

    def __enter__(self) -> BlockWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # No pre-unlink: mode "w" truncates a stale .part from a crashed run,
        # and HDF5 file locking refuses one another process holds open.
        self._file = h5py.File(self.part_path, "w", libver="earliest")
        try:
            st = os.stat(self.part_path)
            self._part_identity = (st.st_dev, st.st_ino)
            _write_encoded(self._file, self._root_attrs())
            self._file.require_group("streams")
            self._file.require_group("epochs")
            self._file.require_group("summary")
        except BaseException:
            self._abort()
            raise
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc_type is not None:
            self._abort()
            return
        try:
            for handle in self._handles:
                if not handle.closed:
                    self.records.append(handle.close())
            self._commit()
        except BaseException:
            self._abort()
            raise

    def _part_is_mine(self) -> bool:
        try:
            st = os.stat(self.part_path)
        except FileNotFoundError:
            return False
        return (st.st_dev, st.st_ino) == self._part_identity

    def _final_is_same_block(self) -> bool:
        """True unless an existing final file records different original names.

        An unreadable existing file is treated as overwritable garbage.
        """
        if not self.path.exists():
            return True
        try:
            with h5py.File(self.path, "r") as existing:
                session = existing.attrs.get("session")
                block = existing.attrs.get("block")
        except OSError:
            return True

        def text(v: Any) -> str | None:
            if v is None:
                return None
            return v.decode("utf-8") if isinstance(v, bytes) else str(v)

        return (text(session), text(block)) in (
            (None, None),
            (self.job.session, self.job.block),
        )

    def _commit(self) -> None:
        assert self._file is not None
        self._file.flush()
        self._file.close()
        self._file = None
        if not self._part_is_mine():
            raise RuntimeError(
                f"{self.part_path.name}: the .part on disk is not the one this writer created; "
                "another process is building the same block"
            )
        if not self._final_is_same_block():
            raise RuntimeError(
                f"{self.path.name}: a finished file for a different session/block sanitizes "
                "to the same filename; refusing to overwrite it"
            )
        fd = os.open(self.part_path, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        os.replace(self.part_path, self.path)
        dir_fd = os.open(self.path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)

    def _abort(self) -> None:
        if self._file is not None:
            try:
                self._file.close()
            finally:
                self._file = None
        # Only remove a .part this writer created; never another process's.
        if self._part_identity is not None and self._part_is_mine():
            self.part_path.unlink()

    def _require_open(self) -> h5py.File:
        if self._file is None:
            raise RuntimeError("BlockWriter is not open; use it as a context manager")
        return self._file

    # ---- products ----------------------------------------------------------

    def chunk_len(self, n_channels: int) -> int:
        """Samples per storage chunk so one chunk is about `chunk_target_bytes`."""
        per_sample = max(1, n_channels) * self._dtype.itemsize
        return max(1, self.cfg.store.chunk_target_bytes // per_sample)

    def _compression_kwargs(self) -> dict[str, Any]:
        comp = self.cfg.store.compression
        if comp.name == "none":
            return {}
        kwargs: dict[str, Any] = {"compression": comp.name, "shuffle": comp.shuffle}
        if comp.name == "gzip":
            kwargs["compression_opts"] = comp.level
        return kwargs

    def open_product(
        self,
        stream: str,
        product: str,
        role: str,
        n_channels: int,
        sfreq_out_hz: float,
        attrs: dict[str, Any],
        *,
        sfreq_in_hz: float | None = None,
        n_samples_in: int | None = None,
        filter_attrs: dict[str, Any] | None = None,
    ) -> ProductHandle:
        """Create ``/streams/<stream>/<product>`` and return a handle to grow it.

        The dataset is created with `h5py.Group.create_dataset` using
        ``maxshape=(n_channels, None)``, chunks of the full channel width and
        about `cfg.store.chunk_target_bytes`, the store dtype, and the
        policy's compression. `attrs` (typically `FilterReport.as_attrs()`
        plus `channel_ids` and optionally `units`) is written as given after
        the privacy check. The writer's own keys (`t0_s`, `reference`, `role`,
        `n_samples`, the hashes) cannot be overridden: `t0_s` is 0.0 whatever
        the caller passed.

        `sfreq_in_hz` and `n_samples_in` feed the `ProductRecord`; when
        omitted they fall back to ``attrs["sfreq_in_hz"]`` and to the output
        count. `filter_attrs` is what the record carries as
        `ProductRecord.filter_attrs`; when omitted it is `attrs` minus
        `channel_ids` and `units`, coerced to JSON-native types.
        """
        f = self._require_open()
        if n_channels < 1:
            raise ValueError("n_channels must be at least 1")
        if sfreq_out_hz <= 0:
            raise ValueError("sfreq_out_hz must be positive")
        for name, where in ((stream, "stream name"), (product, "product name"), (role, "role")):
            self.privacy.check(name, where)
        self.privacy.check_attrs(attrs, f"{stream}/{product}")
        if filter_attrs is not None:
            self.privacy.check_attrs(filter_attrs, f"{stream}/{product} filter_attrs")

        channel_ids = attrs.get("channel_ids")
        if channel_ids is None:
            channel_ids = [f"ch{i:03d}" for i in range(n_channels)]
        channel_ids = [str(c) for c in channel_ids]
        if len(channel_ids) != n_channels:
            raise ValueError(
                f"{stream}/{product}: {len(channel_ids)} channel_ids for {n_channels} channels"
            )

        merged: dict[str, Any] = {"units": DEFAULT_UNITS}
        merged.update({k: v for k, v in attrs.items() if k not in RESERVED_PRODUCT_ATTRS})
        merged.update(
            {
                "name": product,
                "role": role,
                "sfreq_out_hz": np.float64(sfreq_out_hz),
                "t0_s": np.float64(0.0),
                "reference": REFERENCE_NOTE,
                "n_channels": np.int64(n_channels),
                "channel_ids": _string_array(channel_ids),
                "layout": LAYOUT_NOTE,
                "dtype": self._dtype.name,
            }
        )
        encoded = _encode_attrs(merged)

        group = f["streams"].require_group(hdf_name(stream))
        if "name" not in group.attrs:
            group.attrs["name"] = _string_attr(stream)
        dset_name = hdf_name(product)
        if dset_name in group:
            raise ValueError(f"/streams/{stream}/{product} already exists in this block")
        dset = group.create_dataset(
            dset_name,
            shape=(n_channels, 0),
            maxshape=(n_channels, None),
            chunks=(n_channels, self.chunk_len(n_channels)),
            dtype=self._dtype,
            **self._compression_kwargs(),
        )
        _write_encoded(dset, encoded)

        in_hz = sfreq_in_hz if sfreq_in_hz is not None else attrs.get("sfreq_in_hz")
        record_attrs = (
            dict(filter_attrs)
            if filter_attrs is not None
            else {k: v for k, v in attrs.items() if k not in ("channel_ids", "units")}
        )
        handle = ProductHandle(
            stream=stream,
            product=product,
            role=role,
            n_channels=n_channels,
            sfreq_out_hz=float(sfreq_out_hz),
            sfreq_in_hz=float(in_hz) if in_hz is not None else float(sfreq_out_hz),
            n_samples_in=n_samples_in,
            filter_attrs=_jsonable(record_attrs),
            _dataset=dset,
            _dtype=self._dtype,
            _hasher=hashlib.sha256(),
            _row_hashers=[hashlib.sha256() for _ in range(n_channels)],
        )
        self._handles.append(handle)
        return handle

    # ---- epochs and summaries ------------------------------------------------

    def write_epochs(
        self,
        name: str,
        onsets: np.ndarray,
        offsets: np.ndarray,
        values: np.ndarray,
        attrs: dict[str, Any],
    ) -> None:
        """Write ``/epochs/<name>/{onsets,offsets,values}``.

        Onsets and offsets are float64 seconds relative to block t0 and must
        be one-dimensional. Numeric values are stored as float64; string
        values as a variable-length UTF-8 dataset (after the privacy check).
        Offsets may be empty when the format has none; otherwise they must
        match onsets in length. The group name is `hdf_name(name)` and the
        original name is the group's `name` attribute.
        """
        f = self._require_open()
        self.privacy.check(name, "epoch name")
        self.privacy.check_attrs(attrs, f"epochs/{name}")
        on = np.asarray(onsets, dtype=np.float64)
        off = np.asarray(offsets, dtype=np.float64)
        vals = np.asarray(values)
        for label, arr in (("onsets", on), ("offsets", off), ("values", vals)):
            if arr.ndim != 1:
                raise ValueError(f"epochs/{name}: {label} must be 1-D, got shape {arr.shape}")
        if off.size and off.size != on.size:
            raise ValueError(f"epochs/{name}: {off.size} offsets for {on.size} onsets")
        if vals.size and vals.size != on.size:
            raise ValueError(f"epochs/{name}: {vals.size} values for {on.size} onsets")
        if vals.dtype.kind in ("U", "S", "O"):
            self.privacy.check_value(vals, f"epochs/{name} values")
        elif vals.dtype.kind not in ("i", "u", "f", "b"):
            raise ValueError(f"epochs/{name}: values of dtype {vals.dtype} are not supported")
        reserved = ("t0_s", "units", "n_events", "name")
        merged: dict[str, Any] = {k: v for k, v in attrs.items() if k not in reserved}
        merged.update(
            {
                "name": name,
                "t0_s": np.float64(0.0),
                "units": "seconds from block t0",
                "n_events": np.int64(on.size),
            }
        )
        encoded = _encode_attrs(merged)

        group_name = hdf_name(name)
        if group_name in f["epochs"]:
            raise ValueError(f"/epochs/{name} already exists in this block (as {group_name!r})")
        group = f["epochs"].create_group(group_name)
        group.create_dataset("onsets", data=on, dtype=np.float64)
        group.create_dataset("offsets", data=off, dtype=np.float64)
        if vals.dtype.kind in ("U", "S", "O"):
            group.create_dataset("values", data=_string_array(str(v) for v in vals))
        else:
            group.create_dataset("values", data=vals.astype(np.float64))
        _write_encoded(group, encoded)
        self.epochs_written.append(name)

    def write_summary(
        self,
        stream: str,
        arrays: dict[str, np.ndarray],
        attrs: dict[str, Any],
    ) -> None:
        """Write ``/summary/<stream>/<key>`` for every array, attrs on the group.

        Array names go through `hdf_name`; string arrays are privacy-checked
        element by element and stored as variable-length UTF-8.
        """
        f = self._require_open()
        self.privacy.check(stream, "summary stream name")
        self.privacy.check_attrs(attrs, f"summary/{stream}")
        prepared: list[tuple[str, np.ndarray]] = []
        for key, arr in arrays.items():
            self.privacy.check(str(key), f"summary/{stream} array name")
            data = np.asarray(arr)
            if data.dtype.kind in ("U", "S", "O"):
                self.privacy.check_value(data, f"summary/{stream}/{key}")
                data = _string_array(str(v) for v in data.ravel())
            elif data.dtype.kind == "b":
                data = data.astype(np.int8)
            elif data.dtype.kind not in ("i", "u", "f"):
                raise ValueError(f"summary/{stream}/{key}: dtype {data.dtype} is not supported")
            prepared.append((hdf_name(str(key)), data))
        encoded = _encode_attrs({k: v for k, v in attrs.items() if k != "name"})
        encoded["name"] = _string_attr(stream)

        group = f["summary"].require_group(hdf_name(stream))
        for key, data in prepared:
            if key in group:
                raise ValueError(f"/summary/{stream}/{key} already exists in this block")
            group.create_dataset(key, data=data)
        _write_encoded(group, encoded)
