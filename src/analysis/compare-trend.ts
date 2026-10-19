import {
  DatalabSearchRequest,
  DatalabShoppingKeywordsRequest,
  DatalabShoppingResponse,
} from "../types/datalab.types.js";
import { SearchArgs } from "../schemas/search.schemas.js";
import { resolveDateRange } from "../utils/date.utils.js";
import { CallCounter, FileCache, cachedCall } from "../cache/file-cache.js";
import { DEFAULT_MAX_CALLS, checkBudget } from "./budget.js";
import { Brand, brandKeywords, validateBrands } from "./brand.js";
import {
  AnchorError,
  BatchResult,
  ScaledSeries,
  estimateTrendCalls,
  pickMedianAnchor,
  planBatches,
  rescale,
} from "./rescale.js";

/** 기존 NaverSearchClient가 구조적으로 만족하는 최소 API 표면 */
export interface AnalysisApi {
  searchTrend(req: DatalabSearchRequest): Promise<DatalabShoppingResponse>;
  datalabShoppingKeywords(
    req: DatalabShoppingKeywordsRequest
  ): Promise<DatalabShoppingResponse>;
  search(
    type: "blog" | "cafearticle" | "webkr",
    params: SearchArgs
  ): Promise<any>;
}

/** 한 번의 검색어 트렌드 호출에 넣을 수 있는 그룹 수 (HUB 문서: 최대 5개) */
export const SEARCH_SLOTS_PER_CALL = 5;
/** 쇼핑 인사이트 키워드 그룹 수. Task 1(실제 키 검증)에서 확인한 값으로 갱신한다. */
export const SHOPPING_SLOTS_PER_CALL = 5;

export interface CompareInput {
  brands: Brand[];
  source: "search" | "shopping";
  startDate: string;
  endDate: string;
  timeUnit: "date" | "week" | "month";
  category?: string;
  anchor?: string;
  device?: "pc" | "mo";
  gender?: "f" | "m";
  ages?: string[];
  maxCalls?: number;
  confirm?: boolean;
  dryRun?: boolean;
}

export interface CompareResult {
  source: string;
  anchor: string;
  reanchored: boolean;
  series: ScaledSeries[];
  callsUsed: number;
  cacheHits: number;
  /** 기준 브랜드 변경 없이 한 번 실행할 때의 예상 호출 수 */
  estimatedCalls: number;
  /** 기준 브랜드 재선택/교체가 일어나는 최악의 경우의 호출 수 */
  estimatedCallsMax: number;
  warnings: string[];
  limitations: string[];
  dryRun: boolean;
}

const LIMITATIONS = [
  "모든 값은 실제 검색/클릭 횟수가 아니라 공통 기준 대비 상대 지수입니다.",
  "첫 묶음의 최댓값을 100으로 한 척도로 환산하므로 값이 100을 넘을 수 있습니다.",
  "배치마다 기준 브랜드 값으로 환산한 값이라 작은 브랜드는 값이 거칠 수 있습니다.",
];

function validate(input: CompareInput): void {
  if (input.brands.length === 0) throw new Error("brands가 비어 있습니다.");
  validateBrands(input.brands);
  const names = input.brands.map((b) => b.name);
  if (new Set(names).size !== names.length) {
    throw new Error("브랜드 이름이 중복되었습니다. 이름은 서로 달라야 합니다.");
  }
  if (input.source === "shopping") {
    if (!input.category) {
      throw new Error("source가 shopping이면 category(쇼핑 분야 코드)가 필요합니다.");
    }
    if (input.device || input.gender || input.ages) {
      throw new Error("쇼핑 인사이트 비교는 device/gender/ages 필터를 지원하지 않습니다.");
    }
  }
  if (input.anchor && !names.includes(input.anchor)) {
    throw new Error(`anchor "${input.anchor}"가 브랜드 목록에 없습니다.`);
  }
}

const sumPoints = (points: { ratio: number }[]) =>
  points.reduce((a, p) => a + p.ratio, 0);
const sumOf = (s: ScaledSeries) => sumPoints(s.points);
const maxOf = (s: ScaledSeries) => s.points.reduce((m, p) => Math.max(m, p.ratio), 0);

export async function compareBrandTrend(
  input: CompareInput,
  deps: { api: AnalysisApi; cache: FileCache; counter?: CallCounter }
): Promise<CompareResult> {
  validate(input);
  const { api, cache } = deps;
  const counter = deps.counter ?? new CallCounter();
  const startUsed = counter.used;
  const startHit = counter.hit;

  const { startDate, endDate } = resolveDateRange(input.startDate, input.endDate);
  const slots =
    input.source === "shopping" ? SHOPPING_SLOTS_PER_CALL : SEARCH_SLOTS_PER_CALL;
  const byName = new Map(input.brands.map((b) => [b.name, b]));
  const names = input.brands.map((b) => b.name);
  const estimated = estimateTrendCalls(names.length, slots);
  const estimatedMax = names.length > slots ? estimated * 2 : estimated;
  const maxCalls = input.maxCalls ?? DEFAULT_MAX_CALLS;
  const warnings: string[] = [];
  const firstAnchor = input.anchor ?? names[0];

  if (input.dryRun) {
    if (estimated > maxCalls) {
      warnings.push(
        `예상 호출 ${estimated}회가 상한 ${maxCalls}회를 넘습니다. 실행하려면 confirm: true가 필요합니다.`
      );
    }
    return {
      source: input.source,
      anchor: firstAnchor,
      reanchored: false,
      series: [],
      callsUsed: 0,
      cacheHits: 0,
      estimatedCalls: estimated,
      estimatedCallsMax: estimatedMax,
      warnings,
      limitations: LIMITATIONS,
      dryRun: true,
    };
  }
  checkBudget({ estimated, maxCalls, confirm: input.confirm });

  // 사용자가 승인한 호출 수(confirm이면 예상 호출 수까지)를 넘겨서 다시 계산하지 않는다
  const allowance = input.confirm === true ? Math.max(maxCalls, estimated) : maxCalls;
  const canSpend = () => counter.used - startUsed + estimated <= allowance;

  const fetchBatch = async (batch: string[]): Promise<BatchResult> => {
    let response: DatalabShoppingResponse;
    if (input.source === "shopping") {
      const req: DatalabShoppingKeywordsRequest = {
        startDate,
        endDate,
        timeUnit: input.timeUnit,
        category: input.category as string,
        keyword: batch.map((n) => ({
          name: n,
          param: brandKeywords(byName.get(n) as Brand),
        })),
      };
      response = await cachedCall(cache, counter, "shoppingKeywords", req, () =>
        api.datalabShoppingKeywords(req)
      );
    } else {
      const req: DatalabSearchRequest & {
        device?: string;
        gender?: string;
        ages?: string[];
      } = {
        startDate,
        endDate,
        timeUnit: input.timeUnit,
        keywordGroups: batch.map((n) => ({
          groupName: n,
          keywords: brandKeywords(byName.get(n) as Brand),
        })),
        ...(input.device ? { device: input.device } : {}),
        ...(input.gender ? { gender: input.gender } : {}),
        ...(input.ages ? { ages: input.ages } : {}),
      };
      response = await cachedCall(cache, counter, "searchTrend", req, () =>
        api.searchTrend(req)
      );
    }
    const out: BatchResult = {};
    for (const n of batch) {
      const found = response.results?.find((r) => r.title === n);
      out[n] = (found?.data ?? []).map((d) => ({ period: d.period, ratio: d.ratio }));
    }
    return out;
  };

  const fetchAll = async (anchor: string, order: string[]) => {
    const batches = planBatches(order, anchor, slots);
    const results: BatchResult[] = [];
    for (const b of batches) results.push(await fetchBatch(b));
    return { batches, results };
  };

  let anchor = firstAnchor;
  let fetched = await fetchAll(anchor, names);
  let batches = fetched.batches;
  let scaled: ScaledSeries[];
  try {
    scaled = rescale(anchor, fetched.results);
  } catch (e) {
    if (!(e instanceof AnchorError) || input.anchor) throw e;
    // 기준 브랜드에 데이터가 없다: 첫 묶음에서 가장 큰 브랜드로 기준을 바꿔 다시 계산한다
    const first = fetched.results[0];
    const best = Object.entries(first)
      .filter(([n]) => n !== anchor)
      .map(([n, pts]) => ({ name: n, total: sumPoints(pts) }))
      .sort((a, b) => b.total - a.total)[0];
    if (best && best.total > 0 && canSpend()) {
      anchor = best.name;
      fetched = await fetchAll(anchor, [anchor, ...names.filter((n) => n !== anchor)]);
      batches = fetched.batches;
      scaled = rescale(anchor, fetched.results);
      warnings.push(
        `기준 브랜드 "${firstAnchor}"에 데이터가 없어 기준을 "${anchor}"로 바꿨습니다.`
      );
    } else if (!best || best.total === 0) {
      scaled = rescale(anchor, [first]);
      batches = [fetched.batches[0]];
      warnings.push(
        `"${firstAnchor}"가 속한 첫 묶음에 데이터가 없어 나머지 브랜드는 비교하지 못했습니다. anchor를 직접 지정해 다시 실행하세요.`
      );
    } else {
      throw e;
    }
  }
  let reanchored = false;

  // 값이 전부 0인 브랜드는 기준을 바꿔도 개선되지 않으므로(반올림 0과 실제 0을 구분할 수 없다)
  // 재선택 트리거에서 뺀다. 이 브랜드는 아래에서 "데이터 없음/희소" 경고로 알린다.
  const hasLow = () => scaled.some((s) => s.lowPrecision && maxOf(s) > 0);
  if (hasLow() && !input.anchor && batches.length > 1) {
    if (canSpend()) {
      try {
        const median = pickMedianAnchor(scaled);
        if (median !== anchor) {
          const size = new Map(scaled.map((s) => [s.brand, sumOf(s)]));
          const others = names
            .filter((n) => n !== median)
            .sort((a, b) => (size.get(b) ?? 0) - (size.get(a) ?? 0));
          const next = await fetchAll(median, [median, ...others]);
          scaled = rescale(median, next.results);
          batches = next.batches;
          anchor = median;
          reanchored = true;
        }
      } catch (e) {
        if (!(e instanceof AnchorError)) throw e;
        warnings.push(`기준 브랜드 재선택에 실패해 첫 계산 결과를 유지했습니다: ${e.message}`);
      }
    } else {
      warnings.push(
        "정밀도 낮은 브랜드가 있으나 호출 예산이 부족해 기준 브랜드 재선택을 생략했습니다."
      );
    }
  }

  for (const s of scaled) {
    if (maxOf(s) === 0) {
      warnings.push(`"${s.brand}": 해당 조건에서 데이터 없음/희소 (값이 모두 0)`);
    } else if (s.lowPrecision) {
      warnings.push(
        `"${s.brand}": 정밀도 낮음 — 이 브랜드나 비교 기준의 지수가 너무 작아 값이 거칠 수 있습니다.`
      );
    }
  }

  return {
    source: input.source,
    anchor,
    reanchored,
    series: scaled,
    callsUsed: counter.used - startUsed,
    cacheHits: counter.hit - startHit,
    estimatedCalls: estimated,
    estimatedCallsMax: estimatedMax,
    warnings,
    limitations: LIMITATIONS,
    dryRun: false,
  };
}
