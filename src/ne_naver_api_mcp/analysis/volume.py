"""검색광고 키워드 검색수(절대값)로 Data Lab 상대 지수를 환산해 월별 검색량을 추정한다.

Data Lab은 요청마다 최댓값이 100인 상대 지수이고, 검색광고 keywordstool은 최근 한 달의 PC/모바일
검색수(절대값)다. 일 단위 지수를 한 척도로 모은 뒤 *최근 30일 지수 합*을 검색광고의 월 검색수에
맞춰 계수 k = (월 검색수) / (최근 30일 지수 합)를 구하고, 모든 일의 지수에 k를 곱해 월로 합산한다.
단위(일/월)를 섞으면 "최댓값 100"의 기준이 달라지므로 일 단위로 통일한다.
"""
import calendar
import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from ..cache import CallCounter, FileCache, cached_call
from ..dates import korean_today, resolve_date
from ..searchad import MAX_HINTS_PER_CALL, SearchAdClient, normalize_hint
from .brand import Brand, brand_keywords, validate_brands
from .budget import DEFAULT_MAX_CALLS, check_budget
from .compare_trend import SEARCH_SLOTS_PER_CALL, AnalysisApi, CompareInput, compare_brand_trend
from .rescale import SeriesPoint, estimate_trend_calls

WINDOW_DAYS = 30  # 검색광고의 "최근 한 달"에 맞추는 기준 구간(어제까지 30일)
LOW_COUNT_UPPER = 9  # 검색광고는 10 미만을 "< 10"으로만 알려 준다
K_SPREAD_WARN = 2.0  # 브랜드 간 환산 계수가 이 배수 넘게 다르면 경고

LIMITATIONS = [
    "검색광고의 검색수는 최근 한 달 값이고, Data Lab은 요청 구간의 상대 지수입니다. 두 지표의 집계 정의가 달라 "
    "추정값은 대략적인 규모로만 쓰세요 (브랜드 간 환산 계수 차이가 클수록 오차가 큽니다).",
    "월별 추정값은 일 단위 Data Lab 지수에 환산 계수를 곱해 합친 값입니다. 검색량이 작은 브랜드는 지수가 반올림되어 거칠 수 있습니다.",
    "검색광고가 10 미만으로만 알려 주는 키워드는 환산 기준에서 제외합니다.",
]


@dataclass
class KeywordVolume:
    keyword: str
    pc: int | None
    mobile: int | None
    pc_low: bool
    mobile_low: bool
    comp_idx: str | None = None

    @property
    def low(self) -> bool:
        return self.pc_low or self.mobile_low

    @property
    def total(self) -> int:
        """알려진 PC + 모바일 합 (10 미만으로 가려진 쪽은 0으로 두므로 low일 때는 하한이다)."""
        return (self.pc or 0) + (self.mobile or 0)

    def to_dict(self) -> dict:
        return {
            "keyword": self.keyword,
            "pc": self.pc,
            "mobile": self.mobile,
            "total": self.total,
            "lowVolume": self.low,
            "totalUpperBound": self.total + LOW_COUNT_UPPER * (int(self.pc_low) + int(self.mobile_low)),
            "compIdx": self.comp_idx,
        }


def parse_count(raw: object) -> tuple[int | None, bool]:
    """검색수 값 -> (값, 10 미만 여부). 숫자면 (값, False), '< 10'이면 (None, True)."""
    if isinstance(raw, bool):
        return None, False
    if isinstance(raw, int | float):
        return int(raw), False
    if isinstance(raw, str):
        text = raw.strip().replace(",", "")
        if text.startswith("<"):
            return None, True
        try:
            return int(float(text)), False
        except ValueError:
            return None, False
    return None, False


def parse_keyword_list(response: dict) -> dict[str, KeywordVolume]:
    """keywordstool 응답 -> {공백 없는 소문자 키워드: KeywordVolume}."""
    out: dict[str, KeywordVolume] = {}
    for row in response.get("keywordList", []) or []:
        keyword = str(row.get("relKeyword") or "")
        if not keyword:
            continue
        pc, pc_low = parse_count(row.get("monthlyPcQcCnt"))
        mobile, mobile_low = parse_count(row.get("monthlyMobileQcCnt"))
        out[normalize_hint(keyword).lower()] = KeywordVolume(
            keyword, pc, mobile, pc_low, mobile_low, str(row["compIdx"]) if row.get("compIdx") else None
        )
    return out


@dataclass
class GroupVolume:
    """브랜드(이름+별칭)의 검색광고 월 검색수. 공백만 다른 키워드는 한 번만 센다."""

    keywords: list[KeywordVolume]
    missing: list[str]  # 응답에 없던 키워드

    @property
    def low(self) -> bool:
        return any(k.low for k in self.keywords)

    @property
    def total(self) -> int:
        return sum(k.total for k in self.keywords)

    @property
    def usable(self) -> bool:
        """환산 기준으로 쓸 수 있는가: 값이 있고 10 미만으로 가려진 키워드가 없다."""
        return bool(self.keywords) and not self.low and self.total > 0


def unique_hints(brand: Brand) -> list[str]:
    """브랜드 키워드를 공백 제거 + 소문자로 정규화해 중복을 뺀다 (원래 순서 유지)."""
    seen: set[str] = set()
    out: list[str] = []
    for kw in brand_keywords(brand):
        key = normalize_hint(kw).lower()
        if key and key not in seen:
            seen.add(key)
            out.append(key)
    return out


def group_volume(brand: Brand, stats: dict[str, KeywordVolume]) -> GroupVolume:
    found: list[KeywordVolume] = []
    missing: list[str] = []
    for key in unique_hints(brand):
        if key in stats:
            found.append(stats[key])
        else:
            missing.append(key)
    return GroupVolume(found, missing)


def window_bounds(today: str) -> tuple[str, str]:
    """환산 기준 구간: 어제까지 WINDOW_DAYS일 (Data Lab 일 데이터는 어제까지 확정된다)."""
    yesterday = date.fromisoformat(today) - timedelta(days=1)
    return (yesterday - timedelta(days=WINDOW_DAYS - 1)).isoformat(), yesterday.isoformat()


def ratio_sum(points: list[SeriesPoint], start: str, end: str) -> tuple[float, int]:
    """[start, end] 안 지수 합과 값이 있는 날 수 (ISO 날짜 문자열은 사전순 비교가 날짜순과 같다)."""
    inside = [p.ratio for p in points if start <= p.period <= end]
    return sum(inside), len(inside)


def calibration_factor(volume: int, window_ratio_sum: float) -> float | None:
    return volume / window_ratio_sum if volume > 0 and window_ratio_sum > 0 else None


def monthly_estimates(
    points: list[SeriesPoint], k: float, start: str, end: str
) -> list[dict]:
    """[start, end] 구간의 일 지수를 월로 합산해 k를 곱한다. 일부 날짜만 있는 달은 partial."""
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    sums: dict[str, float] = defaultdict(float)
    days: dict[str, int] = defaultdict(int)
    for p in points:
        if start <= p.period <= end:
            sums[p.period[:7]] += p.ratio
            days[p.period[:7]] += 1
    rows: list[dict] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        key = f"{year:04d}-{month:02d}"
        month_first = max(first, date(year, month, 1))
        month_last = min(last, date(year, month, calendar.monthrange(year, month)[1]))
        expected = (month_last - month_first).days + 1
        rows.append(
            {
                "month": key,
                "estimated": round(k * sums[key]) if key in sums else None,
                "days": days.get(key, 0),
                "expectedDays": expected,
                "partial": days.get(key, 0) < expected,
            }
        )
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return rows


@dataclass
class VolumeInput:
    brands: list[Brand]
    start_date: str
    end_date: str
    max_calls: int | None = None
    confirm: bool = False
    dry_run: bool = False


@dataclass
class BrandEstimate:
    brand: str
    searchad: GroupVolume
    k: float | None
    k_source: str  # "own" | "common" | "none"
    window_ratio_sum: float
    window_days_present: int
    low_precision: bool
    monthly: list[dict]

    def to_dict(self) -> dict:
        return {
            "brand": self.brand,
            "searchadMonthly": {
                "total": self.searchad.total,
                "lowVolume": self.searchad.low,
                "keywords": [k.to_dict() for k in self.searchad.keywords],
                "missingKeywords": self.searchad.missing,
            },
            "calibration": {
                "k": self.k,
                "source": self.k_source,
                "windowRatioSum": round(self.window_ratio_sum, 4),
                "windowDaysPresent": self.window_days_present,
            },
            "lowPrecision": self.low_precision,
            "monthly": self.monthly,
        }


@dataclass
class VolumeResult:
    estimates: list[BrandEstimate]
    window: tuple[str, str]
    common_k: float | None
    calls_used: int
    cache_hits: int
    estimated_calls: int
    warnings: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=lambda: list(LIMITATIONS))
    dry_run: bool = False

    def to_dict(self) -> dict:
        return {
            "dryRun": self.dry_run,
            "window": {"start": self.window[0], "end": self.window[1]},
            "commonK": self.common_k,
            "estimates": [e.to_dict() for e in self.estimates],
            "callsUsed": self.calls_used,
            "cacheHits": self.cache_hits,
            "estimatedCalls": self.estimated_calls,
            "warnings": self.warnings,
            "limitations": self.limitations,
        }


def estimate_volume_calls(brands: list[Brand]) -> tuple[int, int]:
    """(Data Lab 호출 수, 검색광고 호출 수) 예상. 기준 재선택 같은 예외는 포함하지 않는다."""
    keywords = {k for b in brands for k in unique_hints(b)}
    return (
        estimate_trend_calls(len(brands), SEARCH_SLOTS_PER_CALL),
        math.ceil(len(keywords) / MAX_HINTS_PER_CALL),
    )


async def fetch_searchad_stats(
    api: SearchAdClient, brands: list[Brand], cache: FileCache, counter: CallCounter
) -> dict[str, KeywordVolume]:
    keywords = list(dict.fromkeys(k for b in brands for k in unique_hints(b)))
    stats: dict[str, KeywordVolume] = {}
    for i in range(0, len(keywords), MAX_HINTS_PER_CALL):
        batch = keywords[i : i + MAX_HINTS_PER_CALL]
        response = await cached_call(
            cache, counter, "searchadKeywordTool", {"hints": batch}, lambda b=batch: api.keyword_tool(b)
        )
        stats.update(parse_keyword_list(response))
    return stats


async def estimate_search_volume(
    inp: VolumeInput,
    trend_api: AnalysisApi,
    searchad: SearchAdClient,
    cache: FileCache,
    counter: CallCounter | None = None,
    *,
    today: str | None = None,
) -> VolumeResult:
    if not inp.brands:
        raise ValueError("brands가 비어 있습니다.")
    validate_brands(inp.brands)
    names = [b.name for b in inp.brands]
    if len(set(names)) != len(names):
        raise ValueError("브랜드 이름이 중복되었습니다. 이름은 서로 달라야 합니다.")

    counter = counter or CallCounter()
    used0, hit0 = counter.used, counter.hit
    today = today or korean_today()
    window = window_bounds(today)
    yesterday = window[1]
    start, end = resolve_date(inp.start_date), min(resolve_date(inp.end_date), yesterday)
    if start > end:
        raise ValueError(f"조회 구간이 올바르지 않습니다: {start} ~ {end} (종료일은 어제까지 가능합니다)")
    fetch_start = min(start, window[0])

    trend_calls, ad_calls = estimate_volume_calls(inp.brands)
    estimated = trend_calls + ad_calls
    max_calls = DEFAULT_MAX_CALLS if inp.max_calls is None else inp.max_calls
    warnings: list[str] = []

    def result(estimates: list[BrandEstimate], common_k: float | None, dry: bool) -> VolumeResult:
        return VolumeResult(
            estimates=estimates, window=window, common_k=common_k,
            calls_used=counter.used - used0, cache_hits=counter.hit - hit0,
            estimated_calls=estimated, warnings=warnings, dry_run=dry,
        )

    if inp.dry_run:
        if estimated > max_calls:
            warnings.append(
                f"예상 호출 {estimated}회가 상한 {max_calls}회를 넘습니다. 실행하려면 confirm: true가 필요합니다."
            )
        return result([], None, True)
    check_budget(estimated, max_calls, inp.confirm)

    stats = await fetch_searchad_stats(searchad, inp.brands, cache, counter)
    trend = await compare_brand_trend(
        CompareInput(
            brands=inp.brands, source="search", start_date=fetch_start, end_date=yesterday,
            time_unit="date", max_calls=max(max_calls, estimated * 2), confirm=True,
        ),
        trend_api, cache, counter,
    )
    warnings.extend(trend.warnings)
    series = {s.brand: s for s in trend.series}

    groups = {b.name: group_volume(b, stats) for b in inp.brands}
    sums = {n: ratio_sum(series[n].points, *window) if n in series else (0.0, 0) for n in names}

    # 자체 기준으로 쓸 수 있는 브랜드의 계수
    own_k = {
        n: calibration_factor(groups[n].total, sums[n][0]) if groups[n].usable else None for n in names
    }
    valid = [n for n in names if own_k[n] is not None]
    common_k = (
        sum(groups[n].total for n in valid) / sum(sums[n][0] for n in valid) if valid else None
    )
    if len(valid) >= 2:
        ks = [own_k[n] for n in valid]  # type: ignore[misc]
        spread = max(ks) / min(ks)  # type: ignore[type-var]
        if spread > K_SPREAD_WARN:
            warnings.append(
                f"브랜드마다 환산 계수가 {spread:.1f}배까지 차이 납니다. 검색광고와 Data Lab의 집계 차이이거나 "
                "검색량이 작은 브랜드의 지수가 거칠기 때문일 수 있습니다. 추정값을 신중히 해석하세요."
            )
    if not valid:
        raise ValueError(
            "검색광고 월 검색수가 있는 브랜드가 없어 환산할 수 없습니다 (모두 10 미만이거나 조회되지 않음). "
            "더 큰 키워드를 포함하거나 별칭을 추가하세요."
        )

    estimates: list[BrandEstimate] = []
    for b in inp.brands:
        n = b.name
        pts = series[n].points if n in series else []
        k, source = own_k[n], "own"
        if k is None:
            k, source = (common_k, "common") if pts and sum(sums[n]) > 0 else (None, "none")
            if source == "common":
                reason = "10 미만으로만 조회됨" if groups[n].low else "검색광고에서 조회되지 않음"
                warnings.append(
                    f'"{n}": 검색광고 검색수가 {reason}이라 다른 브랜드의 공통 환산 계수로 추정했습니다 (오차 큼).'
                )
            else:
                warnings.append(f'"{n}": 환산할 수 있는 데이터가 없어 추정하지 못했습니다.')
        if groups[n].missing:
            warnings.append(f'"{n}": 검색광고 응답에 없는 키워드: {", ".join(groups[n].missing)}')
        if sums[n][1] < WINDOW_DAYS and pts:
            warnings.append(f'"{n}": 환산 기준 구간 {WINDOW_DAYS}일 중 {sums[n][1]}일의 지수만 있습니다.')
        estimates.append(
            BrandEstimate(
                brand=n, searchad=groups[n], k=k, k_source=source,
                window_ratio_sum=sums[n][0], window_days_present=sums[n][1],
                low_precision=bool(series[n].low_precision) if n in series else True,
                monthly=monthly_estimates(pts, k, start, end) if k is not None else [],
            )
        )
    return result(estimates, common_k, False)
