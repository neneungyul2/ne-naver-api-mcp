import { createHash } from "node:crypto";
import { promises as fs } from "node:fs";
import os from "node:os";
import path from "node:path";

/** 키 순서와 무관하게 같은 문자열이 되도록 객체 키를 정렬해 직렬화한다. */
function stableStringify(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    const obj = value as Record<string, unknown>;
    return `{${Object.keys(obj)
      .sort()
      .map((k) => `${JSON.stringify(k)}:${stableStringify(obj[k])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value) ?? "null";
}

export function cacheKey(endpoint: string, params: unknown): string {
  return createHash("sha256")
    .update(`${endpoint}\n${stableStringify(params)}`)
    .digest("hex");
}

export interface FileCacheOptions {
  dir: string;
  ttlMs: number;
  now?: () => number;
}

/** 응답 값만 파일로 저장하는 TTL 캐시. params/헤더는 저장하지 않는다. */
export class FileCache {
  private readonly now: () => number;

  constructor(private readonly opts: FileCacheOptions) {
    this.now = opts.now ?? Date.now;
  }

  private file(key: string): string {
    return path.join(this.opts.dir, `${key}.json`);
  }

  async get<T>(key: string): Promise<T | undefined> {
    try {
      const raw = JSON.parse(await fs.readFile(this.file(key), "utf8"));
      if (typeof raw?.savedAt !== "number") return undefined;
      if (this.now() - raw.savedAt > this.opts.ttlMs) return undefined;
      return raw.value as T;
    } catch {
      return undefined;
    }
  }

  async set(key: string, value: unknown): Promise<void> {
    await fs.mkdir(this.opts.dir, { recursive: true });
    await fs.writeFile(
      this.file(key),
      JSON.stringify({ savedAt: this.now(), value }),
      "utf8"
    );
  }
}

/** 환경변수(NAVER_CACHE_DIR, NAVER_CACHE_TTL_HOURS)를 읽어 캐시를 만든다. */
export function defaultCache(): FileCache {
  const dir =
    process.env.NAVER_CACHE_DIR?.trim() ||
    path.join(os.homedir(), ".naver-search-mcp", "cache");
  const hours = Number(process.env.NAVER_CACHE_TTL_HOURS);
  const ttlHours = Number.isFinite(hours) && hours > 0 ? hours : 24;
  return new FileCache({ dir, ttlMs: ttlHours * 3600 * 1000 });
}

export class CallCounter {
  used = 0;
  hit = 0;
  increment(): void {
    this.used++;
  }
  recordHit(): void {
    this.hit++;
  }
}

/** 캐시에 있으면 hit만 세고, 없으면 fn 호출 후 used를 세고 저장한다. */
export async function cachedCall<T>(
  cache: FileCache,
  counter: CallCounter,
  endpoint: string,
  params: unknown,
  fn: () => Promise<T>
): Promise<T> {
  const key = cacheKey(endpoint, params);
  const hit = await cache.get<T>(key);
  if (hit !== undefined) {
    counter.recordHit();
    return hit;
  }
  const value = await fn();
  counter.increment();
  await cache.set(key, value);
  return value;
}
