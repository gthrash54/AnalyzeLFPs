"""The QC report: what a reviewer actually looks at.

Structured as a model and a renderer, deliberately. `build_model` decides what
goes in the report; `render_html` decides how it looks. A second renderer, MNE's
Report for people who want the familiar format, reads the same model, so the two
cannot drift on content. Anything that belongs in every report goes in the model,
never in a renderer.

The HTML is self-contained: figures are embedded, so it opens anywhere, survives
being emailed, and needs nothing installed at review time.

No identifiers. The subject is named by study ID and nothing else, and the model
carries no path from the recording it describes.
"""

from __future__ import annotations

import base64
import html
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from .decisions import qc_dir
from .flags import Flag

_SEVERITY_ORDER = {"high": 0, "med": 1, "low": 2}


@dataclass
class Figure:
    title: str
    png: bytes
    caption: str = ""

    def data_uri(self) -> str:
        return "data:image/png;base64," + base64.b64encode(self.png).decode()


@dataclass
class ReportModel:
    """Everything a report shows, independent of how it is rendered."""

    study_id: str
    session: str
    generated_at: str
    overview: dict[str, Any] = field(default_factory=dict)
    figures: list[Figure] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def flags_by_severity(self) -> list[Flag]:
        return sorted(
            self.flags,
            key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9), f.flag_type, f.target),
        )

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for flag in self.flags:
            out[flag.flag_type] = out.get(flag.flag_type, 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def _fig_to_png(fig) -> bytes:
    buffer = io.BytesIO()
    fig.savefig(buffer, format="png", dpi=110, bbox_inches="tight")
    return buffer.getvalue()


def _psd_grid(data, sfreq, names, regions, mains_hz: float) -> Figure:
    """One panel per region, one line per contact. Where a reviewer looks first."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    order: list[str] = []
    for region in regions:
        if region not in order:
            order.append(region)

    fig, axes = plt.subplots(1, len(order), figsize=(6 * len(order), 3.6), squeeze=False)
    freqs = np.fft.rfftfreq(data.shape[1], 1.0 / sfreq)
    spectrum = np.abs(np.fft.rfft(data, axis=1)) ** 2
    keep = (freqs >= 1) & (freqs <= min(200.0, sfreq / 2))

    for ax, region in zip(axes[0], order, strict=False):
        for i, name in enumerate(names):
            if regions[i] != region:
                continue
            ax.semilogy(freqs[keep], spectrum[i, keep], linewidth=0.7, label=name)
        for harmonic in (mains_hz, mains_hz * 2, mains_hz * 3):
            if harmonic < sfreq / 2:
                ax.axvline(harmonic, color="crimson", alpha=0.25, linewidth=0.8)
        ax.set_title(region.upper(), fontsize=9)
        ax.set_xlabel("Frequency (Hz)", fontsize=8)
        ax.grid(alpha=0.25, which="both")
        ax.legend(fontsize=5, ncol=2)
    axes[0][0].set_ylabel("Power", fontsize=8)
    fig.tight_layout()
    png = _fig_to_png(fig)
    plt.close(fig)
    return Figure(
        "Spectra by region",
        png,
        f"One line per contact. Red lines mark {mains_hz:.0f} Hz and its harmonics.",
    )


def _window_snippets(data, sfreq, names, flags: list[Flag], limit: int = 6) -> list[Figure]:
    """A short raw trace around each flagged window, with the window shaded."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    window_flags = [f for f in flags if f.target_type == "window"][:limit]
    index = {name: i for i, name in enumerate(names)}
    figures: list[Figure] = []

    for flag in window_flags:
        channel = flag.evidence.get("channel")
        if channel not in index:
            continue
        t0 = float(flag.evidence.get("t_start_s", 0.0))
        t1 = float(flag.evidence.get("t_end_s", t0 + 1.0))
        pad = 1.5
        lo = max(0, int((t0 - pad) * sfreq))
        hi = min(data.shape[1], int((t1 + pad) * sfreq))
        if hi <= lo:
            continue
        segment = data[index[channel], lo:hi]
        # Downsample for display only; the report must stay small.
        step = max(1, len(segment) // 4000)
        times = np.arange(lo, hi, step) / sfreq
        fig, ax = plt.subplots(figsize=(8, 1.8))
        ax.plot(times, segment[::step], linewidth=0.6, color="#1f2937")
        ax.axvspan(t0, t1, color="orange", alpha=0.25)
        ax.set_xlabel("Time (s)", fontsize=8)
        ax.set_title(f"{channel}  ·  {flag.flag_type}", fontsize=9)
        ax.grid(alpha=0.2)
        fig.tight_layout()
        figures.append(
            Figure(
                f"{channel} at {t0:.1f}s",
                _fig_to_png(fig),
                f"Shaded: the flagged window. Ratio to this channel's median "
                f"peak-to-peak: {flag.evidence.get('ratio', 'n/a')}.",
            )
        )
        plt.close(fig)
    return figures


def build_model(
    study_id: str,
    session: str,
    data: np.ndarray,
    sfreq: float,
    names: list[str],
    regions: list[str],
    flags: list[Flag],
    windows: list[dict[str, Any]] | None = None,
    mains_hz: float = 60.0,
) -> ReportModel:
    """Assemble everything a report shows. Renderer-independent."""
    by_region: dict[str, int] = {}
    for region in regions:
        by_region[region] = by_region.get(region, 0) + 1

    notes: list[str] = []
    if any(f.flag_type == "insufficient_channels" for f in flags):
        notes.append(
            "Some groups have too few contacts for a robust outlier statistic. "
            "Those report evidence with no proposed action, and need a human look "
            "rather than a threshold."
        )
    for window in windows or []:
        if window.get("status") in {"draft", "under_revision"}:
            notes.append(
                f"The {window['condition']} window is marked {window['status']}, so "
                "any result using it inherits that."
            )

    figures = [_psd_grid(data, sfreq, names, regions, mains_hz)]
    figures += _window_snippets(data, sfreq, names, flags)

    return ReportModel(
        study_id=study_id,
        session=session,
        generated_at=datetime.now(UTC).isoformat(timespec="seconds"),
        overview={
            "sampling_rate_hz": round(float(sfreq), 3),
            "duration_s": round(data.shape[1] / sfreq, 1),
            "channels": len(names),
            "channels_by_region": by_region,
            "conditions": [w["condition"] for w in (windows or [])],
            "mains_hz": mains_hz,
        },
        figures=figures,
        flags=flags,
        notes=notes,
    )


_CSS = """
body{font:13px/1.45 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
     margin:0;padding:24px;background:#fafaf9;color:#1c1917}
h1{font-size:17px;margin:0 0 2px}h2{font-size:14px;margin:24px 0 8px}
.sub{color:#78716c;font-size:12px}
table{border-collapse:collapse;width:100%;font-size:12px}
th{text-align:left;color:#78716c;font-weight:600;border-bottom:1px solid #d6d3d1;padding:4px 6px}
td{border-bottom:1px solid #e7e5e4;padding:4px 6px;vertical-align:top}
.sev{display:inline-block;padding:1px 6px;border-radius:3px;font-size:11px;font-weight:600}
.high{background:#ffe4e6;color:#9f1239}.med{background:#fef3c7;color:#92400e}
.low{background:#e7e5e4;color:#44403c}
.note{background:#fffbeb;border-left:3px solid #f59e0b;padding:8px 10px;margin:8px 0;font-size:12px}
figure{margin:12px 0}img{max-width:100%;border:1px solid #e7e5e4;border-radius:3px}
figcaption{color:#78716c;font-size:11px;margin-top:3px}
code{font-size:11px;color:#44403c}
.counts span{display:inline-block;margin-right:12px;font-size:12px}
"""


def render_html(model: ReportModel, path: Path) -> Path:
    """Self-contained HTML. Figures embedded, nothing needed at review time."""
    e = html.escape
    parts = [
        "<!doctype html><meta charset='utf-8'>",
        f"<title>QC {e(model.study_id)}</title><style>{_CSS}</style>",
        f"<h1>QC review · {e(model.study_id)} · {e(model.session)}</h1>",
        f"<p class='sub'>Generated {e(model.generated_at)}. "
        "Flags are proposals with evidence, not decisions.</p>",
    ]

    ov = model.overview
    parts.append("<h2>Overview</h2><p class='counts'>")
    parts.append(f"<span><b>{ov['channels']}</b> channels</span>")
    parts.append(f"<span><b>{ov['sampling_rate_hz']}</b> Hz</span>")
    parts.append(f"<span><b>{ov['duration_s']}</b> s</span>")
    for region, n in ov["channels_by_region"].items():
        parts.append(f"<span>{e(region)}: <b>{n}</b></span>")
    parts.append("</p>")

    counts = model.counts()
    if counts:
        parts.append("<p class='counts'>")
        for kind, n in counts.items():
            parts.append(f"<span>{e(kind)}: <b>{n}</b></span>")
        parts.append("</p>")

    for note in model.notes:
        parts.append(f"<div class='note'>{e(note)}</div>")

    parts.append("<h2>Figures</h2>")
    for figure in model.figures:
        parts.append(
            f"<figure><img alt='{e(figure.title)}' src='{figure.data_uri()}'>"
            f"<figcaption>{e(figure.title)} — {e(figure.caption)}</figcaption></figure>"
        )

    parts.append("<h2>Flags</h2>")
    if not model.flags:
        parts.append("<p class='sub'>No flags.</p>")
    else:
        parts.append(
            "<table><tr><th>severity</th><th>type</th><th>target</th>"
            "<th>proposed</th><th>evidence</th><th>flag id</th></tr>"
        )
        for flag in model.flags_by_severity():
            evidence = ", ".join(f"{k}={v}" for k, v in flag.evidence.items())
            parts.append(
                f"<tr><td><span class='sev {e(flag.severity)}'>{e(flag.severity)}</span></td>"
                f"<td>{e(flag.flag_type)}</td><td>{e(flag.target)}</td>"
                f"<td>{e(flag.proposed_action) or '<i>none</i>'}</td>"
                f"<td>{e(evidence)}</td><td><code>{e(flag.flag_id)}</code></td></tr>"
            )
        parts.append("</table>")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(parts))
    return path


def write_report(
    model: ReportModel, derivatives_dir: Path, filename: str = "report.html"
) -> Path:
    return render_html(model, qc_dir(model.study_id, derivatives_dir) / filename)
