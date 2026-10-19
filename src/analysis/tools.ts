import path from "node:path";
import { z } from "zod";
import type { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { BrandSchema, brandKeywords, validateBrands } from "./brand.js";
import { DEFAULT_MAX_CALLS, checkBudget } from "./budget.js";
import { AnalysisApi, CompareResult, compareBrandTrend } from "./compare-trend.js";
import { extractCandidates } from "./candidates.js";
import {
  MentionSource,
  Post,
  collectPosts,
  estimateMentionCalls,
  filterByBrands,
  monthlyCounts,
} from "./mentions.js";
import { CallCounter, FileCache, defaultCache } from "../cache/file-cache.js";
import { ExportResult, Sheet, exportSheets } from "../export/export.js";

const MentionSourceSchema = z.enum(["blog", "cafearticle", "webkr"]);

const CompareShape = {
  brands: z.array(BrandSchema).min(1).max(30).describe("비교할 브랜드 목록 (이름 + 별칭)"),
  source: z
    .enum(["search", "shopping"])
    .describe("search: 검색어 트렌드, shopping: 쇼핑 인사이트(키워드)"),
  startDate: z.string().describe("시작일 (yyyy-mm-dd 또는 'today')"),
  endDate: z.string().describe("종료일 (yyyy-mm-dd 또는 'today')"),
  timeUnit: z.enum(["date", "week", "month"]),
  category: z
    .string()
    .optional()
    .describe("쇼핑 분야 코드 (source가 shopping일 때 필수, find_category로 조회)"),
  anchor: z.string().optional().describe("기준 브랜드 이름 (생략하면 자동)"),
  device: z.enum(["pc", "mo"]).optional().describe("search에서만 사용"),
  gender: z.enum(["f", "m"]).optional().describe("search에서만 사용"),
  ages: z.array(z.string()).optional().describe("search에서만 사용 (코드 1~11)"),
  maxCalls: z
    .number()
    .int()
    .positive()
    .optional()
    .describe(`API 호출 상한 (기본 ${DEFAULT_MAX_CALLS})`),
  confirm: z.boolean().optional().describe("예상 호출 수가 상한을 넘어도 진행"),
  dryRun: z.boolean().optional().describe("호출 없이 예상 호출 수만 계산"),
  exportAs: z
    .string()
    .optional()
    .describe("지정하면 xlsx/csv로 저장할 파일 이름(확장자 제외)"),
};

const MentionsShape = {
  brands: z.array(BrandSchema).min(1).max(30).describe("브랜드 목록 (이름 + 별칭)"),
  sources: z.array(MentionSourceSchema).min(1).default(["blog", "cafearticle"]),
  maxPostsPerBrand: z
    .number()
    .int()
    .min(1)
    .max(1000)
    .default(100)
    .describe("검색어당 수집할 최근 글 수 (기본 100, 최대 1000). 최근 언급 경향을 보는 용도입니다."),
  queriesPerBrand: z
    .number()
    .int()
    .min(1)
    .max(3)
    .default(1)
    .describe("브랜드당 사용할 검색어 수 (이름, 별칭 순)"),
  topCandidates: z.number().int().min(1).max(200).default(30),
  maxCalls: z.number().int().positive().optional(),
  confirm: z.boolean().optional(),
  dryRun: z.boolean().optional(),
  exportAs: z.string().optional(),
};

const SOURCE_LABEL: Record<MentionSource, string> = {
  blog: "블로그",
  cafearticle: "카페글",
  webkr: "웹문서",
};

const MENTION_LIMITATIONS = [
  "월별 언급 건수는 검색어당 최대 1,000건 수집 표본에서 계산한 근사치이며 실제 전체 건수가 아닙니다.",
  "동시 언급 브랜드는 단어 공출현으로 만든 후보이며 정확한 브랜드 목록이 아닙니다. 브랜드 여부는 직접 판단하세요.",
];

const exportDir = () =>
  process.env.NAVER_EXPORT_DIR?.trim() || path.join(process.cwd(), "exports");

const asText = (value: unknown) => ({
  content: [{ type: "text" as const, text: JSON.stringify(value, null, 2) }],
});

const round = (n: number) => Math.round(n * 10000) / 10000;

/** 내보내기 실패가 이미 비용을 치른 분석 결과를 버리지 않도록 오류를 값으로 돌려준다. */
async function tryExport(
  sheets: Sheet[],
  baseName: string
): Promise<{ exported?: ExportResult; exportError?: string }> {
  try {
    return { exported: await exportSheets(sheets, { dir: exportDir(), baseName }) };
  } catch (e) {
    return { exportError: `내보내기 실패: ${(e as Error).message}` };
  }
}

function trendSheets(res: CompareResult): Sheet[] {
  const periods = [
    ...new Set(res.series.flatMap((s) => s.points.map((p) => p.period))),
  ].sort();
  const rows = periods.map((period) => [
    period,
    ...res.series.map((s) => {
      const p = s.points.find((x) => x.period === period);
      return p ? round(p.ratio) : null;
    }),
  ]);
  return [
    { name: "트렌드", columns: ["기간", ...res.series.map((s) => s.brand)], rows },
    {
      name: "한계",
      columns: ["안내"],
      rows: [...res.limitations, ...res.warnings].map((t) => [t]),
    },
  ];
}

export function registerAnalysisTools(
  server: Pick<McpServer, "registerTool">,
  api: AnalysisApi,
  deps: { cache?: FileCache } = {}
): void {
  const cacheOf = () => deps.cache ?? defaultCache();

  server.registerTool(
    "brand_compare_trend",
    {
      description:
        "📈 Compare relative search/shopping-click trends of several book brands on one common scale (anchor keyword rescaling across batches). Values are relative indexes, not counts. Supports dryRun, call budget and xlsx/csv export. (도서 브랜드 여러 개의 검색어 트렌드 또는 쇼핑 클릭 추이를 기준 브랜드로 환산해 한 척도로 비교. 값은 상대 지수)",
      inputSchema: CompareShape,
    },
    async (args: any) => {
      const input = z.object(CompareShape).parse(args);
      const result = await compareBrandTrend(input, { api, cache: cacheOf() });
      const ex =
        input.exportAs && !result.dryRun
          ? await tryExport(trendSheets(result), input.exportAs)
          : {};
      return asText({
        ...result,
        ...(ex.exportError ? { warnings: [...result.warnings, ex.exportError] } : {}),
        ...ex,
      });
    }
  );

  server.registerTool(
    "brand_mentions",
    {
      description:
        "📝 Collect blog/cafe/web posts that mention book brands, count them per month (approximate sample), and list co-mentioned candidate terms with examples. Candidate terms are not verified brands — judge them yourself. Supports dryRun, call budget and xlsx/csv export. (도서 브랜드를 언급한 블로그/카페/웹 글을 수집해 월별 집계와 동시 언급 후보 단어를 제공)",
      inputSchema: MentionsShape,
    },
    async (args: any) => {
      const input = z.object(MentionsShape).parse(args);
      validateBrands(input.brands);
      const estimated = estimateMentionCalls(
        input.brands,
        input.sources,
        input.queriesPerBrand,
        input.maxPostsPerBrand
      );
      const maxCalls = input.maxCalls ?? DEFAULT_MAX_CALLS;
      const limitations = MENTION_LIMITATIONS;
      if (input.dryRun) {
        const warnings =
          estimated > maxCalls
            ? [
                `예상 호출 ${estimated}회가 상한 ${maxCalls}회를 넘습니다. 실행하려면 confirm: true가 필요합니다.`,
              ]
            : [];
        return asText({ dryRun: true, estimatedCalls: estimated, warnings, limitations });
      }
      checkBudget({ estimated, maxCalls, confirm: input.confirm });

      const ctx = { cache: cacheOf(), counter: new CallCounter() };
      const seen = new Set<string>();
      const posts: Post[] = [];
      const warnings: string[] = [];
      const apiTotals: Array<{
        source: MentionSource;
        brand: string;
        query: string;
        total: number;
        collected: number;
        oldestDate?: string;
        truncated: boolean;
      }> = [];
      for (const source of input.sources) {
        for (const brand of input.brands) {
          for (const query of brandKeywords(brand).slice(0, input.queriesPerBrand)) {
            const { posts: got, total } = await collectPosts(
              api,
              source,
              query,
              input.maxPostsPerBrand,
              ctx
            );
            const dates = got.map((p) => p.date).filter((d): d is string => !!d).sort();
            const oldestDate = dates[0];
            const truncated = total > got.length;
            apiTotals.push({
              source,
              brand: brand.name,
              query,
              total,
              collected: got.length,
              ...(oldestDate ? { oldestDate } : {}),
              truncated,
            });
            if (truncated && oldestDate) {
              warnings.push(
                `${SOURCE_LABEL[source]} "${brand.name}" 검색어 "${query}": 전체 ${total}건 중 최근 ${got.length}건만 수집했습니다 (가장 오래된 글 ${oldestDate}). 그 이전 월의 집계는 불완전합니다.`
              );
            }
            for (const p of got) {
              const key = `${p.source}\u0000${p.link}`;
              if (seen.has(key)) continue;
              seen.add(key);
              posts.push(p);
            }
          }
        }
      }

      const { kept, excluded } = filterByBrands(posts, input.brands);
      const { rows: monthly, undated } = monthlyCounts(kept);
      const candidates = extractCandidates(kept, input.brands, { top: input.topCandidates });

      for (const source of input.sources) {
        const mine = kept.filter((p) => p.source === source);
        if (mine.length > 0 && mine.every((p) => !p.date)) {
          warnings.push(
            `${SOURCE_LABEL[source]}은 날짜 정보가 없어 월별 집계에서 제외했습니다. (건수와 후보 분석에는 포함)`
          );
        }
      }

      // 표본이 잘린 소스는 브랜드마다 닿는 과거가 다르다. 가장 늦은 시작일 이전(그 달 포함)은 비교할 수 없다.
      const comparableFrom: Partial<Record<MentionSource, string>> = {};
      for (const t of apiTotals) {
        if (!t.truncated || !t.oldestDate) continue;
        const cur = comparableFrom[t.source];
        if (!cur || t.oldestDate > cur) comparableFrom[t.source] = t.oldestDate;
      }
      const monthlyRows = monthly.map((r) => {
        const from = comparableFrom[r.source];
        return { ...r, partial: from ? r.month <= from.slice(0, 7) : false };
      });

      const result = {
        dryRun: false,
        monthly: monthlyRows,
        comparableFrom,
        undated,
        apiTotals,
        collected: posts.length,
        kept: kept.length,
        excluded,
        candidates,
        callsUsed: ctx.counter.used,
        cacheHits: ctx.counter.hit,
        estimatedCalls: estimated,
        warnings,
        limitations,
      };

      let ex: { exported?: ExportResult; exportError?: string } = {};
      if (input.exportAs) {
        const sheets: Sheet[] = [
          {
            name: "월별언급",
            columns: ["월", "브랜드", "소스", "건수", "부분집계"],
            rows: monthlyRows.map((r) => [
              r.month,
              r.brand,
              r.source,
              r.count,
              r.partial ? "Y" : "",
            ]),
          },
          {
            name: "후보",
            columns: ["단어", "총빈도", "브랜드별", "예시", "출처"],
            rows: candidates.map((c) => [
              c.term,
              c.total,
              Object.entries(c.byBrand)
                .map(([b, n]) => `${b}:${n}`)
                .join("; "),
              c.examples.join(" | "),
              c.sources.join(","),
            ]),
          },
          {
            name: "한계",
            columns: ["안내"],
            rows: [...limitations, ...warnings].map((t) => [t]),
          },
        ];
        ex = await tryExport(sheets, input.exportAs);
      }
      return asText({
        ...result,
        ...(ex.exportError ? { warnings: [...warnings, ex.exportError] } : {}),
        ...ex,
      });
    }
  );
}
