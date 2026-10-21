"""검색, 데이터랩, find_category 도구가 올바른 클라이언트 메서드와 요청을 만드는지 확인한다."""
import json

import pytest
from mcp import Client

from ne_naver_api_mcp.client import ApiError
from ne_naver_api_mcp.dates import resolve_date
from ne_naver_api_mcp.server import create_server
from tests.fakes import RESPONSE, RecordingClient

RANGE = {"startDate": "2025-01-01", "endDate": "2025-06-30", "timeUnit": "month"}
REQ_BASE = dict(RANGE)


@pytest.fixture
def rec() -> RecordingClient:
    return RecordingClient()


async def call(rec, name: str, args: dict):
    async with Client(create_server(rec)) as client:
        return await client.call_tool(name, args)


def text(result) -> str:
    return result.content[0].text


@pytest.mark.parametrize(
    "tool, kind",
    [
        ("search_webkr", "webkr"), ("search_news", "news"), ("search_blog", "blog"),
        ("search_cafearticle", "cafearticle"), ("search_image", "image"), ("search_kin", "kin"),
        ("search_encyc", "encyc"), ("search_local", "local"),
    ],
)
async def test_each_search_tool_calls_its_search_type(rec, tool, kind):
    result = await call(rec, tool, {"query": "그래머인사이드", "display": 3})
    name, search_type, params = rec.calls[0]
    assert (name, search_type) == ("search", kind)
    assert {k: v for k, v in params.items() if v is not None} == {"query": "그래머인사이드", "display": 3}
    assert json.loads(text(result)) == RESPONSE


async def test_search_tool_passes_sort_and_start(rec):
    await call(rec, "search_blog", {"query": "q", "start": 101, "sort": "date"})
    params = rec.calls[0][2]
    assert params["start"] == 101 and params["sort"] == "date"


async def test_results_are_json_text_with_korean_unescaped(rec):
    result = await call(rec, "search_blog", {"query": "q"})
    assert "값" in text(result) and "\\u" not in text(result)


async def test_datalab_search_resolves_today_and_passes_groups(rec):
    await call(rec, "datalab_search", {
        "startDate": "2025-01-01", "endDate": "today", "timeUnit": "month",
        "keywordGroups": [{"groupName": "그래머", "keywords": ["그래머", "grammar"]}],
    })
    name, req = rec.calls[0]
    assert name == "search_trend"
    assert req["endDate"] == resolve_date("today")
    assert req["keywordGroups"] == [{"groupName": "그래머", "keywords": ["그래머", "grammar"]}]


async def test_shopping_category_sends_category_pairs(rec):
    await call(rec, "datalab_shopping_category", {**RANGE, "category": [{"name": "영어", "param": ["50005951"]}]})
    name, req = rec.calls[0]
    assert name == "shopping_category"
    assert req["category"] == [{"name": "영어", "param": ["50005951"]}]


@pytest.mark.parametrize(
    "tool, method, extra, expected_keys",
    [
        ("datalab_shopping_by_device", "shopping_by_device", {"category": "C", "device": "mo"}, {"category", "device"}),
        ("datalab_shopping_by_gender", "shopping_by_gender", {"category": "C", "gender": "f"}, {"category", "gender"}),
        ("datalab_shopping_by_age", "shopping_by_age", {"category": "C", "ages": ["10", "20"]}, {"category", "ages"}),
        ("datalab_shopping_keywords", "shopping_keywords",
         {"category": "C", "keyword": [{"name": "k", "param": ["k"]}]}, {"category", "keyword"}),
        ("datalab_shopping_keyword_by_device", "shopping_keyword_by_device",
         {"category": "C", "keyword": "k", "device": "pc"}, {"category", "keyword", "device"}),
        ("datalab_shopping_keyword_by_gender", "shopping_keyword_by_gender",
         {"category": "C", "keyword": "k", "gender": "m"}, {"category", "keyword", "gender"}),
        ("datalab_shopping_keyword_by_age", "shopping_keyword_by_age",
         {"category": "C", "keyword": "k", "ages": ["30"]}, {"category", "keyword", "ages"}),
    ],
)
async def test_each_shopping_tool_sends_only_its_own_fields(rec, tool, method, extra, expected_keys):
    await call(rec, tool, {**RANGE, **extra})
    name, req = rec.calls[0]
    assert name == method
    assert set(req) == {"startDate", "endDate", "timeUnit"} | expected_keys
    for key in expected_keys:
        assert req[key] == extra[key]


async def test_a_bad_date_is_reported_as_a_tool_error(rec):
    result = await call(rec, "datalab_search", {
        "startDate": "2025/01/01", "endDate": "today", "timeUnit": "month",
        "keywordGroups": [{"groupName": "g", "keywords": ["k"]}],
    })
    assert result.is_error is True
    assert "Invalid date format" in text(result)
    assert rec.calls == []


async def test_api_errors_become_tool_errors_without_hiding_the_message(rec):
    rec.fail = ApiError("[NAVER API HUB] HTTP 400 — https://x\nboom")
    result = await call(rec, "search_blog", {"query": "q"})
    assert result.is_error is True
    assert "HTTP 400" in text(result) and "boom" in text(result)


async def test_find_category_returns_real_categories_as_json(rec):
    result = await call(rec, "find_category", {"query": "도서", "max_results": 3})
    data = json.loads(text(result))
    assert data["total_found"] == 3
    assert data["categories"][0]["levels"]["대분류"] == "도서"
    assert "도서" in text(result)  # 한글이 \uXXXX로 이스케이프되지 않는다
    assert "\\u" not in text(result)
