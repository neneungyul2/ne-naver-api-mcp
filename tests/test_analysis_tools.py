"""brand_compare_trend, brand_mentions 도구 (Node analysis-tools 테스트 이식 + baseline/부분 집계)."""
import json
from pathlib import Path

import pytest

from ne_naver_api_mcp.analysis.brand import BrandInput
from mcp.server.mcpserver.exceptions import ToolError
from ne_naver_api_mcp.tools.analysis import register_analysis_tools
from tests.fakes import capture_registrar, make_cache, regex_factory


class Api:
    """검색어 트렌드, 쇼핑, 검색을 모두 흉내 내는 가짜 API (호출을 기록한다)."""

    def __init__(self):
        self.calls: list[str] = []

    async def search_trend(self, req):
        self.calls.append("search_trend")
        groups = req["keywordGroups"]
        return {
            "results": [
                {"title": g["groupName"], "data": [
                    {"period": "2025-01-01", "ratio": 100 / (i + 1)},
                    {"period": "2025-02-01", "ratio": 50 / (i + 1)},
                ]}
                for i, g in enumerate(groups)
            ]
        }

    async def shopping_keywords(self, req):
        self.calls.append("shopping")
        return {"results": []}

    async def search(self, type, params):  # noqa: A002
        self.calls.append(f"search:{type}")
        dated = type == "blog"
        items = [
            {"title": "<b>그래머인사이드</b> 쎄듀 교재", "description": "중등 문법",
             "link": f"https://{type}/1", **({"postdate": "20250312"} if dated else {})},
            {"title": "그래머인사이드 후기 쎄듀", "description": "정리",
             "link": f"https://{type}/2", **({"postdate": "20250401"} if dated else {})},
        ]
        return {"total": 2, "items": items}


class TruncatedApi(Api):
    """total은 250건인데 최근 2건만 담긴 표본."""

    async def search(self, type, params):  # noqa: A002
        r = await super().search(type, params)
        r["total"] = 250
        return r


class BaselineApi(Api):
    async def search(self, type, params):  # noqa: A002
        self.calls.append(params["query"])
        if params["query"] == "교재일반":
            items = [{"title": f"문법 영어 정리 {i}", "description": "", "link": f"https://base/{i}",
                      "postdate": "20250301"} for i in range(4)]
        else:
            items = [
                {"title": "그래머인사이드 문법 쎄듀", "description": "", "link": "https://b/1", "postdate": "20250312"},
                {"title": "그래머인사이드 문법 쎄듀 후기글", "description": "", "link": "https://b/2", "postdate": "20250313"},
            ]
        return {"total": len(items), "items": items}


def setup(api, tmp_path, **kw):
    registrar, server = capture_registrar()
    register_analysis_tools(registrar, api, make_cache(tmp_path), tokenizer_factory=kw.get("factory", regex_factory))
    return server.tools


def brand(name="그래머인사이드", aliases=None):
    return BrandInput(name=name, aliases=aliases or [])


COMPARE = dict(source="search", startDate="2025-01-01", endDate="2025-02-28", timeUnit="month")


async def test_two_tools_are_registered_once(tmp_path):
    registrar, server = capture_registrar()
    register_analysis_tools(registrar, Api(), make_cache(tmp_path))
    assert sorted(server.tools) == ["brand_compare_trend", "brand_mentions"]
    assert all(server.descriptions.values())


async def test_compare_dry_run_makes_no_call_and_returns_limitations(tmp_path):
    api = Api()
    out = json.loads(await setup(api, tmp_path)["brand_compare_trend"](brands=[brand("A"), brand("B")], dryRun=True, **COMPARE))
    assert api.calls == []
    assert out["dryRun"] is True and out["limitations"]


async def test_compare_export_writes_files_and_reports_paths(tmp_path, monkeypatch):
    export_dir = tmp_path / "exp"
    monkeypatch.setenv("NAVER_EXPORT_DIR", str(export_dir))
    out = json.loads(await setup(Api(), tmp_path)["brand_compare_trend"](
        brands=[brand("A"), brand("B")], exportAs="비교", **COMPARE))
    assert out["limitations"]
    assert Path(out["exported"]["xlsxPath"]).exists()
    assert all(Path(p).exists() for p in out["exported"]["csvPaths"])
    assert Path(out["exported"]["xlsxPath"]).resolve().is_relative_to(export_dir.resolve())


async def test_mentions_cafe_without_dates_is_excluded_from_monthly_with_a_warning(tmp_path):
    out = json.loads(await setup(Api(), tmp_path)["brand_mentions"](
        brands=[brand()], sources=["blog", "cafearticle"]))
    assert any("카페글" in w and "월별 집계에서 제외" in w for w in out["warnings"])
    assert any(r["source"] == "blog" and r["month"] == "2025-03" for r in out["monthly"])
    assert not any(r["source"] == "cafearticle" for r in out["monthly"])
    assert out["undated"]["cafearticle"] == 2
    assert any(c["term"] == "쎄듀" and c["total"] >= 2 for c in out["candidates"])
    assert out["limitations"]
    assert out["kept"] == 4


async def test_mentions_dry_run_makes_no_call(tmp_path):
    api = Api()
    out = json.loads(await setup(api, tmp_path)["brand_mentions"](
        brands=[brand()], sources=["blog"], maxPostsPerBrand=300, dryRun=True))
    assert api.calls == [] and out["estimatedCalls"] == 3


async def test_mentions_default_max_posts_is_100(tmp_path):
    out = json.loads(await setup(Api(), tmp_path)["brand_mentions"](brands=[brand()], sources=["blog"], dryRun=True))
    assert out["estimatedCalls"] == 1


async def test_mentions_over_budget_needs_confirm(tmp_path):
    with pytest.raises(ToolError, match="confirm"):
        await setup(Api(), tmp_path)["brand_mentions"](
            brands=[brand("A"), brand("B")], sources=["blog", "cafearticle"],
            maxPostsPerBrand=1000, maxCalls=5)


async def test_mentions_warns_when_the_sample_only_reaches_recent_posts(tmp_path):
    out = json.loads(await setup(TruncatedApi(), tmp_path)["brand_mentions"](brands=[brand()], sources=["blog"]))
    t = out["apiTotals"][0]
    assert (t["collected"], t["oldestDate"], t["truncated"]) == (2, "2025-03-12", True)
    assert any("250" in w and "2025-03-12" in w and "불완전" in w for w in out["warnings"])


async def test_mentions_marks_months_not_comparable_as_partial(tmp_path):
    out = json.loads(await setup(TruncatedApi(), tmp_path)["brand_mentions"](brands=[brand()], sources=["blog"]))
    assert out["comparableFrom"]["blog"] == "2025-03-12"
    rows = {r["month"]: r for r in out["monthly"]}
    assert rows["2025-03"]["partial"] is True and rows["2025-04"]["partial"] is False


async def test_export_failure_keeps_the_analysis_result(tmp_path, monkeypatch):
    blocker = tmp_path / "file.txt"
    blocker.write_text("x", encoding="utf-8")
    monkeypatch.setenv("NAVER_EXPORT_DIR", str(blocker / "sub"))  # 파일 아래에는 폴더를 만들 수 없다
    tools = setup(Api(), tmp_path)
    compare = json.loads(await tools["brand_compare_trend"](
        brands=[brand("A"), brand("B")], exportAs="x", **COMPARE))
    assert len(compare["series"]) == 2 and compare["exportError"]
    assert any("내보내기 실패" in w for w in compare["warnings"]) and "exported" not in compare
    mentions = json.loads(await tools["brand_mentions"](brands=[brand()], sources=["blog"], exportAs="x"))
    assert mentions["kept"] > 0 and any("내보내기 실패" in w for w in mentions["warnings"])


async def test_mentions_validates_brands_before_any_call_even_for_dry_run(tmp_path):
    api = Api()
    aliases = [f"별칭{i}" for i in range(20)]
    with pytest.raises(ToolError, match="최대 20개"):
        await setup(api, tmp_path)["brand_mentions"](brands=[brand("A", aliases)], dryRun=True)
    assert api.calls == []


async def test_mentions_baseline_query_removes_generic_words_and_counts_its_calls(tmp_path):
    api = BaselineApi()
    tools = setup(api, tmp_path)
    kwargs = dict(brands=[brand()], sources=["blog"], baselineQuery="교재일반")
    dry = json.loads(await tools["brand_mentions"](**kwargs, dryRun=True))
    assert dry["estimatedCalls"] == 2 and api.calls == []

    out = json.loads(await tools["brand_mentions"](**kwargs))
    assert "교재일반" in api.calls and out["callsUsed"] == 2
    terms = [c["term"] for c in out["candidates"]]
    assert "쎄듀" in terms and "문법" not in terms
    assert out["baselineCollected"] == 4


async def test_default_tokenizer_uses_the_korean_morphological_analyzer(tmp_path):
    registrar, server = capture_registrar()
    register_analysis_tools(registrar, BaselineApi(), make_cache(tmp_path))  # 기본 토크나이저(kiwi)
    out = json.loads(await server.tools["brand_mentions"](brands=[brand()], sources=["blog"]))
    terms = [c["term"] for c in out["candidates"]]
    assert "쎄듀" in terms
    assert not any(t.startswith("그래머인사이드") for t in terms)
