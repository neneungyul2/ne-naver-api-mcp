import { Brand, brandKeywords } from "./brand.js";
import { KeptPost, MentionSource, Post, stripHtml } from "./mentions.js";

export type Candidate = {
  term: string;
  total: number;
  byBrand: Record<string, number>;
  examples: string[];
  sources: MentionSource[];
  /** 기준 검색 결과 글 중 이 단어가 나온 비율 (기준 검색을 줬을 때만) */
  baselineRate?: number;
  /** (브랜드 글에서의 비율) / (기준 검색에서의 비율). 클수록 이 브랜드 글에 특징적인 단어 */
  lift?: number;
};

/** 기준 검색 글에서 이 비율 이상 나오는 단어는 일반 단어로 보고 후보에서 뺀다 */
export const DEFAULT_GENERIC_RATE = 0.15;
/** 브랜드명 뒤에 붙은 조사로 보는 최대 글자 수 (예: 그래머인사이드는) */
const MAX_PARTICLE_LEN = 2;

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

/**
 * 브랜드 키워드 전체(whole)와 그 키워드를 이루는 단어들(공백 기준)을 비교용으로 모은다.
 * all은 후보에서 제외할 토큰, whole은 조사가 붙은 형태를 찾는 데 쓴다.
 */
function brandTokens(brands: Brand[]): { all: Set<string>; whole: string[] } {
  const all = new Set<string>();
  const whole: string[] = [];
  for (const b of brands) {
    for (const kw of brandKeywords(b)) {
      const squashed = kw.replace(/\s+/g, "").toLowerCase();
      all.add(squashed);
      whole.push(squashed);
      for (const w of kw.split(/\s+/)) if (w) all.add(w.toLowerCase());
    }
  }
  return { all, whole };
}

/** 문장 하나에서 후보가 될 수 있는 토큰들 (중복 제거) */
function tokensOf(text: string): Set<string> {
  const out = new Set<string>();
  for (const m of text.matchAll(TOKEN)) out.add(m[0].toLowerCase());
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
  opts: {
    top?: number;
    stopwords?: Set<string>;
    /** 해당 카테고리의 일반 검색 결과 글들. 주면 흔한 단어를 걸러내고 lift를 계산한다. */
    baseline?: Post[];
    genericRate?: number;
  } = {}
): Candidate[] {
  const top = opts.top ?? 30;
  const stop = opts.stopwords ?? DEFAULT_STOPWORDS;
  const genericRate = opts.genericRate ?? DEFAULT_GENERIC_RATE;
  const { all: excluded, whole: brandWholes } = brandTokens(brands);
  const withParticle = (t: string) =>
    brandWholes.some(
      (b) => b.length >= 3 && t.length > b.length && t.startsWith(b) && t.length - b.length <= MAX_PARTICLE_LEN
    );
  const map = new Map<string, Candidate>();

  const baselineDf = new Map<string, number>();
  const baselineN = opts.baseline?.length ?? 0;
  for (const p of opts.baseline ?? []) {
    for (const t of tokensOf(`${stripHtml(p.title)} ${stripHtml(p.description)}`)) {
      baselineDf.set(t, (baselineDf.get(t) ?? 0) + 1);
    }
  }
  const baselineRateOf = (t: string) => (baselineDf.get(t) ?? 0) / baselineN;

  for (const post of kept) {
    const title = stripHtml(post.title);
    const description = stripHtml(post.description);
    const pieces = `${title}. ${description}`
      .split(/(?<=[.!?])\s+|\n/)
      .map((s) => s.trim())
      .filter(Boolean);
    const tokens = new Set<string>();
    for (const t of tokensOf(`${title} ${description}`)) {
      if (/^\d+$/.test(t) || stop.has(t) || excluded.has(t) || withParticle(t)) continue;
      if (baselineN > 0 && baselineRateOf(t) >= genericRate) continue;
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

  const result = [...map.values()];
  if (baselineN > 0) {
    for (const c of result) {
      const rate = baselineRateOf(c.term);
      c.baselineRate = rate;
      // 기준 검색에 한 번도 안 나온 단어는 1/(N+1)로 보정해 lift가 무한대가 되지 않게 한다
      c.lift = c.total / kept.length / Math.max(rate, 1 / (baselineN + 1));
    }
  }
  return result
    .sort((a, b) => b.total - a.total || a.term.localeCompare(b.term))
    .slice(0, top);
}
