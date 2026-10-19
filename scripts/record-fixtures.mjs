// 실제 NAVER API HUB 응답을 tests/fixtures/ 에 녹화한다 (호출 8회).
// 사용: npm run build && node scripts/record-fixtures.mjs   (.env의 NCP_APIGW_API_KEY_ID/KEY 사용)
// 제3자 콘텐츠(블로그/카페 글의 제목, 요약, 주소, 이름)는 합성 값으로 바꾸고, 키 값이 섞였는지 확인한다.
import "dotenv/config";
import fs from "node:fs";
import { NaverSearchClient } from "../dist/src/clients/naver-search.client.js";
import { resolveCredentials } from "../dist/src/config/credentials.js";

const credentials = resolveCredentials(process.env);
const client = NaverSearchClient.getInstance();
client.initialize(credentials);

const OUT = "tests/fixtures";
fs.mkdirSync(OUT, { recursive: true });

// 공개 저장소에 올라가므로 제3자 글의 제목/요약은 합성 텍스트로 바꾼다 (구조와 날짜 형식만 실제 값)
const scrubItem = (item, i) => ({
  ...item,
  title: `<b>그래머인사이드</b> 샘플 제목 ${i + 1}`,
  description: `샘플 요약입니다. <b>그래머인사이드</b> 문법 교재 예시 문장 ${i + 1}.`,
  link: `https://example.invalid/post/${i}`,
  ...(item.bloggername !== undefined
    ? { bloggername: "example", bloggerlink: `https://example.invalid/blog/${i}` }
    : {}),
  ...(item.cafename !== undefined
    ? { cafename: "example", cafeurl: `https://example.invalid/cafe/${i}` }
    : {}),
});

function save(name, value) {
  const text = JSON.stringify(value, null, 2);
  for (const secret of [credentials.clientId, credentials.clientSecret]) {
    if (secret && text.includes(secret)) throw new Error(`${name}: 키 값이 섞였습니다. 저장하지 않습니다.`);
  }
  fs.writeFileSync(`${OUT}/${name}.json`, text + "\n", "utf8");
  console.log("saved", name);
}

for (const type of ["blog", "cafearticle", "webkr"]) {
  const res = await client.search(type, { query: "그래머인사이드", display: 3, sort: "date" });
  save(`search-${type}`, { ...res, items: res.items.map(scrubItem) });
}

const range = { startDate: "2025-01-01", endDate: "2025-06-30", timeUnit: "month" };
save(
  "search-trend",
  await client.searchTrend({
    ...range,
    keywordGroups: [{ groupName: "그래머인사이드", keywords: ["그래머인사이드", "그래머 인사이드"] }],
  })
);

const shopRange = { startDate: "2024-01-01", endDate: "2026-09-30", timeUnit: "month" };
const kw = (name) => ({ name, param: [name] });
save(
  "shopping-keywords",
  await client.datalabShoppingKeywords({
    ...shopRange,
    category: "50005951",
    keyword: [kw("그래머인사이드"), kw("천일문 중등 그래머")],
  })
);

// 키워드 그룹당 param 2개 이상은 400 (실제 확인된 제한)
try {
  await client.datalabShoppingKeywords({
    ...shopRange,
    category: "50005951",
    keyword: [{ name: "그래머인사이드", param: ["그래머인사이드", "그래머 인사이드"] }],
  });
  throw new Error("400이 예상됐지만 성공했습니다");
} catch (e) {
  const message = String(e.message).split("\n").slice(0, 2).join("\n").replace(/"errId":"[^"]*",?/, "");
  save("shopping-param-limit-error", { status: 400, message });
}
