import test from "node:test";
import assert from "node:assert/strict";
import {
  brandKeywords,
  matchesBrand,
  BrandSchema,
} from "../dist/src/analysis/brand.js";

test("brandKeywords는 완전 동일/대소문자만 다른 항목을 제거하고 공백 차이는 유지한다", () => {
  const kws = brandKeywords({
    name: "그래머인사이드",
    aliases: ["그래머 인사이드", "그래머인사이드", "Grammar Inside", "grammar inside"],
  });
  assert.deepEqual(kws, ["그래머인사이드", "그래머 인사이드", "Grammar Inside"]);
});

test("brandKeywords는 빈 별칭을 버린다", () => {
  assert.deepEqual(brandKeywords({ name: "천일문", aliases: ["", "  "] }), ["천일문"]);
});

test("brandKeywords는 키워드가 21개 이상이면 최대 20개 오류를 던진다", () => {
  const aliases = Array.from({ length: 20 }, (_, i) => `별칭${i}`);
  assert.throws(() => brandKeywords({ name: "이름", aliases }), /최대 20개/);
});

test("matchesBrand는 공백 차이를 무시한다", () => {
  assert.equal(
    matchesBrand("천일문 중등 그래머 후기", { name: "천일문중등그래머", aliases: [] }),
    true
  );
  assert.equal(
    matchesBrand("그래머 수업", { name: "그래머인사이드", aliases: [] }),
    false
  );
});

test("BrandSchema는 aliases 기본값을 빈 배열로 채운다", () => {
  assert.deepEqual(BrandSchema.parse({ name: "천일문" }), { name: "천일문", aliases: [] });
});
