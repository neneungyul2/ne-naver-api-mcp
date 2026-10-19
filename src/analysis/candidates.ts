import { Brand, brandKeywords } from "./brand.js";
import { KeptPost, MentionSource, stripHtml } from "./mentions.js";

export type Candidate = {
  term: string;
  total: number;
  byBrand: Record<string, number>;
  examples: string[];
  sources: MentionSource[];
};

/** 후보에서 뺄 일반 단어 (교재 블로그에서 어디에나 나오는 말) */
export const DEFAULT_STOPWORDS = new Set([
  "후기",
  "리뷰",
  "추천",
  "구매",
  "정리",
  "사용",
  "이용",
  "내용",
  "소개",
  "비교",
  "방법",
  "있는",
  "있다",
  "합니다",
  "입니다",
  "그리고",
  "하지만",
  "에서",
  "이번",
  "오늘",
]);

const MAX_EXAMPLES = 3;
const MAX_EXAMPLE_LEN = 100;
const TOKEN = /[가-힣A-Za-z0-9]{2,}/g;

/** 브랜드 키워드 전체와 그 키워드를 이루는 단어들(공백 기준)을 비교용으로 모은다. */
function brandTokens(brands: Brand[]): Set<string> {
  const out = new Set<string>();
  for (const b of brands) {
    for (const kw of brandKeywords(b)) {
      out.add(kw.replace(/\s+/g, "").toLowerCase());
      for (const w of kw.split(/\s+/)) if (w) out.add(w.toLowerCase());
    }
  }
  return out;
}

function snippetFor(pieces: string[], token: string): string {
  const piece = pieces.find((p) => p.toLowerCase().includes(token)) ?? pieces[0] ?? "";
  return piece.slice(0, MAX_EXAMPLE_LEN);
}

/**
 * 브랜드와 함께 언급된 후보 단어를 센다. 형태소 분석은 하지 않는다(조사가 붙은
 * 형태는 별개 토큰). 브랜드 판별은 호출한 쪽(Claude)이 한다.
 */
export function extractCandidates(
  kept: KeptPost[],
  brands: Brand[],
  opts: { top?: number; stopwords?: Set<string> } = {}
): Candidate[] {
  const top = opts.top ?? 30;
  const stop = opts.stopwords ?? DEFAULT_STOPWORDS;
  const excluded = brandTokens(brands);
  const map = new Map<string, Candidate>();

  for (const post of kept) {
    const title = stripHtml(post.title);
    const description = stripHtml(post.description);
    const pieces = `${title}. ${description}`
      .split(/(?<=[.!?])\s+|\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    const tokens = new Set<string>();
    for (const m of `${title} ${description}`.matchAll(TOKEN)) {
      const t = m[0].toLowerCase();
      if (/^\d+$/.test(t) || stop.has(t) || excluded.has(t)) continue;
      tokens.add(t);
    }
    for (const t of tokens) {
      const c =
        map.get(t) ?? { term: t, total: 0, byBrand: {}, examples: [], sources: [] };
      c.total++;
      for (const b of post.brands) c.byBrand[b] = (c.byBrand[b] ?? 0) + 1;
      if (c.examples.length < MAX_EXAMPLES) {
        const ex = snippetFor(pieces, t);
        if (ex && !c.examples.includes(ex)) c.examples.push(ex);
      }
      if (!c.sources.includes(post.source)) c.sources.push(post.source);
      map.set(t, c);
    }
  }

  return [...map.values()]
    .sort((a, b) => b.total - a.total || a.term.localeCompare(b.term))
    .slice(0, top);
}
