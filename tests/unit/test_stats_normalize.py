"""Centre and scale, chosen separately, each carrying its explanation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from dbsspeech.stats import (
    CENTERS,
    SCALES,
    describe_choice,
    load_options,
    normalize,
    options_for_schema,
)

pytestmark = pytest.mark.unit

KEY = ["derivation", "freq_hz"]


@pytest.fixture
def long():
    """One derivation, one frequency, three conditions with known values."""
    return pd.DataFrame(
        {
            "derivation": ["d1"] * 3,
            "freq_hz": [20.0] * 3,
            "condition": ["overt", "metro", "rest"],
            "db": [10.0, 4.0, 1.0],       # mean 5.0
            "db_sd": [2.0, 1.0, 3.0],     # pooled sqrt((4+1+9)/3) = 2.16025
            "n_segments": [10, 10, 10],
        }
    )


# ---- explanations ------------------------------------------------------------

def test_every_option_is_explained():
    """A bare enum tells a first-year student nothing."""
    options = load_options()
    for group, keys in (("centers", CENTERS), ("scales", SCALES)):
        for key in keys:
            info = options[group][key]
            assert info["description"].strip()
            assert info["when_to_use"].strip()
            assert info["caveat"].strip()


def test_schema_options_are_render_ready():
    opts = options_for_schema()
    assert {o["value"] for o in opts["centers"]} == set(CENTERS)
    assert {o["value"] for o in opts["scales"]} == set(SCALES)
    for o in opts["centers"] + opts["scales"]:
        assert o["label"] and o["description"] and o["caveat"]


def test_choice_produces_a_caption_sentence():
    s = describe_choice("grand_mean", "pooled_within_condition").sentence()
    assert "Grand mean" in s and "Pooled within-condition" in s


def test_caption_names_the_baseline_condition_when_one_is_used():
    s = describe_choice("condition", "condition", baseline_condition="rest").sentence()
    assert "'rest'" in s


def test_run_record_carries_the_explanations():
    rec = describe_choice("grand_mean", "own_condition").to_record()
    assert rec["center"] == "grand_mean"
    assert rec["scale_explanation"]["caveat"].strip()
    assert rec["sentence"]


def test_unknown_choices_name_the_valid_ones():
    with pytest.raises(ValueError, match="unknown centre"):
        describe_choice("vibes", "none")
    with pytest.raises(ValueError, match="unknown scale"):
        describe_choice("none", "vibes")


# ---- arithmetic --------------------------------------------------------------

def test_grand_mean_and_pooled_scale(long):
    """Centre 5.0, scale the pooled SD sqrt((4 + 1 + 9) / 3) = 2.16025.

    This asserted mean(2, 1, 3) = 2.0 until 2026-09-09, which is the arithmetic
    mean of the standard deviations rather than a pooled one, and is the smaller
    of the two whenever the conditions differ in variability. The test agreed
    with the code and both were wrong, so every z on the default scale was
    inflated: on this fixture by a factor of 2.16025 / 2.0, about 8 percent.
    """
    pooled = np.sqrt((2.0**2 + 1.0**2 + 3.0**2) / 3.0)
    z = normalize(long, describe_choice("grand_mean", "pooled_within_condition"), KEY)
    np.testing.assert_allclose(
        z, [(10 - 5) / pooled, (4 - 5) / pooled, (1 - 5) / pooled]
    )
    # And the direction, stated so a future change cannot quietly reverse it.
    assert pooled > np.mean([2.0, 1.0, 3.0])


def test_own_condition_scale_uses_each_conditions_spread(long):
    z = normalize(long, describe_choice("grand_mean", "own_condition"), KEY)
    np.testing.assert_allclose(z, [(10 - 5) / 2, (4 - 5) / 1, (1 - 5) / 3])


def test_named_baseline_condition_centres_on_it(long):
    choice = describe_choice("condition", "none", baseline_condition="rest")
    z = normalize(long, choice, KEY)
    np.testing.assert_allclose(z, [9.0, 3.0, 0.0])


def test_baseline_condition_scale(long):
    choice = describe_choice("condition", "condition", baseline_condition="rest")
    z = normalize(long, choice, KEY)
    np.testing.assert_allclose(z, [9 / 3, 3 / 3, 0.0])


def test_no_centring_gives_a_ratio(long):
    z = normalize(long, describe_choice("none", "own_condition"), KEY)
    np.testing.assert_allclose(z, [10 / 2, 4 / 1, 1 / 3])


def test_no_scaling_leaves_decibels(long):
    z = normalize(long, describe_choice("grand_mean", "none"), KEY)
    np.testing.assert_allclose(z, [5.0, -1.0, -4.0])


def test_across_conditions_scale_uses_the_spread_of_means(long):
    z = normalize(long, describe_choice("grand_mean", "across_conditions"), KEY)
    expected_sd = np.std([10.0, 4.0, 1.0], ddof=1)
    np.testing.assert_allclose(z, [(10 - 5) / expected_sd, (4 - 5) / expected_sd,
                                   (1 - 5) / expected_sd])


def test_whole_recording_weights_by_segment_count(long):
    """Longer conditions pull the centre; that is what separates it from grand_mean."""
    weighted = long.copy()
    weighted.loc[weighted["condition"] == "rest", "n_segments"] = 80
    z_grand = normalize(weighted, describe_choice("grand_mean", "none"), KEY)
    z_whole = normalize(weighted, describe_choice("whole_recording", "none"), KEY)
    assert not np.allclose(z_grand, z_whole)


def test_zero_scale_becomes_nan_not_infinity(long):
    """An infinite z reads as an enormous effect; NaN is noticed."""
    flat = long.copy()
    flat["db_sd"] = 0.0
    z = normalize(flat, describe_choice("grand_mean", "own_condition"), KEY)
    assert z.isna().all()


def test_missing_baseline_condition_is_an_explicit_error(long):
    choice = describe_choice("condition", "none", baseline_condition="nope")
    with pytest.raises(ValueError, match="not in this run"):
        normalize(long, choice, KEY)


def test_every_combination_runs(long):
    for center in CENTERS:
        for scale in SCALES:
            choice = describe_choice(center, scale, baseline_condition="rest")
            out = normalize(long, choice, KEY)
            assert len(out) == len(long)


# ---- B5. the pooled scale is pooled ------------------------------------------

def _pooled_closed_form(sds, ns):
    import numpy as np

    w = np.clip(np.asarray(ns, float) - 1.0, 0, None)
    sds = np.asarray(sds, float)
    if w.sum() == 0:
        return float(np.sqrt(np.mean(sds**2)))
    return float(np.sqrt(np.sum(w * sds**2) / w.sum()))


@pytest.mark.parametrize(
    ("sds", "ns"),
    [
        ([2.0, 2.0, 2.0], [10, 10, 10]),      # equal: pooled == mean
        ([1.8, 2.0, 2.2], [10, 10, 10]),
        ([0.5, 2.0, 5.0], [10, 10, 10]),
        ([0.5, 2.0, 5.0], [5, 10, 50]),       # unequal n, weighting matters
        ([1.0, 3.0], [1, 1]),                 # every weight zero, RMS fallback
        ([2.5], [12]),                        # a single condition
    ],
)
def test_the_pooled_scale_matches_the_closed_form(sds, ns):
    import pandas as pd

    from dbsspeech.stats.normalize import _pooled_sd

    long = pd.DataFrame({
        "grp": ["g"] * len(sds),
        "condition": [f"c{i}" for i in range(len(sds))],
        "db_sd": sds,
        "n_segments": ns,
    })
    got = float(_pooled_sd(long, ["grp"], "db_sd").iloc[0])
    assert got == pytest.approx(_pooled_closed_form(sds, ns), abs=1e-12)


def test_the_pooled_scale_is_never_below_the_mean_of_the_sds():
    """The direction of the bug. mean(s_i) <= sqrt(mean(s_i^2)) by Jensen, so
    the old scale was too small and every z it divided was too large."""
    import numpy as np
    import pandas as pd

    from dbsspeech.stats.normalize import _pooled_sd

    rng = np.random.default_rng(0)
    for _ in range(200):
        sds = rng.uniform(0.1, 6.0, size=4)
        long = pd.DataFrame({
            "grp": ["g"] * 4, "condition": list("abcd"),
            "db_sd": sds, "n_segments": [10] * 4,
        })
        pooled = float(_pooled_sd(long, ["grp"], "db_sd").iloc[0])
        assert pooled >= float(np.mean(sds)) - 1e-12


def test_pooling_groups_independently():
    import pandas as pd

    from dbsspeech.stats.normalize import _pooled_sd

    long = pd.DataFrame({
        "grp": ["a", "a", "b", "b"],
        "condition": ["c1", "c2", "c1", "c2"],
        "db_sd": [1.0, 3.0, 2.0, 2.0],
        "n_segments": [10, 10, 10, 10],
    })
    out = _pooled_sd(long, ["grp"], "db_sd")
    assert float(out.loc["a"]) == pytest.approx(_pooled_closed_form([1, 3], [10, 10]))
    assert float(out.loc["b"]) == pytest.approx(2.0)


def test_across_conditions_refuses_a_single_condition_instead_of_returning_nan():
    """std of one value is NaN, which emptied the whole z column with no
    message."""
    import pandas as pd

    from dbsspeech.stats import describe_choice, normalize

    long = pd.DataFrame({
        "grp": ["g", "g"], "condition": ["overt", "overt"],
        "db": [1.0, 2.0], "db_sd": [0.5, 0.5], "n_segments": [10, 10],
    })
    choice = describe_choice("grand_mean", "across_conditions")
    with pytest.raises(ValueError, match="only one"):
        normalize(long, choice, ["grp"])
