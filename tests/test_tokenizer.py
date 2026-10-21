import subprocess
import sys

import pytest

from ne_naver_api_mcp.analysis.brand import Brand
from ne_naver_api_mcp.analysis.candidates import extract_candidates
from ne_naver_api_mcp.analysis.mentions import KeptPost
from ne_naver_api_mcp.analysis.tokenizer import KiwiTokenizer, default_tokenizer, regex_tokenizer


def test_regex_tokenizer_matches_the_node_rule():
    assert regex_tokenizer("그래머 인사이드 2024 책 Grammar-Inside!") == ["그래머", "인사이드", "2024", "grammar", "inside"]
    assert regex_tokenizer("") == []


@pytest.fixture(scope="module")
def kiwi() -> KiwiTokenizer:
    return KiwiTokenizer()


def test_kiwi_strips_particles(kiwi):
    tokens = kiwi("그래머인사이드는 좋아요")
    assert "그래머인사이드" in tokens
    assert "그래머인사이드는" not in tokens


def test_kiwi_keeps_only_nouns_foreign_words_and_roots(kiwi):
    tokens = kiwi("교재를 빠르게 읽었다")
    assert "교재" in tokens
    assert "빠르게" not in tokens and "읽었다" not in tokens


def test_kiwi_lowercases_english(kiwi):
    tokens = kiwi("Grammar Inside 워크북")
    assert "grammar" in tokens and "inside" in tokens


def test_kiwi_drops_single_character_tokens(kiwi):
    assert all(len(t) >= 2 for t in kiwi("책 책상 컵 쎄듀 교재"))


def test_user_dictionary_keeps_brand_words_whole():
    tokens = KiwiTokenizer(["워크북", "다사영어"])("워크북 다사영어 숙제")
    assert "워크북" in tokens and "다사영어" in tokens


def test_default_tokenizer_registers_brand_keywords_as_user_words():
    tokenize = default_tokenizer([Brand("천일문중등그래머", ("천일문 중등 그래머",))])
    tokens = tokenize("천일문중등그래머는 쎄듀 교재")
    assert "천일문중등그래머" in tokens
    assert "쎄듀" in tokens


def _run(code: str) -> str:
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, encoding="utf-8", check=True
    )
    return out.stdout.strip()


def test_kiwi_is_loaded_lazily():
    code = (
        "import sys\n"
        "import ne_naver_api_mcp.analysis.tokenizer as t\n"
        "before = 'kiwipiepy' in sys.modules\n"
        "tok = t.KiwiTokenizer(['쎄듀'])\n"
        "created = 'kiwipiepy' in sys.modules\n"
        "tok('쎄듀 교재')\n"
        "after = 'kiwipiepy' in sys.modules\n"
        "print(before, created, after)"
    )
    assert _run(code) == "False False True"


def test_candidates_with_kiwi_drop_particle_forms_and_keep_nouns(kiwi):
    kept = [
        KeptPost("blog", "그래머인사이드는 쎄듀 교재가 좋아요", "", "1", brands=["그래머인사이드"]),
        KeptPost("blog", "그래머인사이드를 쎄듀 책으로 풀었어요", "", "2", brands=["그래머인사이드"]),
    ]
    terms = [c.term for c in extract_candidates(kept, [Brand("그래머인사이드")], tokenize=kiwi)]
    assert "쎄듀" in terms
    assert not any(t.startswith("그래머인사이드") for t in terms)
