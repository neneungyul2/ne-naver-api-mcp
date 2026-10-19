export type SeriesPoint = { period: string; ratio: number };
/** 배치 하나의 결과. 키는 그룹명(브랜드명), 모든 배치에 기준 브랜드가 들어 있다. */
export type BatchResult = Record<string, SeriesPoint[]>;
export type ScaledSeries = {
  brand: string;
  points: SeriesPoint[];
  lowPrecision: boolean;
};

export const DEFAULT_LOW_THRESHOLD = 1;

export class AnchorError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "AnchorError";
  }
}

const sum = (points: SeriesPoint[]) => points.reduce((a, p) => a + p.ratio, 0);

/** 각 배치 = [기준, ...나머지 최대 slotsPerCall-1개]. 브랜드가 기준뿐이면 [[기준]]. */
export function planBatches(
  brands: string[],
  anchor: string,
  slotsPerCall: number
): string[][] {
  if (!brands.includes(anchor)) {
    throw new Error(`기준 브랜드 "${anchor}"가 브랜드 목록에 없습니다.`);
  }
  const others = brands.filter((b) => b !== anchor);
  const perCall = slotsPerCall - 1;
  if (others.length === 0) return [[anchor]];
  const batches: string[][] = [];
  for (let i = 0; i < others.length; i += perCall) {
    batches.push([anchor, ...others.slice(i, i + perCall)]);
  }
  return batches;
}

export function estimateTrendCalls(
  brandCount: number,
  slotsPerCall: number
): number {
  return Math.max(1, Math.ceil((brandCount - 1) / (slotsPerCall - 1)));
}

/**
 * 첫 배치를 기준 척도로 두고, 배치 b의 환산 계수는
 * Σ(첫 배치의 기준 값) / Σ(배치 b의 기준 값)이다.
 */
export function rescale(
  anchor: string,
  batches: BatchResult[],
  opts: { lowThreshold?: number } = {}
): ScaledSeries[] {
  const threshold = opts.lowThreshold ?? DEFAULT_LOW_THRESHOLD;
  if (batches.length === 0) throw new AnchorError("배치 결과가 없습니다.");

  batches.forEach((batch, i) => {
    if (!batch[anchor]) {
      throw new AnchorError(`기준 브랜드 "${anchor}"가 ${i + 1}번째 배치 결과에 없습니다.`);
    }
  });
  // 배치가 하나면 환산이 필요 없으므로 기준 값이 0이어도 괜찮다
  const multi = batches.length > 1;
  const refSum = sum(batches[0][anchor]);
  if (multi && !(refSum > 0)) {
    throw new AnchorError(
      `기준 브랜드 "${anchor}"의 검색 지수가 기간 내내 0입니다. 다른 기준 브랜드를 지정하세요.`
    );
  }

  const maxOf = (points: SeriesPoint[]) =>
    points.reduce((m, p) => Math.max(m, p.ratio), 0);
  const scaled: ScaledSeries[] = [];
  const push = (brand: string, points: SeriesPoint[], batchWeak: boolean) => {
    scaled.push({
      brand,
      points,
      lowPrecision: maxOf(points) < threshold || batchWeak,
    });
  };

  // 기준 브랜드의 지수가 그 배치 안에서 너무 작으면(API 반올림 잡음) 그 배치의 환산이 거칠다
  const weak = (batch: BatchResult) => multi && maxOf(batch[anchor]) < threshold;

  push(anchor, batches[0][anchor], false);
  batches.forEach((batch, i) => {
    let k = 1;
    const batchWeak = weak(batch);
    if (i > 0) {
      const s = sum(batch[anchor]);
      if (!(s > 0)) {
        throw new AnchorError(
          `기준 브랜드 "${anchor}"의 ${i + 1}번째 배치 지수가 0이라 환산할 수 없습니다.`
        );
      }
      k = refSum / s;
    }
    for (const [brand, points] of Object.entries(batch)) {
      if (brand === anchor) continue;
      push(
        brand,
        points.map((p) => ({ period: p.period, ratio: p.ratio * k })),
        batchWeak
      );
    }
  });
  return scaled;
}

/** 합계가 0보다 큰 브랜드 중 기간 합계가 중앙값인 브랜드 (짝수면 아래쪽 중앙값). */
export function pickMedianAnchor(scaled: ScaledSeries[]): string {
  const withData = scaled.filter((s) => sum(s.points) > 0);
  if (withData.length === 0) {
    throw new AnchorError("데이터가 있는 브랜드가 없어 기준 브랜드를 고를 수 없습니다.");
  }
  const sorted = [...withData].sort((a, b) => sum(a.points) - sum(b.points));
  return sorted[Math.floor((sorted.length - 1) / 2)].brand;
}
