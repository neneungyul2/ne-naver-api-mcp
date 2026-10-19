import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  cacheKey,
  FileCache,
  CallCounter,
  cachedCall,
} from "../dist/src/cache/file-cache.js";

const tmp = () => fs.mkdtempSync(path.join(os.tmpdir(), "naver-cache-"));

test("cacheKey는 키 순서와 무관하고 엔드포인트가 다르면 다르다", () => {
  assert.equal(cacheKey("/a", { x: 1, y: 2 }), cacheKey("/a", { y: 2, x: 1 }));
  assert.notEqual(cacheKey("/a", { x: 1 }), cacheKey("/b", { x: 1 }));
});

test("FileCache는 저장한 값을 돌려주고 TTL이 지나면 undefined", async () => {
  let t = 1000;
  const cache = new FileCache({ dir: tmp(), ttlMs: 500, now: () => t });
  await cache.set("k", { a: 1 });
  assert.deepEqual(await cache.get("k"), { a: 1 });
  t += 501;
  assert.equal(await cache.get("k"), undefined);
});

test("FileCache는 깨진 파일을 undefined로 처리한다", async () => {
  const dir = tmp();
  fs.writeFileSync(path.join(dir, "bad.json"), "{not json");
  const cache = new FileCache({ dir, ttlMs: 1000 });
  assert.equal(await cache.get("bad"), undefined);
});

test("cachedCall은 같은 인자로 두 번 호출해도 fn을 한 번만 부른다", async () => {
  const cache = new FileCache({ dir: tmp(), ttlMs: 10000 });
  const counter = new CallCounter();
  let calls = 0;
  const fn = async () => {
    calls++;
    return { ok: true };
  };
  await cachedCall(cache, counter, "/e", { q: 1 }, fn);
  await cachedCall(cache, counter, "/e", { q: 1 }, fn);
  assert.equal(calls, 1);
  assert.equal(counter.used, 1);
  assert.equal(counter.hit, 1);
});

test("캐시 파일에는 params(키 포함 가능 값)를 저장하지 않는다", async () => {
  const dir = tmp();
  const cache = new FileCache({ dir, ttlMs: 10000 });
  await cachedCall(cache, new CallCounter(), "/e", { token: "SECRET-KEY-123" }, async () => ({
    ok: 1,
  }));
  for (const f of fs.readdirSync(dir)) {
    assert.equal(fs.readFileSync(path.join(dir, f), "utf8").includes("SECRET-KEY-123"), false);
  }
});
