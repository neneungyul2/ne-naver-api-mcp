"""실제 네이버 검색광고 API로 문서에 없는 가정을 확인한다.

기본 `uv run pytest`에서는 건너뛴다. 실행: NAVER_LIVE_TEST=1 uv run pytest tests/live/test_searchad.py -v -s
(작업 폴더의 .env 또는 환경변수의 NAVER_SEARCHAD_* 3개와 NCP_APIGW_API_KEY_ID/KEY 필요)

확인할 가정:
- /keywordstool 응답이 keywordList / relKeyword / monthlyPcQcCnt / monthlyMobileQcCnt 형식이다.
- 입력 키워드(공백 제거)가 relKeyword로 그대로 돌아온다.
- 10 미만이 문자열로 오는 형식 ("< 10").
- 같은 키워드에 대해 Data Lab 일 지수 합(어제까지 30일)과 검색광고 월 검색수의 비(k)가 키워드별로
  비슷한 범위인가 (estimate_search_volume의 전제). 값은 -s로 출력해 사람이 본다.
"""
import os

import pytest

from ne_naver_api_mcp.analysis.brand import Brand
from ne_naver_api_mcp.analysis.volume import VolumeInput, estimate_search_volume, parse_keyword_list
from ne_naver_api_mcp.cache import FileCache
from ne_naver_api_mcp.client import NaverApiClient
from ne_naver_api_mcp.config import load_dotenv_if_present, resolve_credentials, resolve_searchad_credentials
from ne_naver_api_mcp.searchad import SearchAdClient

pytestmark = pytest.mark.live

KEYWORDS = ["영어문법", "토익", "수능영어", "초등영어"]


@pytest.fixture
async def clients(tmp_path):
    load_dotenv_if_present()
    creds = resolve_searchad_credentials(os.environ)
    if creds is None:
        pytest.skip("NAVER_SEARCHAD_* 키가 없습니다")
    ad = SearchAdClient(creds)
    hub = NaverApiClient(resolve_credentials(os.environ))
    yield ad, hub, FileCache(tmp_path / "cache", ttl_ms=10**9)
    await ad.aclose()
    await hub.aclose()


async def test_keywordstool_response_shape(clients):
    ad, _, _ = clients
    response = await ad.keyword_tool(KEYWORDS[:2])
    rows = response["keywordList"]
    assert rows and {"relKeyword", "monthlyPcQcCnt", "monthlyMobileQcCnt"} <= set(rows[0])
    stats = parse_keyword_list(response)
    for k in KEYWORDS[:2]:
        assert k in stats, f"입력 키워드 {k}가 relKeyword로 돌아오지 않았습니다"
        print(k, stats[k].to_dict())


async def test_low_volume_representation(clients):
    ad, _, _ = clients
    response = await ad.keyword_tool(["가나다라마바사아자차카타파하zzq"])
    print("rare keyword rows:", response["keywordList"][:3])


async def test_calibration_factor_is_comparable_across_keywords(clients):
    ad, hub, cache = clients
    brands = [Brand(k) for k in KEYWORDS]
    result = await estimate_search_volume(
        VolumeInput(brands=brands, start_date="2025-01-01", end_date="today", confirm=True),
        hub, ad, cache,
    )
    for e in result.estimates:
        print(f"{e.brand}: 월 검색수 {e.searchad.total}, k={e.k} ({e.k_source})")
    print("공통 k:", result.common_k)
    for w in result.warnings:
        print("경고:", w)
    assert result.common_k and result.common_k > 0
