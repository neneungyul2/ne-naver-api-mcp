import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { registerAnalysisTools } from "../dist/src/analysis/tools.js";
import { FileCache } from "../dist/src/cache/file-cache.js";

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "tools-"));
const mkCache = () => new FileCache({ dir: tmp(), ttlMs: 1e9 });

function fakeServer() {
  const tools = {};
  return {
    tools,
    registerTool(name, config, handler) {
      tools[name] = { config, handler };
    },
  };
}

function fakeApi() {
  const calls = [];
  return {
    calls,
    async searchTrend(req) {
      calls.push("searchTrend");
      return {
        results: req.keywordGroups.map((g, i) => ({
          title: g.groupName,
          data: [
            { period: "2025-01-01", ratio: 100 / (i + 1) },
            { period: "2025-02-01", ratio: 50 / (i + 1) },
          ],
        })),
      };
    },
    async datalabShoppingKeywords() {
      calls.push("shopping");
      return { results: [] };
    },
    async search(type, params) {
      calls.push(`search:${type}`);
      const withDate = type === "blog";
      return {
        total: 2,
        items: [
          {
            title: "<b>그래머인사이드</b> 쎄듀 교재",
            description: "중등 문법",
            link: `https://${type}/1`,
            ...(withDate ? { postdate: "20250312" } : {}),
          },
          {
            title: "그래머인사이드 후기 쎄듀",
            description: "정리",
            link: `https://${type}/2`,
            ...(withDate ? { postdate: "20250401" } : {}),
          },
        ],
      };
    },
  };
}

const parse = (res) => JSON.parse(res.content[0].text);

test("도구 2개를 한 번씩 등록한다", () => {
  const server = fakeServer();
  registerAnalysisTools(server, fakeApi(), { cache: mkCache() });
  assert.deepEqual(Object.keys(server.tools).sort(), ["brand_compare_trend", "brand_mentions"]);
});

test("brand_compare_trend: dryRun은 호출 없이 한계 문구를 돌려준다", async () => {
  const server = fakeServer();
  const api = fakeApi();
  registerAnalysisTools(server, api, { cache: mkCache() });
  const out = parse(
    await server.tools.brand_compare_trend.handler({
      brands: [{ name: "A" }, { name: "B" }],
      source: "search",
      startDate: "2025-01-01",
      endDate: "2025-02-28",
      timeUnit: "month",
      dryRun: true,
    })
  );
  assert.equal(api.calls.length, 0);
  assert.equal(out.dryRun, true);
  assert.ok(out.limitations.length > 0);
});

test("brand_compare_trend: exportAs를 주면 xlsx/csv가 생기고 경로가 결과에 있다", async () => {
  const exportDir = tmp();
  process.env.NAVER_EXPORT_DIR = exportDir;
  try {
    const server = fakeServer();
    registerAnalysisTools(server, fakeApi(), { cache: mkCache() });
    const out = parse(
      await server.tools.brand_compare_trend.handler({
        brands: [{ name: "A" }, { name: "B" }],
        source: "search",
        startDate: "2025-01-01",
        endDate: "2025-02-28",
        timeUnit: "month",
        exportAs: "비교",
      })
    );
    assert.ok(out.limitations.length > 0);
    assert.ok(fs.existsSync(out.exported.xlsxPath));
    assert.ok(out.exported.csvPaths.every((p) => fs.existsSync(p)));
    assert.ok(out.exported.xlsxPath.startsWith(exportDir));
  } finally {
    delete process.env.NAVER_EXPORT_DIR;
  }
});

test("brand_mentions: 카페글이 전부 날짜 없음이면 월별 집계 제외 경고를 낸다", async () => {
  const server = fakeServer();
  const api = fakeApi();
  registerAnalysisTools(server, api, { cache: mkCache() });
  const out = parse(
    await server.tools.brand_mentions.handler({
      brands: [{ name: "그래머인사이드" }],
      sources: ["blog", "cafearticle"],
    })
  );
  assert.ok(out.warnings.some((w) => w.includes("카페글") && w.includes("월별 집계에서 제외")));
  assert.ok(out.monthly.some((r) => r.source === "blog" && r.month === "2025-03"));
  assert.equal(out.monthly.some((r) => r.source === "cafearticle"), false);
  assert.equal(out.undated.cafearticle, 2);
  assert.ok(out.candidates.some((c) => c.term === "쎄듀" && c.total >= 2));
  assert.ok(out.limitations.length > 0);
  assert.equal(out.kept, 4);
});

test("brand_mentions: dryRun은 API를 호출하지 않는다", async () => {
  const server = fakeServer();
  const api = fakeApi();
  registerAnalysisTools(server, api, { cache: mkCache() });
  const out = parse(
    await server.tools.brand_mentions.handler({
      brands: [{ name: "그래머인사이드" }],
      sources: ["blog"],
      maxPostsPerBrand: 300,
      dryRun: true,
    })
  );
  assert.equal(api.calls.length, 0);
  assert.equal(out.estimatedCalls, 3);
});

test("brand_mentions: 예상 호출이 상한을 넘으면 던진다", async () => {
  const server = fakeServer();
  registerAnalysisTools(server, fakeApi(), { cache: mkCache() });
  await assert.rejects(
    server.tools.brand_mentions.handler({
      brands: [{ name: "A" }, { name: "B" }],
      sources: ["blog", "cafearticle"],
      maxPostsPerBrand: 1000,
      maxCalls: 5,
    }),
    /confirm/
  );
});

// total이 수집 건수보다 큰 가짜 검색 API (최근 글만 담긴 표본)
function truncatedApi() {
  return {
    async search(type) {
      return {
        total: 250,
        items: [
          { title: "그래머인사이드 신간", description: "a", link: `https://${type}/1`, postdate: "20250401" },
          { title: "그래머인사이드 후기", description: "b", link: `https://${type}/2`, postdate: "20250312" },
        ],
      };
    },
  };
}

test("brand_mentions: 표본이 최근 글에 한정되면 가장 오래된 날짜와 함께 경고한다", async () => {
  const server = fakeServer();
  registerAnalysisTools(server, truncatedApi(), { cache: mkCache() });
  const out = parse(
    await server.tools.brand_mentions.handler({
      brands: [{ name: "그래머인사이드" }],
      sources: ["blog"],
    })
  );
  assert.equal(out.apiTotals[0].collected, 2);
  assert.equal(out.apiTotals[0].oldestDate, "2025-03-12");
  assert.equal(out.apiTotals[0].truncated, true);
  assert.ok(
    out.warnings.some((w) => w.includes("250") && w.includes("2025-03-12") && w.includes("불완전"))
  );
});

test("내보내기가 실패해도 분석 결과는 돌려주고 경고한다", async () => {
  const blocker = path.join(tmp(), "file.txt");
  fs.writeFileSync(blocker, "x");
  process.env.NAVER_EXPORT_DIR = path.join(blocker, "sub");
  try {
    const server = fakeServer();
    registerAnalysisTools(server, fakeApi(), { cache: mkCache() });
    const compare = parse(
      await server.tools.brand_compare_trend.handler({
        brands: [{ name: "A" }, { name: "B" }],
        source: "search",
        startDate: "2025-01-01",
        endDate: "2025-02-28",
        timeUnit: "month",
        exportAs: "x",
      })
    );
    assert.ok(compare.series.length === 2);
    assert.ok(compare.warnings.some((w) => w.includes("내보내기 실패")));
    assert.ok(compare.exportError);
    assert.equal(compare.exported, undefined);

    const mentions = parse(
      await server.tools.brand_mentions.handler({
        brands: [{ name: "그래머인사이드" }],
        sources: ["blog"],
        exportAs: "x",
      })
    );
    assert.ok(mentions.kept > 0);
    assert.ok(mentions.warnings.some((w) => w.includes("내보내기 실패")));
  } finally {
    delete process.env.NAVER_EXPORT_DIR;
  }
});

test("brand_mentions: 키워드가 20개를 넘는 브랜드는 dryRun이어도 호출 전에 오류", async () => {
  const server = fakeServer();
  const api = fakeApi();
  registerAnalysisTools(server, api, { cache: mkCache() });
  const aliases = Array.from({ length: 20 }, (_, i) => `별칭${i}`);
  await assert.rejects(
    server.tools.brand_mentions.handler({ brands: [{ name: "A", aliases }], dryRun: true }),
    /최대 20개/
  );
  assert.equal(api.calls.length, 0);
});
