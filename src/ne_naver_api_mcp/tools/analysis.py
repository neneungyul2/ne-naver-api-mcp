"""분석 도구 2개: brand_compare_trend, brand_mentions (+ xlsx/CSV 내보내기)."""
import asyncio
import json
import math
import os
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field

from ..analysis.brand import Brand, BrandInput, brand_keywords, validate_brands
from ..analysis.budget import DEFAULT_MAX_CALLS, check_budget
from ..analysis.candidates import extract_candidates
from ..analysis.compare_trend import AnalysisApi, CompareInput, CompareResult, compare_brand_trend
from ..analysis.mentions import (
    MentionSource,
    Post,
    collect_posts,
    estimate_mention_calls,
    filter_by_brands,
    monthly_counts,
)
from ..analysis.tokenizer import Tokenizer, default_tokenizer
from ..cache import CallCounter, FileCache, default_cache
from ..export import Sheet, export_sheets
from ..tool_filter import ToolRegistrar
from .descriptions import DESCRIPTIONS

SOURCE_LABEL = {"blog": "블로그", "cafearticle": "카페글", "webkr": "웹문서"}
MENTION_LIMITATIONS = [
    "월별 언급 건수는 검색어당 최대 1,000건 수집 표본에서 계산한 근사치이며 실제 전체 건수가 아닙니다.",
    "동시 언급 브랜드는 단어 공출현으로 만든 후보이며 정확한 브랜드 목록이 아닙니다. 브랜드 여부는 직접 판단하세요.",
]

Brands = Annotated[
    list[BrandInput],
    Field(min_length=1, max_length=30, description="비교할 브랜드 목록 (이름 + 별칭)"),
]
TimeUnit = Annotated[Literal["date", "week", "month"], Field(description="구간 단위")]
MaxCalls = Annotated[int | None, Field(ge=1, description=f"API 호출 상한 (기본 {DEFAULT_MAX_CALLS})")]
Confirm = Annotated[bool | None, Field(description="예상 호출 수가 상한을 넘어도 진행")]
DryRun = Annotated[bool | None, Field(description="호출 없이 예상 호출 수만 계산")]
ExportAs = Annotated[str | None, Field(description="지정하면 xlsx/csv로 저장할 파일 이름(확장자 제외)")]


def _dump(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2)


def _export_dir() -> Path:
    configured = os.environ.get("NAVER_EXPORT_DIR", "").strip()
    return Path(configured) if configured else Path.cwd() / "exports"


def _try_export(sheets: list[Sheet], base_name: str) -> dict:
    """내보내기 실패가 이미 비용을 치른 분석 결과를 버리지 않도록 오류를 값으로 돌려준다."""
    try:
        return {"exported": export_sheets(sheets, _export_dir(), base_name).to_dict()}
    except Exception as e:  # noqa: BLE001 - 파일 시스템/라이브러리 오류를 모두 경고로 바꾼다
        return {"exportError": f"내보내기 실패: {e}"}


def trend_sheets(result: CompareResult) -> list[Sheet]:
    periods = sorted({p.period for s in result.series for p in s.points})
    rows = []
    for period in periods:
        row: list = [period]
        for s in result.series:
            point = next((p for p in s.points if p.period == period), None)
            row.append(round(point.ratio, 4) if point else None)
        rows.append(row)
    return [
        Sheet("트렌드", ["기간", *[s.brand for s in result.series]], rows),
        Sheet("한계", ["안내"], [[t] for t in [*result.limitations, *result.warnings]]),
    ]


def register_analysis_tools(
    registrar: ToolRegistrar,
    api: AnalysisApi | None,
    cache: FileCache | None = None,
    tokenizer_factory: Callable[[Sequence[Brand]], Tokenizer] | None = None,
) -> None:
    def cache_of() -> FileCache:
        return cache if cache is not None else default_cache()

    make_tokenizer = tokenizer_factory or default_tokenizer

    async def brand_compare_trend(
        brands: Brands,
        source: Annotated[
            Literal["search", "shopping"],
            Field(description="search: 검색어 트렌드, shopping: 쇼핑 인사이트(키워드)"),
        ],
        startDate: Annotated[str, Field(description="시작일 (yyyy-mm-dd 또는 'today')")],
        endDate: Annotated[str, Field(description="종료일 (yyyy-mm-dd 또는 'today')")],
        timeUnit: TimeUnit,
        category: Annotated[
            str | None, Field(description="쇼핑 분야 코드 (source가 shopping일 때 필수, find_category로 조회)")
        ] = None,
        anchor: Annotated[str | None, Field(description="기준 브랜드 이름 (생략하면 자동)")] = None,
        device: Annotated[Literal["pc", "mo"] | None, Field(description="search에서만 사용")] = None,
        gender: Annotated[Literal["f", "m"] | None, Field(description="search에서만 사용")] = None,
        ages: Annotated[list[str] | None, Field(description="search에서만 사용 (코드 1~11)")] = None,
        maxCalls: MaxCalls = None,
        confirm: Confirm = None,
        dryRun: DryRun = None,
        exportAs: ExportAs = None,
    ) -> str:
        inp = CompareInput(
            brands=[b.to_brand() for b in brands],
            source=source,
            start_date=startDate,
            end_date=endDate,
            time_unit=timeUnit,
            category=category,
            anchor=anchor,
            device=device,
            gender=gender,
            ages=ages,
            max_calls=maxCalls,
            confirm=bool(confirm),
            dry_run=bool(dryRun),
        )
        result = await compare_brand_trend(inp, api, cache_of())
        out = result.to_dict()
        if exportAs and not result.dry_run:
            ex = _try_export(trend_sheets(result), exportAs)
            if "exportError" in ex:
                out["warnings"] = [*result.warnings, ex["exportError"]]
            out.update(ex)
        return _dump(out)

    async def brand_mentions(
        brands: Brands,
        sources: Annotated[list[MentionSource], Field(min_length=1)] = ("blog", "cafearticle"),  # type: ignore[assignment]
        maxPostsPerBrand: Annotated[
            int,
            Field(ge=1, le=1000, description="검색어당 수집할 최근 글 수 (기본 100, 최대 1000). 최근 언급 경향을 보는 용도입니다."),
        ] = 100,
        queriesPerBrand: Annotated[
            int, Field(ge=1, le=3, description="브랜드당 사용할 검색어 수 (이름, 별칭 순)")
        ] = 1,
        topCandidates: Annotated[int, Field(ge=1, le=200)] = 30,
        baselineQuery: Annotated[
            str | None,
            Field(
                description="해당 카테고리의 일반 검색어 (예: '중등 영어 문법 교재'). 주면 이 검색 결과에서 "
                "흔한 단어(문법, 영어 등)를 동시 언급 후보에서 뺍니다. 호출이 소스당 1회 이상 늘어납니다."
            ),
        ] = None,
        baselinePosts: Annotated[
            int, Field(ge=10, le=300, description="기준 검색에서 수집할 글 수 (기본 100)")
        ] = 100,
        maxCalls: MaxCalls = None,
        confirm: Confirm = None,
        dryRun: DryRun = None,
        exportAs: ExportAs = None,
    ) -> str:
        sources_list: list[MentionSource] = list(sources)
        brand_list = [b.to_brand() for b in brands]
        validate_brands(brand_list)
        baseline_calls = (
            len(sources_list) * math.ceil(baselinePosts / 100) if baselineQuery else 0
        )
        estimated = (
            estimate_mention_calls(brand_list, sources_list, queriesPerBrand, maxPostsPerBrand)
            + baseline_calls
        )
        max_calls = DEFAULT_MAX_CALLS if maxCalls is None else maxCalls
        if dryRun:
            warnings = (
                [f"예상 호출 {estimated}회가 상한 {max_calls}회를 넘습니다. 실행하려면 confirm: true가 필요합니다."]
                if estimated > max_calls
                else []
            )
            return _dump(
                {"dryRun": True, "estimatedCalls": estimated, "warnings": warnings,
                 "limitations": MENTION_LIMITATIONS}
            )
        check_budget(estimated, max_calls, bool(confirm))

        shared_cache, counter = cache_of(), CallCounter()
        seen: set[tuple[str, str]] = set()
        posts: list[Post] = []
        warnings: list[str] = []
        api_totals: list[dict] = []
        for source in sources_list:
            for brand in brand_list:
                for query in brand_keywords(brand)[:queriesPerBrand]:
                    got, total = await collect_posts(
                        api, source, query, maxPostsPerBrand, shared_cache, counter
                    )
                    dates = sorted(p.date for p in got if p.date)
                    oldest = dates[0] if dates else None
                    truncated = total > len(got)
                    entry = {"source": source, "brand": brand.name, "query": query, "total": total,
                             "collected": len(got), "truncated": truncated}
                    if oldest:
                        entry["oldestDate"] = oldest
                    api_totals.append(entry)
                    if truncated and oldest:
                        warnings.append(
                            f'{SOURCE_LABEL[source]} "{brand.name}" 검색어 "{query}": 전체 {total}건 중 최근 '
                            f"{len(got)}건만 수집했습니다 (가장 오래된 글 {oldest}). 그 이전 월의 집계는 불완전합니다."
                        )
                    for p in got:
                        key = (p.source, p.link)
                        if key not in seen:
                            seen.add(key)
                            posts.append(p)

        kept, excluded = filter_by_brands(posts, brand_list)
        monthly, undated = monthly_counts(kept)

        # 표본이 잘린 소스는 브랜드마다 닿는 과거가 다르다. 가장 늦은 시작일 이전(그 달 포함)은 비교할 수 없다.
        comparable_from: dict[str, str] = {}
        for t in api_totals:
            if t["truncated"] and "oldestDate" in t:
                current = comparable_from.get(t["source"])
                if current is None or t["oldestDate"] > current:
                    comparable_from[t["source"]] = t["oldestDate"]
        monthly_rows = [
            {**r, "partial": r["source"] in comparable_from and r["month"] <= comparable_from[r["source"]][:7]}
            for r in monthly
        ]

        baseline: list[Post] = []
        if baselineQuery:
            seen_base: set[tuple[str, str]] = set()
            for source in sources_list:
                got, _ = await collect_posts(api, source, baselineQuery, baselinePosts, shared_cache, counter)
                for p in got:
                    key = (p.source, p.link)
                    if key not in seen_base:
                        seen_base.add(key)
                        baseline.append(p)
        # 형태소 분석은 CPU를 쓰고 모델 로딩에 시간이 걸리므로 스레드에서 돌려 서버가 멈추지 않게 한다
        tokenize = make_tokenizer(brand_list)
        candidates = await asyncio.to_thread(
            lambda: extract_candidates(
                kept, brand_list, top=topCandidates, tokenize=tokenize, baseline=baseline or None
            )
        )

        for source in sources_list:
            mine = [p for p in kept if p.source == source]
            if mine and all(not p.date for p in mine):
                warnings.append(
                    f"{SOURCE_LABEL[source]}은 날짜 정보가 없어 월별 집계에서 제외했습니다. (건수와 후보 분석에는 포함)"
                )

        out = {
            "dryRun": False,
            "monthly": monthly_rows,
            "comparableFrom": comparable_from,
            "undated": undated,
            "apiTotals": api_totals,
            "collected": len(posts),
            "kept": len(kept),
            "excluded": excluded,
            "candidates": [c.to_dict() for c in candidates],
            "baselineCollected": len(baseline),
            "callsUsed": counter.used,
            "cacheHits": counter.hit,
            "estimatedCalls": estimated,
            "warnings": warnings,
            "limitations": MENTION_LIMITATIONS,
        }
        if exportAs:
            sheets = [
                Sheet("월별언급", ["월", "브랜드", "소스", "건수", "부분집계"],
                      [[r["month"], r["brand"], r["source"], r["count"], "Y" if r["partial"] else ""]
                       for r in monthly_rows]),
                Sheet("후보", ["단어", "총빈도", "브랜드별", "예시", "출처"],
                      [[c.term, c.total, "; ".join(f"{b}:{n}" for b, n in c.by_brand.items()),
                        " | ".join(c.examples), ",".join(c.sources)] for c in candidates]),
                Sheet("한계", ["안내"], [[t] for t in [*MENTION_LIMITATIONS, *warnings]]),
            ]
            ex = _try_export(sheets, exportAs)
            if "exportError" in ex:
                out["warnings"] = [*warnings, ex["exportError"]]
            out.update(ex)
        return _dump(out)

    for fn in (brand_compare_trend, brand_mentions):
        registrar.register(fn.__name__, fn, DESCRIPTIONS[fn.__name__])
