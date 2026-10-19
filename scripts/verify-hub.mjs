// NAVER API HUB 실제 경로/응답 형식 확인용 스크립트 (호출 약 15회).
// 사용: npm run build && node scripts/verify-hub.mjs   (.env의 NCP_APIGW_API_KEY_ID/KEY 사용)
// 키 값은 출력하지 않는다. 응답은 최상위 키와 첫 항목의 키 구조만 보여 준다.
import "dotenv/config";
import { NaverSearchClient } from "../dist/src/clients/naver-search.client.js";
import { resolveCredentials } from "../dist/src/config/credentials.js";

const credentials = resolveCredentials(process.env);
if (credentials.provider !== "hub") {
  console.error("NAVER API HUB 키(NCP_APIGW_API_KEY_ID/KEY)가 필요합니다.");
  process.exit(1);
}
const client = NaverSearchClient.getInstance();
client.initialize(credentials);

const CATEGORY = "50005951"; // 도서 > 국어/외국어 > 영어 > 문법/독해/작문
const range = { startDate: "2025-01-01", endDate: "2025-06-30", timeUnit: "month" };
let calls = 0;

const shape = (v, depth = 0) => {
  if (Array.isArray(v)) return v.length ? [`[${v.length}] ` + JSON.stringify(shape(v[0], depth + 1))] : [];
  if (v && typeof v === "object") {
    return Object.fromEntries(
      Object.entries(v).map(([k, x]) => [k, depth > 2 ? typeof x : shape(x, depth + 1)])
    );
  }
  return typeof v;
};

async function probe(label, fn) {
  calls++;
  try {
    const res = await fn();
    console.log(`OK   ${label}`);
    return res;
  } catch (e) {
    const msg = String(e?.message ?? e).split("\n").slice(0, 2).join(" | ").slice(0, 300);
    console.log(`FAIL ${label} :: ${msg}`);
    return undefined;
  }
}

const kw = (name) => ({ name, param: [name] });

// 1) 검색 3종
for (const type of ["blog", "cafearticle", "webkr"]) {
  const res = await probe(`search/${type}`, () =>
    client.search(type, { query: "그래머인사이드", display: 3, sort: "date" })
  );
  if (res) {
    console.log("   top-level keys:", Object.keys(res).join(","), "| total:", res.total);
    console.log("   item keys:", Object.keys(res.items?.[0] ?? {}).join(","));
    console.log("   item dates:", (res.items ?? []).map((i) => i.postdate ?? i.date ?? "(none)").join(","));
  }
}

// 2) 검색어 트렌드
const trend = await probe("search-trend", () =>
  client.searchTrend({
    ...range,
    keywordGroups: [{ groupName: "그래머인사이드", keywords: ["그래머인사이드", "그래머 인사이드"] }],
  })
);
if (trend) console.log("   shape:", JSON.stringify(shape(trend)));

// 3) 쇼핑 인사이트 8종 경로
const shopping = [
  ["shopping/categories", () => client.datalabShoppingCategory({ ...range, category: [{ name: "영어문법", param: [CATEGORY] }] })],
  ["shopping/category/keywords", () => client.datalabShoppingKeywords({ ...range, category: CATEGORY, keyword: [kw("그래머인사이드")] })],
  ["shopping/category/device", () => client.datalabShoppingByDevice({ ...range, category: CATEGORY, device: "mo" })],
  ["shopping/category/gender", () => client.datalabShoppingByGender({ ...range, category: CATEGORY, gender: "f" })],
  ["shopping/category/age", () => client.datalabShoppingByAge({ ...range, category: CATEGORY, ages: ["10", "20"] })],
  ["shopping/category/keyword/device", () => client.datalabShoppingKeywordByDevice({ ...range, category: CATEGORY, keyword: "그래머인사이드", device: "mo" })],
  ["shopping/category/keyword/gender", () => client.datalabShoppingKeywordByGender({ ...range, category: CATEGORY, keyword: "그래머인사이드", gender: "f" })],
  ["shopping/category/keyword/age", () => client.datalabShoppingKeywordByAge({ ...range, category: CATEGORY, keyword: "그래머인사이드", ages: ["10", "20"] })],
];
for (const [label, fn] of shopping) {
  const res = await probe(label, fn);
  if (res && label === "shopping/category/keywords") {
    console.log("   shape:", JSON.stringify(shape(res)));
    console.log("   points:", (res.results?.[0]?.data ?? []).length, "keyword echo:", JSON.stringify(res.results?.[0]?.keyword));
  }
}

// 4) 쇼핑 키워드 그룹 개수 한도 (5개, 6개)
for (const n of [5, 6]) {
  const names = ["그래머인사이드", "천일문", "쎄듀", "오늘의문법", "중학영문법", "능률보카"].slice(0, n);
  await probe(`shopping keywords x${n} groups`, () =>
    client.datalabShoppingKeywords({ ...range, category: CATEGORY, keyword: names.map(kw) })
  );
}

console.log(`\n호출 ${calls}회`);
