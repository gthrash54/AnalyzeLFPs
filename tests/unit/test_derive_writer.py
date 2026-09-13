"""The block writer: crash-safe, self-describing, and privacy-refusing.

Four properties are guarded, each against the file on disk rather than against
the writer's own bookkeeping.

A finished block must be readable with plain h5py, arrays bit-exact and every
attribute present, because the store's whole point is that nothing downstream
imports the builder. A block is `.part` until the writer commits and `.h5`
after, and an exception, even one raised while entering, leaves neither, so a
reader never meets a half-written file and a second writer never steals the
first one's file. The recorded `data_sha256` must equal a hash computed
independently from the same samples, so a rerun can prove it reproduced the
store. And the writer must refuse a Box path, a tank stem in any spelling, a
date in any spelling, or a filesystem path in any name, key or value it is
handed, whatever the config says, because it is the last thing between the raw
archive and a synced derivative.

Every identifier-shaped string in this file is synthetic: study `uh0000` is not
in the archive and the date fields spell the last day of 1999.
"""

from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
from importlib import metadata
from pathlib import Path

import h5py
import numpy as np
import pytest

from dbsspeech.derive.config import DeriveConfig, load_config
from dbsspeech.derive.model import BlockJob
from dbsspeech.derive.writer import (
    BlockWriter,
    PrivacyChecker,
    PrivacyRefusal,
    hdf_name,
    recompute_hashes,
    sanitize_name,
)

pytestmark = pytest.mark.unit

REDACT = [r"u[gh]\d{4}-\d{6}-\d{6}", r"\d{1,2}/\d{1,2}/\d{4}", r"\d{4}-\d{2}-\d{2}"]
# Synthetic: study 3099 does not exist and the timestamp is 1999-12-31 23:59:59.
STEM = "uh0000-991231-235959"
ISO_DATE = "1999-12-31"
SLASH_DATE = "12/31/1999"


@pytest.fixture
def cfg() -> DeriveConfig:
    return DeriveConfig.model_validate(
        {
            "store": {"chunk_target_bytes": 64, "dtype": "float32"},
            "privacy": {"redact_patterns": REDACT},
        }
    )


@pytest.fixture
def job(tmp_path: Path) -> BlockJob:
    return BlockJob(
        study_id="uh0000",
        session="intraop 1",
        block="Block A/3",
        source_format="tdt_mat",
        local_dir=tmp_path / "staged",
    )


def _text(value: object) -> str:
    """Fixed-length UTF-8 attributes come back from h5py as bytes."""
    return value.decode("utf-8") if isinstance(value, bytes) else str(value)


def _chunks(n_channels: int = 3, sizes: tuple[int, ...] = (5, 7, 2)) -> list[np.ndarray]:
    rng = np.random.default_rng(7)
    return [rng.standard_normal((n_channels, n)) for n in sizes]


# ---- names and paths -----------------------------------------------------------

def test_names_are_sanitized_to_a_safe_charset_with_spaces_as_underscores():
    assert sanitize_name("intraop 1") == "intraop_1"
    assert sanitize_name("Block A/3") == "Block_A_3"
    assert sanitize_name("clean-name_v1.2") == "clean-name_v1.2"


def test_a_name_that_sanitizes_to_nothing_is_refused():
    with pytest.raises(ValueError):
        sanitize_name("   ")


def test_hdf_names_drop_a_trailing_slash_and_never_nest():
    assert hdf_name("PeA/") == "PeA"
    assert hdf_name("a/b") == "a_b"
    assert hdf_name("mic_") == "mic_"


def test_the_output_path_follows_the_layout_and_the_originals_are_kept(tmp_path, job, cfg):
    with BlockWriter(tmp_path / "store", job, cfg, {}) as w:
        pass
    assert w.path == tmp_path / "store" / "uh0000" / "intraop_1__Block_A_3.h5"
    with h5py.File(w.path, "r") as f:
        assert _text(f.attrs["session"]) == "intraop 1"
        assert _text(f.attrs["block"]) == "Block A/3"
        assert _text(f.attrs["session_sanitized"]) == "intraop_1"


# ---- lifecycle: .part until commit, nothing on failure -------------------------

def test_the_file_is_part_while_open_and_h5_only_after_a_clean_exit(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        assert w.part_path.exists()
        assert not w.path.exists()
    assert w.path.exists()
    assert not w.part_path.exists()


def test_an_exception_inside_the_context_leaves_no_part_and_no_h5(tmp_path, job, cfg):
    with pytest.raises(RuntimeError, match="boom"), BlockWriter(tmp_path, job, cfg, {}) as w:
        h = w.open_product("ecos", "lfp", "lfp", 2, 8000.0, {"channel_ids": ["a", "b"]})
        h.append(np.zeros((2, 10)))
        raise RuntimeError("boom")
    assert not w.part_path.exists()
    assert not w.path.exists()
    assert list(w.path.parent.iterdir()) == []


def test_a_failure_while_entering_leaves_no_part_and_no_open_handle(
    tmp_path, job, cfg, monkeypatch
):
    """Python skips __exit__ when __enter__ raises, so __enter__ cleans up itself."""
    import dbsspeech.derive.writer as writer_mod

    def explode() -> str:
        raise RuntimeError("version lookup failed")

    monkeypatch.setattr(writer_mod, "_builder_version", explode)
    w = BlockWriter(tmp_path, job, cfg, {})
    with pytest.raises(RuntimeError, match="version lookup"), w:
        pass
    assert not w.part_path.exists()
    assert not w.path.exists()
    assert w._file is None


@pytest.mark.parametrize(
    "value",
    [
        Path("/x/y"),
        dt.datetime(1999, 12, 31, 23, 59),
        dt.date(1999, 12, 31),
        np.datetime64("1999-12-31"),
    ],
    ids=["path", "datetime", "date", "datetime64"],
)
def test_a_path_or_datetime_in_provenance_is_refused_before_any_file_exists(
    tmp_path, job, cfg, value
):
    with pytest.raises(PrivacyRefusal):
        BlockWriter(tmp_path, job, cfg, {"source": value})
    assert not any(tmp_path.rglob("*.h5*"))


def test_an_unencodable_provenance_value_fails_before_any_file_exists(tmp_path, job, cfg):
    with pytest.raises(TypeError):
        BlockWriter(tmp_path, job, cfg, {"mixed": ["a", 1]})
    with pytest.raises(TypeError):
        BlockWriter(tmp_path, job, cfg, {"obj": object()})
    assert not any(tmp_path.rglob("*.h5*"))


def test_a_stale_part_from_an_earlier_crash_is_overwritten(tmp_path, job, cfg):
    part = tmp_path / "uh0000" / "intraop_1__Block_A_3.h5.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(b"garbage from a crashed run")
    with BlockWriter(tmp_path, job, cfg, {}):
        pass
    assert not part.exists()
    with h5py.File(part.with_suffix(""), "r") as f:
        assert "streams" in f


def test_a_second_writer_on_the_same_block_cannot_steal_the_first_ones_file(tmp_path, job, cfg):
    """HDF5's file lock refuses the second opener, and the first writer's data lands."""
    with BlockWriter(tmp_path, job, cfg, {}) as first:
        h = first.open_product("ecos", "lfp", "lfp", 1, 8000.0, {})
        h.append(np.full((1, 6), 1.0))
        second = BlockWriter(tmp_path, job, cfg, {})
        with pytest.raises(OSError):
            second.__enter__()
        assert first.part_path.exists(), "the loser must not unlink the live .part"
    assert first.path.exists()
    assert not first.part_path.exists()
    with h5py.File(first.path, "r") as f:
        np.testing.assert_array_equal(f["streams/ecos/lfp"][...], np.full((1, 6), 1.0))


def test_a_part_swapped_underneath_the_writer_is_not_renamed_into_place(tmp_path, job, cfg):
    """If the inode changed, the .part is someone else's; refuse and leave it alone."""
    with (
        pytest.raises(RuntimeError, match="not the one this writer created"),
        BlockWriter(tmp_path, job, cfg, {}) as w,
    ):
        w.part_path.unlink()
        w.part_path.write_bytes(b"another process's file")
    assert not w.path.exists()
    assert w.part_path.read_bytes() == b"another process's file"


def test_two_blocks_that_sanitize_to_the_same_filename_do_not_overwrite_each_other(tmp_path, cfg):
    first = BlockJob("uh0000", "s", "Block A/3", "tdt_mat", tmp_path)
    second = BlockJob("uh0000", "s", "Block A 3", "tdt_mat", tmp_path)
    with BlockWriter(tmp_path, first, cfg, {}) as w1:
        w1.open_product("ecos", "lfp", "lfp", 1, 8000.0, {}).append(np.ones((1, 3)))
    with (
        pytest.raises(RuntimeError, match="same filename"),
        BlockWriter(tmp_path, second, cfg, {}) as w2,
    ):
        w2.open_product("ecos", "lfp", "lfp", 1, 8000.0, {}).append(np.zeros((1, 3)))
    assert w1.path == w2.path
    assert not w2.part_path.exists()
    with h5py.File(w1.path, "r") as f:
        assert _text(f.attrs["block"]) == "Block A/3"
        np.testing.assert_array_equal(f["streams/ecos/lfp"][...], np.ones((1, 3)))


def test_rebuilding_the_same_block_replaces_the_earlier_file(tmp_path, job, cfg):
    for fill in (1.0, 2.0):
        with BlockWriter(tmp_path, job, cfg, {}) as w:
            w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {}).append(np.full((1, 3), fill))
    with h5py.File(w.path, "r") as f:
        np.testing.assert_array_equal(f["streams/ecos/lfp"][...], np.full((1, 3), 2.0))


# ---- round trip with plain h5py --------------------------------------------------

def test_a_finished_block_reads_back_with_plain_h5py_arrays_exact_and_attrs_present(
    tmp_path, job, cfg
):
    chunks = _chunks()
    filter_attrs = {
        "resample_up": 512,
        "resample_down": 3125,
        "resample_method": "scipy.signal.resample_poly",
        "sfreq_in_hz": 48828.125,
        "usable_bandwidth_hz": 3200.0,
        "meets_spec": True,
        "channel_ids": ["ecog01", "ecog02", "ecog03"],
    }
    provenance = {"reader": "tdt_mat", "n_source_windows": 4}
    with BlockWriter(tmp_path, job, cfg, provenance) as w:
        h = w.open_product("ecos", "lfp", "lfp", 3, 8000.0, filter_attrs)
        for c in chunks:
            h.append(c)
        rec = h.close()
        w.write_epochs(
            "PeA/",
            onsets=np.array([0.5, 1.5]),
            offsets=np.array([0.6, 1.6]),
            values=np.array([1, 2]),
            attrs={"source": "tsq index"},
        )
        w.write_summary(
            "ecos",
            {"rms": np.array([1.0, 2.0, 3.0]), "psd_hz": np.linspace(0, 100, 5)},
            {"aggregate": "median"},
        )

    expected = np.concatenate(chunks, axis=1).astype(np.float32)
    assert rec.n_samples_out == expected.shape[1]

    # From here on: what a MATLAB user or a plain h5py script sees.
    with h5py.File(w.path, "r") as f:
        d = f["streams/ecos/lfp"]
        np.testing.assert_array_equal(d[...], expected)
        assert d.dtype == np.float32
        assert d.maxshape == (3, None)
        assert d.chunks[0] == 3
        assert d.compression == "gzip"
        assert d.shuffle is True

        assert _text(d.attrs["role"]) == "lfp"
        assert _text(d.attrs["name"]) == "lfp"
        assert float(d.attrs["sfreq_out_hz"]) == 8000.0
        assert float(d.attrs["t0_s"]) == 0.0
        assert _text(d.attrs["units"]) == "unknown (TDT Scale: Unity)"
        assert "no re-referencing" in _text(d.attrs["reference"])
        assert [_text(c) for c in d.attrs["channel_ids"]] == ["ecog01", "ecog02", "ecog03"]
        assert int(d.attrs["resample_up"]) == 512
        assert _text(d.attrs["resample_method"]) == "scipy.signal.resample_poly"
        assert int(d.attrs["n_samples"]) == expected.shape[1]
        assert int(d.attrs["n_nonfinite"]) == 0
        assert _text(d.attrs["data_sha256"]) == rec.data_sha256
        assert "MATLAB" in _text(d.attrs["layout"])

        assert int(f.attrs["schema_version"]) == cfg.schema_version
        assert _text(f.attrs["study_id"]) == "uh0000"
        assert _text(f.attrs["source_format"]) == "tdt_mat"
        assert _text(f.attrs["config_sha256"]) == cfg.sha256()
        assert _text(f.attrs["reader"]) == "tdt_mat"
        assert int(f.attrs["n_source_windows"]) == 4
        assert _text(f["streams/ecos"].attrs["name"]) == "ecos"

        e = f["epochs/PeA"]
        assert _text(e.attrs["name"]) == "PeA/"
        np.testing.assert_array_equal(e["onsets"][...], [0.5, 1.5])
        np.testing.assert_array_equal(e["offsets"][...], [0.6, 1.6])
        np.testing.assert_array_equal(e["values"][...], [1.0, 2.0])
        assert e["onsets"].dtype == np.float64
        assert _text(e.attrs["source"]) == "tsq index"
        assert int(e.attrs["n_events"]) == 2

        s = f["summary/ecos"]
        np.testing.assert_array_equal(s["rms"][...], [1.0, 2.0, 3.0])
        assert s["psd_hz"].shape == (5,)
        assert _text(s.attrs["aggregate"]) == "median"


def test_builder_version_is_recorded_when_the_package_is_installed(tmp_path, job, cfg):
    try:
        installed = metadata.version("analyzedbs")
    except metadata.PackageNotFoundError:
        installed = "unknown"
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        pass
    with h5py.File(w.path, "r") as f:
        assert _text(f.attrs["builder_version"]) == installed


def test_string_attributes_are_fixed_length_utf8_so_matlab_reads_them(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {"note": "caf\u00e9"}) as w:
        pass
    with h5py.File(w.path, "r") as f:
        info = h5py.check_string_dtype(f.attrs.get_id("note").dtype)
        assert info is not None
        assert info.encoding == "utf-8"
        assert info.length is not None, "fixed length, not variable"
        assert _text(f.attrs["note"]) == "caf\u00e9"


def test_booleans_are_stored_as_int8_so_matlab_reads_a_number_not_an_enum(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {"flag": True, "flags": [True, False]}) as w:
        w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {"meets_spec": False})
    with h5py.File(w.path, "r") as f:
        assert f.attrs["flag"].dtype == np.int8 and int(f.attrs["flag"]) == 1
        assert f.attrs["flags"].dtype == np.int8
        np.testing.assert_array_equal(f.attrs["flags"], [1, 0])
        assert f["streams/ecos/lfp"].attrs["meets_spec"].dtype == np.int8


def test_the_chunk_length_targets_the_configured_byte_count(tmp_path, job, cfg):
    # 64 bytes / (4 channels * 4 bytes) = 4 samples per chunk.
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        w.open_product("ecos", "lfp", "lfp", 4, 8000.0, {}).append(np.zeros((4, 3)))
    with h5py.File(w.path, "r") as f:
        assert f["streams/ecos/lfp"].chunks == (4, 4)


def test_compression_level_and_dtype_come_from_the_config(tmp_path, job):
    cfg = DeriveConfig.model_validate(
        {
            "store": {
                "dtype": "float64",
                "compression": {"name": "gzip", "level": 6, "shuffle": False},
            },
            "privacy": {"redact_patterns": REDACT},
        }
    )
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        h = w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {})
        h.append(np.array([[0.1, 0.2]]))
        rec = h.close()
    with h5py.File(w.path, "r") as f:
        d = f["streams/ecos/lfp"]
        assert d.dtype == np.float64
        assert d.compression == "gzip"
        assert d.compression_opts == 6
        assert d.shuffle is False
        np.testing.assert_array_equal(d[...], [[0.1, 0.2]])
        assert _text(d.attrs["dtype"]) == "float64"
    expected = np.array([[0.1, 0.2]], dtype=np.float64)
    assert rec.data_sha256 == hashlib.sha256(expected.tobytes(order="C")).hexdigest()


def test_caller_supplied_units_are_honored(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        w.open_product("emgg", "emg", "emg", 1, 2000.0, {"units": "V"})
    with h5py.File(w.path, "r") as f:
        assert _text(f["streams/emgg/emg"].attrs["units"]) == "V"


# ---- the content hash --------------------------------------------------------------

def test_data_sha256_equals_the_c_order_float32_hash_for_a_single_channel(tmp_path, job, cfg):
    chunks = _chunks(n_channels=1, sizes=(9, 4, 6))
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        h = w.open_product("mic_", "mic", "mic", 1, 16000.0, {})
        for c in chunks:
            h.append(c)
        rec = h.close()
    whole = np.concatenate(chunks, axis=1).astype(np.float32)
    assert rec.data_sha256 == hashlib.sha256(whole.tobytes(order="C")).hexdigest()


def test_multichannel_hashes_are_time_major_overall_and_c_order_per_channel(tmp_path, job, cfg):
    """A streaming hash cannot reproduce C order across rows; each row's C-order hash is kept."""
    chunks = _chunks(n_channels=3, sizes=(5, 7, 2))
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        h = w.open_product("ecos", "lfp", "lfp", 3, 8000.0, {})
        for c in chunks:
            h.append(c)
        rec = h.close()
    whole = np.concatenate(chunks, axis=1).astype(np.float32)
    assert rec.data_sha256 == hashlib.sha256(whole.tobytes(order="F")).hexdigest()
    with h5py.File(w.path, "r") as f:
        d = f["streams/ecos/lfp"]
        assert "time-major" in _text(d.attrs["data_sha256_order"])
        per_channel = [_text(x) for x in d.attrs["channel_sha256"]]
        assert per_channel == [
            hashlib.sha256(whole[i].tobytes(order="C")).hexdigest() for i in range(3)
        ]
        # The verifier, streaming the file back in small windows, agrees.
        assert recompute_hashes(d, window=4) == (rec.data_sha256, per_channel)


def test_the_hash_does_not_depend_on_how_the_stream_was_chunked(tmp_path, job, cfg):
    data = np.concatenate(_chunks(n_channels=2, sizes=(6, 6)), axis=1)

    def build(splits: tuple[int, ...], suffix: str) -> str:
        j = BlockJob("uh0000", "s", f"b{suffix}", "tdt_mat", tmp_path)
        with BlockWriter(tmp_path, j, cfg, {}) as w:
            h = w.open_product("ecos", "lfp", "lfp", 2, 8000.0, {})
            for piece in np.split(data, splits, axis=1):
                h.append(piece)
            return h.close().data_sha256

    assert build((4,), "1") == build((1, 5, 9), "2")


def test_samples_that_overflow_the_store_dtype_are_counted_not_hidden(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        h = w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {})
        h.append(np.array([[1e300, 1.0, np.nan]]))
        assert h.n_nonfinite == 2
    with h5py.File(w.path, "r") as f:
        assert int(f["streams/ecos/lfp"].attrs["n_nonfinite"]) == 2


# ---- refusals --------------------------------------------------------------------

def test_a_chunk_with_the_wrong_channel_count_is_refused(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        h = w.open_product("ecos", "lfp", "lfp", 3, 8000.0, {})
        with pytest.raises(ValueError, match="expected \\(3, n_new\\)"):
            h.append(np.zeros((2, 10)))
        with pytest.raises(ValueError):
            h.append(np.zeros(10))


def test_a_closed_handle_refuses_further_appends(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        h = w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {})
        h.close()
        with pytest.raises(RuntimeError, match="already closed"):
            h.append(np.zeros((1, 1)))


def test_channel_ids_must_match_the_channel_count(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w, pytest.raises(ValueError, match="channel_ids"):
        w.open_product("ecos", "lfp", "lfp", 3, 8000.0, {"channel_ids": ["a", "b"]})


def test_t0_is_zero_regardless_of_what_the_caller_passes(tmp_path, job, cfg):
    """A raw TDT start time is a surgery timestamp; it must never reach the file."""
    with BlockWriter(tmp_path, job, cfg, {"t0_s": 0.25}) as w:
        h = w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {"t0_s": 0.25})
        h.append(np.zeros((1, 4)))
        w.write_epochs("Cam1", np.array([0.0]), np.array([]), np.array([]), {"t0_s": 0.25})
    with h5py.File(w.path, "r") as f:
        assert float(f["streams/ecos/lfp"].attrs["t0_s"]) == 0.0
        assert float(f["epochs/Cam1"].attrs["t0_s"]) == 0.0
        assert float(f.attrs["t0_s"]) == 0.0


def test_provenance_cannot_override_the_writers_own_root_attributes(tmp_path, job, cfg):
    forged = {"study_id": "x", "schema_version": 99, "config_sha256": "0" * 64, "t0_s": 0.5}
    with BlockWriter(tmp_path, job, cfg, forged) as w:
        pass
    with h5py.File(w.path, "r") as f:
        assert _text(f.attrs["study_id"]) == "uh0000"
        assert int(f.attrs["schema_version"]) == cfg.schema_version
        assert _text(f.attrs["config_sha256"]) == cfg.sha256()
        assert float(f.attrs["t0_s"]) == 0.0


def test_the_reference_note_cannot_be_overridden(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {"reference": "bipolar", "n_samples": 99})
    with h5py.File(w.path, "r") as f:
        d = f["streams/ecos/lfp"]
        assert "no re-referencing" in _text(d.attrs["reference"])
        assert int(d.attrs["n_samples"]) == 0


@pytest.mark.parametrize(
    "offending",
    [
        "/Box/Some Lab/Archive/thing",
        "Box:/Archive/thing",
        "BOX:/archive",
        "box/archive",
        STEM,
        STEM.upper() + "_increment1_depth1.tsq",
        STEM.replace("-", "_"),
        STEM.replace("-", " "),
        "991231-235959",
        "date_19991231 time_0900",
        "19991231",
        f"recorded {SLASH_DATE} in OR 3",
        ISO_DATE,
        "Dec 31, 1999",
        "31 December 1999",
        "31.12.1999",
        "/home/someone/DBS Data/uh0000",
        "C:\\Users\\someone\\archive",
        "~/DBS Data/staged",
        "file:///home/x/y",
        "smb://server/share",
    ],
)
def test_a_string_value_that_leaks_a_path_stem_or_date_is_refused(tmp_path, job, cfg, offending):
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {"comment": offending})
    assert not w.path.exists()
    assert not w.part_path.exists()


def test_the_shipped_config_refuses_archive_name_shapes_in_any_case_or_separator():
    """Loads configs/derive.yaml itself, so a config regression is caught here."""
    checker = PrivacyChecker(load_config().privacy.redact_patterns)
    for text in (
        STEM.upper() + "_increment1_depth1.tsq",
        STEM.replace("-", "_"),
        "BRAINaim1_date_19991231 time_0900_run1",
        STEM,
    ):
        with pytest.raises(PrivacyRefusal):
            checker.check(text, "test")
    checker.check("increment1_depth1_DNU", "test")
    checker.check("uh0000", "test")


def test_an_empty_redact_list_still_refuses_stems_and_dates_because_the_floor_is_hard_coded():
    checker = PrivacyChecker([])
    for text in (STEM, STEM.upper(), ISO_DATE, SLASH_DATE, "19991231", "date_19991231"):
        with pytest.raises(PrivacyRefusal):
            checker.check(text, "test")


def test_a_numeric_timestamp_under_a_date_like_key_is_refused(tmp_path, job, cfg):
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {"meas_date": 9.0e8}):
        pass
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {"start_time": 19991231}):
        pass
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {"timestamps": [1.0, 9e8]}):
        pass
    # Small numbers under such keys are durations and pass; other keys are unconstrained.
    with BlockWriter(tmp_path, job, cfg, {"build_time_s": 42.5, "n_samples_in": 9e8}) as w:
        pass
    assert w.path.exists()


def test_an_attribute_key_is_checked_as_strictly_as_a_value(tmp_path, job, cfg):
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {STEM: 1})


def test_provenance_and_the_job_itself_are_checked_before_anything_is_written(tmp_path, cfg):
    bad_job = BlockJob("uh0000", STEM, "b", "tdt_tank", tmp_path)
    with pytest.raises(PrivacyRefusal):
        BlockWriter(tmp_path, bad_job, cfg, {})
    good_job = BlockJob("uh0000", "s", "b", "tdt_tank", tmp_path)
    with pytest.raises(PrivacyRefusal):
        BlockWriter(tmp_path, good_job, cfg, {"source": "/Box/Archive/x"})
    assert not any(tmp_path.rglob("*.h5*"))


def test_channel_ids_and_epoch_names_and_string_values_are_checked_too(tmp_path, job, cfg):
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {"channel_ids": [ISO_DATE]})
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.write_epochs("/Box/x", np.array([0.0]), np.array([]), np.array([]), {})
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.write_epochs("Note", np.array([0.0]), np.array([]), np.array([SLASH_DATE]), {})


def test_summary_attrs_array_names_and_string_arrays_are_checked(tmp_path, job, cfg):
    ok = {"rms": np.array([1.0])}
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.write_summary("ecos", ok, {"tank": STEM})
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.write_summary("ecos", {STEM: np.array([1.0])}, {})
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.write_summary("ecos", {"labels": np.array(["a", ISO_DATE])}, {})
    with pytest.raises(PrivacyRefusal), BlockWriter(tmp_path, job, cfg, {}) as w:
        w.write_summary("/Box/ecos", ok, {})
    assert not any(tmp_path.rglob("*.h5*"))


def test_ordinary_attribute_text_is_not_mistaken_for_a_path_or_a_date(tmp_path, job, cfg):
    """Rate strings, method names, unit notes and digests carry slashes and digits legitimately."""
    attrs = {
        "sfreq_in_exact": "390625/8",
        "resample_method": "scipy.signal.resample_poly",
        "filter_design": "kaiser(beta=8.6) firwin, cutoff 3600.000 Hz; decimate 4 2000",
        "units": "unknown (TDT Scale: Unity)",
        "filter_coeff_sha256": hashlib.sha256(b"x").hexdigest(),
        "n_samples_str": "20000000",
        "block_note": "increment1_depth1_DNU sept 2",
    }
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        w.open_product("ecos", "lfp", "lfp", 1, 8000.0, attrs).append(np.zeros((1, 2)))
    assert w.path.exists()


# ---- epochs and summaries: shape rules -------------------------------------------

def test_two_dimensional_epoch_arrays_are_refused_rather_than_flattened(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        with pytest.raises(ValueError, match="1-D"):
            w.write_epochs("x", np.array([[1.0, 2.0], [3.0, 4.0]]), np.array([]), np.array([]), {})
        with pytest.raises(ValueError, match="offsets"):
            w.write_epochs("x", np.array([1.0, 2.0]), np.array([1.0]), np.array([]), {})


def test_an_epoch_name_with_a_slash_does_not_create_a_nested_group(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        w.write_epochs("a/b", np.array([1.0]), np.array([]), np.array([]), {})
        w.write_epochs("a", np.array([2.0]), np.array([]), np.array([]), {})
        with pytest.raises(ValueError, match="already exists"):
            w.write_epochs("a/", np.array([3.0]), np.array([]), np.array([]), {})
    assert w.epochs_written == ["a/b", "a"]
    with h5py.File(w.path, "r") as f:
        assert sorted(f["epochs"]) == ["a", "a_b"]
        assert _text(f["epochs/a_b"].attrs["name"]) == "a/b"


# ---- the record ----------------------------------------------------------------------

def test_unclosed_handles_are_finalized_on_exit_and_recorded(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        h = w.open_product("ecos", "lfp", "lfp", 2, 8000.0, {"sfreq_in_hz": 48828.125})
        h.append(np.ones((2, 3)))
    assert len(w.records) == 1
    rec = w.records[0]
    assert rec.n_samples_out == 3
    assert rec.sfreq_in_hz == 48828.125
    assert rec.filter_attrs["sfreq_in_hz"] == 48828.125
    with h5py.File(w.path, "r") as f:
        assert int(f["streams/ecos/lfp"].attrs["n_samples"]) == 3


def test_the_record_is_json_serializable_even_with_numpy_attrs(tmp_path, job, cfg):
    attrs = {
        "filter_ntaps": np.int64(101),
        "alias_floor_db": np.float32(-91.5),
        "edges": np.arange(3),
    }
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        rec = w.open_product("ecos", "lfp", "lfp", 1, 8000.0, attrs).close()
    blob = json.dumps(dataclasses.asdict(rec))
    assert json.loads(blob)["filter_attrs"]["filter_ntaps"] == 101
    assert json.loads(blob)["filter_attrs"]["edges"] == [0, 1, 2]


def test_an_explicit_filter_attrs_keyword_is_what_the_record_carries(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        rec = w.open_product(
            "ecos", "lfp", "lfp", 1, 8000.0, {"stat": 1.0}, filter_attrs={"resample_up": 512}
        ).close()
    assert rec.filter_attrs == {"resample_up": 512}


def test_writing_the_same_product_twice_is_an_error(tmp_path, job, cfg):
    with BlockWriter(tmp_path, job, cfg, {}) as w:
        w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {}).close()
        with pytest.raises(ValueError, match="already exists"):
            w.open_product("ecos", "lfp", "lfp", 1, 8000.0, {})
