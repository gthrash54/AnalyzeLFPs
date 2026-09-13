"""The QC report. Model and renderer are separate so a second renderer cannot drift."""

from __future__ import annotations

import numpy as np
import pytest

from dbsspeech.qc import Flag, build_model, render_html
from dbsspeech.qc.report import ReportModel

pytestmark = pytest.mark.unit

SFREQ = 500.0


@pytest.fixture
def scene():
    rng = np.random.default_rng(0)
    data = rng.standard_normal((6, int(SFREQ * 20))) * 1e-5
    names = [f"c{i+1}" for i in range(6)]
    regions = ["stn"] * 3 + ["gpi"] * 3
    return data, names, regions


def _model(scene, flags=None, windows=None) -> ReportModel:
    data, names, regions = scene
    return build_model("S01", "ses1", data, SFREQ, names, regions,
                       flags or [], windows)


def test_overview_describes_the_recording(scene):
    model = _model(scene)
    assert model.overview["channels"] == 6
    assert model.overview["channels_by_region"] == {"stn": 3, "gpi": 3}
    assert model.overview["duration_s"] == pytest.approx(20.0)


def test_a_spectra_figure_is_always_produced(scene):
    assert _model(scene).figures[0].title == "Spectra by region"


def test_window_flags_get_a_snippet_with_the_window_shaded(scene):
    flag = Flag("window", "c1@4.00s", "amplitude_window",
                {"channel": "c1", "t_start_s": 4.0, "t_end_s": 5.0, "ratio": 12.0},
                "annotate_window", "med")
    titles = [f.title for f in _model(scene, [flag]).figures]
    assert any("c1 at 4.0s" in t for t in titles)


def test_snippets_are_capped_so_the_report_stays_small(scene):
    flags = [
        Flag("window", f"c1@{i}", "amplitude_window",
             {"channel": "c1", "t_start_s": float(i), "t_end_s": float(i) + 0.5, "ratio": 9},
             "annotate_window", "med")
        for i in range(15)
    ]
    # One spectra figure plus at most six snippets.
    assert len(_model(scene, flags).figures) <= 7


def test_flags_are_ordered_by_severity(scene):
    flags = [
        Flag("channel", "c2", "line_noise", {}, "notch", "low"),
        Flag("channel", "c1", "flat_channel", {}, "exclude_channel", "high"),
        Flag("channel", "c3", "variance_outlier", {}, "exclude_channel", "med"),
    ]
    assert [f.severity for f in _model(scene, flags).flags_by_severity()] == ["high", "med", "low"]


def test_counts_summarize_by_type(scene):
    flags = [Flag("channel", f"c{i}", "line_noise", {}, "notch", "low") for i in range(4)]
    flags.append(Flag("channel", "c5", "flat_channel", {}, "exclude_channel", "high"))
    assert _model(scene, flags).counts() == {"line_noise": 4, "flat_channel": 1}


def test_insufficient_channels_produces_an_explanatory_note(scene):
    flag = Flag("channel", "group:stn/ring", "insufficient_channels",
                {"n_channels_in_group": 2, "minimum_required": 4}, "", "low")
    notes = _model(scene, [flag]).notes
    assert any("human look" in n for n in notes)


def test_a_window_under_revision_is_noted(scene):
    windows = [{"condition": "rest", "status": "under_revision"}]
    assert any("under_revision" in n for n in _model(scene, [], windows).notes)


# ---- rendering ---------------------------------------------------------------

def test_html_is_self_contained(scene, tmp_path):
    """It must open anywhere, including from an email attachment."""
    path = render_html(_model(scene), tmp_path / "report.html")
    text = path.read_text()
    assert "data:image/png;base64," in text
    assert "<img" in text
    assert "src='http" not in text and 'src="http' not in text


def test_html_names_the_subject_by_study_id_only(scene, tmp_path):
    text = render_html(_model(scene), tmp_path / "r.html").read_text()
    assert "S01" in text


def test_html_carries_no_filesystem_paths(scene, tmp_path):
    """A report leaves the machine; a path can name a subject or a date."""
    text = render_html(_model(scene), tmp_path / "r.html").read_text()
    for fragment in ("/Users/", "/Volumes/", ".mat", ".tsq", "Box-Box"):
        assert fragment not in text, fragment


def test_html_shows_evidence_and_the_proposed_action(scene, tmp_path):
    flag = Flag("channel", "c1", "flat_channel", {"std": 1.5e-9},
                "exclude_channel", "high")
    text = render_html(_model(scene, [flag]), tmp_path / "r.html").read_text()
    assert "flat_channel" in text
    assert "exclude_channel" in text
    assert "1.5e-09" in text


def test_html_escapes_content(scene, tmp_path):
    """Evidence is data, not markup."""
    flag = Flag("channel", "<script>alert(1)</script>", "flat_channel", {},
                "exclude_channel", "high")
    text = render_html(_model(scene, [flag]), tmp_path / "r.html").read_text()
    assert "<script>alert(1)</script>" not in text
    assert "&lt;script&gt;" in text


def test_a_report_with_no_flags_says_so(scene, tmp_path):
    assert "No flags." in render_html(_model(scene), tmp_path / "r.html").read_text()


def test_report_stays_small(scene, tmp_path):
    """A few megabytes at most; a reviewer has to be able to open it."""
    flags = [
        Flag("window", f"c1@{i}", "amplitude_window",
             {"channel": "c1", "t_start_s": float(i), "t_end_s": float(i) + 0.5, "ratio": 9},
             "annotate_window", "med")
        for i in range(6)
    ]
    path = render_html(_model(scene, flags), tmp_path / "r.html")
    assert path.stat().st_size < 3_000_000, path.stat().st_size
