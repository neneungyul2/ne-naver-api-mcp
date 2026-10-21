"""후보 추출 로직. 기본 토크나이저(정규식)로 Node 테스트와 같은 입력/기대값을 검증한다."""
import pytest

from ne_naver_api_mcp.analysis.brand import Brand
from ne_naver_api_mcp.analysis.candidates import DEFAULT_STOPWORDS, extract_candidates
from ne_naver_api_mcp.analysis.mentions import KeptPost, Post

A = Brand("그래머인사이드")
B = Brand("천일문중등그래머")


def kp(**over) -> KeptPost:
    base = dict(source="blog", title="", description="", link="l", brands=["그래머인사이드"])
    base.update(over)
    return KeptPost(**base)


def bp(title: str, i: int) -> Post:
    return Post(source="blog", title=title, description="", link=f"b{i}")


def test_counts_total_by_brand_examples_and_sources():
    cands = extract_candidates(
        [
            kp(title="그래머인사이드 쎄듀 교재", link="1"),
            kp(title="그래머인사이드 쎄듀 문제집", link="2"),
            kp(title="천일문중등그래머 쎄듀 비교", link="3", brands=["천일문중등그래머"]),
        ],
        [A, B],
    )
    c = next(x for x in cands if x.term == "쎄듀")
    assert c.total == 3
    assert c.by_brand == {"그래머인사이드": 2, "천일문중등그래머": 1}
    assert len(c.examples) <= 3 and all(len(e) <= 100 for e in c.examples)
    assert c.sources == ["blog"]


def test_excludes_brand_keywords_stopwords_numbers_and_single_characters():
    cands = extract_candidates([kp(title="그래머인사이드 후기 2024 책 쎄듀", link="1")], [A, B])
    assert [c.term for c in cands] == ["쎄듀"]
    assert "후기" in DEFAULT_STOPWORDS


def test_a_token_repeated_in_one_post_counts_once():
    cands = extract_candidates([kp(title="쎄듀 쎄듀 쎄듀", description="쎄듀", link="1")], [A])
    assert next(c for c in cands if c.term == "쎄듀").total == 1


def test_html_tags_never_become_tokens():
    cands = extract_candidates(
        [kp(title="<b>쎄듀</b> <b>교재</b>", description="<b>문법</b>", link="1")], [A]
    )
    terms = [c.term for c in cands]
    assert "쎄듀" in terms
    assert not any("<" in t or ">" in t or t == "b" for t in terms)


def test_respects_top_and_sorts_by_total_then_term():
    cands = extract_candidates(
        [
            kp(title="가나다 라마바 사아자", link="1"),
            kp(title="가나다 라마바", link="2"),
            kp(title="가나다", link="3"),
        ],
        [A],
        top=2,
    )
    assert [c.term for c in cands] == ["가나다", "라마바"]
    assert [c.total for c in cands] == [3, 2]


def test_collects_source_kinds():
    cands = extract_candidates(
        [kp(title="쎄듀", link="1", source="blog"), kp(title="쎄듀", link="2", source="cafearticle")],
        [A],
    )
    assert sorted(next(c for c in cands if c.term == "쎄듀").sources) == ["blog", "cafearticle"]


def test_baseline_removes_common_words_and_reports_rate_and_lift():
    kept = [
        kp(title="그래머인사이드 문법 쎄듀 교재", link="1"),
        kp(title="그래머인사이드 문법 쎄듀 후기글", link="2"),
        kp(title="그래머인사이드 문법 능률 비교", link="3"),
    ]
    baseline = [*[bp(f"중등 문법 정리 {i}", i) for i in range(8)], bp("쎄듀 소개", 8), bp("다른 글", 9)]
    cands = extract_candidates(kept, [A], baseline=baseline)
    assert "문법" not in [c.term for c in cands]
    c = next(x for x in cands if x.term == "쎄듀")
    assert c.total == 2
    assert c.baseline_rate == pytest.approx(0.1)
    assert c.lift > 1


def test_without_baseline_rate_and_lift_are_none():
    c = extract_candidates([kp(title="그래머인사이드 쎄듀", link="1")], [A])[0]
    assert c.baseline_rate is None and c.lift is None


def test_generic_rate_is_adjustable():
    kept = [kp(title="그래머인사이드 쎄듀", link="1")]
    baseline = [bp("쎄듀 소개", 0), *[bp(f"기타 {i}", i + 1) for i in range(9)]]
    assert extract_candidates(kept, [A], baseline=baseline, generic_rate=0.05) == []
    assert len(extract_candidates(kept, [A], baseline=baseline, generic_rate=0.5)) == 1


def test_brand_name_with_a_particle_is_excluded_but_compounds_stay():
    cands = extract_candidates(
        [kp(title="그래머인사이드는 그래머인사이드를 그래머인사이드워크북 비교", link="1")], [A]
    )
    terms = [c.term for c in cands]
    assert "그래머인사이드는" not in terms and "그래머인사이드를" not in terms
    assert "그래머인사이드워크북" in terms


def test_injected_tokenizer_replaces_the_default_rule():
    cands = extract_candidates(
        [kp(title="alpha beta", link="1")], [A], tokenize=lambda text: ["커스텀"]
    )
    assert [c.term for c in cands] == ["커스텀"]


def test_to_dict_uses_camel_case_keys():
    kept = [kp(title="그래머인사이드 쎄듀", link="1")]
    d = extract_candidates(kept, [A], baseline=[bp("쎄듀", 0), bp("다른", 1), bp("글", 2), bp("a", 3),
                                                bp("b", 4), bp("c", 5), bp("d", 6), bp("e", 7)])[0].to_dict()
    assert set(d) == {"term", "total", "byBrand", "examples", "sources", "baselineRate", "lift"}
    plain = extract_candidates(kept, [A])[0].to_dict()
    assert "baselineRate" not in plain and "lift" not in plain
