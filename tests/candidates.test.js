import test from "node:test";
import assert from "node:assert/strict";
import { extractCandidates, DEFAULT_STOPWORDS } from "../dist/src/analysis/candidates.js";

const A = { name: "그래머인사이드", aliases: [] };
const B = { name: "천일문중등그래머", aliases: [] };
const kp = (over) => ({
  source: "blog",
  title: "",
  description: "",
  link: "l",
  brands: ["그래머인사이드"],
  ...over,
});

test("공통 단어의 총 빈도, 브랜드별 빈도, 예시 문장을 센다", () => {
  const cands = extractCandidates(
    [
      kp({ title: "그래머인사이드 쎄듀 교재", link: "1" }),
      kp({ title: "그래머인사이드 쎄듀 문제집", link: "2" }),
      kp({ title: "천일문중등그래머 쎄듀 비교", link: "3", brands: ["천일문중등그래머"] }),
    ],
    [A, B]
  );
  const c = cands.find((x) => x.term === "쎄듀");
  assert.equal(c.total, 3);
  assert.deepEqual(c.byBrand, { 그래머인사이드: 2, 천일문중등그래머: 1 });
  assert.ok(c.examples.length <= 3);
  assert.ok(c.examples.every((e) => e.length <= 100));
  assert.deepEqual(c.sources, ["blog"]);
});

test("브랜드 키워드, 불용어, 숫자만, 1글자는 후보에서 제외한다", () => {
  const cands = extractCandidates(
    [kp({ title: "그래머인사이드 후기 2024 책 쎄듀", link: "1" })],
    [A, B]
  );
  const terms = cands.map((c) => c.term);
  assert.deepEqual(terms, ["쎄듀"]);
  assert.ok(DEFAULT_STOPWORDS.has("후기"));
});

test("같은 글에서 같은 토큰이 여러 번 나와도 글당 1회로 센다", () => {
  const cands = extractCandidates(
    [kp({ title: "쎄듀 쎄듀 쎄듀", description: "쎄듀", link: "1" })],
    [A]
  );
  assert.equal(cands.find((c) => c.term === "쎄듀").total, 1);
});

test("태그가 후보 토큰으로 나타나지 않는다", () => {
  const cands = extractCandidates(
    [kp({ title: "<b>쎄듀</b> <b>교재</b>", description: "<b>문법</b>", link: "1" })],
    [A]
  );
  const terms = cands.map((c) => c.term);
  assert.ok(terms.includes("쎄듀"));
  assert.equal(terms.some((t) => /[<>]/.test(t) || t === "b"), false);
});

test("top을 지키고 total 내림차순, 같으면 사전순으로 정렬한다", () => {
  const cands = extractCandidates(
    [
      kp({ title: "가나다 라마바 사아자", link: "1" }),
      kp({ title: "가나다 라마바", link: "2" }),
      kp({ title: "가나다", link: "3" }),
    ],
    [A],
    { top: 2 }
  );
  assert.deepEqual(cands.map((c) => c.term), ["가나다", "라마바"]);
  assert.deepEqual(cands.map((c) => c.total), [3, 2]);
});

test("출처 유형을 모은다", () => {
  const cands = extractCandidates(
    [
      kp({ title: "쎄듀", link: "1", source: "blog" }),
      kp({ title: "쎄듀", link: "2", source: "cafearticle" }),
    ],
    [A]
  );
  assert.deepEqual(cands.find((c) => c.term === "쎄듀").sources.sort(), ["blog", "cafearticle"]);
});
