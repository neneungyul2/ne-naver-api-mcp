"""검색광고 도구 2개: searchad_keyword_volume, estimate_search_volume (+ xlsx/CSV 내보내기).

NAVER_SEARCHAD_* 키가 설정된 경우에만 등록된다.
"""
import json
import math
from typing import Annotated

from pydantic import Field

from ..analysis.budget import DEFAULT_MAX_CALLS, check_budget
from ..analysis.compare_trend import AnalysisApi
from ..analysis.volume import (
    VolumeInput,
    VolumeResult,
    estimate_search_volume as run_estimate,
    parse_keyword_list,
)
from ..cache import CallCounter, FileCache, cached_call, default_cache
from ..export import Sheet
from ..searchad import MAX_HINTS_PER_CALL, SearchAdClient, normalize_hint
from ..tool_filter import ToolRegistrar
from .analysis import Brands, Confirm, DryRun, ExportAs, MaxCalls, _try_export
from .descriptions import DESCRIPTIONS

MAX_KEYWORDS = 50


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def volume_sheets(result: VolumeResult) -> list[Sheet]:
    months = sorted({r["month"] for e in result.estimates for r in e.monthly})
    rows = []
    for month in months:
        row: list = [month]
        for e in result.estimates:
            cell = next((r for r in e.monthly if r["month"] == month), None)
            row.append(cell["estimated"] if cell else None)
        rows.append(row)
    return [
        Sheet("월별추정검색량", ["월", *[e.brand for e in result.estimates]], rows),
        Sheet(
            "환산",
            ["브랜드", "검색광고 월 검색수", "10 미만 포함", "환산 계수 k", "k 출처", "기준구간 지수합", "기준구간 일수"],
            [
                [e.brand, e.searchad.total, "Y" if e.searchad.low else "", e.k, e.k_source,
                 round(e.window_ratio_sum, 4), e.window_days_present]
                for e in result.estimates
            ],
        ),
        Sheet("한계", ["안내"], [[t] for t in [*result.limitations, *result.warnings]]),
    ]


def register_searchad_tools(
    registrar: ToolRegistrar,
    trend_api: AnalysisApi | None,
    searchad: SearchAdClient | None,
    cache: FileCache | None = None,
) -> None:
    def cache_of() -> FileCache:
        return cache if cache is not None else default_cache()

    async def searchad_keyword_volume(
        keywords: Annotated[
            list[str],
            Field(min_length=1, max_length=MAX_KEYWORDS, description="월 검색수를 조회할 키워드 목록"),
        ],
        includeRelated: Annotated[
            bool, Field(description="True면 연관 키워드(검색수 많은 순)도 함께 돌려줍니다")
        ] = False,
        relatedTop: Annotated[int, Field(ge=1, le=200, description="연관 키워드 최대 개수 (기본 30)")] = 30,
        maxCalls: MaxCalls = None,
        confirm: Confirm = None,
        exportAs: ExportAs = None,
    ) -> str:
        assert searchad is not None
        wanted = list(dict.fromkeys(normalize_hint(k).lower() for k in keywords if normalize_hint(k)))
        if not wanted:
            raise ValueError("키워드가 비어 있습니다.")
        estimated = math.ceil(len(wanted) / MAX_HINTS_PER_CALL)
        check_budget(estimated, DEFAULT_MAX_CALLS if maxCalls is None else maxCalls, bool(confirm))
        shared, counter = cache_of(), CallCounter()
        found: dict = {}
        related: dict = {}
        for i in range(0, len(wanted), MAX_HINTS_PER_CALL):
            batch = wanted[i : i + MAX_HINTS_PER_CALL]
            response = await cached_call(
                shared, counter, "searchadKeywordTool", {"hints": batch},
                lambda b=batch: searchad.keyword_tool(b),
            )
            for key, vol in parse_keyword_list(response).items():
                (found if key in wanted else related).setdefault(key, vol)
        results = [
            found[k].to_dict() if k in found else {"keyword": k, "found": False} for k in wanted
        ]
        out: dict = {
            "window": "최근 한 달 (검색광고 keywordstool)",
            "results": results,
            "callsUsed": counter.used,
            "cacheHits": counter.hit,
            "notes": [
                "10 미만은 숫자 대신 '< 10'으로만 제공되어 값을 null로 두고 lowVolume을 true로 표시합니다.",
                "공백은 제거해 조회합니다 (검색광고는 띄어쓰기를 구분하지 않습니다).",
            ],
        }
        if includeRelated:
            top = sorted(related.values(), key=lambda v: -v.total)[:relatedTop]
            out["related"] = [v.to_dict() for v in top]
        if exportAs:
            rows = [
                [r["keyword"], r.get("pc"), r.get("mobile"), r.get("total"), r.get("lowVolume"), r.get("compIdx")]
                for r in results if r.get("found", True)
            ]
            sheets = [Sheet("검색수", ["키워드", "PC", "모바일", "합계", "10미만 포함", "경쟁정도"], rows)]
            if includeRelated:
                sheets.append(
                    Sheet("연관키워드", ["키워드", "PC", "모바일", "합계", "경쟁정도"],
                          [[r["keyword"], r["pc"], r["mobile"], r["total"], r["compIdx"]] for r in out["related"]])
                )
            out.update(_try_export(sheets, exportAs))
        return _dump(out)

    async def estimate_search_volume(
        brands: Brands,
        startDate: Annotated[str, Field(description="시작일 (yyyy-mm-dd 또는 'today')")],
        endDate: Annotated[str, Field(description="종료일 (yyyy-mm-dd 또는 'today', 어제까지 반영)")],
        maxCalls: MaxCalls = None,
        confirm: Confirm = None,
        dryRun: DryRun = None,
        exportAs: ExportAs = None,
    ) -> str:
        assert searchad is not None and trend_api is not None
        inp = VolumeInput(
            brands=[b.to_brand() for b in brands],
            start_date=startDate,
            end_date=endDate,
            max_calls=maxCalls,
            confirm=bool(confirm),
            dry_run=bool(dryRun),
        )
        result = await run_estimate(inp, trend_api, searchad, cache_of())
        out = result.to_dict()
        if exportAs and not result.dry_run:
            ex = _try_export(volume_sheets(result), exportAs)
            if "exportError" in ex:
                out["warnings"] = [*result.warnings, ex["exportError"]]
            out.update(ex)
        return _dump(out)

    registrar.register("searchad_keyword_volume", searchad_keyword_volume, DESCRIPTIONS["searchad_keyword_volume"])
    registrar.register("estimate_search_volume", estimate_search_volume, DESCRIPTIONS["estimate_search_volume"])
