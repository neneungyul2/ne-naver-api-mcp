"""브랜드와 함께 언급된 후보 단어 추출 (브랜드 여부 판별은 호출한 쪽이 한다)."""
import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from .brand import Brand, brand_keywords
from .mentions import KeptPost, MentionSource, Post, strip_html
from .tokenizer import Tokenizer, regex_tokenizer

DEFAULT_STOPWORDS = frozenset(
    {
        "후기", "리뷰", "추천", "구매", "정리", "사용", "이용", "내용", "소개", "비교", "방법",
        "있는", "있다", "합니다", "입니다", "그리고", "하지만", "에서", "이번", "오늘",
    }
)
DEFAULT_GENERIC_RATE = 0.15  # 기준 검색 글의 이 비율 이상에 나오면 일반 단어로 본다
MAX_EXAMPLES = 3
MAX_EXAMPLE_LEN = 100
MAX_PARTICLE_LEN = 2  # 브랜드명 뒤에 붙은 조사로 보는 최대 글자 수 (예: 그래머인사이드는)


@dataclass
class Candidate:
    term: str
    total: int
    by_brand: dict[str, int] = field(default_factory=dict)
    examples: list[str] = field(default_factory=list)
    sources: list[MentionSource] = field(default_factory=list)
    baseline_rate: float | None = None
    lift: float | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "term": self.term,
            "total": self.total,
            "byBrand": self.by_brand,
            "examples": self.examples,
            "sources": self.sources,
        }
        if self.baseline_rate is not None:
            d["baselineRate"] = self.baseline_rate
        if self.lift is not None:
            d["lift"] = self.lift
        return d


def _brand_tokens(brands: Sequence[Brand]) -> tuple[set[str], list[str]]:
    """제외할 토큰 전체(all)와, 조사가 붙은 형태를 찾는 데 쓸 브랜드 전체 이름(whole)."""
    all_tokens: set[str] = set()
    wholes: list[str] = []
    for brand in brands:
        for keyword in brand_keywords(brand):
            squashed = "".join(keyword.split()).lower()
            all_tokens.add(squashed)
            wholes.append(squashed)
            all_tokens.update(w.lower() for w in keyword.split() if w)
    return all_tokens, wholes


def _snippet(pieces: list[str], token: str) -> str:
    piece = next((p for p in pieces if token in p.lower()), pieces[0] if pieces else "")
    return piece[:MAX_EXAMPLE_LEN]


def extract_candidates(
    kept: Sequence[KeptPost],
    brands: Sequence[Brand],
    *,
    top: int = 30,
    stopwords: frozenset[str] | None = None,
    baseline: Sequence[Post] | None = None,
    generic_rate: float = DEFAULT_GENERIC_RATE,
    tokenize: Tokenizer = regex_tokenizer,
) -> list[Candidate]:
    stop = DEFAULT_STOPWORDS if stopwords is None else stopwords
    excluded, wholes = _brand_tokens(brands)

    def with_particle(token: str) -> bool:
        return any(
            len(b) >= 3 and len(token) > len(b) and token.startswith(b)
            and len(token) - len(b) <= MAX_PARTICLE_LEN
            for b in wholes
        )

    baseline_n = len(baseline) if baseline else 0
    baseline_df: dict[str, int] = {}
    for p in baseline or []:
        for t in set(tokenize(f"{strip_html(p.title)} {strip_html(p.description)}")):
            baseline_df[t] = baseline_df.get(t, 0) + 1

    def baseline_rate(token: str) -> float:
        return baseline_df.get(token, 0) / baseline_n

    found: dict[str, Candidate] = {}
    for post in kept:
        title, description = strip_html(post.title), strip_html(post.description)
        pieces = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n", f"{title}. {description}") if s.strip()]
        tokens = set()
        for t in set(tokenize(f"{title} {description}")):
            if t.isdigit() or t in stop or t in excluded or with_particle(t):
                continue
            if baseline_n > 0 and baseline_rate(t) >= generic_rate:
                continue
            tokens.add(t)
        for t in tokens:
            c = found.setdefault(t, Candidate(term=t, total=0))
            c.total += 1
            for b in post.brands:
                c.by_brand[b] = c.by_brand.get(b, 0) + 1
            if len(c.examples) < MAX_EXAMPLES:
                example = _snippet(pieces, t)
                if example and example not in c.examples:
                    c.examples.append(example)
            if post.source not in c.sources:
                c.sources.append(post.source)

    result = list(found.values())
    if baseline_n > 0:
        for c in result:
            rate = baseline_rate(c.term)
            c.baseline_rate = rate
            # 기준 검색에 한 번도 안 나온 단어는 1/(N+1)로 보정해 lift가 무한대가 되지 않게 한다
            c.lift = c.total / len(kept) / max(rate, 1 / (baseline_n + 1))
    result.sort(key=lambda c: (-c.total, c.term))
    return result[:top]
