"""블로그/카페/웹 글 수집, 브랜드 필터, 월별 집계."""
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal

from ..cache import CallCounter, FileCache, cached_call
from .brand import Brand, matches_brand
from .compare_trend import AnalysisApi

MentionSource = Literal["blog", "cafearticle", "webkr"]

PAGE_SIZE = 100
MAX_START = 1000
_POSTDATE = re.compile(r"([0-9]{4})([0-9]{2})([0-9]{2})")
_TAG = re.compile(r"<[^>]*>")


@dataclass
class Post:
    source: MentionSource
    title: str
    description: str
    link: str
    date: str | None = None  # yyyy-mm-dd. 날짜 정보가 없거나 형식이 다르면 None


@dataclass
class KeptPost(Post):
    brands: list[str] = field(default_factory=list)


def strip_html(text: str) -> str:
    """태그 제거 + 엔티티 복원 (&amp;는 이중 복원을 막으려고 마지막에 처리)."""
    s = _TAG.sub("", text or "")
    for entity, char in (("&quot;", '"'), ("&#39;", "'"), ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " ")):
        s = s.replace(entity, char)
    s = s.replace("&amp;", "&")
    return re.sub(r"\s+", " ", s).strip()


def normalize_post(source: MentionSource, raw: dict) -> Post:
    m = _POSTDATE.fullmatch(str(raw.get("postdate") or ""))
    return Post(
        source=source,
        title=strip_html(str(raw.get("title") or "")),
        description=strip_html(str(raw.get("description") or "")),
        link=str(raw.get("link") or ""),
        date=f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None,
    )


async def collect_posts(
    api: AnalysisApi,
    source: MentionSource,
    query: str,
    max_posts: int,
    cache: FileCache,
    counter: CallCounter,
) -> tuple[list[Post], int]:
    """sort=date로 최근 글부터 최대 max_posts(≤1000)건을 페이지 단위로 수집한다. 링크 기준 중복 제거."""
    cap = min(max_posts, MAX_START)
    posts: list[Post] = []
    seen: set[str] = set()
    total = 0
    start = 1
    while start <= MAX_START and len(posts) < cap:
        params = {"query": query, "display": PAGE_SIZE, "start": start, "sort": "date"}
        response = await cached_call(
            cache, counter, f"search:{source}", params, lambda p=params: api.search(source, p)
        )
        if isinstance(response.get("total"), int):
            total = response["total"]
        items = response.get("items") or []
        if not items:
            break
        for raw in items:
            post = normalize_post(source, raw)
            if post.link in seen:
                continue
            seen.add(post.link)
            posts.append(post)
            if len(posts) >= cap:
                break
        if len(items) < PAGE_SIZE:
            break
        start += PAGE_SIZE
    return posts, total


def filter_by_brands(
    posts: Sequence[Post], brands: Sequence[Brand]
) -> tuple[list[KeptPost], int]:
    """제목+요약에 브랜드 키워드가 있는 글만 남기고 포함된 브랜드명을 붙인다."""
    kept: list[KeptPost] = []
    excluded = 0
    for p in posts:
        text = strip_html(f"{p.title} {p.description}")
        hit = [b.name for b in brands if matches_brand(text, b)]
        if not hit:
            excluded += 1
            continue
        kept.append(KeptPost(p.source, p.title, p.description, p.link, p.date, hit))
    return kept, excluded


def monthly_counts(kept: Sequence[KeptPost]) -> tuple[list[dict], dict[str, int]]:
    """월 × 브랜드 × 소스 건수. 날짜 없는 글은 소스별 undated로 센다."""
    undated = {"blog": 0, "cafearticle": 0, "webkr": 0}
    counts: dict[tuple[str, str, str], int] = {}
    for p in kept:
        if not p.date:
            undated[p.source] += 1
            continue
        month = p.date[:7]
        for brand in p.brands:
            key = (month, brand, p.source)
            counts[key] = counts.get(key, 0) + 1
    rows = [
        {"month": m, "brand": b, "source": s, "count": n} for (m, b, s), n in sorted(counts.items())
    ]
    return rows, undated


def estimate_mention_calls(
    brands: Sequence[Brand],
    sources: Sequence[str],
    queries_per_brand: int,
    max_posts: int,
) -> int:
    pages = math.ceil(min(max_posts, MAX_START) / PAGE_SIZE)
    return len(brands) * len(sources) * queries_per_brand * pages
