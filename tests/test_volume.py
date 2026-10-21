"""검색광고 검색수로 Data Lab 일 지수를 환산하는 역산 로직 테스트 (가짜 API, 정답을 알고 있는 세계)."""
from datetime import date, timedelta

import pytest

from ne_naver_api_mcp.analysis.brand import Brand
from ne_naver_api_mcp.analysis.budget import BudgetExceededError
from ne_naver_api_mcp.analysis.rescale import SeriesPoint
from ne_naver_api_mcp.analysis.volume import (
    VolumeInput,
    calibration_factor,
    estimate_search_volume,
    group_volume,
    monthly_estimates,
    parse_count,
    parse_keyword_list,
    unique_hints,
    window_bounds,
)
from ne_naver_api_mcp.cache import CallCounter, FileCache

TODAY = "2026-10-21"  # 환산 기준 구간 = 2026-09-21 ~ 2026-10-20


def days(start: str, end: str):
    d = date.fromisoformat(start)
    while d <= date.fromisoformat(end):
        yield d
        d += timedelta(days=1)


class FakeTrend:
    """truth[브랜드](날짜) = 그날의 실제 검색량. 요청마다 최댓값 100으로 정규화한다 (Data Lab 흉내)."""

    def __init__(self, truth):
        self.truth = truth
        self.calls: list[dict] = []

    async def search_trend(self, req):
        self.calls.append(req)
        assert req["timeUnit"] == "date"
        ds = list(days(req["startDate"], req["endDate"]))
        vols = {g["groupName"]: [self.truth[g["groupName"]](d) for d in ds] for g in req["keywordGroups"]}
        peak = max(v for vs in vols.values() for v in vs)
        return {
            "results": [
                {"title": n, "data": [{"period": d.isoformat(), "ratio": v / peak * 100} for d, v in zip(ds, vs)]}
                for n, vs in vols.items()
            ]
        }

    async def shopping_keywords(self, req):  # pragma: no cover
        raise AssertionError

    async def search(self, type, params):  # noqa: A002  # pragma: no cover
        raise AssertionError


class FakeSearchAd:
    """keyword -> 응답 행. 값은 정수 또는 '< 10'."""

    def __init__(self, rows: dict[str, tuple[object, object]]):
        self.rows = rows
        self.calls: list[list[str]] = []

    async def keyword_tool(self, hints):
        self.calls.append(list(hints))
        return {
            "keywordList": [
                {"relKeyword": h, "monthlyPcQcCnt": self.rows[h][0], "monthlyMobileQcCnt": self.rows[h][1], "compIdx": "높음"}
                for h in hints
                if h in self.rows
            ]
        }


A = lambda d: 1000 + (d.day % 5) * 10  # noqa: E731
B = lambda d: 300  # noqa: E731
W0, W1 = window_bounds(TODAY)


def window_total(fn) -> int:
    return sum(fn(d) for d in days(W0, W1))


def month_truth(fn, month: str) -> int:
    first = date.fromisoformat(f"{month}-01")
    return sum(fn(d) for d in days(first.isoformat(), (first.replace(day=28) + timedelta(days=4)).replace(day=1).isoformat()) if d.month == first.month)


@pytest.fixture
def cache(tmp_path):
    return FileCache(tmp_path / "cache", ttl_ms=10**9)


def run(brands, trend, ad, cache, **over):
    base = dict(brands=brands, start_date="2026-08-01", end_date="2026-09-30")
    base.update(over)
    return estimate_search_volume(VolumeInput(**base), trend, ad, cache, CallCounter(), today=TODAY)


def test_parse_count_variants():
    assert parse_count(1234) == (1234, False)
    assert parse_count("1,234") == (1234, False)
    assert parse_count("< 10") == (None, True)
    assert parse_count("<10") == (None, True)
    assert parse_count(None) == (None, False)
    assert parse_count(True) == (None, False)


def test_parse_keyword_list_and_group_dedupes_spacing_variants():
    stats = parse_keyword_list(
        {"keywordList": [
            {"relKeyword": "그래머인사이드", "monthlyPcQcCnt": 100, "monthlyMobileQcCnt": "< 10"},
            {"relKeyword": "Zeta", "monthlyPcQcCnt": 5000, "monthlyMobileQcCnt": 9000},
        ]}
    )
    brand = Brand("그래머인사이드", ("그래머 인사이드", "Grammar Inside"))
    assert unique_hints(brand) == ["그래머인사이드", "grammarinside"]
    g = group_volume(brand, stats)
    assert g.total == 100 and g.low and not g.usable  # 모바일이 10 미만으로 가려져 기준으로 못 쓴다
    assert g.missing == ["grammarinside"]


def test_window_bounds_are_30_days_ending_yesterday():
    assert window_bounds("2026-10-21") == ("2026-09-21", "2026-10-20")
    assert (date.fromisoformat(W1) - date.fromisoformat(W0)).days == 29


def test_calibration_factor_guards():
    assert calibration_factor(300, 3.0) == 100
    assert calibration_factor(0, 3.0) is None
    assert calibration_factor(300, 0.0) is None


def test_monthly_estimates_marks_partial_months():
    pts = [SeriesPoint(f"2026-08-{d:02d}", 1.0) for d in range(10, 32)] + [
        SeriesPoint(f"2026-09-{d:02d}", 2.0) for d in range(1, 31)
    ]
    rows = {r["month"]: r for r in monthly_estimates(pts, 10, "2026-08-01", "2026-09-30")}
    assert rows["2026-08"]["partial"] and rows["2026-08"]["estimated"] == 220
    assert not rows["2026-09"]["partial"] and rows["2026-09"]["estimated"] == 600


async def test_recovers_true_monthly_volume_for_two_brands(cache):
    trend = FakeTrend({"A": A, "B": B})
    ad = FakeSearchAd({
        "aa": (int(window_total(A) * 0.6), window_total(A) - int(window_total(A) * 0.6)),
        "bb": (int(window_total(B) * 0.6), window_total(B) - int(window_total(B) * 0.6)),
    })
    # 브랜드 이름이 곧 키워드다 (소문자·공백 제거: "aa", "bb")
    trend = FakeTrend({"AA": A, "BB": B})
    result = await run([Brand("AA", ("A A",)), Brand("BB")], trend, ad, cache)
    by = {e.brand: e for e in result.estimates}
    assert by["AA"].k_source == "own" and by["BB"].k_source == "own"
    sept = {e.brand: next(r for r in e.monthly if r["month"] == "2026-09") for e in result.estimates}
    assert not sept["AA"]["partial"]
    assert sept["AA"]["estimated"] == pytest.approx(month_truth(A, "2026-09"), abs=2)
    assert sept["BB"]["estimated"] == pytest.approx(month_truth(B, "2026-09"), abs=2)
    # 호출: 일 단위 트렌드 1회 + 검색광고 1회 (공백만 다른 별칭은 한 키워드로 센다)
    assert len(trend.calls) == 1 and ad.calls == [["aa", "bb"]]
    assert result.warnings == [] and result.common_k == pytest.approx(by["AA"].k, rel=1e-6)


async def test_low_volume_brand_uses_common_scale_with_warning(cache):
    trend = FakeTrend({"AA": A, "BB": B})
    ad = FakeSearchAd({
        "aa": (window_total(A) // 2, window_total(A) - window_total(A) // 2),
        "bb": ("< 10", "< 10"),
    })
    result = await run([Brand("AA"), Brand("BB")], trend, ad, cache)
    by = {e.brand: e for e in result.estimates}
    assert by["BB"].k_source == "common" and by["BB"].k == by["AA"].k
    assert any('"BB"' in w and "10 미만" in w for w in result.warnings)
    sept = next(r for r in by["BB"].monthly if r["month"] == "2026-09")
    assert sept["estimated"] == pytest.approx(month_truth(B, "2026-09"), abs=2)


async def test_k_spread_warning_when_sources_disagree(cache):
    trend = FakeTrend({"AA": A, "BB": B})
    ad = FakeSearchAd({
        "aa": (window_total(A), 0),
        "bb": (window_total(B) * 3, 0),  # 검색광고가 B를 3배로 알려 준 경우
    })
    result = await run([Brand("AA"), Brand("BB")], trend, ad, cache)
    assert any("배까지 차이" in w for w in result.warnings)


async def test_no_usable_volume_raises(cache):
    trend = FakeTrend({"AA": A})
    ad = FakeSearchAd({"aa": ("< 10", "< 10")})
    with pytest.raises(ValueError, match="환산할 수 없습니다"):
        await run([Brand("AA")], trend, ad, cache)


async def test_dry_run_makes_no_calls_and_reports_estimate(cache):
    trend, ad = FakeTrend({"AA": A}), FakeSearchAd({})
    result = await run([Brand("AA")], trend, ad, cache, dry_run=True)
    assert result.dry_run and result.estimated_calls == 2
    assert trend.calls == [] and ad.calls == []


async def test_budget_is_enforced_across_both_apis(cache):
    brands = [Brand(f"B{i}") for i in range(12)]
    trend, ad = FakeTrend({b.name: A for b in brands}), FakeSearchAd({})
    with pytest.raises(BudgetExceededError):
        await run(brands, trend, ad, cache, max_calls=3)
    assert trend.calls == [] and ad.calls == []


async def test_end_date_is_clamped_to_yesterday_and_future_start_rejected(cache):
    trend = FakeTrend({"AA": A})
    ad = FakeSearchAd({"aa": (window_total(A), 0)})
    result = await run([Brand("AA")], trend, ad, cache, start_date="2026-10-01", end_date="today")
    months = result.estimates[0].monthly
    assert [r["month"] for r in months] == ["2026-10"] and months[0]["partial"] is False
    assert months[0]["expectedDays"] == 20  # 10월 1~20일
    with pytest.raises(ValueError, match="조회 구간"):
        await run([Brand("AA")], trend, ad, cache, start_date="2026-10-25", end_date="2026-10-30")


async def test_fetch_range_covers_calibration_window_even_for_old_ranges(cache):
    trend = FakeTrend({"AA": A})
    ad = FakeSearchAd({"aa": (window_total(A), 0)})
    await run([Brand("AA")], trend, ad, cache, start_date="2026-01-01", end_date="2026-01-31")
    req = trend.calls[0]
    assert req["startDate"] == "2026-01-01" and req["endDate"] == W1
