"""pynm_features: py_neuromodulation's published feature set, as a recipe.

Their features are standardized and published, so using them as a library gives
those features without maintaining them and makes outputs comparable to other
labs' work. This wraps their offline stream; it does not reimplement anything.

Written against the installed package (0.1.7) rather than from memory. What that
inspection established, and why each matters:

`nm.Stream(sfreq, channels, settings, line_noise)` then `.run(data=...)`
    Data is passed as ``(n_channels, n_samples)``, which is the orientation our
    reader already returns.

The channels frame needs `name, rereference, used, target, type, status, new_name`
    Built from our manifest, so a contact QC excluded never reaches them.

`rereference` accepts the string `"None"`
    This matters more than it looks. We apply our own montage before handing the
    data over, and their default is a common average. Leaving it at the default
    would re-reference already-referenced data, which is silent and wrong.

`settings.frequency_ranges_hz` is a plain dict of `FrequencyRange`
    So `configs/bands.yaml` drives their bands rather than their defaults, and
    config-over-code survives the boundary.

Their heavier features (fooof, nolds, bispectrum, coherence, mne_connectivity)
are off by default here. They are slow, several need more channels than a lead
has, and none has been calibrated for this data. Turn one on deliberately.
"""

from __future__ import annotations

import json
from typing import Any, ClassVar

import numpy as np
import pandas as pd
from pydantic import BaseModel, Field

from ..preprocess import cutoff_fraction_from, usable_bandwidth_hz
from ..stats import options_for_schema
from .psd import ClaimedEventDuration, _shared_guardrail_context
from .registry import RecipeContext, RecipeResult, recipe

NAME = "pynm_features"

# Off unless asked for: slow, or needing more channels than a lead has, or simply
# uncalibrated for this data.
HEAVY_FEATURES = ("fooof", "nolds", "bispectrum", "coherence", "mne_connectivity")


class PynmParams(BaseModel):
    """Parameters for pynm_features."""

    # Same reason as the other recipes: the form is built from these, and a field
    # named `sampling_rate_features_hz` titled "Sampling Rate Features Hz" asks a
    # person to work out what it means before they can decide whether to touch it.
    # Everything outside ESSENTIAL has a defensible default and sits under
    # Advanced.
    LABELS: ClassVar[dict[str, str]] = {
        "leads": "Leads to include",
        "conditions": "Conditions to label features by",
        "reference": "Montage applied before handing the data over",
        "sfreq_target_hz": "Analyze at this sampling rate (Hz)",
        "features": "Feature set",
        "sampling_rate_features_hz": "Feature values per second",
        "segment_length_features_ms": "Window each value is computed over (ms)",
        "line_noise_hz": "Mains frequency (Hz)",
        "use_project_bands": "Use this project's bands rather than theirs",
    }
    ESSENTIAL: ClassVar[tuple[str, ...]] = (
        "conditions", "features", "reference", "line_noise_hz",
    )
    claimed_event_duration_s: ClaimedEventDuration = None

    leads: list[str] | None = Field(default=None)
    conditions: list[str] | None = Field(
        default=None,
        description="None runs the whole recording and labels each feature row by "
                    "whichever condition window it falls in.",
    )
    reference: str = Field(
        default="bipolar_vertical",
        description="Our montage, applied before the data is handed over. Their "
                    "re-referencing is switched off so it is not applied twice.",
    )
    sfreq_target_hz: float = Field(default=1000.0, gt=0)
    features: list[str] | None = Field(
        default=None,
        description="None means their defaults minus the heavy ones. Naming a "
                    "feature here enables exactly that set.",
    )
    sampling_rate_features_hz: float = Field(default=10.0, gt=0)
    segment_length_features_ms: float = Field(default=1000.0, gt=0)
    line_noise_hz: float = Field(default=60.0, gt=0)
    use_project_bands: bool = Field(
        default=True,
        description="Drive their frequency ranges from configs/bands.yaml rather "
                    "than their defaults.",
    )


def build_channels(names: list[str], region: str) -> pd.DataFrame:
    """Their channels frame, from our derivation names.

    `rereference` is the string "None" deliberately: the data handed over has
    already been re-referenced by our montage, and their default common average
    would silently apply a second one.
    """
    # Their vocabulary, not ours. A depth lead is 'dbs'; anything else we hand
    # over is cortical.
    ch_type = "dbs" if region in {"stn", "gpi", "gpe", "vim"} else "ecog"
    return pd.DataFrame({
        "name": names,
        "rereference": ["None"] * len(names),
        "used": [1] * len(names),
        "target": [0] * len(names),
        "type": [ch_type] * len(names),
        "status": ["good"] * len(names),
        "new_name": names,
    })


def build_settings(ctx: RecipeContext, params: PynmParams):
    """Their settings object, driven by our config where the two overlap."""
    import py_neuromodulation as nm
    from py_neuromodulation.utils.types import FrequencyRange

    settings = nm.NMSettings.get_default()
    settings.sampling_rate_features_hz = params.sampling_rate_features_hz
    settings.segment_length_features_ms = params.segment_length_features_ms

    available = set(settings.features.model_dump())
    if params.features is not None:
        unknown = sorted(set(params.features) - available)
        if unknown:
            raise ValueError(
                f"unknown py_neuromodulation feature(s) {unknown}; "
                f"available: {sorted(available)}"
            )
        for name in available:
            setattr(settings.features, name, name in params.features)
    else:
        for name in HEAVY_FEATURES:
            if name in available:
                setattr(settings.features, name, False)

    if params.use_project_bands:
        configured = (ctx.configs.get("bands") or {}).get("bands") or {}
        nyquist = params.sfreq_target_hz / 2
        ours = {
            name: FrequencyRange(float(lo), float(hi))
            for name, (lo, hi) in configured.items()
            if hi < nyquist
        }
        if ours:
            settings.frequency_ranges_hz = ours
    return settings


def label_conditions(
    times_s: np.ndarray, windows: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    """Label each feature row by the condition window it falls in.

    Rows outside every window get an empty label rather than being dropped, so a
    reader can see how much of the recording was not in any condition.
    """
    labels = [""] * len(times_s)
    statuses = [""] * len(times_s)
    for window in windows:
        t0, t1 = float(window["t_start_s"]), float(window["t_end_s"])
        inside = (times_s >= t0) & (times_s < t1)
        for index in np.flatnonzero(inside):
            labels[int(index)] = window["condition"]
            statuses[int(index)] = window.get("status", "")
    return labels, statuses


def _feature_times_seconds(frame: pd.DataFrame, duration_s: float) -> np.ndarray:
    """Their `time` column, normalized to seconds and checked against the recording.

    Measured against the installed version, the unit is milliseconds. It is not
    documented in the signature, so rather than trust that, the values are
    checked against the recording length: getting this wrong would mislabel every
    feature row's condition silently, which is worse than failing.
    """
    if "time" not in frame.columns:
        return np.arange(len(frame), dtype=float)
    times = frame["time"].to_numpy(dtype=float)
    if times.size == 0 or duration_s <= 0:
        return times

    span = float(times.max())
    if span <= duration_s * 1.5:
        return times                      # already seconds
    if span <= duration_s * 1500.0:
        return times / 1000.0             # milliseconds, as measured
    raise ValueError(
        f"py_neuromodulation returned feature times spanning {span}, which is "
        f"neither seconds nor milliseconds for a {duration_s:.1f} s recording. "
        "Refusing to guess: a wrong unit mislabels every row's condition silently."
    )

def guardrail_context(session: Any, params: PynmParams) -> dict[str, Any]:
    conditions = tuple(params.conditions or session.conditions())
    configured = (session.configs.get("bands") or {}).get("bands") or {}
    nyquist = params.sfreq_target_hz / 2
    bands = {
        name: (float(lo), float(hi))
        for name, (lo, hi) in configured.items()
        if hi < nyquist
    }
    return {
        "reference_scheme": params.reference,
        "reference_is_shared": True,
        "sfreq_hz": params.sfreq_target_hz,
        "usable_bandwidth_hz": usable_bandwidth_hz(
            params.sfreq_target_hz, cutoff_fraction_from(session.configs)
        ),
        "requested_bands": bands,
        "window_s": params.segment_length_features_ms / 1000.0,
        "conditions": conditions,
        # Their features are not dB or z; they are their own units, so the
        # dB-without-z check does not apply here.
        "reports_db": None,
        "reports_z": None,
        "baseline_is_smoothed": False,
        "per_contact_baseline_subtracted": True,
        **_shared_guardrail_context(session, params),
    }


@recipe(
    NAME,
    "py_neuromodulation's feature set computed on approved data, with their "
    "settings driven by our config and their re-referencing switched off.",
    PynmParams,
    version="1",
    question="What does the standard py_neuromodulation feature set give for this "
             "recording?",
    produces="A feature time series per derivation, the settings file they ran "
             "under, and a summary of which features were computed.",
)
def pynm_features(ctx: RecipeContext) -> RecipeResult:
    import py_neuromodulation as nm

    params: PynmParams = ctx.params
    session = ctx.session
    lead_ids = params.leads or list(session.leads())

    windows = [
        w for w in session.windows()
        if params.conditions is None or w["condition"] in params.conditions
    ]
    settings = build_settings(ctx, params)
    enabled = sorted(k for k, v in settings.features.model_dump().items() if v)
    ctx.log(f"features enabled: {enabled}")

    frames: list[pd.DataFrame] = []
    for lead_id in lead_ids:
        lead = session.leads()[lead_id]
        sig = session.read_derived(
            lead_id, params.reference, sfreq_target_hz=params.sfreq_target_hz
        )
        channels = build_channels(list(sig.names), lead.target)
        ctx.log(f"{lead_id}: {len(sig.names)} derivations at {sig.sfreq_hz:.1f} Hz")

        stream = nm.Stream(
            sfreq=sig.sfreq_hz, channels=channels, settings=settings,
            line_noise=params.line_noise_hz, verbose=False,
        )
        features = stream.run(
            data=sig.data, out_dir=str(ctx.out_dir),
            experiment_name=f"{session.study_id}_{lead_id}",
            save_csv=False, return_df=True,
        )
        duration_s = sig.data.shape[1] / sig.sfreq_hz
        times = _feature_times_seconds(features, duration_s)
        labels, statuses = label_conditions(times, windows)
        features = features.assign(
            study_id=session.study_id, lead_id=lead_id, target=lead.target,
            scheme=params.reference, time_s=times,
            condition=labels, window_status=statuses,
        )
        frames.append(features)

    if not frames:
        raise RuntimeError("no features computed; check the manifest leads")

    features = pd.concat(frames, ignore_index=True)
    out = ctx.out_dir
    features.to_parquet(out / "features.parquet", index=False)

    # Their exact settings, so a run can be reproduced against their version.
    settings_path = out / "pynm_settings.json"
    settings_path.write_text(
        json.dumps(settings.model_dump(), indent=2, default=str)
    )

    summary = {
        "recipe": NAME,
        "py_neuromodulation_version": getattr(nm, "__version__", "unknown"),
        "features_enabled": enabled,
        "n_feature_rows": int(len(features)),
        "n_feature_columns": int(
            len([c for c in features.columns if "_" in c and not c.startswith("study")])
        ),
        "reference": params.reference,
        "their_rereferencing": "disabled; ours is applied before handover",
        "frequency_ranges_hz": {
            name: [r.frequency_low_hz, r.frequency_high_hz]
            for name, r in settings.frequency_ranges_hz.items()
        },
        "rows_by_condition": features["condition"].value_counts().to_dict(),
        "rows_outside_any_window": int((features["condition"] == "").sum()),
        "windows_needing_care": sorted(
            features.loc[features["window_status"].isin(["under_revision", "draft"]),
                         "condition"].unique().tolist()
        ),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return RecipeResult(tables={"features": features}, figures=[], summary=summary)


pynm_features.guardrail_context = guardrail_context
pynm_features.option_explanations = options_for_schema
