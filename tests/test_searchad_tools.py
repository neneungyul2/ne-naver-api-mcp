"""검색광고 도구가 키가 있을 때만 등록되고, 올바르게 동작하는지 확인한다."""
import json

import pytest
from mcp import Client

from ne_naver_api_mcp.server import create_server
from tests.fakes import RecordingClient

TOOLS = {"searchad_keyword_volume", "estimate_search_volume"}


class FakeSearchAd:
    def __init__(self):
        self.calls: list[list[str]] = []
        self.closed = False

    async def keyword_tool(self, hints):
        self.calls.append(list(hints))
        rows = [
            {"relKeyword": h, "monthlyPcQcCnt": 1000, "monthlyMobileQcCnt": "< 10", "compIdx": "중간"}
            for h in hints
        ]
        # 연관 키워드 (입력하지 않은 키워드)
        rows += [
            {"relKeyword": "연관a", "monthlyPcQcCnt": 50, "monthlyMobileQcCnt": 100, "compIdx": "낮음"},
            {"relKeyword": "연관b", "monthlyPcQcCnt": 500, "monthlyMobileQcCnt": 700, "compIdx": "높음"},
        ]
        return {"keywordList": rows}

    async def aclose(self):
        self.closed = True


async def tool_names(**kw):
    async with Client(create_server(RecordingClient(), **kw)) as client:
        return {t.name for t in (await client.list_tools()).tools}


async def test_tools_registered_only_with_searchad():
    assert not TOOLS & await tool_names()
    names = await tool_names(searchad=FakeSearchAd())
    assert TOOLS <= names and len(names) == 22


async def test_allow_list_applies_to_searchad_tools():
    assert await tool_names(searchad=FakeSearchAd(), allow={"estimate_search_volume"}) == {"estimate_search_volume"}


async def test_keyword_volume_matches_inputs_and_lists_related(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVER_CACHE_DIR", str(tmp_path / "cache"))
    ad = FakeSearchAd()
    async with Client(create_server(RecordingClient(), searchad=ad)) as client:
        result = await client.call_tool(
            "searchad_keyword_volume",
            {"keywords": ["그래머 인사이드", "그래머인사이드", "없는말"], "includeRelated": True, "relatedTop": 1},
        )
    out = json.loads(result.content[0].text)
    kws = {r["keyword"]: r for r in out["results"]}
    # 공백만 다른 입력은 하나로 합쳐 조회한다
    assert ad.calls == [["그래머인사이드", "없는말"]]
    assert kws["그래머인사이드"]["pc"] == 1000 and kws["그래머인사이드"]["mobile"] is None
    assert kws["그래머인사이드"]["lowVolume"] is True and kws["그래머인사이드"]["totalUpperBound"] == 1009
    assert [r["keyword"] for r in out["related"]] == ["연관b"]  # 검색수 많은 순, relatedTop=1


async def test_keyword_volume_budget_blocks_large_requests(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVER_CACHE_DIR", str(tmp_path / "cache"))
    ad = FakeSearchAd()
    async with Client(create_server(RecordingClient(), searchad=ad)) as client:
        result = await client.call_tool(
            "searchad_keyword_volume", {"keywords": [f"k{i}" for i in range(50)], "maxCalls": 2}
        )
    assert result.is_error and "상한" in result.content[0].text
    assert ad.calls == []


async def test_estimate_dry_run_reports_calls_without_api_use(tmp_path, monkeypatch):
    monkeypatch.setenv("NAVER_CACHE_DIR", str(tmp_path / "cache"))
    rec, ad = RecordingClient(), FakeSearchAd()
    async with Client(create_server(rec, searchad=ad)) as client:
        result = await client.call_tool(
            "estimate_search_volume",
            {"brands": [{"name": "그래머인사이드"}], "startDate": "2026-08-01", "endDate": "2026-09-30", "dryRun": True},
        )
    out = json.loads(result.content[0].text)
    assert out["dryRun"] is True and out["estimatedCalls"] == 2
    assert rec.calls == [] and ad.calls == []


async def test_searchad_client_is_closed_on_shutdown():
    ad = FakeSearchAd()
    async with Client(create_server(RecordingClient(), searchad=ad)) as client:
        await client.list_tools()
    assert ad.closed
