import { CallCounter, FileCache, cachedCall } from "../cache/file-cache.js";
import { Brand, matchesBrand } from "./brand.js";
import type { AnalysisApi } from "./compare-trend.js";

export type MentionSource = "blog" | "cafearticle" | "webkr";
export type Post = {
  source: MentionSource;
  title: string;
  description: string;
  link: string;
  /** yyyy-mm-dd. 날짜 정보가 없거나 형식이 다르면 undefined */
  date?: string;
};
export type KeptPost = Post & { brands: string[] };

const PAGE_SIZE = 100;
const MAX_START = 1000;

/** 태그 제거 + 엔티티 복원 (&amp;는 이중 복원을 막으려고 마지막에 처리) */
export function stripHtml(s: string): string {
  return (s ?? "")
    .replace(/<[^>]*>/g, "")
    .replace(/&quot;/g, '"')
    .replace(/&#39;/g, "'")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/\s+/g, " ")
    .trim();
}

export function normalizePost(source: MentionSource, raw: any): Post {
  const m = /^(\d{4})(\d{2})(\d{2})$/.exec(String(raw?.postdate ?? ""));
  return {
    source,
    title: stripHtml(String(raw?.title ?? "")),
    description: stripHtml(String(raw?.description ?? "")),
    link: String(raw?.link ?? ""),
    ...(m ? { date: `${m[1]}-${m[2]}-${m[3]}` } : {}),
  };
}

/** sort=date로 최대 maxPosts(≤1000)건을 페이지 단위로 수집한다. link 기준 중복 제거. */
export async function collectPosts(
  api: AnalysisApi,
  source: MentionSource,
  query: string,
  maxPosts: number,
  ctx: { cache: FileCache; counter: CallCounter }
): Promise<{ posts: Post[]; total: number }> {
  const cap = Math.min(maxPosts, MAX_START);
  const posts: Post[] = [];
  const seen = new Set<string>();
  let total = 0;
  for (let start = 1; start <= MAX_START && posts.length < cap; start += PAGE_SIZE) {
    const params = { query, display: PAGE_SIZE, start, sort: "date" as const };
    const res = await cachedCall(ctx.cache, ctx.counter, `search:${source}`, params, () =>
      api.search(source, params)
    );
    total = typeof res?.total === "number" ? res.total : total;
    const items: any[] = res?.items ?? [];
    if (items.length === 0) break;
    for (const raw of items) {
      const post = normalizePost(source, raw);
      if (seen.has(post.link)) continue;
      seen.add(post.link);
      posts.push(post);
      if (posts.length >= cap) break;
    }
    if (items.length < PAGE_SIZE) break;
  }
  return { posts, total };
}

/** 제목+요약에 브랜드 키워드가 있는 글만 남기고, 포함된 브랜드명을 붙인다. */
export function filterByBrands(
  posts: Post[],
  brands: Brand[]
): { kept: KeptPost[]; excluded: number } {
  const kept: KeptPost[] = [];
  let excluded = 0;
  for (const p of posts) {
    const text = stripHtml(`${p.title} ${p.description}`);
    const hit = brands.filter((b) => matchesBrand(text, b)).map((b) => b.name);
    if (hit.length === 0) {
      excluded++;
    } else {
      kept.push({ ...p, brands: hit });
    }
  }
  return { kept, excluded };
}

export function monthlyCounts(kept: KeptPost[]): {
  rows: Array<{ month: string; brand: string; source: MentionSource; count: number }>;
  undated: Record<MentionSource, number>;
} {
  const undated: Record<MentionSource, number> = { blog: 0, cafearticle: 0, webkr: 0 };
  const map = new Map<string, { month: string; brand: string; source: MentionSource; count: number }>();
  for (const p of kept) {
    if (!p.date) {
      undated[p.source]++;
      continue;
    }
    const month = p.date.slice(0, 7);
    for (const brand of p.brands) {
      const key = `${month}\u0000${brand}\u0000${p.source}`;
      const row = map.get(key) ?? { month, brand, source: p.source, count: 0 };
      row.count++;
      map.set(key, row);
    }
  }
  const rows = [...map.values()].sort(
    (a, b) =>
      a.month.localeCompare(b.month) ||
      a.brand.localeCompare(b.brand) ||
      a.source.localeCompare(b.source)
  );
  return { rows, undated };
}

export function estimateMentionCalls(
  brands: Brand[],
  sources: MentionSource[],
  queriesPerBrand: number,
  maxPosts: number
): number {
  const pages = Math.ceil(Math.min(maxPosts, MAX_START) / PAGE_SIZE);
  return brands.length * sources.length * queriesPerBrand * pages;
}

