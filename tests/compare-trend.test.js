import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { compareBrandTrend } from "../dist/src/analysis/compare-trend.js";
import { FileCache, CallCounter } from "../dist/src/cache/file-cache.js";
import { BudgetExceededError } from "../dist/src/analysis/budget.js";

const mkCache = () =>
  new FileCache({ dir: fs.mkdtempSync(path.join(os.tmpdir(), "cmp-")), ttlMs: 1e9 });
const brand = (name) => ({ name, aliases: [] });
const brands = (...names) => names.map(brand);
const periods = ["2025-01-01", "2025-02-01"];

// 실제 검색량(world)을 요청 안 최댓값=100으로 정규화해 돌려주는 가짜 API
function makeApi(world) {
  const calls = [];
  const respond = (groups) => {
    const max = Math.max(...groups.flatMap((g) => world[g]));
    return {
      results: groups.map((g) => ({
        title: g,
        data: world[g].map((v, i) => ({
          period: periods[i],
          ratio: max ? (v / max) * 100 : 0,
        })),
      })),
    };
  };
  return {
    calls,
    async searchTrend(req) {
      const groups = req.keywordGroups.map((k) => k.groupName);
      calls.push({ kind: "search", groups, req });
      return respond(groups);
    },
    async datalabShoppingKeywords(req) {
      const groups = req.keyword.map((k) => k.name);
      calls.push({ kind: "shopping", groups, req });
      return respond(groups);
    },
    async search() {
      throw new Error("unused");
    },
  };
}

const base = { source: "search", startDate: "2025-01-01", endDate: "2025-02-28", timeUnit: "month" };
const world6 = { A: [100, 100], B: [50, 50], C: [200, 200], D: [20, 20], E: [400, 400], F: [10, 10] };
const ratios = (res, name) => res.series.find((s) => s.brand === name).points.map((p) => p.ratio);

test("브랜드 6개는 기준 A를 고정해 2번 호출하고 한 척도로 환산한다", async () => {
  const api = makeApi(world6);
  const res = await compareBrandTrend(
    { ...base, brands: brands("A", "B", "C", "D", "E", "F") },
    { api, cache: mkCache() }
  );
  assert.deepEqual(api.calls.map((c) => c.groups), [["A", "B", "C", "D", "E"], ["A", "F"]]);
  assert.equal(res.callsUsed, 2);
  assert.equal(res.anchor, "A");
  assert.equal(res.reanchored, false);
  assert.ok(Math.abs(ratios(res, "F")[0] - 2.5) < 1e-9);
  assert.ok(Math.abs(ratios(res, "E")[0] - 100) < 1e-9);
  assert.ok(res.limitations.length > 0);
});

test("키워드 묶음은 이름+별칭으로 전달된다", async () => {
  const api = makeApi({ A: [1, 1] });
  await compareBrandTrend(
    { ...base, brands: [{ name: "A", aliases: ["에이", "A"] }] },
    { api, cache: mkCache() }
  );
  assert.deepEqual(api.calls[0].req.keywordGroups, [{ groupName: "A", keywords: ["A", "에이"] }]);
  assert.equal(api.calls.length, 1);
});

test("dryRun은 호출 없이 예상 호출 수만 돌려준다", async () => {
  const api = makeApi(world6);
  const res = await compareBrandTrend(
    { ...base, brands: brands("A", "B", "C", "D", "E", "F"), dryRun: true },
    { api, cache: mkCache() }
  );
  assert.equal(api.calls.length, 0);
  assert.equal(res.estimatedCalls, 2);
  assert.equal(res.dryRun, true);
});

test("예상 호출이 maxCalls를 넘으면 BudgetExceededError, confirm이면 진행", async () => {
  const input = { ...base, brands: brands("A", "B", "C", "D", "E", "F"), maxCalls: 1 };
  await assert.rejects(
    compareBrandTrend(input, { api: makeApi(world6), cache: mkCache() }),
    BudgetExceededError
  );
  const res = await compareBrandTrend({ ...input, confirm: true }, { api: makeApi(world6), cache: mkCache() });
  assert.equal(res.callsUsed, 2);
});

test("같은 입력을 다시 실행하면 캐시로 호출 0회", async () => {
  const cache = mkCache();
  const input = { ...base, brands: brands("A", "B", "C", "D", "E", "F") };
  await compareBrandTrend(input, { api: makeApi(world6), cache });
  const api2 = makeApi(world6);
  const res = await compareBrandTrend(input, { api: api2, cache });
  assert.equal(api2.calls.length, 0);
  assert.equal(res.callsUsed, 0);
  assert.equal(res.cacheHits, 2);
});

const world2 = { A: [10000, 10000], B: [5000, 5000], C: [100, 100], D: [1, 1], E: [50, 50], F: [2, 2] };

test("정밀도 낮은 브랜드가 있고 배치가 2개 이상이면 중앙 브랜드로 한 번 재기준한다", async () => {
  const api = makeApi(world2);
  const res = await compareBrandTrend(
    { ...base, brands: brands("A", "B", "C", "D", "E", "F") },
    { api, cache: mkCache() }
  );
  assert.equal(res.reanchored, true);
  assert.equal(res.anchor, "E");
  assert.equal(api.calls.length, 4);
  assert.deepEqual(api.calls[2].groups, ["E", "A", "B", "C", "F"]);
  assert.deepEqual(api.calls[3].groups, ["E", "D"]);
  assert.equal(res.callsUsed, 4);
  assert.ok(res.warnings.some((w) => w.includes("D")));
});

test("anchor를 직접 지정하면 재기준하지 않고 경고만 낸다", async () => {
  const api = makeApi(world2);
  const res = await compareBrandTrend(
    { ...base, anchor: "A", brands: brands("A", "B", "C", "D", "E", "F") },
    { api, cache: mkCache() }
  );
  assert.equal(res.reanchored, false);
  assert.equal(api.calls.length, 2);
  assert.ok(res.warnings.some((w) => w.includes("D") && w.includes("정밀도")));
});

test("배치가 하나뿐이면 재기준하지 않는다", async () => {
  const api = makeApi({ X: [10000, 10000], Y: [1, 1], Z: [100, 100] });
  const res = await compareBrandTrend({ ...base, brands: brands("X", "Y", "Z") }, { api, cache: mkCache() });
  assert.equal(res.reanchored, false);
  assert.equal(api.calls.length, 1);
  assert.ok(res.warnings.some((w) => w.includes("Y")));
});

test("쇼핑은 category가 필수이고 요청에 category와 keyword가 들어간다", async () => {
  const api = makeApi({ A: [100, 100], B: [50, 50] });
  await assert.rejects(
    compareBrandTrend({ ...base, source: "shopping", brands: brands("A") }, { api, cache: mkCache() }),
    /category/
  );
  const res = await compareBrandTrend(
    { ...base, source: "shopping", category: "CAT1", brands: [{ name: "A", aliases: ["에이"] }, brand("B")] },
    { api, cache: mkCache() }
  );
  assert.equal(api.calls[0].kind, "shopping");
  assert.equal(api.calls[0].req.category, "CAT1");
  // 실제 HUB는 키워드 그룹당 param을 1개만 허용한다 (2026-10-19 확인)
  assert.deepEqual(api.calls[0].req.keyword[0], { name: "A", param: ["A"] });
  assert.ok(res.warnings.some((w) => w.includes("A") && w.includes("별칭")));
});

test("쇼핑에 device를 주면 오류", async () => {
  await assert.rejects(
    compareBrandTrend(
      { ...base, source: "shopping", category: "CAT1", device: "pc", brands: brands("A") },
      { api: makeApi({ A: [1, 1] }), cache: mkCache() }
    ),
    /device/
  );
});

test("쇼핑 결과가 전부 0인 브랜드는 오류 없이 데이터 없음 경고", async () => {
  const api = makeApi({ A: [100, 100], B: [0, 0] });
  const res = await compareBrandTrend(
    { ...base, source: "shopping", category: "CAT1", brands: brands("A", "B") },
    { api, cache: mkCache() }
  );
  assert.ok(res.warnings.some((w) => w.includes("B") && w.includes("데이터 없음")));
});

test("브랜드 이름이 중복되면 오류", async () => {
  await assert.rejects(
    compareBrandTrend({ ...base, brands: brands("A", "A") }, { api: makeApi({ A: [1, 1] }), cache: mkCache() }),
    /중복/
  );
});

test("결과에 환경변수의 비밀 값이 섞이지 않는다", async () => {
  process.env.NCP_APIGW_API_KEY = "SECRET-KEY-123";
  try {
    const res = await compareBrandTrend(
      { ...base, brands: brands("A", "B") },
      { api: makeApi({ A: [100, 100], B: [50, 50] }), cache: mkCache(), counter: new CallCounter() }
    );
    assert.equal(JSON.stringify(res).includes("SECRET-KEY-123"), false);
  } finally {
    delete process.env.NCP_APIGW_API_KEY;
  }
});

test("첫 브랜드에 데이터가 없어도 5개 이하면 오류 없이 경고한다", async () => {
  const res = await compareBrandTrend(
    { ...base, brands: brands("A", "B") },
    { api: makeApi({ A: [0, 0], B: [10, 20] }), cache: mkCache() }
  );
  assert.deepEqual(ratios(res, "B"), [50, 100]);
  assert.ok(res.warnings.some((w) => w.includes("A") && w.includes("데이터 없음")));
});

test("기준 브랜드에 데이터가 없고 배치가 여럿이면 가장 큰 브랜드로 기준을 바꿔 계속한다", async () => {
  const world = { A: [0, 0], B: [100, 100], C: [50, 50], D: [20, 20], E: [10, 10], F: [5, 5] };
  const res = await compareBrandTrend(
    { ...base, brands: brands("A", "B", "C", "D", "E", "F") },
    { api: makeApi(world), cache: mkCache() }
  );
  assert.equal(res.anchor, "B");
  assert.ok(Math.abs(ratios(res, "F")[0] - 5) < 1e-9);
  assert.ok(res.warnings.some((w) => w.includes("A") && w.includes("기준")));
});

test("재기준은 합계가 0인 브랜드를 고르지 않는다", async () => {
  const world = { A: [10000, 10000], B: [0, 0], C: [0, 0], D: [0, 0], E: [50, 50], F: [2, 2] };
  const res = await compareBrandTrend(
    { ...base, brands: brands("A", "B", "C", "D", "E", "F") },
    { api: makeApi(world), cache: mkCache() }
  );
  assert.equal(res.reanchored, true);
  assert.equal(res.anchor, "E");
  assert.ok(res.warnings.some((w) => w.includes("B") && w.includes("데이터 없음")));
});

test("confirm이어도 재기준으로 승인한 호출 수를 넘기지 않고 최대 호출 수를 알려 준다", async () => {
  const api = makeApi(world2);
  const res = await compareBrandTrend(
    { ...base, brands: brands("A", "B", "C", "D", "E", "F"), maxCalls: 1, confirm: true },
    { api, cache: mkCache() }
  );
  assert.equal(res.reanchored, false);
  assert.equal(res.callsUsed, 2);
  assert.equal(res.estimatedCalls, 2);
  assert.equal(res.estimatedCallsMax, 4);
  assert.ok(res.warnings.some((w) => w.includes("예산")));
});

test("나중 배치의 기준 지수가 너무 작으면 그 배치 브랜드에 정밀도 경고를 낸다", async () => {
  const world = { A: [100, 100], B: [100, 100], C: [100, 100], D: [100, 100], E: [100, 100], F: [1e6, 1e6] };
  const res = await compareBrandTrend(
    { ...base, anchor: "A", brands: brands("A", "B", "C", "D", "E", "F") },
    { api: makeApi(world), cache: mkCache() }
  );
  assert.ok(res.warnings.some((w) => w.includes("F") && w.includes("정밀도")));
});

test("키워드가 20개를 넘거나 이름이 비어 있으면 dryRun에서도 먼저 오류", async () => {
  const aliases = Array.from({ length: 20 }, (_, i) => `별칭${i}`);
  await assert.rejects(
    compareBrandTrend(
      { ...base, brands: [{ name: "A", aliases }], dryRun: true },
      { api: makeApi({ A: [1, 1] }), cache: mkCache() }
    ),
    /최대 20개/
  );
  await assert.rejects(
    compareBrandTrend(
      { ...base, brands: [{ name: " ", aliases: [] }], dryRun: true },
      { api: makeApi({ A: [1, 1] }), cache: mkCache() }
    ),
    /비어/
  );
});

// 쇼핑 인사이트처럼 키워드(param[0])로 데이터를 찾는 가짜 API
function makeKeywordApi(worldByKeyword) {
  const calls = [];
  return {
    calls,
    async searchTrend() {
      throw new Error("unused");
    },
    async search() {
      throw new Error("unused");
    },
    async datalabShoppingKeywords(req) {
      calls.push(req.keyword.map((k) => ({ name: k.name, kw: k.param[0] })));
      const vols = req.keyword.map((k) => worldByKeyword[k.param[0]] ?? [0, 0]);
      const max = Math.max(...vols.flat());
      return {
        results: req.keyword.map((k, i) => ({
          title: k.name,
          data: vols[i].map((v, j) => ({ period: periods[j], ratio: max ? (v / max) * 100 : 0 })),
        })),
      };
    },
  };
}

const shop = { ...base, source: "shopping", category: "CAT1" };
const bigB = { name: "천일문 중등 그래머", aliases: ["천일문", "천일문중등그래머"] };

test("쇼핑에서 이름에 데이터가 없으면 별칭을 순서대로 시도한다", async () => {
  const api = makeKeywordApi({ A: [100, 100], 천일문: [40, 40] });
  const res = await compareBrandTrend({ ...shop, brands: [brand("A"), bigB] }, { api, cache: mkCache() });
  assert.equal(api.calls.length, 2);
  assert.deepEqual(api.calls[1], [{ name: "A", kw: "A" }, { name: "천일문 중등 그래머", kw: "천일문" }]);
  assert.ok(Math.abs(ratios(res, "천일문 중등 그래머")[0] - 40) < 1e-9);
  assert.ok(res.warnings.some((w) => w.includes("천일문") && w.includes("별칭으로 조회")));
  assert.equal(res.callsUsed, 2);
});

test("첫 별칭도 비면 다음 별칭까지 시도하고 최대 시도 수를 넘지 않는다", async () => {
  const api = makeKeywordApi({ A: [100, 100], 천일문중등그래머: [30, 30] });
  const res = await compareBrandTrend({ ...shop, brands: [brand("A"), bigB] }, { api, cache: mkCache() });
  assert.equal(api.calls.length, 3);
  assert.ok(Math.abs(ratios(res, "천일문 중등 그래머")[0] - 30) < 1e-9);

  const api2 = makeKeywordApi({ A: [100, 100] });
  const res2 = await compareBrandTrend({ ...shop, brands: [brand("A"), bigB] }, { api: api2, cache: mkCache() });
  assert.equal(api2.calls.length, 3);
  assert.ok(res2.warnings.some((w) => w.includes("천일문 중등 그래머") && w.includes("데이터 없음")));
});

test("모든 브랜드에 데이터가 있으면 별칭을 시도하지 않는다", async () => {
  const api = makeKeywordApi({ A: [100, 100], "천일문 중등 그래머": [50, 50], 천일문: [99, 99] });
  const res = await compareBrandTrend({ ...shop, brands: [brand("A"), bigB] }, { api, cache: mkCache() });
  assert.equal(api.calls.length, 1);
  assert.ok(Math.abs(ratios(res, "천일문 중등 그래머")[0] - 50) < 1e-9);
});

test("별칭 재시도는 승인한 호출 예산을 넘지 않는다", async () => {
  const api = makeKeywordApi({ A: [100, 100], 천일문: [40, 40] });
  const res = await compareBrandTrend(
    { ...shop, brands: [brand("A"), bigB], maxCalls: 1 },
    { api, cache: mkCache() }
  );
  assert.equal(api.calls.length, 1);
  assert.ok(res.warnings.some((w) => w.includes("별칭") && w.includes("예산")));
  assert.ok(res.estimatedCallsMax >= 3);
});
