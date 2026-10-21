import json

import pytest

from ne_naver_api_mcp.analysis.brand import Brand
from ne_naver_api_mcp.analysis.budget import BudgetExceededError
from ne_naver_api_mcp.analysis.compare_trend import CompareInput, compare_brand_trend
from ne_naver_api_mcp.cache import CallCounter, FileCache

PERIODS = ["2025-01-01", "2025-02-01"]


def brands(*names: str) -> list[Brand]:
    return [Brand(n) for n in names]


@pytest.fixture
def cache(tmp_path) -> FileCache:
    return FileCache(tmp_path / "cache", ttl_ms=10**9)


def inp(**over) -> CompareInput:
    base = dict(
        brands=[],
        source="search",
        start_date="2025-01-01",
        end_date="2025-02-28",
        time_unit="month",
    )
    base.update(over)
    return CompareInput(**base)


def respond(groups: list[str], volumes: list[list[float]]) -> dict:
    """요청 안 최댓값을 100으로 정규화해 돌려주는 Data Lab 흉내."""
    peak = max(v for vol in volumes for v in vol)
    return {
        "results": [
            {
                "title": g,
                "data": [
                    {"period": PERIODS[i], "ratio": (v / peak * 100) if peak else 0}
                    for i, v in enumerate(vol)
                ],
            }
            for g, vol in zip(groups, volumes)
        ]
    }


class FakeApi:
    """world[브랜드 이름] = 실제 검색량. 검색어 트렌드와 쇼핑 모두 이름으로 조회한다."""

    def __init__(self, world: dict[str, list[float]]):
        self.world = world
        self.calls: list[dict] = []

    async def search_trend(self, req: dict) -> dict:
        groups = [g["groupName"] for g in req["keywordGroups"]]
        self.calls.append({"kind": "search", "groups": groups, "req": req})
        return respond(groups, [self.world[g] for g in groups])

    async def shopping_keywords(self, req: dict) -> dict:
        groups = [k["name"] for k in req["keyword"]]
        self.calls.append({"kind": "shopping", "groups": groups, "req": req})
        return respond(groups, [self.world[g] for g in groups])

    async def search(self, type: str, params: dict) -> dict:
        raise AssertionError("unused")


class KeywordApi:
    """쇼핑 인사이트처럼 키워드(param[0])로 데이터를 찾는 가짜 API."""

    def __init__(self, world_by_keyword: dict[str, list[float]]):
        self.world = world_by_keyword
        self.calls: list[list[tuple[str, str]]] = []

    async def search_trend(self, req: dict) -> dict:
        raise AssertionError("unused")

    async def search(self, type: str, params: dict) -> dict:
        raise AssertionError("unused")

    async def shopping_keywords(self, req: dict) -> dict:
        self.calls.append([(k["name"], k["param"][0]) for k in req["keyword"]])
        vols = [self.world.get(k["param"][0], [0, 0]) for k in req["keyword"]]
        return respond([k["name"] for k in req["keyword"]], vols)


def ratios(res, name: str) -> list[float]:
    return [p.ratio for p in next(s for s in res.series if s.brand == name).points]


WORLD6 = {"A": [100, 100], "B": [50, 50], "C": [200, 200], "D": [20, 20], "E": [400, 400], "F": [10, 10]}
WORLD2 = {"A": [10000, 10000], "B": [5000, 5000], "C": [100, 100], "D": [1, 1], "E": [50, 50], "F": [2, 2]}
SIX = brands("A", "B", "C", "D", "E", "F")


async def test_six_brands_fix_anchor_A_in_two_calls_and_share_one_scale(cache):
    api = FakeApi(WORLD6)
    res = await compare_brand_trend(inp(brands=SIX), api, cache)
    assert [c["groups"] for c in api.calls] == [["A", "B", "C", "D", "E"], ["A", "F"]]
    assert res.calls_used == 2
    assert res.anchor == "A" and res.reanchored is False
    assert ratios(res, "F")[0] == pytest.approx(2.5)
    assert ratios(res, "E")[0] == pytest.approx(100)
    assert res.limitations


async def test_keyword_groups_use_name_plus_aliases(cache):
    api = FakeApi({"A": [1, 1]})
    await compare_brand_trend(inp(brands=[Brand("A", ("에이", "A"))]), api, cache)
    assert api.calls[0]["req"]["keywordGroups"] == [{"groupName": "A", "keywords": ["A", "에이"]}]
    assert len(api.calls) == 1


async def test_dry_run_only_estimates(cache):
    api = FakeApi(WORLD6)
    res = await compare_brand_trend(inp(brands=SIX, dry_run=True), api, cache)
    assert api.calls == []
    assert res.estimated_calls == 2 and res.dry_run is True


async def test_over_budget_raises_unless_confirmed(cache, tmp_path):
    kwargs = dict(brands=SIX, max_calls=1)
    with pytest.raises(BudgetExceededError):
        await compare_brand_trend(inp(**kwargs), FakeApi(WORLD6), cache)
    res = await compare_brand_trend(inp(**kwargs, confirm=True), FakeApi(WORLD6), cache)
    assert res.calls_used == 2


async def test_same_request_again_uses_the_cache(cache):
    await compare_brand_trend(inp(brands=SIX), FakeApi(WORLD6), cache)
    api2 = FakeApi(WORLD6)
    res = await compare_brand_trend(inp(brands=SIX), api2, cache)
    assert api2.calls == []
    assert res.calls_used == 0 and res.cache_hits == 2


async def test_low_precision_with_several_batches_reanchors_once_on_the_median_brand(cache):
    api = FakeApi(WORLD2)
    res = await compare_brand_trend(inp(brands=SIX), api, cache)
    assert res.reanchored is True and res.anchor == "E"
    assert len(api.calls) == 4
    assert api.calls[2]["groups"] == ["E", "A", "B", "C", "F"]
    assert api.calls[3]["groups"] == ["E", "D"]
    assert res.calls_used == 4
    assert any("D" in w for w in res.warnings)


async def test_explicit_anchor_is_never_swapped_only_warned(cache):
    api = FakeApi(WORLD2)
    res = await compare_brand_trend(inp(brands=SIX, anchor="A"), api, cache)
    assert res.reanchored is False and len(api.calls) == 2
    assert any("D" in w and "정밀도" in w for w in res.warnings)


async def test_single_batch_never_reanchors(cache):
    api = FakeApi({"X": [10000, 10000], "Y": [1, 1], "Z": [100, 100]})
    res = await compare_brand_trend(inp(brands=brands("X", "Y", "Z")), api, cache)
    assert res.reanchored is False and len(api.calls) == 1
    assert any("Y" in w for w in res.warnings)


async def test_shopping_needs_category_and_sends_one_param_per_group(cache):
    api = FakeApi({"A": [100, 100], "B": [50, 50]})
    with pytest.raises(ValueError, match="category"):
        await compare_brand_trend(inp(source="shopping", brands=brands("A")), api, cache)
    res = await compare_brand_trend(
        inp(source="shopping", category="CAT1", brands=[Brand("A", ("에이",)), Brand("B")]),
        api,
        cache,
    )
    call = api.calls[0]
    assert call["kind"] == "shopping"
    assert call["req"]["category"] == "CAT1"
    # 실제 HUB는 키워드 그룹당 param을 1개만 허용한다 (2026-10-19 확인)
    assert call["req"]["keyword"][0] == {"name": "A", "param": ["A"]}
    assert any("A" in w and "별칭" in w for w in res.warnings)


async def test_shopping_rejects_device_filter(cache):
    with pytest.raises(ValueError, match="device"):
        await compare_brand_trend(
            inp(source="shopping", category="CAT1", device="pc", brands=brands("A")),
            FakeApi({"A": [1, 1]}),
            cache,
        )


async def test_shopping_brand_with_all_zero_data_is_a_warning_not_an_error(cache):
    api = FakeApi({"A": [100, 100], "B": [0, 0]})
    res = await compare_brand_trend(
        inp(source="shopping", category="CAT1", brands=brands("A", "B")), api, cache
    )
    assert any("B" in w and "데이터 없음" in w for w in res.warnings)


async def test_duplicate_brand_names_are_rejected(cache):
    with pytest.raises(ValueError, match="중복"):
        await compare_brand_trend(inp(brands=brands("A", "A")), FakeApi({"A": [1, 1]}), cache)


async def test_result_never_contains_environment_secrets(cache, monkeypatch):
    monkeypatch.setenv("NCP_APIGW_API_KEY", "SECRET-KEY-123")
    res = await compare_brand_trend(
        inp(brands=brands("A", "B")),
        FakeApi({"A": [100, 100], "B": [50, 50]}),
        cache,
        CallCounter(),
    )
    assert "SECRET-KEY-123" not in json.dumps(res.to_dict(), ensure_ascii=False)


async def test_first_brand_without_data_is_fine_when_everything_fits_one_call(cache):
    res = await compare_brand_trend(
        inp(brands=brands("A", "B")), FakeApi({"A": [0, 0], "B": [10, 20]}), cache
    )
    assert ratios(res, "B") == [50, 100]
    assert any("A" in w and "데이터 없음" in w for w in res.warnings)


async def test_empty_anchor_with_several_batches_falls_back_to_the_biggest_brand(cache):
    world = {"A": [0, 0], "B": [100, 100], "C": [50, 50], "D": [20, 20], "E": [10, 10], "F": [5, 5]}
    res = await compare_brand_trend(inp(brands=SIX), FakeApi(world), cache)
    assert res.anchor == "B"
    assert ratios(res, "F")[0] == pytest.approx(5)
    assert any("A" in w and "기준" in w for w in res.warnings)


async def test_reanchor_never_picks_a_brand_without_data(cache):
    world = {"A": [10000, 10000], "B": [0, 0], "C": [0, 0], "D": [0, 0], "E": [50, 50], "F": [2, 2]}
    res = await compare_brand_trend(inp(brands=SIX), FakeApi(world), cache)
    assert res.reanchored is True and res.anchor == "E"
    assert any("B" in w and "데이터 없음" in w for w in res.warnings)


async def test_confirm_does_not_let_reanchoring_exceed_the_approved_calls(cache):
    api = FakeApi(WORLD2)
    res = await compare_brand_trend(inp(brands=SIX, max_calls=1, confirm=True), api, cache)
    assert res.reanchored is False
    assert res.calls_used == 2 and res.estimated_calls == 2 and res.estimated_calls_max == 4
    assert any("예산" in w for w in res.warnings)


async def test_a_tiny_anchor_in_a_later_batch_warns_about_that_batch(cache):
    world = {n: [100, 100] for n in "ABCDE"} | {"F": [1e6, 1e6]}
    res = await compare_brand_trend(inp(brands=SIX, anchor="A"), FakeApi(world), cache)
    assert any("F" in w and "정밀도" in w for w in res.warnings)


async def test_validation_runs_before_any_call_even_for_dry_run(cache):
    aliases = tuple(f"별칭{i}" for i in range(20))
    with pytest.raises(ValueError, match="최대 20개"):
        await compare_brand_trend(
            inp(brands=[Brand("A", aliases)], dry_run=True), FakeApi({"A": [1, 1]}), cache
        )
    with pytest.raises(ValueError, match="비어"):
        await compare_brand_trend(
            inp(brands=[Brand(" ")], dry_run=True), FakeApi({"A": [1, 1]}), cache
        )


SHOP = dict(source="shopping", category="CAT1")
BIG_B = Brand("천일문 중등 그래머", ("천일문", "천일문중등그래머"))


async def test_shopping_tries_aliases_in_order_when_the_name_has_no_data(cache):
    api = KeywordApi({"A": [100, 100], "천일문": [40, 40]})
    res = await compare_brand_trend(inp(**SHOP, brands=[Brand("A"), BIG_B]), api, cache)
    assert len(api.calls) == 2
    assert api.calls[1] == [("A", "A"), ("천일문 중등 그래머", "천일문")]
    assert ratios(res, "천일문 중등 그래머")[0] == pytest.approx(40)
    assert any("천일문" in w and "별칭으로 조회" in w for w in res.warnings)
    assert res.calls_used == 2


async def test_shopping_goes_on_to_the_next_alias_and_stops_after_two_tries(cache):
    api = KeywordApi({"A": [100, 100], "천일문중등그래머": [30, 30]})
    res = await compare_brand_trend(inp(**SHOP, brands=[Brand("A"), BIG_B]), api, cache)
    assert len(api.calls) == 3
    assert ratios(res, "천일문 중등 그래머")[0] == pytest.approx(30)

    api2 = KeywordApi({"A": [100, 100]})
    res2 = await compare_brand_trend(inp(**SHOP, brands=[Brand("A"), BIG_B]), api2, FileCache(cache.directory / "x", 10**9))
    assert len(api2.calls) == 3
    assert any("천일문 중등 그래머" in w and "데이터 없음" in w for w in res2.warnings)


async def test_shopping_does_not_try_aliases_when_every_brand_has_data(cache):
    api = KeywordApi({"A": [100, 100], "천일문 중등 그래머": [50, 50], "천일문": [99, 99]})
    res = await compare_brand_trend(inp(**SHOP, brands=[Brand("A"), BIG_B]), api, cache)
    assert len(api.calls) == 1
    assert ratios(res, "천일문 중등 그래머")[0] == pytest.approx(50)


async def test_shopping_alias_retries_stay_within_the_approved_budget(cache):
    api = KeywordApi({"A": [100, 100], "천일문": [40, 40]})
    res = await compare_brand_trend(
        inp(**SHOP, brands=[Brand("A"), BIG_B], max_calls=1), api, cache
    )
    assert len(api.calls) == 1
    assert any("별칭" in w and "예산" in w for w in res.warnings)
    assert res.estimated_calls_max >= 3


async def test_to_dict_uses_the_node_compatible_camel_case_keys(cache):
    res = await compare_brand_trend(
        inp(brands=brands("A", "B")), FakeApi({"A": [100, 100], "B": [50, 50]}), cache
    )
    d = res.to_dict()
    assert set(d) == {
        "source", "anchor", "reanchored", "series", "callsUsed", "cacheHits",
        "estimatedCalls", "estimatedCallsMax", "warnings", "limitations", "dryRun",
    }
    assert set(d["series"][0]) == {"brand", "points", "lowPrecision"}
    assert set(d["series"][0]["points"][0]) == {"period", "ratio"}
