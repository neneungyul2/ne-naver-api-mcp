import pytest

from ne_naver_api_mcp.analysis.rescale import (
    AnchorError,
    SeriesPoint,
    estimate_trend_calls,
    pick_median_anchor,
    plan_batches,
    rescale,
    ScaledSeries,
)


def pts(*ratios):
    return [SeriesPoint(f"2025-0{i + 1}-01", r) for i, r in enumerate(ratios)]


def ratios(series: ScaledSeries) -> list[float]:
    return [p.ratio for p in series.points]


def by(res, brand) -> ScaledSeries:
    return next(s for s in res if s.brand == brand)


def test_rescale_scales_later_batches_by_the_anchor_sum_ratio():
    res = rescale(
        "A",
        [
            {"A": pts(100, 50), "X": pts(10, 5)},
            {"A": pts(50, 25), "Y": pts(100, 50)},
        ],
    )
    assert ratios(by(res, "A")) == [100, 50]
    assert ratios(by(res, "X")) == [10, 5]
    assert ratios(by(res, "Y")) == [200, 100]  # k = 150 / 75 = 2
    assert res[0].brand == "A"  # 기준이 맨 앞


def test_zero_anchor_in_first_batch_with_several_batches_is_an_anchor_error():
    with pytest.raises(AnchorError, match="기준 브랜드"):
        rescale("A", [{"A": pts(0, 0), "X": pts(10, 5)}, {"A": pts(5, 5), "Y": pts(1, 1)}])


def test_single_batch_needs_no_scaling_so_zero_anchor_is_fine():
    res = rescale("A", [{"A": pts(0, 0), "X": pts(10, 5)}])
    assert ratios(by(res, "X")) == [10, 5]
    assert by(res, "A").low_precision is True


def test_zero_anchor_sum_in_a_later_batch_is_an_anchor_error():
    with pytest.raises(AnchorError):
        rescale("A", [{"A": pts(100, 50), "X": pts(1, 1)}, {"A": pts(0, 0), "Y": pts(100, 50)}])


def test_anchor_missing_from_a_batch_is_an_anchor_error():
    with pytest.raises(AnchorError):
        rescale("A", [{"A": pts(1, 1)}, {"Y": pts(1, 1)}])


def test_low_precision_when_max_is_below_threshold():
    res = rescale("A", [{"A": pts(100, 50), "small": pts(0.4, 0.1), "big": pts(5, 1)}])
    assert by(res, "small").low_precision is True
    assert by(res, "big").low_precision is False


def test_weak_anchor_in_a_later_batch_flags_that_batchs_brands():
    res = rescale(
        "A",
        [
            {"A": pts(100, 100), "X": pts(50, 50)},
            {"A": pts(0.5, 0.5), "F": pts(100, 100)},
        ],
    )
    assert by(res, "F").low_precision is True
    assert by(res, "X").low_precision is False


def test_empty_batches_is_an_anchor_error():
    with pytest.raises(AnchorError):
        rescale("A", [])


def test_plan_batches_puts_the_anchor_first_in_every_batch():
    assert plan_batches(["A", "B", "C", "D", "E", "F"], "A", 5) == [
        ["A", "B", "C", "D", "E"],
        ["A", "F"],
    ]
    assert plan_batches(["A"], "A", 5) == [["A"]]
    assert plan_batches(["B", "A"], "A", 5) == [["A", "B"]]
    with pytest.raises(ValueError):
        plan_batches(["A", "B"], "Z", 5)


@pytest.mark.parametrize("n, expected", [(1, 1), (5, 1), (6, 2), (10, 3)])
def test_estimate_trend_calls(n, expected):
    assert estimate_trend_calls(n, 5) == expected


def test_pick_median_anchor_chooses_the_middle_total():
    scaled = [
        ScaledSeries("lo", pts(5, 5), False),
        ScaledSeries("mid", pts(10, 10), False),
        ScaledSeries("hi", pts(15, 15), False),
    ]
    assert pick_median_anchor(scaled) == "mid"


def test_pick_median_anchor_skips_zero_sum_brands_and_uses_lower_median_for_even_counts():
    scaled = [
        ScaledSeries("z1", pts(0, 0), True),
        ScaledSeries("z2", pts(0, 0), True),
        ScaledSeries("z3", pts(0, 0), True),
        ScaledSeries("lo", pts(1, 1), False),
        ScaledSeries("hi", pts(9, 9), False),
    ]
    assert pick_median_anchor(scaled) == "lo"
    with pytest.raises(AnchorError):
        pick_median_anchor([ScaledSeries("z", pts(0), True)])
