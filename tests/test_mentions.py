import pytest

from ne_naver_api_mcp.analysis.brand import Brand
from ne_naver_api_mcp.analysis.mentions import (
    KeptPost,
    Post,
    collect_posts,
    estimate_mention_calls,
    filter_by_brands,
    monthly_counts,
    normalize_post,
    strip_html,
)
from ne_naver_api_mcp.cache import CallCounter, FileCache


@pytest.fixture
def ctx(tmp_path):
    return FileCache(tmp_path / "cache", ttl_ms=10**9), CallCounter()


class SearchApi:
    """total건이 있는 가짜 검색 API. 페이지별 호출을 기록한다."""

    def __init__(self, total: int, dup_link: bool = False):
        self.total, self.dup_link = total, dup_link
        self.calls: list[tuple[str, dict]] = []

    async def search(self, type: str, params: dict) -> dict:
        self.calls.append((type, dict(params)))
        start, display = params.get("start", 1), params.get("display", 10)
        items = []
        for i in range(start, min(start + display, self.total + 1)):
            link = "https://x/1" if self.dup_link and i == 101 else f"https://x/{i}"
            items.append(
                {"title": f"<b>제목</b> {i}", "link": link, "description": f"요약 {i}", "postdate": "20250312"}
            )
        return {"total": self.total, "start": start, "display": display, "items": items}


def test_strip_html_removes_tags_and_decodes_entities():
    assert strip_html('<b>천일문</b> &quot;후기&quot; &amp; 정리') == '천일문 "후기" & 정리'
    assert strip_html("a &amp;quot; b") == "a &quot; b"  # 이중 복원 방지
    assert strip_html("a&nbsp;&nbsp;b   c") == "a b c"
    assert strip_html("it&#39;s &lt;x&gt;") == "it's <x>"


def test_normalize_post_parses_postdate_and_tolerates_bad_values():
    raw = {"title": "<b>t</b>", "link": "l", "description": "d"}
    assert normalize_post("blog", {**raw, "postdate": "20250312"}).date == "2025-03-12"
    assert normalize_post("blog", {**raw, "postdate": ""}).date is None
    assert normalize_post("blog", {**raw, "postdate": "2025-3"}).date is None
    assert normalize_post("cafearticle", raw).date is None
    assert normalize_post("blog", raw).title == "t"


async def test_collect_posts_pages_by_date_with_display_100(ctx):
    api = SearchApi(250)
    posts, total = await collect_posts(api, "blog", "그래머", 1000, *ctx)
    assert [c[1]["start"] for c in api.calls] == [1, 101, 201]
    assert api.calls[0][1]["sort"] == "date" and api.calls[0][1]["display"] == 100
    assert api.calls[0][0] == "blog"
    assert len(posts) == 250 and total == 250


async def test_collect_posts_stops_at_max_posts_and_dedupes_links(ctx):
    api = SearchApi(250)
    posts, _ = await collect_posts(api, "blog", "q", 150, *ctx)
    assert len(api.calls) == 2 and len(posts) == 150

    # 검색어를 바꿔 위 호출의 캐시를 읽지 않게 한다
    dup, _ = await collect_posts(SearchApi(250, dup_link=True), "blog", "q-dup", 250, *ctx)
    assert len(dup) == 249


async def test_collect_posts_stops_on_an_empty_page_and_reuses_the_cache(ctx):
    api = SearchApi(0)
    posts, _ = await collect_posts(api, "blog", "q", 1000, *ctx)
    assert posts == [] and len(api.calls) == 1

    await collect_posts(SearchApi(250), "blog", "z", 1000, *ctx)
    used = ctx[1].used
    again = SearchApi(250)
    await collect_posts(again, "blog", "z", 1000, *ctx)
    assert ctx[1].used == used and again.calls == []


async def test_collect_posts_never_asks_for_start_above_1000(ctx):
    api = SearchApi(5000)
    posts, _ = await collect_posts(api, "blog", "q", 5000, *ctx)
    assert len(api.calls) == 10
    assert max(c[1]["start"] for c in api.calls) == 901
    assert len(posts) == 1000


B1 = Brand("그래머인사이드", ("그래머 인사이드",))
B2 = Brand("천일문중등그래머")


def post(**over) -> Post:
    base = dict(source="blog", title="", description="", link="l")
    base.update(over)
    return Post(**base)


def test_filter_by_brands_matches_titles_split_by_tags_and_counts_excluded():
    kept, excluded = filter_by_brands(
        [
            post(title="<b>그래머</b> <b>인사이드</b> 후기", link="1"),
            post(title="그래머 수업 일반", link="2"),
            post(description="천일문 중등 그래머와 그래머인사이드 비교", link="3"),
        ],
        [B1, B2],
    )
    assert len(kept) == 2 and excluded == 1
    assert kept[0].brands == ["그래머인사이드"]
    assert sorted(kept[1].brands) == ["그래머인사이드", "천일문중등그래머"]


def kept(**over) -> KeptPost:
    base = dict(source="blog", title="", description="", link="l", brands=["A"])
    base.update(over)
    return KeptPost(**base)


def test_monthly_counts_buckets_by_month_brand_source_and_counts_undated():
    rows, undated = monthly_counts(
        [
            kept(date="2025-03-12", link="1"),
            kept(date="2025-03-20", link="2", brands=["A", "B"]),
            kept(date="2025-04-01", link="3"),
            kept(source="cafearticle", link="4"),
        ]
    )

    def count(month, brand, source="blog"):
        return next(
            (r["count"] for r in rows if (r["month"], r["brand"], r["source"]) == (month, brand, source)),
            None,
        )

    assert count("2025-03", "A") == 2 and count("2025-03", "B") == 1 and count("2025-04", "A") == 1
    assert undated == {"blog": 0, "cafearticle": 1, "webkr": 0}
    assert all(r["source"] != "cafearticle" for r in rows)
    assert [r["month"] for r in rows] == sorted(r["month"] for r in rows)


def test_estimate_mention_calls():
    assert estimate_mention_calls([B1, B2], ["blog", "cafearticle"], 1, 1000) == 40
    assert estimate_mention_calls([B1], ["blog"], 2, 150) == 4
    assert estimate_mention_calls([B1], ["blog"], 1, 5000) == 10  # 1000건 상한
