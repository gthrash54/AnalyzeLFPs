"""The z column: (value - centre) / scale, with both halves chosen separately.

Centre and scale answer different questions. The centre decides what a result is
compared against; the scale decides what counts as a large difference. Coupling
them into one `baseline` setting hid that, and hid which of the two a reader was
actually looking at.

Every option's meaning lives in `configs/statistics.yaml` rather than in a
docstring, so the same words reach three places: the JSON schema an interface
builds its form from, the run record, and the figure caption. A reader should
never have to guess what a z meant.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

DEFAULT_CONFIG = Path(__file__).resolve().parents[3] / "configs" / "statistics.yaml"

CENTERS = ("grand_mean", "condition", "whole_recording", "none")
SCALES = (
    "pooled_within_condition",
    "own_condition",
    "condition",
    "across_conditions",
    "none",
)


def load_options(path: Path | None = None) -> dict[str, Any]:
    p = Path(path or DEFAULT_CONFIG)
    return yaml.safe_load(p.read_text()) if p.exists() else {"centers": {}, "scales": {}}


@dataclass(frozen=True)
class NormalizationChoice:
    """A resolved centre and scale, with the words that explain them."""

    center: str
    scale: str
    baseline_condition: str
    center_info: dict[str, str]
    scale_info: dict[str, str]

    def sentence(self) -> str:
        """One line for a figure caption or a run summary."""
        c = self.center_info.get("label", self.center)
        s = self.scale_info.get("label", self.scale)
        if self.center == "condition" or self.scale == "condition":
            return f"z = (value - {c}) / {s}, baseline condition '{self.baseline_condition}'"
        return f"z = (value - {c}) / {s}"

    def to_record(self) -> dict[str, Any]:
        """What the run record stores, explanations included."""
        return {
            "center": self.center,
            "scale": self.scale,
            "baseline_condition": self.baseline_condition,
            "sentence": self.sentence(),
            "center_explanation": self.center_info,
            "scale_explanation": self.scale_info,
        }


def describe_choice(
    center: str,
    scale: str,
    baseline_condition: str = "rest",
    options: dict[str, Any] | None = None,
) -> NormalizationChoice:
    """Resolve a centre and scale against the configured explanations."""
    options = options if options is not None else load_options()
    if center not in CENTERS:
        raise ValueError(f"unknown centre {center!r}; have {CENTERS}")
    if scale not in SCALES:
        raise ValueError(f"unknown scale {scale!r}; have {SCALES}")
    return NormalizationChoice(
        center=center,
        scale=scale,
        baseline_condition=baseline_condition,
        center_info=(options.get("centers") or {}).get(center, {}),
        scale_info=(options.get("scales") or {}).get(scale, {}),
    )


def options_for_schema(options: dict[str, Any] | None = None) -> dict[str, Any]:
    """Explanations in the shape an interface can render beside each choice."""
    options = options if options is not None else load_options()
    out: dict[str, Any] = {}
    for group, keys in (("centers", CENTERS), ("scales", SCALES)):
        out[group] = [
            {
                "value": key,
                "label": (options.get(group) or {}).get(key, {}).get("label", key),
                "description": (options.get(group) or {})
                .get(key, {})
                .get("description", "")
                .strip(),
                "when_to_use": (options.get(group) or {})
                .get(key, {})
                .get("when_to_use", "")
                .strip(),
                "caveat": (options.get(group) or {}).get(key, {}).get("caveat", "").strip(),
            }
            for key in keys
        ]
    return out


def normalize(
    long: pd.DataFrame,
    choice: NormalizationChoice,
    key: list[str],
    value_col: str = "db",
    sd_col: str = "db_sd",
    condition_col: str = "condition",
) -> pd.Series:
    """Return the z column for `long`, grouped by `key`.

    `long` carries one row per group per condition, with `value_col` the mean and
    `sd_col` the spread across time segments within that condition.
    """
    center = _center(long, choice, key, value_col, condition_col)
    scale = _scale(long, choice, key, value_col, sd_col, condition_col)
    # A zero or missing scale would produce infinities, which read as enormous
    # effects. Better an explicit NaN that a reader notices.
    safe = scale.replace(0.0, np.nan)
    return (long[value_col] - center) / safe


def _center(
    long: pd.DataFrame,
    choice: NormalizationChoice,
    key: list[str],
    value_col: str,
    condition_col: str,
) -> pd.Series:
    if choice.center == "none":
        return pd.Series(0.0, index=long.index)
    if choice.center == "condition":
        base = long[long[condition_col] == choice.baseline_condition]
        if base.empty:
            raise ValueError(
                f"centre 'condition' needs condition {choice.baseline_condition!r}, "
                f"which is not in this run (have {sorted(long[condition_col].unique())})"
            )
        return _broadcast(long, base.groupby(key)[value_col].mean(), key)
    if choice.center == "whole_recording":
        # Weighted by segment count where available, so longer conditions count
        # for more; that is the difference from grand_mean.
        if "n_segments" in long.columns:
            weighted = long.assign(_w=long[value_col] * long["n_segments"])
            num = weighted.groupby(key)["_w"].sum()
            den = long.groupby(key)["n_segments"].sum()
            return _broadcast(long, num / den, key)
        return _broadcast(long, long.groupby(key)[value_col].mean(), key)
    return _broadcast(long, long.groupby(key)[value_col].mean(), key)


def _pooled_sd(long: pd.DataFrame, key: list[str], sd_col: str) -> pd.Series:
    """Pooled standard deviation per group, weighted by segment count.

        s_pooled = sqrt( sum((n_i - 1) * s_i^2) / sum(n_i - 1) )

    This used to be `long.groupby(key)[sd_col].mean()`, the arithmetic mean of
    the per-condition standard deviations. That is a different and systematically
    smaller number: by Jensen's inequality mean(s_i) <= sqrt(mean(s_i^2)), with
    equality only when every s_i is equal. Since this is the default scale and it
    divides every z, every default z in the project was inflated. Measured on
    synthetic groups: 1.003x for mildly unequal SDs, 1.25x for strongly unequal
    ones, 1.8x when the segment counts differ as well.

    It is the same inequality, in the same direction, that guardrail G3 already
    refuses to let a recipe commit when it forms a ratio after averaging.

    `n_segments` is already carried on every row, so the correct weighting costs
    nothing. Where it is absent, or where every weight is zero because each
    condition contributed a single segment, this falls back to the unweighted
    root mean square of the SDs, which is the pooled SD under equal n.
    """
    frame = long[key].copy()
    sd = long[sd_col].astype(float)
    if "n_segments" in long.columns:
        weight = (long["n_segments"].astype(float) - 1.0).clip(lower=0.0)
    else:
        weight = pd.Series(1.0, index=long.index)

    frame["_w"] = weight.to_numpy()
    frame["_num"] = (weight * sd**2).to_numpy()
    num = frame.groupby(key)["_num"].sum()
    den = frame.groupby(key)["_w"].sum()

    pooled = np.sqrt(num / den.where(den > 0))
    if pooled.isna().any():
        # Every condition in the group had one segment, so (n-1) is zero
        # throughout and the weighting carries no information.
        frame["_sq"] = (sd**2).to_numpy()
        unweighted = np.sqrt(frame.groupby(key)["_sq"].mean())
        pooled = pooled.fillna(unweighted)
    return pooled


def _scale(
    long: pd.DataFrame,
    choice: NormalizationChoice,
    key: list[str],
    value_col: str,
    sd_col: str,
    condition_col: str,
) -> pd.Series:
    if choice.scale == "none":
        return pd.Series(1.0, index=long.index)
    if choice.scale == "own_condition":
        return long[sd_col].astype(float)
    if choice.scale == "condition":
        base = long[long[condition_col] == choice.baseline_condition]
        if base.empty:
            raise ValueError(
                f"scale 'condition' needs condition {choice.baseline_condition!r}, "
                f"which is not in this run (have {sorted(long[condition_col].unique())})"
            )
        return _broadcast(long, base.groupby(key)[sd_col].mean(), key)
    if choice.scale == "across_conditions":
        counts = long.groupby(key)[condition_col].nunique()
        if (counts < 2).any():
            thin = sorted(counts[counts < 2].index.astype(str))[:5]
            raise ValueError(
                "scale 'across_conditions' measures spread between conditions, "
                f"and {int((counts < 2).sum())} group(s) have only one: {thin}. "
                "std of a single value is NaN, which would silently empty the "
                "whole z column. Choose another scale or include another "
                "condition."
            )
        spread = long.groupby(key)[value_col].std(ddof=1)
        return _broadcast(long, spread, key)
    return _broadcast(long, _pooled_sd(long, key, sd_col), key)


def _broadcast(long: pd.DataFrame, per_group: pd.Series, key: list[str]) -> pd.Series:
    """Spread a per-group value back over every row of that group."""
    merged = long[key].merge(
        per_group.rename("_v").reset_index(), on=key, how="left"
    )
    return pd.Series(merged["_v"].to_numpy(), index=long.index)
