import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  stripHtml,
  normalizePost,
  collectPosts,
  filterByBrands,
  monthlyCounts,
  estimateMentionCalls,
} from "../dist/src/analysis/mentions.js";
import { FileCache, CallCounter } from "../dist/src/cache/file-cache.js";

const mkCtx = () => ({
  cache: new FileCache({ dir: fs.mkdtempSync(path.join(os.tmpdir(), "men-")), ttlMs: 1e9 }),
  counter: new CallCounter(),
});

// total건이 있는 가짜 검색 API. 페이지별 호출을 기록한다.
function makeSearchApi(total, { dupLink } = {}) {
  const calls = [];
  return {
    calls,
    async search(type, params) {
      calls.push({ type, params });
      const start = params.start ?? 1;
      const display = params.display ?? 10;
      const items = [];
      for (let i = start; i < start + display && i <= total; i++) {
        items.push({
          title: `<b>제목</b> ${i}`,
          link: dupLink && i === 101 ? "https://x/1" : `https://x/${i}`,
          description: `요약 ${i}`,
          postdate: "20250312",
        });
      }
      return { total, start, display, items };
    },
  };
}

test("stripHtml은 태그를 지우고 엔티티를 복원한다", () => {
  assert.equal(stripHtml("<b>천일문</b> &quot;후기&quot; &amp; 정리"), '천일문 "후기" & 정리');
  assert.equal(stripHtml("a &amp;quot; b"), "a &quot; b");
});

test("normalizePost는 postdate를 yyyy-mm-dd로 바꾸고 이상한 값은 date 없음", () => {
  const raw = { title: "<b>t</b>", link: "l", description: "d" };
  assert.equal(normalizePost("blog", { ...raw, postdate: "20250312" }).date, "2025-03-12");
  assert.equal(normalizePost("blog", { ...raw, postdate: "" }).date, undefined);
  assert.equal(normalizePost("blog", { ...raw, postdate: "2025-3" }).date, undefined);
  assert.equal(normalizePost("cafearticle", raw).date, undefined);
  assert.equal(normalizePost("blog", raw).title, "t");
});

test("collectPosts는 date 정렬, display 100으로 페이지를 넘기며 수집한다", async () => {
  const api = makeSearchApi(250);
  const { posts, total } = await collectPosts(api, "blog", "그래머", 1000, mkCtx());
  assert.equal(api.calls.length, 3);
  assert.deepEqual(api.calls.map((c) => c.params.start), [1, 101, 201]);
  assert.equal(api.calls[0].params.sort, "date");
  assert.equal(api.calls[0].params.display, 100);
  assert.equal(api.calls[0].type, "blog");
  assert.equal(posts.length, 250);
  assert.equal(total, 250);
});

test("collectPosts는 maxPosts에서 멈추고 link 중복을 제거한다", async () => {
  const api = makeSearchApi(250);
  const { posts } = await collectPosts(api, "blog", "q", 150, mkCtx());
  assert.equal(api.calls.length, 2);
  assert.equal(posts.length, 150);

  const dup = await collectPosts(makeSearchApi(250, { dupLink: true }), "blog", "q", 250, mkCtx());
  assert.equal(dup.posts.length, 249);
});

test("collectPosts는 빈 페이지가 오면 중단하고 두 번째 실행은 캐시를 쓴다", async () => {
  const ctx = mkCtx();
  const api = makeSearchApi(0);
  const { posts } = await collectPosts(api, "blog", "q", 1000, ctx);
  assert.equal(posts.length, 0);
  assert.equal(api.calls.length, 1);

  const api2 = makeSearchApi(250);
  await collectPosts(api2, "blog", "z", 1000, ctx);
  const used = ctx.counter.used;
  await collectPosts(makeSearchApi(250), "blog", "z", 1000, ctx);
  assert.equal(ctx.counter.used, used);
});

test("collectPosts는 start가 1000을 넘지 않는다", async () => {
  const api = makeSearchApi(5000);
  const { posts } = await collectPosts(api, "blog", "q", 5000, mkCtx());
  assert.equal(api.calls.length, 10);
  assert.equal(Math.max(...api.calls.map((c) => c.params.start)), 901);
  assert.equal(posts.length, 1000);
});

const B1 = { name: "그래머인사이드", aliases: ["그래머 인사이드"] };
const B2 = { name: "천일문중등그래머", aliases: [] };
const post = (over) => ({ source: "blog", title: "", description: "", link: "l", ...over });

test("filterByBrands는 <b>로 쪼개진 제목도 매칭하고 무관한 글은 제외 수에 센다", () => {
  const { kept, excluded } = filterByBrands(
    [
      post({ title: "<b>그래머</b> <b>인사이드</b> 후기", link: "1" }),
      post({ title: "그래머 수업 일반", link: "2" }),
      post({ description: "천일문 중등 그래머와 그래머인사이드 비교", link: "3" }),
    ],
    [B1, B2]
  );
  assert.equal(kept.length, 2);
  assert.equal(excluded, 1);
  assert.deepEqual(kept[0].brands, ["그래머인사이드"]);
  assert.deepEqual(kept[1].brands.sort(), ["그래머인사이드", "천일문중등그래머"].sort());
});

test("monthlyCounts는 월 x 브랜드 x 소스로 세고 날짜 없는 글은 undated", () => {
  const { rows, undated } = monthlyCounts([
    { ...post({ date: "2025-03-12", link: "1" }), brands: ["A"] },
    { ...post({ date: "2025-03-20", link: "2" }), brands: ["A", "B"] },
    { ...post({ date: "2025-04-01", link: "3" }), brands: ["A"] },
    { ...post({ source: "cafearticle", link: "4" }), brands: ["A"] },
  ]);
  const get = (month, brand, source = "blog") =>
    rows.find((r) => r.month === month && r.brand === brand && r.source === source)?.count;
  assert.equal(get("2025-03", "A"), 2);
  assert.equal(get("2025-03", "B"), 1);
  assert.equal(get("2025-04", "A"), 1);
  assert.equal(undated.cafearticle, 1);
  assert.equal(undated.blog, 0);
  assert.equal(rows.some((r) => r.source === "cafearticle"), false);
});

test("estimateMentionCalls", () => {
  assert.equal(estimateMentionCalls([B1, B2], ["blog", "cafearticle"], 1, 1000), 40);
  assert.equal(estimateMentionCalls([B1], ["blog"], 2, 150), 4);
});
