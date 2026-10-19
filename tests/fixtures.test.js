// 실제 NAVER API HUB 응답을 녹화한 샘플(tests/fixtures)로 분석 코드를 검증한다.
// 샘플은 `node scripts/record-fixtures.mjs`로 다시 녹화할 수 있다. 네트워크는 쓰지 않는다.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { compareBrandTrend } from "../dist/src/analysis/compare-trend.js";
import { collectPosts, filterByBrands, normalizePost } from "../dist/src/analysis/mentions.js";
import { FileCache, CallCounter } from "../dist/src/cache/file-cache.js";

const fx = (name) =>
  JSON.parse(fs.readFileSync(new URL(`./fixtures/${name}.json`, import.meta.url), "utf8"));
const mkCache = () =>
  new FileCache({ dir: fs.mkdtempSync(path.join(os.tmpdir(), "fx-")), ttlMs: 1e9 });

const blog = fx("search-blog");
const cafe = fx("search-cafearticle");
const web = fx("search-webkr");
const trend = fx("search-trend");
const shopping = fx("shopping-keywords");
const paramLimit = fx("shopping-param-limit-error");

test("검색 응답 구조: 최상위 키와 항목 필드", () => {
  for (const res of [blog, cafe, web]) {
    assert.deepEqual(Object.keys(res), ["lastBuildDate", "total", "start", "display", "items"]);
    assert.equal(typeof res.total, "number");
  }
  assert.match(blog.items[0].postdate, /^\d{8}$/);
  assert.ok(blog.items.every((i) => /^\d{8}$/.test(i.postdate)));
  assert.ok(cafe.items.every((i) => i.postdate === undefined && i.date === undefined));
  assert.ok(web.items.every((i) => i.postdate === undefined && i.date === undefined));
});

test("실제 블로그 항목을 정규화하면 날짜가 yyyy-mm-dd이고 태그가 없다", () => {
  const posts = blog.items.map((i) => normalizePost("blog", i));
  assert.ok(posts.every((p) => /^\d{4}-\d{2}-\d{2}$/.test(p.date)));
  assert.ok(posts.every((p) => !/[<>]/.test(p.title) && !/[<>]/.test(p.description)));
});

test("카페글과 웹문서는 날짜가 없는 것으로 정규화된다", () => {
  assert.ok(cafe.items.every((i) => normalizePost("cafearticle", i).date === undefined));
  assert.ok(web.items.every((i) => normalizePost("webkr", i).date === undefined));
});

test("실제 응답으로 수집하고 브랜드 필터를 거치면 <b>로 감싸진 브랜드명도 잡힌다", async () => {
  const api = {
    async search(type) {
      return { blog, cafearticle: cafe, webkr: web }[type];
    },
  };
  const { posts, total } = await collectPosts(api, "blog", "그래머인사이드", 100, {
    cache: mkCache(),
    counter: new CallCounter(),
  });
  assert.equal(posts.length, blog.items.length);
  assert.equal(total, blog.total);
  const { kept } = filterByBrands(posts, [{ name: "그래머인사이드", aliases: ["그래머 인사이드"] }]);
  assert.ok(kept.length >= 1);
});

test("검색어 트렌드 응답을 그대로 비교에 쓰면 단일 브랜드는 최댓값이 100이다", async () => {
  const api = { async searchTrend() { return trend; } };
  const res = await compareBrandTrend(
    {
      brands: [{ name: "그래머인사이드", aliases: ["그래머 인사이드"] }],
      source: "search",
      startDate: "2025-01-01",
      endDate: "2025-06-30",
      timeUnit: "month",
    },
    { api, cache: mkCache() }
  );
  assert.equal(res.callsUsed, 1);
  assert.equal(res.series[0].points.length, trend.results[0].data.length);
  assert.equal(Math.max(...res.series[0].points.map((p) => p.ratio)), 100);
});

// 서버의 실제 제한(녹화된 400)을 흉내 내는 쇼핑 API: 그룹 5개 초과, param 2개 이상이면 거절한다
function strictShoppingApi(response) {
  const calls = [];
  return {
    calls,
    async datalabShoppingKeywords(req) {
      calls.push(req);
      if (req.keyword.length > 5 || req.keyword.some((k) => k.param.length > 1)) {
        throw new Error(paramLimit.message);
      }
      return response;
    },
  };
}

test("쇼핑 요청은 실제 서버 제한(그룹당 param 1개, 그룹 5개)을 지킨다", async () => {
  const api = strictShoppingApi(shopping);
  const names = shopping.results.map((r) => r.title);
  const res = await compareBrandTrend(
    {
      brands: [
        { name: names[0], aliases: ["별칭1", "별칭2"] },
        { name: names[1], aliases: ["별칭3"] },
      ],
      source: "shopping",
      category: "50005951",
      startDate: "2024-01-01",
      endDate: "2026-09-30",
      timeUnit: "month",
    },
    { api, cache: mkCache() }
  );
  assert.ok(api.calls.length >= 1);
  assert.ok(res.series.length === 2);
});

test("실제 쇼핑 응답에서 데이터가 빈 브랜드는 데이터 없음 경고로 알린다", async () => {
  const api = strictShoppingApi(shopping);
  const empty = shopping.results.find((r) => r.data.length === 0);
  assert.ok(empty, "샘플에 데이터가 빈 키워드가 있어야 한다");
  const res = await compareBrandTrend(
    {
      brands: shopping.results.map((r) => ({ name: r.title, aliases: [] })),
      source: "shopping",
      category: "50005951",
      startDate: "2024-01-01",
      endDate: "2026-09-30",
      timeUnit: "month",
    },
    { api, cache: mkCache() }
  );
  assert.ok(res.warnings.some((w) => w.includes(empty.title) && w.includes("데이터 없음")));
});

test("서버 오류 메시지는 그대로 전달되고 키 값은 섞이지 않는다", async () => {
  process.env.NCP_APIGW_API_KEY = "SECRET-KEY-123";
  try {
    const api = {
      async datalabShoppingKeywords() {
        throw new Error(paramLimit.message);
      },
    };
    await assert.rejects(
      compareBrandTrend(
        {
          brands: [{ name: "A", aliases: [] }],
          source: "shopping",
          category: "50005951",
          startDate: "2024-01-01",
          endDate: "2026-09-30",
          timeUnit: "month",
        },
        { api, cache: mkCache() }
      ),
      (e) => /should NOT have more than 1 items/.test(e.message) && !e.message.includes("SECRET-KEY-123")
    );
  } finally {
    delete process.env.NCP_APIGW_API_KEY;
  }
});
