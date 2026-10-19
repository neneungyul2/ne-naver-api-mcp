import { z } from "zod";

export const MAX_KEYWORDS_PER_BRAND = 20;

export const BrandSchema = z.object({
  name: z.string().min(1).describe("브랜드(제품/시리즈) 이름"),
  aliases: z
    .array(z.string())
    .default([])
    .describe("표기가 다른 별칭 (예: 띄어쓰기, 영문 표기)"),
});

export type Brand = { name: string; aliases: string[] };

/**
 * 검색 키워드 목록. 이름 + 별칭에서 빈 값과 (대소문자 무시) 중복을 제거한다.
 * 공백만 다른 항목은 서로 다른 검색어이므로 유지한다.
 */
export function brandKeywords(brand: Brand): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of [brand.name, ...brand.aliases]) {
    const kw = raw.trim();
    if (!kw) continue;
    const key = kw.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push(kw);
  }
  if (out.length > MAX_KEYWORDS_PER_BRAND) {
    throw new Error(
      `브랜드 "${brand.name}"의 키워드는 최대 ${MAX_KEYWORDS_PER_BRAND}개까지 지정할 수 있습니다 (현재 ${out.length}개).`
    );
  }
  return out;
}

/** 호출 전에 브랜드 입력을 검증한다 (키워드 20개 초과, 이름이 빈 브랜드). */
export function validateBrands(brands: Brand[]): void {
  for (const b of brands) {
    if (brandKeywords(b).length === 0) {
      throw new Error("브랜드 이름이 비어 있습니다. name은 공백이 아닌 문자열이어야 합니다.");
    }
  }
}

function squash(s: string): string {
  return s.replace(/\s+/g, "").toLowerCase();
}

/** 텍스트에 브랜드 키워드가 하나라도 있으면 true. 공백/대소문자 차이는 무시한다. */
export function matchesBrand(text: string, brand: Brand): boolean {
  const haystack = squash(text);
  return brandKeywords(brand).some((kw) => haystack.includes(squash(kw)));
}
