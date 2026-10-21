"""MCP 클라이언트로 서버를 연결해 도구 목록과 입력 스키마를 확인한다."""
import json
import os
import sys

from mcp import Client
from mcp.client.stdio import StdioServerParameters

from ne_naver_api_mcp.server import create_server
from tests.fakes import RecordingClient

SEARCH = ["search_webkr", "search_news", "search_blog", "search_cafearticle", "search_image",
          "search_kin", "search_encyc", "search_local"]
DATALAB = ["datalab_search", "datalab_shopping_category", "datalab_shopping_by_device",
           "datalab_shopping_by_gender", "datalab_shopping_by_age", "datalab_shopping_keywords",
           "datalab_shopping_keyword_by_device", "datalab_shopping_keyword_by_gender",
           "datalab_shopping_keyword_by_age"]
EXPECTED = set(SEARCH + DATALAB + ["find_category", "brand_compare_trend", "brand_mentions"])


async def get_tools() -> dict:
    """서버를 프로세스 안에서 연결해 도구 이름 → 도구 정의를 돌려준다."""
    async with Client(create_server(RecordingClient())) as client:
        return {t.name: t for t in (await client.list_tools()).tools}


def schema(tool) -> dict:
    return tool.input_schema if hasattr(tool, "input_schema") else tool.inputSchema


async def test_all_twenty_tools_are_registered():
    tools = await get_tools()
    assert set(tools) == EXPECTED
    assert len(tools) == 20


async def test_every_tool_has_a_description():
    assert all((t.description or "").strip() for t in (await get_tools()).values())


async def test_search_tool_arguments_match_the_node_version():
    t = (await get_tools())["search_blog"]
    assert {"query", "display", "start", "sort"} <= set(schema(t)["properties"])
    assert schema(t)["required"] == ["query"]


async def test_brand_compare_trend_arguments():
    s = schema((await get_tools())["brand_compare_trend"])
    assert {"brands", "source", "startDate", "endDate", "timeUnit", "category", "anchor",
            "maxCalls", "confirm", "dryRun", "exportAs"} <= set(s["properties"])
    assert {"brands", "source", "startDate", "endDate", "timeUnit"} <= set(s["required"])


async def test_brand_mentions_arguments():
    s = schema((await get_tools())["brand_mentions"])
    assert {"brands", "sources", "maxPostsPerBrand", "queriesPerBrand", "topCandidates",
            "baselineQuery", "baselinePosts", "maxCalls", "confirm", "dryRun", "exportAs"} <= set(s["properties"])
    assert s["required"] == ["brands"]
    assert s["properties"]["maxPostsPerBrand"]["default"] == 100


async def test_find_category_arguments():
    s = schema((await get_tools())["find_category"])
    assert {"query", "max_results"} <= set(s["properties"])


async def test_ages_are_limited_to_the_ten_year_codes():
    s = schema((await get_tools())["datalab_shopping_by_age"])
    dumped = json.dumps(s["properties"]["ages"])
    for code in ["10", "20", "30", "40", "50", "60"]:
        assert f'"{code}"' in dumped


async def test_a_wrong_type_gives_a_readable_error_naming_the_argument():
    async with Client(create_server(RecordingClient())) as client:
        result = await client.call_tool(
            "datalab_shopping_by_age",
            {"startDate": "2025-01-01", "endDate": "2025-02-01", "timeUnit": "month",
             "category": "50005951", "ages": [10]},
        )
    assert result.is_error is True
    assert "ages" in result.content[0].text


async def test_tools_allow_env_limits_the_tools_over_stdio(tmp_path):
    env = dict(os.environ)
    env.update(NCP_APIGW_API_KEY_ID="dummyid", NCP_APIGW_API_KEY="dummysecret",
               NAVER_TOOLS_ALLOW="find_category,brand_mentions")
    params = StdioServerParameters(
        command=sys.executable,
        args=["-c", "from ne_naver_api_mcp.server import main; main()"],
        env=env, cwd=str(tmp_path),
    )
    async with Client(params) as client:
        names = sorted(t.name for t in (await client.list_tools()).tools)
    assert names == ["brand_mentions", "find_category"]
