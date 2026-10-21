"""여러 번 나눠 호출한 Data Lab 상대 지수를 기준 브랜드로 한 척도에 맞춘다.

Data Lab의 ratio는 요청 하나 안에서 최댓값이 100인 상대값이다. 모든 요청에 기준 브랜드를
넣고, 배치 b의 환산 계수를 k_b = Σ(첫 배치의 기준 값) / Σ(배치 b의 기준 값)으로 둔다.
"""
import math
from dataclasses import dataclass

DEFAULT_LOW_THRESHOLD = 1.0


@dataclass
class SeriesPoint:
    period: str
    ratio: float


BatchResult = dict[str, list[SeriesPoint]]


@dataclass
class ScaledSeries:
    brand: str
    points: list[SeriesPoint]
    low_precision: bool


class AnchorError(Exception):
    pass


def _sum(points: list[SeriesPoint]) -> float:
    return sum(p.ratio for p in points)


def _max(points: list[SeriesPoint]) -> float:
    return max((p.ratio for p in points), default=0.0)


def plan_batches(brands: list[str], anchor: str, slots_per_call: int) -> list[list[str]]:
    """각 배치 = [기준, ...나머지 최대 slots_per_call-1개]. 브랜드가 기준뿐이면 [[기준]]."""
    if anchor not in brands:
        raise ValueError(f'기준 브랜드 "{anchor}"가 브랜드 목록에 없습니다.')
    others = [b for b in brands if b != anchor]
    per_call = slots_per_call - 1
    if not others:
        return [[anchor]]
    return [[anchor, *others[i : i + per_call]] for i in range(0, len(others), per_call)]


def estimate_trend_calls(brand_count: int, slots_per_call: int) -> int:
    return max(1, math.ceil((brand_count - 1) / (slots_per_call - 1)))


def rescale(
    anchor: str, batches: list[BatchResult], low_threshold: float = DEFAULT_LOW_THRESHOLD
) -> list[ScaledSeries]:
    if not batches:
        raise AnchorError("배치 결과가 없습니다.")
    for i, batch in enumerate(batches):
        if anchor not in batch:
            raise AnchorError(f'기준 브랜드 "{anchor}"가 {i + 1}번째 배치 결과에 없습니다.')

    multi = len(batches) > 1  # 배치가 하나면 환산이 필요 없으므로 기준 값이 0이어도 괜찮다
    ref_sum = _sum(batches[0][anchor])
    if multi and not ref_sum > 0:
        raise AnchorError(
            f'기준 브랜드 "{anchor}"의 검색 지수가 기간 내내 0입니다. 다른 기준 브랜드를 지정하세요.'
        )

    scaled: list[ScaledSeries] = []

    def push(brand: str, points: list[SeriesPoint], batch_weak: bool) -> None:
        scaled.append(ScaledSeries(brand, points, _max(points) < low_threshold or batch_weak))

    push(anchor, batches[0][anchor], False)
    for i, batch in enumerate(batches):
        # 기준의 지수가 그 배치 안에서 너무 작으면(API 반올림 잡음) 그 배치의 환산이 거칠다
        batch_weak = multi and _max(batch[anchor]) < low_threshold
        k = 1.0
        if i > 0:
            batch_sum = _sum(batch[anchor])
            if not batch_sum > 0:
                raise AnchorError(
                    f'기준 브랜드 "{anchor}"의 {i + 1}번째 배치 지수가 0이라 환산할 수 없습니다.'
                )
            k = ref_sum / batch_sum
        for brand, points in batch.items():
            if brand == anchor:
                continue
            push(brand, [SeriesPoint(p.period, p.ratio * k) for p in points], batch_weak)
    return scaled


def pick_median_anchor(scaled: list[ScaledSeries]) -> str:
    """합계가 0보다 큰 브랜드 중 기간 합계가 중앙값인 브랜드 (짝수면 아래쪽 중앙값)."""
    with_data = [s for s in scaled if _sum(s.points) > 0]
    if not with_data:
        raise AnchorError("데이터가 있는 브랜드가 없어 기준 브랜드를 고를 수 없습니다.")
    ordered = sorted(with_data, key=lambda s: _sum(s.points))
    return ordered[(len(ordered) - 1) // 2].brand
