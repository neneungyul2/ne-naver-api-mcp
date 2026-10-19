// 실제 NAVER API HUB를 호출해 코드가 기대는 가정을 확인한다 (호출 약 9회).
// 기본 `npm test`에서는 건너뛴다. 실행: npm run test:live  (.env의 NCP_APIGW_API_KEY_ID/KEY 필요)
import test from "node:test";
import assert from "node:assert/strict";
import { NaverSearchClient } from "../../dist/src/clients/naver-search.client.js";
import { resolveCredentials } from "../../dist/src/config/credentials.js";

const skip = process.env.NAVER_LIVE_TEST === "1" ? false : "NAVER_LIVE_TEST=1 일 때만 실행 (npm run test:live)";

function client() {
  const c = NaverSearchClient.getInstance();
  c.initialize(resolveCredentials(process.env));
  return c;
}
const range = { startDate: "2025-01-01", endDate: "2025-06-30", timeUnit: "month" };
const CATEGORY = "50005951";
const kw = (name) => ({ name, param: [name] });

test("블로그 postdate는 YYYYMMDD이다", { skip }, async () => {
  const res = await client().search("blog", { query: "그래머인사이드", display: 3, sort: "date" });
  assert.ok(res.items.length > 0);
  assert.ok(res.items.every((i) => /^\d{8}$/.test(i.postdate)));
});

test("카페글과 웹문서 항목에는 날짜 필드가 없다 (있게 되면 월별 집계 설계를 바꿀 수 있다)", { skip }, async () => {
  for (const type of ["cafearticle", "webkr"]) {
    const res = await client().search(type, { query: "그래머인사이드", display: 3, sort: "date" });
    assert.ok(res.items.length > 0, type);
    assert.ok(res.items.every((i) => i.postdate === undefined && i.date === undefined), type);
  }
});

test("검색어 트렌드 응답: period는 yyyy-mm-dd, 단일 그룹은 최댓값 100", { skip }, async () => {
  const res = await client().searchTrend({
    ...range,
    keywordGroups: [{ groupName: "그래머인사이드", keywords: ["그래머인사이드", "그래머 인사이드"] }],
  });
  const data = res.results[0].data;
  assert.ok(data.length > 0);
  assert.ok(data.every((d) => /^\d{4}-\d{2}-\d{2}$/.test(d.period) && typeof d.ratio === "number"));
  assert.equal(Math.max(...data.map((d) => d.ratio)), 100);
});

test("쇼핑 키워드 그룹은 5개까지 허용되고 6개는 400이다", { skip }, async () => {
  const names = ["그래머인사이드", "천일문", "쎄듀", "오늘의문법", "중학영문법", "능률보카"];
  const ok = await client().datalabShoppingKeywords({
    ...range,
    category: CATEGORY,
    keyword: names.slice(0, 5).map(kw),
  });
  assert.equal(ok.results.length, 5);
  await assert.rejects(
    client().datalabShoppingKeywords({ ...range, category: CATEGORY, keyword: names.map(kw) }),
    /HTTP 400/
  );
});

test("쇼핑 키워드 그룹의 param은 1개만 허용된다", { skip }, async () => {
  await assert.rejects(
    client().datalabShoppingKeywords({
      ...range,
      category: CATEGORY,
      keyword: [{ name: "그래머인사이드", param: ["그래머인사이드", "그래머 인사이드"] }],
    }),
    /should NOT have more than 1 items/
  );
});
