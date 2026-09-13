"""Build one block: read it locally, resample, summarize, write, and report.

`build_block` is the only entry point and it is pure with respect to the
outside world: it reads from `job.local_dir`, writes under `out_root` (and
`audio_root` for microphone products), and returns a `BlockResult`. It never
contacts Box, never deletes a source, and never raises for a data problem; a
block that cannot be built comes back as `quarantined` (policy says stop) or
`failed` (something broke), with an already-redacted message.

Streaming. A block is read in windows of `cfg.store.window_s` seconds through
`Recording.read(tmin, tmax)`, so peak memory is a few hundred megabytes per
worker regardless of block length. Each window is resampled independently
with `scipy.signal.resample_poly` (via `derive.resample`) on a padded read and
the padding is discarded, which reproduces a single-shot resample exactly
because the anti-alias filter is finite: the padding is longer than half the
filter, and window starts are aligned to multiples of the decimation factor
so every window's output lands on the same global sample grid.

Stimulation. A block the policy calls stim-on (`cfg.build.is_native_rate_block`)
keeps every stream at native rate. The anti-alias filter rings for several
milliseconds around every pulse edge, which at 130 Hz is every sample, so
artifact handling has to happen before any decimation, not after.

Summaries are computed at native rate before resampling, so the store still
describes what it no longer holds above the cutoff.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Sequence
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from dbsspeech.derive.config import DeriveConfig
from dbsspeech.derive.model import BlockJob, BlockResult, ProductRecord, Quarantine
from dbsspeech.derive.redact import Scrubber, redact_exception
from dbsspeech.derive.resample import (
    FilterReport,
    FilterSpec,
    RateNotRational,
    design_antialias,
    exact_ratio,
    resample_exact,
)
from dbsspeech.derive.roles import classify_stream, group_by_role
from dbsspeech.derive.summarize import StreamSummarizer
from dbsspeech.derive.writer import BlockWriter
from dbsspeech.io.base import EpochSeries, PrivacyPolicy, Recording, StreamInfo, open_recording

# The build passes its own policy rather than trusting configs/privacy.yaml, so
# the store cannot inherit a wrong setting. Filenames are never surfaced and
# every field any reader has ever marked sensitive is withheld.
BUILD_PRIVACY_POLICY = PrivacyPolicy(
    filenames_deidentified=False,
    restricted_metadata_fields=frozenset({
        "Subject", "Experiment", "User", "blockname", "tankpath",
        "subject_info", "meas_date", "experimenter", "description",
    }),
)

# Formats whose readers group everything into one stream and name channels.
CHANNEL_NAMED_FORMATS = frozenset({"brainvision", "edf"})

UNITS_BY_FORMAT = {
    "tdt_tank": "unknown (TDT Scale: Unity)",
    "tdt_mat": "unknown (TDT Scale: Unity)",
    "brainvision": "V (as scaled by MNE)",
    "edf": "V (as scaled by MNE)",
}


@dataclass(frozen=True)
class ProductPlan:
    """One thing to write: a stream (or a channel subset of it) at a rate."""

    stream: str
    role: str
    product: str
    channels: tuple[int, ...] | None   # None means every channel, in order
    sfreq_in_hz: float
    sfreq_out_hz: float
    native: bool
    reason: str                        # why this rate: policy, native product, stim-on


class _FilterCache:
    """One designed filter per (input rate, output rate); design is not free."""

    def __init__(self, spec: FilterSpec, max_denominator: int) -> None:
        self.spec = spec
        self.max_denominator = max_denominator
        self._cache: dict[tuple[float, float], tuple[int, int, np.ndarray, FilterReport]] = {}

    def get(self, sfreq_in: float, sfreq_out: float) -> tuple[int, int, np.ndarray, FilterReport]:
        key = (sfreq_in, sfreq_out)
        if key not in self._cache:
            try:
                up, down = exact_ratio(sfreq_in, sfreq_out, self.max_denominator)
            except RateNotRational as exc:
                raise Quarantine("rate_not_exactly_rational", str(exc)) from exc
            try:
                taps, report = design_antialias(up, down, sfreq_in, self.spec)
            except ValueError as exc:
                raise Quarantine("filter_did_not_meet_spec", str(exc)) from exc
            self._cache[key] = (up, down, taps, report)
        return self._cache[key]


def resolve_entry(job: BlockJob) -> Path:
    """The path to hand to `open_recording` for this job.

    TDT tanks open on the block directory. The .mat export and BrainVision open
    on a file: `job.entry` if given, else the one candidate in the directory,
    preferring `<study_id>_<block>.mat` because that is how the lab names them.
    """
    if job.entry is not None:
        return job.entry
    d = job.local_dir
    if job.source_format == "tdt_tank":
        return d
    suffix = {"tdt_mat": ".mat", "brainvision": ".vhdr", "edf": ".edf"}.get(job.source_format)
    if suffix is None:
        raise Quarantine("unknown_format", job.source_format)
    preferred = d / f"{job.study_id}_{job.block}{suffix}"
    if preferred.exists():
        return preferred
    candidates = sorted(p for p in d.glob(f"*{suffix}") if p.is_file())
    if len(candidates) != 1:
        raise Quarantine(
            "entry_not_unique",
            f"{len(candidates)} {suffix} files in the block directory; name one in job.entry",
        )
    return candidates[0]


def plan_products(
    rec: Recording, job: BlockJob, cfg: DeriveConfig, native_block: bool
) -> list[ProductPlan]:
    """Decide what gets written for this block, and at what rate. Pure."""
    plans: list[ProductPlan] = []
    named = job.source_format in CHANNEL_NAMED_FORMATS
    for name, info in rec.streams.items():
        if named:
            groups = group_by_role(list(info.channel_ids), cfg)   # may raise Quarantine
            targets = [(role, tuple(idx)) for role, idx in groups.items()]
        else:
            role = classify_stream(name, cfg)                     # may raise Quarantine
            targets = [(role, None)] if role else []
        for role, channels in targets:
            product = cfg.product_for(role)
            if product is None:
                continue
            if native_block:
                out, native, reason = info.sfreq_hz, True, "stimulation block: native rate"
            elif product.target_hz == "native":
                out, native, reason = info.sfreq_hz, True, "product policy: native"
            elif float(product.target_hz) >= info.sfreq_hz:
                out, native = info.sfreq_hz, True
                reason = "target at or above native; never upsampled"
            else:
                out, native, reason = float(product.target_hz), False, "product policy"
            plans.append(ProductPlan(
                stream=name, role=role, product=product.name, channels=channels,
                sfreq_in_hz=info.sfreq_hz, sfreq_out_hz=out, native=native, reason=reason,
            ))
    return plans


def validate_epochs(
    epochs: dict[str, EpochSeries], duration_s: float, cfg: DeriveConfig
) -> dict[str, EpochSeries]:
    """Drop configured stores and refuse onsets that cannot be on the block clock.

    A latent reader bug can put the clock origin on a stray tiny timestamp,
    which makes every onset read as a Unix epoch (about 1.7e9 s). Anything
    outside ``[0, duration * (1 + slack)]`` quarantines the block.
    """
    keep: dict[str, EpochSeries] = {}
    # A fractional slack alone is too tight for a block of a second or two: a
    # camera frame time can legitimately sit a few milliseconds past the last
    # sample. Fifty milliseconds is far below anything a wrong clock origin
    # produces (that error is on the order of 1e9 seconds).
    limit = duration_s * (1.0 + cfg.epochs.max_onset_slack_fraction) + 0.05
    for name, es in epochs.items():
        if name in cfg.epochs.drop_stores or len(es) == 0:
            continue
        lo, hi = float(np.min(es.onsets)), float(np.max(es.onsets))
        if lo < 0.0 or hi > limit:
            raise Quarantine(
                "epoch_clock_origin",
                f"{name}: onsets span [{lo:.3f}, {hi:.3f}] s but the block is {duration_s:.1f} s",
            )
        keep[name] = es
    return keep


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            digest.update(block)
    return digest.hexdigest()


def _windows(n_samples: int, window: int, down: int) -> list[tuple[int, int]]:
    """Half-open input ranges covering [0, n), starts aligned to `down`."""
    step = max(down, (window // down) * down)
    return [(a, min(n_samples, a + step)) for a in range(0, n_samples, step)]


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def _stream_product(
    rec: Recording,
    info: StreamInfo,
    plan: ProductPlan,
    cfg: DeriveConfig,
    writer: BlockWriter,
    filters: _FilterCache,
    units: str,
    native_block: bool,
) -> ProductRecord:
    """Read one stream in windows, summarize at native rate, resample, write."""
    n_in = info.n_samples
    f_in = info.sfreq_hz
    channels = list(plan.channels) if plan.channels is not None else None
    n_ch = len(channels) if channels is not None else info.n_channels
    ids = tuple(info.channel_ids[i] for i in channels) if channels is not None else info.channel_ids

    if plan.native:
        up = down = 1
        taps = None
        report: FilterReport | None = None
        pad = 0
    else:
        up, down, taps, report = filters.get(f_in, plan.sfreq_out_hz)
        pad = _ceil_div(len(taps) - 1, 2 * up) + 2

    summarizer = StreamSummarizer(f_in, n_ch, cfg.summary)
    attrs: dict[str, Any] = {
        "units": units,
        "channel_ids": list(ids),
        "rate_reason": plan.reason,
        "native_rate_block": native_block,
        "window_s": cfg.store.window_s,
    }
    if report is not None:
        # The measured report lives on the dataset itself, where a reader that
        # never imports this package still finds it. The two numbers a
        # guardrail consumes keep their plain names; the rest are prefixed so
        # they cannot collide with the writer's own rate attributes.
        attrs["usable_bandwidth_hz"] = report.usable_bandwidth_hz
        attrs["alias_floor_db"] = report.alias_floor_db
        attrs.update({f"filter_{k}": v for k, v in report.as_attrs().items()})
    else:
        attrs["usable_bandwidth_hz"] = f_in / 2.0
    handle = writer.open_product(
        plan.stream, plan.product, plan.role, n_ch, plan.sfreq_out_hz, attrs,
        sfreq_in_hz=f_in, n_samples_in=n_in,
        # Empty, not None, for a native-rate product: the writer would otherwise
        # fill the record with the dataset attrs, and "no filter" should read
        # as no filter.
        filter_attrs=report.as_attrs() if report is not None else {},
    )

    window = int(cfg.store.window_s * f_in)
    for a, b in _windows(n_in, window, down):
        s = max(0, ((a - pad) // down) * down) if pad else a
        e = min(n_in, b + pad)
        x = rec.read(info.name, channels, tmin=s / f_in, tmax=e / f_in)
        if x.shape[1] != e - s:
            raise RuntimeError(
                f"reader returned {x.shape[1]} samples for [{s}, {e}) of {info.name}"
            )
        summarizer.update(x[:, a - s : b - s])
        if plan.native:
            handle.append(x[:, a - s : b - s])
            continue
        y = resample_exact(x, up, down, taps)
        base = (s * up) // down          # s is a multiple of down, so this is exact
        j0 = _ceil_div(a * up, down) - base
        j1 = _ceil_div(b * up, down) - base
        handle.append(y[:, j0:j1])

    record = handle.close()
    summary = summarizer.finalize()
    key = plan.stream if plan.channels is None else f"{plan.stream}_{plan.role}"
    writer.write_summary(key, summary.as_arrays(), {
        **summary.as_attrs(), "role": plan.role, "product": plan.product,
        "sfreq_hz": f_in, "channel_ids": list(ids),
    })
    return record


def build_block(
    job: BlockJob,
    cfg: DeriveConfig,
    out_root: Path,
    *,
    provenance: dict[str, Any],
    scrubber: Scrubber,
    audio_root: Path | None = None,
    spec: FilterSpec | None = None,
) -> BlockResult:
    """Build one staged block into the store. Never raises for a data problem."""
    t0 = time.monotonic()
    out_root = Path(out_root).expanduser()
    audio_root = Path(audio_root).expanduser() if audio_root is not None else None
    if audio_root is not None and audio_root == out_root:
        audio_root = None

    def finish(**kw: Any) -> BlockResult:
        return BlockResult(
            study_id=job.study_id, session=job.session, block=job.block,
            seconds=time.monotonic() - t0, **kw,
        )

    try:
        entry = resolve_entry(job)
        prov = dict(provenance)
        if entry.is_file():
            prov.setdefault("source_sha256", _sha256_file(entry))
            prov.setdefault("source_bytes", entry.stat().st_size)
        prov.setdefault("config_sha256", cfg.sha256())

        filt_spec = spec or FilterSpec(
            passband_fraction_of_out_nyquist=cfg.resample.passband_fraction_of_out_nyquist,
            stopband_fraction_of_out_nyquist=cfg.resample.stopband_fraction_of_out_nyquist,
            stopband_attenuation_db=cfg.resample.stopband_attenuation_db,
            require_measured_alias_floor_db=cfg.resample.require_measured_alias_floor_db,
        )
        filters = _FilterCache(filt_spec, cfg.resample.max_denominator)
        units = UNITS_BY_FORMAT.get(job.source_format, "unknown")

        with ExitStack() as stack:
            rec = stack.enter_context(
                open_recording(entry, format=job.source_format, policy=BUILD_PRIVACY_POLICY)
            )
            streams = rec.streams
            epochs = rec.epochs
            if not streams:
                raise Quarantine("no_streams", "the recording declares no continuous streams")
            duration = max(info.duration_s for info in streams.values())
            native_block = cfg.build.is_native_rate_block(job.block, list(epochs.keys()))
            plans = plan_products(rec, job, cfg, native_block)
            if not plans:
                raise Quarantine("nothing_to_write", "no stream maps to a product under policy")
            kept_epochs = validate_epochs(epochs, duration, cfg)

            main = stack.enter_context(BlockWriter(out_root, job, cfg, prov))
            audio: BlockWriter | None = None
            if audio_root is not None and any(p.role == "mic" for p in plans):
                audio = stack.enter_context(BlockWriter(audio_root, job, cfg, prov))

            records: list[ProductRecord] = []
            for plan in plans:
                target = audio if (audio is not None and plan.role == "mic") else main
                records.append(_stream_product(
                    rec, streams[plan.stream], plan, cfg, target, filters, units, native_block
                ))

            epoch_attrs = {"source": job.source_format, "t0_s": 0.0}
            for name, es in kept_epochs.items():
                for w in (main, audio):
                    if w is not None:
                        w.write_epochs(name, es.onsets, es.offsets, es.values,
                                       {**epoch_attrs, "n_events": len(es)})

        out_path = main.path
        audio_rel = str(audio.path.relative_to(audio_root)) if audio is not None else None
        return finish(
            status="done",
            out_relpath=str(out_path.relative_to(out_root)),
            out_sha256=_sha256_file(out_path),
            out_bytes=out_path.stat().st_size,
            audio_relpath=audio_rel,
            products=records,
            epochs_written=sorted(kept_epochs),
        )
    except Quarantine as q:
        return finish(
            status="quarantined", quarantine_reason=q.reason,
            error_class="Quarantine", error_message=scrubber.scrub(q.detail),
        )
    except KeyboardInterrupt:
        raise
    except Exception as exc:  # noqa: BLE001  (every failure must reach the ledger)
        cls, msg = redact_exception(exc, scrubber)
        return finish(status="failed", error_class=cls, error_message=msg)


def default_provenance(builder_version: str = "unknown") -> dict[str, Any]:
    """What every output should carry beyond the block identity."""
    from dbsspeech.runs.record import (  # noqa: PLC0415  (avoid a heavy import at module load)
        _git,
        versions,
    )

    return {
        "builder_version": builder_version,
        "git_sha": _git("rev-parse", "HEAD") or "unknown",
        "library_versions": json.dumps(versions(), sort_keys=True),
    }


__all__: Sequence[str] = (
    "BUILD_PRIVACY_POLICY", "ProductPlan", "build_block", "default_provenance",
    "plan_products", "resolve_entry", "validate_epochs",
)
