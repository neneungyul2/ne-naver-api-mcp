"""실제 NAVER API HUB 응답을 녹화한 샘플(tests/fixtures)로 분석 코드를 검증한다.

샘플은 `uv run python scripts/record_fixtures.py`로 다시 녹화할 수 있다. 네트워크는 쓰지 않는다.
"""
import json
import re
from pathlib import Path

import pytest

from ne_naver_api_mcp.analysis.brand import Brand
from ne_naver_api_mcp.analysis.compare_trend import CompareInput, compare_brand_trend
from ne_naver_api_mcp.analysis.mentions import collect_posts, filter_by_brands, normalize_post
from ne_naver_api_mcp.cache import CallCounter, FileCache
from ne_naver_api_mcp.client import ApiError

FIXTURES = Path(__file__).parent / "fixtures"


def fx(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


BLOG, CAFE, WEB = fx("search-blog"), fx("search-cafearticle"), fx("search-webkr")
TREND, SHOPPING, PARAM_LIMIT = fx("search-trend"), fx("shopping-keywords"), fx("shopping-param-limit-error")


@pytest.fixture
def cache(tmp_path) -> FileCache:
    return FileCache(tmp_path / "cache", ttl_ms=10**9)


def test_search_response_structure_and_item_fields():
    for res in (BLOG, CAFE, WEB):
        assert list(res) == ["lastBuildDate", "total", "start", "display", "items"]
        assert isinstance(res["total"], int)
    assert all(re.fullmatch(r"[0-9]{8}", i["postdate"]) for i in BLOG["items"])
    assert all("postdate" not in i and "date" not in i for i in CAFE["items"])
    assert all("postdate" not in i and "date" not in i for i in WEB["items"])


def test_real_blog_items_normalize_to_iso_dates_without_tags():
    posts = [normalize_post("blog", i) for i in BLOG["items"]]
    assert all(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", p.date) for p in posts)
    assert all("<" not in p.title + p.description and ">" not in p.title + p.description for p in posts)


def test_cafe_and_web_items_have_no_date():
    assert all(normalize_post("cafearticle", i).date is None for i in CAFE["items"])
    assert all(normalize_post("webkr", i).date is None for i in WEB["items"])


async def test_collecting_and_brand_filtering_real_responses_catches_bold_wrapped_names(cache):
    class Api:
        async def search(self, type, params):  # noqa: A002
            return {"blog": BLOG, "cafearticle": CAFE, "webkr": WEB}[type]

    posts, total = await collect_posts(Api(), "blog", "그래머인사이드", 100, cache, CallCounter())
    assert len(posts) == len(BLOG["items"]) and total == BLOG["total"]
    kept, _ = filter_by_brands(posts, [Brand("그래머인사이드", ("그래머 인사이드",))])
    assert len(kept) >= 1


async def test_a_recorded_search_trend_response_gives_a_single_brand_peak_of_100(cache):
    class Api:
        async def search_trend(self, req):
            return TREND

    res = await compare_brand_trend(
        CompareInput(brands=[Brand("그래머인사이드", ("그래머 인사이드",))], source="search",
                     start_date="2025-01-01", end_date="2025-06-30", time_unit="month"),
        Api(), cache,
    )
    assert res.calls_used == 1
    assert len(res.series[0].points) == len(TREND["results"][0]["data"])
    assert max(p.ratio for p in res.series[0].points) == 100


class StrictShoppingApi:
    """서버의 실제 제한(녹화된 400)을 흉내 낸다: 그룹 5개 초과 또는 param 2개 이상이면 거절한다."""

    def __init__(self):
        self.calls: list[dict] = []

    async def shopping_keywords(self, req):
        self.calls.append(req)
        if len(req["keyword"]) > 5 or any(len(k["param"]) > 1 for k in req["keyword"]):
            raise ApiError(PARAM_LIMIT["message"])
        return SHOPPING


def shopping_input(brands: list[Brand]) -> CompareInput:
    return CompareInput(brands=brands, source="shopping", category="50005951",
                        start_date="2024-01-01", end_date="2026-09-30", time_unit="month")


async def test_shopping_requests_respect_the_real_server_limits_even_with_aliases(cache):
    api = StrictShoppingApi()
    names = [r["title"] for r in SHOPPING["results"]]
    res = await compare_brand_trend(
        shopping_input([Brand(names[0], ("별칭1", "별칭2")), Brand(names[1], ("별칭3",))]), api, cache
    )
    assert api.calls and len(res.series) == 2


async def test_a_keyword_with_no_data_in_the_recorded_response_warns_instead_of_failing(cache):
    empty = next(r for r in SHOPPING["results"] if not r["data"])
    res = await compare_brand_trend(
        shopping_input([Brand(r["title"]) for r in SHOPPING["results"]]), StrictShoppingApi(), cache
    )
    assert any(empty["title"] in w and "데이터 없음" in w for w in res.warnings)


async def test_server_error_messages_pass_through_and_never_contain_the_key(cache, monkeypatch):
    monkeypatch.setenv("NCP_APIGW_API_KEY", "SECRET-KEY-123")

    class Api:
        async def shopping_keywords(self, req):
            raise ApiError(PARAM_LIMIT["message"])

    with pytest.raises(ApiError) as e:
        await compare_brand_trend(shopping_input([Brand("A")]), Api(), cache)
    assert "should NOT have more than 1 items" in str(e.value)
    assert "SECRET-KEY-123" not in str(e.value)
