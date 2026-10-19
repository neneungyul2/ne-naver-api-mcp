import test from "node:test";
import assert from "node:assert/strict";
import {
  rescale,
  planBatches,
  estimateTrendCalls,
  pickMedianAnchor,
  AnchorError,
} from "../dist/src/analysis/rescale.js";

const pts = (...ratios) => ratios.map((ratio, i) => ({ period: `2025-0${i + 1}-01`, ratio }));
const ratios = (s) => s.points.map((p) => p.ratio);
const byBrand = (res, b) => res.find((s) => s.brand === b);

test("rescale은 기준 합 비율로 두 번째 배치를 첫 배치 척도로 환산한다", () => {
  const res = rescale("A", [
    { A: pts(100, 50), X: pts(10, 5) },
    { A: pts(50, 25), Y: pts(100, 50) },
  ]);
  assert.deepEqual(ratios(byBrand(res, "A")), [100, 50]);
  assert.deepEqual(ratios(byBrand(res, "X")), [10, 5]);
  assert.deepEqual(ratios(byBrand(res, "Y")), [200, 100]);
});

test("배치가 둘 이상일 때 첫 배치의 기준 값이 전부 0이면 AnchorError", () => {
  assert.throws(
    () => rescale("A", [{ A: pts(0, 0), X: pts(10, 5) }, { A: pts(5, 5), Y: pts(1, 1) }]),
    (e) => e instanceof AnchorError && /기준 브랜드/.test(e.message)
  );
});

test("배치가 하나면 기준 값이 0이어도 환산이 필요 없으니 던지지 않는다", () => {
  const res = rescale("A", [{ A: pts(0, 0), X: pts(10, 5) }]);
  assert.deepEqual(ratios(byBrand(res, "X")), [10, 5]);
  assert.equal(byBrand(res, "A").lowPrecision, true);
});

test("pickMedianAnchor는 합계가 0인 브랜드를 후보에서 뺀다", () => {
  const scaled = [
    { brand: "z1", points: pts(0, 0), lowPrecision: true },
    { brand: "z2", points: pts(0, 0), lowPrecision: true },
    { brand: "z3", points: pts(0, 0), lowPrecision: true },
    { brand: "lo", points: pts(1, 1), lowPrecision: false },
    { brand: "hi", points: pts(9, 9), lowPrecision: false },
  ];
  assert.equal(pickMedianAnchor(scaled), "lo");
  assert.throws(
    () => pickMedianAnchor([{ brand: "z", points: pts(0), lowPrecision: true }]),
    AnchorError
  );
});

test("나중 배치에서 기준의 지수가 임계값 미만이면 그 배치의 브랜드를 lowPrecision으로 표시한다", () => {
  const res = rescale("A", [
    { A: pts(100, 100), X: pts(50, 50) },
    { A: pts(0.5, 0.5), F: pts(100, 100) },
  ]);
  assert.equal(byBrand(res, "F").lowPrecision, true);
  assert.equal(byBrand(res, "X").lowPrecision, false);
});

test("둘째 배치의 기준 합이 0이면 AnchorError", () => {
  assert.throws(
    () =>
      rescale("A", [
        { A: pts(100, 50), X: pts(1, 1) },
        { A: pts(0, 0), Y: pts(100, 50) },
      ]),
    AnchorError
  );
});

test("배치에 기준 키가 없으면 AnchorError", () => {
  assert.throws(
    () => rescale("A", [{ A: pts(1, 1) }, { Y: pts(1, 1) }]),
    AnchorError
  );
});

test("환산 후 최댓값이 임계값 미만이면 lowPrecision", () => {
  const res = rescale("A", [{ A: pts(100, 50), small: pts(0.4, 0.1), big: pts(5, 1) }]);
  assert.equal(byBrand(res, "small").lowPrecision, true);
  assert.equal(byBrand(res, "big").lowPrecision, false);
});

test("planBatches는 기준을 모든 배치 맨 앞에 넣고 나머지를 나눈다", () => {
  assert.deepEqual(planBatches(["A", "B", "C", "D", "E", "F"], "A", 5), [
    ["A", "B", "C", "D", "E"],
    ["A", "F"],
  ]);
  assert.deepEqual(planBatches(["A"], "A", 5), [["A"]]);
  assert.throws(() => planBatches(["A", "B"], "Z", 5));
});

test("estimateTrendCalls", () => {
  assert.equal(estimateTrendCalls(1, 5), 1);
  assert.equal(estimateTrendCalls(5, 5), 1);
  assert.equal(estimateTrendCalls(6, 5), 2);
  assert.equal(estimateTrendCalls(10, 5), 3);
});

test("pickMedianAnchor는 기간 합계가 중앙값인 브랜드를 고른다", () => {
  const scaled = [
    { brand: "lo", points: pts(5, 5), lowPrecision: false },
    { brand: "mid", points: pts(10, 10), lowPrecision: false },
    { brand: "hi", points: pts(15, 15), lowPrecision: false },
  ];
  assert.equal(pickMedianAnchor(scaled), "mid");
});
