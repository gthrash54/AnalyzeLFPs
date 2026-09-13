"""Building one block end to end, on the synthetic TDT export.

The property that carries everything else is the second test: reading a block
in windows, resampling each window on a padded read, and discarding the
padding must produce the same samples as resampling the whole stream at once.
If that ever drifts, every derivative has a seam every thirty seconds and no
downstream analysis would report it.

The rest guards the contract with the ledger: a data problem comes back as a
result with a status and a redacted message, never as an exception, and
nothing is left on disk when a block does not build.
"""

from __future__ import annotations

import math
from pathlib import Path

import h5py
import numpy as np
import pytest
from scipy.signal import resample_poly

from dbsspeech.derive.config import DeriveConfig
from dbsspeech.derive.model import BlockJob, Quarantine
from dbsspeech.derive.pipeline import build_block, resolve_entry, validate_epochs
from dbsspeech.derive.redact import Scrubber
from dbsspeech.derive.resample import design_antialias
from dbsspeech.io.base import EpochSeries, open_recording
from tests.fixtures.make_tdt_fixture import SFREQ_AUDIO, SFREQ_NEURAL, make_fixture

pytestmark = pytest.mark.unit

LFP_HZ = 400.0      # 2000 -> 400 is 1/5
MIC_HZ = 500.0      # 1000 -> 500 is 1/2


def _cfg(tmp_path: Path, **overrides) -> DeriveConfig:
    raw = {
        "store": {"root": str(tmp_path / "store"), "window_s": 0.5},
        "roles": {"streams": {"neur": "lfp", "mic_": "mic"}, "on_unmapped": "quarantine"},
        "products": {
            "lfp": {"name": "lfp", "target_hz": LFP_HZ},
            "mic": {"name": "mic", "target_hz": MIC_HZ},
        },
        "build": {"native_rate_block_patterns": ["increment"]},
        "privacy": {"redact_patterns": [r"u[gh]\d{4}-\d{6}-\d{6}"]},
    }
    raw.update(overrides)
    return DeriveConfig.model_validate(raw)


@pytest.fixture(scope="module")
def block_dir(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("uh0000") / "motor_baseline"
    d.mkdir()
    make_fixture(d / "uh0000_motor_baseline.mat")
    return d


def _job(block_dir: Path, block: str = "motor_baseline") -> BlockJob:
    return BlockJob(study_id="uh0000", session="stage1", block=block,
                    source_format="tdt_mat", local_dir=block_dir)


def _scrub(tmp_path: Path) -> Scrubber:
    return Scrubber([r"u[gh]\d{4}-\d{6}-\d{6}"], forbidden_path_roots=[tmp_path])


def _build(tmp_path: Path, block_dir: Path, cfg: DeriveConfig | None = None, **kw):
    cfg = cfg or _cfg(tmp_path)
    return build_block(_job(block_dir), cfg, tmp_path / "store",
                       provenance={"builder_version": "test"}, scrubber=_scrub(tmp_path), **kw), cfg


# ---- the happy path ----------------------------------------------------------

def test_a_block_builds_to_one_file_with_both_products(tmp_path, block_dir):
    result, cfg = _build(tmp_path, block_dir)
    assert result.status == "done", result.error_message
    out = tmp_path / "store" / result.out_relpath
    assert out.exists() and out.suffix == ".h5"
    assert not list((tmp_path / "store").rglob("*.part"))
    names = {(r.stream, r.product, r.role) for r in result.products}
    assert names == {("neur", "lfp", "lfp"), ("mic_", "mic", "mic")}
    with h5py.File(out, "r") as f:
        lfp = f["streams/neur/lfp"]
        assert lfp.attrs["sfreq_out_hz"] == LFP_HZ
        assert lfp.attrs["t0_s"] == 0.0
        assert "usable_bandwidth_hz" in lfp.attrs
        assert "summary/neur/psd_db" in f


def test_windowed_resampling_equals_a_single_shot_resample(tmp_path, block_dir):
    """The seam test. 0.5 s windows on a multi-second block, compared sample for sample."""
    result, cfg = _build(tmp_path, block_dir)
    assert result.status == "done", result.error_message
    entry = resolve_entry(_job(block_dir))
    with open_recording(entry, format="tdt_mat") as rec:
        x = rec.read("neur")
    up, down = 1, 5
    taps, _ = design_antialias(up, down, SFREQ_NEURAL)
    expected = resample_poly(x, up, down, axis=-1, window=taps, padtype="line")
    with h5py.File(tmp_path / "store" / result.out_relpath, "r") as f:
        got = f["streams/neur/lfp"][...]
    assert got.shape == expected.shape
    assert got.shape[1] == math.ceil(x.shape[1] * up / down)
    np.testing.assert_allclose(got, expected.astype(got.dtype), rtol=0, atol=1e-5)


def test_the_output_length_is_the_exact_ratio_for_every_product(tmp_path, block_dir):
    result, _ = _build(tmp_path, block_dir)
    by = {r.product: r for r in result.products}
    assert by["lfp"].n_samples_out == math.ceil(by["lfp"].n_samples_in * LFP_HZ / SFREQ_NEURAL)
    assert by["mic"].n_samples_out == math.ceil(by["mic"].n_samples_in * MIC_HZ / SFREQ_AUDIO)


# ---- policy: native rate and the audio split ---------------------------------

def test_a_stimulation_block_keeps_native_rate(tmp_path, block_dir):
    cfg = _cfg(tmp_path)
    job = BlockJob(study_id="uh0000", session="stage1", block="increment1_depth1",
                   source_format="tdt_mat", local_dir=block_dir)
    result = build_block(job, cfg, tmp_path / "store",
                         provenance={"builder_version": "test"}, scrubber=_scrub(tmp_path))
    assert result.status == "done", result.error_message
    lfp = next(r for r in result.products if r.product == "lfp")
    assert lfp.sfreq_out_hz == SFREQ_NEURAL
    assert lfp.n_samples_out == lfp.n_samples_in
    assert lfp.filter_attrs == {}


def test_microphone_products_go_to_the_audio_root_when_given(tmp_path, block_dir):
    cfg = _cfg(tmp_path)
    audio_root = tmp_path / "audio"
    result = build_block(_job(block_dir), cfg, tmp_path / "store",
                         provenance={"builder_version": "test"}, scrubber=_scrub(tmp_path),
                         audio_root=audio_root)
    assert result.status == "done", result.error_message
    assert result.audio_relpath is not None
    with h5py.File(tmp_path / "store" / result.out_relpath, "r") as f:
        assert "streams/neur/lfp" in f
        assert "streams/mic_" not in f
    with h5py.File(audio_root / result.audio_relpath, "r") as f:
        assert "streams/mic_/mic" in f
        assert "streams/neur" not in f


# ---- refusals come back as results, and leave nothing behind ------------------

def test_an_unmapped_stream_quarantines_and_writes_nothing(tmp_path, block_dir):
    cfg = _cfg(tmp_path, roles={"streams": {"mic_": "mic"}, "on_unmapped": "quarantine"})
    result, _ = _build(tmp_path, block_dir, cfg)
    assert result.status == "quarantined"
    assert result.quarantine_reason == "unmapped_stream"
    assert "neur" in (result.error_message or "")
    assert not list((tmp_path / "store").rglob("*.h5"))
    assert not list((tmp_path / "store").rglob("*.part"))


def test_a_missing_source_fails_with_a_redacted_message(tmp_path):
    cfg = _cfg(tmp_path)
    missing = tmp_path / "uh0000" / "nope"
    missing.mkdir(parents=True)
    job = BlockJob(study_id="uh0000", session="stage1", block="nope",
                   source_format="tdt_mat", local_dir=missing)
    result = build_block(job, cfg, tmp_path / "store",
                         provenance={"builder_version": "test"}, scrubber=_scrub(tmp_path))
    assert result.status in ("failed", "quarantined")
    assert str(tmp_path) not in (result.error_message or "")


def test_epochs_off_the_block_clock_are_refused(tmp_path):
    cfg = _cfg(tmp_path)
    good = {"PeA/": EpochSeries("PeA/", onsets=np.array([0.5, 1.0]))}
    assert set(validate_epochs(good, 10.0, cfg)) == {"PeA/"}
    dropped = {"Note": EpochSeries("Note", onsets=np.array([0.5]))}
    assert validate_epochs(dropped, 10.0, cfg) == {}
    unix = {"PeA/": EpochSeries("PeA/", onsets=np.array([1.7e9]))}
    with pytest.raises(Quarantine, match="epoch_clock_origin"):
        validate_epochs(unix, 10.0, cfg)
    # A frame time a few milliseconds past the end of a very short block is
    # legitimate (seen on a 1.6 s block in the archive), not a clock error.
    edge = {"Cam1": EpochSeries("Cam1", onsets=np.array([0.07, 1.620]))}
    assert set(validate_epochs(edge, 1.6, cfg)) == {"Cam1"}
    far = {"Cam1": EpochSeries("Cam1", onsets=np.array([1.9]))}
    with pytest.raises(Quarantine, match="epoch_clock_origin"):
        validate_epochs(far, 1.6, cfg)


def test_resolve_entry_prefers_the_lab_naming_then_the_sole_candidate(tmp_path):
    d = tmp_path / "blk"
    d.mkdir()
    (d / "other.mat").write_bytes(b"")
    job = BlockJob("uh0000", "s", "blk", "tdt_mat", d)
    assert resolve_entry(job) == d / "other.mat"
    (d / "uh0000_blk.mat").write_bytes(b"")
    assert resolve_entry(job) == d / "uh0000_blk.mat"
    (d / "third.mat").write_bytes(b"")
    (d / "uh0000_blk.mat").unlink()
    with pytest.raises(Quarantine, match="entry_not_unique"):
        resolve_entry(job)
