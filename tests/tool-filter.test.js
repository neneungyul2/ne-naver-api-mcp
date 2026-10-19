import test from "node:test";
import assert from "node:assert/strict";
import { parseToolAllowList, applyToolFilter } from "../dist/src/analysis/tool-filter.js";

test("parseToolAllowList는 비어 있으면 null(전체 허용)", () => {
  assert.equal(parseToolAllowList(undefined), null);
  assert.equal(parseToolAllowList(""), null);
  assert.equal(parseToolAllowList("  , "), null);
});

test("parseToolAllowList는 쉼표 구분 이름의 Set을 만든다", () => {
  assert.deepEqual(
    [...parseToolAllowList(" search_blog , brand_mentions ")].sort(),
    ["brand_mentions", "search_blog"]
  );
});

test("applyToolFilter는 허용 목록에 있는 도구만 원본에 등록한다", () => {
  const registered = [];
  const server = { registerTool: (name) => registered.push(name) };
  applyToolFilter(server, new Set(["a", "c"]));
  server.registerTool("a", {}, () => {});
  server.registerTool("b", {}, () => {});
  server.registerTool("c", {}, () => {});
  assert.deepEqual(registered, ["a", "c"]);
});

test("applyToolFilter는 null이면 전부 등록한다", () => {
  const registered = [];
  const server = { registerTool: (name) => registered.push(name) };
  applyToolFilter(server, null);
  server.registerTool("a", {}, () => {});
  server.registerTool("b", {}, () => {});
  assert.deepEqual(registered, ["a", "b"]);
});
