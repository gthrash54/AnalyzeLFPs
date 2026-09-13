"""tfr_onset: does it find a planted event at the right time and frequency."""

from __future__ import annotations

import csv
import json

import h5py
import numpy as np
import pytest

from dbsspeech.recipes import get, run
from dbsspeech.recipes.tfr import TfrParams, _apply_baseline, _frequencies, _pad_seconds

pytestmark = pytest.mark.unit

SID, SES = "S01", "ses1"
CONTACTS = ["1", "2a", "2b", "2c", "3a", "3b", "3c", "4"]
SFREQ = 1000.0
BURST_HZ = 20.0
BURST_START = 4.0      # seconds into the recording
BURST_LEN = 2.0
ONSET = 3.0            # condition window starts here, so the burst is at t = +1


def _write_fixture(path):
    """A recording with a beta burst at a known time, on known contacts."""
    rng = np.random.default_rng(0)
    n = int(SFREQ * 12)
    t = np.arange(n) / SFREQ
    data = rng.standard_normal((8, n)).astype(np.float32) * 1e-5

    burst = (t >= BURST_START) & (t < BURST_START + BURST_LEN)
    envelope = np.zeros(n, dtype=np.float32)
    envelope[burst] = 1.0
    for ch in (0, 1, 2, 3):
        data[ch] += (6e-5 * envelope * np.sin(2 * np.pi * BURST_HZ * t)).astype(np.float32)

    path.parent.mkdir(parents=True, exist_ok=True)
    with h5py.File(path, "w") as f:
        g = f.create_group("importdata/streams/neur")
        g.create_dataset("data", data=data.T, chunks=(256, 8), compression="gzip")
        g.create_dataset("fs", data=np.array([[SFREQ]], dtype=np.float64))
        g.create_dataset("startTime", data=np.array([[0.0]], dtype=np.float64))
        g.create_dataset("channel", data=np.arange(1, 9, dtype=np.uint16).reshape(-1, 1))
        codes = np.array([ord(c) for c in "neur"], dtype=np.uint16).reshape(-1, 1)
        g.create_dataset("name", data=codes)


@pytest.fixture(scope="module")
def project(tmp_path_factory):
    base = tmp_path_factory.mktemp("tfr")
    _write_fixture(base / "data" / "block" / "block.mat")
    m = base / "manifest"
    m.mkdir()

    def write(name, header, rows):
        with (m / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write("subjects.csv",
          ["study_id", "session", "hemisphere", "format", "root_relpath",
           "acquisition", "acquisition_date", "notes"],
          [[SID, SES, "R", "tdt_mat", "block", "acq", "", ""]])
    write("streams.csv",
          ["study_id", "session", "stream", "n_channels", "sfreq_hz", "units",
           "role", "relpath", "notes"],
          [[SID, SES, "neur", "8", str(SFREQ), "V", "neural", "", ""]])
    write("leads.csv",
          ["study_id", "session", "lead_id", "target", "hemisphere", "lead_model",
           "channel_first", "channel_last", "rotation_deg", "notes"],
          [[SID, SES, "lead1", "stn", "R", "unknown_directional_1331", "1", "8", "0", ""]])
    write("channels.csv",
          ["study_id", "session", "stream", "ch_index", "ch_name", "region",
           "lead_id", "lead_contact", "site", "include", "exclude_reason"],
          [[SID, SES, "neur", str(i + 1), f"c{i+1}", "stn", "lead1", cid, "", "true", ""]
           for i, cid in enumerate(CONTACTS)])
    write("windows.csv",
          ["study_id", "session", "condition", "t_start_s", "t_end_s",
           "derived_from", "status", "notes"],
          [[SID, SES, "overt", str(ONSET), "9.0", "microphone", "in_use", ""]])
    return base


def _approve(tmp_path):
    from dbsspeech.qc import propose, sign

    propose([], SID, tmp_path / "derivatives")
    sign(SID, "test-reviewer", tmp_path / "derivatives")


def _run(project, tmp_path, **params):
    _approve(tmp_path)
    return run(
        "tfr_onset", SID, SES, claim="test run",
        params={"tmin": -2.0, "tmax": 5.0, "fmin": 8.0, "fmax": 60.0, "n_freqs": 16,
                "sfreq_target_hz": SFREQ, "decim": 4,
                "primary_reference": "monopolar", "references": ["monopolar"],
                **params},
        overrides={"G1_shared_reference_common_mode": "synthetic fixture"},
        manifest_dir=project / "manifest", data_dir=project / "data",
        runs_dir=tmp_path / "runs", derivatives_dir=tmp_path / "derivatives",
    )


def _record(tmp_path, rid):
    return json.loads((tmp_path / "runs" / f"{rid}.json").read_text())


# ---- pieces in isolation -----------------------------------------------------

def test_frequencies_are_log_spaced():
    freqs = _frequencies(TfrParams(fmin=2.0, fmax=200.0, n_freqs=10))
    ratios = freqs[1:] / freqs[:-1]
    np.testing.assert_allclose(ratios, ratios[0], rtol=1e-6)


def test_padding_covers_the_longest_wavelet():
    """A wavelet needs signal either side of the point it reports.

    Five sigma of the widest envelope, which is what MNE builds. Asserted 0.25 s
    until 2026-09-09, which was half the nominal wavelet duration and 37 percent
    short of the kernel actually convolved.
    """
    freqs = np.array([2.0, 50.0])
    n_cycles = freqs * 0.5
    # sigma_t is constant here: n_cycles / f is 0.5 s at both frequencies.
    expected = 5.0 * 0.5 / (2.0 * np.pi)
    assert _pad_seconds(freqs, n_cycles) == pytest.approx(expected)
    assert _pad_seconds(freqs, n_cycles) > 0.25


def test_logratio_baseline_is_zero_where_nothing_changes():
    power = np.ones((4, 100))
    times = np.linspace(-2, 5, 100)
    out = _apply_baseline(power, times, TfrParams(baseline_mode="logratio"))
    np.testing.assert_allclose(out, 0.0, atol=1e-9)


def test_zscore_baseline_uses_unsmoothed_variability():
    rng = np.random.default_rng(0)
    power = rng.standard_normal((3, 400)) + 10
    times = np.linspace(-2, 5, 400)
    out = _apply_baseline(power, times, TfrParams(baseline_mode="zscore"))
    baseline = out[:, (times >= -2) & (times <= -0.25)]
    assert abs(float(baseline.mean())) < 0.3


def test_baseline_none_leaves_power_untouched():
    power = np.arange(20, dtype=float).reshape(2, 10)
    times = np.linspace(-2, 5, 10)
    np.testing.assert_array_equal(
        _apply_baseline(power, times, TfrParams(baseline_mode="none")), power
    )


# ---- the recipe --------------------------------------------------------------

def test_registered_with_sensible_defaults():
    assert get("tfr_onset").version == "1"
    p = TfrParams()
    assert p.method == "morlet"
    assert p.baseline_mode == "logratio"
    assert p.tmin < 0, "a baseline needs time before onset"


def test_a_run_produces_maps_and_a_figure(project, tmp_path):
    rid = _run(project, tmp_path)
    outputs = _record(tmp_path, rid)["outputs"]
    assert "tfr_long.parquet" in outputs
    assert "tfr_onset.png" in outputs
    assert "window_provenance.csv" in outputs
    assert any(o.startswith("tfr.") for o in outputs), outputs


def test_the_planted_burst_is_found_at_the_right_time_and_frequency(project, tmp_path):
    """The burst runs from t=+1 to t=+3 after onset, at 20 Hz."""
    rid = _run(project, tmp_path)
    peak = _record(tmp_path, rid)["summary"]["peaks"][0]
    assert peak["peak_freq_hz"] == pytest.approx(BURST_HZ, rel=0.35), peak
    assert 0.5 < peak["peak_time_s"] < 3.5, peak


def test_the_map_spans_exactly_what_was_asked_for(project, tmp_path):
    """Padding is cropped away, so the reported range is the requested range.

    This used to be called test_no_reported_point_sits_on_an_edge, which is a
    claim about padding, not about the range. The range test is still worth
    having; the claim in the old name is tested below, against MNE.
    """
    rid = _run(project, tmp_path)
    summary = _record(tmp_path, rid)["summary"]
    assert summary["time_range_s"][0] >= -2.0
    assert summary["time_range_s"][1] <= 5.0


def test_no_reported_point_sits_on_an_edge():
    """The pad covers the kernel MNE actually convolves, at every frequency.

    Asserted against MNE rather than against a stored number: MNE builds a
    Morlet out to five sigma either side, not to one nominal cycle, so the old
    pad of half the nominal duration was 37 percent short at the defaults and
    the guarantee in the module docstring was false.
    """
    try:
        from mne.time_frequency import morlet
    except ImportError:                                  # pragma: no cover
        from mne.time_frequency.tfr import morlet

    from dbsspeech.recipes.tfr import _frequencies, _n_cycles, _pad_seconds

    sfreq = 1000.0
    for factor in (0.25, 0.5, 1.0, 3.0):
        params = TfrParams(n_cycles_factor=factor)
        freqs = _frequencies(params)
        n_cycles = _n_cycles(params, freqs)
        pad = _pad_seconds(freqs, n_cycles, sfreq)
        for f, nc in zip(freqs, n_cycles, strict=True):
            kernel = morlet(sfreq, [float(f)], n_cycles=float(nc))[0]
            half_support_s = len(kernel) / sfreq / 2.0
            assert pad >= half_support_s - 1e-9, (
                f"factor={factor} f={f:.2f}Hz needs {half_support_s:.4f}s "
                f"either side, pad is {pad:.4f}s"
            )


def test_the_old_pad_would_have_failed_that():
    """Guard the guard. The previous rule was half the nominal duration."""
    try:
        from mne.time_frequency import morlet
    except ImportError:                                  # pragma: no cover
        from mne.time_frequency.tfr import morlet

    from dbsspeech.recipes.tfr import _frequencies

    params = TfrParams()
    freqs = _frequencies(params)
    n_cycles = freqs * params.n_cycles_factor
    old_pad = float(np.max(n_cycles / freqs) / 2.0)
    worst = max(
        len(morlet(1000.0, [float(f)], n_cycles=float(nc))[0]) / 1000.0 / 2.0
        for f, nc in zip(freqs, n_cycles, strict=True)
    )
    assert old_pad < worst, "MNE's kernel no longer exceeds the old pad; revisit B2"


def test_window_provenance_travels_with_the_result(project, tmp_path):
    import pandas as pd

    rid = _run(project, tmp_path)
    prov = pd.read_csv(tmp_path / "derivatives" / "results" / rid / "window_provenance.csv")
    assert prov["derived_from"].iloc[0] == "microphone"
    assert prov["onset_s"].iloc[0] == pytest.approx(ONSET)


def test_summary_says_what_onset_means(project, tmp_path):
    """An onset is a window start, and the reader has to know whether that
    window was measured or asserted.

    This used to assert the words "no task markers", which was true of every
    recording in the project when it was written and stopped being true when
    `dbsspeech windows` learned to read them. A test that pins the wording of a
    claim goes green while the claim goes false.
    """
    note = _record(tmp_path, _run(project, tmp_path))["summary"]["onset_note"]
    assert "manifest/windows.csv" in note
    assert "window_provenance.csv" in note
    assert "task_marker" in note


def test_multitaper_runs_too(project, tmp_path):
    rid = _run(project, tmp_path, method="multitaper", n_freqs=8)
    assert _record(tmp_path, rid)["summary"]["method"] == "multitaper"


def test_a_band_above_the_cutoff_is_refused(project, tmp_path):
    from dbsspeech.guardrails import GuardrailBlocked

    with pytest.raises(GuardrailBlocked, match="usable bandwidth"):
        _run(project, tmp_path, fmax=900.0, sfreq_target_hz=1000.0)


@pytest.fixture(scope="module")
def project_repeats(tmp_path_factory):
    """The same recording with two windows for one condition.

    The shape of a repeated-trial paradigm, and the shape no fixture had. Every
    existing fixture and the real manifest carry one window per condition, which
    is why a bug that only appears on the second window survived: the map was
    keyed by condition, so the second overwrote the first while provenance went
    on recording both.

    Windows do not overlap, because the manifest validator rejects overlapping
    windows of one condition, and both sit far enough inside the 12 s recording
    to supply the full requested range either side of onset.
    """
    base = tmp_path_factory.mktemp("tfr_repeats")
    _write_fixture(base / "data" / "block" / "block.mat")
    m = base / "manifest"
    m.mkdir()

    def write(name, header, rows):
        with (m / name).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write("subjects.csv",
          ["study_id", "session", "hemisphere", "format", "root_relpath",
           "acquisition", "acquisition_date", "notes"],
          [[SID, SES, "R", "tdt_mat", "block", "acq", "", ""]])
    write("streams.csv",
          ["study_id", "session", "stream", "n_channels", "sfreq_hz", "units",
           "role", "relpath", "notes"],
          [[SID, SES, "neur", "8", str(SFREQ), "V", "neural", "", ""]])
    write("leads.csv",
          ["study_id", "session", "lead_id", "target", "hemisphere", "lead_model",
           "channel_first", "channel_last", "rotation_deg", "notes"],
          [[SID, SES, "lead1", "stn", "R", "unknown_directional_1331", "1", "8", "0", ""]])
    write("channels.csv",
          ["study_id", "session", "stream", "ch_index", "ch_name", "region",
           "lead_id", "lead_contact", "site", "include", "exclude_reason"],
          [[SID, SES, "neur", str(i + 1), f"c{i+1}", "stn", "lead1", cid, "", "true", ""]
           for i, cid in enumerate(CONTACTS)])
    write("windows.csv",
          ["study_id", "session", "condition", "t_start_s", "t_end_s",
           "derived_from", "status", "notes"],
          [[SID, SES, "overt", "3.0", "5.5", "microphone", "in_use", ""],
           [SID, SES, "overt", "6.0", "8.0", "microphone", "in_use", ""]])
    return base


def test_a_repeated_condition_produces_one_map_per_window(project_repeats, tmp_path):
    """B1. The map key omitted the window, so the second overwrote the first."""
    import pandas as pd

    rid = _run(project_repeats, tmp_path)
    rec = _record(tmp_path, rid)
    assert rec["status"] == "ok"
    assert rec["summary"]["n_windows_per_condition"] == {"overt": 2}
    # One lead, one montage, two windows.
    assert rec["summary"]["n_maps"] == 2

    out = tmp_path / "derivatives" / "results" / rid
    long = pd.read_parquet(out / "tfr_long.parquet")
    assert sorted(long["onset_s"].unique().tolist()) == [3.0, 6.0]


def test_provenance_rows_match_the_maps_they_describe(project_repeats, tmp_path):
    """The failure this makes impossible: window_provenance.csv claiming two
    windows contributed to a map that came from one of them."""
    import pandas as pd

    rid = _run(project_repeats, tmp_path)
    out = tmp_path / "derivatives" / "results" / rid
    prov = pd.read_csv(out / "window_provenance.csv")
    long = pd.read_parquet(out / "tfr_long.parquet")

    assert len(prov) == _record(tmp_path, rid)["summary"]["n_maps"]
    assert sorted(prov["onset_s"].unique().tolist()) == sorted(
        long["onset_s"].unique().tolist()
    )


def test_each_repeat_is_baselined_to_its_own_pre_onset_period(project_repeats, tmp_path):
    """Kept separate, not averaged: the two maps must differ, because they are
    two different stretches of a noisy recording."""
    import numpy as np
    import xarray as xr

    rid = _run(project_repeats, tmp_path)
    out = tmp_path / "derivatives" / "results" / rid
    array = xr.open_dataarray(out / "tfr.nc")
    assert array.sizes["map"] == 2
    a, b = array.values[0], array.values[1]
    assert not np.allclose(np.nan_to_num(a), np.nan_to_num(b))


def _project_with_windows(tmp_path_factory, name, window_rows):
    """The standard fixture with whatever windows a test needs."""
    base = tmp_path_factory.mktemp(name)
    _write_fixture(base / "data" / "block" / "block.mat")
    m = base / "manifest"
    m.mkdir()

    def write(fname, header, rows):
        with (m / fname).open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(header)
            w.writerows(rows)

    write("subjects.csv",
          ["study_id", "session", "hemisphere", "format", "root_relpath",
           "acquisition", "acquisition_date", "notes"],
          [[SID, SES, "R", "tdt_mat", "block", "acq", "", ""]])
    write("streams.csv",
          ["study_id", "session", "stream", "n_channels", "sfreq_hz", "units",
           "role", "relpath", "notes"],
          [[SID, SES, "neur", "8", str(SFREQ), "V", "neural", "", ""]])
    write("leads.csv",
          ["study_id", "session", "lead_id", "target", "hemisphere", "lead_model",
           "channel_first", "channel_last", "rotation_deg", "notes"],
          [[SID, SES, "lead1", "stn", "R", "unknown_directional_1331", "1", "8", "0", ""]])
    write("channels.csv",
          ["study_id", "session", "stream", "ch_index", "ch_name", "region",
           "lead_id", "lead_contact", "site", "include", "exclude_reason"],
          [[SID, SES, "neur", str(i + 1), f"c{i+1}", "stn", "lead1", cid, "", "true", ""]
           for i, cid in enumerate(CONTACTS)])
    write("windows.csv",
          ["study_id", "session", "condition", "t_start_s", "t_end_s",
           "derived_from", "status", "notes"],
          window_rows)
    return base


def test_a_window_too_near_the_start_is_skipped_not_shortened(tmp_path_factory, tmp_path):
    """B3. tmin is -2.0, so an onset at 0.5 s cannot supply the pre-onset period.

    Shortening it instead would produce a map covering a different time range
    from every other map, which cannot be stacked into the netCDF and, where two
    happened to crop to equal lengths, would carry a time axis wrong by the
    offset with no exception raised.
    """
    project = _project_with_windows(
        tmp_path_factory, "tfr_early",
        [[SID, SES, "overt", "0.5", "2.5", "microphone", "in_use", ""],
         [SID, SES, "metro", "3.0", "5.0", "microphone", "in_use", ""]],
    )
    rid = _run(project, tmp_path)
    rec = _record(tmp_path, rid)
    assert rec["status"] == "ok"
    # The early window contributed nothing; the viable one still did.
    assert rec["summary"]["n_windows_per_condition"] == {"metro": 1}


def test_a_window_running_past_the_end_is_skipped(tmp_path_factory, tmp_path):
    """The same at the other end. The recording is 12 s and tmax is +5.0."""
    project = _project_with_windows(
        tmp_path_factory, "tfr_late",
        [[SID, SES, "overt", "3.0", "5.0", "microphone", "in_use", ""],
         [SID, SES, "metro", "9.5", "11.0", "microphone", "in_use", ""]],
    )
    rid = _run(project, tmp_path)
    rec = _record(tmp_path, rid)
    assert rec["status"] == "ok"
    assert rec["summary"]["n_windows_per_condition"] == {"overt": 1}


def test_every_surviving_map_shares_one_time_axis(tmp_path_factory, tmp_path):
    """What the two skips buy: the netCDF stack cannot raise, because every map
    spans exactly the requested range."""
    import xarray as xr

    project = _project_with_windows(
        tmp_path_factory, "tfr_axis",
        [[SID, SES, "overt", "3.0", "5.0", "microphone", "in_use", ""],
         [SID, SES, "metro", "6.0", "8.0", "microphone", "in_use", ""]],
    )
    rid = _run(project, tmp_path)
    out = tmp_path / "derivatives" / "results" / rid
    array = xr.open_dataarray(out / "tfr.nc")
    assert array.sizes["map"] == 2
    assert float(array.time.min()) >= -2.0
    assert float(array.time.max()) <= 5.0


# ---- B4. an empty baseline is never silently raw power -----------------------

def test_a_baseline_outside_the_epoch_is_refused_at_parameter_time():
    """It used to return raw power, which the caller then labelled dB and drew
    on a colour scale shared with maps that really were dB."""
    with pytest.raises(ValueError, match="outside the epoch"):
        TfrParams(tmin=0.0, tmax=5.0, baseline_tmin=-2.0, baseline_tmax=-0.25)


def test_a_backwards_baseline_is_refused():
    with pytest.raises(ValueError, match="must be after"):
        TfrParams(baseline_tmin=-0.25, baseline_tmax=-2.0)


def test_baseline_mode_none_does_not_need_a_baseline():
    """Nothing is expressed relative to anything, so there is nothing to check."""
    params = TfrParams(tmin=0.0, tmax=5.0, baseline_mode="none")
    assert params.baseline_mode == "none"


def test_an_empty_mask_raises_rather_than_returning_power():
    """The backstop, reached by handing _apply_baseline times the params say
    should not exist."""
    power = np.ones((4, 50))
    times = np.linspace(1.0, 5.0, 50)          # entirely after the baseline
    params = TfrParams(tmin=-2.0, tmax=5.0,
                       baseline_tmin=-2.0, baseline_tmax=-0.25)
    with pytest.raises(RuntimeError, match="selected no samples"):
        _apply_baseline(power, times, params)


# ---- B2, second half. the low end is real rather than nominal ----------------

def test_the_cycle_floor_binds_at_the_bottom_of_the_default_grid():
    """n_cycles = 0.5 * f gives 1.0 cycle at 2 Hz, which is an envelope detector
    and not a frequency estimate. The floor makes delta and theta mean what the
    axis says they mean."""
    from dbsspeech.recipes.tfr import _frequencies, _n_cycles

    params = TfrParams()
    freqs = _frequencies(params)
    nc = _n_cycles(params, freqs)

    assert nc.min() >= params.min_cycles
    assert nc[0] == pytest.approx(3.0)          # 2 Hz, was 1.0
    # And it stops binding once the factor exceeds it.
    binds_below = params.min_cycles / params.n_cycles_factor
    assert np.all(nc[freqs > binds_below] > params.min_cycles - 1e-9)
    assert np.allclose(nc[freqs < binds_below], params.min_cycles)


def test_the_floor_costs_time_resolution_and_the_summary_says_so(project, tmp_path):
    """The cost is real and inherent, so it is reported per frequency rather
    than left for a reader to infer from a smear near onset."""
    rid = _run(project, tmp_path)
    summary = _record(tmp_path, rid)["summary"]

    res = summary["time_resolution_s"]
    assert res, "no per-frequency time resolution reported"
    lowest = min(float(k) for k in res)
    highest = max(float(k) for k in res)
    # Never better at the bottom. This fixture runs fmin=8 Hz, above the 6 Hz
    # knee, so the floor does not bind and the durations are legitimately
    # constant; the strictly-worse case is asserted directly below.
    assert res[f"{lowest:.2f}"] >= res[f"{highest:.2f}"]
    assert summary["longest_resolvable_event_s"] >= summary[
        "shortest_resolvable_event_s"
    ]
    assert summary["min_cycles_binds_below_hz"] == pytest.approx(
        TfrParams().min_cycles / TfrParams().n_cycles_factor
    )


def test_below_the_knee_the_map_is_slower_and_the_numbers_show_it():
    """Where the floor binds, the wavelet lengthens and time resolution drops.
    Checked on the parameters rather than through a run, so it does not depend
    on a fixture whose fmin happens to sit above the knee."""
    from dbsspeech.recipes.tfr import _frequencies, _n_cycles

    params = TfrParams(fmin=2.0, fmax=150.0, n_freqs=40)
    freqs = _frequencies(params)
    durations = _n_cycles(params, freqs) / freqs
    assert durations[0] > durations[-1]
    assert durations[0] == pytest.approx(params.min_cycles / 2.0)   # 1.5 s at 2 Hz
    assert durations[-1] == pytest.approx(params.n_cycles_factor)   # 0.5 s above


def test_the_floor_can_be_turned_off_for_a_deliberate_constant_duration_tiling():
    """Constant-duration tiling is a legitimate choice; it just should not be the
    silent default at 1.0 cycle."""
    from dbsspeech.recipes.tfr import _frequencies, _n_cycles

    params = TfrParams(min_cycles=1.0)
    freqs = _frequencies(params)
    nc = _n_cycles(params, freqs)
    durations = nc / freqs
    assert np.allclose(durations, durations[0]), "should be constant duration"
