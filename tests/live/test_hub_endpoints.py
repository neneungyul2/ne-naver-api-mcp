"""실제 NAVER API HUB를 호출해 코드가 기대는 가정을 확인한다 (호출 약 23회).

기본 `uv run pytest`에서는 건너뛴다. 실행: NAVER_LIVE_TEST=1 uv run pytest tests/live -v
(작업 폴더의 .env 또는 환경변수의 NCP_APIGW_API_KEY_ID / NCP_APIGW_API_KEY 필요)
"""
import os
import re

import pytest

from ne_naver_api_mcp.client import ApiError, NaverApiClient
from ne_naver_api_mcp.config import load_dotenv_if_present, resolve_credentials
from ne_naver_api_mcp.endpoints import UNVERIFIED_OR_INVALID

pytestmark = pytest.mark.live

SEARCH_TYPES = ["webkr", "news", "blog", "cafearticle", "image", "kin", "encyc", "local"]
CATEGORY = "50005951"  # 도서 > 국어/외국어 > 영어 > 문법/독해/작문
RANGE = {"startDate": "2025-01-01", "endDate": "2025-06-30", "timeUnit": "month"}


@pytest.fixture
async def client():
    load_dotenv_if_present()
    c = NaverApiClient(resolve_credentials(os.environ))
    yield c
    await c.aclose()


def kw(name: str) -> dict:
    return {"name": name, "param": [name]}


INACTIVE_MARKER = "활성화되어 있지 않습니다"


@pytest.mark.parametrize("kind", SEARCH_TYPES)
async def test_search_type_is_served_by_hub(client, kind):
    if kind in UNVERIFIED_OR_INVALID:
        with pytest.raises(ApiError):
            await client.search(kind, {"query": "그래머인사이드", "display": 1})
        return
    try:
        res = await client.search(kind, {"query": "그래머인사이드", "display": 1})
    except ApiError as e:
        if INACTIVE_MARKER in str(e):
            # 게이트웨이는 경로를 알지만 사용 중인 Application에 이 API가 추가되지 않았다.
            # 응답 구조는 이 계정으로는 확인할 수 없다 (실패가 아니라 "미확인").
            pytest.skip(f"{kind}: 이 Application에서 비활성 (경로는 HUB에 있음, 응답 구조 미확인)")
        raise
    assert "items" in res, f"{kind}: {list(res)}"


async def test_unknown_search_type_is_404_not_inactive(client):
    """없는 경로(404)와 "Application에 미활성"(401)은 게이트웨이가 다르게 응답한다."""
    with pytest.raises(ApiError) as e:
        await client.search("zzzz-not-a-type", {"query": "a", "display": 1})
    assert "HTTP 404" in str(e.value)
    assert INACTIVE_MARKER not in str(e.value)


async def test_blog_postdate_is_yyyymmdd(client):
    res = await client.search("blog", {"query": "그래머인사이드", "display": 3, "sort": "date"})
    assert res["items"]
    assert all(re.fullmatch(r"[0-9]{8}", i["postdate"]) for i in res["items"])


@pytest.mark.parametrize("kind", ["cafearticle", "webkr"])
async def test_cafe_and_web_items_have_no_date_field(client, kind):
    res = await client.search(kind, {"query": "그래머인사이드", "display": 3, "sort": "date"})
    assert res["items"]
    assert all("postdate" not in i and "date" not in i for i in res["items"])


async def test_search_trend_shape_and_single_group_max_is_100(client):
    res = await client.search_trend(
        {**RANGE, "keywordGroups": [{"groupName": "그래머인사이드", "keywords": ["그래머인사이드", "그래머 인사이드"]}]}
    )
    data = res["results"][0]["data"]
    assert data
    assert all(re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", d["period"]) for d in data)
    assert max(d["ratio"] for d in data) == 100


@pytest.mark.parametrize(
    "method, body",
    [
        ("shopping_category", {"category": [{"name": "영어문법", "param": [CATEGORY]}]}),
        ("shopping_keywords", {"category": CATEGORY, "keyword": [kw("그래머인사이드")]}),
        ("shopping_by_device", {"category": CATEGORY, "device": "mo"}),
        ("shopping_by_gender", {"category": CATEGORY, "gender": "f"}),
        ("shopping_by_age", {"category": CATEGORY, "ages": ["10", "20"]}),
        ("shopping_keyword_by_device", {"category": CATEGORY, "keyword": "그래머인사이드", "device": "mo"}),
        ("shopping_keyword_by_gender", {"category": CATEGORY, "keyword": "그래머인사이드", "gender": "f"}),
        ("shopping_keyword_by_age", {"category": CATEGORY, "keyword": "그래머인사이드", "ages": ["10", "20"]}),
    ],
)
async def test_each_shopping_endpoint_answers(client, method, body):
    res = await getattr(client, method)({**RANGE, **body})
    assert "results" in res


async def test_shopping_keyword_groups_max_5_and_6_is_400(client):
    names = ["그래머인사이드", "천일문", "쎄듀", "오늘의문법", "중학영문법", "능률보카"]
    ok = await client.shopping_keywords({**RANGE, "category": CATEGORY, "keyword": [kw(n) for n in names[:5]]})
    assert len(ok["results"]) == 5
    with pytest.raises(ApiError, match="HTTP 400"):
        await client.shopping_keywords({**RANGE, "category": CATEGORY, "keyword": [kw(n) for n in names]})


async def test_shopping_keyword_param_max_one(client):
    with pytest.raises(ApiError, match="should NOT have more than 1 items"):
        await client.shopping_keywords(
            {**RANGE, "category": CATEGORY, "keyword": [{"name": "그래머인사이드", "param": ["그래머인사이드", "그래머 인사이드"]}]}
        )
