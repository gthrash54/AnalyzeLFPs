"""The derivative-store policy, validated, with a stable hash.

`configs/derive.yaml` is the source of truth. This module turns it into typed
objects with `pydantic.BaseModel` (extra keys refused, so a typo in the YAML is
an error and not a silently ignored setting) and gives the resolved policy a
sha256 that every output records. A block is rebuilt when, and only when, the
policy that built it has changed.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[3] / "configs" / "derive.yaml"

Role = Literal["lfp", "emg", "mic", "micro", "monitor"]
ROLES: tuple[str, ...] = ("lfp", "emg", "mic", "micro", "monitor")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Compression(_Strict):
    name: Literal["gzip", "lzf", "none"] = "gzip"
    level: int = Field(default=1, ge=0, le=9)
    shuffle: bool = True


class StoreConfig(_Strict):
    root: str = "~/Dropbox/DBS Derivatives"
    # Where microphone products go. None means beside everything else. Kept
    # separate because operating-room audio is a HIPAA identifier and the main
    # root may be a synced folder.
    audio_root: str | None = None
    format: Literal["hdf5"] = "hdf5"
    dtype: Literal["float32", "float64"] = "float32"
    compression: Compression = Compression()
    chunk_target_bytes: int = Field(default=4 * 1024 * 1024, gt=0)
    window_s: float = Field(default=30.0, gt=0)

    def root_path(self) -> Path:
        return Path(self.root).expanduser()

    def audio_root_path(self) -> Path:
        return Path(self.audio_root).expanduser() if self.audio_root else self.root_path()


class BuildConfig(_Strict):
    max_attempts: int = Field(default=3, ge=1)
    stale_timeout_s: float = Field(default=3600.0, gt=0)
    # Blocks matching any of these (re.search, case-insensitive) keep every
    # stream at native rate: stimulation artifact must be handled before any
    # anti-alias filter smears pulse edges across the ERNA window.
    native_rate_block_patterns: list[str] = Field(default_factory=list)
    native_rate_when_stim_epochs_present: bool = True
    stim_epoch_stores: list[str] = Field(default_factory=list)

    @field_validator("native_rate_block_patterns")
    @classmethod
    def _compile(cls, v: list[str]) -> list[str]:
        for p in v:
            _compile_or_value_error(p)
        return v

    def is_native_rate_block(self, block: str, epoch_names: Sequence[str] = ()) -> bool:
        """Stim-on by name, or by a stimulation epoch store being present."""
        if any(re.search(p, block, re.IGNORECASE) for p in self.native_rate_block_patterns):
            return True
        if self.native_rate_when_stim_epochs_present:
            present = set(epoch_names)
            return any(s in present for s in self.stim_epoch_stores)
        return False


class ResampleConfig(_Strict):
    passband_fraction_of_out_nyquist: float = Field(default=0.8, gt=0, lt=1)
    stopband_fraction_of_out_nyquist: float = Field(default=1.0, gt=0, le=1)
    stopband_attenuation_db: float = Field(default=90.0, gt=0)
    max_denominator: int = Field(default=3125, gt=0)
    require_measured_alias_floor_db: float = -80.0


class RolesConfig(_Strict):
    streams: dict[str, Role] = Field(default_factory=dict)
    channel_patterns: dict[str, list[str]] = Field(default_factory=dict)
    on_unmapped: Literal["quarantine", "skip"] = "quarantine"

    @field_validator("channel_patterns")
    @classmethod
    def _patterns_compile_and_name_roles(cls, v: dict[str, list[str]]) -> dict[str, list[str]]:
        for role, patterns in v.items():
            if role not in ROLES and role != "ignore":
                raise ValueError(f"channel_patterns key {role!r} is not a role")
            for p in patterns:
                _compile_or_value_error(p)
        return v


class ProductConfig(_Strict):
    name: str
    # 'native' keeps the stream at its recorded rate.
    target_hz: float | Literal["native"]

    @field_validator("target_hz")
    @classmethod
    def _positive_or_native(cls, v: float | str) -> float | str:
        if v != "native" and float(v) <= 0:
            raise ValueError("target_hz must be positive or 'native'")
        return v


class EpochsConfig(_Strict):
    keep_all: bool = True
    drop_stores: list[str] = Field(default_factory=lambda: ["Note"])
    max_onset_slack_fraction: float = Field(default=0.01, ge=0)


class PsdConfig(_Strict):
    enabled: bool = True
    nperseg_s: float = Field(default=1.0, gt=0)
    overlap: float = Field(default=0.5, ge=0, lt=1)
    aggregate: Literal["median", "mean"] = "median"


class SummaryConfig(_Strict):
    full_rate_psd: PsdConfig = PsdConfig()
    per_channel_stats: list[str] = Field(
        default_factory=lambda: ["rms", "min", "max", "n_at_rail", "pc1_variance_fraction"]
    )


class ReferencingConfig(_Strict):
    apply: Literal["none"] = "none"
    record_common_mode: bool = True


class PrivacyConfig(_Strict):
    emit_source_filenames: bool = False
    emit_acquisition_datetime: bool = False
    redact_patterns: list[str] = Field(default_factory=list)

    @field_validator("redact_patterns")
    @classmethod
    def _compile(cls, v: list[str]) -> list[str]:
        for p in v:
            _compile_or_value_error(p)
        return v


def _compile_or_value_error(pattern: str) -> None:
    """pydantic only turns ValueError into a validation error; re.error is not one."""
    try:
        re.compile(pattern)
    except re.error as exc:
        raise ValueError(f"pattern {pattern!r} does not compile: {exc}") from exc


class DeriveConfig(_Strict):
    schema_version: int = 1
    store: StoreConfig = StoreConfig()
    build: BuildConfig = BuildConfig()
    resample: ResampleConfig = ResampleConfig()
    roles: RolesConfig = RolesConfig()
    products: dict[str, ProductConfig] = Field(default_factory=dict)
    epochs: EpochsConfig = EpochsConfig()
    summary: SummaryConfig = SummaryConfig()
    source_preference: list[str] = Field(
        default_factory=lambda: ["tdt_mat", "tdt_tank", "brainvision"]
    )
    epochs_always_from_tsq: bool = True
    referencing: ReferencingConfig = ReferencingConfig()
    privacy: PrivacyConfig = PrivacyConfig()

    @field_validator("products")
    @classmethod
    def _products_name_roles(cls, v: dict[str, ProductConfig]) -> dict[str, ProductConfig]:
        for role in v:
            if role not in ROLES:
                raise ValueError(f"products key {role!r} is not a role")
        return v

    def product_for(self, role: str) -> ProductConfig | None:
        return self.products.get(role)

    def sha256(self) -> str:
        """Hash of the resolved policy, independent of key order and layout."""
        blob = json.dumps(self.model_dump(mode="json"), sort_keys=True,
                          separators=(",", ":")).encode()
        return hashlib.sha256(blob).hexdigest()


def load_config(path: Path | str | None = None) -> DeriveConfig:
    """Read and validate `configs/derive.yaml`, or the file given."""
    p = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    raw: Any = yaml.safe_load(p.read_text()) or {}
    return DeriveConfig.model_validate(raw)
