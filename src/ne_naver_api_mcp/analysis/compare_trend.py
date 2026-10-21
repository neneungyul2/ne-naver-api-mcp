"""브랜드 비교 트렌드: 여러 브랜드의 검색어 트렌드/쇼핑 클릭 추이를 한 척도의 상대 지수로 비교한다."""
import math
from dataclasses import dataclass, field
from typing import Literal, Protocol

from ..cache import CallCounter, FileCache, cached_call
from ..dates import resolve_date_range
from .brand import Brand, brand_keywords, validate_brands
from .budget import DEFAULT_MAX_CALLS, check_budget
from .rescale import (
    AnchorError,
    BatchResult,
    ScaledSeries,
    SeriesPoint,
    estimate_trend_calls,
    pick_median_anchor,
    plan_batches,
    rescale,
)


class AnalysisApi(Protocol):
    """NaverApiClient가 구조적으로 만족하는 최소 API 표면."""

    async def search_trend(self, req: dict) -> dict: ...

    async def shopping_keywords(self, req: dict) -> dict: ...

    async def search(self, type: str, params: dict) -> dict: ...  # noqa: A002


SEARCH_SLOTS_PER_CALL = 5  # 검색어 트렌드 그룹 수 (HUB 문서: 최대 5개)
SHOPPING_SLOTS_PER_CALL = 5  # 쇼핑 인사이트 키워드 그룹 수 (실제 호출로 확인: 6개는 400)
SHOPPING_KEYWORDS_PER_BRAND = 1  # 쇼핑은 키워드 그룹당 param 1개만 받는다 (확인됨)
SHOPPING_ALIAS_TRIES = 2  # 이름에 데이터가 없을 때 쇼핑에서 별칭을 순서대로 시도하는 최대 횟수

LIMITATIONS = [
    "모든 값은 실제 검색/클릭 횟수가 아니라 공통 기준 대비 상대 지수입니다.",
    "첫 묶음의 최댓값을 100으로 한 척도로 환산하므로 값이 100을 넘을 수 있습니다.",
    "배치마다 기준 브랜드 값으로 환산한 값이라 작은 브랜드는 값이 거칠 수 있습니다.",
]


@dataclass
class CompareInput:
    brands: list[Brand]
    source: Literal["search", "shopping"]
    start_date: str
    end_date: str
    time_unit: Literal["date", "week", "month"]
    category: str | None = None
    anchor: str | None = None
    device: str | None = None
    gender: str | None = None
    ages: list[str] | None = None
    max_calls: int | None = None
    confirm: bool = False
    dry_run: bool = False


@dataclass
class CompareResult:
    source: str
    anchor: str
    reanchored: bool
    series: list[ScaledSeries]
    calls_used: int
    cache_hits: int
    estimated_calls: int  # 기준 브랜드 변경 없이 한 번 실행할 때
    estimated_calls_max: int  # 기준 재선택/교체, 별칭 시도까지 일어나는 최악의 경우
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=lambda: list(LIMITATIONS))
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "anchor": self.anchor,
            "reanchored": self.reanchored,
            "series": [
                {
                    "brand": s.brand,
                    "points": [{"period": p.period, "ratio": p.ratio} for p in s.points],
                    "lowPrecision": s.low_precision,
                }
                for s in self.series
            ],
            "callsUsed": self.calls_used,
            "cacheHits": self.cache_hits,
            "estimatedCalls": self.estimated_calls,
            "estimatedCallsMax": self.estimated_calls_max,
            "warnings": self.warnings,
            "limitations": self.limitations,
            "dryRun": self.dry_run,
        }


def _validate(inp: CompareInput) -> None:
    if not inp.brands:
        raise ValueError("brands가 비어 있습니다.")
    validate_brands(inp.brands)
    names = [b.name for b in inp.brands]
    if len(set(names)) != len(names):
        raise ValueError("브랜드 이름이 중복되었습니다. 이름은 서로 달라야 합니다.")
    if inp.source == "shopping":
        if not inp.category:
            raise ValueError("source가 shopping이면 category(쇼핑 분야 코드)가 필요합니다.")
        if inp.device or inp.gender or inp.ages:
            raise ValueError("쇼핑 인사이트 비교는 device/gender/ages 필터를 지원하지 않습니다.")
    if inp.anchor and inp.anchor not in names:
        raise ValueError(f'anchor "{inp.anchor}"가 브랜드 목록에 없습니다.')


def _sum(points: list[SeriesPoint]) -> float:
    return sum(p.ratio for p in points)


def _peak(series: ScaledSeries) -> float:
    return max((p.ratio for p in series.points), default=0.0)


async def compare_brand_trend(
    inp: CompareInput,
    api: AnalysisApi,
    cache: FileCache,
    counter: CallCounter | None = None,
) -> CompareResult:
    _validate(inp)
    counter = counter or CallCounter()
    start_used, start_hit = counter.used, counter.hit

    start_date, end_date = resolve_date_range(inp.start_date, inp.end_date)
    shopping = inp.source == "shopping"
    slots = SHOPPING_SLOTS_PER_CALL if shopping else SEARCH_SLOTS_PER_CALL
    by_name = {b.name: b for b in inp.brands}
    names = [b.name for b in inp.brands]
    estimated = estimate_trend_calls(len(names), slots)
    alias_brands = (
        [b for b in inp.brands if len(brand_keywords(b)) > SHOPPING_KEYWORDS_PER_BRAND]
        if shopping
        else []
    )
    alias_rounds = (
        min(
            SHOPPING_ALIAS_TRIES,
            max(len(brand_keywords(b)) - SHOPPING_KEYWORDS_PER_BRAND for b in alias_brands),
        )
        if alias_brands
        else 0
    )
    alias_calls = math.ceil(len(alias_brands) / (slots - 1)) * alias_rounds if alias_brands else 0
    estimated_max = (estimated * 2 if len(names) > slots else estimated) + alias_calls
    max_calls = DEFAULT_MAX_CALLS if inp.max_calls is None else inp.max_calls
    warnings: list[str] = []
    first_anchor = inp.anchor or names[0]

    def result(anchor: str, reanchored: bool, series: list[ScaledSeries], dry: bool) -> CompareResult:
        return CompareResult(
            source=inp.source,
            anchor=anchor,
            reanchored=reanchored,
            series=series,
            calls_used=counter.used - start_used,
            cache_hits=counter.hit - start_hit,
            estimated_calls=estimated,
            estimated_calls_max=estimated_max,
            warnings=warnings,
            dry_run=dry,
        )

    if inp.dry_run:
        if estimated > max_calls:
            warnings.append(
                f"예상 호출 {estimated}회가 상한 {max_calls}회를 넘습니다. "
                "실행하려면 confirm: true가 필요합니다."
            )
        return result(first_anchor, False, [], True)
    check_budget(estimated, max_calls, inp.confirm)

    if shopping:
        for b in inp.brands:
            dropped = brand_keywords(b)[SHOPPING_KEYWORDS_PER_BRAND:]
            if dropped:
                warnings.append(
                    f'"{b.name}": 쇼핑 인사이트는 키워드 그룹당 1개만 지원해 이름으로만 조회합니다. '
                    f"별칭({', '.join(dropped)})은 이름에 데이터가 없을 때만 순서대로 시도합니다."
                )

    # 사용자가 승인한 호출 수(confirm이면 예상 호출 수까지)를 넘겨서 다시 계산하지 않는다
    allowance = max(max_calls, estimated) if inp.confirm else max_calls

    def can_spend(extra: int | None = None) -> bool:
        return counter.used - start_used + (estimated if extra is None else extra) <= allowance

    async def fetch_batch(batch: list[str], keyword_index: dict[str, int] | None = None) -> BatchResult:
        keyword_index = keyword_index or {}
        if shopping:
            keyword = []
            for n in batch:
                kws = brand_keywords(by_name[n])
                keyword.append({"name": n, "param": [kws[keyword_index.get(n, 0)] if keyword_index.get(n, 0) < len(kws) else kws[0]]})
            req: dict = {
                "startDate": start_date,
                "endDate": end_date,
                "timeUnit": inp.time_unit,
                "category": inp.category,
                "keyword": keyword,
            }
            response = await cached_call(
                cache, counter, "shoppingKeywords", req, lambda: api.shopping_keywords(req)
            )
        else:
            req = {
                "startDate": start_date,
                "endDate": end_date,
                "timeUnit": inp.time_unit,
                "keywordGroups": [
                    {"groupName": n, "keywords": brand_keywords(by_name[n])} for n in batch
                ],
            }
            for key, value in (("device", inp.device), ("gender", inp.gender), ("ages", inp.ages)):
                if value:
                    req[key] = value
            response = await cached_call(
                cache, counter, "searchTrend", req, lambda: api.search_trend(req)
            )
        found = {r.get("title"): r for r in response.get("results", []) or []}
        return {
            n: [SeriesPoint(d["period"], d["ratio"]) for d in (found.get(n) or {}).get("data", [])]
            for n in batch
        }

    async def fetch_all(anchor: str, order: list[str]):
        batches = plan_batches(order, anchor, slots)
        return batches, [await fetch_batch(b) for b in batches]

    anchor = first_anchor
    batches, results = await fetch_all(anchor, names)
    reanchored = False
    try:
        scaled = rescale(anchor, results)
    except AnchorError:
        if inp.anchor:
            raise
        # 기준 브랜드에 데이터가 없다: 첫 묶음에서 가장 큰 브랜드로 기준을 바꿔 다시 계산한다
        first = results[0]
        candidates = sorted(
            ((n, _sum(pts)) for n, pts in first.items() if n != anchor), key=lambda t: -t[1]
        )
        best = candidates[0] if candidates else None
        if best and best[1] > 0 and can_spend():
            original = anchor
            anchor = best[0]
            batches, results = await fetch_all(anchor, [anchor, *[n for n in names if n != anchor]])
            scaled = rescale(anchor, results)
            warnings.append(f'기준 브랜드 "{original}"에 데이터가 없어 기준을 "{anchor}"로 바꿨습니다.')
        elif not best or best[1] == 0:
            results = [first]
            scaled = rescale(anchor, results)
            batches = [batches[0]]
            warnings.append(
                f'"{first_anchor}"가 속한 첫 묶음에 데이터가 없어 나머지 브랜드는 비교하지 못했습니다. '
                "anchor를 직접 지정해 다시 실행하세요."
            )
        else:
            raise

    # 값이 전부 0인 브랜드는 기준을 바꿔도 개선되지 않으므로(반올림 0과 실제 0을 구분할 수 없다)
    # 재선택 트리거에서 뺀다. 이 브랜드는 아래에서 "데이터 없음/희소" 경고로 알린다.
    def has_low() -> bool:
        return any(s.low_precision and _peak(s) > 0 for s in scaled)

    if has_low() and not inp.anchor and len(batches) > 1:
        if can_spend():
            try:
                median = pick_median_anchor(scaled)
                if median != anchor:
                    size = {s.brand: _sum(s.points) for s in scaled}
                    others = sorted((n for n in names if n != median), key=lambda n: -size.get(n, 0))
                    next_batches, next_results = await fetch_all(median, [median, *others])
                    scaled = rescale(median, next_results)
                    results, batches, anchor, reanchored = next_results, next_batches, median, True
            except AnchorError as e:
                warnings.append(f"기준 브랜드 재선택에 실패해 첫 계산 결과를 유지했습니다: {e}")
        else:
            warnings.append(
                "정밀도 낮은 브랜드가 있으나 호출 예산이 부족해 기준 브랜드 재선택을 생략했습니다."
            )

    # 쇼핑: 이름에 데이터가 없는 브랜드는 별칭을 순서대로 시도한다 (키워드 그룹당 1개 제한 때문)
    if shopping and alias_brands:

        def is_empty(n: str) -> bool:
            s = next((x for x in scaled if x.brand == n), None)
            return s is None or _peak(s) == 0

        index: dict[str, int] = {}
        for round_no in range(1, SHOPPING_ALIAS_TRIES + 1):
            targets = [
                n
                for n in names
                if n != anchor and is_empty(n) and len(brand_keywords(by_name[n])) > round_no
            ]
            if not targets:
                break
            need = math.ceil(len(targets) / (slots - 1))
            if not can_spend(need):
                quoted = ", ".join(f'"{n}"' for n in targets)
                warnings.append(f"쇼핑 별칭 시도: 호출 예산이 부족해 {quoted}의 별칭을 시도하지 못했습니다.")
                break
            for t in targets:
                index[t] = round_no
            retry = [
                await fetch_batch([anchor, *targets[i : i + slots - 1]], index)
                for i in range(0, len(targets), slots - 1)
            ]
            kept = [{k: v for k, v in b.items() if k not in targets} for b in results]
            results = [*kept, *retry]
            scaled = rescale(anchor, results)
        for n, i in index.items():
            if not is_empty(n):
                warnings.append(
                    f'"{n}": 이름에 데이터가 없어 별칭으로 조회했습니다: "{brand_keywords(by_name[n])[i]}"'
                )

    for s in scaled:
        if _peak(s) == 0:
            warnings.append(f'"{s.brand}": 해당 조건에서 데이터 없음/희소 (값이 모두 0)')
        elif s.low_precision:
            warnings.append(
                f'"{s.brand}": 정밀도 낮음 — 이 브랜드나 비교 기준의 지수가 너무 작아 값이 거칠 수 있습니다.'
            )
    return result(anchor, reanchored, scaled, False)
