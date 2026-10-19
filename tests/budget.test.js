import test from "node:test";
import assert from "node:assert/strict";
import { checkBudget, BudgetExceededError } from "../dist/src/analysis/budget.js";

test("기본 상한 30을 넘으면 confirm 없이는 던진다", () => {
  assert.throws(() => checkBudget({ estimated: 31 }), (e) => {
    assert.ok(e instanceof BudgetExceededError);
    assert.equal(e.estimated, 31);
    assert.equal(e.maxCalls, 30);
    assert.match(e.message, /confirm/);
    return true;
  });
});

test("confirm이 true거나 상한 이내면 통과한다", () => {
  checkBudget({ estimated: 31, confirm: true });
  checkBudget({ estimated: 30 });
});

test("maxCalls를 지정하면 그 값이 상한이다", () => {
  assert.throws(() => checkBudget({ estimated: 6, maxCalls: 5 }), BudgetExceededError);
});
